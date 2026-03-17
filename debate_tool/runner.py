#!/usr/bin/env python3
"""
通用辩论框架 — 读取 Markdown + YAML front-matter 驱动多模型辩论。

用法:
    debate-tool run my_topic.md
    debate-tool run my_topic.md --rounds 5
    debate-tool run my_topic.md --dry-run
"""

import argparse
import asyncio
import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import httpx
import yaml

from debate_tool.core import (
    DEFAULT_DEBATERS,
    DEFAULT_JUDGE,
    DEFAULT_EARLY_STOP_THRESHOLD,
    check_convergence,
    estimate_tokens,
    build_compact_context,
    build_full_compact,
    DEFAULT_COMPACT_TRIGGER,
    parse_compact_checkpoint,
    DEFAULT_COMPACT_THRESHOLD,
)
from debate_tool.compact_state import (
    render_public_markdown,
    render_stance_for_system,
    build_phase_a_prompt,
    build_phase_b_prompt,
    build_validity_check_prompt,
    build_stance_drift_check_prompt,
    build_stance_correction_prompt,
    get_compact_model_config,
    get_check_model_config,
    get_embedding_config,
    validate_public_info,
    validate_participant_state,
    format_delta_entries_text,
    merge_pruned_paths_if_needed,
)
from debate_tool.debug_log import DebugLogger, init_debug_logging, dlog
from debate_tool.log_io import (
    LogFormatError, build_log_path, Log, identify_files,
    LOG_FILE_SUFFIX, SUMMARY_FILE_SUFFIX,
)
from debate_tool.topic_parser import (
    parse_topic_file, parse_resume_topic, _mask_key,
    _parse_early_stop, _parse_cot, _coerce_int,
    _normalize_debaters, _normalize_judge, _expand_env,
)
from debate_tool.llm_client import (
    TokenLimitError, call_llm, _strip_json_fence, _split_cot_or_regenerate_reply,
)
from debate_tool.cross_exam import run_cross_exam
from debate_tool.config_ops import (
    _apply_overrides, resolve_effective_config, _describe_overrides,
    modify_topic, validate_topic_log_consistency, _validate_api_config,
)
from debate_tool.compact_engine import (
    _compact_for_retry, _compact_single_debater, _do_compact,
    _parse_form_output, _fallback_form_filling,
)

# ── 環境変数 ────────────────────────────────────────────
ENV_BASE_URL = os.environ.get("DEBATE_BASE_URL", "").strip()
ENV_API_KEY = os.environ.get("DEBATE_API_KEY", "").strip()


async def run(cfg: dict, topic_path: Path, *, cot_length: int | None = None, log_path: Path | None = None):
    stem = topic_path.stem
    out_dir = topic_path.parent

    if log_path is None:
        log_path = build_log_path(topic_path)
    from debate_tool import core as _core
    initial_config = _core._build_initial_config(cfg)
    log = Log(log_path, cfg["title"], topic=cfg.get("topic_body", ""), initial_config=initial_config)
    topic = cfg["topic_body"]
    debaters = cfg["debaters"]
    judge = cfg["judge"]
    rounds = cfg["rounds"]
    timeout = cfg["timeout"]
    max_reply_tokens = cfg["max_reply_tokens"]
    constraints = cfg["constraints"]
    cross_exam = cfg.get("cross_exam", 0)
    early_stop = cfg.get("early_stop", 0.0)
    if cot_length is None:
        cot_length = cfg.get("cot_length", None)
    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()

    if cross_exam < 0:
        cross_exam_rounds = set(range(1, rounds))
    else:
        cross_exam_rounds = set(range(1, min(cross_exam, rounds) + 1))

    print("=" * 60)
    print(f"  {cfg['title']}")
    flags = []
    if cross_exam_rounds:
        if cross_exam < 0:
            flags.append("质询(全轮)")
        elif cross_exam == 1:
            flags.append("质询(R1)")
        else:
            flags.append(f"质询(R1~R{max(cross_exam_rounds)})")
    if early_stop:
        flags.append(f"早停(≥{early_stop:.0%})")
    if cot_length is not None:
        if cot_length > 0:
            flags.append(f"CoT(≤{cot_length}t)")
        else:
            flags.append("CoT")
    if flags:
        print(f"  [{', '.join(flags)}]")
    print(f"  {rounds} 轮 | 辩手: {', '.join(d['name'] for d in debaters)}")
    print(f"  裁判: {judge['name']}")
    if debate_base_url:
        print(f"  API: {debate_base_url}")
    print("=" * 60)

    last_seq = 0
    challenged_last: set[str] | None = None
    for rnd in range(1, rounds + 1):
        print(f"\n\n📢 第 {rnd}/{rounds} 轮\n")
        new_log = log.since(last_seq)

        if rnd == 1:
            user_ctx = f"## 辩论议题\n\n{topic}"
            base_task_desc = cfg["round1_task"]
        elif rnd == rounds:
            user_ctx = f"## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{new_log}"
            base_task_desc = cfg["final_task"]
        else:
            user_ctx = f"## 辩论议题\n\n{topic}\n\n## 上轮辩论内容\n\n{new_log}"
            base_task_desc = cfg["middle_task"]

        constraints_block = ""
        if constraints:
            constraints_block = f"\n\n核心约束：\n{constraints}"

        mark = log.entries[-1]["seq"] if log.entries else 0
        current_user_ctx = user_ctx
        replies = []
        system_text = f"## 辩论议题\n\n{topic}"

        for _ in range(10):

            async def speak(
                d,
                rnd=rnd,
                base_task_desc=base_task_desc,
                _ctx=current_user_ctx,
                constraints_block=constraints_block,
                _challenged_last=challenged_last,
                _middle_task_desc=cfg.get("middle_task", ""),
                _middle_task_optional=cfg.get("middle_task_optional", False),
            ):
                debater_base_url = (d.get("base_url", "") or debate_base_url).strip()
                debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
                if _challenged_last is not None:
                    if d["name"] in _challenged_last:
                        if rnd == rounds:
                            task_desc = (
                                "【优先任务】逐条回应你收到的每一个质询，指出对方质疑中的不当之处，"
                                "并可修正自己的方案。每条质疑都必须回应，字数紧张时可简短作答。"
                                "若回应已占用大量篇幅，可省略下方的最终任务。"
                                "\n\n【最终任务（可选）】" + base_task_desc
                            )
                        else:
                            base_response = (
                                "【优先任务】逐条回应你收到的每一个质询，指出对方质疑中的不当之处，"
                                "并可修正自己的方案。每条质疑都必须回应，字数紧张时可简短作答。"
                                "若回应已占用大量篇幅，可省略下方的推进任务。"
                                "\n\n【推进任务（可选）】"
                            )
                            if _middle_task_optional or not _middle_task_desc:
                                task_desc = "逐条回应你收到的每一个质询，指出对方质疑中的不当之处，并可修正自己的方案。每条质疑都必须回应，字数紧张时可简短作答。400-600 字"
                            else:
                                task_desc = base_response + _middle_task_desc
                    else:
                        if rnd == rounds:
                            task_desc = base_task_desc
                        else:
                            task_desc = (
                                "本轮无人向你提出质询。如有新论点或补充可继续阐发；"
                                "若你认为本轮无新内容可补充，可简短表示等待本轮，无需强行发言。200-400 字"
                            )
                else:
                    task_desc = base_task_desc
                sys_prompt = (
                    f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮。\n\n"
                    f"任务：{task_desc}{constraints_block}"
                )
                last_state = log.get_last_compact_state()
                if last_state and last_state.get("participants"):
                    participant = next(
                        (p for p in last_state["participants"] if p["name"] == d["name"]),
                        None,
                    )
                    if participant:
                        stance_injection = render_stance_for_system(participant)
                        sys_prompt = (
                            sys_prompt + "\n\n" + stance_injection
                            + "\n\n你收到的是辩论状态快照。「已否决路径」不得以任何变体重新提出。"
                            "你的立场描述已更新为上述「当前辩论立场」，以此为准，忽略初始立场中关于观点的陈述。"
                        )
                base_sys_prompt = sys_prompt
                if cot_length is not None:
                    cot_note = "请先在 <thinking>...</thinking> 标签内完成你的思考过程。"
                    if cot_length > 0:
                        cot_note += f" 思考内容不超过 {cot_length} token。"
                    sys_prompt = sys_prompt + "\n\n" + cot_note
                    call_max_tokens = (
                        (cot_length + max_reply_tokens) if cot_length > 0
                        else (max_reply_tokens + 2000)
                    )
                else:
                    call_max_tokens = max_reply_tokens
                last_cp_entry = next(
                    (e for e in reversed(log.entries) if e.get("tag") == "compact_checkpoint"),
                    None,
                )
                if last_cp_entry:
                    cp_state = last_cp_entry.get("state") or parse_compact_checkpoint(last_cp_entry["content"]).get("state")
                    cp_public_view = render_public_markdown(cp_state) if cp_state else last_cp_entry.get("content", "")
                    delta_text = log.since(last_cp_entry["seq"])
                    if delta_text != "(无新内容)":
                        effective_ctx = cp_public_view + "\n\n## 快照后新增内容\n\n" + delta_text
                    else:
                        effective_ctx = cp_public_view
                else:
                    effective_ctx = _ctx
                raw = await call_llm(
                    d["model"], sys_prompt, effective_ctx,
                    max_reply_tokens=call_max_tokens, timeout=timeout,
                    base_url=debater_base_url, api_key=debater_api_key,
                )
                if cot_length is not None:
                    thinking, reply = await _split_cot_or_regenerate_reply(
                        raw,
                        model=d["model"], base_sys_prompt=base_sys_prompt,
                        user_ctx=effective_ctx, max_reply_tokens=max_reply_tokens,
                        timeout=timeout, base_url=debater_base_url, api_key=debater_api_key,
                    )
                else:
                    thinking, reply = "", raw
                return thinking, reply
            try:
                raw_results = await asyncio.gather(*[speak(d) for d in debaters])
                break
            except TokenLimitError as e:
                print(
                    f"\n  📦 Token 超限 (model_max={e.model_max_tokens})，compact 后重试...",
                    file=sys.stderr,
                )
                try:
                    _new_state, _checkpoint_seq = await _do_compact(log, cfg, system_text)
                    current_user_ctx = render_public_markdown(_new_state)
                except ValueError as compact_err:
                    print(
                        f"\n  ❌ compact 配置缺失，无法自动压缩: {compact_err}",
                        file=sys.stderr,
                    )
                    print(
                        "  请在 topic YAML 中配置 compact_model / compact_check_model 后重试。",
                        file=sys.stderr,
                    )
                    raise
        else:
            raise RuntimeError(f"第 {rnd} 轮经过多次 compact 仍无法完成，请手动压缩日志")

        for d, (thinking, reply) in zip(debaters, raw_results):
            if thinking:
                log.add(d["name"], thinking, "thinking", flush=False)
            log.add(d["name"], reply, flush=False)
            replies.append(reply)
        log._flush()
        last_seq = mark

        if early_stop and rnd < rounds:
            converged, avg_sim = check_convergence(replies, early_stop)
            print(f"\n  📊 收敛检查: 平均相似度 {avg_sim:.1%} (阈值 {early_stop:.0%})")
            if converged:
                print("  ⚡ 观点已收敛，跳过剩余轮次，直接进入裁判阶段")
                break

        compact_threshold = cfg.get("compact_threshold", DEFAULT_COMPACT_THRESHOLD)
        if estimate_tokens(current_user_ctx) > compact_threshold:
            print(
                f"\n  📦 上下文超过 {compact_threshold} tokens，主动触发 compact...",
                file=sys.stderr,
            )
            try:
                _new_state, _checkpoint_seq = await _do_compact(log, cfg, system_text)
                current_user_ctx = render_public_markdown(_new_state)
            except ValueError as e:
                print(
                    f"\n  ⚠️ compact 配置缺失（{e}），跳过主动 compact",
                    file=sys.stderr,
                )

        if rnd in cross_exam_rounds and rnd < rounds:
            print(f"\n\n🔍 质询环节 (R{rnd}.5)\n")
            challenged_set = await run_cross_exam(
                debaters, log, topic, rnd,
                max_reply_tokens=max_reply_tokens, timeout=timeout,
                debate_base_url=debate_base_url, debate_api_key=debate_api_key,
            )
            challenged_last = challenged_set
        else:
            challenged_last = None
    print("\n\n⚖️ 裁判总结\n")
    judge_instructions = cfg["judge_instructions"]
    if not judge_instructions:
        judge_instructions = (
            "输出结构化 Summary：\n\n"
            "## 一、各辩手表现评价（每位 2-3 句）\n\n"
            "## 二、逐一裁定\n"
            "对每个议题给出：\n"
            "- **裁定**：最终方案\n"
            "- **理由**：引用辩论中的关键论据\n"
            "- **优先级**：P0 / P1 / P2\n\n"
            "## 三、完整修改清单"
        )
    human_entries = [e for e in log.entries if e.get("tag") == "human"]
    if human_entries:
        human_block = "\n".join(f"- {e['content']}" for e in human_entries)
        judge_instructions += (
            f"\n\n## 四、观察者意见回应\n"
            f"本次辩论中有观察者注入了以下意见：\n{human_block}\n"
            f"请逐条说明各辩手对这些意见的吸收和回应情况。"
        )
    judge_sys = (
        f"你是辩论裁判（{judge['name']}），负责做出最终裁定。\n\n"
        f"{judge_instructions}\n\n"
        f"裁定规则：\n"
        f"- 基于事实和数据\n"
        f"- 引用辩论中的关键论据\n"
        f"- 简洁、可操作"
    )
    judge_max_tokens = judge.get("max_tokens", 8000)
    judge_base_url = (judge.get("base_url", "") or debate_base_url).strip()
    judge_api_key = (judge.get("api_key", "") or debate_api_key).strip()
    summary = await call_llm(
        judge["model"], judge_sys,
        f"全部辩论（压缩版）：\n\n{log.compact()}",
        temperature=0.3, max_reply_tokens=judge_max_tokens,
        timeout=timeout, base_url=judge_base_url, api_key=judge_api_key,
    )
    log.add(judge["name"], summary, "summary")

    sp = out_dir / f"{stem}{SUMMARY_FILE_SUFFIX}"
    sp.write_text(
        f"# {cfg['title']} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}",
        encoding="utf-8",
    )
    print(f"\n✅ 完成！ 日志: {log.path} | 总结: {sp}")


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
) -> None:
    if not log_path.exists():
        print(f"❌ 日志文件不存在: {log_path}", file=sys.stderr)
        print("请先运行 debate-tool run 进行首次辩论", file=sys.stderr)
        sys.exit(1)

    log = Log.load_from_file(log_path)
    print(f"📂 已加载 {len(log.entries)} 条日志记录")
    eff_cfg = resolve_effective_config(log)

    if resume_topic_path:
        rt_overrides, rt_message = parse_resume_topic(resume_topic_path)
        if "rounds" in rt_overrides:
            extra_rounds = rt_overrides.pop("rounds")
        rt_overrides.pop("guide", None)  # guide 仅支持 CLI --guide，resume topic 中忽略
        if rt_overrides:
            cfg_overrides = {**(cfg_overrides or {}), **rt_overrides}
        if rt_message and not message:
            message = rt_message

    if cfg_overrides:
        has_debater_changes = "add_debaters" in cfg_overrides or "drop_debaters" in cfg_overrides
        if has_debater_changes and not force:
            print(
                "❌ add_debaters / drop_debaters 需要 --force 确认（辩手变更是不可逆操作）",
                file=sys.stderr,
            )
            sys.exit(1)
        # 检查 drop_debaters 中不存在的辩手名，发出警告但继续
        if "drop_debaters" in cfg_overrides:
            existing_names = {d["name"] for d in eff_cfg["debaters"]}
            for name in cfg_overrides["drop_debaters"]:
                if name not in existing_names:
                    print(f"⚠️ drop_debaters: 辩手「{name}」不存在，跳过", file=sys.stderr)
        # 先 apply 到 eff_cfg，检查辩手数量后再写 log（避免失败时污染日志）
        _apply_overrides(eff_cfg, cfg_overrides)

    if cross_exam is not None:
        eff_cfg["cross_exam"] = cross_exam
    if cot_length is not None:
        eff_cfg["cot"] = cot_length

    validate_topic_log_consistency(log, force=force)

    # 最少辩手数量检查（写 log 之前，避免失败时污染日志）
    if len(eff_cfg["debaters"]) < 2:
        names = [d["name"] for d in eff_cfg["debaters"]]
        print(
            f"❌ 辩论至少需要 2 名辩手，当前只有 {len(names)} 名：{names}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 辩手数量验证通过，正式写入 config_override 到日志
    if cfg_overrides:
        desc = _describe_overrides(cfg_overrides)
        log.add("@系统", desc, "config_override", extra={"overrides": cfg_overrides})

    debate_api_key = ENV_API_KEY
    for d in eff_cfg["debaters"]:
        if not d.get("api_key"):
            d["api_key"] = debate_api_key

    topic = log.topic
    debaters = eff_cfg["debaters"]
    judge = eff_cfg["judge"]
    timeout = eff_cfg.get("timeout", 300)
    max_reply_tokens = eff_cfg.get("max_reply_tokens", 6000)
    constraints = eff_cfg.get("constraints", "")
    debate_base_url = ENV_BASE_URL
    num_debaters = len(debaters)
    system_text = f"## 辩论议题\n\n{topic}"
    cot_length = eff_cfg.get("cot", None)

    out_dir = log_path.parent
    stem = log_path.stem
    if stem.endswith("_debate_log"):
        stem = stem[: -len("_debate_log")]

    if message:
        log.add("👤 观察者", message, "human")
        print(f"\n💬 已注入观察者消息")

    base_round = len([e for e in log.entries if not e.get("tag")]) // max(num_debaters, 1)
    for r_offset in range(1, extra_rounds + 1):
        rnd = base_round + r_offset
        print(f"\n\n📢 续跑第 {rnd} 轮\n")
        new_log = log.since(0)

        if guide_prompt:
            task_desc = f"回应其他辩手观点，深化立场。400-600 字\n\n观察者指引：{guide_prompt}"
        elif message and r_offset == 1:
            task_desc = "请回应观察者提出的问题/意见，同时深化自己的立场。400-600 字"
        elif r_offset == extra_rounds and eff_cfg.get("final_task"):
            task_desc = eff_cfg["final_task"]
        else:
            task_desc = eff_cfg.get("middle_task", "回应其他辩手观点，深化立场。400-600 字")

        constraints_block = f"\n\n核心约束：\n{constraints}" if constraints else ""

        async def speak(d, rnd=rnd, task_desc=task_desc, constraints_block=constraints_block, _new_log=None):
            debater_base_url = (d.get("base_url", "") or debate_base_url).strip()
            debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
            sys_prompt = (
                f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮（续跑）。\n\n"
                f"任务：{task_desc}{constraints_block}"
            )
            base_sys_prompt = sys_prompt
            if cot_length is not None:
                cot_note = "请先在 <thinking>...</thinking> 标签内完成你的思考过程。"
                if cot_length > 0:
                    cot_note += f" 思考内容不超过 {cot_length} token。"
                sys_prompt = sys_prompt + "\n\n" + cot_note
                call_max_tokens = (
                    (cot_length + max_reply_tokens) if cot_length > 0
                    else (max_reply_tokens + 2000)
                )
            else:
                call_max_tokens = max_reply_tokens
            ctx = f"{system_text}\n\n## 辩论历史\n\n{_new_log or new_log}"
            raw = await call_llm(
                d["model"], sys_prompt, ctx,
                max_reply_tokens=call_max_tokens, timeout=timeout,
                base_url=debater_base_url, api_key=debater_api_key,
            )
            if cot_length is not None:
                thinking, reply = await _split_cot_or_regenerate_reply(
                    raw,
                    model=d["model"], base_sys_prompt=base_sys_prompt,
                    user_ctx=ctx, max_reply_tokens=max_reply_tokens,
                    timeout=timeout, base_url=debater_base_url, api_key=debater_api_key,
                )
            else:
                thinking, reply = "", raw
            return thinking, reply
        for compact_attempt in range(10):
            try:
                raw_results = await asyncio.gather(*[speak(d) for d in debaters])
                break
            except TokenLimitError as e:
                print(
                    f"\n  📦 Token 超限 (model_max={e.model_max_tokens})，触发 compact 后重试...",
                    file=sys.stderr,
                )
                compact_text = _compact_for_retry(log.entries, e.model_max_tokens, num_debaters, system_text)
                log.add("Compact Checkpoint", compact_text, "compact_checkpoint")
                new_log = compact_text

                async def speak_retry(d, rnd=rnd, task_desc=task_desc, constraints_block=constraints_block, _nl=compact_text):
                    debater_base_url = (d.get("base_url", "") or debate_base_url).strip()
                    debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
                    sys_prompt = (
                        f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮（续跑）。\n\n"
                        f"任务：{task_desc}{constraints_block}"
                    )
                    if cot_length is not None:
                        cot_note = "请先在 <thinking>...</thinking> 标签内完成你的思考过程。"
                        if cot_length > 0:
                            cot_note += f" 思考内容不超过 {cot_length} token。"
                        base_sys_prompt = sys_prompt
                        sys_prompt = sys_prompt + "\n\n" + cot_note
                        call_max_tokens = (
                            (cot_length + max_reply_tokens) if cot_length > 0
                            else (max_reply_tokens + 2000)
                        )
                    else:
                        call_max_tokens = max_reply_tokens
                    ctx = f"{system_text}\n\n## 辩论历史\n\n{_nl}"
                    raw = await call_llm(
                        d["model"], sys_prompt, ctx,
                        max_reply_tokens=call_max_tokens, timeout=timeout,
                        base_url=debater_base_url, api_key=debater_api_key,
                    )
                    if cot_length is not None:
                        thinking, reply = await _split_cot_or_regenerate_reply(
                            raw,
                            model=d["model"], base_sys_prompt=base_sys_prompt,
                            user_ctx=ctx, max_reply_tokens=max_reply_tokens,
                            timeout=timeout, base_url=debater_base_url, api_key=debater_api_key,
                        )
                    else:
                        thinking, reply = "", raw
                    return thinking, reply

                try:
                    raw_results = await asyncio.gather(*[speak_retry(d) for d in debaters])
                    break
                except TokenLimitError as e2:
                    print(f"  ⚠️ compact 后仍超限 (attempt {compact_attempt + 1})，继续缩...", file=sys.stderr)
                    compact_text = _compact_for_retry(log.entries, e2.model_max_tokens, num_debaters, system_text)
                    log.add("Compact Checkpoint", compact_text, "compact_checkpoint")
                    new_log = compact_text
        else:
            raise RuntimeError(f"第 {rnd} 轮经过多次 compact 仍无法完成，请手动压缩日志")
        for d, (thinking, reply) in zip(debaters, raw_results):
            if thinking:
                log.add(d["name"], thinking, "thinking", flush=False)
            log.add(d["name"], reply, flush=False)
        log._flush()

        do_cross_exam = (
            cross_exam is not None
            and cross_exam != 0
            and (cross_exam < 0 or r_offset <= cross_exam)
            and r_offset < extra_rounds
        )
        if do_cross_exam:
            print(f"\n\n🔍 质询环节 (续跑 R{rnd}.5)\n")
            await run_cross_exam(
                debaters, log, topic, rnd,
                max_reply_tokens=max_reply_tokens, timeout=timeout,
                debate_base_url=debate_base_url, debate_api_key=debate_api_key,
            )

    print("\n\n⚖️ 裁判总结\n")
    judge_instructions = eff_cfg.get("judge_instructions", "")
    if not judge_instructions:
        judge_instructions = (
            "输出结构化 Summary：\n\n"
            "## 一、各辩手表现评价（每位 2-3 句）\n\n"
            "## 二、逐一裁定\n"
            "对每个议题给出：\n"
            "- **裁定**：最终方案\n"
            "- **理由**：引用辩论中的关键论据\n"
            "- **优先级**：P0 / P1 / P2\n\n"
            "## 三、完整修改清单"
        )
    human_entries = [e for e in log.entries if e.get("tag") == "human"]
    if human_entries:
        human_block = "\n".join(f"- {e['content']}" for e in human_entries)
        judge_instructions += (
            f"\n\n## 四、观察者意见回应\n"
            f"本次辩论中有观察者注入了以下意见：\n{human_block}\n"
            f"请逐条说明各辩手对这些意见的吸收和回应情况。"
        )
    judge_sys = (
        f"你是辩论裁判（{judge['name']}），负责做出最终裁定。\n\n"
        f"{judge_instructions}\n\n"
        f"裁定规则：\n- 基于事实和数据\n- 引用辩论中的关键论据\n- 简洁、可操作"
    )
    judge_max_tokens = judge.get("max_tokens", 8000)
    judge_base_url = (judge.get("base_url", "") or debate_base_url).strip()
    judge_api_key = (judge.get("api_key", "") or debate_api_key).strip()
    judge_ctx = log.since(0)

    for _ in range(5):
        try:
            summary = await call_llm(
                judge["model"], judge_sys,
                f"全部辩论（含续跑）：\n\n{judge_ctx}",
                temperature=0.3, max_reply_tokens=judge_max_tokens,
                timeout=timeout, base_url=judge_base_url, api_key=judge_api_key,
            )
            break
        except TokenLimitError as e:
            print(f"\n  📦 裁判 token 超限 (max={e.model_max_tokens})，compact 后重试...", file=sys.stderr)
            judge_ctx = _compact_for_retry(log.entries, e.model_max_tokens, num_debaters, "")
    else:
        summary = "[裁判总结失败：多次 compact 后仍超限]"
    log.add(judge["name"], summary, "summary")

    sp = out_dir / f"{stem}{SUMMARY_FILE_SUFFIX}"
    sp.write_text(
        f"# {log.title} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}",
        encoding="utf-8",
    )
    print(f"\n✅ 续跑完成！ 日志: {log.path}")


def compact_log(
    log_path: Path,
    *,
    keep_last: int = 0,
    token_budget: int = 60000,
    topic_path: "Path | None" = None,
) -> None:
    if not log_path.exists():
        print(f"❌ 日志文件不存在: {log_path}", file=sys.stderr)
        sys.exit(1)

    resolved_topic_path: "Path | None" = topic_path
    if resolved_topic_path is None:
        stem = log_path.stem
        if stem.endswith("_debate_log"):
            candidate_stem = stem[: -len("_debate_log")]
        else:
            candidate_stem = stem
        candidate = log_path.parent / f"{candidate_stem}.md"
        if candidate.exists():
            resolved_topic_path = candidate
            print(f"  自动发现 topic 文件: {resolved_topic_path}")

    log = Log.load_from_file(log_path)

    if resolved_topic_path is None and log.initial_config:
        ic = log.initial_config
        debaters_base_url = ((ic.get("debaters") or [{}])[0].get("base_url", "") or "")
        cfg = {
            **ic,
            "base_url": ic.get("judge", {}).get("base_url", "") or debaters_base_url,
            "api_key": "",
            "topic_body": log.topic,
        }
        print("  使用 v2 log 内嵌配置（无需外部 topic 文件）")
    elif resolved_topic_path is None:
        print("❌ 未找到对应的 topic 文件，请通过 --topic 参数指定。", file=sys.stderr)
        sys.exit(1)
    else:
        cfg = parse_topic_file(resolved_topic_path)

    system_text = f"## 辩论议题\n\n{cfg['topic_body']}"
    total = len(log.entries)
    print(f"📂 已加载 {total} 条日志记录")
    before_tokens = estimate_tokens("\n\n".join(e["content"] for e in log.entries))

    try:
        _compact_state, checkpoint_seq = asyncio.run(_do_compact(log, cfg, system_text))
    except ValueError as compact_err:
        print(f"\n  ❌ compact 配置缺失，无法压缩: {compact_err}", file=sys.stderr)
        print("  请在 topic YAML 中配置 compact_model / compact_check_model 后重试。", file=sys.stderr)
        sys.exit(1)

    after_tokens = (
        estimate_tokens(_compact_state)
        if isinstance(_compact_state, str)
        else estimate_tokens(render_public_markdown(_compact_state))
    )
    print(f"\n📦 压缩完成:")
    print(f"   Token: {before_tokens} → {after_tokens} (checkpoint)")
    print(f"   Checkpoint seq: {checkpoint_seq}")
    print(f"   日志: {log.path}")


def main(argv=None):
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
            "  debate-tool run my_topic.md --cross-exam --early-stop\n"
            "\n"
            "质询:\n"
            "  --cross-exam [N]  每轮后增加质询子回合 (默认 N=1, 仅 R1 后)\n"
            "                    N=2 → R1, R2 后均质询; N=-1 → 每轮都质询\n"
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
    ap.add_argument("--cross-exam", nargs="?", type=int, const=1, default=None, metavar="N", help="质询轮数 (默认 1; -1=每轮都质询)")
    ap.add_argument("--early-stop", nargs="?", type=float, const=DEFAULT_EARLY_STOP_THRESHOLD, default=None, metavar="T", help="启用收敛早停 (默认阈值 0.55; 可指定 0~1 之间的值)")
    ap.add_argument("--cot", "--think", dest="cot_length", nargs="?", type=int, const=0, default=None, metavar="LENGTH", help="为辩手启用思考空间 (CoT)。LENGTH 为可选思考 token 预算，省略则不限制。")
    ap.add_argument("--output", type=Path, default=None, metavar="LOG_FILE", help="指定输出日志文件路径（默认: {stem}_{timestamp}_debate_log.json）")
    ap.add_argument("--debug", nargs="?", const=True, default=None, metavar="DEBUG_LOG", help="开启 debug 日志：省略文件名则输出到控制台，指定文件名则写入文件（10MB 轮转）")

    args = ap.parse_args(argv)
    topic_path = args.topic.resolve()
    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    cfg = parse_topic_file(topic_path)
    if args.cross_exam is not None:
        cfg["cross_exam"] = args.cross_exam
    if args.early_stop is not None:
        cfg["early_stop"] = args.early_stop
    if args.rounds is not None:
        cfg["rounds"] = args.rounds
    cli_cot = args.cot_length
    cfg.setdefault("cross_exam", 0)
    cfg.setdefault("early_stop", 0.0)

    effective_url = (cfg["base_url"] or ENV_BASE_URL).strip()
    effective_key = (cfg["api_key"] or ENV_API_KEY).strip()
    api_issues = _validate_api_config(cfg)
    if args.dry_run:
        stem = topic_path.stem
        out_dir = topic_path.parent
        print("=" * 60)
        print(f"  🔍 Dry Run — {cfg['title']}")
        print("=" * 60)
        print(f"\n  文件:     {topic_path}")
        print(f"  轮数:     {cfg['rounds']}")
        cx = cfg.get("cross_exam", 0)
        if cx < 0:
            print(f"  质询:     每轮")
        elif cx == 1:
            print(f"  质询:     R1 后")
        elif cx > 1:
            print(f"  质询:     R1~R{cx} 后")
        else:
            print(f"  质询:     否")
        print(f"  早停:     {'是 (阈值 {:.0%})'.format(cfg.get('early_stop', 0.0)) if cfg.get('early_stop') else '否'}")
        effective_cot = cli_cot if cli_cot is not None else cfg.get("cot_length", None)
        if effective_cot is not None:
            if effective_cot > 0:
                print(f"  CoT:      是 (思考预算 {effective_cot} token)")
            else:
                print(f"  CoT:      是 (无预算限制)")
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
        if cfg["base_url"]:
            print("  (来源: front-matter)")
        elif os.environ.get("DEBATE_BASE_URL"):
            print("  (来源: 环境变量)")
        else:
            print("  (来源: 未设置)")
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
        return

    if api_issues:
        print(
            "❌ 缺少 API 配置:\n  - "
            + "\n  - ".join(api_issues)
            + "\n请设置 DEBATE_BASE_URL / DEBATE_API_KEY，或在 topic front-matter 提供全局/辩手/裁判级 base_url / api_key",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.debug is not None:
        init_debug_logging(args.debug)
        if args.debug is not True:
            print(f"  🐛 Debug 日志 → {args.debug}", file=sys.stderr)

    if args.output is not None:
        out_log_path = args.output.resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_log_path = topic_path.parent / f"{topic_path.stem}_{ts}{LOG_FILE_SUFFIX}"
    asyncio.run(run(cfg, topic_path, cot_length=cli_cot, log_path=out_log_path))


if __name__ == "__main__":
    main()
