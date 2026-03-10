# 模块名：Layer 2 证据评分（Layer 2 Evidence Scoring / S4-S5 节点）

<!-- import from 00_shared_types: EvidenceAtom, EvidenceChain, AxisScoreEntry, TestableClaim, AxisRulebook, DEFAULT_RULEBOOK -->

## 一句话定位

接收 `TestableClaim`，为其收集 `EvidenceAtom` 并计算每个评估轴的 `axis_score`，输出完整的 `EvidenceChain`（含评分）——是认知引擎的"验证工厂"，负责把定性假设转化为定量评分。

---

## 通俗解释

想象一个质检实验室。律师（CC）把每一份案件指控书（`TestableClaim`）送进来，实验室要：
1. 收集与这份指控相关的所有证据（`EvidenceAtom`）——文件、数据、证人证词。
2. 给每条证据打"证据强度"标签——是轶事？相关性研究？随机对照实验？还是公理？
3. 对每个评估维度（轴）汇总计算：支持分 - 反对分 = 该维度的可信度评分。
4. 最终产出一张完整的检验报告（`EvidenceChain`）。

质检实验室有一条铁律：**每条证据只挂一个维度**（`axis_id` 唯一），强迫自己精确。如果一条证据同时关系到两个维度，就拆成两条分别处理。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: EvidenceAtom, EvidenceChain, AxisScoreEntry, TestableClaim,
//                               AxisRulebook, DEFAULT_RULEBOOK, StrengthTier

interface EvidenceCollectionResult {
  atoms: EvidenceAtom[];
  collection_warnings: string[];  // 如：文档缺失、链接失效等
}

interface ScoreComputationResult {
  axis_scores: AxisScoreEntry[];
  global_score: number;           // 加权综合分 ∈ [0, 1]
  score_epsilon: number;          // 综合不确定性
}

interface ChainIntegrityReport {
  claim_alignment_verified: boolean;
  dependency_status_verified: boolean;
  score_evidence_alignment_verified: boolean;
  acyclicity_verified: boolean;
  violations: string[];
}

// Layer 2 主函数（S4 + S5 合并接口）
function run_layer2_verification(
  claim: TestableClaim,
  rulebook: AxisRulebook,
  epoch_id: number
): Result<EvidenceChain, L2VerificationError>;

type L2VerificationError =
  | { code: "EVIDENCE_CONFLICT"; conflicting_atoms: [EvidenceAtom, EvidenceAtom]; axis_id: string }
  | { code: "INTEGRITY_CHECK_FAILED"; report: ChainIntegrityReport }
  | { code: "NO_EVIDENCE_FOUND"; axis_ids: string[] }
  | { code: "DEPENDENCY_UNSATISFIED"; unresolved_claim_ids: string[] };
```

---

## 伪代码实现（Python 风格）

```python
def run_layer2_verification(
    claim: TestableClaim,
    rulebook: AxisRulebook,
    epoch_id: int
) -> Result[EvidenceChain, L2VerificationError]:

    # ======================================================
    # S4 阶段: 证据收集与提取
    # ======================================================

    # Step 1: 从外部文档和内部 Claim 中提取 EvidenceAtom
    collection = collect_evidence(claim, epoch_id)
    if collection.atoms is None:
        return Err(L2VerificationError(
            code="NO_EVIDENCE_FOUND",
            axis_ids=extract_axis_ids(claim)
        ))

    # Step 2: 验证每个 Atom 的轴映射（每个 atom 只能挂一个轴）
    for atom in collection.atoms:
        if not is_valid_axis(atom.axis_id, claim):
            # 轴不匹配：记录警告，丢弃该 atom
            collection.collection_warnings.append(
                f"atom {atom.evidence_id}: axis {atom.axis_id} 不在 claim 的评估轴中"
            )
            collection.atoms.remove(atom)

    # Step 3: 依赖声明状态检查（对 INTERNAL_CLAIM 类型的引用）
    unsatisfied = []
    for atom in collection.atoms:
        if atom.ref.kind == "INTERNAL_CLAIM":
            dep_status = get_claim_status(atom.ref.claim_id)
            if dep_status not in ("VERIFIED", "DEFENSIBLE"):
                unsatisfied.append(atom.ref.claim_id)

    if unsatisfied:
        return Err(L2VerificationError(
            code="DEPENDENCY_UNSATISFIED",
            unresolved_claim_ids=unsatisfied
        ))

    # Step 4: 证据冲突检测
    for axis_id in get_unique_axes(collection.atoms):
        pro_atoms = [a for a in collection.atoms if a.axis_id == axis_id and a.polarity == "PRO"]
        con_atoms = [a for a in collection.atoms if a.axis_id == axis_id and a.polarity == "CON"]

        if pro_atoms and con_atoms:
            # 检查是否存在无法调和的强证据冲突
            conflict = detect_strong_conflict(pro_atoms, con_atoms, rulebook)
            if conflict.is_blocking:
                return Err(L2VerificationError(
                    code="EVIDENCE_CONFLICT",
                    conflicting_atoms=(conflict.pro_atom, conflict.con_atom),
                    axis_id=axis_id
                ))

    # ======================================================
    # S5 阶段: 评分计算
    # ======================================================

    axis_scores: list[AxisScoreEntry] = []

    for axis_id in get_unique_axes(collection.atoms):
        axis_atoms = [a for a in collection.atoms if a.axis_id == axis_id]
        score_entry = compute_axis_score(axis_id, axis_atoms, rulebook)
        axis_scores.append(score_entry)

    # ======================================================
    # 完整性检查（四项不变式）
    # ======================================================
    integrity = verify_chain_integrity(claim, collection.atoms, axis_scores)
    if not all([
        integrity.claim_alignment_verified,
        integrity.dependency_status_verified,
        integrity.score_evidence_alignment_verified,
        integrity.acyclicity_verified
    ]):
        return Err(L2VerificationError(
            code="INTEGRITY_CHECK_FAILED",
            report=integrity
        ))

    # ======================================================
    # 组装并返回 EvidenceChain
    # ======================================================
    return Ok(EvidenceChain(
        claim_id=claim.claim_id,
        epoch_id=epoch_id,
        atoms=collection.atoms,
        axis_scores=axis_scores,
        integrity=integrity
    ))


def compute_axis_score(
    axis_id: str,
    atoms: list[EvidenceAtom],
    rulebook: AxisRulebook
) -> AxisScoreEntry:
    """
    将 EvidenceAtom[] 折算为单个轴的 [0, 1] 得分。
    使用 sigmoid 函数平滑 pro/con 差值。
    """
    pro_atoms = [a for a in atoms if a.polarity == "PRO"]
    con_atoms = [a for a in atoms if a.polarity == "CON"]

    # 按强度等级折算原始分
    def raw_score(atom_list: list[EvidenceAtom]) -> float:
        return sum(
            rulebook.tier_score[a.strength_tier] * a.llm_confidence
            for a in atom_list
        )

    raw_pro = raw_score(pro_atoms)
    raw_con = raw_score(con_atoms)

    # sigma 平滑（避免极端值）
    k = rulebook.sigmoid_k or 2
    midpoint = rulebook.sigmoid_midpoint or 0
    net = raw_pro - raw_con
    score = 1 / (1 + math.exp(-k * (net - midpoint)))

    # 不确定性（epsilon）：使用最大单个 atom 的 tier_epsilon
    epsilon = max(
        (rulebook.tier_epsilon[a.strength_tier] for a in atoms),
        default=0.15   # 无证据时默认高不确定性
    )

    # 计算 provenance
    if pro_atoms or con_atoms:
        provenance = "RULE_ONLY"
    elif any(a.extractor == "LLM" for a in atoms):
        provenance = "LLM_EXTRACTED_RULE_SCORED"
    else:
        provenance = "DEFAULT_TIER"

    return AxisScoreEntry(
        axis_id=axis_id,
        score=score,
        epsilon=epsilon,
        provenance=provenance,
        evidence_ids=[a.evidence_id for a in atoms],
        aggregation_detail={
            "raw_pro": raw_pro,
            "raw_con": raw_con,
            "pro_count": len(pro_atoms),
            "con_count": len(con_atoms),
            "sigmoid_k": k,
            "sigmoid_midpoint": midpoint
        }
    )


def verify_chain_integrity(
    claim: TestableClaim,
    atoms: list[EvidenceAtom],
    axis_scores: list[AxisScoreEntry]
) -> ChainIntegrityReport:
    """验证四项不变式"""
    violations = []

    # INV-1: 所有 atom 的 claim_id 必须与当前 claim_id 一致
    mismatched = [a for a in atoms if a.target_claim_id != claim.claim_id]
    if mismatched:
        violations.append(f"claim_id 不一致: {[a.evidence_id for a in mismatched]}")

    # INV-2: INTERNAL_CLAIM 引用的 claim 状态必须是 VERIFIED 或 DEFENSIBLE
    # （已在 S4 阶段检查，这里双重确认）
    dep_violations = [
        a.ref.claim_id for a in atoms
        if a.ref.kind == "INTERNAL_CLAIM"
        and get_claim_status(a.ref.claim_id) not in ("VERIFIED", "DEFENSIBLE")
    ]
    if dep_violations:
        violations.append(f"依赖状态不满足: {dep_violations}")

    # INV-3: 每个 axis_score 的 evidence_ids 都能在 atoms 中找到
    atom_ids = {a.evidence_id for a in atoms}
    for as_entry in axis_scores:
        missing = [eid for eid in as_entry.evidence_ids if eid not in atom_ids]
        if missing:
            violations.append(f"axis {as_entry.axis_id} 的 evidence_ids 引用不存在的 atom: {missing}")

    # INV-4: 无循环依赖（INTERNAL_CLAIM 引用不形成环）
    if has_circular_dependency(atoms):
        violations.append("检测到循环证据依赖")

    return ChainIntegrityReport(
        claim_alignment_verified=not any("claim_id 不一致" in v for v in violations),
        dependency_status_verified=not any("依赖状态不满足" in v for v in violations),
        score_evidence_alignment_verified=not any("引用不存在" in v for v in violations),
        acyclicity_verified=not any("循环" in v for v in violations),
        violations=violations
    )
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-L2-01 | 每个 `EvidenceAtom.axis_id` 只允许映射一个轴（禁止多轴映射） | S4 收集时过滤 |
| INV-L2-02 | `INTERNAL_CLAIM` 类型的 atom 引用的 claim 状态必须是 `VERIFIED` 或 `DEFENSIBLE` | S4 依赖检查 |
| INV-L2-03 | 证据链四项完整性不变式（claim_alignment / dependency / score_alignment / acyclicity）全部通过才输出 | 完整性检查 |
| INV-L2-04 | `axis_score ∈ [0, 1]`（sigmoid 函数保证） | 数学保证 |
| INV-L2-05 | 无证据时 epsilon 默认 0.15（高不确定性），不为 0 | compute_axis_score |
| INV-L2-06 | 规则表（AxisRulebook）可版本化，变更时已有 EvidenceChain 需要重算 | 运行时约定 |
| INV-L2-07 | `EVIDENCE_CONFLICT` 仅在强证据级别（CAUSAL_STATISTICAL 或 AXIOMATIC）冲突时触发 | detect_strong_conflict |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"

```
输入 TestableClaim:
  claim_id: "claim-007"
  statement: "以 1850-2023 年历史累积 CO₂ 排放量为基准的责任分担方案，
              将使发展中国家的边际减排成本低于发达国家（按 GDP 占比控制）"
  falsifier: "若控制 GDP 后，发展中国家边际减排成本 ≥ 发达国家，则证伪"
  scope_boundary: ["ax_burden_share"]
  status: "PENDING"

S4: 证据收集

  Atom-1: {
    ref: { kind: "EXTERNAL_DOC", doc_id: "IPCC_AR6_WG3", span_hash: "a3f2...", offsets: [10200, 10450] },
    axis_id: "ax_burden_share",
    polarity: "PRO",
    strength_tier: "CAUSAL_STATISTICAL",  // 使用历史统计数据
    llm_confidence: 0.88
  }

  Atom-2: {
    ref: { kind: "EXTERNAL_DOC", doc_id: "WTO_2023_Dev", span_hash: "b7e1...", offsets: [3400, 3600] },
    axis_id: "ax_burden_share",
    polarity: "PRO",
    strength_tier: "CORRELATIONAL",  // 相关性研究
    llm_confidence: 0.72
  }

  Atom-3: {
    ref: { kind: "EXTERNAL_DOC", doc_id: "OECD_Cost_Analysis", span_hash: "c9d3...", offsets: [780, 950] },
    axis_id: "ax_burden_share",
    polarity: "CON",
    strength_tier: "ANECDOTAL",  // 来自部分成员国反映
    llm_confidence: 0.55
  }

  冲突检测：
    PRO: Atom-1（CAUSAL_STATISTICAL）, Atom-2（CORRELATIONAL）
    CON: Atom-3（ANECDOTAL）
    detect_strong_conflict():
      strongest_con = ANECDOTAL → 不触发阻塞性冲突（仅 CAUSAL_STATISTICAL/AXIOMATIC 才阻塞）
    → 非阻塞，继续

S5: 评分计算（使用 DEFAULT_RULEBOOK）

  axis_id = "ax_burden_share":
    raw_pro = 0.75 × 0.88 + 0.40 × 0.72 = 0.66 + 0.288 = 0.948
    raw_con = 0.15 × 0.55 = 0.0825
    net = 0.948 - 0.0825 = 0.8655
    score = 1 / (1 + exp(-2 × (0.8655 - 0))) = 1 / (1 + e^-1.731) ≈ 0.849
    epsilon = max(0.04, 0.08, 0.12) = 0.12  // 最大单个 atom epsilon

完整性检查：全部通过

输出 EvidenceChain:
  claim_id: "claim-007"
  epoch_id: 2
  atoms: [Atom-1, Atom-2, Atom-3]
  axis_scores: [{ axis_id: "ax_burden_share", score: 0.849, epsilon: 0.12 }]
  integrity: { all true }
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-7~~** → **已裁定** ✅（完整裁定见 `09_context_compression.md`）
> - 裁定结论：Layer 2 输出的 `EvidenceChain` 通过 `CLAIM_VERIFIED` delta 以 `VerifiedClaimFull` 形态入库，压缩为异步后台任务；Layer 2 本身不触发压缩；业务代码统一通过 accessor `get_evidence(claim): EvidenceAccess` 访问，避免直接依赖具体字段。
> - 关键规格：L2 输出只产 `VerifiedClaimFull`（`_tag: "FULL"`）；L1 的 `apply_delta` 纯函数接收后存入状态；压缩由独立的 `should_compress(state) → CompressionJob[]` 决策 + `apply_compression_result` 应用。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`
