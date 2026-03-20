#!/usr/bin/env python3
"""debate-tool 全量功能测试脚本

覆盖：
  T1  基础 run（TAG 标签验证）
  T2  CoT（thinking 条目验证）
  T3  cross-exam（质询条目验证）
  T4  early-stop（不崩溃 + summary 存在）
  T5  resume + --message（human 条目验证）
  T6  resume + --guide（续跑条目存在）
  T7  resume topic 文件（echo 格式验证）
  T8  compact（checkpoint 条目 + token 报告）
  T9  金丝雀上下文连续性（constraints 清空后标签复述）

用法：
  python3 scripts/test_full.py            # 全量
  python3 scripts/test_full.py T2 T9     # 指定测试
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".local" / "test_kimi_v7.md"
WORKDIR = ROOT / ".local" / "test_full_run"

# ── 公共 topic（bakumatsu + gpt-4o-mini，轮次各测试自行覆盖）────────────────

TOPIC_YAML = textwrap.dedent("""\
    ---
    title: "全量测试辩题"
    rounds: 3
    max_reply_tokens: 300
    timeout: 120
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}

    compact_threshold: 175000
    compact_model: gpt-4o-mini
    compact_base_url: ${DEBATE_BASE_URL}
    compact_api_key: ${DEBATE_API_KEY}
    compact_check_model: gpt-4o-mini
    compact_check_base_url: ${DEBATE_BASE_URL}
    compact_check_api_key: ${DEBATE_API_KEY}

    debaters:
      - name: 必然派
        model: gpt-4o-mini
        base_url: ${DEBATE_BASE_URL}
        api_key: ${DEBATE_API_KEY}
        style: "必然论：幕府崩溃是财政、合法性、军事三重矛盾锁死的必然。"

      - name: 偶然派
        model: gpt-4o-mini
        base_url: ${DEBATE_BASE_URL}
        api_key: ${DEBATE_API_KEY}
        style: "偶然论：孝明天皇之死、锦旗出现等节点充满偶发性。"

    judge:
      model: gpt-4o-mini
      name: 裁判
      base_url: ${DEBATE_BASE_URL}
      api_key: ${DEBATE_API_KEY}
      max_tokens: 300

    judge_instructions: |
      就"幕府失败是偶然还是必然"做出裁定。明确支持哪方，引用2个具体论点。

    constraints: ""

    round1_task: |
      在回复第一行单独写 [TAG-R1]。
      然后陈述你的核心论点，150字以内，援引1个具体历史事件。

    middle_task: |
      在回复第一行单独写 [TAG-R{轮次}]（第2轮写[TAG-R2]，依此类推）。
      然后反驳对方最薄弱的论点，150字以内。

    final_task: |
      在回复第一行单独写 [TAG-FINAL]。
      最终陈词，指出对方最强论点并化解，120字以内。
    ---

    # 幕末维新：幕府的失败是偶然还是必然？

    1853年黑船来航后，幕府在财政枯竭、合法性危机、军事失败三重压力下于1868年终结。
""")

CANARY_TOPIC_YAML = textwrap.dedent("""\
    ---
    title: "金丝雀上下文连续性测试"
    rounds: 3
    max_reply_tokens: 300
    timeout: 120
    base_url: ${DEBATE_BASE_URL}
    api_key: ${DEBATE_API_KEY}

    compact_threshold: 400
    compact_model: gpt-4o-mini
    compact_base_url: ${DEBATE_BASE_URL}
    compact_api_key: ${DEBATE_API_KEY}
    compact_check_model: gpt-4o-mini
    compact_check_base_url: ${DEBATE_BASE_URL}
    compact_check_api_key: ${DEBATE_API_KEY}
    compact_message: "请在每位辩手的 key_arguments 中保留其第2轮发言里使用的专属金丝雀标签（格式如 [CANARY-XX-XXX]），不得省略。"

    debaters:
      - name: 必然派
        model: gpt-4o-mini
        base_url: ${DEBATE_BASE_URL}
        api_key: ${DEBATE_API_KEY}
        style: "必然论：幕府崩溃是财政、合法性、军事三重矛盾锁死的必然。"

      - name: 偶然派
        model: gpt-4o-mini
        base_url: ${DEBATE_BASE_URL}
        api_key: ${DEBATE_API_KEY}
        style: "偶然论：孝明天皇之死、锦旗出现等节点充满偶发性。"

    judge:
      model: gpt-4o-mini
      name: 裁判
      base_url: ${DEBATE_BASE_URL}
      api_key: ${DEBATE_API_KEY}
      max_tokens: 300

    judge_instructions: "做出裁定，明确支持哪方。"

    constraints: |
      【金丝雀规则·仅第2轮】每位辩手在第2轮发言的第一行单独输出自己的专属金丝雀标签：
      - 必然派：[CANARY-BZ-K9X]
      - 偶然派：[CANARY-OY-P7M]
      其他轮次不使用此标签。

    round1_task: "陈述核心论点，100字以内，援引1个历史事件。"

    middle_task: |
      【第一行单独输出你的专属金丝雀标签，见 constraints】
      然后反驳对方最薄弱的论点，150字以内。

    final_task: "最终陈词，120字以内。"
    ---

    # 幕末维新：幕府的失败是偶然还是必然？
""")

CANARY_RESUME_YAML = textwrap.dedent("""\
    ---
    constraints: ""

    middle_task: |
      请在回复的第一行复述你在第2轮发言中使用的专属金丝雀标签（完整格式），
      然后继续正常辩论，150字以内。

    final_task: |
      请在回复的第一行复述你在第2轮发言中使用的专属金丝雀标签（完整格式），
      然后继续正常辩论，150字以内。
    ---
""")


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def prepare_env() -> dict[str, str]:
    text = SECRETS.read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---", 2)[1])
    env = os.environ.copy()
    env["DEBATE_BASE_URL"] = front["base_url"]
    env["DEBATE_API_KEY"] = front["api_key"]
    return env


def run_cmd(cmd: list[str], env: dict[str, str], label: str = "") -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"[{label}] 命令失败: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout[-2000:]}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )
    return result


def load_log(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def entries_of(data: dict) -> list[dict]:
    return data.get("entries", [])


def all_entries_of(data: dict) -> list[dict]:
    """JSON entries 字段包含全部记录（含 compact 前的），直接返回即可。"""
    return data.get("entries", [])


# ── Log 格式基础校验 ──────────────────────────────────────────────────────────

def validate_log_format(data: dict, label: str) -> list[str]:
    """校验 log 基础格式，返回错误列表（空=OK）"""
    errors: list[str] = []

    if data.get("format") != "debate-tool-log":
        errors.append(f"format 字段错误: {data.get('format')!r}")
    if data.get("version") != 2:
        errors.append(f"version 字段错误: {data.get('version')!r}")
    if not data.get("topic"):
        errors.append("topic 字段缺失或为空")
    if not isinstance(data.get("initial_config"), dict):
        errors.append("initial_config 缺失或非 dict")

    entries = entries_of(data)
    if not entries:
        errors.append("entries 为空")
        return errors

    # seq 连续性（可能从非0开始，但必须递增无重复）
    seqs = [e.get("seq") for e in entries if e.get("seq") is not None]
    if seqs != sorted(set(seqs)):
        errors.append(f"seq 不连续或有重复: {seqs}")

    # 每条 entry 必须字段
    for e in entries:
        for field in ("seq", "tag", "name", "content"):
            if field not in e:
                errors.append(f"entry seq={e.get('seq','?')} 缺少字段 {field!r}")
        # speech 条目（tag=""）不能 content 为空
        if e.get("tag") == "" and not e.get("content", "").strip():
            errors.append(f"speech 条目 seq={e.get('seq')} content 为空")

    return errors


# ── 测试实现 ──────────────────────────────────────────────────────────────────

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.checks: list[tuple[str, bool, str]] = []  # (desc, passed, detail)

    def ok(self, desc: str, detail: str = ""):
        self.checks.append((desc, True, detail))

    def fail(self, desc: str, detail: str = ""):
        self.checks.append((desc, False, detail))

    def check(self, desc: str, cond: bool, detail: str = ""):
        if cond:
            self.ok(desc, detail)
        else:
            self.fail(desc, detail)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


def run_and_validate(label, cmd, env, log_path) -> tuple[dict, TestResult]:
    r = TestResult(label)
    run_cmd(cmd, env, label)
    data = load_log(log_path)
    errs = validate_log_format(data, label)
    r.check("log 格式正确", not errs, "; ".join(errs) if errs else "")
    return data, r


def t1_basic_run(env: dict, workdir: Path) -> TestResult:
    topic = workdir / "t1.md"
    topic.write_text(TOPIC_YAML)
    log = workdir / "t1.json"

    data, r = run_and_validate("T1", [
        sys.executable, "-m", "debate_tool", "run", str(topic),
        "--rounds", "2", "--output", str(log)
    ], env, log)

    entries = entries_of(data)
    speeches = [e for e in entries if not e.get("tag")]
    r.check("发言条数 == 4（2轮×2辩手）", len(speeches) == 4,
            f"实际 {len(speeches)} 条")

    r1 = [e for e in speeches[:2] if "[TAG-R1]" in e["content"]]
    r.check("第1轮两条发言均含 [TAG-R1]", len(r1) == 2,
            f"含标签 {len(r1)}/2")

    final = [e for e in speeches[2:] if "[TAG-FINAL]" in e["content"]]
    r.check("第2轮（final）两条发言均含 [TAG-FINAL]", len(final) == 2,
            f"含标签 {len(final)}/2")

    r.check("有 summary 条目", any(e.get("tag") == "summary" for e in entries))
    return r


def t2_cot(env: dict, workdir: Path) -> TestResult:
    topic = workdir / "t2.md"
    topic.write_text(TOPIC_YAML)
    log = workdir / "t2.json"

    data, r = run_and_validate("T2", [
        sys.executable, "-m", "debate_tool", "run", str(topic),
        "--rounds", "2", "--cot", "--output", str(log)
    ], env, log)

    entries = entries_of(data)
    thinking = [e for e in entries if e.get("tag") == "thinking"]
    speeches = [e for e in entries if not e.get("tag")]

    r.check("有 thinking 条目（新行为：parse 失败 → 二次调用）",
            len(thinking) > 0, f"thinking 条目数: {len(thinking)}")
    r.check("thinking 条目数 == speech 条目数",
            len(thinking) == len(speeches),
            f"thinking={len(thinking)} speech={len(speeches)}")
    r.check("thinking 内容非空",
            all(e.get("content", "").strip() for e in thinking),
            "存在空 thinking")

    # 验证每条 thinking 和对应 speech 的 seq 相邻
    paired = True
    for th in thinking:
        seq = th.get("seq", -1)
        paired_speech = next((e for e in speeches if e.get("seq") == seq + 1), None)
        if not paired_speech:
            paired = False
            break
    r.check("thinking 与后续 speech 条目 seq 相邻", paired)
    return r


def t3_cross_exam(env: dict, workdir: Path) -> TestResult:
    topic = workdir / "t3.md"
    topic.write_text(TOPIC_YAML)
    log = workdir / "t3.json"

    data, r = run_and_validate("T3", [
        sys.executable, "-m", "debate_tool", "run", str(topic),
        "--rounds", "2", "--cross-exam", "--output", str(log)
    ], env, log)

    entries = entries_of(data)
    cx = [e for e in entries if e.get("tag") == "cross_exam"]
    r.check("有 cross_exam 条目", len(cx) > 0, f"cross_exam 条目数: {len(cx)}")
    r.check("cross_exam 内容非空",
            all(e.get("content", "").strip() for e in cx))
    r.check("有 summary 条目", any(e.get("tag") == "summary" for e in entries))
    return r


def t4_early_stop(env: dict, workdir: Path) -> TestResult:
    topic = workdir / "t4.md"
    topic.write_text(TOPIC_YAML)
    log = workdir / "t4.json"

    data, r = run_and_validate("T4", [
        sys.executable, "-m", "debate_tool", "run", str(topic),
        "--rounds", "5", "--early-stop", "--output", str(log)
    ], env, log)

    entries = all_entries_of(data)
    speeches = [e for e in entries if not e.get("tag")]
    r.check("至少跑了1轮（≥2条发言）", len(speeches) >= 2, f"发言数: {len(speeches)}")
    r.check("最多跑了5轮（≤10条发言）", len(speeches) <= 10, f"发言数: {len(speeches)}")
    r.check("有 summary 条目", any(e.get("tag") == "summary" for e in entries))
    return r


def t5_resume_message(env: dict, workdir: Path) -> TestResult:
    topic = workdir / "t5.md"
    topic.write_text(TOPIC_YAML)
    log = workdir / "t5.json"

    run_cmd([sys.executable, "-m", "debate_tool", "run", str(topic),
             "--rounds", "2", "--output", str(log)], env, "T5-run")

    run_cmd([sys.executable, "-m", "debate_tool", "resume", str(log),
             "--rounds", "1", "--message", "请两位辩手直接点名对方最弱的一个论点"], env, "T5-resume")

    data = load_log(log)
    r = TestResult("T5")
    errs = validate_log_format(data, "T5")
    r.check("log 格式正确", not errs, "; ".join(errs) if errs else "")

    entries = all_entries_of(data)
    human = [e for e in entries if e.get("tag") == "human"]
    r.check("有 human 条目", len(human) == 1, f"human 条目数: {len(human)}")
    r.check("human 内容含关键词",
            "最弱" in (human[0].get("content", "") if human else ""))

    summaries = [e for e in entries if e.get("tag") == "summary"]
    r.check("有 ≥2 个 summary（run + resume 各一）", len(summaries) >= 2,
            f"summary 数: {len(summaries)}")
    return r


def t6_resume_guide(env: dict, workdir: Path) -> TestResult:
    topic = workdir / "t6.md"
    topic.write_text(TOPIC_YAML)
    log = workdir / "t6.json"

    run_cmd([sys.executable, "-m", "debate_tool", "run", str(topic),
             "--rounds", "2", "--output", str(log)], env, "T6-run")

    before_entries = len(entries_of(load_log(log)))
    run_cmd([sys.executable, "-m", "debate_tool", "resume", str(log),
             "--rounds", "1", "--guide", "聚焦军事层面的具体战役证据"], env, "T6-resume")

    data = load_log(log)
    r = TestResult("T6")
    errs = validate_log_format(data, "T6")
    r.check("log 格式正确", not errs, "; ".join(errs) if errs else "")

    after_entries = len(entries_of(data))
    r.check("resume 后 entries 增加（≥2条新发言+1条summary）",
            after_entries >= before_entries + 3,
            f"before={before_entries} after={after_entries}")

    # guide 是 ephemeral，不写入 log，验证无 config_override 含 guide 内容
    overrides = [e for e in entries_of(data) if e.get("tag") == "config_override"]
    r.check("guide 不写入 config_override 条目", len(overrides) == 0,
            f"config_override 条目数: {len(overrides)}")
    return r


def t7_resume_echo(env: dict, workdir: Path) -> TestResult:
    topic = workdir / "t7.md"
    topic.write_text(TOPIC_YAML)
    log = workdir / "t7.json"

    resume_topic = workdir / "t7_resume.md"
    resume_topic.write_text(textwrap.dedent("""\
        ---
        middle_task: |
          【ECHO验证任务·必须按格式完成】

          第一步：逐字引用对方辩手在第1轮辩论中说的原文（不少于30字），格式严格如下：
          > [R1原文引用] 对方第1轮中写道："……（原文，不得改写）"

          第二步：指出该段引用的最大逻辑漏洞，提出你的反驳，100字以内。

        final_task: |
          【ECHO验证任务·必须按格式完成】

          第一步：逐字引用对方辩手在第1轮辩论中说的原文（不少于30字），格式严格如下：
          > [R1原文引用] 对方第1轮中写道："……（原文，不得改写）"

          第二步：指出该段引用的最大逻辑漏洞，提出你的反驳，100字以内。
        ---
    """))

    run_cmd([sys.executable, "-m", "debate_tool", "run", str(topic),
             "--rounds", "2", "--output", str(log)], env, "T7-run")
    run_cmd([sys.executable, "-m", "debate_tool", "resume", str(log),
             str(resume_topic), "--rounds", "1"], env, "T7-resume")

    data = load_log(log)
    r = TestResult("T7")
    errs = validate_log_format(data, "T7")
    r.check("log 格式正确", not errs, "; ".join(errs) if errs else "")

    entries = entries_of(data)
    speeches = [e for e in entries if not e.get("tag")]
    resume_speeches = speeches[-2:]  # 最后2条是 resume 轮发言

    echo_pattern = re.compile(r"> \[R1原文引用\]")
    echo_hits = [e for e in resume_speeches if echo_pattern.search(e.get("content", ""))]
    r.check("resume 轮发言含 > [R1原文引用] 格式引用（至少1条）",
            len(echo_hits) >= 1, f"含引用格式的发言: {len(echo_hits)}/2")
    return r


def t8_compact(env: dict, workdir: Path) -> TestResult:
    topic = workdir / "t8.md"
    # compact_threshold 调小以确保触发
    topic_yaml = TOPIC_YAML.replace("compact_threshold: 175000", "compact_threshold: 400")
    topic.write_text(topic_yaml)
    log = workdir / "t8.json"

    run_cmd([sys.executable, "-m", "debate_tool", "run", str(topic),
             "--rounds", "3", "--output", str(log)], env, "T8-run")

    data = load_log(log)
    r = TestResult("T8")
    errs = validate_log_format(data, "T8")
    r.check("log 格式正确", not errs, "; ".join(errs) if errs else "")

    all_e = all_entries_of(data)
    checkpoints = [e for e in all_e if e.get("tag") == "compact_checkpoint"]
    r.check("有 compact_checkpoint 条目", len(checkpoints) >= 1,
            f"checkpoint 数: {len(checkpoints)}")

    # 验证 checkpoint 含有效 state（JSON 内嵌）
    valid_state = False
    for cp in checkpoints:
        state = cp.get("state") or {}
        if state.get("participants") and state.get("disputes") is not None:
            valid_state = True
            break
    r.check("compact_checkpoint 含有效 state 结构", valid_state)

    # 手动 compact
    result = run_cmd([sys.executable, "-m", "debate_tool", "compact", str(log)],
                     env, "T8-compact")
    r.check("manual compact 执行成功（无崩溃）", True)
    r.check("manual compact 输出 token 报告",
            "Token:" in result.stdout or "压缩完成" in result.stdout,
            result.stdout[-300:])
    return r


def t9_canary(env: dict, workdir: Path) -> TestResult:
    """金丝雀上下文连续性测试（constraints 清空，防止作弊）"""
    topic = workdir / "t9_canary.md"
    topic.write_text(CANARY_TOPIC_YAML)
    resume_topic = workdir / "t9_resume.md"
    resume_topic.write_text(CANARY_RESUME_YAML)
    log = workdir / "t9.json"

    run_cmd([sys.executable, "-m", "debate_tool", "run", str(topic),
             "--rounds", "3", "--output", str(log)], env, "T9-run")

    data = load_log(log)
    r = TestResult("T9")
    errs = validate_log_format(data, "T9")
    r.check("log 格式正确", not errs, "; ".join(errs) if errs else "")

    # 找第2轮发言（第3、4条 speech entry，索引2和3）
    all_e = all_entries_of(data)
    speeches = [e for e in all_e if not e.get("tag")]
    canary_re = re.compile(r"\[CANARY-[A-Z0-9\-]+\]")

    r2_speeches = speeches[2:4] if len(speeches) >= 4 else []
    planted: dict[str, str] = {}  # name → actual tag
    for sp in r2_speeches:
        m = canary_re.search(sp.get("content", ""))
        if m:
            planted[sp["name"]] = m.group(0)

    r.check("第2轮两辩手均输出了 CANARY 标签",
            len(planted) == 2, f"植入标签: {planted}")

    if len(planted) < 2:
        r.fail("无法继续验证（植入失败）")
        return r

    # 验证 compact 确实触发了
    checkpoints = [e for e in all_e if e.get("tag") == "compact_checkpoint"]
    r.check("compact 至少触发一次（确保测试有效）",
            len(checkpoints) >= 1, f"checkpoint 数: {len(checkpoints)}")

    # resume（constraints 清空，模型无法从系统提示作弊）
    run_cmd([sys.executable, "-m", "debate_tool", "resume", str(log),
             str(resume_topic), "--rounds", "1"], env, "T9-resume")

    data2 = load_log(log)
    entries2 = entries_of(data2)
    speeches2 = [e for e in entries2 if not e.get("tag")]
    resume_speeches = speeches2[-2:]  # 最后2条是续跑轮发言

    for sp in resume_speeches:
        name = sp["name"]
        expected = planted.get(name, "")
        content = sp.get("content", "")
        found = canary_re.search(content)
        actual = found.group(0) if found else "(未找到)"
        correct = actual == expected
        r.check(f"{name} 正确复述了金丝雀标签",
                correct, f"期望={expected!r} 实际={actual!r}")
    return r


# ── 报告输出 ──────────────────────────────────────────────────────────────────

ALL_TESTS = {
    "T1": t1_basic_run,
    "T2": t2_cot,
    "T3": t3_cross_exam,
    "T4": t4_early_stop,
    "T5": t5_resume_message,
    "T6": t6_resume_guide,
    "T7": t7_resume_echo,
    "T8": t8_compact,
    "T9": t9_canary,
}


def print_result(r: TestResult) -> None:
    status = "✅ PASS" if r.passed else "❌ FAIL"
    print(f"\n{status}  {r.name}")
    for desc, ok, detail in r.checks:
        mark = "  ✓" if ok else "  ✗"
        line = f"{mark} {desc}"
        if detail:
            line += f"  [{detail}]"
        print(line)


def main() -> int:
    selected = sys.argv[1:] if len(sys.argv) > 1 else list(ALL_TESTS.keys())
    unknown = [t for t in selected if t not in ALL_TESTS]
    if unknown:
        print(f"未知测试: {unknown}，可用: {list(ALL_TESTS)}", file=sys.stderr)
        return 1

    print("读取 API 凭证...", end=" ", flush=True)
    env = prepare_env()
    print("OK")

    if WORKDIR.exists():
        shutil.rmtree(WORKDIR)
    WORKDIR.mkdir(parents=True)

    results: list[TestResult] = []
    for name in selected:
        print(f"\n{'─'*50}")
        print(f"▶ 运行 {name}...")
        try:
            r = ALL_TESTS[name](env, WORKDIR)
        except Exception as exc:
            r = TestResult(name)
            r.fail("测试执行异常", str(exc)[-300:])
        print_result(r)
        results.append(r)

    # 汇总
    print(f"\n{'═'*50}")
    print("汇总")
    print(f"{'═'*50}")
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    for r in results:
        print(f"  {'✅' if r.passed else '❌'} {r.name}")
    print(f"\n{passed}/{total} 通过")
    print(f"工作目录: {WORKDIR}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
