<p align="center">
  <img src="fredTux-2-0.png" alt="FredTux 2.0 Logo" width="100%">
</p>


# FredTux 2.0

- Sprache: Deutsch | [English version](README.md)

FredTux 2.0 ist ein modularer, lokaler Agenten-Harness auf Basis 
der Python-Standardbibliothek. Er verbindet eine CLI-Oberfläche 
mit einem Agenten-Loop, dateibasierten Sitzungen, einem 
Ollama-Client und austauschbaren Werkzeugen.

 **Projektstatus:** MVP / 0.5.0. CLI, lokale OpenAI-kompatible HTTP-API, Ollama-Vorcheck,
 Session-Persistenz, Markdown-Protokollierung, SSE-Streaming und die lokalen RAG-Werkzeuge sind
 implementiert. Authentifizierung, TUI und MCP-Plugins sind noch nicht implementiert.

## Installation

Voraussetzung: Python 3.10 oder neuer.

Schnellstart (One-Liner):

```bash
git clone <repository-url> && cd fredTux-2-0 && bash fredtux-install.sh && source .venv/bin/activate
```

Mit aktivierter virtueller Umgebung zeigen `fredtux` und `python` auf die
Projektumgebung. Die Einzelschritte für eine frische Installation aus einem
Git-Checkout:

```bash
git clone <repository-url>
cd fredTux-2-0
bash fredtux-install.sh
.venv/bin/python scripts/devcheck.py --no-ollama-check
.venv/bin/fredtux
```

`fredtux-install.sh` prüft `python3` und `python3 -m venv`. Fehlen `python3`,
`python3-venv` oder `python3-pip`, werden die benötigten Systempakete auf Debian/Ubuntu
automatisch per `apt-get` installiert; dafür werden Root-Rechte oder `sudo` verwendet.
Danach erstellt das Script die virtuelle Umgebung, installiert das Paket, legt `config.nd`
aus `config.nd.example` an und erstellt die konfigurierten Laufzeitverzeichnisse.

Die Datei `config.nd` ist bewusst versioniert und enthält nur Beispielwerte auf
`127.0.0.1`. Echte API-Zugangsdaten gehören nicht in das Repository.

`devcheck.py` prüft Python-Version, virtuelle Umgebung, Editable-Installation,
Console-Script, Laufzeitverzeichnisse und standardmäßig den Ollama-Endpunkt. Wenn der
Ollama-Check nicht gebraucht wird:

```bash
.venv/bin/python scripts/devcheck.py --no-ollama-check
.venv/bin/fredtux --no-ollama-check
```

## Standardumgebung

Die folgenden Werte sind die eingebauten Fallback-Werte. Eine vorhandene
`config.nd` im Projekt hat Vorrang vor diesen Werten; Umgebungsvariablen haben wiederum
Vorrang vor `config.nd`. Die mitgelieferte `config.nd` zeigt auf den lokalen
Ollama-Knoten `127.0.0.1:11434`.

Für einen entfernten oder selbst gehosteten Knoten die Adresse durch den
eigenen Host ersetzen, zum Beispiel `http://ollama.example.internal:11434`.
Dabei muss es sich wirklich um einen Ollama-Knoten handeln, nicht um einen
OpenAI-kompatiblen Hub. Es werden keine Anmeldedaten benötigt.

| Einstellung | Standardwert | Bedeutung |
|---|---|---|
| `FREDTUX_HOME` | `~/.fredtux-2.0` | Sitzungen und RAG-Daten |
| `FREDTUX_CONFIG_FILE` | `./config.nd` | Optionaler Pfad zur Schnellkonfiguration |
| `FREDTUX_OLLAMA_URL` | `http://127.0.0.1:11434` | Native Ollama-Diagnose |
| `FREDTUX_BASE_URL` | `${FREDTUX_OLLAMA_URL}/v1` | OpenAI-kompatibler Chat-Endpunkt |
| `FREDTUX_MODEL` | `gemma4:latest` | Modellname |
| `FREDTUX_API_KEY` | leer | Optionaler Bearer-Token für externe APIs |
| `FREDTUX_OLLAMA_TIMEOUT` | `60` | Timeout für `/api/tags` und Diagnose |
| `FREDTUX_TIMEOUT` | `120` | Timeout für Chat-/OpenAI-kompatible Anfragen |
| `FREDTUX_SKIP_OLLAMA_CHECK` | `0` | `1` überspringt die native Ollama-Diagnose |
| `FREDTUX_API_HOST` | `0.0.0.0` | Bind-Adresse des FredTux-HTTP-Servers |
| `FREDTUX_API_PORT` | `8765` | Port des FredTux-HTTP-Servers |
| `FREDTUX_API_MODEL` | `fredtux-2-0` | Virtueller OpenAPI-Modellname |
| `FREDTUX_MAX_IDLE_ROUNDS` | `6` | Runden ohne erfolgreichen Werkzeugaufruf, bevor abgebrochen wird |
| `FREDTUX_MAX_TOTAL_ROUNDS` | `40` | Harte Obergrenze aller Werkzeugrunden (Endlosschleifenschutz) |

## Schnelles Umschalten mit `config.nd`

Für den häufigen Endpunktwechsel liegt im Projekt eine einfache `KEY=WERT`-Datei.
Sie wird automatisch geladen; Umgebungsvariablen haben Vorrang. Die Endung `.nd`
ist eine bewusste FredTux-Namenskonvention (neben `shell.nd`); der Inhalt ist eine
einfache INI-artige `KEY=WERT`-Datei, kein YAML und kein JSON. Es funktionieren nur
ganzzeilige `#`-Kommentare — ein `#` hinter einem Wert gehört zum Wert.

### OpenAI-kompatibler Endpunkt: vier Zeilen genügen

```ini
FREDTUX_BASE_URL=http://mein-hub:8000/v1
FREDTUX_MODEL=mein-modellname
FREDTUX_API_KEY=sk-...
FREDTUX_SKIP_OLLAMA_CHECK=1
```

Das ist die gesamte Konfiguration:

- `FREDTUX_BASE_URL` — wohin gesendet wird; FredTux hängt `/chat/completions`
  daran. Ohne diese Zeile geht jede Anfrage an `127.0.0.1:11434/v1` (lokales Ollama).
- `FREDTUX_MODEL` — der Upstream-Modellname; nach außen identifiziert sich
  FredTux weiterhin als `fredtux-2-0`.
- `FREDTUX_API_KEY` — optional; wird automatisch als `Authorization: Bearer ...`
  mitgeschickt.
- `FREDTUX_SKIP_OLLAMA_CHECK=1` — Pflicht bei jedem Nicht-Ollama-Endpunkt.
  Ohne diesen Wert läuft die CLI zuerst den nativen Ollama-Vorcheck
  (`GET /api/version`, …) und bricht den Start mit Exit-Code 2 ab, wenn der
  Vorcheck fehlschlägt.

`FREDTUX_OLLAMA_URL` wird nur für die native Ollama-Diagnose gebraucht und ist
für einen OpenAI-kompatiblen Endpunkt nicht nötig. Den Endpunkt einmal
prüfen, bevor FredTux startet:

```bash
curl http://mein-hub:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer sk-...' \
  -d '{"model":"mein-modellname","messages":[{"role":"user","content":"ping"}]}'
```

Wenn curl eine Antwort bekommt, antwortet auch FredTux — gestartet wird mit
`.venv/bin/fredtux`.

### Vollständige `config.nd`

Alle restlichen Einstellungen in einer Datei (Bind-Adresse und Port des
FredTux-HTTP-Servers, Werkzeugschleifen-Limits):

```ini
FREDTUX_BASE_URL=http://127.0.0.1:8000/v1
FREDTUX_OLLAMA_URL=http://127.0.0.1:8000
FREDTUX_MODEL=llm-bahnhof
FREDTUX_SKIP_OLLAMA_CHECK=1
FREDTUX_API_HOST=0.0.0.0
FREDTUX_API_PORT=8765
FREDTUX_API_MODEL=fredtux-2-0
FREDTUX_MAX_IDLE_ROUNDS=6
FREDTUX_MAX_TOTAL_ROUNDS=40
```

`127.0.0.1:8000` ist kein direkter Ollama-Port, deshalb wird der native
`/api/*`-Vorcheck in dieser Konfiguration bewusst übersprungen.

Zum Zurückwechseln auf lokales Ollama die Werte auf `127.0.0.1:11434` und
`FREDTUX_SKIP_OLLAMA_CHECK=0` zurücksetzen. Niemals echte API-Keys in
`config.nd` eintragen; Zugangsdaten gehören in Umgebungsvariablen.

Alles funktioniert auch komplett als Umgebungsvariablen für einen einzelnen
Aufruf; das Überspringen kommt dann von der CLI-Option:

```bash
export FREDTUX_BASE_URL="http://mein-hub:8000/v1"
export FREDTUX_MODEL="mein-modellname"
export FREDTUX_API_KEY="sk-..."
.venv/bin/fredtux --no-ollama-check
```

## Ollama-Vorprüfung

Der Vorcheck verwendet die native Ollama-API:

1. `GET /api/version` – Dienst und Version prüfen
2. `GET /api/tags` – installierte Modelle prüfen
3. `GET /api/ps` – aktuell geladene Modelle anzeigen

`/api/tags` auf dem Testknoten kann mehrere Sekunden benötigen. Deshalb ist der
separate `FREDTUX_OLLAMA_TIMEOUT` vorhanden. Bei einem Timeout wird nicht behauptet,
der Server sei offline; der Fehler unterscheidet zwischen fehlender Erreichbarkeit
und langsamer Antwort. Bei einem fehlenden Modell werden die verfügbaren Modelle
sowie ein `OLLAMA_HOST=... ollama pull ...`-Befehl angezeigt.

## Bedienung

```text
FredTux 2.0 – Sitzung <ID>
Gib /help für Befehle ein.
```

| Eingabe | Wirkung |
|---|---|
| normale Nachricht | an den Agenten senden |
| `/help` | CLI-Hilfe anzeigen |
| `/sessions` | Markdown-Sitzungen auflisten |
| `/session <ID>` | Sitzung fortsetzen |
| `--session <ID>` | Sitzung beim Start laden |
| `/new` | neue Sitzung erzeugen |
| `/exit` oder `/quit` | beenden |

Jede Nachricht wird in `FREDTUX_HOME/sessions/<ID>.md` protokolliert. Eine gleichnamige
JSON-Sidecar-Datei erhält Tool-Call-Metadaten für verlustfreies Fortsetzen. Die
Session-ID enthält nur Buchstaben, Ziffern, `_` und `-`.

## OpenAI-kompatible API

FredTux kann neben der CLI als lokaler HTTP-Server gestartet werden:

```bash
.venv/bin/fredtux --serve
```

Standard-URL:

```text
http://127.0.0.1:8765/v1
```

Wichtige Endpunkte:

| Methode | URL | Zweck |
|---|---|---|
| `GET` | `/health` | FredTux-Status und Version |
| `GET` | `/v1/models` | OpenAI-kompatible Modelliste |
| `POST` | `/v1/chat/completions` | Chatabschluss mit `messages` |

Beispiel:

```bash
curl http://127.0.0.1:8765/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -d '{"model":"fredtux-2-0","messages":[{"role":"user","content":"Antworte nur mit OK"}]}'
```

Bei `"stream": true` antwortet FredTux als OpenAI-SSE-Stream. Die Chunks enthalten
`choices[0].delta.content`; abgeschlossen wird die Verbindung mit `data: [DONE]`.
Tool-Aufrufe werden intern verarbeitet und nicht als rohe Tool-Chunks an den Client
weitergereicht.

Die virtuelle Modell-ID `fredtux-2-0` ist die FredTux-Schnittstelle nach außen. Der
konfigurierte Upstream-Endpunkt und sein Modell werden dadurch nicht verändert.
FredTux akzeptiert zusätzlich den Kompatibilitätsnamen `fredtux-2.0`; unbekannte Modelle
werden mit HTTP 400 abgewiesen.

Die Antwort enthält zusätzlich `fredtux_session_id`. Für das Fortsetzen kann dieselbe
ID als JSON-Feld `session_id` oder als Header `X-FredTux-Session-ID` gesendet werden.
Standardmäßig bindet der Server auf `0.0.0.0:8765` und ist damit im lokalen Netz
erreichbar. Für einen Zugriff von einem anderen Rechner muss die IP-Adresse dieses
Rechners verwendet werden, zum Beispiel `http://192.168.x.x:8765/v1`; `0.0.0.0` selbst
ist keine Zieladresse. Der Server besitzt noch keine Authentifizierung und darf deshalb
nicht ungeschützt ins Internet freigegeben werden. Mit `--host 127.0.0.1` kann die
Bindung wieder auf den lokalen Rechner begrenzt werden.

## Shell- und Dateiwerkzeuge

Shell-Zugriff ist als austauschbares Werkzeugset implementiert und wird **nicht** durch
freien Text in der Systemanweisung aktiviert. Die Sicherheitsstufe steht in `shell.nd`.

| Modus | Verhalten |
|---|---|
| `allowlist` | Nur einzelne Kommandos aus `FREDTUX_SHELL_ALLOWED_COMMANDS`; keine Shell-Metazeichen |
| `standard` | Standardbefehle `pwd`, `ls`, `cd`, `grep`, `ping`, `lynx`, `top`, `ssh`, `screen` plus Dateiwerkzeuge im Schreibbereich |
| `coding` | Entwicklungswerkzeuge, Textverarbeitung, Archive, Prozess-/Netzdiagnose und Skript-Infrastruktur mit Pipes/Redirection; 300 s Timeout |
| `yolo` | Beliebige Bash-Kommandos; nur bewusst aktivieren |

Aktuelle Datei `shell.nd`:

```ini
FREDTUX_SHELL_MODE=coding
FREDTUX_SHELL_ROOT=.
FREDTUX_SHELL_WRITE_ROOT=.
FREDTUX_SHELL_EXTRA_ROOTS=~/BACKUP
FREDTUX_SHELL_WRITE=1
FREDTUX_SHELL_TIMEOUT=30
FREDTUX_CODING_TIMEOUT=300
FREDTUX_SHELL_ALLOWED_COMMANDS=pwd, ls, cd, grep, ping, lynx, top, ssh, screen
```

`FREDTUX_SHELL_EXTRA_ROOTS` ergänzt kommagetrennte Pfade, die im Coding-Modus zusätzlich
als Lese-, Arbeits- und Zielpfade freigegeben sind – etwa das Backup-Verzeichnis
`~/BACKUP/fredtux-2.0-backups/`. Das Schreiben über `write_file` bleibt weiterhin auf
`FREDTUX_SHELL_WRITE_ROOT` beschränkt; Coding-Ausgaben dürfen zusätzlich in
`FREDTUX_SHELL_EXTRA_ROOTS` landen. Das Umleitungsziel `/dev/null` ist im Coding-Modus
immer erlaubt.

Die verfügbaren Datei- und Kommandowerkzeuge sind:

- `read_file(path, max_bytes)` – UTF-8-Dateien lesen
- `write_file(path, content)` – Textdateien im Schreibbereich schreiben
- `change_permissions(path, mode)` – oktale Rechte im Schreibbereich setzen
- `run_coding_command(steps, cwd, redirect_stdout, stdin, stderr)` – bevorzugte, strukturierte argv-Pipeline ohne Shell-String; `stderr` ist `capture` oder `discard`
- `execute_command(command, cwd)` – eingeschränkte Kompatibilitäts-API; validiert Shell-Syntax, bevor sie ausgeführt wird

Im `allowlist`- und `standard`-Modus wird niemals `shell=True` verwendet. Im `coding`-Modus
wird für neue Aufgaben bevorzugt `run_coding_command` verwendet: Die Schritte enthalten
jeweils ein separates `program` und eine Argumentliste. `stdin` versorgt den ersten
Schritt; danach wird dessen stdout automatisch als stdin des nächsten Schritts verwendet.
`stderr=capture` sammelt Fehlermeldungen aller Schritte, `stderr=discard` unterdrückt sie.
Pro Schritt können `stdin` (nur Schritt 1), `stderr` und `redirect_stdout` gesetzt werden.
Dadurch werden Shell-Syntaxzeichen in Argumenten niemals als Code interpretiert und die
Pipeline wird ohne `shell=True` ausgeführt.

`execute_command` bleibt nur als eingeschränkte Kompatibilitäts-API mit zentralem
Validator erhalten. In beiden APIs sind nur die in `CODING_COMMANDS` definierten
Entwicklungsbefehle zugelassen; Pfade außerhalb der freigegebenen Verzeichnisse werden
abgewiesen. `coding` verwendet `FREDTUX_CODING_TIMEOUT` (Default 300 Sekunden), nicht den
kurzen Standard-Timeout. Projekt- und FredTux-Home-Pfade dürfen im Coding-Modus gelesen
werden; Schreibaktionen bleiben im konfigurierten Schreibbereich. Das ist ausdrücklich
keine Sandbox für beliebige Python-, Bash- oder Git-Programme.

Im `allowlist`- und `standard`-Modus werden Befehle wie `rm -rf`, Pipes, `;`, `&&`,
Command-Substitution und Umleitungen abgewiesen.

Im Standard-Modus sind `config.nd`, `shell.nd`, `.env`, `.git` und `.venv` gegen
Schreibzugriffe geschützt. API-Schlüssel werden aus der ausgeführten Umgebung entfernt.

YOLO wird ausschließlich durch eine manuelle Konfiguration aktiviert:

```ini
FREDTUX_SHELL_MODE=yolo
```

Das gibt dem Agenten praktisch uneingeschränkten Shell-Zugriff. Nur in einer
vertrauenswürdigen, isolierten Umgebung verwenden.

### Coding-Werkzeuge

`CODING_COMMANDS` in `fredtux/tools/shell.py` ist die maßgebliche Allowlist für
`run_coding_command` und die Kompatibilitäts-API `execute_command`. Freigegeben sind:

- **Entwicklung:** `python3`, `pip3`, `make`, `git`, `find`, `ruff`, `black`, `mypy`, `bash`, `sh`
- **Projekt/Dateien:** `which`, `wc`, `head`, `tail`, `sort`, `uniq`, `date`, `rm`, `cp`, `mv`, `chmod`, `stat`, `dirname`, `basename`, `mkdir`, `touch`, `cat`, `test`, `env`
- **Textverarbeitung:** `sed`, `awk`, `xargs`, `cut`, `tr`, `nl`, `paste`, `join`, `comm`, `column`, `fold`, `expand`, `split`, `csplit`
- **Vergleich/Integrität:** `diff`, `patch`, `md5sum`, `sha256sum`, `base64`
- **Archive:** `tar`, `zip`, `unzip`, `gzip`, `xz`
- **Prozesse/Netz:** `ps`, `kill`, `timeout`, `watch`, `nc`, `telnet`, `dig`, `ss`, `curl`, `wget`
- **Dateisystem/Allgemein:** `pwd`, `ls`, `grep`, `realpath`, `readlink`, `file`, `install`, `uuidgen`, `tee`, `od`, `hexdump`, `echo`, `printf`, `true`, `false`, `df`, `du`, `free`

`python` und `fzf` bleiben absichtlich außen vor: Auf den unterstützten Systemen ist
`python3` der vorhandene Interpreter; `fzf` ist keine erforderliche FredTux-Abhängigkeit.
Nach einer Änderung an `CODING_COMMANDS` muss der laufende FredTux-Prozess neu gestartet
werden, damit er die neue Liste verwendet.

## Werkzeugschleifen: Fortschritt statt fester Rundenzahl

FredTux bricht den Agentenloop nicht mehr nach einer festen Zahl von Runden ab. Eine
Runde gilt als *Fortschritt*, wenn mindestens einer ihrer Werkzeugaufrufe ohne
`FEHLER` beantwortet wurde. Solange das passiert, darf der Agent beliebig viele
Werkzeuge nacheinander ausführen – auch das Anlegen von fünf oder zwölf Dateien in
einer Anfrage.

Zwei Grenzen schützen trotzdem vor Endlosschleifen:

| Einstellung | Standard | Wirkung |
|---|---|---|
| `FREDTUX_MAX_IDLE_ROUNDS` | `6` | Abbruch nach dieser Zahl *aufeinanderfolgender* Runden ohne Fortschritt; jede erfolgreiche Runde setzt den Zähler zurück |
| `FREDTUX_MAX_TOTAL_ROUNDS` | `40` | Harte Obergrenze aller Runden als letztes Sicherheitsnetz |

Wiederholte Fehlschläge fangen zusätzlich `_tool_loop_error`: der zweite Aufruf
desselben Werkzeugs mit denselben fehlgeschlagenen Parametern oder drei
aufeinanderfolgende `FEHLER` beenden die Schleife sofort – unabhängig von den
Rundenzählern.

Bricht eine Grenze, nennt die Meldung die Ursache mit:

```text
FEHLER: Maximale Anzahl von Werkzeugschleifen erreicht. Runden gesamt=40,
Runden ohne Fortschritt=0, Limit=40/6. Letzter Werkzeugaufruf: list_files({"path":"."})
```

Dieselben Werte stehen im Fehlerlog unter der Kategorie `tool_loop`.

## Fehlerlog und Live-Mitschrift

Technische Fehler werden append-only als JSON Lines unter
`~/.fredtux-2.0/logs/errors.jsonl` gespeichert. Jeder Eintrag enthält einen
UTC-Zeitstempel, die Session-ID, die Kategorie und die Fehlermeldung. Während FredTux
läuft, kann das Log live verfolgt werden:

```bash
tail -F ~/.fredtux-2.0/logs/errors.jsonl
```

Die Datei wird absichtlich nicht rotiert. Die vollständige Unterhaltung bleibt in den
Sitzungsdateien unter `~/.fredtux-2.0/sessions/` erhalten.

## Coding-Agent-Regeln

Die verbindlichen Betriebsregeln liegen in `CODING_AGENT.md` und werden bei jeder
Agent-Initialisierung in den System-Prompt geladen. Sie verlangen unter anderem:
zuerst RAG und vorhandene Dateien prüfen, `run_coding_command` statt roher Shell-
Strings verwenden, Schreibpfade begrenzen, nach Fehlern nicht denselben Aufruf
wiederholen und nach zwei identischen beziehungsweise drei aufeinanderfolgenden
Werkzeugfehlern abzubrechen.

### Regeln zur Laufzeit ändern: `reload_rules`

`CODING_AGENT.md` ist damit nicht nur beim Start wirksam: Der Agent darf die Datei
mit `write_file` ändern und lädt sie anschließend mit dem Werkzeug `reload_rules`
in den laufenden System-Prompt. Ohne diesen Aufruf würde eine geänderte Regel erst
in der nächsten Sitzung gelten – der Kreislauf aus „Fehler finden, Ursache
verstehen, Regel festhalten, ab jetzt anders handeln" bliebe sonst offen – die Regel
würde erst nach einem Neustart greifen.

`reload_rules` ersetzt ausschließlich die Systemnachricht der aktuellen Sitzung;
der Gesprächsverlauf bleibt unangetastet. Die Antwort nennt den Ergebniszustand:

```text
Regelwerk neu geladen: CODING_AGENT.md hat jetzt 27 Zeilen (+2). Die Regeln gelten ab sofort in dieser Sitzung.
Regelwerk unverändert: CODING_AGENT.md mit 27 Zeilen ist bereits aktiv.
```

Ist `CODING_AGENT.md` nicht vorhanden, fällt der System-Prompt auf die reine
Grundanweisung zurück. Fehlt in der Sitzung eine Systemnachricht, wird sie an
Position 0 eingesetzt.

## Agenten- und Werkzeugarchitektur

```text
main.py / .venv/bin/fredtux / .venv/bin/fredtux-api
        │
        ├── fredtux.interfaces.cli    interaktive CLI
        └── fredtux.interfaces.api    OpenAI-kompatibler HTTP-Server
                │
                ├── fredtux.config    Umgebung und Laufzeitverzeichnisse
                ├── fredtux.llm       OpenAI-Chat + native Ollama-Diagnose
                ├── fredtux.core      Agenten-Loop und Tool-Ausführung
                ├── fredtux.sessions  Markdown + JSON-Sidecar + Datei-Locking
                └── fredtux.tools     dateibasiertes Markdown-RAG
```

Der Agenten-Loop sendet System-, Nutzer- und Werkzeughistorie an das konfigurierte
Modell. Unterstützte Werkzeuge:

- `save_knowledge(title, content)` – Markdown-Notiz im RAG speichern
- `search_knowledge(query)` – lokale Markdown-Dateien durchsuchen
- `list_knowledge()` – vorhandene RAG-Dateien auflisten

Die Werkzeugimplementierung schreibt derzeit nur in `FREDTUX_HOME` und startet keine
Shell-Kommandos. Neue Werkzeuge sollen über `ToolRegistry` registriert und über
Tests abgesichert werden.

## Laufzeitdaten und Datenschutz

Standardverzeichnisse:

```text
~/.fredtux-2.0/
├── sessions/                 Chatverläufe (.md + .json)
└── data/brain/rag/           dauerhafte Markdown-Notizen
```

Nicht in das Repository gehören:

- `.venv/`
- `*.pyc` und `__pycache__/`
- API-Schlüssel
- private Sitzungs- oder RAG-Daten
- generierte `*.egg-info/`-Verzeichnisse

Vor dem Veröffentlichen immer prüfen:

```bash
git status --short
git check-ignore -v .venv fredtux_2.0.egg-info
```

## Fehlersuche

### `Ollama ist ... nicht erreichbar`

- `FREDTUX_OLLAMA_URL` und Port prüfen
- Netzwerk/SSH zum Zielhost prüfen
- Ollama auf dem Zielknoten starten
- keinen OpenAI-kompatiblen Hub (etwa einen Router auf Port `8000`) als lokalen Ollama-Test verwenden

### `Modell ... ist nicht installiert`

Die Ausgabe listet die von `/api/tags` gelieferten Namen. Danach beispielsweise:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama pull <exakter-modellname>
```

### `Zeitüberschreitung bei /api/tags`

Der Dienst antwortet, aber die Modellliste ist langsam. Timeout erhöhen:

```bash
FREDTUX_OLLAMA_TIMEOUT=120 .venv/bin/python scripts/devcheck.py
```

### Start mit falscher Python-Umgebung

Nicht `python` oder das System-Python verwenden:

```bash
.venv/bin/python scripts/devcheck.py --no-ollama-check
```

### `ModuleNotFoundError` beim Entry-Point

Die Installation ist veraltet oder wurde außerhalb der venv ausgeführt:

```bash
.venv/bin/python -m pip install --no-deps --editable .
.venv/bin/fredtux --help
```

## Tests und Qualitätssicherung

```bash
.venv/bin/python -m compileall -q .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/devcheck.py --no-ollama-check
.venv/bin/fredtux --help
```

Diese Prüfungen laufen lokal auf Python 3.10, 3.11 und 3.12; das Projekt hat keine
GitHub-CI. Der Live-Ollama-Check ist absichtlich nicht dabei, weil er einen internen
Netzwerkhost und ein installiertes Modell benötigt.

## Abhängigkeiten

- **Laufzeit:** keine externen Python-Pakete; `urllib`, `json`, `pathlib`, `fcntl` und
  weitere Module der Standardbibliothek.
- **Entwicklung:** `venv`, `pip` und das beim Editable-Install verwendete
  Setuptools-Backend; keine Testbibliothek erforderlich.
- **Laufzeitdienst:** Ollama ist eine externe Voraussetzung, keine Python-Abhängigkeit.

Details stehen in [`docs/DEPENDENCIES.ger.md`](docs/DEPENDENCIES.ger.md).

## GitHub-Veröffentlichung

Vorbereitet sind `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md` und `LICENSE`.

Vor jedem Push:

```bash
git status --short
git diff --check
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/devcheck.py --no-ollama-check
```

Danach den Quellstand nach `main` auf GitHub pushen und die Version aus
`pyproject.toml` (aktuell `0.5.0`) als Release veröffentlichen. Keine Secrets,
`.venv`-Inhalte oder privaten `~/.fredtux-2.0`-Daten committen.

## Lizenz

AGPL-3.0-or-later. Die vollständige Lizenz steht in `LICENSE`.

## Powered by AI

Dieses Projekt wurde mit Unterstützung KI-gestützter Werkzeuge für die
Codeänderungen und die Dokumentation entwickelt. Der Code, die Tests und die
Architekturentscheidungen stammen von einer menschlich verantwortlichen Person; für
verbleibende Fehler ist entsprechend das Projekt verantwortlich.

Die eingesetzten Modelle werden nicht namentlich genannt. Die verwendeten Werkzeuge
haben keinen Einfluss auf die Lizenz: Das Projekt steht weiterhin unter
AGPL-3.0-or-later (siehe [Lizenz](#lizenz)).
