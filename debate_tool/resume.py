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
from debate_tool.topic_parser import parse_resume_topic, _parse_bool, _parse_cot, _coerce_int


def base_round(log, cfg):
    """已完成轮数"""
    # 必须用 all_entries() 计入 compact 后存档的旧轮次
    return len([e for e in log.all_entries() if not e.get("tag")]) // max(len(cfg["debaters"]), 1)


def patch_resume_cfg(cfg, log, extra_rounds, guide_prompt, cross_exam, cot_length):
    """设置 cfg["rounds"]，处理 guide/cot，返回 (brnd, xrounds)"""
    brnd = base_round(log, cfg)
    cfg["rounds"] = brnd + extra_rounds
    if guide_prompt:
        guide_task = f"回应其他辩手观点，深化立场。400-600 字\n\n观察者指引：{guide_prompt}"
        cfg["middle_task"] = guide_task
        cfg["final_task"] = guide_task
    if cot_length is not None:
        cfg["cot"] = cot_length

    from debate_tool.core_loop import compute_xexam_rounds, parse_cross_exam
    effective_cx = cross_exam if cross_exam is not None else cfg.get("cross_exam", 0)
    effective_cx = parse_cross_exam(effective_cx)
    xrounds = compute_xexam_rounds(effective_cx, extra_rounds, base_rnd=brnd)

    return brnd, xrounds


# ── Runtime fields that resume topic YAML can supply ─────
# These are popped from overrides dict and returned separately so they
# don't get recorded as config_override entries in the log.
_RESUME_RUNTIME_KEYS = ("rounds", "guide", "no_judge", "force", "message")


def merge_resume_overrides(overrides, resume_topic_path, *, cli_kwargs: "dict | None" = None):
    """Merge resume-topic YAML overrides with programmatic overrides.

    Returns (merged_overrides, runtime_dict) where runtime_dict contains
    keys from ``_RESUME_RUNTIME_KEYS`` extracted from the resume topic YAML.
    CLI kwargs always take precedence over resume topic values.
    """
    runtime: dict = {}
    if not resume_topic_path:
        return (overrides or {}), runtime
    rt, body = parse_resume_topic(resume_topic_path)
    for key in _RESUME_RUNTIME_KEYS:
        if key in rt:
            runtime[key] = rt.pop(key)
    if body and "message" not in runtime:
        runtime["message"] = body
    elif body and runtime.get("message"):
        runtime["message"] = runtime["message"] + "\n\n" + body

    merged = {**(overrides or {}), **rt}

    if cli_kwargs:
        for key in _RESUME_RUNTIME_KEYS:
            if key in cli_kwargs and cli_kwargs[key] not in (None, "", False, 0):
                runtime[key] = cli_kwargs[key]

    return merged, runtime


def apply_and_validate(cfg, log, overrides, cross_exam, cot_length, force):
    dlog("flow.resume.validate", f"overrides={list((overrides or {}).keys())}",
         overrides=list((overrides or {}).keys()))
    if ("add_debaters" in (overrides or {}) or "drop_debaters" in (overrides or {})) and not force:
        die("❌ add_debaters / drop_debaters 需要 --force 确认（辩手变更是不可逆操作）")
    if overrides:
        _apply_overrides(cfg, overrides)
        log.add("@系统", _describe_overrides(overrides), "config_override", extra={"overrides": overrides})
    if cross_exam is not None:
        from debate_tool.core_loop import parse_cross_exam
        cfg["cross_exam"] = parse_cross_exam(cross_exam)
    if cot_length is not None:
        cfg["cot"] = cot_length
    validate_topic_log_consistency(log, force=force)
    check_min_debaters(cfg)


def check_min_debaters(cfg):
    if len(cfg["debaters"]) >= 2:
        return
    names = [d["name"] for d in cfg["debaters"]]
    die(f"❌ 辩论至少需要 2 名辩手，当前只有 {len(names)} 名：{names}")


def load_and_patch(log_path, resume_topic_path, overrides, cross_exam, cot_length, force,
                   *, cli_kwargs: "dict | None" = None):
    dlog("flow.resume.load", f"path={log_path}", path=str(log_path))
    log = load_log_or_die(log_path)
    cfg = resolve_effective_config(log)
    cfg["topic_body"] = log.topic
    overrides, runtime = merge_resume_overrides(overrides, resume_topic_path, cli_kwargs=cli_kwargs)

    effective_force = force or _parse_bool(runtime.get("force", False))
    effective_cross_exam = cross_exam
    if effective_cross_exam is None and "cross_exam" in overrides:
        from debate_tool.core_loop import parse_cross_exam
        effective_cross_exam = parse_cross_exam(overrides.pop("cross_exam"))
    effective_cot = cot_length
    if effective_cot is None and "cot" in overrides:
        effective_cot = _parse_cot(overrides.pop("cot"))

    apply_and_validate(cfg, log, overrides, effective_cross_exam, effective_cot, effective_force)

    if _parse_bool(runtime.get("no_judge", False)):
        cfg["no_judge"] = True

    return log, cfg, runtime


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
    dlog("flow.resume", f"log={log_path} rounds={extra_rounds}",
         log=str(log_path), rounds=extra_rounds, guide=bool(guide_prompt))

    cli_kwargs = {
        "rounds": extra_rounds,
        "message": message,
        "guide": guide_prompt,
        "force": force,
        "no_judge": no_judge,
    }
    log, cfg, runtime = load_and_patch(
        log_path, resume_topic_path, cfg_overrides, cross_exam, cot_length, force,
        cli_kwargs=cli_kwargs,
    )

    effective_message = message or runtime.get("message", "")
    if effective_message:
        log.add("👤 观察者", effective_message, "human")
        print("\n💬 已注入观察者消息")

    effective_rounds = extra_rounds
    rt_rounds = runtime.get("rounds")
    if rt_rounds is not None and extra_rounds == 1:
        effective_rounds = _coerce_int(rt_rounds, extra_rounds)

    effective_guide = guide_prompt or runtime.get("guide", "")

    brnd, xrounds = patch_resume_cfg(cfg, log, effective_rounds, effective_guide, cross_exam, cot_length)
    await core_loop(cfg, log, brnd, cfg.get("cot", cot_length), xrounds)

    effective_no_judge = no_judge or cfg.get("no_judge", False)
    if effective_no_judge:
        print(f"\n✅ 续跑完成（跳过裁判）。日志: {log.path}")
        return
    summary = await judge_phase(cfg, log)
    write_summary_resume(log, cfg, summary, summary_path=summary_path)
