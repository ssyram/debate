# 模块名：声明编译器（Claim Compiler / CC 节点）

<!-- import from 00_shared_types: HypothesisDraft, TestableClaim, RegulativeIdea, QuestionFrame -->
<!-- import from 02_hypothesis_draft: HypothesisDraft 统一类型 -->

## 一句话定位

接收 `HypothesisDraft`，将其编译为具体可检验的 `TestableClaim`（含证伪条件和验证协议），或将无法桥接到经验检验的草稿降格为 `RegulativeIdea`——是草稿进入 Layer 2 验证前的最后一道类型门控。

---

## 通俗解释

想象一家法庭文书室。律师（MB / repair）递进来各种案件陈述草稿。文书室的工作是把每份草稿转换成"可在法庭上举证的正式指控书"——要有具体指控（`falsifiable_statement`），要有证据收集协议（`verification_plan`），还要划定管辖范围（`scope_boundary`）。

如果一份草稿说的是"这个被告在道德上是个坏人"，文书室没办法把它变成可以在法庭上举证的指控（无法证伪）——就把它归档为"参考性理念"（`RegulativeIdea`），供律师参考，但不作为主要指控。

文书室按草稿的**内容类型**（`tension_source.kind`）选择不同的文书模板，而不是按草稿来自哪个律师（`provenance.source`）——因为文书格式取决于案件性质，不取决于递送人。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: HypothesisDraft, TestableClaim, RegulativeIdea, QuestionFrame

interface CompileResult {
  testable_claim: {
    claim_id: string;
    statement: string;            // 精确化后的可检验命题
    falsifier: string;            // 证伪条件（可操作的）
    boundary_conditions: string[];
  };
  verification_plan: {
    verifier_type: "EMPIRICAL_CHECK" | "LOGICAL_AUDIT" | "SCOPE_REVIEW" | "TARGETED_RECHECK" | "AXIS_CONSISTENCY_CHECK";
    required_evidence: string[];
  };
  compile_warnings: string[];
}

type CompileError =
  | { code: "UNBOUND_OPEN_TERM"; unresolved_terms: string[]; refinement_signal: RefinementSignal }
  | { code: "NO_EMPIRICAL_BRIDGE"; reason: string }
  | { code: "AXIS_MISMATCH"; offending_axis: string; refinement_signal: RefinementSignal };

type RefinementSignal = {
  rejected_draft_id: string;
  unresolved_term: string;
  offending_context: string;
  epoch: number;
};

// CC 对外暴露两个出口：
// 1. TestableClaim（编译成功）→ 进入 Layer 2
// 2. RegulativeIdea（无经验桥接）→ 进入 RB 节点
// 3. CompileError(UNBOUND_OPEN_TERM | AXIS_MISMATCH) → 返回 RefinementSignal 给 QN 精炼回路

function clarity_compile(
  draft: HypothesisDraft,
  frame: QuestionFrame
): { ok: true; value: CompileResult } | { ok: false; error: CompileError };

// 将编译结果路由到正确的下游
type CCOutput =
  | { kind: "TESTABLE_CLAIM"; claim: TestableClaim }
  | { kind: "REGULATIVE_IDEA"; idea: RegulativeIdea }
  | { kind: "REFINEMENT_NEEDED"; signal: RefinementSignal };
```

---

## 伪代码实现（Python 风格）

```python
def clarity_compile(
    draft: HypothesisDraft,
    frame: QuestionFrame
) -> Result[CompileResult, CompileError]:

    # ======================================================
    # Step 1: 前置检查 - Open term 硬门控
    # ======================================================
    unbound = [
        t for t in frame.open_terms
        if t in draft.claim_sketch
        # 注意：如果该 open term 已在精炼回路中被降解（不在 frame.open_terms 中），则通过
    ]
    if unbound:
        return Err(CompileError(
            code="UNBOUND_OPEN_TERM",
            unresolved_terms=unbound,
            refinement_signal=RefinementSignal(
                rejected_draft_id=draft.draft_id,
                unresolved_term=unbound[0],
                offending_context=f"claim_sketch 中含未绑定的开放术语",
                epoch=draft.provenance.epoch
            )
        ))

    # ======================================================
    # Step 2: 前置检查 - 评价轴有效性
    # ======================================================
    valid_axis_ids = {ax.axis_id for ax in frame.evaluation_axes}
    offending = [r for r in draft.scope_ref if r.startswith("ax_") and r not in valid_axis_ids]
    if offending:
        return Err(CompileError(
            code="AXIS_MISMATCH",
            offending_axis=offending[0],
            refinement_signal=RefinementSignal(
                rejected_draft_id=draft.draft_id,
                unresolved_term=offending[0],
                offending_context=f"scope_ref 引用了不在 QuestionFrame 中的轴",
                epoch=draft.provenance.epoch
            )
        ))

    # ======================================================
    # Step 3: 根据 tension_source.kind 选择证伪器合成策略
    # 禁止根据 provenance.source 分支！
    # ======================================================
    tension = draft.tension_source

    if tension.kind in ("EXTERNAL_POSITION", "STAKEHOLDER_CONFLICT"):
        # 轴冲突类：从 evidence_ref 提取对立立场，构造对比证伪
        falsifier_result = synthesize_contrastive_falsifier(
            claim=draft.claim_sketch,
            evidence=tension.evidence_ref,
            axes=frame.evaluation_axes
        )

    elif tension.kind == "EVALUATION_AXIS_SPLIT":
        # 评价轴分裂：构造轴独立性证伪
        falsifier_result = synthesize_axis_independence_falsifier(
            claim=draft.claim_sketch,
            evidence=tension.evidence_ref
        )

    elif tension.kind in ("GAP_REPAIR", "SCHEMA_REPAIR"):
        # 修复类：从 note 提取缺口描述，构造覆盖性证伪
        falsifier_result = synthesize_coverage_falsifier(
            claim=draft.claim_sketch,
            gap_description=tension.note,
            scope=draft.scope_ref
        )

    else:
        # OTHER: 通用证伪
        falsifier_result = synthesize_generic_falsifier(draft.claim_sketch)

    # ======================================================
    # Step 4: 检查是否有经验桥接路径
    # ======================================================
    if falsifier_result.status == "NO_EMPIRICAL_BRIDGE":
        # 降格为 RegulativeIdea，不终止 pipeline
        return Err(CompileError(
            code="NO_EMPIRICAL_BRIDGE",
            reason=falsifier_result.reason
        ))

    # ======================================================
    # Step 5: 根据 tension_source.tier 选择验证计划类型
    # ======================================================
    tier = tension.tier
    if tier == "EMPIRICAL":
        verifier_type = "EMPIRICAL_CHECK"
    elif tier == "L2_FAILURE":
        verifier_type = "TARGETED_RECHECK"
    elif tier == "STRUCTURAL":
        verifier_type = "LOGICAL_AUDIT"
    else:  # INTERNAL_AXIS
        verifier_type = "AXIS_CONSISTENCY_CHECK"

    # ======================================================
    # Step 6: 精确化 claim
    # ======================================================
    testable_stmt = refine_claim(
        sketch=draft.claim_sketch,
        scope=draft.scope_ref,
        open_risks=draft.open_term_risk,
        hints=draft.verifier_hint,
        frame=frame
    )

    # ======================================================
    # Step 7: 组装结果
    # ======================================================
    warnings = check_open_term_risks(draft.open_term_risk)

    return Ok(CompileResult(
        testable_claim={
            "claim_id": generate_id("claim"),
            "statement": testable_stmt,
            "falsifier": falsifier_result.falsifier,
            "boundary_conditions": derive_boundaries(draft.scope_ref, frame)
        },
        verification_plan={
            "verifier_type": verifier_type,
            "required_evidence": tension.evidence_ref + draft.verifier_hint
        },
        compile_warnings=warnings
    ))


def route_compile_result(
    result: Result[CompileResult, CompileError],
    draft: HypothesisDraft
) -> CCOutput:
    """将 CC 编译结果路由到正确的下游节点"""
    if result.ok:
        return CCOutput(
            kind="TESTABLE_CLAIM",
            claim=TestableClaim(
                claim_id=result.value.testable_claim["claim_id"],
                source_draft_id=draft.draft_id,
                falsifiable_statement=result.value.testable_claim["statement"],
                required_evidence_types=result.value.verification_plan["required_evidence"],
                verification_protocol=result.value.verification_plan["verifier_type"],
                scope_boundary=result.value.testable_claim["boundary_conditions"],
                status="PENDING"
            )
        )

    elif result.error.code == "NO_EMPIRICAL_BRIDGE":
        return CCOutput(
            kind="REGULATIVE_IDEA",
            idea=RegulativeIdea(
                idea_id=generate_id("idea"),
                source_draft_id=draft.draft_id,
                claim_sketch=draft.claim_sketch,
                no_empirical_bridge_reason=result.error.reason
            )
        )

    else:
        # UNBOUND_OPEN_TERM 或 AXIS_MISMATCH → 返回精炼信号给 QN
        return CCOutput(
            kind="REFINEMENT_NEEDED",
            signal=result.error.refinement_signal
        )
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-CC-01 | CC 绝对禁止读取 `draft.provenance.source` 进行分支——来源分支是设计错误 | 代码审查 |
| INV-CC-02 | NQ 的 fatal 是"问题级"的，CC 的 `NO_EMPIRICAL_BRIDGE` 是"草稿级"的，两者无回退边 | 状态机约定 |
| INV-CC-03 | CC 返回 `NO_EMPIRICAL_BRIDGE` 不终止 pipeline；其他草稿继续正常编译 | 调度层处理 |
| INV-CC-04 | `UNBOUND_OPEN_TERM` 和 `AXIS_MISMATCH` 必须携带 `RefinementSignal`，用于触发 QN 精炼回路 | 类型约束 |
| INV-CC-05 | `TestableClaim.status` 初始值为 `"PENDING"`，由 Layer 2 更新 | 初始化约定 |
| INV-CC-06 | 证伪器合成逻辑只按 `tension_source.kind` 和 `tension_source.tier` 分支，不按 `provenance` 分支 | 代码审查 |
| INV-CC-07 | 若所有草稿均返回 `NO_EMPIRICAL_BRIDGE`，不回退到 NQ 重判定；所有 `RegulativeIdea` 进入 RB 节点 | 调度层约定 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"

### Trace A：编译成功（TestableClaim）

```
输入 HypothesisDraft:
  draft_id: "mb-003"
  claim_sketch: "历史累积排放量应作为国家责任分担的主要依据"
  scope_ref: ["ax_burden_share"]
  verifier_hint: ["比较以历史累积排放为基准的配额分配与等额配额分配下的减排效果"]
  tension_source:
    kind: "EVALUATION_AXIS_SPLIT"
    tier: "INTERNAL_AXIS"
    evidence_ref: ["IPCC AR6 历史排放数据库", "Paris Agreement NDC Reports"]
    note: "ax_burden_share 轴内的两极对立：历史责任 vs 现时能力"
  open_term_risk: []

clarity_compile(draft, frame):
  Step 1: open_terms=[] → 无 unbound，通过
  Step 2: "ax_burden_share" ∈ valid_axis_ids → 通过
  Step 3: kind="EVALUATION_AXIS_SPLIT"
    → synthesize_axis_independence_falsifier()
    → falsifier: "若以 1850-2023 年历史累积 CO₂ 排放量为基准计算配额，
                  发展中国家的年减排成本 ≤ 发达国家的年减排成本（按 GDP 占比归一化），
                  则历史责任论被证伪"
    → status: "OK"（有经验桥接路径）
  Step 4: status ≠ NO_EMPIRICAL_BRIDGE → 继续
  Step 5: tier="INTERNAL_AXIS" → verifier_type="AXIS_CONSISTENCY_CHECK"
  Step 6: refine_claim()
    → testable_stmt: "在 2024-2035 年减排目标框架下，以 1850-2023 年历史
                      累积 CO₂ 排放量（IPCC 数据库）为基准的责任分担方案，
                      将使发展中国家的边际减排成本低于发达国家（按 GDP 占比控制）"

输出 CompileResult:
  testable_claim.claim_id: "claim-007"
  testable_claim.falsifier: "若...则历史责任论被证伪"
  verification_plan.verifier_type: "AXIS_CONSISTENCY_CHECK"
  compile_warnings: []

→ CCOutput: { kind: "TESTABLE_CLAIM", claim: TestableClaim(claim-007) }
→ 进入 Layer 2 验证
```

### Trace B：降格为 RegulativeIdea（NO_EMPIRICAL_BRIDGE）

```
输入 HypothesisDraft:
  draft_id: "mb-005"
  claim_sketch: "碳排放交易机制在道德上优于碳税，
                 因为它更尊重各国的主权决策权"
  tension_source.kind: "EXTERNAL_POSITION"

clarity_compile(draft, frame):
  Step 3: kind="EXTERNAL_POSITION"
    → synthesize_contrastive_falsifier()
    → 尝试构造对比证伪：
      "主权决策权"无法映射到可测量的结果指标
      → status: "NO_EMPIRICAL_BRIDGE"
      → reason: "'道德优越性'和'主权尊重'缺乏可操作的经验测试维度"
  Step 4: status = NO_EMPIRICAL_BRIDGE → 返回 Err

→ CCOutput: { kind: "REGULATIVE_IDEA",
              idea: RegulativeIdea(source="mb-005", reason="...") }
→ 进入 RB 节点（供参考，不作为主要论证）

注：mb-005 的 NO_EMPIRICAL_BRIDGE 不影响 mb-001~mb-004 的正常编译。
```

### Trace C：触发精炼信号（UNBOUND_OPEN_TERM）

```
场景：Epoch 1 的 frame 仍有 open_terms=["公平"]，
      某草稿 claim_sketch 含"公平"一词

clarity_compile(draft, frame):
  Step 1: unbound = ["公平"]（frame.open_terms 中的 "公平" 出现在 claim_sketch）
    → 返回 Err(CompileError{
        code: "UNBOUND_OPEN_TERM",
        refinement_signal: {
          rejected_draft_id: "mb-001",
          unresolved_term: "公平",
          offending_context: "claim_sketch 中含未绑定术语 '公平'",
          epoch: 1
        }
      })

→ CCOutput: { kind: "REFINEMENT_NEEDED", signal }
→ QN 精炼回路收到信号，尝试将"公平"降解为具体轴
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-6~~** → **已裁定** ✅（完整裁定见 `03_macro_breadth.md` 和 `11_layer1_orchestrator.md`）
> - 裁定结论：RB 节点两阶段（规则预筛 + LLM 提取代理变量），`extract_testable_angle` 为核心函数，失败路径写入 `L1State.rb_reject_log`；`RegulativeIdea` 不再是孤儿对象。
> - 裁定来源：`gap_missing_nodes_debate_summary.md`

> **~~GAP-8~~** → **已裁定** ✅（完整裁定见 `11_layer1_orchestrator.md`）
> - 裁定结论：D2 只注入索引句柄 `EvidenceRef`（不携带 EvidenceChain 正文），历史视图为只读投影不持久化；`verifier_type` 通过 `build_verification_context` 传递，Layer 2 根据 `VerificationContext.prior_verdicts` 调整策略，不再形同虚设。
> - 关键规格：`EvidenceRef { claim_id; epoch_id; verdict; etag; storage_key }`；`VerificationContext { current_epoch; prior_evidence: EvidenceRef[]; prior_verdicts: Record<ClaimId, verdict> }`；`build_verification_context(state: L1State): VerificationContext`（纯函数）。
> - 裁定来源：`gap_missing_nodes_debate_summary.md`
