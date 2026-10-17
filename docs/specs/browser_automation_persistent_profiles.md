# Spec: Browser Automation with Multi-Browser & Persistent Profiles

## 1. Objective
Enable JASPER to act as an everyday web automation assistant by controlling the user's preferred desktop browser (Google Chrome, Microsoft Edge, or Chromium) using a persistent profile directory. This preserves logins (Google/Gmail, Outlook, Amazon, etc.) across sessions, allowing the user to request tasks like:
`"jasper open browser and go to my email, summarize the email from 7-eleven"`

## 2. Tech Stack & Dependencies
- **Language / Runtime:** Python 3.12 (`.\.venv\Scripts\python.exe`)
- **Automation Framework:** Playwright (`sync_api`) with `launch_persistent_context`
- **Supported Browser Channels:**
  - `chrome` (System-installed Google Chrome)
  - `msedge` (System-installed Microsoft Edge on Windows 11)
  - `chromium` (Bundled Playwright Chromium fallback)
- **Profile Storage:** `%USERPROFILE%/.jasper/browser_profile` (or `~/.jasper/browser_profile`)
- **UI Framework:** PySide6 (`SettingsWorkspace` configuration)

## 3. Commands
- **Unit & Integration Tests:**  
  `.\.venv\Scripts\python.exe -m pytest tests/test_browser_persistent.py -v`
- **Full Test Suite:**  
  `.\.venv\Scripts\python.exe -m pytest tests -q`
- **Desktop Application Run:**  
  `.\.venv\Scripts\python.exe -m app.desktop`

## 4. Architecture & Interface Design

### 4.1. BrowserConfig Dataclass
```python
@dataclass
class BrowserConfig:
    channel: str = "chrome"  # "chrome", "msedge", "chromium"
    headless: bool = False
    user_data_dir: Path | None = None
    viewport_width: int = 1280
    viewport_height: int = 800
```

### 4.2. Persistent Context Initialization (`BrowserController`)
Instead of launching an ephemeral, blank browser with `chromium.launch()` and `browser.new_context()`, `BrowserController` initializes via Playwright's `launch_persistent_context`:
```python
user_dir = self.config.user_data_dir or (Path.home() / ".jasper" / "browser_profile")
user_dir.mkdir(parents=True, exist_ok=True)

launch_kwargs = {
    "user_data_dir": str(user_dir),
    "headless": self.config.headless,
    "viewport": {"width": self.config.viewport_width, "height": self.config.viewport_height},
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
    ],
}
if self.config.channel in ("chrome", "msedge"):
    launch_kwargs["channel"] = self.config.channel

self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
```

### 4.3. High-Level Web Summarization Tool
In addition to step-by-step DOM tools (`browser_click`, `browser_type`), expose:
- `browser_summarize(url: str, topic_or_query: str)`: Navigates to the page, extracts readable content or search results matching the query, and produces a structured summary of the target information.

### 4.4. UI Settings Integration (`SettingsWorkspace`)
In `SettingsWorkspace`, add a **Browser & Web Automation** section:
- **Default Browser Engine Dropdown:** `Google Chrome (Recommended)`, `Microsoft Edge`, `Bundled Chromium`.
- **Browser Headless Toggle:** Visible (Headed, default) vs. Background (Headless).
- **Persistent Profile Path:** Shows the active profile directory with a "Open Profile Folder" button.

## 5. Testing Strategy
1. **`tests/test_browser_persistent.py`:**
   - Test channel selection logic (`chrome`, `msedge`, `chromium`).
   - Test fallback to `chromium` if system Chrome or Edge executable is not found.
   - Test `launch_persistent_context` parameter generation and profile folder creation.
   - Test DOM reading and interactive element extraction with persistent context.
   - Test settings serialization and deserialization for browser channel preferences.

## 6. Boundaries & Invariants
- **Always:** Use persistent context so login sessions and cookies survive across app restarts.
- **Always:** Route interactive actions that mutate web pages (`browser_click`, `browser_type`) through the `ApprovalGate` (`Risk.WRITE`).
- **Always:** Allow graceful fallback to bundled Chromium if the user's selected channel (e.g. Chrome) is not installed on the system.
- **Ask First:** Deleting or resetting the user's persistent profile directory.
- **Never:** Log, store, or transmit captured passwords or session cookies outside local memory.

## 7. Success Criteria
- [ ] User can select Google Chrome, Microsoft Edge, or Chromium in JASPER Settings.
- [ ] Browser launches with persistent user data directory (`~/.jasper/browser_profile`).
- [ ] User can log into their webmail or web accounts once, and subsequent JASPER tasks retain the logged-in session.
- [ ] Asking JASPER to check a page or summarize an email reads the content from the persistent browser session and returns a clean summary.
- [ ] 100% test pass rate across unit, integration, and full regression test suites.
