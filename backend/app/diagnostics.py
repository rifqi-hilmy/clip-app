"""Environment diagnostics: verifies external tools the pipeline depends on."""
from __future__ import annotations

import shutil
import subprocess
from typing import Any

from .config import settings


def _run(cmd: list[str], timeout: int = 15) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return (out.stdout or out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_tools() -> dict[str, Any]:
    result: dict[str, Any] = {}

    ffmpeg = shutil.which("ffmpeg")
    result["ffmpeg"] = {"ok": bool(ffmpeg), "path": ffmpeg}
    if ffmpeg:
        ver = _run([ffmpeg, "-hide_banner", "-version"]) or ""
        result["ffmpeg"]["version"] = ver.splitlines()[0] if ver else None
        encoders = _run([ffmpeg, "-hide_banner", "-encoders"]) or ""
        result["ffmpeg"]["h264_amf"] = "h264_amf" in encoders
        result["ffmpeg"]["libx264"] = "libx264" in encoders

    ffprobe = shutil.which("ffprobe")
    result["ffprobe"] = {"ok": bool(ffprobe), "path": ffprobe}

    js = shutil.which(settings.js_runtime)
    result["js_runtime"] = {
        "ok": bool(js),
        "name": settings.js_runtime,
        "version": _run([js, "--version"]) if js else None,
    }

    try:
        import yt_dlp

        result["yt_dlp"] = {"ok": True, "version": yt_dlp.version.__version__}
    except ImportError:
        result["yt_dlp"] = {"ok": False}

    result["ok"] = all(v.get("ok") for v in result.values() if isinstance(v, dict))
    return result
