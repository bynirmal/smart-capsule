"""Optional start-with-Windows support.

Writes only the per-user ``HKCU\\...\\Run`` value, and only when the user turns the
setting on. Any failure is reported to the caller; it is never silent.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SmartCapsule"


def _command() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller build
        return f'"{sys.executable}" --minimised'
    entry = Path(__file__).resolve().parents[1] / "main.py"
    return f'"{sys.executable}" "{entry}"'


def is_enabled() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:  # pragma: no cover - permissions
        logger.debug("Autostart query failed", exc_info=True)
        return False


def set_enabled(enabled: bool) -> tuple[bool, str]:
    """Enable or disable autostart; returns ``(ok, message)``."""
    if not sys.platform.startswith("win"):
        return False, "Autostart is only implemented for Windows in this build."

    try:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
                return True, "Smart Capsule will start with Windows."
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
            return True, "Autostart disabled."
    except OSError as exc:  # pragma: no cover - policy/permissions
        logger.warning("Autostart update failed: %s", exc)
        return False, f"Windows refused the change: {exc}"
