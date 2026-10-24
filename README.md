# JASPER (v0.8.0)

**JASPER = Just Another Smart Program Executing Request**

Local-first, privacy-respecting personal AI assistant and autonomous desktop companion for Windows 11. Built on a capability-based security boundary with Ollama inference, explicit memory, PySide6 desktop workspace, multimodal vision, Hive Mind multi-agent coordination, scoped desktop autonomy, proactive companion observation, and real-time safety auditing.

---

## 🚀 Core Capabilities (v0.8.0)

- ⚡ **Scoped Desktop Autonomy & Multi-Turn Auto-Fix:**
  - High-precision sliced file reading (`read_text_file`) with line-range controls.
  - Non-destructive surgical chunk editing (`edit_file_chunk`) requiring exact substring verification.
  - Scoped shell command execution (`run_terminal_command`) bound to `workspace_root` with hard 30-second timeouts.
  - Natural intent routing auto-detecting coding, debugging, and task execution requests with multi-turn observation feedback and self-repair.
- 👁️ **Proactive Companion Observation (`DeltaScreenWatcher`):**
  - Zero-GPU perceptual screen diffing (<1ms CPU overhead via 32x32 grayscale downsampling).
  - Active window and task awareness notifying you when background builds, downloads, or jobs finish.
  - Objective-focused vision verification (`qwen3-vl:8b`) with natural `/watch [goal]` and `/stopwatch` desktop controls.
  - Zero continuous video streaming and a mandatory 10-minute maximum duration safety cap.
- 🛡️ **Total Safety & Interactive Audit Ledger:**
  - Human-in-the-loop modal approvals for all file modifications and terminal commands.
  - Recursive argument sanitization stripping credentials, tokens, and passwords across all depths.
  - Slide-out `AuditTimelineDrawer` (`/audit`) with live metric counters (`Total`, `Tools`, `Approved`, `Denied`), category filters, expandable JSON payload inspection, and one-click JSON export.
- 🎙️ **Local Voice STT/TTS:**
  - Faster-Whisper local speech-to-text with Windows CUDA DLL preloading and silence noise gating.
  - Windows native Speech TTS and optional Piper TTS.
- 🧠 **Explicit Long-Term Memory & Local Cognition:**
  - Deterministic SQLite memory (`remember that...`, `what do you remember about...`).
  - Cognitive mode routing across local models (`qwen3:8b`, `qwen3:14b`, `qwen3-vl:8b`).
- 💬 **Desktop Workspace:**
  - Multi-workspace dark PySide6 GUI with collapsible threaded chat sessions drawer (`+ New Chat`, rename, pin, delete).
  - Dual-monitor screen snipper and visual inspection workspace.

---

## 📋 Requirements

- **Operating System:** Windows 11
- **Python:** 3.12+
- **Inference Runtime:** [Ollama](https://ollama.ai) installed and running locally
- **Local Models:**
  ```powershell
  ollama pull qwen3:8b
  ollama pull qwen3:14b
  ollama pull qwen3-vl:8b
  ```

---

## 🛠️ Quick Start

### 1. Setup Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-desktop.txt
```

*(Optional: for voice support, install voice dependencies)*
```powershell
pip install -r requirements-voice.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` if you wish to customize model names, speech parameters, or workspace paths:
```powershell
Copy-Item .env.example .env
```

### 3. Launch JASPER
Launch the desktop application:
```powershell
python -m app.desktop
```
*(Or double-click `JASPER.bat` for silent background launch).*

The developer CLI remains accessible via:
```powershell
python -m app.main
```

---

## 🔒 Security & Capability Boundaries

JASPER enforces an uncompromising, fail-closed security boundary:
1. **Explicit Permission Gates:** Every file modification (`Risk.WRITE`) and shell execution (`Risk.EXECUTE`) unconditionally surfaces an un-ignorable modal approval dialog presenting tool name, target paths, exact parameters, and reason.
2. **Workspace Containment:** All filesystem access and shell executions are strictly canonicalized and pinned to `workspace_root`. Directory traversal and symlink escapes are blocked.
3. **Credential Protection:** Recursive argument sanitization redacts sensitive keys (`token`, `secret`, `password`, `key`, `credential`, `auth`, `bearer`) from all user-facing dialogs and audit representations.
4. **Fail-Closed Lifecycle:** Modal dismissals, Esc key presses, window closures, and request cancellations immediately abort execution and release resources safely.
5. **Zero Passive Video Streaming:** Proactive vision uses static in-memory 32x32 thumbnails; no video feeds are ever recorded or transmitted.

---

## 🗺️ Milestone Evolution Summary

| Milestone | Release | Core Capabilities | Verification Status |
| :--- | :--- | :--- | :--- |
| **Foundation & Core CLI** | `v0.1 – v0.2.4` | Local Ollama client, hardware grounding (`get_system_info`), read-only filesystem inspection, structured logging. | **Complete** |
| **Explicit Memory Layer** | `v0.3.0` | Deterministic SQLite keyword-overlap memory store. Only explicit commands persist memories. | **Complete** |
| **Desktop GUI & Voice Foundation** | `v0.4.0 – v0.4.2` | PySide6 dark UI, system tray, Faster-Whisper local CUDA STT, Windows Speech TTS. | **Complete** |
| **Multimodal Vision & Cancellation** | `v0.5.0 – v0.6.1` | Static image file inspection via `qwen3-vl:8b`, cognitive routing, full-stack cooperative cancellation tokens. | **Complete** |
| **Hive Mind Multi-Agent Core** | `v0.7.0 – v0.7.3` | Planner/Executor delegation, `ScopedPermissionManager`, async `ApprovalGate`, live-model verification harness. | **Complete** |
| **Desktop Autonomy & Observation** | `v0.8.0` | Surgical file chunk editing, scoped terminal commands, `DeltaScreenWatcher`, slide-out `AuditTimelineDrawer`. | **Current (GA)** |
| **Daily Driver Desktop Assistant** | `v0.9.0` | Global Windows hotkey overlay, ambient resource monitoring, scheduled task queue. | *Planned* |
| **Companion Integration & Mobile** | `v1.0.0` | Authenticated local REST daemon, secure mobile companion app (Tailscale/Wi-Fi), remote task approvals. | *Planned* |

---

## 📚 Technical Documentation

For in-depth architectural specifications, design rationales, and engineering decisions:
- [Architecture & Concurrency Flow](docs/ARCHITECTURE.md) — System request flow, cognitive modes, and capability boundaries
- [Architecture Decision Records (ADRs)](docs/DECISIONS.md) — 24 documented decisions on security, state machines, and fail-closed policies
- [Project Vision & Core Principles](docs/PROJECT_VISION.md) — Local-first privacy, bounded autonomy, and permission gating
- [Development Roadmap](docs/ROADMAP.md) — Detailed milestone tracking and future planning
- [v0.8.0 Release Notes](docs/release_notes/v0.8.0.md) — Comprehensive feature breakdown and test verification metrics
- [Windows Standalone Packaging](docs/deployment/windows_packaging.md) — Instructions for building the standalone PyInstaller release
