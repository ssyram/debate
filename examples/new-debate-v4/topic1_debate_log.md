# v4 认知引擎：整体系统设计的自由探索 辩论日志

> 2026-03-11T18:37:59.221079

---


### [1] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-11T18:37:59.221023*

# 第一部分：系统全景解释

## 一、这个系统是什么，解决什么问题

### 问题背景

当我们向大语言模型（LLM）提出一个复杂的开放域问题——比如"设计一个新的编程语言"、"分析全球供应链的脆弱性"、"设计一个认知引擎系统"——我们通常会得到一个看起来流畅但实际上存在大量问题的回答：

1. **广度不足**：模型只探索了问题空间的一小部分，遗漏了关键维度
2. **深度不足**：每个维度都只是浅尝辄止，缺乏严谨推理
3. **自洽性差**：不同部分之间可能存在矛盾，但模型不会自我检查
4. **无法区分确定性**：所有结论都以同样的自信语气呈现，无论它们是经过严格论证的还是随意猜测的
5. **不可追溯**：你无法知道某个结论是怎么得出的，依赖了什么前提

### 解决方案概述

**v4 认知引擎**是一个多智能体辩论系统，它将一个复杂问题的解决过程分解为多个专业化的角色（引擎），让它们以结构化的方式协作、辩论、验证，最终产出一个**带有明确置信度标注的、可追溯的、自洽的**答案。

核心思想可以用一句话概括：**不要让一个模型一次性回答复杂问题，而是让多个专业化角色反复探索、质疑、裁决，把思考过程外化为一个可检查的知识图谱。**

---

## 二、核心数据结构：DAG（有向无环图）

在理解各组件之前，必须先理解它们共同操作的核心数据结构。

### 什么是 DAG

DAG 是一个**有向无环图**（Directed Acyclic Graph），它是整个系统的"共享黑板"——所有引擎都在这个图上读写。图中的每个节点代表一个知识单元，边代表节点之间的关系。

### 节点类型

系统定义了以下节点类型：

| 节点类型 | 含义 | 示例 |
|---------|------|------|
| **QuestionNode** | 一个待回答的问题或子问题 | "终止条件应该如何设计？" |
| **ThesisNode** | 对某个问题的回答/主张 | "应该使用双轨终止条件" |
| **EvidenceNode** | 支持或反对某个主张的证据/论据 | "双轨设计可以避免过早终止" |
| **ConflictNode** | 标记两个节点之间的矛盾 | "主张A说用固定阈值，主张B说用动态阈值" |
| **SynthesisNode** | 对多个节点的综合/调和 | "综合A和B：在不同阶段使用不同策略" |

### 边类型

节点之间的边表示关系：

- **supports**：A 支持 B
- **contradicts**：A 与 B 矛盾
- **refines**：A 是 B 的细化
- **decomposes_to**：A 分解为子问题 B
- **depends_on**：A 依赖 B 的结论

### 双轨状态系统

每个节点携带两种不同性质的状态信息：

**构成性状态（Constitutive Status）**——这是一个离散的标签，表示节点在认知流程中的"身份"：

| 状态 | 含义 |
|------|------|
| **Proposed** | 刚被提出，尚未经过任何审查 |
| **Contested** | 有人提出了反对意见，正在争议中 |
| **Validated** | 经过裁判裁决，被确认为成立 |
| **Rejected** | 经过裁判裁决，被否决 |
| **Hypothesis** | 有一定支持但证据不足以确认，标记为假说 |

**调节性分数（Regulatory Scores）**——这是连续的数值，用于引导系统的注意力分配：

| 分数 | 含义 | 范围 |
|------|------|------|
| **confidence** | 对该节点内容正确性的置信度 | 0.0 - 1.0 |
| **controversy** | 该节点引发争议的程度 | 0.0 - 1.0 |
| **impact** | 该节点对最终答案的重要程度 | 0.0 - 1.0 |

**为什么需要双轨？** 因为它们回答不同的问题：
- 构成性状态回答"这个结论的认知地位是什么"——是已验证的事实，还是待检验的假说？
- 调节性分数回答"系统接下来应该关注什么"——高争议+高影响的节点应该优先处理

这两者是正交的。一个 Validated 节点可能 confidence=0.75（验证通过但不是铁证），一个 Hypothesis 节点可能 confidence=0.6（有一定支持但不够）。

---

## 三、系统组件详解

### 3.1 维护器（DAG Maintainer）

**职责**：维护 DAG 的结构完整性和一致性。它是 DAG 的"数据库管理员"。

**具体工作**：
- 接收其他引擎的操作请求（添加节点、添加边、修改状态）
- 验证操作的合法性（比如不能创建环、不能给不存在的节点添加边）
- 维护节点的索引，支持按状态、类型、分数等查询
- 当节点状态变化时，传播影响（比如一个 ThesisNode 被 Rejected，依赖它的其他节点需要重新评估）
- **初始化**：接收输入问题，创建根 QuestionNode，建立初始 DAG 结构

**关键设计决策**：维护器不做任何"思考"——它不判断内容的对错，只确保数据结构的一致性。这是一个纯粹的基础设施组件。

### 3.2 广度引擎（Breadth Engine）

**职责**：探索问题空间的广度——发现子问题、识别维度、确保没有重要方面被遗漏。

**工作方式**：
1. 接收一个 QuestionNode（或整个 DAG 的当前状态）
2. 分析当前已覆盖的维度
3. 识别尚未探索的维度和子问题
4. 为每个新发现的维度创建新的 QuestionNode
5. 对已有的 ThesisNode 提出初步的替代方案

**输入**：当前 DAG 状态 + 焦点节点
**输出**：一组新的 QuestionNode 和初步的 ThesisNode（状态为 Proposed）

**类比**：广度引擎像是一个头脑风暴的主持人——它的工作是确保所有重要话题都被放上桌面，但不负责深入讨论任何一个话题。

### 3.3 深度引擎（Depth Engine）

**职责**：对特定节点进行深入分析——构建论证链、寻找证据、细化方案。

**工作方式**：
1. 接收一个需要深入分析的节点（通常是高 impact 但低 confidence 的 ThesisNode）
2. 构建支持或反对该节点的论证链
3. 创建 EvidenceNode 来支撑论证
4. 如果发现需要进一步分解，创建更细粒度的子问题
5. 更新相关节点的 confidence 分数

**输入**：目标节点 + 相关上下文（DAG 中与该节点相关的子图）
**输出**：一组 EvidenceNode、可能的 ThesisNode 细化、更新的 confidence 分数

**类比**：深度引擎像是一个专题研究员——给它一个具体话题，它会深入挖掘，给出详细的分析和证据。

### 3.4 攻击引擎（Attack Engine）

**职责**：质疑和挑战现有结论——寻找矛盾、漏洞、隐含假设、反例。

**工作方式**：
1. 扫描 DAG 中的 ThesisNode（特别是那些 confidence 较高但尚未被挑战的）
2. 尝试找到反驳论据
3. 检查不同 ThesisNode 之间的一致性
4. 当发现矛盾时，创建 ConflictNode 连接矛盾的双方
5. 将被挑战的节点状态从 Proposed 改为 Contested

**输入**：当前 DAG 状态（特别关注 Proposed 和 Validated 状态的节点）
**输出**：ConflictNode、反驳 EvidenceNode、状态变更请求

**关键机制——ConflictNode 的创建过程**：
1. 攻击引擎发现节点 A 和节点 B 之间存在矛盾
2. 创建一个 ConflictNode C，包含矛盾的具体描述
3. 添加边：C → A（contradicts）和 C → B（contradicts）
4. 将 A 和 B 的状态改为 Contested
5. 提高 A 和 B 的 controversy 分数

**类比**：攻击引擎像是一个魔鬼代言人（Devil's Advocate）——它的工作就是找茬，确保没有未经检验的假设蒙混过关。

### 3.5 裁判引擎（Judge Engine）

**职责**：对争议做出裁决——当节点处于 Contested 状态时，评估正反双方的论据，做出最终判断。

**工作方式**：
1. 从 DAG 中选取 Contested 状态的节点（优先选择高 impact 的）
2. 收集与该节点相关的所有证据（支持和反对的 EvidenceNode）
3. 评估证据的质量和相关性
4. 做出裁决：
   - **Validated**：证据充分支持，确认成立
   - **Rejected**：证据充分反对，否决
   - **Hypothesis**：有一定支持但不够确定，标记为假说
   - **保持 Contested**：需要更多信息，暂不裁决
5. 记录裁决理由（创建 SynthesisNode 解释裁决逻辑）

**输入**：Contested 节点 + 所有相关证据
**输出**：状态变更（Validated/Rejected/Hypothesis）+ 裁决理由 + 更新的 confidence 分数

**Validated vs Hypothesis 的区别**：
- **Validated**：系统有足够信心认为这个结论是正确的。它经过了质疑和辩护，证据链完整。用户可以较高信心地采纳。
- **Hypothesis**：系统认为这个方向可能是对的，但证据不足以确认。可能是因为问题本身具有不确定性，或者需要外部信息才能验证。用户应将其视为"值得进一步探索的方向"而非确定结论。

这个区分的意义在于**诚实地表达认知边界**——系统不会把所有东西都包装成确定结论，而是明确告诉用户"这些我比较确定，这些我不太确定"。

### 3.6 协议层（Protocol Layer）

**职责**：协调各引擎的调用顺序和交互方式。它是整个系统的"指挥官"。

**工作方式**：

协议层运行一个主循环，每次迭代包含以下步骤：

```
REPEAT:
  1. [广度阶段] 调用广度引擎，探索新维度
  2. [深度阶段] 选择高优先级节点，调用深度引擎深入分析
  3. [攻击阶段] 调用攻击引擎，质疑现有结论
  4. [裁决阶段] 调用裁判引擎，处理争议
  5. [评估阶段] 检查终止条件
UNTIL 终止条件满足
```

**优先级选择逻辑**：
- 深度引擎的目标选择：优先选择 `impact × (1 - confidence)` 最高的节点（重要但不确定的节点最需要深入分析）
- 裁判引擎的目标选择：优先选择 `impact × controversy` 最高的 Contested 节点（重要且争议大的节点最需要裁决）

---

## 四、终止条件的设计逻辑

系统不能无限运行，需要知道什么时候"够了"。终止条件采用**双轨设计**：

### 硬性终止条件（任一满足即停止）
- **最大迭代次数**：防止无限循环（比如最多 20 轮）
- **最大 token 消耗**：防止资源耗尽
- **用户中断**：用户随时可以要求停止

### 软性终止条件（综合评估）
- **覆盖率**：所有根问题的子问题中，有多少比例已经有了 Validated 或 Hypothesis 的回答？
- **稳定性**：最近 N 轮迭代中，DAG 的变化量是否趋近于零？（没有新节点被创建，没有状态变更）
- **争议解决率**：Contested 节点占总节点的比例是否低于阈值？

**直觉**：当系统已经探索了足够多的维度（覆盖率高）、不再产生新的发现（稳定）、大部分争议都已解决（争议率低）时，继续运行的边际收益很小，应该停止。

---

## 五、最终输出结构

系统运行结束后，产出以下结构化输出：

1. **Validated 主线**：所有 Validated 状态的节点，按 DAG 的拓扑顺序组织，形成一个连贯的、经过验证的答案骨架
2. **Hypothesis 清单**：所有 Hypothesis 状态的节点，附带支持证据和不确定原因，供用户进一步探索
3. **未决 Issue**：仍处于 Contested 或 Proposed 状态的重要节点，说明为什么没有解决
4. **推理追溯**：每个 Validated 结论都可以追溯到支持它的证据链和裁决记录

---

## 六、系统的核心价值

| 传统 LLM 回答 | v4 认知引擎 |
|--------------|------------|
| 一次性生成，无法检查过程 | 思考过程外化为 DAG，完全可检查 |
| 所有结论同等自信 | 明确区分 Validated / Hypothesis / 未决 |
| 容易遗漏维度 | 广度引擎专门负责发现遗漏 |
| 不会自我质疑 | 攻击引擎专门负责找茬 |
| 矛盾可能被忽略 | ConflictNode 机制确保矛盾被显式处理 |
| 无法追溯推理 | 每个结论都有完整的证据链 |

---

# 第二部分：完整示例走通

## 输入

- **问题**："设计一个能处理开放域大问题的认知引擎"
- **Objective**："产出一个尽量细节的可用设计方案及其辩护"

---

## Step 0：维护器建立初始 DAG

维护器接收输入，创建初始结构：

```
[Q-ROOT] QuestionNode
  content: "设计一个能处理开放域大问题的认知引擎"
  objective: "产出一个尽量细节的可用设计方案及其辩护"
  status: Proposed
  confidence: 0.0
  controversy: 0.0
  impact: 1.0
```

维护器还会做一个初步的问题分解（或者将此任务委托给广度引擎的第一次调用）：

```
初始 DAG:
  Q-ROOT (impact=1.0)
```

---

## Step 1：广度引擎的第一次调用

### 输入

```json
{
  "focus_node": "Q-ROOT",
  "current_dag": {
    "nodes": ["Q-ROOT"],
    "edges": []
  },
  "instruction": "分析这个问题，识别需要回答的核心子问题和关键维度"
}
```

### 广度引擎的思考过程

广度引擎分析"设计认知引擎"这个问题，识别出以下维度：

1. 系统的整体架构是什么？（单体 vs 多智能体？）
2. 核心数据结构是什么？（如何表示知识？）
3. 有哪些功能组件？各自职责是什么？
4. 组件之间如何协调？（协议/调度）
5. 如何保证输出质量？（验证机制）
6. 何时停止？（终止条件）
7. 最终输出的格式是什么？

### 输出

```json
{
  "new_nodes": [
    {
      "id": "Q-ARCH",
      "type": "QuestionNode",
      "content": "系统应该采用什么整体架构？",
      "status": "Proposed",
      "confidence": 0.0,
      "impact": 0.95
    },
    {
      "id": "Q-DATA",
      "type": "QuestionNode",
      "content": "核心数据结构应该如何设计？",
      "status": "Proposed",
      "confidence": 0.0,
      "impact": 0.9
    },
    {
      "id": "Q-COMPONENTS",
      "type": "QuestionNode",
      "content": "需要哪些功能组件？各自职责是什么？",
      "status": "Proposed",
      "confidence": 0.0,
      "impact": 0.9
    },
    {
      "id": "Q-PROTOCOL",
      "type": "QuestionNode",
      "content": "组件之间如何协调？调度策略是什么？",
      "status": "Proposed",
      "confidence": 0.0,
      "impact": 0.85
    },
    {
      "id": "Q-QUALITY",
      "type": "QuestionNode",
      "content": "如何保证输出质量和自洽性？",
      "status": "Proposed",
      "confidence": 0.0,
      "impact": 0.85
    },
    {
      "id": "Q-TERMINATION",
      "type": "QuestionNode",
      "content": "终止条件应该如何设计？",
      "status": "Proposed",
      "confidence": 0.0,
      "impact": 0.8
    },
    {
      "id": "Q-OUTPUT",
      "type": "QuestionNode",
      "content": "最终输出应该是什么格式和结构？",
      "status": "Proposed",
      "confidence": 0.0,
      "impact": 0.75
    },
    {
      "id": "T-ARCH-MULTI",
      "type": "ThesisNode",
      "content": "应该采用多智能体辩论架构，不同角色负责不同认知功能",
      "status": "Proposed",
      "confidence": 0.5,
      "impact": 0.95
    },
    {
      "id": "T-DATA-DAG",
      "type": "ThesisNode",
      "content": "应该使用 DAG（有向无环图）作为核心数据结构来表示知识",
      "status": "Proposed",
      "confidence": 0.5,
      "impact": 0.9
    }
  ],
  "new_edges": [
    {"from": "Q-ROOT", "to": "Q-ARCH", "type": "decomposes_to"},
    {"from": "Q-ROOT", "to": "Q-DATA", "type": "decomposes_to"},
    {"from": "Q-ROOT", "to": "Q-COMPONENTS", "type": "decomposes_to"},
    {"from": "Q-ROOT", "to": "Q-PROTOCOL", "type": "decomposes_to"},
    {"from": "Q-ROOT", "to": "Q-QUALITY", "type": "decomposes_to"},
    {"from": "Q-ROOT", "to": "Q-TERMINATION", "type": "decomposes_to"},
    {"from": "Q-ROOT", "to": "Q-OUTPUT", "type": "decomposes_to"},
    {"from": "T-ARCH-MULTI", "to": "Q-ARCH", "type": "answers"},
    {"from": "T-DATA-DAG", "to": "Q-DATA", "type": "answers"}
  ]
}
```

### DAG 状态（第一轮广度后）

```
Q-ROOT
├── Q-ARCH ← T-ARCH-MULTI (Proposed, conf=0.5)
├── Q-DATA ← T-DATA-DAG (Proposed, conf=0.5)
├── Q-COMPONENTS
├── Q-PROTOCOL
├── Q-QUALITY
├── Q-TERMINATION
└── Q-OUTPUT
```

---

## Step 2：深度引擎的一次典型调用

### 选择目标

协议层计算优先级：`impact × (1 - confidence)`

| 节点 | impact | confidence | 优先级 |
|------|--------|------------|--------|
| T-ARCH-MULTI | 0.95 | 0.5 | 0.475 |
| T-DATA-DAG | 0.9 | 0.5 | 0.45 |
| Q-COMPONENTS | 0.9 | 0.0 | 0.9（但这是问题节点，需要先生成回答） |

协议层选择 **T-ARCH-MULTI**（"应该采用多智能体辩论架构"）进行深入分析。

### 输入

```json
{
  "target_node": "T-ARCH-MULTI",
  "context": {
    "parent_question": "Q-ARCH: 系统应该采用什么整体架构？",
    "root_objective": "产出一个尽量细节的可用设计方案及其辩护",
    "related_nodes": ["T-DATA-DAG"]
  },
  "instruction": "深入分析这个主张，构建支持论证，识别关键假设，评估可行性"
}
```

### 深度引擎的分析过程

深度引擎对"多智能体辩论架构"进行深入分析：

**论证1**：单一 LLM 调用的认知局限性
- 单次调用受限于模型的注意力窗口和生成惯性
- 无法同时扮演"提出者"和"批评者"角色（认知偏差）
- 多智能体可以通过角色分离克服这一限制

**论证2**：辩论机制的质量保证价值
- 对抗性检验是科学方法的核心（同行评审、可证伪性）
- 辩论迫使每个主张都必须经受质疑
- 这比单纯的"自我反思"更有效，因为角色分离减少了确认偏差

**论证3**：可行性分析
- 现有 LLM 能够遵循角色指令（广泛验证）
- 多次调用的成本可以通过结构化 prompt 控制
- 主要风险：引擎之间的信息传递可能丢失上下文

### 输出

```json
{
  "new_nodes": [
    {
      "id": "E-ARCH-1",
      "type": "EvidenceNode",
      "content": "单一 LLM 调用存在认知局限：注意力窗口限制、生成惯性、无法同时扮演对立角色。多智能体架构通过角色分离克服这些限制。",
      "status": "Proposed",
      "confidence": 0.75,
      "impact": 0.8
    },
    {
      "id": "E-ARCH-2",
      "type": "EvidenceNode",
      "content": "对抗性检验（辩论）是比自我反思更有效的质量保证机制，因为角色分离减少了确认偏差。类比：科学同行评审。",
      "status": "Proposed",
      "confidence": 0.8,
      "impact": 0.85
    },
    {
      "id": "E-ARCH-3",
      "type": "EvidenceNode",
      "content": "可行性风险：引擎之间的信息传递可能丢失上下文，需要精心设计 context 传递机制。",
      "status": "Proposed",
      "confidence": 0.7,
      "impact": 0.7
    }
  ],
  "new_edges": [
    {"from": "E-ARCH-1", "to": "T-ARCH-MULTI", "type": "supports"},
    {"from": "E-ARCH-2", "to": "T-ARCH-MULTI", "type": "supports"},
    {"from": "E-ARCH-3", "to": "T-ARCH-MULTI", "type": "supports"}
  ],
  "score_updates": [
    {"node": "T-ARCH-MULTI", "confidence": 0.7}
  ]
}
```

### DAG 状态（深度分析后）

```
Q-ROOT
├── Q-ARCH ← T-ARCH-MULTI (Proposed, conf=0.7)
│              ├── E-ARCH-1 (supports, conf=0.75)
│              ├── E-ARCH-2 (supports, conf=0.8)
│              └── E-ARCH-3 (supports, conf=0.7, 标记了风险)
├── Q-DATA ← T-DATA-DAG (Proposed, conf=0.5)
├── Q-COMPONENTS
├── Q-PROTOCOL
├── Q-QUALITY
├── Q-TERMINATION
└── Q-OUTPUT
```

---

## Step 3：攻击引擎发现 ConflictNode 的全过程

### 背景

假设经过几轮迭代后，DAG 中已经有了更多内容。特别是关于终止条件，出现了两个竞争性的主张：

```
Q-TERMINATION
├── T-TERM-FIXED: "应该使用固定阈值终止条件（如：当所有节点 confidence > 0.8 时停止）"
│   ├── E-TERM-F1: "固定阈值简单明确，易于实现和理解" (supports)
│   └── status: Proposed, confidence: 0.6
│
└── T-TERM-ADAPTIVE: "应该使用自适应终止条件（基于 DAG 变化率的稳定性检测）"
    ├── E-TERM-A1: "不同问题的复杂度不同，固定阈值无法适应" (supports)
    └── status: Proposed, confidence: 0.6
```

### 攻击引擎的调用

#### 输入

```json
{
  "scan_scope": "all_proposed_and_validated_nodes",
  "current_dag": "... (完整 DAG 状态) ...",
  "instruction": "寻找矛盾、漏洞、未经检验的假设、反例"
}
```

#### 攻击引擎的分析过程

攻击引擎扫描 DAG，发现以下问题：

**发现1：T-TERM-FIXED 和 T-TERM-ADAPTIVE 之间存在直接矛盾**
- T-TERM-FIXED 主张使用固定阈值
- T-TERM-ADAPTIVE 主张使用自适应机制
- 这两者不能同时为真（至少不能在同一层面上同时为真）

**发现2：T-TERM-FIXED 有一个未经检验的假设**
- 它假设存在一个对所有问题都合适的 confidence 阈值
- 但不同类型的问题（事实性 vs 设计性 vs 价值判断性）的"合理 confidence"差异很大

**发现3：对 T-ARCH-MULTI 的一个挑战**
- 多智能体架构假设不同角色能产生真正不同的视角
- 但如果底层都是同一个 LLM，角色分离可能只是表面的

#### 输出

```json
{
  "new_nodes": [
    {
      "id": "CONFLICT-TERM-1",
      "type": "ConflictNode",
      "content": "T-TERM-FIXED 和 T-TERM-ADAPTIVE 在终止策略上存在直接矛盾：固定阈值 vs 自适应机制。核心分歧在于是否存在通用的终止标准。",
      "status": "Proposed",
      "confidence": 0.9,
      "impact": 0.8
    },
    {
      "id": "E-ATTACK-TERM-1",
      "type": "EvidenceNode",
      "content": "反驳 T-TERM-FIXED：不同类型的问题（事实性 vs 设计性 vs 价值判断性）对 confidence 的合理期望差异很大。事实性问题可能达到 0.95，而设计性问题 0.7 可能就是合理上限。固定阈值 0.8 对前者太低，对后者太高。",
      "status": "Proposed",
      "confidence": 0.8,
      "impact": 0.75
    },
    {
      "id": "E-ATTACK-ARCH-1",
      "type": "EvidenceNode",
      "content": "对 T-ARCH-MULTI 的质疑：如果所有引擎底层使用同一个 LLM，角色分离可能只是 prompt 层面的，不能保证产生真正独立的视角。需要论证为什么 prompt 级别的角色分离足以产生有意义的对抗。",
      "status": "Proposed",
      "confidence": 0.65,
      "impact": 0.8
    }
  ],
  "new_edges": [
    {"from": "CONFLICT-TERM-1", "to": "T-TERM-FIXED", "type": "contradicts"},
    {"from": "CONFLICT-TERM-1", "to": "T-TERM-ADAPTIVE", "type": "contradicts"},
    {"from": "E-ATTACK-TERM-1", "to": "T-TERM-FIXED", "type": "contradicts"},
    {"from": "E-ATTACK-ARCH-1", "to": "T-ARCH-MULTI", "type": "contradicts"}
  ],
  "status_changes": [
    {"node": "T-TERM-FIXED", "new_status": "Contested", "controversy": 0.8},
    {"node": "T-TERM-ADAPTIVE", "new_status": "Contested", "controversy": 0.6},
    {"node": "T-ARCH-MULTI", "new_status": "Contested", "controversy": 0.5}
  ]
}
```

### DAG 状态（攻击后）

```
Q-TERMINATION
├── T-TERM-FIXED (CONTESTED, conf=0.6, controversy=0.8)
│   ├── E-TERM-F1 (supports)
│   ├── E-ATTACK-TERM-1 (contradicts) ← "固定阈值不适应不同问题类型"
│   └── CONFLICT-TERM-1 (contradicts) ← "与 T-TERM-ADAPTIVE 矛盾"
│
└── T-TERM-ADAPTIVE (CONTESTED, conf=0.6, controversy=0.6)
    ├── E-TERM-A1 (supports)
    └── CONFLICT-TERM-1 (contradicts) ← "与 T-TERM-FIXED 矛盾"

Q-ARCH
└── T-ARCH-MULTI (CONTESTED, conf=0.7, controversy=0.5)
    ├── E-ARCH-1, E-ARCH-2, E-ARCH-3 (supports)
    └── E-ATTACK-ARCH-1 (contradicts) ← "同一 LLM 的角色分离可能不够"
```

---

## Step 4：裁判引擎处理 Contested 情况

### 选择目标

裁判引擎计算优先级：`impact × controversy`

| 节点 | impact | controversy | 优先级 |
|------|--------|-------------|--------|
| T-TERM-FIXED | 0.8 | 0.8 | 0.64 |
| T-ARCH-MULTI | 0.95 | 0.5 | 0.475 |
| T-TERM-ADAPTIVE | 0.8 | 0.6 | 0.48 |

裁判选择 **T-TERM-FIXED**（优先级最高）和相关的 **CONFLICT-TERM-1** 一起处理。

### 裁判处理终止条件争议

#### 输入

```json
{
  "contested_nodes": ["T-TERM-FIXED", "T-TERM-ADAPTIVE"],
  "conflict": "CONFLICT-TERM-1",
  "supporting_evidence": {
    "T-TERM-FIXED": ["E-TERM-F1: 简单明确，易于实现"],
    "T-TERM-ADAPTIVE": ["E-TERM-A1: 不同问题复杂度不同"]
  },
  "opposing_evidence": {
    "T-TERM-FIXED": ["E-ATTACK-TERM-1: 固定阈值不适应不同问题类型"]
  },
  "instruction": "评估双方论据，做出裁决"
}
```

#### 裁判的分析过程

**评估 T-TERM-FIXED（固定阈值）**：
- 支持论据：简单明确（E-TERM-F1）——这是真的，但"简单"不是充分理由
- 反对论据：不适应不同问题类型（E-ATTACK-TERM-1）——这个反驳很有力，因为系统明确要处理"开放域"问题，问题类型的多样性是核心需求
- 裁决：**Rejected**。固定阈值作为唯一终止机制不可行。但"简单明确"的优点可以保留——作为硬性上限（fallback）而非主要机制。

**评估 T-TERM-ADAPTIVE（自适应终止）**：
- 支持论据：适应不同问题复杂度（E-TERM-A1）——合理
- 但缺乏具体机制描述——"自适应"是什么意思？基于什么信号？
- 裁决：**Hypothesis**。方向正确但细节不足，需要进一步细化。

**综合裁决**：创建一个 SynthesisNode 来调和双方。

#### 输出

```json
{
  "decisions": [
    {
      "node": "T-TERM-FIXED",
      "new_status": "Rejected",
      "confidence": 0.2,
      "reasoning": "固定阈值作为唯一终止机制不可行，因为开放域问题的类型多样性使得不存在通用阈值。但固定上限可作为安全网保留。"
    },
    {
      "node": "T-TERM-ADAPTIVE",
      "new_status": "Hypothesis",
      "confidence": 0.6,
      "reasoning": "自适应终止的方向正确，但需要具体化：基于什么信号？如何定义'稳定'？需要进一步深入分析。"
    }
  ],
  "new_nodes": [
    {
      "id": "SYNTH-TERM-1",
      "type": "SynthesisNode",
      "content": "终止条件应采用双轨设计：(1) 硬性终止条件作为安全网（最大迭代次数、最大 token 消耗），吸收了 T-TERM-FIXED 的'简单明确'优点；(2) 软性终止条件基于自适应信号（覆盖率、稳定性、争议解决率），发展 T-TERM-ADAPTIVE 的方向。两者结合：软性条件决定正常停止时机，硬性条件防止异常情况。",
      "status": "Proposed",
      "confidence": 0.7,
      "impact": 0.8
    }
  ],
  "new_edges": [
    {"from": "SYNTH-TERM-1", "to": "T-TERM-FIXED", "type": "refines"},
    {"from": "SYNTH-TERM-1", "to": "T-TERM-ADAPTIVE", "type": "refines"},
    {"from": "SYNTH-TERM-1", "to": "Q-TERMINATION", "type": "answers"}
  ],
  "conflict_resolution": {
    "conflict": "CONFLICT-TERM-1",
    "resolution": "通过综合双方优点解决：固定阈值降级为安全网，自适应机制作为主要终止策略",
    "status": "Resolved"
  }
}
```

### DAG 状态（裁决后）

```
Q-TERMINATION
├── T-TERM-FIXED (REJECTED, conf=0.2)
├── T-TERM-ADAPTIVE (HYPOTHESIS, conf=0.6)
├── CONFLICT-TERM-1 (Resolved)
└── SYNTH-TERM-1 (Proposed, conf=0.7) ← "双轨终止设计"
    ├── refines T-TERM-FIXED
    └── refines T-TERM-ADAPTIVE
```

注意 SYNTH-TERM-1 本身状态是 Proposed——它还需要经过后续的攻击和裁决才能变成 Validated。这就是系统的递归性质：综合结论本身也要经受检验。

---

## Step 5：后续迭代（简要描述）

系统继续运行多轮迭代：

**第3-5轮**：
- 广度引擎发现遗漏的维度：错误处理、可扩展性、用户交互模式
- 深度引擎深入分析 DAG 数据结构的设计细节（节点类型、边类型、双轨状态系统）
- 攻击引擎质疑 T-ARCH-MULTI，深度引擎回应（论证 prompt 级角色分离虽不完美但足够有效）
- 裁判将 T-ARCH-MULTI 裁决为 Validated（confidence=0.75），附带条件：需要精心设计 prompt 以最大化角色差异

**第6-8轮**：
- 深度引擎细化各组件的具体设计
- 攻击引擎发现双轨状态系统中的一个问题：构成性状态和调节性分数之间的转换规则不够明确
- 裁判裁决：双轨状态系统的基本设计 Validated，但转换规则标记为 Hypothesis（需要实际实验验证）

**第9-10轮**：
- DAG 变化率显著下降（稳定性条件趋近满足）
- 覆盖率达到 85%（大部分子问题都有了回答）
- 争议解决率达到 90%
- 软性终止条件满足，系统停止

---

## Step 6：最终输出

### Validated 主线（经过验证的核心设计）

```
1. 整体架构 [VALIDATED, conf=0.75]
   → 采用多智能体辩论架构，包含广度引擎、深度引擎、攻击引擎、裁判引擎、
     维护器、协议层六个组件
   → 辩护：角色分离克服单一 LLM 的认知局限，对抗性检验提供质量保证
   → 条件：需要精心设计 prompt 以最大化角色差异

2. 核心数据结构 [VALIDATED, conf=0.8]
   → 使用 DAG（有向无环图）作为共享知识表示
   → 节点类型：QuestionNode, ThesisNode, EvidenceNode, ConflictNode, SynthesisNode
   → 边类型：supports, contradicts, refines, decomposes_to, depends_on

3. 双轨状态系统 [VALIDATED, conf=0.7]
   → 构成性状态：Proposed → Contested → Validated/Rejected/Hypothesis
   → 调节性分数：confidence, controversy, impact
   → 两者正交，服务不同目的

4. 终止条件 [VALIDATED, conf=0.7]
   → 双轨设计：硬性安全网 + 软性自适应条件
   → 软性条件基于覆盖率、稳定性、争议解决率

5. 输出结构 [VALIDATED, conf=0.75]
   → Validated 主线 + Hypothesis 清单 + 未决 Issue + 推理追溯
```

### Hypothesis 清单（方向可能正确但需进一步验证）

```
H1. 状态转换规则 [HYPOTHESIS, conf=0.55]
   → 构成性状态和调节性分数之间的具体转换规则
   → 不确定原因：需要实际运行数据来校准阈值

[WARNING: output was truncated due to max_tokens limit]

---
