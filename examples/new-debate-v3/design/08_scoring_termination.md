# 模块名：评分与终止（Scoring Termination / PA 节点）

<!-- import from 00_shared_types: VerifiedClaimFull, VerifiedClaimCompressed, GapSpec, TerminationGapKind, TerminationConfig, RankedClaim, EpsilonState -->
<!-- import from 06_epsilon_calibration: is_meaningful_change, EpsilonState -->

## 一句话定位

对所有已验证的 `VerifiedClaim` 按评估轴加权投影计算综合分，维护排名历史，并判断系统是否满足终止条件（无阻塞 Gap + 排名稳定 N 轮 + 覆盖率足够）——是认知引擎的"决策仲裁者"。

---

## 通俗解释

想象一个马拉松赛事的终点裁判委员会。每一轮（epoch）结束后，委员会要做三件事：

1. **排名**：把所有选手（VerifiedClaim）按综合成绩（加权轴得分）排序，看谁领先。
2. **稳定性评估**：如果连续 N 轮排名没有实质变化（变化在测量误差 epsilon 以内），说明比赛结果已经可以接受了。
3. **阻塞检查**：如果赛道上还有重大安全问题（`blocks_termination=true` 的 GapSpec），不管排名多稳定，比赛必须继续——先解决安全问题。

三个条件同时满足才宣布终止：没有阻塞缺口 + 排名稳定 + 覆盖率足够。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: VerifiedClaimFull, GapSpec, TerminationGapKind, TerminationConfig, RankedClaim
// import from 06_epsilon_calibration: EpsilonState

interface PAState {
  ranked_claims: RankedClaim[];
  ranking_history: RankingEntry[];
  consecutive_stable_epochs: number;
  epsilon_states: Record<string, EpsilonState>;
  termination_config: TerminationConfig;
  termination_reason?: string;
}

interface RankingEntry {
  epoch_id: number;
  ranked_claim_ids: string[];
  axis_scores: Record<string, number>;
  has_intervention_before: boolean;
}

interface TerminationDecision {
  should_terminate: boolean;
  blocking_gaps: GapSpec[];          // 阻塞终止的 gaps（TerminationGapKind 视角）
  stable_epochs: number;
  coverage_score: number;
  termination_reason?: string;       // 如果 should_terminate=true
  blocking_reason?: string;          // 如果 should_terminate=false
}

// 核心函数
function compute_rankings(
  verified_claims: VerifiedClaimFull[],
  frame: QuestionFrame,
  epsilon_states: Record<string, EpsilonState>
): RankedClaim[];

function check_termination(
  pa_state: PAState,
  active_gaps: GapSpec[],
  current_epoch: number
): TerminationDecision;

function update_pa_state(
  pa_state: PAState,
  new_rankings: RankedClaim[],
  current_epoch: number
): PAState;
```

---

## 伪代码实现（Python 风格）

```python
# 终止条件配置默认值
DEFAULT_TERMINATION_CONFIG = TerminationConfig(
    top_k=3,
    min_coverage=0.70,
    hysteresis_rounds=2,  # 排名稳定的连续轮次要求
    score_alpha=1.0        # 评分缩放因子（注意：不是 ema_alpha！）
)


def compute_rankings(
    verified_claims: list[VerifiedClaimFull],
    frame: QuestionFrame,
    epsilon_states: dict[str, EpsilonState]
) -> list[RankedClaim]:
    """
    为所有已验证的 claim 计算加权综合分并排序。
    使用 score_alpha 缩放因子（与 ema_alpha 是不同参数，GAP-5）。
    """
    ranked = []

    for claim in verified_claims:
        # Step 1: 计算每个轴的加权得分贡献
        weighted_score = 0.0
        covered_weight = 0.0

        for axis in frame.evaluation_axes:
            axis_id = axis.axis_id
            raw_score = claim.axis_scores.get(axis_id)

            if raw_score is None:
                continue  # 该轴无覆盖

            # 应用 score_alpha 缩放（平滑极端分数）
            score_alpha = DEFAULT_TERMINATION_CONFIG.score_alpha
            scaled_score = score_alpha * raw_score

            weighted_score += axis.weight * scaled_score
            covered_weight += axis.weight

        # Step 2: 覆盖率（已覆盖轴的权重总和）
        coverage = covered_weight  # ∈ [0, 1]

        ranked.append(RankedClaim(
            claim_id=claim.claim_id,
            score=weighted_score,
            coverage=coverage
        ))

    # Step 3: 按综合分降序排列
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def check_termination(
    pa_state: PAState,
    active_gaps: list[GapSpec],
    current_epoch: int
) -> TerminationDecision:
    """
    终止判定：三个条件同时满足才返回 should_terminate=True。
    gap.kind 使用 TerminationGapKind（终止视角），不同于 RepairGapKind。
    """
    config = pa_state.termination_config

    # ======================================================
    # 条件 1: 无阻塞 Gap
    # ======================================================
    blocking_gaps = [
        g for g in active_gaps
        if g.blocks_termination
    ]

    if blocking_gaps:
        return TerminationDecision(
            should_terminate=False,
            blocking_gaps=blocking_gaps,
            stable_epochs=pa_state.consecutive_stable_epochs,
            coverage_score=compute_avg_coverage(pa_state.ranked_claims),
            blocking_reason=f"存在 {len(blocking_gaps)} 个阻塞性缺口：{[g.gap_id for g in blocking_gaps]}"
        )

    # ======================================================
    # 条件 2: 覆盖率足够
    # ======================================================
    top_k_claims = pa_state.ranked_claims[:config.top_k]
    avg_coverage = (
        sum(c.coverage for c in top_k_claims) / len(top_k_claims)
        if top_k_claims else 0.0
    )

    if avg_coverage < config.min_coverage:
        return TerminationDecision(
            should_terminate=False,
            blocking_gaps=[],
            stable_epochs=pa_state.consecutive_stable_epochs,
            coverage_score=avg_coverage,
            blocking_reason=f"覆盖率 {avg_coverage:.2f} < 最低要求 {config.min_coverage}"
        )

    # ======================================================
    # 条件 3: 排名稳定
    # ======================================================
    if pa_state.consecutive_stable_epochs >= config.hysteresis_rounds:
        return TerminationDecision(
            should_terminate=True,
            blocking_gaps=[],
            stable_epochs=pa_state.consecutive_stable_epochs,
            coverage_score=avg_coverage,
            termination_reason=(
                f"排名连续稳定 {pa_state.consecutive_stable_epochs} 轮，"
                f"覆盖率 {avg_coverage:.2f}，无阻塞缺口"
            )
        )
    else:
        return TerminationDecision(
            should_terminate=False,
            blocking_gaps=[],
            stable_epochs=pa_state.consecutive_stable_epochs,
            coverage_score=avg_coverage,
            blocking_reason=(
                f"排名稳定轮次不足：{pa_state.consecutive_stable_epochs} / {config.hysteresis_rounds}"
            )
        )


def update_pa_state(
    pa_state: PAState,
    new_rankings: list[RankedClaim],
    current_epoch: int
) -> PAState:
    """
    更新 PA 状态：比较新旧排名，更新稳定性计数器。
    使用 is_meaningful_change() 检查变化是否超过 epsilon。
    """
    old_top = [r.claim_id for r in pa_state.ranked_claims[:3]]
    new_top = [r.claim_id for r in new_rankings[:3]]

    # 检查 Top-K 排名是否发生有意义的变化
    ranking_changed = False
    if old_top != new_top:
        ranking_changed = True
    else:
        # 排名相同，但检查分数变化是否超过 epsilon
        for new_r in new_rankings[:3]:
            old_r = next((r for r in pa_state.ranked_claims if r.claim_id == new_r.claim_id), None)
            if old_r is None:
                ranking_changed = True
                break
            epsilon_state = pa_state.epsilon_states.get(new_r.claim_id)
            epsilon = epsilon_state.current_epsilon if epsilon_state else 0.05

            if is_meaningful_change(old_r.score, new_r.score, epsilon):
                ranking_changed = True
                break

    # 更新连续稳定轮次计数器
    if ranking_changed:
        consecutive_stable_epochs = 0
    else:
        consecutive_stable_epochs = pa_state.consecutive_stable_epochs + 1

    # 记录本轮排名历史
    new_entry = RankingEntry(
        epoch_id=current_epoch,
        ranked_claim_ids=[r.claim_id for r in new_rankings],
        axis_scores={r.claim_id: r.score for r in new_rankings},
        has_intervention_before=False  # 干预后由 apply_intervention 更新
    )

    new_history = pa_state.ranking_history + [new_entry]
    # 滑动窗口：保留最近 5 轮（性能优化，不影响语义）
    if len(new_history) > 5:
        new_history = new_history[-5:]

    return PAState(
        ranked_claims=new_rankings,
        ranking_history=new_history,
        consecutive_stable_epochs=consecutive_stable_epochs,
        epsilon_states=pa_state.epsilon_states,
        termination_config=pa_state.termination_config
    )


def classify_gap_for_termination(gap: GapSpec) -> TerminationGapKind | None:
    """
    将通用 GapSpec 分类为终止视角的 TerminationGapKind。
    注意：这不是将 RepairGapKind 转换为 TerminationGapKind，
         而是从 GapSpec 描述中提取终止相关的分类。
    """
    # 轴覆盖缺口
    if "UNCOVERED" in gap.description.upper() or gap.kind == "UNCOVERED_HIGH_WEIGHT_AXIS":
        return "UNCOVERED_HIGH_WEIGHT_AXIS"
    # 证据冲突
    elif gap.kind == "EVIDENCE_CONFLICT":
        return "EVIDENCE_CONFLICT"
    # 未解决的反证
    elif gap.kind == "UNRESOLVED_DEFEATER":
        return "UNRESOLVED_DEFEATER"
    else:
        return None  # 非终止相关的 gap，不影响终止判定
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-PA-01 | `ranked_claims` 按 `score` 降序排列（可通过比较 `ranked_claims[i].score >= ranked_claims[i+1].score` 验证） | 排序保证 |
| INV-PA-02 | 终止需三条件同时满足：无阻塞 Gap + 覆盖率 ≥ `min_coverage` + 稳定 ≥ `hysteresis_rounds` | `check_termination` 逻辑 |
| INV-PA-03 | `is_meaningful_change()` 返回 false 时不递增稳定计数器——噪声不算稳定 | `update_pa_state` 逻辑 |
| INV-PA-04 | 干预（如 `REWEIGHT_AXIS`）后必须重置 `consecutive_stable_epochs = 0` | `apply_intervention` 约定 |
| INV-PA-05 | `score_alpha`（评分缩放）≠ `ema_alpha`（epsilon 学习率），配置和代码中严格区分 | GAP-5 |
| INV-PA-06 | `blocking_gaps` 判断基于 `GapSpec.blocks_termination` 布尔标志，而非 gap 的枚举 kind | 字段读取 |
| INV-PA-07 | `ranking_history` 保留最近 5 轮（滑动窗口），续跑时不清空——epoch_id 单调递增 | 窗口机制 |
| INV-PA-08 | `coverage_score ∈ [0, 1]`，等于已覆盖轴的权重之和 | 数学保证 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"，Epoch 3

```
输入：
  verified_claims:
    claim-007: { ax_burden_share: 0.849, ax_economic: 0.712 }
    claim-009: { ax_capacity: 0.821, ax_economic: 0.680, ax_implement: 0.755 }
    claim-011: { ax_burden_share: 0.501, ax_capacity: 0.633 }
  frame.evaluation_axes:
    ax_economic:    weight=0.25, epsilon=0.046
    ax_burden_share: weight=0.25, epsilon=0.022
    ax_capacity:    weight=0.25, epsilon=0.038
    ax_implement:   weight=0.25, epsilon=0.055

compute_rankings():

  claim-007:
    weighted_score = 0.25×0.849 + 0.25×0.712 = 0.212 + 0.178 = 0.390
    coverage = 0.25 + 0.25 = 0.50  ← 只覆盖了 2 个轴

  claim-009:
    weighted_score = 0.25×0.821 + 0.25×0.680 + 0.25×0.755 = 0.205 + 0.170 + 0.189 = 0.564
    coverage = 0.25 + 0.25 + 0.25 = 0.75

  claim-011:
    weighted_score = 0.25×0.501 + 0.25×0.633 = 0.125 + 0.158 = 0.283
    coverage = 0.25 + 0.25 = 0.50

  Rankings: [claim-009(0.564), claim-007(0.390), claim-011(0.283)]

active_gaps:
  gap-007: { blocks_termination: true, kind: "MISSING_DISCRIMINATOR" }
  gap-012: { blocks_termination: false, kind: "UNCOVERED_HIGH_WEIGHT_AXIS" }

check_termination():
  条件 1：blocking_gaps = [gap-007] → 存在阻塞
  → TerminationDecision {
      should_terminate: false,
      blocking_reason: "存在 1 个阻塞性缺口：['gap-007']",
      stable_epochs: 2,
      coverage_score: 0.583  ← (0.75+0.50+0.50)/3
    }

[假设 Epoch 4 后 gap-007 通过 repair 被关闭]

Epoch 4 check_termination():
  条件 1: blocking_gaps = [] → 通过
  条件 2: avg_coverage(top-3) = 0.75 ≥ 0.70 → 通过
  条件 3: consecutive_stable_epochs = 2 ≥ 2 → 通过
  → TerminationDecision {
      should_terminate: true,
      termination_reason: "排名连续稳定 2 轮，覆盖率 0.75，无阻塞缺口"
    }
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-5~~** → **已裁定** ✅
> - 裁定结论：所有配置在 epoch 0 初始化时全量校验，结构性错误（类型不匹配、约束违反、必填字段缺失、权重之和 ≠ 1.0）FATAL 拒绝启动；未知字段采用 `warn + strip` 降级运行；`score_alpha`（评分缩放因子）与 `ema_alpha`（epsilon 学习率）全代码库严格区分命名。
> - 关键规格：`ConfigValidationResult = { level: "FATAL"; errors } | { level: "DEGRADED"; warnings; stripped_fields } | { level: "OK" }`；`initialize_system(config) → Result<L1State, Fatal>`；FATAL 条件：axes 为空、权重和 ≠ 1.0（±0.001）、GapSpec 引用不存在的 axis_id、类型不匹配、必填字段缺失。
> - 可推翻条件：`DEGRADED` 启动导致下游模块因缺少被 strip 的字段而运行时崩溃 >2 次，则将对应 `UNKNOWN_FIELD` 提升为 FATAL。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`

> **~~GAP-2~~** → **已裁定** ✅（完整裁定见 `00_shared_types.md`）
> - 裁定结论：GapSpec.kind 升级为 Tagged Union；PA 节点只能调用 `create_termination_gap` 工厂函数，`classify_gap_for_termination()` 通过 `gap.kind.type === "TERMINATION"` 过滤，不得将 REPAIR 类 gap 误判为终止相关缺口。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`
