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


def search_knowledge(rag_dir: Path, query: str) -> str:
    terms = [term.casefold() for term in re.findall(r"\w+", query) if len(term) > 2]
    results: list[tuple[int, Path, str]] = []
    for path in sorted(rag_dir.glob("*.md")):
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
    return "Wissensdateien:\n" + ("\n".join(f"- {name}" for name in files) if files else "(noch keine)")
