#!/usr/bin/env python3
"""Migrate debate-tool log from v1 to v2 format.

Usage:
    python3 scripts/migrate_v1_to_v2.py TOPIC_FILE LOG_FILE [--output OUTPUT]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from debate_tool.core import _build_initial_config
from debate_tool.runner import parse_topic_file


def migrate(topic_path: Path, log_path: Path, output_path: Path) -> None:
    # 1. 解析 topic 文件
    cfg = parse_topic_file(topic_path)
    topic_body = cfg.get("topic_body", "")

    # 2. 构建 initial_config（唯一入口）
    initial_config = _build_initial_config(cfg)

    # 3. 读取 v1 log
    with log_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    # 4. 注入 v2 字段
    payload["version"] = 2
    payload["topic"] = topic_body
    payload["initial_config"] = initial_config

    # 5. compact_checkpoint 兼容：补填 active: True
    for entry in payload.get("entries", []):
        if entry.get("tag") == "compact_checkpoint":
            content = entry.get("content", "")
            try:
                checkpoint = json.loads(content)
                state = checkpoint.get("state", {})
                for participant in state.get("participants", []):
                    if "active" not in participant:
                        participant["active"] = True
                entry["content"] = json.dumps(checkpoint, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass  # 旧格式纯文本，跳过

    # 6. 写出
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"迁移完成：{output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate v1 log to v2")
    parser.add_argument("topic_file", type=Path)
    parser.add_argument("log_file", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    output = args.output or args.log_file.with_name(
        args.log_file.stem + "_v2" + args.log_file.suffix
    )
    migrate(args.topic_file, args.log_file, output)


if __name__ == "__main__":
    main()
