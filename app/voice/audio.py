from __future__ import annotations

import time
from pathlib import Path


def record_until_silence(
    output_path: str | Path,
    *,
    max_seconds: float = 8.0,
    sample_rate: int = 16_000,
    silence_seconds: float = 0.9,
    silence_threshold: float = 0.01,
    min_seconds: float = 0.6,
) -> Path:
    """Record microphone input until silence or the maximum duration.

    Audio packages are imported lazily so JASPER can still run in text-only
    mode when voice dependencies are not installed.
    """
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError(
            "Voice recording requires the optional voice dependencies. "
            "Install with: pip install -r requirements-voice.txt"
        ) from exc

    if max_seconds <= 0 or sample_rate <= 0:
        raise ValueError("max_seconds and sample_rate must be positive.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames: list[np.ndarray] = []
    started_at = time.monotonic()
    last_voice_at = started_at

    def callback(indata, _frames, _time_info, status) -> None:
        nonlocal last_voice_at
        if status:
            # Recording can continue through non-fatal device status messages.
            pass
        block = indata.copy()
        frames.append(block)
        rms = float(np.sqrt(np.mean(np.square(block.astype(np.float32)))))
        if rms >= silence_threshold:
            last_voice_at = time.monotonic()

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            callback=callback,
            blocksize=1024,
        ):
            while True:
                now = time.monotonic()
                elapsed = now - started_at
                if elapsed >= max_seconds:
                    break
                if elapsed >= min_seconds and now - last_voice_at >= silence_seconds:
                    break
                time.sleep(0.05)
    except Exception as exc:
        raise RuntimeError(f"Microphone recording failed: {exc}") from exc

    if not frames:
        raise RuntimeError("No microphone audio was captured.")

    audio = np.concatenate(frames, axis=0)
    sf.write(str(output), audio, sample_rate, subtype="PCM_16")
    return output
