"""Global keyboard shortcuts.

On Windows, hotkeys are registered with the operating system (``RegisterHotKey``)
so they work while another application has focus. Everywhere else, or when a
combination is already taken, the same actions remain available as in-app
bindings and the failure is reported instead of silently ignored.
"""

from __future__ import annotations

import logging
import sys
from typing import Callable

logger = logging.getLogger(__name__)

# Windows modifiers
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

SHORTCUTS: dict[str, tuple[str, int]] = {
    "toggle_sidekick": ("Ctrl+Shift+Space", 0x20),
    "quick_save": ("Ctrl+Shift+S", 0x53),
    "capture_selection": ("Ctrl+Shift+C", 0x43),
    "open_app": ("Ctrl+Shift+O", 0x4F),
}

TCL_BINDINGS: dict[str, str] = {
    "toggle_sidekick": "<Control-Shift-KeyPress-space>",
    "quick_save": "<Control-Shift-KeyPress-s>",
    "capture_selection": "<Control-Shift-KeyPress-c>",
    "open_app": "<Control-Shift-KeyPress-o>",
}


class ShortcutManager:
    """Register OS-level hotkeys with graceful degradation."""

    def __init__(self, root, handlers: dict[str, Callable[[], None]]) -> None:
        self.root = root
        self.handlers = {key: handler for key, handler in handlers.items() if handler}
        self.registered: list[str] = []
        self.failed: dict[str, str] = {}
        self._ids: dict[int, str] = {}
        self._poll_job: str | None = None

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Bind in-app shortcuts, then attempt OS-level registration."""
        for action, sequence in TCL_BINDINGS.items():
            handler = self.handlers.get(action)
            if handler is None:
                continue
            try:
                self.root.bind_all(sequence, lambda _event, fn=handler: fn())
            except Exception:  # pragma: no cover - exotic Tk builds
                logger.debug("Could not bind %s", sequence, exc_info=True)

        if sys.platform.startswith("win"):
            self._register_windows()
        else:
            self.failed["__platform__"] = "Global hotkeys are Windows-only in this build; in-app shortcuts work."

    def stop(self) -> None:
        if self._poll_job is not None:
            try:
                self.root.after_cancel(self._poll_job)
            except Exception:  # pragma: no cover
                pass
            self._poll_job = None
        self._unregister_windows()

    # ------------------------------------------------------------------ #
    def _register_windows(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            self._user32 = user32

            for index, (action, (label, vk)) in enumerate(SHORTCUTS.items(), start=1):
                if action not in self.handlers:
                    continue
                if user32.RegisterHotKey(None, index, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, vk):
                    self.registered.append(label)
                    self._ids[index] = action
                else:
                    self.failed[action] = f"{label} is already used by another application"
                    logger.warning("Hotkey %s is unavailable", label)

            self._poll()
        except Exception as exc:  # pragma: no cover - non-standard environments
            logger.warning("Global hotkey registration failed: %s", exc)
            self.failed["__platform__"] = f"Global hotkeys unavailable: {exc}"

    def _poll(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

            class MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", POINT),
                ]

            message = MSG()
            # Only WM_HOTKEY messages are removed, so Tk's own queue is untouched.
            while self._user32.PeekMessageW(ctypes.byref(message), None, WM_HOTKEY, WM_HOTKEY, 1):
                action = self._ids.get(int(message.wParam))
                handler = self.handlers.get(action) if action else None
                if handler is not None:
                    try:
                        handler()
                    except Exception:  # noqa: BLE001 - a handler must not kill polling
                        logger.exception("Shortcut handler failed: %s", action)
        except Exception:  # pragma: no cover - defensive
            logger.debug("Hotkey poll failed", exc_info=True)

        try:
            self._poll_job = self.root.after(150, self._poll)
        except Exception:  # pragma: no cover - window closed
            self._poll_job = None

    def _unregister_windows(self) -> None:
        if not sys.platform.startswith("win"):
            return
        try:
            user32 = getattr(self, "_user32", None)
            if user32 is None:
                return
            for index in list(self._ids):
                user32.UnregisterHotKey(None, index)
            self._ids.clear()
        except Exception:  # pragma: no cover
            logger.debug("Unregistering hotkeys failed", exc_info=True)

    # ------------------------------------------------------------------ #
    def status(self) -> dict[str, object]:
        return {
            "registered": list(self.registered),
            "failed": dict(self.failed),
            "shortcuts": {action: label for action, (label, _vk) in SHORTCUTS.items()},
        }
