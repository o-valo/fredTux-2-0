"""Mitlaufende Läufe – was gerade rechnet und was davon schon sichtbar ist.

Der Hintergrund: ein Lauf gehört zur *Sitzung*, nicht zur Verbindung. Ein Client
kann mitten im Lauf verschwinden; die Antwort landet trotzdem in der Sitzung.
Damit ein zweiter Client (anderes Gerät, andere App) demselben Lauf zusehen kann,
muss der Text aber *während* des Laufs irgendwo ankommen - genau das leistet der
Puffer hier. Ohne ihn gäbe es nur das Ergebnis am Ende.
"""

from __future__ import annotations

import threading
import time


class Run:
    """Ein laufender Lauf: Puffer, Zustand und die Zeit, die er schon braucht."""

    def __init__(self, session_id: str, client: str = "-") -> None:
        self.session_id = session_id
        self.client = client
        self.started = time.monotonic()
        self.error: str | None = None
        self._parts: list[str] = []
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._cancel = threading.Event()

    def append(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._parts.append(text)

    def text(self) -> str:
        with self._lock:
            return "".join(self._parts)

    def chars(self) -> int:
        with self._lock:
            return sum(len(part) for part in self._parts)

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def age(self) -> int:
        return int(time.monotonic() - self.started)

    def cancel(self) -> None:
        """Bittet den Lauf abzubrechen – was bis dahin geantwortet wurde, bleibt stehen.

        Abgebrochen wird zwischen zwei Stücken, nicht mitten im Modellaufruf: der
        Aufruf selbst ist nicht unterbrechbar, das nächste Stück aber wird nicht
        mehr angefordert.
        """
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def finish(self) -> None:
        self._done.set()

    def wait(self, timeout: float | None) -> bool:
        """Wartet auf das Ende. ``None`` heißt unbegrenzt; True = fertig."""
        return self._done.wait(timeout)

    def describe(self) -> str:
        if self.finished:
            zustand = "fertig"
        elif self.cancelled:
            zustand = "wird abgebrochen"
        else:
            zustand = "läuft"
        text = f"{self.session_id}: {zustand} seit {self.age()} s, {self.chars()} Zeichen"
        if self.client and self.client != "-":
            text += f", Client {self.client}"
        return text


class RunRegistry:
    """Die laufenden Läufe, nach Sitzung geordnet.

    Bewusst einfach gehalten: es gibt einen Laufplatz, also höchstens einen Lauf
    pro Sitzung. Ein neuer Lauf zur selben Sitzung ersetzt den alten Eintrag –
    er hat dann auch den Platz, der alte ist beendet.
    """

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def begin(self, session_id: str, client: str = "-") -> Run:
        run = Run(session_id, client)
        with self._lock:
            self._runs[session_id] = run
        return run

    def finish(self, run: Run) -> None:
        """Markiert den Lauf als fertig – der Puffer bleibt lesbar.

        Der Eintrag wird bewusst nicht sofort entfernt: ein Client, der sich
        knapp nach dem Ende anhängt, soll die Antwort noch bekommen, auch wenn
        er die Sitzungsdatei nicht selbst lesen kann. Ersetzt wird der Eintrag
        beim nächsten Lauf derselben Sitzung.
        """
        run.finish()

    def get(self, session_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(session_id)

    def active(self) -> list[Run]:
        with self._lock:
            return [run for run in self._runs.values() if not run.finished]
