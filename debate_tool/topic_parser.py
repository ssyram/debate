"""Topic/config parsing utilities extracted from runner.py.

Parses Markdown + YAML front-matter topic files and resume topic files.
Depends only on stdlib (os, re, pathlib) + PyYAML + debate_tool.core constants.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from debate_tool.core import (
    DEFAULT_DEBATERS,
    DEFAULT_EARLY_STOP_THRESHOLD,
    DEFAULT_JUDGE,
)


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
    def _replace(m: re.Match) -> str:
        var = m.group(1) or m.group(2) or ""
        return os.environ.get(var, m.group(0) or "") or ""
    return re.sub(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)", _replace, value)


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


def parse_resume_topic(path: Path) -> tuple[dict, str]:
    """解析 Resume Topic 文件（YAML front-matter + Markdown body）。

    返回 (overrides_dict, message_body)。
    - 运行控制字段 rounds、guide 提取后不记入 config_override
    - 其余字段构成 cfg_overrides dict

    Resume Topic 格式（YAML front-matter 含增量配置，body 为观察者消息）：
    ---
    rounds: 2
    judge_instructions: "..."
    middle_task: "..."
    add_debaters:
      - name: X
        model: gpt-5
        style: "..."
    drop_debaters:
      - 旧辩手名
    ---

    消息正文（观察者消息）
    """
    text = path.read_text(encoding="utf-8")
    # 分离 front-matter 和 body（复用 topic 文件的解析逻辑）
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
        else:
            fm_text = ""
            body = text
    else:
        fm_text = ""
        body = text

    overrides: dict = {}
    if fm_text:
        try:
            raw = yaml.safe_load(fm_text)
            if isinstance(raw, dict):
                overrides = raw
        except Exception:
            pass

    # 运行控制字段：提取后不记入 config_override
    # (调用方负责从返回的 overrides 中 pop 这些字段)
    return overrides, body


def _mask_key(key: str) -> str:
    if len(key) <= 7:
        return "****"
    return key[:3] + "****" + key[-4:]
