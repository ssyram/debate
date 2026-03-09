# v3 认知引擎：HypothesisDraft 接口的统一规范 裁判总结

> 2026-03-09T19:01:40.231119

# 裁判裁定书

---

## 第一部分：白话版结论

### 问题 A：MB 草稿和 repair 草稿应该用同一个类型，还是分成两个子类型？

**裁定：采用"规范化统一消费类型 + 上游允许各自原始类型"的方案。**

这不是 Linus 最初的"一个大结构体打天下"，也不是 Ssyram/康德的"两个子类型 + 薄薄的公共接口"。裁定的方案是：**存在一个完整的、语义封闭的 `HypothesisDraft` 统一类型，它是 CC、is_homologous()、池管理、终止报告等所有共享消费者的唯一输入；但 MB 和 repair 在各自的生产函数内部可以先用自己的中间结构，只要在进入共享流水线之前必须通过一个规范化工厂函数转换为统一类型。**

**日常比喻**：想象一个国际邮局。中国寄来的包裹有中文面单，德国寄来的有德文面单，格式完全不同。但进入分拣流水线之前，每个包裹都必须贴上一张统一格式的国际标签——收件人、重量、目的地、是否易碎，全部用同一套字段填写。分拣员只看这张标签，不需要去读原始面单。但这张标签上的每个字段都必须有真实含义，不能因为中国包裹没有"易碎"概念就随便填个"否"——如果里面真的是瓷器，那就必须标"是"。

**具体场景举例**：当系统同时持有一个 MB 草稿（"利益相关者对碳税效果存在分歧"）和一个 repair 草稿（"L2 验证发现碳税假设缺少发展中国家视角"），`is_homologous()` 需要判断它们是否在探索同一个知识空间。如果用两个不同的子类型，这个函数要么写 `if-else` 分支（Linus 正确指出的问题），要么只看一个过于贫瘠的公共基类（康德和 Ssyram 的 Base 缺少 `problem_id`、`open_term_risk` 等字段）。统一类型让这个比较在同一个字段集合上进行，无需类型判断。

**关键裁定理由**：

1. **Linus 赢在核心论点上**：CC 和 `is_homologous()` 确实不应该因为草稿来源不同而写分支逻辑。三位辩手最终都承认了这一点（康德最终版的 `CompilableDraft` 和 Ssyram 最终版的 `DraftCore` 实质上都在向统一消费类型靠拢）。

2. **康德和 Ssyram 赢在一个关键修正上**：`ttl` 不应该作为统一类型的必填字段。Ssyram 的论证是决定性的——repair 草稿的生命周期由 L2 ChallengeTracker 的 stage 状态机管理，而 MB 草稿的生命周期由广度池 TTL 衰减管理。强行统一 `ttl` 会导致 repair 草稿被错误淘汰，切断 CEGAR 反馈回路。这不是"名义上有语义上空"的抽象批评，而是一个可以直接导致系统终止条件永远无法满足的具体 bug。

3. **Ssyram 的"编译投影"方案被否决**：把 `tension_source` 降格为只含 `synthesis_route` 和 `falsifier_hints` 的 `CompilableTension`，会丢失 debug tracing、终止解释、同源性比较所需的原始语义信息。康德对此的攻击是精确的。

**需要修正的场景**：如果未来系统明确裁定所有草稿（无论来源）进入同一个候选池并由统一的淘汰机制管理，则 `ttl` 可以回到统一类型的必填字段中。

**一句话总结**：统一消费类型是对的，但 `ttl` 和 `repair_stage` 等生命周期字段必须放在 `provenance` 的来源特定子结构中，而非作为顶层必填字段。

---

### 问题 B：字段合并与规范化规则

**裁定：`scope_ref`、`verifier_hint`、`open_term_risk`、`tension_source` 全部统一为必填字段，但 MB 必须在产出时强制推导 `scope_ref`（禁止空数组），repair 必须将单个 `verifier_hint` 字符串包装为数组。**

**日常比喻**：就像工厂质检——每个产品出厂前都必须填写完整的检验报告。不能因为某条生产线"通常不测这个指标"就留空。如果你的生产线确实无法测量某个指标，那说明你的生产线需要升级，而不是检验报告需要删字段。

**具体场景举例**：MB 产出一个草稿时，如果 `scope_ref` 为空数组 `[]`，那么当 `is_homologous()` 用 Jaccard 相似度比较这个 MB 草稿和一个 repair 草稿（`scope_ref: ["economic_impact", "developing_nations"]`）时，Jaccard 系数恒为 0，系统会认为它们完全不同源——即使它们的 `claim_sketch` 几乎一样。这是 Linus 在交叉质询中精确指出的偏置问题。因此 MB 必须在产出时从 `QuestionFrame` 的 `evaluation_axes` 和 `stakeholder_map` 中推导出 `scope_ref`。

**关键裁定细节**：

| 字段 | MB 规范化规则 | Repair 规范化规则 |
|------|-------------|-----------------|
| `scope_ref` | 从 QuestionFrame 推导，禁止 `[]` | 从 GapSpec 继承，必填 |
| `verifier_hint` | 已经是 `string[]`，保持 | 单 string 包装为 `[string]` |
| `open_term_risk` | 原生产出 | 从 L2 失败上下文推导，允许 `[]` |
| `tension_source.tier` | 原生值 | `"L2_FAILURE"`（这是真实语义，不是占位） |
| `tension_source.evidence_ref` | 原生值 | 从 challenge 上下文提取，允许 `[]` |
| `problem_id` | 原生值 | 由 L1 调度层从 `claim_to_problem` 映射注入 |

**需要修正的场景**：如果 L2 返回的结构性失败确实无法稳定映射回 `problem_id`（例如跨多个 problem 的系统性 schema 失败），则需要引入 `problem_id: string | string[]` 或额外的映射机制。

**一句话总结**：所有共享消费字段必填，但"必填"意味着上游必须做真实推导，不是填默认值糊弄。

---

### 问题 C：CC compile() 的接口设计

**裁定：`clarity_compile()` 接受统一的 `HypothesisDraft`，内部可以根据 `tension_source.kind` 和 `tension_source.tier` 进行语义分支，但绝对禁止根据 `provenance.source` 进行来源分支。**

**日常比喻**：一个翻译官接到一份文件，他可以根据文件的主题（科技论文 vs 法律合同 vs 医学报告）选择不同的翻译策略——这是合法的语义分支。但他不应该根据"这份文件是从北京寄来的还是从柏林寄来的"来决定翻译策略——这是非法的来源分支。文件的主题恰好和来源有相关性（北京寄来的更可能是中文科技论文），但翻译策略应该基于主题本身，不是邮戳。

**具体场景举例**：CC 收到一个 `tension_source.kind = "GAP_REPAIR"` 且 `tier = "L2_FAILURE"` 的草稿。CC 知道这意味着需要构造一个针对特定知识缺口的证伪器，所以它会从 `evidence_ref` 中提取缺口描述来生成 falsifier。CC 不需要知道这个草稿来自 repair 模块——它只需要知道张力类型是 GAP_REPAIR。如果未来 MB 也能产出 GAP_REPAIR 类型的草稿（比如在初始分析中就发现了知识缺口），CC 的逻辑完全不需要改动。

**这解决了 Ssyram 的核心质疑**："CC 终究会按 kind/tier 分发，这与知道来源有何区别？"区别在于：按 `kind/tier` 分发是基于**编译所需的语义维度**，按 `source` 分发是基于**生产来源的偶然事实**。前者是稳定的（语义不变则逻辑不变），后者是脆弱的（新来源出现则逻辑必须改）。康德在最终轮对此的阐述是精确的。

**需要修正的场景**：如果未来发现某些编译策略确实只对 repair 草稿有意义（例如需要读取 `repair_stage` 来决定证伪器的严格程度），则应将 `repair_stage` 提升为 `tension_source` 的可选子字段，而非让 CC 去读 `provenance`。

**一句话总结**：CC 按语义分支，不按来源分支；如果某个来源特有的信息确实影响编译，就把它提升为语义字段。

---

### 问题 D：`compute_semantic_similarity()` 和 `is_homologous()` 的关系

**裁定：两者不应共用实现，但应共用底层特征提取工具。`is_homologous()` 是知识空间同一性的二值判断，`compute_semantic_similarity()` 是多样性优化的连续度量。**

**日常比喻**：图书管理员有两个任务。任务一：判断两本书是不是同一本书的不同版本（`is_homologous`）——即使封面不同、章节顺序不同，只要核心内容讲的是同一件事，就算同源。任务二：给书架上的书打多样性分数（`compute_semantic_similarity`）——两本都讲经济学但一本侧重宏观一本侧重微观，相似度高但不同源。管理员可以共用"读目录、提取关键词"这个基础技能，但判断逻辑完全不同。

**具体场景举例**：
- MB 草稿 A："碳税会降低 GDP 增长率"（scope: [economic_impact, gdp]）
- Repair 草稿 B："碳税对发展中国家 GDP 的影响被低估"（scope: [economic_impact, gdp, developing_nations]）
- MB 草稿 C："碳税会促进绿色技术创新"（scope: [innovation, green_tech]）

`is_homologous(A, B)` 应返回 `true`——它们探索的是同一个知识空间（碳税对 GDP 的影响），B 只是 A 的精化修复。
`compute_semantic_similarity(A, C)` 应返回一个中等值（比如 0.4）——它们都关于碳税，但探索不同维度，应该保留多样性。
`is_homologous(A, C)` 应返回 `false`——它们不是同一个知识空间的变体。

如果共用实现，你要么把二值判断做成"阈值切割连续分数"（丢失结构信息），要么把连续度量做成"二值判断的软化"（引入不必要的复杂性）。

**关键接口关系**：
- 共用：`extract_homology_features(draft: HypothesisDraft) → HomologyFeatures`（提取 claim tokens、scope set、tension kind）
- 分离：`is_homologous()` 在 features 上做 Jaccard + claim overlap 的复合判断，输出 boolean
- 分离：`compute_semantic_similarity()` 在 features 上做 embedding cosine similarity，输出 [0,1] 浮点数

**需要修正的场景**：如果实践中发现 `is_homologous()` 的硬阈值导致大量边界案例误判，可以考虑让它也输出置信度分数，但判断逻辑仍应独立于相似度计算。

**一句话总结**：共用特征提取，分离判断逻辑；同源性是"是不是同一本书的不同版本"，相似度是"两本书有多像"。

---

## 第二部分：可实现性摘要

### 1. HypothesisDraft 最终完整 TypeScript 类型定义

**方案选择：统一类型方案（修正版 A1）。**

理由：三位辩手最终都收敛到了"CC 和 is_homologous() 需要一个完整的、不需要类型判断的输入"这一共识。子类型方案（A2/A3）在理论上优美，但在实践中要么导致公共基类过于贫瘠（Ssyram 的 Base 缺少 `problem_id`、`open_term_risk`），要么导致公共协议膨胀到与统一类型无实质区别（康德最终版的 `CompilableDraft` 已经包含了几乎所有字段）。选择统一类型，但将生命周期管理字段隔离到 `provenance` 子结构中。

```typescript
// ============================================================
// 枚举与基础类型
// ============================================================

type DraftId = string;
type ProblemId = string;
type Epoch = number;

type DraftSource = "MB" | "REPAIR";

type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT"
  | "GAP_REPAIR"
  | "SCHEMA_REPAIR"
  | "OTHER";

type EpistemicTier =
  | "INTERNAL_AXIS"    // MB: 内部评价轴冲突
  | "EMPIRICAL"        // MB: 经验性可检验分歧
  | "L2_FAILURE"       // Repair: 来自 L2 验证失败
  | "STRUCTURAL";      // Repair: 结构性 schema 问题

// ============================================================
// 核心统一类型
// ============================================================

interface TensionSource {
  kind: TensionKind;
  tier: EpistemicTier;
  evidence_ref: string[];   // MB: 原生证据引用; Repair: 从 challenge 上下文提取, 允许 []
  note: string;             // MB: 张力描述; Repair: gap/challenge 描述
}

interface Provenance {
  source: DraftSource;
  epoch: Epoch;

  // === MB 特有（Repair 时为 undefined）===
  ttl?: number;                    // 仅 MB 草稿使用的广度池生存预算

  // === Repair 特有（MB 时为 undefined）===
  source_gap_id?: string;          // 触发修复的 GapSpec ID
  source_challenge_id?: string;    // 触发修复的 Challenge ID
  repair_stage?: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
}

interface HypothesisDraft {
  // --- 核心标识 ---
  draft_id: DraftId;
  problem_id: ProblemId;           // 必填。MB 原生; Repair 由 L1 调度层注入

  // --- 语义内容 ---
  claim_sketch: string;            // 假设的自然语言草稿
  scope_ref: string[];             // 必填且禁止空数组。MB 从 QF 推导; Repair 从 GapSpec 继承
  verifier_hint: string[];         // 统一为数组。Repair 的单 string 包装为 [string]
  open_term_risk: string[];        // MB 原生; Repair 从 L2 失败上下文推导, 允许 []

  // --- 张力来源 ---
  tension_source: TensionSource;

  // --- 来源与生命周期元数据 ---
  provenance: Provenance;
}
```

**设计决策说明**：

- `ttl` 放在 `provenance` 内且为可选：解决了 Ssyram/康德关于"repair 草稿被 TTL 误淘汰"的核心担忧，同时保留了 MB 草稿的广度池管理能力。池管理器读 `provenance.ttl`（存在则用 TTL 衰减，不存在则按 repair stage 管理），这是**基于字段存在性的分支**，不是基于 `source` 的分支。
- `scope_ref` 禁止空数组：解决了 Linus 指出的 Jaccard 偏置问题。
- `tension_source` 保留完整语义（`kind` + `tier` + `evidence_ref` + `note`）：解决了康德对 Ssyram "编译投影丢失信息"的攻击。
- `problem_id` 必填：采纳 Ssyram 的论证——CEGAR 闭环要求所有草稿可溯源到 QuestionFrame。

### 2. CC compile() 最终接口规范

```typescript
// ============================================================
// CC compile() 接口
// ============================================================

interface CompileResult {
  testable_claim: {
    claim_id: string;
    statement: string;           // 精确化后的可检验命题
    falsifier: string;           // 证伪条件
    boundary_conditions: string[];
  };
  verification_plan: {
    verifier_type: string;       // e.g., "EMPIRICAL_CHECK", "LOGICAL_AUDIT", "SCOPE_REVIEW"
    required_evidence: string[];
  };
  compile_warnings: string[];    // 编译过程中的风险提示
}

function clarity_compile(
  draft: HypothesisDraft,
  frame: QuestionFrame
): CompileResult;
```

**关键分支伪代码**：

```python
def clarity_compile(draft: HypothesisDraft, frame: QuestionFrame) -> CompileResult:
    # 1. 提取编译上下文（不读 provenance.source）
    tension = draft.tension_source

    # 2. 根据 tension.kind 选择证伪器合成策略
    if tension.kind in ("EXTERNAL_POSITION", "STAKEHOLDER_CONFLICT"):
        # 轴冲突类：从 evidence_ref 提取对立立场，构造对比证伪
        falsifier = synthesize_contrastive_falsifier(
            claim=draft.claim_sketch,
            evidence=tension.evidence_ref,
            axes=frame.evaluation_axes
        )
    elif tension.kind == "EVALUATION_AXIS_SPLIT":
        # 评价轴分裂：构造轴独立性证伪
        falsifier = synthesize_axis_independence_falsifier(
            claim=draft.claim_sketch,
            evidence=tension.evidence_ref
        )
    elif tension.kind in ("GAP_REPAIR", "SCHEMA_REPAIR"):
        # 修复类：从 note 提取缺口描述，构造覆盖性证伪
        falsifier = synthesize_coverage_falsifier(
            claim=draft.claim_sketch,
            gap_description=tension.note,
            scope=draft.scope_ref
        )
    else:
        # OTHER: 通用证伪
        falsifier = synthesize_generic_falsifier(draft.claim_sketch)

    # 3. 根据 tension.tier 调整验证计划
    if tension.tier == "EMPIRICAL":
        verifier_type = "EMPIRICAL_CHECK"
    elif tension.tier == "L2_FAILURE":
        verifier_type = "TARGETED_RECHECK"
    elif tension.tier == "STRUCTURAL":
        verifier_type = "LOGICAL_AUDIT"
    else:  # INTERNAL_AXIS
        verifier_type = "AXIS_CONSISTENCY_CHECK"

    # 4. 精确化 claim
    testable_claim = refine_claim(
        sketch=draft.claim_sketch,
        scope=draft.scope_ref,
        open_risks=draft.open_term_risk,
        hints=draft.verifier_hint,
        frame=frame
    )

    # 5. 组装结果
    return CompileResult(
        testable_claim=TestableClaim(
            claim_id=generate_id(),
            statement=testable_claim,
            falsifier=falsifier,
            boundary_conditions=derive_boundaries(draft.scope_ref, frame)
        ),
        verification_plan=VerificationPlan(
            verifier_type=verifier_type,
            required_evidence=tension.evidence_ref + draft.verifier_hint
        ),
        compile_warnings=check_open_term_risks(draft.open_term_risk)
    )
```

**注意**：整个函数中没有任何 `if draft.provenance.source == "MB"` 或 `if draft.provenance.source == "REPAIR"` 的分支。所有分支都基于 `tension_source.kind` 和 `tension_source.tier` 这两个语义维度。

### 3. is_homologous() 最终接口规范

```typescript
// ============================================================
// 同源性判定接口
// ============================================================

interface HomologyFeatures {
  claim_tokens: Set<string>;       // claim_sketch 的标准化 token 集合
  scope_set: Set<string>;          // scope_ref 的集合化表示
  tension_kind: TensionKind;
  problem_id: ProblemId;
}

function extract_homology_features(
  draft: HypothesisDraft
): HomologyFeatures;

function is_homologous(
  a: HypothesisDraft,
  b: HypothesisDraft,
  threshold?: { claim_jaccard: number; scope_jaccard: number }
): boolean;
```

**核心比较逻辑伪代码**：

```python
DEFAULT_CLAIM_THRESHOLD = 0.6
DEFAULT_SCOPE_THRESHOLD = 0.5

def extract_homology_features(draft: HypothesisDraft) -> HomologyFeatures:
    return HomologyFeatures(
        claim_tokens=tokenize_and_normalize(draft.claim_sketch),
        scope_set=set(draft.scope_ref),
        tension_kind=draft.tension_source.kind,
        problem_id=draft.problem_id
    )

def is_homologous(
    a: HypothesisDraft,
    b: HypothesisDraft,
    threshold=None
) -> bool:
    fa = extract_homology_features(a)
    fb = extract_homology_features(b)

    # 1. 快速排除：不同 problem 的草稿不可能同源
    if fa.problem_id != fb.problem_id:
        return False

    # 2. Claim 内容重叠度
    claim_sim = jaccard(fa.claim_tokens, fb.claim_tokens)
    claim_thresh = threshold.claim_jaccard if threshold else DEFAULT_CLAIM_THRESHOLD

    # 3. Scope 重叠度
    scope_sim = jaccard(fa.scope_set, fb.scope_set)
    scope_thresh = threshold.scope_jaccard if threshold else DEFAULT_SCOPE_THRESHOLD

    # 4. 复合判断：claim 和 scope 都超过阈值才算同源
    #    注意：不检查 provenance.source，跨来源比较是正常场景
    return claim_sim >= claim_thresh and scope_sim >= scope_thresh
```

**设计说明**：
- `problem_id` 作为快速排除条件：不同问题框架下的草稿即使 claim 相似也不算同源。
- `tension_kind` 提取但未参与当前判断：预留给未来可能的精细化规则（例如 `GAP_REPAIR` 和 `EXTERNAL_POSITION` 即使 claim 相似也可能不同源）。
- 不使用 embedding cosine similarity：同源性是结构判断，不是语义相似度。

### 4. compute_semantic_similarity() 和 is_homologous() 的关系裁定

**裁定：共用特征提取接口，独立判断逻辑。**

```typescript
// 共用层
function extract_homology_features(draft: HypothesisDraft): HomologyFeatures;

// is_homologous(): 结构性二值判断
//   输入: 两个 HypothesisDraft
//   输出: boolean
//   方法: Jaccard on tokens + scope, 硬阈值
//   用途: 去重（MB 产出后去重, repair 产出后去重）

// compute_semantic_similarity(): 连续语义度量
//   输入: 两个 HypothesisDraft (或 TestableClaim)
//   输出: number ∈ [0, 1]
//   方法: embedding cosine similarity on claim_sketch
//   用途: 多样性优化（广度池排序, 假设集覆盖度评估）
```

**约定**：
- `is_homologous()` 返回 `true` 蕴含 `compute_semantic_similarity()` 返回高值（>0.6），但反之不成立。
- 两者不得互相调用。
- 如果未来需要"软同源性"（置信度），扩展 `is_homologous()` 的返回类型为 `{ homologous: boolean; confidence: number }`，但不合并到 `compute_semantic_similarity()` 中。

### 5. 完整数据流示意

```
┌─────────────────────────────────────────────────────────────────┐
│                        Layer 1 主循环                            │
│                                                                 │
│  ┌──────────┐    normalize_mb()     ┌──────────────────┐        │
│  │    MB     │ ──────────────────→  │                  │        │
│  │ (产出     │   RawMBDraft →       │  HypothesisDraft │        │
│  │  RawMB)   │   HypothesisDraft    │     候选池       │        │
│  └──────────┘                       │                  │        │
│                                     │  is_homologous() │        │
│                                     │  去重 ──────────→│ 去重后 │
│                                     │                  │ 的池   │
│                                     └────────┬─────────┘        │
│                                              │                  │
│                                              ▼                  │
│                                     ┌──────────────────┐        │
│                                     │  CC.compile()    │        │
│                                     │  (统一接口,       │        │
│                                     │   按 kind/tier   │        │
│                                     │   语义分支)       │        │
│                                     └────────┬─────────┘        │
│                                              │                  │
│                                              ▼                  │
│                                     ┌──────────────────┐        │
│                                     │  TestableClaim[] │        │
│                                     │  → 送入 Layer 2  │        │
│                                     └────────┬─────────┘        │
│                                              │                  │
│                          ┌───────────────────┘                  │
│                          ▼                                      │
│                 ┌──────────────────┐                             │
│                 │   Layer 2 验证    │                             │
│                 │   (D2 + 挑战者)   │                             │
│                 └────────┬─────────┘                             │
│                          │                                      │
│                          ▼ L2Return (含 GapSpec, Challenge)     │
│                 ┌──────────────────┐                             │
│                 │   Repair Block   │                             │
│                 │   (产出 RawRepair)│                             │
│                 └────────┬─────────┘                             │
│                          │                                      │
│                          ▼ normalize_repair()                   │
│                 ┌──────────────────┐                             │
│                 │ HypothesisDraft  │                             │
│                 │ (repair 来源)     │                             │
│                 └────────┬─────────┘                             │
│                          │                                      │
│                          ▼ is_homologous() 去重                 │
│                          │ (与池中已有草稿比较,                   │
│                          │  包括 MB 来源的草稿)                   │
│                          │                                      │
│                          ▼                                      │
│                 合并回 HypothesisDraft 候选池                    │
│                          │                                      │
│                          ▼                                      │
│                 CC.compile() → 新一轮 Layer 2                   │
│                          │                                      │
│                          ▼                                      │
│                 检查终止条件                                     │
│                 (连续两个 epoch 无 ranking-changing repair)      │
└─────────────────────────────────────────────────────────────────┘
```

**规范化工厂函数**：

```python
def normalize_mb(raw: RawMBDraft, frame: QuestionFrame) -> HypothesisDraft:
    assert len(raw.scope_ref) > 0 or infer_scope(raw, frame), "MB must have non-empty scope_ref"
    return HypothesisDraft(
        draft_id=raw.draft_id,
        problem_id=raw.problem_id,
        claim_sketch=raw.claim_sketch,
        scope_ref=raw.scope_ref or infer_scope(raw, frame),
        verifier_hint=raw.verifier_hint,  # 已经是 string[]
        open_term_risk=raw.open_term_risk,
        tension_source=TensionSource(
            kind=raw.tension_source.kind,
            tier=raw.tension_source.tier,
            evidence_ref=raw.tension_source.evidence_ref,
            note=raw.tension_source.note
        ),
        provenance=Provenance(
            source="MB",
            epoch=current_epoch(),
            ttl=raw.ttl  # MB 特有
        )
    )

def normalize_repair(raw: RawRepairDraft, ctx: RepairContext) -> HypothesisDraft:
    return HypothesisDraft(
        draft_id=generate_id(),
        problem_id=ctx.frame.problem_id,  # 由 L1 调度层注入
        claim_sketch=raw.claim_sketch,
        scope_ref=raw.scope_ref,  # 从 GapSpec 继承, 必填
        verifier_hint=[raw.verifier_hint] if isinstance(raw.verifier_hint, str) else raw.verifier_hint,
        open_term_risk=infer_open_term_risk(raw, ctx) or [],
        tension_source=TensionSource(
            kind=raw.tension_kind,  # "GAP_REPAIR" | "SCHEMA_REPAIR"
            tier="L2_FAILURE",
            evidence_ref=extract_evidence_from_challenge(ctx),
            note=raw.detail
        ),
        provenance=Provenance(
            source="REPAIR",
            epoch=current_epoch(),
            source_gap_id=ctx.gap_id,
            source_challenge_id=ctx.challenge_id,
            repair_stage=ctx.current_stage
        )
    )
```

### 6. 实现难度最高的 2 个子问题及其风险

**风险 1：MB 阶段 `scope_ref` 的强制推导（难度：高）**

- **问题**：裁定要求 MB 产出时 `scope_ref` 禁止为空数组，必须从 QuestionFrame 推导。但 MB 的核心任务是发散性假设生成，此时 QuestionFrame 可能尚未完全成型（特别是第一个 epoch），evaluation_axes 可能不完整。
- **风险**：`infer_scope()` 的推导质量直接影响 `is_homologous()` 的准确性。如果推导出的 scope 过于宽泛（例如所有 MB 草稿都推导出 `["general"]`），Jaccard 会系统性地将不同草稿判为同源。
- **缓解措施**：为 `infer_scope()` 设置最低粒度要求（至少 2 个不同的 scope token），并在 normalize_mb 中加入断言检查。如果推导失败，应抛出编译错误而非静默填充。

**风险 2：跨来源 `is_homologous()` 的阈值校准（难度：高）**

- **问题**：MB 草稿和 repair 草稿的 `claim_sketch` 风格可能系统性不同（MB 倾向于探索性、宽泛的表述；repair 倾向于针对性、精确的表述）。固定的 Jaccard 阈值可能导致：阈值过高 → 跨来源同源草稿漏检 → 重复假设进入 L2；阈值过低 → 不同源草稿被错误折叠 → 知识空间覆盖度下降。
- **风险**：没有现成的标注数据来校准阈值，且 Jaccard 对 token 粒度高度敏感。
- **缓解措施**：初始阈值设为保守值（claim: 0.6, scope: 0.5），并在系统运行中收集 `is_homologous()` 的判断日志。引入可观测性钩子，允许在不改代码的情况下调整阈值。考虑在 Jaccard 之外引入 embedding cosine similarity 作为辅助信号（但不替代结构判断）。