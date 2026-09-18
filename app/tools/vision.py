"""Read-only image inspection tool for the JASPER tool registry."""

from __future__ import annotations

from pathlib import Path

from app.vision.image import DEFAULT_MAX_IMAGE_BYTES, SUPPORTED_IMAGE_EXTENSIONS


# Known image magic byte signatures.
# These are checked against the first bytes of the file to reject non-image
# files that have been renamed with an image extension.  This runs at the LLM
# trust boundary *before* VisionManager or the Ollama provider read the file.
_IMAGE_SIGNATURES: tuple[bytes, ...] = (
    b"\x89PNG\r\n\x1a\n",       # PNG
    b"\xff\xd8\xff",             # JPEG (all variants)
    b"RIFF",                     # WebP (RIFF container; "WEBP" at offset 8)
)


def validate_image_path(raw_path: str) -> Path:
    """Resolve, validate, and content-check an image path.

    This is the LLM trust boundary: the path originates from a model-selected
    tool argument and must be validated before it reaches VisionManager or the
    filesystem.

    Checks applied:
    1. Path resolves to an existing file.
    2. File extension is in the supported image allowlist.
    3. File size does not exceed the safety limit.
    4. File header bytes match a known image signature (rejects non-image
       files that were renamed with an image extension).
    """
    path = Path(raw_path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
        raise ValueError(
            f"Unsupported image type '{suffix}'. Supported types: {supported}"
        )

    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"Image file is empty: {path}")
    if size > DEFAULT_MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image is too large ({size / 1024 / 1024:.1f} MB). "
            f"Maximum allowed is {DEFAULT_MAX_IMAGE_BYTES / 1024 / 1024:.1f} MB."
        )

    # Read the first 12 bytes to verify the file contains actual image data.
    # This prevents an LLM from tricking the tool into reading an arbitrary
    # file that was given an image extension.
    with path.open("rb") as handle:
        header = handle.read(12)
    if not any(header.startswith(sig) for sig in _IMAGE_SIGNATURES):
        raise ValueError(
            f"File does not contain valid image data: {path.name}"
        )

    # WebP requires an additional check: bytes 8-12 must be "WEBP".
    if header[:4] == b"RIFF" and header[8:12] != b"WEBP":
        raise ValueError(
            f"File does not contain valid image data: {path.name}"
        )

    return path
