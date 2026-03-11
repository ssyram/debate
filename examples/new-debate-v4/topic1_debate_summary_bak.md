# v4 认知引擎：整体系统设计的自由探索 裁判总结

> 2026-03-11T12:24:40.398353

# 最终裁定

## 第一部分：整体设计方案

### 1. 系统总体架构

系统是一个**带有非确定性运算单元（LLM）的有向无环图（DAG）状态空间搜索系统**，由一个确定性的中央维护器驱动，多个无状态 LLM worker 执行具体推理任务。

**核心原则：维护器是唯一状态写入者；LLM 是纯函数式 worker；所有 LLM 输出在写入前必须通过确定性协议层。**

#### 1.1 组件清单与职责边界

**中央维护器（Maintainer）**——纯代码实现，非 LLM
- 持有唯一权威状态（DAG + 元数据）
- 遍历 DAG 找到待处理节点，组装上下文，派发给 worker
- 接收 worker 提案，经协议层验证后写入 DAG
- 执行调度决策（基于 UCT 或优先级队列）
- 执行终止判定（基于可计算的停止策略）

**广度引擎（Breadth Engine）**——LLM worker，无状态
- 输入：宏观组件 + 约束集
- 输出：微观组件列表（子问题分解、备选方案枚举）
- 纯函数签名：`(MacroComponent, Constraints) → List<MicroComponent>`

**深度引擎（Depth Engine）**——LLM worker，无状态
- 输入：单个节点 + 其直接依赖的上下文摘要
- 输出：证明步骤、定义精化、假设显式化
- 纯函数签名：`(Node, ContextPack) → ProofTree | RefinedDefinition | ExplicitAssumptions`

**攻击引擎（Attack Engine）**——LLM worker，无状态
- 输入：待攻击节点 + 其声明的假设与依赖
- 输出：结构化反例（必须指明被攻击的前提、构造的反例情境、推导出的矛盾）
- 纯函数签名：`(TargetNode, AssumptionSet) → List<CounterExample>`

**裁判引擎（Judge Engine）**——LLM worker，无状态，仅用于对抗性裁定
- 输入：固定证据包（被攻击节点 + 反例 + 术语表）
- 输出：三值判定（ConflictConfirmed / NoConflictFound / Contested）
- 多次采样（N=3, Temperature=0.2），按表决规则输出

**确定性协议层（Protocol Layer）**——纯代码，维护器的前置门控
- 所有 worker 输出在写入 DAG 前必须通过此层
- 执行硬验证（schema、引用闭合、无环、字段完整）
- 硬验证失败 → 拒绝写入，生成修复 issue，worker 重试（上限 3 次）

#### 1.2 权威状态结构

```
DAG 节点类型：
  - Objective        （目标定义，含可计算约束与不可计算理念的分离）
  - Artifact         （方案片段/主张/定义/假设/证据）
  - Issue            （待解决问题）
  - ConflictNode     （攻击产出的冲突记录）
  - RegulativeNote   （不可反例化的理念性判断，不参与存活率计算）

DAG 边类型：
  - DependsOn        （硬依赖：被依赖节点必须 StructurallyOK 以上）
  - RefinesTo        （细化关系：宏观→微观）
  - Contradicts      （冲突关系：攻击引擎产出）
  - SoftReference    （软引用：Hypothesis 之间可互引，但不构成硬前提）

每个 Artifact 携带：
  - assumptions: Vec<Assumption>       （显式假设集）
  - constitutive_status: ConstitutiveStatus  （见下）
  - regulative_score: RegulativeScore        （见下）
  - branch_id: BranchId                      （所属分支）
  - revision: Rev                            （版本号）
```

#### 1.3 双轨状态系统：构成性状态与调节性分数正交

这是本方案最关键的设计决策之一。每个节点同时持有两个正交标签：

**构成性状态（ConstitutiveStatus）**——离散、确定性驱动、决定"可依赖性"
- `Invalid`：结构不合法（硬验证失败、术语偷换被确证、DAG 引用断裂）
- `Draft`：刚写入，尚未经过任何验证
- `StructurallyOK`：硬验证通过、假设显式、依赖闭合、术语表一致
- `Validated{protocol_id, evidence_hash}`：通过外部可重复验证（测试通过、证明检查通过、基准达标）
- `Hypothesis`：结构合格但无外部验证协议可用；永远不得作为硬依赖前提

**调节性分数（RegulativeScore）**——连续、可含 LLM 信号、仅用于资源调度
- survivability（对抗存活率）
- coverage（子问题覆盖度）
- novelty（相对已有节点的信息增量）
- 这些分数**不得**产生任何硬门槛效力

**硬规则：**
- 节点 A 要作为节点 B 的 `DependsOn` 硬依赖 → A 必须 `StructurallyOK` 以上
- 节点要进入最终交付的"主线" → 必须 `Validated` 或明确标注为 `Hypothesis(assumptions=[...])`
- 调节性分数只决定"先算哪个/先看哪个"，不决定"可依赖/可交付"

#### 1.4 工件双轨分类：Verified vs Hypothesis

所有工件分为两类，对应不同的写入规则和依赖规则：

**Verified 工件**
- 必须有非空的、可执行/可复现的 Evidence（测试、基准、证明草图、外部审计记录）
- 只能依赖其他 Verified 工件或显式声明的 Assumption
- ConstitutiveStatus 必须达到 `Validated`
- 可作为硬依赖前提

**Hypothesis 工件**
- 不要求可执行 Evidence，但必须有显式 Assumptions 和 Defeaters（可撤销条件）
- 禁止作为 Verified 工件的硬依赖
- Hypothesis 之间可通过 SoftReference 互引
- ConstitutiveStatus 最高为 `Hypothesis`
- 在最终输出中明确标注为"在假设集 X 下的条件性结论"

#### 1.5 维护器的调度循环

```
loop {
    // 1. 检查全局停止条件
    if stop_policy.should_stop(&workspace) {
        break;  // 输出当前状态 + 未决清单
    }

    // 2. 从 DAG 中选择下一个待处理节点
    //    优先级由 UCT/调节性分数驱动（纯调度，非裁判）
    let next = scheduler.pick_next(&workspace);

    // 3. 根据节点类型和状态，决定派发给哪个 worker
    let task = match next {
        NeedsDecomposition(n) => Task::Breadth(n),
        NeedsProof(n)         => Task::Depth(n),
        NeedsAttack(n)        => Task::Attack(n),
        HasConflict(n)        => Task::Judge(n),
        NeedsClarification(n) => Task::Clarify(n),
    };

    // 4. 组装上下文（只取该节点及直接相邻的边和节点，控制在窗口内）
    let context = context_assembler.pack(&workspace, &task);

    // 5. 派发给 worker，获取提案
    let proposal = worker_pool.execute(task, context);

    // 6. 协议层硬验证
    match protocol_layer.validate(&workspace, &proposal) {
        Ok(valid_proposal) => {
            // 7. 写入 DAG，更新版本号
            workspace.apply(valid_proposal);
        }
        Err(hard_error) => {
            // 8. 生成修复 issue，worker 重试（上限 3 次）
            workspace.create_repair_issue(hard_error, task);
        }
    }
}
```

#### 1.6 攻击与裁判流程

攻击引擎对每个 `StructurallyOK` 以上的节点进行 N 次采样攻击（N 由预算控制）。每个反例必须是结构化的：

```
struct CounterExample {
    target_node: NodeId,
    attacked_premise: ArtifactId,
    scenario: String,           // 构造的反例情境
    derived_contradiction: String, // 推导出的矛盾
}
```

反例通过协议层硬验证后，进入 Judge 流程：

- Judge 接收固定证据包（被攻击节点的定义表 + 假设集 + 反例），N=3 次采样
- 3-0 → `ConflictConfirmed`：在被攻击节点上挂 ConflictNode，降低调节性分数，生成修复 Issue
- 0-3 → `NoConflictFound`：反例被标记为无效，节点调节性分数微升
- 2-1 或 1-2 → `Contested`：**不产生任何构成性效力**，触发概念澄清任务

**Contested 的处理（概念拆分协议）：**
1. 维护器生成 `ClarifyTerm` 任务，派发给深度引擎
2. 深度引擎输出候选 Facet 列表（可观测维度的投影）
3. 候选 Facet 带入原冲突重新跑 Judge：只有能让 Judge 从 2-1 收敛到 3-0 或 0-3 的 Facet 被接纳
4. 拆分深度硬上限 `MAX_DEPTH = 3`；超限则强制降级为 `AxiomaticDivergence`（世界观分叉），不再尝试机械解决

#### 1.7 分支管理（Branching）

**分支触发条件：**
- 深度引擎遇到缺失前提（Unknown）且该前提无法从外部获取 → 生成互斥假设集 → Fork
- 概念拆分超限触发 `AxiomaticDivergence` → Fork
- 攻击揭示出根本性前提冲突 → Fork

**分支爆炸控制（硬规则）：**
- `max_forks_per_unknown = 3`（不是二值，但有上限）
- `max_total_branches = 32`（全局上限）
- 分支合并条件：假设集完全一致（集合相等，非 embedding 相似）且结论在结构上等价（依赖图同构）
- 超出上限时：按调节性分数排序，淘汰最低分支（淘汰 = 标记为 `Deprecated`，保留审计记录，不删除）
- 淘汰是调节性的（资源回收），不是构成性的（不宣称该分支"错误"）

#### 1.8 终止条件（Stop Policy）

终止条件是**三重合取**，任一满足即停止：

**1. 预算耗尽（硬上限）**
- `max_total_tokens`：全局 token 消耗上限
- `max_rounds`：主循环迭代上限
- `max_wall_time`：墙钟时间上限

**2. 结构收敛（可计算指标）**
- `承诺层变动率（LedgerChurn）`：最近 W 轮中 ConstitutiveStatus 发生变化的节点比例 < ε₁
- `Issue 闭合率`：未解决 Issue 数量 / 总 Issue 数量 < ε₂
- `攻击存活率方差`：最近 W 轮中各节点 survivability 的变化方差 < ε₃

**3. 攻击健康度检查（防模式坍缩）**
- 最近 K 轮攻击产出的反例，经确定性去重（精确字符串匹配 + 被攻击前提 ID 匹配）后，新颖反例比例 < δ
- 若触发此条件，系统在停止前执行一次"多样性注入"：用不同 system prompt 模板重新生成一批攻击；若注入后仍无新颖反例，则确认停止

**终止时的输出：**
- 所有 `Validated` 工件组成的主线 DAG
- 所有 `Hypothesis` 工件及其假设集
- 未决 Issue 清单（含严重度、关联节点、尝试次数）
- 被淘汰分支的摘要（避坑指南）
- 停止原因（预算/收敛/攻击疲劳）
- **明确声明：这是"当前预算下的最佳近似"，不是"问题已完全解决"**

#### 1.9 超大项目（10M token 级）的处理策略

**上下文窗口管理：**
- 维护器为每次 worker 调用组装上下文时，只提取目标节点 + 直接相邻节点 + 术语表摘要 + 全局约束摘要
- 上下文预算硬上限（如 128K token），超出则按依赖距离裁剪
- 术语表作为全局共享的压缩知识，由维护器维护，每个 worker 调用都附带相关子集

**增量构建：**
- DAG 是增量的：每次 worker 只产出少量新节点/边，维护器增量写入
- 不需要任何 worker 一次性"看到"整个 10M token 的状态
- 全局一致性由维护器的确定性检查保证（引用闭合、无环、术语一致）

**分层抽象：**
- 广度引擎负责宏观→微观的分解，形成多层 DAG
- 每层的节点数量有软上限（由调度器控制），防止单层过于扁平
- 深度引擎只在叶子层或指定层工作，不需要全局视野

**并行化：**
- 多个 worker 可并行执行不同节点的任务
- 维护器串行写入（避免并发冲突），但可批量处理
- 攻击引擎天然可并行（对不同节点独立攻击）

---

## 第二部分：关键设计决策的辩护

### 决策 1：维护器是纯代码状态机，不是 LLM Agent

**辩护：** Linus 和 Ssyram 在第一轮就达成共识：维护器的决策应由图的拓扑结构决定，而不是由 LLM 去"想"下一步。康德虽然用不同术语，但也同意维护器的写入动作必须有确定性规则。

反对选项是"让维护器也是 LLM，但弱化其决策"（原始 v4 方案）。这被三方一致否决，理由是：LLM 不知道自己确不确信（Ssyram 语），"弱化决策"会偷偷把决策塞回维护器（Linus 语），维护器的写入具有构成性后果因此必须可审计（康德语）。没有任何辩手为"维护器用 LLM"做出有效辩护。

### 决策 2：双轨状态系统（构成性状态 vs 调节性分数正交）

**辩护：** 这是三轮辩论中最核心的争论焦点。

Linus 要求所有状态都可计算、可回滚，倾向于用单一的 `confidence: f32` + `status: Draft/Accepted/Rejected`。Ssyram 要求用对抗存活率作为唯一度量。康德指出这两种做法都会把调节性信号偷换为构成性承诺。

康德的批判在此处是决定性的：Ssyram 在第 20 轮承认"我试图用伪装成确定性的离散函数把大模型的概率性洗白成形式系统的绝对真理"；Linus 在第 25 轮也最终接受了 Verified/Hypothesis 的二分法。三方最终收敛到：**构成性资格只能由确定性条件授予，LLM 信号只能影响调度**。

反对选项是"用单一分数同时驱动调度和承诺"。这被否决，因为它会导致 survivability 排序被用户误读为真理排序（康德第 27 轮的论证），且 LLM 打分的方差会随意击穿任何硬门槛（Ssyram 第 11 轮对康德的质询，后被康德接受并修正）。

### 决策 3：硬验证（协议层）与软信号（攻击/裁判）严格分离

**辩护：** Ssyram 在第 14 轮承认自己"把语法/结构错误和语义/逻辑错误混为一谈"。Linus 从第一轮就坚持 validator 必须分层。最终方案：

- 硬验证（schema、引用、无环）是确定性代码，Error 阻止写入
- 软信号（逻辑冲突、定义模糊）由攻击+裁判产出，只能挂 ConflictNode 或降低调节性分数，不能阻止写入

反对选项是"所有 Error 都不截断控制流，靠拓扑吸收"（Ssyram 第 8 轮）。这被 Linus 用具体反例击溃：JSON 结构错误或引用断裂的 artifact 如果写入 DAG，后续所有依赖图遍历都会崩溃。Ssyram 在第 14 轮完全接受此修正。

### 决策 4：Judge 输出三值（ConflictConfirmed / NoConflictFound / Contested），而非二值或连续分数

**辩护：** 二值（YES/NO）被 Linus 在第 16 轮击溃："你只是把连续随机变量量化成二值随机变量，方差更大，收敛更慢"。连续分数（severity: f32）被 Ssyram 在第 11 轮击溃："0.4 的阈值完全取决于 prompt 微小扰动"。

三值方案的关键创新是 `Contested`：它不产生任何构成性效力，而是触发概念澄清任务。这把 Judge 的不确定性从"被迫做裁决"转化为"识别出需要更多结构化工作的地方"。这是康德"调节性理念"在工程上唯一可落地的体现：争议不是要被强行裁决的，而是要被转化为可处理的结构性任务的。

### 决策 5：分支合并用严格等价（假设集集合相等 + 依赖图同构），不用 embedding 相似度

**辩护：** Linus 在第 16 轮给出致命反例：embedding 相似度 > 0.95 的两个 claim 可能在边界条件上有生死之别（`index > 0` vs `index >= 0`）。合并它们会造成 silent regression，且不可审计。

代价是合并频率极低，分支可能较多。但这被分支爆炸控制的硬规则（`max_total_branches = 32`，按调节性分数淘汰最低分支）所缓解。宁可多保留几个分支并最终按调节性分数排序输出，也不要用不可靠的相似度合并造成静默错误。

### 决策 6：概念拆分有硬深度上限（MAX_DEPTH = 3），超限强制降级为世界观分叉

**辩护：** 康德在第 24 轮和 Ssyram 在第 23 轮都指出：没有良基关系的概念精化会陷入无限倒退。Linus 在第 22 轮要求"给我 ClarifyError 的分支和回滚路径"。

MAX_DEPTH = 3 是工程妥协，但它有明确的认识论辩护：如果三层拆分仍无法让 Judge 收敛，这几乎确定不是"概念欠规定"问题，而是"根本性前提冲突"或"对象域不可构成化"。此时正确的做法不是继续拆分，而是承认分歧并 Fork。这对应康德的"二律背反"概念：某些争议不是通过更精细的分析可解决的，而是需要在不同前提体系下分别展开。

### 决策 7：终止条件是"当前预算下的最佳近似"，不是"问题已完全解决"

**辩护：** 康德从第一轮就坚持"N 轮稳定不等于充分探索"。Linus 要求可计算的停止条件。Ssyram 要求预算化。

最终方案的三重合取终止条件（预算 OR 收敛 OR 攻击疲劳）是三方立场的综合：
- 预算耗尽是 Linus 的硬工程要求
- 结构收敛是 Ssyram 的 CEGAR 收敛思路（但只作为停止信号，不作为真理担保）
- 攻击健康度检查是康德"防模式坍缩"的工程化（但用确定性去重而非 embedding 相似度）

输出时明确声明"这是近似，不是完成"，并附带未决清单，是康德"调节性残余"概念的唯一可落地形式。

### 决策 8：Hypothesis 工件禁止作为 Verified 工件的硬依赖

**辩护：** 这是 Linus 在第 25 轮提出的最清晰的设计原则："拿不出证据，就别污染主线"。在开放域（历史解释、架构审美判断），大量工件永远无法获得外部可重复验证。

Ssyram 在第 17 轮质疑康德"必须有外部可重复检验将导致系统永远 0 Commit"。这个质疑是有效的，但解法不是降低 Commit 标准，而是**接受大量工件只能是 Hypothesis**，并在输出中诚实标注。系统的价值不在于把所有东西都盖章为"真"，而在于：(a) 把能验证的验证了，(b) 把不能验证的假设显式化了，(c) 把攻击过程中发现的风险记录了。

### 决策 9：攻击健康度检查用确定性去重，不用 embedding 相似度

**辩护：** Ssyram 在第 17 轮对康德的质询中指出：embedding 相似度在逻辑空间中不等于命题等价性（`index > 0` vs `index >= 0` 的 embedding 极高但语义不同）。康德在第 15 轮也承认需要修正。

确定性去重（精确字符串匹配 + 被攻击前提 ID 匹配）虽然会漏掉语义等价的不同表述，但不会产生 false positive（把不同攻击误判为相同）。在"防模式坍缩"的场景下，false positive 比 false negative 更危险：如果把两个实际不同的攻击误判为重复，系统会错误地认为攻击已疲劳并停止。宁可多跑几轮"看似重复"的攻击，也不要因为 embedding 误判而过早停止。

---

## 第三部分：遗留未决问题清单

### 问题 1：开放域 Objective 的 ScoreFnSpec 到底怎么写？

**为何未决：** Ssyram 在第 5 轮质询 Linus："'德川家为什么能取得丰臣天下'的 ScoreFnSpec 代码逻辑是什么？"Linus 在第 7 轮回应时承认"开放域的 score 只能是 LLM 打分的统计量"，但又坚持"必须可计算"。最终方案把 LLM 打分降格为调节性分数，但这意味着**开放域问题的调度优先级仍然依赖不可靠的信号**。

这是本质性的张力：系统需要某种信号来决定"先算哪个"，但在开放域中没有可靠的纯函数信号。当前方案的缓解措施（用对抗存活率而非直接打分）减轻了问题但未消除。需要更多实验数据来确定：对抗存活率在开放域中是否比随机调度显著更好。

### 问题 2：Domain Profile 的初始化协议

**为何未决：** Ssyram 在第 23 轮质询康德："Domain Profile 是静态预置还是动态生成？如果动态生成，就是用 LLM 定义 LLM 的类型边界，循环论证。"康德未给出完全令人满意的回答。

当前方案的处理是：协议层的硬验证（schema、引用、无环）不依赖 Domain Profile，因此核心安全性不受影响。但"哪些节点应标记为 RegulativeNote（不参与存活率计算）"这一分类决策，确实需要某种领域知识。如果这个分类由 LLM 做，就存在循环风险；如果由用户预置，就限制了泛化能力。这是一个需要在实际部署中通过迭代解决的问题，而非可以在设计阶段完全确定的。

### 问题 3：Judge 的跨 seed 稳定性在实践中是否足够

**为何未决：** 三方都承认 Judge 是概率性的。当前方案用三值输出 + Contested 降级来缓解，但没有实验数据证明：在真实的开放域任务中，Judge 的 3-0/0-3 比例是多少？Contested 比例是多少？如果 Contested 比例过高（比如 > 50%），系统会把大量时间花在概念澄清上，可能导致实际吞吐量过低。

这是信息不足的问题：需要在真实任务上跑实验，测量 Judge 的稳定性分布，然后据此调整 N（采样次数）和 Temperature。

### 问题 4：分支淘汰的调节性分数排序是否会引入隐性偏见

**为何未决：** 当分支数达到上限时，按调节性分数淘汰最低分支。但调节性分数本身依赖 LLM 信号（对抗存活率），而 LLM 可能对某些类型的假设有系统性偏见（例如偏好主流叙事、偏好简单解释）。这意味着被淘汰的分支可能恰恰是最有创新性但最不符合 LLM 训练分布的分支。

这是本质上无法单一裁定的问题：任何有限资源下的搜索都必须做取舍，而取舍标准不可能完全无偏。当前方案的缓解措施是：淘汰的分支保留审计记录（不删除），用户可以手动恢复。但这不能从根本上解决偏见问题。

### 问题 5：10M token 级项目中术语表的维护与一致性

**为何未决：** 当 DAG 规模达到数万节点时，术语表本身可能变得庞大且内部不一致。维护器需要某种机制来检测术语表内部的冲突（同一术语在不同子图中被赋予不同定义），但这种检测在自然语言中不是确定性可解的。

当前方案假设术语表由维护器维护且每次 worker 调用附带相关子集，但没有详细定义"术语冲突检测"的算法。对于代码/形式化领域，可以用精确匹配；对于自然语言领域，这仍然是开放问题。

### 问题 6：Hypothesis 工件在实际使用中的价值传递

**为何未决：** 系统可能产出大量 Hypothesis 工件（尤其在开放域），每个都带着假设集和 defeaters。用户面对数十个 Hypothesis 时，如何高效地理解和选择？当前方案只提供调节性分数排序和未决清单，但没有定义"面向用户的摘要生成"协议。这不是核心架构问题，但会严重影响系统的实际可用性。

### 问题 7：多 worker 并行时的上下文一致性

**为何未决：** 当前方案允许多个 worker 并行执行，维护器串行写入。但如果 worker A 和 worker B 同时读取了 DAG 的同一快照，各自产出了互相冲突的提案，维护器串行写入时第二个提案可能基于过时的状态。这是经典的并发一致性问题，当前方案未详细定义冲突检测与重试策略。在小规模下可以简单地串行化所有 worker 调用，但在 10M token 级项目中这会成为瓶颈。