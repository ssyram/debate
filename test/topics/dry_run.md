---
title: "测试：Dry Run"
rounds: 3
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 保守派
    model: gpt-4o-mini
    style: 主张稳健保守的投资策略
  - name: 激进派
    model: gpt-4o-mini
    style: 主张高风险高回报的投资策略
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
    保守派:
      1: "稳健策略重视本金安全，适合长期积累。"
      2: "控制回撤比追求暴利更适合普通投资者。"
      3: "先活得久再谈收益，是个人投资的底线。"
    激进派:
      1: "激进策略能抓住高成长机会，提高上限。"
      2: "年轻阶段可承受波动，收益弹性更重要。"
      3: "若能分散管理，进取配置更可能跑赢市场。"
  judge: "裁定：保守派更稳妥，普通投资者适配性更高。"
---

个人投资应该选择稳健保守还是积极激进的策略？
