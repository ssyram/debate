# debate-tool Compact 输出设计：压缩后辩手应该看到什么？ 裁判总结

> 2026-03-12T15:47:56.343200

# 裁判裁定书

## 一、关键设计分歧裁定

### A. Compact 输出区块：最终采用哪些区块？各区块职责和优先级？

**裁定：采纳康德第三轮提出的「v1 最低必要集 4 块」方案，但补入 Ssyram 的强类型约束。**

理由：三位辩手在最终轮次已高度收敛。Linus 和康德的完整 schema 包含 timeline_brief、open_questions、assumptions、admitted_weaknesses 等字段，但康德在第15条中正确指出：v1 只需要 4 个刚需区块即可同时满足「思路延续」和「防回滚打转」两个核心目标。过早堆字段会增加 LLM 填表出错率，且每个多余字段都是 token 开销。

**v1 必须包含的 4 个区块（按优先级排序）：**

| 优先级 | 区块 | 职责 | Token 预算占比 |
|--------|------|------|---------------|
| 1 | `participants`（立场卡，含 abandoned_claims） | 替代原始立场描述，告诉辩手「你现在站在哪」 | 40% |
| 2 | `disputes`（当前争点） | 搜索前沿，告诉辩手「下一步该攻哪」 | 25% |
| 3 | `axioms`（已达成共识） | 逻辑基座，不可再争 | 15% |
| 4 | `pruned_paths`（被否决路径） | 负向硬约束，防止打转 | 20% |

`topic` 作为元数据始终存在但不计入 token 预算。`timeline_brief`、`open_questions`、`assumptions` 等留给 v2。

---

### B. LLM 摘要流程：自动 compact 时的模型选择策略？是否需要主动 compact？

**裁定：采纳 Ssyram 的「主动阈值触发」，但拒绝其三步拆分方案；采用单次 LLM 调用 + Python 后校验。**

理由：

1. **主动 vs 被动**：Ssyram 在第2条中正确指出「等到 token 溢出再 compact 时上下文已经脏了」。应在 `current_tokens > threshold * max_tokens`（建议 threshold=0.7）时主动触发，而非等到溢出。这一点 Linus 和康德均未反对。

2. **单次调用 vs 多步拆分**：这是本次辩论最尖锐的分歧。Linus 提议 A/B/C 三步填表，Ssyram 在第11条和第14条中猛烈攻击其「参照完整性破坏」问题——如果调用 A 将 Dispute D1 标记为 resolved，但调用 B 仍在 Player A 的 core_claims 中保留针对 D1 的激进主张，合并时就会产生悬空指针。**Ssyram 的攻击成立。** 在没有复杂的事务性合并逻辑的情况下，拆分调用的一致性风险远大于单次调用的 token 开销。

   **裁定方案**：单次 LLM 调用生成完整的 `CompactState` JSON，然后由 Python 代码做后校验（schema 校验 + 交叉引用检查）。如果校验失败，重试（最多 2 次），而非降级。

3. **模型选择**：compact 调用应使用与辩手相同或更强的模型。如果辩手用 GPT-4o，compact 也用 GPT-4o；如果辩手用 Claude Sonnet，compact 可用 Claude Sonnet 或 Opus。不应降级到弱模型做摘要——这是 Linus 在第4条中隐含建议的，我明确反对。状态提取的质量直接决定后续辩论质量。

---

### C. 增量压缩：增量 merge vs 全量重建？Checkpoint 结构的最小 metadata 集合？

**裁定：严格增量。`S_n = f(S_{n-1}, Δ_n)`，拒绝全量重建。**

理由：这是三位辩手唯一完全一致的结论。Ssyram 在第2条中最先形式化了这一点，Linus 在第4条中明确赞同，康德在第6条中也采纳。全量重建会导致「摘要的摘要的摘要」，语义漂移不可控。

**增量更新的具体含义**：
- LLM 的输入是：`prev_state`（上一次的 CompactState JSON）+ `delta_entries`（自上次 checkpoint 以来的原始对话文本）
- LLM 的输出是：新的 `CompactState` JSON
- LLM **不会看到** checkpoint 之前的原始对话

**最小 metadata 集合**：
```python
{
    "compact_version": int,        # schema 版本号
    "covered_seq_end": int,        # 本次 compact 覆盖到的最后一条 log entry 的 seq
    "prev_compact_seq": int | None # 上一次 compact checkpoint 的 seq（用于链式追溯）
}
```

**关于 Ssyram 的「失败时 block 而非降级」**：我部分采纳。compact 失败时应重试（最多 2 次，可切换备用 API endpoint）。如果仍然失败，**不降级为文本截断**（Ssyram 在第14条中正确指出这会导致因果链断裂），而是保留上一次的 `CompactState` 不变，将新增 entries 作为原始文本追加在 markdown 视图之后。这不是「降级」，而是「延迟 compact」——state 仍然是上一次的合法状态，只是 delta 暂时未被吸收。下次 compact 时 delta 会更大，但状态链不会断。

---

### D. 演进表示：changelog vs 立场快照 vs 其他？被抛弃路径的控制策略？

**裁定：立场快照为主体，changelog 不进入 v1。被抛弃路径采用 Ssyram 的「单调递增」约束。**

理由：

1. **立场快照 vs changelog**：Linus 在第1条中提出了详细的「立场演进时间线」，康德在第3条中也有 timeline_brief。但康德在第15条中自己做了减法——v1 不需要 timeline。我同意。辩手需要的是「当前棋盘」而非「棋谱」。如果辩手需要理解「为什么立场变了」，`abandoned_claims` 中的 `reason` 字段已经足够。完整的演进轨迹是 v2 的事。

2. **被抛弃路径的控制策略**：Ssyram 在第14条中提出 `pruned_paths` 和 `abandoned_claims` 必须**单调递增，禁止删除**。这是正确的——从 CEGAR 的视角看，删除一个负向约束等于重新打开一条已被证伪的路径。

   但 Linus 在第7条中提出的「pruned_paths 只保留最近 M 个，更早的合成概括性描述」也有工程合理性——无限增长的列表最终会吃光 token。

   **折中裁定**：`pruned_paths` 单调递增，但当条目超过 10 条时，允许将最早的条目**合并**（多条合并为一条更抽象的描述），但**不允许删除**。合并后的条目标记 `"merged": true`，保留所有被合并条目的 ID 列表。这样既保持单调性，又控制 token。

3. **在辩手 prompt 中的呈现方式**：采纳 Ssyram 的建议——`pruned_paths` 在 Markdown 视图中必须以**禁止指令**的口吻出现（「以下路径已被否决，不得以任何变体形式重新提出」），而非历史回顾（「曾经讨论过以下路径」）。

---

## 二、推荐的 Compact 方案

### 2.1 CompactState Python 数据结构

```python
from typing import TypedDict, List, Literal, Optional

class Claim(TypedDict):
    id: str                          # e.g. "A1", "B2"
    text: str
    status: Literal["active", "abandoned"]

class Argument(TypedDict):
    id: str                          # e.g. "A1-arg1"
    claim_id: str                    # 关联的 claim
    text: str
    status: Literal["active", "weakened", "refuted"]

class AbandonedClaim(TypedDict):
    id: str
    original_text: str
    reason: str
    decided_by: Literal["self", "opponent", "judge", "consensus"]

class ParticipantState(TypedDict):
    name: str
    stance_version: int
    one_line_position: str
    core_claims: List[Claim]
    key_arguments: List[Argument]
    abandoned_claims: List[AbandonedClaim]  # 单调递增，不可删除

class Dispute(TypedDict):
    id: str                          # e.g. "D1"
    title: str                       # 一句话描述争点
    status: Literal["open", "resolved"]
    positions: dict                  # { "辩手A": "A的立场", "辩手B": "B的立场" }
    resolution: Optional[str]        # 如果 resolved，简述结论

class PrunedPath(TypedDict):
    id: str                          # e.g. "P1"
    description: str                 # 被否决的论证路径
    reason: str                      # 为什么走不通
    decided_by: str                  # 谁否决的
    merged: bool                     # 是否为合并条目
    merged_from: Optional[List[str]] # 如果是合并条目，原始 ID 列表

class CompactState(TypedDict):
    compact_version: int             # schema 版本，当前为 1
    covered_seq_end: int             # 覆盖到的最后一条 entry seq
    prev_compact_seq: Optional[int]  # 上一次 compact 的 seq

    topic: dict                      # { "current_formulation": str, "notes": str? }

    participants: List[ParticipantState]
    axioms: List[str]                # 已达成共识，不可再争
    disputes: List[Dispute]
    pruned_paths: List[PrunedPath]   # 单调递增


class CompactCheckpointContent(TypedDict):
    state: CompactState
    view: str                        # 渲染给辩手的 Markdown
```

### 2.2 LLM 摘要 Prompt 的关键指令

```
你是辩论状态提取器。你的任务是将辩论的当前状态更新为结构化 JSON。

## 输入
1. 上一次的辩论状态（CompactState JSON）：
{prev_state_json}

2. 自上次状态以来的新增对话：
{delta_entries_text}

## 输出要求
输出一个更新后的 CompactState JSON，严格遵循以下 schema：
{schema_description}

## 更新规则（必须严格遵守）

### 单调性约束
- `abandoned_claims`：只能新增，不能删除或修改已有条目。
- `pruned_paths`：只能新增，不能删除。如果条目超过 10 条，将最早的 2-3 条合并为一条更抽象的描述，设置 merged=true 并记录 merged_from。
- `axioms`：只能新增，不能删除。一旦双方达成共识，该共识不可撤回。

### 立场卡更新
- 如果辩手在新对话中修改了立场，更新 `core_claims` 和 `key_arguments`，并递增 `stance_version`。
- 如果辩手放弃了某个主张，将其从 `core_claims` 中标记为 `abandoned`，同时在 `abandoned_claims` 中新增一条记录。
- 不要凭空创造辩手没有表达过的立场。

### 争点更新
- 如果新对话中出现了新的争议焦点，新增 Dispute 条目。
- 如果某个争点在新对话中被解决（双方达成一致或一方明确让步），将其标记为 `resolved` 并填写 `resolution`。
- 已 resolved 的争点不可重新打开。

### 剪枝路径
- 如果新对话中某条论证路径被明确否决（被对方反驳且提出方未能有效回应，或提出方自行放弃），新增 `pruned_paths` 条目。

### 共识
- 如果双方在新对话中明确同意某个事实或前提，新增 `axioms` 条目。

## 输出格式
仅输出 JSON，不要包含任何解释文字。
```

### 2.3 触发流程描述

```
1. 每次辩手发言后，计算当前上下文 token 数
2. 如果 current_tokens > 0.7 * max_context_tokens：
   a. 收集 prev_state（上一次 compact 的 CompactState，如果是首次则为 null）
   b. 收集 delta_entries（自 prev_compact_seq 以来的所有 log entries）
   c. 调用 LLM（使用与辩手同级或更强的模型），输入 prev_state + delta_entries，要求输出新的 CompactState JSON
   d. Python 后校验：
      - JSON schema 校验（所有必填字段存在、类型正确）
      - 单调性校验：new.abandoned_claims ⊇ prev.abandoned_claims
      - 单调性校验：new.pruned_paths ⊇ prev.pruned_paths（按 id 检查）
      - 单调性校验：new.axioms ⊇ prev.axioms
      - 交叉引用校验：key_arguments 中的 claim_id 必须存在于 core_claims 中
      - disputes 中 resolved 的不可变回 open
   e. 如果校验失败：重试（最多 2 次）。如果仍失败：保留上一次 state 不变，新增 entries 以原文追加在 view 末尾（延迟 compact）
   f. 校验通过：渲染 Markdown view，写入 compact_checkpoint entry
3. 后续辩手的上下文构造：
   - system prompt 中注入：「你收到的是辩论状态快照，不是聊天记录。在此基础上继续推进，不要重开已解决的问题或重复已被否决的路径。」
   - 上下文 = state.view（Markdown）+ compact 之后的新增 entries（如果有的话）
```

### 2.4 Mock Compact 输出示例

**场景**：3 轮辩论，议题「AI 是否应该拥有法律人格」，辩手 A（支持）vs 辩手 B（反对）。

**CompactState JSON**：
```json
{
  "compact_version": 1,
  "covered_seq_end": 12,
  "prev_compact_seq": null,

  "topic": {
    "current_formulation": "AI 系统是否应被赋予独立的法律人格（类似公司法人）？",
    "notes": "双方已同意讨论范围限于民事责任领域，不涉及刑事责任"
  },

  "participants": [
    {
      "name": "辩手A（支持方）",
      "stance_version": 2,
      "one_line_position": "AI 应被赋予有限法律人格，以解决自主决策场景下的责任归属真空",
      "core_claims": [
        {"id": "A1", "text": "当 AI 自主做出决策时，现有法律框架无法合理归责给开发者或用户", "status": "active"},
        {"id": "A2", "text": "公司法人制度证明非自然人实体可以有效承担法律责任", "status": "active"},
        {"id": "A3", "text": "AI 具有完全的道德主体地位", "status": "abandoned"}
      ],
      "key_arguments": [
        {"id": "A1-arg1", "claim_id": "A1", "text": "自动驾驶事故中，当算法做出人类无法预见的决策时，追究程序员的过失责任在法理上不成立", "status": "active"},
        {"id": "A2-arg1", "claim_id": "A2", "text": "公司法人不具备意识但可以签约、被诉、承担赔偿，AI 法律人格可参照此模式", "status": "active"}
      ],
      "abandoned_claims": [
        {
          "id": "A-ab1",
          "original_text": "AI 具有完全的道德主体地位，因此应有法律人格",
          "reason": "B 指出道德主体地位要求意识和自由意志，当前 AI 不具备；A 承认此论据过强，转为'功能性法律人格'立场",
          "decided_by": "self"
        }
      ]
    },
    {
      "name": "辩手B（反对方）",
      "stance_version": 2,
      "one_line_position": "不应赋予 AI 法律人格，应通过扩展现有产品责任和代理法来解决归责问题",
      "core_claims": [
        {"id": "B1", "text": "法律人格的本质是权利与义务的对等，AI 无法真正'承担'义务", "status": "active"},
        {"id": "B2", "text": "产品责任法 + 强制保险制度足以覆盖 AI 造成的损害", "status": "active"}
      ],
      "key_arguments": [
        {"id": "B1-arg1", "claim_id": "B1", "text": "公司法人背后有自然人股东承担最终责任，AI 法人背后没有对等的责任主体", "status": "active"},
        {"id": "B2-arg1", "claim_id": "B2", "text": "欧盟 AI Act 已采用风险分级+强制保险的路径，无需引入法律人格", "status": "active"}
      ],
      "abandoned_claims": []
    }
  ],

  "axioms": [
    "讨论范围限于民事责任领域",
    "当前 AI 系统不具备意识或自由意志",
    "确实存在 AI 自主决策场景下的责任归属困难"
  ],

  "disputes": [
    {
      "id": "D1",
      "title": "公司法人类比是否成立",
      "status": "open",
      "positions": {
        "辩手A": "公司法人证明非自然人可承担法律责任，AI 可参照",
        "辩手B": "公司法人背后有自然人兜底，AI 没有，类比不成立"
      },
      "resolution": null
    },
    {
      "id": "D2",
      "title": "现有法律框架是否足以解决归责问题",
      "status": "open",
      "positions": {
        "辩手A": "产品责任法无法覆盖 AI 自主决策的场景",
        "辩手B": "扩展产品责任法+强制保险即可，无需新概念"
      },
      "resolution": null
    }
  ],

  "pruned_paths": [
    {
      "id": "P1",
      "description": "通过论证 AI 具有道德主体地位来支持法律人格",
      "reason": "双方已同意当前 AI 不具备意识和自由意志，道德主体论据不成立",
      "decided_by": "consensus",
      "merged": false,
      "merged_from": null
    }
  ]
}
```

**渲染给辩手的 Markdown View**：

```markdown
# 辩论压缩快照 v2（覆盖至第 12 条发言）

## 1. 当前议题
AI 系统是否应被赋予独立的法律人格（类似公司法人）？
> 范围限定：仅讨论民事责任领域，不涉及刑事责任。

## 2. 辩手立场卡

### 辩手A（支持方）—— 立场版本 2
**一句话立场**：AI 应被赋予有限法律人格，以解决自主决策场景下的责任归属真空。

当前核心主张：
1. [A1] 当 AI 自主做出决策时，现有法律框架无法合理归责给开发者或用户
2. [A2] 公司法人制度证明非自然人实体可以有效承担法律责任

关键论据：
- [A1-arg1] 自动驾驶事故中，当算法做出人类无法预见的决策时，追究程序员的过失责任在法理上不成立
- [A2-arg1] 公司法人不具备意识但可以签约、被诉、承担赔偿，AI 法律人格可参照此模式

已放弃的主张（不得以任何变体重新提出）：
- ~~[A3] AI 具有完全的道德主体地位~~ → 自行放弃。原因：B 指出道德主体地位要求意识和自由意志，A 承认论据过强，已转向"功能性法律人格"。

### 辩手B（反对方）—— 立场版本 2
**一句话立场**：不应赋予 AI 法律人格，应通过扩展现有产品责任和代理法来解决归责问题。

当前核心主张：
1. [B1] 法律人格的本质是权利与义务的对等，AI 无法真正"承担"义务
2. [B2] 产品责任法 + 强制保险制度足以覆盖 AI 造成的损害

关键论据：
- [B1-arg1] 公司法人背后有自然人股东承担最终责任，AI 法人背后没有对等的责任主体
- [B2-arg1] 欧盟 AI Act 已采用风险分级+强制保险的路径，无需引入法律人格

## 3. 已达成共识（不可再争）
1. 讨论范围限于民事责任领域
2. 当前 AI 系统不具备意识或自由意志
3. 确实存在 AI 自主决策场景下的责任归属困难

## 4. 当前争点

| ID | 争点 | 状态 |
|----|------|------|
| D1 | 公司法人类比是否成立 | 🔴 开放 |
| D2 | 现有法律框架是否足以解决归责问题 | 🔴 开放 |

**D1 双方立场**：
- A：公司法人证明非自然人可承担法律责任，AI 可参照
- B：公司法人背后有自然人兜底，AI 没有，类比不成立

**D2 双方立场**：
- A：产品责任法无法覆盖 AI 自主决策的场景
- B：扩展产品责任法+强制保险即可，无需新概念

## 5. 已否决路径（⛔ 禁止以任何变体形式重新提出）
- **[P1]** 通过论证 AI 具有道德主体地位来支持法律人格
  → 否决原因：双方已同意当前 AI 不具备意识和自由意志，道德主体论据不成立。
```

---

## 三、实现路线图

### 3.1 需要新增的文件

**`src/debate/compact_schema.py`**
- 定义 `CompactState`、`ParticipantState`、`Claim`、`Argument`、`AbandonedClaim`、`Dispute`、`PrunedPath`、`CompactCheckpointContent` 等 TypedDict（或 Pydantic model）
- 实现 `validate_compact_state(state: dict) -> tuple[bool, list[str]]`：schema 校验 + 单调性校验 + 交叉引用校验
- 实现 `render_markdown_view(state: CompactState) -> str`：从 state 渲染 Markdown
- 接口签名：
  ```python
  def validate_compact_state(
      new_state: dict, 
      prev_state: Optional[dict] = None
  ) -> tuple[bool, list[str]]:
      """返回 (is_valid, error_messages)。prev_state 用于单调性检查。"""
  
  def render_markdown_view(state: dict) -> str:
      """将 CompactState 渲染为辩手可读的 Markdown。"""
  ```

### 3.2 需要修改的文件

**`src/debate/compact.py`**（核心修改）
- 修改 `compact_log()` 或等价函数：
  - 输入变更：接收 `prev_state: Optional[CompactState]` + `delta_entries: list[LogEntry]`（而非全部历史）
  - LLM 调用：使用上述 prompt 模板，要求输出 JSON
  - 输出变更：返回 `CompactCheckpointContent`（包含 `state` + `view`）
  - 新增后校验逻辑：调用 `validate_compact_state(new_state, prev_state)`
  - 新增重试逻辑：校验失败时重试最多 2 次
  - 新增延迟 compact 逻辑：重试仍失败时，保留 prev_state，将 delta 原文追加到 view 末尾
  - 关键逻辑：
    ```python
    async def compact_log(
        prev_state: Optional[CompactState],
        delta_entries: list[LogEntry],
        model: str,
        max_retries: int = 2
    ) -> CompactCheckpointContent:
        prompt = build_compact_prompt(prev_state, delta_entries)
        for attempt in range(max_retries + 1):
            raw_json = await call_llm(prompt, model=model, response_format="json")
            new_state = json.loads(raw_json)
            valid, errors = validate_compact_state(new_state, prev_state)
            if valid:
                view = render_markdown_view(new_state)
                return {"state": new_state, "view": view}
        # 所有重试失败：延迟 compact
        fallback_view = render_markdown_view(prev_state) + "\n\n---\n## 未压缩的最新对话\n" + format_entries(delta_entries)
        return {"state": prev_state, "view": fallback_view}
    ```

**`src/debate/context.py`**（或构造辩手上下文的模块）
- 修改上下文构造逻辑：
  - 如果存在 compact checkpoint，使用 `checkpoint.content["view"]` 替代原始对话历史
  - 使用 `checkpoint.content["state"]["topic"]["current_formulation"]` 替代原始 topic
  - 使用 `checkpoint.content["state"]["participants"]` 中对应辩手的立场卡替代原始立场描述
  - 在 system prompt 中注入：「你收到的是辩论状态快照。在此基础上继续推进。已否决路径部分列出的论证路径不得以任何变体形式重新使用。」

**`src/debate/manager.py`**（或辩论流程控制模块）
- 新增 compact 触发逻辑：
  ```python
  def should_compact(current_tokens: int, max_tokens: int, threshold: float = 0.7) -> bool:
      return current_tokens > threshold * max_tokens
  ```
- 在每轮辩手发言后检查是否需要 compact
- 调用 `compact_log()` 时传入正确的 `prev_state` 和 `delta_entries`

**`src/debate/log.py`**（或 log entry 相关模块）
- `compact_checkpoint` entry 的 `content` 字段类型从 `str` 改为 `CompactCheckpointContent`（即 `{"state": ..., "view": ...}`）
- 新增辅助方法：获取自某个 seq 以来的所有 entries

### 3.3 实现优先级

| 优先级 | 任务 | 预计工作量 |
|--------|------|-----------|
| P0 | `compact_schema.py`：数据结构定义 + 校验函数 + Markdown 渲染 | 半天 |
| P0 | `compact.py`：改造为增量式 + JSON 输出 + 后校验 + 重试 | 1 天 |
| P1 | `context.py`：上下文构造适配新的 checkpoint 格式 | 半天 |
| P1 | `manager.py`：主动触发逻辑 | 2 小时 |
| P2 | 集成测试：用 mock 数据验证完整流程 | 半天 |