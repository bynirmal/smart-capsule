"""Settings: persisted user preferences and environment information."""

from __future__ import annotations

import logging

import customtkinter as ctk

from config import APP_NAME, BUILD_STAGE, COMPRESSION_MODES, SUPPORTED_AI_PLATFORMS, VERSION, data_dir
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Card, KeyValueRow, ghost_button, primary_button

logger = logging.getLogger(__name__)

COMPRESSION_LABELS = {
    "balanced": "Balanced — essential context plus useful detail",
    "high": "High compression — critical project state only",
    "full": "Full preservation — original data kept alongside the summary",
}


class SettingsPage(BasePage):
    page_key = "settings"
    title = "Settings"
    subtitle = "Preferences stored locally in SQLite"

    def build(self) -> None:
        ghost_button(self.header_actions, "Restore defaults", self._restore_defaults).pack(side="right", padx=(0, 8))
        primary_button(self.header_actions, "Save settings", self._save).pack(side="right")

        prefs = Card(
            self.body,
            "Capsule defaults",
            "Applied by the capture and generation engines",
            padding=18,
            accent=COLORS["accent"],
        )
        prefs.pack(fill="x", pady=(0, 12), padx=6)

        ctk.CTkLabel(
            prefs.body, text="Default compression mode", font=font(12), text_color=COLORS["text_dim"], anchor="w"
        ).pack(fill="x", pady=(0, 4))
        self.compression_menu = ctk.CTkOptionMenu(
            prefs.body,
            values=[COMPRESSION_LABELS[mode] for mode in COMPRESSION_MODES],
            height=36,
            corner_radius=10,
            font=font(11),
            dropdown_font=font(11),
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
        )
        self.compression_menu.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            prefs.body, text="Default capture platform", font=font(12), text_color=COLORS["text_dim"], anchor="w"
        ).pack(fill="x", pady=(0, 4))
        self.platform_menu = ctk.CTkOptionMenu(
            prefs.body,
            values=list(SUPPORTED_AI_PLATFORMS),
            height=36,
            corner_radius=10,
            font=font(11),
            dropdown_font=font(11),
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
        )
        self.platform_menu.pack(fill="x", pady=(0, 12))

        safety = Card(self.body, "Safety", "Destructive actions stay deliberate", padding=18, accent=COLORS["warning"])
        safety.pack(fill="x", pady=(0, 12), padx=6)

        self.confirm_switch = ctk.CTkSwitch(
            safety.body,
            text="Ask before deleting a capsule",
            font=font(12),
            text_color=COLORS["text_dim"],
            progress_color=COLORS["accent"],
            button_color=COLORS["text"],
            button_hover_color=COLORS["text_dim"],
        )
        self.confirm_switch.pack(anchor="w", pady=4)

        self.local_switch = ctk.CTkSwitch(
            safety.body,
            text="Keep all AI processing on this machine (recommended)",
            font=font(12),
            text_color=COLORS["text_dim"],
            progress_color=COLORS["accent"],
            button_color=COLORS["text"],
            button_hover_color=COLORS["text_dim"],
        )
        self.local_switch.pack(anchor="w", pady=4)

        about = Card(self.body, "About this installation", "Runtime and storage facts", padding=18)
        about.pack(fill="x", pady=(0, 12), padx=6)
        self.row_version = KeyValueRow(about.body, "Version")
        self.row_version.pack(fill="x", pady=3)
        self.row_stage = KeyValueRow(about.body, "Build stage")
        self.row_stage.pack(fill="x", pady=3)
        self.row_data = KeyValueRow(about.body, "Data directory")
        self.row_data.pack(fill="x", pady=3)

        self.status_label = ctk.CTkLabel(
            self.body, text="", font=font(11), text_color=COLORS["success"], anchor="w"
        )
        self.status_label.pack(fill="x", padx=12, pady=(0, 16))

        self._load()

    def on_show(self) -> None:
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        mode = self.db.get_setting("default_compression", "balanced")
        self.compression_menu.set(COMPRESSION_LABELS.get(mode, COMPRESSION_LABELS["balanced"]))

        platform = self.db.get_setting("default_platform", "ChatGPT")
        if platform not in SUPPORTED_AI_PLATFORMS:
            platform = "ChatGPT"
        self.platform_menu.set(platform)

        if self.db.get_bool_setting("confirm_delete", True):
            self.confirm_switch.select()
        else:
            self.confirm_switch.deselect()

        if self.db.get_bool_setting("local_only_ai", True):
            self.local_switch.select()
        else:
            self.local_switch.deselect()

        self.row_version.set(f"{APP_NAME} v{VERSION}")
        self.row_stage.set(BUILD_STAGE)
        folder = str(data_dir())
        self.row_data.set(folder if len(folder) <= 46 else "…" + folder[-45:])
        self.status_label.configure(text="")

    def _save(self) -> None:
        label = self.compression_menu.get()
        mode = next((key for key, text in COMPRESSION_LABELS.items() if text == label), "balanced")
        try:
            self.db.set_setting("default_compression", mode)
            self.db.set_setting("default_platform", self.platform_menu.get())
            self.db.set_setting("confirm_delete", "1" if self.confirm_switch.get() else "0")
            self.db.set_setting("local_only_ai", "1" if self.local_switch.get() else "0")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Could not save settings")
            self.status_label.configure(text=f"Could not save: {exc}", text_color=COLORS["danger"])
            return
        self.status_label.configure(text="Settings saved to the local database.", text_color=COLORS["success"])
        self.app.set_status("Settings saved", kind="success")

    def _restore_defaults(self) -> None:
        try:
            self.db.set_setting("default_compression", "balanced")
            self.db.set_setting("default_platform", "ChatGPT")
            self.db.set_setting("confirm_delete", "1")
            self.db.set_setting("local_only_ai", "1")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Could not restore defaults")
            self.status_label.configure(text=f"Could not restore: {exc}", text_color=COLORS["danger"])
            return
        self._load()
        self.status_label.configure(text="Defaults restored.", text_color=COLORS["success"])
