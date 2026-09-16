from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "jasper.db"
VOICE_TEMP_DIR = DATA_DIR / "voice"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
VOICE_TEMP_DIR.mkdir(exist_ok=True)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
JASPER_MODEL = os.getenv("JASPER_MODEL", "qwen3:14b")
JASPER_FAST_MODEL = os.getenv("JASPER_FAST_MODEL", "qwen3:8b")
JASPER_KEEP_ALIVE = os.getenv("JASPER_KEEP_ALIVE", "5m")
JASPER_THINK = os.getenv("JASPER_THINK", "false").lower() in {"1", "true", "yes", "on"}
JASPER_MAX_OUTPUT_TOKENS = max(128, int(os.getenv("JASPER_MAX_OUTPUT_TOKENS", "768")))

# Vision is intentionally isolated from the text-model configuration so a future
# vision provider/model can be changed without affecting normal chat routing.
JASPER_VISION_MODEL = os.getenv("JASPER_VISION_MODEL", "qwen3-vl:8b")
JASPER_VISION_KEEP_ALIVE = os.getenv("JASPER_VISION_KEEP_ALIVE", "5m")
JASPER_VISION_THINK = os.getenv("JASPER_VISION_THINK", "false").lower() in {"1", "true", "yes", "on"}
JASPER_VISION_MAX_OUTPUT_TOKENS = max(128, int(os.getenv("JASPER_VISION_MAX_OUTPUT_TOKENS", "512")))
JASPER_VISION_MAX_IMAGE_MB = max(1, int(os.getenv("JASPER_VISION_MAX_IMAGE_MB", "10")))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
JASPER_MEMORY_ENABLED = os.getenv("JASPER_MEMORY_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
JASPER_MEMORY_SEARCH_LIMIT = max(1, int(os.getenv("JASPER_MEMORY_SEARCH_LIMIT", "5")))

# Voice configuration. Heavy audio/AI dependencies stay optional so text-only
# JASPER remains lightweight and usable when voice is disabled.
JASPER_VOICE_ENABLED = os.getenv("JASPER_VOICE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
JASPER_STT_MODEL = os.getenv("JASPER_STT_MODEL", "small")
JASPER_STT_DEVICE = os.getenv("JASPER_STT_DEVICE", "auto")
JASPER_STT_GPU_COMPUTE_TYPE = os.getenv("JASPER_STT_GPU_COMPUTE_TYPE", "int8_float16")
JASPER_STT_CPU_COMPUTE_TYPE = os.getenv("JASPER_STT_CPU_COMPUTE_TYPE", "int8")
JASPER_STT_LANGUAGE = os.getenv("JASPER_STT_LANGUAGE", "ms")
JASPER_STT_BEAM_SIZE = max(1, int(os.getenv("JASPER_STT_BEAM_SIZE", "5")))
JASPER_STT_INITIAL_PROMPT = os.getenv("JASPER_STT_INITIAL_PROMPT", "")
JASPER_TTS_PROVIDER = os.getenv("JASPER_TTS_PROVIDER", "windows").lower()
JASPER_TTS_VOICE = os.getenv("JASPER_TTS_VOICE", "") or None
JASPER_TTS_RATE = int(os.getenv("JASPER_TTS_RATE", "0"))
JASPER_TTS_VOLUME = max(0, min(100, int(os.getenv("JASPER_TTS_VOLUME", "100"))))
JASPER_PIPER_MODEL = Path(os.getenv("JASPER_PIPER_MODEL", str(DATA_DIR / "voices" / "en_US-lessac-medium.onnx")))
JASPER_PIPER_CONFIG = Path(os.getenv("JASPER_PIPER_CONFIG", str(DATA_DIR / "voices" / "en_US-lessac-medium.onnx.json")))
JASPER_PIPER_USE_CUDA = os.getenv("JASPER_PIPER_USE_CUDA", "false").lower() in {"1", "true", "yes", "on"}
JASPER_VOICE_SAMPLE_RATE = int(os.getenv("JASPER_VOICE_SAMPLE_RATE", "16000"))
JASPER_VOICE_RECORD_MAX_SECONDS = float(os.getenv("JASPER_VOICE_RECORD_MAX_SECONDS", "8"))
JASPER_VOICE_MIN_SECONDS = float(os.getenv("JASPER_VOICE_MIN_SECONDS", "0.6"))
JASPER_VOICE_SILENCE_SECONDS = float(os.getenv("JASPER_VOICE_SILENCE_SECONDS", "0.9"))
JASPER_VOICE_SILENCE_THRESHOLD = float(os.getenv("JASPER_VOICE_SILENCE_THRESHOLD", "0.01"))
JASPER_VOICE_CONVERSATION_MAX_TURNS = max(1, int(os.getenv("JASPER_VOICE_CONVERSATION_MAX_TURNS", "8")))
JASPER_VOICE_CONVERSATION_EMPTY_LIMIT = max(1, int(os.getenv("JASPER_VOICE_CONVERSATION_EMPTY_LIMIT", "2")))
