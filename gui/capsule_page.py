"""Create Capsule: generate a structured capsule from a capture and review it.

Flow: pick a captured draft → generate (extract + compress) → edit the key fields
→ save a new version → export or resume. All heavy work runs on a worker thread.
"""

from __future__ import annotations

import logging
from pathlib import Path
import tkinter.filedialog as filedialog

import customtkinter as ctk

from config import CAPSULE_EXTENSION, COMPRESSION_MODES
from core.capture_engine import CaptureEngine
from core.capsule_generator import generate_capsule
from core.parser_engine import ParseResult
from database.models import Capsule
from exporters import FORMATS, SUFFIXES, export_document
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Card, ghost_button, primary_button, text_box
from gui.workers import run_in_background

logger = logging.getLogger(__name__)

MODE_LABELS = {
    "balanced": "Balanced",
    "high": "High compression",
    "full": "Full preservation",
}


class CapsulePage(BasePage):
    page_key = "create_capsule"
    title = "Create Capsule"
    subtitle = "Capture once → organize → compress → export → continue anywhere"

    def build(self) -> None:
        self.engine = CaptureEngine(self.db)
        self._drafts: dict[str, Capsule] = {}
        self._result: ParseResult | None = None
        self._capsule_id: str | None = None
        self._document: dict | None = None

        ghost_button(self.header_actions, "↻  Refresh", self._refresh_drafts).pack(side="right")

        source = Card(
            self.body,
            "Source capture",
            "Draft capsules waiting for context extraction",
            padding=18,
            accent=COLORS["accent"],
        )
        source.pack(fill="x", pady=(0, 12), padx=6)

        row = ctk.CTkFrame(source.body, fg_color="transparent")
        row.pack(fill="x")
        self.draft_menu = ctk.CTkOptionMenu(
            row,
            values=["No capture drafts"],
            height=34,
            corner_radius=9,
            font=font(11),
            dropdown_font=font(11),
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            dynamic_resizing=False,
            width=420,
        )
        self.draft_menu.pack(side="left")

        self.mode_menu = ctk.CTkOptionMenu(
            row,
            values=[MODE_LABELS[mode] for mode in COMPRESSION_MODES],
            height=34,
            corner_radius=9,
            font=font(11),
            dropdown_font=font(11),
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["violet"],
            button_hover_color=COLORS["violet"],
            text_color=COLORS["text"],
            width=170,
        )
        default_mode = self.db.get_setting("default_compression", "balanced")
        self.mode_menu.set(MODE_LABELS.get(default_mode, MODE_LABELS["balanced"]))
        self.mode_menu.pack(side="left", padx=8)

        primary_button(row, "Generate capsule", self._generate, height=34).pack(side="left")

        self.source_hint = ctk.CTkLabel(
            source.body,
            text="",
            font=font(11),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=800,
        )
        self.source_hint.pack(fill="x", pady=(10, 0))

        # -- review ----------------------------------------------------------
        self.review = Card(
            self.body,
            "Review",
            "Edit anything before it becomes part of the capsule",
            padding=18,
            accent=COLORS["success"],
        )
        self.review_body = ctk.CTkFrame(self.review.body, fg_color="transparent")

        self.fields: dict[str, ctk.CTkEntry] = {}
        for key, label in (
            ("name", "Project name"),
            ("objective", "Objective"),
            ("next_action", "Next action"),
        ):
            ctk.CTkLabel(
                self.review_body, text=label.upper(), font=font(9, "bold"), text_color=COLORS["text_muted"], anchor="w"
            ).pack(fill="x", pady=(8, 3))
            entry = ctk.CTkEntry(
                self.review_body,
                height=34,
                corner_radius=9,
                fg_color=COLORS["bg"],
                border_color=COLORS["border"],
                text_color=COLORS["text"],
                font=font(11),
            )
            entry.pack(fill="x")
            self.fields[key] = entry

        ctk.CTkLabel(
            self.review_body,
            text="SUMMARY",
            font=font(9, "bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", pady=(10, 3))
        self.summary_box = text_box(self.review_body, height=120)
        self.summary_box.pack(fill="x")

        self.review_meta = ctk.CTkLabel(
            self.review_body,
            text="",
            font=font(10),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=820,
        )
        self.review_meta.pack(fill="x", pady=(8, 0))

        actions = ctk.CTkFrame(self.review_body, fg_color="transparent")
        actions.pack(fill="x", pady=(12, 0))
        primary_button(actions, "Save changes", self._save_edits, height=34).pack(side="left")
        ghost_button(actions, "Open resume screen", lambda: self.app.navigate("resume"), height=34).pack(
            side="left", padx=8
        )

        exports = ctk.CTkFrame(self.review_body, fg_color="transparent")
        exports.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(
            exports, text="EXPORT", font=font(9, "bold"), text_color=COLORS["text_muted"]
        ).pack(side="left", padx=(0, 8))
        for fmt, label in FORMATS.items():
            ghost_button(
                exports, label if fmt != "scapsule" else CAPSULE_EXTENSION, lambda f=fmt: self._export(f), height=30
            ).pack(side="left", padx=(0, 6))

        self._refresh_drafts()

    def on_show(self) -> None:
        self._refresh_drafts()

    # ------------------------------------------------------------------ #
    def _refresh_drafts(self) -> None:
        try:
            capsules = self.db.list_capsules(limit=200)
        except Exception as exc:  # noqa: BLE001
            self.app.set_status(f"Could not read captures: {exc}", kind="error")
            return

        self._drafts = {
            f"{capsule.title[:58]} · {capsule.source_platform}": capsule
            for capsule in capsules
            if capsule.payload().get("draft")
        }
        if self._drafts:
            labels = list(self._drafts)
            self.draft_menu.configure(values=labels)
            current = self.draft_menu.get()
            self.draft_menu.set(current if current in labels else labels[0])
            self.source_hint.configure(
                text=f"{len(labels)} draft capture(s) available. Choose one and generate its capsule.",
                text_color=COLORS["text_muted"],
            )
        else:
            self.draft_menu.configure(values=["No capture drafts"])
            self.draft_menu.set("No capture drafts")
            self.source_hint.configure(
                text="No drafts yet — capture a conversation first, then return here to generate the capsule.",
                text_color=COLORS["text_muted"],
            )

    def _selected_draft(self) -> Capsule | None:
        label = self.draft_menu.get()
        capsule = self._drafts.get(label)
        if capsule is None:
            self.app.set_status("Capture a conversation first", kind="warning")
        return capsule

    def _mode(self) -> str:
        label = self.mode_menu.get()
        return next((key for key, text in MODE_LABELS.items() if text == label), "balanced")

    # ------------------------------------------------------------------ #
    def _generate(self) -> None:
        capsule = self._selected_draft()
        if capsule is None:
            return

        self.app.set_status("Extracting context and compressing…")
        mode = self._mode()

        def task():
            result = self.engine.rebuild_result(capsule)
            conversation_id = self.engine.conversation_id_for(capsule)
            capsule_id, document = generate_capsule(
                self.db,
                result,
                capsule_id=capsule.id,
                mode=mode,
                conversation_id=conversation_id,
            )
            return result, document, capsule_id

        run_in_background(self, task, self._generated, self._generate_failed)

    def _generate_failed(self, error: Exception) -> None:
        logger.exception("Capsule generation failed")
        self.app.set_status(f"Generation failed: {error}", kind="error")

    def _generated(self, payload) -> None:
        result, document, capsule_id = payload
        self._result = result
        self._document = document
        self._capsule_id = capsule_id

        project = document.get("project") or {}
        progress = document.get("progress") or {}
        compression = document.get("compression") or {}

        self.fields["name"].delete(0, "end")
        self.fields["name"].insert(0, str(project.get("name") or ""))
        self.fields["objective"].delete(0, "end")
        self.fields["objective"].insert(0, str(project.get("objective") or ""))
        self.fields["next_action"].delete(0, "end")
        self.fields["next_action"].insert(0, str(progress.get("next_action") or ""))

        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", str(document.get("summary") or ""))

        self.review_meta.configure(
            text=(
                f"{compression.get('mode')} compression · ~{compression.get('capsule_tokens', 0):,} capsule "
                f"tokens vs ~{compression.get('original_tokens', 0):,} original "
                f"({compression.get('token_method')}). "
                f"{len(document.get('code') or [])} code block(s), "
                f"{len((progress.get('pending') or []))} pending task(s), "
                f"{len((progress.get('errors') or []))} error(s) recorded."
            ),
            text_color=COLORS["text_muted"],
        )

        self.review.pack(fill="x", pady=(0, 12), padx=6)
        self.app.set_status(f"Capsule generated for “{project.get('name')}”", kind="success")

    def _save_edits(self) -> None:
        if self._result is None or self._capsule_id is None:
            self.app.set_status("Generate a capsule first", kind="warning")
            return

        overrides = {
            "name": self.fields["name"].get().strip(),
            "objective": self.fields["objective"].get().strip(),
            "next_action": self.fields["next_action"].get().strip(),
        }
        mode = self._mode()
        result = self._result
        capsule_id = self._capsule_id
        self.app.set_status("Saving new capsule version…")

        def task():
            new_id_, document = generate_capsule(
                self.db, result, capsule_id=capsule_id, mode=mode, overrides=overrides
            )
            return new_id_, document

        run_in_background(self, task, self._edits_saved, self._generate_failed)

    def _edits_saved(self, payload) -> None:
        capsule_id, document = payload
        self._document = document
        self._capsule_id = capsule_id
        self.app.set_status("Capsule updated · new version stored", kind="success")
        self._refresh_drafts()

    # ------------------------------------------------------------------ #
    def _export(self, fmt: str) -> None:
        if not self._document:
            self.app.set_status("Generate a capsule before exporting", kind="warning")
            return

        suffix = SUFFIXES[fmt]
        path = filedialog.asksaveasfilename(
            title=f"Export {FORMATS[fmt]}",
            defaultextension=suffix,
            initialfile=f"smart_capsule{suffix}",
            filetypes=[(FORMATS[fmt], f"*{suffix}"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            written = export_document(self._document, Path(path), fmt)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Export failed")
            self.app.set_status(f"Export failed: {exc}", kind="error")
            return
        self.app.set_status(f"Exported {written.name}", kind="success")
