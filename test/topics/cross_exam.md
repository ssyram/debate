---
title: "测试：质询模式"
rounds: 2
cross_exam: 1
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 乐观派
    model: gpt-4o-mini
    style: 认为AI对社会利大于弊
  - name: 谨慎派
    model: gpt-4o-mini
    style: 认为AI风险不可忽视
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述核心论点，80字以内。"
middle_task: "回应质询并深化论点，80字以内。"
final_task: "最终陈词，60字以内。"
judge_instructions: "简短裁定，100字以内。"
mock_responses:
  debaters:
    乐观派:
      1: "AI提升效率与医疗水平，整体收益更大。"
      2: "我方承认风险，但治理可控且收益更广。"
    谨慎派:
      1: "AI会放大失业与误判，风险不能低估。"
      2: "若规则滞后，AI伤害会先于收益出现。"
  judge: "裁定：乐观派论证更完整，但也应重视治理。"
  cx_select:
    乐观派: "谨慎派"
    谨慎派: "乐观派"
  cx_questions:
    乐观派:
      - "你如何量化AI带来的失业规模？"
      - "若加强监管，风险为何仍不可控？"
    谨慎派:
      - "你如何保证AI决策不会系统性偏见？"
      - "效率提升能否覆盖社会适应成本？"
---

AI技术的快速发展对人类社会是利大于弊还是弊大于利？
