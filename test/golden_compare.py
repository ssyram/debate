"""Golden reference comparison utilities for debate-tool tests.

Normalizes timestamp-only differences so deterministic mock outputs
can be compared across runs.
"""
import json
import re
import difflib
from pathlib import Path

TS_SENTINEL = "__TS__"
URL_SENTINEL = "__URL__"
KEY_SENTINEL = "__KEY__"

_URL_KEYS = {"base_url", "compact_base_url", "compact_check_base_url"}
_KEY_KEYS = {"api_key", "compact_api_key", "compact_check_api_key"}


def _normalize_config(cfg: dict) -> dict:
    out = {}
    for k, v in cfg.items():
        if k in _URL_KEYS:
            out[k] = URL_SENTINEL
        elif k in _KEY_KEYS:
            out[k] = KEY_SENTINEL
        elif k == "judge" and isinstance(v, dict):
            out[k] = _normalize_config(v)
        elif k == "debaters" and isinstance(v, list):
            out[k] = [_normalize_config(d) if isinstance(d, dict) else d for d in v]
        else:
            out[k] = v
    return out


def normalize_log(data: dict) -> dict:
    out = dict(data)
    out["created_at"] = TS_SENTINEL
    out["updated_at"] = TS_SENTINEL
    if "initial_config" in out and isinstance(out["initial_config"], dict):
        out["initial_config"] = _normalize_config(out["initial_config"])
    out["entries"] = []
    for e in data.get("entries", []):
        ec = dict(e)
        ec["ts"] = TS_SENTINEL
        out["entries"].append(ec)
    return out


def normalize_summary(text: str) -> str:
    """Replace the ISO8601 timestamp line in summary markdown with sentinel.

    Format: '> 2026-03-21T14:30:26.201293' → '> __TS__'
    """
    return re.sub(
        r"^(>\s*)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?",
        rf"\1{TS_SENTINEL}", text, count=1, flags=re.MULTILINE,
    )


def _canonical_json(data: dict) -> str:
    """Canonical JSON for diffing: sorted keys, 2-space indent."""
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def compare_golden_log(actual_path: Path, golden_path: Path) -> tuple[bool, str]:
    """Compare actual log JSON against golden reference after normalization.

    Returns (passed, diff_description).
    """
    actual_data = json.loads(actual_path.read_text(encoding="utf-8"))
    golden_data = json.loads(golden_path.read_text(encoding="utf-8"))

    actual_json = _canonical_json(normalize_log(actual_data))
    golden_json = _canonical_json(normalize_log(golden_data))

    if actual_json == golden_json:
        return True, ""

    diff = difflib.unified_diff(
        golden_json.splitlines(keepends=True),
        actual_json.splitlines(keepends=True),
        fromfile="golden", tofile="actual", n=3,
    )
    return False, "".join(diff)


def compare_golden_summary(actual_path: Path, golden_path: Path) -> tuple[bool, str]:
    """Compare actual summary MD against golden reference after normalization."""
    actual_norm = normalize_summary(actual_path.read_text(encoding="utf-8"))
    golden_norm = normalize_summary(golden_path.read_text(encoding="utf-8"))

    if actual_norm == golden_norm:
        return True, ""

    diff = difflib.unified_diff(
        golden_norm.splitlines(keepends=True),
        actual_norm.splitlines(keepends=True),
        fromfile="golden", tofile="actual", n=3,
    )
    return False, "".join(diff)


def write_golden_log(data: dict, golden_path: Path):
    """Write normalized log as golden reference."""
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    golden_path.write_text(
        _canonical_json(normalize_log(data)) + "\n", encoding="utf-8",
    )


def write_golden_summary(text: str, golden_path: Path):
    """Write normalized summary as golden reference."""
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    golden_path.write_text(normalize_summary(text), encoding="utf-8")
