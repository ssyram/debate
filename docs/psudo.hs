{-# LANGUAGE MultiWayIf #-}

-- ═══════════════════════════════════════════════════════════════════════════════
--  debate-tool 核心逻辑规范（pseudo-Haskell）
--  规则: 函数体 ≤5 行（promptFor 除外）
--  所有文本生成集中在 promptFor; 控制流与提示词完全解耦
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── Types ───────────────────────────────────────────────────────────────────

data Tag     = Speech | Thinking | XExam | Human | Compact | Summary deriving Eq
data Entry   = Entry { eSeq :: Int, eName :: String, eContent :: String, eTag :: Tag }
data Debater = Debater { dName, dModel, dStyle, dUrl, dKey :: String }
data Judge   = Judge { jName, jModel :: String, jInstr :: String, jMaxTok :: Int }
data XPayload = XPayload { xTarget, xReason :: String, xQs :: [String] }
data LlmErr  = TokenLimit | OtherErr String
data EarlyStop = EarlyStop deriving (Show, Typeable)
instance Exception EarlyStop

data Config = Config
  { cDebaters :: [Debater], cJudge :: Judge
  , cTopic, cTitle, cConstraints :: String
  , cRounds, cTimeout, cMaxReply :: Int
  , cR1Task, cMidTask, cFinTask, cJudgeInstr :: String
  , cXExamSet :: Set Int, cEarlyThresh :: Double
  , cCotLen :: Maybe Int, cCompactThresh :: Int }

data Log = Log { lEntries :: IORef [Entry], lPath :: FilePath, lTitle :: String }
data Env = Env { eCfg :: Config, eLog :: Log, eRnd :: Int, eChallenged :: Maybe (Set String) }
type D   = ReaderT Env IO

-- ── Prompt ADT ──────────────────────────────────────────────────────────────

data Prompt
  = PSys     Debater Int String String (Maybe String)  -- debater, round, task, constraints, stance
  | PCtx     String (Maybe String)                      -- topic, history (Nothing → R1)
  | PMid     String (Maybe (Set String)) String         -- baseTask, challengedSet, myName
  | PCot     (Maybe Int)                                -- cot budget
  | PXSelSys Debater [String]                           -- questioner, opponent names
  | PXSelCtx [(String, String)]                         -- (name, speech) pairs
  | PXAskSys Debater String                             -- questioner, target name
  | PXAskCtx String String                              -- target name, target speech
  | PJSys    Judge String [Entry]                       -- judge, instructions, human entries
  | PJCtx    String                                     -- full log text

-- ── Entry points ────────────────────────────────────────────────────────────

run topicFile = do
  (cfg, log) <- (,) <$> parseTopic topicFile <*> newLog topicFile
  runReaderT (coreLoop >> judgePhase >> writeSummary) (Env cfg log 0 Nothing)

resume logFile overrides = do
  (cfg, log) <- loadLog logFile >>= patchWith overrides
  runReaderT (coreLoop >> judgePhase >> writeSummary) (Env cfg log (baseRound log) Nothing)

-- ── Core loop ───────────────────────────────────────────────────────────────

coreLoop = do
  n <- asks (cRounds . eCfg)
  catch (\EarlyStop -> pure ()) $ forM_ [1..n] $ \r -> local (setRnd r) oneRound

oneRound = do
  replies <- debaterRound
  xResult <- ifM shouldXExam (Just <$> crossExam replies) (pure Nothing)
  saveRound replies xResult
  whenM (converged replies) notifyAbort
  whenM shouldCompact doCompact

-- ── Debater round ───────────────────────────────────────────────────────────

debaterRound = asks (cDebaters . eCfg) >>= mapConcurrently oneDebater

oneDebater d = do
  sys <- sysPrompt d
  ctx <- userCtx
  callWithRetry d sys ctx

sysPrompt d = do
  task <- roundTask d; stance <- getStance (dName d); Env{eCfg=c, eRnd=r} <- ask
  pure $ promptFor (PSys d r task (cConstraints c) stance)

userCtx = do
  Env{eCfg=c, eLog=l, eRnd=r} <- ask
  pure $ promptFor (PCtx (cTopic c) (if r == 1 then Nothing else Just (history l)))

roundTask d = do
  Env{eCfg=c, eRnd=r, eChallenged=ch} <- ask
  pure $ if | r == 1         -> cR1Task c
            | r == cRounds c -> cFinTask c
            | otherwise      -> promptFor (PMid (cMidTask c) ch (dName d))

-- ── LLM call with CoT + token-limit retry ──────────────────────────────────

callWithRetry d sys ctx = do
  result <- tryLlm d sys ctx
  case result of
    Right raw       -> cotSplit d sys ctx raw
    Left TokenLimit -> doCompact >> callWithRetry d sys ctx

cotSplit d sys ctx raw = do
  cot <- asks (cCotLen . eCfg)
  case cot of { Nothing -> pure ("", raw); Just _ -> finishCot d sys ctx raw }

finishCot d sys ctx raw =
  let (th, body) = extractThinking raw
  in if null body then ("",) <$> callLlm d (stripCot sys) ctx else pure (th, body)

-- ── Cross examination ───────────────────────────────────────────────────────

crossExam latestSpeeches = do
  ds <- asks (cDebaters . eCfg)
  results <- mapConcurrently (oneXExam latestSpeeches) ds
  mapM_ saveXEntry results
  pure (foldMap (maybe mempty (singleton . xTarget) . snd) results)

oneXExam latestSpeeches =
  oneTimeFullXExam latestSpeeches <|> xExam_pickAndAsk latestSpeeches <|> xExamNoOpinion

pickTarget q sp =
  callLlm q (promptFor (PXSelSys q (others q sp))) (promptFor (PXSelCtx sp)) >>= parseTarget

askQs q t sp =
  callLlm q (promptFor (PXAskSys q t)) (promptFor (PXAskCtx t (speechOf t sp))) >>= parsePayload t

-- ── Judge ───────────────────────────────────────────────────────────────────

judgePhase = mkJudgeSys >>= judgeRetry >>= saveJudge

mkJudgeSys = do
  Env{eCfg=c, eLog=l} <- ask
  pure $ promptFor (PJSys (cJudge c) (cJudgeInstr c) (filter ((== Human) . eTag) (readEntries l)))

judgeRetry sys = do
  ctx <- promptFor . PJCtx <$> compactAll
  result <- tryJudge sys ctx
  either (\TokenLimit -> compressLog >> judgeRetry sys) pure result

-- ── Side effects ────────────────────────────────────────────────────────────

writeSummary = asks eLog >>= \l -> liftIO $ writeFile (summaryPath l) (fmtSummary l)

doCompact = asks eLog >>= \l -> runCompact l >>= \s -> appendEntry l (mkEntry "Compact" (render s) Compact)

saveRound replies xr = do
  l <- asks eLog; ds <- asks (cDebaters . eCfg)
  forM_ (zip ds replies) $ \(d, (th, body)) ->
    unless (null th) (appendEntry l (mkEntry (dName d) th Thinking))
    >> appendEntry l (mkEntry (dName d) body Speech)

saveXEntry (qName, Just p) = asks eLog >>= \l ->
  appendEntry l (mkEntry (qName <> " → " <> xTarget p) (encodeJSON p) XExam)
saveXEntry (qName, Nothing) = asks eLog >>= \l ->
  appendEntry l (mkEntry (qName <> " → (弃权)") "本轮没有意见" XExam)

saveJudge s = asks eLog >>= \l -> appendEntry l (mkEntry (jName . cJudge . eCfg $ undefined) s Summary)

-- ── Predicates ──────────────────────────────────────────────────────────────

shouldXExam   = asks (\e -> eRnd e `member` cXExamSet (eCfg e) && eRnd e < cRounds (eCfg e))
converged  rs = asks (\e -> cEarlyThresh (eCfg e) > 0 && jaccardSim (map snd rs) >= cEarlyThresh (eCfg e))
shouldCompact = asks (\e -> tokenEst (history (eLog e)) > cCompactThresh (eCfg e))
setRnd r e    = e { eRnd = r }

-- ── Helpers (留给外围实现, 每个 ≤5 行) ──────────────────────────────────────

parseTopic   :: FilePath -> IO Config                            -- YAML front-matter + Markdown body
newLog       :: FilePath -> IO Log                               -- 创建空日志
loadLog      :: FilePath -> IO (Config, Log)                     -- 加载 v2 JSON 日志
patchWith    :: Overrides -> (Config, Log) -> IO (Config, Log)   -- 应用覆盖 + 校验
baseRound    :: Log -> Int                                       -- 已有 Speech 数 / 辩手数

getStance    :: String -> D (Maybe String)     -- 从最近 compact checkpoint 提取该辩手立场
history      :: Log -> String                  -- compact 快照 + delta, 或完整日志
latestSpeeches :: D [(String, String)]         -- 最近 N 条非 Thinking 条目
compactAll   :: D String                       -- 全日志渲染为文本
compressLog  :: D ()                           -- compact 日志以便裁判重试

tryLlm  :: Debater -> String -> String -> D (Either LlmErr String)
tryJudge :: String -> String -> D (Either LlmErr String)
callLlm :: Debater -> String -> String -> D String   -- tryLlm >>= fromRight

extractThinking :: String -> (String, String)  -- 拆分 <thinking>...</thinking>
stripCot        :: String -> String            -- 去掉系统提示中的 CoT 附注

parseTarget  :: String -> D String             -- 解析 {"target": "..."}, 失败则重试
parsePayload :: String -> String -> D XPayload -- 解析 XPayload, 多级降级

readEntries  :: Log -> [Entry]                 -- readIORef . lEntries
appendEntry  :: Log -> Entry -> D ()           -- 追加 + 刷盘
mkEntry      :: String -> String -> Tag -> Entry
summaryPath  :: Log -> FilePath
fmtSummary   :: Log -> String
runCompact   :: Log -> D CompactState          -- 两阶段 compact 引擎
render       :: CompactState -> String

others   :: Debater -> [(String, a)] -> [String]  -- 排除自己的对手名单
speechOf :: String -> [(String, String)] -> String -- 按名字查发言

-- ── promptFor (全部提示词模板) ──────────────────────────────────────────────

promptFor :: Prompt -> String

promptFor (PSys d rnd task cstr mStance) = unlines $
  [ "你是「" <> dName d <> "」，风格为「" <> dStyle d <> "」。第 " <> show rnd <> " 轮。"
  , ""
  , "任务：" <> task
  ]
  ++ (if null cstr then [] else ["", "核心约束：", cstr])
  ++ maybe [] stanceBlock mStance
  where
    stanceBlock s =
      [ "", s
      , ""
      , "你收到的是辩论状态快照。「已否决路径」不得以任何变体重新提出。"
      , "你的立场描述已更新为上述「当前辩论立场」，以此为准，忽略初始立场中关于观点的陈述。"
      ]

promptFor (PCtx topic Nothing) =
  "## 辩论议题\n\n" <> topic

promptFor (PCtx topic (Just hist)) =
  "## 辩论议题\n\n" <> topic <> "\n\n## 上轮辩论内容\n\n" <> hist

promptFor (PMid _base Nothing _me) = _base

promptFor (PMid base (Just challenged) me)
  | me `member` challenged =
      "【优先任务】逐条回应你收到的每一个质询，指出对方质疑中的不当之处，"
      <> "并可修正自己的方案。每条质疑都必须回应，字数紧张时可简短作答。"
      <> "若回应已占用大量篇幅，可省略下方的推进任务。"
      <> "\n\n【推进任务（可选）】" <> base
  | otherwise =
      "本轮无人向你提出质询。如有新论点或补充可继续阐发；"
      <> "若你认为本轮无新内容可补充，可简短表示等待本轮，无需强行发言。200-400 字"

promptFor (PCot Nothing) =
  "请先在 <thinking>...</thinking> 标签内完成你的思考过程。"

promptFor (PCot (Just n)) =
  promptFor (PCot Nothing) <> " 思考内容不超过 " <> show n <> " token。"

promptFor (PXSelSys q opponents) = unlines
  [ "你是「" <> dName q <> "」（" <> dStyle q <> "），现在进入同步质询子回合。"
  , "你的任务是先选择一个要质询的对象。"
  , "【输出要求】只输出一个 JSON 对象: {\"target\": \"<被质询者姓名>\"}"
  , "【硬约束】target 必须是以下之一：" <> intercalate ", " opponents
  , "不要输出解释，不要输出长文"
  ]

promptFor (PXSelCtx speeches) =
  encodeJSON [ object ["name" .= n, "content" .= c] | (n, c) <- speeches ]

promptFor (PXAskSys q target) = unlines
  [ "你是「" <> dName q <> "」（" <> dStyle q <> "），现在进入质询环节。"
  , "你会收到一个 JSON 输入。请只基于该输入完成质询。"
  , "【输出要求】只输出 JSON:"
  , "  {\"target\": \"" <> target <> "\", \"reason\": \"...\", \"questions\": [\"...\"]}"
  , "【硬约束】"
  , "- target 必须是 " <> target <> "，不可改成其他人"
  , "- questions 长度 1~5"
  , "- 每个问题优先指向 target 本轮发言中的具体说法"
  , "- 不要输出综合方案、实施路线图、结论性长文"
  , "- 同步质询子回合：你看不到别人提出的问题，也不要回应任何别人可能对你提出的质询"
  ]

promptFor (PXAskCtx target speech) =
  encodeJSON $ object ["target" .= target, "target_speech" .= speech]

promptFor (PJSys j instr humans) = unlines $
  [ "你是辩论裁判（" <> jName j <> "），负责做出最终裁定。"
  , ""
  , if null instr then defaultJudgeInstr else instr
  , ""
  , "裁定规则："
  , "- 基于事实和数据"
  , "- 引用辩论中的关键论据"
  , "- 简洁、可操作"
  ] ++ humanBlock humans
  where
    defaultJudgeInstr = unlines
      [ "输出结构化 Summary："
      , ""
      , "## 一、各辩手表现评价（每位 2-3 句）"
      , ""
      , "## 二、逐一裁定"
      , "对每个议题给出："
      , "- **裁定**：最终方案"
      , "- **理由**：引用辩论中的关键论据"
      , "- **优先级**：P0 / P1 / P2"
      , ""
      , "## 三、完整修改清单"
      ]
    humanBlock [] = []
    humanBlock hs =
      [ ""
      , "## 四、观察者意见回应"
      , "本次辩论中有观察者注入了以下意见："
      ] ++ map (\e -> "- " <> eContent e) hs
        ++ ["请逐条说明各辩手对这些意见的吸收和回应情况。"]

promptFor (PJCtx logText) =
  "全部辩论（压缩版）：\n\n" <> logText
