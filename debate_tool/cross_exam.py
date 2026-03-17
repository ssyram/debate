"""Cross-examination logic for debate-tool."""
from __future__ import annotations

import asyncio
import json
import re as _re
import sys
from pathlib import Path

from .debug_log import dlog
from .llm_client import call_llm
from .log_io import Log


async def run_cross_exam(
    debaters: list[dict],
    log: Log,
    topic: str,
    rnd: int,
    *,
    max_reply_tokens: int,
    timeout: int,
    debate_base_url: str,
    debate_api_key: str,
) -> set[str]:
    """Dynamic cross-examination after a debate round.

    Each questioner sees all debaters' latest speeches, then chooses whom to challenge.
    All challenge prompts are issued before any cross-exam entry is written to the log,
    so questioners behave as if they are asking simultaneously within the sub-round.
    Returns the set of debater names who were challenged (parsed from LLM responses).
    """
    n = len(debaters)
    # Collect latest round speeches — skip thinking entries, take last N non-thinking entries
    non_thinking = [e for e in log.entries if e.get("tag") != "thinking"]
    latest_entries = non_thinking[-n:]
    speech_by_name: dict[str, str] = {e["name"]: e["content"] for e in latest_entries}

    challenged_set: set[str] = set()
    debater_names = [d["name"] for d in debaters]

    async def ask_cross_exam(questioner: dict) -> tuple[dict, dict | None, bool]:
        q_base_url = (questioner.get("base_url", "") or debate_base_url).strip()
        q_api_key = (questioner.get("api_key", "") or debate_api_key).strip()

        opponents = [d for d in debater_names if d != questioner["name"]]
        selection_payload = {
            "topic": topic,
            "round": rnd,
            "questioner": {
                "name": questioner["name"],
                "style": questioner["style"],
            },
            "opponents": opponents,
            "speeches": [
                {
                    "name": d["name"],
                    "round": rnd,
                    "content": speech_by_name.get(d["name"], "(无发言)"),
                }
                for d in debaters
            ],
        }

        select_prompt = (
            f"你是「{questioner['name']}」（{questioner['style']}），现在进入同步质询子回合。\n"
            f"你的任务是先选择一个要质询的对象。\n"
            f"【输出要求】只输出一个 JSON 对象，不要输出其他文本。\n"
            f"JSON 结构必须为：\n"
            f"{{\n"
            f"  \"target\": \"<被质询者姓名>\"\n"
            f"}}\n\n"
            f"【硬约束】\n"
            f"- target 必须是以下之一：{', '.join(opponents)}\n"
            f"- 不要输出解释，不要输出长文"
        )
        select_user = json.dumps(selection_payload, ensure_ascii=False, indent=2)

        selected_raw = await call_llm(
            questioner["model"],
            select_prompt,
            select_user,
            max_reply_tokens=min(max_reply_tokens, 1200),
            timeout=timeout,
            base_url=q_base_url,
            api_key=q_api_key,
        )
        selected_target = _extract_cross_exam_selected_target(
            selected_raw,
            questioner_name=questioner["name"],
            debater_names=debater_names,
        )
        if selected_target is None:
            selected_retry_prompt = (
                f"你上次输出不合规。"
                f"现在必须只输出一个 JSON 对象，格式严格为 {{\"target\": \"<姓名>\"}}。"
            )
            selected_retry_user = (
                f"候选 target：{', '.join(opponents)}\n"
                f"你上次输出如下（不合规）：\n{selected_raw[:3000]}\n\n"
                f"请重输，只允许 JSON。"
            )
            selected_retry_raw = await call_llm(
                questioner["model"],
                selected_retry_prompt,
                selected_retry_user,
                temperature=0.1,
                max_reply_tokens=300,
                timeout=timeout,
                base_url=q_base_url,
                api_key=q_api_key,
            )
            selected_target = _extract_cross_exam_selected_target(
                selected_retry_raw,
                questioner_name=questioner["name"],
                debater_names=debater_names,
            )

        if selected_target is None:
            return questioner, None, True

        question_payload = {
            "topic": topic,
            "round": rnd,
            "questioner": {
                "name": questioner["name"],
                "style": questioner["style"],
            },
            "target": selected_target,
            "target_speech": {
                "name": selected_target,
                "round": rnd,
                "content": speech_by_name.get(selected_target, "(无发言)"),
            },
        }

        sys_prompt = (
            f"你是「{questioner['name']}」（{questioner['style']}），现在进入质询环节。\n"
            f"你会收到一个 JSON 输入。请只基于该输入完成质询。\n\n"
            f"【输出要求】只输出一个 JSON 对象，不要输出 Markdown、解释、前后缀文本。\n"
            f"JSON 结构必须为：\n"
            f"{{\n"
            f"  \"target\": \"{selected_target}\",\n"
            f"  \"reason\": \"<一句话质询理由>\",\n"
            f"  \"questions\": [\"<问题1>\", \"<问题2>\", \"<问题3，可选>\"]\n"
            f"}}\n\n"
            f"【硬约束】\n"
            f"- target 必须是 {selected_target}，不可改成其他人\n"
            f"- questions 长度为 1 到 5\n"
            f"- 每个问题优先指向 target 的本轮发言中的具体说法，但是也可以指向历史发言（最多两条历史发言相关，且至少一条本轮发言相关）\n"
            f"- 本回合执行结构化输出协议，优先级高于人格化写作风格；不要输出长文论证\n"
            f"- 这是一个同步质询子回合：你现在看不到别人提出的问题，"
            f"也不要回应任何别人可能对你提出的质询\n"
            f"- 不要输出综合方案、实施路线图、结论性长文。"
        )
        user_ctx = json.dumps(question_payload, ensure_ascii=False, indent=2)

        raw_result = await call_llm(
            questioner["model"],
            sys_prompt,
            user_ctx,
            max_reply_tokens=max_reply_tokens,
            timeout=timeout,
            base_url=q_base_url,
            api_key=q_api_key,
        )
        payload = _extract_valid_cross_exam_payload(
            raw_result,
            questioner_name=questioner["name"],
            debater_names=debater_names,
            expected_target=selected_target,
        )
        if payload is None:
            repair_system = (
                f"你上次输出不合规。"
                f"现在必须只输出一个 JSON 对象，严格按协议返回。"
            )
            repair_user = (
                f"固定 target：{selected_target}\n"
                f"协议：target 必须是 {selected_target}，reason 为一句话，questions 为 2-3 个字符串。\n"
                f"原始输出如下（可能不合规）：\n"
                f"{raw_result[:4000]}"
            )
            repaired = await call_llm(
                questioner["model"],
                repair_system,
                repair_user,
                temperature=0.1,
                max_reply_tokens=min(max_reply_tokens, 1200),
                timeout=timeout,
                base_url=q_base_url,
                api_key=q_api_key,
            )
            repaired_payload = _extract_valid_cross_exam_payload(
                repaired,
                questioner_name=questioner["name"],
                debater_names=debater_names,
                expected_target=selected_target,
            )
            if repaired_payload is not None:
                return questioner, repaired_payload, False

            form_system = (
                f"你是质询填表助手。"
                f"请按填表格式输出，不要输出其他文本。"
            )
            form_user = (
                f"questioner: {questioner['name']}\n"
                f"target: {selected_target}\n"
                f"target_speech:\n{speech_by_name.get(selected_target, '(无发言)')[:4000]}\n\n"
                f"请按以下格式填写：\n"
                f"质询对象: {selected_target}\n"
                f"质询理由: <一句话>\n"
                f"问题1: <问题>\n"
                f"问题2: <问题>\n"
                f"问题3: <可选问题>"
            )
            form_raw = await call_llm(
                questioner["model"],
                form_system,
                form_user,
                temperature=0.1,
                max_reply_tokens=min(max_reply_tokens, 1200),
                timeout=timeout,
                base_url=q_base_url,
                api_key=q_api_key,
            )
            form_payload = _extract_cross_exam_form_payload(form_raw, selected_target=selected_target)
            if form_payload is not None:
                return questioner, form_payload, False

            # ── 极简降级策略（3 次 JSON 结构化尝试全部失败后追加） ──
            # Step 1: 选择题——让模型只回答数字来选目标辩手
            fb_opponents = [d for d in debater_names if d != questioner["name"]]
            fb_numbered = "\n".join(f"{i + 1}={name}" for i, name in enumerate(fb_opponents))
            fb_select_prompt = (
                f"你是辩手「{questioner['name']}」。\n"
                f"你想在本轮交叉质询中攻击哪位辩手？\n"
                f"{fb_numbered}\n"
                f"只回答数字。"
            )
            fb_select_resp = await call_llm(
                questioner["model"],
                fb_select_prompt,
                "",
                max_reply_tokens=10,
                timeout=timeout,
                base_url=q_base_url,
                api_key=q_api_key,
            )
            dlog(f"[cross-exam raw fallback target] {fb_select_resp!r}")
            fb_digit = next((c for c in fb_select_resp if c.isdigit()), None)
            fb_idx = int(fb_digit) - 1 if fb_digit is not None else -1
            if fb_idx < 0 or fb_idx >= len(fb_opponents):
                return questioner, None, True
            fb_target_name = fb_opponents[fb_idx]

            # Step 2: 收集目标辩手发言（最后 3 条，前 800 字）
            fb_target_entries = [
                e for e in log.entries
                if e.get("name") == fb_target_name and e.get("tag") != "thinking"
            ][-3:]
            fb_target_text = "\n\n".join(
                f"[{e.get('seq', '?')}] {e['content']}" for e in fb_target_entries
            )[:800] or "(无发言记录)"

            # Step 3: reason 问答
            fb_reason_prompt = (
                f"你是辩手「{questioner['name']}」。\n"
                f"以下是「{fb_target_name}」的发言记录：\n"
                f"{fb_target_text}\n\n"
                f"你为什么要质疑他？（任意文字，100字以内）"
            )
            fb_reason_resp = await call_llm(
                questioner["model"],
                fb_reason_prompt,
                "",
                max_reply_tokens=200,
                timeout=timeout,
                base_url=q_base_url,
                api_key=q_api_key,
            )
            dlog(f"[cross-exam raw fallback reason] {fb_reason_resp!r}")
            fb_reason = fb_reason_resp.strip() or "质疑其论点的合理性"

            # Step 4: question 问答
            fb_question_prompt = (
                f"你是辩手「{questioner['name']}」。\n"
                f"以下是「{fb_target_name}」的发言记录：\n"
                f"{fb_target_text}\n\n"
                f"你想问他什么问题？（任意文字，100字以内）"
            )
            fb_question_resp = await call_llm(
                questioner["model"],
                fb_question_prompt,
                "",
                max_reply_tokens=200,
                timeout=timeout,
                base_url=q_base_url,
                api_key=q_api_key,
            )
            dlog(f"[cross-exam raw fallback question] {fb_question_resp!r}")
            fb_question = fb_question_resp.strip() or "请进一步解释你的立场。"

            # Step 5: 组装 payload
            fb_payload = {
                "target": fb_target_name,
                "reason": fb_reason,
                "questions": [fb_question],
            }
            return questioner, fb_payload, False

        return questioner, payload, False

    cross_exam_results = await asyncio.gather(*[ask_cross_exam(questioner) for questioner in debaters])

    for questioner, payload, no_opinion in cross_exam_results:
        if payload is not None:
            challenged_name = payload["target"]
            challenged_set.add(challenged_name)
            log.add(
                f"{questioner['name']} → {challenged_name}",
                json.dumps(payload, ensure_ascii=False, indent=2),
                "cross_exam",
            )
        elif no_opinion:
            log.add(f"{questioner['name']} → (本轮没有意见)", "本轮没有意见", "cross_exam")
        else:
            log.add(f"{questioner['name']} → (本轮没有意见)", "本轮没有意见", "cross_exam")

    return challenged_set


def _resolve_debater_name(candidate: str, *, questioner_name: str, debater_names: list[str]) -> str | None:
    text = candidate.strip().strip(" \t\n\r\"'`\u201c\u201d\u2018\u2019[]()（）【】《》<>,，。；;：:")
    if not text:
        return None

    others = [name for name in debater_names if name != questioner_name]

    for name in others:
        if text == name:
            return name

    for name in others:
        if name in text or text in name:
            return name

    return None


def _extract_cross_exam_target(result: str, *, questioner_name: str, debater_names: list[str]) -> str | None:
    others = [name for name in debater_names if name != questioner_name]
    if not others:
        return None

    payload = _extract_cross_exam_json(result)
    if payload and isinstance(payload.get("target"), str):
        resolved = _resolve_debater_name(
            payload["target"],
            questioner_name=questioner_name,
            debater_names=debater_names,
        )
        if resolved:
            return resolved

    # 1) Strict/near-strict target markers
    patterns = [
        _re.compile(r"^\s*质询对象\s*[：:]\s*(.+?)\s*$", _re.M),
        _re.compile(r"^\s*(?:target|challenged|challenge)\s*[：:]\s*(.+?)\s*$", _re.M | _re.I),
        _re.compile(r"\[TARGET\]\s*(.+?)\s*\[/TARGET\]", _re.I | _re.S),
    ]
    for pat in patterns:
        match = pat.search(result)
        if not match:
            continue
        resolved = _resolve_debater_name(
            match.group(1),
            questioner_name=questioner_name,
            debater_names=debater_names,
        )
        if resolved:
            return resolved

    # 2) If there is only one possible opponent, lock to that opponent.
    if len(others) == 1:
        return others[0]

    # 3) Mention-frequency fallback for multi-debater cases.
    hits = {name: result.count(name) for name in others}
    best = max(hits.values()) if hits else 0
    if best > 0:
        winners = [name for name, cnt in hits.items() if cnt == best]
        if len(winners) == 1:
            return winners[0]

    return None


def _extract_cross_exam_json(result: str) -> dict | None:
    text = result.strip()
    candidates: list[str] = [text]

    fence = _re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, _re.I)
    if fence:
        candidates.append(fence.group(1).strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    brace_match = _re.search(r"(\{[\s\S]*\})", text)
    if brace_match:
        try:
            parsed = json.loads(brace_match.group(1))
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    return None


def _extract_valid_cross_exam_payload(
    result: str,
    *,
    questioner_name: str,
    debater_names: list[str],
    expected_target: str | None = None,
) -> dict | None:
    payload = _extract_cross_exam_json(result)
    if not isinstance(payload, dict):
        return None

    target_raw = payload.get("target")
    reason_raw = payload.get("reason")
    questions_raw = payload.get("questions")

    if not isinstance(target_raw, str):
        return None
    target = _resolve_debater_name(
        target_raw,
        questioner_name=questioner_name,
        debater_names=debater_names,
    )
    if target is None:
        return None
    if expected_target is not None and target != expected_target:
        return None

    if not isinstance(reason_raw, str) or not reason_raw.strip():
        return None

    if not isinstance(questions_raw, list):
        return None
    questions = [q.strip() for q in questions_raw if isinstance(q, str) and q.strip()]
    if len(questions) < 2:
        return None

    return {
        "target": target,
        "reason": reason_raw.strip(),
        "questions": questions[:3],
    }


def _extract_cross_exam_selected_target(result: str, *, questioner_name: str, debater_names: list[str]) -> str | None:
    payload = _extract_cross_exam_json(result)
    if not isinstance(payload, dict):
        return None
    target_raw = payload.get("target")
    if not isinstance(target_raw, str):
        return None
    return _resolve_debater_name(
        target_raw,
        questioner_name=questioner_name,
        debater_names=debater_names,
    )


def _extract_cross_exam_form_payload(result: str, *, selected_target: str) -> dict | None:
    text = result.strip()
    if not text:
        return None

    reason_match = _re.search(r"^(?:质询理由|理由)\s*[：:]\s*(.+)$", text, _re.M)
    reason = reason_match.group(1).strip() if reason_match else ""

    question_matches = _re.findall(r"^(?:问题\s*\d+|Q\s*\d+)\s*[：:]\s*(.+)$", text, _re.M | _re.I)
    questions = [q.strip() for q in question_matches if q.strip()]

    if len(questions) < 2:
        bullet_matches = _re.findall(r"^(?:[-*]|\d+[.)])\s*(.+)$", text, _re.M)
        for line in bullet_matches:
            stripped = line.strip()
            if stripped and stripped not in questions:
                questions.append(stripped)
            if len(questions) >= 3:
                break

    if not reason or len(questions) < 2:
        return None

    return {
        "target": selected_target,
        "reason": reason,
        "questions": questions[:3],
    }
