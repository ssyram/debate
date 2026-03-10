# v3 认知引擎：上下文压缩续跑——五个未裁定点 裁判总结

> 2026-03-10T12:28:26.064208

# 裁判裁定书

## 裁定点 A：L2Return 是否是独立爆炸点？

### 结论
**此点不成立为独立爆炸点。** L2Return 必须是严格增量事件（EpochDelta），L1 通过状态存储吸收，禁止历史拼接进 prompt。但须保留可回溯引用接口以支持审计。

### 关键分歧与取舍
三位辩手在"L2Return 必须是增量"这一点上罕见地完全一致（Linus 的 `EpochDelta`、Ssyram 的 `Event<EpochDelta>`、Kant 的 `gap_delta.opened/updated/closed`）。真正的分歧在两处：

**分歧一：增量的去重语义。** Linus 在交叉质询中精确指出 Ssyram 的初始定义缺失 `GAP_UPDATE/RESOLVED` 事件类型，导致 L1 无法区分"新 gap"与"同 gap 的精化"，最终退化为 concat。Ssyram 在后续轮次未直接回应此质询（其注意力转向了 D 点的 AST 哈希重构）。Kant 的接口在初始轮次即区分了 `opened/updated/closed`，结构最完整。**裁判采纳 Linus 的 ADT 化事件类型（tagged union）+ Kant 的三态生命周期语义。**

**分歧二：过程史是否需要进 prompt。** Kant 提出"可追责性需要过程证据"（如：为什么某 gap 被 SUSPENDED 而非继续 repair），认为 Linus 将"不注入历史"从调节性策略僭越为构成性原则。Linus 反驳：可追责要的是"可回溯引用"而非"prompt 内历史"。**裁判裁定 Linus 正确**——审计需求通过 `archive_ref: string` 式的外部引用满足，不构成"历史必须进 prompt"的理由。但 Kant 的质疑揭示了一个真实需求：必须保留回溯接口。

### 具体规格

```typescript
type GapId = string;

// 事件类型：tagged union（采纳 Linus 结构 + Kant 生命周期）
type EpochDelta =
  | { kind: "GAP_OPEN"; gap: GapSpec }
  | { kind: "GAP_PATCH"; gap_id: GapId; patch: JsonPatch }  // RFC 6902
  | { kind: "GAP_CLOSE"; gap_id: GapId; resolution: "RESOLVED" | "SUSPENDED" | "MERGED" | "INVALIDATED" }
  | { kind: "SCHEMA_CHALLENGE_NEW"; ch: SchemaChallengeNotice }
  | { kind: "CLAIM_VERIFIED"; claim: VerifiedClaim }
  | { kind: "CLAIM_SUSPENDED"; claim_id: string; reason: string };

interface L2Return {
  epoch_id: number;
  deltas: EpochDelta[];
  size_bytes: number;  // L1 可拒收/报警
}

// L1 状态吸收（纯函数）
function applyDelta(s: L1State, d: EpochDelta): Result<L1State, ApplyError>;

// 审计回溯接口（不进 prompt，仅供外部查询）
interface EpochArchive {
  get_deltas_by_epoch(epoch_id: number): EpochDelta[];
  get_gap_history(gap_id: GapId): EpochDelta[];
}
```

**触发条件：** 单个 L2Return 的 `size_bytes > 32KB` 或 `deltas.length > 200` 时，L1 拒收并要求 L2 做 epoch 内合并（同一 gap_id 的连续 PATCH 折叠为单次 PATCH）。此阈值来自 Linus 对"事件风暴"的质询——Ssyram 的"单 epoch >4000 tokens"阈值无法捕获大量微更新的结构性失败。

**失败行为：** L1 拒收后返回 `{ rejected: true, reason: "EPOCH_TOO_LARGE", hint: "COALESCE_PATCHES" }`，L2 必须合并后重发。

### 可推翻条件
如果存在裁判规则或下游消费者需要在 prompt 内引用"某 gap 从 OPEN 到 CLOSE 的完整演变过程"（而非仅引用当前状态），则需重新评估是否允许有限的过程注入（限定为特定 gap_id 的事件切片，非全量历史）。

---

## 裁定点 B：rejection_history 的上限保护

### 结论
**此点是真实问题，但严重程度被高估。** 核心风险不是内存（Ssyram 正确），而是 Linus 指出的"超限后系统行为语义变化"和"DoS 面"。需要分层淘汰策略和明确的降级语义。

### 关键分歧与取舍
**Ssyram** 将此点斥为"无病呻吟"（"10万条32字节哈希=3.2MB，直接忽略"）。**Linus** 反驳：(1) 内存估算过于粗糙（忽略 HashSet 实际开销），(2) 关键问题不是内存而是"超限后系统做什么"——不淘汰则成 DoS 面，淘汰则改变语义。**Kant** 提出冷热分区 + Bloom Filter 方案，但被 Ssyram 质询"Bloom Filter 无法语义匹配"。Kant 回应：冷区索引的是 `is_homologous()` 产出的指纹而非原始文本哈希，因此 exact match 足够。

**裁判取舍：**
- Ssyram 的"假问题"判断不成立——Linus 的 DoS/语义退化论据是有效的。
- Kant 的冷热分区在架构上正确，其"冷区只存 fingerprint"的澄清回应了 Ssyram 的质询。
- Linus 的 `HOT_FULL_DROP` 降级策略实用，但 Kant 正确指出：不记录指纹会改变后续探索路径，这是语义变化而非仅性能退化。

### 具体规格

```typescript
type FP = string; // blake3-256 hex，由 is_homologous() 的稳定特征生成

interface RejectionStore {
  // 热区：内存 HashSet
  hot: Set<FP>;  // max 50_000 entries
  
  // 冷区：磁盘/外部索引，exact fingerprint match
  cold: { has(fp: FP): Promise<boolean> };
  
  // 写入
  record(fp: FP): void;  // 先写 hot，hot 满则 LRU 淘汰到 cold
  
  // 查询：先 hot 再 cold
  has(fp: FP): Promise<boolean>;
}

// 降级策略
interface RejectionStoreConfig {
  hot_max: 50_000;
  cold_max: 500_000;
  
  // cold 写入失败时的降级
  cold_write_failure_policy: "HOT_ONLY";  // 不写 cold，但必须发 metric
  
  // cold 查询失败时的降级
  cold_read_failure_policy: "TREAT_AS_MISS";  // 当作未见过，可能重复探索
}
```

**触发条件：** `hot.size >= 50_000` 触发 LRU 淘汰到冷区；`cold.size >= 500_000` 触发最旧条目丢弃。

**失败行为：** 
- 冷区写入失败：降级为仅热区，发出 `metric: "rejection_cold_write_fail"`。**此降级必须标记为语义退化**（采纳 Kant 的论点：不记录指纹确实改变后续搜索空间），日志级别 WARN 而非 INFO。
- 冷区读取失败：视为 miss，允许重复探索，发出 metric。
- 任何降级发生时，当前 epoch 的 L2Return 中须包含 `{ kind: "REJECTION_STORE_DEGRADED", detail: string }`，使上层可感知。

### 可推翻条件
如果 Kant 的指纹生成方案（`is_homologous()` 产出的 fp）被证明不稳定（即语义相同的草稿产出不同 fp），则冷区退化为虚设，必须替换为 LSH/向量索引，且需满足 `p95_latency < 50ms`。

---

## 裁定点 C：裁判 prompt 的压缩策略

### 结论
**此点是真实问题。** 采纳 Kant 的 IssueTable 结构化压缩方案，但必须加上 Ssyram 质询所揭示的双轨校验机制，以解决"压缩阶段信息丢失不可审计"的问题。

### 关键分歧与取舍
**Kant** 提出 IssueTable（结构化争点表）压缩早期轮次，包含 `positions`、`key_attacks`、`falsifiers`、`quotes`。**Ssyram** 发起关键质询：IssueTable 由 LLM 生成，压缩过程本身可能丢失关键 falsifier，且裁判自检无法发现**压缩阶段**的信息丢失（"用 LLM 审计 LLM"的循环依赖）。**Linus** 未深入此点。

**Kant 的回应**（第 9 轮）提出了双轨校验：(1) 每行至少 2 条原文引用（`span_hash` 可重算命中），(2) 引用未命中则回滚为保留更多原文轮次。

**裁判取舍：**
- Ssyram 的质询完全成立：LLM 生成的 IssueTable 不可盲信。
- Kant 的双轨校验是有效补救，但需要增强：不仅检查"引用是否存在"，还需检查"每个待裁定点是否被覆盖"。
- 最终方案：IssueTable + 机械校验 + 失败回滚。

### 具体规格

```typescript
interface IssueTableRow {
  issue_id: "A" | "B" | "C" | "D" | "E";
  quotes: {
    turn_id: number;
    speaker: string;
    span_hash: string;   // blake3 of exact substring
    text: string;         // exact substring from original
  }[];  // min 2 per row
  positions: Record<string, string>;  // speaker -> one-sentence position
  key_attacks: string[];
  falsifiers: string[];
}

// 机械校验（纯函数，不经过 LLM）
interface IssueTableValidator {
  validate(table: IssueTableRow[], original_turns: Turn[]): ValidationResult;
}

type ValidationResult =
  | { ok: true }
  | { ok: false; errors: ValidationError[] };

type ValidationError =
  | { kind: "QUOTE_NOT_FOUND"; issue_id: string; span_hash: string }
  | { kind: "TOO_FEW_QUOTES"; issue_id: string; count: number }
  | { kind: "UNCOVERED_ISSUE"; issue_id: string }  // 某待裁定点无对应行
  | { kind: "SPEAKER_MISSING"; issue_id: string; speaker: string };  // 某辩手立场未被记录
```

**触发条件：** 裁判 prompt 总 token 数超过 `JUDGE_PROMPT_MAX = 12000 tokens` 时，对第 `current_turn - 4` 轮及更早的轮次执行压缩。

**失败行为：**
1. IssueTable 校验失败（任何 `ValidationError`）→ 回滚：`JUDGE_MAX_FULL_TURNS` 从 4 增至 6，保留更多原文。
2. 回滚后仍超 token 限制 → 按 Ssyram 建议的最坏情况处理：截断最早轮次但保留所有辩手的"可推翻条件"句段（通过正则匹配 `"可推翻条件"` 关键词定位）。
3. 压缩 LLM 生成幻觉引用（`span_hash` 无法在原文中重算命中）→ 丢弃该行，用原文替代，发出 `metric: "issue_table_hallucination"`。

### 可推翻条件
如果在实际运行中，IssueTable 校验通过但裁判仍做出与原文证据矛盾的裁定（即"断章取义但哈希命中"的情况），则需要增加：引用上下文窗口扩展（quote 前后各 100 字符一并保留）或引入第二个独立 LLM 做交叉校验。

---

## 裁定点 D：repair() LLM 上下文的压缩策略

### 结论
**此点是最关键的真实问题。** 绝对禁止自然语言摘要。采纳 Ssyram 的 AST 哈希负向约束方案（经 Linus 质询后重构的版本），辅以 Linus 的水印保留机制。

### 关键分歧与取舍
**核心共识：** 三位辩手均同意禁止自然语言摘要（Ssyram："最厌恶权重由 LLM 决定且不可审计"；Linus："不是宣言，给我能跑的签名"；Kant 也同意结构化）。

**分歧一：约束的表示形式。** 
- Ssyram 初始版本用 `excluded_paths: string[]`（自然语言路径描述），被 Linus 正确质询为"拼写漂移导致静默失效"。
- Ssyram 修正版本改为 AST 哈希 + JSON Pointer（`RFC6901_Ptr` + `BLAKE3 hash`），用纯函数 `is_unsat()` 做硬拦截。
- Linus 提出 16 字节 `ScopeFp`（结构指纹）+ 水印保留机制。

**裁判取舍：** Ssyram 的修正版本（AST 哈希 + JSON Pointer）比 Linus 的 `ScopeFp` 更精确——JSON Pointer 指向具体节点，而不是整体指纹，允许更细粒度的约束。但 Linus 的水印机制（`watermarks = 8`）解决了 prompt 中"如何向 LLM 示例失败模式"的问题，两者互补。

**分歧二：压缩触发阈值。** Linus 提出 `attempts > 24` 时触发压缩。Ssyram 提出"连续 5 次被 `is_unsat` 拦截"时退入 Suspended。这是两个不同的阈值，分别控制不同的事件。

### 具体规格

```typescript
type RFC6901_Ptr = string;  // JSON Pointer
type ASTHash = string;       // BLAKE3

interface NegativeConstraint {
  target_gap_id: string;
  attempt_epoch: number;
  stage: "STRICT" | "RELAXED" | "ADJACENT";
  signatures: { ptr: RFC6901_Ptr; banned_hash: ASTHash }[];
}

// 纯函数拦截（不经过 LLM）
function is_unsat(draft: Draft, constraints: NegativeConstraint[]): boolean {
  return constraints.some(c =>
    c.signatures.every(s =>
      hash_ast(json_pointer_get(draft, s.ptr)) === s.banned_hash
    )
  );
}

// Prompt 注入的压缩形式（采纳 Linus 的水印机制）
interface AttemptedScopesForPrompt {
  total_attempts: number;
  constraint_count: number;
  // 最近 N 个失败的具体示例，供 LLM 理解"不要做什么"
  watermarks: {
    ptr: RFC6901_Ptr;
    banned_hash: ASTHash;
    human_readable_hint: string;  // 由确定性模板生成，非 LLM
  }[];
  archive_ref: string;  // 完整约束集的外部引用
}

interface AttemptedScopesConfig {
  // 压缩触发：单个 gap 的尝试次数超过此值
  compress_threshold: 24;
  // prompt 中保留的水印数量
  max_watermarks: 8;
  // 连续被 is_unsat 拦截次数超过此值 → Suspended
  consecutive_unsat_limit: 5;
}
```

**触发条件：**
1. 单个 gap 的 `attempts > 24` → 压缩：仅保留 `max_watermarks = 8` 个水印示例进 prompt，完整约束集由 `is_unsat()` 在 L2 验证前硬拦截。
2. LLM 连续 5 次生成的 draft 被 `is_unsat()` 拦截 → 该 gap 进入 `S7(Suspended)`，原因标记为 `CONSTRAINT_SPACE_EXHAUSTED`。

**失败行为：**
- `is_unsat()` 为纯函数，不存在 LLM 依赖的失败模式。
- 如果 `json_pointer_get` 因 draft 结构不匹配而返回 undefined → 该约束不匹配（安全侧：放行），但发出 `metric: "constraint_pointer_miss"`。高频出现此 metric 说明约束的 JSON Pointer 需要更新。

### 可推翻条件
如果离线回放显示：(1) 水印去重后重复提案率仍 >15%（Linus 的阈值），或 (2) LLM 通过微小的结构重命名（不改变语义但改变 AST 哈希）绕过 `is_unsat()` 拦截，则需要在 AST 哈希之上增加语义归一化层（如：先 canonicalize JSON 再哈希），或引入 LSH 做模糊匹配。

---

## 裁定点 E：Active Challenge 的轮转注入策略

### 结论
**此点是真实问题。** 采纳 Linus 的"blocking challenge 永不轮出"规则，辅以 Kant 的注入预算控制，并加入 Ssyram 质询所揭示的单调性保护。

### 关键分歧与取舍
**Linus** 提出核心规则：`blocks_termination = true` 的 challenge 永久钉在 prompt 中，不参与轮转。非 blocking 的 challenge 按优先级轮转，限制注入数量。

**Ssyram** 质询 Kant：轮转注入可能破坏 CEGAR 循环的单调性——如果 challenge X 在第 N 轮被轮出，第 N+1 轮的 repair 可能生成一个满足 X 的方案但违反了已轮出的 Y，导致震荡。

**Kant** 回应（第 9 轮）提出：轮出的 challenge 不是被遗忘，而是被编译为 `NegativeConstraint` 保留在约束集中——即"轮出 prompt 但不轮出验证"。这是关键的架构洞见。

**裁判取舍：** Kant 的"轮出 prompt 但不轮出验证"原则正确，与 D 点的 `is_unsat()` 机制天然整合。Linus 的"blocking 永不轮出"是必要的底线规则。

### 具体规格

```typescript
interface ChallengeInjectionConfig {
  // Blocking challenge：永不轮出 prompt
  blocking_always_injected: true;
  
  // 非 blocking challenge 的 prompt 注入预算
  non_blocking_max_in_prompt: 3;
  
  // 轮转策略：优先级排序后取 top-N
  rotation_priority: (c: Challenge) => number;
  // 优先级因子：age（越老越高）、repair_failure_count（越多越高）、severity
}

// 关键规则：轮出 prompt ≠ 轮出验证
interface ChallengeRotationPolicy {
  // 在 prompt 中的 challenge：LLM 可见，引导修复
  in_prompt: Challenge[];  // blocking + top-N non-blocking
  
  // 不在 prompt 中但仍参与验证的 challenge
  // 编译为 NegativeConstraint，由 is_unsat() 硬拦截
  out_of_prompt_but_validated: Challenge[];
  
  // 验证流程：draft 必须通过 ALL challenge 的验证，不仅是 prompt 中的
  validate(draft: Draft): { 
    passed: Challenge[]; 
    failed: Challenge[];  // 包括 out_of_prompt 的
  };
}
```

**触发条件：** 当活跃 challenge 总数超过 `non_blocking_max_in_prompt + blocking 数量` 时启动轮转。

**失败行为：**
- Draft 被 `out_of_prompt_but_validated` 中的 challenge 拒绝 → L2 将该 challenge 提升到下一轮的 `in_prompt` 中（自动优先级提升），确保 LLM 在下一轮可见此约束。
- 如果同一 challenge 连续 3 次从 `out_of_prompt` 拒绝 draft → 永久提升为 `in_prompt`（类 blocking 待遇），并压缩其他低优先级 challenge。
- 如果 `in_prompt` 总 token 超过预算（`CHALLENGE_PROMPT_BUDGET = 4000 tokens`）→ 按 Linus 的水印机制，最低优先级的非 blocking challenge 压缩为单行摘要 + `archive_ref`。

### 可推翻条件
如果在实际运行中出现"challenge A 和 B 交替拒绝 draft"的震荡模式（连续 6 轮交替失败），说明约束集存在内在矛盾（unsatisfiable），此时应触发元级诊断：暂停 repair，报告 `CONSTRAINT_CONFLICT` 给 L1，由人工或更高层级仲裁。

---

## 优先级排序（按实现紧迫性）

| 优先级 | 裁定点 | 理由 |
|--------|--------|------|
| **P0** | **D（repair 压缩策略）** | 三位辩手一致认为最关键；直接影响系统核心循环的收敛性；`is_unsat()` 纯函数是 E 点的前置依赖 |
| **P1** | **A（L2Return 增量语义）** | 接口基础设施，所有其他点的数据流依赖于此；且三方共识最强，实现风险最低 |
| **P2** | **E（Challenge 轮转）** | 依赖 D 点的 `NegativeConstraint` 机制；直接影响多 challenge 场景下的系统行为；Ssyram 的震荡风险质询表明需尽早落地 |
| **P3** | **B（rejection_history 上限）** | 真实问题但不紧急；短期内用 `hot_max = 50_000` 的简单 HashSet 即可运行，冷区可延后实现 |
| **P4** | **C（裁判 prompt 压缩）** | 真实问题但仅在辩论轮次较多时触发；IssueTable + 校验机制较复杂，可在系统稳定运行后迭代 |