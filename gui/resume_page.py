"""Resume Project: pick a capsule, choose a destination, carry the context over."""

from __future__ import annotations

import logging
import webbrowser
import tkinter.filedialog as filedialog
from pathlib import Path

import customtkinter as ctk

from core.resume_engine import DESTINATION_URLS, DESTINATIONS, continuation_prompt, context_brief
from database.models import Capsule
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Card, ghost_button, primary_button, text_box
from gui.workers import run_in_background

logger = logging.getLogger(__name__)


class ResumePage(BasePage):
    page_key = "resume"
    title = "Resume Project"
    subtitle = "Carry the working state forward — not hidden platform memory"

    def build(self) -> None:
        self._capsules: dict[str, Capsule] = {}
        self._document: dict | None = None
        self._brief: str = ""
        self._prompt: str = ""

        ghost_button(self.header_actions, "↻  Refresh", self._load_capsules).pack(side="right")

        selector = Card(self.body, "Choose a capsule", "Capsules with extracted context", padding=18, accent=COLORS["accent"])
        selector.pack(fill="x", pady=(0, 12), padx=6)

        row = ctk.CTkFrame(selector.body, fg_color="transparent")
        row.pack(fill="x")

        self.capsule_menu = ctk.CTkOptionMenu(
            row,
            values=["No capsules"],
            height=34,
            corner_radius=9,
            font=font(11),
            dropdown_font=font(11),
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            width=430,
            command=lambda _value: self._load_selected(),
        )
        self.capsule_menu.pack(side="left")

        self.destination_menu = ctk.CTkOptionMenu(
            row,
            values=list(DESTINATIONS),
            height=34,
            corner_radius=9,
            font=font(11),
            dropdown_font=font(11),
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["violet"],
            button_hover_color=COLORS["violet"],
            text_color=COLORS["text"],
            width=150,
            command=lambda _value: self._rebuild_prompt(),
        )
        self.destination_menu.set("ChatGPT")
        self.destination_menu.pack(side="left", padx=8)

        primary_button(row, "Load", self._load_selected, height=34).pack(side="left")

        self.load_hint = ctk.CTkLabel(
            selector.body,
            text="A capsule is required before a prompt can be generated.",
            font=font(11),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=800,
        )
        self.load_hint.pack(fill="x", pady=(10, 0))

        overview = Card(self.body, "Project overview", "What the destination assistant will receive", padding=18)
        overview.pack(fill="x", pady=(0, 12), padx=6)
        self.overview_body = ctk.CTkFrame(overview.body, fg_color="transparent")
        self.overview_body.pack(fill="x")

        prompt_card = Card(
            self.body,
            "Continuation prompt",
            "Paste this into the destination assistant",
            padding=18,
            accent=COLORS["success"],
        )
        prompt_card.pack(fill="x", pady=(0, 12), padx=6)
        self.prompt_box = text_box(prompt_card.body, height=260)
        self.prompt_box.pack(fill="x")

        actions = ctk.CTkFrame(prompt_card.body, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        primary_button(actions, "Copy prompt", self._copy_prompt, height=34).pack(side="left")
        ghost_button(actions, "Copy context brief", self._copy_brief, height=34).pack(side="left", padx=8)
        ghost_button(actions, "Export prompt", self._export_prompt, height=34).pack(side="left")
        ghost_button(actions, "Open destination AI", self._open_destination, height=34).pack(side="left", padx=8)
        ghost_button(actions, "Manage capsules", lambda: self.app.navigate("capsules"), height=34).pack(side="left")

        self._load_capsules()

    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self._load_capsules()

    def focus_capsule(self, capsule_id: str) -> None:
        """Select a specific capsule (used from the library screen)."""
        self._load_capsules(preferred=capsule_id)

    def _load_capsules(self, preferred: str | None = None) -> None:
        try:
            capsules = self.db.list_capsules(limit=200)
        except Exception as exc:  # noqa: BLE001
            self.app.set_status(f"Could not read capsules: {exc}", kind="error")
            return

        usable = [capsule for capsule in capsules if not capsule.payload().get("draft")]
        self._capsules = {f"{capsule.title[:58]} · {capsule.source_platform}": capsule for capsule in usable}

        if not usable:
            self.capsule_menu.configure(values=["No capsules"])
            self.capsule_menu.set("No capsules")
            self.load_hint.configure(
                text="No generated capsules yet. Create one from a captured conversation to build a handoff.",
                text_color=COLORS["text_muted"],
            )
            self._clear()
            return

        labels = list(self._capsules)
        self.capsule_menu.configure(values=labels)
        chosen = labels[0]
        if preferred:
            chosen = next(
                (label for label, capsule in self._capsules.items() if capsule.id == preferred), labels[0]
            )
        self.capsule_menu.set(chosen)
        self.load_hint.configure(
            text=f"{len(labels)} capsule(s) available. Choose a destination to tailor the prompt.",
            text_color=COLORS["text_muted"],
        )
        self._load_selected()

    def _selected(self) -> Capsule | None:
        return self._capsules.get(self.capsule_menu.get())

    def _clear(self) -> None:
        self._document = None
        self.prompt_box.delete("1.0", "end")
        for child in self.overview_body.winfo_children():
            child.destroy()

    # ------------------------------------------------------------------ #
    def _load_selected(self) -> None:
        capsule = self._selected()
        if capsule is None:
            self._clear()
            return

        def task():
            document = capsule.payload()
            return capsule, document

        run_in_background(self, task, self._loaded, self._load_failed)

    def _load_failed(self, error: Exception) -> None:
        logger.exception("Loading capsule failed")
        self.app.set_status(f"Could not load capsule: {error}", kind="error")

    def _loaded(self, payload) -> None:
        capsule, document = payload
        self._document = document
        self._brief = context_brief(document)
        self._rebuild_prompt()
        self._render_overview(capsule, document)
        self.app.set_status(f"Loaded “{capsule.title}”", kind="success")

    def _render_overview(self, capsule: Capsule, document: dict) -> None:
        project = document.get("project") or {}
        progress = document.get("progress") or {}
        compression = document.get("compression") or {}

        for child in self.overview_body.winfo_children():
            child.destroy()

        rows = (
            ("Project", project.get("name") or capsule.title),
            ("Objective", project.get("objective") or "not stated"),
            ("Stage", f"{project.get('stage')} (inferred)"),
            ("Next action", progress.get("next_action") or "not recorded"),
            ("Pending tasks", str(len(progress.get("pending") or []))),
            ("Unresolved errors", str(sum(1 for item in progress.get("errors") or [] if not item.get("resolved")))),
            ("Compression", f"{compression.get('mode')} · ~{compression.get('capsule_tokens', 0):,} tokens"),
        )
        for label, value in rows:
            line = ctk.CTkFrame(self.overview_body, fg_color="transparent")
            line.pack(fill="x", pady=2)
            ctk.CTkLabel(
                line, text=label, font=font(11), text_color=COLORS["text_muted"], width=130, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                line,
                text=str(value),
                font=font(11),
                text_color=COLORS["text"],
                anchor="w",
                justify="left",
                wraplength=640,
            ).pack(side="left", fill="x", expand=True)

    def _rebuild_prompt(self) -> None:
        if self._document is None:
            return
        destination = self.destination_menu.get()
        self._prompt = continuation_prompt(self._document, destination)
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", self._prompt)

    # ------------------------------------------------------------------ #
    def _copy(self, text: str, message: str) -> None:
        if not text:
            self.app.set_status("Load a capsule first", kind="warning")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.set_status(message, kind="success")

    def _copy_prompt(self) -> None:
        self._rebuild_prompt()
        self._copy(self._prompt, f"Continuation prompt copied for {self.destination_menu.get()}")

    def _copy_brief(self) -> None:
        self._brief = context_brief(self._document) if self._document else ""
        self._copy(self._brief, "Context brief copied")

    def _export_prompt(self) -> None:
        if not self._document:
            self.app.set_status("Load a capsule first", kind="warning")
            return
        path = filedialog.asksaveasfilename(
            title="Export continuation prompt",
            defaultextension=".txt",
            initialfile="continuation_prompt.txt",
            filetypes=[("Text", "*.txt"), ("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            target = Path(path)
            body = self._prompt or continuation_prompt(self._document, self.destination_menu.get())
            target.write_text(body, encoding="utf-8")
        except OSError as exc:
            self.app.set_status(f"Export failed: {exc}", kind="error")
            return
        self.app.set_status(f"Prompt exported to {target.name}", kind="success")

    def _open_destination(self) -> None:
        url = DESTINATION_URLS.get(self.destination_menu.get(), "")
        if not url:
            self.app.set_status("No destination URL for this option", kind="warning")
            return
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Could not open browser")
            self.app.set_status(f"Could not open browser: {exc}", kind="error")
