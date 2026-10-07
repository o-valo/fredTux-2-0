# Contributing to FredTux 2.0 / Beiträge zu FredTux 2.0

**Languages:** [Deutsch](#deutsch) · [English](#english)

<a id="deutsch"></a>

## Deutsch

Danke für Beiträge. Das Projekt ist ein kleiner Python-Agenten-Harness unter AGPL-3.0-or-later.

### Entwicklungsumgebung

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-deps --editable .
.venv/bin/python scripts/devcheck.py --no-ollama-check
```

Es werden keine externen Runtime-Abhängigkeiten benötigt. Python 3.10, 3.11 und 3.12
werden in CI getestet.

### Pflichtprüfungen vor einem Pull Request

```bash
.venv/bin/python -m compileall -q .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/devcheck.py --no-ollama-check
.venv/bin/fredtux --help
git diff --check
```

Live-Ollama-Tests sind optional und gehören nicht in die Standard-CI, weil sie von
einem internen Netzwerkhost und einem installierten Modell abhängen.

### Entwicklungsregeln

- Öffentliche Funktionen und CLI-Texte auf Deutsch dokumentieren, wenn sie für den
  Betreiber relevant sind.
- Keine Geheimnisse, API-Keys, Session-Dateien oder RAG-Inhalte committen.
- Neue externe Python-Abhängigkeiten müssen in `pyproject.toml` und
  [`docs/DEPENDENCIES.ger.md`](docs/DEPENDENCIES.ger.md) eingetragen werden.
- Neue Werkzeuge brauchen eine explizite Tool-Registry und Tests.
- Änderungen an Session-Persistenz müssen mit einer Round-Trip-Prüfung abgesichert
  werden.
- API- oder Datenformatänderungen benötigen eine Aktualisierung von `README.ger.md`,
  `README.md` und `CHANGELOG.md`.
- Neue oder geänderte Doku unter `docs/` wird zweisprachig gepflegt:
  `NAME.md` (Englisch) und `NAME.ger.md` (Deutsch) mit gegenseitigem Sprachumschalter.

### Commit- und PR-Konventionen

Kleine, nachvollziehbare Commits verwenden. PR-Beschreibungen müssen Problem,
Lösung, Tests und bekannte Einschränkungen nennen. Keine force-pushes auf `main`.

### Kontakt und Sicherheitsmeldungen

Normale Fragen gehören in Issues oder Pull Requests. Sicherheitsrelevante Meldungen
bitte nicht öffentlich mit Secrets posten; siehe [`SECURITY.md`](SECURITY.md).

---

<a id="english"></a>

## English

Thanks for contributing. The project is a small Python agent harness under
AGPL-3.0-or-later.

### Development environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-deps --editable .
.venv/bin/python scripts/devcheck.py --no-ollama-check
```

No external runtime dependencies are required. Python 3.10, 3.11, and 3.12 are
tested in CI.

### Mandatory checks before a pull request

```bash
.venv/bin/python -m compileall -q .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/devcheck.py --no-ollama-check
.venv/bin/fredtux --help
git diff --check
```

Live Ollama tests are optional and are not part of standard CI, because they
depend on an internal network host and an installed model.

### Development rules

- Document public functions and CLI texts in German when they are relevant to
  the operator.
- Do not commit secrets, API keys, session files, or RAG content.
- New external Python dependencies must be entered in `pyproject.toml` and in
  [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).
- New tools need an explicit tool registry and tests.
- Changes to session persistence must be covered by a round-trip check.
- API or data format changes require an update of `README.md`, `README.ger.md`,
  and `CHANGELOG.md`.
- New or changed documentation under `docs/` is maintained bilingually:
  `NAME.md` (English) and `NAME.ger.md` (German) with a language switcher in
  each file.

### Commit and PR conventions

Use small, comprehensible commits. PR descriptions must name the problem, the
solution, the tests, and known limitations. No force-pushes to `main`.

### Contact and security reports

Ordinary questions belong in issues or pull requests. Please do not post
security-relevant reports publicly with secrets; see
[`SECURITY.md`](SECURITY.md).
