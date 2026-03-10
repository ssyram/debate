# 模块名：共享类型定义（Shared Types）

> 本文件是整个 v3 认知引擎的"类型中枢"。所有跨模块共用的类型定义在此处唯一化。其他模块通过注释 `# import from 00_shared_types` 引用，**禁止在其他文件中重新定义这些类型**，以防止版本漂移。

---

## 基础 ID 类型

```typescript
type ProblemId = string;
type DraftId   = string;
type ClaimId   = string;
type EvidenceId = string;
type AxisId    = string;
type GapId     = string;
type EpochId   = number;   // 单调递增，禁止重置为 0
```

---

## QuestionFrame（问题框架）

由 `normalize_question()` 产出，是整个引擎的"宪法"。

```typescript
type CategoryErrorTag =
  | "SELF_REFERENCE_PARADOX"
  | "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY"
  | "UNFALSIFIABLE_VALUE_ASSERTION"
  | "SCOPE_UNBOUNDED";

type FalsifierIndependence = "INDEPENDENT" | "STAKEHOLDER_DERIVED";

interface RegulativeAxis {
  axis_id: AxisId;
  label: string;
  mode: "regulative";               // 字面量类型，编译期强制；禁止 "constitutive"
  weight: number;                   // 归一化权重，所有轴之和 = 1.0
  epsilon: number;                  // 测量不确定性，由 scoring_epsilon 模块维护
  falsifier: string;                // 该轴的可证伪条件
  falsifier_independence: FalsifierIndependence;
  // INDEPENDENT: 该 falsifier 不依赖任何特定利益方立场，进入 MB 内部层
  // STAKEHOLDER_DERIVED: 降级为经验层
}

interface QuestionFrame {
  problem_id: ProblemId;
  scope: string;
  evaluation_axes: [RegulativeAxis, ...RegulativeAxis[]]; // 非空元组，编译期保证 length >= 1
  open_terms: string[];             // 语义未绑定的词项（单调递减）
  stakeholders: string[];
  excluded_forms: CategoryErrorTag[];
  axis_rulebook?: Record<AxisId, AxisRulebook>; // 可选的领域特定证据折算规则
  contextual_notes?: ContextualNote[];          // 用户干预追加的上下文
}

interface ContextualNote {
  type: "SCOPE_REFINEMENT" | "STAKEHOLDER_SPECIFICATION" | "DOMAIN_CONSTRAINT";
  content: string;
  added_at_epoch: EpochId;
}
```

---

## HypothesisDraft（假设草稿）

MB 和 repair() 共享的统一消费类型。

```typescript
type DraftSource = "MB" | "REPAIR";

type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT"
  | "GAP_REPAIR"
  | "SCHEMA_REPAIR"
  | "OTHER";

type EpistemicTier =
  | "INTERNAL_AXIS"   // MB: 来自独立 falsifier 的评价轴冲突
  | "EMPIRICAL"       // MB: 经验性可检验分歧
  | "L2_FAILURE"      // Repair: 来自 Layer 2 验证失败
  | "STRUCTURAL";     // Repair: 结构性 schema 问题

interface TensionSource {
  kind: TensionKind;
  tier: EpistemicTier;
  evidence_ref: string[];  // MB: 原生证据引用; Repair: 从 challenge 上下文提取，允许 []
  note: string;
}

interface Provenance {
  source: DraftSource;
  epoch: EpochId;
  // MB 特有（Repair 时为 undefined）
  ttl?: number;
  // Repair 特有（MB 时为 undefined）
  source_gap_id?: GapId;
  source_challenge_id?: string;
  repair_stage?: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
}

interface HypothesisDraft {
  draft_id: DraftId;
  problem_id: ProblemId;           // 必填。MB 原生; Repair 由 L1 调度层注入
  claim_sketch: string;
  scope_ref: string[];             // 必填且禁止空数组
  verifier_hint: string[];         // 统一为数组
  open_term_risk: string[];        // 可为 []
  tension_source: TensionSource;
  provenance: Provenance;
}
```

---

## GapSpec（知识缺口规格）

> **~~GAP-2~~** → **已裁定** ✅
> - 裁定结论：采纳 Tagged Union 按来源域分离（`REPAIR` / `TERMINATION`），L2 只产 REPAIR 类 gap，PA 只产 TERMINATION 类 gap，由类型系统在创建点强制约束，路由为纯函数 `dispatch_gap`。
> - 关键规格：`GapKind = { type: "REPAIR"; subkind: RepairSubKind; ... } | { type: "TERMINATION"; subkind: TerminationSubKind; ... }`；工厂函数 `create_repair_gap` / `create_termination_gap` 编译期强制 kind.type 固定。合并是操作（`merge_gaps`），不是类型扩展。
> - 可推翻条件：若出现第三类 gap 来源（如用户手动注入），需扩展 `GapKind.type` 枚举并同时提供对应工厂函数和 `dispatch_gap` 分支；若 stakeholder 权重变化导致 gap 重新解释，正确做法是 `GAP_CLOSE` 旧 + `GAP_OPEN` 新，而非原地修改 `kind`。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`
>
> **与文档建议对齐说明**：本文件原方案已将 kind 拆分为 `RepairGapKind | TerminationGapKind` 联合类型，与裁定方向一致，但裁定进一步要求改为 Tagged Union（`{ type: "REPAIR"; subkind: RepairSubKind }` 形式）而非字符串联合，创建点必须有工厂函数约束，且 `GapSpec` 中不再保留 `evidence_summary` 字段。以下类型定义已按裁定更新。

```typescript
// ── GapSpec 权威定义（裁定版）──
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

type GapKind =
  | { type: "REPAIR"; subkind: RepairSubKind; source_epoch: EpochId }
  | { type: "TERMINATION"; subkind: TerminationSubKind; evaluation_axis: AxisId };

interface GapSpec {
  gap_id: GapId;
  kind: GapKind;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  description: string;
  blocks_termination: boolean;     // TERMINATION gaps: 固定 true；REPAIR gaps: 可配置
  created_epoch: EpochId;
  related_claim_ids: ClaimId[];
}

// ── 创建约束（编译期强制）──
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

// ── 路由（纯函数）──
function dispatch_gap(gap: GapSpec): "RB_NODE" | "PA_NODE" {
  switch (gap.kind.type) {
    case "REPAIR": return "RB_NODE";
    case "TERMINATION": return "PA_NODE";
  }
}

// ── 合并协议（合并是操作，不是类型）──
function merge_gaps(
  primary_id: GapId,
  secondary_id: GapId,
  state: L1State
): { updated_state: L1State; closed_gap_id: GapId; merge_reason: string };
// secondary gap 收到 GAP_CLOSE { resolution: "MERGED" }
// primary gap 的 related_claim_ids 合并 secondary 的
```

---

## EvidenceAtom 与 EvidenceChain（证据原子与证据链）

```typescript
type StrengthTier =
  | "ANECDOTAL"           // 轶事/个人经验
  | "CORRELATIONAL"       // 相关性研究
  | "CAUSAL_STATISTICAL"  // 因果统计/RCT
  | "AXIOMATIC";          // 公理/定义性真理

type ScoreProvenance =
  | "RULE_ONLY"
  | "LLM_EXTRACTED_RULE_SCORED"
  | "DEFAULT_TIER";

type EvidenceRef =
  | { kind: "EXTERNAL_DOC"; doc_id: string; span_hash: string; offsets: [number, number] }
  | { kind: "INTERNAL_CLAIM"; claim_id: ClaimId; claim_epoch: EpochId; required_status: "VERIFIED" | "DEFENSIBLE" };

interface EvidenceAtom {
  evidence_id: EvidenceId;
  ref: EvidenceRef;
  target_claim_id: ClaimId;
  axis_id: AxisId;              // 一个 atom 只挂一个 axis（禁止多轴映射）
  polarity: "PRO" | "CON";
  strength_tier: StrengthTier;
  llm_confidence: number;       // ∈ [0, 1]
  extractor: "RULE" | "LLM";
  validated: true;
}

interface AxisScoreEntry {
  axis_id: AxisId;
  score: number;          // ∈ [0, 1]
  epsilon: number;        // 测量不确定性
  provenance: ScoreProvenance;
  evidence_ids: EvidenceId[];
  aggregation_detail: {
    raw_pro: number;
    raw_con: number;
    pro_count: number;
    con_count: number;
    sigmoid_k: number;
    sigmoid_midpoint: number;
  };
}

interface EvidenceChain {
  claim_id: ClaimId;
  epoch_id: EpochId;
  atoms: EvidenceAtom[];
  axis_scores: AxisScoreEntry[];
  integrity: {
    claim_alignment_verified: boolean;
    dependency_status_verified: boolean;
    score_evidence_alignment_verified: boolean;
    acyclicity_verified: boolean;
  };
}
```

---

## VerifiedClaim（已验证命题）

> **~~GAP-7~~** → **已裁定** ✅（完整裁定见 `09_context_compression.md`）
> - 裁定结论：`apply_delta` 保持纯函数只入库 `VerifiedClaimFull`，压缩为异步后台任务，压缩失败不影响 claim 状态；业务代码通过 accessor `get_evidence` 访问，accessor 返回显式可用性标记。
> - 关键规格：`type VerifiedClaim = VerifiedClaimFull | VerifiedClaimCompressed`；accessor 返回 `EvidenceAccess = { available: true; atoms; source: "FULL"|"REHYDRATED" } | { available: false; summary; atom_count; hash }`；压缩由 `enqueue_compression` + `apply_compression_result` 异步两步完成。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`

```typescript
// 全量形态（压缩前）
interface VerifiedClaimFull {
  claim_id: ClaimId;
  source_draft_id: DraftId;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;              // ∈ [0, 1]
  axis_scores: Partial<Record<AxisId, number>>;
  evidence_chain: EvidenceAtom[];     // 全量证据原子
}

// 压缩后形态（context_compression 执行后）
interface CompressedEvidenceProfile {
  axis_id: AxisId;
  counts_pro: Record<StrengthTier, number>;
  counts_con: Record<StrengthTier, number>;
  watermarks_pro: Record<StrengthTier, EvidenceAtom | null>;
  watermarks_con: Record<StrengthTier, EvidenceAtom | null>;
  pinned_conflicts: PinnedConflict[];
  archive_ref: ArchiveRef | null;
  strength_rulebook_version: string;
  covered_epoch_range: [number, number];
  total_atom_count: number;
}

interface PinnedConflict {
  gap_spec_id: string;
  gap_kind: "EVIDENCE_CONFLICT" | "UNRESOLVED_DEFEATER";
  pro_atom: EvidenceAtom;
  con_atom: EvidenceAtom;
  detected_epoch: EpochId;
  resolved: boolean;
}

interface ArchiveRef {
  storage_uri: string;
  blake3_hash: string;
  byte_len: number;
}

interface VerifiedClaimCompressed {
  claim_id: ClaimId;
  source_draft_id: DraftId;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<AxisId, number>>;
  evidence_profiles: Record<AxisId, CompressedEvidenceProfile>;
  active_window: EvidenceAtom[];   // 热区：最近 N 个 epoch 的原始 Atom
}
```

---

## L2Return / EpochDelta（Layer 2 返回结构）

> **~~GAP-1~~** → **已裁定** ✅（完整裁定见 `07_repair_strategy.md`）
> - 裁定结论：采纳增量事件流版本（`deltas: EpochDelta[]`）为唯一权威边界，`evidence_summary` 从 L2Return 永久移除；上下文投影由 L1 侧纯函数 `project_evidence_summary` 完成，禁止 LLM 调用；`EVIDENCE_DIGEST_SUGGESTED` 作为可选增量事件回流。
> - 关键规格：`L2Return { epoch_id; deltas: EpochDelta[]; size_bytes }` + 新增 `EpochDelta` variant `EVIDENCE_DIGEST_SUGGESTED`；投影函数签名 `project_evidence_summary(state: L1State, query: EvidenceQuery): Result<EvidenceSummary, EvidenceProjectionError>`。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`
>
> **与文档建议对齐说明**：本文件原方案已采用增量事件结构，与裁定完全一致。裁定额外增加了 `EVIDENCE_DIGEST_SUGGESTED` variant 和 L1 侧投影函数规格，已在下方 `EpochDelta` 类型中补充该 variant。

```typescript
type EpochDelta =
  | { kind: "GAP_OPEN"; gap: GapSpec }
  | { kind: "GAP_PATCH"; gap_id: GapId; patch: JsonPatch }     // RFC 6902
  | { kind: "GAP_CLOSE"; gap_id: GapId; resolution: "RESOLVED" | "SUSPENDED" | "MERGED" | "INVALIDATED" }
  | { kind: "SCHEMA_CHALLENGE_NEW"; ch: SchemaChallengeNotice }
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaimFull }
  | { kind: "CLAIM_SUSPENDED"; claim_id: ClaimId; reason: string }
  | { kind: "EVIDENCE_DIGEST_SUGGESTED"; gap_id: GapId; text: string; model: string }; // 裁定新增：L2 主动提供的语义摘要（可选）

interface L2Return {
  epoch_id: EpochId;
  deltas: EpochDelta[];
  size_bytes: number;   // 超过 32KB 时 L1 拒收，要求 L2 合并后重发
}

interface SchemaChallengeNotice {
  challenge_id: string;
  trigger: "REPLAY_REGRESSION" | "COVERAGE_GAP" | "ANOMALY";
  suggested_dimension?: string;
  description: string;
}
```

---

## TestableClaim（可检验命题）

```typescript
interface TestableClaim {
  claim_id: ClaimId;
  source_draft_id: DraftId;
  falsifiable_statement: string;
  required_evidence_types: string[];
  verification_protocol: string;
  scope_boundary: string[];
  status?: "PENDING" | "VERIFIED" | "DEFENSIBLE" | "REJECTED" | "SUSPENDED";
}
```

---

## RegulativeIdea（调节性理念）

CC 编译失败时的输出，不进入 Layer 2 验证，进入 RB 节点。

```typescript
interface RegulativeIdea {
  idea_id: string;
  source_draft_id: DraftId;
  claim_sketch: string;
  no_empirical_bridge_reason: string;
  // 供 RB 节点用于广度探索的参考
}
```

---

## AxisRulebook（证据折算规则）

```typescript
interface AxisRulebook {
  tier_score: Record<StrengthTier, number>;
  tier_epsilon: Record<StrengthTier, number>;
  sigmoid_k?: number;
  sigmoid_midpoint?: number;
}

// Layer 2 内置默认值（当 QuestionFrame 未提供领域特定规则时使用）
const DEFAULT_RULEBOOK: AxisRulebook = {
  tier_score: { ANECDOTAL: 0.15, CORRELATIONAL: 0.40, CAUSAL_STATISTICAL: 0.75, AXIOMATIC: 0.95 },
  tier_epsilon: { ANECDOTAL: 0.12, CORRELATIONAL: 0.08, CAUSAL_STATISTICAL: 0.04, AXIOMATIC: 0.01 },
  sigmoid_k: 2,
  sigmoid_midpoint: 0,
};
```

---

## RankedClaim 与 TerminationConfig

```typescript
interface RankedClaim {
  claim_id: ClaimId;
  score: number;     // ∈ [0, 1]，由 PA 节点的加权投影公式计算
  coverage: number;  // ∈ [0, 1]，已覆盖轴的权重质量之和
}

interface TerminationConfig {
  top_k: number;
  min_coverage: number;
  hysteresis_rounds: number;  // 默认 2
  // score_alpha: 评分缩放因子（注意：区别于 ema_alpha）
  score_alpha: number;        // 默认 1.0，可离线校准
}
```

---

## 已裁定缺口汇总（本文件涉及部分）

> **~~GAP-1~~** → **已裁定** ✅：`L2Return` 两版本冲突已在本文件中通过采用增量事件结构解决（并补充 `EVIDENCE_DIGEST_SUGGESTED` variant）。repair_strategy 模块必须更新以读取 `L1State`（经 `applyDelta` 吸收后），而非直接读旧版 `L2Return`。裁定来源：`gap_type_consolidation_debate_summary.md`

> **~~GAP-2~~** → **已裁定** ✅：`GapSpec.kind` 已在本文件中升级为 Tagged Union（`{ type: "REPAIR" | "TERMINATION"; subkind; ... }`），并增加 `create_repair_gap` / `create_termination_gap` 工厂函数和 `dispatch_gap` 路由函数。所有模块必须通过工厂函数创建 gap，不能混用。裁定来源：`gap_type_consolidation_debate_summary.md`

> **~~GAP-4~~** → **已裁定** ✅：`HypothesisDraft` 的统一定义以本文件为准。repair_strategy 中旧版缺少 `problem_id`、`open_term_risk`，`verifier_hint` 为单 string 非数组——这些均已在本文件的统一定义中修正。裁定来源：`gap_type_consolidation_debate_summary.md`（GAP-4 实为评估轴冻结裁定，不影响本文件的 HypothesisDraft 定义，本条保持原文档约束不变）
