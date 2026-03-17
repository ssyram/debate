# 测试覆盖报告

> 重构版本：v2 Log Schema（Log-Centric 架构）
> 日期：2026-03-16

## 基线（重构前）
- 通过：25 / 失败：3（既有问题，非新引入）

## 当前状态
- 通过：41 / 失败：3（与基线相同的既有问题）
- 新增通过测试：+17（来自本次重构新增的 6 个测试类）

## 既有失败（未修复，与本次重构无关）

| # | 测试名 | 失败原因 |
|---|--------|---------|
| 1 | `ConversionAndLogTests::test_compact_log_keeps_json_valid` | compact_log 需要 topic path 或 initial_config |
| 2 | `RunAndResumeTests::test_resume_appends_human_cross_exam_and_summary` | resume() 签名变更，测试 mock 未同步 |
| 3 | `RunAndResumeTests::test_run_supports_cot_cross_exam_and_optional_middle_task` | cross-exam 阶段 IndexError，mock 未同步 |

## 测试类总览

### 原有测试类

| 测试类 | 测试数 | 通过 | 失败 | 说明 |
|--------|--------|------|------|------|
| `TopicParsingTests` | 2 | 2 | 0 | YAML/frontmatter 解析 |
| `CrossExamParsingTests` | 8 | 8 | 0 | 质询目标提取 |
| `CrossExamFlowTests` | 3 | 3 | 0 | 质询并发流程 |
| `IdentifyFilesTests` | 3 | 3 | 0 | 文件识别逻辑 |
| `LLMCompatibilityTests` | 2 | 2 | 0 | LLM 响应格式兼容性；重试逻辑 |
| `CliOptionTests` | 1 | 1 | 0 | CLI dry-run 覆盖报告 |
| `ConversionAndLogTests` | 3 | 2 | 1 | 日志转换，1 个既有失败 |
| `RunAndResumeTests` | 2 | 0 | 2 | 运行/续跑集成，2 个既有失败 |
| `TopicConsistencyCheckTests` | 3 | 3 | 0 | 已替换为 v2 validate 测试 |

### 本次新增测试类（v2 重构验证）

| 测试类 | 测试数 | 通过 | 覆盖内容 |
|--------|--------|------|---------|
| `LogSchemaV2Tests` | 2 | 2 | v2 格式写入；v1 格式报错退出 |
| `ResolveEffectiveConfigTests` | 5 | 5 | 无 override；单次；多次累积；add+drop；judge override |
| `ResumeTopicParseTests` | 4 | 4 | YAML 解析；body 提取；add/drop；无 front-matter |
| `BuildInitialConfigTests` | 1 | 1 | api_key 排除；base_url 保留；compact 字段 |
| `MigrationScriptTests` | 1 | 1 | v1→v2 迁移正确性 |
| `DescribeOverridesTests` | 4 | 4 | 空 overrides；middle_task；add；drop |

## 测试模式说明

- 所有集成测试（RunAndResumeTests）使用 `fake_call_llm` mock LLM 调用，无实际网络请求
- 迁移脚本测试使用 `test_edo.md`（江户幕府辩题，gpt-4o-mini）作为 fixture
- v2 Schema 测试使用临时目录（`tempfile.TemporaryDirectory`）
