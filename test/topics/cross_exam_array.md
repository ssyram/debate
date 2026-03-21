---
title: "测试：数组质询模式"
rounds: 3
cross_exam: [1]
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 甲方
    model: gpt-4o-mini
    style: 支持电动车
  - name: 乙方
    model: gpt-4o-mini
    style: 支持燃油车
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述核心论点，80字以内。"
middle_task: "回应对方，80字以内。"
final_task: "最终陈词，60字以内。"
judge_instructions: "简短裁定，100字以内。"
mock_responses:
  debaters:
    甲方:
      1: "电动车通勤成本低，城市使用更安静便捷。"
      2: "家用短途场景里，补能与续航已足够。"
      3: "综合成本与体验，电动车更适合多数家庭。"
    乙方:
      1: "燃油车补能快，长途与寒冷地区更稳妥。"
      2: "保值和基础设施成熟仍是燃油车优势。"
      3: "若重视通用性，燃油车目前仍更可靠。"
  judge: "裁定：甲方更贴近家庭日常场景，论证略强。"
  cx_select:
    甲方: "乙方"
    乙方: "甲方"
  cx_questions:
    甲方:
      - "家庭日常短途占多，长途优势是否被夸大？"
      - "燃油价格波动下，成本优势如何维持？"
    乙方:
      - "节假日排队充电时，电动车如何保证效率？"
      - "冬季续航下降后，家用便利是否受影响？"
---

电动车和燃油车，哪种更适合作为家庭用车？
