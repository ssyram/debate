"""Compact engine for debate-tool.

从 runner.py 提取的 compact 核心逻辑：
  - _compact_for_retry
  - _parse_form_output
  - _fallback_form_filling
  - _compact_single_debater
  - _do_compact
"""
from __future__ import annotations

import asyncio
import json
import math as _math
import sys

import httpx

from .debug_log import dlog
from .llm_client import call_llm, _strip_json_fence
from .log_io import Log
from .core import (
    build_compact_context,
    parse_compact_checkpoint,
)
from .compact_state import (
    render_public_markdown,
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

_MIN_SEGMENT_CHARS = 30_000

# ── PARTICIPANT_SCHEMA ────────────────────────────────────────────────────────
# Schema-driven field definitions for fillForm.
# Each entry is a (field_name, spec) tuple.
# spec types:
#   {"type": "computed", "fn": callable(ctx) -> value}
#   {"type": "open"}
#   {"type": "choice", "options": [...]}  OR  {"type": "choice", "fn_options": callable(ctx) -> [...]}
#   {"type": "list", "item_schema": [(name, spec), ...]}
PARTICIPANT_SCHEMA: "list[tuple[str, dict]]" = [
    ("name",           {"type": "computed", "fn": lambda ctx: ctx["debater_name"]}),
    ("active",         {"type": "computed", "fn": lambda ctx: ctx.get("prev_active", True)}),
    ("stance_version", {"type": "computed", "fn": lambda ctx: ctx.get("prev_version", 0) + 1}),
    ("stance",         {"type": "open"}),
    ("core_claims",    {"type": "list", "item_schema": [
        ("id",     {"type": "computed", "fn": lambda ctx: f"C{ctx['item_index'] + 1}"}),
        ("text",   {"type": "open"}),
        ("status", {"type": "choice", "options": ["active", "abandoned"]}),
    ]}),
    ("key_arguments",  {"type": "list", "item_schema": [
        ("id",       {"type": "computed", "fn": lambda ctx: f"A{ctx['item_index'] + 1}"}),
        ("claim_id", {"type": "choice", "fn_options": lambda ctx: [c["id"] for c in ctx.get("filled", {}).get("core_claims", [])]}),
        ("text",     {"type": "open"}),
        ("status",   {"type": "choice", "options": ["active", "abandoned"]}),
    ]}),
    ("abandoned_claims", {"type": "list", "item_schema": [
        ("id",     {"type": "computed", "fn": lambda ctx: f"AC{ctx['item_index'] + 1}"}),
        ("text",   {"type": "open"}),
        ("reason", {"type": "open"}),
    ]}),
]


def _compact_for_retry(
    entries: list[dict],
    model_max_tokens: int,
    num_debaters: int,
    system_text: str,
) -> str:
    budget = int(model_max_tokens * 0.7)
    _MAX_ITERATIONS = 20  # explicit limit: prevent infinite loops

    for _iter in range(_MAX_ITERATIONS):
        result = build_compact_context(
            entries,
            token_budget=budget,
            num_debaters=num_debaters,
            system_text=system_text,
        )
        # Use budget * 4 as the char limit (safe upper bound for mixed CJK/Latin).
        # English: ~4 chars/token; CJK: ~1.5 chars/token — 4x is conservative.
        char_limit = max(budget * 4, _MIN_SEGMENT_CHARS)
        if len(result) <= char_limit:
            return result
        # Reduce token budget so build_compact_context produces shorter output
        budget = int(budget * 0.8)
        if budget * 4 < _MIN_SEGMENT_CHARS:
            raise RuntimeError(
                f"compact 后上下文仍超限且 token budget 已压至 {budget} tokens，"
                f"无法继续压缩。请手动 compact 或缩减辩论轮次。"
            )
        print(
            f"  ⚠️ compact 后仍超限（iter={_iter+1}），budget 缩至 {budget} tokens，重新压缩...",
            file=sys.stderr,
        )

    raise RuntimeError(
        f"compact 超过最大迭代次数 {_MAX_ITERATIONS}，放弃。"
    )


def _parse_form_output(
    text: str,
    name: str,
    prev_participant: "dict | None",
) -> "dict | None":
    """解析填表模式的纯文本输出，返回 ParticipantState dict 或 None"""
    try:
        lines = text.strip().split("\n")
        stance_lines = []
        claims = []
        args = []

        section = None
        for line in lines:
            line = line.strip()
            if line.startswith("STANCE:"):
                section = "stance"
                continue
            elif line.startswith("CORE_CLAIMS:"):
                section = "claims"
                continue
            elif line.startswith("KEY_ARGUMENTS:"):
                section = "args"
                continue

            if section == "stance" and line:
                stance_lines.append(line)
            elif section == "claims" and "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    claims.append({"id": parts[0], "text": parts[1], "status": parts[2]})
            elif section == "args" and "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4:
                    args.append({
                        "id": parts[0],
                        "claim_id": parts[1],
                        "text": parts[2],
                        "status": parts[3],
                    })

        if stance_lines:
            return {
                "name": name,
                "stance_version": (prev_participant.get("stance_version", 0) + 1) if prev_participant else 1,
                "stance": "\n".join(stance_lines),
                "core_claims": claims,
                "key_arguments": args,
                "abandoned_claims": prev_participant.get("abandoned_claims", []) if prev_participant else [],
            }
    except Exception:
        pass
    return None


async def _retry_with_feedback(n: int, async_fn) -> str:
    """最多重试 n 次，每次把上次异常信息作为 feedback 传入 async_fn(feedback: str)。

    async_fn(feedback) 应返回字符串结果，或 raise 表示失败。
    最后一次失败时异常向上穿透。
    """
    feedback = ""
    last_exc: "Exception | None" = None
    for _attempt in range(n):
        try:
            return await async_fn(feedback)
        except Exception as e:
            exc_str = str(e)
            if "control character" in exc_str or "Invalid control" in exc_str:
                feedback = (
                    f"上次失败：字符串值中包含非法控制字符（如裸换行符、制表符等）。"
                    f"请确保输出纯文本，不含任何非法控制字符。"
                )
            else:
                feedback = f"上次失败：{exc_str[:150]}"
            last_exc = e
    raise last_exc  # type: ignore[misc]


def _build_filled_summary(filled: dict) -> str:
    """将已填字段摘要化为简短文字，用于 prompt 上下文。"""
    parts = []
    if filled.get("stance"):
        parts.append(f"立场：{str(filled['stance'])[:80]}")
    if filled.get("core_claims"):
        parts.append(f"核心主张：{len(filled['core_claims'])} 条")
    if filled.get("key_arguments"):
        parts.append(f"关键论点：{len(filled['key_arguments'])} 条")
    if filled.get("abandoned_claims"):
        parts.append(f"已放弃主张：{len(filled['abandoned_claims'])} 条")
    return "；".join(parts) if parts else "（尚无已填字段）"


async def _fill_fields(
    schema: "list[tuple[str, dict]]",
    base_ctx: dict,
    debater: dict,
    base_url: str,
    api_key: str,
) -> dict:
    """递归地按 schema 顺序填充字段，返回填充完成的 dict。

    base_ctx 必须包含：
      - debater_name: str
      - delta_text: str（近期辩论摘要，可为空串）
      - prev_active: bool（可选）
      - prev_version: int（可选）
      - filled: dict（已填字段，由本函数维护并传递给 computed fn）
      - item_index: int（list item 时使用）
    """
    name = base_ctx["debater_name"]
    filled: dict = base_ctx.get("filled", {})
    delta_text = base_ctx.get("delta_text", "")

    for field_name, spec in schema:
        ctx = {**base_ctx, "filled": filled}
        field_type = spec["type"]

        if field_type == "computed":
            filled[field_name] = spec["fn"](ctx)

        elif field_type == "open":
            filled_summary = _build_filled_summary(filled)
            prompt_base = (
                f"你是辩手「{name}」。\n"
                f"已填信息：{filled_summary}\n"
                f"近期辩论记录（摘要）：{delta_text[:600]}\n\n"
                f"请填写「{field_name}」字段，用简洁文字描述。不要空白回答。"
            )

            async def _ask_open(feedback: str, _pb=prompt_base) -> str:
                prompt = _pb
                if feedback:
                    prompt += f"\n（{feedback}，请重新尝试）"
                resp = await call_llm(
                    debater["model"], "",
                    prompt,
                    base_url=base_url, api_key=api_key, max_reply_tokens=800,
                )
                dlog(f"[fillForm open {field_name}] {resp!r}")
                val = resp.strip()
                if not val:
                    raise ValueError(f"「{field_name}」回答为空")
                return val

            filled[field_name] = await _retry_with_feedback(3, _ask_open)

        elif field_type == "choice":
            # 确定有效选项
            if "fn_options" in spec:
                options = spec["fn_options"](ctx)
            else:
                options = spec["options"]

            if not options:
                # 没有有效选项（如 core_claims 为空时 claim_id 无选项）→ 跳过
                filled[field_name] = ""
                continue

            options_str = "、".join(f"「{o}」" for o in options)
            filled_summary = _build_filled_summary(filled)
            prompt_base = (
                f"你是辩手「{name}」。\n"
                f"已填信息：{filled_summary}\n"
                f"请为「{field_name}」选择一个值，有效选项：{options_str}。\n"
                f"只输出选项中的一个值，不附加其他文字。"
            )

            async def _ask_choice(feedback: str, _pb=prompt_base, _opts=options) -> str:
                prompt = _pb
                if feedback:
                    prompt += f"\n（{feedback}，请只回答选项之一）"
                resp = await call_llm(
                    debater["model"], "",
                    prompt,
                    base_url=base_url, api_key=api_key, max_reply_tokens=50,
                )
                dlog(f"[fillForm choice {field_name}] {resp!r}")
                text = resp.strip()
                # 宽松匹配：只要响应中包含某个选项即认为有效
                matched = next((o for o in _opts if o in text), None)
                if matched is None:
                    raise ValueError(
                        f"「{field_name}」无法解析为有效选项（回答：{text[:60]}，选项：{_opts}）"
                    )
                return matched

            # choice 失败是 fatal：_retry_with_feedback 抛出异常，向上穿透
            filled[field_name] = await _retry_with_feedback(3, _ask_choice)

        elif field_type == "list":
            item_schema = spec["item_schema"]
            items: list = []

            # ── askBulk ──────────────────────────────────────────────
            bulk_ok = False
            try:
                filled_summary = _build_filled_summary(filled)
                bulk_prompt = (
                    f"你是辩手「{name}」。\n"
                    f"已填信息：{filled_summary}\n"
                    f"近期辩论记录（摘要）：{delta_text[:600]}\n\n"
                    f"请列出「{field_name}」的所有条目（每条以「- 」开头，一行一条）。"
                    f"如果没有任何条目，请回答「没有」。"
                )
                bulk_resp = await call_llm(
                    debater["model"], "",
                    bulk_prompt,
                    base_url=base_url, api_key=api_key, max_reply_tokens=1200,
                )
                dlog(f"[fillForm askBulk {field_name}] {bulk_resp!r}")
                bulk_text = bulk_resp.strip()

                # 判断是否"没有"
                _no_keywords = ("没有", "无", "暂无", "none", "no item", "nothing")
                if any(kw in bulk_text.lower() for kw in _no_keywords):
                    items = []
                    bulk_ok = True
                else:
                    raw_lines = [
                        line.lstrip("- ").strip()
                        for line in bulk_text.splitlines()
                        if line.strip() and line.strip() not in ("-",)
                    ]
                    if raw_lines:
                        for idx, line_text in enumerate(raw_lines):
                            item_ctx = {
                                **base_ctx,
                                "filled": dict(filled),
                                "item_index": idx,
                                # 为 item 的 open 字段提供"当前行内容"提示
                                "delta_text": f"该条目内容：{line_text}\n\n" + delta_text,
                            }
                            item_filled = await _fill_fields(
                                item_schema, item_ctx, debater, base_url, api_key
                            )
                            # 覆盖 open 字段如果已被初始化但行内容更具体
                            # （bulk 中每行 = text 字段的初始内容，优先用行内容）
                            if "text" not in item_filled or not item_filled["text"]:
                                item_filled["text"] = line_text
                            items.append(item_filled)
                        bulk_ok = True
                    # 若 raw_lines 为空但没有"没有"关键词：bulk 失败，走 askIterative
            except Exception as bulk_exc:
                dlog(f"[fillForm askBulk {field_name} failed] {bulk_exc}")
                bulk_ok = False

            # ── askIterative（bulk 失败时）────────────────────────────
            if not bulk_ok:
                items = []
                idx = 0
                # 问第一条
                first_prompt = (
                    f"你是辩手「{name}」。\n"
                    f"请告诉我「{field_name}」的第一条内容是什么？\n"
                    f"如果没有任何内容，请回答「没有」。"
                )
                first_resp = await call_llm(
                    debater["model"], "",
                    first_prompt,
                    base_url=base_url, api_key=api_key, max_reply_tokens=600,
                )
                dlog(f"[fillForm askIterative {field_name} first] {first_resp!r}")
                first_text = first_resp.strip()

                _no_kw = ("没有", "无", "暂无", "none", "no item", "nothing")
                if any(kw in first_text.lower() for kw in _no_kw):
                    # 合法空列表
                    items = []
                elif not first_text:
                    # 空响应 = fatal
                    raise ValueError(
                        f"「{field_name}」askIterative 第一条返回空，无法填充列表"
                    )
                else:
                    # 有内容，填第一条 item
                    item_ctx = {
                        **base_ctx,
                        "filled": dict(filled),
                        "item_index": idx,
                        "delta_text": f"该条目内容：{first_text}\n\n" + delta_text,
                    }
                    item_filled = await _fill_fields(
                        item_schema, item_ctx, debater, base_url, api_key
                    )
                    if "text" not in item_filled or not item_filled["text"]:
                        item_filled["text"] = first_text
                    items.append(item_filled)
                    idx += 1

                    # 继续追问
                    while True:
                        next_prompt = (
                            f"你是辩手「{name}」。\n"
                            f"「{field_name}」还有下一条吗？\n"
                            f"如果没有，请回答「没有」；如果有，请直接给出内容。"
                        )
                        next_resp = await call_llm(
                            debater["model"], "",
                            next_prompt,
                            base_url=base_url, api_key=api_key, max_reply_tokens=600,
                        )
                        dlog(f"[fillForm askIterative {field_name} next idx={idx}] {next_resp!r}")
                        next_text = next_resp.strip()
                        if any(kw in next_text.lower() for kw in _no_kw):
                            break
                        if not next_text:
                            break  # 空响应视为结束，不 fatal（已有第一条）
                        item_ctx2 = {
                            **base_ctx,
                            "filled": dict(filled),
                            "item_index": idx,
                            "delta_text": f"该条目内容：{next_text}\n\n" + delta_text,
                        }
                        item_filled2 = await _fill_fields(
                            item_schema, item_ctx2, debater, base_url, api_key
                        )
                        if "text" not in item_filled2 or not item_filled2["text"]:
                            item_filled2["text"] = next_text
                        items.append(item_filled2)
                        idx += 1

            filled[field_name] = items

        else:
            # 未知 spec 类型，跳过
            dlog(f"[fillForm] 未知 spec type={field_type!r} for field {field_name!r}，跳过")

    return filled


async def _fallback_form_filling(
    debater: dict,
    initial_style: str,
    prev_participant: "dict | None",
    delta_entries: "list[dict]",
    base_url: str,
    api_key: str,
    failure_reason: str = "",
) -> "dict | None":
    """Schema-driven fillForm 实现。

    按 PARTICIPANT_SCHEMA 逐字段填充 ParticipantState：
      - computed 字段直接计算，不调 LLM
      - open 字段：retryWithFeedback(3)，非空即通过
      - choice 字段：retryWithFeedback(3)，解析失败 fatal（raise ValueError）
      - list 字段：先 askBulk，失败后 askIterative
        - askIterative 零条目但"没有"= 合法空列表
        - askIterative 连第一条都写不出来 = fatal（raise ValueError）

    fatal 路径会让 _compact_single_debater 里的外层降级到 usePrevious。

    返回 ParticipantState dict，或 None（外层用 hardFallback）
    """
    name = debater.get("name", "未知辩手")

    # ── fillForm 主流程 ────────────────────────────────────────────────────────
    try:
        delta_text = format_delta_entries_text(delta_entries)[:800]
        base_ctx: dict = {
            "debater_name": name,
            "delta_text": delta_text,
            "prev_active": prev_participant.get("active", True) if prev_participant else True,
            "prev_version": prev_participant.get("stance_version", 0) if prev_participant else 0,
            "filled": {},
            "item_index": 0,
        }

        result = await _fill_fields(
            PARTICIPANT_SCHEMA, base_ctx, debater, base_url, api_key
        )

        # 最终校验
        if not validate_participant_state(result):
            raise ValueError(f"fillForm validate_participant_state 失败: {list(result.keys())}")

        print(f"  ✅ {name} fillForm（schema-driven）成功", file=sys.stderr)
        return result

    except Exception as e:
        print(f"  ⚠️ {name} fillForm 失败: {e}", file=sys.stderr)

    # ── 极简兜底（不调 LLM）────────────────────────────────────────────────────
    try:
        last_content = ""
        for entry in reversed(delta_entries):
            content = entry.get("content", "")
            if content and content.strip():
                last_content = content.strip()[:200]
                break
        stance_fallback = last_content if last_content else initial_style or name
        active_flag = prev_participant.get("active", True) if prev_participant else True
        result_simple = {
            "name": name,
            "active": active_flag,
            "stance_version": (prev_participant.get("stance_version", 0) + 1) if prev_participant else 1,
            "stance": stance_fallback,
            "core_claims": [],
            "key_arguments": [],
            "abandoned_claims": prev_participant.get("abandoned_claims", []) if prev_participant else [],
        }
        print(f"  ⚠️ {name} 降级极简兜底", file=sys.stderr)
        return result_simple
    except Exception as e2:
        print(f"  ⚠️ {name} 极简兜底也失败: {e2}", file=sys.stderr)

    # ── 保留上次状态（prev_participant） ────────────────────────────────────────
    if prev_participant:
        print(f"  ⚠️ {name} 降级：保留上次状态", file=sys.stderr)
        return {
            **prev_participant,
            "stance_version": prev_participant.get("stance_version", 0) + 1,
            "_from_l5": True,
        }

    # ── 空状态（外层处理） ───────────────────────────────────────────────────────
    print(f"  ⚠️ {name} 降级：无 prev，返回 None", file=sys.stderr)
    return None


async def _compact_single_debater(
    debater: dict,
    delta_entries: "list[dict]",
    prev_state: "dict | None",
    cfg: dict,
) -> dict:
    """Phase B 单辩手立场自更新。返回 ParticipantState dict（失败时返回 fallback）。"""
    name = debater.get("name", "未知辩手")
    initial_style = debater.get("style", "")

    # 从上一次 compact state 中找该辩手的上一次 participant state
    prev_participant = None
    if prev_state and prev_state.get("participants"):
        prev_participant = next(
            (p for p in prev_state["participants"] if p.get("name") == name),
            None,
        )

    fallback = {
        "name": name,
        "stance_version": 0,
        "stance": initial_style,
        "core_claims": [],
        "key_arguments": [],
        "abandoned_claims": [],
    }

    debater_base_url = (debater.get("base_url", "") or "").strip()
    debater_api_key = (debater.get("api_key", "") or "").strip()

    # 获取 check model 配置（缺失则传播 ValueError）
    check_model, check_url, check_key = get_check_model_config(cfg)

    # 获取 embedding 配置（缺失则跳过 embedding 检查，仅用合理性校验）
    _embedding_available = True
    try:
        emb_model, emb_url, emb_key = get_embedding_config(cfg)
    except ValueError as emb_err:
        print(
            f"  ⚠️ embedding 配置缺失（{emb_err}），跳过 embedding 相似度检查",
            file=sys.stderr,
        )
        _embedding_available = False
        emb_model = emb_url = emb_key = ""

    prev_stance = ""
    if prev_participant:
        prev_stance = prev_participant.get("stance", "")

    failure_feedback = ""
    for attempt in range(3):
        try:
            sys_p, usr_p = build_phase_b_prompt(debater, initial_style, delta_entries, prev_stance=prev_stance)
            # 重试时把上次失败原因追加进 user prompt，让模型有方向地修正
            if attempt > 0 and failure_feedback:
                usr_p += (
                    f"\n\n【上一次立场生成失败，请根据以下反馈修正后重新输出】\n"
                    f"{failure_feedback}\n"
                    f"请重新输出符合要求的 JSON。"
                )
            raw = await call_llm(
                debater["model"],
                sys_p,
                usr_p,
                base_url=debater_base_url,
                api_key=debater_api_key,
                max_reply_tokens=3000,
            )
            dlog(f"[compact raw phase_b_raw] {raw!r}")
            result = json.loads(_strip_json_fence(raw))
            if not validate_participant_state(result):
                failure_feedback = f"输出 JSON 缺少必要字段，实际字段为：{list(result.keys())}"
                raise ValueError(f"ParticipantState 结构校验失败: {list(result.keys())}")

            # 合理性校验
            csys, cusr = build_validity_check_prompt(
                json.dumps(result, ensure_ascii=False)
            )
            check_resp = await call_llm(
                check_model,
                csys,
                cusr,
                base_url=check_url,
                api_key=check_key,
                max_reply_tokens=10,
            )
            dlog(f"[compact raw check_resp] {check_resp!r}")
            if not check_resp.strip().lower().startswith("y"):
                failure_feedback = f"立场合理性校验不通过（校验器回答：{check_resp.strip()[:100]}）。请确保立场描述内部自洽、符合辩论情境。"
                raise ValueError(f"合理性校验不通过: {check_resp.strip()[:100]}")

            # ── Embedding 相似度检查（checkWays 优先级逻辑）────────────────
            if _embedding_available:
                new_notes = result.get("stance", "")
                ref_notes = prev_stance if prev_stance else initial_style[:400]

                def _cos(a: list, b: list) -> float:
                    dot = sum(x * y for x, y in zip(a, b))
                    na = _math.sqrt(sum(x * x for x in a)) or 1.0
                    nb = _math.sqrt(sum(y * y for y in b)) or 1.0
                    return dot / (na * nb)

                try:
                    texts = [new_notes]
                    if prev_stance:
                        texts.append(prev_stance)
                    texts.append(initial_style[:400])

                    async with httpx.AsyncClient(timeout=30) as emb_client:
                        emb_resp = await emb_client.post(
                            emb_url.rstrip("/"),
                            headers={
                                "Authorization": f"Bearer {emb_key}",
                                "Content-Type": "application/json",
                            },
                            json={"model": emb_model, "input": texts},
                        )
                        emb_resp.raise_for_status()
                        emb_data = emb_resp.json()
                        vecs = [item["embedding"] for item in emb_data.get("data", [])]

                    if len(vecs) < 2:
                        raise ValueError("embedding 返回向量数不足")

                    vec_new = vecs[0]
                    vec_recent = vecs[1] if prev_stance and len(vecs) >= 3 else None
                    vec_origin = vecs[-1]

                    cos_orig = _cos(vec_new, vec_origin)
                    cos_rec = _cos(vec_new, vec_recent) if vec_recent is not None else None

                    # checkWays 优先级：先查 origin 底线，再查 recent 相邻
                    if cos_orig < 0.4:
                        needs_check = True
                        ref_is_origin = True
                    elif cos_rec is not None and cos_rec < 0.6:
                        needs_check = True
                        ref_is_origin = False
                    else:
                        needs_check = False
                        ref_is_origin = False

                    if needs_check:
                        ref_notes_text = initial_style[:400] if ref_is_origin else ref_notes
                        ref_label = "初始立场" if ref_is_origin else "上一版本立场"
                        cos_val = cos_orig if ref_is_origin else (cos_rec if cos_rec is not None else cos_orig)

                        current_result = result
                        for check_depth in range(2):
                            # Step 1：判断（REFINEMENT / DEFECTION）
                            drift_sys, drift_usr = build_stance_drift_check_prompt(
                                name, initial_style, ref_notes_text,
                                current_result.get("stance", ""),
                                json.dumps(current_result, ensure_ascii=False),
                                cos_val,
                            )
                            drift_resp = await call_llm(
                                check_model, drift_sys, drift_usr,
                                base_url=check_url, api_key=check_key,
                                max_reply_tokens=150,
                            )
                            dlog(f"[compact raw drift_resp] {drift_resp!r}")
                            first_line = (
                                drift_resp.strip().splitlines() or [""]
                            )[0].strip().upper()
                            print(
                                f"  🔍 {name} depth={check_depth} {ref_label} "
                                f"cos={cos_val:.3f} → {drift_resp[:60]}",
                                file=sys.stderr,
                            )

                            if first_line == "REFINEMENT":
                                result = current_result
                                break

                            # Step 2：DEFECTION → 修正（仅第一次）
                            if check_depth < 1:
                                corr_sys, corr_usr = build_stance_correction_prompt(
                                    name, initial_style,
                                    prev_stance if prev_stance else None,
                                    json.dumps(current_result, ensure_ascii=False),
                                    delta_entries,
                                    drift_resp.strip()[:300],
                                    include_initial=ref_is_origin,
                                )
                                corr_raw = await call_llm(
                                    debater["model"], corr_sys, corr_usr,
                                    base_url=debater_base_url,
                                    api_key=debater_api_key,
                                    max_reply_tokens=3000,
                                )
                                dlog(f"[compact raw corr_raw] {corr_raw!r}")
                                try:
                                    corr_parsed = json.loads(_strip_json_fence(corr_raw))
                                    if validate_participant_state(corr_parsed):
                                        current_result = corr_parsed
                                        continue
                                except Exception:
                                    pass
                                failure_feedback = (
                                    f"立场偏移（{ref_label} cos={cos_val:.3f}），"
                                    f"修正解析失败。检查器：{drift_resp[:100]}"
                                )
                                raise ValueError("立场偏移且修正失败")
                            else:
                                failure_feedback = (
                                    f"立场偏移（{ref_label} cos={cos_val:.3f}），"
                                    f"两次判断均为 DEFECTION。检查器：{drift_resp[:100]}"
                                )
                                raise ValueError(f"立场偏移无法修正: {drift_resp[:60]}")

                except ValueError:
                    raise
                except Exception as emb_exc:
                    print(
                        f"  ⚠️ embedding 检查出错（{emb_exc}），跳过本次相似度检查",
                        file=sys.stderr,
                    )

            return result

        except Exception as exc:
            # 若 failure_feedback 尚未被更具体的分支设置，填入通用 JSON 格式错误提示
            if not failure_feedback:
                exc_str = str(exc)
                if "control character" in exc_str or "Invalid control" in exc_str:
                    failure_feedback = (
                        f"JSON 解析失败：字符串值中包含非法控制字符（如裸换行符、制表符等）。"
                        f"请确保所有字符串字段内部的换行用 \\n 转义，制表符用 \\t 转义，"
                        f"不要在 JSON 字符串值中直接插入换行或其他控制字符。"
                    )
                else:
                    failure_feedback = (
                        f"输出格式有误（{exc}），请确保输出合法 JSON，"
                        f"字段包含：name, stance_version, stance, core_claims, key_arguments, abandoned_claims"
                    )
            if attempt < 2:
                print(
                    f"  ⚠️ Phase B {name} attempt {attempt + 1} 失败: {exc}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  ⚠️ Phase B {name} 3 次全失败，使用 fallback: {exc}",
                    file=sys.stderr,
                )

    # 三次 JSON 尝试全失败，进入渐进式降级
    print(f"  ⚠️ {name} JSON 解析三次全失败，尝试降级模式", file=sys.stderr)
    fallback_reason = ""
    for _fb_attempt in range(3):
        fallback_result = await _fallback_form_filling(
            debater, initial_style, prev_participant, delta_entries,
            debater_base_url, debater_api_key,
            failure_reason=fallback_reason,
        )
        if not fallback_result:
            break  # None = L5/空，不做 cos，直接用硬 fallback

        # 检查是否来自 L3 沿用（_from_l5 标记）
        if fallback_result.get("_from_l5"):
            fallback_result.pop("_from_l5", None)
            return fallback_result  # L3 沿用，跳过 cos

        # 删除临时标记字段（如有其他标记）
        fallback_result.pop("_from_l5", None)

        # cos 相似度检查（仅 stance）
        cos_val_fb: float = 0.0
        skip_cos = not _embedding_available
        if _embedding_available:
            new_stance = fallback_result.get("stance", "")
            ref_text = initial_style
            try:
                async with httpx.AsyncClient(timeout=30) as emb_client:
                    emb_resp = await emb_client.post(
                        emb_url.rstrip("/"),
                        headers={"Authorization": f"Bearer {emb_key}", "Content-Type": "application/json"},
                        json={"model": emb_model, "input": [new_stance, ref_text]},
                    )
                    emb_resp.raise_for_status()
                    vecs = [item["embedding"] for item in emb_resp.json().get("data", [])]
                if len(vecs) >= 2:
                    cos_val_fb = _cos(vecs[0], vecs[1])
                    dlog(f"[compact fallback cos] {name} attempt={_fb_attempt} cos={cos_val_fb:.3f}")
                    if cos_val_fb >= 0.4:
                        return fallback_result  # cosPass
                    # cos < 0.4，继续进行 LLM 语义检查
                else:
                    skip_cos = True  # embedding 返回不足，跳过 cos，直接 LLM 检查
            except Exception as e:
                dlog(f"[compact fallback cos error] {e}")
                skip_cos = True  # embedding 失败，跳过 cos，直接 LLM 检查

        # LLM 语义检查（无 embedding 或 cos < 0.4 时均进入）
        try:
            drift_sys, drift_usr = build_stance_drift_check_prompt(
                name, initial_style, initial_style,
                fallback_result.get("stance", ""),
                json.dumps(fallback_result, ensure_ascii=False),
                cos_val_fb,
            )
            semantic_resp = await call_llm(
                check_model, drift_sys, drift_usr,
                base_url=check_url, api_key=check_key,
                max_reply_tokens=150,
            )
            dlog(f"[compact fallback semantic check] {semantic_resp!r}")
            first_line = (semantic_resp.strip().splitlines() or [""])[0].strip().upper()
            print(
                f"  🔍 {name} fallback semantic check attempt={_fb_attempt} "
                f"cos={cos_val_fb:.3f} → {semantic_resp[:60]}",
                file=sys.stderr,
            )
            if first_line == "REFINEMENT":
                return fallback_result  # semanticPass
            # DEFECTION → 带理由重进大循环
            fallback_reason = (
                f"立场语义偏离初始立场（cos={cos_val_fb:.3f}，"
                f"检查器：{semantic_resp.strip()[:200]}）"
            )
            continue
        except Exception as sem_e:
            dlog(f"[compact fallback semantic check error] {sem_e}")
            # LLM 语义检查异常，fallback 回上次立场
            if prev_participant:
                fb = dict(prev_participant)
                fb["stance_version"] = prev_participant.get("stance_version", 0) + 1
                return fb
            return None

    # 3 次全不通过，接受最后结果
    if fallback_result:
        fallback_result.pop("_from_l5", None)
        return fallback_result

    return fallback


async def _do_compact(
    log: Log,
    cfg: dict,
    system_text: str,
    proxy_sent_counts: "dict[str, int] | None" = None,
) -> "tuple[dict, int]":
    """新 compact 核心函数：Phase A（公共信息）+ Phase B（辩手立场）。

    proxy_sent_counts: 各 proxy debater 的 sent_count 快照（key=debater name，value=sent_count）。
      若非 None，则写入 compact_checkpoint 的 state 中，供 proxy 重启后恢复。

    返回 (new_state, checkpoint_seq)。
    """
    prev_state = log.get_last_compact_state()
    prev_compact_seq = prev_state.get("covered_seq_end", 0) if prev_state is not None else 0

    # exclude_tags 说明：
    # - "thinking"：CoT 思考过程，内部计算，不暴露给摘要
    # - "summary"：裁判总结。其内容可能含有 mock 示例（如示例 JSON、假设场景），
    #   会污染 Phase A 的议题提取，导致 topic 被替换成示例里的内容。
    # - "compact_checkpoint"：上一次 compact 的结构化结果。
    #   该状态已通过两条独立路径传入：
    #     Phase A → build_phase_a_prompt(prev_state, ...)  ← prev_state 即上次 checkpoint 的 state
    #     Phase B → _compact_single_debater(..., prev_participant=...) ← 各辩手 stance 单独传入
    #   若同时出现在 delta_entries 里则重复传递。
    #   （当前实现中 compact_checkpoint 的 content="" 所以实际无害，但语义上应排除。）
    delta_entries = log.entries_since_seq(
        prev_compact_seq,
        exclude_tags=("thinking", "summary", "compact_checkpoint", "config_override"),
    )
    dlog(f"[compact] Phase A 开始  prev_compact_seq={prev_compact_seq}  delta={len(delta_entries)} 条")

    # 若无增量，返回已有 checkpoint 的 public_view
    if not delta_entries:
        last_cp = next(
            (e for e in reversed(log.entries) if e.get("tag") == "compact_checkpoint"),
            None,
        )
        if last_cp:
            state = last_cp.get("state") or parse_compact_checkpoint(last_cp["content"]).get("state")
            public_view = render_public_markdown(state) if state else last_cp.get("content", "（无公共视图）")
            return public_view, last_cp["seq"]
        # 没有任何 checkpoint，使用系统文本
        return system_text, 0

    # ── Phase A: 公共信息生成 ──────────────────────────────────
    model, base_url, api_key = get_compact_model_config(cfg)  # ValueError 传播

    phase_a_result: "dict | None" = None

    phase_a_feedback = ""
    for attempt in range(3):
        try:
            sys_p, usr_p = build_phase_a_prompt(prev_state, delta_entries)
            # 重试时把上次失败原因追加进 user prompt，让模型有方向地修正
            if attempt > 0 and phase_a_feedback:
                usr_p += (
                    f"\n\n【上一次公共信息生成失败，请根据以下反馈修正后重新输出】\n"
                    f"{phase_a_feedback}\n"
                    f"请重新输出符合要求的 JSON。"
                )
            dlog(f"[compact] Phase A LLM call  model={model}  url={base_url}")
            raw = await call_llm(
                model, sys_p, usr_p,
                base_url=base_url, api_key=api_key, max_reply_tokens=4000,
            )
            dlog(f"[compact raw phase_a_raw] {raw!r}")
            parsed = json.loads(_strip_json_fence(raw))
            is_valid, errors = validate_public_info(parsed, prev_state)
            if not is_valid:
                phase_a_feedback = f"输出 JSON 单调性校验失败：{errors}，请修正后重新输出。"
                raise ValueError(f"Phase A 单调性校验失败: {errors}")
            phase_a_result = parsed
            dlog(f"[compact] Phase A 成功  axioms={len(parsed.get('axioms',[]))}  disputes={len(parsed.get('disputes',[]))}  pruned={len(parsed.get('pruned_paths',[]))}")
            break
        except Exception as exc:
            # 若 phase_a_feedback 尚未被更具体的分支设置，填入通用提示
            if not phase_a_feedback:
                exc_str = str(exc)
                if "control character" in exc_str or "Invalid control" in exc_str:
                    phase_a_feedback = (
                        f"JSON 解析失败：字符串值中包含非法控制字符（如裸换行符、制表符等）。"
                        f"请确保所有字符串字段内部的换行用 \\n 转义，制表符用 \\t 转义，"
                        f"不要在 JSON 字符串值中直接插入换行或其他控制字符。"
                    )
                else:
                    phase_a_feedback = (
                        f"输出格式有误（{exc}），请确保输出合法 JSON，"
                        f"字段包含：topic, axioms, disputes, pruned_paths"
                    )
            dlog(f"[compact] Phase A attempt {attempt+1} 失败: {exc}")
            if attempt < 2:
                print(
                    f"  ⚠️ Phase A attempt {attempt + 1} 失败: {exc}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  ⚠️ Phase A 3 次全失败，降级为逐字段填表: {exc}",
                    file=sys.stderr,
                )

    if phase_a_result is None:
        # Phase A 降级：逐字段独立调用 LLM
        dlog("[compact] Phase A 降级为逐字段模式")
        _fallback_topic = (
            prev_state.get("topic") if prev_state
            else {"current_formulation": "（无法提取）", "notes": None}
        ) or {"current_formulation": "（无法提取）", "notes": None}
        _fallback_axioms = prev_state.get("axioms", []) if prev_state else []
        _fallback_disputes = prev_state.get("disputes", []) if prev_state else []
        _fallback_pruned = prev_state.get("pruned_paths", []) if prev_state else []

        delta_text_brief = format_delta_entries_text(delta_entries)[:3000]

        async def _fetch_field(field_name: str, field_hint: str, fallback_val):
            field_feedback = ""
            for _attempt in range(3):
                try:
                    usr = f"{delta_text_brief}\n\n请提取「{field_name}」字段，{field_hint}。只输出该字段的 JSON 值。"
                    if _attempt > 0 and field_feedback:
                        usr += (
                            f"\n\n【上一次提取失败，请根据以下反馈修正后重新输出】\n"
                            f"{field_feedback}\n"
                            f"请重新输出符合要求的 JSON。"
                        )
                    r = await call_llm(
                        model,
                        "你是辩论状态提取器。只输出要求的 JSON 字段，不附加任何文字。",
                        usr,
                        base_url=base_url, api_key=api_key, max_reply_tokens=1000,
                    )
                    dlog(f"[compact raw _fetch_field({field_name!r})] {r!r}")
                    return json.loads(_strip_json_fence(r))
                except Exception as e:
                    exc_str = str(e)
                    if "control character" in exc_str or "Invalid control" in exc_str:
                        field_feedback = (
                            f"JSON 解析失败：字符串值中包含非法控制字符（如裸换行符、制表符等）。"
                            f"请确保所有字符串字段内部的换行用 \\n 转义，制表符用 \\t 转义，"
                            f"不要在 JSON 字符串值中直接插入换行或其他控制字符。"
                        )
                    else:
                        field_feedback = f"输出格式有误（{e}），请确保输出合法 JSON，{field_hint}。"
                    print(f"  ⚠️ Phase A 降级字段 {field_name} attempt {_attempt+1} 失败: {e}", file=sys.stderr)
            return fallback_val

        topic_val = await _fetch_field(
            "topic", '格式: {"current_formulation": "...", "notes": null}', _fallback_topic
        )
        axioms_val = await _fetch_field(
            "axioms", "格式: [\"共识1\", \"共识2\"]", _fallback_axioms
        )
        disputes_val = await _fetch_field(
            "disputes",
            '格式: [{"id":"D1","title":"...","status":"open","positions":{},"resolution":null}]',
            _fallback_disputes,
        )
        pruned_val = await _fetch_field(
            "pruned_paths",
            '格式: [{"id":"P1","description":"...","reason":"...","decided_by":"...","merged":false,"merged_from":null}]',
            _fallback_pruned,
        )

        phase_a_result = {
            "topic": topic_val,
            "axioms": axioms_val if isinstance(axioms_val, list) else _fallback_axioms,
            "disputes": disputes_val if isinstance(disputes_val, list) else _fallback_disputes,
            "pruned_paths": pruned_val if isinstance(pruned_val, list) else _fallback_pruned,
        }

    # 处理 pruned_paths 超 10 条的情况
    if isinstance(phase_a_result.get("pruned_paths"), list):
        phase_a_result["pruned_paths"] = merge_pruned_paths_if_needed(
            phase_a_result["pruned_paths"]
        )

    # ── Phase B: 辩手立场自更新（并行） ──────────────────────────
    debaters = cfg.get("debaters", [])
    dlog(f"[compact] Phase B 开始  辩手数={len(debaters)}")
    participant_states = await asyncio.gather(
        *[
            _compact_single_debater(d, delta_entries, prev_state, cfg)
            for d in debaters
        ]
    )

    # ── 合并与存储 ────────────────────────────────────────────────
    # Derive compact_version by counting existing checkpoints (1-based)
    compact_version = (
        sum(1 for e in log.entries if e.get("tag") == "compact_checkpoint") + 1
    )
    new_state = {
        **phase_a_result,
        "participants": list(participant_states),
        "compact_version": compact_version,
        "covered_seq_end": delta_entries[-1]["seq"],
        "prev_compact_seq": prev_compact_seq,
    }
    if proxy_sent_counts is not None:
        new_state["proxy_sent_counts"] = proxy_sent_counts
    log.add("Compact Checkpoint", "", "compact_checkpoint", extra={"state": new_state})

    checkpoint_seq = next(
        e["seq"] for e in reversed(log.entries) if e.get("tag") == "compact_checkpoint"
    )
    return new_state, checkpoint_seq
