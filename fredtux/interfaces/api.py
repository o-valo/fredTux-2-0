"""OpenAI-kompatible HTTP-Schnittstelle für FredTux 2.0."""

from __future__ import annotations

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

from .. import __version__
from ..config import Config
from ..core import AgentCore
from ..llm import LLMError


class FredTuxHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, config: Config, agent: AgentCore):
        super().__init__(server_address, handler_class)
        self.config = config
        self.default_agent = agent
        self.agent_factory = lambda session_id: AgentCore(config=config, session_id=session_id)
        self.agent_lock = Lock()


class FredTuxRequestHandler(BaseHTTPRequestHandler):
    server: FredTuxHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": "fredtux-2.0",
                    "version": __version__,
                    "api": "/v1",
                    "upstream": self.server.config.base_url,
                },
            )
            return
        if path == "/v1/models":
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.server.config.api_model,
                            "object": "model",
                            "created": 0,
                            "owned_by": "fredtux",
                        }
                    ],
                },
            )
            return
        self._send_error_json(404, f"Unbekannter Endpunkt: {path}")

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path != "/v1/chat/completions":
            self._send_error_json(404, f"Unbekannter Endpunkt: {path}")
            return
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._send_error_json(400, str(exc))
            return
        stream_requested = bool(payload.get("stream"))
        requested_model = payload.get("model")
        if requested_model not in (None, self.server.config.api_model, "fredtux-2.0"):
            self._send_error_json(
                400,
                f"Unbekanntes FredTux-Modell {requested_model!r}. Verfügbar: {self.server.config.api_model}.",
            )
            return

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            self._send_error_json(400, "messages muss eine nicht leere Liste sein.")
            return
        user_text = self._last_user_text(messages)
        if user_text is None:
            self._send_error_json(400, "messages muss einen user-Eintrag mit Text enthalten.")
            return

        session_id = payload.get("session_id") or self.headers.get("X-FredTux-Session-ID")
        if session_id is not None and (not isinstance(session_id, str) or not session_id):
            self._send_error_json(400, "session_id muss eine nicht leere Zeichenkette sein.")
            return

        if stream_requested:
            completion_id = f"chatcmpl-fredtux-{uuid.uuid4().hex}"
            self._start_sse()
            try:
                with self.server.agent_lock:
                    if session_id:
                        agent = self.server.agent_factory(session_id)
                    else:
                        agent = self.server.default_agent
                    active_session = agent.session_id
                    for chunk in agent.ask_stream(user_text):
                        self._send_sse_chunk(completion_id, active_session, content=chunk)
                self._send_sse_chunk(completion_id, active_session, finish_reason="stop")
                self._send_sse_done()
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:  # Nach SSE-Start nur noch ein Fehlerereignis möglich.
                self._send_sse_error(str(exc))
            return

        try:
            with self.server.agent_lock:
                if session_id:
                    agent = self.server.agent_factory(session_id)
                else:
                    agent = self.server.default_agent
                answer = agent.ask(user_text)
                active_session = agent.session_id
        except FileNotFoundError as exc:
            self._send_error_json(404, str(exc))
            return
        except LLMError as exc:
            self._send_error_json(502, str(exc))
            return
        except Exception as exc:  # Server bleibt bei einem einzelnen Fehler erreichbar.
            self._send_error_json(500, f"FredTux-interner Fehler: {type(exc).__name__}: {exc}")
            return

        self._send_json(
            200,
            {
                "id": f"chatcmpl-fredtux-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.server.config.api_model,
                "fredtux_session_id": active_session,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": answer},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length ist ungültig.") from exc
        if length <= 0 or length > 2_000_000:
            raise ValueError("Request-Body ist leer oder größer als 2 MB.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Ungültiges JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON-Objekt erwartet.")
        return payload

    @staticmethod
    def _last_user_text(messages: list[Any]) -> str | None:
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content
        return None

    def _start_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _send_sse_chunk(
        self, completion_id: str, session_id: str, content: str | None = None, finish_reason: str | None = None
    ) -> None:
        delta = {"content": content} if content is not None else {}
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.server.config.api_model,
            "fredtux_session_id": session_id,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        self._write_sse(payload)

    def _send_sse_done(self) -> None:
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _send_sse_error(self, message: str) -> None:
        self._write_sse({"error": {"message": message, "type": "fredtux_error"}})
        try:
            self._send_sse_done()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _write_sse(self, payload: dict[str, Any]) -> None:
        body = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": {"message": message, "type": "invalid_request_error", "code": status}})

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"FredTux-API {self.address_string()} {format % args}")


def create_server(config: Config, host: str = "0.0.0.0", port: int = 8765, agent: AgentCore | None = None) -> FredTuxHTTPServer:
    return FredTuxHTTPServer((host, port), FredTuxRequestHandler, config, agent or AgentCore(config=config))


def serve(config: Config, host: str = "0.0.0.0", port: int = 8765) -> None:
    server = create_server(config, host, port)
    actual_host, actual_port = server.server_address[:2]
    print(f"FredTux-API läuft auf http://{actual_host}:{actual_port}/v1")
    print(f"OpenAI-Endpunkt: http://{actual_host}:{actual_port}/v1/chat/completions")
    print("Beenden mit Strg+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFredTux-API wird beendet.")
    finally:
        server.server_close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="FredTux 2.0 OpenAI-kompatibler HTTP-Server")
    parser.add_argument("--host", default=None, help="Bind-Adresse; überschreibt FREDTUX_API_HOST")
    parser.add_argument("--port", type=int, default=None, help="Port; überschreibt FREDTUX_API_PORT")
    args = parser.parse_args()
    config = Config.from_env()
    serve(config, args.host or config.api_host, args.port or config.api_port)
