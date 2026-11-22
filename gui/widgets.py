"""Reusable CustomTkinter widgets that implement the Smart Capsule look.

Keeping these in one module means pages only describe *content*; the visual
language (rounded cards, subtle borders, hover states, stat panels) stays
consistent and is changed in one place.
"""

from __future__ import annotations

from typing import Callable, Iterable

import customtkinter as ctk

from gui.theme import COLORS, RADIUS, font, icon_font


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def format_bytes(size: int | float) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_timestamp(value, fallback: str = "never") -> str:
    if value is None:
        return fallback
    try:
        return value.strftime("%d %b %Y · %H:%M")
    except (AttributeError, ValueError):  # pragma: no cover - defensive
        return fallback


def clear_children(widget: ctk.CTkBaseClass) -> None:
    for child in widget.winfo_children():
        child.destroy()


# --------------------------------------------------------------------------- #
# Cards and panels
# --------------------------------------------------------------------------- #
class Card(ctk.CTkFrame):
    """Rounded panel with an optional title/subtitle header."""

    def __init__(
        self,
        master,
        title: str | None = None,
        subtitle: str | None = None,
        padding: int = 18,
        accent: str | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("fg_color", COLORS["panel"])
        kwargs.setdefault("corner_radius", RADIUS["card"])
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["border"])
        super().__init__(master, **kwargs)

        self.padding = padding
        self.accent = accent
        self.inner = ctk.CTkFrame(self, fg_color="transparent")
        self.inner.pack(fill="both", expand=True, padx=padding, pady=padding)

        self.header: ctk.CTkFrame | None = None
        if title:
            self.header = ctk.CTkFrame(self.inner, fg_color="transparent")
            self.header.pack(fill="x", pady=(0, 14))

            if accent:
                dot = ctk.CTkFrame(self.header, fg_color=accent, width=6, height=18, corner_radius=3)
                dot.pack(side="left", padx=(0, 10))
                dot.pack_propagate(False)

            text_block = ctk.CTkFrame(self.header, fg_color="transparent")
            text_block.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                text_block, text=title, font=font(14, "bold"), text_color=COLORS["text"], anchor="w"
            ).pack(anchor="w")
            if subtitle:
                ctk.CTkLabel(
                    text_block,
                    text=subtitle,
                    font=font(11),
                    text_color=COLORS["text_muted"],
                    anchor="w",
                ).pack(anchor="w", pady=(2, 0))

            self.header_actions = ctk.CTkFrame(self.header, fg_color="transparent")
            self.header_actions.pack(side="right")

        self.body = ctk.CTkFrame(self.inner, fg_color="transparent")
        self.body.pack(fill="both", expand=True)


class StatCard(ctk.CTkFrame):
    """Key figure with label and supporting hint."""

    def __init__(self, master, label: str, value: str = "—", hint: str = "", accent: str | None = None):
        super().__init__(
            master,
            fg_color=COLORS["panel"],
            corner_radius=RADIUS["card"],
            border_width=1,
            border_color=COLORS["border"],
        )
        self._accent = accent or COLORS["accent"]

        bar = ctk.CTkFrame(self, fg_color=self._accent, height=3, corner_radius=2)
        bar.pack(fill="x", padx=18, pady=(16, 0))
        bar.pack_propagate(False)

        self._label = ctk.CTkLabel(
            self, text=label.upper(), font=font(10, "bold"), text_color=COLORS["text_muted"], anchor="w"
        )
        self._label.pack(fill="x", padx=18, pady=(12, 0))

        self._value = ctk.CTkLabel(
            self, text=value, font=font(26, "bold"), text_color=COLORS["text"], anchor="w"
        )
        self._value.pack(fill="x", padx=18, pady=(2, 0))

        self._hint = ctk.CTkLabel(
            self, text=hint, font=font(11), text_color=COLORS["text_dim"], anchor="w", wraplength=200, justify="left"
        )
        self._hint.pack(fill="x", padx=18, pady=(0, 16))

    def set(self, value: str, hint: str | None = None) -> None:
        self._value.configure(text=value)
        if hint is not None:
            self._hint.configure(text=hint)


class ActionCard(ctk.CTkFrame):
    """Large clickable call-to-action tile used on the dashboard."""

    def __init__(
        self,
        master,
        title: str,
        subtitle: str,
        icon: str,
        command: Callable[[], None],
        accent: str = COLORS["accent"],
        enabled: bool = True,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["panel"],
            corner_radius=RADIUS["card"],
            border_width=1,
            border_color=COLORS["border"],
            cursor="hand2" if enabled else "",
        )
        self._command = command
        self._accent = accent
        self._enabled = enabled

        badge = ctk.CTkFrame(self, fg_color=COLORS["panel_alt"], corner_radius=12, width=38, height=38)
        badge.pack(anchor="w", padx=16, pady=(16, 0))
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text=icon, font=icon_font(17), text_color=accent).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            self, text=title, font=font(13, "bold"), text_color=COLORS["text"], anchor="w", justify="left"
        ).pack(fill="x", padx=16, pady=(12, 0))

        ctk.CTkLabel(
            self,
            text=subtitle,
            font=font(11),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=190,
        ).pack(fill="x", padx=16, pady=(3, 16))

        self._bind_tree(self)

    def _bind_tree(self, widget) -> None:
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Button-1>", self._on_click, add="+")
        for child in widget.winfo_children():
            self._bind_tree(child)

    def _on_enter(self, _event=None) -> None:
        if not self._enabled:
            return
        self.configure(fg_color=COLORS["panel_hover"], border_color=self._accent)

    def _on_leave(self, _event=None) -> None:
        if not self._enabled:
            return
        self.configure(fg_color=COLORS["panel"], border_color=COLORS["border"])

    def _on_click(self, _event=None) -> None:
        if self._enabled:
            self._command()


class Badge(ctk.CTkLabel):
    """Small pill label, e.g. a platform name or status."""

    def __init__(self, master, text: str, color: str = COLORS["accent"], text_color: str | None = None, **kwargs):
        super().__init__(
            master,
            text=text,
            font=font(10, "bold"),
            text_color=text_color or color,
            fg_color=COLORS["panel_alt"],
            corner_radius=RADIUS["pill"],
            padx=10,
            pady=3,
            **kwargs,
        )


class KeyValueRow(ctk.CTkFrame):
    """Label on the left, value on the right (system status style)."""

    def __init__(self, master, label: str, value: str = "—", value_color: str | None = None, mono: bool = False):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(
            self, text=label, font=font(12), text_color=COLORS["text_muted"], anchor="w"
        ).pack(side="left", padx=(0, 12))
        self.value = ctk.CTkLabel(
            self,
            text=value,
            font=font(12, "normal"),
            text_color=value_color or COLORS["text"],
            anchor="e",
            justify="right",
            wraplength=230,
        )
        self.value.pack(side="right")

    def set(self, value: str, color: str | None = None) -> None:
        self.value.configure(text=value)
        if color:
            self.value.configure(text_color=color)


def divider(master, pady: int = 10) -> ctk.CTkFrame:
    line = ctk.CTkFrame(master, fg_color=COLORS["border_soft"], height=1, corner_radius=0)
    line.pack(fill="x", pady=pady)
    line.pack_propagate(False)
    return line


def empty_state(master, title: str, message: str, icon: str = "◇") -> ctk.CTkFrame:
    holder = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkLabel(holder, text=icon, font=icon_font(30), text_color=COLORS["border"]).pack(pady=(6, 4))
    ctk.CTkLabel(holder, text=title, font=font(13, "bold"), text_color=COLORS["text_dim"]).pack()
    ctk.CTkLabel(
        holder,
        text=message,
        font=font(11),
        text_color=COLORS["text_muted"],
        wraplength=360,
        justify="center",
    ).pack(pady=(4, 6))
    return holder


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #
def primary_button(master, text: str, command: Callable[[], None], **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 38)
    kwargs.setdefault("corner_radius", RADIUS["control"])
    kwargs.setdefault("font", font(12, "bold"))
    kwargs.setdefault("fg_color", COLORS["accent"])
    kwargs.setdefault("hover_color", COLORS["accent_hover"])
    kwargs.setdefault("text_color", "#FFFFFF")
    return ctk.CTkButton(master, text=text, command=command, **kwargs)


def ghost_button(master, text: str, command: Callable[[], None], **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 34)
    kwargs.setdefault("corner_radius", RADIUS["control"])
    kwargs.setdefault("font", font(12))
    kwargs.setdefault("fg_color", "transparent")
    kwargs.setdefault("hover_color", COLORS["panel_alt"])
    kwargs.setdefault("text_color", COLORS["text_dim"])
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", COLORS["border"])
    return ctk.CTkButton(master, text=text, command=command, **kwargs)


def danger_button(master, text: str, command: Callable[[], None], **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 34)
    kwargs.setdefault("corner_radius", RADIUS["control"])
    kwargs.setdefault("font", font(12))
    kwargs.setdefault("fg_color", COLORS["danger_soft"])
    kwargs.setdefault("hover_color", COLORS["danger"])
    kwargs.setdefault("text_color", COLORS["danger"])
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", COLORS["danger"])
    return ctk.CTkButton(master, text=text, command=command, **kwargs)


# --------------------------------------------------------------------------- #
# Text areas
# --------------------------------------------------------------------------- #
def text_box(master, height: int = 200, placeholder: str = "") -> ctk.CTkTextbox:
    return ctk.CTkTextbox(
        master,
        height=height,
        fg_color=COLORS["bg"],
        border_width=1,
        border_color=COLORS["border"],
        corner_radius=RADIUS["control"],
        text_color=COLORS["text"],
        font=font(12),
        wrap="word",
        scrollbar_button_color=COLORS["border"],
        scrollbar_button_hover_color=COLORS["panel_hover"],
    )


def scroll_area(master) -> ctk.CTkScrollableFrame:
    frame = ctk.CTkScrollableFrame(
        master,
        fg_color="transparent",
        corner_radius=0,
        scrollbar_button_color=COLORS["border_soft"],
        scrollbar_button_hover_color=COLORS["panel_hover"],
    )
    frame.grid_columnconfigure(0, weight=1)
    return frame


def chip_row(master, labels: Iterable[str]) -> ctk.CTkFrame:
    row = ctk.CTkFrame(master, fg_color="transparent")
    for label in labels:
        Badge(row, label).pack(side="left", padx=(0, 6), pady=2)
    return row


# --------------------------------------------------------------------------- #
# Modal dialogs
# --------------------------------------------------------------------------- #
def confirm_dialog(parent, title: str, message: str, confirm_text: str = "Confirm", danger: bool = True) -> bool:
    """Modal yes/no dialog. Returns True when the user confirms."""
    result = {"value": False}

    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("440x230")
    dialog.configure(fg_color=COLORS["bg"])
    dialog.resizable(False, False)
    dialog.transient(parent.winfo_toplevel())
    dialog.grab_set()

    dialog.update_idletasks()
    x = parent.winfo_toplevel().winfo_rootx() + (parent.winfo_toplevel().winfo_width() - 440) // 2
    y = parent.winfo_toplevel().winfo_rooty() + (parent.winfo_toplevel().winfo_height() - 230) // 3
    dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    ctk.CTkLabel(dialog, text=title, font=font(15, "bold"), text_color=COLORS["text"]).pack(
        anchor="w", padx=24, pady=(22, 6)
    )
    ctk.CTkLabel(
        dialog,
        text=message,
        font=font(12),
        text_color=COLORS["text_dim"],
        wraplength=390,
        justify="left",
    ).pack(anchor="w", padx=24)

    buttons = ctk.CTkFrame(dialog, fg_color="transparent")
    buttons.pack(fill="x", padx=24, pady=20, side="bottom")

    def close(value: bool) -> None:
        result["value"] = value
        dialog.grab_release()
        dialog.destroy()

    ghost_button(buttons, "Cancel", lambda: close(False), width=110).pack(side="right")
    if danger:
        danger_button(buttons, confirm_text, lambda: close(True), width=140).pack(side="right", padx=8)
    else:
        primary_button(buttons, confirm_text, lambda: close(True), width=140).pack(side="right", padx=8)

    dialog.bind("<Escape>", lambda _e: close(False))
    dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
    dialog.wait_window()
    return result["value"]


def message_dialog(parent, title: str, message: str) -> None:
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("460x220")
    dialog.configure(fg_color=COLORS["bg"])
    dialog.resizable(False, False)
    dialog.transient(parent.winfo_toplevel())
    dialog.grab_set()
    ctk.CTkLabel(dialog, text=title, font=font(15, "bold"), text_color=COLORS["text"]).pack(
        anchor="w", padx=24, pady=(22, 6)
    )
    ctk.CTkLabel(
        dialog,
        text=message,
        font=font(12),
        text_color=COLORS["text_dim"],
        wraplength=410,
        justify="left",
    ).pack(anchor="w", padx=24)
    primary_button(dialog, "Close", dialog.destroy, width=110).pack(side="right", padx=24, pady=20)
    dialog.wait_window()
