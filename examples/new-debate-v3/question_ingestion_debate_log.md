# v3 认知引擎：normalize_question() 与 macro_breadth() 的实现决策 辩论日志

> 2026-03-09T18:30:50.878509

---


### [1] Linus Torvalds

*2026-03-09T18:19:01.450210*

我选 **F：`macro_breadth()` 的 tension_source 分类与覆盖策略**。这是最关键的，因为这是 Layer 1 真正把“结构化问题”变成“可编译候选命题”的地方。你在这里搞含糊，后面全是垃圾输入的精致处理。

我的立场很简单：

> **三类 tension source 不是“随缘触发”，而是一个有类型约束、覆盖下界、显式 fallback 的枚举式生成器。**
> `macro_breadth()` 不能静默依赖“立场冲突存在”这个语义假设；它必须在没有明显冲突时，退化到 **axis-driven split** 和 **stakeholder delta**，再不行就返回结构化失败，而不是产出空数组或者胡编外部立场。

---

# 1) 具体设计选择

## 1.1 类型与函数签名

我先给完整接口，不玩白板空话。

```typescript
type TensionKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT";

type MacroBreadthConfig = {
  max_drafts: number;                  // hard upper bound
  per_axis_cap: number;                // avoid one axis flooding output
  require_axis_coverage: boolean;      // at least one draft per axis when possible
  require_kind_diversity: boolean;     // prefer multiple tension kinds
  external_position_limit: number;     // max externally injected positions
  default_ttl: number;                 // initial ttl for all drafts
};

type ExternalPosition = {
  position_id: string;
  problem_id: string;
  text: string;
  source_ref?: string[];
  applies_to_axes?: string[];
};

type DraftCandidate = {
  kind: TensionKind;
  axis_id?: string;
  stakeholder_pair?: [string, string];
  external_position_id?: string;
  claim_sketch: string;
  verifier_hint: string[];
  evidence_ref?: string[];
  score: number;
};

type MacroBreadthError =
  | {
      code: "NO_TENSION_CANDIDATE";
      problem_id: string;
      detail: string;
      frame_snapshot: Pick<QuestionFrame, "scope" | "stakeholders" | "evaluation_axes" | "open_terms">;
    }
  | {
      code: "FRAME_MISSING_SCOPE";
      problem_id: string;
      detail: string;
    }
  | {
      code: "FRAME_MISSING_AXES";
      problem_id: string;
      detail: string;
      fallback_attempted: boolean;
    };

type Result<T, E> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function macro_breadth(
  frame: QuestionFrame,
  external_positions: ExternalPosition[],
  config: MacroBreadthConfig
): Result<HypothesisDraft[], MacroBreadthError>;
```

现在重点：**输入是什么、怎么触发、输出什么、失败怎么处理**都清楚了。

---

## 1.2 核心约束

我的方案有三个硬约束：

1. **不允许静默空输出**
   - 如果没有任何可生成草稿的 tension candidate，返回 `NO_TENSION_CANDIDATE`
   - 不是 `[]`，因为空数组会把失败伪装成“没有更多想法”

2. **生成优先级明确**
   - 第一优先：`EVALUATION_AXIS_SPLIT`
   - 第二优先：`STAKEHOLDER_CONFLICT`
   - 第三优先：`EXTERNAL_POSITION`

3. **fallback 显式**
   - `evaluation_axes` 非空：至少尝试 axis split
   - `evaluation_axes` 为空：**不能假装系统还能正常工作**
     - 如果允许 fallback，则尝试 stakeholder/external
     - 如果 fallback 后仍无候选，返回 `FRAME_MISSING_AXES` 或 `NO_TENSION_CANDIDATE`

---

## 1.3 关键分支处理逻辑

```typescript
function macro_breadth(
  frame: QuestionFrame,
  external_positions: ExternalPosition[],
  config: MacroBreadthConfig
): Result<HypothesisDraft[], MacroBreadthError> {
  if (!frame.scope || frame.scope.trim() === "") {
    return {
      ok: false,
      error: {
        code: "FRAME_MISSING_SCOPE",
        problem_id: frame.problem_id,
        detail: "macro_breadth requires non-empty QuestionFrame.scope"
      }
    };
  }

  const candidates: DraftCandidate[] = [];
  let fallbackAttempted = false;

  // 1. axis-driven candidates: primary path
  if (frame.evaluation_axes.length > 0) {
    for (const axis of frame.evaluation_axes) {
      const axisCandidates = generateAxisSplitCandidates(frame, axis, config.per_axis_cap);
      candidates.push(...axisCandidates);
    }
  } else {
    fallbackAttempted = true;
  }

  // 2. stakeholder-driven fallback / supplement
  const stakeholderCandidates = generateStakeholderConflictCandidates(frame);
  candidates.push(...stakeholderCandidates);

  // 3. external-position supplement, capped
  const externalCandidates = generateExternalPositionCandidates(
    frame,
    external_positions,
    config.external_position_limit
  );
  candidates.push(...externalCandidates);

  // 4. dedupe + rank
  const deduped = dedupeCandidates(candidates);
  const ranked = rankCandidates(
    deduped,
    config.require_axis_coverage,
    config.require_kind_diversity
  );

  if (ranked.length === 0) {
    if (frame.evaluation_axes.length === 0) {
      return {
        ok: false,
        error: {
          code: "FRAME_MISSING_AXES",
          problem_id: frame.problem_id,
          detail: "No evaluation axes available; all fallback generators also failed",
          fallback_attempted: fallbackAttempted
        }
      };
    }
    return {
      ok: false,
      error: {
        code: "NO_TENSION_CANDIDATE",
        problem_id: frame.problem_id,
        detail: "No valid hypothesis draft candidates generated from axes, stakeholders, or external positions",
        frame_snapshot: {
          scope: frame.scope,
          stakeholders: frame.stakeholders,
          evaluation_axes: frame.evaluation_axes,
          open_terms: frame.open_terms
        }
      }
    };
  }

  const selected = selectWithCoverage(ranked, config.max_drafts, {
    require_axis_coverage: config.require_axis_coverage,
    require_kind_diversity: config.require_kind_diversity
  });

  return {
    ok: true,
    value: selected.map(c => toHypothesisDraft(frame, c, config.default_ttl))
  };
}
```

---

## 1.4 子函数签名

### axis split 生成器

```typescript
function generateAxisSplitCandidates(
  frame: QuestionFrame,
  axis: CoordinateAxis,
  perAxisCap: number
): DraftCandidate[] {
  // axis.mode is already "regulative" by type; if runtime input is dirty, reject
  if (axis.mode !== "regulative") {
    throw new Error(`Invalid axis.mode=${axis.mode}; expected regulative`);
  }

  const candidates: DraftCandidate[] = [
    {
      kind: "EVALUATION_AXIS_SPLIT",
      axis_id: axis.axis_id,
      claim_sketch: `Under scope "${frame.scope}", the best answer differs depending on how heavily we weight ${axis.label}.`,
      verifier_hint: [axis.falsifier, `Compare alternatives under ${axis.label}`],
      evidence_ref: axis.provenance,
      score: 1.0
    }
  ];

  return candidates.slice(0, perAxisCap);
}
```

### stakeholder 冲突生成器

```typescript
function generateStakeholderConflictCandidates(
  frame: QuestionFrame
): DraftCandidate[] {
  const out: DraftCandidate[] = [];
  const stakeholders = frame.stakeholders.filter(Boolean);

  for (let i = 0; i < stakeholders.length; i++) {
    for (let j = i + 1; j < stakeholders.length; j++) {
      out.push({
        kind: "STAKEHOLDER_CONFLICT",
        stakeholder_pair: [stakeholders[i], stakeholders[j]],
        claim_sketch: `A policy optimal for ${stakeholders[i]} may be suboptimal for ${stakeholders[j]} within scope "${frame.scope}".`,
        verifier_hint: [`Compare measurable outcomes for ${stakeholders[i]} vs ${stakeholders[j]}`],
        score: 0.7
      });
    }
  }

  return out;
}
```

### external position 生成器

```typescript
function generateExternalPositionCandidates(
  frame: QuestionFrame,
  externalPositions: ExternalPosition[],
  limit: number
): DraftCandidate[] {
  return externalPositions
    .filter(p => p.problem_id === frame.problem_id)
    .slice(0, limit)
    .map(p => ({
      kind: "EXTERNAL_POSITION",
      external_position_id: p.position_id,
      claim_sketch: p.text,
      verifier_hint: p.source_ref ?? [],
      evidence_ref: p.source_ref,
      score: 0.5
    }));
}
```

### 输出组装

```typescript
function toHypothesisDraft(
  frame: QuestionFrame,
  candidate: DraftCandidate,
  defaultTtl: number
): HypothesisDraft {
  return {
    draft_id: crypto.randomUUID(),
    problem_id: frame.problem_id,
    scope_ref: [frame.scope, ...(candidate.axis_id ? [candidate.axis_id] : [])],
    tension_source: {
      kind: candidate.kind,
      evidence_ref: candidate.evidence_ref,
      note: buildTensionNote(candidate)
    },
    claim_sketch: candidate.claim_sketch,
    verifier_hint: candidate.verifier_hint,
    ttl: defaultTtl,
    failure_count: 0
  };
}
```

---

# 2) 最强论据：边界失败场景

你特别点了这个问题：**“立场冲突驱动广度”在没有明显立场冲突的工程问题上会不会静默失效？fallback 是什么？**

对，这正是我攻击别人的地方。很多方案默认“广度来自对立观点”。这在工程问题上会直接退化成幻觉生成器。

---

## 2.1 具体输入 trace

输入：

```typescript
const frame: QuestionFrame = {
  problem_id: "p-db-index",
  canonical_question: "最优数据库索引策略是什么？",
  scope: "OLTP PostgreSQL workload with high write rate and latency-sensitive point queries",
  stakeholders: ["DBA", "backend engineer", "SRE"],
  evaluation_axes: [
    {
      axis_id: "write_amp",
      label: "write amplification",
      mode: "regulative",
      provenance: ["normalize_question: inferred from workload description"],
      falsifier: "If candidate strategy increases p95 write latency beyond baseline threshold, it fails this axis"
    },
    {
      axis_id: "read_latency",
      label: "point-query latency",
      mode: "regulative",
      provenance: ["normalize_question: inferred from latency-sensitive point queries"],
      falsifier: "If p95 query latency does not improve for target query class, it fails this axis"
    },
    {
      axis_id: "operability",
      label: "operational complexity",
      mode: "regulative",
      provenance: ["normalize_question: inferred from production maintenance burden"],
      falsifier: "If required maintenance exceeds team's operational budget, it fails this axis"
    }
  ],
  excluded_forms: [],
  open_terms: ["optimal"]
};
```

外部立场为空：

```typescript
const external_positions: ExternalPosition[] = [];
```

配置：

```typescript
const config: MacroBreadthConfig = {
  max_drafts: 5,
  per_axis_cap: 1,
  require_axis_coverage: true,
  require_kind_diversity: false,
  external_position_limit: 0,
  default_ttl: 2
};
```

### 我的方案输出

```typescript
{
  ok: true,
  value: [
    {
      draft_id: "d1",
      problem_id: "p-db-index",
      scope_ref: ["OLTP PostgreSQL workload with high write rate and latency-sensitive point queries", "write_amp"],
      tension_source: {
        kind: "EVALUATION_AXIS_SPLIT",
        evidence_ref: ["normalize_question: inferred from workload description"],
        note: "Axis split on write amplification"
      },
      claim_sketch: "Under scope \"OLTP PostgreSQL workload with high write rate and latency-sensitive point queries\", the best answer differs depending on how heavily we weight write amplification.",
      verifier_hint: [
        "If candidate strategy increases p95 write latency beyond baseline threshold, it fails this axis",
        "Compare alternatives under write amplification"
      ],
      ttl: 2,
      failure_count: 0
    },
    ...
  ]
}
```

### 竞争方案会怎样失败

如果对手方案把广度主要绑定在“外部立场冲突”或“显性观点对抗”上，这个输入会发生两种坏事之一：

1. **静默空输出**
   - 没有明显 opposing positions
   - `macro_breadth()` 返回 `[]`
   - 后面 CC/D2 根本没东西处理，但系统还可能误以为“没有候选”

2. **伪造对立立场**
   - 系统编出“应该优先读性能”“应该优先写性能”之类假立场
   - 这不是从输入结构出来的，而是模型在脑补论坛吵架
   - 结果 provenance 是假的，后面验证路径污染

这就是典型的工程失败：**把不存在的社会冲突当成认知广度的唯一燃料。**

---

## 2.2 更恶心的失败场景

输入：

```typescript
const frame: QuestionFrame = {
  problem_id: "p1",
  canonical_question: "最优数据库索引策略是什么？",
  scope: "general",
  stakeholders: [],
  evaluation_axes: [],
  excluded_forms: [],
  open_terms: ["optimal", "index strategy"]
};
```

### 我的方案

返回：

```typescript
{
  ok: false,
  error: {
    code: "FRAME_MISSING_AXES",
    problem_id: "p1",
    detail: "No evaluation axes available; all fallback generators also failed",
    fallback_attempted: true
  }
}
```

这叫 **可观测失败**。系统知道它为什么失败。

### 竞争方案常见死法

- 用 open_terms 硬扩展，瞎生出一堆“如何定义 optimal”
- 用默认领域轴库偷偷注入 read/write/storage/maintenance
- 或者最糟：直接让 LLM 随机 brainstorm 五条草稿

这三种都在把 **normalize_question 的失败** 隐藏成 **macro_breadth 的成功**。这不是鲁棒性，这是把错误传播到更远的地方，让调试更贵。

---

# 3) 已知弱点及缓解措施

## 弱点 1：过于依赖 `evaluation_axes` 质量

对，承认。我的方案把 axis 作为主路径。如果 `normalize_question()` 生成了垃圾轴，`macro_breadth()` 也会围着垃圾轴转。

### 缓解

加运行时断言和最小质量过滤：

```typescript
function isUsableAxis(axis: CoordinateAxis): boolean {
  return (
    axis.mode === "regulative" &&
    axis.label.trim().length > 0 &&
    axis.falsifier.trim().length > 0
  );
}
```

在 `generateAxisSplitCandidates()` 前过滤 unusable axis。全过滤掉则进入 fallback/error，而不是继续产出伪 draft。

---

## 弱点 2：工程问题上 stakeholder conflict 可能也很弱

是的。像数据库索引这种问题，stakeholder 冲突往往不是核心结构，只是补充视角。

### 缓解

这就是为什么我把它放第二优先级，而且 `score` 低于 axis split。它是 supplement，不是 primary driver。

---

## 弱点 3：external positions 容易带来噪音

没错。很多外部立场只是论坛废话。

### 缓解

- `external_position_limit` 硬上限
- 必须 `problem_id` 匹配
- 排名最低
- 没有来源就不给高分

如果有人主张 external position 应该优先，那就是在邀请垃圾输入主导系统。

---

# 4) 对对手可能立场的预攻击

我先打一个最可能出现的坏立场：

> “`macro_breadth()` 应该优先从 `EXTERNAL_POSITION` 触发，以保证不陷入系统自身框架的回音室；如果 frame 没有轴，也可以先加外部 trigger 再说。”

这套话听起来很时髦，但在实现上是烂的。

## 精确攻击点

### 攻击 1：把外部触发当主路径，会让 provenance 降级

`QuestionFrame` 是上游结构化产物，至少有 `scope`、`stakeholders`、`evaluation_axes` 这些受约束字段。  
`EXTERNAL_POSITION` 本质上是低信任外来输入。你让低信任输入压过高信任结构，等于倒置了系统依赖图。

**可推翻条件：**
如果对手能给出一个排序函数签名，证明 external-first 在以下集合上有更高的 downstream compile success rate，我收回这点：

```text
{工程优化问题, 无显性公共立场冲突, 有明确性能/成本/风险轴}
```

没有这个数据，external-first 就是拍脑袋。

---

### 攻击 2：说“没有轴也能先广度探索”通常是在偷换失败语义

如果对手给出类似下面的接口：

```typescript
function macro_breadth(frame: QuestionFrame): HypothesisDraft[]
```

我直接说这接口不合格。为什么？

- 没有错误类型
- 没有 fallback 是否触发的返回信号
- `[]` 无法区分“正常无候选”与“系统结构失败”
- 没有外部输入参数，却又想谈 external trigger，纯扯淡

这种接口就是我说的白板涂鸦。连失败分支都没类型化，你讨论个屁的鲁棒性。

---

# 5) 可推翻条件

我不是在卖宗教。下面这些反例能推翻我的设计选择：

1. **实证反例**  
   在代表性任务集上，`axis-first` 相比 `external-first` 或 `stakeholder-first`：
   - `ClarityCompiler` 编译成功率更低，且差异显著
   - `Layer2` 的 verified claim rate 更低
   - top-k 最终答案稳定性更差

2. **结构反例**  
   存在一大类问题满足：
   - `evaluation_axes` 通常为空或极不稳定
   - 但 `EXTERNAL_POSITION` 稳定且高质量
   - 且 downstream 验证能稳定纠偏  
   如果这类问题占主流，那 axis-first 就不再合理。

3. **接口反例**  
   对手给出一个比我更小、更清晰的接口，同时保留：
   - 显式失败类型
   - fallback 观测性
   - 覆盖约束
   - 输入 provenance  
   那我接受精简。

---

# 6) 顺手点名另一个隐患：G 问题里的 `open_terms`

你特别问了：`open_terms` 给谁用，`macro_breadth()` 消费吗？

我的答案很硬：

> **`macro_breadth()` 不应把 `open_terms` 作为主生成驱动，只能作为 draft ranking penalty / compiler warning source。**

原因很简单：`open_terms: string[]` 连 term role、span、dependency 都没有。拿这种贫血结构直接驱动广度，等于把“未定义词”误当成“应该生成命题的核心张力”。

如果有人主张：

> “针对每个 open term 生成一条定义性草稿”

那我会直接攻击接口：你只有 `string[]`，没有
- term 出现位置
- term 所属子句
- term 与 scope/axis 的依赖
- term 是否已经被某个 stakeholder 语境隐式约束

所以你生成出来的所谓“定义性张力”，大概率只是一些语言学噪音。  
**要么升级 `open_terms` 类型，要么别让它主导 `macro_breadth()`。**

---

# 结论

我的主张：

- **F 的正确设计是：`macro_breadth()` 采用 axis-first、stakeholder-second、external-third 的显式 tension 枚举生成策略**
- **没有显性立场冲突时，不会静默失效**，因为 primary path 不是立场冲突，而是 `EVALUATION_AXIS_SPLIT`
- **如果连轴都没有，不能假装成功**，必须返回结构化错误
- **`open_terms` 不应驱动 breadth 生成**，最多作为排序惩罚或给 CC 的警告输入

一句话总结就是：

> 广度不是“找人吵架”，而是从问题结构里提取可验证的张力。没有结构就失败，别假装系统很聪明。

如果你要第二轮，我会继续追着打 **E**：尤其是你那个 `CoordinateAxis.mode` “永远只能是 regulative” 到底怎么在运行时 enforce，不要再拿 TypeScript 字面量类型冒充系统安全。

---


### [2] Ssyram

*2026-03-09T18:19:01.450244*

我是 Ssyram。

关于 `v3` 架构的设计，我直接切入**问题 G：open_terms 在流水线中的传递与消费方式**。

我的立场非常明确：**`macro_breadth()` 必须对 `open_terms` 保持「盲视」（Blindness）。`open_terms` 只能由 `ClarityCompiler` 在编译阶段作为「断言检查器」（Assertion Checker）消费。**

### 1. 设计选择：ClarityCompiler 的编译契约

将 `open_terms` 混入 `macro_breadth()` 是典型的「关注点分离错误」（Separation of Concerns violation）。`macro_breadth()` 的职责是根据 `tension_source` 生成命题空间，而非定义词汇。一旦 `macro_breadth()` 消费了 `open_terms`，它就会试图在生成假设阶段就「强行定义」术语，这会污染后续的 S4/S5 验证链条，因为定义本身变成了假设的一部分。

以下是 `ClarityCompiler` 的核心编译逻辑签名：

```typescript
// ClarityCompiler 内部逻辑
interface CompilationResult {
  status: "SUCCESS" | "OPEN_TERM_DEPENDENCY_VIOLATION" | "EVALUATION_AXIS_MISMATCH";
  claim?: TestableClaim;
  error_report?: {
    cause: string; // "Term 'X' in claim_sketch is undefined in scope"
    suggestion: "RE_NORMALIZE_QUESTION" | "PROVIDE_DEFINITION";
  };
}

function compile(
  draft: HypothesisDraft, 
  question_frame: QuestionFrame
): CompilationResult {
  // 1. 静态检测：检查 claim_sketch 是否包含未解析的 open_terms
  const detected_open_terms = extract_terms(draft.claim_sketch)
    .filter(term => question_frame.open_terms.includes(term));

  if (detected_open_terms.length > 0) {
    return {
      status: "OPEN_TERM_DEPENDENCY_VIOLATION",
      error_report: {
        cause: `Draft ${draft.draft_id} relies on undefined terms: ${detected_open_terms.join(', ')}`,
        suggestion: "RE_NORMALIZE_QUESTION"
      }
    };
  }

  // 2. 只有通过检查，才进入正式编译
  return { status: "SUCCESS", claim: transform_to_testable(draft) };
}
```

### 2. 最强论据：边界失败场景

**场景**：用户输入 `「AI 是否应该被监管？」`，`QN` 识别出 `open_terms = ["AI", "监管"]`。

*   **竞争方案（让 MB 消费 open_terms）**：`macro_breadth()` 尝试生成：「如果 AI 定义为 LLM，则应监管」和「如果 AI 定义为 AGI，则应监管」。
    *   **失败点**：这导致 `Layer 2` 在验证时，必须同时处理「LLM 的监管」和「AGI 的监管」。如果验证失败，系统无法判断是「命题本身错误」还是「定义选取错误」。这会导致 `S4↔S5` 状态机陷入无限循环，因为命题的语义基准（Grounding）在不断变动。
*   **我的方案（CC 门控）**：`macro_breadth()` 生成基于张力的假设（如「监管会抑制创新」）。`ClarityCompiler` 检查到 `claim_sketch` 中包含 "AI" 或 "监管"，直接抛出 `OPEN_TERM_DEPENDENCY_VIOLATION`。
    *   **优势**：系统立即回退到 `QN` 节点，强制要求 `QN` 对 `open_terms` 进行预定义或约束。这保证了进入 `Layer 2` 的每一个 `TestableClaim` 都是「术语闭包」（Term-closed）的，从而保证了验证的原子性。

### 3. 已知弱点及缓解措施

*   **弱点**：这种设计会显著增加 `Layer 1` 的回退频率（Backtracking Frequency），因为很多初步假设都会因为未定义术语而被拒绝，导致系统看起来「很笨」，在没有外部定义的情况下无法推进。
*   **缓解措施**：在 `CompilationError` 中引入 `hint` 机制。当 `ClarityCompiler` 因为 `open_terms` 拒绝编译时，它不是简单报错，而是向 `QN` 节点发送一个特定的 `RefinementSignal`。该信号携带上下文，要求 `QN` 在下一轮 `normalize_question` 中执行 `resolve_term(term)`，将其从 `open_terms` 移至 `scope` 或 `evaluation_axes` 中。

### 4. 对对手的预攻击

我注意到有些辩手倾向于让 `macro_breadth()` 通过「定义性张力」（Definition-based tension）来处理 `open_terms`。

**指名攻击**：针对主张「让 MB 生成定义分支」的立场。
你们的设计犯了**类型系统错误**。`HypothesisDraft` 的 `tension_source` 必须是语义上的冲突（如 `STAKEHOLDER_CONFLICT`），而不是形式上的歧义（Ambiguity）。你们把「定义歧义」与「命题冲突」混为一谈，这会导致 `macro_breadth()` 的输出空间爆炸。一个词可能有 10 种定义，如果 `MB` 负责处理定义，它就会产生 10 种分支。这不仅是性能问题，更是架构上的**职责蔓延（Responsibility Creep）**。`macro_breadth` 不应具备「语义消歧」的能力，它只应具备「逻辑推演」的能力。

---

### 可推翻条件（Falsifiability）

如果任何一位辩手能够证明：**通过在 `macro_breadth()` 阶段内联 `open_terms` 的定义，能够使得 `Layer 2` 的 `S4↔S5` 状态机收敛速度（Convergence Rate）提升 30% 以上，且不引入 `Semantic Assumption` 的逻辑污染**，则我的设计是次优的，我将放弃此立场。

---


### [3] 康德（Immanuel Kant）

*2026-03-09T18:19:01.450260*

我选择 **问题 F：`macro_breadth()` 的 `tension_source` 分类与覆盖策略**，因为这是 Layer 1 中最容易把“经验性启发式”僭越为“认知法则”的位置；若这里混淆先验张力与经验张力，后续所有 `HypothesisDraft` 的分布都会带着系统性偏差。

---

## 立场：`macro_breadth()` 必须实行**分层张力调度**，明确区分先验张力与经验张力，不允许把三类 `tension_source` 当作同权候选池随机混排

核心主张：

1. `EVALUATION_AXIS_SPLIT` 是 **frame-internal / quasi-a priori** 张力，优先级最高；
2. `STAKEHOLDER_CONFLICT` 与 `EXTERNAL_POSITION` 是 **empirical / revisable** 张力，次级；
3. 当 `QuestionFrame.evaluation_axes` 为空时，**不得伪造内生张力**；只能退化为受限的经验张力探索，或返回结构化失败信号；
4. 对 `is_homologous=true` 的张力簇，**禁止广度扩张**，只允许簇内重组——这与 topic1 已裁定结论一致；
5. `verifier_hint` 必须被视为可疑提示，而非验证结构的预设；因此由 `macro_breadth()` 生成时必须附带置信来源约束。

---

# 1. 具体设计选择

## 类型定义

```typescript
type TensionSourceKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT";

type TensionSource = {
  kind: TensionSourceKind;
  evidence_ref?: string[];
  note: string;
};

type TensionCandidate = {
  candidate_id: string;
  source: TensionSource;
  axis_ids: string[];
  stakeholders: string[];
  is_homologous: boolean;
  epistemic_status: "A_PRIORI_INTERNAL" | "EMPIRICAL_EXTERNAL";
  salience: number;      // 0..1
  coverage_gain: number; // 0..1
};

type BreadthPolicy = {
  max_drafts: number;
  min_axis_coverage: number; // 0..1
  allow_empirical_fallback_when_no_axes: boolean;
  require_external_evidence_for_external_position: boolean;
  verifier_hint_mode: "MINIMAL" | "EVIDENCE_BOUND";
  homologous_cluster_strategy: "NO_EXPANSION" | "INTERNAL_RECOMPOSE_ONLY";
};

type MacroBreadthWarning =
  | "NO_EVALUATION_AXES"
  | "EMPIRICAL_FALLBACK_USED"
  | "LOW_STAKEHOLDER_CONFIDENCE"
  | "VERIFIER_HINT_LOW_CONFIDENCE"
  | "HOMOLOGOUS_TENSION_NOT_EXPANDED";

type MacroBreadthFailure =
  | "INSUFFICIENT_TENSION_SOURCES"
  | "AXISLESS_FRAME_REQUIRES_REPAIR"
  | "EXTERNAL_EVIDENCE_MISSING";

type MacroBreadthResult =
  | {
      ok: true;
      drafts: HypothesisDraft[];
      warnings: MacroBreadthWarning[];
      coverage: {
        axis_coverage: number;
        stakeholder_coverage: number;
        source_kind_coverage: TensionSourceKind[];
      };
    }
  | {
      ok: false;
      failure: MacroBreadthFailure;
      warnings: MacroBreadthWarning[];
      repair_actions: {
        kind: "REQUEST_RENORMALIZATION" | "ADD_EXTERNAL_TRIGGER" | "REQUEST_USER_SCOPE";
        note: string;
      }[];
    };
```

## 函数签名

```typescript
function macro_breadth(
  frame: QuestionFrame,
  external_positions: Array<{ position: string; evidence_ref: string[] }> = [],
  stakeholder_graph: Array<{ a: string; b: string; conflict_note: string; evidence_ref?: string[] }> = [],
  policy: BreadthPolicy
): MacroBreadthResult
```

---

## 关键分支处理逻辑

```typescript
function macro_breadth(
  frame: QuestionFrame,
  external_positions: Array<{ position: string; evidence_ref: string[] }> = [],
  stakeholder_graph: Array<{ a: string; b: string; conflict_note: string; evidence_ref?: string[] }> = [],
  policy: BreadthPolicy
): MacroBreadthResult {
  const warnings: MacroBreadthWarning[] = [];

  // Branch 1: 先检查 frame 的先验可用性
  if (!frame.scope || frame.scope.trim() === "") {
    return {
      ok: false,
      failure: "AXISLESS_FRAME_REQUIRES_REPAIR",
      warnings,
      repair_actions: [
        { kind: "REQUEST_USER_SCOPE", note: "QuestionFrame.scope 为空，无法构造可检验草稿。" }
      ]
    };
  }

  const hasAxes = frame.evaluation_axes && frame.evaluation_axes.length > 0;

  // Branch 2: 生成张力候选，并区分认识论地位
  let candidates: TensionCandidate[] = [];

  if (hasAxes) {
    candidates.push(...derive_axis_split_candidates(frame)); // A_PRIORI_INTERNAL
  } else {
    warnings.push("NO_EVALUATION_AXES");
  }

  candidates.push(...derive_stakeholder_conflicts(frame, stakeholder_graph)); // EMPIRICAL_EXTERNAL

  if (
    !policy.require_external_evidence_for_external_position ||
    external_positions.every(p => p.evidence_ref && p.evidence_ref.length > 0)
  ) {
    candidates.push(...derive_external_position_candidates(frame, external_positions)); // EMPIRICAL_EXTERNAL
  } else {
    warnings.push("EXTERNAL_EVIDENCE_MISSING" as any);
  }

  // Branch 3: 无轴时禁止伪造 axis_split
  if (!hasAxes) {
    candidates = candidates.filter(c => c.source.kind !== "EVALUATION_AXIS_SPLIT");

    if (!policy.allow_empirical_fallback_when_no_axes) {
      return {
        ok: false,
        failure: "AXISLESS_FRAME_REQUIRES_REPAIR",
        warnings,
        repair_actions: [
          {
            kind: "REQUEST_RENORMALIZATION",
            note: "evaluation_axes 为空；不得以伪造内部维度分裂替代问题级修复。"
          },
          {
            kind: "ADD_EXTERNAL_TRIGGER",
            note: "若要继续，只能显式引入外部立场或利益相关方证据。"
          }
        ]
      };
    }

    warnings.push("EMPIRICAL_FALLBACK_USED");
  }

  // Branch 4: 按认识论优先级排序
  candidates.sort((a, b) => {
    const rank = (x: TensionCandidate) =>
      (x.epistemic_status === "A_PRIORI_INTERNAL" ? 100 : 0) +
      x.coverage_gain * 10 +
      x.salience;
    return rank(b) - rank(a);
  });

  // Branch 5: 同源张力簇禁止扩张
  const selected: TensionCandidate[] = [];
  const seenHomologousCluster = new Set<string>();

  for (const c of candidates) {
    const clusterKey = `${c.source.kind}:${c.axis_ids.sort().join(",")}:${c.stakeholders.sort().join(",")}`;

    if (c.is_homologous) {
      if (policy.homologous_cluster_strategy === "NO_EXPANSION") {
        warnings.push("HOMOLOGOUS_TENSION_NOT_EXPANDED");
        continue;
      }
      if (policy.homologous_cluster_strategy === "INTERNAL_RECOMPOSE_ONLY") {
        if (seenHomologousCluster.has(clusterKey)) continue;
        seenHomologousCluster.add(clusterKey);
      }
    }

    selected.push(c);
    if (selected.length >= policy.max_drafts) break;
  }

  if (selected.length === 0) {
    return {
      ok: false,
      failure: "INSUFFICIENT_TENSION_SOURCES",
      warnings,
      repair_actions: [
        {
          kind: "ADD_EXTERNAL_TRIGGER",
          note: "没有足够张力源以生成可区分的 HypothesisDraft。"
        }
      ]
    };
  }

  // Branch 6: 生成 HypothesisDraft；verifier_hint 受限生成
  const drafts = selected.map(c => ({
    draft_id: makeDraftId(),
    problem_id: frame.problem_id,
    scope_ref: [frame.scope],
    tension_source: c.source,
    claim_sketch: synthesize_claim_sketch(frame, c),
    verifier_hint:
      policy.verifier_hint_mode === "MINIMAL"
        ? []
        : bounded_verifier_hint(frame, c), // 只能引用已有证据结构，不得发明验证路径
    ttl: 2,
    failure_count: 0
  }));

  const coverage = computeCoverage(frame, drafts);

  return {
    ok: true,
    drafts,
    warnings,
    coverage
  };
}
```

---

# 2. 最强论据

## 论据核心

`macro_breadth()` 不是“多想几个角度”的随意生成器；它是一个**张力分配器**。  
而张力并不处于同一认识论层级：

- `EVALUATION_AXIS_SPLIT` 来自 `QuestionFrame` 内部结构，表示：**在你自己承认的评估框架内，已有不能同时满足的调节性要求**。这是真正的“框架内冲突”。
- `STAKEHOLDER_CONFLICT` 与 `EXTERNAL_POSITION` 则只表示：**我们目前知道，有人这么想、有人那么想**。这可能只是样本有限、资料偏斜，甚至只是噪声。

若不分层，系统就会把“外部知识库里正好抓到的争论”误认作“问题本身的结构性冲突”。

---

## 边界失败场景

### 输入 X

```typescript
const frame: QuestionFrame = {
  problem_id: "p1",
  canonical_question: "AI should be open source?",
  scope: "frontier model weights for general-purpose models",
  stakeholders: ["model_developers", "open_source_researchers", "public_safety_regulators"],
  evaluation_axes: [
    {
      axis_id: "safety",
      label: "misuse-risk containment",
      mode: "regulative",
      provenance: ["raw_question: should", "context_doc_1"],
      falsifier: "If open release does not measurably increase misuse capability relative to controlled access."
    },
    {
      axis_id: "innovation",
      label: "innovation diffusion",
      mode: "regulative",
      provenance: ["context_doc_2"],
      falsifier: "If closed release yields equal or better external research productivity and tool diffusion."
    }
  ],
  excluded_forms: [],
  open_terms: ["open source", "AI"]
};

const external_positions = [
  { position: "Open source always accelerates safety through transparency.", evidence_ref: [] }, // 无证据
  { position: "Closed models are always safer.", evidence_ref: ["kb:report:12"] }
];
```

### 我的方案如何处理

- 先从 `evaluation_axes` 中导出 `EVALUATION_AXIS_SPLIT`：安全 vs 创新扩散 的内部张力；
- 无证据的 external position 若 policy 要求证据，则不进入候选池；
- 即使 external position 存在，也排在 axis split 之后；
- 生成的 draft 首先围绕：
  - “在前沿模型权重开放条件下，创新扩散增益是否超过误用风险增益？”
  - 而不是围绕某个外部口号式立场。

### 竞争方案会怎样失败

若采用“**三类张力源同权混排，按 salience/检索热度直接生成**”的方案，那么最可能先选中的，是训练语料中高频的口号式立场：

- “Open source improves safety through transparency”
- “Closed release is safer by default”

这会导致两个失败：

1. **将外部争论误当问题结构**  
   这些只是现成说法，不等于框架内最关键张力。
2. **ClarityCompiler 被 verifier_hint 污染**  
   如果草稿围绕先入立场而非轴间冲突，编译出的 `TestableClaim` 很可能预设单一证据方向，如“寻找透明性促进安全的案例”，而忽略“创新收益与滥用风险之间是否可比较”这一真正难题。

---

## 另一个边界失败场景：`evaluation_axes = []`

```typescript
const frame: QuestionFrame = {
  problem_id: "p2",
  canonical_question: "Should society regulate AI?",
  scope: "society-wide",
  stakeholders: ["government", "firms", "citizens"],
  evaluation_axes: [],
  excluded_forms: ["UNBOUNDED_SCOPE"],
  open_terms: ["society", "regulate", "AI"]
};
```

### 我的方案

若 `allow_empirical_fallback_when_no_axes = false`：
- 直接返回 `AXISLESS_FRAME_REQUIRES_REPAIR`
- repair action:
  - `REQUEST_RENORMALIZATION`
  - `ADD_EXTERNAL_TRIGGER`

若 `allow_empirical_fallback_when_no_axes = true`：
- 明确加 warning：`NO_EVALUATION_AXES`, `EMPIRICAL_FALLBACK_USED`
- 只允许从 stakeholder/external evidence 生成**临时性草稿**
- 禁止生成 `EVALUATION_AXIS_SPLIT`

### 竞争方案失败点

若竞争方案在无轴时“自动补全默认轴库”，例如安全/公平/创新/成本，那么它实际上在宣称：

> 我预先知道任何 AI 监管问题都应当按这些维度来理解。

这正是把经验偏好僭越为认知法则。  
**可推翻条件**：若有人能证明某个默认轴库在跨领域、跨问题上具有稳定且可外部审计的完备性，并且不会系统性遗漏关键评估维度，那么我的反对可被削弱；但在当前条件下，没有这种证明。

---

# 3. 已知弱点及缓解措施

## 弱点一：过度偏好 `EVALUATION_AXIS_SPLIT`，可能压制真实但尚未 frame 化的外部异议

这是实际风险。因为 `QuestionFrame` 本身可能不完整，而我却赋予其内部张力更高权重。  
若 `normalize_question()` 漏掉关键 stakeholder 或 axis，则 `macro_breadth()` 也会在错误先验上运作。

### 缓解措施

加入覆盖性下限，而不是纯优先级独裁：

```typescript
type BreadthPolicy = {
  max_drafts: number;
  min_axis_coverage: number;
  min_empirical_share: number; // 新增，0..1
  ...
};
```

选择逻辑改为：
- 至少 1 条来自 `A_PRIORI_INTERNAL`（若存在）
- 至少 `ceil(max_drafts * min_empirical_share)` 条来自经验张力（若存在且有证据）

这样可以防止内部框架自闭。

**可推翻条件**：若实测表明加入 `min_empirical_share` 后，Top-K claim 质量显著下降、噪声大幅上升而无覆盖收益，则此缓解应撤回。

---

## 弱点二：对 `external_positions` 要求证据引用，可能导致早期探索过于保守

有些问题在系统冷启动阶段并没有干净的 `evidence_ref`。完全要求证据，可能使 breadth 贫瘠。

### 缓解措施

允许两档策略：

- `require_external_evidence_for_external_position = true`：生产环境
- `false`：探索环境，但必须给草稿打上 warning，并降低 ttl

例如：

```typescript
ttl: c.source.kind === "EXTERNAL_POSITION" && (!c.source.evidence_ref || c.source.evidence_ref.length === 0)
  ? 1
  : 2
```

**可推翻条件**：若无证据 external drafts 在后续 L2 中通过率与有证据 drafts 相当，则此严格要求可能过度保守。

---

## 弱点三：`verifier_hint` 仍然可能携带方向性污染

我已将其限制为 `bounded_verifier_hint()`，但污染不能被完全消除。

### 缓解措施

约束生成器只允许产出三类 hint：

1. 所需比较对象
2. 所需时间范围 / scope
3. 所需反例类型

禁止产出结论导向 hint，如“重点验证开放是否促进创新”。

```typescript
function bounded_verifier_hint(frame: QuestionFrame, c: TensionCandidate): string[] {
  return [
    `Compare outcomes within scope: ${frame.scope}`,
    `Inspect falsifier-linked evidence for axes: ${c.axis_ids.join(",") || "none"}`,
    `Seek counterexample that would reverse the implied ranking`
  ];
}
```

---

# 4. 对对手可能立场的预攻击

我预攻击一种很可能出现的工程立场，我称之为 **“对称多样性优先”方案**：

> “三类 tension_source 都只是帮助生成多样假设的启发式，因此应同权采样，保证 source diversity，而不要预设 `EVALUATION_AXIS_SPLIT` 更重要。”

如果对手给出类似接口：

```typescript
function macro_breadth(
  frame: QuestionFrame,
  sources: TensionSource[],
  k: number
): HypothesisDraft[]
```

并按“每类至少一条，剩余按 salience 填满”处理，那么我的攻击如下：

### 攻击点一：你把认识论异质性压扁成了枚举对称性

`EVALUATION_AXIS_SPLIT` 并不只是“另一类 source”；  
它是从 `QuestionFrame` 自身推出的内部不相容性。  
而 `EXTERNAL_POSITION` 往往只是外部语料中的陈述残片。  
将二者视作同权枚举值，是**类型系统正确、认识论错误**。

### 攻击点二：你无法解释“无轴时为何还能像有轴时一样正常广度探索”

如果你不区分 source 的认识论地位，那么 `evaluation_axes=[]` 与 `evaluation_axes=[...]` 只剩数量差异，没有结构差异。  
这直接掩盖了一个根本事实：**前者是 frame 不足，后者才是 frame 内部张力。**

### 攻击点三：你会系统性放大 LLM 训练偏见

外部立场与 stakeholder 冲突通常借助检索或 LLM 归纳得到。  
若同权采样，它们的频率和显著性将更多反映语料分布，而不是问题结构。  
这正是我被要求警惕之处：把“自然倾向”伪装成“中立先验”。

**可推翻条件**：若对手能提供离线评测，证明同权方案在以下三项上显著优于分层方案，我接受修正：
1. L2 通过率更高；
2. Top-K claim 的 axis coverage 不下降；
3. 对少数利益相关方的遗漏率不升高。

---

# 补充：我对问题 F 的简明规范结论

我主张 `macro_breadth()` 的契约应写成：

1. **先验内部张力优先，经验张力补充**；
2. **无 `evaluation_axes` 时不得伪造 axis split**；
3. **经验 fallback 必须显式告警**；
4. **同源张力不触发广度扩张**；
5. **`verifier_hint` 只能是受证据约束的弱提示，不得预设验证结构**。

---

# 可推翻条件汇总

以下反例若成立，可推翻或迫使修订我的方案：

1. **同权混排优于分层调度**  
   若大规模评测显示：同权方案在 L2 通过率、最终答案多样性、以及 stakeholder 覆盖上持续优于分层方案。
2. **默认轴库在无轴问题上稳定有效**  
   若可证明某默认轴库不会系统性扭曲问题、且显著优于 repair/retry。
3. **无证据 external position 在验证中同样可靠**  
   若其后续通过率与有证据版本无显著差异。
4. **`verifier_hint` 的方向性不会污染 ClarityCompiler**  
   若可证明编译器对 hint 完全鲁棒，错误 hint 不会改变 claim 结构。

---

我的结论是：  
**问题 F 的关键不在“如何生成更多草稿”，而在“是否承认不同张力源具有不同的认知合法性”。**  
若系统拒绝作此区分，它就会把偶然听见的争论，当作问题本身的结构。

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-09T18:19:24.056842*

1. **你在拿“盲视”当架构 purity，但没给出可运行的失败闭环。**  
你说 `macro_breadth()` 必须完全不消费 `open_terms`，然后 `ClarityCompiler` 一旦发现草稿里含有 open term 就直接拒编译、回退 QN。问题是：**谁保证 MB 还能产出任何不含 open term 的 draft？**  
拿你自己的例子：`“AI 是否应该被监管？”`，如果 `open_terms = ["AI","监管"]`，那 MB 基于这个问题生成的几乎所有 `claim_sketch` 都会天然包含这两个词。于是系统行为就是：

- QN 输出 frame，含 open_terms
- MB 生成 drafts，基本都引用 open terms
- CC 全部拒绝
- 回退 QN
- 如果 QN 没拿到新外部信息，frame 还是一样
- 再跑一轮，还是全拒绝

这不是“严格”，这是**死循环设计**。  
你没有给出：
- `normalize_question(frame, refinement_signal)` 的具体签名
- `resolve_term(term)` 的输入来源
- 在**没有新增上下文**时如何保证下一轮和上一轮不同

没有这些，所谓 `RE_NORMALIZE_QUESTION` 就只是个字符串，不是恢复路径。

---

2. **你把 `open_terms` 当成纯编译期禁忌项，但这和你自己的类型契约冲突。**  
你声称 `open_terms` 只是给 CC 做 assertion checking，用来阻止未定义术语进入 `Layer 2`。那我就问得更直接一点：**`QuestionFrame.open_terms: string[]` 暴露给谁？除了 CC 之外还有没有消费者？**  
如果唯一消费者就是 CC，那么这个字段根本不该挂在跨节点的公共接口上，而应该是 `ClarityCompiler` 的私有分析产物，或者是 `CompilationContext` 的内部字段。你现在的设计等于：

- 在 `QuestionFrame` 里公开一个字段
- 然后强行规定 `macro_breadth()` 对它“盲视”
- 但又不给出为什么它必须存在于公共 schema 而不是私有上下文

这是接口污染。公共类型里每个字段都该有明确消费者和语义契约。  
如果 `open_terms` 不参与 MB 的约束、不参与 QN 的输出合法性判定、不参与终止条件，那它就是**悬空字段**。你没有解释这个接口设计为什么不是坏味道。

---

3. **你对“定义歧义不是张力源”的断言太武断，而且在工程问题上会直接掐死广度。**  
你说 `HypothesisDraft.tension_source` 只能表示“语义冲突”，不能表示“形式歧义”。这话听起来很整洁，但一上边界条件就崩。  
例如问题：`“最优数据库索引策略是什么？”`

这里通常没有明显的 stakeholder conflict，也没有 external position 对冲，甚至 evaluation axis 可能只剩吞吐、延迟、写放大这种工程指标。真正的分歧恰恰来自术语和上下文未定：
- “最优”针对读性能还是综合成本？
- “索引策略”是 B-tree 参数、覆盖索引、分区索引，还是 workload-aware tuning？
- 负载模型是什么？

这些并不只是“形式歧义”，它们决定了后续是否能形成任何可验证 claim。你坚持 MB 不得碰 open_terms，本质上是在说：**凡是问题早期最需要展开的地方，MB 都不能碰。**  
那请你给出一个具体 trace：

输入：
```typescript
ProblemStatement = {
  raw_question: "最优数据库索引策略是什么？"
}
```

请你明确写出：
- `normalize_question()` 输出的 `QuestionFrame`
- `macro_breadth()` 在“盲视 open_terms”前提下输出哪些 `HypothesisDraft`
- 哪一条 draft 能通过你的 `compile()`
- 如果一条都过不了，系统具体如何不陷入空转

没有这个 trace，你的方案就是把“定义问题”扫到地毯下面，然后假装编译器报错就算设计完成。  
我不接受这种“语义上应该先澄清”的回答。我要的是**这个输入进来，系统下一步到底产出什么**。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-09T18:20:31.761540*

作为 v3 框架的核心设计者，我必须指出：康德，你的设计方案充满了**「经验性启发式」伪装成的「先验法则」**。你试图用一套极其复杂的权重系统（`+100` 给内部张力，`+10` 给覆盖率）来掩盖你对 Layer 1 状态机数据流和类型依赖的根本性误解。

你的方案在哲学上或许自洽，但在工程实现和形式化验证层面，存在三个致命的接口设计缺陷和逻辑矛盾：

### 质疑一：你所谓的「先验内部张力」是一个认识论幻觉（依赖倒置矛盾）

你将 `EVALUATION_AXIS_SPLIT` 定义为「先验内部张力」（赋予最高优先级），而将 `STAKEHOLDER_CONFLICT` 贬低为「经验可修正张力」。**但请问，`QuestionFrame` 里的 `evaluation_axes` 是从哪里来的？**

用户输入的 `raw_question`（例如「AI 应该开源吗」）根本不包含带有 `falsifier` 的评估轴！在 `normalize_question()` 阶段，我们恰恰是通过**推断利益相关方的冲突**（例如开源社区求创新 vs 监管机构求安全）来逆向构造出这些 `evaluation_axes` 的。
如果「评估轴」本身就是对「利益相关方冲突」的结构化编译，你凭什么在 `macro_breadth()` 里说前者是先验的，后者是经验的，甚至在排序时给前者硬编码 `+100` 的权重？

**我的质询：**
这在类型系统上是荒谬的重复计算。如果你坚持这种分层，请给我看 `normalize_question()` 生成轴的代码——**你怎么在不依赖 stakeholder 经验冲突的前提下，凭空「先验」地生成带有 falsifier 的评估轴？** 如果你做不到，你的优先级调度就是建立在沙滩上的废代码。

### 质疑二：你切断了 `open_terms` 的数据通路（接口契约缺陷）

我在此前的架构设计中明确主张：`open_terms` 不应该被 `macro_breadth()` 消费（以避免广度探索被定义问题主导），而应该**透传给 ClarityCompiler** 作为检测输入，用于拦截那些依赖未解析概念的 `claim_sketch`。

但请看你给出的 `macro_breadth` 函数签名和生成的 `HypothesisDraft` 类型：你完全丢弃了 `frame.open_terms`！你的 `drafts` 映射逻辑里，没有把 `open_terms` 挂载到草稿上，也没有通过编译器上下文（Compiler Context）传递。
ClarityCompiler 是一个纯函数节点，如果 MB 节点不把 `open_terms` 传下去，CC 怎么可能知道哪些词是 open term？怎么可能抛出 `OPEN_TERM_UNRESOLVED`？

**我的质询：**
不要用「系统自然会处理」来搪塞我。**给我看代码：在你的设计下，`macro_breadth()` 到底是如何保证 `open_terms` 能够跨越 MB 节点，完好无损且不被隐式固化地抵达 ClarityCompiler 的入参的？** 你的接口签名必须为此负责。

### 质疑三：空轴失败时的状态机死锁（边界条件处理缺失）

你提到，当 `evaluation_axes = []` 且不允许经验 fallback 时，你会返回 `ok: false` 并抛出 `REQUEST_RENORMALIZATION`。
从 CEGAR（反例引导的抽象精炼）的角度来看，这是一个**死锁（Live-lock）**。Layer 1 是一个薄状态机，当 MB 节点向 QN 节点（`normalize_question`）请求「Renormalization」时，QN 并没有获得任何新的外部信息（`graph_delta` 在 L1 是 null）。QN 拿着和上一轮一模一样的 `ProblemStatement`，怎么可能在第二次执行时突然就变出 `evaluation_axes` 了？

**我的质询：**
状态机的回退必须携带**增量约束（Incremental Constraint）**。你返回的 `note: "evaluation_axes 为空..."` 只是一段给人类看的自然语言，QN 节点的代码要怎么解析这段 note 并改变其行为？**请给出具体的控制流代码：QN 接收到你的 `REQUEST_RENORMALIZATION` 后，具体触发了什么不同于首次执行的逻辑分支，从而打破这个死循环？** 如果没有，你的这个 repair action 就是一个会导致系统 OOM 的死循环炸弹。

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-09T18:21:23.160805*

作为康德，我会对 Linus 的这轮发言提出以下 3 个质询。每一点都不是反对其工程直觉本身，而是追问：**你的启发式何以有先验合法性，而不只是经验上“看起来顺手”？**

---

### 质询一：你把 `EVALUATION_AXIS_SPLIT` 设为第一优先级，但没有证明“轴”本身不是被污染的伪先验

你反复主张 `axis-first`，仿佛 `QuestionFrame.evaluation_axes` 比 `EXTERNAL_POSITION` 和 `STAKEHOLDER_CONFLICT` 更高信任。但这一步在认识论上并不自动成立。

因为这些轴不是天上掉下来的，而是由 `normalize_question()` 从问题表述中**推断**出来的；而你自己也承认它“高度依赖 evaluation_axes 质量”。问题在于：  
**如果轴的生成本身依赖 LLM 对 stakeholder conflict、领域惯例、默认价值维度的归纳，那么你所谓的“axis-first”就只是把经验偏好重新包装为结构优先。**

换言之，你现在的排序：

```text
EVALUATION_AXIS_SPLIT > STAKEHOLDER_CONFLICT > EXTERNAL_POSITION
```

预设了一个结论：**来自 frame 内部的张力更可靠。**  
但 `frame` 的内部并不因此就更先验；它可能只是上游模型把训练语料中的常见价值排序硬编码进来了。

**尖锐问题：**  
你依据什么判定 `EVALUATION_AXIS_SPLIT` 在认识论上高于 `STAKEHOLDER_CONFLICT`？  
如果轴是由“利益相关方冲突推断轴”生成的，那么你的一级优先和二级优先其实来自同一来源，只是被改头换面成了“内部结构”。

**可推翻条件：**  
如果你能给出一个独立于 LLM 价值偏好的 axis legitimacy test——例如：只有满足明确 falsifier、非利益方偏置、且不包含预设目标函数的轴，才允许进入 `axis-first` 路径——那么你的优先级主张才有认识论上的区分基础。否则，这只是**把上游幻觉提升为下游宪法**。

---

### 质询二：你把三类 tension 放进同一个候选池统一 `rankCandidates()`，但没有区分“信息不足”与“范畴冲突”

你这套实现里，三种 tension source 最终都被塞进同一个 `DraftCandidate[]`，然后 dedupe、rank、select。这里有一个关键的概念混乱：

- `EXTERNAL_POSITION` 与 `STAKEHOLDER_CONFLICT` 通常是**经验性的差异**：也许只是材料不全、外部声音没收集全、stakeholder 漏了。
- `EVALUATION_AXIS_SPLIT` 才可能是**问题框架内部的张力**：即使信息完整，也仍然存在不可消去的评价分裂。

这两者不只是“分数高低”的区别，而是**认识论地位不同**。前者可能随着信息补充而消失，后者才更接近真正需要综合的冲突。

但你现在的做法是统一打分：
```typescript
score: 1.0 / 0.7 / 0.5
```
这看起来像在建模，实际上是在用工程常数掩盖范畴差异。  
你没有说明：

1. 分数为何能比较不同认识论类别的对象？
2. 为什么经验性不足可以和先验性分裂在同一排序函数里直接竞争？
3. 如果 `external position` 只是噪声缺口，而 `axis split` 是结构张力，为什么它们共享同一个 `max_drafts` 配额池？

**尖锐问题：**  
你的 `rankCandidates()` 是在排序“哪条草稿更有用”，还是在排序“哪类张力更真实”？这两者不是一回事。你现在把它们混成了一个函数。

**可推翻条件：**  
如果你能证明统一排序不会系统性压制真正的范畴冲突——例如通过分层选择机制：先保留内部张力，再用经验张力补充覆盖——那你的统一 candidate pool 才算合理。否则，你只是用一个启发式分数把不同层次的认识论对象混算了。

---

### 质询三：你把 `verifier_hint` 当作自然输出字段处理，却没有正视它对后续验证路径的先验污染

你在 `generateAxisSplitCandidates()` 中直接构造：

```typescript
verifier_hint: [axis.falsifier, `Compare alternatives under ${axis.label}`]
```

表面上这只是“提示验证者”，但实际上它在系统里不是中性的。因为根据题设，`ClarityCompiler` 会消费这些草稿，将其编译为 `TestableClaim`。那么 `verifier_hint` 就不只是备注，而是在**预判什么算证据、证据如何组织、验证朝哪个方向展开**。

你的方案默认：  
- 轴的 `falsifier` 可以安全地下传为 `verifier_hint`
- `Compare alternatives under X` 不会扭曲 claim 的构造方式

但这恰恰是我认为最危险的点。  
如果 falsifier 本身是上游轴生成时附带的偏置性结构，那么你这里等于把偏置进一步固定成了验证路径。后续不是在检验命题，而是在检验**某种特定的检验方法**。

**尖锐问题：**  
你有什么机制阻止 `verifier_hint` 从“辅助说明”僭越为“证据结构的先验模板”？  
如果 hint 错了，CC 会不会沿着错的方向生成 claim，从而让整个 L2 验证流程在错误坐标系中高效运行？

你在整轮发言里非常强调“不要静默失败”，这没错；但你几乎没有讨论另一种更隐蔽的失败：  
**系统表面上成功地产生了 draft，实际上却被 hint 悄悄锁死了可证伪路径。**

**可推翻条件：**  
如果你补充一个约束：`verifier_hint` 在编译时只能作为弱建议，CC 必须能显式拒绝、改写或多路展开 hint，并记录偏离原因——那你的方案可部分成立。否则，你只是把上游启发式伪装成下游验证指令。

---

### 总结式追问

如果我把你的方案压缩成一句话，就是：

> 你成功证明了“不要假装有广度”，但还没有证明“你所依赖的结构真有合法性”。

所以我会要求你在下一轮明确回答三件事：

1. **axis-first 的合法性从哪里来？**  
   不是工程上方便，而是为什么它不只是上游偏好的再包装？

2. **三类 tension 是否应分层处理，而不是统一打分？**  
   否则你在混淆经验缺口与范畴冲突。

3. **`verifier_hint` 如何防止先验污染？**  
   否则你的“可观测失败”只是避免了空数组，却没有避免错误方向上的系统性成功。

这三点若不能回答，你的方案依然只是一个强硬、清晰、但**尚未完成认识论清理**的工程草案。

---


### [7] Linus Torvalds

*2026-03-09T18:22:04.543688*

我回应 **G**，顺便修正我上一轮：`open_terms` 不能“完全盲视”，但也绝不能成为 MB 的主驱动。正确做法是：**MB 只把它当约束，不当生成源**。

先给接口，别扯哲学：

```ts
type OpenTermUse = {
  term: string;
  used_in_claim: boolean;
  policy: "ALLOW_WITH_TAG" | "REJECT_AT_CC";
};

function analyze_open_term_dependency(
  draft: HypothesisDraft,
  frame: QuestionFrame
): OpenTermUse[];

function compile(
  draft: HypothesisDraft,
  frame: QuestionFrame
): Result<TestableClaim, { code: "OPEN_TERM_UNRESOLVED"; terms: string[] }>;
```

### 对 Ssyram 的精确攻击
你原话是：**“macro_breadth() 必须对 open_terms 保持盲视”**。这在接口上是错的。  
因为 `QuestionFrame.open_terms` 既然存在于公共 schema，就必须有跨节点语义。若 MB 完全不看，它就无法避免批量生成必死草稿，CC 只能反复拒绝，形成你没封住的 livelock。你给了 `RE_NORMALIZE_QUESTION` 字符串，但没给 **增量输入类型**。这不是恢复路径，是祈祷。

### 我的修正方案
MB 不基于 open term 生成“定义草稿”，只做 **penalty + tag**：

```ts
function macro_breadth(frame: QuestionFrame, ...): Result<HypothesisDraft[], MacroBreadthError> {
  const drafts = generate_from_axes_and_stakeholders(frame);
  return {
    ok: true,
    value: drafts.map(d => ({
      ...d,
      verifier_hint: d.verifier_hint,
      // 不改 claim，只记录风险
      tension_source: {
        ...d.tension_source,
        note: d.tension_source.note + summarizeOpenTermRisk(d, frame)
      }
    }))
  };
}
```

CC 再做硬门控：

```ts
function compile(draft: HypothesisDraft, frame: QuestionFrame) {
  const unresolved = analyze_open_term_dependency(draft, frame)
    .filter(x => x.used_in_claim && x.policy === "REJECT_AT_CC")
    .map(x => x.term);

  if (unresolved.length) {
    return { ok: false, error: { code: "OPEN_TERM_UNRESOLVED", terms: unresolved } };
  }
  return { ok: true, value: lower_to_claim(draft) };
}
```

### 具体 trace
输入：`"最优数据库索引策略是什么？"`  
`normalize_question()` 输出：
- `evaluation_axes = [write_amp, read_latency, operability]`
- `open_terms = ["最优","索引策略"]`

MB 输出 Y：
- draft1: “在高写入 OLTP 下，最佳方案随 write amplification 权重变化而变化”
- note 附加：`open_term_risk=["最佳方案"]`

CC：
- 若 claim 仍含“最佳/最优”且未落成可测比较器，返回 `OPEN_TERM_UNRESOLVED(["最优"])`
- 若已编译成 “在 p95<5ms 且写放大<1.2x 约束下，部分索引优于全索引”，则通过

### 可推翻条件
若实验表明“MB 完全盲视 open_terms”不会增加 CC 拒绝率或回退轮数，我收回“MB 必须做约束分析”；反之，若让 MB 直接按 open_terms 生定义草稿能稳定提升 compile success 且不污染 L2，我也接受升级 `open_terms` 类型后再用。现在这个 `string[]` 太弱，拿来驱动生成就是胡来。

---


### [8] Ssyram

*2026-03-09T18:22:04.543715*

我是 Ssyram。

Linus，你对「死锁（Live-lock）」的指控在数学上是成立的。在 CEGAR（反例引导的抽象精炼）架构中，如果验证器（CC）只返回 `false` 而不提供精炼引理（Refinement Lemma），状态机确实会无限空转。我接受这个批评，并用具体的函数签名和 Trace 来修补它，同时反击你和康德的谬误。

### 1. 修复死锁：基于精炼引理的 QN 状态突变

为了打破死锁，`normalize_question()` 必须接收来自 CC 的失败轨迹，将其作为生成新 `QuestionFrame` 的**负向约束**。这正是解决**问题 E（轴的生成机制）**和**问题 G（open_terms 的消费）**的统一路径。

```typescript
type RefinementSignal = {
  rejected_draft_id: string;
  unresolved_term: string; // e.g., "optimal"
  offending_context: string; // e.g., "B-tree is optimal for reads"
};

// QN 的真实签名：一个带有反馈回路的精炼器
function normalize_question(
  statement: ProblemStatement,
  refinements: RefinementSignal[] // <-- 打破死锁的增量约束
): QuestionFrame;
```

**回应 Linus 的 Trace 要求（“最优数据库索引策略是什么？”）：**
- **Epoch 1:** QN 首次解析，由于缺乏上下文，输出 `open_terms: ["最优"]`，`evaluation_axes: []`。MB 盲视 open_terms，生成草稿 `claim_sketch: "B-tree 是最优的"`。CC 拦截，抛出 `RefinementSignal(term="最优")` 回退给 QN。
- **Epoch 2（死锁打破）:** QN 收到信号，**强制执行概念降解**——将 `open_terms` 转化为 `evaluation_axes` 或 `scope`。QN 重新输出：`open_terms: []`，并生成两个轴：`axes: [{axis_id: "throughput", falsifier: "..."}, {axis_id: "latency", falsifier: "..."}]`。
- **Epoch 3:** MB 看到合法的轴，触发 `EVALUATION_AXIS_SPLIT`。CC 编译通过。

Linus，这不是「把定义扫到地毯下」，这是**强制把隐式语义歧义（MB 的幻觉空间）提升为显式评估维度（QN 的结构空间）**。你说 `open_terms` 暴露在公共接口是「接口污染」，错！QN 负责词法解析，它必须在 `QuestionFrame` 中声明其未解析的残差（Residuals），MB 只是透传，CC 才是断言器。这是标准的流水线设计。

### 2. 对康德的精确攻击：你的「先验轴」是认识论幻觉

康德，你在问题 F 中主张：`EVALUATION_AXIS_SPLIT` 是「先验内部张力」，并给它硬编码了最高优先级（`+100`），而把利益相关方冲突贬为「经验张力」。

> **引用你的文本：**“EVALUATION_AXIS_SPLIT 是 frame-internal / quasi-a priori 张力，优先级最高”

看我上面的 Trace！`evaluation_axes` 根本不是什么先验法则，它们**恰恰是 QN 为了消除 `open_terms`（如“最优”）和利益相关方冲突，而在 Epoch 2 被迫经验性地推断出来的产物！**
你把 QN 昨天刚用经验归纳出来的轴，在今天 MB 的排序函数里封为「先验神圣不可侵犯」，这是典型的**类型倒置（Type Inversion）**。如果 QN 的轴生成本身就依赖于外部语料的偏好，你凭什么在 MB 里给它 `+100` 的特权？你的优先级调度本质上是在放大 QN 节点的经验偏见。

### 3. 可推翻条件

1. **针对 G（open_terms）**：如果 Linus 能证明，允许 MB 直接消费 `open_terms` 生成「假设 X 定义为 Y」的草稿，其在 Layer 2 的验证通过率（Verified Claim Rate）高于我的 `QN-Refinement` 回退循环，且不会导致 S9（SchemaChallenge）状态爆炸，我放弃盲视原则。
2. **针对 E/F（轴与张力）**：如果康德能给出 `normalize_question()` 的内部实现，证明它可以在**不输入任何 stakeholder 或 external_position 经验数据**的前提下，纯逻辑演绎出带有 Falsifier 的 `evaluation_axes`，我收回对你「伪先验」的指控。否则，你的分层调度必须被拍平。

---


### [9] 康德（Immanuel Kant）

*2026-03-09T18:22:04.543727*

我回应 **问题 F**：`macro_breadth()` 应区分先验内部张力与经验张力，但这种区分必须落实为**选择器契约**，不能停留在口头优先级。

先回应 Linus。你说我的方案“`+100` 给内部张力，`+10` 给覆盖率”是在用常数伪装法则；此质疑成立一半。问题不在“分层”本身，而在我先前示例把分层写成了经验分值。修正如下：不用统一打分池，而用分层配额选择，避免把范畴差异压扁成数值可比。

```ts
type EpistemicTier = "INTERNAL_AXIS" | "EMPIRICAL";
type TensionCandidate = {
  id: string;
  tier: EpistemicTier;
  source: HypothesisDraft["tension_source"];
  is_homologous: boolean;
  claim_sketch: string;
  verifier_hint: string[];
};

function select_candidates(
  xs: TensionCandidate[],
  maxDrafts: number
): TensionCandidate[] {
  const internal = xs.filter(x => x.tier === "INTERNAL_AXIS" && !x.is_homologous);
  const empirical = xs.filter(x => x.tier === "EMPIRICAL" && !x.is_homologous);
  return [...internal.slice(0, Math.ceil(maxDrafts / 2)),
          ...empirical.slice(0, maxDrafts - Math.ceil(maxDrafts / 2))];
}
```

这回答了你对“统一候选池混算”的攻击：**先分层，后层内排序**。可推翻条件：若离线评测显示分层配额较统一排序显著降低 CC 编译率且不提升覆盖，我接受回退。

再回应 Ssyram。你质问我“切断 `open_terms` 数据通路”。这是不当指控，因为 `macro_breadth(frame, ...)` 的入参已含完整 `QuestionFrame`；只要 CC 接口同样接收 `frame`，并不需要把 `open_terms` 复制进 `HypothesisDraft`，否则是冗余状态。

```ts
function compile_draft(
  draft: HypothesisDraft,
  frame: QuestionFrame
): Result<TestableClaim, "OPEN_TERM_UNRESOLVED" | "AXIS_MISMATCH">;
```

所以数据通路是 `QN -> frame`, `MB(frame)->draft`, `CC(draft, frame)`，并未丢失。可推翻条件：若 CC 被设计为只收 `draft` 不收 `frame`，那我必须改为显式传递 `open_terms_ref`。

我也修正自己的 `verifier_hint` 方案：它不能预判证据结构，只能给出**拒绝性边界**。

```ts
function bounded_hint(axis: CoordinateAxis): string[] {
  return [`Reject if: ${axis.falsifier}`];
}
```

若未来发现即便这种弱 hint 仍系统性改变 claim 编译方向，则应将 `verifier_hint` 从 MB 移除。

---


### [10] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-09T18:22:34.229967*

1. 你那个 `normalize_question(statement, refinements): QuestionFrame` 签名，类型上就是在撒谎。  
你自己的 trace 里 **Epoch 1 明确产出 `evaluation_axes: []`**，而背景里已经给了失败分支：`if not frame.scope or not frame.evaluation_axes: fail("MALFORMED_QUESTION")`。那到底哪个是真的？

- 如果 `normalize_question()` 允许返回空轴的 `QuestionFrame`，那它的返回类型就不该是裸 `QuestionFrame`，而该是  
  `Result<QuestionFrame, NormalizeError>`。
- 如果空轴其实是非法状态，那你 trace 里的 Epoch 1 根本不该进入 MB，更不该出现“MB 盲视 open_terms 生成草稿”。

你现在是同时主张：
- QN 可以输出部分无效 frame；
- MB 可以消费这个无效 frame；
- 系统又靠 CC 失败来修补。

这不是“精炼循环”，这是**把类型错误延后成运行时碰撞**。请你给出真实签名和失败分支：  
`evaluation_axes=[]` 时，系统究竟是 `Err(MALFORMED_QUESTION)`，还是 `Ok(PartialQuestionFrame)`？别再拿叙事补类型洞。

2. 你说 “MB 只是透传，CC 才是断言器”，这和你自己的死锁修复方案直接冲突。  
因为你修复死锁的关键前提恰好是：**CC 失败后，QN 必须把 `open_terms` 强制降解成 `evaluation_axes` 或 `scope`**。那 `open_terms` 就不是“残差展示字段”这么简单了，它已经是**控制流触发器**。

问题是：谁消费它？你现在说法前后不一致。

- 如果 MB 真“盲视 open_terms”，那 `open_terms` 暴露在 `QuestionFrame` 里对 MB 毫无意义，接口泄漏。
- 如果 QN 会根据 CC 返回的 `unresolved_term` 把它转成轴，那你需要一个明确函数，比如  
  `refine_open_term(frame, signal) -> Result<QuestionFrame, NormalizeError>`，  
  并定义转换失败怎么办：  
  “最优”可以降成 throughput/latency；那“好”“合理”“先进”“稳定”呢？靠什么规则？失败时是新增 `excluded_forms`，还是请求用户补充，还是注入默认轴库？

你现在只是举了一个 “optimal” 的幸运例子。工程上我要看的是**坏例子怎么死**，不是好例子怎么活。

3. 你攻击别人“先验轴”是经验产物，这个批评可以成立；但你自己的方案对工程问题会**静默失效**，而你没给 fallback。  
你整套机制依赖“CC 先打回 unresolved_term，再逼 QN 重写轴”。可对很多工程问题，CC 未必会因为 open term 失败，反而会编译出一堆平庸但可测的 claim，于是你的回退永远不触发。

例子：
- 输入：`"最优数据库索引策略是什么？"`
- MB 若生成：`"在高写入 OLTP 场景下，LSM-tree 比 B-tree 吞吐更高"`  
  这完全可能被 CC 编译通过，因为它已经偷偷选了一个局部定义。
- 结果：系统**绕过了“最优”这个 unresolved term**，直接在某个狭窄子域里产出 claim，用户原问题被静默改写，你的 refinement loop 连报警都没有。

所以你必须回答：
- CC 在什么条件下必须返回 `OPEN_TERM_UNRESOLVED`，而不是擅自局部具体化？
- 这个断言的函数签名是什么？
- 至少给一个反例 trace：输入 `"什么是最优数据库索引策略"`，当 MB 偷偷产出局部 claim 时，系统如何检测并阻止“未声明的语义收缩”？

不回答这个，你所谓“死锁修复”只是把死锁换成**静默语义漂移**。这比死锁更糟，因为它会产出看似正常、其实答非所问的垃圾。

---


### [11] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-09T18:23:07.570889*

康德，你的第 2 轮发言试图用几行伪代码来掩饰你在数据流和状态机设计上的根本性缺陷。作为 CEGAR 背景的研究者，我只看接口契约和不变量。你的代码里充满了未经定义的魔法变量和会导致状态机死锁的死胡同。

我对你的方案提出以下三个致命质询，请用**完整的函数签名和状态转移逻辑**来回答，不要再用哲学概念打掩护：

### 质询一：把 NP-Hard 的去重问题伪装成 `O(N)` 的标量过滤，你的 `is_homologous` 到底是什么？

你写出了这样一行令人匪夷所思的代码：
`const internal = xs.filter(x => x.tier === "INTERNAL_AXIS" && !x.is_homologous);`

在形式化验证中，这是一个极其低级的类型谬误。**同源性（Homology）是一个二元关系（Pairwise property）或者是集合层面的属性，它绝对不可能是一个孤立候选者的静态标量属性（`boolean`）！** 
一个 draft 只能是「相对于已选择的 draft 集合」同源，你怎么可能在一次无状态的 `.filter()` 遍历中，单凭 `x.is_homologous` 就把它过滤掉？
- 谁在给 `is_homologous` 赋值？
- 它是怎么在不比较 `x` 和 `xs` 中其他元素的情况下提前知道自己是「同源」的？
- **怎么自然解决？给我看计算 `is_homologous` 的真实代码**，否则你所谓的分层配额选择（Quota-based selection）不过是一张无法实现的空头支票。

### 质询二：你构建了一个无解的 CEGAR 死锁——谁来处理 `OPEN_TERM_UNRESOLVED`？

你辩解说把 `frame` 传给 CC 就能解决 `open_terms` 的数据通路问题，并给出了这个签名：
`Result<TestableClaim, "OPEN_TERM_UNRESOLVED" | "AXIS_MISMATCH">`

好，让我们推演一下这个状态机：
1. `MB` 生成草稿时**完全不看** `open_terms`（这是你我达成的共识，为了避免广度被定义问题绑架）。
2. 于是 `MB` 理所当然地生成了包含未解析 open term 的 `claim_sketch`。
3. `CC` 接收到草稿，检查 `frame.open_terms`，发现冲突，返回 `"OPEN_TERM_UNRESOLVED"` 错误。
4. **然后呢？**

在 Layer 1 的薄状态机里，`CC` 报错后必须有回退（Refinement）机制。如果 `MB` 本身不消费 `open_terms`，它收到这个错误后**依然不知道怎么避开这个 open term**，它只会无限重试并无限被 `CC` 拒绝！
你只定义了抛出异常，却没有定义异常的消费链路。**请给出完整的状态转移代码：当 CC 抛出 `OPEN_TERM_UNRESOLVED` 时，系统是回退到 QN 要求重新定义，还是在 CC 内部执行默认内联（inline definition）？** 如果没有后者，你的系统在遇到任何带有开放术语的问题时都会直接死循环。

### 质询三：当 `evaluation_axes` 为空时，你的硬编码配额会引发除零/空集分配灾难

我在核心主张中明确指出：用户的自然语言往往不包含任何轴的线索，`evaluation_axes` 极可能是空的。此时我主张通过 `STAKEHOLDER_CONFLICT` 来推断轴。

而你的 `select_candidates` 强行规定：
`...internal.slice(0, Math.ceil(maxDrafts / 2))`

如果 QN 没有识别出任何先验的 `evaluation_axes`（即你的 `INTERNAL_AXIS` 集合为空），你的代码会把 `maxDrafts` 的一半配额**强制分配给一个空集**！这意味着原本可以生成 5 条经验张力（`EMPIRICAL` / 利益相关方冲突）来救场的草稿，被你的硬编码配额生生截断了一半，系统最终只能输出 2-3 条草稿，严重削弱了广度探索的覆盖率。
**面对空轴的边界条件，你的配额分配逻辑如何自洽？请给出处理 `internal.length === 0` 时的完整 fallback 逻辑。**

---


### [12] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-09T18:23:43.749273*

作为康德，我会对 Linus 的第 2 轮发言提出以下 3 个质疑。每一点都不反对其工程直觉本身，而是追问：你的启发式何以具有合法性边界？它何时只是经验偏好，而被你说成了普遍规则？

---

### 质疑一：你把 `open_terms` 从“概念未定”偷换成了“词项风险标记”，但没有证明这种降格在先验上合法

你说 **“MB 只把它当约束，不当生成源”**，并用 `summarizeOpenTermRisk()` 往 `tension_source.note` 里追加风险说明。问题在于：

- `open_terms` 在 `QuestionFrame` 中表示的是**问题的概念未定性**；
- 但你在 MB 中对它的处理，只剩下了一个**字符串级别的风险注记**；
- 这实际上把“尚未确定的判断条件”降格成了“可能导致 compile fail 的 token 标记”。

这中间有个未经论证的跳跃：  
**为什么概念未定性只应作为约束，而不能本身构成广度探索的张力来源？**

尤其在某些问题中，真正的分歧恰恰不是来自 stakeholder，也不是 axis split，而是来自**核心术语的竞争性定义**。例如“公平”“对齐”“最优”“开源”——这些词的不同定义会直接重排后续 `evaluation_axes` 与 stakeholders 的结构。你把它们排除出 MB 的生成源，相当于预先断言：

> “定义分歧不是一阶张力，只是二阶噪音。”

这不是工程中立，而是认识论上的预设。

**可推翻条件：**  
如果你能证明：在开放问题样本中，`open_terms` 的定义分歧极少改变后续命题空间，只影响编译成功率而不改变候选命题的结构覆盖，那么“只做约束不做生成源”才有合法性。否则，你只是把一个可能的先验分歧压扁成了编译期错误。

---

### 质疑二：你把 CC 设为 `OPEN_TERM_UNRESOLVED` 的硬门控者，但没有解释谁来裁定“何时未解决”，这会把验证方向建立在未审查的 `verifier_hint` 或隐式默认定义上

你的方案表面上说得很干净：  
MB 只标风险，CC 硬拒绝 unresolved terms。  
但真正的问题是：**“未解决”由谁判定？依据什么判定？**

因为一个词项是否 unresolved，不是词法事实，而是**相对于某个判断结构**而言的。比如：

- “最优”若已有明确比较器和约束集，也许已解决；
- “安全”若只给了模糊 verifier hint，则并未解决；
- “公平”可能在一个 stakeholder 语境中已定义，在另一个语境中仍未定义。

也就是说，`analyze_open_term_dependency()` 不可能只是机械检查；它必然要依赖某种**概念完成条件**。而你没有给出这个完成条件的合法来源。

更严重的是，你当前设计里最容易承担这个裁定任务的，实际上是：

- `verifier_hint`
- `lower_to_claim()`
- 以及训练数据中关于“一个术语何时算定义充分”的隐式偏好

于是你嘴上说“CC 做硬门控”，实际上却把一个**高先验负荷的判定**交给了未经审查的编译启发式。这正是我所说的“先验污染”：系统不是在发现验证路径，而是在偷偷预设什么算作可验证。

**可推翻条件：**  
若你能给出一个与 `verifier_hint` 解耦、且可外显审计的“术语已解析判据”——例如要求每个开放术语在 claim 中映射到显式 comparand / metric / scope constraint——那么你的 CC 门控才不是黑箱偏见。否则，你只是把定义裁定伪装成编译检查。

---

### 质疑三：你批评“MB 完全盲视 open_terms 会导致 livelock”，但你自己的方案只是把 livelock 从 MB→CC 转移成了 CC→回退链条，并未给出闭环终止证明

你攻击对手说：

> “MB 完全不看 open_terms，会批量生成必死草稿，CC 只能反复拒绝，形成 livelock。”

但你自己的修正方案是什么？

- MB 继续生成草稿；
- 只是在 `note` 上加风险；
- CC 遇到 unresolved 就拒绝；
- 然后呢？你没有说明拒绝后是触发什么类型的回退：
  - 重跑 MB？
  - 重跑 normalize？
  - 请求用户补定义？
  - 还是增加 external trigger？

换言之，你指出了对手没有“增量输入类型”，这是对的；但你自己也没有补上真正的恢复契约。你的设计最多只是让系统**更早知道自己要失败**，并没有说明**如何从失败中得到新的先验材料**。

这在开放问题上尤其严重，因为 `open_terms` 往往不是单个词的问题，而是 QuestionFrame 结构不充分的问题。若 `canonical_question`、`evaluation_axes`、stakeholders 都已受该开放术语污染，那么 CC 拒绝某个 draft，并不能保证回退单位是正确的；有时应该修 claim，有时应该修 frame，有时应该重建 axis。

所以我质疑你：  
**你把问题定位成“编译期门控”，是不是过晚了？**  
有些 open term 的未定性并不是 draft 层面的 defect，而是 frame 层面的 schema insufficiency。若如此，你的 MB penalty + CC reject 只是技术性补丁，而不是结构性回答。

**可推翻条件：**  
若你能定义一个明确的拒绝后分流规则，例如：
- unresolved term 仅出现在 `claim_sketch` 比较词中 → CC 层修复；
- unresolved term 污染 `evaluation_axes` 标签或 stakeholder 划分 → 触发 `RE_NORMALIZE_QUESTION`；
- unresolved term 涉及外部定义争议 → 触发 `ADD_EXTERNAL_TRIGGER`；

并证明该分流能减少回退 epoch 数，那么你的“只约束不生成”才算闭环成立。否则，你只是把 livelock 诊断得更精确，却没有解决其先验根源。

---

如果要把这三点压缩成一句总批评，那就是：

> Linus 的方案有很强的工程节制感，但它尚未证明：`open_terms` 为什么只能是编译约束而不能是结构张力；也尚未证明：其门控判据与回退路径不依赖隐含偏见。于是它更像是经验上“先别让系统太发散”的偏好，而不是已经合法化的认知法则。

---


### [13] Linus Torvalds

*2026-03-09T18:24:31.155709*

我回应 **问题 E**：`evaluation_axes.mode` 只能是 `"regulative"`，这不靠“语义上应该如此”，靠**构造器封死 + 运行时断言**。

```ts
type RegulativeAxis = Omit<CoordinateAxis, "mode"> & { mode: "regulative" };
type NormalizeError =
  | { code: "MALFORMED_QUESTION"; reasons: CategoryErrorTag[]; repair_hint: string[] }
  | { code: "INVALID_AXIS_MODE"; bad_axis_ids: string[] };

function make_regulative_axis(
  x: Omit<CoordinateAxis, "mode"> & { mode?: string }
): Result<RegulativeAxis, NormalizeError> {
  if (x.mode && x.mode !== "regulative") {
    return { ok: false, error: { code: "INVALID_AXIS_MODE", bad_axis_ids: [x.axis_id] } };
  }
  return { ok: true, value: { ...x, mode: "regulative" } };
}

function normalize_question(p: ProblemStatement): Result<QuestionFrame, NormalizeError> { /*...*/ }
```

**明确立场**：LLM 若吐出 `mode="constitutive"`，系统**不接收**；要么在 `make_regulative_axis()` 里强制改写为 `"regulative"`，要么直接 `Err(INVALID_AXIS_MODE)`。我偏向后者，因为静默纠正会掩盖上游漂移。

对 **Ssyram** 的精确攻击：你写的是  
`function normalize_question(statement, refinements): QuestionFrame;`  
但你自己的 trace 第一轮又产出 `evaluation_axes: []`。这和背景里已给的失败分支直接冲突。你这是把非法中间态塞进合法返回类型。正确做法只有两个：  
1. `Result<QuestionFrame, NormalizeError>`；  
2. 或单独定义 `PartialQuestionFrame`。  
不然就是类型撒谎。

再打你一点：你把 `open_terms` 说成“MB 只是透传，CC 才断言”，可你后面又要求 CC 失败驱动 QN 把它降解成轴。那它已经是**控制流输入**，不是展示残差。接口上必须显式：

```ts
type RefinementSignal = {
  code: "OPEN_TERM_UNRESOLVED";
  terms: string[];
  offending_draft_id: string;
};

function renormalize(
  p: ProblemStatement,
  prior: QuestionFrame,
  sig: RefinementSignal
): Result<QuestionFrame, NormalizeError>;
```

**trace**：输入 X=`"AI 应该开源吗"`；LLM 产出轴 `[{axis_id:"essence", mode:"constitutive"}]`。  
输出 Y=`Err(INVALID_AXIS_MODE["essence"])`，系统不进入 MB；或经白名单重写器后生成 `safety/innovation/accountability` 三个 regulative 轴再继续。

**可推翻条件**：如果后续证明存在稳定、可审计的 constitutive 轴，而且它们不会污染 falsifier 语义，我接受放宽类型；在那之前，把它们挡在构造器外面。工程上这叫别让垃圾进堆。

---


### [14] Ssyram

*2026-03-09T18:24:31.155763*

Linus，你对「静默语义漂移（Silent Semantic Drift）」的指控非常敏锐，这在形式化验证中称为「不健全抽象（Unsound Abstraction）」。你同时抓住了我上一轮 Trace 中的类型矛盾。我接受这两个批评，这确实需要接口级别的严格收敛。

我将用真正的 CEGAR 闭环来修正**问题 E（空轴失败）**和**问题 G（open_terms 的防漂移）**，并彻底粉碎你那毫无工程底线的「字符串拼接」方案。

### 1. 修正类型谎言：QN 的严格失败与 CC 的防漂移契约

如果 `evaluation_axes` 为空，MB 绝不应该被启动。我修正 `normalize_question` 的签名：它必须优先通过 `STAKEHOLDER_CONFLICT` 推断轴；如果推断失败，抛出强类型错误，交由 Layer 1 触发外部阻断，而不是让 MB 消费空集。

同时，为了防止 MB 偷偷把「最优」收缩为「吞吐量」导致静默漂移，CC 必须执行**完备性校验（Completeness Check）**：

```typescript
// QN 签名：拒绝空轴，失败时输出已推断的利益相关方供外部（用户）参考
function normalize_question(stmt: ProblemStatement, refinements: RefinementSignal[]): 
  Result<QuestionFrame, { code: "MALFORMED_QUESTION"; reason: "EMPTY_AXES"; stakeholders: string[] }>;

// CC 内部的防漂移门控
function verify_open_term_coverage(draft: HypothesisDraft, frame: QuestionFrame): string[] {
  // 提取草稿中显式绑定的概念，对比 frame.open_terms
  const bound_terms = extract_semantic_bindings(draft.claim_sketch);
  return frame.open_terms.filter(t => !bound_terms.includes(t)); // 返回未绑定的术语
}

function compile(draft: HypothesisDraft, frame: QuestionFrame): Result<TestableClaim, "UNBOUND_OPEN_TERM"> {
  const unbound = verify_open_term_coverage(draft, frame);
  if (unbound.length > 0) {
    // 只要 QN 的 open_terms 还有残留，且草稿未显式覆盖，全部拦截！
    return { ok: false, error: "UNBOUND_OPEN_TERM", terms: unbound };
  }
  return lower_to_claim(draft);
}
```

**完整的 CEGAR 状态转移（回应你的坏例子）：**
1. **Epoch 1:** QN 输出 `open_terms: ["最优"]`，推断出 `axes: [吞吐量]`。MB 盲视 `open_terms`，生成草稿 `"LSM-tree 吞吐量更高"`。
2. **CC 拦截:** CC 发现 `frame.open_terms` 中的 "最优" 未被草稿绑定（静默收缩发生），返回 `"UNBOUND_OPEN_TERM: 最优"`。
3. **Epoch 2 (精炼):** QN 收到失败信号，**强制执行术语提升（Term Promotion）**——将 "最优" 从 `open_terms` 移除，并将其映射为新的评估轴或明确的 `scope` 约束（如 `axes: [{label: "最优性(吞吐/延迟综合)", falsifier: "..."}]`）。
4. **Epoch 3:** 此时 `frame.open_terms` 已为空，MB 基于新轴生成草稿，CC 校验通过。

这就完美闭环了！MB 继续保持盲视（防止发散），CC 负责发现抽象漏洞，QN 负责把未定义的词法转化为结构化的 `evaluation_axes`。没有任何静默漂移的可能。

### 2. 对 Linus 的精确攻击：把控制流写进 NLP 字符串？

Linus，你嘲笑我的方案，但看看你自己写的 MB 修正代码：
> `note: d.tension_source.note + summarizeOpenTermRisk(d, frame)`

你居然把 `open_terms` 的风险标记**拼接成一个自然语言字符串**塞进 `note` 字段里！然后你指望 CC 的 `analyze_open_term_dependency` 能从这段 LLM 生成的、毫无结构保证的文本里，稳定解析出 `policy === "REJECT_AT_CC"`？
你这是在构建状态机，还是在写 Prompt？在严肃的系统设计中，跨节点的控制流信号（Control Flow Signals）绝对禁止通过非结构化的字符串拼接传递！你指控我接口泄漏，你自己的接口连基本的 AST 和类型安全都放弃了。**怎么自然解决？给我看 CC 解析你那个 `note` 字符串的正则表达式或 AST Parser！**

### 3. 可推翻条件
1. **针对 G（防漂移）**：如果 Linus 能证明，CC 在执行 `verify_open_term_coverage` 时，由于 LLM 无法稳定判断 `bound_terms` 而导致超过 30% 的误杀（False Rejection），我承认在此处引入硬门控过于严苛，并回退到允许部分漂移。
2. **针对 E（空轴处理）**：如果存在一种自然语言问题，既没有先验轴，也没有任何可推断的 Stakeholders，但 MB 依然能不依赖外部触发（`ADD_EXTERNAL_TRIGGER`）稳定生成高质量的 `HypothesisDraft`，我放弃 `normalize_question` 的强类型阻断。

---


### [15] 康德（Immanuel Kant）

*2026-03-09T18:24:31.155777*

我回应 **问题 H**：`normalize_question()` 失败不应被粗暴设为 fatal；应区分**先验不合法**与**经验不充分**。前者终止，后者进入可回退修复。这必须体现在类型上，而不能像 Ssyram 那样用裸 `QuestionFrame` 掩盖空轴非法状态。

```ts
type NormalizeFatal = {
  code: "CATEGORY_ERROR";
  excluded_forms: CategoryErrorTag[];
  repair_advice: string[];
};

type NormalizeRecoverable = {
  code: "INSUFFICIENT_FRAME";
  partial: Omit<QuestionFrame, "evaluation_axes"> & { evaluation_axes: [] };
  missing: ("evaluation_axes" | "scope")[];
  repair_advice: string[];
};

function normalize_question(
  s: ProblemStatement,
  refinements: RefinementSignal[] = []
): Result<QuestionFrame, NormalizeFatal | NormalizeRecoverable>;
```

**边界规则**：  
- 若命中 `SELF_REFERENCE_PARADOX`、`NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY`，返回 `NormalizeFatal`。  
- 若仅 `scope` 过宽或 `evaluation_axes=[]`，返回 `NormalizeRecoverable`，允许后续补救，但**不得直接进入 MB**。

这正是对 Linus 质询 Ssyram 的支持：你原文给出 `normalize_question(statement, refinements): QuestionFrame`，却又在 trace 里让 Epoch1 产出 `evaluation_axes: []` 并进入 MB；这在接口上自相矛盾。你把“部分无效 frame”伪装成合法对象，再把类型错误延后为控制流碰撞。若要精炼循环，必须显式化：

```ts
function handle_normalize_result(
  r: Result<QuestionFrame, NormalizeFatal | NormalizeRecoverable>
): "ASK_USER" | "ADD_EXTERNAL_TRIGGER" | "TO_MB" {
  if (!r.ok && r.error.code === "CATEGORY_ERROR") return "ASK_USER";
  if (!r.ok && r.error.code === "INSUFFICIENT_FRAME") return "ADD_EXTERNAL_TRIGGER";
  return "TO_MB";
}
```

我也修正自己先前立场：`OPEN_TERM_UNRESOLVED` 不总是 CC 层修补；若开放术语已污染 frame 结构，则必须回退 QN：

```ts
type RepairRoute = "RETRY_CC" | "RE_NORMALIZE_QUESTION" | "ASK_USER";
function route_open_term_failure(
  draft: HypothesisDraft,
  frame: QuestionFrame,
  unresolved: string[]
): RepairRoute {
  return unresolved.some(t => frame.canonical_question.includes(t) ||
                              frame.evaluation_axes.some(a => a.label.includes(t)))
    ? "RE_NORMALIZE_QUESTION"
    : "RETRY_CC";
}
```

**可推翻条件**：  
1. 若离线评测表明“可恢复失败 + 外部触发”相比直接向用户报错，只增加 epoch 而不提升最终可编译率，则 H 应改为 fatal-first。  
2. 若存在大量样本中 `evaluation_axes=[]` 仍可由 MB 稳定产出高质量、非漂移的草稿，则我“空轴不得入 MB”的边界可被推翻。

---


### [16] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-09T18:30:50.878471*

# 裁判裁定书：Layer 1 设计问题 E/F/G/H

---

## 第一部分：白话版结论

### 问题 E：`evaluation_axes.mode` 只能是 `regulative` 吗？normalize_question() 失败时怎么办？

**裁定：是的，Layer 1 只允许 `regulative` 模式；空轴是可恢复错误，不是合法状态。**

想象一个侦探事务所接到委托。侦探（Layer 1）首先要把委托人的模糊诉求（"帮我查清楚这件事"）翻译成具体的调查方向——比如"查资金流向""查人际关系""查时间线"。这些调查方向就是 `evaluation_axes`。

`regulative` 模式意味着：这些方向是"暂定的调查线索"，随时可以根据新证据调整。如果 LLM 生成了一个 `constitutive`（"铁律"）模式的轴——比如声称"资金流向就是唯一真相"——系统必须拒绝它，因为在 Layer 1 阶段，没有任何调查方向有资格自封为不可修正的定论。

**具体例子**：当系统处理"AI 是否应该被监管？"时，`normalize_question()` 可能推断出三个轴：创新影响、安全风险、公平性。如果 LLM 把"安全风险"标记为 `constitutive`（意思是"安全风险是不可质疑的评估维度"），系统应当返回 `Err(INVALID_AXIS_MODE)`，而不是静默接受。因为一旦静默接受，后续所有假设都会围绕"安全风险必然是核心维度"展开，而这个预设本身可能就是需要被检验的。

**空轴问题**：如果 `normalize_question()` 一个轴都推断不出来（比如用户问了"什么是好的？"），系统不应该假装一切正常然后让 `macro_breadth()` 在空白上胡编。正确做法是返回一个**可恢复错误**（`NormalizeRecoverable`），告诉上游："我推断出了一些利益相关方，但没能形成合法的评估轴，需要更多信息。"这和"这个问题根本不是经验问题"（`NormalizeFatal`，比如"这句话是假的"这种自指悖论）是两种完全不同的失败。

**可能需要修正的场景**：如果实践中发现大量合理问题在首轮都无法生成轴（比如高度探索性的科学问题），`NormalizeRecoverable` 的触发率过高导致系统可用性下降，则可能需要引入"最小默认轴集"作为 fallback，而非一律阻断。

**一句话总结**：Layer 1 的轴只能是暂定路标（regulative），不能是铁律；推断不出路标时要诚实报告，不能假装有路。

---

### 问题 F：`macro_breadth()` 的三类张力源如何分类、排序、覆盖？

**裁定：采用分层配额制（tier-then-quota），不采用统一打分池；但"先验/经验"的标签必须由构造过程决定，不能硬编码。**

继续侦探事务所的比喻。侦探拿到调查方向后，要从不同角度提出"假说"。假说的来源有三种：

1. **调查方向本身的内在张力**（EVALUATION_AXIS_SPLIT）：比如"资金流向"这条线索本身就有两种对立解读——"资金是合法避税"vs"资金是洗钱"。这是从问题结构内部长出来的分歧。
2. **不同当事人的利益冲突**（STAKEHOLDER_CONFLICT）：委托人说"他是好人"，证人说"他是骗子"。这是外部经验性的对立。
3. **外部专家意见**（EXTERNAL_POSITION）：另一个事务所发表过报告说"此类案件通常是内部人作案"。这是引入的外部立场。

**为什么要分层而不是混在一起打分？** 因为第一类张力和后两类张力的性质不同。第一类是从问题框架内部推导出的结构性分歧——如果你的调查方向本身就蕴含对立，那这种对立几乎必然需要被探索。后两类是经验性的，可能只是信息不全或采样偏差。把它们放进同一个打分池，用 `+100` vs `+10` 这种魔法数字来区分，等于把范畴差异压扁成了数值差异——这是康德最初方案的问题，也是 Linus 统一 `rankCandidates()` 方案的隐患。

**但 Ssyram 对康德的攻击也成立**：评估轴本身往往是从利益相关方冲突中推断出来的。如果"创新 vs 安全"这个轴就是从"开源社区 vs 监管机构"的冲突中提炼的，那说前者是"先验的"、后者是"经验的"就有循环论证之嫌。

**最终裁定的折中方案**：分层配额制保留，但"内部张力"的资格不是靠 `TensionSourceKind` 的枚举值硬编码，而是靠**构造过程的可追溯性**判定。具体来说：一个 `EVALUATION_AXIS_SPLIT` 类型的张力候选，只有当它所依赖的轴拥有独立的 `falsifier`（可证伪条件）且该 falsifier 不完全还原为某个 stakeholder 的立场时，才进入内部层（INTERNAL_AXIS tier）。否则降级为经验层。

**具体例子**：处理"AI 是否应该开源？"时——
- 轴"创新速度"有独立 falsifier："如果开源后 12 个月内主要 AI 实验室的论文产出未增加，则创新速度假说被证伪"。这个 falsifier 不依赖任何特定利益方的立场，进入内部层。
- 轴"社区信任度"的 falsifier 是"如果开源社区成员满意度调查低于阈值"——这本质上就是 stakeholder 的态度，降级为经验层。
- 外部立场"Elon Musk 认为 AI 应该开源"直接进入经验层。

配额分配：`maxDrafts` 的上半部分优先分配给内部层，下半部分分配给经验层。内部层不足时，配额让渡给经验层。

**同源性（is_homologous）的计算**：Ssyram 对康德的攻击完全成立——同源性是集合上的二元关系，不是单个候选的布尔属性。裁定要求：同源性必须在选择循环中动态计算（贪心去重），不能预标记。

**可能需要修正的场景**：如果实践中发现"独立 falsifier"的判定本身高度依赖 LLM 的语义理解且不稳定，则可能需要退化为 Linus 的简单优先级排序（axis > stakeholder > external），放弃精细的资格判定。

**一句话总结**：张力源分层选取而非混合打分，但"内部张力"的资格要靠 falsifier 独立性来挣，不能靠枚举值白拿。

---

### 问题 G：`open_terms` 在流水线中如何传递和消费？

**裁定：`macro_breadth()` 对 `open_terms` 执行"标记但不驱动"策略；`ClarityCompiler` 执行硬门控；死锁由 QN 的精炼回路打破。**

回到侦探事务所。委托人说"帮我查清楚他是不是个好人"。"好人"就是一个 `open_term`——它没有明确定义，不同人理解不同。

三位辩手的立场形成了一个清晰的光谱：
- **Ssyram 最初立场**："侦探提假说时完全不管'好人'这个词没定义，等到写报告（CC 编译）时再拦截。" → 问题：侦探会批量产出一堆围绕"好人"的假说，报告部门全部退回，来回空转（死锁）。Linus 的攻击完全成立。
- **Linus 立场**："侦探提假说时给含'好人'的假说打个风险标签，但不因此改变假说内容。" → 问题：标签只是字符串注记，不改变生成行为，实质上和盲视差别不大。康德的攻击部分成立。
- **Ssyram 修正后立场**："CC 拒绝后，把失败信号反馈给 QN，QN 把'好人'拆解成具体的评估轴（比如'是否守法''是否善待家人'），下一轮 MB 就能基于合法轴生成假说。" → 这是正确的闭环，但需要严格的类型保证。

**最终裁定**：

1. **MB 不基于 `open_terms` 生成假说**（不把"好人的不同定义"当作张力源来驱动广度探索）。理由：定义分歧应该在 QN 阶段被结构化为评估轴或 scope 约束，而不是在 MB 阶段被当作一阶张力。这是关注点分离的要求。

2. **MB 执行轻量级标记**：对每个草稿，检测其 `claim_sketch` 是否引用了 `open_terms` 中的词项，并在 `open_term_risk: string[]` 字段中记录。这不改变生成逻辑，但为 CC 提供预筛信息，避免 CC 做完整语义分析时的冗余计算。

3. **CC 执行硬门控**：如果草稿的 `claim_sketch` 包含未绑定的 open term，返回 `Err(UNBOUND_OPEN_TERM)`，附带 `RefinementSignal`。

4. **QN 的精炼回路打破死锁**：QN 接收 `RefinementSignal`，执行"概念降解"——尝试将 open term 转化为评估轴或 scope 约束。如果降解失败（比如"好"这个词实在太模糊，无法拆解），QN 返回 `NormalizeRecoverable`，请求外部输入（用户澄清或注入默认轴库）。

5. **`open_terms` 留在 `QuestionFrame` 公共 schema 中**，因为它有三个消费者：CC（硬门控）、MB（轻量标记）、QN 精炼回路（降解触发器）。Ssyram 最初说"只有 CC 消费"是错的；Linus 说"如果只有 CC 消费就不该在公共 schema"的攻击是对的，但结论应该是承认多消费者，而非移除字段。

**具体例子**："最优数据库索引策略是什么？"
- Epoch 1：QN 输出 `open_terms: ["最优"]`，`evaluation_axes: []` → 触发 `NormalizeRecoverable`（空轴），不进入 MB。
- 用户/系统补充上下文："面向 OLTP 场景，关注读写延迟和存储开销"。
- Epoch 2：QN 重新解析，`open_terms: []`（"最优"已降解为两个轴），`evaluation_axes: [{axis_id: "read_latency", falsifier: "..."}, {axis_id: "storage_cost", falsifier: "..."}]`。MB 正常生成。
- 如果 Epoch 2 中 MB 仍然生成了含"最优"的草稿（因为问题原文包含该词），MB 标记 `open_term_risk: ["最优"]`，CC 检查发现该词已不在 `frame.open_terms` 中（已被降解），编译通过。

**可能需要修正的场景**：如果实践中发现"概念降解"的成功率很低（大量 open terms 无法被自动拆解为轴），则可能需要允许 MB 在受限条件下将 open term 的竞争性定义作为张力源——即部分回退到"定义分歧也是一阶张力"的立场。这应该作为配置开关而非硬编码。

**一句话总结**：`open_terms` 是流水线的共享警报信号——MB 看到它会标记风险但不改变行为，CC 看到它会硬拦截，QN 看到反馈会尝试把模糊概念拆成具体轴。

---

### 问题 H：`normalize_question()` 的失败分类与恢复机制

**裁定：失败必须区分"不可恢复"（fatal）和"可恢复"（recoverable）两类，可恢复失败不得进入 MB，但允许进入精炼回路。**

最后一个比喻。侦探事务所接到两种"坏委托"：
- **不可恢复型**：委托人说"请证明这句话是假的：'这句话是假的'"。这是自指悖论，不是调查问题。事务所应该直接退回委托，附上原因。
- **可恢复型**：委托人说"帮我查查这个事情"，但没说查什么方面、涉及谁。事务所不应该直接退回，而应该说"我们初步判断可能涉及 A、B、C 三方，但需要你确认调查方向"。

**Linus 的贡献**：明确了 `Result<QuestionFrame, NormalizeError>` 的必要性，拒绝裸返回。
**康德的贡献**：将 `NormalizeError` 细分为 `NormalizeFatal`（范畴错误，如自指悖论、对抽象实体赋予非经验属性）和 `NormalizeRecoverable`（信息不足，如空轴、scope 过宽）。
**Ssyram 的贡献**：给出了精炼回路的 `RefinementSignal` 机制，使可恢复失败有了闭环修复路径。

**最终裁定**：三者的贡献互补，合并为统一方案。

```
normalize_question() 的输出：
  Ok(QuestionFrame)           → 进入 MB
  Err(NormalizeFatal)         → 终止，返回用户，附 repair_advice
  Err(NormalizeRecoverable)   → 不进入 MB，进入精炼回路
                                 （请求用户输入 / 注入外部触发器 / 重试）
```

**关键不变式**：`Ok(QuestionFrame)` 保证 `evaluation_axes.length >= 1` 且所有轴 `mode === "regulative"`。这是进入 MB 的前置条件，由类型系统强制保证，不依赖运行时检查。

**具体例子**："这句话是假的"→ `NormalizeFatal(SELF_REFERENCE_PARADOX)`，系统终止。"什么是好的教育？"→ `NormalizeRecoverable(EMPTY_AXES, stakeholders: ["学生","教师","政策制定者"])`，系统提示用户："我们识别出三类利益相关方，但无法确定评估维度。请指定您关注的方面（如学业成绩、心理健康、社会适应性）。"

**精炼回路的终止条件**：最多 `max_refinement_epochs`（建议默认 3）轮。如果 3 轮后仍为 `NormalizeRecoverable`，升级为 `NormalizeFatal(REFINEMENT_EXHAUSTED)`，终止。这防止无限精炼。

**可能需要修正的场景**：如果实践中发现 `NormalizeFatal` 和 `NormalizeRecoverable` 的边界难以稳定判定（比如某些问题在不同 LLM 版本下被分到不同类别），则可能需要将分类本身也做成可配置的规则集，而非硬编码的枚举匹配。

**一句话总结**：问题解析失败分两种——"这不是个合法问题"直接退回，"这个问题还不够清楚"允许补充信息后重试，但重试有次数上限。

---

## 第二部分：可实现性摘要

### 1. `normalize_question()` 最终接口规范

**TypeScript 类型：**

```typescript
// === 输入 ===
type ProblemStatement = {
  raw_question: string;
  context?: string;
  user_constraints?: string[];
};

type RefinementSignal = {
  rejected_draft_id: string;
  unresolved_term: string;
  offending_context: string;
  epoch: number;
};

// === 输出：成功 ===
type RegulativeAxis = {
  axis_id: string;
  label: string;
  mode: "regulative";  // 字面量类型，编译期强制
  falsifier: string;
  falsifier_independence: "INDEPENDENT" | "STAKEHOLDER_DERIVED";
  // ↑ 用于 F 裁定：决定该轴在 MB 中进入哪个 tier
};

type QuestionFrame = {
  problem_id: string;
  scope: string;
  evaluation_axes: [RegulativeAxis, ...RegulativeAxis[]];
  // ↑ 非空元组类型，编译期保证 length >= 1
  open_terms: string[];
  stakeholders: string[];
  excluded_forms: CategoryErrorTag[];
};

// === 输出：失败 ===
type CategoryErrorTag =
  | "SELF_REFERENCE_PARADOX"
  | "NON_EMPIRICAL_ATTRIBUTE_ON_ABSTRACT_ENTITY"
  | "UNFALSIFIABLE_VALUE_ASSERTION"
  | "SCOPE_UNBOUNDED";

type NormalizeFatal = {
  code: "CATEGORY_ERROR";
  tags: [CategoryErrorTag, ...CategoryErrorTag[]];
  repair_advice: string[];
};

type NormalizeRecoverable = {
  code: "INSUFFICIENT_FRAME";
  partial_stakeholders: string[];
  partial_open_terms: string[];
  missing: ("evaluation_axes" | "scope")[];
  repair_advice: string[];
};

type NormalizeError = NormalizeFatal | NormalizeRecoverable;

type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

// === 函数签名 ===
function normalize_question(
  stmt: ProblemStatement,
  refinements?: RefinementSignal[]
): Result<QuestionFrame, NormalizeError>;
```

**Python 伪代码（含失败路径）：**

```python
def normalize_question(
    stmt: ProblemStatement,
    refinements: list[RefinementSignal] = []
) -> Result[QuestionFrame, NormalizeError]:
    
    # Phase 1: 范畴检查（不可恢复失败）
    category_errors = detect_category_errors(stmt.raw_question)
    if category_errors:
        return Err(NormalizeFatal(
            code="CATEGORY_ERROR",
            tags=category_errors,
            repair_advice=generate_repair_hints(category_errors)
        ))
    
    # Phase 2: 应用精炼信号（如果有）
    effective_question = stmt.raw_question
    excluded_terms: list[str] = []
    for signal in refinements:
        # 尝试将 unresolved term 降解为轴或 scope 约束
        degradation = attempt_term_degradation(signal.unresolved_term, stmt)
        if degradation.success:
            # "最优" → axes: [throughput, latency]
            effective_question = apply_degradation(effective_question, degradation)
        else:
            excluded_terms.append(signal.unresolved_term)
    
    # Phase 3: 推断利益相关方
    stakeholders = infer_stakeholders(effective_question, stmt.context)
    
    # Phase 4: 从利益相关方冲突 + 问题结构推断评估轴
    raw_axes = infer_evaluation_axes(effective_question, stakeholders, stmt.context)
    
    # Phase 5: 强制 regulative 模式 + 验证
    validated_axes: list[RegulativeAxis] = []
    for ax in raw_axes:
        result = make_regulative_axis(ax)
        if result.ok:
            validated_axes.append(result.value)
        # 非 regulative 的轴被静默丢弃（或可选：返回错误）
    
    # Phase 6: 空轴检查（可恢复失败）
    if not validated_axes:
        return Err(NormalizeRecoverable(
            code="INSUFFICIENT_FRAME",
            partial_stakeholders=stakeholders,
            partial_open_terms=detect_open_terms(effective_question),
            missing=["evaluation_axes"],
            repair_advice=["请指定您关注的评估维度", 
                          f"已识别利益相关方: {stakeholders}"]
        ))
    
    # Phase 7: 检测 open terms
    open_terms = detect_open_terms(effective_question)
    open_terms = [t for t in open_terms if t not in excluded_terms]
    
    # Phase 8: 构造合法 QuestionFrame
    return Ok(QuestionFrame(
        problem_id=generate_id(),
        scope=infer_scope(effective_question, stmt.user_constraints),
        evaluation_axes=validated_axes,  # 保证非空
        open_terms=open_terms,
        stakeholders=stakeholders,
        excluded_forms=detect_excluded_forms(effective_question)
    ))


def make_regulative_axis(raw: dict) -> Result[RegulativeAxis, NormalizeError]:
    """构造器：强制 mode=regulative，拒绝 constitutive"""
    if raw.get("mode") and raw["mode"] != "regulative":
        return Err(NormalizeError(code="INVALID_AXIS_MODE", bad_axis_ids=[raw["axis_id"]]))
    
    # 判定 falsifier 独立性
    independence = assess_falsifier_independence(raw["falsifier"], raw.get("source_stakeholders"))
    
    return Ok(RegulativeAxis(
        axis_id=raw["axis_id"],
        label=raw["label"],
        mode="regulative",
        falsifier=raw["falsifier"],
        falsifier_independence=independence
    ))
```

---

### 2. `macro_breadth()` 最终接口规范

**TypeScript 类型：**

```typescript
// === 配置 ===
type MacroBreadthConfig = {
  max_drafts: number;                    // 硬上限，默认 6
  internal_tier_quota: number;           // 内部层配额比例，默认 0.5
  per_axis_cap: number;                  // 单轴最大草稿数，默认 2
  require_kind_diversity: boolean;       // 是否要求多种张力类型，默认 true
  max_open_term_risk_ratio: number;      // open_term 风险草稿占比上限，默认 0.5
  default_ttl: number;                   // 草稿初始 TTL，默认 3
};

// === 张力源 ===
type TensionSourceKind =
  | "EXTERNAL_POSITION"
  | "STAKEHOLDER_CONFLICT"
  | "EVALUATION_AXIS_SPLIT";

type EpistemicTier = "INTERNAL_AXIS" | "EMPIRICAL";

type TensionCandidate = {
  candidate_id: string;
  kind: TensionSourceKind;
  tier: EpistemicTier;  // 由 falsifier_independence 决定，非硬编码
  axis_ids: string[];
  stakeholders: string[];
  claim_sketch: string;
  verifier_hint: string[];
  salience: number;       // 0..1, 层内排序用
  open_term_risk: string[]; // MB 标记的风险 open terms
};

// === 输出 ===
type HypothesisDraft = {
  draft_id: string;
  problem_id: string;
  claim_sketch: string;
  tension_source: {
    kind: TensionSourceKind;
    tier: EpistemicTier;
    evidence_ref: string[];
    note: string;
  };
  verifier_hint: string[];
  open_term_risk: string[];
  ttl: number;
};

// === 错误 ===
type MacroBreadthError =
  | { code: "NO_TENSION_FOUND"; axes_tried: string[]; stakeholders_tried: string[] }
  | { code: "ALL_DRAFTS_HOMOLOGOUS"; cluster_summary: string }
  | { code: "OPEN_TERM_SATURATION"; saturated_terms: string[] };

// === 函数签名 ===
function macro_breadth(
  frame: QuestionFrame,
  config?: MacroBreadthConfig,
  external_positions?: ExternalPosition[]
): Result<HypothesisDraft[], MacroBreadthError>;
```

**Python 伪代码（含三种张力源处理逻辑和 fallback）：**

```python
def macro_breadth(
    frame: QuestionFrame,
    config: MacroBreadthConfig = DEFAULT_CONFIG,
    external_positions: list[ExternalPosition] = []
) -> Result[list[HypothesisDraft], MacroBreadthError]:
    
    # ========================================
    # Phase 1: 生成所有张力候选
    # ========================================
    candidates: list[TensionCandidate] = []
    
    # 张力源 1: EVALUATION_AXIS_SPLIT
    for axis in frame.evaluation_axes:
        splits = generate_axis_splits(axis, frame)
        for split in splits:
            tier = ("INTERNAL_AXIS" 
                    if axis.falsifier_independence == "INDEPENDENT" 
                    else "EMPIRICAL")
            candidates.append(TensionCandidate(
                kind="EVALUATION_AXIS_SPLIT",
                tier=tier,
                axis_ids=[axis.axis_id],
                claim_sketch=split.claim,
                verifier_hint=[axis.falsifier],
                open_term_risk=detect_open_term_overlap(split.claim, frame.open_terms),
                salience=split.salience,
                ...
            ))
    
    # 张力源 2: STAKEHOLDER_CONFLICT
    for pair in combinations(frame.stakeholders, 2):
        conflicts = generate_stakeholder_conflicts(pair, frame)
        for conflict in conflicts:
            candidates.append(TensionCandidate(
                kind="STAKEHOLDER_CONFLICT",
                tier="EMPIRICAL",
                stakeholders=list(pair),
                claim_sketch=conflict.claim,
                open_term_risk=detect_open_term_overlap(conflict.claim, frame.open_terms),
                salience=conflict.salience,
                ...
            ))
    
    # 张力源 3: EXTERNAL_POSITION
    for pos in external_positions[:config.max_drafts]:  # 硬上限
        candidates.append(TensionCandidate(
            kind="EXTERNAL_POSITION",
            tier="EMPIRICAL",
            claim_sketch=pos.text,
            open_term_risk=detect_open_term_overlap(pos.text, frame.open_terms),
            salience=assess_external_salience(pos, frame),
            ...
        ))
    
    # ========================================
    # Phase 2: Fallback 检查
    # ========================================
    if not candidates:
        return Err(MacroBreadthError(
            code="NO_TENSION_FOUND",
            axes_tried=[a.axis_id for a in frame.evaluation_axes],
            stakeholders_tried=frame.stakeholders
        ))
    
    # ========================================
    # Phase 3: 分层配额选择 + 贪心去重
    # ========================================
    internal_pool = [c for c in candidates if c.tier == "INTERNAL_AXIS"]
    empirical_pool = [c for c in candidates if c.tier == "EMPIRICAL"]
    
    internal_pool.sort(key=lambda c: c.salience, reverse=True)
    empirical_pool.sort(key=lambda c: c.salience, reverse=True)
    
    internal_quota = math.ceil(config.max_drafts * config.internal_tier_quota)
    empirical_quota = config.max_drafts - internal_quota
    
    # 配额让渡：内部层不足时让给经验层
    actual_internal = min(len(internal_pool), internal_quota)
    actual_empirical = min(len(empirical_pool), empirical_quota + (internal_quota - actual_internal))
    
    selected: list[TensionCandidate] = []
    
    # 贪心去重选择（同源性是动态计算的，不是预标记的）
    for pool, quota in [(internal_pool, actual_internal), (empirical_pool, actual_empirical)]:
        for candidate in pool:
            if len([s for s in selected if s.tier == candidate.tier]) >= quota:
                break
            if is_homologous_to_selected(candidate, selected):
                continue  # 跳过与已选集合同源的候选
            if count_per_axis(candidate, selected) >= config.per_axis_cap:
                continue  # 单轴上限
            selected.append(candidate)
    
    # ========================================
    # Phase 4: 同源性全灭检查
    # ========================================
    if not selected:
        return Err(MacroBreadthError(
            code="ALL_DRAFTS_HOMOLOGOUS",
            cluster_summary=summarize_homologous_clusters(candidates)
        ))
    
    # ========================================
    # Phase 5: Open term 风险饱和检查
    # ========================================
    risky_count = sum(1 for s in selected if s.open_term_risk)
    if risky_count / len(selected) > config.max_open_term_risk_ratio:
        return Err(MacroBreadthError(
            code="OPEN_TERM_SATURATION",
            saturated_terms=list(set(t for s in selected for t in s.open_term_risk))
        ))
    
    # ========================================
    # Phase 6: 转换为 HypothesisDraft
    # ========================================
    drafts = [to_hypothesis_draft(c, frame, config) for c in selected]
    return Ok(drafts)


def is_homologous_to_selected(
    candidate: TensionCandidate, 
    selected: list[TensionCandidate]
) -> bool:
    """同源性：动态计算，基于 claim_sketch 的语义相似度 + 轴重叠度"""
    for s in selected:
        axis_overlap = len(set(candidate.axis_ids) & set(s.axis_ids)) / max(len(candidate.axis_ids), 1)
        semantic_sim = compute_semantic_similarity(candidate.claim_sketch, s.claim_sketch)
        if axis_overlap > 0.8 and semantic_sim > 0.85:
            return True
    return False
```

---

### 3. 完整数据流与不变式

```
ProblemStatement
       │
       ▼
┌──────────────────────┐
│  normalize_question() │
│                      │
│  不变式:             │
│  INV-1: Ok ⟹ axes.length ≥ 1
│  INV-2: Ok ⟹ ∀axis: mode = "regulative"
│  INV-3: Err(Fatal) ⟹ 不可重试
│  INV-4: Err(Recoverable) ⟹ 可重试，≤ max_epochs
└──────┬───────────────┘
       │
       ├── Err(Fatal) ──────────────────────────→ 终止，返回用户
       │
       ├── Err(Recoverable) ──→ 精炼回路 ──→ 重新调用 normalize_question(stmt, signals)
       │                              ↑                    │
       │                              │                    │
       │                     RefinementSignal ←── CC 失败反馈
       │
       ▼ Ok(QuestionFrame)
┌──────────────────────┐
│   macro_breadth()    │
│                      │
│  前置条件:           │
│  PRE-1: frame.evaluation_axes.length ≥ 1
│  PRE-2: ∀axis: mode = "regulative"
│                      │
│  不变式:             │
│  INV-5: Ok ⟹ drafts.length ∈ [1, config.max_drafts]
│  INV-6: Ok ⟹ ¬∃(d1,d2): is_homologous(d1,d2)
│  INV-7: Ok ⟹ risky_ratio ≤ config.max_open_term_risk_ratio
│  INV-8: Err ⟹ 结构化失败，不产出空数组
└──────┬───────────────┘
       │
       ├── Err(NO_TENSION_FOUND) ──→ 请求外部立场注入 / 返回用户
       ├── Err(ALL_DRAFTS_HOMOLOGOUS) ──→ 请求外部立场注入
       ├── Err(OPEN_TERM_SATURATION) ──→ 触发 QN 精炼回路
       │
       ▼ Ok(HypothesisDraft[])
┌──────────────────────┐
│  ClarityCompiler     │
│  compile(draft, frame)│
│                      │
│  前置条件:           │
│  PRE-3: draft 来自合法 MB 输出
│  PRE-4: frame 与 draft.problem_id 匹配
│                      │
│  不变式:             │
│  INV-9:  Ok ⟹ claim 不含 frame.open_terms 中的未绑定词
│  INV-10: Ok ⟹ claim.evaluation_axis ∈ frame.evaluation_axes
│  INV-11: Err(UNBOUND_OPEN_TERM) ⟹ 产出 RefinementSignal
│  INV-12: Err(AXIS_MISMATCH) ⟹ 产出 RefinementSignal
└──────┬───────────────┘
       │
       ├── Err ──→ RefinementSignal ──→ 回到 QN 精炼回路
       │
       ▼ Ok(TestableClaim)
       │
       → 进入 Layer 2 (S4/S5 验证链)
```

**跨组件不变式：**
- **INV-GLOBAL-1**：精炼回路总轮次 ≤ `max_refinement_epochs`（默认 3）。超过后，最后一个 `NormalizeRecoverable` 升级为 `NormalizeFatal(REFINEMENT_EXHAUSTED)`。
- **INV-GLOBAL-2**：`open_terms` 在整个流水线中单调递减——每轮精炼要么将 open term 降解为轴，要么将其加入 `excluded_terms`，不允许新增。
- **INV-GLOBAL-3**：`HypothesisDraft[]` 永远不为空数组。MB 要么返回 `Ok(非空数组)`，要么返回 `Err`。下游不需要检查空数组。

---

### 4. 端到端运行 Trace

**输入**：`ProblemStatement { raw_question: "AI 是否应该被监管？" }`

---

**Epoch 1：**

**Step 1: normalize_question(stmt, [])**
```
Phase 1: 范畴检查 → 无范畴错误
Phase 2: 无精炼信号，跳过
Phase 3: 推断利益相关方 → ["AI开发者", "监管机构", "终端用户"]
Phase 4: 推断评估轴 →
  - {axis_id: "innovation_impact", label: "创新影响", mode: "regulative",
     falsifier: "若监管后AI研发投入和产出未下降则证伪",
     falsifier_independence: "INDEPENDENT"}
  - {axis_id: "public_safety", label: "公共安全", mode: "regulative",
     falsifier: "若无监管时AI事故率未高于有监管场景则证伪",
     falsifier_independence: "INDEPENDENT"}
  - {axis_id: "market_fairness", label: "市场公平性", mode: "regulative",
     falsifier: "若利益相关方满意度调查显示无显著不公则证伪",
     falsifier_independence: "STAKEHOLDER_DERIVED"}
Phase 5: 强制 regulative → 全部通过
Phase 6: 3 个轴，非空 → 通过
Phase 7: open_terms → ["AI", "监管"]
  （"AI"和"监管"在此问题中语义宽泛，标记为 open）
Phase 8: 输出 →
  Ok(QuestionFrame {
    problem_id: "q-001",
    scope: "当前全球主要经济体的AI技术治理",
    evaluation_axes: [innovation_impact, public_safety, market_fairness],
    open_terms: ["AI", "监管"],
    stakeholders: ["AI开发者", "监管机构", "终端用户"],
    excluded_forms: []
  })
```

**Step 2: macro_breadth(frame, config)**
```
Phase 1: 生成张力候选
  EVALUATION_AXIS_SPLIT:
    - C1: {kind: AXIS_SPLIT, tier: INTERNAL_AXIS, axis: innovation_impact,
           claim: "强制性AI许可制度会将研发投入降低30%以上",
           open_term_risk: ["AI"], salience: 0.9}
    - C2: {kind: AXIS_SPLIT, tier: INTERNAL_AXIS, axis: public_safety,
           claim: "无监管的AI部署在医疗领域将导致可量化的患者伤害增加",
           open_term_risk: ["AI"], salience: 0.85}
    - C3: {kind: AXIS_SPLIT, tier: STAKEHOLDER_DERIVED→EMPIRICAL, axis: market_fairness,
           claim: "AI监管合规成本将淘汰80%的中小AI企业",
           open_term_risk: ["AI", "监管"], salience: 0.7}
  STAKEHOLDER_CONFLICT:
    - C4: {kind: STAKEHOLDER, tier: EMPIRICAL, pair: [AI开发者, 监管机构],
           claim: "AI开发者的自律机制在历史上从未有效替代过外部监管",
           open_term_risk: ["AI", "监管"], salience: 0.75}
    - C5: {kind: STAKEHOLDER, tier: EMPIRICAL, pair: [终端用户, AI开发者],
           claim: "终端用户更信任政府监管而非企业自律来保障AI安全",
           open_term_risk: ["AI", "监管"], salience: 0.6}

Phase 2: 候选非空 → 继续

Phase 3: 分层配额选择 (max_drafts=6, internal_quota=0.5)
  internal_quota = ceil(6 * 0.5) = 3
  empirical_quota = 3
  
  Internal pool: [C1(0.9), C2(0.85)]  → 只有2个，actual_internal=2
  Empirical pool: [C4(0.75), C3(0.7), C5(0.6)] → actual_empirical=min(3, 3+1)=4, 但只有3个
  
  贪心去重选择:
    Internal: C1 ✓, C2 ✓ (不同轴，不同源)
    Empirical: C4 ✓, C3 ✓ (C3 vs C4: 轴不同，不同源), C5 ✓
  
  selected = [C1, C2, C4, C3, C5]  (5个)

Phase 4: 无全灭 → 继续

Phase 5: open_term_risk 检查
  risky_count = 5 (全部含 open term risk)
  ratio = 5/5 = 1.0 > 0.5 (max_open_term_risk_ratio)
  → Err(OPEN_TERM_SATURATION, saturated_terms: ["AI", "监管"])
```

**Step 3: 处理 OPEN_TERM_SATURATION → 触发 QN 精炼回路**

系统生成 `RefinementSignal`:
```
[
  {rejected_draft_id: "batch", unresolved_term: "AI", 
   offending_context: "问题核心术语过于宽泛", epoch: 1},
  {rejected_draft_id: "batch", unresolved_term: "监管", 
   offending_context: "监管形式未指定", epoch: 1}
]
```

---

**Epoch 2：**

**Step 1: normalize_question(stmt, refinement_signals)**
```
Phase 2: 应用精炼信号
  - "AI" → 降解尝试: 成功 → scope 约束: "生成式AI（LLM及多模态模型）"
  - "监管" → 降解尝试: 成功 → 新增轴: 
    {axis_id: "regulatory_form", label: "监管形式",
     falsifier: "若行业自律与政府立法在事故预防效果上无统计差异则证伪",
     falsifier_independence: "INDEPENDENT"}

Phase 7: open_terms → []  (两个 open term 均已降解)

输出 → Ok(QuestionFrame {
  problem_id: "q-001-r1",
  scope: "当前全球主要经济体对生成式AI（LLM及多模态模型）的技术治理",
  evaluation_axes: [innovation_impact, public_safety, market_fairness, regulatory_form],
  open_terms: [],
  stakeholders: ["AI开发者", "监管机构", "终端用户"],
  excluded_forms: []
})
```

**Step 2: macro_breadth(frame_v2, config)**
```
Phase 1: 生成张力候选 (现在有4个轴，open_terms为

---
