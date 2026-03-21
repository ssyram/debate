---
judge:
  model: gpt-4o-mini
  name: 新裁判
  max_tokens: 300
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
judge_instructions: "从逻辑严密性和论据充分性两个维度评判，150字以内。"
---
