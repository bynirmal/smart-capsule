"""Compression engine tests: modes, priorities, labelled token estimates."""

from __future__ import annotations

import pytest

from core.compression_engine import BUDGETS, compress
from core.context_engine import extract
from core.parser_engine import parse_text


def _build(message_count: int = 40):
    parts: list[str] = ["User: We must keep the API stateless and never log tokens."]
    for index in range(message_count):
        role = "Assistant" if index % 2 else "User"
        parts.append(
            f"{role}: step {index} — we implemented handler {index} with FastAPI and PostgreSQL, "
            "the tests pass and the schema migration was added. Next step is wiring pagination "
            "for page " + str(index) + "."
        )
    parts.append("User: Next step is the final review.")
    text = "\n\n".join(parts)
    result = parse_text(text)
    return result, extract(result)


def test_balanced_keeps_priority_sections() -> None:
    result, context = _build()
    compression = compress(context, result, "balanced")
    titles = [title for title, _ in compression.sections]
    # The only explicit statement is a constraint, so it belongs to the protected
    # requirements section instead of being duplicated in "User instructions".
    assert "Project requirements" in titles
    assert "Next action" in titles
    flattened = " ".join(item for _, items in compression.sections for item in items)
    assert "stateless" in flattened
    assert compression.original_text_included is False
    assert compression.capsule_tokens > 0
    assert "heuristic" in compression.token_method


def test_high_compression_is_not_larger_than_balanced() -> None:
    result, context = _build(80)
    balanced = compress(context, result, "balanced")
    high = compress(context, result, "high")
    full = compress(context, result, "full")
    assert high.capsule_tokens <= balanced.capsule_tokens
    assert balanced.capsule_tokens <= full.capsule_tokens
    assert high.omitted_messages >= 0


def test_full_preservation_includes_original_text() -> None:
    result, context = _build(10)
    compression = compress(context, result, "full")
    assert compression.original_text_included is True
    assert result.text in compression.plain_text or "Original conversation" in compression.markdown


def test_unknown_mode_rejected() -> None:
    result, context = _build(2)
    with pytest.raises(ValueError):
        compress(context, result, "ultra")


def test_budgets_are_ordered() -> None:
    assert BUDGETS["high"] < BUDGETS["balanced"] < BUDGETS["full"]


def test_markdown_and_plain_rendering() -> None:
    result, context = _build(4)
    compression = compress(context, result, "balanced")
    markdown = compression.markdown
    assert compression.summary.splitlines()[0] in markdown
    assert "##" in markdown
    assert compression.plain_text.startswith(compression.summary)
