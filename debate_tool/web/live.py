"""Flask Blueprint for live debate — SSE streaming + resume endpoints."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from queue import Queue, Empty

from flask import Blueprint, Response, jsonify, render_template, request

from debate_tool.runner import parse_topic_file
from debate_tool.session import (
    DebateSession,
    DebateEvent,
    SessionState,
    create_session,
    get_session,
    list_sessions,
)

debate_bp = Blueprint(
    "debate",
    __name__,
    url_prefix="/debate",
    template_folder="templates",
)

# Per-session SSE queues: session_id → list[Queue]
_sse_queues: dict[str, list[Queue]] = {}
_sse_lock = threading.Lock()


def _register_sse(session_id: str) -> Queue:
    q: Queue = Queue()
    with _sse_lock:
        _sse_queues.setdefault(session_id, []).append(q)
    return q


def _unregister_sse(session_id: str, q: Queue) -> None:
    with _sse_lock:
        qs = _sse_queues.get(session_id, [])
        if q in qs:
            qs.remove(q)


def _broadcast_event(session_id: str, event: DebateEvent) -> None:
    with _sse_lock:
        qs = _sse_queues.get(session_id, [])
        for q in qs:
            try:
                q.put_nowait(event)
            except Exception:
                pass


def _run_debate_in_thread(session: DebateSession) -> None:
    """Run the async debate engine in a background thread."""
    loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(session.run())
        except Exception as exc:
            print(f"[debate-live] Session {session.id} error: {exc}")
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True, name=f"debate-{session.id}")
    t.start()


# ── Page ─────────────────────────────────────────────────


@debate_bp.route("/")
def index():
    """Debate live viewer page."""
    return render_template("debate_live.html")


# ── Session management ───────────────────────────────────


@debate_bp.route("/sessions", methods=["GET"])
def api_list_sessions():
    return jsonify(sessions=list_sessions())


@debate_bp.route("/start", methods=["POST"])
def api_start():
    """Start a new debate session.

    Body: { topic_path: str }
    """
    data = request.get_json(silent=True) or {}

    topic_path_str = data.get("topic_path", "").strip()
    if not topic_path_str:
        return jsonify(error="topic_path is required"), 400

    topic_path = Path(topic_path_str).resolve()
    if not topic_path.exists():
        return jsonify(error=f"File not found: {topic_path}"), 404

    try:
        cfg = parse_topic_file(topic_path)
    except Exception as exc:
        return jsonify(error=f"Failed to parse topic: {exc}"), 400

    if "rounds" in data:
        cfg["rounds"] = int(data["rounds"])
    if "cross_exam" in data:
        cfg["cross_exam"] = int(data["cross_exam"])

    session = create_session(cfg, topic_path)

    # Wire SSE broadcast
    session.on_event(lambda ev: _broadcast_event(session.id, ev))

    # Run in background thread
    _run_debate_in_thread(session)

    return jsonify(success=True, session=session.to_dict())


@debate_bp.route("/<session_id>/status", methods=["GET"])
def api_status(session_id: str):
    session = get_session(session_id)
    if not session:
        return jsonify(error="Session not found"), 404
    return jsonify(session=session.to_dict())


@debate_bp.route("/resume", methods=["POST"])
def api_resume():
    """Resume a completed debate with additional rounds.

    Body: { topic_path, message?, rounds?, cross_exam?, guide?, no_judge? }
    """
    data = request.get_json(silent=True) or {}

    topic_path_str = data.get("topic_path", "").strip()
    if not topic_path_str:
        return jsonify(error="topic_path is required"), 400

    topic_path = Path(topic_path_str).resolve()
    if not topic_path.exists():
        return jsonify(error=f"File not found: {topic_path}"), 404

    log_path = topic_path.parent / f"{topic_path.stem}_debate_log.md"
    if not log_path.exists():
        return jsonify(error=f"No existing debate log found: {log_path}"), 404

    try:
        cfg = parse_topic_file(topic_path)
    except Exception as exc:
        return jsonify(error=f"Failed to parse topic: {exc}"), 400

    from debate_tool.runner import resume as do_resume

    message = data.get("message", "")
    extra_rounds = int(data.get("rounds", 1))
    cross_exam = bool(data.get("cross_exam", False))
    guide = data.get("guide", "")
    no_judge = bool(data.get("no_judge", False))

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                do_resume(
                    cfg,
                    topic_path,
                    message=message,
                    extra_rounds=extra_rounds,
                    cross_exam=cross_exam,
                    guide_prompt=guide,
                    judge_at_end=not no_judge,
                )
            )
        except Exception as exc:
            print(f"[debate-live] Resume error: {exc}")
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True, name="debate-resume")
    t.start()

    return jsonify(success=True, message="Resume started")


# ── SSE stream ───────────────────────────────────────────


@debate_bp.route("/<session_id>/stream", methods=["GET"])
def api_stream(session_id: str):
    """SSE endpoint for real-time debate events."""
    session = get_session(session_id)
    if not session:
        return jsonify(error="Session not found"), 404

    since = int(request.args.get("since", 0))
    q = _register_sse(session_id)

    def generate():
        try:
            # First, send any events already buffered
            for ev in session.get_events_since(since):
                yield ev.to_sse()

            # Then stream new events
            while True:
                try:
                    event = q.get(timeout=30)
                    yield event.to_sse()
                except Empty:
                    # Keepalive
                    yield ": keepalive\n\n"

                # Stop if session is done
                if session.state in (SessionState.DONE, SessionState.ERROR):
                    # Drain remaining events
                    while not q.empty():
                        try:
                            yield q.get_nowait().to_sse()
                        except Empty:
                            break
                    break
        finally:
            _unregister_sse(session_id, q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Log entries ──────────────────────────────────────────


@debate_bp.route("/<session_id>/log", methods=["GET"])
def api_log(session_id: str):
    """Get debate log entries (optionally since a seq number)."""
    session = get_session(session_id)
    if not session:
        return jsonify(error="Session not found"), 404

    since = int(request.args.get("since", 0))
    entries = session.log.get_entries_since(since)
    return jsonify(entries=entries, total=len(session.log.entries))


# ── Judge chat ───────────────────────────────────────────


@debate_bp.route("/<session_id>/judge-chat", methods=["POST"])
def api_judge_chat(session_id: str):
    """Chat with the judge."""
    session = get_session(session_id)
    if not session:
        return jsonify(error="Session not found"), 404

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify(error="Message is required"), 400

    include_in_context = data.get("include_in_context", False)

    # Run async chat in a new loop (we're in sync Flask)
    loop = asyncio.new_event_loop()
    try:
        reply = loop.run_until_complete(
            session.chat_with_judge(message, include_in_context=include_in_context)
        )
    finally:
        loop.close()

    return jsonify(
        success=True,
        reply=reply,
        chats=session.judge_chats,
    )


@debate_bp.route("/<session_id>/judge-chats", methods=["GET"])
def api_judge_chats(session_id: str):
    """Get judge chat history."""
    session = get_session(session_id)
    if not session:
        return jsonify(error="Session not found"), 404
    return jsonify(chats=session.judge_chats)


# ── Context management ───────────────────────────────────


@debate_bp.route("/<session_id>/context", methods=["GET"])
def api_get_context(session_id: str):
    """Get current context state (which entries are excluded)."""
    session = get_session(session_id)
    if not session:
        return jsonify(error="Session not found"), 404

    return jsonify(
        excluded_seqs=sorted(session.log.excluded_seqs),
        total_entries=len(session.log.entries),
        entries=[
            {
                "seq": e["seq"],
                "name": e["name"],
                "tag": e["tag"],
                "excluded": e["seq"] in session.log.excluded_seqs,
                "preview": e["content"][:200],
            }
            for e in session.log.entries
        ],
    )


@debate_bp.route("/<session_id>/context", methods=["POST"])
def api_set_context(session_id: str):
    """Set which entries are excluded from judge context.

    Body: { excluded_seqs: [1, 3, 5] }
    Or: { toggle: 3 }  (toggle single entry)
    """
    session = get_session(session_id)
    if not session:
        return jsonify(error="Session not found"), 404

    data = request.get_json(silent=True) or {}

    if "toggle" in data:
        seq = int(data["toggle"])
        excluded = session.log.toggle_excluded(seq)
        return jsonify(seq=seq, excluded=excluded)

    if "excluded_seqs" in data:
        seqs = set(int(s) for s in data["excluded_seqs"])
        session.log.set_excluded(seqs)
        return jsonify(excluded_seqs=sorted(session.log.excluded_seqs))

    return jsonify(error="Provide 'toggle' or 'excluded_seqs'"), 400


@debate_bp.route("/<session_id>/judge-chat/context", methods=["POST"])
def api_judge_chat_context(session_id: str):
    """Toggle whether a judge chat message is included in judge context.

    Body: { index: 0, in_context: true/false }
    """
    session = get_session(session_id)
    if not session:
        return jsonify(error="Session not found"), 404

    data = request.get_json(silent=True) or {}
    idx = int(data.get("index", -1))
    if idx < 0 or idx >= len(session.judge_chats):
        return jsonify(error="Invalid chat index"), 400

    session.judge_chats[idx]["in_context"] = data.get("in_context", False)
    return jsonify(success=True, chats=session.judge_chats)
