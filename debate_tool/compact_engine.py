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


def _compact_for_retry(
    entries: list[dict],
    model_max_tokens: int,
    num_debaters: int,
    system_text: str,
) -> str:
    budget = int(model_max_tokens * 0.7)
    segment_chars = max(budget * 3, _MIN_SEGMENT_CHARS)

    while True:
        result = build_compact_context(
            entries,
            token_budget=budget,
            num_debaters=num_debaters,
            system_text=system_text,
        )
        if len(result) <= segment_chars:
            return result
        segment_chars = int(segment_chars * 0.8)
        if segment_chars < _MIN_SEGMENT_CHARS:
            raise RuntimeError(
                f"compact 后上下文仍超限且段长已压至 {segment_chars} 字符 (<{_MIN_SEGMENT_CHARS})，"
                f"无法继续压缩。请手动 compact 或缩减辩论轮次。"
            )
        print(
            f"  ⚠️ compact 后仍超限，段长缩至 {segment_chars}，重新压缩...",
            file=sys.stderr,
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


async def _fallback_form_filling(
    debater: dict,
    initial_style: str,
    prev_participant: "dict | None",
    delta_entries: "list[dict]",
    base_url: str,
    api_key: str,
    failure_reason: str = "",
) -> "dict | None":
    """
    JSON 解析三次全失败后的渐进式降级策略（对弱模型鲁棒版）。

    Level 1: 逐字段单问（open text）
      - 只问 stance（开放题，任何非空返回直接用）
      - 对 prev_participant 每个 core_claim 单独问 1/2 选择题
      - 用 validate_participant_state 校验结果
    Level 2: 极简兜底（不调用 LLM）
      - stance 取 delta_entries 最后一条 content 前200字
      - claims/arguments 全空
    Level 3: 保留上次状态（prev_participant 不为 None）
      - 复制 prev_participant，bump stance_version
    Level 4: 空状态兜底（prev_participant 为 None）
      - 返回 None，外层处理

    返回 ParticipantState dict，或 None（让外层用 fallback）
    """
    name = debater.get("name", "未知辩手")
    active_flag = prev_participant.get("active", True) if prev_participant else True

    # ── Level 1: 逐字段单问（open text / 1-2 选择题） ────────────────────────────────────
    l1_reason = ""
    for _l1_attempt in range(3):
        try:
            delta_text = format_delta_entries_text(delta_entries)[:800]
            l1_stance_prompt = f"你是辩手「{name}」。你现在的辩论立场是什么？（任意文字，200字以内）\n\n近期辩论记录：\n{delta_text}"
            if l1_reason:
                l1_stance_prompt += f"\n（上次失败原因：{l1_reason}，请重新尝试）"
            stance_resp = await call_llm(
                debater["model"], "",
                l1_stance_prompt,
                base_url=base_url, api_key=api_key, max_reply_tokens=300,
            )
            dlog(f"[compact raw fallback L1 stance] {stance_resp!r}")
            stance = stance_resp.strip()

            if not stance:
                raise ValueError("stance 返回为空")

            claims = []
            if prev_participant and prev_participant.get("core_claims"):
                for c in prev_participant["core_claims"]:
                    claim_text = c.get("text", "")
                    choice_resp = await call_llm(
                        debater["model"], "",
                        f"主张「{claim_text}」还有效吗？回答 1（有效）或 2（已放弃）",
                        base_url=base_url, api_key=api_key, max_reply_tokens=10,
                    )
                    dlog(f"[compact raw fallback L1 claim] {choice_resp!r}")
                    digit = next((ch for ch in choice_resp if ch in "12"), None)
                    if digit == "2":
                        claims.append({**c, "status": "abandoned"})
                    else:
                        claims.append({**c, "status": "active"})

            result = {
                "name": name,
                "active": active_flag,
                "stance_version": (prev_participant.get("stance_version", 0) + 1) if prev_participant else 1,
                "stance": stance,
                "core_claims": claims,
                "key_arguments": prev_participant.get("key_arguments", []) if prev_participant else [],
                "abandoned_claims": prev_participant.get("abandoned_claims", []) if prev_participant else [],
            }
            if not validate_participant_state(result):
                raise ValueError(f"L1 validate_participant_state 校验失败: {list(result.keys())}")
            print(f"  ✅ {name} 降级 L1（逐字段单问）成功", file=sys.stderr)
            return result
        except Exception as e:
            l1_reason = f"上次失败：{str(e)[:100]}"
            if _l1_attempt < 2:
                continue
            print(f"  ⚠️ {name} 降级 L1 失败（3次全败）: {e}", file=sys.stderr)

    # ── Level 2: 极简兜底（不调用 LLM） ────────────────────────────────────
    l2_reason = ""
    for _l2_attempt in range(3):
        try:
            last_content = ""
            for entry in reversed(delta_entries):
                content = entry.get("content", "")
                if content and content.strip():
                    last_content = content.strip()[:200]
                    break
            stance_l2 = last_content if last_content else initial_style or name

            result_l2 = {
                "name": name,
                "active": active_flag,
                "stance_version": (prev_participant.get("stance_version", 0) + 1) if prev_participant else 1,
                "stance": stance_l2,
                "core_claims": [],
                "key_arguments": [],
                "abandoned_claims": prev_participant.get("abandoned_claims", []) if prev_participant else [],
            }
            print(f"  ⚠️ {name} 降级 L2（极简兜底）", file=sys.stderr)
            return result_l2
        except Exception as e:
            l2_reason = f"上次失败：{str(e)[:100]}"
            if _l2_attempt < 2:
                continue
            print(f"  ⚠️ {name} 降级 L2 失败（3次全败）: {e}", file=sys.stderr)

    # ── Level 3: 保留上次状态 ────────────────────────────────────
    l3_reason = ""
    for _l3_attempt in range(3):
        try:
            if not prev_participant:
                raise ValueError("无 prev_participant，无法保留上次状态")
            print(f"  ⚠️ {name} 降级 L3（保留上次状态）", file=sys.stderr)
            return {
                **prev_participant,
                "stance_version": prev_participant.get("stance_version", 0) + 1,
                "_from_l5": True,
            }
        except Exception as e:
            l3_reason = f"上次失败：{str(e)[:100]}"
            if _l3_attempt < 2:
                continue
            print(f"  ⚠️ {name} 降级 L3 失败（3次全败）: {e}", file=sys.stderr)

    # ── Level 4: 极简逐字段单问（不依赖 delta_text） ────────────────────────────────────
    l4_reason = ""
    for _l4_attempt in range(3):
        try:
            l4_stance_prompt = f"你是辩手「{name}」。\n你现在的辩论立场是什么？（任意文字，200字以内）"
            if failure_reason:
                l4_stance_prompt += f"\n\n（注意：{failure_reason}）"
            if l4_reason:
                l4_stance_prompt += f"\n（上次失败原因：{l4_reason}，请重新尝试）"
            stance_resp = await call_llm(
                debater["model"], "",
                l4_stance_prompt,
                base_url=base_url, api_key=api_key, max_reply_tokens=500,
            )
            dlog(f"[compact raw fallback L4 stance] {stance_resp!r}")
            stance_text = stance_resp.strip()

            if not stance_text:
                raise ValueError("L4 stance 返回为空")

            claims_l4 = []
            if prev_participant and prev_participant.get("core_claims"):
                all_ok = True
                for c in prev_participant["core_claims"]:
                    claim_text = c.get("text", "")
                    status_resp = await call_llm(
                        debater["model"], "",
                        f"你是辩手「{name}」。\n主张「{claim_text}」还有效吗？\n回答 1（有效）或 2（已放弃）",
                        base_url=base_url, api_key=api_key, max_reply_tokens=500,
                    )
                    dlog(f"[compact raw fallback L4 claim] {status_resp!r}")
                    digit = next((ch for ch in status_resp if ch in "12"), None)
                    if digit is None:
                        all_ok = False
                        break
                    if digit == "2":
                        claims_l4.append({**c, "status": "abandoned"})
                    else:
                        claims_l4.append({**c, "status": "active"})
                if not all_ok:
                    raise ValueError("L4 claim 状态解析失败，无法取到 1/2")

            result_l4 = {
                "name": name,
                "active": active_flag,
                "stance_version": (prev_participant.get("stance_version", 0) + 1) if prev_participant else 1,
                "stance": stance_text,
                "core_claims": claims_l4,
                "key_arguments": prev_participant.get("key_arguments", []) if prev_participant else [],
                "abandoned_claims": prev_participant.get("abandoned_claims", []) if prev_participant else [],
            }
            print(f"  ✅ {name} 极简单问模式成功", file=sys.stderr)
            return result_l4
        except Exception as e:
            l4_reason = f"上次失败：{str(e)[:100]}"
            if _l4_attempt < 2:
                continue
            print(f"  ⚠️ {name} 降级 L4 失败（3次全败）: {e}", file=sys.stderr)

    # ── Level 5: 空状态（外层处理） ────────────────────────────────────
    print(f"  ⚠️ {name} 降级 L5（无 prev，返回 None）", file=sys.stderr)
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
                        cos_val = cos_orig if ref_is_origin else cos_rec

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
) -> "tuple[dict, int]":
    """新 compact 核心函数：Phase A（公共信息）+ Phase B（辩手立场）。

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

    for attempt in range(3):
        try:
            sys_p, usr_p = build_phase_a_prompt(prev_state, delta_entries)
            dlog(f"[compact] Phase A LLM call  model={model}  url={base_url}")
            raw = await call_llm(
                model, sys_p, usr_p,
                base_url=base_url, api_key=api_key, max_reply_tokens=4000,
            )
            dlog(f"[compact raw phase_a_raw] {raw!r}")
            parsed = json.loads(_strip_json_fence(raw))
            is_valid, errors = validate_public_info(parsed, prev_state)
            if not is_valid:
                raise ValueError(f"Phase A 单调性校验失败: {errors}")
            phase_a_result = parsed
            dlog(f"[compact] Phase A 成功  axioms={len(parsed.get('axioms',[]))}  disputes={len(parsed.get('disputes',[]))}  pruned={len(parsed.get('pruned_paths',[]))}")
            break
        except Exception as exc:
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
            try:
                r = await call_llm(
                    model,
                    "你是辩论状态提取器。只输出要求的 JSON 字段，不附加任何文字。",
                    f"{delta_text_brief}\n\n请提取「{field_name}」字段，{field_hint}。只输出该字段的 JSON 值。",
                    base_url=base_url, api_key=api_key, max_reply_tokens=1000,
                )
                dlog(f"[compact raw _fetch_field({field_name!r})] {r!r}")
                return json.loads(_strip_json_fence(r))
            except Exception as e:
                print(f"  ⚠️ Phase A 降级字段 {field_name} 失败: {e}", file=sys.stderr)
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
    new_state = {
        **phase_a_result,
        "participants": list(participant_states),
        "compact_version": 1,
        "covered_seq_end": delta_entries[-1]["seq"],
        "prev_compact_seq": prev_compact_seq,
    }
    log.add("Compact Checkpoint", "", "compact_checkpoint", extra={"state": new_state})

    checkpoint_seq = next(
        e["seq"] for e in reversed(log.entries) if e.get("tag") == "compact_checkpoint"
    )
    return new_state, checkpoint_seq
