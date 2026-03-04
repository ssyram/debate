# debate-tool v2 辩论机制改进路线图

> 来源：辩论机制元辩论（2026-03-04），5 辩手 × 3 轮 + 裁判裁定

---

## P0 — 必须实现

### 1. 分歧合约 + 分歧度门槛 + 失败重写

**问题**：同模型 × N + style 太弱导致 5/5 收敛统一结论（"伪辩论"）。

**方案**：
- 立场由规则/stance 分配生成，辩手输出携带强制 JSON 结构：
  - `claim_id`、`claims[]`、`opposed_claims[]`（至少 2 条反对主流）
  - `nonnegotiables[]`（至少 1 条不可妥协）、`failure_conditions[]`
  - `evidence[]/quotes[]`、`questions_to_others[]`
- R1 后做 embedding 相似度 / 聚类检测：
  - `avg_cos > 0.85` 或 `top_cluster_ratio > 0.6` → 触发 `retry_round1`
  - 重写 prompt 追加"与簇中心互斥的替代路径 + 失败条件 + 反对论据"

### 2. 最小串行质询子回合

**问题**：并行发言导致交锋延迟一整轮、锁死共识。

**方案**（`cross_exam=true` 或 deep 模式）：
- R1：并行 `asyncio.gather()`（短输出、结构化）
- R1.5：串行 `for (asker, target) in pairs: await call()` 生成质询
  - 必须引用 `claim_id/quote`，缺失则 retry
- R2：并行答辩，强制逐条回答收到的问题并可修正方案
- 终局裁判

**预期影响**：wall-time +20~40%，交锋质量显著提升。

### 3. Auto 模式 + Baseline Gate + 早停

**问题**：16 次 API 调用、5 分钟、5/5 趋同 — 对确定性议题过度辩论。

**方案**：
- **Auto gate**（默认模式）：
  - Step0：先跑 `single_multi_persona` baseline（1 次调用）
  - 本地解析 baseline：冲突数/约束数/风险词命中/置信度
  - 决定直接输出 or 升级到 fast/standard/deep
- **早停机制**：
  - 每轮后本地计算新信息率 / 主张相似度 / Jaccard
  - 达到收敛阈值立即进入裁判（跳过剩余轮次）
- **三档预设**：
  - fast：3 辩手 × 2 轮、无质询、早停开
  - standard：5 辩手 × 2 轮、可选质询
  - deep：5 辩手 + 质询 + 可选中场追问

### 4. 裁判输出强制结构化 Schema

**问题**：12000 字信息过载、用户仍需人工提取任务、60% 批注为修正。

**方案**：
- 裁判输出强制机器可读 Schema（YAML/JSON），字段至少含：
  - `action`、`confidence`、`acceptance_criteria`
  - `source_claim_ids[]`、`blockers/risks[]`
  - `effort`（可选）、`assignee`（可选）
- Pydantic/JSON schema 校验，失败自动 retry
- 零新增调用、直接可导入项目管理工具

---

## P1 — 应做

### 5. Claims 账本替代 1200 字截断

**问题**：裁判读取压缩版截断到每人 1200 字，丢失关键论据链。

**方案**：
- 落盘 `claims.jsonl`（每轮/每人一条记录，含 `claim_id` 与 `quote_span` 回链指针）
- 裁判默认只读 `claims.jsonl`（而非截断全文）
- 必要时按 `quote_span` 从本地全文检索片段拼入裁判上下文（不额外 LLM 调用）

### 6. 可选中场裁判追问

- 裁判可在中间轮对特定辩手提出追问
- 提升收敛质量但会加调用，作为可选配置

---

## P2 — 可选

### 7. 异构模型 `model_pool`

- 支持多供应商 model pool 配置
- P0 机制稳定后再接入多供应商，避免先增加运维复杂度而收益不确定

### 8. 多裁判交叉评审

- 多个裁判独立评审后综合裁决
- 降低单裁判偏见风险

---

## 配置字段扩展（预览）

```yaml
# topic.yaml 新增字段
mode: auto|fast|standard|deep
auto_gate:
  min_conflicts: 2
  min_constraints: 3
  risk_keywords: [安全, 性能, 兼容]
  min_risk_hits: 2
  confidence_threshold: 0.8
divergence_check:
  metric: cosine|jaccard
  threshold: 0.85
  cluster_ratio: 0.6
  retry: 1
cross_exam: true|false
output_schema: actionable
debater_roles:
  - stance: "反对派"
  - stance: "支持派"
  - stance: "平衡派"
```

## 辩手输出 JSON 结构（预览）

```json
{
  "claim_id": "d1_r1_c1",
  "claims": ["主张1", "主张2"],
  "opposed_claims": ["反对主流的论点1", "反对主流的论点2"],
  "nonnegotiables": ["不可妥协的底线"],
  "failure_conditions": ["方案失败的条件"],
  "evidence": [{"quote_id": "q1", "text": "引用原文"}],
  "questions_to_others": ["对辩手X的质疑"]
}
```

## 裁判输出 Schema（预览）

```yaml
decisions:
  - action: "统一入口点为 debate-tool CLI"
    confidence: 0.92
    source_claim_ids: [d1_r1_c1, d3_r2_c2]
    acceptance_criteria:
      - "python -m debate_tool run 可正常执行"
      - "旧入口 debate.py 返回退出码 2"
    blockers: []
    risks:
      - "依赖 pyproject.toml entry_points 的用户需重新安装"
    effort: "P0"
```
