"""Capture Conversation: paste or import, preview, then save a draft capsule.

Everything shown in the preview comes from the parser result.  Nothing is saved
until the user presses "Save draft capsule".
"""

from __future__ import annotations

import logging
from pathlib import Path
import tkinter.filedialog as filedialog

import customtkinter as ctk

from config import SUPPORTED_AI_PLATFORMS
from core.capture_engine import CaptureEngine
from core.parser_engine import ParseError, ParseResult
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import (
    Badge,
    Card,
    KeyValueRow,
    ghost_button,
    primary_button,
    text_box,
)
from gui.workers import run_in_background

logger = logging.getLogger(__name__)

ROLE_COLORS = {"user": COLORS["accent"], "assistant": COLORS["violet"], "system": COLORS["warning"]}


class CapturePage(BasePage):
    page_key = "capture"
    title = "Capture Conversation"
    subtitle = "Paste a transcript or import a file, review the parse, then save"

    def build(self) -> None:
        self.engine = CaptureEngine(self.db)
        self._result: ParseResult | None = None
        self._mode = "paste"

        source = Card(self.body, "Source", "Nothing is stored until you save", padding=18, accent=COLORS["accent"])
        source.pack(fill="x", pady=(0, 12), padx=6)

        controls = ctk.CTkFrame(source.body, fg_color="transparent")
        controls.pack(fill="x")

        self.mode_switch = ctk.CTkSegmentedButton(
            controls,
            values=["Paste text", "Import file"],
            command=self._on_mode_change,
            height=32,
            corner_radius=9,
            font=font(12),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            unselected_color=COLORS["panel_alt"],
            unselected_hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
        )
        self.mode_switch.set("Paste text")
        self.mode_switch.pack(side="left")

        ctk.CTkLabel(
            controls, text="Platform", font=font(11), text_color=COLORS["text_muted"]
        ).pack(side="left", padx=(20, 8))

        self.platform_menu = ctk.CTkOptionMenu(
            controls,
            values=["Auto-detect", *SUPPORTED_AI_PLATFORMS],
            height=32,
            corner_radius=9,
            font=font(11),
            dropdown_font=font(11),
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            width=170,
        )
        self.platform_menu.set("Auto-detect")
        self.platform_menu.pack(side="left")

        # -- input area (paste / file) ---------------------------------------
        self.input_container = ctk.CTkFrame(source.body, fg_color="transparent")
        self.input_container.pack(fill="x", pady=(14, 0))

        self.paste_frame = ctk.CTkFrame(self.input_container, fg_color="transparent")
        self.paste_frame.pack(fill="x")
        self.text_input = text_box(self.paste_frame, height=220)
        self.text_input.pack(fill="x")

        self.file_frame = ctk.CTkFrame(self.input_container, fg_color="transparent")
        file_row = ctk.CTkFrame(self.file_frame, fg_color="transparent")
        file_row.pack(fill="x")
        self.file_entry = ctk.CTkEntry(
            file_row,
            placeholder_text="No file selected — TXT, Markdown or JSON",
            height=36,
            corner_radius=10,
            fg_color=COLORS["bg"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=font(11),
        )
        self.file_entry.pack(side="left", fill="x", expand=True)
        ghost_button(file_row, "Browse…", self._browse, height=36, width=110).pack(side="left", padx=8)

        actions = ctk.CTkFrame(source.body, fg_color="transparent")
        actions.pack(fill="x", pady=(12, 0))
        primary_button(actions, "Analyse capture", self._analyse, height=36).pack(side="left")
        ghost_button(actions, "Clear", self._clear, height=36).pack(side="left", padx=8)

        self.source_hint = ctk.CTkLabel(
            actions,
            text="Paste a full conversation including role labels such as “User:” and “Assistant:”.",
            font=font(10),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self.source_hint.pack(side="left", padx=12)

        # -- preview ---------------------------------------------------------
        self.preview_card = Card(
            self.body, "Preview", "Parsed from the capture above", padding=18, accent=COLORS["success"]
        )
        self.preview_card.pack(fill="x", pady=(12, 12), padx=6)
        self.preview_body = ctk.CTkFrame(self.preview_card.body, fg_color="transparent")
        self.preview_body.pack(fill="x", pady=(14, 0))

        self.placeholder = ctk.CTkLabel(
            self.preview_card.body,
            text="No capture analysed yet. The parsed messages, code blocks and platform confidence will appear here.",
            font=font(11),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=820,
        )
        self.placeholder.pack(fill="x", pady=(12, 0))

        self.save_button = primary_button(
            self.body, "Save draft capsule", self._save, height=38, state="disabled"
        )
        self.save_button.pack(anchor="w", padx=12, pady=(0, 20))

    # ------------------------------------------------------------------ #
    # UI events
    # ------------------------------------------------------------------ #
    def _on_mode_change(self, value: str) -> None:
        self._mode = "file" if value == "Import file" else "paste"
        if self._mode == "file":
            self.paste_frame.pack_forget()
            self.file_frame.pack(fill="x")
            self.source_hint.configure(text="JSON conversation exports keep roles and code blocks intact.")
        else:
            self.file_frame.pack_forget()
            self.paste_frame.pack(fill="x")
            self.source_hint.configure(
                text="Paste a full conversation including role labels such as “User:” and “Assistant:”."
            )

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a conversation export",
            filetypes=[
                ("Conversation files", "*.txt *.md *.markdown *.json"),
                ("Text", "*.txt"),
                ("Markdown", "*.md *.markdown"),
                ("JSON", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, path)

    def _platform_hint(self) -> str | None:
        value = self.platform_menu.get()
        return None if value == "Auto-detect" else value

    def _clear(self) -> None:
        self.text_input.delete("1.0", "end")
        self.file_entry.delete(0, "end")
        self._result = None
        self.save_button.configure(state="disabled")
        for child in self.preview_body.winfo_children():
            child.destroy()
        self.placeholder.pack(fill="x", pady=(12, 0))
        self.app.set_status("Capture cleared")

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #
    def _analyse(self) -> None:
        hint = self._platform_hint()
        if self._mode == "file":
            raw_path = self.file_entry.get().strip()
            if not raw_path:
                self.app.set_status("Choose a file first", kind="warning")
                return
            if not Path(raw_path).exists():
                self.app.set_status(f"File not found: {raw_path}", kind="error")
                return
            task = lambda: self.engine.analyze_file(raw_path, platform_hint=hint)  # noqa: E731
        else:
            text = self.text_input.get("1.0", "end").strip()
            if not text:
                self.app.set_status("Paste a conversation first", kind="warning")
                return
            task = lambda: self.engine.analyze_text(text, platform_hint=hint)  # noqa: E731

        self.app.set_status("Parsing capture…")
        self.save_button.configure(state="disabled")
        run_in_background(self, task, self._analysed, self._analyse_failed)

    def _analyse_failed(self, error: Exception) -> None:
        logger.info("Capture analysis rejected: %s", error)
        message = str(error) if isinstance(error, ParseError) else f"Unexpected parser error: {error}"
        self.app.set_status(message, kind="error")
        self.placeholder.configure(text=message, text_color=COLORS["danger"])

    def _analysed(self, result: ParseResult) -> None:
        self._result = result
        self._render_preview(result)
        self.save_button.configure(state="normal")
        self.app.set_status(
            f"Parsed {result.message_count} message(s) from {result.platform}", kind="success"
        )

    def _render_preview(self, result: ParseResult) -> None:
        self.placeholder.pack_forget()
        for child in self.preview_body.winfo_children():
            child.destroy()

        header = ctk.CTkFrame(self.preview_body, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(
            header,
            text=result.title,
            font=font(14, "bold"),
            text_color=COLORS["text"],
            anchor="w",
            wraplength=560,
            justify="left",
        ).pack(side="left", fill="x", expand=True)

        confidence_color = {
            "high": COLORS["success"],
            "medium": COLORS["warning"],
            "low": COLORS["danger"],
        }.get(result.platform_confidence, COLORS["text_dim"])
        Badge(
            header,
            f"{result.platform} · {result.platform_confidence} confidence",
            color=confidence_color,
        ).pack(side="right")

        facts = KeyValueRow(self.preview_body, "Volume", result.summary_line)
        facts.pack(fill="x", pady=(10, 2))
        roles = ", ".join(f"{role}: {count}" for role, count in result.roles.items())
        KeyValueRow(self.preview_body, "Roles", roles).pack(fill="x", pady=2)
        KeyValueRow(
            self.preview_body,
            "Code blocks",
            f"{len(result.code_blocks)} detected"
            + (f" ({', '.join(sorted({b.language for b in result.code_blocks}))})" if result.code_blocks else ""),
        ).pack(fill="x", pady=2)
        KeyValueRow(self.preview_body, "Platform reason", result.platform_reason).pack(fill="x", pady=2)
        if result.source_name:
            KeyValueRow(self.preview_body, "Source file", result.source_name).pack(fill="x", pady=2)

        if result.warnings:
            warn = ctk.CTkFrame(
                self.preview_body,
                fg_color=COLORS["warning_soft"],
                corner_radius=10,
                border_width=1,
                border_color=COLORS["warning"],
            )
            warn.pack(fill="x", pady=(10, 4))
            for warning in result.warnings:
                ctk.CTkLabel(
                    warn,
                    text=f"⚠  {warning}",
                    font=font(10),
                    text_color=COLORS["warning"],
                    anchor="w",
                    justify="left",
                    wraplength=780,
                ).pack(fill="x", padx=12, pady=(6, 2))

        ctk.CTkLabel(
            self.preview_body,
            text="MESSAGES",
            font=font(9, "bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", pady=(12, 4))

        for message in result.messages[:12]:
            self._message_row(message)

        if len(result.messages) > 12:
            ctk.CTkLabel(
                self.preview_body,
                text=f"+ {len(result.messages) - 12} more message(s) stored in full but not previewed here.",
                font=font(10),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).pack(fill="x", pady=(4, 0))

    def _message_row(self, message) -> None:
        row = ctk.CTkFrame(
            self.preview_body,
            fg_color=COLORS["panel_alt"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
        )
        row.pack(fill="x", pady=3)

        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(7, 0))
        ctk.CTkLabel(
            top,
            text=message.role.upper(),
            font=font(9, "bold"),
            text_color=ROLE_COLORS.get(message.role, COLORS["text_dim"]),
            anchor="w",
        ).pack(side="left")
        if message.contains_code:
            Badge(top, "code", color=COLORS["success"]).pack(side="right")

        preview = message.content.strip()
        if len(preview) > 320:
            preview = preview[:320] + "…"
        ctk.CTkLabel(
            row,
            text=preview,
            font=font(10),
            text_color=COLORS["text_dim"],
            anchor="w",
            justify="left",
            wraplength=800,
        ).pack(fill="x", padx=12, pady=(2, 8))

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #
    def _save(self) -> None:
        if self._result is None:
            self.app.set_status("Analyse a capture first", kind="warning")
            return
        result = self._result
        self.save_button.configure(state="disabled")
        self.app.set_status("Saving capsule…")
        run_in_background(
            self,
            lambda: self.engine.save_draft(result),
            lambda capsule_id: self._saved(capsule_id, result),
            self._save_failed,
        )

    def _saved(self, capsule_id: str, result: ParseResult) -> None:
        self.placeholder.pack_forget()
        self.app.set_status(
            f"Draft capsule saved · {result.message_count} messages and "
            f"{len(result.code_blocks)} code blocks",
            kind="success",
        )
        self._result = None
        self.save_button.configure(state="disabled")
        for child in self.preview_body.winfo_children():
            child.destroy()

        done = ctk.CTkFrame(self.preview_body, fg_color="transparent")
        done.pack(fill="x", pady=8)
        ctk.CTkLabel(
            done,
            text=f"Saved “{result.title}”. Context extraction (Phase 3) will structure this draft.",
            font=font(12),
            text_color=COLORS["success"],
            anchor="w",
            justify="left",
            wraplength=600,
        ).pack(side="left", fill="x", expand=True)
        primary_button(done, "Open My Capsules", lambda: self.app.navigate("capsules"), height=32).pack(
            side="right"
        )
        self.text_input.delete("1.0", "end")
        self.file_entry.delete(0, "end")

    def _save_failed(self, error: Exception) -> None:
        logger.exception("Saving capture failed")
        self.save_button.configure(state="normal")
        self.app.set_status(f"Could not save capsule: {error}", kind="error")
