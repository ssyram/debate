{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE MultiWayIf #-}
module PolishLoop
  ( runPolish
  ) where

import Control.Monad (foldM)
import Control.Monad.Except (throwError)
import Control.Monad.Reader (asks)
import qualified Data.Text as T
import System.FilePath ((</>))

import CheckPipeline (renderCheckReport, renderIssuesFile, runCheckToDir)
import qualified DebateTool
import qualified Llm
import Log
import Types
import Util (ensureDir, fileExists, readFileText, writeFileText)

forLoop :: Monad m => a -> [b] -> (a -> b -> m a) -> m a
forLoop initVal xs step = foldM step initVal xs

polishDir :: FilePath -> Int -> FilePath
polishDir base n = base </> ("polish_round_" <> show n)

rewriteDesignFile :: FilePath -> Int -> Int -> FilePath
rewriteDesignFile base pr ir = polishDir base pr </> ("rewrite_" <> show pr <> "_" <> show ir <> ".md")

checkDir :: FilePath -> Int -> Int -> FilePath
checkDir base pr ir = polishDir base pr </> ("check_" <> show pr <> "_" <> show ir)

mergeGuideFile :: FilePath -> Int -> Int -> FilePath
mergeGuideFile base pr ir = polishDir base pr </> ("merge_" <> show pr <> "_" <> show ir <> ".md")

runPolish :: AppM Design
runPolish = do
  prepareOutputDir
  logEvent StartPolish
  pair <- loadInitialInputs
  writeInitialArtifactsFor pair
  uncurry (polishLoop 1) pair

prepareOutputDir :: AppM ()
prepareOutputDir = asks cfgOutputDir >>= ensureDir

loadInitialInputs :: AppM (Design, RewriteGuide)
loadInitialInputs = do
  design <- runOrLoadDesign
  decisions <- runOrLoadDecisions design
  pure (design, decisions)

writeInitialArtifactsFor :: (Design, RewriteGuide) -> AppM ()
writeInitialArtifactsFor (design, decisions) = do
  outDir <- asks cfgOutputDir
  writeInitialArtifacts outDir design decisions

writeInitialArtifacts :: FilePath -> Design -> RewriteGuide -> AppM ()
writeInitialArtifacts outDir design decisions = do
  writeFileText (outDir </> "initial_design.md") design
  writeFileText (outDir </> "initial_decisions.md") decisions

polishLoop :: Int -> Design -> RewriteGuide -> AppM Design
polishLoop roundNum design decisions = do
  logEvent (NewPolishLoopRound roundNum)
  maxRounds <- asks cfgMaxPolishRounds
  if roundNum > maxRounds then finishAtMaxRounds design else runPolishRound roundNum design decisions

finishAtMaxRounds :: Design -> AppM Design
finishAtMaxRounds design = do
  outDir <- asks cfgOutputDir
  logWarn "Max polish rounds reached"
  writeFileText (outDir </> "final_design.md") design
  pure design

runPolishRound :: Int -> Design -> RewriteGuide -> AppM Design
runPolishRound roundNum design decisions = do
  rdir <- preparePolishRound roundNum design decisions
  (newDesign, check) <- rewriteWithArtifacts roundNum design decisions
  writePolishRoundArtifacts rdir newDesign check
  advancePolish roundNum newDesign decisions check

preparePolishRound :: Int -> Design -> RewriteGuide -> AppM FilePath
preparePolishRound roundNum design decisions = do
  outDir <- asks cfgOutputDir
  let rdir = polishDir outDir roundNum
  ensureDir rdir
  writeFileText (rdir </> "input_design.md") design
  writeFileText (rdir </> "input_decisions.md") decisions
  pure rdir

writePolishRoundArtifacts :: FilePath -> Design -> CheckReport -> AppM ()
writePolishRoundArtifacts rdir design check = do
  writeFileText (rdir </> "design_after_rewrite.md") design
  writeFileText (rdir </> "check_after_rewrite.md") (renderCheckReport check)

advancePolish :: Int -> Design -> RewriteGuide -> CheckReport -> AppM Design
advancePolish roundNum newDesign decisions check =
  if okToGo check then finishPolish newDesign else continuePolish roundNum newDesign decisions check

finishPolish :: Design -> AppM Design
finishPolish design = do
  outDir <- asks cfgOutputDir
  logEvent EndPolishLoop
  logInfo "Check passed — polish complete"
  writeFileText (outDir </> "final_design.md") design
  pure design

continuePolish :: Int -> Design -> RewriteGuide -> CheckReport -> AppM Design
continuePolish roundNum newDesign decisions check = do
  logFile <- asks cfgLogFile
  newDecisions <- requestNextDecisions logFile decisions newDesign check
  saveRoundDecisions roundNum newDecisions
  logNextRound roundNum
  polishLoop (nextRound roundNum) newDesign newDecisions

saveRoundDecisions :: Int -> RewriteGuide -> AppM ()
saveRoundDecisions roundNum = writeRoundFile roundNum "debate_decisions.md"

writeRoundFile :: Int -> FilePath -> T.Text -> AppM ()
writeRoundFile roundNum name content = do
  outDir <- asks cfgOutputDir
  writeFileText (polishDir outDir roundNum </> name) content

logNextRound :: Int -> AppM ()
logNextRound roundNum = logInfo $ "Debate complete → round " <> T.pack (show (nextRound roundNum))

nextRound :: Int -> Int
nextRound roundNum = roundNum + 1

requestNextDecisions :: FilePath -> RewriteGuide -> Design -> CheckReport -> AppM RewriteGuide
requestNextDecisions logFile decisions design check = do
  DebateTool.compactLog logFile
  DebateTool.resumeForRulings logFile decisions design (renderIssuesFile check)

type RewriteState = (Design, CheckReport, RewriteGuide)

data RewriteProgress
  = RewriteContinue RewriteState
  | RewriteDone Design CheckReport

rewriteWithArtifacts :: Int -> Design -> RewriteGuide -> AppM (Design, CheckReport)
rewriteWithArtifacts polishRound design decisions = do
  logEvent StartRewrite
  final <- initialRewriteProgress design decisions >>= runRewriteRounds polishRound
  finalizeRewrite final

initialRewriteProgress :: Design -> RewriteGuide -> AppM RewriteProgress
initialRewriteProgress design decisions = pure (RewriteContinue (design, emptyCheckReport, decisions))

runRewriteRounds :: Int -> RewriteProgress -> AppM RewriteProgress
runRewriteRounds polishRound progress = do
  outDir <- asks cfgOutputDir
  maxRounds <- asks cfgMaxRewriteRounds
  forLoop progress [1 .. maxRounds] (rewriteStep outDir polishRound)

rewriteStep :: FilePath -> Int -> RewriteProgress -> Int -> AppM RewriteProgress
rewriteStep _ _ done@(RewriteDone _ _) _ = pure done
rewriteStep outDir polishRound (RewriteContinue state) roundNum = do
  logEvent (NewRewriteRound roundNum)
  runRewriteRound outDir polishRound state roundNum

runRewriteRound :: FilePath -> Int -> RewriteState -> Int -> AppM RewriteProgress
runRewriteRound outDir polishRound state roundNum = do
  newDesign <- rewriteAndSave outDir polishRound roundNum state
  newCheck <- runCheckToDir (checkDir outDir polishRound roundNum) newDesign
  mergeResult <- mergeRewriteRound state newDesign newCheck
  saveMergeGuide outDir polishRound roundNum mergeResult
  toRewriteProgress newDesign newCheck mergeResult

rewriteAndSave :: FilePath -> Int -> Int -> RewriteState -> AppM Design
rewriteAndSave outDir polishRound roundNum (curDesign, _, curGuide) = do
  newDesign <- Llm.rewriteDesign curDesign curGuide
  writeFileText (rewriteDesignFile outDir polishRound roundNum) newDesign
  logInfo $ "  Rewrite saved → " <> T.pack (rewriteDesignFile outDir polishRound roundNum)
  pure newDesign

mergeRewriteRound :: RewriteState -> Design -> CheckReport -> AppM Llm.MergeResult
mergeRewriteRound (_, curCheck, decisions) newDesign newCheck =
  Llm.mergeCheckAndDecisions newDesign decisions (renderIssuesFile newCheck) (renderIssuesFile curCheck)

saveMergeGuide :: FilePath -> Int -> Int -> Llm.MergeResult -> AppM ()
saveMergeGuide outDir polishRound roundNum =
  writeFileText (mergeGuideFile outDir polishRound roundNum) . Llm.mrNewGuide

toRewriteProgress :: Design -> CheckReport -> Llm.MergeResult -> AppM RewriteProgress
toRewriteProgress newDesign newCheck mergeResult =
  if noNewGuide (mergeGuide mergeResult)
    then finishRewriteEarly newDesign newCheck
    else continueRewrite newDesign newCheck mergeResult

mergeGuide :: Llm.MergeResult -> RewriteGuide
mergeGuide = Llm.mrNewGuide

finishRewriteEarly :: Design -> CheckReport -> AppM RewriteProgress
finishRewriteEarly newDesign newCheck = do
  logInfo "No new guide — rewrite resolved all addressable issues"
  pure (RewriteDone newDesign newCheck)

continueRewrite :: Design -> CheckReport -> Llm.MergeResult -> AppM RewriteProgress
continueRewrite newDesign newCheck mergeResult = do
  logEvent (NewRewriteGuide (mergeGuide mergeResult))
  pure $ RewriteContinue (newDesign, unresolvedCheck newCheck mergeResult, mergeGuide mergeResult)

unresolvedCheck :: CheckReport -> Llm.MergeResult -> CheckReport
unresolvedCheck check mergeResult = check { crIssues = Llm.mrUnresolvedIssues mergeResult }

finalizeRewrite :: RewriteProgress -> AppM (Design, CheckReport)
finalizeRewrite (RewriteDone design check) = pure (design, check)
finalizeRewrite (RewriteContinue state) = finalizeRewriteAtCap state

finalizeRewriteAtCap :: RewriteState -> AppM (Design, CheckReport)
finalizeRewriteAtCap (design, check, guide) = do
  logEvent MaxRewriteRoundsReached
  pure (design, combineCheckAndGuide check guide)

runOrLoadDesign :: AppM Design
runOrLoadDesign = asks cfgDesignFile >>= maybe loadDesignFromLog readDesignFile

readDesignFile :: FilePath -> AppM Design
readDesignFile file = logInfo ("Loading design from file: " <> T.pack file) >> readFileText file

loadDesignFromLog :: AppM Design
loadDesignFromLog = do
  logFile <- asks cfgLogFile
  let summaryPath = logFile <> ".summary.md"
  hasSummary <- fileExists summaryPath
  if hasSummary then readExistingSummary summaryPath else runTopicMode logFile

readExistingSummary :: FilePath -> AppM Design
readExistingSummary summaryPath = do
  logInfo $ "Loading design from existing summary: " <> T.pack summaryPath
  readFileText summaryPath

runTopicMode :: FilePath -> AppM Design
runTopicMode logFile = do
  topicFile <- requireTopicFile
  logInfo $ "Running debate-tool run on topic: " <> T.pack topicFile
  DebateTool.runTopic topicFile logFile

requireTopicFile :: AppM FilePath
requireTopicFile = asks cfgTopicFile >>= maybe (throwError CannotFindDesign) pure

runOrLoadDecisions :: Design -> AppM RewriteGuide
runOrLoadDecisions design = asks cfgDecisionFile >>= maybe (resolveIssues design) readDecisionFile

readDecisionFile :: FilePath -> AppM RewriteGuide
readDecisionFile file = logInfo ("Loading decisions from file: " <> T.pack file) >> readFileText file

resolveIssues :: Design -> AppM RewriteGuide
resolveIssues design = do
  outDir <- asks cfgOutputDir
  logFile <- asks cfgLogFile
  issuesText <- loadIssuesText design outDir
  writeInitialIssues outDir issuesText
  runInitialResume logFile outDir design issuesText

writeInitialIssues :: FilePath -> T.Text -> AppM ()
writeInitialIssues outDir = writeFileText (outDir </> "initial_issues.md")

loadIssuesText :: Design -> FilePath -> AppM T.Text
loadIssuesText design outDir = asks cfgIssuesFile >>= maybe (runInitialCheck design outDir) readIssuesFile

readIssuesFile :: FilePath -> AppM T.Text
readIssuesFile file = logInfo ("Loading issues from file: " <> T.pack file) >> readFileText file

runInitialCheck :: Design -> FilePath -> AppM T.Text
runInitialCheck design outDir = do
  logInfo "No predefined issues — running check"
  renderIssuesFile <$> runCheckToDir (outDir </> "initial_check") design

runInitialResume :: FilePath -> FilePath -> Design -> T.Text -> AppM RewriteGuide
runInitialResume logFile outDir design issuesText = do
  logInfo "Running debate-tool resume for initial decisions"
  result <- DebateTool.resumeForRulings logFile "" design issuesText
  writeFileText (outDir </> "initial_debate_summary.md") result
  pure result
