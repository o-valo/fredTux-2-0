"""Abschaltbares Aktivitätsprotokoll: Anfragen, Runden, Werkzeuge, Zeiten.

Anders als :mod:`fredtux.errorlog` schreibt dieses Modul nicht nur Fehler,
sondern den normalen Ablauf. Es ist über die Konfiguration steuerbar
(``FREDTUX_LOG``, ``FREDTUX_LOG_LEVEL``, ``FREDTUX_LOG_FILE``) und im
Standardfall aus.

Jeder Datensatz ist eine Zeile JSON, damit ``tail -F`` und ``jq`` direkt
funktionieren. Schreibfehler dürfen eine Anfrage niemals abbrechen: sie werden
einmal auf ``stderr`` gemeldet und danach still übergangen.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEVELS = {"error": 0, "info": 1, "debug": 2}
DEFAULT_LEVEL = "info"
PREVIEW_CHARS = 200
FIELD_CHARS = 500


def preview(value: Any, limit: int = PREVIEW_CHARS) -> str:
    """Kürzt einen Wert für das Protokoll und macht Zeilenumbrüche lesbar."""
    text = str(value).replace("\n", "\\n").replace("\r", "\\r")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… ({len(text)} Zeichen)"


class ActivityLog:
    """Zeilenweises JSONL-Protokoll mit eigenem Ein-/Ausschalter."""

    def __init__(self, path: Path, enabled: bool = False, level: str = DEFAULT_LEVEL):
        self.path = Path(path)
        self.enabled = bool(enabled)
        self.level = level if level in LEVELS else DEFAULT_LEVEL
        self._threshold = LEVELS[self.level]
        self._lock_path = self.path.with_name(f".{self.path.name}.lock")
        self._write_failed = False

    def event(self, kind: str, session_id: str = "-", level: str = "info", **fields: Any) -> None:
        """Schreibt ein Ereignis, sofern das Protokoll an ist und das Level passt."""
        if not self.enabled:
            return
        if LEVELS.get(level, LEVELS[DEFAULT_LEVEL]) > self._threshold:
            return
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "session_id": session_id,
            "event": kind,
        }
        for key, value in fields.items():
            if value is None:
                continue
            record[key] = value if isinstance(value, (bool, int, float)) else preview(value, FIELD_CHARS)
        self._append(record)

    def tail_command(self) -> str:
        return f"tail -F {self.path}"

    def _append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock_path.open("a", encoding="utf-8") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    with self.path.open("a", encoding="utf-8") as stream:
                        stream.write(line)
                        stream.flush()
                        os.fsync(stream.fileno())
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except OSError as exc:  # Protokollieren darf die Anfrage nicht beenden.
            if not self._write_failed:
                self._write_failed = True
                print(f"FredTux: Aktivitätsprotokoll nicht schreibbar ({self.path}): {exc}", file=sys.stderr)


def elapsed_ms(started: float) -> int:
    """Millisekunden seit ``started`` (aus ``time.monotonic()``)."""
    return int((time.monotonic() - started) * 1000)
