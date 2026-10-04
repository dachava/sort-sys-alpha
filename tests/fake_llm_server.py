"""Deterministic Ollama/OpenAI-compatible mock server, used by the M3+ LLM-tier
tests so CI never needs a real model. See CLAUDE.md's testing section.

Supports Ollama's native `/api/chat`, `/api/tags`, `/api/show`, and Lemonade's
OpenAI-compatible `/chat/completions`, `/models` -- the same handler answers
all of them from one swappable "scenario" (status code, JSON body, delay).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


@dataclass
class _Scenario:
    status: int = 200
    body: Any = None
    delay: float = 0.0


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # silence request logging in test output
        pass

    def do_GET(self) -> None:
        self._respond()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # drain the request body, unused by the fake
        self._respond()

    def _respond(self) -> None:
        scenario: _Scenario = self.server.scenario  # type: ignore[attr-defined]
        if scenario.delay:
            time.sleep(scenario.delay)
        payload = json.dumps(scenario.body).encode("utf-8")
        self.send_response(scenario.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class FakeLlmServer:
    """One scenario at a time; call a `set_*` method between assertions."""

    def __init__(self) -> None:
        self._httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.scenario = _Scenario(body={})  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address
        return f"http://{host}:{port}"

    def _set(self, body: Any, *, status: int = 200, delay: float = 0.0) -> None:
        self._httpd.scenario = _Scenario(status=status, body=body, delay=delay)  # type: ignore[attr-defined]

    def set_ollama_reply(self, content: str, *, status: int = 200, delay: float = 0.0) -> None:
        self._set({"message": {"content": content}}, status=status, delay=delay)

    def set_openai_reply(self, content: str, *, status: int = 200, delay: float = 0.0) -> None:
        self._set({"choices": [{"message": {"content": content}}]}, status=status, delay=delay)

    def set_raw_reply(self, body: Any, *, status: int = 200, delay: float = 0.0) -> None:
        self._set(body, status=status, delay=delay)

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
