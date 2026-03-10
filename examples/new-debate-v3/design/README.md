# v3 认知引擎 设计文档

> 本目录包含 v3 认知引擎的完整模块设计，由 12 次辩论裁定文档（`*_debate_summary.md`）综合提炼而成。
> 贯穿样例问题：**"如何设计一个公平的碳排放交易机制？"**

---

## 架构概览

v3 引擎采用双层（Layer 1 / Layer 2）分工架构。Layer 1 负责问题解析、假说生成和调度控制（状态机），Layer 2 负责单个假说的深度证据验证和评分。两层通过严格类型化的 `L2Return`（增量事件流）通信，Layer 1 通过 `applyDelta` 纯函数将增量吸收到 `L1State`。

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Layer 1 状态机                              │
│                                                                     │
│  ProblemStatement                                                   │
│       │                                                             │
│  [QN] normalize_question()                                          │
│       │ QuestionFrame                                               │
│  [MB] macro_breadth()                                               │
│       │ HypothesisDraft[]                                           │
│  [CC] clarity_compile()                                             │
│       ├── TestableClaim[] ───────────────────────────────────────┐  │
│       └── RegulativeIdea[] ─────────────────────────────────┐    │  │
│                                                             │    │  │
│                                                          [RB]    │  │
│                                                             │    │  │
│                                            ┌────────────────┘    │  │
│                                            ▼                     ▼  │
│                                       ┌──────────────────────────┐ │
│                                       │     Layer 2 (D2 节点)    │ │
│                                       │  EvidenceAtom 收集 (S4)  │ │
│                                       │  AxisScore 计算  (S5)    │ │
│                                       └────────────┬─────────────┘ │
│                                                    │ L2Return       │
│                                            applyDelta()             │
│                                                    │ L1State'       │
│  [PA] compute_rankings()                           │                │
│       check_termination() ◄────────────────────────┘               │
│       │                                                             │
│       ├── should_terminate=false → [RB] repair()                   │
│       │                                     │ HypothesisDraft[]    │
│       │                         (repair 草稿进入下一 epoch 的 CC)   │
│       │                                                             │
│       └── should_terminate=true → [AS] assemble_answer_seed()      │
│                                         │ AnswerSeed               │
│                                         ▼                          │
│                                    最终输出                         │
└─────────────────────────────────────────────────────────────────────┘

关键数据类型流：
  QuestionFrame ──► HypothesisDraft ──► TestableClaim ──► EvidenceChain
  ──► VerifiedClaim(Full→Compressed) ──► RankedClaim ──► AnswerSeed
```

---

## 模块地图

| 文件 | 对应 Python 模块 | 核心类型 | 状态 |
|------|----------------|---------|------|
| `00_shared_types.md` | `types.py` | `QuestionFrame`, `HypothesisDraft`, `GapSpec`, `EvidenceAtom`, `L2Return/EpochDelta` | ✅ 完整 |
| `01_question_ingestion.md` | `question_ingestion.py` | `normalize_question()`, `detect_category_errors()`, `NormalizeError` | ✅ 完整 |
| `02_hypothesis_draft.md` | `hypothesis_draft.py` | `HypothesisDraft`, `normalize_mb()`, `normalize_repair()`, `is_homologous()` | ✅ 完整 |
| `03_macro_breadth.md` | `macro_breadth.py` | `macro_breadth()`, `TensionCandidate`, `MacroBreadthError` | ✅ GAP-6 已裁定 |
| `04_claim_compiler.md` | `claim_compiler.py` | `clarity_compile()`, `CompileResult`, `RegulativeIdea` | ✅ GAP-6/8 已裁定 |
| `05_layer2_evidence.md` | `layer2_evidence.py` | `run_layer2_verification()`, `EvidenceChain`, `AxisScoreEntry` | ✅ GAP-7 已裁定 |
| `06_epsilon_calibration.md` | `epsilon_calibration.py` | `update_epsilon()`, `is_meaningful_change()`, `EpsilonState` | ✅ 完整 |
| `07_repair_strategy.md` | `repair_strategy.py` | `repair()`, `is_unsat()`, `NegativeConstraint`, `RepairOutput` | ✅ GAP-1/2/4 已裁定 |
| `08_scoring_termination.md` | `scoring_termination.py` | `check_termination()`, `compute_rankings()`, `TerminationDecision` | ✅ GAP-2/5 已裁定 |
| `09_context_compression.md` | `context_compression.py` | `compress_evidence_chain()`, `CompressedEvidenceProfile`, `rehydrate_evidence()` | ✅ GAP-7 已裁定 |
| `10_resume_mechanism.md` | `resume_mechanism.py` | `EngineSnapshot`, `apply_intervention()`, `InterventionFile` | ✅ GAP-3 已裁定 |
| `11_layer1_orchestrator.md` | `layer1_orchestrator.py` | `Layer1Orchestrator.run_epoch()`, `apply_delta()`, `assemble_answer_seed()` | ✅ GAP-3/6/8 已裁定 |

---

## 已知缺口索引

| 编号 | 名称 | 状态 | 所在文件 | 裁定结论（一句话） |
|------|------|------|---------|------|
| GAP-1 | `L2Return` 两版本冲突 | ✅ 已裁定 | `07_repair_strategy.md`、`11_layer1_orchestrator.md` | 采纳增量事件流 `deltas`，`evidence_summary` 从 L2Return 永久移除，上下文投影由 L1 侧纯函数 `project_evidence_summary` 完成。 |
| GAP-2 | `GapSpec.kind` 枚举不兼容 | ✅ 已裁定 | `07_repair_strategy.md`、`08_scoring_termination.md` | 采纳 Tagged Union 按来源域分离（`REPAIR` / `TERMINATION`），L2 只产 REPAIR 类，PA 只产 TERMINATION 类，由类型系统在创建点强制约束。 |
| GAP-3 | `AnswerSeed`（AS 节点）接口缺失 | ✅ 已裁定 | `10_resume_mechanism.md`、`11_layer1_orchestrator.md` | AnswerSeed 是 tagged union（`ANSWER_SEED \| ANSWER_SEED_SKIPPED`），`assemble_answer_seed(state: L1State): AnswerSeed` 为唯一签名，coverage 二值化。 |
| GAP-4 | `HypothesisDraft` 旧版与统一类型不符 | ✅ 已裁定 | `07_repair_strategy.md` | 评估轴配置在 epoch 0 冻结为不可变快照，运行时轴变更通过 `SCHEMA_CHALLENGE_NEW` + PA 审批产生新快照，轴修改是状态机事件而非热更新。 |
| GAP-5 | `alpha` 符号歧义 | ✅ 已裁定 | `06_epsilon_calibration.md`、`08_scoring_termination.md` | 配置在 epoch 0 全量校验，结构性错误 FATAL 拒绝启动，未知字段 `warn + strip` 降级运行；`ema_alpha` 与 `score_alpha` 严格区分命名。 |
| GAP-6 | RB 节点函数签名缺失 | ✅ 已裁定 | `03_macro_breadth.md`、`04_claim_compiler.md`、`11_layer1_orchestrator.md` | 规则预筛 + LLM 提取代理变量两阶段，novelty 由外部纯函数（Jaccard）计算，失败路径写入 `L1State.rb_reject_log`。 |
| GAP-7 | `VerifiedClaim` 两版本转换边界不明 | ✅ 已裁定 | `05_layer2_evidence.md`、`09_context_compression.md` | `apply_delta` 保持纯函数只入库 `VerifiedClaimFull`，压缩为异步后台任务，业务代码通过 accessor `get_evidence` 访问并获得显式可用性标记。 |
| GAP-8 | D2 节点入口类型和分派逻辑未裁定 | ✅ 已裁定 | `04_claim_compiler.md`、`11_layer1_orchestrator.md` | D2 只注入索引句柄 `EvidenceRef`（不携带 EvidenceChain 正文），历史视图是只读投影不持久化，`build_verification_context` 从 L1State 提取索引。 |

---

## 数据流图

从 `QuestionFrame` 到 `AnswerSeed` 的完整数据流：

```
ProblemStatement
    │
    ▼ normalize_question() → NormalizeError（可恢复/不可恢复）
QuestionFrame
  ├─ evaluation_axes: RegulativeAxis[]   (weight, epsilon, falsifier)
  ├─ open_terms: string[]                (精炼回路单调递减)
  └─ stakeholders: string[]
    │
    ▼ macro_breadth()
HypothesisDraft[]
  ├─ claim_sketch: string
  ├─ scope_ref: string[]                 (禁止空数组)
  ├─ tension_source: { kind, tier }      (分层：INTERNAL_AXIS / EMPIRICAL)
  └─ provenance: { source, ttl?, repair_stage? }
    │
    ▼ clarity_compile() [CC 节点]
    ├── TestableClaim[]
    │     ├─ falsifiable_statement
    │     ├─ falsifier
    │     └─ verification_plan.verifier_type
    └── RegulativeIdea[]
          └─ no_empirical_bridge_reason
    │
    ▼ run_layer2_verification() [D2 节点，Layer 2]
EvidenceChain
  ├─ atoms: EvidenceAtom[]              (每个 atom 绑定唯一 axis_id)
  └─ axis_scores: AxisScoreEntry[]      (sigmoid 折算，epsilon 校准)
    │
    ▼ applyDelta() [L2Return → L1State]
L2Return: { epoch_id, deltas: EpochDelta[] }
  EpochDelta:
    GAP_OPEN/PATCH/CLOSE
    CLAIM_VERIFIED → VerifiedClaimFull
    CLAIM_SUSPENDED
    SCHEMA_CHALLENGE_NEW
    │
    ▼ [压缩触发后] compress_evidence_chain()
VerifiedClaimCompressed
  ├─ evidence_profiles: Record<AxisId, CompressedEvidenceProfile>
  │     ├─ counts_pro/con: Record<StrengthTier, number>
  │     ├─ watermarks_pro/con: Record<StrengthTier, EvidenceAtom | null>
  │     └─ pinned_conflicts: PinnedConflict[]
  └─ active_window: EvidenceAtom[]
    │
    ▼ compute_rankings() + update_epsilon() [PA 节点]
RankedClaim[]
  ├─ score: number                       (加权投影，score_alpha 缩放)
  └─ coverage: number                    (已覆盖轴权重之和)
    │
    ├── check_termination() = false → repair() [RB 节点]
    │       ├─ is_unsat(): AST 哈希负向约束（纯函数，不经 LLM）
    │       └─ normalize_repair() → HypothesisDraft → 回到 CC
    │
    └── check_termination() = true
          │
          ▼ assemble_answer_seed() [AS 节点]
AnswerSeed
  ├─ top_claims: RankedClaim[]
  ├─ coverage_report: Record<AxisId, number>
  ├─ integrity_status: "CLEAN" | "DEBUG_OVERRIDE_APPLIED"
  └─ termination_reason: string
```

---

## 实现顺序建议

根据模块依赖拓扑，推荐按以下顺序实现：

```
第 1 阶段（基础设施）：
  1. 00_shared_types.md → types.py（所有类型定义）
  2. 06_epsilon_calibration.md → epsilon_calibration.py（纯函数，无依赖）
  3. 02_hypothesis_draft.md → hypothesis_draft.py（normalize_mb/repair、is_homologous）

第 2 阶段（Layer 1 前段）：
  4. 01_question_ingestion.md → question_ingestion.py（QN 节点）
  5. 03_macro_breadth.md → macro_breadth.py（MB 节点）
  6. 04_claim_compiler.md → claim_compiler.py（CC 节点）

第 3 阶段（Layer 2）：
  7. 05_layer2_evidence.md → layer2_evidence.py（S4/S5，证据收集 + 评分）
  8. 09_context_compression.md → context_compression.py（压缩 + 再水合）

第 4 阶段（Layer 1 后段）：
  9. 07_repair_strategy.md → repair_strategy.py（RB 节点，depends on L1State）
  10. 08_scoring_termination.md → scoring_termination.py（PA 节点）
  11. 10_resume_mechanism.md → resume_mechanism.py（快照/干预/续跑）
  12. 11_layer1_orchestrator.md → layer1_orchestrator.py（主调度循环，集成所有模块）

注：GAP-3（AnswerSeed 接口）和 GAP-8（D2 分派逻辑）在实现第 12 步时必须补充完整。
```

---

## 快速参考：关键数值配置

| 参数名 | 所在模块 | 默认值 | 说明 |
|--------|---------|--------|------|
| `max_drafts` | MB | 6 | 每 epoch 最多草稿数 |
| `internal_tier_quota` | MB | 0.5 | 内部层（INTERNAL_AXIS）配额比例 |
| `max_hot_atoms_per_claim` | Compression | 50 | 每 claim 热区 atom 上限 |
| `max_total_atoms_per_claim` | Compression | 200 | 每 claim 总 atom 上限 |
| `ema_alpha` | Epsilon | 0.2 | epsilon EMA 学习率（不是 score_alpha！） |
| `score_alpha` | PA | 1.0 | 评分缩放因子（不是 ema_alpha！） |
| `hysteresis_rounds` | PA | 2 | 排名稳定所需连续轮次 |
| `min_coverage` | PA | 0.70 | 终止所需最低覆盖率 |
| `max_refinement_epochs` | QN | 3 | 精炼回路最大轮次 |
| `consecutive_unsat_limit` | Repair | 5 | 被 is_unsat() 连续拦截次数上限 |
| `max_attempts_per_stage` | Repair | 8 | 每阶段最大修复尝试次数 |
| `L2Return_max_size_bytes` | Orchestrator | 32768 | L2Return 大小上限（超出拒收） |
