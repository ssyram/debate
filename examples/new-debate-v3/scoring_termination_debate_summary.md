# v3 认知引擎：has_ranking_change() 的实现与异构命题评分体系 裁判总结

> 2026-03-09T18:24:48.259700

# 裁判裁定

## 第一部分：白话版结论

### 问题 E：异构命题如何建立可比性（评分计算）

**日常类比：** 想象你是一个美食杂志编辑，要给读者推荐"本月最佳餐厅"。你手上有三家餐厅的评价：

- 餐厅A：一位食评家说"口味极佳"（但没评价服务和环境）
- 餐厅B：三位食评家分别说"口味不错""服务很快""环境优雅"
- 餐厅C：一位食评家说"性价比极高"（跟前两家完全不在同一个评价维度）

**辩论的核心分歧是：** 你该怎么把这些"不同维度的评价"变成一个可以排名的分数？

- **Linus 说：** 事先定好评分卡（口味占40%、服务占30%、环境占20%、性价比占10%），每家餐厅按覆盖的维度打分，没被评到的维度不算进分母但会扣一个"覆盖不全"的罚分。最后算出一个总分，直接排名。
- **Ssyram 说：** 类似 Linus，但更强调每个维度的分数必须由具体证据严格折算出来，不能让评审员随便打分。
- **康德 说：** 根本不应该硬算总分！只有在两家餐厅被评价过**相同维度**时，才能比较它们谁更好。如果一家只被评了"口味"、另一家只被评了"性价比"，它们就是"不可比的"——硬排名是自欺欺人。

**我的裁定：采纳 Linus 的加权覆盖率方案作为系统的构成性评分机制，同时吸收康德的部分批评作为审计层约束。**

理由如下：

**a. 明确裁定：** Linus 方案（加权投影 + 覆盖率惩罚的总序）胜出，康德的纯偏序方案被否决作为终止判定的基础。

康德的认识论批评是深刻的——把"口味好"和"服务快"加在一起确实有哲学上的可疑性。但康德自己无法解决一个致命的工程问题：如果三家餐厅各自只被评了不同的维度，它们互相"不可比"，那编辑永远无法决定推荐哪家，杂志永远出不了。Ssyram 在交叉质询中反复追问的"Top-K 切片悖论"——康德的代码写了 `prev[:k]` 切片但自己又否认全局排序的存在——这一矛盾康德始终未能解决。康德在第9轮和第15轮试图用"comparability_cluster 代表元"来缓解，但 `cluster_id` 的计算规则始终是悬空引用，没有给出等价关系的精确定义。

然而，康德的批评迫使 Linus 方案必须承认一个重要约束：**总分只是在特定权重声明下的投影，不是命题的"客观价值"。** 这一点必须在系统的审计输出中明确标注。

**b. 具体例子：** 假设问题框架声明了三个评估轴：交付速度（权重0.4）、人才留存（权重0.35）、运营成本（权重0.25）。

- Claim X："采用微服务可将部署频率提升3倍"——只覆盖交付速度轴，axis_score = 0.85。
  - coverage = 0.4，base = 0.85，score = 0.85 × 0.4^0.5 = 0.85 × 0.632 = 0.537
- Claim Y："混合办公模式下离职率降低20%"——只覆盖人才留存轴，axis_score = 0.70。
  - coverage = 0.35，base = 0.70，score = 0.70 × 0.35^0.5 = 0.70 × 0.592 = 0.414

在 Linus 方案下，X > Y（0.537 > 0.414），因为 X 覆盖了更高权重的轴且表现更强。在康德方案下，X 和 Y "不可比"，因为它们没有共享轴——这在认识论上诚实但在工程上导致系统无法终止。

**c. 可能需要修正的场景：**
- 当绝大多数 claim 彼此无共享轴时（极端异构场景），覆盖率惩罚可能导致所有 claim 分数都很低，排名主要由覆盖率而非实质证据质量决定。此时 γ 参数需要根据领域特征调整，甚至可能需要回退到分簇展示模式（即在产品层采纳康德方案，但终止判定层仍用总序）。
- 当 stakeholder 的权重声明本身存在内部矛盾时，系统应产出诊断性 GapSpec 而非默默算出一个数。

**d. 一句话总结：** 用预声明权重的加权评分卡得出总分来排名，但在审计报告中诚实标注"这个总分是在特定权重假设下的投影，不是绝对真理"。

---

### 问题 F：系统如何知道什么时候可以停下来（终止判定）

**日常类比：** 侦探办案。侦探什么时候可以"结案"？

- **Linus 说：** 连续两次调查之后，嫌疑人名单的前几名没变，而且分数波动也没超过测量误差范围，就可以结案。但只考虑"有足够证据的"嫌疑人——如果某个嫌疑人只有一条间接线索，暂时不列入排名。
- **Ssyram 说：** 类似 Linus，但更强调"测量误差范围"必须从证据工具的精度自动推导，不能人工拍脑袋。
- **康德 说：** 不能只看名单有没有变。必须区分"当前能排名的嫌疑人确实稳定了"和"还有很多线索方向根本没查过"。如果有一个高价值方向完全未被调查，即使现有名单很稳定，也不能结案。

**我的裁定：采纳 Linus 的双层判定机制（集合稳定性 + 分数漂移 + 滞回轮次），同时吸收康德关于 GapSpec 阻塞终止的约束。**

**a. 明确裁定：** Linus 的 `has_ranking_change()` 实现方案胜出，但必须增加康德提出的"regulative residue 阻塞"检查。

Linus 的方案最大的优势是**可执行性**：函数签名明确、配对逻辑正确（按 claim_id 对齐而非位置）、滞回机制防振荡。Ssyram 的方案在 zip 配对上犯了基础错误（辩论中承认），且 delta 公式与 Linus 实质等价但多了一层不必要的复杂性。康德的 cluster_id 方案因为缺乏可计算的聚类规则而无法落地。

但康德提出了一个关键的安全约束：**排序稳定不等于探索充分。** 如果存在高权重轴完全未被任何 claim 覆盖（即"侦探还有一个关键方向完全没查"），即使现有排名连续两轮不变，系统也不应该自信地宣布"结论已经确定"。这一点 Linus 在第12轮被康德质疑后始终没有正面回答。

因此，终止判定必须是：`has_ranking_change() == False` **且** 不存在阻塞性 GapSpec。

**b. 具体例子：** 侦探有三个调查方向：动机（权重0.4）、不在场证明（权重0.35）、物证（权重0.25）。连续两轮调查后，"嫌疑人甲"在动机维度得分最高且排名稳定。但如果物证方向完全没有被调查过（高权重轴未覆盖），系统不应终止——应该产出 GapSpec `{kind: "UNCOVERED_HIGH_WEIGHT_AXIS", blocks_termination: true}` 并触发新一轮调查。

**c. 可能需要修正的场景：**
- 当预算即将耗尽时，即使存在阻塞性 GapSpec，系统也必须能够降级终止（BUDGET_EXHAUSTED），同时在输出中标注"结论受限于未探索维度"。
- coverage 边界处的振荡（claim 的 coverage 在 min_coverage 附近反复跳动）可能导致 Top-K 集合不稳定。Ssyram 对此的批评是有效的——硬阶跃函数确实有问题，但 Linus 的滞回轮次机制（hysteresis_rounds = 2）在大多数实际场景下足以抑制此问题。极端情况下可引入 coverage 的平滑过渡带（如 coverage ∈ [min_coverage - ε, min_coverage + ε] 区间内用线性插值），但这是优化而非核心架构变更。

**d. 一句话总结：** 连续两轮排名前几名没变且分数波动在测量误差内，就可以停——但前提是没有"关键方向完全没查过"的情况。

---

## 第二部分：可实现性摘要

### 1. VerifiedClaim.score 的最终计算规范

```typescript
// === 类型定义 ===

type AxisId = string;

interface EvaluationAxis {
  axis_id: AxisId;
  weight: number;        // 归一化权重，所有 axis 的 weight 之和 = 1.0
  epsilon: number;       // 该轴的归一化测量不确定性，∈ [0, 1]
}

// axis_weight 声明位置：QuestionFrame.evaluation_axes[]
// axis_weight 来源：由 stakeholder 在问题定义阶段预声明，不可由系统运行时发明
interface QuestionFrame {
  evaluation_axes: EvaluationAxis[];  // Σ weight = 1.0
  // ... 其他字段
}

interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;                          // ∈ [0, 1]
  axis_scores: Partial<Record<AxisId, number>>;   // 每个已覆盖轴的评分 ∈ [0, 1]
  // axis_scores 中不存在的 key = N/A（该 claim 不涉及该轴）
  // axis_scores 的值由 Layer 2 根据结构化证据产出
}

interface RankedClaim {
  claim_id: string;
  score: number;       // ∈ [0, 1]，由下述公式计算
  coverage: number;    // ∈ [0, 1]，已覆盖轴的权重质量
}
```

```
// === 评分伪代码 ===

GAMMA = 0.5   // 覆盖率惩罚指数，可由 QuestionFrame 预声明覆盖

function status_factor(status):
    if status == "VERIFIED": return 1.0
    if status == "DEFENSIBLE": return 0.7

function compute_ranked_claim(claim: VerifiedClaim, axes: EvaluationAxis[]) -> RankedClaim:
    // Step 1: 确定已覆盖轴集合
    covered_axes = [a for a in axes if a.axis_id in claim.axis_scores]
    
    // Step 2: 覆盖率 = 已覆盖轴的权重质量之和
    coverage = sum(a.weight for a in covered_axes)
    // coverage ∈ [0, 1]；若 claim 不覆盖任何轴，coverage = 0
    
    // Step 3: 局部归一化基础分
    if coverage == 0:
        return RankedClaim(claim.claim_id, score=0, coverage=0)
    
    base = sum(a.weight * claim.axis_scores[a.axis_id] for a in covered_axes) / coverage
    // base ∈ [0, 1]：已覆盖轴上的加权平均表现
    
    // Step 4: 质量修正
    quality = status_factor(claim.status) * (1 - claim.residual_risk)
    // quality ∈ [0, 1]
    
    // Step 5: 最终得分 = 局部表现 × 质量修正 × 覆盖率惩罚
    score = base * quality * coverage^GAMMA
    // score ∈ [0, 1]
    
    return RankedClaim(claim.claim_id, score, coverage)
```

**归一化协议（处理"某 claim 不涉及某 axis"的情况）：**
- `axis_scores` 中缺失的 key 即为 N/A——该 claim 不涉及该轴
- N/A 轴**不参与分子和分母**（局部归一化：只在已覆盖轴上计算加权平均）
- 但 N/A 轴通过 `coverage^GAMMA` 间接惩罚总分（覆盖轴权重质量越低，惩罚越大）
- 这避免了康德批评的"把 N/A 当 0 混入同一数域"，也避免了完全无惩罚导致"单轴高分 claim 系统性压制多轴 claim"

**score 的值域和语义：**
- 值域：[0, 1]
- 语义：该 claim 在 QuestionFrame 预声明的评估轴空间中，综合考虑证据强度、验证状态、残余风险和维度覆盖广度后的归一化贡献度
- **审计约束**：score 是在特定 QuestionFrame.evaluation_axes 权重声明下的投影值，不是 claim 的内禀属性。改变权重声明会改变 score

### 2. has_ranking_change() 的最终实现规范

```typescript
// === 函数签名 ===

interface TerminationConfig {
  top_k: number;                 // 来源：QuestionFrame 预声明或系统默认值
  min_coverage: number;          // 最低覆盖率门槛，∈ [0, 1]；来源：QuestionFrame
  hysteresis_rounds: number;     // 滞回轮次，默认 2
  alpha: number;                 // delta 缩放因子，默认 1.0，可离线校准
}

function compute_score_delta(axes: EvaluationAxis[], alpha: number): number {
  // delta = alpha * Σ(w_a * epsilon_a)
  // 语义：各轴测量不确定性的加权聚合，作为"排名变化是否超出噪声"的阈值
  return alpha * sum(a.weight * a.epsilon for a in axes)
}
```

**Top-K 集合的精确定义：**
- K 来源：`TerminationConfig.top_k`，由 QuestionFrame 预声明（如"关注前3个最重要的结论"）
- 集合元素：`RankedClaim`（含 claim_id, score, coverage）
- 筛选规则：仅保留 `coverage >= min_coverage` 的 claim，按 score 降序排列，取前 K 个
- 若满足条件的 claim 不足 K 个，则 Top-K 为全部满足条件的 claim

```
// === 完整实现 ===

function has_ranking_change(
    prev: RankedClaim[],      // 上一轮的排序结果（已按 score 降序）
    curr: RankedClaim[],      // 本轮的排序结果（已按 score 降序）
    config: TerminationConfig,
    axes: EvaluationAxis[]
) -> bool:
    
    score_delta = compute_score_delta(axes, config.alpha)
    
    // Step 1: 筛选可排序 claim
    prev_rankable = [c for c in prev if c.coverage >= config.min_coverage]
    curr_rankable = [c for c in curr if c.coverage >= config.min_coverage]
    
    // Step 2: 取 Top-K
    top_prev = prev_rankable[:config.top_k]
    top_curr = curr_rankable[:config.top_k]
    
    // Step 3: 集合变化检测
    prev_ids = {c.claim_id for c in top_prev}
    curr_ids = {c.claim_id for c in top_curr}
    
    if prev_ids != curr_ids:
        return True   // Top-K 成员变化 → 排名已改变
    
    // Step 4: 分数漂移检测（按 claim_id 对齐，非按位置）
    prev_map = {c.claim_id: c.score for c in top_prev}
    curr_map = {c.claim_id: c.score for c in top_curr}
    
    max_drift = max(abs(prev_map[id] - curr_map[id]) for id in prev_ids)
    
    if max_drift >= score_delta:
        return True   // 分数漂移超出噪声阈值 → 排名已改变
    
    return False      // Top-K 集合相同且分数漂移在噪声范围内 → 排名未改变
```

**防振荡机制：**
```
// === 终止判定的外层控制（PA 节点状态机）===

function should_terminate(
    ranking_history: RankedClaim[][],  // 各 epoch 的排序结果历史
    gap_specs: GapSpec[],              // 当前未解决的认知缺口
    config: TerminationConfig,
    axes: EvaluationAxis[]
) -> { terminate: bool, reason: string }:
    
    // 检查 1: 阻塞性 GapSpec（吸收康德的约束）
    blocking_gaps = [g for g in gap_specs if g.blocks_termination]
    if blocking_gaps.length > 0:
        return { terminate: false, reason: "BLOCKING_GAPS_EXIST" }
    
    // 检查 2: 滞回轮次——连续 hysteresis_rounds 轮无排名变化
    if ranking_history.length < config.hysteresis_rounds + 1:
        return { terminate: false, reason: "INSUFFICIENT_ROUNDS" }
    
    stable_count = 0
    for i in range(ranking_history.length - 1, 0, -1):
        if not has_ranking_change(ranking_history[i-1], ranking_history[i], config, axes):
            stable_count += 1
        else:
            break
    
    if stable_count >= config.hysteresis_rounds:
        return { terminate: true, reason: "NO_RANKING_CHANGE" }
    
    return { terminate: false, reason: "RANKING_STILL_CHANGING" }
```

**delta 的来源和计算方法：**
- 来源：`EvaluationAxis.epsilon`（各轴的测量不确定性）+ `alpha`（全局缩放因子）
- 计算：`delta = alpha * Σ(w_a * epsilon_a)`
- 语义：如果所有 Top-K claim 的分数变化都在 delta 以内，视为测量噪声而非实质变化
- alpha 的确定：初始值 1.0，可通过离线回测校准（在已知答案的问题集上调整直到假阳性率 < 5%）

**关于康德偏序方案的裁定说明：** 偏序方案不作为终止判定的基础实现。理由总结如下：
1. 康德的 `comparability_cluster` 缺乏可计算的等价关系定义（Ssyram 质询二未获回答）
2. `prev[:k]` 切片与偏序语义自相矛盾（Ssyram 质询一，康德未能化解）
3. Pareto 前沿在互不可比 claim 不断涌入时无限膨胀，`stable_rounds >= 2` 不具可判定性

但偏序的价值保留在产品展示层：如果系统需要向 stakeholder 解释"为什么 X 排在 Y 前面"，应展示各轴分数的雷达图而非仅展示总分。

### 3. regulative_residue 的分类标准

```typescript
type GapSpec = {
  kind: GapKind;
  blocks_termination: boolean;
  axis_id?: AxisId;           // 涉及的轴（如果适用）
  description: string;
};

type GapKind = 
  | "UNCOVERED_HIGH_WEIGHT_AXIS"   // 高权重轴完全无 claim 覆盖
  | "UNRESOLVED_DEFEATER"          // 存在未解决的反证
  | "WEIGHT_UNDERSPECIFIED"        // 权重声明不完整
  | "EVIDENCE_CONFLICT"            // 同一轴上证据严重冲突
  | "LOW_COVERAGE_FRONTIER"        // 前沿 claim 覆盖率普遍偏低
  | "STAKEHOLDER_DISAGREEMENT";    // stakeholder 权重矛盾
```

**阻塞终止的 GapSpec（blocks_termination = true）：**

| GapKind | 阻塞条件 | 理由 |
|---------|----------|------|
| `UNCOVERED_HIGH_WEIGHT_AXIS` | 该轴 weight > max(所有已覆盖轴 weight) 的 50% | 最关键的评估维度完全没有证据支撑，"结案"不诚实 |
| `UNRESOLVED_DEFEATER` | 反证针对当前 Top-K 中的 claim | 最高排名的结论存在未回应的反驳，结论不可靠 |
| `EVIDENCE_CONFLICT` | 同一轴上两个 VERIFIED claim 方向相反 | 核心证据自相矛盾，排名无意义 |
| `WEIGHT_UNDERSPECIFIED` | 超过 30% 的权重质量未被声明 | 评分体系本身不完整 |

**可留为残余的 GapSpec（blocks_termination = false）：**

| GapKind | 非阻塞条件 | 理由 |
|---------|------------|------|
| `UNCOVERED_HIGH_WEIGHT_AXIS` | 该轴 weight ≤ 已覆盖最高轴 weight 的 50% | 次要维度缺失不影响主要结论 |
| `LOW_COVERAGE_FRONTIER` | Top-K claim 的平均 coverage > 0.5 | 主要结论有足够维度支撑 |
| `STAKEHOLDER_DISAGREEMENT` | 总是非阻塞 | 价值冲突不是认知不足，应在产品层展示多视角排名 |
| `UNRESOLVED_DEFEATER` | 反证仅针对 Top-K 外的 claim | 不影响当前最高排名结论 |

### 4. 完整终止判定 trace

**输入：3 个异构 VerifiedClaim**

QuestionFrame 的 evaluation_axes：
```
axes = [
  { axis_id: "delivery_speed", weight: 0.40, epsilon: 0.08 },
  { axis_id: "talent_retention", weight: 0.35, epsilon: 0.12 },
  { axis_id: "operational_cost", weight: 0.25, epsilon: 0.10 }
]
```

TerminationConfig：
```
config = { top_k: 2, min_coverage: 0.20, hysteresis_rounds: 2, alpha: 1.0 }
```

三个 VerifiedClaim：
```
Claim_A = {
  claim_id: "microservices_deploy",
  status: "VERIFIED",
  residual_risk: 0.10,
  axis_scores: { "delivery_speed": 0.85 }
  // 仅覆盖交付速度
}

Claim_B = {
  claim_id: "hybrid_work_retention",
  status: "DEFENSIBLE",
  residual_risk: 0.15,
  axis_scores: { "talent_retention": 0.80, "operational_cost": 0.60 }
  // 覆盖人才留存和运营成本
}

Claim_C = {
  claim_id: "cloud_migration_cost",
  status: "VERIFIED",
  residual_risk: 0.05,
  axis_scores: { "operational_cost": 0.90, "delivery_speed": 0.50 }
  // 覆盖运营成本和交付速度
}
```

**Step 1：各自如何被评分**

**Claim_A (microservices_deploy)：**
```
covered_axes = ["delivery_speed"]
coverage = 0.40
base = (0.40 × 0.85) / 0.40 = 0.85
quality = 1.0 × (1 - 0.10) = 0.90
score = 0.85 × 0.90 × 0.40^0.5 = 0.85 × 0.90 × 0.6325 = 0.4839
```

**Claim_B (hybrid_work_retention)：**
```
covered_axes = ["talent_retention", "operational_cost"]
coverage = 0.35 + 0.25 = 0.60
base = (0.35 × 0.80 + 0.25 × 0.60) / 0.60 = (0.28 + 0.15) / 0.60 = 0.7167
quality = 0.7 × (1 - 0.15) = 0.595
score = 0.7167 × 0.595 × 0.60^0.5 = 0.7167 × 0.595 × 0.7746 = 0.3303
```

**Claim_C (cloud_migration_cost)：**
```
covered_axes = ["operational_cost", "delivery_speed"]
coverage = 0.25 + 0.40 = 0.65
base = (0.25 × 0.90 + 0.40 × 0.50) / 0.65 = (0.225 + 0.20) / 0.65 = 0.6538
quality = 1.0 × (1 - 0.05) = 0.95
score = 0.6538 × 0.95 × 0.65^0.5 = 0.6538 × 0.95 × 0.8062 = 0.5008
```

**Step 2：如何参与排序**

所有 claim 的 coverage 均 ≥ min_coverage (0.20)，全部可排序。

按 score 降序排列：
```
Rank 1: Claim_C (cloud_migration_cost)   score = 0.5008, coverage = 0.65
Rank 2: Claim_A (microservices_deploy)    score = 0.4839, coverage = 0.40
Rank 3: Claim_B (hybrid_work_retention)   score = 0.3303, coverage = 0.60
```

Top-2 = {Claim_C, Claim_A}

**Step 3：has_ranking_change() 的计算过程**

假设这是 Epoch 3，ranking_history 如下：

**Epoch 1（仅有 Claim_A）：**
```
Top-2 = {Claim_A}  (只有一个 claim)
```

**Epoch 2（Claim_A + Claim_B 出现）：**
```
Claim_A: score = 0.4839
Claim_B: score = 0.3303
Top-2 = {Claim_A, Claim_B}
```

Epoch 1→2 比较：
```
prev_ids = {"microservices_deploy"}
curr_ids = {"microservices_deploy", "hybrid_work_retention"}
prev_ids ≠ curr_ids → has_ranking_change = True
stable_count = 0
```

**Epoch 3（Claim_C 出现）：**
```
Top-2 = {Claim_C, Claim_A}
```

Epoch 2→3 比较：
```
prev_ids = {"microservices_deploy", "hybrid_work_retention"}
curr_ids = {"cloud_migration_cost", "microservices_deploy"}
prev_ids ≠ curr_ids → has_ranking_change = True
stable_count = 0
```

**Epoch 4（无新 claim，证据微调：Claim_C residual_risk 从 0.05 降到 0.04）：**
```
Claim_C: quality = 1.0 × 0.96 = 0.96, score = 0.6538 × 0.96 × 0.8062 = 0.5061
Claim_A: 不变, score = 0.4839
Top-2 = {Claim_C, Claim_A}
```

Epoch 3→4 比较：
```
score_delta = 1.0 × (0.40 × 0.08 + 0.35 × 0.12 + 0.25 × 0.10)
            = 1.0 × (0.032 + 0.042 + 0.025)
            = 0.099

prev_ids = {"cloud_migration_cost", "microservices_deploy"}
curr_ids = {"cloud_migration_cost", "microservices_deploy"}
prev_ids == curr_ids → 检查分数漂移

max_drift = max(|0.5061 - 0.5008|, |0.4839 - 0.4839|)
          = max(0.0053, 0.0)
          = 0.0053

0.0053 < 0.099 → has_ranking_change = False
stable_count = 1
```

**Epoch 5（无新 claim，无变化）：**
```
Top-2 不变，max_drift = 0
has_ranking_change = False
stable_count = 2
```

**Step 4：终止判定**

```
stable_count (2) >= hysteresis_rounds (2) ✓

检查 GapSpec：
- "talent_retention" 轴 (weight=0.35) 未被 Top-2 中任一 claim 覆盖？
  → Claim_A 不覆盖，Claim_C 不覆盖
  → 但 Claim_B 覆盖了且在 Top-K 之外
  → GapSpec: UNCOVERED_HIGH_WEIGHT_AXIS?
  → 检查：talent_retention weight (0.35) > max(已覆盖轴 weight) × 50%?
    → Top-2 覆盖的轴：delivery_speed (0.40), operational_cost (0.25)
    → max = 0.40, 50% = 0.20
    → 0.35 > 0.20 → YES → blocks_termination = true

结论：虽然排名连续两轮稳定，但人才留存轴（高权重）
未被 Top-2 claim 覆盖，存在阻塞性 GapSpec。

→ terminate = false
→ reason = "BLOCKING_GAPS_EXIST: talent_retention axis (weight=0.35) 
   uncovered by Top-K claims"
```

系统应触发新一轮探索，要求 Layer 2 生成覆盖 talent_retention 轴的 claim 或将 Claim_B 的 claim 进一步验证提升其地位。

**若 Epoch 6 后 Claim_B 升级为 VERIFIED 且进入 Top-2：**
```
Claim_B (revised): status=VERIFIED, residual_risk=0.08
quality = 1.0 × 0.92 = 0.92
score = 0.7167 × 0.92 × 0.7746 = 0.5110

新排序: Claim_C (0.5061), Claim_B (0.5110) → 
Top-2 = {Claim_B, Claim_C}

此时 Top-2 覆盖轴 = {talent_retention, operational_cost, delivery_speed} = 全部轴
阻塞性 GapSpec 消除

再经两轮稳定 → terminate = true, reason = "NO_RANKING_CHANGE"
```

### 5. 实现难度最高的 2 个模块及其风险

**模块 1：Layer 2 → axis_scores 映射（风险等级：极高）**

这是整个系统中最难、风险最高的环节。`axis_scores: Partial<Record<AxisId, number>>` 中的每个数值必须由 Layer 2 的结构化证据产出，但 Layer 2 的核心执行者是 LLM。

**风险清单：**
- **黑盒标量转移问题：** Linus 和 Ssyram 都正确指出，如果 axis_scores 的值最终由 LLM "评估"产出，那整个精密的归一化协议只是在一个不可靠的地基上搭建精密仪器。系统把"一个黑盒总分"拆成了"多个黑盒分量"，类型上更丰富了，但认识论上的不确定性并未降低。
- **跨 epoch 标注漂移：** 同一条证据在不同 epoch 可能被 LLM 挂载到不同 axis 上（Linus 交叉质询第10轮提出的 M(c,a) 漂移问题），导致排序变化反映的是标注噪声而非实质证据变化。
- **缓解策略：** (1) 要求 Layer 2 对每个 axis_score 附带 evidence_chain（证据链引用），使 PA 可审计数值来源；(2) 引入 axis_score 的跨 epoch 一致性检查——同一 claim 在相邻 epoch 的 axis_scores 变化超过阈值时触发人工审核标记；(3) 长期方向：用结构化规则引擎替代 LLM 做 axis-claim 映射，LLM 仅负责证据发现。

**模块 2：GapSpec 的自动化检测与 blocks_termination 判定（风险等级：高）**

GapSpec 系统需要自动识别"哪些认知缺口足以阻止终止"，这要求系统具有**元认知能力**——不是"回答问题"，而是"判断自己是否还有关键盲区"。

**风险清单：**
- **假阴性风险（漏检阻塞性 gap）：** 系统可能无法检测到"所有 Top-K claim 都未覆盖某个高权重轴"的情况，尤其当 QuestionFrame 的 evaluation_axes 本身不完整时（所谓的"未知的未知"——Unknown Unknowns）。
- **假阳性风险（过度阻塞）：** 如果 GapSpec 检测过于敏感，系统可能永远找到新的"未覆盖方向"而无法终止，最终总是以 BUDGET_EXHAUSTED 结束，使整个终止判定机制形同虚设。
- **UNRESOLVED_DEFEATER 的判定边界模糊：** "反证是否针对 Top-K claim"需要语义匹配，这又把 LLM 引入了关键路径。
- **缓解策略：** (1) GapSpec 的 blocks_termination 判定规则必须是纯函数，基于可计算的结构化属性（轴权重、覆盖率、claim 状态），不依赖 LLM 推理；(2) 设置 GapSpec 阻塞的最大持续轮次——如果某个 GapSpec 连续 N 轮存在但无法被解决，降级为 regulative_residue 并在输出中标注；(3) 区分 "Known Unknown"（可检测的 gap）和 "Unknown Unknown"（不可检测的 gap），系统只对前者负责。

---

**最终裁定总结：**

| 问题 | 裁定 | 核心理由 |
|------|------|----------|
| E（评分） | Linus 的加权投影 + 覆盖率惩罚总序 | 可执行、可审计，偏序方案导致终止不可判定 |
| F（终止） | Linus 的 has_ranking_change + 康德的 GapSpec 阻塞 | 双层保障：排名稳定性 + 探索充分性 |