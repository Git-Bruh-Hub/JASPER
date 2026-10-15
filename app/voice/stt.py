from __future__ import annotations

import logging
import os
import site
import sys
from pathlib import Path

from app.voice.base import SpeechToTextProvider


_CUDA_DLL_HANDLES: list[object] = []
_CUDA_CONFIGURED: bool = False
_CUDA_BIN_DIRS: list[Path] = []


def _configure_cuda_runtime() -> list[Path]:
    """Make CUDA runtime DLLs in the Python environment discoverable on Windows.

    The current faster-whisper/CTranslate2 Windows GPU stack may rely on NVIDIA
    runtime wheels rather than a system-wide CUDA Toolkit installation. Windows
    native DLL loading does not automatically search those package directories,
    so JASPER configures them for its own process before importing
    faster-whisper. No global Windows PATH changes are made.
    """
    global _CUDA_CONFIGURED
    if _CUDA_CONFIGURED:
        return _CUDA_BIN_DIRS

    if os.name != "nt":
        _CUDA_CONFIGURED = True
        return []

    roots: list[Path] = []
    try:
        roots.extend(Path(p) for p in site.getsitepackages())
    except Exception:
        pass

    roots.append(Path(sys.prefix) / "Lib" / "site-packages")

    bin_dirs: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for relative in (
            Path("nvidia") / "cublas" / "bin",
            Path("nvidia") / "cudnn" / "bin",
            Path("nvidia") / "cuda_runtime" / "bin",
        ):
            directory = (root / relative).resolve()
            if directory in seen or not directory.is_dir():
                continue
            seen.add(directory)
            bin_dirs.append(directory)

    if not bin_dirs:
        _CUDA_CONFIGURED = True
        return []

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        for directory in bin_dirs:
            try:
                _CUDA_DLL_HANDLES.append(add_dll_directory(str(directory)))
            except OSError:
                pass

    current_path = os.environ.get("PATH", "")
    path_entries = current_path.split(os.pathsep) if current_path else []
    normalized = {os.path.normcase(os.path.normpath(entry)) for entry in path_entries}
    new_entries = [
        str(directory)
        for directory in bin_dirs
        if os.path.normcase(os.path.normpath(str(directory))) not in normalized
    ]
    if new_entries:
        os.environ["PATH"] = os.pathsep.join(new_entries + path_entries)

    # Explicitly preload the exact runtime DLLs required for CTranslate2 inference.
    # PySide6 restricts standard DLL search paths (via SetDefaultDllDirectories),
    # which causes bare LoadLibraryA calls in CTranslate2 to ignore both PATH and
    # os.add_dll_directory. Forcing these DLLs into the process module table
    # guarantees they are instantly resolvable when CTranslate2 requests them.
    target_dlls = {"cublas64_12.dll", "cudnn64_9.dll", "cudart64_12.dll"}
    log = logging.getLogger("jasper.voice.stt")
    import ctypes

    for directory in bin_dirs:
        for dll_name in target_dlls:
            dll_path = directory / dll_name
            if dll_path.is_file():
                try:
                    # Retain the loaded CDLL handle at the module level to ensure
                    # it stays alive in the process.
                    handle = ctypes.CDLL(str(dll_path))
                    _CUDA_DLL_HANDLES.append(handle)
                    log.debug("Preloaded CUDA runtime DLL: %s", dll_name)
                except OSError as exc:
                    log.warning("Failed to preload available CUDA DLL %s: %s", dll_name, exc)
                except Exception as exc:
                    log.error("Unexpected error preloading CUDA DLL %s: %s", dll_name, exc)

    _CUDA_BIN_DIRS.extend(bin_dirs)
    _CUDA_CONFIGURED = True
    return bin_dirs


def _normalize_language(language: str) -> str | None:
    value = language.strip().lower()
    if not value or value == "auto":
        return None
    aliases = {
        "bm": "ms",
        "bahasa melayu": "ms",
        "bahasa malaysia": "ms",
        "malay": "ms",
        "ms-my": "ms",
    }
    return aliases.get(value, value)


class FasterWhisperSTT(SpeechToTextProvider):
    """Local speech recognition using faster-whisper with lazy model loading."""

    def __init__(
        self,
        model_name: str = "small",
        *,
        device: str = "auto",
        gpu_compute_type: str = "int8_float16",
        cpu_compute_type: str = "int8",
        language: str = "auto",
        beam_size: int = 5,
        initial_prompt: str = "",
    ) -> None:
        self.model_name = model_name
        self.device = device.lower()
        self.gpu_compute_type = gpu_compute_type
        self.cpu_compute_type = cpu_compute_type
        self.language = _normalize_language(language)
        self.beam_size = max(1, int(beam_size))
        self.initial_prompt = initial_prompt.strip()
        self._model = None
        self._device = None
        self.log = logging.getLogger("jasper.voice.stt")

    def _load_model(self) -> None:
        if self._model is not None:
            return

        cuda_dirs = _configure_cuda_runtime()
        if cuda_dirs:
            self.log.debug("Configured local CUDA DLL directories: %s", cuda_dirs)

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Speech recognition requires faster-whisper. "
                "Install with: pip install -r requirements-voice.txt"
            ) from exc

        if self.device in {"auto", "cuda", "gpu"}:
            try:
                self._model = WhisperModel(
                    self.model_name,
                    device="cuda",
                    compute_type=self.gpu_compute_type,
                )
                self._device = "cuda"
                self.log.info("Loaded STT model=%s device=cuda", self.model_name)
                return
            except Exception as exc:
                if self.device in {"cuda", "gpu"}:
                    raise RuntimeError(
                        f"CUDA speech recognition could not start: {exc}"
                    ) from exc
                self.log.warning("CUDA STT unavailable; falling back to CPU: %s", exc)

        try:
            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type=self.cpu_compute_type,
            )
            self._device = "cpu"
            self.log.info("Loaded STT model=%s device=cpu", self.model_name)
        except Exception as exc:
            raise RuntimeError(f"Could not load STT model '{self.model_name}': {exc}") from exc

    def transcribe(self, audio_path: Path) -> str:
        self._load_model()
        if not audio_path.exists():
            return ""

        kwargs = {
            "language": self.language,
            "beam_size": self.beam_size,
            "vad_filter": True,
            "condition_on_previous_text": False,
        }
        if self.initial_prompt:
            kwargs["initial_prompt"] = self.initial_prompt

        segments, _info = self._model.transcribe(str(audio_path), **kwargs)

        NO_SPEECH_THRESHOLD = 0.6
        LOGPROB_THRESHOLD = -1.0

        accepted_segments = []
        for segment in segments:
            if segment.no_speech_prob > NO_SPEECH_THRESHOLD and segment.avg_logprob < LOGPROB_THRESHOLD:
                self.log.debug(
                    "Rejected segment: text='%s' no_speech_prob=%.3f avg_logprob=%.3f",
                    segment.text.strip(), segment.no_speech_prob, segment.avg_logprob
                )
                continue

            self.log.debug(
                "Accepted segment: text='%s' no_speech_prob=%.3f avg_logprob=%.3f",
                segment.text.strip(), segment.no_speech_prob, segment.avg_logprob
            )
            accepted_segments.append(segment)

        text = " ".join(segment.text.strip() for segment in accepted_segments).strip()
        if not text:
            return ""
        self.log.info(
            "STT transcription completed device=%s segments=%d chars=%s",
            self._device, len(accepted_segments), len(text)
        )
        return text
