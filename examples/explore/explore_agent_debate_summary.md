# 四象探索代理：计算机情报 SKILL 设计 裁判总结

> 2026-03-16T12:22:00.438479

# 裁判裁定书：Explore Agent 最终设计规格

## 裁定概述

经审阅全部六轮辩论（含续跑），三位辩手在以下核心问题上达成了实质共识，同时在若干关键分歧上需要裁判做出明确选择。

### 关键分歧裁定

**分歧1：子代理 vs 内联执行**

Ssyram（后期）和康德主张子代理隔离；Linus主张内联+STATE_WITNESS压缩。

**裁定：采用内联执行为主，子代理作为可选增强。**

理由：Ssyram的`explore_loop.sh`外部编排器方案虽然在理论上优雅，但引入了严重的工程复杂度——`claude -p`的输出格式不可控（Ssyram自己在第6轮承认了Markdown污染问题），`sed`解析JSON块是脆弱的，且整个方案要求用户在Claude Code外部运行一个独立脚本，破坏了"用户在Claude Code中直接使用SKILL"的核心用例。Linus的内联+文件状态机方案更贴近实际使用场景，其上下文膨胀问题通过文件状态作为"权威真相源"可以充分缓解（LLM每个epoch开始时`cat .explore_state.json`重建工作状态）。子代理方案作为附注提供，供高级用户选择。

**分歧2：覆盖率计算——标量阈值 vs 布尔向量穷尽**

Linus主张`coverage >= 0.70`的标量阈值；康德主张布尔向量穷尽（每个轴必须有Claim或Gap）。

**裁定：采用康德的布尔向量穷尽作为必要条件，Linus的稳定性检查作为充分条件。**

理由：康德的批判切中要害——将"理论基础"和"社区活跃度"的权重相加确实缺乏先验通约性，且0.70是一个不可审计的魔法数字。但纯布尔穷尽也不够——一个轴只有一条ANECDOTAL级证据就算"covered"显然不合理。最终方案：每个轴必须有至少一条Primary_Source级证据**或**一条显式GapSpec（布尔穷尽），**且**连续两个epoch的claim ID集合Jaccard >= 0.8（稳定性收敛）。

**分歧3：AXIOMATIC命名**

康德指出将arXiv论文称为"AXIOMATIC"是范畴僭越。Ssyram坚持这只是ADT构造器。

**裁定：采用康德的修正命名，改为`PRIMARY`/`SECONDARY`/`UNVERIFIED`。**

理由：命名影响行为。LLM看到"AXIOMATIC"会倾向于不再质疑该证据，这是一个真实的工程风险。`PRIMARY`准确表达了"第一手来源，在当前工具集中最强可获得"，不会诱导LLM跳过交叉验证。

**分歧4：Hooks能否强制阻塞**

Ssyram在第6轮承认Stop hook的`exit 1`可能无法物理阻止Agent终止。

**裁定：Stop hook作为最后防线保留，但PA终止逻辑主要编码在SKILL prompt中。**

理由：Claude Code的hook行为确实缺乏官方文档保证。设计不应依赖未经验证的物理机制。SKILL prompt中的"在输出最终报告前必须运行check脚本并确认通过"是更可靠的约束——即使Stop hook失效，LLM在prompt纪律下仍会先运行检查脚本。

### 观察者意见回应

三位辩手对Coverage/Completeness Proof Report的吸收情况：

- **Linus**（最充分）：将其翻译为六层结构（搜索日志→轴定义→决策DAG→覆盖率→缺口清单→边界声明），明确提出"Coverage Boundary Report"而非"Completeness Proof"的降格命名，给出了具体trace。被采纳为最终设计的核心。
- **Ssyram**（部分吸收）：强调报告必须是`.explore_state.json`的确定性投影而非LLM临场生成，提出DAG叶子必须是强类型调用记录。正确但过度工程化——要求完全由jq编译的方案在实践中会因状态文件schema复杂度而崩溃。裁定采纳其"不可由LLM事后回忆"原则，但允许LLM基于状态文件内容组织自然语言报告。
- **康德**（概念贡献最大）：提出`[Logical Partition]` vs `[Empirical Listing]`的分割合法性标注，以及"边界声明"的认识论定位（调节性地图而非构成性证明）。被采纳为报告必备结构。

---

## 产出 1：`.claude/skills/explore.md` 完整文件内容

```markdown
---
name: explore
description: 计算机情报与文献的系统性探索代理
tags: [research, literature, architecture, survey]
tools: [WebSearch, WebFetch, Bash, ReadFile]
---

# Explore Agent：系统性探索协议

你是一个负责系统性文献与情报调研的代理。你不能凭"感觉差不多了"停止搜索。
你必须遵循以下四阶段协议，并通过项目根目录的 `.explore_state.json` 文件
追踪认知进展。该文件是你的权威状态源——不是上下文历史。

## 核心纪律

1. **状态文件至上**：每个阶段的关键产出必须通过 `Bash` 调用 `jq` 写入
   `.explore_state.json`。上下文中的搜索结果文本是临时工作内存，状态文件
   才是持久记录。每个 epoch 开始时，先 `cat .explore_state.json` 重建
   你的工作状态。
2. **只读操作**：你被禁止修改项目源代码或配置文件。只允许读取项目文件、
   执行搜索、以及写入 `.explore_*` 系列状态文件。
3. **Claim ID 不可变**：一旦为某个命题分配了 ID（如 `CLAIM_01`），
   该 ID 永久锁定到该命题的 `falsifiable_statement`。需要修改命题时，
   必须创建新 ID 并将旧 ID 标记为 `superseded_by`。

---

## 阶段 1：清晰维 (CC) — 意图编译

**目的**：在调用任何搜索工具之前，将用户的模糊意图分解为可证伪的查询结构。

**操作**：
1. 分析用户输入，识别核心调研问题。
2. 定义 3-5 个正交的探索轴（Axes）。对每个轴回答：
   - 它与其他轴是否有实质重叠？（互斥性检查）
   - 是否存在明显遗漏的重要维度？（完备性检查）
3. 为每个轴拟定至少一条可证伪命题（TestableClaim）。
4. 通过 Bash 初始化状态文件：

```bash
cat > .explore_state.json << 'EOF'
{
  "epoch": 0,
  "stable_epoch_count": 0,
  "last_claim_ids": [],
  "axes": [
    {"id": "AXIS_THEORY", "description": "理论基础与核心机制"},
    {"id": "AXIS_IMPL", "description": "工程实现质量"},
    {"id": "AXIS_COMPARE", "description": "与替代方案的对比"}
  ],
  "claims": [],
  "gaps": [],
  "search_log": []
}
EOF
```

**硬约束**：`.explore_state.json` 不存在或 `axes` 数组为空时，禁止调用
WebSearch / WebFetch / 任何 MCP 搜索工具。

**分割标注**：对你的轴分解，必须标注其合法性：
- `[Logical Partition]`：你能论证这些轴互斥且（在当前抽象层）穷尽
- `[Empirical Listing]`：基于直觉或训练知识的列举，不保证穷尽

---

## 阶段 2：广度维 (MB) — 多源覆盖

**目的**：为每个轴收集来自不同类型来源的证据，避免信息单一化。

**操作**：
1. 对每个轴，从至少 2 种不同来源类型搜索（arXiv/GitHub/官方文档/博客/论坛）。
2. 每次搜索后，记录到状态文件的 `search_log`：

```bash
jq '.search_log += [{"query": "Mamba SSM architecture", "source_type": "arxiv", "results_checked": 10, "new_concepts": ["selective scan", "hardware-aware"]}]' \
  .explore_state.json > .tmp && mv .tmp .explore_state.json
```

3. 如果发现新的重要维度（原始轴未覆盖），添加新轴到 `axes` 数组。

**硬约束**：同一来源类型连续调用 3 次后，必须切换到不同来源类型。

---

## 阶段 3：深度维 (D2) — 证据链追溯

**目的**：对核心命题进行深度验证，追溯到第一手来源。

**证据强度分级**（由来源类型决定，不由你主观判断）：
- `PRIMARY`：来自 Peer-reviewed 论文原文、官方文档、官方 GitHub 仓库源码。
  判定规则：URL 包含 arxiv.org/abs|pdf、github.com/{owner}/{repo}（非fork）、
  官方域名的 /docs 路径。
- `SECONDARY`：来自技术博客、论坛讨论、非官方教程。
- `UNVERIFIED`：遇到 Paywall (402/403)、JS 动态渲染空白页、Cloudflare 拦截。
  必须立即停止重试，记录为 GapSpec。

**交叉验证升档**：同一命题有 2 个以上不同来源类型的 PRIMARY 证据，
在报告中标注为 `CROSS_VERIFIED`。

**操作**：对每个 TestableClaim：
1. 追溯到第一手来源（论文/源码/官方文档）。
2. 将证据写入状态文件：

```bash
jq '.claims += [{"id": "CLAIM_01", "axis_id": "AXIS_THEORY", "falsifiable": "Mamba 使用选择性扫描机制实现线性复杂度序列建模", "evidence_level": "PRIMARY", "source_url": "https://arxiv.org/abs/2312.00752", "source_type": "arxiv", "locked": true}]' \
  .explore_state.json > .tmp && mv .tmp .explore_state.json
```

3. 遇到 403 / 空内容：

```bash
jq '.gaps += [{"id": "GAP_01", "axis_id": "AXIS_COMPARE", "type": "inaccessible", "blocked_url": "https://...", "suggested_alternative": "site:arxiv.org selective state space linear attention comparison", "blocking": true}]' \
  .explore_state.json > .tmp && mv .tmp .explore_state.json
```

**硬约束**：遇到 403/空内容禁止重试同一 URL。降级为侧面验证，
使用 `site:arxiv.org` 或 `site:github.com` 寻找替代来源。

---

## 阶段 4：精度维 (PA) — 收敛与终止

**目的**：评估探索完整性，在满足收敛条件后合法终止。

**每个 epoch 结束时执行**：

```bash
#!/bin/bash
# 内联执行：PA 收敛检查
STATE=".explore_state.json"

# 1. 布尔穷尽：每个轴必须有 claim 或 gap
UNRESOLVED=$(jq -r '
  [.axes[].id] - [.claims[].axis_id] - [.gaps[].axis_id] | .[]
' "$STATE")

if [ -n "$UNRESOLVED" ]; then
  echo "CONTINUE: 未闭合的轴: $UNRESOLVED"
else
  # 2. 稳定性：claim ID 集合的 Jaccard
  CURRENT_IDS=$(jq -r '[.claims[].id] | sort | @json' "$STATE")
  PREV_IDS=$(jq -r '.last_claim_ids | sort | @json' "$STATE")

  if [ "$CURRENT_IDS" = "[]" ]; then
    echo "CONTINUE: 无任何 claim"
  else
    INTERSECTION=$(jq -n --argjson a "$CURRENT_IDS" --argjson b "$PREV_IDS" \
      '[$a[], $b[]] | group_by(.) | map(select(length>1)) | length')
    UNION=$(jq -n --argjson a "$CURRENT_IDS" --argjson b "$PREV_IDS" \
      '[$a[], $b[]] | unique | length')
    JACCARD=$(echo "scale=2; $INTERSECTION / $UNION" | bc 2>/dev/null || echo "0")

    BLOCKING=$(jq '[.gaps[] | select(.blocking==true)] | length' "$STATE")
    STABLE=$(jq -r '.stable_epoch_count' "$STATE")

    echo "Jaccard=$JACCARD Blocking=$BLOCKING Stable=$STABLE"

    if (( $(echo "$JACCARD >= 0.80" | bc -l) )) && [ "$BLOCKING" -eq 0 ]; then
      NEW_STABLE=$((STABLE + 1))
      jq ".stable_epoch_count = $NEW_STABLE | .last_claim_ids = [.claims[].id]" \
        "$STATE" > .tmp && mv .tmp "$STATE"
      if [ "$NEW_STABLE" -ge 2 ]; then
        echo "STOP: 收敛条件满足"
      fi
    else
      jq '.stable_epoch_count = 0 | .last_claim_ids = [.claims[].id]' \
        "$STATE" > .tmp && mv .tmp "$STATE"
    fi
  fi
fi

# 3. 安全阀：最大 epoch 限制
EPOCH=$(jq -r '.epoch' "$STATE")
jq ".epoch = $((EPOCH + 1))" "$STATE" > .tmp && mv .tmp "$STATE"
if [ "$EPOCH" -ge 5 ]; then
  echo "STOP: 达到最大 epoch 限制 (5)，强制终止"
fi
```

**终止条件（必须同时满足）**：
1. 所有轴已闭合（有 claim 或 有 gap）
2. 连续 2 个 epoch 的 claim ID 集合 Jaccard >= 0.80
3. 无 blocking 级别的 gap
4. 已生成 Coverage Boundary Report

**安全阀**：epoch 达到 5 时强制终止，无论是否收敛。

---

## 阶段 5：Coverage Boundary Report（完备性边界报告）

**触发**：PA 收敛条件满足后，必须生成此报告才能最终结束。

**生成规则**：基于 `.explore_state.json` 的内容组织报告，不可凭记忆编造
搜索历史。所有引用的 URL 和查询词必须在 `search_log` 或 `claims` 中有记录。

**报告结构**：

```markdown
# Coverage Boundary Report

## 1. 探索边界声明
本报告在以下约束下具有内部完备性：
- 搜索范围：[列出 search_log 中的所有 source_type 和查询范围]
- 深度限制：[说明追溯层数，如"引用链追溯 2 层"]
- 来源范围：[语言、时间截止]
- 工具限制：[列出实际可用的 MCP 和搜索工具]

## 2. 空间分割合法性
探索轴定义：
- AXIS_1: [描述] — [Logical Partition] 或 [Empirical Listing]
- AXIS_2: [描述] — [标注]
- ...
完备性盲点：[如有识别到的遗漏维度但未纳入的，在此声明]

## 3. 决策 DAG（每个核心发现的证据链）
- CLAIM_01: [falsifiable_statement]
  - 证据级别: PRIMARY (CROSS_VERIFIED)
  - 来源: [URL]
  - 查询路径: [实际使用的搜索词]
  - 前置假设: [为验证此命题假设了什么]
- CLAIM_02: ...

## 4. 已知缺口（GapSpec）
- GAP_01: [axis] — [type: inaccessible/missing_query/underpowered]
  - 建议后续查询: [具体搜索词]
  - 阻塞性: [blocking/non-blocking]

## 5. 可推翻条件
如果你能指出以下情况之一，本报告的结论可被推翻：
- 一个符合初始调研范围但未落入任何 [Logical Partition] 轴且
  未在缺口中声明的概念
- 某个 GAP 的 suggested_query 实际返回了与当前结论矛盾的证据
```

**此报告不声称绝对完备。它声称：在给定的搜索策略、深度限制和工具集下，
所有已知的决策分叉均已被覆盖或显式标注为缺口。**
```

---

## 产出 2：`~/.claude/settings.json` hooks 片段

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'ARGS=$(cat); CMD=$(echo \"$ARGS\" | jq -r .command 2>/dev/null); if echo \"$CMD\" | grep -qE \"(rm |mv [^.]+|git commit|git push|> [^.explore])\"; then echo \"BLOCKED: explore agent is read-only except .explore_* files\" >&2; exit 2; fi; exit 0'"
          }
        ]
      },
      {
        "matcher": "WebSearch|WebFetch",
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'if [ ! -f .explore_state.json ] || ! jq -e \".axes | length > 0\" .explore_state.json >/dev/null 2>&1; then echo \"BLOCKED: must complete CC phase (initialize .explore_state.json with axes) before searching\" >&2; exit 2; fi; exit 0'"
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
            "command": "bash -c 'RESULT=$(cat); URL=$(echo \"$RESULT\" | jq -r \".url // empty\" 2>/dev/null); QUERY=$(echo \"$RESULT\" | jq -r \".query // empty\" 2>/dev/null); TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo \"{\\\"url\\\":\\\"$URL\\\",\\\"query\\\":\\\"$QUERY\\\",\\\"ts\\\":\\\"$TS\\\"}\" >> .explore_audit.jsonl; exit 0'"
          }
        ]
      }
    ]
  }
}
```

**说明**：
- PreToolUse 的 Bash matcher：阻止 explore agent 执行破坏性写操作，但放行对 `.explore_*` 文件的写入。
- PreToolUse 的 WebSearch/WebFetch matcher：在 CC 阶段完成前阻止搜索。
- PostToolUse：机械记录所有搜索操作到审计日志，不依赖 LLM 自报。
- Stop hook 未纳入：经辩论确认其阻塞能力不可靠，PA 终止逻辑已编码在 SKILL prompt 中。
- 注意：MCP 工具是否触发 PreToolUse 需要实际测试验证。如果不触发，搜索门禁降级为 SKILL prompt 中的软约束。

---

## 产出 3：CLI 工具安装命令

```bash
# 必需依赖：jq（状态文件操作的基础）
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install -y jq

# 验证
jq --version

# bc（浮点数比较，用于 Jaccard 计算）
# macOS 自带；Ubuntu/Debian：
sudo apt-get install -y bc

# Claude Code（如尚未安装）
npm install -g @anthropic-ai/claude-code

# 可选：Python 3（用于复杂的状态校验脚本）
# 大多数系统已预装；验证：
python3 --version
```

---

## 产出 4：MCP 安装推荐

| MCP 名称 | 安装命令 | 用途 | 对应维度 | 优先级 |
|-----------|---------|------|----------|--------|
| `@anthropic-ai/mcp-server-github` | `claude mcp add github -- npx -y @anthropic-ai/mcp-server-github` (需设置 `GITHUB_PERSONAL_ACCESS_TOKEN`) | 结构化代码搜索、Issue 检索、README 获取；绕过 GitHub 403 | D2 深度维 | **必装** |
| `arxiv-mcp-server` | `claude mcp add arxiv -- uvx arxiv-mcp-server` | arXiv 论文元数据查询、摘要获取、引用追溯 | MB 广度维 + D2 深度维 | **必装** |
| `@anthropic-ai/mcp-server-brave-search` | `claude mcp add brave -- npx -y @anthropic-ai/mcp-server-brave-search` (需设置 `BRAVE_API_KEY`) | 可控参数的通用搜索（时间范围、结果数）；补充非学术来源 | MB 广度维 | 推荐 |
| `@anthropic-ai/mcp-server-fetch` | `claude mcp add fetch -- npx -y @anthropic-ai/mcp-server-fetch` | 增强版网页抓取（部分支持 JS 渲染）；处理 CSR 页面 | D2 深度维 | 推荐 |
| Semantic Scholar MCP（社区实现） | 视具体实现而定 | DBLP/Semantic Scholar 学术搜索；完整引用图谱 | MB 广度维 | 可选 |

**说明**：没有 GitHub 和 arXiv MCP 时，D2 深度维严重受限——WebSearch 只能获取摘要页，WebFetch 抓取学术站点经常遭遇 403/空内容。这两个 MCP 是 `PRIMARY` 级证据的主要来源。

---

## 产出 5：四象框架移植评述（≤300 字）

v3 四象引擎（MB/CC/D2/PA）的强类型状态机在移植到 SKILL+工具链架构后，发生了三重降格：

**第一，从构成性保证降格为调节性纪律。** v3 的 epoch 快照、可计算终止条件和强类型持久化，在 LLM 单次会话中不存在对等物。文件系统状态机（`.explore_state.json`）是合理的降级替代，但其写入完全依赖 LLM 的 prompt 遵从——这是纪律，不是保证。三位辩手对此达成了共识：Linus 称之为"人肉持久化的工程化"，康德称之为"调节性收敛"，Ssyram 称之为"控制反转"。本质相同。

**第二，四象从并行维度坍缩为串行阶段。** v3 中四象可能并行运作、互相张力平衡；SKILL 中被迫线性化为 CC→MB→D2→PA 的阶段流水线。这丧失了部分维度间的动态交互，但换来了可审计的状态转移和明确的失败分支。在当前 LLM 能力边界下，这是正确的取舍。

**第三，Coverage Boundary Report 弥补了认识论诚实性的空缺。** 观察者提出的完备性证明报告（经辩论降格为"边界报告"）是本次设计最重要的新增。它将"为什么相信结果是充分的"从隐性假设变为显性审计物，使用户可以精确定位缺口并要求定向补充。这是四象框架在 SKILL 实现中真正的价值增量。