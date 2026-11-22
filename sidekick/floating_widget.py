"""Always-available floating assistant window.

Compact by default, draggable, optionally always-on-top, and intentionally thin:
it renders status and dispatches actions. All heavy work is delegated to the
shared core engines on a worker thread, so the widget never freezes.
"""

from __future__ import annotations

import logging

import customtkinter as ctk

from config import APP_NAME, VERSION
from gui.theme import COLORS, RADIUS, font, icon_font
from gui.workers import run_in_background
from sidekick import quick_actions

logger = logging.getLogger(__name__)


class FloatingSidekick(ctk.CTkToplevel):
    """Compact context assistant that stays above the user's work."""

    WIDTH = 316

    def __init__(self, app, on_hide=None) -> None:
        super().__init__(app)
        self.app = app
        self.db = app.db
        self._on_hide = on_hide

        self.withdraw()
        self.title(f"{APP_NAME} Sidekick")
        self.configure(fg_color=COLORS["bg"])
        self.resizable(False, False)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.hide)

        self._expanded = not self.db.get_bool_setting("sidekick_compact", True)
        self._drag_origin: tuple[int, int] | None = None
        self._status_job: str | None = None

        self._build()
        self._apply_preferences()
        self._refresh_status()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        outer = ctk.CTkFrame(self, fg_color=COLORS["sidebar"], corner_radius=16, border_width=1, border_color=COLORS["border"])
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        self.outer = outer

        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 6))
        self._header = header
        for widget in (header,):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        mark = ctk.CTkFrame(header, fg_color=COLORS["accent"], corner_radius=9, width=28, height=28)
        mark.pack(side="left")
        mark.pack_propagate(False)
        ctk.CTkLabel(mark, text="◈", font=icon_font(13), text_color="#FFFFFF").place(relx=0.5, rely=0.5, anchor="center")

        title = ctk.CTkFrame(header, fg_color="transparent")
        title.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            title, text="SMART CAPSULE", font=font(10, "bold"), text_color=COLORS["text"], anchor="w"
        ).pack(anchor="w")

        self._drag_handles = [header, mark, title]
        for widget in self._drag_handles:
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        ctk.CTkButton(
            header,
            text="×",
            width=24,
            height=24,
            corner_radius=8,
            font=font(13, "bold"),
            fg_color="transparent",
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text_muted"],
            command=self.hide,
        ).pack(side="right")

        self._mode_button = ctk.CTkButton(
            header,
            text="▾",
            width=24,
            height=24,
            corner_radius=8,
            font=font(11),
            fg_color="transparent",
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text_muted"],
            command=self.toggle_compact,
        )
        self._mode_button.pack(side="right", padx=(0, 2))

        # -- context block ------------------------------------------------
        context = ctk.CTkFrame(outer, fg_color=COLORS["panel"], corner_radius=12)
        context.pack(fill="x", padx=10, pady=(0, 8))
        inner = ctk.CTkFrame(context, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(
            inner, text="ACTIVE PROJECT", font=font(8, "bold"), text_color=COLORS["text_muted"], anchor="w"
        ).pack(fill="x")
        self.project_label = ctk.CTkLabel(
            inner,
            text="No capsule yet",
            font=font(12, "bold"),
            text_color=COLORS["text"],
            anchor="w",
            wraplength=260,
            justify="left",
        )
        self.project_label.pack(fill="x")

        self.meta_label = ctk.CTkLabel(
            inner, text="Capture a conversation to begin", font=font(9), text_color=COLORS["text_muted"], anchor="w"
        )
        self.meta_label.pack(fill="x", pady=(2, 0))

        # -- quick actions -------------------------------------------------
        self.actions = ctk.CTkFrame(outer, fg_color="transparent")
        self.actions.pack(fill="x", padx=10)
        actions = (
            ("⌁  Capture clipboard", self._capture_clipboard, COLORS["accent"]),
            ("⚡  Quick save capsule", self._quick_save, COLORS["violet"]),
            ("▸  Copy continuation prompt", self._copy_prompt, COLORS["success"]),
            ("▤  Search capsules", lambda: self._open_app("capsules"), COLORS["text_dim"]),
            ("⇩  Import capsule", lambda: self._open_app("import"), COLORS["warning"]),
            ("◈  Open main app", lambda: self._open_app(None), COLORS["accent"]),
        )
        self._action_buttons: list[ctk.CTkButton] = []
        for index, (label, command, color) in enumerate(actions):
            button = ctk.CTkButton(
                self.actions,
                text=label,
                anchor="w",
                height=30,
                corner_radius=9,
                font=font(11),
                fg_color=COLORS["panel"],
                hover_color=COLORS["panel_hover"],
                text_color=color,
                border_width=1,
                border_color=COLORS["border_soft"],
                command=command,
            )
            button.grid(row=index, column=0, sticky="ew", pady=2)
            self._action_buttons.append(button)
        self.actions.grid_columnconfigure(0, weight=1)

        # -- compact row (hidden when expanded) ----------------------------
        self.compact_actions = ctk.CTkFrame(outer, fg_color="transparent")
        for index, (label, command) in enumerate(
            (("⌁ Capture", self._capture_clipboard), ("⚡ Save", self._quick_save), ("▸ Prompt", self._copy_prompt))
        ):
            self.compact_actions.grid_columnconfigure(index, weight=1, uniform="compact")
            ctk.CTkButton(
                self.compact_actions,
                text=label,
                height=30,
                corner_radius=9,
                font=font(10, "bold"),
                fg_color=COLORS["panel"],
                hover_color=COLORS["panel_hover"],
                text_color=COLORS["text_dim"],
                border_width=1,
                border_color=COLORS["border_soft"],
                command=command,
            ).grid(row=0, column=index, sticky="ew", padx=2)

        # -- footer --------------------------------------------------------
        footer = ctk.CTkFrame(outer, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=(8, 10))
        self.status_label = ctk.CTkLabel(
            footer,
            text="Idle",
            font=font(9),
            text_color=COLORS["text_muted"],
            anchor="w",
            wraplength=210,
            justify="left",
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        self.gpu_label = ctk.CTkLabel(
            footer, text="CPU", font=font(9, "bold"), text_color=COLORS["text_muted"], anchor="e"
        )
        self.gpu_label.pack(side="right")

        self.after(0, self._apply_compact_state)

    # ------------------------------------------------------------------ #
    # Window behaviour
    # ------------------------------------------------------------------ #
    def _apply_preferences(self) -> None:
        topmost = self.db.get_bool_setting("sidekick_always_on_top", True)
        try:
            self.attributes("-topmost", topmost)
        except Exception:  # pragma: no cover - platform dependent
            logger.debug("topmost unsupported", exc_info=True)

        try:
            opacity = float(self.db.get_setting("sidekick_opacity", "0.97"))
            self.attributes("-alpha", max(0.55, min(1.0, opacity)))
        except (TypeError, ValueError, Exception):  # pragma: no cover
            logger.debug("alpha unsupported", exc_info=True)

        x = self.db.get_setting("sidekick_x", "")
        y = self.db.get_setting("sidekick_y", "")
        width = self.WIDTH
        height = 470 if self._expanded else 320
        if x.isdigit() and y.isdigit():
            self.geometry(f"{width}x{height}+{x}+{y}")
        else:
            screen_w = self.winfo_screenwidth()
            self.geometry(f"{width}x{height}+{max(screen_w - width - 40, 20)}+120")

    def show(self) -> None:
        self.deiconify()
        self.lift()
        try:
            self.attributes("-topmost", self.db.get_bool_setting("sidekick_always_on_top", True))
        except Exception:  # pragma: no cover
            pass
        self._refresh_status()

    def hide(self) -> None:
        self._remember_position()
        self.withdraw()
        if self._on_hide is not None:
            try:
                self._on_hide()
            except Exception:  # pragma: no cover - defensive
                logger.debug("on_hide callback failed", exc_info=True)

    def toggle_compact(self) -> None:
        self._expanded = not self._expanded
        self.db.set_setting("sidekick_compact", "0" if self._expanded else "1")
        self._apply_compact_state()

    def _apply_compact_state(self) -> None:
        if self._expanded:
            self.compact_actions.pack_forget()
            self.actions.pack(fill="x", padx=10)
            self._mode_button.configure(text="▴")
            self.geometry(f"{self.WIDTH}x470")
        else:
            self.actions.pack_forget()
            self.compact_actions.pack(fill="x", padx=10)
            self._mode_button.configure(text="▾")
            self.geometry(f"{self.WIDTH}x320")

    def _remember_position(self) -> None:
        try:
            self.db.set_setting("sidekick_x", str(self.winfo_x()))
            self.db.set_setting("sidekick_y", str(self.winfo_y()))
        except Exception:  # pragma: no cover - shutdown race
            pass

    def _drag_start(self, event) -> None:
        self._drag_origin = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag_move(self, event) -> None:
        if not self._drag_origin:
            return
        offset_x, offset_y = self._drag_origin
        self.geometry(f"+{event.x_root - offset_x}+{event.y_root - offset_y}")

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #
    def _refresh_status(self) -> None:
        try:
            status = quick_actions.sidekick_status(self.db)
            if status["last_title"]:
                self.project_label.configure(text=status["last_title"])
                suffix = f"{status['capsules']} capsule(s)"
                if status["drafts"]:
                    suffix += f" · {status['drafts']} draft(s)"
                self.meta_label.configure(text=suffix)
            else:
                self.project_label.configure(text="No capsule yet")
                self.meta_label.configure(text="Capture a conversation to begin")

            report = self.app.gpu.report
            self.gpu_label.configure(
                text="GPU" if report.has_gpu else "CPU",
                text_color=COLORS["success"] if report.has_gpu else COLORS["text_muted"],
            )
        except Exception:  # noqa: BLE001 - widget must never die on status
            logger.debug("Sidekick status failed", exc_info=True)

        if self._status_job is not None:
            try:
                self.after_cancel(self._status_job)
            except Exception:  # pragma: no cover
                pass
        if self.winfo_exists():
            self._status_job = self.after(5000, self._refresh_status)

    def _set_status(self, text: str, kind: str = "info") -> None:
        colors = {"info": COLORS["text_muted"], "success": COLORS["success"], "error": COLORS["danger"]}
        self.status_label.configure(text=text, text_color=colors.get(kind, COLORS["text_muted"]))

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _capture_clipboard(self) -> None:
        text = quick_actions.clipboard_text(self)
        if not text.strip():
            self._set_status("Clipboard is empty", "error")
            return
        app = self.app
        app.navigate("capture")
        page = app.pages.get("capture")
        if page is not None and hasattr(page, "text_input"):
            page.text_input.delete("1.0", "end")
            page.text_input.insert("1.0", text)
        self._bring_app_forward()
        self._set_status("Clipboard sent to Capture", "success")

    def _quick_save(self) -> None:
        text = quick_actions.clipboard_text(self)
        if not text.strip():
            self._set_status("Clipboard is empty", "error")
            return
        self._set_status("Saving capsule…")
        run_in_background(
            self,
            lambda: quick_actions.quick_save(self.db, text),
            self._saved,
            self._save_failed,
        )

    def _saved(self, title: str) -> None:
        self._set_status(f"Saved “{title[:40]}”", "success")
        self._refresh_status()

    def _save_failed(self, error: Exception) -> None:
        logger.info("Sidekick quick save failed: %s", error)
        self._set_status(str(error)[:90], "error")

    def _copy_prompt(self) -> None:
        try:
            title, prompt = quick_actions.latest_prompt(self.db, "ChatGPT")
        except ValueError as exc:
            self._set_status(str(exc), "error")
            return
        self.clipboard_clear()
        self.clipboard_append(prompt)
        self._set_status(f"Prompt copied · {title[:28]}", "success")

    def _open_app(self, page: str | None) -> None:
        if page:
            self.app.navigate(page)
        self._bring_app_forward()

    def _bring_app_forward(self) -> None:
        try:
            self.app.deiconify()
            self.app.lift()
            self.app.focus_force()
        except Exception:  # pragma: no cover
            logger.debug("Could not raise main window", exc_info=True)
