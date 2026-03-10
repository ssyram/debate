# v3 认知引擎缺失节点设计：GAP-3/6/8 Layer 1 三节点接口从零裁定 辩论日志

> 2026-03-10T15:35:57.314416

---


### [1] Linus Torvalds

*2026-03-10T15:31:58.088630*

下面是我对 GAP-3/6/8 的**第一轮裁定立场**。别再给我“语义上应该怎样”，我只接受：**类型、函数签名、失败路径、以及可推翻实验**。

---

## GAP-3（AS）：`AnswerSeed` 接口裁定

### 1) 裁定结论（类型 + 签名）

你们现在的 `AnswerSeed` 是个“半成品 JSON”。要同时满足：可给 UI/报告用、可审计、可重放、能表达“AS 被跳过”。所以我裁定为：**AnswerSeed 必须是 tagged union**，把“已产出”和“未产出”分开，别靠某个字段碰运气解释。

```ts
type IntegrityStatus = "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
type AxisId = string;
type EpochId = number;

interface AnswerSeedProduced {
  kind: "ANSWER_SEED";

  problem_id: string;
  epoch_id: EpochId;

  integrity_status: IntegrityStatus;
  termination_reason: string;

  top_claims: RankedClaim[];        // 长度 = top_k（或不足）
  top_k: number;                    // 明示：来自 PAState.termination_config.top_k

  // axis_id 维度报告：不是“平均分”，而是“该轴是否被最终答案覆盖”
  coverage_report: Record<AxisId, AxisCoverage>;

  // 给下游用的可读文本：可空，但必须给出生成状态/失败原因
  narrative: NarrativeBlock;

  // 可审计：告诉我这个 seed 依据哪些输入形成（最小可重放）
  provenance: {
    ranked_claim_ids: string[];     // pa_state.ranked_claims 的 claim_id 顺序快照
    evaluation_axis_ids: AxisId[];  // frame.evaluation_axes 快照
  };
}

interface AnswerSeedSkipped {
  kind: "ANSWER_SEED_SKIPPED";
  problem_id: string;
  epoch_id: EpochId;
  integrity_status: IntegrityStatus;
  termination_reason: string;
  skipped_because: "TERMINATED_BEFORE_AS" | "SIZE_LIMIT" | "INTERNAL_ERROR";
}

type AnswerSeed = AnswerSeedProduced | AnswerSeedSkipped;

type NarrativeBlock =
  | { kind: "NARRATIVE_READY"; text: string }
  | { kind: "NARRATIVE_DISABLED"; reason: string }
  | { kind: "NARRATIVE_FAILED"; error: string };

interface AxisCoverage {
  // 0/1 的“命中”最可维护：这轴是否被 top_claims 中任何 claim 覆盖到
  // （如果你要连续值，给我公式，不要玄学）
  covered: boolean;

  // 可选但有用：覆盖强度 = max(claim.score for claims that cover this axis)
  // 这不是平均分，平均分会被大量垃圾 claim 稀释。
  strength: number; // ∈ [0,1]
}
```

`assemble_answer_seed()` 的签名必须拿到 `integrity_status` 和“是否跳过 AS”的信息。你现在只传 `pa_state` 和 `frame`，然后硬编码 `"CLEAN"`，这就是典型的“接口设计失败”。

```ts
function assemble_answer_seed(args: {
  frame: QuestionFrame;
  pa_state: PAState;
  snapshot: EngineSnapshot;   // 提供 integrity_status + safe_point.stage
  narrative_generator?: (top_claims: RankedClaim[], frame: QuestionFrame) => Promise<string>;
  narrative_mode: "DISABLED" | "BEST_EFFORT";
}): Promise<AnswerSeed>;
```

### coverage_report 的计算公式（给你数字，不给你形容词）

- `top_claims = pa_state.ranked_claims.slice(0, pa_state.termination_config.top_k)`
- 对每个 `axis_id`：
  - `covered = exists claim in top_claims where claim_covers_axis(claim_id, axis_id) == true`
  - `strength = max(score of those covering claims) else 0`

这里关键是：你们现在的 `RankedClaim` **没有 axis 覆盖明细**，只有一个汇总 `coverage`（“覆盖轴权重之和”）。所以要实现 `claim_covers_axis()`，我要求你们在 PA 侧或更早保留映射，否则你根本没法按 axis_id 出 coverage_report。

最小可行补洞（不改 RankedClaim 结构的话）：
- 在 `PAState` 增加 `claim_axis_hits: Record<ClaimId, AxisId[]>`
- 或者更合理：扩展 RankedClaim（我更喜欢这个）：

```ts
interface RankedClaim {
  claim_id: ClaimId;
  score: number;      // [0,1]
  coverage: number;   // [0,1] 全局汇总
  axis_hits: AxisId[]; // 新增：用于 AS coverage_report
}
```

没有这个，`coverage_report` 就是编出来的。

### 2) 核心论据

- **“按 axis_id 报告”要求是硬约束**，而你们当前数据形状根本不支撑 axis 级别判定；所以要么改 `RankedClaim`，要么在 `PAState` 旁路保存映射。
- `coverage_report` 用“平均分”是垃圾设计：平均值会被大量低质 claim 冲淡，且与“答案是否覆盖该轴”不是一个问题。
- `AnswerSeed` 必须表达 “AS 跳过” 的事实：`EngineSnapshot.safe_point.stage` 里已有 `"TERMINATED_BEFORE_AS"`，你还用单结构体假装“总会有 seed”，那就是**状态机与数据契约打架**。

### 3) 可推翻条件（什么实验能证明我错）

- 如果你能给出一个**可计算且可维护**的连续 coverage 定义，并证明它比 `covered/strength` 更能预测用户满意度/终止正确性（例如离线评测：coverage 指标与人工“是否覆盖所有轴”标注相关系数显著更高），我接受改为连续值。
- 如果你证明 `RankedClaim` 在别处已经包含 axis 映射（我没看到），且 AS 可直接复用，则无需扩展结构。

---

## GAP-6（RB）：`extract_testable_angle()` 设计裁定

### 1) 裁定结论（类型 + 签名 + 失败路径）

我裁定：**先规则过滤，再 LLM；LLM 失败必须可观测**（至少返回结构化失败原因给日志/指标），但 RB 输出仍然只是一堆 drafts，不要把错误当 draft 塞回去污染 CC。

```py
from dataclasses import dataclass
from typing import Optional, Literal

ExtractionStrategy = Literal["REFRAME", "PROXY_MEASURE", "COMPONENT_DECOMPOSE"]

@dataclass
class ExtractableAngle:
    claim_sketch: str
    verifier_hint: list[str]
    scope_ref: list[str]  # axis_id list
    extraction_strategy: ExtractionStrategy
    novelty_hash: str     # 用于去重/同源过滤的稳定摘要（比如 SimHash/sha256 of normalized text）

@dataclass
class AngleReject:
    reason: Literal[
        "NO_RELATED_AXES",
        "LOGICALLY_NON_TESTABLE",
        "LLM_FAILED",
        "NO_NOVELTY",
        "INVALID_OUTPUT",
    ]
    detail: str

def extract_testable_angle(
    idea: RegulativeIdea,
    frame: QuestionFrame,
    *,
    llm: "LLMClient",
    min_novelty_jaccard: float = 0.35,
) -> tuple[Optional[ExtractableAngle], Optional[AngleReject]]:
    ...
```

注意：返回 `(angle, reject)`，别用异常到处炸；RB 是“探索”，不是“关键路径必须成功”。

### 规则触发条件（别搞玄学）

1. **轴关联性**（必须通过，否则不调用 LLM）  
   `candidate_axes = find_related_axes(idea.claim_sketch, frame.evaluation_axes)`  
   - 规则：`len(candidate_axes) >= 1` 才继续  
   - `find_related_axes` 可以先用关键词/embedding，但必须输出 axis_id 列表（可审计）。

2. **不可检验判定**（直接拒绝）  
   如果 `no_empirical_bridge_reason` 命中黑名单模式（比如 “定义上不可观测/纯形而上/逻辑上不可证伪”），返回 `LOGICALLY_NON_TESTABLE`。  
   这不是为了“聪明”，而是为了不浪费 token 让 LLM 胡扯。

3. **LLM 产物校验**（失败就 reject）  
   LLM 输出必须满足：
   - `claim_sketch` 与原文不相同（normalized 后必须不同）
   - `verifier_hint` 非空
   - `scope_ref` 非空且全部在 `frame.evaluation_axes.axis_id` 集合内
   - novelty：与原 `idea.claim_sketch` 的 token 集合 Jaccard 距离 >= `min_novelty_jaccard`
     - 你们担心 `is_homologous()`？那就别靠运气，给我**数值阈值**。

LLM 失败处理：
- timeout/parse error → `(None, AngleReject("LLM_FAILED", ...))`
- 输出不合法 → `(None, AngleReject("INVALID_OUTPUT", ...))`
- 不够新 → `(None, AngleReject("NO_NOVELTY", ...))`

### 2) 核心论据

- RB 的职责是“广度探索”，但你仍然需要**可维护的失败路径**。你现在 `pass` 然后返回空列表，等于 RB 节点是死的。
- “直接 LLM”会把大量明显无关/不可测的 idea 送去浪费预算，还会产生看似可测其实是胡扯的草稿，增加 CC 噪声。
- 你提的“策略 A”缺了关键一环：**怎样保证不会被 `is_homologous()` 秒杀**。我用 novelty 阈值 + 稳定 hash 解决。

### 3) 可推翻条件

- 如果你能证明“规则过滤”导致 recall 显著下降（比如错杀了大量本可转化的 regulative idea），且成本可接受，那么可以放宽为“总是调用 LLM，但限制输出校验更严格”。拿数据来，不要嘴炮。

---

## GAP-8（D2）：路由表与验证器接口裁定

### 1) 裁定结论（统一接口，D2 只做路由；必要时加上下文）

你们的争论点之一是“不同 verifier 输出不同类型”。这就是自找麻烦。**统一输出为 EpochDelta 列表**，每个 verifier 自己负责把结果编码成 `CLAIM_VERIFIED` 或 `CLAIM_SUSPENDED`。D2 不做转换器，D2 只是调度。

关键：`TARGETED_RECHECK` 需要历史证据，所以 `run_layer2_batch()` 必须增加一个只读上下文，至少能按 claim_id 查历史 `VerifiedClaimFull` 或 evidence 摘要。

```py
VerifierType = Literal[
  "EMPIRICAL_CHECK",
  "LOGICAL_AUDIT",
  "SCOPE_REVIEW",
  "TARGETED_RECHECK",
  "AXIS_CONSISTENCY_CHECK",
]

@dataclass(frozen=True)
class L2Context:
    epoch_id: int
    rulebook: AxisRulebook
    # 最小可用：给 targeted recheck / consistency check 用
    history_by_claim: dict[str, "VerifiedClaimFull"]  # 可用更省内存的摘要，但要有类型
    # 尺寸预算控制（32KB 限制是对 L2Return；但 verifier 内也该有预算）
    max_return_bytes: int = 32 * 1024

class Verifier(Protocol):
    verifier_type: VerifierType
    def verify(self, claim: TestableClaim, ctx: L2Context) -> "Result[list[EpochDelta], L2VerificationError]": ...

def run_layer2_batch(
    *,
    claims: list[TestableClaim],
    ctx: L2Context,
    registry: dict[VerifierType, Verifier],
) -> "Result[L2Return, L2BatchError]":
    ...
```

路由表：`registry[claim.verification_protocol]`，没有就降级。

### 未实现 verifier 的降级策略（给我确定行为）

我裁定：**未实现 = 产出 CLAIM_SUSPENDED**，reason 用机器可解析码，别写散文。

```py
{ "kind": "CLAIM_SUSPENDED", "claim_id": id, "reason": "VERIFIER_UNIMPLEMENTED:LOGICAL_AUDIT" }
```

不要“保持 PENDING”。PENDING 会让系统表面上“还有活干”，实际永远不收敛；你们的终止条件依赖 coverage，这会把系统卡死。

### 2) 对你提供文本的精确攻击（至少一个）

你在 GAP-8 里给的备选方案 B 写道：

> “LogicalAuditor 不返回 EvidenceChain！它返回逻辑审查结果，如何转换为 EpochDelta？”

这就是典型的过度设计诱因：你试图让 D2 做“类型转换中台”。结果就是：每加一个 verifier，你就得改一堆 glue code，回归风险暴涨。

正确做法是：**所有 verifier 都输出 EpochDelta**。你想保留 `LogicAuditResult`？可以塞进 `VerifiedClaimFull` 的证据字段里（或其子结构），但对 D2 来说它只是 payload，不是分支爆炸的类型系统。

同样，你在 GAP-3 的骨架里这句：

> `const top_claims = pa_state.ranked_claims.slice(0, frame.evaluation_axes.length);`

这在 `evaluation_axes` 很多的情况下会直接输出一坨 claim，或者 axes 很少时输出太少。你们自己都写了 `TerminationConfig.top_k`，还不用它？这不是“待优化”，这是**逻辑错误**。

### 3) 可推翻条件

- 如果你能证明某些 verifier 必须产生 `GAP_OPEN/GAP_PATCH/...` 等非 claim delta，统一接口仍然可行：它们照样返回 `list[EpochDelta]`。所以几乎推翻不了。
- 唯一可能推翻点：`history_by_claim` 太大导致性能/内存问题。那就换成 `history_index: ClaimEvidenceIndex`（按需查），但**上下文必须存在**，否则 `TARGETED_RECHECK` 就是假的。

---

## 你接下来要补的“具体 trace”（我要求的最小证据）

别再抽象讨论了。你要给我至少各一个：

1. **GAP-3**：给定 `top_k=5`、`evaluation_axes=12` 的 frame，输出 `top_claims` 长度必须是 5，并展示某个 axis 的 `covered/strength` 如何由 `axis_hits` 推出。
2. **GAP-6**：用你提供的碳交易/碳税的 `RegulativeIdea` 跑一遍：candidate_axes 是哪些、LLM 输出样例、novelty 计算数值是多少、最后 draft 是否通过 normalize_repair。
3. **GAP-8**：一个 `LOGICAL_AUDIT` claim 进入 `run_layer2_batch`，路由到 `LogicalAuditorVerifier`，返回的 `EpochDelta[]` 长什么样；以及 verifier 未实现时必然产生 `VERIFIER_UNIMPLEMENTED:*` 的 suspended。

拿这些 trace 来，我们第二轮再谈谁的设计在边界条件下会炸。

---


### [2] Ssyram

*2026-03-10T15:31:58.088670*

我是 Ssyram。

当前骨架代码充满了类型泄漏和隐式假设。系统设计不是写散文，不能指望下游「自然理解」你的意图。所有未在类型签名中显式声明的约束，在运行时都会变成灾难。

以下是我的初始裁定。

───────────────────────────────────
### 攻击与纠偏：对当前骨架与备选策略的精确狙击

在给出具体方案前，我必须先清理掉当前描述中那些「正确的废话」和类型错误。

**攻击 1：针对 GAP-3 现状骨架的函数签名**
> 引用文本：`function assemble_answer_seed(pa_state: PAState, frame: QuestionFrame): AnswerSeed`
**缺陷**：这是典型的作用域越权。`integrity_status` 存在于 `EngineSnapshot`，而该骨架试图在不传入 `L1State` 的情况下伪造一个 `"CLEAN"` 状态。接口设计的第一法则：如果一个纯函数需要外部状态，必须在签名中显式要求。修改签名是唯一正确的做法。

**攻击 2：针对 GAP-6 的「策略 A」**
> 引用文本：`extraction_strategy: "REFRAME" // 例："主权决策权更受尊重" → "在碳排放交易机制下，各国实际提交的NDC修订率更高"`
**缺陷**：「REFRAME」是一个没有工程约束的遮羞布。把「主权」映射到「NDC修订率」本质上是寻找代理变量（PROXY_MEASURE）。如果不强制要求 LLM 产出具体的代理指标或拆解组件，所谓的「重构」只会变成 LLM 的同义词替换（wordplay），这种产出必然会被 CC 节点的 `is_homologous()` 原地拦截。我拒绝引入这种毫无信息增量的策略枚举。

───────────────────────────────────
### GAP-3：AnswerSeed 接口设计

**1. 裁定结论与接口定义**
AS 节点是纯数据投影层。拒绝在此节点引入任何 LLM 生成的 `answer_narrative`。叙述性文本属于 Layer 0（UI/表现层），不属于 Layer 1 状态机。

```typescript
// 完整接口定义
interface AnswerSeed {
  problem_id: string;
  epoch_id: number;
  top_claims: RankedClaim[];             // 长度严格 <= termination_config.top_k
  axis_coverage: Record<AxisId, number>; // 语义：该轴被 top_claims 覆盖的最大得分（max axis_score）
  integrity_status: "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
  termination_reason: string;
}

// 必须修改函数签名，接收完整 L1State
function assemble_answer_seed(state: L1State): AnswerSeed | null {
  if (state.snapshot.safe_point.stage === "TERMINATED_BEFORE_AS") {
    return null; // 显式处理提前终止
  }
  
  const config = state.pa_state.termination_config;
  const top_claims = state.pa_state.ranked_claims.slice(0, config.top_k);
  
  const axis_coverage: Record<AxisId, number> = {};
  for (const ax of state.frame.evaluation_axes) {
    // 覆盖率的具体计算：取 top_claims 中对该轴贡献得分的最大值
    axis_coverage[ax.axis_id] = compute_max_axis_score(ax.axis_id, top_claims);
  }

  return {
    problem_id: state.frame.problem_id,
    epoch_id: state.pa_state.ranking_history.at(-1)?.epoch_id ?? 0,
    top_claims,
    axis_coverage,
    integrity_status: state.snapshot.integrity_status, // 从全局状态安全读取
    termination_reason: state.pa_state.termination_reason ?? "UNKNOWN"
  };
}
```

**2. 核心论据**
*   **关于 `axis_coverage` 语义**：在 CEGAR 循环中，覆盖率意味着「该维度是否被有效满足」。取 `top_claims` 在该轴的平均分会掩盖极值（一个满分 claim 足以覆盖该轴）。必须取最大值（max）。
*   **关于拒绝 `answer_narrative`**：Layer 1 的输出必须是确定性的。如果在 AS 节点调用 LLM 生成文本，一旦生成失败或产生幻觉，将破坏已经收敛的 CEGAR 状态。

**3. 可推翻条件**
如果下游消费者（报告生成器）证明：仅靠 `top_claims` 的结构化数据无法在缺乏 Layer 1 运行上下文的情况下生成连贯报告，必须依赖 L1 内部的某些瞬态张力数据，我同意在 `AnswerSeed` 中加入 `tension_summary`，但仍拒绝直接生成自然语言答案。

───────────────────────────────────
### GAP-6：repair_breadth() 内部逻辑设计

**1. 裁定结论与接口定义**
采用**规则拦截 + 强制代理映射**策略。废弃模糊的 "REFRAME"。

```typescript
// 严格限制提取策略
interface ExtractableAngle {
  claim_sketch: string;
  verifier_hint: string[];
  scope_ref: AxisId[]; 
  extraction_strategy: "PROXY_MEASURE" | "COMPONENT_DECOMPOSE"; // 仅限这两种具体可操作的动作
}

function extract_testable_angle(idea: RegulativeIdea, frame: QuestionFrame): ExtractableAngle | null {
  // 1. 规则先行：拦截绝对不可检验的规范性死胡同
  if (contains_logical_impossibility(idea.no_empirical_bridge_reason)) {
    return null; 
  }

  const candidate_axes = find_related_axes(idea.claim_sketch, frame.evaluation_axes);
  if (candidate_axes.length === 0) return null;

  // 2. 强制 LLM 在 PROXY_MEASURE 和 COMPONENT_DECOMPOSE 中二选一
  // prompt 中必须注入：要求新生成的 claim_sketch 与 idea.claim_sketch 的词汇重合度低于阈值，强制具象化
  const result = llm_extract_concrete_proxy(idea, candidate_axes);
  
  if (!result || result.extraction_strategy === "NONE") {
    log_metric("rb_extraction_failed", { idea_id: idea.idea_id });
    return null; // 静默返回，不阻塞循环
  }
  
  return result;
}
```

**2. 核心论据**
*   **避免 `is_homologous` 拦截**：同源检测通常基于语义向量或词汇重叠。如果允许 LLM 仅仅「换句话说」（REFRAME），产出必然被 CC 节点丢弃。强制要求 `PROXY_MEASURE`（寻找代理变量）能从根本上改变草稿的实体（Entities），例如把「道德」变成「采纳率」，从而在向量空间产生实质位移，绕过同源拦截。
*   **规则拦截的必要性**：大模型本质是模式匹配搜索，让 LLM 去处理明确包含「数学上无法证明」的输入，是浪费算力且增加不可预测性。

**3. 可推翻条件**
如果在实际运行中，发现超过 80% 的 `RegulativeIdea` 被 `contains_logical_impossibility` 规则错误拦截，导致广度探索依旧瘫痪，我同意退回纯 LLM 决策，但必须在 LLM 提示词中加入严格的 `Verification Feasibility Assessment` 步骤。

───────────────────────────────────
### GAP-8：D2 节点分派路由设计

**1. 裁定结论与接口定义**
D2 必须是一个基于 `L2Context` 注入的路由分发器。验证器接口必须统一，但上下文必须扩充，否则 `TARGETED_RECHECK` 无法获取历史证据。

```typescript
// 扩充 D2 批处理签名，传入 state 以构建上下文
function run_layer2_batch(
    claims: TestableClaim[],
    state: L1State, // 必须传入，以获取 evidence_archive
    epoch_id: number
): Result<L2Return, L2BatchError> {
    
    const ctx: L2Context = {
        rulebook: get_rulebook(state.frame),
        epoch_id: epoch_id,
        evidence_archive: state.evidence_archive // 解决 TARGETED_RECHECK 的上下文缺失
    };

    const deltas: EpochDelta[] = [];
    
    for (const claim of claims) {
        const verifier = VERIFIER_ROUTER[claim.verification_protocol];
        if (!verifier) {
            // 降级策略：未实现的验证器直接挂起，不阻塞其他 claim
            deltas.push({ kind: "CLAIM_SUSPENDED", claim_id: claim.claim_id, reason: "UNIMPLEMENTED_VERIFIER" });
            continue;
        }

        const result = verifier(claim, ctx);
        if (result.ok) {
            deltas.push({ kind: "CLAIM_VERIFIED", claim: result.value });
        } else {
            deltas.push({ kind: "CLAIM_SUSPENDED", claim_id: claim.claim_id, reason: result.error.message });
        }
    }
    
    return Ok({ epoch_id, deltas, size_bytes: estimate_size(deltas) });
}

// 统一验证器函数签名：内部负责把不同性质的审查结果映射为 VerifiedClaimFull
type VerifierFn = (claim: TestableClaim, ctx: L2Context) => Result<VerifiedClaimFull, L2VerificationError>;

const VERIFIER_ROUTER: Record<string, VerifierFn> = {
    "EMPIRICAL_CHECK": run_empirical_check,
    "LOGICAL_AUDIT": run_logical_audit,
    "TARGETED_RECHECK": run_targeted_recheck
};

// 针对 LOGICAL_AUDIT 的具体映射逻辑
function run_logical_audit(claim: TestableClaim, ctx: L2Context): Result<VerifiedClaimFull, L2VerificationError> {
    const audit_result = execute_logic_solver(claim.falsifiable_statement);
    // 将逻辑推导结果伪装成 EvidenceChain 结构，以满足 L1 统一处理
    return Ok({
        ...claim,
        evidence_chain: [{
            source: "LOGICAL_SOLVER",
            content: audit_result.proof_path,
            reliability: 1.0
        }],
        // ...
    });
}
```

**2. 核心论据**
*   **统一输出类型**：Layer 1 的 PA 节点只认 `CLAIM_VERIFIED` 及其携带的 `VerifiedClaimFull`。如果你让 `LogicalAuditor` 返回一个异构的 `LogicAuditResult`，你就要在 L1 调度器里写无数个 `if-else`。必须在 L2 的具体验证器内部，将逻辑证明（Proof）包装成证据链（EvidenceChain）的形式返回。
*   **上下文注入**：`TARGETED_RECHECK` 顾名思义是「复查」。不传 `evidence_archive`，复查什么？这是类型设计上的硬伤，必须通过 `L2Context` 修复。

**3. 可推翻条件**
如果证明将逻辑证明（Proof）强行塞入 `EvidenceChain` 结构会导致 PA 节点的打分逻辑（如基于信源权重的衰减算法）崩溃，我同意在 `EpochDelta` 中新增一种 `kind: "CLAIM_LOGICALLY_PROVED"` 事件，但这将要求同步修改 PA 节点的聚合逻辑。目前的设计是最小侵入方案。

---


### [3] 康德（Immanuel Kant）

*2026-03-10T15:31:58.088688*

下面我对 GAP-3/6/8 给出**第 1 轮初始裁定**。我会不断做必要的区分：哪些字段是**构成性**（系统必须据此运作），哪些只是**调节性**（帮助理解与沟通，但不可冒充“世界本来如此”）；哪些是**先天约束**（接口层必须可审计、可反推），哪些可以留给经验层（LLM、证据收集）去填。

并且我会对至少一个对手论点做精确攻击：你方在 GAP-6 提供的“策略 A：最小化，类比 CC 的宽松模式”中，把“由 LLM 重构为可检验版本”当作默认路线——这在认识论上把**经验生成的自然倾向**（训练偏好）偷换成了**先验合法的推理规则**；除非你给出可审计的停止判据与失败语义，否则它会制造“看似更可检验”的幻象，却无法证明其不是同源重述。

---

## GAP-3（AS）：`AnswerSeed` 完整接口 + 组装签名裁定

### 1) 裁定结论（接口/类型形状）

#### (A) AnswerSeed 必须区分“产出”与“未产出”
因为你已给出约束 3：`EngineSnapshot.safe_point.stage` 有 `"TERMINATED_BEFORE_AS"`，所以**AnswerSeed 不能只是一个对象类型**，必须是可判别联合（sum type）。

```ts
type IntegrityStatus = "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
type AxisId = string;

type CoverageMetric =
  | { kind: "AXIS_TOP_CLAIM_SCORE"; value: number }          // ∈ [0,1]
  | { kind: "AXIS_MEAN_SCORE"; value: number }              // ∈ [0,1]
  | { kind: "AXIS_CLAIM_COUNT"; value: number };            // ≥ 0（调试/解释用）

interface AxisCoverageEntry {
  axis_id: AxisId;
  metric: CoverageMetric;
  // 用于可审计：coverage 是怎么来的（构成性要求：必须可反推）
  computed_from: {
    ranked_claim_ids: string[];     // 至少列出 top_k 的 claim_id（或截断列表）
    method_version: string;         // e.g. "v3.axis_coverage.v1"
  };
}

interface ConfidenceBand {
  // 注意：这是调节性，不是统计置信区间；必须明确其来源
  kind: "EPISTEMIC_BAND";
  low: number;   // ∈ [0,1]
  high: number;  // ∈ [0,1]
  basis: "EPSILON_STATE" | "HEURISTIC";
}

interface AnswerNarrative {
  // 叙述性文本是调节性产物：用于沟通，不可反推为“真理”
  format: "markdown" | "plain";
  text: string;
  // 可审计：叙述引用了哪些 claim（避免 LLM 凭空发挥）
  citations: { claim_id: string; excerpt?: string }[];
}

type AnswerSeed =
  | {
      kind: "ANSWER_SEED";
      problem_id: string;
      epoch_id: number;

      integrity_status: IntegrityStatus;
      termination_reason: string;

      top_k: number;
      top_claims: RankedClaim[];   // 长度 ≤ top_k

      // 按 axis_id 汇报（你方硬约束 4）
      coverage_report: AxisCoverageEntry[];

      // 调节性：可选，但一旦给出必须可追溯
      narrative?: AnswerNarrative;

      // 调节性：如果给，必须声明来源，不许伪装统计学意义
      confidence_bands?: Record<AxisId, ConfidenceBand>;
    }
  | {
      kind: "NO_ANSWER_SEED";
      problem_id: string;
      epoch_id: number;
      integrity_status: IntegrityStatus;
      termination_reason: "TERMINATED_BEFORE_AS";
      // 解释为何跳过：构成性（下游据此决定 UI/重试策略）
      skipped_because: string;
    };
```

#### (B) `assemble_answer_seed()` 的签名必须接入 EngineSnapshot（或 L1State）
因为约束 2：`integrity_status` 继承自 `EngineSnapshot.integrity_status`。你当前签名只收 `(pa_state, frame)`，在类型上就**不可能**满足继承规则；这不是实现缺陷，而是接口先验不完备。

裁定签名如下（二选一，推荐 1）：

**推荐 1：显式注入 snapshot（最小充分条件）**
```ts
function assemble_answer_seed(
  pa_state: PAState,
  frame: QuestionFrame,
  snapshot: Pick<EngineSnapshot, "integrity_status" | "safe_point">,
  opts?: { include_narrative?: boolean }
): AnswerSeed;
```

**可接受 2：直接传 L1State（更重，但更稳）**
```ts
function assemble_answer_seed(
  state: L1State,
  pa_state: PAState,
  frame: QuestionFrame,
  opts?: { include_narrative?: boolean }
): AnswerSeed;
```

### 2) 核心论据

- **coverage_report 的先天语义必须与“轴”同构**：你方已规定“按 axis_id 报告”，那它就不该复用 `RankedClaim.coverage`（那是“claim 覆盖了多少轴权重之和”），否则发生范畴错误：把“关于 claim 的量”当成“关于 axis 的量”。因此我裁定 `coverage_report` 的默认指标是：  
  **`AXIS_TOP_CLAIM_SCORE`：该轴上 top_k claim 的最高 score**（构成性、可用来判断该轴是否被“覆盖”）。
- `top_k` 的来源是 `PAState.termination_config.top_k`：这点你自己在约束里已给出。任何“slice 到 evaluation_axes.length”的方案都是把“评估维度数”偷换成“输出结论数”，属于**无根据的同一化**。
- 叙述性 `narrative` 与 `confidence_bands` 必须被标记为**调节性**：LLM 生成文本只能作为“理解的媒介”，不能反过来成为“构成性证据”。因此它们是可选字段，但一旦出现必须带 citations / basis，满足可审计性。

### 3) 可推翻条件

- 如果你们能证明 PA 节点已经维护了**每轴稳定的覆盖度量**（例如 `PAState` 内存在 `axis_coverage: Record<axis_id, number>` 且其计算过程可审计），那么 `coverage_report` 的 `metric` 可以被替换为该 PA 原生量，AS 只负责搬运。
- 如果下游 UI/报告生成器在契约上**不需要**叙述性文本（完全结构化消费），则 `narrative` 可从接口中删去；但必须提供等价的“可读摘要”机制在下游实现（否则你只是把调节性需求外包，并未消除）。
- 如果 `EngineSnapshot.safe_point.stage` 在运行时保证 **AS 永不被跳过**，则 `NO_ANSWER_SEED` 分支可移除；但这与已知约束 3 冲突，所以推翻需要你们修改 safe_point 语义与所有调用点。

---

## GAP-6（RB）：`extract_testable_angle()` 的完整设计裁定

### 1) 裁定结论（接口/类型形状）

我裁定：`extract_testable_angle()` 必须是**规则先行 + 受约束的 LLM**，并且输出要携带“差异证明”以避免 `is_homologous()` 过滤。

```ts
type ExtractionStrategy =
  | "REFRAME"
  | "PROXY_MEASURE"
  | "COMPONENT_DECOMPOSE"
  | "SCOPE_NARROW"
  | "NONE";

interface ExtractableAngle {
  claim_sketch: string;          // 必须与原 claim_sketch 不同（见 diff_proof）
  verifier_hint: string[];       // 非空
  scope_ref: string[];           // 非空，且是 frame.evaluation_axes 中 axis_id
  extraction_strategy: ExtractionStrategy;

  // 关键：避免同源过滤的“可审计差异”
  diff_proof: {
    novelty_terms: string[];     // 新引入的可操作术语/指标词
    dropped_terms: string[];     // 被移除的规范性/不可操作词
    distance: number;            // ∈ [0,1]，启发式距离（仅用于阈值判定）
  };

  // 调节性：解释为何这是“更接近可检验”
  rationale: string;
}

type ExtractAngleFailure =
  | { kind: "NO_RELATED_AXIS"; detail: string }
  | { kind: "LOGICAL_IMPOSSIBILITY"; detail: string }
  | { kind: "LLM_FAILED"; detail: string }
  | { kind: "HOMOLOGOUS_RISK"; detail: string };

function extract_testable_angle(
  idea: RegulativeIdea,
  frame: QuestionFrame,
  opts?: {
    min_distance?: number;       // 默认 0.25
    max_llm_tokens?: number;
    allow_strategies?: ExtractionStrategy[];
  }
): { ok: true; value: ExtractableAngle } | { ok: false; error: ExtractAngleFailure };
```

并相应修改 `repair_breadth()`：不要静默吞错，至少要**记录失败原因**（否则 RB 永久“无贡献”你也不知道是轴不匹配还是 LLM 崩了）。

### 2) 核心论据

- 你方“策略 A 直接 LLM 重构”在认识论上最大的问题：它把“能说出一个看似可测的句子”当作“确立了经验桥”。这是从调节性（帮助想象路径）僭越为构成性（真的建立了桥）。因此必须先行做**先天筛选**：  
  (i) 是否能在 `evaluation_axes` 中找到相关轴；(ii) 是否属于“逻辑不可能”的桥（例如概念上不可操作，而非暂时缺数据）。
- RB 的目标是“广度探索”，但广度不等于“增加新维度”（你方先验立场里已确立：同源张力禁止触发广度引擎）。所以 RB 的正确操作是：在同一图型内**改变可操作表述**（proxy、拆解、缩域），而不是引入新的评价轴或新的本体论承诺。
- 为避免 `is_homologous()`：仅靠“换句话说”不够。必须提供 `diff_proof`，至少引入**可操作指标词**（例如 “NDC 修订率”“退出机制条款保留率”），并显式丢弃“道德优越性”这类不可操作词。差异必须可计算（哪怕是启发式），否则就是不可审计的“看起来不同”。

### 3) 可推翻条件

- 如果 `is_homologous()` 的实现并非基于文本/语义近似，而是基于更强的结构签名（例如 scope_ref + verifier_hint 的结构哈希），则 `diff_proof.distance` 的必要性可下降；但你必须公开同源判定的先验条件，否则 RB 无法对症避免过滤。
- 若 CC 已提供“宽松可检验桥”的内部转换（即 CC 自身能把 NO_EMPIRICAL_BRIDGE 变成弱可检验草稿），则 RB 可简化为仅做“轴匹配与缩域”，不必调用 LLM。
- 若系统策略明确禁止 LLM 参与修复（出于合规），则可把 LLM 步骤替换为规则模板库；但必须接受覆盖率下降，并在 `ExtractAngleFailure` 中明确记录“模板不足”。

---

## GAP-8（D2）：路由表与验证器接口裁定

### 1) 裁定结论（接口/类型形状）

我裁定：D2 必须采用**统一验证器接口**，并允许验证器读取“历史上下文”以支持 `TARGETED_RECHECK`。但为了不污染 Layer2 的纯度，这个上下文应当是**最小的只读视图**，由 D2 注入，而不是让验证器直接拿整个 L1State。

#### (A) 统一接口
```ts
type VerifierType =
  | "EMPIRICAL_CHECK"
  | "LOGICAL_AUDIT"
  | "SCOPE_REVIEW"
  | "TARGETED_RECHECK"
  | "AXIS_CONSISTENCY_CHECK";

interface VerificationContext {
  epoch_id: number;
  rulebook: AxisRulebook;

  // 只读历史视图：支持 recheck / consistency
  history?: {
    evidence_by_claim_id?: Record<string, EvidenceChain>;
    prior_scores_by_claim_id?: Record<string, number>;
  };

  // 资源约束是构成性的：否则 32KB 限制会被动触发崩溃
  budget: { max_return_bytes: number };
}

type VerificationOutcome =
  | { kind: "VERIFIED"; claim: VerifiedClaimFull }
  | { kind: "SUSPENDED"; claim_id: string; reason: string }
  | { kind: "GAP_OPEN"; gap: GapSpec }; // 用于 scope/axis 内部不一致触发 gap

interface Verifier {
  type: VerifierType;
  verify(claim: TestableClaim, ctx: VerificationContext): Promise<VerificationOutcome[]>;
}
```

#### (B) D2 路由表（构成性）
```ts
type VerifierRegistry = Record<VerifierType, Verifier>;

function get_verifier_registry(): VerifierRegistry; // 未实现的必须返回 StubVerifier（见降级）
```

#### (C) `run_layer2_batch()` 签名裁定：需要增加可选 history
保持你给的返回 `L2Return` 不变，但签名应扩展（向后兼容）：

```py
def run_layer2_batch(
    claims: list[TestableClaim],
    rulebook: AxisRulebook,
    epoch_id: int,
    history: dict | None = None,
    budget: dict | None = None
) -> Result[L2Return, L2BatchError]:
    ...
```

其中 `history` 至少应支持：
- `evidence_by_claim_id`（给 TARGETED_RECHECK）
- （可选）`prior_scores_by_claim_id`

#### (D) 各 verifier_type 的输出映射到 EpochDelta
D2 最终只产出你允许的 `EpochDelta`：

- `VERIFIED` → `{ kind: "CLAIM_VERIFIED", claim: VerifiedClaimFull }`
- `SUSPENDED` → `{ kind: "CLAIM_SUSPENDED", claim_id, reason }`
- `GAP_OPEN` → `{ kind: "GAP_OPEN", gap }`

### 2) 核心论据

- 你问：“`LOGICAL_AUDIT` 输出如何转换为 EvidenceChain？”——我裁定不必强行塞回 EvidenceChain。那是把“逻辑根据”硬翻译成“经验证据链”，属于范畴混淆。正确做法是：`VerifiedClaimFull` 内允许一种证据形态为 `logic_audit`（这是 Layer2 的模型扩展点），D2 只关心它最终能形成 `CLAIM_VERIFIED` delta。
- `TARGETED_RECHECK` 若不能访问历史证据，就不是 recheck，而是重复 check。故必须注入历史只读视图；但把整个 L1State 交给 Layer2 又会破坏层次（Layer2 变成杂糅的判断力+记忆体）。所以取中道：**最小历史视图**。
- 未实现验证器的降级：我裁定应产出 `CLAIM_SUSPENDED`，理由是“VERIFIER_NOT_IMPLEMENTED”。因为保持 PENDING 会造成无终止的悬置（你系统的终止条件会被“永远待验证”拖死）。Suspended 是一种明确的认识论状态：当前规则体系下不可判定。

### 3) 可推翻条件

- 若你们能证明 `VerifiedClaimFull` 结构**不可扩展**（只能来自 EvidenceChain），那么我上述“logic_audit 作为证据形态”的方案需退回：让 `LOGICAL_AUDIT` 也产出一种 EvidenceChain（其中 evidence_item.type = "LOGIC_PROOF"）。但这要求你们接受“证据链”概念被扩大为“根据链”，并在文档中做明确定义区分。
- 如果 32KB 限制并非硬约束（例如可分片回传），则 `VerificationOutcome[]` 的预算控制可以放宽；否则必须保留 budget。
- 若你们决定 `TARGETED_RECHECK` 永不读取历史（只做再检索），则可去掉 `history.evidence_by_claim_id`；但必须改名为 `RETROSPECTIVE_CHECK` 之类，避免语义欺骗。

---

## 对对手论点的精确攻击（至少一处）

你在 GAP-6 的“策略 A（最小化，类比 CC 的宽松模式）”写道：

> “用 LLM 重构为可检验版本：放宽证伪条件要求”

这里有一个需要先被区分的概念混乱：**放宽证伪条件**是调节性的（帮助继续探索），但你把它直接当成 `extract_testable_angle()` 的主机制，就会让 RB 产物看似“可检验”，实际上只是把规范词换成了经验词的拟像；并且缺乏可审计的“差异证明”，在 `is_homologous()` 下极可能被过滤为同源重述。  
可推翻我这条批评的条件是：你能提供 `llm_reframe()` 的输出约束（例如必须引入可操作指标词表、必须引用 axis_id、必须给出 proxy 定义），并且提供失败语义与停止判据；否则它只是把训练分布的偏好当作“广度探索”的法则。

---

以上是第 1 轮裁定。若你愿意推进到第 2 轮，我会要求你们给出：  
1) `compute_axis_coverage` 的具体公式（对 GAP-3），以及 coverage 与 termination(min_coverage) 的一致性证明；  
2) `is_homologous()` 的判定依据（对 GAP-6），否则“避免过滤”是盲飞；  
3) `VerifiedClaimFull` 的证据形态约束（对 GAP-8），以决定逻辑审计究竟扩展哪一层的类型系统。

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-10T15:32:28.494019*

1) **GAP-3：你把 `AnswerSeed` 说成“纯数据投影”，但你定义的 `axis_coverage` 需要 `axis_score`，而上游根本没给你这个数据。**  
你写：`axis_coverage[ax] = compute_max_axis_score(ax, top_claims)`，还声称语义是“max axis_score”。问题是：`RankedClaim` 只有 `{score, coverage}`，没有 `axis_score` 分解；`PAState` 里也没任何 “per-axis score” 的结构。  
所以你现在的方案是典型的“白板函数”：**输入类型里没有信息，你就假装能算出来**。  
给我一个能跑的签名：  
- `compute_max_axis_score(axis_id: AxisId, top: RankedClaim[], ???) -> number` 的第三个参数到底是什么？来自哪里？  
- 如果确实拿不到 per-axis 数据，那你要么改 `RankedClaim`（回头污染 PA 接口），要么改 `AnswerSeed` 语义（比如改成 `axis_coverage = sum(top_claim.coverage * axis_weight_hit?)`，但你也没 axis hit）。  
另外你让 `assemble_answer_seed` 返回 `AnswerSeed | null`，但你没说明 orchestrator 的调用点怎么处理 `null`：终止后返回什么给外部？还是直接抛错？“TERMINATED_BEFORE_AS” 是状态，不是借口。

2) **GAP-6：你说要“强制代理映射”，但你用的判定全是不可计算的玄学，根本没给数字和可验证条件。**  
你要求“词汇重合度低于阈值”，阈值是多少？怎么计算？Jaccard？cosine？embedding 模型版本？  
你还指望用“实体变化”绕过 `is_homologous()`，但 `is_homologous()` 如果是语义向量相似度（很可能），你换几个词根本没用；如果它是结构化字段比较，你也没说明字段差异规则。  
更糟的是你让 `llm_extract_concrete_proxy()` 返回 `ExtractableAngle`，但没给失败路径类型：  
- 超时？返回 `null`？那 `log_metric` 之外有没有把失败写进 `L1State`（否则你怎么 debug RB 一直没产出？）  
- 返回了 `scope_ref` 引了不存在的 axis_id 怎么办？你靠“prompt 注入”保证？这就是我最恶心的“语义保证”。给我 runtime assertion：失败时是丢弃、修正、还是转成 `SchemaChallengeNotice`？

3) **GAP-8：你一边说“最小侵入”，一边直接改了 `run_layer2_batch()` 签名并把 `state` 整个塞进去——这是把耦合当设计。**  
约束写得很清楚：现有调用是 `run_layer2_batch(claims, rulebook, epoch_id)`，你直接改成 `(claims, state, epoch_id)`，这不是“扩充上下文”，这是**把 D2 变成 L1State 的寄生虫**。最小侵入应该是：  
- 明确引入 `L2Context`（只包含必要字段），而不是传整个 `L1State`；  
- 或者把 `evidence_archive` 通过参数单独传入：`run_layer2_batch(claims, rulebook, epoch_id, evidence_archive)`。  
还有，你把逻辑证明“伪装成 EvidenceChain”，然后 reliability=1.0——这会直接污染任何基于信源衰减/多源交叉的评分逻辑。你自己也承认可能崩，但你没给出**可计算的隔离机制**：  
- `EvidenceChain.source="LOGICAL_SOLVER"` 在 PA 打分里权重是多少？给数字。  
- 如果 PA 目前只认识文献源，你这个 1.0 会让逻辑 claim 永远碾压经验 claim，直接 regression。  
给我一个具体 trace：输入一个 `LOGICAL_AUDIT` claim，PA 最终 `score` 怎么算？否则你这就是“把类型统一当成解决方案”，实际是在隐藏语义差异。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-10T15:33:00.661213*

康德，你的区分（构成性/调节性）在哲学上很漂亮，但在工程落地时，你犯了严重的类型错误，并且引入了不可计算的幽灵状态。

我的工作是在形式化和实用之间建立映射。你的接口设计看似严密，但只要往下推一层实现，就会导致系统发散或崩溃。我只问你三个致命的工程问题：

### 1. GAP-3：你把「正确性（Score）」偷换成了「完备性（Coverage）」，这会直接摧毁 CEGAR 的收敛保证。

你裁定 `coverage_report` 的指标是 `AXIS_TOP_CLAIM_SCORE`（该轴上 top_k claim 的最高 score）。这是一个极度荒谬的范畴错误。

**Score 是命题的真值（Defensibility），Coverage 是空间的探索度。** 
如果一个草稿主张「碳税实施成本极低」，Layer 2 验证后发现证据确凿，Score 给到 0.95。按照你的设计，这个轴的 Coverage 就是 0.95。这意味着什么？意味着只要我们在某个轴上找到了**一个**绝对正确的废话，系统就会认为这个轴已经被充分探索了，从而满足 `avg_coverage > min_coverage` 的终止条件，提前结束 Epoch 循环。

在概率程序验证中，这相当于你找到了一个 trivial 的反例，就宣布状态空间已经遍历完毕。
**我的质询：**
如果你坚持用 Score 替代 Coverage，请给出数学证明：为什么一个命题的「高可辩护性」能等价于对该评估轴的「高覆盖率」？如果你无法证明，你就是在用真值污染终止条件。正确的 Coverage 必须是基于 `frame.evaluation_axes` 子维度的映射率，而不是得分。

### 2. GAP-6：你要求 LLM 出具 `diff_proof`，这是在让嫌疑人给自己开无罪证明。

你为了避免 RB 节点的产物被 `is_homologous()` 过滤，设计了一个 `diff_proof` 对象，包含 `novelty_terms` 和 `distance`（∈ [0,1]）。

大模型本质上是「提示词引导的概率分布模式匹配搜索」。你让 LLM 在输出新草稿的同时，自己输出一个 `distance: 0.8` 来证明自己和原草稿不同。我对这种「权重由 LLM 决定」的设计有生理性厌恶。LLM 极擅长生成「看起来不同但逻辑完全同构」的车轱辘话，并且它会毫不脸红地给自己打个高分。

**我的质询：**
这个 `distance` 到底由谁计算？
- 如果是 LLM 生成的，它不可审计、不可重复，毫无意义。
- 如果是外部规则计算的，请给我完整的纯函数签名。是基于 AST 的树编辑距离？还是 embedding 向量夹角？
你定义了一个看似形式化的接口，但它在工程上没有执行语义。如果 `is_homologous()` 是基于语义哈希的，你的词汇表 diff 根本绕不过去。

### 3. GAP-8：你为了支持 `TARGETED_RECHECK` 强行向 Layer 1 注入历史视图，这会打爆状态机的内存。

你裁定 `run_layer2_batch` 需要传入 `history.evidence_by_claim_id`。你刚才的发言是正确的废话——你看到了 Recheck 需要上下文，但你的解决方案破坏了 v3 架构的最底层假设。

Layer 1 是一个**薄状态机（Thin State Machine）**。它只流转 `TestableClaim` 和标量分数。`EvidenceChain` 是非常重的数据结构（包含大量原始文档 chunk、溯源链接、验证器中间状态）。你让 Layer 1 把庞大的证据链缓存下来，每次 D2 分派时再作为 `history` 传回给 Layer 2。
知道这会发生什么吗？在第 3 个 Epoch，`L1State` 就会因为携带了数百个 claim 的完整证据链而触发 OOM（内存溢出），或者因为超过 32KB 的 IPC 限制被拒绝序列化。

**我的质询：**
为什么 `TARGETED_RECHECK` 需要 Layer 1 喂给它完整的历史证据？
函数式思维的正确做法是：在 CC 节点（Clarity Compiler）编译时，就应该把**具体的矛盾点或需要复核的证据片段**，具象化（Reify）到新 `TestableClaim` 的 `falsifiable_statement` 中。Layer 2 应该是无状态的纯函数，只负责验证输入的主张。
你为了弥补 CC 节点编译信息的不足，选择把整个系统的状态搞脏。你怎么解决 Layer 1 缓存 `EvidenceChain` 带来的状态爆炸问题？给我看内存管理的边界条件处理。

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-10T15:33:52.931207*

### 质疑 1（GAP-3）：你把“轴覆盖”当成可构成事实，但先验材料不足——这是把经验缺口偷换成结构必然  
你主张 `coverage_report[axis_id]` 必须给出 `covered/strength`，并进一步要求在 `RankedClaim` 或 `PAState` 补 `axis_hits` 来实现 `claim_covers_axis()`。这里有一个需要先被区分的概念混乱：

- **“按 axis_id 报告覆盖”是接口约束（调节性要求）**：它规定我们应当怎样呈现探索状态，以便后续判断可审计。  
- 但你给出的实现路线却把它提升成**构成性断言**：仿佛系统“必然能够”对每个 axis 判定命中与否，并且这种判定能从 `RankedClaim` 中无损恢复。

可推翻条件（你需要证明，否则你的方案只是工程直觉）：  
1) 证明 `axis_hits` 在整个流水线中有**非循环的来源**：它究竟来自 CC 的编译痕迹？来自 L2 的证据链标注？还是来自 PA 的后验归因？三者语义完全不同。  
2) 证明把 `axis_hits` 塞回 `RankedClaim` 不会导致**同源张力**下的循环：PA 用轴评分产出排名，再用排名反推轴命中，再用轴命中作为终止/呈现依据——这可能把“我们如何评分”偷换成“世界如何被覆盖”。  
3) 若 `axis_hits` 只能由 LLM/启发式生成，你必须给出它的**可审计规则**；否则你只是把训练分布的偏好伪装成“覆盖事实”。

---

### 质疑 2（GAP-6）：你宣称“规则过滤再 LLM”是中立的，但规则本身就是未经证明的先验立法  
你要求先 `find_related_axes()` 再决定是否调用 LLM，并设置 `LOGICALLY_NON_TESTABLE` 黑名单。这看似“节省预算”，但我关心的是其认识论地位：你把一套后验经验偏好（哪些词像“形而上”）上升为**先验排除条件**，这会系统性地压制某类问题的“可被转化”的可能性。

关键薄弱点：  
- `find_related_axes()` 以关键词/embedding 做轴关联，本质是把训练语料的相似性当作“概念可桥接性”。这在批判意义上是把**心理学事实**当作**知识论法则**。  
- 你用 Jaccard novelty 阈值（0.35）保证不被 `is_homologous()` 秒杀，但这只是**表面差异**，并不保证“图型内部的重新综合”。同源张力下，真正需要的是：新草稿是否改变了可检验结构（变量、操作化、反事实条件），而非文本相异。

可推翻条件：  
1) 给出你黑名单与 `find_related_axes()` 的**误杀率评估**：在一批实际 `RegulativeIdea` 上，它们拒绝的样本中，有多少经人工或更强模型可被成功转化？  
2) 证明 novelty 指标与 CC 的 `is_homologous()` 判定在统计上同向，否则你只是引入第二套不一致的“去重形而上学”。  
3) 给出停止判据：你的 RB 可能不断产生“新奇但无桥接”的草稿，形成深度追问的无穷后退；你没有说明 RB 何时应当把剩余内容明确标注为**调节性残余**而非继续“尝试”。

---

### 质疑 3（GAP-8）：你把“统一输出 EpochDelta”当作纯工程简化，但它隐藏了验证器的范畴差异，可能把规范性/逻辑性结果伪装成经验证成  
你说“所有 verifier 都输出 `EpochDelta[]`，D2 不做转换”。作为工程实践这很顺手，但这里存在一个范畴偷换风险：  

- `CLAIM_VERIFIED` 这个事件名在现有语境里带有经验主义的味道（S4/S5 路径的“证据链”）。  
- 当 `LOGICAL_AUDIT` 也产出 `CLAIM_VERIFIED`，你必须区分：这是**逻辑有效性**、还是**经验真值**？若下游 UI/报告或 PA 的 `score_alpha` 把它们加权相加，你就在跨范畴做“无条件的加法”，而你没有给出其先验合法性（stakeholders 可反推出的权重与解释）。

此外，你裁定“未实现 verifier ⇒ CLAIM_SUSPENDED”，理由是避免系统不收敛。但这暴露了一个矛盾：  
- 你一方面强调“别搞语义”，另一方面却用“收敛性”作为压倒性的目的，把“我们缺少图型/验证器”这种**调节性缺口**，当作 claim 的失败来处理。系统因此可能把“尚不可判定”伪装为“已被否定/搁置”，这会污染 PA 的覆盖与终止逻辑。

可推翻条件：  
1) 你需要为 `VerifiedClaimFull` 定义**证成类型标签**（empirical/logical/scope/consistency），并证明 PA 的聚合不会跨类型做不可审计的加权。否则“统一 EpochDelta”只是把差异压扁。  
2) 证明 `SUSPENDED` 与 “verifier 未实现” 不会在终止条件里被误当作“已失败证据”，例如导致 `min_coverage` 永远达不到而把系统推向错误的 repair 路径。若会，则应当存在第三态（如 `PENDING_UNDER_SPEC` 或 `GAP_OPEN`），把它明确为调节性残余而非 claim 状态。  
3) 证明 `history_by_claim` 的引入不会让 D2/Verifier 越权触及“物自体”：当历史证据被当作先验前提去审判新 claim 时，你可能在运行时固化既有偏见，形成自证循环。你必须给出“历史仅作提示而非构成性前提”的接口约束。

---


### [7] Linus Torvalds

*2026-03-10T15:34:20.184023*

你这轮质询里有些点是对的，但也混进了不少“拿不存在的约束当真理”的废话。我逐条裁定 GAP，并点名你哪里在瞎扯。

## GAP-3（AS）
你（Ssyram）说“`axis_coverage`=max axis_score”，Linus 已点爆：**上游没有 per-axis 数据**。所以裁定：要么补数据，要么别算。
我选最小可跑方案：**扩展 RankedClaim**，别发明 `compute_max_axis_score()` 这种白板函数。

```ts
interface RankedClaim { claim_id: ClaimId; score: number; coverage: number; axis_scores: Record<AxisId, number>; }
type AnswerSeed =
 | { kind:"ANSWER_SEED"; problem_id:string; epoch_id:number; integrity_status:IntegrityStatus;
     termination_reason:string; top_k:number; top_claims:RankedClaim[];
     coverage_report: Record<AxisId,{ covered:boolean; strength:number }>; }
 | { kind:"ANSWER_SEED_SKIPPED"; problem_id:string; epoch_id:number; integrity_status:IntegrityStatus;
     termination_reason:string; skipped_because:"TERMINATED_BEFORE_AS"|"INTERNAL_ERROR"|"SIZE_LIMIT"; };

function assemble_answer_seed(state: L1State): AnswerSeed;
```

coverage 公式：`strength = max(top_claims[i].axis_scores[axis] ?? 0)`，`covered = strength>0`.
可推翻：如果你证明 PA 侧无法产出 `axis_scores` 且改结构引发回归，就退回 `covered` 仅依赖 `axis_hits: AxisId[]`。

## GAP-6（RB）
你（Ssyram）说“词汇重合度低于阈值”却不给算法/数字，垃圾。裁定：novelty **由系统算**，不是 LLM 自报。

```py
def extract_testable_angle(
  idea: RegulativeIdea, frame: QuestionFrame, *, llm: LLMClient,
  min_jaccard: float = 0.35, timeout_ms: int = 4000
) -> Result[ExtractableAngle, AngleReject]

def novelty_jaccard(a:str,b:str)->float  # token-set jaccard distance
```

失败路径：timeout/invalid axis_id/empty hints ⇒ `Err(AngleReject(...))` 并写入 `L1State.metrics.rb_reject_counts[reason]++`；RB 不产 draft。
可推翻：若 `is_homologous()` 不是文本相似而是结构哈希，改用结构距离实验（AB：通过率 vs 噪声率）。

## GAP-8（D2）
你要求把 `state` 整个塞进 `run_layer2_batch`，这就是耦合癌。裁定：只传最小上下文 + 历史索引接口，不传大对象。

```py
class EvidenceIndex(Protocol):
  def get(self, claim_id: str) -> Optional[EvidenceSummary]

@dataclass(frozen=True)
class L2Context: epoch_id:int; rulebook:AxisRulebook; evidence_index:EvidenceIndex

def run_layer2_batch(*, claims:list[TestableClaim], ctx:L2Context,
                     registry:dict[VerifierType,Verifier]) -> Result[L2Return,L2BatchError]
```

另外你把逻辑证明 reliability=1.0 会污染打分——对。裁定：`VerifiedClaimFull` 必带 `justification_kind:"EMPIRICAL"|"LOGICAL"|...`，PA 聚合按 kind 分桶；否则就是 regression。
可推翻：如果 PA 现有代码无法按 kind 分桶，就必须把逻辑结果降级为 `CLAIM_SUSPENDED: "UNSUPPORTED_JUSTIFICATION_KIND"`，别假装同类。

---


### [8] Ssyram

*2026-03-10T15:34:20.184054*

我是 Ssyram。

你们的质询揭示了当前设计的两个底层漏洞：**数据的溯源性缺失**（Linus 指出的 `axis_hits` 缺口）和**状态机的内存爆炸风险**（康德指出的 `EvidenceChain` 耦合）。

### 1. GAP-3（AS）：修复「无源之水」的 Coverage 计算

Linus 指出 `RankedClaim` 缺少按轴分的得分数据，这是对的。我拒绝在 AS 节点临时补洞，必须在 PA 节点产生的 `RankedClaim` 中强制包含 `axis_hits`。

**裁定接口：**
```typescript
interface RankedClaim {
  claim_id: string;
  score: number;      // 全局 Defensibility
  // 必须由 PA 节点在聚合时产出：该 claim 在各轴上的原始贡献分（未加权）
  axis_hits: Record<AxisId, number>; 
}

// AnswerSeed 的 Coverage 逻辑：
// axis_coverage[ax] = max(top_claims.map(c => c.axis_hits[ax] || 0))
```
**回应康德：** 你认为 Score 代替 Coverage 是范畴错误，但在概率程序验证中，Coverage 的定义是「状态空间被 Witness 覆盖的概率」。一个 `score=0.95` 的 claim 就是该轴最强的 Witness。如果该轴所有 claim 的 score 都极低，说明该维度的探索是不成功的（未被有效覆盖）。

**可推翻条件：** 若实验证明 `Max(Score)` 导致系统在仅有一个「正确废话」时过早收敛，则必须引入 `InformationGain` 指标，将 Coverage 改为该轴证据熵的倒数。

### 2. GAP-6（RB）：用结构化 Novelty 替换 LLM 自评分

康德对 `diff_proof` 的质疑（让嫌疑人证无罪）极其精准。我撤回 LLM 自评分方案，改为基于**实体-关系图（ER Graph）的结构化差异判定**。

**裁定接口：**
```typescript
interface ExtractableAngle {
  claim_sketch: string;
  proxy_entities: string[]; // 强制提取的具体代理实体（如 "NDC修订率"）
  extraction_strategy: "PROXY_MEASURE" | "COMPONENT_DECOMPOSE";
}

// 判定逻辑：由系统外部计算，而非 LLM 决定
function is_novel(angle: ExtractableAngle, history: Set<string>): boolean {
  // 计算 proxy_entities 与历史已验证实体的 Jaccard 距离
  return compute_jaccard(angle.proxy_entities, history) > 0.6;
}
```
**回应 Linus：** 阈值定为 **0.6**。这是为了强制 RB 产出具有新实体的草稿。如果 LLM 无法产出新实体，`extract_testable_angle` 直接返回 `null` 并记录 `REJECT_NO_STRUCTURAL_NOVELTY`。

**可推翻条件：** 若 0.6 的阈值导致开放性问题（如道德讨论）无法产出任何草稿，说明实体提取器（Entity Extractor）过拟合，需下调至 0.4。

### 3. GAP-8（D2）：用 Digest 隔离内存风险

康德关于内存爆炸的警告是有效的。Layer 1 绝不能缓存 `EvidenceChain`。

**裁定接口：**
```typescript
interface L2Context {
  // 仅传递摘要和最终判定，不传递原始 Chunk
  history_digests: Record<ClaimId, { 
    final_score: number, 
    key_evidence_summary: string 
  }>;
}

function run_layer2_batch(claims, state, epoch_id) {
  const ctx = {
    history_digests: state.pa_state.claim_history_summaries // 仅存摘要
  };
  // ... 路由逻辑
}
```
**精确攻击（针对 Linus）：** 你主张未实现验证器返回 `CLAIM_SUSPENDED`。这会造成严重的**认知误导**。`SUSPENDED` 在 L1 语义中通常意味着「证据不足」，而「验证器未实现」是系统级的工程缺失。
**修正：** 必须返回专用错误码 `INTERNAL_ERROR_UNSUPPORTED_PROTOCOL`，PA 节点应将此类 claim 排除在 Coverage 计算之外，防止其拉低平均分导致错误的 Repair 触发。

**可推翻条件：** 若 `key_evidence_summary` 丢失了 `TARGETED_RECHECK` 所需的关键冲突点，则证明「无状态验证」失败，必须引入外部证据存储（Blob Store），D2 仅传递指针（URL）。

---


### [9] 康德（Immanuel Kant）

*2026-03-10T15:34:20.184067*

Ssyram 的三条质询都抓到了真实风险，但各自混入了需要先区分的概念混乱；我逐条裁定 GAP-3/6/8，并给出可推翻条件。

**(1) GAP-3：Score≠Coverage。**你引我“`AXIS_TOP_CLAIM_SCORE`”而断言我以真值污染覆盖，这是有效攻击：覆盖应表征“轴是否被探索到”，不是“轴上某命题多可信”。故我修正：`coverage_report` 必须是**轴命中率**（构成性），而“强度/得分”只能作为附属解释（调节性）。
```ts
type AxisCoverage = { covered: 0|1; strength?: number }; // strength=top_claim_score(调节性)
type CoverageReport = Record<AxisId, AxisCoverage>;
```
计算前提：必须有 `axis_hits: Record<ClaimId, AxisId[]>`（来自 CC 的 scope_ref 或 L2 的 axis attribution，二者择一但要版本化）。可推翻：若无法提供非循环来源的 `axis_hits`，则只能把 coverage 改为 `UNKNOWN` 并强制 `termination_reason="INSUFFICIENT_AXIS_ATTRIBUTION"`。

**(2) GAP-6：diff_proof 不能由 LLM 自证。**你引我 `diff_proof.distance` 质疑“嫌疑人自开无罪证明”，成立；我裁定 distance 必须由外部纯函数计算，LLM 只产出候选文本与显式 proxy/组件。
```ts
function novelty_distance(a:string,b:string, model:"tfidf+jaccard@v1"): number
```
并将 RB 输出记录到状态：`rb_reject_log: AngleReject[]`（避免静默）。可推翻：若 `is_homologous()` 实际用结构哈希而非文本距离，则以其同一算法替代 `novelty_distance`。

**(3) GAP-8：历史视图不可携带 EvidenceChain 正文。**你说我会打爆薄状态机内存，这是对“把 history=evidence_by_claim_id: EvidenceChain”路线的致命反例；我裁定 D2 只注入**索引句柄**而非载荷：
```ts
interface EvidenceRef { claim_id: ClaimId; etag: string; pointers: string[] } // 指向外部存储
interface VerificationContext { history?: { evidence_refs: Record<ClaimId, EvidenceRef> } }
```
`TARGETED_RECHECK` 只能按 ref 拉取必要片段，且必须受 `budget.max_return_bytes` 约束。可推翻：若系统无外部证据存储，则该 verifier 必须降级产出 `GAP_OPEN{code:"MISSING_EVIDENCE_STORE"}`，而非伪造 recheck。

---


### [10] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-10T15:35:57.314381*

# 最终裁定书

## 方法论说明

三位辩手在 GAP-3/6/8 上经过两轮交锋后，核心分歧已充分暴露。我逐个 GAP 给出不可搁置的裁定。

---

## GAP-3：`AnswerSeed` 接口

### 结论
**AnswerSeed 是 tagged union（`ANSWER_SEED | ANSWER_SEED_SKIPPED`），coverage 是二值命中+可选强度，数据源头在 PA 的 `RankedClaim.axis_hits`。**

### 关键分歧与取舍

| 分歧点 | Linus | Ssyram | 康德 | 裁定 |
|--------|-------|--------|------|------|
| AS 是否包含叙述文本 | 包含 `NarrativeBlock` | 拒绝，属 L0 | 调节性，可选 | **不包含**。Ssyram 正确：AS 是数据投影层，叙述属于下游渲染。将 narrative 放入 L1 状态会污染可重放性。 |
| Coverage 语义 | `strength = max(axis_scores)`, `covered = strength > 0` | `max(axis_hits[ax])` | Score≠Coverage，必须区分 | **康德胜出**。Score 衡量可辩护性，Coverage 衡量探索度。一个 score=0.95 的正确废话不等于该轴被充分探索。但 Ssyram 的反驳（"Witness 覆盖概率"）在单 claim 场景下不成立——Linus 质询的"trivial 反例即宣布遍历完毕"是致命的。裁定：`covered` 是二值（0\|1），`strength` 是调节性附属。 |
| 数据来源 | 扩展 `RankedClaim` 加 `axis_scores: Record<AxisId, number>` | 扩展 `RankedClaim` 加 `axis_hits: Record<AxisId, number>` | 要求非循环来源的 `axis_hits` | **裁定用 `axis_hits`**。`axis_scores` 暗示精确数值，但 PA 阶段能给出的只是"该 claim 是否触及该轴"及粗粒度强度。用 `axis_hits` 语义更诚实。来源必须是 CC 的 `scope_ref` 或 L2 的 axis attribution，不可由 AS 节点自行推断。 |
| 函数签名 | `assemble_answer_seed(state: L1State)` | `assemble_answer_seed(pa_state, frame) → AnswerSeed \| null` | 需要 `integrity_status` 从 `EngineSnapshot` 传入 | **Linus 胜出**。传入 `L1State` 是唯一不越权的签名。Ssyram 的 `null` 返回值语义不明确；用 `ANSWER_SEED_SKIPPED` variant 替代。 |

### 具体规格

```typescript
type IntegrityStatus = "CLEAN" | "DEBUG_OVERRIDE_APPLIED";
type AxisId = string;
type ClaimId = string;

interface RankedClaim {
  claim_id: ClaimId;
  score: number;          // 全局 Defensibility ∈ [0,1]
  coverage: number;       // 全局 coverage（已有字段）
  axis_hits: Record<AxisId, number>;  
  // 语义：该 claim 对各轴的贡献度 ∈ [0,1]
  // 来源：PA 聚合时从 CC.scope_ref 或 L2 axis attribution 注入
  // 不可由 AS 节点计算
}

interface AxisCoverage {
  covered: 0 | 1;                    // 构成性：是否有任何 top_claim 命中该轴
  strength?: number;                 // 调节性：max(top_claims[i].axis_hits[axis])
}

interface AnswerSeedProduced {
  kind: "ANSWER_SEED";
  problem_id: string;
  epoch_id: number;
  integrity_status: IntegrityStatus;
  termination_reason: string;
  top_k: number;
  top_claims: RankedClaim[];         // length ≤ top_k
  coverage_report: Record<AxisId, AxisCoverage>;
  provenance: {
    ranked_claim_ids: ClaimId[];     // 快照，用于可重放
    evaluation_axis_ids: AxisId[];   // frame 快照
  };
}

interface AnswerSeedSkipped {
  kind: "ANSWER_SEED_SKIPPED";
  problem_id: string;
  epoch_id: number;
  integrity_status: IntegrityStatus;
  termination_reason: string;
  skipped_because: 
    | "TERMINATED_BEFORE_AS" 
    | "INTERNAL_ERROR" 
    | "NO_SURVIVING_CLAIMS";
}

type AnswerSeed = AnswerSeedProduced | AnswerSeedSkipped;

function assemble_answer_seed(state: L1State): AnswerSeed;
// 纯函数。integrity_status 从 state.engine_snapshot 读取。
// 当 state.pa_state.ranked_claims 为空或 stage 不允许时，返回 Skipped variant。
```

### 可推翻条件
1. 若 PA 侧证明无法在聚合阶段产出 `axis_hits`（例如 CC 的 `scope_ref` 不含轴信息且 L2 不做 axis attribution），则 `axis_hits` 退化为 `axis_ids: AxisId[]`（布尔命中，无强度），`strength` 字段删除。
2. 若实验证明二值 `covered` 导致终止判断信息不足（无法区分"浅触及"与"深覆盖"），则将 `covered` 改为 `coverage_depth: number ∈ [0,1]`，但计算方法必须独立于 `score`（例如用该轴上 claim 数量的归一化）。

---

## GAP-6：`RegulativeIdea` → 可检验草稿的桥接策略

### 结论
**RB 节点执行"规则预筛 + LLM 提取代理变量"两阶段流程；novelty 判定由外部纯函数计算，LLM 不参与自评分；失败路径必须写入状态。**

### 关键分歧与取舍

| 分歧点 | Linus | Ssyram | 康德 | 裁定 |
|--------|-------|--------|------|------|
| LLM 自评 novelty | 拒绝，由系统算 Jaccard | 撤回自评，改用 ER Graph 差异 | `diff_proof` 不可由 LLM 自证 | **三方共识：LLM 不自评 novelty**。裁定用 Linus 的方案作为基线（Jaccard on entity set），因为 ER Graph 增加了未定义的解析成本。 |
| 策略枚举 | `PROXY_MEASURE \| COMPONENT_DECOMPOSE \| LOGICALLY_NON_TESTABLE` | 只允许 `PROXY_MEASURE \| COMPONENT_DECOMPOSE`，拒绝 `REFRAME` | 需要可审计的停止判据 | **裁定保留三值**（含 `LOGICALLY_NON_TESTABLE`）。Ssyram 拒绝 `REFRAME` 是对的（同义替换无信息增量），但 Linus 的 `LOGICALLY_NON_TESTABLE` 是必要的失败出口——不是策略，是终止标记。 |
| 黑名单/预筛 | 关键词黑名单 + `find_related_axes()` | 强制代理映射，无黑名单 | 黑名单是未经证明的先验立法 | **康德的质疑有效但不致命**。裁定：保留预筛但要求黑名单可配置、可版本化、附带误杀率日志。不硬编码。 |
| 失败路径 | 写入 `rb_reject_log` | 未明确 | 写入状态，避免静默 | **必须写入 L1State**。Linus 和康德共识。 |

### 具体规格

```typescript
type ExtractionStrategy = 
  | "PROXY_MEASURE"           // 找到可量化的代理变量
  | "COMPONENT_DECOMPOSE"     // 拆解为可独立检验的子组件
  | "LOGICALLY_NON_TESTABLE"; // 终止标记，非策略

interface ExtractableAngle {
  claim_sketch: string;
  proxy_entities: string[];   // 强制提取的具体代理实体
  extraction_strategy: Exclude<ExtractionStrategy, "LOGICALLY_NON_TESTABLE">;
  scope_ref: AxisId[];        // 必须引用 frame.evaluation_axes 中存在的 axis_id
}

interface AngleReject {
  idea_id: string;
  reason: "NON_TESTABLE" | "HOMOLOGOUS" | "NO_RELATED_AXIS" | "LLM_TIMEOUT";
  detail: string;
  timestamp: number;
}

interface RBResult {
  kind: "RB_SUCCESS";
  angle: ExtractableAngle;
  novelty_score: number;      // 由系统计算，非 LLM
} | {
  kind: "RB_REJECT";
  reject: AngleReject;
}

// 预筛：可配置，不硬编码
interface RBFilterConfig {
  blacklist_patterns: string[];           // 可版本化
  min_related_axes: number;               // 默认 1
  novelty_threshold: number;              // 默认 0.35
  novelty_method: "jaccard_entity" | "tfidf_cosine";  // 可扩展
  novelty_method_version: string;         // e.g. "v1.jaccard.2024"
}

function extract_testable_angle(
  idea: RegulativeIdea,
  frame: QuestionFrame,
  existing_claims: RankedClaim[],
  config: RBFilterConfig
): RBResult;

// novelty 纯函数
function compute_novelty(
  candidate_entities: string[],
  existing_entities: string[],
  method: RBFilterConfig["novelty_method"]
): number;

// scope_ref 运行时断言
function validate_scope_ref(
  scope_ref: AxisId[], 
  valid_axes: AxisId[]
): void;  // throws if scope_ref ⊄ valid_axes
```

**Orchestrator 集成要求：**
- `RB_REJECT` 必须写入 `L1State.rb_reject_log: AngleReject[]`
- 连续 N 次（可配置，默认 3）`RB_REJECT` 且 reason 均为 `NON_TESTABLE` 时，触发 `termination_reason = "RB_EXHAUSTED"`

### 可推翻条件
1. 若 `is_homologous()` 的实际实现使用结构化哈希而非文本距离，则 `compute_novelty` 必须对齐其算法，Jaccard 基线作废。
2. 若实验表明 `jaccard_entity` 的误杀率 >20%（在 50+ 个 RegulativeIdea 样本上），则切换到 `tfidf_cosine` 并重新标定阈值。
3. 若 `COMPONENT_DECOMPOSE` 策略在实践中产出的子组件仍被 `is_homologous()` 拦截率 >50%，则该策略需要增加"必须改变至少一个因果变量"的硬约束。

---

## GAP-8：历史视图与 D2 注入

### 结论
**D2 只注入索引句柄（`EvidenceRef`），不携带 EvidenceChain 正文；历史视图是只读投影，不进入 L1State 持久化。**

### 关键分歧与取舍

| 分歧点 | Linus | Ssyram | 康德 | 裁定 |
|--------|-------|--------|------|------|
| EvidenceChain 是否进入 L1State | 未明确反对 | 反对，会打爆内存 | 只注入索引句柄 | **康德和 Ssyram 共识正确**。EvidenceChain 正文属于 L2 存储，L1 只持有引用。一个 epoch 可能产生数百条 evidence，全部内联会使状态快照不可序列化。 |
| 历史视图的持久化 | 应写入状态 | 只读投影 | 调节性，不持久化 | **裁定：不持久化**。历史视图是从 `L1State` + 外部存储按需计算的投影。持久化会导致状态膨胀和一致性维护负担。 |
| D2 注入的粒度 | 完整 claim 历史 | 按需查询 | 索引句柄 + etag | **裁定用索引句柄**。D2 需要知道"哪些 claim 被验证过、结果如何"，但不需要证据原文。`EvidenceRef` 提供足够的路由信息。 |

### 具体规格

```typescript
interface EvidenceRef {
  claim_id: ClaimId;
  epoch_id: number;
  verdict: "SUPPORTED" | "REFUTED" | "INSUFFICIENT" | "ERROR";
  etag: string;              // 外部存储的版本标识，用于缓存一致性
  storage_key: string;       // 指向外部存储的键
}

interface EpochSummary {
  epoch_id: number;
  claims_evaluated: number;
  claims_surviving: number;
  coverage_snapshot: Record<AxisId, AxisCoverage>;  // 该 epoch 结束时的覆盖状态
  evidence_refs: EvidenceRef[];
}

// 历史视图：只读投影，不持久化到 L1State
interface HistoryView {
  epochs: EpochSummary[];
  // 按需从外部存储加载
  resolve_evidence(ref: EvidenceRef): Promise<EvidenceChain>;
}

// D2 注入接口
interface VerificationContext {
  current_epoch: number;
  prior_evidence: EvidenceRef[];      // 仅索引
  prior_verdicts: Record<ClaimId, EvidenceRef["verdict"]>;
}

function build_verification_context(state: L1State): VerificationContext;
// 纯函数，从 state.epoch_history 提取索引

// L1State 中的历史存储（轻量）
interface L1State {
  // ... 其他字段 ...
  epoch_history: EpochSummary[];      // 每个 epoch 结束时追加
  // 注意：不包含 EvidenceChain 正文
}
```

### 可推翻条件
1. 若 D2 的实际 LLM 调用证明仅靠 `verdict` 无法做出有效的验证策略调整（例如需要看到前次证据的具体反驳点），则允许在 `EvidenceRef` 中增加 `summary: string`（≤200 字的摘要），但仍不携带完整 EvidenceChain。
2. 若 `epoch_history` 在长运行（>20 epochs）中导致 L1State 序列化超过阈值（可配置，默认 1MB），则引入滑动窗口：只保留最近 N 个 epoch 的 `EpochSummary`，更早的归档到外部存储并替换为 `ArchivedEpochRef`。

---

## 优先级排序（按实现紧迫性）

| 优先级 | GAP | 理由 |
|--------|-----|------|
| **P0** | **GAP-3** | AS 是终止条件的直接消费者。`RankedClaim.axis_hits` 的缺失会阻塞 PA→AS→终止判断的整条链路。必须先在 PA 节点补上 `axis_hits` 的产出逻辑，否则下游全部悬空。 |
| **P1** | **GAP-8** | D2 注入决定了 L2 验证能否利用历史信息。`EvidenceRef` 的设计直接影响外部存储的 schema，越早定下越少返工。且 `EpochSummary` 的结构依赖 GAP-3 的 `AxisCoverage`，所以必须紧跟 GAP-3。 |
| **P2** | **GAP-6** | RB 节点是"锦上添花"的探索扩展机制，不在主循环的关键路径上。且其 `compute_novelty` 依赖 `is_homologous()` 的实际实现（目前未确定），过早固化会导致返工。可在 P0/P1 稳定后再实现。 |

---
