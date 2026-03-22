module Prompt
  ( -- * Check phases
    phase1Prompt
  , phase2Prompt
  , phase3Prompt
  , phase4Prompt
  , phase5Prompt
    -- * Polish operations
  , rewritePrompt
  , mergePrompt
  ) where

import Data.Text (Text)
import qualified Data.Text as T

-- ────────────────────────────────────────────────────────────────────
-- Check Phase Prompts
-- ────────────────────────────────────────────────────────────────────

phase1Prompt :: Text -> Text
phase1Prompt designDoc = T.unlines
  [ "你是设计文档分析专家。请从以下设计文档中，按 Section 逐一提取所有**原子化设计命题**。"
  , ""
  , "要求："
  , "- 每条命题必须是**可验证的最小声明**（一个接口契约、一个字段约束、一个行为规则）"
  , "- 跨 Section 引用的相同概念独立提取"
  , "- 每 500 字约 5-10 条"
  , ""
  , "**你必须且只能返回一个合法 JSON 数组，不要添加任何其他文字、markdown 代码块标记或解释。**"
  , ""
  , "JSON schema："
  , "```"
  , "[{\"id\": \"P1\", \"section\": \"Section名\", \"text\": \"命题内容\"}, ...]"
  , "```"
  , ""
  , "## 设计文档"
  , ""
  , designDoc
  ]

phase2Prompt :: Text -> Text -> Text
phase2Prompt designDoc propositionsJson = T.unlines
  [ "你是一致性校验专家。以下是从设计文档中抽取的原子化命题。"
  , "请对所有命题两两比对（重点检查跨 Section 的），找出："
  , ""
  , "1. **矛盾**：两条命题对同一主体有相互否定的声明"
  , "2. **遗漏**：某命题声明了 A，但 A 依赖的 B 在文档中没有命题覆盖"
  , ""
  , "严重程度判定："
  , "- critical：会导致系统级别的设计冲突"
  , "- high：会导致实现时运行错误或数据丢失"
  , "- medium：会导致行为不确定或测试无法通过"
  , "- low：文档不清晰，不影响功能"
  , ""
  , "**你必须且只能返回一个合法 JSON 数组，不要添加任何其他文字、markdown 代码块标记或解释。**"
  , ""
  , "JSON schema："
  , "```"
  , "[{\"type\": \"contradiction\"|\"omission\", \"severity\": \"critical\"|\"high\"|\"medium\"|\"low\", \"refs\": [\"Px\", \"Py\"], \"description\": \"说明\"}, ...]"
  , "```"
  , ""
  , "如果没有发现任何矛盾或遗漏，返回空数组 []。"
  , ""
  , "## 命题列表"
  , ""
  , propositionsJson
  , ""
  , "## 原始设计文档"
  , ""
  , designDoc
  ]

phase3Prompt :: Text -> Text -> Text
phase3Prompt designDoc propositionsJson = T.unlines
  [ "你是系统设计分析专家。从以下命题列表中归纳 8-20 个核心设计点。"
  , "然后对所有设计点两两组合，检查 'A 与 B 的交互是否有命题覆盖'。"
  , ""
  , "**你必须且只能返回一个合法 JSON 对象，不要添加任何其他文字、markdown 代码块标记或解释。**"
  , ""
  , "JSON schema："
  , "```"
  , "{"
  , "  \"design_points\": [{\"id\": \"D1\", \"title\": \"设计点名\"}, ...],"
  , "  \"matrix\": [{\"point_a\": \"D1\", \"point_b\": \"D2\", \"status\": \"covered\"|\"weak\"|\"gap\", \"comment\": \"说明\"}, ...]"
  , "}"
  , "```"
  , ""
  , "matrix 中只需包含 status 为 weak 或 gap 的条目（covered 的可省略以节省空间）。"
  , ""
  , "## 命题列表"
  , ""
  , propositionsJson
  , ""
  , "## 原始设计文档"
  , ""
  , designDoc
  ]

phase4Prompt :: Text -> Text -> Text -> Text -> Text
phase4Prompt designDoc propositionsJson issuesJson matrixJson = T.unlines
  [ "你是设计审查总结专家。基于以下四阶段分析的中间结果，撰写最终总结。"
  , ""
  , "**你必须且只能返回一个合法 JSON 对象，不要添加任何其他文字、markdown 代码块标记或解释。**"
  , ""
  , "JSON schema："
  , "```"
  , "{"
  , "  \"summary\": \"整体评价和关键发现的文字总结\","
  , "  \"highlights\": [\"设计亮点1\", \"设计亮点2\"]"
  , "}"
  , "```"
  , ""
  , "## 原始设计文档"
  , ""
  , designDoc
  , ""
  , "## 命题列表"
  , ""
  , propositionsJson
  , ""
  , "## 矛盾与遗漏"
  , ""
  , issuesJson
  , ""
  , "## 交叉覆盖矩阵"
  , ""
  , matrixJson
  ]

-- ────────────────────────────────────────────────────────────────────
-- Polish Operation Prompts
-- ────────────────────────────────────────────────────────────────────

-- | Phase 5: detect unsupported suspicious claims + audit existing Q&A entries.
-- Input: design doc (may contain a ## Q&A section from previous rounds).
-- Output: JSON with two lists — suspicious_claims and qa_feedback.
phase5Prompt :: Text -> Text
phase5Prompt designDoc = T.unlines
  [ "你是设计文档可信度审查专家。请完成两项任务："
  , ""
  , "**任务一：识别无依据的可疑断言（suspicious claims）**"
  , "扫描设计文档中所有未提供足够依据的强断言，例如："
  , "- 未量化的性能保证（「几乎无延迟」「完全兼容」「无损」）"
  , "- 未说明原理的绝对性表述（「总是正确」「永远不会」）"
  , "- 隐含了尚未论证的假设（「由于X，所以Y」但X本身未被证明）"
  , "**不要**把正常的设计决策（有理由说明的选择）列为可疑断言。"
  , ""
  , "**任务二：审查现有 Q&A 条目**（如果文档末尾有 `## Q&A` 节）"
  , "对每条 Q&A 条目给出反馈："
  , "- `redundant`：该问题已在正文中有充分支撑，Q&A 不再必要"
  , "- `still_weak`：Q&A 的回答依然不足以支撑该断言"
  , "- `valid`：Q&A 仍然有必要且回答合理"
  , ""
  , "**你必须且只能返回一个合法 JSON 对象，不要添加任何其他文字、markdown 代码块标记或解释。**"
  , ""
  , "JSON schema："
  , "```"
  , "{"
  , "  \"suspicious_claims\": ["
  , "    {\"id\": \"SC1\", \"claim\": \"原文断言\", \"location\": \"所在节名\", \"reason\": \"为什么可疑\"}"
  , "  ],"
  , "  \"qa_feedback\": ["
  , "    {\"qa_id\": \"QA1\", \"verdict\": \"redundant|still_weak|valid\", \"reason\": \"说明\"}"
  , "  ]"
  , "}"
  , "```"
  , ""
  , "如果没有可疑断言，`suspicious_claims` 返回空数组 []。"
  , "如果文档没有 Q&A 节，`qa_feedback` 返回空数组 []。"
  , ""
  , "## 设计文档"
  , ""
  , designDoc
  ]

rewritePrompt :: Text -> Text -> Text
rewritePrompt design guide = T.unlines
  [ "你是文档一致化专家。基于以下修改指南，修改设计文档使其完整体现所有要求的变更。"
  , ""
  , "要求："
  , "- 对每条指南项，在文档所有相关位置一致体现"
  , "- 引入新概念时，必须同步更新文档中所有相关表格和枚举"
  , "- 不得引入指南以外的新概念"
  , "- 不得删减指南未涉及的内容"
  , "- 直接输出完整修改后的文档全文，不加任何说明或标记"
  , ""
  , "**Q&A 节维护规则**（文档末尾的 `## Q&A` 节）："
  , "- 修改指南中标记为「已解决」的 suspicious claim → 在 Q&A 节添加对应条目"
  , "  格式：`> **QA<N>: <断言原文>** <一句话说明理由>`"
  , "- 修改指南中标记为「Q&A 冗余」的条目 → 从 Q&A 节删除该条目"
  , "- 修改指南中标记为「Q&A 依然不足」的条目 → 更新该条目的回答"
  , "- 修改指南中标记为「无法支撑，删除原断言」的 claim → 从正文删除该断言，同时不加入 Q&A"
  , "- 不要修改 Q&A 节中未被指南涉及的条目"
  , ""
  , "## 修改指南"
  , ""
  , guide
  , ""
  , "## 当前设计文档"
  , ""
  , design
  ]

mergePrompt :: Text -> Text -> Text -> Text -> Text
mergePrompt design decisions newCheckReport oldCheckReport = T.unlines
  [ "你是设计合并专家。给定："
  , "- 当前设计文档"
  , "- 已有的决策集（decisions）"
  , "- 新一轮检查报告（newCheck）"
  , "- 上一轮检查报告（oldCheck）"
  , ""
  , "请判断："
  , "1. 新检查中有哪些问题是已有决策可以解决的 → 产生新的 rewrite guide"
  , "2. 新检查中有哪些问题超出已有决策范围 → 保留为 unresolved"
  , ""
  , "**你必须且只能返回一个合法 JSON 对象，不要添加任何其他文字、markdown 代码块标记或解释。**"
  , ""
  , "JSON schema："
  , "```"
  , "{"
  , "  \"new_guide\": \"基于已有决策可以执行的修改指南（如果没有新的指南，返回空字符串）\","
  , "  \"unresolved_issues\": [{\"type\": \"contradiction\"|\"omission\"|\"matrix_gap\", \"severity\": \"critical\"|\"high\"|\"medium\"|\"low\", \"refs\": [], \"description\": \"说明\"}]"
  , "}"
  , "```"
  , ""
  , "## 决策集"
  , ""
  , decisions
  , ""
  , "## 新检查报告"
  , ""
  , newCheckReport
  , ""
  , "## 上轮检查报告"
  , ""
  , oldCheckReport
  , ""
  , "## 设计文档"
  , ""
  , design
  ]
