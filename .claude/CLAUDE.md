# debate-tool

This is the debate-tool project — a multi-model debate framework.

## Key Files

- `debate_tool/__main__.py` — Unified CLI router (subcommands: `run`, `build`, `stance`)
- `debate_tool/runner.py` — Debate engine. Usage: `debate-tool run <topic.md> [--rounds N] [--dry-run] [--cross-exam [N]] [--early-stop] [--cot[=LENGTH]]`
- `debate_tool/wizard.py` — TUI wizard (14-step curses state machine)
- `debate_tool/core.py` — Defaults, constants, mode presets, convergence check, YAML generation
- `debate_tool/stance.py` — LLM-powered debater stance recommendation
- `template.md` — Topic file template with all fields documented
- `pyproject.toml` — Package config with `[cli]`, `[web]`, `[all]` extras
- `.claude/commands/debate.md` — Claude Code `/debate` skill (source)

## Architecture

1. Topic files use YAML front-matter (between `---`) + Markdown body
2. `debate-tool run` (or `python -m debate_tool run`) parses the topic, runs N rounds with all debaters in parallel, then calls judge
3. `--cross-exam [N]` adds cross-examination after N rounds (default 1; -1=every round)
4. `--early-stop` enables convergence detection (trigram Jaccard) to skip remaining rounds
5. `--cot[=LENGTH]` enables two-stage thinking (CoT) for debaters; thinking is logged with a 🧠 tag and excluded from other debaters' context
6. `debate-tool build` launches wizard (web default, `--cli` for TUI)
7. Output: `{stem}_debate_log.md` + `{stem}_debate_summary.md`
8. API priority: per-debater config > topic-level config > env vars (`DEBATE_BASE_URL`, `DEBATE_API_KEY`)

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
