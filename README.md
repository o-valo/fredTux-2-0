<p align="center">
  <img src="fredTux-2-0.png" alt="FredTux 2.0 logo" width="100%">
</p>



# FredTux 2.0

- Language: English | [Deutsche Fassung](README.ger.md)

FredTux 2.0 is a modular, local agent harness built on the Python standard library.
It combines a CLI interface with an agent loop, file-based sessions, an Ollama
client, and interchangeable tools.

- **Project status:** MVP / 0.5.0. The CLI, the local OpenAI-compatible HTTP API,
-  the Ollama pre-check, session persistence, Markdown logging, SSE streaming, and
-  the local RAG tools are implemented. Authentication, the TUI, and MCP plugins are
-  not implemented yet.

## Installation

Prerequisite: Python 3.10 or newer.

Quickstart (one-liner):

```bash
git clone <repository-url> && cd fredTux-2-0 && bash fredtux-install.sh && source .venv/bin/activate
```

With the virtual environment activated, `fredtux` and `python` refer to the
project environment. The individual steps for a fresh installation from a Git
checkout:

```bash
git clone <repository-url>
cd fredTux-2-0
bash fredtux-install.sh
.venv/bin/python scripts/devcheck.py --no-ollama-check
.venv/bin/fredtux
```

`fredtux-install.sh` checks `python3` and `python3 -m venv`. If `python3`,
`python3-venv`, or `python3-pip` are missing, the required system packages on
Debian/Ubuntu are installed automatically via `apt-get`; this requires root
privileges or `sudo`. The script then creates the virtual environment, installs
the package, creates `config.nd` from `config.nd.example`, and creates the
configured runtime directories.

The file `config.nd` is deliberately tracked and contains only sample values on
`127.0.0.1`. Real API credentials do not belong in the repository.

`devcheck.py` checks the Python version, the virtual environment, the editable
installation, the console script, the runtime directories, and by default the
Ollama endpoint. If the Ollama check is not needed:

```bash
.venv/bin/python scripts/devcheck.py --no-ollama-check
.venv/bin/fredtux --no-ollama-check
```

## Default environment

The following values are the built-in fallbacks. A `config.nd` present in the
project takes precedence over these values; environment variables in turn take
precedence over `config.nd`. The shipped `config.nd` points at the local Ollama
node `127.0.0.1:11434`.

For a remote or self-hosted node, replace the address with your own host, for
example `http://ollama.example.internal:11434`. Make sure the address really is
an Ollama node and not an OpenAI-compatible hub. No credentials are required.

| Setting | Default | Meaning |
|---|---|---|
| `FREDTUX_HOME` | `~/.fredtux-2.0` | Sessions and RAG data |
| `FREDTUX_CONFIG_FILE` | `./config.nd` | Optional path to the quick config file |
| `FREDTUX_OLLAMA_URL` | `http://127.0.0.1:11434` | Native Ollama diagnostics |
| `FREDTUX_BASE_URL` | `${FREDTUX_OLLAMA_URL}/v1` | OpenAI-compatible chat endpoint |
| `FREDTUX_MODEL` | `gemma4:latest` | Model name |
| `FREDTUX_API_KEY` | empty | Optional bearer token for external APIs |
| `FREDTUX_OLLAMA_TIMEOUT` | `60` | Timeout for `/api/tags` and diagnostics |
| `FREDTUX_TIMEOUT` | `120` | Timeout for chat/OpenAI-compatible requests |
| `FREDTUX_SKIP_OLLAMA_CHECK` | `0` | `1` skips the native Ollama diagnostics |
| `FREDTUX_API_HOST` | `0.0.0.0` | Bind address of the FredTux HTTP server |
| `FREDTUX_API_PORT` | `8765` | Port of the FredTux HTTP server |
| `FREDTUX_API_MODEL` | `fredtux-2-0` | Virtual OpenAPI model name |
| `FREDTUX_MAX_IDLE_ROUNDS` | `6` | Rounds without a successful tool call before aborting |
| `FREDTUX_MAX_TOTAL_ROUNDS` | `40` | Hard upper bound on all tool rounds (runaway-loop guard) |

## Switching endpoints quickly with `config.nd`

For the frequent endpoint switch, the project ships a simple `KEY=VALUE` file.
It is loaded automatically; environment variables take precedence. The `.nd`
ending is a deliberate FredTux naming convention (next to `shell.nd`); the
content is a plain INI-style `KEY=VALUE` file, not YAML or JSON. Only full-line
`#` comments are supported — a `#` behind a value becomes part of the value.

### OpenAI-compatible endpoint: four lines are enough

```ini
FREDTUX_BASE_URL=http://my-hub:8000/v1
FREDTUX_MODEL=my-model-name
FREDTUX_API_KEY=sk-...
FREDTUX_SKIP_OLLAMA_CHECK=1
```

That is the whole configuration:

- `FREDTUX_BASE_URL` — where requests go; FredTux appends `/chat/completions`.
  Without this line every request goes to `127.0.0.1:11434/v1` (local Ollama).
- `FREDTUX_MODEL` — the upstream model name; to the outside FredTux still
  identifies as `fredtux-2-0`.
- `FREDTUX_API_KEY` — optional; sent automatically as `Authorization: Bearer ...`.
- `FREDTUX_SKIP_OLLAMA_CHECK=1` — mandatory for every non-Ollama endpoint.
  Without it the CLI first runs the native Ollama pre-check (`GET /api/version`,
  …) and aborts the start with exit code 2 if it fails.

`FREDTUX_OLLAMA_URL` is only used for the native Ollama diagnostics and is not
needed for an OpenAI-compatible endpoint. Check the endpoint once before
starting FredTux:

```bash
curl http://my-hub:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer sk-...' \
  -d '{"model":"my-model-name","messages":[{"role":"user","content":"ping"}]}'
```

If curl gets an answer, FredTux will too — start it with `.venv/bin/fredtux`.

### Complete `config.nd`

All remaining settings in one file (bind address and port of the FredTux HTTP
server, tool-loop limits):

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

`127.0.0.1:8000` is not a direct Ollama port, which is why the native `/api/*`
pre-check is deliberately skipped in this configuration.

To switch back to local Ollama, set the values back to `127.0.0.1:11434` and
`FREDTUX_SKIP_OLLAMA_CHECK=0`. Never put real API keys in `config.nd`; set them
as environment variables instead.

Everything also works as environment variables for a single run; the skip then
comes from the CLI option:

```bash
export FREDTUX_BASE_URL="http://my-hub:8000/v1"
export FREDTUX_MODEL="my-model-name"
export FREDTUX_API_KEY="sk-..."
.venv/bin/fredtux --no-ollama-check
```

## Ollama pre-check

The pre-check uses the native Ollama API:

1. `GET /api/version` – verify service and version
2. `GET /api/tags` – verify installed models
3. `GET /api/ps` – show currently loaded models

`/api/tags` on the test node can take several seconds. That is why the separate
`FREDTUX_OLLAMA_TIMEOUT` exists. On a timeout, FredTux does not claim that the server
is offline; the error distinguishes between an unreachable host and a slow
response. If a model is missing, the available models are listed together with
an `OLLAMA_HOST=... ollama pull ...` command.

## Operation

```text
FredTux 2.0 – session <ID>
Enter /help for commands.
```

| Input | Effect |
|---|---|
| normal message | send to the agent |
| `/help` | show the CLI help |
| `/sessions` | list the Markdown sessions |
| `/session <ID>` | resume a session |
| `--session <ID>` | load a session at startup |
| `/new` | create a new session |
| `/exit` or `/quit` | quit |

Every message is logged in `FREDTUX_HOME/sessions/<ID>.md`. A JSON sidecar file of
the same name receives tool-call metadata for lossless resuming. The session ID
contains only letters, digits, `_`, and `-`.

## OpenAI-compatible API

Besides the CLI, FredTux can be started as a local HTTP server:

```bash
.venv/bin/fredtux --serve
```

Default URL:

```text
http://127.0.0.1:8765/v1
```

Important endpoints:

| Method | URL | Purpose |
|---|---|---|
| `GET` | `/health` | FredTux status and version |
| `GET` | `/v1/models` | OpenAI-compatible model list |
| `POST` | `/v1/chat/completions` | chat completion with `messages` |

Example:

```bash
curl http://127.0.0.1:8765/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -d '{"model":"fredtux-2-0","messages":[{"role":"user","content":"Reply with OK only"}]}'
```

With `"stream": true`, FredTux responds as an OpenAI SSE stream. The chunks contain
`choices[0].delta.content`; the connection is terminated with `data: [DONE]`.
Tool calls are handled internally and are not forwarded to the client as raw tool
chunks.

The virtual model ID `fredtux-2-0` is FredTux's interface to the outside world. The
configured upstream endpoint and its model are not changed by this. FredTux also
accepts the compatibility name `fredtux-2.0`; unknown models are rejected with
HTTP 400.

The response additionally contains `fredtux_session_id`. To resume, the same ID can
be sent as the JSON field `session_id` or as the `X-FredTux-Session-ID` header. By
default the server binds to `0.0.0.0:8765` and is therefore reachable from the
local network. To access it from another machine, use the IP address of this
machine, for example `http://192.168.x.x:8765/v1`; `0.0.0.0` itself is not a
destination address. The server does not yet have authentication and must
therefore not be exposed unprotected to the internet. With `--host 127.0.0.1` the
binding can be limited to the local machine again.

## Shell and file tools

Shell access is implemented as an interchangeable toolset and is **not** enabled
by free text in the system prompt. The security level is set in `shell.nd`.

| Mode | Behaviour |
|---|---|
| `allowlist` | Only individual commands from `FREDTUX_SHELL_ALLOWED_COMMANDS`; no shell metacharacters |
| `standard` | Standard commands `pwd`, `ls`, `cd`, `grep`, `ping`, `lynx`, `top`, `ssh`, `screen` plus file tools in the write area |
| `coding` | Development tools, text processing, archives, process/network diagnostics, and script infrastructure with pipes/redirection; 300 s timeout |
| `yolo` | Arbitrary bash commands; enable deliberately only |

Current `shell.nd` file:

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

`FREDTUX_SHELL_EXTRA_ROOTS` adds comma-separated paths that are additionally
allowed as read, working, and target paths in coding mode – for example the backup
directory `~/BACKUP/fredtux-2.0-backups/`. Writing via `write_file` remains
restricted to `FREDTUX_SHELL_WRITE_ROOT`; coding output may additionally end up in
`FREDTUX_SHELL_EXTRA_ROOTS`. The redirect target `/dev/null` is always allowed in
coding mode.

The available file and command tools are:

- `read_file(path, max_bytes)` – read UTF-8 files
- `write_file(path, content)` – write text files in the write area
- `change_permissions(path, mode)` – set octal permissions in the write area
- `run_coding_command(steps, cwd, redirect_stdout, stdin, stderr)` – preferred, structured argv pipeline without a shell string; `stderr` is `capture` or `discard`
- `execute_command(command, cwd)` – restricted compatibility API; validates shell syntax before executing it

In `allowlist` and `standard` mode, `shell=True` is never used. In `coding` mode,
`run_coding_command` is preferably used for new tasks: the steps each contain a
separate `program` and a list of arguments. `stdin` feeds the first step; afterwards
its stdout is automatically used as the stdin of the next step. `stderr=capture`
collects the error messages of all steps, `stderr=discard` suppresses them. Per step
you can set `stdin` (step 1 only), `stderr`, and `redirect_stdout`. This means shell
syntax characters in arguments are never interpreted as code, and the pipeline is
executed without `shell=True`.

`execute_command` is kept only as a restricted compatibility API with a central
validator. In both APIs, only the development commands defined in `CODING_COMMANDS`
are allowed; paths outside the released directories are rejected. `coding` uses
`FREDTUX_CODING_TIMEOUT` (default 300 seconds), not the short default timeout. Project
and FredTux home paths may be read in coding mode; write actions remain inside the
configured write area. This is expressly not a sandbox for arbitrary Python, bash,
or git programs.

In `allowlist` and `standard` mode, commands such as `rm -rf`, pipes, `;`, `&&`,
command substitution, and redirections are rejected.

In standard mode, `config.nd`, `shell.nd`, `.env`, `.git`, and `.venv` are
protected against write access. API keys are stripped from the executed environment.

YOLO is activated exclusively by manual configuration:

```ini
FREDTUX_SHELL_MODE=yolo
```

That gives the agent practically unrestricted shell access. Use it only in a
trusted, isolated environment.

### Coding tools

`CODING_COMMANDS` in `fredtux/tools/shell.py` is the authoritative allowlist for
`run_coding_command` and the compatibility API `execute_command`. The following
are allowed:

- **Development:** `python3`, `pip3`, `make`, `git`, `find`, `ruff`, `black`, `mypy`, `bash`, `sh`
- **Project/files:** `which`, `wc`, `head`, `tail`, `sort`, `uniq`, `date`, `rm`, `cp`, `mv`, `chmod`, `stat`, `dirname`, `basename`, `mkdir`, `touch`, `cat`, `test`, `env`
- **Text processing:** `sed`, `awk`, `xargs`, `cut`, `tr`, `nl`, `paste`, `join`, `comm`, `column`, `fold`, `expand`, `split`, `csplit`
- **Comparison/integrity:** `diff`, `patch`, `md5sum`, `sha256sum`, `base64`
- **Archives:** `tar`, `zip`, `unzip`, `gzip`, `xz`
- **Processes/network:** `ps`, `kill`, `timeout`, `watch`, `nc`, `telnet`, `dig`, `ss`, `curl`, `wget`
- **Filesystem/general:** `pwd`, `ls`, `grep`, `realpath`, `readlink`, `file`, `install`, `uuidgen`, `tee`, `od`, `hexdump`, `echo`, `printf`, `true`, `false`, `df`, `du`, `free`

`python` and `fzf` are deliberately left out: on the supported systems
`python3` is the interpreter that is present; `fzf` is not a required FredTux
dependency. After a change to `CODING_COMMANDS`, the running FredTux process must
be restarted so that it uses the new list.

## Tool loops: progress instead of a fixed round count

FredTux no longer aborts the agent loop after a fixed number of rounds. A round
counts as *progress* if at least one of its tool calls was answered without
`ERROR`. As long as that happens, the agent may execute arbitrarily many tools
one after another – including creating five or twelve files in a single request.

Two limits still guard against runaway loops:

| Setting | Default | Effect |
|---|---|---|
| `FREDTUX_MAX_IDLE_ROUNDS` | `6` | Abort after this number of *consecutive* rounds without progress; every successful round resets the counter |
| `FREDTUX_MAX_TOTAL_ROUNDS` | `40` | Hard upper bound on all rounds as a last safety net |

Repeated failures are additionally caught by `_tool_loop_error`: the second call
of the same tool with the same failing parameters, or three consecutive
`ERROR`s, ends the loop immediately – regardless of the round counters.

If a limit is hit, the message names the cause:

```text
ERROR: Maximum number of tool loops reached. Rounds total=40,
Rounds without progress=0, limit=40/6. Last tool call: list_files({"path":"."})
```

The same values appear in the error log under the `tool_loop` category.

## Error log and live log tailing

Technical errors are stored append-only as JSON Lines in
`~/.fredtux-2.0/logs/errors.jsonl`. Each entry contains a UTC timestamp, the
session ID, the category, and the error message. While FredTux is running, the log
can be followed live:

```bash
tail -F ~/.fredtux-2.0/logs/errors.jsonl
```

The file is intentionally not rotated. The full conversation remains in the
session files under `~/.fredtux-2.0/sessions/`.

## Coding agent rules

The binding operating rules are in `CODING_AGENT.md` and are loaded into the
system prompt on every agent initialisation. They require, among other things:
check RAG and existing files first, use `run_coding_command` instead of raw
shell strings, limit write paths, do not repeat the same call after an error,
and abort after two identical or three consecutive tool errors.

### Changing rules at runtime: `reload_rules`

This makes `CODING_AGENT.md` effective not only at startup: the agent may modify
the file with `write_file` and then load it into the running system prompt with
the `reload_rules` tool. Without that call, a changed rule would only take
effect in the next session – otherwise the cycle of "find the error, understand
the cause, record the rule, act differently from now on" would stay open, and
the rule would only take effect after a restart.

`reload_rules` replaces only the system message of the current session; the
conversation history remains untouched. The response states the resulting state:

```text
Rule set reloaded: CODING_AGENT.md now has 27 lines (+2). The rules apply immediately in this session.
Rule set unchanged: CODING_AGENT.md with 27 lines is already active.
```

If `CODING_AGENT.md` does not exist, the system prompt falls back to the plain
base instruction. If the session has no system message, it is inserted at
position 0.

## Agent and tool architecture

```text
main.py / .venv/bin/fredtux / .venv/bin/fredtux-api
        │
        ├── fredtux.interfaces.cli    interactive CLI
        └── fredtux.interfaces.api    OpenAI-compatible HTTP server
                │
                ├── fredtux.config    environment and runtime directories
                ├── fredtux.llm       OpenAI chat + native Ollama diagnostics
                ├── fredtux.core      agent loop and tool execution
                ├── fredtux.sessions  Markdown + JSON sidecar + file locking
                └── fredtux.tools     file-based Markdown RAG
```

The agent loop sends the system, user, and tool history to the configured
model. Supported tools:

- `save_knowledge(title, content)` – save a Markdown note in the RAG
- `search_knowledge(query)` – search local Markdown files
- `list_knowledge()` – list the existing RAG files

The tool implementation currently only writes into `FREDTUX_HOME` and starts no
shell commands. New tools should be registered via `ToolRegistry` and covered
by tests.

## Runtime data and privacy

Default directories:

```text
~/.fredtux-2.0/
├── sessions/                 chat transcripts (.md + .json)
└── data/brain/rag/           persistent Markdown notes
```

These do not belong in the repository:

- `.venv/`
- `*.pyc` and `__pycache__/`
- API keys
- private session or RAG data
- generated `*.egg-info/` directories

Always check before publishing:

```bash
git status --short
git check-ignore -v .venv fredtux_2.0.egg-info
```

## Troubleshooting

### `Ollama at ... is not reachable`

- Check `FREDTUX_OLLAMA_URL` and the port
- Check the network/SSH connection to the target host
- Start Ollama on the target node
- do not use an OpenAI-compatible hub (for example a router on port `8000`) as a local Ollama test

### `Model ... is not installed`

The output lists the names returned by `/api/tags`. Then, for example:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 ollama pull <exact-model-name>
```

### `Timeout on /api/tags`

The service responds, but the model list is slow. Increase the timeout:

```bash
FREDTUX_OLLAMA_TIMEOUT=120 .venv/bin/python scripts/devcheck.py
```

### Starting with the wrong Python environment

Do not use `python` or the system Python:

```bash
.venv/bin/python scripts/devcheck.py --no-ollama-check
```

### `ModuleNotFoundError` at the entry point

The installation is outdated or was executed outside the venv:

```bash
.venv/bin/python -m pip install --no-deps --editable .
.venv/bin/fredtux --help
```

## Tests and quality assurance

```bash
.venv/bin/python -m compileall -q .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/devcheck.py --no-ollama-check
.venv/bin/fredtux --help
```

These checks are run locally on Python 3.10, 3.11, and 3.12; the project has no
GitHub CI. The live Ollama check is deliberately left out, because it requires an
internal network host and an installed model.

## Dependencies

- **Runtime:** no external Python packages; `urllib`, `json`, `pathlib`, `fcntl`,
  and other standard library modules.
- **Development:** `venv`, `pip`, and the setuptools backend used for the
  editable install; no test library required.
- **Runtime service:** Ollama is an external prerequisite, not a Python
  dependency.

Details are in [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

## GitHub publication

`CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, and `LICENSE` are ready.

Before every push:

```bash
git status --short
git diff --check
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/devcheck.py --no-ollama-check
```

Then push the current state to `main` on GitHub and publish the version from
`pyproject.toml` (currently `0.5.0`) as a release. Do not commit secrets, `.venv`
contents, or private `~/.fredtux-2.0` data.

## License

AGPL-3.0-or-later. The full license is in `LICENSE`.

## Powered by AI

This project was developed with the help of AI-assisted tooling for the code
changes and the documentation. The code, the tests, and the architectural decisions
come from a human who remains accountable for them; any defects that remain are
accordingly the responsibility of the project.

The models used are not named. The tools used have no influence on the license:
the project remains under AGPL-3.0-or-later (see [License](#license)).
