"""Mitschreibendes Transparenzprotokoll: einem Lauf live zusehen.

Anders als das Aktivitätsprotokoll (``fredtux.jsonl``, standardmäßig aus)
schreibt dieses Protokoll **jedes** Ereignis eines Laufs mit Zeitstempel in
eine Textdatei: Rundenbeginn, Denkausgabe des Modells, Werkzeugaufrufe und
deren Ergebnis, sichtbarer Text.

Damit sieht man mit ``tail -F <pfad>``, was der Agent gerade tut – und vor
allem, **wann zuletzt etwas passiert ist**. Ein Lauf, der auf ein Timeout
zuläuft, bleibt dort sichtbar stehen; ein gesunder Lauf schreibt weiter.

Die Datei wird nur angehängt und nach jeder Zeile geleert (``flush``), damit
``tail`` sofort mitliest. Schreibfehler dürfen eine Anfrage niemals abbrechen.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Längere Zeilen werden gekürzt; der Rest steht ohnehin in der Sitzung.
MAX_ZEICHEN = 400


def _kurz(text: str, limit: int = MAX_ZEICHEN) -> str:
    text = str(text).replace("\n", "\\n").replace("\r", "\\r")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… ({len(text)} Zeichen)"


class StreamLog:
    """Zeilenweise Textdatei mit Zeitstempel, für ``tail -F`` gedacht."""

    def __init__(self, path: Path, enabled: bool = True):
        self.path = Path(path)
        self.enabled = bool(enabled)
        self._fehler_gemeldet = False

    def line(self, text: str) -> None:
        """Schreibt eine Zeile mit Zeitstempel (Millisekunden)."""
        if not self.enabled:
            return
        zeit = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as datei:
                datei.write(f"{zeit}  {_kurz(text)}\n")
                datei.flush()
        except OSError as exc:  # Protokollieren darf den Lauf nicht beenden.
            if not self._fehler_gemeldet:
                self._fehler_gemeldet = True
                print(
                    f"FredTux: Transparenzprotokoll nicht schreibbar ({self.path}): {exc}",
                    file=sys.stderr,
                )

    def tail_command(self) -> str:
        return f"tail -F {self.path}"
