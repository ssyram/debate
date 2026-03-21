# 测试覆盖报告

> 更新日期：2026-03-22

## 测试体系

debate-tool 包含两层测试：

### 1. 端到端集成测试（`test/test.py`）

通过内置 Mock Server 完全离线运行，覆盖所有功能路径。

- **测试总数**：58
- **特性维度**：62
- **覆盖率**：100%

| 系列 | 数量 | 说明 |
|------|------|------|
| RUN | 13 | basic、cross_exam（含 array/all/false CLI）、cot、no_judge、constraints、early_stop 等 |
| RESUME | 10 | basic、message、guide、cross_exam、no_judge、judge_only、topic/judge override、add/drop debater 等 |
| COMPACT | 10 | 全量、幂等性、resume chain、message、keep-last（zero/negative/partial/excessive/double/chain） |
| DEGRADATION | 2 | Phase A 重试（非法 JSON→成功）、Phase B 全链降级（bad JSON→retry, NO→YES, DEFECTION→correction→REFINEMENT） |
| CANARY | 3 | constraints/message/guide 的 prompt 注入验证 |
| ERROR | 12 | 缺少文件、未知命令、非法 JSON、--force 校验、负数参数、modify 错误场景等 |
| NEW | 8 | version、early_stop、drop_debater、resume_cot、modify（含 add/drop force、double） |

运行方式：
```bash
python3 test/test.py          # 全部测试（Mock 模式）
python3 test/test.py --quick  # 仅快速测试
```

> 详细说明见 [test/README.md](../test/README.md)

### 2. 单元测试（`tests/test_runner_json_logs.py`）

使用 `unittest` + `unittest.mock.patch` 直接 mock `call_llm`，不依赖 Mock Server。

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|---------|
| `TopicParsingTests` | 2 | YAML/frontmatter 解析容错 |
| `CrossExamParsingTests` | 8 | 质询目标提取（JSON、标记、模糊匹配） |
| `CrossExamFlowTests` | 3 | 质询并发流程、修复、无意见降级 |
| `IdentifyFilesTests` | 3 | 文件识别逻辑（log/topic 区分） |
| `LLMCompatibilityTests` | 2 | LLM 响应格式兼容性；空响应重试 |
| `CliOptionTests` | 1 | CLI dry-run 覆盖报告 |
| `ConversionAndLogTests` | 3 | 日志转换、格式校验、compact 完整性 |
| `RunAndResumeTests` | 2 | 运行/续跑集成（CoT + cross-exam + resume） |
| `TopicConsistencyCheckTests` | 3 | 一致性校验、force 跳过、不匹配告警 |
| `LogSchemaV2Tests` | 2 | v2 格式写入；v1 格式报错退出 |
| `ResolveEffectiveConfigTests` | 5 | 无 override；单次；多次累积；add+drop；judge override |
| `ResumeTopicParseTests` | 4 | YAML 解析；body 提取；add/drop；无 front-matter |
| `BuildInitialConfigTests` | 1 | api_key 排除；base_url 保留；compact 字段 |
| `MigrationScriptTests` | 1 | v1→v2 迁移正确性 |
| `DescribeOverridesTests` | 4 | 空 overrides；middle_task；add；drop |

## 特性覆盖矩阵

端到端测试覆盖的 62 个特性维度：

```
debater, judge, golden, dry_run, config_validation, cross_exam, cross_exam_all,
cot, no_judge, rounds_override, multi_debater, constraints, cross_exam_array,
cross_exam_cli, cross_exam_disable, resume, message_inject, guide, judge_only,
topic_override, judge_override, add_debater, force, compact.phase_a,
compact.phase_b, validity_check, embedding, compact.idempotence,
compact_checkpoint, compact.resume, compact.message, compact.prompt_injection,
compact.keep_last, compact.keep_last.zero, compact.keep_last.negative,
compact.keep_last.partial, compact.keep_last.excessive, compact.keep_last.double,
compact.keep_last.chain, compact.phase_a.retry, compact.validity_retry,
compact.drift_correction, compact.correction, canary, prompt_placement, error,
missing_file, unknown_cmd, wrong_file_type, force_required, invalid_json, usage,
invalid_arg, modify, missing_arg, cli, version, early_stop, drop_debater,
idempotence
```
