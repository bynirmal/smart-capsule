"""AI Intelligence: engine capability, models and processing backend."""

from __future__ import annotations

import customtkinter as ctk

from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Badge, Card, KeyValueRow, empty_state, ghost_button, primary_button


class AISettingsPage(BasePage):
    page_key = "ai"
    title = "AI Intelligence"
    subtitle = "Local-first extraction with optional neural models"

    def build(self) -> None:
        ghost_button(self.header_actions, "↻  Refresh", self.refresh).pack(side="right")

        engine = Card(self.body, "Processing engine", "What runs right now, on this machine", padding=18, accent=COLORS["success"])
        engine.pack(fill="x", pady=(0, 12), padx=6)

        self.row_mode = KeyValueRow(engine.body, "Active engine")
        self.row_mode.pack(fill="x", pady=3)
        self.row_device = KeyValueRow(engine.body, "Processing device")
        self.row_device.pack(fill="x", pady=3)
        self.row_torch = KeyValueRow(engine.body, "Neural backend")
        self.row_torch.pack(fill="x", pady=3)
        self.row_privacy = KeyValueRow(engine.body, "Data locality")
        self.row_privacy.pack(fill="x", pady=3)

        models = Card(self.body, "Installed models", "Registered local models", padding=18, accent=COLORS["violet"])
        models.pack(fill="x", pady=(0, 12), padx=6)
        self.models_body = ctk.CTkFrame(models.body, fg_color="transparent")
        self.models_body.pack(fill="x")

        planned = Card(self.body, "Capabilities by phase", "No capability is advertised before it works", padding=18)
        planned.pack(fill="x", pady=(0, 12), padx=6)
        rows = (
            ("Phase 3", "Rule-based context extraction, task detection and compression"),
            ("Phase 3", "Summarisation and continuation-prompt generation"),
            ("Phase 3", "Embedding generation for duplicate detection (optional)"),
            ("Phase 7", "Ollama adapter and external provider adapters with explicit consent"),
        )
        for phase, description in rows:
            row = ctk.CTkFrame(planned.body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            Badge(row, phase, color=COLORS["text_dim"]).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(
                row, text=description, font=font(11), text_color=COLORS["text_dim"], anchor="w", justify="left",
                wraplength=700,
            ).pack(side="left", fill="x")

        primary_button(self.body, "Open GPU monitor", lambda: self.app.navigate("gpu")).pack(
            anchor="w", padx=12, pady=(4, 20)
        )
        self.refresh()

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        report = self.app.gpu.report
        neural = report.torch_installed
        self.row_mode.set(
            "Neural models available" if neural else "Rule-based extractor (built-in)",
            COLORS["success"] if neural else COLORS["text_dim"],
        )
        self.row_device.set(report.status_line, COLORS["success"] if report.has_gpu else COLORS["text_dim"])
        self.row_torch.set(
            f"PyTorch {report.torch_version}" if neural else "not installed",
            COLORS["text"] if neural else COLORS["warning"],
        )
        self.row_privacy.set("Local only · no external transmission")

        for child in self.models_body.winfo_children():
            child.destroy()

        models = self.db.query("SELECT name, backend, size_mb, is_default FROM ai_models ORDER BY name")
        if not models:
            empty_state(
                self.models_body,
                "No models registered",
                "Local models are registered once the model manager ships in Phase 3. The rule-based engine "
                "needs no download and always works.",
            ).pack(fill="x", pady=14)
            return

        for model in models:
            row = ctk.CTkFrame(self.models_body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=model["name"], font=font(12), text_color=COLORS["text"]).pack(side="left")
            if model["is_default"]:
                Badge(row, "DEFAULT", color=COLORS["accent"]).pack(side="right")
            ctk.CTkLabel(
                row,
                text=f"{model['backend']} · {model['size_mb']} MB",
                font=font(10),
                text_color=COLORS["text_muted"],
            ).pack(side="right", padx=10)
