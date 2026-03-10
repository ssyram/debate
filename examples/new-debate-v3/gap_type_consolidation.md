---
title: "v3 认知引擎类型冲突裁定：GAP-1/2/4/5/7 权威定义之争"
rounds: 2
cross_exam: true
max_reply_tokens: 10000
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
  禁止：
  - 纯原则性陈述——每个主张必须伴随至少一个具体接口定义或类型形状
  - 稻草人攻击——交叉质询必须引用对手的具体文本
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须：
  1. 对所有待裁定 GAP 给出具体立场（附接口定义或数值）
  2. 对至少一个对手论点精确攻击（指名，引用文本，指出具体缺陷）
  3. 所有主张附可推翻条件

round1_task: |
  第一轮：针对每个待裁定 GAP，给出你的初始立场。
  对每个 GAP 必须包含：
  1. 具体的裁定结论（附接口定义或类型形状）
  2. 支撑该结论的核心论据
  3. 该结论的可推翻条件

final_task: |
  最终轮：给出完整的 GAP 裁定提案作为提交给裁判的最终立场。
  格式：对每个 GAP 给出明确结论（不得搁置），附触发条件/接口规格/失败行为。
  指出本轮辩论中对手哪些论证改变了你的初始立场。

judge_instructions: |
  裁判必须对每个 GAP 逐一给出明确裁定，不得搁置任何一个。
  每个裁定必须包含：
  1. 结论（一句话）
  2. 关键分歧与取舍
  3. 具体规格（TypeScript 接口）
  4. 可推翻条件
  最后给出优先级排序（按实现紧迫性）。
---

# v3 认知引擎类型冲突裁定：GAP-1/2/4/5/7 权威定义之争

## 系统背景

v3 认知引擎是一个双层 AI 辅助认知系统：
- **Layer 1**：7 节点状态机（QN→MB→CC→D2→PA→RB→AS），负责调度，维护 `L1State`
- **Layer 2**：证据验证层，执行实证检验，返回 `EpochDelta` 事件流

数据流：`ProblemStatement → QuestionFrame → HypothesisDraft[] → TestableClaim[] → EvidenceChain → VerifiedClaim → RankedClaim → AnswerSeed`

本场辩论聚焦于设计过程中积累了多个不兼容类型版本的 5 个 GAP，需要裁定最终权威定义。

---

## 待裁定 GAP

### GAP-1：`L2Return` 两版本冲突（阻塞级别：MAJOR）

**问题描述**：`L2Return` 在两个模块中有不兼容的定义——`repair_strategy` 旧版直接读取 `L2Return.evidence_summary` 字段，而 `layer1_orchestrator` 新版采用增量事件结构 `deltas: EpochDelta[]`，该字段不存在于新版。

**版本 A**（来自 `repair_strategy` 辩论，旧版）：
```typescript
// 旧版 L2Return：repair() 直接从中读取 evidence_summary
interface L2Return_OLD {
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  ranking_delta: { claim_id: string; score_change: number }[];
  evidence_summary: string;   // repair() 读取此字段构建提示词上下文
}

// 旧版 repair() 签名——直接接受 L2Return
function repair(
  gap: GapSpec,
  l2_return: L2Return_OLD,   // 直接传入 L2Return
  negative_constraints: NegativeConstraint[]
): RepairOutput;
```

**版本 B**（来自 `context_compression_gaps` 裁定，新版，00_shared_types.md 采纳）：
```typescript
// 新版 L2Return：增量事件结构
type EpochDelta =
  | { kind: "GAP_OPEN"; gap: GapSpec }
  | { kind: "GAP_PATCH"; gap_id: GapId; patch: JsonPatch }
  | { kind: "GAP_CLOSE"; gap_id: GapId; resolution: "RESOLVED" | "SUSPENDED" | "MERGED" | "INVALIDATED" }
  | { kind: "SCHEMA_CHALLENGE_NEW"; ch: SchemaChallengeNotice }
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaimFull }
  | { kind: "CLAIM_SUSPENDED"; claim_id: ClaimId; reason: string };

interface L2Return_NEW {
  epoch_id: EpochId;
  deltas: EpochDelta[];
  size_bytes: number;   // 超过 32KB 时 L1 拒收
}

// 新版 repair() 签名——接受 L1State（经 applyDelta 吸收后）
interface RepairInput {
  gap: GapSpec;
  current_stage: RepairStage;
  l1_state: L1State;      // 经 applyDelta 吸收后的状态
  negative_constraints: NegativeConstraint[];
  max_attempts_per_stage: number;
  consecutive_unsat_limit: number;
}
function repair(input: RepairInput): RepairOutput;
```

**裁定目标**：选择版本 B 为权威（或提出合并方案），并说明 `repair_strategy` 模块如何更新以适应新接口。特别需要裁定：当 `repair()` 需要从 `l1_state` 提取与特定 `gap` 相关的 `evidence_summary` 时，应该使用哪个辅助 API？

**如果忽略这个 GAP 直接实现会发生什么**：`repair()` 调用 `input.l2_return.evidence_summary` 时得到 `undefined`，修复提示词为空，LLM 产出通用草稿而非针对缺口的精确草稿，`STAGE_UPGRADED` 循环直到 `EXHAUSTED`，整个 CEGAR 闭环无法收敛。

---

### GAP-2：`GapSpec.kind` 枚举不兼容（阻塞级别：BLOCKER）

**问题描述**：`GapSpec.kind` 字段在两个模块中使用了完全不同的枚举值集合——`repair_strategy` 使用描述假设框架结构缺陷的视角，`scoring_termination` 使用描述评估轴覆盖状态的视角。两套枚举已在 `00_shared_types.md` 中拆分，但实现时如何严格遵循仍未裁定。

**版本 A**（`repair_strategy` 视角，修复引擎使用）：
```typescript
// 描述"为什么这个假设需要被修复"
type RepairGapKind =
  | "MISSING_DISCRIMINATOR"    // 缺少判别维度
  | "MISSING_OBSERVABLE"       // 缺少可观测量
  | "PREMISE_UNDERSPECIFIED"   // 前提条件未精化
  | "UNCLASSIFIED";            // 无法分类

// repair_strategy 使用示例
function generate_repair_draft(
  gap: GapSpec,
  stage: RepairStage,
  evidence_context: dict,
  l1_state: L1State
) -> RawRepairDraft | None:
    gap_kind = gap.kind  // 期望是 RepairGapKind
    if gap_kind == "MISSING_DISCRIMINATOR":
        prompt = build_discriminator_prompt(...)
    elif gap_kind == "MISSING_OBSERVABLE":
        prompt = build_observable_prompt(...)
    // 若 gap.kind 实际上是 TerminationGapKind（如 "UNCOVERED_HIGH_WEIGHT_AXIS"），
    // 则进入 UNCLASSIFIED 分支，修复策略退化
```

**版本 B**（`scoring_termination` 视角，PA 节点使用）：
```typescript
// 描述"为什么无法终止"
type TerminationGapKind =
  | "UNCOVERED_HIGH_WEIGHT_AXIS"   // 高权重轴完全无 claim 覆盖
  | "UNRESOLVED_DEFEATER"          // 存在未解决的反证
  | "WEIGHT_UNDERSPECIFIED"        // 权重声明不完整
  | "EVIDENCE_CONFLICT"            // 同一轴上证据严重冲突
  | "LOW_COVERAGE_FRONTIER"        // 前沿 claim 覆盖率普遍偏低
  | "STAKEHOLDER_DISAGREEMENT";    // stakeholder 权重矛盾

// scoring_termination 中的错误用法（如果混用）
function classify_gap_for_termination(gap: GapSpec) -> TerminationGapKind | None:
    // 错误：将 gap.kind 直接与 TerminationGapKind 的值比较
    if gap.kind == "UNCOVERED_HIGH_WEIGHT_AXIS":   // 若 gap.kind 实际是 RepairGapKind
        return "UNCOVERED_HIGH_WEIGHT_AXIS"         // 永远不会命中，blocking_gaps 为空
    // 导致 PA 误认为没有终止相关缺口，系统过早终止
```

**统一方案**（`00_shared_types.md` 已采纳，但实现约定未裁定）：
```typescript
// 统一 GapSpec：kind 字段使用联合类型
interface GapSpec {
  gap_id: GapId;
  kind: RepairGapKind | TerminationGapKind;
  blocks_termination: boolean;
  axis_id?: AxisId;
  related_claim_ids?: ClaimId[];
  description: string;
  discriminator?: string;
  evidence_summary?: string;
}
```

**裁定目标**：裁定以下三个问题：
1. `GapSpec` 对象在创建时，`kind` 应该由哪个模块负责赋值（Layer 2 赋 `RepairGapKind`，PA 节点赋 `TerminationGapKind`，还是两者都可以产生 `GapSpec`）？
2. `repair()` 和 `classify_gap_for_termination()` 如何在运行时区分收到的 `GapSpec.kind` 是哪个子类型？
3. 是否需要为两套枚举引入 tagged union 以获得编译期保证？

**如果忽略这个 GAP 直接实现会发生什么**：`generate_repair_draft()` 的 case 分支全部落入 `UNCLASSIFIED`（修复质量退化）；或 `classify_gap_for_termination()` 的所有 gap 落入 `None`（PA 误判无阻塞 gap，系统过早终止）。两种情况都是静默错误，不崩溃但结果完全错误。

---

### GAP-4：`HypothesisDraft` 旧版与统一类型不符（阻塞级别：MAJOR）

**问题描述**：`repair_strategy` 辩论中定义的旧版 `HypothesisDraft` 缺少 `problem_id` 和 `open_term_risk` 字段，且 `verifier_hint` 为单 `string` 而非 `string[]`。`00_shared_types.md` 已采纳统一定义，但旧版在实现时可能被直接使用。

**版本 A**（`repair_strategy` 辩论旧版）：
```typescript
// 旧版 HypothesisDraft（repair 辩论中的定义）
interface HypothesisDraft_OLD {
  draft_id: DraftId;
  // 缺少 problem_id
  claim_sketch: string;
  scope_ref: string[];
  verifier_hint: string;         // 单 string，非数组
  // 缺少 open_term_risk
  tension_source: TensionSource;
  provenance: Provenance;
}

// 旧版 normalize_repair() 产出旧版类型
function normalize_repair_OLD(
  raw: RawRepairDraft,
  gap: GapSpec
): HypothesisDraft_OLD;
```

**版本 B**（`00_shared_types.md` 统一定义，权威版本）：
```typescript
// 统一 HypothesisDraft
interface HypothesisDraft {
  draft_id: DraftId;
  problem_id: ProblemId;           // 必填。MB 原生; Repair 由 L1 调度层注入
  claim_sketch: string;
  scope_ref: string[];             // 禁止空数组
  verifier_hint: string[];         // 统一为数组
  open_term_risk: string[];        // 可为 []
  tension_source: TensionSource;
  provenance: Provenance;
}

// 统一 normalize_repair()——必须通过此工厂函数创建修复草稿
interface RepairContext {
  frame: QuestionFrame;
  gap_id: GapId;
  challenge_id: string;
  current_stage: RepairStage;
}

function normalize_repair(
  raw: RawRepairDraft,
  ctx: RepairContext    // 需要 ctx.frame.problem_id 注入到 draft.problem_id
): HypothesisDraft;
```

**冲突的具体影响**：

```typescript
// is_homologous() 依赖 problem_id 做快速排除
function is_homologous(a: HypothesisDraft, b: HypothesisDraft): boolean {
  // 如果 problem_id 为 undefined（旧版），跨问题的同源判断失效
  if (a.problem_id !== b.problem_id) return false;  // undefined !== undefined → false，误判！
  // 导致跨 problem 的草稿不被去重，草稿池污染
}

// CC 对 verifier_hint 的处理
function refine_claim(
  hints: string[],  // 期望数组
  ...
): string {
  return hints.join("; ");  // 旧版 string 传入时：["旧版单 string".join("; ")] 不是问题，
                             // 但 hints.map(...) 之类操作会对 string 逐字符迭代，行为错误
}
```

**裁定目标**：裁定以下问题：
1. `normalize_repair()` 的 `RepairContext` 中，`problem_id` 从哪里注入（`L1State.frame.problem_id` 还是 `gap.gap_id` 派生）？
2. 是否需要运行时断言保证所有进入草稿池的 `HypothesisDraft` 都有非空 `problem_id`？
3. 旧版代码库中已有的 `verifier_hint: string` 如何迁移（运行时转换还是编译期类型收紧）？

**如果忽略这个 GAP 直接实现会发生什么**：`is_homologous()` 的 `problem_id` 快速排除失效，草稿池无法正确去重，同源草稿重复进入 Layer 2，证据链计算重复，Epoch 循环不收敛。

---

### GAP-5：`alpha` 符号歧义（阻塞级别：MINOR）

**问题描述**：系统中存在两个含义完全不同但都被称为 `alpha` 的参数：`ema_alpha`（epsilon 学习率，控制 EMA 衰减速度）和 `score_alpha`（评分缩放因子，调整分数分布）。两者在原始辩论文档中都简写为 `alpha`，但默认值和语义完全不同。

**版本 A**（`epsilon_calibration` 中的 `ema_alpha`）：
```typescript
// EpsilonState 中的 ema_alpha
interface EpsilonState {
  axis_id: string;
  current_epsilon: number;    // ∈ [min_epsilon, max_epsilon]
  min_epsilon: number;        // 默认 0.01
  max_epsilon: number;        // 默认 0.15
  ema_alpha: number;          // EMA 学习率，默认 0.2
                              // 控制 epsilon 对新观测的响应速度
  epoch_count: number;
  last_scores: number[];
  confidence_level: number;
}

// update_epsilon 中的用法
// epsilon_t = ema_alpha * delta + (1 - ema_alpha) * epsilon_{t-1}
const DEFAULT_EMA_ALPHA = 0.2;  // 学习率：0 = 完全忽略新数据，1 = 完全信任新数据
```

**版本 B**（`scoring_termination` 中的 `score_alpha`）：
```typescript
// TerminationConfig 中的 score_alpha
interface TerminationConfig {
  top_k: number;
  min_coverage: number;
  hysteresis_rounds: number;
  score_alpha: number;        // 评分缩放因子，默认 1.0
                              // 平滑极端分数：scaled_score = score_alpha * raw_score
}

// compute_rankings 中的用法
const score_alpha = DEFAULT_TERMINATION_CONFIG.score_alpha;  // 默认 1.0
const scaled_score = score_alpha * raw_score;
// 注意：score_alpha=0.2 会使所有分数压缩为 1/5，
// 覆盖率检查可能永远无法通过（分数系统性偏低）
```

**混用的具体崩溃场景**：

```python
# 错误的配置文件（混用命名）
config = {
    "alpha": 0.2,  # 原意是 ema_alpha（学习率）
}

# PA 节点错误地将 "alpha" 作为 score_alpha 读取
score_alpha = config.get("alpha", 1.0)  # 得到 0.2，原意是 ema_alpha
scaled_score = score_alpha * raw_score  # 所有分数乘以 0.2

# 结果：
# - claim-009 原始分 0.564 → 压缩后 0.113
# - min_coverage = 0.70
# - 系统永远无法终止（分数永远低于阈值）
# - 不崩溃，但无限循环
```

**裁定目标**：裁定以下问题：
1. 全代码库命名规范：学习率统一称 `ema_alpha`，评分缩放统一称 `score_alpha`，禁止使用裸 `alpha`
2. 配置文件（YAML/JSON）的键名规范是否需要同步更改？
3. 是否需要在 `TerminationConfig` 和 `EpsilonState` 的构造函数中加入 assertion 防止误用（如 `assert 0 < ema_alpha < 1`，`assert score_alpha > 0`）？

**如果忽略这个 GAP 直接实现会发生什么**：`PA` 节点的所有分数被缩放为 1/5，覆盖率检查永远无法满足，系统进入无限 epoch 循环。不崩溃，调试极难（分数看起来"有点低"，不像明显的 bug）。

---

### GAP-7：`VerifiedClaim` 两版本转换边界不明（阻塞级别：MINOR）

**问题描述**：`VerifiedClaim` 有两种形态，但 L1 状态机中何时存放哪种形态、以及 `repair()` 和 `compute_rankings()` 如何在不知道具体形态的情况下正确读取数据，没有明确设计。

**版本 A**（`VerifiedClaimFull`，压缩前，来自 Layer 2 直接输出）：
```typescript
interface VerifiedClaimFull {
  claim_id: ClaimId;
  source_draft_id: DraftId;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;              // ∈ [0, 1]
  axis_scores: Partial<Record<AxisId, number>>;
  evidence_chain: EvidenceAtom[];     // 全量证据原子（可能很大）
}
```

**版本 B**（`VerifiedClaimCompressed`，压缩后，来自 context_compression）：
```typescript
interface VerifiedClaimCompressed {
  claim_id: ClaimId;
  source_draft_id: DraftId;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<AxisId, number>>;
  // 无 evidence_chain 字段！
  evidence_profiles: Record<AxisId, CompressedEvidenceProfile>;
  active_window: EvidenceAtom[];   // 热区：最近 N 个 epoch 的原始 Atom
}
```

**L1State 中的混用问题**：
```typescript
// L1State 中两种形态共存
interface L1State {
  verified_claims: (VerifiedClaimFull | VerifiedClaimCompressed)[];  // 联合类型
  // ...
}

// repair() 试图从 verified_claims 提取证据上下文
function extract_evidence_context(
  claims: (VerifiedClaimFull | VerifiedClaimCompressed)[],
  gap: GapSpec
): EvidenceContext {
  for claim in claims:
    if gap.axis_id in get_claim_axes(claim):
      // 版本 A：claim.evidence_chain 存在（可以直接读 atom）
      // 版本 B：claim.evidence_chain 为 undefined（崩溃！或静默得到 undefined）
      atoms = claim.evidence_chain  // TypeError: 'VerifiedClaimCompressed' has no 'evidence_chain'
}

// compute_rankings() 需要 axis_scores（两种形态都有，但获取路径不同）
function compute_rankings(
  verified_claims: (VerifiedClaimFull | VerifiedClaimCompressed)[]
): RankedClaim[] {
  for claim in verified_claims:
    // axis_scores 字段在两种形态中都存在，但来源不同
    // VerifiedClaimFull.axis_scores 直接可用
    // VerifiedClaimCompressed.axis_scores 可能为 Partial（部分轴无数据）
    score = claim.axis_scores.get(axis_id)  // Partial 时可能为 undefined
}
```

**两个备选设计方案**：

方案 X（接口屏蔽，`09_context_compression.md` 建议）：
```typescript
// 辅助函数屏蔽两种形态差异
function get_axis_scores(claim: VerifiedClaimFull | VerifiedClaimCompressed): Partial<Record<AxisId, number>> {
  return claim.axis_scores;  // 两种形态都有此字段，直接返回
}

function get_evidence_atoms(
  claim: VerifiedClaimFull | VerifiedClaimCompressed,
  axis_id?: AxisId
): EvidenceAtom[] {
  if ('evidence_chain' in claim) {
    return axis_id ? claim.evidence_chain.filter(a => a.axis_id === axis_id) : claim.evidence_chain;
  } else {
    // 压缩形态：从 active_window 取，必要时触发 rehydrate
    return claim.active_window.filter(a => !axis_id || a.axis_id === axis_id);
  }
}
```

方案 Y（L1State 统一为压缩形态，压缩触发后原地替换）：
```typescript
// 压缩触发后立即在 L1State 中替换对应 claim
function trigger_compression(
  state: L1State,
  claim_id: ClaimId
): Result<L1State, CompressError> {
  const full_claim = state.verified_claims.find(c => c.claim_id === claim_id) as VerifiedClaimFull;
  const compress_result = compress_evidence_chain(claim_id, full_claim.evidence_chain, null, config, rulebook_version);
  if (!compress_result.ok) return Err(compress_result.error);
  // 原地替换
  const new_claims = state.verified_claims.map(c =>
    c.claim_id === claim_id
      ? { ...c, evidence_profiles: compress_result.value.profiles, active_window: compress_result.value.active_window } as VerifiedClaimCompressed
      : c
  );
  return Ok({ ...state, verified_claims: new_claims });
}
```

**裁定目标**：在方案 X 和方案 Y 之间选择，或提出第三方案，并给出：
1. 选择方案的完整辅助 API 签名
2. 压缩触发的时机（在 `apply_l2_return()` 内？在 epoch 结束时？）
3. `repair()` 读取证据上下文时的确切代码路径

**如果忽略这个 GAP 直接实现会发生什么**：`repair()` 读取 `VerifiedClaimFull.evidence_chain` 时，若该 claim 已被压缩，得到 `undefined`，修复提示词上下文为空；PA 节点的 `compute_rankings()` 读取 `axis_scores` 时，压缩后形态的 `Partial` 数据可能导致部分轴得分为 0，排名错误，终止条件误触发。
