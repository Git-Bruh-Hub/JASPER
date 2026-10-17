# Tasks: Browser Automation with Multi-Browser & Persistent Profiles

- [x] Task 1: Multi-Browser & Persistent Context Engine
  - Acceptance: `BrowserController` supports `channel` (`chrome`, `msedge`, `chromium`), uses `launch_persistent_context` to retain login cookies/sessions in `~/.jasper/browser_profile`, and falls back safely to bundled Chromium if selected channel is missing.
  - Verify: Unit test `tests/test_browser_persistent.py` verifying persistent context launch options and channel fallbacks.
  - Files: `app/tools/browser.py`

- [x] Task 2: Settings Workspace Browser Configuration UI
  - Acceptance: `SettingsWorkspace` provides a clean UI section allowing user to choose their preferred browser (Chrome, Edge, Chromium) and view profile folder path, saving preference to config.
  - Verify: Test settings update and emission in UI tests.
  - Files: `app/ui/settings_workspace.py`

- [x] Task 3: High-Level Web Summarization & Agent Routing
  - Acceptance: Expose `browser_summarize` tool and wire into `desktop_wiring.py`, enabling natural agent execution of queries like "open browser and summarize the email from 7-eleven".
  - Verify: Orchestrator and coordinator tool tests.
  - Files: `app/tools/browser.py`, `app/agents/desktop_wiring.py`

- [x] Task 4: Regression & End-to-End Verification
  - Acceptance: All new tests in `tests/test_browser_persistent.py` pass and the full repository test suite (512 tests) remains 100% green.
  - Verify: `.\.venv\Scripts\python.exe -m pytest tests/`
  - Files: `tests/test_browser_persistent.py`
