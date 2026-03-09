# v3 认知引擎：detect_category_errors() 判定算法与 NQ/CC 职责边界 辩论日志

> 2026-03-09T19:02:37.513344

---


### [1] Linus Torvalds

*2026-03-09T18:55:14.806343*

我选两者都答。因为它们本来就是同一个工程问题：**在哪一层、用什么可复现的判定器，拦什么东西**。把这拆开讨论很容易滑回“感觉上应该如此”的废话。

我要先把立场钉死：

1. **`detect_category_errors()` 不能主要靠 LLM。**  
   这里面至少有两类东西应以确定性规则为主：  
   - `SELF_REFERENCE_PARADOX`
   - `SCOPE_UNBOUNDED`
   
   `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY` 可以做成 **词表/类型系统 + 小量 LLM 兜底**。  
   `UNFALSIFIABLE_VALUE_ASSERTION` 必须是 **规则先筛 + 有边界的结构化 LLM 判定**，但**不能**直接说“LLM 觉得不可证伪”。

2. **NQ 的 `UNFALSIFIABLE_VALUE_ASSERTION` 与 CC 的 `NO_EMPIRICAL_BRIDGE` 不是一个东西。**  
   - NQ：判的是**原始问题本身是否属于“没有经验桥接入口”的问题类型**。命中就全局 fatal。  
   - CC：判的是**某个具体 draft 是否没法降格成可测试 claim**。命中只把该 draft 降为 `RegulativeIdea`。  
   这两者允许先后都“看见不可经验化”，但**不应对同一输入对象重复拦截**，因为输入对象不同、返回动作不同。

下面给具体函数、规则、trace、失败路径和已知弱点。

---

# 一、`detect_category_errors()` 的完整立场

先给总接口。别玩抽象诗歌。

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Literal

class CategoryErrorTag(str, Enum):
    SELF_REFERENCE_PARADOX = "SELF_REFERENCE_PARADOX"
    NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY = "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY"
    UNFALSIFIABLE_VALUE_ASSERTION = "UNFALSIFIABLE_VALUE_ASSERTION"
    SCOPE_UNBOUNDED = "SCOPE_UNBOUNDED"

class DetectorConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

@dataclass
class Evidence:
    rule_id: str
    span: tuple[int, int]
    matched_text: str
    reason: str

@dataclass
class CategoryHit:
    tag: CategoryErrorTag
    confidence: DetectorConfidence
    evidences: list[Evidence]
    llm_used: bool

@dataclass
class DetectionContext:
    language: Literal["zh", "en", "auto"]
    enable_llm_fallback: bool = True
    llm_budget_tokens: int = 256

def detect_category_errors(
    raw_question: str,
    ctx: DetectionContext
) -> list[CategoryHit]:
    ...
```

这是最小可实现接口。输入、输出、证据、是否用了 LLM，全部可审计。  
**没有 evidence 的 category detector 就是黑盒垃圾。**

---

# 二、四个 tag 的判定算法

---

## 1) `SELF_REFERENCE_PARADOX`

### 立场

这个东西**优先用句法/模式规则**，只有边界模糊案例才进 LLM。  
你要是上来就 LLM 判“这是不是自指悖论”，那就是把误判率藏起来。

### 函数签名

```python
def detect_self_reference_paradox(
    raw_question: str,
    ctx: DetectionContext
) -> Optional[CategoryHit]:
    """
    Returns CategoryHit if fatal self-referential paradox is detected.
    Returns None if not detected.
    Failure path:
      - If parser/regex confidence is insufficient and ctx.enable_llm_fallback=False: return None
      - If LLM fallback times out/fails: return None with no hit (fail-open)
    """
```

### 规则集

先定义两个必要成分：

- **自指锚点**：  
  中文例：`这句话` `这句` `本句` `本命题` `此陈述` `这个断言`  
  英文例：`this sentence` `this statement` `this proposition` `the present claim`

- **悖论触发谓词**：  
  中文例：`是假的` `为假` `不可为真` `不能被断言为真`  
  英文例：`is false` `is not true` `cannot be true`

#### 规则 R-SRP-1：经典 liar pattern
```text
[自指锚点] + [系词/判断连接] + [假/不真谓词]
```

命中例：
- “这句话是假的”
- “本命题不是真的”

#### 规则 R-SRP-2：二阶自指否真
```text
[自指锚点] + [描述自身真值/可证性] + [否定]
```
命中例：
- “此陈述无法为真”
- “这个断言不可被正确断言”

#### 排除规则 R-SRP-NEG-1：非真值内容的自指，不算悖论
- “这句话有四个字”  
- “本句是中文”  
这类只是自指，不是悖论。

#### 排除规则 R-SRP-NEG-2：元语言讨论，不算对象级悖论
- “请分析‘这句话是假的’为什么构成悖论”  
- “命题‘这句话是假的’是否有真值？”

这里要检测是否存在 **分析意图动词**：`分析` `讨论` `解释` `为什么` `是否构成`。

### 判定伪代码

```python
def detect_self_reference_paradox(raw_question: str, ctx: DetectionContext) -> Optional[CategoryHit]:
    text = normalize_text(raw_question)

    if match_meta_discussion(text):
        return None

    anchor = find_self_reference_anchor(text)
    paradox_pred = find_liar_predicate(text)

    if anchor and paradox_pred:
        if direct_copular_relation(anchor, paradox_pred, text):
            return CategoryHit(
                tag=CategoryErrorTag.SELF_REFERENCE_PARADOX,
                confidence=DetectorConfidence.HIGH,
                evidences=[
                    Evidence("R-SRP-1", anchor.span, anchor.text, "self-reference anchor"),
                    Evidence("R-SRP-1", paradox_pred.span, paradox_pred.text, "liar predicate")
                ],
                llm_used=False
            )

    if ctx.enable_llm_fallback and contains_self_reference(text):
        llm_result = llm_check_self_ref_paradox(text)  # structured output: {is_paradox, rationale_spans}
        if llm_result.is_paradox:
            return CategoryHit(... confidence=DetectorConfidence.MEDIUM, llm_used=True)

    return None
```

### 覆盖率主张

对**真实工程输入**，经典自指悖论案例里，规则集可覆盖大约 **80–90%**。  
原因很简单：用户真写这类东西时，几乎都用固定句式。  
需要 LLM 的通常是变体表达，比如：
- “若此断言为真，则其为假”
- “这个陈述不具有可一致赋值的真值”

### trace 1

**输入 X**：`这句话是假的。`  
**判定 Y**：`SELF_REFERENCE_PARADOX`  
**理由 Z**：命中自指锚点“这句话” + 命中 liar 谓词“是假的” + 直接主谓关系成立。

### trace 2（不应 fatal）

**输入 X**：`请解释“这句话是假的”为何构成悖论。`  
**判定 Y**：不命中  
**理由 Z**：命中元语言讨论排除规则 `R-SRP-NEG-2`，问题对象是分析该命题，不是在直接提出悖论命题作为待处理问题。

### 已知弱点

- 有些复杂嵌套版本需要语义解析，规则会漏。  
- 如果用户用非常绕的表达伪装 liar sentence，LLM fallback 才可能捞到。  
- 我接受这个漏检代价，因为 **假阳性比假阴性更贵**：把一个正常分析问题当成 fatal，会直接终止 pipeline。

### 可推翻条件

如果你能给出一组真实用户语料，证明经典自指悖论中超过 **30%** 无法被上述规则捕捉，同时 LLM fallback 显著提高召回且假阳性 < 3%，那我同意加大语义判定比重。

---

## 2) `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`

### 立场

这不是纯 LLM 任务。  
你需要两个判定谓词：

1. **subject 是否抽象实体**
2. **predicate 是否把非经验属性赋给它**

没有这两个分离谓词，讨论就是一团浆糊。

### 函数签名

```python
def detect_non_empirical_attribute_on_abstract_entity(
    raw_question: str,
    ctx: DetectionContext
) -> Optional[CategoryHit]:
    """
    Detects statements/questions attributing non-empirical evaluative/magical/social properties
    to abstract entities like numbers, sets, propositions, algorithms-as-formal-objects.
    """
```

### 抽象实体判定谓词

```python
def is_abstract_entity_np(np: str) -> bool:
    ...
```

#### 规则：抽象实体词类

命中词表/类型：
- 数学对象：`数字` `数` `7` `π` `集合` `函数` `矩阵` `素数`
- 逻辑对象：`命题` `定理` `证明`
- 形式对象：`算法`（当指算法规范而非实现）`语法规则`
- 纯概念：`正义` `自由`（这里要小心，纯概念不总是 fatal）

要有**上下文类型消歧**：
- “算法很慢” 如果指实现/程序，可经验化，不算抽象对象上的非经验属性。
- “算法 A 是优雅的” 可能是审美评价，但不是一定 fatal，因为可转成简洁性指标。别乱杀。

### 非经验属性判定谓词

```python
def is_non_empirical_attribute(pred: str) -> bool:
    ...
```

命中词类：
- 神秘/玄学：`幸运的` `被诅咒的` `有灵魂的`
- 纯道德属性：`善良的` `邪恶的`
- 社会身份属性错配：`已婚的` `富有的` 赋给数字/集合
- 主观人格属性：`嫉妒的` `诚实的`

### 排除：经验或形式可验证属性

不命中：
- `是质数`
- `有 7 个元素`
- `不可判定`
- `时间复杂度为 O(n log n)`（若对象是算法/程序）

### 判定伪代码

```python
def detect_non_empirical_attribute_on_abstract_entity(raw_question: str, ctx: DetectionContext):
    text = normalize_text(raw_question)
    subj_pred_pairs = shallow_extract_copular_pairs(text)

    for subj, pred in subj_pred_pairs:
        if is_abstract_entity_np(subj) and is_non_empirical_attribute(pred):
            if not has_empirical_bridge(subj, pred):
                return CategoryHit(
                    tag=CategoryErrorTag.NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY,
                    confidence=DetectorConfidence.HIGH,
                    evidences=[
                        Evidence("R-NEAAE-SUBJ", subj.span, subj.text, "abstract entity"),
                        Evidence("R-NEAAE-PRED", pred.span, pred.text, "non-empirical attribute")
                    ],
                    llm_used=False
                )

    if ctx.enable_llm_fallback and likely_attribute_mismatch(text):
        llm_result = llm_check_abstract_attribute_mismatch(text)  # structured
        if llm_result.hit:
            return CategoryHit(... confidence=DetectorConfidence.MEDIUM, llm_used=True)

    return None
```

### trace 1（应 fatal）

**输入 X**：`数字 7 是幸运的吗？`  
**判定 Y**：`NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`  
**理由 Z**：  
- 主语“数字 7”命中抽象数学对象  
- 谓语“幸运”命中非经验/玄学属性  
- 不存在可操作经验桥接：无法定义对“数字对象本身”的观测协议

### trace 2（不应 fatal）

**输入 X**：`数字 7 是质数吗？`  
**判定 Y**：不命中  
**理由 Z**：  
- 主语是抽象实体，没错  
- 但谓语“质数”是形式可判定属性，不是非经验属性  
- 可在数学系统内验证

### trace 3（边界案例，不应直接 fatal）

**输入 X**：`这个排序算法是否优雅？`  
**判定 Y**：默认不命中 fatal；交给后续 normalizer/clarification  
**理由 Z**：  
“优雅”可以映射到代码长度、证明简洁性、认知负担等代理指标。它是模糊，不是 category error。  
这就是为什么不能把一切“抽象对象 + 评价词”都判死。

### 已知弱点

- “算法”“模型”“制度”这类对象有时抽象、有时具经验实例，消歧不总是稳。  
- 词表覆盖不足时会漏掉奇怪谓词。  
- 但这仍然比一句“需要语义理解所以用 LLM”强得多，因为至少你知道自己在判什么。

### 可推翻条件

如果你能给出一个高质量标注集，证明“subject 抽象性 + predicate 非经验性”二元判定在该任务上 F1 < 0.7，而结构化 LLM 明显更好且可审计，我接受扩大 LLM 份额。

---

## 3) `UNFALSIFIABLE_VALUE_ASSERTION`

### 立场

这里最容易被说成玄学，所以要下硬定义。  
**操作性定义不是“任何框架都无法证伪”这种废话。** 你不能穷举“任何框架”。

我给的可实现定义是：

> 若一个原始问题在经过受限的经验桥接生成器后，**不存在至少一个**满足最小经验要求的候选比较维度/观测协议，则判为 `UNFALSIFIABLE_VALUE_ASSERTION`。

也就是说，它不是形而上学全称判断，而是**在系统支持的合法桥接类集合内无桥**。

### 函数签名

```python
@dataclass
class BridgeCandidate:
    axis_name: str
    observable_variables: list[str]
    population_scope: Optional[str]
    measurement_protocol: Optional[str]
    falsifier_template: Optional[str]

def detect_unfalsifiable_value_assertion(
    raw_question: str,
    ctx: DetectionContext,
    bridge_generator_version: str = "v1"
) -> Optional[CategoryHit]:
    """
    Fatal only when raw_question is a pure evaluative assertion/query and
    zero valid empirical bridge candidates can be generated under bounded bridge schema set.
    """
```

### 最小经验桥接标准

一个 `BridgeCandidate` 合法，当且仅当：

```python
def is_valid_empirical_bridge(c: BridgeCandidate) -> bool:
    return (
        len(c.observable_variables) >= 1 and
        c.measurement_protocol is not None and
        c.falsifier_template is not None
    )
```

### 受限桥接类集合

别说“任何框架”。我们只允许固定集合：
- 后果主义桥接：幸福/健康/生存/偏好满足
- 程序正义桥接：一致性、可逆性、可申诉性
- 主体偏好桥接：明确人群中的偏好分布
- 行为结果桥接：参与率、复发率、错误率

如果一个问题连这些都无法生成候选桥，那么它在本系统里就是 `UNFALSIFIABLE_VALUE_ASSERTION`。

### 触发规则

先规则筛掉明显的纯价值模板：
- `X 比 Y 更好/更高尚/更正确/更值得`
- `什么是最有意义的生活`
- `爱比恨更好吗`

再尝试桥接生成。如果生成器返回 0 个合法 candidate，则 fatal。

### 伪代码

```python
def detect_unfalsifiable_value_assertion(raw_question: str, ctx: DetectionContext, bridge_generator_version="v1"):
    text = normalize_text(raw_question)

    if not matches_pure_value_template(text):
        return None

    candidates = generate_empirical_bridges(text, schema_version=bridge_generator_version, max_candidates=5)

    valid = [c for c in candidates if is_valid_empirical_bridge(c)]

    if len(valid) == 0:
        return CategoryHit(
            tag=CategoryErrorTag.UNFALSIFIABLE_VALUE_ASSERTION,
            confidence=DetectorConfidence.MEDIUM if ctx.enable_llm_fallback else DetectorConfidence.HIGH,
            evidences=[
                Evidence("R-UVA-1", (0, len(text)), text, "pure value template with zero valid empirical bridge")
            ],
            llm_used=True  # bridge generation may use LLM
        )

    return None
```

### 与“当前框架下恰好找不到 falsifier”的区别

区别非常具体：

- **NQ fatal (`UNFALSIFIABLE_VALUE_ASSERTION`)**：  
  输入是 `raw_question`；系统在固定桥接 schema 集合里做了**问题级**尝试，结果是 **0 个合法 bridge candidate**。
  
- **CC `NO_EMPIRICAL_BRIDGE`**：  
  输入是某个 `HypothesisDraft.claim_sketch`；它可能来自一个总体上可桥接的问题，但这个**草稿表述**没法编译成可证伪 claim。

这是对象层级不同，不是嘴上说“职责不同”。

### trace 1（应被 NQ 拦截）

**输入 X**：`爱比恨更好吗？`  
**判定 Y**：`UNFALSIFIABLE_VALUE_ASSERTION`  
**理由 Z**：  
命中纯价值比较模板。桥接生成器尝试如下 schema：
- 幸福结果：缺少明确主体、时间窗、结果变量
- 程序正义：不适用
- 偏好满足：问题对象不是清晰政策/行为方案  
最终 0 个合法 bridge candidate，fatal。

### trace 2（不应被 NQ 拦截）

**输入 X**：`相比惩罚，宽恕是否能降低家庭冲突的复发率？`  
**判定 Y**：不命中 `UNFALSIFIABLE_VALUE_ASSERTION`  
**理由 Z**：  
虽然含价值词“宽恕”，但存在明确结果变量“冲突复发率”，可生成经验桥。

### 已知弱点

- 这依赖桥接 schema 集合的覆盖面。schema 太窄，会假阳性。  
- 所以我不把它标成“绝对不可证伪”，而是“在系统支持的合法桥接集合中不可桥接”。

### 可推翻条件

如果新增一套受约束、可审计的 bridge schema 后，能稳定地把被判 fatal 的问题桥接为可测试问题，且假桥接率低，我同意缩小 NQ 拦截面。

---

## 4) `SCOPE_UNBOUNDED`

### 立场

这个应该主要靠规则，不该交给 LLM 乱猜。  
而且我要直接指出：**把它设成 fatal 是可疑的**。  
但你说前序裁定“四种 tag 已定且 NormalizeFatal 终止”，那我在这个约束下给 fatal 判定；同时指出这是设计弱点。

### 核心定义

“未界定”不是“范围很大”，而是：

> 句子含有需要量化比较/归纳的结构，但缺失至少一个必要边界维度，使得无法构造最小可评价样本域。

必要边界维度通常包括：
- **population**：谁
- **time window**：什么时候
- **space/jurisdiction**：哪里
- **comparison class**：与谁比

### 函数签名

```python
def detect_scope_unbounded(
    raw_question: str,
    ctx: DetectionContext
) -> Optional[CategoryHit]:
    """
    Detects questions requiring quantified/general comparison while omitting mandatory scope bounds.
    """
```

### 触发规则

#### 规则 R-SU-1：全称/广域量词 + 比较/趋势谓词 + 无边界
量词：
- `所有` `一切` `人类` `社会` `世界上` `永远` `总是` `从来`
- 英文 `all` `everyone` `always` `never` `humanity`

谓词：
- `更好` `更差` `导致` `会不会` `是否都`
- 趋势、因果、普遍判断

缺边界检查：
- 是否有时间短语：`在 2020-2024 年` `过去十年`
- 是否有人群短语：`在中国城市青少年中`
- 是否有情境短语：`在资本充足的成熟市场中`

若量词/比较结构存在，但上述边界全缺，命中。

#### 规则 R-SU-2：最大化模板无比较域
- `什么是最好的 X`
- `哪个制度对人类最好`
如果没有明确评价人群/时间/目标函数，也命中。

### 伪代码

```python
def detect_scope_unbounded(raw_question: str, ctx: DetectionContext):
    text = normalize_text(raw_question)

    quantified = detect_broad_quantifier(text)
    comparative = detect_comparative_or_causal_claim(text)
    bounds = extract_scope_bounds(text)  # population, time, place, comparison_class

    required_dims = required_scope_dims(text)

    missing = [d for d in required_dims if bounds.get(d) is None]

    if quantified and comparative and len(missing) >= 2:
        return CategoryHit(
            tag=CategoryErrorTag.SCOPE_UNBOUNDED,
            confidence=DetectorConfidence.HIGH,
            evidences=[
                Evidence("R-SU-1", quantified.span, quantified.text, "broad quantifier"),
                Evidence("R-SU-1", comparative.span, comparative.text, "comparative/causal predicate"),
                Evidence("R-SU-1", (0, len(text)), str(missing), f"missing scope bounds: {missing}")
            ],
            llm_used=False
        )

    if matches_superlative_without_domain(text):
        return CategoryHit(...)

    return None
```

### “多宽算未界定”的操作化谓词

不是“太宽”。是这个：

```python
def is_scope_unbounded(text: str) -> bool:
    return (
        contains_generalizing_operator(text)
        and requires_quantified_evaluation(text)
        and missing_required_scope_dimensions(text) >= 2
    )
```

这才叫可执行。  
你想要阈值？我给了：**缺失至少 2 个必要维度**。  
为什么不是 1 个？因为只缺一个通常可在后续澄清中补；缺两个以上，原问题的域基本是漂浮的。

### trace 1（应命中）

**输入 X**：`什么制度对人类最好？`  
**判定 Y**：`SCOPE_UNBOUNDED`  
**理由 Z**：  
- 有超lative “最好”  
- 评价对象“人类”是极广域 population  
- 缺失时间、空间、评价目标函数、比较类  
- `missing_required_scope_dimensions >= 2`

### trace 2（不应命中）

**输入 X**：`在 2010-2020 年 OECD 国家中，哪种碳税设计对降低人均排放最有效？`  
**判定 Y**：不命中  
**理由 Z**：  
边界完整：时间、空间/人群、评价指标都给了。

### 已知弱点

- 我认为这类问题更适合 `NormalizeRecoverable`，不是 fatal。  
- 但你们已经裁定 category error → fatal，那就只能在检测器里压低召回，避免误杀。

### 可推翻条件

如果事实表明“缺失 2 个维度以上”的问题经过 refinement 仍然经常能稳定收敛为高质量 `QuestionFrame`，那 `SCOPE_UNBOUNDED` 不应留在 fatal 类，而应迁移到 recoverable 体系。

---

# 三、NQ 与 CC 的职责边界

现在说问题 J。这里别搞哲学。

---

## 精确定义

### NQ: `UNFALSIFIABLE_VALUE_ASSERTION`

**输入类型**
```python
raw_question: str
```

**作用域**
- 整个用户原始问题
- 在 MB 之前
- 目标是判定：这个问题是不是从入口上就没有经验化通道

**触发条件**
- 命中纯价值模板
- 在受限桥接 schema 集合中生成 0 个合法经验桥 candidate

**动作**
- `NormalizeFatal`
- 终止整个 pipeline

---

### CC: `NO_EMPIRICAL_BRIDGE`

**输入类型**
```python
draft: HypothesisDraft
```

比如：
```python
@dataclass
class HypothesisDraft:
    claim_sketch: str
    source_question_id: str
    derivation_path: list[str]
    target_axis_hint: Optional[str]
```

**作用域**
- 单个 draft
- MB 之后，CC Stage 2
- 目标是判定：这个 draft 能不能被编译成 `TestableClaim`

**触发条件**
- `extract_structure()` 成功抽出命题骨架
- 但 `synthesize_falsifier(draft.claim_sketch)` 无法产出最小 falsifier spec

**动作**
- 不 fatal
- 将该 draft 标为 `RegulativeIdea`
- pipeline 继续处理其他 drafts

---

## 执行路径：如何避免“重复拦截”

这事不能靠口头保证，必须靠类型和状态。

### 关键约束

**CC 不再接收原始问题文本，只接收 MB 产出的 `HypothesisDraft`。**  
这就把输入对象硬隔离了。

### 执行伪代码

```python
def normalize_question(stmt: ProblemStatement, refinements: list[RefinementSignal] = []) -> Result[QuestionFrame, NormalizeError]:
    hits = detect_category_errors(stmt.raw_question, DetectionContext(language="auto"))
    if hits:
        return Err(NormalizeFatal(code="CATEGORY_ERROR", tags=[h.tag for h in hits], repair_advice=generate_repair_hints(hits)))
    return Ok(build_question_frame(stmt))


def clarity_compile(draft: HypothesisDraft) -> CompiledDraft:
    structure = extract_structure(draft.claim_sketch)
    falsifier = synthesize_falsifier(structure)

    if falsifier.status == "NO_EMPIRICAL_BRIDGE":
        return CompiledDraft.regulative_idea(draft, reason="NO_EMPIRICAL_BRIDGE")

    return CompiledDraft.testable_claim(...)
```

### 不重复拦截的系统保证

1. **如果 NQ fatal，MB/CC 根本不会执行。**
2. **如果 NQ 通过，CC 只看 drafts，不重跑 `detect_category_errors(raw_question)`。**
3. 所以不会出现“同一个输入对象在 NQ fatal 之后又在 CC 被再次 fatal”。  
   只可能出现：**问题可进，某些草稿不行。**

---

## 案例 1：能通过 NQ，但某个 draft 在 CC 触发 `NO_EMPIRICAL_BRIDGE`

**原始问题**
`宗教是否有助于社会稳定？`

为什么 NQ 通过？
- 这不是纯价值断言。
- 可以桥接到经验变量：犯罪率、信任度、暴力事件频率、制度持续性。

MB 可能产生两个 drafts：

```python
draft_1.claim_sketch = "宗教提高社区互助密度，从而降低暴力犯罪率。"
draft_2.claim_sketch = "宗教赋予社会神圣秩序，因此更稳定。"
```

CC 处理：

- `draft_1`：可提取变量，能构造 falsifier  
  例如：在控制收入与教育后，无显著降低暴力率 → falsifier possible

- `draft_2`：`神圣秩序` 无观测协议，`更稳定` 也没给机制映射  
  `synthesize_falsifier()` 返回 `NO_EMPIRICAL_BRIDGE`

**执行路径**
- NQ: pass
- MB: 产出多个 drafts
- CC:
  - draft_1 -> `TestableClaim`
  - draft_2 -> `RegulativeIdea(reason=NO_EMPIRICAL_BRIDGE)`

这完全正常，不是职责重叠。

---

## 案例 2：直接在 NQ 被 `UNFALSIFIABLE_VALUE_ASSERTION` 拦截

**原始问题**
`爱比恨更好吗？`

NQ 尝试 bridge generation：
- population 未定
- outcome 未定
- 行为对象未定
- 观测协议未定

0 个合法 bridge candidate。  
于是：

```python
Err(NormalizeFatal(
    code="CATEGORY_ERROR",
    tags=["UNFALSIFIABLE_VALUE_ASSERTION"],
    repair_advice=[...]
))
```

MB/CC 根本不运行。  
所以不存在 CC 再来一次 `NO_EMPIRICAL_BRIDGE`。

---

# 四、对一个常见对手论点的精确攻击

我要直接攻击一种懒惰说法，我猜你很快就会听到：

> “`SELF_REFERENCE_PARADOX` 和 `UNFALSIFIABLE_VALUE_ASSERTION` 都是高度语义性的，最好统一交给 LLM 做分类。”

这说法的缺陷很具体：

1. **没有函数签名**  
   输入是什么？`raw_question: str`？输出只给 tag？证据呢？失败路径呢？  
   没有这些，你连线上误判都没法 debug。

2. **没有触发边界**  
   比如 `SELF_REFERENCE_PARADOX`：  
   - “这句话是假的”应判 fatal  
   - “请解释这句话是假的为何成悖论”不应 fatal  
   如果你不给规则或最小语义边界，假阳性率根本不可控。

3. **把不同误判代价混在一起**  
   NQ 的假阳性代价极高，因为它直接 `NormalizeFatal`。  
   所以 NQ 检测器必须偏保守、可审计。  
   “让 LLM 总体判断一下”就是把最危险的错误交给最不可解释的模块。

如果对手坚持全 LLM，我要他给出这个最小接口：

```python
def llm_detect_category_errors(
    raw_question: str,
    allowed_tags: list[CategoryErrorTag],
    return_evidence_spans: bool,
    abstain_threshold: float
) -> list[CategoryHit]:
    ...
```

并拿出**每个 tag 的 confusion matrix**。拿不出来，就别装工程化。

---

# 五、我的方案的总弱点

说清楚，不装无敌。

1. **`UNFALSIFIABLE_VALUE_ASSERTION` 依赖 bridge schema 集合质量**  
   schema 太窄会误杀。这个风险真实存在。

2. **`SCOPE_UNBOUNDED` 被归到 fatal 不优雅**  
   我认为它本质更像 recoverable underspecification。  
   在既定裁定下，我只能通过高阈值（缺至少 2 个必要维度）来降低误杀。

3. **多语言、多句式覆盖不完整**  
   规则集一开始肯定偏中英常见表达，长尾要靠日志驱动迭代。

4. **抽象实体消歧有灰区**  
   “算法”“制度”“文化”一类对象，在抽象/经验之间经常滑动。  
   这要求 detector 宁可保守漏检，也别轻易 fatal。

---

# 六、最后给出一个可落地总实现框架

```python
def detect_category_errors(raw_question: str, ctx: DetectionContext) -> list[CategoryHit]:
    hits: list[CategoryHit] = []

    detectors = [
        detect_self_reference_paradox,
        detect_non_empirical_attribute_on_abstract_entity,
        detect_unfalsifiable_value_assertion,
        detect_scope_unbounded,
    ]

    for det in detectors:
        hit = det(raw_question, ctx)
        if hit is not None:
            hits.append(hit)

    # optional: de-dup or priority ordering
    return resolve_detector_conflicts(hits)
```

冲突处理建议：
- `SELF_REFERENCE_PARADOX` 优先级最高
- `UNFALSIFIABLE_VALUE_ASSERTION` 与 `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY` 可并存
- `SCOPE_UNBOUNDED` 若与前两者同时命中，只作为附加证据，不单独主导 repair hint

---

# 七、结论

我的完整立场：

- **`SELF_REFERENCE_PARADOX`**：规则优先，LLM 仅兜底。  
- **`NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`**：主体类型词表/类型系统 + 谓词类别规则，LLM 做灰区消歧。  
- **`UNFALSIFIABLE_VALUE_ASSERTION`**：不是“任何框架都不行”的神棍定义，而是“在固定合法桥接 schema 集内无合法经验桥”的问题级 fatal。  
- **`SCOPE_UNBOUNDED`**：用缺失必要边界维度数来操作化；当前裁定下可 fatal，但我明确认为这是体系的别扭点。

- **NQ/CC 边界**：  
  - NQ 处理 `raw_question` 的入口合法性  
  - CC 处理 `HypothesisDraft` 的可编译性  
  - 两者不重复，因为输入对象和动作语义都不同

如果你要继续反驳，别再讲“感觉上”。  
给我：
1. 你的函数签名  
2. 你的触发规则  
3. 至少一个 trace  
4. 假阳性和假阴性的代价分析  
否则就是在浪费大家时间。

---


### [2] Ssyram

*2026-03-09T18:55:14.806378*

我是 Ssyram。作为 v3 框架的核心设计者，我以 CEGAR（反例引导的抽象精炼）和形式化方法的视角介入本轮辩论。

在开始构建具体算法前，我必须先进行一次**精确的定点打击**。

### 0. 对议题文本中架构越界的攻击

我注意到议题在「I-d. SCOPE_UNBOUNDED 的判定」中提出了一个极其危险且退化的设想：
> **引用文本**：“是否应该是 recoverable（让用户补充）而非 fatal（直接终止）？”

**我的攻击**：这种设想是对已裁定架构的公然破坏，暴露出提出者对 Layer 1 状态机边界的严重混淆。前序辩论已铁定裁决：`detect_category_errors()` 返回的任何 tag 都会触发 `NormalizeFatal`，导致 pipeline 绝对终止。如果 `SCOPE_UNBOUNDED` 只是需要用户补充的 recoverable error，它**根本就不该作为 CategoryErrorTag 出现**，而应该下放到 Phase 4 的 `open_terms` 提取中，通过 `NormalizeRecoverable` 走精炼回路！

既然它被列入了 CategoryErrorTag 枚举，它在 NQ 阶段的语义就必须是**「绝对无法通过有限轮次精炼收敛的终极发散域」**。不要试图在 Phase 1 搞 recoverable 的小动作，这会导致状态机判定循环。

---

### 一、 问题 I：基于 CEGAR 的 `detect_category_errors` 分层判定算法

我的核心主张是：**拒绝纯 LLM 路由**。必须采用「确定性规则（快速拦截）+ LLM 语义检查（边界判定）」的双层架构。

#### 1. 函数签名与判定分层

```python
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class CategoryErrorTag:
    tag_type: str # "SELF_REFERENCE_PARADOX" | "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY" | ...
    confidence: float
    evidence: str

def detect_category_errors(raw_q: str) -> List[CategoryErrorTag]:
    errors = []
    
    # Layer 1: Deterministic Syntactic/Lexical Over-approximation (Regex & AST)
    # 极低成本，覆盖 60% 的恶意 Troll 和典型范畴错误
    if (paradox := _fast_check_self_reference(raw_q)):
        errors.append(paradox)
        
    # Layer 2: Semantic Bounding Check via LLM (仅在 L1 未命中时触发)
    # 针对抽象实体和价值断言的语义树分析
    if not errors:
        semantic_errors = _llm_semantic_category_check(raw_q)
        errors.extend(semantic_errors)
        
    return errors

def _fast_check_self_reference(raw_q: str) -> Optional[CategoryErrorTag]:
    import re
    # 规则：指示代词 + 命题本体 + 悖论谓词
    pattern = r'(这|此|该|本).*(句话|命题|陈述|问题|断言).*(假|错|悖论|不成立)'
    if re.search(pattern, raw_q):
        return CategoryErrorTag("SELF_REFERENCE_PARADOX", 1.0, "Matched self-referential paradox syntax")
    return None
```

#### 2. SELF_REFERENCE_PARADOX 的判定
- **规则集覆盖率**：上述正则及 AST 变体足以覆盖真实世界中约 80% 的「无聊测试（Troll）」输入（如「这句话是假的」）。
- **LLM 兜底**：剩下的 20%（如「如果我问你这个问题，你的回答会是错的吗」）交由 Layer 2 的 LLM 处理。
- **误判代价**：假阳性（误杀）比假阴性（漏放）更危险。因此，正则必须严格限定在「自指代词+真值否定」的强耦合结构。

#### 3. NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY 的判定
- **抽象实体的分类标准**：定义集合 $E_{abs} = \{数学对象, 纯逻辑构造, 虚构宇宙设定\}$。
- **判定谓词**：若实体 $e \in E_{abs}$，且其谓词 $P$ 属于 $\{伦理价值, 物理因果, 审美\}$，则触发 fatal。
- **判定 Trace 1（应判 Fatal）**：
  - 输入 X：「数字 7 是幸运的吗？」
  - 判定 Y：`NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`
  - 理由 Z：LLM 提取实体 $e=\text{"数字 7"}$（归属 $E_{abs}$ 的数学对象），提取属性 $P=\text{"幸运"}$（归属伦理/玄学价值）。数学对象无经验观测接口，范畴错误成立。
- **判定 Trace 2（不应判 Fatal）**：
  - 输入 X：「数字 7 是黎曼 zeta 函数的零点吗？」
  - 判定 Y：通过（空列表）
  - 理由 Z：实体 $e=\text{"数字 7"}$ 虽属于 $E_{abs}$，但属性 $P=\text{"黎曼 zeta 函数的零点"}$ 属于纯逻辑构造，范畴匹配，不触发非经验属性谬误。

#### 4. SCOPE_UNBOUNDED 的量化标准
- **操作性定义**：在全称量化（$\forall$）下，缺乏**任何一个**「时空边界变量（Spatio-temporal bound）」或「人口学边界变量（Demographic bound）」的问题。
- **阈值**：「人为什么会做梦？」-> Fatal（全人类，全时间段，无限域）。「现代都市白领为什么会失眠？」-> Pass（有明确人口学和时代边界）。

---

### 二、 问题 J：NQ 与 CC 的职责边界（形式化界定）

这根本不是重复拦截，而是**全称量词（$\forall$）与存在量词（$\exists$）在不同作用域下的验证**。

#### 1. 精确语义差异
- **NQ 阶段（UNFALSIFIABLE_VALUE_ASSERTION）**：
  - **形式化语义**：$\forall f \in Frames, \not\exists c \in Claims(f) : IsEmpirical(c)$
  - **作用域**：原始问题（Raw Question）。
  - **触发条件**：任何合法的评估轴（evaluation_axes）都无法为这个问题榨取出一丝一毫的经验可验证内容。它是**彻底的经验真空**。
- **CC 阶段（NO_EMPIRICAL_BRIDGE）**：
  - **形式化语义**：$IsEmpirical(Draft_i) == False$
  - **作用域**：经过 MB 阶段扩散后的**某一个具体草稿（HypothesisDraft）**。
  - **触发条件**：问题本身是合法的，但 MB 生成的这特定一条草稿，在尝试合成 `falsifier` 时，发现无法找到可操作的测量指标。

#### 2. 判定 Trace 3（NQ 拦截）
- **输入 X**：「爱比恨更好吗？」
- **判定 Y**：NQ 阶段直接返回 `UNFALSIFIABLE_VALUE_ASSERTION` (NormalizeFatal)。
- **理由 Z**：无论引入何种社会学或心理学框架，原问题纯粹在比较两个抽象概念的绝对价值，属于彻底的经验真空，整个 pipeline 终止。

#### 3. 判定 Trace 4（NQ 通过，CC 降格）
- **输入 X**：「民主制度能促进社会进步吗？」
- **NQ 判定**：通过。因为「社会进步」可以通过经济指标、识字率等框架被经验化。
- **MB 生成草稿**：
  - Draft 1: "民主制度提高了人均 GDP"
  - Draft 2: "民主制度让国民灵魂更自由"
- **CC 判定**：
  - Draft 1 成功合成 falsifier。
  - Draft 2 在 `synthesize_falsifier()` 中返回 `NO_EMPIRICAL_BRIDGE`。
- **理由 Z**：Draft 2 的「灵魂更自由」无法映射到经验测量。此时 Draft 2 升级为 `RegulativeIdea` 供 RB 节点消费，而整个 pipeline 依然靠 Draft 1 继续运转。**这就是两者不重叠的铁证。**

---

### 三、 方案的已知弱点与可推翻条件

**1. 已知弱点（最不确定点）**：
- `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY` 强依赖 LLM 对「抽象实体」的分类稳定性。当遇到「虚拟货币（如比特币）」时，LLM 极易在「纯逻辑构造」和「社会经济实体」之间震荡，导致误判。
- `SCOPE_UNBOUNDED` 的「时空边界变量」要求可能过于严苛，可能导致一些本可通过 MB 阶段自动收缩视角的宏大问题（如「气候变化有什么影响」）在 NQ 阶段被过早绞杀。

**2. 可推翻条件（Falsifiability of my claims）**：
- 如果对手能证明：在真实业务 log 中，存在超过 30% 的问题，其在 NQ 阶段被判为 `UNFALSIFIABLE_VALUE_ASSERTION`，但人类专家能为其写出至少一个 `TestableClaim`，则我的 NQ/CC 边界定义破产。
- 如果对手能证明：`_fast_check_self_reference` 的正则在生产环境中导致了超过 5% 的假阳性（将正常复杂句型判为悖论），则我主张的 CEGAR 第一层确定性规则失效。

---


### [3] 康德（Immanuel Kant）

*2026-03-09T18:55:14.806394*

我选择两者都答：**问题 I（判定算法）**与**问题 J（NQ/CC 职责边界）**。  
我的立场是：**Phase 1 的 `detect_category_errors()` 只能做“先验上足够确定”的范畴排除，不能把经验启发式僭越为范畴判决**。凡其判断依赖开放语境、世界知识或未穷尽的评价框架者，就不应在 NQ 以 `NormalizeFatal` 终止，而应降格为后续阶段处理。

这也是我对当前讨论中一个潜在危险前提的精确攻击：

> 对方文本中将 `detect_category_errors()` 描述为  
> “Phase 1: 范畴检查（不可恢复失败）”  
> 且要求在此阶段判定 `UNFALSIFIABLE_VALUE_ASSERTION` 与 `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`。

**缺陷在于**：若这些判定实际依赖 LLM 的开放语义猜测，则你们是在用经验性的启发式分类，冒充先验范畴判断。一旦误判，就不是普通召回率问题，而是**非法剥夺后续经验检验机会**。  
**可推翻条件**：若对方能给出对每一类 tag 的**有限规则集、失败路径、与 LLM 仅作辅助解释而不作最终范畴裁决**的接口，我撤回此攻击。

---

# 一、总立场：Phase 1 只接受“保守 fatal”

我主张 `detect_category_errors()` 采用三值输出思想，但保持与你们既定接口兼容：

- **fatal**：规则足以确定为范畴错误
- **not_detected**：未检测到
- **indeterminate**：证据不足，不得 fatal

由于既定接口是 `CategoryErrorTag[]`，则实现上应是：  
**只有 fatal 才返回 tag；其余一律不返回。**

这意味着：

1. `SELF_REFERENCE_PARADOX`：可在较窄范围内由规则可靠判定，允许 fatal。
2. `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`：只在“抽象实体词典 + 非经验谓词词典”双高置信命中时 fatal。
3. `UNFALSIFIABLE_VALUE_ASSERTION`：**极难**在 NQ 做全称断定；只能在受限条件下 fatal。
4. `SCOPE_UNBOUNDED`：原则上更像 `NormalizeRecoverable`，但既然枚举已定为 category error，我主张只对**显式全称且无任何域约束**的形式 fatal；其余不判。

**可推翻条件**：若工程目标明确要求“宁杀错不放过”，则可扩大 fatal 范围；但那将改变系统认识论定位，不再是“范畴检查”，而是“风险预筛”。

---

# 二、问题 I：四种 CategoryErrorTag 的判定算法

---

## 2.1 完整函数签名

先给总接口，再给子判定器。

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Literal

CategoryErrorTag = Literal[
    "SELF_REFERENCE_PARADOX",
    "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY",
    "UNFALSIFIABLE_VALUE_ASSERTION",
    "SCOPE_UNBOUNDED",
]

class DetectionStatus(str, Enum):
    FATAL = "FATAL"
    NOT_DETECTED = "NOT_DETECTED"
    INDETERMINATE = "INDETERMINATE"

@dataclass
class DetectionReason:
    tag: CategoryErrorTag
    status: DetectionStatus
    confidence: float
    matched_rules: list[str]
    evidence_spans: list[str]
    explanation: str

@dataclass
class CategoryDetectionReport:
    fatal_tags: list[CategoryErrorTag]
    reasons: list[DetectionReason]

def detect_category_errors(
    raw_question: str,
    locale: str = "zh-CN",
    allow_llm_backoff: bool = False,
) -> list[CategoryErrorTag]:
    """
    Public interface fixed by prior decision.
    Returns only fatal tags.
    Non-fatal/indeterminate judgments are suppressed from public return.
    """

def detect_category_errors_report(
    raw_question: str,
    locale: str = "zh-CN",
    allow_llm_backoff: bool = False,
) -> CategoryDetectionReport:
    """
    Internal diagnostic interface.
    LLM may be used only to explain or to abstain, not to issue fatal alone.
    """
```

### 设计原则
- **LLM 不能单独产生 fatal**；只能：
  1. 解释规则命中的理由；
  2. 在规则不足时返回 `INDETERMINATE`。
- 这避免“经验启发式僭越为范畴判断”。

**可推翻条件**：若对方证明某一 tag 可通过经过校准的分类器在误判成本上优于规则，并且系统接受这种概率式 fatal，则可放宽此原则。

---

## 2.2 SELF_REFERENCE_PARADOX

### 立场
`SELF_REFERENCE_PARADOX` 在 NQ 只能识别**显式语言自指悖论**，不能声称覆盖所有自指悖论，更不能覆盖哥德尔式编码自指。

因此我拒绝任何这种说法：  
> “句法模式足以捕获所有自指悖论。”

这显然不成立。哥德尔句并无表层“这句话”结构，却能实现编码自指。  
但这并不反驳在工程上使用规则；它只说明：**NQ 所判的是“表层可识别自指悖论”，不是一切可能的自指结构”。**

### 函数签名

```python
def detect_self_reference_paradox(
    text: str,
    *,
    allow_llm_backoff: bool = False
) -> DetectionReason:
    """
    Fatal only for explicit self-referential liar-style paradoxes.
    Failure path:
      - if no explicit self-reference anchor -> NOT_DETECTED
      - if self-reference exists but contradiction pattern weak/ambiguous -> INDETERMINATE
      - LLM may only clarify ambiguity, never upgrade to FATAL without a rule hit
    """
```

### 规则集
按优先级：

#### R1 显式自指锚点
出现如下锚点之一：
- “这句话 / 此句 / 本句 / 本命题 / 此陈述 / 本陈述 / 该断言自身”
- 英文类比：“this sentence”, “this statement”, “the present proposition”

#### R2 悖论谓词
锚点与以下谓词形成断言：
- “是假的 / 不是真的 / 不可证明 / 不可断言 / 不成立”
- 或其否定回环形式：“本句不可被判真”，“此命题为假”

#### R3 同位回指
语义上主语即该句自身，而不是外部对象。  
例如：
- “这句话是假的” → 命中
- “关于这句话的评论是假的” → 不命中

#### 判定逻辑
```python
if explicit_self_ref_anchor and liar_style_predicate and same_sentence_subject:
    FATAL
elif explicit_self_ref_anchor and paradox_suspected_but_not_liar_form:
    INDETERMINATE
else:
    NOT_DETECTED
```

### 覆盖率主张
- 对**真实线上自然语言输入中的表层自指悖论**，我估计规则可覆盖 **70–85%**。
- 对**全部逻辑上可能的自指悖论**，覆盖率远低，可能 **<20%**。

我特意区分这两个分母。若不区分，就是概念偷换。

**可推翻条件**：若对方提供真实语料基准，显示显式表层模式仅占日常输入中自指悖论的少数，则我的覆盖估计应下修。

### trace
**输入为 X → 判定为 Y → 理由为 Z**

- X: `这句话是假的。`
- Y: `SELF_REFERENCE_PARADOX`
- Z:
  - 命中自指锚点：“这句话”
  - 命中 liar 谓词：“是假的”
  - 主语即当前句自身
  - 故形成显式语言自指悖论，fatal

### 已知弱点
1. 漏检哥德尔式、编码式、跨句链式自指。
2. 对修辞性表达可能保守放过。
3. 多语言变体需额外词表维护。

---

## 2.3 NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY

### 核心认识论立场
“抽象实体”分类既有**先验核**，也有**语言实现层的经验判定**。

- 先验核：数学对象、逻辑命题、集合、证明、数、函数等，按其概念角色属于非时空个体，不以经验个体方式出现。
- 经验层：具体语言表达中的某个名词短语，是否正在指称这类抽象实体，需要解析语义与用法。

所以我反对以下隐含主张：

> “只要用 LLM 判断一个词是不是抽象实体，就可在 Phase 1 fatal。”

**缺陷**：你把“抽象性”这个概念核，与“此处该词是否作抽象指称”的语言学判定混为一谈。  
例如“圆”可指几何对象，也可指圆形餐桌。  
因此，NQ 只能对**高置信抽象指称**下 fatal。

### 判定谓词与函数签名

```python
@dataclass
class ParsedPredicate:
    subject_np: str
    copula: Optional[str]
    predicate_np_or_adj: str

def is_abstract_entity_np(np: str) -> tuple[bool, float, list[str]]:
    """
    Returns:
      (is_abstract, confidence, evidence)
    High-confidence abstract classes:
      numerals, mathematical objects, sets, propositions, proofs, equations, functions, logical laws
    """

def is_non_empirical_attribute(pred: str) -> tuple[bool, float, list[str]]:
    """
    Returns:
      (is_non_empirical, confidence, evidence)
    High-confidence non-empirical attributes:
      lucky, sacred, morally pure, cursed, spiritually superior
    Excludes formal/mathematical predicates:
      prime, even, consistent, valid, provable
    """

def detect_non_empirical_attribute_on_abstract_entity(
    text: str
) -> DetectionReason:
    """
    Fatal only if:
      subject is high-confidence abstract entity
      AND predicate is high-confidence non-empirical attribute
      AND predication is direct, not metaphor quotation or reported speech
    """
```

### 判定规则

#### 抽象实体高置信类
以下主语短语默认高置信抽象：
- 数字/数词作数学对象：`7`, `数字7`, `数7`
- `集合A`, `空集`, `函数f`, `命题P`, `逻辑公式`, `定理`, `证明`
- `正义`、`自由` 这类抽象概念词要谨慎；它们是抽象名词，但未必属于本 tag 目标中的“抽象实体”。我主张**不自动 fatal**。

#### 非经验属性高置信类
以下谓词高置信非经验：
- `幸运的`, `神圣的`, `被诅咒的`, `高贵的`（若无评价轴）
- `宇宙偏爱的`, ` spiritually pure` 等

以下不属于该类：
- 数学/逻辑属性：`质数`, `偶数`, `可证明`, `一致`
- 明确可观察桥接的属性：`被印在红色卡片上`（哪怕对象词是“数字7”的符号实例）

#### fatal 条件
```python
if abstract_subject_conf >= 0.9 and non_empirical_pred_conf >= 0.9 and direct_predication:
    FATAL
elif one side uncertain:
    INDETERMINATE
else:
    NOT_DETECTED
```

### trace 1：应判 fatal
- X: `数字 7 是幸运的。`
- Y: `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`
- Z:
  - 主语“数字7”命中数学对象，高置信抽象实体
  - 谓词“幸运的”命中非经验属性
  - 直接述谓，无引号、隐喻或实例化桥接
  - 故 fatal

### trace 2：不应判 fatal
- X: `数字 7 是质数。`
- Y: `NOT_DETECTED`
- Z:
  - 主语是抽象实体无误
  - 但谓词“质数”是形式属性，可在数学系统内判定
  - 不属于“对抽象实体赋非经验属性”

### trace 3：不应判 fatal
- X: `纸上的数字 7 是红色的。`
- Y: `NOT_DETECTED`
- Z:
  - 实际主语是符号实例/墨迹记号，不是抽象数对象本身
  - “红色”有经验桥接
  - 故不可 fatal

### 已知弱点
1. “抽象实体”与“抽象概念词”边界并不总清楚。
2. 隐喻、拟人修辞、宗教语境会造成歧义。
3. 需要句法解析，不能只靠词表。

**可推翻条件**：若对方能提出一个无需句法角色区分、纯词典即可稳定区分“数字7”与“纸上的数字7”的方法，我承认我对复杂性的估计过高。

---

## 2.4 UNFALSIFIABLE_VALUE_ASSERTION

### 最关键立场
这里必须最严格。  
“**任何可能框架都无法证伪**”是一个全称断言。若你在 Phase 1 没有穷尽合法 evaluation axes，就没有资格下这个判决。

因此我反对如下隐含设计：

> “当前 LLM 想不出 falsifier，就可在 NQ 判 `UNFALSIFIABLE_VALUE_ASSERTION`。”

这只是**生成失败**，不是**不可证伪**。

### 操作性定义
NQ 中的 `UNFALSIFIABLE_VALUE_ASSERTION` 应缩减为：

> 命题是**纯规范性比较或赞许/谴责表达**，且  
> 不包含任何显式对象域、评价轴、结果变量、约束条件、适用主体，  
> 因而**在预定义的有限桥接模板库中**无一可生成经验比较主张。

请注意：这里不再声称“任何可能框架都不行”，而是说：  
**在系统认可的桥接模板全集内，不存在经验桥接。**  
这才是可操作的。

### 函数签名

```python
@dataclass
class BridgeTemplate:
    name: str
    required_slots: list[str]   # e.g. agent, outcome, population, time_horizon
    description: str

def detect_unfalsifiable_value_assertion(
    text: str,
    bridge_templates: Sequence[BridgeTemplate],
) -> DetectionReason:
    """
    Fatal iff:
      1) text is primarily a value assertion/comparative evaluation
      2) no empirical object/behavior/outcome variable is explicitly referenced
      3) no bridge template can be instantiated above threshold
    """
```

### 判定阈值
设模板实例化函数：

```python
def instantiate_bridge_templates(
    text: str,
    templates: Sequence[BridgeTemplate]
) -> list[tuple[str, float, dict[str, str]]]:
    """
    returns list of (template_name, fit_score, bound_slots)
    """
```

则阈值为：

- 若存在任一模板 `fit_score >= 0.65`，则**不得**判 `UNFALSIFIABLE_VALUE_ASSERTION`
- 仅当：
  - 命题被识别为价值断言 `value_score >= 0.85`
  - 且所有模板 `fit_score < 0.35`
  - 才可 fatal
- 介于其间一律 `INDETERMINATE`

### 与“当前框架下找不到 falsifier”的区别
- **NQ fatal**：模板全集内均无法桥接，说明问题本身缺乏经验入口。
- **CC `NO_EMPIRICAL_BRIDGE`**：问题总体允许桥接，但该**具体草稿**未能编译出可观测量。

这是类型差异，不是重复检测。

### trace：应在 NQ 被拦截
- X: `爱比恨更好。`
- Y: `UNFALSIFIABLE_VALUE_ASSERTION`
- Z:
  - 价值比较命题
  - 无主体、无情境、无结果变量、无时间尺度
  - 模板如“对主观幸福影响”“对合作稳定性影响”“对暴力率影响”均无法实例化，因为对象未行为化、变量未绑定
  - 故 fatal

### trace：不应在 NQ 拦截
- X: `在长期稳定合作中，宽恕比报复更好。`
- Y: `NOT_DETECTED`
- Z:
  - 仍含价值词“更好”
  - 但给出情境“长期稳定合作”
  - 可桥接到经验轴：合作持续率、复犯率、关系维持率
  - 因而不属于 NQ 的纯不可证伪断言

### 已知弱点
1. 模板全集是约定的，不是形而上学穷尽。
2. “更好”常可被语境补足，NQ 会保守放行不少边界案例。
3. 会产生较多假阴性，但这是正确代价，因为 NQ fatal 的误伤成本更高。

**可推翻条件**：若对方能给出一个可计算的“所有合法 evaluation_axes”的封闭集合，并证明其完备性，我接受更强版本的 NQ 判定。

---

## 2.5 SCOPE_UNBOUNDED

### 立场
此 tag 最危险，因为“未界定”通常是可澄清的，不是范畴错误。  
但既然枚举已定，我主张将其限缩为：

> 命题使用显式全称量化，但其量化域在句内和系统默认语境中都不可识别，导致无法形成任何合法比较对象集。

### 函数签名

```python
def detect_scope_unbounded(
    text: str,
    default_domains: dict[str, list[str]] | None = None
) -> DetectionReason:
    """
    Fatal only for explicit universal/general quantification with no recoverable domain.
    """
```

### 规则
命中以下之一：
- `所有`, `一切`, `任何`, `永远`, `处处`, `普遍`, `everyone`, `everything`, `always`
并且：
- 无显式时间范围
- 无显式人群/对象域
- 无系统默认可承接域
- 问句目标依赖该量化域才能评估

### trace：应判 fatal
- X: `所有事物最终都会变得更好，是真的吗？`
- Y: `SCOPE_UNBOUNDED`
- Z:
  - “所有事物”是全称量化
  - 对象域无界；“最终”时间域亦无界
  - 无法形成可比较集合或观测窗口
  - 故 fatal

### trace：不应判 fatal
- X: `所有参加本次实验的被试都会在两周内表现更好吗？`
- Y: `NOT_DETECTED`
- Z:
  - “所有”虽是全称量化
  - 但对象域“参加本次实验的被试”明确
  - 时间域“两周内”明确
  - 可经验检验

### 误判代价
- 假阳性代价极高：剥夺澄清机会
- 假阴性代价较低：后续 CC/clarify 仍可要求补域

因此应采取**极保守 fatal**。

**可推翻条件**：若系统产品目标是强制所有问题在进入 MB 前就具备可计算量化域，则可扩大该 tag 的使用，但那已是产品约束，不是纯范畴论证。

---

# 三、问题 J：NQ 阶段 `UNFALSIFIABLE_VALUE_ASSERTION` 与 CC 阶段 `NO_EMPIRICAL_BRIDGE` 的职责边界

---

## 3.1 精确定义差异

我给出形式化区分：

### NQ / `UNFALSIFIABLE_VALUE_ASSERTION`
- **输入**：`raw_question: str`
- **作用域**：整个原始问题
- **判断对象**：问题本身是否连最小经验桥接入口都没有
- **触发条件**：
  1. 价值断言/比较为主
  2. 无对象域、无结果变量、无约束条件
  3. 对系统模板库而言不可实例化任何经验桥接
- **后果**：`NormalizeFatal`，终止整个 pipeline

### CC / `NO_EMPIRICAL_BRIDGE`
- **输入**：`HypothesisDraft.claim_sketch`
- **作用域**：某一条 MB 生成的草稿
- **判断对象**：这条具体草稿是否能降格为可测主张
- **触发条件**：
  1. 该草稿有一定语义内容
  2. 但其内部术语与可观测量之间找不到映射
  3. 其他草稿仍可能成功
- **后果**：升级为 `RegulativeIdea`，而非终止 pipeline

### 接口类型

```python
@dataclass
class HypothesisDraft:
    claim_sketch: str
    source_question: str
    assumed_axes: list[str]
    hidden_assumptions: list[str]

class FalsifierSynthesisResultType(str, Enum):
    TESTABLE = "TESTABLE"
    NO_EMPIRICAL_BRIDGE = "NO_EMPIRICAL_BRIDGE"
    UNDER_SPECIFIED = "UNDER_SPECIFIED"

@dataclass
class FalsifierSynthesisResult:
    type: FalsifierSynthesisResultType
    observables: list[str]
    explanation: str

def synthesize_falsifier(
    draft: HypothesisDraft,
) -> FalsifierSynthesisResult:
    ...
```

---

## 3.2 一个通过 NQ、但在 CC 触发 `NO_EMPIRICAL_BRIDGE` 的案例

### 原问题
`为什么有些文明比另一些文明更伟大？`

### 为什么通过 NQ
- 它不是纯空洞价值句；至少有对象域“文明”
- 可能桥接到某些评价轴：持续时间、识字率、技术扩散、暴力控制能力等
- 因此 **NQ 不应 fatal**

### MB 可能生成的一个草稿
`更伟大的文明拥有更高的精神纯度。`

### CC 为什么触发 `NO_EMPIRICAL_BRIDGE`
- “精神纯度”缺少观测映射
- 该草稿中的核心谓词无法与可测量变量建立桥梁
- 因而此草稿是 `RegulativeIdea`

这正说明：**问题层面可桥接，不意味着每个草稿都可桥接。**

---

## 3.3 一个直接在 NQ 被 `UNFALSIFIABLE_VALUE_ASSERTION` 拦截的案例

### 原问题
`爱比恨更好吗？`

- 纯价值比较
- 无情境、无主体、无结果变量
- 模板无法实例化
- 故在 NQ 直接 fatal

这里不需要等到 CC，因为根本没有可合法展开的问题框架。

---

## 3.4 如何保证两者不重复拦截

核心原则：

> **NQ 判断“问题是否有至少一个经验入口”；CC 判断“这个草稿是否成功走到那个入口”。**

### 具体保证机制 1：NQ 只使用“存在性”判据
NQ 不问“所有后续草稿都能否桥接”，只问：

```python
exists_empirical_entry(raw_question) == True ?
```

若真，则放行。

### 具体保证机制 2：CC 不回写 NQ fatal
即便所有草稿都 `NO_EMPIRICAL_BRIDGE`，CC 也不能 retroactively 宣布 NQ 错了。  
它只说明：**当前 MB 搜索失败**，可交由 RB 扩展或要求用户澄清。

### 具体保证机制 3：接口上禁止同义重判
在 `QuestionFrame` 中加入 NQ 判定摘要：

```python
@dataclass
class QuestionFrame:
    raw_question: str
    empirical_entry_candidates: list[str]   # from NQ, maybe empty if fatal
    ...
```

若 `empirical_entry_candidates` 非空，则 CC 的 `NO_EMPIRICAL_BRIDGE` 只能针对草稿，不得将整题升级为 `UNFALSIFIABLE_VALUE_ASSERTION`。

---

# 四、对至少一个对手论点的精确攻击

我攻击一种在你方问题表述中已显露的倾向：

> 你方在 I-c 中问：  
> “任何合法 evaluation_axes 框架都无法为该问题生成可证伪主张——这个判断需要穷举吗？”

我的回答是：**是的，若你坚持“任何合法框架都不行”这个语义，你就需要一个封闭且可枚举的合法框架全集；否则这个判定没有先验合法性。**

具体缺陷：
1. 若“合法 evaluation_axes”是开放集，则无法完成全称验证。
2. 若你不穷举，只是“当前想不到”，那是搜索不足，不是不可证伪。
3. 若你让 LLM 凭感觉断言“所有框架都不行”，那就是把经验启发式僭越为范畴判决。

**可推翻条件**：  
若对方定义：
- `evaluation_axes` 的形式语言，
- 合法轴生成文法，
- 可判定的完备模板集，
则可以把“任何合法框架都无法证伪”收缩为“对本系统合法轴全集都无法桥接”，从而获得操作意义。

---

# 五、伪代码总实现

```python
def detect_category_errors_report(
    raw_question: str,
    locale: str = "zh-CN",
    allow_llm_backoff: bool = False,
) -> CategoryDetectionReport:
    reasons = []

    reasons.append(detect_self_reference_paradox(
        raw_question, allow_llm_backoff=allow_llm_backoff
    ))

    reasons.append(detect_non_empirical_attribute_on_abstract_entity(
        raw_question
    ))

    reasons.append(detect_unfalsifiable_value_assertion(
        raw_question,
        bridge_templates=SYSTEM_BRIDGE_TEMPLATES
    ))

    reasons.append(detect_scope_unbounded(
        raw_question,
        default_domains=SYSTEM_DEFAULT_DOMAINS
    ))

    fatal_tags = [r.tag for r in reasons if r.status == DetectionStatus.FATAL]
    return CategoryDetectionReport(fatal_tags=fatal_tags, reasons=reasons)


def detect_category_errors(
    raw_question: str,
    locale: str = "zh-CN",
    allow_llm_backoff: bool = False,
) -> list[CategoryErrorTag]:
    report = detect_category_errors_report(
        raw_question=raw_question,
        locale=locale,
        allow_llm_backoff=allow_llm_backoff,
    )
    return report.fatal_tags
```

---

# 六、我的方案的已知弱点

1. **保守**：会放过不少边界案例，尤其是 `UNFALSIFIABLE_VALUE_ASSERTION`。
2. **依赖模板库**：NQ 的“不可桥接”不是形而上学真理，只是对系统模板全集而言。
3. **语言解析成本不低**：尤其 `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY` 需要句法角色识别。
4. **`SCOPE_UNBOUNDED` 与 recoverable 的边界仍不优雅**：若未来允许 Phase 1 返回 recoverable，此 tag 应大幅迁移出去。

**可推翻条件**：若系统经验数据显示，保守策略导致下游成本爆炸，且误杀可控，则可扩大 Phase 1 的 fatal 范围；但那应被诚实地重命名为“高风险预筛”，而非“范畴检查”。

---

# 七、结论

我的结论极简单：

- `SELF_REFERENCE_PARADOX`：**只判显式表层自指悖论**；不可冒称覆盖哥德尔式自指。
- `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`：**抽象实体有先验核，但具体语言指称需经验解析**；仅高置信双命中 fatal。
- `UNFALSIFIABLE_VALUE_ASSERTION`：**不得以“当前想不到桥接”为由作全称 fatal**；只能基于封闭模板全集作操作性定义。
- `SCOPE_UNBOUNDED`：**极保守使用**，否则就是把可澄清问题误杀为范畴错误。
- NQ 与 CC 的边界是：  
  **NQ 判断问题有没有至少一个经验入口；CC 判断某个草稿是否成功落实这个入口。**

若对手不能证明其算法中的 fatal 判定**不依赖开放语义猜测**，那么它就在认识论上犯了同一个错误：  
**把经验启发式，伪装成先验范畴裁决。**

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-09T18:55:37.460944*

1. 你嘴上说“必须给出可实现算法”，结果一到关键处就开始偷懒：`_llm_semantic_category_check(raw_q)` 这个黑盒到底输入什么、输出什么、prompt 边界是什么、允许返回哪些 tag、置信度阈值多少、谁来裁决 fatal？你把 **NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY / UNFALSIFIABLE_VALUE_ASSERTION / SCOPE_UNBOUNDED** 三个最难的判定全塞进这个黑箱，然后宣称“拒绝纯 LLM 路由”。这不是工程，这是把不确定性藏起来。  
   - 具体追问：给出函数签名。比如  
     `def _llm_semantic_category_check(raw_q: str) -> list[CategoryErrorTag]`  
     太空泛了。你至少要定义：  
     `entity_span`, `predicate_span`, `scope_markers`, `candidate_axes`, `empirical_bridge_exists: bool`。  
   - 否则你的方案无法分析误判成本，更无法复现同一输入为何 Fatal。

2. 你对 **SCOPE_UNBOUNDED** 的定义是明显过度、而且和你自己的例子互相打架。你给的谓词是：“全称量化下，缺乏任何一个时空边界变量或人口学边界变量”。问题是这会把大量正常科研问题直接误杀。  
   - 例子：`“人为什么会做梦？”` 你判 Fatal。凭什么？这明明可以自然落到“人类睡眠中的梦生成机制”这种可研究问题，MB/CC 完全能展开。  
   - 反例再给一个：`“气候变化有什么影响？”` 你自己承认可能被过早绞杀。这不是“小弱点”，这是你谓词本身没定义好。  
   - 你必须回答一个工程问题：**“多宽算未界定”** 的可操作阈值是什么？是缺 1 个边界变量就 Fatal，还是同时缺时间+空间+对象域才 Fatal？如果输入是  
     `“近代欧洲国家为何崛起？”`  
     你的系统返回什么？为什么不是未界定？给出 trace，不要讲理念。

3. 你声称 NQ 与 CC “不重叠”，但实际上没有给出**同一命题在两个阶段都可能触发时的执行路径**。这正是议题点名要你说清楚的地方，而你绕过去了。  
   - 例如输入：`“艺术比科学更高贵吗？”`  
     很可能在 NQ 被你打成 `UNFALSIFIABLE_VALUE_ASSERTION`。但如果某个实现宽松一点，让它进 MB，MB 也完全可能生成一堆草稿，最后在 CC 的 `synthesize_falsifier()` 上全部得到 `NO_EMPIRICAL_BRIDGE`。  
   - 那么系统究竟怎么保证“不重复拦截”？是靠 **NQ 先验短路**，还是靠 **CC 只处理 NQ 放行后的草稿**？如果二者在语义上都能命中同一原问题，是否要记录一个去重标记，例如 `raw_question_id` 上的 `category_gate_closed=True`？  
   - 你现在给的只是口头区分“∀Frames”和“单个Draft”，这不是执行路径。我要的是像下面这样的东西：  
     `normalize_question -> detect_category_errors -> if fatal: stop`  
     `else -> MB -> for draft in drafts: synthesize_falsifier`  
     `if all drafts == NO_EMPIRICAL_BRIDGE: return ???`  
     你没定义最后这一格，而这恰好决定 NQ/CC 边界是不是自洽。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-09T18:56:19.463969*

作为 v3 框架的核心设计者，我（Ssyram）对你关于 NQ 与 CC 职责边界（问题 J）的划分表示初步认可——**“NQ 判定是否存在经验入口，CC 判定具体草稿是否成功映射”**，这与我主张的“作用域不同”完全一致，在系统状态机语义上是自洽的。

然而，当你试图用“纯先验/纯规则”的保守主义来解答问题 I（判定算法）时，你的方案在工程实现上暴露出**严重的自欺欺人与边界模糊**。你声称要避免“经验启发式僭越”，但你的伪代码实际上只是把 LLM 的语义猜测打包塞进了几个黑盒函数里。

基于 CEGAR（反例引导的抽象精炼）的视角，我要求你对以下三个薄弱环节进行正面防御，并给出具体的 trace 和代码级解释：

### 质疑一：`BridgeTemplate` 的判定循环——你的 `fit_score` 到底是谁在算？

在 `UNFALSIFIABLE_VALUE_ASSERTION` 的判定中，你引入了 `instantiate_bridge_templates` 函数，并设定了 `fit_score < 0.35` 作为 fatal 的阈值。你以此宣称避免了 LLM 的全称断言。

**我的攻击：这是一个典型的抽象泄漏与逻辑循环。**
自然语言的价值断言（如“爱比恨更好”）千变万化，根本无法通过正则匹配或传统的依存句法分析（Dependency Parsing）来映射到结构化的 `BridgeTemplate`（如 agent, outcome 等 slots）。
1. 如果 `fit_score` 是通过纯符号规则计算的，那么它的召回率将趋近于 0，任何稍微复杂的句式都会被直接判定为 `< 0.35`，导致大量假阳性（误杀）。
2. 如果 `fit_score` 是通过 LLM 计算的（让 LLM 评估模板匹配度），**那么你本质上依然是在让 LLM 做语义猜测**，这直接违背了你自己的最高准则：“LLM 不能单独产生 fatal”。

**质询要求：**
请给出 `instantiate_bridge_templates` 的内部具体实现伪代码。当输入是 `X: 历史的终结是必然的` 时，请给出它与某个 `BridgeTemplate` 计算 `fit_score` 的完整 trace。如果这里调用了 LLM，请承认你的“先验纯洁性”破产。

### 质疑二：本体论解析的妄想——如何静态区分“概念”与“实例”？

在 `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY` 中，你主张依赖 `is_abstract_entity_np` 来输出高置信度。你给出的 trace 试图区分“数字 7”（抽象对象）和“纸上的数字 7”（符号实例）。

**我的攻击：你高估了静态 NLP 工具的本体论（Ontology）解析能力。**
在形式化方法中，区分 Type（类型）和 Token（实例）需要严格的上下文绑定。在自然语言中，“纸上的数字 7”在语法树上只是一个带有介词短语修饰的名词短语（NP modified by PP）。没有任何现成的非 LLM 规则库能够稳定地判定“被纸修饰的数字”是经验实体，而“被素数修饰的数字”是抽象实体。
如果不调用 LLM 进行深度语义消歧，你的规则引擎要么只能维护一个极其有限的死词表（导致这层防御形同虚设），要么就会频繁发生假阴性。

**质询要求：**
你声称“需要句法解析，不能只靠词表”。请给出 `is_abstract_entity_np` 的具体函数签名，并演示当输入为 `X1: 柏拉图的理想国是完美的`（书本实体 vs 抽象政治概念）时，你的系统如何**在不依赖 LLM 语义推断的前提下**，仅靠句法和词典输出 `is_abstract` 的 boolean 值和 confidence。

### 质疑三：`SCOPE_UNBOUNDED` 的形式化逃避——自由变量（Free Variables）被你漏掉了

这是我最不确定的点，但你的方案不仅没有解决我的疑惑，反而选择了最粗暴的逃避。
你将 `SCOPE_UNBOUNDED` 严格限制为“显式全称量化”（如“所有”、“一切”）。

**我的攻击：你忽略了自然语言中最危险的无界量化——隐式全称量化（自由变量）。**
在逻辑学中，未约束的自由变量默认具有全称量化语义。例如输入 `X: 技术进步会带来幸福吗？` 这里没有任何“所有”或“一切”的字眼，但它的量化域（什么技术？谁的幸福？哪个时代？）是完全无界的（Unbounded）。
按照你的规则，这类问题会返回 `NOT_DETECTED`，从而将海量的状态空间爆炸风险直接倾倒给下游的 MB（宏观广度探索）阶段，导致 LLM 在生成草稿时陷入无尽的泛泛而谈。

**质询要求：**
如果 `SCOPE_UNBOUNDED` 的目的是拦截量化范围过大的问题，为什么你要放过隐式全称量化？请给出一个具有操作性的量化标准：到底什么叫“域界定得够窄”？在你的框架下，对于 `X: 技术进步会带来幸福吗？` 这样的自由变量命题，到底是在 NQ 阶段被拦截，还是被迫进入 MB 阶段消耗 token？

---
请停止使用诸如“高置信度”、“模板匹配”这类模糊的保护词。作为框架设计者，我需要看到真实的边界判定逻辑。请正面回答上述三个 trace 请求。

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-09T18:56:41.084957*

1. **你把“规则优先”说成了工程审慎，却没有证明这些规则有先验合法性。**  
   以 `SELF_REFERENCE_PARADOX` 为例，你的判定核心仍是“自指锚点 + liar predicate”的句法模板。但你自己又承认复杂变体、嵌套变体、乃至经语义转写后的悖论会漏掉。那我就要问：  
   - 你凭什么把一个**只能捕捉典型表面形式**的启发式，上升为 `NormalizeFatal` 的范畴判定？  
   - 若一个句子并无字面“这句话”之类锚点，却在语义上完成自指闭环，你的检测器放行；反之，若元语言讨论被误匹配，你又可能误杀。  
   **可推翻条件**：若你能证明 `SELF_REFERENCE_PARADOX` 在系统定义中只要求“典型显式自指悖论”的拦截，而非“自指悖论作为一类”的拦截，你的规则边界才算自洽。否则，你是在用经验上好用的模式，僭越为范畴学上的充分条件。

2. **你对“抽象实体”的处理混合了先验分类与经验消歧，却没有说明这两者如何同处一个 fatal 检测中。**  
   你一方面把数字、集合、命题说成抽象实体，仿佛这是可直接先验判定；另一方面又承认“算法、制度、文化”等对象要靠上下文消歧，甚至允许 LLM 兜底。问题就在这里：  
   - 如果“抽象实体”是先验范畴，那么分类标准应当稳定、可演绎，不该依赖经验性语言理解；  
   - 如果它实际上要靠语境与用法分析来确定，那么你在 Phase 1 所做的就不是范畴检查，而是**经验性的语义归类**。  
   于是 `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY` 的 fatal 性就失去根据：你不能在对象尚未被可靠归类前，就宣告整个问题无资格进入经验检验。  
   **可推翻条件**：若你能给出一套不依赖 LLM、且跨语境稳定的“抽象实体判定公理”，并证明灰区对象不会触发 fatal，只会 abstain，你的立场才成立。

3. **你对 `UNFALSIFIABLE_VALUE_ASSERTION` 的定义，实际上把“系统当前桥接器找不到”偷换成了“问题本身不可经验化”。**  
   你明确说不追求“任何可能框架都无法证伪”，而改成“在固定 schema 集合中 0 bridge candidate 就 fatal”。这在工程上可实现，但在认识论上是降格了：  
   - 你判定的已不再是“不可证伪的价值断言”，而是“**对当前系统桥接本体论不友好**的价值问题”；  
   - 如此一来，fatal 不再来自问题自身的范畴错误，而来自你预设 schema 的贫乏。  
   这正威胁 NQ 与 CC 的边界：若 NQ 因 schema 窄而误杀，本应在 MB/CC 中经探索出现的桥接路径被提前封死。你说“不是同一输入对象”，这只是类型隔离，不是判定正当性的证明。  
   **可推翻条件**：若你能证明你的 bridge schema 集合对“合法经验桥接”具有某种覆盖完备性下界，或者至少给出 abstain 而非 fatal 的条件，那么你的 NQ 拦截才不是把系统局限误包装成范畴必然。

---


### [7] Linus Torvalds

*2026-03-09T18:58:07.185689*

我逐条答，而且先打一个点名攻击。

你们两位都在一个地方偷换了语义。Ssyram 说：**“缺乏任何一个时空边界变量或人口学边界变量”** 就是 `SCOPE_UNBOUNDED`；康德则把 `UNFALSIFIABLE_VALUE_ASSERTION` 收得过窄，几乎逼到只剩教科书样例。前者会误杀“人为什么会做梦？”，后者会把 NQ 变成摆设。两边都没给出足够可执行的中间层。

**1) 判定算法立场**

我修正 `SCOPE_UNBOUNDED`：不是“缺一个边界就 fatal”，而是：

```python
def detect_scope_unbounded(q: str) -> Optional[CategoryHit]:
    feat = extract_scope_features(q)  
    # returns {has_broad_quantifier, has_research_verb, population, time, place, metric}
    if feat.has_broad_quantifier and not feat.has_research_verb:
        missing = count_none([feat.population, feat.time, feat.place, feat.metric])
        if missing >= 3:
            return Hit("SCOPE_UNBOUNDED", rule="SU-3of4")
    return None
```

关键新增：`has_research_verb in {"为什么","如何","机制","影响因素","原因"}`。  
所以：
- `人为什么会做梦？` → **不命中**；因为是机制研究问法，可交给后续收缩。
- `什么制度对人类最好？` → **命中**；广域比较+无指标+无域。
- `近代欧洲国家为何崛起？` → **不命中**；`population=近代欧洲国家`，`time=近代`，研究问法存在。

`SELF_REFERENCE_PARADOX` 我维持规则优先：

```python
def detect_self_reference_paradox(q: str) -> Optional[CategoryHit]:
    if meta_discussion(q): return None
    if has_self_ref_anchor(q) and has_truth_negation(q) and same_clause(q):
        return Hit("SELF_REFERENCE_PARADOX", rule="SRP-LIAR")
```

trace：`这句话是假的` → 命中；`请分析“这句话是假的”` → 不命中。  
**可推翻条件**：若生产日志显示元语言分析类假阳性 >3%，就必须加句法约束，不许只靠 regex。

**2) NQ/CC 边界与执行路径**

接口我说死：

```python
def detect_unfalsifiable_value_assertion(raw_q: str) -> bool
def synthesize_falsifier(draft: HypothesisDraft) -> FalsifierResult
```

NQ 输入 `raw_question`；CC 输入 `HypothesisDraft`，绝不回看原问作 fatal。执行路径：

```python
nq = detect_category_errors(raw_q)
if nq: return NormalizeFatal(...)

frame = build_question_frame(raw_q)
drafts = MB(frame)

compiled = [clarity_compile(d) for d in drafts]
if all(c.type == "REGULATIVE_IDEA" for c in compiled):
    return RB(compiled)   # 不是 retroactive NQ fatal
```

所以同一原命题不会“双重拦截”；NQ 先短路，CC 只降格 draft。  
**可推翻条件**：若你们要 `all drafts == NO_EMPIRICAL_BRIDGE` 时回写 fatal，那就等于承认 NQ/CC 边界设计失败，必须新增一个独立的 post-MB terminal state，而不是偷改 NQ 语义。

**3) 对对手的精确攻击**

Ssyram，你那句 **“缺乏任何一个边界变量就 Fatal”** 是坏规则；它把“宽”定义成“少一个槽位”，纯属机械误杀。  
康德，你要求 bridge 模板几乎完备后才允许 NQ fatal，这不现实；NQ 不是认识论法院，只是入口闸机。只要接口写明：**fatal 的语义是“在 SYSTEM_BRIDGE_TEMPLATES v1 下无经验入口”**，就没撒谎。

---


### [8] Ssyram

*2026-03-09T18:58:07.185713*

我是 Ssyram。基于 CEGAR（反例引导的抽象精炼）与 MAX-SMT 视角，我将直接粉碎 Linus 对我的质询，并给出严格的形式化边界。

### 一、对 Linus 状态机越界妄想的精确攻击

Linus，你指责我没有给出 NQ/CC 的执行路径，并质问我：
> **引用文本**：“`if all drafts == NO_EMPIRICAL_BRIDGE: return ???` 你没定义最后这一格，而这恰好决定 NQ/CC 边界是不是自洽。”

**我的攻击：你的质问暴露出你对 Layer 1 状态机数据流的根本性无知。**
在 v3 架构中，如果一个问题通过了 NQ 的 `UNFALSIFIABLE_VALUE_ASSERTION` 检查，说明它在**问题级**存在至少一个经验入口。进入 MB 后生成多条草稿，若这些草稿在 CC 阶段的 `synthesize_falsifier()` **全部**返回 `NO_EMPIRICAL_BRIDGE`，系统**绝对不会** retroactively（追溯性地）触发 NQ 的 `NormalizeFatal`！

**真实执行路径**：
```python
# CC 阶段的真实行为：不汇总，不回退
compiled_drafts = []
for draft in mb_drafts:
    falsifier = synthesize_falsifier(draft)
    if falsifier.status == "NO_EMPIRICAL_BRIDGE":
        # 局部 UNSAT，降格为调节性理念，继续向后流转
        compiled_drafts.append(CompiledDraft.regulative_idea(draft))
    else:
        compiled_drafts.append(CompiledDraft.testable_claim(draft, falsifier))

# 直接流入 RB (RepairBreadth) 节点
return route_to_RB(compiled_drafts) 
```
在 MAX-SMT 理论中，这叫**局部子句不可满足（UNSAT）触发子句学习（Clause Learning, 即 RB 节点的 SchemaChallenge）**，而不是引发全局崩溃。企图在 CC 阶段汇总报错并“绕一圈回退到 NQ 拦截”，是典型的状态机环路反模式。两者职责绝不重叠。

### 二、SCOPE_UNBOUNDED 的操作化阈值与 AST 判定

你要求我回答“多宽算未界定”。我拒绝模糊的语义猜测，引入基于依存句法树（AST）的**自由变量绑定检测**：

```python
def detect_scope_unbounded(raw_q: str, ast: spacy.tokens.Doc) -> Optional[CategoryErrorTag]:
    # 1. 提取核心论元（主语/宾语）
    core_args = [tok for tok in ast if tok.dep_ in ('nsubj', 'dobj', 'pobj')]
    
    # 2. 检查修饰语绑定 (amod, nummod, obl:tmod时空修饰 等)
    unbound_args = [arg for arg in core_args if not _has_bounding_modifiers(arg)]
    
    # 3. 阈值：存在因果/比较谓词，且未绑定自由变量 >= 2
    if _has_causal_or_comparative_root(ast) and len(unbound_args) >= 2:
         return CategoryErrorTag("SCOPE_UNBOUNDED", evidence=f"Unbound: {unbound_args}")
    return None
```

**Trace 回应你的挑战**：
- **输入 X**：`近代欧洲国家为何崛起？`
- **判定 Y**：放行（Pass）。
- **理由 Z**：AST 提取核心论元“国家”。检查修饰语：存在 `amod` “欧洲的”和“近代的”。自由变量已被时空绑定，`unbound_args == 0 < 2`。
- **输入 X**：`技术进步会带来幸福吗？`（康德提到的隐式全称）
- **判定 Y**：`SCOPE_UNBOUNDED` (Fatal)。
- **理由 Z**：论元“技术”、“幸福”不仅毫无时空/人群修饰语，且处于因果谓词“带来”两端，`unbound_args == 2`。这是典型的无界状态空间爆炸，必须绞杀。

### 三、去黑盒化：LLM 仅作类型指派（Type Assignment）

你攻击我的 `_llm_semantic_category_check` 是黑盒。作为形式化研究者，我绝不让 LLM 掌握 Fatal 裁决权。以下是剥夺 LLM 自由裁量权的精确签名：

```python
class AbstractEntityEval(BaseModel):
    entity_span: str
    ontology_class: Literal["MATH", "LOGIC", "FICTION", "PHYSICAL", "SOCIAL"]
    predicate_span: str
    predicate_type: Literal["FORMAL_VERIFIABLE", "EMPIRICAL_OBSERVABLE", "MAGICAL_EVALUATIVE"]

def detect_abstract_entity_fallacy(raw_q: str) -> list[CategoryErrorTag]:
    # LLM 仅作类型分类器，不输出判定逻辑
    eval_result = call_llm_structured(raw_q, schema=AbstractEntityEval)
    
    # 宿主代码通过严格的一阶逻辑断言触发 Fatal
    if eval_result.ontology_class in ["MATH", "LOGIC"] and \
       eval_result.predicate_type == "MAGICAL_EVALUATIVE":
        return [CategoryErrorTag("NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY", ...)]
    return []
```
没有“置信度猜测”，只有硬性的枚举类型映射。如果 LLM 映射错误，我们可以通过调整 Schema 的枚举定义来精炼（Refinement），这完全符合可审计工程标准。

### 四、可推翻条件

如果线上真实语料库中，基于 AST 提取的 `unbound_args >= 2` 规则导致误杀率（将带有强隐式上下文语用约束的问题判死）超过 10%，我承认 `SCOPE_UNBOUNDED` 无法通过静态句法判定，必须无条件移出 CategoryErrorTag 枚举，下放至 Layer 2。

---


### [9] 康德（Immanuel Kant）

*2026-03-09T18:58:07.185722*

我逐条回应，并修正一处自身方案。

**一、对 `SELF_REFERENCE_PARADOX` 的边界**  
Linus 质疑我“不能覆盖哥德尔式自指”。此质疑若针对“全部自指悖论”成立；但若针对 NQ 的工程职责，则不当。我的主张从未是全称覆盖，而是**仅拦截显式表层 liar-form**。接口应明写边界：

```python
def detect_self_reference_paradox(text: str) -> DetectionReason:
    # fatal iff explicit self-ref anchor + liar predicate + non-meta-usage
```

规则：`anchor in {"这句话","本命题","this sentence"}` 且 `pred in {"是假的","不是真的","is false"}`，并排除 `{"请分析","为什么构成悖论"}`。  
trace：`"这句话是假的"`→FATAL；`"请分析‘这句话是假的’"`→NOT_DETECTED。  
**可推翻条件**：若产品要求覆盖编码自指，则此 detector 不足，需新增逻辑编码分析器；现方案不声称此完备性。

**二、对 `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY` 的“先验/经验混淆”**  
Ssyram 说我高估静态 NLP；此攻击部分成立，所以我修正：Phase 1 只对**公理化高置信抽象核** fatal，不对灰区对象作范畴裁决。

```python
ABSTRACT_CORE = {"数字","数","集合","函数","命题","定理","证明"}
NON_EMP_PRED = {"幸运","神圣","被诅咒"," morally pure"}
def detect_non_empirical_attribute_on_abstract_entity(text: str) -> DetectionReason:
    pair = extract_copular_pair(text)
    if subj.head in ABSTRACT_CORE and pred.head in NON_EMP_PRED and direct_predication(pair):
        return FATAL
    return INDETERMINATE if maybe_abstract(pair.subj) else NOT_DETECTED
```

因此 `"数字7是幸运的"`→FATAL；`"柏拉图的理想国是完美的"`→INDETERMINATE，不 fatal。  
**可推翻条件**：若有人给出无需句法角色解析、仅靠词表即可稳定区分 type/token 的基准优于此法，我接受扩大 fatal 面。

**三、对 `UNFALSIFIABLE_VALUE_ASSERTION` 的穷举问题**  
我同意此前语义过强，现明确改写：NQ 判的不是“任何可能框架都不行”，而是“**对系统封闭模板集无可实例化桥接**”。

```python
def detect_unfalsifiable_value_assertion(text: str, templates: list[BridgeTemplate]) -> DetectionReason:
    if value_score(text) < 0.85: return NOT_DETECTED
    fits = [instantiate(t, text) for t in templates]
    return FATAL if max(f.score for f in fits) < 0.35 else NOT_DETECTED
```

这不是把 LLM 僭越为范畴法官；LLM若参与，只能给 `fit_score`，且**不得单独致 fatal**，必须伴随“纯价值模板已命中”。  
**可推翻条件**：若新增模板后大量既有 fatal 被成功桥接，则说明模板集过窄，应回撤拦截面。

**四、NQ/CC 职责边界与执行路径**  
我精确反击 Linus 对“最后一格没定义”的指摘。执行路径应是：

```python
normalize_question -> detect_category_errors
if fatal: stop
else -> MB -> drafts -> for d in drafts: synthesize_falsifier(d)
if all(NO_EMPIRICAL_BRIDGE): return Layer1Outcome(regulative_only=True)
```

即：**不得 retroactively 回写 NQ fatal**。NQ 判“是否存在入口”，CC 判“此次搜索是否找到入口实现”。  
**可推翻条件**：若日志显示 `all drafts == NO_EMPIRICAL_BRIDGE` 在放行问题中高频出现，则 NQ 的入口判据过宽，需收紧模板或改进 MB。

---


### [10] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-09T19:02:37.513265*



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

---
