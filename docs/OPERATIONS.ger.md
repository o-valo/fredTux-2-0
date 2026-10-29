# Betrieb und Healthchecks

> Sprache: Deutsch | [English](OPERATIONS.md)

## Normaler Start

```bash
cd ~/fredTux-2-0
.venv/bin/fredtux
```

Der Start prüft standardmäßig Ollama, bevor eine neue Session angelegt wird. Für
einen externen OpenAI-kompatiblen Anbieter:

```bash
.venv/bin/fredtux --no-ollama-check
```

## Healthcheck ohne Modellgenerierung

```bash
.venv/bin/python scripts/devcheck.py
```

Der Check liest `/api/version`, `/api/tags` und `/api/ps`, schreibt aber keine
Chatnachricht und generiert kein Token. Das ist für Monitoring und CI-Vorbereitung
geeignet.

## HTTP-API

```bash
.venv/bin/fredtux --serve
```

Standardmäßig läuft FredTux dann unter `http://0.0.0.0:8765` und ist auf allen
IPv4-Schnittstellen erreichbar. Von einem anderen Rechner muss die tatsächliche
LAN-IP-Adresse verwendet werden, zum Beispiel `http://192.168.x.x:8765`; `0.0.0.0`
ist nur die Bind-Adresse. Prüfen:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/v1/models
```

Chatbeispiel:

```bash
curl http://127.0.0.1:8765/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -d '{"model":"fredtux-2.0","messages":[{"role":"user","content":"Antworte nur mit OK"}]}'
```

Die API verwendet die aktuelle `config.nd`. Die Session-ID steht in der Antwort als
`fredtux_session_id` und kann bei Folgeanfragen als `session_id` oder
`X-FredTux-Session-ID` verwendet werden. Der Server besitzt noch keine
Authentifizierung. Für eine lokale-only-Bindung
`fredtux --serve --host 127.0.0.1` verwenden; nicht ungeschützt ins Internet
freigeben.

## Sitzungen

```bash
.venv/bin/fredtux --session session-20260924-122322
```

Sitzungsdateien liegen standardmäßig unter `~/.fredtux-2.0/sessions/`. Für ein Backup
werden die Markdown- und JSON-Dateien dieses Verzeichnisses gemeinsam kopiert:

```bash
tar -czf fredtux-sessions-$(date +%Y%m%d).tgz ~/.fredtux-2.0/sessions
```

Vor einer Wiederherstellung muss FredTux nicht laufen. Nach dem Entpacken die Dateien
mit ihren ursprünglichen Namen und Rechten einsetzen.

## Coding-Werkzeuge und Backup-Pfad

Die Coding-Allowlist steht in `fredtux/tools/shell.py` unter `CODING_COMMANDS` und wird
beim Start des FredTux-Prozesses geladen. Sie umfasst unter anderem `python3`, `git`,
`bash`, `sed`, `awk`, `xargs`, `diff`, `patch`, `tar`, `zip`, `unzip`, `gzip`, `xz`,
`ps`, `timeout`, `curl`, `wget`, `tee`, `sha256sum` und weitere Systemwerkzeuge.
`python` und `fzf` sind nicht freigegeben, weil sie hier nicht als
FredTux-Abhängigkeiten benötigt werden.

Standardmäßig ist `FREDTUX_SHELL_EXTRA_ROOTS=~/BACKUP` gesetzt. Deshalb darf der
Coding-Modus das Backup-Ziel `~/BACKUP/fredtux-2.0-backups/` sowohl als
Arbeitsverzeichnis als auch als Ziel für `redirect_stdout` verwenden. `write_file`
bleibt davon getrennt und schreibt weiterhin nur in `FREDTUX_SHELL_WRITE_ROOT`.

Nach einer Änderung an `CODING_COMMANDS` oder an `shell.nd` muss FredTux neu gestartet
werden. Ein laufender Prozess verwendet die alte Allowlist.

## RAG-Daten

`~/.fredtux-2.0/data/brain/rag/` enthält dauerhafte Markdown-Notizen. Die RAG-Suche
liest ausschließlich lokale `.md`-Dateien. Vor einem Backup sollten private Inhalte
geprüft werden.

## Logs und Fehler

FredTux schreibt technische Fehler append-only als JSON Lines nach:

```text
~/.fredtux-2.0/logs/errors.jsonl
```

Jeder Datensatz enthält UTC-Zeitstempel, Session-ID, Fehlerkategorie und Meldung.
Das Log wird nach jedem Eintrag geleert, damit es während eines laufenden Prozesses
mitgefolgt werden kann:

```bash
tail -F ~/.fredtux-2.0/logs/errors.jsonl
```

Die Datei wird nicht rotiert. Die vollständige Ausgabe der Sitzung bleibt zusätzlich
in den Markdown-/JSON-Sitzungsdateien unter `~/.fredtux-2.0/sessions/`.

## Einem Lauf live zusehen

Das **Transparenzprotokoll** ist standardmäßig an (`FREDTUX_STREAM_LOG=1`) und
schreibt die Arbeit des Agenten als Klartext mit, eine Zeile je Ereignis und
Millisekunden vorn:

```bash
tail -F ~/.fredtux-2.0/logs/stream.log
```

```text
18:17:15.421  [Runde 1] codehamr-agent:latest: 12 Nachrichten im Kontext
18:17:15.971  [denkt] Ich prüfe zuerst, ob die Datei existiert.
18:17:17.374  [text] Die Datei fehlt, ich lege sie an.
18:17:18.010  [Werkzeug] write_file {"path":"notiz.md"}
18:17:18.412  [Werkzeug] write_file → ok, 18 Zeichen, 402 ms
18:19:41.003  [Runde 2] codehamr-agent:latest: 14 Nachrichten im Kontext
```

Die Zeitstempel sind der Punkt: Ist die letzte Zeile Minuten alt, rechnet das
Modell noch und der Lauf steuert auf das Zeitlimit zu – sichtbar, lange bevor
die Anfrage abbricht. Streaming-Clients (OpenWebUI und alles, was
`reasoning_content` kennt) bekommen dieselben Marker und die Denkausgabe des
Modells als `delta.reasoning_content`; das Denken bleibt also vom Antworttext
getrennt. `FREDTUX_STREAM_LOG=0` schaltet es ab,
`FREDTUX_STREAM_LOG_FILE` verschiebt die Datei.

Für den normalen Ablauf gibt es zusätzlich das **Aktivitätsprotokoll**, wenn es in
der Konfiguration eingeschaltet ist:

```ini
FREDTUX_LOG=1
FREDTUX_LOG_LEVEL=info
```

```bash
tail -F ~/.fredtux-2.0/logs/fredtux.jsonl
```

Es enthält je Anfrage `request.start`, für jede Runde `llm.reply` mit Dauer und
Zahl der Werkzeugaufrufe, jeden Werkzeugaufruf mit Dauer und Ergebnislänge sowie
`request.end` mit Status und Gesamtdauer. Damit lässt sich eine langsame Antwort
zuordnen: Laden des Modells, lange Inferenz oder eine Werkzeugschleife. Ohne
`FREDTUX_LOG=1` wird die Datei nicht angelegt.

## Modellknoten nicht verwechseln

- `http://<ollama-testknoten>:11434`: direkter Ollama-Testknoten
- `http://<ollama-knoten>:11434`: direkter Ollama-Knoten mit weiteren Modellen
- `http://<pi-knoten>:11434`: kleinerer, langsamer Raspberry-Pi-Knoten
- `http://<router-host>:8000`: OpenAI-kompatibler Router, nicht für lokale Modelltests verwenden
- `http://<llm-hub>:8000`: produktiver LLM-Bahnhof, nicht als lokaler Ollama-Endpunkt
