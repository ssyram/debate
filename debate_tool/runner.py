#!/usr/bin/env python3
"""debate-tool runner — CLI 入口、横幅、dry-run、compact"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from debate_tool.core import (
    DEFAULT_EARLY_STOP_THRESHOLD,
    estimate_tokens,
)
from debate_tool.compact_state import render_public_markdown
from debate_tool.compact_engine import _do_compact
from debate_tool.config_ops import _validate_api_config, resolve_effective_config
from debate_tool.core_loop import ENV_BASE_URL, ENV_API_KEY
from debate_tool.debug_log import init_debug_logging, dlog
from debate_tool.log_io import (
    build_log_path, LOG_FILE_SUFFIX, SUMMARY_FILE_SUFFIX,
)
from debate_tool.log_util import load_log_or_die
from debate_tool.topic_parser import parse_topic_file, _mask_key


# ── Compact CLI ──────────────────────────────────────────────────────────────

def compact_log(log_path: Path, *, keep_last: int = 0, message: str = "") -> None:
    dlog("flow.compact.cli", f"path={log_path}", path=str(log_path))
    log = load_log_or_die(log_path)
    cfg = build_cfg_from_log(log)
    if message:
        cfg["compact_message"] = message  # CLI --message 优先级最高，覆盖 log 内嵌值
    if keep_last > 0:
        cfg["keep_last"] = keep_last
    before = estimate_tokens("\n\n".join(e["content"] for e in log.entries))
    state, seq = run_compact_sync(log, cfg)
    print_compact_result(state, before, seq, log)


def build_cfg_from_log(log):
    ic = log.initial_config
    url = ((ic.get("debaters") or [{}])[0].get("base_url", "") or "")
    return {**ic, "base_url": ic.get("judge", {}).get("base_url", "") or url, "api_key": "", "topic_body": log.topic}


def run_compact_sync(log, cfg):
    dlog("flow.compact.run_sync", f"entries={len(log.entries)}", entries=len(log.entries))
    system_text = f"## 辩论议题\n\n{cfg['topic_body']}"
    compact_message = cfg.get("compact_message", "") or ""
    try:
        return asyncio.run(_do_compact(log, cfg, system_text, compact_message=compact_message))
    except ValueError as e:
        from debate_tool.core_loop import die
        die(f"\n  ❌ compact 配置缺失，无法压缩: {e}\n  请在 topic YAML 中配置 compact_model / compact_check_model 后重试。")


def print_compact_result(state, before, seq, log):
    after = estimate_tokens(render_public_markdown(state) if isinstance(state, dict) else state)
    print(f"\n📦 压缩完成:")
    print(f"   Token: {before} → {after} (checkpoint)")
    print(f"   Checkpoint seq: {seq}")
    print(f"   日志: {log.path}")


# ── Banner ───────────────────────────────────────────────────────────────────

def banner_lines(cfg):
    """构造横幅文本行"""
    lines = ["=" * 60, f"  {cfg['title']}"]
    flags = build_flag_list(cfg)
    if flags:
        lines.append(f"  [{', '.join(flags)}]")
    lines.append(f"  {cfg['rounds']} 轮 | 辩手: {', '.join(d['name'] for d in cfg['debaters'])}")
    lines.append(f"  裁判: {cfg['judge']['name']}")
    url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    if url:
        lines.append(f"  API: {url}")
    lines.append("=" * 60)
    return lines


def print_banner(cfg):
    """打印辩论启动横幅（纯 print）"""
    for line in banner_lines(cfg):
        print(line)


def build_flag_list(cfg):
    flags = []
    cross_exam = cfg.get("cross_exam", 0)
    if cross_exam:
        if isinstance(cross_exam, list):
            flags.append(f"质询(R{','.join(str(r) for r in cross_exam)})")
        elif cross_exam < 0:
            flags.append("质询(全轮)")
        elif cross_exam == 1:
            flags.append("质询(R1)")
        else:
            flags.append(f"质询(R1~R{cross_exam})")
    early = cfg.get("early_stop", 0.0)
    if early:
        flags.append(f"早停(≥{early:.0%})")
    cot = cfg.get("cot_length")
    if cot is not None:
        flags.append(f"CoT(≤{cot}t)" if cot > 0 else "CoT")
    return flags


# ── CLI: dry run ─────────────────────────────────────────────────────────────

def dry_run(cfg, topic_path, cli_cot):
    """dry-run 输出（纯 print，不受 6 行限制）"""
    stem = topic_path.stem
    out_dir = topic_path.parent
    effective_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    effective_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()
    effective_cot = cli_cot if cli_cot is not None else cfg.get("cot_length", None)
    cx = cfg.get("cross_exam", 0)

    print("=" * 60)
    print(f"  🔍 Dry Run — {cfg['title']}")
    print("=" * 60)
    print(f"\n  文件:     {topic_path}")
    print(f"  轮数:     {cfg['rounds']}")
    if isinstance(cx, list):
        print(f"  质询:     R{','.join(str(r) for r in cx)} 后")
    elif cx and cx < 0:
        print(f"  质询:     每轮")
    elif cx == 1:
        print(f"  质询:     R1 后")
    elif cx and cx > 1:
        print(f"  质询:     R1~R{cx} 后")
    else:
        print(f"  质询:     否")
    print(f"  早停:     {'是 (阈值 {:.0%})'.format(cfg.get('early_stop', 0.0)) if cfg.get('early_stop') else '否'}")
    if effective_cot is not None:
        print(f"  CoT:      是 ({'思考预算 ' + str(effective_cot) + ' token' if effective_cot > 0 else '无预算限制'})")
    else:
        print(f"  CoT:      否")
    print(f"  超时:     {cfg['timeout']}s")
    print(f"  max_reply_tokens: {cfg['max_reply_tokens']}")
    print(f"\n  辩手:")
    for d in cfg["debaters"]:
        print(f"    - {d['name']} ({d['model']}) — {d['style']}")
    j = cfg["judge"]
    print(f"\n  裁判:     {j['name']} ({j['model']}, max_tokens={j.get('max_tokens', 8000)})")
    if cfg["constraints"]:
        print(f"\n  约束:\n    {cfg['constraints'][:200]}")
    print(f"\n  议题 (前 300 字):\n    {cfg['topic_body'][:300]}...")
    print(f"\n  输出:")
    print(f"    日志:   {out_dir / f'{stem}_<timestamp>_debate_log.json'} (--output 可覆盖)")
    print(f"    总结:   {out_dir / f'{stem}{SUMMARY_FILE_SUFFIX}'}")
    print(f"\n  API:     {effective_url}")
    print(f"  API Key: {_mask_key(effective_key) if effective_key else '(未设置)'}")
    if cfg.get("base_url"):
        print("  (来源: front-matter)")
    elif os.environ.get("DEBATE_BASE_URL"):
        print("  (来源: 环境变量)")
    else:
        print("  (来源: 未设置)")

    api_issues = _validate_api_config(cfg)
    if api_issues:
        print("\n  ⚠️ API 配置不完整:")
        for issue in api_issues:
            print(f"    - {issue}")
        print("    请通过 front-matter（全局/辩手/裁判）或环境变量补齐 base_url / api_key")
    print(f"\n  Round 1: {cfg['round1_task'][:80]}...")
    print(f"  Middle:  {cfg['middle_task'][:80]}...")
    print(f"  Final:   {cfg['final_task'][:80]}...")
    if cfg["judge_instructions"]:
        print(f"  Judge:   {cfg['judge_instructions'][:80]}...")
    print("\n✅ 配置有效")


# ── CLI: main ────────────────────────────────────────────────────────────────

def main(argv=None):
    args = parse_run_args(argv)
    cfg = parse_topic_file(args.topic.resolve())
    apply_cli_overrides(cfg, args)
    if args.dry_run:
        return dry_run(cfg, args.topic.resolve(), args.cot_length)
    validate_or_die(cfg)
    init_debug_if_needed(args)
    print_banner(cfg)
    from debate_tool.run import run
    summary_path = args.output_summary.resolve() if args.output_summary else None
    asyncio.run(run(cfg, args.topic.resolve(), cot_length=args.cot_length, log_path=resolve_log_path(args), summary_path=summary_path, no_judge=args.no_judge))


def init_debug_if_needed(args):
    if args.debug is None:
        return
    init_debug_logging(args.debug)
    if args.debug is not True:
        print(f"  🐛 Debug 日志 → {args.debug}", file=sys.stderr)


def apply_cli_overrides(cfg, args):
    if args.cross_exam is not None:
        from debate_tool.core_loop import parse_cross_exam
        cfg["cross_exam"] = parse_cross_exam(args.cross_exam)
    if args.early_stop is not None:
        cfg["early_stop"] = args.early_stop
    if args.rounds is not None:
        cfg["rounds"] = args.rounds
    if getattr(args, 'no_judge', False):
        cfg["no_judge"] = True
    cfg.setdefault("cross_exam", 0)
    cfg.setdefault("early_stop", 0.0)


def validate_or_die(cfg):
    api_issues = _validate_api_config(cfg)
    if not api_issues:
        return
    from debate_tool.core_loop import die
    die("❌ 缺少 API 配置:\n  - " + "\n  - ".join(api_issues) + "\n请设置 DEBATE_BASE_URL / DEBATE_API_KEY，或在 topic front-matter 提供全局/辩手/裁判级 base_url / api_key")


def resolve_log_path(args):
    if args.output is not None:
        return args.output.resolve()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return args.topic.resolve().parent / f"{args.topic.resolve().stem}_{ts}{LOG_FILE_SUFFIX}"


def parse_run_args(argv):
    ap = argparse.ArgumentParser(
        description="运行辩论 — 读取 Markdown + YAML front-matter 驱动多模型辩论",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  debate-tool run my_topic.md\n"
            "  debate-tool run my_topic.md --rounds 5\n"
            "  debate-tool run my_topic.md --dry-run\n"
            "  debate-tool run my_topic.md --cross-exam\n"
            "  debate-tool run my_topic.md --cross-exam 3\n"
            "  debate-tool run my_topic.md --cross-exam -1\n"
            "  debate-tool run my_topic.md --cross-exam ALL\n"
            "  debate-tool run my_topic.md --cross-exam '[1,3,5]'\n"
            "  debate-tool run my_topic.md --cross-exam --early-stop\n"
            "\n"
            "质询:\n"
            "  --cross-exam [SPEC]  每轮后增加质询子回合\n"
            "                       N=前N轮, -1/ALL/*=全轮, [1,3,5]=指定轮次\n"
            "\n"
            "早停:\n"
            "  --early-stop      启用收敛早停 (观点趋同时跳过剩余轮次)\n"
            "\n"
            "环境变量:\n"
            "  DEBATE_API_KEY    API 密钥\n"
            "  DEBATE_BASE_URL   API 端点\n"
            "\n"
            "也可在 topic 文件的 YAML front-matter 中设置 base_url / api_key\n"
            "优先级: front-matter > 环境变量\n"
        ),
    )
    ap.add_argument("topic", type=Path, help="议题 Markdown 文件（含 YAML front-matter）")
    ap.add_argument("--rounds", type=int, default=None, help="覆盖辩论轮数")
    ap.add_argument("--dry-run", action="store_true", help="仅解析配置，不调用 LLM")
    ap.add_argument("--cross-exam", nargs="?", const="1", default=None, metavar="SPEC",
                    help="质询: N=前N轮, -1/ALL/*=全轮, [1,3,5]=指定轮次, false/0=不质询")
    ap.add_argument("--early-stop", nargs="?", type=float, const=DEFAULT_EARLY_STOP_THRESHOLD, default=None, metavar="T", help="启用收敛早停")
    ap.add_argument("--cot", "--think", dest="cot_length", nargs="?", type=int, const=0, default=None, metavar="LENGTH", help="为辩手启用思考空间 (CoT)")
    ap.add_argument("--output", type=Path, default=None, metavar="LOG_FILE", help="指定输出日志文件路径")
    ap.add_argument("--output-summary", type=Path, default=None, metavar="SUMMARY_FILE", dest="output_summary", help="指定总结文件输出路径")
    ap.add_argument("--no-judge", action="store_true", dest="no_judge", help="跳过裁判总结阶段")
    ap.add_argument("--debug", nargs="?", const=True, default=None, metavar="DEBUG_LOG", help="开启 debug 日志")
    return ap.parse_args(argv)


if __name__ == "__main__":
    main()
