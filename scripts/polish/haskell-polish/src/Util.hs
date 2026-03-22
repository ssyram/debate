{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE TypeApplications #-}
module Util
  ( lookupEnvText
  , readFileText
  , writeFileText
  , ensureDir
  , fileExists
  , stripYamlFrontMatter
  ) where

import Control.Monad.IO.Class (liftIO)
import Control.Monad.Except (throwError)
import qualified Control.Exception as E
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import System.Directory (createDirectoryIfMissing, doesFileExist)
import System.Environment (lookupEnv)
import Types (AppM, AppError(..))

-- ────────────────────────────────────────────────────────────────────
-- Env
-- ────────────────────────────────────────────────────────────────────

lookupEnvText :: Text -> AppM Text
lookupEnvText name = liftIO (lookupEnv (T.unpack name)) >>= \case
  Just v  -> pure (T.pack v)
  Nothing -> throwError (MissingEnvVar name)

-- ────────────────────────────────────────────────────────────────────
-- File IO within AppM
-- ────────────────────────────────────────────────────────────────────

readFileText :: FilePath -> AppM Text
readFileText fp = do
  result <- liftIO $ E.try @E.IOException (TIO.readFile fp)
  case result of
    Left e  -> throwError (FileReadError fp (T.pack (show e)))
    Right t -> pure t

writeFileText :: FilePath -> Text -> AppM ()
writeFileText fp content = do
  result <- liftIO $ E.try @E.IOException (TIO.writeFile fp content)
  case result of
    Left e  -> throwError (FileReadError fp (T.pack (show e)))
    Right _ -> pure ()

ensureDir :: FilePath -> AppM ()
ensureDir = liftIO . createDirectoryIfMissing True

fileExists :: FilePath -> AppM Bool
fileExists = liftIO . doesFileExist

-- ────────────────────────────────────────────────────────────────────
-- Topic file helpers
-- ────────────────────────────────────────────────────────────────────

-- | Strip YAML front matter (--- ... ---) and return just the markdown body
stripYamlFrontMatter :: Text -> Text
stripYamlFrontMatter txt = maybe txt renderYamlBody (yamlBodyLines txt)

yamlBodyLines :: Text -> Maybe [Text]
yamlBodyLines txt = case T.lines txt of
  ("---" : rest) -> extractYamlBody rest
  _ -> Nothing

extractYamlBody :: [Text] -> Maybe [Text]
extractYamlBody rest = case break (== "---") rest of
  (_, "---" : body) -> Just body
  _ -> Nothing

renderYamlBody :: [Text] -> Text
renderYamlBody = T.strip . T.unlines
