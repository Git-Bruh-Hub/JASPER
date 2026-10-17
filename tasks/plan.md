# Implementation Plan: Browser Automation with Multi-Browser & Persistent Profiles

## User Review Required
> [!IMPORTANT]
> This milestone gives JASPER the ability to control system-installed Google Chrome, Microsoft Edge, or bundled Chromium using a persistent user profile directory (`~/.jasper/browser_profile`). This allows login sessions (webmail, cloud dashboards, etc.) to persist across tasks so JASPER can perform real-world tasks like opening email and summarizing messages without repeated logins.

---

## Proposed Slices

### Slice 1: Multi-Browser & Persistent Context Engine
- **Files:** `app/tools/browser.py`
- **Goal:**
  - Add `BrowserConfig` dataclass supporting `channel` (`"chrome"`, `"msedge"`, `"chromium"`), `user_data_dir`, and `headless` mode.
  - Switch `BrowserController` to Playwright `launch_persistent_context` pointing to `~/.jasper/browser_profile`.
  - Add automatic fallback to bundled Chromium if the requested channel (e.g. Chrome or Edge) is not installed on the system.
  - Implement `browser_summarize(url_or_topic: str)` high-level extractor.

### Slice 2: Settings Workspace Browser UI Integration
- **Files:** `app/ui/settings_workspace.py`
- **Goal:**
  - Add "Browser & Web Automation" settings card in `SettingsWorkspace`.
  - Provide dropdown to select Default Browser: `Google Chrome`, `Microsoft Edge`, `Bundled Chromium`.
  - Display the active persistent profile location with a quick "Open Profile Folder" button.
  - Persist the selected browser in `config/settings.json`.

### Slice 3: Desktop Tool Wiring & High-Level Task Routing
- **Files:** `app/agents/desktop_wiring.py`, `app/core/orchestrator.py`
- **Goal:**
  - Register `browser_summarize` and update browser tool descriptions for natural language routing.
  - Ground the model to recognize requests like "open browser and go to my email, summarize the email from 7-eleven" and decompose into navigation, element observation, and extraction.

### Slice 4: Comprehensive Test Suite & Full Regression Verification
- **Files:** `tests/test_browser_persistent.py`
- **Goal:**
  - Test browser configuration, persistent profile directory resolution, channel fallback, and DOM summarization.
  - Verify settings saving and loading for browser configuration.
  - Run full test suite (`tests/`) to ensure all 507+ tests pass with zero regressions.
