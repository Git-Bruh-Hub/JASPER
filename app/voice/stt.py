from __future__ import annotations

import logging
import os
import site
import sys
from pathlib import Path

from app.voice.base import SpeechToTextProvider


_CUDA_DLL_HANDLES: list[object] = []


def _configure_cuda_runtime() -> list[Path]:
    """Make CUDA runtime DLLs in the Python environment discoverable on Windows.

    The current faster-whisper/CTranslate2 Windows GPU stack may rely on NVIDIA
    runtime wheels rather than a system-wide CUDA Toolkit installation. Windows
    native DLL loading does not automatically search those package directories,
    so JASPER configures them for its own process before importing
    faster-whisper. No global Windows PATH changes are made.
    """
    if os.name != "nt":
        return []

    roots: list[Path] = []
    try:
        roots.extend(Path(p) for p in site.getsitepackages())
    except Exception:
        pass

    # sys.prefix covers the active virtual environment even when site metadata
    # is unavailable or has been customized.
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
        return []

    # os.add_dll_directory handles modern Windows DLL search semantics. Keep
    # the returned handles alive for the lifetime of the process.
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        for directory in bin_dirs:
            try:
                _CUDA_DLL_HANDLES.append(add_dll_directory(str(directory)))
            except OSError:
                pass

    # CTranslate2/native CUDA loading can also consult PATH. Modify only the
    # current JASPER process, never the user's persistent Windows environment.
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

    return bin_dirs


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
    ) -> None:
        self.model_name = model_name
        self.device = device.lower()
        self.gpu_compute_type = gpu_compute_type
        self.cpu_compute_type = cpu_compute_type
        self.language = None if language.lower() == "auto" else language
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
            raise FileNotFoundError(audio_path)

        segments, _info = self._model.transcribe(
            str(audio_path),
            language=self.language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            return ""
        self.log.info("STT transcription completed device=%s chars=%s", self._device, len(text))
        return text
