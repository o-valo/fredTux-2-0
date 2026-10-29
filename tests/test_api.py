import json
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

from fredtux.config import Config
from fredtux.interfaces.api import create_server


class FakeAgent:
    session_id = "api-test-session"

    def ask(self, text):
        return f"Antwort auf: {text}"

    def ask_stream(self, text):
        yield f"Antwort auf: {text}"


class ReasoningAgent(FakeAgent):
    """Schickt Denkausgabe und Marker über den events-Haken, dann den Text."""

    def ask_stream(self, text, events=None):
        if events is not None:
            events({"type": "reasoning", "content": "ich denke nach"})
            events({"type": "marker", "content": "[Runde 1]\n"})
        yield f"Antwort auf: {text}"


class SlowAgent(FakeAgent):
    """Antwortet erst nach ``delay`` Sekunden und zählt die Läufe."""

    def __init__(self, delay=0.0):
        self.delay = delay
        self.calls = 0

    def ask(self, text):
        self.calls += 1
        time.sleep(self.delay)
        return f"Antwort auf: {text}"

    def ask_stream(self, text):
        self.calls += 1
        time.sleep(self.delay)
        yield f"Antwort auf: {text}"


class ApiTests(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.config = Config(home=root, base_url="http://unused/v1", model="llm-bahnhof", api_key=None)
        self._servers = []
        self.server = self._start_server()

    def _start_server(self, config=None, agent=None):
        server = create_server(config or self.config, port=0, agent=agent or FakeAgent())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._servers.append((server, thread))
        return server

    def tearDown(self):
        for server, thread in self._servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def _post(self, server, payload, timeout=15):
        host, port = server.server_address[:2]
        request = urllib.request.Request(
            f"http://{host}:{port}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as fehler:
            return fehler.code, dict(fehler.headers), fehler.read()

    def url(self, path):
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}{path}"

    def test_health_and_models_are_openai_compatible(self):
        with urllib.request.urlopen(self.url("/health"), timeout=2) as response:
            health = json.loads(response.read())
        with urllib.request.urlopen(self.url("/v1/models"), timeout=2) as response:
            models = json.loads(response.read())
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["api"], "/v1")
        self.assertEqual(models["data"][0]["id"], "fredtux-2-0")

    def test_chat_completion_returns_openai_shape_and_session(self):
        payload = json.dumps(
            {"model": "fredtux-2-0", "messages": [{"role": "user", "content": "Hallo"}]}
        ).encode()
        request = urllib.request.Request(
            self.url("/v1/chat/completions"),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.loads(response.read())
        self.assertEqual(result["object"], "chat.completion")
        self.assertEqual(result["fredtux_session_id"], "api-test-session")
        self.assertEqual(result["choices"][0]["message"]["content"], "Antwort auf: Hallo")

    def test_streaming_returns_openai_sse_and_done(self):
        payload = json.dumps(
            {"model": "fredtux-2-0", "stream": True, "messages": [{"role": "user", "content": "Hallo"}]}
        ).encode()
        request = urllib.request.Request(
            self.url("/v1/chat/completions"),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.headers.get_content_type(), "text/event-stream")
            lines = response.read().decode().splitlines()
        self.assertIn("data: [DONE]", lines)
        events = [json.loads(line[6:]) for line in lines if line.startswith("data: {")]
        self.assertEqual("".join(event["choices"][0]["delta"].get("content", "") for event in events), "Antwort auf: Hallo")
        self.assertEqual(events[-1]["choices"][0]["finish_reason"], "stop")

    def test_reasoning_is_streamed_as_reasoning_content(self):
        server = self._start_server(agent=ReasoningAgent())
        payload = {
            "model": "fredtux-2-0",
            "stream": True,
            "messages": [{"role": "user", "content": "Hallo"}],
        }
        status, _, body = self._post(server, payload)
        self.assertEqual(status, 200)
        events = [json.loads(zeile[6:]) for zeile in body.decode().splitlines() if zeile.startswith("data: {")]
        denkt = "".join(e["choices"][0]["delta"].get("reasoning_content") or "" for e in events)
        self.assertIn("ich denke nach", denkt)
        self.assertIn("[Runde 1]", denkt)
        text = "".join(e["choices"][0]["delta"].get("content") or "" for e in events)
        self.assertEqual(text, "Antwort auf: Hallo")

    def test_queue_timeout_answers_429_instead_of_waiting_forever(self):
        """Der zweite Aufruf darf nicht eine Stunde am einen Laufplatz hängen."""
        agent = SlowAgent(delay=1.5)
        server = self._start_server(replace(self.config, queue_timeout=0.2), agent)
        payload = {"model": "fredtux-2-0", "messages": [{"role": "user", "content": "Hallo"}]}
        erster: dict = {}
        laeufer = threading.Thread(
            target=lambda: erster.update(
                zip(("status", "headers", "body"), self._post(server, payload))
            )
        )
        laeufer.start()
        time.sleep(0.3)  # der erste Lauf hält den Platz
        status, headers, body = self._post(server, payload)
        laeufer.join(timeout=15)
        self.assertEqual(status, 429)
        self.assertIn("Retry-After", headers)
        self.assertIn("FREDTUX_QUEUE_TIMEOUT", json.loads(body)["error"]["message"])
        self.assertEqual(erster["status"], 200)
        self.assertEqual(agent.calls, 1)

    def test_waiting_request_gets_the_slot_after_release(self):
        agent = SlowAgent(delay=0.4)
        server = self._start_server(replace(self.config, queue_timeout=10), agent)
        payload = {"model": "fredtux-2-0", "messages": [{"role": "user", "content": "Hallo"}]}
        ergebnisse: list = []
        threads = [
            threading.Thread(target=lambda: ergebnisse.append(self._post(server, payload)[0]))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertEqual(sorted(ergebnisse), [200, 200])
        self.assertEqual(agent.calls, 2)

    def test_disconnected_client_does_not_start_a_run(self):
        """Wer aufgibt, während er wartet, soll keine Rechenzeit verbrauchen."""
        agent = SlowAgent()
        server = self._start_server(replace(self.config, queue_timeout=10), agent)
        server.agent_lock.acquire()  # Laufplatz belegen, damit die Anfrage wartet
        try:
            host, port = server.server_address[:2]
            body = json.dumps(
                {"model": "fredtux-2-0", "messages": [{"role": "user", "content": "Hallo"}]}
            ).encode()
            sock = socket.create_connection((host, port), timeout=2)
            sock.sendall(
                b"POST /v1/chat/completions HTTP/1.1\r\nHost: test\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
            )
            time.sleep(0.2)  # Anfrage ist gelesen und wartet jetzt
            sock.close()  # Client gibt auf
            time.sleep(1.5)  # Warteschleife merkt es (Abfrage alle 0,5 s)
        finally:
            server.agent_lock.release()
        time.sleep(1.0)
        self.assertEqual(agent.calls, 0)

    def test_streaming_queue_timeout_reports_sse_error(self):
        agent = SlowAgent(delay=1.5)
        server = self._start_server(replace(self.config, queue_timeout=0.2), agent)
        belegt = {"model": "fredtux-2-0", "messages": [{"role": "user", "content": "Hallo"}]}
        gestreamt = {
            "model": "fredtux-2-0",
            "stream": True,
            "messages": [{"role": "user", "content": "Hallo"}],
        }
        laeufer = threading.Thread(target=lambda: self._post(server, belegt))
        laeufer.start()
        time.sleep(0.3)
        status, _, body = self._post(server, gestreamt)
        laeufer.join(timeout=15)
        text = body.decode()
        self.assertEqual(status, 200)  # SSE-Kopf ging schon raus
        self.assertIn("fredtux_error", text)
        self.assertIn("FREDTUX_QUEUE_TIMEOUT", text)
        self.assertIn("data: [DONE]", text)


if __name__ == "__main__":
    unittest.main()
