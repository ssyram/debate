#!/usr/bin/env python3
"""Convert JSON debate log back to legacy Markdown format for easy reading."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from debate_tool.log_io import LOG_FILE_SUFFIX, LOG_FORMAT, LOG_VERSION

LEGACY_LOG_FILE_SUFFIX = "_debate_log.md"


def _render_compact_state(state: dict) -> str:
    if not state:
        return "（无 state 数据）"
    lines = []
    topic = state.get("topic", {})
    if topic:
        lines.append(f"### 议题\n{topic.get('current_formulation', '')}")
        if topic.get("notes"):
            lines.append(f"> {topic['notes']}")
    axioms = state.get("axioms", [])
    if axioms:
        lines.append("### 共识（Axioms）")
        for a in axioms:
            lines.append(f"- {a}")
    disputes = state.get("disputes", [])
    if disputes:
        lines.append("### 争点（Disputes）")
        for d in disputes:
            lines.append(f"**[{d['id']}] {d['title']}**（{d['status']}）")
            for name, pos in d.get("positions", {}).items():
                lines.append(f"- {name}：{pos}")
    pruned = state.get("pruned_paths", [])
    if pruned:
        lines.append("### 已否决路径（Pruned Paths）")
        for p in pruned:
            lines.append(f"- [{p['id']}] {p['description']} → {p['reason']}")
    participants = state.get("participants", [])
    if participants:
        lines.append("### 辩手立场快照（Participants）")
        for p in participants:
            lines.append(f"#### {p['name']}（v{p.get('stance_version', '?')}）")
            if p.get("stance"):
                lines.append(p["stance"])
            claims = p.get("core_claims", [])
            if claims:
                lines.append("**核心主张：**")
                for c in claims:
                    lines.append(f"- [{c['id']}]（{c['status']}）{c['text']}")
            abandoned = p.get("abandoned_claims", [])
            if abandoned:
                lines.append("**已放弃：**")
                for a in abandoned:
                    lines.append(f"- ~~{a.get('original_text', a.get('text', ''))}~~ → {a.get('reason', '')}")
    return "\n\n".join(lines)


def _normalize_entries(entries: object, path: Path) -> list[dict]:
    if not isinstance(entries, list):
        raise ValueError(f"{path} 的 entries 字段必须是数组")

    normalized: list[dict] = []
    for idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"{path} 的 entries[{idx}] 必须是对象")

        seq = entry.get("seq")
        ts = entry.get("ts")
        tag = entry.get("tag", "")
        name = entry.get("name")
        content = entry.get("content")

        if not isinstance(seq, int) or seq != idx:
            raise ValueError(f"{path} 的 entries[{idx}] seq 非法，必须从 1 连续递增")
        if not isinstance(ts, str) or not ts.strip():
            raise ValueError(f"{path} 的 entries[{idx}] ts 非法")
        if not isinstance(tag, str):
            raise ValueError(f"{path} 的 entries[{idx}] tag 非法")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path} 的 entries[{idx}] name 非法")
        if not isinstance(content, str):
            raise ValueError(f"{path} 的 entries[{idx}] content 非法")

        normalized_entry: dict = {
            "seq": seq,
            "ts": ts,
            "tag": tag,
            "name": name,
            "content": content,
        }
        if "state" in entry:
            normalized_entry["state"] = entry["state"]
        normalized.append(normalized_entry)

    return normalized


def _load_json_log_payload(path: Path) -> tuple[dict, list[dict]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 不是合法 JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{path} 顶层必须是对象")
    if payload.get("format") != LOG_FORMAT:
        raise ValueError(
            f"{path} format 非法，期望 {LOG_FORMAT!r}，实际 {payload.get('format')!r}"
        )
    version = payload.get("version")
    if version not in (1, LOG_VERSION):
        raise ValueError(
            f"{path} version 非法，支持 1 或 {LOG_VERSION}，实际 {version!r}"
        )

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{path} title 非法")

    entries = _normalize_entries(payload.get("entries"), path)
    if not entries:
        raise ValueError(f"{path} entries 不能为空")

    return payload, entries


def _render_entry_header(name: str, tag: str) -> str:
    tag_to_prefix = {
        "summary": "⚖️ **裁判总结**",
        "cross_exam": "🔍 **质询**",
        "compact_checkpoint": "📦 **Checkpoint**",
        "meta": "📝 **Meta**",
        "thinking": "🧠 **思考**",
        "config_override": "⚙️ **配置变更**",
    }
    prefix = tag_to_prefix.get(tag, "")
    if not prefix:
        return name
    return f"{prefix} {name}" if name else prefix


def _render_markdown(payload: dict, entries: list[dict]) -> str:
    created_at = payload.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        created_at = entries[0]["ts"]

    lines = [
        f"# {payload['title']} 辩论日志",
        "",
        f"> {created_at}",
        "",
        "---",
        "",
    ]

    topic_body = payload.get("topic", "")
    if topic_body:
        lines.extend(
            [
                "## 原始辩题",
                "",
                topic_body,
                "",
                "---",
                "",
            ]
        )

    for entry in entries:
        header = _render_entry_header(entry["name"], entry.get("tag", ""))
        tag = entry.get("tag", "")
        content = entry["content"]
        if tag == "compact_checkpoint" and not content:
            content = _render_compact_state(entry.get("state", {}))
        if tag == "config_override":
            lines.extend(
                [
                    "",
                    "---",
                    "",
                    f"⚙️ **配置变更**：{content}",
                    "",
                    "---",
                    "",
                ]
            )
            continue
        lines.extend(
            [
                "",
                f"### [{entry['seq']}] {header}",
                "",
                f"*{entry['ts']}*",
                "",
                content,
                "",
                "---",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def convert_json_log_to_markdown(source_path: Path, output_path: Path | None = None) -> tuple[Path, str]:
    source_path = source_path.resolve()

    payload, entries = _load_json_log_payload(source_path)
    markdown = _render_markdown(payload, entries)

    if output_path is None:
        if source_path.name.endswith(LOG_FILE_SUFFIX):
            base_name = source_path.name[: -len(LOG_FILE_SUFFIX)]
        else:
            base_name = source_path.stem
        output_path = source_path.with_name(f"{base_name}{LEGACY_LOG_FILE_SUFFIX}")
    else:
        output_path = output_path.resolve()

    output_path.write_text(markdown, encoding="utf-8")
    return output_path, markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="将 JSON 辩论日志重新转换为 Markdown（便于自然语言阅读）",
    )
    parser.add_argument("source", type=Path, help="JSON 日志文件 (*_debate_log.json)")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 Markdown 文件路径（默认生成 *_debate_log.md）",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="转换后同时输出 Markdown 到标准输出",
    )
    args = parser.parse_args(argv)

    source_path = args.source.resolve()
    if not source_path.exists():
        print(f"❌ 文件不存在: {source_path}", file=sys.stderr)
        return 1

    try:
        target, markdown = convert_json_log_to_markdown(source_path, args.output)
    except Exception as exc:
        print(f"❌ 转换失败: {exc}", file=sys.stderr)
        return 1

    print(f"✅ 转换完成: {source_path} -> {target}")
    if args.stdout:
        print("\n" + markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
