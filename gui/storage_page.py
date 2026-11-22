"""Storage management: inspection, backup and folder access."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import customtkinter as ctk

from config import attachments_dir, backups_dir, data_dir, database_path
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Card, KeyValueRow, format_bytes, ghost_button, primary_button
from gui.workers import run_in_background
from storage.backup import create_backup

logger = logging.getLogger(__name__)


class StoragePage(BasePage):
    page_key = "storage"
    title = "Storage Management"
    subtitle = "Local-first data: database, attachments and backups"

    def build(self) -> None:
        ghost_button(self.header_actions, "↻  Refresh", self.refresh).pack(side="right", padx=(0, 8))
        primary_button(self.header_actions, "Backup now", self._backup).pack(side="right")

        overview = Card(self.body, "Local storage", "Everything is stored on this computer", padding=18, accent=COLORS["accent"])
        overview.pack(fill="x", pady=(0, 12), padx=6)

        self.row_data = KeyValueRow(overview.body, "Data directory")
        self.row_data.pack(fill="x", pady=3)
        self.row_db = KeyValueRow(overview.body, "Database file")
        self.row_db.pack(fill="x", pady=3)
        self.row_db_size = KeyValueRow(overview.body, "Database size")
        self.row_db_size.pack(fill="x", pady=3)
        self.row_attach = KeyValueRow(overview.body, "Attachments")
        self.row_attach.pack(fill="x", pady=3)
        self.row_backups = KeyValueRow(overview.body, "Backups")
        self.row_backups.pack(fill="x", pady=3)
        self.row_total = KeyValueRow(overview.body, "Total footprint")
        self.row_total.pack(fill="x", pady=3)

        folders = Card(self.body, "Folder access", "Open locations in your file manager", padding=18)
        folders.pack(fill="x", pady=(0, 12), padx=6)

        buttons = ctk.CTkFrame(folders.body, fg_color="transparent")
        buttons.pack(fill="x")
        ghost_button(buttons, "Open data folder", lambda: self._open_folder(data_dir())).pack(side="left")
        ghost_button(buttons, "Open attachments", lambda: self._open_folder(attachments_dir())).pack(side="left", padx=8)
        ghost_button(buttons, "Open backups", lambda: self._open_folder(backups_dir())).pack(side="left")

        self.activity = ctk.CTkLabel(
            self.body,
            text="",
            font=font(11),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self.activity.pack(fill="x", padx=12, pady=(0, 6))

        self.refresh()

    def on_show(self) -> None:
        self.refresh()

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        run_in_background(self, self._collect, self._apply, self._failed)

    def _collect(self) -> dict[str, object]:
        db_file = database_path()
        attach = attachments_dir()
        attach_bytes = sum(f.stat().st_size for f in attach.rglob("*") if f.is_file()) if attach.exists() else 0
        backup_files = sorted(backups_dir().glob("*.db")) if backups_dir().exists() else []
        return {
            "data_dir": str(data_dir()),
            "db_path": str(db_file),
            "db_bytes": db_file.stat().st_size if db_file.exists() else 0,
            "attach_bytes": attach_bytes,
            "attach_count": sum(1 for f in attach.rglob("*") if f.is_file()) if attach.exists() else 0,
            "backups": backup_files,
            "total": self.db.storage_usage_bytes(),
        }

    def _apply(self, data: dict[str, object]) -> None:
        self.row_data.set(str(data["data_dir"]))
        self.row_db.set(Path(str(data["db_path"])).name)
        self.row_db_size.set(format_bytes(int(data["db_bytes"])))
        self.row_attach.set(
            f"{format_bytes(int(data['attach_bytes']))} · {data['attach_count']} file(s)"
        )
        backups = data["backups"]
        self.row_backups.set(f"{len(backups)} snapshot(s)" if backups else "none yet")
        self.row_total.set(format_bytes(int(data["total"])))

        if backups:
            latest = Path(str(backups[-1]))
            self.activity.configure(
                text=f"Most recent backup: {latest.name} ({format_bytes(latest.stat().st_size)})"
            )

    def _failed(self, error: Exception) -> None:
        logger.exception("Storage inspection failed")
        self.app.set_status(f"Storage inspection failed: {error}", kind="error")

    # ------------------------------------------------------------------ #
    def _backup(self) -> None:
        self.app.set_status("Creating database backup…")
        run_in_background(self, lambda: create_backup(self.db), self._backup_done, self._backup_failed)

    def _backup_done(self, path: Path) -> None:
        self.app.set_status(f"Backup created: {path.name}", kind="success")
        self.activity.configure(text=f"Backup written to {path}")
        self.refresh()

    def _backup_failed(self, error: Exception) -> None:
        logger.exception("Backup failed")
        self.app.set_status(f"Backup failed: {error}", kind="error")

    @staticmethod
    def _open_folder(folder: Path) -> None:
        """Open a directory with the platform file manager."""
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError:
            logger.exception("Could not open %s", folder)
