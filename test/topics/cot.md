---
title: "测试：CoT思考模式"
rounds: 2
cot: 80
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 实用派
    model: gpt-4o-mini
    style: 注重实用性和效率
  - name: 理想派
    model: gpt-4o-mini
    style: 注重完美和长远
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
    实用派:
      1: "先上线能更快验证需求，减少闭门造车。"
      2: "快速迭代更能贴近用户与市场变化。"
    理想派:
      1: "先打磨质量可减少返工与品牌损害。"
      2: "稳定发布能降低维护成本与用户流失。"
  judge: "裁定：实用派更有说服力，验证需求的优势更直接。"
  cot_thinking:
    实用派:
      1: "先抓核心价值，强调反馈速度与试错成本。"
      2: "回应质量担忧，但坚持迭代能更快修正。"
    理想派:
      1: "突出首发质量与信誉成本，避免仓促上线。"
      2: "继续强调返工代价，主打长期稳定收益。"
---

软件开发中，"先上线再迭代"还是"做到完美再发布"，哪种策略更好？
