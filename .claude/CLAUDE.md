# debate-tool

This is the debate-tool project — a multi-model debate framework.

## Key Files

- `debate_tool/__main__.py` — Unified CLI router (subcommands: `run`, `build`, `stance`)
- `debate_tool/runner.py` — Debate engine. Usage: `debate-tool run <topic.md> [--rounds N] [--dry-run] [--cross-exam [N]] [--early-stop]`
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
5. `debate-tool build` launches wizard (web default, `--cli` for TUI)
6. Output: `{stem}_debate_log.md` + `{stem}_debate_summary.md`
7. API priority: per-debater config > topic-level config > env vars (`DEBATE_BASE_URL`, `DEBATE_API_KEY`)

## Development Notes

- Python project using httpx, pyyaml, rich, click, flask
- Minimum 2 debaters required per debate
- The `/debate` skill is installed globally via `install-skills.sh`
- `install.py` must use only Python standard library (runs before dependencies)
- Root-level `debate.py` and `new_debate.py` have been deleted; all logic lives in `debate_tool/` package
- Always use `python3` (not `python`) to avoid Python 2.7 on some systems
- Convergence check uses pure-Python trigram Jaccard (no external deps), supports CJK and Latin
