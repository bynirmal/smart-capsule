"""Capsule exporters: JSON, Markdown, plain text, ZIP and native .scapsule."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from exporters.capsule_exporter import export_scapsule
from exporters.json_exporter import export_json
from exporters.markdown_exporter import export_markdown
from exporters.text_exporter import export_text
from exporters.zip_exporter import export_zip

FORMATS: dict[str, str] = {
    "json": "JSON document",
    "markdown": "Markdown brief + prompt",
    "txt": "Plain text summary",
    "zip": "ZIP archive",
    "scapsule": "Native Smart Capsule package",
}

SUFFIXES: dict[str, str] = {
    "json": ".json",
    "markdown": ".md",
    "txt": ".txt",
    "zip": ".zip",
    "scapsule": ".scapsule",
}


def export_document(document: Mapping[str, Any], target: str | Path, fmt: str) -> Path:
    """Validate and write ``document`` in ``fmt``; returns the written path."""
    normalized = fmt.lower().strip()
    if normalized == "md":
        normalized = "markdown"
    writers = {
        "json": export_json,
        "markdown": export_markdown,
        "txt": export_text,
        "zip": export_zip,
        "scapsule": export_scapsule,
    }
    if normalized not in writers:
        raise ValueError(f"Unsupported export format: {fmt}")
    return writers[normalized](document, Path(target))


__all__ = [
    "FORMATS",
    "SUFFIXES",
    "export_document",
    "export_json",
    "export_markdown",
    "export_text",
    "export_zip",
    "export_scapsule",
]
