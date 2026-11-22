"""JSON exporter: the capsule document exactly as stored."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from core.validator import validate_document


def export_json(document: Mapping[str, Any], target: Path) -> Path:
    validate_document(document).raise_if_invalid()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(dict(document), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target
