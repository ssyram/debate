"""核心辩论循环 — run/resume 共用"""

import asyncio
import os
import sys

from debate_tool.compact_engine import _compact_for_retry, _do_compact
from debate_tool.compact_state import render_public_markdown, render_stance_for_system
from debate_tool.core import (
    DEFAULT_COMPACT_THRESHOLD,
    DEFAULT_EARLY_STOP_THRESHOLD,
    check_convergence,
    estimate_tokens,
    parse_compact_checkpoint,
)
from debate_tool.cot import call_with_cot
from debate_tool.cross_exam import run_cross_exam
from debate_tool.debug_log import dlog
from debate_tool.llm_client import TokenLimitError, call_llm
from debate_tool.log_util import save_replies

# ── Constants ────────────────────────────────────────────────────────────────

ENV_BASE_URL = os.environ.get("DEBATE_BASE_URL", "").strip()
ENV_API_KEY = os.environ.get("DEBATE_API_KEY", "").strip()

DEFAULT_JUDGE_INSTRUCTIONS = (
    "输出结构化 Summary：\n\n"
    "## 一、各辩手表现评价（每位 2-3 句）\n\n"
    "## 二、逐一裁定\n"
    "对每个议题给出：\n"
    "- **裁定**：最终方案\n"
    "- **理由**：引用辩论中的关键论据\n"
    "- **优先级**：P0 / P1 / P2\n\n"
    "## 三、完整修改清单"
)


class EarlyStop(Exception):
    pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def resolve_api(cfg, default_pair=None):
    if default_pair is None:
        default_pair = (ENV_BASE_URL, ENV_API_KEY)
    url = (cfg.get("base_url", "") or default_pair[0]).strip()
    key = (cfg.get("api_key", "") or default_pair[1]).strip()
    return url, key


def judge_api(judge, cfg):
    base = resolve_api(cfg)
    return resolve_api(judge, base)


def compute_xexam_rounds(cross_exam, rounds, base_rnd=0):
    """计算需要做 cross exam 的轮次集合（绝对轮次编号）"""
    if cross_exam is None or cross_exam == 0:
        return set()
    if cross_exam < 0:
        return set(range(base_rnd + 1, base_rnd + rounds))
    return set(range(base_rnd + 1, min(base_rnd + cross_exam, base_rnd + rounds - 1) + 1))


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


# ── Prompt: task selection ───────────────────────────────────────────────────

def task_for_round(cfg, rnd):
    if rnd == 1:
        return cfg["round1_task"]
    if rnd == cfg["rounds"]:
        return cfg["final_task"]
    return cfg["middle_task"]


def apply_challenge(base_task, debater_name, challenged, rnd, cfg):
    """被质询时修改 task。challenged=None 表示本轮无质询环节。"""
    if challenged is None:
        return base_task
    if debater_name in challenged:
        return _challenged_task(base_task, rnd, cfg)
    if rnd == cfg["rounds"]:
        return base_task
    return (
        "本轮无人向你提出质询。如有新论点或补充可继续阐发；"
        "若你认为本轮无新内容可补充，可简短表示等待本轮，无需强行发言。200-400 字"
    )


def _challenged_task(base_task, rnd, cfg):
    """被质询辩手的任务描述（优先回应质询 + 可选推进/最终任务）"""
    priority = (
        "【优先任务】逐条回应你收到的每一个质询，指出对方质疑中的不当之处，"
        "并可修正自己的方案。每条质疑都必须回应，字数紧张时可简短作答。"
    )
    mid = cfg.get("middle_task", "")
    if rnd == cfg["rounds"]:
        return (
            priority
            + "若回应已占用大量篇幅，可省略下方的最终任务。"
            "\n\n【最终任务（可选）】" + base_task
        )
    if cfg.get("middle_task_optional", False) or not mid:
        return (
            "逐条回应你收到的每一个质询，指出对方质疑中的不当之处，并可修正自己的方案。"
            "每条质疑都必须回应，字数紧张时可简短作答。400-600 字"
        )
    return (
        priority
        + "若回应已占用大量篇幅，可省略下方的推进任务。"
        "\n\n【推进任务（可选）】" + mid
    )


# ── Prompt: system prompt builders ──────────────────────────────────────────

def build_debater_sys(d, rnd, task, constraints):
    """纯 prompt 构造：辩手系统提示（不含 compact stance）"""
    base = f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮。\n\n任务：{task}"
    if constraints:
        base += f"\n\n核心约束：\n{constraints}"
    return base


def inject_stance(sys_prompt, log, debater):
    """如果有 compact checkpoint，把辩手立场注入系统提示"""
    state = log.get_last_compact_state()
    if not (state and state.get("participants")):
        return sys_prompt
    p = next(
        (p for p in state["participants"] if p["name"] == debater["name"]),
        None,
    )
    if not p:
        return sys_prompt
    stance = render_stance_for_system(p)
    return (
        sys_prompt + "\n\n" + stance
        + "\n\n你收到的是辩论状态快照。「已否决路径」不得以任何变体重新提出。"
        "你的立场描述已更新为上述「当前辩论立场」，以此为准，忽略初始立场中关于观点的陈述。"
    )


def build_judge_sys(judge_name, instructions, human_entries):
    """纯 prompt 构造：裁判系统提示"""
    instr = instructions or DEFAULT_JUDGE_INSTRUCTIONS
    parts = [
        f"你是辩论裁判（{judge_name}），负责做出最终裁定。\n\n",
        instr,
        "\n\n裁定规则：\n- 基于事实和数据\n- 引用辩论中的关键论据\n- 简洁、可操作",
    ]
    if human_entries:
        human_block = "\n".join(f"- {e['content']}" for e in human_entries)
        parts.append(
            "\n\n## 四、观察者意见回应\n"
            f"本次辩论中有观察者注入了以下意见：\n{human_block}\n"
            "请逐条说明各辩手对这些意见的吸收和回应情况。"
        )
    return "".join(parts)


# ── Prompt: context builders ─────────────────────────────────────────────────

def effective_context(log, topic, rnd):
    """辩手 user context：R1 仅议题，后续轮次含历史（compact 优先）"""
    if rnd == 1:
        return f"## 辩论议题\n\n{topic}"
    cp = next(
        (e for e in reversed(log.entries) if e.get("tag") == "compact_checkpoint"),
        None,
    )
    if not cp:
        return f"## 辩论议题\n\n{topic}\n\n## 辩论历史\n\n{log.since(0)}"
    cp_state = cp.get("state") or parse_compact_checkpoint(cp["content"]).get("state")
    snapshot = render_public_markdown(cp_state) if cp_state else cp.get("content", "")
    delta = log.since(cp["seq"])
    if delta != "(无新内容)":
        return snapshot + "\n\n## 快照后新增内容\n\n" + delta
    return snapshot


# ── Side effects ─────────────────────────────────────────────────────────────

def _find_compact_window_cutoff(log, target_tokens: int) -> "int | None":
    """找到 compact 增量窗口中累积 token 数不超过 target_tokens 的最大 seq。
    返回 None 表示第一条 entry 本身就超限（窗口无法缩减）。
    """
    prev_state = log.get_last_compact_state()
    prev_seq = prev_state.get("covered_seq_end", 0) if prev_state else 0
    delta = log.entries_since_seq(
        prev_seq,
        exclude_tags=("thinking", "summary", "compact_checkpoint", "config_override"),
    )
    if not delta:
        return None
    cumulative = 0
    cutoff_seq = None
    for e in delta:
        tok = estimate_tokens(e.get("content", ""))
        if cumulative + tok > target_tokens:
            break
        cumulative += tok
        cutoff_seq = e["seq"]
    return cutoff_seq


async def do_compact(log, cfg):
    dlog(f"[do_compact] entries={len(log.entries)}")
    system_text = f"## 辩论议题\n\n{cfg.get('topic_body', log.topic)}"
    compact_message = cfg.get("compact_message", "") or ""

    for attempt in range(8):
        cutoff_seq = None
        if attempt > 0:
            threshold = cfg.get("compact_threshold", DEFAULT_COMPACT_THRESHOLD)
            # 用新 threshold 的一半作为安全上限（prompt overhead 约 2x）
            cutoff_seq = _find_compact_window_cutoff(log, threshold // 2)
            if cutoff_seq is None:
                raise RuntimeError(
                    "compact 超限：窗口已无法再缩减（首条 entry 已超 token 上限）"
                )
        try:
            return await _do_compact(
                log, cfg, system_text,
                compact_message=compact_message,
                cutoff_seq=cutoff_seq,
            )
        except ValueError as e:
            print(
                f"\n  ❌ compact 配置缺失: {e}\n  请在 topic YAML 中配置 compact_model / compact_check_model 后重试。",
                file=sys.stderr,
            )
            raise
        except TokenLimitError as e:
            old = cfg.get("compact_threshold", DEFAULT_COMPACT_THRESHOLD)
            new_threshold = max(2000, old // 2)
            cfg["compact_threshold"] = new_threshold
            # 持久化到 log（通过 config_override entry）
            log.add(
                "@系统",
                f"compact 超限 (model_max={e.model_max_tokens})，compact_threshold {old} → {new_threshold}",
                "config_override",
                extra={"overrides": {"compact_threshold": new_threshold}},
            )
            print(
                f"\n  ⚠️ compact 超限 (model_max={e.model_max_tokens})，"
                f"threshold {old} → {new_threshold}，窗口缩减重试 (attempt {attempt + 1})...",
                file=sys.stderr,
            )

    raise RuntimeError("compact 超限：8 次窗口缩减后仍无法完成，请手动处理日志")


# ── Predicates ───────────────────────────────────────────────────────────────

def check_early_stop(cfg, rnd, reply_texts):
    dlog(f"[check_early_stop] rnd={rnd} early_stop={cfg.get('early_stop')}")
    if not cfg.get("early_stop") or rnd >= cfg["rounds"]:
        return
    converged, avg = check_convergence(reply_texts, cfg["early_stop"])
    print(f"\n  📊 收敛检查: 平均相似度 {avg:.1%} (阈值 {cfg['early_stop']:.0%})")
    if converged:
        print("  ⚡ 观点已收敛，跳过剩余轮次，直接进入裁判阶段")
        raise EarlyStop()


async def maybe_compact(cfg, log):
    threshold = cfg.get("compact_threshold", DEFAULT_COMPACT_THRESHOLD)
    dlog(f"[maybe_compact] threshold={threshold}")
    token_count = estimate_tokens(log.since(0))
    if token_count <= threshold:
        return
    print(f"\n  📦 上下文 {token_count} tokens 超过阈值 {threshold}，触发 compact...", file=sys.stderr)
    await do_compact(log, cfg)


def should_cross_exam(rnd, xrounds, total_rounds):
    return rnd in xrounds and rnd < total_rounds


async def retry_on_token_limit(make_tasks, on_fail, max_attempts=10):
    dlog(f"[retry_on_token_limit] max_attempts={max_attempts}")
    for attempt in range(max_attempts):
        try:
            return await asyncio.gather(*make_tasks())
        except TokenLimitError as e:
            await on_fail(e, attempt)
    raise RuntimeError("经过多次 compact 仍无法完成，请手动压缩日志")


# ── Core: debater round ───────────────────────────────────────────────────────

async def one_debater(d, cfg, log, rnd, challenged, cot_len, api):
    dlog(f"[one_debater] {d['name']} rnd={rnd}")
    task = apply_challenge(task_for_round(cfg, rnd), d["name"], challenged, rnd, cfg)
    sp = inject_stance(build_debater_sys(d, rnd, task, cfg["constraints"]), log, d)
    ctx = effective_context(log, cfg["topic_body"], rnd)
    du, dk = resolve_api(d, api)
    return await call_with_cot(d["model"], sp, ctx, cot_len, cfg["max_reply_tokens"], cfg["timeout"], du, dk)


async def compact_on_token_limit(log, cfg, e, attempt):
    entries = log.entries
    if entries and entries[-1].get("tag") == "compact_checkpoint":
        raise RuntimeError(
            f"Token 超限 (model_max={e.model_max_tokens})，但当前日志已处于 compact checkpoint 起始，"
            "再次压缩无效。请缩短 topic 内容或使用支持更大 context 的模型。"
        )
    print(f"\n  📦 Token 超限 (model_max={e.model_max_tokens})，compact 后重试... (attempt {attempt})", file=sys.stderr)
    await do_compact(log, cfg)


async def debater_round(cfg, log, rnd, challenged, cot_len):
    dlog(f"[debater_round] rnd={rnd} debaters={[d['name'] for d in cfg['debaters']]}")
    api = resolve_api(cfg)
    make = lambda: [one_debater(d, cfg, log, rnd, challenged, cot_len, api) for d in cfg["debaters"]]
    return await retry_on_token_limit(make, lambda e, a: compact_on_token_limit(log, cfg, e, a))


# ── Core: cross exam ──────────────────────────────────────────────────────────

async def maybe_cross_exam(cfg, log, rnd, xrounds):
    dlog(f"[maybe_cross_exam] rnd={rnd} should={should_cross_exam(rnd, xrounds, cfg['rounds'])}")
    if not should_cross_exam(rnd, xrounds, cfg["rounds"]):
        return None
    print(f"\n\n🔍 质询环节 (R{rnd}.5)\n")
    url, key = resolve_api(cfg)
    return await run_cross_exam(
        cfg["debaters"], log, cfg["topic_body"], rnd,
        max_reply_tokens=cfg["max_reply_tokens"],
        timeout=cfg["timeout"],
        debate_base_url=url,
        debate_api_key=key,
    )


# ── Core: one round ───────────────────────────────────────────────────────────

async def one_round(cfg, log, rnd, challenged, cot_len, xrounds):
    print(f"\n\n📢 第 {rnd}/{cfg['rounds']} 轮\n")
    await maybe_compact(cfg, log)
    replies = await debater_round(cfg, log, rnd, challenged, cot_len)
    save_replies(log, cfg["debaters"], replies)
    check_early_stop(cfg, rnd, [r for _, r in replies])
    await maybe_compact(cfg, log)
    return await maybe_cross_exam(cfg, log, rnd, xrounds)


# ── Core: judge ───────────────────────────────────────────────────────────────

async def _judge_with_retry(judge, sp, log, cfg, url, key, max_attempts=5):
    dlog(f"[_judge_with_retry] max_attempts={max_attempts}")
    ctx = [log.compact()]
    for attempt in range(max_attempts):
        try:
            return await call_llm(
                judge["model"], sp,
                f"全部辩论（压缩版）：\n\n{ctx[0]}",
                temperature=0.3,
                max_reply_tokens=judge.get("max_tokens", 8000),
                timeout=cfg.get("timeout", 300),
                base_url=url,
                api_key=key,
            )
        except TokenLimitError as e:
            print(f"\n  📦 裁判 token 超限 (max={e.model_max_tokens})，compact 后重试...", file=sys.stderr)
            ctx[0] = _compact_for_retry(log.entries, e.model_max_tokens, len(cfg["debaters"]), "")
    return "[裁判总结失败：多次 compact 后仍超限]"


async def judge_phase(cfg, log):
    print("\n\n⚖️ 裁判总结\n")
    judge = cfg["judge"]
    humans = [e for e in log.entries if e.get("tag") == "human"]
    sp = build_judge_sys(judge["name"], cfg.get("judge_instructions", ""), humans)
    url, key = judge_api(judge, cfg)
    return await _judge_with_retry(judge, sp, log, cfg, url, key)


# ── Core: main loop ───────────────────────────────────────────────────────────

async def core_loop(cfg, log, base_rnd, cot_len, xrounds):
    dlog(f"[core_loop] base={base_rnd} rounds={cfg['rounds']} cot={cot_len} xrounds={xrounds}")
    challenged = None
    try:
        for rnd in range(base_rnd + 1, cfg["rounds"] + 1):
            challenged = await one_round(cfg, log, rnd, challenged, cot_len, xrounds)
    except EarlyStop:
        pass
