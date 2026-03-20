"""极简 resume 入口 — load log → patch cfg → core_loop"""

from pathlib import Path

from debate_tool.config_ops import (
    _apply_overrides,
    _describe_overrides,
    resolve_effective_config,
    validate_topic_log_consistency,
)
from debate_tool.core_loop import core_loop, die, judge_phase
from debate_tool.debug_log import dlog
from debate_tool.log_util import load_log_or_die, write_summary_resume
from debate_tool.topic_parser import parse_resume_topic


def base_round(log, cfg):
    """已完成轮数"""
    # 必须用 all_entries() 计入 compact 后存档的旧轮次
    return len([e for e in log.all_entries() if not e.get("tag")]) // max(len(cfg["debaters"]), 1)


def patch_resume_cfg(cfg, log, extra_rounds, guide_prompt, cross_exam, cot_length):
    """设置 cfg["rounds"]，处理 guide/cot，返回 (brnd, xrounds)"""
    brnd = base_round(log, cfg)
    cfg["rounds"] = brnd + extra_rounds
    if guide_prompt:
        # guide 覆盖所有续跑轮次的 task，包括 final 轮
        guide_task = f"回应其他辩手观点，深化立场。400-600 字\n\n观察者指引：{guide_prompt}"
        cfg["middle_task"] = guide_task
        cfg["final_task"] = guide_task
    if cot_length is not None:
        cfg["cot"] = cot_length

    if cross_exam is None or cross_exam == 0:
        xrounds = set()
    elif cross_exam < 0:
        xrounds = set(range(brnd + 1, cfg["rounds"]))
    else:
        xrounds = set(range(brnd + 1, min(brnd + cross_exam, cfg["rounds"] - 1) + 1))

    return brnd, xrounds


def merge_resume_overrides(overrides, resume_topic_path):
    if not resume_topic_path:
        return overrides or {}
    rt, _ = parse_resume_topic(resume_topic_path)
    rt.pop("rounds", None)
    rt.pop("guide", None)
    return {**(overrides or {}), **rt}


def apply_and_validate(cfg, log, overrides, cross_exam, cot_length, force):
    dlog(f"[apply_and_validate] overrides={list((overrides or {}).keys())}")
    if ("add_debaters" in (overrides or {}) or "drop_debaters" in (overrides or {})) and not force:
        die("❌ add_debaters / drop_debaters 需要 --force 确认（辩手变更是不可逆操作）")
    if overrides:
        _apply_overrides(cfg, overrides)
        log.add("@系统", _describe_overrides(overrides), "config_override", extra={"overrides": overrides})
    if cross_exam is not None:
        cfg["cross_exam"] = cross_exam
    if cot_length is not None:
        cfg["cot"] = cot_length
    validate_topic_log_consistency(log, force=force)
    check_min_debaters(cfg)


def check_min_debaters(cfg):
    if len(cfg["debaters"]) >= 2:
        return
    names = [d["name"] for d in cfg["debaters"]]
    die(f"❌ 辩论至少需要 2 名辩手，当前只有 {len(names)} 名：{names}")


def load_and_patch(log_path, resume_topic_path, overrides, cross_exam, cot_length, force):
    dlog(f"[load_and_patch] {log_path}")
    log = load_log_or_die(log_path)
    cfg = resolve_effective_config(log)
    cfg["topic_body"] = log.topic  # initial_config 不存 topic_body，从 log.topic 补
    overrides = merge_resume_overrides(overrides, resume_topic_path)
    apply_and_validate(cfg, log, overrides, cross_exam, cot_length, force)
    return log, cfg


async def resume(
    *,
    log_path: Path,
    resume_topic_path: "Path | None" = None,
    cfg_overrides: "dict | None" = None,
    message: str = "",
    extra_rounds: int = 1,
    cross_exam: "int | None" = None,
    guide_prompt: str = "",
    force: bool = False,
    cot_length: "int | None" = None,
    summary_path: "Path | None" = None,
    no_judge: bool = False,
) -> None:
    dlog(f"[resume] log={log_path} rounds={extra_rounds} guide={bool(guide_prompt)}")
    log, cfg = load_and_patch(log_path, resume_topic_path, cfg_overrides, cross_exam, cot_length, force)
    if message:
        log.add("👤 观察者", message, "human")
        print("\n💬 已注入观察者消息")
    brnd, xrounds = patch_resume_cfg(cfg, log, extra_rounds, guide_prompt, cross_exam, cot_length)
    await core_loop(cfg, log, brnd, cfg.get("cot", cot_length), xrounds)
    if no_judge or cfg.get("no_judge"):
        print(f"\n✅ 续跑完成（跳过裁判）。日志: {log.path}")
        return
    summary = await judge_phase(cfg, log)
    write_summary_resume(log, cfg, summary, summary_path=summary_path)
