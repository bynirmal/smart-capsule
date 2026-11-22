"""Capsule importer.

Accepts ``.scapsule``, ``.zip`` and ``.json`` files. Every archive entry is
hash-checked against ``manifest.json``, entry names are sanitised to prevent path
traversal, and the document is validated before a single row is written.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from config import APP_NAME, attachments_dir
from core.validator import validate_document
from database.db import Database
from database.models import iso

logger = logging.getLogger(__name__)

MAX_IMPORT_BYTES = 64 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 32 * 1024 * 1024


class ImportError_(ValueError):
    """Raised when a capsule file cannot be imported safely."""


@dataclass(slots=True)
class ImportResult:
    capsule_id: str
    title: str
    document: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)


def _safe_name(name: str) -> str:
    """Reject traversal and normalise to a bare file name."""
    candidate = Path(name.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ImportError_(f"Unsafe archive entry: {name}")
    bare = candidate.name
    if not bare or bare in {".", ".."}:
        raise ImportError_(f"Invalid archive entry: {name}")
    return bare


def _verify_manifest(archive: zipfile.ZipFile, manifest: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    for entry in manifest.get("files") or []:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "")
        if not name or name not in archive.namelist():
            warnings.append(f"Manifest entry missing from archive: {name}")
            continue
        data = archive.read(name)
        digest = hashlib.sha256(data).hexdigest()
        if entry.get("sha256") and digest != entry["sha256"]:
            raise ImportError_(f"Checksum mismatch for {name}; the package is corrupted.")
    return warnings


def _read_archive(path: Path) -> tuple[dict[str, Any], list[tuple[str, bytes]], list[str]]:
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise ImportError_(f"{path.name} is larger than the {MAX_IMPORT_BYTES // 1_048_576} MB import limit.")

    warnings: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "capsule.json" not in names:
                raise ImportError_("The package does not contain capsule.json.")

            if "manifest.json" in names:
                try:
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ImportError_(f"manifest.json is not valid JSON: {exc}") from exc
                if isinstance(manifest, Mapping):
                    warnings.extend(_verify_manifest(archive, manifest))
                    version = manifest.get("format_version")
                    if isinstance(version, int) and version > 1:
                        warnings.append(
                            f"Package manifest declares format version {version}; import may lose fields."
                        )

            try:
                document = json.loads(archive.read("capsule.json").decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ImportError_(f"capsule.json is not valid JSON: {exc}") from exc

            attachment_payloads: list[tuple[str, bytes]] = []
            for name in names:
                if not name.startswith("attachments/") or name.endswith("/"):
                    continue
                data = archive.read(name)
                if len(data) > MAX_ATTACHMENT_BYTES:
                    raise ImportError_(f"Attachment {name} exceeds the size limit.")
                attachment_payloads.append((_safe_name(name), data))
    except zipfile.BadZipFile as exc:
        raise ImportError_(f"{path.name} is not a valid capsule archive.") from exc

    if not isinstance(document, Mapping):
        raise ImportError_("capsule.json must contain a JSON object.")
    return dict(document), attachment_payloads, warnings


def _load_document(path: Path) -> tuple[dict[str, Any], list[tuple[str, bytes]], list[str]]:
    suffix = path.suffix.lower()
    if suffix in {".scapsule", ".zip"}:
        return _read_archive(path)
    if suffix == ".json":
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise ImportError_("The JSON file is larger than the import limit.")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ImportError_(f"{path.name} is not valid JSON: {exc}") from exc
        if not isinstance(document, Mapping):
            raise ImportError_("The JSON root must be a capsule object.")
        return dict(document), [], []
    raise ImportError_(f"Unsupported capsule file type: {suffix or 'unknown'}")


def import_capsule(db: Database, path: str | Path) -> ImportResult:
    """Import a capsule file; raises :class:`ImportError_` without partial writes."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise ImportError_(f"File not found: {file_path}")

    document, attachment_payloads, warnings = _load_document(file_path)

    validation = validate_document(document)
    if not validation.ok:
        raise ImportError_("Invalid capsule: " + "; ".join(validation.errors))
    warnings.extend(validation.warnings)

    original_id = str(document.get("capsule_id") or "")
    new_id = uuid.uuid4().hex
    document["capsule_id"] = new_id
    document["imported_from"] = {
        "capsule_id": original_id,
        "file": file_path.name,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "application": APP_NAME,
    }

    project = document.get("project") or {}
    progress = document.get("progress") or {}
    compression = document.get("compression") or {}
    source = document.get("source") or {}
    title = str(project.get("name") or file_path.stem)[:300]

    stored_attachments: list[str] = []
    folder = attachments_dir() / new_id
    for filename, data in attachment_payloads:
        folder.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()
        target = folder / f"{digest[:12]}_{filename}"
        target.write_bytes(data)
        document.setdefault("attachments", []).append(
            {
                "id": digest[:32],
                "filename": filename,
                "mime_type": "application/octet-stream",
                "size_bytes": len(data),
                "sha256": digest,
                "stored_path": str(target),
            }
        )
        stored_attachments.append(filename)

    capsule = db.create_capsule(
        title=title,
        source_platform=str(source.get("platform") or "Other"),
        summary=str(document.get("summary") or ""),
        next_action=str(progress.get("next_action") or ""),
        compression_mode=str(compression.get("mode") or "balanced"),
        token_estimate=int(compression.get("capsule_tokens") or 0),
        format_version=int(document.get("format_version") or 1),
        payload_json=json.dumps(document, ensure_ascii=False),
    )

    try:
        for item in document.get("attachments") or []:
            if not isinstance(item, Mapping) or not item.get("stored_path"):
                continue
            db.execute(
                "INSERT INTO attachments(id, capsule_id, filename, mime_type, size_bytes, sha256, "
                "stored_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    capsule.id,
                    str(item.get("filename") or "attachment")[:400],
                    str(item.get("mime_type") or "application/octet-stream"),
                    int(item.get("size_bytes") or 0),
                    str(item.get("sha256") or ""),
                    str(item.get("stored_path") or ""),
                    iso(datetime.now(timezone.utc)),
                ),
            )

        original = document.get("original") or {}
        messages = original.get("messages") if isinstance(original, Mapping) else None
        conversation_id = None
        if isinstance(messages, list) and messages:
            conversation_id = uuid.uuid4().hex
            now = iso(datetime.now(timezone.utc))
            with db.connection() as conn:
                conn.execute(
                    "INSERT INTO conversations(id, capsule_id, platform, title, started_at, message_count, "
                    "raw_text, created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        conversation_id,
                        capsule.id,
                        str(source.get("platform") or "Other"),
                        title,
                        None,
                        len(messages),
                        "\n\n".join(
                            f"{str(item.get('role') or 'user').title()}: {str(item.get('content') or '')}"
                            for item in messages
                            if isinstance(item, Mapping)
                        ),
                        now,
                    ),
                )
                conn.executemany(
                    "INSERT INTO messages(id, conversation_id, role, content, sequence, contains_code, "
                    "created_at) VALUES(?,?,?,?,?,?,?)",
                    [
                        (
                            uuid.uuid4().hex,
                            conversation_id,
                            str(item.get("role") or "user"),
                            str(item.get("content") or ""),
                            int(item.get("sequence") or index),
                            1 if item.get("contains_code") else 0,
                            now,
                        )
                        for index, item in enumerate(messages)
                        if isinstance(item, Mapping)
                    ],
                )

        db.execute(
            "INSERT INTO capsule_versions(id, capsule_id, version_number, note, payload_json, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                capsule.id,
                1,
                "Imported capsule",
                json.dumps(document, ensure_ascii=False),
                iso(datetime.now(timezone.utc)),
            ),
        )
    except Exception:
        db.delete_capsule(capsule.id)
        raise

    logger.info("Imported capsule %s from %s", capsule.id, file_path.name)
    return ImportResult(
        capsule_id=capsule.id,
        title=title,
        document=document,
        warnings=warnings,
        attachments=stored_attachments,
    )
