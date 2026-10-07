"""YouTube metadata + download via yt-dlp."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yt_dlp

from ..config import settings

_YT_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")

# Prefer H.264 + AAC in MP4 so the browser <video> can play the source directly.
FORMAT = (
    "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/"
    "bv*[height<=1080]+ba/"
    "b[height<=1080]/b"
)


def extract_youtube_id(url: str) -> str | None:
    m = _YT_ID.search(url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    return None


def _base_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "js_runtimes": {settings.js_runtime: {"path": None}},
        "remote_components": ["ejs:github"],
    }
    if settings.cookies_file and Path(settings.cookies_file).exists():
        opts["cookiefile"] = str(settings.cookies_file)
    return opts


def fetch_info(url: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(_base_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "youtube_id": info["id"],
        "url": info.get("webpage_url") or url,
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": float(info.get("duration") or 0),
        "thumbnail": info.get("thumbnail") or "",
        "heatmap": info.get("heatmap"),
        "chapters": info.get("chapters"),
    }


def video_dir(youtube_id: str) -> Path:
    d = settings.videos_dir / youtube_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(url: str, youtube_id: str, on_progress: Callable[[float, str], None]) -> Path:
    out_dir = video_dir(youtube_id)
    target = out_dir / "source.mp4"
    if target.exists() and target.stat().st_size > 0:
        return target

    # yt-dlp downloads video and audio separately; track overall progress across both.
    state = {"part": 0, "parts": 2}

    def hook(d: dict[str, Any]) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            frac = (d.get("downloaded_bytes", 0) / total) if total else 0.0
            overall = (state["part"] + frac) / state["parts"] * 0.95
            speed = d.get("_speed_str", "").strip()
            on_progress(overall, f"Downloading {frac * 100:.0f}% {speed}")
        elif d["status"] == "finished":
            state["part"] = min(state["part"] + 1, state["parts"] - 1)

    def pp_hook(d: dict[str, Any]) -> None:
        if d["status"] == "started" and d.get("postprocessor") == "Merger":
            on_progress(0.96, "Merging video + audio")

    opts = _base_opts() | {
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "source.%(ext)s"),
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
        "writethumbnail": False,
        "overwrites": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    if not target.exists():
        # Fallback: some formats end up with another extension.
        candidates = sorted(out_dir.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            raise RuntimeError("Download finished but no output file found")
        candidates[0].rename(target)
    return target
