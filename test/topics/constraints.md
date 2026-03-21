---
title: "测试：约束条件"
rounds: 2
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
constraints: |
  - 必须用数据或案例支持论点
  - 禁止人身攻击
  - 每次发言必须引用至少一个具体事实
debaters:
  - name: 线上派
    model: gpt-4o-mini
    style: 主张线上教育优于线下
  - name: 线下派
    model: gpt-4o-mini
    style: 主张线下教育不可替代
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述核心论点并引用事实，80字以内。"
middle_task: "反驳对方，80字以内。"
final_task: "最终总结，60字以内。"
judge_instructions: "裁定谁更有说服力，注意辩手是否遵守了约束条件。100字以内。"
mock_responses:
  debaters:
    线上派:
      1: "线上教育覆盖更广，录播回看提升复习效率。"
      2: "有数据平台支持时，线上个性化更明显。"
    线下派:
      1: "线下互动更强，课堂反馈和纪律更稳定。"
      2: "面对面环境更利于社交训练与长期习惯。"
  judge: "裁定：线上派更贴合未来趋势，但证据都较简短。"
---

线上教育和线下教育，哪种模式更适合未来？
