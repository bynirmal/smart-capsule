"""My Capsules: browse, search and manage stored capsules."""

from __future__ import annotations

import logging

import customtkinter as ctk

from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Badge, Card, confirm_dialog, empty_state, format_timestamp, primary_button, ghost_button
from gui.workers import Debouncer, run_in_background

logger = logging.getLogger(__name__)


class CapsulesPage(BasePage):
    page_key = "capsules"
    title = "My Capsules"
    subtitle = "Every captured context on this machine"

    def build(self) -> None:
        ghost_button(self.header_actions, "↻  Refresh", self.refresh).pack(side="right", padx=(0, 8))
        primary_button(
            self.header_actions, "＋  Capture conversation", lambda: self.app.navigate("capture")
        ).pack(side="right")

        toolbar = ctk.CTkFrame(self.body, fg_color="transparent")
        toolbar.pack(fill="x", padx=6, pady=(0, 12))

        self.search_entry = ctk.CTkEntry(
            toolbar,
            placeholder_text="Search capsules by title, summary or next action…",
            height=36,
            corner_radius=10,
            fg_color=COLORS["panel"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["text_muted"],
            font=font(12),
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", lambda _e: self._debouncer.call(self.refresh))
        self._debouncer = Debouncer(self, 280)

        self.list_card = Card(self.body, "Capsule library", "Newest first", padding=18)
        self.list_card.pack(fill="both", expand=True, padx=6)
        self.list_body = ctk.CTkFrame(self.list_card.body, fg_color="transparent")
        self.list_body.pack(fill="both", expand=True)
        self._capsules: list = []

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        term = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        run_in_background(
            self,
            lambda: self.db.list_capsules(search=term, limit=100),
            self._render,
            self._failed,
        )

    def _failed(self, error: Exception) -> None:
        logger.exception("Capsule listing failed")
        self.app.set_status(f"Could not list capsules: {error}", kind="error")

    def _render(self, capsules) -> None:
        self._capsules = capsules
        for child in self.list_body.winfo_children():
            child.destroy()

        if not capsules:
            term = self.search_entry.get().strip()
            message = (
                f"No capsule matches “{term}”."
                if term
                else "Capture a conversation to create your first portable capsule."
            )
            empty_state(self.list_body, "Nothing here yet", message).pack(fill="x", pady=30)
            self.app.set_status("0 capsules")
            return

        for capsule in capsules:
            self._row(capsule)

        self.app.set_status(f"{len(capsules)} capsule(s) listed")

    def _row(self, capsule) -> None:
        row = ctk.CTkFrame(
            self.list_body,
            fg_color=COLORS["panel_alt"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        row.pack(fill="x", pady=4)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=14, pady=10)

        top = ctk.CTkFrame(info, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=capsule.title, font=font(13, "bold"), text_color=COLORS["text"]).pack(side="left")
        Badge(top, capsule.source_platform, color=COLORS["accent"]).pack(side="left", padx=(8, 0))
        Badge(top, capsule.compression_mode, color=COLORS["violet"]).pack(side="left", padx=(6, 0))
        if capsule.payload().get("draft"):
            Badge(top, "DRAFT", color=COLORS["warning"]).pack(side="left", padx=(6, 0))

        summary = capsule.summary.strip() or capsule.next_action.strip() or "No summary stored for this capsule yet."
        ctk.CTkLabel(
            info,
            text=summary,
            font=font(11),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", pady=(3, 0))
        ctk.CTkLabel(
            info,
            text=f"Saved {format_timestamp(capsule.created_at)}",
            font=font(10),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right", padx=12)
        ghost_button(actions, "Open", lambda c=capsule: self._open(c), height=30).pack(side="left", padx=3)
        ghost_button(actions, "Archive", lambda c=capsule: self._archive(c), height=30).pack(side="left", padx=3)
        ghost_button(actions, "Delete", lambda c=capsule: self._delete(c), height=30).pack(side="left", padx=3)

    # ------------------------------------------------------------------ #
    def _open(self, capsule) -> None:
        self.app.navigate("resume")
        page = self.app.pages.get("resume")
        if page is not None and hasattr(page, "focus_capsule"):
            page.focus_capsule(capsule.id)

    def _archive(self, capsule) -> None:
        self.db.update_capsule(capsule.id, is_archived=True)
        self.app.set_status(f"Archived “{capsule.title}”", kind="success")
        self.refresh()

    def _delete(self, capsule) -> None:
        if self.db.get_bool_setting("confirm_delete", True):
            confirmed = confirm_dialog(
                self,
                "Delete capsule",
                f"“{capsule.title}” and its stored conversations will be removed from this computer. "
                "This cannot be undone.",
                confirm_text="Delete capsule",
            )
            if not confirmed:
                return
        try:
            self.db.delete_capsule(capsule.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Delete failed")
            self.app.set_status(f"Delete failed: {exc}", kind="error")
            return
        self.app.set_status(f"Deleted “{capsule.title}”", kind="success")
        self.refresh()
