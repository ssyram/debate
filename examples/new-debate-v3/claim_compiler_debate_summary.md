# v3 认知引擎：clarity_compile() 的实现决策 裁判总结

> 2026-03-09T18:24:22.149503

# 裁判裁定书

---

## 第一部分：白话版结论

---

### W：严格/宽松平衡——编译器应该只输出"合格品"，还是也可以输出"半成品"？

**问题是什么：**

想象一个翻译局，负责把模糊的研究直觉翻译成可以实际检验的精确命题。争论在于：这个翻译局应该只放行"完全翻译好的成品"（Linus 的立场），还是也可以放行"翻译了一半但骨架清晰的半成品"（Ssyram 的立场）？

**裁定：W1 修正版——二值输出，但增设第三类非命题对象。**

Linus 的核心论点是对的：一个叫"可检验命题"的东西，如果实际上不可检验，那整个系统就在对自己撒谎。Ssyram 的 PROVISIONAL（有证伪逻辑但没有判定阈值）和 SKELETAL（连证伪逻辑都没有）如果都被标记为 `TestableClaim` 的子类型，那下游的验证引擎就必须到处写"如果是半成品就走另一条路"的分支逻辑——这不是编译，是把未完成的工作推给别人。

**具体例子：**

假设有一个草稿："远程办公会降低团队的沟通带宽"。

- Ssyram 的方案：编译器发现"沟通带宽"这个概念有证伪逻辑（可以测量某种沟通频率），但具体阈值不知道该设多少，于是输出 PROVISIONAL。这个半成品进入验证层，验证层围绕它做深度分析，试图在分析过程中"顺便"把阈值定下来。
- Linus 的方案：编译器直接报错"NO_ACCEPT_TEST"，要求修复模块把"沟通带宽"改写成"跨团队同步会议频率每周低于 X 次"或"决策延迟超过 Y 天"，然后重新编译。
- **我的裁定**：Linus 的方案更诚实。让验证层去"顺便"补全编译器该做的工作，是职责越界。但 Linus 需要接受康德的修正——有些东西不是"写得差"，而是"本质上不属于可检验命题"，这需要第三个出口（见 Z 的裁定）。

**什么时候可能需要修正：** 如果实践中发现 repair() 对"逻辑完整但阈值暂缺"的草稿收敛率极低（比如反复重试都定不出合理阈值），那可能需要允许验证层参与阈值探索——但这应该通过显式的"阈值探索协议"而非偷偷降级来实现。

**一句话总结：** 编译器的输出要么是成品，要么是错误报告；把半成品伪装成成品是系统性的自欺。

---

### X：跨领域适应——不同学科的命题应该走不同的编译规则吗？

**问题是什么：**

物理学的命题可以用数字阈值来判定（"温度超过100°C水就沸腾"），但伦理学的命题怎么办（"AI开源是否公平"）？争论在于：是否需要一个"领域模板注册表"来为不同学科提供不同的编译规则。

**裁定：X1 修正版——统一编译流程，领域差异仅体现在 `accept_test` 的谓词类型中，但 `protocol` 类型必须有显式的认识论声明。**

Linus 的统一四步流程（normalize → check_single_proposition → synthesize_falsifier → lower_accept_test）是正确的架构选择。Ssyram 的 `DomainSchemaRegistry` 有一个致命问题：它的 `match()` 函数的判定边界从未被精确定义——什么算"经验领域"、什么算"规范领域"，这个分类本身就是有争议的，把它硬编码进注册表等于把偏见制度化。

但康德对 Linus 的批评也成立：Linus 的 `protocol_id: "expert_adjudication_v1"` 实际上是把领域模板藏进了字符串常量里，概念上并没有消除领域分类，只是让它变得不透明了。

**修正要求：** 每个 `protocol` 类型的 `accept_test` 必须附带一个显式的 `epistemic_status` 声明，标明它是"经验性证伪条件"还是"制度化判断程序"。这不改变编译流程，但让下游知道自己拿到的是什么性质的判定标准。

**具体例子：**

草稿："开源AI模型比闭源模型对小企业更公平"。

- Ssyram 的方案：`DomainSchemaRegistry` 同时匹配到 EMPIRICAL 和 NORMATIVE，返回 CONFLICT，降级为 SKELETAL。
- Linus 的方案：尝试把"公平"降到 `protocol: "expert_adjudication_v1"`，如果成功就编译通过。
- **我的裁定**：走 Linus 的统一流程，但如果最终只能落到 protocol，必须标注 `epistemic_status: "procedural_judgment"`（程序性判断），而非假装这是经验性证伪。如果连 protocol 都落不下来，走 CompileError 或 RegulativeIdea 出口。

**什么时候可能需要修正：** 如果系统需要处理的领域数量极大（比如上百个专业领域），且每个领域的证据制度差异显著到统一流程无法覆盖，那可能需要引入轻量级的领域适配层——但这应该是 `accept_test` 内部的扩展，不是编译主流程的分支。

**一句话总结：** 编译规则统一，领域差异只在判定标准的"最后一公里"体现，且必须诚实标注判定标准的认识论性质。

---

### Y：防漂移机制——如何防止编译器随时间变得越来越松或越来越紧？

**问题是什么：**

想象一个考试的评分标准。如果评分员发现很多学生答不好，可能会不自觉地降低标准（"漂移"）。反过来，如果评分员变得越来越严格，可能会把本来合格的答案也拒掉。编译器也有同样的风险：随着时间推移，它的判定标准可能悄悄偏移。

**裁定：基于 Linus 的审计日志方案，但增加康德式的"标准本身的合法性审查"。**

Linus 提出的机制（replay 审计、错误分布统计、观测哪些价值轴长期无法编译）是必要的工程基础设施。但康德指出了一个深层问题：如果编译标准本身就有系统性偏见（比如天然偏向经验科学、排斥规范性问题），那你统计得越精密，只是在更精确地执行一个有偏的标准。

**具体机制：**

1. **编译日志**：每次编译记录 `(draft_id, result, stage_trace, timestamp)`。
2. **分布监控**：每 N 次编译后，统计各 `CompileErrorCode` 的分布。如果某个错误码（如 `NO_FALSIFIER_SCHEMA`）的占比突然上升或下降超过阈值，触发人工审查。
3. **领域覆盖审计**：统计不同 `domain_kind` 的编译成功率。如果规范性命题的成功率长期显著低于经验性命题，不是自动调松标准，而是触发"标准合法性审查"——检查是否是标准本身对该领域不公平。
4. **回归测试**：维护一组"黄金样本"（已知应该编译成功和应该失败的草稿），每次标准变更后跑回归。

**具体例子：**

假设系统运行三个月后，发现"历史解释类"命题的编译成功率只有 5%，而"经验科学类"是 60%。

- 纯 Linus 方案：可能只是说"历史类草稿写得差，需要更好的 repair"。
- 加入康德修正后：会追问"是不是我们的 accept_test 要求本身就不适合历史解释类命题？是否需要为这类命题设计新的 protocol 类型？还是这类命题本质上应该走 RegulativeIdea 出口？"

**什么时候可能需要修正：** 如果系统规模很小（比如只处理几十个问题），统计监控可能没有足够样本量，此时可能需要更依赖人工审查而非自动化检测。

**一句话总结：** 既要监控标准的执行是否一致，也要定期审问标准本身是否公正。

---

### Z：不可编译命题的处置——那些"重要但无法检验"的想法怎么办？

**问题是什么：**

有些想法很重要、很有启发性，但你就是没办法把它变成一个可以用证据判定真假的命题。比如"正义要求每个人都被当作目的而非手段"——这不是写得差，而是它本质上不是一个经验命题。问题是：系统应该怎么处理这类东西？

**裁定：Z2 修正版——引入 `RegulativeIdea` 作为独立输出类型，不进入 Layer 2，但可在 Layer 1 的 RB 节点被消费以生成新草稿。**

这是三方辩论中争议最激烈、也最有哲学深度的问题。

- **Linus** 说：编译失败就是编译失败，不需要给失败品一个好听的名字。
- **Ssyram** 说：让它以 SKELETAL 的身份进入验证层，利用验证层的证据搜索能力来帮它进化。
- **康德** 说：它不是失败品，也不应该伪装成命题；它是另一种认识论对象，有自己的正面价值。

**我裁定康德的方案最合理，理由如下：**

Ssyram 的 SKELETAL 方案有一个根本性的范畴错误：Layer 2 的验证引擎是为"可验证命题"设计的，它的每个节点（S2 深度分析、S3 精确化、S4 深度探针、S5 广度探针）都预设输入对象有 falsifier。把没有 falsifier 的对象送进去，不是"宽松"，是让引擎在错误的对象上空转。Ssyram 说 S5 可以"基于张力源搜索证据"，但 S5 产出的 `SchemaChallengeNotice` 语义会失真——它到底是在挑战一个命题，还是在说"请先造一个命题出来"？

Linus 的方案诚实但不完整：他承认系统需要保留"高价值但不可编译的残余"，却没有给这些残余一个正面的概念地位。这等于承认了中间态的必要性，却拒绝定义它。

康德的 `RegulativeIdea` 解决了这个问题：它不是失败，不是半成品，而是一种"导向性理念"——它告诉系统"这个方向值得探索，但目前无法直接检验"。它留在 Layer 1，通过 `repair_from_regulative_idea` 尝试分解出可编译的子命题。

**具体例子：**

草稿："AI 的发展应该以人类繁荣为终极目标"。

- Linus 的方案：`CompileError: NO_FALSIFIER_SCHEMA`，repair 尝试改写，但"人类繁荣"这个概念可能怎么改都无法变成单一可检验命题。retry budget 耗尽后丢弃。
- Ssyram 的方案：SKELETAL，进入 S5 搜索相关证据。但 S5 围绕"人类繁荣"做广度扩展，可能返回大量松散相关的文献，却无法收敛成具体的可验证命题。
- 康德的方案：标记为 `RegulativeIdea { domain_kind: "normative", decomposition_hints: ["分解为：AI对就业的影响、AI对心理健康的影响、AI对教育公平的影响"] }`。RB 节点消费这些 hints，生成三个新的、更具体的 `HypothesisDraft`，每个都有更高的编译成功概率。

**关键修正：** 康德需要接受一个可推翻条件——如果线上数据证明 SKELETAL→S5→STRICT 的转化路径确实优于 RegulativeIdea→RB→新Draft→STRICT 的路径（且不增加伪 SchemaChallengeNotice），则应重新考虑。但举证责任在 Ssyram 一方。

**什么时候可能需要修正：** 如果 Layer 1 的 RB 节点确实太弱（没有外部数据源连接），导致 `repair_from_regulative_idea` 的收敛率极低，那可能需要为 RegulativeIdea 设计一个专门的"概念探索通道"——但这应该是 Layer 1 的增强，而非把不合格对象塞进 Layer 2。

**一句话总结：** 不可检验的重要理念不是垃圾，也不是半成品命题；它是另一种认识论对象，应该有自己的名字、自己的出口、自己的演化路径。

---

## 第二部分：可实现性摘要

### 1. clarity_compile() 的完整类型定义

```typescript
// ===== 基础类型 =====
type DomainKind = "empirical" | "normative" | "interpretive" | "mixed";

type EpistemicStatus = 
  | "empirical_falsification"    // 经验性证伪条件
  | "procedural_judgment";       // 制度化判断程序

type PredicateExpr =
  | { kind: "threshold"; metric: string; op: ">" | "<" | ">=" | "<=" | "==" | "!="; 
      value: number | string; window?: string }
  | { kind: "comparative"; lhs_metric: string; op: ">" | "<" | ">=" | "<=" | "==" | "!="; 
      rhs_metric: string; window?: string }
  | { kind: "protocol"; protocol_id: string; pass_rule: string; 
      epistemic_status: EpistemicStatus };

type AcceptTest = {
  predicate: PredicateExpr;
  evidence_bindings: string[];       // 必须映射到 EvidenceBundle 中的键
  indeterminate_when: string[];      // 显式声明何时返回 INDETERMINATE
};

type AcceptTestResult = "PASS" | "FAIL" | "INDETERMINATE";

// ===== 阶段追踪 =====
type StageTrace = {
  structure_ok: boolean;
  falsifier_schema_found: boolean;
  accept_test_bound: boolean;
  failure_stage?: "STRUCTURE" | "FALSIFIER" | "ACCEPT_TEST";
};

// ===== 编译成功输出 =====
type TestableClaim = {
  claim_id: string;
  proposition: string;              // 单一命题，无未绑定变量
  scope: string;                    // 显式化的适用范围
  assumptions: string[];            // 关键前提列表
  falsifier: string;                // 可操作的反证描述
  accept_test: AcceptTest;          // 机器可检查谓词
  non_claim: string[];              // 明确声明未主张什么
};

// ===== 调节性理念 =====
type RegulativeIdea = {
  idea_id: string;
  statement: string;
  domain_kind: DomainKind;
  reason_no_schema: "NO_BRIDGE_TO_OBSERVABLE" | "ONLY_PRAGMATIC_PROTOCOL";
  decomposition_hints: string[];    // 可能的子命题拆解方向
  stage_trace: StageTrace;
};

// ===== 编译错误（可修复） =====
type CompileErrorCode =
  | "MULTI_PROPOSITION"
  | "MISSING_SCOPE"
  | "MISSING_COMPARAND"
  | "UNBOUND_OBSERVABLE"
  | "NO_FALSIFIER_SCHEMA"
  | "NO_ACCEPT_TEST"
  | "STRUCTURAL_VOID"
  | "CATEGORY_ERROR";

type CompileError = {
  code: CompileErrorCode;
  message: string;
  repair_hints: string[];
  stage_trace: StageTrace;
  missing_fields: string[];
};

// ===== 编译结果（三路互斥） =====
type CompileResult =
  | { kind: "TESTABLE_CLAIM"; claim: TestableClaim }
  | { kind: "REGULATIVE_IDEA"; idea: RegulativeIdea }
  | { kind: "COMPILE_ERROR"; error: CompileError };

// ===== 编译选项 =====
type CompileOptions = {
  retry_budget: number;              // 每个 draft 的最大重试次数
};
```

### 2. 最终推荐的编译流水线伪代码

```
function clarity_compile(draft, frame, opts) -> CompileResult:
  
  // ===== Stage 1: Structure Extraction =====
  struct = extract_structure(draft.claim_sketch)
  // 提取: scope, stakeholders, evaluation_axes, tension_source
  
  if struct.failed:
    return COMPILE_ERROR {
      code: "STRUCTURAL_VOID",
      stage_trace: { structure_ok: false, ... },
      repair_hints: struct.suggestions
    }
  
  // ===== Stage 1b: Single Proposition Check =====
  propositions = decompose_to_propositions(struct.claim)
  if propositions.length > 1:
    return COMPILE_ERROR { code: "MULTI_PROPOSITION", ... }
  
  if has_unbound_comparand(propositions[0]):
    return COMPILE_ERROR { code: "MISSING_COMPARAND", ... }
  
  if scope_unbounded(struct.scope, draft.scope_ref):
    return COMPILE_ERROR { code: "MISSING_SCOPE", ... }
  
  // ===== Stage 2: Falsifier Synthesis =====
  falsifier = synthesize_falsifier(struct.tension_source, struct.axes)
  
  if falsifier.failed:
    domain = infer_domain_kind(struct.tension_source)
    
    if falsifier.reason == "NO_EMPIRICAL_BRIDGE" 
       AND domain in ["normative", "interpretive", "mixed"]:
      // 不可图型化 → 调节性理念
      return REGULATIVE_IDEA {
        statement: propositions[0],
        domain_kind: domain,
        reason_no_schema: "NO_BRIDGE_TO_OBSERVABLE",
        decomposition_hints: generate_decomposition(struct),
        stage_trace: { structure_ok: true, falsifier_schema_found: false, ... }
      }
    else:
      // 结构性缺陷 → 可修复错误
      return COMPILE_ERROR { code: "NO_FALSIFIER_SCHEMA", ... }
  
  // ===== Stage 3: Accept Test Lowering =====
  accept = lower_accept_test(falsifier, struct.scope)
  
  if accept.failed:
    if accept.reason == "ONLY_PRAGMATIC_PROTOCOL":
      return REGULATIVE_IDEA {
        reason_no_schema: "ONLY_PRAGMATIC_PROTOCOL",
        decomposition_hints: accept.alternative_framings,
        ...
      }
    else:
      return COMPILE_ERROR {
        code: "NO_ACCEPT_TEST" | "UNBOUND_OBSERVABLE",
        repair_hints: accept.binding_suggestions,
        ...
      }
  
  // ===== Success =====
  return TESTABLE_CLAIM {
    claim_id: generate_id(),
    proposition: propositions[0],
    scope: struct.scope,
    assumptions: extract_assumptions(draft),
    falsifier: falsifier.description,
    accept_test: accept.test,
    non_claim: extract_non_claims(draft)
  }
```

### 3. 与 repair() 的接口协议

```
CompileError → RepairHint 完整映射：

STRUCTURAL_VOID       → "草稿缺乏基本语义结构。请重新表述，
                          明确指出：谁受影响、在什么维度上、存在什么张力。"
                        + stage_trace 供 repair 定位

MULTI_PROPOSITION     → "草稿包含多个独立命题。请拆分为单一命题，
                          或选择最核心的一个。"
                        + propositions[] 列表

MISSING_SCOPE         → "命题适用范围未限定。请指定：时间、地域、
                          人群、组织类型等约束。"
                        + scope_ref 作为参考

MISSING_COMPARAND     → "比较命题缺少比较对象。请补充：
                          '相比什么' 或 '在什么基准下'。"
                        + 已识别的部分比较结构

UNBOUND_OBSERVABLE    → "证伪逻辑已有，但无法绑定到可观测指标。
                          请将模糊概念替换为可测量的代理变量。"
                        + 模糊词列表 + 候选代理变量

NO_FALSIFIER_SCHEMA   → "无法为该命题构造证伪条件。
                          请尝试：缩小范围、选择可观测的子方面、
                          或改用比较框架。"
                        + tension_source 供参考

NO_ACCEPT_TEST        → "证伪逻辑存在，但无法生成机器可检查的判定谓词。
                          请补充：阈值、时间窗、样本约束、或判定协议。"
                        + falsifier 描述 + 候选 predicate 模板

CATEGORY_ERROR        → "命题存在范畴错误（如对抽象实体赋予经验属性）。
                          请重新构造命题的主语-谓语关系。"
                        + 错误类型标签

RegulativeIdea → RB 节点协议：
  RB 接收 RegulativeIdea，消费 decomposition_hints，
  生成 0..N 个新 HypothesisDraft，每个重新进入 clarity_compile()。
  约束：每个 RegulativeIdea 最多触发 3 轮 RB 分解；
  若 3 轮后无子命题编译成功，保留到最终答案的
  "认识论边界"部分，标注为"当前不可编译的导向性理念"。
```

### 4. 防漂移机制的实现规格

```
触发条件：
  1. 滑动窗口（最近 100 次编译）中任一 CompileErrorCode 
     占比变化超过 ±15 个百分点
  2. 任一 domain_kind 的编译成功率偏离历史均值超过 ±20%
  3. RegulativeIdea 输出占比超过总输出的 30%
  4. 黄金样本回归测试失败率 > 5%

检测方法：
  - 每次编译写入审计日志：
    { draft_id, timestamp, result_kind, error_code?, domain_kind?, 
      stage_trace, compile_duration_ms }
  - 每 100 次编译自动计算分布指标
  - 每次编译标准变更后跑黄金样本回归（≥50 个样本，
    覆盖各 domain_kind 和各 error_code）

响应动作：
  - 触发条件 1/2：生成 DriftAlert，包含分布变化详情，
    提交人工审查。审查需回答：
    "是草稿质量变了，还是编译标准漂移了？"
  - 触发条件 3：启动"标准合法性审查"——
    检查是否有某类命题被系统性地错误归类为 RegulativeIdea
  - 触发条件 4：自动回滚到上一版编译标准，
    阻止新标准上线直到回归通过

标准合法性审查协议：
  - 抽取最近被标记为 UNSCHEMATIZABLE 的 20 个案例
  - 人工判定：其中有多少是"真正不可图型化"vs"标准过严"
  - 若 >40% 被判定为"标准过严"，触发标准修订流程
  - 修订后重跑黄金样本 + 历史样本回归
```

### 5. 实现难度最高的 2 个子模块及其风险

**子模块 1：`synthesize_falsifier()` —— 证伪器合成**

- **难度来源**：这是整个流水线中最依赖 LLM 判断力的环节。它需要从自然语言的张力描述中推导出一个可操作的反证条件，同时正确区分"当前写不出证伪器"（可修复）和"这类命题本质上不可证伪"（应转为 RegulativeIdea）。这个区分没有确定性算法，只能依赖启发式规则 + LLM 推理。
- **风险**：(a) LLM 可能过度自信地为不可证伪命题编造伪证伪器，导致假阳性（本应是 RegulativeIdea 的对象被错误编译为 TestableClaim）；(b) 反过来，LLM 可能过度保守，把可证伪命题错误地标记为不可图型化。
- **缓解措施**：对 `synthesize_falsifier` 的输出做二次验证——检查生成的 falsifier 是否真的能区分"命题为真"和"命题为假"的世界状态。维护一个 falsifier 质量的黄金样本集。

**子模块 2：`lower_accept_test()` 中的 `protocol` 类型处理**

- **难度来源**：对于规范性/解释性命题，如果它们能编译（即不被归为 RegulativeIdea），就必须落到 `protocol` 类型的 accept_test。但 `protocol_id` 的设计、`pass_rule` 的定义、以及 `epistemic_status` 的正确标注，都需要领域专业知识。系统需要维护一个 protocol 库，且每个 protocol 的合法性需要被论证。
- **风险**：(a) protocol 库可能覆盖不足，导致大量本可编译的规范性命题被错误地归为 RegulativeIdea；(b) protocol 的 `pass_rule` 可能过于宽松（如"3/5 专家同意即通过"），使得 accept_test 名义上存在但实质上不具备证伪力——这正是康德警告的"把制度化判断程序伪装成经验性证伪"。
- **缓解措施**：每个 protocol 必须附带文档，说明其认识论依据和适用边界。新 protocol 的引入需要通过审查流程。定期审计 protocol 判定结果与后续证据的一致性。