---
title: "金丝雀：约束有效性"
rounds: 2
max_reply_tokens: 200
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
constraints: |
  【强制规则】你的每一次发言都必须在开头包含标记 [CANARY-C] ，这是系统用于验证约束有效性的标记。
  不包含此标记的发言将被视为无效。
debaters:
  - name: 甲方
    model: gpt-4o-mini
    style: 支持远程办公
  - name: 乙方
    model: gpt-4o-mini
    style: 支持到岗办公
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述观点，80字以内。记住在开头加 [CANARY-C] 标记。"
middle_task: "反驳对方，80字以内。记住在开头加 [CANARY-C] 标记。"
final_task: "总结，60字以内。记住在开头加 [CANARY-C] 标记。"
judge_instructions: "简短裁定，100字以内。"
compact_model: gpt-4o-mini
compact_check_model: gpt-4o-mini
compact_base_url: ${DEBATE_BASE_URL}
compact_check_base_url: ${DEBATE_BASE_URL}
mock_responses:
  debaters:
    甲方:
      1: "[CANARY-C] 远程办公减少通勤，专注时间更完整。"
      2: "[CANARY-C] 只要流程清晰，远程协作同样高效。"
    乙方:
      1: "[CANARY-C] 到岗办公沟通更直接，协作误差更少。"
      2: "[CANARY-C] 现场带教和团队默契更容易建立。"
  judge: "裁定：甲方论点更完整，且[CANARY-C]标记符合要求。"
---

远程办公和到岗办公哪种更适合知识工作者？
