"""Human-readable Markdown session storage."""

from __future__ import annotations

import json
import re
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@dataclass
class SessionStore:
    directory: Path

    def __post_init__(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, session_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
        if safe_id != session_id:
            raise ValueError("Session-ID darf nur Buchstaben, Ziffern, _ und - enthalten.")
        return self.directory / f"{session_id}.md"

    def _sidecar_path(self, session_id: str) -> Path:
        return self.directory / f"{session_id}.json"

    def exists(self, session_id: str) -> bool:
        return self.path(session_id).is_file()

    @contextmanager
    def _lock(self, session_id: str, exclusive: bool) -> Iterator[None]:
        """Serialize access to a session across CLI and API processes."""
        sidecar = self._sidecar_path(session_id)
        with sidecar.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def append(self, session_id: str, role: str, content: str) -> None:
        self.append_message(session_id, {"role": role, "content": content})

    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        path = self.path(session_id)
        with self._lock(session_id, exclusive=True):
            sidecar = self._sidecar_path(session_id)
            history = self._load_sidecar(sidecar)
            if not history and path.exists():
                history = self._load_markdown(path)
            if not path.exists():
                path.write_text(
                    f"# FredTux-Sitzung: {session_id}\n\n"
                    f"Erstellt: {datetime.now(timezone.utc).isoformat()}\n\n",
                    encoding="utf-8",
                )
            content = str(message.get("content", ""))
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"## {message['role']}\n\n{content.rstrip()}\n\n")
            history.append(message)
            sidecar.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, session_id: str) -> list[dict[str, Any]]:
        if not self.exists(session_id):
            return []
        with self._lock(session_id, exclusive=False):
            return self._load_sidecar(self._sidecar_path(session_id)) or self._load_markdown(self.path(session_id))

    def _load_sidecar(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists() or not path.stat().st_size:
            return []
        try:
            messages = json.loads(path.read_text(encoding="utf-8"))
            return messages if isinstance(messages, list) else []
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _load_markdown(path: Path) -> list[dict[str, Any]]:
        text = path.read_text(encoding="utf-8")
        messages: list[dict[str, Any]] = []
        current_role: str | None = None
        chunks: list[str] = []
        for line in text.splitlines():
            match = re.fullmatch(r"## (system|user|assistant|tool)", line)
            if match:
                if current_role is not None:
                    messages.append({"role": current_role, "content": "\n".join(chunks).strip()})
                current_role = match.group(1)
                chunks = []
            elif current_role is not None and not line.startswith("# "):
                chunks.append(line)
        if current_role is not None:
            messages.append({"role": current_role, "content": "\n".join(chunks).strip()})
        return [message for message in messages if message["content"]]

    def list_sessions(self) -> list[str]:
        return sorted(path.stem for path in self.directory.glob("*.md"))
