# new-debate-v3：四象引擎体系的综合设计

> 2026-03-09，以 new-debate-v2 七场辩论成果为基础，设计「输入问题 → 四象引擎 → 输出辩护完备答案体系」的 v3 框架

---

## 一、为什么要做这场讨论

new-debate-v2 建立了四引擎（广度/深度/精度/清晰度）作为**命题级故障恢复状态机**的完整体系，产出：

- **清晰度引擎**：全局语义约束层（双层门控：Semantic Clarity Gate + Verifier Availability Gate）
- **深度引擎**：前提追溯器（LCA Premise + 三停止判据）
- **广度引擎**：论域扩展器（Schema Challenge Queue + 双轨制广度）
- **精度引擎**：矛盾路由枢纽（S3→S4/S5，不承担解决）
- **GapSpec 协议**：深度边界锚定广度的强类型接口（含 Provenance + bifurcation_contract）
- **深广双轨机制**（topic3）：S4.5(ReflectiveProbe) + RegulativeCache + S5_Global 独立旁路

**v2 解决的问题**：如何处理单个命题在认知系统内部的质量问题（Draft → Verified）

**v3 要解决的新问题**：如何把**一个输入问题**转化为**多视角辩护完备的答案体系**

这个问题的规模不同：v2 处理的是命题，v3 处理的是整个问题。处理粒度的改变可能意味着架构需要根本性调整。

**核心争议点**：

1. **整体拓扑**：顺序流水线（草案）vs 迭代循环 vs 两层分离（问题级+命题级）vs 统一状态机
2. **清晰度位置**：前置全局门控（v2）vs 后置按需澄清（v3草案）vs 分层双重角色
3. **精度角色**：矛盾路由（v2）vs 论证加固（v3草案）vs 双重职责
4. **深广引擎**：v2 深广双轨机制的 v3 封装 vs 全新独立引擎
5. **广度驱动**：「立场张力」是否是合法的广度引擎核心机制（v2 认为它只是手段，不是引擎本身）

---

## 二、Ssyram 角色更新说明（相比 new-debate-v2）

**新增掌握的 v2 成果**：

- **GapSpec 强类型契约**：废弃自然语言 Query，强制 Provenance + bifurcation_contract，解决幻觉问题
- **先验亲和性剪枝**：两段式（Witness 存在性 + Polarity 分裂性），防伪维度爆炸
- **深广双轨制**：局部广度（S4.5，深度闭合后顺手生成并廉价探针）+ 全局广度（S5_Global，独立旁路）
- **RegulativeCache**：悬置未命中 Gap，等待未来经验激活（异步匹配问题尚未解决）

**新增的 v3 设计问题**：

- v3 草案是：广度（立场张力生成候选答案）→ 深度（生成根基辩护）→ 精度（加固辩护）→ 清晰度（按需澄清）→ 深广引擎（进一步 break down）
- 这个草案有多个假设可能是错的（清晰度位置、精度角色、是否是顺序流水线）
- 最核心的不确定性：v3 的问题级流水线和 v2 的命题级状态机是什么关系？

---

## 三、各场辩论

### 场次一：probe 小辩论（处理粒度打磨）

**文件**：`probe.md`

**目的**：在正式进入 topic1 之前，把「v3 处理粒度」这个核心架构问题打磨清楚。

**核心问题**：v3 的处理粒度——问题级（整个问题走流水线）和命题级（v2 状态机）——应当是**两层分离**、**相互替代**还是**统一重组**？

**设计说明**：1轮，无交叉质询，高打磨。裁判产出 topic1 的注入 message。

---

### 场次二：topic1（v3 综合架构设计）

**文件**：`topic1.md`

**背景注入**：
- v2 四引擎定义（已确立基础）
- topic3 深广双轨机制（已确立基础）
- Ssyram 的 v3 草案（待议起点）

**四个核心设计问题**：
- 问题 A：整体拓扑（流水线/迭代/分层/状态机）
- 问题 B：清晰度引擎位置（前置门控/后置澄清/分层）
- 问题 C：精度引擎角色（路由/加固/双重）
- 问题 D：深广引擎定位（v2 封装/新独立引擎）

**配置**：3轮 + 2次交叉质询，max_reply_tokens: 10000

---

### 场次三及后续（待 topic1 完成后规划）

根据 topic1 裁判产出的「未解问题」确定 topic2 议题。预期可能涉及：

- GapSpec 协议在 v3 中的适配（问题级 GapSpec vs 命题级 GapSpec 的类型差异）
- `bifurcation_contract` 的防诡辩验证机制
- RegulativeCache 的异步匹配效率问题
- 广度引擎「立场张力」机制的精确协议设计

---

## 四、最终原理体系

### 四个核心设计决策裁定结论

| 决策 | 议题 | 裁定 |
|------|------|------|
| **A** | 清晰度引擎放在哪里？ | 双层清晰度：问题级做结构化整理（`QuestionFrame`），命题级保留严格门控（`ClarityCompiler`） |
| **B** | 精度引擎是路由器还是加固者？ | 纯路由器（`PrecisionRoute.graph_delta` 永远为 `null`），任何改写必须通过独立 `RewriteStep` |
| **C** | 是否需要独立的深广引擎？ | 取消深广引擎，功能完全还原为 S4↔S5 状态转移 |
| **D** | Layer 1 和 Layer 2 之间的控制流架构？ | Layer 1 是可回退的薄状态机，通过异步批次派发（Epoch）与 Layer 2 交互，终止条件用 `hasRankingChangingRepair` 明确定义 |

---

### Layer 1 流水线架构

Layer 1 按以下节点顺序运行，是一个可被 Layer 2 反馈推着回退的薄状态机：

```
QuestionNormalizer (QN)
    ↓  输出 QuestionFrame（scope / stakeholders / evaluation_axes）
MacroBreadth (MB)
    ↓  输出 HypothesisDraft[]（含 tension_source / verifier_hint / ttl）
ClarityCompiler (CC)
    ↓  输出 TestableClaim[]（含 falsifier / assumptions / non_claim）
    ↓  未通过的草稿进入 parked 池（ttl -= 1）
Layer2Dispatch (D2)
    ↓  以 DispatchBatch 异步批次派发到 Layer 2
    ↓  Layer 2 返回 L2Return（verified / suspended / gaps / schema_challenges / rewrites）
PrecisionAggregator (PA)
    ↓  检查 ranking_delta.changed 和非同源 schema_challenges
    ↓  若连续 2 轮无变化 → 触发 TerminationReport
    ↓  否则调用 repair() 生成新草稿，循环回 CC
AnswerSynthesis (AS)
    ↓  输出多视角条件化答案 + regulative_residue 残余风险清单
```

终止判据（`hasRankingChangingRepair`）：Top-K 集合不变 AND 分数变化 < delta，连续 N=2 轮无变化则终止。终止时必须区分"构成性完成"（主要结论稳定）与"调节性残余"（仍有未解 GapSpec，标注为残余风险）。

---

### Layer 2 状态机核心接口

Layer 2 使用 v2 四引擎状态机处理单个 `TestableClaim`：

```
S1_CLARIFY  → 命题级清晰度门控（通过则进 S2，失败则 SUSPENDED）
S2_DEPTH    → 深度引擎前提追溯（无缺口则进 S3，有缺口则看类型）
                ↓ MISSING_DISCRIMINATOR → S5_BREADTH
                ↓ 其他缺口 → SUSPENDED(GAP_UNRESOLVED)
S3_PRECISION → 精度纯路由（route_target: DEPTH→S2 / BREADTH→S5 / STOP→S6）
S5_BREADTH   → 广度引擎候选搜索（命中且非同源→S2；否则→SchemaChallengeNotice）
S6_VERIFIED  → 输出 VerifiedClaim（status: VERIFIED | DEFENSIBLE）
```

深广引擎无独立层级，完全通过 S4(DepthProbe)↔S5(BreadthProbe) 状态转移实现（决策 C）。

---

### Layer 1 ↔ Layer 2 接口协议

```typescript
// Layer 1 → Layer 2 派发
type DispatchBatch = {
  batch_id: string;
  problem_id: string;
  claims: TestableClaim[];
  dispatch_policy: "PARALLEL" | "PRIORITY_BY_TENSION";
  budget: { max_claim_steps: number; max_schema_challenges: number };
};

// Layer 2 → Layer 1 返回
type L2Return = {
  batch_id: string;
  verified_claims: VerifiedClaim[];
  suspended_claims: SuspendedClaim[];
  new_gaps: GapSpec[];
  schema_challenges: SchemaChallengeNotice[];
  rewrites: RewriteStep[];           // RewriteStep 含 semantic_diff，精度不直接改图
  ranking_delta: {
    changed: boolean;
    affected_claim_ids: string[];
    reason: "NEW_EVIDENCE" | "DEFEAT" | "SCHEMA_SHIFT" | "NONE";
  };
};

// 终止报告（Layer 1 输出时附带）
type TerminationReport = {
  constitutive_done: boolean;
  regulative_residue: GapSpec[];
  reason: "NO_RANKING_CHANGE" | "BUDGET_EXHAUSTED" | "ALL_TOPK_STABLE";
};
```

完整类型定义（`ProblemStatement`、`QuestionFrame`、`HypothesisDraft`、`TestableClaim`、`VerifiedClaim`、`SuspendedClaim`、`GapSpec`、`SchemaChallengeNotice`、`PrecisionRoute`、`RewriteStep`）及伪代码骨架见 `topic1_debate_summary.md` 第二部分。

---

## 五、潜在问题与风险

### 实现难度最高的 3 个模块

**1. ClarityCompiler（命题级编译器）—— 难度：极高**

- 核心挑战：将自然语言 `HypothesisDraft.claim_sketch` 编译为结构化 `TestableClaim`（含 `falsifier`、`verifier_requirements` 等字段）。本质是受约束的自然语言理解 + 结构化生成。
- 主要风险：编译器倾向生成"安全但平庸"的命题（容易填充 falsifier），会系统性回避真正困难的主张；过于宽松则垃圾命题涌入 Layer 2。
- 缓解措施：显式 parked + ttl 机制（允许草稿多次尝试编译）；对编译结果做 replay regression 防止编译器随时间漂移。

**2. repair() 函数（Layer 1 修复逻辑）—— 难度：高**

- 核心挑战：根据 Layer 2 返回的异构信号（`GapSpec`、`SchemaChallengeNotice`、`SuspendedClaim`），创造性地生成新 `HypothesisDraft`，既要理解"缺什么"，又要提出"从哪里找"。
- 主要风险：修复逻辑太机械（仅把 gap 的 discriminator 塞进新草稿）→ 同义重复候选，Epoch 空转；太自由 → 偏离原始问题框架。
- 缓解措施：强制 repair 产出的草稿引用具体 gap_id 或 schema_challenge；通过同源检测（`is_homologous`）过滤本质相同的重复草稿。

**3. has_ranking_change() 终止判定 —— 难度：中高**

- 核心挑战：在涉及完全不同评估维度（交付速度 vs 人才留存）的异构 claim 之间建立可比较的评分体系。
- 主要风险：评分函数设计不当导致"终止振荡"——第 N 轮判定稳定，第 N+1 轮因微小扰动又判定不稳定，系统在终止边界反复横跳。
- 缓解措施：双重条件（Top-K 集合不变 AND 分数变化 < delta）+ 硬性 MAX_EPOCHS 上限作为保底；评分函数基于 `evaluation_axes` 加权组合，权重在 `QuestionFrame` 中预先声明。

---

### 规则集可能失败的场景

| 场景 | 可能失败的模块 | 说明 |
|------|---------------|------|
| 问题级结构化后超过 80% 草稿无法通过命题级编译 | ClarityCompiler | 说明问题级约束太弱，需前移更多限制 |
| 大量矛盾仅是简单参数范围重叠（如 X>5 vs X>3） | PrecisionRoute（硬分离方案） | 强制走 RewriteStep 可能导致不可接受的延迟；此时可考虑引入极窄"微改写白名单"但须附完整 semantic_diff |
| Layer 2 处理时间极度不均匀（某些 claim 秒完，某些需数分钟） | Layer2Dispatch（纯批次模式） | 快的 claim 等慢的，可引入部分流式返回机制（优化问题，不影响核心架构） |
| 未来出现"问题级覆盖扩展"需求（需重审整个问题框架，不只是单个 claim 的深度缺口） | S4↔S5 状态转移 | 此类需求应由 Layer 1 的 MacroBreadth 重新触发，而非在 Layer 2 内新设引擎 |

---

## 六、文件索引

```
examples/new-debate-v3/
├── README.md                            ← 本文件
├── probe.md                             ← 小辩论（打磨「处理粒度」架构选择）
├── probe_debate_log.md                  ← probe 辩论记录 [已生成]
├── probe_debate_summary.md              ← probe 裁判总结 [已生成]
├── topic1.md                            ← v3 综合架构设计（主辩题）
├── topic1_debate_log.checkpoint_before_round3.md  ← 第3轮前备份
├── topic1_debate_log.md                 ← topic1 完整辩论记录（3轮+2次交叉质询）[已生成]
└── topic1_debate_summary.md             ← topic1 裁判总结（含完整类型定义+伪代码）[已生成]

# 依赖基础（来自 v2）
../new-debate-v2/
├── topic3_debate_summary.md             ← 深广双轨机制总结（已注入 topic1 正文）
├── topic2_debate_summary.md             ← GapSpec 推荐字段集
└── README.md                            ← v2 完整原理体系（v3 参考基础）
```

---

## 七、运行方式

```bash
# 先跑 probe（打磨处理粒度问题）
debate-tool run examples/new-debate-v3/probe.md

# 根据 probe 裁判总结更新 topic1.md，然后跑 topic1
debate-tool run examples/new-debate-v3/topic1.md

# 如需续跑 topic1（注入 probe 裁判建议的 message）
debate-tool resume examples/new-debate-v3/topic1_debate_log.md
```

---

*本框架设计于 2026-03-09，基于 new-debate-v2 七场辩论产出（Claude Sonnet 4.6）*
