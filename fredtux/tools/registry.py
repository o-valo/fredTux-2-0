"""Tool registry with JSON-compatible schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .knowledge import list_knowledge, save_knowledge, search_knowledge
from .shell import ShellTools


@dataclass
class ToolRegistry:
    rag_dir: Path
    shell: ShellTools | None = None

    def __post_init__(self) -> None:
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        if self.shell is None:
            from ..config import Config

            self.shell = ShellTools(Config.from_env())
        self._tools: dict[str, Callable[..., str]] = {
            "save_knowledge": self._save_knowledge,
            "search_knowledge": self._search_knowledge,
            "list_knowledge": self._list_knowledge,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "execute_command": self._execute_command,
            "run_coding_command": self._run_coding_command,
            "change_permissions": self._change_permissions,
        }
        self._extra_schemas: list[dict[str, Any]] = []

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., str],
    ) -> None:
        """Registriert ein Werkzeug zur Laufzeit, z. B. aus dem Agentenkern."""
        self._tools[name] = handler
        self._extra_schemas.append({
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        })

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "save_knowledge",
                    "description": "Speichert eine dauerhafte Notiz als Markdown-Datei im dateibasierten RAG.",
                    "parameters": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["title", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge",
                    "description": "Durchsucht lokale Markdown-Wissensdateien nach relevanten Textstellen.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_knowledge",
                    "description": "Listet alle lokalen Wissensdateien auf.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Liest eine UTF-8-Datei im freigegebenen Shell-Bereich.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Schreibt eine Textdatei nur im aktivierten Standard-/YOLO-Schreibbereich.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "Führt eine Kommandozeile gemäß Shell-Modus aus; Standardmodus verbietet Metazeichen, Coding-Modus erlaubt Entwicklungs-Pipelines.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_coding_command",
                    "description": "Führt eine sichere argv-Pipeline ohne Shell-String oder shell=True aus.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "program": {"type": "string"},
                                        "args": {"type": "array", "items": {"type": "string"}},
                                        "stdin": {"type": "string"},
                                        "stderr": {"type": "string", "enum": ["capture", "discard"]},
                                        "redirect_stdout": {"type": "string"},
                                    },
                                    "required": ["program", "args"],
                                },
                            },
                            "cwd": {"type": "string"},
                            "redirect_stdout": {"type": "string"},
                            "stdin": {"type": "string"},
                            "stderr": {"type": "string", "enum": ["capture", "discard"]},
                        },
                        "required": ["steps"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "change_permissions",
                    "description": "Ändert oktale Dateirechte im freigegebenen Schreibbereich.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "mode": {"type": "string"}},
                        "required": ["path", "mode"],
                    },
                },
            },
        ] + self._extra_schemas

    def call(self, name: str, arguments: str) -> str:
        if name not in self._tools:
            return f"FEHLER: Unbekanntes Werkzeug {name!r}."
        try:
            parsed = json.loads(arguments or "{}")
            if not isinstance(parsed, dict):
                return "FEHLER: Werkzeugargumente müssen ein JSON-Objekt sein."
            return self._tools[name](**parsed)
        except (TypeError, ValueError, OSError) as exc:
            return f"FEHLER im Werkzeug {name!r}: {exc}"

    def _save_knowledge(self, title: str, content: str) -> str:
        return save_knowledge(self.rag_dir, title, content)

    def _search_knowledge(self, query: str) -> str:
        return search_knowledge(self.rag_dir, query)

    def _list_knowledge(self) -> str:
        return list_knowledge(self.rag_dir)

    def _read_file(self, path: str, max_bytes: int = 100_000) -> str:
        return self.shell.read_file(path, max_bytes)

    def _write_file(self, path: str, content: str) -> str:
        return self.shell.write_file(path, content)

    def _execute_command(self, command: str, cwd: str | None = None) -> str:
        return self.shell.execute_command(command, cwd)

    def _run_coding_command(
        self,
        steps: list[dict[str, Any]],
        cwd: str | None = None,
        redirect_stdout: str | None = None,
        stdin: str | None = None,
        stderr: str = "capture",
    ) -> str:
        return self.shell.run_structured_command(steps, cwd, redirect_stdout, stdin, stderr)

    def _change_permissions(self, path: str, mode: str) -> str:
        return self.shell.change_permissions(path, mode)
