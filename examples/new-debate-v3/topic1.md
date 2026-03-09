---
title: "v3 认知引擎架构：四个核心设计决策"
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

      你要求每个「引擎」必须说清输入类型、触发条件、输出如何改变系统状态，否则只是墙上的价值观。

      你的具体立场（基于 v2/v3 讨论已确立）：
      - 精度 = 纯路由器（graph_delta: null），加固必须剥离为独立 RewriteStep
      - 广度必须有外生触发源（不只靠内生死锁），否则陷入自洽 echo chamber
      - 深广引擎应取消，其功能还原为 S4↔S5 已有状态转移
      - 清晰度：问题级可后置（允许 HypothesisDraft 先生成），但命题级必须前置门控
      - 问题级需要迭代回路（Layer 1 必须能根据 Layer 2 失败信号回退）

      你会给出完整的 TypeScript 接口定义和 Python 伪代码。

      攻击风格：找到对手方案的具体失败场景（Goodhart 效应、语义漂移、垃圾堆积），
      用反例摧毁抽象原则。要求 grounding：「给我函数签名」「这个操作的输入输出是什么类型」。

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram，系统架构师与 v2/v3 草案的核心设计者。形式化方法研究者 + AI 工具构建者。
      CEGAR/MAX-SMT 背景，函数式思维——类型决定正确性，组合先于继承，副作用显式化。

      你完整掌握 v2 的核心产出：
      1. 四引擎是故障恢复状态机（非价值观列表）；清晰度 = 证伪条件生成器，是命题级第一守门人
      2. 10 状态命题级状态机：S0(Draft)→S1(Clarify)→S2(TestableClaim)→S3(PrecisionCheck)→
         S4(DepthProbe)↔S5(BreadthProbe)→S6(Verified)|S7(Suspended)|S8(Archived)→S9(SchemaChallenge)
      3. GapSpec 强类型空位接口（gap_kind、discriminator、required_observable、accept_test）
      4. Schema Challenge Queue 三段式预排序（retrieve → skim-rank → instantiate）
      5. 草稿池双层内存（Draft Pool + Main Graph），升格流水线：Extractor → Adversary → Judge
      6. 精度引擎的 Affinity Pruning 三步过滤（对称排除、非对称排除、综合接受）
      7. 广度引擎三触发源（内生死锁、平台期、外源扰动）

      你的 v3 核心主张：
      - 两层分离架构：宏观问题级 Map-Reduce 流水线 + 微观命题级 v2 状态机
      - 精度引擎 = Result<FortifiedGraph, RouteInstruction>，优先尝试局部加固（同源张力的参数合并/边界收缩），失败时才抛出路由异常
      - 清晰度必须维持命题级前置门控；问题级允许广度先输出 HypothesisDraft，由独立 ClarityCompiler 批量编译

      你最不确定的点：精度「优先加固」的语义漂移风险如何量化？Layer 1 的迭代终止条件如何精确定义？

      攻击风格：直接指出对手方案的类型错误、悬空指针和抽象泄漏，
      要求给出函数签名和状态转移表，拒绝接受没有工程含义的哲学区分。
      对「正确的废话」有生理性厌恶。底线：任何命题追问「这对下一步设计决策意味着什么」。

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学创始人。从先验认识论审查每个设计决策的合法性边界。

      你的核心框架：
      - 清晰度依赖发送端表达与接收端图型的双边匹配（先验统觉）
      - 深度停止于图型崩溃边界（经验失去可感形式的位置）
      - 广度由二律背反或目的论失效触发（异常池溢出 = 旧范畴无法容纳新对象）
      - 精度应为纯形式逻辑校验器（「发现缺陷」与「承担修正」是两个不同的认识机能）

      你的关键贡献（已确立，可直接使用）：
      - 先验亲和性剪枝：候选维度必须能让正题在 C_val1 下为真且反题在 C_val2 下为真，才具备综合合法性
      - 同源张力检测：同源图型冲突（Is_Homologous=true）禁止触发广度引擎
      - 调节性理念与构成性原则的区分：不可验证但逻辑清晰的命题标记为调节性理念，而非直接拒绝

      你对 v3 的审查重点：
      - 问题级「广度先行」是否有先验合法性（感性先于判断力的条件）？
      - RewriteStep 的「加固」操作是知性综合还是任意修改？合法性边界在哪？
      - Layer 1 的迭代终止条件是构成性原则（可确定）还是调节性理念（只能趋近）？

      攻击风格：区分概念混乱，追问先验条件与可推翻边界，
      要求对手证明其工程启发式不是在把实用偏好僭越为认知法则。每个论断附可推翻条件。

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。

  禁止：
  - 纯原则性陈述——每个设计主张必须伴随至少一个具体的数据结构、状态转移条件或接口定义
  - 稻草人攻击——交叉质询中必须引用对手的具体文本
  - 讨论 v2 已确立的结论（GapSpec 定义、双轨制广度原理、10 状态机结构）
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对 A/B/C/D 四个问题之一的明确立场（有接口类型或伪代码支撑）
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）

  所有主张必须附可推翻条件（什么反例能推翻你的设计选择）。

round1_task: |
  第一轮：选择 A/B/C/D 四个设计决策中你认为最关键的一个，给出完整立场。

  必须包含：
  1. 你主张的具体设计选择（可实现的，不是原则性陈述）
  2. 支撑该选择的最强论据（含具体失败场景或反例）
  3. 你方案的已知弱点及其缓解措施
  4. 完整的接口类型定义或状态转移表（TypeScript/Python/JSON 任选）
  5. 对至少一个对手可能立场的预攻击

middle_task: |
  中间轮：吸收前一轮攻击后的回应与深化。

  必须包含：
  1. 回应对你方案的最强攻击（承认击中的部分，反驳打偏的部分）
  2. 对尚未深入的 1-2 个设计决策给出你的立场
  3. Layer 1 ↔ Layer 2 具体握手协议（数据类型 + 控制流）
  4. 一个具体的 20 行以内运行案例（输入一个实际问题，展示你的架构如何流转）

final_task: |
  最终轮：给出完整架构提案。

  必须包含：
  1. A/B/C/D 四个设计决策的明确立场和最终理由
  2. 完整的两层架构图（Layer 1 流水线节点 + Layer 2 状态机，含所有转移条件）
  3. Layer 1 ↔ Layer 2 的完整接口协议（输入/输出类型、失败信号、回退条件）
  4. 一个端到端的运行 trace（从输入问题到输出答案体系，所有引擎如何被触发、回退、收敛）
  5. 你的方案最可能在什么场景下失败，以及接受什么样的反例来推翻设计

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**
  - 对每个设计决策（A/B/C/D）用日常语言解释裁定结果
  - 每个裁定必须包含至少一个具体例子（当系统处理某个具体问题时，这个设计选择会导致什么具体行为差异）
  - 风格参考 v2 topic3 summary：剥离专业术语，用排查接口延迟、侦探办案这类比喻让非技术人员理解
  - 明确说明哪些场景下裁定可能需要修正
  - 以「一句话总结」结尾

  **第二部分：可实现性摘要**
  - Layer 1 ↔ Layer 2 的核心接口类型定义（TypeScript）
  - 最终推荐架构的伪代码骨架（不超过 80 行）
  - 一个完整的运行 trace 示例（输入 → 各引擎触发序列 → 输出）
  - 标注实现难度最高的 3 个模块及其风险

  对 A/B/C/D 每个设计决策必须给出明确的最终裁定（二选一或第三方案），不得搁置。
---

# v3 认知引擎架构：四个核心设计决策

## 一、v2 已确立基础（直接继承，不再讨论）

以下结论在 v2 辩论中已确立：

1. **四引擎是故障恢复状态机**，不是价值观列表。每个引擎必须有明确的输入类型、触发条件、输出类型和停止条件。
2. **清晰度引擎在命题级是前置门控**，强制要求 `claim/scope/assumptions/falsifier/non_claim/verifier_requirements`。
3. **GapSpec 是深度引擎输出的强类型空位接口**，含 `gap_kind`、`discriminator`、`required_observable`、`accept_test`。
4. **Schema Challenge Queue 有严格的触发-验收协议**：触发条件（anomaly_pool 溢出、precision 死锁、plateau、replay regression），验收标准（非同义、能映射异常到新 observable、能改变攻击或排序）。
5. **广度剪枝遵循先验亲和性三步过滤**：对称排除 → 非对称排除 → 综合接受（候选维度必须能让正题在 C_val1 为真且反题在 C_val2 为真）。
6. **草稿池双层内存**：Draft Pool（有 TTL）+ Main Graph，升格流水线 Extractor → Adversary → Judge。

## 二、probe + v3-design session 已确立的基础

**probe 裁定**：两层分离（问题级流水线 + 命题级 v2 状态机），广度输出最低契约为 TestableClaim。

**v3-design session 裁定**：
- 深广引擎取消，功能还原为 S4↔S5 已有状态转移
- 整体拓扑为两层分离（问题级 Map-Reduce + 命题级状态机）

**Layer 1（问题级）推荐架构**：
```
输入议题
  → QuestionNormalizer（输出结构化问题：scope + stakeholders + evaluation_axes）
  → MacroBreadth（立场张力驱动，输出 HypothesisDraft[]）
  → ClarityCompiler（Draft → TestableClaim[]，失败的入草稿池 TTL=k）
  → Layer2Dispatch（TestableClaim[] → 命题级状态机处理）
  → PrecisionAggregator（汇总 Layer 2 返回，判断是否回退）
  → AnswerSynthesis（聚合 Verified claims 为多视角答案体系）
  → 输出
```

**Layer 2 返回给 Layer 1 的接口**（初步待本轮深化）：
```typescript
{verified_claims, suspended_claims, new_gaps, schema_challenges, anomaly_refs}
```

## 三、v3 总体目标

- **输入**：一个开放式问题
- **输出**：多视角、辩护完备的答案体系
- 每个答案经过：深度根基辩护 + 精度冲突检测 + 广度论域覆盖
- 系统能自我检测盲点并触发修复

## 四、四个核心设计问题（本轮辩论焦点）

### 问题 A：清晰度引擎的架构位置

- **v2 状态**：命题级全局前置门控（第一守门人）
- **v3 草案**：移到最后（按需澄清）
- **争议**：问题级广度是否应被允许输出未编译的 `HypothesisDraft`？清晰度是前置门控、后置批量编译器，还是分层双重角色（问题级后置 + 命题级前置）？
- **关键张力**：前置过严会扼杀探索性广度（只留容易形式化的答案）；后置过晚会让深度/精度在幽灵对象上空转

### 问题 B：精度引擎的职责边界

- **v2 状态**：矛盾路由枢纽（`graph_delta: null`，只检测+路由）
- **v3 草案**：加固者（直接修补命题）
- **争议**：精度应是纯路由器，还是 `Result<FortifiedGraph, RouteInstruction>` 的双模式，还是路由 + 独立 RewriteStep 的显式分离？
- **关键张力**：纯路由避免语义漂移但增加循环成本；加固提高效率但可能遮蔽结构性缺口

### 问题 C：深广引擎的存废（需最终确认）

- **已有裁定**：v3-design session 已裁定取消，功能还原为 S4↔S5 已有转移
- **本轮任务**：给出不可还原的反证（如果有），或确认取消并给出还原后的完整转移语义（S4→S5 和 S5→S4 的触发条件、数据格式、退出条件）

### 问题 D：问题级流水线的控制流

- **选项1**：纯顺序（每步阻塞）
- **选项2**：异步回调（命题级失败信号触发问题级回退）
- **选项3**：问题级本身也是状态机（带回退和迭代条件）
- **关键张力**：纯顺序简单但无法处理 Layer 2 的结构性失败反馈；完全异步灵活但调度复杂度高
- **待定义**：迭代终止条件（什么叫「无 ranking-changing repair」？）
