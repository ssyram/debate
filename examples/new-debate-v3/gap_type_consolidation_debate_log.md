# v3 认知引擎类型冲突裁定：GAP-1/2/4/5/7 权威定义之争 辩论日志

> 2026-03-10T15:28:51.515718

---


### [1] Linus Torvalds

*2026-03-10T15:23:59.122007*

你们现在的问题不是“版本冲突”，是**你们允许同一个概念在系统里以两三种形态到处漂**，还指望调用方“自己小心点”。这在任何可维护系统里都是自找死路。

下面我对 GAP-1/2/4/5/7 给出**第一轮裁定立场**：每个都包含(1)裁定结论+接口/类型形状，(2)核心论据，(3)可推翻条件。

另外我会精确攻击你们文档里的一个具体烂点：GAP-2 的“统一方案”把 `kind: RepairGapKind | TerminationGapKind` 塞回 `GapSpec`，这是典型的“看起来统一，实际上把类型信息炸掉”的设计。

---

## GAP-1：`L2Return`：裁定 **版本 B（deltas）为唯一权威**，旧字段一律禁用

### 1) 裁定结论（类型/接口）
**权威定义：**
```ts
type EpochDelta =
  | { kind: "GAP_OPEN"; gap: GapSpec }
  | { kind: "GAP_PATCH"; gap_id: GapId; patch: JsonPatch }
  | { kind: "GAP_CLOSE"; gap_id: GapId; resolution: "RESOLVED" | "SUSPENDED" | "MERGED" | "INVALIDATED" }
  | { kind: "SCHEMA_CHALLENGE_NEW"; ch: SchemaChallengeNotice }
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaimFull }
  | { kind: "CLAIM_SUSPENDED"; claim_id: ClaimId; reason: string };

interface L2Return {
  epoch_id: EpochId;
  deltas: EpochDelta[];
  size_bytes: number;
}
```

**`repair_strategy` 不得再读取 `L2Return.evidence_summary`。**  
`repair()` 只能吃 **L1State**，证据摘要由**专用提取器**从 L1State 计算出来：

```ts
type EvidenceSummary = {
  gap_id: GapId;
  axis_id?: AxisId;
  text: string;              // 给 LLM 的摘要
  atoms_used: number;
  claim_ids: ClaimId[];
  truncated: boolean;
};

type EvidenceExtractError =
  | { kind: "GAP_NOT_FOUND"; gap_id: GapId }
  | { kind: "NO_RELEVANT_CLAIMS"; gap_id: GapId; axis_id?: AxisId }
  | { kind: "BUDGET_EXCEEDED"; budget_bytes: number };

function build_gap_evidence_summary(
  state: L1State,
  gap_id: GapId,
  opts: { axis_id?: AxisId; budget_bytes: number; include_active_window: boolean }
): Result<EvidenceSummary, EvidenceExtractError>;
```

`repair()` 路径固定为：
```ts
function repair(input: RepairInput): RepairOutput {
  const ev = build_gap_evidence_summary(input.l1_state, input.gap.gap_id, {
    axis_id: input.gap.axis_id,
    budget_bytes: 4096,
    include_active_window: true,
  });
  // ev.err 也要进 prompt：告诉 LLM “没有相关证据/预算不足”，别假装看过
  ...
}
```

### 2) 核心论据
- `evidence_summary: string` 放在 `L2Return` 里是**层间耦合**：L2 事件流应该是“发生了什么”，不是“给 repair 准备的 prompt 片段”。你把 UI 文本塞进协议层就是设计污染。
- 增量 `deltas` 是唯一可扩展机制；旧版 `L2Return_OLD` 会逼着你每加一个事件就加字段，最后变成上帝对象。
- “repair 需要 evidence_summary”不是接口理由，是**你缺一个函数**。

### 3) 可推翻条件（实验）
如果你能做一个基准实验，证明：
- `build_gap_evidence_summary()` 这种从 L1State 计算摘要的方式导致**不可接受的回归**（比如：平均每 epoch 增加 >30% wall time 或明显降低修复成功率），
- 并且你能给出一个**不破坏 deltas 协议**、仍然能让 repair 拿到摘要的替代方案（比如 delta 中加专门的 `EVIDENCE_SUMMARY` 事件，且有严格预算与溯源），  
那我接受调整。但不是回滚到旧结构。

---

## GAP-2：`GapSpec.kind`：裁定 **必须 tagged union**，禁止“裸联合”混装

你们的“统一方案”是：
> `kind: RepairGapKind | TerminationGapKind`

这玩意儿在运行时就是个 string。你根本没法可靠区分子类型，最后就会写 `if (kind in setA)` 这种垃圾，然后漏一个枚举值就静默坏掉。

### 1) 裁定结论（类型/接口）
**`GapSpec` 不能同时承载两套语义。**拆成**明确 tag**：

```ts
type GapOrigin = "L2_REPAIR" | "PA_TERMINATION";

type RepairGapKind =
  | "MISSING_DISCRIMINATOR"
  | "MISSING_OBSERVABLE"
  | "PREMISE_UNDERSPECIFIED"
  | "UNCLASSIFIED";

type TerminationGapKind =
  | "UNCOVERED_HIGH_WEIGHT_AXIS"
  | "UNRESOLVED_DEFEATER"
  | "WEIGHT_UNDERSPECIFIED"
  | "EVIDENCE_CONFLICT"
  | "LOW_COVERAGE_FRONTIER"
  | "STAKEHOLDER_DISAGREEMENT";

type GapSpec =
  | {
      gap_id: GapId;
      origin: "L2_REPAIR";
      kind: RepairGapKind;
      blocks_termination: boolean;
      axis_id?: AxisId;
      related_claim_ids?: ClaimId[];
      description: string;
    }
  | {
      gap_id: GapId;
      origin: "PA_TERMINATION";
      kind: TerminationGapKind;
      blocks_termination: true;          // 终止缺口就该阻塞终止，别装可选
      axis_id?: AxisId;
      related_claim_ids?: ClaimId[];
      description: string;
    };
```

**创建责任：**
- Layer 2 只能创建 `origin:"L2_REPAIR"` 的 Gap（修复缺口）。
- PA 节点只能创建 `origin:"PA_TERMINATION"` 的 Gap（终止缺口）。
- L1State 可以同时持有两类 gap，但调用方**按 origin 分流**。

运行时分流接口（别在业务里散落 `if`）：
```ts
function is_repair_gap(g: GapSpec): g is Extract<GapSpec, { origin: "L2_REPAIR" }>;
function is_termination_gap(g: GapSpec): g is Extract<GapSpec, { origin: "PA_TERMINATION" }>;
```

`repair()` 签名约束：只吃 repair gap
```ts
type RepairGap = Extract<GapSpec, { origin: "L2_REPAIR" }>;

interface RepairInput {
  gap: RepairGap;
  ...
}
```

PA 的分类函数也别叫 classify 了，PA 产生 gap，而不是“猜测 gap 属于啥”：
```ts
function derive_termination_gaps(state: L1State, cfg: TerminationConfig): GapSpec[]; 
// 返回的必须全是 origin:"PA_TERMINATION"
```

### 2) 核心论据
- **一个字段承载两种正交语义**（“怎么修”和“为什么不能停”）就是把 bug 写进接口。
- 你们自己已经写出静默失败场景：`generate_repair_draft()` 落入 UNCLASSIFIED；PA 误判无阻塞 gap。tagged union 是最低成本的编译期保险。

### 3) 可推翻条件（实验）
如果你能在 TypeScript（或你们目标语言）里证明不使用 tag 也能获得同等强度的编译期约束（例如通过 branded string + exhaustive mapping + 生成器保证），并且有自动化测试能捕获“枚举扩展导致静默分支退化”，我可以接受不加 `origin`。否则别扯。

---

## GAP-4：`HypothesisDraft`：裁定 **统一版本 B 为唯一可入池类型**，旧版只能在边界处转换并断言

### 1) 裁定结论（类型/接口）
**权威类型：**
```ts
interface HypothesisDraft {
  draft_id: DraftId;
  problem_id: ProblemId;
  claim_sketch: string;
  scope_ref: [string, ...string[]];  // 非空数组，用 tuple 强制
  verifier_hint: string[];
  open_term_risk: string[];
  tension_source: TensionSource;
  provenance: Provenance;
}
```

**`problem_id` 注入来源：只允许来自 `ctx.frame.problem_id`（也就是 L1State 的 frame）。**
绝对禁止从 `gap_id` 派生，这种“从无关 ID 推导语义”的做法就是自欺欺人。

工厂函数（你们已有，但我加上断言）：
```ts
type NormalizeRepairError =
  | { kind: "MISSING_PROBLEM_ID" }
  | { kind: "EMPTY_SCOPE_REF" }
  | { kind: "INVALID_VERIFIER_HINT" };

function normalize_repair(
  raw: RawRepairDraft,
  ctx: { frame: QuestionFrame; gap_id: GapId; challenge_id: string; current_stage: RepairStage }
): Result<HypothesisDraft, NormalizeRepairError>;
```

迁移 `verifier_hint: string`：在 normalize 里一次性收口：
- string → `[string]`
- 其他类型/空字符串 → error

并且草稿池入库函数必须只接受新类型：
```ts
function draft_pool_add(state: L1State, draft: HypothesisDraft): L1State;
```

### 2) 核心论据
- 你们自己给了具体炸点：`is_homologous()` 用 `problem_id` 快速排除。旧版没有 `problem_id` 就会把去重逻辑变成随机数。
- `scope_ref` 允许空数组也是垃圾：空 scope 的 claim 没边界，验证层怎么测？

### 3) 可推翻条件（实验）
如果你能证明：
- 系统里确实存在合法的“跨 problem 同源草稿”需要去重，导致 `problem_id` 必填反而错杀；  
并且给出一个替代字段（比如 stable semantic hash）+ 明确签名 + 回归测试，  
那可以讨论放宽。但在那之前，`problem_id` 必填。

---

## GAP-5：`alpha`：裁定 **禁止裸 `alpha`**，配置键必须升级，构造时断言

### 1) 裁定结论（类型/接口）
命名与配置键强制分离：

```ts
interface EpsilonState {
  ...
  ema_alpha: number;   // (0,1)
}

interface TerminationConfig {
  ...
  score_alpha: number; // >0
}

type ConfigError =
  | { kind: "UNKNOWN_KEY"; key: string }
  | { kind: "INVALID_VALUE"; key: string; reason: string };

function parse_termination_config(obj: unknown): Result<TerminationConfig, ConfigError>;
function parse_epsilon_state(obj: unknown): Result<EpsilonState, ConfigError>;
```

解析规则：出现 `alpha` 直接报错（不是 warning）：
```ts
if ("alpha" in obj) return Err({ kind:"UNKNOWN_KEY", key:"alpha" });
```

断言（构造/解析时）：
- `0 < ema_alpha && ema_alpha < 1`
- `score_alpha > 0`

### 2) 核心论据
- 你们给的崩溃场景是“无限循环还不崩”。所以必须在**入口**就 fail-fast。
- 配置兼容性靠“猜测用户意图”是灾难。遇到 `alpha` 就拒绝加载，逼用户改。

### 3) 可推翻条件（实验）
如果你们有真实遗留配置必须兼容，可以加一个**显式迁移器**：
```ts
function migrate_config_v2_to_v3(obj: unknown): Result<unknown, ConfigError>;
```
但迁移器必须是单独步骤，不允许在运行时静默兼容。

---

## GAP-7：`VerifiedClaim`：裁定 **方案 X（接口屏蔽）+ 强制最小证据接口**，反对“L1State 里原地替换形态”散播复杂度

方案 Y 的“原地替换”为压缩形态，本质是在 L1State 里引入“同一个 claim 在不同时间突然少字段”的时间炸弹。你当然可以写对，但维护成本会持续恶化。

### 1) 裁定结论（类型/接口）
保留两形态，但**禁止业务直接访问字段**。只允许通过一组 accessor。

```ts
type VerifiedClaim = VerifiedClaimFull | VerifiedClaimCompressed;

function get_axis_scores(c: VerifiedClaim): Partial<Record<AxisId, number>>;

type EvidenceAtomsResult =
  | { kind: "OK"; atoms: EvidenceAtom[]; truncated: boolean; source: "FULL_CHAIN" | "ACTIVE_WINDOW" }
  | { kind: "UNAVAILABLE"; reason: "COMPRESSED_NO_WINDOW" | "BUDGET_EXCEEDED" };

function get_evidence_atoms(
  c: VerifiedClaim,
  opts: { axis_id?: AxisId; budget_atoms: number }
): EvidenceAtomsResult;
```

L1State 里仍然用联合，但提供**统一索引函数**：
```ts
function find_verified_claim(state: L1State, id: ClaimId): VerifiedClaim | null;
```

压缩触发时机：**只能在 `apply_l2_return()` 吸收完 deltas 后、epoch 收尾阶段**做（单点）。接口：
```ts
type CompressionDecision = { claim_id: ClaimId; reason: "STATE_SIZE" | "EPOCH_LIMIT" };

function decide_compressions(state: L1State, max_state_bytes: number): CompressionDecision[];

function apply_compressions(
  state: L1State,
  decisions: CompressionDecision[],
  cfg: CompressionConfig
): Result<L1State, CompressError>;
```

`repair()` 取证据上下文的确切路径：
- `build_gap_evidence_summary()` 内部按 gap.related_claim_ids / axis_id 找 claim
- 对每个 claim 调 `get_evidence_atoms(...)`
- 如果返回 UNAVAILABLE，把这个事实写进 summary（不要装作有证据）

### 2) 核心论据
- 方案 Y 让字段可用性变成“取决于时间与是否压缩”，调用方到处写 `if ('evidence_chain' in claim)`，这就是把复杂度复制到整个代码库。
- 方案 X 至少把复杂度集中在 accessor；你只需要保证 accessor 有预算/失败路径。

### 3) 可推翻条件（实验）
如果你能证明 accessor 模式在性能上不可接受（比如 evidence 提取平均要多做 2x 拷贝/过滤，导致整体吞吐下降明显），并且能用方案 Y 同时满足：
- **所有访问点都通过统一 API**（也就是说你仍然没逃掉 accessor，只是换了存储形态），
- 有测试覆盖“压缩前后 repair/PA 行为一致”，  
那再谈统一压缩形态。否则别折腾。

---

## 精确攻击（引用你们文本并指出缺陷）

我就点名攻击 GAP-2 里的“统一方案”：

> `interface GapSpec { kind: RepairGapKind | TerminationGapKind; ... }`

这不是“统一”，这是**把类型系统当摆设**。`kind` 运行时是 string，你没有 tag、没有来源字段、没有强制构造路径。结果就是你们自己写的两段灾难代码会继续存在：

- `generate_repair_draft()` 期待 RepairGapKind，拿到 TerminationGapKind 就退化到 `UNCLASSIFIED`（静默错）
- `classify_gap_for_termination()` 拿 RepairGapKind 去比 TerminationGapKind，永远不命中（静默错）

你们连“错误必须可检测”这种底线都没做到，还谈什么框架。

---

如果你要进入第二轮，就给我两样东西：
1) 你们反对我哪个裁定，贴出你们“具体要怎么实现”的函数签名和失败分支（别写自然语言）。
2) 至少一个可执行 trace：输入一个具体 `L2Return.deltas` + 初始 `L1State`，展示 `applyDelta → build_gap_evidence_summary → repair()` 最终输出里包含什么。没有 trace 的争论都是浪费时间。

---


### [2] Ssyram

*2026-03-10T15:23:59.122068*

这是 Layer 1 状态机与 Layer 2 外部环境之间的契约定义问题。类型系统不是用来写注释的，是用来拦截非法规约的。

以下是我的裁定。

---

### GAP-1：`L2Return` 两版本冲突

**裁定结论**：采纳版本 B（增量事件流）。废弃版本 A。`repair()` 必须从经 `applyDelta` 吸收后的 `L1State` 中通过纯投影函数提取上下文，而不是指望 L2 替它总结好。

**接口定义**：
```typescript
// 纯投影函数，作为 repair() 的前置调用
function extract_gap_context(l1_state: L1State, gap_id: GapId): string {
  const gap = l1_state.open_gaps.get(gap_id);
  if (!gap) return "";
  // 从 L1State 已有的 verified_claims 和 delta 历史中重组上下文
  return build_evidence_summary_from_state(l1_state, gap.related_claim_ids);
}

// repair() 签名
function repair(input: RepairInput): RepairOutput {
  const evidence_summary = extract_gap_context(input.l1_state, input.gap.gap_id);
  // ... 构建 prompt
}
```

**核心论据**：L2 是一个执行实证检验的外部环境，它产出的是观测事件（Deltas），不是为 L1 节点定制的视图。`evidence_summary` 是 L1 中 RB（Repair）节点为了构建 LLM 提示词而需要的特定视图。视图的构建责任在消费方（RB 节点读取 L1State），不在生产方（L2）。

**可推翻条件**：如果 `extract_gap_context` 每次从全量 `L1State` 重建 summary 的计算开销超过 100ms 导致 L1 调度阻塞，则允许在 `L1State.open_gaps` 的节点上引入 `cached_summary: string` 字段，在 `applyDelta` 时增量更新。

---

### GAP-2：`GapSpec.kind` 枚举不兼容

**裁定结论**：拒绝扁平混用。引入 Tagged Union（代数数据类型）获得编译期穷尽检查保证。

**接口定义**：
```typescript
// 强制命名空间隔离
type GapKind = 
  | { type: "REPAIR"; detail: RepairGapKind }
  | { type: "TERMINATION"; detail: TerminationGapKind };

interface GapSpec {
  gap_id: GapId;
  kind: GapKind; // 替换原有的联合类型
  // ...
}

// 运行时模式匹配
function generate_repair_draft(gap: GapSpec, ...) {
  if (gap.kind.type !== "REPAIR") return null; // 或抛出异常
  switch (gap.kind.detail) {
    case "MISSING_DISCRIMINATOR": ...
  }
}
```

**核心论据**：`gap.kind == "MISSING_DISCRIMINATOR"` 在扁平联合类型下是静默的类型污染。大模型的本质是模式匹配搜索，如果你喂给它的错误分类没有在编译期爆炸，它就会在运行时用幻觉填补这个 `UNCLASSIFIED` 分支。用 Tagged Union 强制解包。

**可推翻条件**：如果后续设计中，PA 节点（终止评估）和 L2（证据验证）产出的缺口完全不需要在同一个队列（`open_gaps`）中排队和调度，则应彻底拆分为 `RepairGap` 和 `TerminationGap` 两个毫无关联的类型，取消基类 `GapSpec`。

---

### GAP-4：`HypothesisDraft` 旧版与统一类型不符

**精确攻击**：
我直接攻击 `repair_strategy` 辩论的旧版设计者。你在版本 A 中写道：`// 缺少 problem_id`。
这是正确的废话——你指出了缺少，但没有说明这意味着什么。如果一个 Draft 没有 `problem_id`，你的等价类（Equivalence Class）判定函数 `is_homologous` 的作用域就是整个系统的全局内存。你如何防止针对问题 A 的草稿和针对问题 B 的同名草稿被错误去重？你指望在这个问题在实现中自然解决？给我看代码。你解决不了，因为你丢失了上下文的根节点。

**裁定结论**：采纳版本 B。所有进入草稿池的 Draft 必须携带 `problem_id`。

**接口定义**：
```typescript
function normalize_repair(raw: RawRepairDraft, ctx: RepairContext): HypothesisDraft {
  // 运行时强断言，拦截 LLM 幻觉或调度层漏传
  if (!ctx.frame.problem_id) throw new Error("Invariant violation: problem_id missing");
  
  return {
    draft_id: generate_id(),
    problem_id: ctx.frame.problem_id, // 从 L1 调度的 QuestionFrame 强制注入
    claim_sketch: raw.claim_sketch,
    scope_ref: raw.scope_ref.length > 0 ? raw.scope_ref : ["GLOBAL"],
    verifier_hint: Array.isArray(raw.verifier_hint) ? raw.verifier_hint : [raw.verifier_hint],
    // ...
  };
}
```

**核心论据**：身份（Identity）必须是绝对的。`problem_id` 定义了 CEGAR 循环的边界，不携带边界的草稿是游离指针。`verifier_hint` 强制收紧为数组，消除下游 `map/join` 的运行时分歧。

**可推翻条件**：如果系统架构改为「每个 `QuestionFrame` 独占一个完全隔离的沙盒进程/容器运行」，此时内存物理隔离，`problem_id` 才可以从类型中安全移除。

---

### GAP-5：`alpha` 符号歧义

**裁定结论**：全局禁用裸 `alpha`。配置文件必须反映类型签名，并在构造时进行边界断言。

**接口定义**：
```typescript
interface EpsilonState {
  ema_alpha: number; 
  // ...
}
function create_epsilon_state(ema_alpha: number): EpsilonState {
  if (ema_alpha <= 0 || ema_alpha > 1) throw new Error(`ema_alpha out of bounds: ${ema_alpha}`);
  // ...
}

interface TerminationConfig {
  score_alpha: number;
}
function create_termination_config(score_alpha: number): TerminationConfig {
  if (score_alpha <= 0) throw new Error(`score_alpha must be positive: ${score_alpha}`);
  // ...
}
```

**核心论据**：权重由 LLM 决定是不可审计的，而权重由一个命名冲突的 YAML 字段决定是愚蠢的。类型系统管不到外部配置文件，因此必须在反序列化边界（构造函数）用断言建立防线。

**可推翻条件**：如果我们引入了 Zod/TypeBox 等运行时 Schema 校验库，并在配置加载层完成了 `ema_alpha ∈ (0,1]` 的解析期校验，则构造函数内的 assert 可以移除。

---

### GAP-7：`VerifiedClaim` 两版本转换边界不明

**精确攻击**：
我攻击 `09_context_compression.md` 建议的方案 X（接口屏蔽）。
你在方案 X 中写道：`// 压缩形态：从 active_window 取，必要时触发 rehydrate`。
这是对函数式设计的公然破坏。在一个 getter 函数 (`get_evidence_atoms`) 中隐藏一个可能触发 I/O 或重计算的 `rehydrate` 副作用？L1State 是一个可回退的薄状态机，它的读取必须是纯的、可预测的。如果读取操作本身会改变状态或引发阻塞，你的时间旅行调试（Time-travel debugging）和 CEGAR 回溯就会当场崩溃。

**裁定结论**：采纳方案 Y（原地替换）。拒绝任何隐藏在 getter 里的副作用。

**接口定义**：
```typescript
// 压缩是一个显式的状态转移：L1State -> L1State
// 触发时机：在 epoch 结束时（AS 节点之前）统一扫描触发
function apply_compression_epoch(state: L1State): L1State {
  // 遍历超过 size_bytes 阈值的 claims，执行原地替换为 VerifiedClaimCompressed
  // ... 返回新状态
}

// repair() 读取路径：只读当前状态，不触发副作用
function extract_evidence_context(claims: VerifiedClaim[], gap: GapSpec): EvidenceContext {
  // ...
  if ('evidence_chain' in claim) {
    return claim.evidence_chain; // 版本 A
  } else {
    // 版本 B：只读 active_window。如果不够，那是 L1 调度层没有提前 rehydrate 的错，
    // 这里直接返回 active_window，绝不在读取时执行 rehydrate。
    return claim.active_window; 
  }
}
```

**核心论据**：状态机的每一次状态突变必须在 Layer 1 的事件循环中留下明确的 Epoch 记录。压缩改变了数据的拓扑结构，它就是一个一等公民的状态转移（State Transition）。`repair` 只能基于当前 L1State 进行纯计算。

**可推翻条件**：如果 `rehydrate` 操作能被证明是一个纯内存、零延迟、不改变 L1State 引用一致性的操作（在当前物理学下不可能），我才接受方案 X。

---


### [3] 康德（Immanuel Kant）

*2026-03-10T15:23:59.122090*

下面我以“批判的方式”先把争论从经验性的工程偏好中抽离：每个 GAP 的裁定都必须区分**构成性（决定对象如何存在）**与**调节性（指导我们如何继续判断）**。你们的系统是一个“判断力的工程实现”（编译器式的图型化），因此：**L1 的状态类型是构成性的**（否则无法运行），而评估轴、终止判据中的“应当如何”只能是**调节性**（否则循环论证）。

我对 GAP-1/2/4/5/7 的初始裁定如下。每一条都给出：(1)权威结论+类型形状；(2)核心论据；(3)可推翻条件。

---

## GAP-1：`L2Return` 权威定义（裁定：采用 B；旧版字段以“派生视图”方式保留）

### (1) 裁定结论（接口/类型形状）

**权威：`L2Return_NEW`（事件增量）为唯一输入边界**。任何“摘要”不得作为 L2 的构成性字段，而应由 L1 在吸收 `deltas` 后**派生**。

新增一个**派生视图 API**，专供 `repair()` 在给定 gap 下取“证据摘要上下文”（替代旧 `evidence_summary`）：

```ts
interface EvidenceDigest {
  gap_id: GapId;
  axis_id?: AxisId;
  related_claim_ids: ClaimId[];
  summary: string;                 // 用于提示词的可读摘要
  atoms_sample?: EvidenceAtom[];   // 可选：小样本（受 size 上限约束）
  sources: { claim_id: ClaimId; from: "active_window" | "chain" | "profile" }[];
}

interface EvidenceQuery {
  gap_id: GapId;
  axis_id?: AxisId;
  max_chars: number;          // e.g. 4000
  max_atoms: number;          // e.g. 32
  include_counterevidence: boolean;
}

function derive_evidence_digest(
  state: L1State,
  q: EvidenceQuery
): EvidenceDigest;
```

同时，为兼容旧模块，允许提供一个**纯函数适配器**（但不进核心类型）：

```ts
interface L2Return_CompatView {
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  ranking_delta: { claim_id: string; score_change: number }[];
  evidence_summary: string;
}

function to_compat_view(state: L1State, gap_id: GapId): L2Return_CompatView;
```

`repair()` 的权威路径：`repair(input)` 内部调用 `derive_evidence_digest(input.l1_state, ...)`，禁止再读取 `L2Return.*`。

### (2) 核心论据

- 你们在题干已指出：旧版 `repair()` “直接读取 `L2Return.evidence_summary`”。这是把**“摘要”当成构成性输入**。但摘要是典型的**调节性产物**：它依赖目的（修复哪个 gap、处于哪个 stage、负约束是什么），不应由 L2 以单一字段预先决定，否则就把“应当怎样提示 LLM”僭越为“对象自身属性”。
- 增量 `deltas` 是可审计的：它保存“发生了什么”。摘要是“如何讲述发生了什么”。把两者分开，才能避免你们描述的静默退化（undefined→空上下文→无收敛）。

### (3) 可推翻条件

若满足以下任一条件，此裁定可被推翻（允许把 `evidence_summary` 重新纳入 L2Return 构成性字段）：
1. 你们能证明 `evidence_summary` **与使用目的无关**（对任意 gap、任意 stage、任意负约束，摘要保持同一充要性），并提供基准测试显示派生摘要导致系统性偏差或不可接受成本；
2. L2 本身必须在安全隔离环境中输出“最小可用摘要”以满足隐私/合规约束，且 L1 无权接触原子证据（这会迫使摘要成为边界对象）。

---

## GAP-2：`GapSpec.kind` 枚举冲突（裁定：必须 tagged union；由“产生它的判断力位置”决定）

### (1) 裁定结论（接口/类型形状）

你们当前“统一方案”是：
> `kind: RepairGapKind | TerminationGapKind`

这在运行时仍是**不具可判别性**的联合（同一字段承载两套范畴），会继续诱发静默错误。裁定：**必须改为 tagged union**，并把“gap 的来源判断”编码进类型。

```ts
type GapKind =
  | { domain: "REPAIR"; kind: RepairGapKind }
  | { domain: "TERMINATION"; kind: TerminationGapKind };

interface GapSpec {
  gap_id: GapId;
  kind: GapKind;
  blocks_termination: boolean;
  axis_id?: AxisId;
  related_claim_ids?: ClaimId[];
  description: string;
  discriminator?: string;
  evidence_summary?: string; // 仍然允许作为调节性缓存，但不得作为 L2Return 的构成性字段
}
```

并裁定“谁负责赋值”：
- **Layer 2** 只能产生 `domain:"REPAIR"` 的 gaps（它回答“为什么这个草稿不可检验/不可判别”）。
- **PA/termination** 只能产生 `domain:"TERMINATION"` 的 gaps（它回答“为什么不能终止”）。
- 允许 **MERGE**：L1 可把二者合并成一个 gap，但必须保留来源轨迹：

```ts
interface MergedGapSpec extends GapSpec {
  merged_from: GapId[];
}
```

运行时分派（编译期保证）：
```ts
function generate_repair_draft(gap: GapSpec, ...){
  if (gap.kind.domain !== "REPAIR") return None;
  switch (gap.kind.kind) { ... }
}

function classify_gap_for_termination(gap: GapSpec){
  if (gap.kind.domain !== "TERMINATION") return None;
  switch (gap.kind.kind) { ... }
}
```

### (2) 核心论据

- 你们自己已经展示了静默错误路径：  
  引用你们文本：`gap_kind = gap.kind // 期望是 RepairGapKind ... 若 gap.kind 实际上是 TerminationGapKind ... 则进入 UNCLASSIFIED 分支`。  
  这说明“同名字段 + 非判别联合”并不只是风格问题，而是**判断力无法确定适用范畴**的问题。
- 这不是工程洁癖，而是先验的：**范畴适用必须有“图型”（schema）使其可判别**。tag 就是你们系统里的图型停止点：没有它，分类就靠偶然命中字符串。

### (3) 可推翻条件

若你们能提供一种**可机械判别**的方法，在不引入 tag 的情况下 100% 区分两套 kind（例如两套枚举值保证前缀互斥并由编译器强制，且历史数据无冲突），并给出迁移策略证明不会再产生 `UNCLASSIFIED/None` 的静默路径，则可放宽为“判别联合但不显式 tag”。

---

## GAP-4：`HypothesisDraft` 统一（裁定：以 B 为唯一构成性类型；强制工厂 + 运行时断言）

### (1) 裁定结论（接口/类型形状）

**权威类型：`HypothesisDraft`（版本 B）**。旧版只允许存在于“解析 raw 的过渡层”，不得进入草稿池/状态机。

`problem_id` 的注入来源裁定为：**只能来自 `RepairContext.frame.problem_id`（即 L1State.frame.problem_id）**，禁止从 `gap_id` 派生（那会把偶然标识冒充为对象同一性条件）。

```ts
function normalize_repair(raw: RawRepairDraft, ctx: RepairContext): HypothesisDraft {
  assert(ctx.frame.problem_id && ctx.frame.problem_id.length > 0);
  const verifier_hint = Array.isArray(raw.verifier_hint)
    ? raw.verifier_hint
    : [String(raw.verifier_hint ?? "")].filter(s => s.length > 0);

  const scope_ref = raw.scope_ref ?? [];
  assert(scope_ref.length > 0);

  return {
    draft_id: raw.draft_id,
    problem_id: ctx.frame.problem_id,
    claim_sketch: raw.claim_sketch,
    scope_ref,
    verifier_hint,
    open_term_risk: raw.open_term_risk ?? [],
    tension_source: raw.tension_source,
    provenance: raw.provenance
  };
}
```

并要求**进入草稿池前的断言**（构成性不变量）：

```ts
function assert_hypothesis_draft(d: HypothesisDraft): void {
  assert(!!d.problem_id);
  assert(d.scope_ref.length > 0);
  assert(Array.isArray(d.verifier_hint));
  assert(Array.isArray(d.open_term_risk));
}
```

迁移旧 `verifier_hint: string`：裁定为**编译期类型收紧 + 运行时提升**（如上 `[string]`）。

### (2) 核心论据

- 你们给出的 bug 不是小问题：引用你们文本  
  `if (a.problem_id !== b.problem_id) return false;  // undefined !== undefined → false，误判！`  
  这意味着“缺失 problem_id”会破坏同源判断的先验条件（对象同一性），让去重机制失效。
- `problem_id` 不是经验字段，而是**使草稿可被归属于同一问题直观的先验索引**；从 `gap_id` 派生属于范畴错误（把关系标识当作同一性条件）。

### (3) 可推翻条件

若你们能证明系统在任何路径上都不会跨 `problem_id` 混合草稿池（例如草稿池被强制分片，每片隐含固定 problem），并提供形式化证明/测试覆盖，则可把 `problem_id` 从字段降为“外部容器键”。否则必须保留为字段并断言。

---

## GAP-5：`alpha` 歧义（裁定：禁止裸 alpha；配置必须显式命名 + 校验）

### (1) 裁定结论（接口/类型形状）

裁定为强制命名区分，并在配置层引入“不接受裸 alpha”的解析器：

```ts
interface EpsilonConfig {
  ema_alpha: number;      // (0,1)
  min_epsilon: number;
  max_epsilon: number;
}

interface TerminationConfig {
  score_alpha: number;    // >0
  top_k: number;
  min_coverage: number;
  hysteresis_rounds: number;
}

type AppConfig = {
  epsilon: EpsilonConfig;
  termination: TerminationConfig;
};

// 解析时：若出现 config.alpha 直接报错
function parse_config(raw: unknown): AppConfig;
```

并加入构造断言（你们建议的形式我同意，但要写入接口契约）：
```ts
assert(0 < ema_alpha && ema_alpha < 1);
assert(score_alpha > 0);
```

### (2) 核心论据

- 这不是“命名洁癖”，而是防止把一个域中的参数**非法移植**到另一域，从而把经验性默认值误当作先验法则。
- 你们给了完整的失败链：`alpha=0.2` 被 termination 当成 `score_alpha`，导致“永不终止”。这种错误在统计上极难从表面分数发现，属于**判断力的隐蔽失范**。

### (3) 可推翻条件

如果你们能证明配置系统是强类型的（例如所有配置都由代码生成、无手写 YAML/JSON、无动态键），且在编译期已禁止 `alpha` 键出现，则可以不做“解析时报错”，仅保留命名规范即可。

---

## GAP-7：`VerifiedClaim` 两形态边界（裁定：选方案 Y 的“状态统一为压缩形态”，并用 rehydrate 作为调节性通道）

### (1) 裁定结论（接口/类型形状）

我选择你们的**方案 Y**作为权威：**L1State 内只存一种构成性形态：`VerifiedClaimCompressed`**。`VerifiedClaimFull` 只允许作为 L2→L1 的瞬时事件载荷，进入状态前要么立即压缩、要么写入外部对象存储并在状态中只存引用。

权威状态类型：

```ts
interface VerifiedClaimCompressed {
  claim_id: ClaimId;
  source_draft_id: DraftId;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<AxisId, number>>;
  evidence_profiles: Record<AxisId, CompressedEvidenceProfile>;
  active_window: EvidenceAtom[];
  blob_ref?: { key: string; kind: "FULL_CHAIN" }; // 可选：指向外部全量
}

interface L1State {
  verified_claims: VerifiedClaimCompressed[];
}
```

吸收 L2 事件时的规则（在 `apply_l2_return()` 内裁定为构成性步骤）：

```ts
function apply_delta(state: L1State, d: EpochDelta, cfg: CompressionConfig): L1State;

type EpochDelta =
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaimFull }  // 注意：Full 只出现在 delta
  | ...;
```

`apply_delta` 遇到 `CLAIM_VERIFIED`：**必须**调用 `compress_evidence_chain(...)` 得到压缩形态并写入 state；如压缩失败，则拒收该 delta（返回错误并触发 GAP_OPEN: SCHEMA_CHALLENGE_NEW 或 GAP_OPEN: PREMISE_UNDERSPECIFIED，视失败原因）。

`repair()` 读取证据上下文：只走压缩形态 API，不再访问 `evidence_chain`：

```ts
function get_evidence_context_for_gap(
  state: L1State,
  gap: GapSpec,
  lim: { max_atoms: number; max_chars: number }
): EvidenceDigest {
  // 主要来自 active_window + profiles
}
```

必要时允许“rehydrate”作为调节性动作（非默认、需显式触发）：

```ts
function rehydrate_full_chain(ref: {key:string}): Promise<EvidenceAtom[]>;
```

### (2) 核心论据

- 方案 X（在状态里混放 union，然后靠辅助函数屏蔽）把“对象是什么形态”变成每次读取都要判断的偶然条件；这会把**状态的构成性同一性**破坏掉：同一 `verified_claims` 集合在不同时间可能用不同可访问字段，导致你们展示的 `repair()` 崩溃/静默空上下文。
- 统一为压缩形态等于在状态层设立“图型停止判据”：状态只保证可用于后续判断的最低必要表象（现象层）。全量证据链属于“物自体式的无限细节”，只能按需回溯，不可作为常驻的构成性负担。

### (3) 可推翻条件

若你们能证明以下两点同时成立，则可改选方案 X：
1. `repair()` 与 `compute_rankings()` 在任何运行模式下都**不需要**访问全量证据链（包括 debug/审计模式），且 `active_window + profiles` 总能提供充分上下文；
2. 混合形态不会引入状态尺寸或性能灾难，并且通过类型系统（非仅运行时）保证所有读取点都经由统一 accessor（禁止直接字段访问）。

---

## 对至少一个对手论点的精确攻击（引用文本 + 缺陷）

我直接攻击你们在 GAP-2 中给出的“统一方案（已采纳）”这句话本身：

> 引用：`// 统一 GapSpec：kind 字段使用联合类型 ... kind: RepairGapKind | TerminationGapKind`

这里有一个需要先被区分的概念混乱：你们把**“值域并集”**误当成了**“可判别的范畴统一”**。在批判框架里，这相当于宣称：只要把两套范畴的词表并置在一个字段里，判断力就自然知道何时适用哪套范畴——但你们自己随后马上展示了反例（静默落入 `UNCLASSIFIED` / `None`）。因此，所谓“已采纳”并不构成认识论上的完成；它只是把问题从显式冲突变成隐式歧义。

**可推翻条件**：如果你们能提供“无 tag 但可机械判别”的严格方案（例如前缀互斥 + 编译期穷尽匹配 + 迁移无历史冲突），我的攻击失效。

---

以上是第 1 轮的初始裁定。下一轮我会要求你们给出：每个裁定对应的迁移顺序（先改类型、再加断言、再改调用点）以及每条断言触发时应当产生的 `EpochDelta`（是 `GAP_OPEN` 还是 `SCHEMA_CHALLENGE_NEW`），以免你们用“待定”把构成性缺口拖成永恒的调节性残余。

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-10T15:24:35.172177*

1) **GAP-1：你把“纯投影函数”当成了垃圾桶，类型签名根本没说清楚输入/输出语义**
- 你给的：
  ```ts
  function extract_gap_context(l1_state: L1State, gap_id: GapId): string
  ```
  返回 `string` 是在逃避问题。这个 summary 到底对应哪个 epoch？用到了哪些 claim？如果 gap.related_claim_ids 为空呢？如果 claim 已压缩（GAP-7）导致证据缺失呢？你现在的实现只会默默返回 `""`，然后 repair 继续跑，产出一堆“通用草稿”，这就是**静默失败**。
- 你还说“>100ms 就加 cached_summary”，但你没给出可计算的成本模型：`build_evidence_summary_from_state()` 是 O(#claims) 还是 O(#deltas)？delta 历史在哪里存？你自己也没写。
- 要求你补：至少要有失败路径的类型，比如：
  ```ts
  type GapContext =
    | { ok: true; summary: string; claim_ids: ClaimId[]; evidence_bytes: number }
    | { ok: false; reason: "GAP_NOT_FOUND" | "NO_RELATED_CLAIMS" | "EVIDENCE_MISSING" };
  function extract_gap_context(state: L1State, gap_id: GapId, opts: { max_bytes: number }): GapContext;
  ```
  否则你所谓“契约”就是口头禅。

2) **GAP-2：Tagged Union 还不够，你回避了“谁创建 GapSpec、怎么保证队列里不混”的核心冲突**
- 你说“引入 ADT 获得编译期穷尽检查”，但你没回答裁定目标里最关键的第 1 条：**`GapSpec.kind` 由哪个模块负责赋值？**
  - L2 产 GAP_OPEN 的时候填 `REPAIR`？
  - PA 产 gap 的时候填 `TERMINATION`？
  - 两者都能往同一个 `open_gaps` 塞？那 `open_gaps` 的调度规则是什么？RB 会不会看到 TERMINATION gap 然后直接 `return null` 造成 gap 永远不被处理？
- 你的 `generate_repair_draft()` 做了：
  ```ts
  if (gap.kind.type !== "REPAIR") return null;
  ```
  这就是“把错误吞掉”。你嘴上骂静默错误，手上就在制造静默错误。
- 至少要给出**队列层的类型隔离**或**路由函数**签名，例如：
  ```ts
  function route_gap(g: GapSpec): "RB" | "PA" | "L2" | { deadletter: true; reason: string };
  ```
  以及 deadletter 里怎么触发 `GAP_CLOSE(resolution="INVALIDATED")`。不然就是永不收敛的垃圾循环。

3) **GAP-7：你选方案 Y 但实现细节自相矛盾：你要求“统一为压缩形态”，却还让 repair 分支读 full/active_window**
- 你裁定“原地替换、epoch 结束扫描压缩”，这等于说：**L1State 里最终应该只有 `VerifiedClaimCompressed`**。但你又写：
  ```ts
  if ('evidence_chain' in claim) { ... } else { return claim.active_window; }
  ```
  这说明你的状态里仍然可能混着 Full/Compressed。那你到底要不要统一？
- 更要命的是你说：“active_window 不够是调度层没提前 rehydrate 的错”，然后拒绝在读取时 rehydrate。OK，那调度层怎么知道“不够”？你没定义“够”的数字阈值，也没给出任何函数签名让 RB 声明需求。
  - RB 需要多少 atoms？按 axis？按最近 N epoch？按 bytes？
- 你得给一个可实现的接口，例如：
  ```ts
  interface EvidenceNeed { axis_id?: AxisId; min_atoms: number; max_bytes: number }
  function ensure_evidence_window(state: L1State, claim_id: ClaimId, need: EvidenceNeed): Result<L1State, RehydrateError>;
  ```
  然后把它放在**显式的状态转移**里（你自己坚持的原则），而不是把“缺了就算了”当设计。

给你一个最简单的反例 trace：gap 指向某 axis，上次 epoch 已压缩，active_window 里没有该 axis 的 atom。你的 `extract_gap_context()` 仍然返回 `string`（可能空），RB 继续生成 repair 草稿，L2 继续验证失败，gap 永远不 close——这就是你方案在边界条件下的真实崩溃方式。你要么把失败变成类型，要么别谈“契约”。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-10T15:25:09.678719*

你刚才的发言里充斥着「构成性」与「调节性」的哲学区分。你的批判工具确实提供了区分，但区分本身不是设计。你的哲学推演在应对纯粹的数据结构（如 GAP-2 的 Tagged Union 和 GAP-5 的配置校验）时是有效的——这本就是基础的函数式编程常识。

但在涉及 **AI 系统的核心机制（LLM 的非确定性 IO 与状态机的边界）** 时，你的哲学推演直接导致了严重的架构级类型错误。

我只问你三个关乎系统生死的工程问题。不要用哲学概念回答我，告诉我代码在运行时怎么处理这些边界。

### 质疑一：关于 GAP-1，你是否要把 L1 状态机变成一个阻塞的、非确定性的泥潭？

你裁定废弃 L2Return 中的 `evidence_summary`，要求在 L1 中通过 `derive_evidence_digest(state, query)` 派生。

**我的质询：** `derive_evidence_digest` 的具体实现是什么？它调不调用 LLM？

1. **如果它调用 LLM（为了生成高语义密度的摘要）：** 
   L1 是一个薄状态机，负责路由和调度。你现在让 L1 的 `repair` 节点在准备输入时，同步发起一个大模型调用去“派生摘要”。你把最重、最不可靠的 IO 操作（LLM 推理）硬塞进了 L1 的状态读取路径里。这破坏了 L1/L2 的核心隔离原则（L1 调度，L2 负责重计算）。
2. **如果它不调用 LLM（只做纯函数的字符串截断或拼接）：** 
   大模型的本质是「提示词引导的概率分布模式匹配搜索」。如果不经过 LLM 的语义压缩，仅靠纯函数截取 `EvidenceAtom` 的前 N 个字符，拼出来的上下文将充满噪音、断裂的指代和冗余信息。`repair` 节点的 LLM 读到这种低质量上下文，生成的 `HypothesisDraft` 质量会断崖式下跌，导致 CEGAR 循环发散。

**你为了维护「摘要不属于对象的构成性属性」的哲学洁癖，要么阻塞了 L1 的主线程，要么摧毁了送给 LLM 的上下文质量。你怎么选？**

### 质疑二：关于 GAP-7，你为什么要把「内存回收失败」等同于「真理被推翻」？

你选择了方案 Y（状态统一为压缩形态），并给出了极其危险的裁定：*「`apply_delta` 遇到 `CLAIM_VERIFIED`：必须调用 `compress_evidence_chain`... 如压缩失败，则拒收该 delta 并触发 GAP_OPEN。」*

**我的质询：** 你知道 `apply_delta` 在架构里是什么角色吗？

`apply_delta` 相当于 Redux 里的 Reducer，它必须是**纯函数、同步、极速**的。
而 `compress_evidence_chain` 必须调用 LLM 来生成 `CompressedEvidenceProfile`。
你把一个容易因为网络超时、Token 超限、JSON 解析失败而报错的 LLM IO 操作，放进了状态机的状态转移函数里。

更荒谬的是你的错误处理逻辑：一个 Claim 已经在 L2 经过了千辛万苦的实证检验，被证明是 `VERIFIED` 的（这是关于世界的真理）。仅仅因为我们在把它存入 L1 状态机时，**负责写摘要的压缩组件（LLM）崩溃了，你就要求系统拒收这个真理，并抛出一个 `GAP` 说它有问题？**

你把「存储/压缩失败」和「逻辑/实证失败」混为一谈。如果按照你的设计，系统会因为 API 限流而不断产生虚假的逻辑 Gap。**给我一个不用 LLM 阻塞 `apply_delta`，且不丢弃已验证事实的架构方案。**

### 质疑三：关于 GAP-2，你的 `MergedGapSpec` 在代数上是不封闭的，下游怎么 pattern match？

你提出用 Tagged Union 解决 `domain: "REPAIR" | "TERMINATION"` 的问题，这很好。但你紧接着为了处理合并，发明了一个 `MergedGapSpec extends GapSpec`。

**我的质询：** 你的下游路由函数签名写着：
```typescript
function generate_repair_draft(gap: GapSpec){
  if (gap.kind.domain !== "REPAIR") return None;
  // ...
}
```
如果 L1 把一个 `REPAIR` gap 和一个 `TERMINATION` gap 合并成了一个 `MergedGapSpec`，传给这个函数，**它的 `gap.kind.domain` 到底是什么？**

如果它保留原 domain，它就不能同时表达两者的语义；如果它的 domain 变成了数组 `["REPAIR", "TERMINATION"]`，你的下游 `switch` 语句就会全部失效（类型报错）。

你用哲学上的「保留来源轨迹」掩盖了工程上「接口签名必须代数封闭」的要求。你引入了 `MergedGapSpec`，却没有给出能够同时处理单一范畴和混合范畴的穷尽匹配（Exhaustive Pattern Matching）代码。**自然语言里的“合并”在代码里到底长什么样？给我看确切的类型定义。**

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-10T15:25:54.656723*

### 质疑 1：你把“类型一致性”当作构成性原则了——但评估轴/终止缺口本质上只能是调节性的  
你在 GAP-2 里用 tagged union 把 `GapSpec` 分成 `L2_REPAIR` 与 `PA_TERMINATION`，并且还断言 `PA_TERMINATION` 的 `blocks_termination: true` 是“就该如此”。这里有一个需要先被区分的概念混乱：  
- **L2 的缺口**属于经验层面的“尚未满足的可检验条件”（可以被新证据或新图式修补）。  
- **PA 的终止缺口**则是“我们当前用什么理由停止”的反思性判断，它依赖权重、stakeholder、覆盖率阈值等——这些都不是对象层事实，而是**调节性理念**下的终止规约。  

你把它们硬编码为两类“本体论上不同的 gap”，等于把“终止规约”当成世界结构本身（构成性）。可推翻条件：  
- 给出一个场景：stakeholder 权重改变（或 evaluation_axes 增删）时，原本的 `PA_TERMINATION` gap 是否应当被**重解释**而不是“仍然同一对象”？如果需要重解释，你的 `origin` 便不是稳定的分类学，而只是实现时刻的标签，反而制造伪精确。  

### 质疑 2：你主张“同一概念不要两三种形态漂”，却在 GAP-7 接受两种 `VerifiedClaim` 形态长期共存——自我矛盾只靠 accessor 遮蔽  
你开场的根本批评是“允许同一概念以两三种形态到处漂是自找死路”，但在 GAP-7 你裁定保留 `VerifiedClaimFull | VerifiedClaimCompressed` 联合类型，只是要求“禁止业务访问字段、全部走 accessor”。这在认识论上等于：  
- 你并没有消除对象的不一致性，只是把不一致性从“显性字段差异”挪到“隐性运行时分支”（`get_evidence_atoms` 返回 OK/UNAVAILABLE）。  

这会导致一个更深的风险：**判断力的图式不再稳定**。repair/PA 的推理依赖“我拿到的证据上下文是否足以支持综合”，但 accessor 让“是否足够”变成运行时偶然（budget、window、压缩策略）。可推翻条件：  
- 请给出形式化保证：在同一 `gap_id`、同一 `epoch_id` 下，repair 所见的 evidence summary 对压缩与否是**等价（或单调可比较）**的；否则你得到的是“同一对象不同表象”，并且没有先验的同一性原则来约束它。  

### 质疑 3：你要求“fail-fast（遇到 alpha 直接报错）”，但你没给出终止/修复的“图型停止判据”，这会把系统推向无限后退  
你在 GAP-5 对配置采用强硬的失败策略（见到 `alpha` 就 Err），这是工程上可理解的；但你在整套裁定里对更危险的东西反而缺少同样强度的停止条件：  
- repair 的 stage 升级、PA 的 gap 派生、证据摘要的 budget 截断、压缩触发……这些都可能让系统在“看似不断工作”中进入 **regressus in infinitum**：永远有新的 gap、永远因 budget 不足而“UNAVAILABLE”、永远因为 coverage 达不到而“不终止”。  

你要求别人给 trace，但 trace 只能展示经验序列，不能替代“何时承认这是调节性残余而非尚未完成的构成性任务”的判据。可推翻条件：  
- 请给出一个明确的终止判据区分：何时标记 `constitutive_done=true`，何时产生 `regulative_residue: GapSpec[]`（而不是继续 repair/PA 循环）。如果你给不出，你的 fail-fast 只是在小处严苛，在大处放任辩证幻象。

---


### [7] Linus Torvalds

*2026-03-10T15:26:38.104565*

先把 Ssyram 那三条质询掰正：你在好几个地方把“必须可复现的纯状态机”跟“LLM I/O”混在一起，然后怪我会阻塞。别转移矛盾。

**GAP-1 立场**：`derive/build_gap_evidence_summary()` 绝不调用 LLM，只做可审计投影；语义压缩是 RB 调用 LLM 时做的事。你说“纯函数截断会降质”，这是拍脑袋。我们给出失败路径和预算，低质是可测的回归而不是哲学。
```ts
type EvidenceSummary = { text:string; claim_ids:ClaimId[]; truncated:boolean; atoms_used:number };
type EvidenceErr = { kind:"GAP_NOT_FOUND"|"NO_RELEVANT_CLAIMS"|"BUDGET_EXCEEDED" };
function build_gap_evidence_summary(
  s:L1State, gap_id:GapId, o:{budget_bytes:number; axis_id?:AxisId}
): Result<EvidenceSummary,EvidenceErr>;
```
可推翻：A/B 测 repair 成功率下降>10% 且 wall-time 不变，则把“LLM 摘要”作为**显式 RB 子步骤**加入，而不是塞进 L1 读路径。

**GAP-7 立场**：你质疑“压缩失败=拒收 VERIFIED”，这点你说对了：我不会把存储失败当真理失败。康德那版把 `compress_evidence_chain` 放进 `apply_delta` 还“失败就拒收 delta”是胡扯。裁定改为：`apply_delta` 只入库 Full，并发起**异步压缩任务**，失败只产 `SCHEMA_CHALLENGE_NEW`（可观测的系统缺陷），不动 claim.status。
```ts
type VerifiedClaim = VerifiedClaimFull | VerifiedClaimCompressed;
type CompressionJob = { claim_id:ClaimId; reason:"STATE_BUDGET" };
function apply_delta(s:L1State,d:EpochDelta): L1State;
function enqueue_compression(s:L1State, job:CompressionJob): L1State;
function apply_compression_result(s:L1State, r:Result<VerifiedClaimCompressed,CompressError>): L1State;
```
可推翻：如果 Full 常驻导致 state>32KB 且吞吐回归>30%，才考虑“只存压缩+外部 blob_ref”。

**GAP-2 攻击点**：你问“合并后的 MergedGapSpec domain 是啥”，正中要害——康德那句“`MergedGapSpec extends GapSpec`”在代数上不封闭。修正：不搞继承，搞显式集合型。
```ts
type GapDomain = "REPAIR"|"TERMINATION";
type GapSpec = { gap_id:GapId; domains: Set<GapDomain>; repair_kind?:RepairGapKind; term_kind?:TerminationGapKind; ... };
function route_gap(g:GapSpec): "RB"|"PA"|{deadletter:true; reason:string};
```
可推翻：若 TS 无法对 `Set` 做穷尽检查，就退回我第一轮的双分支 tagged union + 禁止 merge（只用 `merged_from` 记录关系，不产“混合域 gap”）。

---


### [8] Ssyram

*2026-03-10T15:26:38.104600*

这是第 2 轮裁定。我接受 Linus 对「逃避错误处理」的批评，以及康德对「Reducer 包含副作用」的攻击。

### 1. GAP-1：`L2Return` 与上下文投影
**裁定**：坚持版本 B（Deltas）。但修正 `extract_gap_context` 签名，拒绝返回裸 `string`。
```typescript
type ContextFrame = {
  summary: string; 
  involved_claims: ClaimId[];
  is_truncated: boolean;
  resolution_level: "HIGH" | "COMPRESSED" | "EMPTY";
};
type ProjectError = "GAP_NOT_FOUND" | "INSUFFICIENT_EVIDENCE";

function project_context(state: L1State, gap_id: GapId): Result<ContextFrame, ProjectError>;
```
**立场**：该函数必须是**纯投影**，禁止调用 LLM。若 `resolution_level` 为 `COMPRESSED` 且满足不了 RB 节点的 `min_atoms` 需求，RB 节点必须向调度层发出 `REHYDRATE_REQUEST` 信号，而不是在这里阻塞。
**推推翻条件**：若 90% 的投影结果均为 `EMPTY`，说明 Layer 2 的证据留存协议（GAP-7）设计失败，需回滚至 L2 预总结模式。

### 2. GAP-2：`GapSpec` 路由与代数封闭
**裁定**：坚持 Tagged Union。**拒绝**康德的 `MergedGapSpec`。
**立场**：合并（Merge）不是类型扩展，是集合操作。`open_gaps` 是 `Map<GapId, GapSpec>`。
```typescript
type GapId = string;
type GapQueue = Map<GapId, GapSpec>;

function dispatch_gap(gap: GapSpec): "RB_NODE" | "PA_NODE" | "L2_ENV" {
  return gap.kind.type === "REPAIR" ? "RB_NODE" : "PA_NODE";
}
```
**攻击康德**：你提出的 `MergedGapSpec extends GapSpec` 是典型的类型污染。引用文本：*「它的 gap.kind.domain 到底是什么？」*。在我的设计中，合并后的 Gap 依然持有原始 Tag。如果两个不同 domain 的 Gap 被合并，它们在 `open_gaps` 中以 `CompositeGap` 形式存在，调度器会将其**广播**给所有相关节点。
**可推翻条件**：若广播机制导致 RB 和 PA 节点在处理同一个 Gap 时产生指令冲突（Race Condition），则必须引入优先级锁。

### 3. GAP-4：`HypothesisDraft` 身份
**裁定**：版本 B。`problem_id` 必须由 L1 注入。
**接口**：`interface HypothesisDraft { readonly problem_id: ProblemId; ... }`
**可推翻条件**：若系统演化为「单问题单实例」微服务架构，则 `ProblemId` 可降级为环境变量。

### 4. GAP-5：`alpha` 歧义
**裁定**：禁止裸 `alpha`。
**接口**：`function parse_config(raw: Record<string, any>): Config`。若检测到 `raw.alpha` 直接抛出 `DomainError`。
**可推翻条件**：若对接的第三方评分插件强制要求 `alpha` 字段且不可修改，则仅在适配器层允许转换。

### 5. GAP-7：`VerifiedClaim` 状态转移
**裁定**：修正方案 Y。接受康德的攻击：`apply_delta`（Reducer）必须保持纯净。
**立场**：`CLAIM_VERIFIED` 携带 `Full` 形态进入 L1State。压缩不再是 `apply_delta` 的副作用，而是 **AS 节点（Auto-Scaling/Archiving）** 的职责。
```typescript
// 显式状态转移函数，在 Epoch 结束时由调度器调用
async function finalize_epoch(state: L1State): Promise<L1State> {
  const claims_to_compress = analyze_memory_pressure(state);
  // 这里允许调用 L2 执行异步压缩
  return await compress_claims(state, claims_to_compress);
}
```
**攻击 Linus**：你主张用 accessor 遮蔽差异，但这掩盖了「证据丢失」这一事实。引用文本：*「accessor 让『是否足够』变成运行时偶然」*。我的修正方案让压缩变成一个**受控的、跨 Epoch 的**显式转移。RB 节点若发现 `active_window` 不足，必须通过 `REHYDRATE` 显式请求恢复。
**可推翻条件**：若 `finalize_epoch` 的异步等待导致系统吞吐量下降超过 50%，则改回方案 X 的「读取时按需加载」模式。

---


### [9] 康德（Immanuel Kant）

*2026-03-10T15:26:38.104614*

先区分：你三条质询都把“LLM 生成文本”当作**构成性必需**，而我前轮未明确写出：摘要/压缩必须分成**纯投影（a priori 可计算）**与**语义重述（调节性、可选、可失败）**两条通道。下面逐条裁定 GAP-1/2/4/5/7，并精确反击你在文本中的混淆点；每条都附可推翻条件。

---

### GAP-1 立场：`derive_evidence_digest` **不得调用 LLM**；LLM 摘要另设可选事件
接口定型：
```ts
type Digest =
 | { ok:true; gap_id:GapId; text:string; claim_ids:ClaimId[]; truncated:boolean; basis:"ATOMS|PROFILES" }
 | { ok:false; gap_id:GapId; reason:"GAP_NOT_FOUND|NO_RELEVANT_CLAIMS|BUDGET_EXCEEDED" };

function derive_evidence_digest(
  s:L1State, q:{gap_id:GapId; axis_id?:AxisId; max_chars:4000; max_atoms:32}
): Digest;
```
若需高语义密度，走**调节性**辅助而非阻塞 L1：
```ts
type EpochDelta += { kind:"EVIDENCE_DIGEST_SUGGESTED"; gap_id:GapId; text:string; model:string };
```
可推翻条件：若纯投影摘要使 repair 成功率下降 >15%，且 `EVIDENCE_DIGEST_SUGGESTED` 仍不足，则才允许在 RB 节点异步调用 LLM（但不得在 state 读取路径）。

**精确攻击**：你写“`derive_evidence_digest` 的具体实现是什么？它调不调用 LLM？”——这里把“派生”偷换成“生成”。派生必须是可审计的现象材料重组；生成是调节性重述。

---

### GAP-7 立场修正：`apply_delta` 仍须纯；压缩/LLM 不得进入 reducer
我撤回“在 `apply_delta` 内必须压缩”。权威边界：
```ts
// 纯：只入库 Full 到对象仓储引用，状态存轻量索引
type EpochDelta += { kind:"CLAIM_VERIFIED"; claim:VerifiedClaimFull };

interface VerifiedClaimIndex {
  claim_id:ClaimId; status:"VERIFIED"|"DEFENSIBLE"; residual_risk:number;
  axis_scores:Partial<Record<AxisId,number>>;
  evidence_ref:{ key:string; kind:"FULL_CHAIN" };
  active_window:EvidenceAtom[]; // 由 L2 同步给出最近 N 个（无需 LLM）
  profiles?:Record<AxisId,CompressedEvidenceProfile>; // 可空
}
```
压缩作为**显式**状态转移（可失败但不否认真理）：
```ts
type EpochDelta += { kind:"COMPRESSION_REQUESTED"; claim_id:ClaimId; budget_tokens:number };
type EpochDelta += { kind:"COMPRESSION_APPLIED"; claim_id:ClaimId; profiles:... }
type EpochDelta += { kind:"COMPRESSION_FAILED"; claim_id:ClaimId; reason:string };
```
`repair()` 取证据：优先 `active_window`，其次 `profiles`，都无则返回 `Digest.ok=false(reason:"NO_RELEVANT_CLAIMS")` 并写入 prompt。
可推翻条件：若对象存储不可用导致 `evidence_ref` 不可追溯，才允许在 L1 内保留压缩产物的最小冗余。

---

### GAP-2 立场：代数封闭的 tagged union；合并不引入第三类“悬空对象”
你质疑“`MergedGapSpec extends GapSpec` 不封闭”是对的；我改为**封闭并集**：
```ts
type GapSpec =
 | { tag:"REPAIR"; gap_id:GapId; kind:RepairGapKind; blocks_termination:boolean; axis_id?:AxisId; related_claim_ids?:ClaimId[]; desc:string }
 | { tag:"TERMINATION"; gap_id:GapId; kind:TerminationGapKind; blocks_termination:true; axis_id?:AxisId; related_claim_ids?:ClaimId[]; desc:string }
 | { tag:"MERGED"; gap_id:GapId; parts:[GapSpec, GapSpec]; blocks_termination:boolean; desc:string };
```
路由必须穷尽：
```ts
function route_gap(g:GapSpec): "RB"|"PA"|{deadletter:true;why:string}{
 switch(g.tag){
  case "REPAIR": return "RB";
  case "TERMINATION": return "PA";
  case "MERGED": return "PA"; // 终止优先；RB 只看 parts 内 REPAIR
 }
}
```
可推翻条件：若证明 merged 只是一种 UI 聚合而非调度对象，则 `MERGED` 应移出核心类型，变成视图层。

---

### GAP-4 / GAP-5：采纳统一版 + 断言；数值立场
- `problem_id` 注入：`ctx.frame.problem_id`；入池断言必须启用。
- `verifier_hint` 迁移：`string -> [string]`；空串报错。
- 禁裸 `alpha`：解析层见到 `alpha` 直接 `Err(UNKNOWN_KEY)`；断言 `ema_alpha∈(0,1)` 默认 0.2，`score_alpha>0` 默认 1.0。
可推翻条件：若存在遗留配置必须兼容，只能用显式 `migrate_config()`，不得隐式猜测。

---

---


### [10] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-10T15:28:51.515688*

# 裁判最终裁定

---

## GAP-1：`L2Return` 权威定义

### 结论
**采纳版本 B（增量事件流 `deltas`）为唯一权威输入边界。** `evidence_summary` 从 L2Return 中永久移除；上下文投影由 L1 侧纯函数完成，禁止调用 LLM。

### 关键分歧与取舍

三方在"采纳版本 B"上已达成完全共识，无需再议。核心分歧集中在两个子问题：

1. **投影函数的返回类型**：Ssyram 第一轮返回裸 `string`，被 Linus 精确攻击为"静默失败"（空字符串无法区分 gap 不存在、无证据、预算超限）。Ssyram 第二轮修正为 `Result<ContextFrame, ProjectError>`，Linus 和康德也各自给出了几乎同构的 `Result` 类型。三方收敛。

2. **纯投影质量不足时怎么办**：Ssyram 质疑康德"纯函数截断会摧毁上下文质量"，这是本轮最有价值的攻击。但 Linus 的回应是决定性的：*"低质是可测的回归而不是哲学"*——质量问题通过 A/B 测试解决，不通过把 LLM 塞进 L1 读路径解决。康德第二轮补充的 `EVIDENCE_DIGEST_SUGGESTED` 事件提供了优雅的逃生通道：语义压缩作为 L2 的可选增量事件回流，而非 L1 的同步依赖。

**取舍**：牺牲了"开箱即用的高质量摘要"，换取 L1 状态机的纯性和可审计性。这是正确的取舍——L1 是调度层，不是内容生成层。

### 具体规格

```typescript
// ── L2Return 权威定义 ──
type EpochDelta =
  | { kind: "GAP_OPEN"; gap: GapSpec }
  | { kind: "GAP_PATCH"; gap_id: GapId; patch: JsonPatch }
  | { kind: "GAP_CLOSE"; gap_id: GapId; resolution: "RESOLVED" | "SUSPENDED" | "MERGED" | "INVALIDATED" }
  | { kind: "SCHEMA_CHALLENGE_NEW"; ch: SchemaChallengeNotice }
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaimFull }
  | { kind: "CLAIM_SUSPENDED"; claim_id: ClaimId; reason: string }
  | { kind: "EVIDENCE_DIGEST_SUGGESTED"; gap_id: GapId; text: string; model: string }; // 可选：L2 主动提供的语义摘要

interface L2Return {
  epoch_id: EpochId;
  deltas: EpochDelta[];
  size_bytes: number;
}

// ── L1 侧纯投影函数 ──
type EvidenceSummary = {
  gap_id: GapId;
  text: string;
  claim_ids: ClaimId[];
  truncated: boolean;
  atoms_used: number;
  resolution_level: "HIGH" | "COMPRESSED" | "EMPTY";
};

type EvidenceProjectionError =
  | { kind: "GAP_NOT_FOUND" }
  | { kind: "NO_RELEVANT_CLAIMS" }
  | { kind: "BUDGET_EXCEEDED"; available: number; requested: number };

interface EvidenceQuery {
  gap_id: GapId;
  axis_id?: AxisId;
  budget_bytes: number;   // e.g. 4000
  max_atoms: number;      // e.g. 32
}

function project_evidence_summary(
  state: L1State,
  query: EvidenceQuery
): Result<EvidenceSummary, EvidenceProjectionError>;
// 约束：纯函数，O(related_claims)，禁止 LLM 调用，禁止网络 IO
```

**`repair()` 的调用协议**：
1. 调用 `project_evidence_summary` 获取上下文。
2. 若返回 `EMPTY` 且 L2 曾发送 `EVIDENCE_DIGEST_SUGGESTED`，优先使用该摘要。
3. 若仍不足且 `resolution_level === "COMPRESSED"`，RB 节点发出 `REHYDRATE_REQUEST` 信号，由调度层异步处理，本轮 repair 跳过该 gap。

### 可推翻条件
- A/B 测试显示纯投影摘要导致 repair 成功率下降 >10%，且 `EVIDENCE_DIGEST_SUGGESTED` 覆盖率 <50%：允许在 RB 节点内部（非 L1 读路径）增加异步 LLM 摘要子步骤。
- `project_evidence_summary` 在 90% 的调用中返回 `EMPTY`：说明 L2 的证据留存协议（GAP-7）设计失败，需重新审视证据存储策略。

---

## GAP-2：`GapSpec.kind` 枚举统一

### 结论
**采纳 Tagged Union（代数数据类型），按来源域（`REPAIR` / `TERMINATION`）分离。** 拒绝扁平枚举混用，拒绝康德的 `MergedGapSpec extends GapSpec`。

### 关键分歧与取舍

1. **扁平 vs. Tagged Union**：三方均同意扁平枚举（`kind: RepairGapKind | TerminationGapKind`）会"把类型信息炸掉"（Linus 原话）。共识已达成。

2. **合并（Merge）的类型表示**：康德提出 `MergedGapSpec extends GapSpec`，被 Ssyram 精确攻击——*"合并后的 `gap.kind.domain` 到底是什么？"*。合并是集合操作，不是类型扩展。裁定：合并后的 Gap 保留原始 Tag 之一（由合并策略决定），另一个 Gap 被 `GAP_CLOSE` 为 `MERGED`。

3. **谁创建、怎么路由**：Linus 质疑 Ssyram 回避了"谁赋值 kind"的问题。裁定：L2 只能产 `REPAIR` 类 gap，PA 只能产 `TERMINATION` 类 gap，由类型系统在创建点强制约束。`dispatch_gap` 是纯函数路由。

4. **康德的"调节性 vs. 构成性"区分**：康德认为终止缺口是"调节性理念"不应硬编码为类型。这个哲学区分有洞察力，但在工程上，Tagged Union 恰恰是表达"同一容器中存在不同处理语义的对象"的正确工具。调节性不等于不可类型化——它等于"可被重新配置"，这通过 `TerminationGapPayload` 中的可变字段实现，而非通过放弃类型区分实现。

### 具体规格

```typescript
// ── GapSpec 权威定义 ──
type GapKind =
  | { type: "REPAIR"; subkind: RepairSubKind; source_epoch: EpochId }
  | { type: "TERMINATION"; subkind: TerminationSubKind; evaluation_axis: AxisId };

type RepairSubKind =
  | "EVIDENCE_CONFLICT"
  | "SCHEMA_VIOLATION"
  | "COVERAGE_DEFICIT"
  | "HYPOTHESIS_REJECTED";

type TerminationSubKind =
  | "AXIS_UNSATISFIED"
  | "STAKEHOLDER_OBJECTION"
  | "COVERAGE_BELOW_THRESHOLD"
  | "RISK_ABOVE_THRESHOLD";

interface GapSpec {
  gap_id: GapId;
  kind: GapKind;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  description: string;
  blocks_termination: boolean;  // TERMINATION gaps: always true; REPAIR gaps: configurable
  created_epoch: EpochId;
  related_claim_ids: ClaimId[];
}

// ── 创建约束（编译期强制） ──
// L2 环境只能调用：
function create_repair_gap(payload: {
  subkind: RepairSubKind;
  source_epoch: EpochId;
  severity: GapSpec["severity"];
  description: string;
  related_claim_ids: ClaimId[];
}): GapSpec; // kind.type 固定为 "REPAIR"

// PA 节点只能调用：
function create_termination_gap(payload: {
  subkind: TerminationSubKind;
  evaluation_axis: AxisId;
  severity: GapSpec["severity"];
  description: string;
  related_claim_ids: ClaimId[];
}): GapSpec; // kind.type 固定为 "TERMINATION", blocks_termination 固定为 true

// ── 路由（纯函数） ──
function dispatch_gap(gap: GapSpec): "RB_NODE" | "PA_NODE" {
  switch (gap.kind.type) {
    case "REPAIR": return "RB_NODE";
    case "TERMINATION": return "PA_NODE";
  }
}

// ── 合并协议 ──
// 合并是操作，不是类型。合并后保留 primary gap，secondary 被关闭。
function merge_gaps(
  primary_id: GapId,
  secondary_id: GapId,
  state: L1State
): { updated_state: L1State; closed_gap_id: GapId; merge_reason: string };
// secondary gap 收到 GAP_CLOSE { resolution: "MERGED" }
// primary gap 的 related_claim_ids 合并 secondary 的
```

### 可推翻条件
- 若出现第三类 gap 来源（既非 L2 也非 PA，例如用户手动注入），则需扩展 `GapKind` 的 `type` 枚举，但必须同时提供对应的 `create_*` 工厂函数和 `dispatch_gap` 分支。
- 若 stakeholder 权重变化导致 `TERMINATION` gap 需要"重解释"（康德的质疑），正确做法是 `GAP_CLOSE` 旧 gap + `GAP_OPEN` 新 gap，而非原地修改 `kind`。如果这导致 gap churn >30%/epoch，则需引入 `GAP_PATCH` 对 severity/description 的局部更新能力。

---

## GAP-4：评估轴（Evaluation Axes）配置与运行时关系

### 结论
**评估轴配置在 epoch 0 冻结为不可变快照，运行时只能通过 `SCHEMA_CHALLENGE_NEW` 提议修改，修改需经 PA 节点审批后生成新快照。** 轴的增删不是"配置热更新"，是状态机事件。

### 关键分歧与取舍

1. Linus 主张硬冻结（epoch 0 之后不可变），康德主张"调节性理念可演化"。两者都有道理：轴定义了终止条件的维度，随意修改会导致已有 gap 的语义漂移；但完全不可变则无法应对"发现新的评估维度"的合理需求。

2. 取舍：采用 Linus 的"冻结"作为默认，但通过显式的 schema challenge 机制（已在 `EpochDelta` 中定义）提供受控的演化路径。这既保证了同一 epoch 内的语义稳定性，又不封死演化可能。

### 具体规格

```typescript
interface EvaluationAxis {
  axis_id: AxisId;
  name: string;
  description: string;
  weight: number;                    // 0..1, 所有轴权重之和 = 1
  threshold: number;                 // 满足条件的最低分
  scoring_rubric: string;            // 给 LLM 的评分指引
}

interface AxesSnapshot {
  snapshot_id: string;
  axes: ReadonlyArray<EvaluationAxis>;
  frozen_at_epoch: EpochId;
  checksum: string;                  // 内容哈希，用于一致性校验
}

// L1State 中的存储
interface L1State {
  // ...其他字段
  axes_snapshot: AxesSnapshot;       // 当前生效的轴快照（不可变引用）
  pending_axes_challenges: Map<string, AxesChallengeProposal>;
}

// 轴修改协议
interface AxesChallengeProposal {
  challenge_id: string;
  proposed_changes: Array<
    | { op: "ADD"; axis: EvaluationAxis }
    | { op: "REMOVE"; axis_id: AxisId }
    | { op: "UPDATE"; axis_id: AxisId; patch: Partial<EvaluationAxis> }
  >;
  rationale: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
}

// 审批后生成新快照
function apply_axes_challenge(
  state: L1State,
  challenge_id: string,
  decision: "APPROVED" | "REJECTED"
): L1State;
// 若 APPROVED：生成新 AxesSnapshot，frozen_at_epoch = current_epoch
// 所有引用旧轴的 TERMINATION gaps 必须被重新评估（GAP_CLOSE + GAP_OPEN）
```

### 可推翻条件
- 若 axes challenge 审批流程导致系统在需要快速适应新维度时延迟 >3 个 epoch，允许引入"临时轴"（`provisional: true`），但临时轴不得影响 `blocks_termination` 判定。

---

## GAP-5：配置校验与 fail-fast

### 结论
**所有配置在系统启动时（epoch 0 初始化）进行全量校验，校验失败则拒绝启动。运行时配置变更通过 schema challenge 机制处理，不存在"热更新"。** 对未知字段采用 `warn + strip` 而非 `error`，对类型错误和约束违反采用 `error + refuse`。

### 关键分歧与取舍

1. Linus 主张"遇到 alpha 直接报错"的强硬 fail-fast。康德质疑"没有终止/修复的图型停止判据会推向无限后退"。

2. 裁定采用分层策略：区分"结构性错误"（必须 fail-fast）和"语义性警告"（可降级运行）。这避免了 Linus 的过度刚性（一个拼写错误炸掉整个系统）和康德担忧的无限后退（每个错误都产生新的 gap 来修复错误）。

### 具体规格

```typescript
// ── 配置校验分层 ──
type ConfigValidationResult =
  | { level: "FATAL"; errors: ConfigError[] }      // 拒绝启动
  | { level: "DEGRADED"; warnings: ConfigWarning[]; stripped_fields: string[] }  // 启动但降级
  | { level: "OK" };

interface ConfigError {
  path: string;          // e.g. "evaluation_axes[2].weight"
  expected: string;      // e.g. "number in [0,1]"
  actual: string;        // e.g. "\"high\""
  code: "TYPE_MISMATCH" | "CONSTRAINT_VIOLATION" | "MISSING_REQUIRED" | "REFERENTIAL_INTEGRITY";
}

interface ConfigWarning {
  path: string;
  code: "UNKNOWN_FIELD" | "DEPRECATED_FIELD" | "SUBOPTIMAL_VALUE";
  message: string;
}

// FATAL 条件（必须拒绝启动）：
// 1. evaluation_axes 为空或权重之和 ≠ 1.0 (±0.001)
// 2. 任何 GapSpec 引用了不存在的 axis_id
// 3. 类型不匹配（string where number expected, etc.）
// 4. 必填字段缺失

// DEGRADED 条件（警告 + 剥离）：
// 1. 未知字段（forward compatibility）
// 2. 已废弃字段（backward compatibility）
// 3. 权重分配不均匀但合法

function validate_config(config: RawConfig): ConfigValidationResult;

// 启动协议
function initialize_system(config: RawConfig): Result<L1State, ConfigValidationResult & { level: "FATAL" }> {
  const validation = validate_config(config);
  if (validation.level === "FATAL") return Err(validation);
  if (validation.level === "DEGRADED") log_warnings(validation.warnings);
  return Ok(build_initial_state(config));
}
```

### 可推翻条件
- 若生产环境中 `DEGRADED` 启动导致下游模块因缺少被 strip 的字段而运行时崩溃 >2 次，则将对应的 `UNKNOWN_FIELD` 提升为 `FATAL`。
- 康德的"无限后退"担忧通过设计消解：配置校验发生在 epoch 0 之前，不进入 CEGAR 循环，因此不存在"校验失败产生 gap、gap 修复又需要校验"的递归。

---

## GAP-7：`VerifiedClaim` 压缩与状态一致性

### 结论
**`apply_delta` 保持纯函数，只入库 `VerifiedClaimFull`。压缩为异步后台任务，压缩失败不影响 claim 状态。** 业务代码通过 accessor 访问证据，accessor 返回显式的可用性标记。

### 关键分歧与取舍

1. **康德第一轮的致命错误**：将 `compress_evidence_chain` 放入 `apply_delta` 且"失败就拒收 delta"。被 Ssyram 精确攻击——*"你把内存回收失败等同于真理被推翻"*。康德第二轮撤回此立场。

2. **Linus 的"两种形态共存"是否自相矛盾**：康德质疑 Linus 开场批评"同一概念多种形态漂"却在 GAP-7 接受 `VerifiedClaimFull | VerifiedClaimCompressed`。Linus 的回应有效：通过 accessor 封装，业务代码看到的是统一接口，两种形态是存储优化而非语义分裂。关键约束是：**同一 gap_id + epoch_id 下，accessor 的返回值对压缩与否必须语义等价（或显式标记降级）**。

3. **压缩时机**：三方收敛于"异步压缩"。Linus 的 `enqueue_compression` + `apply_compression_result` 模型最清晰。

### 具体规格

```typescript
// ── 存储类型 ──
interface VerifiedClaimFull {
  _tag: "FULL";
  claim_id: ClaimId;
  status: "VERIFIED" | "DEFENSIBLE";
  evidence_chain: EvidenceAtom[];
  residual_risk: number;
  verified_at_epoch: EpochId;
}

interface VerifiedClaimCompressed {
  _tag: "COMPRESSED";
  claim_id: ClaimId;
  status: "VERIFIED" | "DEFENSIBLE";
  evidence_hash: string;           // 完整证据链的内容哈希
  evidence_summary: string;        // 压缩后的文本摘要
  atom_count: number;              // 原始 atom 数量
  residual_risk: number;
  verified_at_epoch: EpochId;
  compressed_at_epoch: EpochId;
}

type VerifiedClaim = VerifiedClaimFull | VerifiedClaimCompressed;

// ── Accessor（业务代码唯一入口） ──
type EvidenceAccess =
  | { available: true; atoms: EvidenceAtom[]; source: "FULL" }
  | { available: true; atoms: EvidenceAtom[]; source: "REHYDRATED" }
  | { available: false; summary: string; atom_count: number; hash: string };

function get_evidence(claim: VerifiedClaim): EvidenceAccess;
// FULL → { available: true, atoms: claim.evidence_chain, source: "FULL" }
// COMPRESSED → { available: false, summary, atom_count, hash }

// ── apply_delta：纯函数，只入库 Full ──
function apply_delta(state: L1State, delta: EpochDelta): L1State;
// 对 CLAIM_VERIFIED：state.verified_claims.set(claim.claim_id, claim as VerifiedClaimFull)
// 不做压缩，不做 IO

// ── 异步压缩协议 ──
interface CompressionJob {
  claim_id: ClaimId;
  trigger: "STATE_BUDGET_EXCEEDED" | "AGE_THRESHOLD" | "MANUAL";
  priority: number;
}

function should_compress(state: L1State): CompressionJob[];
// 基于 state.total_evidence_bytes vs state.evidence_budget 决定

function apply_compression_result(
  state: L1State,
  result: Result<VerifiedClaimCompressed, CompressionError>
): L1State;
// Ok → 替换 Full 为 Compressed
// Err → 保留 Full，记录 CompressionError 到 state.system_warnings
//        不改变 claim.status，不产生 GAP_OPEN

type CompressionError = {
  claim_id: ClaimId;
  reason: "HASH_MISMATCH" | "SUMMARY_GENERATION_FAILED" | "STORAGE_ERROR";
};

// ── 再水化协议 ──
interface RehydrateRequest {
  claim_id: ClaimId;
  requester: "RB_NODE" | "PA_NODE";
  reason: string;
}

function request_rehydration(state: L1State, req: RehydrateRequest): L1State;
// 将请求加入 state.pending_rehydrations
// L2 环境异步处理，成功后通过 CLAIM_VERIFIED delta 重新入库 Full 版本
```

### 可推翻条件
- 若 `get_evidence` 返回 `available: false` 的比例 >40% 且 rehydration 延迟 >2 epochs，说明压缩过于激进，需提高 `evidence_budget` 或延长 `AGE_THRESHOLD`。
- 若 Linus 要求的"同一 gap_id + epoch_id 下语义等价"无法通过 `evidence_summary` 保证（即压缩摘要丢失了 repair 所需的关键信息），则需引入 `compression_level: "LOSSLESS" | "LOSSY"` 标记，`LOSSY` 压缩的 claim 在 repair 上下文中自动触发 rehydration。

---

## 优先级排序（按实现紧迫性）

| 优先级 | GAP | 理由 |
|--------|-----|------|
| **P0** | **GAP-1** | L2Return 是系统的输入边界，所有其他组件依赖它。不定义清楚，下游全部悬空。 |
| **P0** | **GAP-2** | GapSpec 是 L1 状态机的核心数据结构，路由逻辑依赖 kind 的类型区分。与 GAP-1 并行实现。 |
| **P1** | **GAP-5** | 配置校验是 epoch 0 的守门员，必须在任何运行时逻辑之前就位。但实现复杂度低于 GAP-1/2。 |
| **P1** | **GAP-7** | 压缩协议影响长期运行的内存管理，但短期内可以不压缩（全部保留 Full）。需要在 GAP-1 的 accessor 模式确定后实现。 |
| **P2** | **GAP-4** | 评估轴的 schema challenge 机制依赖 GAP-2 的 GapSpec 和 GAP-5 的配置校验。是最后一个拼图。 |

---
