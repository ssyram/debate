# 模块名：Layer 1 调度器（Layer 1 Orchestrator）

<!-- import from all modules -->

## 一句话定位

实现 Layer 1 的 7 节点状态机（QN → MB → CC → D2 → PA → RB → AS），管理每个 epoch 的完整调度循环，处理 Layer 2 返回（`L2Return`）的增量吸收（`applyDelta`），协调续跑机制（`EngineSnapshot`）——是整个认知引擎的"大脑皮层"，所有模块的胶水层。

---

## 通俗解释

想象一个大型法庭审判流程的主任法官（调度器）。他不亲自审查每一份证据，而是协调所有角色：
- 指示接案员（QN）处理委托
- 指示助手（MB）生成假说
- 指示文书室（CC）将假说变成正式指控
- 委托给专家陪审团（Layer 2 / D2）进行深度审查
- 听取审查报告（L2Return），更新案件状态（applyDelta）
- 指示裁判委员会（PA）做出阶段性评估
- 如果有问题（GapSpec），指示维修工（RB/repair）修复
- 如果满足终止条件，指示书记员（AS）整理最终报告

整个流程是一个循环（epoch 循环），每轮结束时可以暂停（保存快照），接受外部干预后再续跑。

---

## 接口定义（TypeScript 类型）

```typescript
// Layer 1 的完整状态
interface L1State {
  frame: QuestionFrame;
  epoch_id: number;                  // 单调递增

  // 草稿池
  draft_pool: HypothesisDraft[];

  // 声明状态
  testable_claims: TestableClaim[];
  regulative_ideas: RegulativeIdea[];
  verified_claims: (VerifiedClaimFull | VerifiedClaimCompressed)[];

  // 缺口与挑战
  active_gaps: GapSpec[];
  challenge_trackers: ChallengeTracker[];

  // Repair 状态
  negative_space: {
    rejection_fingerprints: RejectionFingerprint[];
    by_challenge_index: Record<string, string[]>;
  };
  strategy_per_challenge: Record<string, RepairStage>;

  // PA 状态
  pa_state: PAState;

  // Epsilon 状态（每轴）
  epsilon_states: Record<string, EpsilonState>;
}

// 7 节点枚举
type Node = "QN" | "MB" | "CC" | "D2" | "PA" | "RB" | "AS";

// 每个节点的状态机状态
type NodeStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED" | "SUSPENDED";

// Layer 2 返回处理
function apply_delta(state: L1State, delta: EpochDelta): Result<L1State, ApplyError>;
function apply_l2_return(state: L1State, l2return: L2Return): Result<L1State, ApplyError[]>;

// 主调度入口
function run_epoch(state: L1State, config: EngineConfig): Result<L1State, EngineError>;

// AnswerSeed（AS 节点输出）
interface AnswerSeed {
  problem_id: string;
  epoch_id: number;
  top_claims: RankedClaim[];
  coverage_report: Record<string, number>;  // axis_id → coverage
  integrity_status: "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
  termination_reason: string;
}

function assemble_answer_seed(pa_state: PAState, frame: QuestionFrame): AnswerSeed;
```

---

## 伪代码实现（Python 风格）

```python
class Layer1Orchestrator:
    """Layer 1 调度器：管理 7 节点状态机的完整调度循环"""

    def __init__(self, config: EngineConfig):
        self.config = config

    # ======================================================
    # 主调度入口：运行单个 epoch
    # ======================================================
    def run_epoch(self, state: L1State) -> Result[L1State, EngineError]:
        """
        执行一个完整的 epoch 循环。
        节点顺序：QN → MB → CC → D2 → PA → RB（有 Gap 时）→ AS（终止时）
        """
        epoch = state.epoch_id
        log(f"Epoch {epoch} 开始")

        # ======================================================
        # 节点 1: QN（问题摄取）
        # 仅在第一个 epoch 或收到 RefinementSignal 时执行
        # ======================================================
        if epoch == 0 or has_refinement_signals(state):
            signals = collect_refinement_signals(state)
            qn_result = normalize_question(
                ProblemStatement(raw_question=state.frame.scope),
                refinements=signals
            )

            if not qn_result.ok:
                error = qn_result.error
                if error.code == "CATEGORY_ERROR":
                    return Err(EngineError(
                        node="QN",
                        code="FATAL_CATEGORY_ERROR",
                        detail=str(error)
                    ))
                elif error.code == "INSUFFICIENT_FRAME":
                    # 可恢复：等待用户补充信息
                    return Err(EngineError(
                        node="QN",
                        code="RECOVERABLE_FRAME_ERROR",
                        detail=str(error),
                        refinement_hints=error.repair_advice
                    ))
            else:
                state = dataclasses.replace(state, frame=qn_result.value)

        # ======================================================
        # 节点 2: MB（宏观广度）
        # 每 epoch 生成新一批假说草稿
        # ======================================================
        mb_result = macro_breadth(
            frame=state.frame,
            config=self.config.mb_config,
            external_positions=state.frame.contextual_notes  # 用户注入的外部立场
        )

        if not mb_result.ok:
            error = mb_result.error
            if error.code == "OPEN_TERM_SATURATION":
                # 触发 QN 精炼回路（下一 epoch 重新进入 QN）
                add_refinement_signals(state, error.saturated_terms, epoch)
            elif error.code == "NO_TENSION_FOUND":
                # 无法生成假说：暂停，等待外部立场注入
                return Err(EngineError(node="MB", code="NO_TENSION_FOUND", detail=str(error)))
            # ALL_DRAFTS_HOMOLOGOUS：也暂停，等待外部注入
            new_drafts = []
        else:
            new_drafts = mb_result.value

        # 合并到草稿池，去重
        merged_drafts = deduplicate_drafts(state.draft_pool + new_drafts)
        state = dataclasses.replace(state, draft_pool=merged_drafts)

        # ======================================================
        # 节点 3: CC（声明编译器）
        # 对所有草稿逐个编译
        # ======================================================
        testable_claims = list(state.testable_claims)
        regulative_ideas = list(state.regulative_ideas)
        refinement_signals = []

        for draft in state.draft_pool:
            cc_result = clarity_compile(draft, state.frame)
            output = route_compile_result(cc_result, draft)

            if output.kind == "TESTABLE_CLAIM":
                if not already_compiled(output.claim, testable_claims):
                    testable_claims.append(output.claim)

            elif output.kind == "REGULATIVE_IDEA":
                regulative_ideas.append(output.idea)

            elif output.kind == "REFINEMENT_NEEDED":
                refinement_signals.append(output.signal)

        # 将精炼信号存入状态，供下一 epoch 的 QN 使用
        state = dataclasses.replace(
            state,
            testable_claims=testable_claims,
            regulative_ideas=regulative_ideas
        )
        if refinement_signals:
            store_refinement_signals(state, refinement_signals)

        # ======================================================
        # 节点 4: D2（Layer 2 分派与验证）
        # 将 TestableClaim 送入 Layer 2 进行证据验证
        # ======================================================
        pending_claims = [c for c in testable_claims if c.status == "PENDING"]

        if pending_claims:
            l2_result = run_layer2_batch(
                claims=pending_claims,
                rulebook=get_rulebook(state.frame),
                epoch_id=epoch
            )

            # 接收 L2Return（增量事件格式）
            if l2_result.ok:
                l2return = l2_result.value
                # 检查 L2Return 大小（超过 32KB 时拒收）
                if l2return.size_bytes > 32 * 1024:
                    return Err(EngineError(
                        node="D2",
                        code="L2RETURN_TOO_LARGE",
                        hint="COALESCE_PATCHES"
                    ))

                # 逐个应用增量事件
                apply_result = self.apply_l2_return(state, l2return)
                if not apply_result.ok:
                    return Err(EngineError(node="D2", code="APPLY_DELTA_FAILED", detail=str(apply_result.error)))
                state = apply_result.value

            else:
                return Err(EngineError(node="D2", code="LAYER2_FAILED", detail=str(l2_result.error)))

        # ======================================================
        # 节点 5: PA（评分与终止判定）
        # ======================================================
        new_rankings = compute_rankings(
            verified_claims=state.verified_claims,
            frame=state.frame,
            epsilon_states=state.epsilon_states
        )

        pa_state = update_pa_state(state.pa_state, new_rankings, epoch)

        # 更新 epsilon 状态
        new_epsilon_states = update_all_epsilons(
            state.epsilon_states,
            current_axis_scores=extract_current_scores(state.verified_claims, new_rankings),
            prev_axis_scores=extract_prev_scores(state.pa_state)
        )

        state = dataclasses.replace(
            state,
            pa_state=pa_state,
            epsilon_states=new_epsilon_states
        )

        # 检查是否应该终止
        termination = check_termination(pa_state, state.active_gaps, epoch)

        if termination.should_terminate:
            # ======================================================
            # 节点 7: AS（组装最终答案）
            # ======================================================
            answer_seed = assemble_answer_seed(pa_state, state.frame)
            log(f"Epoch {epoch}: 终止条件满足，输出 AnswerSeed")
            log(f"终止原因：{termination.termination_reason}")

            # 标记状态为终止（但不退出循环，由调用方决定是否续跑）
            state = dataclasses.replace(state, epoch_id=epoch + 1)
            state.answer_seed = answer_seed  # 附加到状态
            return Ok(state)

        # ======================================================
        # 节点 6: RB（修复广度）
        # 对每个阻塞性 GapSpec 执行修复
        # ======================================================
        blocking_gaps = [g for g in state.active_gaps if g.blocks_termination]

        new_repair_drafts = []
        for gap in blocking_gaps:
            stage = state.strategy_per_challenge.get(gap.gap_id, "STRICT")
            constraints = get_constraints_for_gap(state, gap.gap_id)

            repair_input = RepairInput(
                gap=gap,
                current_stage=stage,
                l1_state=state,     # 经 applyDelta 吸收后的状态
                negative_constraints=constraints,
                max_attempts_per_stage=8,
                consecutive_unsat_limit=5
            )
            repair_output = repair(repair_input)

            if repair_output.action == "DRAFT_GENERATED":
                new_repair_drafts.append(repair_output.draft)

            elif repair_output.action == "STAGE_UPGRADED":
                state.strategy_per_challenge[gap.gap_id] = repair_output.next_stage
                log(f"gap {gap.gap_id}: 修复阶段升级 → {repair_output.next_stage}")

            elif repair_output.action == "SUSPENDED":
                suspend_gap(state, gap.gap_id)
                log(f"gap {gap.gap_id}: 修复空间耗尽，进入 Suspended")

            elif repair_output.action == "EXHAUSTED":
                log(f"gap {gap.gap_id}: 所有阶段已穷尽，标记为 EXHAUSTED")

            # 记录新的失败约束
            update_negative_constraints(state, gap.gap_id, repair_output.new_constraints)

        # RegulativeIdea 也进入 RB 节点（广度探索）
        idea_drafts = repair_breadth(regulative_ideas, state.frame)

        # 合并新草稿到草稿池
        all_new = new_repair_drafts + idea_drafts
        merged_drafts = deduplicate_drafts(state.draft_pool + all_new)
        state = dataclasses.replace(state, draft_pool=merged_drafts, epoch_id=epoch + 1)

        log(f"Epoch {epoch} 结束，epoch_id → {epoch + 1}")
        return Ok(state)

    # ======================================================
    # applyDelta：增量吸收 L2Return 的核心函数
    # ======================================================
    def apply_l2_return(
        self,
        state: L1State,
        l2return: L2Return
    ) -> Result[L1State, list[ApplyError]]:
        """纯函数：逐个应用 EpochDelta，失败时保留原状态"""
        errors = []
        current_state = state

        for delta in l2return.deltas:
            result = apply_delta(current_state, delta)
            if result.ok:
                current_state = result.value
            else:
                errors.append(result.error)
                # 不终止：继续应用后续 delta（局部失败不影响整体）
                # 但记录错误，供调用方决策

        if errors:
            return Err(errors)
        return Ok(current_state)


def apply_delta(state: L1State, delta: EpochDelta) -> Result[L1State, ApplyError]:
    """纯函数：应用单个 EpochDelta 到 L1State"""
    if delta.kind == "GAP_OPEN":
        new_gaps = state.active_gaps + [delta.gap]
        return Ok(dataclasses.replace(state, active_gaps=new_gaps))

    elif delta.kind == "GAP_PATCH":
        target = find_gap(state.active_gaps, delta.gap_id)
        if target is None:
            return Err(ApplyError(f"GAP_PATCH: gap {delta.gap_id} 不存在"))
        patched = apply_json_patch(target, delta.patch)
        new_gaps = [patched if g.gap_id == delta.gap_id else g for g in state.active_gaps]
        return Ok(dataclasses.replace(state, active_gaps=new_gaps))

    elif delta.kind == "GAP_CLOSE":
        new_gaps = [g for g in state.active_gaps if g.gap_id != delta.gap_id]
        # 可选：将已关闭的 gap 移入 closed_gaps 用于审计
        return Ok(dataclasses.replace(state, active_gaps=new_gaps))

    elif delta.kind == "CLAIM_VERIFIED":
        new_claims = state.verified_claims + [delta.claim]
        # 同时更新 testable_claims 的状态
        updated_testable = [
            dataclasses.replace(c, status=delta.claim.status)
            if c.claim_id == delta.claim.claim_id else c
            for c in state.testable_claims
        ]
        return Ok(dataclasses.replace(
            state,
            verified_claims=new_claims,
            testable_claims=updated_testable
        ))

    elif delta.kind == "CLAIM_SUSPENDED":
        updated_testable = [
            dataclasses.replace(c, status="SUSPENDED")
            if c.claim_id == delta.claim_id else c
            for c in state.testable_claims
        ]
        return Ok(dataclasses.replace(state, testable_claims=updated_testable))

    elif delta.kind == "SCHEMA_CHALLENGE_NEW":
        new_tracker = ChallengeTracker(
            challenge_id=delta.ch.challenge_id,
            description=delta.ch.description,
            current_stage="STRICT",
            consecutive_filtered_epochs=0,
            status="ACTIVE",
            blocks_termination=True
        )
        new_trackers = state.challenge_trackers + [new_tracker]
        return Ok(dataclasses.replace(state, challenge_trackers=new_trackers))

    else:
        return Err(ApplyError(f"未知的 EpochDelta 类型：{delta.kind}"))


# ======================================================
# RB 节点：RepairBreadth（供 RegulativeIdea 使用）
# ======================================================
def repair_breadth(
    ideas: list[RegulativeIdea],
    frame: QuestionFrame
) -> list[HypothesisDraft]:
    """
    将 RegulativeIdea 转化为广度探索草稿。
    入口签名：目前设计最小化，避免 GAP-6 阻塞实现。
    """
    drafts = []
    for idea in ideas:
        # 尝试从 RegulativeIdea 提取可检验的角度
        extractable = extract_testable_angle(idea, frame)
        if extractable:
            raw = RawRepairDraft(
                claim_sketch=extractable.claim_sketch,
                tension_kind="SCHEMA_REPAIR",
                verifier_hint=extractable.verifier_hint,
                scope_ref=extractable.scope_ref,
                detail=f"由 RegulativeIdea {idea.idea_id} 转化"
            )
            ctx = RepairContext(
                frame=frame,
                gap_id=f"idea-{idea.idea_id}",
                challenge_id=f"idea-{idea.idea_id}",
                current_stage="RELAXED"
            )
            drafts.append(normalize_repair(raw, ctx))

    return drafts


# ======================================================
# AS 节点：AnswerSeed 组装
# ======================================================
def assemble_answer_seed(
    pa_state: PAState,
    frame: QuestionFrame
) -> AnswerSeed:
    """
    组装最终输出。目前实现为最小版本（GAP-3 的临时解决）。
    完整 AnswerSeed 设计待后续补充。
    """
    top_claims = pa_state.ranked_claims[:frame.evaluation_axes.__len__()]

    coverage_report = {}
    for claim in top_claims:
        coverage_report[claim.claim_id] = claim.coverage

    axis_coverage = {}
    for ax in frame.evaluation_axes:
        axis_coverage[ax.axis_id] = compute_axis_coverage(
            ax.axis_id, pa_state.ranked_claims
        )

    return AnswerSeed(
        problem_id=frame.problem_id,
        epoch_id=pa_state.ranking_history[-1].epoch_id if pa_state.ranking_history else 0,
        top_claims=top_claims,
        coverage_report=axis_coverage,
        integrity_status="CLEAN",  # 由调度层根据 intervention_log 更新
        termination_reason=pa_state.termination_reason or "正常终止"
    )
```

---

## 7 节点状态机完整规格

```
QN（问题摄取）
  输入：ProblemStatement + RefinementSignal[]
  输出：QuestionFrame
  触发条件：epoch=0 OR 有 RefinementSignal
  失败处理：
    NormalizeFatal → EngineError(FATAL_CATEGORY_ERROR) → 终止整个 pipeline
    NormalizeRecoverable → EngineError(RECOVERABLE) → 暂停，等待用户补充

MB（宏观广度）
  输入：QuestionFrame + EngineConfig.mb_config + 外部立场
  输出：HypothesisDraft[]（新一批草稿）
  失败处理：
    OPEN_TERM_SATURATION → 存储 RefinementSignal，下 epoch 触发 QN
    NO_TENSION_FOUND → 暂停，等待外部立场注入
    ALL_DRAFTS_HOMOLOGOUS → 同上

CC（声明编译器）
  输入：HypothesisDraft（from 草稿池）+ QuestionFrame
  输出（三种路由）：
    TestableClaim → 进入 D2
    RegulativeIdea → 进入 RB
    RefinementSignal → 存储，下 epoch 触发 QN

D2（Layer 2 分派）
  输入：TestableClaim[] + AxisRulebook + epoch_id
  输出：L2Return（增量事件）
  失败处理：
    L2Return 超大（>32KB）→ 拒收，要求 L2 合并后重发
    applyDelta 失败 → 记录错误，局部跳过，继续其他 delta

PA（评分与终止）
  输入：verified_claims + QuestionFrame + EpsilonState
  输出：ranked_claims + TerminationDecision
  终止条件：无阻塞 Gap AND 覆盖率 ≥ min_coverage AND 稳定 ≥ hysteresis_rounds
  不满足：继续到 RB

RB（修复广度）
  输入：blocking_gaps（GapSpec[]）+ RegulativeIdea[] + L1State
  输出：新 HypothesisDraft[]（修复草稿）
  失败处理：
    SUSPENDED → 挂起该 gap，等待用户干预
    EXHAUSTED → 标记 gap 为 EXHAUSTED，报告

AS（答案组装）
  输入：PAState + QuestionFrame
  输出：AnswerSeed
  触发条件：PA 判定 should_terminate=true
  注意：integrity_status 继承自 EngineSnapshot.integrity_status
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-L1-01 | `epoch_id` 单调递增，每个完整 epoch 后 +1，续跑时不重置 | Phase 4 |
| INV-L1-02 | `apply_delta()` 是纯函数，不修改原 state，返回新 state | 函数式设计 |
| INV-L1-03 | `L2Return.size_bytes > 32KB` 时 L1 拒收，要求 L2 合并后重发 | D2 节点检查 |
| INV-L1-04 | `repair()` 的输入必须是已经 `applyDelta` 后的 `l1_state`，禁止传旧版 `L2Return` | 接口约定（GAP-1） |
| INV-L1-05 | 草稿池去重通过 `is_homologous()` 进行，不是按 `draft_id` 去重 | 调用 `deduplicate_drafts` |
| INV-L1-06 | 每个 epoch 结束后必须处于以下之一：（a）有后台 D2/repair 任务在运行，（b）等待用户干预，（c）已输出 AnswerSeed | 状态机约定 |
| INV-L1-07 | `EngineSnapshot` 的 `negative_space` 全量持久化，禁止 LRU | 快照策略 |
| INV-L1-08 | `DebugOverride` 后 `integrity_status` 传播到 `AnswerSeed`，用户可见 | AS 节点传播 |

---

## 具体样例：一个完整 Epoch 的端到端 Trace

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"，Epoch 3

```
epoch=3, state = {
  frame: QF_v2 (4 axes, open_terms=[]),
  draft_pool: [mb-001, mb-002, repair-007-001],
  testable_claims: [claim-007, claim-009],
  verified_claims: [vc-007, vc-009],  // 来自 Epoch 2
  active_gaps: [gap-007(blocks=true)],
  pa_state: { consecutive_stable_epochs: 2 }
}

────────────────────────────────────
节点 1: QN
  has_refinement_signals = False (open_terms=[])
  → 跳过（非 epoch=0，无精炼信号）
────────────────────────────────────
节点 2: MB
  macro_breadth(QF_v2, config):
    → 生成 [mb-003, mb-004, mb-005]
  去重：
    is_homologous(mb-003, mb-001) = False → 保留
    is_homologous(mb-004, repair-007-001) = True → 丢弃（同源）
    is_homologous(mb-005, mb-002) = False → 保留
  draft_pool: [mb-001, mb-002, repair-007-001, mb-003, mb-005]
────────────────────────────────────
节点 3: CC
  mb-003: → TestableClaim(claim-011) [新]
  mb-005: → RegulativeIdea(idea-001) [无经验桥接]
  repair-007-001: → TestableClaim(claim-012) [新，修复草稿]
  mb-001, mb-002: 已编译，跳过
────────────────────────────────────
节点 4: D2
  pending: [claim-011, claim-012]
  Layer 2 返回 L2Return:
    epoch_id: 3, size_bytes: 4096 < 32KB ✓
    deltas:
      { kind: "CLAIM_VERIFIED", claim: vc-011 (ax_capacity: 0.751) }
      { kind: "GAP_CLOSE", gap_id: "gap-007", resolution: "RESOLVED" }
      // repair-007-001 成功解决了 gap-007！

  applyDelta × 2:
    CLAIM_VERIFIED → verified_claims += [vc-011]
    GAP_CLOSE → active_gaps = []
────────────────────────────────────
节点 5: PA
  compute_rankings([vc-007, vc-009, vc-011]):
    → [claim-009(0.564), claim-011(0.542), claim-007(0.390)]

  update_pa_state():
    旧 top-3: [claim-009, claim-007, claim-011]
    新 top-3: [claim-009, claim-011, claim-007]
    → 排名变化（claim-011 和 claim-007 互换）
    → consecutive_stable_epochs: 2 → 0 (重置)

  check_termination():
    blocking_gaps = [] ✓
    avg_coverage = (0.75+0.50+0.50)/3 = 0.583 < 0.70 ✗
    → should_terminate = False
    → 继续到 RB
────────────────────────────────────
节点 6: RB
  blocking_gaps = [] (gap-007 已关闭)
  → 无阻塞 gap 需要修复

  repair_breadth([idea-001], QF_v2):
    extract_testable_angle(idea-001):
      → idea-001 ("道德优越性") 无法提取可检验角度
      → 返回 None
    → idea_drafts = []

  → draft_pool 无变化

────────────────────────────────────
epoch_id: 3 → 4
返回 Ok(state_with_epoch_4)
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-3~~** → **已裁定** ✅
> - 裁定结论：`AnswerSeed` 是 tagged union（`ANSWER_SEED | ANSWER_SEED_SKIPPED`），coverage 二值化，数据源头在 PA 的 `RankedClaim.axis_hits`；`assemble_answer_seed(state: L1State): AnswerSeed` 为唯一签名（传入 L1State，不传 `null`），Skipped variant 替代原来的 `null` 返回值；AS 节点不包含叙述文本（叙述属于下游渲染层）。
> - 关键规格：`AnswerSeedProduced { kind: "ANSWER_SEED"; problem_id; epoch_id; integrity_status; termination_reason; top_k; top_claims: RankedClaim[]; coverage_report: Record<AxisId, AxisCoverage>; provenance: { ranked_claim_ids; evaluation_axis_ids } }`；`AnswerSeedSkipped { kind: "ANSWER_SEED_SKIPPED"; skipped_because: "TERMINATED_BEFORE_AS" | "INTERNAL_ERROR" | "NO_SURVIVING_CLAIMS" }`；`AxisCoverage { covered: 0|1; strength?: number }`；`RankedClaim` 需扩展 `axis_hits: Record<AxisId, number>` 字段（PA 在聚合时注入）。
> - 可推翻条件：若 PA 侧证明无法产出 `axis_hits`，则退化为 `axis_ids: AxisId[]`（布尔命中）；若二值 `covered` 导致终止判断信息不足，则改为 `coverage_depth: number ∈ [0,1]`（计算方法必须独立于 `score`）。
> - 裁定来源：`gap_missing_nodes_debate_summary.md`

> **~~GAP-6~~** → **已裁定** ✅（完整裁定见 `03_macro_breadth.md`）
> - 裁定结论：RB 节点执行"规则预筛 + LLM 提取代理变量"两阶段；novelty 由外部纯函数（Jaccard on entity set）计算，LLM 不自评 novelty；策略三值（`PROXY_MEASURE | COMPONENT_DECOMPOSE | LOGICALLY_NON_TESTABLE`，最后一个是终止标记非策略）；失败路径写入 `L1State.rb_reject_log: AngleReject[]`；连续 N 次（默认 3）`RB_REJECT` 且原因均为 `NON_TESTABLE` 时触发 `termination_reason = "RB_EXHAUSTED"`。
> - 关键规格：`extract_testable_angle(idea, frame, existing_claims, config): RBResult`；`RBFilterConfig { blacklist_patterns; min_related_axes; novelty_threshold; novelty_method; novelty_method_version }`；`compute_novelty(candidate_entities, existing_entities, method): number`（纯函数）；`scope_ref` 运行时强制断言引用合法 axis_id。
> - 裁定来源：`gap_missing_nodes_debate_summary.md`

> **~~GAP-8~~** → **已裁定** ✅
> - 裁定结论：D2 只注入索引句柄 `EvidenceRef`（不携带 EvidenceChain 正文）；历史视图 `HistoryView` 是只读投影，不进入 L1State 持久化；`build_verification_context(state: L1State): VerificationContext` 从 `state.epoch_history` 提取索引；L1State 中的历史存储为轻量的 `epoch_history: EpochSummary[]`（不包含 EvidenceChain 正文）。
> - 关键规格：`EvidenceRef { claim_id; epoch_id; verdict: "SUPPORTED"|"REFUTED"|"INSUFFICIENT"|"ERROR"; etag; storage_key }`；`EpochSummary { epoch_id; claims_evaluated; claims_surviving; coverage_snapshot: Record<AxisId, AxisCoverage>; evidence_refs: EvidenceRef[] }`；`VerificationContext { current_epoch; prior_evidence: EvidenceRef[]; prior_verdicts: Record<ClaimId, verdict> }`；`HistoryView { epochs: EpochSummary[]; resolve_evidence(ref): Promise<EvidenceChain> }`（按需加载）。
> - 可推翻条件：若 D2 的 LLM 调用仅靠 `verdict` 无法做出有效验证策略调整，允许在 `EvidenceRef` 增加 `summary: string`（≤200 字）但仍不携带完整 EvidenceChain；若 `epoch_history` 在 >20 epochs 后序列化超过 1MB，引入滑动窗口保留最近 N 个 `EpochSummary`，更早的替换为 `ArchivedEpochRef`。
> - 裁定来源：`gap_missing_nodes_debate_summary.md`
