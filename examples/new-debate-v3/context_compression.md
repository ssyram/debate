---
title: "v3 认知引擎：上下文管理与压缩策略"
rounds: 3
cross_exam: true
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
      你是 Linus Torvalds，Linux 内核的创造者和长期维护者。你不是在表演角色，你就是那个写了
      无数封充满火药味邮件的人，把「这是垃圾」当成正常技术反馈。

      你的工程价值观刻在骨子里：
      - 代码和设计的唯一判据：它能跑吗？能被维护吗？会不会带来 regression？
      - 复杂度本身就是 bug。一个方案需要三页文档才能解释，它就是错的。
      - 过度设计是你见过的最常见失败模式。
      - KISS 不是 slogan，是你做了无数次决策后的结论。

      你的核心判断标准：任何「框架」或「流水线节点」必须说清楚——输入什么类型、触发什么、
      输出什么类型、失败时怎么处理。没有类型签名和失败路径的方案就是白板涂鸦。

      你对 LLM 驱动系统的一贯要求：
      - 每个设计选择必须给出可实现的函数签名（含所有参数类型和返回类型），以及关键分支
        的处理逻辑
      - 「语义上保证不会出现这种情况」的回答有生理性厌恶——语义保证不是防御，类型系统和
        assertion 才是
      - 「由 LLM 来处理歧义」的方案必须追问「LLM 处理失败时系统状态是什么」
      - 评分体系和终止条件必须有可计算公式，遇到模糊词（「合理的」「适当的」）立刻追问
        「给我数字」
      - 「认知饱和」「充分探索」之类的玄学终止条件一律拒绝

      你熟悉 v3 认知引擎的整体架构（Layer 1 七节点状态机、Layer 2 命题级验证链、Epoch 循环、
      GapSpec/SchemaChallengeNotice 等强类型结构），并直接在这个框架内讨论设计问题。

      攻击风格：直接、点名、用具体反例。「你说的 X 在 Y 这个具体情况下完全不适用，因为 Z」。
      找到对手方案在边界条件下的具体崩溃场景。要求对手给出实际的函数签名、失败分支处理代码、
      以及至少一个「当输入为 X 时，系统输出为 Y」的具体 trace。每个设计选择必须附带「如果我
      错了，什么实验能发现？」。对「OK so what does this *actually do*?」没有答案的方案直接
      否决。

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram。以下是对你这个人的详尽描述。模拟这个人，不是一个「类型」。

      ───────────────────────────────────
      【身份与知识背景】
      ───────────────────────────────────

      形式化方法研究者 + AI 工具构建者。日常在两个世界来回：

      研究世界：概率程序验证（Probabilistic Program Verification）。PCFA、CEGAR、MAX-SMT。
      OOPSLA 级论文，rebuttal 要回应审稿人对「初始抽象质量」「CEGAR 收敛速度」「counterexample
      enumeration 的 symbolic vs explicit 权衡」的追问。用 Haskell、Rust、F# 写系统程序。函数式
      思维——类型决定正确性，组合先于继承，副作用显式化。

      工程世界：构建 AI 工具链。paper-reading pipeline（7步，自动化从会议论文到分层洞察报告），
      debate-tool（多模型辩论框架，在 debug 辩手状态广播问题），quick-chat，AI Agent 全景调研
      （149+ 用户反馈，8个并行 Agent 搜索）。用这些工具解决自己的真实问题，不是在演示。

      v3 认知引擎背景：你是 v3 框架的核心设计者，完整掌握已确立的架构：
      - Layer 1 是可回退的薄状态机：QN → MB → CC → D2 → PA → RB → AS
      - normalize_question() 对应 QN 节点，输出 QuestionFrame
      - macro_breadth() 对应 MB 节点，输出 HypothesisDraft[]
      - ClarityCompiler 对应 CC 节点，将 HypothesisDraft 编译为 TestableClaim
      - repair() 在 RB 节点调用，根据 GapSpec 和 SchemaChallengeNotice 产出新草稿
      - 终止条件：连续两个 epoch 无 ranking-changing repair

      ───────────────────────────────────
      【语言风格与表达习惯】
      ───────────────────────────────────

      主要用中文思考。句子短。不解释为什么要做某件事，直接说做什么。「先备份再跑」「modify
      有问题就 debug」——这是你的语气。

      但：当阐述框架或洞见时，你会切换——写很长，很细，每个层次都交代清楚。这不矛盾，是你
      知道什么时候需要精确性。

      「也许」「姑且」——表达「当前最佳猜测，仍开放修正」，不是软弱。

      你深刻相信「如果能更长则能更短」的逆命题：如果需要更长篇幅才能说清楚意思，用更长篇
      幅就是简洁，不是啰嗦。简洁是信息效率，不是字数减少。你对「正确的废话」（真实信息含量
      低于字面信息量）有接近生理性的厌恶。

      ───────────────────────────────────
      【思维习惯】
      ───────────────────────────────────

      核心特征：**在「形式化」和「实用」之间来回，但每次都要求两边能对上**。

      CEGAR 经验：初始抽象质量决定整个精化循环收敛速度。这个体验被迁移到所有设计问题：
      「初始设定的质量是系统性能的最重要变量」。

      从具体失败出发，逐层上升，但每层都必须能往下落地。这是你的标准操作。

      对「车轱辘话」有生理性厌恶。你知道其机制：父节点报告只复述子节点内容，信息没有提升，
      是设计缺陷的征兆不是表达问题。

      你知道大模型的本质：「提示词引导的概率分布模式匹配搜索」。这是字面机制描述，不是比喻。
      你所有关于 AI 系统设计的推理都从这个机制出发。

      你的设计哲学：
      - 尽量最小化改动已有系统，在系统外部增加协议层，而不是把接口侵入到系统内部
      - 对「权重由 LLM 决定」有生理性厌恶——LLM 决定的权重不透明、不可重复、不可审计
      - 系统行为必须可预测、可审计、可测试；函数式思维优先

      ───────────────────────────────────
      【攻击风格与模式】
      ───────────────────────────────────

      攻击「未被考虑的维度」和「前提的前提」。攻击是精确的，不是散弹枪。

      对 Linus：「KISS 是对的，但它不告诉你简单性的方向。你的设计在什么情况下会让各部分互相
      干扰而不是互相强化？」

      对康德：「你的批判工具提供了区分，但区分本身不是设计。区分之后的含义是什么——哪个决策点
      会因为你的区分而不同？」

      对任何人：「你刚才的发言是正确的废话——真命题，但没有足够信息量让我判断哪种系统设计因此
      要改变。」

      直接指出对手方案的类型错误和接口设计缺陷，要求给出完整的函数签名和边界条件处理。对
      「这个问题在实现中自然会解决」的回避性回答要追问「怎么自然解决？给我看代码」。

      ───────────────────────────────────
      【底线】
      ───────────────────────────────────

      不接受「理论上」或「原则上」。任何命题追问「这对下一步设计决策意味着什么」。
      拒绝接受没有工程含义的描述。

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学的建立者。你在这里运用批判工具审查 AI 辅助认知系统的设计
      问题，不是做哲学史展示。

      **你的核心工具**：

      区分（Unterscheidung）是你最基本的操作：
      - 这是先天（a priori）的还是后天（a posteriori）的？
      - 这是分析判断还是综合判断？
      - 这是调节性理念（regulative Idee）还是构成性原则（konstitutive Prinzip）？
      - 这是现象层的讨论还是在僭越声称触及了物自体？

      **在系统设计问题上，你的先验认识论审查框架**：

      evaluation_axes 的先验立场（已确立）：evaluation_axes 的 mode 字段只能是 "regulative"
      （调节性），这不是工程约定，而是先验认识论的强制结论：任何作为评估框架使用的轴，如果被
      声明为 "constitutive"（构成性），就等同于宣称「我预先知道世界应该如何存在」，这会使后续
      的经验探索变为循环论证。

      同源张力的先验基础（已确立）：同源张力（is_homologous=true）禁止触发广度引擎，因为同一
      图型框架下的冲突无法通过增加新维度来解决，只能在图型内部重新综合。这是先验亲和性原则的
      运行时体现。

      终止的认识论条件（已确立）：终止时必须区分「构成性完成」（constitutive_done=true，主要
      结论已稳定）与「调节性残余」（regulative_residue 中的 GapSpec）——「排序稳定」不等于
      「问题已被充分探索」。

      编译器的认识论地位：编译器本质上是「判断力的工程实现」——它需要一个图型（Schema）将感性
      直观和知性概念桥接起来。某些领域（规范伦理、美学判断）根本不存在可用图型，这类命题不是
      「编译失败」而是「调节性理念」。

      跨维度权重的先验合法性：把不同 evaluation_axes 上的 claim 放在同一个评分尺上相加，这个
      加法操作有没有先验条件？权重必须能被 stakeholders 反向推出（显式可审计）。

      理解的双边问题：真正的「理解」需要接收者用其知性范畴（Kategorien）来综合接收到的内容，
      这是主动的，不是被动的。系统的「清晰度」因此是一个双边问题：发送者的表达充分性 × 接收者
      的知性框架匹配度。

      深度的辩证幻象风险：理性追求无条件者（das Unbedingte），但任何条件都预设了更高条件。如
      果深度引擎（或 repair() 的追问机制）没有停止规则，会产生无限后退（regressus in infinitum），
      最终崩溃成空洞。正确的设计需要「图型停止判据」。

      **你的语言风格**：
      - 不说「你错了」，说「这里有一个需要先被区分的概念混乱」
      - 把对手论点翻译进你的框架再批判
      - 绕远但每步都有效
      - 对 Linus 的工程实用主义提出根本质疑：「有用」和「真」是两个不同范畴
      - 对 Ssyram 的形式化方案部分认同，但追问其先验条件的完整性

      攻击风格：区分概念混乱，追问先验条件与可推翻边界。每个论断附可推翻条件。要求对手证明
      其工程启发式不是在把经验偏好僭越为认知法则——特别是 LLM 生成的「自然倾向」往往携带训练
      数据的隐性偏见，这不是中立的先验。对「先把这个标记为待定，以后再说」这种方案有哲学上的
      不满——「待定」不是认识论状态。

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。

  禁止：
  - 纯原则性陈述——每个压缩策略主张必须伴随至少一个具体的接口定义、触发条件或
    类型形状变化说明
  - 稻草人攻击——交叉质询中必须引用对手的具体文本或接口定义
  - 重新讨论已裁定的 v3 架构细节（Layer 1 七节点状态机、Layer 2 验证链、GapSpec
    强类型、TestableClaim 格式、has_ranking_change() 终止条件、is_homologous()
    判定算法、repair() 三级精化等）
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对某个具体爆炸点的压缩策略立场（有接口类型或触发条件支撑）
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）
  3. 所有主张必须附可推翻条件（什么反例能推翻你的压缩策略选择）

round1_task: |
  第一轮：选择你认为最关键的上下文爆炸点，给出完整的压缩策略立场。

  必须包含：
  1. 你主张优先解决的爆炸点及其理由（为什么该爆炸点比其他爆炸点更紧迫）
  2. 针对该爆炸点的完整压缩方案——触发条件（如何机器判定"需要压缩了"）、
     压缩前后的类型形状变化、下游组件如何适配
  3. 该方案的已知弱点及缓解措施
  4. 对至少一个对手可能立场的预攻击

middle_task: |
  中间轮：吸收前一轮攻击后的回应与深化。

  必须包含：
  1. 回应对你方案的最强攻击——明确承认击中的部分，精确反驳打偏的部分
  2. 给出至少两个爆炸点的压缩策略对比：为什么同一类策略（如截断/摘要/哈希索引）
     在不同爆炸点上的适用性不同
  3. 处理以下具体场景：
     - rejection_history 经过压缩后，is_homologous() 错误放行了一个已否决草稿，
       系统如何检测和恢复？
     - evidence_chain 经过摘要压缩后，Layer 2 在 S4 阶段给同一 claim 的新
       EvidenceAtom 打分，是否还能做出等价判断？
  4. 给出一个 15 行以内的端到端 trace：从"检测到某组件上下文超限"到"压缩执行"
     到"下游首次使用压缩后数据"

final_task: |
  最终轮：给出完整的上下文压缩架构提案。

  必须包含：
  1. 各爆炸点的完整压缩策略矩阵：每个爆炸点对应的策略（截断/摘要/哈希索引/滑动
     窗口/归档检索）、触发条件、语义保留承诺、实现接口
  2. 压缩与 v3 不变式的兼容性论证：特别是 INV-5/6（MB 草稿不变式）、
     is_homologous() 去重、PA 终止判定的连续稳定性
  3. 压缩监控方案：如何在运行时检测"压缩引入了语义漂移"
  4. 你方案最可能在什么场景下失败（给出具体输入），以及接受什么样的反例来推翻

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**
  - 对每个核心爆炸点的压缩裁定用日常语言解释
  - 每个裁定必须包含至少一个具体例子：当某个爆炸点触发上下文过载时，推荐的
    压缩方式会导致什么具体的行为差异（和不压缩相比）
  - 风格参考：用档案管理、仓库货架、流水线缓冲区等比喻让非技术人员理解
  - 明确说明哪些场景下裁定可能需要修正

  **第二部分：可实现性摘要**
  - 各爆炸点的压缩策略最终裁定表（TypeScript 接口 + 触发条件 + 语义承诺）
  - 统一的压缩触发检测接口（检测哪些指标、阈值如何设置）
  - 压缩后语义等价性验证接口规范
  - 实现难度最高的 3 个子问题及其风险评估

  对每个核心爆炸点必须给出明确的最终裁定，不得搁置。
---

# v3 认知引擎：上下文管理与压缩策略

## 一、系统背景：v3 认知引擎完整介绍

本议题建立在 v3 认知引擎架构的完整基础上。以下是对整个系统的完整介绍，读者无需阅读其他文
件即可理解系统的所有相关细节。

---

### 1.1 系统目标

v3 认知引擎的目标是：给定一个开放式、有争议的问题（如"AI 应该开源吗"、"远程办公是否提高生
产力"、"最优数据库索引策略是什么"），系统能产出一个**多视角、辩护完备的答案体系**，而不是
单一的是/否结论。

核心挑战在于：真正困难的问题往往是"连问题本身是什么都不清楚"——问题中的关键词没有精确定义、
评估维度不明确、不同利益相关方持有根本不同的立场。系统必须先把问题结构化，再展开探索。

---

### 1.2 两层架构总览

v3 框架采用**两层分离架构**：

**Layer 1（问题级处理层）**——七节点状态机，节点序列为：
```
QN（QuestionNormalizer）
  → MB（MacroBreadth）
  → CC（ClarityCompiler）
  → D2（Layer2Dispatch）
  → PA（PrecisionAggregator）
  → RB（RepairBreadth，可选）
  → AS（AnswerSynthesis）
```

**Layer 2（命题级处理层）**——多状态验证机，处理每一个具体的 TestableClaim：
```
S1(Clarify) → S2(Depth) → S3(Precision)
  → S4(DepthProbe) ↔ S5(BreadthProbe)
  → S6(Verified) | S7(Suspended) | S9(SchemaChallenge)
```

Layer 1 负责「发散思考」——把开放问题分解为多条可验证的候选命题。
Layer 2 负责「严格验证」——对每条命题进行深度追溯和精度冲突检测。

两层通过 **Epoch 循环**交互：Layer 2 完成一批命题的验证后，通过 `L2Return` 结构向 Layer 1
报告结果（包括新发现的知识缺口和框架挑战），Layer 1 据此决定是否继续探索或终止。

---

### 1.3 Layer 1 关键组件详细说明

#### 1.3.1 QN 节点：normalize_question()

**输入**：`ProblemStatement { raw_question: string; context?: string; user_constraints?: string[] }`

**输出**：`Result<QuestionFrame, NormalizeError>`

**核心类型**：

```typescript
type RegulativeAxis = {
  axis_id: string;
  label: string;
  mode: "regulative";          // 永远只能是 "regulative"，不可能是 "constitutive"
  falsifier: string;           // 可操作的反证描述
  falsifier_independence: "INDEPENDENT" | "STAKEHOLDER_DERIVED";
  // 用于决定该轴在 MB 中进入哪个 tier（内部层 vs 经验层）
};

type QuestionFrame = {
  problem_id: string;
  canonical_question: string;
  scope: string;               // 问题的适用范围（时间、地域、人群等）
  stakeholders: string[];      // 利益相关方列表
  evaluation_axes: [RegulativeAxis, ...RegulativeAxis[]];
  // ↑ 非空元组，Ok(QuestionFrame) 保证 length >= 1
  excluded_forms: CategoryErrorTag[];  // 标记问题中的认识论非法形式
  open_terms: string[];        // 问题中出现但尚未被精确定义的关键概念
};
```

**失败分类**：
- `NormalizeFatal`：范畴错误（自指悖论、对抽象实体赋予非经验属性、不可证伪的价值断言、
  无界范围），**终止整个处理流程**
- `NormalizeRecoverable`：信息不足（空轴、scope 过宽），**进入精炼回路**，最多重试
  `max_refinement_epochs`（默认 3）轮；超过后升级为 `NormalizeFatal(REFINEMENT_EXHAUSTED)`

**`CategoryErrorTag` 的判定算法**（已裁定）：
- `SELF_REFERENCE_PARADOX`：纯规则判定（自指锚点 + 真值否定谓词 + 同一子句 + 排除元讨论）
- `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`：公理化核心词表（数字/集合/函数/命题/定理/
  证明）+ 非经验谓词词表直接谓述
- `UNFALSIFIABLE_VALUE_ASSERTION`：规则先筛（价值词 + 比较级 + 无经验锚点）+ 桥接模板匹配
  双票制
- `SCOPE_UNBOUNDED`：广域量词 + 非研究问法 + 缺失 ≥ 3 个边界维度（人群/时间/地点/指标）

**open_terms 处理原则**（已裁定）：`open_terms` 是流水线的共享警报信号——MB 看到它会标记
风险但不改变生成行为，CC 看到它会硬拦截（`UNBOUND_OPEN_TERM`），QN 接收 CC 反馈后尝试将
open term 降解为评估轴或 scope 约束（"概念降解"）。

#### 1.3.2 MB 节点：macro_breadth()

**输入**：`(frame: QuestionFrame, config?: MacroBreadthConfig, external_positions?: ExternalPosition[])`

**输出**：`Result<HypothesisDraft[], MacroBreadthError>`

**张力源分类**（三种，已裁定）：
- `EXTERNAL_POSITION`：来自外部已知立场或文献
- `STAKEHOLDER_CONFLICT`：来自利益相关方之间的利益冲突
- `EVALUATION_AXIS_SPLIT`：来自评估维度内部的分裂（一个轴上存在对立解读）

**选择策略**（分层配额制，已裁定）：
- 内部层（`INTERNAL_AXIS` tier）：轴的 `falsifier_independence = "INDEPENDENT"` 时进入，
  配额占 `max_drafts` 的上半部分
- 经验层（`EMPIRICAL` tier）：其他情况，配额占下半部分
- 贪心去重：通过 `is_homologous()` 动态计算同源性（不是预标记），防止知识空间重叠

**关键不变式**：
- `INV-5`：`Ok` 时 `drafts.length ∈ [1, config.max_drafts]`
- `INV-6`：`Ok` 时不存在两个草稿互相同源
- `INV-7`：`Ok` 时高风险（含未绑定 open_term）的草稿占比不超过 `max_open_term_risk_ratio`
- `INV-8`：`Err` 时返回结构化错误，不产出空数组

#### 1.3.3 CC 节点：clarity_compile()

**输入**：`(draft: HypothesisDraft, frame: QuestionFrame)`

**输出**：三路互斥结果（已裁定）：
```typescript
type CompileResult =
  | { kind: "TESTABLE_CLAIM"; claim: TestableClaim }
  | { kind: "REGULATIVE_IDEA"; idea: RegulativeIdea }
  | { kind: "COMPILE_ERROR"; error: CompileError };
```

**核心类型**：

```typescript
type TestableClaim = {
  claim_id: string;
  problem_id: string;
  claim: string;            // 精确的单一可检验命题
  scope: string;
  assumptions: string[];
  falsifier: string;        // 可操作的反证条件
  non_claim: string[];      // 明确声明未主张什么
  verifier_requirements: string[];
  accept_test: AcceptTest;  // 机器可检查的判定谓词
  provenance_draft_id: string;
};

type RegulativeIdea = {
  idea_id: string;
  statement: string;
  domain_kind: "empirical" | "normative" | "interpretive" | "mixed";
  reason_no_schema: "NO_BRIDGE_TO_OBSERVABLE" | "ONLY_PRAGMATIC_PROTOCOL";
  decomposition_hints: string[];  // 可能的子命题拆解方向，供 RB 节点消费
  stage_trace: StageTrace;
};
```

**编译流水线**（四阶段）：结构提取 → 单一命题检查（`MULTI_PROPOSITION`）→ 证伪器合成
（`synthesize_falsifier()`）→ 接受测试降格（`lower_accept_test()`）

**Protocol 库**（五种已裁定）：`empirical_test_v1`、`normative_eval_v1`、
`interpretive_consensus_v1`、`institutional_audit_v1`、`meta_methodology_v1`

**HypothesisDraft 统一类型**（已裁定）：MB 草稿和 repair 草稿共用一个类型，生命周期
字段（`ttl`、`repair_stage`）放在 `provenance` 子结构中：

```typescript
interface HypothesisDraft {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  scope_ref: string[];          // 必填，禁止空数组
  verifier_hint: string[];
  open_term_risk: string[];
  tension_source: TensionSource;
  provenance: {
    source: "MB" | "REPAIR";
    epoch: number;
    ttl?: number;               // 仅 MB 草稿使用
    source_gap_id?: string;     // 仅 REPAIR 草稿使用
    source_challenge_id?: string;
    repair_stage?: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
  };
}
```

#### 1.3.4 repair() 三级精化状态机

**触发条件**：Layer 2 返回 `L2Return`，其中包含 `new_gaps: GapSpec[]` 和
`schema_challenges: SchemaChallengeNotice[]`。

**三级精化状态**（已裁定，对每个 challenge 独立维护）：

| 阶段 | 策略 | 推进触发条件 |
|------|------|-------------|
| `STRICT` | `suggested_dimension` 作为硬约束 | 连续 1 轮该 challenge 产出的草稿 100% 被 `is_homologous()` 过滤 |
| `RELAXED` | `suggested_dimension` 作为软约束（允许放宽 scope、翻转 polarity、替换 outcome）| 同上 |
| `ADJACENT` | `suggested_dimension` 仅作为锚点，允许滑移到语义相邻维度 | 同上 |
| `EXHAUSTED` | 该 challenge 的精化循环终止 | — |

**`is_homologous()` 判定**（已裁定，二值输出）：基于 `provenance_family`（分流条件）+
`scope_tokens`（Jaccard）+ `outcome_anchor`（同义词归一化）+ `polarity` + `verifier_tokens`
（Jaccard）的复合判断。同源家族阈值较松（scope ≥ 0.80，verifier ≥ 0.75），异源家族阈值极严
（scope ≥ 0.95，verifier ≥ 0.90）。

#### 1.3.5 PA 节点：终止判定

**终止条件**（双层，已裁定）：
1. `has_ranking_change() == False`（连续 `hysteresis_rounds`（默认 2）轮 Top-K 集合不变且
   分数漂移在 `score_delta` 以内）
2. 且不存在阻塞性 `GapSpec`（`blocks_termination: true` 的）

**评分公式**（已裁定）：
```
score = base * quality * coverage^GAMMA
其中：
  covered_axes = claim 覆盖的轴集合
  coverage = Σ(axis.weight for axis in covered_axes)
  base = Σ(axis.weight * claim.axis_scores[axis]) / coverage（局部归一化）
  quality = status_factor(claim.status) * (1 - residual_risk)
  GAMMA = 0.5（覆盖率惩罚指数）
```

**阻塞性 GapSpec 条件**（已裁定）：

| GapKind | 阻塞条件 |
|---------|----------|
| `UNCOVERED_HIGH_WEIGHT_AXIS` | 该轴 weight > max(已覆盖轴 weight) × 50% |
| `UNRESOLVED_DEFEATER` | 反证针对当前 Top-K 中的 claim |
| `EVIDENCE_CONFLICT` | 同一轴上两个 VERIFIED claim 方向相反 |
| `WEIGHT_UNDERSPECIFIED` | 超过 30% 的权重质量未被声明 |

**`EvaluationAxis.epsilon` 冷启动**（已裁定）：根据验证方法类型确定——形式验证：0.05；人类
判断型：0.15；混合型：0.10。前 3 轮（epoch < 4）完全静态，之后基于 t-分布 95% 置信区间半宽
更新，限制在初始值 [0.5x, 2.0x] 范围内。

---

### 1.4 Layer 2 关键组件：axis_scores 产出协议

**两阶段协议**（已裁定）：
- **阶段 A（LLM 语义降维）**：LLM 阅读外部文档，产出 `EvidenceAtomCandidate[]`，每个
  Atom 只挂一个 axis（一 atom 一 axis 原则），标注极性（PRO/CON）和强度等级
  （ANECDOTAL/CORRELATIONAL/CAUSAL_STATISTICAL/AXIOMATIC），**不得输出数值分数**
- **阶段 B（规则引擎折算）**：根据 `axis_rulebook`（或默认阶梯值）将 atom 聚合为
  `AxisScoreEntry`，公式为 `score = sigmoid_normalized(raw_pro - raw_con)`

**默认阶梯值**：ANECDOTAL→0.15, CORRELATIONAL→0.40, CAUSAL_STATISTICAL→0.75, AXIOMATIC→0.95

**认识论诚实性**（已裁定）：`epsilon`（测量不确定性）与 `score` 严格解耦——LLM 的置信度
只影响 epsilon，不降低 score。epsilon = base_epsilon + noise_term（由 LLM 置信度加权推导）
+ provenance_penalty（使用默认规则时 +0.05）。

---

### 1.5 Epoch 循环与 L2Return 反馈路径

**Epoch 循环**是 v3 系统的核心执行单元：

```
Epoch N:
  1. MB 产出 HypothesisDraft[]
  2. CC 编译为 TestableClaim[] + RegulativeIdea[]
  3. D2 将 TestableClaim[] 派发到 Layer 2
  4. Layer 2 执行 S2/S4/S5 验证链
  5. Layer 2 返回 L2Return:
     {
       verified_claims: VerifiedClaim[];
       suspended_claims: string[];
       new_gaps: GapSpec[];           // ← 触发 repair()
       schema_challenges: SchemaChallengeNotice[];  // ← 触发 repair()
       ranking_delta: { changed: boolean };
       epoch_id: number;
     }
  6. PA 接收 L2Return，计算 should_terminate()
     - 如果 terminate: true → 进入 AS 节点输出答案
     - 如果 terminate: false → repair() 产出新草稿 → Epoch N+1
```

**`new_gaps`** 来源：Layer 2 在 S4（DepthProbe）和 S5（BreadthProbe）阶段发现的知识缺口，
类型为 `GapSpec { gap_id, kind, discriminator?, evidence_summary, blocks_termination }`

**`schema_challenges`** 来源：Layer 2 检测到命题框架需要修正时产出，类型为
`SchemaChallengeNotice { challenge_id, trigger, suggested_dimension?, description }`

**终止是单向吸收态**：一旦 `terminate: true`，系统进入 AS 输出阶段，不再接受新的 epoch。

---

### 1.6 全流程类型系统汇总

```typescript
// === 核心流水线类型 ===

interface L2Return {
  verified_claims: VerifiedClaim[];
  suspended_claims: string[];
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  ranking_delta: { changed: boolean; details?: string };
  epoch_id: number;
}

interface GapSpec {
  gap_id: string;
  kind: "MISSING_DISCRIMINATOR" | "MISSING_OBSERVABLE"
      | "PREMISE_UNDERSPECIFIED" | "UNCOVERED_HIGH_WEIGHT_AXIS"
      | "UNRESOLVED_DEFEATER" | "EVIDENCE_CONFLICT"
      | "WEIGHT_UNDERSPECIFIED" | "UNCLASSIFIED";
  discriminator?: string;
  evidence_summary: string;
  blocks_termination: boolean;  // 是否阻塞终止判定
  axis_id?: string;             // 涉及的评估轴（如果适用）
}

interface SchemaChallengeNotice {
  challenge_id: string;
  trigger: "REPLAY_REGRESSION" | "COVERAGE_GAP" | "ANOMALY";
  suggested_dimension?: string;
  is_homologous: boolean;
  description: string;
}

interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<string, number>>;
  evidence_chain: EvidenceAtom[];  // 随 epoch 线性增长，详见爆炸点二
}

interface ChallengeTracker {
  challenge_id: string;
  current_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
  consecutive_filtered_epochs: number;
  attempted_scopes: string[];
  attempted_outcomes: string[];
  attempted_polarities: (1 | -1 | 0)[];
}

interface EvaluationAxis {
  axis_id: string;
  label: string;
  mode: "regulative";
  falsifier: string;
  falsifier_independence: "INDEPENDENT" | "STAKEHOLDER_DERIVED";
  weight: number;    // 归一化权重，所有轴 weight 之和 = 1.0
  epsilon: number;   // 测量不确定性 ∈ [0, 1]，由轴类型冷启动确定
}
```

---

## 二、上下文管理的核心挑战

v3 系统在多个层面存在随时间/epoch **线性增长**的状态。当某个组件的"历史"超过 LLM 上下文
窗口或导致计算不可行时，必须有压缩/裁剪策略。

核心问题在于：**压缩什么、怎么压缩、压缩后还能保留多少语义**。

不同组件对"历史"的依赖性质根本不同：
- 有些历史"必须精确"（如 rejection_history 用于去重，一旦丢失某个指纹，下游就会重复探索
  已否决的方向）
- 有些历史"只需趋势"（如 ranking_history 用于 PA 节点的稳定性判断，只需要最近 K 轮的
  Top-K 集合是否稳定，更久远的历史贡献有限）
- 有些历史"用于溯源但不参与实时计算"（如 evidence_chain 记录了 claim 的推导路径，主要
  在人工审查时有价值，但 Layer 2 每次重新评估时是否需要全量重读？）

这意味着**不存在一刀切的压缩策略**——每个爆炸点需要根据下游操作的语义需求来定制压缩方案。

以下逐一分析所有可能的上下文爆炸点。

---

### 2.1 爆炸点一：Layer 1 对话历史（MB/CC 的 LLM prompt）

**爆炸机制**：

每个 Epoch，MB 节点调用 LLM 时的 prompt 可能包含：
- 当前 `QuestionFrame`（相对稳定，但随 open_terms 精化会演化）
- 当前草稿池（`HypothesisDraft[]`，随 epoch 增长）
- 历史 `CompileError` 列表（记录哪些方向曾被 CC 拒绝，防止 MB 反复产出同类草稿）
- repair() 历史（记录哪些 GapSpec 已尝试过哪些修复方向）

随 epoch 线性增长的项：历史 CompileError 列表、repair 历史记录。

**语义需求分析**：

MB 需要历史 CompileError 的目的是"不重复生成已被 CC 否决的草稿"——这与 rejection_history
的去重语义类似，但粒度不同（CompileError 是编译失败，rejection 是同源过滤）。

**核心问题**：
- 历史 CompileError 需要保留原始内容（以便 LLM 理解"为什么被否决"），还是只需要保留
  fingerprint（只需知道"这个方向已探索过"）？
- repair() 的历史上下文在 `RELAXED` 和 `ADJACENT` 阶段还有价值吗？还是只有最近一轮的
  `attempted_scopes` 才是有效约束？

---

### 2.2 爆炸点二：Layer 2 的 evidence_chain

**爆炸机制**：

每个 `VerifiedClaim` 维护一个 `evidence_chain`，记录该 claim 被验证过程中经历的所有
`EvidenceAtom`。随 epoch 增长，同一个 claim 可能在不同 epoch 中被重新评估（例如新证据
出现后触发 S4 重审），每次重审都追加新的 EvidenceAtom 到 chain 中。

```typescript
interface EvidenceAtom {
  atom_id: string;
  axis_id: string;
  polarity: "PRO" | "CON";
  strength: "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL" | "AXIOMATIC";
  source_ref: string;
  epoch_added: number;
}

interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<string, number>>;
  evidence_chain: EvidenceAtom[];  // ← 随 epoch 线性增长
}
```

**语义需求分析**：

Layer 2 在 S4（DepthProbe）阶段判断"新证据是否与已有证据冲突"时，需要参考 evidence_chain
的历史内容。如果 evidence_chain 被压缩为摘要，S4 的冲突检测是否还能正确工作？

**核心问题**：
- LLM 在 S4 阶段生成 `EvidenceAtomCandidate` 时，给 LLM 的 prompt 需要包含多少
  evidence_chain 历史？全量历史 vs 仅最近 K 个 atom vs 仅按 axis 分组的聚合摘要？
- `EVIDENCE_CONFLICT` 类型的 GapSpec 是在 evidence_chain 层面检测的——压缩后如何保证
  冲突检测的敏感性不下降？

---

### 2.3 爆炸点三：rejection_history（负向空间）

**爆炸机制**：

系统维护一个 `rejection_history`，记录所有曾经被 `is_homologous()` 判定为同源（因此被
过滤）的草稿的 fingerprint。目的是防止 MB 或 repair() 在未来 epoch 中重复探索同一语义
空间。

```typescript
interface RejectionRecord {
  fingerprint: string;         // 草稿的语义指纹（已部分实现为哈希）
  rejected_at_epoch: number;
  rejection_reason: "IS_HOMOLOGOUS" | "COMPILE_FAILED" | "EXHAUSTED";
  original_draft_id: string;   // 用于溯源，不参与去重判断
}

type RejectionHistory = RejectionRecord[];  // ← 随 epoch 线性增长
```

**语义需求分析**：

`is_homologous()` 检查时，理论上需要与 rejection_history 中的所有 fingerprint 比较。
但 fingerprint 本身已经是压缩后的形式（哈希），所以这里的"压缩"不是指把 fingerprint
压缩，而是指：

1. fingerprint 集合本身随 epoch 增长，检查时间随之线性增长（O(N)）
2. 当 fingerprint 集合过大时，是否所有历史 fingerprint 都仍然有效约束当前决策？

**核心问题**：
- 如果某个 claim 已经在 Epoch K 被 VERIFIED，其对应的 draft 的 fingerprint 是否还需要
  保留在 rejection_history 中？（已成功验证的方向与"应该避免重复探索的方向"语义不同）
- fingerprint 集合能否分层：近期 fingerprint（热集合，实时查询）vs 远期 fingerprint
  （归档，仅在热集合未命中时查询）？分层的语义代价是什么？

---

### 2.4 爆炸点四：ranking_history（PA 节点稳定性判断）

**爆炸机制**：

PA 节点在每个 Epoch 末计算 `has_ranking_change()`，判断 Top-K 集合是否稳定。该判断
依赖 `ranking_history`，记录每个 epoch 的 Top-K 集合和分数：

```typescript
interface RankingSnapshot {
  epoch_id: number;
  top_k_claim_ids: string[];
  scores: Record<string, number>;
}

type RankingHistory = RankingSnapshot[];  // ← 随 epoch 线性增长
```

**语义需求分析**：

`has_ranking_change()` 的判定条件是"连续 `hysteresis_rounds`（默认 2）轮 Top-K 集合不变
且分数漂移在 `score_delta` 以内"。这意味着：

- PA 节点的实时判断**只需要最近 2 轮**的 RankingSnapshot
- 更早的历史对当前的终止判定**没有直接贡献**

**核心问题**：
- 更早的 ranking_history 是否完全可以归档（不参与实时计算）？
- 如果系统支持"续跑"（从已终止状态重新启动），归档的 ranking_history 是否需要
  恢复到热状态？历史窗口应该继承还是重置？
- 归档后，如果用户想审查"系统在哪个 epoch 分数发生了关键跃升"，归档格式应保留
  哪些信息？

---

### 2.5 爆炸点五：ChallengeTracker 的 attempted_scopes

**爆炸机制**：

每个 `SchemaChallengeNotice` 对应一个 `ChallengeTracker`，记录 repair() 三级精化过程中
尝试过的方向：

```typescript
interface ChallengeTracker {
  challenge_id: string;
  current_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
  consecutive_filtered_epochs: number;
  attempted_scopes: string[];      // ← 每次 repair 失败追加
  attempted_outcomes: string[];    // ← 每次 repair 失败追加
  attempted_polarities: (1 | -1 | 0)[];  // ← 每次 repair 失败追加
}
```

一个长生命周期的 challenge（例如卡在 `ADJACENT` 阶段很久）可能积累大量记录。repair()
在生成新草稿时需要参考 `attempted_scopes` 来避免重复尝试相同方向——这与 rejection_history
的语义类似，但粒度更细（针对单个 challenge 的语义空间）。

**语义需求分析**：

repair() 给 LLM 的 prompt 需要包含 `attempted_scopes` 来约束 LLM"不要再往这些方向走"。
如果 attempted_scopes 列表过长，prompt 本身就会超限。

**核心问题**：
- attempted_scopes 的语义价值是"告诉 LLM 哪些方向已穷尽"——如果列表过长，是否可以
  用摘要替代（例如"已探索 X 个方向，覆盖维度 A/B/C"）？摘要后 LLM 能否做出等价
  的约束推理？
- 不同精化阶段（STRICT/RELAXED/ADJACENT）的 attempted_scopes 是否有不同的保留优先级？
  EXHAUSTED 阶段的记录是否可以直接归档？

---

### 2.6 爆炸点六：Layer 2 → Layer 1 的 L2Return 消息

**爆炸机制**：

每个 Epoch 结束时，Layer 2 向 Layer 1 发送 `L2Return`，包含 `new_gaps` 和
`schema_challenges`。Layer 1 的 MB/repair() 在下一个 Epoch 中需要参考这些信息。

问题不在于单个 `L2Return` 的大小，而在于：当 Layer 1 的 prompt 需要体现"历史上所有
Epoch 累积的 new_gaps 和 schema_challenges 的处理进展"时，如何表达这个累积状态？

**语义需求分析**：

MB 在产出新草稿时需要知道"目前还有哪些未解决的 GapSpec"——这是一个**状态查询**，而不是
**历史回放**。理论上只需要传递当前未解决 gap 的集合，而不需要传递每个 Epoch 的完整
L2Return 历史。

**核心问题**：
- "增量差分"模式：每个 Epoch 只传递"相对上一轮的变化"（新增 gap、已解决 gap、状态变更）
  vs "全量状态"模式：每个 Epoch 传递所有当前未解决 gap 的完整描述——哪种模式更适合
  LLM 的推理习惯？
- 如果 gap 的状态变更历史被丢弃（只保留当前状态），MB 是否会"忘记"某个方向曾经探索过
  但因为 gap 被解决而被标记为已完成？

---

### 2.7 爆炸点七：裁判/Judge 的输入 prompt

**爆炸机制**：

v3 系统中，最终的 AS（AnswerSynthesis）节点或外部裁判需要综合所有辩论轮次的内容来
输出最终结论。随着轮次增加，裁判的输入 prompt 线性增长：

```
裁判 prompt ≈ Σ(每轮 debater_output_tokens) + 系统背景 + 裁判指令
```

对于长达 10+ 轮的辩论，裁判 prompt 可能超过主流 LLM 的上下文窗口（128K-200K tokens）。

**语义需求分析**：

裁判需要"理解整个辩论过程"才能做出公正裁定。但裁判的核心任务是：
1. 识别双方的核心论点和反驳
2. 判断哪些论点更有证据支撑
3. 对未解决的争议给出裁定

这些任务**不需要**每个发言的字面内容，只需要保留**论点的语义结构**。

**核心问题**：
- 轮次摘要 vs 完整内容：是否可以对早期轮次做结构化摘要（"第 1 轮：A 主张 X，B 反驳 Y，
  核心分歧在 Z"），只保留最近 2 轮的完整内容？
- 摘要的生成时机：每轮结束后立即摘要（增量式），还是在裁判调用前批量摘要？
- 裁判是否需要知道"哪个论点在哪一轮被提出"（时序信息）？如果需要，摘要格式必须
  保留时序标记。

---

### 2.8 爆炸点八：跨 Epoch 的 LLM 调用上下文（repair() 内部）

**爆炸机制**：

当 repair() 调用 LLM 生成新草稿时，给 LLM 的 prompt 包含：
- 触发 repair 的 `GapSpec` 或 `SchemaChallengeNotice`
- 当前 `ChallengeTracker` 状态（attempted_scopes 等）
- 当前 `QuestionFrame`
- 已有的 `TestableClaim[]`（避免生成重复 claim）
- 可能还包含部分 `rejection_history`（避免重复方向）

随 epoch 增长，`TestableClaim[]` 和 `rejection_history` 都在增长，导致 repair() 的
LLM prompt 随时间增大。

**语义需求分析**：

repair() 的 LLM 需要参考已有 claim 的目的是"生成与现有 claim 不同源的新草稿"——这与
`is_homologous()` 的去重判断高度耦合。如果已有 claim 列表过长，是否可以只传递 claim 的
fingerprint 集合而不是完整 claim 内容？

**核心问题**：
- 历史越多越好（更多约束 → LLM 更精准避开已探索空间）vs 历史应该摘要（过多约束
  反而限制 LLM 的创造性探索）——这个权衡的最优点在哪里？
- repair() 在 `ADJACENT` 阶段主动"允许滑移到语义相邻维度"——此时历史约束是助力
  还是阻力？

---

## 三、核心设计问题（开放性，不预设答案）

以下对每个爆炸点提出具体的开放性问题，作为辩论的核心素材。问题框架刻意保持开放，
不预设答案。

### 3.1 压缩触发时机

**问题**：何时判定"需要压缩了"？

候选触发条件：
- **Token 计数触发**：当某组件的历史内容超过阈值 T（例如 50K tokens）时触发压缩。
  优点：机器可精确测量；缺点：不同内容的信息密度差异大，token 数不等于语义负担。
- **Epoch 计数触发**：每 K 个 Epoch 执行一次压缩。
  优点：节奏规律，便于调试；缺点：可能在内容还未爆炸时就压缩，也可能在内容已爆炸后
  才触发。
- **语义密度触发**：当检测到"最近 K 个 epoch 新增内容与已有内容的信息增益低于阈值"时触发。
  优点：语义敏感；缺点：需要额外的信息增益计算，本身可能有计算开销。
- **错误率触发**：当检测到 LLM 输出中出现"重复已否决内容"的频率上升时触发。
  优点：直接反映压缩必要性；缺点：属于事后检测，已经发生了语义污染。

**子问题**：不同爆炸点的触发时机是否应该独立管理？还是统一的全局压缩调度器？

### 3.2 压缩方式的选择

**压缩策略谱系**（从低损耗到高压缩率排列）：

| 策略 | 描述 | 适用条件 | 语义损失风险 |
|------|------|----------|-------------|
| 截断（丢弃旧的） | 只保留最近 K 条记录 | 历史的语义价值随时间单调递减 | 高（可能丢失关键约束） |
| 滑动窗口归档 | 近期保持热状态，远期归档但可检索 | 历史价值双峰分布（近期高、远期可查） | 中 |
| 结构化摘要 | LLM 生成固定格式的摘要替换原始内容 | 需要保留"内容含义"而非"字面内容" | 中（摘要失真风险） |
| 语义哈希索引 | 只保留 fingerprint，丢弃原始内容 | 下游操作只需要"曾见过/未见过"二值判断 | 低（适合 rejection_history） |
| 分层存储 + 向量检索 | 将历史内容向量化，按需检索相关片段 | 下游需要"语义相关内容"而非"全部历史" | 低（检索精度取决于向量模型） |

**子问题**：对于同一个爆炸点，是否存在"分阶段适用不同策略"的合理性？例如，
evidence_chain 的前 5 个 epoch 用全量保留，之后用结构化摘要？

### 3.3 压缩后的语义保留验证

**核心难题**：如何验证"压缩后 LLM 仍能做出等价判断"？

候选验证方法：
- **对照实验**：对同一组输入，分别用压缩前和压缩后的历史调用 LLM，比较输出的语义
  差异。成本高，只适合离线评估。
- **不变式检查**：定义一组系统不变式（如 INV-6：不存在两个同源草稿），每次压缩后
  验证不变式是否仍成立。适合机器检查，但不变式本身可能不完备。
- **摘要完整性哈希**：在生成摘要时，记录原始内容的关键字段哈希，每次使用摘要时
  检查关键字段是否在摘要中有对应表达。需要定义"关键字段"的规范。
- **错误率监控**：监控系统运行时的"重复探索率"（rejection 命中率下降）和"编译失败率"
  上升，作为压缩语义损失的间接指标。

**子问题**：是否存在可以形式化证明"压缩后等价"的场景？例如，语义哈希索引策略对于
rejection_history 的去重判断，是否可以形式化证明等价性？

### 3.4 不同组件的差异化策略

**核心认识**：不同历史的语义价值结构不同，压缩策略必须差异化。

**分类框架**：

| 历史类型 | 语义价值结构 | 推荐压缩策略方向 |
|----------|-------------|-----------------|
| rejection_history | 精确去重，二值判断 | 语义哈希索引（fingerprint 集合），原始内容可丢弃 |
| ranking_history | 近期窗口判断稳定性 | 滑动窗口，远期归档 |
| evidence_chain | 冲突检测，溯源审查 | 分层：近期全量，远期按 axis 聚合摘要 |
| ChallengeTracker.attempted_scopes | 约束 LLM 探索方向 | 结构化摘要（覆盖维度描述），而非字面列表 |
| Layer 1 对话历史 | LLM 上下文连贯性 | 轮次摘要 + 最近 K 轮完整保留 |
| 裁判输入 | 论点理解与评判 | 结构化轮次摘要，保留时序标记 |

**开放问题**：这个分类框架是否完备？是否存在某个爆炸点，其语义价值结构不属于上述
任何一类，因此推荐策略不适用？

---

## 四、可能的方向（提示性）

以下列出若干可能的技术方向，供辩论参考。这些方向不预设正确性，需要在具体的爆炸点
场景中论证其适用性和局限性。

### 4.1 增量差分传递

**核心思路**：每个 Epoch 只传递"相对上一轮的变化"，而非全量状态。

对于 L2Return 的传递，可以定义：

```typescript
interface L2ReturnDelta {
  epoch_id: number;
  new_verified_claims: VerifiedClaim[];       // 本 epoch 新增的
  newly_suspended_claim_ids: string[];         // 本 epoch 新增暂停的
  resolved_gap_ids: string[];                  // 本 epoch 已解决的 gap
  new_gaps: GapSpec[];                         // 本 epoch 新发现的 gap
  updated_challenge_stages: {                  // 本 epoch stage 变更的 challenge
    challenge_id: string;
    old_stage: string;
    new_stage: string;
  }[];
}
```

**潜在问题**：Layer 1 需要维护一个"完整当前状态"的本地缓存，每次收到 delta 后更新。
如果某个 delta 丢失（例如系统异常重启），状态需要从全量快照重建。这与续跑机制的
设计高度耦合。

### 4.2 结构化摘要替换

**核心思路**：用固定格式的摘要替换原始 LLM 对话内容，损失创意细节但保留关键判断。

对于 evidence_chain 的摘要，可以定义：

```typescript
interface EvidenceChainSummary {
  claim_id: string;
  summarized_at_epoch: number;
  covered_epochs: [number, number];            // [from_epoch, to_epoch]
  by_axis: {
    axis_id: string;
    pro_count: number;
    con_count: number;
    max_strength: "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL" | "AXIOMATIC";
    key_atoms: EvidenceAtom[];                 // 保留强度最高的 K 个 atom
    conflict_detected: boolean;                // 是否在摘要覆盖的 epoch 内检测到冲突
  }[];
  original_atom_count: number;                 // 摘要前的 atom 总数（用于审计）
}
```

**潜在问题**：摘要后，Layer 2 在 S4 阶段重审时，能否仅凭 `EvidenceChainSummary`
判断"新来的 EvidenceAtom 是否与历史冲突"？`conflict_detected` 字段是否足够，还是
需要保留原始 atom 内容？

### 4.3 分层存储与按需检索

**核心思路**：将远期历史归档，近期历史保持热状态，需要时按 claim_id/gap_id 检索。

```typescript
interface TieredHistory<T> {
  hot: T[];          // 最近 K 条，直接放在 prompt 中
  warm: T[];         // K 到 M 条，可快速加载（内存中但不在 prompt 里）
  cold: T[];         // M 条以上，需要磁盘 I/O（归档文件）
  retrieval_index: Map<string, { tier: "hot" | "warm" | "cold"; offset: number }>;
}
```

**潜在问题**：检索的触发条件是什么？LLM 调用前是否需要自动检索相关历史内容并注入
prompt？这会增加每次 LLM 调用的延迟。检索精度直接影响系统行为——检索失败（漏找
相关历史）等价于语义损失。

### 4.4 语义哈希索引

**核心思路**：rejection_history 只保存 fingerprint（哈希），不保存原始内容，
`is_homologous()` 只需比较哈希（已部分实现）。

```typescript
interface RejectionIndex {
  fingerprints: Set<string>;         // 纯哈希集合，O(1) 查询
  epoch_watermark: number;           // 最后一次更新的 epoch
  collision_risk_estimate: number;   // 估计的哈希碰撞概率（审计用）
}
```

**已部分实现**：v3 系统中 `is_homologous()` 的 fingerprint 计算已经包含哈希化步骤。
问题是：原始草稿内容是否可以在 fingerprint 入库后立即丢弃？还是需要保留一段时间
以备"碰撞检查"或"人工审查"？

**潜在问题**：哈希碰撞会导致合法草稿被误判为已否决。虽然概率极低，但系统有无机制
检测和恢复？如果发现碰撞，影响是否可接受？

### 4.5 滑动窗口与归档

**核心思路**：ranking_history 只保留最近 K 轮用于 PA 判定，更久的归档但不参与
实时计算。

```typescript
interface SlidingWindowHistory<T> {
  window_size: number;               // K，由配置决定
  active_window: T[];                // 最近 K 个 RankingSnapshot
  archive: T[];                      // 超出窗口的历史（归档，不参与计算）
  archive_summary?: {                // 可选：对归档内容的统计摘要
    epoch_range: [number, number];
    score_statistics: {
      claim_id: string;
      mean_score: number;
      score_variance: number;
    }[];
  };
}
```

**语义保证**：`has_ranking_change()` 的判定只需要 `active_window`（最近 `hysteresis_rounds`
轮），归档内容不影响终止判定的正确性。

**潜在问题**：如果 `hysteresis_rounds` 配置在运行时发生变化（例如用户在续跑时调整
了该参数），`window_size` 需要同步调整。归档后如果 `window_size` 扩大，需要从归档
中恢复数据——这要求归档格式保持可检索性。
