"""Central application configuration for Smart Capsule.

Everything the application needs to know about *where* its data lives and
*what* the current build is, lives here so that no other module has to guess
paths.  All values are side-effect free: importing this module never creates
directories or databases.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
APP_NAME = "Smart Capsule"
APP_SLUG = "smart-capsule"
VERSION = "1.0.0"
BUILD_STAGE = "Phase 8 - Release"

TAGLINE = "One Click. Complete Context. Continue Anywhere."
SLOGAN = "ONE CLICK. SAVE YOUR AI MEMORY. CONTINUE ANYWHERE."

CAPSULE_EXTENSION = ".scapsule"
CAPSULE_FORMAT_VERSION = 1

# --------------------------------------------------------------------------- #
# Filesystem layout
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent


def data_dir() -> Path:
    """Return the per-user writable data directory.

    ``SMART_CAPSULE_HOME`` overrides the location, which tests and portable
    installs rely on.  The directory is created on demand.
    """
    override = os.environ.get("SMART_CAPSULE_HOME")
    if override:
        base = Path(override).expanduser()
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SmartCapsule"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "SmartCapsule"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "smart-capsule"

    base.mkdir(parents=True, exist_ok=True)
    return base


def database_path() -> Path:
    """Absolute path of the SQLite database file."""
    return data_dir() / "smart_capsule.db"


def exports_dir() -> Path:
    path = data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def attachments_dir() -> Path:
    path = data_dir() / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backups_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def migrations_dir() -> Path:
    return PROJECT_ROOT / "database" / "migrations"


def assets_dir() -> Path:
    return PROJECT_ROOT / "assets"


# --------------------------------------------------------------------------- #
# UI defaults (persisted settings can override these at runtime)
# --------------------------------------------------------------------------- #
WINDOW_MIN_WIDTH = 1120
WINDOW_MIN_HEIGHT = 720
WINDOW_DEFAULT_SIZE = "1360x860"

SUPPORTED_AI_PLATFORMS: tuple[str, ...] = (
    "ChatGPT",
    "Claude",
    "Gemini",
    "Cursor",
    "Copilot",
    "Perplexity",
    "Other",
)

# Human-readable labels for the persisted compression modes.
COMPRESSION_MODES: tuple[str, ...] = ("balanced", "high", "full")
