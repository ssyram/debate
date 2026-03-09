# v3 认知引擎：normalize_question() 与 macro_breadth() 的实现决策 裁判总结

> 2026-03-09T18:30:50.880108

# 裁判裁定书：Layer 1 设计问题 E/F/G/H

---

## 第一部分：白话版结论

### 问题 E：`evaluation_axes.mode` 只能是 `regulative` 吗？normalize_question() 失败时怎么办？

**裁定：是的，Layer 1 只允许 `regulative` 模式；空轴是可恢复错误，不是合法状态。**

想象一个侦探事务所接到委托。侦探（Layer 1）首先要把委托人的模糊诉求（"帮我查清楚这件事"）翻译成具体的调查方向——比如"查资金流向""查人际关系""查时间线"。这些调查方向就是 `evaluation_axes`。

`regulative` 模式意味着：这些方向是"暂定的调查线索"，随时可以根据新证据调整。如果 LLM 生成了一个 `constitutive`（"铁律"）模式的轴——比如声称"资金流向就是唯一真相"——系统必须拒绝它，因为在 Layer 1 阶段，没有任何调查方向有资格自封为不可修正的定论。

**具体例子**：当系统处理"AI 是否应该被监管？"时，`normalize_question()` 可能推断出三个轴：创新影响、安全风险、公平性。如果 LLM 把"安全风险"标记为 `constitutive`（意思是"安全风险是不可质疑的评估维度"），系统应当返回 `Err(INVALID_AXIS_MODE)`，而不是静默接受。因为一旦静默接受，后续所有假设都会围绕"安全风险必然是核心维度"展开，而这个预设本身可能就是需要被检验的。

**空轴问题**：如果 `normalize_question()` 一个轴都推断不出来（比如用户问了"什么是好的？"），系统不应该假装一切正常然后让 `macro_breadth()` 在空白上胡编。正确做法是返回一个**可恢复错误**（`NormalizeRecoverable`），告诉上游："我推断出了一些利益相关方，但没能形成合法的评估轴，需要更多信息。"这和"这个问题根本不是经验问题"（`NormalizeFatal`，比如"这句话是假的"这种自指悖论）是两种完全不同的失败。

**可能需要修正的场景**：如果实践中发现大量合理问题在首轮都无法生成轴（比如高度探索性的科学问题），`NormalizeRecoverable` 的触发率过高导致系统可用性下降，则可能需要引入"最小默认轴集"作为 fallback，而非一律阻断。

**一句话总结**：Layer 1 的轴只能是暂定路标（regulative），不能是铁律；推断不出路标时要诚实报告，不能假装有路。

---

### 问题 F：`macro_breadth()` 的三类张力源如何分类、排序、覆盖？

**裁定：采用分层配额制（tier-then-quota），不采用统一打分池；但"先验/经验"的标签必须由构造过程决定，不能硬编码。**

继续侦探事务所的比喻。侦探拿到调查方向后，要从不同角度提出"假说"。假说的来源有三种：

1. **调查方向本身的内在张力**（EVALUATION_AXIS_SPLIT）：比如"资金流向"这条线索本身就有两种对立解读——"资金是合法避税"vs"资金是洗钱"。这是从问题结构内部长出来的分歧。
2. **不同当事人的利益冲突**（STAKEHOLDER_CONFLICT）：委托人说"他是好人"，证人说"他是骗子"。这是外部经验性的对立。
3. **外部专家意见**（EXTERNAL_POSITION）：另一个事务所发表过报告说"此类案件通常是内部人作案"。这是引入的外部立场。

**为什么要分层而不是混在一起打分？** 因为第一类张力和后两类张力的性质不同。第一类是从问题框架内部推导出的结构性分歧——如果你的调查方向本身就蕴含对立，那这种对立几乎必然需要被探索。后两类是经验性的，可能只是信息不全或采样偏差。把它们放进同一个打分池，用 `+100` vs `+10` 这种魔法数字来区分，等于把范畴差异压扁成了数值差异——这是康德最初方案的问题，也是 Linus 统一 `rankCandidates()` 方案的隐患。

**但 Ssyram 对康德的攻击也成立**：评估轴本身往往是从利益相关方冲突中推断出来的。如果"创新 vs 安全"这个轴就是从"开源社区 vs 监管机构"的冲突中提炼的，那说前者是"先验的"、后者是"经验的"就有循环论证之嫌。

**最终裁定的折中方案**：分层配额制保留，但"内部张力"的资格不是靠 `TensionSourceKind` 的枚举值硬编码，而是靠**构造过程的可追溯性**判定。具体来说：一个 `EVALUATION_AXIS_SPLIT` 类型的张力候选，只有当它所依赖的轴拥有独立的 `falsifier`（可证伪条件）且该 falsifier 不完全还原为某个 stakeholder 的立场时，才进入内部层（INTERNAL_AXIS tier）。否则降级为经验层。

**具体例子**：处理"AI 是否应该开源？"时——
- 轴"创新速度"有独立 falsifier："如果开源后 12 个月内主要 AI 实验室的论文产出未增加，则创新速度假说被证伪"。这个 falsifier 不依赖任何特定利益方的立场，进入内部层。
- 轴"社区信任度"的 falsifier 是"如果开源社区成员满意度调查低于阈值"——这本质上就是 stakeholder 的态度，降级为经验层。
- 外部立场"Elon Musk 认为 AI 应该开源"直接进入经验层。

配额分配：`maxDrafts` 的上半部分优先分配给内部层，下半部分分配给经验层。内部层不足时，配额让渡给经验层。

**同源性（is_homologous）的计算**：Ssyram 对康德的攻击完全成立——同源性是集合上的二元关系，不是单个候选的布尔属性。裁定要求：同源性必须在选择循环中动态计算（贪心去重），不能预标记。

**可能需要修正的场景**：如果实践中发现"独立 falsifier"的判定本身高度依赖 LLM 的语义理解且不稳定，则可能需要退化为 Linus 的简单优先级排序（axis > stakeholder > external），放弃精细的资格判定。

**一句话总结**：张力源分层选取而非混合打分，但"内部张力"的资格要靠 falsifier 独立性来挣，不能靠枚举值白拿。

---

### 问题 G：`open_terms` 在流水线中如何传递和消费？

**裁定：`macro_breadth()` 对 `open_terms` 执行"标记但不驱动"策略；`ClarityCompiler` 执行硬门控；死锁由 QN 的精炼回路打破。**

回到侦探事务所。委托人说"帮我查清楚他是不是个好人"。"好人"就是一个 `open_term`——它没有明确定义，不同人理解不同。

三位辩手的立场形成了一个清晰的光谱：
- **Ssyram 最初立场**："侦探提假说时完全不管'好人'这个词没定义，等到写报告（CC 编译）时再拦截。" → 问题：侦探会批量产出一堆围绕"好人"的假说，报告部门全部退回，来回空转（死锁）。Linus 的攻击完全成立。
- **Linus 立场**："侦探提假说时给含'好人'的假说打个风险标签，但不因此改变假说内容。" → 问题：标签只是字符串注记，不改变生成行为，实质上和盲视差别不大。康德的攻击部分成立。
- **Ssyram 修正后立场**："CC 拒绝后，把失败信号反馈给 QN，QN 把'好人'拆解成具体的评估轴（比如'是否守法''是否善待家人'），下一轮 MB 就能基于合法轴生成假说。" → 这是正确的闭环，但需要严格的类型保证。

**最终裁定**：

1. **MB 不基于 `open_terms` 生成假说**（不把"好人的不同定义"当作张力源来驱动广度探索）。理由：定义分歧应该在 QN 阶段被结构化为评估轴或 scope 约束，而不是在 MB 阶段被当作一阶张力。这是关注点分离的要求。

2. **MB 执行轻量级标记**：对每个草稿，检测其 `claim_sketch` 是否引用了 `open_terms` 中的词项，并在 `open_term_risk: string[]` 字段中记录。这不改变生成逻辑，但为 CC 提供预筛信息，避免 CC 做完整语义分析时的冗余计算。

3. **CC 执行硬门控**：如果草稿的 `claim_sketch` 包含未绑定的 open term，返回 `Err(UNBOUND_OPEN_TERM)`，附带 `RefinementSignal`。

4. **QN 的精炼回路打破死锁**：QN 接收 `RefinementSignal`，执行"概念降解"——尝试将 open term 转化为评估轴或 scope 约束。如果降解失败（比如"好"这个词实在太模糊，无法拆解），QN 返回 `NormalizeRecoverable`，请求外部输入（用户澄清或注入默认轴库）。

5. **`open_terms` 留在 `QuestionFrame` 公共 schema 中**，因为它有三个消费者：CC（硬门控）、MB（轻量标记）、QN 精炼回路（降解触发器）。Ssyram 最初说"只有 CC 消费"是错的；Linus 说"如果只有 CC 消费就不该在公共 schema"的攻击是对的，但结论应该是承认多消费者，而非移除字段。

**具体例子**："最优数据库索引策略是什么？"
- Epoch 1：QN 输出 `open_terms: ["最优"]`，`evaluation_axes: []` → 触发 `NormalizeRecoverable`（空轴），不进入 MB。
- 用户/系统补充上下文："面向 OLTP 场景，关注读写延迟和存储开销"。
- Epoch 2：QN 重新解析，`open_terms: []`（"最优"已降解为两个轴），`evaluation_axes: [{axis_id: "read_latency", falsifier: "..."}, {axis_id: "storage_cost", falsifier: "..."}]`。MB 正常生成。
- 如果 Epoch 2 中 MB 仍然生成了含"最优"的草稿（因为问题原文包含该词），MB 标记 `open_term_risk: ["最优"]`，CC 检查发现该词已不在 `frame.open_terms` 中（已被降解），编译通过。

**可能需要修正的场景**：如果实践中发现"概念降解"的成功率很低（大量 open terms 无法被自动拆解为轴），则可能需要允许 MB 在受限条件下将 open term 的竞争性定义作为张力源——即部分回退到"定义分歧也是一阶张力"的立场。这应该作为配置开关而非硬编码。

**一句话总结**：`open_terms` 是流水线的共享警报信号——MB 看到它会标记风险但不改变行为，CC 看到它会硬拦截，QN 看到反馈会尝试把模糊概念拆成具体轴。

---

### 问题 H：`normalize_question()` 的失败分类与恢复机制

**裁定：失败必须区分"不可恢复"（fatal）和"可恢复"（recoverable）两类，可恢复失败不得进入 MB，但允许进入精炼回路。**

最后一个比喻。侦探事务所接到两种"坏委托"：
- **不可恢复型**：委托人说"请证明这句话是假的：'这句话是假的'"。这是自指悖论，不是调查问题。事务所应该直接退回委托，附上原因。
- **可恢复型**：委托人说"帮我查查这个事情"，但没说查什么方面、涉及谁。事务所不应该直接退回，而应该说"我们初步判断可能涉及 A、B、C 三方，但需要你确认调查方向"。

**Linus 的贡献**：明确了 `Result<QuestionFrame, NormalizeError>` 的必要性，拒绝裸返回。
**康德的贡献**：将 `NormalizeError` 细分为 `NormalizeFatal`（范畴错误，如自指悖论、对抽象实体赋予非经验属性）和 `NormalizeRecoverable`（信息不足，如空轴、scope 过宽）。
**Ssyram 的贡献**：给出了精炼回路的 `RefinementSignal` 机制，使可恢复失败有了闭环修复路径。

**最终裁定**：三者的贡献互补，合并为统一方案。

```
normalize_question() 的输出：
  Ok(QuestionFrame)           → 进入 MB
  Err(NormalizeFatal)         → 终止，返回用户，附 repair_advice
  Err(NormalizeRecoverable)   → 不进入 MB，进入精炼回路
                                 （请求用户输入 / 注入外部触发器 / 重试）
```

**关键不变式**：`Ok(QuestionFrame)` 保证 `evaluation_axes.length >= 1` 且所有轴 `mode === "regulative"`。这是进入 MB 的前置条件，由类型系统强制保证，不依赖运行时检查。

**具体例子**："这句话是假的"→ `NormalizeFatal(SELF_REFERENCE_PARADOX)`，系统终止。"什么是好的教育？"→ `NormalizeRecoverable(EMPTY_AXES, stakeholders: ["学生","教师","政策制定者"])`，系统提示用户："我们识别出三类利益相关方，但无法确定评估维度。请指定您关注的方面（如学业成绩、心理健康、社会适应性）。"

**精炼回路的终止条件**：最多 `max_refinement_epochs`（建议默认 3）轮。如果 3 轮后仍为 `NormalizeRecoverable`，升级为 `NormalizeFatal(REFINEMENT_EXHAUSTED)`，终止。这防止无限精炼。

**可能需要修正的场景**：如果实践中发现 `NormalizeFatal` 和 `NormalizeRecoverable` 的边界难以稳定判定（比如某些问题在不同 LLM 版本下被分到不同类别），则可能需要将分类本身也做成可配置的规则集，而非硬编码的枚举匹配。

**一句话总结**：问题解析失败分两种——"这不是个合法问题"直接退回，"这个问题还不够清楚"允许补充信息后重试，但重试有次数上限。

---

## 第二部分：可实现性摘要

### 1. `normalize_question()` 最终接口规范

**TypeScript 类型：**

```typescript
// === 输入 ===
type ProblemStatement = {
  raw_question: string;
  context?: string;
  user_constraints?: string[];
};

type RefinementSignal = {
  rejected_draft_id: string;
  unresolved_term: string;
  offending_context: string;
  epoch: number;
};

// === 输出：成功 ===
type RegulativeAxis = {
  axis_id: string;
  label: string;
  mode: "regulative";  // 字面量类型，编译期强制
  falsifier: string;
  falsifier_independence: "INDEPENDENT" | "STAKEHOLDER_DERIVED";
  // ↑ 用于 F 裁定：决定该轴在 MB 中进入哪个 tier
};

type QuestionFrame = {
  problem_id: string;
  scope: string;
  evaluation_axes: [RegulativeAxis, ...RegulativeAxis[]];
  // ↑ 非空元组类型，编译期保证 length >= 1
  open_terms: string[];
  stakeholders: string[];
  excluded_forms: CategoryErrorTag[];
};

// === 输出：失败 ===
type CategoryErrorTag =
  | "SELF_REFERENCE_PARADOX"
  | "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY"
  | "UNFALSIFIABLE_VALUE_ASSERTION"
  | "SCOPE_UNBOUNDED";

type NormalizeFatal = {
  code: "CATEGORY_ERROR";
  tags: [CategoryErrorTag, ...CategoryErrorTag[]];
  repair_advice: string[];
};

type NormalizeRecoverable = {
  code: "INSUFFICIENT_FRAME";
  partial_stakeholders: string[];
  partial_open_terms: string[];
  missing: ("evaluation_axes" | "scope")[];
  repair_advice: string[];
};

type NormalizeError = NormalizeFatal | NormalizeRecoverable;

type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

// === 函数签名 ===
function normalize_question(
  stmt: ProblemStatement,
  refinements?: RefinementSignal[]
): Result<QuestionFrame, NormalizeError>;
```

**Python 伪代码（含失败路径）：**

```python
def normalize_question(
    stmt: ProblemStatement,
    refinements: list[RefinementSignal] = []
) -> Result[QuestionFrame, NormalizeError]:
    
    # Phase 1: 范畴检查（不可恢复失败）
    category_errors = detect_category_errors(stmt.raw_question)
    if category_errors:
        return Err(NormalizeFatal(
            code="CATEGORY_ERROR",
            tags=category_errors,
            repair_advice=generate_repair_hints(category_errors)
        ))
    
    # Phase 2: 应用精炼信号（如果有）
    effective_question = stmt.raw_question
    excluded_terms: list[str] = []
    for signal in refinements:
        # 尝试将 unresolved term 降解为轴或 scope 约束
        degradation = attempt_term_degradation(signal.unresolved_term, stmt)
        if degradation.success:
            # "最优" → axes: [throughput, latency]
            effective_question = apply_degradation(effective_question, degradation)
        else:
            excluded_terms.append(signal.unresolved_term)
    
    # Phase 3: 推断利益相关方
    stakeholders = infer_stakeholders(effective_question, stmt.context)
    
    # Phase 4: 从利益相关方冲突 + 问题结构推断评估轴
    raw_axes = infer_evaluation_axes(effective_question, stakeholders, stmt.context)
    
    # Phase 5: 强制 regulative 模式 + 验证
    validated_axes: list[RegulativeAxis] = []
    for ax in raw_axes:
        result = make_regulative_axis(ax)
        if result.ok:
            validated_axes.append(result.value)
        # 非 regulative 的轴被静默丢弃（或可选：返回错误）
    
    # Phase 6: 空轴检查（可恢复失败）
    if not validated_axes:
        return Err(NormalizeRecoverable(
            code="INSUFFICIENT_FRAME",
            partial_stakeholders=stakeholders,
            partial_open_terms=detect_open_terms(effective_question),
            missing=["evaluation_axes"],
            repair_advice=["请指定您关注的评估维度", 
                          f"已识别利益相关方: {stakeholders}"]
        ))
    
    # Phase 7: 检测 open terms
    open_terms = detect_open_terms(effective_question)
    open_terms = [t for t in open_terms if t not in excluded_terms]
    
    # Phase 8: 构造合法 QuestionFrame
    return Ok(QuestionFrame(
        problem_id=generate_id(),
        scope=infer_scope(effective_question, stmt.user_constraints),
        evaluation_axes=validated_axes,  # 保证非空
        open_terms=open_terms,
        stakeholders=stakeholders,
        excluded_forms=detect_excluded_forms(effective_question)
    ))


def make_regulative_axis(raw: dict) -> Result[RegulativeAxis, NormalizeError]:
    """构造器：强制 mode=regulative，拒绝 constitutive"""
    if raw.get("mode") and raw["mode"] != "regulative":
        return Err(NormalizeError(code="INVALID_AXIS_MODE", bad_axis_ids=[raw["axis_id"]]))
    
    # 判定 falsifier 独立性
    independence = assess_falsifier_independence(raw["falsifier"], raw.get("source_stakeholders"))
    
    return Ok(RegulativeAxis(
        axis_id=raw["axis_id"],
        label=raw["label"],
        mode="regulative",
        falsifier=raw["falsifier"],
        falsifier_independence=independence
    ))
```

---

### 2. `macro_breadth()` 最终接口规范

**TypeScript 类型：**

```typescript
// === 配置 ===
type MacroBreadthConfig = {
  max_drafts: number;                    // 硬上限，默认 6
  internal_tier_quota: number;           // 内部层配额比例，默认 0.5
  per_axis_cap: number;                  // 单轴最大草稿数，默认 2
  require_kind_diversity: boolean;       // 是否要求多种张力类型，默认 true
  max_open_term_risk_ratio: number;      // open_term 风险草稿占比上限，默认 0.5
  default_ttl: number;                   // 草稿初始 TTL，默认 3
};

// === 张力源 ===
type TensionSourceKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT";

type EpistemicTier = "INTERNAL_AXIS" | "EMPIRICAL";

type TensionCandidate = {
  candidate_id: string;
  kind: TensionSourceKind;
  tier: EpistemicTier;  // 由 falsifier_independence 决定，非硬编码
  axis_ids: string[];
  stakeholders: string[];
  claim_sketch: string;
  verifier_hint: string[];
  salience: number;       // 0..1, 层内排序用
  open_term_risk: string[]; // MB 标记的风险 open terms
};

// === 输出 ===
type HypothesisDraft = {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  tension_source: {
    kind: TensionSourceKind;
    tier: EpistemicTier;
    evidence_ref: string[];
    note: string;
  };
  verifier_hint: string[];
  open_term_risk: string[];
  ttl: number;
};

// === 错误 ===
type MacroBreadthError =
  | { code: "NO_TENSION_FOUND"; axes_tried: string[]; stakeholders_tried: string[] }
  | { code: "ALL_DRAFTS_HOMOLOGOUS"; cluster_summary: string }
  | { code: "OPEN_TERM_SATURATION"; saturated_terms: string[] };

// === 函数签名 ===
function macro_breadth(
  frame: QuestionFrame,
  config?: MacroBreadthConfig,
  external_positions?: ExternalPosition[]
): Result<HypothesisDraft[], MacroBreadthError>;
```

**Python 伪代码（含三种张力源处理逻辑和 fallback）：**

```python
def macro_breadth(
    frame: QuestionFrame,
    config: MacroBreadthConfig = DEFAULT_CONFIG,
    external_positions: list[ExternalPosition] = []
) -> Result[list[HypothesisDraft], MacroBreadthError]:
    
    # ========================================
    # Phase 1: 生成所有张力候选
    # ========================================
    candidates: list[TensionCandidate] = []
    
    # 张力源 1: EVALUATION_AXIS_SPLIT
    for axis in frame.evaluation_axes:
        splits = generate_axis_splits(axis, frame)
        for split in splits:
            tier = ("INTERNAL_AXIS" 
                    if axis.falsifier_independence == "INDEPENDENT" 
                    else "EMPIRICAL")
            candidates.append(TensionCandidate(
                kind="EVALUATION_AXIS_SPLIT",
                tier=tier,
                axis_ids=[axis.axis_id],
                claim_sketch=split.claim,
                verifier_hint=[axis.falsifier],
                open_term_risk=detect_open_term_overlap(split.claim, frame.open_terms),
                salience=split.salience,
                ...
            ))
    
    # 张力源 2: STAKEHOLDER_CONFLICT
    for pair in combinations(frame.stakeholders, 2):
        conflicts = generate_stakeholder_conflicts(pair, frame)
        for conflict in conflicts:
            candidates.append(TensionCandidate(
                kind="STAKEHOLDER_CONFLICT",
                tier="EMPIRICAL",
                stakeholders=list(pair),
                claim_sketch=conflict.claim,
                open_term_risk=detect_open_term_overlap(conflict.claim, frame.open_terms),
                salience=conflict.salience,
                ...
            ))
    
    # 张力源 3: EXTERNAL_POSITION
    for pos in external_positions[:config.max_drafts]:  # 硬上限
        candidates.append(TensionCandidate(
            kind="EXTERNAL_POSITION",
            tier="EMPIRICAL",
            claim_sketch=pos.text,
            open_term_risk=detect_open_term_overlap(pos.text, frame.open_terms),
            salience=assess_external_salience(pos, frame),
            ...
        ))
    
    # ========================================
    # Phase 2: Fallback 检查
    # ========================================
    if not candidates:
        return Err(MacroBreadthError(
            code="NO_TENSION_FOUND",
            axes_tried=[a.axis_id for a in frame.evaluation_axes],
            stakeholders_tried=frame.stakeholders
        ))
    
    # ========================================
    # Phase 3: 分层配额选择 + 贪心去重
    # ========================================
    internal_pool = [c for c in candidates if c.tier == "INTERNAL_AXIS"]
    empirical_pool = [c for c in candidates if c.tier == "EMPIRICAL"]
    
    internal_pool.sort(key=lambda c: c.salience, reverse=True)
    empirical_pool.sort(key=lambda c: c.salience, reverse=True)
    
    internal_quota = math.ceil(config.max_drafts * config.internal_tier_quota)
    empirical_quota = config.max_drafts - internal_quota
    
    # 配额让渡：内部层不足时让给经验层
    actual_internal = min(len(internal_pool), internal_quota)
    actual_empirical = min(len(empirical_pool), empirical_quota + (internal_quota - actual_internal))
    
    selected: list[TensionCandidate] = []
    
    # 贪心去重选择（同源性是动态计算的，不是预标记的）
    for pool, quota in [(internal_pool, actual_internal), (empirical_pool, actual_empirical)]:
        for candidate in pool:
            if len([s for s in selected if s.tier == candidate.tier]) >= quota:
                break
            if is_homologous_to_selected(candidate, selected):
                continue  # 跳过与已选集合同源的候选
            if count_per_axis(candidate, selected) >= config.per_axis_cap:
                continue  # 单轴上限
            selected.append(candidate)
    
    # ========================================
    # Phase 4: 同源性全灭检查
    # ========================================
    if not selected:
        return Err(MacroBreadthError(
            code="ALL_DRAFTS_HOMOLOGOUS",
            cluster_summary=summarize_homologous_clusters(candidates)
        ))
    
    # ========================================
    # Phase 5: Open term 风险饱和检查
    # ========================================
    risky_count = sum(1 for s in selected if s.open_term_risk)
    if risky_count / len(selected) > config.max_open_term_risk_ratio:
        return Err(MacroBreadthError(
            code="OPEN_TERM_SATURATION",
            saturated_terms=list(set(t for s in selected for t in s.open_term_risk))
        ))
    
    # ========================================
    # Phase 6: 转换为 HypothesisDraft
    # ========================================
    drafts = [to_hypothesis_draft(c, frame, config) for c in selected]
    return Ok(drafts)


def is_homologous_to_selected(
    candidate: TensionCandidate, 
    selected: list[TensionCandidate]
) -> bool:
    """同源性：动态计算，基于 claim_sketch 的语义相似度 + 轴重叠度"""
    for s in selected:
        axis_overlap = len(set(candidate.axis_ids) & set(s.axis_ids)) / max(len(candidate.axis_ids), 1)
        semantic_sim = compute_semantic_similarity(candidate.claim_sketch, s.claim_sketch)
        if axis_overlap > 0.8 and semantic_sim > 0.85:
            return True
    return False
```

---

### 3. 完整数据流与不变式

```
ProblemStatement
       │
       ▼
┌──────────────────────┐
│  normalize_question() │
│                      │
│  不变式:             │
│  INV-1: Ok ⟹ axes.length ≥ 1
│  INV-2: Ok ⟹ ∀axis: mode = "regulative"
│  INV-3: Err(Fatal) ⟹ 不可重试
│  INV-4: Err(Recoverable) ⟹ 可重试，≤ max_epochs
└──────┬───────────────┘
       │
       ├── Err(Fatal) ──────────────────────────→ 终止，返回用户
       │
       ├── Err(Recoverable) ──→ 精炼回路 ──→ 重新调用 normalize_question(stmt, signals)
       │                              ↑                    │
       │                              │                    │
       │                     RefinementSignal ←── CC 失败反馈
       │
       ▼ Ok(QuestionFrame)
┌──────────────────────┐
│   macro_breadth()    │
│                      │
│  前置条件:           │
│  PRE-1: frame.evaluation_axes.length ≥ 1
│  PRE-2: ∀axis: mode = "regulative"
│                      │
│  不变式:             │
│  INV-5: Ok ⟹ drafts.length ∈ [1, config.max_drafts]
│  INV-6: Ok ⟹ ¬∃(d1,d2): is_homologous(d1,d2)
│  INV-7: Ok ⟹ risky_ratio ≤ config.max_open_term_risk_ratio
│  INV-8: Err ⟹ 结构化失败，不产出空数组
└──────┬───────────────┘
       │
       ├── Err(NO_TENSION_FOUND) ──→ 请求外部立场注入 / 返回用户
       ├── Err(ALL_DRAFTS_HOMOLOGOUS) ──→ 请求外部立场注入
       ├── Err(OPEN_TERM_SATURATION) ──→ 触发 QN 精炼回路
       │
       ▼ Ok(HypothesisDraft[])
┌──────────────────────┐
│  ClarityCompiler     │
│  compile(draft, frame)│
│                      │
│  前置条件:           │
│  PRE-3: draft 来自合法 MB 输出
│  PRE-4: frame 与 draft.problem_id 匹配
│                      │
│  不变式:             │
│  INV-9:  Ok ⟹ claim 不含 frame.open_terms 中的未绑定词
│  INV-10: Ok ⟹ claim.evaluation_axis ∈ frame.evaluation_axes
│  INV-11: Err(UNBOUND_OPEN_TERM) ⟹ 产出 RefinementSignal
│  INV-12: Err(AXIS_MISMATCH) ⟹ 产出 RefinementSignal
└──────┬───────────────┘
       │
       ├── Err ──→ RefinementSignal ──→ 回到 QN 精炼回路
       │
       ▼ Ok(TestableClaim)
       │
       → 进入 Layer 2 (S4/S5 验证链)
```

**跨组件不变式：**
- **INV-GLOBAL-1**：精炼回路总轮次 ≤ `max_refinement_epochs`（默认 3）。超过后，最后一个 `NormalizeRecoverable` 升级为 `NormalizeFatal(REFINEMENT_EXHAUSTED)`。
- **INV-GLOBAL-2**：`open_terms` 在整个流水线中单调递减——每轮精炼要么将 open term 降解为轴，要么将其加入 `excluded_terms`，不允许新增。
- **INV-GLOBAL-3**：`HypothesisDraft[]` 永远不为空数组。MB 要么返回 `Ok(非空数组)`，要么返回 `Err`。下游不需要检查空数组。

---

### 4. 端到端运行 Trace

**输入**：`ProblemStatement { raw_question: "AI 是否应该被监管？" }`

---

**Epoch 1：**

**Step 1: normalize_question(stmt, [])**
```
Phase 1: 范畴检查 → 无范畴错误
Phase 2: 无精炼信号，跳过
Phase 3: 推断利益相关方 → ["AI开发者", "监管机构", "终端用户"]
Phase 4: 推断评估轴 →
  - {axis_id: "innovation_impact", label: "创新影响", mode: "regulative",
     falsifier: "若监管后AI研发投入和产出未下降则证伪",
     falsifier_independence: "INDEPENDENT"}
  - {axis_id: "public_safety", label: "公共安全", mode: "regulative",
     falsifier: "若无监管时AI事故率未高于有监管场景则证伪",
     falsifier_independence: "INDEPENDENT"}
  - {axis_id: "market_fairness", label: "市场公平性", mode: "regulative",
     falsifier: "若利益相关方满意度调查显示无显著不公则证伪",
     falsifier_independence: "STAKEHOLDER_DERIVED"}
Phase 5: 强制 regulative → 全部通过
Phase 6: 3 个轴，非空 → 通过
Phase 7: open_terms → ["AI", "监管"]
  （"AI"和"监管"在此问题中语义宽泛，标记为 open）
Phase 8: 输出 →
  Ok(QuestionFrame {
    problem_id: "q-001",
    scope: "当前全球主要经济体的AI技术治理",
    evaluation_axes: [innovation_impact, public_safety, market_fairness],
    open_terms: ["AI", "监管"],
    stakeholders: ["AI开发者", "监管机构", "终端用户"],
    excluded_forms: []
  })
```

**Step 2: macro_breadth(frame, config)**
```
Phase 1: 生成张力候选
  EVALUATION_AXIS_SPLIT:
    - C1: {kind: AXIS_SPLIT, tier: INTERNAL_AXIS, axis: innovation_impact,
           claim: "强制性AI许可制度会将研发投入降低30%以上",
           open_term_risk: ["AI"], salience: 0.9}
    - C2: {kind: AXIS_SPLIT, tier: INTERNAL_AXIS, axis: public_safety,
           claim: "无监管的AI部署在医疗领域将导致可量化的患者伤害增加",
           open_term_risk: ["AI"], salience: 0.85}
    - C3: {kind: AXIS_SPLIT, tier: STAKEHOLDER_DERIVED→EMPIRICAL, axis: market_fairness,
           claim: "AI监管合规成本将淘汰80%的中小AI企业",
           open_term_risk: ["AI", "监管"], salience: 0.7}
  STAKEHOLDER_CONFLICT:
    - C4: {kind: STAKEHOLDER, tier: EMPIRICAL, pair: [AI开发者, 监管机构],
           claim: "AI开发者的自律机制在历史上从未有效替代过外部监管",
           open_term_risk: ["AI", "监管"], salience: 0.75}
    - C5: {kind: STAKEHOLDER, tier: EMPIRICAL, pair: [终端用户, AI开发者],
           claim: "终端用户更信任政府监管而非企业自律来保障AI安全",
           open_term_risk: ["AI", "监管"], salience: 0.6}

Phase 2: 候选非空 → 继续

Phase 3: 分层配额选择 (max_drafts=6, internal_quota=0.5)
  internal_quota = ceil(6 * 0.5) = 3
  empirical_quota = 3
  
  Internal pool: [C1(0.9), C2(0.85)]  → 只有2个，actual_internal=2
  Empirical pool: [C4(0.75), C3(0.7), C5(0.6)] → actual_empirical=min(3, 3+1)=4, 但只有3个
  
  贪心去重选择:
    Internal: C1 ✓, C2 ✓ (不同轴，不同源)
    Empirical: C4 ✓, C3 ✓ (C3 vs C4: 轴不同，不同源), C5 ✓
  
  selected = [C1, C2, C4, C3, C5]  (5个)

Phase 4: 无全灭 → 继续

Phase 5: open_term_risk 检查
  risky_count = 5 (全部含 open term risk)
  ratio = 5/5 = 1.0 > 0.5 (max_open_term_risk_ratio)
  → Err(OPEN_TERM_SATURATION, saturated_terms: ["AI", "监管"])
```

**Step 3: 处理 OPEN_TERM_SATURATION → 触发 QN 精炼回路**

系统生成 `RefinementSignal`:
```
[
  {rejected_draft_id: "batch", unresolved_term: "AI", 
   offending_context: "问题核心术语过于宽泛", epoch: 1},
  {rejected_draft_id: "batch", unresolved_term: "监管", 
   offending_context: "监管形式未指定", epoch: 1}
]
```

---

**Epoch 2：**

**Step 1: normalize_question(stmt, refinement_signals)**
```
Phase 2: 应用精炼信号
  - "AI" → 降解尝试: 成功 → scope 约束: "生成式AI（LLM及多模态模型）"
  - "监管" → 降解尝试: 成功 → 新增轴: 
    {axis_id: "regulatory_form", label: "监管形式",
     falsifier: "若行业自律与政府立法在事故预防效果上无统计差异则证伪",
     falsifier_independence: "INDEPENDENT"}

Phase 7: open_terms → []  (两个 open term 均已降解)

输出 → Ok(QuestionFrame {
  problem_id: "q-001-r1",
  scope: "当前全球主要经济体对生成式AI（LLM及多模态模型）的技术治理",
  evaluation_axes: [innovation_impact, public_safety, market_fairness, regulatory_form],
  open_terms: [],
  stakeholders: ["AI开发者", "监管机构", "终端用户"],
  excluded_forms: []
})
```

**Step 2: macro_breadth(frame_v2, config)**
```
Phase 1: 生成张力候选 (现在有4个轴，open_terms为