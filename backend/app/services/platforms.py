"""Per-platform safe zones for short-form video (Sprint 1/T5).

Margins are defined in pixels on a 1080x1920 canvas and mark the areas
covered by each platform's UI (like/comment buttons, captions, progress bar).
Use scaled_zone() for other canvas sizes.
"""
from __future__ import annotations

SAFE_ZONES: dict[str, dict[str, int | str]] = {
    "tiktok": {"label": "TikTok", "top": 150, "right": 120, "bottom": 380, "left": 40},
    "reels": {"label": "Instagram Reels", "top": 140, "right": 100, "bottom": 340, "left": 40},
    "shorts": {"label": "YouTube Shorts", "top": 120, "right": 60, "bottom": 300, "left": 40},
}


def scaled_zone(zone: str, w: int, h: int) -> dict[str, int]:
    """Return {top, right, bottom, left} margins scaled to a (w, h) canvas."""
    z = SAFE_ZONES[zone]  # raises KeyError for unknown zone
    sx, sy = w / 1080, h / 1920
    out: dict[str, int] = {}
    for k, v in z.items():
        if k == "label" or not isinstance(v, int):
            continue
        out[k] = int(v * (sx if k in ("left", "right") else sy))
    return out


def list_zones() -> list[dict[str, str]]:
    return [{"id": k, "label": str(v["label"])} for k, v in SAFE_ZONES.items()]
