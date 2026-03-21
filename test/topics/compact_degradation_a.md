---
title: "测试：compact Phase A 降级"
rounds: 2
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 甲方
    model: gpt-4o-mini
    style: 支持远程办公的全面推广
  - name: 乙方
    model: gpt-4o-mini
    style: 支持传统办公模式的优势
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "简述你的核心观点，80字以内。"
middle_task: "反驳对方，80字以内。"
final_task: "最终总结，60字以内。"
judge_instructions: "简短裁定谁更有说服力，100字以内。"
compact_model: gpt-4o-mini
compact_check_model: gpt-4o-mini
compact_base_url: ${DEBATE_BASE_URL}
compact_check_base_url: ${DEBATE_BASE_URL}
compact_embedding_model: text-embedding-3-small
compact_embedding_url: ${DEBATE_EMBEDDING_URL}
compact_embedding_api_key: ${DEBATE_API_KEY}
mock_responses:
  debaters:
    甲方:
      1: "远程办公降低通勤成本，提高工作灵活性，是未来办公的趋势。"
      2: "综上，远程办公在效率、成本、员工满意度上均占优。"
    乙方:
      1: "传统办公促进团队协作，增强企业文化认同，更有利于创新。"
      2: "总结：面对面交流的价值不可替代，传统办公仍是最佳选择。"
  judge: "裁定：甲方论据更具说服力，远程办公的趋势不可逆转。"
  compact:
    phase_a:
      - "这不是合法 JSON，第一次故意失败"
      - "{ 还是不对，第二次故意失败"
      - '{"topic":{"current_formulation":"远程办公 vs 传统办公","notes":null},"axioms":["双方均承认办公方式影响生产力"],"disputes":[{"id":"D1","title":"最佳办公方式","status":"open","positions":{"甲方":"远程办公更优","乙方":"传统办公更优"},"resolution":null}],"pruned_paths":[]}'
    phase_b:
      甲方: '{"name":"甲方","active":true,"stance_version":1,"stance":"支持远程办公。降低通勤成本，提高灵活性。","core_claims":[{"id":"C1","text":"远程办公降低成本","status":"active"}],"key_arguments":[{"id":"A1","claim_id":"C1","text":"通勤费用大幅减少","status":"active"}],"abandoned_claims":[]}'
      乙方: '{"name":"乙方","active":true,"stance_version":1,"stance":"支持传统办公。促进团队协作，增强文化认同。","core_claims":[{"id":"C1","text":"面对面协作更高效","status":"active"}],"key_arguments":[{"id":"A1","claim_id":"C1","text":"即时沟通减少误解","status":"active"}],"abandoned_claims":[]}'
    validity_check: "YES"
    drift_check: "REFINEMENT\n合理细化，立场未发生根本倒转。"
---

远程办公与传统办公，哪种模式更适合现代企业？请从效率、成本、员工满意度三方面讨论。
