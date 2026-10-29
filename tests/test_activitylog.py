import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from fredtux.activitylog import ActivityLog
from fredtux.config import Config
from fredtux.core import AgentCore
from fredtux.interfaces.api import create_server


def read_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class ActivityLogTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.path = self.root / "logs" / "fredtux.jsonl"

    def test_disabled_log_writes_nothing(self):
        log = ActivityLog(self.path, enabled=False)
        log.event("request.start", "s1", chars=3)
        self.assertFalse(self.path.exists())

    def test_enabled_log_writes_one_line_per_event_with_fields(self):
        log = ActivityLog(self.path, enabled=True)
        log.event("request.start", "s1", chars=3, stream=True)
        log.event("tool.call", "s1", tool="pwd", ok=True)
        records = read_records(self.path)
        self.assertEqual([record["event"] for record in records], ["request.start", "tool.call"])
        self.assertEqual(records[0]["session_id"], "s1")
        self.assertEqual(records[0]["chars"], 3)
        self.assertTrue(records[0]["stream"])
        self.assertTrue(records[1]["ok"])
        self.assertIn("timestamp", records[0])
        self.assertEqual(records[0]["level"], "info")

    def test_missing_directories_are_created(self):
        target = self.root / "tief" / "tiefer" / "fredtux.jsonl"
        log = ActivityLog(target, enabled=True)
        log.event("request.start", "s1")
        self.assertTrue(target.parent.is_dir())
        self.assertEqual(len(read_records(target)), 1)

    def test_info_level_drops_debug_records(self):
        log = ActivityLog(self.path, enabled=True, level="info")
        log.event("detail.debug", "s1", level="debug")
        log.event("detail.info", "s1", level="info")
        log.event("detail.error", "s1", level="error")
        self.assertEqual([record["event"] for record in read_records(self.path)], ["detail.info", "detail.error"])

    def test_debug_level_keeps_debug_records(self):
        log = ActivityLog(self.path, enabled=True, level="debug")
        log.event("detail.debug", "s1", level="debug")
        self.assertEqual([record["event"] for record in read_records(self.path)], ["detail.debug"])

    def test_unknown_level_falls_back_to_info(self):
        log = ActivityLog(self.path, enabled=True, level="laut")
        self.assertEqual(log.level, "info")
        log.event("detail.debug", "s1", level="debug")
        self.assertEqual(read_records(self.path), [])

    def test_newlines_are_escaped_so_each_record_stays_one_line(self):
        log = ActivityLog(self.path, enabled=True)
        log.event("note", "s1", text="erste\nzweite")
        record = read_records(self.path)[0]
        self.assertEqual(record["text"], "erste\\nzweite")
        self.assertEqual(len(self.path.read_text(encoding="utf-8").strip().splitlines()), 1)

    def test_long_values_are_capped_with_length_hint(self):
        log = ActivityLog(self.path, enabled=True)
        log.event("note", "s1", text="x" * 900)
        record = read_records(self.path)[0]
        self.assertTrue(record["text"].endswith("(900 Zeichen)"))
        self.assertLess(len(record["text"]), 900)

    def test_none_values_are_omitted(self):
        log = ActivityLog(self.path, enabled=True)
        log.event("note", "s1", a=1, b=None)
        record = read_records(self.path)[0]
        self.assertIn("a", record)
        self.assertNotIn("b", record)

    def test_unwritable_target_does_not_raise(self):
        blocked = self.root / "blocked"
        blocked.mkdir()
        log = ActivityLog(blocked, enabled=True)
        log.event("request.start", "s1")
        self.assertTrue(blocked.is_dir())


class LogConfigTests(unittest.TestCase):
    def test_switch_comes_from_quick_config(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "config.nd"
            path.write_text("FREDTUX_LOG=1\nFREDTUX_LOG_LEVEL=debug\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"FREDTUX_CONFIG_FILE": str(path), "FREDTUX_HOME": str(base / "home")},
                clear=True,
            ):
                config = Config.from_env()
            self.assertTrue(config.log_enabled)
            self.assertEqual(config.log_level, "debug")
            self.assertEqual(config.activity_log_path, config.home / "logs" / "fredtux.jsonl")

    def test_log_is_off_by_default(self):
        config = Config(home=Path(tempfile.mkdtemp()), base_url="http://unused/v1", model="fake", api_key=None)
        self.assertFalse(config.log_enabled)
        self.assertEqual(config.log_level, "info")
        self.assertTrue(str(config.activity_log_path).endswith("logs/fredtux.jsonl"))

    def test_custom_log_file_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "config.nd"
            target = base / "eigenes.log"
            path.write_text(f"FREDTUX_LOG=1\nFREDTUX_LOG_FILE={target}\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"FREDTUX_CONFIG_FILE": str(path), "FREDTUX_HOME": str(base / "home")},
                clear=True,
            ):
                config = Config.from_env()
            self.assertEqual(config.activity_log_path, target.resolve())


class SimpleLLM:
    def chat(self, history, schemas):
        return {"content": "Hallo zurück", "tool_calls": []}

    def chat_stream(self, history, schemas):
        yield {"type": "content", "content": "Hallo zurück"}
        yield {"type": "complete", "content": "Hallo zurück", "tool_calls": []}


class OneToolLLM(SimpleLLM):
    def __init__(self):
        self.calls = 0

    def chat(self, history, schemas):
        self.calls += 1
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "list_files", "arguments": '{"path":"."}'},
                }],
            }
        return {"content": "Fertig", "tool_calls": []}


def make_core(llm=None, **overrides) -> AgentCore:
    config = Config(
        home=Path(tempfile.mkdtemp()),
        base_url="http://unused/v1",
        model="fake",
        api_key=None,
        **overrides,
    )
    core = AgentCore(config, session_id="log-test")
    core.llm = llm or SimpleLLM()
    core.tools.call = lambda _name, _arguments: "Inhalt"
    return core


class CoreLoggingTests(unittest.TestCase):
    def test_ask_writes_start_round_and_end_records(self):
        core = make_core(log_enabled=True)
        self.assertEqual(core.ask("Hallo"), "Hallo zurück")
        records = read_records(core.config.activity_log_path)
        self.assertEqual([record["event"] for record in records], ["request.start", "llm.reply", "request.end"])
        self.assertFalse(records[0]["stream"])
        self.assertEqual(records[1]["tool_calls"], 0)
        self.assertEqual(records[-1]["status"], "ok")
        self.assertEqual(records[-1]["rounds"], 1)
        self.assertIn("duration_ms", records[1])

    def test_stream_records_mark_streaming(self):
        core = make_core(log_enabled=True)
        self.assertEqual("".join(core.ask_stream("Hallo")), "Hallo zurück")
        records = read_records(core.config.activity_log_path)
        self.assertTrue(records[0]["stream"])
        self.assertTrue(records[-1]["stream"])
        self.assertEqual(records[-1]["status"], "ok")

    def test_tool_calls_are_logged_with_duration_and_result(self):
        core = make_core(llm=OneToolLLM(), log_enabled=True)
        self.assertEqual(core.ask("Hallo"), "Fertig")
        records = read_records(core.config.activity_log_path)
        tool_records = [record for record in records if record["event"] == "tool.call"]
        self.assertEqual(len(tool_records), 1)
        self.assertEqual(tool_records[0]["tool"], "list_files")
        self.assertTrue(tool_records[0]["ok"])
        self.assertIn("duration_ms", tool_records[0])
        self.assertEqual(records[-1]["event"], "request.end")

    def test_llm_errors_are_logged_at_error_level(self):
        class BrokenLLM:
            def chat(self, history, schemas):
                raise RuntimeError("Modell kaputt")

            def chat_stream(self, history, schemas):
                raise RuntimeError("Modell kaputt")

        core = make_core(llm=BrokenLLM(), log_enabled=True)
        with self.assertRaises(RuntimeError):
            core.ask("Hallo")
        records = read_records(core.config.activity_log_path)
        errors = [record for record in records if record["event"] == "llm.error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["level"], "error")
        self.assertIn("Modell kaputt", errors[0]["error"])

    def test_disabled_log_creates_no_file(self):
        core = make_core(log_enabled=False)
        core.ask("Hallo")
        self.assertFalse(core.config.activity_log_path.exists())


class FakeAgent:
    session_id = "api-log-session"

    def ask(self, text):
        return f"Antwort auf: {text}"

    def ask_stream(self, text):
        yield f"Antwort auf: {text}"


class ApiLoggingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.config = Config(
            home=self.root,
            base_url="http://unused/v1",
            model="fake",
            api_key=None,
            log_enabled=True,
        )
        self.server = create_server(self.config, port=0, agent=FakeAgent())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.url = f"http://{host}:{port}/v1/chat/completions"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, payload: dict) -> bytes:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.read()

    def test_successful_request_is_logged(self):
        self.post({"model": "fredtux-2-0", "messages": [{"role": "user", "content": "Hallo"}]})
        records = read_records(self.config.activity_log_path)
        self.assertEqual(records[-1]["event"], "http.response")
        self.assertEqual(records[-1]["status"], 200)
        self.assertIn("duration_ms", records[-1])

    def test_rejected_request_is_logged(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.post({"model": "fredtux-2-0", "messages": []})
        records = read_records(self.config.activity_log_path)
        self.assertEqual(records[-1]["event"], "http.reject")
        self.assertEqual(records[-1]["status"], 400)

    def test_streaming_request_is_logged_with_chunk_count(self):
        self.post(
            {
                "model": "fredtux-2-0",
                "stream": True,
                "messages": [{"role": "user", "content": "Hallo"}],
            }
        )
        records = read_records(self.config.activity_log_path)
        self.assertEqual(records[-1]["event"], "http.response")
        self.assertTrue(records[-1]["stream"])
        self.assertEqual(records[-1]["chunks"], 1)


if __name__ == "__main__":
    unittest.main()
