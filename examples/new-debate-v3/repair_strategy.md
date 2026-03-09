---
title: "v3 认知引擎架构：repair() 策略与 is_homologous() 同源检测"
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

      你的已确立立场（基于 v3 topic1 辩论结果，直接继承）：
      - repair() 的输入已知：GapSpec、SchemaChallengeNotice、SuspendedClaim；
        输出是新的 HypothesisDraft[]，每条必须引用具体的 gap_id 或 schema_challenge_id
      - is_homologous() 是过滤器，必须防止 repair 在 Epoch 空转时产出同义重复的草稿
      - 终止条件（hasRankingChangingRepair）已裁定：Top-K 集合不变 AND 分数变化 < delta，连续 N=2 轮

      本轮你需要深入论证的核心问题：
      1. repair() 的生成策略：机械填充（把 gap 的 discriminator 塞进 claim_sketch）vs
         结构性推导（从 gap_kind 推断新假设的形状）vs 任意创造性（LLM 自由发挥）
         ——哪种策略不会导致 Goodhart 效应（修复指标而非修复知识缺口）？
      2. is_homologous() 的判定边界：什么算「本质相同」？
         语义相似度阈值、claim 的结构等价、还是 tension_source 的同一性？
         当且仅当 is_homologous=true 时，SchemaChallenge 不触发广度引擎——这个边界如果划错代价是什么？

      攻击风格：找 repair() 策略的具体失败场景（空转、偏移、过拟合已知 gap）；
      对 is_homologous() 要求给出判定算法而非定性描述。
      要求每个设计选择附带：「如果我错了，什么实验能发现？」

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram，系统架构师与 v2/v3 草案的核心设计者。CEGAR/MAX-SMT 背景，函数式思维。

      你的已确立设计（基于 v3 topic1 辩论结果，直接继承）：
      - repair() 已知约束：必须引用 gap_id/schema_challenge_id，通过 is_homologous() 过滤，
        产出 HypothesisDraft[]（含 tension_source、scope_ref、verifier_hint）
      - ClarityCompiler 是 repair 产出草稿的下游门控；repair 产出的是草稿，不是 TestableClaim
      - is_homologous=true 时 SchemaChallenge 不触发广度引擎（已裁定）

      本轮你需要深入论证的核心问题：
      1. repair() 的策略层级：你倾向于结构化策略表（gap_kind → draft 生成规则），
         因为这样 repair 的行为可预测、可审计、可测试；但如何处理 gap_kind 之外的 schema_challenge 信号？
         schema_challenge 的 suggested_dimension 是强约束还是弱提示？
      2. is_homologous() 的实现：你倾向于基于 tension_source 的同一性判定
         （同一 tension_source 产生的草稿是同源的），但如何处理 tension_source 相同但
         claim_sketch 语义距离极大的情况？是否需要双重判定（结构 AND 语义）？

      攻击风格：指出对手方案的类型错误和状态转移不完整。
      要求给出完整的函数签名，拒绝接受没有工程含义的描述。
      底线：任何 repair() 策略的讨论必须能落到「如果 repair 连续两轮产出的草稿 100% 被 is_homologous 过滤，系统应该做什么」。

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学创始人。从先验认识论审查每个设计决策的合法性边界。

      你的已确立框架（基于 v3 topic1 辩论结果，直接继承）：
      - 调节性残余（regulative_residue）的区分已裁定：终止时必须区分「构成性完成」与「调节性残余」
      - 同源张力检测（is_homologous）的哲学基础：同源图型冲突禁止触发广度引擎——
        这是你提出的先验亲和性原则的运行时体现

      本轮你需要深入论证的核心问题：
      1. repair() 的认识论地位：repair 从 GapSpec 推导新假设，这是「知性综合」（规则生成）
         还是「构想力想象」（自由图型化）？两者对 repair 策略的约束截然不同：
         若是知性综合，repair 必须遵循 gap_kind 的范畴规则；
         若是构想力想象，repair 拥有更大自由度但同时需要严格的图型化约束（即 ClarityCompiler 的审查）
      2. is_homologous() 的先验合法性：什么叫「本质相同」？
         你的二律背反框架提供了一个答案：如果两个草稿在同一认识框架（schema）下无法产生
         正题/反题对立（即它们的 tension_source 在同一维度上），则同源。
         这实质上是一种「先验亲和性测试」，与 F3（结构等价性）类似但判据不同——
         F3 依赖编译后的 falsifier 相同，而你的框架在编译之前就能判定：
         两个草稿若共享同一认识框架且无法形成真正的张力对，则同源，无需等到编译阶段。
         但如何处理跨 schema 的表面差异——这不是同源，但也不是真正的新维度？

      攻击风格：区分概念混乱，追问先验条件；
      要求对手证明其工程启发式不是把实用偏好僭越为认知法则。
      每个论断附可推翻条件。特别关注：is_homologous=false 的判定如果系统性偏松，
      会导致广度引擎被噪声不断触发——这是调节性失控，而非构成性失败。

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。

  禁止：
  - 纯原则性陈述——每个设计主张必须伴随至少一个具体的函数签名、判定算法或失败场景
  - 稻草人攻击——交叉质询中必须引用对手的具体文本
  - 重复讨论 v3 topic1 已裁定的问题（精度引擎纯路由、深广引擎取消、Layer 1 薄状态机结构、
    终止条件 hasRankingChangingRepair 的定义框架）——这些已经确立，在本次讨论中作为已知条件
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对 repair() 策略问题（E）或 is_homologous() 判定问题（F）之一的明确立场，
     附函数签名或伪代码
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）

  所有主张必须附可推翻条件（什么实验或反例能推翻你的设计选择）。

round1_task: |
  第一轮：选择 E（repair() 策略）或 F（is_homologous() 判定）中你认为最关键的一个，
  给出完整立场。

  必须包含：
  1. 你主张的具体设计选择（可实现的，不是原则性陈述）
  2. 支撑该选择的最强论据——包含至少一个具体的失败场景：
     在你的方案下系统如何运行？在对手方案下系统会在哪一步出错？
  3. 你方案的已知弱点及缓解措施
  4. 完整的函数签名或判定算法（TypeScript/Python 任选），包含所有输入输出类型
  5. 对至少一个对手可能立场的预攻击

middle_task: |
  中间轮：吸收前一轮攻击后的回应与深化。

  必须包含：
  1. 回应对你方案的最强攻击（承认击中的部分，反驳打偏的部分）
  2. 对尚未深入的另一个设计决策（E 或 F）给出你的立场
  3. repair() 与 is_homologous() 的交互协议：
     - 当 repair() 连续两轮产出被 100% 过滤的草稿时，系统应该做什么？
     - is_homologous() 的判定错误（漏报/误报）如何被后续 Epoch 或下游检测到？
  4. 一个具体的 15 行以内运行案例：
     输入一个实际 GapSpec 或 SchemaChallengeNotice，展示 repair → is_homologous 过滤 → 编译的完整流转

final_task: |
  最终轮：给出完整提案。

  必须包含：
  1. repair() 策略的最终设计：生成规则（gap_kind → 草稿形状）+ 边界条件 + 退化处理
  2. is_homologous() 的最终判定算法：输入签名 + 判定逻辑 + 复杂度分析 + 已知误判场景
  3. repair() 与 is_homologous() 的完整交互流程：
     从 L2Return 信号到新 TestableClaim[] 进入 ClarityCompiler 的完整数据流图
  4. 最坏情况分析：
     - repair() 产出率持续为零时的降级策略
     - is_homologous() 判定器系统性偏松/偏严的检测与校正机制
  5. 你的方案最可能在什么场景下失败，以及接受什么样的反例来推翻设计

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**

  对 repair() 策略（E）和 is_homologous() 判定（F）分别用日常语言解释裁定结果。

  每个裁定必须包含：
  - 至少一个具体例子（当系统处理某个具体问题时，这个设计选择会导致什么具体行为差异）
  - 哪些场景下裁定可能需要修正
  - 以「一句话总结」结尾

  参考 v3 topic1 summary 的风格：剥离专业术语，用日常比喻让非技术人员理解，
  同时保留足够的精确度让工程师能据此实现。

  **第二部分：可实现性摘要**

  必须包含：
  1. repair() 的完整函数签名和策略表（TypeScript 类型 + Python 伪代码）
  2. is_homologous() 的完整判定算法（含复杂度分析）
  3. repair → is_homologous → ClarityCompiler 的数据流类型定义
  4. 一个完整的运行 trace 示例：
     从 L2Return 信号出发，经过 repair()、is_homologous() 过滤、ClarityCompiler 编译，
     到新 TestableClaim[] 进入下一个 Epoch
  5. 实现难度最高的 2 个子问题及其风险与缓解措施

  对 E 和 F 每个设计决策必须给出明确的最终裁定（具体算法或策略），不得搁置。
---

# v3 认知引擎架构：repair() 策略与 is_homologous() 同源检测

## 一、整体系统背景（完整概述）

本议题围绕 `repair()` 和 `is_homologous()` 两个函数的设计展开。为了让读者无需阅读其他文件就能完整理解讨论背景，以下先介绍 v3 整体架构，再说明这两个组件在其中的位置。

### 1.1 v3 系统的目标与核心挑战

v3 认知引擎旨在处理开放式、有争议的复杂问题——例如「AI 是否应该开源」「城市该投资地铁还是自动驾驶」——并产出多视角、辩护完备的答案，而非简单的是/否结论。

这类问题的核心挑战在于：**探索空间是无限的，但验证预算是有限的**。系统必须在「已知结论已经足够稳定，可以停下来」和「还有重要方向没有探索，停下来会遗漏关键视角」之间做出判断。而驱动这个判断的关键循环，就是 `repair()` 负责的「修复-再探索」环节。

### 1.2 两层分离架构

v3 采用**两层分离架构**，每一层处理不同粒度的问题：

**Layer 1（问题级处理层）**——薄状态机，负责将开放问题分解为多条可验证的候选命题，并协调迭代循环。七个显式状态节点依次执行：

```
QN（QuestionNormalizer，问题规范化）
  → MB（MacroBreadth，宏观广度探索）
  → CC（ClarityCompiler，清晰度编译）
  → D2（Layer2Dispatch，派发到 Layer 2）
  → PA（PrecisionAggregator，精度聚合）
  → RB（RepairBreadth，修复回退）    ← repair() 在此节点调用
  → AS（AnswerSynthesis，答案综合）
```

**Layer 2（命题级处理层）**——v2 状态机，对每条具体的 `TestableClaim` 进行深度追溯和精度检测：

```
S1(Clarify) → S2(Depth) → S3(Precision) → S4(DepthProbe) ↔ S5(BreadthProbe)
  → S6(Verified) | S7(Suspended) | S9(SchemaChallenge)
```

**两层之间的信息流向**是双向的：
- Layer 1 → Layer 2：以 `DispatchBatch` 打包 `TestableClaim[]` 下发
- Layer 2 → Layer 1：以 `L2Return` 回传验证结果、缺口信号（`GapSpec`）、图型挑战（`SchemaChallengeNotice`）和改写建议（`RewriteStep`）
- 当 Layer 2 发现结构性失败（无法找到关键的判别指标、前提不足、图型框架需要扩展），Layer 1 进入 `RB` 节点，调用 `repair()` 生成新的假设草稿，重新进入 CC → D2 循环

### 1.3 迭代循环：Epoch 机制

Layer 1 的每一次「派发 → 等待 → 接收 → 判断」循环称为一个 **Epoch**。每个 Epoch 结束时，Layer 1 在 `PA` 节点聚合 `L2Return`，执行以下判断：

1. **终止检查**：调用 `has_ranking_change()` 比较当前 Epoch 和上一个 Epoch 的 Top-K 排序。如果连续两个 Epoch 无 ranking-changing repair（Top-K 集合不变且分数变化 < delta），则触发终止，输出 `TerminationReport`
2. **修复决策**：如果不终止，进入 `RB` 节点，根据 `L2Return` 中的 `new_gaps`、`schema_challenges`、`suspended_claims` 调用 `repair()` 生成新的 `HypothesisDraft[]`
3. **同源过滤**：`repair()` 产出的草稿必须通过 `is_homologous()` 过滤，移除与已有候选「本质相同」的草稿，防止 Epoch 空转
4. **再编译**：过滤后的草稿进入 CC 节点重新编译，生成新的 `TestableClaim[]`，开始下一个 Epoch

### 1.4 信息如何在各组件间流动

以处理「远程办公是否提高软件团队生产力」为例，一次完整的运行流程如下：

**Epoch 0**：
- QN 规范化问题，产出 `QuestionFrame`（包含评估维度：交付速度、缺陷率、人才留存、创新质量）
- MB 广度探索，产出 3 条 `HypothesisDraft`
- CC 编译为 2 条 `TestableClaim`（其中 1 条因 falsifier 不充分被 park）
- D2 派发到 Layer 2 验证
- Layer 2 返回 `L2Return`：其中 1 条被验证（score=0.72），1 条触发 `SchemaChallengeNotice`（缺少「任务耦合度」判别维度）
- PA 判断 `ranking_delta.changed=true`，不终止

**Epoch 1**（`repair()` 介入）：
- RB 节点调用 `repair(frame, l2_result)`
- `repair()` 读取 `SchemaChallengeNotice`，产出针对「任务耦合度」的新草稿
- **`is_homologous()` 过滤**：检查新草稿是否与已有候选本质相同——新草稿聚焦「高同步依赖团队」，与现有草稿覆盖方向不同，判定 `is_homologous=false`，通过过滤
- CC 编译新草稿，产出 2 条新 `TestableClaim`
- Layer 2 验证，返回新的 `L2Return`
- PA 判断 `ranking_delta.changed=true`，不终止

**Epoch 2-3**：类似循环，直至连续两轮无 ranking change，触发终止

### 1.5 topic1 已裁定的六个核心结论

以下结论在 v3 topic1 辩论中已最终裁定，本轮作为已知条件直接继承，不再讨论：

1. **两层分离架构已裁定**：Layer 1（薄状态机，7 个显式状态）+ Layer 2（v2 命题级状态机）
2. **精度引擎是纯路由器**：`PrecisionRoute.graph_delta` 永远为 `null`，任何改写必须走独立的 `RewriteStep`
3. **深广引擎已取消**：功能完全还原为 `S4↔S5` 状态转移（深度缺口 → GapSpec → 触发广度）
4. **终止条件框架已裁定**：`hasRankingChangingRepair` 检测 Top-K 集合变化 + 分数变化 > delta；连续 N=2 轮无变化则终止；终止时区分构成性完成与调节性残余
5. **is_homologous() 的作用已裁定**：`SchemaChallengeNotice.is_homologous=true` 时，该信号不触发广度引擎（防止同源张力反复触发无效广度搜索）。**注意命名约定**：`SchemaChallengeNotice.is_homologous` 是 Layer 2 在 S5(BreadthProbe) 阶段产出的布尔字段，表示本次广度触发是否与已有张力同源；`is_homologous()` 在本文中另指 Layer 1 RB 节点用于过滤 `HypothesisDraft[]` 的过滤函数。两者共用"同源"概念但层次不同：前者是 Layer 2 对单次广度触发的标注，后者是 Layer 1 对 repair 产出草稿的批量过滤——本轮讨论的核心问题 F 聚焦后者（Layer 1 过滤函数）的判定算法。
6. **repair() 的已知约束**：输入为 `L2Return`（含 `GapSpec[]`、`SchemaChallengeNotice[]`、`SuspendedClaim[]`、`RewriteStep[]`），输出为 `HypothesisDraft[]`；每条草稿必须引用具体的 `gap_id` 或 `schema_challenge_id`；产出草稿须经 Layer 1 `is_homologous()` 过滤函数过滤后再进入 `ClarityCompiler`

**Layer 1 核心接口（已确立，供本轮引用）**：

```typescript
type GapSpec = {
  gap_id: string;
  gap_kind: "MISSING_DISCRIMINATOR" | "MISSING_OBSERVABLE" | "PREMISE_UNDERSPECIFIED";
  discriminator: string;
  required_observable: string[];
  accept_test: string;
};

type SchemaChallengeNotice = {
  source_claim_id: string;
  trigger: "ANOMALY_OVERFLOW" | "PRECISION_DEADLOCK" | "PLATEAU" | "REPLAY_REGRESSION";
  anomaly_refs: string[];
  is_homologous: boolean;
  suggested_dimension?: string;
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
  provenance: { gap_id?: string; schema_challenge_id?: string };  // 必须至少有一个，repair 产出的草稿特有字段
};

// 以下类型来自 topic1 裁定，供本轮论证时引用

type SuspendedClaim = {
  claim_id: string;
  suspend_reason:
    | "CLARITY_COMPILE_FAIL"
    | "GAP_UNRESOLVED"
    | "PRECISION_DEADLOCK"
    | "SCHEMA_REQUIRED"
    | "BUDGET_EXCEEDED";
  retryable: boolean;
};

type RewriteStep = {
  rewrite_id: string;
  source_claim_id: string;
  proposed_claim: TestableClaim;
  justification: string;
  semantic_diff: string[];
};

type L2Return = {
  batch_id: string;
  verified_claims: VerifiedClaim[];
  suspended_claims: SuspendedClaim[];
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  rewrites: RewriteStep[];
  ranking_delta: {
    changed: boolean;
    affected_claim_ids: string[];
    reason: "NEW_EVIDENCE" | "DEFEAT" | "SCHEMA_SHIFT" | "NONE";
  };
};
```

---

## 二、repair() 和 is_homologous() 在架构中的位置

### 2.1 上游输入与下游输出

**`repair()` 的上游**：Layer 2 的 `L2Return`（通过 PA 节点聚合后到达 RB 节点）。`L2Return` 中包含三类触发修复的信号：

- `new_gaps: GapSpec[]`：Layer 2 发现的知识缺口。例如命题「高同步依赖团队中远程办公降低迭代吞吐量」需要「任务耦合度的量化方法」作为前提，但找不到，于是产出 `GapSpec(gap_kind=MISSING_DISCRIMINATOR, discriminator="任务耦合度量")`
- `schema_challenges: SchemaChallengeNotice[]`：Layer 2 发现当前分析框架（Schema）不足以容纳观测到的异常。例如深度引擎发现无论怎么细化命题，「远程办公影响创新」的研究结果始终无法收敛，可能需要引入「团队成熟度」作为新的分析维度
- `suspended_claims: SuspendedClaim[]`：Layer 2 无法继续处理的搁置命题（`CLARITY_COMPILE_FAIL` / `GAP_UNRESOLVED` / `PRECISION_DEADLOCK` / `SCHEMA_REQUIRED` / `BUDGET_EXCEEDED`）

**`repair()` 的下游**：
- 产出新的 `HypothesisDraft[]`，进入 `is_homologous()` 过滤
- 过滤通过的草稿进入 CC 节点（ClarityCompiler）重新编译
- 编译成功的草稿成为新的 `TestableClaim[]`，进入下一个 Epoch 的 D2 派发

**`is_homologous()` 在链中的位置**：
```
repair() → [HypothesisDraft[]] → is_homologous() 过滤 → CC（ClarityCompiler）→ [TestableClaim[]] → D2
```

`is_homologous()` 是 `repair()` 与 `ClarityCompiler` 之间的门卫，防止「修复」产出的草稿只是对已有候选的语义重复，导致新 Epoch 在旧框架内空转。

### 2.2 为什么这两个决策点没有在 topic1 中被解决

topic1 辩论确立了 Layer 1 的整体骨架和终止逻辑的框架，但刻意回避了 `repair()` 和 `is_homologous()` 的内部实现，原因有三：

**第一**，`repair()` 是系统中最接近「创造性认知」的环节——它需要从「我们不知道什么」（GapSpec）推导出「我们接下来应该猜什么」（新 HypothesisDraft）。这个推导的质量直接决定系统的上限，但也是最难形式化的部分。topic1 讨论的是控制流骨架，而非认知生成策略。

**第二**，`is_homologous()` 的判定边界本质上是「什么叫本质相同」这个哲学问题的工程落地。这需要在充分理解 `repair()` 策略之后，才能合理设计——因为 `repair()` 的策略直接影响 `is_homologous()` 需要承担的过滤压力（机械策略产出的草稿高度同质化，自由策略产出的草稿多样性高但漏报风险大）。

**第三**，当 `repair()` 连续多轮产出被 `is_homologous()` 100% 过滤的草稿时，系统应该降级还是终止？这个降级策略的设计需要先明确两个函数的具体实现，才能推导出合理的退出路径。topic1 的伪代码只处理了正常收敛路径，未处理「修复空转」这个边缘情况。

---

## 三、本轮聚焦的两个未决设计点

### 问题 E：repair() 的生成策略

**已知**：
- 输入：`L2Return`（含 `new_gaps: GapSpec[]`、`schema_challenges: SchemaChallengeNotice[]`、`suspended_claims: SuspendedClaim[]`、`rewrites: RewriteStep[]`）
- 输出：`HypothesisDraft[]`（每条必须引用 `gap_id` 或 `schema_challenge_id`）
- 约束：产出草稿必须通过 `is_homologous()` 过滤，才能进入 `ClarityCompiler`

**未决部分**：
- **策略 E1（机械填充）**：`gap.discriminator` 直接塞进 `claim_sketch`，生成「关于 X 的新命题」。简单可预测，但容易在 gap 描述本身不准确时产生无意义草稿。
- **策略 E2（结构化推导）**：根据 `gap_kind` 选择不同的草稿形状模板——例如 `MISSING_DISCRIMINATOR` → 生成「在满足判别条件 D 的子群中，原命题仍成立」的条件化草稿；`MISSING_OBSERVABLE` → 生成「替代可观测量 O 与原始 observable 正相关」的桥接草稿；`PREMISE_UNDERSPECIFIED` → 生成「前提 P 在范围 R 内成立的充分条件」的前提精化草稿。可预测且结构严格，但 `gap_kind` 的三元分类是否穷尽了所有需要修复的情况尚不清楚。
- **策略 E3（LLM 自由创造）**：以 `GapSpec` 和 `QuestionFrame` 作为上下文，让 LLM 自由生成新假设方向。创造性强，但行为不可预测、不可审计，也无法保证新草稿真正覆盖了 gap。
- **混合策略**：E2 为主（gap_kind 已知时）+ E3 兜底（gap_kind 不充分时）。
- **schema_challenge 信号的处理**：`suggested_dimension` 是强约束（repair 必须围绕该维度生成草稿）还是弱提示（repair 可以参考但不必遵循）？这影响 repair 在 schema 触发场景下的自由度。

**关键张力**：
- 策略越机械，repair 越可预测，但越容易在 gap 描述失准时空转；
- 策略越自由，repair 越有创造性，但越难保证对 gap 的覆盖，`is_homologous()` 的负担也越重；
- 如果 repair 连续两轮产出被 `is_homologous()` 100% 过滤，系统该降级还是终止？

---

### 问题 F：is_homologous() 的判定边界

**已知**：
- 作用：过滤 `repair` 产出的 `HypothesisDraft[]`，移除与已有候选「本质相同」的草稿
- 已裁定的场景：`SchemaChallengeNotice.is_homologous=true` 时，该信号不触发广度引擎
- 已裁定的动机：防止 Epoch 空转（repair 产出同义重复的候选，导致 `hasRankingChangingRepair` 永远不触发）

**未决部分**：
- **判定维度 F1（张力来源同一性）**：两个草稿若 `tension_source.kind` 相同且 `scope_ref` 高度重叠，则同源。实现简单，但会将真正不同的假设误判为同源（两个草稿可能来自同一维度但指向对立方向）。
- **判定维度 F2（claim_sketch 语义相似度）**：使用嵌入向量余弦相似度阈值。对语义相近的草稿有效，但阈值选取困难，且计算成本高，更难以解释为什么「这两条被认为相同」。
- **判定维度 F3（结构等价性）**：两个草稿若能被 ClarityCompiler 编译为具有相同 `falsifier` 和 `scope` 的 `TestableClaim`，则同源。最精确，但需要先编译再过滤，顺序颠倒了架构预设（`is_homologous` 是编译前的过滤）。
- **判定维度 F4（verifier_hint 覆盖度）**：两个草稿若 `verifier_hint` 集合高度重叠（验证路径相同），则同源。间接但实用，因为验证路径相同意味着引入的信息量相同。
- **双重条件**：任何单一维度可能都不充分，是否需要「结构 AND 语义」的组合判定？
- **误判后果**：
  - 漏报（将真正新颖的草稿判为同源）：新维度被过滤掉，广度引擎无法被合法触发，系统在旧框架内困死；
  - 误报（将本质相同的草稿判为新颖）：广度引擎被噪声触发，产出无效 `TestableClaim`，Layer 2 预算耗尽在无意义的验证上。

**关键张力**：
- 判定阈值越低（越容易被判为同源），越容易漏报，真正新颖的方向被压制，广度引擎无法合法触发；
- 判定阈值越高（越难被判为同源），越容易误报，广度引擎被噪声触发，Layer 2 预算耗尽在无意义验证上；
- `is_homologous()` 的错误方向与 `repair()` 的策略选择存在耦合：机械填充策略产出的草稿同质化高，`is_homologous()` 的负担大；自由策略产出的草稿多样性高，`is_homologous()` 的漏报风险大。

---

## 四、开放性陈述

本议题没有预设答案，也没有明显的「正确方向」。

`repair()` 和 `is_homologous()` 是 v3 认知引擎中最靠近「创造性认知」的两个环节——它们共同决定了系统在「已知知识耗尽后」的行为。一个过于保守的 `repair` 策略会让系统在旧假设的荒野中原地踏步；一个过于激进的 `is_homologous` 判定会让系统的 Epoch 循环被噪声填满。

以下几组未解决的张力供辩手展开论证：

**关于 repair() 的内在矛盾**：结构化策略 E2 要求 `gap_kind` 是充分分类——但 `gap_kind` 的三元分类（`MISSING_DISCRIMINATOR` / `MISSING_OBSERVABLE` / `PREMISE_UNDERSPECIFIED`）是否能穷尽系统运行中实际遇到的所有知识缺口？如果不能，E2 的策略表会有多大的「分类外逃逸」？逃逸的 gap 如果由 E3 兜底，那 E2+E3 的混合策略的可审计性是否比纯 E3 好多少？

**关于 is_homologous() 的哲学争议**：「本质相同」是形而上学概念，不是工程判据。将其落地为可计算的函数，不可避免地需要选择某种代理变量（张力来源、语义向量、验证路径）。任何代理变量都只是「本质相同」的不完全近似——这个近似的误差是否被系统的其他机制（如 `ttl` 衰减、`MAX_EPOCHS` 上限）所容忍？还是误差会系统性地累积，最终导致终止判断失效？

**两者的耦合问题**：`repair()` 的策略选择直接影响 `is_homologous()` 需要承担的过滤压力。如果先确定 `is_homologous()` 的算法，再设计 `repair()` 的策略，是否会得到不同的架构结论？还是两者必须协同设计（co-design），才能保证在最坏情况下（repair 连续产出被过滤的草稿）系统有明确的降级路径？
