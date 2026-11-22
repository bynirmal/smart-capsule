"""Capsule generation: structured context → portable document → database.

The document shape is the contract in ``docs/capsule_format.md``. Generation is
deterministic: the same conversation and settings always produce the same body
(only ``capsule_id``, ``created_at`` and version counters vary).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from config import APP_NAME, CAPSULE_FORMAT_VERSION, VERSION
from core.compression_engine import CompressionResult, compress
from core.context_engine import ProjectContext, extract
from core.parser_engine import ParseResult
from core.validator import validate_document
from database.db import Database
from database.models import iso

logger = logging.getLogger(__name__)


def _evidence_list(items) -> list[dict[str, Any]]:
    return [
        {
            "text": item.text,
            "certainty": item.certainty,
            "message_index": item.message_index,
            "kind": item.kind,
        }
        for item in items
    ]


def build_document(
    *,
    result: ParseResult,
    context: ProjectContext,
    compression: CompressionResult,
    capsule_id: str | None = None,
    created_at: datetime | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the portable capsule document."""
    stamp = (created_at or datetime.now(timezone.utc)).isoformat()

    return {
        "capsule_id": capsule_id or uuid.uuid4().hex,
        "format_version": CAPSULE_FORMAT_VERSION,
        "created_at": stamp,
        "app_version": VERSION,
        "application": APP_NAME,
        "source": {
            "platform": result.platform,
            "platform_confidence": result.platform_confidence,
            "platform_reason": result.platform_reason,
            "conversation_title": result.title,
            "conversation_date": None,
            "message_count": result.message_count,
            "source_kind": result.source_kind,
            "source_name": result.source_name,
            "conversation_id": conversation_id,
        },
        "project": {
            "name": context.name,
            "objective": context.objective,
            "description": context.description,
            "stage": context.stage,
            "stage_certainty": context.stage_certainty,
            "technologies": list(context.technologies),
            "constraints": [item.text for item in context.constraints],
        },
        "instructions": _evidence_list(context.instructions),
        "technical": {
            "languages": list(context.technical.languages),
            "frameworks": list(context.technical.frameworks),
            "libraries": list(context.technical.libraries),
            "architecture_decisions": _evidence_list(context.technical.decisions),
            "api_configurations": _evidence_list(context.technical.apis),
            "database_structure": _evidence_list(context.technical.databases),
        },
        "code": [
            {
                "language": block.language,
                "purpose": f"Code block from message {block.message_index + 1}",
                "content": block.content,
                "source_message": block.message_index,
            }
            for block in result.code_blocks
        ],
        "progress": {
            "completed": [
                {"task": item.task, "certainty": item.certainty, "message_index": item.message_index}
                for item in context.completed
            ],
            "pending": [
                {"task": item.task, "certainty": item.certainty, "message_index": item.message_index}
                for item in context.pending
            ],
            "current_task": context.current_task,
            "errors": [
                {
                    "error": item.error,
                    "solution": item.solution,
                    "resolved": item.resolved,
                    "certainty": item.certainty,
                    "message_index": item.message_index,
                }
                for item in context.errors
            ],
            "next_action": context.next_action,
            "next_action_certainty": context.next_action_certainty,
        },
        "decisions": _evidence_list(context.decisions),
        "summary": context.summary,
        "warnings": list(context.warnings) + list(result.warnings),
        "attachments": [],
        "original": (
            {
                "messages": [
                    {
                        "role": message.role,
                        "content": message.content,
                        "sequence": message.sequence,
                        "contains_code": message.contains_code,
                    }
                    for message in result.messages
                ]
            }
            if compression.original_text_included
            else None
        ),
        "compression": compression.as_metadata(),
    }


def apply_overrides(context: ProjectContext, overrides: Mapping[str, Any] | None) -> ProjectContext:
    """Apply user edits from the review screen before compression."""
    if not overrides:
        return context
    if value := str(overrides.get("name") or "").strip():
        context.name = value[:160]
    if value := str(overrides.get("objective") or "").strip():
        context.objective = value[:600]
    if value := str(overrides.get("next_action") or "").strip():
        context.next_action = value[:600]
        context.next_action_certainty = "stated"
    return context


def generate_document(
    result: ParseResult,
    *,
    mode: str = "balanced",
    overrides: Mapping[str, Any] | None = None,
    capsule_id: str | None = None,
    conversation_id: str | None = None,
) -> tuple[dict[str, Any], ProjectContext, CompressionResult]:
    """Extract, compress and assemble a document without writing anything."""
    context = apply_overrides(extract(result), overrides)
    compression = compress(context, result, mode)
    document = build_document(
        result=result,
        context=context,
        compression=compression,
        capsule_id=capsule_id,
        conversation_id=conversation_id,
    )
    return document, context, compression


def save_document(
    db: Database,
    document: Mapping[str, Any],
    *,
    capsule_id: str | None = None,
    note: str = "Generated capsule",
) -> str:
    """Persist (or update) a capsule and append a version snapshot."""
    validation = validate_document(document)
    validation.raise_if_invalid()

    payload = json.dumps(dict(document), ensure_ascii=False)
    project = document.get("project") or {}
    progress = document.get("progress") or {}
    compression = document.get("compression") or {}
    source = document.get("source") or {}
    title = str(project.get("name") or "Untitled capsule")[:300]
    summary = str(document.get("summary") or "")
    next_action = str(progress.get("next_action") or "")
    token_estimate = int(compression.get("capsule_tokens") or 0)
    mode = str(compression.get("mode") or "balanced")

    target_id = capsule_id
    if target_id and db.get_capsule(target_id):
        db.update_capsule(
            target_id,
            title=title,
            summary=summary,
            next_action=next_action,
            source_platform=str(source.get("platform") or "Other"),
            compression_mode=mode,
            token_estimate=token_estimate,
            payload_json=payload,
        )
    else:
        capsule = db.create_capsule(
            title=title,
            source_platform=str(source.get("platform") or "Other"),
            summary=summary,
            next_action=next_action,
            compression_mode=mode,
            token_estimate=token_estimate,
            payload_json=payload,
        )
        target_id = capsule.id

    version = int(db.scalar("SELECT COALESCE(MAX(version_number), 0) FROM capsule_versions WHERE capsule_id = ?", (target_id,)) or 0) + 1
    db.execute(
        "INSERT INTO capsule_versions(id, capsule_id, version_number, note, payload_json, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (
            uuid.uuid4().hex,
            target_id,
            version,
            note[:400],
            payload,
            iso(datetime.now(timezone.utc)),
        ),
    )
    logger.info("Saved capsule %s (version %s, mode %s)", target_id, version, mode)
    return target_id


def generate_capsule(
    db: Database,
    result: ParseResult,
    *,
    capsule_id: str | None = None,
    mode: str = "balanced",
    overrides: Mapping[str, Any] | None = None,
    conversation_id: str | None = None,
    note: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Full pipeline used by the desktop app and the web API."""
    document, _context, compression = generate_document(
        result,
        mode=mode,
        overrides=overrides,
        capsule_id=capsule_id,
        conversation_id=conversation_id,
    )
    label = note or f"Generated capsule · {compression.mode}"
    saved_id = save_document(db, document, capsule_id=capsule_id, note=label)
    return saved_id, document
