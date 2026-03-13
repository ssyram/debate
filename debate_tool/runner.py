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
import threading
from datetime import datetime
from pathlib import Path

import httpx
import yaml

import math as _math  # noqa: F401 — used in cosine similarity

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

# ── 环境变量 ────────────────────────────────────────────
ENV_BASE_URL = os.environ.get("DEBATE_BASE_URL", "").strip()
ENV_API_KEY = os.environ.get("DEBATE_API_KEY", "").strip()

# ── Debug 日志 ───────────────────────────────────────────

_DEBUG_MAX_BYTES = 10 * 1024 * 1024   # 10 MB 之后开始裁头
_DEBUG_TRIM_TO   =  5 * 1024 * 1024   # 裁到约 5 MB


class DebugLogger:
    """Debug 输出器：控制台（stderr）或单文件（轮转，10MB 限制）。"""

    def __init__(self, path: "Path | None"):
        self._path = path   # None = stderr
        self._lock = threading.Lock()

    def log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[DEBUG {ts}] {msg}\n"
        if self._path is None:
            print(line, end="", file=sys.stderr)
        else:
            with self._lock:
                with open(self._path, "ab") as f:
                    f.write(line.encode("utf-8", errors="replace"))
                if self._path.stat().st_size > _DEBUG_MAX_BYTES:
                    self._trim()

    def _trim(self) -> None:
        """Discard leading bytes so the file drops to ~5 MB."""
        try:
            data = self._path.read_bytes()
            cut = data.find(b"\n", _DEBUG_TRIM_TO)
            self._path.write_bytes(data[cut + 1:] if cut >= 0 else data[_DEBUG_TRIM_TO:])
        except Exception:
            pass


_debug_logger: "DebugLogger | None" = None


def init_debug_logging(target) -> None:
    """target: None=关闭,  True=stderr,  str/Path=输出到文件"""
    global _debug_logger
    if target is None:
        _debug_logger = None
    elif target is True:
        _debug_logger = DebugLogger(None)
    else:
        _debug_logger = DebugLogger(Path(target))


def dlog(msg: str) -> None:
    """Write a debug message (no-op when debug logging is disabled)."""
    if _debug_logger is not None:
        _debug_logger.log(msg)


LOG_FORMAT = "debate-tool-log"
LOG_VERSION = 1
LOG_FILE_SUFFIX = "_debate_log.json"
SUMMARY_FILE_SUFFIX = "_debate_summary.md"


class LogFormatError(ValueError):
    """Raised when a JSON log file does not match the expected schema."""


def build_log_path(topic_path: Path) -> Path:
    return topic_path.parent / f"{topic_path.stem}{LOG_FILE_SUFFIX}"


# ── YAML Front-matter 解析 ───────────────────────────────


def _parse_early_stop(val) -> float:
    """Parse early_stop: False → 0, True → default threshold, float → that value."""
    if val is False or val is None or val == 0:
        return 0.0
    if val is True:
        return DEFAULT_EARLY_STOP_THRESHOLD
    try:
        f = float(val)
    except (TypeError, ValueError):
        return 0.0
    if not (0 < f < 1):
        return 0.0
    return f


def _parse_cot(val) -> int | None:
    """Parse cot YAML field.

    cot: false / null / 0  → None (disabled)
    cot: true              → 0   (enabled, no token limit)
    cot: 2000              → 2000 (enabled, 2000-token thinking budget)
    """
    if val is False or val is None or val == 0:
        return None
    if val is True:
        return 0
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_debaters(raw_debaters) -> list[dict]:
    if not isinstance(raw_debaters, list):
        raw_debaters = DEFAULT_DEBATERS

    debaters: list[dict] = []
    for item in raw_debaters:
        if not isinstance(item, dict):
            continue
        debaters.append(
            {
                **item,
                "base_url": _expand_env(str(item.get("base_url", "") or "")),
                "api_key": _expand_env(str(item.get("api_key", "") or "")),
            }
        )

    return debaters or [
        {
            **d,
            "base_url": _expand_env(str(d.get("base_url", "") or "")),
            "api_key": _expand_env(str(d.get("api_key", "") or "")),
        }
        for d in DEFAULT_DEBATERS
    ]


def _normalize_judge(raw_judge) -> dict:
    if not isinstance(raw_judge, dict):
        raw_judge = {}
    return {
        **DEFAULT_JUDGE,
        **{
            k: (_expand_env(str(v)) if k in ("base_url", "api_key") else v)
            for k, v in raw_judge.items()
        },
    }


def _expand_env(value: str) -> str:
    import re as _re_env
    def _replace(m: "_re_env.Match") -> str:
        var = m.group(1) or m.group(2) or ""
        return os.environ.get(var, m.group(0) or "") or ""
    return _re_env.sub(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)", _replace, value)


def parse_topic_file(path: Path) -> dict:
    """解析 Markdown 文件的 YAML front-matter + body。"""
    text = path.read_text(encoding="utf-8")

    # 分离 front-matter 和 body
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                front = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                front = {}
            if not isinstance(front, dict):
                front = {}
            body = parts[2].strip()
        else:
            front, body = {}, text
    else:
        front, body = {}, text

    # 组装配置（带默认值）
    cfg = {
        "title": str(front.get("title", path.stem) or path.stem),
        "rounds": _coerce_int(front.get("rounds", 3), 3),
        "timeout": _coerce_int(front.get("timeout", 300), 300),
        "max_reply_tokens": _coerce_int(
            front.get("max_reply_tokens") or front.get("max_tokens", 6000),
            6000,
        ),
        "debaters": _normalize_debaters(front.get("debaters", DEFAULT_DEBATERS)),
        "judge": _normalize_judge(front.get("judge", {})),
        "constraints": str(front.get("constraints", "") or "").strip(),
        "round1_task": str(front.get(
            "round1_task", "针对各议题给出立场和建议，每个 200-300 字"
        ) or "").strip(),
        "middle_task": str(front.get(
            "middle_task", "回应其他辩手观点，深化立场，400-600 字"
        ) or "").strip(),
        "middle_task_optional": bool(front.get("middle_task_optional", False)),
        "final_task": str(front.get(
            "final_task", "最终轮，给出最终建议，标注优先级，300-500 字"
        ) or "").strip(),
        "judge_instructions": str(front.get("judge_instructions", "") or "").strip(),
        "topic_body": body,
        # API 配置：front-matter > 环境变量（支持 ${VAR} 占位符展开）
        "base_url": _expand_env(str(front.get("base_url", "") or "").strip()),
        "api_key": _expand_env(str(front.get("api_key", "") or "").strip()),
        # Mode fields
        "cross_exam": _coerce_int(front.get("cross_exam", 0), 0),
        "early_stop": _parse_early_stop(front.get("early_stop", False)),
        "cot_length": _parse_cot(front.get("cot", None)),
    }
    # 透传所有未明确提取的 front-matter 字段（供 compact 等扩展配置使用）
    for k, v in front.items():
        if k not in cfg:
            cfg[k] = _expand_env(str(v).strip()) if isinstance(v, str) else v
    return cfg


def _validate_log_entries(entries: object, path: Path) -> list[dict]:
    if not isinstance(entries, list):
        raise LogFormatError(f"{path} 的 entries 字段必须是数组")

    normalized: list[dict] = []
    for idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise LogFormatError(f"{path} 的 entries[{idx}] 必须是对象")

        seq = entry.get("seq")
        ts = entry.get("ts")
        tag = entry.get("tag", "")
        name = entry.get("name")
        content = entry.get("content")

        if not isinstance(seq, int) or seq != idx:
            raise LogFormatError(f"{path} 的 entries[{idx}] seq 非法，必须从 1 连续递增")
        if not isinstance(ts, str) or not ts.strip():
            raise LogFormatError(f"{path} 的 entries[{idx}] ts 非法")
        if not isinstance(tag, str):
            raise LogFormatError(f"{path} 的 entries[{idx}] tag 非法")
        if not isinstance(name, str) or not name.strip():
            raise LogFormatError(f"{path} 的 entries[{idx}] name 非法")
        if not isinstance(content, str):
            raise LogFormatError(f"{path} 的 entries[{idx}] content 非法")

        e_normalized = {
            "seq": seq,
            "ts": ts,
            "tag": tag,
            "name": name,
            "content": content,
        }
        # 保留额外字段（如 compact_checkpoint 的 state）
        for k, v in entry.items():
            if k not in e_normalized:
                e_normalized[k] = v
        normalized.append(e_normalized)

    return normalized


def _load_json_log_payload(path: Path) -> tuple[dict, list[dict]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LogFormatError(f"{path} 不是合法 JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LogFormatError(f"{path} 顶层必须是对象")
    if payload.get("format") != LOG_FORMAT:
        raise LogFormatError(
            f"{path} format 非法，期望 {LOG_FORMAT!r}，实际 {payload.get('format')!r}"
        )
    if payload.get("version") != LOG_VERSION:
        raise LogFormatError(
            f"{path} version 非法，期望 {LOG_VERSION}，实际 {payload.get('version')!r}"
        )

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise LogFormatError(f"{path} title 非法")

    entries = _validate_log_entries(payload.get("entries"), path)
    if not entries:
        raise LogFormatError(f"{path} entries 不能为空")
    return payload, entries


def _classify_file(path: Path):
    """识别文件是否为 JSON 日志。

    返回:
      ("log", log_obj)       — 成功 load 为 Log
      ("non_log", log_err)   — 文件存在但不是合法 JSON 日志
    """
    if not path.exists():
        return ("missing", FileNotFoundError(f"{path} 不存在"))
    try:
        log = Log.load_from_file(path)
        return ("log", log)
    except Exception as e:
        return ("non_log", e)


def identify_files(file_a: Path, file_b: Path) -> "tuple[Path, Path]":
    """识别两个文件中的 JSON 日志文件，返回 (log_path, topic_path)。

    规则：必须恰好有一个合法 JSON 日志文件；另一个文件只要存在即可视为 topic。
    """
    for path in (file_a, file_b):
        if not path.exists():
            print(f"❌ 文件不存在: {path}", file=sys.stderr)
            sys.exit(1)

    ra = _classify_file(file_a)
    rb = _classify_file(file_b)

    logs = [(p, r) for p, r in ((file_a, ra), (file_b, rb)) if r[0] == "log"]

    if len(logs) == 2:
        print("❌ 传入了两个日志文件，请提供一个日志文件和一个议题文件。", file=sys.stderr)
        sys.exit(1)

    if len(logs) == 0:
        _, err_a = ra
        _, err_b = rb
        print(
            "❌ 没有检测到合法的 JSON 日志文件，请提供一个 *_debate_log.json 日志文件和一个议题文件。\n"
            f"   {file_a}: {err_a}\n"
            f"   {file_b}: {err_b}",
            file=sys.stderr,
        )
        sys.exit(1)
        sys.exit(1)
    log_path = logs[0][0]
    topic_path = file_b if log_path == file_a else file_a
    print(f"  识别结果: log={log_path.name}  topic={topic_path.name}")
    return log_path, topic_path
    sys.exit(1)


# ── LLM 调用 ─────────────────────────────────────────────

import re as _re

_TOKEN_LIMIT_PATTERNS = [
    _re.compile(r"maximum context length is (\d+)", _re.I),
    _re.compile(r"max_tokens.*?(\d+)", _re.I),
    _re.compile(r"context_length_exceeded.*?(\d+)", _re.I),
    _re.compile(r"this model's maximum context length is (\d+)", _re.I),
    _re.compile(r"tokens? (?:in|exceeds?) .*?(\d+)", _re.I),
    _re.compile(r"(\d+)\s*tokens", _re.I),
]


class TokenLimitError(Exception):
    def __init__(self, model: str, model_max_tokens: int, raw: str):
        self.model = model
        self.model_max_tokens = model_max_tokens
        self.raw = raw
        super().__init__(f"Token limit: {model_max_tokens} for {model}")


def _parse_token_limit(text: str) -> int | None:
    for pat in _TOKEN_LIMIT_PATTERNS:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def _is_token_limit_error(status: int, body: str) -> bool:
    if status == 400:
        low = body.lower()
        return any(
            k in low
            for k in (
                "context_length_exceeded",
                "maximum context length",
                "max_tokens",
                "tokens",
                "context length",
            )
        )
    return False


def _preview_debug_text(text: str, limit: int = 500) -> str:
    text = text or ""
    return text[:limit] + ("..." if len(text) > limit else "")


def _stringify_response_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "output_text" and isinstance(
                    item.get("text"), str
                ):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "".join(parts)
    return ""


def _extract_response_text(data: dict) -> tuple[str, str | None]:
    """Extract text from several OpenAI-compatible response variants.

    Returns (content, finish_reason).
    """
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] or {}
        finish_reason = choice.get("finish_reason")
        message = choice.get("message") or {}
        if "content" in message:
            content = _stringify_response_content(message.get("content"))
            return content, finish_reason
        if isinstance(choice.get("text"), str):
            return choice["text"], finish_reason

    if isinstance(data.get("output_text"), str):
        return data["output_text"], None

    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                if isinstance(content_item, dict) and isinstance(
                    content_item.get("text"), str
                ):
                    parts.append(content_item["text"])
        if parts:
            return "".join(parts), None

    return "", None


async def call_llm(
    model: str,
    system: str,
    user_content: str,
    *,
    temperature: float = 0.7,
    max_reply_tokens: int = 6000,
    timeout: int = 300,
    base_url: str = "",
    api_key: str = "",
) -> str:
    """调用 LLM API，支持按角色覆盖 base_url/api_key。"""
    url = base_url or ENV_BASE_URL
    key = api_key or ENV_API_KEY
    if not url:
        return "[调用失败: 未配置 API Base URL，请设置 DEBATE_BASE_URL 或在 front-matter 提供 base_url]"
    if not key:
        return "[调用失败: 未配置 API Key，请设置 DEBATE_API_KEY 或在 front-matter 提供 api_key]"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_reply_tokens,
    }
    dlog(
        f"LLM 请求  model={model}  url={url}  max_tokens={max_reply_tokens}\n"
        f"  [system] {system}\n"
        f"  [user]   {user_content}"
    )
    async with httpx.AsyncClient(timeout=timeout) as c:
        for attempt in range(3):
            try:
                request_max_tokens = max_reply_tokens
                if attempt > 0:
                    request_max_tokens = min(max(max_reply_tokens * (2**attempt), 600), 12000)
                request_payload = dict(payload)
                request_payload["max_tokens"] = request_max_tokens
                r = await c.post(
                    url.rstrip("/"),
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )
                body_text = r.text
                dlog(
                    f"LLM 原始响应  model={model}  status={r.status_code}\n"
                    f"  {body_text}"
                )
                if _is_token_limit_error(r.status_code, body_text):
                    limit = _parse_token_limit(body_text) or 0
                    raise TokenLimitError(model, limit, body_text)
                r.raise_for_status()
                data = r.json()
                content, finish_reason = _extract_response_text(data)
                if finish_reason == "length" and not content.strip() and attempt < 2:
                    dlog(
                        f"LLM 空截断响应  model={model}  attempt={attempt}  retry_with_max_tokens={min(max(max_reply_tokens * (2 ** (attempt + 1)), 600), 12000)}"
                    )
                    continue
                if finish_reason == "length":
                    content += "\n\n[WARNING: output was truncated due to max_tokens limit]"
                dlog(
                    f"LLM 响应  model={model}  finish={finish_reason}\n"
                    f"  {content[:300]}{'...' if len(content) > 300 else ''}"
                )
                return content
            except TokenLimitError:
                raise
            except Exception as e:
                dlog(f"LLM 错误  model={model}  attempt={attempt}  err={e}")
                if attempt == 2:
                    return f"[调用失败: {e}]"
                print(f"  ⚠️ {model} retry {attempt + 1}: {e}", file=sys.stderr)
                await asyncio.sleep(2**attempt)
    return "[调用失败]"


# ── Token 超限时的分段 compact 重试 ─────────────────────

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


def _strip_json_fence(text: str) -> str:
    """剥离 LLM 返回的 JSON 前后 markdown 代码块标记。"""
    return (
        text.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )


async def _fallback_form_filling(
    debater: dict,
    initial_style: str,
    prev_participant: "dict | None",
    delta_entries: "list[dict]",
    base_url: str,
    api_key: str,
) -> "dict | None":
    """
    JSON 解析三次全失败后的渐进式降级策略。

    Level 1: 填表模式（纯文本格式，不用 JSON）
    Level 2: 逐字段问（先 stance，再逐个 claim 问状态）
    Level 3: 选择题模式（对每个 claim 问 A/B 选择）
    Level 4: 完全保留上次状态

    返回 ParticipantState dict，或 None（让外层用 fallback）
    """
    from .compact_state import format_delta_entries_text

    name = debater.get("name", "未知辩手")

    # ── Level 1: 填表模式 ────────────────────────────────────
    try:
        form_prompt = f"""你是辩手「{name}」。JSON 格式解析失败，改用填表模式。

请按以下格式输出（纯文本，不要 JSON）：

STANCE:
<你的立场笔记，多行文本，200字以内>

CORE_CLAIMS:
A1 | <主张文本> | active
A2 | <主张文本> | abandoned

KEY_ARGUMENTS:
A1-arg1 | A1 | <论据文本> | active

辩论增量记录：
{format_delta_entries_text(delta_entries)[:1000]}
"""
        form_resp = await call_llm(
            debater["model"], "", form_prompt,
            base_url=base_url, api_key=api_key, max_reply_tokens=2000
        )
        parsed = _parse_form_output(form_resp, name, prev_participant)
        if parsed and validate_participant_state(parsed):
            print(f"  ✅ {name} 填表模式成功", file=sys.stderr)
            return parsed
    except Exception as e:
        print(f"  ⚠️ {name} 填表模式失败: {e}", file=sys.stderr)

    # ── Level 2: 逐字段问 ────────────────────────────────────
    try:
        stance_resp = await call_llm(
            debater["model"], "",
            f"你是 {name}。用一段话总结你当前的立场（200字以内）：\n\n辩论增量：{format_delta_entries_text(delta_entries)[:800]}",
            base_url=base_url, api_key=api_key, max_reply_tokens=300
        )
        stance = stance_resp.strip()

        claims = []
        if prev_participant and prev_participant.get("core_claims"):
            for c in prev_participant["core_claims"]:
                status_resp = await call_llm(
                    debater["model"], "",
                    f"主张 {c['id']}: {c['text']}\n当前状态？回答 active/modified/abandoned 之一：",
                    base_url=base_url, api_key=api_key, max_reply_tokens=10
                )
                status = status_resp.strip().lower()
                if status in ["active", "modified", "abandoned"]:
                    claims.append({**c, "status": status})
                else:
                    claims.append(c)

        result = {
            "name": name,
            "stance_version": (prev_participant.get("stance_version", 0) + 1) if prev_participant else 1,
            "stance": stance,
            "core_claims": claims,
            "key_arguments": prev_participant.get("key_arguments", []) if prev_participant else [],
            "abandoned_claims": prev_participant.get("abandoned_claims", []) if prev_participant else [],
        }
        if validate_participant_state(result):
            print(f"  ✅ {name} 逐字段模式成功", file=sys.stderr)
            return result
    except Exception as e:
        print(f"  ⚠️ {name} 逐字段模式失败: {e}", file=sys.stderr)

    # ── Level 3: 选择题模式 ────────────────────────────────────
    try:
        if prev_participant and prev_participant.get("core_claims"):
            claims = []
            for c in prev_participant["core_claims"]:
                choice_resp = await call_llm(
                    debater["model"], "",
                    f"主张: {c['text']}\n选择：A) 仍然有效  B) 已放弃\n回答 A 或 B：",
                    base_url=base_url, api_key=api_key, max_reply_tokens=5
                )
                if "B" in choice_resp.upper():
                    claims.append({**c, "status": "abandoned"})
                else:
                    claims.append(c)

            result = {
                "name": name,
                "stance_version": prev_participant.get("stance_version", 0) + 1,
                "stance": prev_participant.get("stance", initial_style),
                "core_claims": claims,
                "key_arguments": prev_participant.get("key_arguments", []),
                "abandoned_claims": prev_participant.get("abandoned_claims", []),
            }
            if validate_participant_state(result):
                print(f"  ✅ {name} 选择题模式成功", file=sys.stderr)
                return result
    except Exception as e:
        print(f"  ⚠️ {name} 选择题模式失败: {e}", file=sys.stderr)

    # ── Level 4: 完全保留上次 ────────────────────────────────────
    if prev_participant:
        print(f"  ⚠️ {name} 所有降级模式失败，保留上次状态", file=sys.stderr)
        return {
            **prev_participant,
            "stance_version": prev_participant.get("stance_version", 0) + 1
        }

    return None


def _parse_form_output(text: str, name: str, prev_participant: "dict | None") -> "dict | None":
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
                        "status": parts[3]
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
    fallback_result = await _fallback_form_filling(
        debater, initial_style, prev_participant, delta_entries,
        debater_base_url, debater_api_key
    )
    if fallback_result:
        return fallback_result

    return fallback


async def _do_compact(log: "Log", cfg: dict, system_text: str) -> "tuple[str, int]":
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
        exclude_tags=("thinking", "summary", "compact_checkpoint"),
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


# ── CoT 辅助 ──────────────────────────────────────────────

import re as _re_cot

_THINKING_RE = _re_cot.compile(r"<thinking>(.*?)</thinking>", _re_cot.DOTALL)


def _split_cot_response(response: str) -> tuple[str, str]:
    """Split a COT response into (thinking_content, actual_reply).

    If <thinking>...</thinking> tags are present, extract the thinking block and
    treat everything after </thinking> as the actual reply (leading whitespace
    stripped).  If no tags are found, return ("", response) as a fallback.
    """
    m = _THINKING_RE.search(response)
    if m:
        thinking = m.group(1).strip()
        after = response[m.end():].lstrip()
        return thinking, after
    # Fallback: no tags found — treat entire response as reply
    return "", response


# ── 日志 ──────────────────────────────────────────────────


class Log:
    def __init__(self, path: Path, title: str):
        self.path = path
        self.title = title
        self.entries: list[dict] = []
        self._archived_entries: list[dict] = []

    def _all_entries(self) -> list[dict]:
        return [*self._archived_entries, *self.entries]

    def _next_seq(self) -> int:
        all_entries = self._all_entries()
        return (all_entries[-1]["seq"] + 1) if all_entries else 1

    @classmethod
    def load_from_file(cls, path: Path) -> "Log":
        payload, all_entries = _load_json_log_payload(path)

        # Find last checkpoint — only load from there onward
        last_checkpoint_idx = -1
        for idx, e in enumerate(all_entries):
            if e["tag"] == "compact_checkpoint":
                last_checkpoint_idx = idx

        log = cls(path, payload["title"])
        if last_checkpoint_idx >= 0:
            log._archived_entries = all_entries[:last_checkpoint_idx]
            log.entries = all_entries[last_checkpoint_idx:]
            print(
                f"  📦 从 checkpoint #{all_entries[last_checkpoint_idx]['seq']} 恢复，跳过 {last_checkpoint_idx} 条旧记录"
            )
        else:
            log.entries = all_entries

        return log

    def add(self, name: str, content: str, tag: str = "", flush: bool = True, extra: "dict | None" = None):
        e = {
            "seq": self._next_seq(),
            "ts": datetime.now().isoformat(),
            "tag": tag,
            "name": name,
            "content": content,
        }
        if extra:
            e.update(extra)
        self.entries.append(e)
        icon = {
            "summary": "⚖️ 裁判",
            "cross_exam": "🔍",
            "compact_checkpoint": "📦",
            "meta": "📝",
            "thinking": "🧠",
        }.get(tag, "💬")
        print(f"\n{'=' * 60}\n[{e['seq']}] {icon} {name}\n{'=' * 60}")
        t = content
        print(t[:800] + "\n...(见日志)" if len(t) > 800 else t)
        if flush:
            self._flush()

    def _flush(self):
        all_entries = self._all_entries()
        payload = {
            "format": LOG_FORMAT,
            "version": LOG_VERSION,
            "title": self.title,
            "created_at": all_entries[0]["ts"] if all_entries else datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "entries": all_entries,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def since(self, after_seq: int) -> str:
        # "thinking": CoT 内部过程不暴露给其他辩手
        # "summary": 裁判最终裁定不应反向影响辩手后续发言（含续跑场景）
        news = [
            e for e in self.entries
            if e["seq"] > after_seq and e.get("tag") not in ("thinking", "summary")
        ]
        if not news:
            return "(无新内容)"
        return "\n\n".join(f"--- {e['name']} ---\n{e['content']}" for e in news)

    def compact(self) -> str:
        parts = []
        for e in self.entries:
            tag = f"[{e['tag'].upper()}] " if e["tag"] else ""
            if e.get("tag") == "compact_checkpoint":
                state = e.get("state") or parse_compact_checkpoint(e["content"]).get("state")
                t = render_public_markdown(state)[:1200] if state else e.get("content", "")[:1200]
            else:
                t = e["content"][:1200]
                if len(e["content"]) > 1200:
                    t += "...(截断)"
            parts.append(f"### [{e['seq']}] {tag}{e['name']}\n{t}")
        return "\n\n".join(parts)

    def get_last_compact_state(self) -> "dict | None":
        """倒序遍历 entries，找到最后一个 compact_checkpoint，解析并返回其 state。"""
        for e in reversed(self.entries):
            if e.get("tag") == "compact_checkpoint":
                state = e.get("state")
                if state is not None:
                    return state
                # 旧格式兼容：content 是 JSON 字符串
                parsed = parse_compact_checkpoint(e["content"])
                return parsed.get("state")
        return None

    def entries_since_seq(
        self, after_seq: int, exclude_tags: tuple = ("thinking",)
    ) -> "list[dict]":
        """返回 seq > after_seq 且 tag 不在 exclude_tags 的条目列表。"""
        return [
            e for e in self._all_entries()
            if e["seq"] > after_seq and e.get("tag") not in exclude_tags
        ]


# ── 质询子回合 ────────────────────────────────────────────


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
            return questioner, None, True

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
    text = candidate.strip().strip(" \t\n\r\"'`“”‘’[]()（）【】《》<>,，。；;：:")
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


# ── 主流程 ────────────────────────────────────────────────


async def run(cfg: dict, topic_path: Path, *, cot_length: int | None = None, log_path: Path | None = None):
    stem = topic_path.stem
    out_dir = topic_path.parent

    if log_path is None:
        log_path = build_log_path(topic_path)
    log = Log(log_path, cfg["title"])
    topic = cfg["topic_body"]
    debaters = cfg["debaters"]
    judge = cfg["judge"]
    rounds = cfg["rounds"]
    timeout = cfg["timeout"]
    max_reply_tokens = cfg["max_reply_tokens"]
    constraints = cfg["constraints"]
    cross_exam = cfg.get("cross_exam", 0)  # number of rounds with cross-exam
    early_stop = cfg.get("early_stop", 0.0)  # 0=off, (0,1)=threshold
    # COT: CLI > YAML > None (disabled)
    if cot_length is None:
        cot_length = cfg.get("cot_length", None)
    # Per-debate API config
    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()

    # cross_exam == -1 means every round (except last)
    if cross_exam < 0:
        cross_exam_rounds = set(range(1, rounds))  # all except final
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

        # ── Phase A: 并行辩手发言 ──
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
                # Determine per-debater task_desc based on whether challenged last round
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
                # 改动 6：若 log 中存在 compact_checkpoint，注入辩手立场到 sys_prompt
                last_state = log.get_last_compact_state()
                if last_state and last_state.get("participants"):
                    participant = next(
                        (p for p in last_state["participants"] if p["name"] == d["name"]),
                        None,
                    )
                    if participant:
                        stance_injection = render_stance_for_system(participant)
                        sys_prompt = (
                            sys_prompt
                            + "\n\n"
                            + stance_injection
                            + "\n\n你收到的是辩论状态快照。「已否决路径」不得以任何变体重新提出。"
                            "你的立场描述已更新为上述「当前辩论立场」，以此为准，忽略初始立场中关于观点的陈述。"
                        )
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
                # 改动 6：若有 compact_checkpoint，user_ctx 使用 public_view + delta
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
                    d["model"],
                    sys_prompt,
                    effective_ctx,
                    max_reply_tokens=call_max_tokens,
                    timeout=timeout,
                    base_url=debater_base_url,
                    api_key=debater_api_key,
                )
                if cot_length is not None:
                    thinking, reply = _split_cot_response(raw)
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
            raise RuntimeError(
                f"第 {rnd} 轮经过多次 compact 仍无法完成，请手动压缩日志"
            )
        for d, (thinking, reply) in zip(debaters, raw_results):
            if thinking:
                log.add(d["name"], thinking, "thinking", flush=False)
            log.add(d["name"], reply, flush=False)
            replies.append(reply)
        log._flush()  # 一次性写入
        last_seq = mark

        # ── Phase B: 早停检查 ──
        if early_stop and rnd < rounds:
            converged, avg_sim = check_convergence(replies, early_stop)
            print(f"\n  📊 收敛检查: 平均相似度 {avg_sim:.1%} (阈值 {early_stop:.0%})")
            if converged:
                print("  ⚡ 观点已收敛，跳过剩余轮次，直接进入裁判阶段")
                break

        # ── 改动 5：轮结束后主动 compact 检查 ──
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

        # ── Phase C: 质询（若当前轮在 cross_exam_rounds 中且非最后一轮） ──
        if rnd in cross_exam_rounds and rnd < rounds:
            print(f"\n\n🔍 质询环节 (R{rnd}.5)\n")
            challenged_set = await run_cross_exam(
                debaters,
                log,
                topic,
                rnd,
                max_reply_tokens=max_reply_tokens,
                timeout=timeout,
                debate_base_url=debate_base_url,
                debate_api_key=debate_api_key,
            )
            challenged_last = challenged_set
        else:
            challenged_last = None

    # ══════════════════════════════════════════════════
    #  裁判总结
    # ══════════════════════════════════════════════════
    print("\n\n⚖️ 裁判总结\n")

    # 默认裁判指令
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
        judge["model"],
        judge_sys,
        f"全部辩论（压缩版）：\n\n{log.compact()}",
        temperature=0.3,
        max_reply_tokens=judge_max_tokens,
        timeout=timeout,
        base_url=judge_base_url,
        api_key=judge_api_key,
    )
    log.add(judge["name"], summary, "summary")

    sp = out_dir / f"{stem}{SUMMARY_FILE_SUFFIX}"
    sp.write_text(
        f"# {cfg['title']} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}",
        encoding="utf-8",
    )

    print(f"\n✅ 完成！ 日志: {log.path} | 总结: {sp}")


# ── 续跑（resume） ───────────────────────────────────────


async def resume(
    cfg: dict,
    topic_path: Path,
    *,
    log_path: "Path | None" = None,
    message: str = "",
    extra_rounds: int = 1,
    cross_exam: int = 0,
    guide_prompt: str = "",
    judge_at_end: bool = True,
    force: bool = False,
    cot_length: int | None = None,
) -> None:
    stem = topic_path.stem
    out_dir = topic_path.parent
    if log_path is None:
        log_path = build_log_path(topic_path)

    if not log_path.exists():
        print(f"❌ 日志文件不存在: {log_path}", file=sys.stderr)
        print("请先运行 debate-tool run 进行首次辩论", file=sys.stderr)
        sys.exit(1)

    log = Log.load_from_file(log_path)
    print(f"📂 已加载 {len(log.entries)} 条日志记录")

    await check_topic_log_consistency_with_llm(cfg, log, force=force)
    validate_topic_log_consistency(cfg, log, force=force)

    topic = cfg["topic_body"]
    debaters = cfg["debaters"]
    judge = cfg["judge"]
    timeout = cfg["timeout"]
    max_reply_tokens = cfg["max_reply_tokens"]
    constraints = cfg["constraints"]
    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()
    num_debaters = len(debaters)
    system_text = f"## 辩论议题\n\n{topic}"
    # COT: CLI > YAML > None (disabled)
    if cot_length is None:
        cot_length = cfg.get("cot_length", None)

    if message:
        log.add("👤 观察者", message, "human")
        print(f"\n💬 已注入观察者消息")

    base_round = len([e for e in log.entries if not e.get("tag")]) // max(
        num_debaters, 1
    )

    for r_offset in range(1, extra_rounds + 1):
        rnd = base_round + r_offset
        print(f"\n\n📢 续跑第 {rnd} 轮\n")

        new_log = log.since(0)

        if guide_prompt:
            task_desc = (
                f"回应其他辩手观点，深化立场。400-600 字\n\n观察者指引：{guide_prompt}"
            )
        elif message and r_offset == 1:
            task_desc = "请回应观察者提出的问题/意见，同时深化自己的立场。400-600 字"
        else:
            task_desc = cfg["middle_task"]

        constraints_block = f"\n\n核心约束：\n{constraints}" if constraints else ""

        async def speak(
            d,
            rnd=rnd,
            task_desc=task_desc,
            constraints_block=constraints_block,
            _new_log=None,
        ):
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
                sys_prompt = sys_prompt + "\n\n" + cot_note
                call_max_tokens = (
                    (cot_length + max_reply_tokens) if cot_length > 0
                    else (max_reply_tokens + 2000)
                )
            else:
                call_max_tokens = max_reply_tokens
            ctx = f"{system_text}\n\n## 辩论历史\n\n{_new_log or new_log}"
            raw = await call_llm(
                d["model"],
                sys_prompt,
                ctx,
                max_reply_tokens=call_max_tokens,
                timeout=timeout,
                base_url=debater_base_url,
                api_key=debater_api_key,
            )
            if cot_length is not None:
                thinking, reply = _split_cot_response(raw)
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
                compact_text = _compact_for_retry(
                    log.entries, e.model_max_tokens, num_debaters, system_text
                )
                log.add("Compact Checkpoint", compact_text, "compact_checkpoint")
                new_log = compact_text

                async def speak_retry(
                    d,
                    rnd=rnd,
                    task_desc=task_desc,
                    constraints_block=constraints_block,
                    _nl=compact_text,
                ):
                    debater_base_url = (
                        d.get("base_url", "") or debate_base_url
                    ).strip()
                    debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
                    sys_prompt = (
                        f"你是「{d['name']}」，风格为「{d['style']}」。第 {rnd} 轮（续跑）。\n\n"
                        f"任务：{task_desc}{constraints_block}"
                    )
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
                    ctx = f"{system_text}\n\n## 辩论历史\n\n{_nl}"
                    raw = await call_llm(
                        d["model"],
                        sys_prompt,
                        ctx,
                        max_reply_tokens=call_max_tokens,
                        timeout=timeout,
                        base_url=debater_base_url,
                        api_key=debater_api_key,
                    )
                    if cot_length is not None:
                        thinking, reply = _split_cot_response(raw)
                    else:
                        thinking, reply = "", raw
                    return thinking, reply

                try:
                    raw_results = await asyncio.gather(*[speak_retry(d) for d in debaters])
                    break
                except TokenLimitError as e2:
                    print(
                        f"  ⚠️ compact 后仍超限 (attempt {compact_attempt + 1})，继续缩...",
                        file=sys.stderr,
                    )
                    compact_text = _compact_for_retry(
                        log.entries, e2.model_max_tokens, num_debaters, system_text
                    )
                    log.add("Compact Checkpoint", compact_text, "compact_checkpoint")
                    new_log = compact_text
        else:
            raise RuntimeError(
                f"第 {rnd} 轮经过多次 compact 仍无法完成，请手动压缩日志"
            )

        for d, (thinking, reply) in zip(debaters, raw_results):
            if thinking:
                log.add(d["name"], thinking, "thinking", flush=False)
            log.add(d["name"], reply, flush=False)
        log._flush()  # 一次性写入

        do_cross_exam = (
            cross_exam != 0
            and (cross_exam < 0 or r_offset <= cross_exam)
            and r_offset < extra_rounds
        )
        if do_cross_exam:
            print(f"\n\n🔍 质询环节 (续跑 R{rnd}.5)\n")
            await run_cross_exam(
                debaters,
                log,
                topic,
                rnd,
                max_reply_tokens=max_reply_tokens,
                timeout=timeout,
                debate_base_url=debate_base_url,
                debate_api_key=debate_api_key,
            )  # resume 中不使用返回的 challenged_set，无需处理

    if judge_at_end:
        print("\n\n⚖️ 裁判总结\n")
        judge_instructions = cfg.get("judge_instructions", "")
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
        judge_ctx = log.since(0)

        for _ in range(5):
            try:
                summary = await call_llm(
                    judge["model"],
                    judge_sys,
                    f"全部辩论（含续跑）：\n\n{judge_ctx}",
                    temperature=0.3,
                    max_reply_tokens=judge_max_tokens,
                    timeout=timeout,
                    base_url=judge_base_url,
                    api_key=judge_api_key,
                )
                break
            except TokenLimitError as e:
                print(
                    f"\n  📦 裁判 token 超限 (max={e.model_max_tokens})，compact 后重试...",
                    file=sys.stderr,
                )
                judge_ctx = _compact_for_retry(
                    log.entries, e.model_max_tokens, num_debaters, ""
                )
        else:
            summary = "[裁判总结失败：多次 compact 后仍超限]"
        log.add(judge["name"], summary, "summary")

        sp = out_dir / f"{stem}{SUMMARY_FILE_SUFFIX}"
        sp.write_text(
            f"# {cfg['title']} 裁判总结\n\n> {datetime.now().isoformat()}\n\n{summary}",
            encoding="utf-8",
        )

    print(f"\n✅ 续跑完成！ 日志: {log.path}")


# ── 手动压缩 ─────────────────────────────────────────────


def compact_log(
    log_path: Path,
    *,
    keep_last: int = 0,        # 向后兼容，新版不使用
    token_budget: int = 60000,  # 向后兼容
    topic_path: "Path | None" = None,
) -> None:
    if not log_path.exists():
        print(f"❌ 日志文件不存在: {log_path}", file=sys.stderr)
        sys.exit(1)

    # 解析 topic 文件以获取 cfg（含 compact_model 等配置）
    resolved_topic_path: "Path | None" = topic_path

    if resolved_topic_path is None:
        # 尝试在同目录寻找同名（去掉 _debate_log 后缀）的 .md 文件
        stem = log_path.stem
        if stem.endswith("_debate_log"):
            candidate_stem = stem[: -len("_debate_log")]
        else:
            candidate_stem = stem
        candidate = log_path.parent / f"{candidate_stem}.md"
        if candidate.exists():
            resolved_topic_path = candidate
            print(f"  自动发现 topic 文件: {resolved_topic_path}")

    if resolved_topic_path is None:
        print(
            "❌ 未找到对应的 topic 文件，请通过 --topic 参数指定。",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = parse_topic_file(resolved_topic_path)
    system_text = f"## 辩论议题\n\n{cfg['topic_body']}"

    log = Log.load_from_file(log_path)
    total = len(log.entries)
    print(f"📂 已加载 {total} 条日志记录")

    before_tokens = estimate_tokens("\n\n".join(e["content"] for e in log.entries))

    try:
        _compact_state, checkpoint_seq = asyncio.run(_do_compact(log, cfg, system_text))
    except ValueError as compact_err:
        print(
            f"\n  ❌ compact 配置缺失，无法压缩: {compact_err}",
            file=sys.stderr,
        )
        print(
            "  请在 topic YAML 中配置 compact_model / compact_check_model 后重试。",
            file=sys.stderr,
        )
        sys.exit(1)

    after_tokens = estimate_tokens(render_public_markdown(_compact_state))

    print(f"\n📦 压缩完成:")
    print(f"   Token: {before_tokens} → {after_tokens} (checkpoint)")
    print(f"   Checkpoint seq: {checkpoint_seq}")
    print(f"   日志: {log.path}")


def _mask_key(key: str) -> str:
    if len(key) <= 7:
        return "****"
    return key[:3] + "****" + key[-4:]


# ── modify 子命令 ─────────────────────────────────────────


def modify_topic(
    topic_path: Path,
    *,
    set_fields: list[str] | None = None,
    add_debaters: list[str] | None = None,
    drop_debaters: list[str] | None = None,
    pivot_stances: list[str] | None = None,
    reason: str = "",
    force: bool = False,
) -> None:
    """Modify topic file and append a @meta/modify event to the log.

    --set  debater.A.model=gpt-5        (or judge.model=claude, or rounds=5)
    --add  "C|gpt-5.2|激进派风格"        (name|model|style)
    --drop B
    --pivot "A|新的立场描述"             (name|new_style)
    --reason "why this change"
    """
    import yaml

    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    raw_text = topic_path.read_text(encoding="utf-8")
    # Split frontmatter
    parts = raw_text.split("---", 2)
    if len(parts) < 3:
        print("❌ topic 文件格式错误（缺少 YAML frontmatter）", file=sys.stderr)
        sys.exit(1)
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2]

    log_path = build_log_path(topic_path)
    log_exists = log_path.exists()

    if log_exists:
        log = Log.load_from_file(log_path)
        log_debater_names = {
            e["name"]
            for e in log.entries
            if e.get("tag")
            not in ("summary", "cross_exam", "compact_checkpoint", "human", "meta", "thinking")
        }
    else:
        log = None
        log_debater_names: set[str] = set()

    changes: list[str] = []

    # ── --set ──
    for field_expr in set_fields or []:
        if "=" not in field_expr:
            print(f"⚠️ --set 格式应为 key=value: {field_expr}", file=sys.stderr)
            continue
        key, val = field_expr.split("=", 1)
        parts_key = key.strip().split(".")

        if parts_key[0] == "judge":
            if len(parts_key) == 2:
                fm.setdefault("judge", {})
                if isinstance(fm["judge"], str):
                    fm["judge"] = {"name": fm["judge"]}
                old = fm["judge"].get(parts_key[1], "")
                fm["judge"][parts_key[1]] = val
                changes.append(f"set judge.{parts_key[1]}: {old!r} → {val!r}")
        elif parts_key[0] == "debater" and len(parts_key) >= 3:
            target_name = parts_key[1]
            attr = parts_key[2]
            debaters_list = fm.get("debaters", [])
            matched = next(
                (d for d in debaters_list if d.get("name") == target_name), None
            )
            if matched is None:
                matched = next(
                    (d for d in debaters_list if d.get("name", "").startswith(target_name)),
                    None,
                )
            if matched is None:
                matched = next(
                    (d for d in debaters_list if target_name in d.get("name", "")),
                    None,
                )
            if matched is not None:
                old = matched.get(attr, "")
                matched[attr] = val
                changes.append(
                    f"set debater.{matched['name']}.{attr}: {old!r} → {val!r}"
                )
            else:
                print(f"⚠️ 未找到辩手 {target_name}", file=sys.stderr)
        else:
            # Top-level field
            old = fm.get(parts_key[0], "")
            fm[parts_key[0]] = int(val) if val.isdigit() else val
            changes.append(f"set {parts_key[0]}: {old!r} → {val!r}")

    # ── --add ──
    for spec in add_debaters or []:
        parts_spec = spec.split("|", 2)
        if len(parts_spec) < 2:
            print(f"⚠️ --add 格式: name|model|style  got: {spec}", file=sys.stderr)
            continue
        name, model_ = parts_spec[0].strip(), parts_spec[1].strip()
        style = parts_spec[2].strip() if len(parts_spec) > 2 else "中立观察者"
        fm.setdefault("debaters", [])
        if any(d.get("name") == name for d in fm["debaters"]):
            print(f"⚠️ 辩手 {name} 已存在，跳过 --add", file=sys.stderr)
            continue
        fm["debaters"].append({"name": name, "model": model_, "style": style})
        changes.append(f"add debater: {name} ({model_})")

    # ── --drop ──
    for name in drop_debaters or []:
        before = len(fm.get("debaters", []))
        fm["debaters"] = [d for d in fm.get("debaters", []) if d.get("name") != name]
        if len(fm.get("debaters", [])) < before:
            changes.append(f"drop debater: {name}")
            if name in log_debater_names and not force:
                print(
                    f"⚠️ 辩手 {name} 在 log 中有历史条目。"
                    f"其历史将保留在 log 中（以 [INACTIVE] 标记）。"
                    f"使用 --force 跳过此提示。"
                )
        else:
            print(f"⚠️ 未找到辩手 {name}", file=sys.stderr)

    # ── --pivot ──
    for spec in pivot_stances or []:
        parts_spec = spec.split("|", 1)
        if len(parts_spec) < 2:
            print(f"⚠️ --pivot 格式: name|new_style  got: {spec}", file=sys.stderr)
            continue
        name, new_style = parts_spec[0].strip(), parts_spec[1].strip()
        for d in fm.get("debaters", []):
            if d.get("name") == name:
                old_style = d.get("style", "")
                d["style"] = new_style
                changes.append(
                    f"pivot debater.{name}.style: {old_style!r} → {new_style!r}"
                )
                break
        else:
            print(f"⚠️ --pivot: 未找到辩手 {name}", file=sys.stderr)

    if not changes:
        print("⚠️ 没有任何修改", file=sys.stderr)
        return

    # Write updated topic file
    updated_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False)
    topic_path.write_text(f"---\n{updated_fm}---{body}", encoding="utf-8")
    print(f"✅ topic 文件已更新: {topic_path}")
    for c in changes:
        print(f"   • {c}")

    # Append @meta/modify event to log
    if log is not None:
        ts = datetime.now().isoformat()
        change_lines = "\n".join(f"- {c}" for c in changes)
        reason_line = f"\n\n原因：{reason}" if reason else ""
        meta_content = (
            f"**@meta/modify** `{ts}`\n\n"
            f"变更列表：\n{change_lines}"
            f"{reason_line}\n\n"
            f"_注：历史日志条目不受影响，以下续跑使用新配置。_"
        )
        log.add("@meta/modify", meta_content, "meta")
        print(f"   • 已追加 @meta/modify 事件到 log: {log_path}")


async def check_topic_log_consistency_with_llm(
    cfg: dict,
    log: "Log",
    *,
    force: bool = False,
    model: str = "gpt-5-nano",
) -> None:
    """用 LLM 判断 topic 和 log 是否来自同一个话题，输出reasoning。
    
    如果不一致，报 Warning + LLM 的推理理由。使用 --force 可跳过此检查。
    如果指定模型不可用，自动 fallback 到第一辩手的模型。
    """
    topic = cfg.get("topic_body", "").strip()
    if not topic:
        return

    # Extract first few entries from log (look in archived first — handles post-compact case)
    relevant_entries = []
    all_source = list(getattr(log, "_archived_entries", [])) + list(log.entries)
    for e in all_source:
        tag = e.get("tag", "")
        # Skip non-debater content
        if tag in ("summary", "cross_exam", "compact_checkpoint", "meta", "human", "thinking"):
            continue
        content = e.get("content", "").strip()
        if content:
            relevant_entries.append(content)
        # Take at most first 2 actual debater entries
        if len(relevant_entries) >= 2:
            break

    if not relevant_entries:
        return

    log_excerpt = "\n\n---\n\n".join(relevant_entries[:2])

    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()

    system_prompt = (
        "你是一个辩论话题匹配专家。你的任务是判断给定的话题描述和辩论日志摘录是否来自同一个辩论话题。\n\n"
        "请输出二行：\n"
        "第一行：Is-Match: Yes 或 No\n"
        "第二行：Reasoning: [你的分析，解释为什么匹配或不匹配，2-3句话]\n\n"
        "示例输出：\n"
        "Is-Match: Yes\n"
        "Reasoning: 日志中讨论的是猫狗谁更好作为宠物，与话题完全一致。\n\n"
        "或：\n"
        "Is-Match: No\n"
        "Reasoning: 日志讨论的是AI安全风险，与话题中的猫狗对比不相关。"
    )
    
    user_prompt = (
        f"话题描述：\n{topic}\n\n"
        f"日志摘录（第一轮或开场发言）：\n{log_excerpt}\n\n"
        f"这些是来自同一个辩论话题吗？"
    )

    # Try specified model, fallback to debater[0]'s model if it fails
    models_to_try = [model]
    debaters = cfg.get("debaters", [])
    if debaters and debaters[0].get("model"):
        fallback_model = debaters[0]["model"]
        if fallback_model != model:
            models_to_try.append(fallback_model)

    reasoning = ""
    for try_model in models_to_try:
        try:
            dlog(f"🔍 [话题检查] 尝试模型: {try_model}")
            response = await call_llm(
                try_model,
                system_prompt,
                user_prompt,
                max_reply_tokens=300,
                timeout=30,
                base_url=debate_base_url,
                api_key=debate_api_key,
            )
            dlog(f"🔍 [话题检查] {try_model} 响应: {response[:120]}")

            # Check if response is valid (not just warnings/errors)
            if not response or "[WARNING:" in response or "[调用失败" in response or response.startswith("["):
                raise ValueError(f"Invalid response from {try_model}: {response[:100]}")

            # Parse response: look for Is-Match: Yes/No and Reasoning:
            is_consistent = None
            for line in response.split("\n"):
                line = line.strip()
                if line.lower().startswith("is-match:"):
                    is_consistent = "yes" in line.lower() and "no" not in line.lower()
                elif line.lower().startswith("reasoning:"):
                    reasoning = line[len("reasoning:"):].strip()

            # Fallback: simple check if no structured response
            if is_consistent is None:
                is_consistent = "yes" in response.lower() and "no" not in response.lower()

            if not is_consistent:
                msg_parts = [
                    "❌ 话题一致性检查失败：日志内容与话题文件不匹配。"
                ]
                if reasoning:
                    msg_parts.append(f"   判断理由：{reasoning}")
                msg_parts.append("   请确认你运行 resume 时使用了正确的 topic 文件。")
                msg_parts.append("   如要忽视此验证，请使用 --force 标志重试。")
                msg = "\n".join(msg_parts)

                if force:
                    print(f"⚠️ [force 忽略]\n{msg}", file=sys.stderr)
                else:
                    print(msg, file=sys.stderr)
                    sys.exit(1)
            else:
                print(f"✅ 话题一致性校验通过（使用模型: {try_model}）")

            return  # Success, exit function
        except Exception as e:
            if try_model == models_to_try[-1]:
                # Last model failed, just warn
                dlog(f"🔍 [话题检查] 所有模型均失败: {e}")
                print(
                    f"⚠️ 话题一致性校验出错（所有模型均失败），继续执行",
                    file=sys.stderr,
                )
            else:
                dlog(f"🔍 [话题检查] {try_model} 失败 ({type(e).__name__}: {str(e)[:80]})，尝试 fallback...")
            # else: continue to next model in loop


def validate_topic_log_consistency(
    cfg: dict, log: "Log", *, force: bool = False
) -> None:
    topic_names: set[str] = {d["name"] for d in cfg.get("debaters", [])}

    NON_DEBATER_TAGS = {
        "summary",
        "cross_exam",
        "compact_checkpoint",
        "meta",
        "human",
        "thinking",
    }
    log_speaker_names: set[str] = set()
    log_judge_names: set[str] = set()
    # 扫描全部条目（含 compact 之前的 archived entries）
    all_log_entries = list(getattr(log, "_archived_entries", [])) + list(log.entries)
    for e in all_log_entries:
        tag = e.get("tag", "") or ""
        name = e.get("name", "") or ""
        if tag == "summary":
            if name:
                log_judge_names.add(name)
        elif tag in NON_DEBATER_TAGS:
            continue
        elif (
            name.startswith("@meta")
            or name.startswith("👤")
            or name == "Compact Checkpoint"
        ):
            continue
        elif name:
            log_speaker_names.add(name)

    ghost_names = log_speaker_names - topic_names
    if ghost_names:
        msg = (
            f"❌ Log 中存在 topic 未配置的辩手: {', '.join(sorted(ghost_names))}\n"
            f"   使用 --force 跳过此检查，或用 modify --add 将其添加到 topic"
        )
        if force:
            print(f"⚠️ [force 忽略] {msg}", file=sys.stderr)
        else:
            print(msg, file=sys.stderr)
            sys.exit(1)

    new_names = topic_names - log_speaker_names
    if new_names and log.entries:
        print(
            f"ℹ️ Topic 中有 log 未出现的辩手（将作为新辩手参与）: "
            f"{', '.join(sorted(new_names))}"
        )

    topic_judge = (
        cfg.get("judge", {}).get("name", "")
        if isinstance(cfg.get("judge"), dict)
        else ""
    )
    if log_judge_names and topic_judge and topic_judge not in log_judge_names:
        print(
            f"⚠️ 裁判名变更: log 中记录的裁判为 {sorted(log_judge_names)}，"
            f"topic 当前为 {topic_judge!r}"
        )


def _validate_api_config(cfg: dict) -> list[str]:
    issues: list[str] = []

    debate_base_url = (cfg.get("base_url", "") or ENV_BASE_URL).strip()
    debate_api_key = (cfg.get("api_key", "") or ENV_API_KEY).strip()

    for idx, debater in enumerate(cfg.get("debaters", []), start=1):
        debater_name = debater.get("name", f"debater#{idx}")
        url = (debater.get("base_url", "") or debate_base_url).strip()
        key = (debater.get("api_key", "") or debate_api_key).strip()
        missing_fields: list[str] = []
        if not url:
            missing_fields.append("base_url")
        if not key:
            missing_fields.append("api_key")
        if missing_fields:
            issues.append(
                f"debaters[{idx}]({debater_name}): " + ", ".join(missing_fields)
            )

    judge = cfg.get("judge", {}) or {}
    judge_name = judge.get("name", "judge")
    judge_url = (judge.get("base_url", "") or debate_base_url).strip()
    judge_key = (judge.get("api_key", "") or debate_api_key).strip()
    judge_missing: list[str] = []
    if not judge_url:
        judge_missing.append("base_url")
    if not judge_key:
        judge_missing.append("api_key")
    if judge_missing:
        issues.append(f"judge({judge_name}): " + ", ".join(judge_missing))

    return issues


# ── CLI ───────────────────────────────────────────────────


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
    ap.add_argument(
        "topic", type=Path, help="议题 Markdown 文件（含 YAML front-matter）"
    )
    ap.add_argument("--rounds", type=int, default=None, help="覆盖辩论轮数")
    ap.add_argument("--dry-run", action="store_true", help="仅解析配置，不调用 LLM")
    ap.add_argument(
        "--cross-exam",
        nargs="?",
        type=int,
        const=1,
        default=None,
        metavar="N",
        help="质询轮数 (默认 1; -1=每轮都质询)",
    )
    ap.add_argument(
        "--early-stop",
        nargs="?",
        type=float,
        const=DEFAULT_EARLY_STOP_THRESHOLD,
        default=None,
        metavar="T",
        help="启用收敛早停 (默认阈值 0.55; 可指定 0~1 之间的值)",
    )
    ap.add_argument(
        "--cot",
        "--think",
        dest="cot_length",
        nargs="?",
        type=int,
        const=0,
        default=None,
        metavar="LENGTH",
        help="为辩手启用思考空间 (CoT)。LENGTH 为可选思考 token 预算，省略则不限制。",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="LOG_FILE",
        help="指定输出日志文件路径（默认: {stem}_{timestamp}_debate_log.json）",
    )
    ap.add_argument(
        "--debug",
        nargs="?",
        const=True,
        default=None,
        metavar="DEBUG_LOG",
        help="开启 debug 日志：省略文件名则输出到控制台，指定文件名则写入文件（10MB 轮转）",
    )

    args = ap.parse_args(argv)

    # 验证文件存在
    topic_path = args.topic.resolve()
    if not topic_path.exists():
        print(f"❌ 文件不存在: {topic_path}", file=sys.stderr)
        sys.exit(1)

    # 解析配置
    cfg = parse_topic_file(topic_path)

    # ── CLI 覆盖 ──
    # --cross-exam: CLI > YAML > 默认 0
    if args.cross_exam is not None:
        cfg["cross_exam"] = args.cross_exam

    # --early-stop: CLI > YAML
    if args.early_stop is not None:
        cfg["early_stop"] = args.early_stop

    # --rounds 总是覆盖
    if args.rounds is not None:
        cfg["rounds"] = args.rounds

    # --cot: CLI > YAML > None (disabled)
    # args.cot_length: None=not provided, 0=--cot without value, N=--cot=N
    cli_cot = args.cot_length  # None | 0 | positive int

    # 确保默认值
    cfg.setdefault("cross_exam", 0)
    cfg.setdefault("early_stop", 0.0)

    # 解析与校验 API 配置
    effective_url = (cfg["base_url"] or ENV_BASE_URL).strip()
    effective_key = (cfg["api_key"] or ENV_API_KEY).strip()
    api_issues = _validate_api_config(cfg)

    # Dry run — 打印配置后退出
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
        print(
            f"  早停:     {'是 (阈值 {:.0%})'.format(cfg.get('early_stop', 0.0)) if cfg.get('early_stop') else '否'}"
        )
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
        print(
            f"\n  裁判:     {j['name']} ({j['model']}, max_tokens={j.get('max_tokens', 8000)})"
        )
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
            print(
                "    请通过 front-matter（全局/辩手/裁判）或环境变量补齐 base_url / api_key"
            )
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

    # Debug 日志
    if args.debug is not None:
        init_debug_logging(args.debug)
        if args.debug is not True:
            print(f"  🐛 Debug 日志 → {args.debug}", file=sys.stderr)

    # 正式运行
    if args.output is not None:
        out_log_path = args.output.resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_log_path = topic_path.parent / f"{topic_path.stem}_{ts}{LOG_FILE_SUFFIX}"
    asyncio.run(run(cfg, topic_path, cot_length=cli_cot, log_path=out_log_path))


if __name__ == "__main__":
    main()
