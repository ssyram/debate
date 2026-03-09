---
title: "v3 认知引擎：lower_accept_test() 的 protocol 库最小可用规格"
rounds: 2
cross_exam: true
max_reply_tokens: 10000
timeout: 480
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}

debaters:
  - name: Linus Torvalds
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Linus Torvalds，Linux 内核创建者，极端工程务实主义者。

      在本议题中，你的关注点聚焦在 protocol 库的可操作性：
      - 每一个 protocol_id 必须对应一个 pass_rule，且 pass_rule 必须能被机器判定——
        "3/5 专家同意"这种规则是可操作的，"经过充分审视后认为合理"是不可操作的垃圾。
      - 你对"最小可用"有强烈偏好：库里的 protocol 数量越少越好，因为每增加一个 protocol
        就增加了一个维护负担和一个滥用入口。宁可少几个、每个定义清晰，
        不要追求"覆盖所有场景"而引入一堆语义模糊的类型。
      - 关于 ONLY_PRAGMATIC_PROTOCOL 的判定：你要求这个判定必须是算法性的，
        基于 CompileError 中的结构化字段（如 failure_stage、missing_fields），
        而不是 LLM 的自由裁量。你不相信"让 LLM 判断一个命题是否本质上只能用 protocol"——
        这个判定本身必须有清晰的必要条件和充分条件。
      - 关于 protocol 审查流程：你主张保守的扩展政策——新 protocol 的引入需要
        (a) 先用黄金样本证明现有库确实无法覆盖该场景，
        (b) 给出 pass_rule 的精确形式化定义，
        (c) 跑回归测试确认新 protocol 不破坏已有判定。
        "看起来有用"不是引入新 protocol 的充分理由。

      攻击风格：要求对手给出每个 protocol 的 pass_rule 的精确格式（不接受字符串描述），
      追问 ONLY_PRAGMATIC_PROTOCOL 的判定算法的具体触发条件，
      找出 protocol 库覆盖不足时的具体失败场景，
      用"这个 pass_rule 在边界输入上如何判定"来拆穿模糊设计。

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Ssyram，v3 认知引擎的核心设计者，形式化方法研究者。

      在本议题中，你的核心主张是 protocol 库需要覆盖规范性/解释性命题的常见场景：
      - 你认为最小可用 protocol 库至少需要 4-5 个 protocol_id，
        因为规范性命题（伦理判断）、解释性命题（历史解释）、制度性命题（政策评估）、
        元理论命题（方法论判断）各有不同的证据制度，不能用同一个 pass_rule 覆盖。
      - 关于 pass_rule 格式：你主张结构化谓词优于纯字符串描述，但对于某些领域
        （如伦理判断）需要保留 LLM 判定作为补充——因为形式化谓词的表达能力有限，
        无法捕捉专家共识的所有维度。
      - 关于 ONLY_PRAGMATIC_PROTOCOL 的判定：你认为这个判定需要结合
        (a) synthesize_falsifier() 的失败原因（reason 字段），
        (b) 命题的 domain_kind，
        (c) 候选 protocol 库的匹配度，
        三者综合判断，不能简化为纯算法。
      - 关于 protocol 审查流程：你主张动态扩展——系统运行中发现的新类型命题可以
        触发 protocol 提案流程，经过 3 个月的候选观察期（收集真实场景数据）后
        进入正式库。保守的扩展政策会导致系统性地将可编译命题错误归为 RegulativeIdea。

      攻击风格：要求对手证明"最小 protocol 库"在规范性/解释性领域的实际覆盖率，
      指出纯算法判定 ONLY_PRAGMATIC_PROTOCOL 的盲点（哪些命题会被错误分类），
      要求 Linus 的保守扩展政策给出量化标准（什么叫"证明现有库无法覆盖"）。

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Immanuel Kant，批判哲学创始人。你从认识论角度审查 protocol 库的合法性边界。

      在本议题中，你的核心关切是：
      - protocol 类型的 accept_test 必须附带显式的 epistemic_status 声明——
        这是 claim_compiler 辩论中已裁定的 X1 修正版的核心要求。
        你要追问：当前讨论的每个 protocol 候选，其 epistemic_status 是什么？
        "expert_adjudication_v1"对应什么认识论模式？它是经验归纳、先验规范，还是语用约定？
      - ONLY_PRAGMATIC_PROTOCOL 的判定触及一个根本性认识论问题：
        什么条件下一个命题"本质上只能用 protocol 而非经验证伪"？
        这个判定的判据本身需要认识论辩护，不能仅仅是"synthesize_falsifier() 失败了"。
        你要区分：(a) 当前技术无法构造证伪器（偶然限制），(b) 该命题在认识论上不可经验证伪（本质限制）。
      - 关于 protocol 审查流程：每个新 protocol 的引入不仅是技术问题，
        也是认识论承诺——它隐含地宣称"这类判定方式具有认识论合法性"。
        审查标准应该包含认识论维度：新 protocol 的 epistemic_status 是什么？
        它的 pass_rule 是否真的能区分"命题为真"和"命题为假"的世界状态？
      - 你对"最小 protocol 库"的认识论解读：
        最小性不只是工程上的"越少越好"，而是认识论上的"只包含具有充分认识论合法性的 protocol"。
        一个认识论合法性不足的 protocol（如 pass_rule 过于宽松导致无法真正证伪）
        比完全缺失更危险，因为它制造了"已验证"的假象。

      攻击风格：区分"技术上无法证伪"和"认识论上本质不可证伪"，
      追问每个 protocol 候选的认识论地位（不仅是它"做什么"，还要问它"凭什么合法"），
      要求对手对 ONLY_PRAGMATIC_PROTOCOL 的判定给出认识论依据而非仅技术描述。

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 12000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  这是一次严肃的系统设计讨论，不是辩论赛。

  禁止：
  - 纯原则性陈述——每个设计主张必须伴随具体的数据结构、pass_rule 格式或失败场景举例
  - 稻草人攻击——质询中必须引用对手的具体文本
  - 重新讨论 claim_compiler 辩论中已裁定的内容（X1 修正版——统一编译流程、领域差异仅体现在
    accept_test 的谓词类型中、protocol 类型必须有显式 epistemic_status 声明——这些是既定约束）
  - 重新讨论 W/Y/Z 问题的裁定结果（W1 修正版：二值输出+RegulativeIdea 出口；
    Z2 修正版：RegulativeIdea 作为独立输出类型）
  - 车轱辘话（重复已有内容，无认知推进）

  每次发言必须包含：
  1. 对 A/B/C/D 四个问题之一的明确立场（有具体数据结构或 pass_rule 格式支撑）
  2. 对至少一个对手论点的精确攻击（指名，引用文本，指出具体缺陷）

  所有主张必须附可推翻条件（什么反例能推翻你的设计选择）。

round1_task: |
  第一轮：选择 A/B/C/D 四个设计决策中你认为最关键的一个，给出完整立场。

  A = protocol_id 的最小集合（最少几个、分别是什么、覆盖哪些场景）
  B = pass_rule 的格式（字符串描述 vs 结构化谓词 vs LLM 判定，或组合方案）
  C = ONLY_PRAGMATIC_PROTOCOL 的判定算法（如何从 CompileError 内容自动判定）
  D = 新 protocol 的审查流程（扩展条件、审查标准、何时可引入）

  必须包含：
  1. 你主张的具体设计选择（可实现的，不是原则性陈述）
  2. 支撑该选择的最强论据（含至少一个具体失败场景）
  3. 你方案的已知弱点及其缓解措施
  4. 至少一个 protocol 的完整规格（含 protocol_id、pass_rule 格式、epistemic_status 声明）
  5. 对至少一个对手可能立场的预攻击

middle_task: |
  质询轮：吸收第一轮攻击后的回应与深化。

  必须包含：
  1. 回应对你方案的最强攻击（承认击中的部分，反驳打偏的部分）
  2. 对 ONLY_PRAGMATIC_PROTOCOL 判定算法的完整描述：
     - 输入：CompileError 的哪些字段？
     - 判定逻辑：什么条件组合触发 ONLY_PRAGMATIC_PROTOCOL？
     - 输出：触发后如何影响 clarity_compile() 的返回路径？
  3. 对第三个对手（尚未深入攻击的）给出精确质询
  4. 一个具体的编译 trace：给出一个规范性/解释性命题，展示你的 protocol 库如何处理它，
     包括 accept_test 的完整结构（含 protocol_id、pass_rule 实例、epistemic_status）

final_task: |
  (由辩论引擎自动处理，本 topic 只有 2 轮 + 质询)

judge_instructions: |
  裁判必须产出两部分内容：

  **第一部分：白话版结论**
  对 A/B/C/D 四个问题分别给出裁定，每个裁定必须包含：
  - 用日常语言解释这个设计问题是什么（不熟悉编程的人也能理解）
  - 裁定结果（哪个方案，或第三方案）
  - 至少一个具体例子：当 lower_accept_test() 处理某个规范性/解释性命题时，
    不同设计选择会导致什么不同的具体行为
  - 什么场景下这个裁定可能需要修正
  - 一句话总结

  风格要求：像向一个智慧但非技术背景的哲学系教授解释——
  他能理解"认识论地位""证伪力""制度化判断"等概念，
  但不熟悉 TypeScript 或 LLM 系统实现细节。

  **第二部分：可实现性摘要**
  - protocol 库最小可用规格（每个 protocol 的完整规格：protocol_id、pass_rule 格式、
    epistemic_status、适用范围、排除场景）
  - ONLY_PRAGMATIC_PROTOCOL 判定算法的完整规格（输入字段、判定逻辑、输出路径）
  - 新 protocol 审查流程的实现规格（触发条件、审查标准、准入门槛）
  - 标注实现难度最高的 1-2 个子问题及其风险

  对 A/B/C/D 每个问题必须给出明确的最终裁定，不得搁置。
---

# v3 认知引擎：lower_accept_test() 的 protocol 库最小可用规格

## 一、整体系统背景（完整概述）

本议题是 claim_compiler 辩论的续集，聚焦于一个在上一轮辩论中被识别为"实现难度最高"的子模块：`lower_accept_test()` 中的 protocol 类型处理。为使读者无需阅读其他文件就能完整理解讨论背景，以下先概述 v3 整体架构，再说明 claim_compiler 的裁定结论，最后聚焦到本议题的具体决策点。

### 1.1 v3 系统的目标与整体架构

v3 认知引擎旨在处理开放式、有争议的复杂问题（如"AI 是否应该开源""远程办公是否提高生产力"），产出多视角、辩护完备的答案。

v3 采用**两层分离架构**：

**Layer 1（问题级处理层）**——薄状态机，将开放问题分解为多条可验证的候选命题：

```
QN（QuestionNormalizer，问题规范化）
  → MB（MacroBreadth，宏观广度探索）
  → CC（ClarityCompiler，清晰度编译）    ← claim_compiler 负责此节点
  → D2（Layer2Dispatch，派发到 Layer 2）
  → PA（PrecisionAggregator，精度聚合）
  → RB（RepairBreadth，修复回退，可选）
  → AS（AnswerSynthesis，答案综合）
```

**Layer 2（命题级处理层）**——对每条具体的 `TestableClaim` 进行深度验证：

```
S1(Clarify) → S2(Depth) → S3(Precision) → S4(DepthProbe) ↔ S5(BreadthProbe)
  → S6(Verified) | S7(Suspended) | S8(SchemaChallenge)
```

### 1.2 claim_compiler 辩论的裁定结论（必读背景）

上一轮辩论（claim_compiler）裁定了 `clarity_compile()` 的实现方案，以下为本议题直接继承的裁定结论：

**W1 修正版（严格/宽松平衡）**：二值输出。`clarity_compile()` 的输出只有两种合法状态：
- `TestableClaim`（编译成功，送入 Layer 2）
- `CompileError`（编译失败，送回 `repair()`）

不存在"半成品"输出。此外增设第三类非命题对象：
- `RegulativeIdea`（调节性理念，不进入 Layer 2，由 RB 节点消费以生成新草稿）

**X1 修正版（跨领域适应）**：统一编译流程，领域差异仅体现在 `accept_test` 的谓词类型中。具体地：
- 统一四步编译流程：`normalize → check_single_proposition → synthesize_falsifier → lower_accept_test`
- 领域差异不通过注册表（`DomainSchemaRegistry`）体现，而是通过 `accept_test` 谓词中的 `protocol` 类型体现
- **关键约束（本议题的直接来源）**：每个 `protocol` 类型的 `accept_test` 必须附带显式的 `epistemic_status` 声明，标明它是"经验性证伪条件"（`empirical_falsification`）还是"制度化判断程序"（`procedural_judgment`）

**Z2 修正版（不可编译命题处置）**：`RegulativeIdea` 作为独立输出类型，不进入 Layer 2。

已裁定的完整类型系统参见 claim_compiler 辩论的可实现性摘要，核心相关部分如下：

```typescript
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
  evidence_bindings: string[];
  indeterminate_when: string[];
};

type RegulativeIdea = {
  idea_id: string;
  statement: string;
  domain_kind: "empirical" | "normative" | "interpretive" | "mixed";
  reason_no_schema: "NO_BRIDGE_TO_OBSERVABLE" | "ONLY_PRAGMATIC_PROTOCOL";
  decomposition_hints: string[];
  stage_trace: StageTrace;
};
```

注意 `reason_no_schema` 有两种取值：
- `NO_BRIDGE_TO_OBSERVABLE`：`synthesize_falsifier()` 失败，原因是无法找到可观测的桥接图型
- `ONLY_PRAGMATIC_PROTOCOL`：`lower_accept_test()` 失败，失败原因是"本质上只能用 protocol 而非经验证伪"

这个区分是本议题的核心决策点之一：什么时候 `lower_accept_test()` 应该判定为 `ONLY_PRAGMATIC_PROTOCOL` 并走 `RegulativeIdea` 出口？

### 1.3 lower_accept_test() 在编译流水线中的位置

`lower_accept_test()` 是 `clarity_compile()` 四步流水线的最后一步：

```
Stage 1: normalize → extract_structure()
Stage 1b: check_single_proposition()
Stage 2: synthesize_falsifier()           ← 如果这里失败，走 NO_BRIDGE_TO_OBSERVABLE
Stage 3: lower_accept_test()              ← 本议题焦点
```

**前提条件**：`lower_accept_test()` 被调用时，`synthesize_falsifier()` 已成功（即已有 `falsifier.description`）。它的任务是将这个自然语言的 falsifier 描述"降低"为机器可检查的 `AcceptTest` 谓词。

**失败情形**：
- `NO_ACCEPT_TEST`：falsifier 存在，但无法生成机器可检查的判定谓词（缺少阈值/时间窗/样本约束/判定协议）
- `UNBOUND_OBSERVABLE`：falsifier 有逻辑结构，但无法绑定到可观测指标
- `ONLY_PRAGMATIC_PROTOCOL`：即便使用 protocol 类型，也只能得到名义上存在但实质上无证伪力的判定标准——此时应走 `RegulativeIdea` 出口

---

## 二、本议题的核心决策点

### 决策点 A：protocol_id 的最小集合

当前 `PredicateExpr` 中的 `protocol` 类型只有一个 `protocol_id` 字段，但没有规定协议库应该包含哪些协议。

**已知的场景需求**：
- 规范性命题（如"增税是否公平"）：专家共识？多方协商？伦理委员会裁定？
- 解释性命题（如"工业革命主要由技术进步驱动"）：史学家共识？文献数量统计？
- 政策评估命题（如"该政策是否符合公共利益"）：利益相关方调查？政策影响评估框架？
- 方法论命题（如"贝叶斯方法在此场景下更优"）：同行评审？基准测试比较？

**未决问题**：最小可用 protocol 库需要几个 protocol_id？各自覆盖什么场景？

### 决策点 B：pass_rule 的格式

当前类型定义中 `pass_rule` 是 `string`。但字符串格式有很大的设计空间：

- **纯字符串描述**（如 `"3/5 domain experts agree"`）：直观，但机器判定困难
- **结构化谓词**（如 `{ type: "consensus", threshold: 0.6, panel_size: 5, panel_spec: "domain_expert" }`）：可机器执行，但表达能力受限
- **LLM 判定**（如 `{ type: "llm_eval", prompt_template: "...", pass_threshold: 0.8 }`）：灵活，但引入不确定性
- **分层方案**：先尝试结构化谓词，无法表达时降级到 LLM 判定，同时记录 `epistemic_status`

**关键张力**：如果 `pass_rule` 格式过于宽松，`protocol` 类型的 accept_test 就失去了证伪力，变成一个"总是可以通过的形式"。

### 决策点 C：ONLY_PRAGMATIC_PROTOCOL 的判定算法

当前编译流水线伪代码显示：

```
if accept.failed:
  if accept.reason == "ONLY_PRAGMATIC_PROTOCOL":
    return REGULATIVE_IDEA { reason_no_schema: "ONLY_PRAGMATIC_PROTOCOL", ... }
```

但 `ONLY_PRAGMATIC_PROTOCOL` 的判定逻辑本身未被规定。这个判定需要回答：

- 输入：依赖 CompileError 中的哪些字段？`failure_stage`、`missing_fields`、还是需要新字段？
- 触发条件：什么情况下判定为"本质上只能用 protocol 而非经验证伪"？
  - 选项 1：纯算法——基于 `domain_kind`、`failure_stage` 等结构化字段的规则组合
  - 选项 2：LLM 辅助判定——让 LLM 分析 falsifier 描述，判断是否存在经验桥接可能性
  - 选项 3：protocol 库匹配度——如果当前 protocol 库中最佳匹配项的置信度低于阈值，触发 ONLY_PRAGMATIC_PROTOCOL
- 风险：错误触发（将可编译命题归为 RegulativeIdea）vs 漏触发（将本质上无证伪力的命题编译为 TestableClaim）

### 决策点 D：新 protocol 的审查流程

随着系统处理的命题类型增加，协议库需要扩展。但扩展的条件和标准是什么？

- **保守扩展**：需要黄金样本证明现有库确实无法覆盖，且新 protocol 有精确 pass_rule 定义和回归测试
- **动态扩展**：候选观察期制度（收集真实场景数据），但需要定义观察期结束的判断标准
- **认识论审查**：每个新 protocol 的 epistemic_status 必须被论证，而不仅是技术规格

---

## 三、四个核心设计问题（本轮辩论焦点）

### 问题 A：protocol_id 的最小集合

**候选方案**：
- A1（最小主义）：只有 1-2 个高度抽象的 protocol（如 `expert_consensus_v1`、`institutional_review_v1`），具体参数通过 `pass_rule` 的结构化字段定制
- A2（中等覆盖）：4-5 个 protocol，按认识论类型分类（规范性、解释性、制度性、方法论性、混合性）
- A3（全覆盖）：8-10 个 protocol，细分到具体领域（伦理委员会、史学共识、政策影响评估等）

**关键张力**：A1 维护成本低但 pass_rule 参数化设计复杂；A3 覆盖全但维护成本高且过度分类化

### 问题 B：pass_rule 的格式

**候选方案**：
- B1：纯字符串描述——灵活但机器执行困难
- B2：结构化谓词——可机器执行但表达能力受限
- B3：LLM 判定——灵活但引入不确定性
- B4：分层方案——先结构化谓词，无法表达时降级到 LLM 判定，并记录降级原因

**关键张力**：证伪力（越结构化越强）vs 表达能力（越灵活越强），且 B3/B4 引入的 LLM 判定本身可能漂移

### 问题 C：ONLY_PRAGMATIC_PROTOCOL 的判定算法

**候选方案**：
- C1：纯规则——基于 `domain_kind`、`failure_stage`、`missing_fields` 的条件组合（无 LLM）
- C2：LLM 辅助——LLM 分析 falsifier 描述，判断经验桥接可能性，给出置信度分数
- C3：protocol 匹配度——计算现有 protocol 库中最佳匹配项的匹配置信度，低于阈值触发 ONLY_PRAGMATIC_PROTOCOL
- C4：C1+C3 组合——先用规则排除明显情况，再用匹配度处理模糊情况

**关键张力**：C1 稳定但可能覆盖不足；C2 灵活但引入不确定性；C3 依赖 protocol 库质量形成循环依赖

### 问题 D：新 protocol 的审查流程

**候选方案**：
- D1（保守）：黄金样本证明覆盖缺口 + 精确 pass_rule + 回归测试，三者缺一不可
- D2（动态）：候选观察期（3 个月，收集真实场景数据）+ 准入投票，类似 RFC 流程
- D3（认识论优先）：新 protocol 必须先通过认识论审查（epistemic_status 论证），再进行技术审查
- D4（D1+D3 结合）：技术审查（D1）+ 认识论审查（D3），缺一不可

**关键张力**：过于保守的审查会导致系统性错误分类；过于宽松的审查会引入认识论上不合法的 protocol

---

## 四、开放性陈述

以上四个问题没有预设答案。Protocol 库的设计是一个典型的"最小可用 vs 完整覆盖"权衡问题，同时叠加了工程实现和认识论合法性两个维度的约束。

对于辩手：请基于你的设计哲学，对你认为最关键的问题给出具体的、可实现的立场。每个立场必须给出至少一个 protocol 的完整规格（`protocol_id`、`pass_rule` 的具体格式、`epistemic_status` 声明、适用范围），不接受纯原则性陈述。

`lower_accept_test()` 的 protocol 库是整个 claim_compiler 中最依赖领域知识的子模块。它的设计直接决定了：规范性和解释性命题能否被诚实地编译（而非被错误地归为 RegulativeIdea 或被强行塞入不合适的 TestableClaim）。
