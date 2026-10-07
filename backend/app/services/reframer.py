"""Face-tracking reframer: MediaPipe face detection → per-frame crop coordinates.

Produces a concat-friendly text file of crop positions that FFmpeg's `sendcmd`
filter can consume, or alternatively generates a frame-by-frame x-offset array
that the renderer uses with the `crop` filter and `sendcmd`.

Strategy:
  1. Sample frames at ~5 fps (fast enough for smooth tracking, cheap on CPU).
  2. Run MediaPipe Face Detection on each sampled frame.
  3. Pick the largest / most central face.
  4. Convert face bbox centre-x to a crop offset in source pixel coords.
  5. Smooth the offset trajectory with EMA (exponential moving average).
  6. On scene cuts (big jump in offset), snap instantly instead of smoothing.
  7. Write the trajectory as a simple JSON file so the renderer can apply it.
"""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("clip.reframer")

# Lazy-loaded heavy imports
_mp_face = None
_cv2 = None
_np = None


def _ensure_deps():
    """Lazy-import heavy libraries only when needed."""
    global _mp_face, _cv2, _np
    if _mp_face is None:
        import cv2
        import mediapipe as mp
        import numpy as np
        _cv2 = cv2
        _mp_face = mp.solutions.face_detection
        _np = np


@dataclass
class TrackingResult:
    """Per-frame crop x-offsets (0..1 range, centre of crop window)."""
    fps: float
    sample_interval: int  # 1 frame out of every N
    offsets: list[float]  # each value is 0..1 (horizontal centre)
    src_width: int
    src_height: int
    face_found_ratio: float  # fraction of sampled frames where a face was detected


def _extract_frames(source: Path, start: float, duration: float, fps: int = 5) -> Path:
    """Extract frames from video segment at the given fps into a temp directory."""
    out_dir = source.parent / "_reframe_tmp"
    out_dir.mkdir(exist_ok=True)
    # Clean previous frames
    for f in out_dir.glob("frame_*.jpg"):
        f.unlink()

    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
         "-vf", f"fps={fps}", "-q:v", "5",
         str(out_dir / "frame_%05d.jpg")],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return out_dir


def track_faces(
    source: Path,
    start: float,
    end: float,
    *,
    sample_fps: int = 5,
    ema_alpha: float = 0.25,
    scene_jump: float = 0.15,
    on_progress: Callable[[float, str], None] | None = None,
) -> TrackingResult:
    """Detect faces and build a smoothed x-offset trajectory.

    Args:
        source: Path to source video.
        start: Clip start time in seconds.
        end: Clip end time in seconds.
        sample_fps: Frames per second to sample (default 5 = very fast).
        ema_alpha: EMA smoothing factor (0..1). Higher = less smoothing.
        scene_jump: If the raw offset jumps more than this fraction, snap instead of smooth.
        on_progress: Optional callback(progress, message).

    Returns:
        TrackingResult with smoothed crop offsets.
    """
    _ensure_deps()
    assert _cv2 is not None and _mp_face is not None and _np is not None

    duration = max(0.1, end - start)
    if on_progress:
        on_progress(0.0, "Mengekstrak frame untuk face tracking…")

    frames_dir = _extract_frames(source, start, duration, sample_fps)
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))

    if not frame_files:
        log.warning("No frames extracted for face tracking")
        return TrackingResult(fps=sample_fps, sample_interval=1,
                              offsets=[0.5], src_width=1920, src_height=1080,
                              face_found_ratio=0.0)

    # Read first frame to get dimensions
    first = _cv2.imread(str(frame_files[0]))
    src_h, src_w = first.shape[:2]

    raw_offsets: list[float] = []
    faces_found = 0

    with _mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.5) as detector:
        total = len(frame_files)
        for i, fpath in enumerate(frame_files):
            img = _cv2.imread(str(fpath))
            if img is None:
                raw_offsets.append(-1.0)  # marker for "no frame"
                continue

            rgb = _cv2.cvtColor(img, _cv2.COLOR_BGR2RGB)
            results = detector.process(rgb)

            if results.detections:
                # Pick the detection with the largest bounding box (most prominent face)
                best = max(results.detections,
                           key=lambda d: d.location_data.relative_bounding_box.width
                                         * d.location_data.relative_bounding_box.height)
                bbox = best.location_data.relative_bounding_box
                # Centre x of the face (0..1)
                cx = bbox.xmin + bbox.width / 2.0
                raw_offsets.append(max(0.0, min(1.0, cx)))
                faces_found += 1
            else:
                raw_offsets.append(-1.0)  # no face detected

            if on_progress and i % max(1, total // 20) == 0:
                on_progress(0.1 + 0.7 * (i / total), f"Face tracking {i}/{total}")

    # Clean up temp frames
    for f in frame_files:
        f.unlink(missing_ok=True)
    frames_dir.rmdir()

    if on_progress:
        on_progress(0.85, "Smoothing trajectory…")

    # Fill gaps (frames where no face was found) with nearest known value
    offsets = _fill_gaps(raw_offsets, default=0.5)

    # EMA smoothing with scene-cut snapping
    smoothed = _smooth_ema(offsets, alpha=ema_alpha, jump_threshold=scene_jump)

    face_ratio = faces_found / max(1, len(raw_offsets))
    log.info("Face tracking: %d/%d frames had faces (%.0f%%)",
             faces_found, len(raw_offsets), face_ratio * 100)

    return TrackingResult(
        fps=sample_fps,
        sample_interval=1,
        offsets=smoothed,
        src_width=src_w,
        src_height=src_h,
        face_found_ratio=face_ratio,
    )


def _fill_gaps(offsets: list[float], default: float = 0.5) -> list[float]:
    """Replace -1.0 markers with the nearest valid value."""
    result = list(offsets)
    n = len(result)
    if n == 0:
        return [default]

    # Forward fill
    last_good = default
    for i in range(n):
        if result[i] >= 0:
            last_good = result[i]
        else:
            result[i] = last_good

    # Backward fill (for leading gaps)
    last_good = default
    for i in range(n - 1, -1, -1):
        if offsets[i] >= 0:
            last_good = result[i]
            break
    for i in range(n):
        if offsets[i] >= 0:
            break
        result[i] = last_good

    return result


def _smooth_ema(offsets: list[float], alpha: float = 0.25,
                jump_threshold: float = 0.15) -> list[float]:
    """Exponential moving average with scene-cut snapping."""
    if not offsets:
        return [0.5]

    smoothed = [offsets[0]]
    for i in range(1, len(offsets)):
        diff = abs(offsets[i] - smoothed[-1])
        if diff > jump_threshold:
            # Scene cut / big jump — snap immediately
            smoothed.append(offsets[i])
        else:
            smoothed.append(alpha * offsets[i] + (1 - alpha) * smoothed[-1])
    return smoothed


def save_tracking(result: TrackingResult, path: Path) -> None:
    """Save tracking data as JSON for the renderer to consume."""
    data = {
        "fps": result.fps,
        "sample_interval": result.sample_interval,
        "offsets": [round(o, 4) for o in result.offsets],
        "src_width": result.src_width,
        "src_height": result.src_height,
        "face_found_ratio": round(result.face_found_ratio, 3),
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def load_tracking(path: Path) -> TrackingResult | None:
    """Load tracking data from JSON."""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return TrackingResult(**data)


def tracking_to_crop_x(result: TrackingResult, frame_idx: int) -> float:
    """Get the crop_x position (0..1) for a given frame index in the original video.

    The offsets are at `result.fps` samples/sec. This function maps any original
    frame index back to the nearest tracked offset.
    """
    if not result.offsets:
        return 0.5
    idx = min(frame_idx, len(result.offsets) - 1)
    return result.offsets[max(0, idx)]
