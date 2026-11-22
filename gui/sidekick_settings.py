"""Sidekick Settings: real controls for the floating assistant."""

from __future__ import annotations

import logging

import customtkinter as ctk

from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Badge, Card, ghost_button, primary_button
from sidekick import startup_manager

logger = logging.getLogger(__name__)

SHORTCUT_ACTIONS = {
    "toggle_sidekick": "Open / hide Sidekick",
    "quick_save": "Quick save clipboard as capsule",
    "capture_selection": "Send clipboard to Capture",
    "open_app": "Open main application",
}


class SidekickSettingsPage(BasePage):
    page_key = "sidekick"
    title = "Sidekick Settings"
    subtitle = "Floating assistant, global shortcuts and startup behaviour"

    def build(self) -> None:
        ghost_button(self.header_actions, "Show Sidekick", self.app.toggle_sidekick).pack(side="right")

        behaviour = Card(
            self.body,
            "Widget behaviour",
            "Changes apply immediately",
            padding=18,
            accent=COLORS["accent"],
        )
        behaviour.pack(fill="x", pady=(0, 12), padx=6)

        self.topmost_switch = ctk.CTkSwitch(
            behaviour.body,
            text="Keep Sidekick above other windows",
            font=font(12),
            text_color=COLORS["text_dim"],
            progress_color=COLORS["accent"],
            command=self._toggle_topmost,
        )
        self.topmost_switch.pack(anchor="w", pady=4)

        self.compact_switch = ctk.CTkSwitch(
            behaviour.body,
            text="Start in compact mode",
            font=font(12),
            text_color=COLORS["text_dim"],
            progress_color=COLORS["accent"],
            command=self._toggle_compact,
        )
        self.compact_switch.pack(anchor="w", pady=4)

        self.autostart_switch = ctk.CTkSwitch(
            behaviour.body,
            text="Start Smart Capsule when Windows starts",
            font=font(12),
            text_color=COLORS["text_dim"],
            progress_color=COLORS["violet"],
            command=self._toggle_autostart,
        )
        self.autostart_switch.pack(anchor="w", pady=4)

        ctk.CTkLabel(
            behaviour.body,
            text="TRANSPARENCY",
            font=font(9, "bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", pady=(12, 2))
        self.opacity_slider = ctk.CTkSlider(
            behaviour.body,
            from_=0.55,
            to=1.0,
            number_of_steps=9,
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self._preview_opacity,
        )
        self.opacity_slider.pack(fill="x")
        self.opacity_slider.bind("<ButtonRelease-1>", self._save_opacity)

        self.behaviour_note = ctk.CTkLabel(
            behaviour.body,
            text="",
            font=font(10),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=780,
        )
        self.behaviour_note.pack(fill="x", pady=(8, 0))

        shortcuts = Card(
            self.body,
            "Global shortcuts",
            "Registered with Windows so they work from any application",
            padding=18,
            accent=COLORS["violet"],
        )
        shortcuts.pack(fill="x", pady=(0, 12), padx=6)
        self.shortcut_body = ctk.CTkFrame(shortcuts.body, fg_color="transparent")
        self.shortcut_body.pack(fill="x")

        privacy = Card(
            self.body,
            "Privacy",
            "What the Sidekick will never do",
            padding=18,
            accent=COLORS["success"],
        )
        privacy.pack(fill="x", pady=(0, 12), padx=6)
        for line in (
            "No screenshots and no reading of other application windows",
            "Clipboard is read only when you press a capture or save button",
            "Quick save always runs locally and never uploads the conversation",
            "The widget holds no credentials and writes no session tokens",
        ):
            row = ctk.CTkFrame(privacy.body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="◆", font=font(9), text_color=COLORS["success"], width=16).pack(side="left")
            ctk.CTkLabel(
                row, text=line, font=font(11), text_color=COLORS["text_dim"], anchor="w", justify="left",
                wraplength=760,
            ).pack(side="left", fill="x")

        primary_button(self.body, "Open Sidekick now", self.app.toggle_sidekick).pack(
            anchor="w", padx=12, pady=(4, 18)
        )

        self._load()

    def on_show(self) -> None:
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if self.db.get_bool_setting("sidekick_always_on_top", True):
            self.topmost_switch.select()
        else:
            self.topmost_switch.deselect()

        if self.db.get_bool_setting("sidekick_compact", True):
            self.compact_switch.select()
        else:
            self.compact_switch.deselect()

        if startup_manager.is_enabled():
            self.autostart_switch.select()
        else:
            self.autostart_switch.deselect()

        try:
            opacity = float(self.db.get_setting("sidekick_opacity", "0.97"))
        except ValueError:
            opacity = 0.97
        self.opacity_slider.set(max(0.55, min(1.0, opacity)))

        self._render_shortcuts()

    def _render_shortcuts(self) -> None:
        for child in self.shortcut_body.winfo_children():
            child.destroy()

        status = self.app.shortcuts.status() if hasattr(self.app, "shortcuts") else {"registered": [], "failed": {}, "shortcuts": {}}
        shortcuts = status.get("shortcuts") or {}
        failed = status.get("failed") or {}

        for action, label in SHORTCUT_ACTIONS.items():
            row = ctk.CTkFrame(self.shortcut_body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row, text=label, font=font(11), text_color=COLORS["text_dim"], anchor="w"
            ).pack(side="left", fill="x", expand=True)

            keys = shortcuts.get(action, "")
            ctk.CTkLabel(
                row,
                text=keys,
                font=font(10, "bold"),
                text_color=COLORS["text"],
                fg_color=COLORS["panel_alt"],
                corner_radius=8,
                padx=8,
                pady=3,
            ).pack(side="right")

            if action in failed:
                Badge(row, "CONFLICT", color=COLORS["warning"]).pack(side="right", padx=8)
            elif action in (status.get("registered") or []) or keys in (status.get("registered") or []):
                Badge(row, "GLOBAL", color=COLORS["success"]).pack(side="right", padx=8)

        platform_note = failed.get("__platform__") or (
            "Global hotkeys are active. In-app shortcuts also work whenever the window has focus."
            if status.get("registered")
            else "Global registration is unavailable; shortcuts work while the app is focused."
        )
        self.behaviour_note.configure(text=platform_note)

    # ------------------------------------------------------------------ #
    def refresh_status(self) -> None:
        self._render_shortcuts()

    def _toggle_topmost(self) -> None:
        enabled = bool(self.topmost_switch.get())
        self.db.set_setting("sidekick_always_on_top", "1" if enabled else "0")
        widget = getattr(self.app.sidekick, "widget", None)
        if widget is not None:
            try:
                widget.attributes("-topmost", enabled)
            except Exception:  # pragma: no cover
                logger.debug("topmost change failed", exc_info=True)
        self.app.set_status(f"Always on top {'enabled' if enabled else 'disabled'}", kind="success")

    def _toggle_compact(self) -> None:
        compact = bool(self.compact_switch.get())
        self.db.set_setting("sidekick_compact", "1" if compact else "0")
        self.app.set_status(f"Sidekick will start {'compact' if compact else 'expanded'}", kind="success")

    def _toggle_autostart(self) -> None:
        desired = bool(self.autostart_switch.get())
        ok, message = startup_manager.set_enabled(desired)
        if not ok:
            self.app.set_status(message, kind="error")
            if startup_manager.is_enabled():
                self.autostart_switch.select()
            else:
                self.autostart_switch.deselect()
            return
        self.db.set_setting("sidekick_autostart", "1" if desired else "0")
        self.app.set_status(message, kind="success")

    def _preview_opacity(self, value: float) -> None:
        widget = getattr(self.app.sidekick, "widget", None)
        if widget is not None:
            try:
                widget.attributes("-alpha", float(value))
            except Exception:  # pragma: no cover
                logger.debug("alpha change failed", exc_info=True)

    def _save_opacity(self, _event=None) -> None:
        value = round(float(self.opacity_slider.get()), 2)
        self.db.set_setting("sidekick_opacity", f"{value}")
        self.app.set_status(f"Sidekick opacity set to {int(value * 100)}%", kind="success")
