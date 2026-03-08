# new-debate-v2：AI 辅助认知系统的引擎架构设计

> 2026-03-08，共 3 场（1场全新 + 2场续跑），产出四引擎框架完整原理体系

---

## 一、为什么要做这场讨论

上一轮（new-debate-ai）讨论产出了 AI 辅助认知系统的 v0.1 架构（ClaimInstance、三层证据契约、Categorical Veto、DAG 污点追踪等），这是对「如何处理认知系统内部状态」的设计。

但 Ssyram 在与人聊哲学之后意识到，还差了一个更上层的问题：**这个系统的引擎架构是什么——它靠什么驱动自己把认知质量向上提高？**

原有的三维度框架（广度/深度/精度）来自「什么样的结论经受得住考验」，但实践发现：
1. 「清晰度」必须作为第四个独立维度分离出来
2. 这四个维度不是验收指标，必须是「引擎」——有触发条件、输入输出、故障恢复机制
3. 四个引擎如何协同循环（不是独立运行），才能将认知质量向上提高

**这次讨论的总目标**：设计一个清楚的四引擎框架，产出：
- **原理体系**：广度说明（论域覆盖）、深度根基（前提追溯）、精度论证（逻辑自洽）各引擎如何运作，清晰度如何作为守门人
- **潜在问题与风险**：即广度的不足，深度根基中缺少考虑的方面
- **可落地方案**：具体到数据结构、状态转移、触发协议

---

## 二、Ssyram 角色更新说明

相比 new-debate-ai，本轮 Ssyram 的风格描述新增了以下从对话中提炼的信息：

**新增认知与立场**：
- **清晰度的本质理解**：「正确的废话」是清晰度失败的典型——真命题但命题边界模糊，接收者无法构造有效反例。「如果它能更长则它能更短」的逆命题：简洁是信息效率，不是字数减少。
- **四引擎分层判断**：广度最难（隐式裁剪 + 无局部 stopping signal），清晰度第二（需要机械化强制，但不能只靠发送端），深度第三（自然但需停止判据），精度第四（辩论是一种实现但职责可能过重）。
- **立场张力的定位**：它是精度和广度引擎的手段，不是引擎本身。失效条件是「同源分布假张力」。
- **广度难题的精确表述**：辩手确立时论域被无形决定；如何在已有框架内引出框架之外的广度是最大设计问题。

---

## 三、三场辩论过程

### 场次一：old-topic1 续跑（注入四引擎框架）

**来源**：从 `new-debate-ai/topic1_debate_log.checkpoint2.md` 续跑（第35轮）

**注入内容**：将四引擎框架问题注入，要求三方针对广度最难/立场张力触发引擎/引擎协同/具体机械化实现给出判断

**主要产出**：

- **Linus**：四引擎是四类「故障恢复回路」（failure detector + repair loop），不是验收指标。广度引擎 = 外域采样器 + 反框架审计器（强制输出 `UNBOUND_DIMENSIONS` / `ASSUMED_INVARIANTS`）；立场张力失效条件明确（风格差异 ≠ 约束差异）；给出了完整的 Python 伪代码循环：
  ```python
  while budget_ok:
      claims = clarity_engine.normalize(raw_claims)
      issues = precision_engine.find_contradictions(claims)
      assumptions = depth_engine.extract_assumptions(claims, issues)
      new_dims = breadth_engine.search_unbound_dimensions(assumptions)
  ```

- **Ssyram**：清晰度不是普通引擎，是「全局语义约束层 / 可检验性约束层」——没有清晰度，其他三个引擎都无法稳定运转（深度不知追哪个前提，精度不知检查哪条推理链，广度不知当前覆盖哪个切片）。广度的外源扰动通道三类（目标函数改写、语料外检索、角色反转）。

- **康德**：四引擎精确对应人类心智四大先验机能——感性（广度）/知性（精度）/判断力（清晰度）/理性（深度）。给出「清晰度引擎的先验图型化防线」Python 伪代码，强制输出 `empirical_falsifier` + `required_probe_signature`。四引擎协同顺序：清晰度（判断力）→ 广度（感性）→ 精度（知性）→ 深度（理性）→ 循环。

**裁判结论**：三次认知推进——清晰度宪法化（机械可证伪性）、广度祛魅（反框架扫描）、深度硬截断（操作化极限）。

---

### 场次二：new-debate-v2/topic1 全新运行（初始3轮）

**配置**：全新议题，Ssyram 风格纳入了上述新信息，辩题正文包含四个核心设计问题

**主要推进**：

**轮一**：
- Linus 立刻纠正：四引擎是验收指标 vs 引擎的关键区分——引擎必须有输入/触发条件/输出改变系统状态
- Ssyram 确立：清晰度不是同层引擎，是全局门控层；草稿池（Draft Pool）vs 主图分层内存
- 康德 引入：四引擎对应先验机能，清晰度引擎 = 双边匹配（发送端充分性 × 接收端图型匹配度）

**质询轮**：
- Linus 攻击 Ssyram：清晰度门控会卡死高价值模糊想法 → Ssyram 修正：草稿池 + 升格协议（三步流水线）
- Ssyram 攻击康德：区分很多，但没有工程决策点 → 「图型」到底是什么数据结构？
- 康德 攻击 Linus：「有用」和「真」是两个不同范畴，停止判据的先验条件是什么？

**轮二**：
- 「语义清晰度」vs「验证器可用性」被成功解耦：Semantic Clarity Gate（反例模板）+ Verifier Availability Gate（系统挂载对应 verifier）
- Ssyram 修正：四引擎不是线性顺序，精度矛盾时触发深度（冲突源于隐含前提）或广度（冲突表现为死锁）
- Linus 确立三个广度独立触发源：内生触发（平台期/死锁）+ 外生触发（stakeholder/temporal/interface重述）+ 回归触发（历史漏维）

**反退化约束**（关键）：Linus 指出 Ssyram cost 函数会 Goodhart（系统通过缩小 scope 消灭冲突）→ Ssyram 加入信息量下限约束和必须新增失效边界说明

**裁判评分**：广度 8/10，深度 9/10，精度 9/10，清晰度 9/10

---

### 场次三：new-debate-v2/topic1 续跑（Schema Challenge Queue + 状态机）

**注入**：聚焦两个未落地问题——Schema Challenge Queue 具体协议 + 四引擎完整状态机

**Linus 产出**：Schema Challenge Queue 完整触发协议
```json
{
  "trigger_if_any": [
    "anomaly_pool.size >= T1",
    "precision_deadlock == true",
    "plateau_rounds >= T2 && new_attack_type_rate < R",
    "replay_regression_hit == true"
  ]
}
```
广度扩展的唯一合法性标准：**必须能解释 Anomaly Pool 中的旧失败，或在重放集上改变核心结论排序**。验收函数 `accept_schema` 明确。

**Ssyram 产出**：10状态完整状态转移表

```
状态：S0(Draft) S1(Clarify) S2(TestableClaim) S3(PrecisionCheck)
      S4(DepthProbe) S5(BreadthProbe) S6(Verified) S7(Suspended)
      S8(Archived) S9(SchemaChallenge)

关键转移：
S1 -> S2   清晰度通过（两代理可一致重建 claim/scope/falsifier/non_claim）
S2 -> S3   默认进入精度检查
S3 -> S4   矛盾源于隐含前提（触发深度）
S3 -> S5   矛盾表现为死锁（触发广度）
S4 -> S1   挖出新假设，必须重过清晰度门控
S4 -> S7   到达操作化极限，悬置
S5 -> S9   当前 schema 无法表达新对象
S9 -> S2   新 schema 通过验收
S6 -> S4   高置信结论遭遇外部反例（异常池溢出）
```

**康德 产出**：`Antinomy_Resolution_Protocol` JSON，裁定「先深后广」序列：
1. 深度引擎首先触发，寻找冲突双方「最小公共祖先假设（Lowest Common Ancestor Premise）」
2. 若发现共同前提是先验幻象，广度引擎才合法启动
3. 「同源张力」检测：若两个 Agent 共享相同知性范畴（`Is_Homologous = true`），强制聚合（Aggregation），绝对禁止启动广度

**裁判评分**：广度 9.5/10，深度 9/10，精度 9/10，清晰度 9/10

---

## 四、最终原理体系

### 核心范式转移：四引擎 = 四类故障恢复状态机

**不是**：广度/深度/精度/清晰度是「评价维度」或「价值观」
**是**：四类 `failure detector + repair loop`，每类有明确的触发条件、输入输出、停止判据

---

### 1. 清晰度引擎（全局守门人）

**地位**：不是与其他三个平行的引擎，是全局语义约束层。没有清晰度，其他三个引擎无法稳定运转。

**故障类型**：「正确的废话」——真命题但命题边界模糊，接收者无法构造有效反例

**机制**：证伪条件生成器（`empirical_falsifier`）+ 双层门控

```
Semantic Clarity Gate：命题是否包含反例模板（接收者能一致重建 scope/assumptions/falsifier/non_claim）
Verifier Availability Gate：系统是否挂载对应 verifier（缺乏时标记为"调节性理念"，真值悬置）
```

**停止判据**：不需要；是入口拦截器，不是迭代器

**简洁定义**：一个命题通过清晰度门控，当且仅当两个独立 Agent 对"何种观测可推翻它"能做出高度一致的重建

---

### 2. 深度引擎（前提追溯器）

**故障类型**：「结论站着，但地基是空的」——命题可接受，但依赖的隐性前提未被显式化或检验

**触发条件**：精度引擎（S3）发现矛盾源于隐含前提时（`S3 -> S4`）；或有外部反例命中已验证结论时（`S6 -> S4`）

**机制**：
- 「取一隅」选择：不是随机追问，是在精度矛盾时寻找「最小公共祖先假设（LCA Premise）」
- 上下文管理：每次下探生成新假设，新假设必须重新经过清晰度门控（`S4 -> S1`）
- **停止判据**（三选一）：
  1. `OPERATIONAL_LIMIT`：再下探无法生成物理探针（此时转为「探针开发义务」）
  2. `FOUNDATIONAL_CHOICE`：到达基本价值分歧，无法用事实解决
  3. `LOW_MARGINAL_GAIN`：继续下探不改变当前设计排序（注：还须看对未来 Schema 崩溃的吸收能力）

**深度的「求因性」**：这是最自然的引擎，由基模的素性驱动。但无限后退会导致崩溃——停止判据是必须的，不是可选的。

---

### 3. 广度引擎（论域扩展器）

**故障类型**：「看起来对，其实只在一个狭窄切片里对」——系统在被早期 framing 收窄的空间里越来越精密地自洽

**广度的根本难题**：
1. 辩手确立时，论域子集被无形确定——框架外的维度不会自己长出来
2. 广度没有天然的局部 stopping signal（精度有矛盾，深度有不可操作化；广度没有）

**触发源（三类，缺一不可）**：
1. **内生触发**：平台期（连续 N 轮无新攻击类型）、精度死锁、重复攻击类型收敛
2. **外生触发**：强制按 stakeholder / resource / temporal / interface 四类重述问题；目标函数扰动（换优化目标）
3. **回归触发**：历史上被排除但后来造成错误的维度，进入 replay 集合周期性重放

**Schema Challenge Queue 协议**（广度的核心机制）：
```json
触发条件（满足任一）：
- anomaly_pool.size >= T1（无法被解释的外部失败样本积累）
- precision_deadlock == true
- plateau_rounds >= T2 && new_attack_type_rate < R
- replay_regression_hit == true

新 Schema 验收标准（必须满足任一）：
- 能解释 Anomaly Pool 中至少 P% 的旧失败
- 在 replay 集上使核心结论排序产生变化
- 引入节点类型/边类型不是旧类型的同义改写（must_not_do: purely normative relabeling）
```

**广度终极来源的未解分歧**：Kant 坚持广度必须依赖外部「经验阻力」（Anomaly Pool 溢出），因为系统无法从内部完美一致中发现漏维。Linus/Ssyram 认为内部平台期同样可以触发。这个分歧未被解决，因为缺乏实证数据（系统是否会陷入自洽幻觉的 echo chamber）。

---

### 4. 精度引擎（逻辑交通枢纽）

**故障类型**：「内部互相冲突或偷换概念」

**地位**：不承担解决矛盾的任务，而是将矛盾准确分类并路由

**矛盾路由规则**：
- `S3 -> S4`（触发深度）：矛盾源于隐含前提未展开——「为什么双方结论不同」有答案（LCA Premise 存在）
- `S3 -> S5`（触发广度）：矛盾表现为重复死锁，LCA Premise 本身是先验幻象——需要新的分类坐标系

**辩论（立场张力）作为精度引擎手段**：不是引擎本身，是触发精度检验的外力。失效条件：
- **假张力（同源分布）**：两 Agent 共享相同知性范畴，冲突只是同一范畴内的参数差异 → 强制聚合，禁止触发广度
- **大词污染**：立场张力产生大量听起来有道理的高浓度辞藻，但信息量低于字面量 → 清晰度引擎拦截

**反退化约束**（防 Goodhart）：精度引擎不能通过「缩小 scope + 降级断言」消灭冲突。必须加约束：
- 信息量下限（修复后 `not_claiming` 字段不得扩展超过阈值）
- 必须新增失效边界说明（修复不能只删除对象，必须补充"在什么条件下原结论失效"）

---

### 四引擎完整状态转移（核心路径）

```
新命题进入
    ↓
[S0 Draft] → 升格流水线（Extractor → Adversary → Judge）
    ↓ 通过
[S1 Clarify] ← ← ← ← ← ← ← (深度挖出新假设，循环回来)
    ↓ 双代理一致重建
[S2 TestableClaim]
    ↓ 默认
[S3 PrecisionCheck]（精度枢纽）
    ↓ 隐含前提              ↓ 死锁/LCA是幻象
[S4 DepthProbe]         [S5 BreadthProbe]
    ↓ 操作化极限              ↓ 旧schema不足
[S7 Suspended]          [S9 SchemaChallenge]
    |                         ↓ 新schema通过
    |                   [S2 TestableClaim] → ...
    ↓ 充分支持
[S6 Verified]
    ↓ 外部反例命中
[S4 DepthProbe] → 循环
```

---

## 五、潜在问题与风险（广度的不足）

### 1. 广度来源的根本未解问题
**问题**：广度触发的终极来源——内部结构信号（平台期/死锁）还是外部阻力（Anomaly Pool 溢出）？  
**风险**：如果只靠内部触发，系统可能陷入自洽的 echo chamber，在物理崩溃前无法自发发现漏维。  
**现有缓解**：回归触发（历史漏维 replay 集合）+ 外生强制（目标函数扰动）  
**未解**：缺乏实证数据确认内部触发是否充分

### 2. 同源张力检测的鲁棒性
**问题**：`Is_Homologous` 检测在实际 LLM 运行中如何可靠判定？  
**风险**：LLM 产生幻觉，把「短期成本」和「长期成本」误判为异质范畴，错误触发广度引擎引入噪声  
**现有缓解**：要求显式声明「依赖的知性范畴坐标」  
**未解**：范畴分类器的鲁棒性尚未验证

### 3. 异常摄入协议（Anomaly Ingestion Protocol）缺失
**问题**：当物理执行环境返回非结构化 Error（`Timeout Exception`、`User Engagement dropped 15%`）时，如何翻译成 `stuck_signals.anomalies` 结构化字符串？  
**风险**：翻译太具体 → 广度无法泛化；翻译太抽象 → 广度生成废话  
**状态**：这是下一步最值得深挖的工程问题（从「物理探针报错」到「认知图谱异常节点」的映射机制）

### 4. 清晰度引擎的接收端问题
**已知但接受**：清晰度在哲学上是双边问题（发送端充分性 × 接收端范畴匹配度）。当接收端没有对应计算范畴时，发送端格式化无法保证理解。  
**工程上的妥协**：发送端机械强制是必要条件，加接收端 schema compatibility check，不匹配时报 Category Mismatch。这不是完美解，但是系统性改善。

### 5. 广度引擎的「DIMENSION_FAMILIES」硬编码
**问题**：Coverage Matrix 中的维度族（failure_mode, stakeholder, time_scale, interface）依然是人类硬编码的  
**风险**：系统无法内生发现既不在预设列表里、又极其关键的全新维度  
**部分缓解**：Schema Challenge Queue（广度可以挑战自己的 schema），但 SCQ 的输入仍然依赖 Anomaly Pool

---

## 六、最小可实现方案

按照两场讨论的产出，以下是可以立刻开始实现的最小系统：

### 阶段一：清晰度门控（最先实现）
```python
# 核心：两代理一致性测试
def clarity_gate(claim_obj):
    agent1 = extract_falsifier(claim_obj, seed=1)
    agent2 = extract_falsifier(claim_obj, seed=2)
    if jaccard_similarity(agent1.counterexample, agent2.counterexample) < THRESHOLD:
        return "DRAFT"  # 退回草稿池
    return "TESTABLE_CLAIM"
```
配合 `empirical_falsifier` 字段强制要求（不填则拒绝进主图）

### 阶段二：精度枢纽（矛盾分类路由）
```python
def precision_route(contradiction):
    lca = find_lca_premise(contradiction.claim_a, contradiction.claim_b)
    if lca.is_transcendental_illusion:
        return "BREADTH"  # S3 -> S5
    else:
        return "DEPTH"    # S3 -> S4
```

### 阶段三：深度探针（停止判据）
```python
def depth_probe(assumption):
    probe = generate_physical_probe(assumption)
    if probe is None:
        return "SUSPEND", ObligationDevelopment(assumption)
    return "CONTINUE", probe
```

### 阶段四：广度 Schema Challenge（最后实现）
```python
def schema_challenge(anomaly_pool, current_schema):
    if not meets_trigger_conditions(anomaly_pool):
        return None
    proposal = generate_schema_proposal(anomaly_pool, current_schema)
    if accept_schema(proposal, anomaly_pool, replay_set):
        return proposal
    return None
```

**实现顺序**：清晰度门控 → 精度路由 → 深度停止判据 → 广度 Schema Challenge

---

## 七、第二阶段：深度边界锚定广度（2026-03-08 续）

> 本节记录在四引擎框架基础上，针对「以深度接引广度」新提案的验证过程（probe + topic1续跑 + topic2全新）。

### 背景与新提案

四引擎框架第三场遗留问题：**广度触发的终极来源**（内部结构信号 vs 外部 Anomaly Pool）争议未解。

Ssyram 提出新想法：「以深度接引广度」——当深度引擎追溯假设链时，对每个假设 A 同时查询其补域/边界，广度扩展成为深度追溯的自然副产品，不再需要独立触发。

**对原始计划的事后评估**：原始计划中直接注入「补域」概念是有风险的（「补域」在工程上意味着无限膨胀的垃圾桶）。先跑小辩论（probe）打磨语言的策略是正确的——它发现了「补域」的失效点，并产出了更精确的注入 message。这比直接注入原始措辞质量高出一个档次。

### 场次四：probe 小辩论（高打磨）

**目的**：在正式续跑前，用1轮高打磨辩论将「以深度接引广度」打磨清楚。

**关键裁定（probe_debate_summary.md）**：

1. **「补域」概念被废弃**：对自然语言求补集会得到"无限膨胀的垃圾桶"。纯数学意义的补域不可执行。
2. **降级为「结构化相邻探索」**：将假设 A 解析为三元组 $(S, P, J)$，沿三轴生成定向空位：
   - 作用域相邻 $B_{scope}$：当前作用域之外的未覆盖子域
   - 失效条件 $B_{failure}$：使当前性质反转或退化的条件
   - 替代支撑 $B_{alt}$：在支撑不成立时的替代机制
3. **更准确的表述**：「以深度边界锚定广度探索」——深度提供**逻辑空位（Placeholder）**，广度**填充经验内容**
4. **深度只是触发，广度还需外部经验**：深度引擎只能给出空位，广度实例化依然需要 Ontology/Anomaly Pool 注入

**机制更新**（纳入正文的直接文字）：
> 广度引擎不必作为完全独立的随机探索器，其触发与定向机制由深度引擎内生提供。  
> 第一步：深度引擎提供**逻辑空位（GapSpec）**——将假设解析为 $(S, P, J)$ 三元组，沿三轴生成定向空位。  
> 第二步：广度引擎**注入经验内容**——从 Ontology/Anomaly Pool 实例化空位；若无外部经验，该方向自动截断。

### 场次五：topic1 续跑（GapSpec 接口 + 防爆机制）

**注入 message**：probe 产出的裁判介入裁定，聚焦「GapSpec 如何作为 Query 查询外部库」和「候选维度爆炸的防爆机制」。

**主要产出**：

- **Linus**：给出强类型 GapSpec JSON，包含 `gap_id`, `failure_kind`, `query_axes`, `required_observable`, `accept_test`, `reject_if`——告别自然语言 Query
- **Ssyram**：核心洞察——GapSpec 不是 query object，而是 **partial falsification / bifurcation contract**。它不是告诉广度"去哪搜"，而是告诉广度"什么样的候选算把命题分叉了"
- **康德**：「先验亲和性（Transzendentale Affinität）」剪枝协议——候选维度 C 必须能在不同取值下分别使正题和反题为真，才能通过。同时给出三步剪枝协议的 Python 骨架

**裁判裁定**：
1. `GapSpec` 强类型契约化（废弃自然语言）解决了"广度注入工程可操作性"
2. 先验亲和性剪枝（两段式：存在性校验 + 分裂性校验）解决了"伪维度爆炸"

### 场次六：topic2 全新（GapSpec 协议完整化 + 引擎重组）

**辩题**：GapSpec 的完整类型定义 + 先验亲和性剪枝最小实现 + 状态机更新 + 四引擎是否变三引擎

**三大认知推进**：

1. **从格式校验到溯源（Trace Grounding）**：GapSpec 必须含 `TraceGrounding`，将焦点从"语法正确"转到"逻辑合法"——防止 LLM 生成形式完美但无根据的幻觉 GapSpec

2. **从「异常驱动」扩展为「多源经验析取（Provenance Union）」**：
   ```typescript
   type Provenance =
     | { kind: "trace_span",       trace_id: string, ast_node_id: string }
     | { kind: "anomaly",          anomaly_id: string }
     | { kind: "coverage_hole",    missing_slice: string }
     | { kind: "ontology_neighbor", node_id: string };
   ```
   广度不只靠异常驱动，结构性盲区（coverage hole）和本体邻居同样合法

3. **亲和性剪枝拆解：存在性（Witness） vs 分裂性（Polarity）**：
   - Stage 1：候选值域在 Ontology 中存在（否则剪枝）
   - Stage 2：候选值能对同一观测物产生方向相反的预测（否则剪枝）

**裁判最终裁定（GapSpec 推荐最小字段集）**：

```typescript
type Provenance =
  | { kind: "trace_span",       trace_id: string, ast_node_id: string }
  | { kind: "anomaly",          anomaly_id: string }
  | { kind: "coverage_hole",    missing_slice: string }
  | { kind: "ontology_neighbor", node_id: string };

interface GapSpec {
  gap_id:               string;
  target_claim_ast_id:  string;  // 锚定原命题（AST 节点 ID）
  gap_kind:             "scope_split" | "proxy_break" | "mediator";
  provenance:           Provenance;  // 解决幻觉问题
  required_observables: string[];    // 系统中已注册的 Metric/Field ID

  bifurcation_contract: {
    thesis_condition:     string;
    antithesis_condition: string;
    expected_delta_sign:  ">0" | "<0" | "!=0";  // 强制明确的预测差异
  };
}
```

**引擎重组裁定：四引擎 → 三引擎**

> 裁判裁定：合并 S4（深度生成）与 S4.5（溯源网关），重组为「假设综合与溯源引擎（Hypothesis Synthesis & Grounding Engine）」。

理由：脱离了 Trace/Anomaly 溯源的 GapSpec 生成毫无意义。生成与校验应在同一上下文中完成，而不是两个异步流水线节点。

| 原四引擎 | 重组后 |
|---------|--------|
| 清晰度（全局守门人） | 清晰度（不变） |
| 精度（逻辑枢纽） | 精度（不变） |
| 深度（前提追溯） + 广度（论域扩展） | **深广合并引擎**（假设综合与溯源 → 经验实例化） |

**未解的核心问题（下一步）**：
1. `bifurcation_contract` 的防诡辩 Prompt/验证函数——LLM 极擅长"和稀泥"（生成"A提升，B提升较少"式伪分裂）
2. GapSpec 网关（S4.5）失败后的状态机路由语义——是重试、降级为纯逻辑闭包，还是丢弃整条推理链？

---

### 场次七：topic3 全新（机制合理性验证，不预设共识）

**辩题**：「以深度接引广度」是否真正统一了深度与广度引擎？三方从各自立场攻防，结论开放。

**三大认知推进**：

1. **从「语义统一」退格到「接口/控制流收敛」**：Linus 指出广度的知识源、检索机制、失败状态依然独立，「统一」只是把广度从 explorer 改成了 retrieval worker。Ssyram 被迫精确收缩命题：**消灭了无类型的局部广度调用接口，代之以 $(S,P,J)$ Gap 协议**。

2. **从「伴生触发」演进到「守卫门控（Guard）」**：每次深度追溯都无条件派生广度会导致分支爆炸、深度被稀释。必须有 `closure_of_local_depth`（局部深度已闭合）等前置守卫条件，才允许生成 Gap。

3. **从「先验算计」跃升到「经验盲测 + 调节性缓存」**：康德指出用纯逻辑计算「预期信息增益」是先验幻相（把调节性理念当作构成性原则）。结论：引入 S4.5(ReflectiveProbe) 做极低成本外部盲测，未命中的 Gap 存入 RegulativeCache 等待未来经验激活。

**裁判最终裁定**：

| 命题 | 裁定 |
|------|------|
| 机制是否合理？ | **局部广度范畴内高度合理，不能替代全局广度** |
| 是否真正「统一」了深度与广度？ | **没有统一。只统一了局部广度的 Task Formation（下发协议）** |

**推荐的最终架构（双轨制广度 + 经验盲测缓存）**：

```python
# S4: 深度推演
transition S4(assumption):
    if has_deeper_logic(assumption):
        return S4(next_depth)
    # 局部闭合，生成形式空位
    gaps = generate_SPJ_gaps(assumption)
    return S4_5(gaps)

# S4.5: 经验盲测与调节性缓存
transition S4_5(gaps):
    hits, misses = cheap_empirical_probe(gaps, AnomalyPool, budget=small)
    if misses:
        RegulativeCache.push(misses)   # 悬置，等待未来经验激活
    if hits:
        return S5_Local(hits)          # 局部广度：处理命中的 Gap
    else:
        return S7(Deadlock_or_Return)

# 全局广度独立旁路
on_event(New_Anomaly_Ingested):
    if matches(New_Anomaly, RegulativeCache):
        trigger S5_Local(matched_gap)  # 悬置空位被激活
    elif is_schema_breaking(New_Anomaly):
        trigger S5_Global(New_Anomaly) # 全局范式转移（不依赖深度）
```

**「统一」的精确结论**：
- ✅ 统一了：局部广度的触发协议（不再靠独立 heuristics）、接口类型（Typed Gap 取代 free-form）
- ❌ 没统一：广度的外部知识源、全局广度触发（Schema-shift 需独立旁路）
- 新引入：S4.5(ReflectiveProbe) 中间态、RegulativeCache 调节性缓存

**下一步悬置问题**：RegulativeCache 的异步匹配复杂度——随着系统运行缓存膨胀，如何以低于 $O(N \times M)$ 的复杂度判断新涌入的非结构化异常是否匹配几个月前悬置的某个 Gap？

---

## 八、文件索引

```
examples/new-debate-v2/
├── README.md                            ← 本文件
├── probe.md                             ← 小辩论（打磨「以深度接引广度」）
├── probe_debate_log.md                  ← probe 辩论记录
├── probe_debate_summary.md              ← probe 裁判总结（含推荐注入 message）
├── topic1.md                            ← 讨论配置（四引擎议题，更新 Ssyram 风格）
├── topic1_debate_log.md                 ← 完整辩论记录（3轮 + 2次续跑）
├── topic1_debate_summary.md             ← 最新裁判总结
├── topic1_debate_log.checkpoint3.md     ← 第二次续跑前备份
├── topic2.md                            ← GapSpec 协议细节（topic2，被 topic3 定性后有工程参考价值）
├── topic2_debate_log.md                 ← topic2 完整辩论记录
├── topic2_debate_summary.md             ← topic2 裁判总结（含 GapSpec 推荐字段集）
├── topic3.md                            ← 机制合理性验证（核心：「以深度接引广度」是否统一了深广？）
├── topic3_debate_log.md                 ← topic3 完整辩论记录
└── topic3_debate_summary.md             ← topic3 裁判总结（含双轨制广度架构）

# 参考（备份点）
../new-debate-ai/
├── topic1_debate_log.checkpoint2.md    ← old-topic1 续跑前的备份点
└── ...（old 场全部记录）
```

---

## 十、元观察

**清晰度引擎在这次讨论本身就得到了验证**：每次有发言信息量低于字面量（「原则上应该如何」），Linus 就立刻要求 grounding（「具体的 JSON 骨架」「伪代码」）；Ssyram 就追问「这改变了哪个设计决策点」；Kant 则要求「可推翻的界定」。这种互相施压的模式，本身就是清晰度引擎运转的一个示例。

**广度的真实困难在这次讨论里也有体现**：当 Kant 提出「经验阻力是广度的唯一真实来源」时，Linus 和 Ssyram 反对，但双方都无法用实证数据解决这个分歧。这个分歧本身就是「内部一致的系统无法内生发现自己漏维」的一个演示。

**立场张力的作用**：Linus 的工程实用主义（「可计算 or 废话」）、Ssyram 的形式化-实用对接（「每层都要能落地」）、Kant 的批判哲学（「有用 ≠ 真，先验条件是什么」）三者之间的张力，产生了每次真正的推进——不是意见综合，而是找到了新的区分（语义清晰度 vs 验证器可用性；同源张力 vs 异质张力；线性顺序 vs 非线性状态机）。

*本记录由 Claude (Sisyphus) 于 2026-03-08 整理，6场（probe + 3全新 + 2续跑）。*
