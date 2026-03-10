---
title: "v3 认知引擎：续跑机制的设计"
rounds: 3
cross_exam: true
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
      你是一位极端工程务实主义者，背景类似 Linus Torvalds。

      你的核心判断标准：任何"机制"必须说清楚——触发条件是什么、外部写入哪个文件或字段、系统
      下一步如何读取并合并、失败时如何回滚。没有可操作接口定义的"设计"就是白板涂鸦。

      你对本议题的具体关切：
      - v3 是有强类型内部结构的系统（QuestionFrame、HypothesisDraft、TestableClaim、
        GapSpec、EngineSnapshot），任何"续跑"都必须在这些类型约束下进行
      - 人类不懂 gap_id 或 draft_id，所以必须有可读性层，但可读性层不能变成接口本身
      - "v2 追加式 log"在 v3 语境下意味着什么？LLM 如何把自然语言描述可靠地映射回
        GapSpec 或 TestableClaim 的强类型字段？这个映射的错误率是多少？
      - 如果干预文件写错了（比如 deny 了一个不存在的 gap_id），系统应该怎么处理？
        silently ignore 还是 hard fail？这个错误处理本身就是设计的一部分

      攻击风格：要求对手给出具体的接口定义（TypeScript 类型或 Python dataclass）、
      写入路径、读取时机、以及至少一个"用户写了 X，系统做了 Y"的具体 trace。
      对"让 LLM 来处理歧义"的回答要追问"LLM 处理失败时系统状态是什么"。

  - name: Gemini-3.1
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 v3 框架的设计者，具有形式化方法研究背景（CEGAR/MAX-SMT）。

      你完整掌握 v3 已确立的架构，熟悉所有辩论裁定的细节。你的核心设计哲学是：
      尽量最小化改动已有系统，在系统外部增加协议层，而不是把接口侵入到系统内部。

      你的关切：
      - v3 的内部结构已经非常完备（七节点状态机、Layer 2 验证链、Epoch 循环），
        续跑机制应该作为"系统外的外壳"而非修改系统内部
      - 人类干预的粒度问题：太细（直接操作 gap_id）则用户负担过重；太粗（自然语言）
        则映射不可靠。中间地带在哪里？
      - EngineSnapshot 的设计：需要记录哪些状态才能完整恢复？不需要的状态记录下来是
        负担
      - Epoch 边界是自然的暂停点，但 Epoch 之间的状态迁移有哪些不可见的依赖？
        （例如 ChallengeTracker 的 stage 状态机、rejection_history、open_term 演化）

      你最不确定的点：
      - 如果人类在 intervention.json 里表达了"某个方向不重要"，这如何转化为对
        GapSpec.blocks_termination 的影响？是直接修改该字段，还是通过注入一个
        "无证据"的反向 claim 让系统自然收敛？
      - 续跑后的 epoch 编号应该如何维护？从 0 重新开始还是继续递增？这对
        ChallengeTracker 的历史窗口（最近 10 轮）有什么影响？

      攻击风格：追问对手方案在 Epoch 边界处的状态一致性。对"用户操作文件"的方案
      要追问"用户操作完后系统如何验证文件的合法性"。对"LLM 解析"方案要追问
      "解析结果与内部状态的类型对齐如何保证"。

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。

  禁止：
  - 纯原则性陈述——每个设计主张必须伴随至少一个具体的接口定义、文件格式或状态转移条件
  - 稻草人攻击——交叉质询中必须引用对手的具体文本或接口定义
  - 重新讨论已裁定的 v3 架构细节（Layer 1 七节点状态机、Layer 2 验证链、GapSpec 强类型、
    TestableClaim 格式、has_ranking_change() 终止条件等）
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对某个核心设计问题的明确立场（有接口类型或具体格式支撑）
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）
  3. 所有主张必须附可推翻条件（什么反例能推翻你的设计选择）

round1_task: |
  第一轮：选择你认为最关键的设计问题，给出完整立场。

  必须包含：
  1. 你主张的续跑机制的核心接口——写入格式（JSON/YAML/Markdown）、写入时机、
     系统读取时机、状态合并方式
  2. 支撑该选择的最强论据——含至少一个具体场景：用户想表达"某个方向不重要"时，
     从用户操作到系统状态变更的完整步骤
  3. 你方案的已知弱点及缓解措施
  4. 对至少一个对手可能立场的预攻击

middle_task: |
  中间轮：吸收前一轮攻击后的回应与深化。

  必须包含：
  1. 回应对你方案的最强攻击——明确承认击中的部分，精确反驳打偏的部分
  2. 给出 EngineSnapshot 的最小可行类型定义：记录哪些字段、不记录哪些字段、理由
  3. 处理以下具体场景：
     - 用户写了一条无效干预（如引用了不存在的 gap_id），系统如何响应
     - 续跑后 has_ranking_change() 的历史窗口如何处理（继承还是重置）
  4. 给出一个 15 行以内的端到端 trace：从"系统在 Epoch 3 终止"到"用户写了干预"
     到"Epoch 4 开始执行"

final_task: |
  最终轮：给出完整的续跑机制提案。

  必须包含：
  1. 完整的接口规范：EngineSnapshot 类型、InterventionFile 格式、读写时机、
     验证协议、合并逻辑
  2. 续跑与 v2 追加式 log 方式的精确对比：各自的适用场景、精度-便利权衡表
  3. 人类可读性层的设计：如何让用户在不了解 gap_id 的情况下做出有意义的干预
  4. 你方案最可能在什么场景下失败（给出具体输入），以及接受什么样的反例来推翻设计

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**
  - 对每个核心设计问题用日常语言解释裁定结果
  - 每个裁定必须包含至少一个具体例子：当用户想做出某种干预时，这个设计选择
    会导致什么具体的行为差异
  - 风格参考：用侦探办案、工厂流水线、档案管理等比喻让非技术人员理解
  - 明确说明哪些场景下裁定可能需要修正
  - 每个问题以「一句话总结」结尾

  **第二部分：可实现性摘要**
  - EngineSnapshot 的最终类型定义（TypeScript）
  - InterventionFile 的最终格式规范（JSON Schema 或 TypeScript）
  - 人类可读性层的接口规范（从 snapshot 生成可读摘要的函数签名）
  - 状态合并算法的伪代码骨架（apply_intervention(snapshot, intervention) 的逻辑）
  - 一个完整的端到端 trace：Epoch N 终止 → 生成 snapshot → 用户编写干预 →
    系统验证 → Epoch N+1 启动
  - 标注实现难度最高的 3 个子问题及其风险

  对每个核心设计问题必须给出明确的最终裁定，不得搁置。
---

# v3 认知引擎：续跑机制的设计

## 一、系统背景：v3 认知引擎完整介绍

本议题建立在 v3 认知引擎架构的完整基础上。以下是对整个系统的完整介绍，读者无需阅读其他文
件即可理解系统的所有相关细节。

---

### 1.1 系统目标

v3 认知引擎的目标是：给定一个开放式、有争议的问题（如"AI 应该开源吗"、"远程办公是否提高生
产力"、"最优数据库索引策略是什么"），系统能产出一个**多视角、辩护完备的答案体系**，而不是
单一的是/否结论。

核心挑战在于：真正困难的问题往往是"连问题本身是什么都不清楚"——问题中的关键词没有精确定义、
评估维度不明确、不同利益相关方持有根本不同的立场。系统必须先把问题结构化，再展开探索。

---

### 1.2 两层架构总览

v3 框架采用**两层分离架构**：

**Layer 1（问题级处理层）**——七节点状态机，节点序列为：
```
QN（QuestionNormalizer）
  → MB（MacroBreadth）
  → CC（ClarityCompiler）
  → D2（Layer2Dispatch）
  → PA（PrecisionAggregator）
  → RB（RepairBreadth，可选）
  → AS（AnswerSynthesis）
```

**Layer 2（命题级处理层）**——多状态验证机，处理每一个具体的 TestableClaim：
```
S1(Clarify) → S2(Depth) → S3(Precision)
  → S4(DepthProbe) ↔ S5(BreadthProbe)
  → S6(Verified) | S7(Suspended) | S9(SchemaChallenge)
```

Layer 1 负责「发散思考」——把开放问题分解为多条可验证的候选命题。
Layer 2 负责「严格验证」——对每条命题进行深度追溯和精度冲突检测。

两层通过 **Epoch 循环**交互：Layer 2 完成一批命题的验证后，通过 `L2Return` 结构向 Layer 1
报告结果（包括新发现的知识缺口和框架挑战），Layer 1 据此决定是否继续探索或终止。

---

### 1.3 Layer 1 关键组件详细说明

#### 1.3.1 QN 节点：normalize_question()

**输入**：`ProblemStatement { raw_question: string; context?: string; user_constraints?: string[] }`

**输出**：`Result<QuestionFrame, NormalizeError>`

**核心类型**：

```typescript
type RegulativeAxis = {
  axis_id: string;
  label: string;
  mode: "regulative";          // 永远只能是 "regulative"，不可能是 "constitutive"
  falsifier: string;           // 可操作的反证描述
  falsifier_independence: "INDEPENDENT" | "STAKEHOLDER_DERIVED";
  // 用于决定该轴在 MB 中进入哪个 tier（内部层 vs 经验层）
};

type QuestionFrame = {
  problem_id: string;
  canonical_question: string;
  scope: string;               // 问题的适用范围（时间、地域、人群等）
  stakeholders: string[];      // 利益相关方列表
  evaluation_axes: [RegulativeAxis, ...RegulativeAxis[]];
  // ↑ 非空元组，Ok(QuestionFrame) 保证 length >= 1
  excluded_forms: CategoryErrorTag[];  // 标记问题中的认识论非法形式
  open_terms: string[];        // 问题中出现但尚未被精确定义的关键概念
};
```

**失败分类**：
- `NormalizeFatal`：范畴错误（自指悖论、对抽象实体赋予非经验属性、不可证伪的价值断言、
  无界范围），**终止整个处理流程**
- `NormalizeRecoverable`：信息不足（空轴、scope 过宽），**进入精炼回路**，最多重试
  `max_refinement_epochs`（默认 3）轮；超过后升级为 `NormalizeFatal(REFINEMENT_EXHAUSTED)`

**`CategoryErrorTag` 的判定算法**（已裁定）：
- `SELF_REFERENCE_PARADOX`：纯规则判定（自指锚点 + 真值否定谓词 + 同一子句 + 排除元讨论）
- `NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`：公理化核心词表（数字/集合/函数/命题/定理/
  证明）+ 非经验谓词词表直接谓述
- `UNFALSIFIABLE_VALUE_ASSERTION`：规则先筛（价值词 + 比较级 + 无经验锚点）+ 桥接模板匹配
  双票制
- `SCOPE_UNBOUNDED`：广域量词 + 非研究问法 + 缺失 ≥ 3 个边界维度（人群/时间/地点/指标）

**open_terms 处理原则**（已裁定）：`open_terms` 是流水线的共享警报信号——MB 看到它会标记
风险但不改变生成行为，CC 看到它会硬拦截（`UNBOUND_OPEN_TERM`），QN 接收 CC 反馈后尝试将
open term 降解为评估轴或 scope 约束（"概念降解"）。

#### 1.3.2 MB 节点：macro_breadth()

**输入**：`(frame: QuestionFrame, config?: MacroBreadthConfig, external_positions?: ExternalPosition[])`

**输出**：`Result<HypothesisDraft[], MacroBreadthError>`

**张力源分类**（三种，已裁定）：
- `EXTERNAL_POSITION`：来自外部已知立场或文献
- `STAKEHOLDER_CONFLICT`：来自利益相关方之间的利益冲突
- `EVALUATION_AXIS_SPLIT`：来自评估维度内部的分裂（一个轴上存在对立解读）

**选择策略**（分层配额制，已裁定）：
- 内部层（`INTERNAL_AXIS` tier）：轴的 `falsifier_independence = "INDEPENDENT"` 时进入，
  配额占 `max_drafts` 的上半部分
- 经验层（`EMPIRICAL` tier）：其他情况，配额占下半部分
- 贪心去重：通过 `is_homologous()` 动态计算同源性（不是预标记），防止知识空间重叠

**关键不变式**：
- `INV-5`：`Ok` 时 `drafts.length ∈ [1, config.max_drafts]`
- `INV-6`：`Ok` 时不存在两个草稿互相同源
- `INV-7`：`Ok` 时高风险（含未绑定 open_term）的草稿占比不超过 `max_open_term_risk_ratio`
- `INV-8`：`Err` 时返回结构化错误，不产出空数组

#### 1.3.3 CC 节点：clarity_compile()

**输入**：`(draft: HypothesisDraft, frame: QuestionFrame)`

**输出**：三路互斥结果（已裁定）：
```typescript
type CompileResult =
  | { kind: "TESTABLE_CLAIM"; claim: TestableClaim }
  | { kind: "REGULATIVE_IDEA"; idea: RegulativeIdea }
  | { kind: "COMPILE_ERROR"; error: CompileError };
```

**核心类型**：

```typescript
type TestableClaim = {
  claim_id: string;
  problem_id: string;
  claim: string;            // 精确的单一可检验命题
  scope: string;
  assumptions: string[];
  falsifier: string;        // 可操作的反证条件
  non_claim: string[];      // 明确声明未主张什么
  verifier_requirements: string[];
  accept_test: AcceptTest;  // 机器可检查的判定谓词
  provenance_draft_id: string;
};

type RegulativeIdea = {
  idea_id: string;
  statement: string;
  domain_kind: "empirical" | "normative" | "interpretive" | "mixed";
  reason_no_schema: "NO_BRIDGE_TO_OBSERVABLE" | "ONLY_PRAGMATIC_PROTOCOL";
  decomposition_hints: string[];  // 可能的子命题拆解方向，供 RB 节点消费
  stage_trace: StageTrace;
};
```

**编译流水线**（四阶段）：结构提取 → 单一命题检查（`MULTI_PROPOSITION`）→ 证伪器合成
（`synthesize_falsifier()`）→ 接受测试降格（`lower_accept_test()`）

**Protocol 库**（五种已裁定）：`empirical_test_v1`、`normative_eval_v1`、
`interpretive_consensus_v1`、`institutional_audit_v1`、`meta_methodology_v1`

**HypothesisDraft 统一类型**（已裁定）：MB 草稿和 repair 草稿共用一个类型，生命周期
字段（`ttl`、`repair_stage`）放在 `provenance` 子结构中：

```typescript
interface HypothesisDraft {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  scope_ref: string[];          // 必填，禁止空数组
  verifier_hint: string[];
  open_term_risk: string[];
  tension_source: TensionSource;
  provenance: {
    source: "MB" | "REPAIR";
    epoch: number;
    ttl?: number;               // 仅 MB 草稿使用
    source_gap_id?: string;     // 仅 REPAIR 草稿使用
    source_challenge_id?: string;
    repair_stage?: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
  };
}
```

#### 1.3.4 repair() 三级精化状态机

**触发条件**：Layer 2 返回 `L2Return`，其中包含 `new_gaps: GapSpec[]` 和
`schema_challenges: SchemaChallengeNotice[]`。

**三级精化状态**（已裁定，对每个 challenge 独立维护）：

| 阶段 | 策略 | 推进触发条件 |
|------|------|-------------|
| `STRICT` | `suggested_dimension` 作为硬约束 | 连续 1 轮该 challenge 产出的草稿 100% 被 `is_homologous()` 过滤 |
| `RELAXED` | `suggested_dimension` 作为软约束（允许放宽 scope、翻转 polarity、替换 outcome）| 同上 |
| `ADJACENT` | `suggested_dimension` 仅作为锚点，允许滑移到语义相邻维度 | 同上 |
| `EXHAUSTED` | 该 challenge 的精化循环终止 | — |

**`is_homologous()` 判定**（已裁定，二值输出）：基于 `provenance_family`（分流条件）+
`scope_tokens`（Jaccard）+ `outcome_anchor`（同义词归一化）+ `polarity` + `verifier_tokens`
（Jaccard）的复合判断。同源家族阈值较松（scope ≥ 0.80，verifier ≥ 0.75），异源家族阈值极严
（scope ≥ 0.95，verifier ≥ 0.90）。

#### 1.3.5 PA 节点：终止判定

**终止条件**（双层，已裁定）：
1. `has_ranking_change() == False`（连续 `hysteresis_rounds`（默认 2）轮 Top-K 集合不变且
   分数漂移在 `score_delta` 以内）
2. 且不存在阻塞性 `GapSpec`（`blocks_termination: true` 的）

**评分公式**（已裁定）：
```
score = base * quality * coverage^GAMMA
其中：
  covered_axes = claim 覆盖的轴集合
  coverage = Σ(axis.weight for axis in covered_axes)
  base = Σ(axis.weight * claim.axis_scores[axis]) / coverage（局部归一化）
  quality = status_factor(claim.status) * (1 - residual_risk)
  GAMMA = 0.5（覆盖率惩罚指数）
```

**阻塞性 GapSpec 条件**（已裁定）：

| GapKind | 阻塞条件 |
|---------|----------|
| `UNCOVERED_HIGH_WEIGHT_AXIS` | 该轴 weight > max(已覆盖轴 weight) × 50% |
| `UNRESOLVED_DEFEATER` | 反证针对当前 Top-K 中的 claim |
| `EVIDENCE_CONFLICT` | 同一轴上两个 VERIFIED claim 方向相反 |
| `WEIGHT_UNDERSPECIFIED` | 超过 30% 的权重质量未被声明 |

**`EvaluationAxis.epsilon` 冷启动**（已裁定）：根据验证方法类型确定——形式验证：0.05；人类
判断型：0.15；混合型：0.10。前 3 轮（epoch < 4）完全静态，之后基于 t-分布 95% 置信区间半宽
更新，限制在初始值 [0.5x, 2.0x] 范围内。

---

### 1.4 Layer 2 关键组件：axis_scores 产出协议

**两阶段协议**（已裁定）：
- **阶段 A（LLM 语义降维）**：LLM 阅读外部文档，产出 `EvidenceAtomCandidate[]`，每个
  Atom 只挂一个 axis（一 atom 一 axis 原则），标注极性（PRO/CON）和强度等级
  （ANECDOTAL/CORRELATIONAL/CAUSAL_STATISTICAL/AXIOMATIC），**不得输出数值分数**
- **阶段 B（规则引擎折算）**：根据 `axis_rulebook`（或默认阶梯值）将 atom 聚合为
  `AxisScoreEntry`，公式为 `score = sigmoid_normalized(raw_pro - raw_con)`

**默认阶梯值**：ANECDOTAL→0.15, CORRELATIONAL→0.40, CAUSAL_STATISTICAL→0.75, AXIOMATIC→0.95

**认识论诚实性**（已裁定）：`epsilon`（测量不确定性）与 `score` 严格解耦——LLM 的置信度
只影响 epsilon，不降低 score。epsilon = base_epsilon + noise_term（由 LLM 置信度加权推导）
+ provenance_penalty（使用默认规则时 +0.05）。

---

### 1.5 Epoch 循环与 L2Return 反馈路径

**Epoch 循环**是 v3 系统的核心执行单元：

```
Epoch N:
  1. MB 产出 HypothesisDraft[]
  2. CC 编译为 TestableClaim[] + RegulativeIdea[]
  3. D2 将 TestableClaim[] 派发到 Layer 2
  4. Layer 2 执行 S2/S4/S5 验证链
  5. Layer 2 返回 L2Return:
     {
       verified_claims: VerifiedClaim[];
       suspended_claims: string[];
       new_gaps: GapSpec[];           // ← 触发 repair()
       schema_challenges: SchemaChallengeNotice[];  // ← 触发 repair()
       ranking_delta: { changed: boolean };
       epoch_id: number;
     }
  6. PA 接收 L2Return，计算 should_terminate()
     - 如果 terminate: true → 进入 AS 节点输出答案
     - 如果 terminate: false → repair() 产出新草稿 → Epoch N+1
```

**`new_gaps`** 来源：Layer 2 在 S4（DepthProbe）和 S5（BreadthProbe）阶段发现的知识缺口，
类型为 `GapSpec { gap_id, kind, discriminator?, evidence_summary, blocks_termination }

**`schema_challenges`** 来源：Layer 2 检测到命题框架需要修正时产出，类型为
`SchemaChallengeNotice { challenge_id, trigger, suggested_dimension?, description }`

**终止是单向吸收态**：一旦 `terminate: true`，系统进入 AS 输出阶段，不再接受新的 epoch。

---

### 1.6 全流程类型系统汇总

```typescript
// === 核心流水线类型 ===

interface L2Return {
  verified_claims: VerifiedClaim[];
  suspended_claims: string[];
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  ranking_delta: { changed: boolean; details?: string };
  epoch_id: number;
}

interface GapSpec {
  gap_id: string;
  kind: "MISSING_DISCRIMINATOR" | "MISSING_OBSERVABLE"
      | "PREMISE_UNDERSPECIFIED" | "UNCOVERED_HIGH_WEIGHT_AXIS"
      | "UNRESOLVED_DEFEATER" | "EVIDENCE_CONFLICT"
      | "WEIGHT_UNDERSPECIFIED" | "UNCLASSIFIED";
  discriminator?: string;
  evidence_summary: string;
  blocks_termination: boolean;  // 是否阻塞终止判定
  axis_id?: string;             // 涉及的评估轴（如果适用）
}

interface SchemaChallengeNotice {
  challenge_id: string;
  trigger: "REPLAY_REGRESSION" | "COVERAGE_GAP" | "ANOMALY";
  suggested_dimension?: string;
  is_homologous: boolean;
  description: string;
}

interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<string, number>>;
}

interface ChallengeTracker {
  challenge_id: string;
  current_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
  consecutive_filtered_epochs: number;
  attempted_scopes: string[];
  attempted_outcomes: string[];
  attempted_polarities: (1 | -1 | 0)[];
}

interface EvaluationAxis {
  axis_id: string;
  label: string;
  mode: "regulative";
  falsifier: string;
  falsifier_independence: "INDEPENDENT" | "STAKEHOLDER_DERIVED";
  weight: number;    // 归一化权重，所有轴 weight 之和 = 1.0
  epsilon: number;   // 测量不确定性 ∈ [0, 1]，由轴类型冷启动确定
}
```

---

## 二、当前续跑能力的缺口

### 2.1 v3 是一个完全内部闭环的系统

v3 所有状态变更路径均为内部闭环：

- **QN → MB → CC → D2 → PA → RB** 是自动执行的单向流水线
- **Epoch 循环**是由 `should_terminate()` 自动控制的——满足条件就终止，不满足就继续
- **repair()** 的生成策略由 `ChallengeTracker` 的状态机自动推进
- **GapSpec.blocks_termination** 由系统根据规则自动判定

在当前设计中，**没有任何外部介入接口**。一旦启动，系统自主运行直至终止。

### 2.2 没有显式的 EngineSnapshot 类型

v3 的每个子结构都有强类型：
- `QuestionFrame` 保存问题的结构化表示
- `TestableClaim[]` 保存当前的可验证命题集
- `GapSpec[]` 保存当前的知识缺口集
- `ChallengeTracker[]` 保存每个 challenge 的精化状态
- `VerifiedClaim[]` 保存验证结果和分数

但是，**没有一个顶层的统一快照类型**将上述所有子状态聚合在一起。要"暂停"系统并在之后"续
跑"，需要保存的东西分散在多个数据结构中，它们之间还存在依赖关系（例如 `ChallengeTracker`
依赖 `rejection_history`，`EvaluationAxis.epsilon` 有自己的演化历史）。

### 2.3 终止是单向吸收态

`has_ranking_change() == False && !blocking_gaps` 是终止的充分条件，触发后进入 AS 输出，
**不可回退**。如果用户认为系统终止太早（例如某个重要方向根本没被探索到），当前没有"重新激
活"的机制——只能从头运行。

### 2.4 人类干预的对象是强类型内部结构

即使有了续跑机制，人类的干预也面临一个根本挑战：v3 的内部对象都有 ID（`gap_id`、
`challenge_id`、`claim_id`、`axis_id`），人类需要引用这些 ID 才能做出精确干预。但用户在
运行时并不知道这些 ID 的存在，也不清楚它们的语义。

---

## 三、对比 v2 的续跑方式

### 3.1 v2 续跑机制

v2 的续跑机制极其简单：
- **追加式 log**：每次运行将所有辩论轮次输出追加到一个 Markdown 文件（`*_debate_log.md`）
- **`--resume` 标志**：使用 `--resume` 时，系统将已有 log 文件的全部内容作为上下文前缀
  注入，LLM 从这个上下文中自然语言地"重推"系统状态
- **人类可手动编辑 log**：用户可以直接在 log 文件末尾添加文字（例如"请注意：X 方向已经
  在另一个研究中被证伪了"），LLM 会在续跑时将其纳入上下文

### 3.2 v2 方式的优点

- **零改造**：流程层面完全不需要修改，log 就是上下文，上下文就是状态
- **人类友好**：用户用自然语言写，不需要了解任何内部结构
- **透明性高**：log 文件本身就是可读的历史记录

### 3.3 v2 方式的缺点

- **无结构化状态**：LLM 从全文上下文重推状态，无法保证与原始运行的精确延续性。新 epoch 的
  行为完全依赖 LLM 对 log 的解读，可能产生漂移
- **状态不可验证**：无法机器验证"当前状态是否与第 N 轮结束时的状态精确一致"
- **干预精度有限**：人类想表达"deny gap_001 的重要性"时，只能写自然语言，系统不知道这是
  否精确对应某个 `GapSpec` 的 `blocks_termination` 字段
- **上下文膨胀**：随着 epoch 增多，log 文件越来越大，LLM 的上下文窗口压力增大，后期的续跑
  质量可能下降

---

## 四、核心设计挑战（开放性，不预设答案）

### 挑战 P：如何在不改动系统内部逻辑的前提下支持续跑？

v3 的内部逻辑（七节点状态机、Epoch 循环、repair() 三级精化、has_ranking_change() 终止
判定）已经经过多轮辩论裁定，不应该轻易改动。续跑机制是否可以完全作为"系统外的外壳"来实现？

具体来说：
- 如果在 Epoch N 终止时将系统状态序列化到外部文件，在 Epoch N+1 开始时反序列化，是否可以
  做到"对内部逻辑完全透明"？
- 内部逻辑有哪些隐含的"全局状态"（例如 `rejection_history`、epsilon 演化历史）必须被
  序列化？如果遗漏了某个字段，续跑会不会产生微妙的不一致？
- `ChallengeTracker` 的 `consecutive_filtered_epochs` 计数器应该怎么处理？续跑时是继承
  还是重置？继承意味着用户干预前的"被过滤"历史影响续跑行为，重置意味着可能重走已经失败的路

### 挑战 Q：人类如何给出精确的结构化反馈？

v3 的内部结构使用 ID（`gap_id`、`challenge_id`、`claim_id`）来索引对象。人类干预的精度
取决于能否正确引用这些 ID。

具体来说：
- 如果人类想说"我认为'任务耦合度'这个方向不重要，系统不需要继续探索"，他需要知道
  对应的 `GapSpec` 的 `gap_id` 是什么。但用户在运行时并不知道
- 如果系统生成了一个"human-readable 摘要"（例如"当前有 3 个知识缺口：(1) 缺少任务耦合
  度分析 (2) 缺少跨时区场景验证 (3) 缺少统计显著性证据"），用户能否通过这个摘要准确地对应
  到内部 ID？
- 有没有可能通过"自然语言匹配"将用户的自然语言描述映射到具体的 gap_id？这个映射的
  错误率是多少？错误的映射会导致什么后果？

### 挑战 R：如何让反馈和系统状态的融合尽量简单？

v3 系统的强类型约束是其可靠性的来源，但也使得外部干预变得困难。

具体来说：
- 如果用户修改了 `GapSpec.blocks_termination = false`（表示"这个缺口不重要，不需要阻塞
  终止"），系统在下一个 epoch 开始时应该如何处理？是直接采用修改后的值，还是需要验证这
  个修改的一致性（例如检查是否有其他依赖这个 gap 的 claim）？
- 如果用户注入了一条新的 `TestableClaim`（声称"某方向已经有了充分证据"），Layer 2 是否
  需要重新验证这条 claim？如果不验证，系统的"认识论诚实性"是否受损？
- 合并逻辑是否需要处理冲突？（例如用户 deny 了某个 gap，但系统内部有一个 claim 依赖这个
  gap 的存在才有意义）

### 挑战 S：精度 vs 便利的权衡

v2 的非结构化追加和假想的完全结构化接口是两个极端。这两者之间是否存在中间地带？

具体来说：
- "结构化锚点"方案：保持 v2 的自然语言追加，但增加一种特殊标注语法（例如
  `[HUMAN: gap:gap_001 importance=low]`），系统解析这些标注而不是从全文重推状态。这种
  半结构化方案能否兼顾可读性和精度？
- 如果系统在每个 epoch 结束时输出一个"human-readable 摘要 + 可选干预菜单"，用户可以选择
  "继续"、"否定某个缺口"或"注入新证据"，这种交互式 epoch 边界是否比静态文件更自然？
- 结构化接口的维护成本：如果 v3 内部类型（如 `GapSpec` 的字段）发生变化，外部干预格式需要
  同步更新，谁来维护这个同步关系？

---

## 五、可能的方向（提示性，不强制）

以下方向作为启发性提示，不是"候选方案 A/B/C 选哪个"，辩手应当从工程原理出发自行判断和
构建立场。

### 方向一：快照 + 干预文件

每个 epoch 结束时写出 `EngineSnapshot.json`，包含当前 epoch 编号、所有 TestableClaim、
所有 GapSpec（含 blocks_termination 状态）、所有 ChallengeTracker 状态、当前 Top-K 排序、
epoch 历史等。

人类编写 `intervention.json`，支持若干操作类型，例如：
- `DENY_GAP`：声明某个 GapSpec 不再重要（修改 `blocks_termination = false`）
- `INJECT_EVIDENCE`：为某个 claim 注入新的 axis_score 或证据引用
- `OVERRIDE_SCORE`：直接修改某个 claim 的 axis_score（并标注为 `HUMAN_OVERRIDE`）
- `RESET_CHALLENGE`：将某个 ChallengeTracker 重置到 `STRICT` 阶段
- `ADD_CONSTRAINT`：向 QuestionFrame 注入额外的 scope 约束或 evaluation_axis

系统在下一个 epoch 开始时读取 `intervention.json`，验证合法性，应用到 EngineSnapshot，
然后从修改后的快照恢复状态继续执行。

**待讨论**：EngineSnapshot 的最小可行字段集是什么？哪些字段必须序列化，哪些可以重新计算？
干预文件的验证协议是什么？人类如何知道 gap_id？

### 方向二：自然语言注解层

类似 v2，但为特定内部对象提供结构化"锚点"。系统在生成 log 时，在每个 GapSpec 的描述旁
边标注其 gap_id（例如 `<!-- gap:gap_001 -->`）。用户在 log 文件中添加注释时，可以使用
这些锚点（例如 `[HUMAN: gap:gap_001 不再重要]`），系统在续跑时解析这些标注而不是让 LLM
从全文重推。

优点：保持了 v2 的自然语言友好性，同时为精确干预提供了路径。
缺点：需要定义锚点语法、解析规则和错误处理。用户可能不使用锚点，退化为纯 v2 自然语言。

**待讨论**：锚点语法如何设计才能既机器可解析又人类可读？锚点解析失败时系统如何响应？
哪些内部对象值得暴露锚点（gap、challenge、claim、axis）？

### 方向三：交互式 epoch 边界

每个 epoch 结束时不自动继续，而是暂停并输出"本轮进展摘要 + 可选干预菜单"，等待人类
确认或输入干预内容后继续。

菜单示例：
```
=== Epoch 3 完成 ===
当前 Top-3 结论：
  1. [0.72] 在高任务耦合团队中，远程办公降低迭代吞吐量
  2. [0.65] 在高沟通频率团队中，远程办公降低同步沟通质量
  3. [0.51] 在跨时区团队中，远程办公增加沟通延迟

待解决知识缺口（阻塞终止）：
  ● gap_001: 缺少统计显著性证据（运营成本轴未覆盖）

可选操作：
  [1] 继续 Epoch 4（自动执行）
  [2] 标记 gap_001 为非阻塞（我认为运营成本不重要）
  [3] 注入证据（手动提供 gap_001 的证据）
  [4] 终止并输出当前结论
```

**待讨论**：这种交互式模式是否与 v3 的"自动化认知引擎"目标冲突？如果 epoch 耗时较长（例
如需要几小时），等待用户输入是否合理？交互式边界是否应该是可选的（默认自动执行，用
`--interactive` 标志启用）？

### 方向四：只读 log + 插入注释（增强版 v2）

保持 v2 的 log 追加方式，但在续跑时系统首先做结构化预处理：
1. 扫描 log 中所有 `[HUMAN: ...]` 标注（包含对特定 gap/claim 的引用）
2. 尝试将这些标注解析为结构化操作（如果成功，精确应用；如果失败，退化为全文上下文）
3. 解析成功的标注作为"强约束"传递给 repair() 和 PA 节点
4. 解析失败的标注和普通自然语言一起作为"软上下文"传递给 LLM

这个方案的核心假设是：大多数时候用户不会使用锚点（退化为 v2），偶尔需要精确干预时才使用
锚点（获得 v3 级别的精度），系统应该优雅地处理两种情况。

**待讨论**：解析成功和解析失败的干预如何在同一个系统中共存？"强约束"和"软上下文"的优先
级如何处理冲突？这个方案是否引入了新的不一致性风险（用户认为做了精确干预，但解析悄悄失败了）？

---

## 六、开放性陈述

以上四个设计挑战没有显而易见的"正确答案"，每种设计选择都有合理的工程权衡。

**对于辩手**：请基于你自己的技术背景和设计哲学，就你认为最关键的问题给出具体的、可实现的
设计提案。每个主张必须给出接口定义或格式规范——不接受纯原则性陈述。

**对于整个讨论**：我们期待最终能得到以下产出：
1. `EngineSnapshot` 的完整类型定义（记录哪些字段、字段语义、哪些字段可以重新计算而不需要
   序列化）
2. 干预文件的格式规范（操作类型枚举、合法性验证协议、错误处理方式）
3. 人类可读性层的接口规范（如何将内部 ID 映射到用户可理解的描述，反向如何将用户描述映射
   回内部 ID）
4. 状态合并算法的骨架（`apply_intervention(snapshot, intervention) → snapshot` 的语义）
5. 精度-便利权衡的明确立场：续跑机制应该落在 v2（纯自然语言）到完全结构化（直接操作 ID）
   光谱的哪个位置？这个选择的可推翻条件是什么？

这些产出将成为 v3 框架续跑能力实现的直接依据。
