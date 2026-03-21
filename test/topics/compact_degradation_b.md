---
title: "测试：compact Phase B 降级"
rounds: 2
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 赞成方
    model: gpt-4o-mini
    style: 赞成人工智能全面应用
  - name: 反对方
    model: gpt-4o-mini
    style: 对人工智能全面应用持谨慎态度
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
    赞成方:
      1: "人工智能能大幅提升各行业效率，是技术进步的必然方向。"
      2: "综上，AI 的效率提升和创新能力使其全面应用利大于弊。"
    反对方:
      1: "人工智能全面应用存在伦理风险和就业冲击，需要谨慎推进。"
      2: "总结：技术发展应以人为本，AI 应用须有明确边界和监管。"
  judge: "裁定：双方各有道理，但反对方的风险提醒值得重视。"
  compact:
    phase_a: '{"topic":{"current_formulation":"人工智能是否应全面应用","notes":null},"axioms":["双方均承认AI具有变革潜力"],"disputes":[{"id":"D1","title":"AI全面应用的利弊","status":"open","positions":{"赞成方":"利大于弊","反对方":"需要谨慎"},"resolution":null}],"pruned_paths":[]}'
    phase_b:
      赞成方:
        - "这不是合法JSON第一次失败"
        - '{"name":"赞成方","active":true,"stance_version":1,"stance":"支持AI全面应用。大幅提升效率，推动创新。","core_claims":[{"id":"C1","text":"AI提升行业效率","status":"active"}],"key_arguments":[{"id":"A1","claim_id":"C1","text":"自动化减少人工成本","status":"active"}],"abandoned_claims":[]}'
      反对方:
        - "也不是合法JSON"
        - '{"name":"反对方","active":true,"stance_version":1,"stance":"谨慎推进AI应用。存在伦理和就业风险。","core_claims":[{"id":"C1","text":"AI存在伦理风险","status":"active"}],"key_arguments":[{"id":"A1","claim_id":"C1","text":"算法偏见可能加剧不公","status":"active"}],"abandoned_claims":[]}'
    validity_check:
      - "NO"
      - "YES"
    drift_check:
      - "DEFECTION\n立场发生了根本性倒转，需要修正。"
      - "REFINEMENT\n合理细化，立场未发生根本倒转。"
---

人工智能是否应当全面应用于社会各领域？请从效率、伦理、就业三方面讨论。
