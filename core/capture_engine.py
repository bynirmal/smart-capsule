"""Capture orchestration: analyse input, then persist a draft capsule.

Phase 2 stores the parsed conversation verbatim (never rewritten) together with a
portable payload marked ``"draft": true``.  Phase 3 fills the structured context
in place; Phase 4 turns the payload into an exportable capsule document.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import CAPSULE_FORMAT_VERSION
from core.parser_engine import (
    CodeBlock,
    ParseError,
    ParsedMessage,
    ParseResult,
    extract_code_blocks,
    parse_file,
    parse_text,
)
from database.db import Database, new_id
from database.models import Capsule

logger = logging.getLogger(__name__)


class CaptureEngine:
    """UI-independent capture pipeline."""

    def __init__(self, database: Database) -> None:
        self.db = database

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #
    def analyze_text(self, text: str, *, platform_hint: str | None = None) -> ParseResult:
        logger.info("Analysing pasted capture (%s characters)", len(text))
        return parse_text(text, platform_hint=platform_hint)

    def analyze_file(self, path: str | Path, *, platform_hint: str | None = None) -> ParseResult:
        logger.info("Analysing capture file %s", path)
        return parse_file(path, platform_hint=platform_hint)

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save_draft(self, result: ParseResult) -> str:
        """Persist the capture and return the new capsule id.

        Conversation, messages and capsule are written in a single transaction so
        a crash can never leave a capsule without its source conversation.
        """
        if not result.messages:
            raise ParseError("The capture has no messages to save.")

        conversation_id = new_id()
        captured_at = datetime.now(timezone.utc)
        compression_mode = self.db.get_setting("default_compression", "balanced")

        payload = {
            "format_version": CAPSULE_FORMAT_VERSION,
            "draft": True,
            "capture": {
                "captured_at": captured_at.isoformat(),
                "source_kind": result.source_kind,
                "source_name": result.source_name,
                "platform": result.platform,
                "platform_confidence": result.platform_confidence,
                "platform_reason": result.platform_reason,
                "title": result.title,
                "message_count": result.message_count,
                "code_block_count": len(result.code_blocks),
                "character_count": result.character_count,
                "token_estimate": result.token_estimate,
                "token_method": "characters/4 heuristic",
                "warnings": list(result.warnings),
                "conversation_id": conversation_id,
            },
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                    "sequence": message.sequence,
                    "contains_code": message.contains_code,
                }
                for message in result.messages
            ],
            "code": [
                {"language": block.language, "content": block.content, "message_index": block.message_index}
                for block in result.code_blocks
            ],
        }

        capsule = self.db.create_capsule(
            title=result.title or "Untitled capture",
            source_platform=result.platform,
            summary="",
            next_action="",
            compression_mode=compression_mode,
            token_estimate=result.token_estimate,
            format_version=CAPSULE_FORMAT_VERSION,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )

        now = captured_at.isoformat()
        try:
            with self.db.connection() as conn:
                conn.execute(
                    "INSERT INTO conversations(id, capsule_id, platform, title, started_at, message_count, "
                    "raw_text, created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        conversation_id,
                        capsule.id,
                        result.platform,
                        result.title,
                        None,
                        result.message_count,
                        result.text,
                        now,
                    ),
                )
                conn.executemany(
                    "INSERT INTO messages(id, conversation_id, role, content, sequence, contains_code, created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    [
                        (
                            new_id(),
                            conversation_id,
                            message.role,
                            message.content,
                            message.sequence,
                            1 if message.contains_code else 0,
                            now,
                        )
                        for message in result.messages
                    ],
                )
                conn.execute(
                    "INSERT INTO processing_history(id, capsule_id, stage, engine, model_name, device, status, "
                    "detail, started_at, finished_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        new_id(),
                        capsule.id,
                        "capture",
                        "parser",
                        "",
                        "cpu",
                        "ok",
                        f"{result.message_count} messages, {len(result.code_blocks)} code blocks, "
                        f"platform {result.platform} ({result.platform_confidence})",
                        now,
                        now,
                    ),
                )
        except Exception:
            # The capsule must not survive without its conversation.
            self.db.delete_capsule(capsule.id)
            raise

        logger.info("Saved capture as capsule %s (%s messages)", capsule.id, result.message_count)
        return capsule.id

    # ------------------------------------------------------------------ #
    # Reconstruction (desktop review / regeneration)
    # ------------------------------------------------------------------ #
    def rebuild_result(self, capsule: Capsule) -> ParseResult:
        """Recreate a :class:`ParseResult` from a stored capture draft.

        Used when a draft capsule is turned into a full capsule later, so the
        parser does not have to run again over the original raw text.
        """
        payload = capsule.payload()
        capture = payload.get("capture") or {}
        messages: list[ParsedMessage] = []
        for item in payload.get("messages") or []:
            if not isinstance(item, dict):
                continue
            messages.append(
                ParsedMessage(
                    role=str(item.get("role") or "user"),
                    content=str(item.get("content") or ""),
                    sequence=int(item.get("sequence") or len(messages)),
                    contains_code=bool(item.get("contains_code")),
                )
            )
        if not messages:
            raise ParseError("This draft capsule has no stored messages to process.")

        blocks, messages = extract_code_blocks(messages)
        text = "\n\n".join(f"{message.role.title()}: {message.content}" for message in messages)
        return ParseResult(
            text=text,
            messages=messages,
            code_blocks=blocks,
            platform=str(capture.get("platform") or capsule.source_platform or "Other"),
            platform_confidence=str(capture.get("platform_confidence") or "low"),
            platform_reason=str(capture.get("platform_reason") or ""),
            title=str(capture.get("title") or capsule.title),
            warnings=list(capture.get("warnings") or []),
            source_kind=str(capture.get("source_kind") or "paste"),
            source_name=str(capture.get("source_name") or ""),
        )

    def conversation_id_for(self, capsule: Capsule) -> str | None:
        capture = capsule.payload().get("capture") or {}
        value = capture.get("conversation_id")
        return str(value) if value else None
