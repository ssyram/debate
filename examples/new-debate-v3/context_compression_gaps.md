---
title: "v3 认知引擎：上下文压缩续跑——五个未裁定点"
rounds: 2
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
  这是上一场 context_compression 辩论的续跑，聚焦于前次未充分裁定的五个具体问题。

  禁止：
  - 重新讨论已裁定内容（evidence_chain Watermarked Ledger、pinned_conflicts 机制、
    RehydrateError 接口、混合触发条件、ranking_history 滑动窗口等均已裁定，不得再辩）
  - 纯原则性陈述——每个主张必须伴随至少一个具体接口定义、阈值数字或类型形状变化
  - 稻草人攻击——交叉质询中必须引用对手的具体文本或接口定义
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对五个待裁定点中至少两个的具体立场（有数字或接口支撑）
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）
  3. 所有主张必须附可推翻条件

round1_task: |
  第一轮：针对五个待裁定点，给出你的初始立场。

  对每个你选择讨论的点，必须包含：
  1. 具体的裁定结论（是/否/有条件），附数字或接口定义
  2. 支撑该结论的核心论据（一句话，不需要铺垫）
  3. 该结论的可推翻条件

  同时，对至少一个你认为对手会犯的错误，提前给出反驳。

  鼓励质疑"这个点到底是不是真正的问题"——如果你认为某个待裁定点本身就是假问题，
  直接说出来并给出理由。

final_task: |
  最终轮：给出完整的五点裁定提案，作为提交给裁判的最终立场。

  格式要求：
  1. 对每个点（A/B/C/D/E）给出明确的裁定结论——不得搁置
  2. 每个裁定附：触发条件（如有）、具体数值或接口规格、失败行为
  3. 指出本轮辩论中对手论证改变了你哪些初始立场（承认被击中，精确反驳打偏的）
  4. 给出你认为最难裁定的一个点，以及裁判应该特别关注的对立证据

judge_instructions: |
  裁判必须对五个待裁定点（A/B/C/D/E）逐一给出明确裁定，不得搁置任何一点。

  **每个裁定必须包含**：
  1. 结论（一句话）：该点是否是真实问题，以及推荐的具体解决方案
  2. 关键分歧：辩手在此点上的核心对立，以及裁判如何取舍
  3. 具体规格：触发条件（数值）、接口形状（TypeScript）、失败行为
  4. 可推翻条件：什么情况下此裁定需要修正

  **额外要求**：
  - 如果某个待裁定点经辩论后被确认为假问题，裁定必须明确说明"此点不成立，理由是…"
  - 裁定中引用辩手的具体论据（指名），不得做模糊的综合性归纳
  - 最后给出五点裁定的优先级排序（按实现紧迫性）
---

# v3 认知引擎：上下文压缩续跑——五个未裁定点

## 一、前序裁定摘要（已裁定，不再辩论）

上一场辩论（`context_compression.md`）已对 v3 认知引擎的主要上下文爆炸点给出裁定。
以下是已确立结论，本场辩论不得重新开启。

### 1.1 已裁定内容（简表）

| 议题 | 裁定结论 |
|------|----------|
| **evidence_chain 压缩形态** | Ssyram 的 **Watermarked Ledger** 胜出，吸收 Linus/Kant 的 StrengthCounts。形态：`counts_pro/con`（按 strength 分桶计数）+ `watermarks_pro/con`（每桶最多 1 个代表性 Atom 文本）+ `pinned_conflicts`（未解决冲突钉在热区）+ `archive_ref`（冷区引用）。每 axis 最多 8 个 watermark atom，空间严格有界。 |
| **冲突固化（Pinning）机制** | Ssyram 胜出。S4 检测到 `EVIDENCE_CONFLICT` 后，将冲突对钉入 `pinned_conflicts`，驻留热区直到 `repair()` 显式解决。布尔标记方案（Linus）被否决，因无法区分跨 scope/discriminator 的极性差异。 |
| **冷区再水合（RehydrateError）接口** | Linus 胜出。明确定义 `RehydrateError { kind: "MISSING_REF" \| "IO_FAIL" \| "DECODE_FAIL" \| "INTEGRITY_CHECK_FAIL" }`，rehydrate 失败时 S4 **必须**进入 `S7(Suspended)`，**禁止**静默降级为"无冲突"。 |
| **压缩触发条件** | 混合触发：Linus 的 token 硬上限（`max_hot_atoms_per_claim = 50`, `max_total_atoms_per_claim = 200`）为不可违反的安全网，Kant 的信息增益低（最近 3 epoch 新增 atom 未改变任何 axis 的 polarity 或 max_strength）为提前压缩的优化触发器。两者取 OR。 |
| **ranking_history** | 滑动窗口（最近 5 epochs）。三人共识，直接采纳。 |
| **rejection_history** | 保持现状（哈希集合），监控集合大小即可。 |
| **ChallengeTracker** | 按状态分桶，只有 ACTIVE 的进 prompt。 |
| **L1 对话历史** | Linus 的 `PromptMaterializer + ContextBundle` 方案覆盖此需求，采纳。 |
| **Judge prompt** | 按需注入（裁判调用时）。 |

### 1.2 本场聚焦

上一场裁定遗留了五个具体子问题，每个均有明确的待裁定内容。以下第二节详细描述这五个问题。

---

## 二、五个待裁定点

### 待裁定点 A：L2Return 是否是独立爆炸点？

**问题背景**：

`L2Return` 是 Layer 2 每个 epoch 返回给 Layer 1 的结构：

```typescript
interface L2Return {
  verified_claims: VerifiedClaim[];
  suspended_claims: string[];
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  ranking_delta: { changed: boolean; details?: string };
  epoch_id: number;
}
```

每次 epoch 结束，Layer 2 产出一个 `L2Return`，Layer 1 的 `repair()` 和 `PA` 节点消费它。

**核心争议**：

L2Return 本身是否会随 epoch 累积形成上下文压力？有两种相反的判断：

**判断一（L2Return 是独立爆炸点）**：Layer 1 如果需要在 prompt 中注入"历史所有 epoch 的
gap 处理进展"，就需要拼接所有历史 L2Return 的 `new_gaps` 字段。随 epoch 增长，这个累积
内容会超出上下文窗口。

**判断二（L2Return 不是爆炸点）**：L2Return 是增量传递的——每次只传递当前 epoch 的新增内容
（`new_gaps` = 本 epoch 新发现的 gap，而非累积所有历史 gap）。Layer 1 接收后立刻消费并更新
自己的状态缓存，历史 L2Return 不需要在 prompt 中保留。换言之，L2Return 被"吸收"进 Layer 1
的状态管理，由 `PromptMaterializer` 的 `ContextBundle` 负责把当前状态的相关片段注入 prompt。
如果这个判断成立，L2Return 本身根本不需要独立的压缩策略。

**待裁定内容**：

1. L2Return 的传递模式是增量（仅当前 epoch 新增）还是全量（包含所有历史未解决 gap）？
2. 如果是增量，Layer 1 如何维护"当前所有未解决 gap 的完整状态"？状态缓存由谁管理，
   格式是什么？
3. 上一场裁定的 `PromptMaterializer` 方案是否已经覆盖了 L2Return 的注入问题？如果是，
   L2Return 不需要独立压缩策略。如果不是，缺口在哪里？

**鼓励质疑**：如果辩手认为"L2Return 根本不是爆炸点，这是一个假问题"，请直接给出理由。

---

### 待裁定点 B：rejection_history 无界增长时的上限保护

**问题背景**：

上一场裁定为"保持现状（哈希集合），监控集合大小即可"。但裁定未给出：

- **体积阈值**：集合超过多大时触发告警？（条目数？字节数？）
- **超限后的处理路径**：告警了做什么？

**上一场裁定的遗漏**：裁定指出"集合过大时告警"，但没有说告警后系统应该做什么。
这是一个开放的行动缺口。

**候选处理路径**（三选一或组合）：

**路径一：拒绝新 fingerprint 入库**。超阈值后，新的被 `is_homologous()` 判定同源的草稿
不再写入 fingerprint。代价：未来 epoch 中相同语义空间的草稿可能被重复产出。

**路径二：老化淘汰（LRU/FIFO）**。超阈值后，淘汰最旧（或最久未被查询命中）的 fingerprint。
代价：被淘汰的 fingerprint 对应的语义空间不再受保护，repair() 可能重复探索已否决方向。

**路径三：归档冷存储**。超阈值后，将旧 fingerprint 归档到冷区，热区只保留近期 fingerprint。
查询时若热区未命中，再查冷区。代价：查询延迟增加；冷区 IO 失败时行为未定义。

**待裁定内容**：

1. 具体体积阈值的来源：固定常数（给出推荐值）、QuestionFrame 配置项，还是动态计算？
2. 超限后的处理路径（从三选一中裁定，或说明组合方式）。
3. 处理路径的失败行为：无论选哪条路径，超限处理本身失败时系统状态是什么？

---

### 待裁定点 C：裁判 prompt 的完整压缩规格

**问题背景**：

上一场裁定为"按需注入"。这一句话等于没说——任何 prompt 都是"按需注入"的。
遗漏了三个关键子问题：

**子问题 C1：触发条件**。何时判定"裁判 prompt 太大，需要压缩"？候选：
- 轮次数超过阈值（例如 >5 轮时对前期轮次做结构化摘要）
- Token 计数超过裁判模型上下文窗口的某个比例（例如 60%）
- 两者混合

**子问题 C2：压缩策略**。触发后执行什么压缩？候选：
- 对旧轮次做 LLM 生成的结构化摘要（"第 N 轮：A 主张 X，B 反驳 Y，核心分歧 Z"）
- 完整保留最近 K 轮，对更早的轮次做摘要
- 按辩手立场分桶（只保留每位辩手在每个核心议题上的最终立场，丢弃中间轮次）

**子问题 C3：失败行为**。如果压缩后裁判输出质量不足（例如裁判遗漏了某个关键攻击），
系统如何检测和应对？

**待裁定内容**：

1. 触发条件（数值）
2. 压缩策略（从候选中选择，或给出新方案；需附接口或格式定义）
3. 失败行为（裁判输出质量不足时的应对路径，以及如何检测"质量不足"）

---

### 待裁定点 D：repair() LLM 上下文的压缩策略

**问题背景**：

`repair()` 在 RB 节点被调用时，给 LLM 的 prompt 包含多个随修复轮次增长的组件：

```typescript
// repair() 的 LLM prompt 构成（简化）
interface RepairPromptContext {
  gap_spec: GapSpec;                    // 当前 gap 的完整描述（相对稳定，但随精化可能更新）
  challenge_tracker: ChallengeTracker;  // 包含 attempted_scopes（随轮次线性增长）
  evidence_summary: string;             // 与 gap 相关的 claim 证据摘要（可能引用 CompressedEvidenceProfile）
  refinement_state: {                   // 精化阶段状态
    current_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
    consecutive_filtered_epochs: number;
  };
}
```

其中 `attempted_scopes`（`ChallengeTracker` 的字段）是主要增长来源：每次 repair() 失败，
都追加一条新的 scope 记录。

上一场裁定了"ChallengeTracker 按状态分桶，ACTIVE 进 prompt"，但未裁定当单个 ACTIVE
challenge 的 `attempted_scopes` 本身过长时如何处理。

**核心矛盾**：

- `attempted_scopes` 的价值是"告诉 LLM 哪些方向已穷尽，不要再往这些方向走"
- 如果列表过长（例如 ADJACENT 阶段尝试了 50+ 个方向），prompt 超限
- 但摘要化 `attempted_scopes` 存在风险：LLM 可能"忘记"具体的失败方向，在后续轮次中
  重复探索相同的语义子空间

**特别关注**：`EXHAUSTED` 状态的方向列表是否必须全量保留？理由是：EXHAUSTED 方向列表
代表"系统已经证明这个 challenge 无解"的证据——如果丢失，系统可能重新将其标记为 ACTIVE
并浪费算力重新探索。

**待裁定内容**：

1. `attempted_scopes` 中哪些内容可以压缩/摘要（例如 STRICT 阶段的早期尝试），
   哪些必须全量保留（尤其 EXHAUSTED 的方向列表）？
2. 触发压缩的条件（`attempted_scopes` 超过多少条时压缩？）
3. 压缩后的格式（摘要应该保留哪些关键信息？给出具体字段定义）

---

### 待裁定点 E：ChallengeTracker ACTIVE 数量阈值的具体值

**问题背景**：

上一场裁定了"ACTIVE 数量超阈值时注入 prompt"，但未给出：

- **阈值的具体来源**：是固定常数、`QuestionFrame` 的配置项，还是动态计算（例如基于
  当前 token 预算推导）？
- **超阈值时的选择策略**：如果 ACTIVE challenge 数量超过阈值，优先注入哪些？

**候选阈值来源**：

**方案一：固定常数**。例如 `MAX_ACTIVE_CHALLENGES_IN_PROMPT = 5`。优点：简单，行为可预测。
缺点：不适应不同规模问题（简单问题可能 5 个已经足够，复杂问题可能有 20+ 个 ACTIVE challenge）。

**方案二：QuestionFrame 配置项**。在 `QuestionFrame` 中增加 `max_active_challenges: number`
字段，由 QN 节点根据问题复杂度推断。优点：自适应。缺点：QN 节点需要估算问题复杂度，
这本身是一个 LLM 判断，不透明。

**方案三：动态计算（基于 token 预算）**。根据 repair() 的 token 预算（`prompt_token_budget`
的某个固定比例），动态计算最多能注入多少个 ACTIVE challenge。优点：直接与 token 上限挂钩，
不会超限。缺点：不同 challenge 的描述长度不同，计算复杂。

**候选选择策略**（超阈值时优先哪些 ACTIVE challenge）：

- **最老优先**（最早产生的 ACTIVE challenge）：优先解决最长期未解决的阻塞
- **阻塞性优先**（`blocks_termination = true` 的 gap 对应的 challenge）：优先解除终止阻塞
- **最近精化失败次数最多的**：优先投入资源解决最顽固的 challenge

**待裁定内容**：

1. 阈值来源（从三个方案中裁定，或提出新方案）及具体数值（如有）
2. 超阈值时的选择策略（从候选中裁定）
3. 选择策略的失败行为：如果被排除在 prompt 外的 ACTIVE challenge 导致系统做出错误判定，
   如何检测和恢复？

---

## 三、开放性说明

**关于"这到底是不是真正的问题"**：

以上五个待裁定点均由上一场辩论的遗漏推导而来，但这不意味着每个点都是真实的工程问题。
辩手被鼓励在论证中明确质疑某个点的问题性本身。

典型的质疑方向：

- **待裁定点 A（L2Return）**：最可能是假问题。如果 L2Return 确实是增量传递的，且 Layer 1
  有完善的状态缓存机制（已由 `PromptMaterializer` 裁定），那么 L2Return 根本不存在独立的
  上下文爆炸风险，此点不需要单独裁定。

- **待裁定点 B（rejection_history 上限）**：可能是被高估的问题。如果 rejection_history
  中的条目是 32 字节哈希，10000 条也只有约 320KB，不是内存或 prompt 问题，只是一个
  O(N) 查询时间问题——而 O(N) 查询在 N < 100000 的情况下通常不需要特殊处理。

- **待裁定点 C/D/E**：这三个点有具体的工程接口缺口，较难被否定为假问题，但仍欢迎质疑。

**鼓励辩手在第一轮就明确表态**：哪些点你认为是真实问题，哪些点你认为是假问题，以及
理由。这样裁判可以在更清晰的框架下做出裁定。
