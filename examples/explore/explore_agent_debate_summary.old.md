# 四象探索代理：计算机情报 SKILL 设计 裁判总结

> 2026-03-10T16:44:13.856810



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