---
title: "测试：CoT+质询组合"
rounds: 2
cot: 80
cross_exam: 1
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 集中派
    model: gpt-4o-mini
    style: 主张集中办公效率更高
  - name: 远程派
    model: gpt-4o-mini
    style: 主张远程办公更灵活
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述核心论点，80字以内。"
middle_task: "回应质询并深化论点，80字以内。"
final_task: "最终总结，60字以内。"
judge_instructions: "简短裁定，100字以内。"
mock_responses:
  debaters:
    集中派:
      1: "集中办公沟通直接，协作与带教更高效。"
      2: "面对复杂项目，现场同步仍更稳定高效。"
    远程派:
      1: "远程办公更灵活，能扩大人才范围与专注时间。"
      2: "完善流程后，远程同样能稳定协作与成长。"
  judge: "裁定：集中派论据更扎实，但远程派也有灵活优势。"
  cx_select:
    集中派: "远程派"
    远程派: "集中派"
  cx_questions:
    集中派:
      - "远程新人如何获得及时指导与融入团队？"
      - "跨时区协作时，决策延迟如何避免？"
    远程派:
      - "通勤耗时增加后，集中办公效率如何保证？"
      - "安静独立任务为何一定要现场完成？"
  cot_thinking:
    集中派:
      1: "强调即时沟通、默契建立和新人培养优势。"
      2: "借质询继续突出复杂协作的现场效率。"
    远程派:
      1: "突出灵活性、招聘范围和深度工作时间。"
      2: "回应协作疑虑，强调制度与工具可弥补。"
---

远程办公和集中办公，哪种工作模式更有利于团队协作与个人成长？
