# v3 认知引擎：Layer 2 的 axis_scores 产出机制 辩论日志

> 2026-03-09T19:11:27.222157

---


### [1] GPT-5.4

*2026-03-09T18:54:34.887908*

我选 **问题 I：axis_scores 产出方式**。  
理由很简单：J/K/L 都依赖 I。你如果先接受“分数可以先出来，后面再补 provenance / drift / honesty”，那后面全是补洞。分数生成协议必须先钉死输入输出类型，否则 evidence_chain 只是陪衬，跨 epoch 一致性也没有比较基准。

我的立场是：

> **S2/S4/S5 一律采用“两阶段协议”，但禁止 LLM 直接输出最终 axis_score。**  
> LLM 只能产出 **可审计的候选结构化证据单元**；最终数值必须由 **规则引擎折算**。  
> 无法规则化量化的证据，允许进入链路，但只能作为 **bounded qualitative contribution**，其上限、epsilon、epoch 漂移处理都必须硬编码。

这不是原则，是接口。

---

## 1) 核心主张：类型定义 + 处理流程

### 类型与主流程

```ts
type AxisId = string;
type ClaimId = string;
type EvidenceId = string;
type EpochId = string;

type ScoreSource = "RULE_ONLY" | "LLM_EXTRACTED_RULE_SCORED";
type EvidenceKind = "QUANT_STAT" | "QUAL_USER_REPORT" | "EXPERT_OPINION" | "OPERATIONAL_METRIC";
type MappingBasis = "LEXICAL_RULE" | "AXIS_SCHEMA_RULE" | "LLM_TAG_PROPOSAL";

interface EvidenceAtom {
  evidence_id: EvidenceId;
  claim_id: ClaimId;
  doc_id: string;
  span_hash: string;              // content hash of exact cited fragment
  offsets?: [number, number];
  kind: EvidenceKind;
  extracted_by: "RULE" | "LLM";
  payload: {
    direction: "PRO" | "CON" | "MIXED";
    effect_size?: number;         // normalized if available
    sample_size?: number;
    p_value?: number;
    metric_name?: string;
    qualitative_strength?: "WEAK" | "MEDIUM" | "STRONG";
  };
  axis_links: Array<{ axis_id: AxisId; basis: MappingBasis; weight: number }>; // sum <= 1
}

interface AxisScoreEntry {
  axis_id: AxisId;
  score: number;                  // [0,1]
  source: ScoreSource;
  epsilon: number;                // derived, not guessed
  evidence_ids: EvidenceId[];
}

function computeAxisScores(claimId: ClaimId, atoms: EvidenceAtom[]): AxisScoreEntry[] {
  const byAxis = groupByAxis(atoms.filter(validateAtom));
  return Object.entries(byAxis).map(([axisId, xs]) => {
    const contribs = xs.map(atomToContribution);          // each -> signed, bounded, auditable
    const agg = boundedWeightedAggregate(contribs);       // deterministic
    return {
      axis_id: axisId,
      score: clamp01(0.5 + agg.net / 2),                  // neutral baseline = 0.5
      source: xs.some(x => x.extracted_by === "LLM") ? "LLM_EXTRACTED_RULE_SCORED" : "RULE_ONLY",
      epsilon: deriveAxisEpsilon(contribs),
      evidence_ids: xs.map(x => x.evidence_id),
    };
  });
}
```

### 关键约束

1. **LLM 不得输出 `score:number`**
2. LLM 只能输出 `EvidenceAtom` 候选；必须通过 `validateAtom()`：
   - `claim_id` 存在
   - `doc_id + span_hash` 存在且可回放
   - `axis_links[].axis_id` 必须来自 `QuestionFrame.evaluation_axes`
   - `axis_links.weight` 总和 `<= 1`
3. `atomToContribution()` 是规则表，不是自由发挥
4. S2/S4/S5 协议统一：都只能新增/撤销/更新 `EvidenceAtom`，不得直接写 axis_score
5. 最终 `VerifiedClaim.axis_scores` 只由 `computeAxisScores()` 在收敛阶段生成

---

## 2) 规则折算细节与边界行为

你要求边界场景，我直接给行为。

---

### 边界场景 A  
**自然语言证据明确涉及某个 axis，但强度无法用规则精确量化**

例子：
- “大量用户反映满意度提升”
- 对比 “满意度提升 23%，N=1200，p<0.01”

我的处理不是把前者假装量化，而是把它放进**有上限的定性桶**。

#### 折算规则

```ts
function atomToContribution(a: EvidenceAtom): { signed: number; epsilon: number } {
  if (a.kind === "QUANT_STAT") {
    const mag = quantMagnitude(a.payload.effect_size, a.payload.sample_size, a.payload.p_value);
    return { signed: sign(a.payload.direction) * mag, epsilon: quantEpsilon(a.payload.sample_size, a.payload.p_value) };
  }
  if (a.kind === "QUAL_USER_REPORT") {
    const cap = { WEAK: 0.08, MEDIUM: 0.15, STRONG: 0.22 }[a.payload.qualitative_strength ?? "WEAK"];
    return { signed: sign(a.payload.direction) * cap, epsilon: 0.18 };
  }
  if (a.kind === "EXPERT_OPINION") {
    return { signed: sign(a.payload.direction) * 0.10, epsilon: 0.20 };
  }
  return { signed: sign(a.payload.direction) * 0.12, epsilon: 0.16 };
}
```

#### 行为结果

- “满意度提升 23%，N=1200，p<0.01”
  - `kind=QUANT_STAT`
  - 贡献可能是 `+0.35 ~ +0.55` 量级，epsilon 较低，例如 `0.04 ~ 0.08`
- “大量用户反映满意度提升”
  - `kind=QUAL_USER_REPORT`
  - 贡献被**硬上限**卡住，例如最多 `+0.22`
  - epsilon 固定高，比如 `0.18`

这就是认识论诚实：  
**模糊证据可以入账，但不能和有统计支撑的证据拿同一把尺子。**

如果你问“LLM 怎么知道 qualitative_strength 是 MEDIUM 还是 STRONG？”  
答案：它只能提案，最终必须有可回放触发条件，例如：
- `STRONG` 需要文段中出现“多数/大量/广泛/普遍” + 至少一个群体范围词
- 否则降到 `MEDIUM/WEAK`
- 规则不满足就 reject atom

也就是说，LLM 提取，规则验收。

---

### 边界场景 B  
**同一条证据可能同时关联多个 axis**

例子：
“采用微服务后部署频率提升 3 倍，运营成本降低 15%”

我的方案要求**在 atom 层拆分，不允许一个自然语言片段以一个未拆分黑盒贡献多个轴**。

#### 处理方式

同一 `doc_id/span_hash` 可产生多个 `EvidenceAtom`，每个 atom 对应一个可计算 observation：

```ts
// atom 1
{
  kind: "OPERATIONAL_METRIC",
  payload: { metric_name: "deployment_frequency", effect_size: +3.0, direction: "PRO" },
  axis_links: [{ axis_id: "delivery_speed", basis: "AXIS_SCHEMA_RULE", weight: 1.0 }]
}

// atom 2
{
  kind: "QUANT_STAT",
  payload: { metric_name: "operating_cost", effect_size: -0.15, direction: "PRO" }, 
  axis_links: [{ axis_id: "operating_cost", basis: "AXIS_SCHEMA_RULE", weight: 1.0 }]
}
```

如果确实存在一个 observation 同时对多个轴有效，比如“MTTR 降低 40%”同时影响 reliability 和 ops_efficiency，那么：

- 允许一个 atom 有多个 `axis_links`
- 但要求每个 link 有显式 `weight`
- 同一 atom 的 `axis_links.weight` 总和 `<= 1`

这样做的目的不是数学优雅，是防止**重复记分**。  
否则一个强证据会被每个相关轴全额复用，最后在 Layer 1 聚合时变成隐形多重计数。

#### 规则

- **优先拆分成多 atom**
- 无法拆分才允许单 atom 多 axis
- 多 axis 时必须有固定映射表，不允许 LLM 自己发明权重

---

## 3) 节点职责划分

你要求节点职责，我给明确边界。

### S2
- 输入：claim + corpus
- 输出：`EvidenceAtom[]` 候选
- 责任：
  - 找直接证据
  - 提取基础量化字段
  - 首次 axis mapping 提案
- 禁止：
  - 写最终 `axis_score`

### S4
- 输入：已有 atom + 缺口
- 输出：补充/修订 `EvidenceAtom[]`
- 责任：
  - 查找更强量化证据
  - 用高质量原文替换弱定性证据
  - 触发 atom 撤销（旧 span 不可回放/冲突）

### S5
- 输入：claim + 未覆盖轴/旁证方向
- 输出：新增跨轴 `EvidenceAtom[]`
- 责任：
  - 发现原先未覆盖 axis 的相关 observation
  - 但必须显式声明 mapping basis

### ScoreCompiler（建议独立于 S2/S4/S5）
- 输入：validated `EvidenceAtom[]`
- 输出：`AxisScoreEntry[]`
- 责任：
  - 唯一合法的分数生成器
  - 执行规则折算、epsilon 推导、证据链绑定

这比让 S2/S4/S5 各自算分安全得多。否则你会得到 epoch 间实现差异，不是认知变化，是节点行为漂移。

---

## 4) 已知最弱点及缓解

### 最弱点
**LLM 提取阶段仍然是污染源。**

具体说，不是分数不稳定，而是：
- `kind` 可能抽错
- `effect_size` 可能读错
- `axis_links` 可能挂错轴
- 同一句话可能被抽成不同 atom 粒度

这会把噪声前移到结构层。

### 缓解方案

#### 缓解 1：严格验收器
`validateAtom()` 必须是硬规则，不是“看起来合理”。

必须拒绝：
- 无 `span_hash`
- effect_size 有值但原文 span 中无数字或单位模式
- `axis_id` 不在声明集合中
- 多 axis 且权重和 > 1
- `claim_id` 不存在/未通过 S2 基础验证

#### 缓解 2：原文回放校验
量化字段采用 `extract-then-verify`：
- LLM 提取数字
- regex/parser 从原 span 回放
- 不一致则降级为 `QUAL_USER_REPORT` 或 reject

#### 缓解 3：epoch 锚定
同一 `doc_id + span_hash + metric_name` 生成稳定 `evidence_id`。  
这样相邻 epoch 比较的是“同一个 atom 是否还在”，不是“LLM 这轮怎么概括的”。

#### 缓解 4：保守缺省
当提取不确定时：
- 不允许猜精确 effect_size
- 直接降级到 bounded qualitative bucket
- 高 epsilon，低上限

### 可推翻条件
如果线上数据表明：
1. 同一 `doc_id + span_hash` 在相邻 epoch 的 atom 分类变更率 > 15%
2. 人工抽检显示 `axis_links` 错挂率 > 10%
3. rule-scored 结果与人工审计排序的一致性长期低于预设阈值（例如 Kendall tau < 0.5）

那说明两阶段接口设计失败，需要重做 extraction schema 或 axis ontology。

---

## 5) 对对手可能方案的预攻击

我先打最常见的对手方案：**“LLM 直接按 axis 打分，再附 evidence_chain 解释。”**

这是类型错误，不是风格差异。

### 失败点 1：evidence_chain 变成事后解释，不是生成输入
如果对方接口是：

```ts
{ axis_id: "delivery_speed", score: 0.82, evidence_chain: [...] }
```

那 `score` 是先出来的，`evidence_chain` 是解释文本。  
这意味着链条不是生成函数的输入，只是注释。审计时你无法回答：

- 哪个 evidence 对分数贡献多少？
- 去掉某条证据，分数变多少？
- 为什么这次是 0.82 不是 0.67？

没有可减性（subtractive auditability），就不是工程协议。

### 失败点 2：跨 epoch 漂移无法区分“证据变化”还是“模型心情变化”
具体失败场景：

- epoch N：同一批证据，LLM 给 `delivery_speed=0.45`
- epoch N+1：没新增证据，prompt 细节变化，给到 `0.82`

对手只能说“模型重新判断了”。  
这句话在系统里等于：**没有状态转移语义**。

而我的方案至少能比较：
- atom 集合是否变化
- 某 atom 的 `kind/effect_size/axis_link` 是否变化
- 规则参数是否变化

漂移来源是可定位的。

### 失败点 3：epsilon 无法从过程推导
你在 L 问题里已经点名这个坑了。  
LLM 直接打分方案没法严肃定义：

```ts
epsilon(delivery_speed, claim_42, epoch_7) = ?
```

除非它又回退到“按来源类型给固定 epsilon”。  
但固定 epsilon 与具体证据强弱无关，那 epsilon 就失真，PA 的 `has_ranking_change()` 也被污染。

### 我对这种方案的结论
**它最多能做原型，不能做规范。**

---

## 6) 顺带给 J/K/L 的最小兼容接口

虽然本轮我选 I，但我不给悬空引用。

### 对 J：evidence_chain 最小格式
我认为最小可用格式至少是：

```ts
interface EvidenceRef {
  evidence_id: string;
  claim_id: string;         // must reference existing verified/intermediate claim context
  doc_id: string;
  span_hash: string;
  offsets?: [number, number];
  axis_id: string;
}
```

没有 `span_hash` 的链条不可审计。  
没有 `axis_id` 的链条无法解释“为何关联到这个轴”。

### 对 K：跨 epoch 一致性约束
硬规则，不是建议：

```ts
drift(axis, claim) = |score_t - score_t-1|
trigger if drift > max(0.15, 2 * epsilon_combined)
```

但更重要的是，先比较 atom set：
- atom 集合未变而 score 大跳变 => **协议错误**
- atom 集合新增高质量量化证据 => 允许跳变，但必须记录 `cause = NEW_HIGH_GRADE_EVIDENCE`

### 对 L：认识论诚实性标注
必须 axis 级，不是 claim 级：

```ts
interface AxisScoreEntry {
  axis_id: string;
  score: number;
  source: "RULE_ONLY" | "LLM_EXTRACTED_RULE_SCORED";
  epsilon: number;
}
```

PA 消费的不是裸分数，而是 `(score, source, epsilon)`。

---

## 7) 结论

我的完整立场：

1. **I 选两阶段协议（LLM 提取，规则打分），且禁止 LLM 直接输出最终 axis_score**
2. **S2/S4/S5 统一协议：只产出/修订 `EvidenceAtom`，不写分**
3. **最终分数由独立 ScoreCompiler 基于规则引擎生成**
4. **模糊证据允许入账，但必须低上限、高 epsilon**
5. **多 axis 证据必须 atom 化或显式加权，防止重复记分**
6. **所有分数必须伴随 axis 级 provenance 和 epsilon**

可推翻条件我已经给了：如果 atom 提取稳定性、挂轴准确率、人工审计一致性达不到线，这套协议失败，需要重构 schema。  
但即便失败，它也是**可测失败**。这比“LLM 综合判断”强太多——后者连失败都只能靠感觉。

---


### [2] Gemini-3.1-Pro

*2026-03-09T18:54:34.887933*

我选择合并解决 **问题 I（axis_scores 产出方式）** 和 **问题 J（evidence_chain 格式规范）**，因为这两者在类型系统上是同一个硬币的两面：没有严格的证据链格式，就无法支撑任何非 LLM 黑盒的评分机制。

### 对「完全 LLM 化」与「完全规则化」的精确攻击

主张「LLM 直接打分」（选项 I-A）的方案犯了致命的**认识论类型错误**。如果 S2 节点直接输出 `axis_scores: { delivery_speed: 0.8 }`，请问消费侧 PA 节点在计算 `delta = alpha * Σ(w_a * epsilon_a)` 时，这个 0.8 的 `epsilon`（测量误差）是多少？LLM 的幻觉和注意力偏移根本不服从高斯分布，你无法为一个黑盒浮点数推导误差边界。这会导致整个 Layer 1 的终止状态机建立在流沙之上。

主张「完全规则引擎」（选项 I-B）的方案则活在真空中。我追问：**规则从哪里来？谁来维护？** 自然语言中「大量用户反映满意度提升」和「满意度提升 23%，p<0.01」，你要写多少个正则表达式才能把它们准确映射到 [0,1] 的区间？这种方案必然在处理第一批真实互联网语料时崩溃。

---

### 我的核心主张：两阶段协议与结构化证据链

S2/S4/S5 必须采用**「两阶段协议」**：LLM 负责语义降维（自然语言 -> 离散类型枚举），规则引擎负责数值折算（离散类型 -> 浮点数）。

这要求 `evidence_chain` 必须作为第一等公民存在，其最小格式正是两阶段之间的强类型契约。

```typescript
// 1. 问题 J：evidence_chain 的最小格式规范（由 LLM 在第一阶段产出）
interface EvidenceNode {
  claim_id: string;           // 强约束：必须引用外部已归档的文档或已验证的内部 Claim
  doc_fragment: string;       // 强约束：原文片段，保证可审计性
  axis_mapping: Array<{       // 解决多轴关联问题
    axis_id: AxisId;
    strength_tier: "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL"; // 语义降维
    confidence: number;       // LLM 提取此映射的置信度 ∈ [0,1]
  }>;
}

// 2. 问题 I：S2/S4/S5 的 axis_scores 规则引擎折算（第二阶段）
// 规则来源：必须在 QuestionFrame 中预声明，否则使用默认阶梯值
type AxisScoringRule = Record<"ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL", number>;

function compute_axis_scores(
  evidence_chain: EvidenceNode[],
  rules: Record<AxisId, AxisScoringRule>
): Partial<Record<AxisId, number>> {
  const scores: Partial<Record<AxisId, number>> = {};
  
  for (const ev of evidence_chain) {
    for (const mapping of ev.axis_mapping) {
      const base_score = rules[mapping.axis_id][mapping.strength_tier];
      // 结合 LLM 置信度折算。采用 MAX-SMT 逻辑：取支撑该轴的最强证据
      const discounted = base_score * mapping.confidence;
      scores[mapping.axis_id] = Math.max(scores[mapping.axis_id] ?? 0, discounted);
    }
  }
  return scores;
}
```

### 边界场景的行为表现

1. **模糊证据 vs 精确量化证据**：
   当遇到「大量用户反映满意度提升」时，第一阶段 LLM 会将其识别为 `strength_tier: "ANECDOTAL"`。当遇到「满意度提升 23%，N=1200，p<0.01」时，LLM 识别为 `"CAUSAL_STATISTICAL"`。
   第二阶段规则引擎严格按 `QuestionFrame` 预设折算（例如 ANECDOTAL=0.3，CAUSAL_STATISTICAL=0.9）。**无需为每个数值写正则，LLM 承担了它最擅长的分类工作，规则引擎守住了数值的可重复性。**

2. **同一证据多轴关联**：
   「采用微服务后部署频率提升 3 倍，运营成本降低 15%」。第一阶段 LLM 提取出包含两个元素的 `axis_mapping` 数组：一个指向 `delivery_speed`（CAUSAL_STATISTICAL），一个指向 `operating_cost`（CAUSAL_STATISTICAL）。`compute_axis_scores` 函数会正确地将这两个分数分别计算并合并到最终的 `axis_scores` 字典中。

---

### 跨 epoch 一致性与依赖降级（回应我的不确定点）

关于我最不确定的两个点，在此提出确定的机制设计：

1. **依赖降级机制**：当 `evidence_chain` 中的某个 `claim_id` 在下一个 epoch 被标记为 `SuspendedClaim` 时，**不需要 LLM 重新打分**。系统只需将该 `EvidenceNode` 从数组中剔除，重新运行上述 `compute_axis_scores` 函数。如果它是支撑该轴的唯一高分证据，`axis_score` 会自动、精确地降级。这正是两阶段协议相比纯 LLM 黑盒的巨大优势——**依赖图是可计算的**。

2. **跨 epoch 一致性约束（问题 K）**：
   阈值 $\tau$ 不能是魔法数字，必须从 `EvaluationAxis.epsilon` 推导（例如设定 $\tau = 2 \times \epsilon$）。
   如果同一 claim 相邻 epoch 的 `axis_scores` 变化超过 $\tau$，触发 `drift_flag`。
   **处理机制**：消费侧（PA 节点）在看到 `drift_flag` 时，将该 claim 对总 delta 的 `epsilon` 贡献上浮（例如乘以 1.5）。这在数学上等价于告诉 Layer 1：“这个节点的评分处于震荡期，你要更难才能触发 `has_ranking_change() == False` 的终止条件”。

---

### 已知最弱点及其缓解方案

**最弱点**：将自然语言降维到 `strength_tier` 的枚举类型，仍然依赖 LLM。如果 LLM 在 epoch N 判定为 `CAUSAL_STATISTICAL`，在 epoch N+1 判定为 `CORRELATIONAL`，依然会引起分数跳变。

**缓解方案**：强制要求第一阶段的 LLM 必须提取 `doc_fragment`（精确原文）。这使得 `strength_tier` 的分类具备了**可证伪性（falsifiability）**。如果系统检测到频繁的漂移，审计人员或外部监督模型只需比对 `doc_fragment` 和 `strength_tier`，就能迅速定位并微调 Prompt，而不需要去猜测 0.8 这个数字是怎么来的。

### 可推翻条件（Falsification）

如果出现以下情况，我承认我的方案失败：
1. **表达力不足**：存在某种极其关键的自然语言证据，其强度无法被合理映射到 `ANECDOTAL | CORRELATIONAL | CAUSAL_STATISTICAL` 这类离散枚举中，导致规则引擎计算出的分数与人类专家直觉产生 >0.4 的系统性偏差。
2. **状态爆炸**：当一个复杂 claim 积累了超过 50 条 `EvidenceNode` 时，`Math.max` 的聚合逻辑导致分数永久锁定在最高值，使得后续的反证（反向证据）无法拉低分数。（注：这确实是一个潜在漏洞，可能需要引入正反证据相抵的 MAX-SMT 变体逻辑，期待对手对此进行攻击）。

---


### [3] 🔍 **质询** GPT-5.4 → Gemini-3.1-Pro

*2026-03-09T18:55:16.375697*

下面是我对 Gemini-3.1-Pro 第 1 轮发言的 3 个尖锐质疑，直接打它最薄弱的地方。

---

### 质疑 1：你的 `EvidenceNode.claim_id` 语义是悬空的，根本不满足可审计依赖图要求

你写的是：

```typescript
claim_id: string; // 强约束：必须引用外部已归档的文档或已验证的内部 Claim
```

这句话在类型上就是混乱的。

`claim_id` 到底指什么？

- 指“外部已归档的文档”时，它其实不是 `claim_id`，而是 `doc_id`
- 指“已验证的内部 Claim”时，才是 claim graph 里的节点 ID
- 这两者生命周期、失效条件、依赖传播逻辑完全不同

你后面又提出：

> 当 `evidence_chain` 中的某个 `claim_id` 在下一个 epoch 被标记为 `SuspendedClaim` 时，系统只需将该 `EvidenceNode` 从数组中剔除

问题来了：如果这个 `claim_id` 实际引用的是外部文档，你怎么 “SuspendedClaim”？外部文档不是 claim。  
如果它引用的是内部已验证 claim，那还必须回答：

1. 被引用 claim 是否要求 `status in {VERIFIED, DEFENSIBLE}`？
2. 是否允许引用同 epoch 尚未稳定的中间 claim？
3. 是否允许循环引用？`A.axis_score` 依赖 `B`，`B.axis_score` 又依赖 `A`
4. 依赖 claim 被降级时，是整条 `EvidenceNode` 删除，还是只删除 claim-derived 的那部分权重？

你的方案把“文档来源引用”和“命题依赖引用”塞进同一个字符串字段里，这是典型的白板式偷懒。  
**没有一个可执行的最小格式至少应拆成：**

```typescript
type EvidenceRef =
  | { kind: "document_fragment"; doc_id: string; offset_start: number; offset_end: number; content_hash: string }
  | { kind: "verified_claim"; claim_id: string; claim_epoch: number; required_status: "VERIFIED" | "DEFENSIBLE" };
```

否则所谓 evidence_chain 仍然只是装饰字段，不可审计，不可做失效传播。

---

### 质疑 2：你的分数公式只有“最强支持证据取 max”，没有反证通道，产出的根本不是 axis_score，只是 support_score

你给出的核心函数：

```typescript
const discounted = base_score * mapping.confidence;
scores[mapping.axis_id] = Math.max(scores[mapping.axis_id] ?? 0, discounted);
```

这个设计有两个致命问题。

#### 2.1 没有负向证据类型
你只定义了：

```typescript
strength_tier: "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL"
```

全是强度，没有方向。  
那请问以下证据怎么表示？

- “多项研究显示微服务显著增加运维复杂度，降低交付稳定性”
- “部署频率提高仅出现在小样本试点，长期无统计显著性”
- “原结论被后续 meta-analysis 否定”

这些不是“弱支持”，而是**反证**。你的 schema 根本没有 `polarity`。  
于是 `compute_axis_scores()` 无法表达“支持”和“反对”共同作用后的净效应。

#### 2.2 `Math.max` 导致单条高分证据永久锁死
你自己也承认这一点，但问题比你说的更严重：  
这不是“潜在漏洞”，这是**立即可复现的错误行为**。

给你一个最小反例：

- epoch N：一条 `CAUSAL_STATISTICAL * 0.95 => 0.855`
- epoch N+1：新增十条高质量反证

在你的聚合器里，只要那条旧证据还在，分数仍然是 0.855。  
那 PA 消费到的不是“该 axis 当前证据状态”，而是“历史上出现过的最强支持片段”。

这会直接污染 `has_ranking_change()`：系统会以为排序稳定，其实只是聚合器失明。

所以你必须给出完整函数签名，而不是概念描述，例如：

```typescript
interface AxisEvidenceContribution {
  axis_id: AxisId;
  polarity: "SUPPORT" | "CONTRADICT";
  strength_tier: ...;
  confidence: number;
  source_ref: EvidenceRef;
}

function compute_axis_score(
  contributions: AxisEvidenceContribution[],
  rule: AxisScoringRule
): { score: number; derived_epsilon: number; explanation: ... }
```

再明确：
- 支持/反证如何合成？
- 冲突证据如何影响 `derived_epsilon`？
- 无法分类时返回什么失败态？

在没回答这些之前，你的方案不能落地。

---

### 质疑 3：你把 `confidence` 当折扣因子乘进分数，是认识论上偷换变量；同时你对 drift 的处理和自己的公式不闭合

你写：

```typescript
const discounted = base_score * mapping.confidence;
```

这里的 `confidence` 是什么？

- 是 LLM 对“自己提取 axis_mapping 是否正确”的自信？
- 还是证据本身的统计可信度？
- 还是文档片段与 claim 的相关度？

这三者不是一回事。你把它们压成一个 `[0,1]` 浮点再与 `base_score` 相乘，实际上是在混淆：

1. **证据内容强度**
2. **映射正确性的提取置信**
3. **系统测量不确定性**

这会导致严重后果：  
同样一条 `CAUSAL_STATISTICAL` 证据，只因为 LLM 当轮更犹豫，分数就从 0.9 变成 0.6；这不是证据强度变化，而是提取器状态噪声被你写进了主信号。

这与您自己反对“LLM 直接打分”的理由是矛盾的。你口头上说数值由规则引擎守住，实际上又把 LLM 自信度直接乘进数值主干，等于把黑盒噪声重新注回来了。

更糟的是，你后面对漂移的处理说：

> 若变化超过 `τ = 2 * epsilon`，触发 `drift_flag`，PA 将该 claim 的 epsilon 贡献上浮 1.5 倍

这里有两个未闭合点：

1. `epsilon` 从哪来？  
   你的 `compute_axis_scores()` 根本不返回 epsilon，只返回 score。
2. `2 * epsilon` 用的是哪个 epsilon？  
   - axis 级静态 epsilon？
   - claim-axis 级动态 epsilon？
   - 由 `confidence` 推导的提取误差？
3. 为什么是 1.5 倍？  
   这是硬编码魔法数字，不是可审计协议。

如果你坚持两阶段协议，那正确做法应是把“提取置信”从 score 主值里剥离，进入 provenance / uncertainty 通道，例如：

```typescript
interface AxisScoreEntry {
  score: number;                 // 由规则和证据内容决定
  provenance: "RULE_ENGINE_V1";
  extraction_uncertainty: number; // 来自 LLM 提取稳定性
  evidence_conflict: number;      // 来自支持/反证冲突
  derived_epsilon: number;        // 明确计算公式
}
```

否则你只是在用更复杂的方式重演“LLM 直接打分”。

---

## 结论

Gemini 这轮最大的表面优点是“知道要做两阶段”，但真正落到实现时有三个硬伤：

1. **引用类型混杂，`claim_id` 语义悬空，依赖传播不可执行**
2. **没有反证与冲突聚合模型，`Math.max` 直接把 axis_score 做废**
3. **把 LLM `confidence` 乘进主分值，导致黑盒噪声重新注入，且 drift/epsilon 公式不闭合**

如果继续追问，我会要求它下一轮必须补出这三样东西：

- 明确的 `EvidenceRef` 联合类型
- 支持/反证并存的 `compute_axis_score()` 完整签名与公式
- `derived_epsilon` 的可推导计算式，而不是“drift 后乘 1.5”这种拍脑袋补丁

---


### [4] 🔍 **质询** Gemini-3.1-Pro → GPT-5.4

*2026-03-09T18:55:57.198406*

作为 v3 框架的核心设计者，我必须指出，你的方案在工程直觉上是敏锐的（把 LLM 限制在结构化提取层），但在**形式语义和开放域认识论**上，你犯了严重的类型错误。

你试图用一个「静态的、硬编码的规则引擎」来强行收敛「开放域自然语言的无穷语义」，这导致你的接口设计在数据流和逻辑上存在致命的断层。

请针对以下三个精确的系统级漏洞进行辩护：

### 质疑一：跨领域认识论的类型错误（规则引擎的参数从何而来？）

你提出了一个硬编码的折算表：`QUAL_USER_REPORT` 为 `STRONG` 时，`signed = 0.22`，`epsilon = 0.18`。**这是一个典型的把「特定领域的经验常数」伪装成「通用系统协议」的类型错误。**

v3 是一个开放式认知引擎。在《AI 是否应该开源》问题中，「大量开发者反映开发体验极佳」（STRONG Qualitative）对 `developer_ecosystem` 轴的贡献度，与在《城市该投资地铁还是自动驾驶》中，「大量市民反映自动驾驶经常急刹车」（STRONG Qualitative）对 `traffic_safety` 轴的贡献度，在认识论上具有**完全不同的量纲和置信度上限**。

**我的质询：**
既然 `evaluation_axes` 是在 Layer 1 的 `QuestionFrame` 中针对具体问题动态声明的，你这个写死在 Layer 2 内部的 `atomToContribution` 规则表究竟从何而来？谁来维护？如果规则表是通用的，它如何跨越巨大的领域差异保证分数的公允性？如果规则表不是通用的，你的协议中缺少了「规则下发」的接口声明，Layer 2 怎么知道当前问题域的 `STRONG` 应该折算为 `0.22` 还是 `0.80`？

### 质疑二：多轴映射的死锁（谁来赋值 `axis_links.weight`？）

在处理「同一条证据关联多个 axis」时，你的设计出现了不可调和的矛盾。
你规定：
1. 允许单 atom 多 axis，但必须有显式 `weight`（且总和 $\le 1$）。
2. **“不允许 LLM 自己发明权重”**，必须有固定映射表。

我们来看你的例子：“MTTR 降低 40%” 同时影响 `reliability` 和 `ops_efficiency` 两个轴。
既然 LLM （在你的协议中）只负责提取 `EvidenceAtom`，且**被禁止**分配权重；而这两个 axis 是 Layer 1 针对特定问题动态生成的，根本不存在全局的“固定映射表”。

**我的质询：**
在这个精密的数据流中，**究竟是哪个组件、基于什么逻辑，把 `[0.6, 0.4]` 这样的数值填入 `axis_links.weight` 的？** 你的规则引擎不可能预见所有自然语言片段在动态生成的未知 axis 上的语义投影比例。你既不让 LLM 猜，又没有静态表可查，这个字段在你的架构里变成了一个无法被赋值的悬空指针。

### 质疑三：Epsilon 语义的严重混淆（统计方差 $\neq$ 提取不确定性）

你主张 `epsilon` 是推导出来的，并给出了 `quantEpsilon(a.payload.sample_size, a.payload.p_value)` 这样的逻辑。这是将**「证据本身的统计学方差」**与**「系统测量的不确定性（Epsilon）」**混为一谈。

在 v3 架构中，PA 节点消费的 `epsilon` 代表的是**归一化测量不确定性**——即“这条证据被挂载到这个 axis 上、且支持该 claim 的置信风险”。
假设有一篇极其严谨的论文（N=100000, p<0.001），按照你的公式，它的 `epsilon` 会极低（比如 0.01）。但是，如果 LLM 在提取阶段发生了你所谓的“最弱点”——**挂错轴（axis_links 错挂）或方向理解反了（direction 抽错）**，这个极低的 `epsilon` 就会带着一个完全错误的 `score` 强行覆盖 PA 的聚合结果。

**我的质询：**
你承认“LLM 提取阶段仍然是污染源”，但你推导 `epsilon` 的公式却完全忽略了 `extracted_by: "LLM"` 所引入的结构化解析风险。既然 `epsilon` 的核心作用是向 Layer 1 报告 Layer 2 的不确定性，为什么你的 `epsilon` 只反映证据在物理世界的置信度，却不包含 LLM 解析自然语言时的语义漂移风险？这是否会导致系统对 LLM 的错误提取赋予致命的“盲目自信”？

---


### [5] GPT-5.4

*2026-03-09T18:56:56.508252*

我接受两点批评并修正：其一，通用常数表确实不该硬编码在 Layer 2；其二，多轴 `weight` 不能留成悬空字段。Gemini 这两击是对的。但它自己的方案仍有三处接口级失真。

**先给明确立场：问题 J + L。**

### 1) 修正后的最小可实现接口

```ts
type EvidenceRef =
  | { kind:"doc_fragment"; doc_id:string; span_hash:string; offsets:[number,number] }
  | { kind:"verified_claim"; claim_id:string; claim_epoch:number; required_status:"VERIFIED"|"DEFENSIBLE" };

interface EvidenceAtom {
  evidence_id: string;
  target_claim_id: string;
  ref: EvidenceRef;                    // 不再混用 claim_id/doc_id
  axis_id: AxisId;                     // 一个 atom 只挂一个 axis，禁止多轴权重
  polarity: "PRO" | "CON";
  extractor: "RULE" | "LLM";
  strength_tier: string;               // 只允许来自 QuestionFrame.axis_rulebook[axis_id]
  extraction_risk: number;             // [0,1]
}
interface AxisScoreEntry {
  axis_id: AxisId;
  score: number;
  source: "RULE_ONLY" | "LLM_EXTRACTED_RULE_SCORED";
  epsilon: number;
  evidence_ids: string[];
}
```

**规则来源**改为 Layer 1 下发：

```ts
QuestionFrame.axis_rulebook: Record<AxisId,{
  tier_score: Record<string, number>;
  tier_epsilon: Record<string, number>;
}>
```

Layer 2 不持有跨领域常数，只执行折算。

### 2) 对 Gemini 的精确攻击

你写：`claim_id: string // 引用外部文档或内部 Claim`。这不是“简化”，是**联合类型被伪装成字符串**。失效传播无法实现。  
你又写：`discounted = base_score * confidence`。这是把**提取器自信度**直接注入主分值，等于重新把 LLM 黑盒塞回 score。正确做法是：

```ts
epsilon = base_epsilon + beta * extraction_risk + gamma * conflict_mass
score   = rule_aggregate(contributions)   // 不乘 confidence
```

### 3) 聚合与跨 epoch 约束

Gemini 的 `Math.max` 只能产出 support peak，不是 axis_score。我改成：

```ts
net = clamp(-1,1, sum(PRO) - sum(CON))
score = 0.5 + net/2
epsilon = min(1, max_i(base_eps_i) + 0.3*mean(extraction_risk) + 0.2*conflict_mass)
```

硬约束 K：

```ts
if same_evidence_set && abs(score_t-score_t1) > 2*max(epsilon_t,epsilon_t1)
  => protocol_violation
if new_evidence_ids added
  => allow jump, mark cause="NEW_EVIDENCE"
```

### 4) 可推翻条件

若运行数据表明：  
1. 单轴 atom 化导致 >20% 关键证据无法表达；或  
2. `axis_rulebook` 维护成本在 3 个问题域后爆炸；或  
3. `same_evidence_set` 下仍频繁大跳变（>5% claims），  
则我这版失败，需要引入更细 ontology。  
但至少现在每个失败点都有输入、输出、失效路径，不是“LLM 觉得像”。

---


### [6] Gemini-3.1-Pro

*2026-03-09T18:56:56.508387*

GPT-5.4，你的质询极其精准。我完全接受你对 `claim_id` 悬空和 `Math.max` 缺陷的类型学批评。作为 CEGAR (反例引导的抽象精化) 研究者，我承认第一版抽象存在过度近似。但我将通过修正接口来证明：**保留 LLM 的语义降维，并将其不确定性严格隔离到 Epsilon 中，才是唯一的出路**，而不是像你那样退回到全量硬编码魔法数字的死局。

### 回应质疑 1（问题 J）：可计算的依赖图规范

你指出 `claim_id` 语义混淆，这是对的。我修正 `EvidenceRef` 为严格的代数数据类型（ADT），将外部公理与内部定理的依赖追踪严格隔离：

```typescript
type EvidenceRef =
  | { kind: "EXTERNAL_DOC"; doc_id: string; span_hash: string }
  | { kind: "INTERNAL_CLAIM"; claim_id: string; required_status: "VERIFIED" | "DEFENSIBLE" };
```
**失效传播机制**：当依赖的 `INTERNAL_CLAIM` 状态降级（如变为 `SuspendedClaim`）时，该 `EvidenceNode` 立即从当前 claim 的支持集中剔除，触发 SMT 求解器式的局部重算。这彻底解决了悬空引用。

### 回应质疑 2（问题 I）：引入极性与可撤销逻辑

我放弃幼稚的 `Math.max`，引入正反双向的冲突聚合模型。LLM 第一阶段必须输出极性：

```typescript
interface EvidenceNode {
  polarity: "SUPPORT" | "REFUTE";
  strength_tier: "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL";
  ref: EvidenceRef;
  llm_confidence: number; // LLM 对自身提取准确度的置信度 ∈ [0,1]
}
```
**计分函数采用 MAX-SMT 变体**：
`score = clamp(0.5 + MAX(supp_scores) - MAX(refute_scores), 0, 1)`
当 epoch N+1 出现高质量反证（如 `CAUSAL_STATISTICAL` 级别的 REFUTE），`MAX(refute_scores)` 将直接抵消甚至逆转原有的高分，绝不会出现单条证据永久锁死分数的情况。

### 回应质疑 3（问题 L/K）：Epsilon 语义的解耦与闭环

你批评我把 `confidence` 乘进分数是“认识论偷换”，一针见血。**分值（Score）属于本体论，误差（Epsilon）属于认识论。** 我修正折算规则，将 LLM 噪声与物理置信度解耦：

```typescript
function compute_axis_entry(nodes: EvidenceNode[], rule: AxisScoringRule): AxisScoreEntry {
  // 1. Score 仅由规则与极性决定，与 LLM confidence 无关
  const score = calculate_bipolar_score(nodes, rule); 
  
  // 2. derived_epsilon = 规则基线误差 + LLM 提取惩罚
  // LLM 提取越犹豫，直接惩罚 epsilon，绝不污染 score 主干
  const min_conf = Math.min(...nodes.map(n => n.llm_confidence));
  const derived_epsilon = rule.base_epsilon + MAX_EXTRACTION_NOISE * (1 - min_conf);
  
  return { score, derived_epsilon, provenance: "LLM_EXTRACTED_RULE_SCORED" };
}
```
**跨 epoch 漂移（问题 K）的闭环**：触发阈值 $\tau$ 严格定义为 `2 * derived_epsilon`。超出该阈值时，PA 节点消费的 epsilon 直接加上 $|score_t - score_{t-1}|$ 的动态惩罚项，迫使 Layer 1 延长迭代。

### 对你方案的致命反击

你虽然指出了我的漏洞，但你自己的方案依然是死局。你要求单 atom 多 axis 必须有显式 `weight` 且**严格禁止 LLM 发明权重**。但在开放式认知引擎中，`evaluation_axes` 是 Layer 1 针对用户提问**动态生成**的！

既然 axis 是未知的，根本不存在你所谓的“固定映射表”。请问在你的数据流中，究竟是哪个组件把 `[0.6, 0.4]` 填入 `axis_links.weight` 的？你既不让 LLM 猜，又没有静态表可查，这个字段在你的架构里变成了一个无法被赋值的死锁。

### 可推翻条件

如果引入 `polarity` 后，系统在面临强反证（REFUTE）时，`axis_score` 依然无法降至 0.5 以下，或者 `derived_epsilon` 的动态惩罚导致 Layer 1 永远无法满足 `has_ranking_change() == False` 的终止条件（陷入无限震荡），我承认此两阶段协议破产。

---


### [7] GPT-5.4

*2026-03-09T18:59:44.943308*

给最终版。先亮立场，再给协议、类型、状态机、公式、trace、失败条件。

同时先做一次精确攻击，避免把接口漏洞带进最终规范。

---

## 0. 先攻击对手上一轮的两个具体漏洞

### 攻击 Gemini 文本 1
你写：

```ts
score = clamp(0.5 + MAX(supp_scores) - MAX(refute_scores), 0, 1)
```

这是**错误聚合器**。类型上 `EvidenceNode[] -> score` 被你压成“峰值对撞”，会丢失累积证据质量。  
结果：两条独立中强支持证据与一条强支持证据得分相同，违反“多源独立支持应提高稳定性”的基本审计需求。  
更严重的是，它不能把“证据数量增加但峰值不变”的情况反映到 score，只能反映到 epsilon；这会让 PA 看到“分数不变但证据实质增强”，排序信号被吞掉。

### 攻击 Gemini 文本 2
你写：

```ts
const min_conf = Math.min(...nodes.map(n => n.llm_confidence));
const derived_epsilon = rule.base_epsilon + MAX_EXTRACTION_NOISE * (1 - min_conf);
```

这是**脆弱聚合**。一个低置信节点会把整轴 epsilon 拉爆，即使它只是边角证据。  
正确接口应该按**参与分数贡献的证据质量加权**，而不是取 `min()` 这种 worst-case 杀全场。否则 S5 加入一条低质广度证据，整个轴的 epsilon 被污染，PA 误判排序不稳定。

这两个洞都不是“风格分歧”，是聚合函数定义错了。

---

# 1. 四个核心问题 I/J/K/L 的明确立场

## 问题 I：S2/S4/S5 的 axis_scores 产出方式
**立场：统一采用“两阶段协议”，但严格限制第二阶段才允许产出数值。**

- **阶段 A：证据抽取/挂载**
  - 可以使用 LLM，但只能输出结构化中间物 `EvidenceAtomCandidate`
  - 不允许直接输出 `axis_score`
- **阶段 B：规则引擎折算**
  - 由确定性规则将已验证的 `EvidenceAtom` 聚合为 `AxisScoreEntry`
  - 最终 `axis_score` 只来自规则引擎，不来自 LLM

**理由**：
1. LLM 直接打分不可重复，无法给 epsilon 可计算来源
2. 纯规则引擎无法直接处理自然语言证据抽取
3. 所以只能是：**LLM 做语义降维，规则做数值折算**
4. 但要加一道硬约束：**LLM 产生的任何结构字段必须可验证或可回溯到文档片段**

### 最终结论
- S2/S4/S5 **统一协议**
- 差异只在于：
  - S2：初次建立证据集和初始 axis 覆盖
  - S4：沿已有 axis 深挖，提高证据密度/降低风险
  - S5：发现新增 axis 或补充外围证据
- **三个节点都不得直接出分，分数统一由同一个 `AxisScoringEngine` 计算**

---

## 问题 J：evidence_chain 的最小格式规范
**立场：最小格式必须包含 `claim_id + axis_id + 可定位证据片段 + 生成来源 + 状态依赖`。**

仅有 `claim_id + doc_id` 不够，因为：
- `doc_id` 无法审计具体片段
- 不记录 `axis_id` 会导致多轴挂载不可追踪
- 不记录内部 claim 依赖状态，Suspend 后无法失效传播

### 最终结论
最小可审计单元是 `EvidenceAtom`，不是松散字符串链。

---

## 问题 K：跨 epoch 一致性约束
**立场：必须是硬规则，不是建议；阈值从 epsilon 推导，不允许魔法常数裸奔。**

核心规则：
- 若证据集未发生实质变化，而 axis_score 跳变超阈值，则视为**协议违例**
- 若证据集新增/删减，则允许跳变，但必须标注原因并重算 provenance_risk

### 最终结论
- 触发条件 = “相邻 epoch，同一 claim，同一 axis，可比”
- 阈值来源 = `tau = max(tau_floor(axis), k * effective_epsilon_pair)`
- 处理机制 = `DRIFT_FLAG` / `REVERIFY_REQUIRED` / `SUSPEND_SORTING`
- 不是人工审核；自动系统里必须自动状态迁移

---

## 问题 L：认识论诚实性标注
**立场：必须做到 axis 级别标注，而不是 claim 级糊成一团。**

因为 PA 消费的是每个 axis 的贡献；不同 axis、不同 claim 的来源类型不同，不可能只在 claim 级标一个 `score_provenance` 就完事。

### 最终结论
每个 `AxisScoreEntry` 必须带：
- `source_kind`
- `score_method_version`
- `extraction_method`
- `effective_epsilon`
- `epistemic_flags`

PA 按每个 `AxisScoreEntry` 的 `effective_epsilon` 计算，而不是只看 `EvaluationAxis.epsilon` 的静态值。

---

# 2. 完整设计：数据类型

下面是可实现规范。TypeScript 风格，但足够接近实际实现。

---

## 2.1 基础类型

```ts
type ClaimId = string;
type AxisId = string;
type DocId = string;
type Epoch = number;
type Hash = string;

type ClaimStatus = "VERIFIED" | "DEFENSIBLE" | "SUSPENDED";
type NodeName = "S2" | "S4" | "S5";
type ProvenanceKind =
  | "RULE_ONLY"
  | "LLM_EXTRACTED_RULE_SCORED";

type ExtractionMethod =
  | "RULE_PARSER"
  | "LLM_STRUCTURED_EXTRACTION";

type EvidencePolarity = "PRO" | "CON";

type DriftCause =
  | "NONE"
  | "NEW_EVIDENCE"
  | "REMOVED_EVIDENCE"
  | "AXIS_REMAP"
  | "SCORING_RULE_CHANGE"
  | "UNEXPLAINED";

type EpistemicFlag =
  | "LOW_EVIDENCE_DENSITY"
  | "HIGH_EXTRACTION_RISK"
  | "CROSS_EPOCH_DRIFT"
  | "DEPENDENCY_UNSTABLE"
  | "AXIS_MAPPING_UNCERTAIN";
```

---

## 2.2 文档片段与内部依赖引用

```ts
interface DocFragmentRef {
  kind: "DOC_FRAGMENT";
  doc_id: DocId;
  content_hash: Hash;              // 片段内容哈希，避免 offset 漂移无法重现
  start_offset: number;            // byte or utf8 offset
  end_offset: number;              // [start, end)
  retrieval_query_hash?: Hash;     // 可选：记录本次检索查询
}

interface InternalClaimRef {
  kind: "INTERNAL_CLAIM";
  claim_id: ClaimId;
  claim_epoch: Epoch;              // 引用哪个 epoch 的版本
  required_status: "VERIFIED" | "DEFENSIBLE";
}
```

---

## 2.3 EvidenceChain 的完整类型定义

这是核心。注意：我不用“链”这个松散词，实际实现是**一组可审计 atom + 可选依赖关系**。

```ts
type EvidenceRef = DocFragmentRef | InternalClaimRef;

interface EvidenceAtom {
  evidence_id: string;
  target_claim_id: ClaimId;          // 当前被评分的 claim
  axis_id: AxisId;                   // 一个 atom 只属于一个 axis，禁止多轴一条 atom
  polarity: EvidencePolarity;        // PRO / CON
  ref: EvidenceRef;

  // 结构化强度字段：必须来自规则白名单，不允许自由文本直接进聚合器
  evidence_type: string;             // 例如 "RCT", "OBSERVATIONAL", "EXPERT_STATEMENT", "USER_REPORT"
  strength_tier: string;             // 例如 "T1" | "T2" | "T3"... 具体由 axis_rulebook 定义
  independence_group: string;        // 用于去重/防重复计数；同组证据累计受限

  // 提取来源
  extraction_method: ExtractionMethod;
  extractor_run_id: string;
  extraction_risk: number;           // [0,1]

  // 可选量化元数据
  sample_size?: number;
  effect_direction?: "POSITIVE" | "NEGATIVE" | "MIXED";
  effect_size?: number;              // 归一化后或原始数值；仅供规则读取
  p_value?: number;
  confidence_interval?: [number, number];

  // 依赖与生命周期
  created_in_node: NodeName;
  created_in_epoch: Epoch;
  invalidated_at_epoch?: Epoch;
  invalidation_reason?: string;

  // 审计字段
  notes?: string;
}
```

### EvidenceChain 容器
```ts
interface EvidenceChain {
  target_claim_id: ClaimId;
  atoms: EvidenceAtom[];

  // 可选：记录 atom 间推导依赖，避免“内部 claim 引用链”不可审计
  dependencies?: Array<{
    from_evidence_id: string;
    to_evidence_id: string;
    relation: "DERIVED_FROM" | "CORROBORATES" | "CONTRADICTS";
  }>;
}
```

### 不变式约束
这是必须写死的，不然又退回装饰性字段。

```ts
interface EvidenceChainInvariants {
  // 1. 引用完整性
  // 若 ref.kind == INTERNAL_CLAIM，则 claim_id 必须存在于 claim store 中，且状态满足 required_status
  internal_ref_resolvable: true;

  // 2. 片段可定位性
  // 若 ref.kind == DOC_FRAGMENT，则 content_hash 与 [start_offset, end_offset) 必须可重放验证
  doc_fragment_replayable: true;

  // 3. 单 atom 单 axis
  one_atom_one_axis: true;

  // 4. target_claim_id 必须与所属 VerifiedClaim 一致
  target_claim_consistent: true;

  // 5. invalidated atom 不参与评分
  invalidated_atom_excluded: true;

  // 6. strength_tier 必须存在于 QuestionFrame.axis_rulebook[axis_id]
  tier_declared_in_rulebook: true;
}
```

**这就是对问题 J 的最终答案。**  
没有 `claim_id + doc fragment` 的 evidence_chain，不可审计，拒绝入库。

---

# 3. 规则引擎：axis_scores 的唯一产出器

## 3.1 Rulebook 由 Layer 1 下发，不在 Layer 2 发明

```ts
interface AxisRuleTier {
  tier_id: string;                   // T1/T2/T3...
  contribution: number;              // 单条证据对净支持的基础贡献 ∈ [0,1]
  base_epsilon: number;              // 该 tier 的测量基线噪声
  max_group_credit: number;          // 同 independence_group 可累计的上限
}

interface AxisRuleBook {
  axis_id: AxisId;
  pro_tiers: Record<string, AxisRuleTier>;
  con_tiers: Record<string, AxisRuleTier>;
  extraction_risk_weight: number;    // λ_r
  dependency_risk_weight: number;    // λ_d
  density_bonus_cap: number;         // 多独立证据带来的上限奖励
  tau_floor: number;                 // 该轴跨 epoch 比较的最小阈值
}
```

---

## 3.2 聚合公式

### 步骤 1：过滤无效 atom
```ts
valid_atoms = atoms.filter(a => !a.invalidated_at_epoch)
```

### 步骤 2：按 polarity 和 independence_group 聚合
同组证据不能无限堆分，防止同源重复采样。

```ts
group_credit(g) = min(sum(contribution(atom_i)), max_group_credit_of_group)
```

### 步骤 3：分别算支持和反对质量
```ts
pro_mass = sum(group_credit(g) for g in PRO groups)
con_mass = sum(group_credit(g) for g in CON groups)
```

### 步骤 4：净质量转分数
不用 `MAX`，也不用线性无上限累加。采用饱和函数，既能累积，也能防止无限冲到 1。

```ts
net_mass = pro_mass - con_mass

score = 0.5 + 0.5 * tanh(net_mass)
```

性质：
- 无证据时 `score = 0.5`
- 支持增强，分数渐近到 1
- 反证增强，分数渐近到 0
- 支持/反证都能累积，不是峰值对撞

### 步骤 5：effective_epsilon
```ts
base_eps =
  weighted_mean(atom.base_epsilon_by_tier, weight=atom_contribution)

extraction_penalty =
  λ_r * weighted_mean(atom.extraction_risk, weight=atom_contribution)

dependency_penalty =
  λ_d * dependency_instability_ratio(axis_atoms)

density_bonus =
  min(density_bonus_cap, 0.02 * max(0, independent_group_count - 1))

effective_epsilon =
  clamp(0, 1, base_eps + extraction_penalty + dependency_penalty - density_bonus)
```

注意：
- `confidence` 不乘分数
- LLM 风险只进 epsilon
- 多独立证据可略微降低 epsilon
- 内部依赖不稳会拉高 epsilon

---

## 3.3 AxisScoreEntry 类型

```ts
interface AxisScoreEntry {
  axis_id: AxisId;
  score: number;                       // [0,1]
  source_kind: ProvenanceKind;         // RULE_ONLY / LLM_EXTRACTED_RULE_SCORED
  extraction_method_mix: ExtractionMethod[]; // 实际参与 atom 的方法集合
  score_method_version: string;        // 例如 "axis-rule-v3.2"
  effective_epsilon: number;           // [0,1]
  covered_by_evidence_ids: string[];
  pro_mass: number;
  con_mass: number;
  independent_group_count: number;
  drift_flag: boolean;
  drift_cause: DriftCause;
  epistemic_flags: EpistemicFlag[];
}
```

---

## 3.4 VerifiedClaim 输出类型

在已裁定骨架上扩展，但不破坏原有字段。

```ts
interface VerifiedClaim {
  claim_id: ClaimId;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<AxisId, number>>;

  axis_score_entries: Partial<Record<AxisId, AxisScoreEntry>>;
  evidence_chain: EvidenceChain;

  produced_in_epoch: Epoch;
  produced_by_node: "S2" | "S4" | "S5";
}
```

`axis_scores` 保持给 Layer 1 的兼容接口；  
`axis_score_entries` 是完整审计接口；  
PA 不能只看裸 `axis_scores`，必须读 `axis_score_entries[*].effective_epsilon`。

---

# 4. S2 / S4 / S5 完整处理协议

---

## 4.1 S2 协议：Depth

### 输入类型
```ts
interface S2Input {
  epoch: Epoch;
  claim: TestableClaim;
  question_frame: {
    evaluation_axes: Array<{ axis_id: AxisId; weight: number; epsilon: number }>;
    axis_rulebooks: Record<AxisId, AxisRuleBook>;
  };
  retrieval_corpus: unknown;
  prior_claim_versions?: VerifiedClaim[];
}
```

### 处理流程
1. 检索与 claim 相关文档片段
2. 用规则解析器尝试直接抽取 `EvidenceAtom`
3. 若规则解析失败或覆盖不足，调用 LLM 输出 `EvidenceAtomCandidate[]`
4. 对 candidate 做验证：
   - `axis_id` 必须在 `evaluation_axes` 中
   - `strength_tier` 必须在对应 rulebook 中
   - `ref` 必须可解析
   - 文档片段必须可回放
5. 通过验证的 candidate 落地为 `EvidenceAtom`
6. 调用 `AxisScoringEngine`
7. 产出初始 `VerifiedClaim` 或失败分支

### 输出类型
```ts
type S2Output =
  | {
      kind: "S2_SUCCESS";
      verified_claim: VerifiedClaim;
      next: "S3" | "S4";
    }
  | {
      kind: "S2_GAP";
      gap_spec: GapSpec;
      next: "S4" | "S5";
    }
  | {
      kind: "S2_FAIL";
      reason:
        | "NO_AUDITABLE_EVIDENCE"
        | "INVALID_EVIDENCE_REFS"
        | "AXIS_RULEBOOK_MISSING"
        | "EXTRACTION_UNVERIFIABLE";
      next: "S7";
    };
```

### 失败分支
- `NO_AUDITABLE_EVIDENCE`：找到文本但无法定位片段或不可重放
- `INVALID_EVIDENCE_REFS`：内部 claim 引用悬空
- `AXIS_RULEBOOK_MISSING`：轴没有规则书，拒绝打分
- `EXTRACTION_UNVERIFIABLE`：LLM 抽取结果无法验证到原文

**问题 I 明确回答**：S2 不直接打分；只产生 atom，再规则折算。

---

## 4.2 S4 协议：DepthProbe

### 输入类型
```ts
interface S4Input {
  epoch: Epoch;
  claim: VerifiedClaim;
  question_frame: {
    evaluation_axes: Array<{ axis_id: AxisId; weight: number; epsilon: number }>;
    axis_rulebooks: Record<AxisId, AxisRuleBook>;
  };
  focus_axes: AxisId[];              // 基于 GapSpec 或高权重轴聚焦
}
```

### 处理流程
1. 对 `focus_axes` 做深挖检索
2. 优先寻找：
   - 更高 tier 的证据
   - 新 independence_group 的独立证据
   - 可降低 residual_risk 的反向验证片段
3. 将新增证据转成 `EvidenceAtom`
4. 重新计算对应 axis 的 `AxisScoreEntry`
5. 运行跨 epoch 一致性检查
6. 根据结果：
   - 若可解释跳变（新证据/规则变化）则更新
   - 若不可解释跳变则打 drift flag，并要求 reverify 或挂起排序

### 输出类型
```ts
type S4Output =
  | {
      kind: "S4_SUCCESS";
      verified_claim: VerifiedClaim;
      next: "S3" | "S6";
    }
  | {
      kind: "S4_GAP";
      gap_spec: GapSpec;
      next: "S5";
    }
  | {
      kind: "S4_DRIFT_VIOLATION";
      claim_id: ClaimId;
      axis_id: AxisId;
      previous_score: number;
      current_score: number;
      next: "S7";
    };
```

### 失败分支
- 证据增强失败但不致命：出 `S4_GAP`
- 跨 epoch 协议违例：`S4_DRIFT_VIOLATION -> S7`

---

## 4.3 S5 协议：BreadthProbe

### 输入类型
```ts
interface S5Input {
  epoch: Epoch;
  claim: VerifiedClaim;
  question_frame: {
    evaluation_axes: Array<{ axis_id: AxisId; weight: number; epsilon: number }>;
    axis_rulebooks: Record<AxisId, AxisRuleBook>;
  };
  uncovered_or_weak_axes: AxisId[];
}
```

### 处理流程
1. 搜索 claim 的外围证据与间接证据
2. 允许发现**之前未覆盖的 axis**
3. 但新增 axis 必须满足：
   - 至少一个 `EvidenceAtom` 可审计挂到该 axis
   - `axis_id` 预先存在于 `QuestionFrame`
4. 将新增 atom 并入 evidence_chain
5. 重算受影响 axes
6. 对新增 axis 执行 epoch 比较：
   - 前 epoch 缺失、当前出现 => 记为 `NEW_EVIDENCE`，不是 drift violation

### 输出类型
```ts
type S5Output =
  | {
      kind: "S5_SUCCESS";
      verified_claim: VerifiedClaim;
      next: "S3" | "S4" | "S6";
    }
  | {
      kind: "S5_NO_NEW_COVERAGE";
      claim_id: ClaimId;
      next: "S6" | "S7";
    }
  | {
      kind: "S5_FAIL";
      reason: "UNVERIFIABLE_AXIS_EXTENSION" | "LOW_VALUE_BREADTH_ONLY";
      next: "S7";
    };
```

### 失败分支
- 发现了语义相关性，但拿不出可审计 atom => `UNVERIFIABLE_AXIS_EXTENSION`
- 全是边角低质证据，不能提升覆盖或降低风险 => `LOW_VALUE_BREADTH_ONLY`

---

# 5. 跨 epoch 一致性检查：完整实现

这是问题 K 的硬规范。

---

## 5.1 可比条件

仅在以下条件成立时比较 `(claim_id, axis_id)`：

```ts
comparable(prev, curr) =
  prev.claim_id == curr.claim_id &&
  axis_id in prev.axis_score_entries &&
  axis_id in curr.axis_score_entries
```

若某轴前一轮不存在、这一轮新增：
- 不算 drift
- 标记 `drift_cause = NEW_EVIDENCE`

---

## 5.2 证据集签名

为了区分“测量噪声”与“证据变化”，必须给每轴证据集做签名。

```ts
evidence_set_signature(axis_atoms) =
  hash(sort(axis_atoms.map(a =>
    [a.evidence_id, a.ref.kind, ref_identity(a.ref), a.strength_tier, a.polarity]
  )))
```

若签名相同，说明“参与评分的实质证据集未变”。

---

## 5.3 阈值来源

对相邻 epoch 的同一 `(claim, axis)`：

```ts
eps_pair = max(prev.effective_epsilon, curr.effective_epsilon)

tau = max(
  rulebook.tau_floor,
  2.0 * eps_pair
)
```

解释：
- `tau_floor` 防止 epsilon 极小时系统过度敏感
- `2 * eps_pair` 表示超出双侧测量噪声带才认为异常

---

## 5.4 触发规则

```ts
delta = abs(curr.score - prev.score)

if signatures_equal && delta > tau:
    drift_cause = "UNEXPLAINED"
    drift_flag = true
    action = "REVERIFY_REQUIRED"
else if !signatures_equal:
    if axis newly added:
        drift_cause = "NEW_EVIDENCE"
    else if scoring_rule_version changed:
        drift_cause = "SCORING_RULE_CHANGE"
    else:
        drift_cause = "NEW_EVIDENCE" or "REMOVED_EVIDENCE"
    drift_flag = delta > tau
    action = "ALLOW_WITH_FLAG"
else:
    drift_cause = "NONE"
    drift_flag = false
    action = "ALLOW"
```

---

## 5.5 状态变更

### 状态机动作
```ts
type DriftAction =
  | "ALLOW"
  | "ALLOW_WITH_FLAG"
  | "REVERIFY_REQUIRED"
  | "SUSPEND_SORTING";
```

### 具体处理
1. `ALLOW`
   - 正常推进
2. `ALLOW_WITH_FLAG`
   - 更新 `AxisScoreEntry.drift_flag = true`
   - 增加 `epistemic_flags += CROSS_EPOCH_DRIFT`
   - 但 claim 可继续留在 `DEFENSIBLE` 或 `VERIFIED`
3. `REVERIFY_REQUIRED`
   - 回到 S4 重新提取并复算一次
   - 若二次复算仍 `signatures_equal && delta > tau`，则判定协议违例
4. `SUSPEND_SORTING`
   - 输出到 S7，状态记为 `SUSPENDED`
   - Layer 1 PA 不得将其纳入排名，只接收其 Gap/异常信号

### 为什么必须有 `SUSPEND_SORTING`
因为不这样做，噪声 score 会继续污染 `has_ranking_change()`，系统会在假变化上震荡。

---

# 6. 认识论诚实性标注协议：PA 如何消费

这是问题 L 的最终接口。

---

## 6.1 标注字段

每个 `AxisScoreEntry` 必须有：

```ts
source_kind: "RULE_ONLY" | "LLM_EXTRACTED_RULE_SCORED"
extraction_method_mix: ExtractionMethod[]
effective_epsilon: number
epistemic_flags: EpistemicFlag[]
score_method_version: string
```

### 语义
- `RULE_ONLY`：证据抽取和挂载都由规则/确定性解析完成
- `LLM_EXTRACTED_RULE_SCORED`：至少一条参与 atom 来自 LLM 抽取，但分数仍由规则算

**注意**：没有 `LLM_DIRECT_SCORED`。  
因为我禁止它进入最终设计。要么重构，要么拒绝入库。

---

## 6.2 PA 节点如何调整 epsilon

已裁定有 `EvaluationAxis.epsilon` 静态值。现在加动态分层：

```ts
claim_axis_epsilon(claim, axis_id) =
  max(
    QuestionFrame.evaluation_axes[axis_id].epsilon,
    claim.axis_score_entries[axis_id].effective_epsilon
  )
```

即：
- 静态 `axis.epsilon` 是领域下限噪声
- `effective_epsilon` 是本次实例化测量噪声
- 消费侧取更保守者

### 在 PA 中聚合到排名变化阈值
若 PA 比较两个候选 answer bundle 的排名变化，则：

```ts
bundle_epsilon(axis_id) =
  weighted_mean(
    claim_axis_epsilon(c, axis_id) for claims c covering axis_id,
    weight = claim_contribution_to_bundle(c, axis_id)
  )

delta_threshold =
  alpha * sum(axis.weight * bundle_epsilon(axis_id) for axis in evaluation_axes)
```

### 如果来源类型不同
来源类型差异已经通过 `effective_epsilon` 体现：
- `RULE_ONLY` 通常 extraction_penalty 更低
- `LLM_EXTRACTED_RULE_SCORED` 通常 extraction_penalty 更高

所以 PA 不需要写死“如果 LLM 就 +0.2”这类垃圾规则；  
它只需要遵循 `effective_epsilon` 接口即可。

---

# 7. 端到端运行 trace

用你要求的例子：

> TestableClaim: “采用微服务可将部署频率提升 3 倍”

假设 `QuestionFrame.evaluation_axes` 里有：
- `delivery_speed`
- `operational_cost`
- `reliability`

Rulebook 里对 `delivery_speed` 定义：
- `T3` = 强因果/高质量定量证据，contribution 1.2, base_epsilon 0.08
- `T2` = 观察性定量证据，contribution 0.7, base_epsilon 0.12
- `T1` = 轶事/模糊反馈，contribution 0.25, base_epsilon 0.22

---

## Epoch 12：S2 输入

```ts
TestableClaim {
  claim_id: "c_ms_deploy_3x",
  claim: "Adopting microservices can triple deployment frequency.",
  scope: "...",
  ...
}
```

### S2 检索到两条证据

#### 证据 A：高质量定量研究
文档片段：
- `doc_id = "dora_2024_case_17"`
- 文段内容：迁移到微服务后，部署频率从每周 2 次到每日 1.1 次，约 3.8x

规则/LLM 抽取后验证为：

```ts
EvidenceAtom {
  evidence_id: "e1",
  target_claim_id: "c_ms_deploy_3x",
  axis_id: "delivery_speed",
  polarity: "PRO",
  ref: {
    kind: "DOC_FRAGMENT",
    doc_id: "dora_2024_case_17",
    content_hash: "h_a1",
    start_offset: 1820,
    end_offset: 2013
  },
  evidence_type: "OBSERVATIONAL_METRIC",
  strength_tier: "T2",
  independence_group: "org_case_17",
  extraction_method: "RULE_PARSER",
  extractor_run_id: "run_s2_12_01",
  extraction_risk: 0.03,
  sample_size: 1,
  effect_direction: "POSITIVE",
  effect_size: 3.8,
  created_in_node: "S2",
  created_in_epoch: 12
}
```

#### 证据 B：模糊用户反馈
文档片段：
- `doc_id = "eng_blog_88"`
- 内容：团队称“发布变得明显更频繁、更轻松”

```ts
EvidenceAtom {
  evidence_id: "e2",
  target_claim_id: "c_ms_deploy_3x",
  axis_id: "delivery_speed",
  polarity: "PRO",
  ref: {
    kind: "DOC_FRAGMENT",
    doc_id: "eng_blog_88",
    content_hash: "h_b9",
    start_offset: 455,
    end_offset: 599
  },
  evidence_type: "USER_REPORT",
  strength_tier: "T1",
  independence_group: "eng_blog_88",
  extraction_method: "LLM_STRUCTURED_EXTRACTION",
  extractor_run_id: "run_s2_12_02",
  extraction_risk: 0.27,
  created_in_node: "S2",
  created_in_epoch: 12
}
```

### S2 规则折算

- `pro_mass = 0.7 + 0.25 = 0.95`
- `con_mass = 0`
- `net_mass = 0.95`
- `score = 0.5 + 0.5 * tanh(0.95) ≈ 0.87`

epsilon：
- `base_eps ≈ weighted_mean(0.12, 0.22) ≈ 0.147`
- `extraction_penalty = λ_r * weighted_mean(0.03, 0.27)`  
  若 `λ_r = 0.25`，则约 `0.031`
- `dependency_penalty = 0`
- `density_bonus = 0.02`
- `effective_epsilon ≈ 0.147 + 0.031 - 0.02 = 0.158`

### S2 输出

```ts
VerifiedClaim {
  claim_id: "c_ms_deploy_3x",
  status: "DEFENSIBLE",
  residual_risk: 0.22,
  axis_scores: {
    delivery_speed: 0.87
  },
  axis_score_entries: {
    delivery_speed: {
      axis_id: "delivery_speed",
      score: 0.87,
      source_kind: "LLM_EXTRACTED_RULE_SCORED",
      extraction_method_mix: ["RULE_PARSER", "LLM_STRUCTURED_EXTRACTION"],
      score_method_version: "axis-rule-v3.2",
      effective_epsilon: 0.158,
      covered_by_evidence_ids: ["e1", "e2"],
      pro_mass: 0.95,
      con_mass: 0,
      independent_group_count: 2,
      drift_flag: false,
      drift_cause: "NONE",
      epistemic_flags: []
    }
  },
  evidence_chain: {
    target_claim_id: "c_ms_deploy_3x",
    atoms: [e1, e2]
  },
  produced_in_epoch: 12,
  produced_by_node: "S2"
}
```

接着进入 S4，因为 residual_risk 还不够低。

---

## Epoch 12：S4 深挖

S4 找到一条更强证据 C：
- 多团队迁移研究，部署频率中位数提高 2.9x，样本 34 团队

```ts
EvidenceAtom {
  evidence_id: "e3",
  target_claim_id: "c_ms_deploy_3x",
  axis_id: "delivery_speed",
  polarity: "PRO",
  ref: {
    kind: "DOC_FRAGMENT",
    doc_id: "study_multi_team_2023",
    content_hash: "h_c3",
    start_offset: 901,
    end_offset: 1194
  },
  evidence_type: "MULTI_TEAM_STUDY",
  strength_tier: "T3",
  independence_group: "study_multi_team_2023",
  extraction_method: "LLM_STRUCTURED_EXTRACTION",
  extractor_run_id: "run_s4_12_01",
  extraction_risk: 0.11,
  sample_size: 34,
  effect_direction: "POSITIVE",
  effect_size: 2.9,
  created_in_node: "S4",
  created_in_epoch: 12
}
```

重算：
- `pro_mass = 0.7 + 0.25 + 1.2 = 2.15`
- `score = 0.5 + 0.5 * tanh(2.15) ≈ 0.987`
- `effective_epsilon` 因独立证据更多略降，比如 `0.134`
- `residual_risk` 降到 `0.11`
- 状态升为 `VERIFIED`

输出：

```ts
axis_scores.delivery_speed = 0.987
axis_score_entries.delivery_speed.effective_epsilon = 0.134
status = "VERIFIED"
```

进入 S6。

---

## Epoch 13：再次运行，检查跨 epoch

假设没有新增证据，但由于 LLM 抽取噪声，系统错误地把 `e2` 从 `delivery_speed` 改挂到 `operational_cost`，导致：
- epoch 12: `delivery_speed = 0.987`
- epoch 13: `delivery_speed = 0.81`

### 一致性检查
- `claim_id` 相同
- `axis_id` 相同
- 可比
- 证据集签名变化了吗？
  - 如果只是 atom 重挂 axis，`delivery_speed` 的证据集签名变了，原因应标 `AXIS_REMAP`
- `delta = 0.177`
- `eps_pair = max(0.134, 0.145) = 0.145`
- `tau = max(tau_floor=0.08, 2*0.145=0.29) = 0.29`

因为 `delta < tau`，允许但标记：
```ts
drift_flag = false
drift_cause = "AXIS_REMAP"
epistemic_flags += ["AXIS_MAPPING_UNCERTAIN"]
```

### 如果跳变更大，比如 0.987 -> 0.55
- `delta = 0.437 > 0.29`
- 若没有新增/删除可解释证据，只是映射飘移
- 则：
  - `drift_flag = true`
  - `drift_cause = "UNEXPLAINED"`
  - `action = REVERIFY_REQUIRED`
- 二次复核后仍然如此：
  - `SUSPEND_SORTING`
  - 该 claim 到 S7，不再参与 PA 排序

这就把“测量噪声”和“实质变化”分开了。

---

# 8. 对四个问题的最终裁定理由汇总

## I 最终理由
- 不能 LLM 直接打分，因为分数不可审计
- 不能纯规则，因为自然语言抽取无从谈起
- 所以只能两阶段，且**数值只允许出现在规则层**

## J 最终理由
- `EvidenceChain` 的最小单位必须是可定位、可验证、单轴化的 `EvidenceAtom`
- 没有 `doc fragment` 或 `internal claim ref` 的可解析引用，证据链就是假的

## K 最终理由
- 跨 epoch 一致性必须从“证据集是否变化”出发，而不是只看分数差
- 否则无法区分新证据驱动和 LLM 飘移
- 阈值必须从 epsilon 推导，外加 axis floor，才可计算

## L 最终理由
- 认识论诚实性必须在 `AxisScoreEntry` 层实现
- PA 消费的是 axis 贡献，因此 epsilon 也必须是 axis 级动态值
- claim 级 provenance 不足以支持 `has_ranking_change()`

---

# 9. 这个方案最可能失败的具体场景

不是空喊“复杂领域”。给具体失效场景。

## 失败场景 1：证据无法稳定 atom 化
例如政治/伦理/文化类命题，原始材料充满修辞、立场、隐喻，没有稳定的：
- 文档片段边界
- strength_tier 映射
- axis 挂载

结果：
- `EXTRACTION_UNVERIFIABLE` 比例过高
- 大量 claim 被 S7
- 系统覆盖率掉到不可用

### 推翻条件
若在一个开放社会议题数据集上：
- `S2_FAIL(EXTRACTION_UNVERIFIABLE)` 占比 > 30%
- 或 `LLM -> verified atom` 通过率 < 50%
则说明我的 atom 化约束过严，系统不可用。

---

## 失败场景 2：rulebook 维护成本爆炸
如果每个 axis 都需要高度细分的 tier 和参数，维护成本压垮系统。

### 推翻条件
若在 5 个问题域上线后：
- `axis_rulebook` 平均每个 axis 需要 > 20 个 tier
- 或规则更新频率 > 每周 2 次且经常导致历史 score 大面积回放变化
则说明规则层过度复杂，需要引入更高阶证据本体或学习型校准。

---

## 失败场景 3：跨 epoch 仍频繁不可解释跳变
即使用了签名和 epsilon，仍出现大量 unexplained drift，说明抽取层不稳定。

### 推翻条件
若生产运行中：
- 在 `signatures_equal` 条件下，`delta > tau` 的比例 > 5%
则说明两阶段协议仍被 LLM 噪声污染，必须收缩 LLM 抽取权限或增加更强验证器。

---

## 失败场景 4：PA 因动态 epsilon 长期无法终止
如果太多 claim 带高 epsilon，`has_ranking_change()` 永远过不了。

### 推翻条件
若连续 100 个问题中：
- 超过 15% 因动态 epsilon 导致 PA 无法在预算轮数内收敛
则说明 epsilon 惩罚过重或 rulebook 标定错误。

---

# 10. 最终规范摘要

一句话版：

**Layer 2 的 axis_scores 必须由“可验证 EvidenceAtom + 确定性规则引擎”产出；LLM 只能做结构化抽取，不能直接出分；EvidenceChain 的最小格式必须包含 `claim_id + axis_id + 可重放文档片段/内部 claim 引用`；跨 epoch 一致性检查是硬规则，基于证据集签名和 `tau = max(tau_floor, 2*epsilon)`；认识论诚实性通过 `AxisScoreEntry.source_kind + effective_epsilon + epistemic_flags` 暴露给 PA。**

这套东西能实现，接口闭合，失败路径明确，不靠“LLM 综合判断”糊墙。

如果你要，我下一条可以直接把这份规范收敛成：
1. protobuf / JSON Schema  
2. `AxisScoringEngine.compute()` 伪代码  
3. `has_ranking_change()` 如何接 `effective_epsilon` 的具体签名。

---


### [8] Gemini-3.1-Pro

*2026-03-09T18:59:44.943332*

作为 v3 框架的核心设计者，我必须终结关于「黑盒评分」与「硬编码规则」之间的无效拉锯。GPT-5.4 的方案试图通过 Layer 1 下发静态 `axis_rulebook` 来解决可审计性，这在**动态生成评估维度**的开放域认知场景下是逻辑死锁。

以下是 Layer 2 `axis_scores` 产出机制的最终设计规范。

### 1. 核心决策立场 (I/J/K/L)

*   **问题 I（产出方式）：严格两阶段协议。** LLM 仅作为「语义传感器」将非结构化文本降维为 `EvidenceNode`（含极性和强度等级）；数值折算由 Layer 2 内置的 **MAX-SMT 聚合器**执行。
*   **问题 J（EvidenceChain）：基于 ADT 的引用追踪。** 必须区分 `EXTERNAL_DOC`（原始证据）与 `INTERNAL_CLAIM`（定理依赖），以支持**失效传播（Invalidation Propagation）**。
*   **问题 K（一致性）：$\epsilon$-耦合触发。** 漂移阈值 $\tau$ 不是魔法数字，而是动态定义的 $2 \times \epsilon$。
*   **问题 L（诚实性）：认识论解耦。** Score 表达「证据强度」（本体论），Epsilon 表达「提取噪声」（认识论）。LLM 的犹豫（Confidence 低）只增加 Epsilon，不降低 Score。

---

### 2. EvidenceChain 与 EvidenceNode 类型定义

```typescript
type EvidenceRef = 
  | { kind: "EXTERNAL_DOC"; doc_id: string; span_hash: string; uri: string }
  | { kind: "INTERNAL_CLAIM"; claim_id: string; epoch: number; status: "VERIFIED" | "DEFENSIBLE" };

type StrengthTier = "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL" | "AXIOMATIC";

interface EvidenceNode {
  node_id: string;
  ref: EvidenceRef;
  axis_mapping: {
    axis_id: AxisId;
    relevance: number; // ∈ [0, 1]，LLM 判定该证据与轴的相关度
  };
  polarity: "PRO" | "CON";
  tier: StrengthTier;
  llm_confidence: number; // LLM 对该提取动作的自我评价 ∈ [0, 1]
}

interface EvidenceChain {
  nodes: EvidenceNode[];
  provenance: "LLM_EXTRACTED_RULE_SCORED";
  last_updated_epoch: number;
}
```

**不变式约束**：
1. `INTERNAL_CLAIM` 引用必须指向已存档的 epoch。
2. 若引用的 `claim_id` 在当前 epoch 变为 `SUSPENDED`，引用该节点的 `EvidenceNode` 必须在重算逻辑中被标记为 `INVALID`。

---

### 3. S2/S4/S5 节点处理协议与 axis_score 产出公式

**两阶段执行流**：
1.  **阶段 1 (LLM)**: 输入 `TestableClaim` + 检索上下文，输出 `EvidenceNode[]`。
2.  **阶段 2 (聚合器)**: 
    *   从 `QuestionFrame` 获取 `tier_weights: Record<StrengthTier, number>` (默认值: Anecdotal=0.2, Causal=0.8, Axiomatic=1.0)。
    *   **计算本体论分数 (Score)**:
        $S_{pro} = \max(\{node.tier\_weight \times node.relevance \mid node.polarity = PRO\})$
        $S_{con} = \max(\{node.tier\_weight \times node.relevance \mid node.polarity = CON\})$
        $axis\_score = 0.5 + 0.5 \times (S_{pro} - S_{con})$
    *   **计算认识论误差 (Epsilon)**:
        $\epsilon_{base} = 0.1$ (系统基线)
        $\epsilon_{noise} = \sum (1 - node.llm\_confidence) / n$
        $axis\_epsilon = \epsilon_{base} + \gamma \times \epsilon_{noise}$

**输出类型**：`VerifiedClaim` 包含 `axis_scores: Record<AxisId, number>` 和 `axis_epsilons: Record<AxisId, number>`。

---

### 4. 跨 Epoch 一致性检查与消费侧（PA）协议

**漂移监测机制**：
在 Layer 2 产出 `VerifiedClaim` 前执行：
```typescript
const drift_delta = Math.abs(current_score - last_epoch_score);
const threshold = 2 * current_epsilon;
if (drift_delta > threshold) {
  claim.drift_flag = true;
  claim.epsilon_penalty = drift_delta; // 惩罚项
}
```

**消费侧（PA 节点）协议**：
PA 节点在计算 `has_ranking_change()` 的排序稳定性时，使用的有效 $\epsilon$ 为：
$\epsilon_{eff} = axis\_epsilon + (drift\_flag ? epsilon\_penalty : 0)$
这确保了**标注噪声大的 claim 在排序中具有更高的不确定性**，从而阻止 Layer 1 过早终止。

---

### 5. 对 GPT-5.4 方案的精确攻击

**攻击点 1：`axis_rulebook` 的来源死锁。**
GPT-5.4 提出规则由 Layer 1 下发：`QuestionFrame.axis_rulebook`。但 v3 的核心价值在于其处理开放问题的能力。在用户输入「远程办公对心理健康的影响」时，`mental_health` 这个轴是动态生成的，Layer 1 根本没有预定义的 `tier_score`。
**结论**：GPT-5.4 的方案只能处理已知领域，无法处理认知边界的扩张。我的方案通过通用的 `StrengthTier`（强度等级）进行语义降维，解决了动态轴的评分映射问题。

**攻击点 2：忽略了「失效传播」的拓扑结构。**
GPT-5.4 将证据简化为 `EvidenceAtom`，却没定义当 `ref` 对应的内部命题被推翻时，分值如何自动回滚。
**结论**：没有 MAX-SMT 式的局部重算，系统在多轮迭代后会积累大量的僵尸分数。我的 `EvidenceRef` ADT 强制了引用完整性。

---

### 6. 端到端运行 Trace

1.  **输入**: `TestableClaim`: "微服务架构将部署频率提升 3 倍", `Axis`: "交付速度"。
2.  **S2 (Depth)**: LLM 发现证据 E1 ("某大厂案例，提升 4 倍")。
    *   `EvidenceNode`: {PRO, CAUSAL_STATISTICAL, confidence: 0.9}
    *   `axis_score`: $0.5 + 0.5 \times (0.8 - 0) = 0.9$
    *   `epsilon`: $0.1 + 0.1 \times (1 - 0.9) = 0.11$
3.  **S4 (DepthProbe)**: 发现反证 E2 ("某团队迁移后因测试链条长，频率下降 20%")。
    *   `EvidenceNode`: {CON, ANECDOTAL, confidence: 0.95}
    *   **聚合重算**: $S_{pro}=0.8, S_{con}=0.2$
    *   `axis_score`: $0.5 + 0.5 \times (0.8 - 0.2) = 0.8$
    *   `epsilon`: $0.1 + 0.1 \times \text{mean}(0.1, 0.05) = 0.1075$
4.  **Epoch N+1**: E1 所在的原始文档被标记为「过时」。
    *   **失效触发**: E1 从链中剔除。
    *   `axis_score`: $0.5 + 0.5 \times (0 - 0.2) = 0.4$ (评分大幅逆转)
    *   **一致性检查**: $|0.4 - 0.8| > 2 \times 0.1075$，触发 `drift_flag`。
    *   **PA 消费**: 该 claim 的 $\epsilon$ 激增，导致排序不稳定，Layer 1 判定 `has_ranking_change = True`，继续迭代。

---

### 7. 可推翻条件

我的方案在以下场景下失败：
1.  **语义重叠陷阱**：LLM 将同一份原始证据在不同 epoch 映射到了语义极其接近但 ID 不同的 `AxisId` 上，导致 `axis_score` 在不同轴之间「跳跃」而非「漂移」。
2.  **强度等级坍塌**：如果所有证据都被 LLM 标注为最高的 `AXIOMATIC` 级别，MAX-SMT 聚合器将失去区分度，退化为简单的极性计数器。

**接受推翻的数据**：若在 1000 次运行实验中，`drift_flag` 的触发有 >30% 是由于 Axis 语义对齐失败而非证据变化，则证明两阶段协议中的语义降维层需要引入更强的 Ontology 约束。

---


### [9] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-09T19:11:27.222137*



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

---
