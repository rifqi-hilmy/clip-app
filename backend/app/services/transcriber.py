"""Speech-to-text with faster-whisper (CPU, int8) producing word-level timestamps."""
from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo"]

_model_lock = threading.Lock()
_model_cache: dict[str, Any] = {}


def _get_model(name: str):
    from faster_whisper import WhisperModel  # heavy import, keep lazy

    with _model_lock:
        if name not in _model_cache:
            _model_cache.clear()  # keep only one model in RAM
            _model_cache[name] = WhisperModel(
                name, device="cpu", compute_type="int8", cpu_threads=max(1, (os.cpu_count() or 4) - 1)
            )
        return _model_cache[name]


def extract_audio(source: Path, target: Path) -> Path:
    if target.exists() and target.stat().st_size > 0:
        return target
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)],
        check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return target


def transcript_path(video_dir: Path) -> Path:
    return video_dir / "transcript.json"


def load_transcript(video_dir: Path) -> dict[str, Any] | None:
    p = transcript_path(video_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _load_wav(path: Path):
    """16 kHz mono PCM16 WAV -> float32 numpy array in [-1, 1]."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(
    source: Path,
    video_dir: Path,
    *,
    model: str = "small",
    language: str | None = None,
    on_progress: Callable[[float, str], None],
) -> dict[str, Any]:
    on_progress(0.01, "Mengekstrak audio")
    audio = extract_audio(source, video_dir / "audio.wav")

    on_progress(0.03, f"Memuat model Whisper '{model}' (unduh sekali di awal)")
    whisper = _get_model(model)

    # Pass decoded samples (not a path): faster-whisper's own PyAV-based decoder
    # breaks with recent PyAV releases, and we already have a clean 16 kHz WAV.
    segments_iter, info = whisper.transcribe(
        _load_wav(audio),
        language=language or None,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=5,
        condition_on_previous_text=False,  # reduces repetition loops on long audio
    )
    total = info.duration or 1.0
    lang = info.language
    on_progress(0.05, f"Transkripsi ({lang})")

    segments: list[dict[str, Any]] = []
    for seg in segments_iter:
        words = [
            {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
            for w in (seg.words or [])
        ]
        segments.append({
            "id": len(segments),
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words,
        })
        frac = 0.05 + 0.94 * min(seg.end / total, 1.0)
        on_progress(frac, f"Transkripsi {seg.end / total * 100:.0f}% ({lang})")

    data = {
        "language": lang,
        "language_probability": round(info.language_probability, 3),
        "model": model,
        "duration": total,
        "segments": segments,
    }
    transcript_path(video_dir).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
