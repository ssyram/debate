# debate-tool

This is the debate-tool project — a multi-model debate framework.

## Key Files

- `debate_tool/__main__.py` — Unified CLI router (subcommands: `run`, `build`)
- `debate_tool/runner.py` — Debate engine. Usage: `debate-tool run <topic.md> [--rounds N] [--dry-run] [--cross-exam [N]] [--early-stop] [--cot[=LENGTH]] [--output LOG] [--output-summary SUMMARY] [--no-judge]` / `debate-tool resume <log.json> [resume_topic.md] [--rounds N] [--message MSG] [--guide PROMPT] [--cross-exam [N]] [--cot [N]] [--force] [--no-judge] [--output-summary SUMMARY]`
- `debate_tool/wizard.py` — TUI wizard (14-step curses state machine)
- `debate_tool/core.py` — Defaults, constants, mode presets, convergence check, YAML generation
- `template.md` — Topic file template with all fields documented
- `scripts/opencode_proxy.py` — OpenCode session 代理，把 OpenCode session 包装成 OpenAI-compatible 辩手后端
- `scripts/migrate_v1_to_v2.py` — v1→v2 日志迁移脚本
- `test_edo.md` — 测试用 topic 文件（江户幕府辩题，gpt-4o-mini）
- `pyproject.toml` — Package config with `[cli]`, `[web]`, `[all]` extras
- `.claude/commands/debate.md` — Claude Code `/debate` skill (source)

## Architecture

1. Topic files use YAML front-matter (between `---`) + Markdown body
2. `debate-tool run` (or `python -m debate_tool run`) parses the topic, runs N rounds with all debaters in parallel, then calls judge
3. `--cross-exam [N]` adds cross-examination after N rounds (default 1; -1=every round)
4. `--early-stop` enables convergence detection (trigram Jaccard) to skip remaining rounds
5. `--cot[=LENGTH]` enables two-stage thinking (CoT) for debaters; thinking is logged with a 🧠 tag and excluded from other debaters' context
6. `debate-tool build` launches wizard (web default, `--cli` for TUI)
7. Output: `{stem}_debate_log.json` (v2 Log Schema, self-contained) + `{stem}_debate_summary.md`
8. API priority: per-debater config > topic-level config > env vars (`DEBATE_BASE_URL`, `DEBATE_API_KEY`)
9. `resume --guide PROMPT` — lightweight CLI-only ephemeral task override (not persisted to log); replaces `middle_task` for all rounds of this resume run. resume has no `round1_task` by design: use `--guide --rounds 1` to target only the first resume round, then resume again without `--guide` for subsequent rounds. Fine-grained per-round control belongs in resume topic YAML (`middle_task`, `final_task`).

## Development Notes

- Python project using httpx, pyyaml, rich, click, flask
- Minimum 2 debaters required per debate
- The `/debate` skill is installed globally via `install-skills.sh`
- `install.py` must use only Python standard library (runs before dependencies)
- Root-level `debate.py` and `new_debate.py` have been deleted; all logic lives in `debate_tool/` package
- Always use `python3` (not `python`) to avoid Python 2.7 on some systems
- Convergence check uses pure-Python trigram Jaccard (no external deps), supports CJK and Latin
- API config: topic files must use `${DEBATE_BASE_URL}` / `${DEBATE_API_KEY}` placeholders for base_url and api_key; real values are injected via environment variables or `.env`; hard-coding is not allowed
- Commits: Never commit on your own initiative; only commit when the user explicitly instructs it

## Compact Design Principles

Compact（上下文压缩）的设计精神：

- **理想目标**：compact 后辩手表现应等同甚至超越不压缩——去掉噪音后注意力更集中。好的 compact 是「重组信息使其比原始对话更高效传达辩论状态」，不只是「token 限制下尽量少丢」
- **LLM 摘要**：compact 通过 LLM 调用生成结构化摘要，不做纯文本截断
- **核心维度**（参考框架）：思路延续（辩手能接上最新线索继续推进）+ 不回滚打转（不重新提出已否决观点）
- **输出应体现**：辩论演进轨迹、最新决策和立场、被抛弃路径及理由

## Debate Standard Workflow

**辩论完整标准流程（Debate Standard Workflow）**：

1. **搜集信息**：收集足够的背景信息（已有设计稿、相关 summary、前置决策）
2. **写 topic**：写 topic 文件，必须包含：完整系统背景（让辩手无需读其他文件）+ 具体决策点说明 + 开放性问题框架，API 凭证使用 `${DEBATE_BASE_URL}` / `${DEBATE_API_KEY}` 占位符
3. **自洽性检查**：只看那一份 topic 文档，判断背景是否完整自洽；如有问题先读相关文件再补充修复
4. **运行辩论**：从 `.local/test_kimi_v7.md` 注入真实凭证，运行 `python3 -m debate_tool run <topic.md> --rounds N --cross-exam`，运行后立刻还原占位符
5. **查看遗留问题**：读取 summary，评估是否有未解决的障碍点或新矛盾
6. **后续处理**：
   - 有新话题 → 重新走完整流程（步骤 1 起）
   - 续跑现有辩论 → 写 message + 运行 → 综合 → 评估 → 循环

## OpenCode Proxy

`scripts/opencode_proxy.py` 让本地 OpenCode session 充当辩手后端，实现 OpenAI-compatible 接口。

### 架构要点

- **一进程一 session**：每个 proxy 进程管理一个 OpenCode session，不同辩手使用不同端口
- **增量上下文（sent_count）**：proxy 跟踪 `_sent_count`，每次只把 `messages[sent_count:]` 的 delta 发给 OpenCode，避免重复传输
- **消息格式化**：system → `system` 字段；user → 正文；assistant（历史）→ 前缀 `[你之前的发言]\n`；多段用 `\n\n---\n\n` 分隔
- **完成检测**：POST 后 sleep 2s，然后轮询 `GET /session/status`；status==`idle` 且消息数增加时视为完成；超时则报 500
- **懒创建 session**：第一次 POST 请求时才调用 `POST /session`；`GET /health` 不触发创建
- **标准库限制**：只用 `urllib`, `http.server`, `json`, `threading`, `argparse`, `time`, `uuid`，不引入外部依赖

### 启动示例

```bash
# 辩手 A（端口 8081）
python3 scripts/opencode_proxy.py \
    --port 8081 \
    --opencode-url http://localhost:3000 \
    --provider-id yunwu \
    --model-id gpt-5.4 \
    --debater-name "正方辩手" \
    --read-only

# 辩手 B（端口 8082）
python3 scripts/opencode_proxy.py \
    --port 8082 \
    --opencode-url http://localhost:3000 \
    --provider-id yunwu \
    --model-id claude-3-7-sonnet \
    --debater-name "反方辩手"
```

### Topic 文件配置

runner.py 的 `call_llm` 直接 POST 到 `base_url` 字段（不自动追加路径），因此 **`base_url` 必须是完整 URL，含路径**：

```yaml
debaters:
  - name: 正方辩手
    model: yunwu/gpt-5.4
    base_url: http://localhost:8081/v1/chat/completions
    api_key: dummy
  - name: 反方辩手
    model: yunwu/claude-3-7-sonnet
    base_url: http://localhost:8082/v1/chat/completions
    api_key: dummy
```

proxy 同时监听 `/chat/completions` 和 `/v1/chat/completions`（两路径等价）。

### model 字段解析规则

- `"providerID/modelID"`（如 `yunwu/gpt-5.4`）→ 自动拆分
- 否则 → CLI `--provider-id` 作为 provider，`model` 字段值作为 modelID

### CLI 参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--port` | 8081 | proxy 监听端口 |
| `--opencode-url` | http://localhost:3000 | OpenCode serve 地址 |
| `--provider-id` | yunwu | 默认 provider |
| `--model-id` | (必填) | 默认 model |
| `--debater-name` | debater | session title |
| `--read-only` | false | 禁止写文件工具 |
| `--no-web` | — | 禁用 web 搜索 |
| `--cwd` | 当前目录 | session 工作目录 |
| `--timeout` | 300s | 等待回复超时 |
| `--poll-interval` | 2s | 轮询间隔 |

## Debate Topic Design Philosophy

辩题设计的核心原则：**客观描述现象，不假定问题**。

### 标准结构

一个好的辩题应当按照以下顺序引导讨论，**并在裁判（judge）的 style 或 topic 正文中明确要求裁判按此顺序逐一回答**：

1. **现象是什么？**（客观描述观察到的事实，不带预设结论）
2. **现象是不是真问题？**（评估：这个现象值得关注吗？会有危害吗？）
3. **真问题的本质分解**（如果是真问题：分解成更具体、更本质的若干子问题，并论证"问题的本质其实是这些子问题"）
4. **如何解决这些问题？**（针对每个子问题提出方案）

### 关键约束

- **不要在 topic 背景里假定问题已经存在**：背景只描述现象和上下文，让辩手自己判断是否成立
- **裁判必须按顺序回答**：裁判的最终裁定应覆盖以上全部步骤，不能跳过"是否真问题"直接跳到"解决方案"
- **问题分解是核心产出**：第 3 步的子问题清单是辩论最有价值的输出——每个子问题可以单独开一场新辩论，实现递归深入

### 好处

- 避免"伪问题辩论"：辩论结束后发现根本不是真问题
- 产出可操作的子问题列表，每个都可以作为独立辩题
- 裁判的结构化回答使辩论结果更容易被后续利用

### 反例（不应该做的）

❌ 背景直接写："compact 机制的修正调用存在 X 问题，需要改进"
✅ 应改为："观察到以下现象：[客观描述 cos 值、修正调用、最终结果]，这是什么原因导致的？是否是设计缺陷？"
