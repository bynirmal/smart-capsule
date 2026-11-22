"""Connected Platforms: capture sources and their local activity."""

from __future__ import annotations

import logging

import customtkinter as ctk

from config import SUPPORTED_AI_PLATFORMS
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Badge, Card, ghost_button
from gui.workers import run_in_background

logger = logging.getLogger(__name__)


class PlatformsPage(BasePage):
    page_key = "platforms"
    title = "Connected Platforms"
    subtitle = "Where your context comes from"

    def build(self) -> None:
        ghost_button(self.header_actions, "↻  Refresh", self.refresh).pack(side="right")

        overview = Card(
            self.body,
            "Capture sources",
            "Counts come from capsules stored on this machine",
            padding=18,
            accent=COLORS["accent"],
        )
        overview.pack(fill="x", pady=(0, 12), padx=6)
        self.list_body = ctk.CTkFrame(overview.body, fg_color="transparent")
        self.list_body.pack(fill="x")

        browser = Card(
            self.body,
            "Browser extension",
            "Chrome Manifest V3 · side panel + popup",
            padding=18,
            accent=COLORS["violet"],
        )
        browser.pack(fill="x", pady=(0, 12), padx=6)
        status = ctk.CTkFrame(browser.body, fg_color="transparent")
        status.pack(fill="x")
        ctk.CTkLabel(
            status,
            text="Not built yet — the extension, its adapters and the authenticated local bridge ship in Phase 7.",
            font=font(11),
            text_color=COLORS["text_dim"],
            anchor="w",
            justify="left",
            wraplength=740,
        ).pack(side="left", fill="x", expand=True)
        Badge(status, "Phase 7", color=COLORS["warning"]).pack(side="right")

        ctk.CTkLabel(
            browser.body,
            text=(
                "Planned adapters: ChatGPT, Claude, Gemini, plus a generic adapter for compatible sites. Each "
                "adapter is versioned because page structure changes, and capture is always user-initiated."
            ),
            font=font(11),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=780,
        ).pack(fill="x", pady=(8, 0))

        self.refresh()

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        run_in_background(self, self.db.stats, self._render, self._failed)

    def _failed(self, error: Exception) -> None:
        logger.exception("Platform stats failed")
        self.app.set_status(f"Could not read platform usage: {error}", kind="error")

    def _render(self, stats) -> None:
        for child in self.list_body.winfo_children():
            child.destroy()

        for platform in SUPPORTED_AI_PLATFORMS:
            count = stats.platforms.get(platform, 0)
            row = ctk.CTkFrame(self.list_body, fg_color="transparent")
            row.pack(fill="x", pady=3)

            ctk.CTkLabel(
                row, text=platform, font=font(12, "bold"), text_color=COLORS["text"], width=120, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=f"{count} capsule(s)" if count else "no capsules captured yet",
                font=font(11),
                text_color=COLORS["text_dim"] if count else COLORS["text_muted"],
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            Badge(
                row,
                "CONNECTED" if count else "AVAILABLE",
                color=COLORS["success"] if count else COLORS["text_muted"],
            ).pack(side="right")
