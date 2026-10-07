# Abhängigkeiten und Versionsstrategie

> Sprache: Deutsch | [English](DEPENDENCIES.md)

## Python-Laufzeit

- Mindestversion: Python 3.10
- Entwicklungs- und CI-Referenz: Python 3.12
- Unterstützt werden 3.10, 3.11 und 3.12.
- FredTux benutzt keine externen Laufzeitpakete.

Die Laufzeit verwendet ausschließlich die Standardbibliothek, unter anderem
`urllib`, `json`, `pathlib`, `dataclasses`, `argparse`, `unittest`, `re`, `fcntl`
und `contextlib`.

## Build und Entwicklung

`pyproject.toml` verwendet PEP 517 mit `setuptools>=68` als Build-Backend.
Setuptools wird nur beim Erzeugen bzw. Editable-Installieren des Projekts benötigt,
nicht beim normalen Start innerhalb der fertigen `.venv`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-deps --editable .
```

`--no-deps` ist korrekt, weil das Projekt derzeit keine Runtime-Dependencies hat.
Falls später Bibliotheken hinzukommen, müssen sie in `[project].dependencies`
und in `docs/DEPENDENCIES.ger.md` eingetragen werden.

## Externe Dienste

Ollama ist ein optionaler Laufzeitdienst, keine Python-Abhängigkeit. Die
Standard-Diagnose verwendet den nativen Ollama-Endpunkt. Eine andere
OpenAI-kompatible API kann mit `FREDTUX_BASE_URL` und `FREDTUX_API_KEY` konfiguriert
werden; dafür muss `--no-ollama-check` verwendet werden.

## Verschlüsselung und Geheimnisse

`FREDTUX_API_KEY` gehört nicht in `.env.example`, CI-Logs oder Git-History. Für GitHub
Actions ist ein Repository-Secret nur nötig, wenn später echte externe API-Tests
hinzukommen. Die normale CI verwendet keine Geheimnisse.
