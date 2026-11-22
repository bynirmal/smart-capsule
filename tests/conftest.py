"""Shared pytest fixtures.

Every test runs against a throw-away data directory so the developer's real
capsules are never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def home(tmp_path, monkeypatch) -> Path:
    """Isolated SMART_CAPSULE_HOME for one test."""
    path = tmp_path / "home"
    path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SMART_CAPSULE_HOME", str(path))
    return path


@pytest.fixture()
def db(home: Path):
    """Migrated database living inside the isolated home."""
    from database.db import Database

    database = Database(home / "capsule.db")
    database.initialize()
    return database
