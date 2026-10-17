# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for JASPER Windows Desktop Application."""

import sys
from pathlib import Path

block_cipher = None
ROOT = Path(".").resolve()

datas = [
    (str(ROOT / "assets"), "assets"),
]

# If data folder exists (e.g. data/voices, default configs), include it
data_dir = ROOT / "data"
if data_dir.exists():
    datas.append((str(data_dir), "data"))

hidden_imports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "playwright.sync_api",
    "app.agents.desktop_wiring",
    "app.core.logging_setup",
    "app.ui.main_window",
    "app.ui.worker",
    "app.ui.toast_banner",
    "app.ui.settings_workspace",
    "app.ui.tasks_workspace",
    "app.ui.scheduled_workspace",
    "app.ui.plugins_workspace",
    "app.ui.vision_workspace",
    "app.ui.approval_dialog",
    "dotenv",
    "urllib.request",
    "urllib.parse",
    "sqlite3",
]

a = Analysis(
    [str(ROOT / "app" / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook", "IPython"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JASPER",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to False for native Windows GUI (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "jasper_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="JASPER",
)
