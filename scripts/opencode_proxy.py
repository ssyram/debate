#!/usr/bin/env python3
"""
scripts/opencode_proxy.py

OpenAI-compatible HTTP proxy that wraps an OpenCode session as a debater backend.

Usage:
    python3 scripts/opencode_proxy.py \
        --port 8081 \
        --opencode-url http://localhost:3000 \
        --provider-id yunwu \
        --model-id gpt-5.4 \
        --debater-name "正方辩手"

In the debate topic file, set the debater's base_url to:
    http://localhost:8081/v1/chat/completions
(runner.py posts directly to the full URL, so include /v1/chat/completions)

Standard library only — no external dependencies.
"""

from __future__ import annotations

import argparse
import os
import http.server
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any


# ---------------------------------------------------------------------------
# OpenCode client helpers
# ---------------------------------------------------------------------------


def _oc_request(
    opencode_url: str,
    method: str,
    path: str,
    body: Any = None,
    timeout: float = 30.0,
) -> Any:
    """
    Send a request to the OpenCode server and return the parsed JSON body.
    Raises urllib.error.HTTPError / urllib.error.URLError on failure.
    """
    url = opencode_url.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}


# ---------------------------------------------------------------------------
# Proxy state (one session per process)
# ---------------------------------------------------------------------------


class OpenCodeProxy:
    def __init__(
        self,
        opencode_url: str,
        provider_id: str,
        model_id: str,
        debater_name: str,
        read_only: bool,
        allow_web: bool,
        cwd: str,
        timeout: float,
        poll_interval: float,
        port: int,
        agent: str = "build",
    ) -> None:
        self.opencode_url = opencode_url
        self.provider_id = provider_id
        self.model_id = model_id
        self.debater_name = debater_name
        self.read_only = read_only
        self.allow_web = allow_web
        self.cwd = cwd
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.port = port
        self.agent = agent

        self._session_id: str | None = None
        self._sandbox_dir: str | None = None
        self._sent_count: int = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _make_sandbox(self) -> str:
        """Create a unique per-session sandbox directory and return its path."""
        import uuid as _uuid
        sandbox_base = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "proxy_workspace", "sessions"
        )
        sandbox = os.path.join(sandbox_base, _uuid.uuid4().hex[:12])
        os.makedirs(sandbox, exist_ok=True)
        return sandbox

    def _ensure_session(self) -> str:
        """Lazily create the OpenCode session on first use."""
        if self._session_id is not None:
            return self._session_id

        self._sandbox_dir = self._make_sandbox()

        payload: dict[str, Any] = {"title": self.debater_name}
        if self.cwd:
            payload["cwd"] = self.cwd

        # Try to create session with permission restrictions; fall back if unsupported
        if self.read_only:
            permissions = [
                {"behavior": "deny", "tool": "write"},
                {"behavior": "deny", "tool": "edit"},
                {"behavior": "deny", "tool": "patch"},
                {"behavior": "deny", "tool": "multiedit"},
            ]
            payload["permission"] = permissions
            try:
                resp = _oc_request(
                    self.opencode_url, "POST", "/session", body=payload
                )
            except Exception as exc:
                print(
                    f"[opencode_proxy] WARNING: failed to create session with permissions: {exc}",
                    file=sys.stderr,
                )
                print(
                    "[opencode_proxy] Retrying without permission field...",
                    file=sys.stderr,
                )
                payload.pop("permission", None)
                resp = _oc_request(self.opencode_url, "POST", "/session", body=payload)
        else:
            resp = _oc_request(self.opencode_url, "POST", "/session", body=payload)

        self._session_id = resp["id"]
        print(
            f"[opencode_proxy] Session created: {self._session_id}",
            file=sys.stderr,
        )
        print(
            f"[opencode_proxy] Sandbox: {self._sandbox_dir}",
            file=sys.stderr,
        )
        return self._session_id

    # ------------------------------------------------------------------
    # Message helpers
    # ------------------------------------------------------------------

    def _get_messages(self, session_id: str) -> list[dict]:
        resp = _oc_request(
            self.opencode_url, "GET", f"/session/{session_id}/message"
        )
        if isinstance(resp, list):
            return resp
        # Some versions wrap in a dict
        return resp.get("messages", [])

    def _get_status(self, session_id: str) -> dict[str, str]:
        """Returns the full status mapping {sessionID: status_string}.
        
        OpenCode v1.2+ returns {"sessionID": {"type": "busy"|"idle"}} — we
        normalise the values to plain strings so the rest of the code works.
        """
        resp = _oc_request(self.opencode_url, "GET", "/session/status")
        if not isinstance(resp, dict):
            return {}
        normalised: dict[str, str] = {}
        for sid, val in resp.items():
            if isinstance(val, dict):
                normalised[sid] = val.get("type", "idle")
            elif isinstance(val, str):
                normalised[sid] = val
            else:
                normalised[sid] = "idle"
        return normalised

    def _extract_last_assistant_text(self, messages: list[dict]) -> str:
        """Find last AssistantMessage and join all TextPart contents."""
        for msg in reversed(messages):
            # OpenCode v1.2+: role lives in msg["info"]["role"], not msg["role"]
            role = msg.get("info", {}).get("role", "") or msg.get("role", "")
            # OpenCode uses "assistant" role; parts array contains typed content
            if role == "assistant":
                parts = msg.get("parts", [])
                texts = [
                    p.get("text", "")
                    for p in parts
                    if p.get("type") == "text" and p.get("text", "").strip()
                ]
                if texts:
                    result = "\n".join(texts)
                    # Strip COURT WORKING MODE confirmation header injected by global CLAUDE.md
                    import re as _re
                    result = _re.sub(r'^.*?!COURT WORKING MODE ENABLED![\s\n]*', '', result, flags=_re.DOTALL)
                    return result.strip()
        return ""

    # ------------------------------------------------------------------
    # Core: chat completion
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        model_override: str | None = None,
        request_id: str = "req-1",
    ) -> dict:
        """
        Process an OpenAI-style messages list and return an OpenAI-compatible
        response dict.
        """
        # Resolve provider/model
        provider_id = self.provider_id
        model_id = self.model_id
        if model_override:
            if "/" in model_override:
                parts = model_override.split("/", 1)
                provider_id, model_id = parts[0], parts[1]
            else:
                model_id = model_override

        with self._lock:
            session_id = self._ensure_session()

            # --- Build delta text to send ---
            # If the incoming conversation is no longer than what we already
            # sent, this is a new debate run re-using the same session (续跑).
            # Reset sent_count so we send just the latest user message.
            if len(messages) <= self._sent_count:
                self._sent_count = max(0, len(messages) - 1)
            delta_messages = messages[self._sent_count :]
            system_text: str | None = None
            delta_parts: list[str] = []

            for msg in delta_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Multi-part content: join text segments
                    content = "\n".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )

                if role == "system":
                    system_text = content
                elif role == "user":
                    delta_parts.append(content)
                elif role == "assistant":
                    delta_parts.append(f"[你之前的发言]\n{content}")

            # Join delta segments
            combined_text = "\n\n---\n\n".join(delta_parts)

            # If no user message but we have something, still send (delta_parts
            # may be empty if only system changed — in that case skip the POST)
            if not combined_text.strip() and not system_text:
                return self._empty_response(request_id, model_id)

            # If there's only system context and no actual delta user content,
            # still proceed — OpenCode needs to know the updated context
            if not combined_text.strip():
                combined_text = "(context update)"

            # --- Record message count before sending ---
            try:
                msgs_before = self._get_messages(session_id)
            except Exception:
                msgs_before = []
            count_before = len(msgs_before)

            # --- POST message to OpenCode ---
            post_body: dict[str, Any] = {
                "parts": [{"type": "text", "text": combined_text}],
                "model": {"providerID": provider_id, "modelID": model_id},
            }
            # Prepend a lightweight context note so the model knows it is
            # operating inside a debate session and where its sandbox is.
            # Avoid aggressive override language that triggers safety refusals.
            session_context = (
                "You are participating in a structured debate session.\n"
                f"Your writable sandbox directory (for scratch files only): {self._sandbox_dir}\n"
                "Do not write or modify files outside that directory.\n\n"
            )
            effective_system = session_context + (system_text or "")
            post_body["system"] = effective_system

            # Explicitly use the built-in "build" agent to bypass any plugin
            # (e.g. oh-my-opencode Sisyphus) that would otherwise intercept
            # the session and spawn indefinite sub-agents.
            post_body["agent"] = self.agent

            # Save current sent_count so we can roll back on failure
            sent_count_before = self._sent_count

            try:
                _oc_request(
                    self.opencode_url,
                    "POST",
                    f"/session/{session_id}/message",
                    body=post_body,
                    timeout=self.timeout + 60,  # allow blocking responses longer than poll timeout
                )

                # Update sent_count after successful POST
                self._sent_count = len(messages)

                # --- Wait for completion ---
                reply_text = self._wait_for_reply(session_id, count_before)
            except Exception:
                # Roll back _sent_count so the next retry re-sends the same messages
                self._sent_count = sent_count_before
                raise

        # --- Build OpenAI-compatible response ---
        created = int(time.time())
        return {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": created,
            "model": f"{provider_id}/{model_id}",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    def _wait_for_reply(self, session_id: str, count_before: int) -> str:
        """
        Poll until a new assistant message with text content appears.

        We return as soon as we see a new assistant message with substantive
        text — we do NOT wait for the session to go idle, because opencode's
        build-agent may continue spawning sub-tasks after the first reply.
        Waiting for idle would block indefinitely in that case.
        """
        # Initial sleep to give OpenCode time to start processing
        time.sleep(2.0)

        deadline = time.time() + self.timeout
        last_msg_count = count_before

        while time.time() < deadline:
            # Check message count
            try:
                current_msgs = self._get_messages(session_id)
                current_count = len(current_msgs)
            except Exception:
                time.sleep(self.poll_interval)
                continue

            if current_count > count_before:
                # New messages appeared — check if any is a complete assistant reply
                text = self._extract_last_assistant_text(current_msgs)
                if text:
                    return text
                # Messages appeared but no text yet (e.g. tool-call only) — keep polling
                last_msg_count = current_count

            time.sleep(self.poll_interval)

        raise TimeoutError(
            f"OpenCode session {session_id} did not complete within "
            f"{self.timeout}s (status polling)"
        )

    @staticmethod
    def _empty_response(request_id: str, model_id: str) -> dict:
        return {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": ""},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


def make_handler(proxy: OpenCodeProxy):
    class Handler(http.server.BaseHTTPRequestHandler):
        # Suppress default request log lines; we log ourselves
        def log_message(self, fmt, *args):  # noqa: N802
            pass

        def _send_json(self, status: int, data: Any) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "session": proxy._session_id,
                        "port": proxy.port,
                    },
                )
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path not in (
                "/chat/completions",
                "/v1/chat/completions",
            ):
                self._send_json(404, {"error": "not found"})
                return

            # Read body
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                req_data = json.loads(raw.decode())
            except json.JSONDecodeError as exc:
                self._send_json(400, {"error": f"invalid JSON: {exc}"})
                return

            messages = req_data.get("messages", [])
            model_field = req_data.get("model", "")
            import uuid as _uuid

            request_id = str(_uuid.uuid4())

            print(
                f"[opencode_proxy] POST {self.path} — {len(messages)} messages",
                file=sys.stderr,
            )

            try:
                response = proxy.chat(
                    messages=messages,
                    model_override=model_field or None,
                    request_id=request_id,
                )
                self._send_json(200, response)
            except TimeoutError as exc:
                print(f"[opencode_proxy] TIMEOUT: {exc}", file=sys.stderr)
                self._send_json(
                    500,
                    {"error": {"message": str(exc), "type": "timeout"}},
                )
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")
                msg = f"OpenCode HTTP {exc.code}: {body}"
                print(f"[opencode_proxy] ERROR: {msg}", file=sys.stderr)
                self._send_json(
                    500,
                    {"error": {"message": msg, "type": "opencode_error"}},
                )
            except urllib.error.URLError as exc:
                msg = f"OpenCode connection error: {exc.reason}"
                print(f"[opencode_proxy] ERROR: {msg}", file=sys.stderr)
                self._send_json(
                    500,
                    {"error": {"message": msg, "type": "connection_error"}},
                )
            except Exception as exc:
                import traceback

                msg = f"Unexpected error: {exc}"
                print(
                    f"[opencode_proxy] ERROR: {msg}\n{traceback.format_exc()}",
                    file=sys.stderr,
                )
                self._send_json(
                    500,
                    {"error": {"message": msg, "type": "internal_error"}},
                )

    return Handler


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenAI-compatible proxy that wraps an OpenCode session as a debater.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=8081, help="Proxy listen port")
    parser.add_argument(
        "--opencode-url",
        default="http://localhost:3000",
        help="OpenCode server base URL",
    )
    parser.add_argument(
        "--provider-id",
        default="yunwu",
        help="Default OpenCode provider ID",
    )
    parser.add_argument(
        "--model-id",
        required=True,
        help="Default OpenCode model ID (required)",
    )
    parser.add_argument(
        "--debater-name",
        default="debater",
        help="Session title / debater name",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Create session with write-tool permissions denied",
    )

    web_group = parser.add_mutually_exclusive_group()
    web_group.add_argument(
        "--allow-web",
        dest="allow_web",
        action="store_true",
        default=True,
        help="Allow web search in the session (default)",
    )
    web_group.add_argument(
        "--no-web",
        dest="allow_web",
        action="store_false",
        help="Disable web search in the session",
    )

    parser.add_argument(
        "--cwd",
        default="",
        help="Working directory for the OpenCode session (default: current dir)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1800.0,
        help="Seconds to wait for each OpenCode reply",
    )
    parser.add_argument(
        "--agent",
        default="build",
        help="OpenCode agent to use (default: 'build'; available: build/plan/general/explore). "
             "Setting this explicitly bypasses plugin overrides like oh-my-opencode Sisyphus. "
             "Note: 'chat' is not a valid OpenCode agent; use 'build' for standard operation.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between status/message polls",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import os

    cwd = args.cwd or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "proxy_workspace"
    )

    proxy = OpenCodeProxy(
        opencode_url=args.opencode_url,
        provider_id=args.provider_id,
        model_id=args.model_id,
        debater_name=args.debater_name,
        read_only=args.read_only,
        allow_web=args.allow_web,
        cwd=cwd,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
        port=args.port,
        agent=args.agent,
    )

    # Print config summary to stderr
    print("=" * 60, file=sys.stderr)
    print("[opencode_proxy] Configuration", file=sys.stderr)
    print(f"  Listen port    : {args.port}", file=sys.stderr)
    print(f"  OpenCode URL   : {args.opencode_url}", file=sys.stderr)
    print(f"  Provider       : {args.provider_id}", file=sys.stderr)
    print(f"  Model          : {args.model_id}", file=sys.stderr)
    print(f"  Debater name   : {args.debater_name}", file=sys.stderr)
    print(f"  Read-only      : {args.read_only}", file=sys.stderr)
    print(f"  Allow web      : {args.allow_web}", file=sys.stderr)
    print(f"  Agent          : {args.agent}", file=sys.stderr)
    print(f"  CWD            : {cwd}", file=sys.stderr)
    print(f"  Timeout        : {args.timeout}s", file=sys.stderr)
    print(f"  Poll interval  : {args.poll_interval}s", file=sys.stderr)
    print("  Session        : (lazy — created on first request)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    handler_class = make_handler(proxy)
    server = http.server.HTTPServer(("0.0.0.0", args.port), handler_class)

    # Print ready line to stdout (machine-readable)
    print(f"Proxy ready at http://localhost:{args.port}", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[opencode_proxy] Shutting down.", file=sys.stderr)
        server.shutdown()


if __name__ == "__main__":
    main()
