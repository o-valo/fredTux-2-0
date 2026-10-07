"""Interactive shell interface."""

from __future__ import annotations

import argparse
import sys

from ..config import Config
from ..core import AgentCore
from .api import serve
from ..llm import LLMClient, OllamaError


HELP = """Befehle:
  /help                 Diese Hilfe anzeigen
  /sessions             Sitzungen anzeigen
  /session <ID>         Bestehende Sitzung fortsetzen
  /new                  Neue Sitzung beginnen
  /exit                 Beenden
Alles andere wird als normale Nachricht an FredTux gesendet.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="FredTux 2.0 – modularer Agent")
    parser.add_argument("--session", help="Bestehende Session-ID fortsetzen")
    parser.add_argument(
        "--no-ollama-check",
        action="store_true",
        help="Prüfung von Ollama, Modell und geladenen Modellen überspringen",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="OpenAI-kompatiblen HTTP-Server statt interaktiver CLI starten",
    )
    parser.add_argument("--host", default=None, help="Bind-Adresse für --serve; überschreibt FREDTUX_API_HOST")
    parser.add_argument("--port", type=int, default=None, help="Port für --serve; überschreibt FREDTUX_API_PORT")
    args = parser.parse_args()

    try:
        config = Config.from_env()
    except (OSError, ValueError) as exc:
        print(f"Start fehlgeschlagen: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.serve:
        serve(config, args.host or config.api_host, args.port or config.api_port)
        return

    if args.no_ollama_check or config.skip_ollama_check:
        reason = "config.nd" if config.skip_ollama_check and not args.no_ollama_check else "Option"
        print(f"Ollama-Prüfung übersprungen ({reason}).")
    else:
        try:
            status = LLMClient(config).check_ollama()
        except OllamaError as exc:
            print("Ollama-Verbindung fehlgeschlagen:", file=sys.stderr)
            print(str(exc), file=sys.stderr)
            print("\nHinweis: Mit --no-ollama-check kann der Chat auch ohne Vorprüfung gestartet werden.", file=sys.stderr)
            raise SystemExit(2) from exc
        print(status.summary())

    try:
        agent = AgentCore(config=config, session_id=args.session)
    except (OSError, ValueError) as exc:
        print(f"Start fehlgeschlagen: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"FredTux 2.0 – Sitzung {agent.session_id}")
    print("Gib /help für Befehle ein.")
    while True:
        try:
            text = input("\nDu > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBis bald!")
            return
        if not text:
            continue
        if text in {"/exit", "/quit"}:
            print("Bis bald!")
            return
        if text == "/help":
            print(HELP)
            continue
        if text == "/sessions":
            sessions = agent.sessions.list_sessions()
            print("\n".join(f"- {session}" for session in sessions) or "(keine Sitzungen)")
            continue
        if text == "/new":
            print(f"Neue Sitzung: {agent.new_session()}")
            continue
        if text.startswith("/session "):
            session_id = text.removeprefix("/session ").strip()
            try:
                agent.switch_session(session_id)
                print(f"Sitzung {session_id} geladen.")
            except (FileNotFoundError, ValueError) as exc:
                print(f"FEHLER: {exc}")
            continue
        try:
            print(f"\nFredTux > {agent.ask(text)}")
        except Exception as exc:  # CLI bleibt auch bei Backend-/Netzwerkfehlern bedienbar.
            print(f"FEHLER: {exc}", file=sys.stderr)
