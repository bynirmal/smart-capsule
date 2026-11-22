"""Dashboard: the command centre of the application.

Every figure on this screen is read from SQLite or from the live GPU probe -
nothing is hard-coded.  Loading happens on a worker thread so the window never
stalls while statistics are gathered.
"""

from __future__ import annotations

import logging

import customtkinter as ctk

from ai.gpu_manager import GpuReport
from gui.base_page import BasePage
from gui.theme import COLORS, SPACE, font, icon_font
from gui.widgets import (
    ActionCard,
    Badge,
    Card,
    KeyValueRow,
    StatCard,
    empty_state,
    format_bytes,
    scroll_area,
)
from gui.workers import run_in_background

logger = logging.getLogger(__name__)


class DashboardPage(BasePage):
    page_key = "dashboard"
    title = "Dashboard"
    subtitle = "One click. Complete context. Continue anywhere."

    def build(self) -> None:
        self.action_button("↻  Refresh", self.refresh)

        # -- headline figures ------------------------------------------------
        stats_row = ctk.CTkFrame(self.body, fg_color="transparent")
        stats_row.pack(fill="x", padx=6, pady=(0, 6))
        for column in range(4):
            stats_row.grid_columnconfigure(column, weight=1, uniform="stats")

        self.card_capsules = StatCard(stats_row, "Total capsules", "0", "Portable context snapshots", COLORS["accent"])
        self.card_projects = StatCard(stats_row, "Active projects", "0", "Projects with a live capsule", COLORS["violet"])
        self.card_last = StatCard(stats_row, "Last saved", "—", "No capsule captured yet", COLORS["success"])
        self.card_storage = StatCard(stats_row, "Storage used", "0 B", "Local database + attachments", COLORS["warning"])

        for index, card in enumerate(
            (self.card_capsules, self.card_projects, self.card_last, self.card_storage)
        ):
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0 if index == 3 else 6))

        # -- primary actions -------------------------------------------------
        ctk.CTkLabel(
            self.body,
            text="QUICK ACTIONS",
            font=font(10, "bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", padx=10, pady=(22, 8))

        actions_row = ctk.CTkFrame(self.body, fg_color="transparent")
        actions_row.pack(fill="x", padx=6)
        actions = (
            ("Create Capsule", "Start a structured capsule", "＋", COLORS["accent"], lambda: self.app.navigate("create_capsule")),
            (
                "Capture Conversation",
                "Paste, import or grab context",
                "⌁",
                COLORS["violet"],
                lambda: self.app.navigate("capture"),
            ),
            ("Import Capsule", "Load a .scapsule package", "⇩", COLORS["success"], lambda: self.app.navigate("import")),
            ("Resume Project", "Reopen working context", "▸", COLORS["warning"], lambda: self.app.navigate("resume")),
        )
        for column, (title, subtitle, icon, accent, command) in enumerate(actions):
            actions_row.grid_columnconfigure(column, weight=1, uniform="actions")
            ActionCard(actions_row, title, subtitle, icon, command, accent=accent).grid(
                row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 3 else 6)
            )

        # -- recent + status -------------------------------------------------
        lower = ctk.CTkFrame(self.body, fg_color="transparent")
        lower.pack(fill="both", expand=True, padx=6, pady=(20, 6))
        lower.grid_columnconfigure(0, weight=3)
        lower.grid_columnconfigure(1, weight=2)

        self.recent_card = Card(lower, "Recent capsules", "Newest captures and generated capsules", padding=18)
        self.recent_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.recent_body = ctk.CTkFrame(self.recent_card.body, fg_color="transparent")
        self.recent_body.pack(fill="both", expand=True)

        right = ctk.CTkFrame(lower, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")

        status_card = Card(right, "System status", "Live runtime information", padding=18, accent=COLORS["success"])
        status_card.pack(fill="x")

        self.row_gpu = KeyValueRow(status_card.body, "Compute device")
        self.row_gpu.pack(fill="x", pady=3)
        self.row_engine = KeyValueRow(status_card.body, "AI engine")
        self.row_engine.pack(fill="x", pady=3)
        self.row_model = KeyValueRow(status_card.body, "Active model")
        self.row_model.pack(fill="x", pady=3)
        self.row_processing = KeyValueRow(status_card.body, "Processing")
        self.row_processing.pack(fill="x", pady=3)
        self.row_storage = KeyValueRow(status_card.body, "Data folder")
        self.row_storage.pack(fill="x", pady=3)

        platforms_card = Card(right, "Connected platforms", "Captured sources", padding=18, accent=COLORS["violet"])
        platforms_card.pack(fill="x", pady=(12, 0))
        self.platform_body = ctk.CTkFrame(platforms_card.body, fg_color="transparent")
        self.platform_body.pack(fill="x")

        self.refresh()

    # ------------------------------------------------------------------ #
    # Data flow
    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.app.set_status("Loading dashboard…")
        run_in_background(self, self._load, self._apply, self._failed)

    def _load(self):
        stats = self.db.stats()
        recent = self.db.recent_capsules(6)
        usage = self.db.storage_usage_bytes()
        report = self.app.gpu.report
        last_run = self.db.query_one(
            "SELECT stage, engine, status, started_at FROM processing_history ORDER BY started_at DESC LIMIT 1"
        )
        return stats, recent, usage, report, last_run

    def _failed(self, error: Exception) -> None:
        logger.exception("Dashboard load failed")
        self.app.set_status(f"Dashboard could not load: {error}", kind="error")

    def _apply(self, payload) -> None:
        stats, recent, usage, report, last_run = payload

        self.card_capsules.set(str(stats.total_capsules), "Portable context snapshots")
        self.card_projects.set(str(stats.total_projects), "Projects with a live capsule")
        if stats.last_capsule_title:
            self.card_last.set(
                stats.last_capsule_title[:26] + ("…" if len(stats.last_capsule_title) > 26 else ""),
                "Latest capsule on this machine",
            )
        else:
            self.card_last.set("—", "No capsule captured yet")
        self.card_storage.set(format_bytes(usage), "Local database + attachments")

        self._render_recent(recent)
        self._render_platforms(stats.platforms)
        self._render_status(report, last_run)
        self.app.set_status("Dashboard up to date")

    def _render_recent(self, capsules) -> None:
        for child in self.recent_body.winfo_children():
            child.destroy()

        if not capsules:
            empty_state(
                self.recent_body,
                "No capsules yet",
                "Capture a conversation or import a .scapsule file to build your first portable context.",
            ).pack(fill="x", pady=24)
            return

        for capsule in capsules:
            row = ctk.CTkFrame(self.recent_body, fg_color="transparent")
            row.pack(fill="x", pady=(0, 10))

            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True)

            title_row = ctk.CTkFrame(left, fg_color="transparent")
            title_row.pack(fill="x")
            ctk.CTkLabel(
                title_row,
                text=capsule.title,
                font=font(12, "bold"),
                text_color=COLORS["text"],
                anchor="w",
            ).pack(side="left")
            Badge(title_row, capsule.source_platform, color=COLORS["accent"]).pack(side="left", padx=(8, 0))

            stamp = capsule.created_at.strftime("%d %b %Y · %H:%M") if capsule.created_at else "unknown date"
            ctk.CTkLabel(
                left, text=stamp, font=font(10), text_color=COLORS["text_muted"], anchor="w"
            ).pack(fill="x", pady=(1, 0))

        self.recent_card.body.update_idletasks()

    def _render_platforms(self, platforms: dict[str, int]) -> None:
        for child in self.platform_body.winfo_children():
            child.destroy()

        if not platforms:
            ctk.CTkLabel(
                self.platform_body,
                text="No platform captured yet. Imported capsules will appear here.",
                font=font(11),
                text_color=COLORS["text_muted"],
                anchor="w",
                wraplength=300,
                justify="left",
            ).pack(fill="x")
            return

        for name, count in list(platforms.items())[:5]:
            row = ctk.CTkFrame(self.platform_body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row, text=name, font=font(12), text_color=COLORS["text_dim"], anchor="w"
            ).pack(side="left")
            Badge(row, str(count), color=COLORS["success"]).pack(side="right")

    def _render_status(self, report: GpuReport, last_run) -> None:
        self.row_gpu.set(report.status_line, COLORS["success"] if report.has_gpu else COLORS["text_dim"])
        self.row_engine.set(
            "Neural (PyTorch)" if report.torch_installed else "Rule-based (CPU, built-in)",
            COLORS["success"] if report.torch_installed else COLORS["text_dim"],
        )

        model = self.db.get_setting("ai_default_model", "")
        self.row_model.set(model or "No model selected", COLORS["text_dim"] if not model else COLORS["text"])

        if last_run is None:
            self.row_processing.set("Idle", COLORS["text_dim"])
        else:
            self.row_processing.set(f"{last_run['stage']} · {last_run['status']}", COLORS["text"])

        from config import data_dir

        folder = str(data_dir())
        self.row_storage.set(folder if len(folder) <= 34 else "…" + folder[-33:], COLORS["text_muted"])
