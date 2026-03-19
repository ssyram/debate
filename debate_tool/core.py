"""Pure logic — no curses, no click, no rich imports.

Constants, defaults, YAML generation, file I/O.
"""

from __future__ import annotations

import json
import math
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
    {"name": "GPT-5.2", "model": "gpt-5.2", "style": "务实工程派"},
    {"name": "Kimi-K2.5", "model": "kimi-k2.5", "style": "创新挑战派"},
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

# Comma-separated model list for cycling across debaters.
# e.g. "gpt-5.2,kimi-k2.5,MiniMax-M2.5"
# The i-th debater gets models[i % len(models)].
_raw_models = os.environ.get("DEFAULT_DEBATE_MODELS", "").strip()
DEFAULT_DEBATE_MODELS: list[str] = (
    [m.strip() for m in _raw_models.split(",") if m.strip()]
    if _raw_models
    else ["gpt-5.2"]
)

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
    "title",
    "rounds",
    "timeout",
    "max_reply_tokens",
    "cross_exam",
    "early_stop",
    "base_url",
    "api_key",
    "debaters",
    "judge",
    "constraints",
    "round1_task",
    "middle_task",
    "final_task",
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
    set_a = {a[i : i + 3] for i in range(len(a) - 2)}
    set_b = {b[i : i + 3] for i in range(len(b) - 2)}
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
        f"  max_tokens: {judge.get('max_tokens', 8000)}",
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
    max_reply_tokens = config.get("max_reply_tokens", DEFAULT_MAX_TOKENS)
    if max_reply_tokens != DEFAULT_MAX_TOKENS:
        parts.append(f"max_reply_tokens: {max_reply_tokens}")

    # cross_exam — emit if non-zero
    cross_exam = config.get("cross_exam", 0)
    if cross_exam:
        parts.append(f"cross_exam: {cross_exam}")

    # early_stop — emit if non-zero
    early_stop = config.get("early_stop", 0.0)
    if early_stop:
        if early_stop == DEFAULT_EARLY_STOP_THRESHOLD:
            parts.append("early_stop: true")
        else:
            parts.append(f"early_stop: {early_stop}")

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


# ---------------------------------------------------------------------------
# Token estimation & context compaction
# ---------------------------------------------------------------------------

# Conservative CJK-heavy estimate: ~2 tokens/char for CJK, ~0.33 for ASCII
_CJK_RANGES = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"\u2e80-\u2eff\u3000-\u303f\uff00-\uffef]"
)

DEFAULT_COMPACT_TRIGGER = 0.8
DEFAULT_COMPACT_THRESHOLD = 175_000  # token 数超过此值时主动触发 compact


def estimate_tokens(text: str) -> int:
    cjk_count = len(_CJK_RANGES.findall(text))
    ascii_count = len(text) - cjk_count
    return math.ceil(cjk_count * 2 + ascii_count * 0.33)


def build_compact_context(
    entries: list[dict],
    *,
    token_budget: int,
    num_debaters: int,
    system_text: str = "",
) -> str:
    """Build tiered compact context from debate log entries.

    Zones:
      Hot  — recent 1-2 rounds: full text   (40-50% budget)
      Warm — rounds 3-5 back:   truncated   (30-40% budget)
      Cold — older rounds:      one-liner   (10-15% budget)
      System (topic/constraints) always preserved (10-15% budget).

    Returns the compacted context string.
    """
    if not entries:
        return "(无辩论记录)"

    system_tokens = estimate_tokens(system_text) if system_text else 0
    available = token_budget - system_tokens
    if available <= 0:
        return "(上下文预算不足)"

    entries_per_round = max(num_debaters, 1)
    total_entries = len(entries)
    total_rounds = math.ceil(total_entries / entries_per_round)

    hot_rounds = min(2, total_rounds)
    hot_cutoff = total_entries - (hot_rounds * entries_per_round)
    if hot_cutoff < 0:
        hot_cutoff = 0

    warm_rounds = min(3, total_rounds - hot_rounds)
    warm_cutoff = hot_cutoff - (warm_rounds * entries_per_round)
    if warm_cutoff < 0:
        warm_cutoff = 0

    cold_entries = entries[:warm_cutoff]
    warm_entries = entries[warm_cutoff:hot_cutoff]
    hot_entries = entries[hot_cutoff:]

    hot_budget = int(available * 0.50)
    warm_budget = int(available * 0.35)
    cold_budget = available - hot_budget - warm_budget

    parts: list[str] = []

    if cold_entries:
        cold_lines = []
        chars_per_entry = max(cold_budget * 3 // max(len(cold_entries), 1), 40)
        for e in cold_entries:
            tag = f"[{e['tag'].upper()}] " if e.get("tag") else ""
            first_line = e["content"].split("\n", 1)[0][:chars_per_entry]
            cold_lines.append(f"[{e['seq']}] {tag}{e['name']}: {first_line}")
        parts.append("### 早期轮次摘要\n" + "\n".join(cold_lines))

    if warm_entries:
        warm_lines = []
        chars_per_entry = max(warm_budget * 3 // max(len(warm_entries), 1), 100)
        for e in warm_entries:
            tag = f"[{e['tag'].upper()}] " if e.get("tag") else ""
            content = e["content"]
            if len(content) > chars_per_entry:
                half = chars_per_entry // 2
                content = content[:half] + "\n...(省略)...\n" + content[-half:]
            warm_lines.append(f"### [{e['seq']}] {tag}{e['name']}\n{content}")
        parts.append("\n\n".join(warm_lines))

    if hot_entries:
        hot_lines = []
        chars_per_entry = max(hot_budget * 3 // max(len(hot_entries), 1), 200)
        for e in hot_entries:
            tag = f"[{e['tag'].upper()}] " if e.get("tag") else ""
            content = e["content"][:chars_per_entry]
            if len(e["content"]) > chars_per_entry:
                content += "...(截断)"
            hot_lines.append(f"### [{e['seq']}] {tag}{e['name']}\n{content}")
        parts.append("\n\n".join(hot_lines))

    return "\n\n".join(parts)


def build_full_compact(
    entries: list[dict],
    *,
    token_budget: int,
    keep_last: int = 0,
) -> tuple[str, list[dict]]:
    """Compress entries uniformly — no protected zones.

    Args:
        keep_last: number of entries from the end to keep uncompressed.
                   0 = compress everything.

    Returns (compact_text, kept_entries) where kept_entries are the
    uncompressed tail entries (empty list if keep_last=0).
    """
    if not entries:
        return "(无辩论记录)", []

    if keep_last > 0 and keep_last < len(entries):
        to_compact = entries[:-keep_last]
        kept = entries[-keep_last:]
    elif keep_last >= len(entries):
        return "(无需压缩)", list(entries)
    else:
        to_compact = entries
        kept = []

    total_chars = sum(len(e["content"]) for e in to_compact)
    chars_budget = token_budget * 3
    if total_chars <= chars_budget:
        chars_per_entry = max(chars_budget // max(len(to_compact), 1), 200)
    else:
        ratio = chars_budget / max(total_chars, 1)
        chars_per_entry = max(
            int(max(len(e["content"]) for e in to_compact) * ratio), 80
        )

    _TAG_DISPLAY = {
        "summary": "裁判总结",
        "cross_exam": "质询",
        "human": "观察者",
        "meta": "系统变更",
        "thinking": "思考",
        "compact_checkpoint": "压缩快照",
    }
    parts: list[str] = []
    for e in to_compact:
        raw_tag = e.get("tag", "") or ""
        tag_label = _TAG_DISPLAY.get(raw_tag, "发言")
        content = e["content"]
        if len(content) > chars_per_entry:
            half = chars_per_entry // 2
            content = content[:half] + "\n...(压缩省略)...\n" + content[-half:]
        parts.append(f"[{e['seq']}] {e['name']}（{tag_label}）\n{content}")

    return "\n\n---\n\n".join(parts), kept


def parse_compact_checkpoint(content_str: str) -> dict:
    """解析 compact_checkpoint entry 的 content 字段。

    新格式：JSON 字符串，包含 {"state": CompactState, "public_view": str}
    旧格式：纯文本字符串（向后兼容）

    返回 {"state": dict|None, "public_view": str}
    """
    try:
        parsed = json.loads(content_str)
        if isinstance(parsed, dict) and "public_view" in parsed:
            return parsed
        # JSON 但不是新格式，当作旧格式处理
        return {"state": None, "public_view": content_str}
    except (json.JSONDecodeError, ValueError):
        # 旧格式：纯文本
        return {"state": None, "public_view": content_str}


def _build_initial_config(cfg: dict) -> dict:
    """从 parsed topic cfg 构建 v2 log 的 initial_config 快照。

    规则：
    - per-debater base_url 保留（多端点场景必需），api_key 排除
    - judge base_url 保留，api_key 排除
    - 包含 compact 相关配置字段（compact_model 等），未配置则填 null
    - middle_task_optional 字段在 v2 中废弃，不写入
    - 这是唯一构建 initial_config 的入口，run() 和迁移脚本均调用此函数
    """
    return {
        "debaters": [
            {k: v for k, v in d.items() if k != "api_key"}
            for d in cfg["debaters"]
        ],
        "judge": {k: v for k, v in cfg["judge"].items() if k != "api_key"},
        "constraints": cfg.get("constraints", ""),
        "round1_task": cfg.get("round1_task", ""),
        "middle_task": cfg.get("middle_task", ""),
        "final_task": cfg.get("final_task", ""),
        "judge_instructions": cfg.get("judge_instructions", ""),
        "max_reply_tokens": cfg.get("max_reply_tokens", 6000),
        "timeout": cfg.get("timeout", 300),
        "cross_exam": cfg.get("cross_exam", 0),
        "early_stop": cfg.get("early_stop", False),
        "cot": cfg.get("cot_length", None),
        # compact 配置：使 compact_log 命令无需外部 topic 文件即可独立运行
        "compact_model": cfg.get("compact_model", None),
        "compact_check_model": cfg.get("compact_check_model", None),
        "compact_max_tokens": cfg.get("compact_max_tokens", None),
        "embedding_model": cfg.get("embedding_model", None),
        # 注意：middle_task_optional 在 v2 中废弃，不写入
    }
