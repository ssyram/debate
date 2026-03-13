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
    "debaters": [{"name": "A", "model": "gpt-5", "style": "支持X"}],
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
    "cot": null
  },
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp",
  "entries": [...]
}
```

**关键约束**：
- `topic` 字段只写一次，不可变（= 辩论的 Identity）
- `initial_config` 不包含 `base_url` / `api_key`（API 凭证始终从 env / .env 注入，不持久化到 log）
- `initial_config` 是首次 run 时的快照，后续 resume 通过 `config_override` entries 演化

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

**新增函数**：`resolve_effective_config(log) -> dict`

```python
def resolve_effective_config(log: Log) -> dict:
    """从 log 的 initial_config + 所有 config_override entries 合并出当前有效配置。"""
    cfg = deepcopy(log.initial_config)
    for entry in log.all_entries():
        if entry.get("tag") != "config_override":
            continue
        overrides = entry.get("overrides", {})
        # 辩手增减
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
    all_entries = self._all_entries()
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

### 2.3 `load_from_file()` 支持 v1/v2

```python
@classmethod
def load_from_file(cls, path: Path) -> "Log":
    payload, all_entries = _load_json_log_payload(path)
    log = cls(
        path,
        payload["title"],
        topic=payload.get("topic", ""),               # v2 字段，v1 为空
        initial_config=payload.get("initial_config", {}),  # v2 字段，v1 为空
    )
    # ... checkpoint 恢复逻辑不变
```

### 2.4 `since()` 排除新 tag

在 exclude set 中加入 `"config_override"`（配置变更不应出现在辩手上下文中）。

---

## 三、`run()` 函数改动

**文件**：`debate_tool/runner.py` — `async def run()` (line 1790)

### 3.1 创建 Log 时注入 topic + initial_config

当前 (line 1796 附近)：
```python
log = Log(log_path, title)
```

改为：
```python
# 构建 initial_config（排除 API 凭证）
initial_config = {
    "debaters": [
        {k: v for k, v in d.items() if k not in ("base_url", "api_key")}
        for d in cfg["debaters"]
    ],
    "judge": {k: v for k, v in cfg["judge"].items() if k not in ("base_url", "api_key")},
    "constraints": cfg["constraints"],
    "round1_task": cfg["round1_task"],
    "middle_task": cfg["middle_task"],
    "final_task": cfg["final_task"],
    "judge_instructions": cfg.get("judge_instructions", ""),
    "max_reply_tokens": cfg["max_reply_tokens"],
    "timeout": cfg["timeout"],
    "cross_exam": cfg.get("cross_exam", 0),
    "early_stop": cfg.get("early_stop", False),
    "cot": cfg.get("cot_length", None),
}

log = Log(log_path, title, topic=cfg["topic_body"], initial_config=initial_config)
```

run() 其余逻辑不变 — 仍然使用 `cfg` 驱动循环（第一次 run 不经过 resolve_effective_config）。

---

## 四、`resume()` 函数重构（核心改动）

**文件**：`debate_tool/runner.py` — `async def resume()` (line 2115-2391)

### 4.1 新签名

```python
async def resume(
    *,
    log_path: Path,
    # 可选：v1 log 或首次 bootstrap 时需要
    topic_path: Path | None = None,
    cfg_overrides: dict | None = None,      # 新增：结构化 config overrides
    # 保留现有参数
    message: str = "",
    extra_rounds: int = 1,
    cross_exam: int | None = None,          # None = 沿用 effective config
    guide_prompt: str = "",
    judge_at_end: bool = True,
    force: bool = False,
    cot_length: int | None = None,          # None = 沿用 effective config
) -> None:
```

### 4.2 Config 解析流程

```python
log = Log.load_from_file(log_path)

# 1. 获取 topic（辩题）
if log.topic:
    topic = log.topic  # v2 log：从 log 读
elif topic_path:
    fallback_cfg = parse_topic_file(topic_path)
    topic = fallback_cfg["topic_body"]
    # 补存到 log（升级 v1 → v2）
    log.topic = topic
    log.initial_config = _build_initial_config(fallback_cfg)
else:
    print("❌ v1 日志需要提供 topic 文件", file=sys.stderr)
    sys.exit(1)

# 2. 解析 effective config（initial + 历史 overrides）
eff_cfg = resolve_effective_config(log)

# 3. 应用本次 CLI overrides
if cfg_overrides:
    # 记录到 log
    desc = _describe_overrides(cfg_overrides)  # 生成人类可读摘要
    log.add("@系统", desc, "config_override", extra={"overrides": cfg_overrides})
    # 合并
    _apply_overrides(eff_cfg, cfg_overrides)

# 4. CLI 参数覆盖对应字段
if cross_exam is not None:
    eff_cfg["cross_exam"] = cross_exam
if cot_length is not None:
    eff_cfg["cot"] = cot_length

# 5. 注入 API 凭证（始终从 env）
debate_base_url = (eff_cfg.get("base_url", "") or ENV_BASE_URL).strip()
debate_api_key = (eff_cfg.get("api_key", "") or ENV_API_KEY).strip()

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

新增 `extra_rounds=0` 支持（当前 range(1, 1) 不执行循环，直接到 judge）。用于外部编排在最后一步只出 summary。

---

## 五、Resume CLI 改动

**文件**：`debate_tool/__main__.py` — `_handle_resume()` (line 36-120)

### 5.1 新 CLI 接口

```
debate-tool resume LOG_FILE [options]

位置参数:
  LOG_FILE                日志文件（必需）

兼容:
  --topic TOPIC_FILE      Topic 文件（v1 日志必需，v2 可选）

运行控制:
  --rounds N              追加轮数 (默认 1, 0=仅裁判)
  --no-judge              跳过裁判
  --judge-only            等价于 --rounds 0

Config 覆盖 (记录为 config_override entry):
  --task TEXT             覆盖 middle_task
  --constraint TEXT       替换 constraints
  --add-constraint TEXT   追加 constraint

辩手管理 (记录为 config_override entry):
  --add-debater "name|model|style"   添加辩手
  --drop-debater NAME                移除辩手

消息注入:
  --message TEXT          观察者消息
  --guide TEXT            辩手引导

其他:
  --cross-exam [N]        质询频率
  --cot [LENGTH]          CoT
  --force                 跳过校验
```

### 5.2 向后兼容

旧 `debate-tool resume FILE_A FILE_B` 两文件模式保留。检测：传了两个文件 → 旧模式（auto-identify log vs topic）。

---

## 六、`_load_json_log_payload()` 兼容 v1/v2

**文件**：`debate_tool/runner.py` — `_load_json_log_payload()` (line 316-340)

增加对 v2 字段的透传。v1 log（无 topic / initial_config）在 load 时这些字段为空/None，resume 时检测到空则要求提供 topic 文件。

---

## 七、`validate_topic_log_consistency()` 放宽

**文件**：`debate_tool/runner.py` — line 2770-2833

当前：debater name 不匹配就 exit（除非 --force）。

改为：
- **不再 exit**：打印 warning 说明辩手变更情况
- **记录变更**：列出新增/移除的辩手
- 如果有 `config_override` entry 显式记录了 add/drop_debaters，则视为合法变更，不 warn

`check_topic_log_consistency_with_llm()` 也需适配：topic 从 log.topic 读而非 cfg。

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

### 8.3 Compact 与 config_override 的交互

- `config_override` entries 被 `format_delta_entries_text()` 跳过（已有 tag filter 机制，加入 `"config_override"`）
- Compact Phase A 的 delta entries 不包含 config_override（纯辩论内容）
- 当 compact 发生在辩手变更后，Phase B 根据当前 effective debaters list（从 resolve_effective_config 获取）决定为哪些辩手更新 stance

---

## 九、外部编排实现 Phase（使用示例）

无需 runner 改动，完全通过 resume 组合实现：

```bash
# Phase 1: 现象分析 (2 轮)
debate-tool run topic.md --rounds 2 --no-judge --cross-exam

# Phase 2: 真问题判断 (1 轮)
debate-tool resume topic_debate_log.json \
  --task "基于前面的现象分析，判断是否构成真问题。" \
  --constraint "本阶段只做判断，不提解决方案" \
  --rounds 1 --no-judge

# Phase 3: 问题分解 (2 轮，加入分析师)
debate-tool resume topic_debate_log.json \
  --task "将已确认的真问题分解为具体的子问题" \
  --add-debater "分析师|gpt-5|擅长问题分解" \
  --rounds 2 --no-judge --cross-exam

# Phase 4: 解决方案 (2 轮，分析师退出)
debate-tool resume topic_debate_log.json \
  --task "针对每个子问题提出解决方案，标注优先级" \
  --drop-debater "分析师" \
  --rounds 2

# 仅裁判（不再跑轮次）
debate-tool resume topic_debate_log.json --judge-only
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
- 新增辅助函数 `_build_initial_config(cfg) -> dict`（从 parsed cfg 提取 initial_config，排除 API 凭证）

### 10.3 `template.md`

不变。Topic 文件格式保持不变——它仍然是首次 run 的输入格式。

---

## 十一、向后兼容

| 场景 | 行为 |
|------|------|
| v1 log + topic 文件 resume | 正常工作（topic 从文件读，首次 resume 时 log 升级为 v2） |
| v1 log 无 topic 文件 resume | 报错提示需要 topic 文件 |
| v2 log 无 topic 文件 resume | 正常工作（topic 从 log 读） |
| v2 log + topic 文件 resume | topic 文件被忽略（log.topic 优先），打印提示 |
| 旧 CLI `resume FILE_A FILE_B` | 兼容：自动识别 log vs topic |
| 新 CLI `resume LOG_FILE` | 新模式：单文件 |

---

## 十二、测试计划

**文件**：`tests/test_runner_json_logs.py`

### 新增测试类

1. **LogSchemaV2Tests**
   - v2 log 写入包含 topic + initial_config
   - v1 log load 后 topic/initial_config 为空
   - v1→v2 升级（resume 时自动填充）

2. **ResolveEffectiveConfigTests**
   - 无 override → 返回 initial_config
   - 单次 override → 正确合并
   - 多次 override → 累积合并
   - add_debaters + drop_debaters → 正确增减
   - judge override → 正确替换

3. **ResumeCLITests**
   - 单文件模式（新 CLI）
   - 两文件模式（向后兼容）
   - --task / --constraint / --add-debater 映射到 cfg_overrides
   - --judge-only → extra_rounds=0

4. **ResumeIntegrationTests**（mock call_llm）
   - resume with --task → debater prompt 包含自定义 task
   - resume with --add-debater → 新辩手参与发言
   - resume with --drop-debater → 被移除辩手不发言
   - config_override entry 正确写入 log
   - 多次 resume → effective config 累积正确

---

## 十三、文件影响总览

| 文件 | 改动性质 |
|------|----------|
| `debate_tool/runner.py` | Log 类 v2、resolve_effective_config、run() 存 topic+config、resume() 重构、validate 放宽 |
| `debate_tool/__main__.py` | resume CLI 重构（单文件 + 新参数）、向后兼容两文件 |
| `debate_tool/core.py` | `_build_initial_config()` 辅助函数 |
| `debate_tool/compact_state.py` | ParticipantState.active 字段、filter 适配 |
| `scripts/convert_json_log_to_md.py` | config_override 渲染、v2 topic 输出 |
| `tests/test_runner_json_logs.py` | 4 个新测试类 |

---

## 十四、验证方式

1. **现有测试全过**：`python3 -m pytest tests/ -v`
2. **v1 兼容**：用旧 topic 文件 `run` 再 `resume FILE_A FILE_B` → 行为不变
3. **v2 基本流程**：
   - `run topic.md` → 检查 log.json 包含 `topic` 和 `initial_config` 字段
   - `resume log.json --rounds 1` → 无需 topic 文件，正常续跑
4. **Config override**：
   - `resume log.json --task "新任务"` → 检查 log 中有 `config_override` entry，debater prompt 包含 "新任务"
   - 再次 `resume log.json --rounds 1`（不指定 --task）→ 沿用上次的 "新任务"（累积）
5. **辩手增减**：
   - `resume log.json --add-debater "C|gpt-5|中立"` → 新辩手参与
   - `resume log.json --drop-debater "A"` → A 不参与
6. **Phase 编排**：执行「九、外部编排实现 Phase」中的完整流程
