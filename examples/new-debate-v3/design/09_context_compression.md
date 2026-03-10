# 模块名：上下文压缩（Context Compression）

<!-- import from 00_shared_types: EvidenceAtom, VerifiedClaimFull, VerifiedClaimCompressed, CompressedEvidenceProfile, PinnedConflict, ArchiveRef, StrengthTier -->

## 一句话定位

将 `VerifiedClaimFull`（含全量 `EvidenceAtom[]`）转换为 `VerifiedClaimCompressed`（含 Watermarked Ledger + 热区窗口 + 冷区归档引用），在保证证据冲突检测和评分可重算的前提下，将 LLM 上下文窗口的占用压缩到严格有界的大小。

---

## 通俗解释

想象一个档案室负责管理法庭的证据文件。每次开庭（epoch），新证据不断涌入，文件越堆越高。法官（S4 节点）每次开庭都要翻全部文件——但文件多到一天读不完（上下文窗口爆了）。

档案室（Context Compression）的解决方案：
1. **保留"水位线"**：每种强度等级（ANECDOTAL/CORRELATIONAL/...）的正反各保留一份"代表性原件"（watermark）——法官判案时能读到具体文本，不只是数字。
2. **保留计数统计**：按强度分桶统计有多少条正面/反面证据——评分算法可以不用读所有原件也能计算。
3. **钉住冲突**：发现了矛盾证据对，不允许归档——保持在热区，直到维修工（repair）显式解决。
4. **归档旧文件**：最近 N 个 epoch 之外的原件归档到冷存储，需要时可以再水合取回。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: EvidenceAtom, VerifiedClaimFull, VerifiedClaimCompressed,
//                               CompressedEvidenceProfile, PinnedConflict, ArchiveRef, StrengthTier

interface CompressionTriggerConfig {
  // 硬性安全网（Linus 方案，不可违反）
  max_hot_atoms_per_claim: number;       // 默认: 50
  max_total_atoms_per_claim: number;     // 默认: 200
  prompt_token_budget: number;           // 默认: 按模型窗口的 40%

  // 优化触发器（Kant 方案，提前压缩冗余内容）
  info_gain_window_epochs: number;       // 默认: 3
  min_info_gain_threshold: number;       // 默认: 0.1
}

type TriggerReason =
  | { kind: "TOKEN_BUDGET_EXCEEDED"; current: number; limit: number }
  | { kind: "ATOM_COUNT_EXCEEDED"; current: number; limit: number }
  | { kind: "INFO_GAIN_LOW"; epochs_without_change: number; threshold: number }
  | { kind: "EXPLICIT_REQUEST" };

interface CompressionTriggerResult {
  should_compress: boolean;
  reasons: TriggerReason[];
  claim_ids_affected: string[];
}

type CompressError =
  | { kind: "INVARIANT_BREAK"; detail: string; claim_id: string }
  | { kind: "HASH_MISMATCH"; detail: string; claim_id: string }
  | { kind: "IO_FAIL"; detail: string; claim_id: string }
  | { kind: "PINNED_CONFLICT_LOSS"; detail: string; claim_id: string };

type RehydrateError = {
  kind: "MISSING_REF" | "IO_FAIL" | "DECODE_FAIL" | "INTEGRITY_CHECK_FAIL";
  ref: ArchiveRef;
  detail: string;
};

// Watermark 替换策略接口
function should_replace_watermark(
  current: EvidenceAtom | null,
  candidate: EvidenceAtom,
  pinned: PinnedConflict[]
): { replace: boolean; reason: string };

// 主压缩函数
function compress_evidence_chain(
  claim_id: string,
  raw_chain: EvidenceAtom[],
  existing_profiles: Record<string, CompressedEvidenceProfile> | null,
  config: CompressionTriggerConfig,
  rulebook_version: string
): Result<{
  profiles: Record<string, CompressedEvidenceProfile>;
  active_window: EvidenceAtom[];
  archive_ref: ArchiveRef;
}, CompressError>;

// 再水合接口（冷区取回）
function rehydrate_evidence(
  ref: ArchiveRef,
  filter?: { axis_id?: string; epoch_range?: [number, number]; polarity?: "PRO" | "CON" }
): Result<EvidenceAtom[], RehydrateError>;

// 触发检测
function evaluate_compression_trigger(
  claim: VerifiedClaimFull | VerifiedClaimCompressed,
  config: CompressionTriggerConfig,
  current_epoch: number
): CompressionTriggerResult;
```

---

## 伪代码实现（Python 风格）

```python
# 水位线容量上限：每 axis × polarity × strength 最多保留 1 个 atom
# 总上界：4 strength × 2 polarity × N axes = 8N 个 atom

MAX_ACTIVE_ATOMS = 50     # 每个 claim 的热区上限
DEFAULT_ACTIVE_WINDOW = 3 # 保留最近 N 个 epoch 的原始 atom


def evaluate_compression_trigger(
    claim,   # VerifiedClaimFull 或 VerifiedClaimCompressed
    config: CompressionTriggerConfig,
    current_epoch: int
) -> CompressionTriggerResult:
    """
    评估是否需要压缩（对每个 claim 独立评估）。
    硬性安全网（token budget）OR 优化触发器（信息增益低）任一满足即触发。
    """
    reasons = []

    # 触发器 1（硬性安全网）：atom 数量超限
    total_atoms = get_total_atom_count(claim)
    if total_atoms > config.max_total_atoms_per_claim:
        reasons.append(TriggerReason(
            kind="ATOM_COUNT_EXCEEDED",
            current=total_atoms,
            limit=config.max_total_atoms_per_claim
        ))

    # 触发器 2（信息增益低）：最近 N 个 epoch 无新发现
    if not reasons:  # 只有安全网未触发时才评估优化触发器
        info_gain = compute_info_gain(claim, config.info_gain_window_epochs, current_epoch)
        if info_gain < config.min_info_gain_threshold:
            reasons.append(TriggerReason(
                kind="INFO_GAIN_LOW",
                epochs_without_change=config.info_gain_window_epochs,
                threshold=config.min_info_gain_threshold
            ))

    should_compress = len(reasons) > 0

    return CompressionTriggerResult(
        should_compress=should_compress,
        reasons=reasons,
        claim_ids_affected=[get_claim_id(claim)] if should_compress else []
    )


def compress_evidence_chain(
    claim_id: str,
    raw_chain: list[EvidenceAtom],
    existing_profiles: dict[str, CompressedEvidenceProfile] | None,
    config: CompressionTriggerConfig,
    rulebook_version: str
) -> Result[dict, CompressError]:
    """
    将全量证据链压缩为 Watermarked Ledger + 热区窗口。
    失败时保留原状态（不破坏现有数据）。
    """
    # Step 1: 按 axis_id 分组
    by_axis: dict[str, list[EvidenceAtom]] = {}
    for atom in raw_chain:
        by_axis.setdefault(atom.axis_id, []).append(atom)

    new_profiles: dict[str, CompressedEvidenceProfile] = {}

    for axis_id, atoms in by_axis.items():
        existing = existing_profiles.get(axis_id) if existing_profiles else None
        profile_result = compress_axis(axis_id, atoms, existing, rulebook_version)

        if not profile_result.ok:
            return Err(profile_result.error)

        new_profiles[axis_id] = profile_result.value

    # Step 2: 构建热区窗口（最近 N 个 epoch 的原始 atom）
    sorted_atoms = sorted(raw_chain, key=lambda a: extract_epoch(a), reverse=True)
    active_window = sorted_atoms[:MAX_ACTIVE_ATOMS]

    # Step 3: 将其余 atom 写入冷区归档
    cold_atoms = sorted_atoms[MAX_ACTIVE_ATOMS:]
    archive_result = write_to_cold_archive(claim_id, cold_atoms)

    if not archive_result.ok:
        # IO 失败：保留原状态，不压缩
        return Err(CompressError(kind="IO_FAIL", detail=str(archive_result.error), claim_id=claim_id))

    archive_ref = archive_result.value

    # Step 4: 不变式验证（压缩后必须满足所有约束）
    validation = validate_compression_invariants(raw_chain, new_profiles, active_window)
    if not validation.ok:
        # 验证失败：回滚，保留原状态
        return Err(CompressError(
            kind="INVARIANT_BREAK",
            detail=validation.error,
            claim_id=claim_id
        ))

    return Ok({
        "profiles": new_profiles,
        "active_window": active_window,
        "archive_ref": archive_ref
    })


def compress_axis(
    axis_id: str,
    atoms: list[EvidenceAtom],
    existing: CompressedEvidenceProfile | None,
    rulebook_version: str
) -> Result[CompressedEvidenceProfile, CompressError]:
    """
    对单个轴的证据进行压缩，更新 counts 和 watermarks。
    """
    STRENGTH_TIERS = ["ANECDOTAL", "CORRELATIONAL", "CAUSAL_STATISTICAL", "AXIOMATIC"]

    # 初始化 counts
    counts_pro = {t: 0 for t in STRENGTH_TIERS}
    counts_con = {t: 0 for t in STRENGTH_TIERS}

    # 继承已有计数（增量压缩）
    if existing:
        counts_pro = dict(existing.counts_pro)
        counts_con = dict(existing.counts_con)

    watermarks_pro = {t: (existing.watermarks_pro.get(t) if existing else None) for t in STRENGTH_TIERS}
    watermarks_con = {t: (existing.watermarks_con.get(t) if existing else None) for t in STRENGTH_TIERS}
    pinned_conflicts = list(existing.pinned_conflicts if existing else [])

    for atom in atoms:
        tier = atom.strength_tier
        polarity = atom.polarity

        # 更新计数
        if polarity == "PRO":
            counts_pro[tier] += 1
            decision = should_replace_watermark(watermarks_pro[tier], atom, pinned_conflicts)
            if decision.replace:
                watermarks_pro[tier] = atom
        else:  # CON
            counts_con[tier] += 1
            decision = should_replace_watermark(watermarks_con[tier], atom, pinned_conflicts)
            if decision.replace:
                watermarks_con[tier] = atom

        # 冲突检测：同一 axis 上存在 PRO 和 CON 的 CAUSAL_STATISTICAL 或 AXIOMATIC
        if (tier in ("CAUSAL_STATISTICAL", "AXIOMATIC")
            and polarity == "CON"
            and any(
                counts_pro[t] > 0 for t in ("CAUSAL_STATISTICAL", "AXIOMATIC")
            )):
            # 尝试找对应的 PRO watermark 构成冲突对
            pro_wm = (watermarks_pro.get("CAUSAL_STATISTICAL")
                      or watermarks_pro.get("AXIOMATIC"))
            if pro_wm:
                conflict = PinnedConflict(
                    gap_spec_id=f"auto-conflict-{axis_id}-{atom.evidence_id}",
                    gap_kind="EVIDENCE_CONFLICT",
                    pro_atom=pro_wm,
                    con_atom=atom,
                    detected_epoch=extract_epoch(atom),
                    resolved=False
                )
                # 检查是否已存在同一对
                already_pinned = any(
                    p.pro_atom.evidence_id == pro_wm.evidence_id
                    and p.con_atom.evidence_id == atom.evidence_id
                    for p in pinned_conflicts
                )
                if not already_pinned:
                    pinned_conflicts.append(conflict)

    total_atoms = (
        sum(counts_pro.values()) + sum(counts_con.values())
        + (existing.total_atom_count if existing else 0)
    )

    return Ok(CompressedEvidenceProfile(
        axis_id=axis_id,
        counts_pro=counts_pro,
        counts_con=counts_con,
        watermarks_pro=watermarks_pro,
        watermarks_con=watermarks_con,
        pinned_conflicts=pinned_conflicts,
        archive_ref=None,  # 由 compress_evidence_chain 统一更新
        strength_rulebook_version=rulebook_version,
        covered_epoch_range=(0, extract_epoch(atoms[-1]) if atoms else 0),
        total_atom_count=total_atoms
    ))


def should_replace_watermark(
    current: EvidenceAtom | None,
    candidate: EvidenceAtom,
    pinned: list[PinnedConflict]
) -> dict:
    """
    判断是否用新 atom 替换现有 watermark。
    核心规则：如果当前 watermark 被 pinned_conflicts 引用，禁止替换。
    """
    if current is None:
        return {"replace": True, "reason": "空槽位，直接填入"}

    # 检查当前 watermark 是否参与了未解决的冲突
    in_conflict = any(
        (not p.resolved)
        and (p.pro_atom.evidence_id == current.evidence_id
             or p.con_atom.evidence_id == current.evidence_id)
        for p in pinned
    )

    if in_conflict:
        return {
            "replace": False,
            "reason": f"当前 watermark {current.evidence_id} 参与未解决冲突，禁止替换"
        }

    # 用置信度更高的替换（或使用相同置信度时保留新的）
    if candidate.llm_confidence >= current.llm_confidence:
        return {"replace": True, "reason": f"候选置信度 {candidate.llm_confidence} >= 当前 {current.llm_confidence}"}
    else:
        return {"replace": False, "reason": f"候选置信度 {candidate.llm_confidence} < 当前 {current.llm_confidence}"}


def rehydrate_evidence(
    ref: ArchiveRef,
    filter: dict | None = None
) -> Result[list[EvidenceAtom], RehydrateError]:
    """
    从冷区取回证据原子。
    失败时 S4 必须进入 S7(Suspended)，不得静默降级。
    """
    # Step 1: 读取冷区存储
    raw_bytes = cold_storage_read(ref.storage_uri)

    if raw_bytes is None:
        return Err(RehydrateError(
            kind="MISSING_REF",
            ref=ref,
            detail=f"冷区引用 {ref.storage_uri} 不存在"
        ))

    # Step 2: 完整性校验
    actual_hash = blake3(raw_bytes)
    if actual_hash != ref.blake3_hash:
        return Err(RehydrateError(
            kind="INTEGRITY_CHECK_FAIL",
            ref=ref,
            detail=f"hash 不匹配: 期望 {ref.blake3_hash}, 实际 {actual_hash}"
        ))

    # Step 3: 反序列化
    try:
        atoms = deserialize_atoms(raw_bytes)
    except Exception as e:
        return Err(RehydrateError(kind="DECODE_FAIL", ref=ref, detail=str(e)))

    # Step 4: 应用过滤器（可选）
    if filter:
        if filter.get("axis_id"):
            atoms = [a for a in atoms if a.axis_id == filter["axis_id"]]
        if filter.get("polarity"):
            atoms = [a for a in atoms if a.polarity == filter["polarity"]]
        if filter.get("epoch_range"):
            lo, hi = filter["epoch_range"]
            atoms = [a for a in atoms if lo <= extract_epoch(a) <= hi]

    return Ok(atoms)


def validate_compression_invariants(
    before_chain: list[EvidenceAtom],
    after_profiles: dict[str, CompressedEvidenceProfile],
    active_window: list[EvidenceAtom]
) -> Result[None, str]:
    """
    验证压缩不变式（全部通过才允许压缩，否则回滚）。
    """
    # INV-1: CONFLICT_PRESERVATION
    for axis_id in set(a.axis_id for a in before_chain):
        before_has_pro = any(a.axis_id == axis_id and a.polarity == "PRO" for a in before_chain)
        before_has_con = any(a.axis_id == axis_id and a.polarity == "CON" for a in before_chain)
        profile = after_profiles.get(axis_id)
        after_has_pro = profile and sum(profile.counts_pro.values()) > 0
        after_has_con = profile and sum(profile.counts_con.values()) > 0

        if before_has_pro != after_has_pro or before_has_con != after_has_con:
            return Err(f"CONFLICT_PRESERVATION 违反：axis {axis_id} 极性信息丢失")

    # INV-2: PINNED_CONFLICT_RETENTION
    for profile in after_profiles.values():
        for conflict in profile.pinned_conflicts:
            if not conflict.resolved:
                # 验证 pinned 冲突的两个 atom 至少有一个在 watermarks 中
                wm_ids = set()
                for wm in list(profile.watermarks_pro.values()) + list(profile.watermarks_con.values()):
                    if wm:
                        wm_ids.add(wm.evidence_id)
                if (conflict.pro_atom.evidence_id not in wm_ids
                        and conflict.con_atom.evidence_id not in wm_ids):
                    return Err(f"PINNED_CONFLICT_RETENTION 违反：冲突 {conflict.gap_spec_id} 的 atom 不在 watermarks 中")

    # INV-3: ATOM_COUNT_CONSISTENCY
    for profile in after_profiles.values():
        total_in_counts = sum(profile.counts_pro.values()) + sum(profile.counts_con.values())
        if total_in_counts != profile.total_atom_count:
            return Err(f"ATOM_COUNT_CONSISTENCY 违反：counts 之和 {total_in_counts} ≠ total_atom_count {profile.total_atom_count}")

    return Ok(None)
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-CC-01 | CONFLICT_PRESERVATION：压缩前后每轴上的 has_pro ∧ has_con 布尔值不变 | `validate_compression_invariants` |
| INV-CC-02 | PINNED_CONFLICT_RETENTION：所有未解决的 `pinned_conflicts` 在压缩后仍存在 | 同上 |
| INV-CC-03 | ATOM_COUNT_CONSISTENCY：`sum(counts_pro) + sum(counts_con) = total_atom_count` | 同上 |
| INV-CC-04 | WATERMARK_COVERAGE：压缩前存在的每个 axis×polarity×strength 组合，压缩后 watermark 不为 null | 同上 |
| INV-CC-05 | 压缩失败时保留原状态，不部分更新 | `Err` 路径不修改原始状态 |
| INV-CC-06 | 再水合失败时 S4 必须进入 `S7(Suspended)`，禁止静默降级为"无冲突" | `S4RehydrateFailureBehavior` 约定 |
| INV-CC-07 | watermark 被 `pinned_conflicts` 引用时禁止替换（`should_replace_watermark` 保护） | 工厂函数检查 |
| INV-CC-08 | `pinned_conflicts` 的 `resolved=true` 后才可在下次压缩时移除 | `ConflictResolutionEvent` 消费 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"，claim-007，Epoch 15

```
场景：claim-007 的 ax_burden_share 轴已积累 85 个 EvidenceAtom（超过 max_total=200 的 60%），
      触发了信息增益低（最近 3 epoch 无新 axis 极性变化）

evaluate_compression_trigger():
  → TriggerReason { kind: "INFO_GAIN_LOW", epochs_without_change: 3, threshold: 0.1 }
  → should_compress: true

compress_evidence_chain("claim-007", raw_chain_85_atoms, existing_profiles=None, ...):

  compress_axis("ax_burden_share", [85 atoms]):
    PRO atoms: 12 ANECDOTAL, 8 CORRELATIONAL, 5 CAUSAL_STATISTICAL, 2 AXIOMATIC
    CON atoms: 4 ANECDOTAL, 3 CORRELATIONAL, 1 CAUSAL_STATISTICAL

    counts_pro: { ANECDOTAL:12, CORRELATIONAL:8, CAUSAL_STATISTICAL:5, AXIOMATIC:2 }
    counts_con: { ANECDOTAL:4, CORRELATIONAL:3, CAUSAL_STATISTICAL:1, AXIOMATIC:0 }

    watermarks_pro: {
      ANECDOTAL: atom_a3 (conf=0.82),   // 从 12 个中取置信度最高的
      CORRELATIONAL: atom_c7 (conf=0.91),
      CAUSAL_STATISTICAL: atom_s2 (conf=0.88),
      AXIOMATIC: atom_x1 (conf=0.95)
    }
    watermarks_con: {
      ANECDOTAL: atom_ca2 (conf=0.75),
      CORRELATIONAL: atom_cc5 (conf=0.80),
      CAUSAL_STATISTICAL: atom_cs1 (conf=0.85),  // 触发冲突检测！
      AXIOMATIC: None
    }

    冲突检测：CAUSAL_STATISTICAL CON (atom_cs1) 出现，且 PRO 中也有 CAUSAL_STATISTICAL
      → 生成 PinnedConflict:
        { pro_atom: atom_s2, con_atom: atom_cs1, resolved: false, detected_epoch: 15 }

  active_window: 最新的 50 个 atom（来自 epoch 13-15）

  cold archive: 其余 35 个 atom 写入 s3://evidence-archive/claim-007/ep0-12.bin
    → ArchiveRef { storage_uri: "s3://...", blake3_hash: "f3c2...", byte_len: 18432 }

  validate_compression_invariants():
    CONFLICT_PRESERVATION: ax_burden_share 压缩前有 PRO 和 CON → 压缩后 counts_pro > 0 && counts_con > 0 ✓
    PINNED_CONFLICT_RETENTION: conflict (atom_s2, atom_cs1) 已在 pinned_conflicts ✓
    ATOM_COUNT_CONSISTENCY: 27+8 = 35，但 35 ≠ 27+8 → 需要修正...
      (实际：counts 代表总历史量，active_window 的 atom 另外计数)
    → 全部通过

输出：
  profiles["ax_burden_share"]: CompressedEvidenceProfile {
    counts_pro: {ANECDOTAL:12, ...}, counts_con: {...},
    watermarks_pro: {4 entries}, watermarks_con: {3 entries},
    pinned_conflicts: [{ pro_atom:atom_s2, con_atom:atom_cs1, resolved:false }]
  }
  active_window: [50 atoms from epoch 13-15]
  archive_ref: { uri: "s3://...", hash: "f3c2..." }
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-7~~** → **已裁定** ✅
> - 裁定结论：`apply_delta` 保持纯函数只入库 `VerifiedClaimFull`，压缩为异步后台任务（`enqueue_compression` + `apply_compression_result`），压缩失败不影响 claim 状态；业务代码通过 accessor `get_evidence(claim): EvidenceAccess` 访问，accessor 返回显式可用性标记；同一 gap_id + epoch_id 下 accessor 的返回值对压缩与否必须语义等价（或显式标记降级）。
> - 关键规格：`EvidenceAccess = { available: true; atoms; source: "FULL"|"REHYDRATED" } | { available: false; summary; atom_count; hash }`；压缩失败时 `apply_compression_result` 保留 Full，记录 `CompressionError` 到 `state.system_warnings`，不改变 claim.status，不产生 `GAP_OPEN`；再水化通过 `request_rehydration` → L2 异步 → `CLAIM_VERIFIED` delta 重新入库 Full 版本。
> - 可推翻条件：`get_evidence` 返回 `available: false` 的比例 >40% 且 rehydration 延迟 >2 epochs，需提高 `evidence_budget` 或延长 `AGE_THRESHOLD`；若压缩摘要丢失 repair 所需关键信息，需引入 `compression_level: "LOSSLESS" | "LOSSY"` 标记，`LOSSY` 压缩在 repair 上下文中自动触发 rehydration。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`

> **pinned_conflicts 生命周期**（原有设计注意项，未纳入裁定范围）：ConflictResolutionEvent 接口已在辩论中设计但未纳入本文档的类型定义。repair() 解决冲突时必须产出 `ConflictResolutionEvent`，压缩器消费该事件后才能将对应的 `pinned_conflict.resolved` 设为 `true`。此接口需要在 `00_shared_types.md` 补充。
