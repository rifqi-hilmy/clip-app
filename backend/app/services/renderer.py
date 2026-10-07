"""FFmpeg rendering: cut + 9:16 reframe (blur background / manual center crop / face tracking)."""
from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..config import settings

OUT_W, OUT_H = 1080, 1920

# Sprint 1/T2: supported vertical aspects -> (width, height)
ASPECTS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


@dataclass
class RenderSpec:
    source: Path
    output: Path
    start: float
    end: float
    aspect: str = "9:16"  # 9:16 | 1:1 | 4:5 | original
    reframe: str = "blur"  # blur | center | face
    crop_x: float = 0.5
    ass_file: Path | None = None  # burn-in captions (must live next to output)
    face_offsets: list = field(default_factory=list)  # per-sample crop_x from face tracking
    face_fps: float = 5.0  # sample rate of face_offsets
    loudnorm: bool = True  # EBU R128-ish loudness normalization for consistent volume
    # Sprint 1 / T6: non-silent keep ranges [(a, b)] in seconds, relative to clip start.
    # When set, audio select is baked into filter_complex instead of -af.
    keep_ranges: list | None = None
    keep_ranges_audio: bool = True  # False when the source has no audio stream


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    st = data["streams"][0]
    return {"width": int(st["width"]), "height": int(st["height"]),
            "duration": float(data.get("format", {}).get("duration", 0) or 0)}


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def target_size(spec: RenderSpec, src_w: int, src_h: int) -> tuple[int, int]:
    """Output (w, h) for the requested aspect."""
    if spec.aspect == "original":
        return (src_w, src_h)
    return ASPECTS.get(spec.aspect, (OUT_W, OUT_H))


def build_filter(spec: RenderSpec, src_w: int, src_h: int) -> str:
    """Return a -filter_complex graph producing [v]."""
    if spec.aspect == "original":
        return "[0:v]setsar=1[v]"

    tw, th = target_size(spec, src_w, src_h)
    target = tw / th

    # Sprint 1/T6: silence removal — keep only non-silent ranges.
    # Implemented as trim+concat (aselect proved unreliable for dropping
    # audio frames on some FFmpeg builds; trim/atrim always works).
    # NOTE: explicit split/asplit is required — ffmpeg's auto-inserted split
    # on fan-out mis-negotiates frame size with trim (1280x720 leak).
    trim_graph = ""
    if spec.keep_ranges:
        n = len(spec.keep_ranges)
        vouts = "".join(f"[vraw{i}]" for i in range(n))
        v_trims = ";".join(
            f"[vraw{i}]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]"
            for i, (a, b) in enumerate(spec.keep_ranges)
        )
        v_ins = "".join(f"[v{i}]" for i in range(n))
        trim_graph = f";[vraw]split={n}{vouts};{v_trims};{v_ins}concat=n={n}:v=1:a=0[v]"
        if spec.keep_ranges_audio:
            aouts = "".join(f"[ain{i}]" for i in range(n))
            a_trims = ";".join(
                f"[ain{i}]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[au{i}]"
                for i, (a, b) in enumerate(spec.keep_ranges)
            )
            a_ins = "".join(f"[au{i}]" for i in range(n))
            a_chain = f"{a_ins}concat=n={n}:v=0:a=1"
            if spec.loudnorm:
                a_chain += ",loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95"
            trim_graph += f";[0:a]asplit={n}{aouts};{a_trims};{a_chain}[a]"

    if spec.reframe == "face" and spec.face_offsets:
        # Face tracking: compute per-scene crop positions.
        # For short clips (<= 90s at 5fps = 450 offsets), using the dominant
        # position is smooth enough.  We split into scene segments where
        # the face position jumps significantly.
        base = _build_face_filter(spec, src_w, src_h, tw, th)
    elif spec.reframe == "center" or (spec.reframe == "face" and not spec.face_offsets):
        # "face" without offsets falls back to centre crop with the given crop_x
        if src_w / src_h > target:  # wider than target -> crop width
            cw, ch = _even(src_h * target), _even(src_h)
            x = int((src_w - cw) * min(max(spec.crop_x, 0.0), 1.0))
            y = 0
        else:  # taller -> crop height (centered)
            cw, ch = _even(src_w), _even(src_w / target)
            x, y = 0, (src_h - ch) // 2
        base = f"[0:v]crop={cw}:{ch}:{x}:{y},scale={tw}:{th}:flags=lanczos,setsar=1[v]"
    else:
        # blur: full frame centered over a blurred, zoomed copy of itself.
        # Background is blurred at low resolution, which is much cheaper on CPU.
        bw, bh = _even(tw // 4), _even(th // 4)
        base = (
            "[0:v]split=2[bg][fg];"
            f"[bg]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},boxblur=12:2,"
            f"scale={tw}:{th}[bgb];"
            f"[fg]scale={tw}:{th}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
            "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
        )

    if not spec.keep_ranges:
        return base
    # Reframe output becomes [vraw]; trim each keep-range, then concat.
    return base[: -len("[v]")] + "[vraw]" + trim_graph


def _build_face_filter(spec: RenderSpec, src_w: int, src_h: int,
                       tw: int = OUT_W, th: int = OUT_H) -> str:
    """Build a blur-background + face-tracked crop overlay filter.

    The approach: render the source in two layers:
      1. Background: blurred full-frame (same as blur mode).
      2. Foreground: the source cropped to 9:16 centred on the tracked face position,
         overlaid at the centre.

    For a short clip, we use the median face offset as a static crop_x.
    For longer clips with significant face movement, we segment and use
    the median of each segment.  Since FFmpeg's crop filter accepts expressions,
    we precompute a single stable crop position per clip — which is the practical
    sweet spot for 15-90s short-form clips.
    """
    # Compute the dominant face position (median offset)
    import statistics
    median_x = statistics.median(spec.face_offsets) if spec.face_offsets else 0.5

    target = tw / th
    if src_w / src_h > target:
        cw, ch = _even(src_h * target), _even(src_h)
        x = int((src_w - cw) * min(max(median_x, 0.0), 1.0))
        y = 0
    else:
        cw, ch = _even(src_w), _even(src_w / target)
        x, y = 0, (src_h - ch) // 2

    # Blur background + face-tracked crop overlay
    return (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=12:2,"
        f"scale={tw}:{th}[bgb];"
        f"[fg]crop={cw}:{ch}:{x}:{y},scale={tw}:{th}:flags=lanczos[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
    )


def _encoder_args(encoder: str) -> list[str]:
    if encoder == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


_TIME_RE = re.compile(r"out_time_us=(\d+)")


def _run_ffmpeg(cmd: list[str], duration: float, on_progress: Callable[[float], None],
                cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        m = _TIME_RE.match(line.strip())
        if m and duration > 0:
            on_progress(min(int(m.group(1)) / 1e6 / duration, 0.999))
    stderr = proc.stderr.read() if proc.stderr else ""
    return proc.wait(), stderr


def output_size(spec: RenderSpec, src_w: int, src_h: int) -> tuple[int, int]:
    return target_size(spec, src_w, src_h)


def _has_audio(path: Path) -> bool:
    """True when the file contains at least one audio stream."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        )
        return bool(out.stdout.strip())
    except subprocess.CalledProcessError:
        return False


def render(spec: RenderSpec, on_progress: Callable[[float, str], None]) -> Path:
    info = probe(spec.source)
    in_duration = max(0.1, spec.end - spec.start)  # input trim length (-t)
    # Effective output duration (shorter when silence removal drops ranges).
    duration = in_duration
    if spec.keep_ranges:
        duration = max(0.1, sum(b - a for a, b in spec.keep_ranges))
        if not _has_audio(spec.source):
            spec.keep_ranges_audio = False  # video-only source: skip audio select
    graph = build_filter(spec, info["width"], info["height"])
    spec.output.parent.mkdir(parents=True, exist_ok=True)

    cwd: Path | None = None
    if spec.ass_file:
        # Windows drive letters ("C:") break filter-arg parsing, so reference the
        # ASS file by bare name and run ffmpeg from its directory.
        cwd = spec.ass_file.parent
        graph = graph[: -len("[v]")] + f"[vpre];[vpre]ass={spec.ass_file.name}[v]"

    # Audio chain: loudness normalization. When keep_ranges is set (T6 silence
    # removal) with audio present, the aselect+loudnorm live inside
    # filter_complex and we map [a] instead.
    use_graph_audio = bool(spec.keep_ranges and spec.keep_ranges_audio)
    audio_map = "[a]" if use_graph_audio else "0:a?"
    af_args: list[str] = []
    if spec.loudnorm and not use_graph_audio:
        af_args = ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95"]

    def cmd_for(encoder: str) -> list[str]:
        return [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
            "-ss", f"{spec.start:.3f}", "-i", str(spec.source.resolve()), "-t", f"{in_duration:.3f}",
            "-filter_complex", graph, "-map", "[v]", "-map", audio_map,
            *_encoder_args(encoder), "-pix_fmt", "yuv420p",
            *af_args,
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(spec.output.resolve()),
        ]

    encoders = [settings.video_encoder]
    if settings.video_encoder != "libx264":
        encoders.append("libx264")  # fallback if the hardware encoder fails

    last_err = ""
    for enc in encoders:
        on_progress(0.0, f"Rendering ({enc})")
        code, err = _run_ffmpeg(cmd_for(enc), duration,
                                lambda p, e=enc: on_progress(p, f"Rendering ({e}) {p * 100:.0f}%"), cwd)
        if code == 0 and spec.output.exists():
            return spec.output
        last_err = err.strip()[-1500:]
    raise RuntimeError(f"FFmpeg failed: {last_err}")
