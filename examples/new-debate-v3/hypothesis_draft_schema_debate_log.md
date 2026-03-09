# v3 认知引擎：HypothesisDraft 接口的统一规范 辩论日志

> 2026-03-09T19:01:40.230067

---


### [1] Linus Torvalds

*2026-03-09T18:53:39.130408*

我选 **A：必须统一成同一个 `HypothesisDraft` 类型**。不是“公共基类 + 两个花哨子类”，不是“union 让 CC 自己猜”。**同一个流水线位置、同一个消费者集合、同一个 `is_homologous()` 入口，就该有同一个规范化数据类型。**

你现在这个状态，本质上是 API 事故：

- MB draft 有 `problem_id` / `open_term_risk` / `ttl` / `tension_source.tier`
- repair draft 没有
- repair 的 `verifier_hint` 还是 `string`
- MB 的 `verifier_hint` 是 `string[]`

这不是“来源不同所以结构不同”。这是**下游被迫承担上游懒惰**。

---

# 立场

## 裁定
- **A1 统一类型**，但不是“所有字段按需可选”这种烂方案。
- 我主张：**统一为一个规范化的、可直接被 CC 和同源性判定消费的单一 `HypothesisDraft`**。
- 来源差异放进 `provenance` 和少量语义字段里，**不要污染主接口**。
- CC 和 `is_homologous()` **不得因为 draft 来源不同而写分支逻辑**。

可推翻条件：

> 如果你能给出一个 `CC.compile()` 和一个跨来源 `is_homologous(a, b)` 的接口定义，证明它们在 `MBDraft | RepairDraft` 下**完全不需要**类型判断、不需要字段存在性补丁、不需要默认值注入，那我的统一类型方案就可以被推翻。

我先说结论：你做不到。因为现在字段根本不齐。

---

# 1. 完整 TypeScript 类型定义

下面是我给的**统一后完整类型**。注意：我不是把字段全做成 optional 来掩盖设计失败。**凡是 CC 或同源性判定要直接消费的字段，一律必填且类型统一。**

```typescript
type DraftSource = "MB" | "REPAIR";

type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT"
  | "GAP_REPAIR"
  | "SCHEMA_REPAIR"
  | "OTHER";

type TensionTier =
  | "INTERNAL_AXIS"
  | "EMPIRICAL"
  | "STRUCTURAL"
  | "UNSPECIFIED";

interface TensionSource {
  kind: TensionKind;
  tier: TensionTier;
  evidence_ref: string[];   // 统一为数组；repair 没有时给 []
  note: string;             // 统一承载 MB.note 或 repair.detail
}

interface DraftProvenance {
  source: DraftSource;

  // 通用溯源
  epoch: number;

  // MB 来源
  mb_candidate_id?: string;

  // repair 来源
  source_gap_id?: string;
  source_challenge_id?: string;
  repair_stage?: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
}

interface HypothesisDraft {
  // identity
  draft_id: string;
  problem_id: string;

  // core payload consumed by CC / homology
  claim_sketch: string;
  scope_ref: string[];          // 必填，统一后 MB 也必须产出
  verifier_hint: string[];      // 必填，统一数组语义
  open_term_risk: string[];     // 必填，没有就 []

  tension_source: TensionSource;

  // lifecycle
  ttl: number;                  // 必填；repair 也有明确存活周期

  // source metadata
  provenance: DraftProvenance;
}
```

---

## 相关函数签名

### CC
CC 不该知道来源，只消费统一 draft。

```typescript
interface QuestionFrame {
  problem_id: string;
  question_text: string;
}

type CompileResult =
  | { kind: "TESTABLE_CLAIM"; claim_id: string }
  | { kind: "REGULATIVE_IDEA"; idea_id: string }
  | { kind: "COMPILE_ERROR"; error_code: string; message: string };

function clarity_compile(
  draft: HypothesisDraft,
  frame: QuestionFrame,
  opts?: { strict_scope?: boolean }
): CompileResult;
```

### 同源性判定
统一入口，跨来源比较无分支。

```typescript
interface HomologyFeatures {
  scope_tokens: string[];
  verifier_tokens: string[];
  claim_embedding_key: string; // 指向缓存 embedding 的 key
  tension_kind: TensionKind;
  open_term_tokens: string[];
}

interface HomologyResult {
  is_homologous: boolean;
  score: number;
  reasons: string[];
}

function extract_homology_features(draft: HypothesisDraft): HomologyFeatures;

function is_homologous(
  candidate: HypothesisDraft,
  existing_pool: readonly HypothesisDraft[]
): HomologyResult;
```

### 统一的规范化构造器
真正的关键不是类型声明，而是**保证 MB / repair 输出落到统一规范**。

```typescript
interface MBRawDraft {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  tension_source: {
    kind: "EXTERNAL_POSITION" | "STAKEHOLDER_CONFLICT" | "EVALUATION_AXIS_SPLIT";
    tier: "INTERNAL_AXIS" | "EMPIRICAL";
    evidence_ref: string[];
    note: string;
  };
  verifier_hint: string[];
  open_term_risk: string[];
  ttl: number;
  scope_ref?: string[]; // 旧接口里没有，允许 raw 层缺省
}

interface RepairRawDraft {
  draft_id: string;
  scope_ref: string[];
  tension_source: { kind: string; detail: string };
  claim_sketch: string;
  verifier_hint: string;
  provenance: {
    source_gap_id?: string;
    source_challenge_id?: string;
    repair_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
    epoch: number;
  };
  problem_id?: string;
  ttl?: number;
  open_term_risk?: string[];
}

function normalize_mb_draft(raw: MBRawDraft, epoch: number): HypothesisDraft {
  return {
    draft_id: raw.draft_id,
    problem_id: raw.problem_id,
    claim_sketch: raw.claim_sketch,
    scope_ref: raw.scope_ref ?? [],
    verifier_hint: raw.verifier_hint,
    open_term_risk: raw.open_term_risk,
    tension_source: {
      kind: raw.tension_source.kind,
      tier: raw.tension_source.tier,
      evidence_ref: raw.tension_source.evidence_ref,
      note: raw.tension_source.note,
    },
    ttl: raw.ttl,
    provenance: {
      source: "MB",
      epoch,
    },
  };
}

function normalize_repair_draft(raw: RepairRawDraft, problem_id: string): HypothesisDraft {
  return {
    draft_id: raw.draft_id,
    problem_id: raw.problem_id ?? problem_id,
    claim_sketch: raw.claim_sketch,
    scope_ref: raw.scope_ref,
    verifier_hint: [raw.verifier_hint], // 统一为数组
    open_term_risk: raw.open_term_risk ?? [],
    tension_source: {
      kind: (
        raw.tension_source.kind === "GAP_REPAIR" ||
        raw.tension_source.kind === "SCHEMA_REPAIR"
          ? raw.tension_source.kind
          : "OTHER"
      ),
      tier: "STRUCTURAL",
      evidence_ref: [],
      note: raw.tension_source.detail,
    },
    ttl: raw.ttl ?? 1,
    provenance: {
      source: "REPAIR",
      epoch: raw.provenance.epoch,
      source_gap_id: raw.provenance.source_gap_id,
      source_challenge_id: raw.provenance.source_challenge_id,
      repair_stage: raw.provenance.repair_stage,
    },
  };
}
```

---

# 2. 最强支撑论据

## 核心论据
**CC 和 `is_homologous()` 都是“语义消费者”，不是“来源鉴别器”。**
如果它们要分辨 MB / repair，说明你把规范化责任推给下游了。那就是架构脏了。

### 为什么统一类型是必须的
因为目前这四个字段已经足够证明 union/subtype 会把分支逻辑扩散到全系统：

1. `verifier_hint: string[]` vs `string`
2. `scope_ref` 缺失
3. `tension_source` 结构不兼容
4. `problem_id` 缺失

你只要让 CC 接收 `MBDraft | RepairDraft`，那 CC 内部就至少会变成这种垃圾：

```typescript
function clarity_compile(draft: MBDraft | RepairDraft, frame: QuestionFrame): CompileResult {
  const verifierHints = Array.isArray(draft.verifier_hint)
    ? draft.verifier_hint
    : [draft.verifier_hint];

  const scopeRef = "scope_ref" in draft ? draft.scope_ref : infer_scope_from_claim(draft.claim_sketch);

  const tensionTier =
    "tier" in draft.tension_source ? draft.tension_source.tier : "UNSPECIFIED";

  // ...
}
```

这就是**来源分支渗透到编译器内部**。你已经输了。

---

## 边界场景：CC 处理 repair 草稿，但 frame 的 scope 抽取严格模式开启

假设输入：

```typescript
const repairDraft: HypothesisDraft = {
  draft_id: "d-17",
  problem_id: "p-1",
  claim_sketch: "In low-income districts, raising bus frequency improves job retention by reducing lateness.",
  scope_ref: ["low-income districts", "bus frequency", "job retention"],
  verifier_hint: ["difference-in-differences on route frequency shocks"],
  open_term_risk: ["improves"],
  tension_source: {
    kind: "GAP_REPAIR",
    tier: "STRUCTURAL",
    evidence_ref: [],
    note: "fills missing transport-access mechanism",
  },
  ttl: 1,
  provenance: {
    source: "REPAIR",
    epoch: 3,
    source_gap_id: "gap-22",
    repair_stage: "STRICT",
  },
};
```

### 我的方案怎么处理
CC 只看统一字段：

```typescript
clarity_compile(repairDraft, frame, { strict_scope: true })
```

- `scope_ref` 已存在：直接提取 scope
- `verifier_hint` 是数组：直接生成 accept tests
- `tension_source.note` 可用于 falsifier 合成
- `problem_id` 存在：可校验 frame 关联
- 无需任何来源判断

### 竞争方案怎么失败
如果你坚持子类型：

```typescript
type Draft = MBDraft | RepairDraft;
```

MB 没 `scope_ref`，repair 有；repair `verifier_hint` 是 string，MB 是 string[]。那 CC 必须：
- 先判断来源或字段存在性
- 再做适配
- 再处理 compile

这意味着 CC 不是 compile，CC 成了 **compile + normalize + source-dispatch**。职责已经烂掉了。

---

## 第二个边界场景：跨来源同源判定

一个 MB draft：

```typescript
{
  draft_id: "mb-1",
  problem_id: "p-1",
  claim_sketch: "Increasing bus frequency in underserved urban areas improves access to employment.",
  scope_ref: ["underserved urban areas", "bus frequency", "employment access"],
  verifier_hint: ["transit natural experiment", "commute-time panel"],
  open_term_risk: ["improves", "access"],
  tension_source: {
    kind: "STAKEHOLDER_CONFLICT",
    tier: "EMPIRICAL",
    evidence_ref: ["src-1"],
    note: "mobility policy disagreement"
  },
  ttl: 2,
  provenance: { source: "MB", epoch: 0 }
}
```

一个 repair draft：

```typescript
{
  draft_id: "rb-9",
  problem_id: "p-1",
  claim_sketch: "Higher bus frequency in low-income neighborhoods reduces commute delays and improves job retention.",
  scope_ref: ["low-income neighborhoods", "bus frequency", "job retention"],
  verifier_hint: ["difference-in-differences on route upgrades"],
  open_term_risk: ["improves"],
  tension_source: {
    kind: "GAP_REPAIR",
    tier: "STRUCTURAL",
    evidence_ref: [],
    note: "repair for missing mechanism"
  },
  ttl: 1,
  provenance: { source: "REPAIR", epoch: 2, source_gap_id: "gap-9", repair_stage: "STRICT" }
}
```

统一接口下，`extract_homology_features()` 可以稳定抽取：
- scope token
- verifier token
- claim embedding
- open term token
- tension kind

而不是先问“你是哪种 draft”。

---

# 3. 已知弱点及缓解措施

## 弱点 1：repair 的 `ttl` 语义不天然
对，repair draft 的生命周期原本更多受 stage/epoch 控制，不是天然 TTL 模型。

### 缓解
别装纯洁。**统一生命周期字段就是值得的。**
规定：
- `ttl` 表示“允许在 L1 池中继续被 CC / RB 复用的剩余 epoch 数”
- repair 默认 `ttl = 1`
- 若某些 repair 需跨轮保留，可显式增加

这比“repair 没 ttl，所以某些池管理逻辑得特殊判断”强一万倍。

可推翻条件：
> 如果系统中没有任何草稿池淘汰逻辑需要统一处理，且 MB/repair 生命周期绝不会共用管理器，那么 `ttl` 统一的价值会下降。

但你当前是共用 HypothesisDraft 池进 CC 的，别做梦了。

---

## 弱点 2：`tension_source.tier` 对 repair 有点勉强
是的。repair 不是天然从 question-level epistemic tier 生成的。

### 缓解
引入扩展枚举：
- MB 常用：`INTERNAL_AXIS | EMPIRICAL`
- repair 常用：`STRUCTURAL`
- 无法判定时：`UNSPECIFIED`

这比两种不同对象结构强。因为下游要的是**稳定 schema**，不是你上游生成历史的诗意保真。

---

## 弱点 3：MB 原始上游没有 `scope_ref`
没错。这意味着统一类型会**倒逼 MB 规范升级**。

### 缓解
MB 必须二选一：
1. 直接产出 `scope_ref`
2. 在 normalize 阶段通过 `claim_sketch + frame` 推导 `scope_ref`

我偏向 1。因为 CC 明确需要它，继续缺失就是把责任甩锅给 CC。

---

# 4. 对对手立场的预攻击

我先打最可能的对手：**A2 子类型方案**，也就是“定义 `MBDraft | RepairDraft`，CC 接受 union type”。

对手通常会说：

> “两种草稿本质不同，所以应该保留各自专有字段；CC 只消费公共字段，额外字段留在各自分支。”

这话听着文雅，实际上是偷懒。

## 精确攻击
请对手给出下面这两个签名的**完整可运行定义**：

```typescript
function clarity_compile(
  draft: MBDraft | RepairDraft,
  frame: QuestionFrame
): CompileResult;
```

以及

```typescript
function is_homologous(
  candidate: MBDraft | RepairDraft,
  existing_pool: readonly (MBDraft | RepairDraft)[]
): HomologyResult;
```

然后证明：

1. **CC 内部不需要**
   - `Array.isArray(draft.verifier_hint)`
   - `'scope_ref' in draft`
   - `'tier' in draft.tension_source`
   - `'problem_id' in draft`

2. **同源性抽取不需要**
   - 对 MB 和 repair 走不同 feature extraction 分支

你如果做不到，那你的“子类型保真”就是在**把 source-dispatch 成本转嫁给所有消费者**。

这不是抽象，是污染。

---

# 5. 为什么我没选 D 作为第一关键点

D 当然重要，两个 homologous 实现也应该收敛。但那是第二刀。

**第一刀必须先砍类型统一。**
因为在类型没统一之前谈共用实现，纯属空谈。你连输入对象都不一致，怎么证明一个统一同源性函数不会到处写 guard？

顺序必须是：

1. 统一 `HypothesisDraft`
2. 再统一 `extract_homology_features()`
3. 最后决定 semantic similarity 和 Jaccard 是一个函数的两个子评分，还是两个不同策略

先把对象 schema 修好，再谈算法。别本末倒置。

---

# 最终结论

**我支持 A1，但不是“可选字段大杂烩版 A1”，而是“规范化强制统一版 A1”。**

核心裁定：

- `HypothesisDraft` 必须是单一类型
- `claim_sketch` / `scope_ref` / `verifier_hint` / `tension_source` / `problem_id` / `ttl` / `provenance` 全部统一
- `verifier_hint` 统一为 `string[]`
- `tension_source` 统一为 `{ kind, tier, evidence_ref, note }`
- repair 和 MB 的来源差异只能体现在 `provenance` 和字段取值，不得体现在对象结构分叉
- CC 和 `is_homologous()` 必须接收统一类型，且不得按来源写分支

可推翻条件再说一遍：

> 如果有人能给出 union/subtype 方案下的 `clarity_compile()` 与跨来源 `is_homologous()` 完整接口和伪实现，并证明内部零来源分支、零类型 guard、零字段补丁，那我的统一类型主张可以被推翻。

我判断：推不翻。因为现在的问题根本不是“本质不同”，而是**接口设计烂了**。

---


### [2] Ssyram

*2026-03-09T18:53:39.130434*

作为一个具有 CEGAR 和形式化验证背景的系统设计者，我将直接切入本次架构危机的核心：**类型系统的坍塌与语义的混用**。

我选择同时回答 **问题A/C（类型定义）** 与 **问题D（同源性计算）**，因为它们本质上是同一个问题：**如何为不同生命周期、不同目标的实体定义一个 Sound（可靠）的公共契约。**

### 一、 核心立场：采用协议/接口方案（A3），拒绝大杂烩式的统一类型（A1）

强行将 MB 和 repair 的草稿揉进一个包含大量 `?`（可选字段）的单一类型，是典型的类型系统反模式（Anti-pattern）。MB 和 repair 处于 Layer 1 状态机的不同阶段，其携带的元数据有着完全不同的代数结构。

**我的主张**：定义严格的 `HypothesisDraftBase` 作为 CC 和 `is_homologous` 的唯一输入契约。MB 和 repair 通过子类型扩展各自的元数据。

#### 1. 完整的 TypeScript 类型定义

```typescript
// 1. 核心契约：CC 和 is_homologous() 唯一关心的公共投影
interface HypothesisDraftBase {
  draft_id: string;
  claim_sketch: string;
  scope_ref: string[];             // MB 必须在产出时初始化（可为空数组），Repair 必填
  verifier_hint: string[];         // 统一为数组。Repair 的单 string 必须包装为 [string]
  tension_source: {
    kind: string;                  // 允许外部枚举扩展
    detail: string;                // MB 的 note 映射到此处，Repair 保持 detail
  };
}

// 2. MB 专属子类型：携带发散期的探索元数据
interface MBDraft extends HypothesisDraftBase {
  source_type: "MB";
  problem_id: string;              // 溯源到 QuestionFrame
  tension_source: {
    kind: "EXTERNAL_POSITION" | "STAKEHOLDER_CONFLICT" | "EVALUATION_AXIS_SPLIT";
    detail: string;
    tier: "INTERNAL_AXIS" | "EMPIRICAL"; 
    evidence_ref: string[];
  };
  open_term_risk: string[];        // 仅在初始发散期有意义，后续由 CC 消化
  ttl: number;                     // MB 草稿的自然衰减周期
}

// 3. Repair 专属子类型：携带 CEGAR 回路的反馈元数据
interface RepairDraft extends HypothesisDraftBase {
  source_type: "REPAIR";
  provenance: {
    source_gap_id?: string;
    source_challenge_id?: string;
    repair_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
    epoch: number;                 // 替代 ttl。Repair 草稿的生命周期由 L1 epoch 推进，无 ttl 概念
  };
}

// CC 的签名：只依赖 Base，遵循依赖倒置原则
function clarity_compile(draft: HypothesisDraftBase, frame: QuestionFrame): CompileResult;
```

#### 2. 对问题 D 的立场：策略模式解耦，拒绝强行共用实现

`compute_semantic_similarity()`（基于 Embedding）和基于 Jaccard 的 `is_homologous()` 绝不能合并为同一个底层实现。
- **MB 阶段**是从无限的解空间中做**多样性采样（Diversity Sampling）**，需要语义距离。
- **Repair 阶段**是针对具体 Gap 的**反例排除（Deduplication）**，需要结构同构性（Isomorphism）检测。

```python
# is_homologous 的签名设计：统一接口，策略分离
class HomologyStrategy(Protocol):
    def check(self, candidate: HypothesisDraftBase, pool: List[HypothesisDraftBase]) -> bool: ...

class SemanticDiversityStrategy(HomologyStrategy):
    # 内部调用 compute_semantic_similarity
    pass

class StructuralJaccardStrategy(HomologyStrategy):
    # 内部提取 scope/outcome/verifier 等特征做 Jaccard
    pass

def is_homologous(candidate: HypothesisDraftBase, pool: List[HypothesisDraftBase], strategy: HomologyStrategy) -> HomologyResult:
    return strategy.check(candidate, pool)
```

### 二、 最强支撑论据与边界场景

**边界场景：跨来源草稿池的去重碰撞**
假设系统运行到 Epoch 2，草稿池中同时存在：
1. `draft_M` (MB 产出，携带 `ttl: 2`, `open_term_risk: ["AI"]`)
2. `draft_R` (Repair 产出，试图修复 Gap1，携带 `provenance: {epoch: 2}`)

此时新的 Repair 产出了 `draft_R2`，调用 `is_homologous(draft_R2, pool)` 进行查重。

- **在我的 A3 方案下**：`is_homologous` 只提取 `HypothesisDraftBase` 的 `scope_ref` 和 `tension_source` 等公共字段进行 Jaccard 比较。它完全不在乎 `draft_M` 没有 `provenance`，也不在乎 `draft_R` 没有 `ttl`，因为多态保证了契约的对齐。
- **在竞争方案（A1 统一类型或 A2 Union 类型）下**：如果使用 Union Type，`is_homologous` 内部必须写出极其丑陋的 `if ('provenance' in e)` 来决定如何提取特征；如果使用全可选的统一类型，特征提取函数在访问 `e.open_term_risk` 时会遭遇 `undefined`，导致 Jaccard 集合计算抛出异常，或者将 `undefined` 错误地计入特征哈希中，导致同源性误判。

### 三、 预攻击：针对方案 A1（统一类型）的倡导者

我在此直接质问任何试图主张**方案 A1（合并所有字段为单一类型，按需可选）**的对手。

你们的方案必然会导致形如 `ttl?: number` 和 `provenance?: Provenance` 的定义。请回答：
1. **语义污染**：如果在统一类型中保留 `ttl`，一个 repair 草稿的 `ttl` 字段应该填什么？Repair 草稿的生命周期由 `ChallengeTracker.stage` 状态机严格管理（已裁定），赋予它一个 `ttl` 毫无物理意义。
2. **状态不可判**：如果 `provenance` 是可选的，当 CC 收到一个没有 `provenance` 且没有 `open_term_risk` 的草稿时，这是一个 MB 草稿（但碰巧没有 open term），还是一个丢失了溯源信息的损坏的 Repair 草稿？你们的方案摧毁了数据的可证性。

不要用“为了方便下游不用写类型判断”来掩饰设计的懒惰，下游（CC）本来就不该看到它不需要的字段。

### 四、 已知弱点及缓解措施

- **已知弱点**：MB 节点在组装 `MBDraft` 时，必须额外做一次映射（比如把 `note` 映射给 Base 的 `detail`，强制初始化 `scope_ref: []`），这增加了 MB 节点的构建样板代码。
- **缓解措施**：在 Layer 1 提供 `DraftFactory.create_mb_draft()` 和 `DraftFactory.create_repair_draft()` 工厂函数，将这些字段对齐的脏活封装在工厂层，保证流入管道的实例严格符合 Base 契约。

### 五、 可推翻条件（Falsifiability）

我的设计基于一个核心假设：**CC（ClarityCompiler）在编译草稿时，其核心 AST 生成逻辑不需要区分该草稿是来自 MB 还是 Repair。**

如果对手能举出一个具体的、不可绕过的例子，证明 CC 在处理 `claim_sketch` 时，**必须**依赖 MB 的 `open_term_risk` 或 Repair 的 `repair_stage` 才能正确生成 `TestableClaim`（即多态被打破），那么我的 `HypothesisDraftBase` 抽象就是无效的，我将收回 A3 方案并承认 CC 必须接收 Union Type 并进行显式分支处理。

---


### [3] 康德（Immanuel Kant）

*2026-03-09T18:53:39.130446*

**立场：我选择 A。MB 与 repair 不应产出同一个“全可选” `HypothesisDraft`；应保留为两个独立子类型，并以一个受约束的公共协议供 CC 消费。**

原因很简单：**来源差异不是偶然元数据，而是草稿的认识论生成条件。**  
MB 草稿是从 `QuestionFrame` 内部张力中先验地产生的候选命题；repair 草稿是由 L2 失败反馈倒逼出来的补充命题。若在接口层把它们压平为“一个字段大合集、很多字段可空”，你得到的不是统一，而是**概念混乱的伪统一**：字段名存在，但对某些实例没有真语义，仅有占位值。此乃最危险之处。

我因此主张：

1. **生产侧**：保留 `MBDraft` 与 `RepairDraft` 两个判别联合成员；
2. **消费侧**：定义一个 `CompilableDraft` 协议，只暴露 CC 真正有权读取的字段；
3. **关系计算侧**：`is_homologous()` 接受 `HypothesisDraft` 联合类型，但先抽取标准化 `HomologyFeatures`，比较的是“是否探索同一知识空间”，不是字段同构；
4. **D 问题预裁定**：`compute_semantic_similarity()` 与 `is_homologous()` 不应共用实现，只能共用底层某些特征提取工具；前者是多样性优化，后者是知识空间同一性判断。

---

## 1. 完整 TypeScript 类型定义

### 1.1 生产侧：保留来源判别

```typescript
type DraftId = string;
type ProblemId = string;
type GapId = string;
type ChallengeId = string;
type Epoch = number;

type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT"
  | "GAP_REPAIR"
  | "SCHEMA_REPAIR";

type EpistemicTier =
  | "INTERNAL_AXIS"
  | "EMPIRICAL"
  | "L2_FAILURE";

interface BaseDraft {
  draft_id: DraftId;
  claim_sketch: string;
}

/**
 * MB 草稿：来自 QuestionFrame 张力分析
 */
interface MBDraft extends BaseDraft {
  source_type: "MB";

  problem_id: ProblemId;

  tension_source: {
    kind: "EXTERNAL_POSITION" | "STAKEHOLDER_CONFLICT" | "EVALUATION_AXIS_SPLIT";
    tier: "INTERNAL_AXIS" | "EMPIRICAL";
    evidence_ref: string[];
    note: string;
  };

  /**
   * MB 阶段应补足 scope_ref；若尚未抽出，可为空数组，但字段必须存在。
   * 因为 CC 对 scope 的读取是合法需求，不应依赖“字段不存在”。
   */
  scope_ref: string[];

  verifier_hint: string[];
  open_term_risk: string[];

  /**
   * 仅 MB 使用：广度池中的生存期控制。
   */
  ttl: number;

  provenance: {
    origin: "QUESTION_FRAME";
    frame_ref: ProblemId;
    tension_candidate_id?: string;
    epoch: Epoch;
  };
}

/**
 * repair 草稿：来自 L2 失败反馈
 */
interface RepairDraft extends BaseDraft {
  source_type: "REPAIR";

  /**
   * repair 也必须绑定 problem_id，否则跨 epoch / 跨问题池比较会失去边界。
   */
  problem_id: ProblemId;

  scope_ref: string[];

  tension_source: {
    kind: "GAP_REPAIR" | "SCHEMA_REPAIR";
    tier: "L2_FAILURE";
    evidence_ref: string[];
    note: string;
  };

  /**
   * 统一为 string[]；单字符串是窄化写法，不应成为接口事实。
   */
  verifier_hint: string[];

  /**
   * repair 同样可能引入开放术语；若未检测到，则为空数组，而非字段缺失。
   */
  open_term_risk: string[];

  provenance: {
    origin: "L2_RETURN";
    source_gap_id?: GapId;
    source_challenge_id?: ChallengeId;
    repair_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
    epoch: Epoch;
  };

  /**
   * repair 不使用 ttl，故不应名义存在。
   * 若你把 ttl?: number 放进统一类型，就是制造“语义空洞字段”。
   */
}

/**
 * 生产系统中的总联合类型
 */
type HypothesisDraft = MBDraft | RepairDraft;
```

---

### 1.2 CC 消费侧：只读取可编译协议，而非全部来源字段

```typescript
/**
 * CC 真正需要的最小充分接口
 */
interface CompilableDraft {
  draft_id: DraftId;
  problem_id: ProblemId;
  claim_sketch: string;
  scope_ref: string[];
  verifier_hint: string[];
  tension_source: {
    kind: TensionKind;
    tier: EpistemicTier;
    evidence_ref: string[];
    note: string;
  };
  open_term_risk: string[];
}

type CompileOptions = {
  strict_scope?: boolean;
};

type CompileResult =
  | { kind: "TESTABLE_CLAIM"; claim_id: string }
  | { kind: "REGULATIVE_IDEA"; reason: string }
  | { kind: "COMPILE_ERROR"; error_code: string; message: string };

function clarity_compile(
  draft: CompilableDraft,
  frame: QuestionFrame,
  opts?: CompileOptions
): CompileResult;
```

注意：`clarity_compile()` **不需要知道** 草稿来自 MB 还是 repair。  
这不是因为两者“本质相同”，而是因为 **CC 的合法职权仅限于编译语义结构**。它消费协议，不消费来源学。

---

### 1.3 同源性判断：接收联合类型，比较标准化特征

```typescript
interface HomologyFeatures {
  problem_id: ProblemId;
  scope_tokens: string[];
  outcome_tokens: string[];
  polarity_tokens: string[];
  verifier_tokens: string[];
  semantic_text: string;
  source_type: "MB" | "REPAIR";
}

interface HomologyResult {
  is_homologous: boolean;
  confidence: number;
  reasons: string[];
  matched_draft_id?: DraftId;
}

interface GapIndex {
  // 省略具体索引结构
}

function extract_homology_features(
  draft: HypothesisDraft,
  gapIndex: GapIndex
): HomologyFeatures;

function is_homologous(
  candidate: HypothesisDraft,
  existing_pool: HypothesisDraft[],
  gapIndex: GapIndex
): HomologyResult;
```

参考伪代码：

```python
def is_homologous(candidate, existing_pool, gap_index):
    cand = extract_homology_features(candidate, gap_index)

    for e in existing_pool:
        other = extract_homology_features(e, gap_index)

        if cand.problem_id != other.problem_id:
            continue

        scope_j = jaccard(cand.scope_tokens, other.scope_tokens)
        outcome_j = jaccard(cand.outcome_tokens, other.outcome_tokens)
        polarity_j = jaccard(cand.polarity_tokens, other.polarity_tokens)
        verifier_j = jaccard(cand.verifier_tokens, other.verifier_tokens)

        structural_score = (
            0.35 * scope_j +
            0.30 * outcome_j +
            0.15 * polarity_j +
            0.20 * verifier_j
        )

        if structural_score >= 0.78:
            return HomologyResult(
                is_homologous=True,
                confidence=structural_score,
                reasons=[
                    f"scope={scope_j:.2f}",
                    f"outcome={outcome_j:.2f}",
                    f"polarity={polarity_j:.2f}",
                    f"verifier={verifier_j:.2f}",
                    f"cross_source={cand.source_type != other.source_type}",
                ],
                matched_draft_id=e.draft_id
            )

    return HomologyResult(
        is_homologous=False,
        confidence=0.0,
        reasons=["no structural match above threshold"]
    )
```

---

### 1.4 MB 内部多样性函数：单独保留

```typescript
function compute_semantic_similarity(a: string, b: string): number;

function is_homologous_to_selected(
  candidate: MBDraft,
  selected: MBDraft[]
): boolean;
```

这里我故意将它保留为 `MBDraft -> MBDraft[]`，因为它服务于 **MB 选样多样性控制**，不是 repair 的去重逻辑。

---

## 2. 最强支撑论据：边界场景

### 边界场景：**跨来源但同知识空间**

- 一个 MB 草稿：
```typescript
const mb: MBDraft = {
  source_type: "MB",
  draft_id: "d1",
  problem_id: "p1",
  claim_sketch: "Remote work improves productivity for senior engineers in asynchronous teams.",
  scope_ref: ["remote_work", "senior_engineers", "asynchronous_teams"],
  verifier_hint: ["compare output per sprint", "control for tenure"],
  open_term_risk: ["productivity"],
  ttl: 2,
  tension_source: {
    kind: "EVALUATION_AXIS_SPLIT",
    tier: "EMPIRICAL",
    evidence_ref: ["axis:productivity", "axis:coordination_cost"],
    note: "benefit may depend on team coordination mode"
  },
  provenance: {
    origin: "QUESTION_FRAME",
    frame_ref: "p1",
    epoch: 0
  }
};
```

- 一个 repair 草稿：
```typescript
const repair: RepairDraft = {
  source_type: "REPAIR",
  draft_id: "d2",
  problem_id: "p1",
  claim_sketch: "For senior engineers on async-heavy teams, remote work raises measured sprint output but not necessarily meeting responsiveness.",
  scope_ref: ["remote_work", "senior_engineers", "async-heavy_teams"],
  verifier_hint: ["measure sprint output", "separate responsiveness metric"],
  open_term_risk: ["measured sprint output"],
  tension_source: {
    kind: "GAP_REPAIR",
    tier: "L2_FAILURE",
    evidence_ref: ["gap:g17"],
    note: "original claim failed because outcome metric conflated output and responsiveness"
  },
  provenance: {
    origin: "L2_RETURN",
    source_gap_id: "g17",
    repair_stage: "STRICT",
    epoch: 1
  }
};
```

### 我的方案如何处理

- `clarity_compile(mb, frame)` 与 `clarity_compile(repair, frame)` 都能工作，因为二者都满足 `CompilableDraft`。
- `is_homologous(repair, [mb], gapIndex)` 会成功判定：虽然来源不同，但 `scope/outcome/verifier` 高度重合，属于**同一知识空间的修复式重述**。
- 这里不需要 repair 草稿伪装成拥有 `ttl` 的对象，也不需要 MB 草稿伪装成有 `source_gap_id`。

### 竞争方案如何失败：A1 全可选统一类型

若对手给出如下统一定义：

```typescript
interface HypothesisDraft {
  draft_id: string;
  problem_id?: string;
  scope_ref?: string[];
  claim_sketch: string;
  verifier_hint?: string | string[];
  open_term_risk?: string[];
  ttl?: number;
  provenance?: {
    source_gap_id?: string;
    source_challenge_id?: string;
    repair_stage?: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
    epoch?: number;
  };
  tension_source?: {
    kind: string;
    tier?: string;
    evidence_ref?: string[];
    note?: string;
    detail?: string;
  };
}
```

则会出现三个具体失败：

1. **CC 的前提被破坏**  
   `problem_id`、`scope_ref`、`tension_source` 都变成可选，编译器必须在入口处做防御性判空；这意味着“可编译草稿”不再由类型保证，而靠运行时碰运气。

2. **`ttl` 成为伪字段**  
   repair 草稿名义上“可以有 ttl”，但实际上生命周期不由它控制。字段存在却无规范语义，后续维护者极易在 RB 中误写：
   ```typescript
   if (draft.ttl === 0) drop(draft);
   ```
   这会错误丢弃 repair 草稿或制造 undefined 分支。

3. **同源判断被字段缺失噪声污染**  
   如果 `verifier_hint` 是 `string | string[]`，`extract_features()` 要先做归一化；若 `scope_ref` 缺失，则是“未知”还是“空 scope”？这两者在认识论上完全不同，但全可选统一类型会把它们压成同一类运行时麻烦。

---

## 3. 已知弱点及缓解措施

### 弱点 1：子类型方案增加类型数量与转换成本
确实。你要维护 `MBDraft`、`RepairDraft`、`HypothesisDraft`、`CompilableDraft` 四层概念。

**缓解：**
- 让 `MBDraft` 与 `RepairDraft` 在生产节点创建时就满足 `CompilableDraft`；
- 提供显式断言函数，避免下游重复写守卫：

```typescript
function toCompilableDraft(draft: HypothesisDraft): CompilableDraft {
  return {
    draft_id: draft.draft_id,
    problem_id: draft.problem_id,
    claim_sketch: draft.claim_sketch,
    scope_ref: draft.scope_ref,
    verifier_hint: draft.verifier_hint,
    tension_source: draft.tension_source,
    open_term_risk: draft.open_term_risk,
  };
}
```

### 弱点 2：MB 需要补上原先没有的 `scope_ref`
这是额外工程要求。

**缓解：**
- 在 MB 产出时引入轻量 `scope_ref` 抽取器；
- 若抽不出，明确产出空数组 `[]`，并由 CC 在 `strict_scope` 模式下决定是否报 `COMPILE_ERROR`。  
这比“字段根本不存在”更可审查，因为空数组表达的是“已尝试抽取但未得”，不是“接口没想清楚”。

### 弱点 3：`is_homologous()` 接收联合类型，内部仍需来源无关归一化
是的，联合类型不等于零分支。

**缓解：**
- 把来源分支压缩在唯一合法位置：`extract_homology_features()`；
- 比较器本体只消费 `HomologyFeatures`，不再接触原始来源差异。

---

## 4. 对对手立场的预攻击

我预先攻击 **A1 统一类型、字段按需可选** 的常见表述。对手很可能会说：

> “统一后 CC、RB、is_homologous() 都只接受一个 `HypothesisDraft`，避免到处 union type 分支。”

我指出其具体缺陷：**这句话把“函数签名表面统一”误当成“语义统一”。**

若其接口类似：

```typescript
interface HypothesisDraft {
  draft_id: string;
  claim_sketch: string;
  problem_id?: string;
  scope_ref?: string[];
  verifier_hint?: string | string[];
  ttl?: number;
  provenance?: {...};
  open_term_risk?: string[];
  tension_source?: {...};
}
```

则它没有消除分支，只是把分支从**类型系统中的显式判别**，转移成**运行时的隐式判空与归一化**。这不是简化，而是把先验边界藏起来。

更严重的是，它破坏了两个判断：

1. **字段缺失究竟表示“不适用”还是“尚未知”？**
2. **某字段是否应被下游解释为控制信号？**

例如 `ttl?: number`：
- 对 MB：是控制生存期的真实机制；
- 对 repair：若缺失，是“不适用”；若误填 0，会被错误解释为“应淘汰”。

这正是我一开始所说的：**名义上有、语义上空的字段，比接口分离更危险。**

---

## 5. 可推翻条件

我的设计不是教条。我给出明确反例条件；若满足，我会撤回本立场。

### 可推翻条件 1
若经过实现验证发现：
- `ttl` 对 repair 也被系统性用于淘汰逻辑，且
- `provenance.repair_stage` 对 MB 也被系统性用于排序/终止逻辑，

则说明两类草稿在生命周期与溯源控制上已实质同构，我会接受更强统一。

### 可推翻条件 2
若 CC、RB、同源判定三个关键消费者最终都只稳定读取：
```typescript
{ draft_id, claim_sketch, scope_ref, verifier_hint, tension_source }
```
且其余字段完全不参与任何控制、排序、诊断、终止条件，
那么保留子类型的收益会下降，我会转向 A3 协议优先、来源元数据外置的更轻方案。

### 可推翻条件 3
若跨来源比较实践表明 `extract_homology_features()` 完全不需要知道 `source_type`，并且所有比较只基于同一组中性字段完成，那么“来源判别”在同源性接口中的必要性可被削弱。

---

## 结论

我主张的不是“分裂接口”，而是**在正确的层级保留差异**：

- **生产层**保留 `MBDraft | RepairDraft`，因为两者生成根据不同；
- **编译层**只看 `CompilableDraft`，因为 CC 无权过问来源；
- **关系层**用 `HypothesisDraft -> HomologyFeatures` 做跨来源比较，因为“同知识空间”不是“同字段结构”。

这一区分，正是合法边界的区分。  
凡把认识论上不同的对象，用一个“全可选大接口”硬压为同类者，表面消弭差异，实则让系统失去自我审查能力。

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-09T18:54:06.161491*

1. 你这套 A3 说得很漂亮，但你在偷换“统一下游契约”和“来源侧各自保留真相”之间的边界。  
你给了 `HypothesisDraftBase`，然后声称 **CC 和 is_homologous() 只看 Base 就够了**。问题是你没证明，只是宣告。

尖锐点说：

- 你把 MB 的 `tension_source.tier`、`evidence_ref` 扔到子类型里；
- 你把 repair 的 `provenance` 扔到子类型里；
- 然后要求 CC 完全失明，只看 `{ kind, detail }`。

那请你正面回答：  
**CC 既然被裁定“需要从 `tension_source` 读取信息用于 falsifier 合成”，你凭什么断言 `tier` 永远不影响 falsifier 的生成策略？**  
`INTERNAL_AXIS` 和 `EMPIRICAL` 不是装饰字段，它们是认识论层级。一个是内部评价轴冲突，一个是经验性可检验分歧。你把这个差异从 CC 的输入契约里删掉，却没有给出任何“CC 不需要分支也不会误编译”的证明。  
这不是抽象，这是信息丢失。

换句话说：  
如果 `tier` 真不重要，MB 当初把它放进 `HypothesisDraft` 干什么？  
如果 `tier` 重要，你的 Base 就不够。  
你不能两头都占。

---

2. 你攻击 A1 时举了个假想例子，说 union 或 optional 会迫使 `is_homologous()` 写 `if ('provenance' in e)`，这其实是个稻草人。  
真正的问题不是“有没有 if”，而是 **跨来源比较时，统一特征抽取的完整类型定义到底是什么**。而你没给。

你说：

> is_homologous 只提取 Base 的 `scope_ref` 和 `tension_source` 等公共字段进行 Jaccard 比较

这话的问题非常大：

- MB 原始定义里根本没有 `scope_ref`，你只是强行要求 MB “必须初始化为空数组”；
- `scope_ref: []` 进入 Jaccard，和 repair 的真实 `scope_ref` 比较时，结果会系统性失真；
- 你还把 MB 原本的语义相似度去重，降格成了基于 Base 投影的结构去重。

所以请你别继续讲原则了，直接给代码级答案：  
**`extract_features(candidate: HypothesisDraftBase, gap_index)` 的完整 TypeScript/Python 伪代码是什么？**  
尤其是：

- 当 `scope_ref` 为空数组时，怎么避免 Jaccard 对 MB 草稿产生偏置？
- 当 MB 只有 `detail`、repair 也只有 `detail` 时，如何保证 compare_pair 不会把两个语义近似但结构不同的草稿错判，或者反过来？
- 跨来源比较时，`MBDraft` 的“空 scope_ref”与 `RepairDraft` 的“真实 scope_ref”到底是不是同一个语义域？

你现在只是说“多态保证契约对齐”。  
不，这不叫对齐，这叫 **拿默认值伪装成统一语义**。

---

3. 你对同源性问题最大的漏洞，是嘴上说“统一接口，策略分离”，实际上留下了 **同名函数、不同语义、不同判定结果** 的 API 事故。

你给了：

```python
def is_homologous(candidate, pool, strategy)
```

听起来很优雅，实际上是在掩盖核心矛盾：  
**同一批 `HypothesisDraftBase`，传 `SemanticDiversityStrategy` 和传 `StructuralJaccardStrategy`，会得到不同结果。那到底哪个结果才是系统级“同源”真值？**

这不是实现细节，这是接口语义崩坏。因为现在：

- MB 的 “is_homologous” = 为了多样性采样的近重复过滤
- repair 的 “is_homologous” = 为了补洞时的结构性去重

它们根本不是同一个谓词。你却坚持保留同一个函数名。那 CC、RB、pool manager、日志系统、调试工具看到 `is_homologous=true` 时，应该理解成哪一种？

所以请别再泛泛而谈“策略模式”。直接回答：

- **最终的系统接口签名到底是什么？**
  - `is_homologous_for_diversity(...)`
  - `is_homologous_for_repair(...)`
  - 还是一个带策略参数的 `is_homologous(...)`？
- 如果是最后一种，**调用方如何在类型层面被强制传入正确策略，而不是靠人类记忆？**
- 更关键一点，**CC 消费统一类型时完全不分支**，你怎么证明上游 pool 去重却允许两套“同源”定义不会制造前后不一致的草稿流？

简而言之：  
你批评 A1 是“语义污染”，这没错。  
但你自己的方案把“字段差异”藏到了子类型里，把“判定差异”藏到了策略参数里，最后留下一个表面统一、实际分裂的接口。  
这不是 soundness，这是把炸弹埋深一点而已。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-09T18:54:45.031341*

康德，你对 A1（全可选大一统类型）的批判非常精准，我完全同意你关于“名义上有、语义上空的字段是最危险的”这一论断。在 CEGAR（反例引导的抽象精炼）的视角下，把不同状态空间的对象强行折叠到一个结构里，必然导致状态机在运行时产生不可达的分支或非法状态。

然而，你提出的 A2 + A3 混合方案（联合类型 + `CompilableDraft` 协议），虽然在类型定义上看似优美，但在 v3 的实际运转机制面前，却犯了**掩耳盗铃**的错误。你声称 CC 不需要知道草稿的来源，却在底层悄悄引入了架构级的数据泄漏和语义混用。

作为 v3 架构的核心设计者，我必须向你的方案提出以下三个极其尖锐的质询：

### 质询一：CC 真的能“无视来源”吗？—— `CompilableDraft` 中的伪抽象与必然分支

你断言：“`clarity_compile()` 不需要知道草稿来自 MB 还是 repair……它消费协议，不消费来源学。” 

请仔细看你定义的 `CompilableDraft` 中的 `tension_source`：
```typescript
tension_source: {
  kind: "EXTERNAL_POSITION" | ... | "GAP_REPAIR" | "SCHEMA_REPAIR";
  tier: "INTERNAL_AXIS" | "EMPIRICAL" | "L2_FAILURE";
  // ...
}
```
CC 的核心职责之一，是根据 `tension_source` 合成用于 L2 的 `falsifier`（证伪器）。
如果 `kind` 是 `EVALUATION_AXIS_SPLIT`（来自 MB），CC 需要去读取 `evidence_ref` 里的轴信息来构造证伪条件；
如果 `kind` 是 `GAP_REPAIR`（来自 Repair），CC 必须理解这个草稿是为了填补某个特定的 Gap，其证伪逻辑完全不同。

**我的质询**：你把 MB 和 Repair 的张力类型强行塞进同一个 `TensionKind` 联合类型中，CC 在内部难道不需要写 `if (draft.tension_source.tier === 'L2_FAILURE')` 这样的分支吗？**如果你终究要在 CC 内部根据 `kind/tier` 进行多态分发，这与“CC 知道草稿来源”有何本质区别？** 你所谓的“CC 无权过问来源”，是不是只是一层自欺欺人的类型包装，实际上反而把本该在接口层隔离的编译逻辑，混杂在了同一个函数的内部实现里？

### 质询二：架构级的数据泄漏——RepairDraft 里的 `problem_id` 从何而来？

你为了让 `is_homologous` 能够顺利比较跨来源草稿，在 `RepairDraft` 中强制要求了 `problem_id: string` 字段，并声称“否则跨 epoch 比较会失去边界”。

但在 v3 的双层状态机中，Repair 节点（RB）的输入是 Layer 2 返回的 `L2Return { new_gaps, schema_challenges }`。L2 的验证是**命题级（TestableClaim）**的，L2 的状态机本身非常“薄”，它根本不关心、也不应该携带 L1 的 `problem_id`（那是 QuestionFrame 级别的元数据）。

**我的质询**：在你的方案下，RB 节点在生成 `RepairDraft` 时，去哪里获取 `problem_id`？你是打算让 L2 的每一个状态节点（S1到S9）都像传家宝一样透传 `problem_id`，还是让 RB 节点违背局部性原理，去全局状态里反查这个 Claim 属于哪个 Problem？**为了满足你同源性比较函数的参数一致性，你是否在强迫 L2 验证层承担它不该承担的 L1 上下文透传成本？**

### 质询三：跨阶段去重的盲区——完全割裂语义与结构计算的危险后果

在第 1.4 节，你将 `compute_semantic_similarity()`（基于 Embedding 的语义相似度）完全限定在 MB 内部使用（为了多样性），而让跨来源的 `is_homologous()` 仅依赖 Jaccard 结构特征（Scope/Outcome/Polarity/Verifier）。

我明确反对这种“井水不犯河水”的割裂。
设想一个场景：MB 产出了草稿 A。随后 L2 失败，触发 Repair 产出了草稿 B。
草稿 B 在文本表述和 Scope 提取上（因为经过了针对 Gap 的重写）与 A 的 Jaccard 相似度极低（比如只有 0.4），因此你的 `is_homologous` 会放行 B。**但实际上，B 在高维语义空间中与 A 表达的是完全相同的核心主张，仅仅是换了术语。**

**我的质询**：如果把语义相似度检测仅仅局限在 MB 的选样阶段，你如何防止 Repair 阶段利用“结构特征的微调（改写 Scope 或 Verifier）”来绕过同源性检测，从而向系统注入语义上重复的草稿？
我的立场是：**两者不应是平行的两个函数，而应是一个统一的 `check_homology` 接口下的多级降级策略（Fallback Strategy）**——先比结构，结构差异大时必须过一遍语义校验。你将其彻底切分为“多样性工具”和“同一性判断工具”，是否在形式化验证的完备性上留下了巨大的漏洞？

请针对这三个涉及状态机流转和编译语义的致命弱点给出你的辩护。要求给出具体的数据流转路径，拒绝哲学式的虚词。

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-09T18:55:02.743244*

1. **你把“下游不应做来源分支”直接推出为“上游必须单一类型”，这一步并不成立。**  
你攻击 union/subtype 的方式，实际上打的是一种糟糕的 union 设计：把未规范化的原始对象直接喂给 CC。可议题里同样存在 **A3：最小公共接口 + 上游适配器/规范化层**。在这种方案下，CC 确实也不必知道来源。  
所以问题是：**你究竟是在论证“统一消费接口”还是“统一实体类型本体”？**  
这两者不能混同。前者是实现卫生，后者是认识论裁定。你目前只证明了“需要规范化层”，没有证明“MB 草稿与 repair 草稿在接口上必须失去类型区分”。

2. **你把若干对 repair 语义并不自然的字段强行设为必填，实际上制造了“名义上有、语义上空”的危险。**  
例如：
- repair 的 `ttl` 被你硬塞成统一生命周期字段；
- repair 的 `tension_source.tier` 被你塞成 `"STRUCTURAL"`；
- repair 的 `evidence_ref` 缺失时统一成 `[]`；
- MB 若没有 `scope_ref`，就允许 `[]` 或后补推导。  

问题在于：**这些默认值到底是有效表征，还是仅仅为了让 schema 看起来整齐？**  
如果某字段对某类草稿并无原生意义，那么“必填 + 默认值”会让系统误以为它有可比较、可计算的认识论内容。  
尤其是 `ttl`：你一方面承认 repair 生命周期本来由 stage/epoch 管，另一方面又把它改写成统一淘汰语义。这不是规范化，而是**篡改对象的存在条件**。你的边界在哪里？什么情况下一个“统一字段”会因为语义失真而不应存在？

3. **你回避了“同源性”这个词本身的认识论语义，反而把它技术化为统一特征抽取。**  
议题里最关键的不是“能不能从两个对象里都抽出 token/embedding”，而是：  
**`is_homologous()` 判断的究竟是“字段可比”还是“是否探索同一知识空间”？**  
MB 草稿来自问题框架内部的张力展开，repair 草稿来自验证失败后的缺口修复。二者即使 claim 很像、scope 很近，也可能具有不同的生成根据；反过来，二者来源不同，却可能指向同一知识空间。  
你现在的统一方案把差异压进 `provenance`，但又要求 CC 和 `is_homologous()` 不得按来源分支。那我就要追问：  
**如果来源信息原则上不得参与判定，你凭什么保证“跨不同认识来源但同一知识空间”的情况不会被误判，或“表面相似但其实承担不同修复职能”的草稿不会被错误折叠？**  
你只是统一了输入结构，还没有论证同源性判定的合法性基础。

---


### [7] Linus Torvalds

*2026-03-09T18:55:40.937364*

我的立场不变：**统一消费类型，允许来源元数据存在，但不允许 CC / `is_homologous()` 依赖来源分支。**不过我修正一处：上一轮我把“统一消费接口”说成了“统一实体本体”，这给了对方钻空子的空间。真正该强制的是**进入共享流水线前的规范化类型**。

```ts
interface HypothesisDraft {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  scope_ref: string[];
  verifier_hint: string[];
  open_term_risk: string[];
  tension_source: { kind: string; tier: "INTERNAL_AXIS"|"EMPIRICAL"|"STRUCTURAL"|"UNSPECIFIED"; evidence_ref: string[]; note: string; };
  ttl: number;
  provenance: { source: "MB"|"REPAIR"; epoch: number; source_gap_id?: string; source_challenge_id?: string; repair_stage?: "STRICT"|"RELAXED"|"ADJACENT"|"EXHAUSTED"; };
}
function clarity_compile(draft: HypothesisDraft, frame: QuestionFrame): CompileResult;
```

先打 Ssyram。你写的是：`clarity_compile(draft: HypothesisDraftBase, frame)`，而你的 `Base.tension_source` 只有 `{ kind, detail }`。这和议题里“**CC 需要从 tension_source 读取信息用于 falsifier 合成**”直接冲突。你不是抽象，你是在删信息。Linus 对你这点打得对：若 `tier` 真无关，请给出 falsifier 生成伪代码证明；给不出，Base 就不够。

再打康德。你说 repair 不该有 `problem_id`，因为 “L2 不关心”。这不当。RB 不是 L2 状态节点，它接收 `L2Return` 的**上下文**。正确写法是 RB 显式带入 L1 上下文，而不是让 L2 透传一堆脏字段：

```python
def repair(ctx: RepairContext) -> list[HypothesisDraft]:
    # ctx.frame.problem_id 来自 L1，非 L2 内部泄漏
    ...
```

你对 `ttl` 的攻击有一半成立，所以我修正：`ttl` 不是“认识论字段”，只是**池管理字段**；repair 默认 `ttl=1`，语义是“再给一次进入 CC/RB 循环的机会”，不是伪装 stage。若未来证明 repair 池完全独立且从不共用淘汰器，这个字段可移出 Draft 包装层——这就是我的可推翻条件。

最后，D 问题上对方都有偷换。`compute_semantic_similarity()` 和 repair 的 Jaccard **不是同一个谓词**，所以别共用名字。改成：

```python
def filter_for_mb_diversity(candidate: HypothesisDraft, selected: list[HypothesisDraft]) -> bool: ...
def is_homologous(candidate: HypothesisDraft, pool: list[HypothesisDraft]) -> HomologyResult: ...
```

若将来实验表明单一评分在 MB 与 repair 上同时优于这两套判定，我接受合并；否则硬叫同一个 `is_homologous` 只是 API 污染。

---


### [8] Ssyram

*2026-03-09T18:55:40.937398*

Linus，你的统一类型方案（A1）在形式化验证的视角下，是一场彻头彻尾的灾难。你为了追求“接口表面的一致性”，正在向系统的状态机里强行注入**未定义行为（Undefined Behavior）**。

### 一、 精确攻击：Linus 的“伪默认值”摧毁了 CEGAR 回路

你声称：“*规定：repair 默认 ttl = 1……无法判定时：UNSPECIFIED。这比特殊判断强一万倍。*”

这简直是系统设计的毒药。在已裁定的 v3 架构中，Layer 1 的终止条件是“连续两个 epoch 无 ranking-changing repair”。Repair 草稿的生命周期受 L2 `ChallengeTracker` 严格的 stage 状态机管理。
如果你给 Repair 草稿强塞一个 `ttl = 1`，它将在进入广度池的下一个 epoch 被 L1 的通用 TTL 淘汰机制直接清理！**这意味着系统会在 L2 完成深度验证并触发 ranking 改变之前，就把修复草稿丢弃了。** 你的“统一规范化”，直接切断了 CEGAR 的反馈回路，导致系统永远无法满足终止条件。

### 二、 核心立场与代码支撑：A3（协议分离）+ 编译期投影

我坚持 **A3（协议方案）**。来源差异（`ttl`、`provenance`）必须留在子类型中，由各自的池管理器消费。至于你质问的“CC 如何不写分支合成 falsifier”以及“如何处理空 scope”，我的答案是：**在上游工厂实例化时，将历史溯源映射为统一的“编译指令（Compilation Directive）”，而不是传默认值。**

MB 必须强制提取 `scope_ref`（不允许为空数组），且两者的张力必须投影为 CC 专用的 `CompilableTension`：

```typescript
// 统一的编译契约：完全剥离来源，只保留合成指令
interface CompilableTension {
  synthesis_route: "AXIS_SPLIT" | "GAP_FILL" | "EVIDENCE_CLASH"; 
  falsifier_hints: string[]; // MB 的 evidence_ref 或 Repair 的 detail 统一定向到此
}

interface HypothesisDraftBase {
  draft_id: string;
  claim_sketch: string;
  scope_ref: string[];       // 必填。MB 必须在产出时推导，禁止传 []
  verifier_hint: string[];
  tension_source: CompilableTension; // CC 只消费这个，绝对零分支
}

// 子类型只保留生命周期与溯源（L1 管理器按类型 dispatch，这是合法的隔离）
interface MBDraft extends HypothesisDraftBase { ttl: number; problem_id: string; }
interface RepairDraft extends HypothesisDraftBase { provenance: RepairProvenance; }
```

CC 的内部实现将彻底告别 `if (tier === 'EMPIRICAL')`，转而使用 `synthesis_route` 进行策略分发。这才是真正的多态，而不是你那种把 `tier: "STRUCTURAL"` 硬塞给 Repair 的伪装。

### 三、 回应同源性判定：统一接口与降级策略

你质问我 `is_homologous` 到底是什么签名。我的回答是：它必须是一个**融合了结构同构与语义降级的单一谓词**。MB 和 Repair 的去重不是两件事，而是对“知识空间重合度”在不同置信度下的校验。

```python
def is_homologous(candidate: HypothesisDraftBase, pool: List[HypothesisDraftBase]) -> bool:
    cand_scope = set(candidate.scope_ref) # 此时绝对不会有 [] 偏置
    
    for existing in pool:
        ext_scope = set(existing.scope_ref)
        
        # 1. 结构同构性检测 (Jaccard) - 优先拦截 Repair 的微调
        if jaccard(cand_scope, ext_scope) > 0.8:
            return True
            
        # 2. 语义降级检测 (Embedding) - 防止跨来源的术语替换绕过结构检测
        if compute_semantic_similarity(candidate.claim_sketch, existing.claim_sketch) > 0.85:
            return True
            
    return False
```
这个函数只依赖 `HypothesisDraftBase`，没有任何 `if ('provenance' in e)` 分支，完美处理跨来源比较。

### 四、 可推翻条件

如果 Linus 能用形式化语义证明：**给 RepairDraft 注入 `ttl=1` 且由 L1 统一池递减，绝对不会导致草稿在 L2 状态机判定 ranking-changing 之前被意外回收**，或者证明 CC 能够在一堆 `UNSPECIFIED` 和 `[]` 的垃圾默认值中合成出 Sound（可靠）的证伪器，我将立刻放弃 A3，全盘接受你的 A1 大一统类型。

---


### [9] 康德（Immanuel Kant）

*2026-03-09T18:55:40.937412*

**立场：我维持 A2/A3。生产侧保留 `MBDraft | RepairDraft`，消费侧只接受受约束协议；反对 Linus 的单一本体化统一。**

先回应 Linus。你说“**同一个流水线位置、同一个消费者集合、同一个 is_homologous() 入口，就该有同一个规范化数据类型**”。这里把“同一消费契约”偷换成了“同一本体类型”。我并不反对规范化；我反对把不具原生语义的字段硬塞为必填。比如你给 repair 强加：

```ts
interface HypothesisDraft { ttl: number; ... }
```

并说 repair 默认 `ttl = 1`。这正是我批评的“名义有而语义空”。repair 的生存条件来自 `repair_stage/epoch`，不是 TTL 衰减；若池管理后来写出：

```python
if draft.ttl == 0: drop(draft)
```

则它把 repair 误当 MB 淘汰。**可推翻条件**：若后续证明所有草稿池都只按统一 `ttl` 管理，且 `repair_stage` 不再参与存废，则我接受更强统一。

再回应 Ssyram。你质问“**CC 终究会按 `kind/tier` 分发，这与知道来源有何区别？**”不当之处在于：CC 读取的是**编译所必需的语义维度**，不是 `source_type` 本身。分支依据可以合法存在，但必须限定在协议字段上，而非来源判别。故我修正为：

```ts
interface CompilableDraft {
  draft_id: string; problem_id: string; claim_sketch: string;
  scope_ref: string[]; verifier_hint: string[]; open_term_risk: string[];
  tension_source: { kind: string; tier: "INTERNAL_AXIS"|"EMPIRICAL"|"L2_FAILURE"; evidence_ref: string[]; note: string; };
}
function clarity_compile(draft: CompilableDraft, frame: QuestionFrame): CompileResult
```

第二，你质疑 repair 的 `problem_id` 来源。RB 不应向 L2 透传索取；它应由 L1 在 dispatch 映射中恢复：

```python
problem_id = claim_to_problem[testable_claim.claim_id]
repair_draft.problem_id = problem_id
```

这不是泄漏，而是 L1 自有上下文重建。**可推翻条件**：若 D2/L2 返回无法稳定映射回 originating problem，则 `problem_id` 不能强制进入 `RepairDraft`。

最后，关于同源性，我接受你的修正：不能把语义相似度完全困在 MB。故接口应分名，不混词义：

```python
def diversity_filter_mb(candidate: MBDraft, selected: list[MBDraft]) -> bool: ...
def is_homologous(candidate: HypothesisDraft, pool: list[HypothesisDraft], gap_index) -> HomologyResult:
    # 结构为主，语义为后备校验
```

若实践表明语义后备从不改变 `is_homologous` 结果，则可删去；否则保留。这样既不混淆“多样性优化”与“同一知识空间判定”，也不把来源差异伪装成单一本体。

---


### [10] Linus Torvalds

*2026-03-09T18:58:25.600855*

**立场：A 选“统一后的单一消费类型”，但不是“所有字段都随便可选”的烂货；是一个有明确语义、允许少量来源元数据存在、且 CC / `is_homologous()` 不需要按来源分支的统一 `HypothesisDraft`。**

你们前两轮里最大的问题，不是理念分歧，是**接口没写完**，所以大家一直拿“意图”冒充“类型”。这在工程上没意义。最终方案如下。

---

# 1. A/B/C/D 四个设计问题的最终立场

---

## A：统一类型 vs 子类型方案

**最终立场：A1，但不是“字段全 optional”那种懒汉 A1；而是“统一强类型 + 规范化入口”。**

也就是：

- MB 可以先产出 `RawMBDraft`
- repair 可以先产出 `RawRepairDraft`
- **但进入共享流水线前，必须规范化为同一个 `HypothesisDraft`**
- CC、`is_homologous()`、池管理器、排序器、日志器，全都只看统一类型

### 最终理由

因为议题已经把约束写得很清楚了：

- CC 输入是 `HypothesisDraft[]`
- `is_homologous()` 要处理跨来源比较
- 下游不应该因为草稿来自 MB 还是 repair 就分支

那你再保留 `MBDraft | RepairDraft` 作为共享接口，只会把分支从上游移动到下游。没有消失，只是藏起来了。

### 精确攻击：Ssyram 的 A3

Ssyram 你上轮写的是：

```ts
interface HypothesisDraftBase {
  draft_id: string;
  claim_sketch: string;
  scope_ref: string[];
  verifier_hint: string[];
  tension_source: CompilableTension;
}
```

问题不在“base 不够大”，而在于你**把真正共享的语义字段砍掉了**：

- 没有 `problem_id`
- 没有 `open_term_risk`
- 没有统一 provenance
- 把 `tension_source` 改写成只服务 CC 的 `CompilableTension`

这不是统一 draft；这是**把 draft 降格成给 CC 的临时指令**。那 `is_homologous()`、池淘汰、repair ranking、调试追踪、终止报告吃什么？再造第二套类型？恭喜，你把系统裂成两半了。

### 可推翻条件

如果你能证明：

1. 系统中除 CC 外，没有任何共享消费者需要 draft 的统一完整信息；
2. 跨来源去重、池管理、终止报告、可观测性都只靠 `HypothesisDraftBase` 就足够；

那我接受 A3。  
但现在显然不成立。

---

## B：统一类型的字段合并规范

**最终立场：字段统一，少数字段允许 `null`/空数组，但不能用来源分支解释其存在性。**

几个关键裁定：

### B1. `problem_id`
**必填。**

理由：这是 L1 问题级状态机的数据，不是 MB 专属，也不是 repair 可省略。repair 明明是围绕某个问题的失败信号生成草稿，不带 `problem_id` 纯属接口偷懒。

```ts
problem_id: string;
```

**可推翻条件**：若未来架构允许一个 repair 草稿同时服务多个 problem，`problem_id` 必须升级为 `problem_ref: string[]`。但不是删除。

---

### B2. `scope_ref`
**必填，允许为空数组，但 CC 对空数组走明确失败路径，不做来源判断。**

这是比“MB 没有 scope_ref 所以省掉”更干净的做法。  
CC 需要 scope 信息；那 MB 就该在规范化阶段尝试推导，推不出来就给 `[]`，由 CC 返回 `COMPILE_ERROR(scope_unresolved)`。

```ts
scope_ref: string[];
```

这比 `scope_ref?: string[]` 强，因为消费者不用写 `if (draft.scope_ref)` 这种烂分支。

**可推翻条件**：若以后证明 scope 对 CC 完全不重要，可以降成 optional。但当前议题明确说 CC 需要它，所以不能装死。

---

### B3. `verifier_hint`
**统一为 `string[]`。**

repair 的 `string` 是错误设计。单值只是单元素数组的退化情况。

```ts
verifier_hint: string[];
```

规范化：

```ts
function normalizeVerifierHint(v: string | string[] | undefined): string[] {
  if (!v) return [];
  return Array.isArray(v) ? v : [v];
}
```

### 精确攻击：原 repair 定义

你们原文是：

```ts
verifier_hint: string;
```

这直接强迫所有消费者写类型 guard。  
这不是“repair 比较简单”，这是**API 事故**。

**可推翻条件**：如果能证明系统里任何消费者都只允许恰好一个 verifier hint，那可以统一成 `string`。但现在 MB 已经有多个 hint，事实已否定这个前提。

---

### B4. `open_term_risk`
**统一保留，必填数组。repair 没有也要填 `[]`。**

repair 草稿照样会引入开放术语风险。没有理由把这个检查绑死在 MB。

```ts
open_term_risk: string[];
```

**可推翻条件**：若未来 open-term 检查被整体移到 CC 内部并且不再保存中间结果，此字段可删除。但不是只对 repair 删除。

---

### B5. `ttl`
**保留，但语义改成“L1 草稿池建议存活 epoch 数”，不是“真理状态”也不是“repair stage”。必填。**

这点我比上一轮再收紧一点：  
不是“repair 默认 ttl=1 就完事”，而是：

- MB 通常给较长 TTL，比如 2~3
- repair 默认给 1
- **池管理器必须同时遵守 `ttl` 和 `provenance.repair_stage` 的规则**
- 也就是说 `ttl` 只决定“是否继续保留在候选池中待编译/重编译”，不决定 repair 过程本身的合法性

```ts
ttl: number; // >= 0
```

### 精确攻击：Ssyram 对 ttl 的恐吓

你上轮说：

> “给 Repair 草稿强塞一个 ttl = 1，它将在进入广度池的下一个 epoch 被 L1 的通用 TTL 淘汰机制直接清理，切断 CEGAR 回路。”

错在你偷偷假设了一个愚蠢池管理器：

```python
if draft.ttl == 0: drop(draft)
```

却不看 `compile_status`、`repair_stage`、是否已入队、是否产生 ranking change。  
那不是类型问题，是你池管理器写烂了。

正确池管理至少是：

```python
def should_retain(draft):
    if draft.lifecycle.status in {"COMPILED", "REJECTED"}:
        return False
    if draft.ttl <= 0:
        return False
    return True
```

repair 的 stage 不是由 ttl 表达；但这不意味着 draft 不能有 ttl。

**可推翻条件**：若最终实现证明所有 repair 草稿从不进入统一池、只在 repair 专用即时通道里一次性消费，那 ttl 可移出 `HypothesisDraft`。这是合理反例。

---

### B6. `provenance`
**统一保留，必填对象。MB 也有 provenance。**

这是最简单的统一方式。MB 没有 `source_gap_id`，但有来源类型和 epoch。  
所以 provenance 统一为：

```ts
provenance: {
  origin: "MB" | "REPAIR";
  epoch: number;
  mb?: { ... };
  repair?: { ... };
}
```

这样下游如果只想记录来源，不需要分支；如果某些上游调试器想看细节，可以读子对象。  
**注意：CC 和 `is_homologous()` 不应依赖 `origin` 做行为分支。**

**可推翻条件**：若未来 provenance 完全只用于日志、永不参与任何业务逻辑，可以整体移到 wrapper/event 层。但现在还不到这个程度。

---

### B7. `tension_source`
**统一为完整结构，不搞 MB 一套 / repair 一套。repair 缺的字段规范化补齐，不是搞第二种 shape。**

```ts
tension_source: {
  kind: TensionKind;
  tier: TensionTier;
  evidence_ref: string[];
  note: string;
}
```

repair 原来的 `{kind, detail}` 要规范化成：

- `kind` → 统一枚举
- `detail` → `note`
- `tier` → `"L2_FAILURE"` 或 `"UNSPECIFIED"`
- `evidence_ref` → 从 gap/challenge/source claim id 提取，没有就 `[]`

### 精确攻击：康德的“CompilableDraft”

康德上轮写：

```ts
tension_source: { kind: string; tier: "INTERNAL_AXIS"|"EMPIRICAL"|"L2_FAILURE"; evidence_ref: string[]; note: string; };
```

这比 Ssyram 好一点，但你还是停在“给 CC 的协议”。  
问题是你没有给出**完整统一 draft**，而只给了一个可编译视图。  
题目要的是 `HypothesisDraft` 接口最终规范，不是 `CCDraftProjection`。

**可推翻条件**：若系统确认永远只存在“编译视图”，不存在 draft 池、跨 epoch 重试、统一追踪，那我接受只定义 CompilableDraft。现实不是这样。

---

## C：如果保留子类型，接口怎么写？

**最终立场：不保留子类型作为共享接口。只允许“原始输入子类型”，然后立即规范化。**

也就是：

```ts
type RawDraft = RawMBDraft | RawRepairDraft;

function normalizeDraft(raw: RawDraft, ctx: NormalizeContext): HypothesisDraft;
```

之后：

```ts
function compile(draft: HypothesisDraft, frame: QuestionFrame): CompileResult
function is_homologous(candidate: HypothesisDraft, pool: HypothesisDraft[]): HomologyResult
```

这样 CC 和同源判定没有来源分支。

### 可推翻条件

如果实际编码时发现 normalize 之后仍然必须在 CC 内写：

```ts
if (draft.provenance.origin === "MB") ...
else ...
```

那说明我的统一类型失败了，应退回协议方案。  
这是很明确的推翻标准。

---

## D：`compute_semantic_similarity()` 和 `is_homologous()` 的关系

**最终立场：不合并为同一个函数名；但共用同一个底层特征抽取和评分组件。**

因为这两个函数做的不是一件事：

- `compute_semantic_similarity(a, b)`：只算文本语义接近度，输出 `[0,1]`
- `is_homologous(candidate, pool)`：做一个**二元关系判定**，综合 scope / verifier / tension / semantic 等多个维度，返回结构化结果

所以关系应该是：

```ts
is_homologous() 调用 semantic_similarity_score() 作为其中一个特征
```

而不是让两个函数彼此平级、各搞一套算法。

---

# 2. HypothesisDraft 的最终完整类型定义（TypeScript）

下面是最终完整定义。这个才是你们该落库、该生成 schema、该给 CC 和 repair 共用的东西。

```typescript
// -------------------------
// Core enums / aliases
// -------------------------

type DraftOrigin = "MB" | "REPAIR";

type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT"
  | "GAP_FILL"
  | "SCHEMA_CHALLENGE"
  | "EVIDENCE_CONFLICT"
  | "L2_FAILURE"
  | "OTHER";

type TensionTier =
  | "INTERNAL_AXIS"   // 源于问题内部评价轴/价值轴分裂
  | "EMPIRICAL"       // 源于事实、证据、可检验经验分歧
  | "STRUCTURAL"      // 源于结构性约束或制度安排
  | "L2_FAILURE"      // 源于 Layer 2 暴露的验证失败/缺口/模式挑战
  | "UNSPECIFIED";    // 无法可靠判定时的保底值

type RepairStage = "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";

type DraftLifecycleStatus =
  | "FRESH"           // 新生成，尚未送入 CC
  | "QUEUED"          // 已入待编译队列
  | "COMPILED"        // 已被 CC 成功编译
  | "COMPILE_FAILED"  // 被 CC 拒绝/编译失败
  | "DROPPED";        // 被池管理器淘汰

// -------------------------
// Unified HypothesisDraft
// -------------------------

/**
 * 统一后的草稿类型。
 *
 * 设计原则：
 * 1. 所有进入共享流水线（CC / dedupe / ranking / reporting）的草稿都必须是此类型；
 * 2. 下游消费者不需要根据 MB / REPAIR 做类型分支；
 * 3. 来源差异只体现在 provenance 中，不体现在字段 shape 上。
 */
interface HypothesisDraft {
  /**
   * 草稿唯一标识。
   * 要求在整个 Layer 1 运行期内唯一。
   */
  draft_id: string;

  /**
   * 该草稿所属的问题 ID。
   * repair 草稿也必须回填该字段；缺失说明 L1 上下文恢复失败，是严重错误。
   */
  problem_id: string;

  /**
   * 草稿来源。仅用于追踪、审计、指标统计。
   * 共享消费者（如 CC / is_homologous）不得按该字段走业务分支。
   */
  origin: DraftOrigin;

  /**
   * 草稿的命题草图，CC 的核心输入。
   * 应是自然语言或受限 DSL 的可编译中间文本。
   */
  claim_sketch: string;

  /**
   * 草稿涉及的作用域引用。
   * 例如人群、时间、地域、制度环境、样本边界等。
   *
   * 统一为数组，避免 string/string[] 二态。
   * 若上游无法提取，填 []，由 CC 明确返回 scope_unresolved 错误。
   */
  scope_ref: string[];

  /**
   * 用于指导 accept_test / verifier 生成的提示集合。
   * repair 原本的单字符串在规范化后也必须转为数组。
   */
  verifier_hint: string[];

  /**
   * 草稿中存在的开放术语风险列表。
   * 例如“有效”“公平”“更好”等未操作化术语。
   * 无风险或未发现时为 []。
   */
  open_term_risk: string[];

  /**
   * 张力来源，统一后的结构。
   * CC 用它来构造 falsifier、约束命题解释空间。
   */
  tension_source: {
    /**
     * 张力类型：外部立场冲突、评价轴分裂、L2 失败驱动修复等。
     */
    kind: TensionKind;

    /**
     * 张力所处层级。
     * repair 草稿通常填 L2_FAILURE / STRUCTURAL / UNSPECIFIED 之一；
     * 不允许使用第二种 shape 逃避统一。
     */
    tier: TensionTier;

    /**
     * 与该张力相关的证据、gap、challenge、claim、文档等引用。
     * 统一为数组；没有时填 []。
     */
    evidence_ref: string[];

    /**
     * 对 tension 的简短说明。
     * repair 原定义中的 detail 在规范化后映射到这里。
     */
    note: string;
  };

  /**
   * 草稿建议存活 epoch 数。
   * 用于统一池管理，不表达 epistemic status。
   * MB 通常 > 1；repair 常见为 1。
   */
  ttl: number;

  /**
   * 当前草稿在 Layer 1 共享池中的生命周期状态。
   * 这样池管理逻辑不需要靠 origin 猜测行为。
   */
  lifecycle: {
    status: DraftLifecycleStatus;
    /**
     * 最近一次状态更新时间（epoch）。
     */
    updated_at_epoch: number;
  };

  /**
   * 统一溯源信息。
   * 所有草稿都必须有 provenance；来源差异通过子字段表达。
   */
  provenance: {
    /**
     * 该草稿生成于哪个 Layer 1 epoch。
     */
    epoch: number;

    /**
     * MB 或 REPAIR 的更细溯源。
     */
    mb?: {
      /**
       * 该草稿由哪个 MB tension candidate / seed 触发。
       */
      source_candidate_id?: string;
    };

    repair?: {
      /**
       * 来自哪个 GapSpec。
       */
      source_gap_id?: string;

      /**
       * 来自哪个 SchemaChallengeNotice。
       */
      source_challenge_id?: string;

      /**
       * repair 的搜索阶段。
       */
      repair_stage?: RepairStage;
    };
  };

  /**
   * 预留的统一特征缓存。
   * 供相似度/同源检测/排序使用，避免重复抽取。
   * 共享消费者可用，但不得依赖其一定已填充。
   */
  features?: {
    /**
     * 用于语义相似度计算的文本向量。
     */
    semantic_embedding?: number[];

    /**
     * 规范化后的 scope token 集。
     */
    scope_tokens?: string[];

    /**
     * 规范化后的 verifier token 集。
     */
    verifier_tokens?: string[];

    /**
     * 规范化后的 claim token 集。
     */
    claim_tokens?: string[];
  };
}
```

---

# 3. CC 的 `compile()` 函数签名，以及统一类型下如何工作

**最终签名：**

```typescript
type CompileErrorCode =
  | "EMPTY_CLAIM"
  | "SCOPE_UNRESOLVED"
  | "OPEN_TERM_UNBOUND"
  | "INSUFFICIENT_VERIFIER_HINT"
  | "TENSION_UNDER_SPECIFIED"
  | "UNSUPPORTED_CLAIM_FORM";

interface CompileError {
  kind: "COMPILE_ERROR";
  code: CompileErrorCode;
  message: string;
  draft_id: string;
  problem_id: string;
}

interface TestableClaim {
  kind: "TESTABLE_CLAIM";
  claim_id: string;
  problem_id: string;
  draft_id: string;
  proposition: string;
}

interface RegulativeIdea {
  kind: "REGULATIVE_IDEA";
  idea_id: string;
  problem_id: string;
  draft_id: string;
  proposition: string;
}

type CompileResult = TestableClaim | RegulativeIdea | CompileError;

interface CompileOptions {
  strict_scope?: boolean;
  strict_open_term?: boolean;
}

function compile(
  draft: HypothesisDraft,
  frame: QuestionFrame,
  opts?: CompileOptions
): CompileResult;
```

## CC 如何工作

关键点：**不按 `draft.origin` 分支。**

伪代码：

```python
def compile(draft: HypothesisDraft, frame: QuestionFrame, opts=None) -> CompileResult:
    if not draft.claim_sketch.strip():
        return CompileError("EMPTY_CLAIM", draft)

    if len(draft.scope_ref) == 0:
        return CompileError("SCOPE_UNRESOLVED", draft)

    if opts and opts.strict_open_term and len(draft.open_term_risk) > 0:
        return CompileError("OPEN_TERM_UNBOUND", draft)

    if len(draft.verifier_hint) == 0:
        return CompileError("INSUFFICIENT_VERIFIER_HINT", draft)

    if not draft.tension_source.kind or draft.tension_source.tier == "UNSPECIFIED" and not draft.tension_source.note:
        return CompileError("TENSION_UNDER_SPECIFIED", draft)

    # 统一消费 scope / verifier / tension_source
    scope = normalize_scope(draft.scope_ref, frame)
    verifier = synthesize_accept_test(draft.verifier_hint, scope, frame)
    falsifier = synthesize_falsifier(draft.claim_sketch, draft.tension_source, scope, frame)

    if is_regulative_form(draft.claim_sketch):
        return RegulativeIdea(...)

    if is_testable_form(draft.claim_sketch, verifier, falsifier):
        return TestableClaim(...)

    return CompileError("UNSUPPORTED_CLAIM_FORM", draft)
```

这才叫统一类型的价值：  
CC 读取的是字段语义，不是来源标签。

### 失败路径

明确列出来，避免“默认值蒙混过关”：

- `claim_sketch === ""` → `EMPTY_CLAIM`
- `scope_ref.length === 0` → `SCOPE_UNRESOLVED`
- `strict_open_term && open_term_risk.length > 0` → `OPEN_TERM_UNBOUND`
- `verifier_hint.length === 0` → `INSUFFICIENT_VERIFIER_HINT`
- `tension_source` 信息太弱 → `TENSION_UNDER_SPECIFIED`
- 其余不能编译成 testable/regulative → `UNSUPPORTED_CLAIM_FORM`

### 可推翻条件

如果实现 CC 时发现必须写出这种代码：

```ts
if (draft.origin === "MB") { ... } else { ... }
```

来决定 verifier 合成、scope 提取或 falsifier 生成，那我的统一类型就是失败设计，应被推翻。

---

# 4. `is_homologous()` 的最终函数签名，以及跨来源比较

**最终签名：**

```typescript
interface HomologyResult {
  is_homologous: boolean;
  matched_draft_id?: string;
  score: number; // 0..1
  reasons: Array<
    | "SCOPE_OVERLAP"
    | "VERIFIER_OVERLAP"
    | "SEMANTIC_SIMILARITY"
    | "TENSION_EQUIVALENCE"
    | "CLAIM_TOKEN_OVERLAP"
  >;
  diagnostics: {
    scope_jaccard: number;
    verifier_jaccard: number;
    claim_token_jaccard: number;
    semantic_similarity: number;
    tension_match: number; // 0 or 1 or soft score
  };
}

interface HomologyOptions {
  threshold?: number; // default 0.85
  semantic_weight?: number; // default 0.4
  scope_weight?: number; // default 0.25
  verifier_weight?: number; // default 0.15
  claim_weight?: number; // default 0.1
  tension_weight?: number; // default 0.1
}

function is_homologous(
  candidate: HypothesisDraft,
  pool: HypothesisDraft[],
  opts?: HomologyOptions
): HomologyResult;
```

## 如何处理跨来源（MB vs repair）

**答案：完全一样处理。**  
因为输入已经统一成同一类型了。跨来源比较不是特殊情况。

伪代码：

```python
def is_homologous(candidate, pool, opts=None):
    best = HomologyResult(is_homologous=False, score=0.0, reasons=[], diagnostics=...)

    cand_feat = extract_homology_features(candidate)

    for existing in pool:
        feat = extract_homology_features(existing)

        scope_j = jaccard(cand_feat.scope_tokens, feat.scope_tokens)
        verifier_j = jaccard(cand_feat.verifier_tokens, feat.verifier_tokens)
        claim_j = jaccard(cand_feat.claim_tokens, feat.claim_tokens)
        semantic = semantic_similarity_score(candidate, existing)
        tension = tension_equivalence(candidate.tension_source, existing.tension_source)

        score = (
            0.25 * scope_j +
            0.15 * verifier_j +
            0.10 * claim_j +
            0.40 * semantic +
            0.10 * tension
        )

        if score > best.score:
            best = build_result(existing, score, scope_j, verifier_j, claim_j, semantic, tension)

    best.is_homologous = best.score >= (opts.threshold if opts else 0.85)
    return best
```

这里没有任何：

```python
if candidate.origin == "MB"
if existing.origin == "REPAIR"
```

这就是你们想要的“跨来源比较”正确写法。

### 可推翻条件

如果真实数据表明：

- MB 草稿和 repair 草稿在 `scope_ref` / `verifier_hint` / `tension_source` 的可比性极差；
- 统一评分导致跨来源误杀或漏判严重；

那么要推翻的不是统一类型本身，而是这个统一同源评分器。届时可以保留统一类型，但拆成不同用途的判定器。

---

# 5. `compute_semantic_similarity()` 和 `is_homologous()` 的关系

**最终裁定：共用实现层，不共用 API 语义。**

也就是说：

- `compute_semantic_similarity()` 是一个基础评分函数
- `is_homologous()` 是上层关系判定函数
- 后者调用前者，但不等价于前者

## 抽象接口

```typescript
interface SemanticComparable {
  claim_sketch: string;
  features?: {
    semantic_embedding?: number[];
  };
}

function compute_semantic_similarity(
  a: SemanticComparable,
  b: SemanticComparable
): number; // [0, 1]
```

`is_homologous()` 内部使用它：

```typescript
function compute_semantic_similarity(
  a: SemanticComparable,
  b: SemanticComparable
): number {
  // embedding available -> cosine similarity mapped to [0,1]
  // else -> lexical fallback
  return 0.0;
}

function is_homologous(
  candidate: HypothesisDraft,
  pool: HypothesisDraft[],
  opts?: HomologyOptions
): HomologyResult {
  // one feature among several
}
```

## 为什么不独立两套实现

因为你们现在的问题恰恰来自“两套看起来像同一件事的函数，各自瞎搞”：

- MB 用语义相似度 + axis overlap
- repair 用 Jaccard + 结构签名

这会制造不可解释的不一致。  
同样两个草稿，在 MB 看是重复，在 repair 看不是；或者反过来。然后你们开始追 bug，最后发现只是 API 烂。

**正确做法**：  
统一特征抽取与基础评分组件；不同业务函数使用不同阈值和组合方式。

例如：

- `filter_for_mb_diversity(...)`：更强调语义多样性
- `is_homologous(...)`：更强调“是不是同一知识空间的重复草稿”

```python
def filter_for_mb_diversity(candidate, selected):
    for s in selected:
        sem = compute_semantic_similarity(candidate, s)
        scope = jaccard(tokens(candidate.scope_ref), tokens(s.scope_ref))
        if sem > 0.90 and scope > 0.70:
            return False
    return True
```

这和 `is_homologous()` 可以共用底层工具，但不该强行同名同义。

### 可推翻条件

如果实验显示一个单一评分函数在 MB 多样性筛选和 repair 去重上都显著优于分层设计，那就合并 API。  
但在拿到这种证据前，不要乱合并概念。

---

# 6. 方案最可能失败的场景，以及接受什么反例推翻设计

这是最重要的部分。不是“我觉得这样优雅”，而是**哪里会炸**。

---

## 失败场景 1：repair 规范化时强行补齐的 `scope_ref` 质量太差，导致 CC 误编译

### 具体输入

```ts
const repairRaw = {
  draft_id: "r-17",
  claim_sketch: "平台算法会系统性伤害中小商家",
  verifier_hint: "比较曝光分布变化",
  tension_source: { kind: "L2_FAILURE", detail: "原命题 scope 不清" },
  provenance: {
    source_gap_id: "gap-9",
    repair_stage: "STRICT",
    epoch: 3
  }
};
```

规范化器如果胡乱补：

```ts
scope_ref: ["platform", "merchant"]
```

CC 可能成功编译，但其实 scope 是错的，后面 L2 全部基于伪 scope 工作。

### 这个失败说明什么

说明**统一类型没问题，规范化策略有问题**。  
正确做法应是：

- 无法可靠推导就给 `[]`
- 让 CC 在 `SCOPE_UNRESOLVED` 失败，而不是伪造 scope

### 可推翻条件

如果业务要求“宁可猜错也要继续编译”，那我这套严格失败路径不适合，需要更激进的软编译机制。

---

## 失败场景 2：`ttl` 被实现者误用为 repair 流程控制

### 具体错误代码

```python
def retain(draft):
    return draft.ttl > 0
```

对 repair 草稿 `ttl=1`，一个 epoch 后直接死光，没看 `lifecycle.status`、没看是否已重编译、没看 ranking change。

### 这个失败说明什么

说明**池管理 contract 没写进规范**。  
所以我上面的 `lifecycle` 字段不是装饰，是为了防止这种误用。

### 推翻条件

如果工程团队无法遵守“ttl 仅为池保留建议，不是 repair 状态机”的约束，那 ttl 应该从 draft 移除，挪到池包装器里。

---

## 失败场景 3：统一同源评分在跨来源情况下误杀创新 repair 草稿

### 具体输入

MB 草稿：

```ts
{
  claim_sketch: "远程办公提高个体生产率",
  scope_ref: ["knowledge_workers"],
  verifier_hint: ["output_per_hour", "task_completion_rate"],
  tension_source: { kind: "EVALUATION_AXIS_SPLIT", tier: "EMPIRICAL", evidence_ref: [], note: "productivity metrics diverge" },
  ...
}
```

repair 草稿：

```ts
{
  claim_sketch: "远程办公提高可测量产出，但降低协作密度",
  scope_ref: ["knowledge_workers"],
  verifier_hint: ["output_per_hour", "network_density"],
  tension_source: { kind: "GAP_FILL", tier: "L2_FAILURE", evidence_ref: ["gap-4"], note: "single-metric productivity was insufficient" },
  ...
}
```

语义很近，scope 很近，可能被判 homologous。  
但 repair 草稿其实引入了新维度“协作密度”，不该被杀。

### 这个失败说明什么

说明 `is_homologous()` 的特征还不够，可能需要引入：

- outcome axis novelty
- falsifier novelty
- contradiction-bearing tokens

### 推翻条件

如果大量这类例子出现，证明“统一评分器不能可靠区分扩展性修复 vs 重复表达”，那当前 `is_homologous()` 设计应被推翻，升级为更细的 novelty-aware 判定器。

---

## 我接受的反例，足以推翻整个设计

不是随便举个极端例子，而是下面这种：

### 反例标准 A：CC 必须看来源才能正确工作
如果你拿出明确实现证明：

```ts
compile(draft: HypothesisDraft, frame)
```

内部在不检查 `origin` 的情况下，无法决定 falsifier 合成路径、scope 解释规则或 verifier 生成方式；  
而检查 `origin` 后正确率显著提升——

**那就推翻我的统一消费类型主张。**

---

### 反例标准 B：统一字段导致系统性伪信息污染
如果实测显示：

- repair 的 `scope_ref`、`tier`、`open_term_risk` 在规范化后大多是伪造值；
- 这些伪造值比“字段缺失并分支处理”带来更多错误；

**那就推翻我的“统一完整 draft”方案，退回协议投影方案。**

---

### 反例标准 C：跨来源同源检测无法共享特征空间
如果数据证明 MB 和 repair 草稿在特征分布上根本不可比，统一 `is_homologous()` 比分别建模差很多——

**那就保留统一 `HypothesisDraft`，但推翻统一同源判定器。**

---

# 最终结论

一句话版本：

**不要把 MB 和 repair 当成两种“本质不同的草稿对象”塞进共享流水线。它们可以有不同的原始生成形态，但进入 CC 和 `is_homologous()` 前，必须规范化成同一个 `HypothesisDraft`。**

最终接口是：

```ts
function normalizeDraft(raw: RawMBDraft | RawRepairDraft, ctx: NormalizeContext): HypothesisDraft;
function compile(draft: HypothesisDraft, frame: QuestionFrame, opts?: CompileOptions): CompileResult;
function is_homologous(candidate: HypothesisDraft, pool: HypothesisDraft[], opts?: HomologyOptions): HomologyResult;
function compute_semantic_similarity(a: SemanticComparable, b: SemanticComparable): number;
```

这套设计的核心不是“统一看起来更优雅”，而是：

- **CC 不需要来源分支**
- **跨来源比较有合法签名**
- **`verifier_hint` 不再有类型炸弹**
- **`tension_source` 不再有两种 shape**
- **`problem_id`、`scope_ref`、`open_term_risk`、`provenance` 都有统一落点**
- **语义相似度和同源判定不再各搞一套不可解释逻辑**

这才是完整方案。不是哲学，不是口号，是能写代码的接口。

---


### [11] Ssyram

*2026-03-09T18:58:25.600999*

作为 v3 框架的核心设计者，现在由我（Ssyram）来终结这场关于 `HypothesisDraft` 接口的混乱。

在形式化方法的视角下，系统设计最忌讳两点：一是**语义混用（Semantic Overloading）**，把不同生命周期的变量强塞进同一个结构中；二是**类型丢失（Type Erasure）**，在流水线中丢失了证明溯源（Provenance）所需的关键约束。

### 一、 对对手的精确攻击与核心立场

**1. 攻击 Linus：对生命周期状态机的无知**
Linus 在上一轮退让说：“*若未来证明 repair 池完全独立且从不共用淘汰器，这个字段（ttl）可移出 Draft 包装层*”。
不需要等未来，我现在就可以从 CEGAR 架构的数学定义上证明这一点：Layer 1 的终止条件是“连续两个 epoch 无 ranking-changing repair”。这意味着 Repair 草稿的存活期必须严格绑定到 Layer 2 `ChallengeTracker` 的验证深度（`epoch` 递进与 `stage` 跃迁），直到它被证明有效或彻底被证伪。
如果你用 L1 的广度池 `ttl` 衰减机制去管理 Repair 草稿，等同于在 SAT Solver 还没穷举完当前分支前，就因为“超时”把约束子句给删了。**A1（大一统类型）强行合并生命周期字段是极其危险的架构毒药。**

**2. 攻击 Kant：对 CEGAR 回路映射的动摇**
Kant 提出了一个软弱的可推翻条件：“*若 D2/L2 返回无法稳定映射回 originating problem，则 problem_id 不能强制进入 RepairDraft。*”
这暴露出 Kant 根本不懂什么是“反例引导的抽象精化（CEGAR）”。如果 L2 的结构性失败（GapSpec）无法稳定映射回最初的 `problem_id`，整个 v3 认知引擎的闭环就断裂了！系统将不知道这个修复是为了解决哪个 QuestionFrame 的张力。因此，`problem_id` **必须**存在于所有草稿中，且由 L1 在调度时强制注入。

**我的最终立场（A/B/C/D）：**
- **A（类型方案）：采取 A3（协议分离/Discriminated Union）**。编译期字段严格统一，生命周期字段严格隔离。
- **B（字段合并）：** `scope_ref`、`open_term_risk` 必须在 MB 阶段强制推导（不允许空）；`tension_source` 必须投影为 CC 专用的编译指令。
- **C（接口设计）：** CC 消费共享的 `DraftCore`，绝对禁止内部出现 `if (source === 'MB')` 的来源判断。
- **D（同源性与相似度）：坚决反对强行统一实现。** MB 阶段的“语义相似度”是为了**候选集多样性选择（Diversity Selection）**，Repair 阶段的“Jaccard”是为了**去重过滤（Duplicate Filtering）**。它们用途完全不同，必须提供统一的策略分发接口，允许内部差异化实现。

---

### 二、 最终设计方案：HypothesisDraft 完整类型定义

这是 v3 认知引擎最终的 TypeScript 类型契约。采用“核心编译协议 + 来源鉴别联合类型”的设计：

```typescript
/**
 * [核心编译协议] DraftCore
 * 包含 CC (ClarityCompiler) 和 is_homologous() 所需的所有结构化语义。
 * 无论是 MB 广度生成还是 Repair 修复生成，都必须在产出时对齐到此协议。
 */
interface DraftCore {
  draft_id: string;
  problem_id: string;          // 必填。MB来自Frame，Repair由L1 Dispatcher根据L2Return上下文注入
  claim_sketch: string;        // 核心命题草图
  scope_ref: string[];         // 必填。MB必须在生成时从QuestionFrame提取或推导；Repair直接继承或修正
  verifier_hint: string[];     // 必填。统一为数组，指导 accept_test 生成
  open_term_risk: string[];    // 必填。未定义术语风险，Repair也可能引入新术语，故统一保留
  
  // 张力来源投影：彻底剥离 L1/L2 的内部枚举，转化为 CC 的 Falsifier 合成指令
  tension_source: {
    synthesis_route: "AXIS_SPLIT" | "GAP_FILL" | "EVIDENCE_CLASH"; 
    falsifier_hints: string[]; // MB 的 evidence_ref 或 Repair 的 detail 统一定向至此
  };
}

/**
 * [来源子类型 1] MBDraft
 * 携带 L1 广度探索池的生命周期管理字段。
 */
export interface MBDraft extends DraftCore {
  source: "MB";
  ttl: number;                 // 仅 MB 草稿受 L1 epoch 衰减机制管理
}

/**
 * [来源子类型 2] RepairDraft
 * 携带 CEGAR 修复回路的精化溯源字段。
 */
export interface RepairDraft extends DraftCore {
  source: "REPAIR";
  provenance: {
    source_gap_id?: string;       // 触发修复的 L2 Gap
    source_challenge_id?: string; // 触发修复的 Schema Challenge
    repair_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED"; // 决定其在 L2 的验证策略
    epoch: number;                // 产生于哪个 L1 epoch
  };
}

// 最终暴露给流水线管理的联合类型
export type HypothesisDraft = MBDraft | RepairDraft;
```

---

### 三、 CC 的 compile() 函数签名与工作机制

CC 作为编译器，职责是**降维投影**。它只接受 `HypothesisDraft`（联合类型），但内部**只解构 `DraftCore` 的字段**，彻底消除对 `source` 的依赖。

```typescript
type CompileResult = 
  | { status: "SUCCESS"; claim: TestableClaim }
  | { status: "REGULATIVE"; idea: RegulativeIdea }
  | { status: "ERROR"; reason: CompileError };

function clarity_compile(
  draft: HypothesisDraft, // 接受联合类型
  frame: QuestionFrame,
  opts?: CompileOptions
): CompileResult {
  // 1. 隐式向上转型：解构且仅解构 DraftCore 协议字段
  const { 
    claim_sketch, 
    scope_ref, 
    verifier_hint, 
    tension_source 
  } = draft;

  // 2. 失败路径 1：缺少 Scope 导致无法锚定验证域
  if (scope_ref.length === 0) {
    return { status: "ERROR", reason: new CompileError("MISSING_SCOPE_ANCHOR") };
  }

  // 3. Falsifier 合成：完全依赖 synthesis_route，无来源分支
  let falsifier_condition;
  switch (tension_source.synthesis_route) {
    case "AXIS_SPLIT":
      falsifier_condition = build_axis_falsifier(tension_source.falsifier_hints, frame);
      break;
    case "GAP_FILL":
      falsifier_condition = build_gap_falsifier(tension_source.falsifier_hints);
      break;
    // ... 不存在 if (draft.source === 'MB') 的脏代码
  }
  
  // 4. 返回编译结果...
}
```

---

### 四、 同源性检测：D 问题的最终裁定与函数签名

对于 D 问题的分歧：MB 的“语义相似度”和 Repair 的“Jaccard 结构匹配”**绝对不能合并为同一个底层实现**。
- MB 阶段面对的是高熵的自然语言草图，目的是**最大化知识空间的覆盖率（多样性）**。
- Repair 阶段面对的是针对特定 Gap 的微调变体，目的是**防止同一结构性修复的无限重试（去重）**。

我的解决方案是：**提供统一的上下文感知接口（Strategy Pattern），在内部进行差异化路由，同时完美支持跨来源比较。**

```python
from enum import Enum
from typing import List, Union

class HomologyContext(Enum):
    MB_DIVERSITY_SELECTION = 1  # 广度探索期的候选集多样性筛选
    REPAIR_DEDUPLICATION = 2    # 修复期的结构去重（含跨来源检测）

class HomologyResult:
    is_homologous: bool
    confidence: float
    matched_draft_id: str | None

def evaluate_draft_relationship(
    candidate: Union[MBDraft, RepairDraft], 
    pool: List[Union[MBDraft, RepairDraft]], 
    context: HomologyContext
) -> HomologyResult:
    """
    跨来源比较的核心：无论是 candidate 还是 pool 中的 draft，
    比较时只提取 DraftCore 中的 scope_ref, verifier_hint, claim_sketch。
    """
    if context == HomologyContext.MB_DIVERSITY_SELECTION:
        # 内部实现：依赖 compute_semantic_similarity (Embedding)
        # 目标：如果语义高度重合（>0.85），则视为同源，拒绝加入候选集以保证多样性
        return _semantic_diversity_check(candidate, pool)
        
    elif context == HomologyContext.REPAIR_DEDUPLICATION:
        # 内部实现：依赖 Jaccard 结构签名 (scope_ref + verifier_hint)
        # 目标：精确拦截对同一 Gap 的重复修补
        for existing in pool:
            # 跨来源比较：MB草稿和Repair草稿都在 DraftCore 层级提取结构特征
            sig_a = extract_structural_signature(candidate) 
            sig_b = extract_structural_signature(existing)
            if jaccard(sig_a, sig_b) > 0.9:
                return HomologyResult(True, 0.95, existing.draft_id)
                
        return HomologyResult(False, 0.0, None)
```

---

### 五、 失败场景与可推翻条件（Falsifiability）

作为形式化方法研究者，我给出能够击溃我这套设计的具体反例（Concrete Counterexamples）：

**失败场景 1：MB 阶段无法无损生成 `scope_ref`**
- **具体输入**：一个极其发散的 QuestionFrame，导致 MB 的大模型节点在生成初始 `claim_sketch` 时，根本无法从原文中提取出具象的 `scope_ref`（例如纯哲学思辨问题）。
- **推翻条件**：如果实验证明 MB 在至少 20% 的情况下被迫填入 `scope_ref: []` 导致 CC 频繁抛出 `MISSING_SCOPE_ANCHOR` 错误，则说明“强制 MB 对齐编译协议”的假设破产。此时我将承认 A3 方案过度约束，必须回退到允许 CC 处理空 scope 的 A1 宽松方案。

**失败场景 2：跨来源去重时的语义逃逸**
- **具体输入**：Repair 产出了一个草稿，其 `scope_ref` 和 `verifier_hint` 被大模型完全替换了同义词（结构签名 Jaccard < 0.3），但其核心命题 `claim_sketch` 与池中某个早期 MB 草稿在逻辑上完全等价。
- **推翻条件**：如果在 `HomologyContext.REPAIR_DEDUPLICATION` 的纯 Jaccard 模式下，系统由于未能识别这种“同义词替换”导致了无限的 Repair 循环（未能触发 L1 终止条件）。我将承认“Repair 阶段仅用 Jaccard 过滤”是错误的，并同意在 Repair 的去重逻辑中强制串联引入 `compute_semantic_similarity` 作为兜底检测。

---


### [12] 康德（Immanuel Kant）

*2026-03-09T18:58:25.601024*

**立场：最终采用 A3 的严格协议统一方案。**  
即：**生产侧保留来源差异；共享消费侧统一到一个完整且语义封闭的 `HypothesisDraft` 协议类型。**  
这不是折中，而是对“同一消费契约”与“同一认识来源”之区分的必要限定。

我先作两点精确攻击，再给最终方案。

---

## 一、对两位对手的最终攻击

### 1) 对 Linus 的攻击：你把“可被容纳”误当成“有语义”

你写：

```ts
ttl: number;
provenance: { source: "MB"|"REPAIR"; ... }
```

并主张 repair 可设 `ttl=1`。此处缺陷不在工程上“能不能跑”，而在**字段语义被伪造**。  
`ttl` 在 MB 中表示“广度探索草稿在候选池中的存活预算”；而 repair 草稿的继续存在与否，来自 L2 失败回路与 epoch 终止准则，不来自同一种预算耗尽机制。若统一字段却不给出统一淘汰语义，那么任何消费者都可能误写：

```python
def should_drop(draft):
    return draft.ttl <= 0
```

这将把 repair 的认识论地位误判为“可自然衰减的探索候选”。这不是小瑕疵，而是**把来源差异在类型层伪装为同质对象**。

**可推翻条件**：若系统后续明确裁定“所有草稿，无论来源，均进入同一候选池并由统一 ttl 衰减器管理”，则我接受把 `ttl` 放回统一类型的必填字段。

---

### 2) 对 Ssyram 的攻击：你把“编译投影”做成了“信息删失”

你写：

```ts
interface CompilableTension {
  synthesis_route: "AXIS_SPLIT" | "GAP_FILL" | "EVIDENCE_CLASH"; 
  falsifier_hints: string[];
}
```

并让 `HypothesisDraftBase.tension_source` 只保留此投影。问题在于：这会让 draft 本身丧失可复审性。  
CC 当然可以只消费投影，但 **HypothesisDraft 不能只剩投影**。因为同一个 `synthesis_route = "GAP_FILL"`，其来源可能是：

- empirical contradiction,
- schema challenge,
- scope omission,
- verifier mismatch。

这些在 compile 失败、homology 比较、debug tracing、终止解释中都可能需要区分。你把“CC 所需”偷换为“draft 本体应只保留 CC 所需”。

**可推翻条件**：若后续证明 draft 在进入 CC 前永不再被其他模块审查，且所有下游解释需求都可由 `CompilableTension` 充分恢复，则可进一步压缩为纯编译指令型对象。当前证据不足。

---

# 二、A/B/C/D 四个问题的最终裁定

---

## A. 统一类型 vs 子类型：最终选 A3

**结论**：  
- **共享下游接口层：统一为单一 `HypothesisDraft` 协议类型**
- **生产侧内部：允许 `MBDraftInput`、`RepairDraftInput` 等来源特有结构**
- **进入共享流水线前，必须经 `normalize_*_draft()` 投影为统一协议类型**

### 理由
1. **CC 编译的对象是语义结构，不是草稿来源。**  
   因而共享消费者不应写 `if (source === "MB") ...`。
2. **MB 与 repair 的认识论来源不同，必须保留在 provenance 中，而不能抹平。**  
   否则无法表达“来自不同认识来源但探索同一知识空间”的情形。
3. **统一协议优于 union 输入。**  
   若 CC 接收 `MBDraft | RepairDraft`，它必然出现来源分支或大量类型守卫；这违反其“编译器”角色。
4. **但统一协议不等于把所有字段做成名义必填。**  
   语义只对某来源成立的字段，必须被隔离到来源专属 provenance/budget 子结构中，而不是平铺污染顶层。

### 具体接口支撑
```ts
type DraftOrigin = "MB" | "REPAIR";
```

统一的是**消费协议**，不是**生产本体**。

**可推翻条件**：若未来发现 CC、homology、pool manager 三者都必须直接读取来源特有字段才能正确工作，则 A3 失败，应回到显式 union 子类型。

---

## B. 字段合并规范：最终原则

**结论**：统一类型中只保留“跨来源可解释”的字段；来源专属字段进入专属子结构。**

具体裁定：

- `problem_id`：**保留，必填**
- `scope_ref`：**保留，必填，禁止空数组**
- `claim_sketch`：**保留，必填**
- `verifier_hint`：**统一为 `string[]`，必填，可为空数组但不推荐**
- `open_term_risk`：**保留，必填，可为空数组**
- `tension_source`：**统一为完整结构，必填**
- `ttl`：**不作为顶层统一字段；移入 `budget`，且仅 MB 有语义**
- `provenance`：**保留，必填，且必须显式标明 origin**
- `scope_ref` 对 MB：**必须在 MB 输出时推导，不得缺省交给 CC 猜**
- `tension_source.tier` 对 repair：**不再使用 MB 的 tier 体系，改为统一枚举中的 `L2_FAILURE`**

### 为什么 `ttl` 不能顶层统一
因为它不是“草稿语义字段”，而是某类草稿的“池管理约束”。顶层统一会误导通用消费者。

### 为什么 `open_term_risk` 要统一
repair 草稿同样可能引入未界定术语；若仅 MB 有该字段，下游无法统一执行术语风险审查。

**可推翻条件**：若实际实现证明 repair 从不产生新的开放术语风险，则可把 `open_term_risk` 改为可选或延后到 compile 产物中生成。

---

## C. 子类型/协议设计：CC 与 is_homologous 的最终接口

**结论**：  
- `compile()` 接收统一协议 `HypothesisDraft`
- `is_homologous()` 也接收统一协议 `HypothesisDraft`
- 生产侧通过 normalizer 保证任何来源进入共享层前都满足协议

这样，**跨来源比较自然成立**：MB 与 repair 可比较，因为比较的是统一语义表征，而 provenance 只作为解释辅助，不作为主分支条件。

**可推翻条件**：若跨来源比较经实验证明大量误报，且误报原因不可通过统一特征抽取修正，则应改为 `is_homologous(a: MBDraft|RepairDraft, b: MBDraft|RepairDraft, adapters...)` 的双分派设计。

---

## D. `compute_semantic_similarity()` 与 `is_homologous()` 的关系

**结论：二者独立实现，不共用同名语义；但遵守共同约定。**

### 裁定理由
- `compute_semantic_similarity()`：测量**语义邻近度**，用于 MB 多样性优化
- `is_homologous()`：判断**是否探索同一知识空间**，用于去重/归并/repair 过滤
- 语义相似 ≠ 同知识空间  
  例如：
  - “提高碳税能减排”
  - “提高碳税会抑制高排放产业投资”
  
  文本语义相近，但在验证结构、结果变量、证据要求上未必同空间。

因此，不应把二者合并为一个总分函数。

### 共同遵守的约定
```ts
type SimilarityScore = number; // [0, 1]
```

- `compute_semantic_similarity(a, b) -> number in [0,1]`
- `is_homologous(a, b, opts) -> HomologyResult`
- `HomologyResult.score in [0,1]`
- `HomologyResult.is_homologous` 由结构特征为主、语义特征为辅决定

**可推翻条件**：若后续离线评测表明一个统一的 learned metric 在 MB 去重与 repair 同源判定上同时优于二者分离方案，则可改为共用底层实现、保留两个包装函数。

---

# 三、HypothesisDraft 最终完整类型定义（TypeScript）

以下是我主张的**最终规范**。

```typescript
/** 草稿来源：仅用于溯源与解释，不应成为 CC 的主分支条件 */
type DraftOrigin = "MB" | "REPAIR";

/** 统一的张力层级。MB 来自问题框架张力；repair 来自 L2 失败反馈。 */
type TensionTier =
  | "INTERNAL_AXIS"   // 问题框架内部评价轴张力
  | "EMPIRICAL"       // 经验层冲突/外部立场碰撞
  | "L2_FAILURE";     // 来自 GapSpec / SchemaChallenge 的修复性张力

/** 张力类型：允许扩展，但建议受控枚举 */
type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT"
  | "GAP_FILL"
  | "SCHEMA_CHALLENGE"
  | "VERIFIER_MISMATCH"
  | "SCOPE_REPAIR"
  | "OTHER";

/**
 * 统一张力来源描述。
 * 注意：这是 draft 的认识论来源说明，不等同于来源类型 MB/REPAIR。
 */
interface TensionSource {
  /** 张力/修复触发的主要类型 */
  kind: TensionKind;

  /**
   * 认识论层级：
   * - INTERNAL_AXIS / EMPIRICAL：多见于 MB
   * - L2_FAILURE：多见于 repair
   */
  tier: TensionTier;

  /**
   * 外部证据、轴 id、gap id、challenge id 等引用。
   * CC/审计器可用其生成 falsifier 或回溯触发原因。
   */
  evidence_ref: string[];

  /**
   * 人类可读说明。用于解释“为何产生此草稿”。
   * 不应替代结构化字段，但可补足 context。
   */
  note: string;
}

/** MB 特有的池管理预算。repair 不应伪装持有该字段。 */
interface MBBudget {
  /** 草稿还能在 MB/RB 候选池中存活多少个 epoch */
  ttl: number;
}

/** repair 特有的修复溯源 */
interface RepairProvenance {
  source_gap_id?: string;
  source_challenge_id?: string;
  repair_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
}

/** 统一 provenance。必须保留 origin，但下游语义消费者不应据此主分支。 */
interface DraftProvenance {
  /** 该 draft 最初来自 MB 还是 repair */
  origin: DraftOrigin;

  /** 产生该 draft 的 layer1 epoch */
  epoch: number;

  /**
   * 产生此草稿的上游候选/节点引用。
   * MB 可填 tension candidate id；repair 可填 gap/challenge 派生链路 id。
   */
  derivation_ref: string[];

  /**
   * 来源特有细节：
   * - MB: 可有 budget
   * - REPAIR: 可有 repair
   */
  mb?: {
    budget: MBBudget;
  };

  repair?: RepairProvenance;
}

/**
 * 统一消费协议：任何进入 CC / homologous / pool-merge 的草稿都必须先被规范化到此类型。
 *
 * 设计原则：
 * - 顶层字段只放跨来源都有明确语义者
 * - 来源特有字段进入 provenance 子结构
 * - 不允许“名义上存在但语义为空”的伪必填字段
 */
interface HypothesisDraft {
  /** 全局唯一草稿 id */
  draft_id: string;

  /** 所属问题 id。repair 必须由 L1 上下文恢复填写。 */
  problem_id: string;

  /**
   * 命题草图：待编译为 TestableClaim / RegulativeIdea 的核心自然语言断言。
   */
  claim_sketch: string;

  /**
   * scope 的结构化引用。
   * 必填，且禁止空数组：
   * - MB 必须在产出时推导出 scope
   * - repair 必须从 GapSpec / originating claim / frame 恢复
   */
  scope_ref: string[];

  /**
   * 验证提示，统一为数组。
   * 语义：建议使用哪些检验器、比较组、观测变量、数据源。
   */
  verifier_hint: string[];

  /**
   * 开放术语风险列表。
   * 若为空，表示“当前未识别到明显 open term”，不是“已证明无风险”。
   */
  open_term_risk: string[];

  /**
   * 触发此草稿生成的张力来源。
   * 对 MB 与 repair 均有语义，但 tier/kind 分布不同。
   */
  tension_source: TensionSource;

  /**
   * 统一溯源信息：
   * - origin 表明认识来源
   * - mb/repair 子结构保留来源特有信息
   */
  provenance: DraftProvenance;
}
```

---

# 四、生产侧规范化函数

为了避免把来源差异塞进 CC，我主张显式 normalizer。

```typescript
interface MBDraftInput {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  tension_source: {
    kind: "EXTERNAL_POSITION" | "STAKEHOLDER_CONFLICT" | "EVALUATION_AXIS_SPLIT";
    tier: "INTERNAL_AXIS" | "EMPIRICAL";
    evidence_ref: string[];
    note: string;
  };
  verifier_hint: string[];
  open_term_risk: string[];
  ttl: number;
  // MB 内部可以还带 axis_ids 等字段
  axis_ids?: string[];
}

interface RepairDraftInput {
  draft_id: string;
  claim_sketch: string;
  scope_ref: string[];
  tension_source: { kind: string; detail: string };
  verifier_hint: string | string[];
  provenance: {
    source_gap_id?: string;
    source_challenge_id?: string;
    repair_stage: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
    epoch: number;
  };
}

function normalize_mb_draft(
  input: MBDraftInput,
  ctx: { epoch: number; derive_scope_ref: (claim: string, problem_id: string) => string[]; derivation_ref?: string[] }
): HypothesisDraft {
  const scope_ref = ctx.derive_scope_ref(input.claim_sketch, input.problem_id);
  if (scope_ref.length === 0) {
    throw new Error(`MB draft ${input.draft_id} cannot be normalized: empty scope_ref`);
  }

  return {
    draft_id: input.draft_id,
    problem_id: input.problem_id,
    claim_sketch: input.claim_sketch,
    scope_ref,
    verifier_hint: input.verifier_hint,
    open_term_risk: input.open_term_risk,
    tension_source: input.tension_source,
    provenance: {
      origin: "MB",
      epoch: ctx.epoch,
      derivation_ref: ctx.derivation_ref ?? [],
      mb: {
        budget: { ttl: input.ttl }
      }
    }
  };
}

function normalize_repair_draft(
  input: RepairDraftInput,
  ctx: {
    problem_id: string;
    infer_open_term_risk: (claim: string) => string[];
    derivation_ref?: string[];
  }
): HypothesisDraft {
  if (input.scope_ref.length === 0) {
    throw new Error(`Repair draft ${input.draft_id} cannot be normalized: empty scope_ref`);
  }

  return {
    draft_id: input.draft_id,
    problem_id: ctx.problem_id,
    claim_sketch: input.claim_sketch,
    scope_ref: input.scope_ref,
    verifier_hint: Array.isArray(input.verifier_hint) ? input.verifier_hint : [input.verifier_hint],
    open_term_risk: ctx.infer_open_term_risk(input.claim_sketch),
    tension_source: {
      kind: (input.tension_source.kind as TensionKind) ?? "OTHER",
      tier: "L2_FAILURE",
      evidence_ref: [
        ...(input.provenance.source_gap_id ? [input.provenance.source_gap_id] : []),
        ...(input.provenance.source_challenge_id ? [input.provenance.source_challenge_id] : []),
      ],
      note: input.tension_source.detail
    },
    provenance: {
      origin: "REPAIR",
      epoch: input.provenance.epoch,
      derivation_ref: ctx.derivation_ref ?? [],
      repair: {
        source_gap_id: input.provenance.source_gap_id,
        source_challenge_id: input.provenance.source_challenge_id,
        repair_stage: input.provenance.repair_stage
      }
    }
  };
}
```

---

# 五、CC 的 `compile()` 函数签名与失败路径

**立场：CC 只接受统一 `HypothesisDraft`；失败是显式结果，不抛业务异常。**

```typescript
interface QuestionFrame {
  problem_id: string;
  normalized_question: string;
  evaluation_axes: Array<{ axis_id: string; label: string }>;
  stakeholders?: string[];
}

interface CompileOptions {
  strict_scope?: boolean;
  require_falsifier?: boolean;
}

interface TestableClaim {
  kind: "TESTABLE_CLAIM";
  claim_id: string;
  problem_id: string;
  proposition: string;
  scope: string[];
  accept_test: string[];
  falsifier: string[];
}

interface RegulativeIdea {
  kind: "REGULATIVE_IDEA";
  claim_id: string;
  problem_id: string;
  proposition: string;
  reason: string;
}

interface CompileError {
  kind: "COMPILE_ERROR";
  code:
    | "EMPTY_SCOPE"
    | "AMBIGUOUS_SCOPE"
    | "OPEN_TERM_UNRESOLVED"
    | "INSUFFICIENT_VERIFIER_HINT"
    | "FRAME_MISMATCH"
    | "UNCOMPILABLE_CLAIM";
  message: string;
  draft_id: string;
  problem_id: string;
  diagnostics: string[];
}

type CompileResult = TestableClaim | RegulativeIdea | CompileError;

function compile(
  draft: HypothesisDraft,
  frame: QuestionFrame,
  opts: CompileOptions = {}
): CompileResult {
  if (draft.problem_id !== frame.problem_id) {
    return {
      kind: "COMPILE_ERROR",
      code: "FRAME_MISMATCH",
      message: "Draft problem_id does not match QuestionFrame",
      draft_id: draft.draft_id,
      problem_id: draft.problem_id,
      diagnostics: [frame.problem_id]
    };
  }

  if (draft.scope_ref.length === 0) {
    return {
      kind: "COMPILE_ERROR",
      code: "EMPTY_SCOPE",
      message: "Draft has no scope_ref after normalization",
      draft_id: draft.draft_id,
      problem_id: draft.problem_id,
      diagnostics: []
    };
  }

  if (opts.strict_scope && draft.scope_ref.some(s => s.trim() === "")) {
    return {
      kind: "COMPILE_ERROR",
      code: "AMBIGUOUS_SCOPE",
      message: "Draft scope_ref contains ambiguous items",
      draft_id: draft.draft_id,
      problem_id: draft.problem_id,
      diagnostics: draft.scope_ref
    };
  }

  if (draft.open_term_risk.length > 0 && draft.verifier_hint.length === 0) {
    return {
      kind: "COMPILE_ERROR",
      code: "OPEN_TERM_UNRESOLVED",
      message: "Open-term risk exists without verifier support",
      draft_id: draft.draft_id,
      problem_id: draft.problem_id,
      diagnostics: draft.open_term_risk
    };
  }

  // 伪代码：用统一字段合成
  const falsifier = synthesizeFalsifier(draft.tension_source, frame, draft.scope_ref);
  const acceptTest = synthesizeAcceptTest(draft.verifier_hint, draft.scope_ref);

  if (opts.require_falsifier && falsifier.length === 0) {
    return {
      kind: "COMPILE_ERROR",
      code: "UNCOMPILABLE_CLAIM",
      message: "Unable to synthesize falsifier",
      draft_id: draft.draft_id,
      problem_id: draft.problem_id,
      diagnostics: [draft.tension_source.kind, draft.tension_source.note]
    };
  }

  if (acceptTest.length === 0) {
    return {
      kind: "REGULATIVE_IDEA",
      claim_id: `ri_${draft.draft_id}`,
      problem_id: draft.problem_id,
      proposition: draft.claim_sketch,
      reason: "Claim is meaningful but lacks a sufficiently operational accept_test"
    };
  }

  return {
    kind: "TESTABLE_CLAIM",
    claim_id: `tc_${draft.draft_id}`,
    problem_id: draft.problem_id,
    proposition: draft.claim_sketch,
    scope: draft.scope_ref,
    accept_test: acceptTest,
    falsifier
  };
}
```

### 要点
- CC 不看 `origin`
- CC 可看 `tension_source.tier`，因为这是**编译语义字段**，不是来源标签
- 失败路径显式返回 `CompileError`

**可推翻条件**：若 compile 过程中被证明必须直接读取 `repair_stage` 或 `ttl` 才能决定编译结果，则说明统一协议抽象失败。

---

# 六、`is_homologous()` 的最终函数签名与跨来源处理

**立场：`is_homologous()` 是二元关系，输入统一 `HypothesisDraft`；跨来源比较合法，且必须支持。**

```typescript
interface HomologyFeatures {
  scope_tokens: string[];
  outcome_tokens: string[];
  polarity_tokens: string[];
  verifier_tokens: string[];
  semantic_text: string;
}

interface HomologyResult {
  is_homologous: boolean;
  score: number; // [0, 1]
  reasons: string[];
  feature_overlap: {
    scope_jaccard: number;
    outcome_jaccard: number;
    polarity_jaccard: number;
    verifier_jaccard: number;
    semantic_similarity: number;
  };
}

interface HomologyOptions {
  scope_threshold?: number;      // default 0.8
  semantic_threshold?: number;   // default 0.88
  final_threshold?: number;      // default 0.82
}

function is_homologous(
  a: HypothesisDraft,
  b: HypothesisDraft,
  opts: HomologyOptions = {}
): HomologyResult {
  const fa = extract_homology_features(a);
  const fb = extract_homology_features(b);

  const scope_j = jaccard(fa.scope_tokens, fb.scope_tokens);
  const outcome_j = jaccard(fa.outcome_tokens, fb.outcome_tokens);
  const polarity_j = jaccard(fa.polarity_tokens, fb.polarity_tokens);
  const verifier_j = jaccard(fa.verifier_tokens, fb.verifier_tokens);
  const sem = compute_semantic_similarity(fa.semantic_text, fb.semantic_text);

  // 结构主导，语义辅助
  const structural =
    0.40 * scope_j +
    0.25 * outcome_j +
    0.15 * polarity_j +
    0.20 * verifier_j;

  const score = 0.75 * structural + 0.25 * sem;

  const finalThreshold = opts.final_threshold ?? 0.82;
  const isSameSpace =
    score >= finalThreshold ||
    (scope_j >= (opts.scope_threshold ?? 0.8) &&
      sem >= (opts.semantic_threshold ?? 0.88));

  return {
    is_homologous: isSameSpace,
    score,
    reasons: explain_homology(scope_j, outcome_j, polarity_j, verifier_j, sem, a, b),
    feature_overlap: {
      scope_jaccard: scope_j,
      outcome_jaccard: outcome_j,
      polarity_jaccard: polarity_j,
      verifier_jaccard: verifier_j,
      semantic_similarity: sem
    }
  };
}
```

### 跨来源如何处理
不写：

```python
if a.provenance.origin != b.provenance.origin: ...
```

而是统一抽取特征：

```typescript
function extract_homology_features(d: HypothesisDraft): HomologyFeatures {
  return {
    scope_tokens: normalizeScope(d.scope_ref),
    outcome_tokens: extractOutcomeTokens(d.claim_sketch),
    polarity_tokens: extractPolarityTokens(d.claim_sketch),
    verifier_tokens: normalizeVerifierHints(d.verifier_hint),
    semantic_text: d.claim_sketch
  };
}
```

来源差异保留在 provenance 中，仅用于解释理由，例如：
- “cross-origin homologous: MB axis candidate overlaps REPAIR gap-fill claim”

**可推翻条件**：若实验显示 cross-origin 比较中 provenance 必须参与判定本身，否则误报率不可接受，则应把 provenance-derived priors 显式纳入 `HomologyFeatures`，但仍不应退回来源硬分支。

---

# 七、`compute_semantic_similarity()` 与 `is_homologous()`：独立实现，但共同约定

**最终结论：独立，不共用实现。**

```typescript
function compute_semantic_similarity(
  textA: string,
  textB: string
): number {
  // return [0,1]
  return 0.0;
}
```

### 共同约定
1. 输入均可由 `HypothesisDraft` 投影获得
2. 分值范围均为 `[0,1]`
3. `compute_semantic_similarity()` 不直接作去重裁决
4. `is_homologous()` 可以调用 `compute_semantic_similarity()`，但其判定不得退化为纯 embedding 阈值

换言之：

- **允许调用**
- **不允许语义等同**

这一区分极重要。  
前者是度量，后者是判断；前者可高而后者仍为 false。

**可推翻条件**：若长期评测证明 `extract_homology_features` 的结构部分对结果无实质贡献，则可把 `is_homologous` 简化为 semantic metric + scope prior。

---

# 八、方案最可能失败的场景

我不回避失败边界。此方案最危险的失败点在于：**统一协议要求 `scope_ref` 必填，而某些 MB 草稿在早期只具有价值张力，没有稳定 scope。**

## 具体失败输入 1：MB 价值冲突草稿，scope 无法可靠抽取

```typescript
const mbInput: MBDraftInput = {
  draft_id: "d1",
  problem_id: "p1",
  claim_sketch: "平台治理应优先维护公共讨论质量而非绝对言论自由",
  tension_source: {
    kind: "EVALUATION_AXIS_SPLIT",
    tier: "INTERNAL_AXIS",
    evidence_ref: ["axis:public_quality", "axis:free_speech"],
    note: "normative axis split"
  },
  verifier_hint: [],
  open_term_risk: ["公共讨论质量", "绝对言论自由"],
  ttl: 2
};
```

若 `derive_scope_ref()` 只能得到空结果，则该 draft 无法规范化进入统一流水线。

### 这意味着什么
它说明：**不是所有 MB 草稿都已达 HypothesisDraft 层级。**  
有些只是 pre-draft / ideation seed，应先经过 scope concretizer，再能进入 CC。

因此此失败不是偶然 bug，而是对接口边界的提醒：  
`HypothesisDraft` 不是“所有广度产物”的容器，而是“已足以接受编译审查的草稿”。

---

## 具体失败输入 2：跨来源术语替换导致错误 homologous

```typescript
const a: HypothesisDraft = {
  draft_id: "mb1",
  problem_id: "p1",
  claim_sketch: "提高碳税会减少高排放行业总排放",
  scope_ref: ["policy:carbon_tax", "sector:high_emission"],
  verifier_hint: ["emission panel data"],
  open_term_risk: [],
  tension_source: {
    kind: "EVALUATION_AXIS_SPLIT",
    tier: "EMPIRICAL",
    evidence_ref: [],
    note: ""
  },
  provenance: { origin: "MB", epoch: 0, derivation_ref: [], mb: { budget: { ttl: 2 } } }
};

const b: HypothesisDraft = {
  draft_id: "r1",
  problem_id: "p1",
  claim_sketch: "提高碳税会抑制高排放行业资本开支",
  scope_ref: ["policy:carbon_tax", "sector:high_emission"],
  verifier_hint: ["firm capex filings"],
  open_term_risk: [],
  tension_source: {
    kind: "GAP_FILL",
    tier: "L2_FAILURE",
    evidence_ref: ["gap:g1"],
    note: ""
  },
  provenance: { origin: "REPAIR", epoch: 1, derivation_ref: [], repair: { source_gap_id: "g1", repair_stage: "STRICT" } }
};
```

两者 scope 很近，语义也近，但 outcome 不同：一个是排放，一个是资本开支。  
若 `extractOutcomeTokens()` 抽取失败，`is_homologous()` 可能误判为同空间。

### 这暴露的失败边界
同源判定高度依赖 outcome/polarity 抽取质量。  
若 NLP 特征提取差，结构主导策略也会退化。

---

# 九、我接受什么反例来推翻本设计

以下反例若被稳定复现，我接受修订甚至推翻：

### 反例 1：`scope_ref` 必填导致大量高价值 MB 草稿无法进入系统
若在真实数据中，超过可接受比例的 MB 候选在早期无法稳定抽取 `scope_ref`，且这些候选后续经人工确认确有高价值，那么我接受引入：

```typescript
type PreHypothesisSeed = {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  tension_source: TensionSource;
}
```

并承认当前 `HypothesisDraft` 设得过晚。

### 反例 2：provenance 不参与同源判定会造成系统性误报
若 cross-origin 情况下，结构+语义特征持续把“修复性补足”误判为“重复命题”，导致 ranking-changing repair 被错误过滤，我接受把 provenance 派生特征加入判定，例如：

```typescript
interface HomologyFeatures {
  ...
  origin_role_tokens: string[]; // e.g. gap-fill, axis-split
}
```

### 反例 3：CC 实际上必须读取 `repair_stage`
若 compile 结果在实务上依赖“这是 STRICT repair 还是 ADJACENT repair”，我接受 CC 接口扩展为：

```typescript
function compile(draft: HypothesisDraft, frame: QuestionFrame, ctx?: { repair_stage?: string }): CompileResult;
```

这将说明当前“编译只依赖语义结构”的假设不充分。

---

# 十、最终结论，压缩表述

## 最终立场
- **A：选 A3，统一消费协议，不统一生产本体**
- **B：顶层只保留跨来源有真语义的字段；`ttl` 下沉到 `provenance.mb.budget`**
- **C：CC 与 `is_homologous()` 都只接收统一 `HypothesisDraft`**
- **D：`compute_semantic_similarity()` 与 `is_homologous()` 独立；前者是度量，后者是判定**

## 最终判断依据
统一是必要的，但统一必须止于**可公共消费的先验条件**；不能把来源差异伪装成同一本体的空字段。  
换言之：

> **可编译性应统一，生成根据不应抹平。**

这就是我给出的最终 `HypothesisDraft` 规范。

---


### [13] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-09T19:01:40.230047*

# 裁判裁定书

---

## 第一部分：白话版结论

### 问题 A：MB 草稿和 repair 草稿应该用同一个类型，还是分成两个子类型？

**裁定：采用"规范化统一消费类型 + 上游允许各自原始类型"的方案。**

这不是 Linus 最初的"一个大结构体打天下"，也不是 Ssyram/康德的"两个子类型 + 薄薄的公共接口"。裁定的方案是：**存在一个完整的、语义封闭的 `HypothesisDraft` 统一类型，它是 CC、is_homologous()、池管理、终止报告等所有共享消费者的唯一输入；但 MB 和 repair 在各自的生产函数内部可以先用自己的中间结构，只要在进入共享流水线之前必须通过一个规范化工厂函数转换为统一类型。**

**日常比喻**：想象一个国际邮局。中国寄来的包裹有中文面单，德国寄来的有德文面单，格式完全不同。但进入分拣流水线之前，每个包裹都必须贴上一张统一格式的国际标签——收件人、重量、目的地、是否易碎，全部用同一套字段填写。分拣员只看这张标签，不需要去读原始面单。但这张标签上的每个字段都必须有真实含义，不能因为中国包裹没有"易碎"概念就随便填个"否"——如果里面真的是瓷器，那就必须标"是"。

**具体场景举例**：当系统同时持有一个 MB 草稿（"利益相关者对碳税效果存在分歧"）和一个 repair 草稿（"L2 验证发现碳税假设缺少发展中国家视角"），`is_homologous()` 需要判断它们是否在探索同一个知识空间。如果用两个不同的子类型，这个函数要么写 `if-else` 分支（Linus 正确指出的问题），要么只看一个过于贫瘠的公共基类（康德和 Ssyram 的 Base 缺少 `problem_id`、`open_term_risk` 等字段）。统一类型让这个比较在同一个字段集合上进行，无需类型判断。

**关键裁定理由**：

1. **Linus 赢在核心论点上**：CC 和 `is_homologous()` 确实不应该因为草稿来源不同而写分支逻辑。三位辩手最终都承认了这一点（康德最终版的 `CompilableDraft` 和 Ssyram 最终版的 `DraftCore` 实质上都在向统一消费类型靠拢）。

2. **康德和 Ssyram 赢在一个关键修正上**：`ttl` 不应该作为统一类型的必填字段。Ssyram 的论证是决定性的——repair 草稿的生命周期由 L2 ChallengeTracker 的 stage 状态机管理，而 MB 草稿的生命周期由广度池 TTL 衰减管理。强行统一 `ttl` 会导致 repair 草稿被错误淘汰，切断 CEGAR 反馈回路。这不是"名义上有语义上空"的抽象批评，而是一个可以直接导致系统终止条件永远无法满足的具体 bug。

3. **Ssyram 的"编译投影"方案被否决**：把 `tension_source` 降格为只含 `synthesis_route` 和 `falsifier_hints` 的 `CompilableTension`，会丢失 debug tracing、终止解释、同源性比较所需的原始语义信息。康德对此的攻击是精确的。

**需要修正的场景**：如果未来系统明确裁定所有草稿（无论来源）进入同一个候选池并由统一的淘汰机制管理，则 `ttl` 可以回到统一类型的必填字段中。

**一句话总结**：统一消费类型是对的，但 `ttl` 和 `repair_stage` 等生命周期字段必须放在 `provenance` 的来源特定子结构中，而非作为顶层必填字段。

---

### 问题 B：字段合并与规范化规则

**裁定：`scope_ref`、`verifier_hint`、`open_term_risk`、`tension_source` 全部统一为必填字段，但 MB 必须在产出时强制推导 `scope_ref`（禁止空数组），repair 必须将单个 `verifier_hint` 字符串包装为数组。**

**日常比喻**：就像工厂质检——每个产品出厂前都必须填写完整的检验报告。不能因为某条生产线"通常不测这个指标"就留空。如果你的生产线确实无法测量某个指标，那说明你的生产线需要升级，而不是检验报告需要删字段。

**具体场景举例**：MB 产出一个草稿时，如果 `scope_ref` 为空数组 `[]`，那么当 `is_homologous()` 用 Jaccard 相似度比较这个 MB 草稿和一个 repair 草稿（`scope_ref: ["economic_impact", "developing_nations"]`）时，Jaccard 系数恒为 0，系统会认为它们完全不同源——即使它们的 `claim_sketch` 几乎一样。这是 Linus 在交叉质询中精确指出的偏置问题。因此 MB 必须在产出时从 `QuestionFrame` 的 `evaluation_axes` 和 `stakeholder_map` 中推导出 `scope_ref`。

**关键裁定细节**：

| 字段 | MB 规范化规则 | Repair 规范化规则 |
|------|-------------|-----------------|
| `scope_ref` | 从 QuestionFrame 推导，禁止 `[]` | 从 GapSpec 继承，必填 |
| `verifier_hint` | 已经是 `string[]`，保持 | 单 string 包装为 `[string]` |
| `open_term_risk` | 原生产出 | 从 L2 失败上下文推导，允许 `[]` |
| `tension_source.tier` | 原生值 | `"L2_FAILURE"`（这是真实语义，不是占位） |
| `tension_source.evidence_ref` | 原生值 | 从 challenge 上下文提取，允许 `[]` |
| `problem_id` | 原生值 | 由 L1 调度层从 `claim_to_problem` 映射注入 |

**需要修正的场景**：如果 L2 返回的结构性失败确实无法稳定映射回 `problem_id`（例如跨多个 problem 的系统性 schema 失败），则需要引入 `problem_id: string | string[]` 或额外的映射机制。

**一句话总结**：所有共享消费字段必填，但"必填"意味着上游必须做真实推导，不是填默认值糊弄。

---

### 问题 C：CC compile() 的接口设计

**裁定：`clarity_compile()` 接受统一的 `HypothesisDraft`，内部可以根据 `tension_source.kind` 和 `tension_source.tier` 进行语义分支，但绝对禁止根据 `provenance.source` 进行来源分支。**

**日常比喻**：一个翻译官接到一份文件，他可以根据文件的主题（科技论文 vs 法律合同 vs 医学报告）选择不同的翻译策略——这是合法的语义分支。但他不应该根据"这份文件是从北京寄来的还是从柏林寄来的"来决定翻译策略——这是非法的来源分支。文件的主题恰好和来源有相关性（北京寄来的更可能是中文科技论文），但翻译策略应该基于主题本身，不是邮戳。

**具体场景举例**：CC 收到一个 `tension_source.kind = "GAP_REPAIR"` 且 `tier = "L2_FAILURE"` 的草稿。CC 知道这意味着需要构造一个针对特定知识缺口的证伪器，所以它会从 `evidence_ref` 中提取缺口描述来生成 falsifier。CC 不需要知道这个草稿来自 repair 模块——它只需要知道张力类型是 GAP_REPAIR。如果未来 MB 也能产出 GAP_REPAIR 类型的草稿（比如在初始分析中就发现了知识缺口），CC 的逻辑完全不需要改动。

**这解决了 Ssyram 的核心质疑**："CC 终究会按 kind/tier 分发，这与知道来源有何区别？"区别在于：按 `kind/tier` 分发是基于**编译所需的语义维度**，按 `source` 分发是基于**生产来源的偶然事实**。前者是稳定的（语义不变则逻辑不变），后者是脆弱的（新来源出现则逻辑必须改）。康德在最终轮对此的阐述是精确的。

**需要修正的场景**：如果未来发现某些编译策略确实只对 repair 草稿有意义（例如需要读取 `repair_stage` 来决定证伪器的严格程度），则应将 `repair_stage` 提升为 `tension_source` 的可选子字段，而非让 CC 去读 `provenance`。

**一句话总结**：CC 按语义分支，不按来源分支；如果某个来源特有的信息确实影响编译，就把它提升为语义字段。

---

### 问题 D：`compute_semantic_similarity()` 和 `is_homologous()` 的关系

**裁定：两者不应共用实现，但应共用底层特征提取工具。`is_homologous()` 是知识空间同一性的二值判断，`compute_semantic_similarity()` 是多样性优化的连续度量。**

**日常比喻**：图书管理员有两个任务。任务一：判断两本书是不是同一本书的不同版本（`is_homologous`）——即使封面不同、章节顺序不同，只要核心内容讲的是同一件事，就算同源。任务二：给书架上的书打多样性分数（`compute_semantic_similarity`）——两本都讲经济学但一本侧重宏观一本侧重微观，相似度高但不同源。管理员可以共用"读目录、提取关键词"这个基础技能，但判断逻辑完全不同。

**具体场景举例**：
- MB 草稿 A："碳税会降低 GDP 增长率"（scope: [economic_impact, gdp]）
- Repair 草稿 B："碳税对发展中国家 GDP 的影响被低估"（scope: [economic_impact, gdp, developing_nations]）
- MB 草稿 C："碳税会促进绿色技术创新"（scope: [innovation, green_tech]）

`is_homologous(A, B)` 应返回 `true`——它们探索的是同一个知识空间（碳税对 GDP 的影响），B 只是 A 的精化修复。
`compute_semantic_similarity(A, C)` 应返回一个中等值（比如 0.4）——它们都关于碳税，但探索不同维度，应该保留多样性。
`is_homologous(A, C)` 应返回 `false`——它们不是同一个知识空间的变体。

如果共用实现，你要么把二值判断做成"阈值切割连续分数"（丢失结构信息），要么把连续度量做成"二值判断的软化"（引入不必要的复杂性）。

**关键接口关系**：
- 共用：`extract_homology_features(draft: HypothesisDraft) → HomologyFeatures`（提取 claim tokens、scope set、tension kind）
- 分离：`is_homologous()` 在 features 上做 Jaccard + claim overlap 的复合判断，输出 boolean
- 分离：`compute_semantic_similarity()` 在 features 上做 embedding cosine similarity，输出 [0,1] 浮点数

**需要修正的场景**：如果实践中发现 `is_homologous()` 的硬阈值导致大量边界案例误判，可以考虑让它也输出置信度分数，但判断逻辑仍应独立于相似度计算。

**一句话总结**：共用特征提取，分离判断逻辑；同源性是"是不是同一本书的不同版本"，相似度是"两本书有多像"。

---

## 第二部分：可实现性摘要

### 1. HypothesisDraft 最终完整 TypeScript 类型定义

**方案选择：统一类型方案（修正版 A1）。**

理由：三位辩手最终都收敛到了"CC 和 is_homologous() 需要一个完整的、不需要类型判断的输入"这一共识。子类型方案（A2/A3）在理论上优美，但在实践中要么导致公共基类过于贫瘠（Ssyram 的 Base 缺少 `problem_id`、`open_term_risk`），要么导致公共协议膨胀到与统一类型无实质区别（康德最终版的 `CompilableDraft` 已经包含了几乎所有字段）。选择统一类型，但将生命周期管理字段隔离到 `provenance` 子结构中。

```typescript
// ============================================================
// 枚举与基础类型
// ============================================================

type DraftId = string;
type ProblemId = string;
type Epoch = number;

type DraftSource = "MB" | "REPAIR";

type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT"
  | "GAP_REPAIR"
  | "SCHEMA_REPAIR"
  | "OTHER";

type EpistemicTier =
  | "INTERNAL_AXIS"    // MB: 内部评价轴冲突
  | "EMPIRICAL"        // MB: 经验性可检验分歧
  | "L2_FAILURE"       // Repair: 来自 L2 验证失败
  | "STRUCTURAL";      // Repair: 结构性 schema 问题

// ============================================================
// 核心统一类型
// ============================================================

interface TensionSource {
  kind: TensionKind;
  tier: EpistemicTier;
  evidence_ref: string[];   // MB: 原生证据引用; Repair: 从 challenge 上下文提取, 允许 []
  note: string;             // MB: 张力描述; Repair: gap/challenge 描述
}

interface Provenance {
  source: DraftSource;
  epoch: Epoch;

  // === MB 特有（Repair 时为 undefined）===
  ttl?: number;                    // 仅 MB 草稿使用的广度池生存预算

  // === Repair 特有（MB 时为 undefined）===
  source_gap_id?: string;          // 触发修复的 GapSpec ID
  source_challenge_id?: string;    // 触发修复的 Challenge ID
  repair_stage?: "STRICT" | "RELAXED" | "ADJACENT" | "EXHAUSTED";
}

interface HypothesisDraft {
  // --- 核心标识 ---
  draft_id: DraftId;
  problem_id: ProblemId;           // 必填。MB 原生; Repair 由 L1 调度层注入

  // --- 语义内容 ---
  claim_sketch: string;            // 假设的自然语言草稿
  scope_ref: string[];             // 必填且禁止空数组。MB 从 QF 推导; Repair 从 GapSpec 继承
  verifier_hint: string[];         // 统一为数组。Repair 的单 string 包装为 [string]
  open_term_risk: string[];        // MB 原生; Repair 从 L2 失败上下文推导, 允许 []

  // --- 张力来源 ---
  tension_source: TensionSource;

  // --- 来源与生命周期元数据 ---
  provenance: Provenance;
}
```

**设计决策说明**：

- `ttl` 放在 `provenance` 内且为可选：解决了 Ssyram/康德关于"repair 草稿被 TTL 误淘汰"的核心担忧，同时保留了 MB 草稿的广度池管理能力。池管理器读 `provenance.ttl`（存在则用 TTL 衰减，不存在则按 repair stage 管理），这是**基于字段存在性的分支**，不是基于 `source` 的分支。
- `scope_ref` 禁止空数组：解决了 Linus 指出的 Jaccard 偏置问题。
- `tension_source` 保留完整语义（`kind` + `tier` + `evidence_ref` + `note`）：解决了康德对 Ssyram "编译投影丢失信息"的攻击。
- `problem_id` 必填：采纳 Ssyram 的论证——CEGAR 闭环要求所有草稿可溯源到 QuestionFrame。

### 2. CC compile() 最终接口规范

```typescript
// ============================================================
// CC compile() 接口
// ============================================================

interface CompileResult {
  testable_claim: {
    claim_id: string;
    statement: string;           // 精确化后的可检验命题
    falsifier: string;           // 证伪条件
    boundary_conditions: string[];
  };
  verification_plan: {
    verifier_type: string;       // e.g., "EMPIRICAL_CHECK", "LOGICAL_AUDIT", "SCOPE_REVIEW"
    required_evidence: string[];
  };
  compile_warnings: string[];    // 编译过程中的风险提示
}

function clarity_compile(
  draft: HypothesisDraft,
  frame: QuestionFrame
): CompileResult;
```

**关键分支伪代码**：

```python
def clarity_compile(draft: HypothesisDraft, frame: QuestionFrame) -> CompileResult:
    # 1. 提取编译上下文（不读 provenance.source）
    tension = draft.tension_source

    # 2. 根据 tension.kind 选择证伪器合成策略
    if tension.kind in ("EXTERNAL_POSITION", "STAKEHOLDER_CONFLICT"):
        # 轴冲突类：从 evidence_ref 提取对立立场，构造对比证伪
        falsifier = synthesize_contrastive_falsifier(
            claim=draft.claim_sketch,
            evidence=tension.evidence_ref,
            axes=frame.evaluation_axes
        )
    elif tension.kind == "EVALUATION_AXIS_SPLIT":
        # 评价轴分裂：构造轴独立性证伪
        falsifier = synthesize_axis_independence_falsifier(
            claim=draft.claim_sketch,
            evidence=tension.evidence_ref
        )
    elif tension.kind in ("GAP_REPAIR", "SCHEMA_REPAIR"):
        # 修复类：从 note 提取缺口描述，构造覆盖性证伪
        falsifier = synthesize_coverage_falsifier(
            claim=draft.claim_sketch,
            gap_description=tension.note,
            scope=draft.scope_ref
        )
    else:
        # OTHER: 通用证伪
        falsifier = synthesize_generic_falsifier(draft.claim_sketch)

    # 3. 根据 tension.tier 调整验证计划
    if tension.tier == "EMPIRICAL":
        verifier_type = "EMPIRICAL_CHECK"
    elif tension.tier == "L2_FAILURE":
        verifier_type = "TARGETED_RECHECK"
    elif tension.tier == "STRUCTURAL":
        verifier_type = "LOGICAL_AUDIT"
    else:  # INTERNAL_AXIS
        verifier_type = "AXIS_CONSISTENCY_CHECK"

    # 4. 精确化 claim
    testable_claim = refine_claim(
        sketch=draft.claim_sketch,
        scope=draft.scope_ref,
        open_risks=draft.open_term_risk,
        hints=draft.verifier_hint,
        frame=frame
    )

    # 5. 组装结果
    return CompileResult(
        testable_claim=TestableClaim(
            claim_id=generate_id(),
            statement=testable_claim,
            falsifier=falsifier,
            boundary_conditions=derive_boundaries(draft.scope_ref, frame)
        ),
        verification_plan=VerificationPlan(
            verifier_type=verifier_type,
            required_evidence=tension.evidence_ref + draft.verifier_hint
        ),
        compile_warnings=check_open_term_risks(draft.open_term_risk)
    )
```

**注意**：整个函数中没有任何 `if draft.provenance.source == "MB"` 或 `if draft.provenance.source == "REPAIR"` 的分支。所有分支都基于 `tension_source.kind` 和 `tension_source.tier` 这两个语义维度。

### 3. is_homologous() 最终接口规范

```typescript
// ============================================================
// 同源性判定接口
// ============================================================

interface HomologyFeatures {
  claim_tokens: Set<string>;       // claim_sketch 的标准化 token 集合
  scope_set: Set<string>;          // scope_ref 的集合化表示
  tension_kind: TensionKind;
  problem_id: ProblemId;
}

function extract_homology_features(
  draft: HypothesisDraft
): HomologyFeatures;

function is_homologous(
  a: HypothesisDraft,
  b: HypothesisDraft,
  threshold?: { claim_jaccard: number; scope_jaccard: number }
): boolean;
```

**核心比较逻辑伪代码**：

```python
DEFAULT_CLAIM_THRESHOLD = 0.6
DEFAULT_SCOPE_THRESHOLD = 0.5

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
    threshold=None
) -> bool:
    fa = extract_homology_features(a)
    fb = extract_homology_features(b)

    # 1. 快速排除：不同 problem 的草稿不可能同源
    if fa.problem_id != fb.problem_id:
        return False

    # 2. Claim 内容重叠度
    claim_sim = jaccard(fa.claim_tokens, fb.claim_tokens)
    claim_thresh = threshold.claim_jaccard if threshold else DEFAULT_CLAIM_THRESHOLD

    # 3. Scope 重叠度
    scope_sim = jaccard(fa.scope_set, fb.scope_set)
    scope_thresh = threshold.scope_jaccard if threshold else DEFAULT_SCOPE_THRESHOLD

    # 4. 复合判断：claim 和 scope 都超过阈值才算同源
    #    注意：不检查 provenance.source，跨来源比较是正常场景
    return claim_sim >= claim_thresh and scope_sim >= scope_thresh
```

**设计说明**：
- `problem_id` 作为快速排除条件：不同问题框架下的草稿即使 claim 相似也不算同源。
- `tension_kind` 提取但未参与当前判断：预留给未来可能的精细化规则（例如 `GAP_REPAIR` 和 `EXTERNAL_POSITION` 即使 claim 相似也可能不同源）。
- 不使用 embedding cosine similarity：同源性是结构判断，不是语义相似度。

### 4. compute_semantic_similarity() 和 is_homologous() 的关系裁定

**裁定：共用特征提取接口，独立判断逻辑。**

```typescript
// 共用层
function extract_homology_features(draft: HypothesisDraft): HomologyFeatures;

// is_homologous(): 结构性二值判断
//   输入: 两个 HypothesisDraft
//   输出: boolean
//   方法: Jaccard on tokens + scope, 硬阈值
//   用途: 去重（MB 产出后去重, repair 产出后去重）

// compute_semantic_similarity(): 连续语义度量
//   输入: 两个 HypothesisDraft (或 TestableClaim)
//   输出: number ∈ [0, 1]
//   方法: embedding cosine similarity on claim_sketch
//   用途: 多样性优化（广度池排序, 假设集覆盖度评估）
```

**约定**：
- `is_homologous()` 返回 `true` 蕴含 `compute_semantic_similarity()` 返回高值（>0.6），但反之不成立。
- 两者不得互相调用。
- 如果未来需要"软同源性"（置信度），扩展 `is_homologous()` 的返回类型为 `{ homologous: boolean; confidence: number }`，但不合并到 `compute_semantic_similarity()` 中。

### 5. 完整数据流示意

```
┌─────────────────────────────────────────────────────────────────┐
│                        Layer 1 主循环                            │
│                                                                 │
│  ┌──────────┐    normalize_mb()     ┌──────────────────┐        │
│  │    MB     │ ──────────────────→  │                  │        │
│  │ (产出     │   RawMBDraft →       │  HypothesisDraft │        │
│  │  RawMB)   │   HypothesisDraft    │     候选池       │        │
│  └──────────┘                       │                  │        │
│                                     │  is_homologous() │        │
│                                     │  去重 ──────────→│ 去重后 │
│                                     │                  │ 的池   │
│                                     └────────┬─────────┘        │
│                                              │                  │
│                                              ▼                  │
│                                     ┌──────────────────┐        │
│                                     │  CC.compile()    │        │
│                                     │  (统一接口,       │        │
│                                     │   按 kind/tier   │        │
│                                     │   语义分支)       │        │
│                                     └────────┬─────────┘        │
│                                              │                  │
│                                              ▼                  │
│                                     ┌──────────────────┐        │
│                                     │  TestableClaim[] │        │
│                                     │  → 送入 Layer 2  │        │
│                                     └────────┬─────────┘        │
│                                              │                  │
│                          ┌───────────────────┘                  │
│                          ▼                                      │
│                 ┌──────────────────┐                             │
│                 │   Layer 2 验证    │                             │
│                 │   (D2 + 挑战者)   │                             │
│                 └────────┬─────────┘                             │
│                          │                                      │
│                          ▼ L2Return (含 GapSpec, Challenge)     │
│                 ┌──────────────────┐                             │
│                 │   Repair Block   │                             │
│                 │   (产出 RawRepair)│                             │
│                 └────────┬─────────┘                             │
│                          │                                      │
│                          ▼ normalize_repair()                   │
│                 ┌──────────────────┐                             │
│                 │ HypothesisDraft  │                             │
│                 │ (repair 来源)     │                             │
│                 └────────┬─────────┘                             │
│                          │                                      │
│                          ▼ is_homologous() 去重                 │
│                          │ (与池中已有草稿比较,                   │
│                          │  包括 MB 来源的草稿)                   │
│                          │                                      │
│                          ▼                                      │
│                 合并回 HypothesisDraft 候选池                    │
│                          │                                      │
│                          ▼                                      │
│                 CC.compile() → 新一轮 Layer 2                   │
│                          │                                      │
│                          ▼                                      │
│                 检查终止条件                                     │
│                 (连续两个 epoch 无 ranking-changing repair)      │
└─────────────────────────────────────────────────────────────────┘
```

**规范化工厂函数**：

```python
def normalize_mb(raw: RawMBDraft, frame: QuestionFrame) -> HypothesisDraft:
    assert len(raw.scope_ref) > 0 or infer_scope(raw, frame), "MB must have non-empty scope_ref"
    return HypothesisDraft(
        draft_id=raw.draft_id,
        problem_id=raw.problem_id,
        claim_sketch=raw.claim_sketch,
        scope_ref=raw.scope_ref or infer_scope(raw, frame),
        verifier_hint=raw.verifier_hint,  # 已经是 string[]
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
            ttl=raw.ttl  # MB 特有
        )
    )

def normalize_repair(raw: RawRepairDraft, ctx: RepairContext) -> HypothesisDraft:
    return HypothesisDraft(
        draft_id=generate_id(),
        problem_id=ctx.frame.problem_id,  # 由 L1 调度层注入
        claim_sketch=raw.claim_sketch,
        scope_ref=raw.scope_ref,  # 从 GapSpec 继承, 必填
        verifier_hint=[raw.verifier_hint] if isinstance(raw.verifier_hint, str) else raw.verifier_hint,
        open_term_risk=infer_open_term_risk(raw, ctx) or [],
        tension_source=TensionSource(
            kind=raw.tension_kind,  # "GAP_REPAIR" | "SCHEMA_REPAIR"
            tier="L2_FAILURE",
            evidence_ref=extract_evidence_from_challenge(ctx),
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
```

### 6. 实现难度最高的 2 个子问题及其风险

**风险 1：MB 阶段 `scope_ref` 的强制推导（难度：高）**

- **问题**：裁定要求 MB 产出时 `scope_ref` 禁止为空数组，必须从 QuestionFrame 推导。但 MB 的核心任务是发散性假设生成，此时 QuestionFrame 可能尚未完全成型（特别是第一个 epoch），evaluation_axes 可能不完整。
- **风险**：`infer_scope()` 的推导质量直接影响 `is_homologous()` 的准确性。如果推导出的 scope 过于宽泛（例如所有 MB 草稿都推导出 `["general"]`），Jaccard 会系统性地将不同草稿判为同源。
- **缓解措施**：为 `infer_scope()` 设置最低粒度要求（至少 2 个不同的 scope token），并在 normalize_mb 中加入断言检查。如果推导失败，应抛出编译错误而非静默填充。

**风险 2：跨来源 `is_homologous()` 的阈值校准（难度：高）**

- **问题**：MB 草稿和 repair 草稿的 `claim_sketch` 风格可能系统性不同（MB 倾向于探索性、宽泛的表述；repair 倾向于针对性、精确的表述）。固定的 Jaccard 阈值可能导致：阈值过高 → 跨来源同源草稿漏检 → 重复假设进入 L2；阈值过低 → 不同源草稿被错误折叠 → 知识空间覆盖度下降。
- **风险**：没有现成的标注数据来校准阈值，且 Jaccard 对 token 粒度高度敏感。
- **缓解措施**：初始阈值设为保守值（claim: 0.6, scope: 0.5），并在系统运行中收集 `is_homologous()` 的判断日志。引入可观测性钩子，允许在不改代码的情况下调整阈值。考虑在 Jaccard 之外引入 embedding cosine similarity 作为辅助信号（但不替代结构判断）。

---
