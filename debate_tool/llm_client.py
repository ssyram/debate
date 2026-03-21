"""LLM 调用模块：call_llm 及相关辅助函数。"""

import asyncio
import os
import re as _re
import sys

import httpx

from .debug_log import dlog

# ── 环境变量 ────────────────────────────────────────────
ENV_BASE_URL = os.environ.get("DEBATE_BASE_URL", "").strip()
ENV_API_KEY = os.environ.get("DEBATE_API_KEY", "").strip()

# ── Token 限制检测 ────────────────────────────────────────

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
    purpose: str = "",
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
    dlog("llm.request", f"model={model} purpose={purpose}",
         model=model, purpose=purpose, url=url,
         max_tokens=max_reply_tokens,
         system=_preview_debug_text(system, 800),
         user=_preview_debug_text(user_content, 800))
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
                dlog("llm.response.raw", f"model={model} status={r.status_code}",
                     model=model, purpose=purpose, status=r.status_code,
                     body=_preview_debug_text(body_text, 2000))
                if _is_token_limit_error(r.status_code, body_text):
                    limit = _parse_token_limit(body_text) or 0
                    raise TokenLimitError(model, limit, body_text)
                r.raise_for_status()
                data = r.json()
                content, finish_reason = _extract_response_text(data)
                if finish_reason == "length" and attempt < 2:
                    dlog("llm.response.truncated", f"model={model} attempt={attempt}",
                         model=model, purpose=purpose, attempt=attempt,
                         retry_max_tokens=min(max(max_reply_tokens * (2 ** (attempt + 1)), 600), 16000))
                    continue
                dlog("llm.response", f"model={model} finish={finish_reason}",
                     model=model, purpose=purpose, finish_reason=finish_reason,
                     content=_preview_debug_text(content, 300))
                return content
            except TokenLimitError:
                raise
            except Exception as e:
                dlog("llm.error", f"model={model} attempt={attempt} err={e}",
                     model=model, purpose=purpose, attempt=attempt, error=str(e))
                if attempt == 2:
                    return f"[调用失败: {e}]"
                print(f"  ⚠️ {model} retry {attempt + 1}: {e}", file=sys.stderr)
                await asyncio.sleep(2**attempt)
    return "[调用失败]"


def _strip_json_fence(text: str) -> str:
    """剥离 LLM 返回的 JSON 前后 markdown 代码块标记。"""
    return (
        text.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )


# ── CoT 辅助 ──────────────────────────────────────────────

_THINKING_RE = _re.compile(r"<thinking>(.*?)</thinking>", _re.DOTALL)
_THINKING_OPEN_RE = _re.compile(r"<thinking>(.*)", _re.DOTALL)


def _strip_thinking_tags(text: str) -> str:
    """去除所有 <thinking>...</thinking> 标签及残留的 <thinking> / </thinking> 标记。"""
    text = _re.sub(r"<thinking>.*?</thinking>", "", text, flags=_re.DOTALL)
    text = _re.sub(r"</?thinking>", "", text)
    return text.strip()


def _split_cot_response(response: str) -> tuple[str, str]:
    """Split a COT response into (thinking_content, actual_reply).

    Returns (thinking, reply).  Both non-empty = parse success.
    Any other result (no tags, truncated, empty reply) = parse failure.
    """
    m = _THINKING_RE.search(response)
    if m:
        thinking = m.group(1).strip()
        after = response[m.end():].lstrip()
        return thinking, after
    # Truncated: opening tag present but no closing tag
    m_open = _THINKING_OPEN_RE.search(response)
    if m_open:
        return m_open.group(1).strip(), ""
    # No tags at all
    return "", response


async def _split_cot_or_regenerate_reply(
    response: str,
    *,
    model: str,
    base_sys_prompt: str,
    user_ctx: str,
    max_reply_tokens: int,
    timeout: int,
    base_url: str,
    api_key: str,
) -> tuple[str, str]:
    """Extract (thinking, reply) from a CoT response.

    Parse success = both thinking and reply are non-empty.
    Parse failure (no tags, truncated, or empty reply) = strip all <thinking>
    tags from the full response and use the cleaned text as thinking context
    for a second call that produces the reply.
    """
    thinking, reply = _split_cot_response(response)
    if thinking and reply:
        return thinking, reply
    # Parse failed — treat full response (tags stripped) as thinking context
    cleaned = _strip_thinking_tags(response) or response
    recovery_sys = (
        base_sys_prompt
        + "\n\n【补全任务】以下是你已完成的思考内容：\n"
        + cleaned
        + "\n\n请基于以上思考内容直接输出辩论发言，不使用 <thinking> 标签。"
    )
    reply = await call_llm(
        model, recovery_sys, user_ctx,
        max_reply_tokens=max_reply_tokens,
        timeout=timeout,
        base_url=base_url,
        api_key=api_key,
        purpose="cot.recovery",
    )
    return cleaned, reply
