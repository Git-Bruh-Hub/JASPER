from __future__ import annotations

import logging
import subprocess
import tempfile
import wave
from pathlib import Path

from app.voice.base import TextToSpeechProvider


class WindowsSpeechTTS(TextToSpeechProvider):
    """Windows built-in speech synthesis; no neural voice model is required."""

    def __init__(self, *, voice: str | None = None, rate: int = 0, volume: int = 100) -> None:
        self.voice = voice
        self.rate = int(rate)
        self.volume = max(0, min(100, int(volume)))

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        escaped = text.replace("'", "''")
        voice_line = f"$s.SelectVoice('{self.voice.replace(chr(39), chr(39)*2)}');" if self.voice else ""
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate={self.rate}; $s.Volume={self.volume}; "
            f"{voice_line}"
            f"$s.Speak('{escaped}'); $s.Dispose()"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Windows speech synthesis failed.")


class PiperTTS(TextToSpeechProvider):
    """Local neural speech synthesis using the Piper Python API."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        config_path: str | Path | None = None,
        use_cuda: bool = False,
        length_scale: float = 1.0,
    ) -> None:
        self.model_path = Path(model_path)
        self.config_path = Path(config_path) if config_path else None
        self.use_cuda = use_cuda
        self.length_scale = float(length_scale)
        self._voice = None
        self.log = logging.getLogger("jasper.voice.tts")

    def _load_voice(self):
        if self._voice is not None:
            return self._voice
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Piper voice model not found: {self.model_path}. "
                "Download a compatible .onnx voice model and set JASPER_PIPER_MODEL."
            )
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise RuntimeError(
                "Piper TTS is not installed. Install with: pip install piper-tts"
            ) from exc

        kwargs = {"use_cuda": self.use_cuda}
        if self.config_path:
            kwargs["config_path"] = str(self.config_path)
        try:
            self._voice = PiperVoice.load(str(self.model_path), **kwargs)
        except Exception as exc:
            raise RuntimeError(f"Could not load Piper voice: {exc}") from exc
        return self._voice

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        try:
            import sounddevice as sd
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError(
                "Piper playback requires sounddevice and soundfile. "
                "Install with: pip install -r requirements-voice.txt"
            ) from exc

        voice = self._load_voice()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
            wav_path = Path(temp.name)
        try:
            with wave.open(str(wav_path), "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
            audio, sample_rate = sf.read(str(wav_path), dtype="float32")
            sd.play(audio, sample_rate)
            sd.wait()
            self.log.info("Piper TTS completed chars=%s", len(text))
        finally:
            wav_path.unlink(missing_ok=True)
