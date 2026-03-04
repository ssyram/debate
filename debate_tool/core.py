"""Pure logic — no curses, no click, no rich imports.

Constants, defaults, YAML generation, file I/O.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------

DEFAULT_DEBATERS = [
    {"name": "GPT-5.2",    "model": "gpt-5.2",          "style": "务实工程派"},
    {"name": "Kimi-K2.5",  "model": "kimi-k2.5",        "style": "创新挑战派"},
    {"name": "Sonnet-4-6", "model": "claude-sonnet-4-6", "style": "严谨分析派"},
]

DEFAULT_JUDGE: dict[str, Any] = {
    "model": "claude-opus-4-6",
    "name": "Opus-4-6 (裁判)",
    "max_tokens": 8000,
}

DEFAULT_ROUNDS = 3
DEFAULT_TIMEOUT = 300
DEFAULT_MAX_TOKENS = 6000

DEFAULT_BASE_URL = os.environ.get("DEBATE_BASE_URL", "").strip()
DEFAULT_API_KEY = os.environ.get("DEBATE_API_KEY", "").strip()

DEFAULT_ROUND1_TASK = "针对各议题给出立场和建议，每个 200-300 字"
DEFAULT_MIDDLE_TASK = "回应其他辩手观点，深化立场，400-600 字"
DEFAULT_FINAL_TASK = "最终轮，给出最终建议，标注优先级，300-500 字"

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

DEFAULT_CONSTRAINTS = ""

# ---------------------------------------------------------------------------
# Early-stop convergence threshold
# ---------------------------------------------------------------------------

DEFAULT_EARLY_STOP_THRESHOLD = 0.55


# All YAML front-matter field names in order
FIELD_ORDER = [
    "title", "rounds", "timeout", "max_tokens",
    "cross_exam", "early_stop",
    "base_url", "api_key",
    "debaters", "judge",
    "constraints",
    "round1_task", "middle_task", "final_task",
    "judge_instructions",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def title_to_filename(title: str) -> str:
    """Convert a title string to a safe filename slug.

    '我的辩论 Topic — V2' → 'my_debate_topic_v2.md'
    Falls back to 'debate_topic.md' if title is empty or all non-ASCII.
    """
    # Replace CJK and special chars with underscores
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[-\s]+", "_", slug).strip("_")
    # If result is empty (all CJK chars removed), use transliteration hint or default
    if not slug:
        # Simple: use pinyin-like heuristic — just use "debate_topic"
        slug = "debate_topic"
    return f"{slug}.md"


def mask_key(key: str) -> str:
    """Mask API key for display: first 3 + **** + last 4."""
    if not key:
        return "(空)"
    if len(key) <= 7:
        return "****"
    return key[:3] + "****" + key[-4:]


def is_curses_supported() -> bool:
    """Check if curses TUI is supported on this platform."""
    import sys
    if sys.platform == "win32":
        try:
            import curses  # noqa: F401
            return True
        except ImportError:
            return False
    return True


def detect_platform() -> str:
    """Detect current OS."""
    import sys
    p = sys.platform
    if p.startswith("linux"):
        return "linux"
    elif p == "darwin":
        return "macos"
    elif p == "win32":
        return "windows"
    return "unknown"


def trigram_jaccard(a: str, b: str) -> float:
    """Character-trigram Jaccard similarity. Works for CJK and Latin text."""
    if not a or not b:
        return 0.0
    # Normalise whitespace
    a = " ".join(a.split())
    b = " ".join(b.split())
    if len(a) < 3 or len(b) < 3:
        return 1.0 if a == b else 0.0
    set_a = {a[i:i + 3] for i in range(len(a) - 2)}
    set_b = {b[i:i + 3] for i in range(len(b) - 2)}
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def check_convergence(outputs: list[str], threshold: float) -> tuple[bool, float]:
    """Check if N outputs have converged (pairwise average similarity >= threshold).

    Returns (converged, avg_similarity).
    """
    if len(outputs) < 2:
        return False, 0.0
    sims = [trigram_jaccard(a, b) for a, b in combinations(outputs, 2)]
    avg = sum(sims) / len(sims)
    return avg >= threshold, avg


# ---------------------------------------------------------------------------
# YAML generation
# ---------------------------------------------------------------------------


def _yaml_literal_block(text: str, indent: int = 2) -> str:
    """Format a multiline string as YAML literal block (|)."""
    prefix = " " * indent
    lines = text.split("\n")
    return "|\n" + "\n".join(f"{prefix}{line}" for line in lines)


def _yaml_debaters(debaters: list[dict]) -> str:
    """Format debaters list as YAML."""
    lines = []
    for d in debaters:
        lines.append(f'  - name: "{d["name"]}"')
        lines.append(f'    model: "{d["model"]}"')
        lines.append(f'    style: "{d["style"]}"')
        debater_base_url = str(d.get("base_url", "")).strip()
        if debater_base_url:
            lines.append(f'    base_url: "{debater_base_url}"')
        debater_api_key = str(d.get("api_key", "")).strip()
        if debater_api_key:
            lines.append(f'    api_key: "{debater_api_key}"')
    return "\n".join(lines)


def _yaml_judge(judge: dict) -> str:
    """Format judge dict as YAML."""
    lines = [
        f'  model: "{judge["model"]}"',
        f'  name: "{judge["name"]}"',
        f'  max_tokens: {judge.get("max_tokens", 8000)}',
    ]
    judge_base_url = str(judge.get("base_url", "")).strip()
    if judge_base_url:
        lines.append(f'  base_url: "{judge_base_url}"')
    judge_api_key = str(judge.get("api_key", "")).strip()
    if judge_api_key:
        lines.append(f'  api_key: "{judge_api_key}"')
    return "\n".join(lines)


def generate_topic_file(config: dict) -> str:
    """Build full .md content: ---\\n{yaml}\\n---\\n\\n{body}

    Omits fields that match their defaults to keep output clean.
    Always emits: title, debaters, judge (for clarity even if defaults).
    """
    parts: list[str] = []

    # title — always emit
    parts.append(f'title: "{config.get("title", "")}"')

    # rounds — emit if non-default
    rounds = config.get("rounds", DEFAULT_ROUNDS)
    if rounds != DEFAULT_ROUNDS:
        parts.append(f"rounds: {rounds}")

    # timeout — emit if non-default
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    if timeout != DEFAULT_TIMEOUT:
        parts.append(f"timeout: {timeout}")

    # max_tokens — emit if non-default
    max_tokens = config.get("max_tokens", DEFAULT_MAX_TOKENS)
    if max_tokens != DEFAULT_MAX_TOKENS:
        parts.append(f"max_tokens: {max_tokens}")

    # cross_exam — emit if non-zero
    cross_exam = config.get("cross_exam", 0)
    if cross_exam:
        parts.append(f"cross_exam: {cross_exam}")

    # early_stop — emit if True
    early_stop = config.get("early_stop", False)
    if early_stop:
        parts.append("early_stop: true")

    # base_url — only if set
    base_url = config.get("base_url", "").strip()
    if base_url:
        parts.append(f'base_url: "{base_url}"')

    # api_key — only if set
    api_key = config.get("api_key", "").strip()
    if api_key:
        parts.append(f'api_key: "{api_key}"')

    # debaters — always emit
    debaters = config.get("debaters", DEFAULT_DEBATERS)
    parts.append(f"debaters:\n{_yaml_debaters(debaters)}")

    # judge — always emit
    judge = config.get("judge", DEFAULT_JUDGE)
    parts.append(f"judge:\n{_yaml_judge(judge)}")

    # constraints — only if set
    constraints = config.get("constraints", "").strip()
    if constraints:
        parts.append(f"constraints: {_yaml_literal_block(constraints)}")

    # round tasks — only if non-default
    round1 = config.get("round1_task", DEFAULT_ROUND1_TASK).strip()
    if round1 and round1 != DEFAULT_ROUND1_TASK:
        parts.append(f"round1_task: {_yaml_literal_block(round1)}")

    middle = config.get("middle_task", DEFAULT_MIDDLE_TASK).strip()
    if middle and middle != DEFAULT_MIDDLE_TASK:
        parts.append(f"middle_task: {_yaml_literal_block(middle)}")

    final = config.get("final_task", DEFAULT_FINAL_TASK).strip()
    if final and final != DEFAULT_FINAL_TASK:
        parts.append(f"final_task: {_yaml_literal_block(final)}")

    # judge_instructions — only if non-default
    ji = config.get("judge_instructions", DEFAULT_JUDGE_INSTRUCTIONS).strip()
    if ji and ji != DEFAULT_JUDGE_INSTRUCTIONS:
        parts.append(f"judge_instructions: {_yaml_literal_block(ji)}")

    # Assemble
    yaml_block = "\n".join(parts)
    body = config.get("topic_body", "").strip()

    return f"---\n{yaml_block}\n---\n\n{body}\n"


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def write_topic_file(path: Path, content: str) -> None:
    """Atomic write: .tmp + os.replace(), mkdir parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def get_run_command(path: Path) -> str:
    """Return the command to run a debate with the given topic file."""
    return f"python -m debate_tool run {path}"


def get_dryrun_command(path: Path) -> str:
    """Return the command for a dry-run preview."""
    return f"python -m debate_tool run {path} --dry-run"
