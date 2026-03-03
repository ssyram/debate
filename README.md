# debate-tool

多模型辩论框架，支持 N(>= 2) 个辩手并行多轮辩论，最终由裁判模型给出裁决。

提供两种使用界面：
- **命令行 TUI 向导** — 双栏 Curses 界面，14 步生成辩论配置文件
- **Web 向导** — 响应式单页应用，实时预览，一键提交生成

## 1. 安装

**依赖：Python 3.11+**

```bash
git clone <repo-url>
cd debate-tool
pip install -r requirements.txt
```

依赖：`httpx`、`pyyaml`、`rich`、`click`、`flask`

## 2. 快速开始

### 方法一：Web 向导（推荐）

```bash
python -m debate_tool.web
# 自动打开浏览器本地地址（由 host/port 决定）
```

Web 版与 CLI 版逻辑完全一致，支持宽屏双栏（左侧实时预览 + 右侧表单）和窄屏上下堆叠布局。

### 方法二：命令行 TUI 向导

```bash
python new_debate.py
# 或
python -m debate_tool
```

双栏 Curses TUI，左栏实时预览 YAML，右栏输入表单，共 14 步：

1. 辩论标题
2. 输出路径
3. 轮数设置
4. API 端点（`base_url`，可选）
5. API 密钥（`api_key`，可选）
6. 话题正文（内联输入或指定外部文件）
7. 立场生成器（可选，AI 驱动）
8. 辩手配置（≥2 名，强制校验）
9. 裁判配置（默认 claude-opus-4-6）
10. 约束条件（注入 system prompt）
11. 各轮任务说明（第一轮 / 中间轮 / 最后一轮）
12. 裁判指令
13. 预览（可滚动）并确认生成
14. 成功提示（显示文件路径与运行命令）

CLI 选项：

```bash
python -m debate_tool --output PATH       # 指定输出文件路径
python -m debate_tool --topic-file PATH   # 指定话题文件（跳过部分步骤）
```

Web 选项：

```bash
python -m debate_tool.web --port 8080     # 指定端口
python -m debate_tool.web --no-browser    # 不自动打开浏览器
```

### 方法三：使用模板文件

```bash
cp template.md my_topic.md
# 编辑 my_topic.md，填写 YAML 元数据和话题内容
python debate.py my_topic.md
```

## 3. 运行辩论

```bash
# 基本运行
python debate.py my_topic.md

# 覆盖轮数
python debate.py my_topic.md --rounds 5

# 试运行（仅校验配置，不调用 API）
python debate.py my_topic.md --dry-run
```

**输出文件**：
- `{stem}_debate_log.md` — 完整辩论记录（每轮每位辩手发言）
- `{stem}_debate_summary.md` — 裁判结构化裁决

## 4. API 配置

优先级（从高到低）：

1. 话题文件 YAML 中的 `base_url` / `api_key`
2. 环境变量 `DEBATE_BASE_URL` / `DEBATE_API_KEY`

建议将 API 密钥配置为环境变量，避免写入版本控制：

```bash
export DEBATE_API_KEY=your_api_key
export DEBATE_BASE_URL=your_api_base_url
```

## 5. YAML 字段参考

话题文件以 `---` 包裹的 YAML 块开头：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `title` | string | 文件名 | 辩论标题 |
| `rounds` | int | 3 | 辩论轮数 |
| `timeout` | int | 300 | 单次 API 超时（秒） |
| `max_tokens` | int | 6000 | 辩手单次输出 token 上限 |
| `base_url` | string | env/fallback | OpenAI 兼容 API 端点 |
| `api_key` | string | env/fallback | API 密钥 |
| `debaters` | list | 3 个默认辩手 | 每项含 `name` / `model` / `style` |
| `judge` | object | claude-opus-4-6 | 含 `model` / `name` / `max_tokens` |
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

## 6. 立场生成器

`stance.py` 是独立的 LLM 驱动立场生成器，根据议题自动推荐辩手配置。

### 独立 CLI

```bash
# 基本用法（JSON 输出到 stdout）
python -m debate_tool.stance my_topic.md

# 指定模型和辩手数量
python -m debate_tool.stance my_topic.md --model gpt-5.2 --num 4

# 输出 YAML 格式
python -m debate_tool.stance my_topic.md --format yaml

# 附加自定义要求
python -m debate_tool.stance my_topic.md --prompt "需要一个红队攻击手"
```

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

### TUI 向导立场工作区快捷键

| 键 | 操作 |
|----|------|
| `Space` | 切换选中/取消选中 |
| `Enter` | 确认（需 ≥2 个选中） |
| `C` | 继续生成（纯追加） |
| `R` | 重新生成（保留已选，移除未选，追加新） |
| `A` | 添加自定义辩手 |
| `E` | 编辑当前辩手 |
| `D` | 删除当前辩手 |
| `V` | 立场检验（启发式警告） |
| `Esc` | 跳过/返回 |

## 7. 文件结构

```
debate-tool/
├── .gitignore
├── README.md
├── requirements.txt
├── debate.py              # 辩论运行器
├── new_debate.py          # TUI 向导启动器
├── template.md            # 话题文件模板
└── debate_tool/
    ├── __init__.py        # 版本
    ├── __main__.py        # CLI 入口 + 14 步状态机
    ├── core.py            # 纯逻辑：默认值、YAML 生成、文件 I/O
    ├── ui.py              # Curses TUI 基础组件
    ├── stance.py          # 立场生成器（可独立使用）
    ├── steps.py           # 14 步向导步骤函数
    └── web/
        ├── __init__.py
        ├── __main__.py    # Web 入口（argparse + 自动打开浏览器）
        ├── app.py         # Flask 路由 + 7 个 API 端点
        └── templates/
            └── wizard.html  # 单页应用（HTML + CSS + JS）
```

## License

MIT
