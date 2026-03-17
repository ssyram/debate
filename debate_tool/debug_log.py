"""调试日志模块：DebugLogger 类及相关工具函数。"""

import sys
import threading
from datetime import datetime
from pathlib import Path

# ── Debug 日志 ───────────────────────────────────────────

_DEBUG_MAX_BYTES = 10 * 1024 * 1024   # 10 MB 之后开始裁头
_DEBUG_TRIM_TO   =  5 * 1024 * 1024   # 裁到约 5 MB


class DebugLogger:
    """Debug 输出器：控制台（stderr）或单文件（轮转，10MB 限制）。"""

    def __init__(self, path: "Path | None"):
        self._path = path   # None = stderr
        self._lock = threading.Lock()

    def log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[DEBUG {ts}] {msg}\n"
        if self._path is None:
            print(line, end="", file=sys.stderr)
        else:
            with self._lock:
                with open(self._path, "ab") as f:
                    f.write(line.encode("utf-8", errors="replace"))
                if self._path.stat().st_size > _DEBUG_MAX_BYTES:
                    self._trim()

    def _trim(self) -> None:
        """Discard leading bytes so the file drops to ~5 MB."""
        try:
            data = self._path.read_bytes()
            cut = data.find(b"\n", _DEBUG_TRIM_TO)
            self._path.write_bytes(data[cut + 1:] if cut >= 0 else data[_DEBUG_TRIM_TO:])
        except Exception:
            pass


_debug_logger: "DebugLogger | None" = None


def init_debug_logging(target) -> None:
    """target: None=关闭,  True=stderr,  str/Path=输出到文件"""
    global _debug_logger
    if target is None:
        _debug_logger = None
    elif target is True:
        _debug_logger = DebugLogger(None)
    else:
        _debug_logger = DebugLogger(Path(target))


def dlog(msg: str) -> None:
    """Write a debug message (no-op when debug logging is disabled)."""
    if _debug_logger is not None:
        _debug_logger.log(msg)
