import tempfile
import unittest
from pathlib import Path

from fredtux.config import Config
from fredtux.core import AgentCore


class FailingToolLLM:
    def __init__(self):
        self.calls = 0

    def _reply(self):
        self.calls += 1
        return {
            "content": "",
            "tool_calls": [{
                "id": f"call-{self.calls}",
                "type": "function",
                "function": {"name": "execute_command", "arguments": '{"command":"pwd"}'},
            }],
        }

    def chat(self, history, schemas):
        return self._reply()

    def chat_stream(self, history, schemas):
        yield {"type": "complete", "content": "", "tool_calls": self._reply()["tool_calls"]}


def make_core(llm=None, tool_result="FEHLER im Werkzeug: absichtlich fehlgeschlagen", **overrides):
    root = Path(tempfile.mkdtemp())
    config = Config(
        home=root,
        base_url="http://unused/v1",
        model="fake",
        api_key=None,
        **overrides,
    )
    core = AgentCore(config, session_id="tool-loop-test")
    core.llm = llm or FailingToolLLM()
    resolve = tool_result if callable(tool_result) else (lambda _name, _arguments: tool_result)
    core.tools.call = resolve
    return core


class ToolLoopTests(unittest.TestCase):
    def make_core(self, **kwargs):
        return make_core(**kwargs)

    def test_system_prompt_contains_coding_loop_rules(self):
        core = self.make_core()
        prompt = core.system_prompt()
        self.assertIn("Verbindliche Regeln", prompt)
        self.assertIn("Nach zwei identischen Werkzeugfehlern", prompt)
        self.assertIn("run_coding_command", prompt)

    def test_ask_stops_after_repeated_tool_failure(self):
        core = self.make_core()
        result = core.ask("Test")
        self.assertIn("mehrfach", result)
        self.assertEqual(core.llm.calls, 2)
        self.assertNotIn("Maximale Anzahl", result)

    def test_stream_stops_after_repeated_tool_failure(self):
        core = self.make_core()
        result = list(core.ask_stream("Test"))
        self.assertTrue(any("mehrfach" in item for item in result))
        self.assertEqual(core.llm.calls, 2)
        self.assertNotIn("Maximale Anzahl", "".join(result))

    def test_tool_errors_are_written_to_live_log(self):
        core = self.make_core()
        core.ask("Test")
        log_path = core.config.error_log_path
        self.assertTrue(log_path.is_file())
        records = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(len(records), 2)
        self.assertIn('"category":"tool"', records[0])
        self.assertIn("absichtlich fehlgeschlagen", records[0])
        self.assertTrue(log_path.parent.is_dir())


class ReloadRulesTests(unittest.TestCase):
    def make_core(self, rules: str):
        root = Path(tempfile.mkdtemp())
        config = Config(home=root, base_url="http://unused/v1", model="fake", api_key=None)
        core = AgentCore(config, session_id="reload-rules-test")
        rules_path = root / "CODING_AGENT.md"
        rules_path.write_text(rules, encoding="utf-8")
        core.rules_path = rules_path
        core.history = [{"role": "system", "content": core.system_prompt()}]
        return core

    def test_reload_rules_picks_up_changed_file(self):
        core = self.make_core("Regel eins.\n")
        self.assertIn("Regel eins.", core.history[0]["content"])
        core.rules_path.write_text("Regel eins.\nRegel zwei.\n", encoding="utf-8")
        result = core.tools.call("reload_rules", "{}")
        self.assertIn("neu geladen", result)
        self.assertIn("Regel zwei.", core.history[0]["content"])
        self.assertEqual(core.history[0]["role"], "system")

    def test_reload_rules_without_change_reports_unchanged(self):
        core = self.make_core("Regel eins.\n")
        result = core.tools.call("reload_rules", "{}")
        self.assertIn("unverändert", result)

    def test_reload_rules_without_rules_file_keeps_base_prompt(self):
        core = self.make_core("Regel eins.\n")
        core.rules_path.unlink()
        result = core.tools.call("reload_rules", "{}")
        self.assertIn("neu geladen", result)
        self.assertNotIn("Verbindliche Coding-Regeln", core.history[0]["content"])
        self.assertIn("Du bist FredTux", core.history[0]["content"])

    def test_reload_rules_without_system_message_inserts_one(self):
        core = self.make_core("Regel eins.\n")
        core.history = [{"role": "user", "content": "Hallo"}]
        result = core.tools.call("reload_rules", "{}")
        self.assertIn("neu geladen", result)
        self.assertIn("Regel eins.", core.history[0]["content"])
        self.assertEqual(core.history[0]["role"], "system")
        self.assertEqual(core.history[1]["role"], "user")

    def test_reload_rules_is_offered_to_the_model(self):
        core = self.make_core("Regel eins.\n")
        names = [schema["function"]["name"] for schema in core.tools.schemas()]
        self.assertIn("reload_rules", names)

    def test_reload_rules_keeps_the_rest_of_the_conversation(self):
        core = self.make_core("Regel eins.\n")
        core.history.append({"role": "user", "content": "Frage"})
        core.history.append({"role": "assistant", "content": "Antwort"})
        core.rules_path.write_text("Regel zwei.\n", encoding="utf-8")
        core.tools.call("reload_rules", "{}")
        self.assertEqual([m["role"] for m in core.history], ["system", "user", "assistant"])
        self.assertEqual(core.history[1]["content"], "Frage")
        self.assertEqual(core.history[2]["content"], "Antwort")


class ManyToolRoundsLLM:
    """Modell, das erst viele erfolgreiche Werkzeugaufrufe fordert, dann antwortet."""

    def __init__(self, tool_rounds: int):
        self.tool_rounds = tool_rounds
        self.calls = 0

    def _reply(self):
        self.calls += 1
        if self.calls <= self.tool_rounds:
            return {
                "content": "",
                "tool_calls": [{
                    "id": f"call-{self.calls}",
                    "type": "function",
                    "function": {"name": "write_file", "arguments": f'{{"path":"datei-{self.calls}.txt"}}'},
                }],
            }
        return {"content": "Alle Dateien geschrieben.", "tool_calls": []}

    def chat(self, history, schemas):
        return self._reply()

    def chat_stream(self, history, schemas):
        reply = self._reply()
        if reply["content"]:
            yield {"type": "content", "content": reply["content"]}
        yield {"type": "complete", "content": reply["content"], "tool_calls": reply["tool_calls"]}


class EndlessToolLLM:
    """Modell, das dauerhaft denselben erfolgreichen Werkzeugaufruf wiederholt."""

    def __init__(self):
        self.calls = 0

    def _reply(self):
        self.calls += 1
        return {
            "content": "",
            "tool_calls": [{
                "id": f"call-{self.calls}",
                "type": "function",
                "function": {"name": "list_files", "arguments": '{"path":"."}'},
            }],
        }

    def chat(self, history, schemas):
        return self._reply()

    def chat_stream(self, history, schemas):
        yield {"type": "complete", "content": "", "tool_calls": self._reply()["tool_calls"]}


class ToolLoopBudgetTests(unittest.TestCase):
    def test_many_successful_tool_rounds_do_not_abort(self):
        core = make_core(llm=ManyToolRoundsLLM(12), tool_result="Datei geschrieben.")
        self.assertEqual(core.ask("Schreibe 12 Dateien."), "Alle Dateien geschrieben.")
        self.assertEqual(core.llm.calls, 13)

    def test_stream_allows_many_successful_tool_rounds(self):
        core = make_core(llm=ManyToolRoundsLLM(12), tool_result="Datei geschrieben.")
        chunks = list(core.ask_stream("Schreibe 12 Dateien."))
        self.assertIn("Alle Dateien geschrieben.", "".join(chunks))
        self.assertNotIn("Maximale Anzahl", "".join(chunks))

    def test_endless_successful_tool_calls_stop_at_total_round_limit(self):
        core = make_core(llm=EndlessToolLLM(), tool_result="Inhalt", max_total_rounds=5, max_idle_rounds=99)
        result = core.ask("Endlosschleife.")
        self.assertIn("Maximale Anzahl von Werkzeugschleifen erreicht", result)
        self.assertIn("Runden gesamt=5", result)
        self.assertIn("list_files", result)

    def test_stream_endless_successful_tool_calls_stop_at_total_round_limit(self):
        core = make_core(llm=EndlessToolLLM(), tool_result="Inhalt", max_total_rounds=4, max_idle_rounds=99)
        result = "".join(core.ask_stream("Endlosschleife."))
        self.assertIn("Maximale Anzahl von Werkzeugschleifen erreicht", result)
        self.assertIn("Runden gesamt=4", result)

    def test_idle_rounds_limit_stops_rounds_without_progress(self):
        class FailAfterSuccessLLM(EndlessToolLLM):
            """Erster Aufruf erfolgreich, danach nur noch fehlgeschlagene Aufrufe."""

            def _reply(self):
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
                return {
                    "content": "",
                    "tool_calls": [{
                        "id": f"call-{self.calls}",
                        "type": "function",
                        "function": {"name": "list_files", "arguments": f'{{"path":"runde-{self.calls}"}}'},
                    }],
                }

        def tool_result(name, arguments):
            return "Inhalt" if arguments.endswith('"."}') else "FEHLER im Werkzeug: kein Fortschritt"

        core = make_core(llm=FailAfterSuccessLLM(), tool_result=tool_result, max_total_rounds=99, max_idle_rounds=2)
        result = core.ask("Runden ohne Fortschritt.")
        self.assertIn("Maximale Anzahl von Werkzeugschleifen erreicht", result)
        self.assertIn("Runden gesamt=3", result)
        self.assertIn("Runden ohne Fortschritt=2", result)
        self.assertEqual(core.llm.calls, 3)

    def test_progress_resets_idle_counter(self):
        core = make_core(llm=EndlessToolLLM(), tool_result="Inhalt", max_total_rounds=8, max_idle_rounds=1)
        result = core.ask("Viele Runden mit Fortschritt.")
        self.assertIn("Runden gesamt=8", result)
        self.assertIn("Runden ohne Fortschritt=0", result)
        self.assertEqual(core.llm.calls, 8)

    def test_loop_diagnostics_are_logged(self):
        core = make_core(llm=EndlessToolLLM(), tool_result="Inhalt", max_total_rounds=3, max_idle_rounds=99)
        core.ask("Endlosschleife.")
        records = [line for line in core.config.error_log_path.read_text(encoding="utf-8").splitlines() if line]
        self.assertIn('"category":"tool_loop"', records[-1])
        self.assertIn("Runden gesamt=3", records[-1])


class DenkLLM:
    """Schickt Denkausgabe, dann sichtbaren Text, dann das Ende."""

    def __init__(self):
        self.calls = 0

    def chat(self, history, schemas):
        self.calls += 1
        return {"content": "Hallo", "reasoning": "Ich überlege.", "tool_calls": []}

    def chat_stream(self, history, schemas):
        self.calls += 1
        yield {"type": "reasoning", "content": "Ich überlege. "}
        yield {"type": "content", "content": "Hallo"}
        yield {"type": "complete", "content": "Hallo", "tool_calls": []}


class TransparenzTests(unittest.TestCase):
    def test_denken_und_marker_kommen_ueber_events(self):
        core = make_core(llm=DenkLLM())
        ereignisse: list = []
        text = "".join(core.ask_stream("Hallo", events=ereignisse.append))
        self.assertEqual(text, "Hallo")
        arten = [e["type"] for e in ereignisse]
        self.assertIn("reasoning", arten)
        self.assertIn("marker", arten)
        inhalt = "".join(e["content"] for e in ereignisse)
        self.assertIn("Ich überlege.", inhalt)
        self.assertIn("[Runde 1]", inhalt)
        self.assertIn("[Ende]", inhalt)

    def test_protokoll_haelt_den_ganzen_lauf_fest(self):
        core = make_core(llm=DenkLLM())
        list(core.ask_stream("Hallo"))
        protokoll = core.config.stream_log_path.read_text(encoding="utf-8")
        self.assertIn("[Runde 1]", protokoll)
        self.assertIn("[denkt] Ich überlege.", protokoll)
        self.assertIn("[text] Hallo", protokoll)
        self.assertIn("[Ende]", protokoll)
        self.assertRegex(protokoll.splitlines()[0], r"^\d{2}:\d{2}:\d{2}\.\d{3}")

    def test_protokoll_laesst_sich_abschalten(self):
        core = make_core(llm=DenkLLM(), stream_log=False)
        list(core.ask_stream("Hallo"))
        self.assertFalse(core.config.stream_log_path.exists())

    def test_nicht_streamender_aufruf_landet_ebenfalls_im_protokoll(self):
        core = make_core(llm=DenkLLM())
        self.assertEqual(core.ask("Hallo"), "Hallo")
        protokoll = core.config.stream_log_path.read_text(encoding="utf-8")
        self.assertIn("[denkt] Ich überlege.", protokoll)
        self.assertIn("[Runde 1]", protokoll)


class SystemBriefingTests(unittest.TestCase):
    """Der Systemüberblick, mit dem jede Sitzung startet."""

    def make_core(self, briefing: str | None = "## RAG\nAlle Notizen unter ~/.fredtux-2.0/data/brain/rag/\n", **overrides):
        root = Path(tempfile.mkdtemp())
        config = Config(home=root, base_url="http://unused/v1", model="fake", api_key=None, **overrides)
        core = AgentCore(config, session_id="briefing-test")
        core.rules_path = root / "CODING_AGENT.md"
        core.rules_path.write_text("Regel eins.\n", encoding="utf-8")
        core.briefing_path = root / "SYSTEM.md"
        if briefing is not None:
            core.briefing_path.write_text(briefing, encoding="utf-8")
        core.history = [{"role": "system", "content": core.system_prompt()}]
        return core

    def test_ueberblick_steht_im_systemprompt(self):
        core = self.make_core("## Wo ich laufe\npi-ki ist 10.7.0.125.\n")
        prompt = core.history[0]["content"]
        self.assertIn("Systemüberblick", prompt)
        self.assertIn("pi-ki ist 10.7.0.125.", prompt)

    def test_verweis_auf_das_rag_kommt_beim_modell_an(self):
        core = self.make_core()
        self.assertIn("~/.fredtux-2.0/data/brain/rag/", core.history[0]["content"])

    def test_mitgelieferte_datei_existiert_und_wird_geladen(self):
        core = make_core()
        self.assertTrue(core.briefing_path.is_file())
        self.assertEqual(core.briefing_path.name, "SYSTEM.md")
        self.assertIn("data/brain/rag", core.system_prompt())

    def test_fehlende_datei_aendert_den_prompt_nicht(self):
        core = self.make_core(briefing=None)
        prompt = core.system_prompt()
        self.assertNotIn("Systemüberblick (SYSTEM.md)", prompt)
        self.assertIn("Du bist FredTux", prompt)
        self.assertIn("Verbindliche Coding-Regeln", prompt)

    def test_abschalter_laesst_den_ueberblick_weg(self):
        core = self.make_core("Nur ein Test.\n", system_briefing=False)
        self.assertNotIn("Nur ein Test.", core.system_prompt())

    def test_zu_grosser_ueberblick_wird_gekuerzt(self):
        core = self.make_core("A" * 5000 + "\nENDE-DES-TEXTES\n", system_max_chars=1000)
        prompt = core.system_prompt()
        self.assertIn("Systemüberblick gekürzt", prompt)
        self.assertIn("Zeichen, hier 1000", prompt)
        self.assertNotIn("ENDE-DES-TEXTES", prompt)
        self.assertLess(len(core.system_briefing()), 1200)

    def test_eigener_pfad_aus_der_konfiguration(self):
        root = Path(tempfile.mkdtemp())
        own = root / "UEBERBLICK.md"
        own.write_text("Eigener Überblick.\n", encoding="utf-8")
        config = Config(
            home=root, base_url="http://unused/v1", model="fake", api_key=None, system_file=own
        )
        core = AgentCore(config, session_id="briefing-pfad-test")
        self.assertEqual(core.briefing_path, own)
        self.assertIn("Eigener Überblick.", core.system_prompt())

    def test_reload_rules_nimmt_einen_geaenderten_ueberblick_mit(self):
        core = self.make_core("Erster Stand.\n")
        core.briefing_path.write_text("Zweiter Stand.\n", encoding="utf-8")
        result = core.tools.call("reload_rules", "{}")
        self.assertIn("neu geladen", result)
        self.assertIn("SYSTEM.md", result)
        self.assertIn("Zweiter Stand.", core.history[0]["content"])
        self.assertNotIn("Erster Stand.", core.history[0]["content"])

    def test_reload_rules_ohne_aenderung_meldet_unveraendert(self):
        core = self.make_core("Gleicher Stand.\n")
        self.assertIn("unverändert", core.tools.call("reload_rules", "{}"))


if __name__ == "__main__":
    unittest.main()
