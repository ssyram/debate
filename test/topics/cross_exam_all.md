---
title: "测试：全轮质询"
rounds: 2
cross_exam: -1
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 开源派
    model: gpt-4o-mini
    style: 主张开源优先
  - name: 闭源派
    model: gpt-4o-mini
    style: 主张商业闭源优先
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
    开源派:
      1: "开源促进审计与协作，创新扩散更快。"
      2: "透明代码更利于修复问题与建立信任。"
    闭源派:
      1: "闭源更利于投入回收和统一产品质量。"
      2: "持续盈利才能支撑长期研发与服务。"
  judge: "裁定：开源派更占上风，透明性论点更具体。"
  cx_select:
    开源派: "闭源派"
    闭源派: "开源派"
  cx_questions:
    开源派:
      - "闭源如何避免用户被单一厂商锁定？"
      - "缺少外部审计时，安全问题如何发现？"
    闭源派:
      - "开源项目缺资金时，维护责任由谁承担？"
      - "社区分叉频繁时，用户如何保证稳定？"
---

软件开发应该优先选择开源还是闭源方案？
