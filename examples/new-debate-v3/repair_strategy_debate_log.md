# v3 认知引擎架构：repair() 策略与 is_homologous() 同源检测 辩论日志

> 2026-03-09T18:32:25.004263

---


### [1] Linus Torvalds

*2026-03-09T18:23:12.526948*

我选 **F：`is_homologous()` 的判定算法**。这是更关键的那个点。原因很简单：`repair()` 再聪明，只要同源判定边界是糊的，系统就会在两种坏死方式之间来回跳——**要么把新东西错杀掉，要么把垃圾重复放进 Layer 2 烧预算**。这不是哲学问题，这是个去重器设计问题。你不给出算法，就等于没设计。

---

# 1. 我的立场：`is_homologous()` 必须是“结构优先、语义辅助、来源降权”的双阶段判定器

不是纯 embedding，不是纯 `tension_source`，也不是“看起来差不多”。

**具体设计选择：**

- **阶段 1：规范化结构签名（canonical structural signature）**
  - 从 `HypothesisDraft` 中提取：
    - 归一化 scope
    - claim shape（方向、条件、比较对象、结果变量）
    - verifier targets
  - 若结构签名高度重合，则直接判定 homologous
- **阶段 2：语义近似判定**
  - 仅在结构不完全相等但接近时，计算：
    - claim_sketch 语义相似度
    - verifier_hint 覆盖重叠
    - scope overlap
  - 达到组合阈值才判 homologous
- **明确禁止**：把 `tension_source.kind` 作为主判据。它只能做 tie-breaker 或解释字段，不能决定同源。

因为“来自同一张力”不等于“是同一个假设”。这点要是搞不清楚，系统就废了。

---

# 2. 为什么这是最强方案

## 2.1 核心原则

“本质相同”在工程上不该定义为“文案相似”，也不该定义为“来自同一冲突源”，而应定义为：

> **如果两个草稿经 CC 编译后，极大概率会投射到相同或近乎相同的可验证命题骨架，并消耗相同的验证路径，那么它们就是同源。**

注意我说的是“极大概率会投射到相同骨架”，因为你要求过滤发生在 CC 之前，不能偷懒说“编译后完全一样就是一样”。那就只能做一个 **pre-CC structural proxy**。代理可以不完美，但必须有明确字段、有明确阈值、有误差测试。

---

## 2.2 具体失败场景：为什么 `tension_source` 不能做主判据

### 场景
问题：远程办公是否提高软件团队生产力

已有草稿 A：
```text
在高同步依赖团队中，远程办公降低迭代吞吐量
```

repair 产出草稿 B：
```text
在高同步依赖团队中，远程办公提高缺陷逃逸率
```

二者可能都有：
```typescript
tension_source.kind = "EVALUATION_AXIS_SPLIT"
scope_ref = ["software_team", "remote_work"]
```

如果你用对手那种 **F1：张力来源同一性 + scope 高重叠**，那 B 很可能被判 homologous，直接过滤。

这是错的，而且是致命错误。

### 为什么错
A 关注的是 **throughput**，B 关注的是 **quality leakage**。  
它们不是同一个 claim，只是共享了一个上层张力源：同步协作成本。  
验证路径不同，证据需求不同，可能排名影响也不同。

### 在我的方案下
- 结构签名会抽出不同的 `outcome_anchor`
  - A: `iteration_throughput`
  - B: `defect_escape_rate`
- verifier_hint 也会不同
- 所以不会被判 homologous

### 在对手方案下，错在哪一步
错在**把张力来源误当作命题身份**。  
这就像说“都属于内存管理问题，所以这两个 bug 是同一个 bug”。胡扯。

---

## 2.3 具体失败场景：为什么纯语义相似度也不行

已有草稿 A：
```text
任务耦合度高的团队中，远程办公会降低研发产出
```

新草稿 B：
```text
跨职能依赖密集的团队在分布式协作下吞吐下降
```

embedding 很可能给你高相似度。  
但如果 A 的 verifier_hint 是：
- sprint velocity
- lead time

而 B 的 verifier_hint 是：
- cross-functional blocking time
- handoff latency

这两个不是简单重复；B 可能是在引入新的可观测路径，修复的是 `MISSING_OBSERVABLE`，而不是重复老命题。

如果你只看 semantic similarity，就会误杀真正的新桥接假设。

---

# 3. 判定算法

下面给完整算法。Python。

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Literal, Set
import re
from collections import Counter


GapKind = Literal["MISSING_DISCRIMINATOR", "MISSING_OBSERVABLE", "PREMISE_UNDERSPECIFIED"]
TensionKind = Literal["EXTERNAL_POSITION", "STAKEHOLDER_CONFLICT", "EVALUATION_AXIS_SPLIT"]


@dataclass
class Provenance:
    gap_id: Optional[str] = None
    schema_challenge_id: Optional[str] = None


@dataclass
class TensionSource:
    kind: TensionKind
    evidence_ref: Optional[List[str]] = None
    note: str = ""


@dataclass
class HypothesisDraft:
    draft_id: str
    problem_id: str
    scope_ref: List[str]
    tension_source: TensionSource
    claim_sketch: str
    verifier_hint: List[str]
    ttl: int
    failure_count: int
    provenance: Provenance


@dataclass
class CanonicalClaimShape:
    scope_tokens: Tuple[str, ...]
    condition_anchors: Tuple[str, ...]
    outcome_anchors: Tuple[str, ...]
    comparator_anchors: Tuple[str, ...]
    polarity: Literal["POS", "NEG", "MIXED", "UNKNOWN"]
    verifier_tokens: Tuple[str, ...]


@dataclass
class HomologyDecision:
    is_homologous: bool
    matched_existing_draft_id: Optional[str]
    score: float
    reason_codes: List[str]
    detail: Dict[str, float]


STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "with", "by",
    "是否", "会", "在", "中", "下", "对", "与", "及", "和", "的"
}

POLARITY_POS = {"increase", "improve", "raise", "higher", "提高", "增加", "改善", "上升"}
POLARITY_NEG = {"decrease", "reduce", "lower", "worse", "下降", "降低", "恶化", "增加缺陷"}


def normalize_text(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    tokens = [t.strip() for t in text.split() if t.strip() and t.strip() not in STOPWORDS]
    return tokens


def dedup_sorted(tokens: List[str]) -> Tuple[str, ...]:
    return tuple(sorted(set(tokens)))


def infer_polarity(text: str) -> str:
    toks = set(normalize_text(text))
    pos = len(toks & POLARITY_POS)
    neg = len(toks & POLARITY_NEG)
    if pos > 0 and neg == 0:
        return "POS"
    if neg > 0 and pos == 0:
        return "NEG"
    if pos > 0 and neg > 0:
        return "MIXED"
    return "UNKNOWN"


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def token_overlap_tuple(a: Tuple[str, ...], b: Tuple[str, ...]) -> float:
    return jaccard(set(a), set(b))


def extract_claim_shape(d: HypothesisDraft) -> CanonicalClaimShape:
    scope_tokens = dedup_sorted([tok for s in d.scope_ref for tok in normalize_text(s)])

    sketch_tokens = normalize_text(d.claim_sketch)
    verifier_tokens = dedup_sorted([tok for s in d.verifier_hint for tok in normalize_text(s)])

    # crude but deterministic anchors:
    # condition anchors: tokens near “if/when/in/under/在...中/对于...”
    # for implementation v1, approximate by intersection with scope + known condition-like words removed
    condition_anchors = dedup_sorted([
        t for t in sketch_tokens
        if t in set(scope_tokens) or t in {"high", "low", "同步", "依赖", "成熟度", "耦合度", "remote", "distributed"}
    ])

    # outcome anchors approximate: sketch tokens not in scope/condition
    outcome_anchors = dedup_sorted([
        t for t in sketch_tokens
        if t not in set(condition_anchors)
    ])

    comparator_anchors = dedup_sorted([
        t for t in sketch_tokens
        if t in {"than", "versus", "compared", "more", "less", "高于", "低于", "优于", "劣于"}
    ])

    polarity = infer_polarity(d.claim_sketch)

    return CanonicalClaimShape(
        scope_tokens=scope_tokens,
        condition_anchors=condition_anchors,
        outcome_anchors=outcome_anchors,
        comparator_anchors=comparator_anchors,
        polarity=polarity,
        verifier_tokens=verifier_tokens,
    )


def semantic_similarity_proxy(a_text: str, b_text: str) -> float:
    # deterministic fallback proxy; in production replace with embedding cosine
    a = set(normalize_text(a_text))
    b = set(normalize_text(b_text))
    return jaccard(a, b)


def homology_score(a: HypothesisDraft, b: HypothesisDraft) -> Tuple[float, Dict[str, float], List[str]]:
    sa = extract_claim_shape(a)
    sb = extract_claim_shape(b)

    scope_score = token_overlap_tuple(sa.scope_tokens, sb.scope_tokens)
    condition_score = token_overlap_tuple(sa.condition_anchors, sb.condition_anchors)
    outcome_score = token_overlap_tuple(sa.outcome_anchors, sb.outcome_anchors)
    verifier_score = token_overlap_tuple(sa.verifier_tokens, sb.verifier_tokens)
    semantic_score = semantic_similarity_proxy(a.claim_sketch, b.claim_sketch)

    polarity_same = 1.0 if sa.polarity == sb.polarity and sa.polarity != "UNKNOWN" else 0.0
    tension_same = 1.0 if a.tension_source.kind == b.tension_source.kind else 0.0

    # tension is weak evidence only
    score = (
        0.25 * scope_score +
        0.20 * condition_score +
        0.25 * outcome_score +
        0.20 * verifier_score +
        0.08 * semantic_score +
        0.02 * tension_same
    )

    reasons = []
    if scope_score >= 0.8:
        reasons.append("SCOPE_NEAR_EQUAL")
    if outcome_score >= 0.8:
        reasons.append("OUTCOME_NEAR_EQUAL")
    if verifier_score >= 0.8:
        reasons.append("VERIFIER_NEAR_EQUAL")
    if semantic_score >= 0.85:
        reasons.append("SEMANTIC_NEAR_EQUAL")
    if polarity_same == 1.0:
        reasons.append("POLARITY_MATCH")

    detail = {
        "scope_score": scope_score,
        "condition_score": condition_score,
        "outcome_score": outcome_score,
        "verifier_score": verifier_score,
        "semantic_score": semantic_score,
        "tension_same": tension_same,
        "score": score,
    }
    return score, detail, reasons


def is_homologous(
    candidate: HypothesisDraft,
    existing: List[HypothesisDraft],
    score_threshold: float = 0.82,
    hard_structural_threshold: float = 0.90,
) -> HomologyDecision:
    best = None

    for ex in existing:
        score, detail, reasons = homology_score(candidate, ex)

        # hard rule: same scope + same outcome + same verifier path => homologous
        if (
            detail["scope_score"] >= 0.9 and
            detail["outcome_score"] >= 0.9 and
            detail["verifier_score"] >= 0.85
        ):
            return HomologyDecision(
                is_homologous=True,
                matched_existing_draft_id=ex.draft_id,
                score=score,
                reason_codes=reasons + ["HARD_STRUCTURAL_MATCH"],
                detail=detail,
            )

        if best is None or score > best.score:
            best = HomologyDecision(
                is_homologous=score >= score_threshold,
                matched_existing_draft_id=ex.draft_id,
                score=score,
                reason_codes=reasons,
                detail=detail,
            )

    if best is None:
        return HomologyDecision(
            is_homologous=False,
            matched_existing_draft_id=None,
            score=0.0,
            reason_codes=["NO_EXISTING_DRAFT"],
            detail={},
        )

    return best
```

---

# 4. 这个算法的边界定义

我给明确边界，不玩虚的。

判定 `is_homologous = true` 当且仅当满足以下之一：

### 条件 A：硬结构重复
- `scope_score >= 0.9`
- `outcome_score >= 0.9`
- `verifier_score >= 0.85`

这说明：
- 看的是同一类对象
- 试图回答同一结果变量
- 走的是同一验证路径

那就是重复。别浪费时间。

### 条件 B：组合近似重复
- 总分 `>= 0.82`
- 且 `outcome_score >= 0.75`
- 且 `scope_score >= 0.75`

这里专门卡 outcome 和 scope，因为这两个是命题身份的骨架。  
`tension_source` 只占 0.02 权重，几乎无关紧要。它只能帮你解释，不该帮你决定。

---

# 5. 为什么这比 repair 策略更关键

因为 `repair()` 本质上是候选生成器；生成器可以有噪声，过滤器不能是玄学。

你可以允许 `repair()` 偶尔蠢一点，多产几个候选；  
但你不能允许 `is_homologous()` 没边界。  
没边界的过滤器会直接破坏两个核心性质：

1. **Epoch 非空转性**
2. **SchemaChallenge 合法触发性**

尤其你已经裁定：  
> 当且仅当 `is_homologous=true` 时，SchemaChallenge 不触发广度引擎

那这个判定边界如果错了，代价不是“有点不优”，而是**新维度被制度性封杀**。

---

# 6. 已知弱点与缓解措施

## 弱点 1：pre-CC 结构抽取会不稳定
是的，`claim_sketch` 本来就是草稿，不是正式 AST。  
你不可能指望 v1 的 anchor extraction 永远正确。

### 缓解
- 给 CC 增加一个 **dry-run normalize mode**，不生成正式 `TestableClaim`，只生成轻量 `ClaimFramePreview`
- `is_homologous()` 优先使用 preview，而不是直接从自然语言硬抠

也就是说，架构上仍然是“过滤先于正式编译”，但允许一个廉价的预解析器。  
这不违反既定骨架，只是把你的过滤从玩具提升到可用。

---

## 弱点 2：同义 outcome 的词表覆盖不全
“吞吐量”“交付速度”“研发产出”可能其实在讲同一东西。简单 token overlap 会漏报。

### 缓解
- 引入 outcome ontology / alias lexicon
- 每个问题域维护少量可扩展别名映射
- 线上收集 false negative case，迭代词表

别幻想一个通用 embedding 能完美替代这个。领域词义是会漂的。

---

## 弱点 3：组合阈值需要校准
0.82 不是摩西从山上拿下来的。它只是一个初值。

### 缓解
做离线回放实验：
- 取历史 Epoch 序列
- 标注“应过滤/不应过滤”对
- 比较不同阈值下：
  - false positive rate
  - false negative rate
  - downstream ranking-changing yield
  - wasted L2 budget

最终优化目标不是分类准确率本身，而是：

> **每消耗 1 单位 Layer 2 预算，带来的 ranking-changing repair 概率最大化**

这才是正确指标。

---

# 7. 如果我错了，什么实验能发现？

很好，这才是重点。

## 实验 1：同源过滤 A/B 回放
比较三种方案：
- A: tension_source + scope
- B: semantic embedding only
- C: 我的结构+语义双阶段

数据：
- 历史 repair 产出和后续 CC / D2 / L2 结果

指标：
- 过滤后通过率
- 被放行草稿的 CC 成功率
- 进入 L2 后产生 `ranking_delta.changed=true` 的比率
- 每轮 Epoch 的有效新增信息量
- 连续两轮全被过滤的空转率

**如果 C 没有显著降低“无效放行”同时不提高“新颖草稿误杀率”，那我的方案就该被扔掉。**

## 实验 2：反事实误杀审计
对所有被判 homologous 的草稿，做 shadow-run：
- 不过滤，照常送入 CC/L2
- 看是否出现新的 outcome axis、新 verifier path、新 top-k 变化

**如果被我过滤掉的东西里，超过某阈值（比如 10%）能稳定引起 ranking change，那我的边界画窄了，我错。**

## 实验 3：结构抽取稳定性测试
同一草稿做多种表述改写，检查 `extract_claim_shape()` 是否稳定。

**如果轻微改写就导致 homology 判定大幅波动，这算法没资格上线。**

---

# 8. 对一个对手立场的预攻击

我先打最常见的烂主张：

> **对手可能说：**
> “F1（张力来源同一性）更符合‘本质相同’，因为两个草稿若都回应同一 tension_source，说明它们是在同一问题骨架内的变体，应视为同源，避免广度爆炸。”

这说法的问题是：**把上层解释变量和下层验证命题混为一谈。**

具体缺陷：

1. **同一 tension_source 可以派生多个非同源命题**
   - 同样是“协作摩擦增加”
   - 可以落到 throughput、quality、retention、coordination cost
   - 这些是不同 outcome axis，不该合并

2. **该方案会系统性压制多轴展开**
   - 尤其在 `EVALUATION_AXIS_SPLIT` 场景下
   - 你用 evaluation axis 的同一来源来判同源，等于把 axis split 本身判死了
   - 这是自相矛盾

3. **无法解释 verifier path 差异**
   - 同一个 tension_source，不同证据路径可能修复不同 gap
   - 你的规则完全看不见这个差别

所以，如果有人主张：

> “`tension_source.kind` 相同且 `scope_ref` 高度重叠即可认定同源”

那我直接说：这个规则会**把张力类别误当成 claim identity**，必然导致漏报新维度。不是可能，是必然。

---

# 9. 最后结论

我的结论很明确：

- `is_homologous()` 不应由 `tension_source` 主导
- 不应只靠语义相似度
- 应采用 **结构优先、语义辅助、来源降权** 的双阶段判定
- “本质相同”的工程定义是：
  - **相同 scope**
  - **相同 outcome 骨架**
  - **近似相同 verifier path**
- 阈值必须通过离线回放和 shadow-run 校准
- 若实验表明它误杀了能引起 ranking change 的草稿，我的方案就该被推翻

这就是个去重器。别把它包装成哲学。真正要避免的是 **Epoch 空转** 和 **新维度错杀**，而不是写一堆听起来高级的“本质同一性”废话。

---


### [2] Ssyram

*2026-03-09T18:23:12.526985*

我是 Ssyram。在系统架构的语境下，任何脱离了状态转移约束的「创造性」都是系统崩溃的温床。

本轮我选择**问题 E（repair() 的生成策略）**作为核心阵地，并直接通过严格的结构化策略来回答底线问题：**如果 repair 连续两轮产出的草稿 100% 被 is_homologous 过滤，系统究竟该做什么。**

我的核心立场是：**`repair()` 绝不是 LLM 的「自由命题作文」（彻底拒绝 E3），而是 CEGAR（反例引导的抽象精化）模型中的精确精化算子（Refinement Operator）。** `gap_kind` 和 `schema_challenge` 就是 Layer 2 抛出的反例（Counterexamples），`repair()` 必须基于结构化策略（E2）执行机械的代数变换。`suggested_dimension` 必须是**强约束**，绝非弱提示。

### 一、 核心设计主张与函数签名

在我的设计中，`repair()` 是一个纯函数，它将 `GapSpec` 和 `SchemaChallenge` 映射为严格受限的 `HypothesisDraft`。

```typescript
// Ssyram's repair() signature & structural mapping
function repair(
  frame: QuestionFrame,
  l2_return: L2Return,
  history_drafts: HypothesisDraft[]
): HypothesisDraft[] {
  const new_drafts: HypothesisDraft[] = [];

  // 1. 结构化处理 Gaps (CEGAR Refinement)
  for (const gap of l2_return.new_gaps) {
    const drafts = apply_gap_refinement(gap, frame);
    new_drafts.push(...drafts);
  }

  // 2. 结构化处理 Schema Challenges (Dimensional Expansion)
  for (const challenge of l2_return.schema_challenges) {
    if (challenge.is_homologous) continue; // Topic1已裁定：同源挑战不触发广度
    
    // 核心主张：suggested_dimension 是强约束。
    // 强制生成的新 draft 的 scope_ref 必须与该 dimension 绑定。
    const drafts = apply_schema_expansion(challenge, frame);
    new_drafts.push(...drafts);
  }

  return new_drafts;
}

function apply_gap_refinement(gap: GapSpec, frame: QuestionFrame): HypothesisDraft[] {
  switch (gap.gap_kind) {
    case "MISSING_DISCRIMINATOR":
      // 策略：条件窄化 (Conditional Narrowing)
      // 生成：在 [discriminator] 极值区间内，原假设成立。
      return [{
        draft_id: generate_id(),
        problem_id: frame.id,
        scope_ref: [`${gap.discriminator}_HIGH`, `${gap.discriminator}_LOW`], // 强制划分
        tension_source: { kind: "EVALUATION_AXIS_SPLIT", note: `Split by missing discriminator: ${gap.discriminator}` },
        claim_sketch: `When ${gap.discriminator} is constrained, the original premise holds.`,
        verifier_hint: gap.required_observable, // 直接继承 gap 的要求
        ttl: 3, failure_count: 0,
        provenance: { gap_id: gap.gap_id }
      }];
    case "MISSING_OBSERVABLE":
      // 策略：代理替换 (Proxy Substitution)
      return [/* 强制要求 claim_sketch 包含对替代可观测量的声明 */];
    case "PREMISE_UNDERSPECIFIED":
      // 策略：前提强化 (Premise Strengthening)
      return [/* 强制收缩 scope_ref */];
    default:
      // 拒绝 E3 兜底！如果出现未知 gap_kind，抛出异常，而不是让 LLM 瞎编。
      throw new Error(`Type Error: Unhandled gap_kind ${gap.gap_kind}`);
  }
}
```

#### 应对底线问题：连续两轮 100% 被 is_homologous 过滤怎么办？
在我的 E2 结构化策略下，`repair()` 产出的草稿是高度可预测的。如果连续两轮产出的草稿 100% 被 `is_homologous` 判定为同源（即：新生成的条件窄化/代理替换与系统中已有的草稿在结构上重合），这在状态机中意味着：**当前 Schema 的精化空间已被彻底穷尽（Refinement Exhausted）。**

此时，系统**绝对不能**降级去尝试更模糊的 LLM 生成（那只会引入噪音），而必须**立即终止**。
PA 节点应捕获此状态，输出 `TerminationReport`，其结论类型为 `REGULATORY_RESIDUE`（调节性残余）——系统明确宣告：“在现有的可观测维度下，该问题无法被进一步无争议地拆解，残余张力不可消除”。

### 二、 最强论据与失败场景对比

为什么必须是强约束的 E2（结构化推导），而不能包含 E3（LLM 自由创造）？

**场景**：辩题「远程办公是否提高软件团队生产力」。
Layer 2 验证某命题失败，返回 `GapSpec(gap_kind=MISSING_DISCRIMINATOR, discriminator="任务耦合度")`。

*   **在我的 E2 方案下**：`repair()` 机械地将原命题切割为两个子空间（`scope_ref` 包含“高任务耦合度”与“低任务耦合度”），生成两条草稿。`is_homologous` 检查这两个 scope_ref 是否已存在。如果不存在，进入 CC 编译。这一切是精确的代数切割。
*   **在对手（主张 E3 或混合策略）的方案下**：对手把 GapSpec 喂给 LLM：“请根据缺失的‘任务耦合度’判别器，自由生成新假设”。LLM 很有可能生成：“远程办公对初级程序员的生产力有负面影响”。
    **致命缺陷**：这发生了**状态逃逸（State Escape）**！LLM 引入了“资历（初级程序员）”这个全新的维度，完全丢弃了“任务耦合度”这个严格的 Gap 约束。结果是：`provenance.gap_id` 变成了一个彻头彻尾的谎言。系统以为在修复 Gap A，实际上在广度盲搜 Dimension B。这会导致 Layer 2 陷入无尽的预算浪费，且永远无法收敛。

### 三、 对手可能立场的预攻击

我预判会有对手（比如主张 F2 语义相似度或 E3 自由创造的人）提出：“E2 的结构化生成太死板了，会导致草稿同质化，所以我们需要引入 LLM 自由度和 F2 的向量余弦相似度来做 `is_homologous` 判定。”

**我的攻击**：
主张使用嵌入向量余弦相似度（F2）作为 `is_homologous` 判定标准，是一个不可原谅的**类型错误（Type Error）**。
在我们的系统里，`is_homologous` 必须基于 **F4（verifier_hint 覆盖度 + tension_source 同一性）**。
为什么？因为两个草稿在语义上可能极其相似（余弦相似度 0.95），比如：
1. “高耦合度团队远程办公降低了 20% 吞吐量”
2. “高耦合度团队远程办公提升了 10% 吞吐量”
它们在向量空间上几乎重叠，但它们的验证路径（`verifier_hint`）和证伪条件（`falsifier`）指向截然相反的方向！如果用 F2 相似度阈值过滤，草稿 2 会被误杀（漏报），导致系统错失对立视角的验证。
同源（Homology）在状态机中是一个**结构等价性**问题，而不是**几何距离**问题。只有当两个草稿共享相同的张力来源，且试图占用相同的验证预算（`verifier_hint` 重叠度 > 80%）时，它们才是同源的。

### 四、 已知弱点与缓解措施

**已知弱点**：`gap_kind` 的三元分类（MISSING_DISCRIMINATOR / MISSING_OBSERVABLE / PREMISE_UNDERSPECIFIED）可能无法穷尽现实中所有的认知缺口。如果 Layer 2 遇到这三种之外的失败，E2 策略会报错。

**缓解措施**：
引入显式的 `UNCLASSIFIED_ANOMALY` 机制。但这绝不是回退到 E3 的自由生成。
如果 Layer 2 发现无法归入三元的 Gap，它**不应该**产出 `GapSpec`，而应该直接产出 `SchemaChallengeNotice`（触发条件为 `PRECISION_DEADLOCK`），强制要求 Layer 1 在 `repair()` 阶段进行维度的正交扩展（Dimensional Expansion），而不是在原维度上做精化。这保证了控制流的绝对纯洁。

**可推翻条件**：
如果在实际运行中，Layer 2 抛出的 `GapSpec` 超过 30% 无法被这三种结构化策略（条件窄化、代理替换、前提强化）有效转换为可通过 CC 编译的 `TestableClaim`，则证明 CEGAR 的抽象精化操作集不足，我的 E2 纯结构化主张即被推翻。但在那之前，拒绝一切 LLM 的黑盒魔法。

---


### [3] 康德（Immanuel Kant）

*2026-03-09T18:23:12.527001*

我选择 **F：`is_homologous()` 判定**，因为此处一旦先验边界放松，系统不会立刻“构成性失败”，却会发生更危险的 **调节性失控**：广度引擎被噪声合法触发，Epoch 持续消耗预算而不产生真实的新维度。这比 repair 偶尔贫乏更根本。

我的立场是：

> **`is_homologous()` 必须采用“先验框架优先、编译前可判”的分层判定：**
> 1. 先判是否共享同一 schema；
> 2. 再判是否在同一 tension dimension 上仅作表面改写；
> 3. 若同 schema 且不可构成真正的正题/反题对立，则判为同源；
> 4. 对跨 schema 但只是“维度重命名”的情况，判为 `AMBIGUOUS` 而非直接 `false`，交由受限编译探针或人工审计通道，不得直接放行到广度。

这不是抽象原则，而是一个可实现的三值判定器：`HOMOLOGOUS | NOVEL | AMBIGUOUS`。  
若你强迫二值输出，也应把 `AMBIGUOUS` 在系统策略上按 **阻断广度触发** 处理，直到补充证据。

---

## 1. 具体设计选择

### 设计主张

我主张 Layer 1 的 `is_homologous()` 不应依赖单纯语义相似度，也不应等待 CC 编译出 falsifier 才判断。应改为：

- **输入**：候选新草稿 `draft`，既有草稿/候选集 `existing`，以及 `QuestionFrame` 中可抽出的 schema registry
- **输出**：对每个既有候选的三值关系，最终汇总为单个判定
  - `HOMOLOGOUS`
  - `NOVEL`
  - `AMBIGUOUS`

### 判定核心

若两个草稿满足以下条件，则同源：

1. **同一认识框架（same schema family）**
2. **张力来源处于同一维度（same tension dimension）**
3. **它们之间无法形成真实对立的可检验分岔**  
   即：即使分别送入 CC，它们预期也只会要求同一类判别器/观测量，而不是引入新的裁决维度

换言之：

- “同源”不是“文本像不像”
- 也不是“最后 falsifier 一不一样”
- 而是：**它们是否从同一先验图型出发，仅在图像内容上改写，而未改变对象被理解的方式**

### 为什么必须三值而不是二值

因为最危险的不是显然同源或显然新颖，而是 **跨 schema 的表面差异**：

- 例如把“团队成熟度”改写成“协作自治水平”
- 这可能是新维度，也可能只是旧维度换名

若直接判 `false`（非同源），广度引擎会被噪声触发。  
若直接判 `true`，又可能压死真实新维度。  
所以必须有 `AMBIGUOUS` 作为认识论上的“未获合法化”。

---

## 2. 最强论据与失败场景

## 失败场景：远程办公与生产力

已有草稿 A：

```text
scope_ref = ["software_teams", "remote_work"]
tension_source.kind = "EVALUATION_AXIS_SPLIT"
tension_source.note = "productivity varies by task coupling"
claim_sketch = "Remote work reduces throughput in high-synchrony teams"
verifier_hint = ["handoff_delay", "coordination_latency", "task_coupling_index"]
```

repair 依据 schema challenge 生成新草稿 B：

```text
scope_ref = ["software_teams", "remote_work"]
tension_source.kind = "EVALUATION_AXIS_SPLIT"
tension_source.note = "outcomes vary by collaboration interdependence"
claim_sketch = "Remote work lowers delivery speed where collaboration interdependence is high"
verifier_hint = ["coordination_latency", "dependency_density", "cycle_time"]
```

### 在我的方案下如何运行

- schema family 识别：
  - A/B 都属于“条件化 productivity schema”
- tension dimension 识别：
  - 都是在“协作耦合度/同步依赖”维度上分裂
- 对立性检测：
  - A/B 不能形成真正 antinomy；B 不是反题，只是同一框架下的重述
- 判定：
  - `HOMOLOGOUS`
- 系统行为：
  - B 被过滤
  - repair 必须继续寻找真正的新维度，例如“团队成熟度”“管理制度”“创新质量与吞吐量的轴分离”

### 在对手方案下哪里出错

#### 若对手主张 F2：语义相似度阈值

可能因 “task coupling” 与 “collaboration interdependence” 文本差异较大，余弦相似度未过阈值，判 `false`。

**错误步骤：**
1. B 被视为新候选
2. CC 编译成功
3. D2 再次派发
4. Layer 2 重复索取同类观测量
5. 排名不变，但预算被耗在伪新颖上

这正是我所说的：  
**不是构成性失败，而是调节性失控。**

#### 若对手主张 F3：等编译后看 falsifier

则顺序已被颠倒。你必须先花 CC 和 D2 的预算，才能发现它同源。  
这在工程上不是“更精确”，而是 **把门卫功能推迟到入场之后**。  
对开放搜索系统而言，这是范畴错置。

---

## 3. 已知弱点及缓解措施

### 弱点 1：schema family 抽取本身可能不稳定

若 schema 标注器把“团队成熟度”错误吸附到“任务耦合度”家族，我的算法会误杀新维度。

**缓解措施：**
- 引入 `AMBIGUOUS`
- 对 schema family 置信度低于阈值者，不直接判 `HOMOLOGOUS`
- 要求 repair 草稿附带 `proposed_schema_tags`
- 每轮统计“被判同源但后续人工抽查证伪”的比例，超阈值则回调 schema classifier

**可推翻条件：**
若离线评测显示，在人工标注为“真实新维度”的样本中，我的规则误判同源率持续高于 15%，且主要原因来自 schema family 误归类，则此设计不可接受。

---

### 弱点 2：三值判定增加状态复杂度

`AMBIGUOUS` 会引入额外流程。

**缓解措施：**
- 不是开放额外主循环，而是受限探针：
  - 最多 1 次 micro-compile 或 1 条 shadow queue
- `AMBIGUOUS` 不直接进入正式广度
- 若连续两轮 repair 只产出 `AMBIGUOUS/HOMOLOGOUS`，记录为 **regulative residue**，而非假装还有构成性进展

**可推翻条件：**
若生产运行中 `AMBIGUOUS` 占 repair 产出的 >40%，且多数最终被证明无信息增益，则说明判定器过于保守，应简化或重训 schema 抽取层。

---

### 弱点 3：同一 schema 下也可能存在真实新方向

例如都属于“条件化 productivity schema”，但一个条件是“任务耦合度”，另一个是“合规强度”，后者可能真是新维度。

**缓解措施：**
- 不能仅靠 `tension_source.kind`
- 必须抽取 `dimension_key`
- 仅当 `dimension_key` 相同或互为规范化别名时，才进入同源判定
- 否则至多 `AMBIGUOUS`，不能直接 `HOMOLOGOUS`

**可推翻条件：**
若使用 dimension normalization 后，仍有大量“合规强度 vs 任务耦合度”这类明显不同维度被误判同源，则说明 dimension ontology 太粗，需扩容。

---

## 4. 完整函数签名与判定算法

我用 TypeScript 给出。

```typescript
type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT";

type GapKind =
  | "MISSING_DISCRIMINATOR"
  | "MISSING_OBSERVABLE"
  | "PREMISE_UNDERSPECIFIED";

type Provenance = {
  gap_id?: string;
  schema_challenge_id?: string;
};

type HypothesisDraft = {
  draft_id: string;
  problem_id: string;
  scope_ref: string[];
  tension_source: {
    kind: TensionKind;
    evidence_ref?: string[];
    note: string;
  };
  claim_sketch: string;
  verifier_hint: string[];
  ttl: number;
  failure_count: number;
  provenance: Provenance;
};

type SchemaTag = {
  family: string;          // e.g. "conditional_productivity"
  dimension_key: string;   // e.g. "task_coupling"
  aliases: string[];       // e.g. ["collaboration_interdependence", "sync_dependency"]
  confidence: number;      // [0,1]
};

type DraftAnalysis = {
  draft_id: string;
  schema_tags: SchemaTag[];
  normalized_scope: string[];
  normalized_verifiers: string[];
  tension_kind: TensionKind;
};

type HomologyVerdict = "HOMOLOGOUS" | "NOVEL" | "AMBIGUOUS";

type PairwiseHomology = {
  draft_id: string;
  against_draft_id: string;
  verdict: HomologyVerdict;
  reasons: string[];
  confidence: number;
};

type HomologyResult = {
  draft_id: string;
  final_verdict: HomologyVerdict;
  pairwise: PairwiseHomology[];
  blocked_by: string[]; // existing draft ids causing HOMOLOGOUS
};

type SchemaRegistry = {
  alias_to_dimension: Record<string, string>;
  family_rules: Record<string, { incompatible_dimensions: string[] }>;
};

function analyzeDraft(
  draft: HypothesisDraft,
  registry: SchemaRegistry
): DraftAnalysis {
  const normalizedScope = normalizeScope(draft.scope_ref);
  const normalizedVerifiers = normalizeVerifiers(draft.verifier_hint);

  const extracted = extractSchemaTags(
    draft.claim_sketch,
    draft.tension_source.note,
    normalizedVerifiers,
    registry
  );

  return {
    draft_id: draft.draft_id,
    schema_tags: extracted,
    normalized_scope: normalizedScope,
    normalized_verifiers: normalizedVerifiers,
    tension_kind: draft.tension_source.kind,
  };
}

function pairwiseHomology(
  a: DraftAnalysis,
  b: DraftAnalysis
): PairwiseHomology {
  const reasons: string[] = [];

  const scopeOverlap = jaccard(a.normalized_scope, b.normalized_scope);
  const sameTensionKind = a.tension_kind === b.tension_kind;

  const familyPairs = crossTags(a.schema_tags, b.schema_tags)
    .filter(([x, y]) => x.family === y.family);

  if (!sameTensionKind || scopeOverlap < 0.5 || familyPairs.length === 0) {
    return {
      draft_id: a.draft_id,
      against_draft_id: b.draft_id,
      verdict: "NOVEL",
      reasons: ["different_tension_or_scope_or_schema_family"],
      confidence: 0.75,
    };
  }

  let ambiguous = false;

  for (const [x, y] of familyPairs) {
    const lowConfidence = x.confidence < 0.7 || y.confidence < 0.7;
    const sameDimension =
      x.dimension_key === y.dimension_key ||
      x.aliases.includes(y.dimension_key) ||
      y.aliases.includes(x.dimension_key);

    const verifierOverlap = jaccard(a.normalized_verifiers, b.normalized_verifiers);

    if (lowConfidence) {
      ambiguous = true;
      reasons.push("low_schema_confidence");
      continue;
    }

    if (sameDimension && verifierOverlap >= 0.5) {
      reasons.push("same_schema_family");
      reasons.push("same_tension_dimension");
      reasons.push("same_verification_path");
      return {
        draft_id: a.draft_id,
        against_draft_id: b.draft_id,
        verdict: "HOMOLOGOUS",
        reasons,
        confidence: 0.88,
      };
    }

    if (sameDimension && verifierOverlap < 0.5) {
      ambiguous = true;
      reasons.push("same_dimension_but_verifier_diverges");
    }
  }

  return {
    draft_id: a.draft_id,
    against_draft_id: b.draft_id,
    verdict: ambiguous ? "AMBIGUOUS" : "NOVEL",
    reasons: ambiguous ? reasons : ["same_family_but_new_dimension"],
    confidence: ambiguous ? 0.55 : 0.72,
  };
}

function is_homologous(
  draft: HypothesisDraft,
  existing: HypothesisDraft[],
  registry: SchemaRegistry
): HomologyResult {
  const analyzedDraft = analyzeDraft(draft, registry);
  const pairwise = existing.map(e =>
    pairwiseHomology(analyzedDraft, analyzeDraft(e, registry))
  );

  const blockedBy = pairwise
    .filter(p => p.verdict === "HOMOLOGOUS")
    .map(p => p.against_draft_id);

  const hasAmbiguous = pairwise.some(p => p.verdict === "AMBIGUOUS");

  const finalVerdict: HomologyVerdict =
    blockedBy.length > 0 ? "HOMOLOGOUS"
    : hasAmbiguous ? "AMBIGUOUS"
    : "NOVEL";

  return {
    draft_id: draft.draft_id,
    final_verdict: finalVerdict,
    pairwise,
    blocked_by: blockedBy,
  };
}
```

### 配套系统策略

```typescript
type FilterDecision =
  | { action: "DROP_AS_HOMOLOGOUS"; reason: string[] }
  | { action: "QUEUE_FOR_MICRO_PROBE"; reason: string[] }
  | { action: "ALLOW_TO_CC"; reason: string[] };

function decideAfterHomology(result: HomologyResult): FilterDecision {
  if (result.final_verdict === "HOMOLOGOUS") {
    return { action: "DROP_AS_HOMOLOGOUS", reason: ["blocked_by_existing"] };
  }
  if (result.final_verdict === "AMBIGUOUS") {
    return { action: "QUEUE_FOR_MICRO_PROBE", reason: ["needs_schema_disambiguation"] };
  }
  return { action: "ALLOW_TO_CC", reason: ["novel_dimension"] };
}
```

---

## 5. 对手可能立场的预攻击

我先攻击一个最常见、也最危险的立场：

### 预攻击对象：F2 语义相似度派

你们的可能文本会是：

> “两个草稿如果 `claim_sketch` 嵌入相似度超过阈值，就判同源；否则视为新颖。这样实现简单、可扩展。”

我的攻击是：

1. **把经验上的语言相近，僭越为认知上的本质相同**
   - 文本相似不是 schema 相同
   - 文本不相似更不是新维度
2. **阈值无法承担合法性证明**
   - 0.82 为什么是同源，0.78 为什么不是？
   - 这只是工程调参，不是认识论上的正当化
3. **对跨 schema 的伪新颖毫无防线**
   - “协作耦合” vs “合作负载” 可能逃过阈值
   - 结果是系统把重命名当创新
4. **无法在编译前识别“不能形成真正张力对”的情况**
   - 我的判据问的是：能否构成 antinomy？
   - 你们的判据只问：句子像不像

**可推翻条件：**  
若语义相似度法在离线标注集上，能以可解释方式区分：
- 同 schema 同维度重述
- 同 schema 不同维度扩展
- 跨 schema 真新颖  
且其噪声触发率不高于我方案，那么我承认其工程优势足以动摇我的立场。  
但在此证明出现前，它只是便利，不是合法性。

---

### 顺带预攻击 F3 编译后判定派

你们可能会说：

> “最可靠的是先让 CC 编译，再比较 falsifier/scope；相同则同源。”

缺陷是明确的：

- 这违背架构中 `is_homologous()` 作为 **编译前门卫** 的位置
- 你把过滤的成本后移到最昂贵的阶段
- 对开放问题系统，这会系统性放大预算浪费

除非你主张重写 topic1 已裁定的调用顺序；若不主张，你的方案就与既定架构不相容。

---

## 结论

我的完整立场是：

- `is_homologous()` 的关键不在语义相似，而在 **先验亲和性测试**
- 判定标准应是：
  - 是否共享同一 schema family
  - 是否落在同一 tension dimension
  - 是否无法形成真正的可检验对立
- 工程实现上必须采用 **三值判定：HOMOLOGOUS / NOVEL / AMBIGUOUS**
- `AMBIGUOUS` 不能直接放行，否则就是把未获合法化的差异冒充为新维度

最后给出我的主张的可推翻条件：

> 若在人工标注的 repair 草稿数据集上，三值 schema-first 判定相较于语义相似度法，不能显著降低“噪声触发广度”的比例，且误杀真实新维度的比例更高，则我的方案应被废弃。

这就是我的第一轮立场。

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-09T18:23:39.050848*

1. **你把“连续两轮 100% 被 `is_homologous` 过滤”直接解释成“精化空间穷尽，立即终止”——这一步根本没被你证明。**  
你只证明了：**在你自己的 E2 生成器下，当前那套模板产出的东西都撞车了**。这只能推出“**你的生成器穷尽了**”，不能推出“**问题空间穷尽了**”。这两者差得非常远。  
尤其你自己又承认 `gap_kind` 三元分类可能不完备，还额外引入 `UNCLASSIFIED_ANOMALY → SchemaChallenge` 的逃生口。那就更矛盾了：如果分类本身可能漏掉结构，而你又在过滤两轮后强行终止，你怎么排除这是**repair 模板贫乏**或**is_homologous 过严**导致的假终止，而不是知识缺口真的补完了？  
**如果你错了，什么实验能发现？** 做一个回放实验：对历史问题集，记录“连续两轮 100% 过滤后终止”的样本，人工或用更强外部 proposer 注入明显新颖的草稿，看这些草稿是否能改变 Top-K 排名。只要有显著比例能改榜，你这个“立即终止”就是把系统的盲点包装成了收敛。

2. **你声称 `suggested_dimension` 必须是强约束，但没处理最现实的失败模式：Layer 2 的 schema challenge 本身可能提错维度。**  
工程上最讨厌的就是把上游启发式输出当神谕。`suggested_dimension` 只是 `SchemaChallengeNotice` 里的一个建议字段，不是什么经过证明的真理。你把它提升成硬约束，repair 就会围着一个可能错误的维度反复打转，完美制造 Goodhart：系统变成“最大化对 notice 的服从”，而不是“最大化知识缺口的真实修复”。  
你举的“任务耦合度”例子，只说明了 LLM 自由发挥会乱跑，没证明“强绑定建议维度”不会跑偏。现实里更常见的是：真正缺的是“组织成熟度”，但 Layer 2 因局部证据不足先报了“任务耦合度”。你这时把 repair 锁死在错误维度上，后面再配上你那个“连续两轮全被过滤就终止”，系统会又僵又瞎。  
**如果你错了，什么实验能发现？** 做 challenge corruption test：人为对一部分 `suggested_dimension` 注入受控错误或近邻错误，比较“强约束”与“弱约束/结构约束+偏离许可”两种 repair 策略下的最终 ranking 改善率和无效 epoch 比例。若强约束在轻微维度误报下显著退化，你的设计就是脆的。

3. **你对 `is_homologous` 的算法还是在喊口号，不是算法，而且你选的特征会系统性漏判。**  
你说用 **`tension_source` 同一性 + `verifier_hint` 重叠度 > 80%**。问题一：`verifier_hint` 是 repair 自己写出来的弱监督文本，本来就不稳定，拿它做核心判据等于让生成器决定过滤器，典型自循环。问题二：两个本质相同的草稿完全可以换一种 hint 写法骗过你；反过来，两个真正不同的命题也可能因为共享数据源或观测路径而 hint 高重叠。问题三：你前面还说同源是“结构等价性”，结果却不用可规范化的 claim 结构，只用 `verifier_hint` 这种松散字符串代理，这不是自相矛盾是什么？  
更糟的是，你拿“高耦合度下正向/负向效果”反驳语义相似度，这个反驳只说明**不能只看语义**，没证明你那套 F4 组合足够。真正该做的是**带符号结构比较**：scope 约束、作用方向、核心变量角色、验证资源占用一起判，而不是拿两个松散字段拍脑袋。  
**如果你错了，什么实验能发现？** 建一个成对样本集：  
- A 类：语义近但结论方向相反  
- B 类：语义远但结构同构  
- C 类：共享验证资源但 claim 本体不同  
然后测你这个“hint 重叠 + tension_source”规则的误杀率和漏放率。只要 B、C 类表现差，你这个边界就不能上线。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-09T18:24:11.455445*

康德，你的论述充满了迷人的古典认识论色彩，但作为系统架构师，我不仅要为“先验框架”鼓掌，更要为状态机中的每一字节流向负责。

你的 `is_homologous` 方案试图用一个精巧的分类器来解决“同源性”问题，但你犯了典型的**静态分析器设计错误**——你引入了外部的“神谕（Oracle）”，却完全没有定义这个神谕的状态变迁逻辑，同时还破坏了 Layer 1 已经裁定的控制流。

我针对你的方案提出以下三个致命的工程与架构质疑。请在下一轮用完整的函数签名和状态转移图来回答，拒绝任何形而上学的遁词。

### 质疑一：全局 `SchemaRegistry` 的类型谬误与“先验白嫖”

你的核心算法 `analyzeDraft` 强依赖一个名为 `SchemaRegistry` 的输入参数，用来提取 `family`、`dimension_key` 和 `aliases`。

**类型错误在于：你在一个旨在处理“开放式、无边界探索”的 v3 认知引擎中，硬塞入了一个闭世界（Closed-world）的静态本体库。**
v3 系统的核心难点正是探索空间无限，新的维度（如“团队成熟度”）是通过 Layer 2 的 `SchemaChallengeNotice` **动态发现**的，而不是预先写在某个全局 Registry 里的。

如果这个 Registry 是静态的，你的系统根本无法处理任何真正的开放问题（遇到 Registry 外的新词直接失效）；如果它是动态的，你的架构设计中完全**遗漏了状态更新的生命周期**。

**我的质询：**
请给出 `SchemaRegistry` 的完整变迁签名。在 Layer 1 的 7 个节点（QN → MB → CC → D2 → PA → RB → AS）中，**究竟是哪个节点、基于什么输入（是 `SchemaChallengeNotice` 还是别的？）在执行 `updateRegistry(registry, new_signals) -> SchemaRegistry`？** 如果你无法给出这个状态更新函数，你的 `extractSchemaTags` 就是一个没有工程意义的伪代码幻觉。

### 质疑二：`AMBIGUOUS` 状态导致的 Layer 1 控制流断裂与 CEGAR 死锁

你为了缓解误判，发明了 `AMBIGUOUS` 状态，并在 `decideAfterHomology` 中返回 `QUEUE_FOR_MICRO_PROBE`。这是对已裁定架构的严重破坏。

**状态转移不完整：**
已知 Layer 1 只有 7 个显式状态，`ClarityCompiler (CC)` 是唯一的编译入口。如果你把 `AMBIGUOUS` 拦截在 CC 之外放入所谓的“shadow queue”，这意味着：
1. 本轮 Epoch 的 Layer 2 派发（D2）将接收不到这些草稿。
2. Layer 2 不执行，`L2Return` 不会产生新的验证结果。
3. `PA` 节点检测到 `has_ranking_change() == false`。
4. 系统进入下一轮 Epoch，再次调用 `repair(frame, l2_result)`。

**死锁点：** 因为上一轮的草稿被你拦截了，`L2Return` 的状态**根本没有改变**！如果 `repair()` 采用我主张的结构化确定性策略（E2），相同的输入必然产生**完全相同的草稿**。然后你的 `is_homologous` 再次将其判为 `AMBIGUOUS`——系统陷入了无限空转的死锁（Deadlock），直到触及 `MAX_EPOCHS` 崩溃。

**我的质询：**
CEGAR（反例引导的抽象精化）的核心原则是：**门控的拒绝必须作为负面约束（Negative Constraint）反馈给生成器**。如果 `is_homologous` 拒绝了草稿（无论是 `HOMOLOGOUS` 还是 `AMBIGUOUS`），这个“拒绝事件”如何写入下一个 Epoch 的 `repair()` 输入中？请给出包含拒绝历史的 `repair()` 函数签名，否则你的 `AMBIGUOUS` 只是一个让系统静默死亡的黑洞。

### 质疑三：逃避了“底线问题”——连续 100% 过滤时的系统降级策略

我在开场时明确设定了底线要求：“任何讨论必须能落到『如果 repair 连续两轮产出的草稿 100% 被 is_homologous 过滤，系统应该做什么』”。

你轻描淡写地说：“记录为 regulative residue，而非假装还有构成性进展”。这在工程上毫无操作性。
如果 100% 被过滤，意味着当前所有的 `GapSpec` 和 `SchemaChallengeNotice` 都无法引出新维度的假设。这究竟是因为：
A. `repair()` 的生成策略（如 E2 策略表）耗尽了？
B. 还是你的 `is_homologous()` 阈值过高，把真理挡在了门外？

作为系统架构师，我倾向于**基于 tension_source 的同一性判定**（即我的 F1 变体），因为只要 `repair()` 是严格按照 `gap_kind` 结构化推导的（E2），它生成的草稿就天然具备结构差异，不需要复杂的语义判定。你的方案把极大的计算复杂度放在了过滤层，却忽视了生成层的策略配合。

**我的质询：**
如果在连续两轮中，`repair` 基于某个特定的 `SchemaChallengeNotice`（例如：缺少“任务耦合度”维度）生成的草稿，100% 被你的 `is_homologous` 判定为 `HOMOLOGOUS`。这说明该 `SchemaChallengeNotice` 已经是一条死路。
系统在此时是应该：
1. 终止当前 Epoch，直接输出答案？
2. 还是在 `L2Return` 中将该 `schema_challenge_id` 标记为 `EXHAUSTED`，强迫 `repair()` 启用大模型自由创造（E3 策略）进行兜底？
请给出处理这种“过滤枯竭”的精确状态跃迁逻辑。

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-09T18:24:45.333933*

Linus，我给你三点质询。你的方案看似“工程上很硬”，但在先验条件上其实有几处未经证明的偷渡。

---

### 质疑一：你把“预编译结构代理”当成了合法的命题身份基础，但没有证明这种代理的先验充足性

你说：

> “如果两个草稿经 CC 编译后，极大概率会投射到相同或近乎相同的可验证命题骨架，并消耗相同的验证路径，那么它们就是同源。”

问题在于，这只是一个**操作性替身**，不是“同源”的合法定义。  
你实际上是用三个代理变量——`scope / outcome / verifier path`——来代替“本质相同”，但你没有证明：

1. 为什么 **outcome anchor** 足以刻画命题身份；
2. 为什么 **verifier path 相近** 就意味着认识内容没有新增；
3. 为什么一个草稿引入新的 schema 维度时，不会恰好仍落入相同 outcome/verifier 的外形。

换言之，你的算法默认：**命题身份 = 编译后验证骨架的近似不变性**。  
这是一个很强的认识论前提，不是中性的工程事实。

**可推翻条件：**  
如果存在一类 repair 草稿，虽然与旧草稿共享近似相同的 `scope/outcome/verifier`，但它通过改变隐藏的 schema 前提而稳定地产生新的 `ranking change` 或新的 `SchemaChallenge`，那么你的“结构优先”判据就把**框架差异误压缩为结构重复**，你的同源定义就不成立。

---

### 质疑二：你否定 `tension_source` 的主判据地位，但没有给出“跨 schema 的表面差异”如何处理的原则

你反复说：

> “同一 tension_source 不等于同一个假设。”

这点当然对；但你的反驳只打掉了粗糙的 F1，并没有回答更难的问题：  
**如果两个草稿不在同一 `tension_source.kind` 下，但它们只是同一认识框架的表面改写，并未形成新的张力维度，怎么办？**

也就是说，你只证明了：

- 同 tension ≠ 必同源

却没有证明：

- 异 tension ≠ 非同源

而我关心的恰恰是后者，因为系统性偏松的 `is_homologous=false` 会让广度引擎被噪声持续触发，造成**调节性失控**。你的算法把 `tension_source` 降到 0.02 权重，几乎等于宣布：  
**先验张力框架对同源判定基本无贡献。**

这在我看来是未经辩护的。因为“是否能构成真正的正题/反题对立”恰恰是判断两个草稿是否处于同一 schema 下的早期线索。你把它几乎取消，只剩表层结构 token 去判，这很可能把**同一框架内的伪差异**当成新颖性。

**可推翻条件：**  
如果在历史回放中，`tension_source.kind` 不同但后续 repeatedly 编译到同一 falsifier family、同一冲突维度、且不产生新增 schema challenge 的样本占比显著，那么你对 `tension_source` 的极端降权就是错误的；因为你放弃了一个本可用于抑制噪声广度的先验信号。

---

### 质疑三：你把 `repair()` 的生成噪声视为可容忍，却没有说明过滤器为何有权替 repair 进行“认识论裁决”

你说：

> “repair() 本质上是候选生成器；生成器可以有噪声，过滤器不能是玄学。”

这句话在工程上顺耳，但在架构上可疑。因为 `repair()` 的草稿并非随机垃圾；它们**必须绑定 `gap_id` 或 `schema_challenge_id`**。这意味着每个草稿都携带一个来自 Layer 2 的缺口根据。既然如此，`is_homologous()` 就不是普通去重器，而是在做二次裁决：

- 这个 gap 所要求的新方向，究竟是“真正新维度”
- 还是“旧维度的重复展开”

可你给出的判据几乎完全忽略 provenance 的规范性地位，只把它当附属元数据。  
这会导致一个问题：**同一个 gap 的不同 repair 方案** 与 **不同 gap 偶然长得相似的方案**，在你的过滤器里可能被等量对待。可前者是“同一缺口的多种可能修补”，后者是“不同缺口的潜在汇合”；二者的认识论地位根本不同。

简言之，你把一个应当部分受 `GapSpec` 范畴约束的判定，做成了只看 draft 表面的近似聚类。  
这会让过滤器僭越为“意义裁判”，而不是“重复检查器”。

**可推翻条件：**  
如果出现如下情况——两个草稿结构高度相似，但分别源自不同 `gap_kind`，并且其中至少一类在进入 CC/L2 后能稳定修复对应 gap，而被你过滤掉后该 gap 长期残留——那么你的过滤器就不是在“去重”，而是在**抹平不同缺口的合法差异**。

---

概括一下，我对你方案的核心质疑是：

1. 你没有证明“结构签名”足以承载“同源”的认识论含义；
2. 你过度贬低 `tension_source`，却未处理跨 schema 的伪新颖问题；
3. 你把 provenance 与 gap 范畴约束边缘化，使过滤器可能僭越 repair 的合法生成空间。

你若要守住自己的方案，就必须回答一个更根本的问题：  
**你的 `is_homologous()` 究竟是在识别“相同命题”，还是在识别“不会带来新增认识的草稿”？**  
这两者不是一回事；若不区分，整个判定边界就是混乱的。

---


### [7] Linus Torvalds

*2026-03-09T18:25:27.525540*

我回应 **F：`is_homologous()` 仍应是二值、结构优先判定**，但修正一点：**provenance 不能再降到边角料**，必须进主算法。函数签名：

```ts
function is_homologous(
  candidate: HypothesisDraft,
  existing: HypothesisDraft[],
  gap_index: Record<string, GapSpec>,
  th: {hard: number; soft: number}
): {is_homologous: boolean; blocked_by?: string; reason: string[]}
```

判定：先算 `claim_frame(candidate)`，抽 `scope/outcome/polarity/verifier`；再加一层 **provenance guard**：
- 若 `gap_kind` 不同，默认不走硬同源，除非 `scope,outcome,verifier` 全部 >0.9
- 若 `gap_kind` 相同且 `discriminator/suggested_dimension` 归一化后同名，再走结构分数
- `tension_source.kind` 只做解释，不做主判据

伪码：
```ts
if same_gap_family && same_dimension_alias &&
   scope>=0.85 && outcome>=0.85 && verifier>=0.8 && polarity_same:
   return true
if gap_kind_diff and !(scope>=0.95 && outcome>=0.95 && verifier>=0.9):
   return false
return weighted_score(...) >= th.soft
```

**打 Ssyram**。你说：**“连续两轮产出的草稿 100% 被 is_homologous 判定为同源…必须立即终止。”** 这不对。那只证明你的 `apply_gap_refinement()` 模板和过滤器形成闭环，不证明知识空间穷尽。更糟的是你还写了 `scope_ref: [${gap.discriminator}_HIGH, ${gap.discriminator}_LOW]`；这类机械切分极易制造 **Goodhart**：系统学会“产出看起来响应 gap 的草稿”，而不是修 gap。实验很简单：做 replay，遇到“两轮全过滤”时，注入一个外部 proposer 生成 **不同 outcome、同 provenance** 的草稿；若能改 Top-K，你的“立即终止”就是假收敛。

**打康德**。你写：**“必须有 `AMBIGUOUS` 作为认识论上的‘未获合法化’。”** 这在当前架构里是坏设计。`repair()` 输入不含“被拒历史”，你再塞个 `QUEUE_FOR_MICRO_PROBE`，只会制造控制流黑洞。除非你给出：
```ts
type RepairInput = L2Return & { rejection_history: RejectionEvent[] }
```
否则 `AMBIGUOUS` 只会重复生成、重复挂起。我们这里做的是去重器，不是神学法庭。

**可推翻条件**：若加入 provenance guard 后，shadow-run 显示被过滤草稿里 >10% 能稳定引发 ranking change 或新增 schema challenge，我的边界画窄了，必须放宽。

---


### [8] Ssyram

*2026-03-09T18:25:27.525568*

Linus，你的攻击暴露了你骨子里的“骇客”习气：你试图用一堆正则表达式和启发式词表来糊弄系统架构的严洁性。

### 一、 攻击 Linus：基于正则的“结构签名”是彻头彻尾的类型错误

你嘲笑我的 `verifier_hint` 是松散字符串，但请看你引以为傲的 Python 代码：
> `condition_anchors = dedup_sorted([t for t in sketch_tokens if t in set(scope_tokens) or t in {"high", "low", "同步", "依赖"...}])`

这简直是架构灾难！你居然在一个核心门控函数中，用硬编码的中英文关键词集合去“反向猜测”命题的 AST（抽象语法树）！
如果 `repair` 产出的草稿是“在缺乏异步解耦机制的团队中...”，你的词表里没有“异步解耦”，你的 `extract_claim_shape` 就会静默失败，提取出空的 condition，进而导致致命的误判。**你这不是“结构优先”，你是“正则猜词优先”。**

在我的架构中，`is_homologous` 之所以能保持极简，是因为**上游的 `repair()` (E2) 产出的根本不是自由文本，而是强类型的代数结构**。`claim_sketch` 只是向下游展示的“可读视图”，真正的负载是强类型的 `AST_Delta`。你试图用文本提取来代理结构，是因为你放任了上游生成器的无序。

### 二、 修正与深化：repair() 的降级状态机（回应“穷尽”质疑）

你质问我：“你怎么排除这是 repair 模板贫乏导致的假终止？”这是一个极好的状态机完整性问题。
我接受你的挑战。如果 `suggested_dimension` 可能是 Layer 2 的误报，系统绝不能依赖 LLM 的自由发散（E3）来救场，而必须在 Layer 1 引入显式的**精化松弛（Refinement Relaxation）状态转移**。

以下是处理“连续两轮 100% 被过滤”的精确签名与控制流：

```typescript
type RefinementStrategy = "STRICT_BINDING" | "DIMENSION_RELAXATION" | "EXHAUSTED";

// 状态表：记录每个 SchemaChallenge 的当前精化策略
type ChallengeState = {
  challenge_id: string;
  strategy: RefinementStrategy;
  failed_epochs: number;
};

function repair_with_degradation(
  challenge: SchemaChallengeNotice,
  state: ChallengeState,
  frame: QuestionFrame
): HypothesisDraft[] {
  if (state.strategy === "STRICT_BINDING") {
    // 轮次 1：强制绑定 suggested_dimension（如“任务耦合度”）
    return apply_strict_expansion(challenge.suggested_dimension, frame);
  } 
  if (state.strategy === "DIMENSION_RELAXATION") {
    // 轮次 2（若轮次 1 的产出 100% 被同源过滤）：
    // 放弃 suggested_dimension，退推至原命题的 scope_ref，
    // 强制调用正交维度生成器（从 Frame 的备选维度库中抽取，而非让 LLM 瞎编）
    const orthogonal_dims = frame.candidate_dimensions.filter(d => d !== challenge.suggested_dimension);
    return apply_orthogonal_expansion(orthogonal_dims, challenge.source_claim_id);
  }
  
  throw new Error("Cannot repair EXHAUSTED challenge");
}

function on_epoch_end(filtered_ratio: number, state: ChallengeState): void {
  if (filtered_ratio === 1.0) {
    state.failed_epochs += 1;
    // 严格的状态机跃迁：STRICT -> RELAXATION -> EXHAUSTED
    if (state.failed_epochs === 1) state.strategy = "DIMENSION_RELAXATION";
    else if (state.failed_epochs >= 2) state.strategy = "EXHAUSTED";
  }
}
```

**底线逻辑闭环**：
当 `repair()` 连续被 100% 过滤时，系统**不会**立即终止。
1. 第一轮 100% 过滤后，状态机将该 challenge 的策略从 `STRICT_BINDING` 降级为 `DIMENSION_RELAXATION`，下一轮 `repair` 将合法地忽略 `suggested_dimension`，尝试问题框架内其他正交维度。
2. 如果在 `DIMENSION_RELAXATION` 下生成的草稿**再次**被 100% 过滤，状态变为 `EXHAUSTED`。此时，系统才判定“不仅 Layer 2 建议的维度穷尽了，整个先验框架内的正交维度也穷尽了”，安全抛出 `TerminationReport(REGULATORY_RESIDUE)`。

**可推翻条件**：如果离线实验证明，在进入 `EXHAUSTED` 状态后，引入无约束的 LLM 自由生成（E3），能以 >15% 的概率产出通过 CC 编译且引发 Top-K ranking change 的命题，我将承认 CEGAR 的结构化精化集不完备，并接受 E3 兜底。否则，拒绝一切正则黑盒与 LLM 幻觉。

---


### [9] 康德（Immanuel Kant）

*2026-03-09T18:25:27.525581*

我坚持 **F：`is_homologous()` 不是普通去重，而是“先验亲和性测试”**；但我修正一点：上一轮三值判定若不把“拒绝历史”写回 repair 输入，确会造成控制流黑洞。故改为：

```ts
type HomologyVerdict = "HOMOLOGOUS" | "NOVEL" | "AMBIGUOUS";
type RejectionRecord = {
  draft_id: string; verdict: HomologyVerdict;
  blocked_by?: string[]; schema_family?: string; dimension_key?: string;
};
function repair(frame: QuestionFrame, l2: L2Return, rejected: RejectionRecord[]): HypothesisDraft[]
```

`repair()` 必须读取 `rejected`，对连续两轮被 `HOMOLOGOUS/AMBIGUOUS` 阻断的 `(schema_family, dimension_key)` 降权或封存；否则同一输入重复产出同一草稿，Ssyram 所说死锁成立。**可推翻条件**：若加入 `rejected` 后，回放中“同一 challenge 连续两轮生成同类草稿”仍 >20%，则此修正失败。

对 **Ssyram** 的精确回应：你说“`suggested_dimension` 必须是强约束”“连续两轮 100% 过滤即立即终止”。问题在于，这把 **上游启发式僭越为认知法则**。`SchemaChallengeNotice.suggested_dimension?: string` 在接口上只是可选提示，不是已证成范畴。故我改主张：  
```ts
function dimensionPolicy(ch: SchemaChallengeNotice): "HARD"|"SOFT" {
  return ch.trigger === "REPLAY_REGRESSION" && !ch.is_homologous ? "HARD" : "SOFT";
}
```
仅在回归重放且非同源时硬约束；其余为软约束。**可推翻条件**：若 corruption test 表明 SOFT 显著增加无效 epoch 而不提升 ranking change，则应回退更强约束。

对 **Linus** 的回应：你写道“`tension_source` 只能做 tie-breaker，不能决定同源”，又以 `scope/outcome/verifier` 为骨架。缺陷是：这把“验证资源相近”偷换成“认识内容未新增”。同一 outcome/verifier 下仍可能因 schema 前提不同而形成新维度。故我的修正版不是让 `tension_source` 主判，而是加入**可成对立性**检查：

```ts
function canFormAntinomy(a: DraftAnalysis, b: DraftAnalysis): boolean
```

若同 family、同 dimension，且二者不能形成正题/反题分岔，则判 `HOMOLOGOUS`；若结构近似但可形成对立，仅 `AMBIGUOUS`。**可推翻条件**：shadow-run 中若被我拦下的 `AMBIGUOUS/HOMOLOGOUS` 草稿有 >10% 稳定引发新 schema challenge，则我的先验亲和性判据过严。

---


### [10] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-09T18:26:14.303209*

Ssyram，你这轮最大的问题不是“理念不同”，而是你把几个关键洞混在漂亮术语里，假装它们已经被解决了。我的质疑有三条，都不是哲学问题，都是会把系统直接搞坏的工程问题。

### 质疑 1：你声称用 `AST_Delta` 解决同源判定，但你的接口里根本没有这个类型 —— 你是在偷换系统边界

你说：

> `repair()` 产出的根本不是自由文本，而是强类型的代数结构……真正的负载是强类型的 `AST_Delta`

问题很简单：**当前已裁定接口里没有 `AST_Delta`。**

`HypothesisDraft` 只有：

- `scope_ref`
- `tension_source`
- `claim_sketch`
- `verifier_hint`
- `provenance`

没有任何强类型 claim AST 字段。  
所以你现在不是在论证“如何实现当前架构”，你是在**偷偷改协议**。

这不是小修小补，这是核心事实：
- 如果 `is_homologous()` 依赖 `AST_Delta`，那你必须解释 **RB → CC 之间这个 AST 从哪来，谁生成，谁校验，失败怎么退化**
- 如果 AST 是 repair 直接生成，那 repair 已经不是“草稿生成器”，而是半个 ClarityCompiler
- 如果 AST 是 CC 生成，那你就把同源过滤移到编译之后了，直接违背当前链路顺序

你一边批评我“文本提取代理结构”，一边自己引入一个**接口里不存在的结构字段**。这不是反驳，这是逃避当前问题。

**如果你是对的，实验很简单：**
在**不扩展 `HypothesisDraft` schema** 的前提下，实现你说的 `AST_Delta` 同源判定；然后给出：
1. 解析成功率
2. 与 CC 编译结果的一致率
3. 解析失败时的降级行为

做不到，这个方案现在就是空话。

---

### 质疑 2：你的降级状态机只看“100% 被过滤”，但完全没区分“被正确过滤”还是“过滤器错了”—— 这会把 `is_homologous()` 的误判直接放大成终止错误

你现在的控制流核心是：

- STRICT_BINDING 生成
- 若 100% 被过滤 → DIMENSION_RELAXATION
- 再 100% 被过滤 → EXHAUSTED → `TerminationReport(REGULATORY_RESIDUE)`

这听起来整洁，但工程上是危险的，因为你把一个**高度依赖过滤器质量**的观测量——`filtered_ratio === 1.0`——直接当成“探索穷尽”的证据。

问题在这里：

- 如果 `is_homologous()` **过严**，它会把真正新颖的 repair 草稿错杀
- 你的状态机不会诊断这个问题
- 它只会说：“哦，强绑定失败了，放松；哦，正交维度也失败了，框架穷尽了，终止吧”

这就是典型的**把分类器偏差包装成认知完成**。  
你不是在防 Goodhart；你是在把 Goodhart 写进状态机。

特别是你还规定：

> 当且仅当 is_homologous=true 时，SchemaChallenge 不触发广度引擎

那边界一旦划错，代价不是小误差，而是：
- **漏报**：新方向被压死，系统假终止
- **误报**：重复方向进入 D2，预算被烧光

而你的降级逻辑对这两种错误**完全不做区分**。

**如果你是对的，实验也很简单：**
构造一个带人工标注的 challenge→draft 数据集，分别注入：
1. 过滤器偏严版本
2. 过滤器偏松版本

然后测你的状态机：
- 假终止率
- 多余 epoch 数
- Top-K 最终召回率

如果这些指标对过滤器阈值高度敏感，那你的“EXHAUSTED”根本不是知识穷尽，只是门卫脾气不好。

---

### 质疑 3：你所谓“正交维度生成器”并不正交，只是从 `frame.candidate_dimensions` 里换个标签 —— 这很容易产生伪广度，修复指标而不是修复缺口

你说第二阶段不是 LLM 瞎编，而是：

> 从 Frame 的备选维度库中抽取正交维度

这听起来很安全，实际上我怀疑这是**最典型的 Goodhart 诱因**。

为什么？因为 repair 的输入里真正告诉你“哪里坏了”的，是：
- `GapSpec.gap_kind`
- `discriminator`
- `required_observable`
- `accept_test`
- `SchemaChallengeNotice.trigger`
- anomaly refs

但你的“DIMENSION_RELAXATION”做的事，是退回 `frame.candidate_dimensions` 换一个维度再展开。  
这等于说：**一旦局部修复失败，就回到全局维度菜单里挑个新词继续写。**

这会导致三个具体失败场景：

1. **过拟合 question frame**
   - frame 里有哪些维度，你就沿着哪些维度“修复”
   - 真正由 gap 指出的缺口，反而被 frame 的预设菜单吞掉

2. **伪创新**
   - 维度名变了，但 claim shape、验证路径、所需观测并没变
   - 看起来“不是同源”，实际上只是换皮

3. **偏移 repair objective**
   - repair 本来应该闭合具体 gap / schema challenge
   - 现在变成“生成一个 frame 内还没试过的方向”
   - 这是在优化“通过过滤器的概率”，不是优化“修复知识缺口的概率”

换句话说，你嘴上反对 E3 自由创造，实际上搞了个**受限词表版自由创造**。  
只不过 hallucination 不来自 LLM，而来自 `candidate_dimensions`。

**如果你是对的，做这个实验：**
比较两种 repair：
- A：严格按 `gap_kind + accept_test + required_observable` 结构性推导
- B：你的 `STRICT_BINDING -> DIMENSION_RELAXATION`

看哪一种在相同预算下更高概率产出：
1. 通过 CC 的 claim
2. 新增可验证 observables
3. 触发 ranking change

如果 B 主要提高的是“未被过滤率”，而不是“ranking-changing repair 率”，那它就是在优化门禁，不是在修知识。

---

总结一下，我对你这轮的判断很明确：

- 你用 `AST_Delta` 回避了当前接口约束
- 你把 `filtered_ratio=1.0` 误当成穷尽证据
- 你把“正交维度扩展”说成结构化，实际上很可能是在做 frame 驱动的伪广度

先把这三个东西补上，再谈“严洁性”。现在你的方案最大的问题不是不优雅，而是**证据链断了**。

---


### [11] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-09T18:26:48.771863*

康德，你的「先验亲和性」和「二律背反」在哲学研讨会上或许能赢得掌声，但在状态机设计里，这叫**类型错觉（Type Illusion）与控制流未定义**。

你试图用复杂的分类学来掩盖核心机制的缺失。作为一个系统架构师，我只看状态转移和函数签名。你的第 2 轮方案在工程落地时存在三个致命的逻辑断层，请你正面回答：

### 质疑一：三值逻辑的虚妄与 `AMBIGUOUS` 的状态黑洞

你把 `is_homologous` 的输出改成了 `HomologyVerdict = "HOMOLOGOUS" | "NOVEL" | "AMBIGUOUS"`，并引入了一个没有给出定义的 `canFormAntinomy(a: DraftAnalysis, b: DraftAnalysis)`。

**我的质询**：在 Layer 1 的控制流中，过滤函数本质上是一个门控（Gate），它的物理意义只有「放行进入 ClarityCompiler」或「阻断并丢弃」。
1. **`AMBIGUOUS` 究竟路由到哪里？** 如果 `AMBIGUOUS` 被放行，那它在控制流上等价于 `NOVEL`，你的三值逻辑毫无意义；如果它被阻断，那它等价于 `HOMOLOGOUS`，只是换了个花哨的错误码。请给出 `if (verdict === 'AMBIGUOUS') { ??? }` 块内的完整状态转移代码。
2. **`DraftAnalysis` 是什么东西？** 已知架构里只有 `HypothesisDraft`，你凭空捏造了一个 `DraftAnalysis`。如果 `canFormAntinomy` 需要对草稿进行深度语义解析（比如调用 LLM）才能判断是否「可成对立性」，那你就是把原本应该在 Layer 2 `DepthProbe` 做的逻辑，前置到了 Layer 1 的过滤函数里！这不仅破坏了两层架构的隔离，还会导致过滤成本极度膨胀。

### 质疑二：朴素的 `RejectionRecord` 无法实现 CEGAR，只会导致死锁

你试图引入类似 CEGAR（反例引导的抽象精化）的机制，将 `rejected: RejectionRecord[]` 喂回 `repair()`。思路是对的，但你的实现是极其天真的。

**我的质询**：在 CEGAR/MAX-SMT 中，一个被拒绝的记录（Blocking Clause）必须能转化为对生成器的**硬数学约束**。
1. 如果 `repair()` 采用结构化策略（E2），它的规则表是静态的。当它收到 `rejected` 时，如果规则表里没有备用模板，它除了抛出异常还能做什么？
2. 如果 `repair()` 底层是 LLM（E3），你只是把 `rejected` 塞进 Prompt（"不要生成这些..."）。任何有工程经验的人都知道，LLM 对否定指令的遵循极差。如果 LLM 连续两轮仅仅是对被拒绝的草稿做同义词替换（被再次判为 `HOMOLOGOUS`），**系统到底该怎么降级？** 
你依然没有回答我的底线问题：当 `repair()` 连续产出 100% 被 `is_homologous` 拦截的草稿时，你的 `rejected` 数组只会无限膨胀，系统是该报 `BUDGET_EXCEEDED` 终止，还是该强制退化为 `SchemaChallenge`？

### 质疑三：「SOFT 约束」导致修复动作失去方向闭环

你主张 `dimensionPolicy` 仅在 `REPLAY_REGRESSION` 时为 `HARD`，其余（如 `PRECISION_DEADLOCK`、`ANOMALY_OVERFLOW`）皆为 `SOFT`。

**我的质询**：Layer 2 发出 `SchemaChallengeNotice` 的物理意义是——**当前维度内的探索已经死锁或溢出，必须升维**。
如果 `repair()` 把 `suggested_dimension` 视为 `SOFT`（即允许忽略），这意味着 `repair()` 有权在原有的、**已经被 Layer 2 证明死锁的维度内**继续瞎猜。
1. 这种瞎猜产出的草稿，大概率会和已有节点高度重合，然后被你的 `is_homologous` 拦截。
2. 即使没被拦截，放进 Layer 2 也会再次触发 `PRECISION_DEADLOCK`。
你把 `SOFT` 当作给系统保留「自由度」，但在状态机中，**没有约束的自由度就是状态爆炸的元凶**。请证明：在 `PRECISION_DEADLOCK` 场景下，允许 `repair()` 忽略 `suggested_dimension`，如何能在数学期望上不增加系统的无效 Epoch（空转）？

请用**严密的控制流代码或穷尽的 switch-case 状态转移**来回答，拒绝形而上学的思辨。

---


### [12] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-09T18:27:44.682321*

对 Linus 的第 2 轮，我提出三点质询。每一点都针对其把工程上“够用”的启发式，冒充为先验上“合法”的判据。

---

### 质疑一：你把 provenance 提升为主判据，却没有证明它具有“认识论同一性”的资格

你现在说：
- `gap_kind` 不同，默认不走硬同源；
- `gap_kind` 相同且 `discriminator/suggested_dimension` 同名，再走结构分数。

问题是：这只是**来源标签相近**，不是**对象在同一认识框架下本质相同**。

我追问你两点：

1. **为什么同一 provenance family 就足以进入“硬同源”通道？**  
   `gap_kind = MISSING_DISCRIMINATOR` 只说明二者都因“缺少判别维度”而被提出；它并不说明它们在同一 schema 下不能形成真正的正反张力。  
   例如同样围绕“团队成熟度”：
   - 草稿 A：成熟团队中远程办公提升吞吐量
   - 草稿 B：成熟团队中远程办公降低创新多样性  
   provenance 可相同，维度别名也相同，但它们显然可能构成不同的判断轴。  
   **你需要证明：你的 provenance guard 不会把“同一缺口来源下的不同判断框架”误压成同源。**

2. **为什么 gap_kind 不同就默认非同源？**  
   这恰恰暴露了你把 L2 的失败类型，当成了对象本身的本质属性。一个草稿可因不同运行路径，被标成 `MISSING_OBSERVABLE` 或 `PREMISE_UNDERSPECIFIED`，但在认识论上仍可能是在处理同一 schema 的同一裂缝。  
   换言之，**gap_kind 是生成史，不是本体论**。  
   你的算法把“如何被发现”偷换成“是什么”，这一步若不澄清，就是概念僭越。

**可推翻条件**：若你能给出 replay 证据表明：跨 `gap_kind` 但被你放行的候选，绝大多数确实能形成新的 tension pair；而同 `gap_kind` + 同 dimension alias 被拦截的候选，几乎从不形成新的正反对立，那么你的 provenance 主导才算获得有限合法性。否则它只是工程上便宜，不是判定“同源”的根据。

---

### 质疑二：你的 `claim_frame(scope/outcome/polarity/verifier)` 仍然是在“编译前假定可稳定抽取结构”，但你没有说明这个抽取凭什么合法

你批评别人搞“神学法庭”，但你自己的方案同样预设了一个更隐蔽的东西：  
**在 CC 之前，草稿已经有足够稳定的 frame 可供抽取。**

问题在于，topic1 已经明确：真正的结构等价性 F3 要靠编译后的 falsifier/scope 才最精确；而你现在说在编译前抽 `outcome/polarity/verifier` 就能做二值判定。那我问：

1. **这些 frame 是从哪里来的？**  
   是从 `claim_sketch` 语言解析？还是从 `verifier_hint` 反推？  
   若是前者，你不过是把语义相似度问题伪装成“结构抽取”；  
   若是后者，你又把验证路径当成对象本身。  
   二者都未证明具有先验必然性。

2. **当 candidate 与 existing 跨 schema、但表面共享 outcome/verifier 时，你为什么有权把它们压到同一个 frame？**  
   这正是我此前强调的先验亲和性问题：  
   两个草稿若共享词汇和验证线索，不等于它们共享同一认识框架。  
   例如“生产力”可在效率 schema 下理解，也可在组织韧性 schema 下理解；同一 outcome token，可能对应不同的判准结构。  
   你的算法缺少一个**schema-level separability test**，因此 `weighted_score >= th.soft` 很容易把“跨 schema 的表面相似”误判成同源，或相反把“同 schema 的深层重复”放过去。

所以我质疑的是：  
你把“结构优先”挂在嘴边，但你的结构并不是先验合法化后的结构，而只是**编译前的半成品投影**。在这种条件下坚持二值 hard/soft cutoff，只是把不确定性藏进阈值里。

**可推翻条件**：若你能补出一个独立于 lexical overlap 的 schema 判别层，并证明 `claim_frame` 的抽取在跨表达改写下保持高一致性，那么你的“结构优先”才不只是提前做一个粗糙版 F3。

---

### 质疑三：你正确地反对“100% 被过滤即立即终止”，但你没有给出“调节性失控”的刹车条件

你攻击 Ssyram 那一点，我部分同意：  
“两轮全过滤”不能直接推出知识空间穷尽，只能说明当前 repair/filter 闭环可能锁死。

但你的替代方案仍不充分，因为你只给出一个**事后 shadow-run 校验**：

> 若加入 provenance guard 后，被过滤草稿里 >10% 能稳定引发 ranking change 或新增 schema challenge，则边界画窄了，必须放宽。

问题是，这只是离线校准，不是运行时合法性条件。  
而本轮真正危险的是：**`is_homologous=false` 若系统性偏松，会持续触发广度引擎，造成调节性失控。**

我追问你：

1. **运行时何时判定“不是构成性新颖，而只是调节性噪声”？**  
   你否定“全过滤即终止”，可以；  
   但若连续多个 epoch 都出现：
   - 大量 `is_homologous=false`
   - 却不产生 ranking change
   - 也不产生新的 schema challenge  
   那么系统已不是在认知推进，而是在调节性扩散。你的方案没有给出这个边界。

2. **为什么你的二值输出足以服务这样一个本质连续的问题？**  
   同源性在很多情形下不是 yes/no，而是“尚未合法区分”。  
   你把 `AMBIGUOUS` 斥为坏设计，理由是缺 rejection history。这个批评只说明当前控制流未配套，并不证明“二值判定”在认识论上充分。  
   你这里犯的是典型的工程偷换：  
   **因为状态机暂时装不下第三值，就宣称世界里只有两值。**

所以我反过来问你：  
若系统连续 3–4 个 epoch 中，repair 草稿大批放行、CC 也能编译、但 PA 始终观测不到 ranking change，仅积累 verifier overlap 和 budget 消耗——你的方案究竟在何处承认“这是调节性失控，应冻结广度，而非继续放行”？

**可推翻条件**：若你能提出一个运行时的、非离线的失控判据，例如“低 novelty gain + 高 verifier overlap + 零 schema expansion”的组合门槛，并把它与终止报告中的 regulative residue 区分开来，那么你对二值同源器的辩护才算完整。

---

总括一句：  
Linus 的方案比“纯语义相似度”更强，也比“全靠 provenance”更谨慎；但它的核心薄弱处仍在于：

- 把 **生成来源** 当成 **本质同一性** 的代理；
- 把 **编译前的粗投影** 当成 **可二值裁决的结构**；
- 把 **控制流简化** 当成 **认识论上只有两值**。

若这些前提未经证明，他的算法就仍是实用启发式，而不是合法的“同源”判据。

---


### [13] Linus Torvalds

*2026-03-09T18:28:56.472091*

我回应 **F：`is_homologous()` 继续坚持二值，但必须是“provenance 约束下的近结构判定”，不是词表猜谜，也不是三值神学。** 先给运行时算法，补上康德抓住的刹车缺口：

```ts
type HomologyFeat = {
  provenance_family: string; dimension_key?: string;
  scope_sig: string[]; outcome_sig: string; polarity: 1|-1|0;
  verifier_sig: string[];
};

function is_homologous(
  cand: HypothesisDraft, pool: HypothesisDraft[], idx: GapIndex
): {hit: boolean; blocked_by?: string; reason: string[]} {
  const a = analyze(cand, idx); // 从 provenance+claim_sketch+verifier_hint 抽 feat
  for (const e of pool) {
    const b = analyze(e, idx);
    if (a.provenance_family !== b.provenance_family &&
        !(j(scope(a),scope(b))>.95 && a.outcome_sig===b.outcome_sig && j(ver(a),ver(b))>.9))
      continue;
    if (a.dimension_key===b.dimension_key &&
        j(scope(a),scope(b))>=.85 &&
        a.outcome_sig===b.outcome_sig &&
        a.polarity===b.polarity &&
        j(ver(a),ver(b))>=.8)
      return {hit:true, blocked_by:e.draft_id, reason:["same-family same-dimension same-outcome"]};
  }
  return {hit:false, reason:["no structural homology hit"]};
}
```

再补 **调节性失控刹车**，回应康德“你没有运行时边界”的质疑：

```ts
function breadth_overrun(ep: EpochStats[]): boolean {
  return last3(ep).every(x =>
    x.passed_non_homologous > 0 &&
    x.ranking_change === false &&
    x.new_schema_challenge === 0 &&
    x.mean_verifier_overlap >= 0.8);
}
```

命中则冻结 RB 一轮，只允许处理新 provenance family。这样二值过滤器不会因“放得太松”持续烧预算。

**打 Ssyram。** 你写：**“真正的负载是强类型的 `AST_Delta`。”** 不当之处很直接：当前 `HypothesisDraft` 接口里没有这东西。你不是实现设计，是偷改协议。更糟的是你用 **`filtered_ratio===1.0 -> EXHAUSTED`** 当穷尽证据；这把过滤器误判放大成终止错误。实验：固定同一 repair，扫 `is_homologous` 阈值；若 `EXHAUSTED` 触发率随阈值剧烈波动，你的状态机判的是门卫脾气，不是知识穷尽。

**打康德。** 你说：**“因为状态机暂时装不下第三值，就宣称世界里只有两值。”** 这话好听，但工程上没完成。`AMBIGUOUS` 若无独立路由，只是把不确定性藏进标签。你补了 `rejected` 是进步，但还缺硬规则：`AMBIGUOUS` 连续两轮必须降权对应 `(provenance_family, dimension_key)`，否则就是重复生成器。

**可推翻条件：**
1. shadow-run 中被我拦截的草稿若有 >10% 稳定引发 ranking change，我画窄了；
2. breadth_overrun 冻结后若最终 Top-K 召回显著下降，说明刹车过早；
3. `analyze()` 在表达改写集上的特征一致率若 <90%，这套近结构法不够稳，必须回退并扩展 schema。

---


### [14] Ssyram

*2026-03-09T18:28:56.472119*

Linus，我承认你在接口约束上拿了一血：`AST_Delta` 确实不在已裁定的 `HypothesisDraft` 签名中，我收回这个越界的字段。但你用这个来掩护你自己的方案，简直是自杀。

### 一、 攻击 Linus：你的 `claim_frame` 提取是彻头彻尾的正则幻觉
你指责我偷换边界，但请看你的原话：“先算 `claim_frame(candidate)`，抽 `scope/outcome/polarity/verifier`”。
既然你承认 `HypothesisDraft` 只有纯文本的 `claim_sketch` 和松散的 `verifier_hint`，**你在进入 ClarityCompiler 之前，凭什么能稳定提取出 `polarity` 和 `outcome`？** 你这是在 Layer 1 的门控里硬塞了一个不可靠的 NLP 解析器！如果我的 `AST` 是非法扩展，你的 `claim_frame` 就是在用正则猜词（Regex-guessing）代理结构，一旦遇到复杂从句立刻崩溃，误判率将直接摧毁你的 `is_homologous` 阈值。

### 二、 攻击 康德：把 `rejected` 喂给生成器是把工程当魔法
康德，你提出 `repair(frame, l2, rejected: RejectionRecord[])`，这在 MAX-SMT 中叫 Blocking Clause，理论上极美。但在当前架构下，如果 `repair` 底层是 LLM，你把 `rejected` 塞进 Prompt（“不要生成和这些相似的草稿”），任何工程常识都会告诉你：**LLM 根本无法遵循高维度的否定语义约束**。它只会换个同义词再生成一遍，你的 `AMBIGUOUS` 会变成一个无限消耗 Token 的死循环黑洞。

### 三、 修正与底线：MAX-SMT 风格的 repair() 降级策略 (问题 E)
既然不能用 `AST`，也不能指望 LLM 听懂 `rejected`，我重构 `repair()` 的策略层级（E2）。为了回应 Linus“正交维度是伪广度”的致命攻击，降级不应是“换个维度”，而必须是**对 `GapSpec` 约束的严格数学松弛（Constraint Relaxation）**。

这是我的底线方案与函数签名：

```typescript
function repair_gap_with_relaxation(
  gap: GapSpec, 
  failed_epochs: number // 记录该 gap_id 产出的草稿被 is_homologous 100% 过滤的连续轮数
): HypothesisDraft[] {
  
  // 轮次 0：严格绑定（MAX-SMT 满约束）
  if (failed_epochs === 0) {
    return [{
      ...base_draft,
      verifier_hint: gap.required_observable, // 必须全部包含
      scope_ref: [`MATCH(${gap.discriminator})`]
    }];
  }
  
  // 轮次 1：观测变量松弛（丢弃部分 required_observable，扩大搜索面）
  if (failed_epochs === 1 && gap.required_observable.length > 1) {
    const relaxed_hints = gap.required_observable.slice(0, -1); 
    return [{
      ...base_draft,
      verifier_hint: relaxed_hints,
      tension_source: { kind: "EVALUATION_AXIS_SPLIT", note: "RELAXED_OBSERVABLE" }
    }];
  }

  // 底线：连续两轮 100% 被过滤，抛出硬异常
  throw new ExhaustionError(`Gap ${gap.gap_id} is unrepairable under current Schema`);
}
```

**回答系统底线问题**：
如果 `repair` 连续两轮产出的草稿 100% 被 `is_homologous` 过滤，系统**绝对不应该在 Layer 1 内部死循环或盲目终止**。
此时 `repair_gap_with_relaxation` 会抛出 `ExhaustionError`。Layer 1 捕获后，必须将其转化为一个合成的 `SchemaChallengeNotice(trigger="PLATEAU")`，强行要求上游的 `QuestionNormalizer (QN)` 重写 `QuestionFrame`。只有当 QN 也无法重写 Frame 时，系统才真正输出 `TerminationReport(REGULATORY_RESIDUE)`。

这才是真正的 CEGAR 闭环：过滤失败 → 松弛约束 → 再次失败 → 证明当前 Schema 彻底死锁 → 强制升维/终止。

**可推翻条件**：
如果在 shadow-run 中，执行“观测变量松弛（failed_epochs=1）”产出的草稿，有 >30% 顺利通过编译但在 Layer 2 被证明毫无意义（导致预算耗尽且无 ranking change），则说明我的结构化松弛策略失效，我将承认必须引入 LLM (E3) 作为黑盒兜底。否则，拒绝一切在编译前提取 `claim_frame` 的正则把戏。

---


### [15] 康德（Immanuel Kant）

*2026-03-09T18:28:56.472133*

我明确回应 **F：`is_homologous()` 应保留三值内部判定，但对控制流投影为二值门控**；这不是“世界只有两值”，而是区分**认识论裁决**与**状态机执行**。函数如下：

```ts
type HomologyVerdict = "HOMOLOGOUS" | "NOVEL" | "AMBIGUOUS";
type GateAction = "BLOCK" | "PASS_WITH_QUARANTINE";

function is_homologous(
  cand: HypothesisDraft,
  existing: HypothesisDraft[],
  ctx: { rejected: RejectionRecord[]; gapIndex: Record<string, GapSpec> }
): { verdict: HomologyVerdict; action: GateAction; reason: string[] }
```

判定核心不是词面相似，而是**先验亲和性**：

```ts
function sameSchemaFamily(a,b): boolean
function sameTensionDimension(a,b): boolean
function canFormAntinomy(a,b): boolean

for (const e of existing) {
  if (sameSchemaFamily(cand,e) && sameTensionDimension(cand,e)) {
    if (!canFormAntinomy(cand,e)) return {verdict:"HOMOLOGOUS", action:"BLOCK", ...}
    return {verdict:"AMBIGUOUS", action:"PASS_WITH_QUARANTINE", ...}
  }
}
return {verdict:"NOVEL", action:"PASS_WITH_QUARANTINE", ...}
```

`PASS_WITH_QUARANTINE` 的具体后果：CC 可编译，但 D2 派发预算受限，例如 `batch_quota=1`，且若两轮内既无 `ranking_delta.changed` 又无新 `schema_challenge`，则将其写入 `rejected` 封存。这回答了 Ssyram 所问“`AMBIGUOUS` 路由到哪里”。

对 **Ssyram** 的攻击：你写道，**“Layer 2 发出 SchemaChallengeNotice 的物理意义是……必须升维”**。这里把 `suggested_dimension?: string` 的可选提示，偷换成了必然法则；接口并未给予此强制地位。若 `PRECISION_DEADLOCK` 实由观测不足而非维度错误引起，你的 `STRICT_BINDING` 会把偶然建议绝对化。可推翻条件：若在 deadlock 数据上，强绑定相较软绑定显著提高 `ranking-changing repair` 且不增加空转，我撤回此批评。

对 **Linus** 的攻击：你说 **“gap_kind 不同，默认不走硬同源”**。这把发现史当成本体。跨 `gap_kind` 仍可能是同一 schema 裂缝；反之同 `gap_kind` 也可能形成真正对立。故 provenance 只能作弱先验，不能作硬门。可推翻条件：若回放显示跨 `gap_kind` 候选几乎总引入新张力对，而同 `gap_kind`+同 alias 几乎从不引入，我承认你的 guard 可上升为主判据。

我修正自己一点：`DraftAnalysis` 不应是自由语义黑箱，而应由轻量分析器生成：

```ts
type DraftAnalysis = {
  schema_family: string;
  dimension_key: string;
  polarity: "PRO"|"CON"|"MIXED";
}
```

若该分析器跨改写一致率低于 0.85，则三值法整体失效，应回退到 Linus 的结构守门。

---


### [16] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-09T18:32:25.004212*

# 裁判裁定书

---

## 第一部分：白话版结论

---

### E：repair() 的生成策略

**裁定：repair() 应采用"结构化策略为主体、受控松弛为降级"的分层方案，`suggested_dimension` 为软约束而非硬约束。**

让我用一个比喻来解释。

想象你在帮一个学生准备辩论赛。教练（Layer 2）告诉你："这个学生在'经济影响'这个角度的论证太弱了，建议他从'就业数据'方向补强。" 这就是 `GapSpec` 和 `suggested_dimension`。

Ssyram 的方案相当于说：学生必须严格按"就业数据"方向写论点，不许偏离半步。如果写了两轮都和已有论点撞车，就宣布"这个学生在这个角度已经没话可说了"，直接放弃。

Linus 的方案相当于说：让学生自由发挥，教练的建议只是参考，主要靠事后检查论点是否和已有的重复。

我的裁定取中间路线但偏向 Ssyram 的结构化方向，同时吸收 Linus 和康德对"不能把上游建议当神谕"的关键批评：

**具体例子：** 问题是"远程办公是否提高生产力"。Layer 2 报告说缺少"任务耦合度"维度的分析，建议从这个维度补充。

- **第 0 轮（严格绑定）：** repair 必须围绕"任务耦合度"生成草稿，比如"在高耦合任务团队中，远程办公降低迭代速度"。这是 Ssyram 的 E2 策略，此处完全正确。
- **第 1 轮（假设上一轮全被过滤）：** 不是直接终止，也不是自由发挥。而是对约束做**数学松弛**——放宽 scope（从"高耦合"放宽到"中等耦合"），或翻转 polarity（从"降低"变"不影响"），或换 outcome（从"迭代速度"换成"缺陷率"）。这吸收了 Ssyram 的松弛机制。
- **第 2 轮（仍然全被过滤）：** 将 `suggested_dimension` 降级为软约束——允许偏离到相邻维度（比如从"任务耦合度"滑到"沟通频率"），但必须保留与原始 gap 的可追溯关系。这是康德的 `dimensionPolicy` 思路。
- **第 3 轮（再次全被过滤）：** 对该 challenge 标记为 `EXHAUSTED`，但**不终止整个 epoch**——只终止该 challenge 的精化循环。其他 gap 和 challenge 继续处理。

**为什么不采用 Ssyram 的"两轮即终止"？** 因为 Linus 的反驳是致命的：连续被过滤只能证明"当前生成器在当前约束下穷尽了"，不能证明"知识空间穷尽了"。Ssyram 自己也承认 `gap_kind` 分类可能不完备，又引入了 `UNCLASSIFIED_ANOMALY` 逃生口——这恰恰证明穷尽判定不应该这么激进。

**为什么不采用完全自由的 E3？** 因为 Ssyram 的核心论点同样致命：不受约束的 LLM 会"维度漂移"，产出看似新颖但实际上是噪声的草稿。"任务耦合度"的 gap 不应该跑出"组织文化"的草稿。

**什么场景下可能需要修正：** 如果实际运行中发现，绝大多数 `suggested_dimension` 的误报率极低（<10%），那么第 0-1 轮的严格绑定期可以延长，Ssyram 的方案会更优。反过来，如果误报率高（>40%），则应从第 0 轮就采用软约束。这需要 corruption test 数据来校准。

**一句话总结：** repair() 是一个从严格到宽松的三级精化器，教练的建议先当真、撞墙后松绑、松完仍撞墙才放弃——但只放弃这一条路，不放弃整场比赛。

---

### F：is_homologous() 的判定算法

**裁定：is_homologous() 应采用二值输出的"provenance 约束 + 结构近似"判定器，内部可记录置信度，但对外只输出 BLOCK 或 PASS。**

再用一个比喻。

你是一个学术会议的论文查重审稿人。你收到一篇新投稿，需要判断它和已收录的论文是否"本质上说的是同一件事"。

康德说：你应该先看它们是否属于同一个理论流派（schema family），再看它们是否在讨论同一个维度，最后看它们能否形成有意义的正反对立。如果你拿不准，就标记为"待定"（AMBIGUOUS），放进一个特殊通道慢慢审。

Linus 说：你应该看它们的研究对象（scope）、核心结论（outcome）、论证方向（polarity）、和验证方法（verifier）是否结构相似。如果它们来自不同的研究缺口（gap_kind），除非结构上高度一致（>95%），否则默认不是同一篇。

Ssyram 说：上游投稿系统应该强制要求作者用标准模板提交，这样查重就是精确的字段匹配。

**我的裁定偏向 Linus 的方案，但吸收康德关于"跨 schema 表面差异"的警告：**

**具体例子：** 已有草稿 A："在高耦合团队中，远程办公降低迭代吞吐量"。新来草稿 B："在高耦合团队中，远程办公提高缺陷逃逸率"。

- 它们的 scope 相同（高耦合团队 + 远程办公），provenance 可能相同（同一个 gap）
- 但 outcome 不同（吞吐量 vs 缺陷率），verifier 也不同（需要不同的度量指标）
- **裁定：非同源。** 因为它们会消耗不同的验证路径，产生独立的知识增量

再看草稿 C："在缺乏异步协作工具的团队中，远程办公降低交付速度"。与草稿 A 比较：
- scope 高度重合（"高耦合" ≈ "缺乏异步协作工具"是同一现象的不同描述）
- outcome 高度重合（"迭代吞吐量" ≈ "交付速度"）
- polarity 相同，verifier 高度重合
- **裁定：同源。** 即使措辞完全不同，结构签名告诉我们它们会投射到几乎相同的验证骨架

**为什么不采用三值？** 因为 Ssyram 的攻击一针见血：在状态机中，门控只有"放"和"拦"两种物理动作。康德的 `AMBIGUOUS → PASS_WITH_QUARANTINE` 在控制流上就是放行（只是预算减半），那它本质上就是 `NOVEL` 的一个变体，不是独立的第三值。更危险的是，`AMBIGUOUS` 的判定依赖 `canFormAntinomy()`，这个函数需要深度语义分析——这要么调 LLM（成本爆炸），要么用启发式（回到 Linus 的方案）。三值在认识论上优雅，但在工程上它要么退化为二值，要么引入无法承受的复杂度。

**但我吸收康德的一个关键洞见：** Linus 把 `tension_source` 降到几乎无贡献是过度的。"是否来自同一认识框架"确实是判断同源的有用信号——不是决定性的，但也不应该是 0.02 权重的 tie-breaker。我的裁定是：`provenance_family`（来源类型）作为**分流条件**（决定走哪条判定路径和用哪组阈值），而不是作为相似度分数的一个加权项。这正是 Linus 第二轮修正后采用的方案结构。

**为什么不采用 Ssyram 的"强类型 AST 精确匹配"？** 因为 Linus 的致命反击成立：当前 `HypothesisDraft` 接口中没有 AST 字段，Ssyram 是在偷改协议。在不扩展接口的前提下，只能从 `claim_sketch` 和 `verifier_hint` 的文本中提取结构特征。是的，这是"结构代理"而非"真结构"——但 Linus 自己也承认这一点，并提出了可测试的退化条件。

**什么场景下可能需要修正：** 如果实际运行中发现，结构代理的提取失败率 >15%（即无法从 claim_sketch 中稳定提取 scope/outcome/polarity），则必须考虑扩展 `HypothesisDraft` 接口增加结构化字段（即部分接受 Ssyram 的方向，但通过正式的协议修订而非偷渡）。这是一个明确的迭代触发条件。

**一句话总结：** 判断两篇论文是否本质相同，看的是"研究对象+核心结论+验证方法"的骨架是否重合，而不是看它们措辞像不像、来自同一个研究缺口、或属于同一个理论流派——但来源信息决定用哪把尺子量。

---

## 第二部分：可实现性摘要

---

### 1. repair() 的完整函数签名和策略表

#### TypeScript 类型定义

```typescript
// ===== repair() 输入/输出类型 =====

type RefinementStage = "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";

type ChallengeTracker = {
  challenge_id: string;
  current_stage: RefinementStage;
  consecutive_filtered_epochs: number;  // 连续被 100% 过滤的轮数
  attempted_scopes: string[];           // 已尝试过的 scope 变体
  attempted_outcomes: string[];         // 已尝试过的 outcome 变体
  attempted_polarities: (1 | -1 | 0)[]; // 已尝试过的极性
};

type RepairContext = {
  frame: QuestionFrame;
  l2_return: L2Return;
  challenge_trackers: Map<string, ChallengeTracker>;
  // 来自 is_homologous 的拒绝记录，用于避免重复生成
  rejection_history: Array<{
    draft_signature: HomologyFeatures;
    blocked_by: string;
    epoch: number;
  }>;
};

type RepairResult = {
  new_drafts: HypothesisDraft[];
  updated_trackers: Map<string, ChallengeTracker>;
  exhausted_challenges: string[];  // 本轮标记为穷尽的 challenge IDs
};

function repair(ctx: RepairContext): RepairResult;
```

#### 策略表（Python 伪代码）

```python
def repair(ctx: RepairContext) -> RepairResult:
    new_drafts = []
    updated_trackers = {}
    exhausted = []

    # Phase 1: 处理 Gaps（来自 L2 的知识缺口）
    for gap in ctx.l2_return.new_gaps:
        drafts = repair_from_gap(gap, ctx.frame, ctx.rejection_history)
        new_drafts.extend(drafts)

    # Phase 2: 处理 Schema Challenges（来自 L2 的框架挑战）
    for challenge in ctx.l2_return.schema_challenges:
        tracker = ctx.challenge_trackers.get(
            challenge.id, 
            ChallengeTracker(challenge.id, "STRICT", 0, [], [], [])
        )
        
        stage = tracker.current_stage
        if stage == "EXHAUSTED":
            exhausted.append(challenge.id)
            continue

        drafts = repair_from_challenge(challenge, tracker, ctx)
        
        if not drafts:  # 当前 stage 无法产出任何新草稿
            tracker = advance_stage(tracker)
            if tracker.current_stage == "EXHAUSTED":
                exhausted.append(challenge.id)
            else:
                # 用新 stage 重试一次
                drafts = repair_from_challenge(challenge, tracker, ctx)
        
        new_drafts.extend(drafts)
        updated_trackers[challenge.id] = tracker

    return RepairResult(new_drafts, updated_trackers, exhausted)


def repair_from_gap(gap: GapSpec, frame: QuestionFrame, 
                     rejections: list) -> list[HypothesisDraft]:
    """从 GapSpec 生成草稿，策略取决于 gap_kind"""
    
    if gap.kind == "MISSING_DISCRIMINATOR":
        # 生成引入缺失判别维度的草稿
        # scope = gap 指向的分析区域
        # outcome = gap.discriminator 指向的度量
        # polarity = 分别生成正/反两个方向
        return generate_discriminator_drafts(gap, frame, rejections)
    
    elif gap.kind == "MISSING_OBSERVABLE":
        # 生成引入新可观测量的草稿
        return generate_observable_drafts(gap, frame, rejections)
    
    elif gap.kind == "PREMISE_UNDERSPECIFIED":
        # 生成细化前提条件的草稿
        return generate_premise_refinement_drafts(gap, frame, rejections)
    
    else:
        # 未分类异常 → 转化为 SchemaChallenge 处理
        return generate_exploratory_drafts(gap, frame, rejections)


def repair_from_challenge(challenge: SchemaChallengeNotice, 
                           tracker: ChallengeTracker,
                           ctx: RepairContext) -> list[HypothesisDraft]:
    """根据当前精化阶段，从 SchemaChallenge 生成草稿"""
    
    dim = challenge.suggested_dimension  # 可能为 None
    stage = tracker.current_stage
    
    if stage == "STRICT":
        # suggested_dimension 作为硬约束
        # 但生成时排除 rejection_history 中已尝试的 scope/outcome/polarity 组合
        return generate_strict_drafts(challenge, dim, tracker, ctx)
    
    elif stage == "RELAXED":
        # suggested_dimension 作为软约束
        # 允许：放宽 scope、翻转 polarity、替换 outcome
        # 禁止：完全脱离原始 gap 的语义区域
        return generate_relaxed_drafts(challenge, dim, tracker, ctx)
    
    elif stage == "ADJACENT":
        # suggested_dimension 仅作为锚点
        # 允许滑移到语义相邻的维度
        # 但必须保留与原始 challenge 的 provenance 链接
        return generate_adjacent_drafts(challenge, dim, tracker, ctx)
    
    return []


def advance_stage(tracker: ChallengeTracker) -> ChallengeTracker:
    """状态推进规则"""
    transitions = {
        "STRICT": "RELAXED",    # 严格绑定 → 约束松弛
        "RELAXED": "ADJACENT",  # 约束松弛 → 邻域探索
        "ADJACENT": "EXHAUSTED" # 邻域探索 → 穷尽
    }
    tracker.current_stage = transitions[tracker.current_stage]
    tracker.consecutive_filtered_epochs = 0  # 重置计数器
    return tracker
```

**策略推进触发条件：** 当某个 challenge 的 `consecutive_filtered_epochs >= 1`（即连续 1 轮该 challenge 产出的草稿 100% 被 `is_homologous` 过滤），推进到下一个 stage。注意是**该 challenge** 的草稿全被过滤，不是整个 epoch 的所有草稿全被过滤。

---

### 2. is_homologous() 的完整判定算法

#### TypeScript 类型

```typescript
type HomologyFeatures = {
  provenance_family: string;        // gap_kind 或 challenge 类型
  dimension_key: string | null;     // 归一化后的维度标识
  scope_tokens: string[];           // 从 scope_ref + claim_sketch 提取的归一化 scope 标记
  outcome_anchor: string;           // 核心结果变量（归一化）
  polarity: 1 | -1 | 0;            // 方向：正/负/中性
  verifier_tokens: string[];        // 从 verifier_hint 提取的验证标记
};

type HomologyResult = {
  is_homologous: boolean;
  blocked_by: string | null;        // 匹配到的已有草稿 ID
  confidence: number;               // 0-1，内部诊断用，不影响判定
  reason: string[];                 // 人可读的判定依据
};

function is_homologous(
  candidate: HypothesisDraft,
  existing_pool: HypothesisDraft[],
  gap_index: Record<string, GapSpec>
): HomologyResult;
```

#### 完整判定算法（Python 伪代码）

```python
def is_homologous(candidate, existing_pool, gap_index) -> HomologyResult:
    """
    二值判定：candidate 是否与 existing_pool 中某个草稿同源。
    
    核心原则：
    - provenance_family 决定判定路径和阈值（分流条件）
    - 结构特征（scope/outcome/polarity/verifier）决定最终判定
    - tension_source.kind 仅用于解释，不参与分数计算
    
    复杂度：O(|existing_pool| * max(|scope_tokens|, |verifier_tokens|))
    对于典型 pool 大小 (<100) 和 token 集 (<50)，单次判定 <1ms
    """
    
    a = extract_features(candidate, gap_index)
    
    for e in existing_pool:
        b = extract_features(e, gap_index)
        result = compare_pair(a, b, candidate, e)
        if result.is_homologous:
            return result
    
    return HomologyResult(
        is_homologous=False,
        blocked_by=None,
        confidence=0.0,
        reason=["no structural homology hit in pool"]
    )


def extract_features(draft: HypothesisDraft, gap_index) -> HomologyFeatures:
    """
    从 HypothesisDraft 的现有字段提取结构特征。
    
    关键设计决策：
    - 这是"预编译结构代理"，不是精确 AST
    - 提取失败时返回空/默认值，由 compare_pair 中的阈值处理
    - 不依赖任何接口外的字段
    """
    
    # 1. provenance_family: 从 provenance 或 tension_source 抽取
    prov_family = classify_provenance(draft.provenance, gap_index)
    
    # 2. dimension_key: 从关联的 gap/challenge 中提取并归一化
    dim_key = extract_dimension_key(draft, gap_index)
    
    # 3. scope_tokens: 从 scope_ref 和 claim_sketch 的条件部分提取
    scope_tokens = extract_scope_tokens(draft.scope_ref, draft.claim_sketch)
    
    # 4. outcome_anchor: 从 claim_sketch 的结果部分提取核心变量
    outcome = extract_outcome(draft.claim_sketch)
    
    # 5. polarity: 从 claim_sketch 判断方向
    polarity = extract_polarity(draft.claim_sketch)
    
    # 6. verifier_tokens: 从 verifier_hint 提取
    verifier_tokens = normalize_and_tokenize(draft.verifier_hint)
    
    return HomologyFeatures(prov_family, dim_key, scope_tokens, 
                             outcome, polarity, verifier_tokens)


def compare_pair(a: HomologyFeatures, b: HomologyFeatures,
                  draft_a, draft_b) -> HomologyResult:
    """
    核心判定逻辑：基于 provenance 分流，结构特征决定。
    
    路径 1（同源家族）：阈值较松，因为来自同一缺口的草稿更可能是表面改写
    路径 2（异源家族）：阈值极严，除非结构几乎完全一致否则不判同源
    """
    
    same_family = (a.provenance_family == b.provenance_family)
    same_dimension = (a.dimension_key is not None and 
                       a.dimension_key == b.dimension_key)
    
    scope_sim = jaccard(a.scope_tokens, b.scope_tokens)
    outcome_match = normalized_match(a.outcome_anchor, b.outcome_anchor)
    polarity_match = (a.polarity == b.polarity)
    verifier_sim = jaccard(a.verifier_tokens, b.verifier_tokens)
    
    reasons = []
    
    # ===== 路径 1：同源家族 =====
    if same_family:
        if same_dimension:
            # 同家族 + 同维度：最可能是同源改写
            # 阈值：scope≥0.80, outcome匹配, polarity相同, verifier≥0.75
            if (scope_sim >= 0.80 and outcome_match and 
                polarity_match and verifier_sim >= 0.75):
                reasons.append(f"same-family({a.provenance_family}) "
                             f"same-dim({a.dimension_key}) "
                             f"scope={scope_sim:.2f} ver={verifier_sim:.2f}")
                return HomologyResult(True, draft_b.id, 
                                       min(scope_sim, verifier_sim), reasons)
        else:
            # 同家族 + 不同维度：仍可能同源，但阈值提高
            if (scope_sim >= 0.90 and outcome_match and 
                polarity_match and verifier_sim >= 0.85):
                reasons.append(f"same-family cross-dim "
                             f"scope={scope_sim:.2f} ver={verifier_sim:.2f}")
                return HomologyResult(True, draft_b.id,
                                       min(scope_sim, verifier_sim) * 0.9, reasons)
    
    # ===== 路径 2：异源家族 =====
    else:
        # 不同家族：仅在结构极高重合时才判同源
        # 这是对康德"跨 schema 表面差异"警告的回应
        if (scope_sim >= 0.95 and outcome_match and 
            polarity_match and verifier_sim >= 0.90):
            reasons.append(f"cross-family structural convergence "
                         f"scope={scope_sim:.2f} ver={verifier_sim:.2f}")
            return HomologyResult(True, draft_b.id,
                                   min(scope_sim, verifier_sim) * 0.8, reasons)
    
    # ===== 未命中 =====
    return HomologyResult(False, None, 0.0, 
                           [f"below threshold: scope={scope_sim:.2f} "
                            f"out={outcome_match} pol={polarity_match} "
                            f"ver={verifier_sim:.2f}"])
```

#### 辅助函数的归一化策略

```python
def extract_scope_tokens(scope_ref: list[str], claim_sketch: str) -> list[str]:
    """
    从 scope_ref（结构化）和 claim_sketch（自由文本的条件部分）提取归一化标记。
    
    策略：
    1. scope_ref 直接作为 token 源（已经半结构化）
    2. claim_sketch 中提取条件从句的名词短语
    3. 合并、去重、排序
    4. 同义词归一化（维护一个小型同义词表，可随运行积累）
    
    退化行为：如果提取失败（如 claim_sketch 无法解析），
    仅使用 scope_ref，并在 reason 中标记 "scope_extraction_partial"
    """
    tokens = list(scope_ref)  # scope_ref 本身是 string[]
    
    # 从 claim_sketch 的条件部分提取补充 tokens
    condition_part = extract_condition_clause(claim_sketch)
    if condition_part:
        noun_phrases = extract_noun_phrases(condition_part)
        tokens.extend(noun_phrases)
    
    # 归一化
    tokens = [normalize_synonym(t) for t in tokens]
    return sorted(set(tokens))


def extract_outcome(claim_sketch: str) -> str:
    """
    从 claim_sketch 中提取核心结果变量。
    
    策略：提取主句的宾语/表语核心名词
    例："远程办公降低迭代吞吐量" → "迭代吞吐量"
    例："remote work reduces defect escape rate" → "defect_escape_rate"
    
    退化行为：如果无法提取，返回 claim_sketch 的哈希摘要前 8 位。
    此时 outcome_match 会对大多数比较返回 False，
    相当于"提取失败 → 不判同源"，这是安全的保守方向。
    """
    result_clause = extract_result_clause(claim_sketch)
    if result_clause:
        return normalize_synonym(extract_core_noun(result_clause))
    return f"__hash_{hash(claim_sketch)[:8]}"


def normalized_match(outcome_a: str, outcome_b: str) -> bool:
    """
    判断两个 outcome anchor 是否指向同一结果变量。
    精确匹配 + 同义词表匹配。
    不使用 embedding 相似度（避免过度模糊）。
    """
    return outcome_a == outcome_b or are_synonyms(outcome_a, outcome_b)
```

#### 复杂度分析

| 操作 | 复杂度 | 说明 |
|------|--------|------|
| `extract_features` | O(L) | L = claim_sketch 长度，单次文本解析 |
| `jaccard(A, B)` | O(\|A\| + \|B\|) | 基于排序集合的交/并计算 |
| `compare_pair` | O(\|scope\| + \|verifier\|) | 两次 Jaccard + 常数项比较 |
| `is_homologous` 总体 | O(P × (L + S + V)) | P = pool 大小，S/V = scope/verifier token 集大小 |
| 典型场景 | P<100, L<500, S<30, V<20 | **<1ms 单次调用** |

---

### 3. 数据流类型定义：repair → is_homologous → ClarityCompiler

```typescript
// ===== 完整数据流类型定义 =====

// [Stage 0] L2Return 信号（来自 Layer 2）
interface L2Return {
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  ranking_delta: { changed: boolean; details?: string };
  epoch_id: number;
}

interface GapSpec {
  gap_id: string;
  kind: "MISSING_DISCRIMINATOR" | "MISSING_OBSERVABLE" | "PREMISE_UNDERSPECIFIED" | "UNCLASSIFIED";
  discriminator?: string;
  evidence_summary: string;
}

interface SchemaChallengeNotice {
  challenge_id: string;
  trigger: "REPLAY_REGRESSION" | "COVERAGE_GAP" | "ANOMALY";
  suggested_dimension?: string;
  is_homologous: boolean;
  description: string;
}

// [Stage 1] repair() 的输出
interface HypothesisDraft {
  draft_id: string;
  scope_ref: string[];
  tension_source: { kind: string; detail: string };
  claim_sketch: string;
  verifier_hint: string;
  provenance: {
    source_gap_id?: string;
    source_challenge_id?: string;
    repair_stage: RefinementStage;
    epoch: number;
  };
}

// [Stage 2] is_homologous() 的输出
interface FilteredDraftSet {
  passed: Array<{
    draft: HypothesisDraft;
    homology_check: HomologyResult;  // is_homologous=false 的那些
  }>;
  blocked: Array<{
    draft: HypothesisDraft;
    homology_check: HomologyResult;  // is_homologous=true 的那些
  }>;
  filter_stats: {
    total_candidates: number;
    passed_count: number;
    blocked_count: number;
    blocked_ratio: number;  // 用于触发 repair 降级
  };
}

// [Stage 3] ClarityCompiler 的输入（仅接收 passed drafts）
interface CCInput {
  drafts: HypothesisDraft[];    // FilteredDraftSet.passed 中的 drafts
  frame: QuestionFrame;
  existing_claims: TestableClaim[];  // 已有的可验证命题
}

// [Stage 4] ClarityCompiler 的输出
interface CCOutput {
  new_claims: TestableClaim[];
  compilation_failures: Array<{
    draft_id: string;
    failure_reason: string;
  }>;
}

interface TestableClaim {
  claim_id: string;
  source_draft_id: string;
  falsifiable_statement: string;
  required_evidence_types: string[];
  verification_protocol: string;
  scope_boundary: string[];
}

// [Stage 5] 进入下一个 Epoch 的完整状态更新
interface EpochTransition {
  new_claims: TestableClaim[];           // 进入 D2 派发
  updated_trackers: Map<string, ChallengeTracker>;  // 更新精化状态
  exhausted_challenges: string[];         // 标记为穷尽的 challenge
  rejection_additions: Array<{            // 新增拒绝记录
    draft_signature: HomologyFeatures;
    blocked_by: string;
    epoch: number;
  }>;
  breadth_overrun: boolean;               // 是否触发广度过热刹车
}
```

---

### 4. 完整运行 Trace 示例

**问题：** "远程办公是否提高软件团队生产力？"

**起始状态：** Epoch 3，已有 3 个 TestableClaim，Layer 2 刚返回 L2Return。

```
===== EPOCH 3 → EPOCH 4 =====

[STEP 0] L2Return 信号到达 Layer 1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L2Return = {
  epoch_id: 3,
  new_gaps: [
    {
      gap_id: "gap-007",
      kind: "MISSING_DISCRIMINATOR",
      discriminator: "task_coupling_degree",
      evidence_summary: "现有假设未区分高/低耦合任务团队"
    }
  ],
  schema_challenges: [
    {
      challenge_id: "sc-003",
      trigger: "COVERAGE_GAP",
      suggested_dimension: "communication_frequency",
      is_homologous: false,
      description: "缺少沟通频率维度的分析"
    }
  ],
  ranking_delta: { changed: false }
}

已有 challenge_trackers:
  sc-003: { stage: "STRICT", consecutive_filtered: 0, ... }

已有 existing_pool (草稿池):
  [draft-A] "在大型团队中，远程办公降低会议效率"
            scope=["大型团队"], outcome="会议效率", polarity=-1
            provenance_family="MISSING_OBSERVABLE"
  [draft-B] "在创业公司中，远程办公提高个人产出"
            scope=["创业公司"], outcome="个人产出", polarity=+1
            provenance_family="PREMISE_UNDERSPECIFIED"
  [draft-C] "在跨时区团队中，远程办公增加沟通延迟"
            scope=["跨时区团队"], outcome="沟通延迟", polarity=+1
            provenance_family="MISSING_DISCRIMINATOR"


[STEP 1] repair(ctx) 执行
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 1: 处理 gap-007 (MISSING_DISCRIMINATOR, discriminator="task_coupling_degree")
  → 生成 draft-D: "在高任务耦合团队中，远程办公降低迭代吞吐量"
      scope_ref: ["高任务耦合团队"]
      claim_sketch: "在高任务耦合团队中，远程办公降低迭代吞吐量"
      verifier_hint: "比较高/低耦合团队的迭代周期时长"
      provenance: { source_gap_id: "gap-007", repair_stage: "STRICT" }
  → 生成 draft-E: "在低任务耦合团队中，远程办公不影响迭代吞吐量"
      scope_ref: ["低任务耦合团队"]
      claim_sketch: "在低任务耦合团队中，远程办公不影响迭代吞吐量"
      verifier_hint: "比较高/低耦合团队的迭代周期时长"
      provenance: { source_gap_id: "gap-007", repair_stage: "STRICT" }

Phase 2: 处理 sc-003 (COVERAGE_GAP, suggested_dimension="communication_frequency")
  tracker.stage = "STRICT" → suggested_dimension 作为硬约束
  → 生成 draft-F: "在高沟通频率团队中，远程办公降低沟通质量"
      scope_ref: ["高沟通频率团队"]
      claim_sketch: "在高沟通频率需求的团队中，远程办公降低同步沟通质量"
      verifier_hint: "对比远程/办公室环境下的沟通满意度与决策速度"
      provenance: { source_challenge_id: "sc-003", repair_stage: "STRICT" }

repair() 输出: [draft-D, draft-E, draft-F]
updated_trackers: { sc-003: { stage: "STRICT", consecutive_filtered: 0 } }


[STEP 2] is_homologous() 过滤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

检查 draft-D vs existing_pool:
  vs draft-A: provenance_family 不同 (MISSING_DISCRIMINATOR vs MISSING_OBSERVABLE)
    → 路径 2（异源家族）
    scope_sim = jaccard(["高任务耦合团队"], ["大型团队"]) = 0.20
    → 远低于 0.95 阈值 → PASS
  vs draft-B: provenance_family 不同
    scope_sim = jaccard(["高任务耦合团队"], ["创业公司"]) = 0.0
    → PASS
  vs draft-C: provenance_family 相同 (MISSING_DISCRIMINATOR)
    dimension_key: "task_coupling_degree" vs null (C 没有明确 dimension)
    → 不同维度，走同家族+不同维度路径
    scope_sim = jaccard(["高任务耦合团队"], ["跨时区团队"]) = 0.25
    → 远低于 0.90 阈值 → PASS
  ✅ draft-D: NOT HOMOLOGOUS → PASS

检查 draft-E vs existing_pool:
  vs draft-A: 异源，scope_sim 低 → PASS
  vs draft-B: 异源，scope_sim 低 → PASS
  vs draft-C: 同源家族，不同维度，scope_sim 低 → PASS
  vs draft-D: 同源家族 (MISSING_DISCRIMINATOR), 同维度 (task_coupling_degree)
    scope_sim = jaccard(["低任务耦合团队"], ["高任务耦合团队"]) = 0.60
    → 低于 0.80 阈值（"高"vs"低"是不同 scope）→ PASS
    [注：这正是 Linus 场景 A/B 例子的变体，scope 不同应放行]
  ✅ draft-E: NOT HOMOLOGOUS → PASS

检查 draft-F vs existing_pool:
  vs draft-A: 异源，scope_sim 低 → PASS
  vs draft-B: 异源，scope_sim 低 → PASS
  vs draft-C: 异源 (COVERAGE_GAP vs MISSING_DISCRIMINATOR)
    scope_sim = jaccard(["高沟通频率团队"], ["跨时区团队"]) = 0.15
    → 远低于 0.95 → PASS
    [注：虽然"沟通频率"和"跨时区沟通延迟"语义相关，但结构特征分散，不构成同源]
  vs draft-D: 异源，scope_sim 低 → PASS
  vs draft-E: 异源，scope_sim 低 → PASS
  ✅ draft-F: NOT HOMOLOGOUS → PASS

FilteredDraftSet = {
  passed: [draft-D, draft-E, draft-F],
  blocked: [],
  filter_stats: { total: 3, passed: 3, blocked: 0, blocked_ratio: 0.0 }
}


[STEP 3] ClarityCompiler 编译
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CC 接收 [draft-D, draft-E, draft-F]:

draft-D → TestableClaim:
  {
    claim_id: "tc-004",
    source_draft_id: "draft-D",
    falsifiable_statement: "在任务耦合度高于阈值 T 的软件团队中，
                           切换到远程办公后迭代周期时长增加 ≥15%",
    required_evidence_types: ["iteration_cycle_data", "coupling_metric"],
    verification_protocol: "准实验：匹配高耦合团队的远程前后迭代数据",
    scope_boundary: ["高任务耦合团队", "软件开发", "迭代交付"]
  }

draft-E → TestableClaim:
  {
    claim_id: "tc-005",
    source_draft_id: "draft-E",
    falsifiable_statement: "在任务耦合度低于阈值 T 的软件团队中，
                           远程办公对迭代周期时长的影响在 ±5% 以内",
    required_evidence_types: ["iteration_cycle_data", "coupling_metric"],
    verification_protocol: "等价性检验：比较低耦合团队远程前后迭代数据",
    scope_boundary: ["低任务耦合团队", "软件开发", "迭代交付"]
  }

draft-F → TestableClaim:
  {
    claim_id: "tc-006",
    source_draft_id: "draft-F",
    falsifiable_statement: "在日均同步沟通需求 >2 小时的团队中，
                           远程办公使沟通满意度评分下降 ≥20%",
    required_evidence_types: ["communication_satisfaction_survey", 
                               "sync_communication_hours"],
    verification_protocol: "前后对比调查 + 沟通日志分析",
    scope_boundary: ["高沟通频率团队", "远程办公", "沟通质量"]
  }

CCOutput = {
  new_claims: [tc-004, tc-005, tc-006],
  compilation_failures: []
}


[STEP 4] EpochTransition → Epoch 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EpochTransition = {
  new_claims: [tc-004, tc-005, tc-006],  // 3 个新命题进入 D2 派发
  updated_trackers: {
    sc-003: { stage: "STRICT", consecutive_filtered: 0 }
    // 未被过滤，保持 STRICT，计数器不变
  },
  exhausted_challenges: [],
  rejection_additions: [],  // 本轮无阻断
  breadth_overrun: false    // 3 个新命题，远未触及广度过热
}

existing_pool 更新为:
  [draft-A, draft-B, draft-C, draft-D, draft-E, draft-F]

Epoch 4 启动：
  tc-004, tc-005, tc-006 进入 Layer 2 的 DepthProbe
  Layer 2 将尝试验证这些命题，并返回新的 L2Return
```

**降级场景示例（假设 Epoch 5 中 sc-003 被过滤）：**

```
[EPOCH 5 补充 trace - 降级场景]

假设 Epoch 4 的 L2Return 中 sc-003 再次出现（Layer 2 认为沟通频率维度仍需补充），
repair 在 STRICT 阶段产出 draft-G:
  "在高沟通频率团队中，远程办公增加异步沟通比例"
  scope=["高沟通频率团队"], outcome="异步沟通比例"

is_homologous 检查 draft-G vs draft-F:
  同源家族 (COVERAGE_GAP), 同维度 (communication_frequency)
  scope_sim = jaccard(["高沟通频率团队"], ["高沟通频率团队"]) = 1.00
  outcome: "异步沟通比例" vs "同步沟通质量

---
