"""调试日志模块：DebugLogger 类及相关工具函数。

输出格式由文件扩展名决定：
  --debug=foo.json  → JSONL（每行一个 JSON 对象，含 type/ts/msg + 额外字段）
  --debug=foo.log   → 文本 [type ts] msg
  --debug           → stderr 文本 [type ts] msg
"""

import json as _json
import sys
import threading
from datetime import datetime
from pathlib import Path

_DEBUG_MAX_BYTES = 10 * 1024 * 1024
_DEBUG_TRIM_TO   =  5 * 1024 * 1024


class DebugLogger:

    def __init__(self, path: "Path | None", *, json_mode: bool = False):
        self._path = path
        self._json = json_mode
        self._lock = threading.Lock()

    def log(self, type_: str, msg: str, **fields) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if self._json:
            record = {"type": type_, "ts": ts, "msg": msg, **fields}
            line = _json.dumps(record, ensure_ascii=False) + "\n"
        else:
            line = f"[{type_} {ts}] {msg}\n"

        if self._path is None:
            print(line, end="", file=sys.stderr)
        else:
            with self._lock:
                with open(self._path, "ab") as f:
                    f.write(line.encode("utf-8", errors="replace"))
                if self._path.stat().st_size > _DEBUG_MAX_BYTES:
                    self._trim()

    def _trim(self) -> None:
        try:
            p = self._path
            assert p is not None
            data = p.read_bytes()
            cut = data.find(b"\n", _DEBUG_TRIM_TO)
            p.write_bytes(data[cut + 1:] if cut >= 0 else data[_DEBUG_TRIM_TO:])
        except Exception:
            pass


_debug_logger: "DebugLogger | None" = None


def init_debug_logging(target) -> None:
    """target: None=关闭,  True=stderr,  str/Path=输出到文件

    .json 扩展名自动启用 JSONL 模式。
    """
    global _debug_logger
    if target is None:
        _debug_logger = None
    elif target is True:
        _debug_logger = DebugLogger(None)
    else:
        p = Path(target)
        _debug_logger = DebugLogger(p, json_mode=(p.suffix.lower() == ".json"))


def dlog(type_or_msg: str, msg: str = "", **fields) -> None:
    """写入一条调试记录。

    两种调用方式（向后兼容）：
      dlog("some message")                     → type="debug", msg="some message"
      dlog("llm.request", "...", model=...,)   → type="llm.request", msg="...", + fields
    """
    if _debug_logger is None:
        return
    if not msg:
        _debug_logger.log("debug", type_or_msg)
    else:
        _debug_logger.log(type_or_msg, msg, **fields)
