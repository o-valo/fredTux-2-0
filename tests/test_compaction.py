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
        self.assertIs(new_history[0], history[0])

    def test_summary_is_second_system_message(self):
        new_history = self.compactor.compact(build_history(24), "s1")
        self.assertEqual(new_history[1]["role"], "system")
        self.assertIn("[Verlauf]", new_history[1]["content"])

    def test_result_is_structurally_valid(self):
        new_history = self.compactor.compact(build_history(24), "s1")
        self.assertEqual(structure_problems(new_history), [])

    def test_summary_respects_max_chars(self):
        llm = StubLLM(text="y" * 5000)
        compactor = Compactor(self.config, llm, self.rag)
        new_history = compactor.compact(build_history(24), "s1")
        body = new_history[1]["content"]
        self.assertLess(len(body), self.config.summary_max_chars + 200)

    def test_fallback_when_model_fails(self):
        compactor = Compactor(self.config, BrokenLLM(), self.rag)
        new_history = compactor.compact(build_history(24), "s1")
        self.assertEqual(structure_problems(new_history), [])
        self.assertTrue(new_history[1]["content"].strip())

    def test_summary_call_does_not_use_tools(self):
        self.compactor.compact(build_history(24), "s1")
        self.assertGreaterEqual(self.llm.calls, 1)


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