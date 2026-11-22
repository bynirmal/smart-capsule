"""Capture engine tests: parsing, role splitting, code preservation, drafts."""

from __future__ import annotations

import json

import pytest

from core.capture_engine import CaptureEngine
from core.parser_engine import (
    ParseError,
    detect_platform,
    estimate_tokens,
    parse_file,
    parse_text,
)

TRANSCRIPT = """User: Build a FastAPI service with JWT auth.

Assistant: Here is the module.

```python
def create_token(user_id: str) -> str:
    # Assistant: this is code, not a role marker
    return sign(user_id)
```

User: Now add refresh tokens.
"""


def test_role_splitting_and_code_preservation() -> None:
    result = parse_text(TRANSCRIPT, platform_hint="Claude")
    assert result.message_count == 3
    assert [m.role for m in result.messages] == ["user", "assistant", "user"]
    assert result.platform == "Claude"
    assert result.platform_confidence == "high"
    assert len(result.code_blocks) == 1
    assert result.code_blocks[0].language == "python"
    assert "return sign(user_id)" in result.code_blocks[0].content
    # The line "Assistant:" inside the fence must not split the message.
    assert "this is code, not a role marker" in result.messages[1].content
    assert result.messages[1].contains_code is True
    assert result.messages[0].contains_code is False


def test_long_conversation_keeps_every_message() -> None:
    text = "\n\n".join(
        f"{'User' if index % 2 == 0 else 'Assistant'}: turn {index} with some content"
        for index in range(200)
    )
    result = parse_text(text)
    assert result.message_count == 200
    assert result.messages[0].role == "user"
    assert result.messages[-1].role == "assistant"
    assert result.messages[-1].content.endswith("turn 199 with some content")


def test_unlabelled_capture_is_kept_with_warning() -> None:
    result = parse_text("Just a loose paragraph of context without any role labels.")
    assert result.message_count == 1
    assert result.messages[0].role == "user"
    assert any("No role markers" in warning for warning in result.warnings)
    assert result.platform_confidence == "low"


def test_empty_capture_rejected() -> None:
    with pytest.raises(ParseError):
        parse_text("   \n  ")


def test_platform_detection_signals() -> None:
    platform, confidence, reason = detect_platform("You said: hello\n\nChatGPT said: hi")
    assert platform == "ChatGPT"
    assert confidence in {"medium", "high"}
    assert reason

    platform, confidence, _ = detect_platform("Anthropic's Claude answered this.")
    assert platform == "Claude"

    platform, confidence, _ = detect_platform("nothing specific here")
    assert platform == "Other"
    assert confidence == "low"


def test_heading_style_transcript() -> None:
    text = "## Human\nHow do I cache this?\n\n## Assistant\nUse a TTL cache."
    result = parse_text(text)
    assert result.message_count == 2
    assert result.messages[0].role == "user"
    assert result.messages[1].role == "assistant"


def test_token_estimate_is_labelled_heuristic() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcdefgh") == 2
    result = parse_text(TRANSCRIPT)
    assert result.token_estimate > 0
    assert "heuristic" in result.summary_line


def test_parse_json_message_list(tmp_path) -> None:
    payload = {
        "title": "JWT refactor",
        "platform": "Claude",
        "messages": [
            {"role": "user", "content": "Add refresh tokens"},
            {"role": "assistant", "content": "Here:\n```python\nprint('ok')\n```"},
        ],
    }
    path = tmp_path / "chat.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = parse_file(path, platform_hint=None)
    assert result.title == "JWT refactor"
    assert result.platform == "Claude"
    assert result.message_count == 2
    assert result.code_blocks[0].language == "python"
    assert result.source_kind == "json"


def test_parse_chatgpt_mapping_export(tmp_path) -> None:
    payload = {
        "title": "Exported thread",
        "mapping": {
            "a": {"message": {"author": {"role": "user"}, "content": {"parts": ["first"]}}},
            "b": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["second"]}}},
        },
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = parse_file(path)
    assert [m.role for m in result.messages] == ["user", "assistant"]
    assert result.messages[1].content == "second"


def test_corrupted_json_reports_line(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"messages": [}', encoding="utf-8")
    with pytest.raises(ParseError) as error:
        parse_file(path)
    assert "not valid JSON" in str(error.value)


def test_unsupported_and_missing_files(tmp_path) -> None:
    with pytest.raises(ParseError):
        parse_file(tmp_path / "missing.txt")

    xml = tmp_path / "chat.xml"
    xml.write_text("<chat/>", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_file(xml)


def test_markdown_file_import(tmp_path) -> None:
    path = tmp_path / "session.md"
    path.write_text(TRANSCRIPT, encoding="utf-8")
    result = parse_file(path)
    assert result.source_kind == "markdown"
    assert result.source_name == "session.md"
    assert result.message_count == 3


def test_save_draft_persists_conversation_and_messages(db) -> None:
    engine = CaptureEngine(db)
    result = engine.analyze_text(TRANSCRIPT, platform_hint="ChatGPT")
    capsule_id = engine.save_draft(result)

    capsule = db.get_capsule(capsule_id)
    assert capsule is not None
    assert capsule.title == "Build a FastAPI service with JWT auth."

    conversation = db.query_one("SELECT * FROM conversations WHERE capsule_id = ?", (capsule_id,))
    assert conversation is not None
    assert conversation["message_count"] == 3
    assert "return sign(user_id)" in conversation["raw_text"]

    messages = db.query(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY sequence",
        (conversation["id"],),
    )
    assert [row["role"] for row in messages] == ["user", "assistant", "user"]

    payload = capsule.payload()
    assert payload["draft"] is True
    assert payload["capture"]["message_count"] == 3
    assert payload["capture"]["code_block_count"] == 1

    runs = db.query("SELECT stage, status FROM processing_history WHERE capsule_id = ?", (capsule_id,))
    assert runs and runs[0]["stage"] == "capture"


def test_save_draft_removes_capsule_when_conversation_write_fails(db, monkeypatch) -> None:
    """A capsule must never survive without the conversation it captured."""
    from contextlib import contextmanager

    engine = CaptureEngine(db)
    result = engine.analyze_text(TRANSCRIPT)
    real_connection = db.connection

    class FailingInsert:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, params=()):
            if "INSERT INTO conversations" in sql:
                raise RuntimeError("simulated failure")
            return self._conn.execute(sql, params)

        def __getattr__(self, item):
            return getattr(self._conn, item)

    @contextmanager
    def flaky_connection():
        with real_connection() as conn:
            yield FailingInsert(conn)

    monkeypatch.setattr(db, "connection", flaky_connection)
    with pytest.raises(RuntimeError):
        engine.save_draft(result)

    # The cleanup path must have removed the half-written capsule.
    assert db.count_capsules() == 0
    assert db.scalar("SELECT COUNT(*) FROM conversations") == 0


def test_analysis_does_not_write_to_database(db) -> None:
    engine = CaptureEngine(db)
    engine.analyze_text(TRANSCRIPT)
    assert db.count_capsules() == 0
