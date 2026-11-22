"""Main application window: sidebar shell, page router and status bar."""

from __future__ import annotations

import logging

import customtkinter as ctk

from ai.gpu_manager import GpuManager, GpuReport
from config import APP_NAME, BUILD_STAGE, TAGLINE, VERSION, WINDOW_DEFAULT_SIZE, WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
from database.db import Database, get_database
from gui.navigation import DEFAULT_PAGE, get_item
from gui.sidebar import Sidebar
from gui.theme import COLORS, SPACE, apply_appearance, font
from gui.workers import run_in_background
from sidekick import quick_actions
from sidekick.keyboard_shortcuts import ShortcutManager
from sidekick.window_manager import SidekickWindowManager

logger = logging.getLogger(__name__)


class SmartCapsuleApp(ctk.CTk):
    """Root window. Owns the database, GPU manager and page instances."""

    def __init__(self, database: Database | None = None, gpu_manager: GpuManager | None = None) -> None:
        apply_appearance()
        super().__init__()

        self.db = database or get_database()
        self.gpu = gpu_manager or GpuManager()
        self.pages: dict[str, object] = {}
        self.current_key: str | None = None

        self.title(f"{APP_NAME} — {TAGLINE}")
        self.geometry(WINDOW_DEFAULT_SIZE)
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.configure(fg_color=COLORS["bg"])

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = Sidebar(self, on_navigate=self.navigate, on_sidekick=self.toggle_sidekick)
        self.sidebar.grid(row=0, column=0, sticky="nsw")

        self.content = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self._build_status_bar()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.sidekick = SidekickWindowManager(self)
        self.shortcuts = ShortcutManager(
            self,
            {
                "toggle_sidekick": self.toggle_sidekick,
                "quick_save": self.quick_save_from_clipboard,
                "capture_selection": self.capture_clipboard,
                "open_app": self._raise_app,
            },
        )

        self.navigate(DEFAULT_PAGE)
        self._probe_hardware()
        self.shortcuts.start()

    # ------------------------------------------------------------------ #
    # Chrome
    # ------------------------------------------------------------------ #
    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COLORS["sidebar"], corner_radius=0, height=28)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        bar.pack_propagate(False)

        self._status_dot = ctk.CTkLabel(bar, text="●", font=font(9), text_color=COLORS["accent"], width=18)
        self._status_dot.pack(side="left", padx=(16, 0))

        self._status_label = ctk.CTkLabel(
            bar, text="Ready", font=font(10), text_color=COLORS["text_muted"], anchor="w"
        )
        self._status_label.pack(side="left", padx=(2, 0))

        ctk.CTkLabel(
            bar,
            text=f"v{VERSION} · {BUILD_STAGE}",
            font=font(10),
            text_color=COLORS["text_muted"],
        ).pack(side="right", padx=18)

    def set_status(self, message: str, kind: str = "info") -> None:
        colors = {
            "info": COLORS["accent"],
            "success": COLORS["success"],
            "warning": COLORS["warning"],
            "error": COLORS["danger"],
        }
        self._status_dot.configure(text_color=colors.get(kind, COLORS["accent"]))
        self._status_label.configure(
            text=message,
            text_color=COLORS["text_dim"] if kind == "info" else colors.get(kind, COLORS["text_dim"]),
        )

    # ------------------------------------------------------------------ #
    # Routing
    # ------------------------------------------------------------------ #
    def navigate(self, key: str) -> None:
        """Show the page registered under ``key``, creating it on first visit."""
        try:
            item = get_item(key)
        except KeyError:
            self.set_status(f"Unknown page: {key}", kind="error")
            return

        page = self.pages.get(key)
        if page is None:
            try:
                page = item.load()(self.content, self)
            except Exception as exc:  # noqa: BLE001 - a broken page must not kill the app
                logger.exception("Failed to build page %s", key)
                self._show_error_page(key, exc)
                return
            self.pages[key] = page

        if self.current_key and self.current_key != key:
            previous = self.pages.get(self.current_key)
            if previous is not None:
                previous.grid_forget()

        page.grid(row=0, column=0, sticky="nsew")
        self.current_key = key
        self.sidebar.set_active(key)

        try:
            page.on_show()
        except Exception as exc:  # noqa: BLE001
            logger.exception("on_show failed for %s", key)
            self.set_status(f"{item.label}: {exc}", kind="error")

    def _show_error_page(self, key: str, error: Exception) -> None:
        frame = ctk.CTkFrame(self.content, fg_color=COLORS["bg"], corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(
            frame, text="This screen could not be loaded", font=font(18, "bold"), text_color=COLORS["text"]
        ).pack(pady=(120, 8))
        ctk.CTkLabel(
            frame,
            text=f"{key}: {error}",
            font=font(12),
            text_color=COLORS["danger"],
            wraplength=640,
            justify="center",
        ).pack()
        self.pages[key] = frame
        self.current_key = key
        self.sidebar.set_active(key)
        self.set_status(f"Page error: {error}", kind="error")

    # ------------------------------------------------------------------ #
    # Hardware probe
    # ------------------------------------------------------------------ #
    def _probe_hardware(self) -> None:
        self.sidebar.set_hardware_status("Detecting hardware…", f"{APP_NAME} v{VERSION}", ok=True)
        run_in_background(self, self.gpu.refresh, self._apply_hardware, self._hardware_failed)

    def _apply_hardware(self, report: GpuReport) -> None:
        headline = report.status_line
        detail = report.recommended.vram_label if report.has_gpu else "CPU processing · no GPU required"
        self.sidebar.set_hardware_status(headline, detail, ok=report.has_gpu)
        self.set_status(
            "GPU acceleration ready" if report.has_gpu else "Running on CPU — all features remain available",
            kind="success" if report.has_gpu else "info",
        )

    def _hardware_failed(self, error: Exception) -> None:
        logger.exception("Hardware probe failed")
        self.sidebar.set_hardware_status("CPU only", f"{APP_NAME} v{VERSION}", ok=False)
        self.set_status(f"Hardware probe failed: {error}", kind="warning")

    # ------------------------------------------------------------------ #
    # Sidekick
    # ------------------------------------------------------------------ #
    def toggle_sidekick(self) -> None:
        """Show or hide the floating assistant."""
        try:
            visible = self.sidekick.toggle()
        except Exception as exc:  # noqa: BLE001 - the widget must never kill the app
            logger.exception("Sidekick toggle failed")
            self.set_status(f"Sidekick unavailable: {exc}", kind="error")
            return
        self.set_status(
            "Sidekick shown — Ctrl+Shift+Space to hide" if visible else "Sidekick hidden",
            kind="success" if visible else "info",
        )
        page = self.pages.get("sidekick")
        if page is not None and hasattr(page, "refresh_status"):
            page.refresh_status()

    def quick_save_from_clipboard(self) -> None:
        """Ctrl+Shift+S: turn the clipboard into a capsule (explicit action)."""
        text = quick_actions.clipboard_text(self)
        if not text.strip():
            self.set_status("Clipboard is empty — nothing saved", kind="warning")
            return
        self.set_status("Quick-saving clipboard as a capsule…")
        run_in_background(
            self,
            lambda: quick_actions.quick_save(self.db, text),
            lambda title: self._quick_saved(title),
            lambda error: self.set_status(f"Quick save failed: {error}", kind="error"),
        )

    def _quick_saved(self, title: str) -> None:
        self.set_status(f"Quick-saved “{title}”", kind="success")
        page = self.pages.get("dashboard")
        if page is not None and hasattr(page, "refresh"):
            page.refresh()

    def capture_clipboard(self) -> None:
        """Ctrl+Shift+C: send the clipboard to the capture screen for review."""
        text = quick_actions.clipboard_text(self)
        if not text.strip():
            self.set_status("Clipboard is empty", kind="warning")
            return
        self.navigate("capture")
        page = self.pages.get("capture")
        if page is not None and hasattr(page, "text_input"):
            page.text_input.delete("1.0", "end")
            page.text_input.insert("1.0", text)
        self.set_status("Clipboard loaded into Capture", kind="success")
        self._raise_app()

    def _raise_app(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:  # pragma: no cover - window manager dependent
            logger.debug("Could not raise main window", exc_info=True)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def _on_close(self) -> None:
        try:
            self.shortcuts.stop()
        except Exception:  # pragma: no cover
            logger.debug("Stopping shortcuts failed", exc_info=True)
        try:
            self.sidekick.destroy()
        except Exception:  # pragma: no cover
            logger.debug("Destroying sidekick failed", exc_info=True)
        try:
            self.db.set_setting("last_open_page", self.current_key or DEFAULT_PAGE)
        except Exception:  # pragma: no cover - closing must never raise
            logger.debug("Could not persist last page", exc_info=True)
        self.destroy()
