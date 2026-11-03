"""Kontextverwaltung für lange Sitzungen.

Fred schickt bei jedem Aufruf die komplette Historie mit. Ohne Begrenzung
füllt eine einzelne lange Werkzeugausgabe das Fenster und der LLM-Aufruf
bricht mit HTTP 400 ("exceeds the available context size") ab.

Dieses Modul fasst ältere Runden zusammen und entfernt sie aus dem Prompt.
Die Sitzungsdateien bleiben dabei vollständig: gekürzt wird nur die Liste,
die an das Modell geht. Verdichtete Inhalte landen zusätzlich in der
Wissensbank und sind über search_knowledge wieder abrufbar.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config
from .llm import LLMClient


# Gute Naeherung fuer deutschen und englischen Mischtext.
CHARS_PER_TOKEN = 3.5

# Erst bei 75 % der konfigurierten Grenze verdichten: das gibt Luft, damit
# die Verdichtung nicht schon bei der naechsten kurzen Nachricht wieder greift.
COMPACTION_TRIGGER_RATIO = 0.75

# Mindestzahl neuer Nachrichten zwischen zwei Verdichtungen.
MIN_MESSAGES_BETWEEN_COMPACTIONS = 12

# Werkzeugdeklarationen gehen als JSON mit und sind dichter als Fliesstext:
# gemessen auf 10.7.0.79 rund 2,9 Zeichen je Token statt 3,5.
TOOL_JSON_CHARS_PER_TOKEN = 2.9

# Vorlagen- und Nachrichtenrahmen der Chat-Vorlage (Rollenmarken, Werkzeug-
# Praeambel). Kleiner Aufschlag, damit die Rechnung nicht knapp daneben liegt.
TEMPLATE_RESERVE_TOKENS = 400

# Laengen, auf die einzelne Nachrichten beim Auffuellen des Fensters gekuerzt
# werden. Werkzeugausgaben zuerst und am schaerfsten: eine ausgelesene
# HTML-Seite ist fast immer der Grund fuer den Ueberlauf.
CLIP_TOOL_CHARS = 1200
CLIP_TEXT_CHARS = 4000

# Unter dieser Laenge wird eine Werkzeugantwort nicht weiter gekuerzt: ein
# Rest muss lesbar bleiben, sonst hilft das Ergebnis dem Modell nicht mehr.
MIN_CLIP_CHARS = 400

# Notiz an der Schnittstelle jeder Kuerzung, damit das Modell weiss, dass hier
# gekuerzt wurde und der vollstaendige Inhalt in der Sitzungsdatei steht.
CLIP_MARKER = "\n[... gekuerzt, um das Context-Fenster zu halten; vollstaendig in der Sitzungsdatei ...]\n"


# Verdichtete Runden kommen in ein Unterverzeichnis. search_knowledge liest
# nur Dateien direkt in rag_dir, sonst wuerden die Archive die eigentlichen
# Notizen aus den Suchergebnissen verdraengen.
ARCHIVE_DIRNAME = "archiv"

# Trennzeile zwischen Systemprompt und verdichtetem Verlauf. Die Verdichtung
# wird an den bestehenden Systemprompt angehaengt statt als eigene Nachricht
# eingefuegt: Qwen-Vorlagen lehnen jede Systemnachricht ausser der ersten ab
# ("System message must be at the beginning.", HTTP 500).
CONTEXT_MARKER = "\n\n[Verlauf]\n"

SUMMARY_TEMPLATE = (
    "Fasse das folgende Gespraechsprotokoll fuer den Fortlauf der Unterhaltung "
    "zusammen. Behalte nur das, was spaeter noch gebraucht wird: erkannte "
    "Fakten ueber den Nutzer und seine Projekte, getroffene Entscheidungen, "
    "wichtige Ergebnisse, offene Punkte und laufende Aufgaben. "
    "Verliere keine Zahlen, Dateinamen, Pfade oder Namen. "
    "Weglassen von Hoeflichkeiten und Redundanzen. Antworte auf Deutsch, "
    "als kompakte Stichpunkte, hoechstens {limit} Zeichen, ohne Vorrede."
)

ARCHIVE_HEADER = (
    "Automatisch verdichteter Teil einer Sitzung. Diese Runden wurden aus dem "
    "aktiven Kontext entfernt, um das Context-Fenster freizuhalten. Der Inhalt "
    "bleibt vollstaendig in der Sitzungsdatei und kann bei Bedarf von dort "
    "gelesen werden."
)


@dataclass
class Compactor:
    config: Config
    llm: LLMClient
    rag_dir: Path

    def __post_init__(self) -> None:
        self._last_size = 0

    # -- Groessenmessung ------------------------------------------------
    @staticmethod
    def estimate_tokens(history: list[dict[str, Any]]) -> int:
        total = 0
        for message in history:
            content = message.get("content")
            if isinstance(content, str):
                total += len(content)
            if message.get("tool_calls"):
                total += 200
        return int(total / CHARS_PER_TOKEN)

    def needs_compaction(self, history: list[dict[str, Any]]) -> bool:
        """Entscheidet mit Hysterese, damit nicht jede Runde verdichtet wird.

        Zwei Bedingungen muessen zutreffen: Der Context muss deutlich ueber
        der Grenze liegen (sonst kaempft die Verdichtung gegen jedes neue
        Token), und seit dem letzten Mal muss genug hinzugekommen sein.
        Ohne diese Bremse feuert die Verdichtung im eingeschwungenen Zustand
        bei praktisch jedem Aufruf und kostet jedes Mal einen extra LLM-Call.
        """
        if not self.needs_free_headroom(history):
            return False
        since_last = len(history) - self._last_size
        if since_last < max(self.config.keep_recent, MIN_MESSAGES_BETWEEN_COMPACTIONS):
            return False
        return True

    def needs_free_headroom(self, history: list[dict[str, Any]]) -> bool:
        """Nur bei echtem Ueberlauf verdichten, nicht am Anschlag."""
        tokens = self.estimate_tokens(history)
        return tokens > self.config.context_limit * COMPACTION_TRIGGER_RATIO

    # -- Hartes Auffuellen des Fensters ---------------------------------
    @staticmethod
    def _chars(history: list[dict[str, Any]]) -> int:
        return sum(len(m["content"]) for m in history if isinstance(m.get("content"), str))

    @staticmethod
    def _clip(content: str, limit: int) -> str:
        """Kuerzt eine Nachricht auf ``limit`` Zeichen und markiert die Stelle.

        Kopf und Ende bleiben erhalten: bei Werkzeugausgaben steht das Ergebnis
        meist am Ende, bei Seiten der Titel am Anfang.
        """
        if len(content) <= limit:
            return content
        head = int(limit * 0.6)
        tail = limit - head
        return f"{content[:head]}{CLIP_MARKER}{content[-tail:]}"

    def budget(self, overhead_tokens: int = 0) -> int:
        """Tokens, die der Historie zustehen: Grenze minus Werkzeuge und Vorlage."""
        return max(1, self.config.context_limit - max(0, overhead_tokens))

    def fit_context(
        self, history: list[dict[str, Any]], overhead_tokens: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """Kuerzt die Nachrichtenliste, bis sie samt Ueberhang ins Fenster passt.

        Die Verdichtung allein reicht nicht: sie schneidet aeltere Runden ab,
        kann aber eine einzelne riesige Werkzeugausgabe nicht verkleinern. Genau
        die sprengt das Fenster, und der Modellserver schneidet dann **von
        vorne** ab – die Frage des Nutzers faellt heraus und die Chat-Vorlage
        bricht mit "No user query found in messages." ab (HTTP 500).

        Gibt die (ggf. neue) Liste und die Zahl der gekuerzten Zeichen zurueck.
        Die Sitzungsdateien bleiben unveraendert vollstaendig.
        """
        budget = self.budget(overhead_tokens)
        if self.estimate_tokens(history) <= budget:
            return history, 0

        zeichen_vorher = self._chars(history)
        new = list(history)
        # Erste Stufe: Werkzeugantworten kuerzen, aelteste zuerst – die neueste
        # ist die, mit der das Modell gerade arbeitet. Reicht eine Grenze nicht,
        # wird sie halbiert; eine feste Laenge passt nicht zu jedem Fenster.
        cap = CLIP_TOOL_CHARS
        while self.estimate_tokens(new) > budget and cap >= MIN_CLIP_CHARS:
            for index, message in enumerate(new):
                if message.get("role") != "tool":
                    continue
                content = message.get("content")
                if not isinstance(content, str) or len(content) <= cap:
                    continue
                new[index] = dict(message, content=self._clip(content, cap))
                if self.estimate_tokens(new) <= budget:
                    break
            cap //= 2
        # Zweite Stufe: einzelne ueberlange Textnachrichten (z. B. eingefuegter
        # Seiteninhalt). Der Systemprompt bleibt unangetastet.
        for index, message in enumerate(new):
            if self.estimate_tokens(new) <= budget:
                break
            if index == 0 or message.get("role") == "tool":
                continue
            content = message.get("content")
            if not isinstance(content, str) or len(content) <= CLIP_TEXT_CHARS:
                continue
            new[index] = dict(message, content=self._clip(content, CLIP_TEXT_CHARS))
        # Dritte Stufe: reicht Kuerzen nicht (viele mittelgrosse Nachrichten),
        # fallen die aeltesten Runden weg – ohne Modellaufruf, sonst kostet jeder
        # uebervolle Lauf eine zusaetzliche Zusammenfassung und die
        # Verdichtungsbremse waere ausgehebelt. Systemprompt und Frage bleiben.
        while self.estimate_tokens(new) > budget and len(new) > 2:
            index = 2 if new[0].get("role") == "system" else 1
            if index >= len(new):
                break
            if new[index].get("role") == "user":
                index += 1  # die Frage selbst nie wegwerfen
            if index >= len(new):
                break
            del new[index]
            # Eine Werkzeugantwort ohne ihren Aufruf wuerde der Endpunkt ablehnen.
            while index < len(new) and new[index].get("role") == "tool":
                del new[index]
        return new, max(0, zeichen_vorher - self._chars(new))

    # -- Sichere Schnittkante ------------------------------------------
    def _safe_cut(self, history: list[dict[str, Any]], keep_recent: int) -> int:
        """Findet eine Schnittstelle, die keine Werkzeugpaare zerreissst.

        Eine Nachricht mit Rolle "tool" gehoert immer zu einem unmittelbar
        vorhergehenden Assistenten mit tool_calls. Wird zwischen beiden
        geschnitten, lehnt der OpenAI-Endpunkt die Nachrichtliste ab.
        """
        cut = len(history) - keep_recent
        cut = max(1, min(cut, len(history)))

        # Der erste behaltene Eintrag darf keine verwaiste Werkzeugantwort sein.
        while cut < len(history) and history[cut].get("role") == "tool":
            cut -= 1
        # ...und die letzte verdichtete Nachricht darf kein offener Werkzeugaufruf sein.
        while cut > 1 and history[cut - 1].get("role") == "tool":
            cut -= 1
        while (
            cut > 1
            and history[cut - 1].get("role") == "assistant"
            and history[cut - 1].get("tool_calls")
        ):
            cut -= 1
        return max(1, cut)

    # -- Verdichtung ----------------------------------------------------
    def _transcript(self, messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for message in messages:
            role = str(message.get("role", "?"))
            content = message.get("content")
            if not isinstance(content, str):
                content = ""
            name = message.get("name")
            if role == "tool" and name:
                role = f"tool:{name}"
            if role == "assistant" and message.get("tool_calls"):
                calls = ", ".join(
                    str(call.get("function", {}).get("name", "?")) for call in message["tool_calls"]
                )
                lines.append(f"[{role}] (Werkzeugaufrufe: {calls}) {content}".rstrip())
                continue
            if content:
                lines.append(f"[{role}] {content}")
        return "\n\n".join(lines)

    def _summarize(self, transcript: str) -> str:
        """Lässt das Modell zusammenfassen; fällt auf einen Extrakt zurück."""
        prompt = SUMMARY_TEMPLATE.format(limit=self.config.summary_max_chars)
        try:
            reply = self.llm.chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": transcript},
                ]
            )
            summary = str(reply.get("content") or "").strip()
        except Exception:
            summary = ""
        if not summary:
            summary = self._fallback_summary(transcript)
        if len(summary) > self.config.summary_max_chars:
            summary = summary[: self.config.summary_max_chars].rstrip() + " ..."
        return summary

    @staticmethod
    def _fallback_summary(transcript: str, limit: int = 2000) -> str:
        """Ohne LLM: die inhaltlich dichtesten Zeilen behalten."""
        lines = [line for line in transcript.splitlines() if line.strip()]
        scored = sorted(lines, key=len, reverse=True)[:12]
        return "\n".join(line[:400] for line in scored)[:limit]

    # -- Archiv ---------------------------------------------------------
    def _archive(self, title: str, body: str, session_id: str) -> str | None:
        """Schreibt verdichtete Runden in das Archiv-Unterverzeichnis.

        Bewusst nicht direkt in rag_dir: search_knowledge wertet nur Dateien
        dort aus und gibt die besten Treffer zurueck. Archive blieben sonst
        als Ballast in den Suchergebnissen und verdraengten echte Notizen.
        """
        safe_session = re.sub(r"[^a-zA-Z0-9_-]+", "-", session_id).strip("-") or "sitzung"
        # Deterministischer Hash: gleicher Inhalt ergibt denselben Dateinamen,
        # auch nach einem Neustart (hash() waere prozessabhaengig).
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]
        archive_dir = self.rag_dir / ARCHIVE_DIRNAME
        path = archive_dir / f"archiv-{safe_session}-{digest}.md"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {title}\n\n{ARCHIVE_HEADER}\n\n{body}\n", encoding="utf-8")
        except OSError:
            return None
        return path.name

    # -- Hauptaufruf ----------------------------------------------------
    def compact(self, history: list[dict[str, Any]], session_id: str) -> list[dict[str, Any]]:
        """Verdichtet die Historie, falls sie zu gross geworden ist.

        Gibt die neue Nachrichtenliste zurueck. Bei Erfolg wird der Summary an
        den Systemprompt (Index 0) angehaengt; eine frueher angehaengte
        Verdichtung wird dabei ersetzt. Die Liste enthaelt danach weiterhin
        genau **eine** Systemnachricht und zwar an erster Stelle.
        """
        if not self.needs_compaction(history):
            return history

        cut = self._safe_cut(history, self.config.keep_recent)
        if cut <= 1 or cut >= len(history) - 1:
            # Zu wenig zum Verdichten oder nichts sinnvoll zu schneiden.
            return history

        evicted = history[1:cut]
        transcript = self._transcript(evicted)
        if not transcript.strip():
            return history

        summary = self._summarize(transcript)
        archive_name = None
        if self.config.archive_evicted:
            archive_name = self._archive(
                f"Sitzung {session_id} - verdichtete Runden",
                transcript,
                session_id,
            )

        note = (
            "Zusammenfassung der frueheren Unterhaltung. Der ausfuehrliche "
            "Verlauf dieser Runden steht nicht mehr im aktiven Kontext."
        )
        if archive_name:
            note += f" Gesichert in der Wissensdatei '{archive_name}'."

        base = ""
        if history and history[0].get("role") == "system":
            base = str(history[0].get("content") or "").split(CONTEXT_MARKER)[0]
        system_message = {"role": "system", "content": f"{base}{CONTEXT_MARKER}{summary}"}
        kept = self._with_user_anchor(history, cut)
        new_history = [system_message, *kept]
        self._last_size = len(new_history)
        return new_history

    @staticmethod
    def _with_user_anchor(history: list[dict[str, Any]], cut: int) -> list[dict[str, Any]]:
        """Stellt sicher, dass die behaltene Liste eine Benutzerfrage enthaelt.

        Die Chat-Vorlage von Qwen3 bricht mit "No user query found in messages."
        ab (HTTP 500), wenn nach der Systemnachricht keine Nachricht der Rolle
        "user" mehr folgt. Genau das entsteht bei einer langen Werkzeugkette:
        die sichere Schnittkante wandert rueckwaerts ueber alle Werkzeugpaare
        bis hinter die letzte Frage, und die verschwindet dann in der
        Zusammenfassung. Deshalb wird die letzte Frage vor den behaltenen Teil
        gestellt – sie ist der Auftrag, der gerade laeuft, und gehoert nicht
        allein in eine Zusammenfassung.
        """
        kept = history[cut:]
        if any(message.get("role") == "user" for message in kept):
            return kept
        last_query = next(
            (m for m in reversed(history[:cut]) if m.get("role") == "user"), None
        )
        if last_query is None:
            return kept
        return [last_query, *kept]