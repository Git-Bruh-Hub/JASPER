from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class VisionImage:
    path: Path
    media_type: str
    base64_data: str


def _detect_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    try:
        return mapping[suffix]
    except KeyError as exc:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
        raise ValueError(f"Unsupported image type '{suffix}'. Supported types: {supported}") from exc


def load_image(path: str | Path, *, max_bytes: int = DEFAULT_MAX_IMAGE_BYTES) -> VisionImage:
    """Validate a local image file and prepare its base64 representation."""
    image_path = Path(path).expanduser().resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    media_type = _detect_media_type(image_path)
    size = image_path.stat().st_size
    if size <= 0:
        raise ValueError(f"Image file is empty: {image_path}")
    if size > max_bytes:
        raise ValueError(
            f"Image is too large ({size / 1024 / 1024:.1f} MB). "
            f"Maximum allowed is {max_bytes / 1024 / 1024:.1f} MB."
        )

    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return VisionImage(path=image_path, media_type=media_type, base64_data=data)
