---
title: "金丝雀：消息/引导基准"
rounds: 1
max_reply_tokens: 200
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 赞成方
    model: gpt-4o-mini
    style: 支持电动车
  - name: 反对方
    model: gpt-4o-mini
    style: 支持燃油车
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述核心观点，80字以内。"
final_task: "最终总结，60字以内。"
judge_instructions: "简短裁定，100字以内。"
compact_model: gpt-4o-mini
compact_check_model: gpt-4o-mini
compact_base_url: ${DEBATE_BASE_URL}
compact_check_base_url: ${DEBATE_BASE_URL}
mock_responses:
  debaters:
    赞成方:
      1: "电动车日常成本更低，城市通勤体验更好。"
    反对方:
      1: "燃油车补能更快，长途出行仍更省心。"
  judge: "裁定：赞成方更贴近当前城市用户的主要需求。"
---

电动车和燃油车哪种更适合当前消费者？
