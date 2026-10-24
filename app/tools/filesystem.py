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

def read_text_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(str(p))
    if p.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError("File type is not allowlisted for text reading.")
    if p.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"File exceeds {MAX_READ_BYTES} byte safety limit.")
    
    content = p.read_text(encoding="utf-8", errors="replace")
    if start_line is None and end_line is None:
        return content

    lines = content.splitlines(keepends=False)
    total_lines = len(lines)
    s = max(1, start_line or 1)
    e = min(total_lines, end_line if end_line is not None else total_lines)
    if s > total_lines:
        return f"[Line {s} is beyond end of file ({total_lines} lines total)]"

    sliced = [f"{i}: {lines[i - 1]}" for i in range(s, e + 1)]
    return "\n".join(sliced)


def edit_file_chunk(path: str, target: str, replacement: str) -> dict:
    """Surgically replace a unique target block in a text file with replacement content."""
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    if p.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError(f"File extension '{p.suffix}' is not allowlisted for text editing.")

    content = p.read_text(encoding="utf-8", errors="replace")
    occurrences = content.count(target)
    if occurrences == 0:
        raise ValueError(f"Target string not found in {p.name}. Ensure target exactly matches existing file content.")
    if occurrences > 1:
        raise ValueError(f"Target string occurs {occurrences} times in {p.name}. Provide a more specific target block to ensure unique replacement.")

    new_content = content.replace(target, replacement, 1)
    new_bytes = new_content.encode("utf-8")
    if len(new_bytes) > MAX_READ_BYTES:
        raise ValueError(f"Updated content exceeds {MAX_READ_BYTES} byte safety limit.")

    p.write_text(new_content, encoding="utf-8")
    return {
        "status": "success",
        "path": str(p),
        "filename": p.name,
        "bytes_written": len(new_bytes),
        "message": f"Successfully replaced target chunk in {p.name}.",
    }


def write_text_file(path: str, content: str) -> dict:
    p = Path(path).expanduser().resolve()
    if p.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError(f"File extension '{p.suffix}' is not allowlisted for text writing.")
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_READ_BYTES:
        raise ValueError(f"Content exceeds {MAX_READ_BYTES} byte safety limit.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"path": str(p), "bytes_written": len(content_bytes), "status": "written"}

