"""SQLite storage layer for Smart Capsule.

Design notes
------------
* Standard-library ``sqlite3`` only - no compiled extensions, so the app starts
  on locked-down machines where third-party ``.pyd`` files are blocked.
* A fresh connection is opened per unit of work and closed afterwards.  SQLite
  in WAL mode handles this cheaply and it makes the layer thread-safe: a
  background worker can never touch a connection owned by the UI thread.
* Schema changes live in ``database/migrations/*.sql`` and are applied in
  filename order, tracked by ``PRAGMA user_version``.  That keeps future
  upgrades (Phase 4 capsule versions, Phase 8 cloud sync) non-destructive.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from config import attachments_dir, database_path, migrations_dir
from database.models import (
    AppStats,
    Capsule,
    Project,
    iso,
    parse_datetime,
    utcnow,
)

logger = logging.getLogger(__name__)


def new_id() -> str:
    return uuid.uuid4().hex


class Database:
    """Thin, explicit repository around one SQLite file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Connections
    # ------------------------------------------------------------------ #
    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection; commits on success, rolls back on error."""
        conn = sqlite3.connect(str(self.path), timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #
    def schema_version(self) -> int:
        with self.connection() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def available_migrations(self) -> list[tuple[int, Path]]:
        """Return ``(version, path)`` pairs parsed from the migrations folder."""
        folder = migrations_dir()
        if not folder.exists():
            return []
        found: list[tuple[int, Path]] = []
        for file in sorted(folder.glob("*.sql")):
            prefix = file.name.split("_", 1)[0]
            if prefix.isdigit():
                found.append((int(prefix), file))
        return found

    def initialize(self) -> None:
        """Apply every migration newer than the current ``user_version``."""
        with self.connection() as conn:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])

        pending = [(v, p) for v, p in self.available_migrations() if v > current]
        if not pending and current == 0:
            # No migration files shipped (e.g. running from a packaged build):
            # fall back to the embedded schema so the app still starts.
            from database.schema import SCHEMA_SQL

            with self.connection() as conn:
                conn.executescript(SCHEMA_SQL)
                conn.execute("PRAGMA user_version=1")
            logger.info("Database created from embedded schema at %s", self.path)
            return

        for version, file in pending:
            sql = file.read_text(encoding="utf-8")
            with self.connection() as conn:
                conn.executescript(sql)
                conn.execute(f"PRAGMA user_version={version}")
            logger.info("Applied migration %s (%s)", file.name, version)

        with self.connection() as conn:
            conn.execute("PRAGMA user_version=%d" % (pending[-1][0] if pending else current))

    # ------------------------------------------------------------------ #
    # Generic helpers
    # ------------------------------------------------------------------ #
    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return list(conn.execute(sql, tuple(params)).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(sql, tuple(params)).fetchone()

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        with self.connection() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row else None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run a write statement and return ``lastrowid``."""
        with self.connection() as conn:
            cursor = conn.execute(sql, tuple(params))
            return int(cursor.lastrowid or 0)

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return str(row["value"]) if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, iso(utcnow())),
        )

    def get_bool_setting(self, key: str, default: bool = False) -> bool:
        raw = self.get_setting(key, "1" if default else "0")
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    # ------------------------------------------------------------------ #
    # Capsules
    # ------------------------------------------------------------------ #
    def create_capsule(
        self,
        *,
        title: str,
        source_platform: str = "Other",
        summary: str = "",
        next_action: str = "",
        compression_mode: str = "balanced",
        token_estimate: int = 0,
        format_version: int = 1,
        payload_json: str = "{}",
        project_id: str | None = None,
    ) -> Capsule:
        now = utcnow()
        capsule_id = new_id()
        self.execute(
            "INSERT INTO capsules(id, project_id, title, source_platform, format_version, summary, "
            "next_action, compression_mode, token_estimate, payload_json, is_archived, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,0,?,?)",
            (
                capsule_id,
                project_id,
                title.strip() or "Untitled capsule",
                source_platform or "Other",
                int(format_version),
                summary,
                next_action,
                compression_mode,
                int(token_estimate),
                payload_json,
                iso(now),
                iso(now),
            ),
        )
        row = self.query_one("SELECT * FROM capsules WHERE id = ?", (capsule_id,))
        assert row is not None
        return Capsule.from_row(row)

    def get_capsule(self, capsule_id: str) -> Capsule | None:
        row = self.query_one("SELECT * FROM capsules WHERE id = ?", (capsule_id,))
        return Capsule.from_row(row) if row else None

    def list_capsules(
        self,
        *,
        search: str = "",
        platform: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Capsule]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_archived:
            clauses.append("is_archived = 0")
        if platform and platform != "All":
            clauses.append("source_platform = ?")
            params.append(platform)
        if search.strip():
            like = f"%{search.strip()}%"
            clauses.append("(title LIKE ? OR summary LIKE ? OR next_action LIKE ?)")
            params.extend([like, like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.query(
            f"SELECT * FROM capsules {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [Capsule.from_row(row) for row in rows]

    def count_capsules(self, *, include_archived: bool = True) -> int:
        sql = "SELECT COUNT(*) FROM capsules"
        if not include_archived:
            sql += " WHERE is_archived = 0"
        return int(self.scalar(sql) or 0)

    def update_capsule(self, capsule_id: str, **fields: Any) -> None:
        allowed = {
            "title",
            "summary",
            "next_action",
            "source_platform",
            "compression_mode",
            "token_estimate",
            "payload_json",
            "project_id",
            "is_archived",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        self.execute(
            f"UPDATE capsules SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), iso(utcnow()), capsule_id),
        )

    def delete_capsule(self, capsule_id: str) -> None:
        """Delete a capsule and its dependent rows (attachments cascade)."""
        for row in self.query("SELECT stored_path FROM attachments WHERE capsule_id = ?", (capsule_id,)):
            path = Path(row["stored_path"]) if row["stored_path"] else None
            if path and path.exists():
                try:
                    path.unlink()
                except OSError:  # pragma: no cover - best effort cleanup
                    logger.warning("Could not delete attachment file %s", path)
        self.execute("DELETE FROM capsules WHERE id = ?", (capsule_id,))

    def recent_capsules(self, limit: int = 6) -> list[Capsule]:
        rows = self.query("SELECT * FROM capsules ORDER BY created_at DESC LIMIT ?", (limit,))
        return [Capsule.from_row(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Projects
    # ------------------------------------------------------------------ #
    def create_project(self, name: str, description: str = "") -> Project:
        now = utcnow()
        project_id = new_id()
        self.execute(
            "INSERT INTO projects(id, name, description, status, created_at, updated_at) VALUES(?,?,?,?,?,?)",
            (project_id, name.strip() or "Untitled project", description, "active", iso(now), iso(now)),
        )
        row = self.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))
        assert row is not None
        return Project.from_row(row)

    def list_projects(self) -> list[Project]:
        return [Project.from_row(row) for row in self.query("SELECT * FROM projects ORDER BY updated_at DESC")]

    def ensure_project(self, name: str) -> Project:
        """Return the project with this name, creating it when missing."""
        row = self.query_one("SELECT * FROM projects WHERE name = ?", (name.strip(),))
        if row is not None:
            return Project.from_row(row)
        return self.create_project(name)

    # ------------------------------------------------------------------ #
    # Dashboard aggregates
    # ------------------------------------------------------------------ #
    def stats(self) -> AppStats:
        total = int(self.scalar("SELECT COUNT(*) FROM capsules") or 0)
        archived = int(self.scalar("SELECT COUNT(*) FROM capsules WHERE is_archived = 1") or 0)
        projects = int(self.scalar("SELECT COUNT(*) FROM projects WHERE status = 'active'") or 0)
        latest = self.query_one("SELECT title, created_at FROM capsules ORDER BY created_at DESC LIMIT 1")
        platform_rows = self.query(
            "SELECT COALESCE(NULLIF(source_platform, ''), 'Other') AS platform, COUNT(*) AS n "
            "FROM capsules GROUP BY platform ORDER BY n DESC"
        )
        return AppStats(
            total_capsules=total,
            total_projects=projects,
            archived_capsules=archived,
            last_capsule_title=str(latest["title"]) if latest else None,
            last_capsule_at=parse_datetime(latest["created_at"]) if latest else None,
            platforms={str(row["platform"]): int(row["n"]) for row in platform_rows},
        )

    def storage_usage_bytes(self) -> int:
        total = 0
        for file in (self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm")):
            if file.exists():
                total += file.stat().st_size
        folder = attachments_dir()
        if folder.exists():
            for file in folder.rglob("*"):
                if file.is_file():
                    total += file.stat().st_size
        return total

    def last_capsule_age(self) -> str:
        """Human-readable age of the newest capsule ('' when there is none)."""
        stamp = self.scalar("SELECT created_at FROM capsules ORDER BY created_at DESC LIMIT 1")
        created = parse_datetime(stamp)
        if created is None:
            return ""
        delta = datetime.now(timezone.utc) - created
        seconds = max(int(delta.total_seconds()), 0)
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60} min ago"
        if seconds < 86400:
            return f"{seconds // 3600} h ago"
        return f"{seconds // 86400} d ago"


_database: Database | None = None


def get_database() -> Database:
    """Process-wide database singleton, migrated on first use."""
    global _database
    if _database is None:
        _database = Database()
        _database.initialize()
    return _database


def reset_database_singleton() -> None:
    """Testing helper: forget the cached database instance."""
    global _database
    _database = None
