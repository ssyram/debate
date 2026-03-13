# debate-tool Compact 输出设计：压缩后辩手应该看到什么？ 辩论日志

> 2026-03-12T15:39:27.741954

---


### [1] Linus Torvalds

*2026-03-12T15:39:27.741954*

先给一个整体结论，然后分块展开（1 输出结构、2 摘要流程、3 增量压缩、4 演进表示），每一块都尽量落到「可以直接实现」的层面。

---

## 0. 总体设计思路（核心取向）

- **Compact 输出不是“缩短的对话记录”**，而是对当前辩论状态的「数据结构化快照」。
- 辩手看到的东西应该更像是：  
  「当前世界状态 + 双方角色卡 + 已经走过/被否决的路径 + 未决问题」，  
  而不是「上一轮发生了什么的浓缩版」。

所以我建议直接把 compact 结果设计成一个**固定 schema 的结构化文本**（最好接近 YAML / Markdown-structured），并在辩手的 system prompt 里明确告诉模型：  
> 你收到的不是聊天记录，而是“辩论状态描述”，你只能在此基础上继续推进，而不能重开问题。

下面按问题拆解。

---

## 1. 输出区块设计：compact 输出长什么样？

### 1.1 顶层结构

建议固定一个类似这样的结构（用 Markdown + 伪 YAML 风格，兼容人和 LLM）：

```markdown
## 辩论状态快照 (Compact Checkpoint v1)

### 1. 议题与阶段

- 议题：{topic 简要重述/澄清版}
- 当前阶段：{立论 / 攻防 / 总结 / 自由辩论 ... 自由描述也可}
- 当前轮次：{大致轮次编号或阶段描述}
- 主要讨论焦点：
  - 焦点1：...
  - 焦点2：...

---

### 2. 辩手立场快照

#### 2.1 辩手 A

- 当前核心立场（替换初始立场）：
  - 主结论：...
  - 关键论点：
    1. ...
    2. ...
  - 关键前提/假设：
    - ...
  - 对对方立场的整体评价：
    - 认可：...
    - 质疑：...

- 立场演进（简要时间线，越近越详细）：
  - [最近] 在回应 B 的 XXX 后，A 将 YYY 修正为 ZZZ，因为 ...
  - [更早] 初始认为 ...，在 ... 阶段被自身/对方质疑为 ...（仍坚持 / 已部分修改）

- 已明确放弃或弱化的观点：
  - 放弃点1：原主张 ...，被理由 ... 否定（被 A 自己/被 B/被裁判否决）
  - 放弃点2：...

- 当前主要待解决问题（A 视角）：
  - 问题1：...
  - 问题2：...

#### 2.2 辩手 B

（结构同 A，镜像一份）

---

### 3. 已达成与未达成的共识

- 已达成共识（不应被重复争论的点）：
  1. 双方都接受：...
  2. 双方都接受：...

- 争议仍然存在但核心论点已经轮到饱和的点：
  1. 争议点：...
     - A 已提出：...
     - B 已反驳：...
     - 当前状态：争议未解决，但不应重复既有论点，需寻找新角度/证据。

---

### 4. 被否决 / 行不通的路径记录

- 被否决路径列表（每项 1–3 句）：
  - 路径ID: P1
    - 描述：尝试用「...」来证明「...」
    - 否决原因：逻辑错误 / 与之前共识冲突 / 证据不足 / 被对方成功反例化 ...
    - 状态：不应在后续重复提出同一路径（除非有重大新信息）

  - 路径ID: P2
    - 描述：...
    - 否决原因：...

（可只保留最近若干个；更旧的合并为更粗粒度描述）

---

### 5. 当前开放问题与下一步建议

- 未决关键问题列表（如果要继续推进必须触及的）：
  1. Q1：...  
     - 为什么重要：...
     - 现有信息：A 认为 ...；B 认为 ...
  2. Q2：...

- 建议下一步推进方向（对当前轮次辩手的导航）：
  - 对 A 的建议（如果下一发言者是 A）：请优先就 Q1 / 焦点X 回应 YYY，不要再重复已记录为“被否决”的路径 P1,P2。
  - 对 B 的建议：...

---

### 6. 元信息

- 本次 compact 涉及的原始轮数范围：seq {start_seq} – {end_seq}
- 这不是完整对话记录，而是辩论状态摘要。后续发言不得假装“没发生过”这里记录的放弃/否决。
```

### 1.2 区块优先级（token 不够时如何裁剪）

优先性从高到低：

1. `2. 辩手立场快照`（当下核心立场、已放弃观点、待解决问题）  
2. `3. 已达成与未达成的共识`  
3. `4. 被否决的路径记录`（至少最近的）  
4. `5. 当前开放问题与下一步建议`  
5. `1. 议题与阶段`（可以简短）  
6. `6. 元信息`（可极度精简甚至删除）

实现上可以让 compact 生成器先生成「完整结构」，然后写一个简单的 `truncate_by_sections()`，按优先级裁剪文本长度。

---

## 2. LLM 摘要流程：怎么生成这些区块？

### 2.1 生成策略：一次大调用 vs 多次“填表式”调用

结合你提出的“填表流程”，我建议：

- **外层控制逻辑是“填表”**，但依然可以允许「少量多区块一次生成」，不要切得太碎：
  - 优点：减少串联错误、简化状态管理。
  - 缺点：要想好防止单次输出格式崩坏。

一个折中方案：

1. 第一步：生成**结构骨架 + 高层摘要**（议题&阶段 + 双方核心立场摘要 + 已达成共识）。  
   - Prompt A：输入最近一段对话（或从上一个 checkpoint 到现在的内容），输出区块 1, 2（不含演进细节），3 的草稿。
2. 第二步：生成**立场演进 & 被放弃路径**。  
   - Prompt B：专门让模型找「立场变化」和「被显式/隐式否决的论点」，输出区块 2 中的「立场演进」「已放弃观点」以及区块 4。
3. 第三步：生成**未决问题和下一步建议**。  
   - Prompt C：基于前两步产出的（它们可以拼在一起作为系统描述），再配上原文的一点尾部对话，生成区块 5。

最后由程序拼装成统一结构。

这样做的好处：

- 各块的任务边界清晰，“立场演进”和“被否决路径”的抽取可以用专门的提示词强调「不要重复原始内容，只提变化」。
- 如果某一步出错，重试成本较小。

### 2.2 Prompt 风格（核心要求）

对每个 Prompt 都要强调几个要点：

- **你不是裁判，不做价值判断**，只做“状态记录”。
- **记录的是变化与决策，而不是复述所有内容**。
- 对「已放弃/否决点」要有明确输出格式：包含「原主张」+「否决原因」+「否决主体」。
- 禁止使用「可能」「大概」去虚构对话中不存在的否决。

示例：Prompt B 的中文简版框架（省略细节）：

> 你将收到从上一个 compact checkpoint 到当前的辩论记录片段。  
> 你的任务不是再总结观点，而是：
> 1. 找出每个辩手对自己立场的修改、弱化、澄清（立场演进）。
> 2. 找出哪些论点或推理路径已经被明确或事实上否决。
> 
> 输出时遵守以下规则：
> - 对每个变更用一句话说明「以前认为什么，现在如何调整」。
> - 对每个被否决路径，必须包含：原主张 / 否决理由 / 否决是由谁发起（对方/自己/裁判）。
> - 不要重复列出初始立场，只记录变化。

### 2.3 自动 compact 时原模型不可用

两类策略可以叠加：

1. **预留 buffer + 预激活压缩**  
   - 在每轮构建辩手上下文时，如果 `log_token_estimate + 新一轮预估 > 模型上限 - safety_buffer`，提前触发 compact，而不是在真正超限后才处理。
   - 这个预 compact 调用可以使用「专门的便宜压缩模型」（例如一个固定的、高上限的模型），不占用当前辩手模型的 quota。
2. **强制使用“压缩专用模型”**  
   - 在配置中允许指定一个 `compact_model`（可以是同一厂商但不同 endpoint、也可以是本地模型），所有 compact 一律用它。
   - 这样即使某个辩手的 API token 用完或上限不同，也不会影响压缩。

如果没有额外模型，只能在本地/其他云上拉一个便宜 LLM（甚至 8k–16k 上限的小模型）。  
压缩质量略差也没关系，反正这是“辅助信息”，后续辩手模型能在其基础上进行修正。

---

## 3. 增量压缩：多次 checkpoint 怎么避免“摘要的摘要”烂掉？

### 3.1 原则：新 compact 基于「上一个 checkpoint + 之后的原始对话」，而不是再总结总结

流程可以是：

1. log 文件加载时：  
   - 找到**最后一个 `compact_checkpoint`**，标记为 `C_{N-1}`。
   - 从它之后的 entries 是**未压缩对话**。
2. 新 compact `build_compact_context()` 时：  
   - 输入给压缩模型的内容应是：
     - `C_{N-1}.content`（上一版状态快照文本）  
     + 从 `C_{N-1}.seq` 之后到当前的所有发言（未压缩原文）。
   - Prompt 中明确写：  
     > `C_{N-1}` 是上一轮的状态快照，请你在此基础上进行“更新”，而不是重头总结整个辩论。  
     > 你可以：
     > - 保留仍然正确的部分；
     > - 更新立场变化；
     > - 合并新否决路径；
     > - 删除已被双方显式承认无关紧要的枝节。
3. 生成新 `C_N` 后，旧的 `C_{N-1}` 挪到 `_archived_entries`，只在文件中保留 `C_N`+后续未压缩日志。

这样做的关键是：**compact 输出本身就是“辩论状态的主要载体”**，而不是“附属摘要”。每次 compact 都把旧状态 + 新信息整合为新状态。

### 3.2 控制信息衰减

为了防止“总结的总结”引入过度信息损失，可以加两道安全机制：

1. **在状态结构中保留一些“不可摘要字段”**  
   比如：
   - 「已达成共识」列表：除非新出现的对话直接推翻，否则不允许被模型删掉，只能添加或细化。
   - 「被否决路径」：除非明确被推翻为其实可行（这种少数情况也要通过对话显示），否则不允许从列表中消失，只能合并摘要（例如合并多个类似路径为一个条目，但保留核心否决理由）。
   实现方式：在 prompt 中写明确规则；Model 1 做完后，程序可以做简单检查：如果旧摘要中的某个共识/被否决路径在新摘要中完全消失，就提示模型“重新生成并保留这些项”（自动重试）。
2. **限制“对摘要再摘要”的深度**  
   在 prompt 中建议模型：  
   > 对于来自 `C_{N-1}` 的内容，只进行**必要的更新和极少的压缩**，不要重新概括全部内容。  
   > 优先在“演进与否决列表”中增加新项，而不是重写旧项。

---

## 4. 演进表示：用什么数据结构记立场变化、决策变迁、被抛弃路径？

### 4.1 立场变化（State + Diff）

立场可以拆成两层：

- **当前状态（State）**：  
  在「辩手立场快照」里，采用结构化字段：
  - 主结论
  - 关键论点（列表）
  - 关键前提
  - 对对方立场的总体看法

- **演进轨迹（Diff）**：  
  用一个短时间线列表记录「从上一个 checkpoint 到现在」的变化即可，避免无限增长：

```markdown
- 立场演进（最近若干条）：
  - [C_{N-1} → 现在] 在 XXX 问题上，从「所有情况都 Y」修正为「大多数情况 Y，但存在例外 Z」，原因是 B 指出 ...
  - [更早] ...
```

在多次 compact 时，可以让模型：

- 保留最近 3–5 条条目；
- 更老的条目合并为一行「早期阶段曾主张 ...，现已调整为 ...」。

### 4.2 被否决路径（Paths）

为避免模型“回滚打转”，对于每条被否决路径记录：

- `id`（可以只是 P1, P2...，不必唯一但足够 refer）
- `描述`：该路径试图证明什么，用的主要思路是啥（1 句）
- `否决原因`：逻辑/事实/设定冲突等
- `否决方式`：被谁如何指出（对方质询 / 自己承认 / 裁判裁定）
- `状态`：`不可再用` / `仅在补充证据后可复用` / `部分否决（可以改写）`

例子：

```markdown
- 路径ID: P3
  - 描述：通过「A 市成功案例」直接推论「全国普适可行」
  - 否决原因：样本过少且对 B 市不适用（B 指出异质性）
  - 否决方式：B 的反例 + A 承认外推条件不满足
  - 状态：不可再用“单一城市直接外推全国”的推理结构
```

后续在辩手提示里强调：

> 你不得再使用状态为“不可再用”的路径（即使换了措辞）。  
> 若要继续类似方向，必须明确说明「在 P3 被否决的基础上，尝试一个不同的路径：...」。

### 4.3 决策变迁与共识

对于「双方共同认可/裁判认可」的结果：

- 一律进入 `已达成共识` 列表。
- 每条共识记录：
  - 结论：...
  - 由谁主导提出
  - 对方是否显式同意（引用大致话术，如“B 表示‘这点我同意’”）
  - 是否用于否决某条路径（可指向 P_id）

这可以作为「不回滚」防护网：  
在后续轮次，辩手如果又开始争论一个已共识的前提，模型应该在自我对话中提醒自己「这已被记录为共识，请转向仍有争议的问题」。

---

## 5. 如何让辩手“用”这些结构而不走回头路？

最后要解决的是：**即使 compact 设计得很好，如果辩手 prompt 不利用这些结构，照样会回滚。**

建议对辩手的 system prompt 做两个改动：

1. 告诉辩手：“你收到的是状态快照而不是聊天记录”：  
   - 明确指出各区块的含义与用途。
   - 明说禁止行为：  
     - 不得重复提出 `已放弃观点` 内的论点。
     - 不得在没有理由的情况下推翻 `已达成共识` 中的内容。
     - 使用新路径时，最好对照 `被否决路径`，避免结构上相同的推理。
2. 增加一个**自检步骤**（可放在工具侧或要求模型做“心中检查”），例如在每轮生成前，先让模型内部写下一个短 plan（可以用 `thinking` tag 存）：  
   - 我要回应哪一个开放问题/焦点？
   - 我是否无意中重复了 `已放弃观点` 或 `被否决路径`？  
   这一步可以不暴露给用户，只是给模型一点“自我对齐”空间。

---

## 6. 小结：对四个问题的具体回答

1. **输出区块设计**  
   - 采用固定的「辩论状态快照」结构：  
     议题&阶段 → 双方立场快照（含演进 & 放弃点） → 共识 & 饱和争议点 → 被否决路径 → 未决问题 & 下一步建议 → 元信息。  
   - 提前定义优先级，以便在 token 紧张时有序裁剪。
2. **LLM 摘要流程**  
   - 推荐“填表式多步”：  
     - A: 高层结构（立场+共识）  
     - B: 立场演进 + 被否决路径  
     - C: 未决问题 + 下一步  
   - 强制使用一个独立的 `compact_model`，并在溢出前预 compact（留 buffer）。
3. **增量压缩**  
   - 新 compact 基于「上一个 checkpoint 的状态快照 + 此后原始发言」，不是对摘要的摘要。  
   - 在 prompt + 代码层双重限制：共识 & 否决路径默认不可消失，只能追加/合并。
4. **演进表示**  
   - 立场用 State+Diff：当前立场字段 + 近期演进时间线。  
   - 被抛弃路径用带 id 的列表，记录原思路+否决原因+状态。  
   - 共识和决策变迁单独列表，成为后续阶段的“约束条件”。

如果你愿意，我们可以下一步直接写一份可用的 compact 生成 Prompt 草案（按 A/B/C 三步）和一个简易的「基于 checkpoint + 新对话」的伪代码流程，把这套设计落成可直接实现的接口。

---


### [2] Ssyram

*2026-03-12T15:39:27.741988*

现在的 compact 实现本质上是一个「有损压缩」函数，这种设计在概率程序验证里叫「过近似（Over-approximation）」。如果我们只是机械地截断或模糊化，辩手就会在搜索空间里原地打转。**好的 compact 必须是「状态抽象」而非「文本摘要」。**

我攻击目前「一次性输出大文本块」的设想。这在工程上不可控，且 LLM 对长文本内部结构的注意力分布极不均匀。我们需要的是一个**基于状态转移的增量更新机制**。

### 1. 输出区块：从「叙事」转向「状态机」

不要给辩手一段「由于 A 说了... B 反驳了...」的废话。辩手需要的是当前辩论的 **Search Frontier**。

我建议 `compact_checkpoint` 必须包含以下四个显式定义的区块（以 `CompactState` 类型约束）：

```python
class CompactState(TypedDict):
    # 1. 已达成共识的命题（不再争议，作为后续推理的 Axioms）
    axioms: List[str] 
    
    # 2. 活跃冲突点（当前的搜索前沿，每个冲突点需包含双方最新的核心 Argument）
    active_frontiers: Dict[str, Dict[str, str]] # { "issue_id": { "player_a": "arg", "player_b": "rebuttal" } }
    
    # 3. 辩手状态演进（Stance Evolution）
    # 必须包含：原始立场 -> 经过 N 轮后的修正立场 -> 修正理由
    player_evolution: Dict[str, Dict[str, str]] 
    
    # 4. 剪枝路径（Dead Ends）
    # 记录已被否决的路径及否决理由，防止 LLM 回滚打转
    pruned_paths: List[Dict[str, str]] # [ { "path": "...", "reason": "..." } ]
```

**优先级策略**：
- `active_frontiers` 必须保留最高精度，占 50% token。
- `pruned_paths` 采用「布隆过滤器」思路，只记录关键词和否决结论，占 15%。
- `axioms` 压缩为短句，占 15%。
- `player_evolution` 占 20%。

### 2. 流程设计：主动 Compact 与「分段填表」

等到 token 溢出再 compact 是典型的「被动防御」，此时上下文已经脏了。

**我的方案：阈值触发的主动增量压缩。**
- **触发逻辑**：当 `current_tokens > 0.8 * max_tokens` 时，触发 `compact`。
- **模型选择**：自动 compact 时，如果原模型超限，**必须**使用一个具备更大 context window 或更廉价的模型（如 `gpt-4o-mini` 或专门的 `summarizer` 配置）来处理。不要指望原模型在极限边缘还能稳定输出结构化 JSON。

**分段填表算法（Pseudo-code）**：

```python
def incremental_compact(old_checkpoint: CompactState, new_entries: List[Entry]) -> CompactState:
    # 步骤 1: 提取新 entries 中的冲突增量
    # Prompt: "基于旧共识 {old_checkpoint.axioms}，分析新对话中哪些点达成了共识，哪些是新冲突"
    diff = extract_diff(old_checkpoint, new_entries)
    
    # 步骤 2: 更新状态机
    new_state = {
        "axioms": merge_axioms(old_checkpoint.axioms, diff.new_consensus),
        "active_frontiers": update_frontiers(old_checkpoint.active_frontiers, diff.active_issues),
        "player_evolution": update_stances(old_checkpoint.player_evolution, new_entries),
        "pruned_paths": old_checkpoint.pruned_paths + diff.rejected_ideas
    }
    
    # 步骤 3: 这里的关键是 Pruning。如果 pruned_paths 过长，进行二次压缩
    if len(str(new_state)) > LIMIT:
        new_state["pruned_paths"] = summarize_dead_ends(new_state["pruned_paths"])
        
    return new_state
```

### 3. 增量压缩与信息衰减：拒绝「套娃」

第 N 次 compact 遇到第 N-1 次 checkpoint 时，**绝对不能**把 N-1 的内容丢进 prompt 重新摘要。这会导致严重的语义漂移（Semantic Drift）。

**设计原则：Checkpoint 是不可变基座（Base），只对 Delta 进行 Reduce。**

在 `debate-tool` 的 `Log` 类中，`build_compact_context` 的输入应该是：
`Last_Checkpoint (JSON)` + `New_Entries_Since_Last_Checkpoint (Text)`。

LLM 的任务不是「总结全文」，而是「将 Delta 合并入 State」。

### 4. 演进表示：如何防止「原地打转」？

辩手回滚打转通常是因为 LLM 忘记了某个路径为什么走不通。`pruned_paths` 区块必须被注入到辩手的 `System Prompt` 或 `User Context` 的显著位置。

**Prompt 示例（用于生成 `pruned_paths`）**：
> "识别本次对话中被明确否定、证伪或因逻辑矛盾被放弃的提议。每个记录包含：1. 被放弃的观点；2. 放弃的决定性理由。格式：{ 'idea': '...', 'reason': '...' }"

在给辩手下一次迭代的输入时，格式化如下：
```markdown
## 辩论状态摘要
### 已确认事实 (Axioms)
- ...
### 需继续讨论的冲突 (Active Frontiers)
- 议题 A: 辩手 1 认为... 辩手 2 反驳...
### 已否决路径 (Pruned - 勿重复提出)
- 路径 X: 因 [理由] 已被弃用。
```

### 5. 针对「自动 compact」的硬性接口定义

我要求 `debate-tool` 增加一个 `CompactManager` 类，隔离压缩逻辑：

```python
class CompactManager:
    def __init__(self, summarizer_model: str):
        self.model = summarizer_model

    async def fold(self, base_state: CompactState, entries: List[LogEntry]) -> CompactState:
        """
        核心逻辑：将新条目折叠进旧状态。
        类似函数式编程中的 foldl: f(state, x) -> state'
        """
        # 1. 调用 LLM 更新 Axioms 和 Frontiers
        # 2. 调用 LLM 更新 Player Stances
        # 3. 语义去重 (De-duplication)
        pass

    def format_for_player(self, state: CompactState) -> str:
        """将结构化状态转换为辩手可理解的 Markdown"""
        return f"### 已达成共识\n{state['axioms']}\n..."
```

### 总结我的立场：

1.  **反对**单纯的文本压缩，**支持**结构化的状态转移（Axioms/Frontiers/Pruned）。
2.  **必须**引入 `summarizer` 专用模型配置，解决溢出时原模型不可用的死锁。
3.  **增量更新**：Compact 过程是 `f(State_N-1, Entries_N) -> State_N`，而不是 `f(Log_0...N) -> Summary`。
4.  **显式剪枝**：记录 `pruned_paths` 是防止辩论陷入局部最优解或死循环的唯一手段。

给下一步实现的建议：先定义好 `CompactState` 的 JSON Schema，然后写三个独立的 Prompt 分别负责 `axioms`、`frontiers` 和 `pruned_paths` 的更新。一次性生成整个 JSON 极易失败。

---


### [3] 康德（Immanuel Kant）

*2026-03-12T15:39:27.742006*

下面按你给的上下文直接给一个「可落地的设计方案」，同时把 4 个问题都覆盖掉。默认你是实现者+重度用户，我会偏工程化而不是抽象空谈。

---

## 1. 输出区块设计：compact 后辩手到底看到什么？

### 1.1 顶层结构（给辩手看到的整体形态）

建议把 `compact_text` 设计成**强结构化 + 人类可读**的 Markdown：

```markdown
# 辩论压缩快照 v3

## 1. 当前议题 & 立场状态

### 1.1 议题
{topic 的简化版，可在首次压缩时重写、之后仅微调}

### 1.2 辩手立场总览
- 辩手A：{一句话立场总结}
- 辩手B：{一句话立场总结}
- （可选）裁判/系统：{若有}

## 2. 各辩手立场卡（Canonical State）

### 辩手A 立场卡（版本 3）
- 当前核心主张：
  1. ...
  2. ...
- 支撑的关键论据：
  - 论据1：...
  - 论据2：...
- 已承认的弱点/前提：
  - ...
- 明确放弃的主张：
  - 【废弃】主张X —— 被对方 Y 反驳，理由：...
  - 【废弃】主张Y —— 自己承认不成立，理由：...

### 辩手B 立场卡（版本 3）
（同上结构）

## 3. 演进轨迹（Timeline of Debate）

按时间顺序抓「跳变点」，而不是所有轮次：

1. **阶段 1：立场初始表述**
   - A：...
   - B：...

2. **阶段 2：关键冲突点出现**
   - 核心争议点：
     - 争议点 #1：{一句话}
       - A 立场：...
       - B 立场：...
       - 当前裁判/共识状态：{尚未解决 / 暂时接受 B 的版本 / A 部分让步}
   - 被放弃的路线：
     - A 放弃 X，因为...

3. **阶段 3：最近一轮重大更新**
   - 最新的主张修正/让步：
     - A：从「...」修正为「...」，承认「...」
     - B：新增了「...」这一攻击点

（这一块控制在 5–10 条时间节点内）

## 4. 当前待解决的关键问题（Next Steps）

未来发言建议聚焦在：

1. [开放] 争议点 #2：{一句话描述}
   - 当前状态：A 有论据但未回应 B 的反驳 / 双方都没有给出实证 / 裁判还未判定
2. [开放] 争议点 #3：...

每位辩手在接下来的发言中应该：
- 辩手A：优先处理「...」的问题，避免重复「...」这一已被否决的路线
- 辩手B：优先回应「...」的质疑，并尝试 solidify 「...」这一优势点

## 5. 技术元数据（给系统/调试用，可隐藏给辩手）

- compact_version: 3
- last_original_seq: 47
- checkpoints_history:
  - v1: from seq 1–20, created at ...
  - v2: from seq 1–33, created at ...
  - v3: from seq 1–47, created at ...
```

**辩手真正会看到的可以是：1–4 部分**，第 5 部分只写进 log，不一定喂给模型。

---

### 1.2 关键设计点

1. **立场卡是唯一真相源（canonical state）**  
   - 「topic 初始立场描述」只在第一次用，之后**每次 compact 后都用立场卡覆盖掉旧的立场描述**。
   - 辩手在下一轮看到的，是自己和对方**当前版本的立场卡**，而不是老立场 + 一堆历史发言。

2. **废弃路径必须结构化记载**  
   存在一个明确的小节「明确放弃的主张」，格式固定：
   ```markdown
   - 【废弃】主张：{句式化的主张}
     - 被谁否决：{自己 / 对方 / 裁判}
     - 否决理由（1–2 句）：...
   ```
   这样下一轮模型容易 pattern-match：  
   > 啊，这一块前面标了废弃，我不能再拿来当论点。

3. **演进轨迹只记节点，不记流水账**  
   你要的是「思路延续」，不是「还原完整历史」。所以 timeline 只保留**几个状态转折点**：
   - 初始立场 → 出现核心争议 → 各方第一次严肃回应 → 裁判/共识初步判定 → 最新一轮重大修正

4. **Next Steps 区块是防止「原地打转」的核心**  
   把：

   - 哪些问题已经解决
   - 哪些问题还开放
   - 每个辩手下一步应该干什么、避免干什么

   显式写出来。模型看到这个，最容易被「牵着走」进正确的继续路径，而不是回去重提早被否决的点。

---

## 2. LLM 摘要流程：怎么调用、怎么分块、模型挂了怎么办？

### 2.1 不要一次性大 Prompt，改成「填表流水线」

按你说的「填表」思路，建议拆成多次调用，每次生成一个结构化区块。典型流程（伪代码风格）：

1. **预处理**：从 log 中抽取原始文本
   - 获取从上一个 `compact_checkpoint` 之后到当前的所有 entries（包括旧的 checkpoint 内容 + 新发言）。
   - 对 `thinking` 等内部 tag 可选择丢弃或高度压缩。

2. **调用 1：生成议题 &争议点摘要**

   Prompt 大意：

   > 输入：原始议题 + 最新一段对话（可能跨多轮）  
   > 输出：
   > - 一个精简后的议题描述（可重写）  
   > - 当前存在的 3–7 个「核心争议点」，每个 1–2 句

   得到结构块：
   ```json
   {
     "topic_slim": "...",
     "disputes": [
       {"id": "D1", "title": "...", "summary": "...", "status": "open/partial/closed"},
       ...
     ]
   }
   ```

3. **调用 2：为每个辩手生成 / 更新立场卡**

   对每位辩手单独跑一次（或在一个 prompt 里分角色输出结构化 JSON）：

   Prompt 大意：

   > 输入：  
   > - 上一个版本的该辩手立场卡（如有）  
   > - 自上次 checkpoint 以后该辩手所有相关发言  
   > - 对方对这些发言的主要回应  
   > 输出：更新后的立场卡，包括：
   > - 当前核心主张（合并修正后的版本）  
   > - 关键论据  
   > - 承认的弱点/前提  
   > - 新增的、明确废弃的主张（包括原因）

   输出结构：
   ```json
   {
     "name": "辩手A",
     "version": 3,
     "core_claims": [...],
     "key_arguments": [...],
     "weaknesses": [...],
     "abandoned_claims": [...]
   }
   ```

4. **调用 3：生成演进轨迹（timeline）**

   Prompt 大意：

   > 输入：从上一个 checkpoint 以来的对话摘要（可以使用裁判 summary + 当前轮对话）  
   > 输出：若干「阶段节点」，每个节点包含：
   > - 阶段标题  
   > - 本阶段核心事件/论点变化（按辩手分开）  
   > - 争议点状态变化（引用 D1, D2 等）

   结构化输出后再渲染成 Markdown 的 “## 演进轨迹”。

5. **调用 4：生成 Next Steps**

   Prompt 大意：

   > 输入：
   > - 各辩手最新立场卡  
   > - 争议点列表及状态  
   > - 演进轨迹  
   > 输出：
   > - 「当前待解决的关键问题清单」  
   > - 对每个辩手的「下一轮建议行动」+「需要避免重复的点」

   这一步是强制模型**考虑未来**而不是只总结过去。

6. **拼装 Markdown**

   工具层负责把前几步的 JSON 结果，按 1.1 的模板拼接成一份 Markdown `compact_text`，同时在 log 中保留 JSON 结构（可以放在 `compact_checkpoint` 的 `content` 里；人看用 Markdown，系统用 JSON）。

---

### 2.2 自动 compact 时原模型不可用怎么办？

有几个实务约束：

- 「触发 compact」的模型（辩手）已经超 token 了，**不能再用它来压缩**。
- 但你可以：
  1. 用另一个专门的小模型（如本地 LLM 或更低配 API）做 compact；
  2. 或者在溢出前就有节奏地「预 compact」。

方案：

1. **引入专职 Compact 模型配置**

   在配置中增加一个 `compact_model`，单独的 `base_url/api_key/max_tokens`：

   - 默认使用开源/小模型，比如 `gpt-4o-mini` / `qwen2.5-32b` 等；
   - 和辩手模型解耦，所以即使辩手模型走的是别的 vendor，也没关系。

2. **提前 compact：水位线策略**

   在每轮发言前估算 token 总量，如果：

   - `当前日志 tokens + 预估本轮发言 tokens > 某个 soft_limit`  
   → 先跑一轮 compact，再让辩手继续发言。

   这样大部分 compact 发生在「还能用原模型的阶段」，但你仍然**不要依赖原模型**，统一用 `compact_model`，避免复杂度。

3. **兜底方案**

   如果 `compact_model` 调用失败：

   - 使用 ultra 简化版 compact：  
     - 只保留最近 N 条发言 + 裁判 summary + 上一次的 compact checkpoint；  
     - 不做结构化，只加一条提示「历史被截断，可能导致部分复读」。
   - 这是 token 安全的，但体验降级可接受。

---

## 3. 增量压缩 & 多次 checkpoint：避免层层摘要导致信息腐烂

### 3.1 总原则：永远只压缩「新增增量 + 上一次 checkpoint」，不要递归压摘要

做 compact 时的输入应该是：

- 上一个 `compact_checkpoint` 的「结构化 JSON 状态」（立场卡 + 争议点 + timeline 概要）
- 自上一次 checkpoint 之后的**原始**发言 entries（裁判 summary 可以作为高权重参考）

流水：

1. `load_from_file()` 时：
   - 找到最后一个 checkpoint，把它的 JSON 状态读出（作为「旧状态」）；
   - 之后的 entries 保留为本轮「增量对话」。

2. `build_compact_context()` 时：
   - Prompt 不是对所有历史重 summarization，而是：
     - 输入：旧状态（JSON） + 新增发言（文本）  
     - 输出：新状态（JSON）

   这和「数据库里维护一份 canonical state，每次只 apply delta」的思路一样。

3. 这样避免的东西：

   - 不会出现 V1 → 压成 V2 → 再压成 V3 → 信息越来越稀薄的递归摘要；
   - 每次都是「旧 state + 新增对话 → 新 state」，信息密度基本稳定。

### 3.2 如何控制信息不爆炸？

因为旧状态是高密度结构化信息，新增对话是流水，这样的组合本身比较精简。但仍有几个策略：

- 对「演进轨迹」只保留最近 K 个阶段节点（比如 K=5–7），更早的阶段归并成一行「早期阶段略：...」。
- 对「废弃主张」保留最近 N 个（比如 N=10），更旧的合并成「早期有若干已废弃主张，此处略」。
- 对每个争议点有一个 `status`：
  - `open`：完整保留描述；
  - `partial_resolved`：保留概要；
  - `resolved`：在立场卡里留一行结果即可，timeline 里不再细讲。

---

## 4. 演进与弃用路径的数据结构设计

你实际需要两类结构：

1. **长寿命、随时间演进的「状态结构」**
2. **短寿命、帮助模型理解「过程」的 narrative 结构**

### 4.1 状态结构（写入 JSON）

示意定义（伪 schema）：

```json
{
  "compact_version": 3,
  "topic": {
    "current_formulation": "当前议题精简描述",
    "notes": "可选的一些澄清"
  },
  "participants": [
    {
      "name": "辩手A",
      "stance_version": 3,
      "core_claims": [
        {"id": "A1", "text": "...", "status": "active/abandoned"},
        ...
      ],
      "key_arguments": [
        {"id": "A1-arg1", "claim_id": "A1", "text": "...", "strength": "strong/weak"},
        ...
      ],
      "admitted_weaknesses": [
        {"id": "A-w1", "text": "...", "related_claims": ["A1", "A2"]}
      ],
      "abandoned_claims": [
        {
          "claim_id": "A0",
          "text": "原主张...",
          "reason": "被 B 指出逻辑自相矛盾",
          "decided_by": "self/opponent/judge",
          "ts": "..."
        }
      ]
    },
    {
      "name": "辩手B",
      ...
    }
  ],
  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "...",
      "status": "open/partial_resolved/resolved",
      "positions": {
        "辩手A": "A 在此争议中的立场摘要",
        "辩手B": "..."
      },
      "resolution": "如果已 resolved，写结论"
    }
  ],
  "timeline_brief": [
    {
      "phase": 1,
      "title": "立场初步陈述",
      "summary": "..."
    },
    {
      "phase": 2,
      "title": "围绕可行性的首次冲突",
      "summary": "..."
    }
  ],
  "open_questions": [
    {
      "id": "Q1",
      "text": "目前尚未解决的问题...",
      "related_disputes": ["D2"],
      "suggested_focus": {
        "辩手A": "建议处理...",
        "辩手B": "建议处理..."
      }
    }
  ]
}
```

**要点：**

- `participants[*].core_claims` + `abandoned_claims` 是防复读的关键；
- `disputes` 用来组织「争点」，给未来轮次提供 anchor；
- `open_questions` 就是 Next Steps 的结构化版本。

### 4.2 给模型看的 narrative（Markdown 渲染）

- 从上述 JSON 生成 Markdown。
- 立场卡 + 演进轨迹 + Next Steps 都由这些结构转换而来。
- 你可以在 `compact_checkpoint` 的 `content` 字段里同时存：  
  - `content.markdown`: 给辩手看的  
  - `content.state`: 上面这种 JSON 状态  
  （或者 JSON log 内再嵌套一层）

---

## 5. 回到 4 个问题快速对照总结

1. **输出区块设计**  
   - 建议 4 大块：议题&立场总览 / 各辩手立场卡 / 演进轨迹 / Next Steps  
   - 底层有 JSON 状态结构，渲染成 Markdown 喂给辩手。  
   - 核心机制：立场卡覆盖原始立场描述 + 明确记录废弃主张。

2. **LLM 摘要流程**  
   - 不一次性大块；拆成「议题 & 争点」「各辩手立场卡」「演进轨迹」「Next Steps」多次调用，填表式生成 JSON。  
   - 使用独立的 `compact_model`，与辩手模型解耦。  
   - 加 soft-limit 预 compact，避免在超 token 后才被动压缩。  
   - 调用失败时有 fallback 简化策略。

3. **增量压缩**  
   - 每次 compact：上一次 checkpoint 的 JSON 状态 + 新增发言 → 新 JSON 状态。  
   - 不对旧摘要再摘要，避免信息衰减。  
   - timeline / 废弃主张 等有「有限窗口 + 归并」策略控制大小。

4. **演进表示 & 被抛弃路径结构**  
   - 用 `participants[*].core_claims / abandoned_claims / admitted_weaknesses` 表示每个辩手的立场演进。  
   - 用 `disputes` / `timeline_brief` 表示整体辩论演进轨迹。  
   - 用 `open_questions` + 每辩手的 `suggested_focus` 为下一轮指明路径，防止回滚打转。

如果你愿意，我可以下一步直接写出一套「compact_model 用 prompt 模板」（中文/英文皆可），包括每一步 JSON schema 和示例，这样可以直接粘到代码里用。

---


### [4] 🔍 **质询** Linus Torvalds → (未解析)

*2026-03-12T15:40:08.783616*

下面给出一份「站在作者视角」的综合方案，同时点评三位辩手的提案，并给出可以直接实现的设计。

我会按这四点组织：

1. 要达成的“体验目标”到底是什么  
2. 综合三人观点后的 **compact 输出结构**（辩手会看到什么）  
3. **状态结构 & 增量压缩机制**（避免信息衰减 / 打转）  
4. **LLM 摘要流水线 & Prompt 颗粒度**（如何落地）

---

## 1. 体验层目标再精炼一下

你已经定了两个目标：

- 思路能顺畅接上（思路延续）  
- 不会回滚打转（不重提否决路径）

这里再加两条工程视角上的隐形目标：

1. **辩手上下文必须是“状态”而不是“历史”**：  
   模型不擅长在一大段流水账里找出“当前局面”，所以我们要喂给它的是「当前棋局盘面」，而不是「从第 1 手到第 120 手的棋谱」。

2. **compact 本身要可增量维护**：  
   每次 compact 应该是：  
   `新状态 = f(旧状态, 新增对话)`  
   而不是：  
   `新状态 = summarize(全部历史)`  
   这既减少 token，又避免语义漂移。

Linus / Ssyram / “康德” 三个方案其实都在向同一个方向靠拢：**用结构化状态 + 填表式更新**，区别只是结构多少、侧重点不同。

我下面给的方案是三者的折中版：  
- 结构不至于太复杂到难以实现；  
- 又有足够信息让模型真的「不打转」。

---

## 2. 辩手看到的 compact 输出长什么样？

### 2.1 对辩手暴露的 Markdown 结构

建议统一一套简洁但信息够用的结构（把三人的 schema 做了瘦身、合并）：

```markdown
# 辩论压缩快照 v{version}

## 1. 当前议题与阶段

- 议题简述：{topic_slim}
- 当前阶段：{例如：立论 / 攻防 / 收束 / 自由辩论...}
- 当前主要争点：
  - [D1] {争点1一句话}
  - [D2] {争点2一句话}
  - ...

---

## 2. 辩手立场卡（当前版本）

### 2.1 辩手 {A_name}

- 一句话立场：{A_one_line}
- 当前核心主张：
  1. {A_claim_1}
  2. {A_claim_2}
- 关键论据（仅列主要的几条）：
  - {A_arg_1}
  - {A_arg_2}
- 已承认的前提 / 弱点：
  - {A_weak_1}
  - {A_weak_2}

- 明确放弃或弱化的主张（不得原样再用）：
  - 【废弃】{A_abandoned_1}
    - 否决方式：{self / opponent / judge}
    - 否决理由：{1–2 句}
  - 【废弃】{A_abandoned_2}
    - ...

### 2.2 辩手 {B_name}

（同上结构）

---

## 3. 争点状态（已达成 / 仍有争议）

### 3.1 已达成共识（不应再反复争论）

- [C1] {共识点一句话}
  - 由谁提出：{A/B/裁判}
  - 双方态度：{均明确同意 / B 无异议 / A 无异议}

### 3.2 仍在争议的核心问题

- [D1] {争点1一句话}
  - A 的当前立场：{1–2 句}
  - B 的当前立场：{1–2 句}
  - 现状：{尚无裁决 / 双方证据不足 / A 占上风但未封板...}

- [D2] {争点2一句话}
  - ...

---

## 4. 被否决 / 行不通的推理路径（防止回滚）

以下路径已被认为行不通，后续发言不应在没有重大新信息的情况下重复使用：

- [P1] {路径一句话描述}
  - 尝试证明：{想证明的结论}
  - 主要思路：{略}
  - 否决原因：{逻辑错误 / 与共识 Cx 冲突 / 被反例推翻 / 证据不足...}
  - 否决方式：{被对方指出 / 自己承认 / 裁判裁定}
  - 状态：{不可再用 / 仅在补充证据后可重启 / 已部分修正为新路径 Px'}

- [P2] {路径一句话描述}
  - ...

---

## 5. 最近演进概要 & 下一步建议

### 5.1 最近几轮的关键变化（时间线概要）

- 最近阶段的要点：
  - A 从「...」修正为「...」，承认了「...」。
  - B 新增了「...」这一攻击点，并成功让 A 废弃了「...」。
  - 争点 [D2] 从「模糊争论」收束为「是否接受前提 X」。

（控制在 3–6 条）

### 5.2 接下来应重点推进的方向

- 关键开放问题：
  - [Q1] {尚未解决的关键问题1}
    - 与争点：{D1/D2...} 相关
  - [Q2] {尚未解决的关键问题2}

- 对辩手 {A_name} 的建议：
  - 优先处理：{Q1 / D2 ...}
  - 在发言中请避免：
    - 重复使用路径 [P1] / 拿【废弃】主张「...」当前提
    - 重复质疑已在 3.1 中记录为共识的内容

- 对辩手 {B_name} 的建议：
  - 优先处理：{...}
  - 注意避免：{...}
```

**这就是 compact 后辩手看到的东西**（作为 `## 辩论历史\n\n{compact_text}` 注入）。  
注意几点：

- 它不是“上一轮谁说了什么”的流水记载，而是「当前局面的说明书」；
- 【废弃主张】+「被否决路径」+「共识」三个区块，是防止回滚打转的关键；
- 「下一步建议」给模型一个非常强的“轨道”：要往哪里推进、不要回到哪里。

---

## 3. 状态结构 & 增量压缩机制

Markdown 是喂给辩手的视图，但真正维护的应该是一个 **CompactState JSON**。这里综合三人的结构，做成一个可直接实现的 schema：

```python
# 伪 TypedDict / Pydantic Schema

class AbandonedClaim(TypedDict):
    id: str            # "A-ab1"
    text: str          # 原主张
    decided_by: str    # "self" | "opponent" | "judge"
    reason: str        # 否决理由（简短）
    ts: str            # ISO 时间戳（可选）

class PathRecord(TypedDict):
    id: str            # "P1"
    description: str   # 路径一句话描述
    target: str        # 尝试证明的结论
    reason: str        # 否决原因
    decided_by: str    # "self" | "opponent" | "judge"
    status: str        # "forbidden" | "revive_with_new_evidence" | "partially_invalid"

class ParticipantState(TypedDict):
    name: str
    version: int
    one_line: str
    core_claims: List[str]
    key_arguments: List[str]
    weaknesses: List[str]
    abandoned_claims: List[AbandonedClaim]

class Dispute(TypedDict):
    id: str            # "D1"
    title: str         # 争点一句话
    summary: str       # 简要说明
    status: str        # "open" | "partial_resolved" | "resolved"
    positions: Dict[str, str]  # { "辩手A": "...", "辩手B": "..." }
    resolution: str    # 若 resolved，则写结论，否则为空

class ConsensusPoint(TypedDict):
    id: str            # "C1"
    text: str          # 共识内容
    proposer: str      # 谁先提
    acceptance: str    # "both_explicit" | "A_no_objection" | "B_no_objection"

class TimelineItem(TypedDict):
    phase: int
    title: str
    summary: str       # 1–3 句描述本阶段关键变化

class OpenQuestion(TypedDict):
    id: str            # "Q1"
    text: str
    related_disputes: List[str]
    suggested_focus: Dict[str, str]  # 对各辩手的建议

class CompactState(TypedDict):
    compact_version: int
    topic_slim: str
    stage: str
    participants: List[ParticipantState]
    disputes: List[Dispute]
    consensus: List[ConsensusPoint]
    pruned_paths: List[PathRecord]
    timeline_brief: List[TimelineItem]
    open_questions: List[OpenQuestion]
    last_original_seq: int
```

### 3.1 增量压缩：f(旧状态, 新 entries) → 新状态

在你的 `Log` / `compact_checkpoint` 流程中：

- `load_from_file()`：
  - 找最后一个 `compact_checkpoint` entry；
  - `content` 里保存两部分：
    - `state`（这个 JSON）
    - `markdown`（给人/辩手看的快照）
  - 把 `state` 读出来，作为 `old_state`；
  - 之后的 entries 是 `new_entries`。

- 新一轮 compact 时：

```python
def build_compact_context(old_state: CompactState | None, new_entries: List[Entry]) -> CompactState:
    if old_state is None:
        # 第一次 compact：用全部历史 entries + topic 建初始 state
        return initial_compact(new_entries)
    else:
        # 增量 compact：old_state + 新 entries → new_state
        return incremental_compact(old_state, new_entries)
```

`incremental_compact` 的设计（结合 Ssyram 的 fold 思路）：

- 输入：`old_state` + `text_of(new_entries)`；
- Prompt 不要求“从头总结整个辩论”，而是明确写：

> - `old_state` 是上一轮压缩时的辩论状态，请你在此基础上「更新」：  
>   - 保留仍然正确的部分  
>   - 根据新对话更新：  
>     - 各辩手的立场卡（core_claims / weaknesses / abandoned_claims）  
>     - 争点（disputes）及其状态  
>     - 新的共识点（consensus）  
>     - 新增的被否决路径（pruned_paths）  
>     - timeline_brief 中最近阶段  
>     - open_questions / suggested_focus  
> - 禁止从 `old_state` 中无缘无故删除共识点或被否决路径，除非新对话明确推翻它。

这样每次都是“apply delta”，不会出现“摘要的摘要”。

### 3.2 防信息衰减 / 爆炸的小规则

在 prompt + 代码层双重约束：

- **共识与被否决路径**：
  - 默认不可被删除；可合并、多条合成一条更概括的，但内容不能完全消失。
  - 程序层可做 sanity check：  
    - 如果新 state 中共识数远小于 old_state（例如减少 50% 以上），自动重试，且在 prompt 中警告模型「不要删除旧共识」。

- **timeline_brief / pruned_paths 限长**：
  - timeline 只保留最近 5–7 条，老的合并成 1–2 条「早期阶段概要」。
  - pruned_paths 只保留最近若干条最重要的（比如按“被引用次数”或显性严重程度打分后保留 top K），其余合并描述。

- **disputes / open_questions**：
  - 已 `resolved` 的争点简化，只在共识里保留一行；
  - `open_questions` 只保留真正阻碍推进的关键问题（3–5 个）。

---

## 4. LLM 摘要流水线 & Prompt 颗粒度

结合你希望的「填表式」和三位辩手的意见，我建议采用**3–4 步调用**，每步任务窄而清晰，输出 JSON，然后由代码拼成 `CompactState` 和最终 Markdown。

### 4.1 建议的流水线

假设有一个 `compact_model`（专职压缩模型），所有 compact 一律用它（不要用辩手模型，便于统一）。

#### 步骤 0：触发策略

- 在每轮构建上下文时，估算 `log_tokens`；
- 若 `log_tokens + 预估当前辩手发言 > 模型上限 * 0.8`：
  - 先触发 compact；
  - 用 `compact_model`：  
    - 输入：`old_state` + `new_entries_since_last_checkpoint`；
    - 得到 `new_state` + `markdown`；
  - 在 log 中写入 `compact_checkpoint` entry；
  - 后续辩手再继续用 `markdown` 作为历史。

这样避免「真正超限时原模型不可用」的死锁。

#### 步骤 1：更新各辩手立场卡

Prompt 概要（针对 A/B 两个 participant，可以一次性让模型输出一个 participants 列表，也可以分角色调用）：  

输入：

- `old_state.participants`（旧立场卡）；
- `new_entries` 中 A/B 的发言 + 对方对这些发言的主要回应（可以由你先做简单筛选，提取对话片段）；
- 话题与当前争点列表：`old_state.disputes`。

输出：

- 更新后的 `participants`，每个包含：
  - `one_line`
  - `core_claims`
  - `key_arguments`
  - `weaknesses`
  - 新增的 `abandoned_claims`（保持旧的也带上）

Prompt 要点：

- 强调「在旧立场卡基础上增量更新」；
- 清楚定义【废弃主张】的条件；
- 禁止随意删除旧的 `abandoned_claims`，除非新对话明确推翻。

#### 步骤 2：更新争点 & 共识 & 被否决路径

输入：

- `old_state.disputes`
- `old_state.consensus`
- `old_state.pruned_paths`
- `new_entries` 的摘要（可以先跑一个快速 summarization）或者直接原文（视 token 而定）。

输出：

- 更新后的 `disputes`:
  - 哪些争点状态从 open → partial_resolved / resolved；
  - 新出现的争点。
- 更新后的 `consensus`:
  - 新达成的共识条目；
- 追加的 `pruned_paths`:
  - 新出现的被否决推理路径。

Prompt 要点：

- 把「已达成共识」「仍在争议」「被否决路径」三种结果明确区分；
- 明写规则：  
  - 旧共识 / 旧 pruned_paths 原则上不可删除，只能扩充或稍微重写；
  - 只有在新对话明确“推翻旧结论”的时候，才允许标记“过时”并写入新的条目。

#### 步骤 3：更新 timeline_brief & open_questions

输入：

- 更新后的 `participants` / `disputes` / `consensus`；
- `new_entries` 的整体语义（或再跑一个小 summary）。

输出：

- 若干新的 timeline 节点（1–2 个）；
- 更新的 `open_questions` 列表和每个辩手的 `suggested_focus`。

Prompt 要点：

- 要求只记录「真正改变局面」的事件；
- 明确最多输出多少条 timeline / open_questions（例如 3 each）。

#### 步骤 4：组装 CompactState & Markdown

- 由代码将步骤 1–3 输出合并成 `new_state`；
- 使用一个简单的模板函数 `render_state_to_markdown(new_state)`，生成前面 2.1 的 Markdown；
- 将 `{ "state": new_state, "markdown": markdown }` 序列化进 `compact_checkpoint` 的 `content` 字段。

---

## 5. 小结：把三人的观点怎么合并进你要的设计

- 从 Linus 那里借：  
  - 「辩论状态快照」的整体视角（世界状态 + 角色卡 + 被否决路径 + 未决问题）  
  - 区块优先级思路：立场卡 > 共识/争点 > 被否决路径 > Next Steps > 议题简介

- 从 Ssyram 那里借：  
  - 把 compact 视为 `State` 的增量更新而不是全文摘要；  
  - 明确 `pruned_paths` 的语义：剪枝，防走回头路；  
  - 用一个专职 `compact_model`，并设计 `incremental_compact(old_state, new_entries)` 的 fold 逻辑。

- 从 “康德” 那里借：  
  - 立场卡覆盖初始立场的「canonical state」思想；  
  - 明确的 JSON state + Markdown 渲染；  
  - 「Next Steps」作为防模型复读的导航机制。

综合之后，你得到的是：

1. **对辩手**：一份统一结构的 Markdown “状态快照”，更像围棋实况解说 + 当前局面图，而不是聊天摘要。  
2. **对系统**：一个 `CompactState` JSON，支持多次 checkpoint 的增量维护，不会越压越糊。  
3. **对实现**：3–4 步的填表式 prompt 流水线，各步任务很窄，便于调试与重试；compact 使用独立模型，并在 token 接近上限前主动触发。

如果你愿意，下一步我可以帮你写出具体的中文/英文 Prompt 模板（一步步的 system + user 指令）、以及 `incremental_compact` 的伪代码实现，把这个设计直接变成可拷贝进项目的代码草案。

---


### [5] 🔍 **质询** Ssyram → Linus Torvalds

*2026-03-12T15:40:26.494662*

质询对象：Linus Torvalds

Linus，你的方案在直觉上抓住了「状态快照」的重点，但在系统实现层面，你的逻辑过于依赖 LLM 的「自觉性」，缺乏形式上的约束。这种「State + Diff」的描述非常模糊，在概率程序验证（Probabilistic Program Verification）的视角下，这种设计极易引入语义漂移（Semantic Drift）。

针对你的方案，我有以下三个尖锐质疑：

**1. 关于「State + Diff」的收敛性与自洽性：**
你建议在「立场快照」中记录「State（当前立场）」和「Diff（演进轨迹）」。但在多轮增量压缩（Incremental Compacting）中，如果你的 Diff 只是「最近若干条变化」，你如何保证 State 的更新过程符合 `State_N = fold(State_N-1, Entries_N)` 的函数式一致性？
如果 State 的更新是由 LLM 自由发挥生成的，而没有强制的 Schema 约束（例如：要求必须显式标注哪些 Axioms 被推翻），那么经过三次 compact 后，State 就会变成「摘要的摘要的摘要」，原始辩论的严密逻辑会被 LLM 的叙事惯性彻底抹平。**请给出具体的 `update_state` 伪代码，说明你如何防止 State 在多次迭代中丢失关键的逻辑约束（Invariants）。**

**2. 关于「三步走填表」的原子性与冲突处理：**
你提议分三步（Prompt A/B/C）生成快照。这是一个工程上的灾难。LLM 在不同调用间的 Context Window 是孤立的。如果 Prompt B（演进与路径）识别出了一个被否决的路径 P1，但 Prompt A（核心立场）在生成时因为随机性没有体现出对 P1 的规避，最终拼装出的 Markdown 就会包含逻辑冲突。
这种「分布式状态生成」如何保证原子性（Atomicity）？如果步骤 C 发现步骤 A 生成的「当前焦点」与「被否决路径」矛盾，你的系统逻辑是重试、合并还是直接报错？**不要跟我说「模型通常能处理好」，我要看你的冲突解决策略（Conflict Resolution Strategy）。**

**3. 关于「被否决路径」的 Grounding（落地）问题：**
你定义了 P1, P2 这样的路径 ID，但在辩手（Player）的 System Prompt 里，你只是告诉它「不要重复 P1」。这太软弱了。LLM 对「不要做什么」的指令遵循度极低，除非这些路径被映射到具体的逻辑谓词或事实命题上。
如果 P1 是「通过 A 证明 B」，辩手很可能会换个措辞变成「利用 A 的特性推导 B 的结论」来绕过你的模糊匹配。**请说明：你的 `pruned_paths` 块如何实现「强制剪枝」？是否需要将这些路径提取为具体的「禁止关键词集合」或「逻辑负约束」，并强制注入到辩手的 Thinking 过程中？**

你的方案里充满了「建议」、「草稿」、「简要」这种词汇，这正是「正确的废话」。**给我看数据结构，给我看状态转移方程。**

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → (未解析)

*2026-03-12T15:41:30.801934*

下面先给结论，然后分别评价三位辩手的方案，并给出一套综合、可直接实现的设计（重点放在：**compact 输出长什么样、怎么生成、怎么增量更新**）。

---

## 一、总体立场：Compact =「辩论状态机快照」，而不是「精简聊天记录」

- compact 的产物应该是一个**结构化状态**，包括：
  - 双方当前立场（已替换初始立场）
  - 已达成共识
  - 正在争论的前沿问题
  - 已被否决/废弃的路径
  - 下一步应该怎么推进
- 给辩手看到的是这个状态的 **Markdown 渲染版**；
- 给系统使用的是同一状态的 **JSON 结构版**；
- 每次 compact 是：  
  `新状态 = f(旧状态, 上次 checkpoint 以来的新对话)`  
  而不是不断对全文、对旧摘要再摘要。

下面直接给出最终建议的 schema 和流程，之后再说明它是如何融合/取舍 Linus / Ssyram / 康德的方案的。

---

## 二、compact 输出的结构：JSON + Markdown 双层

### 2.1 内部状态 JSON Schema（核心）

定义一个 `CompactState`，作为 `compact_checkpoint.content` 的结构内容（可以是 JSON 或 YAML 字符串）：

```jsonc
{
  "compact_version": 1,
  "topic": {
    "current_formulation": "当前议题的精简描述（允许对原 topic 进行澄清/修正）",
    "notes": "（可选）对题目理解上的细微澄清"
  },
  "participants": [
    {
      "name": "辩手A",
      "stance_version": 3,
      "one_line_position": "一句话概括当前立场",
      "core_claims": [
        {
          "id": "A1",
          "text": "主结论/子结论：...",
          "status": "active"  // active / abandoned
        }
      ],
      "key_arguments": [
        {
          "id": "A1-arg1",
          "claim_id": "A1",
          "text": "支撑 A1 的关键论据",
          "status": "active"   // active / weakened
        }
      ],
      "assumptions": [
        {
          "id": "A-assump1",
          "text": "A 承认的关键前提或适用条件"
        }
      ],
      "admitted_weaknesses": [
        {
          "id": "A-w1",
          "text": "A 自己承认的弱点/不足",
          "related_claims": ["A1"]
        }
      ],
      "abandoned_claims": [
        {
          "id": "A0",
          "text": "【废弃】原主张：...",
          "reason": "被 B 指出事实错误 / 被自己承认逻辑不成立 / 被裁判否决",
          "decided_by": "self/opponent/judge",
          "ts": "2025-01-01T12:00:00Z"
        }
      ]
    },
    {
      "name": "辩手B",
      "...": "同上结构"
    }
  ],
  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点的1-2句说明",
      "status": "open", // open / partial_resolved / resolved
      "positions": {
        "辩手A": "A 在 D1 上的当前立场摘要",
        "辩手B": "B 在 D1 上的当前立场摘要"
      },
      "resolution": "若 status=resolved，在这里总结 consensus/裁决",
      "related_claims": ["A1", "B2"]
    }
  ],
  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实/前提：...",
      "source": "debate_consensus/judge"
    }
  ],
  "timeline_brief": [
    {
      "phase": 1,
      "title": "立场初步陈述",
      "summary": "这一阶段主要发生了什么（高度概括）"
    },
    {
      "phase": 2,
      "title": "围绕可行性的首次冲突",
      "summary": "..."
    }
  ],
  "pruned_paths": [
    {
      "id": "P1",
      "description": "尝试用「单一城市案例」外推出全国的路径",
      "reason": "被对方指出样本不具代表性，且当事方承认外推条件不成立",
      "decided_by": "opponent+self",
      "status": "no_reuse" // no_reuse / reuse_with_new_evidence
    }
  ],
  "open_questions": [
    {
      "id": "Q1",
      "text": "目前尚未解决的关键问题：...",
      "related_disputes": ["D1"],
      "suggested_focus": {
        "辩手A": "下一轮应优先解决 ...，避免重复 P1 的路径",
        "辩手B": "下一轮应优先对 ... 给出更强证据"
      }
    }
  ],
  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47,
    "created_at": "2025-01-01T12:00:00Z"
  }
}
```

**这层是“真正的辩论状态数据结构”，后续 compact 都基于它做增量更新。**

---

### 2.2 给辩手看的 Markdown 渲染格式

从 `CompactState` 生成一段简洁 Markdown，替换原来的「逐条发言记录」：

```markdown
# 辩论压缩快照 v1

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{participants[A].one_line_position}
- 辩手B：{participants[B].one_line_position}

---

## 2. 各辩手立场卡（Canonical State）

### 辩手A 立场卡（版本 {stance_version}）

- 当前核心主张：
  {列出 core_claims.status = active 的若干条}

- 关键论据：
  {列出 key_arguments.status = active 的要点}

- 承认的前提/适用范围：
  {assumptions 列表}

- 已承认的弱点：
  {admitted_weaknesses 列表（简化）}

- 明确放弃的主张（禁止原样再提出）：
  {abandoned_claims 列表，每条 1–2 句，包含理由}

### 辩手B 立场卡（版本 {stance_version}）

（同样格式）

---

## 3. 争点与共识

### 3.1 已达成共识（不应再争论）

{从 axioms + status=resolved 的 disputes 渲染列表}

### 3.2 仍在争论的核心焦点

对以下争点，需要继续推进（避免重复旧论点，只能提出新的论证或证据）：

{disputes.status in [open, partial_resolved]，每个输出：
- 争点编号 / 标题
- A 当前立场摘要
- B 当前立场摘要
- 当前状态：open / partial_resolved
}

---

## 4. 被否决的路径（不可再走的路）

以下推理或论证路径已被事实/逻辑否决，除非有**重大新证据**，不应重复使用：

{从 pruned_paths.status = no_reuse 渲染列表，每条包括：
- 路径说明
- 否决理由
- 谁否决的
}

---

## 5. 演进简史（仅保留关键节点）

{从 timeline_brief 渲染 3–7 条时间节点，帮助模型理解“已经走过哪些阶段”}

---

## 6. 当前未决问题与下一步建议

当前尚未解决的关键问题：

{从 open_questions 渲染 id + text}

下一轮建议：

- 对辩手A：{open_questions[*].suggested_focus.辩手A 的合并版}
- 对辩手B：{同上}
```

**优先级裁剪**（token 紧张时）：

1. 最高优先：  
   - 各辩手立场卡（尤其 core_claims / abandoned_claims）  
   - 仍在争论的核心焦点（3.2）  
   - 被否决路径（4）
2. 次优：  
   - 已达成共识（3.1）  
   - 当前未决问题与下一步建议（6）
3. 可精简：  
   - 演进简史（5）  
   - 议题长描述 & notes

实现上写一个 `render_markdown(state, max_tokens=None)`，按优先级拼装+截断。

---

## 三、LLM 摘要流程：分步“填表”+ 专用 compact 模型

### 3.1 专用 compact 模型 & 提前触发

配置增加：

```yaml
compact:
  model: "your-compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

使用原则：

- 所有 compact 一律用 `compact.model`，不依赖任何辩手模型；
- 在构造辩手下一轮上下文时，如果预估：
  `current_log_tokens + expected_reply_tokens > soft_trigger_ratio * debater_model_limit`  
  则先调用 compact，再喂 compact_text 给辩手；
- 如果 compact 调用失败，用简单降级策略（只截取最近 N 条发言 + 上一个 compact 快照的简略版）。

### 3.2 增量 compact 流程（核心）

伪代码：

```python
def build_compact_context(log: Log) -> CompactState:
    last_cp = log.last_compact_checkpoint()  # 可能返回 None
    if last_cp is None:
        old_state = None
        covered_end = 0
    else:
        old_state = json.loads(last_cp.content["state"])
        covered_end = last_cp.content["state"]["meta"]["covered_seq_end"]

    new_entries = log.entries_after(covered_end)  # 原始发言（排除 thinking/meta 等）

    # Step 1: 预压缩新 entries 为短 summary（可选）
    new_segment_summary = summarize_raw_entries(new_entries)

    # Step 2: 调用 compact_model 更新状态
    new_state = update_compact_state_with_llm(
        model=compact_model,
        old_state=old_state,
        new_entries_text=new_segment_summary or raw_text(new_entries)
    )

    # Step 3: 控制体积（裁剪 timeline/pruned_paths 等）
    new_state = shrink_state_if_needed(new_state)

    return new_state
```

### 3.3 LLM“填表式”更新：拆三步调用

可以用一次调用搞定，但工程上更稳的是 2–3 步流水线（调用同一个 compact 模型，避免单次输出崩掉全局格式）：

#### 调用 A：更新争点与共识（topic / disputes / axioms）

输入：

- `old_state.topic / disputes / axioms`（如有）
- 新对话片段文本

任务：

- 对议题描述做必要微调（如发现误解）；
- 识别/更新争点列表 `disputes`：  
  - 新增新的争点 Dk  
  - 更新已有争点的 summary / status / resolution  
- 识别/更新 `axioms`：双方显式同意的前提/事实。

输出：只包含 `topic`, `disputes`, `axioms` 三部分的 JSON 片段。

#### 调用 B：更新各辩手立场卡（participants）

输入：

- `old_state.participants`（旧立场卡）
- 新对话片段中每个辩手的发言 + 对方的回应（可以简单按 name 分组）

任务：

- 对每个参与者：
  - 更新 `one_line_position`；
  - 更新/新增 `core_claims`（主张变化）；
  - 更新/新增 `key_arguments`；
  - 补充 `assumptions / weaknesses`；
  - 识别新出现的 `abandoned_claims`（包括：谁否决、理由）。

重点提示：

- 不要删除旧的 `abandoned_claims` 和仍然有效的核心主张；
- 当主张从 active → abandoned 时，一定要保留原文和否决理由。

输出：`participants` 片段的 JSON。

#### 调用 C：更新 timeline / pruned_paths / open_questions

输入：

- 更新后的 `topic / disputes / participants`（可拼一份摘要给模型看）
- 新对话片段（或其简要 summary）  

任务：

- 用极短的列表更新 `timeline_brief`（最多 N 条，最旧的合并）；
- 从新的对话中抽取：
  - `pruned_paths`: 被明确否决的“推理路径”（不仅是某个单一结论，而是「论证方式」）；
  - `open_questions`: 从 `disputes` + 当前立场综合出的“未来必须解决的问题”，并为每个辩手给出 1–2 句下一步建议。

输出：`timeline_brief`, `pruned_paths`, `open_questions` 片段。

#### 组合与校验

- 程序端合并 A/B/C 的结果为 `new_state`；
- 对一些关键属性做简单检查：
  - 若旧 `axioms` 中某条在新结果中完全消失，而对话中没有出现推翻它的内容，则认为模型误删 → 自动重试或强行保留旧 axioms；
  - 同理对 `abandoned_claims` / `pruned_paths` 做“不能凭空消失”规则。

---

## 四、增量压缩策略：防止信息衰减 & 原地打转

### 4.1 不对摘要再摘要，只对「old_state + delta」做更新

原则：

- 输入给 compact 模型的不再是「上一个 Markdown 文本」，而是 `old_state` 的 JSON（或结构化描述）+ 新对话片段；
- 模型的任务是「update state」，而不是「重新总结历史」。

这样：

- 不会出现“摘要再摘要”的多轮语义漂移；
- 旧状态中的关键信息（axioms / abandoned_claims / pruned_paths）只会被追加、精简描述，而不会被重写遗忘。

### 4.2 控制信息体积 & 防止关键信息被压缩掉

策略：

- `timeline_brief`: 只保留最近 5–7 个阶段；更早阶段合并为一条“早期阶段略述”；  
- `pruned_paths`: 只保留最近 M 条详细描述（如 M=10），更旧的合并成若干概括（例如“早期已有多次被否决的‘从个案直接外推整体’路径”）；  
- `abandoned_claims`: 保留全部（因为条目少且非常关键），但可以限制每条 text 长度（例如 1–2 句）。

同时在 Prompt 里明确：

> 你可以缩短语言和合并类似条目，但不得删除仍然有效的「共识（axioms）」和「已弃用/被否决的路径与主张」。

---

## 五、辩手视角的使用方式：防“回滚打转”

最后要落到：**辩手在看到 compact_text 时，如何被 “引导” 不再走废路**。

对辩手的 system prompt 增补：

1. 明确说明输入结构：

> 你将收到的不是原始对话，而是「辩论状态快照」。  
> 它包含：  
> - 各辩手当前立场卡（这是对你立场的最新定义，替代初始说明）；  
> - 已达成共识；  
> - 正在争论的核心焦点；  
> - 已被明确否决的路径和废弃主张；  
> - 当前未决问题和给你的行动建议。

2. 明确禁止行为：

> 你不得：
> - 再次把「已明确放弃的主张」当作自己的论点提出；
> - 再次沿用「被否决的路径」中的推理方式（即使换言之）；
> - 在没有新理由或新证据时，质疑已经列入「已达成共识」的内容。

3. 建议自检步骤（可以让工具用 `thinking` tag 承载）：

> 在正式输出前，请在内部先检查：  
> - 我本轮要回答的是哪个 `open_questions` 或哪一个 `disputes`？  
> - 我是否无意中重复了「abandoned_claims」或「pruned_paths」中被否决的观点或论证方式？  
> 只有通过检查后，再生成对外发言。

---

## 六、与三位辩手方案的整合与取舍

- **继承自 Linus 的点**  
  - 「状态快照」视角，而非纯聊天摘要；  
  - 强结构化、类似 YAML/JSON 的 schema；  
  - 显式记录被否决路径和立场演进；  
  - 优先级有序的 Markdown 渲染。

- **继承自 Ssyram 的点**  
  - 把 compact 看成 `State` 的函数式更新：`State' = f(State, Delta)`；  
  - 明确 `axioms / active_frontiers(pruned_paths)` 三分法；  
  - 引入 `CompactManager`/类似组件抽象，隔离压缩逻辑。

- **继承自康德的点**  
  - 立场卡作为「canonical state」，覆盖初始立场；  
  - Timeline 只记“跳变点”；  
  - `Next Steps` 作为防止原地打转的关键区块；  
  - 多次小调用「填表式生成」而非一次大文本。

- **刻意不做的事**  
  - 不让 compact 使用辩手模型（避免 token/endpoint 约束纠缠）；  
  - 不对旧 Markdown 文本再摘要，而是始终使用 JSON 状态作为输入；  
  - 不试图完全还原对话，只保留“状态”和“关键轨迹”。

---

如果你愿意，下一步可以直接做两件非常具体的工程工作：

1. 我帮你写出三套 Prompt 模板（A/B/C），分别用于更新 `disputes+axioms`、`participants`、`timeline+pruned_paths+open_questions`，包含中英文注释；
2. 给出一个简化版 `CompactManager` 类的 Python 代码骨架，你可以直接嵌到 `debate-tool` 里试跑。

---


### [7] Linus Torvalds

*2026-03-12T15:42:08.281456*

直接从结论开始：  
**compact 输出应该是一个“辩论状态机的快照”，而不是精简聊天记录；形态上是：内部 JSON 状态 + 对辩手的 Markdown 渲染。**  
下面给一个可落地、兼容你现有架构的设计，覆盖你现在四个问题。

---

## 1. 输出区块设计：compact 之后辩手看到什么？

### 1.1 内部状态结构（CompactState JSON）

`compact_checkpoint.content` 建议存成一个对象：

```jsonc
{
  "state": { ...CompactState JSON... },
  "markdown": "渲染给辩手看的文本"
}
```

核心是 `state`，示例 schema（可以稍简化）：

```jsonc
{
  "compact_version": 1,

  "topic": {
    "current_formulation": "当前议题的精简版描述（允许修正/澄清）",
    "notes": "（可选）对题目理解上的补充说明"
  },

  "participants": [
    {
      "name": "辩手A",
      "stance_version": 3,
      "one_line_position": "一句话概括 A 当前立场",

      "core_claims": [
        { "id": "A1", "text": "主张1...", "status": "active" },   // active / abandoned
        { "id": "A2", "text": "主张2...", "status": "active" }
      ],

      "key_arguments": [
        { "id": "A1-arg1", "claim_id": "A1", "text": "支撑 A1 的关键论据", "status": "active" }
      ],

      "assumptions": [
        { "id": "A-assump1", "text": "A 承认的关键前提/适用条件" }
      ],

      "admitted_weaknesses": [
        { "id": "A-w1", "text": "A 承认的弱点", "related_claims": ["A1"] }
      ],

      "abandoned_claims": [
        {
          "id": "A-ab1",
          "text": "【废弃】原主张：...",
          "reason": "被 B 反驳/自己承认/裁判裁定，理由：...",
          "decided_by": "self/opponent/judge",
          "ts": "2025-01-01T12:00:00Z"
        }
      ]
    },

    { "name": "辩手B", "...": "同上结构" }
  ],

  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点 1-2 句说明",
      "status": "open",   // open / partial_resolved / resolved
      "positions": {
        "辩手A": "A 在 D1 上的当前立场摘要",
        "辩手B": "B 在 D1 上的当前立场摘要"
      },
      "resolution": "若已 resolved，这里描述共识/裁决，否则空",
      "related_claims": ["A1", "B2"]
    }
  ],

  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实/前提：...",
      "source": "debate_consensus/judge"
    }
  ],

  "timeline_brief": [
    {
      "phase": 1,
      "title": "立场初始陈述",
      "summary": "这一阶段主要发生了什么（高度概括）"
    },
    {
      "phase": 2,
      "title": "围绕可行性的首次激烈冲突",
      "summary": "..."
    }
  ],

  "pruned_paths": [
    {
      "id": "P1",
      "description": "尝试用「单一城市案例」外推出全国的路径",
      "target": "想证明全国可行",
      "reason": "被指出样本不具代表性，当事方承认外推条件不成立",
      "decided_by": "opponent/self/judge",
      "status": "no_reuse"   // no_reuse / reuse_with_new_evidence / partially_invalid
    }
  ],

  "open_questions": [
    {
      "id": "Q1",
      "text": "目前尚未解决的关键问题：...",
      "related_disputes": ["D1"],
      "suggested_focus": {
        "辩手A": "下一轮应优先解决 ...，避免重复 P1 的路径",
        "辩手B": "下一轮应优先对 ... 给出更强证据"
      }
    }
  ],

  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47,
    "created_at": "2025-01-01T12:00:00Z"
  }
}
```

特点：

- **立场卡是 canonical**：以后每轮喂给辩手的，不再是 topic 里原始立场，而是 `participants[*]`。
- **三块防打转结构**：
  - `axioms` + `disputes`（已共识 / 争点）
  - `abandoned_claims`（废弃主张）
  - `pruned_paths`（被否决的推理路径）

---

### 1.2 给辩手看到的 Markdown

`compact_text` 就从 `state` 渲染为 Markdown，替换原来的逐条日志：

```markdown
# 辩论压缩快照 v{compact_version}

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{A.one_line_position}
- 辩手B：{B.one_line_position}

---

## 2. 各辩手立场卡（当前版本）

### 辩手A 立场卡（版本 {A.stance_version}）

- 当前核心主张：
  - {active core_claims 简洁列出}

- 关键论据：
  - {active key_arguments 列出主要几条}

- 承认的前提/适用范围：
  - {assumptions 关键几条}

- 已承认的弱点：
  - {admitted_weaknesses 简化}

- 明确放弃的主张（不得原样再提出）：
  - {abandoned_claims，每条：主张+否决主体+理由}

### 辩手B 立场卡（版本 {B.stance_version}）

（同样格式）

---

## 3. 争点与共识

### 3.1 已达成共识（不应再争论）

- {从 axioms + disputes.status=resolved 渲染列表}

### 3.2 仍在争论的核心焦点

- [D1] {disputes[0].title}
  - A 当前立场：{positions.A}
  - B 当前立场：{positions.B}
  - 当前状态：{open/partial_resolved}

- [D2] ...

---

## 4. 被否决的路径（不可再走的路）

以下推理/论证路径已被事实或逻辑否决，除非有重大新证据，不应重复使用：

- [P1] {description}
  - 试图证明：{target}
  - 否决原因：{reason}
  - 否决方式：{decided_by 描述}

- [P2] ...

---

## 5. 演进简史（只保留关键节点）

{从 timeline_brief 渲染 3–7 条阶段说明，帮助模型理解「已经走过哪些阶段」}

---

## 6. 当前未决问题与下一步建议

当前尚未解决的关键问题：

- [Q1] {text}
- [Q2] ...

下一轮建议：

- 对辩手A：{合并所有 Q*.suggested_focus.A}
- 对辩手B：{合并所有 Q*.suggested_focus.B}
```

**优先级（token 不够时裁剪顺序）**：

1. 必须保留：
   - 两个立场卡（尤其 active claims + abandoned_claims）
   - 3.2 争点（仍在争论的核心问题）
   - 4 被否决路径
2. 其次：
   - 3.1 共识（axioms + resolved disputes）
   - 6 下一步建议
3. 最后可裁剪：
   - 5 演进简史
   - 1 中议题 notes

实现：`render_markdown(state, max_tokens=None)` 里，按区块追加 + 估算长度，超出时从低优先级开始丢。

---

## 2. LLM 摘要流程：用什么 prompt、如何分步、自动 compact 时模型不可用怎么办？

### 2.1 专用 compact 模型 + 提前触发

配置里加一个专门段：

```yaml
compact:
  model: "your-compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

使用策略：

- 所有 compact 一律用这个 `compact.model`，不要用辩手 A/B 的 endpoint；  
- 构造辩手上下文时，如果：

  ```text
  已有日志 tokens + 预估本轮回复 tokens > debater_model_limit * soft_trigger_ratio
  ```
  
  就先 compact，再让辩手继续；  
- compact 调用失败时的降级：  
  最近 N 条发言 + 上一个 checkpoint 的简短截断文本，简单标注「历史被截断，可能略有复读」，作为 fallback。

这样避免「真正超限才 compact」导致原模型不可用的死锁。

---

### 2.2 增量 compact：f(旧状态, 新 entries) → 新状态

你现有 `Log` 流程可以这样接上：

```python
def build_compact_context(log: Log, compact_model) -> dict:
    last_cp = log.last_compact_checkpoint()  # 返回最后一个 checkpoint entry 或 None

    if last_cp is None:
        old_state = None
        covered_end = 0
    else:
        cp_content = json.loads(last_cp["content"])
        old_state = cp_content["state"]
        covered_end = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(covered_end)  # 只取发言/质询/summary，排除 thinking/meta/human
    new_entries_text = format_entries_for_compact(new_entries)  # 简单拼接成文本

    new_state = incremental_compact_with_llm(
        model=compact_model,
        old_state=old_state,
        new_entries_text=new_entries_text,
        covered_start=1 if old_state is None else old_state["meta"]["covered_seq_start"],
        covered_end=log.last_seq()
    )

    markdown = render_markdown(new_state)

    # 写入 log
    log.add(
        name="Compact Checkpoint",
        tag="compact_checkpoint",
        content=json.dumps({"state": new_state, "markdown": markdown}, ensure_ascii=False)
    )

    return new_state, markdown
```

核心是 `incremental_compact_with_llm`，它只做：

> old_state（可以为 None） + 新对话文本 → new_state （JSON）

**不再重新 summarize 整段历史，也不再对旧 Markdown 摘要再摘要。**

---

### 2.3 填表式多步调用（而不是一次性大块）

为了稳，建议拆成 3 个调用（都用 compact_model）：

#### 调用 A：更新 topic / disputes / axioms

输入（user）大致：

- 当前 old_state 中的 `topic`, `disputes`, `axioms`（若无则为空列表）；
- 新对话文本（从上个 checkpoint 之后）；

系统指示（伪）：

> 你是辩论记录维护助手。  
> 你将收到旧的辩论状态片段（topic, disputes, axioms）和一段新增对话。  
> 你的任务是：在旧状态基础上，增量更新这三部分。  
> - 可以：增加新的争点、更新争点状态、加入新的共识前提；  
> - 不可以：随意删除旧的共识/争点，除非新对话明确推翻它们。

输出 JSON：

```jsonc
{
  "topic": {...},
  "disputes": [...],
  "axioms": [...]
}
```

#### 调用 B：更新 participants（立场卡）

输入：

- old_state.participants（可空）
- 新对话文本，附带各条 entry 的 name（以便按辩手分段）

任务提示要点：

- 在旧立场卡基础上更新：one_line_position / core_claims / key_arguments / assumptions / admitted_weaknesses；
- 检出新增的 abandoned_claims：  
  - 某主张被明确否定且辩手承认不成立 / 裁判裁定不成立；
- 不要删除旧的 abandoned_claims，除非新对话**明确**恢复（这时可将 status 标成 active + 说明原因）。

输出 JSON：

```jsonc
{
  "participants": [ ... ]
}
```

#### 调用 C：更新 timeline_brief / pruned_paths / open_questions

输入：

- 调用 A/B 得到的 updated topic/disputes/participants；
- 新对话文本（或一个短 summary）；

任务：

- 增补 1–2 个时间节点到 timeline_brief（必要时合并过旧节点）；
- 从新增对话里抽取被明确否决的“推理路径” → pruned_paths（注意是“用什么方式证明什么”）；
- 基于最新 disputes / participants 产生 2–5 个 open_questions，并为每个参与者生成短建议。

输出 JSON：

```jsonc
{
  "timeline_brief": [...],
  "pruned_paths": [...],
  "open_questions": [...]
}
```

#### 合并与约束

在 Python 侧合并 A/B/C 的 JSON 为 new_state：

- topic / disputes / axioms ← A
- participants ← B
- timeline / pruned_paths / open_questions ← C
- meta.covered_seq_* 由本地填；  
- compact_version = old_state.compact_version + 1 或从 1 开始。

加一些简单规则防语义漂移：

- 若 old_state.axioms 中某条在新输出完全没出现，而新对话里也没有显式推翻的迹象：  
  → 直接把旧 axioms 那条合并回 new_state；
- 同理对 abandoned_claims / pruned_paths 做“不能凭空消失”检查。

---

## 3. 多次 compact：如何避免信息逐层衰减？

关键原则：**永远只更新 state，不对旧摘要再摘要。**

- `load_from_file()` 时：
  - 找最后一个 compact_checkpoint；
  - 解析其 `content.state` 作为 old_state；
  - 此后 entries 即为“delta 对话”。

- `build_compact_context()` 时：
  - 输入给 LLM 的不是之前的 Markdown，而是 old_state（JSON）+ delta 文本；
  - LLM 只干「更新 JSON」这件事。

为防“越压越少”：

- 共识（axioms）和被否决路径（pruned_paths）默认不可删除。  
  如果 LLM 输出时丢了很多条，程序可以：
  - warn + 自动把旧的补回去；
  - 或加一轮重试，附带“你删掉了这些旧共识，请保留”。

- timeline/pruned_paths 长度控制：
  - timeline 只保留最近 5–7 个节点，更早的合成一条 “早期阶段略述”；
  - pruned_paths 只保留最近 M 个详细记录（如 10），更早的合成 1–2 条概括性描述（也可由 LLM 在调用 C 中完成）。

- abandoned_claims 建议全保留（条目数量通常不会爆炸，而且对防复读极重要），只限制每条描述长度。

---

## 4. 演进表示与「不回滚打转」：怎么喂给辩手？

### 4.1 覆盖初始立场：立场卡是唯一真相源

后续每轮构造辩手上下文：

- 不再使用 topic 中的原始「双方立场描述」；
- 而是用：

```text
## 辩论议题
{topic.current_formulation}

## 辩论历史（压缩快照）
{markdown_from_compact}
```

这样模型自然以立场卡为准，不会沿着初始 topic 文案里的陈述打转。

---

### 4.2 System prompt 中明确约束

在辩手的 system prompt 里加几条强约束（简化版）：

> - 你收到的“辩论历史”是一个状态快照，而不是完整聊天记录；  
> - 你必须以其中的「立场卡」描述作为你和对方的最新立场，不再参考初始提示中的旧立场；  
> - 你不得：
>   - 再次把已列入「废弃主张」的内容当作自己的论点；
        （即使换个措辞也不行）
>   - 沿用「被否决的路径」中描述的论证方式；
>   - 在没有新证据或论证的情况下，否认「已达成共识/axioms」里的内容。

可选：在工具侧给每次辩手调用前，加一个短「thinking 自检」prompt（内部 tag 不给用户看）：

> 请先在内部检查：  
> 1. 你本轮想讨论的争点/问题是 state.disputes/open_questions 中的哪些？  
> 2. 你是否无意中要使用已列为「废弃主张」或「被否决路径」的思路？  
> 通过检查后，再生成对外发言。

这对大多数模型会明显减少“回滚打转”。

---

## 5. 对你四个问题的直接回答

1. **输出区块设计**  
   - 内部：一个 `CompactState` JSON（topic / participants / disputes / axioms / timeline / pruned_paths / open_questions / meta）；  
   - 对辩手：由 state 渲染成结构化 Markdown，有固定 6 个区块；  
   - 明确三块“防打转”区：废弃主张、被否决路径、共识 + 争点。

2. **LLM 摘要流程**  
   - 所有 compact 用一个专用 `compact_model`，与辩手模型解耦；  
   - 在 token 接近上限（例如 0.8）时提前 compact；  
   - 摘要过程拆成 3 次窄任务调用（更新 topic/disputes/axioms；更新 participants；更新 timeline/pruned_paths/open_questions），每次输出 JSON 片段；  
   - 合成 state 之后由代码渲染 Markdown。

3. **增量压缩**  
   - 每次 compact 的输入：上一个 checkpoint 的 `state` + 之后的原始 entries 文本；  
   - LLM 任务是“更新 state”，不是重写整个历史；  
   - 对 axioms/abandoned_claims/pruned_paths 做简单防删除检查，防止关键信息被误压掉。

4. **演进表示 / 被抛弃路径结构**  
   - 立场演进通过 `participants[*].core_claims + admitted_weaknesses + abandoned_claims` 表现——当前状态 + 被废弃的历史；  
   - 决策变迁与共识通过 `disputes + axioms + timeline_brief` 表现；  
   - 被抛弃路径用 `pruned_paths`（含：路径描述/目标/否决原因/否决者/状态）结构化记录，并在 system prompt 中禁止复用。

如果你想继续深入，下一步可以直接做两件事：  
- 定义一个最小版 `CompactState`（剥离掉你暂时用不到的字段）；  
- 我可以帮你写一套具体的中文 Prompt 模板（A/B/C 三步），以及 `incremental_compact_with_llm` 的骨架代码，直接能往 `debate-tool` 里塞。

---


### [8] Ssyram

*2026-03-12T15:42:08.281494*

我不接受任何带有「叙事性」的压缩方案。辩论不是写小说，是**在约束空间下的路径搜索**。

我支持「状态机快照」和「Canonical State」的结合，但必须将其形式化为 **State Transition Function**。Compact 的本质是将历史对话（Trace）投影到当前状态空间（State Space）。

### 1. 核心数据结构：`CompactState`

我们不需要「摘要」，我们需要一个能描述**搜索前沿（Search Frontier）**的结构。

```python
class CompactState(TypedDict):
    # 1. 逻辑公理：双方已确认不再争议的事实。后续推理的 Base Case。
    axioms: List[str] 
    
    # 2. 辩手 Canonical State：替换掉原始 topic 中的立场描述。
    # 包含：当前主张、已承认的弱点、[关键] 已废弃主张。
    player_states: Dict[str, PlayerState] 
    
    # 3. 剪枝路径（Negative Constraints）：这是防止原地打转的硬约束。
    # 记录：尝试过的路径 -> 失败理由（由谁证伪）。
    pruned_paths: List[Dict[str, str]] 
    
    # 4. 开放冲突点（Search Frontier）：当前正在交锋的逻辑节点。
    active_disputes: List[DisputeNode]
```

### 2. 转换函数：增量更新逻辑

拒绝「对全文重新总结」。Compact 必须是增量的，逻辑如下：

```python
def compact_transition(prev_state: CompactState, delta_entries: List[LogEntry]) -> CompactState:
    """
    状态转移方程: S_{n} = f(S_{n-1}, Δ)
    Δ 是自上次 Checkpoint 以来的原始对话。
    """
    # 1. 提取 Delta 中的逻辑增量（新共识、新冲突、被证伪的论点）
    diff = extract_logic_diff(prev_state, delta_entries)
    
    # 2. 更新状态机：
    # - 将 diff.consensus 合并入 axioms
    # - 将 diff.refuted_args 移入 player_states.abandoned_claims 和 pruned_paths
    # - 更新 active_disputes
    return apply_diff(prev_state, diff)
```

### 3. 攻击「建议区块」，支持「负向约束注入」

Linus 提到的「下一步建议」太弱了。模型经常无视建议，但它们对**负向约束（Negative Constraints）**非常敏感。

在喂给辩手的 Context 中，`pruned_paths` 不应只是「历史记录」，而应作为 **Forbidden Search Space** 注入到 System Prompt 或 Thinking 引导中：

```markdown
### 搜索空间约束 (Forbidden Paths)
- 禁止重提路径 P1: [论点 A -> 结论 B]，因 [逻辑矛盾/证据不足] 已被 [辩手 X] 证伪。
- 禁止使用主张 C: 已被标记为【废弃】。
```

这种「硬剪枝」是保证辩论不回滚的唯一形式化手段。

### 4. 落地决策

我要求在下一轮实现中，`debate-tool` 必须将 `compact_checkpoint` 分离为 `state` (JSON) 和 `view` (Markdown)。辩手读取 `view`，而下一次 compact 必须读取 `state` 作为输入基准。这是防止语义漂移（Semantic Drift）的底线。

---


### [9] 康德（Immanuel Kant）

*2026-03-12T15:42:08.281514*

下面直接给出我自己的设计立场和方案，会尽量结合上轮三位辩手的内容，但不复述，只在有分歧处做取舍，并紧贴你现在的架构约束。

---

## 一、我对「compact 后辩手应该看到什么」的核心结论

1. `compact_checkpoint` 的本质应该是 **“辩论状态机快照”**，而不是「缩短的对话记录」。
2. 辩手看到的东西应该明确回答四件事：
   - 现在各方到底站在哪些结论上（当前立场卡）
   - 哪些东西已经被大家承认（共识/axioms）
   - 哪些推理路径已经被判死刑（被否决路径）
   - 还剩哪些关键问题值得继续推（开放问题/next steps）
3. 这些信息本质上是一个固定 schema 的状态结构（JSON / YAML），**渲染成 Markdown** 给辩手看；  
   LLM 压缩时操作的是这个状态，而不是原始对话全文。

下面按你问的四个问题逐一回答。

---

## 二、问题 1：输出区块设计（compact_text 结构）

### 2.1 内部状态：CompactState（JSON）

建议把 `compact_checkpoint.content` 改成一个结构化对象（可以是 JSON 字符串），包含一个 `state`，形如：

```jsonc
{
  "compact_version": 1,
  "topic": {
    "current_formulation": "当前议题的精简描述，可在首次压缩时重写",
    "notes": "对题目理解的澄清（可选）"
  },
  "participants": [
    {
      "name": "辩手A",
      "stance_version": 3,
      "one_line_position": "一句话概括 A 当前立场",
      "core_claims": [
        {"id": "A1", "text": "主结论或子结论 1", "status": "active"},
        {"id": "A2", "text": "主结论或子结论 2", "status": "active"}
      ],
      "key_arguments": [
        {"id": "A1-arg1", "claim_id": "A1", "text": "支撑 A1 的关键论据", "status": "active"},
        {"id": "A2-arg1", "claim_id": "A2", "text": "支撑 A2 的关键论据", "status": "active"}
      ],
      "assumptions": [
        {"id": "A-assump1", "text": "A 承认的关键前提/适用条件 1"}
      ],
      "admitted_weaknesses": [
        {"id": "A-w1", "text": "A 自己承认的弱点/不足", "related_claims": ["A1"]}
      ],
      "abandoned_claims": [
        {
          "id": "A-ab1",
          "text": "【废弃】原主张：...",
          "reason": "被 B 指出事实错误 / 自己承认逻辑不成立 / 被裁判否决",
          "decided_by": "self/opponent/judge",
          "ts": "2025-01-01T12:00:00Z"
        }
      ]
    },
    {
      "name": "辩手B",
      "stance_version": 2,
      "one_line_position": "...",
      "core_claims": [...],
      "key_arguments": [...],
      "assumptions": [...],
      "admitted_weaknesses": [...],
      "abandoned_claims": [...]
    }
  ],
  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点的一句话概述",
      "status": "open",    // open / partial_resolved / resolved
      "positions": {
        "辩手A": "A 在 D1 上的当前立场摘要",
        "辩手B": "B 在 D1 上的当前立场摘要"
      },
      "resolution": "",     // 若 resolved，则在这里写结论
      "related_claims": ["A1", "B2"]
    }
  ],
  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实或前提：...",
      "source": "debate_consensus/judge"
    }
  ],
  "timeline_brief": [
    {
      "phase": 1,
      "title": "立场初步陈述",
      "summary": "这一阶段主要发生了什么（高度概括，不超过 2–3 句）"
    },
    {
      "phase": 2,
      "title": "围绕可行性的首次冲突",
      "summary": "..."
    }
  ],
  "pruned_paths": [
    {
      "id": "P1",
      "description": "尝试用“单一城市案例”直接外推出全国可行性",
      "target": "全国范围结论",
      "reason": "被指出样本不具代表性，且当事方承认外推条件不成立",
      "decided_by": "opponent+self",
      "status": "no_reuse" // no_reuse / reuse_with_new_evidence / partially_invalid
    }
  ],
  "open_questions": [
    {
      "id": "Q1",
      "text": "目前尚未解决的关键问题：...",
      "related_disputes": ["D1"],
      "suggested_focus": {
        "辩手A": "下一轮应优先针对 ...，避免重复走 P1 路径",
        "辩手B": "下一轮应优先巩固 ...，并回应 ... 的质疑"
      }
    }
  ],
  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47,
    "created_at": "2025-01-01T12:00:00Z"
  }
}
```

这就是「辩论状态」的唯一真源。后续每次 compact 都是 `new_state = f(old_state, delta_entries)`。

---

### 2.2 对辩手暴露的 compact_text（Markdown）

`compact_text` 就是对上面 `CompactState` 的渲染：

```markdown
# 辩论压缩快照 v1

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{A.one_line_position}
- 辩手B：{B.one_line_position}

---

## 2. 各辩手立场卡（当前版本）

### 辩手A 立场卡（版本 {A.stance_version}）

- 当前核心主张：
  - {A.core_claims 中 status=active 的若干条（1–3 条）}

- 关键论据：
  - {A.key_arguments 中 status=active 的要点（1–3 条）}

- 承认的前提/适用范围：
  - {A.assumptions}

- 已承认的弱点：
  - {A.admitted_weaknesses}

- 明确放弃的主张（不得原样再用）：
  - {A.abandoned_claims，每条 1–2 句，包含 reason / decided_by}

### 辩手B 立场卡（版本 {B.stance_version}）

（同上结构）

---

## 3. 争点与共识

### 3.1 已达成共识（不应再反复争论）

- {由 axioms + status=resolved 的 disputes 渲染，一条一句话}

### 3.2 仍在争论的核心焦点

- [D1] {disputes[0].title}
  - A 当前立场：{disputes[0].positions["辩手A"]}
  - B 当前立场：{disputes[0].positions["辩手B"]}
  - 当前状态：{disputes[0].status}

（按需列出 2–5 个）

---

## 4. 被否决的推理路径（不可再走的路）

以下路径已被认为行不通，除非有重大新证据，不应再使用同样的推理方式：

- [P1] {pruned_paths[0].description}
  - 目标结论：{target}
  - 否决原因：{reason}
  - 决策方式：{decided_by}
  - 状态：{status}

（只保留最近若干条，老的可以合并）

---

## 5. 演进简史（仅保留关键节点）

- 阶段 {phase}: {title} —— {summary}

（3–7 条，帮助模型理解已经走过哪些阶段）

---

## 6. 当前未决问题与下一步建议

当前尚未解决的关键问题：

- [Q1] {open_questions[0].text}
- [Q2] ...

下一轮建议：

- 对辩手A：{合并 open_questions[*].suggested_focus["辩手A"]}
- 对辩手B：{同上}
```

**优先级（token 不够时）**：

1. 必保：
   - 2. 立场卡（尤其 core_claims / abandoned_claims）
   - 3.2 仍在争论的焦点
   - 4. 被否决路径
2. 次保：
   - 3.1 共识
   - 6. 下一步建议
3. 可精简：
   - 1. 议题长描述
   - 5. 演进简史

可以写一个简单的 `render_markdown(state, max_tokens=None)` 函数按优先级分段截断。

---

## 三、问题 2：LLM 摘要流程与「原模型不可用」

### 3.1 专用 compact 模型 & 触发时机

**配置上增加专门的 compact 模型**，与辩手模型完全解耦：

```yaml
compact:
  model: "compact-llm-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

使用原则：

- 所有 compact 调用都用这一个 `compact_model`，不依赖辩手自己的 endpoint/限制；
- 每轮准备辩手上下文前，预估：
  `log_tokens + 预估回复_tokens > soft_trigger_ratio * debater_max_tokens`
  → 先 compact，再让辩手继续；
- 如果 compact 调用失败，fallback 为“简单裁剪策略”：保留最近 N 条发言 + 上一次 compact 的极简摘要，并在快照里显式标注「压缩失败，历史可能不完整」。

这样自动 compact 时就不会出现「原模型不可用」的问题。

### 3.2 分步“填表”而不是一次大块

为了减少一次输出结构崩掉的概率，我建议 **最多三步 LLM 调用**，每步产出一个片段 JSON，由代码合并：

1. **调用 A：更新 topic / disputes / axioms**

   - 输入：
     - `old_state.topic / disputes / axioms`（或空）
     - `new_entries_text`（上次 checkpoint 以来的新对话 raw 或 summary）
   - 输出：
     - `{ "topic": ..., "disputes": [...], "axioms": [...] }`

   Prompt 核心指示：
   - 识别新增或变化的争点（disputes），更新其 status/positions；
   - 识别双方显式同意的前提/事实，输出 axioms；
   - 不要随意删除旧 axioms，除非新对话明确推翻它们。

2. **调用 B：更新 participants（立场卡）**

   - 输入：
     - `old_state.participants`
     - `new_entries_text` 按辩手分组的发言（可通过简单过滤 `name`）
   - 输出：
     - `{ "participants": [ ... ] }`

   Prompt 核心指示：
   - 在旧立场卡基础上增量更新：
     - 修改 `one_line_position`；
     - 增加或修正 `core_claims`；
     - 增加或修正 `key_arguments` / `assumptions` / `admitted_weaknesses`；
     - 标记新的 `abandoned_claims`（包含原因与 decided_by）。
   - 不要删除旧的 `abandoned_claims`，除非新对话明确指出之前是误判且被共同推翻。

3. **调用 C：更新 timeline_brief / pruned_paths / open_questions**

   - 输入：
     - 前两步合并出的暂时 `topic + disputes + participants + axioms`
     - `new_entries_text` 或其简要摘要
   - 输出：
     - `{ "timeline_brief": [...], "pruned_paths": [...], "open_questions": [...] }`

   Prompt 核心指示：
   - timeline 只记录真正“改变局面”的 1–2 个新节点；
   - 识别新的被否决「推理路径」（不是单个观点，而是论证方式），填入 `pruned_paths`；
   - 根据当前 disputes 状态和 participants 立场，给出 2–5 个 open_questions，并为各辩手写简短建议。

最后由代码 merge 三个 JSON 片段为 `new_state`，填补 old_state 未被提及字段（例如某步没输出某字段，就沿用旧值）。

---

## 四、问题 3：增量压缩与避免信息逐层衰减

### 4.1 严格采用「旧状态 + 新对话 → 新状态」

`build_compact_context()` 的输入应该是：

- `old_state`: 上一次 `compact_checkpoint` 的 `state`（JSON）；
- `new_entries`: 从 `old_state.meta.covered_seq_end` 之后的所有条目（原始对话）。

伪代码：

```python
def build_compact_context(log: Log) -> CompactState:
    last_cp = log.last_compact_checkpoint()
    if last_cp is None:
        old_state = None
        start_seq = 0
    else:
        old_state = json.loads(last_cp.content["state"])
        start_seq = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(start_seq, exclude_tags=["thinking", "meta"])

    new_entries_text = format_entries_as_plain_text(new_entries)

    new_state = update_state_with_llm(old_state, new_entries_text)

    new_state["meta"]["covered_seq_start"] = 1 if old_state is None else old_state["meta"]["covered_seq_start"]
    new_state["meta"]["covered_seq_end"] = log.last_seq()

    return new_state
```

这里关键是：**不再把旧的 Markdown 压缩文本丢回模型让它再摘要**，而是用结构化的 old_state 作为“事实基座”，只对 delta 做更新。

### 4.2 防信息衰减的约束

在 Prompt 和代码两层加限制：

- **共识（axioms）和被否决路径（pruned_paths）原则上不可消失**  
  - Prompt 里写明：旧条目除非新对话明确推翻，否则不能删除，只能：
    - 保留原样；
    - 合并多个类似条目为更概括的一条；
  - 代码做 sanity check：如果新 axioms 数量明显减少（比如减半），且对话中没出现“推翻”的迹象，可以自动重试或强行保留旧条目。

- **timeline_brief 与 pruned_paths 限长**  
  - timeline 只保留最近 K 条（比如 5–7），老的合并成一条“早期阶段概括”；
  - pruned_paths 只保留最近若干重要的路径（例如按出现频次或严重程度选择 top N），其余合并成一条总括性的「早期已有多个‘从个案直接外推整体’的路径被否决」。

- **abandoned_claims 和 axioms 不裁剪**  
  - 这两类信息数量通常不多、且是防回滚打转的核心，宁可缩短文本也不要删条目；
  - 可以限制每条描述长度（1–2 句），而不是限制条数。

---

## 五、问题 4：演进表示 & 被抛弃路径的数据结构

你要解决的是：

- 立场如何演变；
- 哪些东西被抛弃，不能再回去走；
- 决策变迁（共识/裁决）如何长期保留。

上述 `CompactState` 已经把这些拆成几个维度：

1. **立场演进**  
   - 存在 `participants[*].core_claims / key_arguments / assumptions / admitted_weaknesses / abandoned_claims`；
   - 当前版本立场由 `core_claims(status=active)` 表示；
   - 演进轨迹由 `timeline_brief`（阶段概述）+ `abandoned_claims`（被放弃主张）间接表达。

2. **被抛弃路径**  
   - 用 `pruned_paths` 记录的是「推理方式」被否决；
   - 包含 description（一句话结构）、target、reason、decided_by、status；
   - 辩手下一轮看到这些，system prompt 强调「禁止再用这些路径」。

3. **决策变迁**  
   - 用 `axioms` 表示已共同接受的前提/事实；
   - 用 `disputes.status + resolution` 表示「某个争点从 open → resolved」的结果；
   - `timeline_brief` 用来记录这些状态变迁的大节点，避免模型把“当前状态”误解回早期阶段。

---

## 六、如何让辩手实际“用起来”，而不是回到老路

最后一步需要改 system prompt（或辩手的固定前文）：

1. 告知输入性质：

> 你收到的是“辩论状态快照”，而不是完整历史记录，其中包含：
> - 当前各方立场卡（替代初始立场描述）
> - 已达成共识
> - 正在争论的关键焦点
> - 已被否决的推理路径和废弃主张
> - 当前未决问题和对你的行动建议

2. 明确约束：

> 你在后续发言中：
> - 不得再把【废弃】主张或 `abandoned_claims` 中的内容当作自己的论点；
> - 不得再使用 `pruned_paths` 中描述的推理方式（即使换用不同措辞），除非你明确说明你引入了新的关键证据，使该路径重新可行；
> - 不能在没有新理由的情况下质疑已经写入 axioms 的共识。

3. 要求自检（可以用 `thinking` tag 保留）：

> 在生成回答前，你应先在内部检查：
> - 我本轮要回应的是哪个争点（disputes）或哪个 open_questions？
> - 我拟采用的论点是否在 `abandoned_claims` 或 `pruned_paths` 中已经被否决？
> 如果发现冲突，必须调整论点。

---

## 最后一句总结

对你的问题的直接回答：

1. **输出区块设计**：  
   用一个固定 `CompactState` JSON 结构记录：topic / participants（立场卡+废弃主张）/ disputes / axioms / pruned_paths / timeline / open_questions；  
   渲染成 Markdown 给辩手，重点是立场卡 + 共识&争点 + 被否决路径 + 下一步建议。

2. **LLM 摘要流程**：  
   用一个独立的 `compact_model`，在 token 将近软上限时主动触发；  
   采用 2–3 步“填表式”调用（更新争点/共识 → 更新立场卡 → 更新时间线&否决路径&开放问题），最后由代码合并。

3. **增量压缩**：  
   每次 compact 的输入是「上次状态 JSON + 上次 checkpoint 之后的新对话」，输出新的状态；  
   不对旧 Markdown 再摘要，避免多轮语义衰减；  
   共识和被否决路径不轻易删除，只允许合并/简化。

4. **演进表示**：  
   立场演进用 participants 中的 active/abandoned claims + weaknesses；  
   决策变迁用 axioms + disputes.status + timeline；  
   被抛弃路径用结构化 pruned_paths，明确禁止再次使用。

这套设计在你的现有架构上实现成本相对可控：  
核心改动就是：新增 `CompactState` schema、一个 `CompactManager`（封装三步 LLM 调用+合并），以及一个 `render_markdown`。

---


### [10] 🔍 **质询** Linus Torvalds → (未解析)

*2026-03-12T15:42:51.390963*

下面是我对三位辩手 2 轮发言的「综合立场 + 局部取舍」——直接回答你这轮隐含的问题：  
**现在已经有了一个相当完整的方案雏形，下一步应该怎么收敛成可实现的设计？**

我不会重复他们的内容，只说**我赞同什么、反对什么、怎么具体落地**。

---

## 一、整体方向：我支持「状态快照 + JSON 内核 + Markdown 视图」

三个人其实已经高度收敛在几个点上：

1. **compact 输出不应是“缩短的对话记录”，而是“辩论状态机快照”**  
   - 这个我完全认同；继续喂「聊天摘要」会导致模型不断产生“新摘要的摘要”，信息不可避免地漂移和衰减。
2. **检查点 entry 里要有两层东西**：  
   - `state`：结构化 JSON（或 YAML）——内部使用，增量更新的基准；  
   - `view`（或 `markdown`）：根据 state 渲染的文本 —— 辩手实际看到的内容。
3. **今后每次 compact 的输入应该是**：  
   - 上一次的 `state`  
   - + 上次 checkpoint 之后的新增 entries 文本  
   → 输出新的 `state`，再渲染成 Markdown。

我建议你直接采纳这一共识，这是整个设计是否稳固的关键。

---

## 二、在三种风格里做选择：我会这样取舍

### 2.1 Linus：偏工程实践 + 强结构化

- 我基本完全同意他给出的 `CompactState` schema 风格和 Markdown 区块拆分。
- 优点：
  - 和你现有的 log 架构贴合，容易嵌进去；
  - 对「立场卡」、「被否决路径」、「共识/争点」拆得足够细。
- 建议：  
  把他的 JSON schema 做一个**精简版**作为 v1，不要一上来就堆满所有字段（比如时间戳可以先不强制）。

### 2.2 Ssyram：强调「搜索空间」和「负向约束」

他提醒了两个非常重要的点：

1. **compact 本质是 State Transition Function**：  
   `S_n = f(S_{n-1}, Δ)`，而不是「重新总结全部历史」。这点对防信息衰减是刚性要求，我完全赞同。
2. **负向约束（Forbidden Paths）要写成“硬约束”**：  
   - 不只是记录「曾经失败过」，而是要在辩手上下文里被明确标为：
     - 禁止再次使用的主张；
     - 禁止再次使用的推理路径。
   - 这点比「下一步建议」更有约束力。

我会把这两点直接融合进最后方案里——尤其是 `pruned_paths` 在对辩手的 prompt 中要以「禁止事项」的口吻出现，而不是“历史回顾”。

### 2.3 康德：整体方案整合 + 系统提示的约束

康德这轮基本就是在把以上两种风格做成一份「可直接照抄的设计文档」；  
我认为他已经给出了最接近你可以直接落地的方案：

- 完整的 `CompactState` 结构；
- Markdown 渲染布局；
- 三步 “填表式” LLM 过程（A/B/C）；
- System prompt 中对辩手的行为约束。

我会在此基础上做一点“工程层面的收缩”——去掉 v1 实现里可能属于“过度设计”的部分，让你能快速把第一版跑起来。

---

## 三、我建议你 v1 真的落地的 schema（精简版）

### 3.1 `compact_checkpoint.content` 形式

建议就用 JSON 字符串，结构是：

```jsonc
{
  "state": { ...CompactState... },
  "markdown": "给辩手看的渲染文本"
}
```

其中 `state` 采用**精简版** schema：

```jsonc
{
  "compact_version": 1,

  "topic": {
    "current_formulation": "当前议题的精简描述",
    "notes": "对题目理解和边界的补充（可选）"
  },

  "participants": [
    {
      "name": "辩手A",
      "stance_version": 1,
      "one_line_position": "一句话概括 A 当前立场",

      "core_claims": [
        { "id": "A1", "text": "A 的核心主张 1", "status": "active" }
      ],

      "key_arguments": [
        { "id": "A1-arg1", "claim_id": "A1", "text": "支撑 A1 的关键论据", "status": "active" }
      ],

      "abandoned_claims": [
        {
          "id": "A-ab1",
          "text": "【废弃】原主张：...",
          "reason": "被 B 反驳 / 自己承认 / 裁判裁定，理由：...",
          "decided_by": "self/opponent/judge"
        }
      ]
    },
    {
      "name": "辩手B",
      "stance_version": 1,
      "one_line_position": "...",
      "core_claims": [...],
      "key_arguments": [...],
      "abandoned_claims": [...]
    }
  ],

  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点一句话概述",
      "status": "open",   // open / resolved
      "positions": {
        "辩手A": "A 在 D1 上的当前立场",
        "辩手B": "B 在 D1 上的当前立场"
      },
      "resolution": ""     // resolved 时写共识/裁定
    }
  ],

  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实/前提：...",
      "source": "debate_consensus/judge"
    }
  ],

  "pruned_paths": [
    {
      "id": "P1",
      "description": "被否决的推理路径：如何如何证明什么",
      "reason": "否决原因：逻辑矛盾 / 证据不足 / 前提不成立",
      "decided_by": "self/opponent/judge",
      "status": "no_reuse"
    }
  ],

  "open_questions": [
    {
      "id": "Q1",
      "text": "尚未解决的关键问题",
      "related_disputes": ["D1"]
    }
  ],

  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47
  }
}
```

刻意删掉了 v1 不必要的字段：

- 去掉每条 `timeline_brief`（你可以之后再加）；
- 去掉时间戳等非必需 meta；
- `assumptions` / `admitted_weaknesses` 也可以先不加，如之后发现有必要再枚举。

这使得 v1 的实现更轻量，但又保留了三类关键信息：

1. 当前立场（`core_claims` / `key_arguments`）  
2. 已放弃主张与路径（`abandoned_claims` + `pruned_paths`）  
3. 共识与争点进度（`axioms` + `disputes.status`）

---

## 四、辩手实际要看到的 Markdown 结构（v1 版）

你可以直接约定 `compact_text` = 一次调用 `render_markdown(state)` 的结果，结构：

```markdown
# 辩论压缩快照 v{compact_version}

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{A.one_line_position}
- 辩手B：{B.one_line_position}

---

## 2. 各辩手当前立场

### 辩手A

- 核心主张：
  - {active core_claims，1–3 条}

- 关键论据：
  - {active key_arguments，1–3 条}

- 已明确放弃的主张（不得再次使用）：
  - {abandoned_claims，每条 1 行，带 reason/decided_by}

### 辩手B

（同上）

---

## 3. 共识与争点

### 3.1 已达成共识（不应再反复争论）

- {axioms 列表，每条一句话}

### 3.2 当前仍在争论的焦点

- [D1] {title}
  - A：{positions["辩手A"]}
  - B：{positions["辩手B"]}
  - 状态：{status}

（最多列 3–5 个）

---

## 4. 被否决的推理路径（禁止再走）

以下推理方式已经被明确否决，除非有重大新证据，不应再使用：

- [P1] {description}
  - 否决原因：{reason}
  - 决策方式：{decided_by}
  - 状态：{status}

（列出最近若干条）

---

## 5. 尚未解决的关键问题

- [Q1] {text}
- [Q2] ...
```

这已经足够支撑「思路延续 + 防止回滚打转」两大目标。

---

## 五、LLM 摘要流程：我建议的 v1 流程

### 5.1 配置一个独立 compact 模型 + 软触发

在你的 config 里加一段：

```yaml
compact:
  model: "your-compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

系统逻辑：

- 构造给辩手的上下文时，先预估：
  - “现有 log（或 compact markdown）的 tokens + 预估回复 token”  
  如果超过 `debater_limit * soft_trigger_ratio` → 先调用 compact。
- 所有 compact 调用都用 `compact.model`，不依赖辩手自己的 endpoint；
- 如果 compact 调用失败，fallback：保留最近 N 条原始发言 + 一行提示「历史被截断，可能略有重复」。

### 5.2 v1 可以用「一次调用」就够：`old_state + delta → new_state`

虽然三位辩手都提到了 2–3 步「填表式」调用，但对 v1 来说，你可以先实现**一个主调用**：

```python
def incremental_compact(old_state: dict | None, delta_text: str) -> dict:
    """
    用 compact_model 调用:
    输入: old_state (JSON) + delta_text (新对话)
    输出: new_state (JSON)
    """
```

Prompt 要点：

- 如果 `old_state` 为 null：
  - 从 delta_text 中直接提取初始 `topic` / `participants` / `disputes` / `axioms` / `pruned_paths` / `open_questions`；
- 否则：
  - 从 old_state 读取旧的字段，在此基础上**增量更新**；
  - 明确告诉模型：
    - `axioms` / `abandoned_claims` / `pruned_paths` 不要删除旧条目，只可：
      - 保持原样；
      - 合并为更简短、更概括的条目；
    - 如要“推翻”旧共识，必须在新 state 里显式说明（比如在 `axioms` 新增一个「原 AxX 被否决」的条目，同时从 disputes / resolutions 中反映）。

输出 format：

- 严格要求 LLM 返回一个 JSON，且字段名固定，如上 schema；
- 你可以在 Python 侧做少量验证：  
  - 判断关键字段是否存在；
  - 若缺失就补回 old_state 对应字段。

等 v1 跑稳后，再考虑拆成 A/B/C 三步填表调用，提高鲁棒性。

---

## 六、多次 compact 时如何避免信息衰减

关键原则我完全同意 Ssyram / 康德说的：

- **永远不要对旧的 Markdown 再摘要。**  
- 只以 `state` 为「权威历史」。

你的流程可以是：

1. `load_from_file()`：
   - 找到最后一个 `compact_checkpoint`；
   - 解析其中 `content.state` 为 `old_state`；
   - `covered_seq_end = old_state.meta.covered_seq_end`。
2. 新一轮 compact 时：
   - 从日志中取出 `seq > covered_seq_end` 的 entries（排除 `thinking/meta` 等）；
   - 拼成 `delta_text`；
   - 调用 `incremental_compact(old_state, delta_text)` → `new_state`；
   - 渲染 Markdown，写入新的 `compact_checkpoint`。

再强调一次：**不要把之前的 `markdown` 再喂给 compact 模型做摘要**，那样你就变成“摘要的摘要”了。

同时做两个简单的防护：

- 若新 `axioms` 数量远小于旧（比如少了一半），且 delta 里没有任何推翻迹象：
  - 直接把旧的 axioms 合并回 new_state；
- `abandoned_claims` / `pruned_paths` 不裁剪条数，只裁剪单条的文字长度。

---

## 七、如何喂给辩手，确保不会回滚

### 7.1 上下文构造方式

压缩后，每轮给辩手的 user context 改为：

```text
## 辩论议题
{state.topic.current_formulation}

## 辩论历史（压缩快照）
{markdown}
```

不再重复初始 topic 中的“立场描述”；  
也就是：**立场卡成为唯一的 canonical 立场来源**。

### 7.2 System prompt 中加入硬约束（负向约束）

在辩手的 system prompt 里追加：

> 你会收到一个“辩论状态快照”，其中包括：
> - 你和对手的最新立场卡（替代初始提示中的立场）；
> - 已达成的共识（axioms）；
> - 正在争论的焦点（disputes）；
> - 已被否决的主张和推理路径（abandoned_claims / pruned_paths）；
> - 尚未解决的关键问题。
>
> 你必须遵守以下约束：
> 1. 不得再使用被标记为【废弃】的主张（abandoned_claims），即使换用不同措辞。
> 2. 不得再次采用 pruned_paths 中描述的推理方式，除非你提供了**新的关键证据**并明确说明为何现在该路径重新可行。
> 3. 不得在没有新理由的前提下质疑 axioms 中的共识前提。
> 4. 回应时优先围绕 `当前仍在争论的焦点` 和 `尚未解决的关键问题` 展开，而不是重新打开已解决的问题。

可选增强：在每轮调用前，给模型一个短 `thinking` 自检：

> 在内部先检查：
> - 你打算回应的是哪些争点 / 未决问题？
> - 你准备使用的核心主张或推理路径是否出现在废弃主张或被否决路径中？
> 如果有冲突，应调整你的论证方式。

你可以把这段 `thinking` 结果标记为 `"tag": "thinking"`，不暴露给对方辩手。

---

## 八、简短总结：我自己的立场

1. **输出区块设计**：  
   - `compact_checkpoint.content` = `{state, markdown}`；  
   - `state` 用一个精简版 `CompactState` JSON 表示：topic / participants / disputes / axioms / pruned_paths / open_questions / meta；  
   - `markdown` 结构化展示：立场卡 → 共识与争点 → 被否决路径（禁止事项）→ 未决问题。

2. **LLM 摘要流程**：  
   - 使用独立的 compact 模型，提前在 soft ratio 触发；  
   - v1：先实现一个主函数 `incremental_compact(old_state, delta)` 一次调用产出新 state；  
   - 校验输出，必要时自动把旧 axioms / pruned_paths / abandoned_claims 补回。

3. **增量压缩**：  
   - 输入永远是上次的 `state` + 新增 entries 文本；  
   - 不再对旧 Markdown 做二次摘要；  
   - 新 checkpoint 覆盖的 seq 区间写入 `meta`。

4. **演进表示与不回滚打转**：  
   - 当前立场：`participants.core_claims + key_arguments`；  
   - 被抛弃内容：`abandoned_claims + pruned_paths`（写成禁止事项）；  
   - 决策变迁：`axioms + disputes.status`；  
   - System prompt 中用负向约束明确禁止复用这些被否决的主张和路径。

如果你愿意下一步进入“实现阶段”，我可以帮你按这个 v1 方案写出：

- `CompactState` 的 Python dataclass / TypedDict；
- 一个简化版的 `incremental_compact` prompt 模板（中文）；
- 一个 `render_markdown(state, max_tokens=None)` 的雏形。

---


### [11] 🔍 **质询** Ssyram → Linus Torvalds

*2026-03-12T15:43:23.850090*

质询对象：Linus Torvalds

我认同你提出的 `CompactState` JSON 与 Markdown 视图分离的架构，这符合我要求的「状态机快照」。但你的**状态更新逻辑（State Transition）和异常处理**在形式化和工程实际上存在致命漏洞。你把状态机当成了普通的文本摘要来写。

我只问你三个涉及系统底线的问题：

**1. 拆分调用的「脑裂」与参照完整性（Referential Integrity）如何保证？**
你建议将增量压缩拆为 A（争点/共识）、B（立场卡）、C（剪枝路径）三次 LLM 调用。
在状态机中，这三者是高度耦合的。如果调用 A 将 Dispute D1 标记为 `resolved`，但并行的调用 B 仍在 Player A 的 `core_claims` 中保留了针对 D1 的激进主张；或者调用 C 生成的 `open_questions` 引用了调用 A 中根本没生成的 Dispute ID。
你把一个原子的状态转移函数 $\Delta S$ 拆成了三个独立的非确定性投影。
**质询**：在没有人工介入的自动化 Pipeline 中，你如何处理 A、B、C 三个 JSON 片段合并时的逻辑冲突和悬空指针（Dangling IDs）？给我具体的合并校验伪代码，我不接受「LLM 通常会保持一致」这种概率性废话。

**2. 你的 Fallback 策略正在破坏 Canonical State（唯一真相源）**
你提到：「compact 调用失败时的降级：最近 N 条发言 + 上一个 checkpoint 的简短截断文本」。
这是一个纯粹的工程灾难。我刚刚确立了 `CompactState` 是辩论的 Canonical State。如果第 N 次 Compact 失败，你降级给辩手喂了「截断文本」，辩手基于这个「非正式状态」产生了新的发言 $\Delta_{n+1}$。当下一次触发 Compact 时，系统试图计算 $S_{n+1} = f(S_{n-1}, \Delta_n + \Delta_{n+1})$，此时因果链已经断裂，语义漂移将不可逆转。
**质询**：状态转移必须是原子的（Atomic）。失败就是失败，为什么不直接 Block 并重试 / 切换备用 API，而是允许系统进入一个未定义（Undefined）的脏状态继续运行？

**3. CEGAR 单调性：你对「负向约束」的压缩会导致死循环**
你建议：「pruned_paths 只保留最近 M 个，更早的合成 1–2 条概括性描述」。
从 CEGAR（反例引导的抽象精炼）的视角看，`pruned_paths` 就是排除错误路径的 Counterexamples。负向约束的集合必须是**单调递增（Monotonically Increasing）**的。如果你让 LLM 去「概括/合并」早期的废弃路径，必然导致约束变得模糊，辩手模型会立刻钻空子，重新踏入早期的死胡同原地打转。
**质询**：既然防打转是核心诉求，为什么要把绝对不能丢失的硬约束（Pruned Paths）交给 LLM 去做有损压缩（Lossy Compression）？如果 Token 真的溢出，正确的工程做法难道不是把 `pruned_paths` 剥离出 LLM 的生成流，作为纯显式的外部校验规则或向量检索库吗？

---


### [12] 🔍 **质询** 康德（Immanuel Kant） → (未解析)

*2026-03-12T15:44:15.664546*

下面按你的需求，直接给一个「综合版、第 2 轮回应」——结合 Linus / Ssyram / 康德三人的立场，但收敛成一套可落地的设计方案，专门回答你这几个问题：

- compact 后辩手到底应该看到什么？
- 输出结构怎么设计、如何填表式生成？
- 多次 compact 怎么避免信息衰减与打转？
- 被抛弃路径和演进怎么表示？

我会尽量用你现有架构语言来讲（log entries, tags, compact_checkpoint 等），并给出“可以今天就实现”的方案。

---

## 1. 结论：compact 输出的总体形态

**统一结论**：

1. `compact_checkpoint.content` 不再是纯文本，而是：
   ```json
   {
     "state": { ...CompactState JSON... },
     "markdown": "渲染给辩手看的文本"
   }
   ```
2. 对辩手来说，**看到的是 `markdown`**；  
   对下一次 compact 来说，**使用的是 `state`**（而不是旧的 markdown 或原始长对话），即：

   > 新状态 = f(旧 state, 新增 log entries)

3. `state` 是一个「辩论状态机快照」，内容比原始对话**更结构化、更可执行**，重点体现：
   - 双方当前立场（立场卡）
   - 已达成共识
   - 仍在争论的焦点
   - 已被否决的主张 / 推理路径（负向约束）
   - 当前未决问题和下一步行动方向

---

## 2. 输出区块设计：`CompactState` + 渲染给辩手的 Markdown

### 2.1 `CompactState` JSON Schema（内部存储）

紧贴你现有 JSON log 的风格，建议最小可用版本如下（可以裁剪字段、慢慢演进）：

```jsonc
{
  "compact_version": 1,

  "topic": {
    "current_formulation": "当前议题的精简/澄清描述（首次压缩时可重写）",
    "notes": "（可选）对题目理解的补充说明"
  },

  "participants": [
    {
      "name": "辩手A",
      "stance_version": 3,
      "one_line_position": "一句话概括 A 当前立场",

      "core_claims": [
        { "id": "A1", "text": "A 的主张 1", "status": "active" },
        { "id": "A2", "text": "A 的主张 2", "status": "active" }
      ],

      "key_arguments": [
        {
          "id": "A1-arg1",
          "claim_id": "A1",
          "text": "支撑 A1 的关键论据",
          "status": "active"
        }
      ],

      "assumptions": [
        { "id": "A-assump1", "text": "A 明确承认的前提/适用条件" }
      ],

      "admitted_weaknesses": [
        {
          "id": "A-w1",
          "text": "A 承认的弱点/不确定性",
          "related_claims": ["A1"]
        }
      ],

      "abandoned_claims": [
        {
          "id": "A-ab1",
          "text": "【废弃】原主张：...",
          "reason": "被 B 反驳 / 自己承认 / 裁判裁定，理由：...",
          "decided_by": "self/opponent/judge",
          "ts": "2025-01-01T12:00:00Z"
        }
      ]
    },

    {
      "name": "辩手B",
      "stance_version": 2,
      "one_line_position": "一句话概括 B 当前立场",
      "core_claims": [...],
      "key_arguments": [...],
      "assumptions": [...],
      "admitted_weaknesses": [...],
      "abandoned_claims": [...]
    }
  ],

  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点的一句话总结",
      "status": "open",      // open / partial_resolved / resolved
      "positions": {
        "辩手A": "A 在 D1 上的当前立场概述",
        "辩手B": "B 在 D1 上的当前立场概述"
      },
      "resolution": "",      // 若 resolved，则写共识/裁决
      "related_claims": ["A1", "B2"]
    }
  ],

  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实/前提：...",
      "source": "debate_consensus/judge"
    }
  ],

  "timeline_brief": [
    {
      "phase": 1,
      "title": "初始陈述阶段",
      "summary": "这一阶段主要发生了什么（1–2 句）"
    },
    {
      "phase": 2,
      "title": "围绕可行性的一轮交锋",
      "summary": "..."
    }
  ],

  "pruned_paths": [
    {
      "id": "P1",
      "description": "尝试用“单一城市案例”直接推全国可行性",
      "target": "证明全国可行",
      "reason": "被指出样本不具代表性，当事方承认外推条件不成立",
      "decided_by": "opponent/self/judge",
      "status": "no_reuse"   // no_reuse / reuse_with_new_evidence / partially_invalid
    }
  ],

  "open_questions": [
    {
      "id": "Q1",
      "text": "目前尚未解决的核心问题：...",
      "related_disputes": ["D1"],
      "suggested_focus": {
        "辩手A": "A 下一轮优先做什么，需避免哪些已被否决路径",
        "辩手B": "B 下一轮优先做什么，需强化哪里"
      }
    }
  ],

  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47,
    "created_at": "2025-01-01T12:00:00Z"
  }
}
```

你可以把这看成一个简单版的“搜索状态机”：

- `participants` = 每个辩手的 canonical 立场卡（替换 topic 中的初始立场段落）。
- `axioms` + status=resolved 的 `disputes` = 已确立的共识和结论。
- `pruned_paths` + `abandoned_claims` = 明确剪掉的搜索空间（禁止再走的路）。
- `open_questions` + status=open 的 `disputes` = 当前搜索前沿。

---

### 2.2 喂给辩手的 `markdown`（compact_text）

在 log 里你仍然只存一段字符串给模型用，这段就是从 `state` 渲染的：

```markdown
# 辩论压缩快照 v{compact_version}

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{A.one_line_position}
- 辩手B：{B.one_line_position}

---

## 2. 各辩手立场卡（当前版本）

### 辩手A 立场卡（版本 {A.stance_version}）

- 当前核心主张：
  - {A.core_claims 中 status=active 的 1–3 条}

- 关键论据：
  - {A.key_arguments 中 status=active 的 1–3 条}

- 承认的前提/适用范围：
  - {A.assumptions 中的关键前提}

- 已承认的弱点：
  - {A.admitted_weaknesses 的简短列表}

- 明确放弃的主张（不得原样再提出）：
  - {A.abandoned_claims：主张 + 否决主体 + 理由（1–2 句）}

### 辩手B 立场卡（版本 {B.stance_version}）

（同上）

---

## 3. 争点与共识

### 3.1 已达成共识（不应再争论）

- {从 axioms + disputes.status=resolved 渲染，一条一句话}

### 3.2 仍在争论的核心焦点

- [D1] {disputes[0].title}
  - A 当前立场：{positions["辩手A"]}
  - B 当前立场：{positions["辩手B"]}
  - 当前状态：{status}

（按需列 2–5 个）

---

## 4. 被否决的推理路径（禁止重复）

以下推理路径已被事实或逻辑否决，除非有重大新证据，不应再次使用同样的论证方式：

- [P1] {description}
  - 目标结论：{target}
  - 否决原因：{reason}
  - 决策方式：{decided_by}
  - 当前状态：{status}

---

## 5. 演进简史（仅保留关键节点）

- 阶段 {phase}: {title} —— {summary}

（3–7 条）

---

## 6. 当前未决问题与下一步建议

当前尚未解决的关键问题：

- [Q1] {open_questions[0].text}
- [Q2] ...

下一轮建议：

- 对辩手A：{合并 open_questions[*].suggested_focus["辩手A"]}
- 对辩手B：{同上}
```

**优先级（token 不足时的裁剪顺序）**：

1. 必保：
   - 2. 立场卡（特别是 core_claims + abandoned_claims）
   - 3.2 仍在争论的核心焦点
   - 4. 被否决路径
2. 次保：
   - 3.1 已达成共识
   - 6. 下一步建议
3. 可裁剪：
   - 1. notes 与长说明
   - 5. 演进简史（可以只留最近 1–2 个阶段）

渲染函数可以简单估算 token 长度，按上述顺序拼接，超出就不加低优先级块。

---

## 3. LLM 摘要流程：专用模型 + 填表式多步

### 3.1 模型与触发策略

新增一段配置：

```yaml
compact:
  model: "your-compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

- 所有 compact 一律用这一个 `compact_model`（与 A/B 辩手的 endpoint 解耦）。
- 每轮在调用辩手模型前先估算：

  ```text
  已有上下文 token + 预估本轮回复 token
  > debater_limit * soft_trigger_ratio
  ```

  就先 compact，再喂辩手。

- 如果 compact 调用失败，fallback：简单保留最近 N 条发言 + 上一个 checkpoint 的短截断摘要，并显式插一句「历史被截断，可能略有重复」，防止彻底死。

这样就不会出现“自动 compact 时原辩手模型因为超限 unusable”的死锁。

### 3.2 核心：增量 compact 函数

伪代码结构建议改为：

```python
def build_compact_context(log: Log, compact_model) -> tuple[dict, str]:
    last_cp = log.last_compact_checkpoint()

    if last_cp is None:
        old_state = None
        covered_end = 0
    else:
        cp_content = json.loads(last_cp["content"])
        old_state = cp_content["state"]
        covered_end = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(
        covered_end,
        exclude_tags=["thinking", "meta", "compact_checkpoint"]
    )
    new_entries_text = format_entries_for_compact(new_entries)

    new_state = incremental_compact_with_llm(
        model=compact_model,
        old_state=old_state,
        new_entries_text=new_entries_text,
        new_covered_end=log.last_seq()
    )

    markdown = render_markdown(new_state)

    log.add(
        name="Compact Checkpoint",
        tag="compact_checkpoint",
        content=json.dumps(
            {"state": new_state, "markdown": markdown},
            ensure_ascii=False
        )
    )

    return new_state, markdown
```

### 3.3 `incremental_compact_with_llm`：三步填表式调用

为减少「一次大 JSON 崩掉」风险，把 compact 拆为三个较小任务：

#### 调用 A：更新 topic / disputes / axioms

输入：

- old_state 中的 `topic / disputes / axioms`（可能为 None）
- 新对话文本 `new_entries_text`

输出 JSON：

```jsonc
{
  "topic": {...},
  "disputes": [...],
  "axioms": [...]
}
```

提示要点（简化版）：

- 你是「辩论记录维护助手」；
- 基于旧状态 + 新对话：
  - 可以新增/更新 disputes（争点 id，title，summary，status，positions，resolution）；
  - 可以新增 axioms（双方明确接受的事实/前提）；
- 不允许删除旧 axioms 和已 resolved 的 disputes，除非新对话里有明确推翻。

#### 调用 B：更新 participants（立场卡）

输入：

- old_state.participants（或空）
- 新对话文本（需带上每条 entry 的 `name`，便于切分谁说的）

输出 JSON：

```jsonc
{
  "participants": [ ... ]
}
```

提示要点：

- 按人更新立场卡；对每个参与者：
  - 更新 `one_line_position`（如果有进一步明确或改变）；
  - 增补/修改 `core_claims`、`key_arguments`、`assumptions`；
  - 如果某主张被明确否定、且说话人/裁判承认，则加入 `abandoned_claims`（包含 reason / decided_by）。
- 不允许删除旧的 abandoned_claims，除非新对话明确说明恢复某主张，此时可以：
  - 为该主张新增一个 active 的 claim（带新 id），并在说明中注明基于新证据恢复。

#### 调用 C：更新 timeline_brief / pruned_paths / open_questions

输入：

- A + B 合并出的临时 state 片段（topic / participants / disputes / axioms）
- new_entries_text 或其短 summary

输出 JSON：

```jsonc
{
  "timeline_brief": [...],
  "pruned_paths": [...],
  "open_questions": [...]
}
```

提示要点：

- timeline_brief：
  - 只添加真正改变局面/状态的关键阶段（1–2 个），旧阶段可合并；
- pruned_paths：
  - 把“某种证明方式失败”的信息结构化：description / target / reason / decided_by / status；
  - 不允许凭空删除旧 paths，只可精简合并；
- open_questions：
  - 从 disputes.status = open 的争点中提炼出 2–5 个「当前核心问题」；
  - 为每个问题对每位辩手给出一句“下一步重点方向”。

#### 合并与防呆

在 Python 里合并 A/B/C 的输出：

- 对于新 JSON 未输出的字段，沿用 old_state 的对应部分；
- 设置 `compact_version = old_state.compact_version + 1` 或 1；
- 填 `meta.covered_seq_start` 和新的 `covered_seq_end`。

同时做一层 sanity check，避免 LLM 偷删关键信息：

- 若新 `axioms` 数量比旧的少很多，且新对话中未检测到“推翻”语句 → 将旧 axioms 合并回去；
- 同理，对于 `abandoned_claims` 和 `pruned_paths`，默认“只增不减”，除非非常明确的「恢复」信息。

---

## 4. 多次 compact：如何避免逐层衰减和回滚打转

### 4.1 永远基于 state，不基于旧 markdown

这是最关键的一点：

- `load_from_file()` 时：
  - 找最后一个 `compact_checkpoint`；
  - `state = json.loads(entry.content)["state"]`；
  - 以后所有 compact 都基于这个 `state`；
  - 之后的 entries 才是 delta。

- **不要**再让 LLM看之前的 markdown 压缩摘要，避免「摘要的摘要」导致语义漂移。

### 4.2 防信息衰减的几条硬规则

1. **共识和否决信息“只增不减”**：
   - `axioms`、`abandoned_claims`、`pruned_paths` 大部分情况下不允许减少条数；  
   - 如模型删掉很多条，程序自动把旧条目 merge 回来，或重试时在 prompt 中明确指出“上次你删掉了哪些，请保留”。

2. **长度控制依赖“合并”而不是“删掉”**：
   - `timeline_brief`：只保留最近 K 条（例如 5–7），更老的合成一条汇总：“早期阶段的讨论主要围绕 X/Y，已内化到当前立场中，不再展开”；
   - `pruned_paths`：只保留最近/最关键的若干条，其他可由 LLM在调用 C 时合成一条概括型描述。

3. **限制每条文本的长度，而不是限制条数**：
   - 每个 axioms / abandoned_claims / pruned_paths 条目 1–2 句，避免它们自己变成 token 黑洞；
   - 条目数量保守增长，但因为每条很短，对 token 的影响可控。

---

## 5. 演进表示 & 被抛弃路径：具体如何防止“打回原点”

### 5.1 立场演进（起点 → 当前 → 被废弃）

由三层信息组成：

1. `participants[*].core_claims(status=active)`  
   → 当前立场的“骨架”。

2. `participants[*].admitted_weaknesses`  
   → 当前立场自带的“免责声明”，减少无谓反复。

3. `participants[*].abandoned_claims`  
   → 曾经走过但已放弃的主张（无论是逻辑不通、事实错误、不适用等）。

在渲染给辩手的 Markdown 中，**立场卡是辩手的「最新自我说明」**，相当于替换掉 topic 里的初始立场描述。

### 5.2 被抛弃路径（not only “观点”，更是“推理路线”）

`pruned_paths` 是比 abandoned_claims 更强的否决信息：

- abandoned_claims：已经不能再“得到那个结论”的具体说法；
- pruned_paths：已经不能再“沿用那种证明方式”来得出某类结论。

例如：

```jsonc
{
  "id": "P3",
  "description": "用单一极端案例推广到整体结论",
  "target": "证明全国普遍适用",
  "reason": "B 指出该案例不具代表性，A 同意不能据此做一般归纳",
  "decided_by": "opponent+self",
  "status": "no_reuse"
}
```

渲染给辩手时要明确写成「禁止性约束」：

> - 禁止再次使用路径 P3：用单一极端案例直接推全国普适性，理由：已被判定样本不具代表性，当事方已承认不能据此外推。

### 5.3 System prompt 层的强约束

在辩手 system prompt 里加入：

1. 描述输入性质：

> “辩论历史”部分是一个状态快照，包含：
> - 你的最新立场卡（替代初始立场中对你立场的描述）
> - 对方的最新立场卡
> - 双方已达成的共识
> - 已被否决的主张和推理路径
> - 当前开放争点和建议的下一步行动方向

2. 硬性约束：

> 你不得：
> - 再次将已列入「废弃主张」(abandoned_claims) 的内容当作自己的论点，即使换掉措辞；
> - 再次采用 `被否决的推理路径` 中描述的论证方式；
> - 在没有提供新证据或新论证的情况下，否认 axioms 中已经写明的共识。

3. 可选的“自检步骤”（放在一个 `thinking` tag 的辅助调用里）：

> 在生成正式发言前，请在内部简短检查：
> - 本轮你打算回应的是哪些争点（disputes）或 open_questions？
> - 你计划使用的论点是否出现在已废弃主张或被否决路径中？
> 若存在冲突，请调整你的论点或引入新的关键证据。

---

## 6. 针对你列出 4 个问题的直接回答

### 6.1 输出区块设计

- `compact_checkpoint.content` 结构：
  ```json
  {
    "state": CompactState,
    "markdown": "渲染给辩手看的文本"
  }
  ```
- `CompactState` 至少包含：
  - topic（当前议题表达）
  - participants（立场卡：active claims / weaknesses / abandoned_claims）
  - disputes（争点及其当前状态）
  - axioms（共识）
  - pruned_paths（被否决路径）
  - timeline_brief（演进节点）
  - open_questions（未决问题 + 建议）
  - meta（覆盖的 seq 范围）

- 给辩手看的 `markdown` 有 6 个区块，按优先级裁剪。

### 6.2 LLM 摘要流程 & 原模型不可用

- 使用单独配置的 `compact_model`，不依赖辩手自己的 endpoint；
- 在上下文接近 soft limit（比如 0.8）时提前 compact；
- 摘要流程拆为三步“填表式”小调用（更新 topic/disputes/axioms → participants → timeline/pruned_paths/open_questions），每步输出 JSON 片段，由本地代码合并；
- 失败时 fallback 为简单截断方案。

### 6.3 多次 compact / 增量压缩 & 避免信息衰减

- 每次 compact 的输入是：上一个 checkpoint 的 `state` + 之后的新 log entries（排除 thinking/meta 等）；
- LLM 仅负责从 `old_state + delta` → `new_state`，不再看旧 markdown 压缩文本；
- 对 axioms / abandoned_claims / pruned_paths 做“只增不减”约束，异常删减会被代码纠正或触发重试；
- timeline/pruned_paths 长度通过「合并」而不是删条来控制：老的归并为概括条目。

### 6.4 演进表示 & 被抛弃路径的数据结构

- 立场演进：
  - `core_claims(status=active)` + `admitted_weaknesses` 表示当前立场；
  - `abandoned_claims` 表示历史中被否决的主张；
  - `timeline_brief` 记录关键演化阶段。
- 被抛弃路径：
  - 用 `pruned_paths` 记录“论证方式”被否决的信息（description / target / reason / decided_by / status）；
  - system prompt 明确声明这些路径为“禁止再走”的负向约束。

---

如果你下一步想具体落地，可以从三个最小改动开始：

1. 给 `compact_checkpoint.content` 换成上面这层 `{state, markdown}`；
2. 定一个最小版 `CompactState`（必要字段：participants / disputes / axioms / pruned_paths / meta）；
3. 实现 `incremental_compact_with_llm` 的第一个版本，可以先只做“单步调用 + 输出完整 CompactState”，后续再拆成三步填表式。

---


### [13] Linus Torvalds

*2026-03-12T15:45:22.017415*

下面我直接给出一套「可以实现、并且兼容你现有架构」的结论性方案，只围绕：**compact 之后辩手看到什么**，以及这背后需要的最小设计。

---

## 1. Compact 之后，辩手到底应该看到什么？

统一成一句话：

> 辩手看到的是「辩论状态机快照的 Markdown 视图」，而不是裁剪过的聊天记录。

也就是：每次 compact 产生一个结构：

```jsonc
{
  "state": { ...CompactState... },     // 机器内部用
  "markdown": "渲染给辩手看的文本"     // 辩手实际看到
}
```

在上下文构造上：

- 没 compact 前：  
  `## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{log.since(last_seq)}`
- compact 后：  
  `## 辩论议题\n\n{state.topic.current_formulation}\n\n## 辩论历史（压缩快照）\n\n{markdown}`

并且从 compact 之后开始，**不再使用 topic 里传入的原始“立场描述”作为辩手立场**，而是用 `state.participants` 中的立场卡。

---

## 2. 内部结构：CompactState（辩论状态机）

这是 compact 的核心，建议 v1 使用一个精简但足够用的 schema：

```jsonc
{
  "compact_version": 1,

  "topic": {
    "current_formulation": "当前议题的精简/澄清描述",
    "notes": "（可选）对题目理解的补充说明"
  },

  "participants": [
    {
      "name": "辩手A",
      "stance_version": 1,
      "one_line_position": "一句话概括 A 当前立场",

      "core_claims": [
        { "id": "A1", "text": "A 的核心主张 1", "status": "active" }
      ],

      "key_arguments": [
        {
          "id": "A1-arg1",
          "claim_id": "A1",
          "text": "支撑 A1 的关键论据",
          "status": "active"
        }
      ],

      "abandoned_claims": [
        {
          "id": "A-ab1",
          "text": "【废弃】原主张：...",
          "reason": "被 B 反驳 / 自己承认 / 裁判裁定，理由：...",
          "decided_by": "self/opponent/judge"
        }
      ]
    },
    {
      "name": "辩手B",
      "stance_version": 1,
      "one_line_position": "一句话概括 B 当前立场",
      "core_claims": [...],
      "key_arguments": [...],
      "abandoned_claims": [...]
    }
  ],

  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点一句话概述",
      "status": "open",     // open / resolved (v1 可以先不做 partial)
      "positions": {
        "辩手A": "A 在 D1 上的当前立场",
        "辩手B": "B 在 D1 上的当前立场"
      },
      "resolution": ""       // resolved 时写结论
    }
  ],

  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实/前提：...",
      "source": "debate_consensus/judge"
    }
  ],

  "pruned_paths": [
    {
      "id": "P1",
      "description": "被否决的推理路径：如何如何证明什么",
      "reason": "否决原因：逻辑矛盾 / 证据不足 / 前提不成立",
      "decided_by": "self/opponent/judge",
      "status": "no_reuse"
    }
  ],

  "open_questions": [
    {
      "id": "Q1",
      "text": "尚未解决的关键问题",
      "related_disputes": ["D1"]
    }
  ],

  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47
  }
}
```

注意这里的取舍：

- v1 只保留「必须防打转、必须续思路」的字段：
  - participants（立场卡 + abandoned_claims）
  - disputes（争点）
  - axioms（共识）
  - pruned_paths（被否决路径）
  - open_questions（下一步要攻的点）
- timeline_brief、assumptions、admitted_weaknesses 等可以后续再加。

原则：**CompactState 是唯一真源（canonical state）**，后续一切 compact 都基于它做增量更新。

---

## 3. 对辩手显示的 Markdown 结构（compact_text）

`compact_text` 就是对上面的 `CompactState` 做一次模板渲染：

```markdown
# 辩论压缩快照 v{compact_version}

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{A.one_line_position}
- 辩手B：{B.one_line_position}

---

## 2. 各辩手当前立场

### 辩手A

- 核心主张：
  - {A.core_claims 中 status=active 的 1–3 条}

- 关键论据：
  - {A.key_arguments 中 status=active 的 1–3 条}

- 已明确放弃的主张（不得再次使用）：
  - {A.abandoned_claims，每条 1 行，含 reason / decided_by}

### 辩手B

（同上）

---

## 3. 共识与争点

### 3.1 已达成共识（不应再反复争论）

- {axioms 列表，每条一句话}

### 3.2 当前仍在争论的焦点

- [D1] {title}
  - A：{positions["辩手A"]}
  - B：{positions["辩手B"]}
  - 状态：{status}

（最多列 3–5 个）

---

## 4. 被否决的推理路径（禁止再走）

以下推理方式已经被明确否决，除非有重大新证据，不应再使用：

- [P1] {description}
  - 否决原因：{reason}
  - 决策方式：{decided_by}
  - 状态：{status}

（列出最近几条）

---

## 5. 尚未解决的关键问题

- [Q1] {text}
- [Q2] ...
```

当 token 不够时，裁剪顺序：

1. 必须保留：
   - 2. 各辩手当前立场（尤其 abandoned_claims）
   - 3.2 争点
   - 4. 被否决路径
2. 次要：
   - 3.1 共识
   - 5. 未决问题
3. 可裁剪：
   - 1 中 notes / 长解释

你可以写一个 `render_markdown(state, max_tokens=None)`，按区块顺序 append，超过上限就跳过低优先级块。

---

## 4. LLM 摘要流程（compact 如何生成这些区块）

### 4.1 必要前提：独立 compact 模型 + 软触发

配置里增加：

```yaml
compact:
  model: "compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

策略：

- 所有 compact 调用都用这个 compact.model；
- 构造辩手上下文时，如果：
  - 历史 + 预估回复 > debater_limit * soft_trigger_ratio  
  → 先 compact，再让辩手说话；
- 若 compact 调用失败，fallback：  
  保留最近 N 条发言 + 一句「历史被截断，可能略有重复」，这不是理想状态，但保证系统不断。

### 4.2 增量 compact：S_new = f(S_old, Δ)

核心函数：

```python
def build_compact_context(log: Log, compact_model) -> tuple[dict, str]:
    last_cp = log.last_compact_checkpoint()

    if last_cp is None:
        old_state = None
        covered_end = 0
    else:
        cp_content = json.loads(last_cp["content"])
        old_state = cp_content["state"]
        covered_end = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(
        covered_end,
        exclude_tags=["thinking", "meta", "compact_checkpoint"]
    )
    new_entries_text = format_entries_for_compact(new_entries)

    new_state = incremental_compact_with_llm(
        model=compact_model,
        old_state=old_state,
        new_entries_text=new_entries_text,
        new_covered_end=log.last_seq()
    )

    markdown = render_markdown(new_state)

    log.add(
        name="Compact Checkpoint",
        tag="compact_checkpoint",
        content=json.dumps({"state": new_state, "markdown": markdown},
                          ensure_ascii=False)
    )

    return new_state, markdown
```

关键点：**输入是 old_state + 新对话 delta**，完全不用旧 markdown，避免“摘要的摘要”。

### 4.3 v1 的 LLM 调用策略

你可以先做简单版：**一次调用直接产出完整 CompactState**：

```python
def incremental_compact_with_llm(model, old_state, new_entries_text, new_covered_end):
    # 构造 prompt：system + user
    # system：说明目标 schema、字段含义、约束（例如 axioms / abandoned_claims 只增不减）
    # user：包含 old_state（或 null）+ new_entries_text
    # 模型返回 JSON，解析为 new_state
    ...
```

Prompt 核心要求：

- 如果 old_state 为 null：从 new_entries_text 直接提取初始 topic / participants / disputes / axioms / pruned_paths / open_questions；
- 否则：
  - 在 old_state 基础上做增量更新；
  - 不得删除旧的 axioms / abandoned_claims / pruned_paths，除非新对话中明确出现“推翻、恢复”等信号（你也可以在 v1 直接写死：这三类只增不减）。

后续如果发现一次性 JSON 易出错，可以再按前面讨论拆为 A/B/C 三步「填表式」调用；但 v1 一次调用足够把流程跑起来。

---

## 5. 多次 compact：如何避免信息逐层衰减？

三条原则：

1. **永远基于 state，不再对旧 markdown 再摘要**  
   - load 时：只认最后一个 `compact_checkpoint.content.state`；  
   - 旧 markdown 不再进入任何 compact 调用。

2. **共识和否决信息“只增不减”**  
   - 默认规则：`axioms` / `abandoned_claims` / `pruned_paths` 不减，只能增加；  
   - 如果 LLM 输出把它们大幅减小，代码可以直接把 old_state 中这些字段 merge 回 new_state。

3. **控制单条长度，不控制条数**  
   - 每条 axioms / abandoned_claims / pruned_paths 限制为 1–2 句，避免每条太长；  
   - 条目本身保留，这样「已经否决过的路」不会被遗忘。

---

## 6. 防止“回滚打转”的具体手段

### 6.1 立场：立场卡覆盖初始 topic

compact 后，每轮喂给辩手：

```text
## 辩论议题
{state.topic.current_formulation}

## 辩论历史（压缩快照）
{markdown}
```

不再重复当初 topic 里那段「A 负责正方，认为……」的描述，避免模型回到初始设定，而忽视已经演化过的立场。

### 6.2 被否决内容：abandoned_claims + pruned_paths

- abandoned_claims：记录“**不能再主张**”的观点；
- pruned_paths：记录“**不能再采用**”的推理方式。

在 Markdown 里清楚写：

> 已明确放弃的主张（不得再次使用）：  
> 被否决的推理路径（禁止再走）：

### 6.3 system prompt 中的强约束

在辩手的 system prompt 里加一段：

> 你会收到一个“辩论状态快照”，其中包括：
> - 你和对方的最新立场卡（替代初始提示中的立场描述）
> - 已达成的共识（axioms）
> - 正在争论的焦点（disputes）
> - 已被否决的主张和推理路径（abandoned_claims / pruned_paths）
> - 尚未解决的关键问题（open_questions）
>
> 你必须遵守：
> 1. 不得再次使用已列入「废弃主张」的内容，即使换用不同措辞。
> 2. 不得再次采用 `被否决的推理路径` 中的论证方式，除非你明确提出了新的关键证据并说明为什么该路径现在重新可行。
> 3. 不得在没有新理由的情况下质疑 axioms 中的共识前提。
> 4. 优先围绕“当前仍在争论的焦点”和“尚未解决的关键问题”展开，不要重新打开已解决问题。

可选：在每轮生成前插一个 `thinking` 自检（tag 标为 thinking，不给对方看）：

> - 我本轮要回应的是哪个争点或未决问题？  
> - 我即将使用的主张/推理是否出现在废弃主张或被否决路径中？如是，需要调整。

---

## 7. 对你四个设计问题的直接回答

1. **输出区块设计**  
   - 内部：`CompactState` JSON，包含 topic / participants / disputes / axioms / pruned_paths / open_questions / meta；  
   - 对辩手：由 state 渲染成 Markdown，区块顺序：
     1) 议题 & 立场一句话  
     2) 各辩手当前立场（含废弃主张）  
     3) 共识与争点  
     4) 被否决的推理路径（禁止再走）  
     5) 尚未解决的关键问题  

2. **LLM 摘要流程**  
   - 使用独立 compact 模型，提前在 soft ratio 触发；  
   - `incremental_compact_with_llm(old_state, new_entries_text)`：  
     - 若无 old_state，从新对话抽取首个 CompactState；  
     - 否则在 old_state 上增量更新；  
   - v1 可先实现为一次调用输出完整 state，后续再拆成多步“填表”。

3. **增量压缩 / 多次 compact**  
   - 每次 compact 的输入是：上一个 checkpoint 的 `state` + 后续 entries 文本；  
   - 输出新的 `state`，再渲染成 markdown 并写入新的 checkpoint；  
   - 从不对旧 markdown 再摘要；  
   - 对 axioms / abandoned_claims / pruned_paths 采用“只增不减”策略，代码层面必要时合并旧条目。

4. **演进表示 / 被抛弃路径**  
   - 当前立场：`participants.core_claims + key_arguments`；  
   - 演进与被放弃：`abandoned_claims` 记录被否决主张；  
   - 决策变迁和共识：`axioms + disputes.status/resolution`；  
   - 被抛弃路径：`pruned_paths` 结构化记录被否决推理方式，并在 prompt 中以「禁止」口吻出现。

如果你想下一步直接动手实现，我可以帮你写：  
- 一个精简版 `CompactState` TypedDict；  
- 一个用于 `incremental_compact_with_llm` 的中文 prompt 模板；  
- 一个简单的 `render_markdown(state, max_tokens=None)`。

---


### [14] Ssyram

*2026-03-12T15:45:22.017456*

我明确**反对**康德和 Linus 提出的「拆分为 A/B/C 三步调用」和「失败时降级为文本截断」的方案。

把状态转移拆成三次独立的 LLM 调用，在工程上叫**破坏参照完整性（Referential Integrity）**。如果在调用 A 中 Dispute D1 被标记为 resolved，但在调用 B 中 Player A 仍针对 D1 输出 active claims，你的合并逻辑就会产生悬空指针和状态冲突。而在自动化 Pipeline 中，状态一旦脏了，后续所有的推理都会崩溃。

至于「降级为文本截断」更是滑稽——如果状态转移失败，正确的做法是抛出异常、重试或切换备用 API，而不是悄悄塞给系统一个未定义格式的脏数据让语义不可逆地漂移。

以下是我要求的最终落地实现方案，核心原则只有一个：**Compact 是严格的单调状态转移（Monotonic State Transition），LLM 仅作为 Diff 生成器，状态的合并与约束由 Python 强类型代码兜底。**

### 1. 完整数据结构（Python 强类型定义）

抛弃松散的 Dict，必须使用 `TypedDict` 或 `Pydantic` 锁定 Schema。`compact_checkpoint` 的 `content` 必须是严格的 `{"state": CompactState, "view": str}`。

```python
from typing import TypedDict, List, Dict, Literal

class PrunedPath(TypedDict):
    id: str
    description: str  # 尝试过的论证路径
    reason: str       # 为什么走不通（硬约束来源）
    decided_by: str

class PlayerState(TypedDict):
    one_line_position: str
    core_claims: List[str]
    abandoned_claims: List[str] # 必须单调递增，禁止删除

class DisputeNode(TypedDict):
    id: str
    title: str
    status: Literal["open", "resolved"]
    positions: Dict[str, str] # key 为辩手 name

class CompactState(TypedDict):
    version: int
    covered_seq_end: int
    axioms: List[str]                 # 事实基座（单调递增）
    pruned_paths: List[PrunedPath]    # 负向约束（单调递增）
    players: Dict[str, PlayerState]   # 规范化立场
    disputes: List[DisputeNode]       # 搜索前沿
```

### 2. LLM 摘要 Prompt 与输出约束

**不要让 LLM 直接输出完整的新状态，让它输出 Delta（增量）**。现代模型（GPT-4o/Claude-3.5-Sonnet）完全支持 Structured Output。我们只要求一次调用，强制返回 JSON 匹配 `CompactStateDiff` Schema。

**System Prompt 核心指令：**
```text
你是一个形式化状态机更新工具。
输入包含：
1. `old_state`: 上一次的辩论状态 (JSON)
2. `delta_log`: 上次状态之后的新增对话记录

你的任务是提取 `delta_log` 中的逻辑增量，输出一个 JSON 对象：
{
  "new_axioms": ["新增的共识，若无则空"],
  "new_pruned_paths": [{"id": "P_n", "description": "...", "reason": "..."}],
  "new_abandoned_claims": {"辩手A": ["..."], "辩手B": ["..."]},
  "updated_players_core_claims": {"辩手A": ["..."], "辩手B": ["..."]},
  "updated_disputes": [{"id": "D1", "status": "resolved", ...}]
}

绝对约束：
- 不要输出旧状态中已有的 axioms 和 pruned_paths，只输出新增（Delta）。
- 任何被证伪的逻辑必须写入 new_pruned_paths 或 new_abandoned_claims。
```

### 3. 触发流程（三条路径）

在配置中独立定义 `compact_model`（必须是支持 JSON Mode 或 Tool Calling 的高智商模型）。

```python
# 路径 1: 主动/软触发 (Proactive) - 拦截在崩溃前
def check_soft_trigger(log: Log, pending_reply_tokens: int, limit: int):
    current_tokens = count_tokens(log.get_active_context())
    if current_tokens + pending_reply_tokens > limit * 0.8:
        execute_compact_pipeline(log)

# 路径 2: 自动/硬触发 (Reactive) - 现有的 token 超限异常捕获
def _compact_for_retry(self, log: Log):
    # 发生溢出异常时，原模型不可用，直接调用独立 compact_model
    execute_compact_pipeline(log)

# 路径 3: 手动触发 (Manual)
@click.command()
def compact_cmd(log_file):
    log = Log.load_from_file(log_file)
    execute_compact_pipeline(log)
    log._flush()
```

### 4. 增量压缩的 Merge 逻辑（Python 侧的单调性保证）

这是防打转的最关键防线。LLM 可能会遗忘，但代码不会。**负向约束（Axioms, Pruned Paths, Abandoned Claims）在 Python 级别执行 Append-Only 操作。**

```python
def apply_diff(old_state: CompactState, diff: dict, last_seq: int) -> CompactState:
    new_state = copy.deepcopy(old_state)
    
    # 1. 严格单调递增的集合 (Append-Only)
    new_state["axioms"].extend(diff.get("new_axioms", []))
    new_state["pruned_paths"].extend(diff.get("new_pruned_paths", []))
    
    for player, claims in diff.get("new_abandoned_claims", {}).items():
        if player in new_state["players"]:
            new_state["players"][player]["abandoned_claims"].extend(claims)
            
    # 2. 覆盖更新的集合 (Overwrite)
    for player, claims in diff.get("updated_players_core_claims", {}).items():
        if player in new_state["players"]:
            new_state["players"][player]["core_claims"] = claims
            
    # 3. 状态机流转 (Disputes)
    # 合并 updated_disputes 逻辑略...
    
    new_state["version"] += 1
    new_state["covered_seq_end"] = last_seq
    return new_state
```

### 5. 与现有代码的具体改动点

**改动 1：`Log.load_from_file()` 的游标切分**
不再恢复 `compact_checkpoint` 之前的原始条目。
```python
def load_from_file(self):
    # ... 扫描找最后一个 tag == "compact_checkpoint"
    if last_checkpoint:
        content = json.loads(last_checkpoint["content"])
        self._current_state = content["state"] # 提取内部状态
        # 仅保留 covered_seq_end 之后的 entries 作为 active log
        self.entries = [e for e in all_entries if e["seq"] > self._current_state["covered_seq_end"]]
```

**改动 2：`build_compact_context()` 的重构**
```python
def execute_compact_pipeline(log: Log):
    old_state = log._current_state or get_empty_state()
    delta_entries = log.entries # 当前活跃的增量 log
    delta_text = format_entries(delta_entries)
    
    # 1. LLM 提取增量 (严格 JSON)
    diff_json = call_compact_model_for_diff(old_state, delta_text)
    
    # 2. Python 侧合并状态，保证单调性
    new_state = apply_diff(old_state, diff_json, log.last_seq())
    
    # 3. 渲染给辩手看的 View (包含强硬的负向约束声明)
    view_md = render_to_markdown(new_state)
    
    # 4. 写入 Checkpoint
    log.add(
        name="System",
        tag="compact_checkpoint",
        content=json.dumps({"state": new_state, "view": view_md})
    )
    # 清空已压缩的 entries
    log.archive_active_entries()
    log._current_state = new_state
```

**改动 3：辩手 Context 注入（负向约束的武器化）**
在构造喂给辩手的 Prompt 时，不仅提供 `view_md`，必须在 System 层面注入硬约束：
```python
def build_debater_prompt(topic, log):
    context = f"## 议题\n{topic}\n\n## 当前状态快照\n{log.get_last_view_md()}"
    
    # 提取状态机中的负向约束，直接作为 System 指令
    state = log._current_state
    if state and state["pruned_paths"]:
        forbidden_rules = "\n".join([f"- 禁止使用路径: {p['description']} (原因: {p['reason']})" for p in state["pruned_paths"]])
        context += f"\n\n## 绝对约束 (违反将导致判负)\n{forbidden_rules}"
        
    return context + f"\n\n## 最新对话\n{log.get_active_text()}"
```

这种设计，JSON 态负责严谨的机器合并，Markdown 态负责人类/模型的上下文理解，而 Python 侧的 Append-Only 逻辑彻底斩断了 LLM 遗忘历史导致原地打转的可能性。这才是无需人工干预的工程级解法。

---


### [15] 康德（Immanuel Kant）

*2026-03-12T15:45:22.017476*

下面先不复述上轮内容，直接给一个“可落地、v1 就能实现”的设计，专门回答这轮隐含问题：你现在已经基本收敛到「状态机快照 + JSON 内核 + Markdown 视图」，这轮要做的是再收紧：到底要保留哪些元素、哪些可以先砍掉，才能兼顾实用性和复杂度。

我会按你这轮关心的几个点组织：

- 1）我们到底**非有不可**的结构块是什么？
- 2）v1 的压缩流程应该尽量**多简单**，三步填表要不要先降级？
- 3）多次 compact 的“状态转移方程”怎么写，最少写多少逻辑才能安全？
- 4）「防打转 / 不回滚」到底靠哪几个字段就够了？

---

## 1. v1 里 compact 输出“最低必要集”：只留 4 块

你的目标是：compact 后辩手表现不比原始对话差，甚至更好。与其一上来就全量 schema，我建议 v1 只锁定四块“真正刚需”的东西：

1. **双方当前立场卡（含废弃主张）**
2. **当前争点（disputes）**
3. **共识/axioms**
4. **被否决路径（pruned_paths）**

而 timeline_brief、open_questions、弱点/前提 等可以之后再补。先用这 4 块已经足以：

- 延续思路（立场卡 + 当前争点）
- 防回滚打转（废弃主张 + 被否决路径 + 共识）

### 1.1 内部 `state`（v1 精简 schema）

`compact_checkpoint.content` 里 **只约定一层结构**：

```jsonc
{
  "state": {
    "compact_version": 1,

    "topic": {
      "current_formulation": "当前议题的简要版（可在首次 compact 时重写）"
    },

    "participants": [
      {
        "name": "辩手A",
        "stance_version": 1,
        "one_line_position": "一句话概括 A 当前立场",

        "core_claims": [
          { "id": "A1", "text": "A 当前的主张 1", "status": "active" }
        ],
        "key_arguments": [
          { "id": "A1-arg1", "claim_id": "A1", "text": "支撑 A1 的关键论据", "status": "active" }
        ],

        "abandoned_claims": [
          {
            "id": "A-ab1",
            "text": "【废弃】原主张：...",
            "reason": "被反驳/承认错误/裁判裁定，简要说明",
            "decided_by": "self/opponent/judge"
          }
        ]
      },
      {
        "name": "辩手B",
        "stance_version": 1,
        "one_line_position": "一句话概括 B 当前立场",
        "core_claims": [...],
        "key_arguments": [...],
        "abandoned_claims": [...]
      }
    ],

    "disputes": [
      {
        "id": "D1",
        "title": "关于 X 是否可行",
        "summary": "争点一句话概述",
        "status": "open",   // open / resolved
        "positions": {
          "辩手A": "A 在 D1 上的当前立场",
          "辩手B": "B 在 D1 上的当前立场"
        },
        "resolution": ""     // resolved 时写共识/裁决
      }
    ],

    "axioms": [
      {
        "id": "Ax1",
        "text": "双方明确接受的事实/前提：...",
        "source": "debate_consensus/judge"
      }
    ],

    "pruned_paths": [
      {
        "id": "P1",
        "description": "被否决的推理方式：如何如何证明什么",
        "reason": "否决原因（逻辑矛盾/证据不足/前提不成立等）",
        "decided_by": "self/opponent/judge",
        "status": "no_reuse"
      }
    ],

    "meta": {
      "covered_seq_start": 1,
      "covered_seq_end": 47
    }
  },

  "markdown": "渲染给辩手看的文本"
}
```

刻意砍掉了：

- timeline_brief
- open_questions
- assumptions / weaknesses

原因很简单：**v1 先解决不回滚打转，再考虑“更顺滑推进”**。上面这一小撮信息就足够构成一个状态机。

### 1.2 渲染给辩手看的 `markdown`（v1 结构）

`compact_text` = `render_markdown(state)`，结构可以约成：

```markdown
# 辩论压缩快照 v{compact_version}

## 1. 当前议题

{topic.current_formulation}

---

## 2. 双方当前立场

### 辩手A（立场版本 {A.stance_version}）

- 一句话立场：{A.one_line_position}

- 核心主张：
  - {A.core_claims 中 status=active 的 1–3 条}

- 关键论据：
  - {A.key_arguments 中 status=active 的 1–3 条}

- 已明确放弃的主张（不得再使用）：
  - {A.abandoned_claims，每条一句：主张 + 理由 + 谁否决的}

### 辩手B（立场版本 {B.stance_version}）

（同上）

---

## 3. 共识与争点

### 3.1 已达成共识（不应再反复争论）

- {axioms 列表，每条一句}

### 3.2 当前仍在争论的焦点

- [D1] {title}
  - A：{positions["辩手A"]}
  - B：{positions["辩手B"]}
  - 状态：{status}

（最多 3–5 个）

---

## 4. 被否决的推理路径（禁止再走）

以下推理方式已经被明确否决，除非你在本轮引入新的关键证据证明之前的否决不再适用，否则不得再次使用：

- [P1] {description}
  - 否决原因：{reason}
  - 决策方式：{decided_by}
  - 状态：{status}
```

**token 不够时的裁剪顺序**（v1 也要约好）：

1. 必保：
   - 2. 双方当前立场（尤其 abandoned_claims）
   - 3.2 当前争点
   - 4. 被否决路径
2. 次保：
   - 3.1 共识
3. 可裁剪：
   - 1. 议题描述（允许用更短版本替代）

把这部分实现成一个不用 LLM 的 `render_markdown(state, max_tokens=None)`，手写逻辑即可。

---

## 2. 摘要流程：v1 不拆三步，先做一个“单步、强 schema”的 incremental_compact

三步填表（A/B/C）确实更稳，但你现在要一个“能跑”的版本，我建议 v1 直接：

- **只用一个 LLM 调用**：`old_state + delta_text => new_state`
- 把所有字段一次性填完，强制返回完整 `CompactState` JSON
- 本地做一点校验/补丁，保证单调性

### 2.1 配置一个独立 compact 模型 + Soft limit

配置：

```yaml
compact:
  model: "your-compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

策略：

- 构造辩手上下文前，先预估：
  - `历史上下文 tokens + 预估本轮回复 tokens`
  - 若 > `debater_limit * soft_trigger_ratio` → 先 compact，一定要保持“提前 compact”。
- 所有 compact 一律用 `compact.model`，不占用辩手配额，也不会跟辩手的 max_token 纠缠。

### 2.2 v1 核心函数：`incremental_compact_with_llm`

伪代码：

```python
def incremental_compact_with_llm(model, old_state, new_entries_text, new_covered_end):
    """
    old_state: dict or None
    new_entries_text: str, 从上一个 covered_seq_end 之后的所有 relevant entries 拼成的文本
    """

    # 1. 构造 prompt
    system = """你是辩论记录维护助手。你的任务是维护一个 JSON 状态对象 state，
    描述双方当前立场、争点、共识、已放弃主张和被否决路径。
    你将收到旧状态（可能为 null）和一段新增对话，请在旧状态基础上增量更新 state。
    要求：
    - 如果旧状态不为空，必须保留其中的已有信息，只允许：
      * 在必要时修改当前立场（core_claims / key_arguments）
      * 添加新的 abandoned_claims / pruned_paths / axioms / disputes
      * 更新现有 disputes 的 status / positions / resolution
    - 不允许随意删除旧的 axioms、abandoned_claims、pruned_paths 条目，
      除非新增对话中出现明确推翻它们的内容。
    - 返回的 JSON 必须完全符合给定 schema。
    """

    user = {
        "old_state": old_state,  # None 或 dict
        "new_entries": new_entries_text,
        "schema_hint": SIMPLE_SCHEMA_DOC  # 可选，用自然语言+key 列表提醒字段
    }

    # 2. 调用 LLM，得到 new_state_raw
    new_state_raw = call_llm_json(model, system, user)

    # 3. 本地修补：确保关键字段存在，且必要时“只增不减”
    new_state = patch_and_merge(old_state, new_state_raw)
    new_state["compact_version"] = (old_state or {}).get("compact_version", 0) + 1
    new_state.setdefault("meta", {})
    new_state["meta"]["covered_seq_start"] = (old_state or {}).get("meta", {}).get("covered_seq_start", 1)
    new_state["meta"]["covered_seq_end"] = new_covered_end

    return new_state
```

### 2.3 `patch_and_merge`：少量工程逻辑就够

这个函数只干三件事：

1. **补字段**：  
   - 如果 `participants` / `disputes` / `axioms` / `pruned_paths` 缺失，就沿用 old_state 对应部分；
2. **保证“只增不减”**：
   - 对 `axioms`、`abandoned_claims`、`pruned_paths`：
     - 建立以 `id` 或文本 hash 为 key 的集合；
     - 如果 new_state 里面比 old_state 少了很多条（可以设一个阈值，比如减少超过 30%），且 delta_text 里没明显“推翻”的信号，就把 old 的条目 merge 回 new；
   - 这一步可以先写得保守一点：**新+旧去重合并**，宁可多，不要少。
3. **ID 规范**：
   - old_state 有 id 的条目，如果 new_state 对同一内容换了 id，可以暂时不处理（v1 先不做复杂的 referential integrity），只保证 id 不为空即可。

这样你 v1 的复杂度还算可控：**只写一个函数 + 一个补丁函数**，不需要三次调用。

---

## 3. 多次 compact 的“状态转移方程”：S_n = f(S_{n-1}, Δ)

把你目前的流程拉直一下：

```python
def build_compact_context(log: Log, compact_model):
    last_cp = log.last_compact_checkpoint()

    if last_cp is None:
        old_state = None
        covered_end = 0
    else:
        cp_content = json.loads(last_cp["content"])
        old_state = cp_content["state"]
        covered_end = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(
        covered_end,
        exclude_tags=["thinking", "meta", "compact_checkpoint"]
    )
    new_entries_text = format_entries_for_compact(new_entries)

    new_state = incremental_compact_with_llm(
        model=compact_model,
        old_state=old_state,
        new_entries_text=new_entries_text,
        new_covered_end=log.last_seq()
    )

    markdown = render_markdown(new_state)

    log.add(
        name="Compact Checkpoint",
        tag="compact_checkpoint",
        content=json.dumps(
            {"state": new_state, "markdown": markdown},
            ensure_ascii=False
        )
    )

    return new_state, markdown
```

约定：

- 以后任何 compact 触发（自动、手动）都只能基于这个 `state` + 之后的 entries；
- 绝不再对旧 Markdown 做二次摘要；
- `load_from_file()` 恢复时：
  - 找最后一个 checkpoint；
  - 把 `content.state` 当作当前状态；
  - 老 entries 归档，新 entries 作为 delta。

---

## 4. 「不回滚打转」在 v1 里究竟靠什么实现？

核心就是三类“负向约束 + Canonical 状态”的组合：

1. **Canonical 立场卡覆盖初始立场**
   - 喂给辩手的上下文改成：

     ```text
     ## 辩论议题
     {state.topic.current_formulation}

     ## 辩论历史（压缩快照）
     {markdown}
     ```

   - 不再重复 topic 中的原始「A/B 的立场描述」；
   - system prompt 里写明：“以压缩快照中的立场卡为最新立场，不要再依赖最早的立场提示。”

2. **废弃主张 + 被否决路径的硬约束**

   system prompt 加一段（可复用）：

   > 你必须遵守：
   > - 不得再次将 `废弃主张` (abandoned_claims) 中的内容当作自己的论点，即使换用不同措辞；
   > - 不得再次使用 `被否决的推理路径` (pruned_paths) 中描述的论证方式，除非你在本轮引入新的关键证据并明确说明为何之前的否决不再适用；
   > - 不得在没有新理由的情况下否认 axioms 中已写明的共识。

   这样模型即使有复读冲动，被这一层硬约束“拎着后脖颈”拉回来。

3. **可选：自检 Thinking（v1 可以先不做）**

   如果你愿意多加一层，可以在调用辩手 LLM 前自动插一小段“内部自检”（tag=thinking）：

   > - 本轮你要回应的是哪个争点或问题？
   > - 你准备使用的论点是否落在废弃主张或被否决路径中？
   > 若有冲突，请先内部调整，再生成对外发言。

   这不是必须，但对大模型的效果会有明显提升。

---

## 5. 总结成一个“v1 实施清单”

### 必做（才能让 compact 真正用起来）

1. **更改 compact_checkpoint 结构**

   - `content` 改为 `{"state": {...}, "markdown": "..."}`；
   - `state` 使用精简 schema（topic / participants / disputes / axioms / pruned_paths / meta）。

2. **实现 `incremental_compact_with_llm`**

   - 输入：`old_state`, `new_entries_text`, `new_covered_end`；
   - 输出：新的 `state`（完整 schema）；
   - 用一个 LLM 调用 + 一个 `patch_and_merge` 函数保证：
     - 字段齐全；
     - axioms / abandoned_claims / pruned_paths “只增不减”。

3. **实现 `render_markdown(state)`**

   - 生成固定结构的 Markdown（立场卡 → 共识 & 争点 → 被否决路径）；
   - 内部按优先级裁剪内容。

4. **改上下文构造逻辑**

   - 在 compact 后，给辩手喂的是：
     ```text
     ## 辩论议题
     {state.topic.current_formulation}

     ## 辩论历史（压缩快照）
     {markdown}
     ```
   - 不再同时附整段老对话。

5. **在辩手 system prompt 中加入对废弃主张 & 否决路径 & 共识的约束**

   - 明确“不得复用”、“不得重启已解决争点”等规则。

### 可选 / 以后再加

- 分三步（A/B/C）填表式调用提高鲁棒性；
- 增加 timeline_brief、open_questions、assumptions、weaknesses 等丰富演进表达；
- 把 pruned_paths 提取成外部校验规则（真正做“硬剪枝”）。

---

如果你愿意，我可以在下一轮直接给出：

- 一个实际可用的 `incremental_compact_with_llm` Prompt 模板（中文，匹配上面 v1 schema）
- 一个 `render_markdown(state)` 的具体伪代码/示例实现

这样你只需要把这两个块塞进 `debate-tool` 的 `build_compact_context()` 调用链里，就能直接跑一版 v1。

---


### [16] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-12T15:47:56.340054*

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

---
