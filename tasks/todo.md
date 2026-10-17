# Todo List: C → B → A Implementation

- [x] Task 1 (Option C): Desktop Notification Toasts & System Tray Alerts
  - [x] 1.1 Add `JASPER_NOTIFICATIONS_ENABLED` config in `app/core/config.py` and settings toggle.
  - [x] 1.2 Create `ToastBanner` in `app/ui/toast_banner.py` adhering to `frontend-ui-engineering` dark-theme aesthetics.
  - [x] 1.3 Wire `notify(title, message, level)` into `app/ui/main_window.py` for task completion, approvals, and errors.
  - [x] 1.4 Write unit tests in `tests/test_notifications.py` and verify all tests pass.

- [x] Task 2 (Option B): Expanded Browser Automation Capabilities
  - [x] 2.1 Add multi-tab management (`new_tab`, `switch_tab`, `close_tab`, `list_tabs`) in `app/tools/browser.py`.
  - [x] 2.2 Add email extraction helper (`read_inbox`) for webmail services (Gmail, Outlook, generic) in `app/tools/browser.py`.
  - [x] 2.3 Wire new browser tools into `app/agents/desktop_wiring.py`.
  - [x] 2.4 Write unit tests in `tests/test_browser_expanded.py` and verify all tests pass.

- [x] Task 3 (Option A): Windows Deployability & Standalone Packaging
  - [x] 3.1 Create `jasper.spec` PyInstaller specification with assets, icon, and DLL hooks.
  - [x] 3.2 Create `scripts/build_windows_exe.ps1` for automated compilation and packaging.
  - [x] 3.3 Validate build configuration and packaging dependencies.
