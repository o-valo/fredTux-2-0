# Dependencies and version strategy

> Language: English | [Deutsche Fassung](DEPENDENCIES.ger.md)

## Python runtime

- Minimum version: Python 3.10
- Development and CI reference: Python 3.12
- Supported are 3.10, 3.11, and 3.12.
- FredTux uses no external runtime packages.

The runtime uses only the standard library, including `urllib`, `json`,
`pathlib`, `dataclasses`, `argparse`, `unittest`, `re`, `fcntl`, and
`contextlib`.

## Build and development

`pyproject.toml` uses PEP 517 with `setuptools>=68` as the build backend.
Setuptools is only needed when building or editable-installing the project, not
for normal startup within the finished `.venv`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-deps --editable .
```

`--no-deps` is correct because the project currently has no runtime
dependencies. If libraries are added later, they must be entered in
`[project].dependencies` and in `docs/DEPENDENCIES.md`.

## External services

Ollama is an optional runtime service, not a Python dependency. The default
diagnostics use the native Ollama endpoint. A different OpenAI-compatible API
can be configured with `FREDTUX_BASE_URL` and `FREDTUX_API_KEY`; for that,
`--no-ollama-check` must be used.

## Encryption and secrets

`FREDTUX_API_KEY` does not belong in `.env.example`, CI logs, or git history. For
GitHub Actions a repository secret is only needed if real external API tests are
added later. Normal CI uses no secrets.
