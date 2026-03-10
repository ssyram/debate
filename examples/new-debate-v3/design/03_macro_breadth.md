# 模块名：宏观广度（Macro Breadth / MB 节点）

<!-- import from 00_shared_types: QuestionFrame, HypothesisDraft, TensionSource, RegulativeAxis -->
<!-- import from 02_hypothesis_draft: normalize_mb, is_homologous -->

## 一句话定位

接收 `QuestionFrame`，从三类张力源（评价轴内在分裂、利益相关方冲突、外部立场）生成多样化的 `HypothesisDraft[]`，保证覆盖不同认识层次的探索角度，并通过贪心去重避免同质化——是认知引擎的"发散思维"模块。

---

## 通俗解释

侦探事务所接到调查委托（`QuestionFrame`）后，要提出各种可能的假说方向。MB 就是事务所里的头脑风暴会议。

会议上有三类想法来源：
1. **案件结构本身的矛盾**：调查方向"创新速度"这条线索本身就有两种对立解读，这些是内部逻辑逼迫出来的，必须探索。
2. **各方证人/当事人的冲突陈述**：开发者说 AI 应该开源，监管机构说不能开源。
3. **其他权威人士的观点**：某位顾问写了报告说业界自律从来不管用。

会议有配额：优先探索内部矛盾（因为这些更可能是核心），再探索经验性冲突。而且，已经有人提了同样方向的假说，就不再重复。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: QuestionFrame, HypothesisDraft

type EpistemicTier = "INTERNAL_AXIS" | "EMPIRICAL";

type TensionSourceKind =
  | "EVALUATION_AXIS_SPLIT"
  | "STAKEHOLDER_CONFLICT"
  | "EXTERNAL_POSITION";

interface TensionCandidate {
  candidate_id: string;
  kind: TensionSourceKind;
  tier: EpistemicTier;            // 由 falsifier_independence 决定，非硬编码
  axis_ids: string[];
  stakeholders: string[];
  claim_sketch: string;
  verifier_hint: string[];
  salience: number;               // [0, 1]，层内排序用
  open_term_risk: string[];
}

interface MacroBreadthConfig {
  max_drafts: number;               // 默认 6
  internal_tier_quota: number;      // 内部层配额比例，默认 0.5
  per_axis_cap: number;             // 单轴最大草稿数，默认 2
  require_kind_diversity: boolean;  // 是否要求多种张力类型，默认 true
  max_open_term_risk_ratio: number; // open_term 风险草稿占比上限，默认 0.5
  default_ttl: number;              // 草稿初始 TTL，默认 3
}

interface ExternalPosition {
  text: string;
  source_ref?: string;
}

type MacroBreadthError =
  | { code: "NO_TENSION_FOUND"; axes_tried: string[]; stakeholders_tried: string[] }
  | { code: "ALL_DRAFTS_HOMOLOGOUS"; cluster_summary: string }
  | { code: "OPEN_TERM_SATURATION"; saturated_terms: string[] };

type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

function macro_breadth(
  frame: QuestionFrame,
  config?: MacroBreadthConfig,
  external_positions?: ExternalPosition[]
): Result<HypothesisDraft[], MacroBreadthError>;
```

---

## 伪代码实现（Python 风格）

```python
DEFAULT_CONFIG = MacroBreadthConfig(
    max_drafts=6,
    internal_tier_quota=0.5,
    per_axis_cap=2,
    require_kind_diversity=True,
    max_open_term_risk_ratio=0.5,
    default_ttl=3,
)


def macro_breadth(
    frame: QuestionFrame,
    config: MacroBreadthConfig = DEFAULT_CONFIG,
    external_positions: list[ExternalPosition] = []
) -> Result[list[HypothesisDraft], MacroBreadthError]:

    # ======================================================
    # Phase 1: 生成所有张力候选
    # ======================================================
    candidates: list[TensionCandidate] = []

    # 张力源 1: EVALUATION_AXIS_SPLIT
    for axis in frame.evaluation_axes:
        splits = generate_axis_splits(axis, frame)
        # tier 由 falsifier_independence 决定，不是枚举值硬编码
        tier = ("INTERNAL_AXIS"
                if axis.falsifier_independence == "INDEPENDENT"
                else "EMPIRICAL")

        for split in splits:
            candidates.append(TensionCandidate(
                candidate_id=generate_id("tc"),
                kind="EVALUATION_AXIS_SPLIT",
                tier=tier,
                axis_ids=[axis.axis_id],
                stakeholders=[],
                claim_sketch=split.claim,
                verifier_hint=[axis.falsifier],
                salience=split.salience,
                open_term_risk=detect_open_term_overlap(split.claim, frame.open_terms)
            ))

    # 张力源 2: STAKEHOLDER_CONFLICT
    from itertools import combinations
    for pair in combinations(frame.stakeholders, 2):
        conflicts = generate_stakeholder_conflicts(list(pair), frame)
        for conflict in conflicts:
            candidates.append(TensionCandidate(
                candidate_id=generate_id("tc"),
                kind="STAKEHOLDER_CONFLICT",
                tier="EMPIRICAL",       # 利益相关方冲突始终是经验层
                axis_ids=conflict.related_axes,
                stakeholders=list(pair),
                claim_sketch=conflict.claim,
                verifier_hint=conflict.hints,
                salience=conflict.salience,
                open_term_risk=detect_open_term_overlap(conflict.claim, frame.open_terms)
            ))

    # 张力源 3: EXTERNAL_POSITION
    for pos in external_positions[:config.max_drafts]:  # 硬上限
        candidates.append(TensionCandidate(
            candidate_id=generate_id("tc"),
            kind="EXTERNAL_POSITION",
            tier="EMPIRICAL",
            axis_ids=infer_axes_from_position(pos, frame),
            stakeholders=[],
            claim_sketch=pos.text,
            verifier_hint=[],
            salience=assess_external_salience(pos, frame),
            open_term_risk=detect_open_term_overlap(pos.text, frame.open_terms)
        ))

    # ======================================================
    # Phase 2: Fallback 检查
    # ======================================================
    if not candidates:
        return Err(MacroBreadthError(
            code="NO_TENSION_FOUND",
            axes_tried=[a.axis_id for a in frame.evaluation_axes],
            stakeholders_tried=frame.stakeholders
        ))

    # ======================================================
    # Phase 3: 分层配额选择 + 贪心去重
    # ======================================================
    internal_pool = sorted(
        [c for c in candidates if c.tier == "INTERNAL_AXIS"],
        key=lambda c: c.salience, reverse=True
    )
    empirical_pool = sorted(
        [c for c in candidates if c.tier == "EMPIRICAL"],
        key=lambda c: c.salience, reverse=True
    )

    internal_quota = math.ceil(config.max_drafts * config.internal_tier_quota)
    empirical_quota = config.max_drafts - internal_quota

    actual_internal = min(len(internal_pool), internal_quota)
    # 内部层不足时，配额让渡给经验层
    actual_empirical = min(
        len(empirical_pool),
        empirical_quota + (internal_quota - actual_internal)
    )

    selected: list[TensionCandidate] = []

    for pool, quota in [(internal_pool, actual_internal), (empirical_pool, actual_empirical)]:
        for candidate in pool:
            tier_selected = [s for s in selected if s.tier == candidate.tier]
            if len(tier_selected) >= quota:
                break

            # 同源性是动态计算的，不是预标记的
            if is_candidate_homologous_to_selected(candidate, selected):
                continue  # 跳过同源候选

            if count_per_axis(candidate, selected) >= config.per_axis_cap:
                continue  # 单轴上限

            selected.append(candidate)

    # ======================================================
    # Phase 4: 同源性全灭检查
    # ======================================================
    if not selected:
        return Err(MacroBreadthError(
            code="ALL_DRAFTS_HOMOLOGOUS",
            cluster_summary=summarize_homologous_clusters(candidates)
        ))

    # ======================================================
    # Phase 5: Open term 风险饱和检查
    # ======================================================
    risky_count = sum(1 for s in selected if s.open_term_risk)
    if len(selected) > 0 and risky_count / len(selected) > config.max_open_term_risk_ratio:
        return Err(MacroBreadthError(
            code="OPEN_TERM_SATURATION",
            saturated_terms=list(set(
                t for s in selected for t in s.open_term_risk
            ))
        ))

    # ======================================================
    # Phase 6: 转换为统一 HypothesisDraft（通过工厂函数）
    # ======================================================
    drafts = []
    for c in selected:
        raw = RawMBDraft(
            draft_id=generate_id("mb"),
            problem_id=frame.problem_id,
            claim_sketch=c.claim_sketch,
            scope_ref=c.axis_ids,           # 可能为空，normalize_mb 会推导
            verifier_hint=c.verifier_hint,
            open_term_risk=c.open_term_risk,
            tension_source=TensionSource(
                kind=c.kind,
                tier=c.tier,
                evidence_ref=[],
                note=f"tension source: {c.kind} | stakeholders: {c.stakeholders}"
            ),
            ttl=config.default_ttl
        )
        drafts.append(normalize_mb(raw, frame))

    return Ok(drafts)


def is_candidate_homologous_to_selected(
    candidate: TensionCandidate,
    selected: list[TensionCandidate]
) -> bool:
    """同源性：动态计算，不预标记。"""
    for s in selected:
        axis_overlap = (
            len(set(candidate.axis_ids) & set(s.axis_ids)) /
            max(len(candidate.axis_ids), 1)
        )
        semantic_sim = compute_semantic_similarity_raw(candidate.claim_sketch, s.claim_sketch)
        if axis_overlap > 0.8 and semantic_sim > 0.85:
            return True
    return False


def count_per_axis(candidate: TensionCandidate, selected: list[TensionCandidate]) -> int:
    """计算候选所涉及的主轴在已选集中的出现次数"""
    if not candidate.axis_ids:
        return 0
    primary_axis = candidate.axis_ids[0]
    return sum(
        1 for s in selected
        if primary_axis in s.axis_ids
    )
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-MB-01 | `Ok` 输出的 `drafts.length ∈ [1, config.max_drafts]` | 贪心选择保证上界；Phase 4 保证下界 |
| INV-MB-02 | `Ok` 输出中不存在两两同源的草稿 | 贪心去重（Phase 3） |
| INV-MB-03 | `open_term_risk` 占比 ≤ `max_open_term_risk_ratio`，否则返回 Err | Phase 5 |
| INV-MB-04 | 单轴草稿数 ≤ `per_axis_cap` | Phase 3 |
| INV-MB-05 | `tier` 由 `axis.falsifier_independence` 决定，禁止硬编码 `TensionSourceKind` 的枚举值 | 代码审查 |
| INV-MB-06 | `Err` 时不产出空数组——失败必须是结构化的错误类型 | 接口约定 |
| INV-MB-07 | 配额让渡：内部层不足时，剩余配额自动让给经验层 | Phase 3 逻辑 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"（Epoch 2，已精炼后的 `QuestionFrame_v2`）

```
输入 QuestionFrame_v2:
  problem_id: "q-carbon-001-r1"
  evaluation_axes:
    ax_economic: "经济效率"  (INDEPENDENT, w=0.25)
    ax_burden_share: "负担分担原则"  (INDEPENDENT, w=0.25)
    ax_capacity: "能力差异原则"  (INDEPENDENT, w=0.25)
    ax_implement: "实施可行性"  (STAKEHOLDER_DERIVED, w=0.25)
  open_terms: []  ← 已精炼
  stakeholders: ["发展中国家政府", "发达国家政府", "能源密集型企业", "环保组织"]

Phase 1: 生成张力候选

  EVALUATION_AXIS_SPLIT（ax_economic, INDEPENDENT → INTERNAL_AXIS）:
    C1: "配额定价机制是否应该引入碳价格走廊（上下限）以稳定市场预期"
        salience: 0.88, open_term_risk: []
    C2: "碳排放权拍卖收益应分配给受影响行业还是绿色能源研发"
        salience: 0.72, open_term_risk: []

  EVALUATION_AXIS_SPLIT（ax_burden_share, INDEPENDENT → INTERNAL_AXIS）:
    C3: "历史累积排放量应作为国家责任分担的主要依据"
        salience: 0.90, open_term_risk: []

  EVALUATION_AXIS_SPLIT（ax_capacity, INDEPENDENT → INTERNAL_AXIS）:
    C4: "GDP 作为能力替代指标在发展中国家具有系统性低估问题"
        salience: 0.75, open_term_risk: []

  EVALUATION_AXIS_SPLIT（ax_implement, STAKEHOLDER_DERIVED → EMPIRICAL）:
    C5: "自愿碳市场与强制碳市场的整合会削弱机制的整体约束力"
        salience: 0.68, open_term_risk: []

  STAKEHOLDER_CONFLICT（发展中国家 vs 发达国家）:
    C6: "排放权分配应优先保障发展中国家的发展权利而非绝对减排"
        salience: 0.80, open_term_risk: []

  STAKEHOLDER_CONFLICT（能源密集型企业 vs 环保组织）:
    C7: "免费配额分配（Grandfather Clause）会降低企业的减排动力"
        salience: 0.70, open_term_risk: []

Phase 3: 分层配额选择（max_drafts=6, internal_quota=0.5）

  internal_pool: [C3(0.90), C1(0.88), C4(0.75), C2(0.72)]
  empirical_pool: [C6(0.80), C5(0.68), C7(0.70)]

  internal_quota = ceil(6 × 0.5) = 3
  actual_internal = min(4, 3) = 3

  贪心去重选择 Internal:
    C3 ✓（无已选）
    C1 ✓（axis_overlap(C1,C3) = 0/1 = 0 < 0.8 → 不同源；且不同轴）
    C4 ✓（ax_capacity vs ax_burden_share、ax_economic → 轴各异）

  actual_empirical = min(3, 3 + 0) = 3

  贪心去重选择 Empirical:
    C6 ✓
    C5 ✓（STAKEHOLDER_DERIVED 轴 ax_implement，与 C6 轴不重叠）
    C7 ✓

  selected = [C3, C1, C4, C6, C5, C7]  → 6 个

Phase 5: open_term_risk
  risky_count = 0，ratio = 0 ≤ 0.5 → 通过

Phase 6: normalize_mb × 6
  → 6 个合法 HypothesisDraft，scope_ref 均非空，ttl = 3
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-6~~** → **已裁定** ✅
> - 裁定结论：RB 节点执行"规则预筛 + LLM 提取代理变量"两阶段；novelty 由外部纯函数（Jaccard on entity set）计算，LLM 不自评；策略三值（`PROXY_MEASURE | COMPONENT_DECOMPOSE | LOGICALLY_NON_TESTABLE`）；失败路径写入 `L1State.rb_reject_log: AngleReject[]`；连续 N 次（默认 3）`NON_TESTABLE` 时触发 `termination_reason = "RB_EXHAUSTED"`。
> - 关键规格：`extract_testable_angle(idea: RegulativeIdea, frame: QuestionFrame, existing_claims: RankedClaim[], config: RBFilterConfig): RBResult`；`RBFilterConfig { blacklist_patterns: string[]; min_related_axes: number; novelty_threshold: number; novelty_method: "jaccard_entity" | "tfidf_cosine"; novelty_method_version: string }`；`compute_novelty(candidate_entities, existing_entities, method): number`（纯函数）；`scope_ref` 强制引用合法 axis_id，运行时断言。
> - 可推翻条件：`jaccard_entity` 误杀率 >20%（50+ RegulativeIdea 样本），则切换 `tfidf_cosine` 并重新标定阈值；`COMPONENT_DECOMPOSE` 策略输出的子组件被 `is_homologous()` 拦截率 >50%，需增加"必须改变至少一个因果变量"硬约束。
> - 裁定来源：`gap_missing_nodes_debate_summary.md`
