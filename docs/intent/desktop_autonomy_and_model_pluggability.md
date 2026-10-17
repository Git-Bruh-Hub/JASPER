# Statement of Intent: Desktop Autonomy & Pluggable Multi-Agent Models

> **Status:** Confirmed by User (2026-10-16)  
> **Source Authority:** Interactive intent extraction via `/interview-me`  
> **Target Branch:** `release/v0.7.3` / `main`  
> **Active Decision:** Desktop Autonomy (Phase 1) is **ACTIVE**; Gemma 26B/27B Integration (Phase 2) is **ON HOLD**

---

## 1. Intent Summary

- **Immediate Active Goal (Phase 1):** Enable real autonomous execution (`/auto`) in the PySide6 desktop GUI with live interactive `ApprovalDialog` modal prompts on Windows 11, utilizing the existing verified local Ollama models (`qwen3:14b` for multi-agent reasoning, `qwen3:8b` for general chat, and `qwen3-vl:8b` for vision).
- **Deferred Goal (Phase 2 — On Hold):** Implement model-agnostic multi-agent pluggability and integrate `gemma2:27b` (often referenced as Gemma 26B) as an alternative high-capacity Deep Planner alongside Qwen.

---

## 2. Core Dimensions of Intent

| Dimension | Specification |
| :--- | :--- |
| **Outcome** | Transition JASPER from an assistant whose autonomous mode only runs in test harnesses to a daily personal desktop assistant where typing `/auto <task>` in the GUI activates the Hive Mind coordinator and surfaces physical approval modals for user decision. |
| **User** | User operating JASPER locally on a personal Windows 11 desktop. |
| **Why Now** | The v0.7.3 foundation is cleanly committed with 465 passing automated tests. Keeping `/auto` hardcoded to return `"Autonomous mode is not enabled."` in `app/desktop.py` is the primary bottleneck preventing real-world hands-on use. |
| **Success Criteria** | Launch `.\.venv\Scripts\python.exe -m app.desktop`, enter an `/auto` task in chat, observe the coordinator plan the actions, see the modal `ApprovalDialog` appear on screen, and confirm or deny with mouse/keyboard to safely execute or abort bounded actions. |
| **Binding Constraints** | Mandatory human approval for side-effecting actions; strict workspace root containment; fail-closed execution on denial or timeout; fit within local hardware limits (NVIDIA RTX 3060 12GB VRAM + 32GB RAM). |
| **Out of Scope** | Unrestricted arbitrary shell execution (`powershell.exe`/`cmd.exe`); removing human confirmation prompts; continuous background surveillance. |

---

## 3. Staged Implementation Roadmap

### Phase 1: Desktop Autonomy Activation (Immediate Focus — In Progress)
1. **Desktop Coordinator Wiring:** Safely instantiate and wire `MultiAgentCoordinator` into `JasperWorker` in [`app/desktop.py`](file:///c:/Users/chitz/Desktop/JASPER%20Project/JASPER_v0.2.2/app/desktop.py).
2. **Safe Default Tool Scoping:** Provide safe, bounded tools for initial desktop `/auto` turns (e.g., system observation, structured read tools, and in-workspace controlled tools).
3. **Interactive Human Verification:** Launch the live desktop app and physically verify the end-to-end user experience (request → planning → approval dialog → click allow/deny → response).

### Phase 2: Model Pluggability & Gemma Integration (On Hold)
1. **Configurable Model Architecture:** Abstract model assignment so Planner, Executor, and Chat roles can be configured via environment variables or UI settings without hardcoding model names.
2. **Gemma 27B Evaluation:** Test local performance of `gemma2:27b` via Ollama on RTX 3060 (evaluating VRAM split and inference latency across 12GB VRAM + 32GB RAM).
3. **Specialized Planner Prompting:** Optimize task decomposition prompts for Gemma's instruction-following format.

---

## 4. Preserved Intent Record: Gemma 26B/27B Integration

### 4.1 Background & Motivation
- **Context:** The user inquired about extending JASPER's reasoning capabilities beyond `qwen3` to include Google's Gemma model family (specifically `gemma2:27b`, colloquially referenced as Gemma 26B).
- **Vision:** Gemma 27B offers strong high-order deductive reasoning and analytical planning capabilities. Adding it as a pluggable Deep Planner allows users to leverage Gemma for complex multi-step strategy while keeping lightweight models (e.g., `qwen3:8b` or `qwen3:14b`) for rapid tool execution and conversational chat.

### 4.2 Architectural Design for Future Implementation
1. **Role-Based Model Configuration:**
   - Decouple model names from agent code into configurable roles:
     - `PLANNER_MODEL`: Default `qwen3:14b`, selectable `gemma2:27b`.
     - `EXECUTOR_MODEL`: Default `qwen3:8b` or `qwen3:14b`.
     - `VISION_MODEL`: `qwen3-vl:8b`.
     - `CHAT_MODEL`: `qwen3:8b`.
2. **Local Hardware Budget & Offloading Strategy:**
   - Host GPU: NVIDIA RTX 3060 (12GB GDDR6 VRAM).
   - Host Memory: 32GB System RAM.
   - For `gemma2:27b` (Q4_K_M ~16GB weights): Partial GPU offloading via Ollama (e.g., 20–24 layers in VRAM, remainder in RAM) or dynamic sequential loading (unloading executor while planner runs).
3. **Prompt Adaptation:**
   - Gemma models utilize `<start_of_turn>user ... <end_of_turn>` and `<start_of_turn>model ... <end_of_turn>` markup.
   - Ensure the multi-agent prompt serializer properly conforms to Gemma's turn tokens without leaking raw tags.

### 4.3 Decision to Hold & Resumption Criteria
- **User Decision (2026-10-16):** Put Gemma 26B/27B on hold. Prioritize Phase 1 first so the user can immediately experience autonomous mode and visual approval dialogs in the desktop application.
- **Resumption Trigger:** Re-evaluate and implement Phase 2 once Phase 1 desktop autonomy is fully wired, verified with regression tests, and accepted via interactive visual testing.
