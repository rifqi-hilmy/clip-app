"""Silence detection for auto-trimming dead air from clips (Sprint 1/T6)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_START_RE = re.compile(r"silence_start:\s*([\d.]+)")
_END_RE = re.compile(r"silence_end:\s*([\d.]+)")


def detect_silences(source: Path, start: float, end: float,
                    db: float = -35.0, min_dur: float = 0.8) -> list[tuple[float, float]]:
    """Detect silences in [start, end] of the source file.

    Returns [(silence_start, silence_end)] in seconds **relative to the clip
    start** (i.e. matching the timeline used by the render select filter).
    """
    dur = max(0.1, end - start)
    cmd = [
        "ffmpeg", "-hide_banner", "-v", "info",
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(source.resolve()),
        "-af", f"silencedetect=noise={db}dB:d={min_dur}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    silences: list[tuple[float, float]] = []
    pending: float | None = None
    for line in (proc.stderr or "").splitlines():
        m = _START_RE.search(line)
        if m:
            pending = float(m.group(1))
            continue
        m = _END_RE.search(line)
        if m and pending is not None:
            s = max(0.0, min(pending, dur))
            e = max(0.0, min(float(m.group(1)), dur))
            if e > s:
                silences.append((s, e))
            pending = None
    if pending is not None:  # silence runs to the end of the clip
        silences.append((max(0.0, min(pending, dur)), dur))
    return silences


def nonsilent_ranges(duration: float, silences: list[tuple[float, float]],
                     pad: float = 0.12, merge_gap: float = 0.3) -> list[tuple[float, float]]:
    """Invert silences into keep-ranges, with padding and small-gap merging.

    Always returns at least [(0, duration)] so a fully-silent detection can
    never nuke the whole clip.
    """
    ranges: list[tuple[float, float]] = []
    cur = 0.0
    for s, e in sorted(silences):
        s = max(0.0, s - pad)
        e = min(duration, e + pad)
        if s > cur:
            ranges.append((cur, s))
        cur = max(cur, e)
    if cur < duration - 0.05:
        ranges.append((cur, duration))
    merged: list[tuple[float, float]] = []
    for a, b in ranges:
        if merged and a - merged[-1][1] < merge_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        elif b - a >= 0.2:
            merged.append((a, b))
    return merged or [(0.0, duration)]
