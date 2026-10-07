"""Append-only error logging for diagnosing FredTux while it is running."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class ErrorLog:
    """Write complete, line-oriented error records suitable for ``tail -F``."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_name(f".{self.path.name}.lock")

    def write(self, category: str, message: str, session_id: str = "-") -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "category": category,
            "message": str(message).replace("\n", "\\n"),
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock_path.open("a", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(line)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def tail_command(self) -> str:
        return f"tail -F {self.path}"
