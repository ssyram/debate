# GapSpec 协议与先验亲和性剪枝：深度边界锚定广度的具体实现 裁判总结

> 2026-03-08T03:13:19.688880

这是一场质量极高的架构与协议设计辩论。三位参与者分别代表了**工程实用主义（Linus）**、**类型与契约设计（Ssyram）**以及**认识论与系统边界（Kant）**。辩论成功地将一个模糊的自然语言 JSON 推进到了具备强类型约束和溯源机制的系统接口。

以下是本裁判的最终裁定：

### 一、认知增量评估

本次讨论实现了三次关键的认知推进：

1. **从“格式校验”到“认识论溯源（Trace Grounding）”**
   * **事件**：Linus [4] 和 [7] 攻击 Ssyram [2] 的 TypeScript 定义，指出 `validateGapSpec` 只能防格式错误，不能防 LLM 幻觉（“包装成强类型的幻觉”）。
   * **增量**：确立了 GapSpec 必须包含 `TraceGrounding`，将系统设计的焦点从“语法正确性”转移到了“逻辑合法性”。
2. **从“异常驱动”扩展为“多源经验析取（Provenance Union）”**
   * **事件**：Ssyram [11] 和 Linus [13] 联合反驳 Kant [9] 提出的“必须基于 Anomaly”的硬性门槛。
   * **增量**：明确了系统的探索能力不能仅靠“事故（异常）驱动”，引入了 `CoverageHole`（覆盖盲区）和 `OntologyNeighbor`（本体邻居），并将其固化为代数数据类型（ADT）的析取来源。
3. **拆解亲和性剪枝：区分“存在性（Witness）”与“分裂性（Polarity）”**
   * **事件**：Linus [10] 攻击 Ssyram [8] 的 `witness` 方案，指出证明候选值存在（如“新手/专家”）不等于证明它们能让命题产生正反分裂。
   * **增量**：明确了剪枝必须是两段式的——先验真（值域在本体库中存在）+ 逻辑真（能对同一观测物产生方向相反的预测）。

---

### 二、四维度评分

* **广度 (8/10)**：覆盖了连续变量与离散变量的处理、异常触发与主动探索（Coverage Hole）的边界。**忽视的角度**：如果底层的 Ontology（本体库）本身存在概念漂移或错误，GapSpec 的溯源机制将如何降级？
* **深度 (9/10)**：极深。Kant 成功地将“分析判断 vs 综合判断”的哲学概念映射到了“LLM 同义改写 vs LLM 引入新维度”的工程灾难上，迫使 Linus 和 Ssyram 放弃了简单的字符串匹配，转向 AST 节点和 Trace ID 的硬链接。
* **精度 (9/10)**：极高。Linus 敏锐地抓住了 Ssyram 方案中 `exists c1/c2` 无法保证预测符号翻转的逻辑漏洞；Ssyram 也精准指出了 Linus 早期 `novelty_tokens <= 3` 是一种粗暴且会扼杀系统发现能力的教条阈值。
* **清晰度 (8/10)**：参与者均使用了 TypeScript/Python 伪代码来具象化自己的主张，使得“接收者能构造出合理反例”的标准被完美执行（例如 Linus 用 `motivational stability` 构造的反例）。

---

### 三、未解决的核心分歧

1. **二律背反（Polarity Split）的机器可判定性仍未落地**
   * **原因**：虽然三方都同意候选维度必须能将原命题“分裂”为正反两面，但 Linus 要求的 `step3_accept` 最小可执行判定到底怎么写？是让 LLM 玩角色扮演输出两个预测？还是必须映射到具体的数学符号翻转？这里依然停留在伪代码层面，缺乏防 LLM 诡辩的机制。
2. **S4.5（网关层）失败后的状态机路由语义**
   * **原因**：Linus [10] 提出质疑，如果 GapSpec 缺乏溯源被网关拦截，系统是应该重试、降级为纯逻辑闭包、还是直接丢弃该推理链？辩论后期大家的精力集中在类型定义上，遗漏了异常流转（Error Routing）的定义。

---

### 四、最终裁定

基于辩论共识与工程可行性，本裁判做出以下执行裁定：

#### 1. GapSpec 的推荐最小字段集
采纳 Kant 的 ADT（代数数据类型）思想与 Linus/Ssyram 的溯源机制，废弃所有自由文本解释。

```typescript
// 1. 经验溯源（必须且只能是以下四种之一）
type Provenance = 
  | { kind: "trace_span", trace_id: string, ast_node_id: string }
  | { kind: "anomaly", anomaly_id: string }
  | { kind: "coverage_hole", missing_slice: string }
  | { kind: "ontology_neighbor", node_id: string };

// 2. 核心协议
interface GapSpec {
  gap_id: string;
  target_claim_ast_id: string; // 锚定原命题
  gap_kind: "scope_split" | "proxy_break" | "mediator"; // 决定后续验证逻辑
  provenance: Provenance; // 解决“幻觉/脑补”问题
  required_observables: string[]; // 必须是系统中已注册的 Metric/Field ID
  
  // 机器可执行的分裂契约
  bifurcation_contract: {
    thesis_condition: string;
    antithesis_condition: string;
    expected_delta_sign: ">0" | "<0" | "!=0"; // 强制要求明确的预测差异
  };
}
```

#### 2. 先验亲和性剪枝的推荐实现方案
必须采用**“两段式硬拦截”**，禁止让 LLM 一次性完成判断：
* **Stage 1 (Witness Check - 存在性校验)**：候选维度的取值（`cand.values`）必须在 Ontology 中有注册，或能通过确定性分桶（Deterministic Binning）得出。否则直接剪枝。
* **Stage 2 (Polarity Check - 分裂性校验)**：将 `cand.values` 注入 GapSpec 的 `bifurcation_contract`。要求 LLM（或轻量判别模型）仅输出 `[True, False]` 来回答：“当取值为 A 时，是否必然导致 expected_delta_sign？”。如果无法形成对立，立即剪枝。

#### 3. 引擎重组裁定：四引擎变三引擎
**裁定：合并 S4（深度生成）与 S4.5（溯源网关），重组为“假设综合与溯源引擎（Hypothesis Synthesis & Grounding Engine）”。**
* **理由**：辩论已充分证明，脱离了 Trace/Anomaly 溯源的 GapSpec 生成毫无意义（即 Kant 所谓的“先验幻相”）。生成与校验不应是两个异步的流水线节点，而应在同一个上下文中完成。如果 LLM 生成了 GapSpec 但无法提供合法的 `Provenance`，该生成在引擎内部就应被视为失败并重试，而不应把“伪来源垃圾”抛给下游状态机。

#### 4. 下一步最值得深挖的具体问题
**“如何设计 `bifurcation_contract` 的防诡辩 Prompt 或验证函数？”**
* **背景**：LLM 极擅长“和稀泥”，即使你要求它做正反预测，它也可能生成“A导致提升，B导致提升较少”这种伪分裂。下一步必须明确：如何用最低的算力成本，强制 LLM 或规则引擎严格判定候选维度是否真正构成了“二律背反”（即一个有效，另一个失效/反转），这是决定 S5（广度引擎）会不会被垃圾候选淹没的最后一道防线。