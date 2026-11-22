"""Single navigation registry shared by the sidebar and the page router.

Pages are referenced by module path and class name so importing this module is
cheap and cannot create circular imports (pages import widgets, not navigation).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NavItem:
    key: str
    label: str
    icon: str
    group: str
    module: str
    class_name: str
    phase: int = 1

    def load(self) -> type:
        module = importlib.import_module(self.module)
        return getattr(module, self.class_name)


NAV_ITEMS: tuple[NavItem, ...] = (
    # -- Workspace ---------------------------------------------------------
    NavItem("dashboard", "Dashboard", "◈", "WORKSPACE", "gui.dashboard", "DashboardPage"),
    NavItem("create_capsule", "Create Capsule", "＋", "WORKSPACE", "gui.capsule_page", "CapsulePage"),
    NavItem("capture", "Capture Conversation", "⌁", "WORKSPACE", "gui.capture_page", "CapturePage"),
    NavItem("capsules", "My Capsules", "▤", "WORKSPACE", "gui.capsules_page", "CapsulesPage"),
    NavItem("import", "Import Capsule", "⇩", "WORKSPACE", "gui.import_page", "ImportPage"),
    NavItem("resume", "Resume Project", "▸", "WORKSPACE", "gui.resume_page", "ResumePage"),
    # -- Intelligence ------------------------------------------------------
    NavItem("ai", "AI Intelligence", "✦", "INTELLIGENCE", "gui.ai_settings", "AISettingsPage"),
    NavItem("gpu", "GPU Monitor", "⚡", "INTELLIGENCE", "gui.gpu_monitor", "GpuMonitorPage"),
    NavItem("sidekick", "Sidekick Settings", "◉", "INTELLIGENCE", "gui.sidekick_settings", "SidekickSettingsPage"),
    # -- System ------------------------------------------------------------
    NavItem("platforms", "Connected Platforms", "◍", "SYSTEM", "gui.platforms_page", "PlatformsPage"),
    NavItem("versions", "Version History", "↺", "SYSTEM", "gui.version_history_page", "VersionHistoryPage"),
    NavItem("storage", "Storage Management", "▦", "SYSTEM", "gui.storage_page", "StoragePage"),
    NavItem("settings", "Settings", "⚙", "SYSTEM", "gui.settings", "SettingsPage"),
)

DEFAULT_PAGE = "dashboard"


def get_item(key: str) -> NavItem:
    for item in NAV_ITEMS:
        if item.key == key:
            return item
    raise KeyError(f"Unknown page: {key}")


def groups() -> list[tuple[str, list[NavItem]]]:
    """Nav items grouped for the sidebar, preserving declaration order."""
    ordered: list[tuple[str, list[NavItem]]] = []
    for item in NAV_ITEMS:
        for name, members in ordered:
            if name == item.group:
                members.append(item)
                break
        else:
            ordered.append((item.group, [item]))
    return ordered


def page_class(key: str) -> type[Any]:
    return get_item(key).load()
