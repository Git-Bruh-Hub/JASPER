# JASPER AI — Project Vision

> **Status:** Active Reference Document  
> **Authority:** Derived from `JASPER.md` (Sections 1–8, 37–40, 54, 60), `docs/planning/1_PRD.md`, and validated repository architecture.

---

## 1. Executive Summary

**JASPER** (**J**ust **A**nother **S**mart **P**rogram **E**xecuting **R**equest) is a local-first personal AI assistant foundation for Windows 11.

JASPER is built on a single, fundamental conviction:
> **An AI assistant must be deeply capable and autonomous without ever sacrificing user control, system privacy, or operational safety.**

Rather than granting an LLM unconstrained access to shell commands, operating system APIs, or the filesystem, JASPER interposes an explicit **capability-based security boundary** between model reasoning and computer execution. The LLM may propose intent, but only a deterministic, policy-driven Coordinator and Scoped Permission Manager may authorize and execute actions.

---

## 2. Core Problem & Motivation

Modern desktop AI agents frequently fail at one of two extremes:
1. **The Passive Chatbot:** Confined entirely to text generation, unable to inspect local hardware, read files, or take meaningful action on behalf of the user.
2. **The Unsafe Autonomous Loop:** Granted raw bash/PowerShell or unrestricted API execution, creating severe risks of prompt injection, data destruction, unauthorized external communications, and untraceable system corruption.

JASPER solves this dichotomy by establishing a **local-first, permission-governed cognitive architecture**:
- **Privacy by Default:** Core reasoning and data remain on the local machine using local Ollama models (e.g., `qwen3:14b`, `qwen3:8b`, `qwen3-vl:8b`) and local SQLite storage.
- **Human-in-the-Loop Safeguards:** Any action with side effects (writing files, executing processes, deleting data, network calls) must be intercepted by an asynchronous Approval Gate and explicitly approved by the user.
- **Separation of Reasoning from Authority:** An LLM cannot grant itself permissions. Claimed tools or forged scopes in model output are ignored; capabilities are derived strictly from an authoritative, local Tool Registry.
- **Verifiable Truth:** System observations (CPU, RAM, GPU, storage) are grounded in direct, live hardware measurements rather than hallucinated model assumptions.

---

## 3. Long-Term Destination & User Experience

The long-term goal of JASPER is an intelligent, everyday personal companion for Windows (akin to JARVIS) providing:
- **Multimodal Interaction:** Seamless text chat, voice interaction (local STT and TTS), and image/vision understanding in a unified desktop interface.
- **Contextual & Explicit Memory:** Deterministic recall of explicitly saved user preferences and facts without silent mass-surveillance of all conversations.
- **Multi-Agent Hive Mind:** Coordinated internal specialists (e.g., a Planner that decomposes goals and an Executor that formulates concrete tool actions) governed by disagreement resolution and budget limits.
- **Reliable Task Execution:** Ability to plan and execute multi-step research, local file processing, and desktop automation reliably.
- **System Awareness:** Continuous, low-overhead awareness of local machine resource state, GPU memory, and running background tasks.

---

## 4. Foundational Principles

### Principle 1: Local-First / Hybrid
Local models running on local hardware are the primary reasoning engines. External cloud APIs (OpenAI, Anthropic) are treated strictly as optional fallbacks for heavy reasoning tasks where local models cannot complete a complex task, and require explicit user opt-in.

### Principle 2: Permission-Gated Execution
Every action follows the invariant sequence:
```text
Perceive → Understand → Retrieve → Plan → Authorize → Act → Observe → Verify → Remember
```
No tool runs without prior verification against the `ScopedPermissionManager` and, where required, explicit user confirmation via the `ApprovalGate`.

### Principle 3: Bounded Autonomy & Fail-Closed Behavior
Autonomy is strictly bounded:
- Fixed round limits on tool loops and agent rounds.
- Strict token budgets.
- If planner output is malformed, if arguments cannot be canonicalized, or if an unknown tool error occurs, the system **fails closed** to an error state rather than guessing or retrying destructively.

### Principle 4: Truth Grounding & Separation of Claims
Model assertions are never treated as facts. If the user asks for PC specifications, JASPER forces a live hardware tool observation and renders the answer from measured data. Model claims about tool success are only accepted when verified by tool return payloads.

### Principle 5: Uncompromised Git and Workspace Safety
JASPER development respects user work: no blind resets, no uninspected cache cleanups, and no destructive commands. Development proceeds in thin, verifiable slices backed by automated regression tests.

---

## 5. Non-Goals & Unacceptable Behaviors

JASPER **MUST NEVER**:
- Provide an LLM with unrestricted access to `powershell.exe`, `cmd.exe`, or arbitrary Python code evaluation.
- Enable arbitrary filesystem deletion or recursive directory purging without individual confirmation.
- Execute continuous background screen recording or continuous microphone surveillance.
- Silently transmit user data, files, or conversations to external third-party telemetry services.
- Retry side-effecting operations (writes, executions, destructive actions) when an outcome is unknown or ambiguous.
- Allow untrusted external content (retrieved web text, parsed email content) to grant authority or bypass system permissions.

---

## 6. Current Implementation vs. Long-Term Vision

To prevent confusion across development sessions, capabilities are categorized into their current verified reality versus future goals:

| Capability | Current Status (Verified) | Future Vision (Planned) |
| :--- | :--- | :--- |
| **User Interface** | PySide6 desktop GUI workspace + CLI shell with Dark Cyberpunk aesthetic. | Ambient floating overlay, companion mobile client over Wi-Fi/Tailscale. |
| **Inference Engine** | Local Ollama API (`qwen3:8b`, `qwen3:14b`, `qwen3-vl:8b`). | Dynamic local model orchestration with optional encrypted API fallbacks. |
| **Tool Registry** | Read-only inspection (`get_system_info`, `read_text_file`, `validate_image`). | Bounded write tools, Playwright web research, application launchers. |
| **Voice Interface** | One-turn Faster-Whisper STT with CUDA DLL preloading and noise gating. | Continuous hands-free conversation with wake-word and streaming TTS. |
| **Vision** | Static image file inspection via `qwen3-vl:8b` in chat/CLI. | Dynamic UI inspection, visual artifact verification. |
| **Agent Cognition** | v0.7 MultiAgentCoordinator (Planner/Executor delegation, DisagreementResolver, Orchestrator routing). | Multi-agent collaboration with specialized Critic and Reflector roles. |
| **Security Boundary** | ScopedPermissionManager, Async ApprovalGate, canonicalization, retry guards. | OS-level application sandboxing, fine-grained capability tokens. |
