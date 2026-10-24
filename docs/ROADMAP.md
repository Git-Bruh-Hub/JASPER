# JASPER AI — Dependency-Aware Development Roadmap

> **Status:** Active Roadmap & Planning Baseline  
> **Guiding Principle:** Prioritize reliable authorization, predictable execution, recoverability, and trustworthy outcomes before expanding autonomous scope.

---

## Milestone Overview

```text
[M0: Foundation & Core Assistant] (v0.1 – v0.6.1) ──────────► COMPLETE (Verified)
      │
      ▼
[M1: Hive Mind Core Slices 1–7 & Hardening] (v0.7.0) ──────► COMPLETE (Verified)
      │
      ▼
[M2: Project Brain Bootstrap & Test Reconciliation] (v0.7.1) ─► COMPLETE (Verified)
      │
      ▼
[M2.1: Desktop Approval Bridge & Controlled E2E Verification] ─► COMPLETE (Verified)
      │
      ▼
[M3: Controlled Live-Model Validation & Readiness Review] (v0.7.2) ─► COMPLETE (Verified)
      │
      ▼
[M4: Git Working-Tree & Release Tag Consolidation] (v0.7.3) ──► COMPLETE (Verified)
      │
      ▼
[M5: Desktop Autonomy, Proactive Vision & Audit Ledger] (v0.8.0) ─► COMPLETE (Verified)
      │
      ▼
[M6: Daily Driver Desktop & Proactive Assistance] (v0.9.0) ────► PLANNED
      │
      ▼
[M7: Personal Intelligence & Companion Integration] (v1.0.0) ─► PLANNED
```

---

## Milestone Details

### Milestone 0: Core Foundation, Desktop, Vision & Cancellation (v0.1 – v0.6.1)
* **Status:** **COMPLETE** [VERIFIED]
* **Goal & Rationale:** Establish a stable local-first CLI and PySide6 desktop assistant with Ollama models, explicit SQLite memory, read-only system tools, Faster-Whisper voice, multimodal vision, and comprehensive request cancellation.
* **Scope Completed:**
  - Fast and main model routing (`qwen3:8b`, `qwen3:14b`).
  - Read-only tools (`get_system_info`, `read_text_file`).
  - Dark mode PySide6 GUI with system tray.
  - Faster-Whisper CUDA DLL preloading fix and silence noise gating.
  - `qwen3-vl:8b` image inspection bridge.
  - Cancellation token propagation across GUI workers and streaming requests.
* **Verification Method:** Verified through active codebase, commit history (`ec158b0`, `ef9d455`, `9ba956d`), and passing cancellation test suites (`test_engine_cancellation.py`, `test_request_cancellation.py`).

---

### Milestone 1: v0.7 Hive Mind Core — Slices 1–7 & Security Hardening
* **Status:** **COMPLETE** [VERIFIED]
* **Goal & Rationale:** Build a multi-agent delegation system (Planner/Executor) governed by capability permissions, async human approvals, retry limits, and disagreement resolution.
* **Scope Completed:**
  - Slice 1: Typed immutable contracts (`contracts.py`).
  - Slice 2: Scoped permission management (`scoped_permissions.py`) and audit logging (`audit.py`).
  - Slice 3: Asynchronous human-in-the-loop approval gate (`approval.py`).
  - Slice 4: Stateful Coordinator state machine (`coordinator.py`).
  - Slice 5: Retry policy with side-effect prohibition and `DisagreementResolver` (`retry.py`, commit `5a3a4e2`).
  - Slice 6: Planner/Executor multi-agent coordinator (`multi_agent_coordinator.py`, commit `2de2637`).
  - Slice 7: Orchestrator routing and LLM adapters (`adapters.py`, `orchestrator.py`, commit `c8ae534`).
  - Hardening: Coordinator argument canonicalization (TOCTOU defense) and adapter model-claim stripping (commits `7d3f182`, `a7005d2`).
* **Verification Method:** 159 passing unit/integration tests across `tests/test_coordinator.py`, `test_security_forgeries.py`, `test_approval_gate.py`, `test_slice5_retry_failure.py`, `test_slice6_agent_logic.py`, `test_adapters.py`.

---

### Milestone 2: Project Brain Bootstrap & Test Reconciliation (v0.7.1)
* **Status:** **COMPLETE** [VERIFIED]
* **Goal & Rationale:** Establish a single, authoritative, evidence-based Project Brain (`PROJECT_VISION.md`, `PROJECT_STATE.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `DECISIONS.md`, `AGENTS.md`), reconcile stale sections in `JASPER.md`, and preserve local regression tests.
* **Scope Completed:**
  - Created 6 core Project Brain documents.
  - Aligned documentation with actual Git history (`a7005d2`).
  - Preserved untracked artifacts (`diff.patch`, `docs/`, `security-recovery-backup/`, `graphify-out/`).
* **Verification Method:** Full suite verification (448 tests passing).

---

### Milestone 2.1: Desktop Approval Bridge, Modal Presentation & Controlled Verification (Steps 7–16)
* **Status:** **COMPLETE** [VERIFIED]
* **Goal & Rationale:** Implement guarded coordinator recovery, thinking-tag response sanitization, a thread-safe approval resolution API, PySide6 desktop approval bridge, and modal dialog. Verify the full approval lifecycle end-to-end using deterministic dependency injection without enabling autonomous execution in production desktop configuration.
* **Scope Completed:**
  - **Guarded Recovery:** `MultiAgentCoordinator.reset()` transitioning from `ERROR` back to `IDLE` with cleared gates; `PLANNER_REJECTION` audit events (Steps 7–8).
  - **Response Sanitization:** `sanitize_thinking_tags` in `app/core/response.py` stripping `<think>` tags cleanly (Step 9).
  - **Thread-Safe Approval API:** `Coordinator.resolve_approval` and `ApprovalGate` resolution with audit events and timeout cleanup (Steps 11–12).
  - **Shutdown Hardening:** `MainWindow.closeEvent` dismisses active approvals and terminates workers within 3000ms (Step 13).
  - **Desktop Approval Bridge & Dialog:** `JasperWorker.approval_requested` signal, `JasperWorker.resolve_approval` slot, and modal `ApprovalDialog` in PySide6 with Esc/close denial (Steps 14A–14B).
  - **Controlled E2E Verification:** 11 deterministic end-to-end tests in `tests/test_desktop_approval_e2e.py` covering all 15 required approval/denial/timeout/shutdown scenarios via test-injected callables (Step 15).
  - **Project Brain Reconciliation:** Authoritative documentation and handover preparation (Step 16).
* **Boundary Invariant:** Desktop autonomous mode remains completely disabled in normal configuration (`app/desktop.py` leaves `coordinator=None` and `multi_agent_coordinator=None`).
* **Verification Method:** 11/11 passing tests in `tests/test_desktop_approval_e2e.py`; 448/448 passing tests in full suite.

---

### Milestone 3: Controlled Live-Model Runtime Validation & Readiness Review (v0.7.2)
* **Status:** **COMPLETE** [VERIFIED in Steps 17–18B]
* **Goal & Rationale:** Conduct an independent architecture and privacy review of the desktop approval boundary, build an isolated live harness with scratch tool registries, and execute a controlled runtime validation using a live local Ollama model (`qwen3:14b`). **Desktop autonomous mode remains disabled by default.**
* **Scope Completed:**
  - **Privacy Review & Hardening (Steps 17A–17C):** Audited argument display paths; implemented recursive sanitization in `app/ui/approval_dialog.py` protecting nested dicts and lists against credential exposure; added 9 privacy unit tests.
  - **Isolated Live-Model Harness (Step 18A):** Built standalone `tests/support/live_harness.py` with scratch `ToolRegistry` (strictly scoped to `get_system_info` for read-only and `mock_safe_action` for approval) and 8 deterministic contract tests (`tests/test_live_harness_contracts.py`).
  - **Sequential Live Smoke Tests (Step 18B):**
    - **Test A (Read-Only):** Model called `get_system_info` without write tools; CPU and OS reported accurately; 0 mock calls.
    - **Test B (Approval Allow):** Model called `mock_safe_action`; approval surfaced and resolved `granted=True`; mock handler executed post-approval (call count 1); coordinator returned `IDLE`.
    - **Test C (Approval Deny):** Model called `mock_safe_action`; approval surfaced and resolved `granted=False`; mock handler was blocked (call count 0); coordinator halted safely in `ERROR`.
  - **Boundary Invariant Maintained:** `app/desktop.py` unchanged; production desktop `/auto` remains unconfigured and fails closed.
* **Verification Method:** Live sequential runs against local Ollama `qwen3:14b` + 8 contract tests + 465 full suite tests passing.

---

### Milestone 4: Git Working-Tree & Release Tag Consolidation (v0.7.3)
* **Status:** **COMPLETE** [VERIFIED in commit `c1b23eb`]
* **Goal & Rationale:** Staged, reviewed, and committed accumulated working-tree changes into atomic commits, verified passing test suite, and merged into `main` as `v0.7.3`.

---

### Milestone 5: Desktop Autonomy, Proactive Vision & Audit Ledger (v0.8.0)
* **Status:** **COMPLETE** [VERIFIED in `feature/desktop-autonomy`]
* **Goal & Rationale:** Empower JASPER with scoped desktop autonomy to read files, surgically edit code chunks, execute verified terminal commands, proactively observe background jobs via perceptual screen diffing, and provide total safety visibility via an interactive audit timeline ledger.
* **Scope Completed:**
  - Surgical filesystem and terminal execution tools (`read_text_file`, `edit_file_chunk`, `run_terminal_command`) bound to `workspace_root` with 30-second timeouts.
  - Multi-turn autonomous problem-solving loop with feedback injection (stdout/stderr, file diffs, screen captures) and natural intent routing.
  - Low-overhead proactive observation (`DeltaScreenWatcher`, 32x32 grayscale downsampling, <1ms, 0% GPU load, `/watch [goal]`, `/stopwatch`).
  - Thread-safe in-memory audit ledger (500 events) and slide-out `AuditTimelineDrawer` (`/audit`, real-time metric chips, JSON export).
* **Verification Method:** Verified across 577 passing unit and integration tests (`tests/test_desktop_autonomy_tools.py`, `tests/test_autonomous_problem_solving.py`, `tests/test_delta_watcher.py`, `tests/test_audit_timeline.py`).

---

### Milestone 6: Personal Daily Driver & Proactive Assistance (v0.9)
* **Status:** **PLANNED**
* **Goal & Rationale:** Transform JASPER into a seamless daily assistant with global Windows hotkeys, ambient background monitoring, and scheduled reminder tasks.
* **Dependencies:** Milestone 5 complete.
* **Scope:**
  - Global Windows hotkey overlay.
  - Background system resource monitor emitting alerts when VRAM/RAM exceeds thresholds.
  - Scheduled tasks and reminder queue in SQLite.
* **Non-Scope:** Unrestricted background mouse/keyboard automation or continuous screen recording.

---

### Milestone 7: Long-Term Personal Intelligence & Companion Integration (v1.0)
* **Status:** **PLANNED**
* **Goal & Rationale:** Achieve the full JARVIS-like vision: authenticated local REST API, secure mobile companion app (Tailscale/local Wi-Fi), and remote push notification approval prompts for long-running desktop tasks.
* **Dependencies:** Milestones 1–6 complete.
* **Scope:**
  - Local TLS/token-authenticated REST daemon exposed by the desktop core.
  - Mobile client for remote text/voice input and approval responses.
  - Comprehensive multi-agent cognitive loop with reflection and long-term memory synthesis.
