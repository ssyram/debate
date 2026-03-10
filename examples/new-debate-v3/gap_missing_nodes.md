---
title: "v3 认知引擎缺失节点设计：GAP-3/6/8 Layer 1 三节点接口从零裁定"
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

# v3 认知引擎缺失节点设计：GAP-3/6/8 Layer 1 三节点接口从零裁定

## 系统背景

v3 认知引擎是一个双层 AI 辅助认知系统：
- **Layer 1**：7 节点状态机（QN→MB→CC→D2→PA→RB→AS），负责调度，维护 `L1State`
- **Layer 2**：证据验证层，执行实证检验，返回 `EpochDelta` 事件流

Layer 1 的数据流：
```
ProblemStatement
    │ normalize_question() [QN]
    ▼
QuestionFrame
    │ macro_breadth() [MB]
    ▼
HypothesisDraft[]
    │ clarity_compile() [CC]
    ├─→ TestableClaim[]  ─────────────────────────────→ [D2：Layer 2 分派]
    └─→ RegulativeIdea[] ─────────────────────────────→ [RB：修复广度]
                                                              │
                                              [D2 返回 L2Return]
                                                    │ applyDelta()
                                                    ▼
                                               L1State'
                                                    │ compute_rankings() [PA]
                                                    │ check_termination()
                                        ┌───────────┤
                                        │ false     │ true
                                        ▼           ▼
                                   repair() [RB]  [AS：答案组装]
                                        │           │
                              HypothesisDraft[]   AnswerSeed
                              回到 CC 进入下一 epoch
```

本场辩论聚焦于三个内部接口**从未被完整设计**的节点：AS 节点（GAP-3）、RB 节点的 `repair_breadth()` 内部逻辑（GAP-6）、以及 D2 节点的路由表（GAP-8）。这三个 GAP 是「从零设计」而不是「在冲突版本中选择」——辩手需要从已知约束出发推导出完整接口。

---

## 待裁定 GAP

### GAP-3：`AnswerSeed`（AS 节点）接口缺失（阻塞级别：BLOCKER）

**问题描述**：当 PA 节点判定 `should_terminate=true` 后，AS 节点负责组装最终输出。目前 `layer1_orchestrator` 中给出了一个最小骨架实现，但 `AnswerSeed` 的完整字段定义（特别是人类可读的叙述性答案、置信区间、以及对下游消费者的接口契约）尚未裁定。

**已知约束（设计时必须满足）**：

1. `top_claims` 来自 PA 节点的 `PAState.ranked_claims`（类型已确立）
2. `integrity_status` 必须继承自 `EngineSnapshot.integrity_status`（`"CLEAN"` 或 `"DEBUG_OVERRIDE_APPLIED"`）
3. `EngineSnapshot.safe_point.stage` 中存在 `"TERMINATED_BEFORE_AS"` 状态，说明 AS 节点可能被跳过——设计必须能区分"正常产出 AnswerSeed"和"提前终止未产出 AnswerSeed"
4. `coverage_report` 必须按 `axis_id` 维度报告（而非按 `claim_id`）

**当前最小骨架实现**（`layer1_orchestrator` 现状）：

```typescript
// 当前仅有的 AnswerSeed 定义（layer1_orchestrator.md）
interface AnswerSeed {
  problem_id: string;
  epoch_id: number;
  top_claims: RankedClaim[];
  coverage_report: Record<string, number>;  // axis_id → coverage（值域未定义）
  integrity_status: "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
  termination_reason: string;
}

// 当前最小实现（assemble_answer_seed 骨架）
function assemble_answer_seed(pa_state: PAState, frame: QuestionFrame): AnswerSeed {
  const top_claims = pa_state.ranked_claims.slice(0, frame.evaluation_axes.length);

  const coverage_report: Record<string, number> = {};
  for (const ax of frame.evaluation_axes) {
    coverage_report[ax.axis_id] = compute_axis_coverage(ax.axis_id, pa_state.ranked_claims);
    // compute_axis_coverage 未定义！返回值的语义不清楚
  }

  return {
    problem_id: frame.problem_id,
    epoch_id: pa_state.ranking_history.at(-1)?.epoch_id ?? 0,
    top_claims,
    coverage_report,
    integrity_status: "CLEAN",      // 硬编码！未从 EngineSnapshot 继承
    termination_reason: pa_state.termination_reason ?? "正常终止"
  };
}
```

**已知问题清单（辩手需要逐一给出裁定方案）**：

1. `coverage_report` 的值应该是什么？是 `RankedClaim.coverage`（已覆盖轴的权重之和，∈ [0,1]）？还是轴上所有 claim 的 `axis_score` 加权平均？两者语义完全不同：
   - `claim.coverage = 0.75` 表示该 claim 覆盖了权重总量 75% 的轴
   - `axis_score_avg["ax_capacity"] = 0.60` 表示 `ax_capacity` 轴上所有 claim 的平均得分为 0.60

2. `top_claims` 的 `k` 值：当前 `slice(0, frame.evaluation_axes.length)` 意味着取"和评估轴数量相同数量的 claims"，但 `evaluation_axes` 可以有任意多个轴，这个切片规则有问题：3 个轴不代表只取 3 个 claim。正确的 `top_k` 应该来自哪里？

3. `integrity_status` 硬编码为 `"CLEAN"` 是错误的。正确做法是从 `L1State` 中读取 `EngineSnapshot.integrity_status`。但 `assemble_answer_seed()` 目前只接收 `pa_state` 和 `frame`，无法访问 `integrity_status`——函数签名需要修改吗？

4. 下游消费者（如报告生成器、用户界面）需要什么？目前 `AnswerSeed` 只有结构化数据，没有叙述性答案文本。是否需要增加：
   - `answer_narrative: string`（基于 `top_claims` 的自然语言总结，需要 LLM 生成）
   - `confidence_bands: Record<AxisId, [number, number]>`（每轴的 `[score - epsilon, score + epsilon]` 置信区间）

**设计约束供辩手参考**：

```typescript
// 已确立的上下游类型（辩手推导 AnswerSeed 时必须兼容）
interface RankedClaim {
  claim_id: ClaimId;
  score: number;     // ∈ [0, 1]
  coverage: number;  // ∈ [0, 1]，已覆盖轴的权重之和
}

interface TerminationConfig {
  top_k: number;         // 已有此配置，是取 top_claims 的正确来源
  min_coverage: number;
  hysteresis_rounds: number;
  score_alpha: number;
}

interface PAState {
  ranked_claims: RankedClaim[];
  ranking_history: RankingEntry[];
  consecutive_stable_epochs: number;
  epsilon_states: Record<string, EpsilonState>;
  termination_config: TerminationConfig;   // top_k 在这里
  termination_reason?: string;
}

// EngineSnapshot 中有 integrity_status
interface EngineSnapshot {
  integrity_status: "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
  // ...
}
```

**裁定目标**：给出完整的 `AnswerSeed` 类型定义（含所有字段及其语义），以及 `assemble_answer_seed()` 的正确函数签名（参数列表是否需要增加 `integrity_status` 或完整 `L1State`）。

**如果忽略这个 GAP 直接实现会发生什么**：PA 节点判定 `should_terminate=true` 后，L1 调度器调用 `assemble_answer_seed()`，当前骨架实现：（1）`coverage_report` 语义不清，下游无法正确解读；（2）`integrity_status` 永远为 `"CLEAN"`，`DEBUG_OVERRIDE` 后的污染状态对用户不可见；（3）`top_k` 取值错误，可能输出过多或过少的结论。系统不崩溃，但输出的 `AnswerSeed` 包含错误数据。

---

### GAP-6：RB 节点 `repair_breadth()` 内部逻辑未设计（阻塞级别：MAJOR）

**问题描述**：RB 节点（Repair Breadth）接收来自 CC 的 `RegulativeIdea[]`，通过 `repair_breadth()` 尝试将其转化为广度探索草稿。当前 `layer1_orchestrator` 给出了最小骨架，但内部的 `extract_testable_angle()` 函数完全未设计，导致所有 `RegulativeIdea` 都返回 `None`，RB 节点对广度探索无任何贡献。

**已知约束（设计时必须满足）**：

1. `RegulativeIdea` 来自 CC 的 `NO_EMPIRICAL_BRIDGE` 错误路径：这类理念无法通过标准证伪合成得到 `TestableClaim`
2. RB 节点的目标是"广度探索"——不是精确修复已知 gap，而是从新角度重新审视同一议题
3. `extract_testable_angle()` 的输入必须是 `RegulativeIdea`（含 `claim_sketch` 和 `no_empirical_bridge_reason`），输出必须是 `HypothesisDraft`（或 `null` 表示无法提取）
4. 产出的草稿会进入 CC 重新编译——因此不能要求草稿必须可检验，只需要"比原始 RegulativeIdea 更接近可检验"即可
5. 已有的 `normalize_repair()` 工厂函数必须被使用（保证产出是合法的 `HypothesisDraft`）

**当前最小骨架实现**（`layer1_orchestrator` 现状）：

```python
# 当前 repair_breadth() 实现（最小版本）
def repair_breadth(
    ideas: list[RegulativeIdea],
    frame: QuestionFrame
) -> list[HypothesisDraft]:
    drafts = []
    for idea in ideas:
        # 尝试从 RegulativeIdea 提取可检验的角度
        extractable = extract_testable_angle(idea, frame)
        if extractable:
            raw = RawRepairDraft(
                claim_sketch=extractable.claim_sketch,
                tension_kind="SCHEMA_REPAIR",
                verifier_hint=extractable.verifier_hint,
                scope_ref=extractable.scope_ref,
                detail=f"由 RegulativeIdea {idea.idea_id} 转化"
            )
            ctx = RepairContext(
                frame=frame,
                gap_id=f"idea-{idea.idea_id}",
                challenge_id=f"idea-{idea.idea_id}",
                current_stage="RELAXED"
            )
            drafts.append(normalize_repair(raw, ctx))

    return drafts

# extract_testable_angle() 完全未实现
def extract_testable_angle(
    idea: RegulativeIdea,
    frame: QuestionFrame
) -> ExtractableAngle | None:
    pass  # TODO: 核心逻辑未设计
```

**核心问题：`extract_testable_angle()` 应该怎么工作？**

`RegulativeIdea` 的典型样例：
```typescript
// 来自 CC 的 RegulativeIdea
RegulativeIdea {
  idea_id: "idea-001",
  source_draft_id: "mb-005",
  claim_sketch: "碳排放交易机制在道德上优于碳税，因为它更尊重各国的主权决策权",
  no_empirical_bridge_reason: "'道德优越性'和'主权尊重'缺乏可操作的经验测试维度"
}
```

从这个 `RegulativeIdea` 出发，可能的转化策略：

**策略 A（最小化，类比 CC 的宽松模式）**：
```typescript
// 用 LLM 重构为可检验版本：放宽证伪条件要求
interface ExtractableAngle {
  claim_sketch: string;        // 重构后的草稿
  verifier_hint: string[];     // 验证提示（可以更模糊，允许间接证伪）
  scope_ref: string[];         // 评估轴引用
  extraction_strategy: "REFRAME" | "PROXY_MEASURE" | "COMPONENT_DECOMPOSE" | "NONE";
}

// REFRAME: 将规范性主张重构为可比较的经验主张
// 例："主权决策权更受尊重" → "在碳排放交易机制下，各国实际提交的NDC修订率更高"
//
// PROXY_MEASURE: 找到规范概念的代理可测量指标
// 例："道德优越性" → "在国际谈判中被更多国家自愿采纳的比率"
//
// COMPONENT_DECOMPOSE: 拆解为子命题，各子命题可独立检验
// 例："主权尊重" → [决策自主性指标A, 退出机制保留率B, 第三方约束力度C]
```

**策略 B（保守化，先判断是否值得尝试）**：
```typescript
// 先用规则判断能否提取，失败则直接返回 None（不调用 LLM）
function extract_testable_angle(idea: RegulativeIdea, frame: QuestionFrame): ExtractableAngle | None {
  // 规则 1：如果 no_empirical_bridge_reason 包含"数学上无法"/"逻辑上不可能"等词，返回 None
  if (contains_logical_impossibility(idea.no_empirical_bridge_reason)) return null;

  // 规则 2：检查 frame.evaluation_axes 中是否有轴能与 idea.claim_sketch 关联
  const candidate_axes = find_related_axes(idea.claim_sketch, frame.evaluation_axes);
  if (candidate_axes.length === 0) return null;

  // 规则 3：调用 LLM 尝试重构（仅当上述规则通过时）
  return llm_reframe(idea, candidate_axes, strategy="RELAXED");
}
```

**已知的下游约束（对 `extract_testable_angle()` 的输出施加约束）**：

```typescript
// normalize_repair() 对输入的要求
interface RawRepairDraft {
  claim_sketch: string;         // 不能与 idea.claim_sketch 完全相同（否则等于没改）
  tension_kind: TensionKind;    // 必须是 "SCHEMA_REPAIR"
  verifier_hint: string[];      // 不能为空数组（normalize_repair 会检查）
  scope_ref: string[];          // 必须非空，且引用 frame 中存在的 axis_id
  detail: string;
}

// CC 的 is_homologous() 会过滤同源草稿
// 因此 repair_breadth 产出的草稿必须在内容上与已有草稿有实质差异
// （否则立即被去重丢弃，RB 节点贡献为零）
```

**裁定目标**：给出 `extract_testable_angle()` 的完整设计，包含：
1. 函数签名（返回类型 `ExtractableAngle` 的完整定义）
2. 调用 LLM 的触发条件（规则先行还是直接 LLM）
3. LLM 调用失败时的处理（静默返回 `None`？还是记录错误？）
4. 产出的草稿如何避免被 `is_homologous()` 立即过滤（即如何保证与原始 `RegulativeIdea` 有足够差异）

**如果忽略这个 GAP 直接实现会发生什么**：所有 `RegulativeIdea` 在 Epoch 循环中被 CC 路由到 RB 节点后，`repair_breadth()` 返回空列表，`RegulativeIdea` 永久积累在 `L1State.regulative_ideas` 中但从不产生任何草稿。广度探索完全失效，引擎只能通过 `repair()` 修复已知 gap，无法从全新角度生成假说。系统不崩溃，但探索空间严重受限，对开放性问题（如碳排放机制设计）的答案质量显著下降。

---

### GAP-8：D2 节点入口类型和分派路由未裁定（阻塞级别：MAJOR）

**问题描述**：D2 节点是 Layer 1 与 Layer 2 之间的分派层。CC 编译产出的 `TestableClaim` 包含 `verification_protocol` 字段（来自 CC 的 `verifier_type`），指定了该 claim 应该用哪种验证器来验证。但 D2 节点如何根据 `verifier_type` 将 claim 分派给不同验证器，完全没有设计。

**已知约束（设计时必须满足）**：

1. CC 已确立 `verifier_type` 的 5 个枚举值：
   - `"EMPIRICAL_CHECK"`：通过收集实证文献验证（S4+S5 标准路径）
   - `"LOGICAL_AUDIT"`：纯逻辑推导的命题，不需要实证文献，需要逻辑一致性审查
   - `"SCOPE_REVIEW"`：范围边界审查，检查 claim 的适用范围是否合理
   - `"TARGETED_RECHECK"`：针对已有证据的重新检验（来自 `L2_FAILURE` 的修复草稿）
   - `"AXIS_CONSISTENCY_CHECK"`：评估轴内部一致性检查（来自 `INTERNAL_AXIS` 张力）

2. Layer 2 的核心函数 `run_layer2_verification()` 目前只有一条路径（S4 证据收集 + S5 评分），它假设所有 claim 都走 `EMPIRICAL_CHECK` 路径

3. `TestableClaim` 中记录 `verifier_type` 的字段名为 `verification_protocol`（来自 `route_compile_result()` 的赋值：`verification_protocol: result.value.verification_plan["verifier_type"]`）

4. D2 节点目前在 `layer1_orchestrator` 中以 `run_layer2_batch()` 函数调用，函数签名已知：
   ```python
   l2_result = run_layer2_batch(
       claims=pending_claims,          # TestableClaim[]，已包含 verification_protocol 字段
       rulebook=get_rulebook(state.frame),
       epoch_id=epoch
   )
   ```

5. `run_layer2_batch()` 的返回值是 `L2Return`（增量事件结构），这个接口必须保持不变

**当前缺失的分派逻辑**（D2 节点现状）：

```python
# 当前 run_layer2_batch() 实现（假想中的伪代码——实际上根本没有设计）
def run_layer2_batch(
    claims: list[TestableClaim],
    rulebook: AxisRulebook,
    epoch_id: int
) -> Result[L2Return, L2BatchError]:
    deltas = []
    for claim in claims:
        # 问题：完全忽略 claim.verification_protocol！
        # 所有 claim 都走同一条 EMPIRICAL_CHECK 路径
        result = run_layer2_verification(claim, rulebook, epoch_id)
        if result.ok:
            deltas.append({ "kind": "CLAIM_VERIFIED", "claim": result.value.to_verified_claim() })
        else:
            deltas.append({ "kind": "CLAIM_SUSPENDED", "claim_id": claim.claim_id, "reason": str(result.error) })
    return Ok(L2Return(epoch_id=epoch_id, deltas=deltas, size_bytes=estimate_size(deltas)))
```

**需要设计的 D2 路由表**：

每种 `verifier_type` 对应不同的验证路径，辩手需要给出：

```typescript
// 问题 1：每种 verifier_type 对应的验证器接口是什么？
type VerifierType = "EMPIRICAL_CHECK" | "LOGICAL_AUDIT" | "SCOPE_REVIEW" | "TARGETED_RECHECK" | "AXIS_CONSISTENCY_CHECK";

// 备选方案 A：统一接口，验证器内部分派
interface Verifier {
  verify(claim: TestableClaim, rulebook: AxisRulebook, epoch_id: number): Result<EvidenceChain, L2VerificationError>;
}
// 分派点在 D2 节点，选择不同的 Verifier 实例

// 备选方案 B：不同验证器有不同接口，D2 负责类型转换
interface EmpiricalVerifier {
  collect_evidence(claim: TestableClaim, rulebook: AxisRulebook, epoch_id: number): Result<EvidenceChain, L2VerificationError>;
}
interface LogicalAuditor {
  audit_logic(claim: TestableClaim, epoch_id: number): Result<LogicAuditResult, LogicAuditError>;
  // 注意：LogicalAuditor 不返回 EvidenceChain！它返回逻辑审查结果，如何转换为 EpochDelta？
}
```

**已知的具体崩溃场景**：

```
场景：CC 将一个来自 STRUCTURAL 张力的草稿编译为 TestableClaim：
  claim = {
    claim_id: "claim-015",
    falsifiable_statement: "碳排放配额系统在公理上要求总量上限必须先于分配规则确定",
    verification_protocol: "LOGICAL_AUDIT",   // 纯逻辑主张，不需要实证文献
    ...
  }

当前 D2 行为（忽略 verification_protocol）：
  → 调用 run_layer2_verification(claim-015, rulebook, epoch=5)
  → S4 证据收集：尝试在外部文档中搜索"碳排放配额系统公理"相关文献
  → 无实证文献（因为这是逻辑命题，不是经验命题）
  → 返回 L2VerificationError { code: "NO_EVIDENCE_FOUND" }
  → EpochDelta: { kind: "CLAIM_SUSPENDED", claim_id: "claim-015", reason: "无证据" }

期望行为：
  → D2 识别 verification_protocol = "LOGICAL_AUDIT"
  → 路由到 LogicalAuditor
  → 检查"总量上限先于分配规则"是否在给定公理系统下成立
  → 返回 EpochDelta: { kind: "CLAIM_VERIFIED", claim: VerifiedClaimFull { ... } }

错误影响：
  LOGICAL_AUDIT 类型的 claim 全部被错误地标记为 SUSPENDED，
  PAState 无法获得这类 claim 的评分，
  claim.coverage = 0，
  终止条件 avg_coverage < min_coverage，
  系统无法收敛
```

**需要裁定的具体问题**：

1. `LOGICAL_AUDIT` 验证器的输出类型是什么？它如何转换为 `EvidenceChain`（或者它是否产出不同的中间结构，由 D2 转换为 `EpochDelta`）？
2. `TARGETED_RECHECK` 验证器如何访问该 claim 之前的 `EvidenceChain`（需要从 `L1State` 传入已有证据吗）？
3. `run_layer2_batch()` 的签名是否需要修改（例如增加 `l1_state` 参数，让验证器能访问历史证据）？
4. 如果某个验证器尚未实现，D2 应该返回什么 `EpochDelta`（`CLAIM_SUSPENDED` 还是让 claim 继续保持 `PENDING` 状态等待实现）？

**设计约束供辩手参考**：

```typescript
// 已确立的 TestableClaim 类型（含 verification_protocol 字段）
interface TestableClaim {
  claim_id: ClaimId;
  source_draft_id: DraftId;
  falsifiable_statement: string;
  required_evidence_types: string[];
  verification_protocol: string;  // 来自 CC 的 verifier_type 值
  scope_boundary: string[];
  status?: "PENDING" | "VERIFIED" | "DEFENSIBLE" | "REJECTED" | "SUSPENDED";
}

// 已确立的 L2Return 结构（D2 的输出必须符合此格式）
interface L2Return {
  epoch_id: EpochId;
  deltas: EpochDelta[];
  size_bytes: number;   // 超过 32KB 时 L1 拒收
}

// 已确立的 EpochDelta 类型（D2 只能产出这几种事件）
type EpochDelta =
  | { kind: "GAP_OPEN"; gap: GapSpec }
  | { kind: "GAP_PATCH"; gap_id: GapId; patch: JsonPatch }
  | { kind: "GAP_CLOSE"; gap_id: GapId; resolution: string }
  | { kind: "SCHEMA_CHALLENGE_NEW"; ch: SchemaChallengeNotice }
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaimFull }
  | { kind: "CLAIM_SUSPENDED"; claim_id: ClaimId; reason: string };
```

**裁定目标**：给出完整的 D2 路由表设计，包含：
1. 每种 `verifier_type` 对应的验证器接口定义
2. `run_layer2_batch()` 函数的完整签名（是否需要增加参数）
3. 每种验证器的输出如何映射为 `EpochDelta`
4. 未实现的验证器的降级策略

**如果忽略这个 GAP 直接实现会发生什么**：所有 `LOGICAL_AUDIT`、`SCOPE_REVIEW`、`TARGETED_RECHECK`、`AXIS_CONSISTENCY_CHECK` 类型的 claim 全部走 `EMPIRICAL_CHECK` 路径。逻辑命题被当作经验命题验证，找不到实证文献就被标记为 `SUSPENDED`。PAState 中这类 claim 的 `coverage=0`，终止条件无法满足（因为这些轴无覆盖），CEGAR 闭环无法收敛。`verifier_type` 字段形同虚设，CC 精心分类的工作全部浪费。
