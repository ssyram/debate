# 模块名：修复策略（Repair Strategy / RB 节点）

<!-- import from 00_shared_types: GapSpec, RepairGapKind, HypothesisDraft, L2Return, EpochDelta, VerifiedClaimFull -->
<!-- import from 02_hypothesis_draft: normalize_repair, RepairContext -->

## 一句话定位

接收 Layer 2 返回的 `GapSpec`（知识缺口），通过三级渐进策略（STRICT → RELAXED → ADJACENT）生成修复草稿，利用 AST 哈希负向约束（`is_unsat()`）避免重复已失败的方向——是 CEGAR 反馈回路的修复引擎。

---

## 通俗解释

想象你是工厂里的质检维修工（repair 模块），质检流水线（Layer 2）告诉你某个产品有问题：

- "这个齿轮缺少判别维度"（`MISSING_DISCRIMINATOR`）
- "这里缺少可观测量"（`MISSING_OBSERVABLE`）

你有三种修复策略，从保守到激进：

1. **STRICT（精确修复）**：沿着原来的设计，找到具体缺失的那个螺丝，精确加上去。
2. **RELAXED（松弛修复）**：原来的方案改动比较大，但还是在同一个零件族里找替代方案。
3. **ADJACENT（相邻探索）**：换一个完全不同的设计思路，但目标还是修好这条生产线。

每次修复方案被拒绝（质检再次失败），你都要记录这个方案的"指纹"，下次不再提一模一样的方案。如果在一个方向上被拒绝 5 次以上，就升级策略（STRICT → RELAXED → ADJACENT）。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: GapSpec, RepairGapKind, HypothesisDraft, L1State

type RepairStage = "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";

// AST 哈希负向约束（防止重复失败方向）
type RFC6901_Ptr = string;  // JSON Pointer
type ASTHash = string;       // BLAKE3

interface NegativeConstraint {
  target_gap_id: string;
  attempt_epoch: number;
  stage: RepairStage;
  signatures: { ptr: RFC6901_Ptr; banned_hash: ASTHash }[];
}

// repair() 的输入：通过 L1State 读取，而非直接读旧版 L2Return
interface RepairInput {
  gap: GapSpec;
  current_stage: RepairStage;
  l1_state: L1State;      // 经 applyDelta 吸收后的状态；含 verified_claims、ranking 等
  negative_constraints: NegativeConstraint[];   // 历史失败记录
  max_attempts_per_stage: number;  // 默认 8
  consecutive_unsat_limit: number; // 默认 5，超出则进入 Suspended
}

interface RepairOutput {
  draft: HypothesisDraft | null;          // null 表示当前阶段无新方向可尝试
  next_stage: RepairStage;
  new_constraints: NegativeConstraint[];   // 本次失败产生的新约束（如有）
  action: "DRAFT_GENERATED" | "STAGE_UPGRADED" | "SUSPENDED" | "EXHAUSTED";
}

// 纯函数拦截：不经过 LLM
function is_unsat(draft: HypothesisDraft, constraints: NegativeConstraint[]): boolean;

// 核心修复函数
function repair(input: RepairInput): RepairOutput;
```

---

## 伪代码实现（Python 风格）

```python
# 配置常量
MAX_ATTEMPTS_PER_STAGE = 8
CONSECUTIVE_UNSAT_LIMIT = 5
STAGE_ORDER = ["STRICT", "RELAXED", "ADJACENT", "EXHAUSTED"]


def repair(input: RepairInput) -> RepairOutput:
    """
    对单个 GapSpec 执行修复尝试。
    核心原则：通过 l1_state 读取上下文（经 applyDelta 吸收），
              而非读取原始 L2Return（避免 GAP-1 冲突）。
    """
    gap = input.gap
    stage = input.current_stage
    constraints = input.negative_constraints

    # ======================================================
    # 检查是否已耗尽所有修复阶段
    # ======================================================
    if stage == "EXHAUSTED":
        return RepairOutput(
            draft=None,
            next_stage="EXHAUSTED",
            new_constraints=[],
            action="EXHAUSTED"
        )

    # ======================================================
    # 读取当前状态中与此 gap 相关的上下文
    # （从 l1_state 读取，而非旧版 L2Return 的 evidence_summary）
    # ======================================================
    relevant_claims = [
        c for c in input.l1_state.verified_claims
        if gap.axis_id in get_claim_axes(c)
    ]
    evidence_context = extract_evidence_context(relevant_claims, gap)

    # ======================================================
    # 根据 stage 选择修复策略，生成草稿
    # ======================================================
    consecutive_unsat = 0
    new_constraints = []

    for attempt in range(MAX_ATTEMPTS_PER_STAGE):
        # 根据当前阶段和 gap.kind 生成候选草稿
        raw_draft = generate_repair_draft(gap, stage, evidence_context, input.l1_state)

        if raw_draft is None:
            # 当前阶段已无更多可尝试方向
            break

        # ====================================
        # 纯函数拦截：检查是否与历史失败同源
        # ====================================
        if is_unsat(raw_draft, constraints + new_constraints):
            consecutive_unsat += 1

            if consecutive_unsat >= CONSECUTIVE_UNSAT_LIMIT:
                # 连续多次被拦截 → 进入 Suspended
                return RepairOutput(
                    draft=None,
                    next_stage=stage,
                    new_constraints=new_constraints,
                    action="SUSPENDED"
                )
            continue  # 跳过，尝试下一个

        consecutive_unsat = 0  # 找到了可行方向，重置计数

        # ====================================
        # 规范化为统一 HypothesisDraft
        # ====================================
        ctx = RepairContext(
            frame=input.l1_state.frame,
            gap_id=gap.gap_id,
            challenge_id=gap.gap_id,  # 暂时与 gap_id 相同
            current_stage=stage
        )
        draft = normalize_repair(raw_draft, ctx)

        return RepairOutput(
            draft=draft,
            next_stage=stage,
            new_constraints=new_constraints,
            action="DRAFT_GENERATED"
        )

    # ======================================================
    # 当前阶段尝试耗尽 → 升级阶段
    # ======================================================
    current_idx = STAGE_ORDER.index(stage)
    next_stage = STAGE_ORDER[current_idx + 1]  # STRICT → RELAXED → ADJACENT → EXHAUSTED

    return RepairOutput(
        draft=None,
        next_stage=next_stage,
        new_constraints=new_constraints,
        action="STAGE_UPGRADED"
    )


def is_unsat(
    draft: HypothesisDraft,
    constraints: list[NegativeConstraint]
) -> bool:
    """
    纯函数：检查草稿是否命中任何已记录的失败模式。
    不经过 LLM——完全基于 AST 哈希对比。
    """
    draft_json = to_canonical_json(draft.claim_sketch)

    for constraint in constraints:
        if constraint.target_gap_id != draft.provenance.source_gap_id:
            continue  # 不同 gap 的约束不适用

        # 检查是否所有签名都命中
        all_matched = all(
            hash_ast(json_pointer_get(draft_json, sig.ptr)) == sig.banned_hash
            for sig in constraint.signatures
        )

        if all_matched:
            return True  # 命中已知失败模式

    return False


def generate_repair_draft(
    gap: GapSpec,
    stage: RepairStage,
    evidence_context: dict,
    l1_state: L1State
) -> RawRepairDraft | None:
    """
    根据 gap.kind 和 stage 调用 LLM 生成修复草稿。
    gap.kind 分派：RepairGapKind 对应修复视角。
    """
    gap_kind = gap.kind  # RepairGapKind

    if gap_kind == "MISSING_DISCRIMINATOR":
        prompt = build_discriminator_prompt(gap, stage, evidence_context)
    elif gap_kind == "MISSING_OBSERVABLE":
        prompt = build_observable_prompt(gap, stage, evidence_context)
    elif gap_kind == "PREMISE_UNDERSPECIFIED":
        prompt = build_premise_prompt(gap, stage, evidence_context)
    else:  # UNCLASSIFIED
        prompt = build_generic_repair_prompt(gap, stage, evidence_context)

    response = call_llm(prompt)

    if response is None or response.empty:
        return None

    return RawRepairDraft(
        claim_sketch=response.claim_sketch,
        tension_kind="GAP_REPAIR",
        verifier_hint=response.verifier_hint,
        scope_ref=extract_scope_from_gap(gap, l1_state.frame),
        detail=f"{gap.gap_id}: {gap.description} [stage={stage}]"
    )


def record_failure_constraint(
    gap: GapSpec,
    failed_draft: HypothesisDraft,
    stage: RepairStage,
    epoch: int
) -> NegativeConstraint:
    """将失败的草稿转化为 AST 哈希约束，防止重复"""
    draft_json = to_canonical_json(failed_draft.claim_sketch)

    # 提取关键结构节点的 BLAKE3 哈希
    key_ptrs = ["/claim_sketch", "/scope_ref/0"]
    signatures = [
        {
            "ptr": ptr,
            "banned_hash": hash_ast(json_pointer_get(draft_json, ptr))
        }
        for ptr in key_ptrs
        if json_pointer_get(draft_json, ptr) is not None
    ]

    return NegativeConstraint(
        target_gap_id=gap.gap_id,
        attempt_epoch=epoch,
        stage=stage,
        signatures=signatures
    )
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-RP-01 | `repair()` 从 `l1_state` 读取 `verified_claims` 和 `ranking`，禁止直接读取旧版 `L2Return.evidence_summary` | 接口约定（GAP-1） |
| INV-RP-02 | `is_unsat()` 是纯函数，不调用 LLM | 代码审查 |
| INV-RP-03 | `is_unsat()` 判定时，`JSON Pointer` 路径不匹配返回 `false`（安全侧：放行），同时发出 metric | 实现约定 |
| INV-RP-04 | 连续 `CONSECUTIVE_UNSAT_LIMIT` 次被 `is_unsat()` 拦截 → `SUSPENDED`，不再尝试 | 循环计数器 |
| INV-RP-05 | 阶段升级顺序：`STRICT → RELAXED → ADJACENT → EXHAUSTED`，不可逆转 | `STAGE_ORDER` 数组 |
| INV-RP-06 | `normalize_repair()` 保证输出是合法的 `HypothesisDraft`（scope_ref 非空等） | 工厂函数 |
| INV-RP-07 | `gap.kind` 使用 `RepairGapKind` 枚举（修复视角），不使用 `TerminationGapKind` | GAP-2 拆分 |
| INV-RP-08 | 失败约束的 `target_gap_id` 必须匹配当前修复的 `gap.gap_id`，跨 gap 约束不适用 | `is_unsat()` 过滤 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"

```
场景：Layer 2 对 claim-007 验证后产出 EpochDelta:
  { kind: "GAP_OPEN", gap: GapSpec {
    gap_id: "gap-007",
    kind: "MISSING_DISCRIMINATOR",   // RepairGapKind
    blocks_termination: true,
    axis_id: "ax_burden_share",
    description: "历史责任论缺少判别'历史期'的具体边界：
                  不同的历史起算点（1850年 vs 1990年 vs 2000年）
                  会导致完全不同的责任分担结果"
  }}

L1 通过 applyDelta 更新 l1_state，然后调用 repair():

RepairInput:
  gap: gap-007
  current_stage: "STRICT"
  l1_state: { verified_claims: [...], frame: QF_v2, ... }
  negative_constraints: []   // 第一次修复，无历史约束
  max_attempts_per_stage: 8

repair() 执行：

  Step 1: stage != EXHAUSTED → 继续
  Step 2: 从 l1_state 提取相关上下文
    relevant_claims: [claim-007（ax_burden_share）]
    evidence_context: { 历史排放数据, IPCC AR6 数据库 }

  Step 3: 第 1 次尝试（STRICT 阶段）
    generate_repair_draft(gap, "STRICT", evidence_context, l1_state):
      → 提示词：[MISSING_DISCRIMINATOR 场景，STRICT 策略]
      → LLM 生成：
        claim_sketch: "以工业化前的 1850 年作为历史起算点，
                       基于 IPCC AR6 温室气体排放清单计算累积排放量，
                       作为国家责任分担的客观基准"
        verifier_hint: "若使用 1850 年起算点与 1990 年起算点的责任分担结果
                        差异小于 10%，则判别维度无实质影响"
        scope_ref: ["ax_burden_share"]

    is_unsat(draft, []):
      constraints 为空 → False（无历史约束可匹配）

    normalize_repair(raw, ctx):
      → HypothesisDraft {
          draft_id: "repair-007-001",
          problem_id: "q-carbon-001-r1",
          claim_sketch: "以工业化前的 1850 年作为历史起算点...",
          scope_ref: ["ax_burden_share"],
          verifier_hint: ["若使用 1850 年起算点..."],
          tension_source: { kind: "GAP_REPAIR", tier: "L2_FAILURE" },
          provenance: { source: "REPAIR", repair_stage: "STRICT" }
        }

返回 RepairOutput:
  draft: HypothesisDraft(repair-007-001)
  next_stage: "STRICT"
  new_constraints: []
  action: "DRAFT_GENERATED"

---

[后续：Layer 2 验证 repair-007-001 后仍然失败]

第二次修复调用：
  negative_constraints: [record_failure_constraint(gap-007, repair-007-001, "STRICT", epoch=3)]

第 2 次尝试：
  LLM 生成与 repair-007-001 语义接近的草稿（相同判别维度，稍微换了措辞）
  is_unsat() 检查：
    draft_json → /claim_sketch 的 blake3 = banned_hash → True（命中约束！）
  consecutive_unsat = 1

  ...（继续尝试）

第 6 次尝试：consecutive_unsat >= 5 → 进入 Suspended

返回 RepairOutput:
  draft: None
  next_stage: "STRICT"
  new_constraints: [...]
  action: "SUSPENDED"
→ L1 将 gap-007 标记为 SUSPENDED，报告给用户
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-1~~** → **已裁定** ✅
> - 裁定结论：采纳增量事件流 `deltas` 为唯一权威输入边界，`evidence_summary` 从 L2Return 永久移除；上下文投影由 L1 侧纯函数 `project_evidence_summary(state, query)` 完成，禁止 LLM 调用；`EVIDENCE_DIGEST_SUGGESTED` 作为可选事件回流提供语义摘要。
> - 关键规格：`repair()` 的输入改为 `l1_state: L1State`（经 `applyDelta` 吸收后的状态）；投影函数 `project_evidence_summary(state: L1State, query: EvidenceQuery): Result<EvidenceSummary, EvidenceProjectionError>`；若返回 `EMPTY` 且 L2 曾发 `EVIDENCE_DIGEST_SUGGESTED`，优先使用该摘要；仍不足且 `resolution_level === "COMPRESSED"` 则发出 `REHYDRATE_REQUEST`，本轮跳过该 gap。
> - 可推翻条件：A/B 测试显示纯投影摘要导致 repair 成功率下降 >10% 且 `EVIDENCE_DIGEST_SUGGESTED` 覆盖率 <50%，则允许在 RB 节点内部增加异步 LLM 摘要子步骤（非 L1 读路径）。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`

> **~~GAP-2~~** → **已裁定** ✅（完整裁定见 `00_shared_types.md`）
> - 裁定结论：GapSpec.kind 升级为 Tagged Union，`{ type: "REPAIR"; subkind: RepairSubKind }` 与 `{ type: "TERMINATION"; subkind: TerminationSubKind }` 严格区分；本模块（repair 视角）只能调用 `create_repair_gap` 工厂函数，dispatch 为纯函数 `dispatch_gap`。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`

> **~~GAP-4~~** → **已裁定** ✅（完整裁定见 `00_shared_types.md`，GAP-4 裁定为评估轴冻结规格）
> - 裁定结论：评估轴配置在 epoch 0 冻结为 `AxesSnapshot`（不可变），运行时轴变更通过 `SCHEMA_CHALLENGE_NEW` 提议 + PA 节点审批后生成新快照；`HypothesisDraft` 统一定义仍以 `00_shared_types.md` 为准，repair_strategy 必须通过 `normalize_repair()` 工厂函数生成草稿，禁止直接构造旧版字段集合。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`
