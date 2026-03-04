# debate-tool

多模型辩论框架，支持 N(>= 2) 个辩手并行多轮辩论，最终由裁判模型给出裁决。

提供两种使用界面：
- **Web 向导** — 响应式单页应用，实时预览，一键提交生成
- **命令行 TUI 向导** — 双栏 Curses 界面，14 步生成辩论配置文件

## 1. 安装

**依赖：Python 3.11+**

### 推荐方式：pip install

```bash
git clone <repo-url>
cd debate-tool
pip install ".[all]"       # 全量安装所有功能
```

按需安装：

```bash
pip install .              # 仅核心（httpx, pyyaml）→ 可运行辩论
pip install ".[cli]"       # 核心 + CLI（rich, click）→ TUI 向导
pip install ".[web]"       # 核心 + Web（flask）→ Web 向导
pip install ".[all]"       # 全部功能
```

### 安装脚本（替代方式）

```bash
python install.py          # 交互式菜单
python install.py --all    # 全量安装所有依赖
python install.py --skill  # 安装 Claude Code /debate 命令
python install.py --env    # 设置 DEBATE_TOOL_DIR 环境变量
```

> **Windows 用户**：TUI 向导依赖 `curses`（macOS/Linux 内置）。Windows 上需额外安装 `windows-curses`，`install.py` 会自动处理。若 TUI 不可用，可使用 Web 向导作为替代。

## 2. 快速开始

### 生成辩论配置

```bash
# Web 向导（推荐，默认）
debate-tool build

# TUI 向导
debate-tool build --cli

# 也可直接用模板
cp template.md my_topic.md
# 编辑 my_topic.md，填写 YAML 元数据和话题内容
```

### 运行辩论

```bash
# 基本运行
debate-tool run my_topic.md

# 覆盖轮数
debate-tool run my_topic.md --rounds 5

# 试运行（仅校验配置，不调用 API）
debate-tool run my_topic.md --dry-run
```

### 生成辩手立场

```bash
debate-tool stance my_topic.md
debate-tool stance my_topic.md --num 5 --format yaml
```

> 所有命令也可通过 `python -m debate_tool <command>` 调用。

**输出文件**：
- `{stem}_debate_log.md` — 完整辩论记录（每轮每位辩手发言）
- `{stem}_debate_summary.md` — 裁判结构化裁决

## 3. API 配置

优先级（从高到低）：

1. 角色级配置（`debaters[].base_url` / `debaters[].api_key`，以及 `judge.base_url` / `judge.api_key`）
2. 话题文件全局 `base_url` / `api_key`
3. 环境变量 `DEBATE_BASE_URL` / `DEBATE_API_KEY`

建议将 API 密钥配置为环境变量，避免写入版本控制：

```bash
export DEBATE_API_KEY=your_api_key
export DEBATE_BASE_URL=your_api_base_url
```

## 4. YAML 字段参考

话题文件以 `---` 包裹的 YAML 块开头：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `title` | string | 文件名 | 辩论标题 |
| `rounds` | int | 3 | 辩论轮数 |
| `timeout` | int | 300 | 单次 API 超时（秒） |
| `max_tokens` | int | 6000 | 辩手单次输出 token 上限 |
| `base_url` | string | env/fallback | OpenAI 兼容 API 端点 |
| `api_key` | string | env/fallback | API 密钥 |
| `debaters` | list | 3 个默认辩手 | 每项含 `name` / `model` / `style`，可选 `base_url` / `api_key` |
| `judge` | object | claude-opus-4-6 | 含 `model` / `name` / `max_tokens`，可选 `base_url` / `api_key` |
| `constraints` | string | `""` | 约束条件，注入每位辩手的 system prompt |
| `round1_task` | string | 内置默认 | 第一轮任务说明 |
| `middle_task` | string | 内置默认 | 中间轮任务说明 |
| `final_task` | string | 内置默认 | 最后一轮任务说明 |
| `judge_instructions` | string | 内置默认 | 裁判评判指令 |

**示例**：

```yaml
---
title: "AI 是否应该拥有投票权"
rounds: 3
debaters:
  - name: 务实工程派
    model: gpt-5.2
    style: 注重可行性与工程实现，以数据和案例为据
  - name: 创新挑战派
    model: kimi-k2.5
    style: 挑战现有假设，探索前沿可能性
  - name: 严谨分析派
    model: claude-sonnet-4-6
    style: 逻辑严谨，系统性分析各方论点
judge:
  model: claude-opus-4-6
  name: 首席裁判
  max_tokens: 8000
---

在此输入辩论议题的详细背景与讨论要点...
```

## 5. 立场生成器

`stance` 子命令是独立的 LLM 驱动立场生成器，根据议题自动推荐辩手配置。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `topic` | 话题 `.md` 文件路径（必填） | — |
| `--model MODEL` | 生成所用 LLM | `gpt-5.2` |
| `--num N` | 辩手数量 | 3 |
| `--prompt TEXT` | 附加生成指令 | — |
| `--format json\|yaml` | 输出格式 | `json` |
| `--base-url URL` | API 端点 | — |
| `--api-key KEY` | API 密钥 | — |

### Library API

```python
from debate_tool.stance import generate_stances_sync, format_stances_json

result = generate_stances_sync(topic_body, model="gpt-5.2", num_debaters=3)
print(format_stances_json(result))
```

## 6. 文件结构

```
debate-tool/
├── pyproject.toml         # 包配置 + 入口点 + extras
├── install.py             # 安装脚本（交互式 + CLI，纯标准库）
├── install-skills.sh      # Claude Code Skill 安装（Shell 版）
├── template.md            # 话题文件模板
├── v2_mechanism_roadmap.md # 辩论机制 v2 改进路线图
├── requirements/          # 传统 requirements 文件（向后兼容）
│   ├── core.txt
│   ├── cli.txt
│   ├── web.txt
│   └── all.txt
└── debate_tool/
    ├── __init__.py        # 版本
    ├── __main__.py        # 统一入口路由（run / build / stance）
    ├── runner.py          # 辩论运行器（核心引擎）
    ├── wizard.py          # TUI 向导（14 步状态机）
    ├── core.py            # 纯逻辑：默认值、YAML 生成、文件 I/O
    ├── ui.py              # Curses TUI 基础组件
    ├── stance.py          # 立场生成器（可独立使用）
    ├── steps.py           # 14 步向导步骤函数
    └── web/
        ├── __init__.py
        ├── __main__.py    # Web 入口
        ├── app.py         # Flask 路由 + API 端点
        └── templates/
            └── wizard.html
```

## License

MIT
