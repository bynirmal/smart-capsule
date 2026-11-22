"""Capsule search with payload matching and snippet extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass

from database.db import Database
from database.models import Capsule

_WS = re.compile(r"\s+")


@dataclass(slots=True)
class SearchHit:
    capsule: Capsule
    snippet: str
    where: str


def _snippet(text: str, term: str, width: int = 120) -> str:
    collapsed = _WS.sub(" ", text or "").strip()
    if not term:
        return collapsed[:width]
    index = collapsed.lower().find(term.lower())
    if index < 0:
        return collapsed[:width]
    start = max(0, index - width // 3)
    end = min(len(collapsed), index + len(term) + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(collapsed) else ""
    return f"{prefix}{collapsed[start:end]}{suffix}"


def search(db: Database, term: str, *, limit: int = 50) -> list[SearchHit]:
    """Search titles, summaries, next actions and the stored payload."""
    query = (term or "").strip()
    if not query:
        rows = db.query("SELECT * FROM capsules WHERE is_archived = 0 ORDER BY created_at DESC LIMIT ?", (limit,))
        return [
            SearchHit(Capsule.from_row(row), _snippet(Capsule.from_row(row).summary, ""), "recent")
            for row in rows
        ]

    like = f"%{query}%"
    rows = db.query(
        "SELECT * FROM capsules WHERE is_archived = 0 AND (title LIKE ? OR summary LIKE ? "
        "OR next_action LIKE ? OR payload_json LIKE ?) ORDER BY created_at DESC LIMIT ?",
        (like, like, like, like, limit),
    )

    hits: list[SearchHit] = []
    for row in rows:
        capsule = Capsule.from_row(row)
        lowered = query.lower()
        if lowered in capsule.title.lower():
            hits.append(SearchHit(capsule, _snippet(capsule.title, query), "title"))
        elif lowered in capsule.summary.lower():
            hits.append(SearchHit(capsule, _snippet(capsule.summary, query), "summary"))
        elif lowered in capsule.next_action.lower():
            hits.append(SearchHit(capsule, _snippet(capsule.next_action, query), "next action"))
        else:
            hits.append(SearchHit(capsule, _snippet(capsule.payload_json, query), "content"))
    return hits
