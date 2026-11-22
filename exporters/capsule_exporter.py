"""Native ``.scapsule`` exporter.

The package is a ZIP with a known layout: ``capsule.json``, ``manifest.json`` and
``attachments/``. The manifest carries the SHA-256 of every entry so an importer
can detect corruption or tampering before reading the document.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from exporters.zip_exporter import build_archive


def export_scapsule(document: Mapping[str, Any], target: Path) -> Path:
    if target.suffix.lower() != ".scapsule":
        target = target.with_suffix(".scapsule")
    return build_archive(document, target)
