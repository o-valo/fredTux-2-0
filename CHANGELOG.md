# Changelog

All notable changes to this project are documented here. The format follows
Keep a Changelog and the project uses semantic versioning.

## [0.6.0] - 2026-10-29

### Added
- **Systemüberblick beim Start** (`SYSTEM.md`, `FREDTUX_SYSTEM_BRIEFING`,
  Standard an): kurze Datei, die beim Sitzungsstart wörtlich in den Systemprompt
  geladen wird und nur den Weg in die Wissensbasis zeigt –
  `~/.fredtux-2.0/data/brain/rag/` samt `archiv/`, die drei Werkzeuge und die
  Reihenfolge, in der nachgeschlagen wird. Der Agent muss dafür nicht mehr im
  Home-Verzeichnis suchen; alles Weitere gehört als Eintrag ins RAG, das nur
  geladen wird, wenn es gebraucht wird. `FREDTUX_SYSTEM_FILE` ändert den Pfad,
  `FREDTUX_SYSTEM_MAX_CHARS` (Standard 1200) begrenzt die Kosten im Prefill;
  `reload_rules` lädt Regeln und Überblick gemeinsam neu.
- **Denkausgabe im Stream:** `reasoning_content`, `reasoning` und `thinking`
  aus der Upstream-Antwort werden weitergereicht. Streaming-Clients erhalten
  sie als `delta.reasoning_content`, getrennt vom Antworttext.
- Runden- und Werkzeugmarker gehen zusätzlich als Denkausgabe an den Client,
  damit Schweigen im Stream immer erklärt ist.
- **Transparenzprotokoll** (`fredtux/streamlog.py`, `FREDTUX_STREAM_LOG`,
  Standard an): `<home>/logs/stream.log` schreibt jedem Lauf live mit –
  Rundenbeginn, Denkausgabe, Werkzeugaufrufe samt Ergebnis und Dauer sowie den
  sichtbaren Text, jede Zeile mit Zeitstempel. Mit `tail -F` sieht man, ob ein
  Lauf noch arbeitet oder auf ein Zeitlimit zuläuft, lange bevor es greift.
- Automatische Context-Verdichtung (`fredtux/compaction.py`): überschreitet die
  Historie `FREDTUX_CONTEXT_LIMIT`, werden die ältesten Runden vom Modell
  zusammengefasst, als Systemnachricht an Position 1 in den Prompt zurückgegeben
  und aus der Nachrichtenliste entfernt. Die Sitzungsdateien bleiben vollständig –
  gekürzt wird nur die Liste, die an das Modell geht.
- Verdichtete Runden werden unter `<RAG>/archiv/` abgelegt und sind über
  `search_knowledge` mit `include_archives=true` wieder auffindbar. Ohne dieses
  Argument durchsucht die Suche nur die eigentlichen Notizen, damit die
  zahlreichen Archive sie nicht aus den Top-5-Treffern verdrängen.
- Aktivitätsprotokoll (`fredtux/activitylog.py`), über die Konfiguration
  schaltbar: `FREDTUX_LOG=1` schreibt Anfragen, Modellrunden, Werkzeugaufrufe und
  Dauern als JSON Lines nach `<FREDTUX_HOME>/logs/fredtux.jsonl`
  (`FREDTUX_LOG_FILE` ändert den Pfad, `FREDTUX_LOG_LEVEL=debug` ergänzt die
  HTTP-Zugriffszeilen). Standard ist **aus**. Ereignisse: `request.start`,
  `llm.reply`, `llm.error`, `tool.call`, `request.end` (mit `status`, Runden und
  Gesamtdauer), dazu `http.request`, `http.response`, `http.reject` und
  `http.abort`. Prompts und Antworten werden nicht im Wortlaut gespeichert, nur
  Längen. Ein nicht beschreibbares Log bricht keine Anfrage ab.
- Eine Zeile je Anfrage auf stdout (`client`, `session`, `status`, `wait_ms`,
  `duration_ms`, `chunks`/`chars`). Unter systemd landet sie in `api.log` und
  zeigt auch ohne `FREDTUX_LOG=1`, wer den Knoten belegt.
- Der HTTP-Server protokolliert auch den Antwortweg: Erfolg, Fehler,
  abgebrochene Streams und die Zahl der SSE-Chunks. Bisher war bei einer
  hängenden Anfrage überhaupt nichts nachvollziehbar.
- `FREDTUX_QUEUE_TIMEOUT` (Standard 300 s): begrenzt, wie lange eine Anfrage
  auf den einen Laufplatz wartet. Danach antwortet der Server mit HTTP 429 und
  `Retry-After`, statt den Client bis zu dessen eigenem Zeitlimit hängen zu
  lassen. `0` wartet nicht, ein negativer Wert wartet unbegrenzt (altes
  Verhalten). Die Ablehnung nennt, wer den Platz hält und seit wann.
- `FREDTUX_MAX_TOOL_OUTPUT` (Standard 8000): Werkzeugergebnisse werden in der
  Mitte gekappt, Anfang und Ende bleiben lesbar, mit Hinweis auf die
  Gesamtlänge. Ein einzelnes `curl` oder `cat` kann den Context sonst
  vollständig auffrisen.
- `FREDTUX_NUM_CTX` (Standard 0 = Server-Default): wird als `options.num_ctx`
  pro Anfrage mitgeschickt. Wirkt nur bei Servern, die das auswerten – Ollama
  ignoriert es über den OpenAI-kompatiblen Endpunkt und bleibt bei 32768.

### Fixed
- Abbruch mit HTTP 400 „request exceeds the available context size": die Historie
  wuchs unbegrenzt, weil `core.py` nur anhängte und nie etwas entfernte. Ein
  einzelner Werkzeugaufruf über 45 KB Zeichen hatte eine Sitzung auf über
  100 KB gebracht.
- Die HTTP-Zugriffszeile auf `stdout` wurde gepuffert und landete bei
  `StandardOutput=append:` erst beim Prozessende in der Datei – also praktisch
  nie. `print(..., flush=True)` und die Protokollzeile beheben das.
- Ein Client, der während der Wartezeit aufgibt, wird erkannt (Socket wird nur
  befragt, nicht gelesen) und startet keinen Lauf mehr. Bisher lief die Anfrage
  trotzdem los und blockierte den einzigen Laufplatz.
- Falscher Chat-Endpunkt fällt jetzt beim Start auf statt erst bei der ersten Eingabe:
  Die CLI prüft vor dem Prompt `GET <FREDTUX_BASE_URL>/models` (10 s, ohne Modell zu laden)
  und bricht mit Exit-Code 2 ab, wenn dort nichts antwortet. Ursache war eine `config.nd`
  auf `gift`, in der `FREDTUX_OLLAMA_URL` auf `10.7.0.24` zeigte (Vorcheck lief durch,
  Modell gefunden) und `FREDTUX_BASE_URL` auf den eigenen Rechner `192.168.200.216`, wo
  nichts auf Port 11434 lauscht – „Connection refused" erst nach dem Tippen der ersten
  Nachricht und ohne Hinweis auf die falsche Zeile. Die Fehlermeldungen des LLM-Clients
  nennen jetzt den Endpunkt, den HTTP-Status samt Servermeldung bzw. bei Zeitüberschreitung
  das Limit und den Hinweis auf `FREDTUX_TIMEOUT` (kalte/große Modelle brauchen beim ersten
  Aufruf länger als die 120 s Standard, auf dem Testknoten gemessen). `scripts/devcheck.py`
  prüft den Endpunkt ebenso; `--no-ollama-check` überspringt beide Prüfungen.
  Sieben neue Tests in `tests/test_llm.py`, Doku in README.md und README.ger.md.
- `fredtux-install.sh` übernimmt eine vorhandene `.venv` nur noch, wenn sie zu Python 3.10
  oder neuer passt und `pip` enthält. Vorher genügte ein `.venv`-Ordner mit `bin/python`,
  wie ihn ein abgebrochener `python3 -m venv`-Lauf auf Systemen ohne `python3-venv`
  hinterlässt: Der nächste Aufruf brach dann mit `No module named pip` ab (beobachtet auf
  `gift`, Ubuntu 24.04, Konto `bot`). Fehlt `pip`, wird es jetzt per `ensurepip`
  nachinstalliert, sonst die Umgebung neu erstellt. Die Vorabprüfung fragt zusätzlich
  `python3 -m ensurepip --version` ab, damit fehlende Systempakete gleich mitinstalliert
  werden – `python3 -m venv --help` gelingt auch ohne `python3-venv`, die Prüfung schlug
  also nicht an. Beides steht in README.md und README.ger.md.

Zur Verdichtung: die Hysterese feuert erst ab 75 % der Grenze und frühestens nach
zwölf neuen Nachrichten. Ohne diese Bremse lief sie im eingeschwungenen Zustand
bei praktisch jedem Aufruf und kostete jedes Mal einen zusätzlichen Modellaufruf.
Die Schnittkarte trennt niemals ein Werkzeugpaar – eine `tool`-Nachricht ohne
vorhergehenden Assistenten mit `tool_calls` lehnt der OpenAI-Endpunkt ab. Für 39
Historiegrößen geprüft. Ohne funktionierendes Modell fällt die Zusammenfassung
auf einen extraktiven Rückfall zurück, statt den Prompt ungekürzt zu lassen.

Gemessen an einem aufzeichnenden Modell-Stub: maximaler Prompt über 30 Runden
von 37.926 auf 12.489 Zeichen (−67 %), Grenze eingehalten.

110 Tests grün: 30 Kern, 24 Verdichtung, 21 Aktivitätsprotokoll, 9 LLM,
8 API, 7 Shell, 5 Konfiguration, 3 Backup, 3 Ollama.

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
