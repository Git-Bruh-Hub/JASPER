"""Tests for the v0.5.2 vision-to-text bridge and Chat-workspace image attachment."""

from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication

from app.core.orchestrator import Orchestrator
from app.core.permissions import PermissionManager
from app.main import build_registry, build_vision_manager
from app.memory.sqlite_memory import SQLiteMemory
from app.vision.base import VisionProvider, VisionResult
from app.vision.manager import VisionManager
from app.vision.router import VisionRouter

# ---------------------------------------------------------------------------
# Minimal valid image bytes (same as in other test modules)
# ---------------------------------------------------------------------------

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
    "BwYIDAoMCwsKCwsNCxAQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQME"
    "BAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
    "FBQUFBQUFBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/"
    "EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAA"
    "AAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AKwA//9k="
)
WEBP_BYTES = base64.b64decode(
    "UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AA/vv9UAA="
)


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------


class _StubVisionProvider(VisionProvider):
    """Vision provider that always returns a canned observation."""

    OBSERVATION = "A test image with a red circle."

    async def analyze(self, image_path, prompt, *, model=None, max_output_tokens=None):
        return VisionResult(
            provider="stub",
            model="stub-model",
            image_path=str(image_path),
            prompt=prompt,
            answer=self.OBSERVATION,
        )


def _stub_vision_manager() -> VisionManager:
    return VisionManager(VisionRouter(_StubVisionProvider()))


def _make_orchestrator(
    vision: VisionManager | None = None, *, tmp_path: Path
) -> Orchestrator:
    """Create an Orchestrator backed by a real file-based SQLiteMemory.

    SQLite in-memory databases (":memory:") are scoped to a single connection
    object, so each new connection opened by SQLiteMemory._connect() sees an
    empty database without the schema.  Using a real file avoids this.
    """
    db = SQLiteMemory(tmp_path / "test.db")
    registry = build_registry(vision)
    return Orchestrator(registry, PermissionManager(), db, vision=vision)


# ---------------------------------------------------------------------------
# Vision bridge — Orchestrator.respond() with image_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_respond_with_image_injects_observation(tmp_path: Path) -> None:
    """When image_path is provided, the vision observation appears in the
    system messages sent to the provider."""
    image = tmp_path / "photo.png"
    image.write_bytes(PNG_BYTES)

    vm = _stub_vision_manager()
    orchestrator = _make_orchestrator(vision=vm, tmp_path=tmp_path)

    captured_messages: list[list[dict]] = []

    async def fake_chat(messages, *, model, tools, max_output_tokens, cancel_callback=None):
        captured_messages.append(messages)
        return {"message": {"role": "assistant", "content": "I see a red circle."}}

    with patch.object(orchestrator.models.local, "chat", side_effect=fake_chat):
        await orchestrator.respond("What is in the image?", image_path=str(image))

    assert captured_messages, "Provider should have been called"
    all_content = " ".join(
        m["content"] for msgs in captured_messages for m in msgs if m.get("role") == "system"
    )
    assert "VISION OBSERVATION" in all_content
    assert _StubVisionProvider.OBSERVATION in all_content


@pytest.mark.asyncio
async def test_respond_without_image_skips_vision(tmp_path: Path) -> None:
    """When no image_path is given, VisionManager is never called."""
    vm = _stub_vision_manager()
    vm.analyze = AsyncMock(wraps=vm.analyze)  # spy
    orchestrator = _make_orchestrator(vision=vm, tmp_path=tmp_path)

    async def fake_chat(messages, *, model, tools, max_output_tokens, cancel_callback=None):
        return {"message": {"role": "assistant", "content": "Hello."}}

    with patch.object(orchestrator.models.local, "chat", side_effect=fake_chat):
        await orchestrator.respond("Hello JASPER")

    vm.analyze.assert_not_called()


@pytest.mark.asyncio
async def test_respond_observation_not_injected_when_no_vision_manager(tmp_path: Path) -> None:
    """Orchestrator with no VisionManager ignores image_path gracefully."""
    orchestrator = _make_orchestrator(vision=None, tmp_path=tmp_path)  # no vision

    captured_messages: list[list[dict]] = []

    async def fake_chat(messages, *, model, tools, max_output_tokens, cancel_callback=None):
        captured_messages.append(messages)
        return {"message": {"role": "assistant", "content": "OK."}}

    with patch.object(orchestrator.models.local, "chat", side_effect=fake_chat):
        await orchestrator.respond("Hello", image_path="/some/nonexistent/photo.png")

    all_content = " ".join(
        m["content"] for msgs in captured_messages for m in msgs if m.get("role") == "system"
    )
    assert "VISION OBSERVATION" not in all_content


@pytest.mark.asyncio
async def test_respond_raises_when_vision_fails(tmp_path: Path) -> None:
    """If VisionManager raises, respond() must propagate the exception.
    The normal text-LLM must NOT be called."""
    image = tmp_path / "photo.png"
    image.write_bytes(PNG_BYTES)

    vm = _stub_vision_manager()
    vm.analyze = AsyncMock(side_effect=RuntimeError("Ollama unavailable"))
    orchestrator = _make_orchestrator(vision=vm, tmp_path=tmp_path)

    llm_called = False

    async def fake_chat(messages, *, model, tools, max_output_tokens, cancel_callback=None):
        nonlocal llm_called
        llm_called = True
        return {"message": {"role": "assistant", "content": "should not reach here"}}

    with patch.object(orchestrator.models.local, "chat", side_effect=fake_chat):
        with pytest.raises(RuntimeError, match="Ollama unavailable"):
            await orchestrator.respond("What is this?", image_path=str(image))

    assert not llm_called, "Text-model must NOT be called when vision analysis fails"


@pytest.mark.asyncio
async def test_respond_raises_for_invalid_image_path(tmp_path: Path) -> None:
    """An invalid path (missing file) must propagate as FileNotFoundError.
    The normal text-LLM must NOT be called."""
    missing = tmp_path / "ghost.png"  # does not exist

    vm = _stub_vision_manager()
    orchestrator = _make_orchestrator(vision=vm, tmp_path=tmp_path)

    llm_called = False

    async def fake_chat(messages, *, model, tools, max_output_tokens, cancel_callback=None):
        nonlocal llm_called
        llm_called = True
        return {"message": {"role": "assistant", "content": "should not reach here"}}

    with patch.object(orchestrator.models.local, "chat", side_effect=fake_chat):
        with pytest.raises(FileNotFoundError):
            await orchestrator.respond("What is this?", image_path=str(missing))

    assert not llm_called, "Text-model must NOT be called when image path is invalid"


@pytest.mark.asyncio
async def test_respond_includes_filename_in_observation_header(tmp_path: Path) -> None:
    """The injected system message should include the image filename so the
    LLM has provenance information."""
    image = tmp_path / "my_screenshot.png"
    image.write_bytes(PNG_BYTES)

    vm = _stub_vision_manager()
    orchestrator = _make_orchestrator(vision=vm, tmp_path=tmp_path)

    captured: list[list[dict]] = []

    async def fake_chat(messages, *, model, tools, max_output_tokens, cancel_callback=None):
        captured.append(messages)
        return {"message": {"role": "assistant", "content": "ok"}}

    with patch.object(orchestrator.models.local, "chat", side_effect=fake_chat):
        await orchestrator.respond("Describe this", image_path=str(image))

    all_content = " ".join(
        m["content"] for msgs in captured for m in msgs if m.get("role") == "system"
    )
    assert "my_screenshot.png" in all_content


# ---------------------------------------------------------------------------
# Orchestrator.__init__ backward compatibility
# ---------------------------------------------------------------------------


def test_orchestrator_init_without_vision_is_backward_compatible() -> None:
    """Existing callers that pass only registry/permissions/memory still work."""
    orchestrator = Orchestrator(build_registry(), PermissionManager(), MagicMock())
    assert orchestrator.vision is None


def test_orchestrator_init_with_vision_stores_it() -> None:
    vm = _stub_vision_manager()
    orchestrator = Orchestrator(build_registry(), PermissionManager(), MagicMock(), vision=vm)
    assert orchestrator.vision is vm


# ---------------------------------------------------------------------------
# Qt-dependent tests (worker slot + MainWindow UI)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# --- Worker slot -----------------------------------------------------------


def test_worker_has_send_text_with_image_slot(qapp) -> None:
    """JasperWorker must expose the send_text_with_image slot."""
    from app.ui.worker import JasperWorker

    worker = JasperWorker()
    assert callable(getattr(worker, "send_text_with_image", None))


# --- MainWindow Chat attachment controls -----------------------------------


def _make_main_window(qapp):
    """Instantiate a MainWindow with a real worker."""
    from PySide6.QtCore import QThread

    from app.ui.main_window import MainWindow
    from app.ui.worker import JasperWorker

    thread = QThread()
    worker = JasperWorker()
    worker.moveToThread(thread)
    thread.start()
    window = MainWindow(worker, thread)
    return window, thread


def test_main_window_has_attach_button(qapp) -> None:
    window, thread = _make_main_window(qapp)
    try:
        assert hasattr(window, "attach_button"), "attach_button widget must exist"
        assert window.attach_button.toolTip() != ""
    finally:
        thread.quit()
        thread.wait(2000)


def test_attachment_chip_hidden_by_default(qapp) -> None:
    window, thread = _make_main_window(qapp)
    try:
        # The chip is hidden() — not just not shown because window isn't visible
        assert window.attachment_chip.isHidden(), "chip must be hidden when no image attached"
        assert window._attached_image_path is None
    finally:
        thread.quit()
        thread.wait(2000)


def test_set_attachment_shows_chip(qapp, tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    image.write_bytes(PNG_BYTES)
    window, thread = _make_main_window(qapp)
    try:
        window._set_attachment(str(image))
        assert window._attached_image_path == str(image)
        # isHidden() is the reliable check when the parent window isn't shown
        assert not window.attachment_chip.isHidden(), "chip must not be hidden after set_attachment"
        assert "sample.png" in window.attachment_label.text()
    finally:
        thread.quit()
        thread.wait(2000)


def test_clear_attachment_hides_chip(qapp, tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    image.write_bytes(PNG_BYTES)
    window, thread = _make_main_window(qapp)
    try:
        window._set_attachment(str(image))
        window._clear_attachment()
        assert window._attached_image_path is None
        assert window.attachment_chip.isHidden()
    finally:
        thread.quit()
        thread.wait(2000)


def test_send_clears_attachment(qapp, tmp_path: Path) -> None:
    """After _send_text() is invoked the attachment should be cleared."""
    image = tmp_path / "sample.png"
    image.write_bytes(PNG_BYTES)
    window, thread = _make_main_window(qapp)
    try:
        window._set_attachment(str(image))
        window.input.setText("What do you see?")
        # Capture the emitted signal
        emitted: list[tuple] = []
        window.request_text_with_image.connect(lambda t, p: emitted.append((t, p)))
        window._send_text()
        # chip cleared after send
        assert window._attached_image_path is None
        assert window.attachment_chip.isHidden()
        # correct signal emitted
        assert emitted, "request_text_with_image must have been emitted"
        assert emitted[0][0] == "What do you see?"
        assert emitted[0][1] == str(image)
    finally:
        thread.quit()
        thread.wait(2000)


def test_send_without_attachment_uses_text_signal(qapp) -> None:
    """When no image is attached, _send_text() uses the plain text signal."""
    window, thread = _make_main_window(qapp)
    try:
        window.input.setText("Hello JASPER")
        text_emitted: list[str] = []
        image_emitted: list[tuple] = []
        window.request_text.connect(lambda t: text_emitted.append(t))
        window.request_text_with_image.connect(lambda t, p: image_emitted.append((t, p)))
        window._send_text()
        assert text_emitted == ["Hello JASPER"]
        assert not image_emitted
    finally:
        thread.quit()
        thread.wait(2000)


# --- _extract_valid_image_path -------------------------------------------
# Test the helper directly with proper QMimeData objects instead of going
# through drop events (which have Qt ownership issues in offscreen tests).


def test_extract_valid_image_path_accepts_png(qapp, tmp_path: Path) -> None:
    image = tmp_path / "photo.png"
    image.write_bytes(PNG_BYTES)
    window, thread = _make_main_window(qapp)
    try:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(image))])
        result = window._extract_valid_image_path(mime)
        assert result is not None
        assert Path(result).name == "photo.png"
    finally:
        thread.quit()
        thread.wait(2000)


def test_extract_valid_image_path_rejects_txt(qapp, tmp_path: Path) -> None:
    doc = tmp_path / "readme.txt"
    doc.write_text("hello")
    window, thread = _make_main_window(qapp)
    try:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(doc))])
        result = window._extract_valid_image_path(mime)
        assert result is None
    finally:
        thread.quit()
        thread.wait(2000)


def test_extract_valid_image_path_rejects_web_url(qapp) -> None:
    """A web URL ending in .png is not a local path and must return None."""
    window, thread = _make_main_window(qapp)
    try:
        mime = QMimeData()
        mime.setUrls([QUrl("https://example.com/logo.png")])
        result = window._extract_valid_image_path(mime)
        assert result is None
    finally:
        thread.quit()
        thread.wait(2000)


def test_extract_valid_image_path_returns_none_for_empty_mime(qapp) -> None:
    window, thread = _make_main_window(qapp)
    try:
        result = window._extract_valid_image_path(None)
        assert result is None
        result2 = window._extract_valid_image_path(QMimeData())  # no URLs set
        assert result2 is None
    finally:
        thread.quit()
        thread.wait(2000)


def test_set_attachment_then_clear_resets_state(qapp, tmp_path: Path) -> None:
    """Full attach → dismiss cycle leaves state clean."""
    image = tmp_path / "photo.jpg"
    image.write_bytes(JPEG_BYTES)
    window, thread = _make_main_window(qapp)
    try:
        window._set_attachment(str(image))
        assert window._attached_image_path is not None
        assert not window.attachment_chip.isHidden()
        window._clear_attachment()
        assert window._attached_image_path is None
        assert window.attachment_chip.isHidden()
        assert window.attachment_label.text() == ""
    finally:
        thread.quit()
        thread.wait(2000)
