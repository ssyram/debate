---
# ═══════════════════════════════════════════════════════════════
#  辩论议题配置模板
#  所有字段均可省略，有合理默认值。
#
#  使用方法:
#    1. 复制此文件:  cp template.md my_topic.md
#    2. 编辑内容
#    3. 运行辩论:    debate-tool run my_topic.md
#    4. 预览配置:    debate-tool run my_topic.md --dry-run
#    5. 质询模式:    debate-tool run my_topic.md --cross-exam
#    6. 全轮质询:    debate-tool run my_topic.md --cross-exam -1
#    7. 收敛早停:    debate-tool run my_topic.md --early-stop
#
#  或使用 Web UI 向导:  python -m debate_tool live
#  向导支持 AI 立场推荐 (可选), 自动生成辩手配置。
# ═══════════════════════════════════════════════════════════════

# 辩论标题 (默认: 文件名)
title: "在此输入辩论标题"

# 辩论轮数 (默认: 3, --rounds 总是覆盖)
rounds: 3

# 单次 API 超时秒数 (默认: 300)
# timeout: 300

# 辩手单次回复最多输出的 token 数（控制输出长度，默认: 6000）
# 注意：这是输出限制，不是上下文窗口大小。上下文超限时系统会自动 compact 历史并重试。
# max_reply_tokens: 6000

# COT (Chain of Thought) 思考模式
# true = 开启，无思考 token 限制
# 2000 = 开启，思考不超过 2000 tokens
# false/省略 = 关闭（默认）
# cot: false

# 质询轮数 (默认: 0, 即不质询)
#   1   — R1 后质询 (辩手 round-robin 互相质疑)
#   3   — R1~R3 后均质询
#   -1  — 每轮都质询 (最后一轮除外)
# 也可用 CLI flag: debate-tool run topic.md --cross-exam [N]
# cross_exam: 1

# 早停 (默认: false)
# 每轮后检查观点收敛度, 达到阈值则跳过剩余轮次
# true = 使用默认阈值 55%; 也可指定 0~1 之间的浮点数
# 可通过 CLI flag 开启: debate-tool run topic.md --early-stop [T]
# early_stop: true
# early_stop: 0.6

# ─── API 配置 (可选) ───────────────────────────────────
# 不填则使用环境变量 DEBATE_BASE_URL / DEBATE_API_KEY,
# base_url: "your_api_base_url"
# api_key: "your_api_key"

# ─── 辩手配置 (至少 2 位) ──────────────────────────────
# style 格式建议: "立场名：具体说明"
# 辩手之间应形成有效对立或互补。
#
# 常见立场模板:
#   通用型: 务实工程派 / 创新挑战派 / 严谨分析派
#   权衡型: 精简派 / 覆盖派 / 平衡派
#   审查型: 严格审查派 / 支持验证派 / 中立分析派
#   自定义: "红队攻击手：目标是找到所有漏洞..."
debaters:
  - name: "GPT-5.2"
    model: "gpt-5.2"
    style: "务实工程派"
    # base_url: "your_api_base_url"
    # api_key: "your_api_key"
  - name: "Kimi-K2.5"
    model: "kimi-k2.5"
    style: "创新挑战派"
  - name: "Sonnet-4-6"
    model: "claude-sonnet-4-6"
    style: "严谨分析派"

# ─── 裁判配置 ──────────────────────────────────────────
judge:
  model: "claude-opus-4-6"
  name: "Opus-4-6 (裁判)"
  max_tokens: 8000
  # base_url: "your_api_base_url"
  # api_key: "your_api_key"

# ─── 约束条件 (可选) ──────────────────────────────────
# 注入每个辩手的 system prompt, 作为不可违反的规则。
# constraints: |
#   - 效果变差宁愿不变
#   - 所有建议必须给出具体措辞
#   - 严守职责边界

# ─── 各轮任务指令 (可选, 有默认值) ────────────────────
# round1_task: |
#   针对各议题给出立场和建议，每个 200-300 字
# middle_task: |
#   回应其他辩手观点，深化立场，400-600 字
# final_task: |
#   最终轮，给出最终建议，标注优先级，300-500 字

# ─── 裁判指令 (可选, 有默认值) ────────────────────────
# judge_instructions: |
#   输出结构化 Summary：
#   ## 一、各辩手表现评价（每位 2-3 句）
#   ## 二、逐一裁定
#   对每个议题给出：
#   - **裁定**：最终方案
#   - **理由**：引用辩论中的关键论据
#   - **优先级**：P0 / P1 / P2
#   ## 三、完整修改清单
---

# 辩论议题

在此写入辩论正文内容...

## 背景

描述辩论的背景和上下文。

## 议题一

...

## 议题二

...

## 关键数据 (如有)

提供支撑辩论的数据、对比表格等。
