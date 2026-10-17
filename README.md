# JASPER (v0.7 Core)

**JASPER = Just Another Smart Program Executing Request**

Local-first personal AI assistant foundation for Windows 11. Built on a capability-based security boundary with Ollama inference, explicit memory, PySide6 desktop workspace, multimodal vision, and Hive Mind multi-agent coordination.

## v0.2 scope

- Local Ollama chat
- English / Bahasa Malaysia / casual rojak instruction handling
- Model-provider abstraction
- **Ollama tool calling / agent loop**
- Read-only tool registry
- Permission policy
- SQLite conversation/event memory
- Structured logging
- System-info and filesystem read tools
- Clean extension points for browser, voice, vision, multi-agent cognition and autonomy

## Requirements

- Windows 11
- Python 3.12+
- Ollama installed and running
- A local Ollama model with tool-calling support

Default text model: `qwen3:14b`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull qwen3:8b
ollama pull qwen3:14b
python -m app.main
```

Create `.env` from `.env.example` if you want to override defaults.

## Desktop workspace — v0.4.2

JASPER now has a Windows desktop workspace around the existing JASPER Core. It is intentionally dark, clean, compact, and simple to navigate.

Install the GUI dependency:

```powershell
pip install -r requirements-desktop.txt
```

Launch it with:

```powershell
python -m app.desktop
```

The first desktop milestone provides:

- Chat workspace using the existing Orchestrator.
- Optional one-turn voice input/output through the existing voice layer.
- Live system footer for Ollama, voice, memory/tools, and detected GPU state.
- Windows system-tray entry with Open and Exit.
- Navigation placeholders for Tasks, Vision, Agents, Files, Web, and Settings so later capabilities have stable UI homes.
- GUI code isolated from JASPER Core so future vision and multi-agent work can plug into the same application.

The CLI remains available for development:

```powershell
python -m app.main
```

## v0.6.1 — Vision Foundation & Adaptive Cognition

v0.5 adds a provider-independent local vision layer without giving the vision model permission to control the computer.

Architecture:

```text
Image file
   ↓
VisionManager
   ↓
VisionRouter
   ↓
VisionProvider
   ↓
VisionResult
   ↓
Future JASPER Core integration
```

The first implementation uses Ollama's multimodal `/api/chat` interface and sends image data through the message `images` field. It does not add external cloud vision services, continuous screen monitoring, or computer-control actions.

Current local baseline:

```text
JASPER_VISION_MODEL=qwen3-vl:8b
JASPER_VISION_MAX_OUTPUT_TOKENS=512
JASPER_VISION_MAX_IMAGE_MB=10
```

Install the vision model separately:

```powershell
ollama pull qwen3-vl:8b
```

The CLI can test the foundation before the desktop Vision workspace is wired in:

```text
:vision <image-path> <question>
```

Example:

```text
:vision C:\Users\Name\Pictures\test.png What is in this image?
```

Safety boundary for v0.6.1:

- Image files are read-only inputs.
- Vision analysis does not click, type, delete, execute commands, or modify the machine.
- Continuous screen watching is not enabled.
- Visual observations are kept separate from verified system facts.
- Provider/model choice is configurable rather than hard-coded into JASPER Core.

## v0.2.2 — Hardware & Runtime Awareness

`get_system_info` can report the Windows CPU model, CPU core counts, live RAM values, NVIDIA GPU/VRAM state, mounted storage volumes, and local Ollama `/api/ps` state.

## v0.2.3 — System Information Accuracy

- Direct hardware/runtime fact questions force a fresh `get_system_info` observation before answering.
- RAM and storage are read from the live machine rather than inferred by the model.
- Direct system-fact responses are formatted from observed tool values.

## v0.2.4 — Expanded Ground-Truth System Observation

- Combined hardware/runtime questions and common phrases such as `my PC specs` force a fresh system observation.
- Conceptual questions remain on the normal LLM path.

## v0.3.0 — Explicit Long-Term Memory

v0.3 adds a local persistent memory layer.

- Use `Remember that ...` to explicitly save a long-term memory.
- Ask `What do you remember about ...?` to recall it.
- Use `Forget ...` to remove a matching memory.
- Memory search is deterministic and local; no embeddings or external memory service are required.
- Only explicit user memory commands write long-term memories.

## v0.4.0 — Voice Interface Foundation

Voice remains an interface around the existing JASPER Core:

```text
Voice → STT → JASPER Core → response → TTS
```

The voice stack uses local Faster-Whisper STT and Windows Speech TTS by default, with optional Piper TTS. Voice dependencies remain separate in `requirements-voice.txt`.

Enable voice with:

```text
JASPER_VOICE_ENABLED=true
```

Useful commands in the CLI are `:voice`, `:conversation`, and `:speak <text>`.

## v0.4.1 — Voice Quality + Continuous Conversation

- Configurable STT language, beam size, and initial prompt.
- Bounded `:conversation` mode.
- Explicit local English stop phrases, with `stop listening` as the canonical control phrase.
- TTS formatting cleanup and configurable Windows voice/rate/volume.
- Continuous conversation does not create an always-listening or wake-word service.

## v0.4.2 — Desktop + Tested STT Baseline

The current tested STT baseline is fixed Malay recognition (`ms`) rather than automatic language detection. The language setting is an STT control only; the LLM still receives text and can understand/respond in English, Bahasa Malaysia, or BM-English rojak.

Defaults:

```text
JASPER_STT_MODEL=small
JASPER_STT_DEVICE=auto
JASPER_STT_GPU_COMPUTE_TYPE=int8_float16
JASPER_STT_CPU_COMPUTE_TYPE=int8
JASPER_STT_LANGUAGE=ms
JASPER_STT_BEAM_SIZE=5
```

The desktop interface is the main application shell. Vision, richer task management, adaptive multi-agent cognition, web research, and automation can be added behind the existing navigation instead of requiring a future GUI rewrite.

## Safety boundary

JASPER still uses a read-only permission layer. The current tool set has no arbitrary shell, delete-file, registry, admin, or destructive tool.

## v0.7 — Hive Mind Multi-Agent Architecture, Desktop Approval & Live Harness Verification

The repository implements the v0.7 Hive Mind multi-agent architecture (Slices 1–7), desktop approval integration, and controlled live-model verification (Steps 7–18B):
- Typed contracts (`app/agents/contracts.py`).
- Capability-based `ScopedPermissionManager` with workspace boundary containment.
- Asynchronous `ApprovalGate` and thread-safe resolution API (`Coordinator.resolve_approval`).
- Guarded `Coordinator` recovery (`MultiAgentCoordinator.reset()`) and planner rejection audit events.
- PySide6 desktop approval presentation bridge (`JasperWorker.approval_requested`) and modal dialog (`ApprovalDialog`) with recursive privacy redaction.
- Response sanitization (`sanitize_thinking_tags`) stripping model reasoning artifacts.
- Deterministic end-to-end integration test suite (`tests/test_desktop_approval_e2e.py`).
- Isolated live-model test harness (`tests/support/live_harness.py`, `tests/test_live_harness_contracts.py`) validated against local Ollama `qwen3:14b`.

> **Security Note:** Desktop autonomous execution (`/auto`) is **disabled by default** in normal desktop startup (`app/desktop.py`) and fails closed unless a coordinator is explicitly injected in a controlled test harness.

## Documentation

For technical architecture, design principles, and engineering decisions:
- [Architecture & Concurrency Flow](docs/ARCHITECTURE.md) — System request flow, cognitive modes, and capability boundaries
- [Architecture Decision Records (ADRs)](docs/DECISIONS.md) — 20 documented decisions on security, state machines, and fail-closed policies
- [Project Vision & Core Principles](docs/PROJECT_VISION.md) — Local-first privacy, bounded autonomy, and permission gating
- [Development Roadmap](docs/ROADMAP.md) — Planned capabilities and milestone tracking
- [Windows Standalone Packaging](docs/deployment/windows_packaging.md) — Instructions for building the standalone PyInstaller release

