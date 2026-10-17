# Windows Standalone Deployment & Packaging Guide

This guide details how to build and distribute JASPER as a standalone Windows executable (`JASPER.exe`) with the official cyberpunk arc-reactor icon and bundled assets.

---

## 1. Prerequisites

1. **Windows 10/11 64-bit**
2. **Local Python Virtual Environment (`.venv`)** with all dependencies installed.
3. **PyInstaller**:
   ```powershell
   .\.venv\Scripts\python.exe -m pip install pyinstaller
   ```

---

## 2. One-Click Automated Build

Run the automated packaging PowerShell script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_exe.ps1 -InstallPyInstaller
```

### What This Does:
1. Validates that `.\.venv\Scripts\python.exe` is present and active.
2. Checks and installs `pyinstaller` if missing.
3. Verifies `assets/jasper_icon.ico` and `assets/jasper_icon.png`.
4. Executes PyInstaller against `jasper.spec` with `--clean` and `--noconfirm`.
5. Emits the standalone distribution folder into `dist/JASPER/`.

---

## 3. Output Artifacts

After compilation, the output directory contains:
```text
dist/JASPER/
├── JASPER.exe             <-- Main double-clickable Windows application
├── assets/                <-- Bundled icons and artwork
│   ├── jasper_icon.ico
│   └── jasper_icon.png
├── PySide6/               <-- Qt GUI libraries and styles
├── _internal/             <-- Python runtime and DLL dependencies
```

---

## 4. Creating a Windows Desktop Shortcut

To pin JASPER to your Windows Desktop or Start Menu:
1. Right-click on `dist\JASPER\JASPER.exe`.
2. Select **Show more options** → **Send to** → **Desktop (create shortcut)**.
3. The shortcut will automatically feature the official JASPER logo icon.
4. Double-click the shortcut to run JASPER as an independent native desktop companion.

---

## 5. Persistent Data & Sessions in Standalone Mode

In standalone mode, user data is isolated cleanly:
* **Logins & Web Sessions:** Saved in `~/.jasper/browser_profile` (or `%USERPROFILE%\.jasper\browser_profile`).
* **Preferences & Models:** Loaded from `.env` in the working directory or default configuration.
