# debate-tool 大改计划：Log 为主体 + 续跑驱动的结构化辩论

## Context

当前架构以 **topic 文件为中心**：run/resume 都从 topic 文件读取全部配置，log 只存 entries + title。问题：

1. **log 不自包含**：丢失 topic 文件后 log 无法独立使用
2. **resume 受限**：只能 `--message` / `--guide` 微调，不能改 task/constraints/debaters
3. **Phase 只能硬编码**：阶段式辩论必须在 runner 内建 phases

**目标**：log 为辩论主体（辩题为不可变根基），resume 为核心操作原语（每次可带 config overrides），外部编排通过多次 resume 实现 Phase，无需 runner 内建阶段。

**Config 模型**：累积式。log 存 initial_config，每次 resume 的 overrides 记录为 `config_override` entry，下次 resume 默认值 = initial + 历史 overrides 合并 + 本次 CLI overrides。

---

## 一、Log Schema v2

### 1.1 新 JSON 结构

**文件**：`debate_tool/runner.py` — Log 类 (line 1240) 和 `_flush()` (line 1300)

```json
{
  "format": "debate-tool-log",
  "version": 2,
  "title": "辩论标题",
  "topic": "辩论议题的完整 Markdown 正文（不可变）",
  "initial_config": {
    "debaters": [{"name": "A", "model": "gpt-5", "style": "支持X", "base_url": "http://localhost:8081/v1/chat/completions"}],
    "judge": {"name": "裁判", "model": "claude-opus-4-6", "max_tokens": 8000},
    "constraints": "核心约束文本",
    "round1_task": "...",
    "middle_task": "...",
    "final_task": "...",
    "judge_instructions": "...",
    "max_reply_tokens": 6000,
    "timeout": 300,
    "cross_exam": 0,
    "early_stop": false,
    "cot": null,
    "compact_model": null,
    "compact_check_model": null,
    "compact_max_tokens": null,
    "embedding_model": null
  },
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp",
  "entries": [...]
}
```

<!-- Fix C1: per-debater API 凭证策略——base_url 保留，api_key 排除 -->
**关键约束**：
- `topic` 字段只写一次，不可变（= 辩论的 Identity）
- `initial_config` **保留** per-debater `base_url`（URL 不是秘密，且 OpenCode Proxy 等多端点场景依赖它），但**排除** `api_key`（密钥不持久化到 log）
- `api_key` 始终从 env / .env 注入，不持久化到 log
- `initial_config` 是首次 run 时的快照，后续 resume 通过 `config_override` entries 演化

<!-- Fix H2: compact 相关配置字段加入 initial_config，使 compact_log 命令可从 v2 log 独立运行 -->
- `initial_config` 还包含 compact 相关配置字段：`compact_model`、`compact_check_model`、`compact_max_tokens`、`embedding_model`（若未配置则填 null），使 `compact_log` 命令无需外部 topic 文件即可独立运行

### 1.2 Config Override Entry（新 tag）

```json
{
  "seq": N,
  "ts": "ISO timestamp",
  "tag": "config_override",
  "name": "@系统",
  "content": "变更摘要（人类可读）",
  "overrides": {
    "middle_task": "只做现象描述，不下判断",
    "constraints": "不允许提出解决方案",
    "add_debaters": [{"name": "新辩手", "model": "gpt-5", "style": "中立分析"}],
    "drop_debaters": ["旧辩手"],
    "judge": {"name": "新裁判", "model": "claude-opus-4-6"},
    "cross_exam": -1
  }
}
```

### 1.3 Effective Config 解析

<!-- Fix H4: _all_entries() 改为公开方法 all_entries()，避免运行时 AttributeError -->
<!-- Fix L1: round1_task 有意排除在可 override 字段之外，因为 resume 不存在"第一轮"语义 -->
<!-- Fix L8: add_debaters 先执行，drop_debaters 后执行，避免同一 entry 中"加了又删"的歧义 -->
**新增函数**：`resolve_effective_config(log) -> dict`

```python
def resolve_effective_config(log: Log) -> dict:
    """从 log 的 initial_config + 所有 config_override entries 合并出当前有效配置。"""
    cfg = deepcopy(log.initial_config)
    for entry in log.all_entries():  # 使用公开方法 all_entries()（见 Section 二）
        if entry.get("tag") != "config_override":
            continue
        overrides = entry.get("overrides", {})
        # 辩手增减：先执行 add_debaters，再执行 drop_debaters，避免同一 entry 中"加了又删"的歧义
        if "add_debaters" in overrides:
            existing_names = {d["name"] for d in cfg["debaters"]}
            for d in overrides["add_debaters"]:
                if d["name"] not in existing_names:
                    cfg["debaters"].append(d)
        if "drop_debaters" in overrides:
            drop_set = set(overrides["drop_debaters"])
            cfg["debaters"] = [d for d in cfg["debaters"] if d["name"] not in drop_set]
        # judge 替换（完整覆盖）
        if "judge" in overrides:
            cfg["judge"].update(overrides["judge"])
        # 简单字段覆盖
        # 注意：round1_task 有意排除在可 override 字段之外，因为 resume 不存在"第一轮"语义
        for key in ("middle_task", "final_task", "constraints", "judge_instructions",
                     "max_reply_tokens", "timeout", "cross_exam", "early_stop", "cot"):
            if key in overrides:
                cfg[key] = overrides[key]
    return cfg
```

放在 `runner.py` 中，靠近 Log 类。

---

## 二、Log 类改动

**文件**：`debate_tool/runner.py` — Log 类 (line 1240-1361)

<!-- Fix H4: _all_entries() 改为公开方法 all_entries() -->
### 2.0 `_all_entries()` 改为公开方法 `all_entries()`

将现有私有方法 `_all_entries()` 改为公开方法 `all_entries()`，理由：`resolve_effective_config` 及外部代码需要遍历全部 entries（含 archived），不应通过私有接口访问。

```python
# 原：def _all_entries(self) -> list[dict]:
# 改为：
def all_entries(self) -> list[dict]:
    """返回 archived_entries + entries 的合并列表（按 seq 顺序）。"""
    return self._archived_entries + self.entries
```

内部所有调用 `self._all_entries()` 的地方同步改为 `self.all_entries()`。

### 2.1 构造函数扩展

```python
class Log:
    def __init__(self, path: Path, title: str, *, topic: str = "", initial_config: dict | None = None):
        self.path = path
        self.title = title
        self.topic = topic                          # 新增：不可变辩题
        self.initial_config = initial_config or {}  # 新增：首次配置快照
        self.entries: list[dict] = []
        self._archived_entries: list[dict] = []
```

### 2.2 `_flush()` 输出 v2 格式

```python
def _flush(self):
    all_entries = self.all_entries()  <!-- Fix r2-H4: _all_entries() → all_entries()，与 Section 2.0 公开方法声明保持一致 -->
    payload = {
        "format": LOG_FORMAT,
        "version": 2,  # 升级
        "title": self.title,
        "topic": self.topic,                    # 新增
        "initial_config": self.initial_config,  # 新增
        "created_at": all_entries[0]["ts"] if all_entries else datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "entries": all_entries,
    }
    # ... atomic write 逻辑不变
```

### 2.3 `load_from_file()` 严格 v2

```python
@classmethod
def load_from_file(cls, path: Path) -> "Log":
    payload, all_entries = _load_json_log_payload(path)
    # 严格要求 v2 格式
    if payload.get("version") != 2 or "topic" not in payload or "initial_config" not in payload:
        print("❌ 日志格式不是 v2，缺少 topic 或 initial_config 字段。", file=sys.stderr)
        print("   请先运行迁移脚本：python3 scripts/migrate_v1_to_v2.py TOPIC_FILE LOG_FILE", file=sys.stderr)
        sys.exit(1)
    log = cls(
        path,
        payload["title"],
        topic=payload["topic"],
        initial_config=payload["initial_config"],
    )
    # ... checkpoint 恢复逻辑不变
```

### 2.4 `since()` 排除新 tag

<!-- Fix M5: tag filter 矩阵——明确三处各自排除的 tag，config_override 必须加入全部三处 -->
在 exclude set 中加入 `"config_override"`（配置变更不应出现在辩手上下文中）。

**完整 tag filter 矩阵**（三处 filter 均需统一）：

| tag | `since()` 排除 | `entries_since_seq()` 排除 | `format_delta_entries_text()` 排除 |
|-----|--------------|--------------------------|----------------------------------|
| `thinking` | ✅ | ✅ (exclude_tags) | ✅ |
| `summary` | ✅ | ✅ (exclude_tags) | ✅ |
| `config_override` | ✅ **新增** | ✅ **新增** | ✅ **新增** |

实现要求：
- `since()`：在硬编码 exclude set 中加入 `"config_override"`
- `entries_since_seq(exclude_tags)` 的调用方：确保传入的 `exclude_tags` 包含 `"config_override"`
- `format_delta_entries_text()`：在 tag filter 处加入 `"config_override"`

---

## 三、`run()` 函数改动

**文件**：`debate_tool/runner.py` — `async def run()` (line 1790)

### 3.1 创建 Log 时注入 topic + initial_config

当前 (line 1796 附近)：
```python
log = Log(log_path, title)
```

<!-- Fix C1: per-debater base_url 保留（OpenCode Proxy 等多端点场景依赖），仅排除 api_key -->
<!-- Fix M6: 调用 core._build_initial_config(cfg) 而非内联，确保唯一入口 -->
<!-- Fix L2: middle_task_optional 字段在 v2 中废弃，迁移时忽略，不写入 initial_config -->
改为：
```python
# 调用 core._build_initial_config(cfg) 构建 initial_config（唯一入口，见 Section 10.2）
initial_config = core._build_initial_config(cfg)

log = Log(log_path, title, topic=cfg["topic_body"], initial_config=initial_config)
```

`_build_initial_config(cfg)` 的构建逻辑见 Section 10.2。要点：
- per-debater `base_url` **保留**（URL 不是秘密，多端点场景必需）
- per-debater `api_key` **排除**（密钥不持久化）
- judge 的 `base_url` 同理保留，`api_key` 排除
- compact 配置字段（`compact_model`, `compact_check_model`, `compact_max_tokens`, `embedding_model`）从 cfg 中提取，未配置则填 null
- `middle_task_optional` 字段在 v2 中废弃，不写入 initial_config

run() 其余逻辑不变 — 仍然使用 `cfg` 驱动循环（第一次 run 不经过 resolve_effective_config）。

---

## 四、`resume()` 函数重构（核心改动）

**文件**：`debate_tool/runner.py` — `async def resume()` (line 2115-2391)

### 4.1 新签名

```python
async def resume(
    *,
    log_path: Path,
    resume_topic_path: Path | None = None,  # 新增：Resume Topic 文件路径
    cfg_overrides: dict | None = None,      # 新增：结构化 config overrides
    # 保留现有参数
    message: str = "",
    extra_rounds: int = 1,
    cross_exam: int | None = None,          # None = 沿用 effective config
    guide_prompt: str = "",
    force: bool = False,
    cot_length: int | None = None,          # None = 沿用 effective config
) -> None:
```

### 4.2 Config 解析流程

<!-- Fix H1: 定义 _describe_overrides / _apply_overrides 签名和职责 -->
<!-- Fix C1: per-debater base_url 从 eff_cfg["debaters"] 读，api_key 从 env 注入 -->
<!-- Fix L6: eff_cfg.get("base_url", "") 已无意义（initial_config 不存全局 base_url），改为直接用 ENV_BASE_URL -->

**辅助函数定义**（新增，放在 `runner.py` 靠近 `resolve_effective_config` 处）：

```python
def _describe_overrides(overrides: dict) -> str:
    """生成 config_override entry 的人类可读摘要字符串（写入 entry.content）。

    职责：把 overrides dict 的键值对转为简洁中文描述。
    示例输出："更新 middle_task；新增辩手：分析师；移除辩手：旧辩手"
    不依赖任何外部状态，纯函数。
    """
    ...

def _apply_overrides(cfg: dict, overrides: dict) -> None:
    """将单次 override dict 就地合并到 cfg（复用 resolve_effective_config 内的合并逻辑）。

    职责：处理 add_debaters、drop_debaters、judge、以及简单字段覆盖。
    执行顺序：先 add_debaters，后 drop_debaters（避免同一 entry 中"加了又删"的歧义）。
    不处理 round1_task（有意排除，resume 不存在"第一轮"语义）。
    注意：resolve_effective_config 应在内部循环中调用 _apply_overrides，而非重复相同逻辑。
    """
    ...
```

`resolve_effective_config` 重构为内部调用 `_apply_overrides`：
```python
def resolve_effective_config(log: Log) -> dict:
    cfg = deepcopy(log.initial_config)
    for entry in log.all_entries():
        if entry.get("tag") == "config_override":
            _apply_overrides(cfg, entry.get("overrides", {}))
    return cfg
```

**Config 解析主流程**：

```python
log = Log.load_from_file(log_path)

# 1. 获取 topic（辩题）— v2 log 必定包含
topic = log.topic

# 2. 解析 effective config（initial + 历史 overrides）
eff_cfg = resolve_effective_config(log)

# 2.5 解析 Resume Topic 文件（在 effective config 之后、CLI overrides 之前）
if resume_topic_path:
    rt_overrides, rt_message = parse_resume_topic(resume_topic_path)
    # 提取运行控制参数（不记入 config_override）
    if "rounds" in rt_overrides:
        extra_rounds = rt_overrides.pop("rounds")
    if "guide" in rt_overrides:
        guide_prompt = rt_overrides.pop("guide")
    # 剩余字段作为 cfg_overrides
    if rt_overrides:
        cfg_overrides = {**(cfg_overrides or {}), **rt_overrides}
    # body 作为 message（与 --message 互斥）
    if rt_message and not message:
        message = rt_message

# 3. 应用本次 CLI overrides
if cfg_overrides:
    # 记录到 log
    desc = _describe_overrides(cfg_overrides)  # 生成人类可读摘要
    log.add("@系统", desc, "config_override", extra={"overrides": cfg_overrides})
    # 合并
    _apply_overrides(eff_cfg, cfg_overrides)

# 4. CLI 参数覆盖对应字段（临时覆盖，不记入 log）
if cross_exam is not None:
    eff_cfg["cross_exam"] = cross_exam
if cot_length is not None:
    eff_cfg["cot"] = cot_length

# 5. 注入 API 凭证（始终从 env）
# 注意：全局 base_url 已无意义（eff_cfg 中无该字段），直接使用 ENV 变量作为 fallback
debate_base_url = ENV_BASE_URL  # eff_cfg.get("base_url", "") 已无意义，不再使用
debate_api_key = ENV_API_KEY
# per-debater 凭证：base_url 从 eff_cfg["debaters"] 读（已持久化），api_key 从 env 注入
for d in eff_cfg["debaters"]:
    if not d.get("api_key"):
        d["api_key"] = debate_api_key  # 运行时注入，不写回 log

# 6. 提取工作变量
debaters = eff_cfg["debaters"]
judge = eff_cfg["judge"]
constraints = eff_cfg["constraints"]
middle_task = eff_cfg["middle_task"]
# ...
```

### 4.3 Validation 更新

- **移除** debater name 强制匹配检查（`validate_topic_log_consistency` 中的 ghost debater exit）
- **保留** LLM consistency check（但 topic 从 log 读而非 cfg）
- **新增** debater 变更日志：当 effective debaters 与上次不同时，打印变更信息

### 4.4 辩论循环

<!-- Fix L3: early_stop 在 resume 中的行为说明 -->
**`early_stop` 在 resume 中的行为**：resume 继承并激活 `early_stop`。若 `eff_cfg["early_stop"]` 为 True，则在每轮结束后执行 trigram Jaccard 收敛检测，与 run() 行为一致。逻辑：resume 是辩论的延续，不应因切换入口而改变收敛行为。

Resume 的内层循环逻辑与当前基本一致，但使用 `eff_cfg` 而非 `cfg`：

```python
for r_offset in range(1, extra_rounds + 1):
    rnd = base_round + r_offset

    # 任务选择（优先级：guide > message first round > eff_cfg middle_task）
    if guide_prompt:
        task_desc = f"回应其他辩手观点，深化立场。400-600 字\n\n观察者指引：{guide_prompt}"
    elif message and r_offset == 1:
        task_desc = "请回应观察者提出的问题/意见，同时深化自己的立场。400-600 字"
    elif r_offset == extra_rounds and eff_cfg.get("final_task"):
        task_desc = eff_cfg["final_task"]  # 本批次最后一轮用 final_task
    else:
        task_desc = eff_cfg["middle_task"]

    # speak() 闭包使用 eff_cfg 中的 debaters, constraints 等
    # ... 其余逻辑不变
```

### 4.5 Judge-only 模式

`extra_rounds=0` 表示不追加辩论轮次（`range(1, 1)` 不执行循环），但 judge 仍然执行。用于外部编排在最后一步只出 summary。

---

## 四·五、Resume Topic 文件格式

Resume Topic 文件是 resume 操作的重量级输入，格式照抄 topic 文件（YAML front-matter + Markdown body）。

### 设计原则：Judge 是核心输出

Judge 是辩论与用户之间的核心接口。每次 resume 结束后 judge 都会生成 summary，用户通过 summary 了解辩论进展、决定下一步操作。因此：

- **Judge 永远执行**，不提供跳过选项
- **`judge_instructions` 是每个 Phase 最重要的配置**——它决定了 judge 关注什么、输出什么格式
- 外部编排的关键：每个 Phase 用不同的 `judge_instructions` 引导 judge 产出不同类型的总结

### 格式定义

YAML front-matter 包含 config overrides（没提到的字段保持不变）：

```yaml
---
# 运行控制
rounds: 2

# Judge 指令（每个 Phase 的核心配置）
judge_instructions: "总结各方对真问题的判断，列出共识和分歧点"

# 任务覆盖
middle_task: "基于前面的现象分析，判断是否构成真问题。"
final_task: "给出最终判断。"
constraints: "本阶段只做判断，不提解决方案"

# 辩手增减（谨慎使用）
add_debaters:
  - name: 分析师
    model: gpt-5
    style: "擅长问题分解，关注逻辑链完整性"

drop_debaters:
  - 旧辩手名

# Judge 覆盖
judge:
  model: claude-opus-4-6
  max_tokens: 1000

# 其他
cross_exam: -1
max_reply_tokens: 800
cot: 200
guide: "关注论证链的完整性"
---

这里是观察者消息正文，等同于 --message。

辩手会看到这段内容，可以包含多段 Markdown。用于向辩手提出问题、提供新信息或重新聚焦讨论方向。
```

### 字段映射

| Resume Topic 字段 | 对应 config override 字段 | 说明 |
|---|---|---|
| `rounds` | CLI `extra_rounds` | 追加轮数（默认 1，0=仅裁判） |
| `judge_instructions` | `judge_instructions` override | Judge 关注点和输出格式（每个 Phase 的核心配置） |
| `middle_task` | `middle_task` override | 本批次中间轮任务 |
| `final_task` | `final_task` override | 本批次最后一轮任务 |
| `constraints` | `constraints` override | 替换约束 |
| `add_debaters` | `add_debaters` override | 添加辩手列表 |
| `drop_debaters` | `drop_debaters` override | 移除辩手名称列表 |
| `judge` | `judge` override | 裁判配置覆盖 |
| `cross_exam` | `cross_exam` override | 质询频率 |
| `max_reply_tokens` | `max_reply_tokens` override | 最大回复 token |
| `cot` | `cot` override | CoT 长度 |
| `guide` | CLI `guide_prompt` | 辩手引导（不记入 config_override） |
| Body | CLI `message` | 观察者消息 |

<!-- Fix M1: CLI vs Resume Topic 持久性语义差异 -->
**持久性语义差异说明**：

| 来源 | 是否记入 log | 行为描述 |
|------|------------|---------|
| Resume Topic 中的字段（`middle_task`, `cross_exam`, `cot` 等） | ✅ 记入 `config_override` entry | **持久累积**：下次 resume 时自动继承（通过 `resolve_effective_config`） |
| CLI 参数 `--cross-exam`、`--cot` | ❌ 不记入 log | **临时覆盖**：只影响本次运行，下次 resume 不继承 |
| CLI 参数 `--rounds`、`--message`、`--guide` | ❌ 不记入 log（内容会写入辩论 entries） | **临时运行控制**：控制本次轮数/消息 |

设计意图：Resume Topic 文件代表"阶段升级"（持久变更），CLI 参数代表"单次调整"（临时覆盖）。同名字段（如 `cross_exam`）在 Resume Topic 中是持久的，在 CLI 中是临时的。

### 解析逻辑

新增函数 `parse_resume_topic(path: Path) -> tuple[dict, str]`：
- 返回 `(overrides_dict, message_body)`
- 复用 topic 文件的 YAML front-matter 解析逻辑
- `rounds`, `guide` 是运行控制参数，提取后不记入 config_override
- 其余字段构成 `cfg_overrides` dict，记入 log 的 config_override entry

### 与 topic 文件的关系

| | Topic 文件 | Resume Topic 文件 |
|---|---|---|
| 用途 | 首次 `run` 的完整配置 | `resume` 的增量覆盖 |
| debaters | 完整辩手列表 | `add_debaters` / `drop_debaters`（增量） |
| Body | 辩题正文（不可变） | 观察者消息 |
| API 凭证 | 包含（`${ENV}` 占位符） | 不包含（从 env 读） |
| 必需字段 | 全部 | 无（全部可选） |

---

## 五、Resume CLI 改动

**文件**：`debate_tool/__main__.py` — `_handle_resume()` (line 36-120)

### 5.1 新 CLI 接口

```
debate-tool resume LOG_FILE [RESUME_TOPIC] [options]

位置参数:
  LOG_FILE                v2 日志文件（必需）
  RESUME_TOPIC            Resume Topic 文件（可选，批量配置）

运行控制（可被 Resume Topic 覆盖）:
  --rounds N              追加轮数 (默认 1, 0=不追加辩论轮次但 judge 仍执行)

消息注入:
  --message TEXT          观察者消息（与 Resume Topic body 互斥）
  --guide TEXT            辩手引导

其他:
  --cross-exam [N]        质询频率
  --cot [LENGTH]          CoT
  --force                 跳过校验
```

<!-- Fix L4: --no-judge 明确列为被删除参数 -->
<!-- Fix L7: parse_resume_topic 内联于 runner.py，不单独建文件 -->
注意：去掉了 `--task`、`--constraint`、`--add-constraint`、`--add-debater`、`--drop-debater`、**`--no-judge`** 这些 CLI 参数。需要批量配置 → 写 Resume Topic 文件。简单续跑 → 只用 `--rounds`、`--message` 等轻量参数。

`parse_resume_topic()` 函数**内联于 `runner.py`**，不单独创建 `debate_tool/resume_topic.py` 文件（见 Section 十三文件影响总览）。

---

## 六、`_load_json_log_payload()` 严格 v2

**文件**：`debate_tool/runner.py` — `_load_json_log_payload()` (line 316-340)

load 时严格验证 `version == 2`，且 `topic` 和 `initial_config` 字段必须存在。如果缺少任何一个，报错退出并提示格式不对：

```python
def _load_json_log_payload(path: Path) -> tuple[dict, list[dict]]:
    # ... 读取 JSON ...
    if payload.get("version") != 2:
        print("❌ 日志格式不是 v2。请先运行迁移脚本：", file=sys.stderr)
        print("   python3 scripts/migrate_v1_to_v2.py TOPIC_FILE LOG_FILE", file=sys.stderr)
        sys.exit(1)
    if "topic" not in payload or "initial_config" not in payload:
        print("❌ v2 日志缺少 topic 或 initial_config 字段。", file=sys.stderr)
        sys.exit(1)
    # ... 返回 payload + entries ...
```

---

## 七、`validate_topic_log_consistency()` 放宽

**文件**：`debate_tool/runner.py` — line 2770-2833

<!-- Fix H5: v2 下比较逻辑重新设计 -->
<!-- Fix L5: check_topic_log_consistency_with_llm 移除 -->

### v2 下的新比较逻辑

**v1 旧逻辑**：比较"topic 文件中的辩手"与"log 中的辩手"，不匹配则 exit。

**v2 新逻辑**：v2 下不再有外部 topic 文件，比较对象改为：
- **Left**：`resolve_effective_config(log)["debaters"]`（计划中应参与的辩手）
- **Right**：log 中实际有发言记录的辩手集合（即 `{e["name"] for e in log.all_entries() if e.get("tag") == "debater"}`）

如有差异则打印 warning 并列出，不 exit（差异可能是合法的，如辩手中途退出后再 resume）。

**新函数签名**：

```python
def validate_topic_log_consistency(log: Log, *, force: bool = False) -> None:
    """v2 版本：比较 effective config 中的辩手列表与 log 中实际发言辩手，差异则 warning。

    Args:
        log: 已加载的 v2 Log 对象（含 initial_config + config_override entries）
        force: 若 True，跳过所有校验
    """
    if force:
        return
    planned = {d["name"] for d in resolve_effective_config(log)["debaters"]}
    actual = {e["name"] for e in log.all_entries() if e.get("tag") == "debater"}
    in_plan_not_spoke = planned - actual
    spoke_not_in_plan = actual - planned
    if in_plan_not_spoke:
        print(f"⚠️  计划辩手未发言：{in_plan_not_spoke}", file=sys.stderr)
    if spoke_not_in_plan:
        print(f"⚠️  发言辩手不在当前计划中：{spoke_not_in_plan}（可能已通过 drop_debaters 移除）", file=sys.stderr)
```

如果有 `config_override` entry 显式记录了 add/drop_debaters，则 `resolve_effective_config` 已反映这些变更，差异会自然减少。

### `check_topic_log_consistency_with_llm()` 移除

该函数在 v2 下语义冗余：topic 已持久化于 log 中（同一数据源），LLM 检查必然通过，维护成本大于价值。v2 实现时删除此函数。

---

## 八、Compact State 适配与辩手扬弃

**文件**：`debate_tool/compact_state.py`

### 8.1 新辩手加入时的上下文继承（扬弃）

新辩手加入已进行中的辩论时，需要「知道前面发生了什么」但「以新视角参与」：

1. **公共信息完整可见**：compact state 的 public view（axioms, disputes, pruned_paths）对新辩手完全可见——这是辩论的客观共识，不属于任何特定辩手
2. **无历史 stance**：新辩手没有 ParticipantState，不继承任何旧辩手的立场。`render_stance_for_system()` 对新辩手跳过
3. **历史发言可见**：新辩手能通过 `log.since()` 看到所有人（包括已退出辩手）的历史发言
4. **style 是新的**：`--add-debater "名字|模型|style"` 中的 style 是全新指定的，不基于任何旧辩手

效果：新辩手就像一个「读完会议纪要后加入讨论的新与会者」——了解背景但带新视角。

### 8.2 ParticipantState 处理动态辩手

Phase B（per-debater stance update）需要处理：
- **新辩手**（无历史 stance）→ 下一次 compact 时 Phase B 为其创建新 ParticipantState（stance_version=0）
- **已退出辩手** → CompactState.participants 中保留其最终 stance 但标记 `active: false`，避免后续 Phase B 继续更新

`ParticipantState` TypedDict 增加：
```python
class ParticipantState(TypedDict):
    name: str
    active: bool  # 新增：False = 已退出辩论
    # ... 其余不变
```

<!-- Fix M4: 迁移时补填 active: True 默认值，见 Section 十一 -->

<!-- Fix L9: CompactState.topic 与 Log.topic 同名语义差异说明 -->
**命名冲突说明**：`CompactState` 中的 `"topic"` 字段与 `Log.topic` 字段同名但语义不同：
- `Log.topic`：辩论的**不可变原始辩题**（首次 run 时从 topic 文件写入，永不修改）
- `CompactState["topic"]`：**LLM 对辩题演进的动态理解**（compact 时由 LLM 生成，随辩论推进更新）

代码注释中应明确区分两者，避免混淆。建议在 `CompactState` TypedDict 的 `topic` 字段注释中写明：`# LLM 生成的辩题演进摘要，非原始辩题文本（原始文本在 log.topic）`

### 8.3 Compact 与 config_override 的交互

<!-- Fix M5: config_override 加入 format_delta_entries_text() 的 tag filter（见 Section 2.4 矩阵） -->
- `config_override` entries 被 `format_delta_entries_text()` 跳过（已有 tag filter 机制，加入 `"config_override"`，详见 Section 2.4 tag filter 矩阵）
- Compact Phase A 的 delta entries 不包含 config_override（纯辩论内容）
- 当 compact 发生在辩手变更后，Phase B 根据当前 effective debaters list（从 resolve_effective_config 获取）决定为哪些辩手更新 stance

<!-- Fix M2: resume 上下文中 _do_compact 的 debaters 来源 -->
**`_do_compact` 在 resume 上下文中的 debaters 来源**：resume 上下文中调用 `_do_compact` 时，应传入 `resolve_effective_config(log)["debaters"]`（即当前有效辩手列表），而非旧的 `cfg["debaters"]`（resume 中不再有外部 cfg 对象）。

<!-- Fix M3: _compact_for_retry 在 v2 下的适配 -->
**`_compact_for_retry` 在 v2 下的适配**：resume 中 TokenLimitError 触发 `_compact_for_retry` 时，该函数同样需要从 log resolve effective debaters。`_compact_for_retry` 应改为接受 `log: Log` 参数，在内部调用 `resolve_effective_config(log)["debaters"]` 获取辩手列表，或明确改为调用 `_do_compact`（统一路径）。若保留现状（不改 `_compact_for_retry`），必须在此处明确说明原因并标注 TODO。

---

## 九、外部编排实现 Phase（使用示例）

无需 runner 改动，完全通过 resume 组合实现：

```bash
# Phase 1: 现象分析 (2 轮)
debate-tool run topic.md --rounds 2 --cross-exam

# Phase 2: 真问题判断 (1 轮)
# phase2.md:
# ---
# rounds: 1
# judge_instructions: "判断哪些现象构成真问题，列出理由和各方分歧"
# middle_task: "基于前面的现象分析，判断是否构成真问题。"
# constraints: "本阶段只做判断，不提解决方案"
# ---
debate-tool resume topic_debate_log.json phase2.md

# Phase 3: 问题分解 (2 轮，加入分析师)
# phase3.md:
# ---
# rounds: 2
# judge_instructions: "评估问题分解的完整性，哪些子问题已充分讨论"
# middle_task: "将已确认的真问题分解为具体的子问题"
# cross_exam: -1
# add_debaters:
#   - name: 分析师
#     model: gpt-5
#     style: "擅长问题分解"
# ---
debate-tool resume topic_debate_log.json phase3.md

# Phase 4: 解决方案 (2 轮，分析师退出)
# phase4.md:
# ---
# rounds: 2
# judge_instructions: "评估各方案的可行性，给出优先级排序和最终建议"
# middle_task: "针对每个子问题提出解决方案，标注优先级"
# drop_debaters:
#   - 分析师
# ---
debate-tool resume topic_debate_log.json phase4.md

# 最终裁定（不追加辩论轮次，只跑 judge）
# final_judge.md:
# ---
# rounds: 0
# judge_instructions: "综合全部讨论，给出最终裁定和行动建议"
# ---
debate-tool resume topic_debate_log.json final_judge.md
```

Orchestrator 脚本可读 summary 后动态决定下一步。

---

## 十、其他文件改动

### 10.1 `scripts/convert_json_log_to_md.py`

- 处理 `config_override` tag：渲染为分割线 + 变更摘要
- 读取 v2 log 的 `topic` 字段，在 md 开头输出辩题

### 10.2 `debate_tool/core.py`

- `FIELD_ORDER` 不变（topic YAML 格式不变）
- `generate_topic_file()` 不变
- 新增辅助函数 `_build_initial_config(cfg) -> dict`（从 parsed cfg 提取 initial_config）

<!-- Fix M6: _build_initial_config 是唯一构建 initial_config 的入口 -->
<!-- Fix C1: base_url 保留，api_key 排除 -->
<!-- Fix H2: compact 配置字段加入 initial_config -->
<!-- Fix L2: middle_task_optional 字段废弃，不写入 initial_config -->
**`_build_initial_config` 是唯一构建 initial_config 的入口**（`run()` 和迁移脚本均调用此函数，不得内联相同逻辑）：

```python
def _build_initial_config(cfg: dict) -> dict:
    """从 parsed topic cfg 构建 v2 log 的 initial_config 快照。

    规则：
    - per-debater base_url 保留（多端点场景必需），api_key 排除
    - judge base_url 保留，api_key 排除
    - 包含 compact 相关配置字段（compact_model 等），未配置则填 null
    - middle_task_optional 字段在 v2 中废弃，不写入（迁移时忽略）
    """
    return {
        "debaters": [
            {k: v for k, v in d.items() if k != "api_key"}
            for d in cfg["debaters"]
        ],
        "judge": {k: v for k, v in cfg["judge"].items() if k != "api_key"},
        "constraints": cfg.get("constraints", ""),
        "round1_task": cfg.get("round1_task", ""),
        "middle_task": cfg.get("middle_task", ""),
        "final_task": cfg.get("final_task", ""),
        "judge_instructions": cfg.get("judge_instructions", ""),
        "max_reply_tokens": cfg.get("max_reply_tokens", 6000),
        "timeout": cfg.get("timeout", 300),
        "cross_exam": cfg.get("cross_exam", 0),
        "early_stop": cfg.get("early_stop", False),
        "cot": cfg.get("cot_length", None),
        # compact 配置：使 compact_log 命令无需外部 topic 文件即可独立运行
        "compact_model": cfg.get("compact_model", None),
        "compact_check_model": cfg.get("compact_check_model", None),
        "compact_max_tokens": cfg.get("compact_max_tokens", None),
        "embedding_model": cfg.get("embedding_model", None),
        # 注意：middle_task_optional 在 v2 中废弃，不写入
    }
```

### 10.3 `template.md`

不变。Topic 文件格式保持不变——它仍然是首次 run 的输入格式。

### 10.4 删除 `modify` 子命令

`debate_tool/__main__.py` 中删除 `modify` 相关路由。`resume` + Resume Topic 文件完全覆盖其功能。

---

## 十一、迁移脚本

新增文件：`scripts/migrate_v1_to_v2.py`

### 功能

<!-- Fix M6: 迁移脚本使用 core._build_initial_config(cfg) 而非内联逻辑 -->
<!-- Fix M4: 迁移时为 compact_checkpoint 中的 ParticipantState 补填 active: True 默认值 -->
<!-- Fix C1: base_url 保留（通过 _build_initial_config 统一处理） -->
接受 topic.md + v1 log.json，输出 v2 log.json：

1. 从 topic 文件解析出 `topic_body`（Markdown 正文）和 cfg
2. 调用 `core._build_initial_config(cfg)` 构建 `initial_config`（唯一入口，确保 base_url 保留、api_key 排除、compact 字段填充）
3. 将 `topic` 和 `initial_config` 注入 log JSON，`version` 改为 `2`
4. **compact_checkpoint 兼容处理**：若 log 中存在 `compact_checkpoint` entry，遍历其 `participants` 列表，为每个 `ParticipantState` 补填 `active: True` 默认值（v1 无此字段，不补填会导致 compact 代码 KeyError）
5. 不修改原文件，输出到新路径（默认 `{stem}_v2.json`，或 `--output` 指定）

### CLI 用法

```bash
python3 scripts/migrate_v1_to_v2.py TOPIC_FILE LOG_FILE [--output OUTPUT]
```

### 示例

```bash
# 默认输出到 my_debate_v2.json
python3 scripts/migrate_v1_to_v2.py topic.md my_debate_debate_log.json

# 指定输出路径
python3 scripts/migrate_v1_to_v2.py topic.md old_log.json --output new_v2_log.json
```

---

## 十二、测试计划

**文件**：`tests/test_runner_json_logs.py`

### 新增测试类

1. **LogSchemaV2Tests**
   - v2 log 写入包含 topic + initial_config
   - v1 log load 报错（提示使用迁移脚本）

2. **ResolveEffectiveConfigTests**
   - 无 override → 返回 initial_config
   - 单次 override → 正确合并
   - 多次 override → 累积合并
   - add_debaters + drop_debaters → 正确增减
   - judge override → 正确替换

3. **ResumeCLITests**
   - 单文件模式（新 CLI）
   - --rounds 0 → judge-only（不追加辩论轮次但 judge 仍执行）
   - Resume Topic 文件解析测试
   - Resume Topic + LOG 组合测试
   - Resume Topic body 作为 message 注入测试

4. **ResumeIntegrationTests**（mock call_llm）
   - resume with Resume Topic middle_task → debater prompt 包含自定义 task
   - resume with add_debaters → 新辩手参与发言
   - resume with drop_debaters → 被移除辩手不发言
   - config_override entry 正确写入 log
   - 多次 resume → effective config 累积正确

5. **MigrationScriptTests**
   - topic + v1 log → v2 log 转换正确（包含 topic 和 initial_config，version == 2）
   - `api_key` 被排除，不出现在 v2 log 的 initial_config 中；`base_url` 保留且正确存在于 initial_config <!-- Fix r2-NEW-2: 正确区分 base_url 保留 vs api_key 排除，与 Section 1.1 关键约束及 _build_initial_config 实现一致 -->
   - 缺少 topic 文件报错

6. **ResumeTopicParseTests**
   - YAML front-matter 解析正确
   - body 提取为 message
   - 缺少 body → message 为空
   - add_debaters / drop_debaters 正确解析
   - 运行控制字段(rounds, guide)与 config override 字段正确分离

---

## 十三、文件影响总览

<!-- Fix H2: 加入 compact_log 相关改动说明 -->
<!-- Fix L7: parse_resume_topic 内联于 runner.py，不单独建文件 -->
| 文件 | 改动性质 |
|------|----------|
| `debate_tool/runner.py` | Log 类 v2、`all_entries()` 公开方法、resolve_effective_config、`_describe_overrides`/`_apply_overrides`、run() 存 topic+config、resume() 重构、validate 放宽、**`parse_resume_topic()` 内联于此文件** |
| `debate_tool/__main__.py` | resume CLI 重构（单文件 + 可选 Resume Topic）、删除 modify 子命令、**删除 `--no-judge` 参数** |
| `debate_tool/core.py` | `_build_initial_config()` 辅助函数（唯一入口，包含 compact 配置字段） |
| `debate_tool/compact_state.py` | ParticipantState.active 字段、filter 适配（config_override tag 排除）、**compact_log 命令适配（从 log.initial_config 读取 compact 配置，无需外部 topic 文件）** |
| `scripts/convert_json_log_to_md.py` | config_override 渲染、v2 topic 输出 |
| `tests/test_runner_json_logs.py` | 6 个新测试类 |
| `scripts/migrate_v1_to_v2.py` | v1 → v2 迁移脚本（含 compact_checkpoint ParticipantState active 字段补填） |
| ~~`debate_tool/resume_topic.py`~~ | **不创建**：`parse_resume_topic()` 内联于 `runner.py` |

---

## 十四、验证方式

<!-- Fix H3: 将 Section 十四验证步骤 3-4 的 --task/--add-debater/--drop-debater 示例改为 Resume Topic 文件方式 -->

1. **现有测试全过**：`python3 -m pytest tests/ -v`
2. **v2 基本流程**：
   - `run topic.md` → 检查 log.json 包含 `topic` 和 `initial_config` 字段
   - `resume log.json --rounds 1` → 无需 topic 文件，正常续跑
3. **Config override（Resume Topic 文件方式）**：
   - 创建 `override_test.md`（front-matter 含 `middle_task: "新任务"`）
   - `resume log.json override_test.md` → 检查 log 中有 `config_override` entry，debater prompt 包含 "新任务"
   - 再次 `resume log.json --rounds 1`（不指定 Resume Topic 文件）→ 沿用上次的 "新任务"（累积）
4. **辩手增减（Resume Topic 文件方式）**：
   - 创建 `add_debater_test.md`（front-matter 含 `add_debaters: [{name: C, model: gpt-5, style: 中立}]`）
   - `resume log.json add_debater_test.md` → 新辩手 C 参与发言
   - 创建 `drop_debater_test.md`（front-matter 含 `drop_debaters: [A]`）
   - `resume log.json drop_debater_test.md` → A 不参与
5. **Phase 编排**：执行「九、外部编排实现 Phase」中的完整流程
6. **迁移脚本**：
   - `python3 scripts/migrate_v1_to_v2.py topic.md v1_log.json` → 输出 v2 log，包含 topic + initial_config，version == 2
   - v1 log 直接 `resume` → 报错并提示使用迁移脚本
