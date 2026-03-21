# debate-tool

多模型辩论框架，支持 N(>= 2) 个辩手并行多轮辩论，最终由裁判模型给出裁决。

提供 Web UI 和命令行两种使用方式：
- **Web UI** — 统一单页应用，内含辩论配置向导 + 实时查看器，支持从界面创建并启动辩论
- **命令行** — `debate-tool run/resume/modify/compact` 直接驱动辩论引擎

## 1. 安装

**依赖：Python 3.11+**

### 推荐方式：pip install

```bash
git clone <repo-url>
cd debate-tool
pip install ".[web]"       # Web UI + 辩论引擎（推荐）
pip install .              # 仅核心（httpx, pyyaml）→ 仅命令行运行辩论
pip install ".[all]"       # 同 [web]
```

### 安装脚本（替代方式）

```bash
python install.py          # 交互式菜单
python install.py --all    # 全量安装所有依赖
python install.py --skill  # 安装 Claude Code /debate 命令
python install.py --env    # 设置 DEBATE_TOOL_DIR 环境变量
```

## 2. 快速开始

### Web UI（推荐）

```bash
# 启动 Web UI，打开浏览器自动配置并启动辩论
python -m debate_tool live

# 或使用 debate-tool 命令（安装后）
debate-tool live
```

Web UI 提供统一的单页应用，包含：
- 辩论配置向导（创建新辩论）
- 实时辩论查看器（监控进度）
- 一键启动辩论

> **架构说明**: Web UI 通过 subprocess 调用 CLI 命令执行辩论，自身仅作为前端界面。所有辩论逻辑由命令行引擎驱动。

### 命令行运行（高级用户）

#### 生成辩论配置

```bash
# 使用模板手动编辑
cp template.md my_topic.md
# 编辑 my_topic.md，填写 YAML 元数据和话题内容
```

#### 运行辩论

```bash
# 基本运行
debate-tool run my_topic.md

# 覆盖轮数
debate-tool run my_topic.md --rounds 5

# 试运行（仅校验配置，不调用 API）
debate-tool run my_topic.md --dry-run

# 质询模式（R1 后增加质询子回合）
debate-tool run my_topic.md --cross-exam

# 指定质询轮数（R1~R3 后均质询）
debate-tool run my_topic.md --cross-exam 3

# 每轮都质询
debate-tool run my_topic.md --cross-exam -1

# 启用收敛早停（默认阈值 55%）
debate-tool run my_topic.md --early-stop

# 自定义早停阈值（60%）
debate-tool run my_topic.md --early-stop 0.6

# 质询 + 早停
debate-tool run my_topic.md --cross-exam --early-stop

# 启用 Chain-of-Thought（辩手先思考再发言，思考内容记入 log 但不传给对方）
debate-tool run my_topic.md --cot

# 指定 CoT 最大 token 数
debate-tool run my_topic.md --cot 2000
```

### 续跑与压缩

```bash
# 简单续跑 1 轮（第一个参数：日志文件 .json，必填）
debate-tool resume my_topic_debate_log.json --rounds 1

# 使用 Resume Topic 文件（第二个参数：.md，可选，用于批量覆盖配置）
debate-tool resume my_topic_debate_log.json phase2.md

# 续跑 2 轮 + 注入观察者意见
debate-tool resume my_topic_debate_log.json --rounds 2 --message "请重点讨论安全性"

# 续跑时启用质询
debate-tool resume my_topic_debate_log.json --rounds 1 --cross-exam

# 只触发 judge，不追加辩论（rounds=0）
debate-tool resume my_topic_debate_log.json --rounds 0

# 跳过裁判（辩论正常跑，只是不执行 judge phase）
debate-tool run my_topic.md --no-judge
debate-tool resume my_topic_debate_log.json --rounds 1 --no-judge

# 只注入配置、什么都不做（用于向 log 写入新字段，如 compact_model）
# 推荐改用 modify，语义更清晰：
debate-tool modify my_topic_debate_log.json inject_config.md
# 等价于（但 modify 更清晰）：
# debate-tool resume my_topic_debate_log.json inject_config.md --rounds 0 --no-judge

# 变更辩手组成（add/drop）须通过 Resume Topic 文件 + --force（防止误操作）
debate-tool resume my_topic_debate_log.json phase2.md --force

# 轻量级指引（不写入 log，仅影响本次续跑的每轮任务描述）
debate-tool resume my_topic_debate_log.json --rounds 1 --guide "聚焦幕府财政危机的根本原因"

# 跳过话题一致性检查（如果日志和 topic 来自不同话题）
debate-tool resume my_topic_debate_log.json different_topic.md --force

# 手动压缩日志（全部压缩，生成 checkpoint）
debate-tool compact my_topic_debate_log.json

# 保留末尾 2 条不压缩，其余全压
debate-tool compact my_topic_debate_log.json --keep-last 2

# 附加压缩指令
debate-tool compact my_topic_debate_log.json --message "重点保留安全性论点"
```

### 仅修改配置（modify）

`modify` 是 `resume --rounds 0 --no-judge` 的简写，仅应用 Resume Topic 中的配置变更，不执行辩论也不触发裁判：

```bash
# 仅应用 Resume Topic 配置变更（不辩论、不裁判）
debate-tool modify my_topic_debate_log.json inject_config.md

# 涉及 add/drop 辩手时仍需 --force
debate-tool modify my_topic_debate_log.json phase2.md --force
```

**Resume Topic 文件**

Resume Topic 文件（.md）支持增量覆盖配置，覆盖内容记入 log 并持久累积：

- **YAML front-matter**：增量覆盖字段（`middle_task`, `final_task`, `constraints`, `judge_instructions`, `add_debaters`, `drop_debaters`, `judge`, `cross_exam`, `max_reply_tokens`, `cot` 等）；`add_debaters`/`drop_debaters` 需配合 `--force` 使用
- **Markdown body**：观察者消息（等同于 `--message`）

> 所有 `resume` / `compact` 操作均追加到同一 `*_debate_log.json`，原始历史完整保留。

> 日志格式转换脚本（双向）：

```bash
# 旧版 Markdown 日志 -> JSON（用于 resume/compact）
python scripts/convert_md_log_to_json.py old_debate_log.md

# JSON 日志 -> Markdown（用于阅读）
python scripts/convert_json_log_to_md.py my_topic_debate_log.json

# 直接输出到终端，方便先转换再作为自然语言阅读
python scripts/convert_json_log_to_md.py my_topic_debate_log.json --stdout
```

> 主工具本身只接受 JSON 日志；Markdown 主要用于阅读或历史迁移。

> 所有命令也可通过 `python -m debate_tool <command>` 调用。

**输出文件**：
- `{stem}_debate_log.json` — 完整辩论记录（JSON 持久化）
- `{stem}_debate_summary.md` — 裁判结构化裁决
- `{stem}_debate_log.md` — 可读版日志（由 `scripts/convert_json_log_to_md.py` 手动生成）

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

### 辩手模型列表

`DEFAULT_DEBATE_MODELS` 环境变量控制辩手的默认模型，逗号分隔，循环分配给每位辩手（第 i 位辩手使用 `models[i % len(models)]`）：

```bash
export DEFAULT_DEBATE_MODELS="gpt-5.2,kimi-k2.5,MiniMax-M2.5"
```

- 未设置时默认全部使用 `gpt-5.2`

## 4. YAML 字段参考

话题文件以 `---` 包裹的 YAML 块开头：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `title` | string | 文件名 | 辩论标题 |
| `rounds` | int | 3 | 辩论轮数 |
| `timeout` | int | 300 | 单次 API 超时（秒） |
| `max_reply_tokens` | int | 6000 | 辩手单次回复最多输出的 token 数（控制输出长度，与上下文窗口无关） |
| `cross_exam` | int | `0` | 质询轮数 (0=关, 1=R1后, -1=每轮) |
| `early_stop` | bool/float | `false` | 收敛早停: `true` 用默认阈值 55%, 或指定 0~1 的浮点数 |
| `no_judge` | bool | `false` | 跳过裁判总结阶段（辩论正常跑，不调用 judge）；可在 topic/resume topic YAML 中设置 |
| `base_url` | string | env/fallback | OpenAI 兼容 API 端点 |
| `api_key` | string | env/fallback | API 密钥 |
| `debaters` | list | 3 个默认辩手 | 每项含 `name` / `model` / `style`，可选 `base_url` / `api_key` |
| `judge` | object | claude-opus-4-6 | 含 `model` / `name` / `max_tokens`（裁判输出上限），可选 `base_url` / `api_key` |
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

### 质询模式 (`--cross-exam`)

质询模式在指定轮次后增加质询子回合，辩手按 round-robin 顺序互相质疑：

```
R1: 并行发言 → R1.5: 串行质询 (d1→d2, d2→d3, ..., dN→d1) → R2: 逐条回应质询 → ...→ 裁判
```

- `--cross-exam` — R1 后质询（等价于 `--cross-exam 1`）
- `--cross-exam 3` — R1、R2、R3 后均质询
- `--cross-exam -1` — 每轮都质询（最后一轮除外）
- 每位提问者引用 target 的发言，提出 2-3 个尖锐质疑
- 质询后的下一轮任务自动变为"逐条回应收到的质询"
- 质询日志标记为 `🔍`，裁判可引用质询中暴露的论证缺陷

**适用场景**：争议性强的议题、需要辩手真正交锋而非各说各话的场合。

在 YAML 中配置：

```yaml
cross_exam: 1    # R1 后质询
cross_exam: -1   # 每轮都质询
```

### 收敛早停 (`--early-stop`)

每轮结束后检查所有辩手发言的字符三元组 Jaccard 相似度，若两两平均相似度达到阈值则跳过剩余轮次，直接进入裁判阶段。

- `--early-stop` — 使用默认阈值 55%
- `--early-stop 0.6` — 自定义阈值 60%

```yaml
early_stop: true       # 默认阈值 55%
early_stop: 0.7        # 自定义阈值 70%
```

可与 `--cross-exam` 组合使用。

## 5. 测试

项目包含完整的端到端集成测试套件，通过内置 Mock Server 完全离线运行，无需真实 LLM API。

```bash
# 运行全部测试（Mock 模式，无需 API key）
python3 test/test.py

# 静默模式
python3 test/test.py --quiet

# 仅运行快速测试（dry_run + error 系列）
python3 test/test.py --quick

# 按名称过滤
python3 test/test.py --filter basic,cross_exam

# 生成/更新 golden 参考文件
python3 test/test.py --generate-golden
```

测试覆盖 58 个场景、62 个特性维度，包括：
- **RUN 系列**（13 项）：basic、cross_exam、cot、constraints、early_stop 等
- **RESUME 系列**（10 项）：message、guide、add/drop debater、judge override 等
- **COMPACT 系列**（10 项）：全量压缩、幂等性、keep-last、resume chain 等
- **DEGRADATION 系列**（2 项）：Phase A/B 重试降级
- **CANARY 系列**（3 项）：constraints/message/guide prompt 注入验证
- **ERROR 系列**（12 项）：缺少文件、非法参数、--force 校验等
- **NEW 系列**（8 项）：version、modify、drop_debater 等

**核心机制**：
- **Mock Server**：轻量级 HTTP 服务器，模拟 OpenAI Chat/Embeddings API，路由表从 topic 文件的 `mock_responses` YAML 字段自动加载
- **Golden 对比**：归一化时间戳/URL/API key 后，与 `test/golden/` 下的参考文件逐字符比较
- **结构性检查**：独立于文本内容的结构断言（辩手数、轮数、质询位置等）

> 详细说明见 [test/README.md](test/README.md)

## 6. 文件结构

```
debate-tool/
├── pyproject.toml         # 包配置 + 入口点 + extras
├── install.py             # 安装脚本（交互式 + CLI，纯标准库）
├── install-skills.sh      # Claude Code Skill 安装（Shell 版）
├── template.md            # 话题文件模板
├── requirements/          # 传统 requirements 文件（向后兼容）
│   ├── core.txt
│   └── web.txt
├── debate_tool/
│   ├── __init__.py        # 版本
│   ├── __main__.py        # 统一入口路由（run / resume / compact / live）
│   ├── runner.py          # 辩论运行器（核心引擎）
│   ├── session.py         # DebateSession（Web live 用，通过 subprocess 调用 CLI）
│   ├── core.py            # 纯逻辑：默认值、YAML 生成、文件 I/O
│   └── web/
│       ├── __init__.py
│       ├── __main__.py    # Web 入口
│       ├── app.py         # Flask 路由 + API 端点
│       ├── live.py        # 辩论实时查看器 Blueprint（subprocess + 文件监视 → SSE）
│       └── templates/
│           ├── debate_live.html  # 统一 UI（含新建辩论 Modal）
│           └── wizard.html       # 完整配置向导（/wizard 路由）
└── test/
    ├── test.py              # 端到端测试主文件
    ├── mock_server.py       # Mock HTTP 服务器
    ├── mock_routes.py       # 路由表（从 topic YAML 解析）
    ├── golden_compare.py    # Golden 文件对比工具
    ├── structural_checks.py # 结构性断言
    ├── README.md            # 测试文档
    ├── topics/              # 测试用 topic 文件（含 mock_responses）
    ├── resume_topics/       # Resume 测试用覆盖文件
    └── golden/              # Golden 参考文件（标准答案）
        ├── run/
        ├── resume/
        └── compact/
```

## License

MIT
