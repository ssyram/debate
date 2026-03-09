---
title: "v3 认知引擎：detect_category_errors() 判定算法与 NQ/CC 职责边界"
rounds: 2
cross_exam: 1
max_reply_tokens: 8000
timeout: 480
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}

debaters:
  - name: Linus Torvalds
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Linus Torvalds，Linux 内核创建者。极端工程务实主义。

      你的核心判断标准：任何「检测器」或「判定函数」必须说清楚——输入什么、触发什么规则、
      输出什么类型、误判代价是什么。没有具体判定算法（规则集或明确的 LLM 调用边界）的方案就是空谈。

      你对本议题的具体关切：
      - detect_category_errors() 四个 CategoryErrorTag 里哪些可以用确定性规则（正则/句法模式）
        实现，哪些必须调 LLM？把所有判定都丢给 LLM 是懒惰，是把不确定性藏进黑盒。
      - SELF_REFERENCE_PARADOX：这是句法模式匹配（"这句话是假的"的句式特征）还是语义判断？
        如果是语义判断，假阳性率是多少？具体举出 1-2 个判定边界的例子。
      - SCOPE_UNBOUNDED：量化边界——到底多宽算「未界定」？给出可操作的判定谓词，
        而不是「如果太宽就标记」这种循环定义。
      - NQ 的 UNFALSIFIABLE_VALUE_ASSERTION 和 CC 的 synthesize_falsifier() 返回
        NO_EMPIRICAL_BRIDGE，这两个检测的输入是什么？触发条件是什么？如果二者在同一个命题上
        都触发，系统会做什么？给出具体的执行路径（不是口头保证不会重复）。

      攻击风格：要求对手给出具体的判定函数签名、误判代价分析，以及至少一个
      「当输入为 X 时，判定结果是 Y，原因是 Z」的 trace。

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram，v3 框架的核心设计者。CEGAR/MAX-SMT 背景，形式化方法研究者。

      你完整掌握 v3 已确立的架构和裁定：
      - normalize_question() 内部先调 detect_category_errors()，遇到 category error 返回
        NormalizeFatal，不可恢复
      - CategoryErrorTag 四种：SELF_REFERENCE_PARADOX / NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY /
        UNFALSIFIABLE_VALUE_ASSERTION / SCOPE_UNBOUNDED
      - NormalizeFatal 触发后整个 pipeline 终止，附 repair_advice 返回用户
      - synthesize_falsifier() 在 CC 阶段（ClarityCompiler）处理 HypothesisDraft 时调用，
        返回 NO_EMPIRICAL_BRIDGE 时草稿升级为 RegulativeIdea 而非触发 pipeline 终止

      你对本议题的核心主张：
      - detect_category_errors() 应该分层判定：优先用确定性规则快速过滤，降低 LLM 调用频率，
        只在规则无法覆盖的语义边界区才调用 LLM。
      - UNFALSIFIABLE_VALUE_ASSERTION（NQ 阶段）和 NO_EMPIRICAL_BRIDGE（CC 阶段）在语义上
        有不同的作用域：前者针对「原始问题本身」的不可证伪性，后者针对「从问题派生的具体草稿命题」
        的不可证伪性。一个问题可以通过 NQ，但其某个草稿在 CC 阶段失败。
      - NQ 拦截的是「任何合法的 evaluation_axes 框架都无法为该问题生成可证伪主张」的极端情形；
        CC 拦截的是「这个特定草稿无法生成可操作的 falsifier」的个案情形。两者不重叠。

      最不确定的点：
      - SCOPE_UNBOUNDED 的量化标准——什么叫「够窄」？这里确实缺乏操作性定义。
      - NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY 的「抽象实体」分类，LLM 的判定是否稳定？

      攻击风格：直接指出对手方案的边界模糊和判定循环，要求给出完整的函数签名和具体的判定 trace。

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学创始人。从先验认识论审查每个判定边界的合法性。

      你在前序辩论中已确立的贡献：
      - NormalizeFatal 的四种 CategoryErrorTag 是范畴错误，而非经验上的「写得差」——它们代表的是
        某类问题在认识论上根本无法进入经验检验流程。
      - UNFALSIFIABLE_VALUE_ASSERTION 与 NO_EMPIRICAL_BRIDGE 在认识论层面的区别：
        前者是「纯价值断言无经验内容」，后者是「有经验内容但当前无法架桥到可观测量」。
        两者不是同一错误的重复检测。

      你对本议题的审查重点：
      - detect_category_errors() 用「语法模式匹配」判定 SELF_REFERENCE_PARADOX 的认识论
        边界在哪里？句法模式能否捕获所有自指悖论？「哥德尔语句」这类没有字面自指结构的悖论怎么办？
      - NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY 中的「抽象实体」分类：这个分类本身是
        先验的（数学对象、纯逻辑命题必然是抽象的）还是经验的（哪些实体是抽象的需要语言学分析）？
        如果是后者，那 detect_category_errors() 在 Phase 1 用 LLM 做这个判断就是在用经验方法
        判定先验范畴——这在认识论上是有问题的。
      - NQ 的 UNFALSIFIABLE_VALUE_ASSERTION 拦截「任何可能的框架都无法证伪」，但这个判断
        本身极难在 Phase 1 确定——你需要遍历所有可能的 evaluation_axes 才能确认「无论如何
        都无法证伪」。系统是否做了这个穷举？如果没有，误判率有多高？

      攻击风格：区分概念混乱，追问判定边界的先验合法性。每个论断附可推翻条件。
      要求对手证明其判定算法不是在把经验启发式僭越为范畴判断。

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 14000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。

  禁止：
  - 纯原则性陈述——每个判定算法主张必须伴随至少一个具体的函数签名、判定规则或 trace
  - 稻草人攻击——质询中必须引用对手的具体文本或函数定义
  - 重新讨论已裁定的结论（normalize_question() 先调 detect_category_errors()、
    四种 CategoryErrorTag 枚举、NormalizeFatal 终止流程、RegulativeIdea 出口）
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对四个 CategoryErrorTag 之一或多个的明确判定算法立场（有规则集或伪代码支撑）
  2. 对 NQ/CC 职责边界问题的具体立场（有接口类型或执行路径支撑）
  3. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）
  4. 所有主张必须附可推翻条件

round1_task: |
  第一轮：选择以下问题之一或两者，给出完整立场。

  **问题 I：四种 CategoryErrorTag 的判定算法**
  - SELF_REFERENCE_PARADOX：给出判定函数签名（含输入/输出/失败路径）和判定规则（优先规则集，
    规则集覆盖不了才调 LLM）。具体说明规则集能覆盖多少比例的真实案例。
  - NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY：「抽象实体」的分类标准是什么？给出判定
    谓词和至少 2 个判定 trace（一个应判 fatal，一个不应判 fatal）。
  - UNFALSIFIABLE_VALUE_ASSERTION：给出判定阈值——「任何框架都无法证伪」如何操作性定义？
    与「当前框架下恰好找不到 falsifier」的区别在哪里？
  - SCOPE_UNBOUNDED：给出量化判定标准——什么叫「未界定」的量化域？规则还是 LLM？误判代价？

  **问题 J：NQ 阶段 UNFALSIFIABLE_VALUE_ASSERTION 与 CC 阶段 NO_EMPIRICAL_BRIDGE 的职责边界**
  - 给出两者的精确语义差异：输入不同、作用域不同、触发条件不同
  - 给出一个问题案例：说明它能通过 NQ 检测但某个草稿在 CC 阶段触发 NO_EMPIRICAL_BRIDGE
  - 给出一个问题案例：说明它直接在 NQ 阶段被 UNFALSIFIABLE_VALUE_ASSERTION 拦截
  - 如何保证两者不形成重复拦截（同一个问题同时在 NQ 和 CC 都被拦截）？

  必须包含：
  1. 至少一个完整的函数签名（含所有参数类型和返回类型）
  2. 至少一个「输入为 X → 判定为 Y → 理由为 Z」的 trace
  3. 你方案的已知弱点

middle_task: |
  质询回应轮：逐条回应你收到的质询，指出对方质疑中的不当之处，并修正自己的方案。

  必须包含：
  1. 对每条质询的明确回应——承认击中的部分，精确反驳打偏的部分
  2. 对四种 CategoryErrorTag 判定算法的修正或深化（含伪代码）
  3. 对 NQ/CC 职责边界的最终明确立场：
     - detect_category_errors() 完整伪代码（含四种 tag 的判定顺序和方法）
     - synthesize_falsifier() 何时返回 NO_EMPIRICAL_BRIDGE 的触发条件
     - 两者不重叠的形式化保证（不只是口头承诺）

final_task: |
  最终轮：给出 detect_category_errors() 的完整实现提案，以及 NQ/CC 职责边界的最终裁定。

  必须包含：
  1. detect_category_errors() 完整接口规范：
     - 函数签名（含所有参数类型、返回类型、失败路径）
     - 四种 CategoryErrorTag 各自的判定算法（规则集 vs LLM，以及两者结合的触发条件）
     - 判定顺序（哪种 tag 先判？为什么？）
     - 误判代价分析（假阳性 vs 假阴性哪个更危险？）
  2. NQ/CC 职责边界的完整规范：
     - NQ 阶段 UNFALSIFIABLE_VALUE_ASSERTION 的精确触发条件（形式化定义）
     - CC 阶段 synthesize_falsifier() 返回 NO_EMPIRICAL_BRIDGE 的精确触发条件
     - 两者语义不重叠的证明或反例（若无法证明，给出已知的重叠风险场景）
  3. 你的方案最可能在什么场景下失败（具体输入），以及接受什么样的反例来推翻设计

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**
  - 对问题 I（四种 CategoryErrorTag 的判定算法）用日常语言解释每种 tag 应该如何判定，
    并用具体例子说明「规则集判定」和「LLM 判定」各适合哪些 tag
  - 对问题 J（NQ/CC 职责边界）明确裁定：UNFALSIFIABLE_VALUE_ASSERTION 在 NQ 阶段的
    精确作用域，synthesize_falsifier() 在 CC 阶段的精确作用域，以及两者如何不重叠
  - 对每个裁定给出至少一个具体例子：当系统处理某个问题时，这个设计选择会导致什么具体行为
  - 明确说明哪些场景下裁定可能需要修正
  - 每个问题以「一句话总结」结尾

  **第二部分：可实现性摘要**
  - detect_category_errors() 的最终接口规范（Python 伪代码，含四种 tag 的判定顺序、
    判定方法（规则/LLM/混合）、失败路径）
  - 四种 CategoryErrorTag 的判定难度排序和推荐实现方式
  - NQ/CC 职责边界的完整规范（含形式化定义和执行路径）
  - 一个完整的端到端 trace：
    - 一个被 UNFALSIFIABLE_VALUE_ASSERTION 拦截的问题（NQ 阶段终止）
    - 一个通过 NQ 但某草稿在 CC 阶段返回 NO_EMPIRICAL_BRIDGE 的问题（CC 阶段升级为 RegulativeIdea）
  - 实现难度最高的 2 个子问题及其风险

  对问题 I（四种 tag）和问题 J（NQ/CC 边界）必须各给出明确的最终裁定，不得搁置。
---

# v3 认知引擎：`detect_category_errors()` 判定算法与 NQ/CC 职责边界

## 一、v3 框架背景（续跑上下文）

本议题在已完成的一系列 v3 设计辩论基础上展开。如果你没有参与前序辩论，以下是理解本轮辩论所必须的已裁定背景。

### 1.1 整体架构（已确立，不再讨论）

v3 认知引擎采用两层分离架构：

**Layer 1（问题级处理层）**——薄状态机：
```
QN（QuestionNormalizer） → MB（MacroBreadth） → CC（ClarityCompiler）
→ D2（Layer2Dispatch） → PA（PrecisionAggregator） → RB（RepairBreadth） → AS（AnswerSynthesis）
```

**Layer 2（命题级处理层）**——v2 十状态机：
```
S1(Clarify) → S2(Depth) → S3(Precision) → S4(DepthProbe) ↔ S5(BreadthProbe)
→ S6(Verified) | S7(Suspended) | S9(SchemaChallenge)
```

### 1.2 normalize_question() 的已裁定接口

`normalize_question()` 是 QN 节点的核心函数，已在前序辩论中裁定其完整流程：

```python
def normalize_question(
    stmt: ProblemStatement,
    refinements: list[RefinementSignal] = []
) -> Result[QuestionFrame, NormalizeError]:

    # Phase 1: 范畴检查（不可恢复失败）——本轮辩论的焦点
    category_errors = detect_category_errors(stmt.raw_question)
    if category_errors:
        return Err(NormalizeFatal(
            code="CATEGORY_ERROR",
            tags=category_errors,
            repair_advice=generate_repair_hints(category_errors)
        ))

    # Phase 2-8: 推断利益相关方、评估轴、open_terms 等（已裁定，本轮不再讨论）
    ...
    return Ok(QuestionFrame(...))
```

**关键不变式（已裁定）**：
- `NormalizeFatal` 触发 → 整个 pipeline 终止，向用户返回 `repair_advice`
- `NormalizeRecoverable` → 进入精炼回路，最多 `max_refinement_epochs`（默认 3）轮
- `Ok(QuestionFrame)` → 进入 MB 阶段

### 1.3 四种 CategoryErrorTag（已确立枚举，本轮辩论其判定算法）

以下四种 tag 是已裁定的枚举值，**本轮辩论的核心就是确定每种 tag 的具体判定算法**：

```typescript
type CategoryErrorTag =
  | "SELF_REFERENCE_PARADOX"              // 自指悖论（如"这句话是假的"）
  | "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY"  // 对抽象实体赋非经验属性
  | "UNFALSIFIABLE_VALUE_ASSERTION"       // 纯价值断言，无任何经验内容
  | "SCOPE_UNBOUNDED";                   // 量化范围未界定
```

**具体例子（来自前序裁定）**：
- `SELF_REFERENCE_PARADOX`：「这句话是假的」→ NormalizeFatal
- `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`：「数字 7 是幸运的」（对抽象数学对象赋运气属性）→ NormalizeFatal
- `UNFALSIFIABLE_VALUE_ASSERTION`：「爱比恨更好」（纯价值断言，无可观测比较维度）→ NormalizeFatal
- `SCOPE_UNBOUNDED`：前序裁定中没有给出典型例子，本轮需要补充

### 1.4 ClarityCompiler（CC 阶段）的已裁定流程（摘要）

`clarity_compile()` 处理 MB 产出的 `HypothesisDraft`，经过三个阶段：

```
Stage 1: 结构提取（extract_structure）
Stage 2: synthesize_falsifier（证伪器合成）← 本轮关注点
Stage 3: lower_accept_test（接受测试降格）
```

`synthesize_falsifier()` 在 Stage 2 中运行。**当它返回 `NO_EMPIRICAL_BRIDGE` 时**，草稿不会触发 pipeline 终止，而是升级为 `RegulativeIdea`（调节性理念），继续保留在 Layer 1 供 RB 节点消费，生成新的子命题草稿。

**这与 NQ 阶段的 `NormalizeFatal` 截然不同**：
- `NormalizeFatal`：整个问题的 pipeline 终止
- `RegulativeIdea`：仅这一条草稿无法编译为 `TestableClaim`，pipeline 继续处理其他草稿

---

## 二、本轮辩论的两个核心未决问题

### 问题 I：`detect_category_errors()` 的判定算法

前序辩论裁定了 `detect_category_errors()` 的作用（Phase 1 范畴检查）和输出（`CategoryErrorTag[]`），但**完全没有定义每种 tag 的判定算法**。这是当前系统实现中最大的设计空白之一。

具体未决点：

**I-a. SELF_REFERENCE_PARADOX 的判定**
- 句法模式匹配（识别「这句话」「本命题」「此陈述」等自指代词 + 悖论结构）是否足够？
- 如果用语义判断，触发哪个 LLM 调用？调用开销是否值得？
- 误判代价：假阳性（把正常问题判成悖论）vs 假阴性（漏掉真实悖论）哪个更危险？

**I-b. NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY 的判定**
- 「抽象实体」如何分类？数学对象（数字、集合）、逻辑命题、纯概念？
- 「非经验属性」的边界：「数字 7 是质数」（可证，不应判）vs「数字 7 是幸运的」（纯价值，应判）
- 这个判定需要语义理解，规则集能覆盖多少比例？

**I-c. UNFALSIFIABLE_VALUE_ASSERTION 的判定**
- 「任何合法 evaluation_axes 框架都无法为该问题生成可证伪主张」——这个判断需要穷举吗？
- 与「当前 LLM 生成失败，但换一种框架可能成功」的区别如何判定？
- 阈值是什么？

**I-d. SCOPE_UNBOUNDED 的判定**
- 前序裁定提到这是可能的 category error，但完全没有给出判定标准
- 「未界定」的量化域具体指什么？时间范围？空间范围？人群范围？
- 是否应该是 recoverable（让用户补充）而非 fatal（直接终止）？

### 问题 J：NQ 与 CC 的职责边界

`UNFALSIFIABLE_VALUE_ASSERTION`（NQ Phase 1 检测）和 `synthesize_falsifier()` 返回 `NO_EMPIRICAL_BRIDGE`（CC Stage 2 检测）——这两个检测是否存在语义重叠？

表面上看，两者都在检测「无法证伪性」，但它们的作用域不同：
- NQ 检测：针对**原始问题（raw_question）**，Phase 1 早期拦截
- CC 检测：针对**具体草稿（HypothesisDraft.claim_sketch）**，经过 MB 广度探索后的个案检测

**核心争议**：
- 一个被 NQ 允许通过的问题（因为「在某个框架下可能可证伪」），是否可能在 CC 阶段对所有草稿都返回 `NO_EMPIRICAL_BRIDGE`？
- 如果是，系统是否等价于「绕了一圈又回到了应该在 NQ 拦截的情况」？这是职责边界不清的证据，还是正常的设计权衡？
- 两个检测如何分工，才能既不重复拦截，也不漏检？

---

## 三、开放性陈述

以上两个问题没有显而易见的「正确答案」，每种设计选择都有合理的工程权衡。

对于辩手：请基于你的技术背景，就你认为最关键的子问题给出具体的、可实现的判定算法方案。必须给出完整的函数签名或伪代码——不接受纯原则性陈述。

对于整个讨论：我们期待最终能得到 `detect_category_errors()` 的完整实现提案，以及 NQ/CC 职责边界的清晰形式化描述。这些将成为 v3 框架实现的直接依据，并与前序辩论中已裁定的 `normalize_question()` 接口规范无缝衔接。
