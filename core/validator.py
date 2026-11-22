"""Capsule document validation.

Both the exporter and the importer run this before touching the filesystem or the
database, so a malformed capsule can never be half-written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from config import CAPSULE_FORMAT_VERSION

REQUIRED_TOP_LEVEL = {
    "capsule_id": str,
    "format_version": int,
    "created_at": str,
    "source": dict,
    "project": dict,
    "summary": str,
    "compression": dict,
    "progress": dict,
}
LIST_FIELDS = ("instructions", "code", "decisions", "attachments")


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ValueError("; ".join(self.errors) or "Invalid capsule document.")


def validate_document(document: Any) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(document, Mapping):
        return ValidationResult(False, ["The capsule document must be a JSON object."], [])

    for key, expected in REQUIRED_TOP_LEVEL.items():
        if key not in document:
            errors.append(f"Missing required field: {key}")
            continue
        value = document[key]
        if not isinstance(value, expected):
            errors.append(f"Field '{key}' must be {expected.__name__}, got {type(value).__name__}")

    for key in LIST_FIELDS:
        if key in document and not isinstance(document[key], list):
            errors.append(f"Field '{key}' must be a list")

    version = document.get("format_version")
    if isinstance(version, int) and version > CAPSULE_FORMAT_VERSION:
        errors.append(
            f"Capsule format version {version} is newer than this build supports "
            f"({CAPSULE_FORMAT_VERSION})."
        )
    elif isinstance(version, int) and version < 1:
        errors.append("Capsule format version must be a positive integer.")

    if not str(document.get("capsule_id", "")).strip():
        errors.append("capsule_id must not be empty")

    project = document.get("project")
    if isinstance(project, Mapping) and not str(project.get("name", "")).strip():
        warnings.append("The capsule has no project name.")

    source = document.get("source")
    if isinstance(source, Mapping) and not str(source.get("platform", "")).strip():
        warnings.append("The capsule does not identify its source platform.")

    compression = document.get("compression")
    if isinstance(compression, Mapping):
        mode = compression.get("mode")
        if mode not in {"balanced", "high", "full"}:
            errors.append(f"Unknown compression mode: {mode!r}")
        method = compression.get("token_method")
        if not isinstance(method, str) or not method:
            warnings.append("Token estimates are not labelled with a method.")

    summary = document.get("summary")
    if isinstance(summary, str) and len(summary) > 40_000:
        errors.append("summary is unreasonably large (>40,000 characters).")

    return ValidationResult(not errors, errors, warnings)
