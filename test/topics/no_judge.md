---
title: "测试：跳过裁判"
rounds: 2
no_judge: true
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 早起派
    model: gpt-4o-mini
    style: 主张早起更健康高效
  - name: 晚起派
    model: gpt-4o-mini
    style: 主张晚睡晚起更适合创造力
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述核心论点，80字以内。"
middle_task: "反驳对方，80字以内。"
final_task: "最终总结，60字以内。"
judge_instructions: "简短裁定，100字以内。"
mock_responses:
  debaters:
    早起派:
      1: "早起更利于规律作息和高质量晨间专注。"
      2: "稳定生物钟让执行力和健康表现更可持续。"
    晚起派:
      1: "晚起可匹配夜间创造高峰，不必强行统一。"
      2: "适合自己的节律，比盲目早起更有效率。"
---

早起和晚起，哪种生活方式更有利于个人发展？
