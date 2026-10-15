# JASPER AI — Architecture Decision Records (ADRs)

> **Status:** Active Reference Log  
> **Authority:** Derived from historical commits, `JASPER.md`, and validated repository architecture.

---

## Index of Decisions

- **ADR-001:** Application-Level Object-Capability Security Boundary vs. Unrestricted Shell
- **ADR-002:** Subclassing `Coordinator` for `MultiAgentCoordinator`
- **ADR-003:** Standalone Typed Contracts as Pure Data Containers
- **ADR-004:** Asynchronous Human-in-the-Loop `ApprovalGate`
- **ADR-005:** Absolute Prohibition on Retrying Side-Effecting Operations
- **ADR-006:** Treating Ambiguous `UNKNOWN` Tool Outcomes as Non-Retriable
- **ADR-007:** Sanitizing LLM Claims in Adapters via Authoritative `ToolRegistry`
- **ADR-008:** Explicit User-Commanded Memory vs. Silent Ambient Recording
- **ADR-009:** Explicit Preloading of Native Windows CUDA DLLs for Voice STT
- **ADR-010:** Mandatory `.venv` Python Virtual Environment Invariant
- **ADR-011:** Zero Blind Destructive Git Operations Policy
- **ADR-012:** Guarded Coordinator Recovery and Planner Rejection Audit
- **ADR-013:** Post-Generation Thinking-Tag Response Sanitization
- **ADR-014:** Thread-Safe Approval Gate Resolution API
- **ADR-015:** Cooperative Desktop Cancellation and Window Shutdown Hardening
- **ADR-016:** Qt Signal Bridge and Modal Presentation for Desktop Approvals
- **ADR-017:** Test-Only Dependency Injection for Autonomous Execution Verification
- **ADR-018:** Controlled Live-Model Runtime Validation & Independent Readiness Review
- **ADR-019:** Recursive Argument Redaction for Desktop Approval Presentation
- **ADR-020:** Isolated Test Harness with Dedicated Scratch Registry for Live Validation

---

### ADR-001: Application-Level Object-Capability Security Boundary
* **Status:** **ACCEPTED** [VERIFIED in commit `b05e2d9`]
* **Context:** LLMs cannot be trusted with unrestricted access to system shells (`powershell.exe`, `cmd.exe`) or arbitrary code execution due to prompt injection vulnerabilities and non-deterministic behavior.
* **Decision:** Implement an in-process object-capability model in Python. An LLM may only propose an action (`ProposedAction`). The action is checked by `ScopedPermissionManager` against explicit risk categories (`Risk`) and a resolved `workspace_root`.
* **Consequences:**
  - *Positive:* High protection against prompt injections attempting to run unauthorized tools or escape directory roots.
  - *Trade-off:* Does not provide OS-level hardware/kernel sandboxing against native binary vulnerabilities.

---

### ADR-002: Subclassing `Coordinator` for `MultiAgentCoordinator`
* **Status:** **ACCEPTED** [VERIFIED in commit `2de2637`]
* **Context:** Slice 6 required adding a multi-agent orchestration layer (Planner and Executor) to the existing v0.7 coordinator without breaking earlier state-machine rules, budget caps, or audit logging.
* **Decision:** Implement `MultiAgentCoordinator` as a direct subclass of `Coordinator`:
  ```python
  class MultiAgentCoordinator(Coordinator):
  ```
* **Consequences:**
  - *Positive:* Reuses all existing permission checks, cancellation callbacks, budget limits, approval gates, and retry policies without code duplication.
  - *Trade-off:* Couples multi-agent delegation to the base Coordinator's state machine transitions.

---

### ADR-003: Standalone Typed Contracts as Pure Data Containers
* **Status:** **ACCEPTED** [VERIFIED in commit `b05e2d9`, hardened in `a7005d2`]
* **Context:** Multi-agent architectures can easily suffer from circular imports and blurred authority boundaries if message objects encapsulate business logic or execution methods.
* **Decision:** Place all inter-agent messages in [`app/agents/contracts.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/contracts.py) as pure, frozen dataclasses (`ProposedAction`, `PermissionScope`, `AgentResult`, `ExternalContent`, `ApprovalRequirement`) with no imports from the rest of the application.
* **Consequences:**
  - *Positive:* Eliminates circular dependencies; ensures contracts are safe to import anywhere; prevents agents from invoking execution methods directly on contract objects.

---

### ADR-004: Asynchronous Human-in-the-Loop `ApprovalGate`
* **Status:** **ACCEPTED** [VERIFIED in commit `b05e2d9`]
* **Context:** Synchronous command prompts block the Python async event loop, freezing desktop UI rendering and preventing prompt cancellation.
* **Decision:** Implement `ApprovalGate` using `asyncio.Future` and unique request UUIDs. When a tool requires approval, an event is emitted to the UI, and the coordinator awaits the future.
* **Consequences:**
  - *Positive:* UI remains fully responsive; the user can inspect consequences; the turn can be cancelled cleanly while pending approval.
  - *Trade-off:* Requires a notifier callback wired to the UI layer.

---

### ADR-005: Absolute Prohibition on Retrying Side-Effecting Operations
* **Status:** **ACCEPTED** [VERIFIED in commit `0884a2e` and `5a3a4e2`]
* **Context:** In distributed systems or autonomous agents, naive retry loops on failed tool calls can cause catastrophic duplicated writes, duplicate payments, or repeated destructive operations.
* **Decision:** In [`app/agents/retry.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/retry.py), `RetryPolicy` classifies operations into `IDEMPOTENT_READ`, `MODEL_INFERENCE`, and `SIDE_EFFECT`. Retrying any `SIDE_EFFECT` operation raises `NonRetriableOperationError`.
* **Consequences:**
  - *Positive:* Prevents duplicate writes or unintended secondary modifications.
  - *Trade-off:* Transient write failures (e.g., temporary file lock) require the user or a replanning loop to re-initiate the action explicitly.

---

### ADR-006: Treating Ambiguous `UNKNOWN` Tool Outcomes as Non-Retriable
* **Status:** **ACCEPTED** [VERIFIED in `JASPER.md` Section 33 and `coordinator.py`]
* **Context:** If a tool execution raises a timeout or disconnects during execution, the true state of the external resource is unknown (the write may have partially or fully completed).
* **Decision:** When `ToolOutcome.UNKNOWN` occurs, the coordinator treats the tool as potentially executed with side effects and halts. It is strictly never retried automatically.
* **Consequences:**
  - *Positive:* Eliminates ghost side-effect duplication.
  - *Trade-off:* Leaves recovery to higher-level verification or explicit user direction.

---

### ADR-007: Sanitizing LLM Claims in Adapters via Authoritative `ToolRegistry`
* **Status:** **ACCEPTED** [VERIFIED in commit `a7005d2`]
* **Context:** In multi-agent autonomous mode (`/auto`), an LLM may output JSON that falsely asserts `risk: "read"` or `approval_requirement: "never"` for a dangerous tool.
* **Decision:** In [`app/agents/adapters.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/agents/adapters.py), discard any permission or approval claims inside LLM output. Reconstruct `PermissionScope` strictly from the authoritative `ToolRegistry.get(name).risk`.
* **Consequences:**
  - *Positive:* Completely closes model forgery vulnerabilities in autonomous mode.
  - *Evidence:* Verified by 13/13 passing tests in `tests/test_security_forgeries.py`.

---

### ADR-008: Explicit User-Commanded Memory vs. Silent Ambient Recording
* **Status:** **ACCEPTED** [VERIFIED in `app/memory/sqlite_memory.py`]
* **Context:** Automatically vectorizing and storing every user sentence into permanent long-term memory introduces severe privacy risks, context pollution, and irrelevance.
* **Decision:** Only explicit user instructions (`Remember that...`, `Forget...`) write to SQLite long-term storage. Standard conversational history remains ephemeral and bounded by `MAX_HISTORY_MESSAGES`.
* **Consequences:**
  - *Positive:* User maintains full agency over their stored personal data; search is deterministic and fast.

---

### ADR-009: Preloading Windows CUDA DLLs for Voice STT
* **Status:** **ACCEPTED** [VERIFIED in commit `9ba956d`]
* **Context:** Faster-Whisper/CTranslate2 failed to load `cublas64_12.dll` on Windows 11 inside PySide6 applications even when the NVIDIA directory was on the system `PATH`.
* **Decision:** In [`app/voice/stt.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/voice/stt.py), discover NVIDIA library paths and explicitly preload `cublas64_12.dll`, `cudnn64_9.dll`, and `cudart64_12.dll` via `ctypes.CDLL(path)` before importing or instantiating Faster-Whisper.
* **Consequences:**
  - *Positive:* Eliminates native DLL load crashes on Windows with NVIDIA RTX GPUs.

---

### ADR-010: Mandatory `.venv` Python Virtual Environment Invariant
* **Status:** **ACCEPTED** [VERIFIED in `JASPER.md` Section 0]
* **Context:** Running tests or commands against the global Python interpreter causes version mismatches, missing dependency errors, and broken PySide6 bindings.
* **Decision:** All commands executed for tests, linting, or running JASPER must explicitly invoke the local virtual environment executable:
  `.\.venv\Scripts\python.exe`
* **Consequences:**
  - *Positive:* Ensures absolute consistency across development agents and environments.

---

### ADR-011: Zero Blind Destructive Git Operations Policy
* **Status:** **ACCEPTED** [VERIFIED in `JASPER.md` Section 0]
* **Context:** AI agents frequently run `git reset --hard` or `git clean -fd` to clear unexpected files, accidentally destroying uncommitted user work, recovery backups, or local patches.
* **Decision:** Agents must never execute blind destructive Git commands. All untracked files and working-tree changes must be inspected and preserved. `git add .` is prohibited in favor of explicit named files.

---

### ADR-012: Guarded Coordinator Recovery and Planner Rejection Audit
* **Status:** **ACCEPTED** [VERIFIED in Steps 7–8]
* **Context:** When a planner proposes an uncanonicalizable action or a disagreement is unresolvable, `MultiAgentCoordinator` transitions to `CoordinatorState.ERROR`. Retaining this coordinator for subsequent user turns would either permanently block requests or cascade state corruption.
* **Decision:** Implement `MultiAgentCoordinator.reset()` to clear active gates, reinitialize budgets, and return state to `CoordinatorState.IDLE`. When an uncanonicalizable action is proposed, emit an explicit `AuditEventType.PLANNER_REJECTION` audit event and transition to `ERROR` without invoking the executor callable or modifying files.
* **Consequences:**
  - *Positive:* Enables a retained coordinator instance in CLI or desktop workers to recover safely on subsequent turns without leaking previous execution state.

---

### ADR-013: Post-Generation Thinking-Tag Response Sanitization
* **Status:** **ACCEPTED** [VERIFIED in Step 9]
* **Context:** Reasoning models (such as Qwen3/DeepSeek) emit `<think>...</think>` blocks or stray `</think>` tags in raw tool/chat output, exposing raw chain-of-thought artifacts to end users.
* **Decision:** Implement `sanitize_thinking_tags` in [`app/core/response.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/core/response.py) and hook it into `Orchestrator._run_model_loop` and CLI printing. The regex strips closed and unclosed thinking blocks and orphan tags, while strictly preserving mathematical/comparison angle brackets (`x < y`) and ordinary markdown text.
* **Consequences:**
  - *Positive:* Clean user presentation across desktop and CLI interfaces without stripping legitimate text.

---

### ADR-014: Thread-Safe Approval Gate Resolution API
* **Status:** **ACCEPTED** [VERIFIED in Steps 11–12]
* **Context:** PySide6 GUI interactions occur on the Qt main thread, while the coordinator and request loop run on worker threads or asyncio event loops. Resolving pending approval futures requires a safe, thread-agnostic entry point.
* **Decision:** Add `Coordinator.resolve_approval(gate_id: str, granted: bool) -> bool`. It validates that `gate_id` exists, is active, and is not expired; cancels or completes the underlying `asyncio.Future` using `loop.call_soon_threadsafe`; records an audit event (`APPROVAL_GRANTED` / `APPROVAL_DENIED`); and removes the gate from active tracking. Fails closed (returns `False`) if the gate is unknown or expired.
* **Consequences:**
  - *Positive:* Decouples UI resolution from async event loop threading; prevents double-resolution races.

---

### ADR-015: Cooperative Desktop Cancellation and Window Shutdown Hardening
* **Status:** **ACCEPTED** [VERIFIED in Step 13]
* **Context:** Closing the desktop window while an approval is pending or while a tool is executing could leave worker threads orphaned or cause crashes during Python teardown.
* **Decision:** In [`MainWindow.closeEvent`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/main_window.py), explicitly dismiss any open `ApprovalDialog` (marking it cancelled without granting approval), trigger `worker.cancel_request()`, and call `thread.quit()` with a 3000ms timeout.
* **Consequences:**
  - *Positive:* Clean window termination; active gates fail closed on shutdown; prevents ungraceful thread aborts.

---

### ADR-016: Qt Signal Bridge and Modal Presentation for Desktop Approvals
* **Status:** **ACCEPTED** [VERIFIED in Steps 14A–14B]
* **Context:** Desktop users must be alerted when an action requires approval (`ApprovalRequirement.ALWAYS`), presented with the tool name, parameters, and rationale, and given explicit control to approve or deny.
* **Decision:**
  1. Add `JasperWorker.approval_requested = Signal(ApprovalRequest)` and `JasperWorker.resolve_approval(gate_id, granted)`.
  2. Implement [`ApprovalDialog`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/approval_dialog.py) as a modal PySide6 dialog.
  3. Wire dialog buttons to emit `decision_made(gate_id, granted)`. Pressing Esc, clicking close, or window close triggers denial (`granted=False`).
* **Consequences:**
  - *Positive:* Safe, non-blocking modal interaction on the GUI thread; fail-closed behavior on dismissal.

---

### ADR-017: Test-Only Dependency Injection for Autonomous Execution Verification
* **Status:** **ACCEPTED** [VERIFIED in Step 15]
* **Context:** Verifying the full desktop approval lifecycle (Request → Worker → Coordinator → Signal → Dialog → Resolution → Tool Execution) required end-to-end integration testing without enabling autonomous mode for ordinary desktop users and without running live model inference.
* **Decision:** Expose optional `planner_callable` and `executor_callable` on [`Orchestrator`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/core/orchestrator.py), and `set_coordinator` on [`JasperWorker`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/worker.py). In test harnesses, inject deterministic fakes that simulate proposed actions and mock tools. In production desktop startup ([`app/desktop.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/desktop.py)), `worker.coordinator` and `orchestrator.multi_agent_coordinator` remain `None`, failing closed for all `/auto` requests.
* **Consequences:**
  - *Positive:* 100% deterministic test coverage of the full end-to-end Qt GUI approval lifecycle without live model dependencies.
  - *Invariant:* Production desktop application remains completely un-autonomous and fails closed.

---

### ADR-018: Controlled Live-Model Runtime Validation & Independent Readiness Review
* **Status:** **ACCEPTED** [VERIFIED in Steps 17–18B]
* **Context:** While deterministic fake tests pass (448/448), the multi-agent coordinator and approval workflow required live verification against local Ollama models (`qwen3:14b`) to confirm that real LLM tool-calling syntax properly maps to coordinator actions and triggers the approval boundary without enabling autonomous mode for desktop users.
* **Decision:**
  1. Conduct live smoke testing via an isolated test runner (`tests/support/live_harness.py`).
  2. Verify three operational modes: Read-Only (`get_system_info`), Approval-Allow (`mock_safe_action` post-approval execution), and Approval-Deny (`mock_safe_action` execution blocked).
  3. Keep desktop autonomous mode disabled by default in production configuration (`app/desktop.py`).
* **Consequences:**
  - *Positive:* Validates real model prompt decomposition and approval gate enforcement without exposing local system files.
  - *Evidence:* Verified in Step 18B (all 3 live scenarios passed cleanly).

---

### ADR-019: Recursive Argument Redaction for Desktop Approval Presentation
* **Status:** **ACCEPTED** [VERIFIED in Step 17C]
* **Context:** When tools are invoked with complex nested arguments (dictionaries, lists), sensitive credential keys (`token`, `secret`, `password`, `key`, `credential`, `auth`, `bearer`) could inadvertently be displayed to users in plaintext in the approval modal.
* **Decision:** In [`app/ui/approval_dialog.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/ui/approval_dialog.py), implement recursive sanitization (`sanitize_arguments`) traversing nested dicts and lists to arbitrary depth, converting non-string keys safely, and replacing sensitive values with `'<redacted>'`.
* **Consequences:**
  - *Positive:* Closes credential display vulnerabilities in approval presentations.
  - *Evidence:* Verified by 13/13 passing tests in `tests/test_desktop_approval_dialog.py`.

---

### ADR-020: Isolated Test Harness with Dedicated Scratch Registry for Live Validation
* **Status:** **ACCEPTED** [VERIFIED in Step 18A]
* **Context:** Running live model tests against production registries (`build_registry()`) risks unintended file modifications or system side effects if the model hallucinates arguments or calls unmocked tools.
* **Decision:** Implement [`tests/support/live_harness.py`](file:///C:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/tests/support/live_harness.py) with an isolated, in-memory `ToolRegistry` built from scratch. For read-only mode, register only `get_system_info`. For approval mode, register only an in-memory `mock_safe_action`. Never register production write or execute tools in the live test harness.
* **Consequences:**
  - *Positive:* Absolute tool containment during live LLM testing; deterministic contract tests prove isolation before live execution.
  - *Evidence:* Verified by 8/8 passing tests in `tests/test_live_harness_contracts.py`.
