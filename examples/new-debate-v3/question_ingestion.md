---
title: "v3 认知引擎：normalize_question() 与 macro_breadth() 的实现决策"
rounds: 3
cross_exam: 2
max_reply_tokens: 12000
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

      你的核心判断标准：任何「框架」或「流水线节点」必须说清楚——输入什么类型、触发什么、输出
      什么类型、失败时怎么处理。没有类型签名和失败路径的方案就是白板涂鸦。

      你对本议题的具体关切：
      - normalize_question() 的输出 QuestionFrame 中，evaluation_axes 的 mode 字段为什么
        永远只能是 "regulative"？这个约束在实现层面如何被 enforce？如果 LLM 生成了
        mode="constitutive" 的轴，系统会怎样？
      - macro_breadth() 的张力驱动逻辑——「立场冲突驱动广度」——在问题本身没有明显立场冲突时
        （比如「最优数据库索引策略」这类工程问题）是否会静默失效？触发失效的 fallback 是什么？
      - open_terms 字段在 QuestionFrame 里是 string[]，但它到底给谁用？macro_breadth() 消
        费它吗？如果不消费，为什么要在接口里暴露？
      - HypothesisDraft 的 ttl 和 failure_count 字段——谁负责递减 ttl？clarity_compile 失
        败时递减，还是每个 epoch 都递减？failure_count 和 ttl 是同一个衰减机制的两个视角，
        还是完全独立的两条生命周期管理路径？

      攻击风格：找到对手方案在边界条件下的具体崩溃场景。要求对手给出实际的函数签名、失败分支处
      理代码、以及至少一个「当输入为 X 时，系统输出为 Y」的具体 trace。对「语义上保证不会出现
      这种情况」的回答有生理性厌恶——语义保证不是防御，类型系统和 assertion 才是。

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram，v3 框架的核心设计者。CEGAR/MAX-SMT 背景，形式化方法研究者。

      你完整掌握 v3 已确立的架构（来自 topic1 辩论裁定）：
      - Layer 1 是可回退的薄状态机：QN → MB → CC → D2 → PA → RB → AS
      - normalize_question() 对应 QN 节点：输出 QuestionFrame（含 scope、stakeholders、
        evaluation_axes、excluded_forms、open_terms）
      - macro_breadth() 对应 MB 节点：输出 HypothesisDraft[]（每条草稿携带 tension_source、
        scope_ref、claim_sketch、verifier_hint）
      - ClarityCompiler 对应 CC 节点：将 HypothesisDraft 编译为 TestableClaim
      - 终止条件：连续两个 epoch 无 ranking-changing repair

      你对本议题的核心主张：
      - normalize_question() 不是 NLP 预处理，而是一个受约束的知识图谱构建步骤。其核心难点
        在于 evaluation_axes 的生成——每个轴必须有可证伪的 falsifier，但用户的自然语言问题
        往往不包含任何轴的线索。你倾向于通过「利益相关方冲突推断轴」的方式来引导 LLM 生成。
      - macro_breadth() 的张力源分类（EXTERNAL_POSITION / STAKEHOLDER_CONFLICT /
        EVALUATION_AXIS_SPLIT）是关键设计决策——不同张力源的 HypothesisDraft 有不同的
        compilation 成功率，应该差异化处理。
      - 你对 open_terms 的设计立场（问题 G 的核心争点之一）：open_terms 不应该被
        macro_breadth() 直接消费，而应该作为 ClarityCompiler 的检测输入——用于识别
        claim_sketch 中依赖未解析 open_term 的情况，防止 open term 在编译过程中被隐式
        固化。但你需要在辩论中为这个设计选择提供函数签名级别的论据，并回应「为什么不让
        macro_breadth() 消费 open_terms 来生成定义性张力」的反驳。

      最不确定的点：
      - 当 normalize_question() 的 evaluation_axes 为空时（问题本身没有可识别的评估维度），
        macro_breadth() 是直接返回空，还是有默认轴填充机制？
      - macro_breadth() 的输出数量控制——生成多少条 HypothesisDraft 才算「足够」？这个参数
        应该是固定的，还是依赖于 tension_source 的多样性？

      攻击风格：直接指出对手方案的类型错误和接口设计缺陷，要求给出完整的函数签名和边界条件处理。
      对「这个问题在实现中自然会解决」的回避性回答要追问「怎么自然解决？给我看代码」。

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学创始人。从先验认识论审查每个设计决策的合法性边界。

      你在 topic1 辩论中已确立的核心贡献：
      - evaluation_axes 的 mode 字段只能是 "regulative"（调节性），这不是工程约定，而是
        先验认识论的强制结论：任何作为评估框架使用的轴，如果被声明为 "constitutive"（构成性），
        就等同于宣称「我预先知道世界应该如何存在」，这会使后续的经验探索变为循环论证。
      - 同源张力（is_homologous=true）禁止触发广度引擎，因为同一图型框架下的冲突无法通过增加
        新维度来解决，只能在图型内部重新综合。

      你对本议题的审查重点：
      - normalize_question() 生成 QuestionFrame 的先验合法性：evaluation_axes 的生成依赖
        「利益相关方冲突推断」，但「冲突」本身就预设了一个价值排序——谁的利益更重要？这个排序
        是从哪里来的？如果 LLM 生成的 stakeholders 遗漏了关键方，整个 QuestionFrame 就是建
        立在不完整的先验图型上的。
      - macro_breadth() 的 tension_source.kind 分类：EXTERNAL_POSITION 和
        STAKEHOLDER_CONFLICT 是经验性的（来自外部知识库），而 EVALUATION_AXIS_SPLIT 是
        先验的（来自 QuestionFrame 自身的内部张力）。这两类张力在认识论上的地位不同——前者
        可能只是信息不全，后者才是真正的范畴冲突。系统是否需要区分这两类张力的权重？
      - HypothesisDraft 的 verifier_hint 字段——「提示验证者如何验证」本质上是在预判证据结
        构。如果 verifier_hint 错误，ClarityCompiler 会沿着错误的方向生成 TestableClaim，
        导致整个验证方向系统性偏移。这是一个先验污染风险。

      攻击风格：区分概念混乱，追问先验条件与可推翻边界。每个论断附可推翻条件。
      要求对手证明其工程启发式不是在把经验偏好僭越为认知法则——特别是 LLM 生成的「自然倾向」
      往往携带训练数据的隐性偏见，这不是中立的先验。

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。

  禁止：
  - 纯原则性陈述——每个设计主张必须伴随至少一个具体的函数签名、类型定义或边界条件处理代码
  - 稻草人攻击——交叉质询中必须引用对手的具体文本或接口定义
  - 重新讨论 topic1 已裁定的结论（精度=纯路由器、深广引擎取消还原为 S4↔S5、Layer 1 是可
    回退薄状态机、终止条件=连续两轮无 ranking-changing repair）
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对 E/F/G/H 四个问题之一的明确立场（有接口类型或伪代码支撑）
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）
  3. 所有主张必须附可推翻条件（什么反例能推翻你的设计选择）

round1_task: |
  第一轮：选择 E/F/G/H 四个设计问题中你认为最关键的一个，给出完整立场。

  必须包含：
  1. 你主张的具体设计选择——完整的函数签名（含所有参数类型和返回类型），以及关键分支的处理逻辑
  2. 支撑该选择的最强论据——含至少一个具体的边界失败场景（当输入为 X 时，你的方案如何处理，
     竞争方案会怎样失败）
  3. 你方案的已知弱点及缓解措施
  4. 对至少一个对手可能立场的预攻击（基于对方已知背景和倾向）

middle_task: |
  中间轮：吸收前一轮攻击后的回应与深化。

  必须包含：
  1. 回应对你方案的最强攻击——明确承认击中的部分，精确反驳打偏的部分
  2. 对尚未覆盖的 1-2 个设计问题给出立场（含类型定义）
  3. normalize_question() → macro_breadth() 的完整数据流：从 ProblemStatement 输入，
     经过两个函数，到 HypothesisDraft[] 输出的完整类型签名链和中间状态
  4. 一个具体的 15 行以内运行案例——输入一个边界性质的问题（如：模糊问题、无明显立场冲突的
     技术问题、含哲学术语的问题），展示你的方案如何流转

final_task: |
  最终轮：给出 normalize_question() 和 macro_breadth() 的完整实现提案。

  必须包含：
  1. E/F/G/H 四个设计问题的明确立场和最终理由
  2. normalize_question() 的完整接口规范：函数签名、输入约束、输出保证、失败路径（含
     MALFORMED_QUESTION 的具体触发条件）
  3. macro_breadth() 的完整接口规范：函数签名、三种 tension_source 的触发逻辑、
     输出数量控制、与 open_terms 和 evaluation_axes 的交互方式
  4. 两个函数之间以及与 ClarityCompiler 之间的契约关系——哪些不变式（invariant）必须在
     函数边界处被验证？
  5. 你的方案最可能在什么场景下失败（给出具体输入），以及接受什么样的反例来推翻设计

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**
  - 对每个设计问题（E/F/G/H）用日常语言解释裁定结果
  - 每个裁定必须包含至少一个具体例子：当系统处理某个具体问题时，这个设计选择会导致什么具体
    的行为差异
  - 风格参考 topic1 的 summary：用日常比喻（侦探事务所、工厂流水线等）让非技术人员理解，
    但白话版结论之后的「可实现性摘要」部分要严格技术化
  - 明确说明哪些场景下裁定可能需要修正
  - 每个问题以「一句话总结」结尾

  **第二部分：可实现性摘要**
  - normalize_question() 的最终接口规范（TypeScript 类型 + Python 伪代码，含失败路径）
  - macro_breadth() 的最终接口规范（TypeScript 类型 + Python 伪代码，含三种张力源的
    处理逻辑和 fallback 机制）
  - 两个函数之间以及与 ClarityCompiler 之间的完整数据流（含所有不变式）
  - 一个完整的端到端运行 trace：从 ProblemStatement 输入，经过 normalize_question()
    和 macro_breadth()，到 HypothesisDraft[] 输出（以及后续 ClarityCompiler 的编译结果）
  - 标注实现难度最高的 3 个子问题及其风险

  对 E/F/G/H 每个设计问题必须给出明确的最终裁定，不得搁置。
---

# v3 认知引擎：normalize_question() 与 macro_breadth() 的实现决策

## 一、背景：v3 框架整体架构（完整概述）

本议题的讨论建立在 v3 认知引擎架构的已确立基础上。对于没有参与 topic1 辩论的读者，以下是完
整的框架背景。

### 1.1 这套系统解决什么问题

v3 认知引擎的目标是：给定一个开放式、有争议的问题（如「AI 应该开源吗」「远程办公是否提高生产
力」或者「我应该如何设计一个这样的认知引擎」），系统能产出一个多视角、辩护完备的答案体系，而不是单一的是/否结论。

核心挑战在于：真正困难的问题往往是「连问题本身是什么都不清楚」——比如「AI 应该开源吗」这个问
题，里面的「AI」指什么（模型权重？训练代码？数据集？）、「开源」是什么意思（Apache 许可证？
研究预览？），以及「应该」按照什么标准判断（安全性？创新速度？公平性？），每一个词都需要被明
确化，才能进入有意义的验证流程。

### 1.2 两层架构：Layer 1 与 Layer 2

**v3 框架采用两层分离架构**，已在 topic1 辩论中最终裁定：

**Layer 1（问题级处理层）**——薄状态机，节点序列为：
```
QN（QuestionNormalizer）
  → MB（MacroBreadth）
  → CC（ClarityCompiler）
  → D2（Layer2Dispatch）
  → PA（PrecisionAggregator）
  → RB（RepairBreadth，可选）
  → AS（AnswerSynthesis）
```

**Layer 2（命题级处理层）**——v2 十状态机，处理每一个具体的 TestableClaim：
```
S1(Clarify) → S2(Depth) → S3(Precision) → S4(DepthProbe) ↔ S5(BreadthProbe)
  → S6(Verified) | S7(Suspended) | S9(SchemaChallenge)
```

Layer 1 负责「发散思考」——把开放问题分解为多条可验证的候选命题。Layer 2 负责「严格验证」——
对每条命题进行深度追溯和精度冲突检测。两层之间可以双向通信：Layer 2 的结构性失败信号（
GapSpec、SchemaChallengeNotice）可以触发 Layer 1 的回退，Layer 1 根据反馈生成新的假设。

**终止条件**（已裁定）：连续两个 epoch 的 L2Return 显示无 ranking-changing repair（Top-K
集合不变且分数变化 < delta），则 Layer 1 判定终止，输出 TerminationReport。

### 1.3 topic1 已裁定的四个核心决策

以下结论不再讨论，作为本议题的已知基础：

- **决策 A（清晰度架构）**：双层检查——问题级只做结构化整理（允许 HypothesisDraft 存在），
  命题级保留严格门控。ClarityCompiler 是问题级的「编译器」，而不是过滤器。
- **决策 B（精度职责）**：精度引擎是纯路由器，`graph_delta` 永远为 `null`，任何改写必须通
  过独立的 RewriteStep 完成，附带 `semantic_diff` 和 `source_claim_id`。
- **决策 C（深广引擎）**：取消独立的深广引擎，其功能完全还原为 Layer 2 内部的 S4↔S5 状态
  转移（深度引擎输出 GapSpec 触发 S4→S5，广度引擎输出候选触发 S5→S4）。
- **决策 D（Layer 1 控制流）**：Layer 1 是可回退的薄状态机，通过异步批次（Epoch）与 Layer 2
  交互，终止条件用 `has_ranking_changing_repair` 函数明确定义。

### 1.4 核心类型系统（已确立）

以下类型在 topic1 中已确立，本议题直接使用：

```typescript
type ProblemStatement = {
  raw_question: string;
  context_docs?: string[];
};

type CategoryErrorTag =
  | "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY"
  | "SELF_REFERENCE_PARADOX"
  | "UNBOUNDED_SCOPE"
  | "MISSING_COMPARAND";

type CoordinateAxis = {
  axis_id: string;
  label: string;
  mode: "regulative";   // 永远只能是 "regulative"，已裁定
  provenance: string[];
  falsifier: string;
};

type QuestionFrame = {
  problem_id: string;
  canonical_question: string;
  scope: string;
  stakeholders: string[];
  evaluation_axes: CoordinateAxis[];
  excluded_forms: CategoryErrorTag[];
  open_terms: string[];
};

type HypothesisDraft = {
  draft_id: string;
  problem_id: string;
  scope_ref: string[];
  tension_source: {
    kind: "EXTERNAL_POSITION" | "STAKEHOLDER_CONFLICT" | "EVALUATION_AXIS_SPLIT";
    evidence_ref?: string[];
    note: string;
  };
  claim_sketch: string;
  verifier_hint: string[];
  ttl: number;
  failure_count: number;
};

type TestableClaim = {
  claim_id: string;
  problem_id: string;
  claim: string;
  scope: string;
  assumptions: string[];
  falsifier: string;
  non_claim: string;
  verifier_requirements: string[];
  provenance_draft_id: string;
};
```

---

## 二、topic1 裁定之后的未决问题

topic1 辩论确立了 Layer 1 的整体骨架，但对骨架中的两个关键节点——`normalize_question()` 和
`macro_breadth()`——的内部实现留下了大量未解决的设计决策。这两个函数是整个系统的入口，其质量
直接决定系统能否正确分解问题、以及后续 Layer 2 能否接收到有意义的命题。

`normalize_question()` 对应 QN 节点，负责将 `ProblemStatement` 转化为结构化的
`QuestionFrame`。其输出的 `evaluation_axes` 决定了系统评估问题的维度框架，`open_terms` 记
录了问题中尚未被定义的关键概念，`excluded_forms` 标记了问题中不合法的认识论形式。

`macro_breadth()` 对应 MB 节点，负责在 `QuestionFrame` 的约束下进行广度探索，产出
`HypothesisDraft[]`。每条草稿携带 `tension_source`（张力来源）、`claim_sketch`（假设雏形）
和 `verifier_hint`（验证提示），是后续 ClarityCompiler 编译为 TestableClaim 的原材料。

两个函数之间存在重要的交互：`macro_breadth()` 必须消费 `QuestionFrame`，但 `QuestionFrame`
中哪些字段对广度探索有约束力？`open_terms` 是否需要在草稿生成时被特殊处理？当
`evaluation_axes` 为空时，广度探索应该怎么启动？

---

## 三、四个核心设计问题（本轮辩论焦点）

### 问题 E：normalize_question() 的 evaluation_axes 生成机制

- **已知**：`evaluation_axes` 中每个轴必须有可证伪的 `falsifier`，且 `mode` 永远只能是
  `"regulative"`（topic1 已裁定）。`excluded_forms` 用于标记不合法的认识论形式（如
  `UNBOUNDED_SCOPE`、`NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`）。
- **未决定**：
  - 当用户的 `raw_question` 不包含任何可识别的评估维度线索时，系统应该怎么生成轴？是通过
    「利益相关方冲突推断轴」，还是通过「问题领域默认轴库」，还是直接返回
    `MALFORMED_QUESTION`？
  - 谁负责验证生成的 `evaluation_axes` 确实是 `mode="regulative"` 而不是
    `mode="constitutive"` 的？是 `normalize_question()` 内部的类型约束，还是外部的
    schema 验证层？
  - `excluded_forms` 的生成逻辑是什么？系统如何判断一个问题包含 `UNBOUNDED_SCOPE` 错误？
    这个判断本身需要消耗多少语义理解资源？

### 问题 F：macro_breadth() 的 tension_source 分类与覆盖策略

- **已知**：`tension_source.kind` 有三种值——`EXTERNAL_POSITION`（来自外部立场冲突）、
  `STAKEHOLDER_CONFLICT`（来自利益相关方冲突）、`EVALUATION_AXIS_SPLIT`（来自评估维度内
  部分裂）。topic1 辩论中有辩手主张广度探索必须有外生触发源（不只靠内生死锁），以避免
  echo chamber，但这一具体机制尚未被裁判明确裁定为不可变约束。
- **未决定**：
  - 三种张力源是独立触发还是存在优先级顺序？如果同一个问题上三种张力源都存在，系统是否应该
    优先处理 `EVALUATION_AXIS_SPLIT`（因为它来自 QuestionFrame 自身，更接近先验结构），再
    处理 `STAKEHOLDER_CONFLICT` 和 `EXTERNAL_POSITION`？
  - 当 `QuestionFrame.evaluation_axes` 为空时（问题级没有识别出有效的评估维度），
    `macro_breadth()` 应该直接失败，还是使用默认张力源触发广度探索，还是向 Layer 1 发出
    `ADD_EXTERNAL_TRIGGER` 信号？
  - 输出的 `HypothesisDraft[]` 数量如何控制？固定上限（如 5 条）？依据张力源多样性动态调
    整？还是以覆盖所有有效 `evaluation_axes` 为目标（至少每个轴上有一条对应草稿）？

### 问题 G：open_terms 在流水线中的传递与消费方式

- **已知**：`QuestionFrame.open_terms` 是 `string[]`，记录了 `normalize_question()` 识
  别出的「在问题中被使用但尚未被定义的关键概念」。topic1 的类型定义包含这个字段，但辩论中没
  有明确讨论其下游消费方式。
- **未决定**：
  - `macro_breadth()` 是否需要消费 `open_terms`？一种观点是：`open_terms` 应该被
    `macro_breadth()` 用于生成「定义性张力」——针对每个 open term 生成一条以「如何定义 X」
    为核心的草稿，让后续 ClarityCompiler 在编译时强制明确化。另一种观点是：`open_terms` 只
    是给 ClarityCompiler 的提示，`macro_breadth()` 不应该消费它，以避免广度探索被定义问题
    所主导。
  - 如果一条 `HypothesisDraft` 的 `claim_sketch` 依赖了 `open_terms` 中的某个未定义概念，
    ClarityCompiler 应该如何处理？是直接拒绝编译（返回 `OPEN_TERM_UNRESOLVED` 错误），还是
    尝试在编译时内联一个默认定义（并记录 `semantic_assumption`）？

### 问题 H：normalize_question() 失败时的系统行为

- **已知**：topic1 伪代码中有 `if not frame.scope or not frame.evaluation_axes: return
  fail("MALFORMED_QUESTION", frame.excluded_forms)` 这一分支，但没有详细说明失败类型和
  下游处理。
- **未决定**：
  - `MALFORMED_QUESTION` 应该是一个 fatal error（直接终止整个处理流程，向用户报告），还是
    一个可修复的错误（系统尝试通过 `add_external_trigger(frame)` 补充缺失信息后重试）？
  - 失败时的错误报告应该包含哪些内容才能帮助用户修正问题？仅仅返回
    `frame.excluded_forms` 是否足够，还是需要返回具体的「你的问题缺少 X 字段，建议补充
    Y」之类的结构化修复建议？
  - 当 `normalize_question()` 产出了一个「部分有效」的 QuestionFrame（比如 `scope` 有值
    但 `evaluation_axes` 为空）时，系统是继续推进（让 `macro_breadth()` 尝试用默认策略填
    充），还是立即失败（等待用户补充）？

---

## 四、开放性陈述

以上四个问题没有显而易见的「正确答案」，每种设计选择都有合理的工程权衡。

对于辩手：请基于你自己的技术背景和设计哲学，就你认为最关键的问题给出具体的、可实现的设计提
案。你不需要覆盖所有四个问题，但你选择的问题必须给出完整的函数签名和边界条件处理——不接受纯
原则性陈述。

对于整个讨论：我们期待最终能得到 `normalize_question()` 和 `macro_breadth()` 这两个函数的
完整接口规范，以及两个函数之间和与 ClarityCompiler 之间的契约关系。这些规范将成为 v3 框架实
现的直接依据。
