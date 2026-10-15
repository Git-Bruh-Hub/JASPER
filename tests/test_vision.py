from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.vision.image import load_image
from app.vision.ollama_provider import OllamaVisionProvider
from app.vision.base import VisionProvider, VisionResult
from app.vision.manager import VisionManager
from app.vision.router import VisionRouter


# Valid 1x1 PNG used only for deterministic local tests.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_load_image_encodes_supported_png(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)

    loaded = load_image(image)

    assert loaded.path == image.resolve()
    assert loaded.media_type == "image/png"
    assert base64.b64decode(loaded.base64_data) == PNG_BYTES


def test_load_image_rejects_unsupported_type(tmp_path: Path) -> None:
    image = tmp_path / "test.txt"
    image.write_text("not an image", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported image type"):
        load_image(image)


def test_load_image_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Image file not found"):
        load_image(tmp_path / "missing.png")


def test_ollama_payload_contains_image_and_prompt(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(PNG_BYTES)
    provider = OllamaVisionProvider()

    payload = provider._payload(image, "What is this?", model="qwen3-vl:8b", stream=False, max_output_tokens=256)

    message = payload["messages"][0]
    assert payload["model"] == "qwen3-vl:8b"
    assert message["content"] == "What is this?"
    assert len(message["images"]) == 1
    assert base64.b64decode(message["images"][0]) == PNG_BYTES


def test_router_uses_configured_model() -> None:
    class DummyVision(VisionProvider):
        async def analyze(self, image_path, prompt, *, model=None, max_output_tokens=None):
            raise AssertionError("not called in this routing test")

        async def stream_analyze(self, image_path, prompt, *, model=None, max_output_tokens=None):
            if False:
                yield ""

    router = VisionRouter(DummyVision(), model="test-vision-model")
    assert router.model == "test-vision-model"


def test_provider_payload_uses_multimodal_chat_shape(tmp_path: Path) -> None:
    image = tmp_path / "test.webp"
    image.write_bytes(b"webp-placeholder")
    provider = OllamaVisionProvider()

    payload = provider._payload(image, "Describe it", model="qwen3-vl:8b", stream=True, max_output_tokens=128)

    assert payload["stream"] is True
    assert payload["messages"][0]["role"] == "user"
    assert isinstance(payload["messages"][0]["images"][0], str)


class _SequenceVision(VisionProvider):
    def __init__(self, responses: list[VisionResult | Exception]):
        self.responses = iter(responses)
        self.calls = 0

    async def analyze(self, image_path, prompt, *, model=None, max_output_tokens=None):
        self.calls += 1
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result

    async def stream_analyze(self, image_path, prompt, *, model=None, max_output_tokens=None):
        if False:
            yield ""


def _vision_result() -> VisionResult:
    return VisionResult(
        provider="test",
        model="test-model",
        image_path="test.png",
        prompt="test",
        answer="The image contains a test object.",
    )


@pytest.mark.asyncio
async def test_manager_retries_empty_provider_response_once(tmp_path: Path) -> None:
    provider = _SequenceVision([
        RuntimeError("Vision model returned an empty response."),
        _vision_result(),
    ])
    manager = VisionManager(VisionRouter(provider), empty_response_retries=1)

    result = await manager.analyze(tmp_path / "test.png", "What is this?")

    assert result.answer == "The image contains a test object."
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_manager_does_not_retry_non_empty_response_errors(tmp_path: Path) -> None:
    provider = _SequenceVision([RuntimeError("HTTP 500")])
    manager = VisionManager(VisionRouter(provider), empty_response_retries=1)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        await manager.analyze(tmp_path / "test.png", "What is this?")

    assert provider.calls == 1


@pytest.mark.asyncio
async def test_manager_reports_empty_after_retry_budget(tmp_path: Path) -> None:
    provider = _SequenceVision([
        RuntimeError("Vision model returned an empty response."),
        RuntimeError("Vision model returned an empty response."),
    ])
    manager = VisionManager(VisionRouter(provider), empty_response_retries=1)

    with pytest.raises(RuntimeError, match=r"empty response after 2 attempt\(s\)"):
        await manager.analyze(tmp_path / "test.png", "What is this?")

    assert provider.calls == 2
