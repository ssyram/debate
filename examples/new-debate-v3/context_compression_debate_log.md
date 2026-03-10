# v3 认知引擎：上下文管理与压缩策略 辩论日志

> 2026-03-10T12:10:07.402390

---


### [1] Linus Torvalds

*2026-03-10T12:01:26.443974*

最关键的爆炸点：**Layer 2 的 `VerifiedClaim.evidence_chain` 无界增长**。理由很简单：它既参与“正确性相关”的在线逻辑（S4 冲突检测、`EVIDENCE_CONFLICT` GapSpec 触发），又会被拿去喂 LLM（证据回放/补充），还会被人类审计。你压缩错了不是“少一点历史”，而是**直接制造 regression：冲突漏检、分数聚合漂移、gap 误消失**。相比之下 `ranking_history` 只要滑窗就完事；`rejection_history` 已经是哈希集合，更多是性能问题不是上下文爆炸；`ChallengeTracker` 是 prompt 体积问题但不直接决定 truth-maintenance。

下面给出一套能实现、能验收、失败路径明确的压缩方案。别跟我谈“语义上应该没问题”，我给你类型签名和断言点。

---

## 1) 优先解决点与紧迫性

### 选择：`evidence_chain`（爆炸点二）

**为什么比其他更紧迫：**
- **它是双用途数据**：在线推理要用（冲突检测/defeater），离线审计也要用（溯源）。这导致你不能简单截断。
- **它是“放大器”**：每次重审追加 atoms，Top-K claim 会被反复重审，增长速度比 epoch 线性更糟（热门 claim 是超线性）。
- **它会反过来污染 Layer 1**：一旦冲突漏检，`GapSpec(EVIDENCE_CONFLICT)` 不触发，PA 可能提前终止，最后答案是胡扯但你还以为收敛了。

可推翻条件（反例实验）：
- 如果你能用数据证明：在实际工作负载里 `evidence_chain` 的 95 分位长度始终 < 200 atoms 且不会触发 prompt 超限、且冲突检测只依赖最新 K 条（K≤10）仍保持同等召回率，那我就同意先别管它。

---

## 2) 完整压缩方案（触发条件 / 类型形状变化 / 下游适配）

### 2.1 目标
把 `evidence_chain` 从“无限数组”变成**分层证据账本**：热区保留原子级细节，冷区变成**可计算的聚合摘要**，并且给冲突检测提供**不退化**的检查接口。

### 2.2 类型变更（压缩前 → 压缩后）

压缩前（你现有的）：
```ts
interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<string, number>>;
  evidence_chain: EvidenceAtom[];
}
```

压缩后（明确形状）：
```ts
type Strength = "ANECDOTAL"|"CORRELATIONAL"|"CAUSAL_STATISTICAL"|"AXIOMATIC";
type Polarity = "PRO"|"CON";

interface EvidenceAtom {
  atom_id: string;
  axis_id: string;
  polarity: Polarity;
  strength: Strength;
  source_ref: string;
  epoch_added: number;
}

interface AxisAggBucket {
  axis_id: string;
  // 可计算、给规则引擎用
  pro_weight: number;   // Σ weight(strength)
  con_weight: number;
  max_strength: Strength;
  // 冲突检测用的“签名”：不靠LLM
  has_pro: boolean;
  has_con: boolean;
  // 审计/检索锚点
  top_atoms: EvidenceAtom[]; // 按强度+新近性取K个
  covered_epoch_range: [number, number];
  atom_count: number;
}

interface EvidenceColdSummary {
  summarized_at_epoch: number;
  covered_epoch_range: [number, number];
  by_axis: Record<string, AxisAggBucket>;
  original_atom_count: number;
  // 防回归：摘要必须能重算axis_scores的raw差值（至少近似到误差界）
  agg_version: 1;
}

interface EvidenceLedger {
  hot_atoms: EvidenceAtom[];          // 最近W个epoch或最近N条
  cold: EvidenceColdSummary[];        // 多段摘要（chunked）
  // 快速索引，避免O(n)扫描
  hot_by_axis: Record<string, {has_pro:boolean; has_con:boolean; max_strength:Strength; atom_count:number}>;
}

interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<string, number>>;
  evidence: EvidenceLedger;           // 替换 evidence_chain
}
```

### 2.3 触发条件（机器可判定，数字化）

我不接受“token 太多了差不多压一下”。给你硬阈值：

```ts
interface EvidenceCompressPolicy {
  max_hot_atoms: number;        // 例如 80
  max_hot_epochs: number;       // 例如 3
  max_total_atoms: number;      // 例如 400 (超过必压)
  top_atoms_per_axis: number;   // 例如 3
}

function should_compress_evidence(
  claim: VerifiedClaim,
  now_epoch: number,
  policy: EvidenceCompressPolicy
): boolean;
```

判定逻辑（关键分支必须明确）：
- `total_atoms = claim.evidence.hot_atoms.length + Σ(cold.original_atom_count)`
- 触发当任一成立：
  1) `claim.evidence.hot_atoms.length > policy.max_hot_atoms`
  2) `now_epoch - min_epoch_in_hot > policy.max_hot_epochs`
  3) `total_atoms > policy.max_total_atoms`

### 2.4 压缩函数签名与失败路径

```ts
type CompressError =
  | { kind: "INVARIANT_BROKEN"; detail: string }
  | { kind: "STRENGTH_UNKNOWN"; atom_id: string }
  | { kind: "EMPTY_HOT_SET"; detail: string };

function compress_evidence_ledger(
  claim: VerifiedClaim,
  now_epoch: number,
  policy: EvidenceCompressPolicy
): Result<VerifiedClaim, CompressError>;
```

压缩算法（可实现，不靠LLM）：
- 从 `hot_atoms` 里选出要“冷凝”的那部分（例如：超出窗口的旧 atoms）。
- 按 `axis_id` 聚合成 `AxisAggBucket`：
  - `weight(strength)` 用你规则书默认阶梯值：0.15/0.40/0.75/0.95（别发明新的一套）
  - `pro_weight = Σ weight` where polarity=PRO
  - `con_weight = Σ weight` where polarity=CON
  - `has_pro/has_con` 直接 bool
  - `top_atoms` 取每轴 top-K（强度优先，其次 epoch 新近）
- 生成一个 `EvidenceColdSummary` chunk append 到 `cold[]`
- 从 `hot_atoms` 移除已冷凝部分，重建 `hot_by_axis`

断言/不变式（压缩后必须检查）：
- `original_atom_count == Σ by_axis.atom_count`（chunk内部一致）
- `covered_epoch_range` 包含 chunk 的所有 atom.epoch_added
- `hot_atoms` 不能为空？不强制，但如果为空，必须保证 `hot_by_axis` 为空且后续逻辑不依赖“至少一条热证据”；否则返回 `EMPTY_HOT_SET` 并让上游决定是否保留最后一条作为热区锚点。

### 2.5 下游组件如何适配（S4 冲突检测 & 轴评分）

#### 冲突检测接口：别再让 S4 “读全历史”
给一个明确的查询函数，S4 用它，不直接遍历数组。

```ts
interface ConflictQuery {
  axis_id: string;
  polarity: Polarity;           // 新证据极性
}

interface ConflictResult {
  conflicts: boolean;
  basis: "HOT" | "COLD" | "BOTH" | "NONE";
}

function evidence_conflicts(
  ledger: EvidenceLedger,
  q: ConflictQuery
): ConflictResult;
```

规则：
- 若新证据 polarity=PRO，则历史若存在 CON（`has_con==true`）即冲突候选；反之亦然。
- `basis` 标出冲突来自 hot 还是 cold，方便产出 `GapSpec(EVIDENCE_CONFLICT)` 的 `evidence_summary`。

#### AxisScore 计算：从 ledger 重建“等价 raw”
你现在 AxisScore 依赖 atom 聚合。那就别要求原子全在。

```ts
interface RawAxisTally { raw_pro: number; raw_con: number; }

function tally_axis_raw_from_ledger(
  ledger: EvidenceLedger,
  axis_id: string
): RawAxisTally;
```

计算：
- `raw_* = hot Σ weight + cold Σ pro_weight/con_weight`
- 然后进入你既定规则引擎 `sigmoid_normalized(raw_pro - raw_con)`，不改评分体系。

**关键点**：压缩不应该改变规则引擎输入的数值统计（除非你选择丢弃弱证据，但那是另一个设计选择，需要误差界；这里不丢弃，只聚合）。

---

## 3) 已知弱点与缓解措施

### 弱点 A：冷摘要丢失“具体来源组合”，可能影响某些细粒度解释
缓解：
- `top_atoms` 每轴保留 K 条强证据作为可读锚点，审计时至少能看到代表性来源。
- 需要更完整审计时从外部存储拉取原子（别塞回 prompt）：把被冷凝的 atoms 写入 `EvidenceAtomStore`（冷存储），只保留索引。

接口：
```ts
interface EvidenceAtomStore {
  put(claim_id: string, atoms: EvidenceAtom[]): Promise<void>;
  get_by_claim_and_epoch_range(claim_id: string, range: [number, number]): Promise<EvidenceAtom[]>;
}
```

### 弱点 B：冲突检测变成“轴级别”而不是“来源级别”
这其实是你想要的：`EVIDENCE_CONFLICT` 的定义就是同轴方向相反。你如果还想做“来源可靠性冲突”那是新 gap kind，别混在这里。

缓解：
- 在 `AxisAggBucket` 增加 `source_class_counts`（可选），按来源类型（论文/报告/新闻/个人）计数，仍是可计算字段，不靠 LLM。

### 弱点 C：哈希/聚合 bug 会引入 silent corruption
缓解：
- 每次压缩做一致性校验，并记录 `original_atom_count`、每轴 count。
- 离线回归测试：对同一组 atoms，压缩前后 `tally_axis_raw` 必须完全相等。

可推翻条件：
- 如果你跑 fuzz/回归测试发现压缩后 axis raw 不可保持（例如 strength 权重规则未来会变、或 atoms 还有额外维度影响 raw），那这套“可重建 raw 等价”就站不住脚，需要把额外维度纳入摘要结构而不是继续装死。

---

## 4) 预攻击：对手可能立场与具体缺陷

我预判有人会说：**“直接结构化摘要（LLM summarize evidence_chain）就行，或者只保留最近 K 个 atoms。”**

这两种都是典型的“白板涂鸦”。

### 攻击 1：只保留最近 K 个 atoms
你在 2.2 自己写了：S4 要做冲突检测。只保最近 K 个会怎样？

具体反例（trace）：
- Epoch 1：axis=A 有强 CON（CAUSAL_STATISTICAL）
- Epoch 2-5：不断追加 PRO 的弱证据
- 你滑窗 K=10，到了 Epoch 8，早期 CON 被截断
- Epoch 9：又来一条 PRO，你的冲突检测看不到历史 CON → **不触发 `EVIDENCE_CONFLICT`**
- PA 看到 Top-K 稳定就终止 → 输出“在 axis A 上支持 PRO”，但系统其实早就有强反证

这不是“可能”，是必然会发生，只要有足够轮次。

可推翻条件：给我数据，证明在真实负载里“重要冲突总发生在最近 K”，并给出 K 的数值下界（比如 99.9% 冲突跨度 ≤ 2 epoch）。否则别提。

### 攻击 2：让 LLM 做摘要替换原子
你要是给我这种接口：
```ts
function summarize(chain: EvidenceAtom[]): string
```
那就是垃圾。没有类型形状、没有可计算字段、没有错误路径。更糟的是：你把冲突检测外包给 LLM，**LLM 失败时系统状态是什么？**冲突漏报了你连检测手段都没有。

要做摘要可以，但必须像我上面那样：摘要是结构化、可重建统计、可做冲突查询的。否则你就是把 correctness 交给随机数生成器。

---

如果你要继续辩，下一轮你必须给出你方案的同等级别东西：触发条件数字、类型签名、失败分支、以及至少一个 trace（输入 atoms → 压缩 → S4 冲突查询输出）。没有这些就别浪费时间。

---


### [2] Ssyram

*2026-03-10T12:01:26.444015*

系统设计不是写散文。我们不讨论「压缩的哲学」，只讨论数据结构的边界和接口签名的演进。

我主张第一优先级解决**爆炸点二：Layer 2 的 `evidence_chain` 爆炸**。

理由很简单：Layer 1 的上下文爆炸（如 MB 提示词过长）最多导致生成效率下降或重复探索，这是**性能问题**；但 Layer 2 的 `evidence_chain` 爆炸如果不加干预，会导致 S4（DepthProbe）阶段的上下文被截断，进而漏判 `EVIDENCE_CONFLICT`，直接把带有致命缺陷的 claim 标记为 `VERIFIED`。这是**正确性问题**。在形式化验证的视角下，正确性永远先于性能。

以下是我的完整方案。

### 1. 压缩方案：基于轴投影的有界状态聚合（Bounded Axis-Projection）

不要用 LLM 去「总结」历史，这是把确定性的状态机交给概率模型去破坏。`evidence_chain` 的本质是一个 Event Sourcing（事件溯源）日志。S4 阶段对它的查询语义只有两个：
1. 算分（需要全量极性和强度的数学聚合）。
2. 冲突检测（只需要新证据与**历史最强证据**或**最近上下文**的对比）。

因此，压缩不应该是一个「定时触发的动作」，而应该在类型系统层面将 `EvidenceAtom[]` 投影为一个**大小严格有界**的聚合状态。

#### 1.1 类型形状变化（Type Signatures）

**修改前：**
```typescript
interface VerifiedClaim {
  // ... 其他字段
  evidence_chain: EvidenceAtom[];  // 随 epoch 线性增长，O(N)
}
```

**修改后：**
移除扁平的 `evidence_chain`，替换为按 `axis_id` 严格分桶的 `AxisEvidenceProfile` 字典。

```typescript
interface VerifiedClaim {
  // ... 其他字段
  evidence_state: Record<string, AxisEvidenceProfile>; // Key: axis_id
}

interface AxisEvidenceProfile {
  axis_id: string;
  // 1. 无损算分状态（纯数字，O(1) 空间，替代了遍历 chain 算分）
  score_components: { raw_pro: number; raw_con: number }; 
  
  // 2. 冲突检测锚点（严格有界，保留最高强度的 Atom，各最多 2 个）
  strongest_pro: EvidenceAtom[]; 
  strongest_con: EvidenceAtom[]; 
  
  // 3. 近期上下文窗口（严格有界，保留最近 3 个 epoch 的 Atom）
  active_window: EvidenceAtom[]; 
  
  // 4. 归档游标（指向外部存储，供人工审查，对 LLM 不可见）
  archive_cursor: string; 
}
```

#### 1.2 触发条件与下游适配

**触发条件：** 
不需要外部监控器判定「是否需要压缩」。这是一个纯函数操作。每次 Layer 2 产生新的 `EvidenceAtom` 时，调用 `update_evidence_state(current_state, new_atom)`：
1. 将 `new_atom` 的强度折算为数值，累加到 `score_components`。
2. 将 `new_atom` 插入 `active_window`，若窗口大小超过限制（如 5 个），将最老的踢入 `archive`。
3. 比较 `new_atom` 与 `strongest_pro/con`，若强度更高则替换。

**下游 S4 适配：**
S4（DepthProbe）的 LLM Prompt 不再接收无尽的 chain。它的输入变为：
*“当前评估轴上，历史最强的支持证据是 [strongest_pro]，最强的反对证据是 [strongest_con]，最近的讨论上下文是 [active_window]。请判断新提取的候选证据是否与上述锚点构成 `EVIDENCE_CONFLICT`。”*

### 2. 已知弱点及缓解措施

**已知弱点：**「千刀万剐」效应。如果一个方向有 100 个 `ANECDOTAL`（轶事级）的反对证据，但由于它们强度低，无法进入 `strongest_con`，且随着时间推移被挤出 `active_window`。此时来了一个新的 `CORRELATIONAL` 支持证据，S4 可能会因为没看到那 100 个轶事证据，而认为没有发生冲突。

**缓解措施：**
`score_components` 中的 `raw_con` 已经无损地累加了那 100 个轶事证据的权重（基于阶梯值）。PA 节点在计算最终 score 和 residual_risk 时，会看到极高的 `raw_con` 阻尼。即使 S4 没有报出精确的 `EVIDENCE_CONFLICT` 缺口，该 claim 的最终得分也会被压低，从而无法成为阻塞终止的绝对 Top-1。

### 3. 预攻击：结构化摘要（Section 4.2）是类型错误

我知道一定有人会主张使用 4.2 节提到的「结构化摘要替换」，让 LLM 生成 `EvidenceChainSummary`，甚至在里面放一个 `conflict_detected: boolean`。

**我对这种方案有生理性厌恶。这是典型的类型错误和责任倒置。**

引用 4.2 的构想：*“`conflict_detected: boolean` // 是否在摘要覆盖的 epoch 内检测到冲突”*

**攻击点：**
如果 LLM 在生成摘要时，把 10 条 `EvidenceAtom` 压缩掉，并输出了一个 `conflict_detected: true`。请问，当下游的 Layer 1 `repair()` 节点被触发时，它需要的 `GapSpec.evidence_summary` 从哪里来？它怎么知道是**哪句话**和**哪句话**冲突了？
你把一个**可计算的结构体数组**，变成了一个**黑盒 LLM 输出的布尔值**。一旦底层证据被销毁，冲突的上下文就丢失了，Layer 1 根本无法生成针对性的新草稿（HypothesisDraft）来修复这个缺口。这直接切断了 v3 架构中 Layer 2 向 Layer 1 传递高精度反馈的反馈链。

把逻辑判断（冲突检测）和状态压缩（摘要）混在一个 LLM 调用里，是 AI 工程中最业余的做法。

### 4. 必须包含的可推翻条件

我的主张基于一个核心假设：**任何有价值的 `EVIDENCE_CONFLICT`，必然发生在历史最强证据（strongest）或近期活跃证据（active_window）与新证据之间。**

**推翻我的条件是：**
如果对手能给出一个具体的工程场景或逻辑推演，证明存在一种高价值的 `EVIDENCE_CONFLICT`，它**既不与**该轴上历史强度最高的证据冲突，**也不与**最近 3 个 epoch 内的证据冲突，而是**必须**通过精确对比第 4 个 epoch 之前某个非最高强度的边缘证据才能被发现，且这种漏判会导致 PA 节点的排名发生致命倒置——那么我的 `AxisEvidenceProfile` 有界投影方案就是错的，我将收回该主张。

否则，请针对我的接口签名进行讨论。

---


### [3] 康德（Immanuel Kant）

*2026-03-10T12:01:26.444031*

我优先要切开的、也是最危险的上下文爆炸点是：**爆炸点二——Layer 2 的 `evidence_chain` 线性增长**。理由并非“它最大”，而是它最容易诱发一种认识论僭越：你把“证据链的叙事完整性”（溯源的可读性）误当作“冲突检测所需的构成性条件”。前者至多是**调节性**的（便于审查与解释），后者才触及系统运行时判断的**构成性**条件（决定 `EVIDENCE_CONFLICT`、`UNRESOLVED_DEFEATER` 等 GapSpec 是否触发）。一旦压缩做错，系统不是“少看点历史”，而是**改变了可否证伪性结构**，让 PA 的终止与 Top‑K 稳定变成幻象。

下面给出完整压缩方案：它的关键是**把 evidence_chain 中“用于冲突判定的最小充分结构”抽取为可机器操作的 Schema**，把其余叙事性内容下沉为归档（调节性、可检索）。

---

## 1) 我主张优先解决的爆炸点及其紧迫性

### 爆炸点二为何比其他更紧迫
- **它直接参与构成性判定**：S4 的冲突检测与 GapSpec(`EVIDENCE_CONFLICT`) 依赖证据历史；压缩失真会改变“冲突是否存在”的事实判定，继而影响 `blocks_termination`，这比 MB prompt 变短、ranking_history 归档这类问题更致命。
- **它的增长是“同一 claim 反复重审”的累积**：这类增长不是简单滑窗能消除，因为新证据的意义恰在于与“旧证据”比较；丢旧即丢判准。
- **它最容易制造辩证幻象**：你若用 LLM 生成“自然语言摘要”替代原子证据，系统会把“摘要看起来一致”当成“证据确实一致”，这正是我所说理性追求无条件者时的幻象：叙事连贯性冒充了可检验结构。

**可推翻条件**：若你能形式化证明（不是经验声称）在现有 S4 冲突检测算法下，冲突判定只依赖最近 K 个 atom（且 K 有全局上界），则此爆炸点不再紧迫；它将降格为普通滑动窗口问题。

---

## 2) 完整压缩方案（触发条件 / 类型形状变化 / 下游适配）

### 2.1 方案总览：两层证据表示 + 冲突索引（Schema）
把 `VerifiedClaim.evidence_chain: EvidenceAtom[]` 拆为：
1) **热层（hot）**：最近少量原子（供 LLM 语义降维阶段参照语境）
2) **构成性索引层（index）**：可机器判定冲突所需的“最小结构”
3) **冷层归档（archive）**：完整 atom 的不可变存储（供审计/回放；默认不进 prompt）

### 2.2 触发条件（机器可判定）
对每个 claim 独立触发（避免全局压缩把无关 claim 一起动刀）：

```typescript
type EvidenceCompressionTrigger =
  | { kind: "ATOM_COUNT"; claim_id: string; atom_count: number; threshold: number }
  | { kind: "TOKEN_BUDGET"; claim_id: string; estimated_tokens: number; threshold: number }
  | { kind: "LOW_INFORMATION_GAIN"; claim_id: string; recent_gain: number; threshold: number; window: number };
```

建议默认触发（满足其一即可）：
- `ATOM_COUNT`: `evidence_chain.length > 80`
- `TOKEN_BUDGET`: 估算注入 prompt 的证据 tokens > 6k（你可以按模型上下文预算配置）
- `LOW_INFORMATION_GAIN`: 最近 3 个 epoch 新增 atoms 都落在已覆盖 axis、且 strength 不提升、且 polarity 不改变（这是“信息增益低”的可计算替代）

**可推翻条件**：如果你能证明对某些 domain（例如高争议但证据粒度细的医学）80 的阈值必然导致漏冲突，则阈值与触发器必须按 domain_kind 分层，而非全局默认。

### 2.3 压缩前后的类型形状变化（接口定义）
把 `VerifiedClaim` 改为（或并行引入新字段，不破坏旧接口也可）：

```typescript
interface EvidenceStoreRef {
  claim_id: string;
  archive_key: string;                 // 指向冷存储
  archived_until_epoch: number;         // 已归档覆盖到哪个 epoch
}

interface EvidenceConflictIndex {
  claim_id: string;
  built_at_epoch: number;
  by_axis: Record<string, {
    // 关键：保留“可冲突”的最小结构，而非叙事摘要
    pro_strength_max: EvidenceAtom["strength"] | null;
    con_strength_max: EvidenceAtom["strength"] | null;
    pro_count: number;
    con_count: number;

    // 保留少量“可回指”的代表原子（不是随意摘要）
    pro_exemplars: EvidenceAtom[];      // top-K by strength, recency tiebreak
    con_exemplars: EvidenceAtom[];

    // 构成性冲突旗标：依据规则（非 LLM）计算
    conflict_flag: boolean;
    conflict_basis: "POLARITY_BOTH_PRESENT" | "HIGH_STRENGTH_OPPOSITION" | "SOURCE_INCOMPATIBILITY" | null;
  }>;
}

interface CompressedEvidenceChain {
  hot: EvidenceAtom[];                 // 最近 K 个，例如 K=12
  index: EvidenceConflictIndex;        // 全历史聚合的构成性索引
  store_ref: EvidenceStoreRef;         // 冷归档引用
  original_atom_count: number;
}

interface VerifiedClaim {
  claim_id: string;
  status: "VERIFIED" | "DEFENSIBLE";
  residual_risk: number;
  axis_scores: Partial<Record<string, number>>;
  evidence: EvidenceAtom[] | CompressedEvidenceChain; // 允许渐进迁移
}
```

### 2.4 压缩算法（关键是“冲突索引”如何构成）
- 将旧 `evidence_chain` 全量写入 archive（不可变）
- 构建 `EvidenceConflictIndex`：
  - 对每个 `axis_id` 统计 pro/con count 与最大 strength
  - 选取 `pro_exemplars`、`con_exemplars` 各 K 个（K=3 或 5）
  - 用**规则**（非 LLM）设置 `conflict_flag`：
    - 若 `pro_count>0 && con_count>0`，则至少标记 `POLARITY_BOTH_PRESENT`
    - 若 `pro_strength_max >= CAUSAL_STATISTICAL` 且 `con_strength_max >= CORRELATIONAL`（阈值可配置），标记 `HIGH_STRENGTH_OPPOSITION`
    - 若 `source_ref` 属于互斥体制（例如同一数据集不同版本不可共存），可加 `SOURCE_INCOMPATIBILITY`（需你已有 source_ref 规范；没有就别装作有）
- 仅保留最近 K 个 atom 进入 `hot`

### 2.5 下游组件如何适配（S4/S5/GapSpec/审计）
- **S4（DepthProbe）冲突检测**改为：
  1) 先查 `index.by_axis[axis_id].conflict_flag`（O(1)）
  2) 新 atom 到来时，仅需更新该 axis 的计数、max_strength 与 exemplars，并重新计算 conflict_flag（增量更新）
  3) 若 conflict_flag 由 false→true，则触发 `GapSpec(EVIDENCE_CONFLICT)`，并在 `evidence_summary` 中引用 exemplars 的 `atom_id/source_ref/epoch_added`
- **LLM 阶段 A（EvidenceAtomCandidate 生成）prompt 注入**：
  - 不再注入全链；注入：
    - `hot` 原子（最近 K）
    - 对相关 axis 的 exemplars（各 1-2 条）
    - `index` 的统计（pro_count/con_count/max_strength），这比叙事摘要更不易误导
- **人工审计/回放**：
  - 需要时通过 `store_ref.archive_key` 拉取全链（调节性用途，不污染运行时上下文）

**可推翻条件**：若你能举出一类冲突只有在“两个低强度证据跨 epoch 的组合模式”下才显现，而上述 index（max_strength + counts + exemplars）系统性检测不到，则 index 的“最小结构”需扩充，例如加入时间分布特征或 source_ref 聚类签名。

---

## 3) 已知弱点与缓解措施

### 弱点 A：索引是“可计算的”，但可能不充分
- **风险**：真正的冲突有时是语义层的（定义漂移、测量口径变化），并不表现为简单 PRO/CON 并存。
- **缓解**：当 S4 发现 `SchemaChallengeNotice(trigger="ANOMALY")` 且 `is_homologous=true` 时，强制一次“口径一致性检查”检索冷存储中该 axis 的近邻 source_ref（但注意：同源张力禁止触发广度引擎，这里只是回读同一图型内材料）。

### 弱点 B：exemplars 选择可能偏置，导致 LLM 被“代表样本”误导
- **风险**：top‑K 强度偏置使少数来源支配语境。
- **缓解**：exemplars 选择加入多样性约束（按 `source_ref` 去重），接口上可扩展：
  - `exemplar_policy: "TOPK" | "TOPK_DIVERSIFIED"`

### 弱点 C：冷存储检索引入延迟与工程复杂度
- **缓解**：把检索变为“仅在冲突/挑战触发时”而非常规路径；并记录 `archive_key` 使检索可审计。

---

## 4) 对至少一个对手立场的预攻击（精确引用 + 缺陷）

我预先反对一种很诱人的立场：你在 4.2 给出的 **“结构化摘要替换”**，尤其是这个字段设计：

> `conflict_detected: boolean;  // 是否在摘要覆盖的 epoch 内检测到冲突`

这里有一个需要先被区分的概念混乱：你把 `conflict_detected` 当成可继承的“事实”，但它其实是**在特定检测程序、特定输入可得性**下的输出。摘要一旦替换原子链，未来的检测程序（或阈值）变更时，你无法回到“对象本身”，只能回到“先前判断的残影”。这正是把调节性记录僭越为构成性基础：系统将被迫把“当时检测到/没检测到”当作对象属性。

我的方案之所以坚持 **index 是规则可重算的、且 archive 保留对象本身**，就是避免让“检测结果”冻结为“存在论事实”。

**可推翻条件**：如果你能给出一个不依赖 LLM、可证明与全量 evidence_chain 等价的冲突判定函数 `F(chain) -> conflict`，并证明你的摘要结构是 `F` 的充分统计量（sufficient statistic），那么 `conflict_detected` 才有资格进入摘要并替代原链；否则它只能作为调节性注释，而不能作为运行时依据。

--- 

这就是第一轮：我选择 evidence_chain，因为它牵涉构成性判定；我的压缩策略是“热原子 + 构成性冲突索引 + 冷归档”的三分法；并且我提前指出仅靠结构化摘要字段（尤其是 `conflict_detected`）会把判断史伪装成对象史。

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-10T12:02:18.723295*

1) 你把“正确性问题”说得很硬，但你的冲突检测语义其实被你自己改烂了  
你宣称 S4 冲突检测“只需要历史最强证据或最近上下文”。这不是“压缩”，这是**换规格**。v3 里 `EVIDENCE_CONFLICT` 的定义根本不是“最强 vs 最新”的冲突，而是“同一轴上证据方向相反导致的冲突缺口”，而且它会触发 **阻塞性 GapSpec**。  
具体崩溃场景：  
- axis X 上早期出现一条 `CAUSAL_STATISTICAL` 的 CON（强但不一定“最强”，因为后来可能来了 `AXIOMATIC` 的 PRO，比如一个制度性原则/公理化断言被错误标为 AXIOMATIC）。  
- 你的 `strongest_*` 只保留“强度最高”的 2 条，窗口只保留最近 3 epoch。那条关键的因果 CON 既不在 strongest（被更强但不相关的“AXIOMATIC”挤掉），也不在 active_window（太旧），就永远消失在 LLM 可见状态里。  
然后新来的 PRO 证据与那条旧 CON 实质冲突，但 S4 看不到，`EVIDENCE_CONFLICT` 不会发，系统就可能在错误的“无冲突”前提下继续推进。你用一句“任何有价值冲突必在 strongest 或 active_window”当语义保证——我讨厌这种“语义保证”。给我**可执行的检查**，否则这就是自欺。

2) 你说“不要用 LLM 总结”，结果你把系统推到更糟的不可审计状态：archive_cursor 是个摆设  
你把证据踢进 `archive_cursor`，然后说“对 LLM 不可见”。OK，那 S4/S5 未来的 re-eval 怎么办？你实际上把验证变成了“只基于一小撮可见锚点”的**有损验证**。  
更关键：你攻击别人 `conflict_detected: boolean` 会切断 `GapSpec.evidence_summary`，但你自己的设计一样切断：当冲突发生在归档区时（按你方案“理论上不会发生”——又来了），你同样没法生成可操作的 `evidence_summary`，因为 L2 当下根本没读归档。  
你需要给出函数签名把这事说清楚：  
- `load_archived_evidence(cursor: string, filter: {axis_id: string, ...}): EvidenceAtom[] | Err` 什么时候调用？  
- 调用失败（IO/缺页/索引损坏）时 S4 状态机走哪个分支？`S7(Suspended)` 还是直接降级 residual_risk？给我明确分支，不要“应该可以”。

3) 你的“千刀万剐”缓解是明显的规格错配：PA 的低分不能替代阻塞性缺口  
你说：就算 S4 漏掉冲突，`raw_con` 会压低分数，Top-1 上不去，所以没事。扯淡。  
在 v3 里 **终止阻塞条件**有 `EVIDENCE_CONFLICT`（同轴 VERIFIED 反向）这种硬条件；它不是“分数低就行”。你把一个应该产生 `GapSpec { kind: "EVIDENCE_CONFLICT", blocks_termination: true }` 的情况，降级成“分数惩罚”。这会让系统在“没有被标记为阻塞”的前提下提前 terminate——这就是 regression。  
而且你还偷换了目标：S4 是为了检测冲突并触发修复，不是为了给 PA 一个更低的 score。修复链条断了，你的系统会稳定地产生“看似收敛但实际上漏了关键缺口”的垃圾输出。

你要继续捍卫这个方案，就别再讲哲学。给我：  
- `update_evidence_state(state: AxisEvidenceProfile, atom: EvidenceAtom) -> AxisEvidenceProfile` 的完整签名与关键分支（尤其是 strongest 替换、窗口踢出、归档写失败）。  
- 一个具体 trace：输入一串 atoms（含 epoch、axis、polarity、strength），展示在你的状态裁剪下**仍然**能触发应该触发的 `EVIDENCE_CONFLICT`；再展示一个你认为“不重要”的漏判 case，并证明它不会造成 `blocks_termination` 的错误判定。否则这设计就只是“希望不会出事”。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-10T12:02:59.248460*

我是 Ssyram。

康德，你的方案在试图用「构成性（Constitutive）与调节性（Regulative）」的区分来掩盖一个核心的工程逃避：**你无法给出一个不依赖 LLM 语义理解的、真正的「冲突判定规则」。**

针对你的第 1 轮发言，提出以下质疑：

### 质疑一：关于 `EvidenceConflictIndex` 的「规则化」幻象与语义逃避

你声称 `conflict_flag` 是依据「规则」而非 LLM 计算的，并给出了 `POLARITY_BOTH_PRESENT` 等示例。这在形式化上是极其廉价且无力的。

在 Layer 2 的 S4/S5 阶段，真正的 `EVIDENCE_CONFLICT` 往往不是简单的「一正一反」，而是**语义蕴含层面的不相容**（例如：证据 A 认为「开源降低了企业级安全」，证据 B 认为「开源提高了代码透明度从而增强了审计安全」）。这两个命题在你的 `index` 里可能都被标记为 `PRO`（支持 AI 开源），或者一个 `PRO` 一个 `CON` 但在不同轴上。

**质疑：**
如果你的规则仅基于 `polarity` 和 `strength` 的计数，那么这种「构成性索引」就是典型的**正确但无用的废话**——它只抓住了最表层的符号冲突，却丢失了导致 Layer 2 震荡的语义冲突。请给出 `is_semantically_conflicting(atom_new, index_exemplars)` 的具体逻辑。如果这个逻辑最终还是回到了 LLM 判定，那么你所谓的「规则引擎」只是给 LLM 穿了一层薄薄的类型外壳，并没有解决「叙事冒充结构」的问题。

### 质疑二：关于 `LOW_INFORMATION_GAIN` 触发器导致的过早收敛（Premature Convergence）

你提出的触发条件之一是「最近 3 个 epoch 新增 atoms 都落在已覆盖 axis、且 strength 不提升、且 polarity 不改变」。

这暴露了你对 CEGAR（逆向精化）经验的忽视：**初始抽象的质量决定收敛速度，但错误的抽象会导致系统进入死胡同。** 在一个对抗性的辩论或研究场景中，证据的出现往往是非单调的。

**质疑：**
这种基于「趋势平稳」的压缩触发，极易让系统进入一种**自洽的盲区**。如果第 4 个 epoch 出现了一个 `strength` 虽低但能推翻整个证据链前提的「微弱信号」（Weak Signal），而此时你的系统已经因为「信息增益低」将历史全部归档并切换到了基于 `exemplars` 的压缩模式，你如何保证这个微弱信号不被 `index` 的统计偏置所淹没？你的压缩协议里是否缺少一个「反向精化（Refinement）」的路径——即在什么情况下，系统必须承认 `index` 失效，从而强制重建（Rehydrate）冷存储中的全量证据？

### 质疑三：关于 `strength` 作为索引核心指标的不可靠性

你的方案高度依赖 `strength`（ANECDOTAL 到 AXIOMATIC）来选择 `exemplars` 并计算 `conflict_flag`。但根据 v3 协议，`strength` 是由 Layer 2 阶段 A 的 LLM 产出的。

**质疑：**
你极力反对「权重由 LLM 决定」，却将系统的「构成性基础」建立在 LLM 对证据强度的概率性判定上。这是一种**隐藏的递归依赖**。如果 Epoch 1 的 LLM 错误地将一个孤证标记为 `AXIOMATIC`，它将永久占据 `exemplars` 的位置，并根据你的规则锁死 `conflict_flag`。

请说明：你的系统如何审计这种「由 LLM 注入的初始偏置」？如果 `index` 是不可逆的压缩，这种偏置就会变成你所谓的「存在论事实」。请给出 `EvidenceConflictIndex` 的**版本校验与重算协议**，以证明它不是在冻结错误。

---

**总结：**
康德，你给出了一个看起来很美的三层架构，但在最关键的「语义冲突如何转化为机器规则」这一点上，你选择了用 `exemplars` 这种抽样手段来糊弄过去。**抽样不是证明，统计不是逻辑。** 如果不能在不调用 LLM 的前提下定义「冲突」，你的 `index` 就只是一个昂贵的缓存，而不是一个认知引擎的构成性组件。

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-10T12:03:50.072790*

1) **这里有一个需要先被区分的概念混乱：你把“冲突检测”当成了构成性（konstitutiv）真理维持，而系统轴本身被规定为调节性（regulativ）评估框架。**  
你说“压缩错了会直接制造 regression：冲突漏检、分数漂移、gap 误消失”，这在工程语气里把 `EVIDENCE_CONFLICT` 当作对“事实矛盾”的构成性判定。但在 v3 里，axis 的 mode 已经被先验裁定为 regulative；冲突也只是“在某一调节性轴上出现相反取向的证据原子”。  
- **尖锐质疑**：你凭什么把“轴级 polarity 相反”提升为必须零退化的在线真理维持？这一步需要一个额外的先验合法性：为什么这种冲突是系统不可容忍的“错误”，而不是调节性地提示“该轴需要更细分的 discriminator / 或回到 SchemaChallenge”？  
- **可推翻条件**：若你能给出一个清晰的判据：在何种轴类型/协议（empirical_test_v1 vs interpretive_consensus_v1 等）下，`EVIDENCE_CONFLICT` 的漏检会导致**必然的**错误终止（而非只是残余不确定性上升、epsilon 变大），那你才有资格把它当成构成性灾难来设计。

2) **你的“不可退化”承诺其实偷换了问题：你把“冲突检测”降格为 `has_pro/has_con`，但这只是在形式上保留了矛盾的影子，未必保留其可用性。**  
你给的 `evidence_conflicts()` 规则是：新 PRO 若历史 has_con 即“冲突候选”。这会把大量本应被更高层图型（Schema）吸收的差异，硬编码为同一类 GapSpec。换言之，你用一个**分析判断式**的布尔接口（有没有相反极性）替代了原先可能是**综合判断式**的冲突评估（是否在同一 scope/同一 discriminator 下矛盾）。  
- **尖锐质疑**：你如何防止“假冲突爆炸”？例如 CON 原子来自不同 scope/不同测量协议/不同 population，只因同轴就被标记 has_con；这会系统性触发 `EVIDENCE_CONFLICT`，使 repair() 进入无谓循环，反而破坏终止条件。你在类型里没有携带 discriminator、scope_tokens、protocol_id，压缩后更不可能恢复。  
- **可推翻条件**：如果你能证明 v3 对 `EvidenceAtom` 的冲突判定本来就**只**依赖 axis_id+polarity（与 scope/assumptions 无关），那你的布尔降维才等价；否则你是在以“可实现”为名，改变了冲突概念。

3) **你声称“压缩不改规则引擎输入数值统计（raw_pro/raw_con 完全等价）”，但这前提依赖 strength→weight 映射在时间上不变；而系统恰恰允许 rulebook/协议演化，这会使你的冷摘要变成不可再解释的历史冻结。**  
你把冷区聚合为 `pro_weight/con_weight`，并宣称可用 `tally_axis_raw_from_ledger()` 重建 raw。可是在 v3 中 strength 阶梯值是“默认”，并非先验必然；未来可能按领域或协议不同调整（甚至 stakeholder 派生）。一旦映射变化，你的冷摘要无法回放“当时为何得出该 raw”。这不是性能问题，而是**可审计性与可更新性**的矛盾。  
- **尖锐质疑**：你到底要的是“当下规则下的可计算性”，还是“跨规则演化的可追溯性”？两者不能同时由 `pro_weight` 这种已经折算过的量来满足。你缺少一个先验选择：冷摘要应保存“原始计数（按 strength 分桶）”还是“折算后的权重和”？  
- **可推翻条件**：若你补充一种保证：strength 权重表在一个 claim 生命周期内不可变（版本锁定），并且审计永远按该版本解释，则你的 raw 等价承诺成立；否则你必须在摘要中保留更原始的 sufficient statistics（例如每轴按 strength×polarity 的计数向量），才能在规则变更后重算。

以上三点共同指向：你的方案很“工程可落地”，但它把若干本应在图型层（Schema / discriminator / protocol）里处理的综合问题，压扁成可计算布尔量与加权和；这一步若无先验条件的交代，就会把经验上的便利僭越为认知法则。

---


### [7] Linus Torvalds

*2026-03-10T12:04:34.694204*

你们质询里最大的不当之处：**把“需要更聪明的语义冲突”当成否定压缩的理由**。v3 已裁定 `EVIDENCE_CONFLICT` 是 *GapSpec kind*，不是哲学讨论。系统要的是：同一 axis 上出现相反极性时，**可计算、可复现地**阻塞终止；不是让 LLM 去“理解”何为真正矛盾。

### 1) 立场：evidence_chain 必须压成“可重算统计 + 可定位样本”，不是 Ssyram 的 strongest/window 也不是纯 LLM 摘要  
我坚持分层 ledger，但修正 Kant 指出的“权重冻结”问题：冷摘要不能只存 `pro_weight/con_weight`，必须存**按 strength 分桶的计数向量**，才能规则表演化后重算。

接口（形状变化）：
```ts
type Strength = "ANECDOTAL"|"CORRELATIONAL"|"CAUSAL_STATISTICAL"|"AXIOMATIC";
type Polarity = "PRO"|"CON";
type StrengthVec = Record<Strength, number>;

interface AxisAggBucketV2 {
  axis_id: string;
  pro_counts: StrengthVec;
  con_counts: StrengthVec;
  has_pro: boolean;
  has_con: boolean;
  top_atoms: EvidenceAtom[];
  covered_epoch_range: [number, number];
  atom_count: number;
  strength_rulebook_version: string; // 仅标记，不折算
}
```
触发条件不变（max_hot_atoms/max_total_atoms），压缩函数失败仍走 `Result<..., CompressError>`。

**可推翻条件**：如果你能证明评分永远只用“当时的默认阶梯值”且不会版本化，那才允许只存折算权重和。

### 2) 精确攻击 Ssyram（引用你的话）  
你写：**“任何有价值的 EVIDENCE_CONFLICT，必然发生在 strongest 或 active_window”**。这就是垃圾“语义保证”。Linus 的反例成立：旧的 `CAUSAL_STATISTICAL CON` 被更强但不同语境的 “AXIOMATIC PRO” 挤掉，同时又滑出 window，你直接漏掉 `blocks_termination` 级别的 gap。  
你还说“分数会被压低所以没事”——错，v3 终止是 *硬阻塞条件*，不是“分数低就行”。

**可推翻条件**：给出离线统计，证明 99.9% 冲突跨度 ≤3 epoch 且 strongest 覆盖率≥99.9%，否则 strongest/window 不是规格内实现。

### 3) 回应 Kant 对我的三点质疑（指出你哪里跑偏）
- 你说 axis 是 regulative 所以冲突不是“构成性灾难”。但 v3 已裁定：`EVIDENCE_CONFLICT` 可 `blocks_termination:true`。这在工程上就是构成性门闩，别偷换成“只是提示”。  
- 你攻击 `has_pro/has_con` 会“假冲突爆炸”。这是你把 discriminator/scope 的事塞进 EvidenceAtom。v3 的 EvidenceAtom 就这些字段；要更细冲突，新增 GapKind/Atom 维度，而不是否决压缩。  
- 你对“权重表演化”质疑有效，所以我上面改成 strength 分桶计数向量，规则变更后可重算。

**可推翻条件**：如果未来把 scope/discriminator 纳入 EvidenceAtom 并且 `EVIDENCE_CONFLICT` 定义依赖它们，那 ledger 的 bucket 必须扩维（axis×discriminator），否则我这版也会回归。

---


### [8] Ssyram

*2026-03-10T12:04:34.694235*

Linus，你的攻击有一半是基于你自己的类型读取错误，另一半打中了真正的痛点。

**1. 驳斥「换规格」的稻草人攻击**

你声称：*“你的 `strongest_*` 只保留‘强度最高’的 2 条……那条关键的因果 CON 既不在 strongest（被更强但不相关的“AXIOMATIC”挤掉）”*

回去看我上一轮给出的类型签名：`strongest_pro` 和 `strongest_con` 是**独立分列**的。一个 `AXIOMATIC` 的 PRO 永远不可能挤掉一个 `CAUSAL_STATISTICAL` 的 CON。你的大脑在解析我的接口时发生了越界访问。只要正反两方都有高强度证据，它们都会分别驻留在各自的锚点中，S4 必然能看到这对矛盾。

**2. 接受修正：分数惩罚不能替代阻塞性判定**

你指出我把 `blocks_termination` 降级为分数惩罚是 regression。**我接受这个质询。** 

在 CEGAR 架构中，counterexample（冲突）必须显式阻断验证循环，不能被数值平滑掉。把逻辑缺口降级为概率阻尼，确实违背了形式化验证的底线。如果冲突被归档，Layer 1 的 `repair()` 确实会因为拿不到 `evidence_summary` 而断链。

**3. 修正方案：强度水位线（Watermarks）与冲突固化**

为了彻底杜绝「旧 CON 被新 CON 挤掉导致漏判」的问题，同时保持严格有界的上下文，我将 `strongest_*` 升级为**强度水位线（Watermarks）**，并引入**冲突固化（Pinning）**机制。

```typescript
type Strength = "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL" | "AXIOMATIC";

interface AxisEvidenceProfile {
  axis_id: string;
  score_components: { raw_pro: number; raw_con: number };
  
  // O(1) 空间：每个强度等级最多保留 1 个代表性 Atom，共计 4 PRO + 4 CON
  watermarks_pro: Record<Strength, EvidenceAtom | null>;
  watermarks_con: Record<Strength, EvidenceAtom | null>;
  
  active_window: EvidenceAtom[];
  
  // 冲突固化：一旦 S4 检测到冲突，直接将 GapSpec 钉死在热区，禁止归档
  pinned_conflicts: GapSpec[];
}
```

**状态机流转：**
1. `update_evidence_state` 插入新 atom 时，直接按 `strength` 写入对应的 `watermarks` 槽位。S4 的 prompt 接收完整的 8 个水位线 Atom。这保证了任何强度层级的最高证据都不会被覆盖。
2. 如果 S4 判定新 Atom 与水位线中的某个 Atom 构成 `EVIDENCE_CONFLICT`，产出的 `GapSpec` 直接推入 `pinned_conflicts`。
3. 只要 `pinned_conflicts` 不为空，PA 节点强制判定 `blocks_termination: true`。Layer 1 的 `repair()` 直接读取 `pinned_conflicts` 中的 `evidence_summary`，不需要去 `archive` 盲目捞数据。

**4. 可推翻条件**

我的水位线设计基于**冲突单调性假设**：如果一个新证据与历史上的某个弱证据（如 `ANECDOTAL`）冲突，那么它必然与同一轴上已保留的同极性强证据（如 `CAUSAL_STATISTICAL`）冲突。

**推翻条件**：如果你能给出一个具体的 trace，证明存在一种高价值的跨极性冲突，它**只**发生在特定来源的弱证据之间，而 S4 看到该轴的高强度证据时反而认为“没有冲突”，导致 `watermarks` 漏判——那么我的 O(1) 水位线投影就是错的。我会承认必须退回到保留全量历史的哈希索引。

否则，接受这个 O(1) 的有界状态结构，停止要求系统去遍历无限增长的数组。

---


### [9] 康德（Immanuel Kant）

*2026-03-10T12:04:34.694249*

1) **压缩立场（爆炸点二）**：我接受 Linus 对“证据链必须支持可重算统计”的压力，但反对把冷区直接折算成 `pro_weight/con_weight` 作为唯一存根。为避免你所说的“规则表演化”冻结历史，我把冷摘要改成**强度分桶计数向量**而非权重和：  
```ts
type Strength = "ANECDOTAL"|"CORRELATIONAL"|"CAUSAL_STATISTICAL"|"AXIOMATIC";
type Polarity = "PRO"|"CON";

type StrengthCounts = Record<Strength, number>;

interface AxisAggBucketV2 {
  axis_id: string;
  pro_counts: StrengthCounts; // 充分统计量（可随 rulebook 重算）
  con_counts: StrengthCounts;
  has_pro: boolean; has_con: boolean;
  max_strength_pro: Strength|null;
  max_strength_con: Strength|null;
  exemplars: { pro: EvidenceAtom[]; con: EvidenceAtom[] };
  covered_epoch_range: [number, number];
}
```
触发条件仍可用 Linus 的 `max_hot_atoms/max_total_atoms`；但**冷凝输出改为 counts**，而 `tally_axis_raw_from_ledger(rulebook_version)` 在运行时再折算。  
**可推翻条件**：若未来 axis_rulebook 需要依赖 atom 的非 strength 特征（如来源可信度分层）才能折算，则仅 counts 不再充分，必须把该特征也纳入桶维度（类型形状扩大）。

2) **对 Ssyram 的精确攻击**：你写“*任何有价值的 EVIDENCE_CONFLICT 必然发生在 strongest 或 active_window*”。这不是“压缩”，而是把冲突的**构成性条件**偷换为经验性启发式；且你自己承认“千刀万剐效应”。在接口上你缺少一个**可审计的反向精化触发器**：当 `score_components` 显示强对立但窗口/strongest 未显冲突时怎么办？  
修正要求（最小接口补洞）：  
```ts
type RehydrateTrigger =
  | { kind:"POLARITY_TENSION"; axis_id:string; raw_pro:number; raw_con:number; threshold:number }
  | { kind:"RULEBOOK_CHANGED"; from:string; to:string };

function should_rehydrate(state: AxisEvidenceProfile, t: RehydrateTrigger): boolean;
```
**可推翻条件**：若你能证明在 v3 的 `GapSpec(EVIDENCE_CONFLICT)` 定义下，冲突只取决于 strongest/window（给出反例不可构造的证明或覆盖测试集99.9%界），此补洞可撤。

3) **对 Ssyram 质疑我的“规则化幻象”的回应**：你说语义不相容常跨轴、同轴同极性也可能冲突——这是把“命题内容矛盾”与 v3 已裁定的 `EVIDENCE_CONFLICT`（同轴反向）混为一谈。跨轴或同轴同极性的张力应走 `SchemaChallengeNotice(trigger="ANOMALY", is_homologous=true)`，而不是强塞进 evidence 压缩层。  
**可推翻条件**：若你能指出现有 Layer2 已把“定义漂移/口径变更”归类为 `EVIDENCE_CONFLICT`（而非 schema_challenge），则我必须把你要的语义检查纳入 index 的可计算字段或新增 GapKind（但这将触及已裁定分类，需另案）。

---


### [10] Linus Torvalds

*2026-03-10T12:07:04.620558*

行。最终轮就别再“原则性讨论”了，给你一个**能落地、能测、不会把 v3 不变式搞回归**的上下文压缩架构。你要矩阵、接口、兼容性、监控、失败样例和可推翻条件——都给。

如果有人还想靠“LLM 自己会理解”的说辞糊弄压缩语义，那就是在生产系统里祈祷。祈祷不是设计。

---

## 0) 总体架构：ContextStore + 受控注入（Prompt Budgeter）

核心原则：**热路径只喂“下游计算真正需要”的最小充分统计量**；原文进冷存储，靠检索/再水合（rehydrate）按需取回。不要把“提示词越来越大”当成架构。

### 0.1 统一存储抽象（强类型）

```ts
type Tier = "HOT" | "WARM" | "COLD";

interface ArchiveRef {
  key: string;               // content-addressed: blake3(raw_bytes)
  tier: Tier;
  codec: "JSON" | "ZSTD_JSON";
  byte_len: number;
}

interface CompressError {
  kind: "CODEC_FAIL" | "HASH_FAIL" | "INVARIANT_BREAK" | "IO_FAIL";
  detail: string;
}

interface RehydrateError {
  kind: "MISSING_REF" | "IO_FAIL" | "DECODE_FAIL";
  ref: ArchiveRef;
}

interface CompressionPolicy {
  token_budget: number;              // per prompt budget hard cap
  hot_token_budget: number;          // enforced
  warm_token_budget: number;         // optional injection
  cold_retrieval_budget: number;     // max retrieved items
}

interface ContextBundle {
  hot: unknown;     // typed per node, not “string soup”
  warm_refs: ArchiveRef[];
  cold_refs: ArchiveRef[];
}
```

### 0.2 受控注入：每个节点必须声明“需要什么类型”

```ts
interface PromptMaterializer<IHot> {
  estimate_tokens(hot: IHot): number;
  materialize(hot: IHot, warm: unknown[], cold: unknown[]): string;
}
```

任何节点想把“历史全塞进去”，先给我 `IHot` 的类型签名和 `estimate_tokens()`，否则滚。

---

## 1) 爆炸点压缩策略矩阵（8 个点全覆盖）

下面每个爆炸点给：策略、触发条件、语义保留承诺、实现接口。

### 1.1 爆炸点一：Layer1 对话历史（MB/CC prompt）

| 项 | 策略 | 触发条件 | 语义保留承诺 | 接口 |
|---|---|---|---|---|
| CompileError 历史 | **结构化摘要 + 指纹集合**（热区只保错误“类别+触发模式+最小反例”）原文冷存 | `compile_errors_tokens > 4k` 或 `count > 50` | 保证 MB 不重复踩同一类编译失败；允许丢失修辞细节 | `compress_compile_errors()` |
| repair 历史 | **ChallengeTracker 聚合摘要**（按 stage/维度覆盖）+ 原 attempted 列表冷存 | `attempted_scopes_tokens > 4k` 或 `len>200` | 保证“已尝试空间”的覆盖信息可用；不保证逐条列举 | `compress_challenge_tracker()` |
| 最近对话 | **滑动窗口**保留最近 `W=2` epoch 全量 prompt 片段 | epoch 递增 | 保留局部连贯性 | `window_dialogue()` |

接口：

```ts
interface CompileErrorDigest {
  tag: string;                 // CompileError kind
  pattern: string;             // minimal natural language pattern
  count: number;
  exemplars: ArchiveRef[];     // pointers to raw errors
}

function compress_compile_errors(
  errors: CompileError[],
  policy: { max_hot: number }
): Result<{ hot: CompileErrorDigest[]; cold: ArchiveRef[] }, CompressError>;

interface ChallengeAttemptSummary {
  challenge_id: string;
  stage: "STRICT"|"RELAXED"|"ADJACENT"|"EXHAUSTED";
  attempted_scope_hashes: string[];  // stable hashes of scope tokens
  coverage_notes: string;           // short, bounded
  raw_archive?: ArchiveRef;
}

function compress_challenge_tracker(
  tracker: ChallengeTracker,
  policy: { max_attempt_hashes: number }
): Result<ChallengeAttemptSummary, CompressError>;
```

可推翻条件：如果你能构造一个 trace 证明 MB 需要**逐字**看到某次 CompileError 的长文本才能避免重犯（而 digest+exemplar ref 做不到），那就说明 CC 的错误类型系统是垃圾，应该扩展 CompileError 分类而不是靠上下文堆文本。

---

### 1.2 爆炸点二：Layer2 evidence_chain（你们吵最凶的那个）

| 项 | 策略 | 触发条件 | 语义保留承诺 | 接口 |
|---|---|---|---|---|
| evidence_chain | **热区原子窗口 + 冷区“强度分桶计数向量 + exemplars + has_pro/has_con” ledger**；原 atom 冷存可取回 | `atoms_total > 256` 或 `hot_atoms > 64` | 保证：同一 axis 出现 PRO 与 CON 的存在性不会因压缩丢失；规则表变更后可重算 raw_pro/raw_con；可定位强样本用于审计/再水合 | `compress_evidence_chain_v2()` |

这基本是我上一轮的立场，外加一个明确的再水合触发器（Kant 说得对：你必须有可审计的 rehydrate 条件，而不是“应该不会”）。

```ts
type Strength = "ANECDOTAL"|"CORRELATIONAL"|"CAUSAL_STATISTICAL"|"AXIOMATIC";
type StrengthVec = Record<Strength, number>;

interface AxisAggBucketV2 {
  axis_id: string;
  pro_counts: StrengthVec;
  con_counts: StrengthVec;
  has_pro: boolean;
  has_con: boolean;
  top_atoms: EvidenceAtom[];           // bounded, e.g. K=3 per polarity
  covered_epoch_range: [number, number];
  atom_count: number;
  strength_rulebook_version: string;
}

interface EvidenceLedgerV2 {
  claim_id: string;
  hot_atoms: EvidenceAtom[];           // last N, full fidelity
  cold_buckets: AxisAggBucketV2[];     // per axis
  raw_atom_archive?: ArchiveRef;       // full chain compressed
}

function compress_evidence_chain_v2(
  claim_id: string,
  atoms: EvidenceAtom[],
  policy: { max_hot_atoms: number; max_total_atoms: number; top_k: number; rulebook_version: string }
): Result<EvidenceLedgerV2, CompressError>;
```

再水合触发（用数字，不讲玄学）：

```ts
type RehydrateTrigger =
  | { kind:"POLARITY_TENSION"; axis_id:string; raw_pro:number; raw_con:number; threshold:number } // e.g. min(raw_pro,raw_con) >= 2.0
  | { kind:"RULEBOOK_CHANGED"; from:string; to:string };

function should_rehydrate_ledger(
  ledger: EvidenceLedgerV2,
  trig: RehydrateTrigger
): boolean;

function rehydrate_atoms(
  ref: ArchiveRef,
  filter?: { axis_id?: string; epoch_range?: [number,number]; max_atoms?: number }
): Result<EvidenceAtom[], RehydrateError>;
```

可推翻条件：给我一个具体输入 trace，满足：
- 同一 axis 的“冲突”只在冷区的**某两个弱证据**之间出现；
- ledger 的 `has_pro/has_con + counts + top_atoms` 无法触发 `POLARITY_TENSION`，且 rehydrate 不会发生；
- 结果导致 `GapSpec(kind="EVIDENCE_CONFLICT", blocks_termination=true)` 漏报。
如果你能稳定复现这种漏报，我就承认需要把桶维度扩到 axis×(source_class 或 discriminator)。但那是**维度扩展**，不是“别压缩了”。

---

### 1.3 爆炸点三：rejection_history

| 项 | 策略 | 触发条件 | 语义保留承诺 | 接口 |
|---|---|---|---|---|
| fingerprint 集合 | **哈希索引（Set/Bloom + 可选二级集合）**；原草稿冷存仅用于碰撞审计 | `len > 1e6` 或内存阈值 | 保证：去重查询 O(1)；允许极低概率假阳性（若用 Bloom），但必须可检测 | `RejectionIndex` |

别再搞 O(N) 扫描数组。

```ts
interface RejectionIndex {
  exact: Set<string>;          // hot exact
  bloom?: { m: number; k: number; bits: Uint8Array }; // optional warm
  archive?: ArchiveRef;        // cold exact shards
  hash_alg: "BLAKE3_128";
}

function rejection_has(index: RejectionIndex, fp: string): boolean;

function rejection_add(index: RejectionIndex, fp: string): Result<RejectionIndex, CompressError>;
```

碰撞/假阳性监测：当 bloom 命中但 exact 未命中时，记录计数；超过阈值（比如 1e-6 命中率）自动降级为 exact-only 或扩容 bloom。

可推翻条件：如果你能证明 is_homologous() 的 fp 分布导致 bloom 假阳性率在合理 m/k 下仍高到影响探索（例如 >0.1%），那 bloom 别用，直接分片 exact set + on-disk cuckoo hash。

---

### 1.4 爆炸点四：ranking_history

| 项 | 策略 | 触发条件 | 语义保留承诺 | 接口 |
|---|---|---|---|---|
| ranking_history | **滑动窗口 K = max(hysteresis_rounds,2)+1**；其余归档 | 每 epoch | 保证：PA 的 has_ranking_change 与未压缩等价 | `SlidingWindowHistory` |

```ts
interface RankingSnapshot { epoch_id:number; top_k_claim_ids:string[]; scores:Record<string,number>; }

interface SlidingWindowHistory<T> {
  window_size: number;
  active: T[];
  archive?: ArchiveRef;
}

function push_ranking_snapshot(
  h: SlidingWindowHistory<RankingSnapshot>,
  snap: RankingSnapshot
): Result<SlidingWindowHistory<RankingSnapshot>, CompressError>;
```

可推翻条件：如果你修改 PA 终止判定去依赖更久远历史（比如趋势、动量），那是**PA 规格变更**，不是压缩问题；窗口大小跟着规格走。

---

### 1.5 爆炸点五：ChallengeTracker.attempted_scopes

| 项 | 策略 | 触发条件 | 语义保留承诺 | 接口 |
|---|---|---|---|---|
| attempted_scopes/outcomes/polarities | **哈希集合 + 小样本 exemplars + stage 分层保留** | `tokens>4k` 或 `len>200` | 保证：repair 不会重复尝试相同 scope token 集（近似）；保留每阶段少量原文例子用于 LLM 约束 | `ChallengeAttemptSummary`（见上） |

关键点：按 stage 分层，STRICT 的约束更硬，保留更多；ADJACENT 少保留。

可推翻条件：如果 is_homologous() 对 scope 的判定依赖原始自然语言而不是 token 集（Jaccard），那你们自己先把 is_homologous() 修好，因为它“已裁定”就是 token/Jaccard。

---

### 1.6 爆炸点六：L2Return 累积状态

| 项 | 策略 | 触发条件 | 语义保留承诺 | 接口 |
|---|---|---|---|---|
| L2Return 历史 | **全量当前状态（State Snapshot）+ 可选 delta 日志冷存** | 每 epoch | 保证：Layer1 看到的是“当前未解决 gaps/challenges”，不是历史回放；断点恢复可用 cold delta 重建 | `L1WorldState` |

```ts
interface L1WorldState {
  epoch_id: number;
  open_gaps: Map<string, GapSpec>;                // unresolved only
  active_challenges: Map<string, ChallengeTracker>; // non-EXHAUSTED
  last_ranking_delta: { changed:boolean; details?:string };
  archive_log?: ArchiveRef;                       // optional delta log
}

function apply_l2return(
  st: L1WorldState,
  ret: L2Return
): Result<L1WorldState, CompressError>;
```

可推翻条件：如果你能指出 MB 需要“gap 曾经出现又解决”的完整时间序列才能生成新草稿，那 MB 就是在做历史叙事，不是在做搜索；那是另一个产品，不是 v3。

---

### 1.7 爆炸点七：裁判/Judge prompt

| 项 | 策略 | 触发条件 | 语义保留承诺 | 接口 |
|---|---|---|---|---|
| 辩论轮次 | **每轮结构化记录（Claim/Attack/Counterexample/Concession）+ 每 N 轮折叠摘要**；最近 2 轮保留全文 | `total_tokens > budget` | 保证裁判能追踪“谁主张了什么、被什么反驳、是否被承认/推翻”，保留时序索引 | `DebateLedger` |

```ts
interface DebateMove {
  round: number;
  side: "A"|"B";
  claims: string[];
  attacks: { target: string; quote: string; defect: string }[];
  falsifiers: string[];     // explicit “what would refute”
}

interface DebateLedger {
  recent_fulltext: ArchiveRef[];  // last 2 rounds raw
  moves: DebateMove[];            // bounded tokens
  folded_summary?: { up_to_round:number; summary:string; ref:ArchiveRef };
}
```

可推翻条件：如果裁判任务需要逐字引用修辞细节，那你要的不是 judge，是法庭速记员。别混需求。

---

### 1.8 爆炸点八：repair() 内部跨 epoch 上下文

| 项 | 策略 | 触发条件 | 语义保留承诺 | 接口 |
|---|---|---|---|---|
| 已有 TestableClaim[] | **只注入 fingerprint + Top-K 代表性 claim（按 axis 覆盖）**；全文冷存可取回 | `claims_tokens>8k` 或 `len>100` | 保证 repair 生成不会同源（靠 is_homologous fp）；同时给 LLM 少量语义锚点避免胡来 | `select_claim_exemplars()` |

```ts
interface ClaimFingerprint { claim_id:string; fp:string; axis_ids:string[]; polarity?: number; }

function select_claim_exemplars(
  claims: TestableClaim[],
  policy: { max_exemplars: number }
): { exemplars: TestableClaim[]; fps: ClaimFingerprint[] };
```

可推翻条件：如果 is_homologous() 在没有全文 claim 的情况下无法判定同源，那是你们把去重逻辑塞给 LLM 了——直接违规。去重必须是可计算函数，不靠 prompt。

---

## 2) 与 v3 不变式的兼容性论证（INV-5/6、is_homologous 去重、PA 稳定性）

### 2.1 INV-5/INV-6（MB 草稿数量与同源性）

- **INV-5（数量范围）**：压缩不触碰 MB 的 `max_drafts` 逻辑；我们只压历史输入，不改输出上界。实现上，PromptBudgeter 超预算时优先丢 warm/cold 注入，不丢 MB 输出配额。
- **INV-6（无同源草稿）**：关键是 `is_homologous()` 不能依赖被压掉的长文本。我们方案里：
  - 热路径保留 `ClaimFingerprint/RejectionIndex`（哈希集合）用于 O(1) 阻断已探索空间；
  - 对 challenge attempted_scopes 用 scope_token_hashes，仍然对应 is_homologous 的 Jaccard 语义。
  
如果你们的 `is_homologous()` 实现偷偷在用自然语言全文做 embedding 相似度，那你们早就违背“已裁定算法”，别怪压缩。

### 2.2 `is_homologous()` 去重与压缩形状变化

去重所需字段：`provenance_family + scope_tokens + outcome_anchor + polarity + verifier_tokens`。  
压缩策略确保这些要么：
- 仍然在热对象中直接存在（draft/claim 自带）；
- 或以**可重建的 hash/token 集**存在（ChallengeAttemptSummary、RejectionIndex）。

所以去重语义不依赖“历史对话全文”。这就是类型系统的意义：你知道你需要什么。

### 2.3 PA 终止判定连续稳定性（has_ranking_change）

PA 只看最近 `hysteresis_rounds`（默认 2）轮 Top-K + 分数漂移。  
SlidingWindowHistory 保留 `window_size >= hysteresis_rounds+1`，因此 **has_ranking_change(压缩后) == has_ranking_change(未压缩)**，这是字面等价，不是“差不多”。

---

## 3) 压缩监控：运行时检测“语义漂移”（不是靠感觉）

你要能在生产里抓到“压缩导致行为变了”。给你三层监控：确定性、统计性、对照抽查。

### 3.1 确定性监控（不变式 + 影子计数）

```ts
interface DriftSignal {
  kind: "INVARIANT_FAIL" | "REPEAT_RATE_SPIKE" | "CONFLICT_MISS_SUSPECT" | "RANKING_INSTABILITY";
  epoch_id: number;
  metric: string;
  value: number;
  threshold: number;
  detail: string;
}

function check_invariants_after_compress(
  st: L1WorldState,
  drafts: HypothesisDraft[]
): DriftSignal[]; // empty == ok
```

指标（全可计算）：
- `repeat_rate = homologous_filtered / generated`，阈值：相对过去 5 epoch 均值 + 3σ。
- `compile_fail_rate` 同上。
- `conflict_suspect`: 若某 axis `min(raw_pro,raw_con) >= T` 但 gap 集合里没有 `EVIDENCE_CONFLICT`，触发 `CONFLICT_MISS_SUSPECT` 并强制 rehydrate。

### 3.2 再水合哨兵（自动触发，不靠人盯）

- `POLARITY_TENSION`：从 ledger counts 重算 raw_pro/raw_con（按当前 rulebook）：
  - `raw_pro = Σ_s pro_counts[s] * weight(s)`
  - `raw_con = Σ_s con_counts[s] * weight(s)`
  - 触发条件：`min(raw_pro, raw_con) >= 2.0`（数字你可以配，但必须是数字）
- `RULEBOOK_CHANGED`：规则版本变更直接触发 rehydrate 或至少重算。

### 3.3 离线抽查对照（便宜版 A/B）

每 20 个 epoch 抽 1 个 claim，做一次“全量原子链 vs ledger 热+冷”的冲突检测对照：
- 若差异率 > 0.5%（可配），报警并冻结进一步压缩阈值（提高 max_hot 或扩 bucket 维度）。

这就是“如果我错了，实验怎么发现”。

---

## 4) 最可能失败的场景（具体输入）+ 可接受反例

### 4.1 最可能失败：EvidenceAtom 的“折算维度”未来扩展导致 counts 不充分

具体输入（会打爆我们当前桶）：
- 后续你们把 `EvidenceAtom` 扩成：
  - `source_trust_tier: "LOW"|"MED"|"HIGH"`
  - 或 `discriminator_id`
- 并且 rulebook 改成：同 strength 下 HIGH 来源权重大于 LOW，且冲突判定要求“同 discriminator”。

那么现在的 `AxisAggBucketV2(axis only)` 会把不同来源/口径混桶，导致：
- raw_pro/raw_con 可重算但错误；
- `POLARITY_TENSION` 触发也可能失真；
- 冲突漏报或假报。

我接受的反例（能推翻/逼我改桶维度）：
- 给出一条 claim，在同一 axis 上：
  - PRO 证据都来自 LOW（大量相关性），CON 证据来自 HIGH（少量因果）
  - 全量链判定应触发 `EVIDENCE_CONFLICT blocks_termination=true`
  - 但按现有 counts 混桶重算后不触发 tension，且 S4 在未 rehydrate 情况下不产 gap
- 这能稳定复现（不是一次性幻觉）。

修复不是“别压缩”，而是把 bucket 升维：
`AxisAggBucketV3 = axis_id × source_trust_tier`（或 × discriminator）。类型形状变化要明确，别写论文。

### 4.2 另一个失败：Bloom 假阳性误杀探索

如果 rejection_index 用 bloom，给我一个 workload：
- fp 分布高度相关（不是随机）
- bloom 假阳性率实测 > 0.1%，导致 MB/repair 产出大量被“误判已见过”的草稿，覆盖率下降、GapSpec 卡死

反例成立就关 bloom，改 exact 分片集合。工程上这就是 feature flag。

---

## 5) 对对手论点的精确攻击（引用原话，指出缺陷）

### 5.1 打 Ssyram：你那套 O(1) watermarks 是“语义单调性假设”，不在规格里

你写：**“冲突单调性假设：若新证据与弱证据冲突，则必与同轴更强证据冲突”**。

这是典型的“听起来合理”的废话，工程上就是未证明的前提。反例不需要哲学：
- 轴：`productivity`
- 弱证据（ANECDOTAL CON）：某行业远程导致协作崩
- 强证据（CAUSAL_STATISTICAL PRO）：另一行业远程提升产出
它们完全可能“都是真的”，冲突只存在于**特定子人群/口径**，而 watermarks 把它们当“同轴可替代代表”，S4 看水位线会误判为“只是异质性”，从而漏掉 v3 定义的同轴反向冲突门闩。

v3 的 `EVIDENCE_CONFLICT` 定义很粗（同轴反向），你反而更不能做这种投影损失。我的 ledger counts 至少保证“同轴出现过 PRO 和 CON”不会丢，且 tension 触发可强制 rehydrate 去找细节。

**可推翻条件（对我）**：如果你能给出覆盖测试证明：在 v3 当前 `EVIDENCE_CONFLICT` 定义下，仅保留 watermarks（每强度 1 个）在 99.99% 情况下与全量链的冲突判定一致，并且 mismatch 都不影响 blocks_termination（也就是全都属于非阻塞冲突），那我承认 watermarks 可作为 warm 层优化。但你得给数字和测试，不是嘴。

### 5.2 打 Kant（小打一下）：你提的 rehydrate trigger 是对的，但别让它变成无限回读

Kant 的 `should_rehydrate()` 是必要补洞，但如果触发阈值不数字化、或触发后回读不加 `max_atoms` 限制，就会变成“压缩了但每次都回读全量”，那就是自欺欺人。

**可推翻条件（对我）**：如果你们的真实 workload 里 `POLARITY_TENSION` 触发率 > 30% 导致 IO/延迟不可接受，那说明我的触发阈值太低或 bucket 维度不够，需要提高统计充分性来降低回读频率（例如更好的 exemplars 选择），而不是继续堆 prompt。

---

## 6) 总结：这方案“实际上做了什么”

- 把所有历史增长点拆成：**热区最小充分统计量** + **冷区可寻址原文**。
- 用**强类型接口**规定每个节点可获得的历史形状，防止 prompt 变成垃圾堆。
- 对 PA（终止）给出字面等价的滑窗保证；对 MB 去重给 hash/index；对 evidence 冲突给 ledger counts + tension 触发再水合。
- 用运行时 drift 监控 + 抽查对照实验来证明“如果我错了，会被发现”。

你要继续讨论，就拿一个爆炸点（比如 attempted_scopes 或 L2Return delta vs snapshot），给出你打算注入 prompt 的**热对象类型**和 token 上界；否则别浪费时间。

---


### [11] Ssyram

*2026-03-10T12:07:04.620582*

这是最终的系统设计提案。不谈哲学，直接交割架构。

Linus 和 Kant，你们在上一轮的交锋中逼近了真实的工程边界，但你们在爆炸点二（`evidence_chain`）的解法上，犯了同一个致命的类型错误——**你们混淆了「数值计算的充分统计量」和「LLM 模式匹配的语义载体」。**

### 1. 精确攻击与爆炸点二的最终收敛

**引用 Kant**：“冷凝输出改为 counts，而 tally_axis_raw_from_ledger(rulebook_version) 在运行时再折算。”
**引用 Linus**：“必须存按 strength 分桶的计数向量，才能规则表演化后重算。”

**攻击**：你们的 `StrengthCounts` 完美解决了 PA 节点算分时的「规则表演化」问题。但你们忘了 Layer 2 的 S4 节点是怎么工作的。S4 的任务是检测 `EVIDENCE_CONFLICT`。大模型的本质是「提示词引导的概率分布模式匹配搜索」。如果你给 S4 的 prompt 里只有 `pro_counts: { CAUSAL_STATISTICAL: 2 }`，LLM 拿什么去和新来的 Atom 做语义比对？没有具体的命题文本（payload），冲突检测机制直接失效。你们的压缩把 S4 变成了瞎子。

**我的立场与接口（爆炸点二：Watermarked Ledger）**：
数值重算需要 Counts，语义碰撞需要 Watermarks（文本）。两者必须正交组合。这是 `evidence_chain` 的最终压缩形态：

```typescript
type Strength = "ANECDOTAL" | "CORRELATIONAL" | "CAUSAL_STATISTICAL" | "AXIOMATIC";

interface CompressedEvidenceProfile {
  axis_id: string;
  // 满足 Kant/Linus 的 PA 算分与规则重算需求（O(1) 空间）
  counts_pro: Record<Strength, number>;
  counts_con: Record<Strength, number>;
  
  // 满足 S4 的 LLM 语义碰撞需求（O(1) 空间，每种强度最多保留 1 个具体 Atom 的文本）
  watermarks_pro: Record<Strength, EvidenceAtom | null>;
  watermarks_con: Record<Strength, EvidenceAtom | null>;
  
  // 满足 Ssyram 的构成性门闩需求：一旦触发，永久驻留热区，直到被 repair 解决
  pinned_conflicts: GapSpec[]; 
}
```
**触发条件**：无缝实时压缩。每个新 Atom 进来，更新 `counts`，如果 `strength` 槽位为空或新 Atom 的置信度更高，则覆盖 `watermarks`。全量历史异步落盘（仅供人类审计），不进入任何计算节点的内存。
**可推翻条件**：如果能证明存在一种 `EVIDENCE_CONFLICT`，它发生在两个同极性、同强度的历史 Atom 之间，且保留其中任何一个都无法与反向新证据触发冲突，那么单槽位的水位线模型破产，我承认必须保留该强度的全部 Atom 列表。

---

### 2. 完整压缩策略矩阵（爆炸点 1, 3-8）

以下是剩余爆炸点的完整压缩策略。每一个都对应具体的接口和触发条件。

#### 爆炸点一 & 八：Layer 1 对话历史与 repair() 跨 Epoch 上下文
**策略**：负向空间的结构化降维（CompileError 摘要化）。
**接口**：
```typescript
interface NegativeConstraintBox {
  rejected_forms: CategoryErrorTag[]; // 累积被 CC 拒绝的非法形式
  dead_ends: string[]; // 摘要化的失败方向，例如 "Scope too narrow: specific to 2023 Q1"
}
```
**触发条件**：当 MB/repair prompt 中的历史 `CompileError` 超过 3 个时触发，调用 LLM 将具体的错误日志压缩为 `NegativeConstraintBox`。
**语义保留承诺**：LLM 只需要知道「不要踩哪些坑」，不需要知道「上一次踩坑的具体姿势」。

#### 爆炸点三：rejection_history
**策略**：纯语义哈希索引（Bloom Filter + Exact Hash Set）。
**接口**：
```typescript
interface RejectionIndex {
  exact_hashes: Set<string>; // 仅存 fingerprint，丢弃原始 draft
  bloom_filter: Uint8Array;  // 用于 O(1) 预筛
}
```
**触发条件**：草稿被判定为同源的瞬间，立即计算 fingerprint 存入，原文本丢弃。
**语义保留承诺**：`is_homologous()` 本身就是基于 fingerprint 计算的。保存原文本对机器去重没有任何增益。

#### 爆炸点四：ranking_history
**策略**：严格滑动窗口。
**接口**：
```typescript
interface RankingWindow {
  window_size: number; // 绑定 PA 的 hysteresis_rounds（默认 2）
  active_snapshots: RankingSnapshot[]; // length <= window_size
  // 历史直接丢弃，不归档。PA 的马尔可夫性决定了它不需要 t - window_size - 1 的状态。
}
```
**触发条件**：每个 epoch 结束时执行 `active_snapshots.shift()`。
**语义保留承诺**：100% 语义保留。PA 终止判定的数学公式仅依赖当前窗口。

#### 爆炸点五：ChallengeTracker.attempted_scopes
**策略**：边界框投影（Bounding Box Projection）。
**接口**：
```typescript
interface ScopeBoundingBox {
  explored_dimensions: string[]; // 例如 ["geography", "time"]
  boundary_descriptions: string[]; // 例如 ["All US states explored", "Post-2000 explored"]
}
```
**触发条件**：`attempted_scopes` 数组长度 > 5 时，触发 LLM 抽取边界框。
**语义保留承诺**：将离散的尝试点连成面，约束 LLM 不要在这个「面」内生成。

#### 爆炸点六：L2Return 消息
**策略**：状态机增量差分（Delta Patching）。
**接口**：
```typescript
interface L2ReturnDelta {
  epoch_id: number;
  resolved_gap_ids: string[]; // MB 收到后从本地未解决列表中划掉
  new_gaps: GapSpec[];        // MB 收到后追加到本地列表
}
```
**触发条件**：默认启用。Layer 1 维护一个 `ActiveGaps` 状态机，Layer 2 只发送 Delta。
**语义保留承诺**：状态机的最终一致性。MB 永远能看到当前所有 `ActiveGaps` 的全景，而不需要在 prompt 里堆叠历史。

#### 爆炸点七：裁判/Judge 输入
**策略**：Epoch 级论点结构树（AST 化）。
**接口**：
```typescript
interface DebateASTNode {
  epoch: number;
  claim_id: string;
  core_proposition: string;
  verified_status: string;
  defeaters: string[]; // 指向其他 claim_id 的指针
}
```
**触发条件**：在 AS 节点启动前，将所有 `VerifiedClaim` 和 `GapSpec` 转换为 AST 格式，丢弃冗长的辩论原话。
**语义保留承诺**：裁判评判的是「论证的拓扑结构」和「证据的最终强度」，而不是修辞。AST 完美保留了拓扑。

---

### 3. 压缩与 v3 不变式的兼容性论证

**关于 INV-5/6（MB 草稿不变式与同源性）**：
`is_homologous()` 的判定依赖 `provenance_family`、`scope_tokens` 等特征。在爆炸点三的压缩中，我们只保留了基于这些特征计算出的 Hash（fingerprint）。因为判定函数本身就是对特征的确定性映射，比较 Hash 与比较特征是数学等价的。INV-6（不存在两个同源草稿）在 Hash 集合无碰撞的前提下得到 100% 保证。

**关于 PA 终止判定的连续稳定性**：
PA 的 `has_ranking_change()` 逻辑是：`current_top_k == prev_top_k && score_delta < epsilon` 连续发生 `hysteresis_rounds` 次。爆炸点四的滑动窗口大小严格等于 `hysteresis_rounds`。这意味着压缩丢弃的状态在代数上永远不会进入 PA 的计算图。终止判定的正确性被形式化地保留。

---

### 4. 压缩监控方案：语义漂移检测

系统在运行时必须能自证压缩没有破坏认知引擎的寻路能力。我部署两个硬性监控指标：

1. **同源碰撞率衰减（Rejection Rate Decay）**：
   - 机制：监控 MB 产出草稿在 `is_homologous()` 处的拦截率。
   - 报警阈值：如果拦截率在连续 3 个 Epoch 内下降超过 40%，且 `ScopeBoundingBox`（爆炸点五）刚刚被触发过。
   - 含义：说明压缩后的 Bounding Box 丢失了精确的负向约束，导致 LLM 正在生成实际上已被探索过、但伪装成新 scope 的草稿。
2. **幻觉缺口复现（Zombie Gap Recurrence）**：
   - 机制：监控 `L2ReturnDelta` 中 `new_gaps` 的哈希值是否与历史上已被 `resolved_gap_ids` 标记的哈希碰撞。
   - 报警阈值：发生 1 次即报警。
   - 含义：说明 Layer 1 的状态机由于历史上下文丢失，未能把「已解决的问题」固化为前提，导致 Layer 2 重新发现了相同的逻辑缺口。

---

### 5. 失败场景与可推翻条件

**最可能失败的场景（具体输入）**：
输入问题：“量子计算对非对称加密的威胁时间表”。
在 repair() 的 `attempted_scopes` 压缩中（爆炸点五），系统尝试了 "RSA-2048", "ECC-256", "AES-128"。压缩机制将其泛化为 `ScopeBoundingBox: { explored_dimensions: ["encryption_algorithms"], boundary_descriptions: ["Standard asymmetric and symmetric algorithms"] }`。
此时，LLM 被这个过于宽泛的 Bounding Box 阻挡，拒绝生成针对 "NTRU"（一种抗量子格密码）的草稿，因为它认为 "NTRU" 属于 "Standard algorithms" 的语义覆盖区。系统过早收敛，漏掉了关键命题。

**接受推翻的反例（Falsification Condition）**：
如果你能构造出一个真实的 prompt 注入实验：
1. 使用全量 `attempted_scopes` 列表时，LLM 成功生成了某个关键的相邻维度草稿。
2. 使用 `ScopeBoundingBox` 摘要后，LLM 连续 3 次 failed to generate 该草稿。
3. 且该草稿对最终 PA 的 Top-K 排名有决定性影响（改变了最终答案）。

只要给出这个 trace，我立刻承认「结构化摘要替换负向约束」在 Layer 1 是非法的，并将爆炸点一和五的策略回滚为「滑动窗口+硬截断」。

这是我的全盘架构。所有接口已强类型化，所有状态变更已绑定确定的触发器。如果你们没有针对具体 `interface` 字段的修改意见，这个议题可以结案了。

---


### [12] 康德（Immanuel Kant）

*2026-03-10T12:07:04.620663*

下面给出**完整的上下文压缩架构提案**。我将它当作“判断力的工程实现”来审查：每一处压缩都必须先区分——哪些下游操作需要**构成性（konstitutiv）**保持、哪些只是**调节性（regulativ）**辅助手段；否则你会把工程便利僭越成认识论法则。

---

## 0) 总体架构：Context Budget Manager（CBM）+ 分层状态仓库

### 0.1 核心原则（可落地）
- **热区（hot）**：进入 LLM prompt 的最小充分集（为下游不变式服务）。
- **温区（warm）**：内存可取但默认不进 prompt（供确定性算法/检索）。
- **冷区（cold）**：归档（对象存储/磁盘），只通过索引/检索回注（rehydrate）进入 warm/hot。
- **压缩不是“遗忘”**：任何被压缩的对象必须留下**可审计的指纹与可反证的承诺**（否则就是把“待定”伪装成知识状态）。

### 0.2 统一接口（所有爆炸点共用）
```ts
type ExplosionPoint =
  | "L1_DIALOG"
  | "EVIDENCE_CHAIN"
  | "REJECTION_HISTORY"
  | "RANKING_HISTORY"
  | "CHALLENGE_TRACKER"
  | "L2RETURN_STATE"
  | "JUDGE_PROMPT"
  | "REPAIR_CONTEXT";

type CompressionStrategy = "TRUNCATE"|"SUMMARY"|"HASH_INDEX"|"SLIDING_WINDOW"|"ARCHIVE_RETRIEVE";

interface CompressionTrigger {
  kind: "TOKEN_BUDGET"|"EPOCH_INTERVAL"|"INFO_GAIN_LOW"|"ERROR_RATE"|"LATENCY";
  point: ExplosionPoint;
  threshold: number;
  observed: number;
  window?: number;         // for interval / rate
}

interface SemanticContract {
  must_preserve: string[];   // fields / invariants promised preserved
  may_approximate: string[]; // explicitly allowed loss
  drift_tests: DriftTestSpec[];
}

interface DriftTestSpec {
  test_id: string;
  description: string;
  // run-time computable predicate; failure emits DriftAlert
  predicate: (before: any, after: any) => boolean;
  severity: "WARN"|"BLOCK";
}

interface CompressResult<T> {
  hot: T;
  warm_ref?: string;     // pointer to warm store
  cold_ref?: string;     // pointer to archive object
  contract: SemanticContract;
  digest: { blake3: string; item_count: number; epoch_range?: [number,number] };
}

interface IContextCompressor {
  point: ExplosionPoint;
  strategies: CompressionStrategy[];
  should_compress: (t: CompressionTrigger, state: any) => boolean;
  compress: (state: any, now_epoch: number) => Result<CompressResult<any>, "CompressError">;
  rehydrate: (query: any) => Promise<any>;  // deterministic retrieval
}
```

---

## 1) 八个爆炸点：完整“策略矩阵”（策略/触发/语义承诺/接口）

### 1.1 爆炸点一：Layer 1 对话历史（MB/CC prompt）
| 项 | 策略 | 触发条件 | 语义保留承诺 | 实现接口 |
|---|---|---|---|---|
| compile_error_history | SUMMARY + HASH_INDEX + ARCHIVE_RETRIEVE | `TOKEN_BUDGET(L1_DIALOG) > T1` 或 `ERROR_RATE(重复compile_error) > r` | **必须**保留：`CompileError.kind` 分布、导致拒绝的最小反例模板、每类错误最近一次样本；**可丢**：原始长文本 | `compile_error_digest: Map<CompileErrorTag, {template:string, last_epoch:number, count:number, fingerprints:Set<string>}>` |
| repair_history（跨 epoch） | SLIDING_WINDOW + SUMMARY | `attempt_records > N` 或 `TOKEN_BUDGET > T2` | **必须**保留：每个 challenge 的 `current_stage`、`consecutive_filtered_epochs`、已尝试“维度族”覆盖摘要；**可丢**：逐条 attempted 文本 | `RepairHistorySummaryV1`（见 1.5） |
| 草稿池回放（给 MB） | TRUNCATE（只给 Top-M 草稿骨架）+ HASH_INDEX（全量指纹温存） | `drafts_tokens > T3` | **必须**保留：INV-5/6 所需的去重指纹与张力来源配额统计；**可丢**：草稿全文 | `DraftSkeleton {draft_id, tension_source, scope_ref, outcome_anchor?, verifier_hint}` |

**可推翻条件**：若你提供 trace 证明 MB 需要“被拒绝草稿的全文语境”才能避免再次生成（即模板+指纹不足以防重复），则必须把该类拒绝样本升级为 warm 可检索全文并在 MB prompt 注入。

---

### 1.2 爆炸点二：Layer 2 的 evidence_chain（你们争执的中心）
我采纳 Linus 的“可重算统计”要求，并补上我上一轮要求的**再注入触发器**，以避免 Ssyram 那种把经验启发式当构成性保证的混乱。

| 项 | 策略 | 触发条件 | 语义保留承诺 | 实现接口 |
|---|---|---|---|---|
| evidence_chain per claim | 分层 ledger：hot atoms + cold axis-bucket counts + exemplars + archive | `total_atoms > max_total_atoms` 或 `hot_atoms > max_hot_atoms` | **必须**保留：对每轴 `has_pro/has_con`、强度分桶计数（可随 rulebook 重算）、每轴 PRO/CON exemplars（K 个）、覆盖 epoch range；**可丢**：低信息密度原子全文 | `EvidenceLedgerV3`（如下） |
| 冲突检测敏感性 | ARCHIVE_RETRIEVE + 再注入触发器 | 见 `should_rehydrate()` | **必须**保证：若历史出现同轴反向证据，则在 S4 可被检测到（通过 has_pro/has_con + exemplars + rehydrate） | `should_rehydrate()` + `rehydrate_atoms()` |

**EvidenceLedgerV3（形状）**
```ts
type Strength = "ANECDOTAL"|"CORRELATIONAL"|"CAUSAL_STATISTICAL"|"AXIOMATIC";
type StrengthCounts = Record<Strength, number>;

interface AxisBucketV3 {
  axis_id: string;
  pro_counts: StrengthCounts;
  con_counts: StrengthCounts;
  has_pro: boolean;
  has_con: boolean;
  exemplars: { pro: EvidenceAtom[]; con: EvidenceAtom[] }; // size <= K each
  covered_epoch_range: [number, number];
  atom_count: number;
}

interface EvidenceLedgerV3 {
  claim_id: string;
  hot_window: EvidenceAtom[];           // newest H
  buckets: AxisBucketV3[];              // cold summary
  archive_ref: string;                 // pointer to full atoms if stored
  strength_rulebook_version_seen: string;
}
```

**再注入触发器（我要求 Ssyram 必须补的洞）**
```ts
type RehydrateTrigger =
  | { kind:"POLARITY_TENSION"; axis_id:string; raw_pro:number; raw_con:number; threshold:number }
  | { kind:"RULEBOOK_CHANGED"; from:string; to:string }
  | { kind:"CONFLICT_SUSPECTED"; axis_id:string; };

function should_rehydrate(ledger: EvidenceLedgerV3, t: RehydrateTrigger): boolean;

async function rehydrate_atoms(params:{
  claim_id: string;
  axis_id?: string;
  epoch_range?: [number,number];
  limit: number;
}): Promise<EvidenceAtom[]>;
```

**对 Linus 与 Ssyram 的精确攻击（指名+引用）**
- 对 Ssyram：你写“**冲突单调性假设**……弱证据的冲突必然也与强证据冲突”。这是把经验心理学当先验法则；一旦出现“强证据来自不同口径/不同可观测定义”，弱证据冲突反而更敏感。你没有给出可计算的停止/回注条件，因此你的 O(1) 结构是**调节性想法被当作构成性保证**。
- 对 Linus：你说“**同一 axis 上出现相反极性时，可计算、可复现地阻塞终止**”。这里有一个需要先被区分的混乱：阻塞条件是构成性的（blocks_termination），但“相反极性”的判定依赖 evidence 表征；若你只给 counts 而不给 exemplars + rehydrate，你让“相反极性”变成纯计数符号游戏，遇到 hash/归档缺失时无法审计其来源。故我坚持 buckets+exemplars+rehydrate 三件套。

**可推翻条件**：若你能给出形式化证明：`EVIDENCE_CONFLICT` 的检测只依赖 `has_pro/has_con`（不依赖 exemplars/来源），且 repair 所需的 `evidence_summary` 可由 counts 构造且足以驱动修复成功率不降，则可删去 exemplars 与 rehydrate。

---

### 1.3 爆炸点三：rejection_history（负向空间）
| 项 | 策略 | 触发条件 | 语义保留承诺 | 实现接口 |
|---|---|---|---|---|
| fingerprint 集合 | HASH_INDEX（热：Bloom/Set；冷：分片归档） | `N_fingerprints > N1` 或 `is_homologous latency > L1` | **必须**保留：去重判定的“曾见过”二值语义；**允许**：极小概率误报（需可侦测） | `RejectionIndexV2` |
| 原始草稿内容 | ARCHIVE_RETRIEVE（仅审计/碰撞回查） | 总是 cold | **必须**保留：fingerprint→draft_id 的溯源；不进入在线判断 | `rejection_archive_ref` |

```ts
interface RejectionIndexV2 {
  hot_set: Set<string>;                 // recent
  warm_bloom: { bits: Uint8Array; k: number; n: number }; // probabilistic
  cold_shards: string[];                // archive refs
  collision_audit: { sample_rate: number; last_audit_epoch: number };
}
```

**可推翻条件**：若运行时检测到 Bloom 误报导致 MB 生成空间被异常压缩（coverage 长期下降且 repair 进入 EXHAUSTED 上升），必须回退为确定性 Set + 分片哈希表（牺牲内存换语义正确性）。

---

### 1.4 爆炸点四：ranking_history（PA 稳定性）
| 项 | 策略 | 触发条件 | 语义保留承诺 | 实现接口 |
|---|---|---|---|---|
| PA 在线判定 | SLIDING_WINDOW | 永远启用，窗口 = `max(hysteresis_rounds,2)+1` | **必须**保留：`has_ranking_change()` 所需最近窗口；**可丢**：更早快照 | `RankingWindow` |
| 审计与续跑 | ARCHIVE_RETRIEVE + SUMMARY | `archive_size > A1` | **必须**保留：epoch→TopK 的可追溯；**可丢**：每轮所有分数细节（可统计化） | `RankingArchiveSummaryV1` |

```ts
interface RankingWindow {
  window: RankingSnapshot[]; // length <= W
  archive_ref?: string;
}
```

**可推翻条件**：若你允许运行时修改 `hysteresis_rounds` 并要求“继承旧历史窗口”参与判定，则必须保证 archive 可随机访问回填，否则终止判定将出现不连续（见 2.3）。

---

### 1.5 爆炸点五：ChallengeTracker.attempted_scopes
| 项 | 策略 | 触发条件 | 语义保留承诺 | 实现接口 |
|---|---|---|---|---|
| attempted_* 列表 | SUMMARY + HASH_INDEX（每 stage 独立）+ TRUNCATE | `len(attempted_scopes) > N2` 或 prompt 超限 | **必须**保留：在同一 challenge 内避免重复尝试的语义；**可丢**：逐条原文 | `ChallengeMemoryV2` |
| EXHAUSTED | ARCHIVE_RETRIEVE | stage==EXHAUSTED | **必须**保留：为何耗尽（统计摘要+最后样本） | `ChallengeArchiveRecord` |

```ts
interface AttemptDigest {
  stage: "STRICT"|"RELAXED"|"ADJACENT";
  scope_fps: Set<string>;
  outcome_fps: Set<string>;
  polarity_seq_tail: (1|-1|0)[];
  coverage_summary: string; // LLM-readable but bounded
  last_examples: {scope:string; outcome:string}[]; // small K
}
interface ChallengeMemoryV2 {
  challenge_id: string;
  current_stage: "STRICT"|"RELAXED"|"ADJACENT"|"EXHAUSTED";
  consecutive_filtered_epochs: number;
  digests: AttemptDigest[];
}
```

**可推翻条件**：如果你给出具体输入使得 repair 需要“完整 attempted_scopes 原文细节”才能产生非同源草稿（指纹+覆盖摘要不足），则把该 challenge 的 attempted_scopes 升级为 warm 可检索，并在 repair prompt 按相似度取 Top-R 原文回注。

---

### 1.6 爆炸点六：L2Return 累积状态（不是历史回放）
| 项 | 策略 | 触发条件 | 语义保留承诺 | 实现接口 |
|---|---|---|---|---|
| gap/challenge 累积 | “全量当前状态”+ 变更日志归档 | `gaps_total > G1` 或 `token > T4` | **必须**保留：当前未解决 gap 集合（供 MB/repair 查询）；**可丢**：每轮完整 L2Return | `GapStateStore` + `DeltaLogArchive` |

```ts
interface GapStateStore {
  open_gaps: Map<string, GapSpec>;              // authoritative
  open_challenges: Map<string, SchemaChallengeNotice>;
  delta_log_ref?: string;                      // cold
}
```

**对对手论点的攻击（引用 Ssyram）**  
Ssyram 在上轮承认“repair 断链因为拿不到 evidence_summary”。同理：若你用纯 delta 且允许丢包/重启，你会把“状态”降格为“回忆”。所以我要求**当前状态是构成性存储**（authoritative map），delta 只是审计性的（调节性）附属。

**可推翻条件**：若系统保证单机不丢消息、且永不续跑/重启，则可取消全量 state store，仅用 delta；但这等于把工程偶然性当先验条件，我不接受其作为 v3 规范默认。

---

### 1.7 爆炸点七：裁判/Judge prompt
| 项 | 策略 | 触发条件 | 语义保留承诺 | 实现接口 |
|---|---|---|---|---|
| 多轮辩论内容 | SUMMARY（结构化争点表）+ SLIDING_WINDOW（最近 2 轮原文）+ ARCHIVE | `rounds > R1` 或 `tokens > T5` | **必须**保留：论点-反驳关系、证据强度归类、未决争点列表、时序锚点（哪轮提出） | `DebateDigestV2` |

```ts
interface DebateDigestV2 {
  issue_graph: { issue_id:string; claim_ids:string[]; pro:string[]; con:string[]; unresolved:string[] }[];
  round_index: { round:number; key_moves:string[]; links:{from:string; to:string; kind:"ATTACK"|"SUPPORT"}[] }[];
  last_full_rounds: { round:number; transcript:string }[]; // size=2
  archive_ref: string;
}
```

**可推翻条件**：如果裁判任务包含“逐字判定是否存在承诺/撤回/自相矛盾”，则必须保留更长原文窗口；结构摘要不足以支持字面承诺审计。

---

### 1.8 爆炸点八：repair() 内部跨 epoch 上下文（claims + rejections 注入）
| 项 | 策略 | 触发条件 | 语义保留承诺 | 实现接口 |
|---|---|---|---|---|
| 已有 TestableClaim 列表 | HASH_INDEX（fingerprints）+ 检索回注（Top similar） | `claims_tokens > T6` | **必须**保留：避免生成同源草稿（服务 INV-6 与 is_homologous 前置约束）；**可丢**：全部 claim 原文 | `ClaimIndexV1` |
| rejection_history 注入 | 不注入全文，只注入“负例模板+指纹统计” | `prompt budget tight` | **必须**保留：避免重复方向；**可丢**：逐条 rejected 原文 | `NegativePromptPackV1` |

```ts
interface ClaimIndexV1 {
  fp_set: Set<string>;
  vector_index_ref?: string; // for semantic retrieve of top-R claims
}

async function build_repair_prompt(ctx:{
  gap: GapSpec;
  challenge?: SchemaChallengeNotice;
  challenge_mem: ChallengeMemoryV2;
  claim_index: ClaimIndexV1;
  rejection_index: RejectionIndexV2;
  prompt_budget: number;
}): Promise<string>;
```

**可推翻条件**：若你证明 repair 在 ADJACENT 阶段必须看“完整 claim 的 assumptions/non_claim”才能避免同源（仅 fingerprint 不够），则必须把这些字段加入索引可检索回注的最小片段，而不是扩大默认 prompt。

---

## 2) 与 v3 不变式的兼容性论证（聚焦 INV-5/6、is_homologous 去重、PA 终止连续稳定）

### 2.1 INV-5/INV-6（MB 草稿不变式）
- **INV-5（drafts.length 有界且非空）**：压缩不改变 MB 的输出长度约束；压缩只作用于“历史上下文注入”，不作用于 `HypothesisDraft[]` 产出类型本身。
- **INV-6（无同源草稿）**：关键在于 `is_homologous()` 所需的输入不被压缩损坏。我的方案把同源避免分两层：
  1) **生成前约束**：repair/MB prompt 只注入 fingerprints + 代表性负例模板（调节性）。
  2) **生成后裁决**：真正构成性的去重仍由已裁定的 `is_homologous()` 算法执行，且其所需字段来自草稿本体与 rejection/claim fingerprint 集合（HASH_INDEX 语义等价于“曾见过”判断）。

**可推翻条件**：若 `is_homologous()` 未来被修改为需要访问“被拒绝草稿全文语义片段”（不只 fingerprint），则 HASH_INDEX 不再等价，必须引入 warm 检索全文回注以完成判定。

### 2.2 is_homologous=true 禁止触发广度引擎（同源张力约束）
压缩后仍保持：当 `SchemaChallengeNotice.is_homologous=true`，repair 的策略不得通过“扩维增加新轴”解决，而是在既有 schema 内重综合。为此我把 ChallengeMemory 的摘要限制为“同一维度族覆盖/未覆盖”，不引入新轴描述，从接口层面避免把“摘要写作”变成偷偷扩维。

**可推翻条件**：若你能构造输入证明：不引入新维度无法解除同源冲突，而系统又不允许 schema_challenge 升格（已裁定），则该先验约束自身需要修订；但这属于架构裁定变更，不在本轮压缩层内解决。

### 2.3 PA 终止判定的连续稳定性（has_ranking_change + blocks_termination）
- ranking_history 用 **滑动窗口**：因为 PA 的构成性判定只依赖最近 `hysteresis_rounds`，故归档旧快照不影响正确性。
- GapSpec 的 `blocks_termination` 必须来自**当前状态 store**（1.6），不可只靠 LLM 回忆或摘要推断。我的方案把 gap 状态做成 authoritative map，因此压缩不会让终止判定“跳变”。

**可推翻条件**：若系统允许“续跑后继承旧 ranking window”并且窗口大小变更，则必须能从 archive 回填并重算；否则会出现你所谓“连续稳定性”破坏（同一输入因窗口不足而提前终止）。

---

## 3) 压缩监控：运行时检测“压缩引入语义漂移”

我不接受“错误率上升再说”的经验主义偷懒；必须有**在线可检**的漂移指标，至少对构成性门闩（去重、阻塞终止）给出硬监控。

### 3.1 漂移告警类型（DriftAlert）
```ts
type DriftAlert =
 | { kind:"DEDUP_REGRESSION"; point:"REJECTION_HISTORY"; epoch:number; duplicate_rate:number; baseline:number }
 | { kind:"CONFLICT_SENSITIVITY_DROP"; point:"EVIDENCE_CHAIN"; axis_id:string; epoch:number; rehydrate_missed:boolean }
 | { kind:"PROMPT_CONSTRAINT_LEAK"; point:"CHALLENGE_TRACKER"; challenge_id:string; epoch:number; repeat_attempt_detected:boolean }
 | { kind:"TERMINATION_DISCONTINUITY"; point:"RANKING_HISTORY"; epoch:number; window_mismatch:boolean };
```

### 3.2 三个具体在线测试（每轮跑，成本可控）
1) **去重回归测试（DEDUP_REGRESSION）**  
   - 统计：`is_homologous()` 命中率、生成后被过滤比例、以及“重复 compile_error kind”比例。  
   - 若压缩后重复率显著上升（相对过去 W 轮 z-score 超阈值），触发：增加 warm 检索注入或扩大 hot_set。

2) **冲突敏感性下降测试（CONFLICT_SENSITIVITY_DROP）**  
   - 当 buckets 显示 `has_pro && has_con` 但 S4 未产出 `EVIDENCE_CONFLICT` 且 `raw_pro/raw_con` 都高时，触发 `should_rehydrate(POLARITY_TENSION)`，并比较 rehydrate 前后是否产生冲突 gap；若“rehydrate 后才出现冲突”，则记一次“压缩漏检险情”。

3) **终止不连续测试（TERMINATION_DISCONTINUITY）**  
   - 在 PA 判定 terminate=true 前，执行一次“窗口扩 1 的影子计算”（只在内存，不改状态）。若影子计算显示 changed=true 或 blocks gap 仍存在，则 BLOCK 并发出告警（说明压缩/窗口配置导致判定不稳）。

**可推翻条件**：若你能证明这些在线测试在现实负载下不可承受（延迟/成本超 SLA），则需明确削减为离线审计；但同时必须接受一个结论：系统不再对构成性门闩提供运行时保证，只剩调节性信心区间。

---

## 4) 最可能失败的场景（给具体输入）与可接受反例

### 4.1 失败场景 A：冲突依赖“来源口径”，但 EvidenceAtom 缺少该字段
**输入构造**：同一 axis（例如“生产力提升”）上  
- 早期 CON：`CAUSAL_STATISTICAL`，来源为“自报问卷”；  
- 后期 PRO：`CAUSAL_STATISTICAL`，来源为“工时日志”；  
两者在 counts/exemplars 层面看似同强度对立，但真正冲突取决于“可观测定义不一致”。现行 v3 把这类问题应归入 schema_challenge（ANOMALY），但如果实现里误把它当 `EVIDENCE_CONFLICT`，则压缩层无法正确表达“口径差异”，rehydrate 也未必能修复，因为字段根本不存在。

**推翻条件（可接受反例）**：给出一条 trace：在不改 v3 已裁定分类的前提下，系统必须在 `EVIDENCE_CONFLICT` 里区分来源口径才能正确阻塞/修复；这将迫使我们承认 evidence 压缩桶维度（axis×strength）不充分，必须扩维（加入 source_class 或 discriminator）。

### 4.2 失败场景 B：Bloom 误报导致探索空间被错误封闭
**输入构造**：大量相似但非同源草稿（高密度同义改写），fingerprint 设计又过短，Bloom 误报叠加哈希碰撞，使 repair 长期产出被“曾见过”拒绝，最终挑战进入 EXHAUSTED，coverage 无法提升。

**推翻条件**：出现可复现的“coverage 停滞 + EXHAUSTED 激增 + rejection 命中异常高”，且审计抽样证明存在误报/碰撞，则必须禁用 Bloom（或提高指纹强度/使用确定性分片表）。

### 4.3 失败场景 C：Judge 摘要丢失“字面承诺”导致裁决错误
**输入构造**：辩手在第 3 轮明确撤回第 1 轮的主张，但摘要只保留“核心分歧”未保留撤回行为，裁判因此判定其自相矛盾或仍坚持原主张。

**推翻条件**：若裁判任务包含承诺审计，则必须把“言语行为”（assert/retract/qualify）纳入 DebateDigest 的结构字段，而不仅是主题摘要。

---

## 5) 我对上一轮对手论点的最终裁决式质询（必须回应的缺陷）

- **对 Linus（引用）**：你说“不是让 LLM 去理解何为真正矛盾”。同意其反神秘化；但你把“可计算”误当作“充分”。没有 exemplars+rehydrate，你的 counts 只能给出“存在对立”而无法给出可审计的 `evidence_summary` 来驱动 repair（你自己也承认 repair 需要链路）。  
  **可推翻条件**：证明 repair 的 `evidence_summary` 可由 counts 机械生成并同样有效（成功修复率不降）。

- **对 Ssyram（引用）**：你以“冲突单调性假设”支撑 O(1) 水位线，这是典型的把经验倾向僭越成先验法则。你必须给出 `should_rehydrate()` 之类的**反向精化触发器**，否则你的“固定槽位”只是把未知压扁成沉默。  
  **可推翻条件**：给出覆盖测试与不可构造反例论证，证明水位线足以覆盖 v3 的冲突定义；否则必须接受分层 ledger + rehydrate。

---

以上方案的目标不是“尽量省 token”，而是：在不触犯 v3 已裁定的不变式与终止条件前提下，把压缩限定为**调节性工具**，并为每一次可能的语义损失提供可计算的反证入口。你若要推翻它，不需要辩论“更好看”的哲学句子；只需给出我列出的那类具体 trace，使某一条语义承诺在运行时被打破即可。

---


### [13] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-10T12:10:07.402369*



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

---
