---
title: "测试：基础运行"
rounds: 2
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 正方
    model: gpt-4o-mini
    style: 支持猫作为最佳宠物
  - name: 反方
    model: gpt-4o-mini
    style: 支持狗作为最佳宠物
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
    正方:
      1: "猫是理想的家庭宠物。猫独立安静，饲养成本低，适合现代家庭，是最佳伴侣选择。"
      2: "综上，猫在陪伴性、成本和易养程度上均占优，是家庭宠物的最佳选择。"
    反方:
      1: "狗是人类最忠实的伙伴。狗热情互动，促进运动和社交，是无可替代的家庭成员。"
      2: "总结：狗的忠诚与陪伴价值远超其养护成本，是家庭宠物的首选。"
  judge: "裁定：正方论据更具说服力。猫的低成本和易养性符合现代家庭需求。"
  compact:
    phase_a: '{"topic":{"current_formulation":"猫和狗哪种更适合作为家庭宠物","notes":null},"axioms":["双方均承认宠物对家庭有积极影响"],"disputes":[{"id":"D1","title":"最佳宠物选择","status":"open","positions":{"正方":"猫更适合","反方":"狗更适合"},"resolution":null}],"pruned_paths":[]}'
    phase_b:
      正方: '{"name":"正方","active":true,"stance_version":1,"stance":"支持猫作为最佳宠物。猫独立安静，饲养成本低，适合现代家庭。","core_claims":[{"id":"C1","text":"猫饲养成本低","status":"active"},{"id":"C2","text":"猫独立安静适合现代家庭","status":"active"}],"key_arguments":[{"id":"A1","claim_id":"C1","text":"猫粮和医疗费用低于狗","status":"active"},{"id":"A2","claim_id":"C2","text":"猫不需要每日遛弯","status":"active"}],"abandoned_claims":[]}'
      反方: '{"name":"反方","active":true,"stance_version":1,"stance":"支持狗作为最佳宠物。狗热情互动，促进运动和社交。","core_claims":[{"id":"C1","text":"狗促进主人运动和社交","status":"active"},{"id":"C2","text":"狗的忠诚度无可替代","status":"active"}],"key_arguments":[{"id":"A1","claim_id":"C1","text":"遛狗促进户外运动","status":"active"},{"id":"A2","claim_id":"C2","text":"狗对主人情感反馈更强","status":"active"}],"abandoned_claims":[]}'
    validity_check: "YES"
    drift_check: "REFINEMENT\n合理细化，立场未发生根本倒转。"
---

猫和狗，哪种动物更适合作为家庭宠物？请从陪伴性、成本、易养程度三方面讨论。
