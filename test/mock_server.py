"""Local OpenAI-compatible mock server for debate-tool tests.

Starts a lightweight HTTP server that returns deterministic canned responses
based on prompt pattern matching. Routes are defined in mock_routes.py.

Usage:
    handle = start_mock_server()
    # handle.base_url  -> "http://127.0.0.1:<port>/v1/chat/completions"
    # handle.requests   -> list of recorded request dicts
    stop_mock_server(handle)
"""
from __future__ import annotations

import json
import socket
import threading
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler

from mock_routes import load_routes, match_route, reset_call_counters


@dataclass
class MockServerHandle:
    base_url: str
    requests: list[dict] = field(default_factory=list)
    _server: HTTPServer | None = None
    _thread: threading.Thread | None = None

    @property
    def embedding_url(self) -> str:
        return self.base_url.replace("/v1/chat/completions", "/v1/embeddings")


# ── Global handle ref (set per-server instance) ──────────────

_current_handle: MockServerHandle | None = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _MockHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress access logs

    def do_POST(self):
        global _current_handle
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._error(400, "Invalid JSON body")
            return

        if "/v1/embeddings" in self.path:
            self._handle_embeddings(data)
            return

        self._handle_chat(data)

    def _handle_chat(self, data):
        global _current_handle

        model = data.get("model", "")
        messages = data.get("messages", [])
        system = messages[0]["content"] if len(messages) > 0 else ""
        user = messages[1]["content"] if len(messages) > 1 else ""
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 6000)

        req_record = {
            "model": model,
            "system": system,
            "user": user,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if _current_handle:
            _current_handle.requests.append(req_record)

        # Route
        route_name, response_text = match_route(system, user, model)

        if route_name is None:
            # Unmatched — return as normal 200 chat completion with error marker
            # so production code doesn't crash on HTTP error, but test harness
            # can detect the marker in subprocess output.
            diag_payload = json.dumps({
                "system": system[:300],
                "user": user[:300],
                "model": model,
            }, ensure_ascii=False)
            error_content = f"[ERROR CALLING: NOT A SCHEDULED ROUTING, GIVEN PROMPT: {diag_payload}]"
            req_record["_route"] = "__unmatched__"
            resp = {
                "id": "mock-unmatched",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": error_content},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
            self._json_response(200, resp)
            return

        # Record which route matched
        req_record["_route"] = route_name

        # Return OpenAI-compatible response
        resp = {
            "id": "mock-001",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
        self._json_response(200, resp)

    def _handle_embeddings(self, data):
        global _current_handle

        model = data.get("model", "")
        inputs = data.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]

        # Record request
        if _current_handle:
            _current_handle.requests.append({
                "model": model,
                "_route": "embeddings",
                "input_count": len(inputs),
            })

        import hashlib
        dim = 1536
        base = [0.02] * dim

        embeddings = []
        for i, text in enumerate(inputs):
            h = hashlib.md5(text.encode("utf-8")).digest()
            vec = list(base)
            for j in range(min(len(h), dim)):
                vec[j] += (h[j] - 128) * 0.0001
            embeddings.append({"object": "embedding", "index": i, "embedding": vec})

        resp = {
            "object": "list",
            "data": embeddings,
            "model": model,
            "usage": {"prompt_tokens": 10, "total_tokens": 10},
        }
        self._json_response(200, resp)

    def _json_response(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, message: str):
        resp = {"error": {"message": message, "type": "mock_error", "code": code}}
        self._json_response(code, resp)


def start_mock_server() -> MockServerHandle:
    """Start mock server on a free port, return handle.

    Loads route tables from topic files on startup.
    """
    global _current_handle

    load_routes()
    port = _find_free_port()
    server = HTTPServer(("127.0.0.1", port), _MockHandler)
    handle = MockServerHandle(
        base_url=f"http://127.0.0.1:{port}/v1/chat/completions",
        _server=server,
    )
    _current_handle = handle

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    handle._thread = thread

    return handle


def stop_mock_server(handle: MockServerHandle):
    """Shutdown mock server cleanly."""
    global _current_handle
    if handle._server:
        handle._server.shutdown()
    if handle._thread:
        handle._thread.join(timeout=5)
    _current_handle = None
