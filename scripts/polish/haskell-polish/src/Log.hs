{-# LANGUAGE LambdaCase #-}
module Log
  ( logEvent
  , logInfo
  , logWarn
  , logErr
  , logPhase
  ) where

import Control.Monad.IO.Class (liftIO)
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import System.IO (hFlush, stdout)
import Types (AppM, LogEvent(..))

-- ────────────────────────────────────────────────────────────────────
-- Core logging
-- ────────────────────────────────────────────────────────────────────

logEvent :: LogEvent -> AppM ()
logEvent = liftIO . printEvent

logInfo :: Text -> AppM ()
logInfo = logEvent . Info

logWarn :: Text -> AppM ()
logWarn = logEvent . Warn

logErr :: Text -> AppM ()
logErr = logEvent . Err

logPhase :: Int -> Text -> AppM ()
logPhase n desc = do
  logEvent (StartCheckPhase n)
  logInfo desc

-- ────────────────────────────────────────────────────────────────────
-- Render
-- ────────────────────────────────────────────────────────────────────

printEvent :: LogEvent -> IO ()
printEvent ev = do
  TIO.putStrLn $ colorize ev
  hFlush stdout

colorize :: LogEvent -> Text
colorize = \case
  StartPolish              -> cyan "[polish] " <> "Starting polish loop"
  NewPolishLoopRound n     -> cyan "[polish] " <> "=== Polish Round " <> T.pack (show n) <> " ==="
  EndPolishLoop            -> green "[polish] " <> "Polish loop complete ✓"
  StartRewrite             -> cyan "[rewrite] " <> "Starting rewrite phase"
  NewRewriteRound n        -> cyan "[rewrite] " <> "  Rewrite round " <> T.pack (show n)
  NewRewriteGuide g        -> cyan "[rewrite] " <> "  New guide: " <> T.take 80 g <> "..."
  MaxRewriteRoundsReached  -> yellow "[rewrite] " <> "Max rewrite rounds reached"
  StartCheck               -> cyan "[check] " <> "Starting finegrained check"
  StartCheckPhase n        -> cyan "[check] " <> "  Phase " <> T.pack (show n)
  EndCheckPhase n          -> cyan "[check] " <> "  Phase " <> T.pack (show n) <> " complete"
  CheckComplete            -> green "[check] " <> "Check complete ✓"
  DebateToolRun f          -> cyan "[debate-tool] " <> "run " <> T.pack f
  DebateToolResume f       -> cyan "[debate-tool] " <> "resume " <> T.pack f
  DebateToolCompact f      -> cyan "[debate-tool] " <> "compact " <> T.pack f
  MergeStart               -> cyan "[merge] " <> "Starting merge"
  MergeComplete            -> green "[merge] " <> "Merge complete ✓"
  RewriteDesignStart       -> cyan "[rewrite] " <> "Rewriting design"
  RewriteDesignComplete    -> green "[rewrite] " <> "Rewrite complete ✓"
  Info t                   -> cyan "[info] " <> t
  Warn t                   -> yellow "[warn] " <> t
  Err t                    -> red "[error] " <> t

cyan, green, yellow, red :: Text -> Text
cyan   t = "\ESC[36m" <> t <> "\ESC[0m"
green  t = "\ESC[32m" <> t <> "\ESC[0m"
yellow t = "\ESC[33m" <> t <> "\ESC[0m"
red    t = "\ESC[31m" <> t <> "\ESC[0m"
