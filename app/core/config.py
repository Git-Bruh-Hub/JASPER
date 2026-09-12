from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "jasper.db"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
JASPER_MODEL = os.getenv("JASPER_MODEL", "qwen3:14b")
JASPER_FAST_MODEL = os.getenv("JASPER_FAST_MODEL", "qwen3:8b")
JASPER_KEEP_ALIVE = os.getenv("JASPER_KEEP_ALIVE", "5m")
JASPER_THINK = os.getenv("JASPER_THINK", "false").lower() in {"1", "true", "yes", "on"}
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
