---
title: "测试：自定义轮数"
rounds: 1
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 极简派
    model: gpt-4o-mini
    style: 主张极简主义生活
  - name: 享受派
    model: gpt-4o-mini
    style: 主张丰富多彩的生活
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述核心论点，80字以内。"
final_task: "最终总结，60字以内。"
judge_instructions: "简短裁定，100字以内。"
mock_responses:
  debaters:
    极简派:
      1: "极简减少负担，让时间与注意力更集中。"
      2: "少而精的生活更稳定，也更容易感到满足。"
    享受派:
      1: "丰富体验能拓宽人生感受与幸福来源。"
      2: "多样选择让生活更有趣，也更有记忆点。"
  judge: "裁定：极简派更有条理，幸福定义解释更清晰。"
---

极简主义还是丰富多彩，哪种生活方式更幸福？
