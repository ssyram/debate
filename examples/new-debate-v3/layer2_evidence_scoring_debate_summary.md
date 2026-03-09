# v3 认知引擎：Layer 2 的 axis_scores 产出机制 裁判总结

> 2026-03-09T19:11:27.223027



# 裁判裁定书

---

# 第一部分：白话版结论

## 辩题背景

这场辩论的核心问题是：当系统需要阅读大量自然语言材料（新闻、报告、用户评论），然后给出一个数字分数（比如"这个方案的安全性得 0.72 分"），这个数字到底怎么产生才是合理的、可信的、可追查的？

四个子问题可以用日常生活类比：

- **问题 I**：教授改论文，是直接凭感觉给分，还是先列评分细则再打分？
- **问题 J**：判决书引用证据，格式要怎么写才算"有据可查"？
- **问题 K**：同一道菜上周评 85 分、这周评 45 分，系统怎么判断是菜变了还是评委飘了？
- **问题 L**：这个分数是"精密仪器测出来的"还是"估摸着猜的"，消费者有没有权利知道？

---

## 裁定 I：axis_scores 产出方式 — 两阶段协议

### 明确选择

**采纳双方共识的"两阶段协议"，但在关键分歧点上做如下裁定：**

> LLM 只做"语义降维"（把一段话变成结构化的证据卡片），规则引擎做"数值折算"（把卡片变成分数）。LLM 永远不得直接输出最终分数。

**白话解释**：想象一个美食评审大赛。第一步，让一位语言能力很强但数学不太靠谱的助手（LLM）阅读所有食评，把每条评论归类：这条说"好吃"（正面、轶事级别），那条说"经过双盲测试甜度提升 23%"（正面、统计级别）。第二步，由一台计算器（规则引擎）按照预定的评分细则，把这些归类好的卡片折算成分数。

助手绝对不能直接喊出"我觉得 82 分"——因为你没法追问这个 82 是怎么来的，也没法计算它的误差有多大。

**关键分歧裁定——规则从哪来？**

- GPT-5.4 主张规则由 Layer 1 通过 `axis_rulebook` 下发，Layer 2 只执行折算。
- Gemini 主张 Layer 2 内置默认阶梯值（ANECDOTAL→0.15, CORRELATIONAL→0.40, CAUSAL_STATISTICAL→0.75），QuestionFrame 可覆盖。

**裁定：采纳 Gemini 的"默认 + 可覆盖"方案，但增加 GPT-5.4 要求的硬约束。**

理由：GPT-5.4 正确指出"跨领域常数不应硬编码在 Layer 2"，但 Gemini 正确反驳"Layer 1 不可能为每个动态生成的 axis 都提前准备好规则表"。折中方案是：Layer 2 持有保守的默认阶梯值（作为 fallback），但 QuestionFrame **可以**下发领域特定的覆盖规则。当使用默认值时，`score_provenance` 必须标注为 `DEFAULT_TIER`，消费侧据此增加不确定性。

**具体例子**：

> 证据："根据 2024 年 Q3 内部调查，87% 的用户对新配送速度表示满意（n=12,000, p<0.001）"
> 
> - **阶段 A（LLM 语义降维）**：产出一张结构化卡片——极性=PRO，强度等级=CAUSAL_STATISTICAL，来源=外部文档，关联轴=delivery_speed
> - **阶段 B（规则引擎折算）**：查 QuestionFrame 下发的规则表（若有）或默认阶梯值，CAUSAL_STATISTICAL 对应基础分 0.75，乘以极性系数 +1，得 axis_score=0.75

**可能需要修正的场景**：当领域极其新颖（比如"量子计算对药物发现的影响"），默认阶梯值可能系统性偏低或偏高，因为我们的经验常数来自传统领域。此时应强制要求 QuestionFrame 提供领域特定覆盖。

**一句话总结**：LLM 做翻译，规则做计算，翻译手册有默认版但允许甲方提供定制版。

---

## 裁定 J：evidence_chain 格式规范

### 明确选择

**采纳双方在最终轮次已趋同的 ADT（代数数据类型）方案，GPT-5.4 的版本在类型精度上更胜一筹。**

> 每条证据的来源引用必须区分"原始文档片段"和"已验证的内部命题"，绝不能混用。

**白话解释**：想象法庭上，律师说"根据证据 A"。法官必须能追问：这个"证据 A"是原始物证（一段监控录像、一份合同原文），还是另一个案子的判决结论（"法院已认定张三有罪"）？这两者的可靠性、失效条件完全不同。如果引用的那个判决被上级法院推翻了，基于它的所有推理都要重新审视——但原始监控录像不会因为别的案子翻案而消失。

**关键分歧裁定——一条证据能不能同时关联多个评分维度？**

- GPT-5.4 坚持"一个 atom 只挂一个 axis"（一条证据只对一个维度打分）
- Gemini 允许"一条证据通过 axis_mapping 关联多个 axis"

**裁定：采纳 GPT-5.4 的"一 atom 一 axis"方案。**

理由：这是本次辩论中最关键的架构分歧。Gemini 的多轴映射方案看似灵活，但正如 GPT-5.4 精准指出的——**谁来赋值跨轴权重？** Gemini 自己也承认 LLM 不应该分配权重，但规则引擎也无法为动态生成的 axis 组合预置权重表。这就形成了逻辑死锁。

一 atom 一 axis 的方案虽然看起来"笨"，但它彻底消除了权重分配问题。如果同一段文字确实影响两个维度，就拆成两个 atom，各自独立走折算流程。冗余优于模糊。

**具体例子**：

> 证据："MTTR（平均修复时间）降低 40%"同时影响 reliability 和 ops_efficiency 两个轴。
> 
> 拆成两个 EvidenceAtom：
> - Atom-1: ref=同一文档片段, axis_id=reliability, polarity=PRO, tier=CAUSAL_STATISTICAL
> - Atom-2: ref=同一文档片段, axis_id=ops_efficiency, polarity=PRO, tier=CAUSAL_STATISTICAL
> 
> 两者独立折算，不需要任何跨轴权重分配。

**可能需要修正的场景**：当 axis 数量极大（>20）且证据高度交叉时，atom 数量可能爆炸。但这是计算效率问题，不是正确性问题，可以通过剪枝而非放松类型约束来解决。

**一句话总结**：一条证据只给一个维度打分，需要影响多个维度就拆成多张卡片，宁可重复也不模糊。

---

## 裁定 K：跨 epoch 一致性约束

### 明确选择

**采纳 Gemini 的 ε 耦合触发机制（τ = 2ε），但增加 GPT-5.4 要求的 claim_id 对齐和双向差异分解。**

> 如果两次评分之差超过误差范围的两倍，系统自动触发审核，但不是简单地报警，而是要说清楚"差异来自新证据还是旧证据失效"。

**白话解释**：想象你是米其林评审。上个月给一家餐厅 85 分，这个月给 45 分。差了 40 分，远超你自己承认的"每次评分可能有 ±5 分误差"的范围。系统会说："等等，请解释。"但关键不是简单报警，而是要追问：是因为厨师换了（新证据），还是因为你上次手松了（评委标准漂移）？

**具体机制**：

1. **阈值 τ 的来源**：`τ(axis) = 2 × ε(axis)`，其中 ε 是当前 epoch 该轴的测量不确定性。这不是魔法数字——它直接来自证据质量。证据越硬（统计数据多），ε 越小，τ 越严格；证据越软（都是轶事），ε 越大，τ 越宽松。这在认识论上是自洽的。

2. **触发后的差异分解**：不是简单设 `drift_flag = true`，而是要做 claim_id 级别的对齐——
   - 哪些证据是新增的？
   - 哪些证据被撤回了（因为引用的内部 claim 被降级）？
   - 剩余不变证据的折算结果是否一致？（如果不一致，说明规则引擎本身变了，这是系统 bug）

**具体例子**：

> Epoch 1：delivery_speed axis_score = 0.75, ε = 0.08, τ = 0.16
> Epoch 2：delivery_speed axis_score = 0.52
> |Δ| = 0.23 > τ = 0.16 → 触发审核
> 
> 差异分解：
> - Epoch 1 有 3 个 PRO atom，Epoch 2 有 2 个 PRO + 1 个 CON
> - 新增 CON atom 来自一份新发布的用户调查
> - 结论：差异来自新证据，不是评委漂移 → drift_flag = false, evidence_delta_flag = true

**可能需要修正的场景**：当 ε 极大（全是轶事证据，ε 可能达 0.3+），τ = 2ε = 0.6，这意味着分数从 0.2 跳到 0.8 都不会触发审核。这在认识论上是诚实的（"我们本来就没什么把握"），但在用户体验上可能令人不安。可能需要设置一个绝对阈值下限（如 τ_min = 0.25）。

**一句话总结**：分数波动超过误差的两倍就要审查，但审查的重点是"为什么变了"而不是"变了就有罪"。

---

## 裁定 L：认识论诚实性标注

### 明确选择

**采纳 GPT-5.4 的立场：Score 和 Epsilon 必须严格解耦，LLM 的置信度只影响 Epsilon，不影响 Score。**

> 分数表达的是"证据说了什么"（本体论），误差表达的是"我们对提取过程有多确定"（认识论）。两者不得混淆。

**白话解释**：你去医院做血糖检测。报告单上写"血糖 7.2 mmol/L"，这是测量值（本体论——你的血糖确实是这个水平）。后面括号里写"±0.3"，这是仪器精度（认识论——仪器可能有这么大的偏差）。你不会因为仪器精度差就说"那血糖改成 6.9 吧"——你应该说"血糖 7.2，但可能在 6.9 到 7.5 之间"。

同理：一条证据说"满意度提升 23%"，这是 CAUSAL_STATISTICAL 级别，折算分 0.75。但 LLM 提取这条证据时只有 60% 的把握自己没看错——那 epsilon 应该增大（比如从 0.05 变成 0.12），但 score 仍然是 0.75，不应该变成 0.75 × 0.6 = 0.45。

**Gemini 的错误**：在早期版本中，Gemini 把 `llm_confidence` 乘进了分数计算（`confidence_weight = llm_confidence`），这正是上述的类型混淆。GPT-5.4 对此的批评完全正确。Gemini 后来在最终轮次中接受了这一修正（"LLM 的犹豫只增加 Epsilon，不降低 Score"），双方在此达成了共识。

**具体的 epsilon 分层机制**：

| score_provenance | 默认 base_epsilon | 说明 |
|---|---|---|
| RULE_ONLY | 0.02 | 纯规则提取（如正则匹配到精确数字），几乎无噪声 |
| LLM_EXTRACTED_RULE_SCORED | 0.05 + noise_term | LLM 做了语义降维，noise_term 由 LLM 置信度决定 |
| DEFAULT_TIER | 0.10 + noise_term | 使用了默认阶梯值而非领域特定规则，额外不确定性 |

其中 `noise_term = MAX_EXTRACTION_NOISE × (1 - weighted_avg_confidence)`，采用 GPT-5.4 提出的**按贡献加权平均**（而非 Gemini 的 `min()` 方案，因为 `min()` 会让一条边角证据的低置信度污染整轴 epsilon）。

**可能需要修正的场景**：当 LLM 的 `llm_confidence` 本身不可靠（LLM 对自身置信度的校准很差）时，基于 confidence 计算 noise_term 就失去了意义。长期可能需要通过 held-out 验证集来校准 LLM 的 confidence。

**一句话总结**：告诉用户"分数是 0.75，但提取过程的误差约 ±0.12"，而不是偷偷把误差藏进分数里给一个看起来很精确的 0.45。

---

## 聚合函数裁定（附属于 I）

双方在最终轮次各自提出了聚合函数，但都有缺陷：

- **Gemini 的 MAX-SMT 变体**（`0.5 + MAX(supp) - MAX(refute)`）：GPT-5.4 正确指出，只取峰值会丢失累积证据质量。两条独立中强证据与一条强证据得分相同，这违反了"多源独立支持应提高稳定性"的审计需求。
- **GPT-5.4 的加权求和**：更合理，但没有充分处理证据饱和问题（无限堆叠弱证据不应无限提升分数）。

**裁定：采用加权求和 + 饱和函数的混合方案。**

```
raw_pro = Σ(tier_score_i) for all PRO atoms
raw_con = Σ(tier_score_i) for all CON atoms
score = clamp(sigmoid_normalized(raw_pro - raw_con), 0, 1)
```

其中 `sigmoid_normalized` 确保：
- 单条强证据可以拉到 0.75，但不到 0.9
- 多条独立中等证据可以累积超过单条强证据
- 存在饱和效应，避免证据堆叠无限推高分数
- 零证据时 score = 0.5（中性，而非 0）

具体的 sigmoid 参数应在 QuestionFrame 中可配置（默认 k=2, midpoint=0）。

---

# 第二部分：可实现性摘要

## 1. S2/S4/S5 节点的 axis_scores 产出协议

### 节点职责划分

| 节点 | 阶段 A（语义降维） | 阶段 B（规则折算） | 产出 |
|---|---|---|---|
| **S2（深度研究）** | LLM 阅读外部文档，提取 `EvidenceAtomCandidate[]` | 规则引擎根据 `axis_rulebook` 或默认阶梯值折算 | `AxisScoreEntry[]` + `EvidenceAtom[]` |
| **S4（对抗审查）** | LLM 审查 S2 产出的 atom，可新增 CON 极性 atom | 规则引擎重新聚合（含新增 CON atom） | 修正后的 `AxisScoreEntry[]` |
| **S5（广度扫描）** | LLM 扫描更广泛来源，补充 S2 遗漏的 atom | 规则引擎增量聚合 | 增量 `AxisScoreEntry[]` 更新 |

### axis_score 产出的具体流程

```
[自然语言文档]
     │
     ▼
 ┌─────────────────────────────┐
 │  阶段 A: LLM 语义降维       │
 │  输入: 文档 + QuestionFrame  │
 │  输出: EvidenceAtomCandidate[]│
 │  约束: 不得输出数值分数      │
 └─────────────┬───────────────┘
               │
               ▼
 ┌─────────────────────────────┐
 │  验证层: span_hash 校验      │
 │  ref 类型检查                │
 │  strength_tier ∈ 合法枚举    │
 │  输出: EvidenceAtom[]        │
 └─────────────┬───────────────┘
               │
               ▼
 ┌─────────────────────────────┐
 │  阶段 B: 规则引擎折算       │
 │  输入: EvidenceAtom[]        │
 │       + axis_rulebook        │
 │  输出: AxisScoreEntry[]      │
 └─────────────────────────────┘
```

### 输入/输出类型定义

```typescript
// ============ 基础类型 ============
type AxisId = string;
type ClaimId = string;
type EvidenceId = string;
type EpochId = string;

// ============ 证据引用（ADT） ============
type EvidenceRef =
  | {
      kind: "EXTERNAL_DOC";
      doc_id: string;
      span_hash: string;          // 引用片段的内容哈希
      offsets: [number, number];   // 原文偏移量
    }
  | {
      kind: "INTERNAL_CLAIM";
      claim_id: ClaimId;
      claim_epoch: EpochId;
      required_status: "VERIFIED" | "DEFENSIBLE";
    };

// ============ 强度等级（语义降维目标） ============
type StrengthTier =
  | "ANECDOTAL"           // 轶事/个人经验
  | "CORRELATIONAL"       // 相关性研究/定性调查
  | "CAUSAL_STATISTICAL"  // 因果统计/RCT/大样本
  | "AXIOMATIC";          // 公理/定义性真理

// ============ 分数来源标注 ============
type ScoreProvenance =
  | "RULE_ONLY"                   // 纯规则提取
  | "LLM_EXTRACTED_RULE_SCORED"   // LLM 提取 + 规则折算
  | "DEFAULT_TIER";               // 使用了默认阶梯值

// ============ 阶段 A 输出（LLM 产出） ============
interface EvidenceAtomCandidate {
  ref: EvidenceRef;
  target_claim_id: ClaimId;
  axis_id: AxisId;                // 一个 atom 只挂一个 axis
  polarity: "PRO" | "CON";
  strength_tier: StrengthTier;
  llm_confidence: number;         // ∈ [0, 1]，LLM 对自身提取准确度的置信度
  extractor: "LLM";
}

// ============ 验证后的 atom ============
interface EvidenceAtom extends EvidenceAtomCandidate {
  evidence_id: EvidenceId;         // 系统分配
  extractor: "RULE" | "LLM";
  validated: true;
}

// ============ 阶段 B 输出 ============
interface AxisScoreEntry {
  axis_id: AxisId;
  score: number;                   // ∈ [0, 1]
  epsilon: number;                 // 测量不确定性 ∈ [0, 1]
  provenance: ScoreProvenance;
  evidence_ids: EvidenceId[];      // 参与折算的所有 atom
  aggregation_detail: {
    raw_pro: number;
    raw_con: number;
    pro_count: number;
    con_count: number;
    sigmoid_k: number;
    sigmoid_midpoint: number;
  };
}

// ============ Layer 1 下发的规则书（可选） ============
interface AxisRulebook {
  tier_score: Record<StrengthTier, number>;    // 每个等级的基础贡献分
  tier_epsilon: Record<StrengthTier, number>;  // 每个等级的基础 epsilon
  sigmoid_k?: number;                          // 聚合饱和参数
  sigmoid_midpoint?: number;
}

// QuestionFrame 中的声明
interface QuestionFrame {
  // ... 其他字段 ...
  evaluation_axes: AxisId[];
  axis_rulebook?: Record<AxisId, AxisRulebook>;  // 可选，不提供则用默认值
}

// ============ 默认阶梯值（Layer 2 内置） ============
const DEFAULT_RULEBOOK: AxisRulebook = {
  tier_score: {
    ANECDOTAL: 0.15,
    CORRELATIONAL: 0.40,
    CAUSAL_STATISTICAL: 0.75,
    AXIOMATIC: 0.95,
  },
  tier_epsilon: {
    ANECDOTAL: 0.12,
    CORRELATIONAL: 0.08,
    CAUSAL_STATISTICAL: 0.04,
    AXIOMATIC: 0.01,
  },
  sigmoid_k: 2,
  sigmoid_midpoint: 0,
};
```

---

## 2. EvidenceChain 的最终类型定义

```typescript
interface EvidenceChain {
  claim_id: ClaimId;
  epoch_id: EpochId;
  atoms: EvidenceAtom[];           // 所有支撑/反驳此 claim 的证据
  axis_scores: AxisScoreEntry[];   // 按 axis 聚合后的分数
  
  // 完整性保证
  integrity: {
    // 所有 atom.target_claim_id 必须 === this.claim_id
    claim_alignment_verified: boolean;
    
    // 所有 INTERNAL_CLAIM 类型的 ref 必须指向状态 ∈ required_status 的 claim
    dependency_status_verified: boolean;
    
    // 所有 axis_scores[i].evidence_ids 必须是 atoms[].evidence_id 的子集
    score_evidence_alignment_verified: boolean;
    
    // 不存在循环引用（claim A 依赖 claim B 依赖 claim A）
    acyclicity_verified: boolean;
  };
}

// ============ 完整性校验函数签名 ============
function validateEvidenceChain(
  chain: EvidenceChain,
  claimGraph: Map<ClaimId, { status: string; epoch: EpochId }>
): {
  valid: boolean;
  violations: Array<{
    kind: "DANGLING_REF" | "STATUS_MISMATCH" | "ORPHAN_EVIDENCE" | "CYCLE_DETECTED";
    detail: string;
  }>;
};
```

**claim_id 引用的完整性保证机制**：

1. **构建时校验**：当 EvidenceAtom 的 ref 为 `INTERNAL_CLAIM` 时，系统必须在 claim graph 中查找该 claim_id，验证 (a) 存在性，(b) epoch 匹配性，(c) 状态满足 `required_status`。
2. **失效传播**：当被引用的 claim 状态降级为 `SUSPENDED` 或 `REFUTED` 时，所有引用它的 atom 被标记为 `invalidated`，触发所在 axis 的重新聚合。
3. **无环约束**：通过拓扑排序在 claim graph 构建阶段检测，若检测到环则拒绝写入并报告 `CYCLE_DETECTED`。

**多 axis 关联的处理方式**：
同一文档片段（相同 `span_hash`）可以产生多个 EvidenceAtom，每个挂不同 axis_id。这些 atom 共享 `ref` 但拥有独立的 `evidence_id`、`polarity`、`strength_tier`。聚合时完全独立，不存在跨 axis 权重分配。

---

## 3. 跨 epoch 一致性约束的最终规范

### 触发审核的阈值 τ

```typescript
// τ 的定义
function computeDriftThreshold(
  currentScore: AxisScoreEntry,
  previousScore: AxisScoreEntry
): number {
  // 取两个 epoch 中较大的 epsilon（保守估计）
  const epsilon = Math.max(currentScore.epsilon, previousScore.epsilon);
  // τ = 2ε，但设置绝对下限
  const TAU_MIN = 0.15;  // 防止高精度证据的阈值过于严苛
  return Math.max(2 * epsilon, TAU_MIN);
}
```

**τ 从哪里推导**：直接来自当前 axis 的 epsilon，epsilon 又来自证据质量和提取置信度。因此 τ 是自适应的——证据越硬，容忍的波动越小。

**谁来声明**：τ 由 Layer 2 的一致性检查模块自动计算，不需要外部声明。QuestionFrame 可以通过 `tau_override` 覆盖（仅用于特殊场景）。

### 触发后的状态变更

```typescript
interface DriftReport {
  axis_id: AxisId;
  claim_id: ClaimId;
  epoch_current: EpochId;
  epoch_previous: EpochId;
  score_current: number;
  score_previous: number;
  delta: number;              // |score_current - score_previous|
  tau: number;                // 阈值
  triggered: boolean;         // delta > tau
  
  // 差异分解（关键！不是简单的 flag）
  decomposition: {
    atoms_added: EvidenceId[];      // 新增 atom
    atoms_removed: EvidenceId[];    // 被删除的 atom（因依赖失效等）
    atoms_unchanged: EvidenceId[];  // 未变化的 atom
    
    // 对 unchanged atoms 重新折算是否一致
    unchanged_rescore_consistent: boolean;
    
    // 结论
    drift_cause: 
      | "NEW_EVIDENCE"           // 差异来自新增/移除证据
      | "EXTRACTION_INSTABILITY" // 相同文档但 LLM 提取结果不同
      | "RULEBOOK_CHANGE"        // axis_rulebook 变更
      | "UNKNOWN";               // 无法归因，需要人工审查
  };
}
```

**drift_flag 的下游影响**：

1. `drift_cause === "NEW_EVIDENCE"`：正常，不触发任何特殊处理，仅记录日志。
2. `drift_cause === "EXTRACTION_INSTABILITY"`：标记该 axis 的 `provenance` 为 `UNSTABLE`，PA 节点在 delta 计算中将 epsilon 翻倍。
3. `drift_cause === "RULEBOOK_CHANGE"`：不应在 epoch 间发生（rulebook 应在 QuestionFrame 初始化时锁定），若发生则为系统错误。
4. `drift_cause === "UNKNOWN"`：暂停该 axis 的 score 更新，等待人工审查。

### 相邻 epoch 的比对机制

按 `claim_id + axis_id` 作为联合键对齐：

```typescript
function compareEpochs(
  prev: EvidenceChain,
  curr: EvidenceChain
): DriftReport[] {
  // 对每个 axis_id，找到 prev 和 curr 中对应的 AxisScoreEntry
  // 按 evidence_id 做集合差运算：
  //   added = curr.atoms - prev.atoms (by evidence_id)
  //   removed = prev.atoms - curr.atoms
  //   unchanged = curr.atoms ∩ prev.atoms
  // 对 unchanged 子集重新运行规则引擎，检查是否与 prev 的折算结果一致
  // 生成 DriftReport
}
```

---

## 4. 认识论诚实性标注协议

### axis_score 的来源类型字段

已在 `ScoreProvenance` 中定义：

```typescript
type ScoreProvenance =
  | "RULE_ONLY"                   // 纯规则提取（如正则匹配到 p 值）
  | "LLM_EXTRACTED_RULE_SCORED"   // LLM 语义降维 + 规则折算（标准路径）
  | "DEFAULT_TIER";               // 使用了 Layer 2 默认阶梯值（非领域特定）
```

### epsilon 分层机制

```typescript
function computeEpsilon(
  atoms: EvidenceAtom[],
  rulebook: AxisRulebook,
  provenance: ScoreProvenance
): number {
  // 1. 基础 epsilon：所有参与 atom 的 tier_epsilon 的加权平均
  const weighted_base = atoms.reduce((sum, atom) => {
    const tier_eps = rulebook.tier_epsilon[atom.strength_tier];
    const contribution = rulebook.tier_score[atom.strength_tier];
    return sum + tier_eps * contribution;
  }, 0) / atoms.reduce((sum, atom) => {
    return sum + rulebook.tier_score[atom.strength_tier];
  }, 0);

  // 2. 提取噪声项：按贡献加权的 LLM 置信度
  const MAX_EXTRACTION_NOISE = 0.15;
  const llm_atoms = atoms.filter(a => a.extractor === "LLM");
  let noise_term = 0;
  if (llm_atoms.length > 0) {
    const weighted_conf = llm_atoms.reduce((sum, atom) => {
      const w = rulebook.tier_score[atom.strength_tier];
      return sum + w * atom.llm_confidence;
    }, 0) / llm_atoms.reduce((sum, atom) => {
      return sum + rulebook.tier_score[atom.strength_tier];
    }, 0);
    noise_term = MAX_EXTRACTION_NOISE * (1 - weighted_conf);
  }

  // 3. 来源附加项
  const provenance_penalty: Record<ScoreProvenance, number> = {
    "RULE_ONLY": 0,
    "LLM_EXTRACTED_RULE_SCORED": 0,
    "DEFAULT_TIER": 0.05,  // 使用默认规则的额外不确定性
  };

  return weighted_base + noise_term + provenance_penalty[provenance];
}
```

### PA 节点如何消费 score_provenance

```typescript
// PA 节点的 delta 计算
function computeDelta(
  axisScores: AxisScoreEntry[],
  weights: Record<AxisId, number>,
  alpha: number
): { delta: number; adjusted_epsilon: number } {
  let weighted_score_sum = 0;
  let weighted_epsilon_sum = 0;

  for (const entry of axisScores) {
    const w = weights[entry.axis_id] ?? 0;
    weighted_score_sum += w * entry.score;

    // 根据 provenance 调整 epsilon 的消费方式
    let effective_epsilon = entry.epsilon;
    if (entry.provenance === "DEFAULT_TIER") {
      effective_epsilon *= 1.5;  // 对默认规则产出的分数增加 50% 不确定性
    }
    weighted_epsilon_sum += w * effective_epsilon;
  }

  return {
    delta: alpha * weighted_score_sum,
    adjusted_epsilon: alpha * weighted_epsilon_sum,
  };
}
```

---

## 5. 完整运行 Trace

### 输入

```
QuestionFrame:
  question: "城市是否应该投资自动驾驶公交系统？"
  evaluation_axes: ["traffic_safety", "cost_efficiency", "public_acceptance"]
  axis_rulebook: {
    traffic_safety: {
      tier_score: { ANECDOTAL: 0.10, CORRELATIONAL: 0.35, CAUSAL_STATISTICAL: 0.80, AXIOMATIC: 0.95 },
      tier_epsilon: { ANECDOTAL: 0.15, CORRELATIONAL: 0.10, CAUSAL_STATISTICAL: 0.03, AXIOMATIC: 0.01 }
    }
    // cost_efficiency 和 public_acceptance 未提供 → 使用 DEFAULT_RULEBOOK
  }

TestableClaim (claim_id = "C-042"):
  text: "自动驾驶公交系统在试点城市显著降低了交通事故率"
  epoch: "E-003"
```

### S2 节点处理

**阶段 A：LLM 语义降维**

LLM 阅读以下文档：
- Doc-A: "深圳 2024 年试点报告：自动驾驶公交线路事故率同比下降 47%（n=1,200 运营日, p<0.001）"
- Doc-B: "Reddit 帖子：我坐过自动驾驶公交，感觉比人类司机稳多了"
- Doc-C: "《交通研究》期刊：自动驾驶系统在恶劣天气下事故率反而上升 12%（n=340, p=0.03）"

LLM 产出 `EvidenceAtomCandidate[]`：

```
Candidate-1:
  ref: { kind: "EXTERNAL_DOC", doc_id: "Doc-A", span_hash: "a3f2...", offsets: [0, 89] }
  target_claim_id: "C-042"
  axis_id: "traffic_safety"
  polarity: "PRO"
  strength_tier: "CAUSAL_STATISTICAL"
  llm_confidence: 0.95
  extractor: "LLM"

Candidate-2:
  ref: { kind: "EXTERNAL_DOC", doc_id: "Doc-B", span_hash: "b7e1...", offsets: [0, 52] }
  target_claim_id: "C-042"
  axis_id: "traffic_safety"
  polarity: "PRO"
  strength_tier: "ANECDOTAL"
  llm_confidence: 0.88
  extractor: "LLM"

Candidate-3:
  ref: { kind: "EXTERNAL_DOC", doc_id: "Doc-C", span_hash: "c9d4...", offsets: [0, 78] }
  target_claim_id: "C-042"
  axis_id: "traffic_safety"
  polarity: "CON"
  strength_tier: "CAUSAL_STATISTICAL"
  llm_confidence: 0.91
  extractor: "LLM"
```

**验证层**：校验 span_hash 存在、strength_tier ∈ 合法枚举、axis_id ∈ QuestionFrame.evaluation_axes → 全部通过，分配 evidence_id：

```
Atom-1 (evidence_id: "EV-101"): PRO, CAUSAL_STATISTICAL, confidence=0.95
Atom-2 (evidence_id: "EV-102"): PRO, ANECDOTAL, confidence=0.88
Atom-3 (evidence_id: "EV-103"): CON, CAUSAL_STATISTICAL, confidence=0.91
```

### S4 节点处理（对抗审查）

S4 审查 S2 的 atom，未发现明显的提取错误或遗漏的反面证据。但注意到 Doc-C 的 CON 证据是在特定条件（恶劣天气）下的，可能影响其对通用 `traffic_safety` 轴的映射。S4 保持 atom 不变但在审查日志中记录此观察。

### 规则引擎折算（阶段 B）

使用 QuestionFrame 提供的 `traffic_safety` 专用 rulebook：

```
PRO atoms:
  Atom-1: CAUSAL_STATISTICAL → tier_score = 0.80
  Atom-2: ANECDOTAL → tier_score = 0.10
  raw_pro = 0.80 + 0.10 = 0.90

CON atoms:
  Atom-3: CAUSAL_STATISTICAL → tier_score = 0.80
  raw_con = 0.80

net = raw_pro - raw_con = 0.90 - 0.80 = 0.10
score = sigmoid_normalized(0.10, k=2, midpoint=0) ≈ 0.55

epsilon 计算:
  base_epsilon:
    加权平均 = (0.80×0.03 + 0.10×0.15 + 0.80×0.03) / (0.80+0.10+0.80)
             = (0.024 + 0.015 + 0.024) / 1.70
             = 0.037
  noise_term:
    weighted_conf = (0.80×0.95 + 0.10×0.88 + 0.80×0.91) / (0.80+0.10+0.80)
                  = (0.76 + 0.088 + 0.728) / 1.70
                  = 0.928
    noise = 0.15 × (1 - 0.928) = 0.011
  provenance_penalty: 0 (使用了领域特定规则)
  
  total_epsilon = 0.037 + 0.011 + 0 = 0.048
```

**AxisScoreEntry 输出**：

```
{
  axis_id: "traffic_safety",
  score: 0.55,
  epsilon: 0.048,
  provenance: "LLM_EXTRACTED_RULE_SCORED",
  evidence_ids: ["EV-101", "EV-102", "EV-103"],
  aggregation_detail: {
    raw_pro: 0.90,
    raw_con: 0.80,
    pro_count: 2,
    con_count: 1,
    sigmoid_k: 2,
    sigmoid_midpoint: 0
  }
}
```

**解读**：分数 0.55（略高于中性），说明正面证据稍微占优（多了一条 ANECDOTAL），但核心统计证据正反各一条，几乎对冲。epsilon 很小（0.048），因为大部分证据都是高质量统计数据，提取置信度也高。

### 跨 epoch 一致性检查

**Epoch E-002 的记录**（假设已存在）：

```
Epoch E-002, claim C-042, traffic_safety:
  score: 0.72, epsilon: 0.06
  evidence_ids: ["EV-081", "EV-082"]  (两条 PRO，一条 CAUSAL_STATISTICAL + 一条 CORRELATIONAL)
```

**比对**：

```
τ = max(2 × 0.048, 2 × 0.06, 0.15) = max(0.096, 0.12, 0.15) = 0.15
|Δ| = |0.55 - 0.72| = 0.17
0.17 > 0.15 → 触发审核！
```

**差异分解**：

```
atoms_added: ["EV-103"] (新增的 CON 证据，Doc-C)
atoms_removed: ["EV-081"] (旧 epoch 的某条证据在新文档集中未被重新提取)
atoms_unchanged: [] (没有完全相同的 atom 跨 epoch 存活)

→ 但 EV-082 (CORRELATIONAL PRO) 与 EV-102 (ANECDOTAL PRO) 来自不同文档
→ unchanged_rescore_consistent: N/A (无 unchanged atoms)
→ drift_cause: "NEW_EVIDENCE"
```

**结论**：差异完全来自新证据（一条高质量反面研究被发现），不是提取不稳定。`drift_cause = "NEW_EVIDENCE"`，无需特殊处理，正常记录。

---

## 6. 实现难度最高的 2 个子模块及其风险

### 子模块 1：LLM 语义降维的一致性保证

**难度来源**：同一段文本，LLM 在不同次调用中可能输出不同的 `strength_tier` 和 `polarity`。例如"事故率下降，但主要因为运行里程也减少了"——这到底是 PRO 还是 CON？LLM 可能今天说 PRO 明天说 MIXED。

**风险**：
- 这直接导致跨 epoch 一致性检查中出现 `EXTRACTION_INSTABILITY`
- 如果 temperature > 0，每次提取结果不同，规则引擎输入不稳定
- 更深层的风险：LLM 的 `llm_confidence` 