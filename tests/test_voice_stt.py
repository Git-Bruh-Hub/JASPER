import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.voice import stt


@pytest.fixture(autouse=True)
def reset_cuda_config():
    """Ensure each test starts with a clean configuration state."""
    # Save original state
    orig_configured = stt._CUDA_CONFIGURED
    orig_handles = list(stt._CUDA_DLL_HANDLES)
    orig_dirs = list(stt._CUDA_BIN_DIRS)
    orig_path = os.environ.get("PATH", "")

    # Reset
    stt._CUDA_CONFIGURED = False
    stt._CUDA_DLL_HANDLES.clear()
    stt._CUDA_BIN_DIRS.clear()

    yield

    # Restore original state
    stt._CUDA_CONFIGURED = orig_configured
    stt._CUDA_DLL_HANDLES[:] = orig_handles
    stt._CUDA_BIN_DIRS[:] = orig_dirs
    os.environ["PATH"] = orig_path


def test_configure_cuda_runtime_locates_nvidia_dirs(monkeypatch):
    """Verify that _configure_cuda_runtime finds NVIDIA package bin directories."""
    # Pretend we are on Windows
    monkeypatch.setattr(os, "name", "nt")

    # Mock site.getsitepackages to return a controlled path
    mock_site = Path("C:/mock/env/Lib/site-packages")
    monkeypatch.setattr("site.getsitepackages", lambda: [str(mock_site)])
    monkeypatch.setattr(sys, "prefix", "C:/mock/sys")

    # Mock is_dir to return True only for our expected dirs
    expected_dirs = {
        (mock_site / "nvidia/cublas/bin").resolve(),
        (mock_site / "nvidia/cudnn/bin").resolve(),
        (mock_site / "nvidia/cuda_runtime/bin").resolve(),
    }
    original_is_dir = Path.is_dir

    def mock_is_dir(self):
        if self.resolve() in expected_dirs:
            return True
        return False

    monkeypatch.setattr(Path, "is_dir", mock_is_dir)

    # Mock the DLL file existence check to return False so we don't actually try to load fake DLLs
    monkeypatch.setattr(Path, "is_file", lambda self: False)

    # Also mock add_dll_directory
    mock_add_dll = MagicMock(return_value="fake_handle")
    monkeypatch.setattr(os, "add_dll_directory", mock_add_dll, raising=False)

    dirs = stt._configure_cuda_runtime()

    assert len(dirs) == 3
    assert set(dirs) == expected_dirs
    assert stt._CUDA_CONFIGURED is True
    assert stt._CUDA_BIN_DIRS == dirs

    # Verify PATH was updated
    current_path = os.environ.get("PATH", "")
    for d in expected_dirs:
        assert str(d) in current_path


def test_configure_cuda_runtime_is_idempotent(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")

    # Set up state as if it was already configured
    mock_dirs = [Path("C:/already_configured")]
    stt._CUDA_CONFIGURED = True
    stt._CUDA_BIN_DIRS.extend(mock_dirs)

    # Run again
    dirs = stt._configure_cuda_runtime()

    # Should immediately return the cached dirs without doing anything
    assert dirs == mock_dirs


def test_configure_cuda_runtime_preloads_target_dlls(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "nt")

    # Create fake nvidia directories with DLL files
    site_packages = tmp_path / "Lib" / "site-packages"
    cublas_bin = site_packages / "nvidia" / "cublas" / "bin"
    cublas_bin.mkdir(parents=True)

    # Create a target DLL that should be loaded
    target_dll = cublas_bin / "cublas64_12.dll"
    target_dll.touch()

    # Create a non-target DLL that should NOT be explicitly preloaded
    other_dll = cublas_bin / "other.dll"
    other_dll.touch()

    monkeypatch.setattr("site.getsitepackages", lambda: [str(site_packages)])
    monkeypatch.setattr(sys, "prefix", str(tmp_path))

    loaded_dlls = []

    class MockCDLL:
        def __init__(self, path):
            loaded_dlls.append(path)
            self.path = path

    import ctypes
    monkeypatch.setattr(ctypes, "CDLL", MockCDLL)

    # We also need to mock add_dll_directory if it exists, to avoid crashing on the fake dir
    mock_add_dll = MagicMock(return_value="dir_handle")
    if hasattr(os, "add_dll_directory"):
        monkeypatch.setattr(os, "add_dll_directory", mock_add_dll)

    dirs = stt._configure_cuda_runtime()

    assert len(dirs) == 1
    assert dirs[0].resolve() == cublas_bin.resolve()

    # Ensure ONLY the target DLL was preloaded via CDLL, not the other one
    assert len(loaded_dlls) == 1
    assert loaded_dlls[0] == str(target_dll)

    # Ensure handle was kept alive
    assert any(isinstance(h, MockCDLL) for h in stt._CUDA_DLL_HANDLES)


def test_configure_cuda_runtime_handles_dll_load_failure(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(os, "name", "nt")

    site_packages = tmp_path / "Lib" / "site-packages"
    cudnn_bin = site_packages / "nvidia" / "cudnn" / "bin"
    cudnn_bin.mkdir(parents=True)

    target_dll = cudnn_bin / "cudnn64_9.dll"
    target_dll.touch()

    monkeypatch.setattr("site.getsitepackages", lambda: [str(site_packages)])
    monkeypatch.setattr(sys, "prefix", str(tmp_path))

    def mock_cdll(path):
        raise OSError(f"Cannot load {path}")

    import ctypes
    monkeypatch.setattr(ctypes, "CDLL", mock_cdll)

    if hasattr(os, "add_dll_directory"):
        monkeypatch.setattr(os, "add_dll_directory", MagicMock())

    import logging
    caplog.set_level(logging.WARNING, logger="jasper.voice.stt")

    dirs = stt._configure_cuda_runtime()

    # The function should succeed without crashing, returning the dirs
    assert len(dirs) == 1

    # We expect a warning in the logs
    assert "Failed to preload available CUDA DLL cudnn64_9.dll" in caplog.text


def test_faster_whisper_stt_preserves_cpu_fallback(monkeypatch, caplog):
    """Verify that if WhisperModel initialization fails for CUDA, it falls back to CPU."""
    class MockWhisperModel:
        def __init__(self, model_size_or_path, device, compute_type):
            if device == "cuda":
                raise RuntimeError("CUDA initialization failed")
            elif device == "cpu":
                self.device = "cpu"

    import faster_whisper
    monkeypatch.setattr(faster_whisper, "WhisperModel", MockWhisperModel)

    # Mock the configure function so we don't mess with real paths
    monkeypatch.setattr(stt, "_configure_cuda_runtime", lambda: [Path("fake")])

    import logging
    caplog.set_level(logging.WARNING, logger="jasper.voice.stt")

    # Initializing with device "auto" should attempt cuda, fail, and fallback to CPU
    provider = stt.FasterWhisperSTT(device="auto")
    provider._load_model()

    assert provider._model is not None
    assert getattr(provider._model, "device", None) == "cpu"
    assert "CUDA STT unavailable; falling back to CPU: CUDA initialization failed" in caplog.text


from dataclasses import dataclass

@dataclass
class FakeSegment:
    text: str
    no_speech_prob: float
    avg_logprob: float

class FakeWhisperModel:
    def __init__(self, segments):
        self.segments = segments
        self.last_kwargs = None

    def transcribe(self, audio_path, **kwargs):
        self.last_kwargs = kwargs
        return self.segments, None


def test_stt_transcribe_missing_file(tmp_path):
    provider = stt.FasterWhisperSTT()
    provider._model = FakeWhisperModel([])
    assert provider.transcribe(tmp_path / "missing.wav") == ""


def test_stt_transcribe_accepts_high_confidence(tmp_path):
    provider = stt.FasterWhisperSTT()
    provider._model = FakeWhisperModel([
        FakeSegment("hello", no_speech_prob=0.1, avg_logprob=-0.5)
    ])

    fake_audio = tmp_path / "audio.wav"
    fake_audio.touch()

    assert provider.transcribe(fake_audio) == "hello"
    assert provider._model.last_kwargs["condition_on_previous_text"] is False
    assert provider._model.last_kwargs["vad_filter"] is True
    assert provider._model.last_kwargs["language"] is None


def test_stt_transcribe_explicit_language(tmp_path):
    provider = stt.FasterWhisperSTT(language="ms")
    provider._model = FakeWhisperModel([
        FakeSegment("hello", no_speech_prob=0.1, avg_logprob=-0.5)
    ])

    fake_audio = tmp_path / "audio.wav"
    fake_audio.touch()

    provider.transcribe(fake_audio)
    assert provider._model.last_kwargs["language"] == "ms"


def test_stt_transcribe_rejects_hallucination(tmp_path, caplog):
    import logging
    caplog.set_level(logging.DEBUG, logger="jasper.voice.stt")

    provider = stt.FasterWhisperSTT()
    provider._model = FakeWhisperModel([
        FakeSegment("noise hallucination", no_speech_prob=0.8, avg_logprob=-1.2)
    ])

    fake_audio = tmp_path / "audio.wav"
    fake_audio.touch()

    assert provider.transcribe(fake_audio) == ""
    assert "Rejected segment" in caplog.text


def test_stt_transcribe_mixed_segments(tmp_path, caplog):
    provider = stt.FasterWhisperSTT()
    provider._model = FakeWhisperModel([
        FakeSegment("valid", no_speech_prob=0.1, avg_logprob=-0.5),
        FakeSegment("hallucination", no_speech_prob=0.9, avg_logprob=-1.5),
        FakeSegment("also valid", no_speech_prob=0.2, avg_logprob=-0.8),
    ])

    fake_audio = tmp_path / "audio.wav"
    fake_audio.touch()

    assert provider.transcribe(fake_audio) == "valid also valid"
