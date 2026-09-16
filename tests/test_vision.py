from types import SimpleNamespace

import pytest

from app.vision.base import VisionResult
from app.vision.manager import VisionManager


class FakeProvider:
    def __init__(self, results=None, error=None):
        self.results = list(results or [])
        self.error = error
        self.calls = 0

    async def analyze(self, image_path, prompt, *, model=None, max_output_tokens=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.results.pop(0)


def result(answer: str) -> VisionResult:
    return VisionResult(
        provider="fake",
        model="test-model",
        image_path="C:\\test.png",
        prompt="test",
        answer=answer,
    )


@pytest.mark.asyncio
async def test_manager_retries_empty_provider_response_once(tmp_path):
    provider = FakeProvider(results=[result(""), result("recovered")])
    manager = VisionManager(SimpleNamespace(provider=provider, model="test"), empty_response_retries=1)
    image = tmp_path / "test.png"
    image.write_bytes(b"x")

    output = await manager.analyze(image, "describe")

    assert output.answer == "recovered"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_manager_does_not_retry_non_empty_response_errors(tmp_path):
    provider = FakeProvider(error=RuntimeError("provider failure"))
    manager = VisionManager(SimpleNamespace(provider=provider, model="test"), empty_response_retries=1)
    image = tmp_path / "test.png"
    image.write_bytes(b"x")

    with pytest.raises(RuntimeError, match="provider failure"):
        await manager.analyze(image, "describe")

    assert provider.calls == 1


@pytest.mark.asyncio
async def test_manager_reports_empty_after_retry_budget(tmp_path):
    provider = FakeProvider(results=[result(""), result("")])
    manager = VisionManager(SimpleNamespace(provider=provider, model="test"), empty_response_retries=1)
    image = tmp_path / "test.png"
    image.write_bytes(b"x")

    with pytest.raises(RuntimeError, match=r"empty response after 2 attempt\(s\)"):
        await manager.analyze(image, "describe")

    assert provider.calls == 2
