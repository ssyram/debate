# 模块名：假设草稿（Hypothesis Draft / HypothesisDraft Schema）

<!-- import from 00_shared_types: HypothesisDraft, TensionSource, Provenance, QuestionFrame -->

## 一句话定位

定义 MB 和 repair() 共享的统一草稿类型，提供两套规范化工厂函数（`normalize_mb` / `normalize_repair`），以及草稿同源性判定（`is_homologous`）和语义相似度计算（`compute_semantic_similarity`）的接口——是所有草稿进入共享流水线前的"通关检验站"。

---

## 通俗解释

想象一个国际邮局的分拣流水线。中国寄来的包裹有中文面单，德国寄来的有德文面单，格式完全不同。但进入分拣流水线之前，**每个包裹都必须贴上一张统一格式的国际标签**——收件人、重量、目的地、是否易碎，全部用同一套字段填写。

`HypothesisDraft` 就是这张统一标签。无论草稿来自初始广度探索（MB）还是 L2 验证失败后的修复（repair），在进入 CC 编译、同源性去重、PA 评分之前，都必须通过工厂函数转换为这个统一类型。

分拣员（CC、is_homologous）只看这张标签，不需要知道包裹来自哪条生产线。

---

## 接口定义（TypeScript 类型）

完整类型定义见 `00_shared_types.md` 中的 `HypothesisDraft`。本文件补充规范化工厂函数接口：

```typescript
// import from 00_shared_types: HypothesisDraft, QuestionFrame, GapSpec

interface RawMBDraft {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  scope_ref: string[];    // MB 可能产出空数组，normalize_mb 必须推导填充
  verifier_hint: string[];
  open_term_risk: string[];
  tension_source: TensionSource;
  ttl: number;
}

interface RawRepairDraft {
  claim_sketch: string;
  tension_kind: TensionKind;
  verifier_hint: string | string[];  // repair 可能产出单 string，需要包装
  scope_ref: string[];               // 从 GapSpec 继承，必填
  detail: string;
}

interface RepairContext {
  frame: QuestionFrame;
  gap_id: string;
  challenge_id: string;
  current_stage: "STRICT" | "RELAXED" | "ADJACENT";
}

// 规范化工厂函数
function normalize_mb(raw: RawMBDraft, frame: QuestionFrame): HypothesisDraft;
function normalize_repair(raw: RawRepairDraft, ctx: RepairContext): HypothesisDraft;

// 同源性判定
interface HomologyThreshold {
  claim_jaccard: number;  // 默认 0.6
  scope_jaccard: number;  // 默认 0.5
}

interface HomologyFeatures {
  claim_tokens: Set<string>;
  scope_set: Set<string>;
  tension_kind: TensionKind;
  problem_id: string;
}

function extract_homology_features(draft: HypothesisDraft): HomologyFeatures;
function is_homologous(a: HypothesisDraft, b: HypothesisDraft, threshold?: HomologyThreshold): boolean;
function compute_semantic_similarity(a: HypothesisDraft, b: HypothesisDraft): number; // [0, 1]
```

---

## 伪代码实现（Python 风格）

```python
DEFAULT_CLAIM_THRESHOLD = 0.6
DEFAULT_SCOPE_THRESHOLD = 0.5


def normalize_mb(raw: RawMBDraft, frame: QuestionFrame) -> HypothesisDraft:
    """MB 草稿规范化工厂函数"""

    # scope_ref 禁止空数组：从 QuestionFrame 强制推导
    scope_ref = raw.scope_ref
    if not scope_ref:
        scope_ref = infer_scope_from_frame(raw, frame)
        if len(scope_ref) < 2:
            raise CompileError(
                f"normalize_mb: scope_ref 推导质量不足（{scope_ref}），"
                f"无法满足最低粒度要求（至少 2 个不同 token）"
            )

    return HypothesisDraft(
        draft_id=raw.draft_id,
        problem_id=raw.problem_id,
        claim_sketch=raw.claim_sketch,
        scope_ref=scope_ref,          # 保证非空
        verifier_hint=raw.verifier_hint,  # MB 已经是 string[]
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
            ttl=raw.ttl  # MB 特有的生命周期预算
        )
    )


def normalize_repair(raw: RawRepairDraft, ctx: RepairContext) -> HypothesisDraft:
    """Repair 草稿规范化工厂函数"""

    # verifier_hint 统一为 list[str]
    if isinstance(raw.verifier_hint, str):
        verifier_hint = [raw.verifier_hint]
    else:
        verifier_hint = raw.verifier_hint

    # open_term_risk 从 L2 失败上下文推导（允许 []）
    open_term_risk = infer_open_term_risk_from_ctx(raw, ctx) or []

    # evidence_ref 从 challenge 上下文提取
    evidence_ref = extract_evidence_from_challenge(ctx) or []

    return HypothesisDraft(
        draft_id=generate_id("repair"),
        problem_id=ctx.frame.problem_id,  # 由 L1 调度层注入
        claim_sketch=raw.claim_sketch,
        scope_ref=raw.scope_ref,  # 从 GapSpec 继承，必须非空
        verifier_hint=verifier_hint,
        open_term_risk=open_term_risk,
        tension_source=TensionSource(
            kind=raw.tension_kind,  # "GAP_REPAIR" | "SCHEMA_REPAIR"
            tier="L2_FAILURE",
            evidence_ref=evidence_ref,
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


def infer_scope_from_frame(raw: RawMBDraft, frame: QuestionFrame) -> list[str]:
    """从 QuestionFrame 推导 scope_ref（当 MB 产出空数组时调用）"""
    scope = []

    # 从 evaluation_axes 收集轴 ID
    for ax in frame.evaluation_axes:
        if ax.axis_id in raw.claim_sketch.lower() or ax.label.lower() in raw.claim_sketch.lower():
            scope.append(ax.axis_id)

    # 从 stakeholders 收集相关方
    for sh in frame.stakeholders:
        if sh.lower() in raw.claim_sketch.lower():
            scope.append(f"stakeholder:{sh}")

    # 最后兜底：使用前两个轴
    if len(scope) < 2:
        scope = [ax.axis_id for ax in frame.evaluation_axes[:2]]

    return list(set(scope))


# ====================================
# 同源性判定
# ====================================

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
    threshold: HomologyThreshold | None = None
) -> bool:
    """
    二值判断：两个草稿是否探索同一知识空间。
    注意：不同 source（MB vs REPAIR）也可以同源，跨来源比较是正常场景。
    """
    fa = extract_homology_features(a)
    fb = extract_homology_features(b)

    # 快速排除：不同 problem 框架下的草稿不可能同源
    if fa.problem_id != fb.problem_id:
        return False

    ct = threshold.claim_jaccard if threshold else DEFAULT_CLAIM_THRESHOLD
    st = threshold.scope_jaccard if threshold else DEFAULT_SCOPE_THRESHOLD

    claim_sim = jaccard(fa.claim_tokens, fb.claim_tokens)
    scope_sim  = jaccard(fa.scope_set, fb.scope_set)

    # claim 和 scope 均超过阈值才算同源
    return claim_sim >= ct and scope_sim >= st


def compute_semantic_similarity(a: HypothesisDraft, b: HypothesisDraft) -> float:
    """
    连续语义度量（[0, 1]），用于多样性优化。
    不得与 is_homologous() 混用：后者是结构判断，前者是语义距离。
    """
    embedding_a = get_embedding(a.claim_sketch)
    embedding_b = get_embedding(b.claim_sketch)
    return cosine_similarity(embedding_a, embedding_b)


def jaccard(set_a: set[str], set_b: set[str]) -> float:
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-HD-01 | `scope_ref` 禁止空数组——Jaccard 对空集会使所有候选被误判为完全不同源 | `normalize_mb` 内 raise |
| INV-HD-02 | `tension_source.tier` 对 repair 草稿必须为 `"L2_FAILURE"` 或 `"STRUCTURAL"` | 工厂函数硬编码 |
| INV-HD-03 | `provenance.ttl` 仅存在于 MB 草稿中；读取 ttl 前必须检查 `provenance.source == "MB"` | 可选字段类型 |
| INV-HD-04 | `is_homologous()` 不得读取 `provenance.source`——来源分支是错误的 | 代码审查约定 |
| INV-HD-05 | CC 的 `clarity_compile()` 不得读取 `provenance.source`——同上 | 代码审查约定 |
| INV-HD-06 | `is_homologous(a, b)` 蕴含 `compute_semantic_similarity(a, b) > 0.6`，反之不成立 | 测试覆盖 |
| INV-HD-07 | 两个函数不得互相调用 | 代码审查约定 |
| INV-HD-08 | repair 草稿的 `scope_ref` 必须继承自触发修复的 `GapSpec.axis_id` | 工厂函数约定 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"

### 场景 A：MB 产出草稿（normalize_mb）

```
MB 产出 RawMBDraft:
  draft_id: "mb-001"
  problem_id: "q-carbon-001-r1"
  claim_sketch: "配额分配基于历史排放量会固化既有排放权，
                 不利于后发国家的经济发展"
  scope_ref: []  ← MB 未能推导，为空数组
  verifier_hint: ["比较不同配额分配机制下发展中国家的年 GDP 增长率"]
  open_term_risk: []
  tension_source: {
    kind: "STAKEHOLDER_CONFLICT",
    tier: "EMPIRICAL",
    evidence_ref: ["IPCC AR6 Ch12", "WTO 2023 Trade Report"],
    note: "发展中国家政府 vs 发达国家政府在配额基准上的冲突"
  }
  ttl: 3

调用 normalize_mb(raw, frame):
  scope_ref 为空 → infer_scope_from_frame():
    - "配额" 命中 ax_equity → 加入 "ax_equity"
    - "经济发展" 命中 ax_economic → 加入 "ax_economic"
    - 兜底检查：len(scope) = 2 ≥ 2 → 通过
    → scope_ref = ["ax_equity", "ax_economic"]

输出 HypothesisDraft:
  draft_id: "mb-001"
  problem_id: "q-carbon-001-r1"
  claim_sketch: "配额分配基于历史排放量会固化既有排放权..."
  scope_ref: ["ax_equity", "ax_economic"]    ← 已推导，非空
  verifier_hint: ["比较不同配额分配机制下发展中国家的年 GDP 增长率"]
  tension_source.tier: "EMPIRICAL"
  provenance: { source: "MB", epoch: 1, ttl: 3 }
```

### 场景 B：Repair 产出草稿（normalize_repair）

```
L2 验证发现：ax_capacity 轴缺少高权重覆盖（GapSpec: gap-007）

Repair 生成 RawRepairDraft:
  claim_sketch: "引入能力调整系数（CDR）可以量化各国绝对减排能力差异，
                 为差异化义务分担提供客观基准"
  tension_kind: "GAP_REPAIR"
  verifier_hint: "若 CDR 与各国历史人均 GDP 增长率相关性 > 0.7 则通过"  ← 单 string
  scope_ref: ["ax_capacity"]      ← 继承自 GapSpec
  detail: "gap-007: ax_capacity 高权重轴无 claim 覆盖"

RepairContext:
  frame: QuestionFrame(problem_id="q-carbon-001-r1")
  gap_id: "gap-007"
  challenge_id: "ch-003"
  current_stage: "STRICT"

调用 normalize_repair(raw, ctx):
  verifier_hint: str → 包装为 ["若 CDR 与各国历史人均 GDP 增长率相关性 > 0.7 则通过"]
  evidence_ref: extract_evidence_from_challenge(ctx) → ["ch-003 描述", "gap-007 上下文"]

输出 HypothesisDraft:
  draft_id: "repair-00a1"
  problem_id: "q-carbon-001-r1"    ← 由 ctx.frame 注入
  claim_sketch: "引入能力调整系数（CDR）..."
  scope_ref: ["ax_capacity"]
  verifier_hint: ["若 CDR 与各国历史人均 GDP 增长率相关性 > 0.7 则通过"]
  tension_source: { kind: "GAP_REPAIR", tier: "L2_FAILURE", ... }
  provenance: { source: "REPAIR", epoch: 3, source_gap_id: "gap-007",
                source_challenge_id: "ch-003", repair_stage: "STRICT" }
```

### 场景 C：is_homologous() 判断两个草稿是否同源

```
草稿 A（MB 来源）:
  claim_sketch: "配额分配基于历史排放量会固化既有排放权"
  scope_ref: ["ax_equity", "ax_economic"]
  problem_id: "q-carbon-001-r1"

草稿 B（Repair 来源）:
  claim_sketch: "历史排放基准的配额机制系统性地偏向高历史排放国"
  scope_ref: ["ax_equity", "ax_burden_share"]
  problem_id: "q-carbon-001-r1"

is_homologous(A, B):
  fa.problem_id == fb.problem_id → 通过快速排除
  claim_tokens A: {"配额", "分配", "历史", "排放量", "固化", "排放权"}
  claim_tokens B: {"历史", "排放", "基准", "配额", "机制", "系统性", "偏向", "排放国"}
  claim_jaccard = |{配额, 历史, 排放}| / |A ∪ B| = 3/11 ≈ 0.27  < 0.6 ← 不满足
  → 判定：NOT homologous

  （注：两个草稿语义相近，但 claim_jaccard 因表述差异低于阈值；
    这说明系统不会误折叠措辞不同但语义类似的草稿——是刻意保留多样性）

compute_semantic_similarity(A, B) → 约 0.72（embedding 捕获语义接近）
  → A 和 B 多样性分数适中，保留两者
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-4~~** → **已裁定** ✅（完整裁定见 `00_shared_types.md` 中 HypothesisDraft 定义）
> - 裁定结论：评估轴配置在 epoch 0 冻结为 `AxesSnapshot`（不可变），轴变更通过 `SCHEMA_CHALLENGE_NEW` + PA 审批产生新快照；`HypothesisDraft` 统一定义以 `00_shared_types.md` 为准（含 `problem_id`、`open_term_risk`、`verifier_hint: string[]`），repair_strategy 必须通过 `normalize_repair()` 生成草稿，`is_homologous()` 的 `problem_id` 快速排除路径在此约束下得以正确工作。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`
