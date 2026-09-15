import asyncio
import logging

from app.core.config import (
    JASPER_PIPER_CONFIG,
    JASPER_PIPER_MODEL,
    JASPER_PIPER_USE_CUDA,
    JASPER_STT_BEAM_SIZE,
    JASPER_STT_CPU_COMPUTE_TYPE,
    JASPER_STT_DEVICE,
    JASPER_STT_GPU_COMPUTE_TYPE,
    JASPER_STT_INITIAL_PROMPT,
    JASPER_STT_LANGUAGE,
    JASPER_STT_MODEL,
    JASPER_TTS_PROVIDER,
    JASPER_TTS_RATE,
    JASPER_TTS_VOLUME,
    JASPER_TTS_VOICE,
    JASPER_VOICE_CONVERSATION_EMPTY_LIMIT,
    JASPER_VOICE_CONVERSATION_MAX_TURNS,
    JASPER_VOICE_ENABLED,
    JASPER_VOICE_MIN_SECONDS,
    JASPER_VOICE_RECORD_MAX_SECONDS,
    JASPER_VOICE_SAMPLE_RATE,
    JASPER_VOICE_SILENCE_SECONDS,
    JASPER_VOICE_SILENCE_THRESHOLD,
    VOICE_TEMP_DIR,
)
from app.core.logging_setup import setup_logging
from app.core.orchestrator import Orchestrator
from app.core.permissions import PermissionManager
from app.memory.sqlite_memory import SQLiteMemory
from app.tools.filesystem import list_directory, read_text_file
from app.tools.registry import Risk, Tool, ToolRegistry
from app.tools.system import get_system_info
from app.voice.manager import VoiceManager
from app.voice.stt import FasterWhisperSTT
from app.voice.tts import PiperTTS, WindowsSpeechTTS


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(
        "get_system_info",
        "Read detailed non-sensitive local system information such as operating system, CPU, GPU, RAM, storage, and local Ollama model state.",
        Risk.READ,
        get_system_info,
        parameters={
            "type": "object",
            "properties": {},
        },
    ))
    registry.register(Tool(
        "list_directory",
        "List entries in a directory without modifying anything.",
        Risk.READ,
        list_directory,
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to inspect, for example C:\\Users\\Name\\Downloads.",
                }
            },
            "required": ["path"],
        },
    ))
    registry.register(Tool(
        "read_text_file",
        "Read a small allowlisted text file without modifying it.",
        Risk.READ,
        read_text_file,
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to a small allowlisted text file.",
                }
            },
            "required": ["path"],
        },
    ))
    return registry


def build_voice_manager() -> VoiceManager:
    stt = FasterWhisperSTT(
        JASPER_STT_MODEL,
        device=JASPER_STT_DEVICE,
        gpu_compute_type=JASPER_STT_GPU_COMPUTE_TYPE,
        cpu_compute_type=JASPER_STT_CPU_COMPUTE_TYPE,
        language=JASPER_STT_LANGUAGE,
        beam_size=JASPER_STT_BEAM_SIZE,
        initial_prompt=JASPER_STT_INITIAL_PROMPT,
    )

    if JASPER_TTS_PROVIDER == "windows":
        tts = WindowsSpeechTTS(
            voice=JASPER_TTS_VOICE,
            rate=JASPER_TTS_RATE,
            volume=JASPER_TTS_VOLUME,
        )
    elif JASPER_TTS_PROVIDER == "piper":
        tts = PiperTTS(
            JASPER_PIPER_MODEL,
            config_path=JASPER_PIPER_CONFIG,
            use_cuda=JASPER_PIPER_USE_CUDA,
        )
    else:
        raise ValueError(
            f"Unsupported JASPER_TTS_PROVIDER={JASPER_TTS_PROVIDER!r}. "
            "Use 'windows' or 'piper'."
        )

    return VoiceManager(
        stt,
        tts,
        temp_dir=VOICE_TEMP_DIR,
        max_seconds=JASPER_VOICE_RECORD_MAX_SECONDS,
        sample_rate=JASPER_VOICE_SAMPLE_RATE,
        silence_seconds=JASPER_VOICE_SILENCE_SECONDS,
        silence_threshold=JASPER_VOICE_SILENCE_THRESHOLD,
        min_seconds=JASPER_VOICE_MIN_SECONDS,
    )


def print_voice_turn(turn_number: int, user_text: str, answer: str) -> None:
    print(f"You (voice {turn_number}): {user_text}")
    print(f"JASPER: {answer}\n")


async def main():
    setup_logging()
    log = logging.getLogger("jasper")
    jasper = Orchestrator(build_registry(), PermissionManager(), SQLiteMemory())
    voice = build_voice_manager() if JASPER_VOICE_ENABLED else None

    print("JASPER v0.4.1")
    print("Tool calling + explicit long-term memory enabled.")
    if voice:
        print("Voice enabled. Use ':voice' for one turn, ':conversation' for continuous conversation, or ':speak <text>'.")
    else:
        print("Voice disabled. Set JASPER_VOICE_ENABLED=true to enable it.")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break

        if user_text.lower() == ":voice":
            if voice is None:
                print("JASPER: Voice is disabled. Enable JASPER_VOICE_ENABLED in .env and restart.\n")
                continue
            try:
                print("JASPER: Listening...")
                spoken_text, answer = await voice.run_once(jasper.respond)
                if not spoken_text:
                    print("JASPER: I didn't detect any speech.\n")
                    continue
                print(f"You (voice): {spoken_text}")
                print(f"JASPER: {answer}\n")
            except Exception as exc:
                log.exception("Voice request failed")
                print(f"JASPER: Voice request failed: {exc}\n")
            continue

        if user_text.lower() == ":conversation":
            if voice is None:
                print("JASPER: Voice is disabled. Enable JASPER_VOICE_ENABLED in .env and restart.\n")
                continue
            try:
                print("JASPER: Conversation mode started. Say 'stop listening' to end it.\n")
                turns = await voice.run_conversation(
                    jasper.respond,
                    max_turns=JASPER_VOICE_CONVERSATION_MAX_TURNS,
                    empty_limit=JASPER_VOICE_CONVERSATION_EMPTY_LIMIT,
                    on_listen_start=lambda turn: print(f"JASPER: Listening (turn {turn})..."),
                    on_turn=print_voice_turn,
                )
                print(f"JASPER: Conversation mode ended after {len(turns)} response(s).\n")
            except Exception as exc:
                log.exception("Voice conversation failed")
                print(f"JASPER: Voice conversation failed: {exc}\n")
            continue

        if user_text.lower().startswith(":speak"):
            if voice is None:
                print("JASPER: Voice is disabled. Enable JASPER_VOICE_ENABLED in .env and restart.\n")
                continue
            text_to_speak = user_text[len(":speak"):].strip()
            if not text_to_speak:
                print("JASPER: Usage: :speak <text>\n")
                continue
            try:
                voice.speak(text_to_speak)
                print("JASPER: Spoken.\n")
            except Exception as exc:
                log.exception("TTS request failed")
                print(f"JASPER: TTS failed: {exc}\n")
            continue

        try:
            answer = await jasper.respond(user_text)
            print(f"JASPER: {answer}\n")
        except Exception as exc:
            log.exception("Request failed")
            print(f"JASPER: I couldn't complete that request: {exc}\n")


if __name__ == "__main__":
    asyncio.run(main())
