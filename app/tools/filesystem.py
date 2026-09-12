from pathlib import Path
MAX_READ_BYTES = 512_000
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".log"}

def list_directory(path: str) -> list[dict]:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(str(p))
    if not p.is_dir():
        raise NotADirectoryError(str(p))
    return [{"name": item.name, "type": "directory" if item.is_dir() else "file"} for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))]

def read_text_file(path: str) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(str(p))
    if p.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError("File type is not allowlisted for text reading.")
    if p.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"File exceeds {MAX_READ_BYTES} byte safety limit.")
    return p.read_text(encoding="utf-8", errors="replace")
