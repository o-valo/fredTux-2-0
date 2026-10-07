#!/usr/bin/env bash
#
# backup_fredtux.sh – Sichert den gesamten FredTux-2.0-Agenten als komprimiertes .tgz.
#
# Gesichert werden:
#   - ~/fredTux-2-0    (Projektverzeichnis)
#   - ~/.fredtux-2.0   (Konfiguration/Daten)
#
# Zielverzeichnis einstellbar (Priorität):
#   1. Positionsargument oder -d/--dest
#   2. Umgebungsvariable BACKUP_DIR
#   3. Standard: ~/BACKUP/fredtux-2.0-backups
#
# Aufbewahrung (nur die letzten X Backups behalten):
#   - Schalter: -k/--keep N
#   - Umgebungsvariable: BACKUP_KEEP=N
#
# Ausgabe: fredtux-2.0-backup-YYYY-MM-DD_HHMMSS.tgz
#
# Beispiele:
#   ./scripts/backup_fredtux.sh /mnt/backups
#   ./scripts/backup_fredtux.sh --keep 7 /mnt/backups
#   BACKUP_KEEP=7 ./scripts/backup_fredtux.sh

set -euo pipefail

KEEP=""
BACKUP_BASE=""

usage() {
    cat <<EOF
Verwendung: backup_fredtux.sh [OPTIONEN] [ZIELVERZEICHNIS]

Sichert ~/fredTux-2-0 und ~/.fredtux-2.0 als komprimiertes .tgz-Archiv.

Optionen:
  -k, --keep N   Nur die letzten N Backups behalten (ältere werden gelöscht)
  -d, --dest DIR Zielverzeichnis für das Backup
  -h, --help     Diese Hilfe anzeigen

Zielverzeichnis (Priorität):
  1. Positionsargument oder -d/--dest
  2. Umgebungsvariable BACKUP_DIR
  3. Standard: ~/BACKUP/fredtux-2.0-backups

Beispiele:
  ./scripts/backup_fredtux.sh /mnt/backups
  ./scripts/backup_fredtux.sh --keep 7 /mnt/backups
  BACKUP_KEEP=7 ./scripts/backup_fredtux.sh
EOF
}

# --- Argumente parsen ---------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -k|--keep)
            KEEP="${2:-}"
            if [ -z "$KEEP" ]; then
                echo "FEHLER: -k/--keep benötigt eine Anzahl." >&2
                exit 1
            fi
            shift 2
            ;;
        -d|--dest)
            BACKUP_BASE="${2:-}"
            if [ -z "$BACKUP_BASE" ]; then
                echo "FEHLER: -d/--dest benötigt ein Verzeichnis." >&2
                exit 1
            fi
            shift 2
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "FEHLER: Unbekannte Option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            if [ -n "$BACKUP_BASE" ]; then
                echo "FEHLER: Zielverzeichnis wurde bereits gesetzt." >&2
                exit 1
            fi
            BACKUP_BASE="$1"
            shift
            ;;
    esac
done

# --- Zielverzeichnis & Aufbewahrung auflösen ----------------------------------
BACKUP_BASE="${BACKUP_BASE:-${BACKUP_DIR:-$HOME/BACKUP/fredtux-2.0-backups}}"
KEEP="${KEEP:-${BACKUP_KEEP:-0}}"

if ! [[ "$KEEP" =~ ^[0-9]+$ ]]; then
    echo "FEHLER: --keep erwartet eine Ganzzahl, bekam '$KEEP'." >&2
    exit 1
fi

# Nan Sekunden verhindern, dass mehrere Backups innerhalb derselben Sekunde
# denselben Dateinamen erzeugen und sich gegenseitig überschreiben.
STAMP="$(date +%Y-%m-%d_%H%M%S_%N)"
BACKUP_FILE="${BACKUP_BASE}/fredtux-2.0-backup-${STAMP}.tgz"

SOURCE_HOME="${FREDTUX_HOME:-$HOME}"

# --- Ausgeschlossene Inhalte (Schlüssel, Venv, Caches) ----------------------
EXCLUDES=(
    --exclude='fredTux-2-0/.venv'
    --exclude='fredTux-2-0/__pycache__'
    --exclude='fredTux-2-0/.git'
    --exclude='fredTux-2-0/.env'
    --exclude='fredTux-2-0/scripts/*.tgz'
    --exclude='fredtux-2.0-backups'
    --exclude='BACKUP'
)

# --- Vorhandene Quellen sammeln ----------------------------------------------
sources=()
for dir in "fredTux-2-0" ".fredtux-2.0"; do
    if [ -d "${SOURCE_HOME}/${dir}" ]; then
        sources+=("$dir")
    else
        echo "Hinweis: ${SOURCE_HOME}/${dir} existiert nicht und wird übersprungen." >&2
    fi
done

if [ "${#sources[@]}" -eq 0 ]; then
    echo "FEHLER: Weder ${SOURCE_HOME}/fredTux-2-0 noch ${SOURCE_HOME}/.fredtux-2.0 gefunden." >&2
    exit 1
fi

mkdir -p "$BACKUP_BASE"

# --- Backup erstellen ---------------------------------------------------------
tar -czf "$BACKUP_FILE" \
    "${EXCLUDES[@]}" \
    -C "$SOURCE_HOME" \
    "${sources[@]}"

echo "✅ Backup erstellt: $BACKUP_FILE"
ls -lh "$BACKUP_FILE"

# --- Aufbewahrung: nur die letzten KEEP Backups behalten ----------------------
if [ "$KEEP" -gt 0 ]; then
    total="$(find "$BACKUP_BASE" -maxdepth 1 -type f -name 'fredtux-2.0-backup-*.tgz' | wc -l)"
    if [ "$total" -gt "$KEEP" ]; then
        delete_count=$((total - KEEP))
        echo "Aufbewahrung: behalte die letzten $KEEP von $total Backups (lösche $delete_count)."
        find "$BACKUP_BASE" -maxdepth 1 -type f -name 'fredtux-2.0-backup-*.tgz' -print \
            | sort \
            | head -n "$delete_count" \
            | while IFS= read -r old; do
                echo "  🗑  lösche altes Backup: $old"
                rm -f "$old"
            done
    else
        echo "Aufbewahrung: nur $total Backups vorhanden (Limit $KEEP) – nichts zu löschen."
    fi
fi
