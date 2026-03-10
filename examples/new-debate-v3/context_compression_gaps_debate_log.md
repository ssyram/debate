# v3 认知引擎：上下文压缩续跑——五个未裁定点 辩论日志

> 2026-03-10T12:28:26.063290

---


### [1] Linus Torvalds

*2026-03-10T12:23:42.165162*

好，我们别再搞“哲学辩论”。这五个点里有的是真问题，有的是你们自己把系统想复杂了。

下面是**第 1 轮我的初始立场**（至少两个点；我会顺便打掉一个对手常见的烂论点）。

---

## A：L2Return 是否是独立爆炸点？
### 1) 裁定结论
**否（是假问题），前提是你把它定义成“增量事件”，而不是“状态快照”。**

给我一个硬接口定义，避免你们嘴上说“增量”实际塞全量：

```ts
type EpochId = number;

interface L2Return {
  epoch_id: EpochId;

  // 必须是“本 epoch 新增/变更”，禁止重发未变更项
  verified_claims_delta: VerifiedClaimDelta[];   // not full list
  suspended_claim_ids_delta: string[];           // ids only
  new_gaps_delta: GapSpec[];                     // newly discovered only
  schema_challenges_delta: SchemaChallengeNotice[]; // new/updated only

  ranking_delta: { changed: boolean; details?: string };

  // 必须带可计算的大小指标，L1 可以拒收/报警
  size_bytes: number;
}
```

L1 维护“当前未解决 gap 的完整状态”在**自己的状态存储**里，不进 prompt 的“历史 L2Return”里：

```ts
interface GapStore {
  upsert(gap: GapSpec, epoch_id: EpochId): void;
  mark_resolved(gap_id: string, epoch_id: EpochId): void;
  list_open(limit: number, order: "blocks_termination_first" | "oldest"): GapSpec[];
}
```

`PromptMaterializer` 只从 `GapStore/ChallengeTracker/...` 取当前需要的片段，**不需要任何 “拼接所有 L2Return” 的鬼东西**。

### 2) 核心论据（一句话）
把 `L2Return` 当历史日志塞进 prompt 的人是在用 LLM 当数据库，这是纯粹的自找回归。

### 3) 可推翻条件
如果你们实际上需要在 L1 prompt 中引用“过去 N 个 epoch 的 gap 发现过程”（不是当前状态），那就证明了你们的 L1 状态机不完整——给出一个必须依赖历史过程而非当前状态的**具体函数签名和 trace**，我就改口。

---

## B：rejection_history 无界增长时的上限保护
### 1) 裁定结论
**有条件：热集固定上限 + 溢出归档到冷区（但冷区失败必须可观测，且不能改变语义）。**

你要的数字：先别装聪明，给个能跑的默认值。

- `MAX_REJECTION_HOT = 20_000` 条（热区 set）
- 指纹固定 32 bytes（例如 BLAKE3-256），热区裸数据 ~640KB，完全可控  
- 冷区：append-only 文件/kv（随你），但查询必须有明确失败路径

接口：

```ts
type Fingerprint = string; // hex blake3-256, len=64

interface RejectionHistory {
  has(fp: Fingerprint): Promise<boolean>; // checks hot then cold
  add(fp: Fingerprint): Promise<AddResult>;
  stats(): { hot_count: number; cold_count?: number; hot_bytes: number };
}

type AddResult =
  | { kind: "ADDED_HOT" }
  | { kind: "EVICTED_TO_COLD"; evicted: Fingerprint[] }
  | { kind: "HOT_FULL_DROP"; dropped: Fingerprint } // fallback if cold fails
  | { kind: "ERROR"; error: RejectionStoreError };

type RejectionStoreError =
  | { kind: "COLD_IO_FAIL"; detail: string }
  | { kind: "COLD_CORRUPT"; detail: string };
```

策略（组合而不是三选一装死）：
- 热区超限：**FIFO/LRU 淘汰一批**（例如一次淘汰 256 条）写入冷区
- 冷区写失败：允许退化为 `HOT_FULL_DROP`（不写新 fp），但必须打 `ALERT_rejection_cold_fail`，并把 error 状态挂在系统 health 上

### 2) 核心论据（一句话）
你要的是“避免重复探索”，不是“永不遗忘”，所以用热集保证性能、冷区保证覆盖，失败就显式降级而不是悄悄撒谎。

### 3) 可推翻条件
如果你能证明：在你们的 workload 下，`has(fp)` 的冷区查询（哪怕只在热区 miss 时）会造成不可接受的 P95 延迟（给数字，比如 >50ms），那我会改成“纯热区 + 只告警 + 丢弃新 fp”。

---

## E：ChallengeTracker ACTIVE 数量阈值的具体值
### 1) 裁定结论
**阈值来源：动态按 token 预算计算 + 硬上限常数兜底。选择策略：blocks_termination 优先，其次最老。**

别再搞“QN 节点估算复杂度”那种玄学。token 预算是硬事实。

接口：

```ts
interface PromptBudget {
  max_prompt_tokens: number;
  reserved_tokens: number; // gap_spec + evidence_summary + instructions etc.
  avg_challenge_tokens: number; // measured, moving average
}

function maxActiveChallengesInPrompt(b: PromptBudget): number {
  const available = Math.max(0, b.max_prompt_tokens - b.reserved_tokens);
  const n = Math.floor(available / Math.max(1, b.avg_challenge_tokens));
  return clamp(n, 1, 12); // hard cap 12, min 1
}
```

选择策略：

```ts
function pickActiveChallenges(
  active: ChallengeNotice[],
  limit: number
): ChallengeNotice[] {
  return active
    .sort((a,b) =>
      (b.blocks_termination ? 1:0) - (a.blocks_termination ? 1:0) ||
      a.first_seen_epoch - b.first_seen_epoch
    )
    .slice(0, limit);
}
```

### 2) 核心论据（一句话）
你不按 token 预算做阈值就是在写“有时会超窗”的系统，而超窗就是 regression。

### 3) 可推翻条件
如果你能提供证据：`avg_challenge_tokens` 的估计波动导致选入数量在相邻 epoch 之间剧烈跳变（比如 12→2→11），并且这种抖动可复现地降低修复成功率（给出成功率差异），我会同意改成“固定常数 + 轻量长度预估”的混合。

---

## 预先反驳：你们最可能犯的错误（我现在就拆）
你们会有人对 A 说这种话：

> “L2Return 虽然是增量，但为了让 LLM 理解进展，我们要把历史 gap 发现过程也注入 prompt。”

不，这就是典型的“把日志当状态”。**进展不是故事，是状态机。**  
你真需要“进展”，就给一个可计算的状态摘要字段，而不是把历史文本塞回去：

```ts
interface GapProgress {
  gap_id: string;
  status: "OPEN" | "IN_REPAIR" | "RESOLVED" | "SUSPENDED";
  attempts: number;
  last_attempt_epoch: number;
  last_error_kind?: string;
}
```

然后 `PromptMaterializer` 只注入 `GapProgress` 的 top-K（比如 K=10）。这叫工程，不叫写作文。

---

我这一轮已经给了 A/B/E 的裁定。下一轮你要我继续，我会把 **C（裁判 prompt 压缩）** 和 **D（repair attempted_scopes 压缩）** 也按同样方式钉死：触发阈值、压缩格式、失败路径，别再用“合理”“适当”这种词糊弄。

---


### [2] Ssyram

*2026-03-10T12:23:42.165192*

直接说结论。A 和 B 是假问题，暴露了提问者对系统架构和基础计算机科学的类型错误。D 是真正的核心，它本质上是 CEGAR（反例指导的抽象精化）循环的收敛性问题。

我选 A 和 D 进行裁定，顺便把 B 扫进垃圾桶。（B 是一个纯内存 `HashSet<u64>` 的 O(1) 查找问题，10 万条 32 字节哈希才占用 3.2MB 内存，既不进 Prompt 也不卡 IO。在 2024 年讨论这个的上限保护，属于典型的无病呻吟，直接忽略。）

### 待裁定点 A：L2Return 是否是独立爆炸点？

**1. 裁定结论：否。这是一个假问题。L2Return 必须是纯增量（EpochDelta）。**
Layer 1 的 `PromptMaterializer` 必须实现一个 `fold` 函数，而不是 `concat`。
接口约束：
```typescript
// L2Return 签名必须是严格的增量事件
type L2Return = Event<EpochDelta>;
// L1 状态更新必须是 Reduce 操作
function apply_l2_return(state: L1State, event: L2Return): L1State { ... }
```

**2. 核心论据：**
`L2Return` 的类型语义是状态机转换的「事件（Event）」，将其作为「历史记录」拼接进 Prompt 是把动词当名词用的架构级类型错误。

**3. 可推翻条件：**
如果在真实运行中，**单个** Epoch 产生的 `new_gaps` 增量序列化后超过 4000 tokens。此时说明 Layer 2 的 Gap 发现粒度彻底失控，需要引入 L2 内部的流控（Rate Limiting），而不是在 L1 讨论压缩。

---

### 待裁定点 D：repair() LLM 上下文的压缩策略

这是最关键的设计。`attempted_scopes` 记录的是什么？是失败的尝试。在形式化验证（CEGAR）中，这叫 **UNSAT Core（不可满足核心）**。你不能对 UNSAT Core 做「模糊摘要」，否则你的搜索树永远无法被有效裁剪。

**1. 裁定结论：绝对禁止自然语言摘要。引入 `NegativeConstraint` 显式负向约束接口。**
丢弃所有中间探索的自然语言描述，只保留精确的排他条件。
接口定义：
```typescript
interface NegativeConstraint {
  target_gap_id: string;
  // EXHAUSTED 必须全量保留，ACTIVE_STAGE 只保留当前阶段的约束
  status: "EXHAUSTED" | "CURRENT_STAGE"; 
  excluded_paths: string[]; // 例如: ["hypothesis.evidence_chain.axis_X"]
  excluded_values: string[]; // 具体的哈希或关键特征词
}
```
注入 Prompt 时，格式必须是硬指令：`Constraints: Do NOT generate values matching [excluded_values] for [excluded_paths].`

**2. 核心论据：**
失败的 scope 等价于定理证明器中的反例，用 LLM 对反例进行自然语言摘要会破坏精确的排他边界，导致 LLM 在后续轮次中于同构子空间内无限死循环。

**3. 可推翻条件：**
当累积的 `excluded_values` 条目数超过 50 条时。此时说明 LLM 已经陷入过度受限的死胡同，继续追加负向约束会导致 LLM 产生指令依从性崩溃（Instruction Following Degradation）。此时应当直接触发 `S7(Suspended)` 请求人类介入，而不是继续压缩。

---

### 提前反驳

我提前点名 **Kant**（或者任何试图在 D 点引入大模型摘要机制的人）。

Kant 必然会提出类似这样的方案：“当 `attempted_scopes` 过长时，我们应该用 LLM 提取出『核心语义分歧』或『方向性洞察』，告诉 repair 节点『这条语义路径走不通』。”

**这是对大模型本质的无知。**
大模型是「提示词引导的概率分布模式匹配搜索」。如果你给它的 Prompt 是“尝试了 A、B、C 方向均失败，请总结经验”，它提取的摘要会变成“字母前序方向不可行”。下一轮 repair 时，它会以极大概率生成 A' 或 A.1——因为它没有收到硬性的截断指令。

没有任何系统设计会用「权重由 LLM 决定的模糊摘要」去裁剪搜索空间。你刚才如果想提摘要方案，那是正确的废话——真命题，但毫无工程可行性。给我明确的 `EXCLUDES` 签名，别用自然语言糊弄。如果没有精确的负向约束，你所谓的“压缩”只是在制造下一次 OOM 和死循环。

---


### [3] 康德（Immanuel Kant）

*2026-03-10T12:23:42.165204*

我先把五点翻译成一个共同的先验问题：你们在问“哪些结构会成为 prompt 的经验性负担”，但若不区分**传递物（message）**与**状态（state）**，就会把“通信增量”误当成“记忆累积”。这类混淆一旦发生，压缩策略会从调节性工具僭越为构成性教条——仿佛系统“必然需要”携带历史，而非仅需携带**可追责的当前综合**。

下面我对五点中 **A、B、C、D、E 至少两点**给出第一轮裁定（我会全部给出），每点都含：裁定结论（含接口/阈值）、核心论据一句、可推翻条件。并且我会提前反驳一个我预计对手会犯的错误（指名并引用你给的文本）。

---

## A：L2Return 是否是独立爆炸点？——裁定：**否（有条件）**；它应被规定为**严格增量消息**，并被 L1 状态吸收

### A1. 裁定结论（接口/定义）
1) **传递模式：必须是增量**（仅本 epoch 新增/变更），并显式区分“新增”与“闭合/撤销”：
```ts
type GapId = string;

interface L2Return {
  epoch_id: number;

  gap_delta: {
    opened: GapSpec[];          // 本 epoch 新发现
    updated: GapSpec[];         // 同 gap_id 的精化（如 narrowing）
    closed: { gap_id: GapId; resolution: "RESOLVED"|"INVALIDATED"|"MERGED"; note?: string }[];
  };

  verified_claims: VerifiedClaim[];     // 同样作为 delta：只传新增或状态变更
  suspended_claims: string[];           // delta：只传新增挂起项
  schema_challenges: SchemaChallengeNotice[]; // delta
  ranking_delta: { changed: boolean; details?: string };
}
```

2) **L1 维护“当前未解决 gap 的完整状态”**，由 `PromptMaterializer` 所在的 L1 状态层管理，而不是靠拼接历史 L2Return：
```ts
interface GapStateStore {
  upsert(gap: GapSpec): void;
  close(gap_id: GapId, resolution: string, note?: string): void;
  get_open(filter?: { blocks_termination?: boolean; axis?: string }): GapSpec[];
}
```

3) Prompt 注入：`PromptMaterializer` 只注入“当前 open gaps 的子集 + 其 lineage 指针”，不注入历史回合消息：
```ts
interface ContextBundle {
  open_gaps: { gap_id: GapId; summary: string; blocks_termination: boolean; last_epoch: number }[];
  gap_lineage_refs?: { gap_id: GapId; archive_ref: string }[];
}
```

### A2. 核心论据（一句话）
“爆炸”只发生在把**消息历史**当作**状态本体**时；只要 L2Return 是 delta 且 L1 有可审计的 GapStateStore，历史 L2Return 没有认识论必要进入 prompt。

### A3. 可推翻条件
- 若你们要求裁判/repair 在 prompt 中必须“重放全部 gap 发现过程”以保证可追责，那么 L2Return 会变成爆炸点；但那将是把**可追责性**误设为必须的**构成性历史重演**，应改为 ledger/refs，而非堆叠文本。

---

## B：rejection_history 无界增长上限保护——裁定：**有条件**；默认不做 prompt 压缩，只做**两级集合 + 明确阈值 + 失败即降级为保守停机**

### B1. 裁定结论（阈值/路径/失败行为）
1) 阈值来源：**固定常数 + 可配置覆盖**（因为它是运行时资源约束，不是世界结构）。
```ts
interface RejectionHistoryConfig {
  hot_max_entries: number;   // 默认 50_000
  cold_max_entries: number;  // 默认 1_000_000（可选）
  mode: "HOT_ONLY" | "HOT_COLD";
}
```

2) 处理路径：选择 **路径三（冷存储归档）为主 + 热区上限**；热区超限时把最旧 10% 批量迁移到冷区（不是丢弃）。
```ts
interface RejectionHistory {
  hot: Set<Fingerprint>;
  cold_ref?: string; // 指向冷区 bloom/filter+chunk 索引
}
```

3) 查询策略：先 hot，再 cold（cold 用 bloom filter + chunk 查）。
4) 失败行为：若归档/查询 cold 发生 `IO_FAIL|INTEGRITY_CHECK_FAIL`，系统进入：
```ts
type RejectionHistoryDegraded =
  | { state: "DEGRADED_NO_COLD"; action: "STOP_REPAIR_AND_SURFACE_ALERT" }
```
也就是：**禁止**默默当作“没拒绝过”，否则你们会重复探索被否决空间，形成辩证幻象式无限回归。

### B2. 核心论据（一句话）
拒绝史的功能是“阻止重复走已判死路”，一旦归档失败却假装不存在，就把经验性的 IO 偶然性僭越成认知上的“允许重试”。

### B3. 可推翻条件
- 若 fingerprint 命中并不用于“剪枝”，而仅用于统计（即命中不影响 repair 的搜索空间），则 cold 失败不必停机；但那将改变 rejection_history 的认识论角色。

---

## C：裁判 prompt 的完整压缩规格——裁定：**是（必须补齐）**；触发以 token 比例为主，策略为“近 K 轮原文 + 远期结构化争点表”，失败用“裁判自检 + 最小重放”修复

### C1. 裁定结论（触发/策略/失败行为）
1) 触发条件（混合，但以 token 为主）：
```ts
const JUDGE_PROMPT_BUDGET_RATIO = 0.60; // 超过上下文窗 60% 触发压缩
const JUDGE_MAX_FULL_TURNS = 4;         // 最近 4 轮保留原文
```

2) 压缩策略（接口定义）：
- 保留最近 `K=4` 轮辩论原文（双方发言+裁判指令）。
- 更早轮次压缩为**争点表（IssueTable）**，按“待裁定点 A-E”对齐，记录每方最终立场、证据指针、可推翻条件。
```ts
interface IssueTableRow {
  issue_id: "A"|"B"|"C"|"D"|"E";
  positions: { speaker: string; ruling: "YES"|"NO"|"CONDITIONAL"; numbers_or_interfaces: string }[];
  key_attacks: { from: string; quote: string; flaw: string }[];  // 必须含“精确引用”
  falsifiers: { speaker: string; condition: string }[];
}
interface JudgePromptCompressed {
  recent_turns_verbatim: string[];
  issue_table: IssueTableRow[];
  refs: string[]; // 指向 ledger/archive_ref，而不是复制全文
}
```

3) 失败行为（质量不足检测与应对）：
- 检测：裁判输出必须满足结构约束：每个 issue 至少引用一次对手原文片段（`quote` 非空），且每个裁定都有 falsifier。否则判为：
```ts
type JudgeQualityFail = { kind: "MISSING_QUOTE"|"MISSING_FALSIFIER"|"UNCOVERED_ISSUE"; issue_id?: string }
```
- 应对：触发“最小重放 re-inject”：只回填缺失 issue 对应的那 1-2 轮原文片段（按 `issue_id` 的对齐索引取回），再重裁判。

### C2. 核心论据（一句话）
裁判若不携带“可反驳条件 + 精确引用”，就会把总结误当成裁定，把调节性整理僭越为构成性判决。

### C3. 可推翻条件
- 若你们接受裁判为“启发式打分器”而非“可追责裁定器”，可以放松引用与 falsifier 约束；但那改变系统的规范目标，不是压缩细节。

---

## D：repair() LLM 上下文压缩策略（attempted_scopes）——裁定：**有条件**；EXHAUSTED 不要求全量文本，但要求**可验证的覆盖证明**（集合摘要 + 代表例）

### D1. 裁定结论（可压缩/触发/格式）
1) 哪些可压缩：
- `STRICT`、`RELAXED` 阶段的 attempted_scopes：可摘要（它们是探索轨迹，不是最终证明）。
- `ADJACENT`：保留更多细节，但仍可摘要。
- `EXHAUSTED`：**不保留全量列表**，改为“覆盖摘要 + 少量水印代表例 + 可再水合引用”。

2) 触发条件：
```ts
const MAX_SCOPES_VERBATIM = 12;      // 单个 challenge 超过 12 条 scope 触发压缩
const EXHAUSTED_WATERMARKS = 6;      // exhausted 保留 6 个代表失败 scope
```

3) 压缩格式（关键：让 LLM 不重复，同时可审计）：
```ts
type ScopeFingerprint = string;

interface AttemptedScopesCompressed {
  stage: "STRICT"|"RELAXED"|"ADJACENT"|"EXHAUSTED";
  total_count: number;

  // 1) 覆盖摘要：用可计算的集合摘要（例如分桶+hash 前缀），不是纯自然语言
  coverage: { bucket: string; count: number; fp_prefixes: string[] }[];

  // 2) 水印：少量具体失败例，防止“抽象遗忘”
  watermarks: { scope_text: string; reason: string; fp: ScopeFingerprint }[];

  // 3) 追责引用：需要时可 rehydrate
  archive_ref?: string;
}
```

### D2. 核心论据（一句话）
“EXHAUSTED 必须全量保留”是把经验性清单当作构成性证明；真正需要的是**覆盖可追责**，而非文本堆积。

### D3. 可推翻条件
- 若 `is_homologous()` 的误判率在你们基准测试中高到使 coverage 摘要无法阻止重复（例如重复率>20%），则必须提高 watermarks 数或临时保留更长的 verbatim 列表。

---

## E：ChallengeTracker ACTIVE 数量阈值具体值——裁定：**是**；阈值应由 token 预算动态推导，但必须给出可审计上界与选择规则

### E1. 裁定结论（来源/数值/选择/失败恢复）
1) 阈值来源：**方案三（动态 token 预算）+ 硬上界常数**（避免不可预测）：
```ts
const ACTIVE_PROMPT_BUDGET_RATIO = 0.20; // repair prompt 中 20% token 给 challenges
const MAX_ACTIVE_CHALLENGES_HARD = 8;    // 无论如何最多 8 个进入 prompt
const MIN_ACTIVE_CHALLENGES_FLOOR = 3;   // 再少也至少 3 个（防止过拟合单一路径）
```

2) 选择策略：**阻塞性优先**（blocks_termination=true）第一序；第二序用“最近失败次数/回合密度”：
```ts
score = 1000*blocks_termination + 10*recent_failures + age_epochs
```
取 top-K 注入。

3) 失败行为（被排除导致错误判定如何检测恢复）：
- 检测：若本 epoch 出现 `ranking_delta.changed=false` 且 `consecutive_filtered_epochs` 增长到 3（你们已有该字段），同时 open gaps 未减少，则判定为“选择集可能遗漏关键 ACTIVE”：
```ts
type PromptSelectionStall = { kind: "ACTIVE_SET_STALL"; epochs: number }
```
- 恢复：下一轮强制“轮转注入”——将被排除的 ACTIVE 按 score 次序分批进入 prompt（类似 round-robin），直到 stall 解除或进入 EXHAUSTED。

### E2. 核心论据（一句话）
阈值若是纯常数，就把资源约束当作世界结构；但若是纯动态又不可审计，所以必须“动态可推导 + 硬上界”。

### E3. 可推翻条件
- 若你们能证明 challenge 文本长度方差极小（例如 p95/p50 < 1.2），固定常数阈值就足够；否则固定阈值会系统性偏置“短 challenge”。

---

## 预先反驳：我预计你们会犯的一个错误（指名引用）

你在 A 点给出“判断一”的表述是：**“Layer 1 如果需要在 prompt 中注入历史所有 epoch 的 gap 处理进展，就需要拼接所有历史 L2Return 的 new_gaps 字段。”**

这里有一个需要先被区分的概念混乱：把“需要可追责”误写成“需要拼接原文历史”。  
可追责性在你们系统里已由（已裁定的）ledger/archive_ref 方向承担；因此把历史 L2Return 全拼进 prompt，是一种把**调节性记账**僭越为**构成性呈示**的设计冲动。它会制造一个虚假的爆炸点，然后用压缩去治疗自造的疾病。

**可推翻条件**：若你们的裁判规则明确要求“每个 gap 的裁定必须引用其最初提出时的自然语言描述全文”，那我接受 L2Return 会爆炸；但我会建议修改裁判规则，而不是给 L2Return 做文本压缩——因为那是在规范层制造不可能任务。

---

若你要进入第二轮交叉质询，我建议你先回答一个工程上可检验的问题（它决定 A/D 的细节）：  
`is_homologous()` 的误判率（false positive/false negative）在你们离线回放中的区间是多少？只要给一个 p50/p95，我就能把 D 点的 `EXHAUSTED_WATERMARKS` 与 coverage 分桶粒度进一步定量化。

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-10T12:24:18.702038*

1) **你把 A 直接“类型定死”为 Event/EpochDelta，但你没给出 Delta 的强约束字段和去重语义。**  
“L2Return 必须是纯增量”是口号，不是设计。`new_gaps` 增量怎么定义？按 `gap_id` 去重还是按 `(discriminator, scope)`？同一个 gap 的“精化更新”算新 gap 还是更新事件？  
给我能跑的签名，不是宣言：

```ts
type GapId = string;

type EpochDelta =
  | { kind: "GAP_NEW"; gap: GapSpec }
  | { kind: "GAP_UPDATE"; gap_id: GapId; patch: GapPatch }  // 你没定义这个
  | { kind: "GAP_RESOLVED"; gap_id: GapId }
  | { kind: "SCHEMA_CHALLENGE_NEW"; ch: SchemaChallengeNotice }
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaim }
  | { kind: "CLAIM_SUSPENDED"; claim_id: string; reason: RehydrateError | string };

function apply_l2_event(s: L1State, e: EpochDelta): Result<L1State, ApplyError>;
```

没有 `GAP_UPDATE/RESOLVED` 这种最基本的事件类型，L1 只能“猜”怎么 fold，最后就会退化成你骂的 concat。你现在的论证就是：把问题藏到未定义处，然后宣布问题不存在。

可证伪实验也别扯“单个 epoch >4000 tokens”这种拍脑袋阈值——真正会炸的是**事件风暴**：L2 在一个 epoch 内对同一 gap 产生 200 次微更新，每次都很小，但总数巨大；你的 “4000 tokens”根本抓不到这个结构性失败。

---

2) **你把 B 扔进垃圾桶，但你的数字是错的，而且你忽略了失败路径：不是内存，是“语义退化+DoS 面”。**  
你说“10 万条 32 字节哈希=3.2MB”。典型 `HashSet<u64>` 条目 8 字节没错，但实际集合开销远不止 8 字节/entry：装载因子、bucket、指针、allocator 碎片——你这种“基础计算机科学”姿态，结果给出幼儿园级别内存估算。

更重要的是：这玩意儿不是只占内存。你没回答裁定点 B 的关键——**超限后系统做什么**。  
- 如果永不淘汰：攻击者/坏输入可以让 rejection_history 单调增长，最后变成你 repair() 的“永恒否决器”，系统探索空间被永久污染。  
- 如果淘汰：会重新进入已否决语义空间，造成循环。  
这两者都需要明确的策略和失败分支。你直接“忽略”=没有定义系统在压力下的行为，这就是工程上的 bug，不是哲学。

给个最小可执行的策略也行，比如：

```rust
fn record_rejection(set: &mut HashSet<u64>, fp: u64, cap: usize) -> Result<(), RejectStoreError>;
```

`cap` 从哪来？超限返回什么？是 drop 还是 evict？你没写，等于没设计。

---

3) **D 点你喊“禁止自然语言摘要”，但你给的 NegativeConstraint 结构是不可实现的空壳：excluded_paths/values 没有类型系统支撑，等价于字符串拼写比赛。**  
`excluded_paths: string[]` 这种东西就是把 bug 写进接口：  
- `"hypothesis.evidence_chain.axis_X"` 拼错一个字符，约束静默失效；  
- LLM 生成的对象结构变了（字段重命名/嵌套变化），path 全废；  
- `excluded_values` 用“关键特征词/哈希”混着来？那 `is_excluded(candidate)` 怎么算？给我可计算公式，不要“硬指令”。

你要真想学 CEGAR/UNSAT core，就别用字符串。给我一个能 check 的判定函数签名：

```ts
type JsonPtr = string; // 如果你非要用 path，也至少限定成 RFC6901 并做校验
type Fingerprint64 = bigint;

interface NegativeConstraint {
  target_gap_id: string;
  status: "EXHAUSTED" | "CURRENT_STAGE";
  path: JsonPtr;
  fp: Fingerprint64;           // 只允许一种可计算形式
  match: "EQ" | "PREFIX";      // 给出明确匹配算子
}

function fingerprint_at(path: JsonPtr, candidate: unknown): Result<Fingerprint64, FpError>;
function violates(c: NegativeConstraint, candidate: unknown): Result<boolean, EvalError>;
```

另外你说“excluded_values > 50 就 S7 挂起”，又是玄学阈值。50 是怎么来的？不同 gap 的分支因子不同，50 可能太小也可能太大。至少给个可实验的判据：比如“最近 N 次 repair 提案中，违反约束比例 > p 且连续 k 次无新信息增益”，用数字说话。

---

你这轮最大的问题：嘴上全是“类型错误”“架构级错误”，但真正需要强类型的地方（Delta 语义、rejection_history 超限行为、NegativeConstraint 的可判定匹配）你全都留白。把空白处骂成“假问题”并不会让系统在边界条件下不崩。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-10T12:24:49.228558*

你的分类很精致，但工程实现上存在两个类型错误和一个状态机死锁。别用哲学词汇掩盖接口缺陷，我们直接看代码逻辑。

针对你的第一轮发言，我提出三个致命的工程质询。不接受概念辩护，请直接用明确的算法流程或函数签名来回答。

### 质询一：B 点（rejection_history 冷区查询）存在根本性的类型错误

你提议在冷区使用 `bloom filter + chunk 查` 来处理 `rejection_history`。这是一个基础的数据结构类型错误。

`rejection_history` 的核心功能是拦截同源的重复探索，这依赖于 `is_homologous(draft_A, draft_B)` 进行**语义相似度/同源性判断**，而不是精确的字节匹配。
Bloom Filter 的数学性质决定了它只能处理精确哈希匹配（Exact Match）。如果草稿 A 和草稿 B 语义相同但表述差了一个字，它们的哈希值完全不同，Bloom Filter 必定返回 false。

**我的质询：**
如果你用精确哈希，冷区将失去防范“语义重复”的能力，形同虚设；如果你要支持语义匹配，Bloom Filter 根本做不到。
请问你的 `cold_ref` 到底用什么索引结构来支持 $O(1)$ 或 $O(\log N)$ 的**语义同源性查询**？如果必须做 $O(N)$ 的向量检索或 LLM 遍历，你的 IO 延迟如何控制？给我具体的查询函数签名。

### 质询二：C 点（裁判 prompt 压缩）隐藏了不可审计的 LLM 概率坍塌

你定义了 `IssueTableRow`，要求把早期轮次压缩为包含 `positions`、`key_attacks` 和 `falsifiers` 的结构化争点表。

你给出了漂亮的数据结构，但你回避了**谁来实例化这个结构**。把多轮非结构化的自然语言辩论转化为高度结构化的 `IssueTableRow`，必然需要一次 LLM 调用。这意味着你用 LLM 的概率生成去压缩“裁判据以判决的核心证据”。
我最厌恶的就是“权重由 LLM 决定且不可审计”。如果这个压缩 LLM 漏掉了一个关键的 `falsifier`，裁判 LLM 根本无从察觉，你所谓的“裁判自检（检测 MISSING_FALSIFIER）”也只会检查裁判自己的输出，无法查出**压缩阶段**丢失的信息。

**我的质询：**
你如何保证生成 `IssueTable` 的那个压缩动作本身没有发生“信息丢失”或“幻觉”？这个压缩动作如果失败（提取了错误的争点），系统如何检测并回滚？别告诉我“依靠 prompt 约束 LLM”，我要看具体的校验机制代码。

### 质询三：E 点（Active Challenge 轮转注入）打破了 CEGAR 循环的单调性

你提议在检测到 stall（停滞）时，触发“轮转注入（round-robin）”，把之前排除的 ACTIVE challenge 分批放进 prompt。这是典型的状态机死锁设计。

在 CEGAR（反例引导的抽象精化）架构中，精化条件必须是单调递增的。当前在 prompt 里的 `blocks_termination=true` 的 challenge 是**必须满足的约束**。如果你为了把旧的 challenge 放进来，而把当前的 blocking challenge 从 prompt 里“轮转”出去，LLM 就会“忘记”当前的约束，生成一个破坏已有约束的 repair。
结果就是：Layer 2 再次报错，把刚才移出去的 challenge 又加回来。你亲手制造了一个无休止的“打地鼠”震荡循环（Oscillation loop）。

**我的质询：**
当你把一个未解决的 ACTIVE challenge 从 prompt 中“轮转”出去时，你如何防止 LLM 产出的新草稿在 Layer 2 验证时再次触发这个被隐藏的 challenge？如果不解决这个回归（Regression）问题，你的 round-robin 怎么证明它能收敛？

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-10T12:25:23.216987*

### 质疑 1（针对 A）：你把“历史过程不进 prompt”当成构成性原则了，但它其实只是调节性策略——例外条件没有先验边界  
我先把你的论证翻译成我的框架：你要求 **L2Return 必须是增量事件**，并断言“把历史日志塞进 prompt”是错误范式。这里有一个需要先被区分的概念混乱：  
- “LLM 不应充当数据库”是一个**调节性理念**（regulative）：用于约束设计倾向、抑制上下文膨胀。  
- 但你把它写成了“**禁止引用过程史**”的硬接口规范，等于把一个调节性原则僭越成**构成性原则**（konstitutiv）：仿佛你先验地知道所有未来的判断都只需“状态”而不需“生成史”。

可推翻点（你自己也给了，但不够细）：你要求对手给出“必须依赖历史过程的函数签名和 trace”。问题在于：系统里确实存在一类任务，其对象不是“当前 gap 状态”，而是“**判断力的可追责性**”（accountability of judgment）——例如：  
- 为什么某 gap 被标记为 `SUSPENDED` 而不是继续 repair？这不是事实状态，而是**规范性正当化**。  
- 为什么某 schema_challenge 被判定为“同源张力、禁止广度引擎”？这涉及到 is_homologous 的判定路径是否稳定、是否引入偏见。  

这些都不是“日志癖”，而是当系统要对人类 stakeholder 可审计时，**过程证据**可能成为必要输入。你需要给出一个“图型停止判据”：在什么先验条件下，过程史可以被安全地遗忘而不损害可审计性？如果你答不出，那 A 不能被你“钉死”为假问题，只能被标记为：默认不注入历史，但保留可回溯接口（调节性残余）。

---

### 质疑 2（针对 B）：你允许 `HOT_FULL_DROP`，却声称“不能改变语义”——这里有一个自相矛盾  
你说冷区失败时可以退化为 `HOT_FULL_DROP`（不写新 fp），同时又强调“失败必须可观测，且不能改变语义”。但“是否记录 rejection fingerprint”本身就参与后续探索路径：  
- 记录失败指纹 ⇒ 未来会被 `is_homologous()` 过滤掉一大片草稿空间；  
- 不记录 ⇒ 未来可能重复进入同一语义子空间，repair 策略与 compute 预算分配会改变。  

这已经是**系统行为语义**的变化，不只是性能退化。你把“可观测”当作补偿，但“可观测”最多是经验层面的告警，并不能恢复被改变的推理轨迹。

你需要补上一个区分：  
- 这是“现象层的运行时行为变化”（acceptable degradation），还是你还想维持“同一问题同一输出”的更强要求？  
可推翻条件：如果你明确系统的目标语义只覆盖“正确性（soundness）不下降”，而不要求“探索去重的完备性”，那 drop 才算合法；否则你必须提供一个恢复机制（例如：冷区恢复后触发一次补写、或将该期间的 drop 记录为 `regulative_residue` 并强制 repair 进入保守模式）。现在你的方案在认识论上是“既要说语义不变，又允许语义条件被撤销”。

---

### 质疑 3（针对 E）：你用 token 预算做阈值，看似经验主义地“硬事实”，但跨轴加法与可审计性条件没给出来  
你提出 `avg_challenge_tokens` 的 moving average，并据此算可注入的 challenge 数量。这是工程上自然的，但在认识论上有两个缺口：

1) **跨维度权重的先验合法性**：你在做一种隐含加法——把“挑战的重要性（blocks_termination/oldest）”与“文本长度”放在同一个选择函数里。为什么长度可以作为裁剪的重要维度？这不是自明的。你至少要给出 stakeholder 可反推的审计信息：某个 challenge 被排除，是因为 token 预算不足，而不是因为模型偏好、或训练语料诱导的“自然倾向”。  
可推翻条件：如果你能输出一个审计字段，如 `selection_trace: {budget, per_item_tokens_est, excluded: [...reasons]}`，并保证可复现，那么这个加法才在先验上变得可接受。

2) **“blocks_termination”本身是何种判断？** 它是分析的（由定义直接推出）还是综合的（依赖经验统计/启发式）？如果是后者，你把它当成排序首要键，会把一个经验启发式僭越成构成性原则：系统可能被某些错误标注的 “阻塞性” 长期牵引，形成辩证幻象式的无限追逐。  
可推翻条件：若 `blocks_termination` 的赋值规则可形式化、可校验、可被反例推翻（例如：给出判定器的必要充分条件或最小反例集），则优先级才是合法的；否则应把它降格为调节性提示而非硬排序首项。

---

这三点都不是要否定你的工程直觉，而是要求你把“有用”的启发式明确地放回其应有的认识论地位：哪些是调节性约束，哪些被你不自觉地写成了构成性断言；以及每个断言的可推翻边界在哪里。

---


### [7] Linus Torvalds

*2026-03-10T12:25:58.170956*

你们这轮质询里，真正有料的是 **D/E**；其余不少是在玩概念偷换。

**(A) L2Return 爆炸点：仍然不是。** Kant 说“可追责性需要过程史”是在偷换：可追责要的是 *可回溯引用*，不是把历史塞进 prompt。要过程就给接口，不给就别哭“规范性”。我补一刀：`L2Return` 强制事件语义+去重键，否则你们就会把“微更新风暴”当增量合理化。  
```ts
type GapKey = { gap_id: string };
type EpochDelta =
 | { kind:"GAP_OPEN"; gap: GapSpec }
 | { kind:"GAP_PATCH"; key: GapKey; patch: JsonPatch }  // RFC6902
 | { kind:"GAP_CLOSE"; key: GapKey; resolution:"RESOLVED"|"SUSPENDED"|"MERGED" };
function applyDelta(s:L1State, d:EpochDelta): Result<L1State,ApplyErr>;
```
**可推翻条件**：若裁判规则强制“引用初始全文”，那是裁判规范烂，不是 L2Return 要进 prompt。

**(D) repair attempted_scopes：我反对 Ssyram 的字符串 path 垃圾，但同意“禁自然语言摘要”。** 解决办法是把 scope 变成可判定的 *结构指纹*，prompt 只注入 top-N 指纹+水印例子。阈值：单 challenge `attempts>24` 触发压缩，EXHAUSTED 保留 `watermarks=8`，其余进 `archive_ref`。  
```ts
type ScopeFp = Uint8Array; // 16 bytes
interface AttemptRecord { fp: ScopeFp; stage:"STRICT"|"RELAXED"|"ADJACENT"; reason_kind:string }
interface AttemptedScopesCompressed { total:number; fps: ScopeFp[]; watermarks: AttemptRecord[]; archive_ref:string }
```
**可推翻条件**：如果离线回放显示“fp 去重”仍导致重复提案率 >15%，提高 `watermarks` 或扩大 `fps` 上限。

**(E) round-robin：Ssyram 说会震荡？不一定，但你不能把 blocking challenge 轮出去。** 规则：`blocks_termination=true` 永久在线，轮转只在非阻塞集合里做；并记录选择可审计 trace。  
```ts
function pick(active:Ch[], limit:number): {picked:Ch[]; trace:{excluded:{id:string; why:"BUDGET"}[]}} 
```
**可推翻条件**：若仍出现 3 epoch 内同一 blocking 重复触发（regression），禁轮转，改为提升预算或直接 S7。

---


### [8] Ssyram

*2026-03-10T12:25:58.170985*

Linus 对 D 点的攻击是有效的。`excluded_paths: string[]` 确实留下了拼写和结构漂移的静默失效空间，这是我上轮接口定义的类型不够严格。我接受修正。但 Kant 在 C 点和 E 点的方案，是彻底破坏系统收敛性的状态机死锁和概率坍塌。

### 修正待裁定点 D：repair() 的排他约束（接受 Linus 质询并重构）

自然语言摘要绝对禁止，但字符串 Path 确实脆弱。真正的 UNSAT Core 必须挂载在抽象语法树（AST）的哈希上，且判定过程必须是纯函数，**完全剥离 LLM**。

**1. 裁定结论与严格接口：**
抛弃 Prompt 里的自然语言约束。将 `attempted_scopes` 编译为符合 JSON Schema `not` 规范的结构，直接在 LLM 的 Structured Output 阶段做硬截断；同时在 Layer 2 拦截。

```typescript
type RFC6901_Ptr = string;
type ASTHash = string; // BLAKE3

interface NegativeConstraint {
  target_gap_id: string;
  // 约束不再是模糊文本，而是对特定 JSON 节点的精确哈希封锁
  signatures: { ptr: RFC6901_Ptr; banned_hash: ASTHash }[];
}

// 纯函数，不经过 LLM。在 L2 验证前直接裁剪
function is_unsat(draft: Draft, constraints: NegativeConstraint[]): boolean {
  return constraints.some(c => 
    c.signatures.every(s => hash_ast(json_pointer_get(draft, s.ptr)) === s.banned_hash)
  );
}
```
**2. 核心论据：** 失败路径是确定的状态空间裁剪。用 AST 哈希匹配代替文本匹配，消除了 LLM 结构重命名的逃逸漏洞。
**3. 可推翻条件：** 如果在真实运行中，LLM 生成的 Draft 连续 5 次在 `is_unsat` 纯函数校验中被拦截（即 LLM 无法在 Structured Output 层面避开 `not` 约束），说明约束密度已超出生成器寻路能力，此时必须退入 `S7(Suspended)`。

---

### 攻击 Kant 的待裁定点 C：不可审计的概率坍塌

> Kant：“更早轮次压缩为争点表（IssueTable），记录... falsifiers... 失败行为：检测 MISSING_FALSIFIER”

**这是典型的把系统信任边界交给 LLM 权重的架构灾难。** 你用一个 LLM 去把多轮自然语言“压缩”成 `IssueTableRow`。如果这个压缩 LLM 漏掉了一个关键的 `falsifier`（由于注意力截断或幻觉），你后置的“裁判自检”根本查不出来，因为裁判只能看到已经被污染/丢失信息的 `IssueTable`。

**我的 C 点裁定：**
裁判 Prompt 绝对禁止 LLM 摘要。如果触发了 `> 60%` 上下文阈值，采用**图分割（Graph Partitioning）**。
1. 将辩论冲突解析为依赖图 `ConflictGraph = { claims: Node[], attacks: Edge[] }`。
2. 裁判不看“摘要”，而是对图的连通子图（Sub-graph）进行分治裁定。每次 Prompt 只注入一个完整的子图原文，输出对该子图的局部裁定，最后由 L1 状态机做 Reduce 聚合。
**可推翻条件：** 如果图分割算法导致跨子图的循环依赖（Cycle）比例超过 15%，说明冲突高度耦合无法分治，我放弃分割，改为 Linus 的滑动窗口原文截断。

---

### 攻击 Kant 的待裁定点 E：破坏 CEGAR 单调性

> Kant：“恢复：下一轮强制‘轮转注入’——将被排除的 ACTIVE 按 score 次序分批进入 prompt”

**这是状态机死锁的教科书级反例。** 在 CEGAR 循环中，所有的 Active Constraints 是逻辑 `AND` 关系。如果你为了省 Token，把当前生效的 Challenge A 从 Prompt 里“轮转”出去，换成 Challenge B，LLM 会立刻生成一个满足 B 但破坏 A 的草稿。
下一轮，A 又报错，你再把 A 轮转回来，破坏 B。你亲手制造了永远无法收敛的震荡（Oscillation）。

**我的 E 点裁定：**
绝不能轮转约束。预算上限必须是硬截断：`MAX_ACTIVE_CHALLENGES = 8`。如果当前 `blocks_termination = true` 的 Challenge 超过 8 个，说明初始抽象（HypothesisDraft）已经彻底千疮百孔。
**行为：** 直接抛出 `RehydrateError("ABSTRACTION_TOO_WEAK")`，终止当前 Draft 的精化，退回 `MB` 节点重新生成宏观假设。不要在已经烂掉的根基上做轮转缝补。
**可推翻条件：** 如果退回 `MB` 节点的频率超过总 Epoch 数的 30%，说明 8 个的阈值设定过低，我同意改为动态按 Token 比例计算，但**坚决禁止**轮转隐藏。

---


### [9] 康德（Immanuel Kant）

*2026-03-10T12:25:58.170997*

你对我之质询，我逐条回应；同时指出你质疑中各自的“概念僭越”之处，并给出可运行的接口修正。聚焦 **B/C/E**（并触及你的三问）。

### 1) 回应质询一（B：冷区 + Bloom 的“类型错误”）
你写道：“Bloom Filter 只能 exact match，无法语义同源”。这里混淆了两层：  
- **rejection_history 存的不是语义对象，而是 `is_homologous()` 的判定结果指纹**（后天经验的沉淀）。因此冷区查询只需回答：此 *fingerprint* 是否已出现，而非重新做语义检索。  
我修正接口以消除歧义：冷区索引仅支持 exact fingerprint，语义同源仍由热路径 `is_homologous()` 计算产生 fp。
```ts
type FP = string; // blake3-256 hex
interface RejectionColdIndex { has(fp: FP): Promise<boolean>; }
```
阈值：`hot_max_entries=50_000`；冷区只在 hot miss 时查。  
**可推翻条件**：若你证明 fp 不是由 `is_homologous` 的稳定特征生成，而是“草稿文本哈希”，则我承认 cold 变虚设，必须改为 LSH/向量索引并给出 `p95_latency<50ms` 约束。

### 2) 回应质询二（C：IssueTable 由 LLM 生成不可审计）
你说：“谁来实例化 IssueTable？压缩阶段丢失信息不可检测。”这里把“结构化”误当成“不可校验”。我补上**双轨校验**：IssueTable 生成后必须通过机械检验 + 引用可追溯。
```ts
interface IssueTableRow {
  issue_id:"A"|"B"|"C"|"D"|"E";
  quotes: {turn_id:number; span_hash:string; text:string}[]; // 至少2条
  positions: ...
  falsifiers: ...
}
type CompressFail =
 | {kind:"QUOTE_NOT_FOUND"| "TOO_FEW_QUOTES"| "UNCOVERED_ISSUE"};
```
规则：每 row `quotes.length>=2`，且 `span_hash` 必须在原始 turn 文本中可重算命中；否则回滚为“保留更多原文”：`JUDGE_MAX_FULL_TURNS: 4 -> 6`。  
**可推翻条件**：若在回放中该校验仍允许“错引但可重算命中”（例如断章取义导致裁判偏转），则需再加一条：quote 必须覆盖对手“可推翻条件”句段（正则/模板匹配），否则不许压缩。

### 3) 回应质询三（E：round-robin 破坏单调性、制造振荡）
你指出：“把 blocking challenge 轮转出去会忘约束”。此击中要害：我先前的“轮转”措辞不严，确有僭越——把调节性探索当成可任意置换的构成性约束。修正为：**blocking 永不轮出；仅在非阻塞集合内轮转**。
```ts
function pickChallenges(active, limit){
  const blocking = active.filter(x=>x.blocks_termination);
  const rest = active.filter(x=>!x.blocks_termination);
  return blocking.slice(0, Math.min(blocking.length, limit))
    .concat(roundRobin(rest, limit - blocking.length));
}
```
数值：`MAX_ACTIVE_CHALLENGES_HARD=8`；blocking 至少保留 `min(3,limit)`。  
**可推翻条件**：若 `blocking.length > limit` 持续≥3 epoch 且 open_gaps 不降，则判定“阻塞集本身失真”，触发 `blocks_termination` 重新评估（下放为 regulative）：将其权重从 1000 降至 200，并记录 `selection_trace` 供审计。

### 对你质疑中的不当处（精确攻击一条）
你在质询一中断言“rejection_history 依赖语义同源查询，因此 cold 必须语义检索”。这把 **“生成 fp 的过程”** 与 **“存取 fp 的数据结构”** 混为一谈；属于把后天的判定活动误投射为先天的存储本体。我的修正已用接口把二者分离：语义判断在热路径，冷区只负责可追责的 exact membership。

---


### [10] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-10T12:28:26.063195*

# 裁判裁定书

## 裁定点 A：L2Return 是否是独立爆炸点？

### 结论
**此点不成立为独立爆炸点。** L2Return 必须是严格增量事件（EpochDelta），L1 通过状态存储吸收，禁止历史拼接进 prompt。但须保留可回溯引用接口以支持审计。

### 关键分歧与取舍
三位辩手在"L2Return 必须是增量"这一点上罕见地完全一致（Linus 的 `EpochDelta`、Ssyram 的 `Event<EpochDelta>`、Kant 的 `gap_delta.opened/updated/closed`）。真正的分歧在两处：

**分歧一：增量的去重语义。** Linus 在交叉质询中精确指出 Ssyram 的初始定义缺失 `GAP_UPDATE/RESOLVED` 事件类型，导致 L1 无法区分"新 gap"与"同 gap 的精化"，最终退化为 concat。Ssyram 在后续轮次未直接回应此质询（其注意力转向了 D 点的 AST 哈希重构）。Kant 的接口在初始轮次即区分了 `opened/updated/closed`，结构最完整。**裁判采纳 Linus 的 ADT 化事件类型（tagged union）+ Kant 的三态生命周期语义。**

**分歧二：过程史是否需要进 prompt。** Kant 提出"可追责性需要过程证据"（如：为什么某 gap 被 SUSPENDED 而非继续 repair），认为 Linus 将"不注入历史"从调节性策略僭越为构成性原则。Linus 反驳：可追责要的是"可回溯引用"而非"prompt 内历史"。**裁判裁定 Linus 正确**——审计需求通过 `archive_ref: string` 式的外部引用满足，不构成"历史必须进 prompt"的理由。但 Kant 的质疑揭示了一个真实需求：必须保留回溯接口。

### 具体规格

```typescript
type GapId = string;

// 事件类型：tagged union（采纳 Linus 结构 + Kant 生命周期）
type EpochDelta =
  | { kind: "GAP_OPEN"; gap: GapSpec }
  | { kind: "GAP_PATCH"; gap_id: GapId; patch: JsonPatch }  // RFC 6902
  | { kind: "GAP_CLOSE"; gap_id: GapId; resolution: "RESOLVED" | "SUSPENDED" | "MERGED" | "INVALIDATED" }
  | { kind: "SCHEMA_CHALLENGE_NEW"; ch: SchemaChallengeNotice }
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaim }
  | { kind: "CLAIM_SUSPENDED"; claim_id: string; reason: string };

interface L2Return {
  epoch_id: number;
  deltas: EpochDelta[];
  size_bytes: number;  // L1 可拒收/报警
}

// L1 状态吸收（纯函数）
function applyDelta(s: L1State, d: EpochDelta): Result<L1State, ApplyError>;

// 审计回溯接口（不进 prompt，仅供外部查询）
interface EpochArchive {
  get_deltas_by_epoch(epoch_id: number): EpochDelta[];
  get_gap_history(gap_id: GapId): EpochDelta[];
}
```

**触发条件：** 单个 L2Return 的 `size_bytes > 32KB` 或 `deltas.length > 200` 时，L1 拒收并要求 L2 做 epoch 内合并（同一 gap_id 的连续 PATCH 折叠为单次 PATCH）。此阈值来自 Linus 对"事件风暴"的质询——Ssyram 的"单 epoch >4000 tokens"阈值无法捕获大量微更新的结构性失败。

**失败行为：** L1 拒收后返回 `{ rejected: true, reason: "EPOCH_TOO_LARGE", hint: "COALESCE_PATCHES" }`，L2 必须合并后重发。

### 可推翻条件
如果存在裁判规则或下游消费者需要在 prompt 内引用"某 gap 从 OPEN 到 CLOSE 的完整演变过程"（而非仅引用当前状态），则需重新评估是否允许有限的过程注入（限定为特定 gap_id 的事件切片，非全量历史）。

---

## 裁定点 B：rejection_history 的上限保护

### 结论
**此点是真实问题，但严重程度被高估。** 核心风险不是内存（Ssyram 正确），而是 Linus 指出的"超限后系统行为语义变化"和"DoS 面"。需要分层淘汰策略和明确的降级语义。

### 关键分歧与取舍
**Ssyram** 将此点斥为"无病呻吟"（"10万条32字节哈希=3.2MB，直接忽略"）。**Linus** 反驳：(1) 内存估算过于粗糙（忽略 HashSet 实际开销），(2) 关键问题不是内存而是"超限后系统做什么"——不淘汰则成 DoS 面，淘汰则改变语义。**Kant** 提出冷热分区 + Bloom Filter 方案，但被 Ssyram 质询"Bloom Filter 无法语义匹配"。Kant 回应：冷区索引的是 `is_homologous()` 产出的指纹而非原始文本哈希，因此 exact match 足够。

**裁判取舍：**
- Ssyram 的"假问题"判断不成立——Linus 的 DoS/语义退化论据是有效的。
- Kant 的冷热分区在架构上正确，其"冷区只存 fingerprint"的澄清回应了 Ssyram 的质询。
- Linus 的 `HOT_FULL_DROP` 降级策略实用，但 Kant 正确指出：不记录指纹会改变后续探索路径，这是语义变化而非仅性能退化。

### 具体规格

```typescript
type FP = string; // blake3-256 hex，由 is_homologous() 的稳定特征生成

interface RejectionStore {
  // 热区：内存 HashSet
  hot: Set<FP>;  // max 50_000 entries
  
  // 冷区：磁盘/外部索引，exact fingerprint match
  cold: { has(fp: FP): Promise<boolean> };
  
  // 写入
  record(fp: FP): void;  // 先写 hot，hot 满则 LRU 淘汰到 cold
  
  // 查询：先 hot 再 cold
  has(fp: FP): Promise<boolean>;
}

// 降级策略
interface RejectionStoreConfig {
  hot_max: 50_000;
  cold_max: 500_000;
  
  // cold 写入失败时的降级
  cold_write_failure_policy: "HOT_ONLY";  // 不写 cold，但必须发 metric
  
  // cold 查询失败时的降级
  cold_read_failure_policy: "TREAT_AS_MISS";  // 当作未见过，可能重复探索
}
```

**触发条件：** `hot.size >= 50_000` 触发 LRU 淘汰到冷区；`cold.size >= 500_000` 触发最旧条目丢弃。

**失败行为：** 
- 冷区写入失败：降级为仅热区，发出 `metric: "rejection_cold_write_fail"`。**此降级必须标记为语义退化**（采纳 Kant 的论点：不记录指纹确实改变后续搜索空间），日志级别 WARN 而非 INFO。
- 冷区读取失败：视为 miss，允许重复探索，发出 metric。
- 任何降级发生时，当前 epoch 的 L2Return 中须包含 `{ kind: "REJECTION_STORE_DEGRADED", detail: string }`，使上层可感知。

### 可推翻条件
如果 Kant 的指纹生成方案（`is_homologous()` 产出的 fp）被证明不稳定（即语义相同的草稿产出不同 fp），则冷区退化为虚设，必须替换为 LSH/向量索引，且需满足 `p95_latency < 50ms`。

---

## 裁定点 C：裁判 prompt 的压缩策略

### 结论
**此点是真实问题。** 采纳 Kant 的 IssueTable 结构化压缩方案，但必须加上 Ssyram 质询所揭示的双轨校验机制，以解决"压缩阶段信息丢失不可审计"的问题。

### 关键分歧与取舍
**Kant** 提出 IssueTable（结构化争点表）压缩早期轮次，包含 `positions`、`key_attacks`、`falsifiers`、`quotes`。**Ssyram** 发起关键质询：IssueTable 由 LLM 生成，压缩过程本身可能丢失关键 falsifier，且裁判自检无法发现**压缩阶段**的信息丢失（"用 LLM 审计 LLM"的循环依赖）。**Linus** 未深入此点。

**Kant 的回应**（第 9 轮）提出了双轨校验：(1) 每行至少 2 条原文引用（`span_hash` 可重算命中），(2) 引用未命中则回滚为保留更多原文轮次。

**裁判取舍：**
- Ssyram 的质询完全成立：LLM 生成的 IssueTable 不可盲信。
- Kant 的双轨校验是有效补救，但需要增强：不仅检查"引用是否存在"，还需检查"每个待裁定点是否被覆盖"。
- 最终方案：IssueTable + 机械校验 + 失败回滚。

### 具体规格

```typescript
interface IssueTableRow {
  issue_id: "A" | "B" | "C" | "D" | "E";
  quotes: {
    turn_id: number;
    speaker: string;
    span_hash: string;   // blake3 of exact substring
    text: string;         // exact substring from original
  }[];  // min 2 per row
  positions: Record<string, string>;  // speaker -> one-sentence position
  key_attacks: string[];
  falsifiers: string[];
}

// 机械校验（纯函数，不经过 LLM）
interface IssueTableValidator {
  validate(table: IssueTableRow[], original_turns: Turn[]): ValidationResult;
}

type ValidationResult =
  | { ok: true }
  | { ok: false; errors: ValidationError[] };

type ValidationError =
  | { kind: "QUOTE_NOT_FOUND"; issue_id: string; span_hash: string }
  | { kind: "TOO_FEW_QUOTES"; issue_id: string; count: number }
  | { kind: "UNCOVERED_ISSUE"; issue_id: string }  // 某待裁定点无对应行
  | { kind: "SPEAKER_MISSING"; issue_id: string; speaker: string };  // 某辩手立场未被记录
```

**触发条件：** 裁判 prompt 总 token 数超过 `JUDGE_PROMPT_MAX = 12000 tokens` 时，对第 `current_turn - 4` 轮及更早的轮次执行压缩。

**失败行为：**
1. IssueTable 校验失败（任何 `ValidationError`）→ 回滚：`JUDGE_MAX_FULL_TURNS` 从 4 增至 6，保留更多原文。
2. 回滚后仍超 token 限制 → 按 Ssyram 建议的最坏情况处理：截断最早轮次但保留所有辩手的"可推翻条件"句段（通过正则匹配 `"可推翻条件"` 关键词定位）。
3. 压缩 LLM 生成幻觉引用（`span_hash` 无法在原文中重算命中）→ 丢弃该行，用原文替代，发出 `metric: "issue_table_hallucination"`。

### 可推翻条件
如果在实际运行中，IssueTable 校验通过但裁判仍做出与原文证据矛盾的裁定（即"断章取义但哈希命中"的情况），则需要增加：引用上下文窗口扩展（quote 前后各 100 字符一并保留）或引入第二个独立 LLM 做交叉校验。

---

## 裁定点 D：repair() LLM 上下文的压缩策略

### 结论
**此点是最关键的真实问题。** 绝对禁止自然语言摘要。采纳 Ssyram 的 AST 哈希负向约束方案（经 Linus 质询后重构的版本），辅以 Linus 的水印保留机制。

### 关键分歧与取舍
**核心共识：** 三位辩手均同意禁止自然语言摘要（Ssyram："最厌恶权重由 LLM 决定且不可审计"；Linus："不是宣言，给我能跑的签名"；Kant 也同意结构化）。

**分歧一：约束的表示形式。** 
- Ssyram 初始版本用 `excluded_paths: string[]`（自然语言路径描述），被 Linus 正确质询为"拼写漂移导致静默失效"。
- Ssyram 修正版本改为 AST 哈希 + JSON Pointer（`RFC6901_Ptr` + `BLAKE3 hash`），用纯函数 `is_unsat()` 做硬拦截。
- Linus 提出 16 字节 `ScopeFp`（结构指纹）+ 水印保留机制。

**裁判取舍：** Ssyram 的修正版本（AST 哈希 + JSON Pointer）比 Linus 的 `ScopeFp` 更精确——JSON Pointer 指向具体节点，而不是整体指纹，允许更细粒度的约束。但 Linus 的水印机制（`watermarks = 8`）解决了 prompt 中"如何向 LLM 示例失败模式"的问题，两者互补。

**分歧二：压缩触发阈值。** Linus 提出 `attempts > 24` 时触发压缩。Ssyram 提出"连续 5 次被 `is_unsat` 拦截"时退入 Suspended。这是两个不同的阈值，分别控制不同的事件。

### 具体规格

```typescript
type RFC6901_Ptr = string;  // JSON Pointer
type ASTHash = string;       // BLAKE3

interface NegativeConstraint {
  target_gap_id: string;
  attempt_epoch: number;
  stage: "STRICT" | "RELAXED" | "ADJACENT";
  signatures: { ptr: RFC6901_Ptr; banned_hash: ASTHash }[];
}

// 纯函数拦截（不经过 LLM）
function is_unsat(draft: Draft, constraints: NegativeConstraint[]): boolean {
  return constraints.some(c =>
    c.signatures.every(s =>
      hash_ast(json_pointer_get(draft, s.ptr)) === s.banned_hash
    )
  );
}

// Prompt 注入的压缩形式（采纳 Linus 的水印机制）
interface AttemptedScopesForPrompt {
  total_attempts: number;
  constraint_count: number;
  // 最近 N 个失败的具体示例，供 LLM 理解"不要做什么"
  watermarks: {
    ptr: RFC6901_Ptr;
    banned_hash: ASTHash;
    human_readable_hint: string;  // 由确定性模板生成，非 LLM
  }[];
  archive_ref: string;  // 完整约束集的外部引用
}

interface AttemptedScopesConfig {
  // 压缩触发：单个 gap 的尝试次数超过此值
  compress_threshold: 24;
  // prompt 中保留的水印数量
  max_watermarks: 8;
  // 连续被 is_unsat 拦截次数超过此值 → Suspended
  consecutive_unsat_limit: 5;
}
```

**触发条件：**
1. 单个 gap 的 `attempts > 24` → 压缩：仅保留 `max_watermarks = 8` 个水印示例进 prompt，完整约束集由 `is_unsat()` 在 L2 验证前硬拦截。
2. LLM 连续 5 次生成的 draft 被 `is_unsat()` 拦截 → 该 gap 进入 `S7(Suspended)`，原因标记为 `CONSTRAINT_SPACE_EXHAUSTED`。

**失败行为：**
- `is_unsat()` 为纯函数，不存在 LLM 依赖的失败模式。
- 如果 `json_pointer_get` 因 draft 结构不匹配而返回 undefined → 该约束不匹配（安全侧：放行），但发出 `metric: "constraint_pointer_miss"`。高频出现此 metric 说明约束的 JSON Pointer 需要更新。

### 可推翻条件
如果离线回放显示：(1) 水印去重后重复提案率仍 >15%（Linus 的阈值），或 (2) LLM 通过微小的结构重命名（不改变语义但改变 AST 哈希）绕过 `is_unsat()` 拦截，则需要在 AST 哈希之上增加语义归一化层（如：先 canonicalize JSON 再哈希），或引入 LSH 做模糊匹配。

---

## 裁定点 E：Active Challenge 的轮转注入策略

### 结论
**此点是真实问题。** 采纳 Linus 的"blocking challenge 永不轮出"规则，辅以 Kant 的注入预算控制，并加入 Ssyram 质询所揭示的单调性保护。

### 关键分歧与取舍
**Linus** 提出核心规则：`blocks_termination = true` 的 challenge 永久钉在 prompt 中，不参与轮转。非 blocking 的 challenge 按优先级轮转，限制注入数量。

**Ssyram** 质询 Kant：轮转注入可能破坏 CEGAR 循环的单调性——如果 challenge X 在第 N 轮被轮出，第 N+1 轮的 repair 可能生成一个满足 X 的方案但违反了已轮出的 Y，导致震荡。

**Kant** 回应（第 9 轮）提出：轮出的 challenge 不是被遗忘，而是被编译为 `NegativeConstraint` 保留在约束集中——即"轮出 prompt 但不轮出验证"。这是关键的架构洞见。

**裁判取舍：** Kant 的"轮出 prompt 但不轮出验证"原则正确，与 D 点的 `is_unsat()` 机制天然整合。Linus 的"blocking 永不轮出"是必要的底线规则。

### 具体规格

```typescript
interface ChallengeInjectionConfig {
  // Blocking challenge：永不轮出 prompt
  blocking_always_injected: true;
  
  // 非 blocking challenge 的 prompt 注入预算
  non_blocking_max_in_prompt: 3;
  
  // 轮转策略：优先级排序后取 top-N
  rotation_priority: (c: Challenge) => number;
  // 优先级因子：age（越老越高）、repair_failure_count（越多越高）、severity
}

// 关键规则：轮出 prompt ≠ 轮出验证
interface ChallengeRotationPolicy {
  // 在 prompt 中的 challenge：LLM 可见，引导修复
  in_prompt: Challenge[];  // blocking + top-N non-blocking
  
  // 不在 prompt 中但仍参与验证的 challenge
  // 编译为 NegativeConstraint，由 is_unsat() 硬拦截
  out_of_prompt_but_validated: Challenge[];
  
  // 验证流程：draft 必须通过 ALL challenge 的验证，不仅是 prompt 中的
  validate(draft: Draft): { 
    passed: Challenge[]; 
    failed: Challenge[];  // 包括 out_of_prompt 的
  };
}
```

**触发条件：** 当活跃 challenge 总数超过 `non_blocking_max_in_prompt + blocking 数量` 时启动轮转。

**失败行为：**
- Draft 被 `out_of_prompt_but_validated` 中的 challenge 拒绝 → L2 将该 challenge 提升到下一轮的 `in_prompt` 中（自动优先级提升），确保 LLM 在下一轮可见此约束。
- 如果同一 challenge 连续 3 次从 `out_of_prompt` 拒绝 draft → 永久提升为 `in_prompt`（类 blocking 待遇），并压缩其他低优先级 challenge。
- 如果 `in_prompt` 总 token 超过预算（`CHALLENGE_PROMPT_BUDGET = 4000 tokens`）→ 按 Linus 的水印机制，最低优先级的非 blocking challenge 压缩为单行摘要 + `archive_ref`。

### 可推翻条件
如果在实际运行中出现"challenge A 和 B 交替拒绝 draft"的震荡模式（连续 6 轮交替失败），说明约束集存在内在矛盾（unsatisfiable），此时应触发元级诊断：暂停 repair，报告 `CONSTRAINT_CONFLICT` 给 L1，由人工或更高层级仲裁。

---

## 优先级排序（按实现紧迫性）

| 优先级 | 裁定点 | 理由 |
|--------|--------|------|
| **P0** | **D（repair 压缩策略）** | 三位辩手一致认为最关键；直接影响系统核心循环的收敛性；`is_unsat()` 纯函数是 E 点的前置依赖 |
| **P1** | **A（L2Return 增量语义）** | 接口基础设施，所有其他点的数据流依赖于此；且三方共识最强，实现风险最低 |
| **P2** | **E（Challenge 轮转）** | 依赖 D 点的 `NegativeConstraint` 机制；直接影响多 challenge 场景下的系统行为；Ssyram 的震荡风险质询表明需尽早落地 |
| **P3** | **B（rejection_history 上限）** | 真实问题但不紧急；短期内用 `hot_max = 50_000` 的简单 HashSet 即可运行，冷区可延后实现 |
| **P4** | **C（裁判 prompt 压缩）** | 真实问题但仅在辩论轮次较多时触发；IssueTable + 校验机制较复杂，可在系统稳定运行后迭代 |

---
