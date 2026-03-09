---
title: "v3 认知引擎：Layer 2 的 axis_scores 产出机制"
rounds: 3
cross_exam: 1
max_reply_tokens: 12000
timeout: 480
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}

debaters:
  - name: GPT-5.4
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是一位极端务实的系统工程师，Linux 内核风格的实现主义者。你坚信：没有可运行代码的
      设计就是白板涂鸦；任何「由 LLM 判断」的环节必须被包裹在可追溯的结构中。

      你对本议题的核心关切：
      - S2（深度分析）和 S4（深度探针）产出 axis_scores 的操作，如果底层是 LLM 评分，
        那整套归一化协议只是在一个不可靠的地基上搭建精密仪器——「把一个黑盒总分拆成多个
        黑盒分量」，类型丰富了但认识论不确定性没降低（这一风险在评分终止辩论裁判总结中
        已明确标注为「极高风险」）
      - evidence_chain 的最小格式：如果 claim_id 引用可以随意悬空（被引用的 claim 不存在
        或未被验证），evidence_chain 就是装饰性字段，不具备可审计性
      - 跨 epoch 一致性：同一条 claim 在相邻两个 epoch 里被 LLM 挂载到不同 axis 上，
        axis_score 跳变 0.4→0.8，这反映的是测量噪声还是实质变化？如何区分？
      - 认识论诚实性标注：「axis_score = 0.85」这个数字必须让消费侧（Layer 1 的 PA 节点）
        知道它来源于 LLM 评估还是结构化规则——来源不同，在 has_ranking_change() 的
        delta 计算中应当有不同的 epsilon 贡献

      你的立场倾向：
      - 规则引擎折算 > LLM 直接打分，理由：可重复、可审计、delta/epsilon 可从规则参数推导
      - evidence_chain 最小格式必须包含 claim_id（指向已通过 S2 的 VerifiedClaim）+
        具体文档片段定位（doc_id + offset 或 content hash）
      - 跨 epoch 一致性约束必须是硬性规则而非「建议」

      攻击风格：要求函数签名、具体公式、边界条件处理。对「LLM 综合判断」的任何回答追问
      「判断过程的输入输出类型是什么？失败时怎么处理？」对「语义保证」有生理性厌恶。

  - name: Gemini-3.1-Pro
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 v3 框架的核心设计者，CEGAR/MAX-SMT 背景，形式化方法研究者。你完整掌握 v3
      已确立的架构，并且理解认知系统与传统软件系统的根本差异：在证据验证领域，「完全确定
      的规则引擎」往往低估了自然语言证据的歧义性，而「完全依赖 LLM」又失去可审计性。

      你完整掌握的 v3 已裁定结论：
      1. Layer 2 命题级状态机：S1(Clarify)→S2(Depth)→S3(Precision)→S4(DepthProbe)
         ↔S5(BreadthProbe)→S6(Verified)|S7(Suspended)|S9(SchemaChallenge)
      2. VerifiedClaim.axis_scores: Partial<Record<AxisId, number>>，每个已覆盖轴的
         评分∈[0,1]，由 Layer 2 根据结构化证据产出（评分终止辩论裁判总结已确立）
      3. 评分公式：score = base × quality × coverage^GAMMA（已裁定）
      4. 评分终止辩论已明确标注：Layer 2 → axis_scores 映射是「风险等级极高」的模块，
         「LLM 分数不等于客观真相」必须在接口层标注

      你的核心主张：
      - S2/S4/S5 节点应采用「两阶段协议」：LLM 负责证据发现（自然语言 → 结构化证据节点），
        规则引擎负责分值折算（结构化证据节点 → axis_score 数值）。
        两阶段分工解决了 LLM 的语义理解优势与规则引擎的可审计优势之间的矛盾
      - evidence_chain 的最小格式应包含：claim_id（已验证来源）、doc_fragment（证据片段
        定位）、axis_mapping（明确宣告这条证据与哪个 axis 相关）、confidence（折算信心）
      - 跨 epoch 一致性约束：同一 claim 相邻 epoch 的同一 axis 分数变化超过阈值 τ，
        触发「漂移审核标记」（drift_flag），消费侧（PA 节点）在 delta 计算中对该 claim
        的 epsilon 贡献上浮

      你最不确定的点：
      - 规则引擎的折算规则从哪里来？是在问题框架定义时预声明（axis_scoring_rules 字段），
        还是从 evaluation_axes 的 falsifier 推导，还是有通用默认规则？
      - 当 evidence_chain 中的某条 claim_id 引用在下一个 epoch 被 suspend（
        SuspendedClaim）时，依赖它的 axis_score 是否需要自动降级？

      攻击风格：直接指出对手方案的类型错误和接口设计缺陷。对「完全规则化」的方案追问「规则
      从哪里来？谁来维护？」对「完全 LLM 化」的方案追问「epsilon 怎么推导？delta 怎么校准？」

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。目标是得出 Layer 2 axis_scores 产出机制的
  可实现规范，包括：节点职责划分、evidence_chain 最小格式、跨 epoch 一致性约束、认识论
  诚实性标注接口。

  禁止：
  - 纯原则性陈述——每个主张必须包含至少一个可计算的结构定义或接口规范
  - 重新讨论已裁定结论（评分公式、Layer 1/2 分离架构、VerifiedClaim 类型骨架、
    精度引擎纯路由、has_ranking_change 的双重终止条件）
  - 「由 LLM 综合判断」作为终止方案，LLM 判断必须被包裹在可追溯的结构中
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对以下四个核心问题至少一个的明确立场（有类型定义或公式支撑）：
     - 问题 I：S2/S4/S5 节点的 axis_scores 产出方式（LLM 直接打分 vs 规则引擎折算 vs 两阶段）
     - 问题 J：evidence_chain 的最小格式规范（必要字段、可选字段、语义约束）
     - 问题 K：跨 epoch axis_score 一致性约束（阈值来源、触发条件、处理机制）
     - 问题 L：认识论诚实性标注（axis_score 来源类型、epsilon 分层、消费侧协议）
  2. 对至少一个对手论点的精确攻击（指名，引用对手文本，指出具体类型错误或接口漏洞）

  所有主张必须附可推翻条件（什么样的运行数据或场景能证明你的方案失败）。

round1_task: |
  第一轮：选择问题 I（axis_scores 产出方式）或问题 J（evidence_chain 格式）中你认为
  更关键的一个，给出完整立场。

  必须包含：
  1. 你的核心主张——不是原则，是具体的类型定义和处理流程（伪代码/TypeScript，10-30 行）
  2. 你方案在以下边界场景下的行为：
     - 当自然语言证据明确涉及某个 axis，但强度无法用规则精确量化时（如「大量用户反映
       满意度提升」vs「满意度提升 23%，N=1200，p<0.01」）
     - 当同一条证据可能同时关联多个 axis 时（如「采用微服务后部署频率提升 3 倍，
       运营成本降低 15%」——同时覆盖交付速度轴和运营成本轴）
  3. 你方案的已知最弱点及其缓解方案
  4. 对至少一个对手可能采用方案的预攻击（指出其具体失败场景）

middle_task: |
  中间轮：吸收第一轮攻击，深化并补充另外 1-2 个问题的立场。

  必须包含：
  1. 回应对你方案的最强攻击（精确承认被击中的部分，并给出修正或反驳）
  2. 补充问题 K（跨 epoch 一致性）和/或问题 L（认识论诚实性）的完整立场
  3. 一个具体的 20 行以内运行案例：
     输入：一条 TestableClaim「采用微服务可将部署频率提升 3 倍」
     展示：该 claim 在 S2→S4 节点的完整处理流程，包括 evidence_chain 如何被构建，
           axis_scores 如何从证据折算，以及跨两个 epoch 后 一致性检查如何触发（或不触发）
  4. evidence_chain 的精确类型定义（TypeScript）——包含所有字段名、类型、语义约束

final_task: |
  最终轮：给出 Layer 2 axis_scores 产出机制的完整设计方案。

  必须包含：
  1. 问题 I/J/K/L 四个设计决策的明确立场和最终理由
  2. S2/S4/S5 节点的完整处理协议（输入类型、axis_scores 产出方式、输出类型、失败分支）
  3. EvidenceChain 的完整类型定义（含所有必要字段、可选字段、不变式约束）
  4. 跨 epoch 一致性检查的完整实现（触发条件、阈值来源、处理后的状态变更）
  5. axis_score 的认识论诚实性标注协议：什么字段记录来源类型，消费侧（PA 节点）如何根据
     来源类型调整 epsilon？
  6. 一个端到端的运行 trace：从 TestableClaim 输入 Layer 2，经过 S2→S4（或 S4↔S5）
     状态转移，到 VerifiedClaim（含完整 axis_scores 和 evidence_chain）产出
  7. 你的方案最可能在什么具体场景下失败，以及接受什么样的运行数据来推翻它

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**

  本轮辩题是 Layer 2 如何将自然语言证据转化为数值 axis_scores。裁判必须用「完全不懂
  编程的人也能理解」的语言解释最终裁定。

  建议类比框架：
  - axis_score 产出方式：类比「学生论文评分」——是让教授直接给一个综合分（LLM 直接打分），
    还是先列出评分细则（规则引擎），再照单打分？还是「教授看论文，助教按细则核对打分」（两阶段）？
  - evidence_chain：类比「判决书的证据链」——最少需要引用哪些内容才算「有据可查」？
    「综合来看证据充分」算不算？
  - 跨 epoch 一致性：类比「同一道菜在两次评分中相差 40 分」——是评委标准变了，还是菜真的变了？
    系统如何区分？
  - 认识论诚实性：类比「估算值」vs「测量值」——消费侧有权知道这个数字是怎么来的

  每个裁定必须包含：
  a. 明确的设计选择（不得搁置）
  b. 至少一个具体例子（给定一条具体证据，展示裁定方案如何处理）
  c. 哪些场景下裁定可能需要修正（诚实标注不确定性）
  d. 一句话总结

  **第二部分：可实现性摘要**

  必须产出以下内容：

  1. **S2/S4/S5 节点的 axis_scores 产出协议**（含：
     - 节点职责划分（哪个节点负责什么）
     - axis_score 产出的具体流程（LLM 阶段 + 规则阶段，或其他方案）
     - 输入/输出类型定义（TypeScript））

  2. **EvidenceChain 的最终类型定义**（含：
     - 所有字段名、类型、语义约束
     - claim_id 引用的完整性保证机制
     - 多 axis 关联的处理方式）

  3. **跨 epoch 一致性约束的最终规范**（含：
     - 触发审核的阈值 τ 来源（从哪里推导？谁来声明？）
     - 触发后的状态变更（drift_flag 的下游影响）
     - 相邻 epoch 的比对机制（按 claim_id 对齐）

  4. **认识论诚实性标注协议**（含：
     - axis_score 的来源类型字段定义（LLM_ASSESSED vs RULE_DERIVED vs HYBRID）
     - epsilon 分层机制（不同来源类型对应的测量不确定性默认值）
     - 消费侧（PA 节点）如何消费 score_provenance 调整 delta 计算）

  5. **一个完整的运行 trace**（输入：一条具体的 TestableClaim，展示：
     - S2 节点如何提取结构化证据
     - S4 节点如何折算 axis_score
     - evidence_chain 的完整内容
     - 跨两个 epoch 时一致性检查的触发或不触发过程）

  6. **实现难度最高的 2 个子模块及其风险**

  对问题 I/J/K/L 四个设计决策必须各给出明确的最终裁定，不得搁置。

---

# v3 认知引擎：Layer 2 的 axis_scores 产出机制

## 一、整体系统背景（完整概述）

本议题围绕 Layer 2 内部如何将自然语言证据转化为数值 axis_scores 展开。为了让读者无需阅读其
他文件就能完整理解讨论背景，以下先介绍 v3 整体架构与数据流，再说明 axis_scores 在其中的位置
与尚未解决的问题。

### 1.1 v3 系统的目标与核心挑战

v3 认知引擎旨在处理开放式、有争议的复杂问题——例如「AI 是否应该开源」「城市该投资地铁还是自
动驾驶」「远程办公是否提高生产力」——并产出多视角、辩护完备的答案体系，而非简单的是/否结论。

系统的核心工作流程是：将一个问题分解为多条可验证的具体命题（称为 TestableClaim），对每条命题
进行深度追溯和精度检测，最终按照预先声明的评估维度（evaluation_axes）对验证结果排序，输出结
构化答案。

### 1.2 两层分离架构

v3 采用**两层分离架构**（已在 topic1 辩论中最终裁定）：

**Layer 1（问题级处理层）**——薄状态机，负责问题分解、命题派发、结果聚合和终止判定：

```
QN（QuestionNormalizer，问题规范化）
  → MB（MacroBreadth，宏观广度探索）
  → CC（ClarityCompiler，清晰度编译）
  → D2（Layer2Dispatch，派发到 Layer 2）
  → PA（PrecisionAggregator，精度聚合）    ← 消费 axis_scores，驱动 has_ranking_change()
  → RB（RepairBreadth，修复回退，可选）
  → AS（AnswerSynthesis，答案综合）
```

**Layer 2（命题级处理层）**——v2 十状态机，处理每一条具体的 TestableClaim：

```
S1(Clarify) → S2(Depth，深度分析) → S3(Precision，精度检测)
  → S4(DepthProbe，深度探针) ↔ S5(BreadthProbe，广度探针)
  → S6(Verified) | S7(Suspended) | S9(SchemaChallenge)
```

**两层之间的信息流向**是双向的：
- Layer 1 → Layer 2：以 `DispatchBatch` 打包 `TestableClaim[]` 下发
- Layer 2 → Layer 1：以 `L2Return` 回传验证结果（含 `VerifiedClaim[]`，其中包含 `axis_scores`）、
  缺口信号（`GapSpec`）、图型挑战（`SchemaChallengeNotice`）等

### 1.3 axis_scores 在架构中的关键地位

`axis_scores` 是连接 Layer 2 的验证工作和 Layer 1 的排序终止判定的核心桥梁：

```
Layer 2 验证证据
  → VerifiedClaim.axis_scores: Partial<Record<AxisId, number>>   ← 本议题的焦点
  → Layer 1 PA 节点消费 axis_scores
  → 计算 VerifiedClaim.score（按已裁定公式）
  → has_ranking_change() 判定排序是否稳定
  → 终止或继续迭代
```

**评分公式（已裁定，来自评分终止辩论裁判总结）**：

```
GAMMA = 0.5   // 覆盖率惩罚指数，可由 QuestionFrame 预声明覆盖

coverage = sum(axis.weight for covered axes)
base = sum(axis.weight * axis_scores[axis_id] for covered axes) / coverage
quality = status_factor(status) * (1 - residual_risk)
score = base * quality * coverage^GAMMA
```

这个公式已经确立了 `axis_scores` 的消费方式。但**四份已有决策文件均未定义**：
`axis_scores` 中的每个数值是怎么来的——Layer 2 内部的 S2/S4/S5 节点如何将自然语言证据转
化为 `∈ [0, 1]` 的数值，以及支撑这些数值的 `evidence_chain` 应具备怎样的最小格式。

### 1.4 Layer 2 内部状态机的节点职责（已确立部分）

Layer 2 的五个关键状态节点的已知职责：

- **S1（Clarify）**：接收 TestableClaim，验证其结构完整性（claim/scope/assumptions/
  falsifier/non_claim/verifier_requirements 六要素），不通过则反弹到 Layer 1
- **S2（Depth，深度分析）**：对 claim 展开深度搜索，找出相关证据（supporting observables），
  验证 claim 的根基是否稳固。这是**产出初步 axis_scores 的关键节点**（具体机制未定义）
- **S3（Precision，精度检测）**：检测 claim 之间的冲突和矛盾，是纯路由器，`graph_delta`
  永远为 `null`，任何改写走独立 `RewriteStep`（已裁定）
- **S4（DepthProbe，深度探针）**：在 S2 建立的基础上进行更深层的证据探测，产出 GapSpec 信号
  （什么方向的证据还不足），并**更新 axis_scores**（具体机制未定义）
- **S5（BreadthProbe，广度探针）**：探索相关但非直接的证据方向，可能覆盖新的 axis（之前 S2
  未能识别的覆盖关系），并**补充或修订 axis_scores**（具体机制未定义）

**已裁定的 VerifiedClaim 类型**（来自评分终止辩论）：

```typescript
interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;                          // ∈ [0, 1]
  axis_scores: Partial<Record<AxisId, number>>;   // 每个已覆盖轴的评分 ∈ [0, 1]
  // axis_scores 中不存在的 key = N/A（该 claim 不涉及该轴）
  // axis_scores 的值由 Layer 2 根据结构化证据产出 ← 本议题的焦点
}
```

---

## 二、已裁定的系统约束（直接继承，不再讨论）

以下结论在 v3 系列辩论中已确立，本轮完全继承：

1. **精度引擎是纯路由器**：S3 节点的 `graph_delta` 永远为 `null`，任何 claim 改写走独立
   `RewriteStep`（含 `semantic_diff` 和 `source_claim_id`）
2. **axis_weight 必须在 QuestionFrame 中预声明**：不得由 Layer 2 运行时发明权重
3. **axis_scores 的 N/A 处理**：不存在的 key = 该 claim 不涉及该轴，N/A 轴不参与分子分母，
   但通过 `coverage^GAMMA` 间接惩罚总分
4. **终止条件**：`has_ranking_change() == False` 且不存在阻塞性 GapSpec，连续 2 轮满足则终止
5. **GapSpec 阻塞终止**：高权重轴完全无 claim 覆盖（UNCOVERED_HIGH_WEIGHT_AXIS）等情况会
   阻止终止，系统必须继续探索
6. **评分终止辩论已明确标注的「极高风险」**：
   > Layer 2 → axis_scores 映射是整个系统中最难、风险最高的环节。如果 axis_scores 的值最
   > 终由 LLM 「评估」产出，那整个精密的归一化协议只是在一个不可靠的地基上搭建精密仪器。
   > 系统把「一个黑盒总分」拆成了「多个黑盒分量」，类型上更丰富了，但认识论上的不确定性并
   > 未降低。缓解方向：要求 Layer 2 对每个 axis_score 附带 evidence_chain，引入跨 epoch
   > 一致性检查，长期方向是用结构化规则引擎替代 LLM 做 axis-claim 映射。

---

## 三、四个核心未决问题（本轮辩论焦点）

### 问题 I：S2/S4/S5 节点的 axis_scores 产出方式

**已知**：S2 是深度分析节点，S4 是深度探针节点，S5 是广度探针节点，三者都可能更新 claim 的
`axis_scores`。但具体产出方式有三种主要选项：

**选项 I-A：LLM 直接输出分值**

S2/S4/S5 节点在完成证据搜索后，将证据摘要和 claim 文本一并交给 LLM，让 LLM 对每个关联 axis
直接输出 0-1 的数值评分。

- 优势：实现简单；能处理证据语义复杂、无法规则化的场景
- 风险：分数不可解释、不可重复、跨 epoch 标注漂移（同一证据不同 epoch 可能被 LLM 挂载到不同
  axis 上，分数差异反映的是 LLM 噪声而非实质变化）；delta/epsilon 无法从 LLM 评分过程推导

**选项 I-B：规则引擎折算证据强度**

S2/S4/S5 节点只负责将自然语言证据解析为结构化证据节点（claim_strength 标签、sample_size、
significance_level 等），评分由预定义的规则引擎按证据属性折算出 axis_score 数值。

- 优势：可重复、可审计；epsilon 可从规则参数推导
- 风险：规则从哪里来？谁维护？「大量用户反映满意度提升」这类模糊证据如何规则化？

**选项 I-C：两阶段协议（LLM 证据发现 + 规则折算）**

第一阶段：LLM 负责将自然语言证据转化为结构化证据节点（`EvidenceNode`），包含 evidence_type、
strength_indicators、axis_mapping；
第二阶段：规则引擎根据 `EvidenceNode` 的结构化属性折算出 `axis_score` 数值。

- 优势：结合了 LLM 的语义理解和规则引擎的可审计性
- 风险：两个阶段之间的接口设计复杂；LLM 的第一阶段输出质量仍然影响最终分数

**未决定**：哪种方案是三个节点（S2/S4/S5）应采用的方式？S2、S4、S5 应该统一协议还是各有差异？

### 问题 J：evidence_chain 的最小格式规范

**已知**：评分终止辩论裁判总结中提出了 `evidence_chain`（证据链引用）的概念，作为「使 PA
可审计数值来源」的缓解策略。但具体格式从未被定义。

**核心未决点**：

- **claim_id 引用的完整性**：evidence_chain 中的 `claim_id` 应该引用什么？是引用
  Layer 2 内部处理中的中间 claim（如正在验证中的 VerifiedClaim），还是引用外部已
  存档的文档？引用的 claim 若后来被 Suspend，依赖它的 axis_score 如何处理？

- **证据定位粒度**：evidence_chain 是否需要包含具体的文档片段定位（doc_id + offset 或内容
  哈希）？还是仅引用来源文档 ID 就足够？粒度越细，实现成本越高，但可审计性越强。

- **多 axis 关联处理**：单条证据「采用微服务后部署频率提升 3 倍，运营成本降低 15%」同时覆盖
  「交付速度」和「运营成本」两个 axis。evidence_chain 是否需要显式声明每条证据关联哪些 axis？
  还是由节点处理时动态推断？

- **最小化与可审计性的权衡**：最小格式意味着实现成本低但信息不足；完整格式意味着更强的可审
  计性但实现复杂。什么是「足够最小」的格式？

### 问题 K：跨 epoch axis_score 一致性约束

**已知**：评分终止辩论裁判总结指出了「跨 epoch 标注漂移」风险：

> 同一条证据在不同 epoch 可能被 LLM 挂载到不同 axis 上，导致排序变化反映的是标注噪声而非实
> 质证据变化。缓解策略：引入 axis_score 的跨 epoch 一致性检查——同一 claim 在相邻 epoch 的
> axis_scores 变化超过阈值时触发人工审核标记。

但这个「一致性检查」的具体机制从未被定义。

**核心未决点**：

- **阈值 τ 的来源**：触发「漂移审核」的阈值 τ 应该怎么确定？是固定值（如 0.3）？是从
  `EvaluationAxis.epsilon` 推导？是从历史运行数据校准？不同问题域（精确科学 vs 开放社会问题）
  的合理 τ 差异可能极大。

- **触发后的处理机制**：当检测到漂移时，系统应该怎么处理？
  - 仅记录 drift_flag，让消费侧（PA 节点）知道？
  - 强制要求 S2/S4 重新验证该 claim 并重新产出 axis_score？
  - 暂停该 claim 的参与排序，降级为 SuspendedClaim？
  - 触发人工审核（不适用于自动化系统）？

- **漂移的方向性**：axis_score 从 0.4 上升到 0.8 和从 0.8 下降到 0.4，两个方向的漂移含义
  不同（前者可能是新证据支撑，后者可能是新反证出现）。一致性检查是否需要区分方向？

- **epoch 比较的对齐方式**：当某个 claim 在 epoch N 没有 axis_score（因为该轴未被覆盖），
  epoch N+1 突然出现了 axis_score，这是「漂移」还是「正常的新发现」？

### 问题 L：axis_scores 产出的认识论诚实性标注

**已知**：评分终止辩论裁判总结明确指出：

> 总分（score）是在特定 QuestionFrame.evaluation_axes 权重声明下的投影值，不是 claim 的内
> 禀属性。改变权重声明会改变 score。这一审计约束必须在系统的审计输出中明确标注。

同时，评分终止辩论明确指出「LLM 分数不等于客观真相」必须在接口层标注——但从未定义具体如何标注。

**核心未决点**：

- **来源类型标注**：axis_score 的值域已确定（[0, 1]），但消费侧（PA 节点）需要知道这个值是
  「LLM 直接打分」「规则引擎折算」还是「两阶段混合」，因为不同来源类型对应不同的测量不确定性
  （epsilon），进而影响 `has_ranking_change()` 的 delta 计算。这个来源类型应该存储在哪里？
  是在 `VerifiedClaim` 的字段中，还是在 `evidence_chain` 的每条记录里？

- **epsilon 分层**：评分终止辩论的公式中，`EvaluationAxis.epsilon` 表示该轴的归一化测量不
  确定性，用于计算 `delta = alpha * Σ(w_a * epsilon_a)`。但如果 axis_score 的来源类型不同
  （LLM 直接打分 vs 规则折算），同一个 axis 在不同 claim 上的 epsilon 应该不同。这如何处理？

- **消费侧协议**：PA 节点在调用 `has_ranking_change()` 时，需要 `EvaluationAxis.epsilon`
  作为输入。如果 epsilon 依赖 axis_score 的来源类型，而来源类型存储在 `VerifiedClaim` 层
  面，PA 节点如何聚合多条 claim 的来源信息并计算一个合理的 epsilon？

---

## 四、关键张力地图

```
axis_scores 产出方式张力：
  LLM 直接打分
    优势：处理语义复杂证据，无需预定义规则
    风险：分数不可重复；epsilon 无法从过程推导；同一证据不同 epoch 被挂载到不同 axis

  规则引擎折算
    优势：可重复、可审计；epsilon 可推导
    风险：规则从哪里来？「模糊证据」如何规则化？规则维护成本

  两阶段协议
    优势：结合双方优势
    风险：两阶段接口设计复杂；LLM 输出质量仍传染最终分数

evidence_chain 格式张力：
  最小化（claim_id + 来源 doc_id）
    优势：实现简单
    风险：doc_id 无定位粒度，无法精确审计；无法处理多 axis 关联

  完整结构（claim_id + doc_fragment + axis_mapping + confidence）
    优势：强可审计性
    风险：实现成本高；LLM 填充这些字段的准确性本身成为新的可靠性问题

跨 epoch 一致性张力：
  硬阈值触发审核
    优势：简单、可操作
    风险：τ 的来源是魔法数字问题的复现

  从 epsilon 推导 τ
    优势：有语义根基
    风险：epsilon 本身的来源又是一个悬空引用

认识论诚实性标注张力：
  claim 级标注（score_provenance 字段在 VerifiedClaim 中）
    优势：标注与使用数据同层
    风险：PA 节点需要聚合多条 claim 的来源才能计算 delta

  axis 级标注（epsilon 按来源类型分层）
    优势：与 delta 计算直接对齐
    风险：同一 axis 的不同 claim 可能有不同来源类型，聚合逻辑复杂
```

---

## 五、开放性陈述

本轮辩论不预设任何问题的答案。两位辩手被邀请对上述未决点提出各自的完整方案，并对彼此方案的
具体缺陷展开精确攻击。

对于任何方案，以下问题是可推翻条件的检验标准：

1. 给定一条具体的 TestableClaim「采用微服务可将部署频率提升 3 倍」以及两条原始证据（一条有
   精确数据支撑，一条是模糊的用户反馈），你的 axis_scores 产出方案能给出确定的
   `axis_scores: { "delivery_speed": number }` 吗？两条证据会产出不同的分值吗？

2. 同一条 claim 在 epoch N 的 `axis_scores["delivery_speed"] = 0.45`，epoch N+1 变为
   `0.82`。你的一致性检查方案会触发审核吗？触发后系统状态如何变更？

3. axis_score 来源于「LLM 直接打分」时，PA 节点在计算 `delta = alpha * Σ(w_a * epsilon_a)`
   时，`delivery_speed` 轴的 epsilon 应该是多少？来源于「规则折算」时呢？这个差异由谁来
   声明、存储在哪里？
