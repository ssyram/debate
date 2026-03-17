"""日志 I/O 模块：日志路径构建、格式校验、加载与 Log 类。

从 runner.py 提取，不含 compact 逻辑或 LLM 调用。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from .core import parse_compact_checkpoint
from .compact_state import render_public_markdown

# ── 日志格式常量 ─────────────────────────────────────────

LOG_FORMAT = "debate-tool-log"
LOG_VERSION = 2
LOG_FILE_SUFFIX = "_debate_log.json"
SUMMARY_FILE_SUFFIX = "_debate_summary.md"


class LogFormatError(ValueError):
    """Raised when a JSON log file does not match the expected schema."""


def build_log_path(topic_path: Path) -> Path:
    return topic_path.parent / f"{topic_path.stem}{LOG_FILE_SUFFIX}"


def _validate_log_entries(entries: object, path: Path) -> list[dict]:
    if not isinstance(entries, list):
        raise LogFormatError(f"{path} 的 entries 字段必须是数组")

    normalized: list[dict] = []
    for idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise LogFormatError(f"{path} 的 entries[{idx}] 必须是对象")

        seq = entry.get("seq")
        ts = entry.get("ts")
        tag = entry.get("tag", "")
        name = entry.get("name")
        content = entry.get("content")

        if not isinstance(seq, int) or seq != idx:
            raise LogFormatError(f"{path} 的 entries[{idx}] seq 非法，必须从 1 连续递增")
        if not isinstance(ts, str) or not ts.strip():
            raise LogFormatError(f"{path} 的 entries[{idx}] ts 非法")
        if not isinstance(tag, str):
            raise LogFormatError(f"{path} 的 entries[{idx}] tag 非法")
        if not isinstance(name, str) or not name.strip():
            raise LogFormatError(f"{path} 的 entries[{idx}] name 非法")
        if not isinstance(content, str):
            raise LogFormatError(f"{path} 的 entries[{idx}] content 非法")

        e_normalized = {
            "seq": seq,
            "ts": ts,
            "tag": tag,
            "name": name,
            "content": content,
        }
        # 保留额外字段（如 compact_checkpoint 的 state）
        for k, v in entry.items():
            if k not in e_normalized:
                e_normalized[k] = v
        normalized.append(e_normalized)

    return normalized


def _load_json_log_payload(path: Path) -> tuple[dict, list[dict]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LogFormatError(f"{path} 不是合法 JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LogFormatError(f"{path} 顶层必须是对象")
    if payload.get("format") != LOG_FORMAT:
        raise LogFormatError(
            f"{path} format 非法，期望 {LOG_FORMAT!r}，实际 {payload.get('format')!r}"
        )
    if payload.get("version") != 2:
        print("❌ 日志格式不是 v2。请先运行迁移脚本：", file=sys.stderr)
        print("   python3 scripts/migrate_v1_to_v2.py TOPIC_FILE LOG_FILE", file=sys.stderr)
        sys.exit(1)
    if "topic" not in payload or "initial_config" not in payload:
        print("❌ v2 日志缺少 topic 或 initial_config 字段。", file=sys.stderr)
        sys.exit(1)

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise LogFormatError(f"{path} title 非法")

    entries = _validate_log_entries(payload.get("entries"), path)
    if not entries:
        raise LogFormatError(f"{path} entries 不能为空")
    return payload, entries


def _classify_file(path: Path):
    """识别文件是否为 JSON 日志。

    返回:
      ("log", log_obj)       — 成功 load 为 Log
      ("non_log", log_err)   — 文件存在但不是合法 JSON 日志
    """
    if not path.exists():
        return ("missing", FileNotFoundError(f"{path} 不存在"))
    try:
        log = Log.load_from_file(path)
        return ("log", log)
    except Exception as e:
        return ("non_log", e)


def identify_files(file_a: Path, file_b: Path) -> "tuple[Path, Path]":
    """识别两个文件中的 JSON 日志文件，返回 (log_path, topic_path)。

    规则：必须恰好有一个合法 JSON 日志文件；另一个文件只要存在即可视为 topic。
    """
    for path in (file_a, file_b):
        if not path.exists():
            print(f"❌ 文件不存在: {path}", file=sys.stderr)
            sys.exit(1)

    ra = _classify_file(file_a)
    rb = _classify_file(file_b)

    logs = [(p, r) for p, r in ((file_a, ra), (file_b, rb)) if r[0] == "log"]

    if len(logs) == 2:
        print("❌ 传入了两个日志文件，请提供一个日志文件和一个议题文件。", file=sys.stderr)
        sys.exit(1)

    if len(logs) == 0:
        _, err_a = ra
        _, err_b = rb
        print(
            "❌ 没有检测到合法的 JSON 日志文件，请提供一个 *_debate_log.json 日志文件和一个议题文件。\n"
            f"   {file_a}: {err_a}\n"
            f"   {file_b}: {err_b}",
            file=sys.stderr,
        )
        sys.exit(1)
    log_path = logs[0][0]
    topic_path = file_b if log_path == file_a else file_a
    print(f"  识别结果: log={log_path.name}  topic={topic_path.name}")
    return log_path, topic_path


# ── 日志 ──────────────────────────────────────────────────


class Log:
    def __init__(self, path: Path, title: str, *, topic: str = "", initial_config: dict | None = None):
        self.path = path
        self.title = title
        self.topic = topic                          # 新增：不可变辩题
        self.initial_config = initial_config or {}  # 新增：首次配置快照
        self.entries: list[dict] = []
        self._archived_entries: list[dict] = []

    def all_entries(self) -> list[dict]:
        return [*self._archived_entries, *self.entries]

    def _next_seq(self) -> int:
        all_entries = self.all_entries()
        return (all_entries[-1]["seq"] + 1) if all_entries else 1

    @classmethod
    def load_from_file(cls, path: Path) -> "Log":
        payload, all_entries = _load_json_log_payload(path)

        # Find last checkpoint — only load from there onward
        last_checkpoint_idx = -1
        for idx, e in enumerate(all_entries):
            if e["tag"] == "compact_checkpoint":
                last_checkpoint_idx = idx

        log = cls(
            path,
            payload["title"],
            topic=payload["topic"],
            initial_config=payload["initial_config"],
        )
        if last_checkpoint_idx >= 0:
            log._archived_entries = all_entries[:last_checkpoint_idx]
            log.entries = all_entries[last_checkpoint_idx:]
            print(
                f"  📦 从 checkpoint #{all_entries[last_checkpoint_idx]['seq']} 恢复，跳过 {last_checkpoint_idx} 条旧记录"
            )
        else:
            log.entries = all_entries

        return log

    def add(self, name: str, content: str, tag: str = "", flush: bool = True, extra: "dict | None" = None):
        e = {
            "seq": self._next_seq(),
            "ts": datetime.now().isoformat(),
            "tag": tag,
            "name": name,
            "content": content,
        }
        if extra:
            e.update(extra)
        self.entries.append(e)
        icon = {
            "summary": "⚖️ 裁判",
            "cross_exam": "🔍",
            "compact_checkpoint": "📦",
            "meta": "📝",
            "thinking": "🧠",
        }.get(tag, "💬")
        print(f"\n{'=' * 60}\n[{e['seq']}] {icon} {name}\n{'=' * 60}")
        t = content
        print(t[:800] + "\n...(见日志)" if len(t) > 800 else t)
        if flush:
            self._flush()

    def _flush(self):
        all_entries = self.all_entries()
        payload = {
            "format": LOG_FORMAT,
            "version": 2,
            "title": self.title,
            "topic": self.topic,
            "initial_config": self.initial_config,
            "created_at": all_entries[0]["ts"] if all_entries else datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "entries": all_entries,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def since(self, after_seq: int) -> str:
        # "thinking": CoT 内部过程不暴露给其他辩手
        # "summary": 裁判最终裁定不应反向影响辩手后续发言（含续跑场景）
        news = [
            e for e in self.entries
            if e["seq"] > after_seq and e.get("tag") not in ("thinking", "summary", "config_override")
        ]
        if not news:
            return "(无新内容)"
        return "\n\n".join(f"--- {e['name']} ---\n{e['content']}" for e in news)

    def compact(self) -> str:
        parts = []
        for e in self.entries:
            tag = f"[{e['tag'].upper()}] " if e["tag"] else ""
            if e.get("tag") == "compact_checkpoint":
                state = e.get("state") or parse_compact_checkpoint(e["content"]).get("state")
                t = render_public_markdown(state)[:1200] if state else e.get("content", "")[:1200]
            else:
                t = e["content"][:1200]
                if len(e["content"]) > 1200:
                    t += "...(截断)"
            parts.append(f"### [{e['seq']}] {tag}{e['name']}\n{t}")
        return "\n\n".join(parts)

    def get_last_compact_state(self) -> "dict | None":
        """倒序遍历 entries，找到最后一个 compact_checkpoint，解析并返回其 state。"""
        for e in reversed(self.entries):
            if e.get("tag") == "compact_checkpoint":
                state = e.get("state")
                if state is not None:
                    return state
                # 旧格式兼容：content 是 JSON 字符串
                parsed = parse_compact_checkpoint(e["content"])
                return parsed.get("state")
        return None

    def entries_since_seq(
        self, after_seq: int, exclude_tags: tuple = ("thinking", "summary", "config_override")
    ) -> "list[dict]":
        """返回 seq > after_seq 且 tag 不在 exclude_tags 的条目列表。"""
        return [
            e for e in self.all_entries()
            if e["seq"] > after_seq and e.get("tag") not in exclude_tags
        ]
