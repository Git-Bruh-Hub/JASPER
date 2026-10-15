# JASPER AI — Formal Project Handover

> **Handover Date:** 2026-10-15  
> **Status:** Active Master Handover Document  
> **Authority:** Local Git inspection, Python test runner execution, and live-model verification evidence.

---

## 1. Project Purpose & Current Implementation Status

### Purpose
**JASPER** (**J**ust **A**nother **S**mart **P**rogram **E**xecuting **R**equest) is a local-first personal AI assistant foundation for Windows 11. It is designed to deliver deep multimodal reasoning (text, Faster-Whisper voice, vision, explicit SQLite memory) while enforcing an application-level capability security boundary between model reasoning and computer execution.

### Current Implementation Status: v0.7.3 (Milestones 0, 1, 2, 2.1, and 3 Complete)
- **Core Cognitive Architecture:** Multi-agent Hive Mind (`MultiAgentCoordinator`, `PlannerAgent`, `ExecutorAgent`, `DisagreementResolver`, `CognitiveRouter`).
- **Authorization & Approval Lifecycle:** In-process capability permissions (`ScopedPermissionManager`), asynchronous human-in-the-loop approval gates (`ApprovalGate`), thread-safe resolution API (`Coordinator.resolve_approval`), and guarded coordinator recovery (`MultiAgentCoordinator.reset()`).
- **Desktop UI Integration:** PySide6 dark UI (`MainWindow`), background worker bridge (`JasperWorker`), modal approval dialog (`ApprovalDialog`) with recursive credential redaction, and graceful shutdown hardening.
- **Controlled Live Validation:** Isolated live-model test harness (`tests/support/live_harness.py`) with scratch tool registries, deterministic contract tests, and verified live inference runs against local Ollama `qwen3:14b`.
- **Verified Suite:** **465 automated tests passing** (`0 failed`) in the local virtual environment.

---

## 2. Architecture & Security Boundaries

JASPER enforces an **in-process object-capability permission model** in Python. The LLM cannot grant itself permissions or invoke arbitrary system tools:

```text
User Request (CLI / Desktop / Voice)
       │
       ▼
Orchestrator.respond()
       │
       ▼
CognitiveRouter.route()
       │
       ├─► SIMPLE / COLLABORATIVE / DEEP ──► Ollama (qwen3:8b / 14b) [Bounded Tool Loops]
       │
       └─► AUTONOMOUS ──► MultiAgentCoordinator.run_multi_agent()
                                │
                                ├─► PlannerAgent (Decomposes task into ProposedAction)
                                │
                                ├─► ExecutorAgent (Formulates concrete tool invocations)
                                │
                                ├─► DisagreementResolver (Checks alignment; halts if >3 rounds)
                                │
                                ├─► ScopedPermissionManager & Canonicalization (TOCTOU Defense)
                                │
                                └─► ApprovalGate (Halts for Risk.WRITE; prompts user)
                                          │
                                          ├─ Allow ──► Tool Execution ──► Coordinator IDLE
                                          └─ Deny  ──► PermissionError ──► Coordinator ERROR
```

### Key Security Invariants
1. **The Model Proposes; The Permission Manager Decides:** Models emit pure declarations of intent (`ProposedAction`). Any authority or risk claims in model JSON are stripped by `PlannerAdapter` and `ExecutorAdapter`; scopes are derived strictly from the local `ToolRegistry`.
2. **Path Canonicalization & Argument Overwrite:** Paths for filesystem tools are canonicalized against `workspace_root` via `Path.resolve()`. The coordinator overwrites `action.arguments[tool.path_argument]` with the canonical path string before dispatching to the handler, eliminating TOCTOU discrepancies.
3. **Absolute Prohibition on Retrying Side Effects:** `RetryPolicy` suppresses automatic retries on any operation marked `SIDE_EFFECT` or returning ambiguous `UNKNOWN` outcomes to prevent duplicated writes.
4. **Desktop Presentation Privacy:** `sanitize_arguments()` in `ApprovalDialog` recursively traverses nested dictionaries and lists to redact sensitive keys (`token`, `secret`, `password`, `key`, `credential`, `auth`, `bearer`) at all depths.
5. **Desktop Autonomous Boundary:** In standard production desktop startup ([`app/desktop.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/desktop.py)), `coordinator=None` and `multi_agent_coordinator=None`. Requests to `/auto` return `"Autonomous mode is not enabled."` and fail closed.

---

## 3. Completed Milestones & Test Evidence

| Milestone | Scope & Deliverables | Verification Status |
| :--- | :--- | :--- |
| **M0: Foundation & Core Assistant** | Local Ollama client (`qwen3:8b`, `qwen3:14b`), read-only tools (`get_system_info`), explicit SQLite memory, Faster-Whisper voice with CUDA DLL preloading, PySide6 desktop GUI, request cancellation tokens. | **VERIFIED** (Commits through `ef9d455`) |
| **M1: Hive Mind Core Slices 1–7** | Typed immutable contracts (`contracts.py`), ScopedPermissionManager, ApprovalGate, stateful Coordinator, side-effect retry guards, Planner/Executor multi-agent delegation, TOCTOU argument canonicalization, model claim stripping. | **VERIFIED** (Commits `b05e2d9` to `a7005d2`) |
| **M2: Project Brain Reconciliation** | Authoritative Project Brain documents (`PROJECT_STATE.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `DECISIONS.md`, `PROJECT_VISION.md`, `AGENTS.md`); preserved untracked artifacts. | **VERIFIED** |
| **M2.1: Desktop Approval Bridge & E2E** | Guarded coordinator recovery (`reset()`), response sanitization (`sanitize_thinking_tags`), thread-safe resolution API (`resolve_approval`), desktop Qt signal bridge (`approval_requested`), modal `ApprovalDialog`, 11 deterministic end-to-end tests (`tests/test_desktop_approval_e2e.py`). | **VERIFIED** (448 tests passing) |
| **M3: Controlled Live Validation (Steps 17–18B)** | Privacy review and recursive argument redaction (`app/ui/approval_dialog.py`); isolated live harness (`tests/support/live_harness.py`) with scratch tool registry; 8 deterministic contract tests (`tests/test_live_harness_contracts.py`); sequential live smoke tests against local Ollama `qwen3:14b`. | **VERIFIED** (465 tests passing) |

### Live Smoke Test Outcomes (Local Ollama `qwen3:14b`)
- **Test A (Read-Only Mode):** Model correctly called `get_system_info`; reported OS and CPU; 0 write tools available; 0 mock calls; exit code 0. [VERIFIED]
- **Test B (Approval Flow - Allow):** Model called `mock_safe_action`; approval request surfaced to notifier; resolved with `granted=True`; in-memory mock handler executed post-approval (`call_count=1`); returned `IDLE`; exit code 0. [VERIFIED]
- **Test C (Approval Flow - Deny):** Model called `mock_safe_action`; approval request surfaced to notifier; resolved with `granted=False`; mock handler was blocked (`call_count=0`); coordinator transitioned safely to `ERROR` (fail-closed); exit code 0. [VERIFIED]

---

## 4. Current Known Risks & Unverified Areas

1. **Live Harness vs. Production Desktop Separation:** Step 18B verified live model inference and approval enforcement using an isolated scratch registry (`tests/support/live_harness.py`). Normal desktop startup (`app/desktop.py`) remains intentionally unconfigured for `/auto` to prevent untested autonomous execution in daily use.
2. **Manual Visual UI Acceptance Pending:** While headless Qt tests proved dialog event handling, keyboard Esc dismissal, and argument redaction, visual inspection on a physical Windows 11 display by a human user has not yet been conducted.
3. **Filesystem TOCTOU Residual Risk:** While the `Coordinator` canonicalizes path arguments and overwrites `action.arguments[tool.path_argument]`, the underlying filesystem tools in `app/tools/filesystem.py` open files by path rather than retaining an open file descriptor handle.
4. **Branch Naming Discrepancy:** The active working branch is named `fix/v0.6.1-cancellation`, but its commit history and current working copy contain the complete v0.7.x Hive Mind architecture and desktop approval implementation.

---

## 5. Exact Local Test Commands

All test and Python commands **MUST** use the local project virtual environment:

```powershell
# 1. Full Regression Test Suite (465 tests)
.\.venv\Scripts\python.exe -m pytest tests -q

# 2. Live Harness Contract Tests (8 tests)
.\.venv\Scripts\python.exe -m pytest tests/test_live_harness_contracts.py -q

# 3. Desktop Approval End-to-End Tests (11 tests)
.\.venv\Scripts\python.exe -m pytest tests/test_desktop_approval_e2e.py -q

# 4. Desktop Approval Dialog & Privacy Tests (13 tests)
.\.venv\Scripts\python.exe -m pytest tests/test_desktop_approval_dialog.py -q

# 5. Coordinator Approval Gate Lifecycle Tests (22 tests)
.\.venv\Scripts\python.exe -m pytest tests/test_coordinator_approval.py -q

# 6. Sequential Live-Model Smoke Tests (Requires Ollama with qwen3:14b running)
# Test A: Read-Only Mode
.\.venv\Scripts\python.exe -m tests.support.live_harness --mode read_only --prompt "Check system info and report OS and CPU."

# Test B: Approval Flow (Explicit Allow)
.\.venv\Scripts\python.exe -m tests.support.live_harness --mode approval --decision allow --prompt "Call mock_safe_action with payload 'live_approval_test'."

# Test C: Approval Flow (Explicit Deny)
.\.venv\Scripts\python.exe -m tests.support.live_harness --mode approval --decision deny --prompt "Call mock_safe_action with payload 'live_denial_test'."
```

---

## 6. Current Git / Workspace State & Preservation Warnings

### Git Status
- **Current Branch:** `fix/v0.6.1-cancellation` [VERIFIED]
- **Current HEAD:** `a7005d2bbe5a1a39d2f6577c14fe5ba74536cfd2` (`a7005d2`) [VERIFIED]
- **Staged Changes:** 0 (`git diff --cached` is empty) [VERIFIED]
- **Production Desktop Code:** [`app/desktop.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/desktop.py) is **completely unchanged** (0 diff) [VERIFIED]

### MANDATORY PRESERVATION INVARIANTS:
1. **Never run destructive Git commands:** Do not execute `git reset --hard`, `git clean -fd`, `git restore .`, or `git checkout -- .`.
2. **Never use `git add .`:** Only stage explicit, named files after user review.
3. **Preserve all untracked artifacts:**
   - `diff.patch` (cumulative patch archive)
   - `docs/` (`docs/planning/1_PRD.md` through `6_Implementation_Plan.md`)
   - `security-recovery-backup/`
   - `graphify-out/`
   - `tests/support/` (`live_harness.py`)
   - All Project Brain documents (`PROJECT_STATE.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `DECISIONS.md`, `PROJECT_VISION.md`, `AGENTS.md`)
   - New test files (`tests/test_live_harness_contracts.py`, `tests/test_desktop_approval_e2e.py`, `tests/test_desktop_approval_bridge.py`, `tests/test_desktop_approval_dialog.py`, `tests/test_desktop_shutdown.py`, `tests/test_coordinator_approval.py`, `tests/test_response_sanitization.py`)

---

## 7. How to Resume Work with Antigravity

When starting a new conversation or session with Antigravity:
1. **Provide this file (`HANDOVER.md`) and direct the agent to the Project Brain:**
   - [`PROJECT_STATE.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/PROJECT_STATE.md): Ground-truth state and verified test metrics.
   - [`ARCHITECTURE.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/ARCHITECTURE.md): System flows, contracts, and security boundaries.
   - [`ROADMAP.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/ROADMAP.md): Ordered milestones and acceptance criteria.
   - [`DECISIONS.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/DECISIONS.md): Architectural decisions ADR-001 through ADR-020.
   - [`AGENTS.md`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/AGENTS.md): Binding rules for coding agents.
2. **Prompt for the new agent:**
   ```text
   Read HANDOVER.md, PROJECT_STATE.md, and AGENTS.md before proposing any action.
   Use .\.venv\Scripts\python.exe for all Python/pytest commands.
   Do not run git reset, clean, or checkout commands that discard work.
   Do not stage or commit without explicit approval.
   Verify that all 465 tests pass before proceeding.
   ```

---

## 8. Recommended Next Milestone

### Recommended Milestone: Milestone 4 — Git Working-Tree & Release Tag Consolidation (v0.7.3)

#### Why This Milestone?
The working tree has accumulated significant verified, tested functionality across Steps 7–18B:
- 16 modified tracked files.
- 19 untracked files and test suites.
- The active branch name (`fix/v0.6.1-cancellation`) no longer reflects the repository's reality (full v0.7.3 Hive Mind multi-agent system).

Consolidating these changes into clean, atomic commits with user authorization and creating a milestone release tag (`v0.7.2` or `v0.7.3`) locks in the verified 465-test baseline and eliminates working-tree drift.

#### Scope of Milestone 4:
1. Review working tree status and diffs with the user.
2. Group changes into logical atomic commits:
   - Commit 1: Core Multi-Agent Hardening & Recovery (reset, planning rejection audit, response sanitization).
   - Commit 2: Desktop Approval Signal Bridge & Modal Dialog (PySide6 worker slots, approval dialog with recursive privacy redaction, shutdown hardening).
   - Commit 3: Test Suites & Live Harness (desktop E2E tests, live harness, deterministic contract tests).
   - Commit 4: Project Brain & Handover Documentation.
3. Create release tag `v0.7.2` (or `v0.7.3`).
4. Reconcile branch tracking (`release/v0.7.2` or merge to `main`).

#### Alternatives Considered:
- **Alternative B: Milestone 3.1 — Manual Visual UI Acceptance:**  
  *Description:* Launch the desktop application locally and have the user physically click Allow/Deny and test Esc dismissal on Windows 11.  
  *Trade-off:* Valuable for UX confidence, but leaves a large uncommitted working tree exposed to accidental drift.
- **Alternative C: Milestone 5 — Bounded Controlled Tool Expansion (Filesystem Write & Web):**  
  *Description:* Begin implementing `file.write` within `workspace_root` and read-only web research.  
  *Trade-off:* Premature. Adding new write capabilities on top of an uncommitted, unbranched working tree dramatically increases risk.

#### Cost of Deferring Milestone 4:
Deferring Git consolidation means every future task operates in a cluttered working tree where accidental resets, merge conflicts, or untracked file loss can destroy days of verified work. Consolidating the baseline now provides absolute safety for future milestones.
