# JASPER v0.3.0

**JASPER = Just Another Smart Program Executing Request**

Local-first personal AI assistant foundation for Windows 11.

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

Default model: `qwen3:14b`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull qwen3:14b
python -m app.main
```

Create `.env` from `.env.example` if you want to override defaults.

## What changed in v0.2

JASPER can now receive tool calls from Ollama, validate them through the permission layer, execute permitted read-only tools, return their results to the model, and continue the conversation until the model produces a final answer.

The current agent loop is capped at 5 tool rounds as a safety limit.

## Test it

Try these in the JASPER prompt:

```text
What CPU am I using?
```

```text
How much RAM do I have available?
```

```text
List the files in C:\\Users\\YOUR_NAME\\Downloads
```

The first two should trigger `get_system_info`. The third should trigger `list_directory`.

## Safety boundary

v0.2 intentionally has **no** delete-file, arbitrary shell, registry, admin, write, or other destructive tool. The permission layer denies every tool except declared `READ` tools.

Do not expose Ollama's local API to the public internet.

## Performance routing

JASPER v0.2.1 uses two local models when available:

- `qwen3:8b` for ordinary conversation and short/simple requests.
- `qwen3:14b` for tools, coding, analysis, planning, and more complex requests.

Ollama keeps the selected model loaded for `5m` by default to avoid repeatedly paying model load time between nearby requests. Thinking is disabled by default for conversational responsiveness; complex tasks can later opt into thinking explicitly.

Before running JASPER v0.2.1, pull the fast model:

```powershell
ollama pull qwen3:8b
```

To inspect whether a model is on the GPU, run:

```powershell
ollama ps
```

The `PROCESSOR` column reports GPU/CPU placement.

## v0.2.2 — Hardware & Runtime Awareness

v0.2.2 keeps the existing read-only tool-calling architecture and adds a richer `get_system_info` tool. It can now report:

- Friendly Windows CPU model name.
- Physical and logical CPU cores.
- RAM total, available, and usage.
- NVIDIA GPU name, VRAM total/used, GPU utilization, and driver version when `nvidia-smi` is available.
- System drive capacity and free space.
- Local Ollama availability and currently loaded models from `/api/ps`, including context length and VRAM allocation.

The hardware probe is read-only. It does not execute user-provided shell commands. NVIDIA data comes from a fixed `nvidia-smi` query, and Ollama state is read from the local loopback API.

### New hardware test

Ask JASPER:

```text
What CPU, GPU, RAM, and storage am I using?
```

For Ollama state:

```text
What model is currently loaded in Ollama, and how much VRAM is it using?
```


## v0.2.3 — System Information Accuracy

- Direct hardware/runtime fact questions force a fresh `get_system_info` observation before answering.
- RAM is read from the live system rather than inferred by the model.
- Storage is enumerated across mounted volumes rather than assuming a single 512 GB drive.
- Direct system-fact responses are formatted from observed tool values, avoiding LLM substitution of guessed hardware specifications.
- Existing read-only safety boundaries remain unchanged.

## v0.2.4 — Expanded Ground-Truth System Observation

- Expanded live-system fact detection beyond exact single-question patterns.
- Combined hardware/runtime questions such as CPU + GPU + RAM + storage + Ollama now force a fresh `get_system_info` observation.
- Added coverage for natural phrases such as `my PC specs` and `system information`.
- Conceptual questions such as `How much RAM should a gaming PC have?` remain with the normal LLM path.
- Direct system facts are still formatted only from observed tool values; no LLM guessing is used.


## v0.3.0 — Explicit Long-Term Memory

v0.3 adds a local, persistent long-term memory layer on top of the existing SQLite conversation history.

- User can explicitly save memories with natural language such as `Remember that my router is a Tenda TX3.`
- JASPER can recall saved memories when they are relevant to a later question.
- JASPER can list memories with `What do you remember about me?`.
- JASPER can forget matching memories with `Forget my router Tenda TX3.`
- Memory search uses deterministic local token overlap; no embeddings or external memory service are required.
- Only explicit user memory commands write long-term memories in v0.3. Automatic LLM-generated memory extraction is intentionally disabled for accuracy and privacy.
- Memory context is marked as user-provided remembered facts so the model is instructed not to invent or silently modify them.
- The existing read-only system tools remain unchanged.

### Memory examples

```text
Remember that my router is a Tenda TX3.
```

```text
What do you remember about my router?
```

```text
Forget my router Tenda TX3.
```

Long-term memories are stored locally in `data/jasper.db`.
