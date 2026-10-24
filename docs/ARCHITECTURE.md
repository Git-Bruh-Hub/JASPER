# JASPER AI — Architecture Specification

> **Status:** Current Implemented Architecture  
> **Authority:** Derived directly from active codebase (`app/`) and verified test suites (`tests/`).

---

## 1. System Overview & Entry Points

JASPER operates as a local-first desktop application with two primary entry points:
1. **Desktop GUI Application:** [`app/desktop.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/desktop.py)
   - Built on PySide6 (`QApplication`).
   - Main window: [`app/ui/main_window.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/main_window.py).
   - Offloads all asynchronous operations to QThread workers: [`app/ui/worker.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/worker.py).
2. **CLI Development Shell:** [`app/main.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/main.py)
   - Interactive terminal loop supporting text prompts, `:vision`, `:voice`, and `:conversation` commands.

---

## 2. Core Request Flow

The central request pipeline is managed by the `Orchestrator` in [`app/core/orchestrator.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/core/orchestrator.py):

```text
User Input (Text / Voice / Image)
      │
      ▼
Orchestrator.respond()
      │
      ├── 1. Memory Command Check (e.g., "remember that...") -> SQLiteMemory [Local Return]
      ├── 2. Direct Hardware Fact Check -> get_system_info [Live Tool Observation Return]
      ├── 3. Hardware Grounding (CPU/RAM explanation) -> Grounded Spec Formatting
      ├── 4. Attached Image Check -> VisionManager.analyze() -> System Observation Prompt
      │
      ▼
CognitiveRouter.route()  [app/agents/router.py]
      │
      ├─► CognitiveMode.SIMPLE       ──► Ollama (qwen3:8b)   [0 tool rounds]
      ├─► CognitiveMode.COLLABORATIVE──► Ollama (qwen3:14b)  [Up to 3 tool rounds via CognitiveEngine]
      ├─► CognitiveMode.DEEP         ──► Ollama (qwen3:14b)  [Up to 5 tool rounds via CognitiveEngine]
      │
      └─► CognitiveMode.AUTONOMOUS   ──► MultiAgentCoordinator.run_multi_agent()
                                           [Planner/Executor Delegation Loop]
```

---

## 3. Hive Mind Multi-Agent Architecture (v0.7)

### A. Subsystem Roles & Responsibilities
- **`Coordinator` ([`app/agents/coordinator.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/coordinator.py)):**
  - Base class providing lifecycle state management: `IDLE → PLANNING → ACTING → OBSERVING → VERIFYING → IDLE` (or `ERROR`).
  - Enforces `CoordinatorBudget` (token caps, agent round caps, tool round caps).
  - Enforces `RetryPolicy` and manages audit logging.
- **`MultiAgentCoordinator` ([`app/agents/multi_agent_coordinator.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/multi_agent_coordinator.py)):**
  - Inherits from `Coordinator`.
  - Orchestrates high-level planner and executor callables.
  - Interposes `DisagreementResolver` to detect and resolve divergence between planned and proposed tool actions.
- **`PlannerAgent` ([`app/agents/planner.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/planner.py)):**
  - Decomposes the user task into a structured `PlannerResult` containing high-level `ProposedAction` declarations.
- **`ExecutorAgent` ([`app/agents/executor.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/executor.py)):**
  - Takes the `PlannerResult` and any `DisagreementFeedback`, formulating concrete tool invocations for the Coordinator.

### B. Typed Contracts ([`app/agents/contracts.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/contracts.py))
All inter-agent communication relies on pure, immutable data containers:
- `ProposedAction`: A declaration of intent (tool name, arguments, requested scope, rationale). **It is not an instruction to execute.**
- `PermissionScope`: Describes the capability required (risk level, canonical resource scope, operation verb, approval requirement).
- `AgentResult`: Container for proposed actions, text summary, and execution status.
- `ExternalContent`: Untrusted string wrapper for retrieved data (files, web pages). Explicitly cannot grant authority or override permissions.

### C. Adapters & Deserialization Defense ([`app/agents/adapters.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/adapters.py))
- `PlannerAdapter` and `ExecutorAdapter` translate raw LLM JSON/tool calls into typed contracts.
- **Security Rule:** Any authority claims (risk category, permission scope, approval bypasses) produced by the model are discarded. The adapter reconstructs scopes and approval requirements strictly from the local `ToolRegistry`.

### D. Guarded Coordinator Recovery ([`app/agents/multi_agent_coordinator.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/multi_agent_coordinator.py))
- A coordinator that encounters an uncanonicalizable action, budget exhaustion, or unresolvable disagreement transitions to `CoordinatorState.ERROR` to prevent cascading failures.
- `MultiAgentCoordinator.reset()` provides safe, guarded recovery: resets state back to `IDLE`, clears pending approval gates and execution futures, and reinitializes budget limits, allowing the retained instance to safely handle subsequent user requests.

---

## 4. Permission Model & Security Boundaries

### A. Object-Capability Permission System
> **IMPORTANT SECURITY NOTE:** JASPER's security boundary is an **application-level object-capability system** implemented in Python. It is **not** an OS-level sandbox (such as Windows AppContainer, Docker, or seccomp). It protects against prompt injection and unauthorized agent action within the Python process boundary.

1. **`ToolRegistry` ([`app/tools/registry.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/tools/registry.py)):**
   - Central authority for tool definitions.
   - Assigns a fixed `Risk` level to each tool: `READ`, `WRITE`, `EXECUTE`, `NETWORK`, `DESTRUCTIVE`, `ADMIN`.
   - Associates filesystem tools with their required path argument name (`path_argument`).
2. **`ScopedPermissionManager` ([`app/core/scoped_permissions.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/core/scoped_permissions.py)):**
   - Enforces an `allowed_risks` frozenset.
   - Enforces a `workspace_root` boundary for filesystem tools. Prevents path traversal outside the designated directory via `Path.resolve()` checks.
3. **`ApprovalGate` ([`app/core/approval.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/core/approval.py)):**
   - Non-blocking, asynchronous approval mechanism for actions requiring human confirmation (`ApprovalRequirement.ALWAYS`).
   - Generates unique approval tokens with configurable lifetimes (`lifetime_seconds`).
   - Caches `ONCE_PER_SESSION` approvals; prompts every time for `ALWAYS`.
4. **TOCTOU Defense & Argument Overwrite:**
   - In [`Coordinator._canonicalize_and_authorize()`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/coordinator.py#L605-L640), filesystem resource paths are expanded and resolved into strict canonical paths.
   - **Crucial Fix:** The Coordinator overwrites `action.arguments[tool.path_argument]` with the resolved canonical path string before dispatching to the tool handler, preventing Time-Of-Check to Time-Of-Use discrepancies where the handler might interpret a relative path differently than authorized.

### B. Approval Resolution API & Desktop Signal Bridge
- **Coordinator Resolution API ([`app/agents/coordinator.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/coordinator.py)):**
  - `Coordinator.resolve_approval(gate_id, granted)` allows explicit allow/deny resolution from outside the coordinator's event loop.
  - Thread-safe and fail-closed: returns `False` if `gate_id` is missing, expired, or already resolved.
- **Worker Signal Bridge ([`app/ui/worker.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/worker.py)):**
  - `JasperWorker.approval_requested`: Qt Signal forwarding `ApprovalRequest` to the GUI thread.
  - `JasperWorker.resolve_approval`: Thread-safe Qt Slot accepting `(gate_id, granted)` and delegating to the attached coordinator. Fails closed (`False`) if no coordinator is configured.
- **Desktop Approval Dialog ([`app/ui/approval_dialog.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/approval_dialog.py)):**
  - Modal PySide6 dialog presenting tool name, risk, parameters, and rationale.
  - Explicit Allow and Deny buttons; pressing Esc or closing the dialog triggers denial. Cleans up cleanly if the request is cancelled.

### C. Desktop Autonomous Mode Pipeline ([`app/agents/desktop_wiring.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/desktop_wiring.py))
- **Production Autonomy Wiring:** When desktop autonomy is initialized, `wire_desktop_autonomy(worker, workspace_root)` instantiates a scoped `MultiAgentCoordinator` bound strictly to `workspace_root`.
- **Surgical Tool Suite:** Registers high-precision, safety-bounded tools:
  - `read_text_file`: Sliced range reading (`start_line`, `end_line`) with 500-line size limit.
  - `edit_file_chunk`: Non-destructive chunk editing requiring exact substring verification before replacement (`Risk.WRITE`, `ApprovalRequirement.ALWAYS`).
  - `run_terminal_command`: Scoped shell command execution with hard 30-second timeout and 4000-character output truncation (`Risk.EXECUTE`, `ApprovalRequirement.ALWAYS`).
- **Natural Intent Routing ([`app/agents/router.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/router.py)):**
  - Transparently routes natural coding requests, error fixing, and testing tasks (e.g., `"inspect the backup script and fix the typo"`) into `CognitiveMode.AUTONOMOUS`.
  - Supports multi-prefix overrides: `/auto`, `/fix`, `/code`, `/task`, `/run`.
- **Multi-Turn Feedback Loop:**
  - `MultiAgentCoordinator` collects structured observations from tool executions, stdout/stderr, and screenshot captures.
  - Injects execution observations back into subsequent planner and executor rounds.
  - Bounded budget: 24 agent rounds, 12 tool rounds, and up to 6 autonomous orchestrator iterations.

### D. Approval Presentation Privacy & Recursive Argument Redaction ([`app/ui/approval_dialog.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/approval_dialog.py))
- `sanitize_arguments(args)` provides recursive protection against credential leakage in user approval modals:
  - Traverses nested dictionaries and lists to arbitrary depth.
  - Detects sensitive key substrings (`token`, `secret`, `password`, `key`, `credential`, `auth`, `bearer`) case-insensitively.
  - Converts non-string keys safely and replaces sensitive values with `'<redacted>'`.
  - Truncates oversized string representations to prevent UI buffer exhaustion.

### E. Isolated Live-Model Harness & Scoped Tool Scoping ([`tests/support/live_harness.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/tests/support/live_harness.py))
- Standalone test infrastructure allowing live Ollama model (`qwen3:14b`) evaluation without activating the production desktop application or production tools.
- Builds an isolated `ToolRegistry` from scratch:
  - **Read-Only Mode:** Exposes only `get_system_info` (`Risk.READ`, `ApprovalRequirement.NEVER`).
  - **Approval Mode:** Exposes only `mock_safe_action` (`Risk.WRITE`, `ApprovalRequirement.ALWAYS`), backed by an in-memory test handler.
- Does not call `build_registry()`, exposes zero production write or filesystem tools, and fails closed upon denial (`PermissionError`) or execution timeout (`TimeoutError`).

---

## 5. Reliability, Retries & Cancellation

### A. Retry Invariants ([`app/agents/retry.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/retry.py))
- `RetryPolicy` strictly prohibits retrying operations with side effects (`OperationType.SIDE_EFFECT`).
- Only idempotent read operations (`OperationType.IDEMPOTENT_READ`) and model reasoning calls are eligible for retry.
- If a tool fails with an ambiguous outcome (`ToolOutcome.UNKNOWN`), it is treated as a potential execution and is **never** retried automatically.

### B. Disagreement Resolution
- If the Executor proposes actions differing from the Planner's plan, `DisagreementResolver` detects divergence.
- Bounded to `max_rounds=3`. If divergence persists, the coordinator raises `DisagreementError`, transitions to `CoordinatorState.ERROR`, and halts without executing actions.

### C. Cancellation Architecture
- Every async loop accepts an optional `cancel_callback: Callable[[], bool]`.
- Checks occur before and after every network call, model chunk, and tool execution round.
- Cancellation immediately raises `asyncio.CancelledError`, halting execution safely.

### D. Desktop Window-Close & Cooperative Shutdown
- `MainWindow.closeEvent` coordinates safe termination:
  1. Dismisses active `ApprovalDialog` without granting approval (`handle_cancelled()`).
  2. Issues cooperative cancellation to worker via `worker.cancel_request()`.
  3. Halts worker thread using `thread.quit()` and waits up to 3000ms. If thread fails to terminate within 3000ms, logs a warning and marks shutdown as unclean without crashing.

---

## 6. Major Subsystems

### A. Persistent Memory ([`app/memory/`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/memory/))
- Local SQLite database (`data/jasper.db` or configured path).
- Tables: `conversations`, `memories` (id, content, category, importance, created_at, updated_at).
- Search: Deterministic token-overlap keyword matching. No external embedding vectors required.
- Writing: Strictly explicit. Normal conversational text is kept in short-term context (`MAX_HISTORY_MESSAGES`) and not silently converted into long-term memories.

### B. Vision Layer & Proactive Observation ([`app/vision/`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/vision/))
- **Static Image Analysis:** Provides static image file and snip inspection via `qwen3-vl:8b` with file validation size caps (10 MB).
- **Proactive DeltaScreenWatcher ([`app/vision/delta_watcher.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/vision/delta_watcher.py)):**
  - **Zero-GPU Perceptual Diffing:** Downsamples screen grabs in memory to 32x32 grayscale buffers via PySide6 (<1ms, 0% GPU load), computing normalized mean absolute pixel differences (`compute_pixel_delta`).
  - **Window Task Awareness:** Detects changes in active desktop window titles and task lists alongside visual deltas.
  - **Targeted Vision Verification:** Only invokes local Vision LLM analysis when a meaningful delta (>3%) occurs, using objective-focused prompts (`YES: <summary>` / `NO: <summary>`).
  - **Privacy & Safety Constraints:** Enforces a mandatory maximum duration cap (default 10 minutes) and strict fail-closed timeout alerts. No continuous video streaming or recording.
  - **Desktop Integration:** Controlled via composer buttons (`👁` / `⏹`) and natural chat commands (`/watch [goal]`, `/stopwatch`, `/unwatch`).

### C. Voice Pipeline ([`app/voice/`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/voice/))
- STT: Faster-Whisper.
  - Windows CUDA DLL preloading in [`app/voice/stt.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/voice/stt.py) preloads `cublas64_12.dll`, `cudnn64_9.dll`, `cudart64_12.dll` to prevent PySide6 crash issues.
  - Audio silence filtering in [`app/voice/audio.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/voice/audio.py) rejects background noise based on RMS thresholds.
- TTS: Windows native Speech API or Piper TTS.

### D. Response Sanitization ([`app/core/response.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/core/response.py))
- `sanitize_thinking_tags(text)` strips model reasoning blocks (`<think>...</think>`, unclosed `<think>...`, orphan `</think>`) before returning answers to CLI or desktop chat.
- Preserves mathematical angle brackets and legitimate response text.

---

## 7. Audit Logging & Safety Ledger UI ([`app/core/audit.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/core/audit.py))

Every permission-sensitive event emits a structured `AuditEvent`:
- `PERMISSION_CHECK` / `SCOPE_DENIED`
- `APPROVAL_REQUESTED` / `APPROVAL_GRANTED` / `APPROVAL_DENIED` / `APPROVAL_EXPIRED` / `APPROVAL_CANCELLED`
- `TOOL_EXECUTION` / `TOOL_SUCCESS` / `TOOL_FAILED` / `TOOL_UNKNOWN`
- `TOOL_RETRY` / `TOOL_RETRY_EXHAUSTED` / `VERIFICATION_RECOVERY`
- `PLANNER_INVOKED` / `EXECUTOR_INVOKED`
- `DISAGREEMENT_DETECTED` / `DISAGREEMENT_HALTED`
- `BUDGET_EXCEEDED`

### In-Memory Ledger & Event Broadcasting
- **Thread-Safe Ring Buffer:** Maintains an in-memory rolling buffer (500 events) for real-time desktop access via `get_recent_audit_records()`.
- **Subscriber Listeners:** Components register via `add_audit_listener(callback)`.
- **Qt Worker Bridge:** `JasperWorker.audit_event_emitted` safely marshals audit records across threads onto the GUI thread.

### Interactive Desktop Presentation
- **`AuditTimelineDrawer` ([`app/ui/audit_timeline.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/audit_timeline.py)):**
  - Slide-out safety drawer accessible via `🛡️ Audit (N)` header toggle or `/audit` chat command.
  - Real-time metric counters (`Total`, `Tools`, `Approved`, `Denied`).
  - Category filters (`All`, `Tools`, `Approvals`, `Security`, `Turns`) and text search.
  - Expandable JSON payload inspector for inspecting arguments and execution details.
  - One-click JSON audit ledger export (`QFileDialog`).
- **`TasksWorkspace` Timeline:** Real-time step updates dynamically populated during autonomous task execution.

