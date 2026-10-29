"""File-based knowledge tools used by the agent."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def save_knowledge(rag_dir: Path, title: str, content: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.strip()).strip("-").lower() or "notiz"
    path = rag_dir / f"{slug}.md"
    if path.exists():
        raise ValueError(f"Eine Wissensdatei mit dem Namen {slug!r} existiert bereits.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title.strip()}\n\n{content.strip()}\n", encoding="utf-8")
    return f"Gespeichert: {path}"


def search_knowledge(rag_dir: Path, query: str, include_archives: bool = False) -> str:
    terms = [term.casefold() for term in re.findall(r"\w+", query) if len(term) > 2]
    results: list[tuple[int, Path, str]] = []
    if include_archives:
        # Archive liegen in einem Unterverzeichnis und wachsen stark; nur auf
        # ausdruecklichen Wunsch mitdurchsuchen, sonst verdraengen sie die
        # eigentlichen Notizen aus den Top-5-Treffern.
        paths = sorted(rag_dir.glob("*.md")) + sorted((rag_dir / "archiv").glob("*.md"))
    else:
        paths = sorted(rag_dir.glob("*.md"))
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        score = sum(text.casefold().count(term) for term in terms)
        if score:
            results.append((score, path, text))
    if not results:
        return "Keine passenden Wissensdateien gefunden."
    results.sort(key=lambda item: item[0], reverse=True)
    return "\n\n".join(f"### {path.stem} ({score} Treffer)\n{text[:3000]}" for score, path, text in results[:5])


def list_knowledge(rag_dir: Path) -> str:
    files = sorted(path.name for path in rag_dir.glob("*.md"))
    listed = "Wissensdateien:\n" + ("\n".join(f"- {name}" for name in files) if files else "(noch keine)")
    archive_dir = rag_dir / "archiv"
    if archive_dir.is_dir():
        archives = sorted(archive_dir.glob("*.md"))
        if archives:
            listed += (
                f"\n\nVerdichtete Sitzungsarchive: {len(archives)} Datei(en) im Unterverzeichnis "
                "'archiv'. Nur mit search_knowledge und include_archives=true durchsuchbar."
            )
    return listed
