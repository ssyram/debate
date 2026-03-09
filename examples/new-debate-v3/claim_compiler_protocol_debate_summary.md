# v3 认知引擎：lower_accept_test() 的 protocol 库最小可用规格 裁判总结

> 2026-03-09T19:06:33.220476

# 裁判裁定书

---

## 第一部分：白话版结论

---

### A. Protocol 库的最小集合：应该有几种"验证程序"？

**问题是什么：**
想象你在建一座法院系统。有些案件是刑事案件（需要物证、DNA），有些是民事纠纷（需要合同、证人），有些是宪法审查（需要法理论证）。问题是：这座法院应该只设一个通用法庭，还是应该从一开始就设几个专门法庭？

在我们的系统中，"protocol"就是验证某类命题的程序。"最低工资提高会减少就业"需要的验证方式（查数据、做实验）和"强制开源高风险AI是不负责任的"需要的验证方式（伦理审议、多维度价值权衡）完全不同。

**裁定：采纳 Ssyram 的 A2 方案（4-5个基础 protocol），但受康德审查约束。**

**理由：** Ssyram 的核心论据无法反驳——不同类型命题的"证据制度"在认识论上确实互斥。用同一个"5人投票过半数"去验证历史解释和伦理判断，就像用刑事法庭的"排除合理怀疑"标准去审理离婚案——不是不能运行，而是运行结果没有认识论意义。Linus 主张的 2-3 个极简集合虽然工程上更安全，但他自己也承认需要 `fairness_assessment_binary_v1` 这类专门 protocol，实际上已经在向 4 个靠拢。

**具体例子：**
当 `lower_accept_test()` 处理"罗马帝国的衰落主要由经济崩溃驱动"这个解释性命题时：
- 如果只有一个通用 `expert_consensus_v1`：系统会召集5个"专家"投票，但不会要求他们基于史料交叉印证来论证，投票结果可能只反映当下流行观点，而非历史学方法论下的合理判断。
- 如果有专门的 `interpretive_consensus_v1`：系统会要求评审者明确引用史料证据、声明方法论立场、记录异议意见，投票结果才有历史学意义上的认识论分量。

**何时需要修正：** 如果实际运行中发现，4-5 个 protocol 中有两个的回归测试结果高度重叠（比如 `normative_eval_v1` 和 `institutional_audit_v1` 在所有测试用例上行为一致），则应合并。

**一句话总结：** 不同类型的知识需要不同类型的验证程序，正如不同类型的案件需要不同类型的法庭。

---

### B. Pass_rule 的格式：验证规则应该多严格？

**问题是什么：**
这个问题类似于：法官判案时，判决依据应该写成什么样？是必须严格引用法条编号和量刑标准（完全结构化），还是可以在法条不够用时写一段"本院认为"的自由裁量（允许人为补充判断）？

在系统中，`pass_rule` 就是"这个命题通过验证的具体标准"。争论焦点是：这个标准能不能包含需要 AI 来解读的模糊部分？

**裁定：采纳 Linus 的 B2 严格结构化方案为基底，但接受 Ssyram 修正版 B4 中"LLM 仅做提取、不做判定"的有限补充。**

**理由：** 这是本次辩论中最精彩的交锋。Linus 的核心攻击——"这不是形式化，这是带引号的自然语言"——击中了 Ssyram 第一版方案的要害。但 Ssyram 的修正版做了关键让步：LLM 只负责从非结构化文本中提取枚举值（如将历史文献映射为 `'dominant' | 'secondary' | 'negligible'`），而 pass/fail 的最终判定由机器执行的 AST 谓词完成。这个修正版在认识论上是诚实的——它承认真实世界的证据往往是非结构化的（论文、史料、政策文件），但坚持判定标准本身必须是机器可执行的。

Linus 对"LLM 漂移"的担忧完全合理，因此必须加上他要求的约束：LLM 提取步骤必须有回归测试集、提取结果必须是封闭枚举、提取失败必须显式报错而非静默降级。

**具体例子：**
当处理"强制开源高风险AI模型是不负责任的"这个规范性命题时：
- 纯 Linus 方案：如果当前没有能完全结构化表达"不负责任"判定标准的 schema，系统直接返回失败。这在认识论上是诚实的，但在实践中意味着系统对几乎所有规范性命题都无能为力。
- Ssyram 修正版：LLM 从伦理文献中提取 `harm_potential: 'high' | 'medium' | 'low'`、`mitigation_feasibility: 'high' | 'medium' | 'low'` 等枚举值，然后机器执行 `harm_potential == 'high' && mitigation_feasibility == 'low' → supports_claim`。判定标准是透明的、可回归测试的，LLM 只是"翻译员"而非"法官"。
- 关键区别：如果 LLM 提取结果不稳定（同一文献两次提取出不同枚举值），系统必须报错 `EXTRACTION_UNSTABLE`，而非静默采用任一结果。

**何时需要修正：** 如果回归测试显示 LLM 提取步骤的一致性低于 90%（同一输入多次提取结果不同），则该 protocol 的 LLM 提取部分必须冻结或移除，退回纯结构化方案。

**一句话总结：** 判定标准必须是机器可执行的铁律，但允许用 AI 做受控的"证据翻译"——翻译员不能改判决书。

---

### C. ONLY_PRAGMATIC_PROTOCOL 的判定：系统何时应该承认"我只能走程序，不能验真假"？

**问题是什么：**
这是系统的"认识论谦逊"机制。有些命题（如"水在100°C沸腾"）可以通过观察世界来验证真假；有些命题（如"死刑是不正义的"）在原则上无法通过观察来证伪，只能通过某种制度化的审议程序来形成判断。系统需要区分这两种情况，并在遇到后者时诚实地说："我无法验证这个命题的真假，我只能告诉你，按照某个审议程序，结论是这样的。"

问题是：这个区分应该怎么做？纯靠算法？还是需要 AI 参与判断？

**裁定：采纳 Linus 的 C1 纯算法判定框架，但补充康德的认识论约束作为必要前置条件。**

**理由：** Linus 给出了目前为止最清晰的判定规则：

1. 失败发生在 `lower_accept_test` 阶段（不是更早）
2. 存在可观察绑定（命题不是完全脱离经验的）
3. 证伪器形状为 `procedural_only`（无法构造经验性反例）
4. 所有候选 protocol 要么 schema 不匹配且缺的是制度字段，要么需要 LLM 语义

这四个条件全部可机器判定，不依赖 LLM。这正是 Linus 的核心洞见：如果判定"是否需要走程序"这件事本身就需要 LLM 的主观判断，那整个失败分支就失去了可信度。

但康德的补充不可或缺：仅靠"当前 schema 表达不了"不足以区分"技术限制"和"认识论限制"。因此，每个 protocol 必须携带 `truth_relation` 元数据。当系统输出 `ONLY_PRAGMATIC_PROTOCOL` 时，它不仅要报告"没有匹配的 protocol"，还要报告"匹配到的最近 protocol 的 `truth_relation` 是 `tracks_reasoned_consensus` 而非 `tracks_world_state`"——这才是认识论上诚实的失败。

**具体例子：**
当处理"最低工资提高到15美元会减少就业"时：
- `synthesize_falsifier()` 成功：可以构造"如果就业数据显示X则命题被削弱"的证伪器
- `lower_accept_test()` 也应该成功：这是经验性命题，有统计方法可以验证
- 结果：正常编译，不走 `ONLY_PRAGMATIC_PROTOCOL`

当处理"强制开源高风险AI模型是不负责任的"时：
- `synthesize_falsifier()` 部分成功：可以找到一些可观察绑定（如"开源后是否导致了安全事故"），但核心的"不负责任"判断无法还原为经验观察
- `lower_accept_test()` 失败：`falsifier_shape = "procedural_only"`，最近匹配的 protocol 是 `normative_eval_v1`，其 `truth_relation = "tracks_reasoned_consensus"`
- 结果：输出 `ONLY_PRAGMATIC_PROTOCOL`，附带说明"此命题的验证本质上是制度化审议，而非经验证伪"

**何时需要修正：** 如果出现一类命题，其 `falsifier_shape` 被算法判定为 `procedural_only`，但后来发现存在可行的经验证伪方案（例如某个曾被认为纯规范性的命题，后来找到了可操作的经验指标），则需要更新 `falsifier_shape` 的判定逻辑。Linus 自己也给出了可推翻条件，这是好的。

**一句话总结：** "我不知道"这句话本身必须是确定性的——系统承认无能的方式不能依赖于另一个不确定的判断。

---

### D. 新 protocol 的审查流程：谁来决定新的"验证程序"能不能入库？

**问题是什么：**
这就像问：谁有权设立新的法庭类型？如果任何人都能随意设立一个"AI伦理特别法庭"并宣称它有权审理某类案件，整个司法体系的公信力就会崩溃。但如果设立新法庭的门槛高到不可能，系统就会因为"没有合适的法庭"而拒绝审理越来越多的案件。

**裁定：采纳康德的四闸门审查框架，但接受 Ssyram 关于"动态观察期"的修正——新 protocol 可以在沙箱中试运行，但不进入生产编译路径。**

**理由：** 康德的核心论点在认识论上无可辩驳：如果引入新 protocol 的机制本身不合法，那么通过该 protocol 产生的所有判定都继承了这种不合法性。他的四闸门（认识论合法性审查、越权测试、黄金样本测试、可推翻条件声明）构成了一个完整的准入框架。

但 Ssyram 的质询也击中了要害：如果完全禁止新 protocol 接触真实数据，那"越权测试"和"缺口证明"就只能基于臆想的测试用例，这本身就不够诚实。因此我裁定：新 protocol 可以进入**影子模式**（shadow mode）——接收真实输入、产生判定结果，但这些结果不进入正式编译输出，仅用于收集回归数据。当影子模式运行满足预设的统计门槛（如处理了至少 N 个真实命题、回归一致性达到 X%）后，才能申请正式准入。

**具体例子：**
假设有人提议增加一个 `aesthetic_judgment_v1` protocol，用于处理"毕加索的《格尔尼卡》是20世纪最重要的反战艺术作品"这类命题：
- 闸门一（认识论合法性）：提议者必须声明 `truth_relation = "tracks_reasoned_consensus"`，并论证为什么美学判断可以通过制度化审议产生有意义的结论。
- 闸门二（越权测试）：必须证明现有的 `normative_eval_v1` 和 `interpretive_consensus_v1` 确实无法覆盖美学判断（例如，美学判断需要的"审美经验"维度在现有 protocol 中没有对应的评估框架）。
- 闸门三（黄金样本）：提供至少 5 个正例和 5 个反例，展示该 protocol 能正确处理"应该通过"和"应该失败"的美学命题。
- 闸门四（可推翻条件）：声明"如果回归测试显示该 protocol 与 `interpretive_consensus_v1` 在所有测试用例上行为一致，则应合并而非独立存在"。
- 影子模式：通过四闸门后，进入 3 个月影子运行，收集真实数据。

**何时需要修正：** 如果影子模式的门槛设置过高（比如要求处理 1000 个真实命题才能申请准入），导致实际上没有任何新 protocol 能通过，则需要降低门槛。具体数字应基于系统实际流量确定。

**一句话总结：** 新的验证程序必须先证明自己有资格验证别人，但这个证明过程不能完全脱离真实世界。

---

## 第二部分：可实现性摘要

### 1. Protocol 库最小可用规格

| 字段 | `empirical_test_v1` | `normative_eval_v1` | `interpretive_consensus_v1` | `institutional_audit_v1` | `meta_methodology_v1` |
|---|---|---|---|---|---|
| **protocol_id** | `empirical_test_v1` | `normative_eval_v1` | `interpretive_consensus_v1` | `institutional_audit_v1` | `meta_methodology_v1` |
| **pass_rule 格式** | 纯结构化谓词：统计阈值 + 数据源绑定 | 结构化审议框架 + LLM 枚举提取（受控） | 结构化审议框架 + LLM 文献提取（受控） | 结构化合规检查清单 | 结构化方法论一致性检查 |
| **epistemic_status** | `empirical_falsification` | `procedural_judgment` | `procedural_judgment` | `procedural_judgment` | `procedural_judgment` |
| **truth_relation** | `tracks_world_state` | `tracks_reasoned_consensus` | `tracks_reasoned_consensus` | `tracks_rule_compliance` | `tracks_reasoned_consensus` |
| **适用范围** | 可经验证伪的事实性命题 | 涉及价值判断的规范性命题 | 涉及因果解释的历史/社会科学命题 | 涉及制度/政策合规性的命题 | 涉及研究方法论本身合理性的命题 |
| **排除场景** | 纯规范性命题、纯定义性命题 | 可直接经验证伪的事实命题 | 可直接经验证伪的事实命题 | 非制度性的纯学术命题 | 非方法论层面的实质性命题 |
| **pass_rule 核心要素** | `{data_source, statistical_test, significance_level, effect_size_threshold}` | `{panel_spec, dimension_list, extraction_schema(enum), pass_expression(AST), reason_giving_required:true, dissent_record_required:true}` | `{panel_spec, source_requirement, extraction_schema(enum), pass_expression(AST), reason_giving_required:true, dissent_record_required:true}` | `{checklist_id, compliance_dimensions, binary_pass_per_item, aggregate_threshold}` | `{methodology_criteria, peer_review_spec, consistency_check_expression}` |
| **misuse_if_treated_as** | — | `empirical_falsification` | `empirical_falsification` | `empirical_falsification` | `empirical_falsification` |

### 2. ONLY_PRAGMATIC_PROTOCOL 判定算法完整规格

**输入字段：**
```typescript
type OPPInput = {
  compile_error: {
    failure_stage: "synthesize_falsifier" | "lower_accept_test";
    observable_bindings_found: number;
    falsifier_shape: "thresholdable" | "comparative" | "procedural_only";
    protocol_candidates: Array<{
      protocol_id: string;
      schema_match: boolean;
      missing_rule_fields: string[];
      requires_llm_semantics: boolean;
      truth_relation: "tracks_world_state" | "tracks_rule_compliance" | "tracks_reasoned_consensus";
    }>;
  };
  claim_metadata: {
    domain_kind: "empirical" | "normative" | "interpretive" | "institutional" | "meta_methodological" | "mixed";
  };
};
```

**判定逻辑（纯算法，无 LLM 调用）：**
```
输出 ONLY_PRAGMATIC_PROTOCOL 当且仅当以下四个条件全部满足：

(1) failure_stage == "lower_accept_test"
    （证伪器构造至少部分成功，失败发生在验证程序匹配阶段）

(2) observable_bindings_found > 0
    （命题不是完全脱离经验的纯先验命题）

(3) falsifier_shape == "procedural_only"
    （无法构造经验性阈值或比较性反例）

(4) 对于所有 protocol_candidates：
    (schema_match == false AND missing_rule_fields 中至少一项属于 INSTITUTIONAL_FIELDS)
    OR requires_llm_semantics == true
    
    其中 INSTITUTIONAL_FIELDS = ["panel_spec", "deliberation_procedure", 
    "reason_giving_required", "dissent_record_required", "dimension_list"]

附加输出要求：
- 必须报告最近匹配 protocol 的 truth_relation
- 如果最近匹配 protocol 的 truth_relation == "tracks_world_state"，
  则不得输出 ONLY_PRAGMATIC_PROTOCOL，改为输出 NO_ACCEPT_TEST
  （这意味着可能是 schema 不足而非认识论限制）
```

**输出路径：**
- 四条件全满足 + 附加检查通过 → `ONLY_PRAGMATIC_PROTOCOL`
- 条件(1)不满足 → `SYNTHESIZER_FAILURE`（更早阶段的失败）
- 条件(2)不满足 → `NO_OBSERVABLE_BINDING`（纯先验命题，不可编译）
- 条件(3)不满足 → `NO_ACCEPT_TEST`（可能存在经验性验证方案但当前未实现）
- 条件(4)不满足 → `NO_ACCEPT_TEST`（protocol 库可能需要扩展，但不是认识论限制）
- 附加检查不通过 → `NO_ACCEPT_TEST`

### 3. 新 Protocol 审查流程实现规格

**触发条件：**
- 系统累计输出 `NO_ACCEPT_TEST`（非 `ONLY_PRAGMATIC_PROTOCOL`）超过阈值 T 次，且这些失败命题聚类到同一 `domain_kind`
- 或：人工提交新 protocol 提案

**四闸门审查标准：**

| 闸门 | 审查内容 | 准入门槛 | 实现方式 |
|---|---|---|---|
| G1: 认识论合法性 | `epistemic_status`、`truth_relation`、`misuse_if_treated_as` 三件套完整且自洽 | 三件套全部填写；`truth_relation` 与 `pass_rule` 结构一致（如声明 `tracks_world_state` 则 pass_rule 不得包含 panel 投票） | 结构化 schema 校验 + 人工审查 |
| G2: 越权测试 | 现有 protocol 库确实无法覆盖目标命题类型 | 提供 ≥5 个命题样本，证明所有现有 protocol 的 `schema_match == false` 且缺失字段不可通过扩展现有 protocol 解决 | 自动化匹配 + 人工确认 |
| G3: 黄金样本测试 | 新 protocol 能正确处理正例和反例 | ≥5 正例 + ≥5 反例 + ≥3 边界用例，全部通过 | 自动化回归测试 |
| G4: 可推翻条件声明 | 声明在什么条件下该 protocol 应被移除或合并 | 至少声明 1 个可推翻条件，且该条件是可机器检测的 | 结构化声明 + 人工审查 |

**影子模式规格：**
- 通过四闸门后进入影子模式，接收真实输入但不影响正式编译输出
- 影子模式持续时间：≥30 天或处理 ≥100 个真实命题（以先到者为准）
- 准入正式库条件：影子模式中回归一致性 ≥95%（同一输入多次执行结果一致）；与现有 protocol 的判定结果差异率 ≥20%（证明确实覆盖了新领域而非重复）

### 4. 实现难度最高的子问题及风险

**子问题 1：LLM 枚举提取的一致性保证（难度：极高）**

这是 B 裁定中"LLM 仅做提取"方案的核心风险。当 LLM 从非结构化文本中提取枚举值时（如将历史文献映射为 `'dominant' | 'secondary' | 'negligible'`），不同的 LLM 版本、不同的上下文窗口、甚至同一 LLM 的不同调用都可能产生不同结果。

**风险：** 如果提取一致性无法达到 90% 以上，整个"LLM 做翻译员"的架构就会退化为"LLM 做法官"，Linus 的担忧就会成真。

**缓解措施：** 每个 protocol 的 `extraction_schema` 必须附带回归测试集（≥20 个标注样本）；提取步骤必须执行 3 次取多数投票；一致性低于阈值时自动触发 `EXTRACTION_UNSTABLE` 错误而非静默降级。

**子问题 2：`falsifier_shape` 的自动判定（难度：高）**

`ONLY_PRAGMATIC_PROTOCOL` 的判定依赖于 `falsifier_shape == "procedural_only"` 这个条件，但如何自动判定一个命题的证伪器形状是 `thresholdable`、`comparative` 还是 `procedural_only`，本身就是一个需要语义理解的任务。

**风险：** 如果 `falsifier_shape` 的判定本身依赖 LLM，就会出现 Linus 警告的循环依赖——用 LLM 来判定"是否需要 LLM"。

**缓解措施：** `falsifier_shape` 应基于 `synthesize_falsifier()` 的结构化输出来推断，而非独立调用 LLM。具体而言：如果 `synthesize_falsifier()` 成功产生了包含数值阈值的证伪器 → `thresholdable`；如果产生了比较性证伪器 → `comparative`；如果只产生了"需要专家审议"类型的输出 → `procedural_only`。这要求 `synthesize_falsifier()` 的输出本身是强类型的，这是上游的设计约束。