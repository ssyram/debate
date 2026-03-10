# v3 认知引擎缺失节点设计：GAP-3/6/8 Layer 1 三节点接口从零裁定 裁判总结

> 2026-03-10T15:35:57.315625

# 最终裁定书

## 方法论说明

三位辩手在 GAP-3/6/8 上经过两轮交锋后，核心分歧已充分暴露。我逐个 GAP 给出不可搁置的裁定。

---

## GAP-3：`AnswerSeed` 接口

### 结论
**AnswerSeed 是 tagged union（`ANSWER_SEED | ANSWER_SEED_SKIPPED`），coverage 是二值命中+可选强度，数据源头在 PA 的 `RankedClaim.axis_hits`。**

### 关键分歧与取舍

| 分歧点 | Linus | Ssyram | 康德 | 裁定 |
|--------|-------|--------|------|------|
| AS 是否包含叙述文本 | 包含 `NarrativeBlock` | 拒绝，属 L0 | 调节性，可选 | **不包含**。Ssyram 正确：AS 是数据投影层，叙述属于下游渲染。将 narrative 放入 L1 状态会污染可重放性。 |
| Coverage 语义 | `strength = max(axis_scores)`, `covered = strength > 0` | `max(axis_hits[ax])` | Score≠Coverage，必须区分 | **康德胜出**。Score 衡量可辩护性，Coverage 衡量探索度。一个 score=0.95 的正确废话不等于该轴被充分探索。但 Ssyram 的反驳（"Witness 覆盖概率"）在单 claim 场景下不成立——Linus 质询的"trivial 反例即宣布遍历完毕"是致命的。裁定：`covered` 是二值（0\|1），`strength` 是调节性附属。 |
| 数据来源 | 扩展 `RankedClaim` 加 `axis_scores: Record<AxisId, number>` | 扩展 `RankedClaim` 加 `axis_hits: Record<AxisId, number>` | 要求非循环来源的 `axis_hits` | **裁定用 `axis_hits`**。`axis_scores` 暗示精确数值，但 PA 阶段能给出的只是"该 claim 是否触及该轴"及粗粒度强度。用 `axis_hits` 语义更诚实。来源必须是 CC 的 `scope_ref` 或 L2 的 axis attribution，不可由 AS 节点自行推断。 |
| 函数签名 | `assemble_answer_seed(state: L1State)` | `assemble_answer_seed(pa_state, frame) → AnswerSeed \| null` | 需要 `integrity_status` 从 `EngineSnapshot` 传入 | **Linus 胜出**。传入 `L1State` 是唯一不越权的签名。Ssyram 的 `null` 返回值语义不明确；用 `ANSWER_SEED_SKIPPED` variant 替代。 |

### 具体规格

```typescript
type IntegrityStatus = "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
type AxisId = string;
type ClaimId = string;

interface RankedClaim {
  claim_id: ClaimId;
  score: number;          // 全局 Defensibility ∈ [0,1]
  coverage: number;       // 全局 coverage（已有字段）
  axis_hits: Record<AxisId, number>;  
  // 语义：该 claim 对各轴的贡献度 ∈ [0,1]
  // 来源：PA 聚合时从 CC.scope_ref 或 L2 axis attribution 注入
  // 不可由 AS 节点计算
}

interface AxisCoverage {
  covered: 0 | 1;                    // 构成性：是否有任何 top_claim 命中该轴
  strength?: number;                 // 调节性：max(top_claims[i].axis_hits[axis])
}

interface AnswerSeedProduced {
  kind: "ANSWER_SEED";
  problem_id: string;
  epoch_id: number;
  integrity_status: IntegrityStatus;
  termination_reason: string;
  top_k: number;
  top_claims: RankedClaim[];         // length ≤ top_k
  coverage_report: Record<AxisId, AxisCoverage>;
  provenance: {
    ranked_claim_ids: ClaimId[];     // 快照，用于可重放
    evaluation_axis_ids: AxisId[];   // frame 快照
  };
}

interface AnswerSeedSkipped {
  kind: "ANSWER_SEED_SKIPPED";
  problem_id: string;
  epoch_id: number;
  integrity_status: IntegrityStatus;
  termination_reason: string;
  skipped_because: 
    | "TERMINATED_BEFORE_AS" 
    | "INTERNAL_ERROR" 
    | "NO_SURVIVING_CLAIMS";
}

type AnswerSeed = AnswerSeedProduced | AnswerSeedSkipped;

function assemble_answer_seed(state: L1State): AnswerSeed;
// 纯函数。integrity_status 从 state.engine_snapshot 读取。
// 当 state.pa_state.ranked_claims 为空或 stage 不允许时，返回 Skipped variant。
```

### 可推翻条件
1. 若 PA 侧证明无法在聚合阶段产出 `axis_hits`（例如 CC 的 `scope_ref` 不含轴信息且 L2 不做 axis attribution），则 `axis_hits` 退化为 `axis_ids: AxisId[]`（布尔命中，无强度），`strength` 字段删除。
2. 若实验证明二值 `covered` 导致终止判断信息不足（无法区分"浅触及"与"深覆盖"），则将 `covered` 改为 `coverage_depth: number ∈ [0,1]`，但计算方法必须独立于 `score`（例如用该轴上 claim 数量的归一化）。

---

## GAP-6：`RegulativeIdea` → 可检验草稿的桥接策略

### 结论
**RB 节点执行"规则预筛 + LLM 提取代理变量"两阶段流程；novelty 判定由外部纯函数计算，LLM 不参与自评分；失败路径必须写入状态。**

### 关键分歧与取舍

| 分歧点 | Linus | Ssyram | 康德 | 裁定 |
|--------|-------|--------|------|------|
| LLM 自评 novelty | 拒绝，由系统算 Jaccard | 撤回自评，改用 ER Graph 差异 | `diff_proof` 不可由 LLM 自证 | **三方共识：LLM 不自评 novelty**。裁定用 Linus 的方案作为基线（Jaccard on entity set），因为 ER Graph 增加了未定义的解析成本。 |
| 策略枚举 | `PROXY_MEASURE \| COMPONENT_DECOMPOSE \| LOGICALLY_NON_TESTABLE` | 只允许 `PROXY_MEASURE \| COMPONENT_DECOMPOSE`，拒绝 `REFRAME` | 需要可审计的停止判据 | **裁定保留三值**（含 `LOGICALLY_NON_TESTABLE`）。Ssyram 拒绝 `REFRAME` 是对的（同义替换无信息增量），但 Linus 的 `LOGICALLY_NON_TESTABLE` 是必要的失败出口——不是策略，是终止标记。 |
| 黑名单/预筛 | 关键词黑名单 + `find_related_axes()` | 强制代理映射，无黑名单 | 黑名单是未经证明的先验立法 | **康德的质疑有效但不致命**。裁定：保留预筛但要求黑名单可配置、可版本化、附带误杀率日志。不硬编码。 |
| 失败路径 | 写入 `rb_reject_log` | 未明确 | 写入状态，避免静默 | **必须写入 L1State**。Linus 和康德共识。 |

### 具体规格

```typescript
type ExtractionStrategy = 
  | "PROXY_MEASURE"           // 找到可量化的代理变量
  | "COMPONENT_DECOMPOSE"     // 拆解为可独立检验的子组件
  | "LOGICALLY_NON_TESTABLE"; // 终止标记，非策略

interface ExtractableAngle {
  claim_sketch: string;
  proxy_entities: string[];   // 强制提取的具体代理实体
  extraction_strategy: Exclude<ExtractionStrategy, "LOGICALLY_NON_TESTABLE">;
  scope_ref: AxisId[];        // 必须引用 frame.evaluation_axes 中存在的 axis_id
}

interface AngleReject {
  idea_id: string;
  reason: "NON_TESTABLE" | "HOMOLOGOUS" | "NO_RELATED_AXIS" | "LLM_TIMEOUT";
  detail: string;
  timestamp: number;
}

interface RBResult {
  kind: "RB_SUCCESS";
  angle: ExtractableAngle;
  novelty_score: number;      // 由系统计算，非 LLM
} | {
  kind: "RB_REJECT";
  reject: AngleReject;
}

// 预筛：可配置，不硬编码
interface RBFilterConfig {
  blacklist_patterns: string[];           // 可版本化
  min_related_axes: number;               // 默认 1
  novelty_threshold: number;              // 默认 0.35
  novelty_method: "jaccard_entity" | "tfidf_cosine";  // 可扩展
  novelty_method_version: string;         // e.g. "v1.jaccard.2024"
}

function extract_testable_angle(
  idea: RegulativeIdea,
  frame: QuestionFrame,
  existing_claims: RankedClaim[],
  config: RBFilterConfig
): RBResult;

// novelty 纯函数
function compute_novelty(
  candidate_entities: string[],
  existing_entities: string[],
  method: RBFilterConfig["novelty_method"]
): number;

// scope_ref 运行时断言
function validate_scope_ref(
  scope_ref: AxisId[], 
  valid_axes: AxisId[]
): void;  // throws if scope_ref ⊄ valid_axes
```

**Orchestrator 集成要求：**
- `RB_REJECT` 必须写入 `L1State.rb_reject_log: AngleReject[]`
- 连续 N 次（可配置，默认 3）`RB_REJECT` 且 reason 均为 `NON_TESTABLE` 时，触发 `termination_reason = "RB_EXHAUSTED"`

### 可推翻条件
1. 若 `is_homologous()` 的实际实现使用结构化哈希而非文本距离，则 `compute_novelty` 必须对齐其算法，Jaccard 基线作废。
2. 若实验表明 `jaccard_entity` 的误杀率 >20%（在 50+ 个 RegulativeIdea 样本上），则切换到 `tfidf_cosine` 并重新标定阈值。
3. 若 `COMPONENT_DECOMPOSE` 策略在实践中产出的子组件仍被 `is_homologous()` 拦截率 >50%，则该策略需要增加"必须改变至少一个因果变量"的硬约束。

---

## GAP-8：历史视图与 D2 注入

### 结论
**D2 只注入索引句柄（`EvidenceRef`），不携带 EvidenceChain 正文；历史视图是只读投影，不进入 L1State 持久化。**

### 关键分歧与取舍

| 分歧点 | Linus | Ssyram | 康德 | 裁定 |
|--------|-------|--------|------|------|
| EvidenceChain 是否进入 L1State | 未明确反对 | 反对，会打爆内存 | 只注入索引句柄 | **康德和 Ssyram 共识正确**。EvidenceChain 正文属于 L2 存储，L1 只持有引用。一个 epoch 可能产生数百条 evidence，全部内联会使状态快照不可序列化。 |
| 历史视图的持久化 | 应写入状态 | 只读投影 | 调节性，不持久化 | **裁定：不持久化**。历史视图是从 `L1State` + 外部存储按需计算的投影。持久化会导致状态膨胀和一致性维护负担。 |
| D2 注入的粒度 | 完整 claim 历史 | 按需查询 | 索引句柄 + etag | **裁定用索引句柄**。D2 需要知道"哪些 claim 被验证过、结果如何"，但不需要证据原文。`EvidenceRef` 提供足够的路由信息。 |

### 具体规格

```typescript
interface EvidenceRef {
  claim_id: ClaimId;
  epoch_id: number;
  verdict: "SUPPORTED" | "REFUTED" | "INSUFFICIENT" | "ERROR";
  etag: string;              // 外部存储的版本标识，用于缓存一致性
  storage_key: string;       // 指向外部存储的键
}

interface EpochSummary {
  epoch_id: number;
  claims_evaluated: number;
  claims_surviving: number;
  coverage_snapshot: Record<AxisId, AxisCoverage>;  // 该 epoch 结束时的覆盖状态
  evidence_refs: EvidenceRef[];
}

// 历史视图：只读投影，不持久化到 L1State
interface HistoryView {
  epochs: EpochSummary[];
  // 按需从外部存储加载
  resolve_evidence(ref: EvidenceRef): Promise<EvidenceChain>;
}

// D2 注入接口
interface VerificationContext {
  current_epoch: number;
  prior_evidence: EvidenceRef[];      // 仅索引
  prior_verdicts: Record<ClaimId, EvidenceRef["verdict"]>;
}

function build_verification_context(state: L1State): VerificationContext;
// 纯函数，从 state.epoch_history 提取索引

// L1State 中的历史存储（轻量）
interface L1State {
  // ... 其他字段 ...
  epoch_history: EpochSummary[];      // 每个 epoch 结束时追加
  // 注意：不包含 EvidenceChain 正文
}
```

### 可推翻条件
1. 若 D2 的实际 LLM 调用证明仅靠 `verdict` 无法做出有效的验证策略调整（例如需要看到前次证据的具体反驳点），则允许在 `EvidenceRef` 中增加 `summary: string`（≤200 字的摘要），但仍不携带完整 EvidenceChain。
2. 若 `epoch_history` 在长运行（>20 epochs）中导致 L1State 序列化超过阈值（可配置，默认 1MB），则引入滑动窗口：只保留最近 N 个 epoch 的 `EpochSummary`，更早的归档到外部存储并替换为 `ArchivedEpochRef`。

---

## 优先级排序（按实现紧迫性）

| 优先级 | GAP | 理由 |
|--------|-----|------|
| **P0** | **GAP-3** | AS 是终止条件的直接消费者。`RankedClaim.axis_hits` 的缺失会阻塞 PA→AS→终止判断的整条链路。必须先在 PA 节点补上 `axis_hits` 的产出逻辑，否则下游全部悬空。 |
| **P1** | **GAP-8** | D2 注入决定了 L2 验证能否利用历史信息。`EvidenceRef` 的设计直接影响外部存储的 schema，越早定下越少返工。且 `EpochSummary` 的结构依赖 GAP-3 的 `AxisCoverage`，所以必须紧跟 GAP-3。 |
| **P2** | **GAP-6** | RB 节点是"锦上添花"的探索扩展机制，不在主循环的关键路径上。且其 `compute_novelty` 依赖 `is_homologous()` 的实际实现（目前未确定），过早固化会导致返工。可在 P0/P1 稳定后再实现。 |