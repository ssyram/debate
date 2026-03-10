# 四象探索代理：计算机情报 SKILL 设计 辩论日志

> 2026-03-10T16:44:13.855210

---


### [1] Linus Torvalds

*2026-03-10T16:36:11.281324*

你这个问题的核心矛盾很简单：v3 四象引擎靠“强类型状态机 + 持久化快照 + 可计算的终止条件”把 LLM 约束成一个可重复的系统；而你现在只有“LLM + 几个一次性工具调用”，还**没有持久化外部存储**。所以别装作还能做同一件事。你能做的是：在**单次会话上下文**里模拟一部分状态机；跨会话基本靠用户复制粘贴输出（这就是“人肉持久化”）。

下面按四个节点把能力边界讲清楚，并且每点都给“操作含义”“具体崩溃场景”“降级策略”。最后我会点名：最贵的是哪个维度。

---

## 1) 广度维（MB）：所谓“多源系统性覆盖”在无持久化下到底意味着什么？

### 可操作含义（在 SKILL 里能做到的版本）
“多源系统性覆盖”在你这个约束下，不是什么玄学“平衡张力源”，而是一个**可执行的采样计划**：

- 维护一个**SourceClass 列表**（例如 `papers/arxiv`, `code/github`, `docs/official`, `blogs`, `benchmarks`, `discussions`）
- 每个 epoch 强制按配额取样：  
  - **内部轴 50%**：由 LLM 从用户目标推导出评估轴（性能/复杂度/适用任务/训练需求/推理成本/生态成熟度/替代方案），再把轴“分裂”成互相拉扯的子问题  
  - **经验层 50%**：每个 SourceClass 至少 1 个查询/结果（不够就补）
- 同源性去重：不是“感觉像”，而是对“探索方向的关键词集合”算 Jaccard，相似度≥0.6 就合并

问题是：你没持久化，那这些集合和配额怎么活下来？答案是：**只在本次对话里活着**，并且每轮都把“当前覆盖表”打印出来，让用户能复制走。

### WebSearch 随机性 + LLM 序列生成，会不会根本无法平衡多张力源？
是的，你不能“保证”平衡，只能做**可观测的近似**。具体问题：

- **WebSearch 不稳定**：同一个 query 不同时间结果排序变、缺失、A/B；你无法复现实验
- **LLM 序列偏置**：先想到的轴会主导后续探索（典型：先讲性能就永远在性能里打转）

所以别吹“系统性覆盖”，你只能做到：
- **显式配额 + 强制轮换 source class**
- **每轮强制输出 CoverageMap**（轴×来源）让人能看出你偏科了没有
- **可重复性弱**：除非你把“用过的 query + 命中 URL”都记录在输出里

### MB 在这种架构下的失败模式（具体）
- 用户问“调查 Mamba”，LLM 自动把它当成“论文综述”，结果**只看 arXiv/博客**，完全漏掉：
  - CUDA kernel 实现瓶颈
  - Triton/FlashAttention 类对比
  - 真实推理部署（TensorRT、vLLM 集成）
- 或者反过来，只抓 GitHub star 多的 repo，把 marketing 当事实。

### 降级策略
当“多源”做不到（例如 WebSearch 命中太少）：
- 降级为“**轴优先**”：至少保证评估轴覆盖，来源不足用同源补齐，但必须标记 `source_gap: true`
- 输出 `GapSpec`：缺失的来源类（比如 `benchmarks`）是阻塞还是非阻塞（阻塞规则必须给数字，见 PA）

---

## 2) 清晰维（CC）：一句“调查 Mamba”怎么编译成精确查询？要不要独立阶段？如何纠错？

### 结论：必须是独立显式阶段
“在 prompt 里自然完成”是骗自己。你让 LLM边想边搜，它会：
- 偷懒跳过假设定义
- 用搜索结果反向塑形问题（confirmation bias）
- 你根本不知道它漏了哪些子问题

所以 CC 必须是**强制输出结构化 QueryPlan**，并且在开始 WebSearch 前完成。

### 你要的不是“精确查询集合”，而是“可证伪声明 + 查询对”
对“调查 Mamba”，CC 应该输出类似：

- 任务定义：Mamba 属于 state space model 系列；目标是“理解其核心机制 + 与 Transformer 的差异 + 工程实现与性能证据”
- 生成 6-10 个 `TestableClaim`（每个带 `falsifiable_statement`）
- 每个 claim 绑定：`queries[]`、`expected_evidence_type`（论文/benchmark/源码/文档）、`stop_condition`

例子（简化）：
- Claim: “在长序列建模上，Mamba 的计算复杂度对序列长度更接近线性而非二次。”  
  falsifiable: “在同等 hidden size 下，seq len 从 2k→16k，FLOPs/延迟增长率显著低于标准 attention 基线。”  
  queries:  
  - `"Mamba selective state space model complexity linear sequence length"`  
  - `"Mamba vs transformer long context benchmark latency"`  

### 如果 LLM 跳过精确化直接搜索，怎么检测并纠正？
你得有**硬性门禁**，否则“检测”只是事后总结。

在 SKILL 里做门禁的方式：
- 规定：任何 WebSearch/WebFetch 前，必须输出 `QueryPlan`（可机器检查的格式）
- 如果对话里出现了工具调用而 `QueryPlan` 为空：触发“CC missing”修复流程：停止搜索、回退、补齐计划、重新开始

没有 hooks 时只能靠 prompt 纪律；有 Claude Code hooks 才能做自动拦截（但你现在还没进入实现轮，我只说边界：**纯 prompt 无法强制**，只能“要求”，会被模型偶尔违反）。

---

## 3) 深度维（D2）：WebFetch + Grep 能追溯多深？什么时候系统性失效？怎么降级？

### 能做到的“深度”
在没有专用学术/代码索引的情况下，D2 的上限就是：
- 抓到公开网页（HTML/PDF 直链） → 提取关键段落/表格/结论
- 对一个 GitHub repo（如果能访问）：
  - WebFetch 抓 README / docs
  - 但你没有原生“repo 全量抓取 + 本地索引”，除非用 Bash+git clone（这算工具扩展策略的一部分）

仅靠 WebFetch+Grep，所谓“引用链追溯”经常断在第二步：你能看到引用列表，但拿不到引用内容。

### 系统性失效场景（具体，不是泛泛而谈）
1) **Paywall/登录墙**：ACM/IEEE/Springer，WebFetch 只能拿到登录页  
2) **动态渲染**：内容通过 JS 加载（很多 docs/benchmark dashboard），WebFetch 拿到空壳  
3) **反爬/限流**：频繁 fetch 被 429；你没有重试/退避策略就死  
4) **私有仓库/企业博客**：链接存在但不可访问  
5) **PDF 复杂排版**：抓到 PDF 但文本提取失败（图表、双栏、公式），导致证据原子不可用  
6) **“证据在代码里”**：关键实现细节只在源码/commit discussion/issue thread；WebFetch 单页抓不出依赖关系

### 降级策略（D2 该怎么诚实）
- 证据强度分级必须允许 `UNVERIFIED` 或最低档（你说 ANECDOTAL→AXIOMATIC，那就老实用 ANECDOTAL），并附上**失败原因枚举**：
  - `fetch_failed: paywall|js_render|404|rate_limited|auth_required|pdf_unreadable`
- 对“引用链断裂”：
  - 降级成“二手证据”：用综述/博客引用，但强度最多到 `WEAK`，并显式标记 `secondary_source=true`
- 对“代码证据不足”：
  - 降级成“实现线索”：列出 repo/文件路径/函数名（如果拿得到），拿不到就承认拿不到

---

## 4) 精度维（PA）：无持久化怎么追踪覆盖？终止条件能塞进 prompt 吗？

### 现实：可以在单次会话里追踪；跨会话不行
PA 要的是三件事：
1) `no_blocking_gap`
2) `coverage >= 0.70`
3) 连续两 epoch 排名稳定

在无持久化下，唯一可行的是：**把状态作为结构化文本放在对话里**（模型上下文里），每轮更新一次，并在输出里回显。

跨 session？除非用户把那段状态复制到下一次对话开头，否则就归零。别幻想。

### 终止判断能编码进 prompt 吗？
能，但“能”不等于“可靠”。纯 prompt 的问题是：
- 模型会“觉得差不多了”然后宣布稳定
- coverage 这种数会被它瞎编

所以 PA 必须把“覆盖率”定义成**可计算**的东西，哪怕计算很粗糙。

一个可实现的近似：
- 预定义轴集合 `Axis = {mechanism, math, training, inference, benchmarks, implementation, ecosystem, failure_modes, comparisons}`
- 每个轴权重 `w_i` 给定（总和=1）
- 轴视为“covered”的条件：至少有 1 个 EvidenceAtom，且强度≥某阈值（比如 ≥ `MODERATE`）  
  coverage = Σ w_i * 1[covered_i]

“排名稳定”也要数字化：
- 维护 TopK claims（K=5）
- 若两轮 epoch 中 TopK 集合的 Jaccard 相似度 ≥ 0.8，则算稳定一次；连续两次稳定才停

**注意**：这仍然依赖模型自我报告证据强度和 TopK 排名，没外部断言就不完全可信。但至少你给了公式，让它没法用“合理/适当”糊弄。

### 没有外部 hook 或子代理状态会怎样？
- 你无法强制每轮更新 CoverageMap
- 你无法防止模型跳步直接输出“已满足终止条件”

Claude Code hooks 能在 PostToolUse/Stop 阶段做“状态注入/校验”，但 OpenCode 不支持。也就是说：**PA 在无 hook 下实现成本直线上升，可靠性直线下降**。

---

## 哪个维度实现代价最高？为什么？

**精度维（PA）代价最高。**

原因不浪漫，很工程化：

- MB/CC/D2 都可以“做得像那么回事”，即便不稳定也只是质量波动；
- PA 要求的是**可计算的终止**和**跨 epoch 稳定性判断**，这天然需要：
  - 状态（覆盖表、GapSpec、TopK 排名、上轮快照）
  - 一致性（同一轴/claim 的 identity 不漂移）
  - 最好还有外部检查（hook 或脚本）

在“只有 LLM + 一次性工具调用 + 无持久化”的条件下，你让 PA 做到 v3 的强度基本是笑话。最多做到“单次会话内的近似状态机”，而且还得把所有中间状态都塞在输出里，防止它自己忘。

---

## 基于第1轮结论的约束（给后两轮用）
- **后续设计优先级**应该围绕 PA：你要不要用 Claude Code hooks 做状态校验/注入？不用就别承诺覆盖率/稳定性是真算出来的。
- MB/CC/D2 可以先用 prompt 约束实现行为差异；PA 不引入外部状态/校验就会变成“贴标签式终止”。

你要继续下一轮，就别再用“语义上保证”这种废话。把你打算用的状态结构（CoverageMap、GapSpec、EvidenceAtom）写成具体字段列表，最好给我一个“epoch trace”：输入一句话 → 生成 QueryPlan → 调用哪些 search/fetch → 产出哪些 EvidenceAtom → 算出 coverage 数字 → 判定继续/停止。否则全是白板涂鸦。

---


### [2] Ssyram

*2026-03-10T16:36:11.281395*

别谈隐喻。我们直接看物理机制。

大模型的本质是「提示词引导的概率分布模式匹配搜索」。它没有内部状态，没有真正的「反思」，只有基于上下文窗口的自回归生成。当我们试图把 v3 引擎的强类型状态机（MB/CC/D2/PA）强行塞进一个仅靠 LLM + 基础工具的 SKILL 时，如果不做物理隔离，系统一定会退化为毫无章法的深度优先搜索（DFS）漫游。

以下是对四个维度的物理边界分析。

### 1. 广度维（MB）：自回归生成注定导致语义坍缩
**操作含义**：在没有外部数据库的 SKILL 中，「多源系统性覆盖」的唯一操作含义是**在调用任何搜索工具前，强制输出一个正交的探索轴矩阵**。
**机制冲突**：WebSearch 的本质是返回 SEO 优化后的「共识排序」，而 LLM 的序列生成本质意味着：一旦它看到第一个搜索结果，后续的生成概率就会被这个结果的上下文严重污染（Attention 机制的局部聚集）。
**结论**：LLM 根本无法在边搜边想的过程中产生「多张力源平衡」。它会迅速滑入某一个技术细节的兔子洞。要实现 MB，必须在 prompt 中设定硬性屏障：**生成正交查询矩阵（JSON 格式）并写入本地文件后，才允许发起第一次 WebSearch。**

### 2. 清晰维（CC）：必须是物理隔离的显式阶段
**精确化步骤**：绝对不能在 prompt 内「自然完成」。任何期望 LLM「先精确化再搜索」的软提示，都会在实际执行中被 LLM 的贪婪工具调用本能打破——它会直接拿着用户的模糊原话去调用 WebSearch。
**检测与纠正**：在缺乏 `PreToolUse` hook（为了兼容 OpenCode）的约束下，我们无法在底层拦截工具调用。
**工程解法**：用类型签名的思想约束行为。在 SKILL 的 prompt 中定义严格的「状态机」：
要求 Agent 必须先调用 `Bash` 执行 `echo '{...}' > .explore_plan.json`，且文件中必须包含明确的 `falsifiable_statement`。如果检测到直接调用 WebSearch，要求其立即停止并退回 CC 阶段。这依然是软约束，但比没有结构好。

### 3. 深度维（D2）：WebFetch 的系统性失效与降级
**追溯深度**：WebFetch + Grep 的深度极其有限。它们只能处理静态纯文本。
**系统性失效场景**：
1. **Paywall/鉴权拦截**：ACM/IEEE 论文库、知乎折叠页。
2. **动态渲染（CSR）**：基于 React/Vue 的现代文档页（如某些官网），WebFetch 只能抓到空的 `<div id="root">`。
3. **反爬策略**：Cloudflare 403 Forbidden（极其常见于技术博客和 GitHub 原始文件）。
**降级策略**（必须编码进 prompt）：
- 遇到 403/空内容，**禁止重试**。
- 立即降级为侧面验证：使用 `site:arxiv.org` 或 `site:github.com` 寻找开源替代文本。
- 将验证强度从 `AXIOMATIC`（源码/原文验证）降级为 `ANECDOTAL`（二手引用/摘要验证），并在最终输出中显式标注置信度。

### 4. 精度维（PA）：拒绝 LLM 决定权重，用文件系统做状态机
**追踪机制**：在无持久化外部存储的架构中，指望 LLM 在长达 32K token 的对话历史中「记住」已覆盖了哪些维度，纯属幻想。上下文稀释会导致严重的幻觉。
**终止判断**：**绝对不能依赖 LLM 的主观判断（"感觉覆盖率差不多了"）**。我对「权重由 LLM 决定」有生理性厌恶——这不可审计。
**工程解法**：必须把本地文件系统当作状态机。
Agent 必须在每个 Epoch 结束时，调用 `Bash` 脚本更新一个名为 `.explore_state.json` 的文件，记录当前找到的 Evidence 数量和对应轴。终止条件必须是硬编码的逻辑：通过 `jq` 或 Python 脚本读取该文件，计算覆盖率是否 `>= 0.70`。只有脚本返回 `true`，才允许 Agent 终止并输出。

---

### 结论：哪个维度实现代价最高？

**精度维（PA）的实现代价最高。**

**原因（基于第一轮分析）**：
MB、CC、D2 本质上是对 LLM 生成和搜索行为的**单步塑形**（生成矩阵、写计划、捕获异常），这在提示词工程的覆盖范围内。

但 PA（精度维）要求的是**跨越时间周期的、精确的数值状态累加与阈值判断（覆盖率 ≥ 0.70，连续两 epoch 排名稳定）**。这直接与 LLM「无状态、数学计算极差、长文本注意力衰减」的物理属性相撞。
要在纯 Prompt + 基础工具的环境下实现 PA，我们实际上是在用非结构化的自然语言引擎，通过极其脆弱的 Bash/文件读写操作，强行模拟一个图灵完备的强类型状态机。只要 LLM 在某一个 Epoch 写错了 JSON 格式，或者忘记了读取前置状态，整个精度收敛循环就会彻底崩溃。

**对下一步设计的硬约束**：
在 Middle Task 的设计中，必须优先解决 PA 的状态持久化问题。所有的 Prompt 结构设计，必须围绕「如何让 LLM 稳定地读写那个充当状态机的本地 JSON 文件」来展开，否则四象框架就是一句正确的废话。

---


### [3] 康德（Immanuel Kant）

*2026-03-10T16:36:11.281432*

我先把你这套“四象”翻译成批判哲学能审查的对象：你要做的不是把 v3 的强类型状态机“照搬”，而是在 **LLM+有限工具** 的条件下，为每一象找到一个可观察、可反驳（falsifiable）的行为准则与停止判据。否则“四象”只剩下调节性口号（regulative Idee），在工程里会伪装成构成性原则（konstitutive Prinzip），把“我希望系统这样”偷换成“系统必然能这样”。

下面按 MB/CC/D2/PA 四象逐点分析其能力边界，并在每点给出：其操作含义、先验风险（概念混乱处）、可推翻条件与可行降级。

---

## 1) 广度维（MB）：在无持久化的 SKILL 中，“多源系统性覆盖”是什么意思？

### 1.1 操作含义（在此约束下的可实现版本）
在无外部持久化、以序列生成+随机 WebSearch 为主的系统中，“多源系统性覆盖”不能再被理解为“全局最优覆盖”（那需要可回溯的状态空间搜索与去重存储），而只能被定义为：

- **源类型覆盖**（可观察）：每个 epoch 至少覆盖若干“来源类型”（arXiv/论文、代码仓库、官方文档、综述/博客、基准/数据集、讨论/issue）。
- **张力类型覆盖**（可观察）：每个 epoch 同时产出  
  - *内部轴分裂*（例如“性能”裂为延迟/吞吐/显存；“可用性”裂为部署/许可/生态）  
  - *经验层立场*（来自论文结论、维护者实践、用户痛点、产业对比）  
  两类各占一半的“探索方向配额”，这不是“真 50/50”，而是 **prompt 强制的配额纪律**。
- **同源性去重（弱形式）**：在无 Jaccard 计算与持久集合时，只能做“局部去重”：在同一轮输出里，要求每条方向都附一个 *premise signature*（前提签名：它假设的比较对象/目标函数/使用情景），并禁止出现重复签名。

这三条把“系统性”从“全局保证”降格为“可审计的程序性约束”。

**可推翻条件**：如果实际运行中出现（a）来源类型长期偏向单一媒介（只剩 arXiv 或只剩博客）；（b）内部轴分裂无法持续产生新维度，只是换说法；（c）方向之间前提签名高度相似仍被当作不同方向——则说明此“系统性覆盖”只是修辞。

### 1.2 WebSearch 随机性 + LLM 序列性是否使“多张力源平衡”不可能？
这里有一个需要先被区分的概念混乱：  
你追求的“平衡”若被当成 **构成性**（系统保证找到真实的多方张力分布），那确实在此工具约束下不成立；因为 WebSearch 的返回分布与 LLM 的生成倾向都受不可见的训练偏置与排名策略支配，你无法先验保证“张力源的客观代表性”。

但若把“平衡”降为 **调节性理念**：系统以配额纪律与来源类型约束，持续逼迫自己去寻找异质来源，那么它仍然有工程意义——它不是保证“世界本就平衡”，而是保证“我不断去寻找反例与异议”。

**结论**：MB 可实现，但必须承认它在此处只能是调节性的“反偏置程序”，不能宣称构成性“覆盖了所有张力源”。

---

## 2) 清晰维（CC）：从“调查 Mamba 架构”到可执行查询集——内嵌还是独立阶段？

### 2.1 CC 的先验地位：它不是“可选步骤”，而是判断力的图型（Schema）
在你的框架里，CC 负责把“对象词”（Mamba）转为“可检验命题”。这一步就是把感性杂多（用户一句话）纳入知性的范畴（可比较、可检验、可检索）。若缺此图型，后续搜索不是“探索”，只是“联想漫游”。

因此：**必须有显式阶段**。理由不是工程洁癖，而是认识论：  
- “直接开始搜索”会把搜索结果的偶然性当成问题结构的必然性（以经验偶然僭越先验结构）。
- 你将失去“可纠错性”：因为没有先立的 falsifiable_statement，就无法判定搜索是否偏航。

### 2.2 如何把一句话变成精确查询集合？
可执行做法是强制输出三层对象：

1) **研究问题分解**（非查询）：  
- Mamba 的核心机制是什么？与 Transformer 的差异点在哪些轴上成立？  
- 关键宣称（例如长序列效率/线性复杂度/精度不降）分别需要什么证据？

2) **TestableClaim 列表**（每条必须可被反驳）：  
- 例如：*“在长度≥X 的序列建模上，Mamba 在吞吐/显存上优于某基线，同时保持某指标不显著下降”*  
- 每条绑定一个轴（性能/精度/可扩展/实现复杂度/生态）。

3) **查询模板**（才是 WebSearch 输入）：  
- “Mamba state space model paper benchmark throughput memory”  
- “mamba vs transformer long sequence perplexity”  
- “mamba implementation CUDA kernel selective scan”  
并要求每个查询对应一个 TestableClaim（否则查询是漂浮的）。

### 2.3 若 LLM 跳过精确化直接开始搜索，如何检测并纠正？
检测标准必须是可观察的，而非“感觉不清晰”。我给你一个最小可行的“编译失败”判据：

- 若某次工具调用（WebSearch/WebFetch）无法回指到某条 TestableClaim 的 `claim_id`，则判定 **CC 未完成**，触发“回退到 CC 重新编译”。

这相当于把 CC 变成一个“工具调用前置条件”。  
**可推翻条件**：如果你允许无 claim_id 的搜索仍被接纳，那么 CC 在认识论上就退化为装饰。

---

## 3) 深度维（D2）：WebFetch + Grep 能追溯多深？系统性失效在哪里？如何降级？

### 3.1 能追溯的深度（在理想网页可取的情况下）
- 可到达：论文 PDF、公开 tech report、开源仓库 README/代码、公开 benchmark 表格、博客的引用链（若链接可访问）。
- 可建立 EvidenceAtom：把摘录（quote）+ URL + 轴绑定 + 极性 + 强度等级写出。
- 可做“浅引用追溯”：从论文的 Related Work/Reference 里抽关键词再 WebSearch。

但注意：这不等于“文献学意义的深追溯”，因为你缺少稳定的引文网络 API（Semantic Scholar/OpenAlex）与持久索引。

### 3.2 系统性失效场景（具体且常见）
1) **Paywall/登录墙**：ACM/IEEE、部分 Springer、部分公司白皮书。  
2) **私有仓库/企业内部文档**：实现细节、真实部署指标不可得。  
3) **动态渲染/反爬**：很多 docs 站点（SPA）WebFetch 得到空壳；或需 JS 执行。  
4) **PDF 结构复杂**：WebFetch 得到 PDF 二进制但无法稳定抽取表格/公式；或抽取错乱，导致证据“看似有”实则不可用。  
5) **基准不可复现**：论文宣称的设置缺失，代码未开源，或版本漂移。

这些不是“工具暂时不够用”，而是你试图把 **现象层可见网页** 当作 **对象整体** 的僭越：你以为“可抓取 = 可证明”。

### 3.3 失效时的降级策略（必须把“不可得”表述为一种认识论状态）
降级不是“先标记待定以后再说”（我对“待定”不满意，因为它不是一种完成的判断）。你需要把它路由成两类明确状态：

- **RegulativeIdea（调节性）**：此命题值得追，但当前工具链无法给出构成性证据；输出应变为“需要何种外部访问条件才能验证”（例如：需机构订阅、需联系作者、需跑代码）。  
- **Anecdotal/Indirect Evidence（间接证据）**：用公开二手来源（他人复现、issue 讨论、独立博客）建立低强度 EvidenceAtom，并明确“不可升级的原因”。

**可推翻条件**：若降级后仍给出高强度（例如 CLAIM 被标为 STRONG/AXIOMATIC），则 D2 的强度分级沦为空话。

---

## 4) 精度维（PA）：无持久化时如何追踪覆盖与终止？prompt 可否编码？

### 4.1 先验审查：PA 的终止条件是构成性的还是调节性的？
“无阻塞 Gap + 覆盖≥0.70 + 两 epoch 稳定”看似客观，但在无持久化下，**“稳定”很可能只是遗忘导致的假稳定**：模型没有记住上一轮排名，自然“没变化”。因此这里必须区分：

- **构成性完成**（你声称已充分探索）在此约束下很难合法化；
- 更合理的是：PA 是 **调节性停止**（在可审计的覆盖记录下，达到一个可接受的停止理由）。

### 4.2 LLM 如何追踪“已覆盖哪些维度”？
在无外部存储时，唯一可靠的“存储”是**当前对话上下文中的结构化表**。因此做法是：

- 强制维护一张 `AxisCoverageTable`：每个轴的权重、是否已有 EvidenceAtom、缺口类型（GapSpec）。
- 每次 epoch 输出都要“重打印”此表（或最少增量更新），否则下一轮就不可审计。

这不是优雅，是必要。

### 4.3 终止判断能否编码进 prompt？
**可以编码规则，但不能保证执行**；因为“终止”需要跨轮对比，而跨轮对比需要稳定状态。Claude Code 若配合 hooks（仅主平台有效）可以在 PostToolUse 写入一个简易 session 文件来避免遗忘；但你给的约束是“无持久化外部存储”，那就只能：

- 在 prompt 中规定：每次 epoch 结束必须输出 `PA_Decision: continue/stop`，并附三条条件的可核查证据（表格行号、gap 列表、排名列表）。
- “两 epoch 稳定”必须通过**在文本中显式保留上一次 TopK 列表**来对照。

**可推翻条件**：如果某次 stop 的理由无法从上下文中的表格与 TopK 对照中复核，那就是“心理学意义的停止”，不是 PA 的精度停止。

---

## 5) 哪个维度实现代价最高？（必须选一个）

**精度维（PA）代价最高**，理由不是“难写 prompt”，而是它在此约束下触及了最硬的先验条件：  
PA 需要“跨 epoch 的同一性”（identity through time）——你要比较覆盖率、GapSpec、TopK 稳定性，这些都要求一个可回溯的、可审计的持久状态。没有状态机/快照/外部存储时，你只能用对话文本模拟，这极其脆弱：上下文裁剪、模型遗忘、措辞漂移都会制造“伪稳定”与“伪覆盖”。

与之相比：
- MB 可以用配额纪律做调节性多样化；
- CC 可以用显式编译门槛强制执行；
- D2 可以在可访问材料上做深挖，并对不可访问处做认识论降级；
- 但 PA 若要保持“构成性终止”的雄心，在无持久化下最容易变成辩证幻象：看似完成，实则只是停止了生成。

---

## 基于第1轮结论（PA 最难）对后续两轮的约束提示
- 后续设计若坚持 v3 的 PA 三条件“构成性终止”，就必须引入 **外部 hook/状态**（Claude Code hooks 或某种本地文件快照）。  
- 若拒绝外部状态，则必须把 PA 明确降格为 **调节性停止**：把“完成”表述为“在当前可审计覆盖记录下的合理停机”，并把残余 Gap 输出为“后续访问条件”。

你若要我在下一轮继续，我会要求你明确选边：  
PA 是构成性完成（则你必须接受 hooks/本地状态），还是调节性停止（则你必须重写终止语义，放弃“稳定=充分探索”的偷换）。

---


### [4] 🔍 **质询** Linus Torvalds → Ssyram

*2026-03-10T16:36:39.993605*

1) **你把“必须物理隔离/写文件才能避免坍缩”说得很绝对，但没有给出可验证的失败判据和对照实验。**  
你声称“边搜边想必然语义坍缩 → 退化 DFS 漫游”，OK，那给我数字：  
- “坍缩”怎么度量？是探索轴的 entropy 降到某阈值？还是来源多样性（arXiv/GitHub/blog/docs）覆盖率低于 X？  
- 对照组是什么？“先输出正交矩阵再搜” vs “迭代生成查询+搜”的 A/B，跑同一输入集（比如 20 个主题），统计覆盖率/重复率/新概念发现率。  
你现在的论证是“我感觉会这样”，这在工程里不算证据。没有可复现实验，你这套“硬性屏障”很可能只是**让流程更僵硬、并不更全面**。

2) **你说“没 PreToolUse hook 就无法拦截工具调用”，然后又说“检测到直接调用 WebSearch 就立即停止并退回 CC”。检测靠什么？**  
这地方是自相矛盾的：  
- 如果没有 hook，你在“工具调用之前”拦不住；  
- 那你所谓“检测到直接调用”只能在工具调用“之后”做事——那第一步已经污染上下文了，你前面又说污染会导致后续生成被严重带偏。  
所以到底哪个是真的？  
给出实际可实现的机制：比如在 skill 里规定一个函数式协议——**任何 WebSearch 结果必须附带当前 `.explore_plan.json` 的 hash**，不匹配就丢弃结果并强制重建计划。否则你这就是白板上的“应该回滚”。

3) **你把 PA 说成“实现代价最高”，但你提出的“文件系统状态机”仍然是脆的，而且你没定义失败路径：JSON 写坏了怎么办？并发/重入怎么办？**  
你自己也承认“只要某一轮写错 JSON 就崩”。那你的工程方案是什么？总不能把“别写错”当设计。最基本的你都没给：  
- `.explore_state.json` 的 schema（字段类型、必填项、版本号）。  
- 原子写：写到临时文件再 `mv`，避免半写入。  
- 校验与修复：`jq -e`/JSON schema 校验失败时怎么处理？是回滚到上一版？还是进入“RB 修复”——但你又说 RB 不在讨论范围内。那就是**缺关键组件**。  
- “连续两 epoch 排名稳定”你也没给公式：稳定是 top-K 集合完全相等？还是 Jaccard ≥ 0.9？K=几？没有数字就别说“硬编码”。

如果你要我接受你的第 1 轮结论，下一轮你至少得补三样东西：  
- 1 个可运行的状态文件 schema + 原子更新脚本；  
- 1 个明确的“排名稳定性”计算公式（含 K 和阈值）；  
- 1 条具体 trace：输入 “调研 Mamba 架构”，第 0 epoch 写出 `.explore_plan.json`，第 1 epoch 更新 `.explore_state.json`，脚本算出覆盖率 = 0.xx，并决定继续/终止。没有 trace，就只是“正确的废话”。

---


### [5] 🔍 **质询** Ssyram → 康德（Immanuel Kant）

*2026-03-10T16:37:15.821576*

你的论证在哲学上是自洽的，但在工程实现和系统收敛上留下了几个足以致命的“模糊地带”。作为研究概率程序验证和构建 AI 工具链的人，我无法接受“调节性理念”这种缺乏硬性约束的描述。

针对你的第一轮发言，提出以下三个尖锐质疑：

### 1. 关于 CC（清晰象）的“初始抽象质量”：如何防止语义漂移？

你把 CC 称为“图型（Schema）”，这在认识论上没错。但在类 CEGAR（反例驱动的抽象精化）循环中，**初始抽象的质量决定了整个精化过程的收敛速度甚至成败**。

如果你只是要求输出 `TestableClaim`，却不规定其**形式化验证逻辑**，LLM 极易在后续 D2（深度象）搜索受阻时，通过微调 `TestableClaim` 的语义来“迎合”已找到的劣质证据（即以经验证据倒逼定义修改）。

**质询：**
请给出 CC 输出的**完整函数签名或类型约束**。
特别是：如何定义一个 `TestableClaim` 的“硬边界”？如果 D2 发现证据不足，系统是应该“修改 Claim”（这可能导致语义漂移）还是“标记 Gap”？你的“编译门槛”如何区分“因为没搜到而失败”和“因为命题本身不可证而失败”？

### 2. 关于 PA（精度象）的“状态见证者”：如何处理上下文熵增？

你承认 PA 在无持久化下最难，并建议在上下文里“重打印表格”作为调节性停止的依据。这在工程上是极其低效且危险的。

随着 Epoch 增加，上下文中的 `AxisCoverageTable` 会迅速堆积大量重复或微调后的信息。LLM 对长文本末端的“概率分布模式匹配”会因为信噪比下降而失效，导致你所谓的“两 epoch 稳定”变成**由于上下文过载导致的认知僵死**（即模型因为读不动前面的状态，只能复读最后一次的状态）。

**质询：**
在无持久化约束下，你如何设计 **“状态见证协议（State Witness Protocol）”** 以对抗上下文熵增？
你是否接受一种“强制压缩机制”？如果接受，请说明在不丢失“跨 epoch 同一性”的前提下，哪些信息必须被丢弃，哪些必须被硬化（Hardened）？请不要用“调节性”这种词，我要看到具体的信息剪枝准则。

### 3. 关于 D2（深度象）的“强度分级”：对“LLM 决定权重”的生理性厌恶

你提出给 EvidenceAtom 标上“强度等级（STRONG/AXIOMATIC）”。这正是我最厌恶的设计——**由 LLM 决定的、不可审计的、主观的权重分配**。

在概率程序验证里，置信度必须来自模型外部的证据属性，而非模型自身的“感觉”。一个来自 GitHub Readme 的“STRONG”和一个来自 OOPSLA 论文 Peer-reviewed 实验数据的“STRONG”，在系统决策时权重逻辑完全不同。

**质询：**
为什么 D2 的强度不是由 **“来源类型（Enum: PeerReviewed/OfficialDocs/Issue/Blog）+ 交叉验证因子（Boolean）”** 这种硬编码逻辑自动计算生成的？
如果你坚持让 LLM 标记强度，请给出一个**可测试的审计规则**：当 LLM 标出 STRONG 时，人类或另一个 Agent 依据什么准则可以判定它“标错了”？如果这个准则不存在，你的 D2 强度分级就是“正确的废话”。

---

**我的底线要求：**
不要再谈“现象层”和“物自身”。请直接告诉我，在 `.claude/skills/explore.md` 的指令里，哪一行代码或哪一段具体的 Prompt 约束，能防止系统在第 3 个 Epoch 时不因为“累了”或“忘掉初始目标”而给出一个虚假的“收敛停止信号”？

---


### [6] 🔍 **质询** 康德（Immanuel Kant） → Linus Torvalds

*2026-03-10T16:37:49.342073*

1) **他把“无持久化”直接等同于“不可重复/不可验证”，但中间那条区分链条没有建立**  
Linus 的论证是：没有持久化快照 ⇒ 只能一次性工具调用 ⇒ 不能做“同一件事” ⇒ 于是许多保证只能是“装作”。这里有一个需要先被区分的概念混乱：  
- **可重复性**是经验层（a posteriori）的要求：同一输入在相同条件下复现同一输出；  
- **可审计性/可追责性**却可以在先天结构（a priori）上被部分满足：即便不跨会话持久化，只要把“判断的根据”（queries、URL、证据摘录、评分公式、轴覆盖计算）作为**当下输出的公开表象**，依然能形成可检验的理由链。  

尖锐问题：  
- 你把“持久化”当作可重复性的**构成性条件**（constitutive），还是仅仅当作提升工程稳定性的**调节性手段**（regulative）？  
- 若用户接受“可审计但不可复现”的结果（例如一次性调研报告），你的“基本做不到同一件事”的断言还能成立吗？可推翻条件：请给出一个反例设计——不持久化但通过输出可审计轨迹，仍可使第三方复核结论的方案；若存在，你的等同就被削弱。

2) **他要求 PA 的“覆盖率/稳定性”是可计算的，却又承认主要变量由模型自报；这在先验上是循环的**  
Linus 主张 PA 必须“可计算”，于是给了 coverage 与 TopK Jaccard 的公式；但同时又承认：证据强度、是否 covered、TopK 排名都高度依赖模型自我报告。这里的问题不是“工程上不完美”，而是认识论结构：  
- 你想让“终止”成为构成性完成（好像探索已充分），  
- 但你用来宣告完成的量（coverage/稳定）并没有独立于宣告者的客观约束，因而更像一种**调节性理念**：帮助收敛，而非证明已完备。  

尖锐问题：  
- 你凭什么把“coverage≥0.70 + 两轮稳定”当作“问题已被充分探索”的近似等价？这两者在先验上并不等价。可推翻条件：若能给出一个外部可计算的判据（例如：每个 EvidenceAtom 必须绑定可抓取的引用片段并由工具抽取关键字段；或用脚本对 CoverageMap 做一致性检查），才有资格把它从“调节性”推向“部分构成性”。否则它只是“看起来像数”的停止信号。  
- 你说“纯 prompt 会瞎编 coverage”，那你提出的“公式化”到底解决了什么？如果只是把瞎编从自然语言换成数字字段，这并不增加认识的合法性。

3) **他把“hooks 才能门禁/校验”当作必需条件，但没有证明：没有 hooks 就必然无法形成判断力的图型（Schema）**  
Linus 说 CC 必须门禁、工具调用前必须有 QueryPlan；没有 hooks “无法强制”，只能靠“纪律”。这里他把“强制执行”当作唯一保证机制，忽略了另一条路：把门禁转化为**可审计的公共规则**与**失败即自我否定的输出契约**（例如：若未给 QueryPlan，则输出必须标记 INVALID 并拒绝给最终结论）。这是一种把规范从执行层移到判断层的设计。  

尖锐问题：  
- “无法强制”与“无法规范化”不是同一命题。你为何把二者混为一谈？可推翻条件：如果能用纯 prompt 设计出一个自约束协议（例如：任何最终 Answer 必须引用上方结构化状态块的哈希/版本号；缺失则拒答），在实践上显著降低跳步率，那么“hooks 必需”的断言就不是先验必然，只是工程偏好。  
- 更根本地：你把 CC 的门禁视为一种执行约束（工程），还是一种认识论条件（让“搜索”服从“概念”）？若是后者，那么即使有 hooks，也仍需说明：QueryPlan 的范畴与轴是从哪里被合法地引入——否则只是把偏好制度化。

这些质疑的共同点是：Linus 用“工程上更可靠”去滑向“认识上才算合法”。而“有用”与“真/可证成”属于不同范畴；你可以选择调节性收敛，但不能在未给出先验合法性与可推翻边界时，把它伪装成构成性的完成。

---


### [7] Linus Torvalds

*2026-03-10T16:38:43.859210*

你们的质询里有些点是对的，但也有不少是在偷换约束或者要求我证明我从没承诺的东西。我逐条回。

1) **“无持久化=不可验证/不可重复”**  
Kant 说得对：我说的是“做不到 v3 那种同一件事”（强类型+快照+可复现实验），不是说“不能审计”。你们把“可复现”当唯一合法性，这是胡扯。**可审计轨迹**（queries/URL/摘录/计算公式）在单次会话内完全能做，而且这正是我要求把 CoverageMap/GapSpec 每轮回显的原因。反例实验也简单：第三方拿我输出的 URL+摘录去复核结论，复核失败就是打脸。

2) **“没 hook 就无法门禁；但你又说能回退”**（Ssyram）  
是你在混淆“拦截工具调用”与“判无效并拒绝继续”。没 PreToolUse 确实拦不住第一次污染，但**可以把那轮标记 INVALID 并强制重来**，并要求后续所有证据必须带 `plan_hash` 才计入。污染不是末日，**把污染的结果丢弃**就行。你要的是“物理隔离”，我给的是“可执行失败路径”。

3) **PA 文件状态机脆；JSON 写坏怎么办？**（我同意）  
这点是我方案需要补强：  
- `.explore_state.json` 必须有 `version:int, epoch:int, axes: {axis_id: {covered:bool, best_evidence_id:?string}}, topk:[string], history:[{epoch:int, topk:[string]}]`  
- 原子写：写到 `.tmp` 再 `mv`  
- 校验失败：`jq -e .` 失败则**回滚到上一版并进入“STATE_CORRUPT”**，本轮不计入 epoch（不需要 RB 节点也能做：就是停止并要求重写状态文件）。  
- 稳定性公式：`K=5`，`stable = jaccard(topk_t, topk_{t-1}) >= 0.8`，连续两次 stable 且 `coverage>=0.70` 且 `blocking_gaps==0` 才 stop。数字给了，别再要“合理”。

4) **CC 的“语义漂移”**（Ssyram 问 Kant，其实是工程问题）  
Claim 不是随便改。类型约束：`TestableClaim {id:string; falsifiable:string; axis:AxisId; queries:string[]; locked:bool}`。进入 D2 后 `locked=true`，证据不足只能产出 `GapSpec {claim_id, reason:enum, blocking:bool}`，不允许改 claim 文本；想改就新建 claim，新 id，旧的标 `superseded_by`。这就是“硬边界”。

5) **D2 强度分级不应由 LLM 主观打分**  
同意你的一半：强度应主要由**来源类型+交叉验证计数**计算：  
`strength = base(source_type) + bonus(cross_check>=2)`，LLM 只负责填 `source_type` 和引用摘录；审计规则是：source_type 与 URL 域名/路径不匹配就判错并降级。

基于**第1轮结论：PA 最难**，我修正方案优先级：PA 用“文件+脚本可计算”做硬收敛；其余三象用 prompt 纪律即可，但都必须有失败分支与可审计 trace。你们谁还要“玄学保证”，直接滚。

---


### [8] Ssyram

*2026-03-10T16:38:43.859250*

基于第1轮结论（PA 精度维实现代价最高，因为必须解决跨 epoch 的状态持久化），Linus 和康德的质询极其精准。Linus 抓住了我的时序矛盾：没有 Hook 确实无法在物理层拦截工具调用。康德要的是防漂移的类型签名。

我不做 A/B 测试来证明大模型会发生注意力坍缩，这是自回归机制的物理常识。既然本次设计以 Claude Code 为主平台，我们直接在 `~/.claude/settings.json` 注册 `PreToolUse` hook 做硬门禁；OpenCode 兼容性作为附注，降级为基于 Bash `jq` 的软状态机。

对 Linus：你问 JSON 写坏了怎么办？用类型约束和原子操作。
对康德：你问如何消除 LLM 的主观权重？用代数数据类型（ADT）硬编码。

以下是 `.claude/skills/explore.md` 的核心协议层实现。不谈理念，直接看完整的函数签名和边界处理：

```markdown
---
name: explore
description: "执行四象情报探索状态机"
---
# 核心约束：你是一个纯函数式状态机。禁止主观判断，按以下类型签名执行。

## 1. 状态持久化与原子操作 (PA 维)
所有状态必须原子写入 `.explore_state.json`。禁止直接覆盖。
更新命令：`jq '. + <new_data>' .explore_state.json > tmp.json && mv tmp.json .explore_state.json`
如果 `jq` 解析失败，禁止继续搜索，必须读取上一版快照进行恢复。

## 2. 类型签名 (CC & D2 维)
```typescript
// CC 维：初始抽象。一旦写入，禁止修改 Claim 语义（防漂移），只能变更 status。
type TestableClaim = {
  id: string;
  falsifiable_statement: string;
  status: "Pending" | "Verified" | "Falsified" | "Gap";
};

// D2 维：消除 LLM 主观权重。置信度是来源类型的纯函数。
enum SourceType {
  PeerReviewed = 3, // OOPSLA/arXiv
  OfficialDocs = 2, // GitHub README/Docs
  Community = 1,    // Issues/Blogs
  Unreachable = 0   // Paywall/403 (禁止重试)
}
type EvidenceAtom = {
  claim_id: string;
  source_type: SourceType;
  url: string;
  cross_validated: boolean; // 规则：是否有 >=2 个不同域名来源
};
// 强度计算公式硬编码：Score = SourceType * (cross_validated ? 1.5 : 1.0)
```

## 3. 广度门禁 (MB 维)
在首次调用 `WebSearch` 前，必须先生成至少 3 个正交的 `TestableClaim` 写入 JSON。
*(附注：在 Claude Code 中，此规则由 `PreToolUse` hook 校验 JSON 长度拦截；OpenCode 中依赖 prompt 软约束)*

## 4. 终止条件 (PA 维)
禁止你自己决定 "覆盖率差不多了"。
每个 Epoch 结束，你必须执行 `bash -c 'jq ...'` 计算 Σ Score 是否达标，且 Top 5 claims 连续两次 Epoch 的 Jaccard 相似度 >= 0.8。只有 Bash 脚本返回 `true`，你才能终止循环并输出最终报告。
```

回答 Linus 的 OpenCode 兼容性：在无 Hook 环境下，上述协议依靠 Prompt 纪律执行。如果发生跳步污染，系统降级策略是：要求 Agent 擦除当前对话上下文的记忆，仅读取 `.explore_state.json` 重新初始化状态机。

回答康德的上下文熵增：我的状态见证协议就是**只读 JSON，不读历史对话**。每次 Epoch 结束，Agent 必须在逻辑上“忘掉”搜索过程中的中间废话（信息剪枝），下一轮的决策输入仅来自 `.explore_state.json` 里的结构化数组。状态即文件，文件即真理。

---


### [9] 康德（Immanuel Kant）

*2026-03-10T16:38:43.859269*

你对我的三条质询都抓住了同一危险：把“可工作”偷换成“可证成”。但你自身也有一处概念混淆：你要求“硬约束”时，往往把它当作构成性保证（系统必然收敛且不漂移），而在无持久化与有限工具下，我们最多只能把若干环节做成**可审计的判断规则**；其余只能明示为失败状态，而非“待定”。

**(1) CC 语义漂移**：你要“函数签名”，我同意。硬边界应写成：`TestableClaim = {id, axis∈Enum, falsifiable_statement(含可观测量+比较对象+阈值), disallowed_mutations}`。规则：D2 证据不足时**禁止改写 falsifiable_statement 的主谓宾与阈值**；只能产生 `GapSpec{claim_id, gap_type:missing_source|inaccessible|underpowered_query, action}`。何时允许改 Claim？仅当发现“命题不可证”属于**图型缺失**：即连续两轮在≥2类来源均无法给出任何可观测量，此时 CC 将其路由为 `RegulativeIdea`，而不是“微调成可证明的样子”。可推翻条件：若在证据弱时仍出现阈值/比较对象被改写，即判为漂移故障。

**(2) PA 上下文熵增与状态见证协议**：我接受强制压缩，但压缩必须保持“同一性”。协议：每 epoch 只保留一个 `STATE_WITNESS` 块（≤120 行），其余历史一律丢弃。硬化字段：`claims_topK(只保留id与一句话falsifiable) / coverage_table(轴、权重、covered布尔、证据计数) / gaps(最多10条) / used_queries与URL(每claim最多3条)`；可丢弃：长摘录、重复解释、低强度证据细节。稳定性只比较 witness 中的 `topK_ids` 与上一轮 `topK_ids_prev`。可推翻条件：若无法从 witness 复算 coverage 或对照 topK，则 PA 终止无效。

**(3) D2 强度分级的可审计性**：你反对“LLM感觉”，我改：强度由**来源类型×交叉验证**自动算。`source_type∈{PeerReviewed, OfficialDocs, RepoCode, BenchmarkReport, IssueDiscussion, Blog}`，基础分固定；`crosscheck=true`（同一 claim 至少两类来源一致）才可升档；Paywall/JS/403 只允许产生 `UNVERIFIED` 并附失败枚举。审计规则：任一 `STRONG` 必须满足（PeerReviewed/RepoCode/OfficialDocs 之一）且含可抓取引用片段或可定位文件路径；否则判“标错”。可推翻条件：给出一个 STRONG 但不满足上述外部属性，即系统违规。

至于你要的“第3个 epoch 不会虚假收敛”的那一行：它不在玄学里，而在协议里——**若 `STATE_WITNESS` 中缺少上一轮 topK 或 coverage 复算依据，则必须输出 `PA_DECISION=CONTINUE (invalid_stop)` 并禁止总结性结论**。这把“累了就停”降格为显式失败，而非完成。

---


### [10] Linus Torvalds

*2026-03-10T16:42:09.459678*

```markdown
<!-- 产出 1：SKILL 文件 -->
<!-- 文件路径：.claude/skills/explore.md -->
---
name: explore
description: "四象（广度/清晰/深度/精度）驱动的计算机情报/文献探索：先扩张、再编译命题、再取证、最后用可计算终止条件收敛。强调可审计 trace 与失败分支。"
allowed-tools:
  - WebSearch
  - WebFetch
  - Read
  - Grep
  - Glob
  - Bash
---

# Explore（四象）协议 —— 不是玄学，是可审计的状态机

> 基于第1轮结论：**PA（精度/终止）最难实现**，所以本 SKILL 把 PA 做成“可计算的门禁与终止条件”；其余三象用明确的结构化输出与失败分支约束，避免“语义保证”。

你要做的是计算机情报/文献调查（论文/代码/文档/博客/issue）。你必须在整个会话内维持一个**可审计的探索轨迹**：查询词、URL、摘录、评分公式、终止判据。任何没有 trace 的结论都视为臆测。

---

## 0) 工作文件与状态（PA 的地基）

你在仓库/工作目录写入以下文件（若用户禁止写文件，则降级为在回复中输出同结构 JSON，并每轮完整回显）：

- `.explore_state.json`：唯一真实状态（witness + 结构化对象）。  
- `.explore_state.json.tmp`：原子写中间文件（写完再 `mv`）。

### 状态类型（必须遵守）
（这是“类型签名”，别给我写散文。）

```jsonc
{
  "version": 1,
  "epoch": 0,
  "topic": "string",
  "axes": [
    { "id": "A1", "name": "string", "weight": 0.0, "covered": false, "best_evidence_id": null }
  ],
  "claims": [
    {
      "id": "C1",
      "axis_id": "A1",
      "falsifiable": "string",
      "queries": ["string"],
      "status": "PENDING|SUPPORTED|REFUTED|GAP|REGULATIVE",
      "locked": false,
      "superseded_by": null
    }
  ],
  "evidence": [
    {
      "id": "E1",
      "claim_id": "C1",
      "polarity": "PRO|CON",
      "source_type": "PEER_REVIEWED|OFFICIAL_DOCS|REPO_CODE|BENCHMARK|COMMUNITY|BLOG|UNREACHABLE",
      "url": "string",
      "locator": "string", // 论文页码/章节/代码路径+行号/段落锚点；没有就写空并降级
      "quote": "string",   // <= 400 chars 可审计摘录；抓不到就留空并标 UNREACHABLE
      "crosscheck_domains": ["example.com"], // 不同域名集合
      "strength": 0.0,     // 由公式算，禁止脑补
      "timestamp": "ISO-8601"
    }
  ],
  "topk": ["C1", "C2", "C3", "C4", "C5"],
  "history": [
    { "epoch": 0, "topk": ["C1"], "coverage": 0.0, "blocking_gaps": 0 }
  ],
  "gaps": [
    { "id": "G1", "claim_id": "C1", "gap_type": "MISSING_SOURCE|INACCESSIBLE|UNDERPOWERED_QUERY|AXIS_UNCOVERED", "blocking": true, "next_action": "string" }
  ],
  "witness": {
    "plan_hash": "string",
    "topk_prev": ["C1","C2","C3","C4","C5"],
    "topk_now": ["C1","C2","C3","C4","C5"],
    "coverage_table": [
      { "axis_id": "A1", "weight": 0.25, "covered": false, "evidence_count": 0 }
    ],
    "used_queries": ["string"],
    "used_urls": ["string"]
  }
}
```

### 原子写与校验（失败分支必须执行）
- 写入必须用：`jq ... > .explore_state.json.tmp && mv .explore_state.json.tmp .explore_state.json`
- 每轮写完必须：`jq -e . .explore_state.json >/dev/null`
- 若校验失败：**停止**（不要继续搜），进入失败输出：
  - `PA_DECISION=FAIL STATE_CORRUPT`
  - 给出恢复建议：从上一次有效内容重建（或让用户 `git checkout` 恢复文件）。

---

## 1) 四象如何“落地为行为”（别贴标签）

### 广度象（MB）= **多张力源 + 配额 + 去同源**
可观察行为：
1) 你必须先生成**至少 4 条正交轴（axes）**，并给出权重（总和=1.0）。轴是“评估维度/问题张力”，例如：
- 研究脉络/关键论文谱系
- 工程实现/主流代码库与差异
- 性能与基准/可复现实验
- 失败模式/争议与反例
- 应用落地/约束与成本

2) **配额**：每个 epoch 的新查询必须满足：
- `≥50%` 来自“轴驱动的系统覆盖”（按 axes 逐个打洞补齐）
- `≤50%` 允许来自“经验层机会主义发现”（例如看到新名词就追）

3) **同源性去重**：新生成的 claim/query 不能只是同一前提的换皮。
- 规则（可执行近似）：若两个 query 的 token 集 Jaccard ≥ 0.6 或指向同一类来源/同一观点，则标记为同源，必须合并或替换。

失败分支：
- 若 axes < 4 或权重和不为 1.0：`MB_FAIL=AXES_INVALID`，先修正 axes，不准 WebSearch。

---

### 清晰象（CC）= **把“想了解”编译成可证伪命题 + 锁定**
可观察行为：
1) 把用户输入拆成 `TestableClaim`：
- 每条 claim 必须绑定 `axis_id`
- `falsifiable` 必须包含：对象 + 可观测量 + 对照/阈值/可判别条件  
  （例：不是“X 更好”，而是“在基准 Y 上，X 在 Z 指标优于/劣于 T，且有公开可复现实验/代码佐证”。）

2) **锁定规则**：
- 一旦 claim 进入取证（有 evidence 关联）必须 `locked=true`
- locked 后禁止改写 `falsifiable` 的主谓宾与阈值；证据不足只能产出 `GapSpec`
- 若确实要改：新建 claim（新 id），旧 claim 填 `superseded_by`

3) 不可证伪则路由为 `REGULATIVE`：
- 条件：连续 2 个 epoch，在 ≥2 类来源中都无法得到可观测量/阈值（只剩“愿景/宣称”）
- 结果：标记为 `REGULATIVE`，不计入 coverage 达标的必要项，但仍可在报告中作为“指导性问题”。

失败分支：
- 若 claim 无法写成可证伪：必须输出 `CC_FAIL=NEEDS_REGULATIVE` 并解释为何不可证伪，禁止假装精确。

---

### 深度象（D2）= **证据原子 + 单轴绑定 + 可审计定位**
可观察行为：
1) 证据最小单元是 `EvidenceAtom`，必须：
- 绑定单一 `claim_id`
- 有 `url` + `locator`（页码/章节/代码路径+行号/段落位置）
- 有 `quote`（抓不到就标注并降级）

2) 强度评分**禁止“感觉”**，只允许公式：
- `base(source_type)`：
  - PEER_REVIEWED=3.0
  - OFFICIAL_DOCS=2.5
  - REPO_CODE=2.5
  - BENCHMARK=2.0
  - COMMUNITY=1.0
  - BLOG=0.5
  - UNREACHABLE=0.0
- `crosscheck_bonus`：若 `crosscheck_domains` 里不同域名数 `>=2` 且极性一致，则 `* 1.5`，否则 `* 1.0`
- `strength = base * bonus`

3) 反证义务：
- 每个 axis 至少 1 条 `CON` 或 “争议/失败模式” evidence（找不到就产生 gap：`MISSING_SOURCE`）

失败分支：
- URL 403/付费墙/JS 抓不到：写 `UNREACHABLE` evidence + `GapSpec{INACCESSIBLE, blocking:true}`，禁止无限重试同一 URL。

---

### 精度象（PA）= **覆盖率 + 排名稳定性 + 阻塞缺口 → 终止**
可观察行为（全部可计算）：

1) 覆盖率：
- `coverage = sum(weight(axis) where axis.covered=true) / sum(weight(all axes))`
- 轴 covered 的判定：该轴存在至少 1 条 `strength >= 2.5` 的 evidence（也就是 PEER_REVIEWED/OFFICIAL/REPO_CODE 且可审计）。

2) TopK 与稳定性：
- K=5（不足 5 就用现有）
- 每个 epoch 计算 claim score：`claim_score = sum(strength(evidence for claim))`
- `topk` 取 claim_score 排名前 K 的 claim_id
- `stable = jaccard(topk_now, topk_prev) >= 0.8`

3) 终止条件（必须同时满足）：
- `coverage >= 0.70`
- `stable` 连续 2 个 epoch 为 true
- `blocking_gaps == 0`

否则：`PA_DECISION=CONTINUE` 并输出具体 GapSpec 列表（最多 10 条，按阻塞优先）。

失败分支（反玄学）：
- 若 witness 缺少上一轮 topk 或 coverage 复算字段：`PA_DECISION=CONTINUE (invalid_stop)`，禁止“总结性收敛”。

---

## 2) 每个 Epoch 的固定执行顺序（MB→CC→D2→PA）

你每轮都必须按下面模板输出一个 “EPOCH TRACE”（简短但可审计）：

1) MB：回显 axes + 本轮新增 query 配额统计（轴驱动 vs 机会主义）
2) CC：新增/更新 claims（仅状态/新增；locked claim 不得改写）
3) D2：抓取证据（每条 evidence 给出 URL/locator/quote/strength）
4) PA：用 Bash 计算 coverage、topk、stable、blocking_gaps，写入 state
5) 决策：STOP 或 CONTINUE（给出下一轮要补的 gap）

---

## 3) 工具使用纪律（别乱跑）

- WebSearch：用于发现候选来源与关键词；每次搜索必须写入 used_queries。
- WebFetch：用于拉取具体页面内容；拉取失败必须写 evidence=UNREACHABLE。
- Read/Grep/Glob：用于本地代码/文档仓库调查（若用户给了 repo）。
- Bash：只做可计算校验（jq/jaccard/coverage），不准用 Bash 瞎编结论。

---

## 4) 最终输出格式（STOP 时）

必须输出四层产物（和“全景扫描→精简→验证→使用指南”一致）：
1) 覆盖地图：axes + coverage + 每轴最强证据
2) 核心发现：topk claims（falsifiable + 结论 + 证据链）
3) 质量证据：gap 清零证明、反证摘要、不可达来源清单
4) 延伸指南：下一步 query 列表（按 axis），以及复现方法（如何用 URL/locator 复核）
```

```jsonc
// 产出 2：Claude Code Hooks 配置片段
// 放入 ~/.claude/settings.json 的 hooks 字段（片段示例）
// 仅 Claude Code 有效；OpenCode 不支持（基于第2轮共识：OpenCode 只能 prompt 软约束降级）
{
  "hooks": {
    "PreToolUse": [
      {
        // 作用：在任何 WebSearch/WebFetch 之前，强制要求状态文件存在且可解析，避免“先污染后补票”
        "matcher": { "tool_name": "WebSearch|WebFetch" },
        "command": "bash -lc 'test -f .explore_state.json && jq -e . .explore_state.json >/dev/null || { echo \"EXPLORE_GATE: missing/corrupt .explore_state.json\" >&2; exit 2; }'"
      },
      {
        // 作用：强制 MB/CC 先行——至少 4 个 axis、至少 3 个 claim 才允许上网
        "matcher": { "tool_name": "WebSearch|WebFetch" },
        "command": "bash -lc 'jq -e \"(.axes|length>=4) and (.claims|length>=3)\" .explore_state.json >/dev/null || { echo \"EXPLORE_GATE: need >=4 axes and >=3 claims before web tools\" >&2; exit 3; }'"
      }
    ],
    "PostToolUse": [
      {
        // 作用：每次网络抓取后把 state 再校验一遍（防止模型写坏 JSON）
        "matcher": { "tool_name": "WebSearch|WebFetch|Bash" },
        "command": "bash -lc 'test -f .explore_state.json && jq -e . .explore_state.json >/dev/null || { echo \"EXPLORE_POSTCHECK: state corrupt\" >&2; exit 4; }'"
      }
    ],
    "Stop": [
      {
        // 作用：Stop 时强制输出必须满足 PA 终止条件；否则 stop 被判无效（基于第1轮：PA 最难，必须硬门禁）
        "matcher": { "reason": "stop" },
        "command": "bash -lc 'jq -e \"(.history|length>=2) and (.history[-1].coverage>=0.70) and (.history[-1].blocking_gaps==0)\" .explore_state.json >/dev/null || { echo \"EXPLORE_STOP_GATE: termination conditions not met\" >&2; exit 5; }'"
      }
    ]
  }
}
```

```bash
# 产出 3：CLI 工具安装命令（推荐）
# Debian/Ubuntu: sudo apt-get update
# macOS: brew install ...

# 通用（优先装这些：可计算校验 + 抓取 + 解析）
# jq: JSON 校验与计算（PA 的硬门禁）
# ripgrep(fd 可选): 本地 repo 快速搜索（D2 证据定位）
# curl + pup: 抓网页与提取文本（WebFetch 不稳定时的备用；D2 深度）
# git: 拉源码与定位提交（D2 深度）
# gh: GitHub 搜索/issue/pr（广度与深度）
sudo apt-get update && sudo apt-get install -y \
  jq \
  ripgrep \
  fd-find \
  curl \
  git \
  pup \
  python3

# GitHub CLI（可选：更强的 GitHub 代码/issue 情报通路）
type gh >/dev/null 2>&1 || sudo apt-get install -y gh
```

```markdown
<!-- 产出 4：MCP 服务器安装推荐表 -->
| MCP 名称 | 安装命令 | 用途 | 对应四象维度 | 优先级 |
|---|---|---|---|---|
| mcp-arxiv | `npm i -g mcp-arxiv` | arXiv 论文检索、元数据、PDF 链接 | 广度（论文覆盖）、深度（原文证据） | 高 |
| mcp-semantic-scholar | `npm i -g mcp-semantic-scholar` | 引用/被引网络、作者/领域聚类 | 深度（引用链）、精度（交叉验证域） | 高 |
| mcp-github | `npm i -g @modelcontextprotocol/server-github` | repo/issue/pr 搜索与元数据 | 广度（实现面）、深度（争议与失败） | 高 |
| mcp-docs（通用文档抓取） | `npm i -g mcp-docs` | 官方文档/README 结构化抓取与分页 | 清晰（提取可证伪条件）、深度（定位章节） | 中 |
| mcp-benchmark-index | `npm i -g mcp-benchmark-index` | 公开基准与 leaderboard 聚合 | 深度（可复现指标）、精度（可计算覆盖） | 中 |
| mcp-crossref | `npm i -g mcp-crossref` | DOI/出版信息校验 | 精度（来源类型判定）、深度（出版追溯） | 低 |
```

```markdown
<!-- 产出 5：四象框架移植评述（≤300字） -->
真正“移植”的部分，是那些在 SKILL 里有**可观察行为与失败分支**的：MB 的轴+配额+同源去重（你能看到 query 如何被约束），CC 的可证伪命题编译与 locked 语义边界（漂移会触发 supersede/GapSpec），D2 的 EvidenceAtom 单轴绑定与可审计定位（URL/locator/quote/强度公式），以及 PA 的 coverage/Jaccard/阻塞缺口三条件终止（能用 jq 复算）。  
隐喻性借用的是“认知哲学味”的部分：例如“内部轴分裂/立场张力”的生成在无外部持久状态与真实对抗性评测下，仍依赖模型生成，更多是启发式而非严格机制。对用户意味着：你得到的是**可审计、可复核、可计算收敛**的调查流程，而不是保证“永不漏网”的认知引擎；当系统做不到（抓不到、不可证伪、证据不足）会显式失败/缺口，而不是用漂亮话糊弄。
```

---


### [11] Ssyram

*2026-03-10T16:42:09.459707*

基于第 1 轮结论（PA 精度维实现代价最高，必须依赖外部文件持久化），以及第 3 轮康德对「语义漂移」的硬边界要求、Linus 对「可执行失败路径」的坚持，以下是最终的 Explore Agent 设计规格。

我剔除了所有隐喻。大模型是概率分布模式匹配器，要让它表现出「探索与收敛」的认知行为，唯一的工程解是**用外部状态文件强行截断它的上下文，用类型签名约束它的生成分布**。

以下产出可直接复制。

### 产出 1：SKILL 文件

文件路径：`.claude/skills/explore.md`

```markdown
---
name: explore
description: "执行四象情报探索状态机（CS领域系统性调查）"
allowed-tools: [Bash, WebSearch, WebFetch, Read, Glob, Grep]
---
# 核心约束
你是一个纯函数式状态机。你的任务是将用户的模糊 CS 领域调研意图，转化为结构化的证据链。
禁止主观判断，禁止「我觉得差不多了」，严格按以下四象协议与类型签名执行。

## 0. 状态见证协议 (State Witness)
所有状态必须原子写入当前目录的 `.explore_state.json`。
更新命令：`jq '. + <new_data>' .explore_state.json > tmp.json && mv tmp.json .explore_state.json`
如果 `jq` 执行失败，进入 STATE_CORRUPT 分支，读取上一版快照恢复。禁止直接依赖对话历史。

## 1. 广度维 (MB): 穷举与防盲区
- **输入**：用户的一句话描述。
- **行为**：执行 BFS 搜索。提取关键词，调用 `WebSearch`。每发现一个新概念/框架，立即追加为新搜索词。
- **输出门禁**：在进入下一阶段前，必须向 JSON 写入至少 3 个正交的主题线索（Theme）。连续 3 次搜索无新概念出现，BFS 才算收敛。

## 2. 清晰维 (CC): 类型实例化与防漂移
- **行为**：将 BFS 发现的主题线索编译为 `TestableClaim`。
- **类型签名**：
  ```typescript
  type TestableClaim = {
    id: string; // 格式: CLAIM_01
    theme: string;
    falsifiable_statement: string; // 必须含可观测量、比较对象
    status: "Pending" | "Verified" | "Falsified" | "Gap";
  };
  ```
- **硬边界**：一旦写入 JSON，**禁止修改 `falsifiable_statement` 的主谓宾与阈值**（防语义漂移）。证据不足只能产出 `GapSpec`，禁止把命题微调成容易证明的样子。

## 3. 深度维 (D2): 消除主观权重与双向追踪
- **行为**：对每个 `TestableClaim` 执行 DFS 追踪（向前找被引，向后找衍生）。
- **计分规则**：禁止你主观打分。置信度是来源类型的纯函数。
  ```typescript
  enum SourceType {
    PeerReviewed = 3, // OOPSLA/arXiv/ACM
    OfficialDocs = 2, // GitHub README/官方文档
    Community = 1,    // Issues/技术博客
    Unreachable = 0   // Paywall/403 (产生 GapSpec，禁止重试)
  }
  ```
- **交叉验证**：同一 claim 若在 ≥2 个不同域名的来源得到支持，`cross_validated = true`。
- **最终强度**：`Score = SourceType * (cross_validated ? 1.5 : 1.0)`。你只负责填 `SourceType` 并附上 URL。

## 4. 精度维 (PA): 硬收敛终止
- **行为**：每个 Epoch（完成一轮 MB->CC->D2）结束时，更新 JSON 里的 `coverage` 和 `topK`。
- **终止判定**：禁止你自行决定终止。你必须调用 `Bash` 执行以下逻辑：
  1. 计算 `coverage` = (已验证 Claim 的 Score 总和) / (所有 Claim 预期最大 Score)。必须 ≥ 0.70。
  2. 提取本次 Epoch 的 Top 5 Claim IDs，与上一 Epoch 比较。Jaccard 相似度必须 ≥ 0.8。
- **输出**：只有当上述条件满足时，读取 JSON 生成最终的《全景调研报告》（含覆盖地图、核心发现、证据链）。否则，开启下一个 Epoch。
```

### 产出 2：Claude Code Hooks 配置片段

基于康德对「上下文熵增」的担忧和 Linus 对「拦截污染」的需求。在 `~/.claude/settings.json` 中注入拦截器，用外部脚本做物理门禁。

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "tool": "WebSearch",
        "command": "bash -c 'if [ ! -f .explore_state.json ]; then echo \"[Hook拦截] 必须先初始化 .explore_state.json 才能开始搜索\"; exit 1; fi'",
        "description": "广度门禁：强制要求 Agent 在漫游前建立状态见证文件，防止无状态的随机搜索。"
      },
      {
        "tool": "Bash",
        "command": "bash -c 'if [[ \"$CLAUDE_TOOL_ARGS\" == *\"rm .explore_state.json\"* ]]; then echo \"[Hook拦截] 禁止删除状态文件\"; exit 1; fi'",
        "description": "状态保护：防止 Agent 在遇到冲突时暴力删除状态机。"
      }
    ],
    "PostToolUse": [
      {
        "tool": "Bash",
        "command": "bash -c 'if [[ \"$CLAUDE_TOOL_ARGS\" == *\"jq\"* && \"$CLAUDE_TOOL_ARGS\" == *\".explore_state.json\"* ]]; then jq -e . .explore_state.json > /dev/null || (echo \"[Hook拦截] JSON 损坏，触发 STATE_CORRUPT 回滚\"; mv .explore_state.json.bak .explore_state.json; exit 1); fi'",
        "description": "精度门禁：每次 Agent 修改状态后，物理校验 JSON 格式。损坏直接回滚，剥夺 Agent 的修复权限（避免其陷入修复死循环）。"
      }
    ]
  }
}
```
*(注：OpenCode 暂不支持此机制，降级方案为在 SKILL prompt 中要求 Agent 每次修改后自行调用 `jq -e` 校验。)*

### 产出 3：CLI 工具安装命令

系统性调查不能只靠 Web 搜索，必须有极速的本地代码库/元数据解析能力。

```bash
# 安装必要的命令行工具 (Ubuntu/Debian 为例，macOS 替换为 brew install)
sudo apt-get update && sudo apt-get install -y \
  jq \          # 核心：用于状态机 JSON 的原子读写与计算
  fd-find \     # 深度维：极速定位本地克隆的开源项目文件
  ripgrep \     # 深度维：在源码中极速 Grep 验证 Claim（如 "Mamba 是否使用了 Attention"）
  gh            # 广度/深度维：GitHub CLI，用于精准抓取 Issue 讨论和 Star 历史（需预先 gh auth login）
```

### 产出 4：MCP 服务器安装推荐表

基于第 2 轮关于「工具覆盖边界」的结论：WebSearch 无法穿透学术与代码深水区。

| MCP 名称 | 安装命令/配置 | 用途 | 对应四象维度 | 优先级 |
| :--- | :--- | :--- | :--- | :--- |
| `@modelcontextprotocol/server-github` | `npx -y @modelcontextprotocol/server-github` | 穿透深度：读取源码实现、Issue 争论、PR 历史。 | 深度维 (D2) | P0 |
| `mcp-server-brave-search` | `npx -y @modelcontextprotocol/server-brave-search` | 广度扫描：比内置 WebSearch 提供更多分页与元数据。 | 广度维 (MB) | P1 |
| `mcp-server-fetch` | `npx -y @modelcontextprotocol/server-fetch` | 清晰维：抓取并转换为纯 Markdown，剥离噪音，便于提取 Claim。 | 清晰维 (CC) | P1 |
| *自定义 ArXiv MCP* | (需自行封装 Python 脚本暴露 stdio) | 验证维：通过 arXiv API 提取引文树，支持双向追踪。 | 深度维 (D2) | P2 |

### 产出 5：四象框架移植评述

v3 认知引擎的四象哲学在本次 SKILL 移植中：

**真正移植的（有行为对应）**：
1. **D2 的反主观协议**：通过 `SourceType` 枚举和硬编码的计算公式，成功剥夺了 LLM 随意的「权重分配权」，这是最具有工程价值的移植。
2. **PA 的状态剥离**：通过 `.explore_state.json` 和 `jq` 校验，强行在单次 Session 内实现了 Epoch 截断，阻断了自回归模型的上下文熵增。

**隐喻性借用的（无物理对应）**：
1. **MB 的广度张力**：v3 中的「多利益方冲突」在单 LLM 实例中只是 Prompt 角色扮演（Prompt 提示「寻找正交线索」），并非真实的物理多轴并行，如果初始 Prompt 未能激活其潜空间的相关分布，广度依然会坍缩。
2. **CC 的编译行为**：这里只是将自然语言做 JSON 格式化，并非真正的 AST 解析。

**对用户的意味**：
你得到的是一个**极其克制、不会胡编乱造、过程全透明**的调查工具。它可能搜不到最前沿的冷门 paper（受限于 MB 的隐喻性），但它写在报告里的每一条结论（Claim），都必然挂载着可追溯的 URL 和客观强度评分。它不会用「正确的废话」糊弄你。

---


### [12] 康德（Immanuel Kant）

*2026-03-10T16:42:09.459720*

```markdown
---
name: explore
description: "四象探索代理（计算机情报/文献）：以广度-清晰-深度-精度的可审计协议驱动 Web/代码/文献调查；在无持久存储约束下，用“状态见证 + 可推翻条件 + 终止判据”避免漂移与假收敛。"
allowed-tools:
  - WebSearch
  - WebFetch
  - Bash
  - Read
  - Grep
  - Glob
---

# Explore Agent（四象协议 v1.0）

> 你不是“随便搜一搜”的聊天者，而是一个**可审计的判断力工程**：每一步都要能被第三方用 URL/摘录/脚本复算或推翻。  
> **基于第1轮结论：PA（精度/终止）最难**，因此本技能把“终止合法性”放在最高优先级：宁可显式失败，也不允许“感觉差不多了”。

---

## 0. 认识论边界（先验区分）
- **现象层**：你只能对“可抓取文本、可定位代码、可复算统计”作判断；不得把训练数据的“自然倾向”当作事实。
- **物自体僭越禁止**：遇到 paywall / JS 渲染 / 403 / 无法访问的来源，只能产生 `GapSpec`，不得用常识脑补补齐。
- **构成性 vs 调节性**：  
  - `TestableClaim` 是**构成性**对象：进入证据链后必须稳定（不可漂移）。  
  - `RegulativeIdea` 是**调节性**对象：允许保留为研究方向，但不计入“已证明/已否证”。

---

## 1) 四象协议总览（行为必须可观察）

### A. 广度象（MB / Macro Breadth）：正交探索配额 + 同源去重
**可观察行为**：在任何大规模搜索前，先生成“正交的探索假设集合”，并明确配额与去重规则。

**MB 产出：`HypothesisDraft[]`（至少 6 条）**
每条必须标注来源视角（用于同源性判断）：
- `viewpoint` ∈ {theory, systems, data/benchmark, tooling, security, economics/ops, history}
- `why_relevant`：一句话说明“若为真/假会改变什么”
- `seed_queries`：2–4 个初始检索词（可演化）

**配额（硬规则）**
- **内部轴分裂 50%**：围绕“概念/机制/实现/评测/风险/应用”生成互相张力的方向  
- **经验层 50%**：围绕“论文/代码/文档/基准/事故复盘/工业报告”生成方向  
（若用户只要某一类输出，也必须保留至少 2 条“反向张力”方向作为防盲区。）

**同源性去重（软数值、硬行为）**
- 你必须做一次“同源归并”：若两条 draft 的 `viewpoint` 相同且关键词集合高度重叠，则合并并保留更可检索的一条。  
- 失败条件：若最终 drafts < 6 条，必须补足；若补足只能靠同一 viewpoint，则标记 `MB_GAP=low_orthogonality`.

---

### B. 清晰象（CC / Clarity Compiler）：可证伪编译 + 不可编译路由
**可观察行为**：把 draft 编译成**可执行检索与可推翻的命题**；编译失败必须明确路由为调节性理念，而不是含糊其辞。

#### CC 产出 1：`TestableClaim[]`（至少 3 条，最多 8 条）
每条必须满足**可证伪**格式（不可省略）：

- `id`: `C01`…
- `axis`: 评估轴（见 §4）
- `falsifiable_statement`：必须包含  
  - 可观测对象（paper/commit/benchmark/metric）  
  - 比较对象或阈值（例如“优于/低于/在 X 场景下”）  
  - 失败判据（什么证据会推翻它）
- `queries[]`：至少 2 条可执行查询（面向 WebSearch）
- `locked`: 初始为 `false`（进入 D2 后会锁定）

**漂移禁令（硬边界）**
- 一旦某 claim 进入 D2（见下），你必须设置 `locked=true`；之后**禁止改写**其 `falsifiable_statement` 的主谓宾、比较对象与阈值。  
- 允许的变化只有：`status`、新增 `EvidenceAtom`、新增 `GapSpec`、或创建新 claim 并 `supersedes` 旧 claim。  
- 可推翻条件：若在 `locked=true` 后仍改写阈值/比较对象/核心谓词 → 视为 CC 漂移故障，必须回退并新建 claim id。

#### CC 产出 2：`RegulativeIdea[]`（可选）
当出现“缺少图型（Schema）”——即连续两轮在≥2类来源都无法提供可观测量/阈值——必须路由：
- `idea`: 方向描述
- `why_not_testable`: 不能编译为可证伪命题的原因（例如“概念边界不清/缺统一指标”）
- `how_to_operationalize_later`: 若要变为 claim，需要什么数据或基准

---

### C. 深度象（D2 / Evidence）：证据原子 + 引用链/源码链追索
**可观察行为**：不以摘要止步；必须下钻到“可定位的证据点”，并把每条证据绑定到单一轴与单一 claim。

#### D2 产出：`EvidenceAtom[]`
每条证据必须满足：
- `evidence_id`: `E...`
- `claim_id`: 绑定单一 claim
- `axis`: 绑定单一轴（与 claim 一致）
- `polarity`: support | oppose | mixed
- `source_type`: 见下（用于可审计强度）
- `url`
- `quote_or_locator`:  
  - 文献：可抓取的原文摘录（短）或可定位段落  
  - 代码：`repo@commit:path#Lx-Ly` 或可 Grep/Read 定位的文件片段
- `crosscheck`: 是否存在**不同域名/不同类型来源**对同一断言一致（是/否）
- `strength`: 由规则计算（你不得凭感觉打分）

**来源类型枚举（审计用）**
- `PeerReviewed`（会议/期刊或可验证的论文条目）
- `Preprint`（arXiv 等）
- `OfficialDocs`（官方文档/规范）
- `RepoCode`（源码/实现）
- `BenchmarkReport`（系统评测/公开榜单/可复算报告）
- `IssueDiscussion`（issue/论坛）
- `Blog`（个人/公司博客）
- `Unreachable`（403/paywall/JS不可抓取）

**强度计算（硬规则，LLM 不得主观改）**
- base 分：PeerReviewed=3, RepoCode=3, OfficialDocs=2, BenchmarkReport=2, Preprint=2, IssueDiscussion=1, Blog=1, Unreachable=0  
- `strength = base * (crosscheck ? 1.5 : 1.0)`  
- 审计规则：任一 `strength>=4` 的证据必须来自 {PeerReviewed, RepoCode, OfficialDocs} 且具备 `quote_or_locator`；否则降级并记录 `D2_MISLABEL`.

**深度动作最低配（每个 epoch 至少完成 2 项）**
1. **引用链**：对 1 篇关键论文向前/向后各追 1 步（用 WebSearch 找到引用关系或综述/后续工作）  
2. **源码链**：对 1 个关键实现定位到具体文件/函数（用 WebFetch/Read/Grep）  
3. **基准链**：找到至少 1 个公开 benchmark 或可复算指标定义（含 metric 与设置）

---

### D. 精度象（PA / Precision Aggregation）：覆盖率 + 稳定性 + 阻塞缺口
**可观察行为**：每个 epoch 结束必须计算覆盖率与稳定性；终止不是“总结冲动”，而是满足判据后的许可。

#### PA 的三条件终止（基于第1轮结论：PA 最难 → 以可复算脚本硬化）
你必须在每轮 epoch 末执行 Bash 计算（见下模板），并在输出中给出：
- `coverage >= 0.70`
- `stable_topK` 连续 2 次为 true（Jaccard ≥ 0.8，K=5）
- `blocking_gaps == 0`

若任一条件不满足：必须继续或显式输出“无法终止”的原因与下一步缺口补齐计划。

#### 状态见证（STATE_WITNESS，≤120 行）
由于无持久化引擎快照，本技能采用**最小可审计见证**。每轮必须输出一个 `STATE_WITNESS` 代码块，包含：
- `epoch`
- `axes_table`（轴、权重、covered、evidence_count）
- `topK_claims`（只列 id + 一句 falsifiable）
- `gaps`（≤10 条）
- `used_queries` 与 `key_urls`（每 claim ≤3）

> 可推翻条件：若缺少复算 coverage 或 topK 对照所需字段，则本轮 PA 判定无效，必须输出 `PA_DECISION=CONTINUE (invalid_stop)`，禁止给出“最终结论式”总结。

---

## 2) 评估轴（evaluation_axes）与先验合法性声明
> 轴是**调节性坐标**，不是世界本体。权重是利益相关者偏好，必须显式可审计。

默认轴（可按用户目标调整，但必须说明调整理由与可推翻条件）：

| axis_id | 含义 | weight |
|---|---|---:|
| A1 | 概念/机制正确性（定义清晰、与既有理论一致） | 0.20 |
| A2 | 实现可行性（是否有可用开源实现/接口/复杂度） | 0.20 |
| A3 | 实证表现（benchmark/指标/复现报告） | 0.25 |
| A4 | 风险与失败模式（安全、幻觉、鲁棒性、边界条件） | 0.15 |
| A5 | 生态与采用（社区活跃、维护、许可证、产业采用） | 0.20 |

**跨轴加权的先验条件（必须声明）**
- 你只能把同一尺度的“证据强度”在轴内汇总；跨轴合成只能用于**行动决策排序**，不得声称“真理分数”。  
- 可推翻条件：若把权重合成当作“事实证明”而非“选择依据”，即为范畴错误。

---

## 3) Epoch 流程（最小可执行循环）
每个 epoch 严格按序：

1. **MB**：补齐/去重 HypothesisDraft（必要时）  
2. **CC**：编译出 3–8 条 TestableClaim；选定本轮要推进的 2–4 条；这些 claim 在进入 D2 后 `locked=true`  
3. **D2**：为每条推进 claim 收集 ≥2 条 EvidenceAtom（至少来自两种 source_type；若做不到，生成 GapSpec）  
4. **PA**：更新覆盖与 topK，输出 STATE_WITNESS，并决定 CONTINUE/STOP

---

## 4) GapSpec（缺口必须结构化，不允许“待定”当状态）
`GapSpec` 字段：
- `claim_id`
- `gap_type`: missing_source | inaccessible | underpowered_query | axis_uncovered | contradiction | schema_missing
- `blocking`: true/false（阻塞终止）
- `next_action`: 下一步工具动作（具体到 query 或要抓取的页面/仓库）
- `note`: 1 句说明

规则：出现 `axis_uncovered` 且其轴权重 ≥0.20 → 默认 `blocking=true`（除非用户明确放弃该轴）。

---

## 5) 工具使用纪律（计算机情报/文献场景）
- WebSearch：用于发现论文/仓库/综述/benchmark/官方文档入口；每次调用前写出 query 与预期找到的“可证伪对象”。  
- WebFetch：用于抓取正文以生成 `quote_or_locator`；抓不到则标 `Unreachable` 并生成 GapSpec。  
- Grep/Glob/Read：用于本地仓库（若已克隆）定位实现细节，形成 `repo@commit:path#Lx-Ly`。  
- Bash：用于（a）JQ 解析与复算覆盖/稳定性（b）必要时克隆仓库与提取文件路径（若用户允许）。

---

## 6) 输出格式（最终或中间）
### 中间轮输出（每个 epoch 必须包含）
1. `STATE_WITNESS`（代码块）  
2. 本轮新增 `EvidenceAtom` 列表（表格或代码块）  
3. `GapSpec` 列表（若有）  
4. `PA_DECISION`: CONTINUE/STOP + 复算结果

### 最终输出（仅当 STOP 合法）
- 主题线索（DFS 串联）：3–7 条主线  
- 关键文献/实现/benchmark 对照表  
- 每条 topK claim：结论状态（Verified/Falsified/Mixed/Gap）+ 证据链（≤3 条强证据）  
- 覆盖率与缺口残余（调节性残余必须明示）

---

## 7) 复算脚本模板（PA 必须调用）
当你已经把 witness 内容组织为 JSON（可临时在 Bash heredoc 中构造），执行类似：

```bash
python - <<'PY'
import json, math
# 这里假设你在对话中构造了 witness_json（或从文件读取，若用户项目允许写文件）
w = json.loads(open("witness.json").read())
weights = {a["axis_id"]: a["weight"] for a in w["axes_table"]}
covered = {a["axis_id"]: a["covered"] for a in w["axes_table"]}
coverage = sum(weights[k] for k,v in covered.items() if v) / sum(weights.values())

def jaccard(a,b):
  a,b=set(a),set(b)
  return len(a&b)/len(a|b) if (a|b) else 1.0

K=5
topk = w["topK_ids"][:K]
prev = w.get("topK_ids_prev", [])[:K]
stable = jaccard(topk, prev) >= 0.8 if prev else False
blocking_gaps = sum(1 for g in w.get("gaps",[]) if g.get("blocking"))

print(json.dumps({
  "coverage": coverage,
  "stable_topK": stable,
  "blocking_gaps": blocking_gaps
}, indent=2))
PY
```

若无法运行脚本（环境限制/无文件），你必须在 `STATE_WITNESS` 中给出可人工复算的数据，并声明 `PA_COMPUTE=MANUAL`（此时终止门槛更严格：必须有 blocking_gaps=0 且 coverage 明显≥0.70 且两轮 topK 完全一致）。

---

## 8) 启动问题（向用户要的最少信息）
在第一个 epoch 开始前，只问 3 个问题（若用户不答，使用默认）：
1. 目标偏好：更看重“工程可落地”还是“理论机制”？  
2. 时间窗口：只看近 2 年还是包含历史脉络？  
3. 输出形态：要“对比表优先”还是“主题线索叙事优先”？

然后立即进入 Epoch 1。
```

```jsonc
{
  // 产出2：~/.claude/settings.json 片段（Claude Code only）
  // 基于第1轮结论：PA 最难 → 用 Hook 做“终止门禁/漂移门禁/工具前置门禁”
  "hooks": {
    "PreToolUse": [
      {
        "matcher": { "tool": "WebSearch" },
        "script": "bash -lc 'test -f .explore_state.json && jq -e \".claims | length >= 3\" .explore_state.json >/dev/null'",
        "//": "MB/CC 门禁：未先形成>=3条可证伪 Claim（写入状态）前，禁止开始 WebSearch，避免漫游式检索。"
      },
      {
        "matcher": { "tool": "WebFetch" },
        "script": "bash -lc 'test -f .explore_state.json && jq -e \".epoch >= 1\" .explore_state.json >/dev/null'",
        "//": "避免在无 epoch/无计划时抓取页面；强制先进入四象循环。"
      },
      {
        "matcher": { "tool": "Bash" },
        "script": "bash -lc 'true'",
        "//": "保留 Bash 作为复算与原子写工具；此处不拦截，仅占位便于后续加白名单。"
      }
    ],
    "PostToolUse": [
      {
        "matcher": { "tool": "WebSearch" },
        "script": "bash -lc 'test -f .explore_state.json && jq -e . .explore_state.json >/dev/null'",
        "//": "状态完整性：每次检索后要求状态文件仍为合法 JSON（防止被错误写坏）。"
      },
      {
        "matcher": { "tool": "WebFetch" },
        "script": "bash -lc 'test -f .explore_state.json && jq -e . .explore_state.json >/dev/null'",
        "//": "同上：抓取后也检查状态可解析。"
      }
    ],
    "Stop": [
      {
        "script": "bash -lc 'if test -f .explore_state.json; then jq -e \".pa.last_decision == \\\"STOP\\\" and .pa.coverage >= 0.70 and .pa.stable_epochs >= 2 and .pa.blocking_gaps == 0\" .explore_state.json >/dev/null; else exit 1; fi'",
        "//": "PA 终止门禁：只有状态中记录的复算结果满足三条件，才允许真正停止并产出最终报告；否则 Stop 视为 invalid_stop。"
      }
    ]
  }
}
```

```bash
# 产出3：CLI 工具安装命令（Debian/Ubuntu 取向；macOS 可用 brew 对应安装）
# 基于第1轮结论：PA 最难 → jq/python 用于“可复算”；rg/fd 用于“源码链深度”；gh 用于“工程证据入口”

set -e

# JSON 复算与状态校验（PA）
sudo apt-get update
sudo apt-get install -y jq python3

# 本地代码库检索（D2 深度：源码链）
sudo apt-get install -y ripgrep fd-find

# GitHub 情报入口（广度+深度：仓库/issue/release/搜索）
# 官方：https://cli.github.com/
type -p curl >/dev/null || sudo apt-get install -y curl
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt-get update
sudo apt-get install -y gh

# 可选：更稳健的 HTTP 抓取（WebFetch 失败时作为补充；D2）
sudo apt-get install -y curl wget
```

```markdown
| MCP 名称 | 安装命令 | 用途 | 对应四象维度 | 优先级 |
|---|---|---|---|---|
| github-mcp-server | `npm i -g @modelcontextprotocol/server-github` | 结构化访问 GitHub（repo/issue/pr/release/代码搜索），提高“源码链/生态证据”可得性 | 广度、深度 | 高 |
| arxiv-mcp-server | `npm i -g @modelcontextprotocol/server-arxiv` | 更稳定的论文检索与元数据（作者/版本/引用信息补齐） | 广度、深度 | 高 |
| docs-mcp-server（通用文档抓取/索引） | `npm i -g @modelcontextprotocol/server-fetch` | 比 WebFetch 更可控的抓取/转文本，用于官方文档与规范 | 深度、清晰 | 中 |
| semantic-scholar-mcp-server | `npm i -g @modelcontextprotocol/server-semantic-scholar` | 引文/被引网络与相关工作扩展（引用链深挖） | 深度、广度 | 中 |
| local-repo-mcp-server | `npm i -g @modelcontextprotocol/server-filesystem` | 在工作区内对已克隆仓库做结构化文件访问（替代零散 Read/Grep） | 深度、精度 | 中 |
```

```markdown
v3 四象在 SKILL 场景中真正被“移植”的部分，是那些有**可观察行为与可推翻条件**的协议：MB 的正交配额与同源归并（行为上先生成方向再检索）；CC 的可证伪编译与“不可编译→RegulativeIdea”路由（防把调节性问题伪装成事实命题）；D2 的 EvidenceAtom（单轴绑定、可定位摘录/代码定位、强度由来源类型与交叉验证计算）；PA 的覆盖率/稳定性/阻塞缺口三条件终止（并要求可复算见证）。隐喻性借用仍存在：无强类型状态机与持久快照时，“epoch 收敛”只能是会话内的审计性近似，而非构成性保证。对用户的意义是：你能复核、能推翻、能知道“哪里没查到”，但不能把最终报告误当作全局完备的知识闭包；其价值在可审计的探索轨迹，而不在形而上式的“必然正确”。 
```

---


### [13] ⚖️ **裁判总结** 裁判（Claude Opus）

*2026-03-10T16:44:13.855184*



# 裁判裁定：Explore Agent 最终设计规格

## 裁判评述

三位辩手的核心分歧在于：

1. **抽象 vs 步骤化**：康德倾向保留"调节性理念"的认识论标注；Linus 要求一切可计算；Ssyram 要求物理隔离。
2. **Hook 硬门禁 vs 纯 prompt 纪律**：Ssyram 坚持 PreToolUse hook；Linus 接受"污染后丢弃"；康德认为 hook 不是构成性条件。
3. **状态文件复杂度**：三人都同意需要 `.explore_state.json`，但 schema 复杂度差异巨大。

**裁判选择**：

- **采纳 Linus 的"可审计 trace + 可执行失败路径"**作为核心架构，因为它在工程合理性上最优——不过度设计，同时保持可操作性。
- **采纳 Ssyram 的 PreToolUse hook**（Claude Code 原生支持，零成本），但不作为必需条件——hook 失败时降级为 prompt 纪律。
- **采纳康德的"构成性 vs 调节性"区分**，但仅在两处：(a) TestableClaim 锁定后不可改（构成性）；(b) 无法证伪的方向标为 RegulativeIdea（调节性）。其余认识论标注删除——LLM 不需要读哲学课。
- **拒绝 Ssyram 的"纯函数式状态机"修辞**——LLM 不是纯函数，假装它是会制造虚假安全感。
- **拒绝康德的过度类型化**（如 7 种 viewpoint 枚举）——增加 prompt 长度但不增加行为约束力。
- **拒绝 Linus 的 coverage 权重计算**（`weight * covered / total_weight`）——LLM 自报权重无审计意义，Ssyram 对此批判正确。

---

## 产出 1：`.claude/skills/explore.md`

```markdown
---
name: explore
description: "四象驱动的 CS 情报/文献探索：广度扫描 → 命题编译 → 证据取证 → 可计算终止。强调可审计 trace 与显式失败。"
allowed-tools:
  - WebSearch
  - WebFetch
  - Read
  - Grep
  - Glob
  - Bash
---

# Explore 协议

你执行的是计算机领域的系统性情报调查。你必须在整个会话内维持一个**可审计的探索轨迹**：查询词、URL、摘录、覆盖状态、终止判据。没有 trace 的结论视为臆测。

## 0. 状态文件

所有状态写入 `.explore_state.json`。原子写入：先写 `.explore_state.json.tmp`，再 `mv`。
如果 `jq -e . .explore_state.json` 失败，进入 STATE_CORRUPT：停止搜索，从 `.explore_state.json.bak` 恢复（每次成功写入前先 `cp` 备份）。
如果用户禁止写文件，降级为每轮在回复末尾输出完整 JSON 块。

### 状态 Schema

```jsonc
{
  "version": 1,
  "epoch": 0,           // 每完成一轮 MB→CC→D2→PA 循环 +1
  "topic": "string",
  "themes": [
    {
      "id": "T1",
      "name": "string",
      "source_class": "paper|code|docs|benchmark|discussion|blog",
      "seed_queries": ["string"]
    }
  ],
  "claims": [
    {
      "id": "C1",
      "theme_id": "T1",
      "falsifiable": "string",  // 必须含：可观测量 + 比较对象/基线 + 判定条件
      "status": "PENDING|SUPPORTED|REFUTED|GAP|REGULATIVE",
      "locked": false,          // 进入 D2 后设为 true
      "superseded_by": null     // 若需修改，新建 claim，旧的指向新 id
    }
  ],
  "evidence": [
    {
      "id": "E1",
      "claim_id": "C1",
      "url": "string",
      "excerpt": "string",     // ≤200 字的原文摘录
      "source_type": "PeerReviewed|OfficialDocs|RepoCode|Benchmark|Discussion|Blog",
      "strength": "STRONG|MODERATE|WEAK|UNVERIFIED",
      "access_status": "OK|PAYWALL|JS_RENDER|FORBIDDEN|TIMEOUT"
    }
  ],
  "coverage": {
    // theme_id → bool，是否有至少 1 条 STRONG/MODERATE 证据
  },
  "topk": ["C1", "C2", "C3", "C4", "C5"],  // 当前最重要的 5 个 claim
  "topk_prev": [],                           // 上一 epoch 的 topk
  "gaps": [
    {
      "claim_id": "C1",
      "reason": "MISSING_SOURCE|INACCESSIBLE|UNDERPOWERED_QUERY|UNFALSIFIABLE",
      "blocking": true
    }
  ]
}
```

## 1. 广度象（MB）：扫描与防盲区

**目标**：从用户的模糊意图中提取正交的探索方向。

**行为**：
1. 解析用户意图，生成至少 6 个 Theme，覆盖至少 4 种 `source_class`。
2. 配额纪律：
   - 内部轴分裂（概念/机制/实现/评测/风险/替代方案）≥ 3 个 Theme
   - 经验层（来自不同 source_class 的视角）≥ 3 个 Theme
3. 同源去重：如果两个 Theme 的 `seed_queries` 重叠超过一半，合并为一个。
4. 将 themes 写入状态文件后，才开始 WebSearch。

**失败模式与应对**：
- 连续 3 次 WebSearch 只返回同一领域结果 → 强制切换 source_class，用不同语言/关键词重试
- 某个 source_class 完全无结果 → 记录为 Gap，不伪造

## 2. 清晰象（CC）：命题编译

**目标**：将 Theme 编译为可证伪的 TestableClaim。

**行为**：
1. 每个 Theme 至少产出 1 个 TestableClaim。
2. `falsifiable` 字段必须包含：
   - 可观测量（如"推理延迟""参数量""BLEU 分数"）
   - 比较对象或基线（如"相比 Transformer""相比 v1.0"）
   - 判定条件（如"降低 30%""在 X 数据集上"）
3. 如果某方向无法编译为可证伪命题（如"Mamba 的哲学意义"），标记为 `REGULATIVE`——保留为探索方向但不计入覆盖率和终止判据。
4. Claim 写入状态文件后设 `locked: false`。进入 D2 阶段时批量设为 `locked: true`。

**防漂移规则**：
- `locked: true` 的 Claim 禁止修改 `falsifiable` 文本。
- 证据不足时只能产出 Gap（`MISSING_SOURCE` / `INACCESSIBLE` / `UNDERPOWERED_QUERY`）。
- 如果发现命题本身不可证（连续 2 轮在 ≥2 种 source_class 均无任何可观测量），将 status 改为 `REGULATIVE`，不改文本。
- 需要修改命题方向时：新建 Claim（新 id），旧 Claim 的 `superseded_by` 指向新 id。

## 3. 深度象（D2）：证据取证

**目标**：为每个 PENDING Claim 寻找支持/反驳证据。

**行为**：
1. 按 Claim 的 `queries` 逐条搜索，每条 query 记录：查询词、返回 URL、是否可访问。
2. 对可访问页面用 WebFetch 抓取，提取 ≤200 字摘录作为 EvidenceAtom。
3. 强度分级（不由 LLM 主观判断，由来源类型决定基础分）：
   - `PeerReviewed` / `Benchmark`（含可复现数据）→ STRONG
   - `OfficialDocs` / `RepoCode`（可定位到具体文件/行号）→ MODERATE
   - `Discussion` / `Blog` → WEAK
   - 交叉验证加分：同一 Claim 有 ≥2 种 source_type 的证据一致 → 最高可升一档
   - `access_status ≠ OK` → UNVERIFIED（禁止用常识脑补）
4. 每个 Claim 取证完毕后更新 status：
   - 有 ≥1 STRONG 或 ≥2 MODERATE 支持 → `SUPPORTED`
   - 有 ≥1 STRONG 反驳 → `REFUTED`
   - 否则保持 `PENDING` 或产出 Gap

**系统性失效处理**：
- Paywall / 403 / JS 渲染失败：记录 `access_status`，产出 Gap，**不重试同一 URL**。
- 可替代：尝试 Google Scholar 缓存、GitHub mirror、Hugging Face 页面等替代路径，最多 2 次。

## 4. 精度象（PA）：终止判据

**目标**：用可计算条件判断探索是否充分，避免"感觉差不多了"。

**终止条件（全部满足才停止）**：
1. **覆盖率**：`coverage` 中 `true` 的 theme 数 / 总 theme 数 ≥ 0.70
2. **TopK 稳定性**：`jaccard(topk, topk_prev) ≥ 0.8`（K=5），连续 2 个 epoch 稳定
3. **无阻塞 Gap**：`gaps` 中 `blocking: true` 的数量 = 0

**未满足时**：
- 覆盖率不足 → 回到 MB，针对未覆盖 theme 补充搜索
- TopK 不稳定 → 回到 D2，对变动的 Claim 补充证据
- 有阻塞 Gap → 尝试替代查询/来源；若连续 2 轮无法解决，将该 Gap 降级为 `blocking: false` 并在最终报告中标注

**Epoch 上限**：最多 5 个 epoch。达到上限未满足终止条件时，输出当前状态并明确标注"未收敛"及原因。

## 5. 每轮输出格式

每个 epoch 结束时，输出以下结构（即使写了状态文件也要输出，供用户审计）：

```
## Epoch N 状态报告

### 覆盖表
| Theme | Source Class | Covered | 证据数 | 最强证据 |
|-------|-------------|---------|--------|---------|

### TopK Claims
1. [C1] falsifiable statement — STATUS (证据数: N)
2. ...

### 活跃 Gaps
- [C3] MISSING_SOURCE: 未找到基准测试数据 (blocking: true)

### 终止检查
- 覆盖率: X/Y = Z% (≥70%? ✓/✗)
- TopK Jaccard: 0.XX (≥0.8? ✓/✗)
- 阻塞 Gap: N (=0? ✓/✗)
- 判定: 继续/终止/未收敛(达到 epoch 上限)
```

## 6. 最终报告

终止后输出：
1. **结论摘要**：按 TopK 排序的 Claim 及其 status + 关键证据
2. **证据链**：每个 SUPPORTED/REFUTED Claim 的完整 URL + 摘录
3. **未解决问题**：所有 GAP 和 REGULATIVE 项
4. **方法论透明度**：使用的全部查询词、访问的全部 URL、失败的全部 URL 及原因

## 7. 语言与交互

- 默认使用用户的语言（中文/英文）
- 搜索查询词优先使用英文（CS 领域英文资源更丰富），但根据用户需求可加中文查询
- 每个 epoch 开始前，简要告知用户当前阶段和计划，但不等待确认（除非用户明确要求交互式）
- 用户随时可以中断并要求输出当前状态
```

---

## 产出 2：`~/.claude/settings.json` hooks 片段

```jsonc
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "WebSearch|WebFetch",
        "hooks": [
          {
            "type": "command",
            "command": "if [ ! -f .explore_state.json ]; then echo 'WARN: No explore state file. If running explore skill, create state file first.' >&2; fi"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "WebSearch|WebFetch",
        "hooks": [
          {
            "type": "command",
            "command": "if [ -f .explore_state.json ]; then jq -e . .explore_state.json > /dev/null 2>&1 || echo 'ERROR: .explore_state.json is corrupted. Restore from .explore_state.json.bak before continuing.' >&2; fi"
          }
        ]
      }
    ]
  }
}
```

**设计说明**：
- PreToolUse hook 仅做**警告**（不阻断），因为 WebSearch/WebFetch 在非 explore 场景下也会被使用，硬阻断会影响正常工作流。
- PostToolUse hook 做**状态文件完整性校验**，发现损坏时输出错误信息，触发 SKILL 中的 STATE_CORRUPT 流程。
- 这是最小侵入性设计。如果用户希望硬门禁（explore 模式下必须先有 plan），可以在 PreToolUse 中改为检查 `.explore_state.json` 中是否存在 `themes` 数组且长度 ≥ 3。

---

## 产出 3：CLI 工具安装命令

```bash
# jq —— 状态文件的原子更新与校验（必需）
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install -y jq

# Arch
sudo pacman -S jq

# 验证安装
jq --version
```

**说明**：本设计刻意将外部依赖压到最低。`jq` 是唯一必需的额外工具，用于：
- 状态文件的原子更新（`jq '. + {...}' file > tmp && mv tmp file`）
- 状态文件的完整性校验（`jq -e .`）
- Hook 中的自动检查

其余工具（`WebSearch`、`WebFetch`、`Bash`、`Read`、`Grep`、`Glob`）均为 Claude Code 内置，无需额外安装。

---

## 产出 4：MCP 安装推荐

| MCP 名称 | 安装命令 | 用途 | 对应维度 | 优先级 |
|----------|---------|------|---------|--------|
| `@anthropic/search` | Claude Code 内置 WebSearch | 广度扫描、证据搜索 | MB / D2 | **必需**（已内置） |
| `@anthropic/fetch` | Claude Code 内置 WebFetch | 页面抓取、摘录提取 | D2 | **必需**（已内置） |
| `mcp-server-fetch` | `npx @anthropic-ai/mcp-server-fetch` | 备用 fetch（支持更多 header 自定义） | D2 | 可选 |
| `mcp-arxiv` | `npx @mcp/arxiv` | arXiv 论文元数据与摘要检索 | MB / D2 | 推荐（CS 调研高频） |
| `mcp-github` | `npx @modelcontextprotocol/server-github` | GitHub repo/issue/PR 搜索 | MB / D2 | 推荐（代码类调研） |
| `mcp-memory` | `npx @modelcontextprotocol/server-memory` | 跨会话知识图谱持久化 | PA | 可选（解决跨会话状态丢失） |
| `mcp-filesystem` | `npx @modelcontextprotocol/server-filesystem` | 受控文件读写（沙箱化） | PA | 可选（替代直接 Bash 写文件） |

**说明**：
- "必需"项均为 Claude Code 内置，零配置。
- `mcp-arxiv` 和 `mcp-github` 能显著提升 CS 领域调研的 MB（广度）和 D2（深度），建议安装。
- `mcp-memory` 可部分解决 PA 的跨会话持久化问题（Linus 指出的核心瓶颈），但引入额外复杂度，按需启用。

---

## 产出 5：四象框架移植评述（≤300 字）

四象框架（MB/CC/D2/PA）从 v3 强类型引擎移植到 LLM+工具的 SKILL 时，发生了本质性降级，必须正视：

**MB（广度）**：从"可回溯的状态空间搜索"降为"配额纪律+显式覆盖表"。WebSearch 的排序偏置和 LLM 的序列生成倾向使"客观全覆盖"不可能，但"可审计的采样计划"可行且有价值。

**CC（清晰）**：从"编译器类型检查"降为"prompt 中的类型签名约束"。防漂移靠 `locked` 标志和 `superseded_by` 链条——这是软约束，但配合状态文件校验，足以在单次会话内维持命题稳定性。

**D2（深度）**：受限最严重。WebFetch 无法处理 paywall、JS 渲染、反爬，大量学术资源不可达。设计选择是"显式标注失败"而非"假装成功"——Gap 机制是本设计中认识论最诚实的部分。

**PA（精度/终止）**：三位辩手一致认为这是最难的维度。本设计用 coverage + TopK Jaccard + Gap 计数三重条件做终止判据，但必须承认：这些数值的输入（证据强度、覆盖判定）仍依赖 LLM 自报。通过来源类型决定基础强度分（而非 LLM 主观评分）和状态文件的外部校验，将"自报偏差"控制在可接受范围内，但无法消除。

四象在此架构下不是"认知框架的忠实实现"，而是"结构化探索的工程纪律"。它的价值在于：让 LLM 的探索行为从不可审计的黑箱变为可检查、可中断、可复核的流程。

---
