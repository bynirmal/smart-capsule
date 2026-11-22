"""Sidekick actions that do not depend on the widget.

Every helper performs an explicit, user-initiated operation. Clipboard access
happens only when the user presses a button; nothing is read in the background.
"""

from __future__ import annotations

import logging
from typing import Any

from core.capsule_generator import generate_capsule
from core.capture_engine import CaptureEngine
from core.resume_engine import continuation_prompt
from database.db import Database
from database.models import Capsule

logger = logging.getLogger(__name__)


def clipboard_text(widget) -> str:
    """Read the clipboard for an explicit user action."""
    try:
        return widget.clipboard_get()
    except Exception:  # noqa: BLE001 - empty or non-text clipboard
        return ""


def latest_capsule(db: Database) -> Capsule | None:
    rows = db.recent_capsules(1)
    return rows[0] if rows else None


def capsule_counts(db: Database) -> tuple[int, int]:
    total = int(db.scalar("SELECT COUNT(*) FROM capsules") or 0)
    drafts = int(db.scalar("SELECT COUNT(*) FROM capsules WHERE payload_json LIKE '%\"draft\": true%'") or 0)
    return total, drafts


def quick_save(db: Database, text: str, platform: str | None = None) -> str:
    """Capture + generate a capsule in one step; returns the capsule title."""
    if not text.strip():
        raise ValueError("Nothing to save: the clipboard is empty.")
    engine = CaptureEngine(db)
    result = engine.analyze_text(text, platform_hint=platform)
    draft_id = engine.save_draft(result)
    try:
        payload = db.get_capsule(draft_id).payload()
        _capsule_id, document = generate_capsule(
            db,
            result,
            capsule_id=draft_id,
            mode=db.get_setting("default_compression", "balanced"),
            conversation_id=(payload.get("capture") or {}).get("conversation_id"),
            note="Quick save from Sidekick",
        )
    except Exception:
        db.delete_capsule(draft_id)
        raise
    project = document.get("project") or {}
    return str(project.get("name") or result.title)


def latest_prompt(db: Database, destination: str = "ChatGPT") -> tuple[str, str]:
    """Return ``(capsule title, prompt)`` for the newest generated capsule."""
    capsule = latest_capsule(db)
    if capsule is None:
        raise ValueError("No capsules yet.")
    document = capsule.payload()
    if "project" not in document:
        raise ValueError("The newest capsule is still a capture draft.")
    return capsule.title, continuation_prompt(document, destination)


def sidekick_status(db: Database) -> dict[str, Any]:
    total, drafts = capsule_counts(db)
    latest = latest_capsule(db)
    return {
        "capsules": total,
        "drafts": drafts,
        "last_title": latest.title if latest else "",
    }
