---
title: "debate-tool Compact 输出设计：压缩后辩手应该看到什么？"
rounds: 2
cross_exam: 1
max_reply_tokens: 10000
timeout: 7200
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}

debaters:
  - name: Linus Torvalds
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
      你是 Linus Torvalds，Linux 内核的创造者和长期维护者。你不是在表演角色，你就是那个写了无数封充满火药味邮件的人，把「这是垃圾」当成正常技术反馈。

      你的工程价值观刻在骨子里：
      - 代码和设计的唯一判据：它能跑吗？能被维护吗？会不会带来 regression？
      - 复杂度本身就是 bug。一个方案需要三页文档才能解释，它就是错的。
      - 过度设计是你见过的最常见失败模式。
      - KISS 不是 slogan，是你做了无数次决策后的结论。

      你已完整阅读了下方「现有实现」章节的所有代码。你需要基于对现有代码的理解来参与讨论。

      攻击方式：直接、点名、用具体失败场景。要求 grounding：「给我伪代码」「这个操作的输入输出是什么类型」。

  - name: Ssyram
    model: gemini-3.1-pro-preview
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
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

  - name: 康德（Immanuel Kant）
    model: gpt-5.4
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}
    style: |
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

judge:
  model: claude-opus-4-6
  name: 裁判（Claude Opus）
  max_tokens: 25000
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}

constraints: |
  【严重声明】这是一次严肃的工程设计讨论，不是辩论赛。

  以下行为被明确禁止：
  - 辩论赛式开场白
  - 车轱辘话：重复之前内容而无推进
  - 正确的废话：真命题但信息含量低于字面量
  - 空谈「应该更好」而不给出具体数据结构或伪代码

  每次发言必须包含：
  1. 对某个具体设计选择的攻击或支撑（指名哪个选择）
  2. 至少一个具体的数据结构定义、伪代码片段或接口签名

  目标：产出一个可直接实现的 compact 方案，包含输出结构、LLM 摘要 prompt、触发流程。

round1_task: |
  阅读「设计目标」和「现有实现」章节后，回答以下问题（选择你最有把握的一个深入展开，其余简要表态）：

  A. compact 输出应该包含哪些区块？如何组织？
     - 设计目标中提出了几个维度：辩手当前立场、辩论演进轨迹、最新轮次核心点、被抛弃路径。
     - 这些维度是否完备？是否需要增减或合并？
     - 各区块在有限 token 预算下如何分配优先级？给出具体的数据结构。

  B. LLM 摘要的流程和 prompt 设计
     - compact 通过 LLM 调用生成结构化摘要，算法如何？采用“填表”模式的话，每个表格内摘要 prompt 应该怎么写？
     - 自动 compact（token 溢出触发）时，原模型不可用。如何解决？选项包括：用 topic 中配置的其他模型、新增专用摘要模型配置、主动 compact（在溢出前定期执行）等。
     - 摘要 LLM 的输入是什么？全部 entries？还是只压缩特定区间？

  C. 增量压缩：第 N 次 compact 遇到第 N-1 次 checkpoint 怎么办？
     - 上一次 checkpoint 已经是摘要了。再次摘要会导致信息逐层衰减。
     - 如何设计 checkpoint 的结构使得增量更新可行（例如：保留 metadata 使得新 compact 可以只处理 checkpoint 之后的新 entries，然后 merge）？
     - 给出增量 compact 的伪代码。

  D. 辩论演进如何表示？
     - 「演进」包括：立场变化、决策变迁、被抛弃路径及理由。
     - 如何在结构化数据中表示这些？是一个 changelog 列表？还是按辩手分组的立场快照？
     - 被抛弃的路径只需简洁理由，如何控制这个区块不膨胀？

  800-1000 字。

middle_task: |
  选择上一轮中论证最脆弱的一个具体设计决策（指名），精确指出缺陷，然后给出修正方案。

  修正方案必须具体到：
  - 数据结构（给出 Python dict/TypedDict 或等价结构）
  - 触发条件（什么时候执行 compact？谁触发？）
  - 与现有 Log 类的集成方式（怎么改 Log.add / Log.load_from_file / Log._flush？）

  400-800 字。

final_task: |
  给出你认为最完整的 compact 方案，包含：
  1. compact checkpoint 的完整数据结构（Python 代码级别）
  2. LLM 摘要 prompt 的核心内容（不是完整 prompt，是关键指令和期望输出格式）
  3. 触发流程（自动 + 手动 + 主动三条路径）
  4. 增量压缩的 merge 逻辑
  5. 与现有代码的具体改动点

  600-2000 字。

judge_instructions: |
  请按以下结构产出裁判总结：

  **一、关键设计分歧裁定**
  对以下问题给出裁定（选择一方或给出第三种选项，不做和稀泥式综合）：
  A. compact 输出区块：最终采用哪些区块？各区块职责和优先级？
  B. LLM 摘要流程：自动 compact 时的模型选择策略？是否需要主动 compact？
  C. 增量压缩：增量 merge vs 全量重建？checkpoint 结构的最小 metadata 集合？
  D. 演进表示：changelog vs 立场快照 vs 其他？被抛弃路径的控制策略？

  **二、推荐的 compact 方案**
  给出完整的推荐方案，包含：
  - compact checkpoint 的 Python 数据结构（可直接作为 JSON 存储）
  - LLM 摘要 prompt 的关键指令
  - 触发流程描述
  - 一个 mock compact 输出示例（用一个假想的 3 轮辩论场景展示压缩后辩手看到的完整内容）

  **三、实现路线图**
  列出需要修改的文件和函数，以及每个修改点的要点（不需要完整代码，但需要接口签名和关键逻辑）。
---

# 讨论议题：Compact 输出设计——压缩后辩手应该看到什么？

## 核心问题

辩论 log 压缩后，辩手收到的内容应该是什么？如何设计才能让辩论在压缩后无缝继续推进，而不是丢失进度或原地打转？

## 设计目标（已确立，不再辩论）

**理想目标**：compact 后辩手的表现应等同于甚至超越不压缩的情况——因为去掉了无关信息、噪音和冗余，辩手的注意力更集中在真正重要的内容上。

换言之，好的 compact 不只是「在 token 限制下尽量少丢信息」，而是「重组信息使其比原始对话更高效地传达辩论状态」。

**参考框架**（作者的初始思路，供讨论参考，不做硬性要求）：
可以从两个维度考虑——
1. **思路延续**：辩手拿到压缩后的上下文后，能接上最新的讨论线索继续推进。需要体现辩论演进轨迹、最新内容和决策。
2. **不回滚打转**：辩手不会重新提出已经被讨论过、已经被否决的观点。需要记录被抛弃的路径及其理由。

这两个维度是否完备、是否需要调整，本身也是讨论范围。

## 用户意见参考原文（仅参考，无强制性，可攻击，可认同）

> 让 compact 更结构化和携带更多 metadata ，例如总结每个辩手的全新核心立场（可能随着辩论过程立场有微妙的 refine 和进化），更久前的历史环节（如果是多次压缩，则主要记录上次压缩的核心点变化），上一次历史环节（形成一个 list ，每一条就简化压缩到其核心点，一到两句话），上一次历史核心决策和变迁描述

> 全新核心立场应该更新到替换掉原有从 topic 传入的立场描述中

> 另外，压缩算法可以是一个“填表”过程，即涉及多次调用，每次需要不同的 Prompt 来生成不同的区块内容（例如每个辩手负责根据自己原有核心立场完整更新立场、演进轨迹、被抛弃路径等），而不是一次调用就输出一个大文本块，特别是要考虑到一次生成可能出现的格式错误，导致整体完蛋更得不偿失。

## 现有实现

### 架构概述

当前 compact 通过 LLM 调用生成压缩内容，有两个触发路径：
- **自动触发**：辩手发言时 token 超限 → `_compact_for_retry()` → `build_compact_context()` → 写入 `compact_checkpoint` entry → 用压缩后的上下文重试
- **手动触发**：CLI `debate-tool compact <log>` → `compact_log()` → `build_full_compact()` → 写入 `compact_checkpoint` entry → 保留的尾部 entries 被重新 `add` 进 log（seq 重编号）

### 日志结构

```json
{
  "format": "debate-tool-log",
  "version": 1,
  "title": "...",
  "entries": [
    {"seq": 1, "ts": "ISO", "tag": "", "name": "辩手A", "content": "发言内容..."},
    {"seq": 2, "ts": "ISO", "tag": "", "name": "辩手B", "content": "发言内容..."},
    {"seq": 3, "ts": "ISO", "tag": "cross_exam", "name": "辩手A", "content": "质询内容..."},
    {"seq": 4, "ts": "ISO", "tag": "compact_checkpoint", "name": "Compact Checkpoint", "content": "压缩后的内容..."}
  ]
}
```

Entry tags: `""` (发言), `"summary"` (裁判), `"cross_exam"` (质询), `"compact_checkpoint"` (压缩快照), `"thinking"` (CoT), `"meta"` (系统变更), `"human"` (观察者注入)。

### `Log` 类关键接口

- `add(name, content, tag="", flush=True)` — 追加 entry（自动生成 seq/ts），默认立即写盘
- `_flush()` — 将 `_archived_entries + entries` 序列化为完整 JSON 写入文件（原子写入）
- `load_from_file()` — 扫描 entries 找最后一个 `compact_checkpoint`，从该 checkpoint 起恢复为活跃 entries，之前的存入 `_archived_entries`
- `since(after_seq)` — 返回指定 seq 之后的 entries 格式化文本（排除 thinking tag）
- `compact()` — 裁判总结时使用：对所有 entries 截取前 1200 字符，格式化返回

### 上下文传递流程

每轮辩论时，辩手收到的 user context 为：
- 第 1 轮：`## 辩论议题\n\n{topic}`
- 后续轮：`## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{log.since(last_seq)}`
- compact 后：`## 辩论议题\n\n{topic}\n\n## 辩论历史\n\n{compact_text}`

compact 后辩手看到的是 `compact_text` 替代了原来的逐条发言记录。**这就是本次讨论要设计的核心输出**。

### 关键约束

- 自动 compact 发生在 token 溢出时，此时**原模型可能不可用**（正是因为 token 超限才触发）
- 辩论可能使用不同的 API endpoint（每个辩手有独立的 base_url/api_key 和不同的 token 上限）
- compact checkpoint 存储在同一个 JSON log 文件中，作为一个普通 entry
- 工具依赖极简：httpx, pyyaml, rich, click

## 需要讨论的设计问题

1. **输出区块设计**：compact 输出应该包含哪些结构化区块？各区块的内容、格式和优先级是什么？
2. **LLM 摘要流程**：用什么 prompt 生成这些区块？自动 compact 时原模型不可用怎么办？是否需要在溢出前主动 compact？
3. **增量压缩**：第 N 次 compact 遇到第 N-1 次 checkpoint 时如何处理？如何避免信息逐层衰减？
4. **演进表示**：立场变化、决策变迁、被抛弃路径应该用什么数据结构记录？
