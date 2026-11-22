"""Base class for every screen in the desktop application."""

from __future__ import annotations

import customtkinter as ctk

from gui.theme import COLORS, SPACE, font, icon_font
from gui.widgets import primary_button, scroll_area


class BasePage(ctk.CTkFrame):
    """Common page chrome: title block, action slot and scrolling content area.

    Subclasses set ``page_key``/``title``/``subtitle``, implement :meth:`build`
    and optionally override :meth:`on_show` / :meth:`refresh`.
    """

    page_key: str = ""
    title: str = "Page"
    subtitle: str = ""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.app = app
        self.db = app.db

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=SPACE["xl"], pady=(SPACE["xl"], SPACE["md"]))
        header.grid_columnconfigure(0, weight=1)

        text_block = ctk.CTkFrame(header, fg_color="transparent")
        text_block.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            text_block, text=self.title, font=font(24, "bold"), text_color=COLORS["text"], anchor="w"
        ).pack(anchor="w")
        if self.subtitle:
            ctk.CTkLabel(
                text_block,
                text=self.subtitle,
                font=font(12),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).pack(anchor="w", pady=(3, 0))

        self.header_actions = ctk.CTkFrame(header, fg_color="transparent")
        self.header_actions.grid(row=0, column=1, sticky="e")

        self.body = scroll_area(self)
        self.body.grid(row=1, column=0, sticky="nsew", padx=SPACE["xl"] - 6, pady=(0, SPACE["md"]))
        self.body.grid_columnconfigure(0, weight=1)

        self.build()

    # -- hooks -------------------------------------------------------------
    def build(self) -> None:
        """Construct the page content. Called once at first display."""

    def on_show(self) -> None:
        """Called every time the page becomes visible."""

    def refresh(self) -> None:
        """Reload dynamic data; safe to call repeatedly."""

    # -- helpers -----------------------------------------------------------
    def action_button(self, text: str, command, **kwargs) -> ctk.CTkButton:
        button = primary_button(self.header_actions, text, command, **kwargs)
        button.pack(side="right", padx=(10, 0))
        return button

    def phase_notice(self, phase: str, message: str, bullets: list[str] | None = None) -> ctk.CTkFrame:
        """Honest status card for capabilities that arrive in a later phase."""
        from gui.widgets import Card

        card = Card(self.body, title="Planned for a later phase", subtitle=phase, accent=COLORS["violet"])
        card.pack(fill="x", pady=(0, 16), padx=6)

        ctk.CTkLabel(
            card.body,
            text=message,
            font=font(12),
            text_color=COLORS["text_dim"],
            justify="left",
            anchor="w",
            wraplength=760,
        ).pack(fill="x", anchor="w")

        for bullet in bullets or []:
            row = ctk.CTkFrame(card.body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="•", font=font(12), text_color=COLORS["violet"], width=14).pack(side="left")
            ctk.CTkLabel(
                row,
                text=bullet,
                font=font(11),
                text_color=COLORS["text_muted"],
                anchor="w",
                justify="left",
                wraplength=720,
            ).pack(side="left", fill="x")
        return card
