# v3 认知引擎架构：repair() 策略与 is_homologous() 同源检测 裁判总结

> 2026-03-09T18:32:25.005485

# 裁判裁定书

---

## 第一部分：白话版结论

---

### E：repair() 的生成策略

**裁定：repair() 应采用"结构化策略为主体、受控松弛为降级"的分层方案，`suggested_dimension` 为软约束而非硬约束。**

让我用一个比喻来解释。

想象你在帮一个学生准备辩论赛。教练（Layer 2）告诉你："这个学生在'经济影响'这个角度的论证太弱了，建议他从'就业数据'方向补强。" 这就是 `GapSpec` 和 `suggested_dimension`。

Ssyram 的方案相当于说：学生必须严格按"就业数据"方向写论点，不许偏离半步。如果写了两轮都和已有论点撞车，就宣布"这个学生在这个角度已经没话可说了"，直接放弃。

Linus 的方案相当于说：让学生自由发挥，教练的建议只是参考，主要靠事后检查论点是否和已有的重复。

我的裁定取中间路线但偏向 Ssyram 的结构化方向，同时吸收 Linus 和康德对"不能把上游建议当神谕"的关键批评：

**具体例子：** 问题是"远程办公是否提高生产力"。Layer 2 报告说缺少"任务耦合度"维度的分析，建议从这个维度补充。

- **第 0 轮（严格绑定）：** repair 必须围绕"任务耦合度"生成草稿，比如"在高耦合任务团队中，远程办公降低迭代速度"。这是 Ssyram 的 E2 策略，此处完全正确。
- **第 1 轮（假设上一轮全被过滤）：** 不是直接终止，也不是自由发挥。而是对约束做**数学松弛**——放宽 scope（从"高耦合"放宽到"中等耦合"），或翻转 polarity（从"降低"变"不影响"），或换 outcome（从"迭代速度"换成"缺陷率"）。这吸收了 Ssyram 的松弛机制。
- **第 2 轮（仍然全被过滤）：** 将 `suggested_dimension` 降级为软约束——允许偏离到相邻维度（比如从"任务耦合度"滑到"沟通频率"），但必须保留与原始 gap 的可追溯关系。这是康德的 `dimensionPolicy` 思路。
- **第 3 轮（再次全被过滤）：** 对该 challenge 标记为 `EXHAUSTED`，但**不终止整个 epoch**——只终止该 challenge 的精化循环。其他 gap 和 challenge 继续处理。

**为什么不采用 Ssyram 的"两轮即终止"？** 因为 Linus 的反驳是致命的：连续被过滤只能证明"当前生成器在当前约束下穷尽了"，不能证明"知识空间穷尽了"。Ssyram 自己也承认 `gap_kind` 分类可能不完备，又引入了 `UNCLASSIFIED_ANOMALY` 逃生口——这恰恰证明穷尽判定不应该这么激进。

**为什么不采用完全自由的 E3？** 因为 Ssyram 的核心论点同样致命：不受约束的 LLM 会"维度漂移"，产出看似新颖但实际上是噪声的草稿。"任务耦合度"的 gap 不应该跑出"组织文化"的草稿。

**什么场景下可能需要修正：** 如果实际运行中发现，绝大多数 `suggested_dimension` 的误报率极低（<10%），那么第 0-1 轮的严格绑定期可以延长，Ssyram 的方案会更优。反过来，如果误报率高（>40%），则应从第 0 轮就采用软约束。这需要 corruption test 数据来校准。

**一句话总结：** repair() 是一个从严格到宽松的三级精化器，教练的建议先当真、撞墙后松绑、松完仍撞墙才放弃——但只放弃这一条路，不放弃整场比赛。

---

### F：is_homologous() 的判定算法

**裁定：is_homologous() 应采用二值输出的"provenance 约束 + 结构近似"判定器，内部可记录置信度，但对外只输出 BLOCK 或 PASS。**

再用一个比喻。

你是一个学术会议的论文查重审稿人。你收到一篇新投稿，需要判断它和已收录的论文是否"本质上说的是同一件事"。

康德说：你应该先看它们是否属于同一个理论流派（schema family），再看它们是否在讨论同一个维度，最后看它们能否形成有意义的正反对立。如果你拿不准，就标记为"待定"（AMBIGUOUS），放进一个特殊通道慢慢审。

Linus 说：你应该看它们的研究对象（scope）、核心结论（outcome）、论证方向（polarity）、和验证方法（verifier）是否结构相似。如果它们来自不同的研究缺口（gap_kind），除非结构上高度一致（>95%），否则默认不是同一篇。

Ssyram 说：上游投稿系统应该强制要求作者用标准模板提交，这样查重就是精确的字段匹配。

**我的裁定偏向 Linus 的方案，但吸收康德关于"跨 schema 表面差异"的警告：**

**具体例子：** 已有草稿 A："在高耦合团队中，远程办公降低迭代吞吐量"。新来草稿 B："在高耦合团队中，远程办公提高缺陷逃逸率"。

- 它们的 scope 相同（高耦合团队 + 远程办公），provenance 可能相同（同一个 gap）
- 但 outcome 不同（吞吐量 vs 缺陷率），verifier 也不同（需要不同的度量指标）
- **裁定：非同源。** 因为它们会消耗不同的验证路径，产生独立的知识增量

再看草稿 C："在缺乏异步协作工具的团队中，远程办公降低交付速度"。与草稿 A 比较：
- scope 高度重合（"高耦合" ≈ "缺乏异步协作工具"是同一现象的不同描述）
- outcome 高度重合（"迭代吞吐量" ≈ "交付速度"）
- polarity 相同，verifier 高度重合
- **裁定：同源。** 即使措辞完全不同，结构签名告诉我们它们会投射到几乎相同的验证骨架

**为什么不采用三值？** 因为 Ssyram 的攻击一针见血：在状态机中，门控只有"放"和"拦"两种物理动作。康德的 `AMBIGUOUS → PASS_WITH_QUARANTINE` 在控制流上就是放行（只是预算减半），那它本质上就是 `NOVEL` 的一个变体，不是独立的第三值。更危险的是，`AMBIGUOUS` 的判定依赖 `canFormAntinomy()`，这个函数需要深度语义分析——这要么调 LLM（成本爆炸），要么用启发式（回到 Linus 的方案）。三值在认识论上优雅，但在工程上它要么退化为二值，要么引入无法承受的复杂度。

**但我吸收康德的一个关键洞见：** Linus 把 `tension_source` 降到几乎无贡献是过度的。"是否来自同一认识框架"确实是判断同源的有用信号——不是决定性的，但也不应该是 0.02 权重的 tie-breaker。我的裁定是：`provenance_family`（来源类型）作为**分流条件**（决定走哪条判定路径和用哪组阈值），而不是作为相似度分数的一个加权项。这正是 Linus 第二轮修正后采用的方案结构。

**为什么不采用 Ssyram 的"强类型 AST 精确匹配"？** 因为 Linus 的致命反击成立：当前 `HypothesisDraft` 接口中没有 AST 字段，Ssyram 是在偷改协议。在不扩展接口的前提下，只能从 `claim_sketch` 和 `verifier_hint` 的文本中提取结构特征。是的，这是"结构代理"而非"真结构"——但 Linus 自己也承认这一点，并提出了可测试的退化条件。

**什么场景下可能需要修正：** 如果实际运行中发现，结构代理的提取失败率 >15%（即无法从 claim_sketch 中稳定提取 scope/outcome/polarity），则必须考虑扩展 `HypothesisDraft` 接口增加结构化字段（即部分接受 Ssyram 的方向，但通过正式的协议修订而非偷渡）。这是一个明确的迭代触发条件。

**一句话总结：** 判断两篇论文是否本质相同，看的是"研究对象+核心结论+验证方法"的骨架是否重合，而不是看它们措辞像不像、来自同一个研究缺口、或属于同一个理论流派——但来源信息决定用哪把尺子量。

---

## 第二部分：可实现性摘要

---

### 1. repair() 的完整函数签名和策略表

#### TypeScript 类型定义

```typescript
// ===== repair() 输入/输出类型 =====

type RefinementStage = "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";

type ChallengeTracker = {
  challenge_id: string;
  current_stage: RefinementStage;
  consecutive_filtered_epochs: number;  // 连续被 100% 过滤的轮数
  attempted_scopes: string[];           // 已尝试过的 scope 变体
  attempted_outcomes: string[];         // 已尝试过的 outcome 变体
  attempted_polarities: (1 | -1 | 0)[]; // 已尝试过的极性
};

type RepairContext = {
  frame: QuestionFrame;
  l2_return: L2Return;
  challenge_trackers: Map<string, ChallengeTracker>;
  // 来自 is_homologous 的拒绝记录，用于避免重复生成
  rejection_history: Array<{
    draft_signature: HomologyFeatures;
    blocked_by: string;
    epoch: number;
  }>;
};

type RepairResult = {
  new_drafts: HypothesisDraft[];
  updated_trackers: Map<string, ChallengeTracker>;
  exhausted_challenges: string[];  // 本轮标记为穷尽的 challenge IDs
};

function repair(ctx: RepairContext): RepairResult;
```

#### 策略表（Python 伪代码）

```python
def repair(ctx: RepairContext) -> RepairResult:
    new_drafts = []
    updated_trackers = {}
    exhausted = []

    # Phase 1: 处理 Gaps（来自 L2 的知识缺口）
    for gap in ctx.l2_return.new_gaps:
        drafts = repair_from_gap(gap, ctx.frame, ctx.rejection_history)
        new_drafts.extend(drafts)

    # Phase 2: 处理 Schema Challenges（来自 L2 的框架挑战）
    for challenge in ctx.l2_return.schema_challenges:
        tracker = ctx.challenge_trackers.get(
            challenge.id, 
            ChallengeTracker(challenge.id, "STRICT", 0, [], [], [])
        )
        
        stage = tracker.current_stage
        if stage == "EXHAUSTED":
            exhausted.append(challenge.id)
            continue

        drafts = repair_from_challenge(challenge, tracker, ctx)
        
        if not drafts:  # 当前 stage 无法产出任何新草稿
            tracker = advance_stage(tracker)
            if tracker.current_stage == "EXHAUSTED":
                exhausted.append(challenge.id)
            else:
                # 用新 stage 重试一次
                drafts = repair_from_challenge(challenge, tracker, ctx)
        
        new_drafts.extend(drafts)
        updated_trackers[challenge.id] = tracker

    return RepairResult(new_drafts, updated_trackers, exhausted)


def repair_from_gap(gap: GapSpec, frame: QuestionFrame, 
                     rejections: list) -> list[HypothesisDraft]:
    """从 GapSpec 生成草稿，策略取决于 gap_kind"""
    
    if gap.kind == "MISSING_DISCRIMINATOR":
        # 生成引入缺失判别维度的草稿
        # scope = gap 指向的分析区域
        # outcome = gap.discriminator 指向的度量
        # polarity = 分别生成正/反两个方向
        return generate_discriminator_drafts(gap, frame, rejections)
    
    elif gap.kind == "MISSING_OBSERVABLE":
        # 生成引入新可观测量的草稿
        return generate_observable_drafts(gap, frame, rejections)
    
    elif gap.kind == "PREMISE_UNDERSPECIFIED":
        # 生成细化前提条件的草稿
        return generate_premise_refinement_drafts(gap, frame, rejections)
    
    else:
        # 未分类异常 → 转化为 SchemaChallenge 处理
        return generate_exploratory_drafts(gap, frame, rejections)


def repair_from_challenge(challenge: SchemaChallengeNotice, 
                           tracker: ChallengeTracker,
                           ctx: RepairContext) -> list[HypothesisDraft]:
    """根据当前精化阶段，从 SchemaChallenge 生成草稿"""
    
    dim = challenge.suggested_dimension  # 可能为 None
    stage = tracker.current_stage
    
    if stage == "STRICT":
        # suggested_dimension 作为硬约束
        # 但生成时排除 rejection_history 中已尝试的 scope/outcome/polarity 组合
        return generate_strict_drafts(challenge, dim, tracker, ctx)
    
    elif stage == "RELAXED":
        # suggested_dimension 作为软约束
        # 允许：放宽 scope、翻转 polarity、替换 outcome
        # 禁止：完全脱离原始 gap 的语义区域
        return generate_relaxed_drafts(challenge, dim, tracker, ctx)
    
    elif stage == "ADJACENT":
        # suggested_dimension 仅作为锚点
        # 允许滑移到语义相邻的维度
        # 但必须保留与原始 challenge 的 provenance 链接
        return generate_adjacent_drafts(challenge, dim, tracker, ctx)
    
    return []


def advance_stage(tracker: ChallengeTracker) -> ChallengeTracker:
    """状态推进规则"""
    transitions = {
        "STRICT": "RELAXED",    # 严格绑定 → 约束松弛
        "RELAXED": "ADJACENT",  # 约束松弛 → 邻域探索
        "ADJACENT": "EXHAUSTED" # 邻域探索 → 穷尽
    }
    tracker.current_stage = transitions[tracker.current_stage]
    tracker.consecutive_filtered_epochs = 0  # 重置计数器
    return tracker
```

**策略推进触发条件：** 当某个 challenge 的 `consecutive_filtered_epochs >= 1`（即连续 1 轮该 challenge 产出的草稿 100% 被 `is_homologous` 过滤），推进到下一个 stage。注意是**该 challenge** 的草稿全被过滤，不是整个 epoch 的所有草稿全被过滤。

---

### 2. is_homologous() 的完整判定算法

#### TypeScript 类型

```typescript
type HomologyFeatures = {
  provenance_family: string;        // gap_kind 或 challenge 类型
  dimension_key: string | null;     // 归一化后的维度标识
  scope_tokens: string[];           // 从 scope_ref + claim_sketch 提取的归一化 scope 标记
  outcome_anchor: string;           // 核心结果变量（归一化）
  polarity: 1 | -1 | 0;            // 方向：正/负/中性
  verifier_tokens: string[];        // 从 verifier_hint 提取的验证标记
};

type HomologyResult = {
  is_homologous: boolean;
  blocked_by: string | null;        // 匹配到的已有草稿 ID
  confidence: number;               // 0-1，内部诊断用，不影响判定
  reason: string[];                 // 人可读的判定依据
};

function is_homologous(
  candidate: HypothesisDraft,
  existing_pool: HypothesisDraft[],
  gap_index: Record<string, GapSpec>
): HomologyResult;
```

#### 完整判定算法（Python 伪代码）

```python
def is_homologous(candidate, existing_pool, gap_index) -> HomologyResult:
    """
    二值判定：candidate 是否与 existing_pool 中某个草稿同源。
    
    核心原则：
    - provenance_family 决定判定路径和阈值（分流条件）
    - 结构特征（scope/outcome/polarity/verifier）决定最终判定
    - tension_source.kind 仅用于解释，不参与分数计算
    
    复杂度：O(|existing_pool| * max(|scope_tokens|, |verifier_tokens|))
    对于典型 pool 大小 (<100) 和 token 集 (<50)，单次判定 <1ms
    """
    
    a = extract_features(candidate, gap_index)
    
    for e in existing_pool:
        b = extract_features(e, gap_index)
        result = compare_pair(a, b, candidate, e)
        if result.is_homologous:
            return result
    
    return HomologyResult(
        is_homologous=False,
        blocked_by=None,
        confidence=0.0,
        reason=["no structural homology hit in pool"]
    )


def extract_features(draft: HypothesisDraft, gap_index) -> HomologyFeatures:
    """
    从 HypothesisDraft 的现有字段提取结构特征。
    
    关键设计决策：
    - 这是"预编译结构代理"，不是精确 AST
    - 提取失败时返回空/默认值，由 compare_pair 中的阈值处理
    - 不依赖任何接口外的字段
    """
    
    # 1. provenance_family: 从 provenance 或 tension_source 抽取
    prov_family = classify_provenance(draft.provenance, gap_index)
    
    # 2. dimension_key: 从关联的 gap/challenge 中提取并归一化
    dim_key = extract_dimension_key(draft, gap_index)
    
    # 3. scope_tokens: 从 scope_ref 和 claim_sketch 的条件部分提取
    scope_tokens = extract_scope_tokens(draft.scope_ref, draft.claim_sketch)
    
    # 4. outcome_anchor: 从 claim_sketch 的结果部分提取核心变量
    outcome = extract_outcome(draft.claim_sketch)
    
    # 5. polarity: 从 claim_sketch 判断方向
    polarity = extract_polarity(draft.claim_sketch)
    
    # 6. verifier_tokens: 从 verifier_hint 提取
    verifier_tokens = normalize_and_tokenize(draft.verifier_hint)
    
    return HomologyFeatures(prov_family, dim_key, scope_tokens, 
                             outcome, polarity, verifier_tokens)


def compare_pair(a: HomologyFeatures, b: HomologyFeatures,
                  draft_a, draft_b) -> HomologyResult:
    """
    核心判定逻辑：基于 provenance 分流，结构特征决定。
    
    路径 1（同源家族）：阈值较松，因为来自同一缺口的草稿更可能是表面改写
    路径 2（异源家族）：阈值极严，除非结构几乎完全一致否则不判同源
    """
    
    same_family = (a.provenance_family == b.provenance_family)
    same_dimension = (a.dimension_key is not None and 
                       a.dimension_key == b.dimension_key)
    
    scope_sim = jaccard(a.scope_tokens, b.scope_tokens)
    outcome_match = normalized_match(a.outcome_anchor, b.outcome_anchor)
    polarity_match = (a.polarity == b.polarity)
    verifier_sim = jaccard(a.verifier_tokens, b.verifier_tokens)
    
    reasons = []
    
    # ===== 路径 1：同源家族 =====
    if same_family:
        if same_dimension:
            # 同家族 + 同维度：最可能是同源改写
            # 阈值：scope≥0.80, outcome匹配, polarity相同, verifier≥0.75
            if (scope_sim >= 0.80 and outcome_match and 
                polarity_match and verifier_sim >= 0.75):
                reasons.append(f"same-family({a.provenance_family}) "
                             f"same-dim({a.dimension_key}) "
                             f"scope={scope_sim:.2f} ver={verifier_sim:.2f}")
                return HomologyResult(True, draft_b.id, 
                                       min(scope_sim, verifier_sim), reasons)
        else:
            # 同家族 + 不同维度：仍可能同源，但阈值提高
            if (scope_sim >= 0.90 and outcome_match and 
                polarity_match and verifier_sim >= 0.85):
                reasons.append(f"same-family cross-dim "
                             f"scope={scope_sim:.2f} ver={verifier_sim:.2f}")
                return HomologyResult(True, draft_b.id,
                                       min(scope_sim, verifier_sim) * 0.9, reasons)
    
    # ===== 路径 2：异源家族 =====
    else:
        # 不同家族：仅在结构极高重合时才判同源
        # 这是对康德"跨 schema 表面差异"警告的回应
        if (scope_sim >= 0.95 and outcome_match and 
            polarity_match and verifier_sim >= 0.90):
            reasons.append(f"cross-family structural convergence "
                         f"scope={scope_sim:.2f} ver={verifier_sim:.2f}")
            return HomologyResult(True, draft_b.id,
                                   min(scope_sim, verifier_sim) * 0.8, reasons)
    
    # ===== 未命中 =====
    return HomologyResult(False, None, 0.0, 
                           [f"below threshold: scope={scope_sim:.2f} "
                            f"out={outcome_match} pol={polarity_match} "
                            f"ver={verifier_sim:.2f}"])
```

#### 辅助函数的归一化策略

```python
def extract_scope_tokens(scope_ref: list[str], claim_sketch: str) -> list[str]:
    """
    从 scope_ref（结构化）和 claim_sketch（自由文本的条件部分）提取归一化标记。
    
    策略：
    1. scope_ref 直接作为 token 源（已经半结构化）
    2. claim_sketch 中提取条件从句的名词短语
    3. 合并、去重、排序
    4. 同义词归一化（维护一个小型同义词表，可随运行积累）
    
    退化行为：如果提取失败（如 claim_sketch 无法解析），
    仅使用 scope_ref，并在 reason 中标记 "scope_extraction_partial"
    """
    tokens = list(scope_ref)  # scope_ref 本身是 string[]
    
    # 从 claim_sketch 的条件部分提取补充 tokens
    condition_part = extract_condition_clause(claim_sketch)
    if condition_part:
        noun_phrases = extract_noun_phrases(condition_part)
        tokens.extend(noun_phrases)
    
    # 归一化
    tokens = [normalize_synonym(t) for t in tokens]
    return sorted(set(tokens))


def extract_outcome(claim_sketch: str) -> str:
    """
    从 claim_sketch 中提取核心结果变量。
    
    策略：提取主句的宾语/表语核心名词
    例："远程办公降低迭代吞吐量" → "迭代吞吐量"
    例："remote work reduces defect escape rate" → "defect_escape_rate"
    
    退化行为：如果无法提取，返回 claim_sketch 的哈希摘要前 8 位。
    此时 outcome_match 会对大多数比较返回 False，
    相当于"提取失败 → 不判同源"，这是安全的保守方向。
    """
    result_clause = extract_result_clause(claim_sketch)
    if result_clause:
        return normalize_synonym(extract_core_noun(result_clause))
    return f"__hash_{hash(claim_sketch)[:8]}"


def normalized_match(outcome_a: str, outcome_b: str) -> bool:
    """
    判断两个 outcome anchor 是否指向同一结果变量。
    精确匹配 + 同义词表匹配。
    不使用 embedding 相似度（避免过度模糊）。
    """
    return outcome_a == outcome_b or are_synonyms(outcome_a, outcome_b)
```

#### 复杂度分析

| 操作 | 复杂度 | 说明 |
|------|--------|------|
| `extract_features` | O(L) | L = claim_sketch 长度，单次文本解析 |
| `jaccard(A, B)` | O(\|A\| + \|B\|) | 基于排序集合的交/并计算 |
| `compare_pair` | O(\|scope\| + \|verifier\|) | 两次 Jaccard + 常数项比较 |
| `is_homologous` 总体 | O(P × (L + S + V)) | P = pool 大小，S/V = scope/verifier token 集大小 |
| 典型场景 | P<100, L<500, S<30, V<20 | **<1ms 单次调用** |

---

### 3. 数据流类型定义：repair → is_homologous → ClarityCompiler

```typescript
// ===== 完整数据流类型定义 =====

// [Stage 0] L2Return 信号（来自 Layer 2）
interface L2Return {
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  ranking_delta: { changed: boolean; details?: string };
  epoch_id: number;
}

interface GapSpec {
  gap_id: string;
  kind: "MISSING_DISCRIMINATOR" | "MISSING_OBSERVABLE" | "PREMISE_UNDERSPECIFIED" | "UNCLASSIFIED";
  discriminator?: string;
  evidence_summary: string;
}

interface SchemaChallengeNotice {
  challenge_id: string;
  trigger: "REPLAY_REGRESSION" | "COVERAGE_GAP" | "ANOMALY";
  suggested_dimension?: string;
  is_homologous: boolean;
  description: string;
}

// [Stage 1] repair() 的输出
interface HypothesisDraft {
  draft_id: string;
  scope_ref: string[];
  tension_source: { kind: string; detail: string };
  claim_sketch: string;
  verifier_hint: string;
  provenance: {
    source_gap_id?: string;
    source_challenge_id?: string;
    repair_stage: RefinementStage;
    epoch: number;
  };
}

// [Stage 2] is_homologous() 的输出
interface FilteredDraftSet {
  passed: Array<{
    draft: HypothesisDraft;
    homology_check: HomologyResult;  // is_homologous=false 的那些
  }>;
  blocked: Array<{
    draft: HypothesisDraft;
    homology_check: HomologyResult;  // is_homologous=true 的那些
  }>;
  filter_stats: {
    total_candidates: number;
    passed_count: number;
    blocked_count: number;
    blocked_ratio: number;  // 用于触发 repair 降级
  };
}

// [Stage 3] ClarityCompiler 的输入（仅接收 passed drafts）
interface CCInput {
  drafts: HypothesisDraft[];    // FilteredDraftSet.passed 中的 drafts
  frame: QuestionFrame;
  existing_claims: TestableClaim[];  // 已有的可验证命题
}

// [Stage 4] ClarityCompiler 的输出
interface CCOutput {
  new_claims: TestableClaim[];
  compilation_failures: Array<{
    draft_id: string;
    failure_reason: string;
  }>;
}

interface TestableClaim {
  claim_id: string;
  source_draft_id: string;
  falsifiable_statement: string;
  required_evidence_types: string[];
  verification_protocol: string;
  scope_boundary: string[];
}

// [Stage 5] 进入下一个 Epoch 的完整状态更新
interface EpochTransition {
  new_claims: TestableClaim[];           // 进入 D2 派发
  updated_trackers: Map<string, ChallengeTracker>;  // 更新精化状态
  exhausted_challenges: string[];         // 标记为穷尽的 challenge
  rejection_additions: Array<{            // 新增拒绝记录
    draft_signature: HomologyFeatures;
    blocked_by: string;
    epoch: number;
  }>;
  breadth_overrun: boolean;               // 是否触发广度过热刹车
}
```

---

### 4. 完整运行 Trace 示例

**问题：** "远程办公是否提高软件团队生产力？"

**起始状态：** Epoch 3，已有 3 个 TestableClaim，Layer 2 刚返回 L2Return。

```
===== EPOCH 3 → EPOCH 4 =====

[STEP 0] L2Return 信号到达 Layer 1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L2Return = {
  epoch_id: 3,
  new_gaps: [
    {
      gap_id: "gap-007",
      kind: "MISSING_DISCRIMINATOR",
      discriminator: "task_coupling_degree",
      evidence_summary: "现有假设未区分高/低耦合任务团队"
    }
  ],
  schema_challenges: [
    {
      challenge_id: "sc-003",
      trigger: "COVERAGE_GAP",
      suggested_dimension: "communication_frequency",
      is_homologous: false,
      description: "缺少沟通频率维度的分析"
    }
  ],
  ranking_delta: { changed: false }
}

已有 challenge_trackers:
  sc-003: { stage: "STRICT", consecutive_filtered: 0, ... }

已有 existing_pool (草稿池):
  [draft-A] "在大型团队中，远程办公降低会议效率"
            scope=["大型团队"], outcome="会议效率", polarity=-1
            provenance_family="MISSING_OBSERVABLE"
  [draft-B] "在创业公司中，远程办公提高个人产出"
            scope=["创业公司"], outcome="个人产出", polarity=+1
            provenance_family="PREMISE_UNDERSPECIFIED"
  [draft-C] "在跨时区团队中，远程办公增加沟通延迟"
            scope=["跨时区团队"], outcome="沟通延迟", polarity=+1
            provenance_family="MISSING_DISCRIMINATOR"


[STEP 1] repair(ctx) 执行
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 1: 处理 gap-007 (MISSING_DISCRIMINATOR, discriminator="task_coupling_degree")
  → 生成 draft-D: "在高任务耦合团队中，远程办公降低迭代吞吐量"
      scope_ref: ["高任务耦合团队"]
      claim_sketch: "在高任务耦合团队中，远程办公降低迭代吞吐量"
      verifier_hint: "比较高/低耦合团队的迭代周期时长"
      provenance: { source_gap_id: "gap-007", repair_stage: "STRICT" }
  → 生成 draft-E: "在低任务耦合团队中，远程办公不影响迭代吞吐量"
      scope_ref: ["低任务耦合团队"]
      claim_sketch: "在低任务耦合团队中，远程办公不影响迭代吞吐量"
      verifier_hint: "比较高/低耦合团队的迭代周期时长"
      provenance: { source_gap_id: "gap-007", repair_stage: "STRICT" }

Phase 2: 处理 sc-003 (COVERAGE_GAP, suggested_dimension="communication_frequency")
  tracker.stage = "STRICT" → suggested_dimension 作为硬约束
  → 生成 draft-F: "在高沟通频率团队中，远程办公降低沟通质量"
      scope_ref: ["高沟通频率团队"]
      claim_sketch: "在高沟通频率需求的团队中，远程办公降低同步沟通质量"
      verifier_hint: "对比远程/办公室环境下的沟通满意度与决策速度"
      provenance: { source_challenge_id: "sc-003", repair_stage: "STRICT" }

repair() 输出: [draft-D, draft-E, draft-F]
updated_trackers: { sc-003: { stage: "STRICT", consecutive_filtered: 0 } }


[STEP 2] is_homologous() 过滤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

检查 draft-D vs existing_pool:
  vs draft-A: provenance_family 不同 (MISSING_DISCRIMINATOR vs MISSING_OBSERVABLE)
    → 路径 2（异源家族）
    scope_sim = jaccard(["高任务耦合团队"], ["大型团队"]) = 0.20
    → 远低于 0.95 阈值 → PASS
  vs draft-B: provenance_family 不同
    scope_sim = jaccard(["高任务耦合团队"], ["创业公司"]) = 0.0
    → PASS
  vs draft-C: provenance_family 相同 (MISSING_DISCRIMINATOR)
    dimension_key: "task_coupling_degree" vs null (C 没有明确 dimension)
    → 不同维度，走同家族+不同维度路径
    scope_sim = jaccard(["高任务耦合团队"], ["跨时区团队"]) = 0.25
    → 远低于 0.90 阈值 → PASS
  ✅ draft-D: NOT HOMOLOGOUS → PASS

检查 draft-E vs existing_pool:
  vs draft-A: 异源，scope_sim 低 → PASS
  vs draft-B: 异源，scope_sim 低 → PASS
  vs draft-C: 同源家族，不同维度，scope_sim 低 → PASS
  vs draft-D: 同源家族 (MISSING_DISCRIMINATOR), 同维度 (task_coupling_degree)
    scope_sim = jaccard(["低任务耦合团队"], ["高任务耦合团队"]) = 0.60
    → 低于 0.80 阈值（"高"vs"低"是不同 scope）→ PASS
    [注：这正是 Linus 场景 A/B 例子的变体，scope 不同应放行]
  ✅ draft-E: NOT HOMOLOGOUS → PASS

检查 draft-F vs existing_pool:
  vs draft-A: 异源，scope_sim 低 → PASS
  vs draft-B: 异源，scope_sim 低 → PASS
  vs draft-C: 异源 (COVERAGE_GAP vs MISSING_DISCRIMINATOR)
    scope_sim = jaccard(["高沟通频率团队"], ["跨时区团队"]) = 0.15
    → 远低于 0.95 → PASS
    [注：虽然"沟通频率"和"跨时区沟通延迟"语义相关，但结构特征分散，不构成同源]
  vs draft-D: 异源，scope_sim 低 → PASS
  vs draft-E: 异源，scope_sim 低 → PASS
  ✅ draft-F: NOT HOMOLOGOUS → PASS

FilteredDraftSet = {
  passed: [draft-D, draft-E, draft-F],
  blocked: [],
  filter_stats: { total: 3, passed: 3, blocked: 0, blocked_ratio: 0.0 }
}


[STEP 3] ClarityCompiler 编译
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CC 接收 [draft-D, draft-E, draft-F]:

draft-D → TestableClaim:
  {
    claim_id: "tc-004",
    source_draft_id: "draft-D",
    falsifiable_statement: "在任务耦合度高于阈值 T 的软件团队中，
                           切换到远程办公后迭代周期时长增加 ≥15%",
    required_evidence_types: ["iteration_cycle_data", "coupling_metric"],
    verification_protocol: "准实验：匹配高耦合团队的远程前后迭代数据",
    scope_boundary: ["高任务耦合团队", "软件开发", "迭代交付"]
  }

draft-E → TestableClaim:
  {
    claim_id: "tc-005",
    source_draft_id: "draft-E",
    falsifiable_statement: "在任务耦合度低于阈值 T 的软件团队中，
                           远程办公对迭代周期时长的影响在 ±5% 以内",
    required_evidence_types: ["iteration_cycle_data", "coupling_metric"],
    verification_protocol: "等价性检验：比较低耦合团队远程前后迭代数据",
    scope_boundary: ["低任务耦合团队", "软件开发", "迭代交付"]
  }

draft-F → TestableClaim:
  {
    claim_id: "tc-006",
    source_draft_id: "draft-F",
    falsifiable_statement: "在日均同步沟通需求 >2 小时的团队中，
                           远程办公使沟通满意度评分下降 ≥20%",
    required_evidence_types: ["communication_satisfaction_survey", 
                               "sync_communication_hours"],
    verification_protocol: "前后对比调查 + 沟通日志分析",
    scope_boundary: ["高沟通频率团队", "远程办公", "沟通质量"]
  }

CCOutput = {
  new_claims: [tc-004, tc-005, tc-006],
  compilation_failures: []
}


[STEP 4] EpochTransition → Epoch 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EpochTransition = {
  new_claims: [tc-004, tc-005, tc-006],  // 3 个新命题进入 D2 派发
  updated_trackers: {
    sc-003: { stage: "STRICT", consecutive_filtered: 0 }
    // 未被过滤，保持 STRICT，计数器不变
  },
  exhausted_challenges: [],
  rejection_additions: [],  // 本轮无阻断
  breadth_overrun: false    // 3 个新命题，远未触及广度过热
}

existing_pool 更新为:
  [draft-A, draft-B, draft-C, draft-D, draft-E, draft-F]

Epoch 4 启动：
  tc-004, tc-005, tc-006 进入 Layer 2 的 DepthProbe
  Layer 2 将尝试验证这些命题，并返回新的 L2Return
```

**降级场景示例（假设 Epoch 5 中 sc-003 被过滤）：**

```
[EPOCH 5 补充 trace - 降级场景]

假设 Epoch 4 的 L2Return 中 sc-003 再次出现（Layer 2 认为沟通频率维度仍需补充），
repair 在 STRICT 阶段产出 draft-G:
  "在高沟通频率团队中，远程办公增加异步沟通比例"
  scope=["高沟通频率团队"], outcome="异步沟通比例"

is_homologous 检查 draft-G vs draft-F:
  同源家族 (COVERAGE_GAP), 同维度 (communication_frequency)
  scope_sim = jaccard(["高沟通频率团队"], ["高沟通频率团队"]) = 1.00
  outcome: "异步沟通比例" vs "同步沟通质量