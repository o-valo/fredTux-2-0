# Security Policy / Sicherheitsrichtlinie

**Languages:** [Deutsch](#deutsch) · [English](#english)

<a id="deutsch"></a>

## Deutsch

### Einordnung

FredTux 2.0 ist ein lokaler MVP-Agent. Er kann derzeit Chatnachrichten an ein
konfiguriertes Modell senden und Markdown-Notizen im lokalen RAG speichern.
Es gibt noch keine öffentliche FredTux-HTTP-API und keine Authentifizierung.

### Nicht unterstützen

- API-Keys, Passwörter oder Session-Inhalte in Issues, PRs oder Logs posten
- private `~/.fredtux-2.0`-Daten ins Repository kopieren
- Test-Endpunkte verwenden, auf denen echte Provider-Tokens fließen können
- `FREDTUX_SHELL_MODE=yolo` in ungeschützten Umgebungen
- `FREDTUX_SHELL_MODE=coding` ohne eng begrenzten `FREDTUX_SHELL_ROOT` und
  `FREDTUX_SHELL_WRITE_ROOT`
- unbekannte Werkzeuge oder Shell-Ausführung über Modelltext aktivieren

### Sichere Konfiguration

- `FREDTUX_API_KEY` nur als Umgebungsvariable oder Secret Store setzen
- `.env` mit Secrets niemals committen
- `.env.example` enthält ausschließlich Platzhalter
- für externe APIs `--no-ollama-check` nur bewusst verwenden
- `shell.nd` und `config.nd` nicht durch den Agenten verändern lassen; im
  Standard-Modus sind sie gegen Schreibzugriffe geschützt
- `yolo` nur in einer isolierten Testumgebung aktivieren; der Modus führt
  beliebige Bash-Kommandos aus
- `coding` erlaubt bewusst Entwicklungsbefehle, Pipes und Redirection. Der Modus
  ist keine Sicherheitsgrenze gegen ein bösartig konfiguriertes Python-Skript
  oder `git`; Root und Schreibbereich müssen daher auf ein eigenes
  Projektverzeichnis zeigen.
- `FREDTUX_SHELL_EXTRA_ROOTS` nur auf eng begrenzte, vertrauenswürdige Verzeichnisse
  setzen (z. B. das eigene Backup-Verzeichnis); niemals `$HOME` oder `/` freigeben.
- RAG- und Session-Verzeichnisse mit restriktiven Dateirechten betreiben

### Meldeweg

Sicherheitsprobleme bitte privat über den Repository-Eigner melden. Der Bericht
soll enthalten:

1. betroffene Version bzw. Commit
2. reproduzierbare Schritte
3. erwartetes und tatsächliches Verhalten
4. mögliche Auswirkung
5. keine echten Secrets oder privaten Nutzdaten

Öffentliche Details und eine technische Beschreibung folgen nach einer Prüfung.

---

<a id="english"></a>

## English

### Classification

FredTux 2.0 is a local MVP agent. It can currently send chat messages to a
configured model and store Markdown notes in the local RAG. There is no public
FredTux HTTP API and no authentication yet.

### Out of scope

- Posting API keys, passwords, or session content in issues, PRs, or logs
- Copying private `~/.fredtux-2.0` data into the repository
- Using test endpoints where real provider tokens may flow
- `FREDTUX_SHELL_MODE=yolo` in unprotected environments
- `FREDTUX_SHELL_MODE=coding` without a tightly limited `FREDTUX_SHELL_ROOT` and
  `FREDTUX_SHELL_WRITE_ROOT`
- Activating unknown tools or shell execution via model text

### Safe configuration

- Set `FREDTUX_API_KEY` only as an environment variable or in a secret store
- Never commit a `.env` containing secrets
- `.env.example` contains placeholders only
- Use `--no-ollama-check` for external APIs deliberately only
- Do not let the agent modify `shell.nd` and `config.nd`; in standard mode they
  are protected against write access
- Enable `yolo` only in an isolated test environment; that mode executes
  arbitrary bash commands
- `coding` deliberately allows development commands, pipes, and redirection.
  That mode is not a security boundary against a maliciously configured Python
  script or `git`; root and write area must therefore point at a dedicated
  project directory.
- Set `FREDTUX_SHELL_EXTRA_ROOTS` only to tightly limited, trusted directories
  (for example your own backup directory); never expose `$HOME` or `/`.
- Operate the RAG and session directories with restrictive file permissions

### Reporting path

Please report security problems privately to the repository owner. The report
should contain:

1. the affected version or commit
2. reproducible steps
3. expected and actual behaviour
4. possible impact
5. no real secrets or private payload data

Public details and a technical description follow after a review.
