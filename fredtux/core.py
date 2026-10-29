"""Core agent loop and session orchestration."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .config import Config
from .compaction import Compactor
from .activitylog import ActivityLog, elapsed_ms
from .errorlog import ErrorLog
from .streamlog import StreamLog
from .llm import LLMClient
from .sessions import SessionStore
from .tools.registry import ToolRegistry
from .tools.shell import ShellTools


class AgentCore:
    def __init__(self, config: Config | None = None, session_id: str | None = None):
        self.config = config or Config.from_env()
        self.config.ensure_dirs()
        self.sessions = SessionStore(self.config.sessions_dir)
        self.error_log = ErrorLog(self.config.error_log_path)
        self.activity = ActivityLog(
            self.config.activity_log_path, self.config.log_enabled, self.config.log_level
        )
        self.streamlog = StreamLog(self.config.stream_log_path, self.config.stream_log)
        self.llm = LLMClient(self.config)
        self.tools = ToolRegistry(self.config.rag_dir, ShellTools(self.config))
        self.compactor = Compactor(self.config, self.llm, self.config.rag_dir)
        self.rules_path = Path(__file__).resolve().parents[1] / "CODING_AGENT.md"
        self.briefing_path = self.config.system_file or (
            Path(__file__).resolve().parents[1] / "SYSTEM.md"
        )
        self.tools.register(
            "reload_rules",
            "Lädt CODING_AGENT.md und den Systemüberblick (SYSTEM.md) neu in den laufenden "
            "Systemprompt. Nötig, nachdem eine der beiden Dateien mit write_file geändert "
            "wurde – sonst gelten die Änderungen erst ab der nächsten Sitzung.",
            {"type": "object", "properties": {}},
            self.reload_rules,
        )
        self.session_id = session_id or datetime.now(timezone.utc).strftime("session-%Y%m%d-%H%M%S")
        self.history = self.sessions.load(self.session_id)
        if not self.history:
            self.history = [{"role": "system", "content": self.system_prompt()}]
            self.sessions.append_message(self.session_id, self.history[0])

    def coding_rules(self) -> str:
        return self.rules_path.read_text(encoding="utf-8") if self.rules_path.is_file() else ""

    def system_briefing(self) -> str:
        """Liest den Systemüberblick, mit dem jede Sitzung startet.

        Die Datei (Vorgabe ``SYSTEM.md``) beantwortet die Fragen, für die der
        Agent sonst im Home-Verzeichnis herumstöbern müsste: wo er läuft, wo
        seine Konfiguration, Protokolle und seine Wissensbasis liegen. Sie wird
        hart gekürzt, weil der Systemprompt bei **jeder** Runde erneut durch das
        Prefill läuft – ein übergroßer Überblick würde jeden Aufruf verlangsamen.
        """
        if not self.config.system_briefing or not self.briefing_path.is_file():
            return ""
        text = self.briefing_path.read_text(encoding="utf-8", errors="replace").strip()
        limit = self.config.system_max_chars
        if len(text) <= limit:
            return text
        return (
            f"{text[:limit].rstrip()}\n\n"
            f"[Systemüberblick gekürzt: {len(text)} Zeichen, hier {limit}. "
            f"Vollständig lesbar in {self.briefing_path}.]"
        )

    def system_prompt(self) -> str:
        rules = self.coding_rules()
        briefing = self.system_briefing()
        parts = [
            "Du bist FredTux, ein modularer, hilfsbereiter Agent. Antworte auf Deutsch. "
            "Nutze lokale Wissenswerkzeuge, wenn dauerhafte Informationen gespeichert oder gesucht werden sollen. "
            "Im Coding-Modus bevorzuge run_coding_command mit strukturierten argv-Schritten; "
            "execute_command ist nur die eingeschränkte Kompatibilitäts-API. "
            "Führe keine nicht angeforderten Systemänderungen aus."
        ]
        if briefing:
            parts.append(f"Systemüberblick ({self.briefing_path.name}):\n{briefing}")
        if rules:
            parts.append(f"Verbindliche Coding-Regeln:\n{rules}")
        return "\n\n".join(parts)

    def reload_rules(self) -> str:
        """Ersetzt den Systemprompt im laufenden Kontext durch den aktuellen Stand."""
        prompt = self.system_prompt()
        rules_lines = len(self.coding_rules().splitlines())
        briefing_lines = len(self.system_briefing().splitlines())
        state = (
            f"{self.rules_path.name} mit {rules_lines} Zeilen, "
            f"{self.briefing_path.name} mit {briefing_lines} Zeilen"
        )
        index = next((i for i, message in enumerate(self.history) if message.get("role") == "system"), None)
        if index is None:
            self.history.insert(0, {"role": "system", "content": prompt})
            return (
                f"Regelwerk neu geladen: {state} wurde als "
                "Systemprompt eingesetzt und gilt ab sofort in dieser Sitzung."
            )
        previous = str(self.history[index].get("content", ""))
        if previous == prompt:
            return f"Regelwerk unverändert: {state} ist bereits aktiv."
        self.history[index]["content"] = prompt
        delta = len(prompt.splitlines()) - len(previous.splitlines())
        return (
            f"Regelwerk neu geladen: {state} ({delta:+d} Zeilen). "
            "Die Regeln gelten ab sofort in dieser Sitzung."
        )


    def switch_session(self, session_id: str) -> None:
        if not self.sessions.exists(session_id):
            raise FileNotFoundError(f"Unbekannte Sitzung: {session_id}")
        self.session_id = session_id
        self.history = self.sessions.load(session_id)
        if not self.history:
            self.history = [{"role": "system", "content": self.system_prompt()}]
            self.sessions.append_message(session_id, self.history[0])

    def new_session(self) -> str:
        self.session_id = datetime.now(timezone.utc).strftime("session-%Y%m%d-%H%M%S-%f")
        self.history = [{"role": "system", "content": self.system_prompt()}]
        self.sessions.append_message(self.session_id, self.history[0])
        return self.session_id

    def _trace(
        self,
        text: str,
        events: Callable[[dict[str, Any]], None] | None = None,
        kind: str = "marker",
    ) -> None:
        """Schreibt einen Marker ins Transparenzprotokoll und meldet ihn dem Client.

        So bleibt ein Lauf sichtbar, auch wenn das Modell minutenlang rechnet:
        Runden, Werkzeugaufrufe und deren Ergebnis stehen mit Zeitstempel in
        ``<home>/logs/stream.log`` und laufen – falls der Client es versteht –
        als Denkausgabe mit.
        """
        self.streamlog.line(text)
        if events is not None:
            events({"type": kind, "content": f"{text}\n"})

    def ask_stream(
        self,
        text: str,
        events: Callable[[dict[str, Any]], None] | None = None,
    ) -> Iterator[str]:
        """Streamt die sichtbare Antwort und führt Tool-Schleifen intern aus.

        ``events`` (optional) bekommt Denkausgabe des Modells sowie Runden- und
        Werkzeugmarker als ``{"type": ..., "content": ...}``, damit ein Client
        dem Lauf live zusehen kann. Ohne den Haken bleibt alles wie bisher.
        """
        started = time.monotonic()
        self.activity.event(
            "request.start", self.session_id, stream=True,
            chars=len(text), messages=len(self.history),
        )
        message = {"role": "user", "content": text}
        self.history.append(message)
        self.sessions.append_message(self.session_id, message)
        failed_calls: set[tuple[str, str]] = set()
        consecutive_failures = 0
        total_rounds = 0
        idle_rounds = 0
        last_call = ""
        while True:
            total_rounds += 1
            made_progress = False
            content_parts: list[str] = []
            completion: dict[str, Any] | None = None
            self._compact_if_needed()
            self._trace(
                f"[Runde {total_rounds}] {self.config.model}: "
                f"{len(self.history)} Nachrichten im Kontext",
                events,
            )
            llm_started = time.monotonic()
            try:
                for event in self.llm.chat_stream(self.history, self.tools.schemas()):
                    art = event.get("type")
                    if art == "reasoning":
                        denkt = str(event.get("content", ""))
                        if denkt:
                            self.streamlog.line(f"[denkt] {denkt}")
                            if events is not None:
                                events({"type": "reasoning", "content": denkt})
                    elif art == "content":
                        content = str(event.get("content", ""))
                        if content:
                            content_parts.append(content)
                            self.streamlog.line(f"[text] {content}")
                            yield content
                    elif art == "complete":
                        completion = event
            except Exception as exc:
                self._log_error("llm_stream", str(exc))
                self.activity.event(
                    "llm.error", self.session_id, level="error", round=total_rounds,
                    duration_ms=elapsed_ms(llm_started), error=str(exc),
                )
                raise
            if completion is None:
                self._log_error("llm_stream", "LLM-Streaming lieferte kein Completion-Ende.")
                raise RuntimeError("LLM-Streaming lieferte kein Completion-Ende.")
            tool_calls = completion.get("tool_calls", [])
            content = completion.get("content", "")
            self.activity.event(
                "llm.reply", self.session_id, round=total_rounds,
                duration_ms=elapsed_ms(llm_started), tool_calls=len(tool_calls),
                content_chars=len(content),
            )
            if not tool_calls:
                assistant_message = {"role": "assistant", "content": content}
                self.history.append(assistant_message)
                self.sessions.append_message(self.session_id, assistant_message)
                self.activity.event(
                    "request.end", self.session_id, stream=True, status="ok",
                    rounds=total_rounds, duration_ms=elapsed_ms(started),
                    content_chars=len(content),
                )
                self._trace(
                    f"[Ende] {total_rounds} Runde(n), "
                    f"{(time.monotonic() - started):.1f} s, {len(content)} Zeichen",
                    events,
                )
                return
            assistant_message = {"role": "assistant", "content": content, "tool_calls": tool_calls}
            self.history.append(assistant_message)
            self.sessions.append_message(self.session_id, assistant_message)
            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                arguments = function.get("arguments", "{}")
                tool_started = time.monotonic()
                self._trace(f"[Werkzeug] {name} {arguments}", events)
                result = self.tools.call(name, arguments)
                failed = str(result).startswith("FEHLER")
                last_call = f"{name}({arguments})"
                self._trace(
                    f"[Werkzeug] {name} → {'FEHLER' if failed else 'ok'}, "
                    f"{len(str(result))} Zeichen, {elapsed_ms(tool_started)} ms",
                    events,
                )
                self.activity.event(
                    "tool.call", self.session_id, round=total_rounds, tool=name,
                    arguments=arguments, duration_ms=elapsed_ms(tool_started),
                    ok=not failed, result_chars=len(str(result)),
                )
                if failed:
                    self._log_error("tool", f"{name}: {result}", arguments)
                else:
                    made_progress = True
                tool_message = {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": name,
                    "content": result,
                }
                self.history.append(tool_message)
                self.sessions.append_message(self.session_id, tool_message)
                loop_error = self._tool_loop_error(
                    name, arguments, result, failed_calls, consecutive_failures,
                )
                consecutive_failures = loop_error[1]
                if loop_error[0]:
                    self.activity.event(
                        "request.end", self.session_id, stream=True, status="tool_loop",
                        rounds=total_rounds, duration_ms=elapsed_ms(started),
                    )
                    yield loop_error[0]
                    return
            idle_rounds = 0 if made_progress else idle_rounds + 1
            if total_rounds >= self.config.max_total_rounds or idle_rounds >= self.config.max_idle_rounds:
                break
        self._log_error("tool_loop", self._loop_diagnostics(total_rounds, idle_rounds, last_call))
        self.activity.event(
            "request.end", self.session_id, stream=True, status="round_limit",
            rounds=total_rounds, duration_ms=elapsed_ms(started),
        )
        yield f"FEHLER: {self._loop_diagnostics(total_rounds, idle_rounds, last_call)}"

    def ask(self, text: str) -> str:
        started = time.monotonic()
        self.activity.event(
            "request.start", self.session_id, stream=False,
            chars=len(text), messages=len(self.history),
        )
        message = {"role": "user", "content": text}
        self.history.append(message)
        self.sessions.append_message(self.session_id, message)
        failed_calls: set[tuple[str, str]] = set()
        consecutive_failures = 0
        total_rounds = 0
        idle_rounds = 0
        last_call = ""
        while True:
            total_rounds += 1
            made_progress = False
            self._compact_if_needed()
            self._trace(
                f"[Runde {total_rounds}] {self.config.model}: "
                f"{len(self.history)} Nachrichten im Kontext"
            )
            llm_started = time.monotonic()
            try:
                reply = self.llm.chat(self.history, self.tools.schemas())
            except Exception as exc:
                self._log_error("llm", str(exc))
                self.activity.event(
                    "llm.error", self.session_id, level="error", round=total_rounds,
                    duration_ms=elapsed_ms(llm_started), error=str(exc),
                )
                raise
            tool_calls = reply.get("tool_calls", [])
            content = reply.get("content", "")
            if reply.get("reasoning"):
                self.streamlog.line(f"[denkt] {reply['reasoning']}")
            self.activity.event(
                "llm.reply", self.session_id, round=total_rounds,
                duration_ms=elapsed_ms(llm_started), tool_calls=len(tool_calls),
                content_chars=len(content),
            )
            if not tool_calls:
                message = {"role": "assistant", "content": content}
                self.history.append(message)
                self.sessions.append_message(self.session_id, message)
                self.activity.event(
                    "request.end", self.session_id, status="ok",
                    rounds=total_rounds, duration_ms=elapsed_ms(started),
                    content_chars=len(content),
                )
                self._trace(
                    f"[Ende] {total_rounds} Runde(n), "
                    f"{(time.monotonic() - started):.1f} s, {len(content)} Zeichen"
                )
                return content
            assistant_message = {"role": "assistant", "content": reply.get("content", ""), "tool_calls": tool_calls}
            self.history.append(assistant_message)
            self.sessions.append_message(self.session_id, assistant_message)
            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                arguments = function.get("arguments", "{}")
                tool_started = time.monotonic()
                self._trace(f"[Werkzeug] {name} {arguments}")
                result = self.tools.call(name, arguments)
                failed = str(result).startswith("FEHLER")
                last_call = f"{name}({arguments})"
                self._trace(
                    f"[Werkzeug] {name} → {'FEHLER' if failed else 'ok'}, "
                    f"{len(str(result))} Zeichen, {elapsed_ms(tool_started)} ms"
                )
                self.activity.event(
                    "tool.call", self.session_id, round=total_rounds, tool=name,
                    arguments=arguments, duration_ms=elapsed_ms(tool_started),
                    ok=not failed, result_chars=len(str(result)),
                )
                if failed:
                    self._log_error("tool", f"{name}: {result}", arguments)
                else:
                    made_progress = True
                tool_message = {"role": "tool", "tool_call_id": call.get("id", ""), "name": name, "content": result}
                self.history.append(tool_message)
                self.sessions.append_message(self.session_id, tool_message)
                loop_error, consecutive_failures = self._tool_loop_error(
                    name, arguments, result, failed_calls, consecutive_failures,
                )
                if loop_error:
                    self.activity.event(
                        "request.end", self.session_id, status="tool_loop",
                        rounds=total_rounds, duration_ms=elapsed_ms(started),
                    )
                    return loop_error
            idle_rounds = 0 if made_progress else idle_rounds + 1
            if total_rounds >= self.config.max_total_rounds or idle_rounds >= self.config.max_idle_rounds:
                break
        diagnostics = self._loop_diagnostics(total_rounds, idle_rounds, last_call)
        self._log_error("tool_loop", diagnostics)
        self.activity.event(
            "request.end", self.session_id, status="round_limit",
            rounds=total_rounds, duration_ms=elapsed_ms(started),
        )
        return f"FEHLER: {diagnostics}"

    def _compact_if_needed(self) -> None:
        """Verdichtet die Historie, bevor sie das Context-Fenster sprengt.

        Wirkt nur auf self.history, also auf die Liste, die ans Modell geht.
        Die Sitzungsdateien bleiben unveraendert vollstaendig.
        """
        before = len(self.history)
        self.history = self.compactor.compact(self.history, self.session_id)
        if len(self.history) < before:
            self.streamlog.line(
                f"[Kontext] verdichtet: {before} → {len(self.history)} Nachrichten"
            )
            self._log_error(
                "compaction",
                f"Context verdichtet: {before} auf {len(self.history)} Nachrichten, "
                f"ca. {self.compactor.estimate_tokens(self.history)} Tokens.",
            )

    def _loop_diagnostics(self, total_rounds: int, idle_rounds: int, last_call: str) -> str:
        return (
            "Maximale Anzahl von Werkzeugschleifen erreicht. "
            f"Runden gesamt={total_rounds}, Runden ohne Fortschritt={idle_rounds}, "
            f"Limit={self.config.max_total_rounds}/{self.config.max_idle_rounds}. "
            f"Letzter Werkzeugaufruf: {last_call or 'unbekannt'}"
        )

    def _log_error(self, category: str, message: str, context: str = "") -> None:
        self.error_log.write(category, f"{message} | args={context}", self.session_id)

    def _tool_loop_error(
        self,
        name: str,
        arguments: str,
        result: str,
        failed_calls: set[tuple[str, str]],
        consecutive_failures: int,
    ) -> tuple[str | None, int]:
        """Stop a runaway model loop after repeated tool failures."""
        if not str(result).startswith("FEHLER"):
            return None, 0
        consecutive_failures += 1
        fingerprint = (name, arguments)
        if fingerprint in failed_calls or consecutive_failures >= 3:
            reason = (
                f"Das Werkzeug {name!r} wurde mehrfach mit denselben fehlerhaften Parametern aufgerufen."
                if fingerprint in failed_calls
                else "Drei aufeinanderfolgende Werkzeugaufrufe sind fehlgeschlagen."
            )
            content = f"FEHLER: {reason} Bitte korrigiere den Aufruf oder gib eine neue Anweisung."
            assistant_message = {"role": "assistant", "content": content}
            self.history.append(assistant_message)
            self.sessions.append_message(self.session_id, assistant_message)
            return content, consecutive_failures
        failed_calls.add(fingerprint)
        return None, consecutive_failures
