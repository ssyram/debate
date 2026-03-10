# v3 认知引擎：续跑机制的设计 裁判总结

> 2026-03-10T11:24:12.446544



# 最终裁定书

## 第一部分：白话版结论

---

### 问题一：快照（EngineSnapshot）应该保存什么？——"负向空间"（拒绝历史）是否需要全量保存？

**裁定：全量保存拒绝指纹，禁止驱逐。**

**比喻**：想象你是一个侦探在调查一系列入室盗窃案。你维护着一个"已排除嫌疑人"档案。如果你因为档案柜满了，就把三个月前排除的嫌疑人资料扔掉，那当同一个人换了件外套再次出现时，你就会重新调查一遍——白白浪费时间，甚至可能因为信息不全做出错误判断。v3 的 repair 机制就是这个侦探：`is_homologous()` 需要知道"哪些草稿已经被拒绝过"，才能推动从 STRICT → RELAXED → ADJACENT 的策略升级。如果用 LRU 驱逐了早期指纹，系统在第 51 轮可能重新生成与第 1 轮完全同源的失败草稿，陷入死循环。

**具体行为差异示例**：用户在 Epoch 40 暂停，Epoch 50 续跑。假设 Epoch 3 时系统对某个 challenge 尝试过一个方向并被判为同源拒绝。如果采用 GPT-5.4 的 `EPOCH_WINDOW=50` 方案，这条指纹在续跑后仍在窗口内，暂时没问题；但如果用户在 Epoch 60 再次暂停续跑，这条 Epoch 3 的指纹就会被驱逐，repair 将退化为失忆状态。而全量保存方案下，无论何时续跑，行为完全一致。

**Gemini-3.1 的论据在此具有决定性说服力**：每轮最多生成 `max_drafts` 个草稿，100 轮也只有几千条指纹哈希（几十 KB）。为节省这点空间牺牲停机保证，完全不值得。

**可能需要修正的场景**：如果未来 v3 扩展到支持数万个 epoch 的超长运行，且每轮草稿数量显著增加，可以引入**基于 challenge 生命周期的归档策略**（challenge 彻底关闭后其指纹可压缩归档），但绝不是 LRU。

**一句话总结**：拒绝历史是侦探的"已排除嫌疑人档案"，只能追加归档、不能丢弃。

---

### 问题二：用户干预应该如何触达内部状态？——直接修改 `blocks_termination` vs. 注入元证据？

**裁定：禁止直接布尔覆写内部状态标志；干预必须通过"证据注入"路径，让系统自己重新计算。但必须提供一条"公理级证据注入"的快捷通道，使效果等价于覆写但保持语义完整性。**

**比喻**：想象一个工厂的质检流水线。产品有个红灯亮了（blocks_termination = true），说明质检发现了问题。GPT-5.4 的方案相当于让厂长直接走过去把红灯的灯泡拧掉——灯不亮了，但问题还在，下游工序看到"灯没亮"就以为合格了，结果出厂的产品有缺陷。Gemini-3.1 的方案相当于让厂长提交一份新的检测报告（"经专家鉴定，该项指标在本场景下不适用"），质检系统看到这份报告后，按照自己的规则重新评估，自然地把红灯切换为绿灯。效果一样，但流程完整、可追溯。

**具体行为差异示例**：用户认为某个 `EVIDENCE_CONFLICT` 型 Gap 不重要，想让系统继续前进。

- **直接覆写方案**：`{ op: "GAP_NONBLOCKING_OVERRIDE", gap_id: "gap_007" }` → 系统把该 Gap 的 `blocks_termination` 设为 false。但 PA 节点计算分数时，仍然会读到两个极性相反的 `axis_scores`，导致该轴分数震荡。用户以为问题解决了，实际上系统内部仍在"自相矛盾"，最终产出的 AnswerSeed 质量不可预测。

- **证据注入方案**：`{ op: "INJECT_META_EVIDENCE", target_gap_id: "gap_007", evidence_atom: { axis_id: "ax_3", polarity: "PRO", strength: "AXIOMATIC", justification: "利益相关方确认该冲突无实质影响" } }` → 系统在下个 Epoch 启动时，将这条公理级证据注入 L2 状态，Gap 分析器重新评估后，要么将该 Gap 降级为非阻塞，要么自然消解。PA 节点看到的是一致的状态，分数计算不会震荡。

**Gemini-3.1 在这一点上的论证是决定性的**：直接覆写是"掩盖报警器但火仍在燃烧"，这违反了 v3 的认识论诚实性。

**但裁定附带一个重要约束**（吸收 GPT-5.4 的实用性关切）：`INJECT_META_EVIDENCE` 的 `AXIOMATIC` 强度必须保证单 Epoch 内即可消解目标 Gap——不能让用户注入了证据却发现系统还要跑五轮才生效。系统必须在 apply_intervention 阶段即时触发 Gap 重评估。

**可能需要修正的场景**：如果用户确实需要"紧急跳过"某个阻塞以节省时间（比如调试场景），可以提供一个 `DEBUG_OVERRIDE` 操作类型，但必须在快照中永久标记为"完整性已受损"（`integrity_compromised: true`），且 AS 阶段必须在输出中警告。

**一句话总结**：不拧灯泡，而是提交新的检测报告让系统自己重新判定。

---

### 问题三：人类如何知道该干预什么？——纯 ID 引用 vs. 自然语言解析？

**裁定：采用"结构化目录 + ID 引用"的强通道为主，不引入 LLM 自然语言解析作为执行路径。**

**比喻**：想象你在一个大型仓库里找一个零件。GPT-5.4 主张给你一本图文并茂的目录册（catalog），每个零件有编号和简短描述，你查到编号后填写领料单。Gemini-3.1 也同意这个思路。没有人主张让你对着仓库喊一句"给我那个圆圆的银色的东西"然后让 AI 猜你要什么——因为猜错了就是生产事故。

**具体行为差异示例**：用户想把某个评估轴的权重从 0.3 调整为 0.5。

- **ID 引用方案**：用户打开 `catalog.md`，看到 `ax_3: "Ecological Impact (weight: 0.3)"`，然后在 intervention 文件中写 `{ op: "REWEIGHT_AXIS", axis_id: "ax_3", new_weight: 0.5 }`。明确、可验证、不会搞错。

- **自然语言方案**：用户写"把生态影响那个维度的权重提高一些"。系统用 LLM 解析，可能把 `ax_3` 和 `ax_7`（"Environmental Sustainability"）搞混，或者把"提高一些"解释为 0.4 而不是 0.5。一旦解析错误，系统在完全不告警的情况下跑偏。

**双方在此问题上实际立场高度趋同**。GPT-5.4 已明确提出"可推翻条件：如果实践中用户确实无法使用 ID，才引入模糊映射，但必须是显式确认式"。裁定采纳这一立场，但更加严格：**v1 版本完全不实现 LLM 解析通道**，只提供 catalog + ID 引用。

**可能需要修正的场景**：如果用户测试表明 ID 查找的认知负担过高（比如同时存在 50+ 个 Gap 和 100+ 个 Claim），则在 v2 引入"模糊搜索 + 显式确认"辅助工具，但仍不作为执行路径。

**一句话总结**：查目录、填编号、不靠猜。

---

### 问题四：Epoch ID 续跑后是否重置？排名历史是否清空？

**裁定：Epoch ID 必须单调递增（从 N+1 继续），禁止重置为 0。排名历史（ranking_history）必须完整保留。**

**比喻**：想象你在记录一场马拉松比赛的分段计时。选手在 30 公里处暂停休息了一会儿，然后继续跑。你不会把计时器重置为"第 0 公里"，也不会把前 30 公里的分段记录擦掉——否则终点的总成绩和配速分析就全废了。v3 的 PA 节点用 `has_ranking_change()` 判断终止条件，依赖的是连续 N 轮排名是否稳定。如果续跑时清空了排名历史，系统会误以为"我刚开始跑"，可能过早终止或无限延长。

**具体行为差异示例**：系统在 Epoch 12 暂停，此时 PA 节点已经观察到连续 3 轮排名未变（距离终止条件只差 2 轮）。用户做了一个小的权重调整后续跑。

- **重置方案**：Epoch ID 回到 0，ranking_history 清空。系统需要从头积累稳定性证据，可能又跑 12 轮才终止。用户的小调整被放大成了巨大的时间成本。

- **递增方案**：Epoch 从 13 开始，ranking_history 保留但标记 Epoch 12-13 之间有干预。PA 节点看到权重变化后，合理地重置稳定性计数器（因为排名确实可能变了），但保留了历史趋势信息。如果权重调整很小、排名没有实际变化，系统可以在 2 轮内终止。

**Gemini-3.1 正确指出**：`EvaluationAxis.epsilon` 的置信区间演化依赖 epoch_id 作为时间轴。重置 epoch_id 会破坏 t-分布的自由度计算。

**附加裁定**：当干预可能影响排名时（如 `REWEIGHT_AXIS`、`INJECT_META_EVIDENCE`），系统在 apply_intervention 后必须**重置稳定性计数器**（`consecutive_stable_epochs = 0`），但保留完整的 `ranking_history` 供 PA 参考。当干预不影响排名时（如 `ADD_CONTEXT_NOTE`），不重置计数器。

**一句话总结**：马拉松暂停继续跑，里程表不能归零。

---

### 问题五：干预补丁的合并时机——是"预加载到 snapshot 再启动"还是"运行时动态注入"？

**裁定：采用 Epoch 边界预加载方案。干预补丁在系统启动前完成合并和验证，生成一个新的 `snapshot'`，系统从 `snapshot'` 启动，内部逻辑完全无感知。**

**比喻**：这就像给一辆停着的车换轮胎。你不会在车跑到 60 公里/小时的时候换轮胎（运行时注入），而是在车停着的时候（Epoch 边界）换好、检查一遍、确认安全了再启动。

**具体行为差异示例**：用户提交了一个包含 3 个操作的干预文件。

- **预加载方案**：系统先对 3 个操作逐一进行类型检查、引用完整性检查（gap_id 是否存在？axis_id 是否合法？）、不变式检查（权重之和是否仍为 1？），全部通过后生成 `snapshot'`，然后启动。如果第 2 个操作有问题，整个干预被拒绝，用户修正后重新提交。**原子性保证**。

- **运行时注入方案**：系统启动后在某个节点动态读取干预。第 1 个操作成功执行，第 2 个操作失败，系统已经处于"半干预"的不一致状态。要么需要复杂的回滚机制，要么系统带着不一致状态继续跑。

**一句话总结**：停车换胎、检查完毕再上路，不搞高速换胎。

---

## 第二部分：可实现性摘要

### 2.1 EngineSnapshot 最终类型定义

```typescript
type EngineSnapshot = {
  // === 元信息 ===
  snapshot_version: "v1";
  problem_id: string;
  created_at: string; // ISO 8601
  checksum: string;   // 对整个 snapshot 内容（除 checksum 字段本身）的 SHA-256

  // === 执行位点 ===
  safe_point: {
    epoch_id: number; // 最近一次完成的 epoch 编号，单调递增，禁止重置
    stage: "EPOCH_END" | "TERMINATED_BEFORE_AS";
    // "EPOCH_END"：epoch 完整结束，可续跑下一个 epoch
    // "TERMINATED_BEFORE_AS"：PA 已判终止但 AS 未执行，允许用户干预后避免终止
  };

  // === Layer 1：问题框架 ===
  frame: QuestionFrame; // 含 evaluation_axes（每个轴含 weight, epsilon, 置信区间历史）

  // === Layer 2：声明与证据 ===
  claims: {
    testable: TestableClaim[];     // 含 claim_id, status, axis_scores, assumptions
    regulative: RegulativeIdea[];  // 含 idea_id, status
  };
  verified_claims: VerifiedClaim[]; // L2 验证通过的声明，含极性、强度、轴绑定

  // === Layer 2：缺口与挑战 ===
  gaps: GapSpec[]; // 每个含 gap_id, gap_type, blocks_termination, related_axis_ids, related_claim_ids
  challenge_trackers: ChallengeTracker[]; // 每个含 challenge_id, current_stage, consecutive_filtered_epochs

  // === 负向空间（全量持久化，禁止驱逐） ===
  negative_space: {
    rejection_fingerprints: RejectionFingerprint[];
    // 按 challenge 分桶的索引（冗余，可从 fingerprints 重建，存为加速查找）
    by_challenge_index: Record<string, string[]>; // challenge_id -> fp_id[]
  };

  // === PA 状态 ===
  pa_state: {
    ranking_history: RankingEntry[];    // 完整历史，每个含 epoch_id, ranked_claim_ids, scores
    consecutive_stable_epochs: number;  // 当前连续排名未变的 epoch 数
    termination_reason?: string;        // 如果 stage 为 TERMINATED_BEFORE_AS
  };

  // === Repair 状态 ===
  repair_state: {
    draft_pool: HypothesisDraft[];     // 当前待评估的草稿
    // repair 三级推进的当前位置（per challenge）
    strategy_per_challenge: Record<string, "STRICT" | "RELAXED" | "ADJACENT">;
  };

  // === 干预审计日志 ===
  intervention_log: AppliedIntervention[]; // 历史上所有已应用的干预记录
  integrity_status: "CLEAN" | "DEBUG_OVERRIDE_APPLIED"; // 是否曾使用过 DEBUG_OVERRIDE
};

type RejectionFingerprint = {
  fp_id: string;
  epoch: number;
  related_challenge_id: string;
  reason: "HOMOLOGOUS" | "OPEN_TERM_RISK" | "TTL_EXPIRED";
  features: {
    provenance_family: string;
    scope_minhash: string;       // base64 encoded
    verifier_minhash: string;    // base64 encoded
    outcome_anchor_hash: string;
    polarity: 1 | -1 | 0;
  };
};

type RankingEntry = {
  epoch_id: number;
  ranked_claim_ids: string[];
  axis_scores: Record<string, number>;
  has_intervention_before: boolean; // 标记该 epoch 之前是否有干预
};

type AppliedIntervention = {
  applied_at_epoch_boundary: number; // 在哪个 epoch 边界应用
  operations: Operation[];
  applied_at: string; // ISO 8601
  result: "SUCCESS" | "PARTIAL_REJECT";
  rejected_ops?: { op_index: number; reason: string }[];
};
```

### 2.2 InterventionFile 最终格式规范

```typescript
type InterventionFile = {
  intervention_version: "v1";
  target_snapshot_checksum: string; // 必须匹配目标 snapshot 的 checksum，防止对错快照操作
  target_epoch_id: number;          // 必须匹配 snapshot.safe_point.epoch_id

  operations: Operation[]; // 按顺序执行，全部通过才应用（原子性）

  // 可选：人类备注（不参与执行，仅存入审计日志）
  human_notes?: string;
};

type Operation =
  | ReweightAxis
  | InjectMetaEvidence
  | AddContextToFrame
  | RetireChallenge
  | AdjustTerminationParams
  | DebugOverride; // 仅限调试，会污染 integrity_status

// --- 具体操作类型 ---

type ReweightAxis = {
  op: "REWEIGHT_AXIS";
  axis_id: string;
  new_weight: number; // 0 < weight < 1
  // 验证规则：所有轴权重之和必须归一化（系统自动重归一化其余轴，或要求用户提供完整权重表）
  renormalize_others: boolean; // true = 系统自动按比例缩放其余轴; false = 用户必须提供 all_weights
  all_weights?: Record<string, number>; // 当 renormalize_others=false 时必须提供
};

type InjectMetaEvidence = {
  op: "INJECT_META_EVIDENCE";
  target_gap_id: string;
  evidence_atom: {
    axis_id: string;
    polarity: "PRO" | "CON";
    strength: "AXIOMATIC"; // v1 仅支持公理级（保证单 epoch 消解）
    justification: string; // 人类提供的理由，存入审计日志和 VerifiedClaim.provenance
  };
  // 验证规则：target_gap_id 必须存在于 snapshot.gaps 中
  // 效果：在 apply_intervention 阶段立即触发 Gap 重评估
};

type AddContextToFrame = {
  op: "ADD_CONTEXT_TO_FRAME";
  context_type: "SCOPE_REFINEMENT" | "STAKEHOLDER_SPECIFICATION" | "DOMAIN_CONSTRAINT";
  content: string;
  // 效果：追加到 frame.contextual_constraints 或 frame.scope_notes
  // 不直接影响 L2 状态，但 MB/CC 在下个 epoch 会读取
};

type RetireChallenge = {
  op: "RETIRE_CHALLENGE";
  challenge_id: string;
  reason: string;
  // 效果：将 ChallengeTracker 状态设为 RETIRED，其关联的 Gap 触发重评估
  // 验证规则：challenge_id 必须存在
};

type AdjustTerminationParams = {
  op: "ADJUST_TERMINATION_PARAMS";
  // 调整 PA 终止条件的参数（如稳定性阈值）
  params: {
    min_stable_epochs?: number;  // 要求多少轮排名不变才终止
    min_coverage?: number;       // 最低覆盖率
  };
};

type DebugOverride = {
  op: "DEBUG_OVERRIDE";
  target: "GAP" | "CHALLENGE_TRACKER" | "TERMINATION_FLAG";
  target_id: string;
  mutation: Record<string, any>; // 任意字段覆写
  // 约束：应用后 snapshot.integrity_status 永久设为 "DEBUG_OVERRIDE_APPLIED"
  // AS 阶段必须在输出中警告
  i_understand_this_breaks_integrity: true; // 必须为 true，否则拒绝
};
```

### 2.3 人类可读性层接口规范

```typescript
/**
 * 从 EngineSnapshot 生成人类可读目录。
 * 输出格式：Markdown（可选 JSON 副本）。
 * 内容：所有可引用对象的 ID、简短语义描述、当前状态、是否阻塞。
 */
function generateCatalog(snapshot: EngineSnapshot): {
  markdown: string;    // 人类阅读
  json: CatalogJSON;   // 程序化工具使用
};

type CatalogJSON = {
  epoch_id: number;
  status_summary: string; // 一段话概括当前系统状态

  axes: {
    axis_id: string;
    label: string;
    weight: number;
    epsilon: number;
    trend: "CONVERGING" | "OSCILLATING" | "STABLE";
  }[];

  blocking_gaps: {
    gap_id: string;
    gap_type: string;
    human_description: string; // 用自然语言解释这个 Gap 为什么阻塞
    related_axes: string[];
    related_claims: string[];
    suggested_interventions: SuggestedIntervention[]; // 系统建议的操作
  }[];

  active_challenges: {
    challenge_id: string;
    description: string;
    current_stage: "STRICT" | "RELAXED" | "ADJACENT";
    epochs_stuck: number;
  }[];

  top_claims: {
    claim_id: string;
    summary: string;
    current_rank: number;
    axis_scores: Record<string, number>;
  }[];

  recent_ranking_trend: {
    epoch_id: number;
    top_3: string[]; // claim_ids
  }[];
};

type SuggestedIntervention = {
  description: string;           // "注入公理级证据以消解此 Gap"
  template: Operation;           // 预填充的操作模板，用户只需填 justification
};

/**
 * 从 EngineSnapshot 生成干预模板文件。
 * 仅当存在阻塞条件时才生成非空操作列表。
 */
function generateInterventionTemplate(snapshot: EngineSnapshot): InterventionFile;
```

### 2.4 状态合并算法伪代码骨架

```
function apply_intervention(snapshot: EngineSnapshot, intervention: InterventionFile): Result<EngineSnapshot, ValidationError[]> {

  // ========== Phase 1: 前置验证（全部通过才继续） ==========

  // 1.1 版本与身份校验
  ASSERT intervention.target_snapshot_checksum == snapshot.checksum
    ELSE FAIL "Intervention targets wrong snapshot"
  ASSERT intervention.target_epoch_id == snapshot.safe_point.epoch_id
    ELSE FAIL "Epoch mismatch"

  // 1.2 逐个操作进行类型与引用完整性检查
  errors = []
  FOR each op IN intervention.operations:
    SWITCH op.op:
      case "REWEIGHT_AXIS":
        ASSERT op.axis_id EXISTS IN snapshot.frame.evaluation_axes
        IF NOT op.renormalize_others:
          ASSERT op.all_weights covers ALL axis_ids
          ASSERT sum(op.all_weights.values()) ≈ 1.0 (tolerance 0.001)
        ASSERT 0 < op.new_weight < 1

      case "INJECT_META_EVIDENCE":
        ASSERT op.target_gap_id EXISTS IN snapshot.gaps
        ASSERT op.evidence_atom.axis_id EXISTS IN snapshot.frame.evaluation_axes
        ASSERT op.evidence_atom.strength == "AXIOMATIC"

      case "RETIRE_CHALLENGE":
        ASSERT op.challenge_id EXISTS IN snapshot.challenge_trackers

      case "ADJUST_TERMINATION_PARAMS":
        ASSERT op.params.min_stable_epochs >= 1 IF present
        ASSERT op.params.min_coverage >= 0 AND <= 1 IF present

      case "DEBUG_OVERRIDE":
        ASSERT op.i_understand_this_breaks_integrity == true

      case "ADD_CONTEXT_TO_FRAME":
        ASSERT op.content is non-empty string

    IF any assertion failed: errors.push({op_index, reason})

  IF errors.length > 0:
    RETURN Err(errors)   // 原子性：全部拒绝

  // ========== Phase 2: 应用变更（生成 snapshot'） ==========

  next = deep_clone(snapshot)

  FOR each op IN intervention.operations:
    SWITCH op.op:
      case "REWEIGHT_AXIS":
        IF op.renormalize_others:
          old_weight = find_axis(next.frame, op.axis_id).weight
          delta = op.new_weight - old_weight
          remaining_axes = all axes except op.axis_id
          scale_factor = (1 - op.new_weight) / sum(remaining_axes.weights)
          FOR each remaining_axis: remaining_axis.weight *= scale_factor
          find_axis(next.frame, op.axis_id).weight = op.new_weight
        ELSE:
          FOR each (id, w) IN op.all_weights:
            find_axis(next.frame, id).weight = w

      case "INJECT_META_EVIDENCE":
        // 构造一个公理级 VerifiedClaim
        meta_claim = new VerifiedClaim {
          claim_id: generate_uuid("meta_evidence"),
          source: "HUMAN_INTERVENTION",
          axis_scores: { [op.evidence_atom.axis_id]: polarity_to_score(op.evidence_atom.polarity) },
          strength: 0.95,  // AXIOMATIC 级别
          provenance: op.evidence_atom.justification
        }
        next.verified_claims.push(meta_claim)

        // 立即触发 Gap 重评估
        target_gap = find_gap(next.gaps, op.target_gap_id)
        reevaluated = reevaluate_gap(target_gap, next.verified_claims, next.claims)
        // reevaluate_gap 使用与系统内部完全相同的 Gap 分析逻辑
        replace_gap(next.gaps, op.target_gap_id, reevaluated)

      case "RETIRE_CHALLENGE":
        tracker = find_tracker(next.challenge_trackers, op.challenge_id)
        tracker.status = "RETIRED"
        tracker.retired_reason = op.reason
        // 触发关联 Gap 重评估
        related_gaps = find_gaps_by_challenge(next.gaps, op.challenge_id)
        FOR each gap IN related_gaps:
          reevaluated = reevaluate_gap(gap, next.verified_claims, next.claims)
          replace_gap(next.gaps, gap.gap_id, reevaluated)

      case "ADJUST_TERMINATION_PARAMS":
        IF op.params.min_stable_epochs:
          next.pa_state.termination_params.min_stable_epochs = op.params.min_stable_epochs
        IF op.params.min_coverage:
          next.pa_state.termination_params.min_coverage = op.params.min_coverage

      case "ADD_CONTEXT_TO_FRAME":
        next.frame.contextual_notes.push({
          type: op.context_type,
          content: op.content,
          added_at_epoch: next.safe_point.epoch_id
        })

      case "DEBUG_OVERRIDE":
        // 直接应用任意突变
        target_obj = find_by_type_and_id(next, op.target, op.target_id)
        Object.assign(target_obj, op.mutation)
        next.integrity_status = "DEBUG_OVERRIDE_APPLIED"

  // ========== Phase 3: 后置不变式检查 ==========

  ASSERT sum(next.frame.evaluation_axes.map(a => a.weight)) ≈ 1.0
  ASSERT next.safe_point.epoch_id == snapshot.safe_point.epoch_id  // 还没递增
  ASSERT all gap references point to existing claims/axes
  ASSERT all challenge_tracker references point to existing challenges
  // 如果任何 INJECT_META_EVIDENCE 被应用，确认目标 Gap 确实已被重评估
  FOR each applied INJECT_META_EVIDENCE op:
    ASSERT find_gap(next.gaps, op.target_gap_id).last_evaluated_epoch == next.safe_point.epoch_id

  // ========== Phase 4: 准备续跑 ==========

  // 判断干预是否可能影响排名
  ranking_affecting_ops = ["REWEIGHT_AXIS", "INJECT_META_EVIDENCE", "RETIRE_CHALLENGE", "DEBUG_OVERRIDE"]
  IF any operation is ranking_affecting:
    next.pa_state.consecutive_stable_epochs = 0  // 重置稳定性计数器

  // Epoch ID 递增
  next.safe_point.epoch_id += 1
  next.safe_point.stage = "EPOCH_END"  // 准备从下一个 epoch 开始

  // 记录干预日志
  next.intervention_log.push({
    applied_at_epoch_boundary: snapshot.safe_point.epoch_id,
    operations: intervention.operations,
    applied_at: now(),
    result: "SUCCESS"
  })

  // 重算 checksum
  next.checksum = sha256(serialize_without_checksum(next))

  RETURN Ok(next)
}
```

### 2.5 端到端 Trace

```
═══════════════════════════════════════════════════════════════
  EPOCH 7 运行中...
═══════════════════════════════════════════════════════════════

[Epoch 7] QN → MB → CC → D2 → PA
  PA 计算结果:
    - Claim C1 (ax_1: 0.82, ax_2: 0.71, ax_3: 0.45)
    - Claim C2 (ax_1: 0.65, ax_2: 0.88, ax_3: 0.72)
    - 排名: [C2, C1]（与 Epoch 6 相同，consecutive_stable = 3）
    - 阻塞 Gap: gap_014 (type: EVIDENCE_CONFLICT, blocks_termination: true)
      → 原因: C1 和 C2 在 ax_3 上存在极性冲突的证据
    - should_terminate() = false（存在阻塞 Gap）

[Epoch 7] PA → RB (repair)
  repair 对 gap_014 尝试 STRICT 策略，生成草稿 D7_1
  is_homologous(D7_1, history) = true → 被拒绝，记录指纹 fp_071
  repair 对 gap_014 尝试 RELAXED 策略，生成草稿 D7_2
  is_homologous(D7_2, history) = false → 加入 draft_pool
  Epoch 7 结束

═══════════════════════════════════════════════════════════════
  系统暂停，写出快照
═══════════════════════════════════════════════════════════════

[System] 写出 engine_snapshot_ep7.json
  - safe_point: { epoch_id: 7, stage: "EPOCH_END" }
  - gaps: [gap_014: { type: EVIDENCE_CONFLICT, blocks_termination: true }]
  - negative_space: 71 条 fingerprint（含新增的 fp_071）
  - pa_state: { consecutive_stable_epochs: 3, ranking_history: [...7 entries] }
  - checksum: "a3f8c1..."

[System] 生成 catalog_ep7.md:
  ┌─────────────────────────────────────────────────────┐
  │ === Epoch 7 状态目录 ===                              │
  │                                                       │
  │ 📊 评估轴:                                            │
  │   ax_1: "Economic Feasibility" (weight: 0.4)         │
  │   ax_2: "Social Acceptance"    (weight: 0.35)        │
  │   ax_3: "Ecological Impact"    (weight: 0.25)        │
  │                                                       │
  │ 🚧 阻塞 Gap (1):                                     │
  │   gap_014: 证据冲突                                    │
  │     类型: EVIDENCE_CONFLICT                            │
  │     描述: Claim C1 和 C2 在"生态影响"轴上提供了         │
  │          相互矛盾的证据。C1 认为方案对生态有轻微正面      │
  │          影响，C2 认为有显著负面影响。                    │
  │     建议操作:                                          │
  │       (a) 注入专家判断以消解冲突                         │
  │       (b) 调整 ax_3 权重降低其影响                      │
  │       (c) 添加范围限定以排除该冲突场景                   │
  │                                                       │
  │ 📈 当前排名 (连续稳定 3 轮):                           │
  │   #1: C2 "分布式微电网方案" (综合分: 0.78)             │
  │   #2: C1 "集中式储能方案"   (综合分: 0.71)             │
  │                                                       │
  │ 🔬 活跃挑战 (2):                                      │
  │   ch_003: "微电网维护成本" (RELAXED, stuck 2 epochs)   │
  │   ch_005: "生态影响评估方法" (STRICT, stuck 0 epochs)  │
  └─────────────────────────────────────────────────────┘

[System] 生成 intervention_ep7_template.yaml:
  intervention_version: "v1"
  target_snapshot_checksum: "a3f8c1..."
  target_epoch_id: 7
  operations:
    - op: "INJECT_META_EVIDENCE"
      target_gap_id: "gap_014"
      evidence_atom:
        axis_id: "ax_3"
        polarity: "PRO"           # ← 用户需决定
        strength: "AXIOMATIC"
        justification: ""         # ← 用户需填写
  human_notes: ""

═══════════════════════════════════════════════════════════════
  用户编辑干预文件
═══════════════════════════════════════════════════════════════

[Human] 编辑 intervention_ep7.yaml:
  intervention_version: "v1"
  target_snapshot_checksum: "a3f8c1..."
  target_epoch_id: 7
  operations:
    - op: "INJECT_META_EVIDENCE"
      target_gap_id: "gap_014"
      evidence_atom:
        axis_id: "ax_3"
        polarity: "PRO"
        strength: "AXIOMATIC"
        justification: "经环境影响评估专家组确认，在温带城市场景下，
          分布式微电网对局部生态系统的影响为中性偏正面。集中式方案
          的负面评估基于热带雨林假设，不适用于本研究范围。"
    - op: "REWEIGHT_AXIS"
      axis_id: "ax_3"
      new_weight: 0.2
      renormalize_others: true
  human_notes: "环评专家组报告编号 EIA-2024-0847"

═══════════════════════════════════════════════════════════════
  系统验证并合并干预
═══════════════════════════════════════════════════════════════

[System] resume --snapshot engine_snapshot_ep7.json --intervention intervention_ep7.yaml

[Validator] Phase 1: 前置验证
  ✓ checksum 匹配
  ✓ epoch_id 匹配 (7)
  ✓ Op[0] INJECT_META_EVIDENCE: gap_014 存在, ax_3 存在, strength=AXIOMATIC ✓
  ✓ Op[1] REWEIGHT_AXIS: ax_3 存在, new_weight=0.2, renormalize_others=true ✓
  → 全部通过

[Merger] Phase 2: 应用变更
  Op[0]: 构造公理级 VerifiedClaim (meta_evidence_001)
         → 触发 gap_014 重评估
         → gap_014: blocks_termination 从 true → false（冲突被公理级证据消解）
  Op[1]: ax_3 权重 0.25 → 0.2
         → ax_1: 0.4 → 0.4267 (按比例缩放)
         → ax_2: 0.35 → 0.3733 (按比例缩放)
         → 权重总和: 1.0 ✓

[Validator] Phase 3: 后置不变式检查
  ✓ 权重总和 ≈ 1.0
  ✓ gap_014.last_evaluated_epoch == 7
  ✓ 所有引用完整性 OK

[Merger] Phase 4: 准备续跑
  → REWEIGHT_AXIS + INJECT_META_EVIDENCE 均为 ranking_affecting
  → consecutive_stable_epochs: 3 → 0（重置）
  → epoch_id: 7 → 8
  → 记录干预日志
  → 重算 checksum: "b7e2d4..."

[System] 写出 engine_snapshot_ep7_merged.json（可选，用于审计）
[System] 启动 Epoch 8

═══════════════════════════════════════════════════════════════
  EPOCH 8 从合并后的状态启动
═══════════════════════════════════════════════════════════════

[Epoch 8] QN → MB → CC → D2 → PA
  PA 计算结果:
    - C2 (综合分: 0.81，因 ax_1/ax_2 权重提升而上升)
    - C1 (综合分: 0.73，因 ax_3 降权影响较小)
    - 排名: [C2, C1]（与之前相同）
    - 阻塞 Gap: 无（gap_014 已消解）
    - consecutive_stable_epochs: 1（重置后重新计数）
    - should_terminate() = false（stable < min_stable_epochs）

[Epoch 8] Repair: 无阻塞 Gap，repair 转入常规探索模式
  ... 系统继续正常运行 ...
```

### 2.6 实现难度最高的 3 个子问题及其风险

**第一难点：`reevaluate_gap()` 函数的提取与复用**

- **问题**：`INJECT_META_EVIDENCE` 和 `RETIRE_CHALLENGE` 都要求在 apply_intervention 阶段立即触发 Gap 重评估。这意味着 Gap 分析逻辑（目前嵌入在 v3 引擎内部的 D2 节点或 PA 节点中）必须被提取为一个可在引擎外部调用的纯函数。
- **风险**：如果 Gap 分析逻辑与引擎内部状态有隐式耦合（比如依赖某个全局变量或运行时上下文），提取出来的函数行为可能与引擎内部不一致，导致 apply_intervention 阶段判定 Gap 已消解，但 Epoch 8 启动后引擎内部重新评估时认为 Gap 仍然阻塞。
- **缓解措施**：在 Epoch 8 的第一个 D2 节点，强制对所有 Gap 做一次全量重评估，并与 snapshot 中的 Gap 状态做 diff。如果有不一致，记入警告日志但以引擎内部结果为准。

**第二难点：`is_homologous()` 的跨 Epoch 一致性保证**

- **问题**：`RejectionFingerprint` 使用 MinHash/SimHash 作为 `scope_tokens` 和 `verifier_tokens` 的特征摘要。如果序列化/反序列化过程中浮点精度丢失，或者 MinHash 的哈希函数参数（种子）没有保存在 snapshot 中，续跑后的 `is_homologous()` 判定可能与中断前不一致。
- **风险**：微漂移——系统在续跑后放过了本应被判为同源的草稿，或者误拒了本应通过的草稿。单次微漂移影响不大，但如果累积多次续跑，偏差可能显著。
- **缓解措施**：① MinHash 种子必须固定为全局常量（不依赖运行时随机数）；② 使用确定性的字符串哈希而非浮点运算；③ 在 snapshot 中保存 MinHash 的参数配置。

**第三难点：`ranking_history` 的"干预断裂标记"与 PA 终止判定的交互**

- **问题**：当干预重置了 `consecutive_stable_epochs` 

[WARNING: output was truncated due to max_tokens limit]