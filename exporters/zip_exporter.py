"""ZIP exporter with a verifiable manifest (shared by .scapsule)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from config import APP_NAME, CAPSULE_FORMAT_VERSION
from core.validator import validate_document


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_archive(document: Mapping[str, Any], target: Path) -> Path:
    """Write a ZIP containing ``capsule.json``, ``manifest.json`` and attachments."""
    validate_document(document).raise_if_invalid()
    target.parent.mkdir(parents=True, exist_ok=True)

    capsule_bytes = json.dumps(dict(document), ensure_ascii=False, indent=2).encode("utf-8")
    files: list[dict[str, Any]] = [
        {"name": "capsule.json", "sha256": _sha256(capsule_bytes), "size": len(capsule_bytes)}
    ]

    attachments = document.get("attachments") or []
    payloads: list[tuple[str, bytes]] = []
    for item in attachments:
        if not isinstance(item, Mapping):
            continue
        filename = Path(str(item.get("filename") or "")).name
        stored = item.get("stored_path")
        if not filename or not stored:
            continue
        source = Path(str(stored))
        if not source.exists() or not source.is_file():
            continue
        data = source.read_bytes()
        archive_name = f"attachments/{filename}"
        payloads.append((archive_name, data))
        files.append({"name": archive_name, "sha256": _sha256(data), "size": len(data)})

    manifest = {
        "application": APP_NAME,
        "format_version": CAPSULE_FORMAT_VERSION,
        "capsule_id": document.get("capsule_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("capsule.json", capsule_bytes)
        for name, data in payloads:
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

    return target


def export_zip(document: Mapping[str, Any], target: Path) -> Path:
    return build_archive(document, target)
