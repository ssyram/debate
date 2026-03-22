{-# LANGUAGE LambdaCase #-}
module Main (main) where

import Control.Monad.IO.Class (liftIO)
import System.Environment (getArgs)
import System.Exit (exitFailure, exitSuccess)
import System.FilePath (takeDirectory, takeBaseName, (</>))
import qualified Data.Text as T
import qualified Data.Text.IO as TIO

import Types
import Util (lookupEnvText, readFileText, ensureDir, stripYamlFrontMatter)
import CheckPipeline (runCheckToDir)

-- ────────────────────────────────────────────────────────────────────

data CheckArgs = CheckArgs
  { caInput  :: FilePath
  , caOutput :: Maybe FilePath
  , caModel  :: Maybe String
  }

parseArgs :: [String] -> Either String CheckArgs
parseArgs = finalizeCheckArgs . foldCheckArgs (CheckArgs "" Nothing Nothing)

foldCheckArgs :: CheckArgs -> [String] -> Either String CheckArgs
foldCheckArgs ca [] = Right ca
foldCheckArgs ca ("--input" : f : rest) = foldCheckArgs ca { caInput = f } rest
foldCheckArgs ca ("--output" : f : rest) = foldCheckArgs ca { caOutput = Just f } rest
foldCheckArgs ca ("--model" : m : rest) = foldCheckArgs ca { caModel = Just m } rest
foldCheckArgs ca (f : rest)
  | null (caInput ca) = foldCheckArgs ca { caInput = f } rest
  | otherwise = Left $ "Unknown argument: " ++ f

finalizeCheckArgs :: Either String CheckArgs -> Either String CheckArgs
finalizeCheckArgs = (>>= requireCheckInput)

requireCheckInput :: CheckArgs -> Either String CheckArgs
requireCheckInput ca
  | null (caInput ca) = Left checkUsage
  | otherwise = Right ca

checkUsage :: String
checkUsage = "Usage: check --input FILE [--output DIR] [--model MODEL]"

-- ────────────────────────────────────────────────────────────────────

main :: IO ()
main = do
  args <- getArgs
  case parseArgs args of
    Left err -> putStrLn err >> exitFailure
    Right ca -> runCheckMain ca

runCheckMain :: CheckArgs -> IO ()
runCheckMain ca = do
  cfgResult <- buildConfig ca
  case cfgResult of
    Left e -> putStrLn ("Config error: " ++ show e) >> exitFailure
    Right cfg -> runCheckWithConfig ca cfg

runCheckWithConfig :: CheckArgs -> Config -> IO ()
runCheckWithConfig ca cfg = do
  result <- runAppM cfg (runCheckApp ca)
  case result of
    Left e -> putStrLn ("Error: " ++ show e) >> exitFailure
    Right report -> finishCheckMain report

runCheckApp :: CheckArgs -> AppM CheckReport
runCheckApp ca = do
  ensureDir (checkOutputDir ca)
  design <- loadCheckDesign ca
  report <- runCheckToDir (checkOutputDir ca) design
  printCheckArtifacts ca
  pure report

loadCheckDesign :: CheckArgs -> AppM T.Text
loadCheckDesign ca = stripYamlFrontMatter <$> readFileText (caInput ca)

printCheckArtifacts :: CheckArgs -> AppM ()
printCheckArtifacts ca = liftIO $ TIO.putStrLn $ "\n📁 Check artifacts in: " <> T.pack (checkOutputDir ca)

finishCheckMain :: CheckReport -> IO ()
finishCheckMain report = do
  putStrLn (checkStatusMessage report)
  exitSuccess

checkStatusMessage :: CheckReport -> String
checkStatusMessage report
  | okToGo report = "✓ Check passed — no blocking issues"
  | otherwise = "✗ Check found blocking issues"

checkOutputDir :: CheckArgs -> FilePath
checkOutputDir ca = case caOutput ca of
  Just d -> d
  Nothing -> defaultCheckOutputDir (caInput ca)

defaultCheckOutputDir :: FilePath -> FilePath
defaultCheckOutputDir input = takeDirectory input </> takeBaseName input ++ "_check"

buildConfig :: CheckArgs -> IO (Either AppError Config)
buildConfig ca = runAppM defaultConfig $ do
  baseUrl <- lookupEnvText "DEBATE_BASE_URL"
  apiKey  <- lookupEnvText "DEBATE_API_KEY"
  let model = maybe (cfgModel defaultConfig) T.pack (caModel ca)
  pure defaultConfig
    { cfgBaseUrl = baseUrl, cfgApiKey = apiKey, cfgModel = model }
