"""Capsule core tests: generation, validation, every export format, round-trip import."""

from __future__ import annotations

import json
import zipfile

import pytest

from core.capsule_generator import generate_capsule, generate_document, save_document
from core.capsule_importer import ImportError_, import_capsule
from core.resume_engine import DESTINATIONS, continuation_prompt, context_brief
from core.validator import validate_document
from exporters import export_document

TRANSCRIPT = """User: Build a FastAPI invoicing service. You must use PostgreSQL.

Assistant: Done: project scaffold and database schema.

User: We decided to use SQLAlchemy for the ORM.

Assistant: Here is the model.

```python
class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
```

User: The list endpoint throws a 500 error about a missing column.

Assistant: The fix is to run the migration that adds total_amount.

User: Next step is adding pagination and tests.
"""


def _document(mode: str = "balanced"):
    from core.parser_engine import parse_text

    result = parse_text(TRANSCRIPT, platform_hint="Claude")
    document, context, compression = generate_document(result, mode=mode)
    return document, context, compression, result


def test_document_shape_is_valid() -> None:
    document, context, compression, _ = _document()
    result = validate_document(document)
    assert result.ok, result.errors
    assert document["format_version"] == 1
    assert document["capsule_id"]
    assert document["source"]["platform"] == "Claude"
    assert document["project"]["name"]
    assert document["project"]["objective"]
    assert document["compression"]["mode"] == "balanced"
    assert document["progress"]["next_action"]
    assert document["code"][0]["language"] == "python"
    assert context.stage_certainty == "inferred"


def test_full_mode_includes_original_messages() -> None:
    document, _, compression, _ = _document("full")
    assert compression.original_text_included
    assert document["original"]["messages"]
    assert len(document["original"]["messages"]) >= 6


def test_balanced_mode_omits_original() -> None:
    document, _, _, _ = _document("balanced")
    assert document["original"] is None


def test_every_export_format(tmp_path) -> None:
    document, _, _, _ = _document("full")
    for fmt, suffix in (
        ("json", ".json"),
        ("markdown", ".md"),
        ("txt", ".txt"),
        ("zip", ".zip"),
        ("scapsule", ".scapsule"),
    ):
        target = export_document(document, tmp_path / f"capsule{suffix}", fmt)
        assert target.exists() and target.stat().st_size > 0

    json_path = tmp_path / "capsule.json"
    assert json.loads(json_path.read_text(encoding="utf-8"))["capsule_id"] == document["capsule_id"]

    markdown = (tmp_path / "capsule.md").read_text(encoding="utf-8")
    assert "Continuation prompt" in markdown

    with zipfile.ZipFile(tmp_path / "capsule.scapsule") as archive:
        names = set(archive.namelist())
        assert {"capsule.json", "manifest.json"} <= names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["files"]


def test_scapsule_roundtrip_import(db, tmp_path) -> None:
    document, _, _, _ = _document("full")
    path = export_document(document, tmp_path / "handoff", "scapsule")

    result = import_capsule(db, path)
    assert result.capsule_id != document["capsule_id"]  # a fresh local id
    assert result.title == document["project"]["name"]

    stored = db.get_capsule(result.capsule_id)
    assert stored is not None
    payload = stored.payload()
    assert payload["imported_from"]["capsule_id"] == document["capsule_id"]
    assert payload["project"]["name"] == document["project"]["name"]
    assert payload["progress"]["next_action"] == document["progress"]["next_action"]

    conversations = db.query("SELECT * FROM conversations WHERE capsule_id = ?", (result.capsule_id,))
    assert len(conversations) == 1
    messages = db.query(
        "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?", (conversations[0]["id"],)
    )
    assert messages[0]["n"] == len(document["original"]["messages"])

    versions = db.query("SELECT * FROM capsule_versions WHERE capsule_id = ?", (result.capsule_id,))
    assert len(versions) == 1


def test_import_json_document(db, tmp_path) -> None:
    document, _, _, _ = _document()
    path = export_document(document, tmp_path / "capsule.json", "json")
    result = import_capsule(db, path)
    assert db.get_capsule(result.capsule_id) is not None


def test_corrupted_archive_is_rejected(db, tmp_path) -> None:
    document, _, _, _ = _document()
    good = export_document(document, tmp_path / "good.scapsule", "scapsule")

    # Rewrite capsule.json inside the archive without updating the manifest.
    bad = tmp_path / "bad.scapsule"
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(bad, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "capsule.json":
                payload = json.loads(data.decode("utf-8"))
                payload["summary"] = "tampered"
                data = json.dumps(payload).encode("utf-8")
            target.writestr(item.filename, data)

    with pytest.raises(ImportError_):
        import_capsule(db, bad)
    assert db.count_capsules() == 0


def test_path_traversal_attachment_is_rejected(db, tmp_path) -> None:
    document, _, _, _ = _document()
    path = tmp_path / "evil.scapsule"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("capsule.json", json.dumps(document))
        archive.writestr("attachments/../../evil.txt", b"nope")
        archive.writestr("manifest.json", json.dumps({"files": []}))

    with pytest.raises(ImportError_):
        import_capsule(db, path)


def test_invalid_format_version_rejected() -> None:
    document, _, _, _ = _document()
    document["format_version"] = 99
    result = validate_document(document)
    assert not result.ok
    assert any("newer" in error for error in result.errors)


def test_regenerating_creates_new_version(db) -> None:
    from core.parser_engine import parse_text

    engine_result = parse_text(TRANSCRIPT, platform_hint="Claude")
    draft_id, _ = generate_capsule(db, engine_result, mode="balanced")
    second_id, document = generate_capsule(db, engine_result, capsule_id=draft_id, mode="high")

    assert second_id == draft_id
    versions = db.query(
        "SELECT version_number FROM capsule_versions WHERE capsule_id = ? ORDER BY version_number",
        (draft_id,),
    )
    assert [row["version_number"] for row in versions] == [1, 2]
    assert db.get_capsule(draft_id).payload()["compression"]["mode"] == "high"


def test_review_overrides_are_applied(db) -> None:
    from core.parser_engine import parse_text

    result = parse_text(TRANSCRIPT)
    _, document = generate_capsule(
        db,
        result,
        overrides={"name": "Invoice API", "next_action": "Ship pagination", "objective": "Custom objective"},
    )
    assert document["project"]["name"] == "Invoice API"
    assert document["progress"]["next_action"] == "Ship pagination"
    assert document["project"]["objective"] == "Custom objective"


def test_resume_prompt_is_destination_specific() -> None:
    document, _, _, _ = _document()
    brief = context_brief(document)
    assert "PROJECT HANDOFF" in brief
    assert document["progress"]["next_action"] in brief

    for destination in DESTINATIONS:
        prompt = continuation_prompt(document, destination)
        assert "hidden model memory" in prompt
        assert document["project"]["name"] in prompt
    assert "repository" in continuation_prompt(document, "Cursor").lower()


def test_invalid_document_is_not_written(db, tmp_path) -> None:
    with pytest.raises(ValueError):
        save_document(db, {"capsule_id": "x"})
    assert db.count_capsules() == 0
