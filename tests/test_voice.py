import asyncio
from pathlib import Path

from app.voice.base import SpeechToTextProvider, TextToSpeechProvider
from app.voice.manager import VoiceManager
from app.voice.stt import _normalize_language
from app.voice.tts import prepare_speech_text


class FakeSTT(SpeechToTextProvider):
    def __init__(self, text: str = "hello jasper") -> None:
        self.text = text

    def transcribe(self, audio_path: Path) -> str:
        assert audio_path.exists()
        return self.text


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


def test_conversation_preserves_turns_and_stops_on_local_phrase(tmp_path, monkeypatch):
    tts = FakeTTS()
    texts = iter(["hi jasper", "apa khabar", "stop listening"])

    class SequenceSTT(SpeechToTextProvider):
        def transcribe(self, audio_path: Path) -> str:
            return next(texts)

    manager = VoiceManager(SequenceSTT(), tts, temp_dir=tmp_path)
    audio_file = tmp_path / "recorded.wav"
    audio_file.write_bytes(b"fake audio")
    _patch_record(monkeypatch, audio_file)

    async def responder(text: str) -> str:
        return f"reply: {text}"

    turns = asyncio.run(manager.run_conversation(responder, max_turns=5))
    assert turns == [("hi jasper", "reply: hi jasper"), ("apa khabar", "reply: apa khabar")]
    assert tts.spoken == ["reply: hi jasper", "reply: apa khabar"]


def test_conversation_stops_after_repeated_empty_inputs(tmp_path, monkeypatch):
    tts = FakeTTS()
    texts = iter(["", ""])

    class SequenceSTT(SpeechToTextProvider):
        def transcribe(self, audio_path: Path) -> str:
            return next(texts)

    manager = VoiceManager(SequenceSTT(), tts, temp_dir=tmp_path)
    audio_file = tmp_path / "recorded.wav"
    audio_file.write_bytes(b"fake audio")
    _patch_record(monkeypatch, audio_file)

    async def responder(_text: str) -> str:
        raise AssertionError("Responder should not be called for empty speech")

    assert asyncio.run(manager.run_conversation(responder, max_turns=5, empty_limit=2)) == []


def test_language_aliases():
    assert _normalize_language("auto") is None
    assert _normalize_language("BM") == "ms"
    assert _normalize_language("Bahasa Melayu") == "ms"
    assert _normalize_language("malay") == "ms"
    assert _normalize_language("en") == "en"


def test_prepare_speech_text_removes_common_markdown():
    text = "**CPU:** `Ryzen 5 5600X`\n- Ready\n[details](https://example.com)"
    assert prepare_speech_text(text) == "CPU: Ryzen 5 5600X Ready details"
