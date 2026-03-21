# debate-tool 端到端测试

## 概览

`test/test.py` 是一个自包含的端到端集成测试套件，通过 **内置 Mock Server** 完全离线运行 debate-tool 的所有功能路径，无需真实 LLM API。

测试覆盖 **58 个场景**，涵盖 62 个特性维度：

| 系列 | 数量 | 说明 |
|------|------|------|
| RUN | 13 | 正常运行（basic、cross_exam、cot、constraints 等） |
| RESUME | 10 | 续跑（message、guide、judge_only、add/drop debater 等） |
| COMPACT | 10 | 日志压缩（全量、幂等性、keep-last、resume chain 等） |
| DEGRADATION | 2 | 降级重试（Phase A/B 失败→重试→成功） |
| CANARY | 3 | 金丝雀 prompt 注入验证（constraints、message、guide） |
| ERROR | 12 | 错误场景（缺少文件、非法参数、--force 校验等） |
| NEW | 8 | version、early_stop、drop_debater、modify 系列 |

## 快速开始

```bash
# 运行全部测试（Mock 模式，无需 API key）
python3 test/test.py

# 静默模式（不打印子进程实时输出）
python3 test/test.py --quiet

# 仅运行快速测试（dry_run + error 系列，秒级完成）
python3 test/test.py --quick

# 按名称过滤
python3 test/test.py --filter basic,cross_exam

# 生成/更新 golden 文件
python3 test/test.py --generate-golden

# 真实 LLM 模式（需要 API key）
source .local/.env && python3 test/test.py --real-llm-test
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--quick` | 仅运行无 API 测试（dry_run + error 系列） |
| `--filter <name>` | 按名称过滤（逗号分隔，模糊匹配） |
| `--quiet` | 不实时打印子进程 stdout/stderr |
| `--keep-workdir` | 测试后保留 workdir（调试用） |
| `--no-cleanup` | 保留金丝雀测试临时文件 |
| `--generate-golden` | 生成/更新 golden 参考文件 |
| `--real-llm-test` | 运行需要真实 LLM 的测试 |

### 输出格式

```
YES  test_name (1.2s) — 说明 | ✓feature1 ✓feature2
NO   test_name (0.3s) — 失败原因
```

- **YES** = 预期成功且成功 / 预期失败且失败
- **NO** = 预期成功却失败 / 预期失败却成功

## 架构

### 目录结构

```
test/
├── test.py              # 测试主文件（入口 + 所有测试函数 + 注册表）
├── mock_server.py       # Mock HTTP 服务器（OpenAI 兼容 API）
├── mock_routes.py       # 路由表（从 topic 文件 YAML 解析 mock_responses）
├── golden_compare.py    # Golden 文件对比工具（归一化时间戳/URL/key）
├── structural_checks.py # 结构性断言（辩手数、轮数、cross_exam 位置等）
├── topics/              # 测试用 topic 文件（含 mock_responses YAML）
│   ├── basic.md
│   ├── cross_exam.md
│   ├── cot.md
│   ├── ...
│   └── error/           # 错误场景 topic
│       ├── bad_yaml.md
│       └── one_debater.md
├── resume_topics/       # Resume 测试用的 topic 覆盖文件
│   ├── add_debater.md
│   ├── drop_debater.md
│   ├── override_config.md
│   └── ...
├── golden/              # Golden 参考文件（"标准答案"）
│   ├── run/             # RUN 系列
│   │   ├── basic_debate_log.json
│   │   ├── basic_debate_summary.md
│   │   └── ...
│   ├── resume/          # RESUME 系列
│   │   ├── resume_basic_debate_log.json
│   │   └── ...
│   └── compact/         # COMPACT 系列
│       └── compact_all_debate_log.json
└── workdir/             # 运行时临时目录（测试后自动清理）
```

### 执行流程

```
test.py main()
  │
  ├─ 启动 Mock Server（监听随机端口）
  │    └─ mock_routes.load_routes() 扫描 topics/*.md + resume_topics/*.md
  │         解析 YAML front-matter 中的 mock_responses 字段
  │         构建路由表：debater/judge/cx/compact → 固定应答
  │
  ├─ 创建 workdir/（每次全新）
  │
  ├─ 按序执行 ALL_TESTS 列表中的测试函数
  │    每个测试函数：
  │    1. 调用 debate_cmd() → subprocess 运行 `python -m debate_tool <command>`
  │       - 环境变量 DEBATE_BASE_URL 指向 Mock Server
  │    2. 检查 returncode
  │    3. 加载输出日志 JSON，执行结构性检查（structural_checks.py）
  │    4. 与 golden 文件对比（golden_compare.py）
  │    5. 返回 TestResult(passed=True/False)
  │
  ├─ 打印汇总（YES/NO 计数、特性覆盖率）
  │
  └─ 清理 workdir/（全部通过时自动删除）
```

## Mock Server

Mock Server 是一个轻量级 HTTP 服务器，模拟 OpenAI Chat Completions API（`/v1/chat/completions`）和 Embeddings API（`/v1/embeddings`）。

### 工作原理

1. **启动**：`start_mock_server()` 在随机端口启动 `HTTPServer`，返回 `MockServerHandle`
2. **路由加载**：`mock_routes.load_routes()` 扫描所有 topic 文件的 `mock_responses` YAML 字段
3. **请求匹配**：每个请求的 system prompt 被分类（`_classify()`），然后查表返回固定应答
4. **请求录制**：所有请求记录到 `handle.requests` 列表，供测试断言使用

### 路由分类

Mock Server 通过 system prompt 中的关键字判断请求类型：

| 分类 | 关键字 | 应答来源 |
|------|--------|----------|
| `debater` | `你是「{name}」，风格为「{style}」。第 {rnd} 轮` | `_debater_table[(name, round)]` |
| `debater_cot` | 同上 + `<thinking>` | `_cot_table` + `_debater_table` |
| `judge` | `你是辩论裁判（{name}）` | `_judge_table[first_debater]` |
| `cx_select` | `选择一个要质询的对象` | `_cx_select_table[questioner]` |
| `cx_question` | `质询环节` | `_cx_questions_table[questioner]` |
| `compact.phase_a` | `辩论状态提取器` | `_compact_phase_a_table` |
| `compact.phase_b` | `立场追踪器` | `_compact_phase_b_table` |
| `compact.validity_check` | `辩论立场校验器` | `_compact_validity_table` |
| `compact.drift_check` | `辩论立场漂移检查器` | `_compact_drift_table` |

### 未匹配路由检测

如果请求未匹配任何路由，Mock Server 不会返回 HTTP 错误（避免让 production code 崩溃），而是返回一个包含 `[ERROR CALLING: NOT A SCHEDULED ROUTING` 标记的 200 响应。测试框架通过 `_check_mock_routing_error()` 检测此标记，将其标记为测试失败。

### 序列循环（降级测试）

`_seq_pick()` 支持路由值为列表时的序列循环：第 N 次调用返回列表的第 N 项（超出则返回最后一项）。这用于测试降级场景（如 Phase A 前 2 次返回非法 JSON，第 3 次成功）。

## Golden 文件对比

Golden 文件是测试的"标准答案"，存储在 `test/golden/` 目录下。

### 归一化规则

对比前会归一化以下不确定性字段（`golden_compare.py`）：

| 字段 | 处理 |
|------|------|
| `created_at` / `updated_at` | 替换为 `__TS__` |
| `entries[].ts` | 替换为 `__TS__` |
| `base_url` / `compact_base_url` / `compact_check_base_url` | 替换为 `__URL__` |
| `api_key` / `compact_api_key` / `compact_check_api_key` | 替换为 `__KEY__` |
| Summary 中的 ISO8601 时间戳行 | 替换为 `__TS__` |

### 生成 Golden 文件

```bash
# 生成所有 golden 文件（覆盖已有）
python3 test/test.py --generate-golden

# 生成特定测试的 golden
python3 test/test.py --generate-golden --filter basic
```

生成流程：测试正常运行后，将归一化的输出写入 `test/golden/{subdir}/{name}_debate_log.json` 和 `{name}_debate_summary.md`。

### 对比机制

```python
# Log JSON 对比
actual_json = canonical_json(normalize_log(actual_data))
golden_json = canonical_json(normalize_log(golden_data))
# 排序键、2 空格缩进、统一序列化后逐字符比较

# Summary MD 对比
actual_norm = normalize_summary(actual_text)  # 替换时间戳
golden_norm = normalize_summary(golden_text)
# 直接字符串比较
```

## 结构性检查

`structural_checks.py` 提供独立于 golden 文本的结构断言：

| 函数 | 说明 |
|------|------|
| `assert_debater_count(data, n)` | 验证辩手人数 |
| `assert_round_count(data, rounds, debaters)` | 验证轮数（speech 数 / 辩手数） |
| `assert_has_judge(data)` / `assert_no_judge(data)` | 验证裁判存在/缺失 |
| `assert_cross_exam_rounds(data, rounds, count)` | 验证质询出现在正确轮次 |
| `assert_no_cross_exam(data)` | 验证无质询 |
| `assert_has_cot(data)` / `assert_no_cot(data)` | 验证 CoT thinking 存在/缺失 |
| `assert_has_compact_checkpoint(data, n)` | 验证 compact checkpoint 存在 |
| `assert_compact_idempotent(before, after)` | 验证二次 compact 幂等性 |

## 注册新测试

### 1. 创建 Topic 文件

在 `test/topics/` 下创建 `your_feature.md`，包含标准的 YAML front-matter 配置和 `mock_responses` 字段：

```yaml
---
title: "测试：新功能"
rounds: 2
max_reply_tokens: 150
timeout: 120
base_url: ${DEBATE_BASE_URL}
api_key: ${DEBATE_API_KEY}
debaters:
  - name: 甲方
    model: gpt-4o-mini
    style: 支持A
  - name: 乙方
    model: gpt-4o-mini
    style: 支持B
judge:
  model: gpt-4o-mini
  name: 裁判
  base_url: ${DEBATE_BASE_URL}
  api_key: ${DEBATE_API_KEY}
  max_tokens: 200
round1_task: "陈述观点，80字以内。"
middle_task: "反驳对方，80字以内。"
final_task: "总结，60字以内。"
judge_instructions: "裁定，100字以内。"
# ↓ Mock 模式必需：定义确定性应答
mock_responses:
  debaters:
    甲方:
      1: "甲方第一轮发言内容。"
      2: "甲方第二轮发言内容。"
    乙方:
      1: "乙方第一轮发言内容。"
      2: "乙方第二轮发言内容。"
  judge: "裁定：甲方论证更完整。"
  # 如需质询，添加 cx_select / cx_questions
  # 如需 CoT，添加 cot_thinking
  # 如需 compact 降级测试，添加 compact.phase_a / phase_b / validity_check / drift_check
---

辩论话题正文...
```

**`mock_responses` 支持的字段：**

| 字段 | 格式 | 说明 |
|------|------|------|
| `debaters.{name}.{round}` | `str` | 辩手在指定轮次的发言 |
| `judge` | `str` | 裁判裁定文本 |
| `cx_select.{questioner}` | `str` | 质询对象选择（→ target name） |
| `cx_questions.{questioner}` | `list[str]` | 质询问题列表 |
| `cot_thinking.{name}.{round}` | `str` | CoT thinking 内容 |
| `compact.phase_a` | `str \| list[str]` | Phase A 状态提取 JSON（列表用于降级测试） |
| `compact.phase_b.{name}` | `str \| list[str]` | Phase B 辩手立场 JSON |
| `compact.validity_check` | `str \| list[str]` | 立场校验结果（"YES"/"NO"） |
| `compact.drift_check` | `str \| list[str]` | 漂移检查结果（"REFINEMENT"/"DEFECTION"） |

### 2. 编写测试函数

在 `test.py` 中添加测试函数，签名为 `def test_your_feature(ctx: TestContext) -> TestResult`：

```python
def test_your_feature(ctx: TestContext) -> TestResult:
    """一句话描述"""
    log_out = WORKDIR / "your_feature_debate_log.json"
    summary_out = WORKDIR / "your_feature_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "your_feature.md"),
                   "--output", str(log_out), "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("your_feature", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)

    # 结构性检查
    for chk in [
        lambda: assert_debater_count(data, 2),
        lambda: assert_round_count(data, 2, 2),
        lambda: assert_has_judge(data),
    ]:
        err = _structural_check("your_feature", chk)
        if err:
            return TestResult("your_feature", False, detail=err)

    # Golden 对比
    golden_err = _check_golden("your_feature", log_out, summary_out)
    if golden_err:
        return TestResult("your_feature", False, detail=golden_err)

    return TestResult("your_feature", True, detail=f"entries={len(data['entries'])}")
```

### 3. 注册测试

在 `test.py` 中修改以下两个数据结构：

```python
# 特性覆盖声明
FEATURE_COVERAGE["your_feature"] = ["debater", "judge", "your_tag", "golden"]

# 测试列表（顺序即执行顺序）
ALL_TESTS.append(("your_feature", test_your_feature))
```

### 4. 生成 Golden 文件

```bash
python3 test/test.py --generate-golden --filter your_feature
```

### 5. 验证

```bash
python3 test/test.py --filter your_feature
# 应输出 YES
```

## Resume 测试

Resume 测试依赖 `basic` 测试产生的日志。测试框架通过 `TestContext.basic_log` 传递：

1. `test_basic` 成功后将日志路径存入 `ctx.basic_log`
2. Resume 测试调用 `_copy_log(ctx, name)` 复制一份副本
3. 在副本上执行 `debate_cmd("resume", ...)` 

要添加新的 Resume 测试，需确保 topic 文件中的 `mock_responses` 涵盖新辩手发言。resume_topics/ 下的文件用于覆盖配置（如 add/drop debater、judge override 等）。

## 其他测试文件

- **`tests/test_runner_json_logs.py`**：单元测试（unittest），测试 runner.py 中的解析器、日志 I/O、LLM 兼容性等，不依赖 Mock Server，使用 `unittest.mock.patch` 直接 mock `call_llm`。
