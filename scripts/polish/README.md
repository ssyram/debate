# Polish

Haskell 驱动的设计细粒度 Check 与迭代打磨流水线。

## 概述

四阶段 Check（命题抽取 → 矛盾/遗漏检测 → 交叉覆盖矩阵 → 总结）+ 多轮迭代打磨循环。每一步的中间产物立即落盘，崩溃不丢工作。

## 前置条件

- GHC 9.6+ 和 cabal 3.12+（通过 [ghcup](https://www.haskell.org/ghcup/) 安装）
- `DEBATE_BASE_URL` 和 `DEBATE_API_KEY` 两个环境变量，可通过以下任意方式提供：
  - 直接 export 到 shell 环境
  - 写入 `.local/.env` 文件（脚本默认自动加载）
  - 通过 `--env FILE` 指定其他 `.env` 文件路径

脚本自动将 `~/.ghcup/bin` 注入 PATH，源文件有变动时自动重新编译。

## hs_check.py

对设计文档执行细粒度四阶段 Check。

### 用法

```bash
python3 scripts/polish/hs_check.py <input.md> [选项]
```

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--output DIR` | 输出目录 | `<input>_check/` |
| `--model MODEL` | LLM 模型名 | `gpt-5.4-nano` |
| `--env FILE` | 额外加载的 `.env` 文件（已有环境变量则无需此项） | `.local/.env` |

### 输出文件

```
<output>/
├── check_report.md          # 完整四阶段报告
├── issues.md                # ★ 仅含需决策的问题点，按严重程度排名（Critical→Low）
├── phase1_propositions.json
├── phase2_issues.json
├── phase3_matrix.json
└── phase4_summary.json
```

> `issues.md` 是 polish 流程的实际输入，只含矛盾、遗漏、矩阵空洞，不含命题列表等参考内容。

## hs_polish.py

多轮迭代打磨，结合 Check、Debate、Rewrite 三阶段循环。

### 用法

```bash
python3 scripts/polish/hs_polish.py <input.md> [选项]
```

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--design FILE` | 预定义设计文件（跳过初始设计生成） | — |
| `--decisions FILE` | 预定义决策/指引文件（跳过初始 Check+Debate） | — |
| `--output-dir DIR` | 输出工作日志目录 | `<input>_polish/` |
| `--model MODEL` | LLM 模型名 | `gpt-5.4-nano` |
| `--max-polish-rounds N` | 外层 Polish 循环上限 | `3` |
| `--max-rewrite-rounds N` | 内层 Rewrite 循环上限 | `2` |
| `--env FILE` | 额外加载的 `.env` 文件（已有环境变量则无需此项） | `.local/.env` |

### 输出目录结构

```
<output>/
├── initial_design.md               # 初始设计
├── initial_check/                  # 初始 Check 产物
│   ├── check_report.md
│   ├── issues.md                   # ★ Debate/Merge 的输入
│   └── phase{1..4}_*.json
├── initial_debate.md               # 初始 Debate 决策
├── initial_decisions.md            # 进入第一轮的决策
├── polish_round_1/
│   ├── input_design.md             # 本轮输入设计
│   ├── input_decisions.md          # 本轮输入决策
│   ├── rewrite_1_1.md              # 第 1 轮第 1 次 Rewrite
│   ├── check_1_1/                  # 对应 Check 产物
│   │   ├── check_report.md
│   │   ├── issues.md
│   │   └── phase{1..4}_*.json
│   ├── merge_1_1.md                # Merge 输出的新指引
│   ├── design_after_rewrite.md     # 本轮 Rewrite 阶段最终设计
│   ├── check_after_rewrite.md      # 对应 Check 报告
│   └── debate_decisions.md         # 本轮 Debate 输出（未通过 Check 时）
├── polish_round_2/
│   └── ...
└── final_design.md                 # 最终打磨结果
```

## debate_polish_legacy.py

旧版 Python 打磨脚本，已被 `hs_check.py` / `hs_polish.py` 取代，仅供参考。

## Haskell 项目

源码位于 `haskell-polish/`，手动构建：

```bash
cd scripts/polish/haskell-polish && cabal build all
```

---

## 编码规范

本项目的 Haskell 编码风格以 `.local/psudo-polish.hs` 为精神参照，核心原则如下。

### 一、函数长度上限：6 行

除以下例外外，**所有函数体不超过 6 行**：
- `Prompt.hs` 中的提示词字符串构造（本质是模板，不是逻辑）
- `Log.hs` 中的 `colorize` 模式匹配（穷举事件类型，列举即文档）
- `CheckPipeline.hs` 中的渲染函数（`renderCheckReport` 等，格式化逻辑本质上是声明式列表）

**不符合的处理方式：** 提取顶层辅助函数，不在 `where` 中嵌套新逻辑块。

```haskell
-- ✗ 太长
runPolish = do
  outDir <- asks cfgOutputDir
  ensureDir outDir
  logEvent StartPolish
  design <- runOrLoadDesign
  decisions <- runOrLoadDecisions design
  writeFileText (outDir </> "initial_design.md") design
  writeFileText (outDir </> "initial_decisions.md") decisions
  polishLoop 1 design decisions

-- ✓ 拆分后
runPolish = do
  prepareOutputDir
  logEvent StartPolish
  pair <- loadInitialInputs
  writeInitialArtifactsFor pair
  uncurry (polishLoop 1) pair

prepareOutputDir :: AppM ()
prepareOutputDir = asks cfgOutputDir >>= ensureDir

loadInitialInputs :: AppM (Design, RewriteGuide)
loadInitialInputs = (,) <$> runOrLoadDesign <*> (runOrLoadDesign >>= runOrLoadDecisions)
```

### 二、不用 `where` 引入新逻辑块

`where` 可以用于**给已有子表达式命名**（一行别名），但不应在其中定义有实质逻辑的多行辅助函数——那会引入额外缩进层级，破坏可读性。

```haskell
-- ✗ where 里面有多行逻辑
toRewriteProgress newDesign newCheck mergeResult =
  if noNewGuide guide then finishRewriteEarly newDesign newCheck
                      else continueRewrite newDesign newCheck mergeResult
  where
    guide = Llm.mrNewGuide mergeResult  -- 这个 OK，只是命名

-- ✓ 提成顶层
mergeGuide :: Llm.MergeResult -> RewriteGuide
mergeGuide = Llm.mrNewGuide

toRewriteProgress newDesign newCheck mergeResult =
  if noNewGuide (mergeGuide mergeResult)
    then finishRewriteEarly newDesign newCheck
    else continueRewrite newDesign newCheck mergeResult
```

### 三、循环用 `forLoop` / `forM_`，不用尾递归

明确将"迭代"和"递归"区分开。循环语义用 `forLoop`（`foldM` 的别名）或 `forM_` 表达，尾递归只用于"直到满足条件才结束"的逻辑（如 `polishLoop`）。

```haskell
-- ✗ 看起来像普通递归，但语义是固定次数的循环
go design guide 0 = ...
go design guide n = do
  newDesign <- Llm.rewrite design guide
  go newDesign guide (n - 1)

-- ✓ 明确是循环
runRewriteRounds polishRound progress = do
  outDir <- asks cfgOutputDir
  maxRounds <- asks cfgMaxRewriteRounds
  forLoop progress [1 .. maxRounds] (rewriteStep outDir polishRound)
```

### 四、第一行 log，后五行逻辑

有副作用的业务函数读起来应该是：**第一行记录当前阶段，接下来 ≤5 行完成工作**。这样扫一眼就知道函数在做什么阶段的事。

```haskell
-- ✓ 标准模式
resolveIssues design = do
  outDir <- asks cfgOutputDir
  logFile <- asks cfgLogFile
  issuesText <- loadIssuesText design outDir
  writeInitialIssues outDir issuesText
  runInitialResume logFile outDir design issuesText
```

### 五、抽象相似逻辑

两段结构相似的代码 → 提取共同抽象，差异作为参数传入。

```haskell
-- ✗ 重复结构
readDesignFile file  = logInfo ("Loading design from file: " <> T.pack file) >> readFileText file
readDecisionFile file = logInfo ("Loading decisions from file: " <> T.pack file) >> readFileText file
readIssuesFile file  = logInfo ("Loading issues from file: " <> T.pack file) >> readFileText file

-- ✓ 如果差别只是 log 文本，可以保留——此处差异足够小，可接受；
--   若参数更多，则抽成 loadFileWithLog :: Text -> FilePath -> AppM Text
loadFileWithLog :: Text -> FilePath -> AppM Text
loadFileWithLog label file = logInfo (label <> T.pack file) >> readFileText file
```

### 六、语言扩展

始终在文件顶部启用以下扩展，以支持上述风格：

```haskell
{-# LANGUAGE MultiWayIf  #-}   -- 多路条件，替代嵌套 if-else
{-# LANGUAGE LambdaCase  #-}   -- \case，替代 \x -> case x of
```

`MultiWayIf` 让多分支条件读起来和 `guard` 一样清晰：

```haskell
runOrLoadDesign = do
  predefinedFile <- asks cfgDesignFile
  logFile        <- asks cfgLogFile
  topicFile      <- asks cfgTopicFile
  if | Just f <- predefinedFile -> readDesignFile f
     | Just f <- logFile        -> loadDesignFromLog f
     | Just f <- topicFile      -> runTopicMode f
     | otherwise                -> throwError CannotFindDesign
```
