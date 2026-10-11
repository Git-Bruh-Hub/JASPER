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

    async def responder(text: str, *, cancel_callback=None) -> str:
        assert text == "hello jasper"
        return "Hello back."

    user_text, answer = asyncio.run(manager.run_once(responder))
    assert user_text == "hello jasper"
    assert answer == "Hello back."
    assert tts.spoken == ["Hello back."]


def test_stop_detector_accepts_normalized_english_variants():
    accepted = [
        "stop listening",
        "STOP LISTENING!",
        "Please, stop listening.",
        "stop listening please",
        "Okay, stop listening",
        "OK stop listening!!!",
        "goodbye jasper",
        "Goodbye, JASPER!",
        "goodbye jasper please",
        "bye jasper",
    ]
    for text in accepted:
        assert VoiceManager.should_stop_conversation(text)


def test_stop_detector_rejects_ambiguous_or_non_english_phrases():
    rejected = [
        "stop",
        "please stop",
        "we should stop listening to music",
        "I heard you say stop listening",
        "berhenti jasper",
        "berhenti dengar",
        "baiklah berhenti dengar",
        "jangan dengar",
        "bye",
        "jasper",
    ]
    for text in rejected:
        assert not VoiceManager.should_stop_conversation(text)


def test_conversation_preserves_turns_and_stops_on_local_phrase(tmp_path, monkeypatch):
    tts = FakeTTS()
    texts = iter(["hi jasper", "apa khabar", "STOP listening!", "should not run"])

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


def test_record_until_silence_aborts_on_pure_silence(tmp_path, monkeypatch):
    import numpy as np
    from app.voice.audio import record_until_silence

    class MockInputStream:
        def __init__(self, *args, callback=None, **kwargs):
            self.callback = callback

        def __enter__(self):
            silent_block = np.zeros((1024, 1), dtype=np.float32)
            self.callback(silent_block, 1024, None, None)
            return self

        def __exit__(self, *args):
            pass

    import sounddevice as sd
    monkeypatch.setattr(sd, "InputStream", MockInputStream)

    output = tmp_path / "out.wav"
    result = record_until_silence(
        output,
        max_seconds=0.2,
        min_seconds=0.0,
        silence_seconds=0.1,
    )

    assert result is None
    assert not output.exists()


def test_record_until_silence_writes_wav_on_speech(tmp_path, monkeypatch):
    import numpy as np
    from app.voice.audio import record_until_silence

    class MockInputStream:
        def __init__(self, *args, callback=None, **kwargs):
            self.callback = callback

        def __enter__(self):
            loud_block = np.ones((1024, 1), dtype=np.float32)
            self.callback(loud_block, 1024, None, None)
            return self

        def __exit__(self, *args):
            pass

    import sounddevice as sd
    monkeypatch.setattr(sd, "InputStream", MockInputStream)

    output = tmp_path / "out.wav"
    result = record_until_silence(
        output,
        max_seconds=0.2,
        min_seconds=0.0,
        silence_seconds=0.1,
    )

    assert result == output
    assert output.exists()


def test_voice_manager_run_once_cancels_before_tts(tmp_path, monkeypatch):
    tts = FakeTTS()
    manager = VoiceManager(FakeSTT(), tts, temp_dir=tmp_path)
    audio_file = tmp_path / "recorded.wav"
    audio_file.write_bytes(b"fake audio")
    _patch_record(monkeypatch, audio_file)

    cancel_flag = False

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

    async def responder(text: str, *, cancel_callback=None) -> str:
        assert text == "hello jasper"
        return "Hello back."

    user_text, answer = asyncio.run(manager.run_once(responder))
    assert user_text == "hello jasper"
    assert answer == "Hello back."
    assert tts.spoken == ["Hello back."]


def test_stop_detector_accepts_normalized_english_variants():
    accepted = [
        "stop listening",
        "STOP LISTENING!",
        "Please, stop listening.",
        "stop listening please",
        "Okay, stop listening",
        "OK stop listening!!!",
        "goodbye jasper",
        "Goodbye, JASPER!",
        "goodbye jasper please",
        "bye jasper",
    ]
    for text in accepted:
        assert VoiceManager.should_stop_conversation(text)


def test_stop_detector_rejects_ambiguous_or_non_english_phrases():
    rejected = [
        "stop",
        "please stop",
        "we should stop listening to music",
        "I heard you say stop listening",
        "berhenti jasper",
        "berhenti dengar",
        "baiklah berhenti dengar",
        "jangan dengar",
        "bye",
        "jasper",
    ]
    for text in rejected:
        assert not VoiceManager.should_stop_conversation(text)


def test_conversation_preserves_turns_and_stops_on_local_phrase(tmp_path, monkeypatch):
    tts = FakeTTS()
    texts = iter(["hi jasper", "apa khabar", "STOP listening!", "should not run"])

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


def test_record_until_silence_aborts_on_pure_silence(tmp_path, monkeypatch):
    import numpy as np
    from app.voice.audio import record_until_silence

    class MockInputStream:
        def __init__(self, *args, callback=None, **kwargs):
            self.callback = callback

        def __enter__(self):
            silent_block = np.zeros((1024, 1), dtype=np.float32)
            self.callback(silent_block, 1024, None, None)
            return self

        def __exit__(self, *args):
            pass

    import sounddevice as sd
    monkeypatch.setattr(sd, "InputStream", MockInputStream)

    output = tmp_path / "out.wav"
    result = record_until_silence(
        output,
        max_seconds=0.2,
        min_seconds=0.0,
        silence_seconds=0.1,
    )

    assert result is None
    assert not output.exists()


def test_record_until_silence_writes_wav_on_speech(tmp_path, monkeypatch):
    import numpy as np
    from app.voice.audio import record_until_silence

    class MockInputStream:
        def __init__(self, *args, callback=None, **kwargs):
            self.callback = callback

        def __enter__(self):
            loud_block = np.ones((1024, 1), dtype=np.float32)
            self.callback(loud_block, 1024, None, None)
            return self

        def __exit__(self, *args):
            pass

    import sounddevice as sd
    monkeypatch.setattr(sd, "InputStream", MockInputStream)

    output = tmp_path / "out.wav"
    result = record_until_silence(
        output,
        max_seconds=0.2,
        min_seconds=0.0,
        silence_seconds=0.1,
    )

    assert result == output
    assert output.exists()


def test_voice_manager_run_once_cancels_before_tts(tmp_path, monkeypatch):
    tts = FakeTTS()
    manager = VoiceManager(FakeSTT(), tts, temp_dir=tmp_path)
    audio_file = tmp_path / "recorded.wav"
    audio_file.write_bytes(b"fake audio")
    _patch_record(monkeypatch, audio_file)

    cancel_flag = False

    async def responder(text: str, *, cancel_callback=None) -> str:
        nonlocal cancel_flag
        cancel_flag = True
        return "Hello back."

    user_text, answer = asyncio.run(
        manager.run_once(responder, cancel_callback=lambda: cancel_flag)
    )
    assert user_text == "hello jasper"
    assert answer == ""
    assert tts.spoken == []


def test_voice_manager_run_once_handles_tts_cancellation_race(tmp_path, monkeypatch):
    tts_failed = False

    class RacingTTS(TextToSpeechProvider):
        def speak(self, text: str) -> None:
            nonlocal tts_failed
            tts_failed = True
            raise RuntimeError("Windows speech synthesis failed.")

    tts = RacingTTS()
    manager = VoiceManager(FakeSTT(), tts, temp_dir=tmp_path)
    audio_file = tmp_path / "recorded.wav"
    audio_file.write_bytes(b"fake audio")
    _patch_record(monkeypatch, audio_file)

    def cancel_callback():
        return tts_failed

    async def responder(text: str, *, cancel_callback=None) -> str:
        return "Hello back."

    user_text, answer = asyncio.run(
        manager.run_once(responder, cancel_callback=cancel_callback)
    )
    assert user_text == "hello jasper"
    assert answer == ""


def test_voice_manager_run_once_propagates_unrelated_tts_error(tmp_path, monkeypatch):
    class FailingTTS(TextToSpeechProvider):
        def speak(self, text: str) -> None:
            raise RuntimeError("Actual unexpected TTS failure.")

    tts = FailingTTS()
    manager = VoiceManager(FakeSTT(), tts, temp_dir=tmp_path)
    audio_file = tmp_path / "recorded.wav"
    audio_file.write_bytes(b"fake audio")
    _patch_record(monkeypatch, audio_file)

    async def responder(text: str, *, cancel_callback=None) -> str:
        return "Hello back."

    import pytest
    with pytest.raises(RuntimeError, match="Actual unexpected TTS failure."):
        asyncio.run(manager.run_once(responder, cancel_callback=lambda: False))
