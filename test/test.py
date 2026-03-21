#!/usr/bin/env python3
"""debate-tool 端到端集成测试

用法:
    source .local/.env && python3 test/test.py          # 运行所有测试
    source .local/.env && python3 test/test.py --quick   # 仅运行 dry-run + 错误场景等快速测试
    source .local/.env && python3 test/test.py --filter basic  # 按名称过滤测试
    source .local/.env && python3 test/test.py --quiet   # 不实时打印子进程输出

输出格式:
    YES  test_name (1.2s) — 说明
    NO   test_name (0.3s) — 失败原因
         <完整 stdout + stderr>

    YES = 预期成功且成功 / 预期失败且失败
    NO  = 预期成功却失败 / 预期失败却成功（后跟完整输出）

测试过程中实时输出子进程 stdout/stderr，让人安心。

测试矩阵（除早停外的所有功能）:

  RUN 系列 (正常场景):
    01. basic            — 基础 2 辩手 2 轮运行
    02. dry_run          — --dry-run 仅校验配置
    03. cross_exam       — --cross-exam R1 后质询
    04. cross_exam_all   — --cross-exam -1 全轮质询
    05. cot              — --cot 思考链模式
    06. no_judge         — --no-judge 跳过裁判
    07. custom_rounds    — --rounds 覆盖轮数
    08. three_debaters   — 3 辩手并行
    09. constraints      — 含约束条件
    10. cot_cross_exam   — CoT + 质询组合
    11. cross_exam_array — YAML cross_exam: [1] 数组语法
    12. cross_exam_all_cli — CLI --cross-exam ALL 全轮质询
    13. cross_exam_false_cli — CLI --cross-exam false 禁用质询

  RESUME 系列 (正常场景，依赖 basic 日志):
    14. resume_basic           — 基础续跑 1 轮
    15. resume_message         — 续跑 + 观察者消息
    16. resume_guide           — 续跑 + --guide 辩手引导
    17. resume_cross_exam      — 续跑 2 轮 + 质询
    18. resume_no_judge        — 续跑 + 跳过裁判
    19. resume_judge_only      — 续跑 --rounds 0 仅裁判
    20. resume_topic_override  — 通过 resume topic .md 覆盖配置
    21. resume_judge_override  — 通过 resume topic 覆盖裁判
    22. resume_add_debater     — add_debaters + --force (gpt-5.4-nano)
    23. resume_cross_exam_topic — 通过 resume topic 启用质询 (2 轮)

  COMPACT 系列:
    24. compact_all            — compact 全量压缩
    25. compact_double         — 二次 compact 幂等性
    26. compact_then_resume    — compact 后续跑正常
    27. compact_message        — --message 注入验证（出现在 user prompt）
    28. compact_keep_last_zero — --keep-last 0 等价全量压缩
    29. compact_keep_last_negative — --keep-last -1 等价全量压缩
    30. compact_keep_last_partial — --keep-last 2 保留末尾增量
    31. compact_keep_last_excessive — --keep-last 超过增量时等价全量压缩
    32. compact_keep_last_double — partial compact 后再 full compact
    33. compact_keep_last_resume_chain — partial compact → resume → full compact

  DEGRADATION 系列 (逐步降级测试):
    D01. compact_degrade_phase_a — Phase A 前2次失败第3次成功
    D02. compact_degrade_phase_b — Phase B bad JSON→retry, validity NO→YES, drift DEFECTION→REFINEMENT

  ERROR 系列 (预期失败场景):
    E01. err_missing_topic       — run 不存在的 topic 文件
    E02. err_unknown_command     — 未知子命令
    E03. err_resume_no_log       — resume 传入 topic 而非 log
    E04. err_resume_nonexist     — resume 传入不存在的文件
    E05. err_add_no_force        — add_debaters 不带 --force
    E06. err_drop_no_force       — drop_debaters 不带 --force
    E07. err_resume_bad_json     — resume 传入非法 JSON
    E08. err_no_args             — 不传任何参数
    E09. err_cross_exam_negative  — --cross-exam -2 负数报错
    E10. err_modify_no_topic     — modify 缺少 topic 文件参数
    E11. err_modify_add_no_force — modify add_debaters 不带 --force
    E12. err_modify_drop_no_force — modify drop_debaters 不带 --force

  CANARY 系列 (金丝雀 — 验证 prompt 注入有效性):
    C01. canary_constraint   — constraints 要求输出 [CANARY-C]，验证辩手遵守
    C02. canary_message      — --message 要求输出 [CANARY-M]，验证消息影响
    C03. canary_guide        — --guide 要求输出 [CANARY-G]，验证引导有效

  NEW 系列:
    N01. version             — --version 输出版本号
    N02. early_stop          — 收敛早停 (mock 模式，相同发言触发)
    N03. drop_debater        — resume + drop_debaters + --force
    N04. resume_cot          — resume + --cot 启用思考链
    N05. modify              — modify 仅注入配置（不辩论、不裁判）
    N06. modify_add_force    — modify + add_debaters + --force，仅写入配置
    N07. modify_drop_force   — modify + drop_debaters + --force，仅写入配置
    N08. modify_double       — modify 连续执行两次，仅追加 config_override

默认模型: gpt-4o-mini
add_debaters 测试: gpt-5.4-nano
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden_compare import compare_golden_log, compare_golden_summary, write_golden_log, write_golden_summary
from structural_checks import (
    assert_cross_exam_rounds, assert_no_cross_exam, assert_no_judge,
    assert_has_judge, assert_debater_count, assert_round_count,
    assert_has_cot, assert_no_cot, assert_has_compact_checkpoint,
    assert_compact_idempotent, StructuralError,
)


# ── 路径常量 ────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = ROOT / "test"
TOPICS_DIR = TEST_DIR / "topics"
ERROR_TOPICS_DIR = TOPICS_DIR / "error"
RESUME_TOPICS_DIR = TEST_DIR / "resume_topics"
WORKDIR = TEST_DIR / "workdir"
GOLDEN_DIR = TEST_DIR / "golden"

# 控制子进程输出是否实时打印
STREAM_OUTPUT = True
# 控制金丝雀测试产生的临时文件是否保留
NO_CLEANUP = False
GENERATE_GOLDEN = False
USE_MOCK = False
_mock_handle = None

MOCK_UNMATCHED_MARKER = "[ERROR CALLING: NOT A SCHEDULED ROUTING"


# ── 数据结构 ────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool            # YES or NO
    duration: float = 0.0   # seconds
    detail: str = ""        # 简要说明
    stdout: str = ""
    stderr: str = ""


@dataclass
class TestContext:
    """跨测试共享的状态"""
    basic_log: Path | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)


# ── 工具函数 ────────────────────────────────────────────────

def _tee_reader(stream, buf: list[str], prefix: str):
    """从 stream 逐行读取，实时打印并收集到 buf。"""
    for line in iter(stream.readline, ""):
        buf.append(line)
        if STREAM_OUTPUT:
            sys.stdout.write(f"       {prefix} {line}")
            sys.stdout.flush()
    stream.close()


def _get_env():
    env = dict(os.environ)
    if USE_MOCK and _mock_handle:
        env["DEBATE_BASE_URL"] = _mock_handle.base_url
        env["DEBATE_API_KEY"] = "mock-key"
        env["DEBATE_EMBEDDING_URL"] = _mock_handle.embedding_url
    return env


def debate_cmd(*args: str, timeout: int = 600, capture_only: bool = False
               ) -> subprocess.CompletedProcess[str]:
    """构建并执行 debate-tool 命令，实时流式输出。"""
    cmd = [sys.executable, "-m", "debate_tool", *args]

    if capture_only or not STREAM_OUTPUT:
        # 静默模式：直接 capture
        return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout,
                              env=_get_env())

    # 流式模式：Popen + tee
    proc = subprocess.Popen(
        cmd, cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=_get_env(),
    )
    stdout_buf: list[str] = []
    stderr_buf: list[str] = []
    t_out = threading.Thread(target=_tee_reader, args=(proc.stdout, stdout_buf, "│"))
    t_err = threading.Thread(target=_tee_reader, args=(proc.stderr, stderr_buf, "│"))
    t_out.start()
    t_err.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    t_out.join()
    t_err.join()
    return subprocess.CompletedProcess(
        cmd, proc.returncode,
        "".join(stdout_buf), "".join(stderr_buf),
    )


def load_log(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def count_tag(data: dict, tag: str) -> int:
    return sum(1 for e in data["entries"] if e.get("tag") == tag)


def has_tag(data: dict, tag: str) -> bool:
    return any(e.get("tag") == tag for e in data["entries"])


def entry_names(data: dict) -> set[str]:
    return {e["name"] for e in data["entries"]}


def _copy_log(ctx: TestContext, name: str) -> Path | None:
    """复制 basic 日志以供 resume 测试使用"""
    if not ctx.basic_log or not ctx.basic_log.exists():
        return None
    dst = WORKDIR / f"{name}_debate_log.json"
    shutil.copy2(ctx.basic_log, dst)
    return dst


def _full_output(r: subprocess.CompletedProcess[str]) -> str:
    """合并 stdout + stderr 用于 NO 场景的完整输出"""
    parts = []
    if r.stdout.strip():
        parts.append(f"[STDOUT]\n{r.stdout.strip()}")
    if r.stderr.strip():
        parts.append(f"[STDERR]\n{r.stderr.strip()}")
    return "\n".join(parts) if parts else "(无输出)"


def _check_mock_routing_error(result: TestResult) -> str | None:
    combined = (result.stdout or "") + (result.stderr or "")
    if MOCK_UNMATCHED_MARKER in combined:
        return "mock unmatched route detected in subprocess output"
    return None


def _structural_check(name: str, fn, *args) -> str | None:
    try:
        fn(*args)
        return None
    except StructuralError as e:
        return f"structural: {e}"


def _check_golden(name: str, log_path: Path, summary_path: Path | None = None,
                  subdir: str = "run") -> str | None:
    if GENERATE_GOLDEN:
        import json as _json
        data = _json.loads(log_path.read_text(encoding="utf-8"))
        write_golden_log(data, GOLDEN_DIR / subdir / f"{name}_debate_log.json")
        if summary_path and summary_path.exists():
            write_golden_summary(summary_path.read_text(encoding="utf-8"),
                                 GOLDEN_DIR / subdir / f"{name}_debate_summary.md")
        return None

    golden_log = GOLDEN_DIR / subdir / f"{name}_debate_log.json"
    if golden_log.exists():
        ok, diff = compare_golden_log(log_path, golden_log)
        if not ok:
            return f"golden log mismatch:\n{diff[:500]}"

    if summary_path and summary_path.exists():
        golden_sum = GOLDEN_DIR / subdir / f"{name}_debate_summary.md"
        if golden_sum.exists():
            ok, diff = compare_golden_summary(summary_path, golden_sum)
            if not ok:
                return f"golden summary mismatch:\n{diff[:500]}"
    return None


# ═══════════════════════════════════════════════════════════
#  RUN 系列（正常场景 — 预期成功）
# ═══════════════════════════════════════════════════════════

def test_basic(ctx: TestContext) -> TestResult:
    """基础 2 辩手 2 轮 + 裁判"""
    log_out = WORKDIR / "basic_debate_log.json"
    summary_out = WORKDIR / "basic_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "basic.md"),
                   "--output", str(log_out), "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("basic", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    if not log_out.exists():
        return TestResult("basic", False, detail="日志文件未生成")
    data = load_log(log_out)
    errs = []
    if data.get("format") != "debate-tool-log": errs.append("format")
    if data.get("version") != 2: errs.append("version")
    if not has_tag(data, "summary"): errs.append("无summary")
    debater_n = sum(1 for e in data["entries"] if e["tag"] == "")
    if debater_n < 4: errs.append(f"辩手发言{debater_n}<4")
    if not summary_out.exists(): errs.append("无summary文件")
    ctx.basic_log = log_out
    ctx.artifacts["basic_log"] = log_out
    if errs:
        return TestResult("basic", False, detail="; ".join(errs))
    for chk in [
        lambda: assert_debater_count(data, 2),
        lambda: assert_round_count(data, 2, 2),
        lambda: assert_has_judge(data),
        lambda: assert_no_cross_exam(data),
    ]:
        err = _structural_check("basic", chk)
        if err:
            return TestResult("basic", False, detail=err)
    golden_err = _check_golden("basic", log_out, summary_out)
    if golden_err:
        return TestResult("basic", False, detail=golden_err)
    return TestResult("basic", True, detail=f"entries={len(data['entries'])}")


def test_dry_run(ctx: TestContext) -> TestResult:
    """--dry-run 仅校验配置"""
    r = debate_cmd("run", str(TOPICS_DIR / "dry_run.md"), "--dry-run")
    if r.returncode != 0:
        return TestResult("dry_run", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    if "✅ 配置有效" not in r.stdout:
        return TestResult("dry_run", False, detail="输出中无 '✅ 配置有效'",
                          stdout=r.stdout, stderr=r.stderr)
    return TestResult("dry_run", True, detail="配置校验通过")


def test_cross_exam(ctx: TestContext) -> TestResult:
    """质询 R1 后"""
    log_out = WORKDIR / "cross_exam_debate_log.json"
    summary_out = WORKDIR / "cross_exam_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "cross_exam.md"), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("cross_exam", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    if not has_tag(data, "cross_exam"):
        return TestResult("cross_exam", False, detail="无cross_exam entry",
                          stdout=r.stdout, stderr=r.stderr)
    err = _structural_check("cross_exam", assert_cross_exam_rounds, data, {1}, 2)
    if err:
        return TestResult("cross_exam", False, detail=err)
    golden_err = _check_golden("cross_exam", log_out, summary_out)
    if golden_err:
        return TestResult("cross_exam", False, detail=golden_err)
    return TestResult("cross_exam", True, detail=f"cx={count_tag(data,'cross_exam')}")


def test_cross_exam_all(ctx: TestContext) -> TestResult:
    """全轮质询 cross_exam=-1"""
    log_out = WORKDIR / "cross_exam_all_debate_log.json"
    summary_out = WORKDIR / "cross_exam_all_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "cross_exam_all.md"), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("cross_exam_all", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    if not has_tag(data, "cross_exam"):
        return TestResult("cross_exam_all", False, detail="无cross_exam entry")
    err = _structural_check("cross_exam_all", assert_cross_exam_rounds, data, {1}, 2)
    if err:
        return TestResult("cross_exam_all", False, detail=err)
    golden_err = _check_golden("cross_exam_all", log_out, summary_out)
    if golden_err:
        return TestResult("cross_exam_all", False, detail=golden_err)
    return TestResult("cross_exam_all", True, detail=f"cx={count_tag(data,'cross_exam')}")


def test_cot(ctx: TestContext) -> TestResult:
    """CoT 思考链"""
    log_out = WORKDIR / "cot_debate_log.json"
    summary_out = WORKDIR / "cot_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "cot.md"), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("cot", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    err = _structural_check("cot", assert_has_cot, data)
    if err:
        return TestResult("cot", False, detail=err)
    golden_err = _check_golden("cot", log_out, summary_out)
    if golden_err:
        return TestResult("cot", False, detail=golden_err)
    return TestResult("cot", True, detail=f"thinking={count_tag(data,'thinking')}")


def test_no_judge(ctx: TestContext) -> TestResult:
    """跳过裁判"""
    log_out = WORKDIR / "no_judge_debate_log.json"
    summary_out = WORKDIR / "no_judge_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "no_judge.md"), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("no_judge", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    if has_tag(data, "summary"):
        return TestResult("no_judge", False, detail="不应有summary entry")
    for chk in [
        lambda: assert_no_judge(data),
        lambda: assert_debater_count(data, 2),
        lambda: assert_round_count(data, 2, 2),
    ]:
        err = _structural_check("no_judge", chk)
        if err:
            return TestResult("no_judge", False, detail=err)
    golden_err = _check_golden("no_judge", log_out)
    if golden_err:
        return TestResult("no_judge", False, detail=golden_err)
    return TestResult("no_judge", True, detail=f"entries={len(data['entries'])}，无summary")


def test_custom_rounds(ctx: TestContext) -> TestResult:
    """--rounds 覆盖轮数"""
    log_out = WORKDIR / "custom_rounds_debate_log.json"
    summary_out = WORKDIR / "custom_rounds_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "custom_rounds.md"), "--rounds", "2",
                   "--output", str(log_out), "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("custom_rounds", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    dn = sum(1 for e in data["entries"] if e["tag"] == "")
    if dn < 4:
        return TestResult("custom_rounds", False, detail=f"发言{dn}<4")
    golden_err = _check_golden("custom_rounds", log_out, summary_out)
    if golden_err:
        return TestResult("custom_rounds", False, detail=golden_err)
    return TestResult("custom_rounds", True, detail=f"发言={dn}")


def test_three_debaters(ctx: TestContext) -> TestResult:
    """3 辩手并行"""
    log_out = WORKDIR / "three_debaters_debate_log.json"
    summary_out = WORKDIR / "three_debaters_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "three_debaters.md"), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("three_debaters", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    de = [e for e in data["entries"] if e["tag"] == ""]
    names = {e["name"] for e in de}
    if len(de) < 6:
        return TestResult("three_debaters", False, detail=f"发言{len(de)}<6")
    if len(names) < 3:
        return TestResult("three_debaters", False, detail=f"辩手种类{len(names)}<3")
    for chk in [
        lambda: assert_debater_count(data, 3),
        lambda: assert_round_count(data, 2, 3),
        lambda: assert_has_judge(data),
    ]:
        err = _structural_check("three_debaters", chk)
        if err:
            return TestResult("three_debaters", False, detail=err)
    golden_err = _check_golden("three_debaters", log_out, summary_out)
    if golden_err:
        return TestResult("three_debaters", False, detail=golden_err)
    ctx.artifacts["three_debaters_log"] = log_out
    return TestResult("three_debaters", True, detail=f"辩手={names}")


def test_constraints(ctx: TestContext) -> TestResult:
    """含约束条件"""
    log_out = WORKDIR / "constraints_debate_log.json"
    summary_out = WORKDIR / "constraints_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "constraints.md"), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("constraints", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    if not data.get("initial_config", {}).get("constraints"):
        return TestResult("constraints", False, detail="initial_config无constraints")
    golden_err = _check_golden("constraints", log_out, summary_out)
    if golden_err:
        return TestResult("constraints", False, detail=golden_err)
    return TestResult("constraints", True, detail=f"entries={len(data['entries'])}")


def test_cot_cross_exam(ctx: TestContext) -> TestResult:
    """CoT + 质询组合"""
    log_out = WORKDIR / "cot_cross_exam_debate_log.json"
    summary_out = WORKDIR / "cot_cross_exam_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "cot_cross_exam.md"), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("cot_cross_exam", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    if not has_tag(data, "cross_exam"):
        return TestResult("cot_cross_exam", False, detail="无cross_exam")
    for chk in [
        lambda: assert_has_cot(data),
        lambda: assert_cross_exam_rounds(data, {1}, 2),
    ]:
        err = _structural_check("cot_cross_exam", chk)
        if err:
            return TestResult("cot_cross_exam", False, detail=err)
    golden_err = _check_golden("cot_cross_exam", log_out, summary_out)
    if golden_err:
        return TestResult("cot_cross_exam", False, detail=golden_err)
    return TestResult("cot_cross_exam", True, detail="CoT+质询OK")


def test_cross_exam_array(ctx: TestContext) -> TestResult:
    """cross_exam: [1] 数组语法，仅 R1 后质询"""
    log_out = WORKDIR / "cross_exam_array_debate_log.json"
    summary_out = WORKDIR / "cross_exam_array_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "cross_exam_array.md"), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("cross_exam_array", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    if not has_tag(data, "cross_exam"):
        return TestResult("cross_exam_array", False, detail="无cross_exam entry")
    err = _structural_check("cross_exam_array", assert_cross_exam_rounds, data, {1}, 2)
    if err:
        return TestResult("cross_exam_array", False, detail=err)
    golden_err = _check_golden("cross_exam_array", log_out, summary_out)
    if golden_err:
        return TestResult("cross_exam_array", False, detail=golden_err)
    return TestResult("cross_exam_array", True, detail=f"cx={count_tag(data,'cross_exam')}")


def test_cross_exam_all_cli(ctx: TestContext) -> TestResult:
    """--cross-exam ALL 等价于 -1 全轮质询"""
    log_out = WORKDIR / "cross_exam_all_cli_debate_log.json"
    summary_out = WORKDIR / "cross_exam_all_cli_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "dry_run.md"), "--rounds", "2",
                   "--cross-exam", "ALL",
                   "--output", str(log_out), "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("cross_exam_all_cli", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    if not has_tag(data, "cross_exam"):
        return TestResult("cross_exam_all_cli", False, detail="无cross_exam entry")
    golden_err = _check_golden("cross_exam_all_cli", log_out, summary_out)
    if golden_err:
        return TestResult("cross_exam_all_cli", False, detail=golden_err)
    return TestResult("cross_exam_all_cli", True,
                      detail=f"cx={count_tag(data,'cross_exam')}")


def test_cross_exam_false_cli(ctx: TestContext) -> TestResult:
    """--cross-exam false 不质询（即使 topic 有 cross_exam）"""
    log_out = WORKDIR / "cross_exam_false_cli_debate_log.json"
    summary_out = WORKDIR / "cross_exam_false_cli_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "cross_exam.md"),
                   "--cross-exam", "false",
                   "--output", str(log_out), "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("cross_exam_false_cli", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    if has_tag(data, "cross_exam"):
        return TestResult("cross_exam_false_cli", False,
                          detail="不应有cross_exam entry（false应禁用质询）")
    err = _structural_check("cross_exam_false_cli", assert_no_cross_exam, data)
    if err:
        return TestResult("cross_exam_false_cli", False, detail=err)
    golden_err = _check_golden("cross_exam_false_cli", log_out, summary_out)
    if golden_err:
        return TestResult("cross_exam_false_cli", False, detail=golden_err)
    return TestResult("cross_exam_false_cli", True, detail="false禁用质询OK")


# ═══════════════════════════════════════════════════════════
#  RESUME 系列（正常场景 — 预期成功）
# ═══════════════════════════════════════════════════════════

def test_resume_basic(ctx: TestContext) -> TestResult:
    """基础续跑 1 轮"""
    log = _copy_log(ctx, "resume_basic")
    if not log: return TestResult("resume_basic", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_basic_debate_summary.md"
    bc = len(load_log(log)["entries"])
    r = debate_cmd("resume", str(log), "--rounds", "1",
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_basic", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    ac = len(load_log(log)["entries"])
    if ac <= bc:
        return TestResult("resume_basic", False, detail=f"entries未增 {bc}→{ac}")
    golden_err = _check_golden("resume_basic", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_basic", False, detail=golden_err)
    return TestResult("resume_basic", True, detail=f"entries {bc}→{ac}")


def test_resume_message(ctx: TestContext) -> TestResult:
    """续跑 + 观察者消息"""
    log = _copy_log(ctx, "resume_message")
    if not log: return TestResult("resume_message", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_message_debate_summary.md"
    r = debate_cmd("resume", str(log), "--rounds", "1", "--message", "请加入成本分析角度",
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_message", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    if not has_tag(load_log(log), "human"):
        return TestResult("resume_message", False, detail="无human entry")
    golden_err = _check_golden("resume_message", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_message", False, detail=golden_err)
    return TestResult("resume_message", True, detail="观察者消息OK")


def test_resume_guide(ctx: TestContext) -> TestResult:
    """续跑 + --guide"""
    log = _copy_log(ctx, "resume_guide")
    if not log: return TestResult("resume_guide", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_guide_debate_summary.md"
    r = debate_cmd("resume", str(log), "--rounds", "1", "--guide", "聚焦成本效益比较",
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_guide", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    golden_err = _check_golden("resume_guide", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_guide", False, detail=golden_err)
    return TestResult("resume_guide", True,
                      detail=f"entries={len(load_log(log)['entries'])}")


def test_resume_cross_exam(ctx: TestContext) -> TestResult:
    """续跑 2 轮 + 质询（需要 >=2 轮才能在续跑中触发 cross_exam）"""
    log = _copy_log(ctx, "resume_cross_exam")
    if not log: return TestResult("resume_cross_exam", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_cross_exam_debate_summary.md"
    r = debate_cmd("resume", str(log), "--rounds", "2", "--cross-exam", "1",
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_cross_exam", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    if not has_tag(load_log(log), "cross_exam"):
        return TestResult("resume_cross_exam", False, detail="无cross_exam")
    golden_err = _check_golden("resume_cross_exam", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_cross_exam", False, detail=golden_err)
    return TestResult("resume_cross_exam", True, detail="续跑质询OK")


def test_resume_no_judge(ctx: TestContext) -> TestResult:
    """续跑 + 跳过裁判"""
    log = _copy_log(ctx, "resume_no_judge")
    if not log: return TestResult("resume_no_judge", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_no_judge_debate_summary.md"
    sc_before = count_tag(load_log(log), "summary")
    r = debate_cmd("resume", str(log), "--rounds", "1", "--no-judge",
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_no_judge", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    sc_after = count_tag(load_log(log), "summary")
    if sc_after > sc_before:
        return TestResult("resume_no_judge", False,
                          detail=f"summary增了 {sc_before}→{sc_after}")
    golden_err = _check_golden("resume_no_judge", log, subdir="resume")
    if golden_err:
        return TestResult("resume_no_judge", False, detail=golden_err)
    return TestResult("resume_no_judge", True, detail="跳过裁判OK")


def test_resume_judge_only(ctx: TestContext) -> TestResult:
    """续跑 --rounds 0 仅裁判"""
    log = _copy_log(ctx, "resume_judge_only")
    if not log: return TestResult("resume_judge_only", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_judge_only_debate_summary.md"
    bd = sum(1 for e in load_log(log)["entries"] if e["tag"] == "")
    r = debate_cmd("resume", str(log), "--rounds", "0",
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_judge_only", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log)
    ad = sum(1 for e in data["entries"] if e["tag"] == "")
    if ad != bd:
        return TestResult("resume_judge_only", False, detail=f"辩手发言变 {bd}→{ad}")
    if not any(e["tag"] == "summary" for e in data["entries"][-3:]):
        return TestResult("resume_judge_only", False, detail="无新summary")
    golden_err = _check_golden("resume_judge_only", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_judge_only", False, detail=golden_err)
    return TestResult("resume_judge_only", True, detail="仅裁判OK")


def test_resume_topic_override(ctx: TestContext) -> TestResult:
    """通过 resume topic 覆盖配置"""
    log = _copy_log(ctx, "resume_topic_override")
    if not log: return TestResult("resume_topic_override", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_topic_override_debate_summary.md"
    r = debate_cmd("resume", str(log), str(RESUME_TOPICS_DIR / "override_config.md"),
                   "--rounds", "1", "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_topic_override", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    if not has_tag(load_log(log), "config_override"):
        return TestResult("resume_topic_override", False, detail="无config_override")
    golden_err = _check_golden("resume_topic_override", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_topic_override", False, detail=golden_err)
    return TestResult("resume_topic_override", True, detail="配置覆盖OK")


def test_resume_judge_override(ctx: TestContext) -> TestResult:
    """通过 resume topic 覆盖裁判"""
    log = _copy_log(ctx, "resume_judge_override")
    if not log: return TestResult("resume_judge_override", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_judge_override_debate_summary.md"
    r = debate_cmd("resume", str(log), str(RESUME_TOPICS_DIR / "judge_override.md"),
                   "--rounds", "0", "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_judge_override", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    if not has_tag(load_log(log), "config_override"):
        return TestResult("resume_judge_override", False, detail="无config_override")
    golden_err = _check_golden("resume_judge_override", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_judge_override", False, detail=golden_err)
    return TestResult("resume_judge_override", True, detail="裁判覆盖OK")


def test_resume_add_debater(ctx: TestContext) -> TestResult:
    """add_debaters + --force (gpt-5.4-nano)"""
    log = _copy_log(ctx, "resume_add_debater")
    if not log: return TestResult("resume_add_debater", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_add_debater_debate_summary.md"
    r = debate_cmd("resume", str(log), str(RESUME_TOPICS_DIR / "add_debater.md"),
                   "--rounds", "1", "--force",
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_add_debater", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log)
    # 验证 override 中有 add_debaters
    has_add = False
    for e in data["entries"]:
        if e.get("tag") == "config_override":
            ov = e.get("overrides", {})
            if "add_debaters" in ov:
                for d in ov["add_debaters"]:
                    if d["name"] == "中立分析师" and d["model"] == "gpt-5.4-nano":
                        has_add = True
    if not has_add:
        return TestResult("resume_add_debater", False,
                          detail="未找到 gpt-5.4-nano add_debaters")
    # 验证新辩手参与发言
    if "中立分析师" not in entry_names(data):
        return TestResult("resume_add_debater", False, detail="新辩手未发言")
    golden_err = _check_golden("resume_add_debater", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_add_debater", False, detail=golden_err)
    ctx.artifacts["resume_add_log"] = log
    return TestResult("resume_add_debater", True, detail="gpt-5.4-nano辩手添加+发言OK")


def test_resume_cross_exam_topic(ctx: TestContext) -> TestResult:
    """通过 resume topic 启用质询 (2 轮以确保触发)"""
    log = _copy_log(ctx, "resume_cx_topic")
    if not log: return TestResult("resume_cross_exam_topic", False, detail="前置: basic日志不存在")
    summary_out = WORKDIR / "resume_cross_exam_topic_debate_summary.md"
    r = debate_cmd("resume", str(log), str(RESUME_TOPICS_DIR / "resume_cross_exam.md"),
                   "--rounds", "2", "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("resume_cross_exam_topic", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    if not has_tag(load_log(log), "cross_exam"):
        return TestResult("resume_cross_exam_topic", False, detail="无cross_exam")
    golden_err = _check_golden("resume_cross_exam_topic", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("resume_cross_exam_topic", False, detail=golden_err)
    return TestResult("resume_cross_exam_topic", True, detail="resume topic质询OK")


# ═══════════════════════════════════════════════════════════
#  COMPACT 系列
# ═══════════════════════════════════════════════════════════

def test_compact_all(ctx: TestContext) -> TestResult:
    """compact 全量压缩（默认 keep_last=0）"""
    src = ctx.artifacts.get("resume_add_log") or ctx.basic_log
    if not src or not src.exists():
        return TestResult("compact_all", False, detail="前置: 无可用日志")
    log = WORKDIR / "compact_test_debate_log.json"
    shutil.copy2(src, log)
    bc = len(load_log(log)["entries"])
    r = debate_cmd("compact", str(log))
    if r.returncode != 0:
        return TestResult("compact_all", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log)
    if not has_tag(data, "compact_checkpoint"):
        return TestResult("compact_all", False, detail="无compact_checkpoint")
    err = _structural_check("compact_all", assert_has_compact_checkpoint, data, 1)
    if err:
        return TestResult("compact_all", False, detail=err)
    golden_err = _check_golden("compact_all", log, subdir="compact")
    if golden_err:
        return TestResult("compact_all", False, detail=golden_err)
    ctx.artifacts["compact_log"] = log
    return TestResult("compact_all", True,
                      detail=f"entries {bc}→{len(data['entries'])}")


def test_compact_double(ctx: TestContext) -> TestResult:
    """compact 两次：第二次应幂等（无新增量时不产生新 checkpoint 或产生等价 checkpoint）"""
    src = ctx.artifacts.get("compact_log")
    if not src or not src.exists():
        return TestResult("compact_double", False, detail="前置: compact_all 未完成")
    log = WORKDIR / "compact_double_debate_log.json"
    shutil.copy2(src, log)
    data_before = load_log(log)
    cp_count_before = count_tag(data_before, "compact_checkpoint")
    entries_before = len(data_before["entries"])

    r = debate_cmd("compact", str(log))
    if r.returncode != 0:
        return TestResult("compact_double", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data_after = load_log(log)
    cp_count_after = count_tag(data_after, "compact_checkpoint")
    entries_after = len(data_after["entries"])

    err = _structural_check("compact_double", assert_compact_idempotent, data_before, data_after)
    if err:
        return TestResult("compact_double", False, detail=err)

    return TestResult("compact_double", True,
                      detail=f"checkpoint {cp_count_before}→{cp_count_after}, "
                             f"entries {entries_before}→{entries_after}")


def test_compact_then_resume(ctx: TestContext) -> TestResult:
    """compact 后 resume 1 轮：验证 compact checkpoint 后续跑仍正常"""
    src = ctx.artifacts.get("compact_log")
    if not src or not src.exists():
        return TestResult("compact_then_resume", False, detail="前置: compact_all 未完成")
    log = WORKDIR / "compact_resume_debate_log.json"
    shutil.copy2(src, log)
    entries_before = len(load_log(log)["entries"])

    r = debate_cmd("resume", str(log), "--rounds", "1")
    if r.returncode != 0:
        return TestResult("compact_then_resume", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log)
    entries_after = len(data["entries"])
    if entries_after <= entries_before:
        return TestResult("compact_then_resume", False,
                          detail=f"entries 未增 {entries_before}→{entries_after}")
    has_new_speech = any(
        e["tag"] == "" and e["seq"] > entries_before
        for e in data["entries"]
    )
    if not has_new_speech:
        return TestResult("compact_then_resume", False, detail="无新辩手发言")
    return TestResult("compact_then_resume", True,
                      detail=f"entries {entries_before}→{entries_after}")


def test_compact_message(ctx: TestContext) -> TestResult:
    """compact --message: 验证 message 出现在 compact LLM 请求的 user prompt 中"""
    src = ctx.artifacts.get("resume_add_log") or ctx.basic_log
    if not src or not src.exists():
        return TestResult("compact_message", False, detail="前置: 无可用日志")
    log = WORKDIR / "compact_message_debate_log.json"
    shutil.copy2(src, log)

    MARKER = "【测试标记：请特别关注安全议题的论证】"
    req_before = len(_mock_handle.requests) if _mock_handle else 0

    r = debate_cmd("compact", str(log), "--message", MARKER)
    if r.returncode != 0:
        return TestResult("compact_message", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)

    if not _mock_handle:
        return TestResult("compact_message", False, detail="非 mock 模式无法检查请求")

    new_reqs = _mock_handle.requests[req_before:]
    compact_reqs = [rq for rq in new_reqs if rq.get("_route", "").startswith("compact.")]
    if not compact_reqs:
        return TestResult("compact_message", False, detail="无 compact 路由请求")

    hits = sum(1 for rq in compact_reqs if MARKER in rq.get("user", ""))
    if hits == 0:
        return TestResult("compact_message", False,
                          detail=f"message 未出现在 user prompt! "
                                 f"compact requests={len(compact_reqs)}, hits=0")
    return TestResult("compact_message", True,
                      detail=f"message in user prompt: {hits}/{len(compact_reqs)}")


def _compact_source_log(ctx: TestContext) -> Path | None:
    src = ctx.artifacts.get("resume_add_log") or ctx.basic_log
    if not src or not src.exists():
        return None
    return src


def _speech_entries(data: dict) -> list[dict]:
    return [e for e in data["entries"] if not e.get("tag")]


def _latest_compact_checkpoint_state(data: dict) -> dict | None:
    cp_entries = [e for e in data["entries"] if e.get("tag") == "compact_checkpoint"]
    if not cp_entries:
        return None
    last_cp = cp_entries[-1]
    if isinstance(last_cp.get("state"), dict):
        return last_cp["state"]
    content = last_cp.get("content", "")
    if not content:
        return None
    return json.loads(content)


def test_compact_keep_last_zero(ctx: TestContext) -> TestResult:
    src = _compact_source_log(ctx)
    if not src:
        return TestResult("compact_keep_last_zero", False, detail="前置: 无可用日志")
    full_log = WORKDIR / "compact_keep_last_zero_full_debate_log.json"
    keep_log = WORKDIR / "compact_keep_last_zero_debate_log.json"
    shutil.copy2(src, full_log)
    shutil.copy2(src, keep_log)

    r_full = debate_cmd("compact", str(full_log))
    r_keep = debate_cmd("compact", str(keep_log), "--keep-last", "0")
    if r_full.returncode != 0:
        return TestResult("compact_keep_last_zero", False, detail=f"baseline exit {r_full.returncode}",
                          stdout=r_full.stdout, stderr=r_full.stderr)
    if r_keep.returncode != 0:
        return TestResult("compact_keep_last_zero", False, detail=f"exit {r_keep.returncode}",
                          stdout=r_keep.stdout, stderr=r_keep.stderr)

    full_data = load_log(full_log)
    keep_data = load_log(keep_log)
    full_cp = _latest_compact_checkpoint_state(full_data)
    keep_cp = _latest_compact_checkpoint_state(keep_data)
    if not full_cp or not keep_cp:
        return TestResult("compact_keep_last_zero", False, detail="无 compact_checkpoint")
    if keep_cp.get("covered_seq_end") != full_cp.get("covered_seq_end"):
        return TestResult("compact_keep_last_zero", False,
                          detail=f"covered_seq_end 不一致: {keep_cp.get('covered_seq_end')} != {full_cp.get('covered_seq_end')}")
    return TestResult("compact_keep_last_zero", True,
                      detail=f"covered_seq_end={keep_cp.get('covered_seq_end')}")


def test_compact_keep_last_negative(ctx: TestContext) -> TestResult:
    src = _compact_source_log(ctx)
    if not src:
        return TestResult("compact_keep_last_negative", False, detail="前置: 无可用日志")
    full_log = WORKDIR / "compact_keep_last_negative_full_debate_log.json"
    keep_log = WORKDIR / "compact_keep_last_negative_debate_log.json"
    shutil.copy2(src, full_log)
    shutil.copy2(src, keep_log)

    r_full = debate_cmd("compact", str(full_log))
    r_keep = debate_cmd("compact", str(keep_log), "--keep-last", "-1")
    if r_full.returncode != 0:
        return TestResult("compact_keep_last_negative", False, detail=f"baseline exit {r_full.returncode}",
                          stdout=r_full.stdout, stderr=r_full.stderr)
    if r_keep.returncode != 0:
        return TestResult("compact_keep_last_negative", False, detail=f"exit {r_keep.returncode}",
                          stdout=r_keep.stdout, stderr=r_keep.stderr)

    full_data = load_log(full_log)
    keep_data = load_log(keep_log)
    full_cp = _latest_compact_checkpoint_state(full_data)
    keep_cp = _latest_compact_checkpoint_state(keep_data)
    if not full_cp or not keep_cp:
        return TestResult("compact_keep_last_negative", False, detail="无 compact_checkpoint")
    if keep_cp.get("covered_seq_end") != full_cp.get("covered_seq_end"):
        return TestResult("compact_keep_last_negative", False,
                          detail=f"covered_seq_end 不一致: {keep_cp.get('covered_seq_end')} != {full_cp.get('covered_seq_end')}")
    return TestResult("compact_keep_last_negative", True,
                      detail=f"covered_seq_end={keep_cp.get('covered_seq_end')}")


def test_compact_keep_last_partial(ctx: TestContext) -> TestResult:
    src = _compact_source_log(ctx)
    if not src:
        return TestResult("compact_keep_last_partial", False, detail="前置: 无可用日志")
    log = WORKDIR / "compact_keep_last_partial_debate_log.json"
    shutil.copy2(src, log)
    before_data = load_log(log)
    delta_before = _speech_entries(before_data)
    if len(delta_before) < 3:
        return TestResult("compact_keep_last_partial", False,
                          detail=f"增量发言不足以验证 keep-last: {len(delta_before)}")

    KEEP_N = 2
    tail_before = delta_before[-KEEP_N:]

    r = debate_cmd("compact", str(log), "--keep-last", str(KEEP_N))
    if r.returncode != 0:
        return TestResult("compact_keep_last_partial", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log)
    cp_state = _latest_compact_checkpoint_state(data)
    if not cp_state:
        return TestResult("compact_keep_last_partial", False, detail="无 compact_checkpoint")
    covered_seq_end = cp_state.get("covered_seq_end", 0)
    max_seq = max(e["seq"] for e in data["entries"])
    if covered_seq_end >= max_seq:
        return TestResult("compact_keep_last_partial", False,
                          detail=f"checkpoint 覆盖到了末尾: covered_seq_end={covered_seq_end}, max_seq={max_seq}")

    cp_seq = next(e["seq"] for e in reversed(data["entries"])
                  if e.get("tag") == "compact_checkpoint")
    after_cp = [e for e in data["entries"]
                if e["seq"] > cp_seq and not e.get("tag")]
    if len(after_cp) != KEEP_N:
        return TestResult("compact_keep_last_partial", False,
                          detail=f"checkpoint 后应有 {KEEP_N} 条保留发言，实际 {len(after_cp)}")
    for orig, reinserted in zip(tail_before, after_cp):
        if reinserted["name"] != orig["name"] or reinserted["content"] != orig["content"]:
            return TestResult("compact_keep_last_partial", False,
                              detail=f"保留条目内容不匹配: "
                                     f"orig({orig['name']!r})≠reinserted({reinserted['name']!r})")
    return TestResult("compact_keep_last_partial", True,
                      detail=f"covered_seq_end={covered_seq_end} < max_seq={max_seq}, "
                             f"kept {KEEP_N} entries after checkpoint OK")


def test_compact_keep_last_excessive(ctx: TestContext) -> TestResult:
    src = _compact_source_log(ctx)
    if not src:
        return TestResult("compact_keep_last_excessive", False, detail="前置: 无可用日志")
    base_data = load_log(src)
    keep_last = len(_speech_entries(base_data)) + 5
    keep_log = WORKDIR / "compact_keep_last_excessive_debate_log.json"
    shutil.copy2(src, keep_log)

    r_keep = debate_cmd("compact", str(keep_log), "--keep-last", str(keep_last))
    if r_keep.returncode != 0:
        return TestResult("compact_keep_last_excessive", False, detail=f"exit {r_keep.returncode}",
                          stdout=r_keep.stdout, stderr=r_keep.stderr)

    keep_data = load_log(keep_log)
    if has_tag(keep_data, "compact_checkpoint"):
        return TestResult("compact_keep_last_excessive", False,
                          detail="keep_last 超过增量时不应生成 compact_checkpoint")
    if len(keep_data["entries"]) != len(base_data["entries"]):
        return TestResult("compact_keep_last_excessive", False,
                          detail=f"entries 意外变化: {len(base_data['entries'])}->{len(keep_data['entries'])}")
    return TestResult("compact_keep_last_excessive", True,
                      detail=f"keep_last={keep_last}, entries 保持 {len(keep_data['entries'])}")


def test_compact_keep_last_double(ctx: TestContext) -> TestResult:
    src = _compact_source_log(ctx)
    if not src:
        return TestResult("compact_keep_last_double", False, detail="前置: 无可用日志")
    log = WORKDIR / "compact_keep_last_double_debate_log.json"
    shutil.copy2(src, log)
    before_data = load_log(log)
    tail_before = _speech_entries(before_data)[-2:]

    r1 = debate_cmd("compact", str(log), "--keep-last", "2")
    if r1.returncode != 0:
        return TestResult("compact_keep_last_double", False, detail=f"step1 exit {r1.returncode}",
                          stdout=r1.stdout, stderr=r1.stderr)
    data_after_step1 = load_log(log)
    cp_entries_step1 = [e for e in data_after_step1["entries"] if e.get("tag") == "compact_checkpoint"]
    if not cp_entries_step1:
        return TestResult("compact_keep_last_double", False, detail="step1 无 compact_checkpoint")

    cp1_seq = cp_entries_step1[-1]["seq"]
    reinserted = [e for e in data_after_step1["entries"]
                  if e["seq"] > cp1_seq and not e.get("tag")]
    if len(reinserted) != 2:
        return TestResult("compact_keep_last_double", False,
                          detail=f"step1: checkpoint 后应有 2 条保留发言，实际 {len(reinserted)}")
    for orig, ri in zip(tail_before, reinserted):
        if ri["content"] != orig["content"]:
            return TestResult("compact_keep_last_double", False,
                              detail=f"step1: 保留条目内容不匹配 name={orig['name']!r}")

    cp_state1 = _latest_compact_checkpoint_state(data_after_step1)
    covered1 = cp_state1.get("covered_seq_end", 0) if cp_state1 else 0

    r2 = debate_cmd("compact", str(log))
    if r2.returncode != 0:
        return TestResult("compact_keep_last_double", False, detail=f"step2 exit {r2.returncode}",
                          stdout=r2.stdout, stderr=r2.stderr)
    data_after_step2 = load_log(log)
    cp_entries_step2 = [e for e in data_after_step2["entries"] if e.get("tag") == "compact_checkpoint"]
    if len(cp_entries_step2) < 2:
        return TestResult("compact_keep_last_double", False,
                          detail=f"checkpoint 数不足: {len(cp_entries_step2)}")
    cp_state2 = _latest_compact_checkpoint_state(data_after_step2)
    covered2 = cp_state2.get("covered_seq_end", 0) if cp_state2 else 0
    if covered2 <= covered1:
        return TestResult("compact_keep_last_double", False,
                          detail=f"step2 checkpoint 未扩大覆盖: {covered1} -> {covered2}")
    return TestResult("compact_keep_last_double", True,
                      detail=f"covered_seq_end {covered1}->{covered2}, checkpoints={len(cp_entries_step2)}")


def test_compact_keep_last_resume_chain(ctx: TestContext) -> TestResult:
    src = _compact_source_log(ctx)
    if not src:
        return TestResult("compact_keep_last_resume_chain", False, detail="前置: 无可用日志")
    log = WORKDIR / "compact_keep_last_resume_chain_debate_log.json"
    shutil.copy2(src, log)

    r1 = debate_cmd("compact", str(log), "--keep-last", "2")
    if r1.returncode != 0:
        return TestResult("compact_keep_last_resume_chain", False, detail=f"step1 exit {r1.returncode}",
                          stdout=r1.stdout, stderr=r1.stderr)
    before_resume_max_seq = max(e["seq"] for e in load_log(log)["entries"])

    r2 = debate_cmd("resume", str(log), "--rounds", "1")
    if r2.returncode != 0:
        return TestResult("compact_keep_last_resume_chain", False, detail=f"step2 exit {r2.returncode}",
                          stdout=r2.stdout, stderr=r2.stderr)

    r3 = debate_cmd("compact", str(log))
    if r3.returncode != 0:
        return TestResult("compact_keep_last_resume_chain", False, detail=f"step3 exit {r3.returncode}",
                          stdout=r3.stdout, stderr=r3.stderr)

    data = load_log(log)
    cp_entries = [e for e in data["entries"] if e.get("tag") == "compact_checkpoint"]
    if len(cp_entries) < 2:
        return TestResult("compact_keep_last_resume_chain", False,
                          detail=f"checkpoint 数不足: {len(cp_entries)}")
    new_speeches = [e for e in _speech_entries(data) if e["seq"] > before_resume_max_seq]
    if not new_speeches:
        return TestResult("compact_keep_last_resume_chain", False, detail="resume 后无新 speech entries")
    if not count_tag(data, "summary"):
        return TestResult("compact_keep_last_resume_chain", False, detail="resume 后无 judge summary")
    return TestResult("compact_keep_last_resume_chain", True,
                      detail=f"checkpoints={len(cp_entries)}, new_speeches={len(new_speeches)}")


# ═══════════════════════════════════════════════════════════
#  DEGRADATION 系列（逐步降级测试 — 序列循环模拟重试/降级路径）
# ═══════════════════════════════════════════════════════════

def _run_and_compact(topic_name: str, test_name: str) -> TestResult:
    """Run a debate with the given topic, then compact ALL.

    Resets mock call counters before compact so sequences start from 0.
    Returns TestResult; on success the log path is in detail.
    """
    from mock_routes import reset_call_counters

    topic = TOPICS_DIR / f"{topic_name}.md"
    log_out = WORKDIR / f"{test_name}_debate_log.json"
    summary_out = WORKDIR / f"{test_name}_debate_summary.md"

    r = debate_cmd("run", str(topic), "--output", str(log_out),
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult(test_name, False, detail=f"run exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)

    reset_call_counters()

    r = debate_cmd("compact", str(log_out))
    if r.returncode != 0:
        return TestResult(test_name, False, detail=f"compact exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)

    data = load_log(log_out)
    if not has_tag(data, "compact_checkpoint"):
        return TestResult(test_name, False, detail="compact 完成但无 compact_checkpoint")
    return TestResult(test_name, True,
                      detail=f"entries={len(data['entries'])}, checkpoint OK")


def test_compact_degrade_phase_a(ctx: TestContext) -> TestResult:
    """Phase A 降级：前 2 次返回非法 JSON，第 3 次成功"""
    return _run_and_compact("compact_degradation_a", "compact_degrade_phase_a")


def test_compact_degrade_phase_b(ctx: TestContext) -> TestResult:
    """Phase B 全链降级：Phase B bad JSON→retry, validity NO→YES, drift DEFECTION→correction→REFINEMENT"""
    return _run_and_compact("compact_degradation_b", "compact_degrade_phase_b")


# ═══════════════════════════════════════════════════════════
#  ERROR 系列（预期失败场景 — 命令应返回非零退出码）
# ═══════════════════════════════════════════════════════════

def _expect_fail(name: str, r: subprocess.CompletedProcess[str],
                 expect_in: str = "") -> TestResult:
    """断言命令失败(returncode!=0)。如果还活着那就是 NO。"""
    if r.returncode == 0:
        return TestResult(name, False,
                          detail=f"预期失败但 exit=0",
                          stdout=r.stdout, stderr=r.stderr)
    combined = r.stdout + r.stderr
    if expect_in and expect_in not in combined:
        return TestResult(name, False,
                          detail=f"退出码{r.returncode}但输出中无'{expect_in}'",
                          stdout=r.stdout, stderr=r.stderr)
    return TestResult(name, True, detail=f"预期失败 exit={r.returncode}")


def test_err_missing_topic(ctx: TestContext) -> TestResult:
    """run 不存在的 topic"""
    r = debate_cmd("run", "/tmp/this_topic_does_not_exist_42.md", capture_only=True)
    return _expect_fail("err_missing_topic", r)


def test_err_unknown_command(ctx: TestContext) -> TestResult:
    """未知子命令"""
    r = debate_cmd("foobar", capture_only=True)
    return _expect_fail("err_unknown_command", r, "未知命令")


def test_err_resume_no_log(ctx: TestContext) -> TestResult:
    """resume 传入 topic(.md) 而非 log(.json) — 应报错"""
    r = debate_cmd("resume", str(TOPICS_DIR / "basic.md"), capture_only=True)
    return _expect_fail("err_resume_no_log", r)


def test_err_resume_nonexist(ctx: TestContext) -> TestResult:
    """resume 传入不存在的文件"""
    r = debate_cmd("resume", "/tmp/nonexistent_log_42.json", capture_only=True)
    return _expect_fail("err_resume_nonexist", r)


def test_err_add_no_force(ctx: TestContext) -> TestResult:
    """add_debaters 不带 --force — 应报错"""
    log = _copy_log(ctx, "err_add_no_force")
    if not log: return TestResult("err_add_no_force", False, detail="前置: basic日志不存在")
    r = debate_cmd("resume", str(log), str(RESUME_TOPICS_DIR / "error_add_no_force.md"),
                   "--rounds", "1", capture_only=True)
    return _expect_fail("err_add_no_force", r, "force")


def test_err_drop_no_force(ctx: TestContext) -> TestResult:
    """drop_debaters 不带 --force — 应报错"""
    log = _copy_log(ctx, "err_drop_no_force")
    if not log: return TestResult("err_drop_no_force", False, detail="前置: basic日志不存在")
    r = debate_cmd("resume", str(log), str(RESUME_TOPICS_DIR / "error_drop_no_force.md"),
                   "--rounds", "1", capture_only=True)
    return _expect_fail("err_drop_no_force", r, "force")


def test_err_resume_bad_json(ctx: TestContext) -> TestResult:
    """resume 传入非法 JSON 文件"""
    bad = WORKDIR / "bad_file.json"
    bad.write_text("this is not json {{{", encoding="utf-8")
    r = debate_cmd("resume", str(bad), capture_only=True)
    return _expect_fail("err_resume_bad_json", r)


def test_err_cross_exam_negative(ctx: TestContext) -> TestResult:
    """--cross-exam -2 应报错（负数仅允许 -1）"""
    r = debate_cmd("run", str(TOPICS_DIR / "dry_run.md"),
                   "--cross-exam", "-2", capture_only=True)
    return _expect_fail("err_cross_exam_negative", r)


def test_err_modify_no_topic(ctx: TestContext) -> TestResult:
    if not ctx.basic_log:
        return TestResult("err_modify_no_topic", False, detail="前置: basic日志不存在")
    r = debate_cmd("modify", str(ctx.basic_log), capture_only=True)
    combined = r.stdout + r.stderr
    if r.returncode == 0:
        return TestResult("err_modify_no_topic", False, detail="预期失败但 exit=0",
                          stdout=r.stdout, stderr=r.stderr)
    if not any(token in combined for token in ("modify", "用法", "需要提供")):
        return TestResult("err_modify_no_topic", False,
                          detail="报错输出未包含 modify/用法/需要提供",
                          stdout=r.stdout, stderr=r.stderr)
    return TestResult("err_modify_no_topic", True, detail=f"预期失败 exit={r.returncode}")


def test_err_modify_add_no_force(ctx: TestContext) -> TestResult:
    log = _copy_log(ctx, "err_modify_add_no_force")
    if not log:
        return TestResult("err_modify_add_no_force", False, detail="前置: basic日志不存在")
    r = debate_cmd("modify", str(log), str(RESUME_TOPICS_DIR / "error_add_no_force.md"),
                   capture_only=True)
    return _expect_fail("err_modify_add_no_force", r, "force")


def test_err_modify_drop_no_force(ctx: TestContext) -> TestResult:
    log = _copy_log(ctx, "err_modify_drop_no_force")
    if not log:
        return TestResult("err_modify_drop_no_force", False, detail="前置: basic日志不存在")
    r = debate_cmd("modify", str(log), str(RESUME_TOPICS_DIR / "error_drop_no_force.md"),
                   capture_only=True)
    return _expect_fail("err_modify_drop_no_force", r, "force")


def test_err_no_args(ctx: TestContext) -> TestResult:
    """不传任何参数 — 应打印 help 并退出"""
    r = debate_cmd(capture_only=True)
    # 不传参数时 main() 调用 _print_help + sys.exit(0)
    if "debate-tool" in (r.stdout + r.stderr) and "run" in (r.stdout + r.stderr):
        return TestResult("err_no_args", True, detail="打印help并退出")
    return TestResult("err_no_args", False, detail="未输出help",
                      stdout=r.stdout, stderr=r.stderr)


# ═══════════════════════════════════════════════════════════
#  CANARY 系列（金丝雀 — 验证 prompt 注入有效性）
# ═══════════════════════════════════════════════════════════

CANARY_ARTIFACTS: list[Path] = []


def _canary_cleanup():
    """清理金丝雀测试产生的临时日志/summary 文件"""
    if NO_CLEANUP:
        return
    for p in CANARY_ARTIFACTS:
        if p.exists():
            p.unlink()
    CANARY_ARTIFACTS.clear()


def _count_canary(data: dict, tag: str, after_seq: int = 0) -> tuple[int, int]:
    """统计辩手发言中包含 tag 的数量。返回 (命中数, 辩手发言总数)。"""
    debater_entries = [
        e for e in data["entries"]
        if e["tag"] == "" and e["seq"] > after_seq
    ]
    hits = sum(1 for e in debater_entries if tag in e["content"])
    return hits, len(debater_entries)


def _parse_debug_jsonl(path: Path) -> list[dict]:
    """解析 JSONL debug 日志文件，返回所有 JSON 记录。"""
    records: list[dict] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def _find_canary_in_prompts(
    records: list[dict],
    canary_tag: str,
    *,
    purpose_filter: str = "",
) -> dict:
    """在 llm.request 类型的 debug 记录中搜索 canary tag。

    返回:
      {
        "in_system": int,    # canary 出现在 system 字段的 request 数
        "in_user": int,      # canary 出现在 user 字段的 request 数
        "total_requests": int, # 符合 purpose 过滤条件的总 request 数
      }
    """
    result = {"in_system": 0, "in_user": 0, "total_requests": 0}
    for rec in records:
        if rec.get("type") != "llm.request":
            continue
        if purpose_filter and purpose_filter not in (rec.get("purpose") or ""):
            continue
        result["total_requests"] += 1
        sys_text = rec.get("system", "")
        usr_text = rec.get("user", "")
        if canary_tag in sys_text:
            result["in_system"] += 1
        if canary_tag in usr_text:
            result["in_user"] += 1
    return result


def test_canary_constraint(ctx: TestContext) -> TestResult:
    """constraints 强制 [CANARY-C]：验证 system prompt 中包含 canary tag"""
    log_out = WORKDIR / "canary_constraint_debate_log.json"
    debug_log = WORKDIR / "canary_constraint_debug.json"
    topic = TOPICS_DIR / "canary_constraint.md"
    r = debate_cmd("run", str(topic), "--output", str(log_out),
                   "--debug", str(debug_log))
    CANARY_ARTIFACTS.extend([log_out, debug_log])
    if r.returncode != 0:
        return TestResult("canary_constraint", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)

    # 1) 检查辩手发言是否包含 canary
    data = load_log(log_out)
    hits, total = _count_canary(data, "[CANARY-C]")

    # 2) 解析 debug JSONL，验证 canary 在 system prompt 中
    records = _parse_debug_jsonl(debug_log)
    prompt_info = _find_canary_in_prompts(records, "[CANARY-C]", purpose_filter="debater")

    detail_parts = [f"output: {hits}/{total}"]
    if prompt_info["total_requests"] > 0:
        detail_parts.append(
            f"prompt: sys={prompt_info['in_system']}/{prompt_info['total_requests']} "
            f"usr={prompt_info['in_user']}/{prompt_info['total_requests']}"
        )
    else:
        detail_parts.append("prompt: no debater requests in debug log")

    # constraints 应出现在 system prompt
    if prompt_info["in_system"] == 0 and prompt_info["total_requests"] > 0:
        return TestResult("canary_constraint", False,
                          detail=f"[CANARY-C] 未出现在 system prompt! {'; '.join(detail_parts)}")
    if hits == 0:
        if USE_MOCK and (prompt_info["in_user"] > 0 or prompt_info["in_system"] > 0):
            return TestResult("canary_constraint", True,
                              detail=f"[mock] prompt placement OK; {'; '.join(detail_parts)}")
        return TestResult("canary_constraint", False,
                          detail=f"LLM 忽略了 canary（prompt 正确但 output 无标记）; {'; '.join(detail_parts)}")
    return TestResult("canary_constraint", True, detail="; ".join(detail_parts))


def test_canary_message(ctx: TestContext) -> TestResult:
    """--message 注入 [CANARY-M]：验证 user context 中包含 canary tag"""
    log = _copy_log(ctx, "canary_message")
    if not log: return TestResult("canary_message", False, detail="前置: basic日志不存在")
    before_data = load_log(log)
    before_seq = before_data["entries"][-1]["seq"]
    debug_log = WORKDIR / "canary_message_debug.json"
    CANARY_ARTIFACTS.extend([log, debug_log])

    r = debate_cmd("resume", str(log), "--rounds", "1", "--no-judge",
                   "--message",
                   "【系统指令】从现在起，每位辩手的发言都必须在开头包含标记 [CANARY-M]，"
                   "这是系统验证标记，不包含则发言无效。",
                   "--debug", str(debug_log))
    if r.returncode != 0:
        return TestResult("canary_message", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)

    # 1) 检查辩手发言
    data = load_log(log)
    hits, total = _count_canary(data, "[CANARY-M]", after_seq=before_seq)

    # 2) 解析 debug JSONL，验证 canary 在 user prompt 中
    records = _parse_debug_jsonl(debug_log)
    prompt_info = _find_canary_in_prompts(records, "[CANARY-M]", purpose_filter="debater")

    detail_parts = [f"output: {hits}/{total}"]
    if prompt_info["total_requests"] > 0:
        detail_parts.append(
            f"prompt: sys={prompt_info['in_system']}/{prompt_info['total_requests']} "
            f"usr={prompt_info['in_user']}/{prompt_info['total_requests']}"
        )
    else:
        detail_parts.append("prompt: no debater requests in debug log")

    # message 应出现在 user context（辩论历史中的 human entry）
    if prompt_info["in_user"] == 0 and prompt_info["in_system"] == 0 and prompt_info["total_requests"] > 0:
        return TestResult("canary_message", False,
                          detail=f"[CANARY-M] 未出现在任何 prompt 中! {'; '.join(detail_parts)}")
    if hits == 0:
        # canary 在 prompt 中但 LLM 没遵守 — 这仍算 prompt 有效，但标注
        if USE_MOCK and (prompt_info["in_user"] > 0 or prompt_info["in_system"] > 0):
            return TestResult("canary_message", True,
                              detail=f"[mock] prompt placement OK; {'; '.join(detail_parts)}")
        if prompt_info["in_user"] > 0 or prompt_info["in_system"] > 0:
            return TestResult("canary_message", False,
                              detail=f"LLM 忽略了 canary（prompt 含标记但 output 无）; {'; '.join(detail_parts)}")
        return TestResult("canary_message", False,
                          detail=f"0/{total} 新发言含 [CANARY-M]; {'; '.join(detail_parts)}")
    return TestResult("canary_message", True, detail="; ".join(detail_parts))


def test_canary_guide(ctx: TestContext) -> TestResult:
    """--guide 注入 [CANARY-G]：验证 system prompt 中包含 canary tag"""
    log = _copy_log(ctx, "canary_guide")
    if not log: return TestResult("canary_guide", False, detail="前置: basic日志不存在")
    before_data = load_log(log)
    before_seq = before_data["entries"][-1]["seq"]
    debug_log = WORKDIR / "canary_guide_debug.json"
    CANARY_ARTIFACTS.extend([log, debug_log])

    r = debate_cmd("resume", str(log), "--rounds", "1", "--no-judge",
                   "--guide",
                   "每位辩手必须在发言开头包含标记 [CANARY-G]，这是验证标记，不包含则无效。",
                   "--debug", str(debug_log))
    if r.returncode != 0:
        return TestResult("canary_guide", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)

    # 1) 检查辩手发言
    data = load_log(log)
    hits, total = _count_canary(data, "[CANARY-G]", after_seq=before_seq)

    # 2) 解析 debug JSONL，验证 canary 在 system prompt 中（guide → task → system）
    records = _parse_debug_jsonl(debug_log)
    prompt_info = _find_canary_in_prompts(records, "[CANARY-G]", purpose_filter="debater")

    detail_parts = [f"output: {hits}/{total}"]
    if prompt_info["total_requests"] > 0:
        detail_parts.append(
            f"prompt: sys={prompt_info['in_system']}/{prompt_info['total_requests']} "
            f"usr={prompt_info['in_user']}/{prompt_info['total_requests']}"
        )
    else:
        detail_parts.append("prompt: no debater requests in debug log")

    # guide 应出现在 system prompt（通过 task 描述）
    if prompt_info["in_system"] == 0 and prompt_info["total_requests"] > 0:
        return TestResult("canary_guide", False,
                          detail=f"[CANARY-G] 未出现在 system prompt! {'; '.join(detail_parts)}")
    if hits == 0:
        if USE_MOCK and (prompt_info["in_user"] > 0 or prompt_info["in_system"] > 0):
            return TestResult("canary_guide", True,
                              detail=f"[mock] prompt placement OK; {'; '.join(detail_parts)}")
        return TestResult("canary_guide", False,
                          detail=f"LLM 忽略了 canary（prompt 正确但 output 无标记）; {'; '.join(detail_parts)}")
    return TestResult("canary_guide", True, detail="; ".join(detail_parts))


# ═══════════════════════════════════════════════════════════
#  NEW 系列（新增测试）
# ═══════════════════════════════════════════════════════════

def test_version(ctx: TestContext) -> TestResult:
    r = debate_cmd("--version", capture_only=True)
    if r.returncode != 0:
        return TestResult("version", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    combined = r.stdout + r.stderr
    if "debate-tool" not in combined:
        return TestResult("version", False,
                          detail=f"输出中无 'debate-tool'",
                          stdout=r.stdout, stderr=r.stderr)
    return TestResult("version", True, detail=combined.strip()[:60])


def test_early_stop(ctx: TestContext) -> TestResult:
    log_out = WORKDIR / "early_stop_debate_log.json"
    summary_out = WORKDIR / "early_stop_debate_summary.md"
    r = debate_cmd("run", str(TOPICS_DIR / "early_stop.md"),
                   "--output", str(log_out), "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("early_stop", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log_out)
    speeches = [e for e in data["entries"] if not e.get("tag")]
    full_expected = 5 * 2
    if len(speeches) >= full_expected:
        return TestResult("early_stop", False,
                          detail=f"未提前停止: speeches={len(speeches)} >= {full_expected}")
    if "收敛" not in r.stdout and "观点已收敛" not in r.stdout:
        return TestResult("early_stop", False,
                          detail="stdout 中无收敛提示",
                          stdout=r.stdout, stderr=r.stderr)
    if not has_tag(data, "summary"):
        return TestResult("early_stop", False, detail="早停后无 judge summary")
    golden_err = _check_golden("early_stop", log_out, summary_out)
    if golden_err:
        return TestResult("early_stop", False, detail=golden_err)
    return TestResult("early_stop", True,
                      detail=f"speeches={len(speeches)}/{full_expected}, 早停OK")


def test_drop_debater(ctx: TestContext) -> TestResult:
    src = ctx.artifacts.get("three_debaters_log")
    if not src or not src.exists():
        return TestResult("drop_debater", False,
                          detail="前置: three_debaters 日志不存在")
    log = WORKDIR / "drop_debater_debate_log.json"
    summary_out = WORKDIR / "drop_debater_debate_summary.md"
    shutil.copy2(src, log)
    before_data = load_log(log)
    before_count = len(before_data["entries"])

    r = debate_cmd("resume", str(log),
                   str(RESUME_TOPICS_DIR / "drop_debater.md"),
                   "--rounds", "1", "--force",
                   "--output-summary", str(summary_out))
    if r.returncode != 0:
        return TestResult("drop_debater", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log)

    has_drop_override = False
    override_seq = 0
    for e in data["entries"]:
        if e.get("tag") == "config_override":
            ov = e.get("overrides", {})
            if "drop_debaters" in ov:
                has_drop_override = True
                override_seq = e["seq"]
    if not has_drop_override:
        return TestResult("drop_debater", False, detail="无 drop_debaters config_override")

    post_speeches = [e for e in data["entries"]
                     if not e.get("tag") and e["seq"] > override_seq]
    post_names = {e["name"] for e in post_speeches}
    if "Go派" in post_names:
        return TestResult("drop_debater", False,
                          detail=f"已移除的 Go派 仍在发言: {post_names}")
    if len(post_names) != 2:
        return TestResult("drop_debater", False,
                          detail=f"期望 2 位辩手发言，实际: {post_names}")

    golden_err = _check_golden("drop_debater", log, summary_out, subdir="resume")
    if golden_err:
        return TestResult("drop_debater", False, detail=golden_err)
    return TestResult("drop_debater", True,
                      detail=f"移除Go派OK, 剩余辩手={post_names}")


def test_resume_cot(ctx: TestContext) -> TestResult:
    log = _copy_log(ctx, "resume_cot")
    if not log:
        return TestResult("resume_cot", False, detail="前置: basic日志不存在")
    before_count = len(load_log(log)["entries"])

    r = debate_cmd("resume", str(log), "--rounds", "1", "--no-judge", "--cot")
    if r.returncode != 0:
        return TestResult("resume_cot", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log)
    new_thinking = [e for e in data["entries"]
                    if e.get("tag") == "thinking" and e["seq"] > before_count]
    if not new_thinking:
        return TestResult("resume_cot", False,
                          detail="无新 thinking entries（CoT 未生效）")
    golden_err = _check_golden("resume_cot", log, subdir="resume")
    if golden_err:
        return TestResult("resume_cot", False, detail=golden_err)
    return TestResult("resume_cot", True,
                      detail=f"new_thinking={len(new_thinking)}")


def test_modify(ctx: TestContext) -> TestResult:
    log = _copy_log(ctx, "modify")
    if not log:
        return TestResult("modify", False, detail="前置: basic日志不存在")
    before_data = load_log(log)
    before_entries = len(before_data["entries"])
    before_speeches = sum(1 for e in before_data["entries"] if not e.get("tag"))
    before_summaries = count_tag(before_data, "summary")

    r = debate_cmd("modify", str(log),
                   str(RESUME_TOPICS_DIR / "modify_config.md"))
    if r.returncode != 0:
        return TestResult("modify", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)
    data = load_log(log)

    if not has_tag(data, "config_override"):
        return TestResult("modify", False, detail="无 config_override entry")

    after_speeches = sum(1 for e in data["entries"] if not e.get("tag"))
    after_summaries = count_tag(data, "summary")
    if after_speeches != before_speeches:
        return TestResult("modify", False,
                          detail=f"辩手发言变化: {before_speeches}→{after_speeches}")
    if after_summaries != before_summaries:
        return TestResult("modify", False,
                          detail=f"summary变化: {before_summaries}→{after_summaries}")

    last_override_seq = max(
        e["seq"] for e in data["entries"] if e.get("tag") == "config_override"
    )
    post_entries = [e for e in data["entries"] if e["seq"] > last_override_seq]
    bad_tags = [e["tag"] for e in post_entries if e.get("tag") in ("", "summary")]
    if bad_tags:
        return TestResult("modify", False,
                          detail=f"config_override 后有意外 entries: {bad_tags}")

    golden_err = _check_golden("modify", log, subdir="resume")
    if golden_err:
        return TestResult("modify", False, detail=golden_err)
    return TestResult("modify", True,
                      detail=f"config_override OK, 无新辩论/裁判")


def test_modify_add_force(ctx: TestContext) -> TestResult:
    log = _copy_log(ctx, "modify_add_force")
    if not log:
        return TestResult("modify_add_force", False, detail="前置: basic日志不存在")

    r = debate_cmd("modify", str(log), str(RESUME_TOPICS_DIR / "add_debater.md"), "--force")
    if r.returncode != 0:
        return TestResult("modify_add_force", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)

    data = load_log(log)
    overrides = [e for e in data["entries"] if e.get("tag") == "config_override"]
    if not overrides:
        return TestResult("modify_add_force", False, detail="无 config_override entry")
    last_override = overrides[-1]
    override_text = last_override.get("content", "")
    override_data = last_override.get("overrides", {})
    if "add_debaters" not in override_data and "新增辩手" not in override_text:
        return TestResult("modify_add_force", False, detail="config_override 中无 add_debaters/新增辩手")

    override_seq = last_override["seq"]
    new_speeches = [e for e in data["entries"] if not e.get("tag") and e["seq"] > override_seq]
    new_summaries = [e for e in data["entries"] if e.get("tag") == "summary" and e["seq"] > override_seq]
    if new_speeches:
        return TestResult("modify_add_force", False,
                          detail=f"config_override 后出现 speech entries: {len(new_speeches)}")
    if new_summaries:
        return TestResult("modify_add_force", False,
                          detail=f"config_override 后出现 summary entries: {len(new_summaries)}")
    return TestResult("modify_add_force", True, detail="add_debaters 仅写入 config_override")


def test_modify_drop_force(ctx: TestContext) -> TestResult:
    src = ctx.artifacts.get("three_debaters_log")
    if not src or not src.exists():
        return TestResult("modify_drop_force", False, detail="前置: three_debaters 日志不存在")
    log = WORKDIR / "modify_drop_force_debate_log.json"
    shutil.copy2(src, log)

    r = debate_cmd("modify", str(log), str(RESUME_TOPICS_DIR / "drop_debater.md"), "--force")
    if r.returncode != 0:
        return TestResult("modify_drop_force", False, detail=f"exit {r.returncode}",
                          stdout=r.stdout, stderr=r.stderr)

    data = load_log(log)
    overrides = [e for e in data["entries"] if e.get("tag") == "config_override"]
    if not overrides:
        return TestResult("modify_drop_force", False, detail="无 config_override entry")
    last_override = overrides[-1]
    override_text = last_override.get("content", "")
    override_data = last_override.get("overrides", {})
    if "drop_debaters" not in override_data and "移除辩手" not in override_text:
        return TestResult("modify_drop_force", False, detail="config_override 中无 drop_debaters/移除辩手")

    override_seq = last_override["seq"]
    new_speeches = [e for e in data["entries"] if not e.get("tag") and e["seq"] > override_seq]
    new_summaries = [e for e in data["entries"] if e.get("tag") == "summary" and e["seq"] > override_seq]
    if new_speeches:
        return TestResult("modify_drop_force", False,
                          detail=f"config_override 后出现 speech entries: {len(new_speeches)}")
    if new_summaries:
        return TestResult("modify_drop_force", False,
                          detail=f"config_override 后出现 summary entries: {len(new_summaries)}")
    return TestResult("modify_drop_force", True, detail="drop_debaters 仅写入 config_override")


def test_modify_double(ctx: TestContext) -> TestResult:
    log = _copy_log(ctx, "modify_double")
    if not log:
        return TestResult("modify_double", False, detail="前置: basic日志不存在")
    before_data = load_log(log)
    before_speeches = sum(1 for e in before_data["entries"] if not e.get("tag"))
    before_summaries = count_tag(before_data, "summary")

    r1 = debate_cmd("modify", str(log), str(RESUME_TOPICS_DIR / "modify_config.md"))
    if r1.returncode != 0:
        return TestResult("modify_double", False, detail=f"step1 exit {r1.returncode}",
                          stdout=r1.stdout, stderr=r1.stderr)
    r2 = debate_cmd("modify", str(log), str(RESUME_TOPICS_DIR / "modify_config.md"))
    if r2.returncode != 0:
        return TestResult("modify_double", False, detail=f"step2 exit {r2.returncode}",
                          stdout=r2.stdout, stderr=r2.stderr)

    data = load_log(log)
    overrides = [e for e in data["entries"] if e.get("tag") == "config_override"]
    if len(overrides) < 2:
        return TestResult("modify_double", False, detail=f"config_override 数不足: {len(overrides)}")
    after_speeches = sum(1 for e in data["entries"] if not e.get("tag"))
    after_summaries = count_tag(data, "summary")
    if after_speeches != before_speeches or after_summaries != before_summaries:
        return TestResult("modify_double", False,
                          detail=f"modify 不应新增辩论/裁判: speeches {before_speeches}->{after_speeches}, summaries {before_summaries}->{after_summaries}")
    return TestResult("modify_double", True, detail=f"config_override={len(overrides)}")


# ═══════════════════════════════════════════════════════════
#  测试注册表
# ═══════════════════════════════════════════════════════════

TestFn = Callable[[TestContext], TestResult]

FEATURE_COVERAGE: dict[str, list[str]] = {
    "basic":            ["debater", "judge", "golden"],
    "dry_run":          ["dry_run", "config_validation"],
    "cross_exam":       ["debater", "judge", "cross_exam", "golden"],
    "cross_exam_all":   ["debater", "judge", "cross_exam_all", "golden"],
    "cot":              ["debater", "judge", "cot", "golden"],
    "no_judge":         ["debater", "no_judge", "golden"],
    "custom_rounds":    ["debater", "judge", "rounds_override", "golden"],
    "three_debaters":   ["debater", "judge", "multi_debater", "golden"],
    "constraints":      ["debater", "judge", "constraints", "golden"],
    "cot_cross_exam":   ["debater", "judge", "cot", "cross_exam", "golden"],
    "cross_exam_array": ["debater", "judge", "cross_exam_array", "golden"],
    "cross_exam_all_cli": ["debater", "judge", "cross_exam_cli", "golden"],
    "cross_exam_false_cli": ["debater", "judge", "cross_exam_disable", "golden"],
    "resume_basic":     ["resume", "debater", "judge", "golden"],
    "resume_message":   ["resume", "message_inject", "golden"],
    "resume_guide":     ["resume", "guide", "golden"],
    "resume_cross_exam": ["resume", "cross_exam", "golden"],
    "resume_no_judge":  ["resume", "no_judge", "golden"],
    "resume_judge_only": ["resume", "judge_only", "golden"],
    "resume_topic_override": ["resume", "topic_override", "golden"],
    "resume_judge_override": ["resume", "judge_override", "golden"],
    "resume_add_debater": ["resume", "add_debater", "force", "golden"],
    "resume_cross_exam_topic": ["resume", "cross_exam", "topic_override", "golden"],
    "compact_all":      ["compact.phase_a", "compact.phase_b", "validity_check", "embedding", "golden"],
    "compact_double":   ["compact.idempotence", "compact_checkpoint", "golden"],
    "compact_then_resume": ["compact.resume", "debater", "judge", "golden"],
    "compact_message":  ["compact.message", "compact.prompt_injection"],
    "compact_keep_last_zero": ["compact.keep_last", "compact.keep_last.zero", "compact_checkpoint"],
    "compact_keep_last_negative": ["compact.keep_last", "compact.keep_last.negative", "compact_checkpoint"],
    "compact_keep_last_partial": ["compact.keep_last", "compact.keep_last.partial", "compact_checkpoint"],
    "compact_keep_last_excessive": ["compact.keep_last", "compact.keep_last.excessive", "compact_checkpoint"],
    "compact_keep_last_double": ["compact.keep_last", "compact.keep_last.double", "compact_checkpoint"],
    "compact_keep_last_resume_chain": ["compact.keep_last", "compact.resume", "compact.keep_last.chain", "debater", "judge"],
    "compact_degrade_phase_a": ["compact.phase_a.retry", "compact.phase_a", "compact_checkpoint"],
    "compact_degrade_phase_b": ["compact.phase_b.retry", "compact.validity_retry", "compact.drift_correction", "compact.correction", "compact_checkpoint"],
    "canary_constraint": ["canary", "constraints", "prompt_placement"],
    "canary_message":   ["canary", "message", "prompt_placement"],
    "canary_guide":     ["canary", "guide", "prompt_placement"],
    "err_missing_topic": ["error", "missing_file"],
    "err_unknown_command": ["error", "unknown_cmd"],
    "err_resume_no_log": ["error", "wrong_file_type"],
    "err_resume_nonexist": ["error", "missing_file"],
    "err_add_no_force":  ["error", "force_required"],
    "err_drop_no_force": ["error", "force_required"],
    "err_resume_bad_json": ["error", "invalid_json"],
    "err_no_args":       ["error", "usage"],
    "err_cross_exam_negative": ["error", "invalid_arg"],
    "err_modify_no_topic": ["error", "modify", "missing_arg"],
    "err_modify_add_no_force": ["error", "modify", "force_required"],
    "err_modify_drop_no_force": ["error", "modify", "force_required"],
    "version":           ["cli", "version"],
    "early_stop":        ["debater", "judge", "early_stop", "golden"],
    "drop_debater":      ["resume", "drop_debater", "force", "golden"],
    "resume_cot":        ["resume", "cot", "no_judge", "golden"],
    "modify":            ["modify", "topic_override", "no_judge", "golden"],
    "modify_add_force":  ["modify", "add_debater", "force"],
    "modify_drop_force": ["modify", "drop_debater", "force"],
    "modify_double":     ["modify", "topic_override", "idempotence"],
}

ALL_TESTS: list[tuple[str, TestFn]] = [
    # ── RUN 系列 ──
    ("basic",            test_basic),
    ("dry_run",          test_dry_run),
    ("cross_exam",       test_cross_exam),
    ("cross_exam_all",   test_cross_exam_all),
    ("cot",              test_cot),
    ("no_judge",         test_no_judge),
    ("custom_rounds",    test_custom_rounds),
    ("three_debaters",   test_three_debaters),
    ("constraints",      test_constraints),
    ("cot_cross_exam",   test_cot_cross_exam),
    ("cross_exam_array", test_cross_exam_array),
    ("cross_exam_all_cli", test_cross_exam_all_cli),
    ("cross_exam_false_cli", test_cross_exam_false_cli),
    # ── RESUME 系列 ──
    ("resume_basic",           test_resume_basic),
    ("resume_message",         test_resume_message),
    ("resume_guide",           test_resume_guide),
    ("resume_cross_exam",      test_resume_cross_exam),
    ("resume_no_judge",        test_resume_no_judge),
    ("resume_judge_only",      test_resume_judge_only),
    ("resume_topic_override",  test_resume_topic_override),
    ("resume_judge_override",  test_resume_judge_override),
    ("resume_add_debater",     test_resume_add_debater),
    ("resume_cross_exam_topic", test_resume_cross_exam_topic),
    # ── COMPACT 系列 ──
    ("compact_all",          test_compact_all),
    ("compact_double",       test_compact_double),
    ("compact_then_resume",  test_compact_then_resume),
    ("compact_message",      test_compact_message),
    ("compact_keep_last_zero", test_compact_keep_last_zero),
    ("compact_keep_last_negative", test_compact_keep_last_negative),
    ("compact_keep_last_partial", test_compact_keep_last_partial),
    ("compact_keep_last_excessive", test_compact_keep_last_excessive),
    ("compact_keep_last_double", test_compact_keep_last_double),
    ("compact_keep_last_resume_chain", test_compact_keep_last_resume_chain),
    # ── DEGRADATION 系列 ──
    ("compact_degrade_phase_a", test_compact_degrade_phase_a),
    ("compact_degrade_phase_b", test_compact_degrade_phase_b),
    # ── CANARY 系列 ──
    ("canary_constraint",  test_canary_constraint),
    ("canary_message",     test_canary_message),
    ("canary_guide",       test_canary_guide),
    # ── ERROR 系列 ──
    ("err_missing_topic",  test_err_missing_topic),
    ("err_unknown_command", test_err_unknown_command),
    ("err_resume_no_log",  test_err_resume_no_log),
    ("err_resume_nonexist", test_err_resume_nonexist),
    ("err_add_no_force",   test_err_add_no_force),
    ("err_drop_no_force",  test_err_drop_no_force),
    ("err_resume_bad_json", test_err_resume_bad_json),
    ("err_no_args",        test_err_no_args),
    ("err_cross_exam_negative", test_err_cross_exam_negative),
    ("err_modify_no_topic", test_err_modify_no_topic),
    ("err_modify_add_no_force", test_err_modify_add_no_force),
    ("err_modify_drop_no_force", test_err_modify_drop_no_force),
    # ── NEW 系列 ──
    ("version",          test_version),
    ("early_stop",       test_early_stop),
    ("drop_debater",     test_drop_debater),
    ("resume_cot",       test_resume_cot),
    ("modify",           test_modify),
    ("modify_add_force", test_modify_add_force),
    ("modify_drop_force", test_modify_drop_force),
    ("modify_double",    test_modify_double),
]

# 快速测试：不调用 API
QUICK_TESTS = {"dry_run", "err_missing_topic", "err_unknown_command",
                "err_resume_no_log", "err_resume_nonexist", "err_resume_bad_json",
                "err_no_args", "err_cross_exam_negative", "err_modify_no_topic", "version"}
REAL_LLM_TESTS: set[str] = set()


# ═══════════════════════════════════════════════════════════
#  输出与主入口
# ═══════════════════════════════════════════════════════════

def print_header(idx: int, total: int, name: str):
    """测试开始前的分隔线"""
    print(f"\n  ┌──── [{idx:02d}/{total:02d}] {name} ────")
    sys.stdout.flush()


def print_verdict(idx: int, total: int, result: TestResult):
    """测试结束后的判定行"""
    verdict = "YES" if result.passed else "NO "
    dur = f"({result.duration:.1f}s)"
    features = FEATURE_COVERAGE.get(result.name, [])
    badge = " | " + " ".join(f"✓{f}" for f in features) if features and result.passed else ""
    print(f"  └─ {verdict}  [{idx:02d}/{total:02d}] {result.name} {dur} — {result.detail}{badge}")
    if not result.passed and not STREAM_OUTPUT:
        full = _full_output(
            subprocess.CompletedProcess("", 0, result.stdout, result.stderr)
        )
        for line in full.split("\n"):
            print(f"       {line}")
    sys.stdout.flush()


def main() -> int:
    import argparse
    global STREAM_OUTPUT

    parser = argparse.ArgumentParser(description="debate-tool 端到端测试")
    parser.add_argument("--quick", action="store_true",
                        help="仅运行快速（无 API）测试")
    parser.add_argument("--filter", default="",
                        help="按名称过滤测试（支持逗号分隔多个）")
    parser.add_argument("--keep-workdir", action="store_true",
                        help="测试后不清理 workdir")
    parser.add_argument("--quiet", action="store_true",
                        help="静默模式：不实时输出子进程内容")
    parser.add_argument("--no-cleanup", action="store_true",
                        help="保留金丝雀测试产生的临时文件")
    parser.add_argument("--generate-golden", action="store_true",
                        help="生成/更新 golden 文件而不是对比")
    parser.add_argument("--real-llm-test", action="store_true",
                        help="运行需要真实 LLM 的测试（canary/compact）")
    args = parser.parse_args()

    global STREAM_OUTPUT, NO_CLEANUP, GENERATE_GOLDEN, USE_MOCK, _mock_handle
    if args.quiet:
        STREAM_OUTPUT = False
    if args.no_cleanup:
        NO_CLEANUP = True
    if args.generate_golden:
        GENERATE_GOLDEN = True

    if not args.real_llm_test and not args.quick:
        USE_MOCK = True

    # 环境校验
    if not USE_MOCK:
        if not os.environ.get("DEBATE_BASE_URL") or not os.environ.get("DEBATE_API_KEY"):
            print("NO  env — 请先设置环境变量: source .local/.env")
            return 1

    # 过滤
    filter_names = set()
    if args.filter:
        filter_names = {n.strip() for n in args.filter.split(",")}

    tests_to_run: list[tuple[str, TestFn]] = []
    for name, fn in ALL_TESTS:
        if args.quick and name not in QUICK_TESTS:
            continue
        if not args.real_llm_test and name in REAL_LLM_TESTS:
            continue
        if args.real_llm_test and name not in REAL_LLM_TESTS:
            continue
        if filter_names and not any(f in name for f in filter_names):
            continue
        tests_to_run.append((name, fn))

    if not tests_to_run:
        print("NO  — 无匹配的测试")
        return 1

    if USE_MOCK:
        from mock_server import start_mock_server, stop_mock_server
        _mock_handle = start_mock_server()
        print(f"  Mock server: {_mock_handle.base_url}")

    # 准备 workdir
    if WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    WORKDIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  debate-tool 端到端集成测试")
    print("  默认模型: gpt-4o-mini | add_debaters: gpt-5.4-nano")
    print("  YES = 符合预期 | NO = 不符合预期（附完整输出）")
    mode = "MOCK" if USE_MOCK else ("REAL-LLM" if args.real_llm_test else "QUICK")
    print(f"  mode: {mode}")
    print("=" * 70)
    print(f"\n  运行 {len(tests_to_run)} 个测试 (workdir: {WORKDIR})\n")
    sys.stdout.flush()

    ctx = TestContext()
    results: list[TestResult] = []
    total = len(tests_to_run)

    try:
        for idx, (name, fn) in enumerate(tests_to_run, 1):
            print_header(idx, total, name)
            t0 = time.time()
            try:
                result = fn(ctx)
            except Exception as exc:
                result = TestResult(name, False, detail=f"异常: {exc}")
            result.duration = time.time() - t0
            if USE_MOCK and result.passed:
                mock_err = _check_mock_routing_error(result)
                if mock_err:
                    result = TestResult(name, False, detail=mock_err,
                                        stdout=result.stdout, stderr=result.stderr)
                    result.duration = time.time() - t0
            results.append(result)
            print_verdict(idx, total, result)
    finally:
        if USE_MOCK and _mock_handle:
            from mock_server import stop_mock_server
            stop_mock_server(_mock_handle)

    # 汇总
    yes_n = sum(1 for r in results if r.passed)
    no_n = sum(1 for r in results if not r.passed)
    total_time = sum(r.duration for r in results)

    print(f"\n{'=' * 70}")
    print(f"  总计: {len(results)} | YES: {yes_n} | NO: {no_n} | 耗时: {total_time:.1f}s")
    print(f"{'=' * 70}")

    all_features: set[str] = set()
    tested_features: set[str] = set()
    for name, _ in tests_to_run:
        feats = FEATURE_COVERAGE.get(name, [])
        all_features.update(feats)
        r = next((r for r in results if r.name == name), None)
        if r and r.passed:
            tested_features.update(feats)
    if all_features:
        coverage_pct = len(tested_features) / len(all_features) * 100
        print(f"\n  特性覆盖: {len(tested_features)}/{len(all_features)} ({coverage_pct:.0f}%)")
        untested = sorted(all_features - tested_features)
        if untested:
            print(f"  未覆盖: {', '.join(untested)}")

    if no_n:
        print("\n  NO 列表:")
        for r in results:
            if not r.passed:
                print(f"    NO  {r.name} — {r.detail}")

    if not args.keep_workdir and not no_n:
        shutil.rmtree(WORKDIR, ignore_errors=True)
        print(f"\n  workdir 已清理")
    else:
        print(f"\n  workdir 保留: {WORKDIR}")

    return 1 if no_n else 0


if __name__ == "__main__":
    raise SystemExit(main())
