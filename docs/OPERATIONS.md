# Operations and health checks

> Language: English | [Deutsche Fassung](OPERATIONS.ger.md)

## Normal startup

```bash
cd ~/fredTux-2-0
.venv/bin/fredtux
```

By default, startup checks Ollama before a new session is created. For an
external OpenAI-compatible provider:

```bash
.venv/bin/fredtux --no-ollama-check
```

## Health check without model generation

```bash
.venv/bin/python scripts/devcheck.py
```

The check reads `/api/version`, `/api/tags`, and `/api/ps`, but does not write a
chat message and does not generate a token. That makes it suitable for
monitoring and CI preparation.

## HTTP API

```bash
.venv/bin/fredtux --serve
```

By default FredTux then runs on `http://0.0.0.0:8765` and is reachable on all IPv4
interfaces. From another machine, the actual LAN IP address must be used, for
example `http://192.168.x.x:8765`; `0.0.0.0` is only the bind address. To check:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/v1/models
```

Chat example:

```bash
curl http://127.0.0.1:8765/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -d '{"model":"fredtux-2.0","messages":[{"role":"user","content":"Reply with OK only"}]}'
```

The API uses the current `config.nd`. The session ID is in the response as
`fredtux_session_id` and can be used in follow-up requests as `session_id` or as
`X-FredTux-Session-ID`. The server does not yet have authentication. For a
local-only binding, use `fredtux --serve --host 127.0.0.1`; do not expose it
unprotected to the internet.

## Sessions

```bash
.venv/bin/fredtux --session session-20260924-122322
```

Session files are located under `~/.fredtux-2.0/sessions/` by default. For a
backup, copy the Markdown and JSON files of this directory together:

```bash
tar -czf fredtux-sessions-$(date +%Y%m%d).tgz ~/.fredtux-2.0/sessions
```

FredTux does not need to be running before a restore. After unpacking, put the
files back with their original names and permissions.

## Coding tools and backup path

The coding allowlist is in `fredtux/tools/shell.py` under `CODING_COMMANDS` and is
loaded when the FredTux process starts. It includes, among others, `python3`, `git`,
`bash`, `sed`, `awk`, `xargs`, `diff`, `patch`, `tar`, `zip`, `unzip`, `gzip`,
`xz`, `ps`, `timeout`, `curl`, `wget`, `tee`, `sha256sum`, and other system
utilities. `python` and `fzf` are not allowed, because they are not needed here
as FredTux dependencies.

By default `FREDTUX_SHELL_EXTRA_ROOTS=~/BACKUP` is set. That is why coding mode may
use the backup target `~/BACKUP/fredtux-2.0-backups/` both as a working directory
and as the target for `redirect_stdout`. `write_file` remains separate from
that and still writes only into `FREDTUX_SHELL_WRITE_ROOT`.

After a change to `CODING_COMMANDS` or to `shell.nd`, FredTux must be restarted. A
running process uses the old allowlist.

## RAG data

`~/.fredtux-2.0/data/brain/rag/` contains persistent Markdown notes. The RAG search
reads exclusively local `.md` files. Before a backup, private content should be
reviewed.

## Logs and errors

FredTux writes technical errors append-only as JSON Lines to:

```text
~/.fredtux-2.0/logs/errors.jsonl
```

Each record contains a UTC timestamp, session ID, error category, and message.
The log is flushed after every entry so that it can be followed while a process
is running:

```bash
tail -F ~/.fredtux-2.0/logs/errors.jsonl
```

The file is not rotated. The full session output additionally remains in the
Markdown/JSON session files under `~/.fredtux-2.0/sessions/`.

## Do not confuse the model nodes

- `http://<ollama-testnode>:11434`: direct Ollama test node
- `http://<ollama-node>:11434`: direct Ollama node with more models
- `http://<pi-node>:11434`: smaller, slower Raspberry Pi node
- `http://<router-host>:8000`: OpenAI-compatible router, do not use for local model tests
- `http://<llm-hub>:8000`: production LLM hub, not a local Ollama endpoint
