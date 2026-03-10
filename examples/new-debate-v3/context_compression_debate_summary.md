# v3 认知引擎：上下文管理与压缩策略 裁判总结

> 2026-03-10T12:10:07.403380



# 辩论裁判最终裁定

---

## 第一部分：白话版结论

### 核心共识：三位辩手在"最紧迫爆炸点"上完全一致

三位辩手——Linus、Ssyram、Kant——在以下判断上**完全收敛**，无任何分歧：

> **爆炸点二（Layer 2 的 `evidence_chain` 无界增长）是最紧迫的，因为它是正确性问题而非性能问题。**

这个共识本身就是裁定的基石。我不需要仲裁"先解决哪个"，因为没有争议。真正需要裁定的是**怎么压缩**——三人在压缩策略的五个子问题上产生了尖锐对立。

---

### 爆炸点一：evidence_chain 的压缩形态

**比喻**：想象你经营一个法庭档案室。每个案件（claim）的证据文件（evidence_chain）越堆越高。法官（S4 冲突检测）每次开庭都要翻全部文件才能判断"有没有矛盾证据"。问题是：文件多到法官一天读不完（上下文窗口爆了），怎么办？

三位辩手提出了三种档案管理方案：

| 方案 | 比喻 | 核心差异 |
|------|------|----------|
| **Linus 的分层账本** | 把旧文件做成统计卡片（按证据强度分桶计数），保留几份原件样本 | 强调"可重算"：规则变了可以重新算分 |
| **Ssyram 的水位线+固化** | 每种级别的正反证据各保留一份"代表性原件"，冲突一旦发现就钉死不许归档 | 强调"LLM 需要读文本"：光有数字没法做语义冲突检测 |
| **Kant 的构成性索引** | 区分"法官判案必须看的"（构成性）和"方便理解但可省略的"（调节性），前者绝不压缩 | 强调认识论区分：不要把便利手段当成必要条件 |

---

### 裁定 1：压缩后的数据形态——Ssyram 的 Watermarked Ledger 胜出，但必须吸收 Linus 的 StrengthCounts

**裁定理由**：

Ssyram 在第 11 轮打出的关键一击是致命的：*"如果你给 S4 的 prompt 里只有 `pro_counts: { CAUSAL_STATISTICAL: 2 }`，LLM 拿什么去和新来的 Atom 做语义比对？"*

这个攻击精准命中了 Linus 和 Kant 方案的共同盲点。S4 节点是 LLM 驱动的——它需要**具体的命题文本**来判断新证据是否与旧证据语义冲突。光给统计计数，LLM 变成了瞎子。Linus 的 `top_atoms` 部分缓解了这个问题，但 Ssyram 的 watermarks 按强度等级分桶保留代表性文本，覆盖更系统。

但 Ssyram 的初始方案有一个被 Linus 打穿的致命漏洞：只保留 "strongest" 2 条会导致特定强度等级的证据被挤掉（第 4 轮的 `CAUSAL_STATISTICAL CON` 被 `AXIOMATIC PRO` 挤掉的反例）。Ssyram 在第 8 轮接受了这个攻击并修正为**按强度分桶的水位线**（每个强度等级 × 每个极性最多 1 个 Atom），这消除了该反例。

同时，Linus 和 Kant 在 StrengthCounts（按强度分桶的计数向量）上形成的共识是正确的：PA 算分需要充分统计量，且规则表可能版本化演进，存原始计数比存折算后的权重和更抗演化。

**具体行为差异（例子）**：

假设 axis "安全性" 上历史有 3 条 PRO（2 条 ANECDOTAL, 1 条 CAUSAL_STATISTICAL）和 1 条 CON（CAUSAL_STATISTICAL），且这条 CON 出现在 epoch 2，现在已经是 epoch 15：

- **不压缩**：S4 读到全部 15 个 epoch 的所有原子，prompt 超限被截断，恰好截掉了 epoch 2 的那条 CON → 冲突漏检 → `EVIDENCE_CONFLICT` 不触发 → 系统错误终止
- **Linus 方案（只有 counts + top_atoms）**：S4 看到 `con_counts: { CAUSAL_STATISTICAL: 1 }`，知道有反面证据，但不知道具体说了什么 → LLM 无法判断新来的 PRO 是否真的与旧 CON 矛盾 → 冲突检测退化为"有没有相反极性"的布尔判定 → 假冲突爆炸
- **Ssyram 修正方案（counts + watermarks + pinned_conflicts）**：S4 看到 `watermarks_con.CAUSAL_STATISTICAL` 里有那条具体的 CON 原子文本，加上 `counts_con` 的统计量 → LLM 能做语义比对，PA 能做规则重算 → 两个需求都满足，且空间严格有界（每 axis 最多 8 个 watermark atom + O(1) 计数）

**可能需要修正的场景**：如果未来 axis_rulebook 需要依赖 atom 的非 strength/polarity 特征（如来源可信度分层、地域适用性）来做折算或冲突判定，则 watermark 的分桶维度需要扩展。这是 Kant 第 9 轮明确指出的可推翻条件，裁定接受。

---

### 裁定 2：冲突固化（Pinning）机制——Ssyram 胜出

**裁定理由**：

Ssyram 在第 8 轮提出的 `pinned_conflicts` 机制解决了一个所有方案都面临的核心问题：**一旦 S4 检测到冲突并生成了 `EVIDENCE_CONFLICT` 类型的 GapSpec，这个冲突必须作为阻塞性条件驻留在热区，直到 Layer 1 的 `repair()` 显式解决它。**

Linus 在第 4 轮的攻击精准指出：如果冲突相关的证据被归档到冷区，Layer 1 的 `repair()` 拿不到 `evidence_summary`，修复链条就断了。Ssyram 的 pinning 机制通过"钉死在热区"直接消除了这个问题。

Kant 的方案虽然在概念上区分了"构成性 vs 调节性"，但没有给出等价的接口级保护机制。Linus 的方案通过 `has_pro/has_con` 布尔标记来保留冲突信号，但被 Kant 在第 6 轮精确打穿：布尔标记是分析判断，把"不同 scope/不同 discriminator 下的同极性"错误等同了。

**具体行为差异（例子）**：

假设 S4 在 epoch 5 检测到 axis "可靠性" 上的 `EVIDENCE_CONFLICT`（一条说"开源模型在医疗场景下不可靠"，一条说"开源模型在代码生成场景下非常可靠"）。这个冲突被报告给 Layer 1 的 `repair()`：

- **无 pinning**：epoch 8 时压缩触发，这两条证据都不是"最近 3 epoch"的，也可能不是"最强"的 → 被归档 → repair() 下一次调用时发现 `evidence_summary` 为空 → 要么修复失败，要么误认为冲突已解决
- **有 pinning**：这对冲突被钉在 `pinned_conflicts` 里 → 无论多少 epoch 过去，只要 repair() 没有显式解决（通过 refine schema/增加 discriminator 等），它就一直在热区 → repair() 每次都能读到完整的冲突上下文

**可能需要修正的场景**：如果 pinned_conflicts 本身无界增长（大量 axis 同时产生大量冲突），就需要一个"冲突合并"策略。这是当前方案中未充分讨论的边缘情况，但在实际工作负载中，同一 claim 上活跃的阻塞性冲突数量应当有限（否则 claim 本身应该被标为 REJECTED 而非继续修复）。

---

### 裁定 3：冷区归档的再水合（Rehydrate）接口——Linus 胜出

**裁定理由**：

Linus 在第 4 轮对 Ssyram 的攻击最尖锐的部分不是关于 strongest 被挤掉，而是关于 `archive_cursor` 的实际可操作性：*"load_archived_evidence 什么时候调用？调用失败时 S4 走哪个分支？给我明确分支，不要'应该可以'。"*

这个质问暴露了一个关键的工程现实：冷区归档不是"写了就忘"，必须有**明确的再水合触发条件、失败处理分支、以及对应的状态机转换**。Linus 在第 10 轮的最终方案给出了最完整的 `RehydrateError` 类型和 `PromptMaterializer` 接口，包括 IO 失败时的明确分支。

Ssyram 和 Kant 都承认冷区归档的必要性，但都没有给出等价的失败处理规范。

**具体行为差异（例子）**：

想象档案室着火了（IO 失败），法官需要调阅一份旧证据来确认冲突：

- **Linus 方案**：系统明确知道"拿不到归档"，走 `RehydrateError.MISSING_REF` 分支 → S4 进入 `S7(Suspended)` 状态 → 不会在缺失信息的情况下做出错误判定 → 等归档恢复后重试
- **Ssyram/Kant 方案**：`archive_cursor` 指向的归档读不到 → 不明确的行为（Ssyram 没给失败分支，Kant 在理论上说了"应留审计痕迹"但没给接口）→ 可能静默降级为"无冲突" → 错误判定

---

### 裁定 4：触发条件——混合触发，Linus 的 token 硬上限为主，Kant 的信息增益为辅

**裁定理由**：

三人在触发条件上的分歧：
- **Linus**：硬性 token 预算 + atom 数量阈值（`max_hot_atoms = 50`, `max_total_atoms = 200`）
- **Ssyram**：基于 atom 数量的阈值触发（`MAX_ACTIVE_ATOMS_PER_AXIS = 3`）
- **Kant**：信息增益低时触发（最近 3 epoch 新增 atom 都落在已覆盖 axis 且不改变 polarity/strength）

Ssyram 在第 5 轮对 Kant 的攻击指出了信息增益触发的致命问题：*"微弱信号问题"*——如果第 4 个 epoch 出现了一个 strength 虽低但能推翻整个前提的新证据，而系统已因"信息增益低"触发了压缩，这个信号可能被归档区的统计偏置淹没。

这个攻击成立，但不足以否定信息增益触发的全部价值。正确的做法是：

1. **Linus 的 token 硬上限作为不可违反的安全网**（防止 prompt 爆炸）
2. **Kant 的信息增益作为"提前压缩"的优化触发器**（在 token 还没满的时候就开始压缩冗余内容）
3. **两者取 OR**：任一条件触发即压缩

**可能需要修正的场景**：信息增益的 3-epoch 窗口大小是经验值。如果实际工作负载中 claim 的证据到达模式是高度突发的（长期沉默后突然涌入），则窗口需要调大或改为自适应。

---

### 裁定 5：Kant 的"构成性 vs 调节性"框架——裁定为有价值的设计原则，但不作为实现约束

Kant 始终坚持：压缩前必须区分哪些数据是"构成性的"（决定系统判定的正确性）、哪些是"调节性的"（帮助理解但可省略）。这个框架在**设计审查**时有价值——它迫使工程师回答"这个字段被压缩后，哪个不变式会被违反？"

但在**实现层面**，这个区分最终被 Ssyram 和 Linus 的具体接口吸收了：
- 构成性 = pinned_conflicts + watermarks + counts（不可压缩或只可有界压缩）
- 调节性 = 完整的 atom 文本叙事、审计日志（可归档到冷区）

所以裁定：**Kant 的框架是正确的设计检查清单，但不需要作为独立的类型层暴露在接口中。** 它的价值已经被其他两人的具体机制实现了。

---

### 其他爆炸点的快速裁定

| 爆炸点 | 紧迫性 | 裁定 |
|--------|--------|------|
| **ranking_history** | 中低 | 三人一致同意滑动窗口即可。裁定采纳。窗口大小 = 最近 5 epochs。 |
| **rejection_history** | 低 | 已是哈希集合，主要是性能问题。裁定：保持现状，监控集合大小即可。 |
| **ChallengeTracker** | 中 | Prompt 体积问题但不影响 truth-maintenance。裁定：按 challenge 状态分桶，只有 ACTIVE 的进 prompt。 |
| **L1 对话历史** | 中 | Linus 第 10 轮的 `PromptMaterializer` 方案覆盖了这个需求。裁定采纳。 |
| **Judge prompt** | 中低 | 同 ChallengeTracker，按需注入。 |

---

## 第二部分：可实现性摘要

### 1. 各爆炸点的压缩策略最终裁定表

```typescript
// ==========================================
// 最终裁定：evidence_chain 压缩后的类型形态
// ==========================================

type Strength = "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL" | "AXIOMATIC";
type Polarity = "PRO" | "CON";

/**
 * 最终裁定的压缩形态：CompressedEvidenceProfile
 * 来源：Ssyram 的 Watermarked Ledger（第11轮）
 *       + Linus/Kant 的 StrengthCounts（第7/9轮）
 *       + Ssyram 的 Pinning 机制（第8轮）
 */
interface CompressedEvidenceProfile {
  axis_id: string;

  // [构成性-算分] 充分统计量，支持 rulebook 版本化重算
  // 来源：Linus R2 + Kant R3 共识
  counts_pro: Record<Strength, number>;
  counts_con: Record<Strength, number>;

  // [构成性-冲突检测] 按强度分桶的水位线，每桶最多 1 个 Atom
  // 空间上界：每 axis 最多 8 个 Atom（4 strength × 2 polarity）
  // 来源：Ssyram R3 修正后方案
  watermarks_pro: Record<Strength, EvidenceAtom | null>;
  watermarks_con: Record<Strength, EvidenceAtom | null>;

  // [构成性-阻塞保护] 冲突固化：S4 检测到的未解决冲突钉在热区
  // 来源：Ssyram R2，响应 Linus R1 对 repair() 断链的攻击
  pinned_conflicts: PinnedConflict[];

  // [调节性-审计] 冷区归档引用
  // 来源：Linus R3 的 ArchiveRef 机制
  archive_ref: ArchiveRef | null;

  // [元数据] 规则版本 + epoch 范围
  strength_rulebook_version: string;
  covered_epoch_range: [number, number];
  total_atom_count: number;
}

interface PinnedConflict {
  gap_spec_id: string;
  gap_kind: "EVIDENCE_CONFLICT" | "UNRESOLVED_DEFEATER";
  pro_atom: EvidenceAtom;  // 冲突对的正方
  con_atom: EvidenceAtom;  // 冲突对的反方
  detected_epoch: number;
  resolved: boolean;        // repair() 解决后设为 true，可在下次压缩时移除
}

/**
 * 压缩后的 VerifiedClaim
 */
interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<string, number>>;

  // 替代原有的 evidence_chain: EvidenceAtom[]
  evidence_profiles: Record<string, CompressedEvidenceProfile>; // key: axis_id

  // 热区：最近 N 个 epoch 的原始 Atom（供 LLM 上下文窗口使用）
  active_window: EvidenceAtom[];  // 上界: MAX_ACTIVE_ATOMS
}
```

### 2. 统一的压缩触发检测接口

```typescript
// ==========================================
// 压缩触发检测接口
// ==========================================

interface CompressionTriggerConfig {
  // 硬性安全网（Linus 方案，不可违反）
  max_hot_atoms_per_claim: number;       // 推荐: 50
  max_total_atoms_per_claim: number;     // 推荐: 200
  prompt_token_budget: number;           // 推荐: 按模型窗口的 40%

  // 优化触发器（Kant 方案，提前压缩冗余内容）
  info_gain_window_epochs: number;       // 推荐: 3
  min_info_gain_threshold: number;       // 推荐: 0.1 (新 atom 未改变任何 axis 的 polarity 或 max_strength)
}

type TriggerReason =
  | { kind: "TOKEN_BUDGET_EXCEEDED"; current: number; limit: number }
  | { kind: "ATOM_COUNT_EXCEEDED"; current: number; limit: number }
  | { kind: "INFO_GAIN_LOW"; epochs_without_change: number; threshold: number }
  | { kind: "EXPLICIT_REQUEST" };  // 手动触发（调试/审计）

interface CompressionTriggerResult {
  should_compress: boolean;
  reasons: TriggerReason[];           // 可能多个同时触发
  claim_ids_affected: string[];       // 哪些 claim 需要压缩
}

/**
 * 触发检测函数签名
 * 对每个 claim 独立评估（避免无关 claim 被连带压缩）
 */
function evaluateCompressionTrigger(
  claim: VerifiedClaim,
  config: CompressionTriggerConfig,
  current_epoch: number
): CompressionTriggerResult;
```

### 3. 压缩执行与语义等价性验证接口

```typescript
// ==========================================
// 压缩执行接口
// ==========================================

interface CompressError {
  kind: "INVARIANT_BREAK" | "HASH_MISMATCH" | "IO_FAIL" | "PINNED_CONFLICT_LOSS";
  detail: string;
  claim_id: string;
}

/**
 * 压缩函数签名
 * 输入：原始 evidence_chain + 当前 profiles（如有）
 * 输出：Result 类型，失败时保留原状态
 */
function compressEvidenceChain(
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

// ==========================================
// 语义等价性验证接口（压缩后的不变式检查）
// ==========================================

interface DriftTestSpec {
  test_id: string;
  description: string;
  invariant: (before: VerifiedClaim, after: VerifiedClaim) => boolean;
}

/**
 * 核心不变式（必须全部通过，否则压缩回滚）
 */
const MANDATORY_DRIFT_TESTS: DriftTestSpec[] = [
  {
    test_id: "CONFLICT_PRESERVATION",
    description: "压缩前后，所有 axis 上 has_pro ∧ has_con 的布尔值不变",
    invariant: (before, after) => {
      // 对每个 axis，检查压缩前 evidence_chain 中是否存在 PRO 和 CON
      // 与压缩后 profiles 中 counts_pro > 0 和 counts_con > 0 是否一致
      return allAxesConflictPreserved(before, after);
    }
  },
  {
    test_id: "SCORE_EQUIVALENCE",
    description: "压缩前后，PA 算分结果在 epsilon 内一致",
    invariant: (before, after) => {
      const score_before = computeAxisScores(before.evidence_chain, currentRulebook());
      const score_after = recomputeFromProfiles(after.evidence_profiles, currentRulebook());
      return allScoresWithinEpsilon(score_before, score_after, 1e-9);
    }
  },
  {
    test_id: "PINNED_CONFLICT_RETENTION",
    description: "所有未解决的 pinned_conflicts 在压缩后仍存在",
    invariant: (before, after) => {
      const unresolved_before = getAllUnresolvedConflicts(before);
      const unresolved_after = getAllPinnedConflicts(after);
      return isSubset(unresolved_before, unresolved_after);
    }
  },
  {
    test_id: "WATERMARK_COVERAGE",
    description: "对每个 axis × polarity × strength 组合，如果压缩前存在该类 atom，压缩后 watermark 不为 null",
    invariant: (before, after) => {
      return allOccupiedBucketsHaveWatermarks(before, after);
    }
  },
  {
    test_id: "ATOM_COUNT_CONSISTENCY",
    description: "压缩后 sum(counts_pro) + sum(counts_con) + active_window.length == total_atom_count",
    invariant: (_before, after) => {
      return atomCountConsistent(after);
    }
  }
];

// ==========================================
// 再水合（Rehydrate）接口 —— 来源：Linus R3
// ==========================================

interface RehydrateError {
  kind: "MISSING_REF" | "IO_FAIL" | "DECODE_FAIL" | "INTEGRITY_CHECK_FAIL";
  ref: ArchiveRef;
  detail: string;
}

/**
 * 从冷区取回原始 Atom
 * 失败时 S4 必须进入 S7(Suspended)，不得静默降级
 */
function rehydrateEvidence(
  ref: ArchiveRef,
  filter?: { axis_id?: string; epoch_range?: [number, number]; polarity?: Polarity }
): Result<EvidenceAtom[], RehydrateError>;

/**
 * S4 状态机在 rehydrate 失败时的行为（强制规范）
 */
type S4RehydrateFailureBehavior = {
  action: "SUSPEND";                    // 进入 S7(Suspended)
  reason: RehydrateError;
  retry_policy: { max_retries: number; backoff_ms: number };
  must_not: "SILENTLY_DEGRADE" | "ASSUME_NO_CONFLICT";  // 禁止的行为
};
```

### 4. 实现难度最高的 3 个子问题及风险评估

#### 子问题 1：Watermark 替换策略的正确性（难度：极高）

**问题描述**：当同一 axis × polarity × strength 桶中出现新的 Atom，需要决定是否替换现有 watermark。替换策略必须保证：旧 watermark 如果参与了未解决的 `pinned_conflict`，则不可被替换。

**风险**：
- 替换时未检查 pinned_conflicts 引用 → 冲突对中的一方消失 → repair() 断链
- 不替换则可能保留了过时的、不再有代表性的 Atom → 冲突检测基于过时信息
- **估计工时**：设计 + 实现 + 测试 约 2-3 周
- **缓解措施**：watermark 替换必须先查询 `pinned_conflicts` 中是否引用了当前 watermark；若引用，则保留旧 watermark，新 atom 仅更新 counts。接口签名：

```typescript
function shouldReplaceWatermark(
  current: EvidenceAtom | null,
  candidate: EvidenceAtom,
  pinned: PinnedConflict[]
): { replace: boolean; reason: string };
```

#### 子问题 2：跨 epoch 的 pinned_conflicts 生命周期管理（难度：高）

**问题描述**：`pinned_conflicts` 必须在 `repair()` 显式解决后才能标记为 `resolved = true`。但 `repair()` 的解决方式可能包括 "refine schema"（增加 discriminator 把原来同一 axis 拆成两个）、"add evidence"（新证据消解冲突）、或 "reject claim"。每种方式对 pinned_conflict 的清理逻辑不同。

**风险**：
- Schema 精化后 axis_id 变了，但旧的 pinned_conflict 还引用旧 axis_id → 永远不会被标记 resolved → 热区无界增长
- **估计工时**：3-4 周（需与 Layer 1 repair 逻辑深度集成）
- **缓解措施**：引入 `ConflictResolutionEvent` 类型，repair() 必须显式产出该事件，压缩器消费该事件来更新 pinned_conflicts：

```typescript
interface ConflictResolutionEvent {
  conflict_id: string;            // 对应 PinnedConflict.gap_spec_id
  resolution_kind: "SCHEMA_REFINED" | "EVIDENCE_ADDED" | "CLAIM_REJECTED" | "MANUAL_OVERRIDE";
  new_axis_ids?: string[];        // schema 精化后的新 axis
  resolved_by_epoch: number;
}
```

#### 子问题 3：再水合（Rehydrate）的性能与一致性（难度：高）

**问题描述**：冷区归档使用 content-addressed 存储（`blake3(raw_bytes)`）。当 S4 需要再水合时，必须在可接受的延迟内完成，且归档内容必须与 `ArchiveRef.byte_len` 和 hash 一致。

**风险**：
- 冷存储延迟过高（对象存储可能 100ms+）→ S4 超时 → 频繁进入 S7(Suspended)
- 归档损坏或被意外删除 → 永久数据丢失 → 无法审计
- **估计工时**：2-3 周（存储层 + 完整性校验 + 重试策略）
- **缓解措施**：
  - 温区缓存（WARM tier）：最近被再水合的归档保留在内存中，TTL 配置
  - 写入时双副本 + 完整性校验
  - 监控 `rehydrate_latency_p99` 和 `rehydrate_error_rate`，超过阈值时告警

---

### 5. 最终裁定汇总矩阵

| 爆炸点 | 压缩策略 | 方案来源 | 触发条件 | 语义承诺 | 失败行为 |
|--------|----------|----------|----------|----------|----------|
| **evidence_chain** | Watermarked Ledger + StrengthCounts + Pinning | Ssyram R3 + Linus/Kant R2-R3 | token 硬上限 OR atom 数阈值 OR 信息增益低 | CONFLICT_PRESERVATION, SCORE_EQUIVALENCE, PINNED_RETENTION, WATERMARK_COVERAGE | 压缩失败 → 保留原状态；rehydrate 失败 → S7(Suspended) |
| **ranking_history** | 滑动窗口（5 epochs） | 三人共识 | epoch 推进时自动裁剪 | Top-K 排名在窗口内可重现 | 无特殊失败处理 |
| **rejection_history** | 保持现状（哈希集合） | Linus R1 | 监控集合大小 | 去重正确性 | 集合过大时告警 |
| **ChallengeTracker** | 按状态分桶（ACTIVE 进 prompt） | 综合 | ACTIVE 数量超阈值 | 所有活跃 challenge 可见 | 无特殊失败处理 |
| **L1 对话历史** | PromptMaterializer + ContextBundle | Linus R3 | token 预算 | 声明式注入，不超预算 | 超预算时截断 WARM 层 |

---

**裁定完毕。** 各爆炸点的压缩策略、触发条件、语义承诺、失败行为均已明确给出，无搁置项。实现应从爆炸点二（evidence_chain）开始，按子问题难度排序：先实现 CompressedEvidenceProfile 类型和压缩函数，再实现 Pinning 生命周期管理，最后实现 Rehydrate 链路。