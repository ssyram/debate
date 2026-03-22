{-# LANGUAGE ScopedTypeVariables #-}
module DebateTool
  ( runTopic
  , resumeForRulings
  , compactLog
  ) where

import Control.Exception      (try, SomeException)
import Control.Monad.Except   (throwError)
import Control.Monad.IO.Class (liftIO)
import qualified Data.Text    as T
import qualified Data.Text.IO as TIO
import System.Exit            (ExitCode(..))
import System.IO              (hClose)
import System.IO.Temp         (withSystemTempFile)
import System.Process         (readProcessWithExitCode)

import Log (logEvent, logInfo)
import Types

compactRefineMsg :: String
compactRefineMsg =
  "重点记录：1) 设计演进轨迹（哪些概念/方案何时被修改采纳及原因）；\
  \2) 已废弃路径（所有被否决方案及废弃理由，已否决路径不得以变体重新提出）；\
  \3) 当前各方最新立场与共识。\
  \淡化具体论证细节，突出结论与演进脉络。"

buildRulingsTopic :: RewriteGuide -> Design -> T.Text -> T.Text
buildRulingsTopic oldDecisions design newIssues = T.unlines
  [ "---"
  , "judge_instructions: |"
  , "  本轮裁判任务分四部分："
  , "  "
  , "  **第一部分：重审被反对的旧裁决**"
  , "  对辩手明确「不服」的旧裁决逐条处理："
  , "  列出双方核心论据（引用原文），呈现对立，给出推荐裁决及理由。"
  , "  "
  , "  **第二部分：新 issues 逐条裁决**（矛盾、遗漏、矩阵空洞）"
  , "  如辩手有对立立场，清晰写明各方观点；"
  , "  给出推荐裁决 accept_fix / reject / defer；"
  , "  若 accept_fix，给出修复方向（1-3 句）和优先级 P0/P1/P2。"
  , "  "
  , "  **第三部分：可疑断言（Suspicious Claims）裁决**"
  , "  对每条可疑断言，给出：推翻 / 支撑 / 延迟。"
  , "  - 推翻：说明该断言不成立，建议从文档删除原断言。"
  , "  - 支撑：给出一句话技术依据，建议加入文档 Q&A 节。"
  , "  - 延迟：需更多信息，暂不裁决。"
  , "  "
  , "  **第四部分：Q&A 条目反馈**"
  , "  对「冗余」条目确认可删；对「依然不足」条目给出更好的回答建议。"
  , "  "
  , "  **最后输出完整修改清单**，格式："
  , "  `[P0] <修复方向>` | `[推翻] SC<N>: 建议删除` | `[支撑] SC<N>: 建议加入 Q&A: <理由>` | `[Q&A 冗余] QA<N>` | `[Q&A 更新] QA<N>: <新回答>`"
  , "round1_task: |"
  , "  对新 issues、可疑断言、Q&A 反馈逐条给出立场："
  , "  - issues：[编号] accept_fix / reject / defer + 理由（1-3 句）"
  , "  - 可疑断言：[SC编号] 推翻 / 支撑 / 延迟 + 具体依据"
  , "  - Q&A 冗余：确认可删或给出保留理由"
  , "  - Q&A 不足：给出更好的回答"
  , "  若对旧裁决有异议，另起「对旧裁决的异议」节逐条说明。"
  , "middle_task: |"
  , "  **对旧裁决的不服**（若有）：明确声明「不服 [条目引用]」，引用原文，给出反对理由。"
  , "  **对本轮其他辩手裁定的回应**：引用原文，攻击判断有误之处；无异议的简单确认。"
  , "final_task: |"
  , "  给出最终裁定立场，格式同第一轮。明确说明哪些条目改变了立场及原因。"
  , "constraints: |"
  , "  - 每条发言必须直接回应至少一个具体条目（issues、SC 或 QA）"
  , "  - 修复建议必须可落到设计文档的具体位置"
  , "  - 提「不服」时必须引用被反对裁决的原文"
  , "  - 不重复讨论无异议的旧裁决，除非有新论据"
  , "---"
  , ""
  , "# 本轮裁决任务"
  , ""
  , "目标：新 issues + 可疑断言 + Q&A 反馈逐条裁决；对旧裁决有异议可提不服。"
  , ""
  , "## 一、上一轮裁决（可提不服）"
  , ""
  , oldDecisions
  , ""
  , "## 二、当前设计文档（rewrite 后，以此为准）"
  , ""
  , design
  , ""
  , "## 三、待裁决清单（issues + 可疑断言 + Q&A 反馈）"
  , ""
  , newIssues
  ]

runDebateTool :: [String] -> AppM T.Text
runDebateTool args = do
  logInfo $ "  $ python3 -m debate_tool " <> T.pack (unwords args)
  result <- liftIO $ try @SomeException $ readProcessWithExitCode "python3" ("-m" : "debate_tool" : args) ""
  decodeProcessResult debateToolErrPrefix debateToolExitPrefix result

debateToolErrPrefix :: T.Text
debateToolErrPrefix = "debate-tool subprocess error: "

debateToolExitPrefix :: T.Text
debateToolExitPrefix = "debate-tool exited "

decodeProcessResult :: T.Text -> T.Text -> Either SomeException (ExitCode, String, String) -> AppM T.Text
decodeProcessResult errPfx _ (Left ex)                      = throwError $ UserError $ errPfx <> T.pack (show ex)
decodeProcessResult _      _ (Right (ExitSuccess,   out, _)) = pure (T.pack out)
decodeProcessResult _      pfx (Right (ExitFailure n, out, err)) =
  throwError $ UserError $ pfx <> T.pack (show n) <> "\n" <> T.pack err <> "\n" <> T.pack out

runTopic :: FilePath -> FilePath -> AppM T.Text
runTopic topicFile logPath = do
  logEvent (DebateToolRun topicFile)
  let summaryPath = logPath <> ".summary.md"
  _ <- runDebateTool ["run", topicFile, "--output", logPath, "--output-summary", summaryPath]
  readSummaryFile summaryPath

resumeForRulings :: FilePath -> RewriteGuide -> Design -> T.Text -> AppM T.Text
resumeForRulings logFile oldDecisions design newIssues = do
  logEvent (DebateToolResume logFile)
  let topic = buildRulingsTopic oldDecisions design newIssues
  let summaryPath = resumeSummaryPath logFile
  result <- liftIO $ try @SomeException $ runResumeWithTopic logFile topic summaryPath
  _ <- decodeProcessResult resumeErrPrefix resumeExitPrefix result
  readSummaryFile summaryPath

resumeSummaryPath :: FilePath -> FilePath
resumeSummaryPath logFile = logFile <> ".resume_summary.md"

resumeErrPrefix :: T.Text
resumeErrPrefix = "debate-tool resume subprocess error: "

resumeExitPrefix :: T.Text
resumeExitPrefix = "debate-tool resume exited "

runResumeWithTopic :: FilePath -> T.Text -> FilePath -> IO (ExitCode, String, String)
runResumeWithTopic logFile topic summaryPath =
  withSystemTempFile "ruling_topic.md" $ \tmpPath h -> do
    hClose h
    TIO.writeFile tmpPath topic
    readProcessWithExitCode "python3"
      ["-m", "debate_tool", "resume", logFile, tmpPath, "--output-summary", summaryPath] ""

compactLog :: FilePath -> AppM ()
compactLog logFile = do
  logEvent (DebateToolCompact logFile)
  _ <- runDebateTool ["compact", logFile, "--message", compactRefineMsg]
  logInfo $ "  Compact complete: " <> T.pack logFile

readSummaryFile :: FilePath -> AppM T.Text
readSummaryFile path = do
  result <- liftIO $ try @SomeException (TIO.readFile path)
  either (throwSummaryReadError path) pure result

throwSummaryReadError :: FilePath -> SomeException -> AppM a
throwSummaryReadError path ex = throwError $ FileReadError path (T.pack (show ex))
