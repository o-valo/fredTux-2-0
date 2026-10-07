"""Sicherheitsbehaftete lokale Shell- und Dateiwerkzeuge."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Config
from .coding import CodingCommandError, CodingCommandValidator, StructuredCommandRunner


STANDARD_COMMANDS = frozenset({"pwd", "ls", "grep", "ping", "lynx", "top", "ssh", "screen", "cd"})
CODING_COMMANDS = frozenset(
    {
        "python3", "pip3", "make", "git", "find", "ruff", "black", "mypy",
        "bash", "sh", "tar", "which", "wc", "head", "tail", "sort", "uniq", "date", "rm", "cp", "mv", "chmod",
        "df", "du", "free", "curl", "wget", "pwd", "ls", "grep", "cat", "mkdir", "touch",
        "true", "false", "echo", "printf", "test", "stat", "dirname", "basename", "env",
        "sed", "awk", "xargs", "cut", "tr", "nl", "paste", "join", "comm", "column", "fold", "expand", "split", "csplit",
        "diff", "patch", "md5sum", "sha256sum", "base64", "ps", "kill", "timeout", "watch", "nc", "telnet", "dig", "ss",
        "zip", "unzip", "gzip", "xz", "realpath", "readlink", "file", "install", "uuidgen", "tee", "od", "hexdump",
    }
)
# Coding mode deliberately does not become an unrestricted yolo shell.  It supports
# the development-oriented operators requested by the coding workflow, while still
# rejecting command substitution, newlines, and other shell escape hatches.
FORBIDDEN_CODING_SYNTAX = set(";$`\n\r\\<")
CODING_OPERATORS = ("&&", "||", "|", ">>", ">", "2>", "&>")
FORBIDDEN_SHELL_SYNTAX = set(";|&$><`\n\r\\")
PROTECTED_STANDARD_NAMES = {"config.nd", "shell.nd", ".env"}


class ShellError(ValueError):
    """Eine Shell- oder Dateirechteoperation wurde verweigert."""


@dataclass
class ShellTools:
    config: Config

    def __post_init__(self) -> None:
        if self.config.shell_mode not in {"allowlist", "standard", "coding", "yolo"}:
            raise ShellError(
                f"Unbekannter Shell-Modus {self.config.shell_mode!r}; erlaubt: allowlist, standard, coding, yolo."
            )
        self.root = self.config.shell_root.resolve()
        self.write_root = self.config.shell_write_root.resolve()
        self.extra_roots = tuple(
            root.resolve() for root in self.config.shell_extra_roots
        )
        self.rules = self._parse_rules(self.config.shell_allowed_commands)
        self.root.mkdir(parents=True, exist_ok=True)
        self._coding_validator = CodingCommandValidator(
            CODING_COMMANDS, (self.root, self.config.home.resolve(), *self.extra_roots)
        )
        self._structured_runner = StructuredCommandRunner(
            self, CODING_COMMANDS, self.config.coding_timeout
        )

    def describe(self) -> str:
        allowed = ", ".join(" ".join(rule) for rule in self.rules) or "(keine Einzelkommandos)"
        return f"Shell-Modus: {self.config.shell_mode}; erlaubte Regeln: {allowed}; Schreibbereich: {self.write_root}"

    def execute_command(self, command: str, cwd: str | None = None) -> str:
        if not isinstance(command, str) or not command.strip():
            raise ShellError("command darf nicht leer sein.")
        if self.config.shell_mode == "yolo":
            return self._run_bash(command, cwd)
        if self.config.shell_mode == "coding":
            self._validate_coding_command(command)
            return self._run_bash(command, cwd, self.config.coding_timeout)
        if any(char in FORBIDDEN_SHELL_SYNTAX for char in command):
            raise ShellError("Shell-Metazeichen sind im Standard-/Allowlist-Modus verboten.")
        try:
            args = shlex.split(command)
        except ValueError as exc:
            raise ShellError(f"Ungültige Kommandozeile: {exc}") from exc
        if not args:
            raise ShellError("command enthält kein Kommando.")
        if not self._allowed(args):
            raise ShellError(
                f"Kommando {args[0]!r} ist nicht freigegeben. Erlaubte Regeln: {self.describe()}"
            )
        if args[0] == "cd":
            return f"Arbeitsverzeichnis: {self._resolve_cwd(cwd, args[1] if len(args) > 1 else None)}"
        return self._run_process(args, cwd)

    def read_file(self, path: str, max_bytes: int = 100_000) -> str:
        target = self._resolve_read_path(path)
        if not target.is_file():
            raise ShellError(f"Datei nicht gefunden: {target}")
        if max_bytes < 1 or max_bytes > 2_000_000:
            raise ShellError("max_bytes muss zwischen 1 und 2.000.000 liegen.")
        data = target.read_bytes()[:max_bytes]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ShellError("Die Datei ist nicht als UTF-8 lesbar.") from exc

    def write_file(self, path: str, content: str) -> str:
        self._require_write_mode()
        target = self._resolve_write_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Geschrieben: {target} ({len(content)} Zeichen)"

    def change_permissions(self, path: str, mode: str) -> str:
        self._require_write_mode()
        target = self._resolve_write_path(path)
        if not re.fullmatch(r"[0-7]{3,4}", mode):
            raise ShellError("mode muss drei oder vier oktale Ziffern haben, z. B. 644 oder 0755.")
        target.chmod(int(mode, 8))
        return f"Rechte von {target} auf {mode} gesetzt."

    def _require_write_mode(self) -> None:
        if not self.config.shell_write_enabled:
            raise ShellError("Schreiben ist deaktiviert; FREDTUX_SHELL_WRITE=1 erforderlich.")
        if self.config.shell_mode == "allowlist":
            raise ShellError("Schreiben ist im Allowlist-Modus verboten; Standard- oder Coding-Modus verwenden.")

    def _resolve_read_path(self, value: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ShellError("Pfad darf nicht leer sein.")
        path = Path(value).expanduser()
        target = (self.root / path if not path.is_absolute() else path).resolve()
        if not target.is_relative_to(self.root):
            raise ShellError(f"Pfad liegt außerhalb des erlaubten Bereichs: {self.root}")
        return target

    def _resolve_write_path(self, value: str) -> Path:
        target = self._resolve_read_path(value)
        if not target.is_relative_to(self.write_root):
            raise ShellError(f"Pfad liegt außerhalb des Schreibbereichs: {self.write_root}")
        if self.config.shell_mode != "yolo":
            relative_parts = target.relative_to(self.write_root).parts
            if target.name in PROTECTED_STANDARD_NAMES or ".git" in relative_parts or ".venv" in relative_parts:
                raise ShellError("Konfiguration, Secrets und virtuelle Umgebung sind im Standard-Modus geschützt.")
        return target

    def _resolve_cwd(self, value: str | None, target_value: str | None = None) -> Path:
        raw = target_value or value or str(self.root)
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.root / path
        target = path.resolve()
        if self.config.shell_mode != "yolo":
            allowed_roots = (self.root,)
            if self.config.shell_mode == "coding":
                allowed_roots = (self.root, self.config.home.resolve(), *self.extra_roots)
            if not any(target == root or target.is_relative_to(root) for root in allowed_roots):
                raise ShellError(f"Arbeitsverzeichnis liegt außerhalb des erlaubten Bereichs: {', '.join(map(str, allowed_roots))}.")
        return target

    def _resolve_coding_output_path(self, value: str) -> Path:
        """Resolve a coding output path, including configured external roots."""
        path = Path(value).expanduser()
        target = (self.root / path if not path.is_absolute() else path).resolve()
        if target == Path("/dev/null"):
            return target
        if target.is_relative_to(self.write_root):
            return self._resolve_write_path(value)
        if self.config.shell_mode == "coding" and any(
            target == root or target.is_relative_to(root) for root in self.extra_roots
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            return target
        raise ShellError(f"Pfad liegt außerhalb des erlaubten Schreibbereichs: {target}")

    def _allowed(self, args: list[str]) -> bool:
        command = Path(args[0]).name
        if self.config.shell_mode == "standard" and command in STANDARD_COMMANDS:
            return True
        for rule in self.rules:
            if args[: len(rule)] == rule:
                return True
            if len(rule) == 1 and command == rule[0]:
                return True
        return False

    @staticmethod
    def _parse_rules(value: str) -> list[list[str]]:
        rules: list[list[str]] = []
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                rule = shlex.split(item)
            except ValueError as exc:
                raise ShellError(f"Ungültige Shell-Regel {item!r}: {exc}") from exc
            if rule:
                rules.append(rule)
        return rules

    def _validate_coding_command(self, command: str) -> None:
        """Delegate legacy command validation to the encapsulated coding policy."""
        try:
            self._coding_validator.validate(command)
        except CodingCommandError as exc:
            raise ShellError(str(exc)) from exc

    def run_structured_command(
        self,
        steps: list[dict[str, Any]],
        cwd: str | None = None,
        redirect_stdout: str | None = None,
        stdin: str | None = None,
        stderr: str = "capture",
    ) -> str:
        """Run a shell-free argv pipeline for new coding-agent tools."""
        try:
            return self._structured_runner.run(steps, cwd, redirect_stdout, stdin, stderr)
        except CodingCommandError as exc:
            raise ShellError(str(exc)) from exc

    def _run_process(self, args: list[str], cwd: str | None) -> str:
        try:
            result = subprocess.run(
                args,
                cwd=self._resolve_cwd(cwd),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.config.shell_timeout,
                env=self._safe_env(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ShellError(f"Zeitüberschreitung nach {self.config.shell_timeout:g} Sekunden: {args[0]}") from exc
        return self._format_result(args, result.returncode, result.stdout, result.stderr)

    def _run_bash(self, command: str, cwd: str | None, timeout: float | None = None) -> str:
        effective_timeout = timeout if timeout is not None else self.config.shell_timeout
        try:
            result = subprocess.run(
                ["/bin/bash", "-lc", command],
                cwd=self._resolve_cwd(cwd),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env=self._safe_env(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ShellError(f"Zeitüberschreitung nach {effective_timeout:g} Sekunden.") from exc
        return self._format_result(["bash", "-lc", command], result.returncode, result.stdout, result.stderr)

    @staticmethod
    def _safe_env() -> dict[str, str]:
        env = os.environ.copy()
        for key in ("FREDTUX_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_API_KEY"):
            env.pop(key, None)
        return env

    @staticmethod
    def _format_result(command: list[str], code: int, stdout: str, stderr: str) -> str:
        output = (stdout or "") + (("\n[stderr]\n" + stderr) if stderr else "")
        output = output[:50_000]
        return f"exit={code}; command={' '.join(command)}\n{output}".rstrip()
