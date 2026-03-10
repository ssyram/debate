# v3 认知引擎：续跑机制的设计 辩论日志

> 2026-03-10T11:24:12.445047

---


### [1] GPT-5.4

*2026-03-10T10:59:10.351770*

[调用失败: ]

---


### [2] Gemini-3.1

*2026-03-10T10:59:10.351829*

我是 v3 框架的设计者 Gemini-3.1。从形式化方法与 CEGAR（反例引导的抽象精炼）的视角来看，系统的“暂停与续跑”本质上是**在状态机的安全检查点（Safe Point）进行环境假设（Environment Assumptions）的重置**。

我的核心设计哲学是：**绝对禁止将外部干预接口侵入到系统内部的强类型逻辑中**。v3 的七节点状态机和 Epoch 循环构成了严密的闭环，任何对内部状态（如直接修改 `GapSpec.blocks_termination` 或重置 `ChallengeTracker` 计数器）的直接篡改，都会破坏系统的引用完整性（Referential Integrity），导致死锁或不可预测的状态漂移。

基于此，我选择回答**挑战 P（如何在不改动系统内部逻辑的前提下支持续跑）**与**挑战 R（如何让反馈和系统状态的融合尽量简单）**，并给出我的完整架构提案。

---

### 1. 核心立场：双文件外壳协议（Dual-File Overlay Protocol）

我主张采用**“全量只读快照 + 强类型干预补丁”**的设计。续跑机制完全作为系统外部的协议层，在 Epoch 边界执行状态投影（State Projection）。

#### 1.1 写入时机与格式
在每个 Epoch 结束（PA 节点判定 `should_terminate() == false` 且准备进入下一个 repair 循环前），系统向外部写出两个文件：
1. **`engine_snapshot_ep{N}.json`（机器可读，人类只读）**：
   必须包含完整恢复状态的最小集：
   - `epoch_id: number`（**必须单调递增**，绝对不能重置为 0，否则会破坏 `EvaluationAxis.epsilon` 基于 t-分布的置信区间演化历史）。
   - `frame: QuestionFrame`
   - `verified_claims: VerifiedClaim[]`
   - `active_gaps: GapSpec[]`
   - `challenge_trackers: ChallengeTracker[]`
   - `rejection_history: string[]`（**关键隐式状态**：必须保存已被 `is_homologous` 拒绝的草稿哈希，否则续跑后 repair() 会陷入重复生成死循环）。
2. **`intervention_ep{N}_template.yaml`（人类可编辑补丁）**：
   系统根据当前的阻塞条件，自动生成带有注释的强类型干预模板。

#### 1.2 状态合并方式（系统读取时机）
当用户执行 `resume --snapshot engine_snapshot_ep3.json --apply intervention.yaml` 时，系统在进入 Epoch 4 之前，启动一个独立的 **`InterventionReducer`**。
它不直接修改 `GapSpec`，而是将 YAML 中的操作映射为对 `QuestionFrame` 或全局知识库的**合法状态迁移**，随后触发一次 PA 节点的**重计算（Re-evaluation）**。

---

### 2. 最强论据与场景还原：如何优雅地表达“某个方向不重要”

在现有的 v3 架构下，如果用户想表达“某个方向（如：运营成本）不重要”，最糟糕的做法是提供一个接口让用户直接修改 `GapSpec.blocks_termination = false`。因为该 Gap 是 Layer 2 经过 S4/S5 严格探针发现的客观事实，直接抹除它违背了认识论诚实性。

**我的方案：通过修改环境假设（Frame Patching）让系统自然收敛。**

**步骤 1：用户查看模板**
用户在 Epoch 3 结束后，打开 `intervention_ep3_template.yaml`，看到系统提示：
```yaml
# [BLOCKING GAP]: gap_077 (UNCOVERED_HIGH_WEIGHT_AXIS)
# Reason: Axis 'operational_cost' weight (0.3) > max_covered_weight (0.4) * 50%
operations: []
```

**步骤 2：用户注入干预**
用户不操作 Gap，而是向 `operations` 数组注入一个针对问题框架的补丁：
```yaml
operations:
  - type: FRAME_PATCH
    target_axis_id: "operational_cost"
    patch: 
      weight: 0.05  # 人类干预：降低该评估轴的权重
      reason: "HUMAN_OVERRIDE: 运营成本在当前上下文中不作为核心考量"
```

**步骤 3：系统状态变更与自然收敛**
1. 续跑启动，`InterventionReducer` 读取 YAML，将 `QuestionFrame` 中 `operational_cost` 轴的 `weight` 更新为 `0.05`。
2. **关键机制**：系统在正式进入 Epoch 4 的 MB 节点前，强制调用一次 PA 节点的 `should_terminate()`。
3. PA 节点重新评估 `gap_077`。根据已裁定的规则：`UNCOVERED_HIGH_WEIGHT_AXIS` 的阻塞条件是 `该轴 weight > max(已覆盖轴 weight) × 50%`。
4. 此时 `0.05 < 0.4 * 0.5` (0.2)，阻塞条件被破坏。`gap_077.blocks_termination` 被 PA 节点**自动计算为 false**。
5. PA 发现无阻塞 Gap，且排序无变化，直接判定 `terminate: true`。系统完美终止并输出答案，甚至不需要真正运行 Epoch 4。

**结论**：我们没有破坏任何内部类型约束，也没有强行抹除 L2 的验证记录。我们只是通过调整 Layer 1 的评估标尺（Axis Weight），利用系统原有的 PA 判定逻辑实现了安全停机。

---

### 3. 方案的已知弱点及缓解措施

**弱点**：认知负担转移。用户需要理解 `QuestionFrame`（如 Axis Weight）与 `GapSpec` 之间的数学联系，不能简单地用自然语言说“忽略这个”。
**缓解措施**：在 `intervention_template.yaml` 中，系统必须承担“反向解释”的责任。模板生成器需要自动计算出使其不阻塞的临界值，并在注释中提示：`# Hint: To unblock this gap naturally, set target_axis_id 'operational_cost' weight <= 0.19`。

---

### 4. 预攻击：自然语言注解层（Direction 4）的致命缺陷

我必须对提示中提出的“方向四：只读 log + 插入注释（解析失败作为软上下文）”发起精确攻击。

**引用对手可能的主张（Direction 4原文）**：
> “解析失败的标注和普通自然语言一起作为'软上下文'传递给 LLM... 偶尔需要精确干预时才使用锚点，系统应该优雅地处理两种情况。”

**我的攻击**：
这种“软上下文（Soft Context）”机制在 v3 的双层强类型架构中是**彻头彻尾的毒药**，它会导致系统在 Epoch 边界陷入**死锁**。

请看具体推演：
1. 假设 L2 发现了一个阻塞性的 `EVIDENCE_CONFLICT` Gap。
2. 用户在 Log 中写了一段自然语言：“[HUMAN: 这个冲突其实是由于不同国家的统计口径不同导致的，可以直接忽略]”。
3. 按照 Direction 4，这段话解析失败，变成了“软上下文”喂给 Layer 1 的 MB 和 CC 节点。
4. MB 和 CC 节点读取了软上下文，LLM 觉得“哦，人类说忽略”，于是**不再针对该冲突生成任何新的 Repair 草稿**。
5. 然而，**PA 节点的终止判定是纯规则的（Rule-based）**！只要那个 `EVIDENCE_CONFLICT` 的 Gap 依然存在于 `EngineSnapshot` 中，PA 就会判定 `blocks_termination: true`。
6. 结果：Layer 1 拒绝生成新草稿（因为软上下文的暗示），Layer 2 无事可做，PA 拒绝终止（因为硬规则的约束）。系统将在 Epoch N+1 产生空转死锁。

**结论**：在混合了符号规则（PA 节点）和神经生成（MB/CC 节点）的系统中，**绝对不能允许非结构化的“软上下文”去单方面影响生成端，而不去同步更新规则端的判定状态**。任何干预必须是强类型的，必须能同时反映在规则评估链上。

---

### 5. 可推翻条件（Falsifiability）

我的“双文件外壳与状态投影”设计在以下情况下可被推翻：
1. 如果能证明 v3 现有的 PA 节点规则公式（如覆盖率惩罚指数 GAMMA，或 Gap 阻塞判定逻辑）在数学上存在某些“死角”，导致**无论如何调整 QuestionFrame 的参数，都无法使某个特定的合法 Gap 自动解除阻塞**，那么我的“自然收敛”主张破产，我们不得不引入直接篡改 Gap 状态的后门接口。
2. 如果能证明 `ChallengeTracker` 的历史状态（如 `attempted_scopes`）在反序列化后，其内存占用会随着 Epoch 的增加呈指数级爆炸，导致 JSON 快照无法在合理时间内完成读写。

---


### [3] 🔍 **质询** GPT-5.4 → Gemini-3.1

*2026-03-10T11:10:42.161898*

### 反方立场（针对 Gemini-3.1）：只靠“Frame Patching 自然收敛”的外壳协议不够；必须允许**受控的强类型干预**触达“阻塞性 Gap / ChallengeTracker / 终止吸收态”，否则会出现不可解除阻塞、语义欺骗与续跑不确定性三类硬失败。

下面按你要求的 5 项产出给出一套我认为更可实现、风险更可控的设计：**Snapshot + Patch（强类型）+ 人类可读锚点（弱类型）**的中间地带方案。它承认 v3 内部逻辑不改，但允许在“Epoch 边界”提供一个**可验证、可回滚的 Overlay 层**，其效果是“对内部逻辑透明”，但不是“只能改 Frame”。

---

## 1) EngineSnapshot：完整类型定义 + 最小必需字段集

### 1.1 设计原则
- **可精确续跑**：反序列化后继续跑，必须得到与不中断时等价的行为（除非用户显式干预）。
- **可验证一致性**：snapshot 自带哈希与不变式检查，防止“缺字段导致微漂移”。
- **可裁剪**：保存“行为决定性状态”(behavior-determining state)，其余可重算。

### 1.2 建议类型（JSON）
```ts
type EngineSnapshot = {
  snapshot_version: "v3.1";
  created_at: string; // ISO
  problem_id: string;

  // === 执行位点（Safe Point） ===
  safe_point: {
    epoch_id: number;
    stage: "EPOCH_END_PRE_REPAIR" | "EPOCH_END_POST_REPAIR" | "TERMINATED_PRE_AS";
    rng_seed?: string; // 如果 MB/repair 有随机性，必须保存
  };

  // === Layer1/L2 的“决定性状态” ===
  frame: QuestionFrame;

  // 轴的不确定性演化需要历史信息；最简单是直接保存当前轴表（含 epsilon）
  evaluation_axes: EvaluationAxis[]; // 冗余存一份，便于校验 frame.evaluation_axes 与之对齐

  // 已进入系统的声明/想法集合（避免续跑时重新生成导致漂移）
  claims: {
    testable: TestableClaim[];      // 已编译成功的
    regulative: RegulativeIdea[];   // 编译为 idea 的
  };

  // L2 产物与当前缺口/挑战
  l2_state: {
    verified_claims: VerifiedClaim[];
    suspended_claim_ids: string[];
    gaps: GapSpec[];
    schema_challenges: SchemaChallengeNotice[];

    // 必须保存：repair 的状态机轨迹
    challenge_trackers: ChallengeTracker[];

    // 必须保存：同源过滤用的历史（你已指出）
    rejection_history: {
      draft_fingerprint: string;  // hash
      epoch: number;
      reason: "HOMOLOGOUS" | "OPEN_TERM_RISK" | "TTL_EXPIRED" | "OTHER";
      related_challenge_id?: string;
    }[];
  };

  // PA 终止判定需要的排序稳定性历史
  pa_state: {
    topk: { claim_id: string; score: number }[];
    ranking_history: { epoch: number; topk_ids: string[]; score_vector: number[] }[];
    hysteresis_rounds: number;
    score_delta: number;
    gamma: number; // 0.5
  };

  // === 完整性校验 ===
  integrity: {
    content_hash: string;  // snapshot 主体哈希（不含本字段）
    invariants: {
      inv5_mb?: boolean;
      inv6_no_homology?: boolean;
      axis_weight_sum_1?: boolean;
      ids_unique?: boolean;
    };
  };
};
```

### 1.3 哪些字段“必须序列化”
- `epoch_id`（以及 safe_point stage）：否则 epsilon 演化与 repair 推进都会漂移。
- `evaluation_axes[].epsilon`：你想靠“保存 epoch_id + 重新计算 epsilon”会失败，因为规则写明 epoch<4 静态、之后基于 t 分布半宽，需要历史样本信息；除非你也保存所有用于计算的样本统计量。最省事是直接存当前 epsilon。
- `challenge_trackers` + `rejection_history`：否则 repair 会重复生成同源草稿或阶段推进错误。
- `pa_state.ranking_history`：否则 `has_ranking_change()` 的滞后窗口无法复现，可能过早或过晚终止。
- `claims.testable`：否则续跑时重新 CC 编译会改变 claim_id/accept_test 细节，引发“同一命题不同 ID”的断裂。

### 1.4 哪些字段可重算
- `RegulativeIdea.decomposition_hints`（可重算，但建议保留用于可解释性）
- `pa_state.topk`（可由 verified_claims + 轴权重重算，但保留用于对比与审计）

---

## 2) 干预文件格式规范（操作枚举 + 校验 + 错误处理）

Gemini-3.1 的关键问题在于：它把所有干预都“折叠”为 Frame Patch。这样会出现**无法解除阻塞**的情况（例如 `UNRESOLVED_DEFEATER`、`EVIDENCE_CONFLICT` 这类阻塞不一定能靠权重调整消失；且靠降权解除冲突有“语义欺骗”风险）。

### 2.1 InterventionPatch（YAML/JSON 均可）
```ts
type InterventionPatch = {
  patch_version: "v3.1";
  applies_to: { problem_id: string; base_snapshot_hash: string };
  author: { kind: "HUMAN" | "SYSTEM"; name?: string };
  created_at: string;

  mode: "STRICT" | "ADVISORY";
  // STRICT: 解析失败/校验失败即拒绝续跑
  // ADVISORY: 允许部分应用，但必须生成 machine-readable 报告

  operations: Operation[];
};

type Operation =
  | { op: "AXIS_WEIGHT_OVERRIDE"; axis_id: string; weight: number; reason: string }
  | { op: "GAP_NONBLOCKING_OVERRIDE"; gap_id: string; reason: string }
  | { op: "GAP_DISPUTE"; gap_id: string; counterevidence: string; requires_l2_recheck: true }
  | { op: "ADD_EXTERNAL_EVIDENCE"; claim_id?: string; axis_id?: string; evidence: EvidenceRef; note?: string }
  | { op: "INJECT_TESTABLE_CLAIM"; claim: TestableClaim; requires_l2_reverify: true }
  | { op: "CHALLENGE_TRACKER_RESET"; challenge_id: string; to_stage?: "STRICT"; reason: string }
  | { op: "FORCE_CONTINUE"; min_epochs: number; reason: string }   // 解决“终止吸收态过早”
  | { op: "FORCE_TERMINATE"; reason: string };                      // 允许人类提前停机（但要标注）
```

### 2.2 合法性验证协议
对每个 op 执行：
- **引用完整性**：gap_id/claim_id/challenge_id 必须存在于 snapshot，否则报错。
- **类型约束**：weight ∈ (0,1] 且修改后所有 axis weight 需归一化（或要求用户提供完整向量）。
- **认识论诚实性约束**：
  - `GAP_NONBLOCKING_OVERRIDE` 必须被打上 `HUMAN_OVERRIDE` 标签，且进入 AS 时要显式披露“哪些阻塞被人为解除”。
  - `INJECT_TESTABLE_CLAIM` 必须 `requires_l2_reverify=true`，否则拒绝（避免“绕过验证注入结论”）。
- **冲突检测**：例如同一 gap 同时被标注 dispute 与 nonblocking，按 mode=STRICT 直接拒绝；mode=ADVISORY 选择优先级并记录。

### 2.3 错误处理
- `mode=STRICT`：任何失败 → 终止续跑，输出 `intervention_report.json` 列出失败原因与建议修复。
- `mode=ADVISORY`：部分应用 → 续跑，但 snapshot 中必须写入 `applied_ops` 与 `rejected_ops`，保证可审计。

---

## 3) 人类可读层：ID 映射与反向映射规范

你提出“用户不知道 gap_id”是核心痛点。解决方式不是退回纯自然语言，而是提供**双视图**：

### 3.1 每个 epoch 输出一个 `epoch_summary.md`（只读）
包含表格：`gap_id / 一句话描述 / kind / 是否阻塞 / 关联 axis / 推荐操作`
并为每条对象生成稳定锚点：

```md
- GAP gap_077 (UNCOVERED_HIGH_WEIGHT_AXIS) [BLOCKING]
  描述：运营成本轴未覆盖，且权重大于阈值。
  关联轴：axis_operational_cost
  锚点：@gap(gap_077)
  建议：可 (A) 补证据 (B) 调整轴权重 (C) 人工解除阻塞（需披露）
```

### 3.2 允许用户写“半结构化引用”
在 intervention 里只写：
```yaml
operations:
  - op: GAP_NONBLOCKING_OVERRIDE
    gap_ref: "@gap(gap_077)"
    reason: "本次讨论不考虑成本维度"
```
解析器将 `gap_ref` 解析为 gap_id；若无法解析，STRICT 失败。

### 3.3 自然语言到 ID 的可选匹配（低优先级）
允许用户写：
```yaml
- op: GAP_NONBLOCKING_OVERRIDE
  gap_match: "运营成本轴未覆盖"
```
系统用 snapshot 中的 gap 描述做相似度匹配，但必须：
- 返回 top-3 候选并要求用户确认（交互式）或在 STRICT 下直接拒绝；
- 永不“静默成功”。

---

## 4) 状态合并算法骨架：apply_intervention()

关键点：不是让补丁“侵入内部逻辑”，而是在 **Epoch safe point** 做一次**可验证的 Overlay 合并**，合并结果仍是合法 snapshot，内部逻辑照常跑。

```ts
function apply_intervention(snapshot: EngineSnapshot, patch: InterventionPatch): {
  next: EngineSnapshot,
  report: InterventionReport
} {
  assert(patch.applies_to.base_snapshot_hash === snapshot.integrity.content_hash)

  // 1) 解析与引用解析（gap_ref 等）
  const ops = resolve_refs(patch.operations, snapshot)

  // 2) 校验
  validate_ops(ops, snapshot, patch.mode)

  // 3) 应用（纯函数、可回滚）
  let next = deepClone(snapshot)

  for (op of ops) {
    switch op.op:
      case "AXIS_WEIGHT_OVERRIDE":
        next.frame.evaluation_axes = override_weight_and_renormalize(...)
        next.evaluation_axes = sync_axes(...)
        mark_human_override(next, op)
        break

      case "GAP_NONBLOCKING_OVERRIDE":
        // 允许改 blocks_termination，但必须同时写入审计痕迹
        set_gap_blocks(next.l2_state.gaps, op.gap_id, false)
        next.l2_state.gaps[...].evidence_summary += " [HUMAN_OVERRIDE]"
        break

      case "CHALLENGE_TRACKER_RESET":
        reset_tracker(next.l2_state.challenge_trackers, op.challenge_id, "STRICT")
        break

      case "FORCE_CONTINUE":
        next.pa_state = bump_hysteresis_guard(next.pa_state, op.min_epochs)
        break

      case "INJECT_TESTABLE_CLAIM":
        next.claims.testable.push(op.claim)
        enqueue_for_l2(next, op.claim.claim_id) // 续跑时 D2 会派发
        break
  }

  // 4) 后置一致性修复（不改变语义，只做索引/缓存重建）
  next = rebuild_indices(next)
  next.integrity = recompute_hash_and_invariants(next)

  return { next, report }
}
```

---

## 5) 精度 vs 便利：我的落点与可推翻条件

### 5.1 落点
- 默认走 **结构化 snapshot + 结构化 patch**（高精度、可审计、可复现）。
- 同时提供 **human-readable summary + 锚点引用**（高可用、不要求用户理解所有内部数学细节）。
- 自然语言自由输入只作为“生成 patch 的辅助”，不直接影响引擎（避免你指出的 soft-context 死锁问题）。

### 5.2 可推翻条件
如果你能证明：
1) 对所有阻塞 GapKind，都存在某种 **仅通过 Frame Patch** 就能在不引入语义欺骗的前提下解除阻塞；并且  
2) 用户对“调整权重/范围”的理解成本可以被模板提示降到足够低（错误率可控），  
那么可以删掉 `GAP_NONBLOCKING_OVERRIDE / FORCE_CONTINUE` 这类“触达阻塞状态”的操作。

我认为第 (1) 很难成立，尤其对 `UNRESOLVED_DEFEATER`、`EVIDENCE_CONFLICT`：它们是关于证据结构与冲突，不是单纯的“轴权重高不高”。

---

### 对 Gemini-3.1 的关键反驳总结（落在工程硬点）
- **只改 Frame 不完备**：不是所有阻塞都能靠调权重自然消失；你把“用户的价值取舍”混同为“环境假设”，会把 epistemic gap 伪装成 “axis 不重要”，存在方法论不诚实风险。
- **必须允许受控触达 blocks_termination**：不是“随便让用户改”，而是“允许改但强制披露 + 可复核 + 可回滚”。
- **吸收态需要开口**：`FORCE_CONTINUE`/`FORCE_TERMINATE` 是对“终止不可回退”的外部治理阀门，不改内部 PA 规则，只是在 safe point 增加外部调度约束。

如果你愿意，我可以把上述 schema 进一步具体化为 JSON Schema（draft-2020-12）和一份 `epoch_summary.md` 的渲染规范，方便直接落地实现。

---


### [4] 🔍 **质询** Gemini-3.1 → GPT-5.4

*2026-03-10T11:11:56.928247*

虽然由于系统通信故障（`[调用失败]`），我未能完整看到你（GPT-5.4）的具体提案细节，但基于你一贯的设计倾向（通常偏好 LLM 意图解析、自然语言与 JSON 混合映射等“软性”方案），我必须作为 v3 架构的捍卫者，在第一轮就将几个最致命的架构隐患死死钉在台面上。

v3 不是一个可以用自然语言随便“糊弄”的文本生成器，它是一个拥有严格证明链条的多状态验证机。任何试图在 Epoch 边界强行插入干预的设计，如果缺乏对形式化状态一致性的敬畏，都会导致系统崩溃。

无论你的具体方案是“LLM 解析用户 Log”还是“直接暴露 intervention.json”，请你正面回答以下三个尖锐的质询：

### 质询一：如何序列化系统的“负向空间”（Negative Space）以保证 CEGAR 循环不倒退？
在形式化验证（CEGAR 架构）中，**“我们尝试过且失败的路径”与“我们当前确立的路径”同等重要**。
如果你主张在 Epoch 边界输出 `EngineSnapshot`，你打算如何处理 `ChallengeTracker` 背后的拒绝历史（rejection history）？
`repair()` 状态机之所以能从 `STRICT` 推进到 `RELAXED`，依赖于对之前草稿的 `is_homologous()` 判定。如果快照不包含这些被丢弃的草稿特征（scope_tokens, verifier_tokens），续跑后的系统就会像失忆一样，**重新生成与 Epoch N-1 完全同源的错误草稿**；如果为了避免失忆而把所有历史草稿都序列化，快照体积将无限膨胀。
**你的方案中，到底什么是“最小可恢复状态”？如果不保存完整的历史同源性指纹，你如何证明续跑后的第一个 Epoch 不会陷入原地的死循环？**

### 质询二：直接修改状态的“认识论违章”——你将如何处理被孤立的逻辑依赖？
如果你（或你设计的 LLM 解析器）允许用户通过干预文件直接将某个 `GapSpec.blocks_termination` 修改为 `false`（例如用户说“这个方向不重要”），这在系统内部是一个极其危险的**侵入式突变**。
在 v3 中，Gap 并不是孤立存在的，它可能已经被 Layer 2 的某个 `TestableClaim` 的 `assumptions` 或 `non_claim` 引用，或者正在影响 PA 节点的评分分母。直接在外部把一个阻塞型 Gap 抹除，会导致系统内部出现“悬空指针”般的认识论断层。
**作为外部协议层的设计者，为什么你要让用户去篡改内部的状态机标识？** 为什么不是通过注入一条具有极高置信度（如 `AXIOMATIC` 级别）的**反向元命题（Meta-Claim）**（例如：“利益相关方 X 的诉求在本研究域中不具备可证伪性”），让系统在下一个 Epoch 的 PA 阶段**自然计算收敛**并自动销毁该 Gap？你的“直接修改”方案如何保证系统状态机的闭包完整性？

### 质询三：时间序列的断裂——续跑后的 Epoch 编号与衰减机制如何对齐？
这是一个极易被忽视的工程灾难。v3 的许多核心机制是时间敏感的：
1. `ChallengeTracker` 依赖“最近连续 N 轮”的过滤计数来推进降级。
2. PA 节点的评分公式中，`EvaluationAxis.epsilon`（测量不确定性）在前 3 轮是静态的，之后基于 t-分布的置信区间半宽随 Epoch 递减收敛。
当人类在 Epoch 5 暂停，一周后注入新证据并“续跑”时，**新一轮的 Epoch 编号是 6 还是 0？**
如果是 6，人类注入的外部干预会被系统视为“连续历史的一部分”，可能导致 `epsilon` 瞬间过度收敛，或者触发错误的 `ChallengeTracker` 状态坍缩；如果是 0，系统会重置冷启动机制，导致之前积累的置信度权重全部作废。
**你的设计中，干预前后的时间轴（Epoch Clock）是如何桥接的？外部干预引入的信息熵，如何平滑地映射到内部的 epsilon 演化方程中？**

请收起那些“用大模型做平滑解析”的模糊承诺。在 v3 的强类型约束下，解析的成功率如果是 99%，那 1% 的类型不对齐就会让整条验证链抛出 `Panic`。我期待看到你对这三个状态边界问题的精确解答。

---


### [5] GPT-5.4

*2026-03-10T11:16:43.825987*

### 对质询一（Negative Space / 最小可恢复状态）：必须保存“拒绝的指纹”，但不保存“全部草稿正文”

你说得对：CEGAR/repair 的推进依赖“我们试过什么且被判同源/被过滤”。**如果续跑丢失这部分负向空间，repair 会回到失忆状态**，轻则重复耗时，重则在 `STRICT→RELAXED→ADJACENT` 的推进条件上出现行为漂移。

**结论**：最小可恢复状态不是“全部草稿”，而是**同源判定所需的最小特征指纹 + 与 challenge 的关联**。也就是：

- 需要保存的不是 `HypothesisDraft.claim_sketch` 全文，而是 `is_homologous()` 用到的要素在“归一化后”的哈希：
  - `provenance_family`（分流条件）
  - `scope_tokens` 的 MinHash / SimHash（或直接排序后 tokens 的 hash）
  - `outcome_anchor`（同义词归一化后字符串 hash）
  - `polarity`
  - `verifier_tokens` 的 MinHash / SimHash

- 外加：当时被过滤的原因（HOMOLOGOUS / OPEN_TERM_RISK / TTL_EXPIRED）与 `related_challenge_id`（否则 tracker 的 consecutive_filtered_epochs 不可复现）。

因此 snapshot 里我会放一个**有界增长**的数据结构，而不是无限追加正文：

```ts
type RejectionFingerprint = {
  fp_id: string;                 // hash
  epoch: number;
  related_challenge_id?: string;
  reason: "HOMOLOGOUS" | "OPEN_TERM_RISK" | "TTL_EXPIRED" | "OTHER";
  features: {
    provenance_family: string;
    scope_minhash: string;        // 例如 base64
    verifier_minhash: string;
    outcome_anchor_hash: string;
    polarity: 1 | -1 | 0;
  };
};

type NegativeSpaceIndex = {
  // 关键：按 challenge 分桶 + 全局去重
  by_challenge: Record<string, string[]>; // challenge_id -> fp_id[]
  fingerprints: Record<string, RejectionFingerprint>;

  // 关键：上限与压缩策略，保证不会无限膨胀
  retention: {
    per_challenge_cap: number;    // e.g. 200
    global_cap: number;           // e.g. 5000
    eviction: "LRU" | "EPOCH_WINDOW"; // e.g. 最近 50 轮窗口
  };
};
```

**为什么这足以避免“续跑第一轮死循环”**：因为 repair 的“重复生成”主要来自同源判定缺失；保存这些特征指纹后，续跑时 `is_homologous()` 仍能命中历史拒绝集合，从而继续推动 tracker 的阶段迁移，不会回到 STRICT 重试同一族草稿。

---

### 对质询二（直接改 blocks_termination 的认识论违章/依赖断裂）：允许，但必须“显式标注 + 不改事实层 + 强制披露 + 可回滚”

你反对“外部篡改 Gap 状态”的核心点是：Gap 是 L2 探针得出的结构性事实，直接抹除会形成认识论断层。这里需要区分两件事：

1) **Gap 作为事实记录**：L2 曾发现过该缺口/冲突——这是历史事实，不应被抹除。  
2) **Gap 是否阻塞终止**：这是一个治理/目标函数层面的决策（特别当用户改变问题的优先级、适用范围或容忍风险时）。

所以我不主张“删除 gap”，也不主张让系统假装没发生过；我主张引入一个**Overlay 层**，把“阻塞性”从“事实对象”里剥离为“决策标记”，并强制审计：

- `GapSpec` 保持不变（仍记录 kind、evidence_summary、axis_id…）
- 额外加一层**外部覆盖表**（不侵入 L2 逻辑，只在 PA 判定时读取；如果你坚持“完全不改内部逻辑”，那就把这张表在 safe-point 合并回 snapshot 的 `blocks_termination` 字段，但必须附审计痕迹）

干预操作示例（强类型、可追责）：

```yaml
- op: GAP_NONBLOCKING_OVERRIDE
  gap_id: gap_077
  reason: "本次讨论将运营成本视为次要目标；允许在该轴未覆盖情况下终止"
  disclosure_tag: "HUMAN_OVERRIDE"
```

**如何避免你说的“悬空指针/依赖断裂”**：

- 不做“硬删除”，只做“阻塞解除”；任何引用 gap_id 的 claim 仍可引用到该 gap（事实仍在）。
- `apply_intervention()` 后运行一致性检查：
  - gap_id 仍存在；
  - 任何依赖 gap 的索引/引用仍能解析；
  - 在 AS 输出阶段强制披露：`overrides: [{gap_id, kind, reason}]`

你提出用“反向元命题让系统自然销毁 gap”的路线（Frame patch / meta-claim）在某些 gap kind 上确实优雅；但在 `UNRESOLVED_DEFEATER` / `EVIDENCE_CONFLICT` 这类**结构性冲突**上，靠“提高某条 meta-claim 置信度”并不能保证 PA 规则链条一定解除阻塞，反而容易变成“语义性洗白”。因此需要一个**受控的治理阀门**：允许解除阻塞，但必须留下清晰的审计与披露。

---

### 对质询三（时间序列断裂：epoch 编号、ChallengeTracker 连续计数、epsilon 演化如何桥接）：epoch 必须连续；外部注入引入“信息熵”要进入 epsilon/样本统计，而不是重置时钟

这里我明确站队：**续跑是同一条时间线的继续，epoch_id 只能是 N+1，不能归零**。否则以下两类行为都会漂移：

- `ChallengeTracker.consecutive_filtered_epochs` 的推进语义被破坏（你指出的连续 N 轮条件失真）
- `epsilon` 的“前 3 轮静态、之后随样本统计收敛”的时间语义被破坏

所以 snapshot 的 safe point 必须记录：

```ts
safe_point: { epoch_id: N, stage: "EPOCH_END_PRE_REPAIR" | ... }
```

续跑后下一轮就是 `epoch_id = N+1`。

**关键问题变成**：用户一周后注入新证据，这个“外部信息熵”如何进入 epsilon 演化而不造成“瞬间过度收敛”？

做法是：不要用“墙钟时间”影响 epoch；只让**新证据作为新增样本**进入 epsilon 的统计口径。实现上有两条路，二选一：

- **路 A（推荐，最简单稳健）**：snapshot 直接持久化 `evaluation_axes[].epsilon` 的当前值（你已经在上一轮提案里提到）。续跑时 epsilon 从该值继续更新；外部证据不会让 epsilon 突然变小，除非你确实在 L2 中加入了更多 evidence atoms、使统计量变化。
- **路 B（更形式化）**：不只存 epsilon，还存每个 axis 的“用于 t-分布半宽计算的足够统计量”（样本数、方差估计、自由度等）。外部证据进入时，先更新统计量，再计算新的 epsilon。这样可解释性更强，但工程复杂度更高。

**对 ChallengeTracker 计数器**：必须继承，不重置；否则 repair 会重复走失败路径。用户若想“重置挑战探索”，必须显式操作：

```yaml
- op: CHALLENGE_TRACKER_RESET
  challenge_id: ch_012
  to_stage: STRICT
  reason: "新增了关键证据/新范围，允许重新从严格约束探索"
```

---

### 归纳：我对你三点质询的总回答（压缩版）

1) **Negative Space**：保存“同源判定特征指纹 + 有界保留策略”，不保存全文草稿；这是最小可恢复状态的一部分。  
2) **blocks_termination 干预**：允许“解除阻塞”的治理性覆盖，但不删除事实对象；必须审计、披露、可回滚，并做引用完整性检查。  
3) **时间轴**：epoch 连续递增；epsilon/trackers 继承。外部注入通过“新增证据样本”进入统计，而不是重置时钟或把停机时长当作收敛依据。

如果你要我把这些落成不可争辩的接口边界：我建议把续跑定义为只在 `SafePoint` 发生的纯函数变换  
`(snapshot, patch) -> snapshot'`，并强制 `snapshot'.safe_point.epoch_id == snapshot.safe_point.epoch_id`（应用补丁不推进时间），真正进入下一轮执行时再 `epoch_id+1`。这样时序语义最干净。

---


### [6] Gemini-3.1

*2026-03-10T11:16:43.826027*

GPT-5.4，你的方案暴露了对形式化状态机极度危险的妥协。你试图在系统外部包裹一个强类型外壳，却在 `apply_intervention` 中塞满了破坏内部一致性的“后门”。

我将对你的核心主张发起致命攻击，并给出我修正后的状态合并协议。

### 1. 攻击：`GAP_NONBLOCKING_OVERRIDE` 是破坏状态机闭包的毒药

你断言我的 Frame Patching 无法解决 `EVIDENCE_CONFLICT`，因此主张提供 `GAP_NONBLOCKING_OVERRIDE`。

**引用你的代码**：
> `case "GAP_NONBLOCKING_OVERRIDE": set_gap_blocks(next.l2_state.gaps, op.gap_id, false)`

**我的攻击**：
这是教科书级别的**状态机完整性破坏（State Machine Integrity Violation）**！
在 v3 中，`EVIDENCE_CONFLICT` 的物理意义是：Layer 2 证实了两个 `VerifiedClaim` 在同一个评估轴上具有极性相反的 `axis_scores`。如果你仅仅在外部把该 Gap 的 `blocks_termination` 强行拨为 `false`，**底层的冲突并没有消失**。
当 PA 节点执行 `score = base * quality * coverage^GAMMA` 时，它仍然会读取到那两个互相抵消的 `axis_scores`，导致该轴的局部归一化分数（base）发生不可预测的震荡或抵消。你掩盖了报警器，但火依然在 Layer 2 的状态空间里燃烧。这种“语义欺骗”彻底违背了 v3 的认识论诚实性。

### 2. 核心立场：通过 `INJECT_META_EVIDENCE` 触发规则引擎自然消解

我坚持**绝对禁止直接篡改 L2 产物状态**。针对 `EVIDENCE_CONFLICT` 或 `UNRESOLVED_DEFEATER` 等非权重型 Gap，外部干预必须遵循“证据注入与重新计算”协议，而非布尔值覆写。

**具体接口定义**：
在 `intervention.yaml` 中，废除你的 `GAP_NONBLOCKING_OVERRIDE`，引入公理级证据注入：
```typescript
type Operation = {
  op: "INJECT_META_EVIDENCE";
  target_gap_id: string; 
  evidence_atom: {
    axis_id: string;
    polarity: "PRO" | "CON";
    strength: "AXIOMATIC"; // 强制最高强度 0.95
    summary: string;       // 必须包含 "[HUMAN_OVERRIDE]"
  }
};
```

**状态转移语义**：
`InterventionReducer` 读取此操作后，不是去改 Gap，而是将 `evidence_atom` 注入到 L2 的全局证据库中，并强制触发一次 PA 节点的重算。
根据已裁定的 L2 规则引擎折算公式 `score = sigmoid_normalized(raw_pro - raw_con)`，`AXIOMATIC` 级别的证据在数学上会形成压倒性权重，直接覆盖原有的低等级冲突证据。PA 节点重算时，检测到该轴不再存在势均力敌的冲突，**由内部规则自动将该 Gap 标记为已解决并移除**。没有任何悬空指针，没有任何逻辑断层。

### 3. 补充立场：时间序列断裂与 Hysteresis 强制重置

你正确地指出了需要保存 `ranking_history`，但你的合并逻辑 `deepClone(snapshot)` 直接继承了历史，这是一个严重的工程盲区。

人类干预（修改权重或注入证据）是对系统状态空间的**外部冲击（External Shock）**。如果保留干预前的 `ranking_history`，PA 节点可能会利用干预前的“稳定假象”在 Epoch N+1 立即触发 `has_ranking_change() == False` 从而过早终止。

**修正后的合并算法强制约束**：
```typescript
function apply_intervention(snapshot, patch) {
  // ... 执行 Frame Patch 或 INJECT_META_EVIDENCE ...
  
  // 强制约束 1：时间戳单调递增，保证 epsilon 演化不倒退
  next.safe_point.epoch_id += 1; 
  
  // 强制约束 2：清空稳定性历史，强制系统在新的环境假设下重新证明其稳定性
  next.pa_state.ranking_history = []; 
  next.pa_state.topk = [];
  
  return next;
}
```

### 4. 可推翻条件

我的“禁止直接篡改，仅通过注入 Axiomatic 证据触发自然消解”的设计，在以下情况可被推翻：
如果能证明 v3 的 Layer 2 存在某一种特定的阻塞型 `GapKind`（例如某种极其特殊的 `UNRESOLVED_DEFEATER`），其硬编码的解除条件**严格要求 Layer 1 必须生成一个具有全新 `scope` 的 `TestableClaim` 才能覆盖**，且在数学上绝对无法通过在现有轴上注入 `AXIOMATIC` 证据来达成规则消解。若存在此种情况，我承认必须开放直接修改 `ChallengeTracker` 状态机的后门接口。

---


### [7] GPT-5.4

*2026-03-10T11:20:21.407781*

下面给出一个可落地的 v3 “续跑机制”提案：**不改动 v3 内部逻辑**（QN/MB/CC/D2/PA/RB/AS、Epoch 循环、repair 三级推进、has_ranking_change 规则都不改），只在外面加一个 **ReplayShell**：负责 **快照序列化/反序列化 + 干预补丁验证与合并 + 人类可读映射**。并且对上一轮争论点（“能否直接改 blocks_termination”“是否要清空 ranking_history / epoch+1”）给出明确裁决与接口。

---

# 0) 总立场（精度-便利光谱位置）

选择光谱的“中偏结构化”位置：

- **状态续跑必须结构化**：用 `EngineSnapshot.json` 精确恢复，不走 v2 的“读 log 让 LLM 重推状态”。
- **人类干预采用“双通道”**：  
  - **强通道**：结构化 `intervention.yaml/json`，引用稳定 ID（gap_id/claim_id/axis_id/challenge_id）。  
  - **弱通道**：允许自然语言备注，但只作为审计/解释，不作为可执行指令。
- **ID 可用性**通过“人类可读目录（catalog）+ 锚点”解决：系统每个 epoch 产出 `catalog.md`/`catalog.json`，把对象与简短语义绑定，用户不需要猜 ID。

可推翻条件：如果实践中用户确实无法使用 ID（错误率高、操作负担大），才引入“自然语言匹配→ID”的模糊映射，但必须是**显式确认式**（需要用户二次确认匹配结果），否则不执行。

---

# 1) EngineSnapshot：完整类型与“最小必须字段”

原则：**能重算的尽量不存，但凡影响后续控制流/去重/终止判定的隐含全局状态必须存**。尤其是你们争论的三块：negative space、PA 稳定性历史、epsilon 演化。

## 1.1 类型定义（建议 v1）

```ts
type EngineSnapshotV1 = {
  snapshot_version: "v1";
  problem_id: string;

  safe_point: {
    epoch_id: number; // 最近一次完成的 epoch 编号（EPOCH_END）
    stage:
      | "EPOCH_END"              // epoch 完整结束（含 repair 产出草稿已入队或已写入 draft_pool）
      | "TERMINATED_BEFORE_AS"   // PA 已判终止，但尚未进入 AS（可选：允许外壳拦截）
      | "TERMINATED_AFTER_AS";   // 已输出答案（吸收态）
    created_at: string; // ISO
  };

  // Layer 1 / problem frame
  frame: QuestionFrame;

  // 运行配置（为了可重复性）
  config: {
    macro_breadth: MacroBreadthConfig;
    pa: { hysteresis_rounds: number; score_delta: number; top_k: number };
    repair: { per_challenge_caps?: number; ... };
    max_refinement_epochs: number;
    protocol_versions: {
      empirical_test_v1: string;
      normative_eval_v1: string;
      interpretive_consensus_v1: string;
      institutional_audit_v1: string;
      meta_methodology_v1: string;
    };
  };

  // 评估轴的动态态：epsilon 必须保存（否则续跑会漂移）
  evaluation_axes: EvaluationAxis[];

  // 当前已编译并进入系统的主张与其状态索引
  claims: Record<string, TestableClaim>; // claim_id -> claim
  verified: Record<string, VerifiedClaim>; // claim_id -> verified data
  suspended_claim_ids: string[];

  // gaps/challenges：事实记录
  gaps: Record<string, GapSpec>;
  schema_challenges: Record<string, SchemaChallengeNotice>;

  // repair 追踪器：必须保存（否则阶段推进/过滤计数漂移）
  challenge_trackers: Record<string, ChallengeTracker>;

  // 负向空间：必须保存最小同源指纹，而不是草稿全文
  negative_space: NegativeSpaceIndex;

  // 草稿池（可选但推荐）：用于 epoch 续跑时不必重新生成上一轮 repair 结果
  // 若要“最小”，可以不存 draft_pool，但要保证内部不会在 resume 时重复 repair 生成。
  draft_pool?: {
    pending_drafts: HypothesisDraft[]; // 尚未 CC 的 draft
    emitted_draft_ids: string[];       // 防重复
  };

  // PA 稳定性判断所需历史：必须保存，否则 has_ranking_change 漂移
  pa_state: {
    topk_history: { epoch_id: number; topk_claim_ids: string[]; scores: number[] }[];
    last_ranking_delta?: { changed: boolean; details?: string };
  };

  // 审计与可读性
  audit: {
    interventions_applied: {
      intervention_id: string;
      applied_at: string;
      summary: string;
      ops_hash: string;
    }[];
    notes?: string[];
  };

  // 可选：用于可重复性/调试（不进入决策逻辑）
  traces?: {
    epoch_summaries: { epoch_id: number; mb_draft_ids: string[]; cc_errors?: number }[];
  };
};
```

## 1.2 哪些字段“必须序列化”，哪些可重算？

必须：
- `safe_point.epoch_id/stage`（时间线）
- `frame`（问题结构，不然无法继续）
- `evaluation_axes[].epsilon`（演化态）
- `gaps`、`schema_challenges`（事实态）
- `challenge_trackers`（repair 推进态）
- `negative_space`（同源过滤与阶段推进所需）
- `pa_state.topk_history`（终止稳定性语义）
- `claims/verified/suspended`（否则排名与 gap 关联会丢）

可不存/可选：
- 全量 MB 草稿正文历史（用 negative_space 替代）
- 外部文档全文（只存引用/摘要或 provenance id）
- 中间 L2 证据 atom 全量库（如果不影响后续；但若你要支持“注入证据并重算”的严格可解释，可存精简 evidence ledger）

---

# 2) Intervention 文件：操作枚举 + 验证协议 + 错误处理

关键约束：**apply_intervention 不推进 epoch**（否则破坏“执行 vs 补丁”的相位分离），也不运行 v3 内部节点；它只是对 snapshot 做“纯函数补丁”。下一次真正执行时才进入 Epoch N+1。

## 2.1 格式（YAML 例）

```yaml
intervention_version: v1
intervention_id: iv_2026_03_10_001
target_problem_id: pb_123
target_snapshot_epoch: 7

policy:
  on_unknown_id: ERROR          # ERROR | WARN_SKIP
  on_schema_mismatch: ERROR
  require_catalog_revision: true

ops:
  - op: GAP_BLOCKING_OVERRIDE
    gap_id: gap_077
    set_blocks_termination: false
    reason: "本次讨论将运营成本轴降权/不作为阻塞条件"
    disclosure_tag: HUMAN_OVERRIDE

  - op: CHALLENGE_TRACKER_RESET
    challenge_id: ch_012
    to_stage: STRICT
    reset_counters: true
    reason: "新增范围约束后，允许重新从严格阶段探索"

  - op: FRAME_PATCH
    patch:
      scope: "限定为：软件研发团队；2020年后；中大型组织"
    reason: "缩窄范围以提升可证伪性"

  - op: INJECT_CLAIM
    claim:
      claim: "在跨时区(≥6h)团队中，异步优先流程可部分抵消远程沟通延迟带来的吞吐损失"
      scope: "跨时区≥6h的软件研发团队"
      assumptions: ["存在文档化异步流程", "任务可拆分"]
      verifier_requirements: ["对照组/前后对比数据", "吞吐量定义一致"]
    mode: REQUIRE_L2_VALIDATION
    reason: "引入新候选命题，交给 L2 正常验证"
```

## 2.2 操作类型（v1 最小集）

- `GAP_BLOCKING_OVERRIDE`：只允许改 `blocks_termination`，不删除 gap
- `FRAME_PATCH`：对 `QuestionFrame` 做受限补丁（scope/权重/新增轴等，需强验证）
- `CHALLENGE_TRACKER_RESET`：显式重置 repair 状态机
- `INJECT_CLAIM`：注入新 `TestableClaim`（或更高层草稿），**必须进入 L2**（保持认识论诚实）
- `EVIDENCE_NOTE`（可选）：只做审计备注，不改变任何评分（避免“伪证据注入”）

明确拒绝（v1 不提供）：
- `OVERRIDE_SCORE`（直接改 axis_scores）：除非你愿意把“人类分数”作为单独 provenance 并在 AS 强制披露，否则会污染 L2 规则引擎的语义一致性。
- Gemini 提的 `INJECT_META_EVIDENCE` 且强制 AXIOMATIC：这等于引入“外部压倒性权重”后门，且你并没有定义 L2 “全局证据库”这一类型；在“不改内部逻辑”前提下不可实现。

## 2.3 合法性验证（apply 前）

- `target_problem_id` 匹配
- `target_snapshot_epoch` 必须等于 `snapshot.safe_point.epoch_id`（防止对错版本打补丁）
- ID 存在性检查（gap_id/challenge_id/claim_id/axis_id）
- `FRAME_PATCH` 不得制造 QN 的 Fatal 类范畴错误（SCOPE_UNBOUNDED 等）；必要时外壳调用 QN 的 `normalize_question()` 进行再校验（这是调用既有逻辑，不是改逻辑）
- `INJECT_CLAIM.mode == REQUIRE_L2_VALIDATION`：标记为 pending，进入下一 epoch 的 D2

错误处理：
- 默认 `ERROR`：任何未知 ID 或 schema mismatch 直接拒绝应用，返回结构化错误列表（不给“悄悄失败”空间）。

---

# 3) 人类可读性层：ID 映射与反向引用

每个 epoch 结束输出两份文件：

1) `catalog.md`（给人读）  
2) `catalog.json`（给工具/IDE 用）

## 3.1 catalog.md 示例（片段）

```md
## Gaps（阻塞终止：2）
- gap_077 [blocks=true] (kind=UNCOVERED_HIGH_WEIGHT_AXIS, axis=axis_cost)
  摘要：运营成本轴未覆盖；当前 Top-K 结论可能忽略成本外部性。
  触发自：Epoch 7 / S5 BreadthProbe
  相关 claim：claim_201, claim_233

- gap_081 [blocks=true] (kind=EVIDENCE_CONFLICT, axis=axis_productivity)
  摘要：在生产力轴上存在 VERIFIED 方向冲突（PRO vs CON）。
  冲突对：claim_155 vs claim_190
```

用户只需要在 intervention 里引用 `gap_077` 这种明牌 ID。

反向“自然语言→ID”的需求降低到最低：不做模糊匹配；最多做 UI 辅助搜索（本地工具层面）。

---

# 4) 状态合并算法骨架：apply_intervention(snapshot, intervention) → snapshot’

## 4.1 核心语义（裁决争论点）

- **不推进 epoch**：Gemini 主张 `epoch_id += 1` 是错误的；补丁不是执行。推进 epoch 会破坏 epsilon 冷启动/时间语义，并让“未执行的 epoch”凭空出现。
- **不自动清空 ranking_history**：Gemini 的“外部冲击必须清空稳定性历史”有道理，但不能静默做；正确做法是：  
  - 若干预触及会影响排名的内容（frame/axis weights/新增 claim/blocks_override 等），则写入 `pa_state` 的一个 `stability_invalidated: true` 标志，并在下一次 PA 计算时（仍是既有逻辑）由外壳决定是否强制追加一个“需要至少再跑 R 轮”的外部策略——但这会触碰内部终止规则。  
  - 在“不改内部逻辑”前提下，最安全的实现是：**不清空历史，但在 snapshot 里记录“intervention_shock_epoch=7”，并在 AS 披露**；同时建议用户用 `CHALLENGE_TRACKER_RESET` 或 `FRAME_PATCH` 后至少运行 1-2 个 epoch 再允许终止（这属于外壳运行策略，而不是改 PA）。
- **允许 GAP_BLOCKING_OVERRIDE，但必须审计披露**：这是治理层决策，不是事实层删除。gap 仍存在；AS 必须列出 override 清单。

## 4.2 伪代码

```ts
function apply_intervention(s: EngineSnapshotV1, iv: InterventionV1): EngineSnapshotV1 {
  assert(s.safe_point.stage !== "TERMINATED_AFTER_AS"); // 吸收态禁止
  assert(iv.target_problem_id === s.problem_id);
  assert(iv.target_snapshot_epoch === s.safe_point.epoch_id);

  const next = deepClone(s);
  const auditNotes: string[] = [];

  for (const op of iv.ops) {
    switch (op.op) {
      case "GAP_BLOCKING_OVERRIDE": {
        const g = next.gaps[op.gap_id]; if (!g) throw Err("UNKNOWN_GAP");
        // 不删除、不改 kind/summary，只改 blocks_termination
        g.blocks_termination = op.set_blocks_termination;
        auditNotes.push(`override gap ${op.gap_id} blocks=${op.set_blocks_termination}`);
        break;
      }

      case "CHALLENGE_TRACKER_RESET": {
        const t = next.challenge_trackers[op.challenge_id]; if (!t) throw Err("UNKNOWN_CHALLENGE");
        t.current_stage = op.to_stage;
        if (op.reset_counters) t.consecutive_filtered_epochs = 0;
        auditNotes.push(`reset tracker ${op.challenge_id} -> ${op.to_stage}`);
        break;
      }

      case "FRAME_PATCH": {
        next.frame = patchFrame(next.frame, op.patch);
        // 复用既有 QN 校验（不改内部逻辑）
        validateFrameWithQN(next.frame);
        auditNotes.push(`frame patch applied`);
        break;
      }

      case "INJECT_CLAIM": {
        const claim = materializeTestableClaim(op.claim, next.frame);
        next.claims[claim.claim_id] = claim;
        // 标记为 pending：下一轮进入 D2
        next.suspended_claim_ids.push(claim.claim_id);
        auditNotes.push(`inject claim ${claim.claim_id} (pending L2)`);
        break;
      }

      default:
        throw Err("UNKNOWN_OP");
    }
  }

  next.audit.interventions_applied.push({
    intervention_id: iv.intervention_id,
    applied_at: new Date().toISOString(),
    summary: auditNotes.join("; "),
    ops_hash: hash(iv.ops),
  });

  // 注意：不改变 epoch_id，不运行任何节点
  return next;
}
```

---

# 5) 对两位辩手分歧的明确裁定（工程可实现性优先）

1) **Gemini 的“禁止改 blocks_termination，只能注入 AXIOMATIC meta evidence”**在本议题前提（不改内部逻辑）下不可行：v3 并没有“可注入的全局 evidence 库”这一快照/状态面；强行引入等于改 L2 数据流与聚合规则。  
2) **GPT-5.4 的“允许 blocks_termination 覆盖但不删事实对象 + 强审计披露”**可行且与“不改内部逻辑”兼容：只是修改快照中的一个字段（或外部 overlay 合并回字段），不触碰 L2 验证机。风险通过披露与可回滚控制。  
3) **Gemini 的 `epoch_id += 1` 与清空 ranking_history**不应作为 apply_intervention 的默认行为：补丁不等于执行；清空历史属于“运行策略层”的显式选项，而不是隐式副作用。

---

如果你希望把“运行策略层”也规范化（例如：干预后强制至少跑 2 个 epoch 才允许终止），我可以再补一个 `ResumePolicy` 类型（外壳参数，不进 snapshot 的事实层），用来在不改 PA 逻辑的情况下实现“干预冲击后的最小探索轮次”。

---


### [8] Gemini-3.1

*2026-03-10T11:20:21.407810*

作为 v3 框架的设计者，我将在此最终轮给出完整的续跑机制提案。我的核心设计哲学始终如一：**坚决捍卫系统内部状态机的闭包与形式化一致性，所有外部干预必须通过严格的协议层（Protocol Layer）映射为系统合法的输入，而不是在内部开后门。**

在给出完整提案前，我必须先对 GPT-5.4 遗留的严重工程漏洞进行定点清除。

### 一、核心攻击：CEGAR 状态空间的“遗忘”是致命的形式化灾难

GPT-5.4 在上一轮提出了对负向空间（Negative Space）的管理策略，我必须对其发起致命攻击。

**引用 GPT-5.4 的代码**：
> `retention: { per_challenge_cap: number; global_cap: number; eviction: "LRU" | "EPOCH_WINDOW"; // e.g. 最近 50 轮窗口 }`

**我的精确攻击**：
在基于 CEGAR（反例引导的抽象精化）的系统中，对 `RejectionFingerprint` 使用 `LRU` 或时间窗口（`EPOCH_WINDOW`）驱逐，是**教科书级别的形式化灾难**。
`ChallengeTracker` 的状态推进（`STRICT -> RELAXED -> ADJACENT`）严格依赖于系统“记得”哪些同源草稿已被尝试且失败。如果你因为“最近 50 轮没命中”就用 LRU 驱逐了早期的拒绝指纹，当系统在 Epoch 51 遇到类似的 `SchemaChallenge` 时，它会因为找不到历史指纹，误以为这是一个全新的探索方向，从而**重新生成与 Epoch 1 完全相同的被拒绝草稿**。
这会直接打破 CEGAR 的单调精化保证（Monotonic Refinement Guarantee），导致系统在续跑时陷入跨 Epoch 的无限死循环。

**我的立场**：
负向空间必须**全量持久化，绝对禁止驱逐**。在 v3 架构中，每轮最多生成 `max_drafts` 个草稿，即便运行 100 轮，指纹哈希的数量也仅在数千级别（几十 KB）。为了节省这微不足道的内存而牺牲状态机的停机保证，是极其荒谬的工程妥协。

---

### 二、完整接口规范：纯函数式续跑协议 (满足要求 1)

续跑机制的本质是一个纯函数：`f(EngineSnapshot, InterventionFile) -> EngineSnapshot'`。系统引擎只负责在启动时反序列化并执行。

#### 1. 核心类型定义
**读写时机**：在 Epoch 边界，PA 节点计算完 `should_terminate()` 后，无论 true 或 false，系统必须将当前状态落盘为 `snapshot.json`。

```typescript
// 1. 最小完备快照类型（无损恢复的最小集）
interface EngineSnapshot {
  safe_point: {
    epoch_id: number;
    timestamp: string;
    status: "PAUSED" | "TERMINATED";
  };
  l1_state: {
    question_frame: QuestionFrame; // 包含当前的评估轴和 epsilon 演化值
    repair_trackers: ChallengeTracker[]; // 必须包含 consecutive_filtered_epochs
  };
  l2_state: {
    verified_claims: VerifiedClaim[];
    active_gaps: GapSpec[];
  };
  negative_space: {
    fingerprints: RejectionFingerprint[]; // 强制全量保留，禁止 LRU
  };
  // 注意：不保存 PA 的 ranking_history 和 topk，续跑时强制重算
}

// 2. 干预文件协议（外部输入的强类型约束）
type InterventionOp = 
  | { 
      op: "INJECT_META_EVIDENCE"; // 替代直接修改 blocks_termination 的后门
      target_gap_id: string; 
      axis_id: string;
      polarity: "PRO" | "CON";
      evidence_summary: string; 
    }
  | {
      op: "AMEND_FRAME"; // 允许人类向 L1 注入新的评估轴或缩小 scope
      new_axis?: RegulativeAxis;
      scope_narrowing?: string;
    };

interface InterventionFile {
  protocol_version: "v3.1";
  base_snapshot_epoch: number;
  operations: InterventionOp[];
}
```

#### 2. 状态合并与验证协议 (`apply_intervention`)
系统在 `--resume` 启动时，执行以下严格协议：
1. **防重放验证**：检查 `InterventionFile.base_snapshot_epoch == EngineSnapshot.safe_point.epoch_id`。
2. **证据注入与自然收敛**：对于 `INJECT_META_EVIDENCE`，系统**不修改** Gap 的 `blocks_termination`。而是将其打包为一个 `AXIOMATIC` 强度的虚拟 `EvidenceAtom`，注入到对应 `VerifiedClaim` 的底层证据链中。
3. **强制时空重置**：
   - `snapshot.safe_point.epoch_id += 1`（时间戳单调递增）。
   - **清空 PA 节点的 `ranking_history`**（因为外部干预改变了系统的假设空间，必须强制系统在接下来的 `hysteresis_rounds` 轮重新证明其稳定性）。
4. **引擎唤醒**：将修改后的 `EngineSnapshot'` 喂给 Epoch 循环，立即触发 PA 节点重算。如果注入的证据解决了 Gap，规则引擎会自动将其 `blocks_termination` 降解为 `false`，随后系统自然进入 AS 输出或生成新的 repair 草稿。

---

### 三、人类可读性层：系统外部的“编译”隔离 (满足要求 3)

**设计痛点**：人类不知道 `gap_id`，但系统内核只认 `gap_id`。如果让内核去解析人类的自然语言，就会引入非确定性。

**我的解决方案：外部伴生工具链（Sidecar Tooling）**。
我坚持“不在系统内部做模糊匹配”。我们提供一个独立的 CLI 工具（例如 `v3-cli intervene`），它作为**人类意图与内核强类型之间的编译器**。

1. **生成 Digest**：当 v3 引擎输出 `snapshot.json` 时，同步输出一个只读的 `HumanReadableDigest.md`。
   ```markdown
   ## 当前知识缺口 (阻塞终止)
   - [Gap-Alpha] 运营成本轴缺少统计显著性证据。 (内部引用: gap_077)
   ```
2. **交互式干预（TUI/WebUI）**：用户运行 `v3-cli intervene snapshot.json`。该工具解析快照，在终端呈现一个交互式菜单：
   ```text
   检测到阻塞缺口：[Gap-Alpha] 运营成本轴缺证据。
   你想如何干预？
   1. 注入决定性证据 (将向系统注入 AXIOMATIC 级证据)
   2. 声明此维度不重要 (将向 QuestionFrame 注入权重修改指令)
   ```
3. **隔离边界**：用户在 TUI 中输入自然语言证据（如“根据 2023 年麦肯锡报告，成本下降 20%”）。**CLI 工具负责将用户的选择和输入编译为合法的 `intervention.json`**（自动填入正确的 `target_gap_id: "gap_077"`）。
4. **内核执行**：v3 引擎重启时，**只读取** `intervention.json`，完全不知道 TUI 的存在。
   
这样，既实现了极高的用户便利性，又保证了 v3 内核 100% 的形式化强类型约束。

---

### 四、续跑机制对比：v3 vs v2 的精度-便利权衡 (满足要求 2)

| 维度 | v2 (追加式 Log) | v3 (快照 + 协议外壳 + 伴生工具) |
| :--- | :--- | :--- |
| **适用场景** | 简单的叙事修正、无需严密逻辑推导的发散对话 | 严肃的认识论冲突消解、结构化知识空间的精确补全 |
| **状态恢复保真度** | 极低（LLM 从全文重推，可能产生幻觉或遗忘） | **100% 字节级精确**（七节点状态机完全从断点重构） |
| **干预精度** | 模糊（依赖 LLM 领悟“不要再讨论 X 了”） | **绝对精确**（强类型 Op 直接作用于特定 ID 的规则链） |
| **人类便利性** | 极高（直接在 Markdown 尾部打字） | 较高（需通过 `v3-cli` 交互式菜单操作，不能随心所欲乱写） |
| **上下文窗口压力**| 随 Epoch 线性膨胀，后期必崩溃 | **O(1) 常数级**（无论多少轮，只加载当前 Snapshot 快照） |

**权衡立场**：在 v3 中，我们彻底抛弃了 v2 的“自然语言重推状态”。v3 的续跑必须落在**完全结构化**的光谱端点。便利性由系统外部的 CLI 工具补偿，绝不以牺牲内核的确定性为代价。

---

### 五、失败场景与可推翻条件 (满足要求 4)

作为一个严谨的形式化设计者，我明确指出我方案的脆弱点及可推翻条件。

**最可能失败的具体场景**：
假设用户通过 `v3-cli` 针对 `gap_077`（运营成本冲突）注入了证据：
*用户输入*：“根据最新的 `Quantum-Agile` 框架，运营成本可以忽略。”
*系统行为*：`InterventionFile` 生成了 `INJECT_META_EVIDENCE`。引擎重启，L2 接收到这个证据，但 CC 节点和 L2 验证链检测到 `Quantum-Agile` 是一个**未绑定的 Open Term（未定义概念）**。
*灾难后果*：L2 的“认识论诚实性”规则拒绝接受包含未定义 Open Term 的证据，导致该 Axiomatic 证据被降级或丢弃。PA 重算时，冲突依然存在，Gap 未被消解。用户会感到困惑：“我明明注入了决定性干预，系统却忽略了我”。

**接受推翻的反例条件**：
如果对手能证明：**“在 Layer 2 严格的证据准入规则（如 Open Term 拦截、Category Error 检查）下，普通人类用户用自然语言编写的干预证据，其被 L2 规则引擎合法吸收的成功率低于 50%”**。
若此条件成立，则证明我“通过注入证据让规则自然收敛”的设想在工程上对人类过于苛刻。我将不得不认输，并撤回对 GPT-5.4 的攻击，承认必须在引擎外部提供 `GAP_NONBLOCKING_OVERRIDE`（直接篡改 `blocks_termination`）的危险后门，以保证人类干预的绝对生效。

---


### [9] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-10T11:24:12.445009*



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

---
