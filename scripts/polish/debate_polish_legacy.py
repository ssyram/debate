#!/usr/bin/env python3
"""scripts/debate_polish.py — automated debate polish loop.

Usage:
    python3 scripts/debate_polish.py <topic.md>          [--iterations N] ...
    python3 scripts/debate_polish.py <log.json> --resume-first <resume_topic.md> ...
    python3 scripts/debate_polish.py <log.json> --check-first  <summary.md>      ...

Options:
    --iterations N      大循环次数（默认 3）
    --dry-run           打印计划不执行
    --claude-bin PATH   claude 可执行文件（默认 claude）
    --inner-max M       内层 rewrite+verify 最大次数（默认 2）
    --refine-model MODEL  内层 claude 调用使用的模型（默认 claude-haiku-4-5-20251001）
"""

import subprocess, argparse, re, sys
from pathlib import Path
from textwrap import dedent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from debate_tool.log_util import load_log_or_die
from debate_tool.config_ops import resolve_effective_config


# ── Logging ────────────────────────────────────────────────────────────────────

def dlog(msg): print(f"\033[36m[polish]\033[0m {msg}", flush=True)


# ── subprocess ─────────────────────────────────────────────────────────────────

def _read(proc):
    lines = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    proc.wait()
    return lines

def capture_run(cmd):
    dlog(f"$ {' '.join(map(str, cmd))}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = _read(proc)
    if proc.returncode != 0: raise RuntimeError(f"Command failed (code {proc.returncode})")
    return lines

def run_silent(cmd):
    dlog(f"$ {' '.join(map(str, cmd))}")
    subprocess.run(cmd, check=True)

def run_with_heartbeat(cmd, max_attempts=3, stall_timeout=300):
    import time, threading
    for attempt in range(1, max_attempts + 1):
        dlog(f"$ {' '.join(map(str, cmd))}" + (f"  (attempt {attempt}/{max_attempts})" if attempt > 1 else ""))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        last_active = [time.monotonic()]
        done = [False]

        def _reader():
            for line in proc.stdout:
                print(line, end="", flush=True)
                last_active[0] = time.monotonic()
            done[0] = True

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        killed = False
        while not done[0]:
            time.sleep(10)
            if time.monotonic() - last_active[0] > stall_timeout:
                dlog(f"  no output for {stall_timeout}s, killing (attempt {attempt}/{max_attempts})")
                proc.kill()
                killed = True
                break

        t.join()
        rc = proc.wait()
        if rc == 0 and not killed:
            return
        dlog(f"  {'stalled' if killed else f'exited code {rc}'}, attempt {attempt}/{max_attempts}")

    raise RuntimeError(f"Command failed after {max_attempts} attempts: {' '.join(map(str, cmd))}")


# ── dry-run ────────────────────────────────────────────────────────────────────

def dry(cmd, note=""):
    dlog(f"[dry] {' '.join(map(str, cmd))}" + (f"  # {note}" if note else ""))
    return []


# ── paths ──────────────────────────────────────────────────────────────────────

def to_summary(log): return log.parent / log.name.replace("_debate_log.json", "_debate_summary.md")

def latest_log(topic):
    dlog(f"Searching latest log for {topic.stem}")
    logs = sorted(topic.parent.glob(f"{topic.stem}_*_debate_log.json"), key=lambda p: p.stat().st_mtime)
    if not logs: raise RuntimeError(f"No debate log found for {topic.stem}")
    return logs[-1]

def parse_log(lines, topic):
    """优先从 debate-tool stdout 正则匹配 log 路径；fallback 找目录下最新的 log 文件。"""
    dlog("Extracting log path from output")
    for line in lines:
        m = re.search(r'[\w./_-]+_debate_log\.json', line)
        if m: return Path(m.group())
    return latest_log(topic)

def parse_summary(lines, log):
    """从 debate-tool stdout 的 ✅ 完成行解析 summary 路径；fallback to_summary(log)。"""
    dlog("Extracting summary path from output")
    for line in lines:
        m = re.search(r'[\w./_-]+_debate_summary\.md', line)
        if m: return Path(m.group())
    return to_summary(log)

def base_stem(args):
    """log.json 输入时剥离时间戳后缀，使 polish 目录名与 topic.md 模式一致。"""
    if args.input.suffix != ".json": return args.input.stem
    return re.sub(r'_\d{8}_\d{6}_debate_log$', '', args.input.stem) or args.input.stem


# ── state init ─────────────────────────────────────────────────────────────────

def init_state(args):
    dlog(f"Mode: {args.mode}")
    issues = [args.issues_first] if getattr(args, 'issues_first', None) else []
    if args.mode == "run":
        return {"log": None, "summaries": [], "issues": issues}
    # resume_first / check_first：log 路径已知，直接从 args.input 初始化
    return {"log": args.input, "summaries": [], "issues": issues}


# ── Step A: run / resume ───────────────────────────────────────────────────────

def _planned_log(pd):
    return pd / "log.json"

def _planned_summary(pd):
    return pd / "summary.md"

def _debate_cmd(args, state, i, pd):
    """run 模式首轮跑全新辩论；其余均为 resume。
    resume_first 模式首轮用用户指定的 resume_topic；后续轮用 pd/resume_{i}.md。"""
    summary_args = ["--output-summary", str(_planned_summary(pd))]
    if args.mode == "run" and i == 1:
        return ["python3", "-m", "debate_tool", "run", str(args.input),
                "--output", str(_planned_log(pd))] + summary_args
    rt = args.resume_first if (args.mode == "resume_first" and i == 1) else pd / f"resume_{i}.md"
    return ["python3", "-m", "debate_tool", "resume", str(state["log"]), str(rt)] + summary_args


_FAIL_MARKERS = ["[调用失败", "调用失败:", "Request URL is missing"]

def _check_summary_or_die(summary_path):
    if not summary_path.exists():
        sys.exit(f"❌ Summary 文件不存在: {summary_path}")
    text = summary_path.read_text(encoding="utf-8")
    for marker in _FAIL_MARKERS:
        if marker in text:
            sys.exit(f"❌ 生成失败，中止 polish。\n  {summary_path}\n  内容前 200 字: {text[:200]}")


def step_a(args, state, i, pd):
    dlog(f"[{i}] Step A: debate")
    cmd   = _debate_cmd(args, state, i, pd)
    lines = dry(cmd) if args.dry_run else capture_run(cmd)
    if args.mode == "run" and i == 1:
        state["log"] = Path(f"<dry-log-1.json>") if args.dry_run else _planned_log(pd)
    summary = _planned_summary(pd)
    if args.dry_run:
        state["summaries"].append(summary)
        return
    _check_summary_or_die(summary)
    state["summaries"].append(summary)

def maybe_step_a(args, state, i, pd):
    """check_first 首轮：把给定 summary 直接注入 state，跳过 debate 运行。其余轮正常走 step_a。"""
    if args.mode == "check_first" and i == 1: return state["summaries"].append(args.check_first)
    step_a(args, state, i, pd)


# ── Step B: finegrained-check ──────────────────────────────────────────────────

def build_prompt(summary, pd, i):
    """Prompt generation — exempt from line-count constraint."""
    claims, issues = pd / f"claims_{i}.md", pd / f"issues_{i}.md"
    return dedent(f"""\
        /finegrained-check {summary}

        额外要求：在完成标准四阶段报告后，请额外写入以下两个文件：

        1. 文件路径：{claims}
           内容：所有过程内容，包括所有 claims 、矛盾分析、缺漏纬度分析等

        2. 文件路径：{issues}
           内容：只包含所有已识别问题（矛盾、遗漏、矩阵空洞），按严重性分组排序：
           - ## 高严重度
           - ## 中严重度
           - ## 低严重度
           每条格式：`- [类型] Px vs Py / Px依赖B：一句话说明`

        **如果 {summary} 找不到文件或者运行失败直接拒绝执行，不要犹豫**
        """)

def step_b(args, state, i, pd):
    dlog(f"[{i}] Step B: finegrained-check on {state['summaries'][-1].name}")
    state["issues"].append(pd / f"issues_{i}.md")
    prompt = build_prompt(state["summaries"][-1], pd, i)
    cmd = _build_check_cmd(args, prompt) if not args.dry_run else _build_check_cmd(args, "<finegrained-prompt>")
    if args.dry_run: return dry(cmd)
    run_with_heartbeat(cmd)


# ── Step C / D: generate resume topic ─────────────────────────────────────────

ISSUES_INSTR = "请在你的总结中，首先针对最新列出的问题清单，逐一给出裁定与修复方向。"
JUDGE_RULINGS_INSTR = "请在你的总结中，对以下问题清单逐一做出裁定。"

def load_judge_instr(log_path):
    """合并 initial_config + 所有 config_override entries，返回最终有效的 judge_instructions。"""
    cfg = resolve_effective_config(load_log_or_die(Path(log_path)))
    return cfg.get("judge_instructions", "")

def prepend_instr(existing, line):
    """幂等前置：line 已含于 existing 则原样返回；否则置于最前，与原文间留一空行。"""
    if line in existing: return existing
    return line + ("\n\n" + existing.strip() if existing.strip() else "")

def yaml_block(text):
    """将多行文本统一缩进 2 格，用于 YAML block scalar（|）。"""
    return "\n".join("  " + l for l in text.splitlines())


# ── issue counting ─────────────────────────────────────────────────────────────

def count_under(text, heading):
    m = re.search(rf'##\s*{re.escape(heading)}(.*?)(?=\n##[^#]|\Z)', text, re.DOTALL)
    return len(re.findall(r'^\s*- ', m.group(1), re.MULTILINE)) if m else 0

def count_issues(path):
    dlog(f"Counting issues in {path.name}")
    if not path.exists(): return (0, 0, 0)
    t = path.read_text()
    return count_under(t, "高严重度"), count_under(t, "中严重度"), count_under(t, "低严重度")


# ── report ─────────────────────────────────────────────────────────────────────

def report_line(i, summary, issues, design_final=None):
    h, m, l = count_issues(issues)
    line = f"## Iteration {i}\n- Summary: `{summary}`\n- Issues: 高={h} 中={m} 低={l}\n"
    if design_final and design_final.exists():
        line += f"- Design final: `{design_final}`\n"
    return line

def write_report(pd, state, args=None):
    dlog("Writing polish report")
    lines = [f"# Debate Polish Report\n\nFinal log: `{state['log']}`\n\n"]
    for i, (s, ip) in enumerate(zip(state["summaries"][:args.iterations] if args else state["summaries"], state["issues"]), 1):
        df = pd / f"design_{i}_final.md"
        lines.append(report_line(i, s, ip, df))
    (pd / "polish_report.md").write_text("\n".join(lines))


# ── Refine constants ───────────────────────────────────────────────────────────

COMPACT_REFINE_MSG = (
    "重点记录：1) 设计演进轨迹（哪些概念/方案何时被修改采纳及原因）；"
    "2) 已废弃路径（所有被否决方案及废弃理由，已否决路径不得以变体重新提出）；"
    "3) 当前各方最新立场与共识。"
    "淡化具体论证细节，突出结论与演进脉络。"
)

# ── Refine helpers ─────────────────────────────────────────────────────────────

def _write_prompt_file(prompt):
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".md", prefix="polish_prompt_")
    os.write(fd, prompt.encode())
    os.close(fd)
    return path

def _build_llm_cmd(args, prompt, *, model=None):
    """构建 LLM CLI 命令。支持 claude 和 opencode 两种后端。"""
    if getattr(args, 'use_opencode', False):
        pfile = _write_prompt_file(prompt)
        cmd = ["opencode", "run"]
        m = model or getattr(args, 'refine_model', None)
        if m:
            cmd += ["-m", m]
        cmd += ["Read and execute the instructions in the attached file exactly.", "-f", pfile]
        return cmd
    cmd = [args.claude_bin, "--dangerously-skip-permissions"]
    m = model or getattr(args, 'refine_model', None)
    if m:
        cmd += ["--model", m]
    cmd += ["-p", prompt]
    return cmd

def _build_check_cmd(args, prompt):
    """构建 finegrained-check 命令（step_b 用，不指定 refine_model）。"""
    if getattr(args, 'use_opencode', False):
        pfile = _write_prompt_file(prompt)
        cmd = ["opencode", "run"]
        if getattr(args, 'opencode_model', None):
            cmd += ["-m", args.opencode_model]
        cmd += ["Read and execute the instructions in the attached file exactly.", "-f", pfile]
        return cmd
    return [args.claude_bin, "--dangerously-skip-permissions", "-p", prompt]

def claude_call(args, prompt):
    if args.dry_run:
        dry(_build_llm_cmd(args, prompt))
        return ""
    if getattr(args, 'use_opencode', False):
        return _http_call(args.refine_model, prompt)
    cmd = _build_llm_cmd(args, prompt)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout

def _http_call(model, prompt):
    import urllib.request, json as _json, os
    url = os.environ.get("DEBATE_BASE_URL", "").rstrip("/")
    key = os.environ.get("DEBATE_API_KEY", "")
    payload = _json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8000,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=300) as r:
        data = _json.loads(r.read())
    return data["choices"][0]["message"]["content"]

def step_b2_compact(args, state):
    dlog("Step B2: compact")
    cmd = ["python3", "-m", "debate_tool", "compact", str(state["log"]), "--message", COMPACT_REFINE_MSG]
    if args.mode == "run" and args.input.suffix == ".md":
        cmd += ["--topic", str(args.input)]
    if args.dry_run: return dry(cmd)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        dlog("Step B2: compact failed (skipped)")

def build_resume_judge_body(current_design_text, issues_text):
    parts = ["# 本轮目的\n\n基于 finegrained-check 识别的问题，各辩手聚焦以下待裁定问题，逐一给出立场和方案。\n如对已裁定内容有异议，请明确声明「不服」并给出理由。\n"]
    parts.append("## 当前设计文档（以此为准）\n\n" + current_design_text.strip() + "\n")
    parts.append("## 待裁定问题清单\n\n" + issues_text.strip() + "\n")
    return "\n".join(parts)

def step_c_gen_resume_judge(args, state, i, pd, current_design_path):
    dlog(f"[{i}] Step C: generate resume_judge_{i}.md")
    path = pd / f"resume_judge_{i}.md"
    if args.dry_run:
        dlog(f"[dry] Would write {path}")
        return path
    current_design = current_design_path.read_text() if current_design_path.exists() else "(设计文档不存在)"
    issues = (pd / f"issues_{i}.md").read_text() if (pd / f"issues_{i}.md").exists() else "(issues 不存在)"
    body = build_resume_judge_body(current_design, issues)
    instr = load_judge_instr(state["log"])
    instr = prepend_instr(instr, JUDGE_RULINGS_INSTR)
    front = f"---\njudge_instructions: |\n{yaml_block(instr)}\n---\n\n"
    path.write_text(front + body)
    return path

def step_d_resume_judge(args, state, i, pd):
    dlog(f"[{i}] Step D (refine): pure judgements resume")
    resume_judge_path = pd / f"resume_judge_{i}.md"
    cmd = ["python3", "-m", "debate_tool", "resume", str(state["log"]), str(resume_judge_path)]
    lines = dry(cmd) if args.dry_run else capture_run(cmd)
    if not args.dry_run:
        state["summaries"].append(parse_summary(lines, state["log"]))
    else:
        state["summaries"].append(Path(f"<dry-ruling-summary-{i}.md>"))

def extract_rulings(summary_path, rulings_path, args):
    """用 haiku 从 debate summary 提取结构化裁定，写入 rulings_path。"""
    dlog(f"Extracting rulings from {summary_path.name}")
    if args.dry_run:
        dlog(f"[dry] Would write {rulings_path}")
        return
    content = summary_path.read_text() if summary_path.exists() else ""
    prompt = (
        "从以下辩论总结中，提取裁判给出的所有裁定。"
        "保留原始编号和措辞，按「### 裁定 N」格式输出，不添加额外内容：\n\n"
        + content
    )
    result = claude_call(args, prompt)
    rulings_path.write_text(result)

def build_rewrite_prompt(design_path, rulings_path):
    design = design_path.read_text() if design_path.exists() else ""
    rulings = rulings_path.read_text() if rulings_path.exists() else ""
    return dedent(f"""\
        你是文档一致化专家。基于以下裁定清单，修改设计文档使其完整体现所有裁定。

        要求：
        - 对每条裁定，在文档所有相关位置一致体现
        - 引入新状态名/枚举值时，必须同步更新文档中所有枚举表
        - 不得引入裁定以外的新概念
        - 不得删减裁定未涉及的内容
        - 直接输出完整修改后的文档，不加说明

        ## 裁定清单

        {rulings}

        ## 当前设计文档

        {design}
        """)

def build_verify_prompt(design_path, rulings_path):
    design = design_path.read_text() if design_path.exists() else ""
    rulings = rulings_path.read_text() if rulings_path.exists() else ""
    return dedent(f"""\
        你是一致性校验专家。逐条核对每条裁定是否在设计文档中完整体现。

        对每处遗漏/不一致，判断类型：
        - rewrite_needed：应用有遗漏，继续内层循环可修复
        - new_ruling_needed：超出现有裁定范围，需新一轮辩论

        最后一行必须是以下格式之一：
        需要继续重写: true
        需要继续重写: false

        ## 裁定清单

        {rulings}

        ## 设计文档

        {design}
        """)

def needs_rewrite(verify_path):
    if not verify_path.exists(): return False
    text = verify_path.read_text()
    m = re.search(r'需要继续重写:\s*(true|false)', text)
    return m.group(1).lower() == "true" if m else False

def _last_verify(pd, i, inner_max):
    for j in range(inner_max, 0, -1):
        p = pd / f"verify_{i}_{j}.md"
        if p.exists(): return p
    return pd / f"verify_{i}_1.md"

def step_e_inner(args, state, i, pd, current_design_path):
    dlog(f"[{i}] Step E inner loop: rewrite + verify (max {args.inner_max})")
    rulings_path = pd / f"rulings_{i}.md"
    design_in = current_design_path
    for j in range(1, args.inner_max + 1):
        design_out = pd / f"design_{i}_{j}.md"
        verify_out = pd / f"verify_{i}_{j}.md"
        # rewrite
        dlog(f"  [{i}/{j}] rewrite: {design_in.name} → {design_out.name}")
        if not args.dry_run:
            rewrite_prompt = build_rewrite_prompt(design_in, rulings_path)
            result = claude_call(args, rewrite_prompt)
            design_out.write_text(result)
            if not design_out.exists() or not design_out.read_text().strip():
                dlog(f"  Warning: {design_out.name} empty or not created by rewrite; copying input")
                design_out.write_text(design_in.read_text())
        else:
            dry(["<rewrite>", str(design_in), "→", str(design_out)])
        # verify
        dlog(f"  [{i}/{j}] verify: {design_out.name}")
        if not args.dry_run:
            verify_prompt = build_verify_prompt(design_out, rulings_path)
            verify_result = claude_call(args, verify_prompt)
            verify_out.write_text(verify_result)
        else:
            dry(["<verify>", str(design_out)])
        design_in = design_out
        # exit condition
        if not args.dry_run and not needs_rewrite(verify_out):
            dlog(f"  Inner loop complete at j={j}")
            break
    # create design_{i}_final.md
    final = pd / f"design_{i}_final.md"
    if not args.dry_run:
        final.write_text(design_in.read_text())
    else:
        dlog(f"[dry] Would write {final}")
    return final

def build_resume_refine(path, log_path, design_final_path, verify_last_path):
    dlog(f"Writing refine resume topic: {path.name}")
    design = design_final_path.read_text() if design_final_path.exists() else ""
    verify = verify_last_path.read_text() if verify_last_path.exists() else ""
    # 检查 verify 中是否有 new_ruling_needed
    has_new = "new_ruling_needed" in verify
    instr = load_judge_instr(log_path)
    new_issues_note = ""
    if has_new:
        new_issues_note = "\n\n## 需新裁定的问题\n\n以下问题超出上轮裁定范围，请本轮优先讨论并给出新裁定：\n\n" + \
            "\n".join(l for l in verify.splitlines() if "new_ruling_needed" in l)
        instr = prepend_instr(instr, ISSUES_INSTR)
    front = f"---\njudge_instructions: |\n{yaml_block(instr)}\n---\n\n" if instr else ""
    body = (
        "# 继续辩论\n\n"
        "以下是经本轮裁定+一致化后的最新设计，请以此为准继续讨论。\n\n"
        "## 最新设计文档\n\n" + design.strip() + "\n"
        + new_issues_note
    )
    path.write_text(front + body)

def _run_iteration_refine(args, state, i, pd):
    """--refine 模式的内层：B2 compact → C gen_judge → D resume_judge → extract_rulings → E inner_loop → build next resume"""
    # B2: compact
    step_b2_compact(args, state)
    # 确定 current_design：始终用 Step A 刚产出的 summary（state["summaries"] 末尾）
    current_design_path = state["summaries"][-1]
    # C: gen resume_judge
    step_c_gen_resume_judge(args, state, i, pd, current_design_path)
    # D: pure judgements resume
    step_d_resume_judge(args, state, i, pd)
    # extract rulings from latest summary
    rulings_path = pd / f"rulings_{i}.md"
    if not args.dry_run:
        extract_rulings(state["summaries"][-1], rulings_path, args)
    else:
        dlog(f"[dry] Would extract rulings → {rulings_path}")
    # E: inner loop
    design_final = step_e_inner(args, state, i, pd, current_design_path)
    # generate next resume (if more iterations to go)
    if i < args.iterations:
        next_resume = pd / f"resume_{i+1}.md"
        verify_last = _last_verify(pd, i, args.inner_max)
        if args.dry_run:
            dlog(f"[dry] Would write {next_resume}")
        else:
            build_resume_refine(next_resume, state["log"], design_final, verify_last)


# ── main loop ──────────────────────────────────────────────────────────────────

def run_iteration(args, state, i, pd):
    dlog(f"=== Iteration {i}/{args.iterations} ===")
    maybe_step_a(args, state, i, pd)
    if not (i == 1 and getattr(args, 'issues_first', None)):
        step_b(args, state, i, pd)
    else:
        dlog(f"[{i}] Step B: skipped (issues provided via --issues-first)")
    _run_iteration_refine(args, state, i, pd)

def run_all(args):
    dlog(f"Starting polish loop: {args.iterations} iterations on {args.input.name}")
    pd = args.input.parent / f"{base_stem(args)}_polish"
    pd.mkdir(exist_ok=True)
    state = init_state(args)
    for i in range(1, args.iterations + 1): run_iteration(args, state, i, pd)
    write_report(pd, state, args)


# ── CLI validation ─────────────────────────────────────────────────────────────

def _validate_json(args):
    dlog("Validating log.json flags")
    if not args.resume_first and not args.check_first:
        sys.exit("Error: log.json input requires --resume-first or --check-first")
    if args.resume_first and args.check_first:
        sys.exit("Error: --resume-first and --check-first are mutually exclusive")
    if args.issues_first and not args.check_first:
        sys.exit("Error: --issues-first requires --check-first")

def validate(args):
    dlog("Validating arguments")
    if args.input.suffix == ".json": return _validate_json(args)
    if args.resume_first or args.check_first:
        sys.exit("Error: --resume-first / --check-first only valid with log.json input")

def resolve_mode(args):
    if args.input.suffix != ".json": return "run"
    return "check_first" if args.check_first else "resume_first"


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Automated debate polish loop")
    p.add_argument("input",            type=Path, help="Topic .md or debate log .json")
    p.add_argument("--resume-first",   type=Path, default=None, metavar="RESUME_TOPIC", dest="resume_first")
    p.add_argument("--check-first",    type=Path, default=None, metavar="SUMMARY",      dest="check_first")
    p.add_argument("--issues-first",   type=Path, default=None, metavar="ISSUES",       dest="issues_first")
    p.add_argument("--iterations",     type=int,  default=3,    metavar="N")
    p.add_argument("--dry-run",        action="store_true",                   dest="dry_run")
    p.add_argument("--topic",          type=Path, default=None, metavar="TOPIC", dest="topic",
                   help="Topic .md file (for compact; auto-inferred from input if .md)")
    p.add_argument("--claude-bin",     default="claude", metavar="PATH",      dest="claude_bin")
    p.add_argument("--inner-max",      type=int,  default=2,    metavar="M",  dest="inner_max")
    p.add_argument("--refine-model",   default=None, metavar="MODEL", dest="refine_model")
    p.add_argument("--use-opencode",   action="store_true",                   dest="use_opencode",
                   help="Use opencode instead of claude for finegrained-check and refine steps")
    p.add_argument("--opencode-model", default="yunwu/qwen3.5-plus", metavar="MODEL", dest="opencode_model",
                   help="Model for opencode finegrained-check (default: yunwu/qwen3.5-plus)")
    args = p.parse_args()
    if args.refine_model is None:
        args.refine_model = "qwen3.5-plus" if args.use_opencode else "claude-haiku-4-5-20251001"
    return args

def main():
    args = parse_args()
    validate(args)
    args.mode = resolve_mode(args)
    if not args.dry_run and not args.input.exists():
        sys.exit(f"Error: input file not found: {args.input}")
    run_all(args)

if __name__ == "__main__": main()
