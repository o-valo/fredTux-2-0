#!/usr/bin/env bash
#
# tagesschau_feed.sh – Holt die neuesten Nachrichten von tagesschau.de über den RSS-Feed.
#
# Nutzt den offiziellen RSS-2.0-Feed:
#   https://www.tagesschau.de/index~rss2.xml
#
# WICHTIG: Der Feed antwortet auf .../index~rss2.xml (ohne Slash).
# Eine URL mit Slash (.../index~rss2/) liefert HTTP 308 → curl braucht -L,
# sonst kommt eine leere Antwort.
#
# Standard: zeigt die 10 neuesten redaktionellen Nachrichten (Titel, Zeit, Link).
#
# Optionen:
#   -n N            Anzahl der anzuzeigenden Nachrichten (Standard: 10)
#   -a, --all       Alle Nachrichten des Feeds anzeigen (ohne Filter)
#   -r, --raw       Rohen XML-Feed ausgeben (statt aufbereiteter Liste)
#   -o, --output F  Feed in Datei F speichern
#   -h, --help      Diese Hilfe anzeigen
#
# Beispiele:
#   ./scripts/tagesschau_feed.sh
#   ./scripts/tagesschau_feed.sh -n 5
#   ./scripts/tagesschau_feed.sh --all
#   ./scripts/tagesschau_feed.sh --raw --output /tmp/feed.xml
#
# Ausgabe: Liste mit Titel, Veröffentlichungszeit und Link.

set -euo pipefail

FEED_URL="https://www.tagesschau.de/index~rss2.xml"
COUNT=10
MODE="list"        # list | all | raw
OUTPUT_FILE=""

usage() {
    cat <<EOF
Verwendung: tagesschau_feed.sh [OPTIONEN]

Holt die neuesten Nachrichten von tagesschau.de über den RSS-Feed.

Optionen:
  -n N            Anzahl der anzuzeigenden Nachrichten (Standard: 10)
  -a, --all       Alle Nachrichten des Feeds anzeigen (ohne Filter)
  -r, --raw       Rohen XML-Feed ausgeben (statt aufbereiteter Liste)
  -o, --output F  Feed in Datei F speichern (funktioniert auch mit --raw)
  -h, --help      Diese Hilfe anzeigen

Beispiele:
  ./scripts/tagesschau_feed.sh
  ./scripts/tagesschau_feed.sh -n 5
  ./scripts/tagesschau_feed.sh --all
  ./scripts/tagesschau_feed.sh --raw --output /tmp/feed.xml
EOF
}

# --- Argumente parsen ---------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -n)
            COUNT="${2:-}"
            if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [ "$COUNT" -lt 1 ]; then
                echo "FEHLER: -n erwartet eine positive Ganzzahl, bekam '$COUNT'." >&2
                exit 1
            fi
            shift 2
            ;;
        -a|--all)
            MODE="all"
            shift
            ;;
        -r|--raw)
            MODE="raw"
            shift
            ;;
        -o|--output)
            OUTPUT_FILE="${2:-}"
            if [ -z "$OUTPUT_FILE" ]; then
                echo "FEHLER: -o/--output benötigt einen Dateipfad." >&2
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
            echo "FEHLER: Unerwartetes Argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

# --- Feed abrufen -------------------------------------------------------------
# -s: stumm, -L: Redirects folgen (308!), -A: Browser-User-Agent.
FEED_DATA="$(curl -s -L -A 'Mozilla/5.0' "$FEED_URL")"

if [ -z "$FEED_DATA" ]; then
    echo "FEHLER: Feed-Abruf lieferte keine Daten von $FEED_URL" >&2
    exit 1
fi

# --- Optional in Datei speichern ----------------------------------------------
if [ -n "$OUTPUT_FILE" ]; then
    printf '%s\n' "$FEED_DATA" > "$OUTPUT_FILE"
    echo "Feed gespeichert: $OUTPUT_FILE"
fi

# --- Rohen Feed ausgeben ------------------------------------------------------
if [ "$MODE" = "raw" ]; then
    printf '%s\n' "$FEED_DATA"
    exit 0
fi

# --- Nachrichten extrahieren --------------------------------------------------
# Titel, pubDate und Link je <item> werden mit grep herausgezogen.
# Sendungsformate (Livestream, tagesschau-Sendungen, Wetter, Podcasts etc.)
# werden für den Standard-/List-Modus herausgefiltert, damit nur redaktionelle
# Nachrichten übrig bleiben.
TITLES="$(printf '%s\n' "$FEED_DATA" | grep '<title>' | sed 's/.*<title>\(.*\)<\/title>.*/\1/')"
DATES="$(printf '%s\n' "$FEED_DATA" | grep '<pubDate>' | sed 's/.*<pubDate>\(.*\)<\/pubDate>.*/\1/')"
LINKS="$(printf '%s\n' "$FEED_DATA" | grep '<link>' | grep -v 'www.tagesschau.de/$' | sed 's/.*<link>\(.*\)<\/link>.*/\1/')"

if [ "$MODE" = "all" ]; then
    printf '%s\n' "$TITLES" | head -n "$COUNT"
    exit 0
fi

# Filtern: Kanal-Titel (erste Zeile) verwerfen, dann Sendungsformate herausfiltern.
FILTERED="$(printf '%s\n' "$TITLES" | tail -n +2 | grep -viE 'livestream|tagesschau24|tagesschau in 100|tagesthemen|tagesschau in einfacher|gebärdensprache|wetter deutschland|regenradar|podcast|^tagesschau$')"

# Anzahl wählen: wenn weniger Nachrichten als gewünscht, alle anzeigen.
DISPLAY_COUNT="$COUNT"
total="$(printf '%s\n' "$FILTERED" | grep -c . || true)"
if [ "$total" -lt "$COUNT" ]; then
    DISPLAY_COUNT="$total"
fi

printf '%s\n' "$FILTERED" | head -n "$DISPLAY_COUNT" | nl -w 2 -s '. '
