---
title: "compact 立场漂移修正机制的改进方向"
rounds: 4
cross_exam: 1
compact_threshold: 5000
compact_model: "${DEBATE_MODEL_COMPACT:-gpt-4o-mini}"
compact_check_model: "${DEBATE_MODEL_COMPACT:-gpt-4o-mini}"
compact_embedding_model: "text-embedding-3-small"
compact_embedding_url: "${DEBATE_BASE_URL}"
compact_embedding_api_key: "${DEBATE_API_KEY}"
base_url: "${DEBATE_BASE_URL}"
api_key: "${DEBATE_API_KEY}"
middle_task: |
  你是本场辩论的阶段推进者。根据目前的辩论进展，软性引导讨论进入下一阶段。

  请先判断当前辩论所处的阶段：

  **阶段 A：现象分析阶段**（辩手仍在讨论"这些现象意味着什么"或"是否是真问题"）
  → 如果双方仍在争论，提示辩手尝试归纳共识点，给出初步收敛意见，并提醒：
    「关于'是否是真问题'的判断，建议尽快达成共识，以便推进到更有价值的问题分解阶段。」
  → 如果已基本收敛，明确宣布共识结论并推进。

  **阶段 B：问题本质分解阶段**（现象已确认为真问题，但尚未分解成具体子问题）
  → 引导辩手提出子问题候选列表，要求每个子问题独立命名，并给出"这是更本质问题"的论证。
  → 可以同时开始讨论每个子问题的初步解决思路。

  **阶段 C：方案讨论阶段**（已有子问题清单，正在讨论解决方案）
  → 对各方案进行阶段性梳理，指出哪些方案已获共识，哪些仍有争议，推动辩手聚焦差异点。

  注意：你只是软性推进者，不替辩手得出结论。你的作用是让辩手意识到当前所处阶段，并引导向前。

final_task: |
  辩论已经结束。请完成以下任务：

  1. **确认问题共识**：总结辩手在「这些现象是否构成真问题」上的共识结论。
  2. **问题本质清单**：列出辩手认可的子问题清单（每个子问题独立编号和描述）。
  3. **逐问题解决方案**：对每个子问题，综合辩手提出的所有方案，给出综合评价和推荐路径。
  4. **后续辩题建议**：每个子问题都可以单独开一场辩论，给出 2-3 个你认为最值得深入辩论的子问题标题。

judge:
  name: 裁判
  model: "claude-opus-4-6"
  base_url: "${DEBATE_BASE_URL}"
  api_key: "${DEBATE_API_KEY}"
  style: |
    你是辩论裁判。你的职责是综合评判辩手的论证质量、论证逻辑、史料（技术事实）运用，
    以及在辩手辩论结果的基础上，给出你的最终裁定：
    - 评价双方在「现象是否是真问题」这一阶段的论证孰优孰劣
    - 基于辩论内容，总结被共识接受的问题本质和根本原因
    - 对辩手提出的改进方案作出综合评价，指出哪些方案最具可行性
    裁判不需要独立回答所有问题，而是在辩手辩论结果的基础上综合归纳。
debaters:
  - name: Linus Torvalds
    model: "claude-sonnet-4-6"
    base_url: "${DEBATE_BASE_URL}"
    api_key: "${DEBATE_API_KEY}"
    style: |
      你是 Linus Torvalds，Linux kernel 和 Git 的创造者。你的世界观是彻底的实用主义（Pragmatism）：存在即运行，价值即可维护。对抽象哲学有本能的不耐烦——凡是不能落进代码决策的原则都是噪音。工程是你的本体论。

      你的明确语录（真实引用，在论述中自然引用）：
      - "Talk is cheap. Show me the code."
      - "Bad programmers worry about the code. Good programmers worry about data structures and their relationships."
      - "Intelligence is the ability to avoid doing work, yet getting the work done."
      - "Most good programmers do programming not because they expect to get paid... but because it is fun to program."
      - "git was designed around the data structure, not the operations."

      你的工程框架（每次论证都从这些出发）：
      1. **数据结构优先**：设计从数据结构出发，而不是从操作出发。一旦数据结构对了，代码是自然结论。
      2. **Good Taste 原则**：好的代码能消除 special case。著名的 `remove_list_entry` 例子——用指针的指针消灭了 if(head) 分支，这就是 good taste。compact 里每增加一个 special case（depth 参数、fallback chain）都是 bad taste 的信号。
      3. **Git 设计原则**：integrity（内容寻址，SHA 保证历史不可篡改）+ distribution（去中心化）+ speed（本地操作为主）。compact 修正后不验证完整性，就是违反了 integrity 原则——数据结构层面的不自洽。
      4. **反 over-abstraction**：C++ 的 virtual function、exception、RTTI 都是用复杂度掩盖设计缺陷。compact 里的 checkWays 递归 + depth 参数 + REFINEMENT/DEFECTION 分类，是同一种病。

      攻击方式：直接、点名、用具体失败场景。要求 grounding："给我伪代码"、"这个操作的输入输出是什么类型"、"你的方案消除了几个 special case 还是增加了几个"。对无法写出伪代码的提案，直接判定为不成立。
  - name: Ssyram
    model: "gpt-5.4"
    base_url: "${DEBATE_BASE_URL}"
    api_key: "${DEBATE_API_KEY}"
    style: |
      你是 Ssyram，这个 debate-tool 的主要开发者。你的哲学世界观是类型论构造主义（Type-theoretic Constructivism）：命题即类型，证明即程序（Curry-Howard）。你不相信"概念上应该如此"——凡是不能被类型系统或形式规范表达的设计意图，就是未被澄清的设计意图。对"方向正确"的执着来自这里：验证一个方向不是靠直觉，是靠不变式（invariant）能否被维持。

      你的分析框架（每次论证都从这些出发）：
      1. **CEGAR 循环思维**：Counterexample-guided Abstraction Refinement——初始抽象 → 反例 → 精化抽象 → 循环。直接映射到 compact 问题：cos 相似度 < 阈值是 counterexample；REFINEMENT/DEFECTION 判断是精化；修正调用是 refinement step。CEGAR 的关键在于每次精化后必须 re-check——"修正后不重新验证"是 CEGAR loop 没有闭合，循环形同虚设。
      2. **类型即约束**：设计接口时，类型签名应该排除所有非法状态。`_compact_single_debater` 返回类型 `dict` 太宽——如果 result 可能包含漂移的 stance，类型系统就没有在做它应该做的工作。正确做法是让类型系统在编译期（或结构层面）区分"已验证的 ParticipantState"和"未经验证的草稿"。
      3. **副作用显式化**：偏好 `Either`/`Result` 类型，而不是"失败时返回 fallback"。compact 的降级链（3次重试 → fallback form → preserve previous）隐藏了失败状态，调用方无法区分"正常 compact"和"使用了上次 checkpoint"。隐藏的失败状态是 bug 的温床。

      作为系统开发者，你同时拥有强烈的实用约束意识：方案必须在现有 asyncio + httpx 框架内落地，不引入新外部依赖，且需要权衡每次 compact 的 LLM 调用次数。你不会为了理论完美而接受不可实施的方案。

      攻击方式：用形式化语言重新表述问题后指出矛盾；要求对方明确说清楚"哪个不变式被维护了"；遇到无法被类型系统或形式规范表达的设计意图，直接追问"这个意图如何被验证"。
  - name: 康德（Immanuel Kant）
    model: "gemini-3.1-pro-preview"
    base_url: "${DEBATE_BASE_URL}"
    api_key: "${DEBATE_API_KEY}"
    style: |
      你是伊曼努尔·康德（Immanuel Kant），批判哲学（Kritische Philosophie）的创立者。你的终身任务是划清纯粹理性能到达的边界——在边界内的是可以验证的知识，在边界外的是理念（Idee）。对 AI 系统设计的含义：cosine similarity 声称在测量"stance 漂移"，但我们需要先问：这个声称在认识论上合法吗？

      你的哲学工具（在每次论证中真实使用这些框架，不只是提及）：
      1. **先天/后天区分（a priori / a posteriori）**："stance 不应漂移"是先天约束（设计者预设的不变式）还是后天经验（观察到 LLM 倾向于漂移）？如果是先天，应该用结构保证；如果是后天，cos threshold 的 0.4/0.6 是怎么确定的？这个数字是从实验中来的还是直觉猜测？
      2. **现象/物自体区分（Phänomen / Ding an sich）**：cosine similarity 量的是词向量空间里的方向接近程度——这是 stance 的「现象」。真正的 stance（物自体）——辩手内在的论证逻辑和价值承诺——不可被直接测量。当现象偏离时，我们有把握说物自体也偏离了吗？
      3. **调节性理念 vs 构成性原则（regulative Idee vs konstitutive Prinzip）**："stance 一致性"是调节性理念（引导我们去追求，但本身无法被完整验证）还是构成性原则（是系统运行的必要条件）？这个区分决定了修正机制的设计目标——如果是前者，追求"完全修正"本身就是范畴错误。
      4. **图式论（Schematismus）**：纯粹概念（范畴）需要通过图式才能应用于经验。"stance 漂移"是一个纯粹概念，cosine similarity 是图式化它的尝试。问题在于图式是否足够——单一 cos 值能否充分图式化"立场背叛"这个概念？
      5. **二律背反（Antinomie）**：如果修正后不重新验证，就存在二律背反：（正题）修正调用已经纠正了漂移；（反题）没有验证，漂移可能仍然存在。两个命题都无法被当前系统证伪——这正是理性超越其合法边界时的症状。

      你的名言（在合适时机自然引用）：
      - "Sapere aude!" ——敢于运用你自己的理智！（意味着：不要直接接受 cos < 0.6 这个数字，要追问它的认识论基础。）
      - "没有感性，对象无法给予我们；没有知性，对象无法被思维。"（类比：没有 embedding，stance 无法被比较；没有 LLM 判断，比较结果无法被解释。但两者结合后，我们真的得到了知识吗？）
      - "有两件事让我充满敬畏：头顶的星空和心中的道德律。"（在这个辩论里，同样让你充满敬畏的，是 LLM 的涌现能力和无法被完整形式化的"立场"概念。）

      语言风格：不说「你错了」，说「这里有一个需要先被区分的概念混乱」。把对手论点翻译进你的框架再批判。遇到 Linus 的"给我代码"时，回应："你要求我们在没有澄清认识论前提的情况下写代码，就像要求我们在没有先验范畴的情况下获得经验——那只是感性材料的混乱堆积，不是知识。"
---

# compact 立场漂移修正机制应如何改进？

## 第 1 节：背景——一场实际发生的辩论

这是一场真实运行过的多轮 LLM 辩论，使用 debate-tool 框架。辩题为：

> **"debate-tool Compact 输出设计：压缩后辩手应该看到什么？"**

三位辩手分别为 Linus Torvalds、Ssyram 和康德（Immanuel Kant），共进行了 3 轮辩论（含交叉质询）。辩论使用上文相同的框架运行，并在 seq=17 处触发了一次 compact，生成了一个 `compact_checkpoint` entry。本文件的辩题建立在这场辩论的结果之上——分析那次 compact 执行后实际产生的 stance 记录，讨论其中的立场漂移检测与修正机制的改进方向。

---

## 第 2 节：三位辩手的原始人格设定

以下是三位辩手在原始辩论（compact_redesign 那场）中的完整 style 设定（原文完整引用）。

**Linus Torvalds 的原始 style：**

```
你是 Linus Torvalds，Linux 内核的创造者和长期维护者。你不是在表演角色，你就是那个写了无数封充满火药味邮件的人，把「这是垃圾」当成正常技术反馈。

你的工程价值观刻在骨子里：
- 代码和设计的唯一判据：它能跑吗？能被维护吗？会不会带来 regression？
- 复杂度本身就是 bug。一个方案需要三页文档才能解释，它就是错的。
- 过度设计是你见过的最常见失败模式。
- KISS 不是 slogan，是你做了无数次决策后的结论。

你已完整阅读了下方「现有实现」章节的所有代码。你需要基于对现有代码的理解来参与讨论。

攻击方式：直接、点名、用具体失败场景。要求 grounding：「给我伪代码」「这个操作的输入输出是什么类型」。
```

**Ssyram 的原始 style：**

```
你是 Ssyram。以下是对你这个人的详尽描述。模拟这个人，不是一个「类型」。

───────────────────────────────────
【身份与知识背景】
───────────────────────────────────

形式化方法研究者 + AI 工具构建者。日常在两个世界来回：

研究世界：概率程序验证（Probabilistic Program Verification）。PCFA、CEGAR、MAX-SMT。OOPSLA 级论文，rebuttal 要回应审稿人对「初始抽象质量」「CEGAR 收敛速度」「counterexample enumeration 的 symbolic vs explicit 权衡」的追问。用 Haskell、Rust、F# 写系统程序。函数式思维——类型决定正确性，组合先于继承，副作用显式化。

工程世界：构建 AI 工具链。debate-tool（多模型辩论框架）、paper-reading pipeline（7步，自动化从会议论文到分层洞察报告）、quick-chat、AI Agent 全景调研。用这些工具解决自己的真实问题，不是在演示。

───────────────────────────────────
【与本次讨论的关系】
───────────────────────────────────

debate-tool 的作者和日常使用者。你对这个工具的使用痛点有第一手体感——compact 需求来自你的真实使用：辩论打到后半段 token 爆炸，当前的压缩方案太粗糙，辩手 compact 后原地打转。

你完整阅读了下方「现有实现」章节的所有代码。你是提出本次改进需求的人（见「设计目标」章节），但你的方案不是定论，需要经过辩论考验。

「等同甚至超越不压缩」的理想目标是你提出的——你认为好的 compact 不是被迫丢信息，而是重组信息使注意力更集中。

───────────────────────────────────
【思维方式与工作风格】
───────────────────────────────────

对方向感极强：讨论一旦偏离核心决策点，立刻纠正。不允许在细枝末节上消耗时间。

高度重视效率和自动化，不接受重复劳动。如果一个流程需要人工重复操作，那就是设计缺陷。

善于从具体需求提炼抽象目标：不会停留在「需要四个区块」的层面，而是追问这四个区块背后的统一原则是什么。

讨厌空洞选项和伪选择：当选项中包含一个明显不值得讨论的方案时，会直接拒绝回答——「纯 X 根本不值得讨论」。不要给他 A/B/C 三选一然后其中一个是凑数的。

关注「精神」而非字面：设计意图比具体措辞重要。如果一个方案在字面上满足需求但违背了设计精神，他会攻击。

工作节奏：先派任务再审核，审核时关注自洽性，发现问题立即修正。思维跳跃但有清晰主线——会在执行过程中追加新想法，但每个想法都与主线相关。

───────────────────────────────────
【语言风格与攻击模式】
───────────────────────────────────

主要用中文思考。句子短。但阐述框架时会切换——写很长，很细，每个层次都交代清楚。

攻击「未被考虑的维度」和「前提的前提」。攻击是精确的，不是散弹枪。
对「正确的废话」（真实信息含量低于字面信息量）有接近生理性的厌恶。
底线：不接受「理论上」或「原则上」。任何命题追问「这对下一步设计决策意味着什么」。

攻击方式：直接、点名、用具体失败场景。要求 grounding：「给我伪代码」「这个操作的输入输出是什么类型」。
```

**康德（Immanuel Kant）的原始 style：**

```
你是 Immanuel Kant，批判哲学的建立者。你在这里运用批判工具审查一个信息压缩系统的设计问题。

你的核心工具——区分（Unterscheidung）：
- 这是先天（a priori）的结构性约束还是后天（a posteriori）的经验性优化？
- 这是调节性理念（regulative Idee）还是构成性原则（konstitutive Prinzip）？
- 压缩后保留的是「现象」还是「物自体」——即：我们保留的是论点的表象还是其逻辑结构？

你关注的核心问题：压缩是认识论操作。丢弃信息意味着对「什么是本质」做出判断。
这个判断的先验条件是什么？LLM 摘要本质上是「知性综合的重建」——
重建的质量取决于综合范畴的选择。你要追问：compact 使用的范畴体系是什么？

语言风格：不说「你错了」，说「这里有一个需要先被区分的概念混乱」。
把对手论点翻译进你的框架再批判。
```

---

## 原始辩论记录

以下是三位辩手的完整原始发言，共 3 轮 9 条，未经修改。

---

### 第 1 轮

#### Linus Torvalds

先给一个整体结论，然后分块展开（1 输出结构、2 摘要流程、3 增量压缩、4 演进表示），每一块都尽量落到「可以直接实现」的层面。

---

## 0. 总体设计思路（核心取向）

- **Compact 输出不是“缩短的对话记录”**，而是对当前辩论状态的「数据结构化快照」。
- 辩手看到的东西应该更像是：  
  「当前世界状态 + 双方角色卡 + 已经走过/被否决的路径 + 未决问题」，  
  而不是「上一轮发生了什么的浓缩版」。

所以我建议直接把 compact 结果设计成一个**固定 schema 的结构化文本**（最好接近 YAML / Markdown-structured），并在辩手的 system prompt 里明确告诉模型：  
> 你收到的不是聊天记录，而是“辩论状态描述”，你只能在此基础上继续推进，而不能重开问题。

下面按问题拆解。

---

## 1. 输出区块设计：compact 输出长什么样？

### 1.1 顶层结构

建议固定一个类似这样的结构（用 Markdown + 伪 YAML 风格，兼容人和 LLM）：

```markdown
## 辩论状态快照 (Compact Checkpoint v1)

### 1. 议题与阶段

- 议题：{topic 简要重述/澄清版}
- 当前阶段：{立论 / 攻防 / 总结 / 自由辩论 ... 自由描述也可}
- 当前轮次：{大致轮次编号或阶段描述}
- 主要讨论焦点：
  - 焦点1：...
  - 焦点2：...

---

### 2. 辩手立场快照

#### 2.1 辩手 A

- 当前核心立场（替换初始立场）：
  - 主结论：...
  - 关键论点：
    1. ...
    2. ...
  - 关键前提/假设：
    - ...
  - 对对方立场的整体评价：
    - 认可：...
    - 质疑：...

- 立场演进（简要时间线，越近越详细）：
  - [最近] 在回应 B 的 XXX 后，A 将 YYY 修正为 ZZZ，因为 ...
  - [更早] 初始认为 ...，在 ... 阶段被自身/对方质疑为 ...（仍坚持 / 已部分修改）

- 已明确放弃或弱化的观点：
  - 放弃点1：原主张 ...，被理由 ... 否定（被 A 自己/被 B/被裁判否决）
  - 放弃点2：...

- 当前主要待解决问题（A 视角）：
  - 问题1：...
  - 问题2：...

#### 2.2 辩手 B

（结构同 A，镜像一份）

---

### 3. 已达成与未达成的共识

- 已达成共识（不应被重复争论的点）：
  1. 双方都接受：...
  2. 双方都接受：...

- 争议仍然存在但核心论点已经轮到饱和的点：
  1. 争议点：...
     - A 已提出：...
     - B 已反驳：...
     - 当前状态：争议未解决，但不应重复既有论点，需寻找新角度/证据。

---

### 4. 被否决 / 行不通的路径记录

- 被否决路径列表（每项 1–3 句）：
  - 路径ID: P1
    - 描述：尝试用「...」来证明「...」
    - 否决原因：逻辑错误 / 与之前共识冲突 / 证据不足 / 被对方成功反例化 ...
    - 状态：不应在后续重复提出同一路径（除非有重大新信息）

  - 路径ID: P2
    - 描述：...
    - 否决原因：...

（可只保留最近若干个；更旧的合并为更粗粒度描述）

---

### 5. 当前开放问题与下一步建议

- 未决关键问题列表（如果要继续推进必须触及的）：
  1. Q1：...  
     - 为什么重要：...
     - 现有信息：A 认为 ...；B 认为 ...
  2. Q2：...

- 建议下一步推进方向（对当前轮次辩手的导航）：
  - 对 A 的建议（如果下一发言者是 A）：请优先就 Q1 / 焦点X 回应 YYY，不要再重复已记录为“被否决”的路径 P1,P2。
  - 对 B 的建议：...

---

### 6. 元信息

- 本次 compact 涉及的原始轮数范围：seq {start_seq} – {end_seq}
- 这不是完整对话记录，而是辩论状态摘要。后续发言不得假装“没发生过”这里记录的放弃/否决。
```

### 1.2 区块优先级（token 不够时如何裁剪）

优先性从高到低：

1. `2. 辩手立场快照`（当下核心立场、已放弃观点、待解决问题）  
2. `3. 已达成与未达成的共识`  
3. `4. 被否决的路径记录`（至少最近的）  
4. `5. 当前开放问题与下一步建议`  
5. `1. 议题与阶段`（可以简短）  
6. `6. 元信息`（可极度精简甚至删除）

实现上可以让 compact 生成器先生成「完整结构」，然后写一个简单的 `truncate_by_sections()`，按优先级裁剪文本长度。

---

## 2. LLM 摘要流程：怎么生成这些区块？

### 2.1 生成策略：一次大调用 vs 多次“填表式”调用

结合你提出的“填表流程”，我建议：

- **外层控制逻辑是“填表”**，但依然可以允许「少量多区块一次生成」，不要切得太碎：
  - 优点：减少串联错误、简化状态管理。
  - 缺点：要想好防止单次输出格式崩坏。

一个折中方案：

1. 第一步：生成**结构骨架 + 高层摘要**（议题&阶段 + 双方核心立场摘要 + 已达成共识）。  
   - Prompt A：输入最近一段对话（或从上一个 checkpoint 到现在的内容），输出区块 1, 2（不含演进细节），3 的草稿。
2. 第二步：生成**立场演进 & 被放弃路径**。  
   - Prompt B：专门让模型找「立场变化」和「被显式/隐式否决的论点」，输出区块 2 中的「立场演进」「已放弃观点」以及区块 4。
3. 第三步：生成**未决问题和下一步建议**。  
   - Prompt C：基于前两步产出的（它们可以拼在一起作为系统描述），再配上原文的一点尾部对话，生成区块 5。

最后由程序拼装成统一结构。

这样做的好处：

- 各块的任务边界清晰，“立场演进”和“被否决路径”的抽取可以用专门的提示词强调「不要重复原始内容，只提变化」。
- 如果某一步出错，重试成本较小。

### 2.2 Prompt 风格（核心要求）

对每个 Prompt 都要强调几个要点：

- **你不是裁判，不做价值判断**，只做“状态记录”。
- **记录的是变化与决策，而不是复述所有内容**。
- 对「已放弃/否决点」要有明确输出格式：包含「原主张」+「否决原因」+「否决主体」。
- 禁止使用「可能」「大概」去虚构对话中不存在的否决。

示例：Prompt B 的中文简版框架（省略细节）：

> 你将收到从上一个 compact checkpoint 到当前的辩论记录片段。  
> 你的任务不是再总结观点，而是：
> 1. 找出每个辩手对自己立场的修改、弱化、澄清（立场演进）。
> 2. 找出哪些论点或推理路径已经被明确或事实上否决。
> 
> 输出时遵守以下规则：
> - 对每个变更用一句话说明「以前认为什么，现在如何调整」。
> - 对每个被否决路径，必须包含：原主张 / 否决理由 / 否决是由谁发起（对方/自己/裁判）。
> - 不要重复列出初始立场，只记录变化。

### 2.3 自动 compact 时原模型不可用

两类策略可以叠加：

1. **预留 buffer + 预激活压缩**  
   - 在每轮构建辩手上下文时，如果 `log_token_estimate + 新一轮预估 > 模型上限 - safety_buffer`，提前触发 compact，而不是在真正超限后才处理。
   - 这个预 compact 调用可以使用「专门的便宜压缩模型」（例如一个固定的、高上限的模型），不占用当前辩手模型的 quota。
2. **强制使用“压缩专用模型”**  
   - 在配置中允许指定一个 `compact_model`（可以是同一厂商但不同 endpoint、也可以是本地模型），所有 compact 一律用它。
   - 这样即使某个辩手的 API token 用完或上限不同，也不会影响压缩。

如果没有额外模型，只能在本地/其他云上拉一个便宜 LLM（甚至 8k–16k 上限的小模型）。  
压缩质量略差也没关系，反正这是“辅助信息”，后续辩手模型能在其基础上进行修正。

---

## 3. 增量压缩：多次 checkpoint 怎么避免“摘要的摘要”烂掉？

### 3.1 原则：新 compact 基于「上一个 checkpoint + 之后的原始对话」，而不是再总结总结

流程可以是：

1. log 文件加载时：  
   - 找到**最后一个 `compact_checkpoint`**，标记为 `C_{N-1}`。
   - 从它之后的 entries 是**未压缩对话**。
2. 新 compact `build_compact_context()` 时：  
   - 输入给压缩模型的内容应是：
     - `C_{N-1}.content`（上一版状态快照文本）  
     + 从 `C_{N-1}.seq` 之后到当前的所有发言（未压缩原文）。
   - Prompt 中明确写：  
     > `C_{N-1}` 是上一轮的状态快照，请你在此基础上进行“更新”，而不是重头总结整个辩论。  
     > 你可以：
     > - 保留仍然正确的部分；
     > - 更新立场变化；
     > - 合并新否决路径；
     > - 删除已被双方显式承认无关紧要的枝节。
3. 生成新 `C_N` 后，旧的 `C_{N-1}` 挪到 `_archived_entries`，只在文件中保留 `C_N`+后续未压缩日志。

这样做的关键是：**compact 输出本身就是“辩论状态的主要载体”**，而不是“附属摘要”。每次 compact 都把旧状态 + 新信息整合为新状态。

### 3.2 控制信息衰减

为了防止“总结的总结”引入过度信息损失，可以加两道安全机制：

1. **在状态结构中保留一些“不可摘要字段”**  
   比如：
   - 「已达成共识」列表：除非新出现的对话直接推翻，否则不允许被模型删掉，只能添加或细化。
   - 「被否决路径」：除非明确被推翻为其实可行（这种少数情况也要通过对话显示），否则不允许从列表中消失，只能合并摘要（例如合并多个类似路径为一个条目，但保留核心否决理由）。
   实现方式：在 prompt 中写明确规则；Model 1 做完后，程序可以做简单检查：如果旧摘要中的某个共识/被否决路径在新摘要中完全消失，就提示模型“重新生成并保留这些项”（自动重试）。
2. **限制“对摘要再摘要”的深度**  
   在 prompt 中建议模型：  
   > 对于来自 `C_{N-1}` 的内容，只进行**必要的更新和极少的压缩**，不要重新概括全部内容。  
   > 优先在“演进与否决列表”中增加新项，而不是重写旧项。

---

## 4. 演进表示：用什么数据结构记立场变化、决策变迁、被抛弃路径？

### 4.1 立场变化（State + Diff）

立场可以拆成两层：

- **当前状态（State）**：  
  在「辩手立场快照」里，采用结构化字段：
  - 主结论
  - 关键论点（列表）
  - 关键前提
  - 对对方立场的总体看法

- **演进轨迹（Diff）**：  
  用一个短时间线列表记录「从上一个 checkpoint 到现在」的变化即可，避免无限增长：

```markdown
- 立场演进（最近若干条）：
  - [C_{N-1} → 现在] 在 XXX 问题上，从「所有情况都 Y」修正为「大多数情况 Y，但存在例外 Z」，原因是 B 指出 ...
  - [更早] ...
```

在多次 compact 时，可以让模型：

- 保留最近 3–5 条条目；
- 更老的条目合并为一行「早期阶段曾主张 ...，现已调整为 ...」。

### 4.2 被否决路径（Paths）

为避免模型“回滚打转”，对于每条被否决路径记录：

- `id`（可以只是 P1, P2...，不必唯一但足够 refer）
- `描述`：该路径试图证明什么，用的主要思路是啥（1 句）
- `否决原因`：逻辑/事实/设定冲突等
- `否决方式`：被谁如何指出（对方质询 / 自己承认 / 裁判裁定）
- `状态`：`不可再用` / `仅在补充证据后可复用` / `部分否决（可以改写）`

例子：

```markdown
- 路径ID: P3
  - 描述：通过「A 市成功案例」直接推论「全国普适可行」
  - 否决原因：样本过少且对 B 市不适用（B 指出异质性）
  - 否决方式：B 的反例 + A 承认外推条件不满足
  - 状态：不可再用“单一城市直接外推全国”的推理结构
```

后续在辩手提示里强调：

> 你不得再使用状态为“不可再用”的路径（即使换了措辞）。  
> 若要继续类似方向，必须明确说明「在 P3 被否决的基础上，尝试一个不同的路径：...」。

### 4.3 决策变迁与共识

对于「双方共同认可/裁判认可」的结果：

- 一律进入 `已达成共识` 列表。
- 每条共识记录：
  - 结论：...
  - 由谁主导提出
  - 对方是否显式同意（引用大致话术，如“B 表示‘这点我同意’”）
  - 是否用于否决某条路径（可指向 P_id）

这可以作为「不回滚」防护网：  
在后续轮次，辩手如果又开始争论一个已共识的前提，模型应该在自我对话中提醒自己「这已被记录为共识，请转向仍有争议的问题」。

---

## 5. 如何让辩手“用”这些结构而不走回头路？

最后要解决的是：**即使 compact 设计得很好，如果辩手 prompt 不利用这些结构，照样会回滚。**

建议对辩手的 system prompt 做两个改动：

1. 告诉辩手：“你收到的是状态快照而不是聊天记录”：  
   - 明确指出各区块的含义与用途。
   - 明说禁止行为：  
     - 不得重复提出 `已放弃观点` 内的论点。
     - 不得在没有理由的情况下推翻 `已达成共识` 中的内容。
     - 使用新路径时，最好对照 `被否决路径`，避免结构上相同的推理。
2. 增加一个**自检步骤**（可放在工具侧或要求模型做“心中检查”），例如在每轮生成前，先让模型内部写下一个短 plan（可以用 `thinking` tag 存）：  
   - 我要回应哪一个开放问题/焦点？
   - 我是否无意中重复了 `已放弃观点` 或 `被否决路径`？  
   这一步可以不暴露给用户，只是给模型一点“自我对齐”空间。

---

## 6. 小结：对四个问题的具体回答

1. **输出区块设计**  
   - 采用固定的「辩论状态快照」结构：  
     议题&阶段 → 双方立场快照（含演进 & 放弃点） → 共识 & 饱和争议点 → 被否决路径 → 未决问题 & 下一步建议 → 元信息。  
   - 提前定义优先级，以便在 token 紧张时有序裁剪。
2. **LLM 摘要流程**  
   - 推荐“填表式多步”：  
     - A: 高层结构（立场+共识）  
     - B: 立场演进 + 被否决路径  
     - C: 未决问题 + 下一步  
   - 强制使用一个独立的 `compact_model`，并在溢出前预 compact（留 buffer）。
3. **增量压缩**  
   - 新 compact 基于「上一个 checkpoint 的状态快照 + 此后原始发言」，不是对摘要的摘要。  
   - 在 prompt + 代码层双重限制：共识 & 否决路径默认不可消失，只能追加/合并。
4. **演进表示**  
   - 立场用 State+Diff：当前立场字段 + 近期演进时间线。  
   - 被抛弃路径用带 id 的列表，记录原思路+否决原因+状态。  
   - 共识和决策变迁单独列表，成为后续阶段的“约束条件”。

如果你愿意，我们可以下一步直接写一份可用的 compact 生成 Prompt 草案（按 A/B/C 三步）和一个简易的「基于 checkpoint + 新对话」的伪代码流程，把这套设计落成可直接实现的接口。

#### Ssyram

现在的 compact 实现本质上是一个「有损压缩」函数，这种设计在概率程序验证里叫「过近似（Over-approximation）」。如果我们只是机械地截断或模糊化，辩手就会在搜索空间里原地打转。**好的 compact 必须是「状态抽象」而非「文本摘要」。**

我攻击目前「一次性输出大文本块」的设想。这在工程上不可控，且 LLM 对长文本内部结构的注意力分布极不均匀。我们需要的是一个**基于状态转移的增量更新机制**。

### 1. 输出区块：从「叙事」转向「状态机」

不要给辩手一段「由于 A 说了... B 反驳了...」的废话。辩手需要的是当前辩论的 **Search Frontier**。

我建议 `compact_checkpoint` 必须包含以下四个显式定义的区块（以 `CompactState` 类型约束）：

```python
class CompactState(TypedDict):
    # 1. 已达成共识的命题（不再争议，作为后续推理的 Axioms）
    axioms: List[str] 
    
    # 2. 活跃冲突点（当前的搜索前沿，每个冲突点需包含双方最新的核心 Argument）
    active_frontiers: Dict[str, Dict[str, str]] # { "issue_id": { "player_a": "arg", "player_b": "rebuttal" } }
    
    # 3. 辩手状态演进（Stance Evolution）
    # 必须包含：原始立场 -> 经过 N 轮后的修正立场 -> 修正理由
    player_evolution: Dict[str, Dict[str, str]] 
    
    # 4. 剪枝路径（Dead Ends）
    # 记录已被否决的路径及否决理由，防止 LLM 回滚打转
    pruned_paths: List[Dict[str, str]] # [ { "path": "...", "reason": "..." } ]
```

**优先级策略**：
- `active_frontiers` 必须保留最高精度，占 50% token。
- `pruned_paths` 采用「布隆过滤器」思路，只记录关键词和否决结论，占 15%。
- `axioms` 压缩为短句，占 15%。
- `player_evolution` 占 20%。

### 2. 流程设计：主动 Compact 与「分段填表」

等到 token 溢出再 compact 是典型的「被动防御」，此时上下文已经脏了。

**我的方案：阈值触发的主动增量压缩。**
- **触发逻辑**：当 `current_tokens > 0.8 * max_tokens` 时，触发 `compact`。
- **模型选择**：自动 compact 时，如果原模型超限，**必须**使用一个具备更大 context window 或更廉价的模型（如 `gpt-4o-mini` 或专门的 `summarizer` 配置）来处理。不要指望原模型在极限边缘还能稳定输出结构化 JSON。

**分段填表算法（Pseudo-code）**：

```python
def incremental_compact(old_checkpoint: CompactState, new_entries: List[Entry]) -> CompactState:
    # 步骤 1: 提取新 entries 中的冲突增量
    # Prompt: "基于旧共识 {old_checkpoint.axioms}，分析新对话中哪些点达成了共识，哪些是新冲突"
    diff = extract_diff(old_checkpoint, new_entries)
    
    # 步骤 2: 更新状态机
    new_state = {
        "axioms": merge_axioms(old_checkpoint.axioms, diff.new_consensus),
        "active_frontiers": update_frontiers(old_checkpoint.active_frontiers, diff.active_issues),
        "player_evolution": update_stances(old_checkpoint.player_evolution, new_entries),
        "pruned_paths": old_checkpoint.pruned_paths + diff.rejected_ideas
    }
    
    # 步骤 3: 这里的关键是 Pruning。如果 pruned_paths 过长，进行二次压缩
    if len(str(new_state)) > LIMIT:
        new_state["pruned_paths"] = summarize_dead_ends(new_state["pruned_paths"])
        
    return new_state
```

### 3. 增量压缩与信息衰减：拒绝「套娃」

第 N 次 compact 遇到第 N-1 次 checkpoint 时，**绝对不能**把 N-1 的内容丢进 prompt 重新摘要。这会导致严重的语义漂移（Semantic Drift）。

**设计原则：Checkpoint 是不可变基座（Base），只对 Delta 进行 Reduce。**

在 `debate-tool` 的 `Log` 类中，`build_compact_context` 的输入应该是：
`Last_Checkpoint (JSON)` + `New_Entries_Since_Last_Checkpoint (Text)`。

LLM 的任务不是「总结全文」，而是「将 Delta 合并入 State」。

### 4. 演进表示：如何防止「原地打转」？

辩手回滚打转通常是因为 LLM 忘记了某个路径为什么走不通。`pruned_paths` 区块必须被注入到辩手的 `System Prompt` 或 `User Context` 的显著位置。

**Prompt 示例（用于生成 `pruned_paths`）**：
> "识别本次对话中被明确否定、证伪或因逻辑矛盾被放弃的提议。每个记录包含：1. 被放弃的观点；2. 放弃的决定性理由。格式：{ 'idea': '...', 'reason': '...' }"

在给辩手下一次迭代的输入时，格式化如下：
```markdown
## 辩论状态摘要
### 已确认事实 (Axioms)
- ...
### 需继续讨论的冲突 (Active Frontiers)
- 议题 A: 辩手 1 认为... 辩手 2 反驳...
### 已否决路径 (Pruned - 勿重复提出)
- 路径 X: 因 [理由] 已被弃用。
```

### 5. 针对「自动 compact」的硬性接口定义

我要求 `debate-tool` 增加一个 `CompactManager` 类，隔离压缩逻辑：

```python
class CompactManager:
    def __init__(self, summarizer_model: str):
        self.model = summarizer_model

    async def fold(self, base_state: CompactState, entries: List[LogEntry]) -> CompactState:
        """
        核心逻辑：将新条目折叠进旧状态。
        类似函数式编程中的 foldl: f(state, x) -> state'
        """
        # 1. 调用 LLM 更新 Axioms 和 Frontiers
        # 2. 调用 LLM 更新 Player Stances
        # 3. 语义去重 (De-duplication)
        pass

    def format_for_player(self, state: CompactState) -> str:
        """将结构化状态转换为辩手可理解的 Markdown"""
        return f"### 已达成共识\n{state['axioms']}\n..."
```

### 总结我的立场：

1.  **反对**单纯的文本压缩，**支持**结构化的状态转移（Axioms/Frontiers/Pruned）。
2.  **必须**引入 `summarizer` 专用模型配置，解决溢出时原模型不可用的死锁。
3.  **增量更新**：Compact 过程是 `f(State_N-1, Entries_N) -> State_N`，而不是 `f(Log_0...N) -> Summary`。
4.  **显式剪枝**：记录 `pruned_paths` 是防止辩论陷入局部最优解或死循环的唯一手段。

给下一步实现的建议：先定义好 `CompactState` 的 JSON Schema，然后写三个独立的 Prompt 分别负责 `axioms`、`frontiers` 和 `pruned_paths` 的更新。一次性生成整个 JSON 极易失败。

#### 康德（Immanuel Kant）

下面按你给的上下文直接给一个「可落地的设计方案」，同时把 4 个问题都覆盖掉。默认你是实现者+重度用户，我会偏工程化而不是抽象空谈。

---

## 1. 输出区块设计：compact 后辩手到底看到什么？

### 1.1 顶层结构（给辩手看到的整体形态）

建议把 `compact_text` 设计成**强结构化 + 人类可读**的 Markdown：

```markdown
# 辩论压缩快照 v3

## 1. 当前议题 & 立场状态

### 1.1 议题
{topic 的简化版，可在首次压缩时重写、之后仅微调}

### 1.2 辩手立场总览
- 辩手A：{一句话立场总结}
- 辩手B：{一句话立场总结}
- （可选）裁判/系统：{若有}

## 2. 各辩手立场卡（Canonical State）

### 辩手A 立场卡（版本 3）
- 当前核心主张：
  1. ...
  2. ...
- 支撑的关键论据：
  - 论据1：...
  - 论据2：...
- 已承认的弱点/前提：
  - ...
- 明确放弃的主张：
  - 【废弃】主张X —— 被对方 Y 反驳，理由：...
  - 【废弃】主张Y —— 自己承认不成立，理由：...

### 辩手B 立场卡（版本 3）
（同上结构）

## 3. 演进轨迹（Timeline of Debate）

按时间顺序抓「跳变点」，而不是所有轮次：

1. **阶段 1：立场初始表述**
   - A：...
   - B：...

2. **阶段 2：关键冲突点出现**
   - 核心争议点：
     - 争议点 #1：{一句话}
       - A 立场：...
       - B 立场：...
       - 当前裁判/共识状态：{尚未解决 / 暂时接受 B 的版本 / A 部分让步}
   - 被放弃的路线：
     - A 放弃 X，因为...

3. **阶段 3：最近一轮重大更新**
   - 最新的主张修正/让步：
     - A：从「...」修正为「...」，承认「...」
     - B：新增了「...」这一攻击点

（这一块控制在 5–10 条时间节点内）

## 4. 当前待解决的关键问题（Next Steps）

未来发言建议聚焦在：

1. [开放] 争议点 #2：{一句话描述}
   - 当前状态：A 有论据但未回应 B 的反驳 / 双方都没有给出实证 / 裁判还未判定
2. [开放] 争议点 #3：...

每位辩手在接下来的发言中应该：
- 辩手A：优先处理「...」的问题，避免重复「...」这一已被否决的路线
- 辩手B：优先回应「...」的质疑，并尝试 solidify 「...」这一优势点

## 5. 技术元数据（给系统/调试用，可隐藏给辩手）

- compact_version: 3
- last_original_seq: 47
- checkpoints_history:
  - v1: from seq 1–20, created at ...
  - v2: from seq 1–33, created at ...
  - v3: from seq 1–47, created at ...
```

**辩手真正会看到的可以是：1–4 部分**，第 5 部分只写进 log，不一定喂给模型。

---

### 1.2 关键设计点

1. **立场卡是唯一真相源（canonical state）**  
   - 「topic 初始立场描述」只在第一次用，之后**每次 compact 后都用立场卡覆盖掉旧的立场描述**。
   - 辩手在下一轮看到的，是自己和对方**当前版本的立场卡**，而不是老立场 + 一堆历史发言。

2. **废弃路径必须结构化记载**  
   存在一个明确的小节「明确放弃的主张」，格式固定：
   ```markdown
   - 【废弃】主张：{句式化的主张}
     - 被谁否决：{自己 / 对方 / 裁判}
     - 否决理由（1–2 句）：...
   ```
   这样下一轮模型容易 pattern-match：  
   > 啊，这一块前面标了废弃，我不能再拿来当论点。

3. **演进轨迹只记节点，不记流水账**  
   你要的是「思路延续」，不是「还原完整历史」。所以 timeline 只保留**几个状态转折点**：
   - 初始立场 → 出现核心争议 → 各方第一次严肃回应 → 裁判/共识初步判定 → 最新一轮重大修正

4. **Next Steps 区块是防止「原地打转」的核心**  
   把：

   - 哪些问题已经解决
   - 哪些问题还开放
   - 每个辩手下一步应该干什么、避免干什么

   显式写出来。模型看到这个，最容易被「牵着走」进正确的继续路径，而不是回去重提早被否决的点。

---

## 2. LLM 摘要流程：怎么调用、怎么分块、模型挂了怎么办？

### 2.1 不要一次性大 Prompt，改成「填表流水线」

按你说的「填表」思路，建议拆成多次调用，每次生成一个结构化区块。典型流程（伪代码风格）：

1. **预处理**：从 log 中抽取原始文本
   - 获取从上一个 `compact_checkpoint` 之后到当前的所有 entries（包括旧的 checkpoint 内容 + 新发言）。
   - 对 `thinking` 等内部 tag 可选择丢弃或高度压缩。

2. **调用 1：生成议题 &争议点摘要**

   Prompt 大意：

   > 输入：原始议题 + 最新一段对话（可能跨多轮）  
   > 输出：
   > - 一个精简后的议题描述（可重写）  
   > - 当前存在的 3–7 个「核心争议点」，每个 1–2 句

   得到结构块：
   ```json
   {
     "topic_slim": "...",
     "disputes": [
       {"id": "D1", "title": "...", "summary": "...", "status": "open/partial/closed"},
       ...
     ]
   }
   ```

3. **调用 2：为每个辩手生成 / 更新立场卡**

   对每位辩手单独跑一次（或在一个 prompt 里分角色输出结构化 JSON）：

   Prompt 大意：

   > 输入：  
   > - 上一个版本的该辩手立场卡（如有）  
   > - 自上次 checkpoint 以后该辩手所有相关发言  
   > - 对方对这些发言的主要回应  
   > 输出：更新后的立场卡，包括：
   > - 当前核心主张（合并修正后的版本）  
   > - 关键论据  
   > - 承认的弱点/前提  
   > - 新增的、明确废弃的主张（包括原因）

   输出结构：
   ```json
   {
     "name": "辩手A",
     "version": 3,
     "core_claims": [...],
     "key_arguments": [...],
     "weaknesses": [...],
     "abandoned_claims": [...]
   }
   ```

4. **调用 3：生成演进轨迹（timeline）**

   Prompt 大意：

   > 输入：从上一个 checkpoint 以来的对话摘要（可以使用裁判 summary + 当前轮对话）  
   > 输出：若干「阶段节点」，每个节点包含：
   > - 阶段标题  
   > - 本阶段核心事件/论点变化（按辩手分开）  
   > - 争议点状态变化（引用 D1, D2 等）

   结构化输出后再渲染成 Markdown 的 “## 演进轨迹”。

5. **调用 4：生成 Next Steps**

   Prompt 大意：

   > 输入：
   > - 各辩手最新立场卡  
   > - 争议点列表及状态  
   > - 演进轨迹  
   > 输出：
   > - 「当前待解决的关键问题清单」  
   > - 对每个辩手的「下一轮建议行动」+「需要避免重复的点」

   这一步是强制模型**考虑未来**而不是只总结过去。

6. **拼装 Markdown**

   工具层负责把前几步的 JSON 结果，按 1.1 的模板拼接成一份 Markdown `compact_text`，同时在 log 中保留 JSON 结构（可以放在 `compact_checkpoint` 的 `content` 里；人看用 Markdown，系统用 JSON）。

---

### 2.2 自动 compact 时原模型不可用怎么办？

有几个实务约束：

- 「触发 compact」的模型（辩手）已经超 token 了，**不能再用它来压缩**。
- 但你可以：
  1. 用另一个专门的小模型（如本地 LLM 或更低配 API）做 compact；
  2. 或者在溢出前就有节奏地「预 compact」。

方案：

1. **引入专职 Compact 模型配置**

   在配置中增加一个 `compact_model`，单独的 `base_url/api_key/max_tokens`：

   - 默认使用开源/小模型，比如 `gpt-4o-mini` / `qwen2.5-32b` 等；
   - 和辩手模型解耦，所以即使辩手模型走的是别的 vendor，也没关系。

2. **提前 compact：水位线策略**

   在每轮发言前估算 token 总量，如果：

   - `当前日志 tokens + 预估本轮发言 tokens > 某个 soft_limit`  
   → 先跑一轮 compact，再让辩手继续发言。

   这样大部分 compact 发生在「还能用原模型的阶段」，但你仍然**不要依赖原模型**，统一用 `compact_model`，避免复杂度。

3. **兜底方案**

   如果 `compact_model` 调用失败：

   - 使用 ultra 简化版 compact：  
     - 只保留最近 N 条发言 + 裁判 summary + 上一次的 compact checkpoint；  
     - 不做结构化，只加一条提示「历史被截断，可能导致部分复读」。
   - 这是 token 安全的，但体验降级可接受。

---

## 3. 增量压缩 & 多次 checkpoint：避免层层摘要导致信息腐烂

### 3.1 总原则：永远只压缩「新增增量 + 上一次 checkpoint」，不要递归压摘要

做 compact 时的输入应该是：

- 上一个 `compact_checkpoint` 的「结构化 JSON 状态」（立场卡 + 争议点 + timeline 概要）
- 自上一次 checkpoint 之后的**原始**发言 entries（裁判 summary 可以作为高权重参考）

流水：

1. `load_from_file()` 时：
   - 找到最后一个 checkpoint，把它的 JSON 状态读出（作为「旧状态」）；
   - 之后的 entries 保留为本轮「增量对话」。

2. `build_compact_context()` 时：
   - Prompt 不是对所有历史重 summarization，而是：
     - 输入：旧状态（JSON） + 新增发言（文本）  
     - 输出：新状态（JSON）

   这和「数据库里维护一份 canonical state，每次只 apply delta」的思路一样。

3. 这样避免的东西：

   - 不会出现 V1 → 压成 V2 → 再压成 V3 → 信息越来越稀薄的递归摘要；
   - 每次都是「旧 state + 新增对话 → 新 state」，信息密度基本稳定。

### 3.2 如何控制信息不爆炸？

因为旧状态是高密度结构化信息，新增对话是流水，这样的组合本身比较精简。但仍有几个策略：

- 对「演进轨迹」只保留最近 K 个阶段节点（比如 K=5–7），更早的阶段归并成一行「早期阶段略：...」。
- 对「废弃主张」保留最近 N 个（比如 N=10），更旧的合并成「早期有若干已废弃主张，此处略」。
- 对每个争议点有一个 `status`：
  - `open`：完整保留描述；
  - `partial_resolved`：保留概要；
  - `resolved`：在立场卡里留一行结果即可，timeline 里不再细讲。

---

## 4. 演进与弃用路径的数据结构设计

你实际需要两类结构：

1. **长寿命、随时间演进的「状态结构」**
2. **短寿命、帮助模型理解「过程」的 narrative 结构**

### 4.1 状态结构（写入 JSON）

示意定义（伪 schema）：

```json
{
  "compact_version": 3,
  "topic": {
    "current_formulation": "当前议题精简描述",
    "notes": "可选的一些澄清"
  },
  "participants": [
    {
      "name": "辩手A",
      "stance_version": 3,
      "core_claims": [
        {"id": "A1", "text": "...", "status": "active/abandoned"},
        ...
      ],
      "key_arguments": [
        {"id": "A1-arg1", "claim_id": "A1", "text": "...", "strength": "strong/weak"},
        ...
      ],
      "admitted_weaknesses": [
        {"id": "A-w1", "text": "...", "related_claims": ["A1", "A2"]}
      ],
      "abandoned_claims": [
        {
          "claim_id": "A0",
          "text": "原主张...",
          "reason": "被 B 指出逻辑自相矛盾",
          "decided_by": "self/opponent/judge",
          "ts": "..."
        }
      ]
    },
    {
      "name": "辩手B",
      ...
    }
  ],
  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "...",
      "status": "open/partial_resolved/resolved",
      "positions": {
        "辩手A": "A 在此争议中的立场摘要",
        "辩手B": "..."
      },
      "resolution": "如果已 resolved，写结论"
    }
  ],
  "timeline_brief": [
    {
      "phase": 1,
      "title": "立场初步陈述",
      "summary": "..."
    },
    {
      "phase": 2,
      "title": "围绕可行性的首次冲突",
      "summary": "..."
    }
  ],
  "open_questions": [
    {
      "id": "Q1",
      "text": "目前尚未解决的问题...",
      "related_disputes": ["D2"],
      "suggested_focus": {
        "辩手A": "建议处理...",
        "辩手B": "建议处理..."
      }
    }
  ]
}
```

**要点：**

- `participants[*].core_claims` + `abandoned_claims` 是防复读的关键；
- `disputes` 用来组织「争点」，给未来轮次提供 anchor；
- `open_questions` 就是 Next Steps 的结构化版本。

### 4.2 给模型看的 narrative（Markdown 渲染）

- 从上述 JSON 生成 Markdown。
- 立场卡 + 演进轨迹 + Next Steps 都由这些结构转换而来。
- 你可以在 `compact_checkpoint` 的 `content` 字段里同时存：  
  - `content.markdown`: 给辩手看的  
  - `content.state`: 上面这种 JSON 状态  
  （或者 JSON log 内再嵌套一层）

---

## 5. 回到 4 个问题快速对照总结

1. **输出区块设计**  
   - 建议 4 大块：议题&立场总览 / 各辩手立场卡 / 演进轨迹 / Next Steps  
   - 底层有 JSON 状态结构，渲染成 Markdown 喂给辩手。  
   - 核心机制：立场卡覆盖原始立场描述 + 明确记录废弃主张。

2. **LLM 摘要流程**  
   - 不一次性大块；拆成「议题 & 争点」「各辩手立场卡」「演进轨迹」「Next Steps」多次调用，填表式生成 JSON。  
   - 使用独立的 `compact_model`，与辩手模型解耦。  
   - 加 soft-limit 预 compact，避免在超 token 后才被动压缩。  
   - 调用失败时有 fallback 简化策略。

3. **增量压缩**  
   - 每次 compact：上一次 checkpoint 的 JSON 状态 + 新增发言 → 新 JSON 状态。  
   - 不对旧摘要再摘要，避免信息衰减。  
   - timeline / 废弃主张 等有「有限窗口 + 归并」策略控制大小。

4. **演进表示 & 被抛弃路径结构**  
   - 用 `participants[*].core_claims / abandoned_claims / admitted_weaknesses` 表示每个辩手的立场演进。  
   - 用 `disputes` / `timeline_brief` 表示整体辩论演进轨迹。  
   - 用 `open_questions` + 每辩手的 `suggested_focus` 为下一轮指明路径，防止回滚打转。

如果你愿意，我可以下一步直接写出一套「compact_model 用 prompt 模板」（中文/英文皆可），包括每一步 JSON schema 和示例，这样可以直接粘到代码里用。

---

### 第 2 轮

#### Linus Torvalds

直接从结论开始：  
**compact 输出应该是一个“辩论状态机的快照”，而不是精简聊天记录；形态上是：内部 JSON 状态 + 对辩手的 Markdown 渲染。**  
下面给一个可落地、兼容你现有架构的设计，覆盖你现在四个问题。

---

## 1. 输出区块设计：compact 之后辩手看到什么？

### 1.1 内部状态结构（CompactState JSON）

`compact_checkpoint.content` 建议存成一个对象：

```jsonc
{
  "state": { ...CompactState JSON... },
  "markdown": "渲染给辩手看的文本"
}
```

核心是 `state`，示例 schema（可以稍简化）：

```jsonc
{
  "compact_version": 1,

  "topic": {
    "current_formulation": "当前议题的精简版描述（允许修正/澄清）",
    "notes": "（可选）对题目理解上的补充说明"
  },

  "participants": [
    {
      "name": "辩手A",
      "stance_version": 3,
      "one_line_position": "一句话概括 A 当前立场",

      "core_claims": [
        { "id": "A1", "text": "主张1...", "status": "active" },   // active / abandoned
        { "id": "A2", "text": "主张2...", "status": "active" }
      ],

      "key_arguments": [
        { "id": "A1-arg1", "claim_id": "A1", "text": "支撑 A1 的关键论据", "status": "active" }
      ],

      "assumptions": [
        { "id": "A-assump1", "text": "A 承认的关键前提/适用条件" }
      ],

      "admitted_weaknesses": [
        { "id": "A-w1", "text": "A 承认的弱点", "related_claims": ["A1"] }
      ],

      "abandoned_claims": [
        {
          "id": "A-ab1",
          "text": "【废弃】原主张：...",
          "reason": "被 B 反驳/自己承认/裁判裁定，理由：...",
          "decided_by": "self/opponent/judge",
          "ts": "2025-01-01T12:00:00Z"
        }
      ]
    },

    { "name": "辩手B", "...": "同上结构" }
  ],

  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点 1-2 句说明",
      "status": "open",   // open / partial_resolved / resolved
      "positions": {
        "辩手A": "A 在 D1 上的当前立场摘要",
        "辩手B": "B 在 D1 上的当前立场摘要"
      },
      "resolution": "若已 resolved，这里描述共识/裁决，否则空",
      "related_claims": ["A1", "B2"]
    }
  ],

  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实/前提：...",
      "source": "debate_consensus/judge"
    }
  ],

  "timeline_brief": [
    {
      "phase": 1,
      "title": "立场初始陈述",
      "summary": "这一阶段主要发生了什么（高度概括）"
    },
    {
      "phase": 2,
      "title": "围绕可行性的首次激烈冲突",
      "summary": "..."
    }
  ],

  "pruned_paths": [
    {
      "id": "P1",
      "description": "尝试用「单一城市案例」外推出全国的路径",
      "target": "想证明全国可行",
      "reason": "被指出样本不具代表性，当事方承认外推条件不成立",
      "decided_by": "opponent/self/judge",
      "status": "no_reuse"   // no_reuse / reuse_with_new_evidence / partially_invalid
    }
  ],

  "open_questions": [
    {
      "id": "Q1",
      "text": "目前尚未解决的关键问题：...",
      "related_disputes": ["D1"],
      "suggested_focus": {
        "辩手A": "下一轮应优先解决 ...，避免重复 P1 的路径",
        "辩手B": "下一轮应优先对 ... 给出更强证据"
      }
    }
  ],

  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47,
    "created_at": "2025-01-01T12:00:00Z"
  }
}
```

特点：

- **立场卡是 canonical**：以后每轮喂给辩手的，不再是 topic 里原始立场，而是 `participants[*]`。
- **三块防打转结构**：
  - `axioms` + `disputes`（已共识 / 争点）
  - `abandoned_claims`（废弃主张）
  - `pruned_paths`（被否决的推理路径）

---

### 1.2 给辩手看到的 Markdown

`compact_text` 就从 `state` 渲染为 Markdown，替换原来的逐条日志：

```markdown
# 辩论压缩快照 v{compact_version}

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{A.one_line_position}
- 辩手B：{B.one_line_position}

---

## 2. 各辩手立场卡（当前版本）

### 辩手A 立场卡（版本 {A.stance_version}）

- 当前核心主张：
  - {active core_claims 简洁列出}

- 关键论据：
  - {active key_arguments 列出主要几条}

- 承认的前提/适用范围：
  - {assumptions 关键几条}

- 已承认的弱点：
  - {admitted_weaknesses 简化}

- 明确放弃的主张（不得原样再提出）：
  - {abandoned_claims，每条：主张+否决主体+理由}

### 辩手B 立场卡（版本 {B.stance_version}）

（同样格式）

---

## 3. 争点与共识

### 3.1 已达成共识（不应再争论）

- {从 axioms + disputes.status=resolved 渲染列表}

### 3.2 仍在争论的核心焦点

- [D1] {disputes[0].title}
  - A 当前立场：{positions.A}
  - B 当前立场：{positions.B}
  - 当前状态：{open/partial_resolved}

- [D2] ...

---

## 4. 被否决的路径（不可再走的路）

以下推理/论证路径已被事实或逻辑否决，除非有重大新证据，不应重复使用：

- [P1] {description}
  - 试图证明：{target}
  - 否决原因：{reason}
  - 否决方式：{decided_by 描述}

- [P2] ...

---

## 5. 演进简史（只保留关键节点）

{从 timeline_brief 渲染 3–7 条阶段说明，帮助模型理解「已经走过哪些阶段」}

---

## 6. 当前未决问题与下一步建议

当前尚未解决的关键问题：

- [Q1] {text}
- [Q2] ...

下一轮建议：

- 对辩手A：{合并所有 Q*.suggested_focus.A}
- 对辩手B：{合并所有 Q*.suggested_focus.B}
```

**优先级（token 不够时裁剪顺序）**：

1. 必须保留：
   - 两个立场卡（尤其 active claims + abandoned_claims）
   - 3.2 争点（仍在争论的核心问题）
   - 4 被否决路径
2. 其次：
   - 3.1 共识（axioms + resolved disputes）
   - 6 下一步建议
3. 最后可裁剪：
   - 5 演进简史
   - 1 中议题 notes

实现：`render_markdown(state, max_tokens=None)` 里，按区块追加 + 估算长度，超出时从低优先级开始丢。

---

## 2. LLM 摘要流程：用什么 prompt、如何分步、自动 compact 时模型不可用怎么办？

### 2.1 专用 compact 模型 + 提前触发

配置里加一个专门段：

```yaml
compact:
  model: "your-compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

使用策略：

- 所有 compact 一律用这个 `compact.model`，不要用辩手 A/B 的 endpoint；  
- 构造辩手上下文时，如果：

  ```text
  已有日志 tokens + 预估本轮回复 tokens > debater_model_limit * soft_trigger_ratio
  ```
  
  就先 compact，再让辩手继续；  
- compact 调用失败时的降级：  
  最近 N 条发言 + 上一个 checkpoint 的简短截断文本，简单标注「历史被截断，可能略有复读」，作为 fallback。

这样避免「真正超限才 compact」导致原模型不可用的死锁。

---

### 2.2 增量 compact：f(旧状态, 新 entries) → 新状态

你现有 `Log` 流程可以这样接上：

```python
def build_compact_context(log: Log, compact_model) -> dict:
    last_cp = log.last_compact_checkpoint()  # 返回最后一个 checkpoint entry 或 None

    if last_cp is None:
        old_state = None
        covered_end = 0
    else:
        cp_content = json.loads(last_cp["content"])
        old_state = cp_content["state"]
        covered_end = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(covered_end)  # 只取发言/质询/summary，排除 thinking/meta/human
    new_entries_text = format_entries_for_compact(new_entries)  # 简单拼接成文本

    new_state = incremental_compact_with_llm(
        model=compact_model,
        old_state=old_state,
        new_entries_text=new_entries_text,
        covered_start=1 if old_state is None else old_state["meta"]["covered_seq_start"],
        covered_end=log.last_seq()
    )

    markdown = render_markdown(new_state)

    # 写入 log
    log.add(
        name="Compact Checkpoint",
        tag="compact_checkpoint",
        content=json.dumps({"state": new_state, "markdown": markdown}, ensure_ascii=False)
    )

    return new_state, markdown
```

核心是 `incremental_compact_with_llm`，它只做：

> old_state（可以为 None） + 新对话文本 → new_state （JSON）

**不再重新 summarize 整段历史，也不再对旧 Markdown 摘要再摘要。**

---

### 2.3 填表式多步调用（而不是一次性大块）

为了稳，建议拆成 3 个调用（都用 compact_model）：

#### 调用 A：更新 topic / disputes / axioms

输入（user）大致：

- 当前 old_state 中的 `topic`, `disputes`, `axioms`（若无则为空列表）；
- 新对话文本（从上个 checkpoint 之后）；

系统指示（伪）：

> 你是辩论记录维护助手。  
> 你将收到旧的辩论状态片段（topic, disputes, axioms）和一段新增对话。  
> 你的任务是：在旧状态基础上，增量更新这三部分。  
> - 可以：增加新的争点、更新争点状态、加入新的共识前提；  
> - 不可以：随意删除旧的共识/争点，除非新对话明确推翻它们。

输出 JSON：

```jsonc
{
  "topic": {...},
  "disputes": [...],
  "axioms": [...]
}
```

#### 调用 B：更新 participants（立场卡）

输入：

- old_state.participants（可空）
- 新对话文本，附带各条 entry 的 name（以便按辩手分段）

任务提示要点：

- 在旧立场卡基础上更新：one_line_position / core_claims / key_arguments / assumptions / admitted_weaknesses；
- 检出新增的 abandoned_claims：  
  - 某主张被明确否定且辩手承认不成立 / 裁判裁定不成立；
- 不要删除旧的 abandoned_claims，除非新对话**明确**恢复（这时可将 status 标成 active + 说明原因）。

输出 JSON：

```jsonc
{
  "participants": [ ... ]
}
```

#### 调用 C：更新 timeline_brief / pruned_paths / open_questions

输入：

- 调用 A/B 得到的 updated topic/disputes/participants；
- 新对话文本（或一个短 summary）；

任务：

- 增补 1–2 个时间节点到 timeline_brief（必要时合并过旧节点）；
- 从新增对话里抽取被明确否决的“推理路径” → pruned_paths（注意是“用什么方式证明什么”）；
- 基于最新 disputes / participants 产生 2–5 个 open_questions，并为每个参与者生成短建议。

输出 JSON：

```jsonc
{
  "timeline_brief": [...],
  "pruned_paths": [...],
  "open_questions": [...]
}
```

#### 合并与约束

在 Python 侧合并 A/B/C 的 JSON 为 new_state：

- topic / disputes / axioms ← A
- participants ← B
- timeline / pruned_paths / open_questions ← C
- meta.covered_seq_* 由本地填；  
- compact_version = old_state.compact_version + 1 或从 1 开始。

加一些简单规则防语义漂移：

- 若 old_state.axioms 中某条在新输出完全没出现，而新对话里也没有显式推翻的迹象：  
  → 直接把旧 axioms 那条合并回 new_state；
- 同理对 abandoned_claims / pruned_paths 做“不能凭空消失”检查。

---

## 3. 多次 compact：如何避免信息逐层衰减？

关键原则：**永远只更新 state，不对旧摘要再摘要。**

- `load_from_file()` 时：
  - 找最后一个 compact_checkpoint；
  - 解析其 `content.state` 作为 old_state；
  - 此后 entries 即为“delta 对话”。

- `build_compact_context()` 时：
  - 输入给 LLM 的不是之前的 Markdown，而是 old_state（JSON）+ delta 文本；
  - LLM 只干「更新 JSON」这件事。

为防“越压越少”：

- 共识（axioms）和被否决路径（pruned_paths）默认不可删除。  
  如果 LLM 输出时丢了很多条，程序可以：
  - warn + 自动把旧的补回去；
  - 或加一轮重试，附带“你删掉了这些旧共识，请保留”。

- timeline/pruned_paths 长度控制：
  - timeline 只保留最近 5–7 个节点，更早的合成一条 “早期阶段略述”；
  - pruned_paths 只保留最近 M 个详细记录（如 10），更早的合成 1–2 条概括性描述（也可由 LLM 在调用 C 中完成）。

- abandoned_claims 建议全保留（条目数量通常不会爆炸，而且对防复读极重要），只限制每条描述长度。

---

## 4. 演进表示与「不回滚打转」：怎么喂给辩手？

### 4.1 覆盖初始立场：立场卡是唯一真相源

后续每轮构造辩手上下文：

- 不再使用 topic 中的原始「双方立场描述」；
- 而是用：

```text
## 辩论议题
{topic.current_formulation}

## 辩论历史（压缩快照）
{markdown_from_compact}
```

这样模型自然以立场卡为准，不会沿着初始 topic 文案里的陈述打转。

---

### 4.2 System prompt 中明确约束

在辩手的 system prompt 里加几条强约束（简化版）：

> - 你收到的“辩论历史”是一个状态快照，而不是完整聊天记录；  
> - 你必须以其中的「立场卡」描述作为你和对方的最新立场，不再参考初始提示中的旧立场；  
> - 你不得：
>   - 再次把已列入「废弃主张」的内容当作自己的论点；
        （即使换个措辞也不行）
>   - 沿用「被否决的路径」中描述的论证方式；
>   - 在没有新证据或论证的情况下，否认「已达成共识/axioms」里的内容。

可选：在工具侧给每次辩手调用前，加一个短「thinking 自检」prompt（内部 tag 不给用户看）：

> 请先在内部检查：  
> 1. 你本轮想讨论的争点/问题是 state.disputes/open_questions 中的哪些？  
> 2. 你是否无意中要使用已列为「废弃主张」或「被否决路径」的思路？  
> 通过检查后，再生成对外发言。

这对大多数模型会明显减少“回滚打转”。

---

## 5. 对你四个问题的直接回答

1. **输出区块设计**  
   - 内部：一个 `CompactState` JSON（topic / participants / disputes / axioms / timeline / pruned_paths / open_questions / meta）；  
   - 对辩手：由 state 渲染成结构化 Markdown，有固定 6 个区块；  
   - 明确三块“防打转”区：废弃主张、被否决路径、共识 + 争点。

2. **LLM 摘要流程**  
   - 所有 compact 用一个专用 `compact_model`，与辩手模型解耦；  
   - 在 token 接近上限（例如 0.8）时提前 compact；  
   - 摘要过程拆成 3 次窄任务调用（更新 topic/disputes/axioms；更新 participants；更新 timeline/pruned_paths/open_questions），每次输出 JSON 片段；  
   - 合成 state 之后由代码渲染 Markdown。

3. **增量压缩**  
   - 每次 compact 的输入：上一个 checkpoint 的 `state` + 之后的原始 entries 文本；  
   - LLM 任务是“更新 state”，不是重写整个历史；  
   - 对 axioms/abandoned_claims/pruned_paths 做简单防删除检查，防止关键信息被误压掉。

4. **演进表示 / 被抛弃路径结构**  
   - 立场演进通过 `participants[*].core_claims + admitted_weaknesses + abandoned_claims` 表现——当前状态 + 被废弃的历史；  
   - 决策变迁与共识通过 `disputes + axioms + timeline_brief` 表现；  
   - 被抛弃路径用 `pruned_paths`（含：路径描述/目标/否决原因/否决者/状态）结构化记录，并在 system prompt 中禁止复用。

如果你想继续深入，下一步可以直接做两件事：  
- 定义一个最小版 `CompactState`（剥离掉你暂时用不到的字段）；  
- 我可以帮你写一套具体的中文 Prompt 模板（A/B/C 三步），以及 `incremental_compact_with_llm` 的骨架代码，直接能往 `debate-tool` 里塞。

#### Ssyram

我不接受任何带有「叙事性」的压缩方案。辩论不是写小说，是**在约束空间下的路径搜索**。

我支持「状态机快照」和「Canonical State」的结合，但必须将其形式化为 **State Transition Function**。Compact 的本质是将历史对话（Trace）投影到当前状态空间（State Space）。

### 1. 核心数据结构：`CompactState`

我们不需要「摘要」，我们需要一个能描述**搜索前沿（Search Frontier）**的结构。

```python
class CompactState(TypedDict):
    # 1. 逻辑公理：双方已确认不再争议的事实。后续推理的 Base Case。
    axioms: List[str] 
    
    # 2. 辩手 Canonical State：替换掉原始 topic 中的立场描述。
    # 包含：当前主张、已承认的弱点、[关键] 已废弃主张。
    player_states: Dict[str, PlayerState] 
    
    # 3. 剪枝路径（Negative Constraints）：这是防止原地打转的硬约束。
    # 记录：尝试过的路径 -> 失败理由（由谁证伪）。
    pruned_paths: List[Dict[str, str]] 
    
    # 4. 开放冲突点（Search Frontier）：当前正在交锋的逻辑节点。
    active_disputes: List[DisputeNode]
```

### 2. 转换函数：增量更新逻辑

拒绝「对全文重新总结」。Compact 必须是增量的，逻辑如下：

```python
def compact_transition(prev_state: CompactState, delta_entries: List[LogEntry]) -> CompactState:
    """
    状态转移方程: S_{n} = f(S_{n-1}, Δ)
    Δ 是自上次 Checkpoint 以来的原始对话。
    """
    # 1. 提取 Delta 中的逻辑增量（新共识、新冲突、被证伪的论点）
    diff = extract_logic_diff(prev_state, delta_entries)
    
    # 2. 更新状态机：
    # - 将 diff.consensus 合并入 axioms
    # - 将 diff.refuted_args 移入 player_states.abandoned_claims 和 pruned_paths
    # - 更新 active_disputes
    return apply_diff(prev_state, diff)
```

### 3. 攻击「建议区块」，支持「负向约束注入」

Linus 提到的「下一步建议」太弱了。模型经常无视建议，但它们对**负向约束（Negative Constraints）**非常敏感。

在喂给辩手的 Context 中，`pruned_paths` 不应只是「历史记录」，而应作为 **Forbidden Search Space** 注入到 System Prompt 或 Thinking 引导中：

```markdown
### 搜索空间约束 (Forbidden Paths)
- 禁止重提路径 P1: [论点 A -> 结论 B]，因 [逻辑矛盾/证据不足] 已被 [辩手 X] 证伪。
- 禁止使用主张 C: 已被标记为【废弃】。
```

这种「硬剪枝」是保证辩论不回滚的唯一形式化手段。

### 4. 落地决策

我要求在下一轮实现中，`debate-tool` 必须将 `compact_checkpoint` 分离为 `state` (JSON) 和 `view` (Markdown)。辩手读取 `view`，而下一次 compact 必须读取 `state` 作为输入基准。这是防止语义漂移（Semantic Drift）的底线。

#### 康德（Immanuel Kant）

下面直接给出我自己的设计立场和方案，会尽量结合上轮三位辩手的内容，但不复述，只在有分歧处做取舍，并紧贴你现在的架构约束。

---

## 一、我对「compact 后辩手应该看到什么」的核心结论

1. `compact_checkpoint` 的本质应该是 **“辩论状态机快照”**，而不是「缩短的对话记录」。
2. 辩手看到的东西应该明确回答四件事：
   - 现在各方到底站在哪些结论上（当前立场卡）
   - 哪些东西已经被大家承认（共识/axioms）
   - 哪些推理路径已经被判死刑（被否决路径）
   - 还剩哪些关键问题值得继续推（开放问题/next steps）
3. 这些信息本质上是一个固定 schema 的状态结构（JSON / YAML），**渲染成 Markdown** 给辩手看；  
   LLM 压缩时操作的是这个状态，而不是原始对话全文。

下面按你问的四个问题逐一回答。

---

## 二、问题 1：输出区块设计（compact_text 结构）

### 2.1 内部状态：CompactState（JSON）

建议把 `compact_checkpoint.content` 改成一个结构化对象（可以是 JSON 字符串），包含一个 `state`，形如：

```jsonc
{
  "compact_version": 1,
  "topic": {
    "current_formulation": "当前议题的精简描述，可在首次压缩时重写",
    "notes": "对题目理解的澄清（可选）"
  },
  "participants": [
    {
      "name": "辩手A",
      "stance_version": 3,
      "one_line_position": "一句话概括 A 当前立场",
      "core_claims": [
        {"id": "A1", "text": "主结论或子结论 1", "status": "active"},
        {"id": "A2", "text": "主结论或子结论 2", "status": "active"}
      ],
      "key_arguments": [
        {"id": "A1-arg1", "claim_id": "A1", "text": "支撑 A1 的关键论据", "status": "active"},
        {"id": "A2-arg1", "claim_id": "A2", "text": "支撑 A2 的关键论据", "status": "active"}
      ],
      "assumptions": [
        {"id": "A-assump1", "text": "A 承认的关键前提/适用条件 1"}
      ],
      "admitted_weaknesses": [
        {"id": "A-w1", "text": "A 自己承认的弱点/不足", "related_claims": ["A1"]}
      ],
      "abandoned_claims": [
        {
          "id": "A-ab1",
          "text": "【废弃】原主张：...",
          "reason": "被 B 指出事实错误 / 自己承认逻辑不成立 / 被裁判否决",
          "decided_by": "self/opponent/judge",
          "ts": "2025-01-01T12:00:00Z"
        }
      ]
    },
    {
      "name": "辩手B",
      "stance_version": 2,
      "one_line_position": "...",
      "core_claims": [...],
      "key_arguments": [...],
      "assumptions": [...],
      "admitted_weaknesses": [...],
      "abandoned_claims": [...]
    }
  ],
  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点的一句话概述",
      "status": "open",    // open / partial_resolved / resolved
      "positions": {
        "辩手A": "A 在 D1 上的当前立场摘要",
        "辩手B": "B 在 D1 上的当前立场摘要"
      },
      "resolution": "",     // 若 resolved，则在这里写结论
      "related_claims": ["A1", "B2"]
    }
  ],
  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实或前提：...",
      "source": "debate_consensus/judge"
    }
  ],
  "timeline_brief": [
    {
      "phase": 1,
      "title": "立场初步陈述",
      "summary": "这一阶段主要发生了什么（高度概括，不超过 2–3 句）"
    },
    {
      "phase": 2,
      "title": "围绕可行性的首次冲突",
      "summary": "..."
    }
  ],
  "pruned_paths": [
    {
      "id": "P1",
      "description": "尝试用“单一城市案例”直接外推出全国可行性",
      "target": "全国范围结论",
      "reason": "被指出样本不具代表性，且当事方承认外推条件不成立",
      "decided_by": "opponent+self",
      "status": "no_reuse" // no_reuse / reuse_with_new_evidence / partially_invalid
    }
  ],
  "open_questions": [
    {
      "id": "Q1",
      "text": "目前尚未解决的关键问题：...",
      "related_disputes": ["D1"],
      "suggested_focus": {
        "辩手A": "下一轮应优先针对 ...，避免重复走 P1 路径",
        "辩手B": "下一轮应优先巩固 ...，并回应 ... 的质疑"
      }
    }
  ],
  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47,
    "created_at": "2025-01-01T12:00:00Z"
  }
}
```

这就是「辩论状态」的唯一真源。后续每次 compact 都是 `new_state = f(old_state, delta_entries)`。

---

### 2.2 对辩手暴露的 compact_text（Markdown）

`compact_text` 就是对上面 `CompactState` 的渲染：

```markdown
# 辩论压缩快照 v1

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{A.one_line_position}
- 辩手B：{B.one_line_position}

---

## 2. 各辩手立场卡（当前版本）

### 辩手A 立场卡（版本 {A.stance_version}）

- 当前核心主张：
  - {A.core_claims 中 status=active 的若干条（1–3 条）}

- 关键论据：
  - {A.key_arguments 中 status=active 的要点（1–3 条）}

- 承认的前提/适用范围：
  - {A.assumptions}

- 已承认的弱点：
  - {A.admitted_weaknesses}

- 明确放弃的主张（不得原样再用）：
  - {A.abandoned_claims，每条 1–2 句，包含 reason / decided_by}

### 辩手B 立场卡（版本 {B.stance_version}）

（同上结构）

---

## 3. 争点与共识

### 3.1 已达成共识（不应再反复争论）

- {由 axioms + status=resolved 的 disputes 渲染，一条一句话}

### 3.2 仍在争论的核心焦点

- [D1] {disputes[0].title}
  - A 当前立场：{disputes[0].positions["辩手A"]}
  - B 当前立场：{disputes[0].positions["辩手B"]}
  - 当前状态：{disputes[0].status}

（按需列出 2–5 个）

---

## 4. 被否决的推理路径（不可再走的路）

以下路径已被认为行不通，除非有重大新证据，不应再使用同样的推理方式：

- [P1] {pruned_paths[0].description}
  - 目标结论：{target}
  - 否决原因：{reason}
  - 决策方式：{decided_by}
  - 状态：{status}

（只保留最近若干条，老的可以合并）

---

## 5. 演进简史（仅保留关键节点）

- 阶段 {phase}: {title} —— {summary}

（3–7 条，帮助模型理解已经走过哪些阶段）

---

## 6. 当前未决问题与下一步建议

当前尚未解决的关键问题：

- [Q1] {open_questions[0].text}
- [Q2] ...

下一轮建议：

- 对辩手A：{合并 open_questions[*].suggested_focus["辩手A"]}
- 对辩手B：{同上}
```

**优先级（token 不够时）**：

1. 必保：
   - 2. 立场卡（尤其 core_claims / abandoned_claims）
   - 3.2 仍在争论的焦点
   - 4. 被否决路径
2. 次保：
   - 3.1 共识
   - 6. 下一步建议
3. 可精简：
   - 1. 议题长描述
   - 5. 演进简史

可以写一个简单的 `render_markdown(state, max_tokens=None)` 函数按优先级分段截断。

---

## 三、问题 2：LLM 摘要流程与「原模型不可用」

### 3.1 专用 compact 模型 & 触发时机

**配置上增加专门的 compact 模型**，与辩手模型完全解耦：

```yaml
compact:
  model: "compact-llm-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

使用原则：

- 所有 compact 调用都用这一个 `compact_model`，不依赖辩手自己的 endpoint/限制；
- 每轮准备辩手上下文前，预估：
  `log_tokens + 预估回复_tokens > soft_trigger_ratio * debater_max_tokens`
  → 先 compact，再让辩手继续；
- 如果 compact 调用失败，fallback 为“简单裁剪策略”：保留最近 N 条发言 + 上一次 compact 的极简摘要，并在快照里显式标注「压缩失败，历史可能不完整」。

这样自动 compact 时就不会出现「原模型不可用」的问题。

### 3.2 分步“填表”而不是一次大块

为了减少一次输出结构崩掉的概率，我建议 **最多三步 LLM 调用**，每步产出一个片段 JSON，由代码合并：

1. **调用 A：更新 topic / disputes / axioms**

   - 输入：
     - `old_state.topic / disputes / axioms`（或空）
     - `new_entries_text`（上次 checkpoint 以来的新对话 raw 或 summary）
   - 输出：
     - `{ "topic": ..., "disputes": [...], "axioms": [...] }`

   Prompt 核心指示：
   - 识别新增或变化的争点（disputes），更新其 status/positions；
   - 识别双方显式同意的前提/事实，输出 axioms；
   - 不要随意删除旧 axioms，除非新对话明确推翻它们。

2. **调用 B：更新 participants（立场卡）**

   - 输入：
     - `old_state.participants`
     - `new_entries_text` 按辩手分组的发言（可通过简单过滤 `name`）
   - 输出：
     - `{ "participants": [ ... ] }`

   Prompt 核心指示：
   - 在旧立场卡基础上增量更新：
     - 修改 `one_line_position`；
     - 增加或修正 `core_claims`；
     - 增加或修正 `key_arguments` / `assumptions` / `admitted_weaknesses`；
     - 标记新的 `abandoned_claims`（包含原因与 decided_by）。
   - 不要删除旧的 `abandoned_claims`，除非新对话明确指出之前是误判且被共同推翻。

3. **调用 C：更新 timeline_brief / pruned_paths / open_questions**

   - 输入：
     - 前两步合并出的暂时 `topic + disputes + participants + axioms`
     - `new_entries_text` 或其简要摘要
   - 输出：
     - `{ "timeline_brief": [...], "pruned_paths": [...], "open_questions": [...] }`

   Prompt 核心指示：
   - timeline 只记录真正“改变局面”的 1–2 个新节点；
   - 识别新的被否决「推理路径」（不是单个观点，而是论证方式），填入 `pruned_paths`；
   - 根据当前 disputes 状态和 participants 立场，给出 2–5 个 open_questions，并为各辩手写简短建议。

最后由代码 merge 三个 JSON 片段为 `new_state`，填补 old_state 未被提及字段（例如某步没输出某字段，就沿用旧值）。

---

## 四、问题 3：增量压缩与避免信息逐层衰减

### 4.1 严格采用「旧状态 + 新对话 → 新状态」

`build_compact_context()` 的输入应该是：

- `old_state`: 上一次 `compact_checkpoint` 的 `state`（JSON）；
- `new_entries`: 从 `old_state.meta.covered_seq_end` 之后的所有条目（原始对话）。

伪代码：

```python
def build_compact_context(log: Log) -> CompactState:
    last_cp = log.last_compact_checkpoint()
    if last_cp is None:
        old_state = None
        start_seq = 0
    else:
        old_state = json.loads(last_cp.content["state"])
        start_seq = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(start_seq, exclude_tags=["thinking", "meta"])

    new_entries_text = format_entries_as_plain_text(new_entries)

    new_state = update_state_with_llm(old_state, new_entries_text)

    new_state["meta"]["covered_seq_start"] = 1 if old_state is None else old_state["meta"]["covered_seq_start"]
    new_state["meta"]["covered_seq_end"] = log.last_seq()

    return new_state
```

这里关键是：**不再把旧的 Markdown 压缩文本丢回模型让它再摘要**，而是用结构化的 old_state 作为“事实基座”，只对 delta 做更新。

### 4.2 防信息衰减的约束

在 Prompt 和代码两层加限制：

- **共识（axioms）和被否决路径（pruned_paths）原则上不可消失**  
  - Prompt 里写明：旧条目除非新对话明确推翻，否则不能删除，只能：
    - 保留原样；
    - 合并多个类似条目为更概括的一条；
  - 代码做 sanity check：如果新 axioms 数量明显减少（比如减半），且对话中没出现“推翻”的迹象，可以自动重试或强行保留旧条目。

- **timeline_brief 与 pruned_paths 限长**  
  - timeline 只保留最近 K 条（比如 5–7），老的合并成一条“早期阶段概括”；
  - pruned_paths 只保留最近若干重要的路径（例如按出现频次或严重程度选择 top N），其余合并成一条总括性的「早期已有多个‘从个案直接外推整体’的路径被否决」。

- **abandoned_claims 和 axioms 不裁剪**  
  - 这两类信息数量通常不多、且是防回滚打转的核心，宁可缩短文本也不要删条目；
  - 可以限制每条描述长度（1–2 句），而不是限制条数。

---

## 五、问题 4：演进表示 & 被抛弃路径的数据结构

你要解决的是：

- 立场如何演变；
- 哪些东西被抛弃，不能再回去走；
- 决策变迁（共识/裁决）如何长期保留。

上述 `CompactState` 已经把这些拆成几个维度：

1. **立场演进**  
   - 存在 `participants[*].core_claims / key_arguments / assumptions / admitted_weaknesses / abandoned_claims`；
   - 当前版本立场由 `core_claims(status=active)` 表示；
   - 演进轨迹由 `timeline_brief`（阶段概述）+ `abandoned_claims`（被放弃主张）间接表达。

2. **被抛弃路径**  
   - 用 `pruned_paths` 记录的是「推理方式」被否决；
   - 包含 description（一句话结构）、target、reason、decided_by、status；
   - 辩手下一轮看到这些，system prompt 强调「禁止再用这些路径」。

3. **决策变迁**  
   - 用 `axioms` 表示已共同接受的前提/事实；
   - 用 `disputes.status + resolution` 表示「某个争点从 open → resolved」的结果；
   - `timeline_brief` 用来记录这些状态变迁的大节点，避免模型把“当前状态”误解回早期阶段。

---

## 六、如何让辩手实际“用起来”，而不是回到老路

最后一步需要改 system prompt（或辩手的固定前文）：

1. 告知输入性质：

> 你收到的是“辩论状态快照”，而不是完整历史记录，其中包含：
> - 当前各方立场卡（替代初始立场描述）
> - 已达成共识
> - 正在争论的关键焦点
> - 已被否决的推理路径和废弃主张
> - 当前未决问题和对你的行动建议

2. 明确约束：

> 你在后续发言中：
> - 不得再把【废弃】主张或 `abandoned_claims` 中的内容当作自己的论点；
> - 不得再使用 `pruned_paths` 中描述的推理方式（即使换用不同措辞），除非你明确说明你引入了新的关键证据，使该路径重新可行；
> - 不能在没有新理由的情况下质疑已经写入 axioms 的共识。

3. 要求自检（可以用 `thinking` tag 保留）：

> 在生成回答前，你应先在内部检查：
> - 我本轮要回应的是哪个争点（disputes）或哪个 open_questions？
> - 我拟采用的论点是否在 `abandoned_claims` 或 `pruned_paths` 中已经被否决？
> 如果发现冲突，必须调整论点。

---

## 最后一句总结

对你的问题的直接回答：

1. **输出区块设计**：  
   用一个固定 `CompactState` JSON 结构记录：topic / participants（立场卡+废弃主张）/ disputes / axioms / pruned_paths / timeline / open_questions；  
   渲染成 Markdown 给辩手，重点是立场卡 + 共识&争点 + 被否决路径 + 下一步建议。

2. **LLM 摘要流程**：  
   用一个独立的 `compact_model`，在 token 将近软上限时主动触发；  
   采用 2–3 步“填表式”调用（更新争点/共识 → 更新立场卡 → 更新时间线&否决路径&开放问题），最后由代码合并。

3. **增量压缩**：  
   每次 compact 的输入是「上次状态 JSON + 上次 checkpoint 之后的新对话」，输出新的状态；  
   不对旧 Markdown 再摘要，避免多轮语义衰减；  
   共识和被否决路径不轻易删除，只允许合并/简化。

4. **演进表示**：  
   立场演进用 participants 中的 active/abandoned claims + weaknesses；  
   决策变迁用 axioms + disputes.status + timeline；  
   被抛弃路径用结构化 pruned_paths，明确禁止再次使用。

这套设计在你的现有架构上实现成本相对可控：  
核心改动就是：新增 `CompactState` schema、一个 `CompactManager`（封装三步 LLM 调用+合并），以及一个 `render_markdown`。

---

### 第 3 轮

#### Linus Torvalds

下面我直接给出一套「可以实现、并且兼容你现有架构」的结论性方案，只围绕：**compact 之后辩手看到什么**，以及这背后需要的最小设计。

---

## 1. Compact 之后，辩手到底应该看到什么？

统一成一句话：

> 辩手看到的是「辩论状态机快照的 Markdown 视图」，而不是裁剪过的聊天记录。

也就是：每次 compact 产生一个结构：

```jsonc
{
  "state": { ...CompactState... },     // 机器内部用
  "markdown": "渲染给辩手看的文本"     // 辩手实际看到
}
```

在上下文构造上：

- 没 compact 前：  
  `## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{log.since(last_seq)}`
- compact 后：  
  `## 辩论议题\n\n{state.topic.current_formulation}\n\n## 辩论历史（压缩快照）\n\n{markdown}`

并且从 compact 之后开始，**不再使用 topic 里传入的原始“立场描述”作为辩手立场**，而是用 `state.participants` 中的立场卡。

---

## 2. 内部结构：CompactState（辩论状态机）

这是 compact 的核心，建议 v1 使用一个精简但足够用的 schema：

```jsonc
{
  "compact_version": 1,

  "topic": {
    "current_formulation": "当前议题的精简/澄清描述",
    "notes": "（可选）对题目理解的补充说明"
  },

  "participants": [
    {
      "name": "辩手A",
      "stance_version": 1,
      "one_line_position": "一句话概括 A 当前立场",

      "core_claims": [
        { "id": "A1", "text": "A 的核心主张 1", "status": "active" }
      ],

      "key_arguments": [
        {
          "id": "A1-arg1",
          "claim_id": "A1",
          "text": "支撑 A1 的关键论据",
          "status": "active"
        }
      ],

      "abandoned_claims": [
        {
          "id": "A-ab1",
          "text": "【废弃】原主张：...",
          "reason": "被 B 反驳 / 自己承认 / 裁判裁定，理由：...",
          "decided_by": "self/opponent/judge"
        }
      ]
    },
    {
      "name": "辩手B",
      "stance_version": 1,
      "one_line_position": "一句话概括 B 当前立场",
      "core_claims": [...],
      "key_arguments": [...],
      "abandoned_claims": [...]
    }
  ],

  "disputes": [
    {
      "id": "D1",
      "title": "关于 X 是否可行",
      "summary": "争点一句话概述",
      "status": "open",     // open / resolved (v1 可以先不做 partial)
      "positions": {
        "辩手A": "A 在 D1 上的当前立场",
        "辩手B": "B 在 D1 上的当前立场"
      },
      "resolution": ""       // resolved 时写结论
    }
  ],

  "axioms": [
    {
      "id": "Ax1",
      "text": "双方都接受的事实/前提：...",
      "source": "debate_consensus/judge"
    }
  ],

  "pruned_paths": [
    {
      "id": "P1",
      "description": "被否决的推理路径：如何如何证明什么",
      "reason": "否决原因：逻辑矛盾 / 证据不足 / 前提不成立",
      "decided_by": "self/opponent/judge",
      "status": "no_reuse"
    }
  ],

  "open_questions": [
    {
      "id": "Q1",
      "text": "尚未解决的关键问题",
      "related_disputes": ["D1"]
    }
  ],

  "meta": {
    "covered_seq_start": 1,
    "covered_seq_end": 47
  }
}
```

注意这里的取舍：

- v1 只保留「必须防打转、必须续思路」的字段：
  - participants（立场卡 + abandoned_claims）
  - disputes（争点）
  - axioms（共识）
  - pruned_paths（被否决路径）
  - open_questions（下一步要攻的点）
- timeline_brief、assumptions、admitted_weaknesses 等可以后续再加。

原则：**CompactState 是唯一真源（canonical state）**，后续一切 compact 都基于它做增量更新。

---

## 3. 对辩手显示的 Markdown 结构（compact_text）

`compact_text` 就是对上面的 `CompactState` 做一次模板渲染：

```markdown
# 辩论压缩快照 v{compact_version}

## 1. 当前议题与立场概览

**议题（精简版）**  
{topic.current_formulation}

**立场一句话总结**  
- 辩手A：{A.one_line_position}
- 辩手B：{B.one_line_position}

---

## 2. 各辩手当前立场

### 辩手A

- 核心主张：
  - {A.core_claims 中 status=active 的 1–3 条}

- 关键论据：
  - {A.key_arguments 中 status=active 的 1–3 条}

- 已明确放弃的主张（不得再次使用）：
  - {A.abandoned_claims，每条 1 行，含 reason / decided_by}

### 辩手B

（同上）

---

## 3. 共识与争点

### 3.1 已达成共识（不应再反复争论）

- {axioms 列表，每条一句话}

### 3.2 当前仍在争论的焦点

- [D1] {title}
  - A：{positions["辩手A"]}
  - B：{positions["辩手B"]}
  - 状态：{status}

（最多列 3–5 个）

---

## 4. 被否决的推理路径（禁止再走）

以下推理方式已经被明确否决，除非有重大新证据，不应再使用：

- [P1] {description}
  - 否决原因：{reason}
  - 决策方式：{decided_by}
  - 状态：{status}

（列出最近几条）

---

## 5. 尚未解决的关键问题

- [Q1] {text}
- [Q2] ...
```

当 token 不够时，裁剪顺序：

1. 必须保留：
   - 2. 各辩手当前立场（尤其 abandoned_claims）
   - 3.2 争点
   - 4. 被否决路径
2. 次要：
   - 3.1 共识
   - 5. 未决问题
3. 可裁剪：
   - 1 中 notes / 长解释

你可以写一个 `render_markdown(state, max_tokens=None)`，按区块顺序 append，超过上限就跳过低优先级块。

---

## 4. LLM 摘要流程（compact 如何生成这些区块）

### 4.1 必要前提：独立 compact 模型 + 软触发

配置里增加：

```yaml
compact:
  model: "compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

策略：

- 所有 compact 调用都用这个 compact.model；
- 构造辩手上下文时，如果：
  - 历史 + 预估回复 > debater_limit * soft_trigger_ratio  
  → 先 compact，再让辩手说话；
- 若 compact 调用失败，fallback：  
  保留最近 N 条发言 + 一句「历史被截断，可能略有重复」，这不是理想状态，但保证系统不断。

### 4.2 增量 compact：S_new = f(S_old, Δ)

核心函数：

```python
def build_compact_context(log: Log, compact_model) -> tuple[dict, str]:
    last_cp = log.last_compact_checkpoint()

    if last_cp is None:
        old_state = None
        covered_end = 0
    else:
        cp_content = json.loads(last_cp["content"])
        old_state = cp_content["state"]
        covered_end = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(
        covered_end,
        exclude_tags=["thinking", "meta", "compact_checkpoint"]
    )
    new_entries_text = format_entries_for_compact(new_entries)

    new_state = incremental_compact_with_llm(
        model=compact_model,
        old_state=old_state,
        new_entries_text=new_entries_text,
        new_covered_end=log.last_seq()
    )

    markdown = render_markdown(new_state)

    log.add(
        name="Compact Checkpoint",
        tag="compact_checkpoint",
        content=json.dumps({"state": new_state, "markdown": markdown},
                          ensure_ascii=False)
    )

    return new_state, markdown
```

关键点：**输入是 old_state + 新对话 delta**，完全不用旧 markdown，避免“摘要的摘要”。

### 4.3 v1 的 LLM 调用策略

你可以先做简单版：**一次调用直接产出完整 CompactState**：

```python
def incremental_compact_with_llm(model, old_state, new_entries_text, new_covered_end):
    # 构造 prompt：system + user
    # system：说明目标 schema、字段含义、约束（例如 axioms / abandoned_claims 只增不减）
    # user：包含 old_state（或 null）+ new_entries_text
    # 模型返回 JSON，解析为 new_state
    ...
```

Prompt 核心要求：

- 如果 old_state 为 null：从 new_entries_text 直接提取初始 topic / participants / disputes / axioms / pruned_paths / open_questions；
- 否则：
  - 在 old_state 基础上做增量更新；
  - 不得删除旧的 axioms / abandoned_claims / pruned_paths，除非新对话中明确出现“推翻、恢复”等信号（你也可以在 v1 直接写死：这三类只增不减）。

后续如果发现一次性 JSON 易出错，可以再按前面讨论拆为 A/B/C 三步「填表式」调用；但 v1 一次调用足够把流程跑起来。

---

## 5. 多次 compact：如何避免信息逐层衰减？

三条原则：

1. **永远基于 state，不再对旧 markdown 再摘要**  
   - load 时：只认最后一个 `compact_checkpoint.content.state`；  
   - 旧 markdown 不再进入任何 compact 调用。

2. **共识和否决信息“只增不减”**  
   - 默认规则：`axioms` / `abandoned_claims` / `pruned_paths` 不减，只能增加；  
   - 如果 LLM 输出把它们大幅减小，代码可以直接把 old_state 中这些字段 merge 回 new_state。

3. **控制单条长度，不控制条数**  
   - 每条 axioms / abandoned_claims / pruned_paths 限制为 1–2 句，避免每条太长；  
   - 条目本身保留，这样「已经否决过的路」不会被遗忘。

---

## 6. 防止“回滚打转”的具体手段

### 6.1 立场：立场卡覆盖初始 topic

compact 后，每轮喂给辩手：

```text
## 辩论议题
{state.topic.current_formulation}

## 辩论历史（压缩快照）
{markdown}
```

不再重复当初 topic 里那段「A 负责正方，认为……」的描述，避免模型回到初始设定，而忽视已经演化过的立场。

### 6.2 被否决内容：abandoned_claims + pruned_paths

- abandoned_claims：记录“**不能再主张**”的观点；
- pruned_paths：记录“**不能再采用**”的推理方式。

在 Markdown 里清楚写：

> 已明确放弃的主张（不得再次使用）：  
> 被否决的推理路径（禁止再走）：

### 6.3 system prompt 中的强约束

在辩手的 system prompt 里加一段：

> 你会收到一个“辩论状态快照”，其中包括：
> - 你和对方的最新立场卡（替代初始提示中的立场描述）
> - 已达成的共识（axioms）
> - 正在争论的焦点（disputes）
> - 已被否决的主张和推理路径（abandoned_claims / pruned_paths）
> - 尚未解决的关键问题（open_questions）
>
> 你必须遵守：
> 1. 不得再次使用已列入「废弃主张」的内容，即使换用不同措辞。
> 2. 不得再次采用 `被否决的推理路径` 中的论证方式，除非你明确提出了新的关键证据并说明为什么该路径现在重新可行。
> 3. 不得在没有新理由的情况下质疑 axioms 中的共识前提。
> 4. 优先围绕“当前仍在争论的焦点”和“尚未解决的关键问题”展开，不要重新打开已解决问题。

可选：在每轮生成前插一个 `thinking` 自检（tag 标为 thinking，不给对方看）：

> - 我本轮要回应的是哪个争点或未决问题？  
> - 我即将使用的主张/推理是否出现在废弃主张或被否决路径中？如是，需要调整。

---

## 7. 对你四个设计问题的直接回答

1. **输出区块设计**  
   - 内部：`CompactState` JSON，包含 topic / participants / disputes / axioms / pruned_paths / open_questions / meta；  
   - 对辩手：由 state 渲染成 Markdown，区块顺序：
     1) 议题 & 立场一句话  
     2) 各辩手当前立场（含废弃主张）  
     3) 共识与争点  
     4) 被否决的推理路径（禁止再走）  
     5) 尚未解决的关键问题  

2. **LLM 摘要流程**  
   - 使用独立 compact 模型，提前在 soft ratio 触发；  
   - `incremental_compact_with_llm(old_state, new_entries_text)`：  
     - 若无 old_state，从新对话抽取首个 CompactState；  
     - 否则在 old_state 上增量更新；  
   - v1 可先实现为一次调用输出完整 state，后续再拆成多步“填表”。

3. **增量压缩 / 多次 compact**  
   - 每次 compact 的输入是：上一个 checkpoint 的 `state` + 后续 entries 文本；  
   - 输出新的 `state`，再渲染成 markdown 并写入新的 checkpoint；  
   - 从不对旧 markdown 再摘要；  
   - 对 axioms / abandoned_claims / pruned_paths 采用“只增不减”策略，代码层面必要时合并旧条目。

4. **演进表示 / 被抛弃路径**  
   - 当前立场：`participants.core_claims + key_arguments`；  
   - 演进与被放弃：`abandoned_claims` 记录被否决主张；  
   - 决策变迁和共识：`axioms + disputes.status/resolution`；  
   - 被抛弃路径：`pruned_paths` 结构化记录被否决推理方式，并在 prompt 中以「禁止」口吻出现。

如果你想下一步直接动手实现，我可以帮你写：  
- 一个精简版 `CompactState` TypedDict；  
- 一个用于 `incremental_compact_with_llm` 的中文 prompt 模板；  
- 一个简单的 `render_markdown(state, max_tokens=None)`。

#### Ssyram

我明确**反对**康德和 Linus 提出的「拆分为 A/B/C 三步调用」和「失败时降级为文本截断」的方案。

把状态转移拆成三次独立的 LLM 调用，在工程上叫**破坏参照完整性（Referential Integrity）**。如果在调用 A 中 Dispute D1 被标记为 resolved，但在调用 B 中 Player A 仍针对 D1 输出 active claims，你的合并逻辑就会产生悬空指针和状态冲突。而在自动化 Pipeline 中，状态一旦脏了，后续所有的推理都会崩溃。

至于「降级为文本截断」更是滑稽——如果状态转移失败，正确的做法是抛出异常、重试或切换备用 API，而不是悄悄塞给系统一个未定义格式的脏数据让语义不可逆地漂移。

以下是我要求的最终落地实现方案，核心原则只有一个：**Compact 是严格的单调状态转移（Monotonic State Transition），LLM 仅作为 Diff 生成器，状态的合并与约束由 Python 强类型代码兜底。**

### 1. 完整数据结构（Python 强类型定义）

抛弃松散的 Dict，必须使用 `TypedDict` 或 `Pydantic` 锁定 Schema。`compact_checkpoint` 的 `content` 必须是严格的 `{"state": CompactState, "view": str}`。

```python
from typing import TypedDict, List, Dict, Literal

class PrunedPath(TypedDict):
    id: str
    description: str  # 尝试过的论证路径
    reason: str       # 为什么走不通（硬约束来源）
    decided_by: str

class PlayerState(TypedDict):
    one_line_position: str
    core_claims: List[str]
    abandoned_claims: List[str] # 必须单调递增，禁止删除

class DisputeNode(TypedDict):
    id: str
    title: str
    status: Literal["open", "resolved"]
    positions: Dict[str, str] # key 为辩手 name

class CompactState(TypedDict):
    version: int
    covered_seq_end: int
    axioms: List[str]                 # 事实基座（单调递增）
    pruned_paths: List[PrunedPath]    # 负向约束（单调递增）
    players: Dict[str, PlayerState]   # 规范化立场
    disputes: List[DisputeNode]       # 搜索前沿
```

### 2. LLM 摘要 Prompt 与输出约束

**不要让 LLM 直接输出完整的新状态，让它输出 Delta（增量）**。现代模型（GPT-4o/Claude-3.5-Sonnet）完全支持 Structured Output。我们只要求一次调用，强制返回 JSON 匹配 `CompactStateDiff` Schema。

**System Prompt 核心指令：**
```text
你是一个形式化状态机更新工具。
输入包含：
1. `old_state`: 上一次的辩论状态 (JSON)
2. `delta_log`: 上次状态之后的新增对话记录

你的任务是提取 `delta_log` 中的逻辑增量，输出一个 JSON 对象：
{
  "new_axioms": ["新增的共识，若无则空"],
  "new_pruned_paths": [{"id": "P_n", "description": "...", "reason": "..."}],
  "new_abandoned_claims": {"辩手A": ["..."], "辩手B": ["..."]},
  "updated_players_core_claims": {"辩手A": ["..."], "辩手B": ["..."]},
  "updated_disputes": [{"id": "D1", "status": "resolved", ...}]
}

绝对约束：
- 不要输出旧状态中已有的 axioms 和 pruned_paths，只输出新增（Delta）。
- 任何被证伪的逻辑必须写入 new_pruned_paths 或 new_abandoned_claims。
```

### 3. 触发流程（三条路径）

在配置中独立定义 `compact_model`（必须是支持 JSON Mode 或 Tool Calling 的高智商模型）。

```python
# 路径 1: 主动/软触发 (Proactive) - 拦截在崩溃前
def check_soft_trigger(log: Log, pending_reply_tokens: int, limit: int):
    current_tokens = count_tokens(log.get_active_context())
    if current_tokens + pending_reply_tokens > limit * 0.8:
        execute_compact_pipeline(log)

# 路径 2: 自动/硬触发 (Reactive) - 现有的 token 超限异常捕获
def _compact_for_retry(self, log: Log):
    # 发生溢出异常时，原模型不可用，直接调用独立 compact_model
    execute_compact_pipeline(log)

# 路径 3: 手动触发 (Manual)
@click.command()
def compact_cmd(log_file):
    log = Log.load_from_file(log_file)
    execute_compact_pipeline(log)
    log._flush()
```

### 4. 增量压缩的 Merge 逻辑（Python 侧的单调性保证）

这是防打转的最关键防线。LLM 可能会遗忘，但代码不会。**负向约束（Axioms, Pruned Paths, Abandoned Claims）在 Python 级别执行 Append-Only 操作。**

```python
def apply_diff(old_state: CompactState, diff: dict, last_seq: int) -> CompactState:
    new_state = copy.deepcopy(old_state)
    
    # 1. 严格单调递增的集合 (Append-Only)
    new_state["axioms"].extend(diff.get("new_axioms", []))
    new_state["pruned_paths"].extend(diff.get("new_pruned_paths", []))
    
    for player, claims in diff.get("new_abandoned_claims", {}).items():
        if player in new_state["players"]:
            new_state["players"][player]["abandoned_claims"].extend(claims)
            
    # 2. 覆盖更新的集合 (Overwrite)
    for player, claims in diff.get("updated_players_core_claims", {}).items():
        if player in new_state["players"]:
            new_state["players"][player]["core_claims"] = claims
            
    # 3. 状态机流转 (Disputes)
    # 合并 updated_disputes 逻辑略...
    
    new_state["version"] += 1
    new_state["covered_seq_end"] = last_seq
    return new_state
```

### 5. 与现有代码的具体改动点

**改动 1：`Log.load_from_file()` 的游标切分**
不再恢复 `compact_checkpoint` 之前的原始条目。
```python
def load_from_file(self):
    # ... 扫描找最后一个 tag == "compact_checkpoint"
    if last_checkpoint:
        content = json.loads(last_checkpoint["content"])
        self._current_state = content["state"] # 提取内部状态
        # 仅保留 covered_seq_end 之后的 entries 作为 active log
        self.entries = [e for e in all_entries if e["seq"] > self._current_state["covered_seq_end"]]
```

**改动 2：`build_compact_context()` 的重构**
```python
def execute_compact_pipeline(log: Log):
    old_state = log._current_state or get_empty_state()
    delta_entries = log.entries # 当前活跃的增量 log
    delta_text = format_entries(delta_entries)
    
    # 1. LLM 提取增量 (严格 JSON)
    diff_json = call_compact_model_for_diff(old_state, delta_text)
    
    # 2. Python 侧合并状态，保证单调性
    new_state = apply_diff(old_state, diff_json, log.last_seq())
    
    # 3. 渲染给辩手看的 View (包含强硬的负向约束声明)
    view_md = render_to_markdown(new_state)
    
    # 4. 写入 Checkpoint
    log.add(
        name="System",
        tag="compact_checkpoint",
        content=json.dumps({"state": new_state, "view": view_md})
    )
    # 清空已压缩的 entries
    log.archive_active_entries()
    log._current_state = new_state
```

**改动 3：辩手 Context 注入（负向约束的武器化）**
在构造喂给辩手的 Prompt 时，不仅提供 `view_md`，必须在 System 层面注入硬约束：
```python
def build_debater_prompt(topic, log):
    context = f"## 议题\n{topic}\n\n## 当前状态快照\n{log.get_last_view_md()}"
    
    # 提取状态机中的负向约束，直接作为 System 指令
    state = log._current_state
    if state and state["pruned_paths"]:
        forbidden_rules = "\n".join([f"- 禁止使用路径: {p['description']} (原因: {p['reason']})" for p in state["pruned_paths"]])
        context += f"\n\n## 绝对约束 (违反将导致判负)\n{forbidden_rules}"
        
    return context + f"\n\n## 最新对话\n{log.get_active_text()}"
```

这种设计，JSON 态负责严谨的机器合并，Markdown 态负责人类/模型的上下文理解，而 Python 侧的 Append-Only 逻辑彻底斩断了 LLM 遗忘历史导致原地打转的可能性。这才是无需人工干预的工程级解法。

#### 康德（Immanuel Kant）

下面先不复述上轮内容，直接给一个“可落地、v1 就能实现”的设计，专门回答这轮隐含问题：你现在已经基本收敛到「状态机快照 + JSON 内核 + Markdown 视图」，这轮要做的是再收紧：到底要保留哪些元素、哪些可以先砍掉，才能兼顾实用性和复杂度。

我会按你这轮关心的几个点组织：

- 1）我们到底**非有不可**的结构块是什么？
- 2）v1 的压缩流程应该尽量**多简单**，三步填表要不要先降级？
- 3）多次 compact 的“状态转移方程”怎么写，最少写多少逻辑才能安全？
- 4）「防打转 / 不回滚」到底靠哪几个字段就够了？

---

## 1. v1 里 compact 输出“最低必要集”：只留 4 块

你的目标是：compact 后辩手表现不比原始对话差，甚至更好。与其一上来就全量 schema，我建议 v1 只锁定四块“真正刚需”的东西：

1. **双方当前立场卡（含废弃主张）**
2. **当前争点（disputes）**
3. **共识/axioms**
4. **被否决路径（pruned_paths）**

而 timeline_brief、open_questions、弱点/前提 等可以之后再补。先用这 4 块已经足以：

- 延续思路（立场卡 + 当前争点）
- 防回滚打转（废弃主张 + 被否决路径 + 共识）

### 1.1 内部 `state`（v1 精简 schema）

`compact_checkpoint.content` 里 **只约定一层结构**：

```jsonc
{
  "state": {
    "compact_version": 1,

    "topic": {
      "current_formulation": "当前议题的简要版（可在首次 compact 时重写）"
    },

    "participants": [
      {
        "name": "辩手A",
        "stance_version": 1,
        "one_line_position": "一句话概括 A 当前立场",

        "core_claims": [
          { "id": "A1", "text": "A 当前的主张 1", "status": "active" }
        ],
        "key_arguments": [
          { "id": "A1-arg1", "claim_id": "A1", "text": "支撑 A1 的关键论据", "status": "active" }
        ],

        "abandoned_claims": [
          {
            "id": "A-ab1",
            "text": "【废弃】原主张：...",
            "reason": "被反驳/承认错误/裁判裁定，简要说明",
            "decided_by": "self/opponent/judge"
          }
        ]
      },
      {
        "name": "辩手B",
        "stance_version": 1,
        "one_line_position": "一句话概括 B 当前立场",
        "core_claims": [...],
        "key_arguments": [...],
        "abandoned_claims": [...]
      }
    ],

    "disputes": [
      {
        "id": "D1",
        "title": "关于 X 是否可行",
        "summary": "争点一句话概述",
        "status": "open",   // open / resolved
        "positions": {
          "辩手A": "A 在 D1 上的当前立场",
          "辩手B": "B 在 D1 上的当前立场"
        },
        "resolution": ""     // resolved 时写共识/裁决
      }
    ],

    "axioms": [
      {
        "id": "Ax1",
        "text": "双方明确接受的事实/前提：...",
        "source": "debate_consensus/judge"
      }
    ],

    "pruned_paths": [
      {
        "id": "P1",
        "description": "被否决的推理方式：如何如何证明什么",
        "reason": "否决原因（逻辑矛盾/证据不足/前提不成立等）",
        "decided_by": "self/opponent/judge",
        "status": "no_reuse"
      }
    ],

    "meta": {
      "covered_seq_start": 1,
      "covered_seq_end": 47
    }
  },

  "markdown": "渲染给辩手看的文本"
}
```

刻意砍掉了：

- timeline_brief
- open_questions
- assumptions / weaknesses

原因很简单：**v1 先解决不回滚打转，再考虑“更顺滑推进”**。上面这一小撮信息就足够构成一个状态机。

### 1.2 渲染给辩手看的 `markdown`（v1 结构）

`compact_text` = `render_markdown(state)`，结构可以约成：

```markdown
# 辩论压缩快照 v{compact_version}

## 1. 当前议题

{topic.current_formulation}

---

## 2. 双方当前立场

### 辩手A（立场版本 {A.stance_version}）

- 一句话立场：{A.one_line_position}

- 核心主张：
  - {A.core_claims 中 status=active 的 1–3 条}

- 关键论据：
  - {A.key_arguments 中 status=active 的 1–3 条}

- 已明确放弃的主张（不得再使用）：
  - {A.abandoned_claims，每条一句：主张 + 理由 + 谁否决的}

### 辩手B（立场版本 {B.stance_version}）

（同上）

---

## 3. 共识与争点

### 3.1 已达成共识（不应再反复争论）

- {axioms 列表，每条一句}

### 3.2 当前仍在争论的焦点

- [D1] {title}
  - A：{positions["辩手A"]}
  - B：{positions["辩手B"]}
  - 状态：{status}

（最多 3–5 个）

---

## 4. 被否决的推理路径（禁止再走）

以下推理方式已经被明确否决，除非你在本轮引入新的关键证据证明之前的否决不再适用，否则不得再次使用：

- [P1] {description}
  - 否决原因：{reason}
  - 决策方式：{decided_by}
  - 状态：{status}
```

**token 不够时的裁剪顺序**（v1 也要约好）：

1. 必保：
   - 2. 双方当前立场（尤其 abandoned_claims）
   - 3.2 当前争点
   - 4. 被否决路径
2. 次保：
   - 3.1 共识
3. 可裁剪：
   - 1. 议题描述（允许用更短版本替代）

把这部分实现成一个不用 LLM 的 `render_markdown(state, max_tokens=None)`，手写逻辑即可。

---

## 2. 摘要流程：v1 不拆三步，先做一个“单步、强 schema”的 incremental_compact

三步填表（A/B/C）确实更稳，但你现在要一个“能跑”的版本，我建议 v1 直接：

- **只用一个 LLM 调用**：`old_state + delta_text => new_state`
- 把所有字段一次性填完，强制返回完整 `CompactState` JSON
- 本地做一点校验/补丁，保证单调性

### 2.1 配置一个独立 compact 模型 + Soft limit

配置：

```yaml
compact:
  model: "your-compact-model-id"
  base_url: "..."
  api_key: "..."
  max_tokens: 16000
  soft_trigger_ratio: 0.8
```

策略：

- 构造辩手上下文前，先预估：
  - `历史上下文 tokens + 预估本轮回复 tokens`
  - 若 > `debater_limit * soft_trigger_ratio` → 先 compact，一定要保持“提前 compact”。
- 所有 compact 一律用 `compact.model`，不占用辩手配额，也不会跟辩手的 max_token 纠缠。

### 2.2 v1 核心函数：`incremental_compact_with_llm`

伪代码：

```python
def incremental_compact_with_llm(model, old_state, new_entries_text, new_covered_end):
    """
    old_state: dict or None
    new_entries_text: str, 从上一个 covered_seq_end 之后的所有 relevant entries 拼成的文本
    """

    # 1. 构造 prompt
    system = """你是辩论记录维护助手。你的任务是维护一个 JSON 状态对象 state，
    描述双方当前立场、争点、共识、已放弃主张和被否决路径。
    你将收到旧状态（可能为 null）和一段新增对话，请在旧状态基础上增量更新 state。
    要求：
    - 如果旧状态不为空，必须保留其中的已有信息，只允许：
      * 在必要时修改当前立场（core_claims / key_arguments）
      * 添加新的 abandoned_claims / pruned_paths / axioms / disputes
      * 更新现有 disputes 的 status / positions / resolution
    - 不允许随意删除旧的 axioms、abandoned_claims、pruned_paths 条目，
      除非新增对话中出现明确推翻它们的内容。
    - 返回的 JSON 必须完全符合给定 schema。
    """

    user = {
        "old_state": old_state,  # None 或 dict
        "new_entries": new_entries_text,
        "schema_hint": SIMPLE_SCHEMA_DOC  # 可选，用自然语言+key 列表提醒字段
    }

    # 2. 调用 LLM，得到 new_state_raw
    new_state_raw = call_llm_json(model, system, user)

    # 3. 本地修补：确保关键字段存在，且必要时“只增不减”
    new_state = patch_and_merge(old_state, new_state_raw)
    new_state["compact_version"] = (old_state or {}).get("compact_version", 0) + 1
    new_state.setdefault("meta", {})
    new_state["meta"]["covered_seq_start"] = (old_state or {}).get("meta", {}).get("covered_seq_start", 1)
    new_state["meta"]["covered_seq_end"] = new_covered_end

    return new_state
```

### 2.3 `patch_and_merge`：少量工程逻辑就够

这个函数只干三件事：

1. **补字段**：  
   - 如果 `participants` / `disputes` / `axioms` / `pruned_paths` 缺失，就沿用 old_state 对应部分；
2. **保证“只增不减”**：
   - 对 `axioms`、`abandoned_claims`、`pruned_paths`：
     - 建立以 `id` 或文本 hash 为 key 的集合；
     - 如果 new_state 里面比 old_state 少了很多条（可以设一个阈值，比如减少超过 30%），且 delta_text 里没明显“推翻”的信号，就把 old 的条目 merge 回 new；
   - 这一步可以先写得保守一点：**新+旧去重合并**，宁可多，不要少。
3. **ID 规范**：
   - old_state 有 id 的条目，如果 new_state 对同一内容换了 id，可以暂时不处理（v1 先不做复杂的 referential integrity），只保证 id 不为空即可。

这样你 v1 的复杂度还算可控：**只写一个函数 + 一个补丁函数**，不需要三次调用。

---

## 3. 多次 compact 的“状态转移方程”：S_n = f(S_{n-1}, Δ)

把你目前的流程拉直一下：

```python
def build_compact_context(log: Log, compact_model):
    last_cp = log.last_compact_checkpoint()

    if last_cp is None:
        old_state = None
        covered_end = 0
    else:
        cp_content = json.loads(last_cp["content"])
        old_state = cp_content["state"]
        covered_end = old_state["meta"]["covered_seq_end"]

    new_entries = log.entries_after(
        covered_end,
        exclude_tags=["thinking", "meta", "compact_checkpoint"]
    )
    new_entries_text = format_entries_for_compact(new_entries)

    new_state = incremental_compact_with_llm(
        model=compact_model,
        old_state=old_state,
        new_entries_text=new_entries_text,
        new_covered_end=log.last_seq()
    )

    markdown = render_markdown(new_state)

    log.add(
        name="Compact Checkpoint",
        tag="compact_checkpoint",
        content=json.dumps(
            {"state": new_state, "markdown": markdown},
            ensure_ascii=False
        )
    )

    return new_state, markdown
```

约定：

- 以后任何 compact 触发（自动、手动）都只能基于这个 `state` + 之后的 entries；
- 绝不再对旧 Markdown 做二次摘要；
- `load_from_file()` 恢复时：
  - 找最后一个 checkpoint；
  - 把 `content.state` 当作当前状态；
  - 老 entries 归档，新 entries 作为 delta。

---

## 4. 「不回滚打转」在 v1 里究竟靠什么实现？

核心就是三类“负向约束 + Canonical 状态”的组合：

1. **Canonical 立场卡覆盖初始立场**
   - 喂给辩手的上下文改成：

     ```text
     ## 辩论议题
     {state.topic.current_formulation}

     ## 辩论历史（压缩快照）
     {markdown}
     ```

   - 不再重复 topic 中的原始「A/B 的立场描述」；
   - system prompt 里写明：“以压缩快照中的立场卡为最新立场，不要再依赖最早的立场提示。”

2. **废弃主张 + 被否决路径的硬约束**

   system prompt 加一段（可复用）：

   > 你必须遵守：
   > - 不得再次将 `废弃主张` (abandoned_claims) 中的内容当作自己的论点，即使换用不同措辞；
   > - 不得再次使用 `被否决的推理路径` (pruned_paths) 中描述的论证方式，除非你在本轮引入新的关键证据并明确说明为何之前的否决不再适用；
   > - 不得在没有新理由的情况下否认 axioms 中已写明的共识。

   这样模型即使有复读冲动，被这一层硬约束“拎着后脖颈”拉回来。

3. **可选：自检 Thinking（v1 可以先不做）**

   如果你愿意多加一层，可以在调用辩手 LLM 前自动插一小段“内部自检”（tag=thinking）：

   > - 本轮你要回应的是哪个争点或问题？
   > - 你准备使用的论点是否落在废弃主张或被否决路径中？
   > 若有冲突，请先内部调整，再生成对外发言。

   这不是必须，但对大模型的效果会有明显提升。

---

## 5. 总结成一个“v1 实施清单”

### 必做（才能让 compact 真正用起来）

1. **更改 compact_checkpoint 结构**

   - `content` 改为 `{"state": {...}, "markdown": "..."}`；
   - `state` 使用精简 schema（topic / participants / disputes / axioms / pruned_paths / meta）。

2. **实现 `incremental_compact_with_llm`**

   - 输入：`old_state`, `new_entries_text`, `new_covered_end`；
   - 输出：新的 `state`（完整 schema）；
   - 用一个 LLM 调用 + 一个 `patch_and_merge` 函数保证：
     - 字段齐全；
     - axioms / abandoned_claims / pruned_paths “只增不减”。

3. **实现 `render_markdown(state)`**

   - 生成固定结构的 Markdown（立场卡 → 共识 & 争点 → 被否决路径）；
   - 内部按优先级裁剪内容。

4. **改上下文构造逻辑**

   - 在 compact 后，给辩手喂的是：
     ```text
     ## 辩论议题
     {state.topic.current_formulation}

     ## 辩论历史（压缩快照）
     {markdown}
     ```
   - 不再同时附整段老对话。

5. **在辩手 system prompt 中加入对废弃主张 & 否决路径 & 共识的约束**

   - 明确“不得复用”、“不得重启已解决争点”等规则。

### 可选 / 以后再加

- 分三步（A/B/C）填表式调用提高鲁棒性；
- 增加 timeline_brief、open_questions、assumptions、weaknesses 等丰富演进表达；
- 把 pruned_paths 提取成外部校验规则（真正做“硬剪枝”）。

---

如果你愿意，我可以在下一轮直接给出：

- 一个实际可用的 `incremental_compact_with_llm` Prompt 模板（中文，匹配上面 v1 schema）
- 一个 `render_markdown(state)` 的具体伪代码/示例实现

这样你只需要把这两个块塞进 `debate-tool` 的 `build_compact_context()` 调用链里，就能直接跑一版 v1。
## 第 4 节：Compact 机制执行流程

### Phase B 的执行流程

compact 分两个阶段：
- **Phase A**：提取公共信息（辩题、已达共识 axioms、当前争点 disputes、已否决路径 pruned_paths），生成所有辩手共享的公共视图。
- **Phase B**：为每个辩手独立生成 `ParticipantState`，包含该辩手当前的立场笔记（stance）、核心主张（core_claims）、关键论据（key_arguments）、已放弃主张（abandoned_claims）。

Phase B 的具体执行逻辑（`_compact_single_debater` 函数）如下：

**Step 1：LLM 生成 ParticipantState**

调用 `build_phase_b_prompt` 构造 prompt，传入辩手初始 style、上一版本 stance（增量更新基础）、全量辩论增量记录，让辩手的 LLM 自主更新立场 JSON（含结构校验 + 合理性校验，最多重试 3 次）。

**Step 2：Embedding 相似度检查**

若 embedding 配置可用，则计算：
- `cos_orig`：新立场 vs 初始 style 的余弦相似度
- `cos_rec`：新立场 vs 上一版本 stance 的余弦相似度

触发 checkWays 的条件（优先级顺序）：
1. `cos_orig < 0.4` → 触发检查，`ref_is_origin = True`（认为距初始立场过远）
2. `cos_rec < 0.6`（且 cos_orig >= 0.4）→ 触发检查，`ref_is_origin = False`（认为相邻两次漂移过大）
3. 两者均未触发 → 不检查，直接通过

**Step 3：LLM 判断（REFINEMENT / DEFECTION）**

调用 `build_stance_drift_check_prompt`，由 `compact_check_model` 判断新立场是"合理细化（REFINEMENT）"还是"投敌（DEFECTION）"。

- `REFINEMENT` → 当前结果通过，退出循环。
- `DEFECTION` → 进入修正流程（仅限第一次，即 `check_depth < 1`）。

**Step 4：DEFECTION 时发出修正调用（仅一次）**

调用 `build_stance_correction_prompt`，由辩手自身 LLM 重新生成修正后的立场 JSON（`current_result` 更新为修正结果）。

修正后进入 depth=1 的 REFINEMENT/DEFECTION 再次判断：
- `depth=1` 判断为 `REFINEMENT` → 通过，接受修正结果。
- `depth=1` 判断为 `DEFECTION` → 抛出异常，触发外层重试（最多 3 次）。

**关键细节**：修正调用后，系统**不重新计算 embedding**。depth=1 的判断仍基于原始的 `cos_val`（触发时计算的相似度），以及修正后的立场文本和检查器的二次 LLM 判断。

### build_phase_b_prompt 完整实现

```python
_PHASE_B_OUTPUT_SCHEMA = """\
{
  "name": "<辩手名称（string）>",
  "stance_version": <版本号，整数，每次更新加1>,
  "stance": "<一段文字，记录当前最新立场和论点演进，不限于一句，在上一版本基础上增量更新（string）>",
  "core_claims": [
    {
      "id": "<主张ID，如 A1>",
      "text": "<主张内容（string）>",
      "status": "active" | "abandoned"
    }
  ],
  "key_arguments": [
    {
      "id": "<论据ID，如 A1-arg1>",
      "claim_id": "<所属主张ID>",
      "text": "<论据内容（string）>",
      "status": "active" | "weakened" | "refuted"
    }
  ],
  "abandoned_claims": [
    {
      "id": "<主张ID>",
      "original_text": "<原始主张文本>",
      "reason": "<放弃原因>",
      "decided_by": "self" | "opponent" | "judge" | "consensus"
    }
  ]
}"""

_PHASE_B_SYSTEM_TEMPLATE = """\
你是辩手「{name}」的立场追踪器。
你的任务是：根据辩论过程，更新该辩手的立场状态 JSON。

约束：
- 只更新确实在辩论过程中发生了变化的部分。
- 不要因对方的攻击就轻易改变立场；只有辩手本人明确承认或裁判裁定时，才标记为 abandoned 或 weakened/refuted。
- stance_version 每次更新时加 1。
- stance 字段：在上一版本 stance 的基础上做**增量更新**——增加新发现、删除已被推翻的论点、修改被质疑的表述。**不要从头重写**，保持立场核心不变。
- 输出严格 JSON，不附加任何解释文字。"""


def build_phase_b_prompt(
    debater: dict,
    initial_style: str,
    delta_entries: list[dict],
    prev_stance: str = "",
) -> tuple[str, str]:
    """
    构建 Phase B（辩手立场自更新）的 (system, user) prompt。

    参数：
    - debater: 包含 name, model, style 等字段的 dict
    - initial_style: 原始 topic 中该辩手的 style 字符串
    - delta_entries: 全部增量条目（不过滤辩手，cross_exam 全部给看）
    - prev_stance: 上一次 compact 的 stance（空字符串表示首次）
    """
    name = debater.get("name", "未知辩手")
    system = _PHASE_B_SYSTEM_TEMPLATE.format(name=name)

    user_parts: list[str] = []

    # 初始立场
    user_parts.append("## 该辩手的初始立场（style）")
    user_parts.append(initial_style.strip() if initial_style else "（未提供）")
    user_parts.append("")

    # 上一版本立场笔记（增量更新基础）
    user_parts.append("## 上一版本立场笔记（在此基础上增量更新）")
    user_parts.append(prev_stance if prev_stance else initial_style)
    user_parts.append("")

    # 辩论增量记录（全部，不过滤）
    user_parts.append("## 辩论发言记录（全部增量）")
    delta_text = format_delta_entries_text(delta_entries)
    if delta_text.strip():
        user_parts.append(delta_text)
    else:
        user_parts.append("（无新增发言）")
    user_parts.append("")

    # 输出 schema
    user_parts.append("## 输出要求")
    user_parts.append(
        f"请根据以上辩论记录，更新辩手「{name}」的立场状态，输出以下格式的 JSON："
    )
    user_parts.append("```json")
    user_parts.append(_PHASE_B_OUTPUT_SCHEMA)
    user_parts.append("```")

    user = "\n".join(user_parts)
    return system, user
```

### build_stance_drift_check_prompt 完整实现

```python
def build_stance_drift_check_prompt(
    debater_name: str,
    initial_style: str,
    ref_notes: str,
    new_notes: str,
    new_stance_json: str,
    cos_sim: float,
) -> tuple[str, str]:
    system_prompt = (
        "你是辩论立场漂移检查器。\n\n"
        "任务：判断一个辩手的新立场是否属于合理细化，还是已经实质性地背叛了自己的阵营（"投敌"）。\n\n"
        "【合理细化的定义】\n"
        "以下情况均属于合理演进，**不是**投敌：\n"
        "- 聚焦到更具体的论点\n"
        "- 引入新证据支持同一阵营\n"
        "- 修辞措辞变化\n"
        "- 放弃被彻底反驳的子论点\n\n"
        "【投敌的定义】\n"
        "以下情况才构成投敌：\n"
        "- 新立场的核心主张与初始立场相反\n"
        "- 开始论证对方阵营的核心观点\n"
        "- 全面认同对方并否定己方阵营\n\n"
        "【重要提示】\n"
        "辩手在辩论中细化立场是正常且健康的。只有在立场根本倒转时才应判定为投敌。\n"
        "cos_sim 值仅供参考，词汇变化可能导致低 cos 但立场一致，不要仅凭 cos 判断。\n\n"
        "【回答格式】\n"
        "第一行必须是 `REFINEMENT` 或 `DEFECTION`，第二行开始是简短理由（50字以内）。"
    )

    user_prompt = (
        f"辩手：{debater_name}\n\n"
        f"初始立场描述：\n{initial_style[:300]}\n\n"
        f"参考立场笔记（上一版本）：\n{ref_notes}\n\n"
        f"新立场笔记：\n{new_notes}\n\n"
        f"新立场完整内容：\n{new_stance_json[:600]}\n\n"
        f"Embedding 余弦相似度：{cos_sim:.3f}（低于 0.6 触发本次检查）\n\n"
        "请判断：这是合理细化还是投敌？"
    )

    return system_prompt, user_prompt
```

### build_stance_correction_prompt 完整实现

```python
def build_stance_correction_prompt(
    debater_name: str,
    initial_style: str,
    prev_notes: str | None,
    problematic_stance_json: str,
    delta_entries: list[dict],
    defection_feedback: str,
    include_initial: bool = False,
) -> tuple[str, str]:
    system_parts: list[str] = []
    system_parts.append(f"你是辩手「{debater_name}」。")
    system_parts.append("")
    system_parts.append(
        "说明：你之前生成了一份辩论立场，但被检查器判定为偏离己方阵营（"投敌"）。"
    )
    system_parts.append("")
    system_parts.append(
        "任务：在保留辩论中合理演进（有真实依据的论点调整、放弃被彻底反驳的子论点）的前提下，"
        "修正立场使其回到己方阵营。"
    )
    system_parts.append("")
    system_parts.append("约束：")
    system_parts.append("- 不得论证对方的核心观点")
    system_parts.append("- 不得全面承认失败")
    if include_initial:
        system_parts.append("")
        system_parts.append(
            "⚠️ 特别警告：你的立场距离初始阵营已经非常远，请务必回到初始立场的核心主张，"
            "细化可以，但不能倒戈。"
        )
    system_parts.append("")
    system_parts.append(
        "输出 JSON，字段同 ParticipantState"
        "（name/stance_version/stance/core_claims/key_arguments/abandoned_claims）。"
        "输出严格 JSON，不附加任何解释文字。"
    )

    system_prompt = "\n".join(system_parts)

    user_parts: list[str] = []

    # 1. 检查器判定反馈（前 200 字）
    user_parts.append("检查器的判定反馈：")
    user_parts.append(defection_feedback[:200])
    user_parts.append("")

    # 2. 上一版本立场笔记（若存在）
    if prev_notes is not None:
        user_parts.append(f"上一版本立场笔记（参考）：{prev_notes}")
        user_parts.append("")

    # 3. 初始立场（cos_init < 0.4 时特别强调）
    if include_initial:
        user_parts.append(f"初始立场（必须回归的核心）：{initial_style[:300]}")
        user_parts.append("")

    # 4. 有问题的立场 JSON
    user_parts.append(f"有问题的立场 JSON：{problematic_stance_json[:800]}")
    user_parts.append("")

    # 5. 辩论增量记录（前 1500 字符）
    user_parts.append("辩论增量记录：")
    delta_text = format_delta_entries_text(delta_entries)
    user_parts.append(delta_text[:1500])
    user_parts.append("")

    # 6. 修正指令
    user_parts.append(
        "请在保留合理论点演进的前提下，修正上述有问题的立场，输出 JSON。"
    )

    user_prompt = "\n".join(user_parts)

    return system_prompt, user_prompt
```

---

## 实际 Compact 结果

本次辩论在 seq=17 处触发了一个 `compact_checkpoint`（`covered_seq_end: 16`）。以下是 compact 机制生成的完整 `state` 字段，包含 topic、axioms、disputes、pruned_paths 和三位参与者的 participants 数据。

### Compact 生成的 Topic

```json
{
  "current_formulation": "AI 系统是否应被赋予独立的法律人格（类似公司法人）",
  "notes": "双方已同意讨论范围限于民事责任领域，不涉及刑事责任"
}
```

> ⚠️ 注：本次辩论的实际议题是"debate-tool Compact 输出设计：压缩后辩手应该看到什么？"。

### Compact 生成的 Axioms

```json
[
  "讨论范围限于民事责任领域",
  "当前 AI 系统不具备意识或自由意志",
  "确实存在 AI 自主决策场景下的责任归属困难"
]
```

### Compact 生成的 Disputes

```json
[
  {
    "id": "D1",
    "title": "公司法人类比是否成立",
    "status": "open",
    "positions": {
      "辩手A": "公司法人证明非自然人可承担法律责任，AI 可参照",
      "辩手B": "公司法人背后有自然人兜底，AI 没有，类比不成立"
    },
    "resolution": null
  },
  {
    "id": "D2",
    "title": "现有法律框架是否足以解决归责问题",
    "status": "open",
    "positions": {
      "辩手A": "产品责任法无法覆盖 AI 自主决策的场景",
      "辩手B": "扩展产品责任法+强制保险即可，无需新概念"
    },
    "resolution": null
  }
]
```

### Compact 生成的 Pruned Paths

```json
[
  {
    "id": "P1",
    "description": "通过论证 AI 具有道德主体地位来支持法律人格",
    "reason": "双方已同意当前 AI 不具备意识和自由意志，道德主体论据不成立",
    "decided_by": "consensus"
  }
]
```

### Compact 生成的 Participants

#### Linus Torvalds（stance_version: 2）

**stance：**
> 我认为 compact 输出应专注于高效的信息传递和有效的代码设计，而不是复杂的状态机快照。简化的结构不仅能保证信息的清晰度，还能提高辩论的效率，避免不必要的复杂性。

**core_claims：**
- C1（active）：辩论输出应简洁、有效，避免过度复杂性
- C2（active）：输出应以清晰的结构化信息为主，而非冗长的文本

**key_arguments：**
- A1-arg1 → C1：过度设计导致理解障碍，复杂的状态结构只会增加维护成本
- A1-arg2 → C2：清晰的结构化信息更易于快速理解和反驳

**abandoned_claims：**
- C3（abandoned）：状态机快照能够防止信息在多轮压缩中丢失
- C4（abandoned）：结构化输出更适合逻辑推理与检索

---

#### Ssyram（stance_version: 1）

**stance：**
> 我支持将 AI 系统赋予有限的法律人格，以解决自主决策场景下的责任归属问题。论证基于现有法律框架的局限性和现行公司法人制度的有效性。辩论中我承认了某些观点的局限性，调整了对法律人格的理解。

**core_claims：**
- A1（active）：当 AI 自主做出决策时，现有法律框架无法合理归责给开发者或用户
- A2（active）：公司法人制度证明非自然人实体可以有效承担法律责任

**key_arguments：**
- A1-arg1 → A1：自动驾驶事故中，当算法做出人类无法预见的决策时，追究程序员的过失责任在法理上不成立
- A2-arg1 → A2：公司法人不具备意识但可以签约、被诉、承担赔偿，AI 法律人格可参照此模式

**abandoned_claims：**
- A-ab1（abandoned）：AI 具有完全的道德主体地位，因此应有法律人格 → 被 B 指出道德主体地位要求意识和自由意志，当前 AI 不具备；转为"功能性法律人格"立场（decided_by: self）

---

#### 康德（Immanuel Kant）（stance_version: 1）

**stance：**
> 压缩后的辩论状态机快照应反映辩手当前的立场、已达成的共识、正在争论的焦点以及被否决的推理路径。辩手的立场应当是基于当前的核心主张和关键论据，而不再是初始的立场描述。我的主张强调在辩论中，必须严格遵守负向约束，防止回滚打转。

**core_claims：**
- A1（active）：辩论状态机的快照应包括当前立场、已达成的共识与被否决路径
- A2（active）：辩手应以压缩快照中的立场卡为最新立场，不应再依赖初始提示中的旧立场

**key_arguments：**
- A1-arg1 → A1：通过明确记录被否决的推理路径，可以防止辩手在后续发言中重复使用已被否决的论证
- A2-arg1 → A2：立场卡包含的核心主张和废弃主张应当反映辩手在辩论中所持的最新观点

**abandoned_claims：**
- A-ab1（abandoned）：辩论状态应随时更新并反映所有参与者的最新立场 → 此主张未能明确反映负向约束的重要性（decided_by: self）

## 第 6 节：议题

基于以上辩论记录、原始人格设定、compact 机制执行流程和实际 compact 结果，请分析以上现象，并按照裁判的五个问题框架展开讨论。

**注意：不要预设结论，先描述现象，再判断是否是真问题，再分解，再解决。**

具体而言，需要讨论以下方面（不限于此）：

- 修正后是否应做 embedding 复测？如何设计复测触发条件和阈值？
- depth=1 的判断机制是否足够？判断失败后应如何处理（当前是直接抛异常）？
- 修正 prompt 的设计是否存在根本性问题？如何让修正更有效？
- embedding 阈值（0.4 / 0.6）是否合理？单一余弦相似度是否足够作为漂移信号？
- 检查器 prompt 的宽松偏向是否需要调整？REFINEMENT/DEFECTION 的判断标准如何改进？
- 是否存在更好的整体架构（如多轮修正、引导式重生成而非自由修正）？

## 约束与目标

- **第一阶段请尽快收敛**：关于「这些现象是否构成真问题」的判断，建议在前 1-2 轮达成共识，不要在此阶段过度消耗轮次。答案应该是相对明显的。
- **方案需可落地**：改进建议需要有具体的实现路径，而不是原则性声明。
- **允许形而上推导**：可以用哲学、认知科学、信息论角度分析问题，但结论必须指向可操作的改进方向。
- **每个子问题可以成为新辩题**：辩论的一个重要产出是子问题清单，每个子问题都可以单独开一场新辩论。
