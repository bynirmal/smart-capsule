"""Import Capsule: load a validated capsule package into the local library."""

from __future__ import annotations

import logging
import tkinter.filedialog as filedialog
from pathlib import Path

import customtkinter as ctk

from config import CAPSULE_EXTENSION
from core.capsule_importer import ImportError_, import_capsule
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Card, ghost_button, primary_button
from gui.workers import run_in_background

logger = logging.getLogger(__name__)


class ImportPage(BasePage):
    page_key = "import"
    title = "Import Capsule"
    subtitle = "Restore portable context — validated before anything is written"

    def build(self) -> None:
        source = Card(
            self.body,
            "Capsule file",
            f"{CAPSULE_EXTENSION} · .zip · .json",
            padding=18,
            accent=COLORS["accent"],
        )
        source.pack(fill="x", pady=(0, 12), padx=6)

        row = ctk.CTkFrame(source.body, fg_color="transparent")
        row.pack(fill="x")
        self.path_entry = ctk.CTkEntry(
            row,
            placeholder_text="No file selected",
            height=36,
            corner_radius=10,
            fg_color=COLORS["bg"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=font(11),
        )
        self.path_entry.pack(side="left", fill="x", expand=True)
        ghost_button(row, "Browse…", self._browse, height=36, width=110).pack(side="left", padx=8)
        primary_button(row, "Import capsule", self._import, height=36).pack(side="left")

        self.result_card = Card(
            self.body, "Result", "Import report", padding=18, accent=COLORS["success"]
        )
        self.result_body = ctk.CTkFrame(self.result_card.body, fg_color="transparent")
        self.result_body.pack(fill="x")

        rules = Card(
            self.body,
            "Validation rules",
            "An import either succeeds completely or changes nothing",
            padding=18,
            accent=COLORS["violet"],
        )
        rules.pack(fill="x", pady=(12, 0), padx=6)
        for rule in (
            "Archive entries are hash-checked against manifest.json",
            "Path traversal outside the data folder is rejected",
            "The capsule format version must be supported by this build",
            "Attachments are stored under the new capsule id only after validation",
        ):
            line = ctk.CTkFrame(rules.body, fg_color="transparent")
            line.pack(fill="x", pady=2)
            ctk.CTkLabel(line, text="✓", font=font(11, "bold"), text_color=COLORS["success"], width=16).pack(
                side="left"
            )
            ctk.CTkLabel(
                line, text=rule, font=font(11), text_color=COLORS["text_dim"], anchor="w", justify="left",
                wraplength=760,
            ).pack(side="left", fill="x")

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a capsule",
            filetypes=[
                ("Smart Capsule", f"*{CAPSULE_EXTENSION}"),
                ("ZIP archive", "*.zip"),
                ("JSON document", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    # ------------------------------------------------------------------ #
    def _import(self) -> None:
        raw = self.path_entry.get().strip()
        if not raw:
            self.app.set_status("Choose a capsule file first", kind="warning")
            return
        path = Path(raw)
        if not path.exists():
            self.app.set_status(f"File not found: {path}", kind="error")
            return

        self.app.set_status("Validating and importing…")
        run_in_background(self, lambda: import_capsule(self.db, path), self._imported, self._failed)

    def _failed(self, error: Exception) -> None:
        message = str(error) if isinstance(error, ImportError_) else f"Import failed: {error}"
        logger.info("Import rejected: %s", message)
        self.app.set_status(message, kind="error")
        self._render_error(message)

    def _render_error(self, message: str) -> None:
        self.result_card.pack(fill="x", pady=(0, 12), padx=6)
        for child in self.result_body.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.result_body,
            text=message,
            font=font(11),
            text_color=COLORS["danger"],
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x")

    def _imported(self, result) -> None:
        self.result_card.pack(fill="x", pady=(0, 12), padx=6)
        for child in self.result_body.winfo_children():
            child.destroy()

        document = result.document
        project = document.get("project") or {}
        compression = document.get("compression") or {}

        ctk.CTkLabel(
            self.result_body,
            text=project.get("name") or result.title,
            font=font(14, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            self.result_body,
            text=(
                f"{compression.get('mode')} compression · "
                f"~{compression.get('capsule_tokens', 0):,} tokens · "
                f"{len(result.attachments)} attachment(s)"
            ),
            font=font(10),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", pady=(2, 6))

        for warning in result.warnings:
            ctk.CTkLabel(
                self.result_body,
                text=f"⚠  {warning}",
                font=font(10),
                text_color=COLORS["warning"],
                anchor="w",
                justify="left",
                wraplength=800,
            ).pack(fill="x", pady=1)

        actions = ctk.CTkFrame(self.result_body, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        primary_button(
            actions,
            "Resume this capsule",
            lambda: self._resume(result.capsule_id),
            height=32,
        ).pack(side="left")
        ghost_button(actions, "View library", lambda: self.app.navigate("capsules"), height=32).pack(
            side="left", padx=8
        )

        self.app.set_status(f"Imported “{result.title}”", kind="success")

    def _resume(self, capsule_id: str) -> None:
        self.app.navigate("resume")
        page = self.app.pages.get("resume")
        if page is not None and hasattr(page, "focus_capsule"):
            page.focus_capsule(capsule_id)
