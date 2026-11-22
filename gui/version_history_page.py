"""Version History: inspect and restore capsule revisions."""

from __future__ import annotations

import json
import logging

import customtkinter as ctk

from core.capsule_generator import save_document
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Badge, Card, empty_state, ghost_button
from gui.workers import run_in_background

logger = logging.getLogger(__name__)


class VersionHistoryPage(BasePage):
    page_key = "versions"
    title = "Version History"
    subtitle = "Every capsule revision, restorable without losing newer work"

    def build(self) -> None:
        ghost_button(self.header_actions, "↻  Refresh", self.refresh).pack(side="right")

        card = Card(
            self.body,
            "Revisions",
            "A snapshot is written on every generation and edit",
            padding=18,
            accent=COLORS["violet"],
        )
        card.pack(fill="x", pady=(0, 12), padx=6)
        self.list_body = ctk.CTkFrame(card.body, fg_color="transparent")
        self.list_body.pack(fill="x")

        ctk.CTkLabel(
            self.body,
            text=(
                "Restoring a version writes its content as the current capsule and records that restore as a "
                "new revision, so nothing is ever destroyed by going back."
            ),
            font=font(11),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", padx=12, pady=(0, 16))

        self.refresh()

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        run_in_background(
            self,
            lambda: self.db.query(
                "SELECT v.capsule_id, v.version_number, v.note, v.created_at, v.payload_json, c.title "
                "FROM capsule_versions v JOIN capsules c ON c.id = v.capsule_id "
                "ORDER BY v.created_at DESC LIMIT 100"
            ),
            self._render,
            self._failed,
        )

    def _failed(self, error: Exception) -> None:
        logger.exception("Version history failed")
        self.app.set_status(f"Could not read version history: {error}", kind="error")

    def _render(self, rows) -> None:
        for child in self.list_body.winfo_children():
            child.destroy()

        if not rows:
            empty_state(
                self.list_body,
                "No revisions yet",
                "Versions appear here once a captured conversation is turned into a capsule.",
            ).pack(fill="x", pady=18)
            return

        for row in rows:
            line = ctk.CTkFrame(
                self.list_body,
                fg_color=COLORS["panel_alt"],
                corner_radius=10,
                border_width=1,
                border_color=COLORS["border"],
            )
            line.pack(fill="x", pady=3)

            ctk.CTkLabel(
                line,
                text=f"v{row['version_number']}",
                font=font(11, "bold"),
                text_color=COLORS["accent"],
                width=42,
                anchor="w",
            ).pack(side="left", padx=(10, 0), pady=8)

            info = ctk.CTkFrame(line, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, pady=6)
            ctk.CTkLabel(
                info, text=row["title"], font=font(12), text_color=COLORS["text"], anchor="w"
            ).pack(fill="x")
            ctk.CTkLabel(
                info,
                text=f"{row['note'] or 'snapshot'} · {str(row['created_at'])[:16]}",
                font=font(9),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).pack(fill="x")

            ghost_button(
                line,
                "Restore",
                lambda r=row: self._restore(r),
                height=28,
                width=80,
            ).pack(side="right", padx=10)

        self.app.set_status(f"{len(rows)} revision(s) listed")

    # ------------------------------------------------------------------ #
    def _restore(self, row) -> None:
        try:
            document = json.loads(row["payload_json"])
            if not isinstance(document, dict):
                raise ValueError("The snapshot is not a capsule document.")
        except (TypeError, ValueError) as exc:
            self.app.set_status(f"Snapshot unreadable: {exc}", kind="error")
            return

        self.app.set_status(f"Restoring version {row['version_number']}…")
        run_in_background(
            self,
            lambda: save_document(
                self.db,
                document,
                capsule_id=row["capsule_id"],
                note=f"Restored version {row['version_number']}",
            ),
            self._restored,
            self._restore_failed,
        )

    def _restored(self, capsule_id: str) -> None:
        self.app.set_status("Version restored · stored as a new revision", kind="success")
        self.refresh()

    def _restore_failed(self, error: Exception) -> None:
        logger.exception("Restore failed")
        self.app.set_status(f"Restore failed: {error}", kind="error")
