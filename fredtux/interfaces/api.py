"""OpenAI-kompatible HTTP-Schnittstelle für FredTux 2.0."""

from __future__ import annotations

import inspect
import json
import select
import socket
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any, Callable
from urllib.parse import urlsplit

from .. import __version__
from ..activitylog import ActivityLog, elapsed_ms
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
        # Wer den einzigen Laufplatz hat, seit wann und für wen – damit eine
        # abgewiesene Anfrage sagen kann, worauf sie gewartet hat.
        self.run_client: str | None = None
        self.run_started: float | None = None
        self.activity = ActivityLog(
            config.activity_log_path, config.log_enabled, config.log_level
        )


class FredTuxRequestHandler(BaseHTTPRequestHandler):
    server: FredTuxHTTPServer

    # Wie oft während des Wartens geprüft wird, ob der Client noch da ist.
    WAIT_POLL_S = 0.5

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
        self._request_started = time.monotonic()
        self._wait_ms: int | None = None
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
            chunks = 0
            self._start_sse()
            slot = self._acquire_run_slot()
            if slot != "ok":
                self._report_no_slot(slot, stream=True)
                return
            try:
                try:
                    if session_id:
                        agent = self.server.agent_factory(session_id)
                    else:
                        agent = self.server.default_agent
                    active_session = agent.session_id
                    # Denkausgabe und Marker mitschicken, wenn der Agent es kann.
                    sende_ereignis = self._reasoning_sender(completion_id, agent)
                    strom = (
                        agent.ask_stream(user_text, events=sende_ereignis)
                        if sende_ereignis is not None
                        else agent.ask_stream(user_text)
                    )
                    for chunk in strom:
                        chunks += 1
                        self._send_sse_chunk(completion_id, active_session, content=chunk)
                finally:
                    self._release_run_slot()
                self._send_sse_chunk(completion_id, active_session, finish_reason="stop")
                # Erst protokollieren, dann abschließen: der Datensatz steht auch
                # dann, wenn der Client die Verbindung sofort danach schließt.
                self._request_event(
                    "http.response", status=200, stream=True,
                    session=getattr(agent, "session_id", "-"), chunks=chunks,
                )
                self._send_sse_done()
            except (BrokenPipeError, ConnectionResetError):
                self._request_event("http.abort", status=499, stream=True, chunks=chunks)
                return
            except Exception as exc:  # Nach SSE-Start nur noch ein Fehlerereignis möglich.
                self._request_event(
                    "http.error", status=500, stream=True, chunks=chunks, error=str(exc)
                )
                self._send_sse_error(str(exc))
            return

        slot = self._acquire_run_slot()
        if slot != "ok":
            self._report_no_slot(slot, stream=False)
            return
        try:
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
        finally:
            self._release_run_slot()

        self._request_event("http.response", status=200, session=active_session, chars=len(answer))
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

    def _acquire_run_slot(self) -> str:
        """Holt den einen Laufplatz, aber nicht beliebig lange.

        Rückgabe: ``"ok"`` (Platz wird gehalten und muss mit
        :meth:`_release_run_slot` freigegeben werden), ``"timeout"`` (Zeitlimit
        erreicht) oder ``"gone"`` (Client hat vor dem Start aufgegeben).

        ``FREDTUX_QUEUE_TIMEOUT`` steuert die Wartezeit: ``< 0`` wartet
        unbegrenzt (altes Verhalten), ``0`` wartet nicht, sonst Sekunden.
        Während des Wartens wird regelmäßig geprüft, ob der Client noch da ist –
        ein aufgegebener Chat belegt sonst den Platz, ohne dass jemand die
        Antwort liest.
        """
        limit = self.server.config.queue_timeout
        deadline = None if limit < 0 else time.monotonic() + limit
        wartete_seit = time.monotonic()
        while True:
            if deadline is None:
                bekam = self.server.agent_lock.acquire(timeout=self.WAIT_POLL_S)
            else:
                rest = deadline - time.monotonic()
                if rest <= 0:
                    bekam = self.server.agent_lock.acquire(blocking=False)
                    if not bekam:
                        self._wait_ms = elapsed_ms(wartete_seit)
                        return "timeout"
                else:
                    bekam = self.server.agent_lock.acquire(timeout=min(self.WAIT_POLL_S, rest))
            if bekam:
                break
            if self._client_gone():
                self._wait_ms = elapsed_ms(wartete_seit)
                return "gone"
        self._wait_ms = elapsed_ms(wartete_seit)
        self.server.run_client = self.address_string()
        self.server.run_started = time.monotonic()
        if self._client_gone():  # Platz frei, aber niemand hört mehr zu.
            self._release_run_slot()
            return "gone"
        return "ok"

    def _release_run_slot(self) -> None:
        self.server.run_client = None
        self.server.run_started = None
        try:
            self.server.agent_lock.release()
        except RuntimeError:  # nicht gehalten – doppeltes Freigeben ist harmlos.
            pass

    def _report_no_slot(self, slot: str, stream: bool) -> None:
        """Meldet, dass diese Anfrage nicht startet – als SSE-Fehler oder JSON."""
        if slot == "gone":
            self._request_event("http.abort", status=499, reason="Client vor dem Lauf weg")
            return
        limit = self.server.config.queue_timeout
        belegt = ""
        if self.server.run_started is not None:
            belegt = (
                f" Belegt seit {int(time.monotonic() - self.server.run_started)} s"
                f" durch {self.server.run_client or 'eine andere Anfrage'}."
            )
        message = (
            f"FredTux ist belegt.{belegt} Diese Anfrage wartete {limit:g} s"
            " und wurde nicht gestartet (FREDTUX_QUEUE_TIMEOUT)."
        )
        if stream:
            self._request_event("http.busy", status=429, message=message)
            self._send_sse_error(message)
            return
        self._send_error_json(429, message, retry_after=max(1, int(limit) or 30))

    def _client_gone(self) -> bool:
        """True, wenn der Client die Verbindung schon geschlossen hat.

        Der Socket wird nur befragt, nicht gelesen (``MSG_PEEK``) und nicht
        blockierend: liegt nichts an, ist die Verbindung offen. Ein leeres
        ``recv`` heißt FIN – ein Lauf dafür wäre verschwendete Rechenzeit.
        """
        sock = getattr(self, "connection", None)
        if sock is None:
            return False
        try:
            bereit, _, _ = select.select([sock], [], [], 0)
        except (OSError, ValueError):
            return True
        if not bereit:
            return False
        try:
            return sock.recv(1, socket.MSG_PEEK) == b""
        except (BlockingIOError, InterruptedError):
            return False
        except OSError:
            return True

    def _request_event(self, kind: str, **fields: Any) -> None:
        """Schreibt ein HTTP-Ereignis ins Aktivitätsprotokoll und nach stdout.

        Die stdout-Zeile ist die Anfragezeile, die unter systemd in api.log
        landet – auch dann, wenn das Aktivitätsprotokoll ausgeschaltet ist.
        """
        started = getattr(self, "_request_started", None)
        if started is not None:
            fields.setdefault("duration_ms", elapsed_ms(started))
        wait_ms = getattr(self, "_wait_ms", None)
        if wait_ms is not None:
            fields.setdefault("wait_ms", wait_ms)
        session = self.headers.get("X-FredTux-Session-ID") or "-"
        self.server.activity.event(kind, session, client=self.address_string(), **fields)
        teile = [f"client={self.address_string()}", f"session={session}"]
        for key in ("status", "wait_ms", "duration_ms", "chunks", "chars", "reason"):
            if key in fields:
                teile.append(f"{key}={fields[key]}")
        print(
            f"FredTux-API {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {kind} "
            + " ".join(teile),
            flush=True,
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

    def _reasoning_sender(
        self, completion_id: str, agent: Any
    ) -> Callable[[dict[str, Any]], None] | None:
        """Rückkanal für Denkausgabe – nur für Agenten, die ``events`` anbieten.

        Ältere Agenten und Test-Doubles ohne diesen Haken werden unverändert
        gestreamt; die Schnittstelle bleibt also abwärtskompatibel.
        """
        try:
            parameter = inspect.signature(agent.ask_stream).parameters
        except (TypeError, ValueError):
            return None
        if "events" not in parameter:
            return None

        def sende(ereignis: dict[str, Any]) -> None:
            text = str(ereignis.get("content", ""))
            if text:
                self._send_sse_chunk(
                    completion_id, agent.session_id, reasoning=text
                )

        return sende

    def _send_sse_chunk(
        self,
        completion_id: str,
        session_id: str,
        content: str | None = None,
        finish_reason: str | None = None,
        reasoning: str | None = None,
    ) -> None:
        delta: dict[str, Any] = {"content": content} if content is not None else {}
        if reasoning is not None:
            delta["reasoning_content"] = reasoning
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

    def _send_error_json(
        self, status: int, message: str, retry_after: int | None = None
    ) -> None:
        self._request_event("http.reject", status=status, message=message)
        self._send_json(
            status,
            {"error": {"message": message, "type": "invalid_request_error", "code": status}},
            retry_after=retry_after,
        )

    def _send_json(
        self, status: int, payload: dict[str, Any], retry_after: int | None = None
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        line = format % args
        self.server.activity.event(
            "http.access", "-", level="debug", client=self.address_string(), line=line
        )
        print(f"FredTux-API {self.address_string()} {line}", flush=True)


def create_server(config: Config, host: str = "0.0.0.0", port: int = 8765, agent: AgentCore | None = None) -> FredTuxHTTPServer:
    return FredTuxHTTPServer((host, port), FredTuxRequestHandler, config, agent or AgentCore(config=config))


def serve(config: Config, host: str = "0.0.0.0", port: int = 8765) -> None:
    server = create_server(config, host, port)
    actual_host, actual_port = server.server_address[:2]
    # flush=True: unter systemd wird stdout in eine Datei umgeleitet und sonst
    # gepuffert – die Startmeldungen erschienen dann erst beim Prozessende.
    print(f"FredTux-API läuft auf http://{actual_host}:{actual_port}/v1", flush=True)
    print(f"OpenAI-Endpunkt: http://{actual_host}:{actual_port}/v1/chat/completions", flush=True)
    if config.log_enabled:
        print(f"Aktivitätsprotokoll: {config.activity_log_path} (Level {config.log_level})", flush=True)
    else:
        print("Aktivitätsprotokoll aus (FREDTUX_LOG=1 schaltet es ein).", flush=True)
    print("Beenden mit Strg+C.", flush=True)
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
