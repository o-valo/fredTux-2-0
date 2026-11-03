"""Tests fuer die automatische Context-Verdichtung.

Deckt die drei Fehlerquellen ab, die zur HTTP-400-Meldung
"request exceeds the available context size" fuehren:

1. Die Schnittkarte darf keine Werkzeugpaare zerschneiden - sonst lehnt der
   OpenAI-Endpunkt die Nachrichtliste ab.
2. Die Verdichtung darf nicht bei jeder Runde feuern (Hysterese).
3. Archive duerfen die eigentlichen Wissensnotizen nicht aus der Suche draengen.
"""

import tempfile
import unittest
from pathlib import Path

from fredtux.compaction import Compactor
from fredtux.tools.knowledge import list_knowledge, search_knowledge


class StubLLM:
    """Liefert eine feste Zusammenfassung, ohne ein echtes Modell zu brauchen."""

    def __init__(self, text="Zusammenfassung der frueheren Runden."):
        self.text = text
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        return {"content": self.text, "tool_calls": []}


class BrokenLLM:
    def chat(self, messages, tools=None):
        raise RuntimeError("simulierter Modellausfall")


class FakeConfig:
    def __init__(self, context_limit=300, keep_recent=6, archive_evicted=True,
                 summary_max_chars=300):
        self.context_limit = context_limit
        self.keep_recent = keep_recent
        self.archive_evicted = archive_evicted
        self.summary_max_chars = summary_max_chars


def build_history(rounds=24, filler="x" * 500):
    """Historie mit Systemprompt und gemischten Werkzeugpaaren."""
    history = [{"role": "system", "content": "SYSTEM"}]
    for i in range(rounds):
        if i % 3 == 2:
            call_id = f"call-{i}"
            history.append({
                "role": "assistant",
                "content": f"Werkzeugaufruf {i}",
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "curl", "arguments": "{}"},
                }],
            })
            history.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": "curl",
                "content": f"Ausgabe {i}",
            })
        else:
            history.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Nachricht {i} " + filler,
            })
    return history


def build_tool_chain(rounds=12, filler="x" * 500):
    """Eine Frage, danach nur noch Werkzeugrunden.

    So sieht der Fall aus, der den Dienst auf 10.7.0.101 mit HTTP 500
    ("No user query found in messages.") beendet hat: die sichere
    Schnittkante wandert rueckwaerts ueber alle Werkzeugpaare, bis hinter
    die letzte Frage – die bleibt dann nur noch in der Zusammenfassung.
    """
    history = [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "Was laeuft morgen um 20:15 im ZDF? " + filler},
    ]
    for i in range(rounds):
        call_id = f"call-{i}"
        history.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {"name": "curl", "arguments": "{}"},
            }],
        })
        history.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": "curl",
            "content": f"Ausgabe {i} " + filler,
        })
    return history


def structure_problems(history):
    """Prueft die OpenAI-Struktur der Nachrichtliste."""
    problems = []
    open_calls = []
    for index, message in enumerate(history):
        role = message.get("role")
        if role == "tool":
            if not open_calls:
                problems.append(f"Index {index}: verwaiste tool-Nachricht")
            else:
                open_calls.remove(message.get("tool_call_id"))
        elif role == "assistant" and message.get("tool_calls"):
            if open_calls:
                problems.append(f"Index {index}: vorheriger Werkzeugaufruf ohne Antwort")
            for call in message["tool_calls"]:
                open_calls.append(call.get("id"))
    if open_calls:
        problems.append(f"offene Werkzeugaufrufe: {open_calls}")
    return problems


class SafeCutTests(unittest.TestCase):
    """Die Schnittkarte muss fuer jede Historiegroesse gueltig sein."""

    def setUp(self):
        self.compactor = Compactor(
            FakeConfig(), StubLLM(), Path(tempfile.mkdtemp())
        )

    def test_cut_never_breaks_tool_pairs(self):
        for rounds in range(1, 40):
            with self.subTest(runden=rounds):
                history = build_history(rounds)
                cut = self.compactor._safe_cut(history, 6)
                problems = structure_problems(history[:cut]) + structure_problems(history[cut:])
                self.assertEqual(problems, [], f"Schnitt bei runden={rounds}")

    def test_cut_never_touches_system_prompt(self):
        history = build_history(30)
        for keep in (2, 4, 6, 10):
            with self.subTest(keep_recent=keep):
                self.assertGreaterEqual(self.compactor._safe_cut(history, keep), 1)

    def test_cut_keeps_enough_recent_messages(self):
        history = build_history(30)
        cut = self.compactor._safe_cut(history, 6)
        self.assertGreaterEqual(len(history) - cut, 1)


class CompactionTests(unittest.TestCase):
    def setUp(self):
        self.rag = Path(tempfile.mkdtemp())
        self.config = FakeConfig()
        self.llm = StubLLM()
        self.compactor = Compactor(self.config, self.llm, self.rag)

    def test_short_history_stays_untouched(self):
        history = build_history(2)
        self.assertIs(self.compactor.compact(history, "s1"), history)

    def test_long_history_is_reduced(self):
        history = build_history(24)
        before = len(history)
        after = self.compactor.compact(history, "s1")
        self.assertLess(len(after), before)

    def test_system_prompt_is_preserved(self):
        history = build_history(24)
        new_history = self.compactor.compact(history, "s1")
        self.assertTrue(new_history[0]["content"].startswith("SYSTEM"))

    def test_summary_is_merged_into_system_prompt(self):
        new_history = self.compactor.compact(build_history(24), "s1")
        self.assertEqual(new_history[0]["role"], "system")
        self.assertIn("[Verlauf]", new_history[0]["content"])

    def test_only_one_system_message(self):
        """Eine zweite Systemnachricht ergibt bei Qwen HTTP 500.

        Die Vorlage bricht mit "System message must be at the beginning." ab,
        sobald eine Systemnachricht nicht an erster Stelle steht. Deshalb muss
        die Verdichtung im Systemprompt aufgehen statt eine eigene Nachricht
        zu bilden.
        """
        new_history = self.compactor.compact(build_history(24), "s1")
        system_positions = [
            index for index, message in enumerate(new_history)
            if message.get("role") == "system"
        ]
        self.assertEqual(system_positions, [0])

    def test_repeated_compaction_replaces_summary(self):
        self.compactor.compact(build_history(24), "s1")
        new_history = self.compactor.compact(build_history(48), "s1")
        merged = new_history[0]["content"]
        self.assertEqual(merged.count("[Verlauf]"), 1)
        self.assertTrue(merged.startswith("SYSTEM"))

    def test_result_is_structurally_valid(self):
        new_history = self.compactor.compact(build_history(24), "s1")
        self.assertEqual(structure_problems(new_history), [])

    def test_summary_respects_max_chars(self):
        llm = StubLLM(text="y" * 5000)
        compactor = Compactor(self.config, llm, self.rag)
        new_history = compactor.compact(build_history(24), "s1")
        body = new_history[0]["content"]
        self.assertLess(len(body), self.config.summary_max_chars + 200)

    def test_fallback_when_model_fails(self):
        compactor = Compactor(self.config, BrokenLLM(), self.rag)
        new_history = compactor.compact(build_history(24), "s1")
        self.assertEqual(structure_problems(new_history), [])
        self.assertIn("[Verlauf]", new_history[0]["content"])

    def test_summary_call_does_not_use_tools(self):
        self.compactor.compact(build_history(24), "s1")
        self.assertGreaterEqual(self.llm.calls, 1)


class UserAnchorTests(unittest.TestCase):
    """Nach der Verdichtung muss eine Benutzerfrage im Kontext bleiben.

    Die Qwen3-Vorlage bricht sonst mit "No user query found in messages." ab
    (HTTP 500) – live gegen 10.7.0.79 nachgewiesen: System + Werkzeugrunde
    ohne User ergab 500, dieselbe Liste mit der Frage davor 200.
    """

    def setUp(self):
        self.rag = Path(tempfile.mkdtemp())
        self.config = FakeConfig()
        self.compactor = Compactor(self.config, StubLLM(), self.rag)

    def test_user_query_survives_a_tool_chain(self):
        after = self.compactor.compact(build_tool_chain(12), "s1")
        users = [m for m in after if m.get("role") == "user"]
        self.assertTrue(users, "keine Benutzerfrage mehr im Kontext")
        self.assertTrue(str(users[-1]["content"]).startswith("Was laeuft morgen"))

    def test_anchored_history_is_structurally_valid(self):
        after = self.compactor.compact(build_tool_chain(12), "s1")
        self.assertEqual(structure_problems(after), [])
        self.assertEqual(
            [i for i, m in enumerate(after) if m.get("role") == "system"], [0]
        )

    def test_summary_is_still_written(self):
        after = self.compactor.compact(build_tool_chain(12), "s1")
        self.assertIn("[Verlauf]", after[0]["content"])

    def test_every_chain_length_keeps_a_user_message(self):
        for rounds in range(1, 15):
            with self.subTest(runden=rounds):
                after = self.compactor.compact(build_tool_chain(rounds), f"s{rounds}")
                self.assertTrue(any(m.get("role") == "user" for m in after))


class HysteresisTests(unittest.TestCase):
    """Verdichtung darf nicht bei jedem Aufruf feuern."""

    def setUp(self):
        self.compactor = Compactor(
            FakeConfig(), StubLLM(), Path(tempfile.mkdtemp())
        )

    def test_does_not_fire_on_every_round(self):
        history = [{"role": "system", "content": "SYS"}]
        firings = 0
        for i in range(40):
            history.append({"role": "user", "content": f"Runde {i} " + "x" * 500})
            history.append({"role": "assistant", "content": f"Antwort {i} " + "y" * 500})
            if self.compactor.needs_compaction(history):
                firings += 1
                history = self.compactor.compact(history, f"sess-{firings}")
        self.assertLess(firings, 12, "Verdichtung feuert zu haeufig")
        self.assertGreater(firings, 0, "Verdichtung feuert gar nicht")

    def test_small_history_never_fires(self):
        history = build_history(2)
        self.assertFalse(self.compactor.needs_compaction(history))


class ArchiveTests(unittest.TestCase):
    """Archive landen im Unterverzeichnis und stoeren die Suche nicht."""

    def setUp(self):
        self.rag = Path(tempfile.mkdtemp())
        self.config = FakeConfig()
        (self.rag / "projekt-colibri.md").write_text(
            "# Projekt Colibri\n\nColibri nutzt eine NVMe.\n", encoding="utf-8"
        )
        self.compactor = Compactor(self.config, StubLLM(), self.rag)

    def _fill_and_compact(self):
        history = [{"role": "system", "content": "SYS"}]
        for i in range(24):
            history.append({
                "role": "user",
                "content": f"Runde {i}: Colibri nutzt eine NVMe. " + "x" * 500,
            })
            history.append({
                "role": "assistant",
                "content": f"Runde {i} bestaetigt: Colibri mit NVMe. " + "y" * 500,
            })
            if self.compactor.needs_compaction(history):
                history = self.compactor.compact(history, "archivtest")
        return history

    def test_archives_go_into_subdirectory(self):
        self._fill_and_compact()
        archives = list((self.rag / "archiv").glob("*.md"))
        self.assertTrue(archives, "keine Archivdatei geschrieben")
        direct = [p.name for p in self.rag.glob("*.md")]
        self.assertEqual(direct, ["projekt-colibri.md"])

    def test_real_notes_are_not_crowded_out(self):
        self._fill_and_compact()
        result = search_knowledge(self.rag, "Colibri NVMe")
        hits = [line for line in result.splitlines() if line.startswith("###")]
        self.assertTrue(hits)
        self.assertFalse([h for h in hits if "archiv" in h],
                         "Archive verdraengen echte Notizen")

    def test_archives_are_reachable_on_request(self):
        self._fill_and_compact()
        result = search_knowledge(self.rag, "Colibri NVMe", include_archives=True)
        hits = [line for line in result.splitlines() if line.startswith("###")]
        self.assertTrue([h for h in hits if "archiv" in h],
                        "Archive nicht auffindbar, obwohl angefordert")

    def test_archive_name_is_deterministic(self):
        first = Path(tempfile.mkdtemp())
        second = Path(tempfile.mkdtemp())
        Compactor(self.config, StubLLM(), first).compact(build_history(24), "sx")
        Compactor(self.config, StubLLM(), second).compact(build_history(24), "sx")
        self.assertEqual(
            sorted(p.name for p in first.glob("archiv/*.md")),
            sorted(p.name for p in second.glob("archiv/*.md")),
        )

    def test_list_knowledge_mentions_archives(self):
        self._fill_and_compact()
        listed = list_knowledge(self.rag)
        self.assertIn("projekt-colibri.md", listed)
        self.assertIn("archiv", listed)


class ToolOutputCapTests(unittest.TestCase):
    """Ein einzelnes Werkzeugergebnis darf den Context nicht auffressen."""

    def setUp(self):
        from fredtux.config import Config
        from fredtux.tools.registry import ToolRegistry
        from fredtux.tools.shell import ShellTools

        self.root = Path(tempfile.mkdtemp())
        self.config = Config(
            home=self.root,
            base_url="http://unused/v1",
            model="fake",
            api_key=None,
            max_tool_output=800,
            shell_mode="yolo",
            shell_root=self.root,
            shell_write_root=self.root,
        )
        self.registry = ToolRegistry(self.config.rag_dir, ShellTools(self.config))
        self.config.ensure_dirs()

    def test_long_output_is_capped(self):
        capped = self.registry._cap_output("A" * 45_135)
        self.assertLess(len(capped), 45_135)

    def test_short_output_is_untouched(self):
        self.assertEqual(self.registry._cap_output("kurz"), "kurz")

    def test_truncation_hint_is_added(self):
        capped = self.registry._cap_output("A" * 45_135)
        self.assertIn("Zeichen vom Werkzeugergebnis entfernt", capped)

    def test_beginning_and_end_survive(self):
        capped = self.registry._cap_output("START" + "x" * 45_135 + "ENDE")
        self.assertTrue(capped.startswith("START"))
        self.assertTrue(capped.rstrip().endswith("ENDE"))


class FitContextTests(unittest.TestCase):
    """Der Ueberlauf, der auf 10.7.0.101 den 500er ausgeloest hat.

    Gemessen am 01.11.2026: dieselbe Nachrichtenliste mit 16 Eintraegen belegte
    mit Werkzeugdeklaration 7680 von 8192 Tokens. Zwei Nachrichten mehr und der
    Server schnitt **von vorne** ab – die Frage fiel heraus, die Vorlage meldete
    "No user query found in messages." Die Liste muss deshalb vor dem Senden
    ins Fenster passen, samt Werkzeugdeklaration.
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.config = FakeConfig(context_limit=300, keep_recent=6)
        self.compactor = Compactor(self.config, StubLLM(), self.root)

    def _history(self, tool_chars=4000, tools=2):
        history = [
            {"role": "system", "content": "SYSTEM"},
            {"role": "user", "content": "Was laeuft morgen um 20:15 im ZDF?"},
        ]
        for i in range(tools):
            history.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": f"c{i}", "type": "function",
                                "function": {"name": "read_file", "arguments": "{}"}}],
            })
            history.append({
                "role": "tool", "tool_call_id": f"c{i}", "name": "read_file",
                "content": f"HTML {i} " + "x" * tool_chars,
            })
        return history

    def test_untouched_when_it_fits(self):
        history = self._history(tool_chars=50)
        gekuerzt, saved = self.compactor.fit_context(history)
        self.assertEqual(saved, 0)
        self.assertIs(gekuerzt, history)

    def test_oversized_tool_output_is_clipped(self):
        history = self._history(tool_chars=4000)
        gekuerzt, saved = self.compactor.fit_context(history)
        self.assertGreater(saved, 0)
        self.assertLessEqual(
            self.compactor.estimate_tokens(gekuerzt), self.compactor.budget(0)
        )

    def test_user_query_survives(self):
        history = self._history(tool_chars=4000)
        gekuerzt, _ = self.compactor.fit_context(history)
        self.assertEqual(gekuerzt[0]["role"], "system")
        self.assertEqual(gekuerzt[1]["role"], "user")
        self.assertIn("ZDF", gekuerzt[1]["content"])

    def test_overhead_counts_against_the_window(self):
        """Die Werkzeugdeklaration liegt im selben Fenster wie die Historie."""
        knapp = Compactor(FakeConfig(context_limit=500), StubLLM(), self.root)
        history = self._history(tool_chars=1500, tools=1)
        _, saved_ohne = knapp.fit_context(history, overhead_tokens=0)
        _, saved_mit = knapp.fit_context(history, overhead_tokens=300)
        self.assertEqual(saved_ohne, 0, "passt ohne Ueberhang bereits")
        self.assertGreater(saved_mit, 0)
        self.assertLess(knapp.budget(300), knapp.budget(0))

    def test_newest_tool_output_is_clipped_last(self):
        history = self._history(tool_chars=4000)
        gekuerzt, _ = self.compactor.fit_context(history)
        alt = next(m for m in gekuerzt if m.get("name") == "read_file")
        neu = [m for m in gekuerzt if m.get("name") == "read_file"][-1]
        self.assertLess(len(alt["content"]), len(neu["content"]) + 1)

    def test_many_middle_sized_messages_fall_away(self):
        """Kuerzen reicht nicht immer – dann muessen aelteste Runden weichen."""
        history = [{"role": "system", "content": "SYSTEM"}]
        history.append({"role": "user", "content": "Was laeuft morgen um 20:15 im ZDF?"})
        for i in range(40):
            history.append({"role": "assistant", "content": f"Antwort {i} " + "y" * 400})
            history.append({"role": "user", "content": f"Frage {i} " + "x" * 400})
        gekuerzt, _ = self.compactor.fit_context(history)
        self.assertLess(len(gekuerzt), len(history))
        self.assertLessEqual(
            self.compactor.estimate_tokens(gekuerzt), self.compactor.budget(0)
        )
        self.assertTrue(any(m.get("role") == "user" for m in gekuerzt))


class PayloadOptionTests(unittest.TestCase):
    """options.num_ctx wird nur gesendet, wenn es konfiguriert ist."""

    def _client(self, num_ctx):
        from fredtux.config import Config
        from fredtux.llm import LLMClient

        config = Config(
            home=Path(tempfile.mkdtemp()),
            base_url="http://unused/v1",
            model="fake",
            api_key=None,
            num_ctx=num_ctx,
        )
        return LLMClient(config)

    def test_disabled_by_default(self):
        self.assertEqual(self._client(0)._payload_options(), {})

    def test_enabled_when_configured(self):
        self.assertEqual(
            self._client(262144)._payload_options(),
            {"options": {"num_ctx": 262144}},
        )


if __name__ == "__main__":
    unittest.main()