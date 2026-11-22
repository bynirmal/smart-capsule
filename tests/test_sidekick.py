"""Sidekick helpers: quick save, counts and prompt retrieval (no GUI required)."""

from __future__ import annotations

import pytest

from core.parser_engine import parse_text
from core.capsule_generator import generate_capsule
from core.capture_engine import CaptureEngine
from sidekick import quick_actions

TRANSCRIPT = """User: Build a FastAPI invoicing service. You must use PostgreSQL.

Assistant: Done: the schema is implemented.

User: Next step is pagination tests.
"""


def test_quick_save_creates_a_generated_capsule(db) -> None:
    title = quick_actions.quick_save(db, TRANSCRIPT, platform="Claude")
    assert title
    capsules = db.list_capsules()
    assert len(capsules) == 1
    payload = capsules[0].payload()
    assert payload.get("draft") is not True
    assert payload["project"]["name"] == title
    assert payload["compression"]["mode"] in {"balanced", "high", "full"}

    versions = db.query("SELECT note FROM capsule_versions WHERE capsule_id = ?", (capsules[0].id,))
    assert versions and "Sidekick" in versions[0]["note"]


def test_quick_save_rejects_empty_clipboard(db) -> None:
    with pytest.raises(ValueError):
        quick_actions.quick_save(db, "   ")
    assert db.count_capsules() == 0


def test_latest_prompt_requires_a_generated_capsule(db) -> None:
    with pytest.raises(ValueError):
        quick_actions.latest_prompt(db)

    engine = CaptureEngine(db)
    result = engine.analyze_text(TRANSCRIPT)
    draft_id = engine.save_draft(result)
    with pytest.raises(ValueError, match="draft"):
        quick_actions.latest_prompt(db)

    generate_capsule(db, result, capsule_id=draft_id)
    title, prompt = quick_actions.latest_prompt(db, "Claude")
    assert title
    assert "hidden model memory" in prompt
    assert "Claude" in prompt or "concise" in prompt.lower()


def test_status_counts_reports_drafts_and_totals(db) -> None:
    engine = CaptureEngine(db)
    engine.save_draft(engine.analyze_text(TRANSCRIPT))
    quick_actions.quick_save(db, TRANSCRIPT)

    status = quick_actions.sidekick_status(db)
    assert status["capsules"] == 2
    assert status["drafts"] == 1
    assert status["last_title"]
