# Architecture and operational boundaries

> Language: English | [Deutsche Fassung](ARCHITECTURE.ger.md)

## Components

### `fredtux.config.Config`

Reads the runtime configuration from environment variables and creates the data
directories. `FREDTUX_HOME` is the single central runtime root.

### `fredtux.llm.LLMClient`

Encapsulates two roles:

1. OpenAI-compatible chat endpoint (`/v1/chat/completions`)
2. Native Ollama diagnostics (`/api/version`, `/api/tags`, `/api/ps`)

The diagnostics deliberately use the native API, because that can check models
and service state even when the OpenAI-compatible route is unreachable.

### `fredtux.interfaces.api`

The HTTP server provides `/health`, `/v1/models`, and `/v1/chat/completions`. It
uses `AgentCore` under an in-process lock, accepts an optional `session_id`, and
binds to `0.0.0.0:8765` by default. The virtual API model ID is `fredtux-2-0`;
`fredtux-2.0` remains accepted as a compatibility alias. With `stream: true`,
OpenAI SSE chunks are sent with `data: [DONE]`. There is no authentication or
CORS policy yet.

### `fredtux.core.AgentCore`

Holds the system prompt, the message history, the session store, and the tool
registry. The system prompt loads `CODING_AGENT.md` with the binding anti-loop
and coding rules. After a tool response, the next LLM request is executed; the
loop limits `FREDTUX_MAX_IDLE_ROUNDS` and `FREDTUX_MAX_TOTAL_ROUNDS` prevent runaway
loops.

### `fredtux.sessions.SessionStore`

Writes human-readable Markdown files. A JSON sidecar file preserves tool-call
IDs and exact message objects. `fcntl.flock` serialises access between several
local processes.

### `fredtux.tools`

`ToolRegistry` provides JSON schemas for the model and dispatches calls to local
Python functions. `knowledge.py` implements the file-based RAG. `ShellTools` adds
`read_file`, `write_file`, `change_permissions`, `run_coding_command`, and the
restricted compatibility API `execute_command`, with the modes `allowlist`,
`standard`, `coding`, and `yolo`. `run_coding_command` accepts structured argv
steps and runs pipelines without `shell=True`. `stdin` is only passed to the
first step; afterwards FredTux connects the stdout streams. `stderr` can be
controlled as `capture` or `discard`. The validation of the legacy string is
encapsulated in `fredtux.tools.coding`.
In normal mode, a shell character string is never interpreted.

## Data flow of a message

1. The CLI takes the text and session ID.
2. `AgentCore.ask` appends the user message and logs it.
3. `LLMClient.chat` sends the history plus the tool schemas to the model.
4. On a tool call, the result is executed locally and stored as a tool message.
5. The next model round delivers the visible response; it is stored.

## Security boundaries

- In `allowlist`/standard mode, the agent executes no arbitrary shell commands.
- The `coding` mode is deliberately not an unrestricted YOLO shell: only defined
  development commands, no command substitution, no leaving the project area.
- Tool parameters are validated as a JSON object.
- Session IDs are checked for safe filenames.
- RAG files live under `FREDTUX_HOME` and not in the repository.
- An API key is only used as an `Authorization` header, never printed.

## Not implemented yet

- authenticated network interface
- TUI/GUI and fluent switching between network interfaces
- MCP/plugin lifecycle
- document/image/audio interfaces
- production-grade rights management for session files
