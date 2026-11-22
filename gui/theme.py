"""Smart Capsule design system.

A single source of truth for colour, spacing and typography so every screen
looks like it belongs to the same product: dark navy canvas, charcoal panels,
electric-blue and violet accents.

Fonts are created through :func:`font` rather than at import time, because Tk
requires a live root window before a font family can be resolved.
"""

from __future__ import annotations

import sys

import customtkinter as ctk

# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #
COLORS: dict[str, str] = {
    "bg": "#0A0E19",
    "sidebar": "#0C1220",
    "panel": "#111A2B",
    "panel_alt": "#16203A",
    "panel_hover": "#1B2742",
    "border": "#1F2B45",
    "border_soft": "#182238",
    "accent": "#3D7BFF",
    "accent_hover": "#5A90FF",
    "accent_soft": "#16244A",
    "violet": "#8B5CF6",
    "violet_soft": "#241F4A",
    "text": "#E9EEFA",
    "text_dim": "#A7B2CC",
    "text_muted": "#74809B",
    "success": "#34D399",
    "success_soft": "#102C27",
    "warning": "#FBBF24",
    "warning_soft": "#2E2612",
    "danger": "#FF647C",
    "danger_soft": "#311720",
}

RADIUS = {"card": 16, "control": 10, "pill": 999}

SPACE = {"xs": 4, "sm": 8, "md": 14, "lg": 20, "xl": 28}

_PLATFORM = sys.platform
UI_FAMILY = "Segoe UI" if _PLATFORM.startswith("win") else ("SF Pro Display" if _PLATFORM == "darwin" else "DejaVu Sans")
ICON_FAMILY = "Segoe UI Symbol" if _PLATFORM.startswith("win") else UI_FAMILY
MONO_FAMILY = "Consolas" if _PLATFORM.startswith("win") else "Menlo"


# --------------------------------------------------------------------------- #
# Colour helpers
# --------------------------------------------------------------------------- #
def hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    red, green, blue = (max(0, min(255, int(round(channel)))) for channel in rgb)
    return f"#{red:02X}{green:02X}{blue:02X}"


def mix(color_a: str, color_b: str, weight: float = 0.5) -> str:
    """Blend ``color_a`` towards ``color_b`` by ``weight`` (0..1)."""
    weight = max(0.0, min(1.0, weight))
    a = hex_to_rgb(color_a)
    b = hex_to_rgb(color_b)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * weight for i in range(3)))


def lighten(color: str, amount: float = 0.12) -> str:
    return mix(color, "#FFFFFF", amount)


def darken(color: str, amount: float = 0.12) -> str:
    return mix(color, "#000000", amount)


def alpha_over(color: str, background: str, alpha: float = 0.2) -> str:
    """Approximate a translucent fill by blending against its background."""
    return mix(background, color, alpha)


# --------------------------------------------------------------------------- #
# Typography
# --------------------------------------------------------------------------- #
def font(size: int = 13, weight: str = "normal", family: str | None = None) -> ctk.CTkFont:
    return ctk.CTkFont(family=family or UI_FAMILY, size=size, weight=weight)


def icon_font(size: int = 15) -> ctk.CTkFont:
    return ctk.CTkFont(family=ICON_FAMILY, size=size)


def mono_font(size: int = 12) -> ctk.CTkFont:
    return ctk.CTkFont(family=MONO_FAMILY, size=size)


# --------------------------------------------------------------------------- #
# Global setup
# --------------------------------------------------------------------------- #
def apply_appearance() -> None:
    """Force the dark, product-defined appearance (not OS-dependent)."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
