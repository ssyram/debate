# 关键编码决策记录

本文件记录本次开发/重构过程中遇到的关键决策点与潜在分歧，供未来维护者参考。

---

## 1. `collectPhases` 中的 logging 策略

**问题**：`runPhaseN` 函数（无目录版本）与 `runPhaseWithWrite` 的 `after` 回调同时调用 `logPhaseN`，导致日志重复打印。

**决策**：让 `runPhaseN` 函数本身**不负责 logging**，logging 统一通过两条路径处理：
- `runCheckToDir` 路径：通过 `runPhaseWithWrite dir name logPhaseN action` 的 `after` 参数回调
- `runCheck`（无目录）路径：通过 `collectPhases` 末尾的 `logPhaseSummary` 一次性打印

**分歧点**：另一种方案是让 `runPhaseN` 内部 log，`runPhaseWithWrite` 传 `ignorePhaseLog`，但这样无目录路径也能工作，不需要单独维护 `logPhaseSummary`。最终选择"职责分离"：`runPhaseN` 只负责执行，log 由外部调用者决定。

---

## 2. `dist-newstyle` 不应提交，但 `.gitignore` 缺少此条目

**问题**：`dist-newstyle/` 是 GHC/cabal 的编译产物目录，体积大（包含 `.o`、`.dyn_o`、二进制文件），不应进入版本控制。但原有 `.gitignore` 未覆盖它。

**决策**：在 `.gitignore` 中添加 `scripts/polish/haskell-polish/dist-newstyle/`。

**原则**：`dist-newstyle` 性质类似 `node_modules` 或 `__pycache__`：可完全由 `cabal build all` 重新生成，不含任何需要版本化的源码或配置，完全属于构建产物。

---

## 3. `proxy_workspace/.opencode/opencode.json` 中的 `yunwu.ai` URL

**问题**：`scripts/proxy/proxy_workspace/.opencode/opencode.json` 中含有 `"baseURL": "https://yunwu.ai/v1"`，这是一个具体的 API 服务域名，是否算敏感信息？

**决策**：保留提交。理由：
- 该文件中**不含 API Key**，只有 base URL。
- Base URL 本质是一个服务地址，类似 `https://api.openai.com/v1`，是公开配置，不是凭证。
- API Key 存储在 `.local/.env`，已被 `.gitignore` 排除。

**风险说明**：如果不希望在公开仓库中披露所使用的 API 服务提供商，可替换为占位符 `https://YOUR_API_BASE_URL/v1`。

---

## 4. `DEFAULT_ENV` 路径的定位策略

**问题**：`hs_check.py` / `hs_polish.py` 原来计算 `DEFAULT_ENV = SCRIPT_DIR.parent / ".local" / ".env"`，指向 `scripts/.local/.env`，但实际文件在 `debate/.local/.env`（仓库根）。

**决策**：改为 `REPO_ROOT = SCRIPT_DIR.parent.parent`（`scripts/polish` → `scripts` → `debate`），`DEFAULT_ENV = REPO_ROOT / ".local" / ".env"`。

**分歧点**：可以通过环境变量 `DEBATE_ENV_FILE` 完全外化，或通过 `--env` 参数指定。但默认路径应该指向仓库根的 `.local/.env`，这是用户最自然的放置位置（与 `README` 中说明一致）。

---

## 5. `where` 的使用边界

**问题**：Style guide 说"不用 `where` 引入新逻辑块"，但在 `Llm.hs` 中 `decodeChatJson` 和 `stripCodeFences` 各有一个单行 `where` 别名：
```haskell
decodeChatJson raw =
  either throwChatDecodeError pure (eitherDecodeStrict (encodeUtf8 (stripCodeFences raw)))
  where throwChatDecodeError err = throwError $ JsonDecodeError (chatDecodeMessage err raw)

stripCodeFences t =
  if hasOpeningFence strippedText then stripFenceBody strippedText else strippedText
  where strippedText = T.strip t
```

**决策**：保留这两处 `where`。理由：
- `throwChatDecodeError` 是一个捕获局部变量 `raw` 的闭包，提取为顶层函数需要额外参数，反而降低可读性。
- `strippedText = T.strip t` 是单纯的表达式命名，无逻辑，属于"一行别名"类别，符合规范中的例外。

---

## 6. `isJust` 的本地定义 vs 导入

**问题**：`app/Polish.hs` 中定义了本地 `isJust :: Maybe a -> Bool`，与 `Data.Maybe.isJust` 重名但未导入（不冲突）。

**决策**：保留本地定义。理由：未引入 `Data.Maybe` 导入，定义在局部，不影响其他模块。若觉得不规范，可替换为 `import Data.Maybe (isJust)` 并删除本地定义。这是无害选择，未作进一步修改。

---

## 7. `logPhase1 "" props` 中传入空字符串

**问题**：`logPhaseSummary` 调用 `logPhase1 "" props`，第一个参数是 JSON 字符串，但传入 `""`。`logPhaseN` 函数签名是 `logPhaseN :: Text -> PhaseResult -> AppM ()`，第一个参数实际上被所有 logPhase 函数忽略（`logPhase1 _ props = ...`），所以传空字符串是合法的。

**决策**：保持现状。若未来需要在 log 中打印 JSON 内容，需要修改此处并传入实际 JSON 文本。

---

## 8. 重写后 issues 数量从 4 增加到 7

**观察**：第一轮 rewrite 后 check 发现的 issues 从 4 个增加到 7 个，同时可疑断言从 10 降到 7，Q&A feedback 从 0 增加到 3。

**解读**：这是预期行为。重写使设计更具体、命题更多（43 条 vs 65 条是因为文档更聚焦），但更具体的描述也暴露了更多的局部不一致。同时，Q&A 节的出现说明 SC 被部分处理。merge 步骤对这 7 个新 issues 判断"均超出当前裁决范围"（no new guide），触发下一轮 debate 裁决——这是正确的行为。

---

## 9. 被删除的旧文件需要 git rm

**问题**：`scripts/` 根目录下的旧文件（`debate_polish.py`, `opencode_proxy.py` 等）在 git 中标记为 `D`（deleted），同时这些文件已在 `scripts/tools/` 和 `scripts/proxy/` 目录中重新出现（untracked）。

**决策**：在 commit 中同时 `git add` 新路径 + `git rm` 旧路径（通过 `git add -A` 或单独操作）。这是一次"移动重组"，而非删除后重写。

**说明**：`tests/test_runner_json_logs.py` 也是类似情况——旧位置 `tests/` 已删除，测试套件现在位于 `test/`（已在 git 中）。此文件真正被删除，不再有对应的新文件。
