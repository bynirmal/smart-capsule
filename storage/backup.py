"""Database backup helpers built on SQLite's online backup API."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from config import backups_dir

logger = logging.getLogger(__name__)


def create_backup(database, label: str = "manual", keep: int = 10) -> Path:
    """Take a consistent snapshot of the live database.

    Uses ``sqlite3.Connection.backup`` so it is safe while the application is
    running (WAL mode included).  Older snapshots beyond ``keep`` are removed.
    """
    folder = backups_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = folder / f"smart_capsule-{label}-{stamp}.db"

    source_conn = sqlite3.connect(str(database.path), timeout=15)
    destination_conn = sqlite3.connect(str(target))
    try:
        with destination_conn:
            source_conn.backup(destination_conn)
    finally:
        destination_conn.close()
        source_conn.close()

    snapshots = sorted(folder.glob("smart_capsule-*.db"))
    for stale in snapshots[:-keep] if keep > 0 else []:
        try:
            stale.unlink()
        except OSError:  # pragma: no cover - best effort
            logger.warning("Could not remove old backup %s", stale)

    logger.info("Backup written to %s", target)
    return target


def list_backups() -> list[Path]:
    folder = backups_dir()
    if not folder.exists():
        return []
    return sorted(folder.glob("smart_capsule-*.db"))


def restore_backup(database, backup_path: Path) -> None:
    """Replace the live database with a snapshot (caller must restart the UI)."""
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    source_conn = sqlite3.connect(str(backup_path))
    destination_conn = sqlite3.connect(str(database.path))
    try:
        with destination_conn:
            source_conn.backup(destination_conn)
    finally:
        destination_conn.close()
        source_conn.close()
    logger.info("Database restored from %s", backup_path)
