"""Plain-text exporter: portable summary for any chat box."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.resume_engine import continuation_prompt
from core.validator import validate_document


def export_text(document: Mapping[str, Any], target: Path) -> Path:
    validate_document(document).raise_if_invalid()
    target.parent.mkdir(parents=True, exist_ok=True)
    body = continuation_prompt(document, "Other")
    target.write_text(body, encoding="utf-8", newline="\n")
    return target
