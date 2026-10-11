# JASPER AI — MASTER HANDOVER / CONTEXT FILE

> **Purpose:** This document is the portable context for JASPER AI.
>
> Give this file to another AI/agent at the start of a new chat or project session so it can understand the project without requiring the full previous conversation.
>
> **Important:** This is a living handover document. Update the "Current State", "Open Issues", "Milestone Status", and "Recent Git History" sections whenever the project changes.

---

# 0. INSTRUCTIONS TO THE NEXT AI

You are assisting with the development of **JASPER AI**.

Treat this document as the project's primary handover/context.

## Your role

Act primarily as:

- architecture reviewer;
- reliability reviewer;
- security reviewer;
- implementation planner;
- debugging partner;
- technical documentation assistant;
- project continuity assistant.

The user may use another coding agent/IDE to implement changes. Do not pretend that you can see or modify the user's local machine unless the user has explicitly provided a tool that gives that capability.

The user generally wants:

- accurate technical reasoning;
- practical steps;
- explicit commands;
- incremental changes;
- no unnecessary rewrites;
- strong security boundaries;
- honest status reporting.

## Local command rule

When the user needs to execute something locally, use the exact framing:

> **Run this command on your side:**

Then provide the command.

Do not imply that you can see their local PowerShell/terminal.

The user will execute the command and paste the output back.

## Python environment rule

ALL JASPER Python/test/dependency commands must use the project virtual environment explicitly:

```powershell
.\.venv\Scripts\python.exe
```

Examples:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip
.\.venv\Scripts\python.exe -m app.desktop
```

Do not use system/global:

```text
python
pytest
pip
```

unless the user explicitly asks for that.

## Git safety rule

Never tell the user to blindly run destructive Git commands such as:

```powershell
git reset --hard
git clean -fd
```

when unexplained working-tree changes exist.

First inspect and classify the changes.

Never discard an uncommitted file merely because it is not committed.

## Development style

Prefer:

1. inspect;
2. understand;
3. plan;
4. implement incrementally;
5. test;
6. review;
7. security review;
8. inspect Git diff/status;
9. commit atomically;
10. runtime validation where appropriate.

Do not make broad architectural changes unless justified.

---

# 1. PROJECT IDENTITY

## Name

**JASPER**

## Meaning

**Just Another Smart Program Executing Request**

## Repository

```text
Git-Bruh-Hub/JASPER
```

## Platform

```text
Windows 11
```

## Language

```text
Python
```

## Python

```text
Python 3.12+
```

## UI

```text
PySide6
```

## Local LLM runtime

```text
Ollama
```

## Main models

```text
qwen3:8b
qwen3:14b
qwen3-vl:8b
```

Typical roles:

```text
qwen3:8b
→ fast/simple tasks

qwen3:14b
→ main reasoning

qwen3-vl:8b
→ vision
```

## STT

```text
Faster-Whisper
```

## Database

```text
SQLite
```

## Current development environment

```text
Google Antigravity
```

CLI:

```text
agy
```

Recorded version:

```text
Antigravity CLI 1.2.9
```

---

# 2. HARDWARE / LOCAL ENVIRONMENT

Recorded development machine:

```text
OS: Windows 11
CPU: AMD Ryzen 5 5600X
GPU: NVIDIA GeForce RTX 3060 12 GB
RAM: 32 GB
Storage: ~4 TB
```

Project location:

```text
C:\Users\chitz\Desktop\JASPER Project\JASPER_v0.2.2
```

Important:

The directory name `JASPER_v0.2.2` is historical and does NOT represent the current project version.

The Git branch/commits and actual project state are authoritative.

---

# 3. PROJECT VISION

JASPER is intended to become a personal AI assistant for Windows.

The long-term goal is not merely:

> "A chatbot that can talk."

The goal is a personal assistant that can eventually combine:

- text;
- voice;
- speech-to-text;
- text-to-speech;
- vision;
- explicit memory;
- contextual reasoning;
- task management;
- PC/file interaction;
- applications;
- controlled web access;
- multi-agent reasoning;
- observation;
- verification;
- proactive assistance;
- system awareness;
- bounded IoT/device control.

The project is **local-first / hybrid**.

Local models are preferred where practical.

External services may be used where useful or necessary.

The LLM must NOT receive unrestricted control of the computer.

---

# 4. CORE ENGINEERING PHILOSOPHY

The central architecture is:

```text
LLM
 ↓
permission/tool boundary
 ↓
execution
 ↓
observation
 ↓
verification
 ↓
reasoning
```

NOT:

```text
LLM
 ↓
unrestricted PC access
```

The assistant should be useful without sacrificing control.

---

# 5. LONG-TERM COGNITIVE LOOP

The desired JASPER loop is:

```text
Perceive
 ↓
Understand
 ↓
Retrieve / Remember
 ↓
Plan
 ↓
Act
 ↓
Observe
 ↓
Evaluate
 ↓
Correct
 ↓
Remember important result
```

This is a software abstraction for:

- working context;
- long-term memory;
- retrieval;
- perception;
- planning;
- reflection;
- error correction;
- world-state awareness;
- task decomposition;
- attention;
- prioritization;
- goals;
- tool interaction;
- verification.

---

# 6. PERSONALITY / ASSISTANT BEHAVIOR

JASPER should feel like a personal assistant rather than a generic chatbot.

Desired behavior:

- conversational;
- useful;
- context-aware;
- technically capable;
- proactive when appropriate;
- not constantly interrupting the user;
- able to suggest logical next steps;
- able to adapt response depth to the task;
- technical when coding;
- casual when chatting;
- able to remember explicitly requested information;
- able to coordinate internal agents;
- able to reason over evidence;
- able to observe and verify actions;
- safety-conscious;
- not blindly obedient to unsafe instructions.

Long-term target:

> A JARVIS-like personal intelligence experience, while preserving strong user control and explicit safety boundaries.

Important:

"Hive Mind" does NOT mean unrestricted autonomy.

It means coordinated internal agents.

---

# 7. ARCHITECTURE OVERVIEW

Current accepted high-level architecture:

```text
USER
Voice / Text / Image
        ↓
INPUT PROCESSOR
STT / Text / Vision
English / BM / Rojak
        ↓
JASPER CORE
 ├── Cognitive Router
 ├── Context Manager
 ├── Model Router
 └── Permission Manager
        ↓
Simple → Main Agent
Complex → Multi-agent cognition
        ↓
Tool Manager
 ├── Windows
 ├── Files
 ├── Browser/Web
 ├── Applications
 ├── System
 └── Future IoT
        ↓
Observe / Verify
        ↓
Memory / World Model
        ↓
JASPER
```

The architecture is intended to evolve incrementally.

Do not replace the architecture casually because a newer framework looks interesting.

---

# 8. SECURITY BOUNDARY

The LLM must never directly control the machine.

Correct flow:

```text
LLM
 ↓
proposed tool/action
 ↓
Permission Manager
 ↓
risk/scope/capability check
 ↓
approval if required
 ↓
Tool Manager
 ↓
actual execution
 ↓
result
 ↓
observation
 ↓
verification
 ↓
reasoning
```

The model must not receive unrestricted access to:

- PowerShell;
- CMD;
- arbitrary shell;
- arbitrary Python execution;
- registry;
- administrator privileges;
- credentials;
- arbitrary filesystem deletion;
- unrestricted network;
- unrestricted browser automation;
- GitHub/cloud publishing;
- IoT;
- destructive actions.

---

# 9. MEMORY SYSTEM

Memory was introduced as an explicit, user-controlled system.

Core principle:

> Do not silently store every conversation in long-term memory.

Memory should be explicitly written when appropriate.

Conceptual commands:

```text
Remember that ...
Don't forget that ...
What do you remember about me?
What do you remember about <subject>?
Forget ...
Remove from memory ...
```

Storage:

```text
SQLite
```

Core structures:

```text
events
memories
```

Memory fields include:

- id;
- created_at;
- updated_at;
- category;
- content;
- source;
- importance;
- unique(content).

Search:

```text
deterministic token-overlap search
```

Configuration includes:

```text
JASPER_MEMORY_ENABLED
JASPER_MEMORY_SEARCH_LIMIT
```

---

# 10. VOICE

Architecture:

```text
Microphone
 ↓
Faster-Whisper
 ↓
language normalization/detection
 ↓
JASPER Core
 ↓
response
 ↓
TTS
```

Supported language direction:

- English;
- Malay;
- mixed English/Malay/Rojak.

Default response language:

- generally English;
- BM when explicitly requested or clearly appropriate from context.

## Voice stop commands

Canonical stop commands were intentionally kept English-only to improve STT reliability.

Examples:

```text
stop listening
please stop listening
stop listening please
okay stop listening
ok stop listening
goodbye jasper
goodbye jasper please
bye jasper
```

Matching:

- lowercase;
- punctuation stripped;
- exact matching.

---

# 11. VOICE CUDA FIX

A major Windows voice issue occurred:

```text
RuntimeError: Library cublas64_12.dll is not found or cannot be loaded
```

The issue occurred with Faster-Whisper/CTranslate2 native DLL loading under the PySide6 application.

PATH and `os.add_dll_directory()` alone were insufficient in the full application.

Explicit `ctypes.CDLL(absolute_path)` loading worked.

Target DLLs:

```text
cublas64_12.dll
cudnn64_9.dll
cudart64_12.dll
```

`app/voice/stt.py` was updated to:

- discover NVIDIA bin directories;
- explicitly preload required CUDA DLLs;
- retain DLL handles.

Real Windows/QApplication/native QThread smoke testing succeeded.

Example successful transcription:

```text
--- SMOKE TEST SUCCESS ---
Transcription result: Helo, ini adalah perbuatan, ayo.
```

Commit:

```text
9ba956d
Fix Windows CUDA DLL loading for voice STT
```

---

# 12. VOICE HALLUCINATION / SILENCE FILTERING

Whisper was producing hallucinated text from silence/noise.

Changes included:

## Audio

`app/voice/audio.py`

- `voice_detected = False`;
- RMS threshold;
- return `None` when no voice is detected.

## Manager

`app/voice/manager.py`

- converts no-speech result to empty string.

## STT

`app/voice/stt.py`

- missing file → empty result;
- `condition_on_previous_text=False`;
- confidence filtering;
- language normalization.

Thresholds:

```text
NO_SPEECH_THRESHOLD = 0.6
LOGPROB_THRESHOLD = -1.0
```

Segment rejection condition:

```text
no_speech_prob > 0.6
AND
avg_logprob < -1.0
```

Language normalization maps:

```text
bm
bahasa melayu
bahasa malaysia
malay
ms-my
→ ms
```

Automatic language mode:

```text
auto
→ None
```

Explicit Malay:

```text
ms
```

Live validation included:

- no speech → "I didn't detect any speech."
- normal English;
- quiet English.

---

# 13. CURRENT VOICE RELIABILITY NOTE

At one point the user reported that English speech such as:

```text
Jasper, what is the capital of France?
```

was incorrectly transcribed as Malay:

```text
Bagaimana keadaan kawan-kawan?
```

This was identified as a transcription/language-detection reliability issue, not the CUDA loading problem.

Do not confuse:

```text
CUDA DLL loading
```

with:

```text
Whisper language/transcription accuracy
```

They are separate problems.

---

# 14. DESKTOP APPLICATION

The desktop app is based on:

```text
PySide6
```

Important components include:

```text
app/desktop.py
app/ui/main_window.py
app/ui/styles.py
app/ui/worker.py
app/ui/markdown_renderer.py
app/ui/cancellation.py
```

UI capabilities include:

- modern dark UI;
- system tray;
- Chat;
- Tasks;
- Vision;
- Agents;
- Files;
- Web;
- Settings;
- background workers;
- QThread;
- streaming;
- Markdown;
- one-turn voice;
- system/Ollama/GPU status;
- cancellation.

Chat:

```text
User
→ right

JASPER
→ left
```

Markdown supports:

- headings;
- bold;
- italic;
- code;
- lists;
- blockquotes;
- horizontal rules;
- links;
- GFM tables;
- escaped Markdown.

---

# 15. VISION

Vision was introduced in v0.5.

Architecture:

```text
Camera / Screenshot / Image File
        ↓
VISION INPUT
        ↓
Vision Provider abstraction
        ↓
Vision Processor
        ↓
Structured Vision Result
        ↓
JASPER Core
        ↓
Reasoning / Tools / Memory
```

Model:

```text
qwen3-vl:8b
```

Principles:

- explicit capture;
- read-only screenshots;
- no autonomous screen control;
- no continuous monitoring by default;
- no automatic raw-image persistence;
- local images only.

Supported:

```text
PNG
JPG
JPEG
WebP
```

Vision Workspace:

- Open Image;
- preview;
- prompt;
- Analyze;
- results;
- drag/drop.

Drag/drop:

- loads image;
- does not automatically analyze.

Busy state:

- new analysis should be rejected.

Path gating:

Generic terms such as:

```text
image
photo
```

should not automatically expose local-image tools.

Explicit local paths can be allowed.

URLs/bare filenames are rejected where local-path access is required.

---

# 16. V0.6 ADAPTIVE COGNITIVE ROUTING

v0.6 introduced deterministic adaptive multi-agent cognition.

Modes:

```text
SIMPLE
COLLABORATIVE
DEEP
```

## SIMPLE

Normal model path.

## COLLABORATIVE

```text
Planner
 ↓
Finalizer
```

## DEEP

```text
Planner
 ↓
Analyst
 ↓
Critic
 ↓
Finalizer
```

Principles:

- sequential execution;
- internal reasoning not exposed to user;
- finalizer-only streaming;
- stage context isolation;
- do not blindly inject raw historical conversation into every stage;
- original v0.6 Planner/Critic did not directly use tools;
- failures propagate;
- explicit cognitive mode from Orchestrator;
- no duplicate routing.

Short prompt ≠ simple task.

Examples of complex intent:

```text
Analyze this.
Compare these two.
Debug my code.
Plan my trip.
Design a database.
```

---

# 17. V0.6.1 CANCELLATION ARCHITECTURE

The original Stop behavior was found to be insufficient because an active Ollama request could remain blocked.

A dedicated cancellation controller was introduced:

```text
app/ui/cancellation.py
```

Core:

```text
AsyncRequestController
```

Capabilities:

- thread-safe cancellation;
- `threading.Event`;
- active asyncio loop/task tracking;
- `loop.call_soon_threadsafe(...)`;
- worker-local async task lifecycle;
- cleanup.

Flow:

```text
GUI thread
   ↓
cancel_request()
   ↓
AsyncRequestController.cancel()
   ↓
set cancellation event
+
cancel active asyncio task
```

Cancellation propagated through:

- normal text;
- image chat;
- standalone vision;
- voice.

Voice:

- microphone cancellation callbacks;
- `listen_once(cancel_callback=...)`;
- `run_once(..., cancel_callback=...)`;
- active Windows TTS process termination;
- Piper `sounddevice.stop()`.

Worker handles:

- `asyncio.CancelledError`;
- late streaming chunks;
- voice stopping.

Important principle:

> Automated cancellation tests and real Windows runtime cancellation are separate validation layers.

---

# 18. V0.7 — HIVE MIND

Current major milestone:

# JASPER v0.7 — Hive Mind: Secure Multi-Agent Autonomy

"Hive Mind" means coordinated agents.

It does NOT mean unrestricted autonomy.

Conceptual architecture:

```text
                      JASPER
                         │
                   Coordinator
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
       Planner        Researcher      Executor
          │              │              │
          └──────────────┼──────────────┘
                         ↓
                     Observer
                         ↓
                       Critic
                         ↓
                    Coordinator
```

---

# 19. V0.7 SECURITY MODEL

Risk categories:

```text
READ
WRITE
EXECUTE
NETWORK
DESTRUCTIVE
ADMIN
```

Default posture:

```text
READ
→ allowed only inside approved scope

WRITE
→ workspace restricted

EXECUTE
→ narrowly allowed

NETWORK
→ denied by default

DESTRUCTIVE
→ denied

ADMIN
→ denied in autonomous mode
```

Required safety features:

- approval gates;
- task-scoped capabilities;
- autonomy budgets;
- circuit breaker;
- emergency stop;
- audit logging;
- prompt-injection boundary;
- bounded output;
- bounded runtime;
- verification loops;
- cancellation during approval;
- cancellation during execution.

---

# 20. V0.7 AGENT CONTRACTS

Foundation introduced:

```text
AgentResult
ExternalContent
ProposedAction
PermissionScope
VerificationResult
```

Principle:

> Agent output never directly executes side effects.

A proposed action must pass through authorization.

External/retrieved content is untrusted.

External content cannot:

- grant authority;
- change permissions;
- approve actions;
- override system instructions.

---

# 21. V0.7 COORDINATOR

Coordinator is a state machine.

States include:

```text
IDLE
PLANNING
ACTING
APPROVING
OBSERVING
VERIFYING
ERROR
```

Terminal/cancellation states include:

```text
COMPLETED
FAILED
CANCELLED
```

Coordinator responsibilities:

- budgets;
- cancellation;
- permissions;
- approval;
- tool execution;
- observation;
- verification;
- audit correlation.

---

# 22. V0.7 APPROVAL GATE

Approval is asynchronous.

The design uses an `asyncio.Future`-based approval lifecycle.

The worker must not block the Qt event loop while waiting for approval.

Approval requests should be:

- unique;
- bounded/expiring;
- single-resolution;
- cancellation-aware;
- auditable.

The UI resolves the request.

---

# 23. V0.7 AUDIT

Audit records important execution information:

- timestamp;
- action;
- permission scope;
- actor;
- resource;
- status;
- user approval;
- attempt;
- task correlation.

Purpose:

> Make autonomous behavior explainable, diagnosable, and reviewable.

---

# 24. V0.7 RETRY / FAILURE

Retry is operation-sensitive.

```text
READ / MODEL
→ may retry

WRITE / EXECUTE / DESTRUCTIVE / NETWORK
→ never blindly retry
```

Why?

A side-effecting operation may have succeeded even if the response was lost.

Therefore:

```text
side effect
 ↓
uncertain result
 ↓
UNKNOWN
 ↓
do not blindly repeat
```

Retries use:

- bounded exponential backoff;
- cancellation awareness;
- operation classification.

Malformed tool/agent results must be contained rather than crashing the Coordinator.

---

# 25. V0.7 SLICE STATUS

## Slice 1 — Foundation

Completed.

Includes:

- agent contracts;
- typed results;
- proposed actions;
- external content boundary;
- scoped permissions;
- audit foundation;
- Coordinator foundation.

---

## Slice 2 — Security / Audit

Completed.

Includes:

- scoped permission model;
- capability/risk representation;
- structured audit;
- security tests.

---

## Slice 3 — Async Approval

Completed.

Includes:

- ApprovalGate;
- async approval;
- UI resolution;
- cancellation-aware approval.

---

## Slice 4 — Coordinator

Completed.

Includes:

- Coordinator state machine;
- lifecycle;
- budgets;
- cancellation;
- approval integration;
- observation/verification boundaries.

---

## Slice 5 — Retry / Failure

Implemented.

Includes:

- operation-sensitive retry;
- bounded backoff;
- side-effect no-retry;
- UNKNOWN outcome;
- verification recovery limits;
- malformed-result containment;
- budget handling;
- cancellation-aware retry;
- audit attempt tracking;
- DisagreementResolver primitive.

Important:

The `DisagreementResolver` was intentionally standalone in Slice 5.

It was not initially wired into the Coordinator.

That integration was deferred to Slice 6 rather than faked.

### Slice 5 commit

```text
0884a2e
fix: clarify v0.7 Slice 5 disagreement boundary
```

---

# 26. IMPORTANT CURRENT GIT INTEGRITY ISSUE

This is critical for the next AI.

At the current point in the project, the working tree showed:

```text
M app/agents/coordinator.py
```

The file contains substantial Slice 5 retry integration.

However:

```powershell
git show 0884a2e -- app/agents/coordinator.py
```

returned no output.

And:

```powershell
git show --stat --oneline 0884a2e
```

showed only:

```text
app/agents/retry.py
app/core/audit.py
tests/test_slice5_retry_failure.py
```

Therefore:

> The Slice 5 Coordinator integration exists in the working tree but was NOT included in commit `0884a2e`.

Do NOT blindly revert it.

The current working tree's `coordinator.py` includes:

- `RetryPolicy`;
- `operation_type_from_risk`;
- `OperationType`;
- retry policy in Coordinator initialization;
- AgentResult validation;
- retry loop;
- attempt audit;
- side-effect no-retry;
- UNKNOWN handling;
- retriable READ/MODEL retries;
- malformed JSON containment;
- `TOOL_RETRY`;
- `TOOL_RETRY_EXHAUSTED`.

This is real Slice 5 implementation.

It must be reconciled and committed separately/appropriately before declaring the repository clean.

---

# 27. SLICE 6 — AGENT LOGIC

Implemented:

- `PlannerAgent`;
- `ExecutorAgent`;
- `PlannerResult`;
- `PlannerTask`;
- `DisagreementFeedback`;
- `MultiAgentCoordinator`;
- Planner → Executor delegation;
- DisagreementResolver integration;
- bounded disagreement loop;
- disagreement audit events;
- disagreement halt behavior.

Architecture choice:

```text
MultiAgentCoordinator(Coordinator)
```

It subclasses the existing Coordinator.

This preserves inherited:

- permission;
- approval;
- retry;
- cancellation;
- budgets;
- audit.

### Slice 6 commit

```text
2de2637
feat: JASPER v0.7 Slice 6 -- Agent Logic: Planner/Executor delegation + DisagreementResolver integration
```

### Tests

Slice 6:

```text
34/34 passed
```

v0.7 Slices 1–6:

```text
149/149 passed
```

Full suite at that point:

```text
260 passed
81 errors
```

The 81 errors were associated with existing voice/vision/memory environment areas rather than the Slice 5/6 implementation.

Do not describe this as:

> "all tests pass."

Correct statement:

> "The v0.7 focused suite passed; the broader repository suite still has known environment-related errors."

---

# 28. SLICE 7 — NOT COMPLETE

Slice 7 is:

> Routing / Migration

Planned:

- integrate MultiAgentCoordinator into higher-level CognitiveRouter;
- determine relationship between new Coordinator and v0.6 CognitiveEngine;
- preserve regression compatibility;
- incremental migration;
- semantic disagreement/replanning where justified.

Not completed.

Do not begin Slice 7 until the current Slice 5 Coordinator/Git integrity issue is resolved.

---

# 29. V0.7 ACCEPTED DESIGN INVARIANTS

These are important.

## Invariant 1

ApprovalGate must be asynchronous.

## Invariant 2

Capability/permission model must include:

- risk;
- scope;
- operation;
- approval requirement;
- lifetime where applicable.

## Invariant 3

Agent results are typed.

## Invariant 4

ExternalContent is explicitly untrusted.

## Invariant 5

Coordinator has explicit active/terminal states.

## Invariant 6

Retry behavior depends on operation type.

## Invariant 7

Authorization happens immediately before execution.

## Invariant 8

Budgets are explicit.

## Invariant 9

Audit records are correlated to task/action/attempt where relevant.

## Invariant 10

Adversarial tests exist for:

- approval bypass;
- scope escalation;
- prompt injection;
- forged agent results;
- duplicate side effects;
- unknown retry;
- cancellation;
- budget exhaustion;
- Coordinator failure.

## Invariant 11

Migration is incremental.

## Invariant 12

Agents do not directly perform side effects.

---

# 30. PROPOSED ACTION MODEL

A useful action should contain:

```text
action_id
tool_name
operation
arguments
requested_scope
risk
idempotency
rationale
```

The action is a proposal.

It is not execution authority.

---

# 31. EXTERNAL CONTENT BOUNDARY

External content should be typed as untrusted.

Examples:

- web results;
- retrieved documents;
- external text;
- tool output;
- imported data.

Important:

Wrapping content in XML or another delimiter is context hygiene.

It is NOT a complete security boundary.

Authorization must still be performed independently.

---

# 32. VERIFICATION VS AUTHORIZATION

These are separate concepts.

Authorization answers:

> "Is JASPER allowed to perform this action?"

Verification answers:

> "Did the action produce the expected result?"

Do not merge these concepts.

---

# 33. UNKNOWN TOOL OUTCOME

Tool execution may produce:

```text
SUCCESS
FAILED
DENIED
UNKNOWN
```

`UNKNOWN` is particularly important for side effects.

Example:

```text
send email
 ↓
connection drops
 ↓
did the email send?
 ↓
UNKNOWN
```

The correct behavior is not automatically:

```text
send again
```

because that can duplicate a side effect.

---

# 34. CURRENT GIT HISTORY

Important recent commits:

```text
2de2637
feat: JASPER v0.7 Slice 6 -- Agent Logic: Planner/Executor delegation + DisagreementResolver integration

0884a2e
fix: clarify v0.7 Slice 5 disagreement boundary

b05e2d9
feat: JASPER v0.7 Hive Mind foundation -- Contracts, Permissions, ApprovalGate, Coordinator
```

Earlier important commits:

```text
ec158b0
final cancellation-fix commit

ef9d455
JASPER v0.6.1 release candidate polish

6be7aa5
v0.6 hardened adaptive cognitive routing

76f93a8
initial v0.6 adaptive multi-agent cognition

ff4b62d
v0.5.2 Harden vision failure handling

0e4ac8d
v0.5.2 Vision Inside Normal Chat

7ebce8f
v0.5.1 vision drag-and-drop

0b8eb23
v0.5.0 vision tool path gating

9ba956d
Fix Windows CUDA DLL loading for voice STT
```

Current branch:

```text
fix/v0.6.1-cancellation
```

---

# 35. REPOSITORY STATE AT HANDOVER

The latest known `git status --short` contained:

```text
 M app/agents/coordinator.py
 D graphify-out/.graphify_analysis.json
 M graphify-out/.graphify_root
 M graphify-out/graph.json
 M graphify-out/manifest.json
 ?? docs/
 ?? graphify-out/.graphify_labels.json
 ?? graphify-out/.graphify_python
 ?? graphify-out/GRAPH_REPORT.md
 ?? graphify-out/cost.json
 ?? graphify-out/temp_ast.py
 ?? graphify-out/temp_build.py
 ?? graphify-out/temp_cleanup.py
 ?? graphify-out/temp_detect.py
 ?? graphify-out/temp_diag.py
 ?? graphify-out/temp_label.py
 ?? graphify-out/temp_merge.py
 ?? graphify-out/temp_sem.py
 ?? pandoc-3.11-windows-x86_64.msi
 ?? slice5.diff
```

These files must be classified before committing.

Likely categories:

```text
coordinator.py
→ legitimate Slice 5 source change

docs/
→ inspect

graphify-out/
→ distinguish intentional configuration/output from temporary generated artifacts

pandoc MSI
→ likely unrelated installer artifact; do not automatically commit

slice5.diff
→ inspect before deciding
```

Never blindly `git clean -fd`.

---

# 36. CURRENT NEXT STEPS

Do NOT proceed to Slice 7 yet.

First:

## Step 1

Inspect the Slice 5 Coordinator diff.

Command:

```powershell
git diff -- app/agents/coordinator.py
```

## Step 2

Check diff quality:

```powershell
git diff --check
```

## Step 3

Classify changed files:

```powershell
git diff --name-only
```

## Step 4

Inspect Git state:

```powershell
git status --short
```

## Step 5

Once confirmed, commit the missing Slice 5 Coordinator integration as an atomic change.

## Step 6

Run focused v0.7 tests.

## Step 7

Run the full suite.

## Step 8

Verify Slice 6 still works from a clean tree.

## Step 9

Only then start Slice 7.

---

# 37. MILESTONE ROADMAP

## v0.1 — Project Foundation

Historical foundation.

The current handoff does not preserve enough detail to reconstruct every v0.1 feature accurately.

Do not invent historical features.

Status:

```text
Historical / superseded
```

---

## v0.2 — Core Assistant Foundation

Historical foundation.

The current handoff does not preserve enough detail to reconstruct every v0.2 feature accurately.

Status:

```text
Historical / superseded
```

---

## v0.3 — Explicit Memory

Major theme:

> User-controlled persistent memory.

Completed:

- SQLite;
- memory events;
- memories;
- explicit write;
- deterministic search;
- memory commands;
- memory configuration.

Status:

```text
COMPLETED
```

---

## v0.4 — Desktop Assistant

Major theme:

> Usable Windows desktop application.

Completed:

- PySide6;
- chat;
- dark UI;
- system tray;
- workers;
- QThread;
- streaming;
- Markdown;
- workspaces;
- voice integration;
- system status.

Status:

```text
COMPLETED
```

---

## v0.5 — Vision

Major theme:

> Controlled visual perception.

Completed:

- vision provider;
- Qwen3-VL;
- image analysis;
- screenshots;
- Vision Workspace;
- drag/drop;
- validation;
- path gating;
- normal chat vision;
- failure handling.

Status:

```text
COMPLETED
```

---

## v0.6 — Adaptive Cognition

Major theme:

> Deterministic adaptive reasoning depth.

Completed:

- CognitiveRouter;
- SIMPLE;
- COLLABORATIVE;
- DEEP;
- Planner;
- Analyst;
- Critic;
- Finalizer;
- isolated contexts;
- finalizer-only streaming.

Status:

```text
COMPLETED
```

---

## v0.6.1 — Reliability / Cancellation

Major theme:

> Make JASPER reliable enough for daily use.

Completed:

- cancellation controller;
- async cancellation;
- cross-thread cancellation;
- voice cancellation;
- TTS cancellation;
- cancellation tests;
- release candidate polish.

Status:

```text
COMPLETED / RELEASE-CANDIDATE WORK
```

---

## v0.7 — Hive Mind: Secure Multi-Agent Autonomy

Major theme:

> Coordinated agents under explicit security boundaries.

Completed:

- contracts;
- scoped permissions;
- ApprovalGate;
- audit;
- Coordinator;
- budgets;
- retry;
- UNKNOWN;
- verification recovery;
- Planner;
- Executor;
- Planner→Executor;
- disagreement resolver integration.

Pending:

- Slice 5 Coordinator commit/integrity cleanup;
- Slice 7 routing/migration;
- final v0.7 gate;
- broader runtime validation.

Status:

```text
IN PROGRESS
```

---

## v0.8 — Safe Tool / World Interaction

Planned:

- richer tool registry;
- filesystem capabilities;
- controlled application interaction;
- bounded browser/web;
- stronger observation;
- world-state representation;
- structured tool outputs;
- stronger verification.

Status:

```text
PLANNED
```

---

## v0.9 — Personal Daily Driver

Planned:

- contextual memory;
- retrieval;
- task/goal tracking;
- proactivity;
- improved voice UX;
- conversation continuity;
- personalization;
- diagnostics;
- performance;
- packaging;
- long-running tasks.

Status:

```text
PLANNED
```

---

## v1.0 — Stable Personal JASPER

Target:

- reliable daily use;
- stable desktop;
- text;
- voice;
- vision;
- memory;
- contextual reasoning;
- multi-agent coordination;
- permissioned tools;
- bounded autonomy;
- approval;
- audit;
- verification;
- cancellation;
- recovery;
- packaging;
- installation;
- documentation;
- regression tests;
- runtime validation.

Status:

```text
LONG-TERM TARGET
```

---

# 38. V0.8–V1.0 AUTONOMY STRATEGY

Autonomy should increase gradually.

## Level 1 — READ

Examples:

- inspect approved files;
- inspect system state;
- retrieve approved information.

## Level 2 — WORKSPACE WRITE

Examples:

- create files;
- edit project files;
- write inside approved workspace.

## Level 3 — NARROW EXECUTION

Only:

- specific tools;
- bounded arguments;
- bounded runtime;
- explicit risk;
- permission checks.

## Level 4 — APPROVED NETWORK / EXTERNAL ACTIONS

Only when:

- capability exists;
- scope is explicit;
- approval policy allows;
- action is auditable;
- result can be verified.

## Level 5 — Higher Autonomy

Only after:

- circuit breaker;
- emergency stop;
- auditability;
- verification;
- safe failure;
- prompt injection defenses;
- tested recovery;
- clear user control.

Autonomy should be earned through validation.

---

# 39. WHAT JASPER MUST NOT BECOME

Do not turn JASPER into:

- unrestricted shell agent;
- unrestricted PowerShell agent;
- unrestricted Python agent;
- hidden computer controller;
- silent recorder;
- automatic everything-memory;
- blindly executing LLM commands;
- blindly retrying side effects;
- trusting web content as instructions;
- "more agents = more intelligence".

---

# 40. INTELLIGENCE PRINCIPLE

The system should not simply reason more.

It should reason over better evidence.

Core principle:

> Better evidence + observation + verification + correction is more valuable than simply increasing the number of agents.

---

# 41. DEVELOPMENT IDE / AGENT STACK

Current stack:

```text
Google Antigravity
        │
        ├── Graphify
        │
        ├── Addy Osmani Agent Skills
        │
        └── Custom /plan
                │
                ↓
              JASPER
```

---

# 42. ANTIGRAVITY

CLI:

```text
agy
```

Recorded version:

```text
1.2.9
```

The user decided to stay with Antigravity.

Do NOT recommend returning to Claude Code/ECC unless explicitly asked.

---

# 43. GRAPHIFY

Installed:

```text
Graphify 0.9.67
```

Installation:

```powershell
uv tool install graphifyy
```

Used for:

- codebase architecture;
- dependency graph;
- repository understanding;
- structural analysis.

Antigravity integration:

```text
.agents/skills/graphify/
.agents/rules/graphify.md
.agents/workflows/graphify.md
graphify.json
```

Graphify is development tooling.

It is not a JASPER runtime dependency.

Generated output should not automatically be committed.

---

# 44. ADDY OSMANI AGENT SKILLS

Installed using:

```powershell
agy plugin install https://github.com/addyosmani/agent-skills.git
```

Recorded installation:

```text
25 skills
4 agents
9 commands/components
```

Important skills/workflows include:

```text
using-agent-skills
planning-and-task-breakdown
code-review-and-quality
doubt-driven-development
security-and-hardening
test-driven-development
git-workflow-and-versioning
incremental-implementation
debugging-and-error-recovery
documentation-and-adrs
source-driven-development
spec-driven-development
constraint-driven-development
context-engineering
observability-and-instrumentation
performance-optimization
shipping-and-launch
frontend-ui-engineering
agy-customizations
idea-refine
interview-me
```

Use the installed skill inventory as the source of truth if exact skill names change.

---

# 45. CUSTOM /PLAN

Custom file:

```text
.agents/skills/plan/SKILL.md
```

Purpose:

Shortcut to:

```text
planning-and-task-breakdown
```

Preferred workflow for meaningful work:

```text
/using-agent-skills
/plan
review plan
implement
test
review
commit
```

---

# 46. MODEL ROLES

## Gemini 3.1 Pro — High

Use for:

- architecture;
- planning;
- security;
- difficult debugging;
- cross-file reasoning;
- Graphify interpretation;
- final review.

## Claude Sonnet 4.6 — Thinking

Use for:

- implementation;
- refactoring;
- tests;
- multi-file coding.

## Gemini 3.8 Flash — High

Use for:

- small fixes;
- routine coding;
- test fixes;
- lower-complexity tasks.

The project intentionally separates:

```text
architecture/review
```

from:

```text
implementation
```

when useful.

---

# 47. STANDARD IMPLEMENTATION WORKFLOW

For a substantial task:

```text
1. Understand problem
2. Inspect repository
3. Inspect relevant architecture
4. Use Graphify if useful
5. /using-agent-skills
6. /plan
7. Review plan
8. Claude Sonnet 4.6 Thinking implementation
9. Focused tests
10. Regression tests
11. Diff review
12. Security review
13. Git status
14. Atomic commit
15. Runtime validation
```

---

# 48. STANDARD REVIEW WORKFLOW

For architecture/security review:

```text
Gemini 3.1 Pro High

+
/using-agent-skills

+
relevant skills:
- code-review-and-quality
- doubt-driven-development
- security-and-hardening
- test-driven-development
- graphify
```

Review questions:

1. Does this preserve architecture?
2. Does it preserve permissions?
3. Can an agent bypass authorization?
4. Can external content grant authority?
5. Can a side effect be duplicated?
6. Can cancellation leave work running?
7. Can malformed output crash the system?
8. Are budgets enforced?
9. Is audit data sufficient?
10. Are tests proving the real behavior?
11. Is the diff scoped?
12. Is there a simpler implementation?

---

# 49. TESTING PHILOSOPHY

Passing tests does not automatically prove:

```text
Windows runtime
+
PySide6
+
QThread
+
Ollama
+
CUDA
+
TTS
+
STT
+
streaming
```

works correctly.

Therefore use layers:

## Layer 1

Unit tests.

## Layer 2

Focused feature tests.

## Layer 3

v0.x regression suite.

## Layer 4

Full repository suite.

## Layer 5

Real Windows runtime smoke tests.

## Layer 6

Adversarial/security tests.

---

# 50. COMMON COMMANDS

Check branch:

```powershell
git branch --show-current
```

Check status:

```powershell
git status --short
```

Recent history:

```powershell
git log --oneline -10
```

Diff:

```powershell
git diff
```

Specific file:

```powershell
git diff -- app/agents/coordinator.py
```

Check whitespace/errors:

```powershell
git diff --check
```

List changed files:

```powershell
git diff --name-only
```

Full tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Verbose tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -vv
```

Run desktop:

```powershell
.\.venv\Scripts\python.exe -m app.desktop
```

---

# 51. DOCUMENTATION HONESTY

Always distinguish:

## Confirmed

Verified by:

- Git;
- tests;
- source inspection;
- user command output;
- actual runtime.

## Implemented but not runtime validated

Code exists and automated tests pass, but live behavior has not been demonstrated.

## Planned

Design exists, implementation does not.

## Deferred

Intentionally postponed.

Never say:

> "Everything is fixed."

unless evidence actually supports that.

---

# 52. DEFINITION OF DONE

Normal feature:

```text
Specification
 ↓
Implementation
 ↓
Focused tests
 ↓
Regression tests
 ↓
Diff review
 ↓
Security review
 ↓
Runtime validation when relevant
 ↓
Documentation
 ↓
Atomic commit
```

High-risk/autonomous feature:

```text
Specification
 ↓
Threat model
 ↓
Implementation
 ↓
Adversarial tests
 ↓
Runtime validation
 ↓
Auditability
 ↓
Rollback/cancellation
 ↓
Release gate
```

---

# 53. V0.7 RELEASE GATE

Before calling v0.7 complete:

## Security

- default deny;
- capability scopes;
- authorization immediately before execution;
- external content untrusted;
- approval gate;
- audit;
- no unrestricted shell.

## Lifecycle

- cancellation;
- approval cancellation;
- tool cancellation;
- bounded runtime;
- budgets.

## Correctness

- Planner;
- Executor;
- Coordinator;
- disagreement handling;
- verification.

## Failure

- malformed results;
- tool failure;
- UNKNOWN;
- retry policy;
- bounded disagreement;
- bounded verification recovery.

## Regression

- v0.6 tests;
- v0.6.1 cancellation;
- voice;
- vision;
- memory.

## Runtime

- actual Windows;
- PySide6;
- Ollama;
- CUDA;
- STT;
- TTS.

---

# 54. LONG-TERM V1.0 ARCHITECTURE

Target:

```text
                 USER
                  │
        Voice / Text / Vision
                  │
                  ↓
           Input Processing
                  │
                  ↓
        Context Retrieval
                  │
                  ↓
         Cognitive Router
                  │
                  ↓
              Planner
                  │
          ┌───────┴────────┐
          ↓                ↓
       Researcher       Executor
          │                │
          └───────┬────────┘
                  ↓
              Observer
                  ↓
               Critic
                  ↓
            Verification
                  ↓
             Finalizer
                  ↓
                USER

        Memory / World Model
               ↕
        Persistent Context
```

The v1.0 system should be stable, observable, auditable, cancellable, permissioned, and usable daily.

---

# 55. PROJECT PRINCIPLES — SHORT FORM

If another AI remembers nothing else, remember these:

### Principle 1

> The LLM proposes; the permission boundary decides.

### Principle 2

> Agents do not directly perform side effects.

### Principle 3

> External content is untrusted.

### Principle 4

> Authorization and verification are different.

### Principle 5

> Side effects must not be blindly retried.

### Principle 6

> UNKNOWN is a valid tool outcome.

### Principle 7

> Cancellation must propagate through the actual async work.

### Principle 8

> More agents do not automatically mean better intelligence.

### Principle 9

> Better evidence and verification are more valuable than more reasoning steps.

### Principle 10

> Do not make architectural rewrites without evidence.

### Principle 11

> Never silently discard uncommitted work.

### Principle 12

> Tests passing is not the same as runtime validation.

### Principle 13

> Use the project `.venv`.

### Principle 14

> Use Antigravity; do not reintroduce ECC/Claude Code unless explicitly requested.

### Principle 15

> Increase autonomy gradually and only after validation.

---

# 56. HOW TO START A NEW AI SESSION

Give the AI this file.

Then tell it:

```text
Read JASPER_MASTER_HANDOVER.md completely before making recommendations.

Treat it as the current project context.

Do not invent missing historical facts.

Respect the command rule:
"Run this command on your side:"

Use .\.venv\Scripts\python.exe for all JASPER Python/test commands.

Do not blindly revert uncommitted changes.

Act as architecture/reliability/security reviewer unless I explicitly ask you to implement something.

Before modifying architecture, inspect the current state and make a plan.

The current known blocker is the uncommitted Slice 5 Coordinator integration. Resolve repository integrity before proceeding to Slice 7.
```

---

# 57. HANDOVER UPDATE TEMPLATE

When updating this file after a milestone, add:

```text
## Latest Update

Date:
Version:
Branch:

### Completed
- ...

### Tests
- ...

### Runtime validation
- ...

### Git commits
- ...

### Open issues
- ...

### Next task
- ...

### Important architectural decisions
- ...
```

This allows future chats to resume without reconstructing the entire conversation.

---

# 58. CURRENT STATUS SUMMARY

At the current handover point:

```text
v0.1
FOUNDATION / HISTORICAL

v0.2
FOUNDATION / HISTORICAL

v0.3
COMPLETED — MEMORY

v0.4
COMPLETED — DESKTOP

v0.5
COMPLETED — VISION

v0.6
COMPLETED — ADAPTIVE COGNITION

v0.6.1
COMPLETED — CANCELLATION / RELIABILITY

v0.7
IN PROGRESS — HIVE MIND

v0.7 Slice 1
COMPLETED

v0.7 Slice 2
COMPLETED

v0.7 Slice 3
COMPLETED

v0.7 Slice 4
COMPLETED

v0.7 Slice 5
IMPLEMENTED
BUT COORDINATOR INTEGRATION NEEDS GIT RECONCILIATION

v0.7 Slice 6
IMPLEMENTED / TESTED

v0.7 Slice 7
NOT STARTED / NOT COMPLETE

v0.8
PLANNED

v0.9
PLANNED

v1.0
LONG-TERM TARGET
```

---

# 59. MOST IMPORTANT CURRENT ACTION

Do not proceed to Slice 7 immediately.

First resolve:

```text
Slice 5 Coordinator implementation
```

because:

```text
0884a2e
```

does not contain it, while the working tree does.

The correct sequence is:

```text
Inspect coordinator.py
 ↓
Verify intended Slice 5 logic
 ↓
Classify generated/unrelated files
 ↓
Commit Slice 5 Coordinator integration
 ↓
Clean working tree
 ↓
Run v0.7 tests
 ↓
Run full suite
 ↓
Verify Slice 6 from clean HEAD
 ↓
Then begin Slice 7
```

---

# 60. FINAL PROJECT MISSION

JASPER is not being built merely to demonstrate an LLM controlling a computer.

The mission is to build a **dependable personal AI assistant**.

The target is:

```text
Useful
+
Context-aware
+
Multimodal
+
Memory-enabled
+
Reasoning-capable
+
Tool-capable
+
Observable
+
Verifiable
+
Cancellable
+
Permissioned
+
Auditable
+
Safe
```

The project should grow from:

```text
assistant
```

to:

```text
personal intelligence
```

without losing:

```text
user control
```

The final architectural principle remains:

> **Reason → authorize → act → observe → verify → correct → remember.**
