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

# ── Data structures ──────────────────────────────────────────────────

@dataclass
class StanceRecommendation:
    """A single recommended debater configuration."""
    name: str   # Display name, e.g. "GPT-5.2"
    model: str  # Model ID, e.g. "gpt-5.2"
    style: str  # Stance description, e.g. "精简派：追求最少改动、最低误伤风险"


@dataclass
class StanceResult:
    """Complete output from the stance generator."""
    debaters: list[StanceRecommendation]  # 3+ recommended debaters
    topic_angles: list[str]               # Key debate angles identified
    reasoning: str                        # Why these stances were chosen
    raw_response: str = ""                # Raw LLM response for debugging


# ── Resolve API config ───────────────────────────────────────────────

def _resolve_config(base_url: str, api_key: str) -> tuple[str, str]:
    """Resolve API config: function args > env vars."""
    url = (
        base_url
        or os.environ.get("DEBATE_BASE_URL", "")
    )
    key = (
        api_key
        or os.environ.get("DEBATE_API_KEY", "")
    )
    return url.strip(), key.strip()


# ── System prompt builder ────────────────────────────────────────────

def _build_system_prompt(num_debaters: int, user_prompt: str) -> str:
    user_prompt_section = (
        f"\n\n用户额外指示：{user_prompt}" if user_prompt else ""
    )
    return (
        f"你是一个辩论策划专家。分析给定的辩论议题，推荐 {num_debaters} 个辩手配置。\n"
        "\n"
        "每个辩手需要：\n"
        "1. name: 显示名称（通常是 LLM 模型名，如 GPT-5.2、Kimi-K2.5、Sonnet-4-6）\n"
        "2. model: 模型 ID（如 gpt-5.2、kimi-k2.5、claude-sonnet-4-6）\n"
        '3. style: 立场描述（格式："立场名：具体说明"，如 "精简派：追求最少改动、最低误伤风险"）\n'
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
        '    {"name": "...", "model": "...", "style": "..."},\n'
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
    """Call LLM to analyze a debate topic and recommend debater configurations.

    Args:
        topic_text: The debate topic body text.
        base_url: API base URL (falls back to env / hardcoded default).
        api_key: API key (falls back to env / hardcoded default).
        model: LLM model ID to use.
        num_debaters: Number of debater configurations to recommend.
        user_prompt: Additional user instructions appended to system prompt.
        timeout: HTTP request timeout in seconds.

    Returns:
        StanceResult with recommended debaters, topic angles, and reasoning.
    """
    url, key = _resolve_config(base_url, api_key)
    if not url:
        msg = "Missing API base URL: provide --base-url or set DEBATE_BASE_URL"
        return StanceResult(debaters=[], topic_angles=[], reasoning=msg)
    if not key:
        msg = "Missing API key: provide --api-key or set DEBATE_API_KEY"
        return StanceResult(debaters=[], topic_angles=[], reasoning=msg)
    system = _build_system_prompt(num_debaters, user_prompt)

    # Truncate overly long topic text
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

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        msg = f"LLM API returned HTTP {exc.response.status_code}"
        print(f"[stance] ERROR: {msg}", file=sys.stderr)
        return StanceResult(
            debaters=[], topic_angles=[], reasoning=msg,
            raw_response=exc.response.text,
        )
    except httpx.RequestError as exc:
        msg = f"LLM API request failed: {exc}"
        print(f"[stance] ERROR: {msg}", file=sys.stderr)
        return StanceResult(
            debaters=[], topic_angles=[], reasoning=msg,
        )

    raw = resp.json()["choices"][0]["message"]["content"]

    parsed = _extract_json(raw)
    if parsed is None:
        msg = "Failed to parse JSON from LLM response"
        print(f"[stance] ERROR: {msg}", file=sys.stderr)
        return StanceResult(
            debaters=[], topic_angles=[], reasoning=msg,
            raw_response=raw,
        )

    # Build StanceResult from parsed data
    debaters = [
        StanceRecommendation(
            name=d.get("name", ""),
            model=d.get("model", ""),
            style=d.get("style", ""),
        )
        for d in parsed.get("debaters", [])
    ]
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
    """Check a list of debater configs for common issues.

    Returns a list of warning strings (empty = all good).
    Pure heuristic — no LLM call.
    """
    warnings: list[str] = []

    if len(debaters) < 2:
        warnings.append("辩手数量不足：至少需要 2 位辩手才能形成有效对立")

    if len(debaters) > 7:
        warnings.append(f"辩手数量过多 ({len(debaters)})：超过 7 位辩手可能导致辩论失焦")

    # Check for duplicate models
    models = [d.get("model", "") for d in debaters]
    seen_models: dict[str, int] = {}
    for m in models:
        seen_models[m] = seen_models.get(m, 0) + 1
    for m, count in seen_models.items():
        if count > 1 and m:
            warnings.append(f"重复模型：{m} 被 {count} 位辩手使用，可能导致观点趋同")

    # Check for empty/missing fields
    for i, d in enumerate(debaters, 1):
        if not d.get("name", "").strip():
            warnings.append(f"辩手 {i}：缺少名称 (name)")
        if not d.get("model", "").strip():
            warnings.append(f"辩手 {i}：缺少模型 (model)")
        if not d.get("style", "").strip():
            warnings.append(f"辩手 {i}：缺少立场描述 (style)")

    # Check for style similarity (simple substring overlap)
    styles = [d.get("style", "").strip() for d in debaters if d.get("style", "").strip()]
    for i in range(len(styles)):
        for j in range(i + 1, len(styles)):
            # Extract the "派" label before colon if present
            label_i = styles[i].split("：")[0].split(":")[0].strip()
            label_j = styles[j].split("：")[0].split(":")[0].strip()
            if label_i and label_j and label_i == label_j:
                warnings.append(
                    f"立场标签重复：辩手 {i+1} 和辩手 {j+1} 都使用 \"{label_i}\""
                )

    return warnings

# ── Sync wrapper ─────────────────────────────────────────────────────

def generate_stances_sync(topic_text: str, **kwargs: Any) -> StanceResult:
    """Synchronous wrapper for generate_stances()."""
    return asyncio.run(generate_stances(topic_text, **kwargs))


# ── Formatting helpers ───────────────────────────────────────────────

def format_stances_json(result: StanceResult) -> str:
    """Format StanceResult as pretty JSON."""
    data = {
        "debaters": [
            {"name": d.name, "model": d.model, "style": d.style}
            for d in result.debaters
        ],
        "topic_angles": result.topic_angles,
        "reasoning": result.reasoning,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_stances_yaml(result: StanceResult) -> str:
    """Format debaters as YAML snippet (for embedding in topic files)."""
    lines = ["debaters:"]
    for d in result.debaters:
        lines.append(f'  - name: "{d.name}"')
        lines.append(f'    model: "{d.model}"')
        lines.append(f'    style: "{d.style}"')
    return "\n".join(lines) + "\n"


# ── Topic file reading ───────────────────────────────────────────────

def _read_topic_body(path: Path) -> str:
    """Read topic file, stripping YAML front-matter if present."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text


# ── CLI ──────────────────────────────────────────────────────────────

def main() -> None:
    """CLI: python -m debate_tool.stance topic.md [--model MODEL] [--num N] [--prompt TEXT] [--format json|yaml]"""
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

    args = parser.parse_args()

    if not args.topic.exists():
        print(f"[stance] ERROR: file not found: {args.topic}", file=sys.stderr)
        sys.exit(1)

    topic_body = _read_topic_body(args.topic)
    if not topic_body.strip():
        print("[stance] ERROR: topic file is empty (after stripping front-matter)", file=sys.stderr)
        sys.exit(1)

    result = generate_stances_sync(
        topic_body,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        num_debaters=args.num,
        user_prompt=args.prompt,
    )

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
