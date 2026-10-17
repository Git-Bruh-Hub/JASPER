# Statement of Intent: Browser Automation & Everyday Web Tasks for JASPER

> **Status:** Confirmed  
> **Source:** Derived from `/interview-me` session on 2026-10-16.

---

## 1. Outcome
Build a real-world Browser Automation engine into JASPER using Playwright that can launch and control the user's chosen desktop browser (Google Chrome, Microsoft Edge, or Chromium) with a persistent user profile to execute everyday web tasks (e.g., opening webmail, extracting messages, and summarizing emails like 7-Eleven receipts/newsletters).

## 2. User & Context
- **Target User:** Personal PC user running JASPER on Windows 11 as a true desktop JARVIS companion.
- **Role Distinction:** Software development and IDE coding tasks are handled directly by Antigravity in the IDE. JASPER's role is everyday desktop companion, voice, screen awareness, and daily computer automation.

## 3. Why Now
JASPER already possesses dual-monitor screen vision, voice STT/TTS, and multi-agent coordination with approval dialogs, but currently lacks the "hands" to interact with web pages, open online accounts, or inspect logged-in services.

## 4. Success Criteria
1. The user can issue a command in chat or voice:
   `"open browser and go to my email, summarize the email from 7-eleven"`
2. JASPER launches or connects to the user's preferred browser (Chrome, Edge, or Chromium) using a persistent profile where sessions and logins are preserved.
3. JASPER navigates to the inbox/search, extracts relevant email content, and delivers a clear, concise summary in JASPER's conversation window.
4. The user can configure their preferred browser engine (Chrome, Edge, Chromium) in JASPER's Settings.

## 5. Constraints
- **Session Persistence:** Must use a persistent user profile directory so logins (2FA, Google, Outlook, etc.) do not need to be re-entered on every task.
- **Multi-Browser Support:** Must support system-installed Google Chrome (`channel="chrome"`), Microsoft Edge (`channel="msedge"`), and standalone Chromium.
- **Safety Boundary:** All click/type operations follow JASPER's `Risk.WRITE` approval policy, and web content is treated as untrusted data (`ExternalContent`).

## 6. Out of Scope
- Code writing / IDE development tools (reserved for Antigravity).
- Throwaway incognito-only browser sessions that discard login cookies.
- Background unmonitored credential dumping or keystroke logging.
