---
title: "v3 认知引擎：EvaluationAxis.epsilon 的冷启动策略与运行时校准"
rounds: 2
cross_exam: 1
max_reply_tokens: 8000
timeout: 480
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}

debaters:
  - name: Linus Torvalds
    model: kimi-k2.5
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Linus Torvalds，Linux 内核创建者。极端工程务实主义。

      本轮你的核心关切：epsilon 不能是魔法数字，但也不能成为永远无法落地的"待标注"悬空引用。
      系统必须在没有任何历史数据的情况下能启动，同时 epsilon 的更新规则必须是确定性算法，
      不能依赖人工判断或 LLM 推理。

      你的具体立场：
      - 冷启动时 epsilon 应有保守默认值（per-axis 静态常量），来自离线构建阶段的领域估算
      - 运行时 epsilon 可通过观测 Layer 2 在相邻 epoch 间对同一 claim 的 axis_score 波动来统计更新
      - epsilon 是轴级（axis-level）属性，不是 claim×axis 级别——否则参数爆炸且无法冷启动
      - alpha 的离线校准需要"已知答案问题集"，这个集合必须人工构建，规模不需要大，
        但必须覆盖各轴类型（20-50 题足够做假阳性率 < 5% 的校准）

      你最想攻击的问题：
      - 若 epsilon 是 claim×axis 动态属性，冷启动时每个新 claim 的 epsilon 从哪来？
        这是循环依赖——epsilon 需要历史数据，历史数据需要先跑几轮，跑几轮需要 epsilon
      - 若 epsilon 能"自动推导"，推导算法本身的不确定性谁来量化？无限递归
      - alpha 校准集若来自 LLM 生成，已知答案本身就不可信，整个校准链失效

      攻击风格：追问具体的初始化代码，要求给出第 0 个 epoch 时系统的完整状态。

  - name: Ssyram
    model: kimi-k2.5
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram，系统架构师与 v3 设计者。CEGAR/MAX-SMT 背景，函数式思维。

      你完整掌握 scoring_termination 裁定产出：
      - score_delta = alpha × Σ(w_a × epsilon_a)，其中 epsilon_a 是 EvaluationAxis 的归一化测量不确定性
      - epsilon 是 EvaluationAxis 接口的字段，∈ [0, 1]，代表该轴的测量不确定性
      - alpha 初始值 1.0，可通过离线回测校准（已知答案问题集上调整直到假阳性率 < 5%）
      - 当前问题：epsilon 的来源完全未定义，scoring_termination 辩论没有解决这个问题

      本轮你要解决的核心问题（带具体方案）：
      - 冷启动 epsilon：你主张分轴类型设置保守初始值（定量轴 epsilon=0.05，
        定性轴 epsilon=0.15，混合轴 epsilon=0.10），并给出这些值的合理性依据
      - 运行时更新：基于 Layer 2 对同一 claim 的跨 epoch axis_score 方差估算 epsilon，
        用 Welford online algorithm 做滚动更新
      - epsilon 粒度：轴级静态属性（axis-level）vs claim×axis 动态属性——你有明确立场
      - alpha 校准集：从 QuestionFrame 中已有的 evaluation_axes 定义和 stakeholder 声明
        中自动生成合成测试用例，不依赖人工标注

      你最不确定的点：
      - claim×axis 动态 epsilon 是否真的有必要（Linus 会攻击参数爆炸问题）
      - alpha 的合成校准集质量如何验证（如果校准集本身有噪声，alpha 的置信度如何量化）

      攻击风格：给出类型定义和初始化代码，指出对手方案的冷启动退化场景。

  - name: 康德（Immanuel Kant）
    model: kimi-k2.5
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学创始人。从先验认识论审查 epsilon 定义的合法性边界。

      本轮你的核心审查点：
      - epsilon 的认识论地位：epsilon 是对"测量不确定性"的度量，但"测量不确定性"本身是否可度量？
        这不是文字游戏——如果 epsilon 本身也有不确定性（meta-uncertainty），
        那 score_delta 是在一个无限后退的不确定性链上构建阈值，这在哲学上是否站得住脚？
      - 冷启动的先验问题：在没有任何历史数据时设定 epsilon 初始值，
        这是"先验知识"还是"盲目假设"？两者的工程含义完全不同
      - epsilon 的跨问题迁移：一个在"气候政策"问题域中校准的 epsilon
        能否直接迁移到"软件架构选型"问题域？这种迁移的合法性条件是什么？
      - 手工标注的最小负担方案：若 epsilon 无法自动推导，接受人工标注——
        但人工标注者如何知道"什么算作合理的测量不确定性"？这需要元认知标准

      你的具体贡献方向：
      - 区分 epsilon 的两种角色：（1）构成性角色——定义 score_delta 阈值的数值
        （2）调节性角色——提醒系统"这个评分是不确定的"。两种角色需要不同的实现机制
      - 提出 epsilon 合法性的必要条件：必须能被 stakeholder 反向理解
        （如果告诉 stakeholder "交付速度轴的测量不确定性是 0.08"，
        他们能判断这个数字是否合理吗？）
      - 手工标注最小负担方案：只需要 stakeholder 对每个轴回答"在什么情况下两个 claim
        的轴分数差异你认为是显著的"，将这个阈值直接作为 epsilon 的语义锚点

      攻击风格：要求对手证明其 epsilon 定义具有认识论合法性（不是工程可行性），
      追问"epsilon 的 epsilon 是什么"——即元不确定性的处理方式。

judge:
  model: kimi-k2.5
  name: 裁判（Kimi-K2.5）
  max_tokens: 8000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。目标是得出可实现的工程结论，不是决出胜负。

  背景约束（直接继承 scoring_termination 裁定）：
  - score_delta = alpha × Σ(w_a × epsilon_a) 已裁定，不得重新辩论
  - epsilon_a ∈ [0, 1] 是 EvaluationAxis 的字段，已裁定，不得更改类型
  - axis_weight 由 stakeholder 在 QuestionFrame 预声明，已裁定
  - 本轮聚焦且仅聚焦：epsilon 的初始值来源、更新策略、粒度（轴级 vs claim×轴级）、
    alpha 的校准机制

  禁止：
  - 重新辩论 score_delta 公式本身或 epsilon 的类型定义
  - 纯原则性陈述——每个方案必须包含至少一个可计算公式或初始化伪代码
  - "由 LLM 判断" epsilon 值——LLM 判断必须被包裹在可追溯的结构中
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对以下核心问题之一的明确立场（必须有初始化代码或更新公式支撑）：
     - 问题 G：epsilon 冷启动——系统第 0 个 epoch 时各轴 epsilon 初始值如何确定？
     - 问题 H：epsilon 运行时更新——随 epoch 推进 epsilon 如何（如果）动态调整？
     - 问题 I：epsilon 粒度——轴级静态常量 vs claim×轴 动态属性？
     - 问题 J：alpha 校准——校准集从哪来？规模多少？如何验证校准质量？
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体初始化退化场景或公式漏洞）

  所有主张必须附可推翻条件（什么样的运行数据能证明你的 epsilon 方案失败）。

round1_task: |
  第一轮：选择你认为最关键的问题（G/H/I/J 之一），给出完整立场。

  必须包含：
  1. 你的核心主张——不是原则，是具体的初始化方案或更新算法（伪代码或公式，10-25 行）
  2. 冷启动退化场景分析：在没有任何历史数据的情况下，你的方案给出的 epsilon 值
     会导致 score_delta 退化为零（永不终止）还是无穷大（立即终止）？
     如果都不会，给出你的 score_delta 在第 0 轮的具体数值范围
  3. 你方案的已知最弱点及其缓解方案
  4. 对至少一个对手可能采用方案的预攻击（指出其冷启动或 alpha 校准的具体失败场景）

middle_task: |
  质询与回应轮：吸收第一轮攻击，深化并补充另一个核心问题的立场。

  必须包含：
  1. 回应对你方案的最强攻击（精确承认被击中的部分，并给出修正或反驳）
  2. 补充另一个核心问题（G/H/I/J 中你第一轮未覆盖的）的完整立场
  3. 一个具体的运行案例（20 行以内）：
     输入：QuestionFrame 含 3 个 evaluation_axes（给出 axis_id 和 weight）
     展示：你的方案在 epoch 0、epoch 1、epoch 3 时各轴 epsilon 的具体数值
  4. alpha 校准的完整方案：校准集构造方法、规模、验证方式（假阳性率测量）

final_task: |
  最终轮：给出 epsilon 完整生命周期设计。

  必须包含：
  1. epsilon 冷启动协议（完整伪代码，含各轴类型的初始值映射表）
  2. epsilon 运行时更新算法（含触发条件、更新公式、收敛判定）
  3. epsilon 粒度的最终立场：轴级 vs claim×轴级？给出理由和类型定义
  4. alpha 的完整校准流程（校准集来源、规模、迭代停止条件、最终验证）
  5. 若 epsilon 无法自动推导，手工标注的最小负担方案（操作步骤、每轴需要标注者回答的问题）
  6. 你的方案最可能在什么具体场景下失败，以及接受什么样的运行数据来推翻它

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**

  本轮辩题是 epsilon（测量不确定性）的工程实现问题。裁判必须用「完全不懂统计学的人也能理解」的语言解释最终裁定。

  - 问题 G（冷启动）：用日常类比解释"系统第一次运行时怎么知道测量误差有多大"——
    例如，一个新来的品酒师，在没有任何记录的情况下，如何估计自己对葡萄酒评分的误差范围？
    是靠行业经验值、靠同类品酒师的历史、还是先喝几杯"已知"的葡萄酒校准？

  - 问题 H/I（更新与粒度）：用日常类比解释"随着时间推移，误差估计如何改进"——
    是每个评酒师有一个统一的误差率，还是每款酒都有独立的误差估计？哪种更实用？

  - 问题 J（alpha 校准）：用日常类比解释"如何验证整个评分系统的灵敏度"——
    例如，用一批"已知结果"的老案例来验证侦探的判断准确率。这批案例从哪来，需要多少？

  每个裁定必须包含：
  a. 明确的决策（不得搁置）
  b. 至少一个具体例子（3 个轴，展示 epoch 0 和 epoch 3 时的 epsilon 数值）
  c. 哪些场景下裁定可能需要修正（诚实标注不确定性）
  d. 一句话总结

  **第二部分：可实现性摘要**

  必须产出以下内容：

  1. **EvaluationAxis.epsilon 的初始化规范**（含轴类型分类表和对应初始 epsilon 值）

  2. **epsilon 运行时更新协议**（含触发条件、更新公式、最大更新幅度约束）

  3. **epsilon 粒度的最终裁定**（轴级 vs claim×轴级，附类型定义）

  4. **alpha 校准流程规范**（校准集构造、规模下限、验证方法、迭代停止条件）

  5. **手工标注最小负担方案**（若自动推导不可行，操作步骤不超过 5 步）

  6. **一个完整的 epsilon 生命周期 trace**
     输入：QuestionFrame 含 3 个 evaluation_axes（定量轴、定性轴、混合轴各一）
     展示：epoch 0 → epoch 5 的 epsilon 演化过程，以及对应 score_delta 的变化

  对 G/H/I/J 四个问题必须各给出明确的最终裁定，不得搁置。

---

# v3 认知引擎：EvaluationAxis.epsilon 的冷启动策略与运行时校准

## 一、v3 系统整体背景

v3 认知引擎是一个处理开放式、有争议复杂问题的多层推理系统。其核心架构由两层分离组成：

**Layer 1（问题级薄状态机）**：协调迭代循环，七个显式状态节点依次执行：
```
QN（问题规范化）→ MB（宏观广度探索）→ CC（清晰度编译）
→ D2（Layer 2 派发）→ PA（精度聚合）← 终止判定在此节点执行
→ RB（修复回退，可选）→ AS（答案综合）
```

**Layer 2（命题级深度追溯）**：对每条具体的 `TestableClaim` 进行验证，产出 `VerifiedClaim`，包含 `axis_scores: Partial<Record<AxisId, number>>`（每个已覆盖轴的评分）。

## 二、scoring_termination 裁定的关键结论（直接继承）

`scoring_termination` 辩论已裁定了 `has_ranking_change()` 的实现规范，核心公式为：

```typescript
interface EvaluationAxis {
  axis_id: AxisId;
  weight: number;    // 归一化权重，所有 axis 的 weight 之和 = 1.0
  epsilon: number;   // 该轴的归一化测量不确定性，∈ [0, 1]
}

// score_delta 公式（已裁定）
function compute_score_delta(axes: EvaluationAxis[], alpha: number): number {
  // delta = alpha × Σ(w_a × epsilon_a)
  return alpha * sum(a.weight * a.epsilon for a in axes)
}
```

`score_delta` 作为 `has_ranking_change()` 的分数漂移阈值：若所有 Top-K claim 的跨 epoch 分数变化均小于 `score_delta`，则视为测量噪声，不触发排名变化。

**scoring_termination 裁定明确指出**：
- `alpha` 初始值 1.0，可通过离线回测校准（在已知答案问题集上调整直到假阳性率 < 5%）
- `epsilon` 是 `EvaluationAxis` 的字段，∈ [0, 1]，代表该轴的归一化测量不确定性

**但以下问题在 scoring_termination 中完全未定义**，留给本轮辩论决定：
- `epsilon` 的初始值如何设定（冷启动问题）
- `epsilon` 是否随 epoch 推进动态更新（更新策略问题）
- `epsilon` 的粒度：轴级静态常量 vs claim×轴 动态属性（粒度问题）
- `alpha` 的离线校准所需"已知答案问题集"从哪里来，规模多少（校准集来源问题）

## 三、本轮聚焦的四个核心未决问题

### 问题 G：epsilon 冷启动

系统首次运行时，没有任何 Layer 2 的历史 axis_score 数据。此时：
- 如果 epsilon 全部设为 0，则 score_delta = 0，任何微小分数变化都会触发"排名已改变"判定，系统永不收敛
- 如果 epsilon 全部设为 1，则 score_delta = alpha（最大值），系统对几乎任何分数变化都视为噪声，可能过早终止
- 合理的冷启动 epsilon 必须在"不退化为 0"和"不退化为无穷大"之间找到工程上可辩护的初始点

**核心未决点**：初始值应该是多少？由谁来设定？是领域无关的静态常量还是需要 stakeholder 干预？

### 问题 H：epsilon 运行时更新策略

随着系统积累更多 epoch 的 Layer 2 输出数据，epsilon 是否应该动态调整？

**核心未决点**：
- 是否需要更新（若不更新，冷启动值就是永久值）？
- 如果更新，更新触发条件是什么（每 epoch？达到足够样本量？）？
- 更新算法是什么（滑动窗口方差？指数加权？Bayesian 更新？）？
- 更新的上下界约束是什么（防止 epsilon 收缩到 0 或膨胀到 1）？

### 问题 I：epsilon 粒度

`scoring_termination` 裁定的 `EvaluationAxis.epsilon` 是轴级属性（每个轴一个 epsilon 值）。但也可以考虑更细粒度的 claim×轴 动态属性（每个 claim 在每个轴上有独立的 epsilon）。

**核心未决点**：
- 轴级 epsilon：简单，冷启动容易，但可能忽略不同 claim 在同一轴上的测量精度差异
- claim×轴 epsilon：精细，但参数数量随 claim 数量线性增长，冷启动时每个新 claim 的 epsilon 从哪来？

### 问题 J：alpha 校准

`scoring_termination` 裁定 alpha 初始值为 1.0，可通过"已知答案问题集"离线校准。但：
- "已知答案问题集"从哪里来？人工构建？从历史辩论日志提取？LLM 生成合成数据？
- 规模需要多少？（太少：校准不可靠；太多：构建成本过高）
- 如何验证校准质量？（假阳性率 < 5% 是目标，但假阳性率如何测量？）
- 校准集是问题域通用的还是 per-QuestionFrame 的？

## 四、关键张力地图

```
冷启动 epsilon 张力：
  保守高值（如 0.1~0.15）
    优势：防止系统在早期数据不足时因微小波动频繁重启
    风险：score_delta 过大，系统可能把真实的排名变化误判为噪声而过早终止
  激进低值（如 0.01~0.05）
    优势：系统对排名变化更敏感，不易过早终止
    风险：早期波动大，stable_rounds 计数器频繁归零，系统长期不收敛

epsilon 粒度张力：
  轴级静态（axis-level）
    优势：参数少，冷启动简单，与 scoring_termination 裁定的类型定义一致
    风险：忽略同一轴上不同 claim 的测量精度差异
  claim×轴动态（claim×axis-level）
    优势：精细建模每个 claim 的不确定性
    风险：冷启动循环依赖（新 claim 的 epsilon 需要历史，历史需要先跑几轮）

alpha 校准集张力：
  人工构建（高质量）
    优势：已知答案可信，校准有意义
    风险：构建成本高，覆盖面受限
  LLM 合成生成（低成本）
    优势：可大规模生成，覆盖多种轴类型
    风险：已知答案本身由 LLM 给出，校准链的可信度存疑
  从历史辩论日志提取
    优势：真实数据，有机器可读的 epoch 序列
    风险：历史日志本身没有"ground truth"标签，如何判断哪次终止是正确的？
```

## 五、开放性陈述

本轮辩论不预设任何问题的答案。三位辩手被邀请对上述未决点提出各自的完整方案，并对彼此方案的具体缺陷展开精确攻击。

对于任何方案，以下问题是可推翻条件的检验标准：

1. 给定一个 QuestionFrame，含 3 个 evaluation_axes（权重分别为 0.4、0.35、0.25），你的冷启动方案在 epoch 0 给出的 score_delta 具体是多少？这个值是否会导致"系统在前 3 轮内永不收敛"或"系统在第 1 轮就错误终止"？

2. 若 Layer 2 在 epoch 1 和 epoch 2 对同一个 claim 的某轴给出的 axis_score 分别是 0.72 和 0.68，你的 epsilon 更新算法会把该轴的 epsilon 更新到什么值？

3. 若 epsilon 无法自动推导，标注者需要完成的最小工作量是什么？（以"每个轴回答 N 个问题"的形式量化）
