module CheckPipeline
  ( runCheck
  , runCheckToDir
  , renderCheckReport
  , renderIssuesFile
  ) where

import Data.Aeson (ToJSON, encode)
import qualified Data.ByteString.Lazy as LBS
import Data.Text (Text)
import qualified Data.Text as T
import Data.Text.Encoding (decodeUtf8)
import System.FilePath ((</>))

import qualified Llm
import Log
import Types
import Util (ensureDir, writeFileText)

runCheckToDir :: FilePath -> Text -> AppM CheckReport
runCheckToDir dir designDoc = do
  ensureDir dir
  logEvent StartCheck
  phases <- collectPhasesToDir dir designDoc
  finishDirCheck dir phases

type PhaseBundle = (Phase1Out, Phase2Out, Phase3Out, Phase4Out, Phase5Out)

collectPhasesToDir :: FilePath -> Text -> AppM PhaseBundle
collectPhasesToDir dir designDoc = do
  phase1 <- runPhase1ToDir dir designDoc
  phase2 <- runPhase2ToDir dir designDoc phase1
  phase3 <- runPhase3ToDir dir designDoc phase1
  phase4 <- runPhase4ToDir dir designDoc phase1 phase2 phase3
  phase5 <- runPhase5ToDir dir designDoc
  pure (phase1, phase2, phase3, phase4, phase5)

finishDirCheck :: FilePath -> PhaseBundle -> AppM CheckReport
finishDirCheck dir (phase1, phase2, phase3, phase4, phase5) =
  finishCheckWithArtifacts dir phase1 phase2 phase3 phase4 phase5

runCheck :: Text -> AppM CheckReport
runCheck designDoc = do
  logEvent StartCheck
  phases <- collectPhases designDoc
  finishCheck (reportFromBundle phases)

collectPhases :: Text -> AppM PhaseBundle
collectPhases designDoc = do
  phase1 <- runPhase1 designDoc
  phase2 <- runPhase2 designDoc phase1
  phase3 <- runPhase3 designDoc phase1
  phase4 <- runPhase4 designDoc phase1 phase2 phase3
  phase5 <- runPhase5 designDoc
  logPhaseSummary phase1 phase2 phase3 phase5
  pure (phase1, phase2, phase3, phase4, phase5)

logPhaseSummary :: Phase1Out -> Phase2Out -> Phase3Out -> Phase5Out -> AppM ()
logPhaseSummary (props,_) (issues,_) (p3,_) (p5,_) =
  logPhase1 "" props >> logPhase2 "" issues >> logPhase3 "" p3 >> logPhase5 "" p5

reportFromBundle :: PhaseBundle -> CheckReport
reportFromBundle (phase1, phase2, phase3, phase4, phase5) =
  buildReport phase1 phase2 phase3 phase4 phase5

type Phase1Out = ([Proposition], Text)
type Phase2Out = ([Issue], Text)
type Phase3Out = (Llm.Phase3Result, Text)
type Phase4Out = (Llm.Phase4Result, Text)
type Phase5Out = (Llm.Phase5Result, Text)

runPhase1ToDir :: FilePath -> Text -> AppM Phase1Out
runPhase1ToDir dir designDoc = runPhaseWithWrite dir "phase1_propositions.json" logPhase1 (runPhase1 designDoc)

runPhase2ToDir :: FilePath -> Text -> Phase1Out -> AppM Phase2Out
runPhase2ToDir dir designDoc (_, propsJson) = runPhaseWithWrite dir "phase2_issues.json" logPhase2 (runPhase2 designDoc ([], propsJson))

runPhase3ToDir :: FilePath -> Text -> Phase1Out -> AppM Phase3Out
runPhase3ToDir dir designDoc (_, propsJson) = runPhaseWithWrite dir "phase3_matrix.json" logPhase3 (runPhase3 designDoc ([], propsJson))

runPhase4ToDir :: FilePath -> Text -> Phase1Out -> Phase2Out -> Phase3Out -> AppM Phase4Out
runPhase4ToDir dir designDoc phase1 phase2 phase3 =
  runPhaseWithWrite dir "phase4_summary.json" ignorePhaseLog (runPhase4 designDoc phase1 phase2 phase3)

runPhase5ToDir :: FilePath -> Text -> AppM Phase5Out
runPhase5ToDir dir designDoc =
  runPhaseWithWrite dir "phase5_suspicious.json" logPhase5 (runPhase5 designDoc)

ignorePhaseLog :: Text -> a -> AppM ()
ignorePhaseLog _ _ = pure ()

runPhase1 :: Text -> AppM Phase1Out
runPhase1 designDoc = do
  props <- Llm.checkPhase1 designDoc
  pure (props, jsonText props)

runPhase2 :: Text -> Phase1Out -> AppM Phase2Out
runPhase2 designDoc (_, propsJson) = do
  issues <- Llm.checkPhase2 designDoc propsJson
  pure (issues, jsonText issues)

runPhase3 :: Text -> Phase1Out -> AppM Phase3Out
runPhase3 designDoc (_, propsJson) = do
  result <- Llm.checkPhase3 designDoc propsJson
  pure (result, jsonText result)

runPhase4 :: Text -> Phase1Out -> Phase2Out -> Phase3Out -> AppM Phase4Out
runPhase4 designDoc (_, propsJson) (_, issuesJson) (_, matrixJson) = do
  result <- Llm.checkPhase4 designDoc propsJson issuesJson matrixJson
  pure (result, jsonText result)

runPhase5 :: Text -> AppM Phase5Out
runPhase5 designDoc = do
  result <- Llm.checkPhase5 designDoc
  pure (result, jsonText result)

runPhaseWithWrite :: ToJSON a => FilePath -> FilePath -> (Text -> a -> AppM ()) -> AppM (a, Text) -> AppM (a, Text)
runPhaseWithWrite dir name after action = do
  (value, body) <- action
  writeFileText (dir </> name) body
  after body value
  pure (value, body)

logPhase1 :: Text -> [Proposition] -> AppM ()
logPhase1 _ props = logInfo $ "Phase 1 extracted " <> countText props <> " propositions"

logPhase2 :: Text -> [Issue] -> AppM ()
logPhase2 _ issues = logInfo $ "Phase 2 found " <> countText issues <> " issues"

logPhase3 :: Text -> Llm.Phase3Result -> AppM ()
logPhase3 _ result = logInfo $ "Phase 3: " <> countText (Llm.p3DesignPoints result) <> " design points, " <> countText (Llm.p3Matrix result) <> " matrix entries"

logPhase5 :: Text -> Llm.Phase5Result -> AppM ()
logPhase5 _ result = logInfo $ "Phase 5: " <> countText (Llm.p5SuspiciousClaims result) <> " suspicious claims, " <> countText (Llm.p5QAFeedback result) <> " Q&A feedback"

finishCheckWithArtifacts :: FilePath -> Phase1Out -> Phase2Out -> Phase3Out -> Phase4Out -> Phase5Out -> AppM CheckReport
finishCheckWithArtifacts dir phase1 phase2 phase3 phase4 phase5 = do
  let report = reportFromBundle (phase1, phase2, phase3, phase4, phase5)
  writeFileText (dir </> "check_report.md") (renderCheckReport report)
  writeFileText (dir </> "issues.md") (renderIssuesFile report)
  finishCheck report

finishCheck :: CheckReport -> AppM CheckReport
finishCheck report = do
  logEvent CheckComplete
  logInfo $ "Check: " <> if okToGo report then "OK ✓" else "Issues ✗"
  pure report

buildReport :: Phase1Out -> Phase2Out -> Phase3Out -> Phase4Out -> Phase5Out -> CheckReport
buildReport (props, _) (issues, _) (p3, _) (p4, _) (p5, _) = CheckReport
  { crPropositions     = props
  , crIssues           = issues
  , crDesignPoints     = Llm.p3DesignPoints p3
  , crMatrix           = Llm.p3Matrix p3
  , crSuspiciousClaims = Llm.p5SuspiciousClaims p5
  , crQAFeedback       = Llm.p5QAFeedback p5
  , crSummary          = Llm.p4Summary p4
  , crHighlights       = Llm.p4Highlights p4
  }

renderCheckReport :: CheckReport -> Text
renderCheckReport cr = T.unlines $
  [ "# Finegrained Check Report", ""
  , "## Phase 1: 命题 (" <> countText (crPropositions cr) <> ")", ""
  ] ++ map renderProp (crPropositions cr) ++
  [ "", "## Phase 2: 矛盾与遗漏 (" <> countText (crIssues cr) <> ")", "" ] ++
  renderIssuesBySev (crIssues cr) ++
  [ "", "## Phase 3: 交叉覆盖矩阵", "", "### Design Points", "" ] ++
  map renderDp (crDesignPoints cr) ++
  [ "", "### Gaps / Weaknesses", "" ] ++
  map renderCell (crMatrix cr) ++
  [ "", "## Phase 4: 总结", "", crSummary cr ] ++
  renderHighlights (crHighlights cr) ++
  renderSuspiciousClaimsSection (crSuspiciousClaims cr) ++
  renderQAFeedbackSection (crQAFeedback cr)

renderHighlights :: [Text] -> [Text]
renderHighlights [] = []
renderHighlights hs = ["", "### 亮点", ""] ++ map ("- " <>) hs

renderProp :: Proposition -> Text
renderProp p = "- **" <> propId p <> "** (" <> propSection p <> "): " <> propText p

renderIssuesBySev :: [Issue] -> [Text]
renderIssuesBySev issues = concatMap (renderIssueGroup issues)
  [ ("高严重度", ((>= High) . issueSeverity))
  , ("中严重度", ((== Medium) . issueSeverity))
  , ("低严重度", ((<= Low) . issueSeverity))
  ]

renderIssueGroup :: [Issue] -> (Text, Issue -> Bool) -> [Text]
renderIssueGroup issues (title, keep) = ["### " <> title] ++ map renderIssue (filter keep issues) ++ [""]

renderIssue :: Issue -> Text
renderIssue i = "- [" <> renderIssueType (issueType i) <> "] " <> T.intercalate " vs " (issueRefs i) <> ": " <> issueDesc i

renderIssueType :: IssueType -> Text
renderIssueType Contradiction = "矛盾"
renderIssueType Omission = "遗漏"
renderIssueType MatrixGap = "矩阵空洞"

renderDp :: DesignPoint -> Text
renderDp dp = "- **" <> dpId dp <> "**: " <> dpTitle dp

renderCell :: CoverageCell -> Text
renderCell cc = "- " <> ccPointA cc <> " × " <> ccPointB cc <> " → " <> renderCoverageStatus (ccStatus cc) <> ": " <> ccComment cc

renderCoverageStatus :: CoverageStatus -> Text
renderCoverageStatus Covered = "✓"
renderCoverageStatus Weak = "⚠"
renderCoverageStatus Gap = "✗"

jsonText :: ToJSON a => a -> Text
jsonText = decodeUtf8 . LBS.toStrict . encode

renderIssuesFile :: CheckReport -> Text
renderIssuesFile cr = T.unlines $
  [ "# 需要决策的打磨点（按严重程度排名）"
  , ""
  , "> 矛盾、遗漏、矩阵空洞按 Critical → Low 排序；可疑断言和 Q&A 反馈单列。"
  , ""
  ] ++ concatMap (renderSevSection (crIssues cr)) [Critical, High, Medium, Low]
    ++ renderMatrixIssues (crMatrix cr)
    ++ renderSuspiciousClaimsSection (crSuspiciousClaims cr)
    ++ renderQAFeedbackSection (crQAFeedback cr)

renderSevSection :: [Issue] -> Severity -> [Text]
renderSevSection issues sev = renderOptionalSection (severityTitle sev) (map renderIssue (filter ((== sev) . issueSeverity) issues))

severityTitle :: Severity -> Text
severityTitle Critical = "Critical"
severityTitle High = "High"
severityTitle Medium = "Medium"
severityTitle Low = "Low"

renderMatrixIssues :: [CoverageCell] -> [Text]
renderMatrixIssues cells = renderOptionalSection "矩阵空洞 / 覆盖薄弱" (map renderCell (filter ((/= Covered) . ccStatus) cells))

renderOptionalSection :: Text -> [Text] -> [Text]
renderOptionalSection _ [] = []
renderOptionalSection title xs = ["## " <> title, ""] ++ xs ++ [""]

countText :: [a] -> Text
countText = T.pack . show . length

renderSuspiciousClaimsSection :: [SuspiciousClaim] -> [Text]
renderSuspiciousClaimsSection = renderOptionalSection "Phase 5: 可疑断言" . map renderSuspiciousClaim

renderSuspiciousClaim :: SuspiciousClaim -> Text
renderSuspiciousClaim sc = "- **" <> scId sc <> "** [" <> scLocation sc <> "] " <> scClaim sc <> " — " <> scReason sc

renderQAFeedbackSection :: [QAFeedback] -> [Text]
renderQAFeedbackSection = renderOptionalSection "Phase 5: Q&A 审查反馈" . map renderQAFeedback

renderQAFeedback :: QAFeedback -> Text
renderQAFeedback (QAStillValid i r) = "- **" <> i <> "** ✓ 保留：" <> r
renderQAFeedback (QARedundant  i r) = "- **" <> i <> "** 🗑 冗余可删：" <> r
renderQAFeedback (QAStillWeak  i r) = "- **" <> i <> "** ⚠ 依然不足：" <> r
