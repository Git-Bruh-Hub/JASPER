# Implementation Plan: C → B → A (Toasts/Tray Alerts → Expanded Browser Automation → Windows Packaging)

## Milestone Sequence Requested by User:
1. **Option C: User Notification Toasts & System Tray Alert Banners**
2. **Option B: Expanded Browser Automation Capabilities (Email extraction, multi-tab switching, element observation)**
3. **Option A: Windows Deployability & Standalone Packaging (`jasper.spec`, build scripts, and standalone EXE)**

---

## Slice 1 (Option C): Desktop Notification Toasts & System Tray Alerts
- **Goal:**
  - Provide both native OS system tray notifications (`QSystemTrayIcon.showMessage`) and a non-intrusive animated in-app toast notification banner in `MainWindow`.
  - Alert the user when:
    - Long-running autonomous web tasks / browser tasks finish.
    - Security approval is requested while the window is in background or minimized.
    - An error or cancellation occurs.
  - Add notification toggle in `app/core/config.py` and `SettingsWorkspace`.
- **Files:**
  - `app/core/config.py`
  - `app/ui/main_window.py`
  - `app/ui/toast_banner.py` (new lightweight widget)
  - `app/ui/settings_workspace.py`
  - `tests/test_notifications.py` (new test file)

---

## Slice 2 (Option B): Expanded Browser Automation Capabilities
- **Goal:**
  - Enhance `BrowserController` in `app/tools/browser.py` with:
    - Tab management: `new_tab(url)`, `switch_tab(index)`, `close_tab(index)`, `list_tabs()`.
    - Dedicated webmail / email helper: `read_inbox(filter_query)` to extract sender, subject, and snippet from webmail DOMs (Gmail, Outlook, Yahoo) using resilient selectors.
    - Element observation & action helper: `click_element(index)`, `type_element(index, text)` for targeted automation.
  - Wire tools into `app/agents/desktop_wiring.py` and update autonomy router.
- **Files:**
  - `app/tools/browser.py`
  - `app/agents/desktop_wiring.py`
  - `tests/test_browser_expanded.py`

---

## Slice 3 (Option A): Windows Deployability & Standalone Packaging
- **Goal:**
  - Create a production-ready PyInstaller build specification `jasper.spec` that bundles:
    - Main entry point: `app/desktop.py`.
    - Assets: `assets/jasper_icon.png`, `assets/jasper_icon.ico`.
    - Binaries & dynamic libraries: Faster-Whisper / CTranslate2 runtime DLLs, PySide6 Qt plugins, Playwright drivers.
  - Add build and validation PowerShell script: `scripts/build_windows_exe.ps1`.
  - Test build process or standalone configuration validation.
- **Files:**
  - `jasper.spec`
  - `scripts/build_windows_exe.ps1`
  - `docs/deployment/windows_packaging.md`
