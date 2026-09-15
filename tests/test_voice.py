import asyncio
from pathlib import Path

from app.voice.base import SpeechToTextProvider, TextToSpeechProvider
from app.voice.manager import VoiceManager


class FakeSTT(SpeechToTextProvider):
    def transcribe(self, audio_path: Path) -> str:
        assert audio_path.exists()
        return "hello jasper"


class FakeTTS(TextToSpeechProvider):
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


def _patch_record(monkeypatch, audio_file: Path):
    monkeypatch.setattr(
        "app.voice.manager.record_until_silence",
        lambda *args, **kwargs: audio_file,
    )


def test_voice_manager_uses_provider_interfaces(tmp_path, monkeypatch):
    tts = FakeTTS()
    manager = VoiceManager(FakeSTT(), tts, temp_dir=tmp_path)
    audio_file = tmp_path / "recorded.wav"
    audio_file.write_bytes(b"fake audio")
    _patch_record(monkeypatch, audio_file)

    assert manager.listen_once() == "hello jasper"
    manager.speak("hello from jasper")
    assert tts.spoken == ["hello from jasper"]


def test_voice_manager_run_once(tmp_path, monkeypatch):
    tts = FakeTTS()
    manager = VoiceManager(FakeSTT(), tts, temp_dir=tmp_path)
    audio_file = tmp_path / "recorded.wav"
    audio_file.write_bytes(b"fake audio")
    _patch_record(monkeypatch, audio_file)

    async def responder(text: str) -> str:
        assert text == "hello jasper"
        return "Hello back."

    user_text, answer = asyncio.run(manager.run_once(responder))
    assert user_text == "hello jasper"
    assert answer == "Hello back."
    assert tts.spoken == ["Hello back."]
