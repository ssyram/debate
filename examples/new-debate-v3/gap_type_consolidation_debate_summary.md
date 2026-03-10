# v3 认知引擎类型冲突裁定：GAP-1/2/4/5/7 权威定义之争 裁判总结

> 2026-03-10T15:28:51.516814

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