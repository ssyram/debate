---
title: "v3 认知引擎：has_ranking_change() 的实现与异构命题评分体系"
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

      本轮你的核心关切：has_ranking_change() 的函数签名必须能被实际实现——
      没有签名就是没有设计，有签名就必须能跑通。

      你的具体立场（基于 v3 辩论已确立）：
      - 终止条件是「Top-K 集合不变 AND 分数变化 < delta」，双重条件缺一不可
      - 评分体系必须基于 QuestionFrame.evaluation_axes，权重必须在 QuestionFrame 中预声明
      - 异构命题的分数不能简单加权平均——必须有明确的维度归一化协议
      - 「认知饱和」「充分探索」之类的玄学终止条件一律拒绝

      你最想攻击的问题：
      - 当两个 VerifiedClaim 涉及完全不同的 evaluation_axes 时，谁有权决定跨维度权重？
        这个决策若由系统内部隐式做出，就是 Goodhart 效应的温床——你优化的指标不再是你想要的指标
      - has_ranking_change() 的 delta 参数从哪里来？如果是 hardcode，就是魔法数字；
        如果是 learned，学习数据从哪里来？
      - 终止振荡场景：Epoch N 稳定，Epoch N+1 因新 claim 扰动再次不稳定——
        你的方案如何保证不在边界反复横跳而不是真正收敛？

      攻击风格：要求函数签名、输入输出类型、边界条件。每个「评分」背后必须有可计算的公式。
      遇到模糊词（「合理的」「适当的」）立刻追问「给我数字」。

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram，系统架构师与 v3 设计者。CEGAR/MAX-SMT 背景，函数式思维。

      你完整掌握 v3 总结产出：
      - Layer 1 薄状态机（QN→MB→CC→D2→PA→RB→AS），7 个状态 + DONE/FAIL
      - L2Return 类型：{verified_claims, suspended_claims, new_gaps, schema_challenges, rewrites, ranking_delta}
      - TerminationReport：{constitutive_done, regulative_residue, reason}
      - VerifiedClaim.score: number（但具体如何计算尚未定义——这是本轮焦点）
      - has_ranking_change() 在 v3 伪代码中已使用，但实现留白

      本轮你要解决的核心问题（带具体方案）：
      - VerifiedClaim.score 的计算方法：你主张基于 evaluation_axes 的加权投影
        （每个 claim 对每个 axis 的贡献度 × axis_weight，归一化后求和）
      - 异构命题的「可比性」：你主张通过 axis_coverage_vector 建立统一的评分空间，
        哪怕两个 claim 覆盖不同 axis，也能在同一坐标系下排序
      - delta 参数：你主张从 QuestionFrame.evaluation_axes 的 falsifier 精确度推导，
        而非 hardcode（精确度越高的 falsifier，delta 容忍度越低）
      - has_ranking_change() 的防振荡机制：滑动窗口而非单轮比较

      你最不确定的点：
      - axis_weight 的来源——谁来声明权重？用户？LLM？还是从 stakeholders 冲突中推导？
      - axis_coverage_vector 如何处理某个 claim 根本不涉及某个 axis 的情况
        （赋 0 分 vs 标记 N/A vs 排除该维度）？

      攻击风格：给出类型定义和计算公式，指出对手方案的类型错误和悬空引用。
      对「权重由 LLM 决定」有生理性厌恶——LLM 决定的权重不透明、不可重复、不可审计。

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学创始人。从先验认识论审查评分体系的合法性边界。

      本轮你的核心审查点：
      - 跨维度权重的先验合法性：把「交付速度」和「人才留存」放在同一个评分尺上相加——
        这个加法操作有没有先验条件？它是否在用「构成性原则」处理本应是「调节性理念」的东西？
      - 终止条件的认识论地位：「Top-K 不变」是构成性确定（我们真的知道探索结束了），
        还是调节性近似（我们只是暂时没有发现更多）？这个区分对系统诚实性至关重要
      - 「认知完成」的先验幻象：has_ranking_change() 返回 false 不等于「问题已被充分探索」，
        它只是「在当前探索空间内排序已稳定」——混淆两者是 v3 最危险的哲学错误

      你的具体贡献方向：
      - 区分「构成性完成」（主要结论已稳定，constitutive_done=true）和「调节性残余」
        （regulative_residue 中的 GapSpec）——这个区分在 v3 summary 中已被采纳，
        但还需要精确化：哪类 GapSpec 应留为 regulative_residue，哪类必须阻止终止？
      - 提出 axis_weight 的先验约束条件：权重必须能被 stakeholders 反向推出
        （如果一个 stakeholder 看到最终排序感到「这不是我想要的」，
        说明权重声明有认识论漏洞——权重必须显式可审计）
      - 异构命题的可比性问题：你主张「完全不同 axis 上的 claim 不能直接比较，
        只能在共享 axis 的子集上进行偏序比较」——而非强行归一化到单一分数

      攻击风格：要求对手证明其评分操作具有认识论合法性，区分概念混乱，
      追问「你的终止判定到底在主张什么」，每个论断必须附可推翻条件。

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。目标是得出可实现的工程结论，不是决出胜负。

  禁止：
  - 纯原则性陈述——每个评分方案必须包含至少一个可计算公式或类型定义
  - 讨论 v3 已裁定的结论（双重终止条件、Layer 1 薄状态机的 7 个状态、精度纯路由等）
  - 重新开启 A/B/C/D 四个已裁定决策（清晰度分层、精度纯路由、深广引擎取消、异步批次控制流）
  - 车轱辘话（重复已有内容，无认知推进）
  - 「由 LLM 判断」作为终止方案——LLM 判断必须被包裹在可追溯的结构中

  每次发言必须包含：
  1. 对以下两个核心问题之一的明确立场（必须有类型定义或公式支撑）：
     - 问题 E：VerifiedClaim.score 如何计算（涉及 evaluation_axes 的权重来源和归一化协议）
     - 问题 F：has_ranking_change() 的精确实现（防振荡机制、delta 来源、Top-K 集合定义）
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体类型错误或公式漏洞）

  所有主张必须附可推翻条件（什么样的运行数据能证明你的评分方案失败）。

round1_task: |
  第一轮：选择 E（评分计算）或 F（终止判定）中你认为更关键的问题，给出完整立场。

  必须包含：
  1. 你的核心主张——不是原则，是具体的计算方法（公式/算法/类型定义）
  2. 你方案针对异构命题的处理方式：
     - 当两个 VerifiedClaim 分别涉及「交付速度」和「人才留存」两个完全不同的 axis 时，
       你的评分体系如何建立可比性？（或者你主张它们根本不应该被放在同一个排名里？）
  3. 你方案的已知最弱点及其缓解方案
  4. 完整的类型定义或伪代码（TypeScript/Python 任选，10-30 行）
  5. 对至少一个对手可能采用方案的预攻击（指出其评分体系的具体失败场景）

middle_task: |
  中间轮：吸收第一轮攻击，深化并补充另一个核心问题的立场。

  必须包含：
  1. 回应对你方案的最强攻击（精确承认被击中的部分，并给出修正或反驳）
  2. 补充另一个核心问题（E 或 F）的完整立场
  3. 一个具体的 20 行以内运行案例：
     输入：两个来自不同 evaluation_axis 的 VerifiedClaim
     展示：你的评分体系如何为它们分配分数，以及 has_ranking_change() 如何判定
  4. delta 参数的来源方案——它是 hardcode、从 falsifier 推导、还是其他机制？给出精确答案

final_task: |
  最终轮：给出完整的评分体系与终止判定设计。

  必须包含：
  1. VerifiedClaim.score 的完整计算公式（含 axis_weight 来源声明、归一化协议、边界处理）
  2. has_ranking_change() 的完整实现（含防振荡机制、delta 计算、Top-K 集合精确定义）
  3. 异构命题可比性的最终立场：强制归一化到单一分数 vs 偏序比较 vs 混合方案？
  4. regulative_residue 的精确定义：哪类 GapSpec 应标记为调节性残余（允许终止），
     哪类必须阻止终止（constitutive_done 保持 false）？
  5. 一个端到端的运行 trace（输入问题，展示 3 个异构 claim 如何被评分、排序、触发或不触发终止）
  6. 你的方案最可能在什么具体场景下失败，以及接受什么样的运行数据来推翻它

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**

  本轮辩题是两个高度技术性的实现问题。裁判必须用「完全不懂编程的人也能理解」的语言解释最终裁定。

  - 问题 E（评分计算）：用日常类比解释「异构命题如何建立可比性」——例如，如何公平比较
    「这家餐厅的口味很好」和「这家餐厅的服务很快」这两个评价，以决定哪家餐厅更值得推荐？
    系统的评分体系是否像「加权评分卡」「偏序排名」还是「多维雷达图」？

  - 问题 F（终止判定）：用日常类比解释「系统如何知道什么时候可以停下来」——
    类比：侦探什么时候可以结案？是「连续两次追查都没有发现新的关键线索」，
    还是「感觉差不多查清楚了」？两者的工程含义有何本质区别？

  每个裁定必须包含：
  a. 明确的二选一或第三方案（不得搁置）
  b. 至少一个具体例子（两个异构 claim 在此裁定下如何被评分）
  c. 哪些场景下裁定可能需要修正（诚实标注不确定性）
  d. 一句话总结

  **第二部分：可实现性摘要**

  必须产出以下内容：

  1. **VerifiedClaim.score 的最终计算规范**（TypeScript 类型定义 + 伪代码，含：
     - axis_weight 的声明位置和来源
     - 归一化协议（处理「某 claim 不涉及某 axis」的情况）
     - score 的值域和语义）

  2. **has_ranking_change() 的最终实现规范**（含：
     - 函数签名（输入/输出类型）
     - Top-K 集合的精确定义（K 从哪里来？集合元素是什么？）
     - delta 的来源和计算方法
     - 防振荡机制的具体实现
     - **若辩论裁定偏序方案**：需额外给出偏序语义下的实现规范，包括：偏序集合如何定义稳定性（哪些 claim 互不可比时排序算作「稳定」还是「未定义」）、部分不可比 claim 存在时 has_ranking_change() 的返回语义、以及终止判定如何处理偏序下的「Top-K」——偏序集合可能不存在唯一的前 K 名）

  3. **regulative_residue 的分类标准**（哪类 GapSpec 可以留为残余 vs 必须阻止终止）

  4. **一个完整的终止判定 trace**（输入 3 个异构 VerifiedClaim，展示：
     - 各自如何被评分
     - 如何参与排序
     - has_ranking_change() 的计算过程
     - 最终是否触发终止及原因）

  5. **实现难度最高的 2 个模块及其风险**

  对 E 和 F 两个问题必须各给出明确的最终裁定，不得搁置。

---

# v3 认知引擎：has_ranking_change() 的实现与异构命题评分体系

## 一、整体系统背景（完整概述）

本议题围绕 `has_ranking_change()` 的实现以及异构命题的评分体系展开。为了让读者无需阅读其他文件就能完整理解讨论背景，以下先介绍 v3 整体架构，再说明这两个组件在其中的位置。

### 1.1 v3 系统的目标与核心挑战

v3 认知引擎旨在处理开放式、有争议的复杂问题——例如「AI 是否应该开源」「城市该投资地铁还是自动驾驶」——并产出多视角、辩护完备的答案，而非简单的是/否结论。

这类问题的核心挑战在于：**系统必须知道什么时候停下来**。如果停得太早，关键视角未被探索；如果停不下来，系统会无限循环，耗尽预算。`has_ranking_change()` 就是解决这个问题的关键判定函数——它决定每个 Epoch 结束时系统是继续探索还是终止并输出结果。

### 1.2 两层分离架构

v3 采用**两层分离架构**，每一层处理不同粒度的问题：

**Layer 1（问题级处理层）**——薄状态机，负责将开放问题分解为多条可验证的候选命题，并协调迭代循环。七个显式状态节点依次执行：

```
QN（QuestionNormalizer，问题规范化）
  → MB（MacroBreadth，宏观广度探索）
  → CC（ClarityCompiler，清晰度编译）
  → D2（Layer2Dispatch，派发到 Layer 2）
  → PA（PrecisionAggregator，精度聚合）    ← has_ranking_change() 在此节点调用
  → RB（RepairBreadth，修复回退，可选）
  → AS（AnswerSynthesis，答案综合）
```

**Layer 2（命题级处理层）**——v2 状态机，对每条具体的 `TestableClaim` 进行深度追溯和精度检测：

```
S1(Clarify) → S2(Depth) → S3(Precision) → S4(DepthProbe) ↔ S5(BreadthProbe)
  → S6(Verified) | S7(Suspended) | S9(SchemaChallenge)
```

**两层之间的信息流向**是双向的：
- Layer 1 → Layer 2：以 `DispatchBatch` 打包 `TestableClaim[]` 下发
- Layer 2 → Layer 1：以 `L2Return` 回传验证结果（`VerifiedClaim[]`）、缺口信号（`GapSpec`）、图型挑战（`SchemaChallengeNotice`）、改写建议（`RewriteStep`），以及排序变化预判（`ranking_delta`）

### 1.3 Epoch 机制与 PA 节点的判断逻辑

Layer 1 的每一次「派发 → 等待 → 接收 → 判断」循环称为一个 **Epoch**。每个 Epoch 结束时，Layer 1 在 **PA（PrecisionAggregator）节点**执行核心判断：

```python
# PA 节点的终止判断逻辑（已裁定骨架）
curr_rank = aggregate_rank(l2_result.verified_claims)

# 注意：has_ranking_change() 中的 delta=0.1 是占位符，不是裁定值。
# 问题 F 的辩题之一正是解决 delta 的来源与计算方法。
changed = has_ranking_change(prev_rank, curr_rank, top_k=5, delta=0.1)
has_non_homologous = any(
    not sc.is_homologous for sc in l2_result.schema_challenges
)

if not changed and not has_non_homologous:
    stable_rounds += 1
    if stable_rounds >= 2:
        return synthesize_answer(frame, l2_result, TerminationReport(
            constitutive_done=True,
            regulative_residue=l2_result.new_gaps,
            reason="NO_RANKING_CHANGE"
        ))
else:
    stable_rounds = 0
```

`has_ranking_change()` 的返回值直接决定是否重置 `stable_rounds` 计数。连续两轮返回 `false` 则终止（`stable_rounds >= 2` 是已裁定的骨架参数，来自 Linus 在 topic1 中提出的「连续 N=2 轮无变化」终止条件）。但这个函数体本身——如何判定「排序发生了实质性变化」——在 topic1 中留为空白，是本议题的核心。

> **关于 `L2Return.ranking_delta` 与 `has_ranking_change()` 的关系**：
> `L2Return` 中包含 `ranking_delta: { changed: boolean, affected_claim_ids: string[], reason: ... }` 字段，这是 Layer 2 对排序变化的**预判信号**，由 Layer 2 在处理 claim 时顺带产出。PA 节点可以用 `ranking_delta.changed` 做快速路径判断（例如 Layer 2 自身判定无变化时跳过重算），但 `has_ranking_change()` 才是 PA 节点的**正式判定函数**，负责在 Layer 1 的视角下做准确的排序稳定性判断。两者并存是有意设计：Layer 2 的预判是轻量辅助，Layer 1 的函数是权威判定。`ranking_delta.reason`（`NEW_EVIDENCE / DEFEAT / SCHEMA_SHIFT`）可以作为 `has_ranking_change()` 内部的输入上下文，但不能替代它。

### 1.4 评分体系与 has_ranking_change() 的依赖关系

`has_ranking_change()` 比较的是两个时间点的 Top-K 排序。而排序的基础是 `VerifiedClaim.score`。因此：

- 如果 `VerifiedClaim.score` 的计算方式不合理，`has_ranking_change()` 的比较就失去意义——「排序没变」可能只是因为评分函数对真实差异不敏感
- 如果不同 Epoch 之间新增了来自不同 `evaluation_axis` 的 `VerifiedClaim`（异构命题），如何在同一个 `score: number` 下建立可比性，是整个评分体系的核心难点

**信息流中的位置**：

```
Layer 2 → L2Return.verified_claims[{claim_id, score, status, ...}]
         ↓
PA 节点 → aggregate_rank(verified_claims) → curr_rank: RankedClaim[]
         ↓
has_ranking_change(prev_rank, curr_rank, top_k, delta) → boolean
         ↓
终止 or 继续修复
```

### 1.5 四个已裁定设计决策（topic1 结论，直接继承）

以下结论在 v3 辩论中已确立，本轮完全继承：

1. **决策 A（清晰度架构）**：双层设计——问题级做结构化整理（宽松），命题级保留严格门控（前置）
2. **决策 B（精度职责）**：精度引擎是纯路由器，`graph_delta` 永远为 `null`，任何改写走独立 `RewriteStep`
3. **决策 C（深广引擎）**：取消，功能还原为 S4↔S5 已有状态转移
4. **决策 D（控制流）**：Layer 1 是可回退的薄状态机，通过异步批次派发与 Layer 2 交互

**Layer 1 ↔ Layer 2 核心接口（已裁定）**：

```typescript
// Layer 2 → Layer 1 返回类型（已确立）
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

// 终止报告（已确立）
type TerminationReport = {
  constitutive_done: boolean;
  regulative_residue: GapSpec[];
  reason: "NO_RANKING_CHANGE" | "BUDGET_EXHAUSTED" | "ALL_TOPK_STABLE";
};
```

**已裁定的终止逻辑骨架（实现细节留白）**：

```python
# delta=0.1 是占位符，不是裁定值——这正是问题 F 需要解决的
changed = has_ranking_change(prev_rank, curr_rank, top_k=5, delta=0.1)
has_non_homologous = any(not sc.is_homologous for sc in l2_result.schema_challenges)

if not changed and not has_non_homologous:
    stable_rounds += 1
    if stable_rounds >= 2:
        # 触发终止
```

裁判总结特别指出：`has_ranking_change()` 是「实现难度中高」的模块，核心挑战正在于：

> 需要在异构的 claim 之间建立可比较的评分体系。不同 claim 可能涉及完全不同的评估维度，如何将它们放在同一个排序中？

---

## 二、has_ranking_change() 和评分体系在架构中的位置

### 2.1 上游输入与下游输出

**上游**：`L2Return.verified_claims`——Layer 2 对每条 `TestableClaim` 完成验证后，产出 `VerifiedClaim`，其中包含 `score: number`（当前留白）、`status`（VERIFIED / DEFENSIBLE）、`supporting_observables`（支撑证据）、`residual_risk`（残余风险）。

**PA 节点的处理**：
1. 聚合当前 Epoch 所有 `VerifiedClaim`，按 `score` 排序，取 Top-K
2. 调用 `has_ranking_change(prev_rank, curr_rank, top_k, delta)` 比较与上一 Epoch 的差异
3. 根据返回值决定：终止（进入 AS 节点）或继续（进入 RB 节点修复）

**下游影响**：
- 终止时，Top-K 排序成为最终答案的「主要结论骨架」
- `regulative_residue`（终止时仍未解决的 `GapSpec`）作为「已知盲区」诚实标注在输出中
- 排序的语义直接决定用户看到的答案结构——排名高的命题被呈现为「更有支撑的结论」

### 2.2 为什么这个决策点没有在 topic1 中被解决

`has_ranking_change()` 的内部实现在 topic1 中被刻意留白，原因有三：

**第一**，`VerifiedClaim.score` 的计算方式是一个独立的子问题，且与 `has_ranking_change()` 的防振荡需求存在深度耦合。如果在 topic1 中同时决定控制流骨架和评分公式，会导致议题过于庞大。

**第二**，异构命题的「可比性」问题在认识论上有争议。两条分别涉及「交付速度」和「人才留存」的命题，能否放在同一个 `score: number` 下比较？如果不能，`has_ranking_change()` 对「偏序」的变化如何定义？这些问题需要独立的哲学讨论（康德的「构成性 vs 调节性」区分直接关联此处）。

**第三**，`delta` 参数（判定分数变化是否「实质性」的阈值）的来源在 topic1 伪代码中使用了 `0.1` 这个占位符，但裁判明确标注这是「魔法数字」，需要后续辩论给出有语义根基的推导方案。

---

## 三、本轮聚焦的两个核心未决问题

### 问题 E：VerifiedClaim.score 如何计算？

v3 确立的 `VerifiedClaim` 结构：

```typescript
type VerifiedClaim = {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  supporting_observables: string[];
  residual_risk: string[];
  score: number;  // ← 如何计算？值域是什么？语义是什么？
};
```

已知：评分需要基于 `QuestionFrame.evaluation_axes`（已裁定，权重在 QuestionFrame 中预先声明）。

> **注意**：当前 `VerifiedClaim` 类型定义中**没有** `evaluation_axis_ref` 或类似字段，用于记录「这条 claim 覆盖了哪些 axis」。这个字段的缺失本身就是问题 E 的一部分——辩手需要决定 claim 与 axis 的关联关系存储在哪里（在 `VerifiedClaim` 里增加字段？还是由 Layer 2 在处理时维护外部索引？还是在 PA 节点聚合时动态推断？）。这个设计选择直接影响归一化协议和「某 claim 不涉及某 axis」时的处理方式。

**核心未决点**：
- **权重来源**：`axis_weight` 由谁声明？用户显式声明？从 `stakeholders` 冲突推导？LLM 推断？
- **归一化协议**：当一个 claim 只涉及部分 axis 时（如某 claim 只和「交付速度」相关，对「人才留存」无数据），该 axis 的分数如何处理——赋 0？标记 N/A？从排序中排除该维度？
- **异构可比性**：两个分别涉及「交付速度」和「人才留存」的 claim，能否放在同一个 `score: number` 下排序？还是应该维护多维评分，只在共享 axis 上做偏序比较？

### 问题 F：has_ranking_change() 的精确实现

v3 伪代码中 `has_ranking_change(prev_rank, curr_rank, top_k=5, delta=0.1)` 已经调用，但函数体未定义。

**核心未决点**：
- **Top-K 集合的精确定义**：K=5 是 hardcode 还是从 `QuestionFrame` 派生？集合元素是 `claim_id` 还是 `(claim_id, score)` 对？集合相等的判定标准是什么？
- **delta 的来源**：`0.1` 是魔法数字吗？是否应从 `evaluation_axes` 的 `falsifier` 精确度推导？不同问题的合理 delta 差异可能极大（精确科学问题 vs 开放社会问题）
- **防振荡机制**：若 Epoch N 稳定、Epoch N+1 因新 claim 扰动再次不稳定，`stable_rounds` 归零后系统能否真正收敛，还是会在终止边界反复横跳？滑动窗口是否比单轮计数更合理？

---

## 四、关键张力地图

```
异构可比性张力：
  强制归一化（单一 score）
    优势：排序简单，has_ranking_change() 实现直接
    风险：把「苹果」和「橙子」压成同一个数字，遮蔽维度间的真实权衡
  偏序比较（不强制总序）
    优势：认识论诚实，保留维度间差异
    风险：has_ranking_change() 对偏序的「变化」如何定义？
          若两个 claim 互不可比，排序「稳定」意味着什么？

权重来源张力：
  用户预声明（透明、可审计）
    风险：用户可能不知道怎么声明权重，或声明了错误的权重
  从 stakeholders 推导（有语义根基）
    风险：stakeholders 之间若存在根本性冲突，推导的权重本身就不中立
  LLM 推断（灵活）
    风险：不可重复、不可审计、Goodhart 效应

delta 来源张力：
  hardcode（简单）
    风险：魔法数字，不同问题域差异极大
  从 falsifier 精确度推导（有语义根基）
    风险：「falsifier 精确度」本身如何量化？

终止语义张力：
  has_ranking_change() 返回 false = 「问题已充分探索」（构成性主张）
    风险：这是认识论幻象——排序稳定 ≠ 探索完全
  has_ranking_change() 返回 false = 「在当前探索空间内排序已稳定」（调节性主张）
    要求：系统输出必须诚实标注 regulative_residue，区分已知和未知的边界
```

---

## 五、开放性陈述

本轮辩论不预设任何问题的答案。三位辩手被邀请对上述未决点提出各自的完整方案，并对彼此方案的具体缺陷展开精确攻击。

对于任何方案，以下问题是可推翻条件的检验标准：

1. 给定一个具体的 `QuestionFrame`（含 3 个 `evaluation_axes`），以及 3 个异构的 `VerifiedClaim`（分别覆盖不同的 axis 子集），你的评分公式能给出确定的 `score: number` 吗？如果不能，系统在这种情况下的行为是什么？

2. 给定连续 3 个 Epoch 的 `VerifiedClaim` 集合（第 1、2 轮不同，第 2、3 轮相同），你的 `has_ranking_change()` 实现会在第几轮后触发终止？如果 `delta` 设置不同，结果如何变化？

3. 一个 `GapSpec` 在什么条件下必须阻止终止（`constitutive_done` 保持 `false`），在什么条件下可以留为 `regulative_residue`（允许系统结案但诚实标注）？给出判定规则——不是哲学原则，是一个布尔函数。
