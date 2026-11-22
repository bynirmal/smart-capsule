# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for Smart Capsule.

Build (from the project root):

    pyinstaller packaging/smart_capsule.spec --noconfirm

The result is ``dist/SmartCapsule/SmartCapsule.exe`` (one-folder build, which
starts faster and keeps the web client's static files editable). Static web
assets and SQL migrations are bundled explicitly because they are loaded from
disk at runtime, not imported as Python modules.
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - provided by PyInstaller

datas = [
    (str(ROOT / "webapp" / "static"), "webapp/static"),
    (str(ROOT / "database" / "migrations"), "database/migrations"),
]

hiddenimports = [
    "webapp.server",
    "webapp.__main__",
    "sidekick.floating_widget",
    "gui.dashboard",
    "gui.capture_page",
    "gui.capsule_page",
    "gui.capsules_page",
    "gui.import_page",
    "gui.resume_page",
    "gui.ai_settings",
    "gui.gpu_monitor",
    "gui.sidekick_settings",
    "gui.platforms_page",
    "gui.version_history_page",
    "gui.storage_page",
    "gui.settings",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "transformers", "sentence_transformers", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SmartCapsule",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SmartCapsule",
)
