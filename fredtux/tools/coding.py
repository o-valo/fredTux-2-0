"""Encapsulated validation and shell-free execution for coding commands."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

DEVNULL_PATH = "/dev/null"


class CodingCommandError(ValueError):
    """A coding command violates the structured execution policy."""


class CodingCommandValidator:
    """Validate the legacy string command API without executing shell syntax."""

    def __init__(self, allowed_commands: set[str], allowed_roots: tuple[Path, ...]):
        self.allowed_commands = frozenset(allowed_commands)
        self.allowed_roots = tuple(root.resolve() for root in allowed_roots)

    def validate(self, command: str) -> None:
        if not isinstance(command, str) or not command.strip():
            raise CodingCommandError("command darf nicht leer sein.")
        if any(char in command for char in "\n\r"):
            raise CodingCommandError("Neue Zeilen sind im Coding-Modus nicht erlaubt.")
        if self._has_unquoted_substitution(command):
            raise CodingCommandError("Kommando-Substitution ist im Coding-Modus nicht erlaubt.")
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError as exc:
            raise CodingCommandError(f"Ungültige Coding-Kommandozeile: {exc}") from exc
        operators = {"&&", "||", "|", ">", ">>", "&>"}
        redirects = {">", ">>", "&>"}
        segments: list[list[str]] = []
        current: list[str] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in {";", "<"}:
                raise CodingCommandError("Diese Shell-Syntaxform ist im Coding-Modus nicht erlaubt.")
            if token in operators:
                if current:
                    segments.append(current)
                    current = []
                if token in redirects:
                    if index + 1 >= len(tokens):
                        raise CodingCommandError("Eine Umleitung benötigt ein Ziel.")
                    self._validate_path(tokens[index + 1])
                    index += 2
                else:
                    index += 1
                continue
            if token == "2" and index + 1 < len(tokens) and tokens[index + 1] in redirects:
                if index + 2 >= len(tokens):
                    raise CodingCommandError("Eine Fehlerausgabe-Umleitung benötigt ein Ziel.")
                self._validate_path(tokens[index + 2])
                index += 3
                continue
            current.append(token)
            index += 1
        if current:
            segments.append(current)
        if not segments:
            raise CodingCommandError("Coding-Befehl enthält kein Kommando.")
        for segment in segments:
            executable = Path(segment[0]).name
            if executable not in self.allowed_commands:
                raise CodingCommandError(
                    f"Kommando {executable!r} ist im Coding-Modus nicht freigegeben."
                )
            for token in segment[1:]:
                self.validate_argument_path(token, executable in {"sed", "awk"})

    @staticmethod
    def _has_unquoted_substitution(command: str) -> bool:
        """Detect shell substitutions without rejecting literal $ in quoted filters."""
        quote: str | None = None
        escaped = False
        for char in command:
            if escaped:
                escaped = False
                continue
            if char == "\\" and quote != "'":
                escaped = True
                continue
            if quote:
                if char == quote:
                    quote = None
                elif quote == '"' and char in "$`":
                    return True
                continue
            if char in "'\"":
                quote = char
            elif char in "$`":
                return True
        return False

    def validate_argument_path(self, token: str, allow_filter: bool = False) -> None:
        """Reject path-like argv values outside the configured roots."""
        path_value = token.split("=", 1)[1] if "=" in token else token
        path_value = re.sub(r"^-[A-Za-z]+", "", path_value)
        if path_value == ".." or path_value.startswith("../"):
            raise CodingCommandError("Coding-Pfade dürfen das Projektverzeichnis nicht verlassen.")
        if not (path_value.startswith("/") or path_value.startswith("~/") or re.match(r"^-[A-Za-z]+[/~]", token)):
            return
        # sed/awk frequently use slash-delimited expressions as arguments. They
        # are expressions, not filesystem paths, and must not trigger the path
        # allowlist merely because they start with a slash.
        if allow_filter and re.fullmatch(r"/.*/[a-z]*", token):
            return
        candidate = Path(path_value).expanduser().resolve()
        if candidate == Path(DEVNULL_PATH):
            return
        if not any(candidate == root or candidate.is_relative_to(root) for root in self.allowed_roots):
            raise CodingCommandError(
                f"Coding-Pfad {token!r} liegt außerhalb der freigegebenen Verzeichnisse."
            )

    def _validate_path(self, token: str) -> None:
        if token == ".." or token.startswith("../"):
            raise CodingCommandError("Coding-Pfade dürfen das Projektverzeichnis nicht verlassen.")
        if not re.search(r"(?:^|=)(?:-[A-Za-z]+)?/", token):
            return
        candidate = Path(token).expanduser().resolve()
        if candidate == Path(DEVNULL_PATH):
            return
        if not any(candidate == root or candidate.is_relative_to(root) for root in self.allowed_roots):
            raise CodingCommandError(
                f"Coding-Pfad {token!r} liegt außerhalb der freigegebenen Verzeichnisse."
            )


class StructuredCommandRunner:
    """Run an argv pipeline without shell=True or shell string interpretation."""

    def __init__(self, shell_tools: Any, allowed_commands: set[str], timeout: float):
        self.shell_tools = shell_tools
        self.allowed_commands = frozenset(allowed_commands)
        self.timeout = timeout

    def run(
        self,
        steps: list[dict[str, Any]],
        cwd: str | None = None,
        redirect_stdout: str | None = None,
        stdin: str | None = None,
        stderr: str = "capture",
    ) -> str:
        if not isinstance(steps, list) or not steps:
            raise CodingCommandError("steps muss mindestens einen Befehl enthalten.")
        if stdin is not None and (not isinstance(stdin, str) or len(stdin.encode("utf-8")) > 2_000_000):
            raise CodingCommandError("stdin muss eine UTF-8-Zeichenkette von maximal 2 MB sein.")
        if stderr not in {"capture", "discard"}:
            raise CodingCommandError("stderr muss 'capture' oder 'discard' sein.")
        workdir = self.shell_tools._resolve_cwd(cwd)
        prepared: list[list[str]] = []
        step_options: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise CodingCommandError("Jeder Pipeline-Schritt muss ein Objekt sein.")
            unknown = set(step) - {"program", "args", "stdin", "stderr", "redirect_stdout"}
            if unknown:
                raise CodingCommandError(
                    f"Unbekannte Pipeline-Option: {', '.join(sorted(unknown))}."
                )
            program = step.get("program")
            args = step.get("args", [])
            if "stdin" in step and index != 0:
                raise CodingCommandError("stdin ist nur für den ersten Pipeline-Schritt erlaubt.")
            if "stdin" in step and stdin is not None:
                raise CodingCommandError("stdin darf nicht gleichzeitig global und im Schritt gesetzt werden.")
            step_stderr = step.get("stderr", stderr)
            if step_stderr not in {"capture", "discard"}:
                raise CodingCommandError("stderr muss 'capture' oder 'discard' sein.")
            if not isinstance(program, str) or not program:
                raise CodingCommandError("program muss ein nichtleerer String sein.")
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise CodingCommandError("args muss eine Liste von Strings sein.")
            if any("\x00" in value for value in [program, *args]):
                raise CodingCommandError("NUL-Zeichen sind in Befehlen nicht erlaubt.")
            if Path(program).name not in self.allowed_commands:
                raise CodingCommandError(f"Kommando {Path(program).name!r} ist nicht freigegeben.")
            for arg in args:
                self.shell_tools._coding_validator.validate_argument_path(arg, Path(program).name in {"sed", "awk"})
            prepared.append([program, *args])
            step_options.append({
                "stdin": step.get("stdin"),
                "stderr": step_stderr,
                "redirect_stdout": step.get("redirect_stdout"),
            })
        output_target = None
        if redirect_stdout is not None:
            if not isinstance(redirect_stdout, str) or not redirect_stdout.strip():
                raise CodingCommandError("redirect_stdout muss ein Pfad sein.")
            if redirect_stdout.strip() == DEVNULL_PATH:
                output_target = Path(DEVNULL_PATH)
            else:
                output_target = self.shell_tools._resolve_coding_output_path(redirect_stdout)
                output_target.parent.mkdir(parents=True, exist_ok=True)
        input_text: str | None = stdin
        stdout = ""
        stderr_parts: list[str] = []
        returncodes: list[int] = []
        for index, argv in enumerate(prepared):
            options = step_options[index]
            if options["stdin"] is not None:
                input_text = options["stdin"]
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=workdir,
                    stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE if options["stderr"] == "capture" else subprocess.DEVNULL,
                    text=True,
                    env=self.shell_tools._safe_env(),
                )
            except OSError as exc:
                raise CodingCommandError(f"Start von {argv[0]!r} fehlgeschlagen: {exc}") from exc
            try:
                stdout, step_stderr = process.communicate(input=input_text, timeout=self.timeout)
                if step_stderr:
                    stderr_parts.append(step_stderr)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.communicate()
                raise CodingCommandError(
                    f"Zeitüberschreitung nach {self.timeout:g} Sekunden: {argv[0]}"
                ) from exc
            step_target = options.get("redirect_stdout")
            if step_target is not None:
                if not isinstance(step_target, str) or not step_target.strip():
                    raise CodingCommandError("redirect_stdout muss ein Pfad sein.")
                if step_target.strip() == DEVNULL_PATH:
                    target = Path(DEVNULL_PATH)
                else:
                    target = self.shell_tools._resolve_coding_output_path(step_target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(stdout, encoding="utf-8")
            input_text = stdout
            returncodes.append(process.returncode)
        if output_target is not None:
            output_target.write_text(stdout, encoding="utf-8")
        command_text = " | ".join(" ".join(argv) for argv in prepared)
        return self.shell_tools._format_result(
            [command_text], returncodes[-1], stdout, "".join(stderr_parts)
        )
