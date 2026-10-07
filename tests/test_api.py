import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from fredtux.config import Config
from fredtux.interfaces.api import create_server


class FakeAgent:
    session_id = "api-test-session"

    def ask(self, text):
        return f"Antwort auf: {text}"

    def ask_stream(self, text):
        yield f"Antwort auf: {text}"


class ApiTests(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.config = Config(home=root, base_url="http://unused/v1", model="llm-bahnhof", api_key=None)
        self.server = create_server(self.config, port=0, agent=FakeAgent())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

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


if __name__ == "__main__":
    unittest.main()
