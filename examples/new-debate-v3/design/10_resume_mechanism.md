# 模块名：续跑机制（Resume Mechanism）

<!-- import from 00_shared_types: QuestionFrame, VerifiedClaimFull, VerifiedClaimCompressed, GapSpec, L2Return, EpochDelta -->

## 一句话定位

定义 `EngineSnapshot`（引擎状态快照）的完整结构、`InterventionFile`（用户干预文件）的格式规范，以及 `apply_intervention()` 函数（原子性地将干预合并到快照生成新起点）——使认知引擎能在任意 epoch 边界暂停、接受用户干预、然后从已知良好状态继续运行。

---

## 通俗解释

想象一场马拉松赛事的记录系统。选手（认知引擎）在跑到第 30 公里时暂停休息（epoch 边界）。系统：

1. **保存快照**：把选手当前的体力状况（PA 排名）、已排除的路线（拒绝指纹）、已发现的问题（GapSpec）、历史分段成绩（ranking_history）全部记录下来——这就是 `EngineSnapshot`。

2. **生成"干预建议单"**：告诉教练（用户）现在比赛状态如何，可以做什么调整——这就是 `catalog`。

3. **接受教练指令**：教练填写调整表（`InterventionFile`）——比如"把'生态影响'这个维度的权重降低一点"，或者"注入专家判断来消解某个证据冲突"。

4. **原子性合并**：系统在启动前完成所有检查和合并，全部通过才生成新快照——停车换轮胎，而不是高速换轮胎。

5. **续跑**：从新快照的 epoch N+1 继续，里程表不归零。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: QuestionFrame, GapSpec, VerifiedClaimFull

type SnapshotVersion = "v1";
type InterventionVersion = "v1";

interface EngineSnapshot {
  // 元信息
  snapshot_version: SnapshotVersion;
  problem_id: string;
  created_at: string;    // ISO 8601
  checksum: string;      // SHA-256（对除 checksum 字段外的全部内容）

  // 执行位点
  safe_point: {
    epoch_id: number;    // 单调递增，禁止重置
    stage: "EPOCH_END" | "TERMINATED_BEFORE_AS";
  };

  // Layer 1：问题框架
  frame: QuestionFrame;

  // Layer 2：声明状态
  claims: {
    testable: TestableClaim[];
    regulative: RegulativeIdea[];
  };
  verified_claims: (VerifiedClaimFull | VerifiedClaimCompressed)[];

  // Layer 2：缺口与挑战
  gaps: GapSpec[];
  challenge_trackers: ChallengeTracker[];

  // 负向空间（全量持久化，禁止 LRU 驱逐）
  negative_space: {
    rejection_fingerprints: RejectionFingerprint[];
    by_challenge_index: Record<string, string[]>;  // challenge_id → fp_id[]
  };

  // PA 状态
  pa_state: {
    ranking_history: RankingEntry[];
    consecutive_stable_epochs: number;
    termination_reason?: string;
    termination_config: TerminationConfig;
  };

  // Repair 状态
  repair_state: {
    draft_pool: HypothesisDraft[];
    strategy_per_challenge: Record<string, "STRICT" | "RELAXED" | "ADJACENT">;
  };

  // 干预审计日志
  intervention_log: AppliedIntervention[];
  integrity_status: "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
}

interface RejectionFingerprint {
  fp_id: string;
  epoch: number;
  related_challenge_id: string;
  reason: "HOMOLOGOUS" | "OPEN_TERM_RISK" | "TTL_EXPIRED";
  features: {
    provenance_family: string;
    scope_minhash: string;
    verifier_minhash: string;
    outcome_anchor_hash: string;
    polarity: 1 | -1 | 0;
  };
}

interface ChallengeTracker {
  challenge_id: string;
  description: string;
  current_stage: "STRICT" | "RELAXED" | "ADJACENT";
  consecutive_filtered_epochs: number;
  status: "ACTIVE" | "RETIRED" | "SUSPENDED";
  blocks_termination: boolean;
  retired_reason?: string;
}

interface InterventionFile {
  intervention_version: InterventionVersion;
  target_snapshot_checksum: string;  // 必须匹配目标快照 checksum
  target_epoch_id: number;
  operations: Operation[];
  human_notes?: string;
}

type Operation =
  | ReweightAxis
  | InjectMetaEvidence
  | AddContextToFrame
  | RetireChallenge
  | AdjustTerminationParams
  | DebugOverride;

interface ReweightAxis {
  op: "REWEIGHT_AXIS";
  axis_id: string;
  new_weight: number;
  renormalize_others: boolean;
  all_weights?: Record<string, number>;
}

interface InjectMetaEvidence {
  op: "INJECT_META_EVIDENCE";
  target_gap_id: string;
  evidence_atom: {
    axis_id: string;
    polarity: "PRO" | "CON";
    strength: "AXIOMATIC";           // v1 仅支持公理级（保证单 epoch 消解）
    justification: string;
  };
}

interface AddContextToFrame {
  op: "ADD_CONTEXT_TO_FRAME";
  context_type: "SCOPE_REFINEMENT" | "STAKEHOLDER_SPECIFICATION" | "DOMAIN_CONSTRAINT";
  content: string;
}

interface RetireChallenge {
  op: "RETIRE_CHALLENGE";
  challenge_id: string;
  reason: string;
}

interface AdjustTerminationParams {
  op: "ADJUST_TERMINATION_PARAMS";
  params: {
    min_stable_epochs?: number;
    min_coverage?: number;
  };
}

interface DebugOverride {
  op: "DEBUG_OVERRIDE";
  target: "GAP" | "CHALLENGE_TRACKER" | "TERMINATION_FLAG";
  target_id: string;
  mutation: Record<string, any>;
  i_understand_this_breaks_integrity: true;  // 必须为 true
}

interface AppliedIntervention {
  applied_at_epoch_boundary: number;
  operations: Operation[];
  applied_at: string;
  result: "SUCCESS" | "PARTIAL_REJECT";
  rejected_ops?: { op_index: number; reason: string }[];
}

// 主函数
function apply_intervention(
  snapshot: EngineSnapshot,
  intervention: InterventionFile
): Result<EngineSnapshot, ValidationError[]>;

// 辅助函数
function generate_catalog(snapshot: EngineSnapshot): { markdown: string; json: CatalogJSON };
function generate_intervention_template(snapshot: EngineSnapshot): InterventionFile;
```

---

## 伪代码实现（Python 风格）

```python
RANKING_AFFECTING_OPS = {"REWEIGHT_AXIS", "INJECT_META_EVIDENCE", "RETIRE_CHALLENGE", "DEBUG_OVERRIDE"}


def apply_intervention(
    snapshot: EngineSnapshot,
    intervention: InterventionFile
) -> Result[EngineSnapshot, list[ValidationError]]:
    """
    原子性地将用户干预合并到快照，生成新快照。
    全部通过才应用，任意失败全部拒绝（原子性保证）。
    """

    # ======================================================
    # Phase 1: 前置验证（全部通过才继续）
    # ======================================================
    errors = []

    # 1.1 checksum 和 epoch_id 匹配验证
    if intervention.target_snapshot_checksum != snapshot.checksum:
        errors.append(ValidationError(
            op_index=-1,
            reason=f"干预文件的 checksum 不匹配目标快照"
        ))
        return Err(errors)

    if intervention.target_epoch_id != snapshot.safe_point.epoch_id:
        errors.append(ValidationError(
            op_index=-1,
            reason=f"epoch_id 不匹配：期望 {snapshot.safe_point.epoch_id}，实际 {intervention.target_epoch_id}"
        ))
        return Err(errors)

    # 1.2 逐操作类型检查
    for i, op in enumerate(intervention.operations):
        if op.op == "REWEIGHT_AXIS":
            if not axis_exists(snapshot.frame, op.axis_id):
                errors.append(ValidationError(op_index=i, reason=f"axis_id {op.axis_id} 不存在"))
            if not op.renormalize_others:
                if op.all_weights is None:
                    errors.append(ValidationError(op_index=i, reason="renormalize_others=false 时必须提供 all_weights"))
                elif abs(sum(op.all_weights.values()) - 1.0) > 0.001:
                    errors.append(ValidationError(op_index=i, reason="all_weights 之和不为 1.0"))
            if not (0 < op.new_weight < 1):
                errors.append(ValidationError(op_index=i, reason="new_weight 超出 (0, 1) 范围"))

        elif op.op == "INJECT_META_EVIDENCE":
            if not gap_exists(snapshot.gaps, op.target_gap_id):
                errors.append(ValidationError(op_index=i, reason=f"gap_id {op.target_gap_id} 不存在"))
            if not axis_exists(snapshot.frame, op.evidence_atom.axis_id):
                errors.append(ValidationError(op_index=i, reason=f"axis_id {op.evidence_atom.axis_id} 不存在"))
            if op.evidence_atom.strength != "AXIOMATIC":
                errors.append(ValidationError(op_index=i, reason="v1 仅支持 AXIOMATIC 强度的注入"))

        elif op.op == "RETIRE_CHALLENGE":
            if not challenge_exists(snapshot.challenge_trackers, op.challenge_id):
                errors.append(ValidationError(op_index=i, reason=f"challenge_id {op.challenge_id} 不存在"))

        elif op.op == "ADJUST_TERMINATION_PARAMS":
            if op.params.get("min_stable_epochs") and op.params["min_stable_epochs"] < 1:
                errors.append(ValidationError(op_index=i, reason="min_stable_epochs 必须 >= 1"))

        elif op.op == "DEBUG_OVERRIDE":
            if not op.i_understand_this_breaks_integrity:
                errors.append(ValidationError(op_index=i, reason="必须设置 i_understand_this_breaks_integrity=true"))

    if errors:
        return Err(errors)

    # ======================================================
    # Phase 2: 应用变更（深度复制后修改）
    # ======================================================
    next = deep_clone(snapshot)

    for op in intervention.operations:
        if op.op == "REWEIGHT_AXIS":
            if op.renormalize_others:
                # 按比例缩放其余轴
                old_weight = get_axis_weight(next.frame, op.axis_id)
                scale = (1 - op.new_weight) / (1 - old_weight) if (1 - old_weight) > 1e-9 else 0
                for ax in next.frame.evaluation_axes:
                    if ax.axis_id != op.axis_id:
                        ax.weight *= scale
                set_axis_weight(next.frame, op.axis_id, op.new_weight)
            else:
                for axis_id, weight in op.all_weights.items():
                    set_axis_weight(next.frame, axis_id, weight)

        elif op.op == "INJECT_META_EVIDENCE":
            # 构造公理级 VerifiedClaim 并注入
            meta_claim = create_meta_verified_claim(op, next.safe_point.epoch_id)
            next.verified_claims.append(meta_claim)
            # 立即触发目标 gap 重评估
            target_gap = find_gap(next.gaps, op.target_gap_id)
            reevaluated = reevaluate_gap(target_gap, next.verified_claims, next.claims)
            replace_gap(next.gaps, op.target_gap_id, reevaluated)

        elif op.op == "RETIRE_CHALLENGE":
            tracker = find_tracker(next.challenge_trackers, op.challenge_id)
            tracker.status = "RETIRED"
            tracker.retired_reason = op.reason
            # 触发关联 gap 重评估
            related_gaps = [g for g in next.gaps if op.challenge_id in get_challenge_ids(g)]
            for gap in related_gaps:
                reevaluated = reevaluate_gap(gap, next.verified_claims, next.claims)
                replace_gap(next.gaps, gap.gap_id, reevaluated)

        elif op.op == "ADJUST_TERMINATION_PARAMS":
            if op.params.get("min_stable_epochs"):
                next.pa_state.termination_config.hysteresis_rounds = op.params["min_stable_epochs"]
            if op.params.get("min_coverage"):
                next.pa_state.termination_config.min_coverage = op.params["min_coverage"]

        elif op.op == "ADD_CONTEXT_TO_FRAME":
            next.frame.contextual_notes = next.frame.contextual_notes or []
            next.frame.contextual_notes.append(ContextualNote(
                type=op.context_type,
                content=op.content,
                added_at_epoch=next.safe_point.epoch_id
            ))

        elif op.op == "DEBUG_OVERRIDE":
            target_obj = find_by_type_and_id(next, op.target, op.target_id)
            for key, val in op.mutation.items():
                setattr(target_obj, key, val)
            next.integrity_status = "DEBUG_OVERRIDE_APPLIED"

    # ======================================================
    # Phase 3: 后置不变式检查
    # ======================================================
    weight_sum = sum(ax.weight for ax in next.frame.evaluation_axes)
    if abs(weight_sum - 1.0) > 0.001:
        return Err([ValidationError(op_index=-1, reason=f"权重之和 {weight_sum:.4f} ≠ 1.0")])

    # 验证所有 gap 引用的 claim 和 axis 仍然有效
    for gap in next.gaps:
        if gap.axis_id and not axis_exists(next.frame, gap.axis_id):
            return Err([ValidationError(op_index=-1, reason=f"gap {gap.gap_id} 引用了已删除的 axis")])

    # ======================================================
    # Phase 4: 准备续跑
    # ======================================================
    # 判断是否影响排名
    ranking_affected = any(op.op in RANKING_AFFECTING_OPS for op in intervention.operations)
    if ranking_affected:
        next.pa_state.consecutive_stable_epochs = 0  # 重置稳定计数器

    # Epoch ID 递增（续跑从 N+1 开始）
    next.safe_point.epoch_id += 1
    next.safe_point.stage = "EPOCH_END"

    # 记录干预日志
    next.intervention_log.append(AppliedIntervention(
        applied_at_epoch_boundary=snapshot.safe_point.epoch_id,
        operations=intervention.operations,
        applied_at=now_iso8601(),
        result="SUCCESS"
    ))

    # 重算 checksum
    next.checksum = sha256(serialize_without_checksum(next))

    return Ok(next)
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-RM-01 | `rejection_fingerprints` 全量持久化，禁止 LRU 驱逐（除非按 challenge 生命周期归档） | 快照持久化策略 |
| INV-RM-02 | `epoch_id` 在续跑时单调递增，禁止重置为 0（否则 epsilon 的 t-分布自由度失效） | `apply_intervention` Phase 4 |
| INV-RM-03 | 干预合并原子性：所有操作全部通过才应用，任意失败全部拒绝 | Phase 1 + 2 的顺序保证 |
| INV-RM-04 | `INJECT_META_EVIDENCE` 的 `strength` 必须为 `AXIOMATIC`（保证单 epoch 消解） | Phase 1 验证 |
| INV-RM-05 | 用户干预不能直接覆写 `blocks_termination` 布尔值；必须通过 `INJECT_META_EVIDENCE` 让系统重评估 | 接口设计（无此操作类型） |
| INV-RM-06 | `DEBUG_OVERRIDE` 应用后 `integrity_status` 永久标记为 `"DEBUG_OVERRIDE_APPLIED"`，AS 节点输出中必须警告 | Phase 2 强制 |
| INV-RM-07 | 影响排名的操作（`REWEIGHT_AXIS` 等）必须重置 `consecutive_stable_epochs = 0` | Phase 4 |
| INV-RM-08 | `target_snapshot_checksum` 必须匹配，防止对错快照操作 | Phase 1 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**：碳排放交易机制，Epoch 7 暂停，用户干预后续跑

```
[Epoch 7 结束，系统暂停]

EngineSnapshot(ep7):
  safe_point: { epoch_id: 7, stage: "EPOCH_END" }
  gaps: [
    gap-007: { blocks_termination: true, kind: "EVIDENCE_CONFLICT",
               description: "ax_capacity 轴上 claim-009 和 claim-011 存在极性冲突" }
  ]
  pa_state: { consecutive_stable_epochs: 3, ranking_history: [...7 entries] }
  checksum: "a3f8c1..."

generate_catalog(snapshot_ep7):
  → 输出 catalog_ep7.md 供用户阅读：
    "阻塞 Gap: gap-007 (EVIDENCE_CONFLICT)
     建议操作: 注入专家判断以消解冲突
     当前排名: [claim-009, claim-007, claim-011]"

[用户编辑 intervention_ep7.yaml]:
  target_snapshot_checksum: "a3f8c1..."
  target_epoch_id: 7
  operations:
    - op: INJECT_META_EVIDENCE
      target_gap_id: gap-007
      evidence_atom:
        axis_id: ax_capacity
        polarity: PRO
        strength: AXIOMATIC
        justification: "环评专家组确认：在温带城市场景下，能力调整系数(CDR)的应用范围不包含高原地区，消解争议"
    - op: REWEIGHT_AXIS
      axis_id: ax_implement
      new_weight: 0.20
      renormalize_others: true
  human_notes: "EIA-2024-0847"

apply_intervention(snapshot_ep7, intervention):

  Phase 1: 验证
    checksum ✓, epoch_id=7 ✓
    Op[0]: gap-007 存在 ✓, ax_capacity 存在 ✓, strength=AXIOMATIC ✓
    Op[1]: ax_implement 存在 ✓, new_weight=0.20, renormalize=true ✓
    → 全部通过

  Phase 2: 应用
    Op[0]: 注入公理级证据
      meta_claim: { axis_scores: { ax_capacity: 0.95 }, strength: "AXIOMATIC" }
      reevaluate_gap(gap-007):
        公理级 PRO 证据消解了 CAUSAL_STATISTICAL CON → gap-007.blocks_termination → false
    Op[1]: 调整权重
      ax_implement: 0.25 → 0.20
      其余三轴按比例缩放：0.25 → 0.267

  Phase 3: 后置检查
    权重之和 = 0.267×3 + 0.20 = 1.001 → 取整后 ≈ 1.0 ✓
    所有 gap 引用完整性 ✓

  Phase 4: 续跑准备
    ranking_affecting: true → consecutive_stable_epochs: 3 → 0（重置）
    epoch_id: 7 → 8
    checksum: "a3f8c1..." → "b7e2d4..."

返回 EngineSnapshot(ep8):
  safe_point: { epoch_id: 8, stage: "EPOCH_END" }
  gaps: [gap-007: { blocks_termination: false }]  ← 已消解
  pa_state: { consecutive_stable_epochs: 0 }
  checksum: "b7e2d4..."

[Epoch 8 正常启动，gap-007 不再阻塞，系统在 2 轮后达到终止条件]
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-3~~** → **已裁定** ✅（完整裁定见 `11_layer1_orchestrator.md`）
> - 裁定结论：`AnswerSeed` 是 tagged union（`ANSWER_SEED | ANSWER_SEED_SKIPPED`），`assemble_answer_seed(state: L1State): AnswerSeed` 为唯一签名（传入 `L1State` 而非 `null`），coverage 二值化，`ANSWER_SEED_SKIPPED` variant 替代原来的 `null` 返回。
> - 关键规格：`AnswerSeedProduced { kind: "ANSWER_SEED"; top_claims: RankedClaim[]; coverage_report: Record<AxisId, AxisCoverage>; integrity_status; termination_reason; provenance }` 和 `AnswerSeedSkipped { kind: "ANSWER_SEED_SKIPPED"; skipped_because: "TERMINATED_BEFORE_AS" | "INTERNAL_ERROR" | "NO_SURVIVING_CLAIMS" }`；`EngineSnapshot.safe_point.stage = "TERMINATED_BEFORE_AS"` 表示 PA 已判终止但 AS 未执行。
> - 裁定来源：`gap_missing_nodes_debate_summary.md`
