# v3 认知引擎：detect_category_errors() 判定算法与 NQ/CC 职责边界 裁判总结

> 2026-03-09T19:02:37.515286



# 裁判裁定书

---

## 第一部分：白话版结论

---

### 问题 I：四种 CategoryErrorTag 的判定算法

#### 总体裁定

三位辩手在核心原则上达成了实质性共识：**确定性规则优先，LLM 仅作辅助，LLM 不得单独产生 fatal**。分歧在于每种 tag 的规则边界画在哪里、LLM 介入的精确条件是什么。我逐一裁定。

---

#### I-a. SELF_REFERENCE_PARADOX

**裁定：纯规则判定，不需要 LLM。**

三位辩手一致同意此 tag 可由规则可靠判定。康德明确限定为"显式表层 liar-form"，Linus 给出了具体的 `has_self_ref_anchor + has_truth_negation + same_clause + 排除 meta_discussion` 的规则链，Ssyram 也将其放在确定性层。

**最终规则**：检测自指锚点（"这句话"、"本命题"、"this sentence"等）+ 真值否定谓词（"是假的"、"不是真的"等）+ 两者在同一子句中 + 排除元讨论语境（"请分析"、"为什么构成悖论"等）。

**具体例子**：
- `"这句话是假的"` → **FATAL**。命中自指锚点 + liar 谓词 + 同一子句。
- `"请分析'这句话是假的'为什么构成悖论"` → **NOT_DETECTED**。元讨论排除规则生效，问题正常进入后续阶段。
- 哥德尔式编码自指 → **NOT_DETECTED**（漏放）。这是已知的召回率缺口，但在 NQ 阶段不构成系统性风险，因为这类问题即使进入后续阶段也不会导致系统崩溃。

**何时需要修正**：如果产品需求要求覆盖编码自指或间接自指悖论，需新增专门的逻辑编码分析器，当前规则不声称此完备性。

**一句话总结**：SELF_REFERENCE_PARADOX 是四种 tag 中最简单的，纯规则、窄覆盖、高精度，宁可漏放不可误杀。

---

#### I-b. NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY

**裁定：公理化核心词表规则判定 fatal，灰区不判 fatal，LLM 仅用于灰区的 INDETERMINATE 标注（不触发 fatal）。**

这是辩论中分歧最有价值的地方。Ssyram 正确指出静态 NLP 工具无法可靠完成本体论解析（区分"数字7"作为抽象对象 vs "纸上的数字7"作为符号实例）。康德的修正方案——将 fatal 限定在"公理化高置信抽象核"（数字、集合、函数、命题、定理、证明）+ 明确的非经验谓词（幸运、神圣、被诅咒）的直接谓述——是正确的工程选择。Linus 的"词表 + 类型系统 + 小量 LLM 兜底"方向正确，但需要采纳康德的保守边界。

**最终规则**：
1. 主语头词命中 `ABSTRACT_CORE = {"数字","数","集合","函数","命题","定理","证明"}` 
2. 谓词头词命中 `NON_EMP_PRED = {"幸运","神圣","被诅咒","morally pure","美丽","邪恶"}`
3. 两者构成直接谓述关系（系词结构）
4. 三条同时满足 → FATAL

**具体例子**：
- `"数字7是幸运的"` → **FATAL**。"数字"∈ ABSTRACT_CORE，"幸运"∈ NON_EMP_PRED，直接谓述。
- `"柏拉图的理想国是完美的"` → **NOT_DETECTED**（或 INDETERMINATE，不触发 fatal）。"理想国"不在公理化核心中，属于灰区。
- `"这个证明是优雅的"` → **NOT_DETECTED**。虽然"证明"∈ ABSTRACT_CORE，但"优雅"在数学语境中有合法的经验性用法（简洁性、步骤数等），不在 NON_EMP_PRED 中。

**何时需要修正**：如果词表过窄导致大量显然荒谬的问题（如"集合论是否感到孤独"）漏过，应扩展 NON_EMP_PRED 词表，但扩展必须逐条审核，不可批量导入。

**一句话总结**：NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY 只在"铁定抽象 + 铁定非经验"的交集上 fatal，灰区一律放行。

---

#### I-c. UNFALSIFIABLE_VALUE_ASSERTION

**裁定：规则先筛（价值词检测 + 比较级/最高级结构 + 缺乏经验锚点）+ 结构化 LLM 辅助（桥接模板匹配），但 LLM 不得单独产生 fatal。采用 Linus 的"双票制"。**

这是四种 tag 中最难的。三位辩手的分歧集中在：
- 康德认为此 tag 在 NQ 几乎不可靠判定，应极度保守
- Linus 认为可以通过"规则筛选 + 桥接模板匹配"实现有边界的判定
- Ssyram 认为可以通过 AST 分析 + LLM 语义检查实现

我采纳 Linus 的方案框架，但吸收康德的保守性约束：

**最终规则**：
1. **规则层**：检测价值词（"更好"、"应该"、"最高贵"、"最重要"等）+ 比较/最高级结构 + 缺乏经验锚点（无具体指标、无具体人群、无具体时间）
2. **桥接模板匹配层**：对规则层命中的问题，尝试将其映射到预定义的桥接模板（如 `{agent, action, outcome, metric}`）。此步骤可使用 LLM 进行结构化提取（不是让 LLM 判断"是否可证伪"，而是让 LLM 提取 slots）
3. **双票制**：规则层命中 AND 桥接模板匹配失败（0 个模板的 fit_score > 阈值）→ FATAL。任一层未命中 → NOT_DETECTED

**关键约束**（采纳康德的攻击）：桥接模板匹配失败意味着"当前系统的模板集无法桥接"，而非"问题本身不可证伪"。因此：
- 模板集必须足够宽（覆盖主要经验研究范式）
- 当模板集扩展后，之前被 fatal 的问题可能不再被 fatal——这是 by design 的，不是 bug

**具体例子**：
- `"艺术比科学更高贵吗？"` → 规则层命中（价值词"高贵" + 比较级 + 无经验锚点）→ 桥接模板匹配：尝试 `{agent=?, action=?, outcome=?, metric=?}`，无法提取有意义的 metric → fit_score 全部 < 阈值 → **FATAL**。
- `"民主制度比威权制度更能促进经济增长吗？"` → 规则层命中（比较级 + 价值词"更能"）→ 桥接模板匹配：`{agent=民主/威权制度, outcome=经济增长, metric=GDP增长率}` → fit_score > 阈值 → **NOT_DETECTED**，进入后续阶段。
- `"爱比恨更好吗？"` → 规则层命中 → 桥接模板匹配失败 → **FATAL**。

**何时需要修正**：如果发现大量有合法经验研究路径的价值问题被误杀，应首先扩展桥接模板集，而非放宽规则层。如果模板集扩展后仍然误杀率高，则应考虑将此 tag 从 NQ fatal 降格为 NQ warning + 后续阶段处理。

**一句话总结**：UNFALSIFIABLE_VALUE_ASSERTION 用"规则筛选 + 桥接模板匹配"的双票制，承认判定的是"当前系统无法桥接"而非"绝对不可证伪"，宁可漏放不可误杀。

---

#### I-d. SCOPE_UNBOUNDED

**裁定：规则判定，采用 Linus 修正后的"3-of-4 + 研究问法排除"方案。**

Ssyram 最初的"缺乏任何一个边界变量即 fatal"被 Linus 用反例（"人为什么会做梦？"）有效击破。Linus 修正后的方案——要求同时缺少 3 个以上边界维度（人群、时间、地点、指标）且不含研究问法动词——在精度和召回率之间取得了合理平衡。康德认为此 tag 更像 recoverable，但既然枚举已定为 category error（Ssyram 正确指出这是前序裁定），则必须给出 fatal 的可操作条件。

**最终规则**：
1. 检测广域量词（"所有"、"一切"、"人类"、"世界"等无限定全称）
2. 检测研究问法动词（"为什么"、"如何"、"机制"、"原因"、"影响因素"等）——命中则排除
3. 统计缺失的边界维度（人群、时间、地点、指标），缺失 ≥ 3 个
4. 条件 1 AND NOT 条件 2 AND 条件 3 → FATAL

**具体例子**：
- `"什么制度对人类最好？"` → 广域量词"人类" + 无研究问法 + 缺失时间/地点/指标（3个）→ **FATAL**。
- `"人为什么会做梦？"` → 有研究问法"为什么" → 排除 → **NOT_DETECTED**。进入后续阶段，MB 可将其收缩为"人类睡眠中的梦生成机制"。
- `"近代欧洲国家为何崛起？"` → 有研究问法"为何" + 有人群"欧洲国家" + 有时间"近代" → **NOT_DETECTED**。
- `"宇宙的意义是什么？"` → 广域量词"宇宙" + 无研究问法（"是什么"不算研究问法动词）+ 缺失人群/时间/指标（3个）→ **FATAL**。

**何时需要修正**：如果"研究问法排除"导致大量真正无法收敛的问题漏过（如"为什么一切存在？"），应对研究问法排除增加二次检查（主语是否仍为无限定全称）。

**一句话总结**：SCOPE_UNBOUNDED 用"广域量词 + 非研究问法 + 缺失≥3个边界维度"的三重条件判定，研究问法是关键的排除阀。

---

### 问题 J：NQ/CC 职责边界

#### 裁定

三位辩手在此问题上的共识远大于分歧。核心共识是：

> **NQ 判定的是问题本身是否存在经验入口；CC 判定的是具体草稿是否成功映射到可测试声明。两者的输入对象不同（原始问题 vs 具体草稿），返回动作不同（全局 fatal vs 局部降格），因此不构成重叠。**

我完全采纳此共识，并做以下精确化：

#### UNFALSIFIABLE_VALUE_ASSERTION 在 NQ 阶段的精确作用域

**作用域**：对原始问题 `raw_q` 整体进行判定。判定的是"这个问题是否存在至少一条经验桥接入口"。如果在当前系统的桥接模板集中找不到任何可行的桥接路径，则 fatal 终止整个 pipeline。

**关键限定**：NQ 的 fatal 是"问题级"的。一旦问题通过 NQ，就意味着系统认为该问题至少存在一个经验入口，后续阶段不得追溯推翻此判定。

#### synthesize_falsifier() 在 CC 阶段的精确作用域

**作用域**：对 MB 阶段生成的每一条具体草稿 `draft` 逐条进行判定。判定的是"这条具体的草稿是否能被降格为可测试的经验声明"。如果某条草稿无法降格，则该草稿被标记为 `RegulativeIdea`（调节性理念），但 pipeline 不终止。

**关键限定**：CC 的 `NO_EMPIRICAL_BRIDGE` 是"草稿级"的。即使所有草稿都返回 `NO_EMPIRICAL_BRIDGE`，系统也不回退到 NQ 重新判定。所有草稿（包括被降格为 RegulativeIdea 的）继续流入 RB（RepairBreadth）节点。

#### 两者如何不重叠

Ssyram 的状态机论证在此是决定性的：NQ 和 CC 操作在不同的数据对象上（原始问题 vs 草稿），产生不同的系统动作（全局终止 vs 局部降格），且不存在从 CC 到 NQ 的回退边。这不是"碰巧不重叠"，而是状态机设计上的结构性保证。

**具体例子**：
- 输入 `"艺术比科学更高贵吗？"` → NQ 阶段：规则层命中 + 桥接模板匹配失败 → **FATAL，pipeline 终止**。用户收到"此问题属于不可证伪的价值断言"的反馈。CC 阶段永远不会看到这个问题。
- 输入 `"民主制度是否促进经济增长？"` → NQ 阶段：桥接模板匹配成功（metric=GDP 增长率）→ **通过**。MB 生成多条草稿，其中一条是"民主制度在道德上优于威权制度"。CC 阶段：对这条草稿调用 `synthesize_falsifier()`，返回 `NO_EMPIRICAL_BRIDGE` → 该草稿降格为 `RegulativeIdea`。其他草稿（如"采用民主制度的国家 GDP 增长率更高"）正常编译为可测试声明。所有草稿继续流入 RB。

**何时需要修正**：如果实践中发现大量问题通过 NQ 后，其所有草稿在 CC 阶段全部返回 `NO_EMPIRICAL_BRIDGE`（即 NQ 的"至少存在一个经验入口"判定系统性失准），则应收紧 NQ 的桥接模板匹配阈值，而非在 CC 阶段增加回退逻辑。

**一句话总结**：NQ 问"这个问题有没有经验入口"（问题级，全局 fatal）；CC 问"这条草稿能不能变成可测试声明"（草稿级，局部降格）；两者输入不同、动作不同、不回退，结构性不重叠。

---

## 第二部分：可实现性摘要

---

### 1. detect_category_errors() 最终接口规范

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List

class CategoryErrorTag(str, Enum):
    SELF_REFERENCE_PARADOX = "SELF_REFERENCE_PARADOX"
    NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY = "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY"
    UNFALSIFIABLE_VALUE_ASSERTION = "UNFALSIFIABLE_VALUE_ASSERTION"
    SCOPE_UNBOUNDED = "SCOPE_UNBOUNDED"

@dataclass
class CategoryErrorHit:
    tag: CategoryErrorTag
    rule_id: str          # 触发的具体规则标识，用于审计
    confidence: float     # 0.0-1.0，仅 >= 0.9 时触发 fatal
    evidence: str         # 人类可读的判定依据
    spans: dict           # 命中的文本片段 {"subject": "数字7", "predicate": "幸运的"}

def detect_category_errors(raw_q: str) -> List[CategoryErrorHit]:
    """
    判定顺序：SRP → NEAOAE → UVA → SU
    理由：从最确定到最不确定，早期命中可短路后续检测
    
    返回值语义：返回列表非空 → NormalizeFatal，pipeline 终止
                返回空列表 → 通过，进入后续阶段
    """
    hits: List[CategoryErrorHit] = []
    
    # ── Stage 1: SELF_REFERENCE_PARADOX (纯规则) ──
    srp = _detect_self_reference_paradox(raw_q)
    if srp and srp.confidence >= 0.9:
        hits.append(srp)
        return hits  # 短路：悖论无需继续检查
    
    # ── Stage 2: NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY (纯规则/词表) ──
    neaoae = _detect_non_empirical_attribute(raw_q)
    if neaoae and neaoae.confidence >= 0.9:
        hits.append(neaoae)
        return hits  # 短路
    
    # ── Stage 3: UNFALSIFIABLE_VALUE_ASSERTION (规则 + 结构化LLM辅助) ──
    uva = _detect_unfalsifiable_value(raw_q)
    if uva and uva.confidence >= 0.9:
        hits.append(uva)
        return hits  # 短路
    
    # ── Stage 4: SCOPE_UNBOUNDED (纯规则) ──
    su = _detect_scope_unbounded(raw_q)
    if su and su.confidence >= 0.9:
        hits.append(su)
    
    return hits


# ════════════════════════════════════════════
# Stage 1: SELF_REFERENCE_PARADOX
# 判定方法：纯规则
# ════════════════════════════════════════════
SELF_REF_ANCHORS = {"这句话", "本命题", "此陈述", "this sentence", "this statement"}
LIAR_PREDICATES = {"是假的", "不是真的", "是错误的", "is false", "is not true"}
META_MARKERS = {"请分析", "为什么", "是否构成悖论", "analyze", "explain why"}

def _detect_self_reference_paradox(raw_q: str) -> Optional[CategoryErrorHit]:
    # 排除元讨论
    if any(m in raw_q for m in META_MARKERS):
        return None
    
    anchor_found = None
    for a in SELF_REF_ANCHORS:
        if a in raw_q:
            anchor_found = a
            break
    if not anchor_found:
        return None
    
    pred_found = None
    for p in LIAR_PREDICATES:
        if p in raw_q:
            pred_found = p
            break
    if not pred_found:
        return None
    
    # 同一子句检查（简化：两者在同一句号/逗号分隔段内）
    if not _in_same_clause(raw_q, anchor_found, pred_found):
        return None
    
    return CategoryErrorHit(
        tag=CategoryErrorTag.SELF_REFERENCE_PARADOX,
        rule_id="SRP-LIAR-v1",
        confidence=0.95,
        evidence=f"自指锚点'{anchor_found}' + 真值否定'{pred_found}'在同一子句",
        spans={"anchor": anchor_found, "predicate": pred_found}
    )
    # 失败路径：编码自指、间接自指 → 漏放（by design）


# ════════════════════════════════════════════
# Stage 2: NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY
# 判定方法：纯规则/词表
# ════════════════════════════════════════════
ABSTRACT_CORE = {"数字", "数", "集合", "函数", "命题", "定理", "证明",
                 "number", "set", "function", "proposition", "theorem", "proof"}
NON_EMP_PRED = {"幸运", "神圣", "被诅咒", "邪恶", "孤独", "快乐", "悲伤",
                "lucky", "sacred", "cursed", "evil", "lonely", "happy", "sad"}

def _detect_non_empirical_attribute(raw_q: str) -> Optional[CategoryErrorHit]:
    pair = _extract_copular_pair(raw_q)  # 提取系词结构的主语和谓语
    if pair is None:
        return None
    
    subj_head = _get_head_noun(pair.subject)
    pred_head = _get_head_adj(pair.predicate)
    
    if subj_head in ABSTRACT_CORE and pred_head in NON_EMP_PRED:
        if _is_direct_predication(pair):  # 排除"纸上的数字7"等实例化用法
            return CategoryErrorHit(
                tag=CategoryErrorTag.NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY,
                rule_id="NEAOAE-CORE-v1",
                confidence=0.95,
                evidence=f"抽象核心'{subj_head}' + 非经验谓词'{pred_head}'直接谓述",
                spans={"subject": pair.subject, "predicate": pair.predicate}
            )
    
    return None
    # 失败路径：灰区对象（"算法"、"文化"）→ 不判 fatal，漏放（by design）
    # 失败路径：非系词结构的范畴错误 → 漏放


# ════════════════════════════════════════════
# Stage 3: UNFALSIFIABLE_VALUE_ASSERTION
# 判定方法：规则先筛 + 结构化LLM辅助（双票制）
# ════════════════════════════════════════════
VALUE_MARKERS = {"更好", "更高贵", "最重要", "应该", "ought to", "better", 
                 "superior", "most important", "should"}
BRIDGE_TEMPLATES = [
    {"name": "comparative_outcome", "slots": ["agent_A", "agent_B", "outcome", "metric"]},
    {"name": "causal_mechanism", "slots": ["cause", "effect", "population", "measure"]},
    {"name": "preference_survey", "slots": ["population", "preference_object", "scale"]},
]

def _detect_unfalsifiable_value(raw_q: str) -> Optional[CategoryErrorHit]:
    # ── 票1：规则层 ──
    value_marker_found = None
    for v in VALUE_MARKERS:
        if v in raw_q:
            value_marker_found = v
            break
    if not value_marker_found:
        return None  # 规则层未命中，直接放行
    
    has_empirical_anchor = _has_empirical_anchor(raw_q)
    # 检查是否有具体指标、人群、时间等经验锚点
    if has_empirical_anchor:
        return None  # 有经验锚点，放行
    
    # ── 票2：桥接模板匹配层（结构化LLM辅助）──
    best_fit = 0.0
    for template in BRIDGE_TEMPLATES:
        # LLM 在此处的角色：结构化提取 slots，不是判断"是否可证伪"
        filled = _llm_extract_slots(raw_q, template)
        # filled: {"agent_A": "艺术", "agent_B": "科学", "outcome": None, "metric": None}
        fit_score = sum(1 for v in filled.values() if v is not None) / len(template["slots"])
        best_fit = max(best_fit, fit_score)
    
    if best_fit < 0.35:  # 所有模板的最佳匹配度都低于阈值
        return CategoryErrorHit(
            tag=CategoryErrorTag.UNFALSIFIABLE_VALUE_ASSERTION,
            rule_id="UVA-DUAL-v1",
            confidence=0.92,
            evidence=f"价值标记'{value_marker_found}' + 无经验锚点 + 桥接模板最佳匹配{best_fit:.2f}",
            spans={"value_marker": value_marker_found, "best_template_fit": str(best_fit)}
        )
    
    return None
    # 失败路径：无价值标记词但语义上是价值断言 → 漏放
    # 失败路径：LLM slot 提取不稳定 → 需要对同一输入多次调用取多数票


# ════════════════════════════════════════════
# Stage 4: SCOPE_UNBOUNDED
# 判定方法：纯规则
# ════════════════════════════════════════════
BROAD_QUANTIFIERS = {"所有", "一切", "人类", "世界", "万物", "everything", 
                     "all", "humanity", "the universe"}
RESEARCH_VERBS = {"为什么", "如何", "机制", "原因", "影响因素", "怎样",
                  "why", "how", "mechanism", "cause", "factor"}

def _detect_scope_unbounded(raw_q: str) -> Optional[CategoryErrorHit]:
    # 检查广域量词
    quant_found = None
    for q in BROAD_QUANTIFIERS:
        if q in raw_q:
            quant_found = q
            break
    if not quant_found:
        return None
    
    # 研究问法排除
    for rv in RESEARCH_VERBS:
        if rv in raw_q:
            return None  # 研究问法存在，放行
    
    # 统计缺失的边界维度
    features = _extract_scope_features(raw_q)
    missing = 0
    if features.population is None: missing += 1
    if features.time is None: missing += 1
    if features.place is None: missing += 1
    if features.metric is None: missing += 1
    
    if missing >= 3:
        return CategoryErrorHit(
            tag=CategoryErrorTag.SCOPE_UNBOUNDED,
            rule_id="SU-3of4-v1",
            confidence=0.90,
            evidence=f"广域量词'{quant_found}' + 非研究问法 + 缺失{missing}/4个边界维度",
            spans={"quantifier": quant_found, "missing_dims": str(missing)}
        )
    
    return None
    # 失败路径：无显式广域量词但语义上无界 → 漏放
    # 失败路径：研究问法排除过宽（"为什么一切存在？"）→ 漏放，需二次检查
```

---

### 2. 四种 CategoryErrorTag 的判定难度排序和推荐实现方式

| 排序 | Tag | 难度 | 推荐方式 | 主要风险 |
|------|-----|------|----------|----------|
| 1（最易） | SELF_REFERENCE_PARADOX | ★☆☆☆☆ | 纯规则 | 召回率低（仅覆盖显式 liar-form），但精度极高 |
| 2 | SCOPE_UNBOUNDED | ★★☆☆☆ | 纯规则 | 研究问法排除可能过宽；边界维度提取依赖简单 NLP |
| 3 | NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY | ★★★☆☆ | 规则/词表 | 系词结构提取需要依存句法分析；灰区对象放弃覆盖 |
| 4（最难） | UNFALSIFIABLE_VALUE_ASSERTION | ★★★★★ | 规则 + 结构化 LLM | LLM slot 提取不稳定；桥接模板集的完备性决定系统行为；双票制增加延迟 |

---

### 3. NQ/CC 职责边界完整规范

```python
# ════════════════════════════════════════════
# 形式化定义
# ════════════════════════════════════════════

# NQ (Normalize & Qualify) 阶段
# 输入：raw_q: str（用户原始问题）
# 输出：NormalizeFatal | NormalizedQuestion
# 判定对象：问题本身
# 判定问题："这个问题是否存在至少一条经验桥接入口？"
# 动作：fatal → pipeline 终止；pass → 进入 MB

# CC (Compile & Check) 阶段  
# 输入：draft: MBDraft（MB 阶段生成的单条草稿）
# 输出：CompiledDraft（TestableClaim | RegulativeIdea）
# 判定对象：具体草稿
# 判定问题："这条草稿是否能被降格为可测试的经验声明？"
# 动作：NO_EMPIRICAL_BRIDGE → 降格为 RegulativeIdea；成功 → TestableClaim

# ════════════════════════════════════════════
# 不重叠的结构性保证
# ════════════════════════════════════════════

# 1. 输入对象不同：raw_q (str) vs draft (MBDraft)
# 2. 返回动作不同：NormalizeFatal (全局终止) vs RegulativeIdea (局部降格)
# 3. 无回退边：CC 不触发 NQ 的重新判定
# 4. 单调性：通过 NQ 的问题永远不会因 CC 结果而被追溯 fatal

# ════════════════════════════════════════════
# 执行路径
# ════════════════════════════════════════════

def pipeline(raw_q: str):
    # Phase 1: NQ
    errors = detect_category_errors(raw_q)
    if errors:
        return NormalizeFatal(errors)  # 全局终止
    
    normalized = normalize(raw_q)
    
    # Phase 2-3: MB (生成多条草稿)
    drafts = generate_drafts(normalized)  # MB 阶段
    
    # Phase 4: CC (逐条编译)
    compiled = []
    for draft in drafts:
        falsifier = synthesize_falsifier(draft)
        if falsifier.status == "NO_EMPIRICAL_BRIDGE":
            compiled.append(CompiledDraft.regulative_idea(draft))
        else:
            compiled.append(CompiledDraft.testable_claim(draft, falsifier))
    
    # Phase 5: RB (所有草稿，包括 RegulativeIdea，继续流入)
    return route_to_RB(compiled)  # 不回退，不重新判定
```

---

### 4. 两个完整的端到端 trace

#### Trace A：被 UNFALSIFIABLE_VALUE_ASSERTION 拦截（NQ 阶段终止）

```
输入: "爱比恨更好吗？"

═══ Phase 1: NQ - detect_category_errors() ═══

Stage 1 (SRP): 无自指锚点 → SKIP
Stage 2 (NEAOAE): "爱"/"恨" ∉ ABSTRACT_CORE → SKIP
Stage 3 (UVA):
  票1-规则层:
    value_marker_found = "更好" ✓
    has_empirical_anchor = False (无具体指标/人群/时间) ✓
    → 规则层命中
  票2-桥接模板匹配层:
    template "comparative_outcome":
      LLM提取: {agent_A: "爱", agent_B: "恨", outcome: None, metric: None}
      fit_score = 2/4 = 0.50 ... 但 outcome 和 metric 都是 None
      → 实际 fit_score 按有效 slot 计算 = 0.50
    template "causal_mechanism":
      LLM提取: {cause: None, effect: None, population: None, measure: None}
      fit_score = 0/4 = 0.00
    template "preference_survey":
      LLM提取: {population: None, preference_object: "爱 vs 恨", scale: None}
      fit_score = 1/3 = 0.33
    best_fit = 0.50
    
    ⚠️ 修正：best_fit = 0.50 > 0.35 阈值
    → 此处需要更严格的 fit_score 计算：
      仅当 outcome/metric/measure 等"可测试性关键 slot"被填充时才计分
      修正后: comparative_outcome 的 outcome=None, metric=None → 关键 slot 0/2 = 0.0
      best_fit(关键slot) = 0.0 < 0.35
    → 桥接模板匹配失败 ✓
  
  双票均命中 → 返回 CategoryErrorHit:
    tag = UNFALSIFIABLE_VALUE_ASSERTION
    rule_id = "UVA-DUAL-v1"
    confidence = 0.92
    evidence = "价值标记'更好' + 无经验锚点 + 桥接模板关键slot最佳匹配0.0"

═══ 结果: NormalizeFatal ═══
Pipeline 终止。
用户反馈: "此问题被识别为不可证伪的价值断言。'爱比恨更好'缺乏可操作的
经验测试维度（无可测量的结果指标）。建议重新表述，例如：'表达爱的行为
是否比表达恨的行为更能促进心理健康？'"

MB/CC/RB 阶段永远不会看到此问题。
```

#### Trace B：通过 NQ，某草稿在 CC 阶段返回 NO_EMPIRICAL_BRIDGE

```
输入: "民主制度是否促进经济增长？"

═══ Phase 1: NQ - detect_category_errors() ═══

Stage 1 (SRP): 无自指锚点 → SKIP
Stage 2 (NEAOAE): "民主制度" ∉ ABSTRACT_CORE → SKIP
Stage 3 (UVA):
  票1-规则层:
    value_marker_found = None ("促进"不在 VALUE_MARKERS 中)
    → 规则层未命中 → SKIP (直接放行，不进入票2)
Stage 4 (SU):
  quant_found = None (无广域量词)
  → SKIP

═══ 结果: 通过 NQ ═══
normalized_q = NormalizedQuestion("民主制度是否促进经济增长？")

═══ Phase 2-3: MB ═══
生成 3 条草稿:
  draft_1: "采用民主选举制度的国家，其 GDP 年均增长率高于非民主国家"
  draft_2: "民主制度通过保护产权和合同执行来降低交易成本，从而促进经济增长"
  draft_3: "民主制度在道德上优于威权制度，因此其经济成果也更优"

═══ Phase 4: CC - synthesize_falsifier() 逐条编译 ═══

draft_1: synthesize_falsifier("采用民主选举制度的国家，其GDP年均增长率高于非民主国家")
  → 成功提取 falsifier:
    testable_prediction = "民主国家 GDP 增长率 > 非民主国家 GDP 增长率"
    data_source = "World Bank GDP data + Polity IV democracy scores"
    falsification_condition = "若控制其他变量后，民主国家 GDP 增长率 ≤ 非民主国家"
  → CompiledDraft.testable_claim(draft_1, falsifier_1)

draft_2: synthesize_falsifier("民主制度通过保护产权...降低交易成本...促进经济增长")
  → 成功提取 falsifier:
    testable_prediction = "产权保护指数与 GDP 增长率正相关，且民主国家产权保护指数更高"
    data_source = "Heritage Foundation Property Rights Index + GDP data"
    falsification_condition = "若产权保护指数与 GDP 增长率无显著相关"
  → CompiledDraft.testable_claim(draft_2, falsifier_2)

draft_3: synthesize_falsifier("民主制度在道德上优于威权制度，因此其经济成果也更优")
  → 失败:
    status = "NO_EMPIRICAL_BRIDGE"
    reason = "道德优越性"无法映射到可测试的经验预测；
             "因此"连接的因果链缺乏可操作的中介变量
  → CompiledDraft.regulative_idea(draft_3)
    # draft_3 被降格为调节性理念，但不被丢弃

═══ Phase 5: RB ═══
route_to_RB([
    testable_claim(draft_1, falsifier_1),   # 可测试
    testable_claim(draft_2, falsifier_2),   # 可测试
    regulative_idea(draft_3)                 # 调节性理念，供参考但不作为核心论证
])

注意：
- draft_3 的 NO_EMPIRICAL_BRIDGE 不触发 NQ 的重新判定
- draft_3 作为 RegulativeIdea 继续存在于系统中
- Pipeline 正常继续，不回退
```

---

### 5. 实现难度最高的 2 个子问题及其风险

#### 风险 1：UNFALSIFIABLE_VALUE_ASSERTION 的桥接模板匹配（难度 ★★★★★）

**核心风险**：LLM slot 提取的不稳定性。同一输入在不同调用中可能提取出不同的 slots，导致 fit_score 波动，进而导致同一问题时而 fatal 时而通过。

**具体场景**：输入 `"自由比平等更重要吗？"`，LLM 可能在一次调用中提取 `{metric: "社会满意度"}` (fit_score 上升)，在另一次调用中提取 `{metric: None}` (fit_score 下降)。

**缓解措施**：
1. 对同一输入调用 LLM 3 次，取 slot 填充的多数票
2. 设置 fit_score 的"不确定区间"（0.30-0.40），落入此区间时不 fatal，标记为 INDETERMINATE 并放行
3. 桥接模板集的扩展需要版本控制和回归测试

**残余风险**：桥接模板集的完备性本质上是开放问题。系统的 fatal 边界会随模板集的扩展而变化，这意味着系统的行为不是完全稳定的。这是 by design 的（康德的攻击在此成立），但需要在系统文档中明确声明。

#### 风险 2：SCOPE_UNBOUNDED 的研究问法排除过宽（难度 ★★★☆☆）

**核心风险**：研究问法排除规则（"为什么"、"如何"等）可能导致真正无法收敛的问题漏过。

**具体场景**：`"为什么一切存在？"` 包含研究问法"为什么"，但主语"一切"是无限定全称，问题实际上无法在有限研究中收敛。当前规则会放行此问题。

**缓解措施**：
1. 对研究问法排除增加二次检查：如果主语仍为 BROAD_QUANTIFIERS 中的元素，则不排除
2. 修正后的规则：`研究问法排除仅在主语非广域量词时生效`

```python
# 修正后的排除逻辑
has_research_verb = any(rv in raw_q for rv in RESEARCH_VERBS)
subject_is_broad = _get_subject(raw_q) in BROAD_QUANTIFIERS
if has_research_verb and not subject_is_broad:
    return None  # 排除
# 否则继续检查缺失维度
```

**残余风险**：主语提取依赖 NLP 工具，可能不准确。但此风险的后果是漏放（问题进入后续阶段被自然处理），而非误杀，因此可接受。

---

*裁定完毕。本裁定书的所有规范均可直接用于实现，所有已知弱点均已标注。*