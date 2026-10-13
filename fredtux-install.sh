#!/usr/bin/env bash
# Install FredTux 2.0 on a fresh computer without copying the original .venv.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

install_system_dependencies() {
    echo "==> Fehlende Systempakete werden über apt installiert"
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "FEHLER: apt-get wurde nicht gefunden. Bitte python3, python3-venv und python3-pip manuell installieren." >&2
        exit 1
    fi
    if [ "$(id -u)" -eq 0 ]; then
        APT=(apt-get)
    elif command -v sudo >/dev/null 2>&1; then
        APT=(sudo apt-get)
    else
        echo "FEHLER: Für die Paketinstallation werden Root-Rechte oder sudo benötigt." >&2
        exit 1
    fi
    "${APT[@]}" update
    DEBIAN_FRONTEND=noninteractive "${APT[@]}" install -y python3 python3-venv python3-pip
}

venv_python_ok() {
    .venv/bin/python - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

venv_has_pip() {
    [ -x .venv/bin/python ] && .venv/bin/python -m pip --version >/dev/null 2>&1
}

create_venv() {
    echo "==> Virtuelle Umgebung wird erstellt: .venv"
    python3 -m venv .venv
}

# pip in einer vorhandenen Umgebung nachinstallieren; ohne ensurepip (z. B. wenn
# python3-venv fehlt) schlägt das fehl und die Umgebung wird neu erstellt.
repair_venv_pip() {
    [ -x .venv/bin/python ] || return 1
    venv_python_ok || return 1
    .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || return 1
    venv_has_pip
}

# Ohne ensurepip legt `python3 -m venv` eine Umgebung ohne pip an. Die Prüfung
# erkennt das und installiert die Systempakete nach.
if ! command -v python3 >/dev/null 2>&1 \
    || ! python3 -m venv --help >/dev/null 2>&1 \
    || ! python3 -m ensurepip --version >/dev/null 2>&1; then
    install_system_dependencies
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "FEHLER: python3 wurde nicht gefunden." >&2
    exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("FEHLER: FredTux 2.0 benötigt Python 3.10 oder neuer.")
PY

# Eine vorhandene .venv wird nur übernommen, wenn sie zu Python 3.10+ passt und
# pip enthält. Kopierte oder mit --without-pip erzeugte Umgebungen sind sonst
# unbrauchbar; `python -m pip` bricht dort mit "No module named pip" ab. In dem
# Fall wird pip per ensurepip nachinstalliert, sonst die Umgebung neu erstellt.
if [ ! -e .venv ]; then
    create_venv
elif venv_python_ok && venv_has_pip; then
    echo "==> Vorhandene .venv wird verwendet"
elif repair_venv_pip; then
    echo "==> Vorhandene .venv wird verwendet (pip wurde nachinstalliert)"
else
    echo "==> Vorhandene .venv ist unbrauchbar und wird neu erstellt"
    rm -rf .venv
    create_venv
fi

if ! venv_has_pip; then
    echo "FEHLER: In .venv ist kein pip verfügbar. Bitte die Umgebung löschen und erneut installieren:" >&2
    echo "  rm -rf .venv && bash fredtux-install.sh" >&2
    exit 1
fi

echo "==> FredTux 2.0 wird installiert"
.venv/bin/python -m pip install --disable-pip-version-check --no-deps -e .

# Lokale Konfiguration nur anlegen, wenn sie noch nicht existiert.
if [ ! -f config.nd ] && [ -f config.nd.example ]; then
    cp config.nd.example config.nd
    echo "==> config.nd aus config.nd.example erstellt"
fi

# Laufzeitverzeichnisse werden über die aktive Konfiguration angelegt.
# So funktioniert sowohl ein projektspezifisches FREDTUX_HOME als auch der
# Standardpfad ~/.fredtux-2.0, ohne private Daten zu kopieren.
FREDTUX_RUNTIME_DIR="$(.venv/bin/python - <<'PY'
from fredtux.config import Config
config = Config.from_env()
config.ensure_dirs()
print(config.home)
PY
)"

cat <<EOF

Installation abgeschlossen.

Start:
  cd "$PROJECT_DIR"
  .venv/bin/fredtux

API-Server:
  .venv/bin/fredtux --serve

Die lokale Laufzeit liegt in:
  $FREDTUX_RUNTIME_DIR

Hinweis: API-Zugangsdaten gehören nicht in Git. Trage sie bei Bedarf in
config.nd oder über Umgebungsvariablen ein.
EOF
