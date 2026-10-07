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

## Modellknoten nicht verwechseln

- `http://<ollama-testknoten>:11434`: direkter Ollama-Testknoten
- `http://<ollama-knoten>:11434`: direkter Ollama-Knoten mit weiteren Modellen
- `http://<pi-knoten>:11434`: kleinerer, langsamer Raspberry-Pi-Knoten
- `http://<router-host>:8000`: OpenAI-kompatibler Router, nicht für lokale Modelltests verwenden
- `http://<llm-hub>:8000`: produktiver LLM-Bahnhof, nicht als lokaler Ollama-Endpunkt
