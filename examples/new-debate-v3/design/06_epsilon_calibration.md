# 模块名：Epsilon 校准（Epsilon Calibration / scoring_epsilon）

<!-- import from 00_shared_types: RegulativeAxis, AxisScoreEntry, EvidenceAtom, QuestionFrame -->

## 一句话定位

维护每个评估轴的测量不确定性（`epsilon`），通过指数移动平均（EMA）在每个 epoch 后动态更新，并在 PA 节点使用 epsilon 进行"有意义差异"判断——防止系统把统计噪声当成真实的证据信号进行终止。

---

## 通俗解释

想象你在追踪一场马拉松比赛的实时配速。每次更新都有测量误差：GPS 精度、记录延迟等。如果你的仪器精度是 ±30 秒/公里，那么两次读数差 10 秒并不意味着选手真的加速了——那在误差范围内。

Epsilon 就是这个"仪器精度"的量化。对于每个评估轴（如"经济效率"），epsilon 告诉我们：分数差小于 epsilon 时，不能认为两轮结果"真的不同"。PA 节点用 epsilon 判断排名是否真正稳定，scoring_termination 用它决定要不要停止迭代。

每轮新证据进来，epsilon 会根据实际观测的评分波动（EMA）自动更新——证据越多越稳定，epsilon 会收紧；来了矛盾证据，epsilon 会放大。

---

## 接口定义（TypeScript 类型）

```typescript
// import from 00_shared_types: RegulativeAxis, AxisScoreEntry

interface EpsilonState {
  axis_id: string;
  current_epsilon: number;    // ∈ [min_epsilon, max_epsilon]
  min_epsilon: number;        // 下限，默认 0.01
  max_epsilon: number;        // 上限，默认 0.15
  ema_alpha: number;          // EMA 学习率（注意：区别于 score_alpha！）
                              // ema_alpha 控制 epsilon 的更新速率
  epoch_count: number;        // 已经参与更新的 epoch 数量
  last_scores: number[];      // 最近 N 个 epoch 的 axis_score（用于计算 variance）
  confidence_level: number;   // t-分布置信水平，默认 0.95
}

interface EpsilonUpdateInput {
  axis_id: string;
  new_score: number;          // 本 epoch 的 axis_score
  prev_score: number;         // 上一 epoch 的 axis_score
  evidence_count: number;     // 本 epoch 的 EvidenceAtom 数量
}

// 更新函数（每 epoch 末调用）
function update_epsilon(
  state: EpsilonState,
  input: EpsilonUpdateInput
): EpsilonState;

// 差异判断（PA 节点调用）
function is_meaningful_change(
  score_a: number,
  score_b: number,
  epsilon: number
): boolean;

// 批量更新所有轴（layer 1 调度）
function update_all_epsilons(
  states: Record<string, EpsilonState>,
  axis_scores_by_epoch: AxisScoreEntry[],
  prev_axis_scores: AxisScoreEntry[]
): Record<string, EpsilonState>;
```

---

## 伪代码实现（Python 风格）

```python
# 常量
MIN_EPSILON_FLOOR = 0.01    # 最小可能的 epsilon（防止过度收紧）
MAX_EPSILON_CEIL  = 0.15    # 最大可能的 epsilon
DEFAULT_EMA_ALPHA = 0.2     # EMA 学习率：越小越稳定，越大越敏感
                             # 注意：这是 ema_alpha，不是 score_alpha！
DEFAULT_CONFIDENCE = 0.95
HISTORY_WINDOW = 5          # 保留最近 N 个 epoch 的历史分数


def update_epsilon(
    state: EpsilonState,
    input: EpsilonUpdateInput
) -> EpsilonState:
    """
    每个 epoch 末更新单个轴的 epsilon。
    使用 EMA 追踪实际分数变动的指数加权移动平均。
    """
    # Step 1: 计算本轮实际变动量（绝对值）
    delta = abs(input.new_score - input.prev_score)

    # Step 2: EMA 更新 epsilon
    # epsilon_t = alpha * delta + (1 - alpha) * epsilon_{t-1}
    new_epsilon_raw = (
        state.ema_alpha * delta +
        (1 - state.ema_alpha) * state.current_epsilon
    )

    # Step 3: 应用证据数量修正因子（证据越多，epsilon 应该越小）
    evidence_factor = 1.0 / math.sqrt(max(1, input.evidence_count))
    adjusted_epsilon = new_epsilon_raw * evidence_factor

    # Step 4: 应用 t-分布置信区间修正
    # 如果历史数据足够，可以用样本方差更精确地估计 epsilon
    if state.epoch_count >= 3:
        history = state.last_scores + [input.new_score]
        if len(history) > HISTORY_WINDOW:
            history = history[-HISTORY_WINDOW:]

        variance = statistics.variance(history) if len(history) > 1 else 0
        std_dev = math.sqrt(variance)

        # t-分布修正（自由度 = epoch_count - 1）
        df = state.epoch_count - 1
        t_critical = scipy_t_critical(state.confidence_level, df)  # 近似：1.96 for 95%
        t_based_epsilon = t_critical * std_dev / math.sqrt(state.epoch_count)

        # 取最大值（保守估计）
        adjusted_epsilon = max(adjusted_epsilon, t_based_epsilon)

    # Step 5: 钳位到 [min, max] 范围
    final_epsilon = max(state.min_epsilon, min(state.max_epsilon, adjusted_epsilon))

    # Step 6: 更新状态
    new_history = state.last_scores + [input.new_score]
    if len(new_history) > HISTORY_WINDOW:
        new_history = new_history[-HISTORY_WINDOW:]

    return EpsilonState(
        axis_id=state.axis_id,
        current_epsilon=final_epsilon,
        min_epsilon=state.min_epsilon,
        max_epsilon=state.max_epsilon,
        ema_alpha=state.ema_alpha,
        epoch_count=state.epoch_count + 1,
        last_scores=new_history,
        confidence_level=state.confidence_level
    )


def is_meaningful_change(
    score_a: float,
    score_b: float,
    epsilon: float
) -> bool:
    """
    判断两个分数之间的差是否超过测量不确定性范围。
    PA 节点用此函数判断"排名是否真正改变了"。
    """
    return abs(score_a - score_b) > epsilon


def update_all_epsilons(
    states: dict[str, EpsilonState],
    current_axis_scores: list[AxisScoreEntry],
    prev_axis_scores: list[AxisScoreEntry]
) -> dict[str, EpsilonState]:
    """批量更新所有轴的 epsilon（Layer 1 调度层在每 epoch 末调用）"""
    prev_by_axis = {as_.axis_id: as_.score for as_ in prev_axis_scores}
    updated_states = {}

    for score_entry in current_axis_scores:
        axis_id = score_entry.axis_id
        state = states.get(axis_id)

        if state is None:
            # 初始化新轴的 epsilon 状态
            state = EpsilonState(
                axis_id=axis_id,
                current_epsilon=0.10,   # 初始高不确定性
                min_epsilon=MIN_EPSILON_FLOOR,
                max_epsilon=MAX_EPSILON_CEIL,
                ema_alpha=DEFAULT_EMA_ALPHA,
                epoch_count=0,
                last_scores=[],
                confidence_level=DEFAULT_CONFIDENCE
            )

        prev_score = prev_by_axis.get(axis_id, score_entry.score)  # 首次则 delta=0
        evidence_count = len([e for e in score_entry.evidence_ids])

        updated = update_epsilon(
            state=state,
            input=EpsilonUpdateInput(
                axis_id=axis_id,
                new_score=score_entry.score,
                prev_score=prev_score,
                evidence_count=evidence_count
            )
        )
        updated_states[axis_id] = updated

    # 保留当前未出现新分数的轴（保持原有状态）
    for axis_id, state in states.items():
        if axis_id not in updated_states:
            updated_states[axis_id] = state

    return updated_states


def initialize_epsilon_states(frame: QuestionFrame) -> dict[str, EpsilonState]:
    """在 QuestionFrame 建立时初始化所有轴的 epsilon 状态"""
    return {
        ax.axis_id: EpsilonState(
            axis_id=ax.axis_id,
            current_epsilon=ax.epsilon,   # 使用 QuestionFrame 中的初始值（通常为 0.10）
            min_epsilon=MIN_EPSILON_FLOOR,
            max_epsilon=MAX_EPSILON_CEIL,
            ema_alpha=DEFAULT_EMA_ALPHA,
            epoch_count=0,
            last_scores=[],
            confidence_level=DEFAULT_CONFIDENCE
        )
        for ax in frame.evaluation_axes
    }
```

---

## 关键约束与不变式

| 编号 | 约束 | 强制方式 |
|------|------|----------|
| INV-EP-01 | `epsilon ∈ [min_epsilon, max_epsilon]`（默认 [0.01, 0.15]） | 钳位操作 |
| INV-EP-02 | `ema_alpha ∈ (0, 1)`，表示 epsilon 学习率；**不是** `score_alpha`（评分缩放因子） | 命名区分 |
| INV-EP-03 | `score_alpha`（评分缩放因子，在 PA 节点）与 `ema_alpha` 是不同参数，不得混用 | GAP-5，见下方 |
| INV-EP-04 | `epoch_count` 从 0 开始单调递增，续跑时不重置（与 epoch_id 联动） | 状态持久化 |
| INV-EP-05 | `last_scores` 窗口大小 = 5，超出时丢弃最旧的 | 滑动窗口 |
| INV-EP-06 | `is_meaningful_change()` 返回 `false` 表示变化在误差范围内，不能触发排名变更计数器重置 | PA 节点调用约定 |
| INV-EP-07 | `update_epsilon()` 是纯函数（返回新状态而非修改原状态），便于 snapshot 序列化 | 函数式设计 |

---

## 具体样例：走一遍完整流程

**贯穿样例问题**："如何设计一个公平的碳排放交易机制？"，聚焦 `ax_burden_share` 轴

### 初始状态

```
EpsilonState(ax_burden_share):
  current_epsilon: 0.10    ← 初始值（高不确定性）
  min_epsilon: 0.01
  max_epsilon: 0.15
  ema_alpha: 0.2
  epoch_count: 0
  last_scores: []
```

### Epoch 1 更新

```
axis_score (epoch 1): 0.849
prev_score: 0.849  (首次，delta = 0)
evidence_count: 3

Step 1: delta = |0.849 - 0.849| = 0.0
Step 2: new_epsilon_raw = 0.2 × 0.0 + 0.8 × 0.10 = 0.080
Step 3: evidence_factor = 1/√3 ≈ 0.577
        adjusted = 0.080 × 0.577 = 0.046
Step 4: epoch_count=0 < 3，跳过 t-分布修正
Step 5: 钳位：max(0.01, min(0.15, 0.046)) = 0.046

EpsilonState after epoch 1:
  current_epsilon: 0.046
  epoch_count: 1
  last_scores: [0.849]
```

### Epoch 2 更新（新证据改变了分数）

```
axis_score (epoch 2): 0.781   ← 新的反向证据进来，分数下降
prev_score: 0.849
evidence_count: 5

Step 1: delta = |0.781 - 0.849| = 0.068
Step 2: new_epsilon_raw = 0.2 × 0.068 + 0.8 × 0.046 = 0.0136 + 0.0368 = 0.0504
Step 3: evidence_factor = 1/√5 ≈ 0.447
        adjusted = 0.0504 × 0.447 = 0.0225
Step 4: epoch_count=1 < 3，跳过
Step 5: 钳位：0.0225 → 在 [0.01, 0.15] 内 → 0.0225

EpsilonState after epoch 2:
  current_epsilon: 0.0225
  epoch_count: 2
  last_scores: [0.849, 0.781]
```

### PA 节点调用 is_meaningful_change()

```
score_epoch1 = 0.849
score_epoch2 = 0.781
epsilon = 0.0225

is_meaningful_change(0.849, 0.781, 0.0225):
  |0.849 - 0.781| = 0.068 > 0.0225
  → True（变化超过测量不确定性，排名变更计数器重置）
```

### 如果两轮分数差仅 0.01

```
is_meaningful_change(0.849, 0.859, 0.0225):
  |0.849 - 0.859| = 0.010 < 0.0225
  → False（变化在误差范围内，排名计数器不重置，系统认为这轮"稳定"）
```

---

## ✅ 已裁定缺口（原设计缺口）

> **~~GAP-5~~** → **已裁定** ✅（完整裁定见 `08_scoring_termination.md`）
> - 裁定结论：`ema_alpha`（epsilon 学习率，本模块）与 `score_alpha`（评分缩放因子，PA 节点）全代码库严格区分命名；配置 schema 中键名也必须不同；系统在 epoch 0 配置全量校验时，若同名配置出现，校验器必须报 FATAL（参见 GAP-5 配置校验分层规格）。
> - 裁定来源：`gap_type_consolidation_debate_summary.md`
