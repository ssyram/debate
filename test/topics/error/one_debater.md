---
title: "错误测试：仅一个辩手"
rounds: 1
max_reply_tokens: 100
timeout: 60
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 唯一辩手
    model: gpt-4o-mini
    style: 孤军奋战
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 100
---

这个话题只有一个辩手，应该报错。
