"""Plain data objects mirroring the SQLite rows.

The application uses dataclasses instead of an ORM so that the storage layer
has zero compiled dependencies.  Each dataclass has a ``from_row`` classmethod
that maps a ``sqlite3.Row`` to the object, which keeps SQL knowledge inside the
database package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    """Parse the ISO-8601 timestamps written by the storage layer."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(slots=True)
class Project:
    id: str
    name: str
    description: str = ""
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Project":
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            status=row["status"] or "active",
            created_at=parse_datetime(row["created_at"]),
            updated_at=parse_datetime(row["updated_at"]),
        )


@dataclass(slots=True)
class Capsule:
    """One portable context capsule."""

    id: str
    title: str
    source_platform: str = "Other"
    project_id: str | None = None
    summary: str = ""
    next_action: str = ""
    compression_mode: str = "balanced"
    token_estimate: int = 0
    format_version: int = 1
    payload_json: str = "{}"
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Capsule":
        return cls(
            id=row["id"],
            title=row["title"],
            source_platform=row["source_platform"] or "Other",
            project_id=row["project_id"],
            summary=row["summary"] or "",
            next_action=row["next_action"] or "",
            compression_mode=row["compression_mode"] or "balanced",
            token_estimate=int(row["token_estimate"] or 0),
            format_version=int(row["format_version"] or 1),
            payload_json=row["payload_json"] or "{}",
            is_archived=bool(row["is_archived"]),
            created_at=parse_datetime(row["created_at"]),
            updated_at=parse_datetime(row["updated_at"]),
        )

    def payload(self) -> dict[str, Any]:
        """Decoded capsule document, or an empty dict when unreadable."""
        try:
            data = json.loads(self.payload_json)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}


@dataclass(slots=True)
class Conversation:
    id: str
    capsule_id: str
    platform: str = "Other"
    title: str = ""
    message_count: int = 0
    raw_text: str = ""
    started_at: datetime | None = None
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Conversation":
        return cls(
            id=row["id"],
            capsule_id=row["capsule_id"],
            platform=row["platform"] or "Other",
            title=row["title"] or "",
            message_count=int(row["message_count"] or 0),
            raw_text=row["raw_text"] or "",
            started_at=parse_datetime(row["started_at"]),
            created_at=parse_datetime(row["created_at"]),
        )


@dataclass(slots=True)
class Message:
    id: str
    conversation_id: str
    role: str = "user"
    content: str = ""
    sequence: int = 0
    contains_code: bool = False
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Message":
        return cls(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"] or "user",
            content=row["content"] or "",
            sequence=int(row["sequence"] or 0),
            contains_code=bool(row["contains_code"]),
            created_at=parse_datetime(row["created_at"]),
        )


@dataclass(slots=True)
class Attachment:
    id: str
    capsule_id: str
    filename: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    sha256: str = ""
    stored_path: str = ""
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Attachment":
        return cls(
            id=row["id"],
            capsule_id=row["capsule_id"],
            filename=row["filename"],
            mime_type=row["mime_type"] or "application/octet-stream",
            size_bytes=int(row["size_bytes"] or 0),
            sha256=row["sha256"] or "",
            stored_path=row["stored_path"] or "",
            created_at=parse_datetime(row["created_at"]),
        )


@dataclass(slots=True)
class CapsuleVersion:
    id: str
    capsule_id: str
    version_number: int
    note: str = ""
    payload_json: str = "{}"
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CapsuleVersion":
        return cls(
            id=row["id"],
            capsule_id=row["capsule_id"],
            version_number=int(row["version_number"] or 1),
            note=row["note"] or "",
            payload_json=row["payload_json"] or "{}",
            created_at=parse_datetime(row["created_at"]),
        )


@dataclass(slots=True)
class AIModel:
    id: str
    name: str
    backend: str = "transformers"
    size_mb: int = 0
    path: str = ""
    is_loaded: bool = False
    is_default: bool = False
    last_used_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "AIModel":
        return cls(
            id=row["id"],
            name=row["name"],
            backend=row["backend"] or "transformers",
            size_mb=int(row["size_mb"] or 0),
            path=row["path"] or "",
            is_loaded=bool(row["is_loaded"]),
            is_default=bool(row["is_default"]),
            last_used_at=parse_datetime(row["last_used_at"]),
        )


@dataclass(slots=True)
class ProcessingRun:
    id: str
    stage: str
    engine: str = "rule-based"
    model_name: str = ""
    device: str = "cpu"
    status: str = "ok"
    detail: str = ""
    capsule_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ProcessingRun":
        return cls(
            id=row["id"],
            stage=row["stage"] or "extract",
            engine=row["engine"] or "rule-based",
            model_name=row["model_name"] or "",
            device=row["device"] or "cpu",
            status=row["status"] or "ok",
            detail=row["detail"] or "",
            capsule_id=row["capsule_id"],
            started_at=parse_datetime(row["started_at"]),
            finished_at=parse_datetime(row["finished_at"]),
        )


@dataclass(slots=True)
class AppStats:
    """Aggregated counters for the dashboard."""

    total_capsules: int = 0
    total_projects: int = 0
    archived_capsules: int = 0
    last_capsule_title: str | None = None
    last_capsule_at: datetime | None = None
    platforms: dict[str, int] = field(default_factory=dict)
