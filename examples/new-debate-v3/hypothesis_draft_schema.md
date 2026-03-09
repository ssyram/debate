---
title: "v3 认知引擎：HypothesisDraft 接口的统一规范"
rounds: 3
cross_exam: 1
max_reply_tokens: 10000
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

      你的核心判断标准：接口不统一就是隐患。两个函数同名返回类型不兼容，是 API 设计事故，不是哲学分歧。

      你对本议题的具体关切：
      - MB 的 HypothesisDraft 有 `problem_id`、`open_term_risk`、`ttl`、`tension_source.tier`，repair 的没有——
        这不是"两种草稿各有关注"，这是同一个 is_homologous() 函数要同时处理两种对象时会爆掉的类型炸弹。
      - repair 的 `verifier_hint` 是 `string`，MB 的是 `string[]`——任何消费 verifier_hint 的代码都要做
        类型 guard，这是接口设计失败的证明。
      - CC（ClarityCompiler）的输入是 `HypothesisDraft[]`，目前不清楚 CC 是否会区别对待 MB 草稿和 repair 草稿。
        如果不区分：缺字段会 NPE；如果区分：CC 要根据来源走不同路径，这破坏了 CC 的职责单一性。
      - `compute_semantic_similarity()` 在 MB 的 is_homologous_to_selected() 中被调用，repair 用 Jaccard——
        同一语义判定，两套实现，必然产生一致性问题。

      攻击风格：要求对手给出统一后的完整 TypeScript 类型定义，以及 CC 消费统一类型时不需要分支判断的证明。
      对"两种草稿本质不同"的论断要追问：那 CC 和 is_homologous() 的接口签名怎么写？

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram，v3 框架的核心设计者。CEGAR/MAX-SMT 背景，形式化方法研究者。

      你完整掌握已裁定的 v3 架构：
      - MB（MacroBreadth）节点：从 QuestionFrame 广度探索，产出初始 HypothesisDraft[]
      - repair() 节点（RB，RepairBreadth）：根据 L2Return（GapSpec + SchemaChallengeNotice），
        产出修复性 HypothesisDraft[]
      - CC（ClarityCompiler）：将 HypothesisDraft 编译为 TestableClaim
      - is_homologous()：在草稿池上做同源性检测，用于去重
      - 终止条件：连续两个 epoch 无 ranking-changing repair

      当前两个 HypothesisDraft 的具体字段冲突：
      - MB 版本（来自 question_ingestion 裁定）：
        { draft_id, problem_id, claim_sketch, tension_source: {kind, tier, evidence_ref, note},
          verifier_hint: string[], open_term_risk: string[], ttl: number }
      - repair 版本（来自 repair_strategy 裁定）：
        { draft_id, scope_ref: string[], tension_source: {kind, detail},
          claim_sketch, verifier_hint: string,
          provenance: {source_gap_id?, source_challenge_id?, repair_stage, epoch} }

      你的核心主张：
      - 两类草稿在 CC 和 is_homologous() 的视角下，所需信息不同。强行统一可能导致某方信息冗余或丢失。
      - 但你也承认接口不统一会造成下游消费困难。你的任务是提出一个设计方案，解决冲突。
      - 对于 compute_semantic_similarity() vs Jaccard 的分歧，你有明确立场：
        两者用途不同（MB 阶段是候选选择，repair 阶段是过滤），
        不应该强制统一到同一实现，而应该提供统一接口、允许内部差异化实现。

      最不确定的点：
      - 如果 MB 和 repair 用统一类型，`ttl` 对 repair 草稿有意义吗？
        repair 草稿的生命周期由 ChallengeTracker 的 stage 机器管理，不是 ttl 递减。
      - provenance 对 MB 草稿有意义吗？MB 的草稿没有 source_gap_id。

      攻击风格：直接指出对手方案的类型冗余和语义混用，要求给出统一类型中每个字段在 MB 和 repair
      两种情况下的具体语义和是否必填。

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学创始人。从先验认识论审查每个设计决策的合法性边界。

      你已理解的 v3 架构背景：
      - MB 草稿是"广度探索产物"：从 QuestionFrame 的评估轴张力中推导出的假设草稿，
        它的本质是"待检验的问题框架内的候选命题"
      - repair 草稿是"修复性产物"：从 Layer 2 的结构性失败（GapSpec/SchemaChallengeNotice）中推导出的，
        它的本质是"针对已知知识缺口的补充假设"
      - CC 编译的是语义结构，不是草稿来源

      你对本议题的审查重点：
      - 两类草稿在认识论上的性质差异：MB 草稿来自先验框架内部的张力分析，
        repair 草稿来自经验验证的失败反馈。这种性质差异是否应该在接口层面被保留？
      - is_homologous() 的语义：它判断的是"两个草稿是否本质上探索同一个知识空间"，
        而不是"两个草稿的字段是否相似"。如果 MB 和 repair 产出的草稿用同一类型表示，
        is_homologous() 是否能正确判断"来自不同认识来源但探索相同空间"的情况？
      - compute_semantic_similarity() vs Jaccard 的深层分歧：
        前者是语义距离度量（用于候选集多样性优化），后者是结构签名匹配（用于过滤重复）。
        统一接口是否会模糊这两种不同的认识论操作？

      攻击风格：区分概念混乱，追问先验条件与可推翻边界。
      特别关注：如果统一类型导致某些字段对某类草稿"语义为空"（如 repair 草稿的 ttl），
      这种"名义上有但语义上空"的状态是否比接口分离更危险？

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。

  禁止：
  - 纯原则性陈述——每个设计主张必须伴随至少一个具体的 TypeScript 类型定义或 Python 伪代码
  - 稻草人攻击——交叉质询中必须引用对手的具体文本或接口定义
  - 重新讨论已裁定的结论（Layer 1 是可回退薄状态机、CC 是编译器、is_homologous() 是动态计算的二元关系、
    终止条件=连续两轮无 ranking-changing repair）
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对本议题核心决策点之一的明确立场（有接口类型或伪代码支撑）
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）
  3. 所有主张必须附可推翻条件（什么反例能推翻你的设计选择）

round1_task: |
  第一轮：选择以下设计问题中你认为最关键的一个，给出完整立场。

  设计问题：
  A. MB 和 repair 应该产出同一个 HypothesisDraft 类型，还是两个独立的子类型？
  B. 如果统一：合并后的字段列表是什么？每个字段对两种来源草稿的语义各是什么？
  C. 如果不统一：CC 的输入类型如何定义（union type 还是 protocol/interface）？is_homologous() 的签名如何写？
  D. compute_semantic_similarity()（MB 内部）和 is_homologous()（repair 阶段）是否应该共用实现？
     如果共用：统一接口是什么？如果不共用：两者的语义区别如何在接口上体现？

  必须包含：
  1. 完整的 TypeScript 类型定义（含所有字段和可选性标注）
  2. 你方案的最强支撑论据——含至少一个具体的边界场景（当 CC 或 is_homologous() 处理边界输入时，你的方案如何处理，竞争方案会怎样失败）
  3. 你方案的已知弱点及缓解措施
  4. 对至少一个对手可能立场的预攻击

middle_task: |
  中间轮：吸收前一轮攻击后的回应与深化。

  必须包含：
  1. 回应对你方案的最强攻击——明确承认击中的部分，精确反驳打偏的部分
  2. 给出 CC 消费 HypothesisDraft 的完整流程：从接收草稿到输出 TestableClaim 或 CompileError，
     在你的类型方案下不需要任何 isinstance/typeof 分支判断的证明（或承认需要分支并解释为何可接受）
  3. 给出 is_homologous() 的完整函数签名，在你的类型方案下如何同时处理 MB 草稿和 repair 草稿
  4. 一个具体的 10 行以内运行案例：展示 MB 草稿和 repair 草稿在同一个 is_homologous() 调用中被正确比较

final_task: |
  最终轮：给出 HypothesisDraft 接口的完整统一方案。

  必须包含：
  1. A/B/C/D 四个设计问题的明确立场和最终理由
  2. HypothesisDraft 的最终完整类型定义（TypeScript）——所有字段、可选性、注释说明每个字段的语义
  3. CC 的 compile() 函数签名，在统一类型下如何工作（含失败路径）
  4. is_homologous() 的最终函数签名，说明如何处理跨来源（MB vs repair）的草稿比较
  5. compute_semantic_similarity() 和 is_homologous() 的关系：共用实现还是独立实现？
     如果共用：给出抽象接口；如果独立：给出两者共同遵守的约定（如输出值域、输入类型）
  6. 你的方案最可能在什么场景下失败（给出具体输入），以及接受什么样的反例来推翻设计

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**
  - 对每个设计问题（A/B/C/D）用日常语言解释裁定结果
  - 每个裁定必须包含至少一个具体例子：当系统处理某个具体场景时，这个设计选择会导致什么具体行为差异
  - 风格参考之前辩论的 summary：用日常比喻（工厂流水线、邮局分拣、图书管理等）让非技术人员理解，
    但白话版结论之后的「可实现性摘要」部分要严格技术化
  - 明确说明哪些场景下裁定可能需要修正
  - 每个问题以「一句话总结」结尾

  **第二部分：可实现性摘要**
  - HypothesisDraft 的最终完整 TypeScript 类型定义（统一类型或子类型方案，二选一，明确说明理由）
  - CC compile() 函数的最终接口规范（函数签名 + 关键分支的伪代码）
  - is_homologous() 的最终接口规范（函数签名 + 核心比较逻辑的伪代码）
  - compute_semantic_similarity() 和 is_homologous() 的关系裁定（共用接口规范 or 独立规范 + 约定）
  - 完整的数据流示意：MB产出草稿 → is_homologous()去重 → CC编译 → repair产出草稿 → is_homologous()去重 → CC编译
  - 标注实现难度最高的 2 个子问题及其风险

  对 A/B/C/D 每个设计问题必须给出明确的最终裁定，不得搁置。
---

# v3 认知引擎：HypothesisDraft 接口的统一规范

## 一、背景：v3 框架整体架构（完整概述）

v3 认知引擎的目标是：给定一个开放式、有争议的问题，系统能产出一个多视角、辩护完备的答案体系。已在前序辩论中裁定的核心架构如下。

### 1.1 两层架构

**Layer 1（问题级处理层）**——薄状态机，节点序列为：
```
QN（QuestionNormalizer）
  → MB（MacroBreadth）
  → CC（ClarityCompiler）
  → D2（Layer2Dispatch）
  → PA（PrecisionAggregator）
  → RB（RepairBreadth）
  → AS（AnswerSynthesis）
```

**Layer 2（命题级处理层）**——v2 十状态机，处理每一个具体的 TestableClaim：
```
S1(Clarify) → S2(Depth) → S3(Precision) → S4(DepthProbe) ↔ S5(BreadthProbe)
  → S6(Verified) | S7(Suspended) | S9(SchemaChallenge)
```

Layer 1 负责"发散思考"，Layer 2 负责"严格验证"。两层之间可以双向通信：Layer 2 的结构性失败信号（GapSpec、SchemaChallengeNotice）触发 Layer 1 的 repair 回路，repair 产出新的 HypothesisDraft 进入 CC 再次编译。

**终止条件**（已裁定）：连续两个 epoch 的 L2Return 显示无 ranking-changing repair，则 Layer 1 终止，输出 TerminationReport。

### 1.2 MB→CC→repair 数据流

```
QuestionFrame
    │
    ▼
┌──────────────┐
│  MB节点       │  macro_breadth(frame) → HypothesisDraft[]（初始草稿池）
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  CC节点       │  clarity_compile(draft, frame) → TestableClaim | RegulativeIdea | CompileError
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  D2/L2节点    │  Layer 2 验证 → L2Return { new_gaps: GapSpec[], schema_challenges: SchemaChallengeNotice[] }
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  RB节点       │  repair(ctx) → HypothesisDraft[]（修复草稿）→ 再次进入 CC
└──────────────┘
```

**关键问题**：MB 和 repair 都产出 `HypothesisDraft[]`，但这两个 `HypothesisDraft` 的定义在两次裁定中产生了字段不兼容的问题。

### 1.3 两次裁定中的 HypothesisDraft 定义

**定义一**（来自 question_ingestion 裁定，MB 的输出）：
```typescript
// MB（macro_breadth）产出的草稿
type HypothesisDraft = {
  draft_id: string;
  problem_id: string;               // 关联 QuestionFrame
  claim_sketch: string;
  tension_source: {
    kind: "EXTERNAL_POSITION" | "STAKEHOLDER_CONFLICT" | "EVALUATION_AXIS_SPLIT";
    tier: "INTERNAL_AXIS" | "EMPIRICAL";    // 认识论层级
    evidence_ref: string[];
    note: string;
  };
  verifier_hint: string[];          // 注意：数组
  open_term_risk: string[];         // MB 标记的 open term 风险
  ttl: number;                      // 草稿存活时间（epoch 数）
};
```

**定义二**（来自 repair_strategy 裁定，repair() 的输出）：
```typescript
// repair() 产出的草稿
interface HypothesisDraft {
  draft_id: string;
  scope_ref: string[];              // 草稿的 scope 引用
  tension_source: { kind: string; detail: string };  // 简化版 tension_source
  claim_sketch: string;
  verifier_hint: string;            // 注意：单个字符串，不是数组
  provenance: {
    source_gap_id?: string;         // 来自哪个 GapSpec
    source_challenge_id?: string;   // 来自哪个 SchemaChallengeNotice
    repair_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
    epoch: number;
  };
}
```

**已知字段不兼容清单：**

| 字段 | MB 定义 | repair 定义 | 冲突性质 |
|------|---------|-------------|---------|
| `problem_id` | `string`（必填） | 缺失 | MB 有，repair 无 |
| `scope_ref` | 缺失 | `string[]`（必填） | repair 有，MB 无 |
| `tension_source` | `{kind, tier, evidence_ref, note}` | `{kind, detail}` | 结构不兼容 |
| `verifier_hint` | `string[]` | `string` | 类型不兼容 |
| `open_term_risk` | `string[]`（必填） | 缺失 | MB 有，repair 无 |
| `ttl` | `number`（必填） | 缺失 | MB 有，repair 无 |
| `provenance` | 缺失 | `{source_gap_id?, source_challenge_id?, repair_stage, epoch}` | repair 有，MB 无 |

### 1.4 两个相关函数的实现分歧

**compute_semantic_similarity()**（来自 MB 的 is_homologous_to_selected()）：
```python
def is_homologous_to_selected(candidate, selected):
    for s in selected:
        axis_overlap = len(set(candidate.axis_ids) & set(s.axis_ids)) / max(len(candidate.axis_ids), 1)
        semantic_sim = compute_semantic_similarity(candidate.claim_sketch, s.claim_sketch)
        if axis_overlap > 0.8 and semantic_sim > 0.85:
            return True
    return False
```
MB 阶段的同源性：基于轴重叠度 + **语义相似度**（embedding 级别），用于候选集多样性筛选。

**is_homologous()**（来自 repair_strategy 裁定，repair 阶段）：
```python
def is_homologous(candidate, existing_pool, gap_index) -> HomologyResult:
    a = extract_features(candidate, gap_index)  # 提取结构特征（scope/outcome/polarity/verifier）
    for e in existing_pool:
        b = extract_features(e, gap_index)
        result = compare_pair(a, b, candidate, e)  # Jaccard + 结构匹配
        if result.is_homologous:
            return result
    return HomologyResult(is_homologous=False, ...)
```
repair 阶段的同源性：基于**结构签名**（scope/outcome/polarity/verifier 的 Jaccard 相似度），用于过滤草稿池中的重复。

### 1.5 ClarityCompiler 的下游消费（已裁定）

CC 的输入类型目前定义为 `HypothesisDraft`（来自 claim_compiler 裁定）：
```typescript
function clarity_compile(
  draft: HypothesisDraft,
  frame: QuestionFrame,
  opts?: CompileOptions
): CompileResult;
// CompileResult = TESTABLE_CLAIM | REGULATIVE_IDEA | COMPILE_ERROR
```

CC 需要从 `HypothesisDraft` 中读取：`claim_sketch`（核心命题），`tension_source`（张力来源，用于 falsifier 合成），`scope_ref` 或等效信息（用于 scope 提取），`verifier_hint`（用于 accept_test 生成）。

**如果 MB 版本没有 `scope_ref`，CC 如何提取 scope？如果 repair 版本的 `verifier_hint` 是 `string` 而 CC 期望 `string[]`，CC 需要做类型 guard 吗？**

---

## 二、核心辩论问题

### 问题 A：统一类型 vs 子类型方案

**方案 A1（统一类型）**：合并所有字段为单一 `HypothesisDraft` 类型，所有字段按需可选。CC、is_homologous() 等下游消费者无需类型分支。

**方案 A2（子类型方案）**：定义 `MBDraft` 和 `RepairDraft` 两个子类型，或定义公共基类 + 子类扩展，CC 接受 union type 输入。

**方案 A3（协议/接口方案）**：定义 `HypothesisDraftBase` 接口（最小公共字段集），CC 和 is_homologous() 只消费 base，各来源的扩展字段通过 metadata 传递。

**关键判断标准**：CC 和 is_homologous() 在实际工作中，是否需要感知"这个草稿来自 MB 还是 repair"？如果需要，统一类型无法消除分支；如果不需要，子类型方案制造了不必要的复杂度。

### 问题 B：统一类型的字段合并规范

如果选择 A1，完整合并后的字段列表是什么？具体要决定：

- `ttl`：对 repair 草稿是否有意义？repair 草稿的生命周期由 `ChallengeTracker.stage` 管理，不依赖 ttl 递减。
- `provenance`：对 MB 草稿是否有意义？MB 草稿没有 source_gap_id，但也有"来自哪个 tension candidate"的溯源需求。
- `open_term_risk`：对 repair 草稿是否有意义？repair 草稿的 claim_sketch 也可能引用 open term。
- `scope_ref`：对 MB 草稿是否有意义？MB 的草稿在 question_ingestion 裁定的类型中没有此字段，但 CC 需要 scope 信息。
- `tension_source.tier`：对 repair 草稿是否有意义？repair 草稿不是从 QuestionFrame 的 tier 体系产生的。

### 问题 C：子类型方案的接口设计

如果选择 A2 或 A3，需要决定：

- CC 的参数类型：`compile(draft: MBDraft | RepairDraft, ...)` 还是 `compile(draft: HypothesisDraftBase, ...)`？
- 如果是 union type，CC 内部是否需要 `if ('provenance' in draft)` 或 `if ('ttl' in draft)` 这样的来源判断分支？这是否违反 CC 的职责单一性？
- is_homologous() 的参数类型：当比较一个 MB 草稿和一个 repair 草稿时（跨来源比较），函数签名如何定义？
- HomologyFeatures 的提取：对于 MB 草稿（没有 `provenance`）和 repair 草稿（没有 `tension_source.tier`），extract_features() 如何统一提取？

### 问题 D：compute_semantic_similarity() 与 is_homologous() 的关系

MB 的 is_homologous_to_selected() 调用 `compute_semantic_similarity()`（基于 embedding 语义相似度），repair 的 is_homologous() 用 Jaccard（基于结构签名）。

**核心分歧**：

- 这两个函数是否在做同一件事？如果是：应该统一为一个函数，MB 和 repair 都调用它。
- 如果不是：它们分别在做什么？用途差异是否足以支撑两套独立实现？
- 如果统一：抽象接口是什么？允许内部差异化实现吗？

**潜在问题**：如果 HypothesisDraft 统一类型，MB 阶段的 is_homologous_to_selected() 和 repair 阶段的 is_homologous() 是否应该合并为同一个函数？合并后，对同一批 MB 草稿用 Jaccard 过滤，是否会错误地放行一些本应被语义相似度过滤的重复草稿？

---

## 三、开放性陈述

以上四个问题没有显而易见的"正确答案"。MB 和 repair 的草稿在流水线中扮演相同的角色（进入 CC 编译），但产生于完全不同的过程（广度探索 vs 修复响应），携带不同的溯源信息。

**期待辩论产出的最终结论**：

1. HypothesisDraft 的最终完整类型定义（不管是统一类型还是子类型方案，必须有明确的 TypeScript 定义）
2. CC compile() 函数的最终签名，在该类型方案下如何工作
3. is_homologous() 的最终签名，如何处理跨来源草稿的比较
4. compute_semantic_similarity() 和 is_homologous() 的关系裁定

这些规范将成为 v3 框架实现的直接依据，需要在不引入歧义的前提下，为 MB 和 repair 两条产出路径提供统一的下游消费接口。
