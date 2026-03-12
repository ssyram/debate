"""DebateSession — event-driven debate engine with resume support.

Replaces the monolithic `runner.run()` with a stateful, observable session.
Human interaction is via resume (multiple runs + opinion injection).

States: IDLE → RUNNING → JUDGING → DONE
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from debate_tool.core import DEFAULT_EARLY_STOP_THRESHOLD, check_convergence
from debate_tool.runner import build_log_path, call_llm, run_cross_exam, Log


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class SessionState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    JUDGING = "judging"
    DONE = "done"
    ERROR = "error"


class EventType(str, Enum):
    # Lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_ERROR = "session_error"

    # Round events
    ROUND_START = "round_start"
    ROUND_END = "round_end"

    # Debater events
    DEBATER_START = "debater_start"
    DEBATER_DONE = "debater_done"

    # Cross-exam
    CROSS_EXAM_START = "cross_exam_start"
    CROSS_EXAM_DONE = "cross_exam_done"

    # Convergence
    CONVERGENCE_CHECK = "convergence_check"
    EARLY_STOP = "early_stop"

    # Judge
    JUDGE_START = "judge_start"
    JUDGE_DONE = "judge_done"
    JUDGE_CHAT_REPLY = "judge_chat_reply"

    # Log entry (generic — wraps any Log.add)
    LOG_ENTRY = "log_entry"


@dataclass
class DebateEvent:
    """A single observable event emitted by the session."""

    type: EventType
    data: dict[str, Any]
    ts: str = field(default_factory=lambda: datetime.now().isoformat())
    seq: int = 0  # filled by session

    def to_sse(self) -> str:
        """Format as SSE message."""
        payload = json.dumps(
            {
                "type": self.type.value,
                "data": self.data,
                "ts": self.ts,
                "seq": self.seq,
            },
            ensure_ascii=False,
        )
        return f"event: {self.type.value}\ndata: {payload}\n\n"


# ---------------------------------------------------------------------------
# EventLog — enhanced Log with event callbacks
# ---------------------------------------------------------------------------


class EventLog(Log):
    """Drop-in replacement for Log that emits DebateEvents on every add()."""

    def __init__(self, path: Path, title: str):
        super().__init__(path, title)
        self._callbacks: list[Callable[[DebateEvent], None]] = []
        # Track which entries are excluded from judge context
        self.excluded_seqs: set[int] = set()

    def on_event(self, cb: Callable[[DebateEvent], None]) -> None:
        self._callbacks.append(cb)

    def _emit(self, event: DebateEvent) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass  # Don't let callback errors break the debate

    def add(self, name: str, content: str, tag: str = "", flush: bool = True) -> None:
        """Override: add entry and emit LOG_ENTRY event."""
        e = {
            "seq": self._next_seq(),
            "ts": datetime.now().isoformat(),
            "tag": tag,
            "name": name,
            "content": content,
        }
        self.entries.append(e)
        icon = {
            "summary": "\u2696\ufe0f \u88c1\u5224",
            "cross_exam": "\U0001f50d",
            "compact_checkpoint": "\U0001f4e6",
        }.get(tag, "\U0001f4ac")
        print(f"\n{'=' * 60}\n[{e['seq']}] {icon} {name}\n{'=' * 60}")
        t = content
        print(t[:800] + "\n...(\u89c1\u65e5\u5fd7)" if len(t) > 800 else t)
        if flush:
            self._flush()

        self._emit(
            DebateEvent(
                type=EventType.LOG_ENTRY,
                data={
                    "seq": e["seq"],
                    "name": name,
                    "tag": tag,
                    "content": content,
                    "ts": e["ts"],
                },
            )
        )

    def compact_filtered(self) -> str:
        """Like compact() but excludes entries in self.excluded_seqs."""
        parts = []
        for e in self.entries:
            if e["seq"] in self.excluded_seqs:
                continue
            tag = f"[{e['tag'].upper()}] " if e["tag"] else ""
            t = e["content"][:1200]
            if len(e["content"]) > 1200:
                t += "...(\u622a\u65ad)"
            parts.append(f"### [{e['seq']}] {tag}{e['name']}\n{t}")
        return "\n\n".join(parts)

    def get_entries_since(self, after_seq: int = 0) -> list[dict]:
        """Return entries with seq > after_seq."""
        return [e for e in self.entries if e["seq"] > after_seq]

    def set_excluded(self, seqs: set[int]) -> None:
        """Set which entry sequences are excluded from judge context."""
        self.excluded_seqs = seqs

    def toggle_excluded(self, seq: int) -> bool:
        """Toggle exclusion. Returns new state (True=excluded)."""
        if seq in self.excluded_seqs:
            self.excluded_seqs.discard(seq)
            return False
        else:
            self.excluded_seqs.add(seq)
            return True


# ---------------------------------------------------------------------------
# DebateSession
# ---------------------------------------------------------------------------


class DebateSession:
    """Stateful, event-driven debate session with resume support."""

    def __init__(self, cfg: dict, topic_path: Path):
        self.id = uuid.uuid4().hex[:12]
        self.cfg = cfg
        self.topic_path = topic_path

        self.state = SessionState.IDLE
        self._event_seq = 0
        self._events: list[DebateEvent] = []
        self._callbacks: list[Callable[[DebateEvent], None]] = []

        # Judge chat history (separate from debate log)
        self.judge_chats: list[dict] = []  # [{role, content, in_context}]

        # Tracking
        self.current_round = 0
        self.total_rounds = cfg["rounds"]
        self.completed = False

        # Build output paths
        stem = topic_path.stem
        out_dir = topic_path.parent
        self.log = EventLog(build_log_path(topic_path), cfg["title"])
        self.summary_path = out_dir / f"{stem}_debate_summary.md"

        # Wire log events to session events
        self.log.on_event(self._on_log_event)

    # ── Event system ─────────────────────────────────────

    def on_event(self, cb: Callable[[DebateEvent], None]) -> None:
        self._callbacks.append(cb)

    def _emit(self, event: DebateEvent) -> None:
        self._event_seq += 1
        event.seq = self._event_seq
        self._events.append(event)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def _on_log_event(self, event: DebateEvent) -> None:
        """Forward log events through session event system."""
        self._event_seq += 1
        event.seq = self._event_seq
        self._events.append(event)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def get_events_since(self, after_seq: int = 0) -> list[DebateEvent]:
        return [e for e in self._events if e.seq > after_seq]

    # ── Judge chat ───────────────────────────────────────

    async def chat_with_judge(
        self, message: str, *, include_in_context: bool = False
    ) -> str:
        """Human chats with judge. Returns judge reply."""
        judge = self.cfg["judge"]
        debate_base_url = (self.cfg.get("base_url", "") or "").strip()
        debate_api_key = (self.cfg.get("api_key", "") or "").strip()
        judge_base_url = (judge.get("base_url", "") or debate_base_url).strip()
        judge_api_key = (judge.get("api_key", "") or debate_api_key).strip()

        # Build judge system prompt
        judge_instructions = self.cfg.get("judge_instructions", "")
        judge_sys = (
            f"\u4f60\u662f\u8fa9\u8bba\u88c1\u5224\uff08{judge['name']}\uff09\u3002"
            f"\u4eba\u7c7b\u89c2\u5bdf\u8005\u6b63\u5728\u4e0e\u4f60\u4ea4\u6d41\u3002\n\n"
            f"\u8fa9\u8bba\u4e0a\u4e0b\u6587\uff08\u7b5b\u9009\u540e\uff09\uff1a\n{self.log.compact_filtered()}\n\n"
            f"\u8bf7\u56de\u7b54\u89c2\u5bdf\u8005\u7684\u95ee\u9898\u3002"
        )

        # Store human message
        self.judge_chats.append(
            {
                "role": "human",
                "content": message,
                "in_context": include_in_context,
                "ts": datetime.now().isoformat(),
            }
        )

        reply = await call_llm(
            judge["model"],
            judge_sys,
            message,
            temperature=0.3,
            max_tokens=judge.get("max_tokens", 8000),
            timeout=self.cfg["timeout"],
            base_url=judge_base_url,
            api_key=judge_api_key,
        )

        self.judge_chats.append(
            {
                "role": "judge",
                "content": reply,
                "in_context": include_in_context,
                "ts": datetime.now().isoformat(),
            }
        )

        self._emit(
            DebateEvent(
                type=EventType.JUDGE_CHAT_REPLY,
                data={
                    "message": message,
                    "reply": reply,
                    "in_context": include_in_context,
                },
            )
        )

        return reply

    # ── Main debate loop ─────────────────────────────────

    async def run(self) -> None:
        self.state = SessionState.RUNNING
        cfg = self.cfg
        log = self.log
        topic = cfg["topic_body"]
        debaters = cfg["debaters"]
        judge = cfg["judge"]
        timeout = cfg["timeout"]
        max_reply_tokens = cfg["max_reply_tokens"]
        constraints = cfg["constraints"]
        cross_exam = cfg.get("cross_exam", 0)
        early_stop = cfg.get("early_stop", 0.0)
        debate_base_url = (cfg.get("base_url", "") or "").strip()
        debate_api_key = (cfg.get("api_key", "") or "").strip()

        # cross_exam_rounds computation
        if cross_exam < 0:
            cross_exam_rounds = set(range(1, self.total_rounds))
        else:
            cross_exam_rounds = set(range(1, min(cross_exam, self.total_rounds) + 1))

        self._emit(
            DebateEvent(
                type=EventType.SESSION_START,
                data={
                    "id": self.id,
                    "title": cfg["title"],
                    "rounds": self.total_rounds,
                    "debaters": [d["name"] for d in debaters],
                    "judge": judge["name"],
                },
            )
        )

        last_seq = 0
        had_cross_exam_last = False
        force_cross_exam_next = False

        try:
            rnd = 0
            while rnd < self.total_rounds:
                rnd += 1
                self.current_round = rnd

                self._emit(
                    DebateEvent(
                        type=EventType.ROUND_START,
                        data={"round": rnd, "total": self.total_rounds},
                    )
                )

                new_log = log.since(last_seq)

                # ── Phase A: parallel debater speeches ──
                if rnd == 1:
                    user_ctx = f"## \u8fa9\u8bba\u8bae\u9898\n\n{topic}"
                    task_desc = cfg["round1_task"]
                elif rnd == self.total_rounds:
                    user_ctx = f"## \u8fa9\u8bba\u8bae\u9898\n\n{topic}\n\n## \u4e0a\u8f6e\u8fa9\u8bba\u5185\u5bb9\n\n{new_log}"
                    task_desc = cfg["final_task"]
                else:
                    user_ctx = f"## \u8fa9\u8bba\u8bae\u9898\n\n{topic}\n\n## \u4e0a\u8f6e\u8fa9\u8bba\u5185\u5bb9\n\n{new_log}"
                    task_desc = cfg["middle_task"]

                if had_cross_exam_last:
                    task_desc = (
                        "\u9010\u6761\u56de\u5e94\u4f60\u6536\u5230\u7684\u8d28\u8be2\uff0c\u6307\u51fa\u5bf9\u65b9\u8d28\u7591\u4e2d\u7684\u4e0d\u5f53\u4e4b\u5904\uff0c"
                        "\u5e76\u53ef\u4fee\u6b63\u81ea\u5df1\u7684\u65b9\u6848\u3002400-600 \u5b57"
                    )

                # Inject human guide prompt if present
                if hasattr(self, "_pending_guide") and self._pending_guide:
                    task_desc += (
                        f"\n\n\u89c2\u5bdf\u8005\u6307\u5f15\uff1a{self._pending_guide}"
                    )
                    self._pending_guide = ""

                constraints_block = ""
                if constraints:
                    constraints_block = (
                        f"\n\n\u6838\u5fc3\u7ea6\u675f\uff1a\n{constraints}"
                    )

                # Emit debater_start for all, then gather
                for d in debaters:
                    self._emit(
                        DebateEvent(
                            type=EventType.DEBATER_START,
                            data={"name": d["name"], "model": d["model"], "round": rnd},
                        )
                    )

                async def speak(
                    d,
                    rnd=rnd,
                    task_desc=task_desc,
                    user_ctx=user_ctx,
                    constraints_block=constraints_block,
                ):
                    debater_base_url = (
                        d.get("base_url", "") or debate_base_url
                    ).strip()
                    debater_api_key = (d.get("api_key", "") or debate_api_key).strip()
                    sys_prompt = (
                        f"\u4f60\u662f\u300c{d['name']}\u300d\uff0c\u98ce\u683c\u4e3a\u300c{d['style']}\u300d\u3002\u7b2c {rnd} \u8f6e\u3002\n\n"
                        f"\u4efb\u52a1\uff1a{task_desc}{constraints_block}"
                    )
                    result = await call_llm(
                        d["model"],
                        sys_prompt,
                        user_ctx,
                        max_reply_tokens=max_reply_tokens,
                        timeout=timeout,
                        base_url=debater_base_url,
                        api_key=debater_api_key,
                    )
                    self._emit(
                        DebateEvent(
                            type=EventType.DEBATER_DONE,
                            data={"name": d["name"], "round": rnd},
                        )
                    )
                    return result

                mark = log.entries[-1]["seq"] if log.entries else 0
                results = await asyncio.gather(*[speak(d) for d in debaters])
                for d, resp in zip(debaters, results):
                    log.add(d["name"], resp)
                last_seq = mark

                # ── Phase B: early stop ──
                if early_stop and rnd < self.total_rounds:
                    converged, avg_sim = check_convergence(results, early_stop)
                    self._emit(
                        DebateEvent(
                            type=EventType.CONVERGENCE_CHECK,
                            data={
                                "avg_similarity": round(avg_sim, 4),
                                "threshold": early_stop,
                                "converged": converged,
                            },
                        )
                    )
                    if converged:
                        self._emit(
                            DebateEvent(
                                type=EventType.EARLY_STOP,
                                data={
                                    "round": rnd,
                                    "avg_similarity": round(avg_sim, 4),
                                },
                            )
                        )
                        break

                # ── Phase C: cross-exam ──
                had_cross_exam_last = False
                do_cross = (
                    rnd in cross_exam_rounds and rnd < self.total_rounds
                ) or force_cross_exam_next
                force_cross_exam_next = False

                if do_cross:
                    self._emit(
                        DebateEvent(
                            type=EventType.CROSS_EXAM_START,
                            data={"round": rnd},
                        )
                    )
                    await run_cross_exam(
                        debaters,
                        log,
                        topic,
                        rnd,
                        max_reply_tokens=max_reply_tokens,
                        timeout=timeout,
                        debate_base_url=debate_base_url,
                        debate_api_key=debate_api_key,
                    )
                    self._emit(
                        DebateEvent(
                            type=EventType.CROSS_EXAM_DONE,
                            data={"round": rnd},
                        )
                    )
                    had_cross_exam_last = True

                self._emit(
                    DebateEvent(
                        type=EventType.ROUND_END,
                        data={"round": rnd, "total": self.total_rounds},
                    )
                )

            # ══════════════════════════════════════════
            #  Judge summary
            # ══════════════════════════════════════════
            self.state = SessionState.JUDGING
            self._emit(
                DebateEvent(
                    type=EventType.JUDGE_START,
                    data={"judge": judge["name"], "model": judge["model"]},
                )
            )

            judge_instructions = cfg.get("judge_instructions", "")
            if not judge_instructions:
                judge_instructions = (
                    "\u8f93\u51fa\u7ed3\u6784\u5316 Summary\uff1a\n\n"
                    "## \u4e00\u3001\u5404\u8fa9\u624b\u8868\u73b0\u8bc4\u4ef7\uff08\u6bcf\u4f4d 2-3 \u53e5\uff09\n\n"
                    "## \u4e8c\u3001\u9010\u4e00\u88c1\u5b9a\n"
                    "\u5bf9\u6bcf\u4e2a\u8bae\u9898\u7ed9\u51fa\uff1a\n"
                    "- **\u88c1\u5b9a**\uff1a\u6700\u7ec8\u65b9\u6848\n"
                    "- **\u7406\u7531**\uff1a\u5f15\u7528\u8fa9\u8bba\u4e2d\u7684\u5173\u952e\u8bba\u636e\n"
                    "- **\u4f18\u5148\u7ea7**\uff1aP0 / P1 / P2\n\n"
                    "## \u4e09\u3001\u5b8c\u6574\u4fee\u6539\u6e05\u5355"
                )

            # Include judge chats marked as in_context
            judge_context_extra = ""
            in_ctx_chats = [c for c in self.judge_chats if c.get("in_context")]
            if in_ctx_chats:
                parts = []
                for c in in_ctx_chats:
                    role_label = (
                        "\u89c2\u5bdf\u8005" if c["role"] == "human" else "\u88c1\u5224"
                    )
                    parts.append(f"[{role_label}] {c['content']}")
                judge_context_extra = (
                    "\n\n## \u89c2\u5bdf\u8005\u4e0e\u88c1\u5224\u7684\u4ea4\u6d41\n\n"
                    + "\n\n".join(parts)
                )

            judge_sys = (
                f"\u4f60\u662f\u8fa9\u8bba\u88c1\u5224\uff08{judge['name']}\uff09\uff0c\u8d1f\u8d23\u505a\u51fa\u6700\u7ec8\u88c1\u5b9a\u3002\n\n"
                f"{judge_instructions}\n\n"
                f"\u88c1\u5b9a\u89c4\u5219\uff1a\n"
                f"- \u57fa\u4e8e\u4e8b\u5b9e\u548c\u6570\u636e\n"
                f"- \u5f15\u7528\u8fa9\u8bba\u4e2d\u7684\u5173\u952e\u8bba\u636e\n"
                f"- \u7b80\u6d01\u3001\u53ef\u64cd\u4f5c"
            )

            judge_base_url = (judge.get("base_url", "") or debate_base_url).strip()
            judge_api_key = (judge.get("api_key", "") or debate_api_key).strip()
            summary = await call_llm(
                judge["model"],
                judge_sys,
                f"\u5168\u90e8\u8fa9\u8bba\uff08\u7b5b\u9009\u540e\uff09\uff1a\n\n{log.compact_filtered()}{judge_context_extra}",
                temperature=0.3,
                max_tokens=judge.get("max_tokens", 8000),
                timeout=timeout,
                base_url=judge_base_url,
                api_key=judge_api_key,
            )
            log.add(judge["name"], summary, "summary")

            self.summary_path.write_text(
                f"# {cfg['title']} \u88c1\u5224\u603b\u7ed3\n\n> {datetime.now().isoformat()}\n\n{summary}",
                encoding="utf-8",
            )

            self._emit(
                DebateEvent(
                    type=EventType.JUDGE_DONE,
                    data={"judge": judge["name"]},
                )
            )

            self.state = SessionState.DONE
            self.completed = True
            self._emit(
                DebateEvent(
                    type=EventType.SESSION_END,
                    data={
                        "id": self.id,
                        "log_path": str(log.path),
                        "summary_path": str(self.summary_path),
                    },
                )
            )

        except Exception as exc:
            self.state = SessionState.ERROR
            self._emit(
                DebateEvent(
                    type=EventType.SESSION_ERROR,
                    data={"error": str(exc)},
                )
            )
            raise

    # ── Serialization ────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize session state for API responses."""
        return {
            "id": self.id,
            "state": self.state.value,
            "title": self.cfg.get("title", ""),
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "debaters": [d["name"] for d in self.cfg["debaters"]],
            "judge": self.cfg["judge"]["name"],
            "log_entries": len(self.log.entries),
            "excluded_seqs": sorted(self.log.excluded_seqs),
            "judge_chats": len(self.judge_chats),
            "completed": self.completed,
        }


# ---------------------------------------------------------------------------
# Session registry (in-process, single-server)
# ---------------------------------------------------------------------------

_sessions: dict[str, DebateSession] = {}


def create_session(cfg: dict, topic_path: Path) -> DebateSession:
    session = DebateSession(cfg, topic_path)
    _sessions[session.id] = session
    return session


def get_session(session_id: str) -> DebateSession | None:
    return _sessions.get(session_id)


def list_sessions() -> list[dict]:
    return [s.to_dict() for s in _sessions.values()]
