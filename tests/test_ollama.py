import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from fredtux.config import Config
from fredtux.llm import LLMClient, OllamaError


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class OllamaCheckTests(unittest.TestCase):
    def make_client(self, model="gemma4-26b-16GB-VRAM-Uncensored", timeout=0.1):
        return LLMClient(
            Config(
                home=Path(tempfile.gettempdir()) / "fredtux-test-home",
                base_url="http://unused/v1",
                model=model,
                api_key=None,
                ollama_url="http://192.168.50.10:11434",
                ollama_timeout=timeout,
            )
        )

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_checks_version_tags_and_loaded_models(self, urlopen):
        def response(request, timeout):
            self.assertEqual(timeout, 0.1)
            path = urlsplit(request.full_url).path
            if path == "/api/version":
                return FakeResponse({"version": "0.34.2"})
            if path == "/api/tags":
                return FakeResponse({"models": [{"name": "gemma4-26b-16GB-VRAM-Uncensored:latest"}]})
            if path == "/api/ps":
                return FakeResponse({"models": [{"name": "gemma4-26b-16GB-VRAM-Uncensored:latest"}]})
            self.fail(f"unerwarteter Endpunkt: {path}")

        urlopen.side_effect = response
        status = self.make_client().check_ollama()
        self.assertEqual(status.version, "0.34.2")
        self.assertEqual(status.model, "gemma4-26b-16GB-VRAM-Uncensored")
        self.assertEqual(status.loaded_models, ("gemma4-26b-16GB-VRAM-Uncensored:latest",))
        self.assertIn("Modell gemma4-26b-16GB-VRAM-Uncensored verfügbar", status.summary())

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_missing_model_reports_available_models_and_pull_command(self, urlopen):
        def response(request, timeout):
            path = urlsplit(request.full_url).path
            if path == "/api/version":
                return FakeResponse({"version": "0.34.2"})
            if path == "/api/tags":
                return FakeResponse({"models": [{"name": "gemma3:1b"}, {"name": "llama3.2:1b"}]})
            self.fail(f"/api/ps sollte bei fehlendem Modell nicht erreicht werden: {path}")

        urlopen.side_effect = response
        with self.assertRaises(OllamaError) as context:
            self.make_client().check_ollama()
        message = str(context.exception)
        self.assertIn("nicht installiert", message)
        self.assertIn("gemma3:1b, llama3.2:1b", message)
        self.assertIn("OLLAMA_HOST=http://192.168.50.10:11434 ollama pull", message)

    @patch("fredtux.llm.urllib.request.urlopen")
    def test_tags_timeout_has_actionable_message(self, urlopen):
        def response(request, timeout):
            if urlsplit(request.full_url).path == "/api/version":
                return FakeResponse({"version": "0.34.2"})
            raise TimeoutError("slow tags")

        urlopen.side_effect = response
        with self.assertRaisesRegex(OllamaError, r"Zeitüberschreitung.*0\.1 Sekunden"):
            self.make_client().check_ollama()


if __name__ == "__main__":
    unittest.main()
