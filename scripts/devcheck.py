#!/usr/bin/env python3
"""Installations- und Startcheck für FredTux 2.0.

Ausführen mit:
    .venv/bin/python scripts/devcheck.py
    .venv/bin/python scripts/devcheck.py --no-ollama-check
"""

from __future__ import annotations

import argparse
import importlib.metadata
import shutil
import sys
from pathlib import Path

from fredtux.config import Config
from fredtux.llm import LLMClient, OllamaError
from fredtux.tools.shell import ShellTools


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="FredTux-2.0-Installations- und Startcheck")
    parser.add_argument(
        "--no-ollama-check",
        action="store_true",
        help="Nur Python-, Installations- und Dateisystemprüfung ausführen",
    )
    args = parser.parse_args()

    print(f"Python: {sys.executable}")
    print(f"Version: {platform_version()}")
    if sys.prefix == sys.base_prefix:
        print("FEHLER: Nicht in einer virtuellen Umgebung gestartet.", file=sys.stderr)
        print("      Verwende: .venv/bin/python scripts/devcheck.py", file=sys.stderr)
        return 2
    if sys.version_info < (3, 10):
        print("FEHLER: FredTux 2.0 benötigt Python 3.10 oder neuer.", file=sys.stderr)
        return 2
    print(f"venv: {sys.prefix}")

    try:
        import fredtux
        from fredtux.core import AgentCore
        from fredtux.interfaces.cli import main as cli_main
    except ImportError as exc:
        print(f"FEHLER: FredTux-Module nicht importierbar: {exc}", file=sys.stderr)
        return 2
    print(f"FredTux-Modul: {fredtux.__version__}")

    try:
        version = importlib.metadata.version("fredtux-2.0")
    except importlib.metadata.PackageNotFoundError:
        print("FEHLER: fredtux-2.0 ist nicht in dieser venv installiert.", file=sys.stderr)
        return 2
    console_script = Path(sys.executable).with_name("fredtux")
    print(f"Paket: fredtux-2.0 {version}")
    print(f"Console-Script: {console_script if console_script.exists() else shutil.which('fredtux') or 'FEHLT'}")
    if not console_script.exists() and not shutil.which("fredtux"):
        print("FEHLER: Das Entry-Point-Skript 'fredtux' fehlt.", file=sys.stderr)
        return 2

    try:
        config = Config.from_env()
        config.ensure_dirs()
        print(f"Home: {config.home}")
        print(f"Sessionen: {config.sessions_dir}")
        print(f"RAG: {config.rag_dir}")
        print(f"API: http://{config.api_host}:{config.api_port}/v1")
        print(f"API-Modell: {config.api_model} (Upstream: {config.model})")
        print(ShellTools(config).describe())
    except (OSError, ValueError) as exc:
        print(f"FEHLER: Laufzeitverzeichnisse nicht nutzbar: {exc}", file=sys.stderr)
        return 2

    if args.no_ollama_check or config.skip_ollama_check:
        reason = "config.nd" if config.skip_ollama_check and not args.no_ollama_check else "Option"
        print(f"Ollama-Prüfung: übersprungen ({reason})")
    else:
        try:
            status = LLMClient(config).check_ollama()
        except OllamaError as exc:
            print(f"FEHLER: {exc}", file=sys.stderr)
            print("Hinweis: Mit --no-ollama-check lässt sich die lokale Installation allein prüfen.", file=sys.stderr)
            return 2
        print(f"Ollama: {status.summary()}")

    # Importiert die CLI und prüft damit den echten Startpfad ohne Eingabe.
    if not callable(cli_main) or not callable(AgentCore):
        print("FEHLER: Startfunktionen sind nicht aufrufbar.", file=sys.stderr)
        return 2
    print(f"Projektpfad: {PROJECT_ROOT}")
    print("Startcheck: OK")
    return 0


def platform_version() -> str:
    import platform

    return platform.python_version()


if __name__ == "__main__":
    raise SystemExit(main())
