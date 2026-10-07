"""Core agent loop and session orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import Config
from .errorlog import ErrorLog
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
        self.llm = LLMClient(self.config)
        self.tools = ToolRegistry(self.config.rag_dir, ShellTools(self.config))
        self.rules_path = Path(__file__).resolve().parents[1] / "CODING_AGENT.md"
        self.tools.register(
            "reload_rules",
            "Lädt CODING_AGENT.md neu in den laufenden Systemprompt. Nötig, nachdem die "
            "Regeln mit write_file geändert wurden – sonst gelten sie erst ab der nächsten Sitzung.",
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

    def system_prompt(self) -> str:
        rules = self.coding_rules()
        prompt = (
            "Du bist FredTux, ein modularer, hilfsbereiter Agent. Antworte auf Deutsch. "
            "Nutze lokale Wissenswerkzeuge, wenn dauerhafte Informationen gespeichert oder gesucht werden sollen. "
            "Im Coding-Modus bevorzuge run_coding_command mit strukturierten argv-Schritten; "
            "execute_command ist nur die eingeschränkte Kompatibilitäts-API. "
            "Führe keine nicht angeforderten Systemänderungen aus."
        )
        return f"{prompt}\n\nVerbindliche Coding-Regeln:\n{rules}" if rules else prompt

    def reload_rules(self) -> str:
        """Ersetzt den Systemprompt im laufenden Kontext durch den aktuellen Regelstand."""
        prompt = self.system_prompt()
        lines = len(self.coding_rules().splitlines())
        index = next((i for i, message in enumerate(self.history) if message.get("role") == "system"), None)
        if index is None:
            self.history.insert(0, {"role": "system", "content": prompt})
            return (
                f"Regelwerk neu geladen: {self.rules_path.name} mit {lines} Zeilen wurde als "
                "Systemprompt eingesetzt und gilt ab sofort in dieser Sitzung."
            )
        previous = str(self.history[index].get("content", ""))
        if previous == prompt:
            return f"Regelwerk unverändert: {self.rules_path.name} mit {lines} Zeilen ist bereits aktiv."
        self.history[index]["content"] = prompt
        delta = len(prompt.splitlines()) - len(previous.splitlines())
        return (
            f"Regelwerk neu geladen: {self.rules_path.name} hat jetzt {lines} Zeilen ({delta:+d}). "
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

    def ask_stream(self, text: str) -> Iterator[str]:
        """Streamt die sichtbare Antwort und führt Tool-Schleifen intern aus."""
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
            try:
                for event in self.llm.chat_stream(self.history, self.tools.schemas()):
                    if event.get("type") == "content":
                        content = str(event.get("content", ""))
                        if content:
                            content_parts.append(content)
                            yield content
                    elif event.get("type") == "complete":
                        completion = event
            except Exception as exc:
                self._log_error("llm_stream", str(exc))
                raise
            if completion is None:
                self._log_error("llm_stream", "LLM-Streaming lieferte kein Completion-Ende.")
                raise RuntimeError("LLM-Streaming lieferte kein Completion-Ende.")
            tool_calls = completion.get("tool_calls", [])
            content = completion.get("content", "")
            if not tool_calls:
                assistant_message = {"role": "assistant", "content": content}
                self.history.append(assistant_message)
                self.sessions.append_message(self.session_id, assistant_message)
                return
            assistant_message = {"role": "assistant", "content": content, "tool_calls": tool_calls}
            self.history.append(assistant_message)
            self.sessions.append_message(self.session_id, assistant_message)
            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                arguments = function.get("arguments", "{}")
                result = self.tools.call(name, arguments)
                last_call = f"{name}({arguments})"
                if str(result).startswith("FEHLER"):
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
                    yield loop_error[0]
                    return
            idle_rounds = 0 if made_progress else idle_rounds + 1
            if total_rounds >= self.config.max_total_rounds or idle_rounds >= self.config.max_idle_rounds:
                break
        self._log_error("tool_loop", self._loop_diagnostics(total_rounds, idle_rounds, last_call))
        yield f"FEHLER: {self._loop_diagnostics(total_rounds, idle_rounds, last_call)}"

    def ask(self, text: str) -> str:
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
            try:
                reply = self.llm.chat(self.history, self.tools.schemas())
            except Exception as exc:
                self._log_error("llm", str(exc))
                raise
            tool_calls = reply.get("tool_calls", [])
            if not tool_calls:
                content = reply.get("content", "")
                message = {"role": "assistant", "content": content}
                self.history.append(message)
                self.sessions.append_message(self.session_id, message)
                return content
            assistant_message = {"role": "assistant", "content": reply.get("content", ""), "tool_calls": tool_calls}
            self.history.append(assistant_message)
            self.sessions.append_message(self.session_id, assistant_message)
            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                arguments = function.get("arguments", "{}")
                result = self.tools.call(name, arguments)
                last_call = f"{name}({arguments})"
                if str(result).startswith("FEHLER"):
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
                    return loop_error
            idle_rounds = 0 if made_progress else idle_rounds + 1
            if total_rounds >= self.config.max_total_rounds or idle_rounds >= self.config.max_idle_rounds:
                break
        diagnostics = self._loop_diagnostics(total_rounds, idle_rounds, last_call)
        self._log_error("tool_loop", diagnostics)
        return f"FEHLER: {diagnostics}"

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
