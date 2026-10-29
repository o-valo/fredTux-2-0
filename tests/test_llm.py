import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from fredtux.config import Config
from fredtux.llm import LLMClient, LLMError


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class LLMErrorMessageTests(unittest.TestCase):
    def make_client(self, base_url="http://192.168.200.216:11434/v1", timeout=0.1):
        return LLMClient(
            Config(
                home=Path(tempfile.gettempdir()) / "fredtux-test-home",
                base_url=base_url,
                model="gemma4:12b",
                api_key=None,
                request_timeout=timeout,
            )
        )

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_chat_names_the_unreachable_endpoint(self, urlopen):
        urlopen.side_effect = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        with self.assertRaises(LLMError) as context:
            self.make_client().chat([{"role": "user", "content": "Hallo"}])
        message = str(context.exception)
        self.assertIn("http://192.168.200.216:11434/v1", message)
        self.assertIn("nicht erreichbar", message)
        self.assertIn("FREDTUX_BASE_URL", message)
        self.assertIn("--no-ollama-check", message)

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_chat_timeout_mentions_limit_and_config_key(self, urlopen):
        urlopen.side_effect = TimeoutError("timed out")
        with self.assertRaises(LLMError) as context:
            self.make_client().chat([{"role": "user", "content": "Hallo"}])
        message = str(context.exception)
        self.assertIn("Zeitüberschreitung nach 0.1 Sekunden", message)
        self.assertIn("FREDTUX_TIMEOUT", message)

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_chat_reports_http_status_and_server_message(self, urlopen):
        error = urllib.error.HTTPError(
            "http://host/v1/chat/completions", 404, "Not Found", {}, None
        )
        error.read = lambda: b'{"error":"model \\"gemma4:12b\\" not found"}'
        urlopen.side_effect = error
        with self.assertRaises(LLMError) as context:
            self.make_client().chat([{"role": "user", "content": "Hallo"}])
        message = str(context.exception)
        self.assertIn("HTTP 404", message)
        self.assertIn("not found", message)

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_chat_reports_broken_answer_with_endpoint(self, urlopen):
        urlopen.return_value = FakeResponse({"unexpected": True})
        with self.assertRaisesRegex(LLMError, r"Ungültige Antwort von .*/chat/completions"):
            self.make_client().chat([{"role": "user", "content": "Hallo"}])


class ChatEndpointCheckTests(unittest.TestCase):
    def make_client(self, base_url="http://192.168.200.216:11434/v1"):
        return LLMClient(
            Config(
                home=Path(tempfile.gettempdir()) / "fredtux-test-home",
                base_url=base_url,
                model="gemma4:12b",
                api_key=None,
            )
        )

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_reachable_endpoint_is_reported(self, urlopen):
        urlopen.return_value = FakeResponse({"object": "list", "data": []})
        message = self.make_client().check_chat_endpoint()
        self.assertIn("Chat-Endpunkt erreichbar", message)
        self.assertIn("http://192.168.200.216:11434/v1", message)
        self.assertEqual(urlopen.call_args.args[0].full_url, "http://192.168.200.216:11434/v1/models")
        self.assertLessEqual(urlopen.call_args.kwargs["timeout"], 10.0)

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_http_error_still_counts_as_reachable(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError("http://host/v1/models", 404, "Not Found", {}, None)
        self.assertIn("Chat-Endpunkt erreichbar", self.make_client().check_chat_endpoint())

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_unreachable_endpoint_stops_the_start_with_a_hint(self, urlopen):
        urlopen.side_effect = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        with self.assertRaises(LLMError) as context:
            self.make_client().check_chat_endpoint()
        message = str(context.exception)
        self.assertIn("http://192.168.200.216:11434/v1", message)
        self.assertIn("OLLAMA_HOST=0.0.0.0", message)


class FakeStream:
    """Antwortobjekt, das sich zeilenweise lesen lässt (SSE)."""

    def __init__(self, zeilen):
        self.zeilen = [z.encode("utf-8") for z in zeilen]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.zeilen)


class DenkausgabeTests(unittest.TestCase):
    def make_client(self):
        return LLMClient(
            Config(
                home=Path(tempfile.gettempdir()) / "fredtux-test-home",
                base_url="http://192.168.200.216:11434/v1",
                model="gemma4:12b",
                api_key=None,
                request_timeout=5,
            )
        )

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_stream_reicht_denkausgabe_unter_beiden_feldnamen_weiter(self, urlopen):
        urlopen.return_value = FakeStream([
            'data: {"choices":[{"delta":{"reasoning_content":"erst "}}]}',
            'data: {"choices":[{"delta":{"reasoning":"denken"}}]}',
            'data: {"choices":[{"delta":{"content":"Antwort"}}]}',
            'data: [DONE]',
        ])
        ereignisse = list(self.make_client().chat_stream([{"role": "user", "content": "Hallo"}]))
        arten = [e["type"] for e in ereignisse]
        self.assertEqual(arten, ["reasoning", "reasoning", "content", "complete"])
        denkt = "".join(e["content"] for e in ereignisse if e["type"] == "reasoning")
        self.assertEqual(denkt, "erst denken")
        self.assertEqual(ereignisse[-1]["content"], "Antwort")

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_chat_nimmt_denkausgabe_mit(self, urlopen):
        urlopen.return_value = FakeResponse(
            {"choices": [{"message": {"content": "Antwort", "reasoning_content": "weil"}}]}
        )
        antwort = self.make_client().chat([{"role": "user", "content": "Hallo"}])
        self.assertEqual(antwort["content"], "Antwort")
        self.assertEqual(antwort["reasoning"], "weil")


if __name__ == "__main__":
    unittest.main()
