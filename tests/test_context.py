"""Context engine tests: extraction quality and certainty marking."""

from __future__ import annotations

from core.context_engine import detect_technologies, extract
from core.parser_engine import parse_text

TRANSCRIPT = """User: I need a FastAPI service for invoicing. You must use PostgreSQL and never expose raw SQL errors.

Assistant: Understood. I will create the project structure.

User: We decided to use SQLAlchemy for the ORM instead of raw psycopg2.

Assistant: Done: the invoice model is implemented.

User: The /invoices endpoint returns a 500 error with a traceback about a missing column.

Assistant: The fix is to run the migration that adds the total_amount column.

User: Next step is adding pagination to the invoice list.
"""


def _context():
    return extract(parse_text(TRANSCRIPT, platform_hint="ChatGPT"))


def test_technologies_and_technical_classification() -> None:
    context = _context()
    assert "FastAPI" in context.technologies
    assert "PostgreSQL" in context.technologies
    assert "SQLAlchemy" in context.technologies
    assert "FastAPI" in context.technical.frameworks
    assert "PostgreSQL" in context.technical.languages or "PostgreSQL" in context.technical.libraries
    assert detect_technologies("we use python and docker") == ["Python", "Docker"]


def test_instructions_and_constraints_are_stated() -> None:
    context = _context()
    texts = " ".join(item.text for item in context.instructions + context.constraints)
    assert "PostgreSQL" in texts
    assert all(item.certainty == "stated" for item in context.instructions)
    assert context.instructions[0].message_index == 0
    # A constraint must appear in both views so nothing is lost from either section.
    assert any("never" in item.text.lower() for item in context.constraints)
    assert any(item.kind == "constraint" for item in context.instructions)


def test_decisions_completed_and_pending() -> None:
    context = _context()
    assert any("SQLAlchemy" in item.text for item in context.decisions)
    assert any("invoice model" in item.task for item in context.completed)
    assert any("pagination" in item.task for item in context.pending)


def test_error_pairs_with_solution() -> None:
    context = _context()
    assert context.errors, "the traceback should be captured"
    error = context.errors[0]
    assert "traceback" in error.error.lower() or "500 error" in error.error.lower()
    assert error.solution
    assert error.resolved is True


def test_next_action_comes_from_explicit_statement() -> None:
    context = _context()
    assert "pagination" in context.next_action.lower()
    assert context.next_action_certainty == "stated"


def test_stage_is_marked_inferred() -> None:
    context = _context()
    assert context.stage_certainty == "inferred"
    assert context.stage in {
        "implementation",
        "debugging (unresolved errors)",
        "planning / design",
        "maintenance",
    }


def test_short_capture_warns_and_never_invents_pending() -> None:
    context = extract(parse_text("User: hi\n\nAssistant: hello"))
    assert context.warnings
    assert context.next_action_certainty == "inferred"


def test_no_instructions_is_reported() -> None:
    context = extract(parse_text("User: tell me a joke\n\nAssistant: a joke"))
    assert any("instructions" in warning.lower() for warning in context.warnings)


def test_technology_detection_is_word_bounded() -> None:
    # 'torch' inside 'torches' must not match.
    assert "PyTorch" not in detect_technologies("we bought torches and go documents")
    assert "PyTorch" in detect_technologies("we use torch for training")
