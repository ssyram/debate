#!/usr/bin/env python3
"""Temporary converter: legacy Markdown debate log -> JSON debate log."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from debate_tool.runner import LOG_FILE_SUFFIX, LOG_FORMAT, LOG_VERSION

LEGACY_LOG_FILE_SUFFIX = "_debate_log.md"


def parse_legacy_markdown_log(path: Path) -> tuple[str, list[dict]]:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    title = "辩论"
    for line in lines:
        if line.startswith("# ") and "辩论日志" in line:
            title = line.lstrip("# ").replace(" 辩论日志", "").strip()
            break

    entries: list[dict] = []
    entry_pattern = re.compile(r"^### \[(\d+)\]\s*(.*)")

    i = 0
    while i < len(lines):
        match = entry_pattern.match(lines[i])
        if not match:
            i += 1
            continue

        seq = int(match.group(1))
        header = match.group(2).strip()
        tag = ""
        name = header
        if "📦 **Checkpoint**" in header:
            tag = "compact_checkpoint"
            name = header.replace("📦 **Checkpoint**", "").strip() or "Compact Checkpoint"
        elif "⚖️ **裁判总结**" in header:
            tag = "summary"
            name = header.replace("⚖️ **裁判总结**", "").strip() or "裁判"
        elif "🔍 **质询**" in header:
            tag = "cross_exam"
            name = header.replace("🔍 **质询**", "").strip() or "质询"
        elif "📝 **Meta**" in header:
            tag = "meta"
            name = header.replace("📝 **Meta**", "").strip() or "@meta"
        elif "🧠 **思考**" in header:
            tag = "thinking"
            name = header.replace("🧠 **思考**", "").strip() or "思考"

        ts = ""
        i += 1
        while i < len(lines) and lines[i] == "":
            i += 1
        if i < len(lines) and lines[i].startswith("*") and lines[i].endswith("*"):
            ts = lines[i].strip("*").strip()
            i += 1

        while i < len(lines) and lines[i] == "":
            i += 1

        content_lines: list[str] = []
        while i < len(lines) and not lines[i].startswith("---"):
            content_lines.append(lines[i])
            i += 1

        while content_lines and content_lines[-1] == "":
            content_lines.pop()

        entries.append(
            {
                "seq": seq,
                "ts": ts or datetime.now().isoformat(),
                "tag": tag,
                "name": name if name else f"Entry {seq}",
                "content": "\n".join(content_lines),
            }
        )

    if not entries:
        raise ValueError(f"{path} 不是可识别的旧版 Markdown 日志")

    return title, entries


def convert_markdown_log_to_json(source_path: Path, output_path: Path | None = None) -> Path:
    source_path = source_path.resolve()
    if output_path is None:
        if source_path.name.endswith(LEGACY_LOG_FILE_SUFFIX):
            base_name = source_path.name[: -len(LEGACY_LOG_FILE_SUFFIX)]
        else:
            base_name = source_path.stem
        output_path = source_path.with_name(f"{base_name}{LOG_FILE_SUFFIX}")
    else:
        output_path = output_path.resolve()

    title, entries = parse_legacy_markdown_log(source_path)
    payload = {
        "format": LOG_FORMAT,
        "version": LOG_VERSION,
        "title": title,
        "created_at": entries[0]["ts"] if entries else datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "entries": entries,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="临时转换器：将旧版 Markdown 辩论日志转换为 JSON 日志",
    )
    parser.add_argument("source", type=Path, help="旧版 Markdown 日志文件 (*_debate_log.md)")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 JSON 文件路径（默认生成 *_debate_log.json）",
    )
    args = parser.parse_args(argv)

    source_path = args.source.resolve()
    if not source_path.exists():
        print(f"❌ 文件不存在: {source_path}", file=sys.stderr)
        return 1

    try:
        target = convert_markdown_log_to_json(source_path, args.output)
    except Exception as exc:
        print(f"❌ 转换失败: {exc}", file=sys.stderr)
        return 1

    print(f"✅ 转换完成: {source_path} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
