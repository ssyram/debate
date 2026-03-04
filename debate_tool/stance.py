#!/usr/bin/env python3
"""
LLM-powered stance / debater-configuration generator.

CLI usage:
    python -m debate_tool.stance topic.md
    python -m debate_tool.stance topic.md --num 5 --format yaml

Library usage:
    from debate_tool.stance import generate_stances, generate_stances_sync
    result = generate_stances_sync(topic_text)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from debate_tool.core import DEFAULT_DEBATE_MODELS

# ── Data structures ──────────────────────────────────────────────────


@dataclass
class StanceRecommendation:
    name: str
    model: str
    style: str


@dataclass
class StanceResult:
    debaters: list[StanceRecommendation]
    topic_angles: list[str]
    reasoning: str
    raw_response: str = ""


# ── Resolve API config ───────────────────────────────────────────────


def _resolve_config(base_url: str, api_key: str) -> tuple[str, str]:
    """Resolve API config: function args > env vars."""
    url = base_url or os.environ.get("DEBATE_BASE_URL", "")
    key = api_key or os.environ.get("DEBATE_API_KEY", "")
    return url.strip(), key.strip()


# ── System prompt builder ────────────────────────────────────────────


def _build_system_prompt(num_debaters: int, user_prompt: str) -> str:
    user_prompt_section = f"\n\n用户额外指示：{user_prompt}" if user_prompt else ""
    return (
        f"你是一个辩论策划专家。分析给定的辩论议题，推荐 {num_debaters} 个辩手配置。\n"
        "\n"
        "每个辩手需要：\n"
        "1. name: 显示名称（立场代号，如 务实派、挑战者、分析师）\n"
        '2. style: 立场描述（格式："立场名：具体说明"，如 "精简派：追求最少改动、最低误伤风险"）\n'
        "\n"
        "立场设计原则：\n"
        "- 辩手之间应形成有效对立或互补，避免同质化\n"
        "- style 应该与议题紧密相关，包含议题特有的术语和关注点\n"
        "- 常见的三元对立结构：保守 vs 激进 vs 平衡，或 审查 vs 支持 vs 中立\n"
        "- 可参考的立场风格模板：\n"
        "  * 通用型：务实工程派 / 创新挑战派 / 严谨分析派\n"
        "  * 权衡型：精简派 / 覆盖派 / 平衡派\n"
        "  * 审查型：严格审查派 / 支持验证派 / 中立分析派\n"
        '  * 也可以完全自定义（如 "红队攻击手：目标是找到所有漏洞..."）\n'
        "\n"
        "同时分析议题的核心辩论角度（3-5 个）。\n"
        f"{user_prompt_section}\n"
        "\n"
        "严格按以下 JSON 格式输出（不要输出其他内容）：\n"
        "```json\n"
        "{\n"
        '  "debaters": [\n'
        '    {"name": "...", "style": "..."},\n'
        "    ...\n"
        "  ],\n"
        '  "topic_angles": ["角度1", "角度2", ...],\n'
        '  "reasoning": "选择这些立场的理由..."\n'
        "}\n"
        "```"
    )


# ── JSON extraction from LLM response ───────────────────────────────


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract JSON from LLM response, handling markdown code fences."""
    # Try to extract from ```json ... ``` blocks first
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    candidate = m.group(1).strip() if m else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Last resort: find first { ... } block
    m2 = re.search(r"\{.*\}", text, re.DOTALL)
    if m2:
        try:
            return json.loads(m2.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _resolve_model(payload: dict[str, Any]) -> str:
    model_name = payload.get("model", "")
    if isinstance(model_name, str):
        model_name = model_name.strip()
    else:
        model_name = ""
    return model_name or "gpt-5.2"


# ── Core async function ──────────────────────────────────────────────


async def generate_stances(
    topic_text: str,
    *,
    base_url: str = "",
    api_key: str = "",
    model: str = "gpt-5.2",
    num_debaters: int = 3,
    user_prompt: str = "",
    timeout: int = 120,
) -> StanceResult:
    url, key = _resolve_config(base_url, api_key)
    if not url:
        msg = "Missing API base URL: provide --base-url or set DEBATE_BASE_URL"
        return StanceResult(debaters=[], topic_angles=[], reasoning=msg)
    if not key:
        msg = "Missing API key: provide --api-key or set DEBATE_API_KEY"
        return StanceResult(debaters=[], topic_angles=[], reasoning=msg)
    system = _build_system_prompt(num_debaters, user_prompt)

    truncated = topic_text[:8000] if len(topic_text) > 8000 else topic_text

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": truncated},
        ],
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    max_retries = 3
    retry_delay = 2

    resp = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    url.rstrip("/"),
                    json=payload,
                    headers=headers,
                )

                if resp.status_code == 503:
                    if attempt < max_retries - 1:
                        print(
                            f"[stance] 503 错误，{retry_delay}秒后重试 (尝试 {attempt + 1}/{max_retries})...",
                            file=sys.stderr,
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        msg = f"LLM API 返回 503 (服务暂时不可用，已重试 {max_retries} 次)"
                        print(f"[stance] ERROR: {msg}", file=sys.stderr)
                        return StanceResult(
                            debaters=[],
                            topic_angles=[],
                            reasoning=msg,
                            raw_response=resp.text,
                        )

                resp.raise_for_status()
                break

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 503:
                if attempt < max_retries - 1:
                    print(
                        f"[stance] 503 错误，{retry_delay}秒后重试 (尝试 {attempt + 1}/{max_retries})...",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            msg = f"LLM API 返回 HTTP {exc.response.status_code}"
            print(f"[stance] ERROR: {msg}", file=sys.stderr)
            return StanceResult(
                debaters=[],
                topic_angles=[],
                reasoning=msg,
                raw_response=exc.response.text,
            )
        except httpx.RequestError as exc:
            msg = f"LLM API request failed: {exc}"
            print(f"[stance] ERROR: {msg}", file=sys.stderr)
            return StanceResult(
                debaters=[],
                topic_angles=[],
                reasoning=msg,
            )

    if resp is None:
        msg = "LLM API request failed: no response received"
        return StanceResult(debaters=[], topic_angles=[], reasoning=msg)

    raw = resp.json()["choices"][0]["message"]["content"]

    parsed = _extract_json(raw)
    if parsed is None:
        msg = "Failed to parse JSON from LLM response"
        print(f"[stance] ERROR: {msg}", file=sys.stderr)
        return StanceResult(
            debaters=[],
            topic_angles=[],
            reasoning=msg,
            raw_response=raw,
        )

    models = DEFAULT_DEBATE_MODELS
    debaters: list[StanceRecommendation] = []
    for i, d in enumerate(parsed.get("debaters", [])):
        if not isinstance(d, dict):
            continue
        assigned_model = models[i % len(models)]
        debaters.append(
            StanceRecommendation(
                name=str(d.get("name", "")).strip(),
                model=assigned_model,
                style=str(d.get("style", "")).strip(),
            )
        )
    topic_angles = parsed.get("topic_angles", [])
    reasoning = parsed.get("reasoning", "")

    return StanceResult(
        debaters=debaters,
        topic_angles=topic_angles,
        reasoning=reasoning,
        raw_response=raw,
    )


# ── Stance checker ──────────────────────────────────────────────────


def check_stances(debaters: list[dict[str, str]]) -> list[str]:
    warnings: list[str] = []

    if len(debaters) < 2:
        warnings.append("辩手数量不足：至少需要 2 位辩手才能形成有效对立")

    if len(debaters) > 7:
        warnings.append(
            f"辩手数量过多 ({len(debaters)})：超过 7 位辩手可能导致辩论失焦"
        )

    for i, d in enumerate(debaters, 1):
        if not d.get("name", "").strip():
            warnings.append(f"辩手 {i}：缺少名称 (name)")
        if not d.get("model", "").strip():
            warnings.append(f"辩手 {i}：缺少模型 (model)")
        if not d.get("style", "").strip():
            warnings.append(f"辩手 {i}：缺少立场描述 (style)")

    styles = [
        d.get("style", "").strip() for d in debaters if d.get("style", "").strip()
    ]
    for i in range(len(styles)):
        for j in range(i + 1, len(styles)):
            label_i = styles[i].split("：")[0].split(":")[0].strip()
            label_j = styles[j].split("：")[0].split(":")[0].strip()
            if label_i and label_j and label_i == label_j:
                warnings.append(
                    f'立场标签重复：辩手 {i + 1} 和辩手 {j + 1} 都使用 "{label_i}"'
                )

    return warnings


# ── Sync wrapper ─────────────────────────────────────────────────────


def generate_stances_sync(topic_text: str, **kwargs: Any) -> StanceResult:
    return asyncio.run(generate_stances(topic_text, **kwargs))


# ── Formatting helpers ───────────────────────────────────────────────


def format_stances_json(result: StanceResult) -> str:
    """Format StanceResult as pretty JSON."""
    data = {
        "debaters": [
            {
                "name": d.name,
                "model": d.model,
                "style": d.style,
            }
            for d in result.debaters
        ],
        "topic_angles": result.topic_angles,
        "reasoning": result.reasoning,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_stances_yaml(result: StanceResult) -> str:
    lines = ["debaters:"]
    for d in result.debaters:
        lines.append(f'  - name: "{d.name}"')
        lines.append(f'    model: "{d.model}"')
        lines.append(f'    style: "{d.style}"')
    return "\n".join(lines) + "\n"


def _read_topic_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text


# ── CLI ──────────────────────────────────────────────────────────────


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="LLM-powered debate stance / debater-configuration generator",
    )
    parser.add_argument(
        "topic",
        type=Path,
        help="Path to topic Markdown file",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.2",
        help="LLM model to use (default: gpt-5.2)",
    )
    parser.add_argument(
        "--num",
        type=int,
        default=3,
        help="Number of debaters to recommend (default: 3)",
    )
    parser.add_argument(
        "--prompt",
        default="",
        help="Additional user instructions for stance generation",
    )
    parser.add_argument(
        "--format",
        choices=["json", "yaml"],
        default="json",
        dest="output_format",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="API base URL (default: env DEBATE_BASE_URL)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key (default: env DEBATE_API_KEY)",
    )

    args = parser.parse_args(argv)

    if not args.topic.exists():
        print(f"[stance] ERROR: file not found: {args.topic}", file=sys.stderr)
        sys.exit(1)

    topic_body = _read_topic_body(args.topic)
    if not topic_body.strip():
        print(
            "[stance] ERROR: topic file is empty (after stripping front-matter)",
            file=sys.stderr,
        )
        sys.exit(1)

    result = generate_stances_sync(
        topic_body,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        num_debaters=args.num,
        user_prompt=args.prompt,
    )

    if not result.debaters and result.reasoning.startswith("Missing API"):
        print(f"[stance] ERROR: {result.reasoning}", file=sys.stderr)
        sys.exit(2)

    if not result.debaters:
        print("[stance] WARNING: no debaters generated", file=sys.stderr)
        if result.raw_response:
            print(f"[stance] Raw LLM response:\n{result.raw_response}", file=sys.stderr)

    if args.output_format == "yaml":
        print(format_stances_yaml(result))
    else:
        print(format_stances_json(result))


if __name__ == "__main__":
    main()
