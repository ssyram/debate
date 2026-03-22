{-# LANGUAGE LambdaCase #-}
module Main (main) where

import Control.Monad.IO.Class (liftIO)
import Control.Monad.Reader (asks)
import System.Environment (getArgs)
import System.Exit (exitFailure, exitSuccess)
import System.FilePath (takeDirectory, takeBaseName, (</>))
import qualified Data.Text as T
import qualified Data.Text.IO as TIO

import Types
import Util (lookupEnvText, ensureDir)
import PolishLoop (runPolish)

-- ────────────────────────────────────────────────────────────────────

data PolishArgs = PolishArgs
  { paTopicFile    :: Maybe FilePath   -- ^ --topic: fresh debate-tool run
  , paLogFile      :: Maybe FilePath   -- ^ --log:   resume existing log
  , paDesignFile   :: Maybe FilePath   -- ^ --design: shortcut, skip run/resume for design
  , paDecisionFile :: Maybe FilePath   -- ^ --decisions: shortcut, skip check+debate
  , paIssuesFile   :: Maybe FilePath   -- ^ --issues: shortcut, skip check
  , paModel        :: Maybe String
  , paOutputDir    :: Maybe FilePath
  , paMaxPolish    :: Maybe Int
  , paMaxRewrite   :: Maybe Int
  }

defaultPA :: PolishArgs
defaultPA = PolishArgs Nothing Nothing Nothing Nothing Nothing Nothing Nothing Nothing Nothing

usage :: String
usage = unlines
  [ "Usage: polish (--topic FILE | --log FILE)"
  , "             [--design FILE] [--decisions FILE] [--issues FILE]"
  , "             [--model MODEL] [--output-dir DIR]"
  , "             [--max-polish-rounds N] [--max-rewrite-rounds N]"
  , ""
  , "  --topic FILE       Run debate-tool on topic.md (fresh start)"
  , "  --log   FILE       Resume existing debate log"
  , "  --design FILE      Skip design generation (load from file)"
  , "  --decisions FILE   Skip check+debate for decisions (load from file)"
  , "  --issues FILE      Skip check, use pre-computed issues"
  ]

parseArgs :: [String] -> Either String PolishArgs
parseArgs = finalizePolishArgs . foldPolishArgs defaultPA

foldPolishArgs :: PolishArgs -> [String] -> Either String PolishArgs
foldPolishArgs pa [] = Right pa
foldPolishArgs pa ("--topic" : f : r) = foldPolishArgs pa { paTopicFile = Just f } r
foldPolishArgs pa ("--log" : f : r) = foldPolishArgs pa { paLogFile = Just f } r
foldPolishArgs pa ("--design" : f : r) = foldPolishArgs pa { paDesignFile = Just f } r
foldPolishArgs pa ("--decisions" : f : r) = foldPolishArgs pa { paDecisionFile = Just f } r
foldPolishArgs pa ("--issues" : f : r) = foldPolishArgs pa { paIssuesFile = Just f } r
foldPolishArgs pa ("--model" : m : r) = foldPolishArgs pa { paModel = Just m } r
foldPolishArgs pa ("--output-dir" : d : r) = foldPolishArgs pa { paOutputDir = Just d } r
foldPolishArgs pa ("--max-polish-rounds" : n : r) = foldPolishArgs pa { paMaxPolish = Just (read n) } r
foldPolishArgs pa ("--max-rewrite-rounds" : n : r) = foldPolishArgs pa { paMaxRewrite = Just (read n) } r
foldPolishArgs pa (f : r)
  | paTopicFile pa == Nothing = foldPolishArgs pa { paTopicFile = Just f } r
  | otherwise = Left $ "Unknown argument: " ++ f

finalizePolishArgs :: Either String PolishArgs -> Either String PolishArgs
finalizePolishArgs = (>>= requirePolishInput)

requirePolishInput :: PolishArgs -> Either String PolishArgs
requirePolishInput pa =
  if hasPolishInput pa then Right pa else Left usage

hasPolishInput :: PolishArgs -> Bool
hasPolishInput pa = any isJust
  [ paTopicFile pa
  , paLogFile pa
  , paDesignFile pa
  ]

isJust :: Maybe a -> Bool
isJust (Just _) = True
isJust Nothing = False

-- ────────────────────────────────────────────────────────────────────

main :: IO ()
main = do
  args <- getArgs
  case parseArgs args of
    Left err -> putStrLn err >> exitFailure
    Right pa -> runPolishMain pa

runPolishMain :: PolishArgs -> IO ()
runPolishMain pa = do
  cfgResult <- buildConfig pa
  case cfgResult of
    Left e -> putStrLn ("Config error: " ++ show e) >> exitFailure
    Right cfg -> runPolishWithConfig cfg

runPolishWithConfig :: Config -> IO ()
runPolishWithConfig cfg = do
  _ <- runAppM cfg (ensureDir (cfgOutputDir cfg))
  result <- runAppM cfg runPolishApp
  case result of
    Left e -> putStrLn ("Polish failed: " ++ show e) >> exitFailure
    Right _ -> exitSuccess

runPolishApp :: AppM Design
runPolishApp = do
  finalDesign <- runPolish
  printPolishSummary
  pure finalDesign

printPolishSummary :: AppM ()
printPolishSummary = do
  outDir <- asks cfgOutputDir
  liftIO $ do
    TIO.putStrLn ""
    TIO.putStrLn $ "Working log dir: " <> T.pack outDir
    TIO.putStrLn $ "Final design:    " <> T.pack (finalDesignPath outDir)

finalDesignPath :: FilePath -> FilePath
finalDesignPath outDir = outDir </> "final_design.md"

buildConfig :: PolishArgs -> IO (Either AppError Config)
buildConfig pa = runAppM defaultConfig $ do
  baseUrl <- lookupEnvText "DEBATE_BASE_URL"
  apiKey  <- lookupEnvText "DEBATE_API_KEY"
  pure (configFromArgs pa baseUrl apiKey)

configFromArgs :: PolishArgs -> T.Text -> T.Text -> Config
configFromArgs pa baseUrl apiKey = defaultConfig
  { cfgBaseUrl = baseUrl
  , cfgApiKey = apiKey
  , cfgModel = polishModel pa
  , cfgLogFile = polishLogFile pa
  , cfgTopicFile = paTopicFile pa
  , cfgDesignFile = paDesignFile pa
  , cfgDecisionFile = paDecisionFile pa
  , cfgIssuesFile = paIssuesFile pa
  , cfgOutputDir = polishOutputDir pa
  , cfgMaxPolishRounds = maybe (cfgMaxPolishRounds defaultConfig) id (paMaxPolish pa)
  , cfgMaxRewriteRounds = maybe (cfgMaxRewriteRounds defaultConfig) id (paMaxRewrite pa)
  }

polishModel :: PolishArgs -> T.Text
polishModel pa = maybe (cfgModel defaultConfig) T.pack (paModel pa)

polishOutputDir :: PolishArgs -> FilePath
polishOutputDir pa = case paOutputDir pa of
  Just d -> d
  Nothing -> derivedPolishOutputDir pa

derivedPolishOutputDir :: PolishArgs -> FilePath
derivedPolishOutputDir pa = case (paTopicFile pa, paLogFile pa) of
  (Just f, _) -> polishSiblingDir f
  (_, Just f) -> polishSiblingDir f
  _ -> "./polish-out"

polishSiblingDir :: FilePath -> FilePath
polishSiblingDir file = takeDirectory file </> takeBaseName file ++ "_polish"

polishLogFile :: PolishArgs -> FilePath
polishLogFile pa = case paLogFile pa of
  Just f -> f
  Nothing -> defaultPolishLogFile (polishOutputDir pa) (paTopicFile pa)

defaultPolishLogFile :: FilePath -> Maybe FilePath -> FilePath
defaultPolishLogFile outDir (Just f) = outDir </> takeBaseName f ++ "_log.json"
defaultPolishLogFile outDir Nothing = outDir </> "debate_log.json"
