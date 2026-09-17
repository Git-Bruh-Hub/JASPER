"""Tests for the inspect_image tool handler and vision tool registration."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.main import build_registry
from app.tools.registry import Risk
from app.tools.vision import validate_image_path
from app.vision.base import VisionProvider, VisionResult
from app.vision.manager import VisionManager
from app.vision.router import VisionRouter


# ---------------------------------------------------------------------------
# Minimal valid image bytes for each supported format.
# Each is the smallest valid file of its type so tests verify real content,
# not just file extensions.
# ---------------------------------------------------------------------------

# Valid 1x1 PNG (standard test pixel).
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

# Valid 1x1 JPEG — minimal JFIF with SOI, APP0, SOF0, SOS, EOI markers.
JPEG_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
    "BwYIDAoMCwsKCwsNCxAQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQME"
    "BAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
    "FBQUFBQUFBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/"
    "EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAA"
    "AAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AKwA//9k="
)

# Valid 1x1 WebP — minimal lossy WebP (RIFF + WEBP + VP8 chunk).
WEBP_BYTES = base64.b64decode(
    "UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AA/vv9UAA="
)


# ---------------------------------------------------------------------------
# validate_image_path tests
# ---------------------------------------------------------------------------


def test_validate_accepts_valid_png(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)

    result = validate_image_path(str(image))

    assert result == image.resolve()


def test_validate_accepts_valid_jpg(tmp_path: Path) -> None:
    image = tmp_path / "photo.jpg"
    image.write_bytes(JPEG_BYTES)

    result = validate_image_path(str(image))

    assert result == image.resolve()


def test_validate_accepts_valid_jpeg(tmp_path: Path) -> None:
    image = tmp_path / "photo.jpeg"
    image.write_bytes(JPEG_BYTES)

    result = validate_image_path(str(image))

    assert result == image.resolve()


def test_validate_accepts_valid_webp(tmp_path: Path) -> None:
    image = tmp_path / "photo.webp"
    image.write_bytes(WEBP_BYTES)

    result = validate_image_path(str(image))

    assert result == image.resolve()


def test_validate_rejects_unsupported_extension(tmp_path: Path) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not an image", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported image type"):
        validate_image_path(str(text_file))


def test_validate_rejects_executable(tmp_path: Path) -> None:
    exe_file = tmp_path / "malicious.exe"
    exe_file.write_bytes(b"\x00" * 100)

    with pytest.raises(ValueError, match="Unsupported image type"):
        validate_image_path(str(exe_file))


def test_validate_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Image file not found"):
        validate_image_path(str(tmp_path / "missing.png"))


def test_validate_rejects_oversized_file(tmp_path: Path) -> None:
    image = tmp_path / "huge.png"
    # Write a file slightly over the 10 MB default limit with valid PNG header.
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024 + 1))

    with pytest.raises(ValueError, match="Image is too large"):
        validate_image_path(str(image))


def test_validate_rejects_empty_file(tmp_path: Path) -> None:
    image = tmp_path / "empty.png"
    image.write_bytes(b"")

    with pytest.raises(ValueError, match="Image file is empty"):
        validate_image_path(str(image))


def test_validate_rejects_non_image_renamed_to_png(tmp_path: Path) -> None:
    """A plain text file renamed to .png must be rejected by content check."""
    fake = tmp_path / "not_really.png"
    fake.write_text("This is just text pretending to be a PNG.", encoding="utf-8")

    with pytest.raises(ValueError, match="does not contain valid image data"):
        validate_image_path(str(fake))


def test_validate_rejects_non_image_renamed_to_jpg(tmp_path: Path) -> None:
    """A ZIP file renamed to .jpg must be rejected by content check."""
    fake = tmp_path / "not_really.jpg"
    # ZIP magic bytes: PK\x03\x04
    fake.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

    with pytest.raises(ValueError, match="does not contain valid image data"):
        validate_image_path(str(fake))


def test_validate_rejects_non_webp_riff_renamed_to_webp(tmp_path: Path) -> None:
    """A RIFF file that is not WebP (e.g. WAV) renamed to .webp must be rejected."""
    fake = tmp_path / "audio.webp"
    # RIFF....WAVE — valid RIFF header but not WebP
    fake.write_bytes(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 100)

    with pytest.raises(ValueError, match="does not contain valid image data"):
        validate_image_path(str(fake))


# ---------------------------------------------------------------------------
# inspect_image handler tests (via build_registry closure)
# ---------------------------------------------------------------------------


class _StubVisionProvider(VisionProvider):
    """Deterministic vision provider for testing the tool handler."""

    def __init__(self, answer: str = "A test image with a red circle."):
        self._answer = answer

    async def analyze(self, image_path, prompt, *, model=None, max_output_tokens=None):
        return VisionResult(
            provider="stub",
            model="stub-vision",
            image_path=str(image_path),
            prompt=prompt,
            answer=self._answer,
        )

    async def stream_analyze(self, image_path, prompt, *, model=None, max_output_tokens=None):
        if False:
            yield ""


def _stub_vision_manager(answer: str = "A test image with a red circle.") -> VisionManager:
    return VisionManager(VisionRouter(_StubVisionProvider(answer), model="stub-vision"))


@pytest.mark.asyncio
async def test_inspect_image_returns_structured_result(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")

    result = await tool.handler(image_path=str(image), question="What is this?")

    assert result["image_path"] == str(image.resolve())
    assert result["observation"] == "A test image with a red circle."
    assert result["model"] == "stub-vision"
    assert result["provider"] == "stub"


@pytest.mark.asyncio
async def test_inspect_image_uses_default_prompt_when_question_empty(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")

    result = await tool.handler(image_path=str(image), question="")

    assert "observation" in result
    assert result["observation"] == "A test image with a red circle."


@pytest.mark.asyncio
async def test_inspect_image_uses_default_prompt_when_question_omitted(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")

    result = await tool.handler(image_path=str(image))

    assert "observation" in result


@pytest.mark.asyncio
async def test_inspect_image_rejects_missing_file(tmp_path: Path) -> None:
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")

    with pytest.raises(FileNotFoundError, match="Image file not found"):
        await tool.handler(image_path=str(tmp_path / "missing.png"))


@pytest.mark.asyncio
async def test_inspect_image_rejects_unsupported_extension(tmp_path: Path) -> None:
    text_file = tmp_path / "secret.db"
    text_file.write_bytes(b"sqlite data")
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")

    with pytest.raises(ValueError, match="Unsupported image type"):
        await tool.handler(image_path=str(text_file))


@pytest.mark.asyncio
async def test_inspect_image_rejects_non_image_content(tmp_path: Path) -> None:
    """The tool must reject a file with a valid image extension but invalid content."""
    fake = tmp_path / "fake.png"
    fake.write_text("not image data", encoding="utf-8")
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")

    with pytest.raises(ValueError, match="does not contain valid image data"):
        await tool.handler(image_path=str(fake))


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


def test_inspect_image_registered_with_read_risk() -> None:
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")

    assert tool.risk == Risk.READ
    assert tool.name == "inspect_image"


def test_inspect_image_not_registered_when_no_vision() -> None:
    registry = build_registry(vision=None)

    with pytest.raises(KeyError, match="Unknown tool: inspect_image"):
        registry.get("inspect_image")


def test_build_registry_without_vision_has_three_tools() -> None:
    registry = build_registry(vision=None)

    assert len(registry.list()) == 3


def test_build_registry_with_vision_has_four_tools() -> None:
    registry = build_registry(vision=_stub_vision_manager())

    assert len(registry.list()) == 4
    names = {tool.name for tool in registry.list()}
    assert names == {"get_system_info", "list_directory", "read_text_file", "inspect_image"}


def test_permission_manager_allows_inspect_image() -> None:
    from app.core.permissions import PermissionManager

    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")
    permissions = PermissionManager()

    assert permissions.allowed(tool) is True


def test_inspect_image_schema_has_required_image_path() -> None:
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")
    schema = tool.schema()

    params = schema["function"]["parameters"]
    assert "image_path" in params["properties"]
    assert "question" in params["properties"]
    assert params["required"] == ["image_path"]


def test_tool_description_matches_policy() -> None:
    """The tool description must not encourage autonomous image inspection."""
    registry = build_registry(vision=_stub_vision_manager())
    tool = registry.get("inspect_image")
    desc = tool.description

    assert "ONLY" in desc
    assert "explicitly provides" in desc
    assert "Do not guess" in desc


# ---------------------------------------------------------------------------
# Schema gating tests (_tool_schemas exposes inspect_image only when a local
# image file path appears in the user's message)
# ---------------------------------------------------------------------------


def _make_orchestrator():
    """Create an Orchestrator with the vision tool registered."""
    from app.core.orchestrator import Orchestrator
    from app.core.permissions import PermissionManager
    from app.memory.sqlite_memory import SQLiteMemory

    registry = build_registry(vision=_stub_vision_manager())
    return Orchestrator(registry, PermissionManager(), SQLiteMemory(":memory:"))


def _schema_names(orchestrator, user_text: str) -> set[str]:
    return {s["function"]["name"] for s in orchestrator._tool_schemas(user_text)}


def test_schema_includes_vision_for_windows_path() -> None:
    """A Windows-style image path should surface the vision tool."""
    names = _schema_names(_make_orchestrator(), r"Look at C:\Users\chitz\photo.png")
    assert "inspect_image" in names


def test_schema_includes_vision_for_forward_slash_windows_path() -> None:
    names = _schema_names(_make_orchestrator(), "Check D:/images/test.jpg")
    assert "inspect_image" in names


def test_schema_includes_vision_for_unix_path() -> None:
    names = _schema_names(_make_orchestrator(), "Describe /home/user/shot.jpeg")
    assert "inspect_image" in names


def test_schema_includes_vision_for_unc_path() -> None:
    names = _schema_names(_make_orchestrator(), r"Analyze \\server\share\img.webp")
    assert "inspect_image" in names


def test_schema_includes_vision_for_home_relative_path() -> None:
    names = _schema_names(_make_orchestrator(), "What is in ~/Desktop/pic.png")
    assert "inspect_image" in names


def test_schema_includes_vision_case_insensitive() -> None:
    names = _schema_names(_make_orchestrator(), r"Open C:\DATA\RESULT.PNG")
    assert "inspect_image" in names


def test_schema_excludes_vision_for_unrelated_query() -> None:
    """inspect_image must NOT appear for a generic text question."""
    names = _schema_names(_make_orchestrator(), "What is the capital of France?")
    assert "inspect_image" not in names
    assert "get_system_info" in names  # Other tools still present


def test_schema_excludes_vision_for_bare_image_word() -> None:
    """Saying 'image' or 'screenshot' without a path must NOT expose the tool."""
    orch = _make_orchestrator()
    for msg in (
        "Can you help with this image?",
        "I took a screenshot",
        "Edit my photo please",
        "What is in the picture?",
    ):
        names = _schema_names(orch, msg)
        assert "inspect_image" not in names, f"Tool leaked for: {msg!r}"


def test_schema_excludes_vision_for_bare_extension() -> None:
    """A bare '.png' without a path prefix must NOT expose the tool."""
    names = _schema_names(_make_orchestrator(), "Can you check the file test.png on my desktop?")
    assert "inspect_image" not in names


def test_schema_excludes_vision_for_url_like_extension() -> None:
    """A web URL ending in .png is not a local path."""
    names = _schema_names(_make_orchestrator(), "Download https://example.com/logo.png")
    assert "inspect_image" not in names

