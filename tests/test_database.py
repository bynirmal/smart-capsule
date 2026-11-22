"""Storage layer tests: schema, CRUD, search, statistics and backups."""

from __future__ import annotations

from database.models import Capsule, Project
from database.schema import SCHEMA_SQL
from storage.backup import create_backup, list_backups


def test_schema_is_created_and_versioned(db) -> None:
    assert db.schema_version() >= 1
    tables = {
        row["name"]
        for row in db.query("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for expected in (
        "capsules",
        "projects",
        "conversations",
        "messages",
        "attachments",
        "capsule_versions",
        "ai_models",
        "processing_history",
        "settings",
    ):
        assert expected in tables

    # The embedded fallback schema must stay structurally valid on its own.
    assert "CREATE TABLE IF NOT EXISTS capsules" in SCHEMA_SQL


def test_settings_roundtrip(db) -> None:
    db.set_setting("default_compression", "high")
    assert db.get_setting("default_compression") == "high"

    # Second write updates instead of duplicating.
    db.set_setting("default_compression", "full")
    assert db.get_setting("default_compression") == "full"
    assert db.scalar("SELECT COUNT(*) FROM settings WHERE key = 'default_compression'") == 1

    assert db.get_bool_setting("missing_flag", True) is True
    db.set_setting("missing_flag", "0")
    assert db.get_bool_setting("missing_flag", True) is False


def test_capsule_lifecycle(db) -> None:
    capsule = db.create_capsule(
        title="Refactor auth module",
        source_platform="Claude",
        summary="Move JWT issuing into a service layer.",
        next_action="Add refresh-token tests.",
        compression_mode="balanced",
        payload_json='{"format_version": 1}',
    )
    assert isinstance(capsule, Capsule)
    assert capsule.id and capsule.created_at is not None

    fetched = db.get_capsule(capsule.id)
    assert fetched is not None and fetched.title == "Refactor auth module"
    assert fetched.payload()["format_version"] == 1

    db.create_capsule(title="Landing page copy", source_platform="ChatGPT")
    assert db.count_capsules() == 2
    assert len(db.list_capsules(search="auth")) == 1
    assert len(db.list_capsules(platform="ChatGPT")) == 1
    assert len(db.list_capsules(platform="All")) == 2

    db.update_capsule(capsule.id, title="Refactor auth service", is_archived=True)
    assert db.get_capsule(capsule.id).title == "Refactor auth service"
    assert db.count_capsules(include_archived=False) == 1

    db.delete_capsule(capsule.id)
    assert db.get_capsule(capsule.id) is None
    assert db.count_capsules() == 1


def test_project_creation_and_reuse(db) -> None:
    first = db.create_project("Smart Capsule")
    assert isinstance(first, Project)
    assert db.ensure_project("Smart Capsule").id == first.id
    assert db.ensure_project("Other").id != first.id
    assert db.stats().total_projects == 2


def test_stats_reflect_capsules(db) -> None:
    assert db.stats().total_capsules == 0
    db.create_capsule(title="First", source_platform="ChatGPT")
    db.create_capsule(title="Second", source_platform="ChatGPT")
    db.create_capsule(title="Third", source_platform="Gemini")

    stats = db.stats()
    assert stats.total_capsules == 3
    assert stats.platforms == {"ChatGPT": 2, "Gemini": 1}
    assert stats.last_capsule_title == "Third"
    assert stats.last_capsule_at is not None


def test_deleting_capsule_cascades(db) -> None:
    capsule = db.create_capsule(title="With conversation")
    db.execute(
        "INSERT INTO conversations(id, capsule_id, platform, title, message_count, raw_text, created_at) "
        "VALUES('conv1', ?, 'ChatGPT', 'chat', 1, 'hi', '2026-01-01T00:00:00+00:00')",
        (capsule.id,),
    )
    db.execute(
        "INSERT INTO messages(id, conversation_id, role, content, sequence, contains_code, created_at) "
        "VALUES('msg1', 'conv1', 'user', 'hi', 0, 0, '2026-01-01T00:00:00+00:00')"
    )
    db.delete_capsule(capsule.id)
    assert db.scalar("SELECT COUNT(*) FROM conversations") == 0
    assert db.scalar("SELECT COUNT(*) FROM messages") == 0


def test_backup_writes_snapshot(db) -> None:
    db.create_capsule(title="Backed up capsule")
    path = create_backup(db)
    assert path.exists()
    assert path in list_backups()

    # The snapshot must be a readable database with the same row.
    import sqlite3

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM capsules").fetchone()[0] == 1


def test_storage_usage_positive_after_write(db) -> None:
    db.create_capsule(title="Something")
    assert db.storage_usage_bytes() > 0
