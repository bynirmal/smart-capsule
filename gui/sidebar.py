"""Sidebar navigation for the main window."""

from __future__ import annotations

from typing import Callable, Sequence

import customtkinter as ctk

from config import APP_NAME, VERSION
from gui.navigation import NavItem, groups
from gui.theme import COLORS, RADIUS, font, icon_font

SIDEBAR_WIDTH = 248


class Sidebar(ctk.CTkFrame):
    """Vertical navigation rail with logo, grouped sections and status footer."""

    def __init__(
        self,
        master,
        on_navigate: Callable[[str], None],
        on_sidekick: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color=COLORS["sidebar"], corner_radius=0, width=SIDEBAR_WIDTH)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._on_navigate = on_navigate
        self._on_sidekick = on_sidekick
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._active: str | None = None

        self._build_logo()
        self._build_nav()
        self._build_footer()

    # -- construction ------------------------------------------------------
    def _build_logo(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 14))

        mark = ctk.CTkFrame(header, fg_color=COLORS["accent"], corner_radius=13, width=42, height=42)
        mark.pack(side="left")
        mark.pack_propagate(False)
        ctk.CTkLabel(
            mark, text="◈", font=icon_font(20), text_color="#FFFFFF"
        ).place(relx=0.5, rely=0.5, anchor="center")

        text = ctk.CTkFrame(header, fg_color="transparent")
        text.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(
            text, text="SMART", font=font(15, "bold"), text_color=COLORS["text"], anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            text, text="CAPSULE", font=font(15, "bold"), text_color=COLORS["accent"], anchor="w"
        ).pack(anchor="w", pady=(0, 1))

        ctk.CTkLabel(
            self,
            text="CONTEXT PORTABILITY SUITE",
            font=font(9, "bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).grid(row=0, column=0, sticky="sw", padx=20, pady=(0, 10))

    def _build_nav(self) -> None:
        nav = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["sidebar"],
            scrollbar_button_hover_color=COLORS["panel_alt"],
        )
        nav.grid(row=1, column=0, sticky="nsew", padx=(12, 6))
        nav.grid_columnconfigure(0, weight=1)

        row = 0
        for group_name, items in groups():
            if row:
                spacer = ctk.CTkFrame(nav, fg_color="transparent", height=8)
                spacer.grid(row=row, column=0, sticky="ew")
                row += 1

            ctk.CTkLabel(
                nav,
                text=group_name,
                font=font(9, "bold"),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).grid(row=row, column=0, sticky="ew", padx=12, pady=(2, 6))
            row += 1

            for item in items:
                button = self._nav_button(nav, item)
                button.grid(row=row, column=0, sticky="ew", pady=1)
                self._buttons[item.key] = button
                row += 1

    def _nav_button(self, master, item: NavItem) -> ctk.CTkButton:
        return ctk.CTkButton(
            master,
            text=f"  {item.icon}   {item.label}",
            anchor="w",
            height=36,
            corner_radius=RADIUS["control"],
            font=font(12),
            fg_color="transparent",
            hover_color=COLORS["panel_alt"],
            text_color=COLORS["text_dim"],
            command=lambda key=item.key: self._on_navigate(key),
        )

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=12)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 16))

        inner = ctk.CTkFrame(footer, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        status_row = ctk.CTkFrame(inner, fg_color="transparent")
        status_row.pack(fill="x")
        self._status_dot = ctk.CTkLabel(
            status_row, text="●", font=font(10), text_color=COLORS["text_muted"], width=12
        )
        self._status_dot.pack(side="left")
        self._status_label = ctk.CTkLabel(
            status_row,
            text="Detecting hardware…",
            font=font(11, "bold"),
            text_color=COLORS["text_dim"],
            anchor="w",
        )
        self._status_label.pack(side="left", padx=(2, 0))

        self._detail_label = ctk.CTkLabel(
            inner,
            text=f"{APP_NAME} v{VERSION}",
            font=font(9),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self._detail_label.pack(fill="x", pady=(2, 0))

        if self._on_sidekick is not None:
            ctk.CTkButton(
                inner,
                text="◉  Show Sidekick",
                height=28,
                corner_radius=8,
                font=font(10, "bold"),
                fg_color=COLORS["accent_soft"],
                hover_color=COLORS["panel_hover"],
                text_color=COLORS["accent"],
                command=self._on_sidekick,
            ).pack(fill="x", pady=(8, 0))

    # -- public API --------------------------------------------------------
    def set_active(self, key: str) -> None:
        self._active = key
        for button_key, button in self._buttons.items():
            if button_key == key:
                button.configure(
                    fg_color=COLORS["accent_soft"],
                    text_color=COLORS["text"],
                    font=font(12, "bold"),
                )
            else:
                button.configure(
                    fg_color="transparent",
                    text_color=COLORS["text_dim"],
                    font=font(12),
                )

    def set_hardware_status(self, headline: str, detail: str = "", ok: bool = True) -> None:
        self._status_dot.configure(text_color=COLORS["success"] if ok else COLORS["warning"])
        self._status_label.configure(text=headline)
        self._detail_label.configure(text=detail or f"{APP_NAME} v{VERSION}")
