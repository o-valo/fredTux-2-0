"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Config:
    home: Path
    base_url: str
    model: str
    api_key: str | None
    request_timeout: float = 120.0
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_timeout: float = 60.0
    skip_ollama_check: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8765
    api_model: str = "fredtux-2-0"
    shell_mode: str = "allowlist"
    shell_root: Path = Path(".")
    shell_write_root: Path = Path(".")
    shell_extra_roots: tuple[Path, ...] = ()
    shell_allowed_commands: str = ""
    shell_write_enabled: bool = False
    shell_timeout: float = 30.0
    coding_timeout: float = 300.0
    max_idle_rounds: int = 6
    max_total_rounds: int = 40

    @classmethod
    def from_env(cls) -> "Config":
        settings = _read_quick_config()
        shell_settings = _read_quick_config(
            Path(os.environ.get("FREDTUX_SHELL_CONFIG_FILE", PROJECT_ROOT / "shell.nd"))
        )
        def get(name: str, default: str) -> str:
            return os.environ.get(name, settings.get(name, shell_settings.get(name, default)))

        home = _project_path(get("FREDTUX_HOME", str(Path.home() / ".fredtux-2.0")))
        ollama_url = get("FREDTUX_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        return cls(
            home=home,
            base_url=get("FREDTUX_BASE_URL", f"{ollama_url}/v1").rstrip("/"),
            model=get("FREDTUX_MODEL", "VladimirGav/gemma4-26b-16GB-VRAM-Uncensored:latest"),
            api_key=get("FREDTUX_API_KEY", "") or None,
            request_timeout=float(get("FREDTUX_TIMEOUT", "120")),
            ollama_url=ollama_url,
            ollama_timeout=float(get("FREDTUX_OLLAMA_TIMEOUT", "60")),
            skip_ollama_check=_as_bool(get("FREDTUX_SKIP_OLLAMA_CHECK", "0")),
            api_host=get("FREDTUX_API_HOST", "0.0.0.0").strip(),
            api_port=int(get("FREDTUX_API_PORT", "8765")),
            api_model=get("FREDTUX_API_MODEL", "fredtux-2-0").strip(),
            shell_mode=get("FREDTUX_SHELL_MODE", "allowlist").strip().lower(),
            shell_root=_project_path(get("FREDTUX_SHELL_ROOT", ".")),
            shell_write_root=_project_path(get("FREDTUX_SHELL_WRITE_ROOT", ".")),
            shell_extra_roots=_parse_roots(get("FREDTUX_SHELL_EXTRA_ROOTS", "")),
            shell_allowed_commands=get("FREDTUX_SHELL_ALLOWED_COMMANDS", "").strip(),
            shell_write_enabled=_as_bool(get("FREDTUX_SHELL_WRITE", "0")),
            shell_timeout=float(get("FREDTUX_SHELL_TIMEOUT", "30")),
            coding_timeout=float(get("FREDTUX_CODING_TIMEOUT", "300")),
            max_idle_rounds=max(1, int(get("FREDTUX_MAX_IDLE_ROUNDS", "6"))),
            max_total_rounds=max(1, int(get("FREDTUX_MAX_TOTAL_ROUNDS", "40"))),
        )

    @property
    def sessions_dir(self) -> Path:
        return self.home / "sessions"

    @property
    def rag_dir(self) -> Path:
        return self.home / "data" / "brain" / "rag"

    @property
    def error_log_path(self) -> Path:
        return self.home / "logs" / "errors.jsonl"

    def ensure_dirs(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        self.error_log_path.parent.mkdir(parents=True, exist_ok=True)


def _as_bool(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "ja", "on"}


def _project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def _parse_roots(value: str) -> tuple[Path, ...]:
    """Liest eine Komma-Liste zusätzlicher freigegebener Pfade (z. B. Backup-Verzeichnisse)."""
    roots: list[Path] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            roots.append(_project_path(item))
    return tuple(roots)


def _read_quick_config(path_value: Path | str | None = None) -> dict[str, str]:
    """Liest eine einfache KEY=WERT-Datei neben dem Projekt oder einen angegebenen Pfad."""
    configured_path = os.environ.get("FREDTUX_CONFIG_FILE") if path_value is None else str(path_value)
    path = Path(configured_path).expanduser() if configured_path else PROJECT_ROOT / "config.nd"
    if not path.is_file():
        return {}
    settings: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Fehler in {path}:{line_number}: erwartet wird KEY=WERT.")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        if not key:
            raise ValueError(f"Fehler in {path}:{line_number}: leerer Schlüssel.")
        settings[key] = value
    return settings
