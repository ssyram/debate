# 模块名：问题摄取（Question Ingestion / QN 节点）

<!-- import from 00_shared_types: QuestionFrame, RegulativeAxis, CategoryErrorTag, RefinementSignal -->

## 一句话定位

接收用户原始问题字符串，输出结构化的 `QuestionFrame`（含评估轴、利益相关方、开放术语），或者返回分类明确的失败信号；是整个认知引擎的入口守门人，也是精炼回路的枢纽节点。

---

## 通俗解释

想象一个侦探事务所接到委托。委托人说的话往往模糊——"帮我查清楚这件事"。QN 节点就是这个所里的首席接案员，负责把委托人的模糊诉求翻译成具体的"调查方向"（评估轴）。

接案员要做三件事：
1. 先判断这个委托是不是"根本不可能调查的"（自指悖论、无界问题），是的话直接退回。
2. 如果委托本身还行，但细节不够，就提出具体问题请委托人补充，然后重试（最多 3 次）。
3. 成功后，给出完整的调查方向清单，确保每个方向都是"暂定的"（regulative），没有哪个方向被宣布为不可质疑的铁律。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: QuestionFrame, RegulativeAxis, CategoryErrorTag

interface ProblemStatement {
  raw_question: string;
  context?: string;
  user_constraints?: string[];
}

interface RefinementSignal {
  rejected_draft_id: string;    // 触发精炼的草稿 ID（或 "batch"）
  unresolved_term: string;      // 无法绑定的开放术语
  offending_context: string;    // 出错上下文描述
  epoch: number;
}

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

function normalize_question(
  stmt: ProblemStatement,
  refinements?: RefinementSignal[]
): Result<QuestionFrame, NormalizeError>;
```

---

## 伪代码实现（Python 风格）

```python
# 常量配置
MAX_REFINEMENT_EPOCHS = 3       # 精炼回路最大轮次
CONFIDENCE_THRESHOLD = 0.90     # CategoryError 的置信度门槛

# 核心词表（详细规则见 question_ingestion_category 模块）
SELF_REF_ANCHORS = {"这句话", "本命题", "此陈述", "this sentence", "this statement"}
LIAR_PREDICATES  = {"是假的", "不是真的", "is false", "is not true"}
META_MARKERS     = {"请分析", "为什么构成悖论", "analyze", "explain why"}
ABSTRACT_CORE    = {"数字", "集合", "函数", "命题", "定理", "证明", "number", "set", "function"}
NON_EMP_PRED     = {"幸运", "神圣", "被诅咒", "孤独", "lucky", "sacred", "cursed", "lonely"}
VALUE_MARKERS    = {"更好", "更高贵", "最重要", "应该", "better", "superior", "should"}
BROAD_QUANTIFIERS = {"所有", "一切", "人类", "世界", "万物", "all", "humanity"}
RESEARCH_VERBS    = {"为什么", "如何", "机制", "原因", "why", "how", "mechanism"}


def normalize_question(
    stmt: ProblemStatement,
    refinements: list[RefinementSignal] = []
) -> Result[QuestionFrame, NormalizeError]:

    # ======================================================
    # Phase 1: 范畴检查（不可恢复失败，早期短路）
    # ======================================================
    hits = detect_category_errors(stmt.raw_question)
    if hits:
        return Err(NormalizeFatal(
            code="CATEGORY_ERROR",
            tags=[h.tag for h in hits],
            repair_advice=generate_repair_hints(hits)
        ))

    # ======================================================
    # Phase 2: 应用精炼信号（概念降解）
    # ======================================================
    effective_question = stmt.raw_question
    excluded_terms: list[str] = []

    for signal in refinements:
        degradation = attempt_term_degradation(signal.unresolved_term, stmt)
        if degradation.success:
            # 将开放术语降解为评估轴或 scope 约束
            # 例：把 "最优" 降解为 axes: [throughput, latency]
            effective_question = apply_degradation(effective_question, degradation)
        else:
            excluded_terms.append(signal.unresolved_term)

    # ======================================================
    # Phase 3: 推断利益相关方
    # ======================================================
    stakeholders = infer_stakeholders(effective_question, stmt.context)

    # ======================================================
    # Phase 4: 从利益相关方冲突 + 问题结构推断评估轴
    # ======================================================
    raw_axes = infer_evaluation_axes(effective_question, stakeholders, stmt.context)

    # ======================================================
    # Phase 5: 强制 regulative 模式，评估 falsifier 独立性
    # ======================================================
    validated_axes: list[RegulativeAxis] = []
    for ax in raw_axes:
        result = make_regulative_axis(ax)
        if result.ok:
            validated_axes.append(result.value)
        # 非 regulative 的轴被静默丢弃（constitutive 轴不合法）

    # ======================================================
    # Phase 6: 空轴检查（可恢复失败）
    # ======================================================
    if not validated_axes:
        return Err(NormalizeRecoverable(
            code="INSUFFICIENT_FRAME",
            partial_stakeholders=stakeholders,
            partial_open_terms=detect_open_terms(effective_question),
            missing=["evaluation_axes"],
            repair_advice=[
                "请指定您关注的评估维度",
                f"已识别利益相关方：{stakeholders}"
            ]
        ))

    # ======================================================
    # Phase 7: 检测残余 open terms
    # ======================================================
    open_terms = detect_open_terms(effective_question)
    open_terms = [t for t in open_terms if t not in excluded_terms]

    # ======================================================
    # Phase 8: 构造合法 QuestionFrame，归一化权重
    # ======================================================
    n = len(validated_axes)
    default_weight = 1.0 / n
    for ax in validated_axes:
        if not hasattr(ax, "weight") or ax.weight is None:
            ax.weight = default_weight
        ax.epsilon = 0.10  # 初始 epsilon，由 scoring_epsilon 模块动态更新

    return Ok(QuestionFrame(
        problem_id=generate_id("q"),
        scope=infer_scope(effective_question, stmt.user_constraints),
        evaluation_axes=validated_axes,
        open_terms=open_terms,
        stakeholders=stakeholders,
        excluded_forms=detect_excluded_forms(effective_question)
    ))


def make_regulative_axis(raw: dict) -> Result[RegulativeAxis, NormalizeError]:
    """构造器：强制 mode=regulative，拒绝 constitutive"""
    if raw.get("mode") and raw["mode"] != "regulative":
        return Err(NormalizeError(code="INVALID_AXIS_MODE", bad_axis_ids=[raw["axis_id"]]))

    independence = assess_falsifier_independence(
        raw["falsifier"], raw.get("source_stakeholders", [])
    )

    return Ok(RegulativeAxis(
        axis_id=raw["axis_id"],
        label=raw["label"],
        mode="regulative",
        weight=raw.get("weight", None),
        epsilon=0.10,
        falsifier=raw["falsifier"],
        falsifier_independence=independence
    ))


def detect_category_errors(raw_q: str) -> list[CategoryErrorHit]:
    """
    判定顺序：SRP → NEAOAE → UVA → SU（从最确定到最不确定）
    早期命中短路后续检测。
    """
    hits = []

    srp = _detect_self_reference_paradox(raw_q)
    if srp and srp.confidence >= CONFIDENCE_THRESHOLD:
        hits.append(srp)
        return hits  # 短路

    neaoae = _detect_non_empirical_attribute(raw_q)
    if neaoae and neaoae.confidence >= CONFIDENCE_THRESHOLD:
        hits.append(neaoae)
        return hits

    uva = _detect_unfalsifiable_value(raw_q)  # 规则 + 结构化 LLM 辅助
    if uva and uva.confidence >= CONFIDENCE_THRESHOLD:
        hits.append(uva)
        return hits

    su = _detect_scope_unbounded(raw_q)
    if su and su.confidence >= CONFIDENCE_THRESHOLD:
        hits.append(su)

    return hits
```

---

## 关键约束与不变式

| 编号 | 约束 | 级别 |
|------|------|------|
| INV-01 | `Ok(QuestionFrame)` ⟹ `evaluation_axes.length ≥ 1` | 编译期（非空元组类型） |
| INV-02 | `Ok(QuestionFrame)` ⟹ `∀axis: mode === "regulative"` | 编译期（字面量类型） |
| INV-03 | `Ok(QuestionFrame)` ⟹ `sum(axis.weight) ≈ 1.0`（容差 0.001） | 运行时断言 |
| INV-04 | `Err(NormalizeFatal)` ⟹ 不可重试，pipeline 终止 | 接口约定 |
| INV-05 | `Err(NormalizeRecoverable)` ⟹ 可重试，但总轮次 ≤ `MAX_REFINEMENT_EPOCHS` | 运行时计数器 |
| INV-06 | 超过 `MAX_REFINEMENT_EPOCHS` 轮的 `NormalizeRecoverable` 升级为 `NormalizeFatal(REFINEMENT_EXHAUSTED)` | 运行时强制 |
| INV-07 | `open_terms` 在整个流水线中单调递减（每轮精炼不允许新增） | 运行时断言 |
| INV-08 | `HypothesisDraft[]` 永远不为空数组（MB 要么 Ok(非空)，要么 Err） | 接口约定 |
| INV-09 | `CategoryErrorHit.confidence < 0.9` 时不触发 fatal，仅标记为 INDETERMINATE | 运行时条件 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"

### Epoch 1：第一次调用

```
输入：ProblemStatement { raw_question: "如何设计一个公平的碳排放交易机制？" }

Phase 1: detect_category_errors()
  → SRP 检查：无自指锚点 → SKIP
  → NEAOAE 检查："碳排放交易机制"∉ ABSTRACT_CORE → SKIP
  → UVA 检查："公平"是价值词 → 规则层命中
    桥接模板匹配：
      comparative_outcome: {agent_A: "自由市场", agent_B: "配额分配",
                             outcome: "减排效果", metric: "CO₂ 减少量"}
      关键 slot 填充率 = 2/2 = 1.0 > 0.35 → 放行（有经验桥接路径）
  → SU 检查："如何"是研究问法动词 → 排除 → SKIP
  → 全部通过

Phase 3: 推断利益相关方
  → ["发展中国家政府", "发达国家政府", "能源密集型企业", "环保组织", "国际监管机构"]

Phase 4: 推断评估轴
  → ax_economic: "经济效率"
      falsifier: "若碳价格信号未导致年减排量增加则证伪"
      falsifier_independence: INDEPENDENT
  → ax_equity: "分配公平性"
      falsifier: "若发展中国家承担的边际减排成本超过发达国家则证伪"
      falsifier_independence: INDEPENDENT
  → ax_implement: "实施可行性"
      falsifier: "若超过 50% 的参与方选择退出则证伪"
      falsifier_independence: STAKEHOLDER_DERIVED（依赖参与方态度调查）

Phase 6: 3 个轴，非空 → 通过

Phase 7: open_terms = ["公平"]（"公平"在此语境语义宽泛）

Phase 8: 输出 Ok(QuestionFrame {
  problem_id: "q-carbon-001",
  scope: "全球碳排放总量控制机制的顶层设计，时间范围 2024-2035",
  evaluation_axes: [ax_economic(w=0.33), ax_equity(w=0.33), ax_implement(w=0.33)],
  open_terms: ["公平"],
  stakeholders: ["发展中国家政府", "发达国家政府", "能源密集型企业", "环保组织", "国际监管机构"]
})
```

### 当 macro_breadth() 返回 OPEN_TERM_SATURATION 时触发精炼回路

```
收到 RefinementSignal:
  { unresolved_term: "公平", offending_context: "草稿均含无绑定价值词 '公平'", epoch: 1 }

Phase 2（精炼回路）: attempt_term_degradation("公平")
  → 成功：将 "公平" 拆解为两个具体维度：
    1. ax_burden_share: "负担分担原则"
       falsifier: "若历史排放与当前义务之比不等于各方 GDP/排放基准比则证伪"
    2. ax_capacity: "能力差异原则"
       falsifier: "若相同减排要求适用于 GDP 差异 10 倍以上的国家则证伪"
  → open_terms: []（"公平"已降解）

Phase 8: 输出 Ok(QuestionFrame_v2 {
  problem_id: "q-carbon-001-r1",
  scope: "...",
  evaluation_axes: [ax_economic, ax_equity→ax_burden_share, ax_capacity, ax_implement],
  open_terms: [],  // 单调递减，从 ["公平"] 变为 []
  ...
})
```

---

## ⚠️ 已知设计缺口

无本模块特有的未裁定缺口。以下是需要注意的边界情况：

1. **哥德尔式编码自指**：SELF_REFERENCE_PARADOX 规则仅覆盖显式 liar-form，编码自指漏放（by design）。如果用户构造了"第 N 行命题是假的"式问题，会进入 MB 阶段，但不会导致系统崩溃。

2. **UVA 的桥接模板集完备性**：桥接模板匹配失败判定的是"当前系统无法桥接"而非"绝对不可证伪"。随模板集扩展，部分之前被 fatal 的问题可能被放行——这是 by design 的行为，必须在产品文档中声明。

3. **研究问法排除过宽**（待修正）：`_detect_scope_unbounded()` 中"为什么"会排除包含广域量词的主语，导致"为什么一切存在？"漏放。修正方案：研究问法排除仅在主语非广域量词时生效。
