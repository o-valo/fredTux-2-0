# Changelog

All notable changes to this project are documented here. The format follows
Keep a Changelog and the project uses semantic versioning.

## [Unreleased]

## [0.5.0] - 2026-10-07

### Changed
- README: „OpenAI-kompatibler Endpunkt: vier Zeilen genügen“ als vollständiges Rezept
  (BASE_URL, MODEL, API_KEY, SKIP_OLLAMA_CHECK) an den Anfang des `config.nd`-Abschnitts
  gestellt – mit Bedienungs-Bullets, curl-Erstcheck, Hinweis auf Exit-Code 2 ohne Skip
  und auf ganzzeilige `#`-Kommentare; Quickstart-One-Liner mit venv-Aktivierung ergänzt,
  `.nd`-Endung erklärt, doppeltes `find` korrigiert, Release-Abschnitt auf 0.5.0 angehoben.
- **Umbenennung Fred 2.0 → FredTux** (01.10.2026, Auftrag aus `AUFTRAG.md`).
  Der Agent heißt jetzt überall FredTux: Ordnername `~/fredTux-2-0` (Entwicklung)
  und `~/GITHUB-Projekte/fredTux-2-0` (Veröffentlichung), Python-Modul `fredtux`,
  CLI `fredtux` und `fredtux-api`, Paketname `fredtux-2.0`, Laufzeitverzeichnis
  `~/.fredtux-2.0`, Umgebungsvariablen `FRED_*` → `FREDTUX_*`, virtuelle Modell-ID
  `fredtux-2-0` (Kompatibilitätsname `fredtux-2.0`), API-Feld `fredtux_session_id`,
  Session-Header `X-FredTux-Session-ID`, Logpräfix `FredTux-API`, Skripte
  `fredtux-install.sh` und `scripts/backup_fredtux.sh`, Backup-Archivname
  `fredtux-2.0-backup-*.tgz` inklusive Zielordner `~/BACKUP/fredtux-2.0-backups`.
  Die Version geht mit diesem Stand auf 0.5.0; das separate Projekt **Freddy** (`~/freddy-1.0`) ist
  davon unberührt. **Achtung:** eine alte `config.nd` mit `FRED_*`-Schlüsseln
  wird nicht mehr gelesen, die Schlüssel müssen `FREDTUX_*` heißen.
- `pyproject.toml` deklariert die Pakete jetzt ausdrücklich
  (`[tool.setuptools] packages`). Die Flat-Layout-Erkennung von Setuptools wertet
  sonst jedes Top-Level-Verzeichnis als potenzielles Paket – auch das
  maschinenlokale `bugs/` – und `pip install -e .` scheitert mit
  "Multiple top-level packages discovered".

### Added
- `FREDTUX_SHELL_EXTRA_ROOTS` als kommagetrennte Zusatzpfade für Coding-Lese-, Arbeits-
  und Zielpfade (Standard in `shell.nd`: `~/BACKUP` für das Backup-Verzeichnis) plus
  `/dev/null` als immer erlaubtes Umleitungsziel im Coding-Modus. Coding-Ausgaben
  dürfen dadurch in `~/BACKUP/fredtux-2.0-backups/` geschrieben werden; das Backup-Skript
  legt Backups standardmäßig dort ab.
- Coding-Allowlist um die im Betrieb benötigten Text-, Vergleich-, Archiv-, Prozess-
  und Diagnosewerkzeuge erweitert: `sed`, `awk`, `xargs`, `uniq`, `cut`, `tr`, `nl`,
  `paste`, `join`, `comm`, `column`, `fold`, `expand`, `split`, `csplit`, `diff`,
  `patch`, `md5sum`, `sha256sum`, `base64`, `ps`, `kill`, `timeout`, `watch`, `nc`,
  `telnet`, `dig`, `ss`, `zip`, `unzip`, `gzip`, `xz`, `realpath`, `readlink`, `file`,
  `install`, `uuidgen`, `tee`, `od` und `hexdump`. `python` und `fzf` bleiben nicht
  freigegeben; `python3` ist der vorgesehene Interpreter.
- Wiederholte fehlerhafte Werkzeugaufrufe werden nach dem zweiten identischen Fehler
  beziehungsweise nach drei aufeinanderfolgenden Fehlern früh beendet.
- `CODING_AGENT.md` wird als verbindlicher Coding-Systemprompt geladen und verhindert
  wiederholte Tool-Aufrufe, unzulässige Shell-Eingaben und unnötige RAG-Schleifen.
- Strukturierte `run_coding_command`-Pipeline ohne `shell=True` als bevorzugte API;
  unterstützt globales und schrittweises `stdin`, `stderr` und `redirect_stdout`.
  Der Legacy-String-Validator liegt jetzt gekapselt in `fredtux.tools.coding`.
- Der Coding-Validator respektiert Shell-Syntax in quotierten Argumenten, etwa RSS-Titel-
  Filter mit `<title>`; Backups erhalten eindeutige Nanosekunden-Zeitstempel.
- OpenAI-kompatibler lokaler HTTP-Server unter `/v1` mit `/health`, `/v1/models`
  und `/v1/chat/completions`.
- `config.nd` als schneller KEY=WERT-Endpunktschalter.
- API-Session-Fortsetzung über `fredtux_session_id`, `session_id` oder `X-FredTux-Session-ID`.
- Konfigurierbares virtuelles API-Modell `fredtux-2-0` mit Alias `fredtux-2.0`.
- Sicherheitsgestufte Shell- und Dateiwerkzeuge (`allowlist`, `standard`, `yolo`).
- Vollständige CLI- und Installationsdokumentation.
- `.venv`-basierter Editable-Install und `scripts/devcheck.py`.
- GitHub-Actions-CI für Python 3.10–3.12.
- Issue- und Pull-Request-Templates.
- Architektur-, Betriebs- und Abhängigkeitsdokumentation.
- Backup-Skript `scripts/backup_fredtux.sh` mit Aufbewahrungs-Schalter `--keep N`
  und Makefile-Target `make backup` (Argumente per `ARGS=...` durchgereicht).
- Dauerhafte RAG-Dokumentation des Setups (`fredtux-2-0-setup-architektur.md`).

## [0.1.1] - 2026-09-25

### Fixed
- Der Agentenloop bricht nicht mehr nach einer festen Rundenzahl ab. Erfolgreiche
  Werkzeugaufrufe galten zuvor genauso wie Fehlversuche; Aufgaben mit vielen
  nacheinander nötigen Werkzeugen (mehrere Dateien schreiben und prüfen) endeten
  mit `FEHLER: Maximale Anzahl von Werkzeugschleifen erreicht.`. Jetzt zählt eine
  Runde nur dann ohne Fortschritt, wenn *kein* Werkzeugaufruf ohne `FEHLER`
  beantwortet wurde; die Abbruchmeldung nennt Rundenzahl, Zahl der Runden ohne
  Fortschritt und den letzten Werkzeugaufruf. Die harte `range(8)`-Grenze in
  `fredtux/core.py` ist entfallen.
- Endlosschleifen bleiben ausgeschlossen: `FREDTUX_MAX_TOTAL_ROUNDS` (Standard 40)
  begrenzt die Gesamtzahl der Runden, `FREDTUX_MAX_IDLE_ROUNDS` (Standard 6) die
  Zahl aufeinanderfolgender Runden ohne Fortschritt, und `_tool_loop_error`
  beendet wiederholte Fehlschläge unverändert sofort.

### Added
- Neues Werkzeug `reload_rules`: lädt `CODING_AGENT.md` in den laufenden
  System-Prompt, ohne die Sitzung zu wechseln. Damit ist der Selbstlern-Kreislauf
  geschlossen – der Agent kann eine Regel per `write_file` ändern und sie im
  selben Gespräch wirksam machen, statt bis zum nächsten Start zu warten. Der
  Aufruf ersetzt nur die Systemnachricht, der Gesprächsverlauf bleibt unangetastet,
  und die Antwort nennt Zeilenzahl und Zeilendifferenz.
- `ToolRegistry.register()` für Werkzeuge, die der Agentenkern zur Laufzeit
  anmeldet.
- `FREDTUX_MAX_IDLE_ROUNDS` und `FREDTUX_MAX_TOTAL_ROUNDS` als konfigurierbare
  Schleifengrenzen in `config.nd`/`config.nd.example` und README.
- Regel 14 in `CODING_AGENT.md`: Nach jeder Änderung an der Regeldatei
  `reload_rules` aufrufen.
- Regressionstests für Viel-Tool-Aufgaben, Endlosschleifen, Idle-Abbruch und
  Zurücksetzen des Fortschrittszählers (32 Tests gesamt, grün).

## [0.1.0] - 2026-09-24

### Added
- Modularer Python-Agenten-Loop mit OpenAI-kompatibler Chat-Schnittstelle.
- Native Ollama-Diagnose über `/api/version`, `/api/tags` und `/api/ps`.
- Markdown-Sitzungen mit JSON-Sidecar und Datei-Locking.
- Dateibasiertes RAG mit `save_knowledge`, `search_knowledge` und `list_knowledge`.
- CLI-Sitzungswechsel über Session-ID.

### Known limitations
- Keine öffentliche HTTP-Authentifizierung, TUI- oder MCP-Anbindung.
- Keine rotierende Logdatei und keine produktionsreife Authentifizierung.
