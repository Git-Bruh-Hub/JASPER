# JASPER v0.4.1

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

## v0.4.0 — Voice Interface Foundation

v0.4 adds voice as an interface around the existing JASPER Core instead of putting speech logic inside the reasoning system.

Architecture:

```text
Text  ────────────────────────┐
                              ↓
Voice → STT → JASPER Core → response → TTS → Voice
```

### Voice features

- `SpeechToTextProvider` and `TextToSpeechProvider` abstractions keep providers replaceable.
- Local STT uses `faster-whisper` with lazy model loading.
- STT defaults to GPU with automatic CPU fallback when CUDA is unavailable.
- On Windows, JASPER automatically discovers NVIDIA CUDA runtime wheels inside the active Python environment and configures their DLL directories for the current process. It does not modify the user's permanent Windows PATH.
- The voice dependency set includes CUDA 12 cuBLAS, CUDA runtime, NVRTC, and cuDNN 9 runtime packages for the current CTranslate2 GPU stack.
- Audio recording is local and stops after configurable silence or a maximum duration.
- Windows built-in Speech Synthesis is the default TTS provider, so a neural TTS model is not required for the first voice test.
- Piper TTS is available as an optional local neural provider.
- Voice dependencies live in `requirements-voice.txt`; the normal text-only installation remains lightweight.
- Voice is disabled by default through `JASPER_VOICE_ENABLED=false`.
- No wake-word listener is enabled in v0.4.
- No autonomous voice-triggered actions are introduced in v0.4.

### Enable voice

Install the optional voice stack:

```powershell
pip install -r requirements-voice.txt
```

Then set in `.env`:

```text
JASPER_VOICE_ENABLED=true
```

Start JASPER and use:

```text
:voice
```

JASPER records one utterance, transcribes it locally, sends the text through the normal JASPER Core, then speaks the response.

You can also use:

```text
:speak Hello from JASPER.
```

for a direct TTS test.

### STT configuration

`faster-whisper` can run on NVIDIA CUDA or CPU. The current Windows GPU setup uses CUDA 12 and cuDNN 9 runtime packages installed in the Python environment. JASPER configures their package-local DLL directories automatically before loading Faster-Whisper. Keep `JASPER_STT_DEVICE=auto` unless you have a reason to force a device.

Defaults:

```text
JASPER_STT_MODEL=small
JASPER_STT_DEVICE=auto
JASPER_STT_GPU_COMPUTE_TYPE=int8_float16
JASPER_STT_CPU_COMPUTE_TYPE=int8
JASPER_STT_LANGUAGE=auto
```

### TTS configuration

Default provider:

```text
JASPER_TTS_PROVIDER=windows
```

For local neural Piper TTS, install `piper-tts`, download a compatible voice model, then configure:

```text
JASPER_TTS_PROVIDER=piper
JASPER_PIPER_MODEL=data/voices/en_US-lessac-medium.onnx
JASPER_PIPER_CONFIG=data/voices/en_US-lessac-medium.onnx.json
```

Voice models are external assets and should be stored locally rather than committed to the JASPER repository.

## v0.4.1 — Voice Quality + Continuous Conversation

v0.4.1 improves the voice layer without bypassing the existing JASPER Core.

### Better multilingual STT control

- `JASPER_STT_LANGUAGE=auto` remains the default for mixed English/Bahasa Malaysia/rojak speech.
- Common aliases such as `bm`, `malay`, and `bahasa melayu` are normalized to Whisper's `ms` language code when a fixed language is desired.
- `JASPER_STT_BEAM_SIZE` controls decoding breadth; the default remains `5`.
- `JASPER_STT_INITIAL_PROMPT` is available as an optional vocabulary/context hint. It is blank by default so users do not accidentally bias recognition.

### Continuous conversation

Use:

```text
:conversation
```

JASPER will listen, respond, speak, and listen again. The loop is deliberately bounded:

- Maximum turns: `JASPER_VOICE_CONVERSATION_MAX_TURNS` (default `8`).
- Repeated empty recordings end the session after `JASPER_VOICE_CONVERSATION_EMPTY_LIMIT` (default `2`).
- Local stop phrases such as `stop listening`, `goodbye jasper`, and `berhenti jasper` end the loop without sending the phrase to the LLM.
- The loop is **not** an always-listening service and does **not** use a wake word.
- Every non-stop utterance still goes through the normal JASPER Orchestrator, memory, tools, and permission checks.

### More natural TTS

Common Markdown formatting in JASPER responses is normalized before speech so the TTS engine does not read formatting markers aloud. Windows TTS voice, rate, and volume can also be configured through `.env`.

### v0.4.1 safety boundary

Continuous conversation only changes how voice input is collected. It does not create new PC-control permissions, background listeners, or autonomous execution paths.
