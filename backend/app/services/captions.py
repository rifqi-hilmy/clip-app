"""Caption generation: word timestamps -> ASS (styled, burn-in) and SRT."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Preset definitions (sizes are for a 1080-wide canvas; scaled for other resolutions)
PRESETS: dict[str, dict[str, Any]] = {
    "bold": {  # TikTok-style: big uppercase, thick outline, active word highlighted yellow
        "label": "Bold (highlight kata)", "font": "Arial", "size": 86, "bold": True, "upper": True,
        "primary": "&H00FFFFFF", "highlight": "&H0000FFFF", "outline_c": "&H00000000", "back": "&H64000000",
        "border": 1, "outline": 7, "shadow": 3, "margin_v": 560, "max_words": 3, "max_chars": 20,
    },
    "box": {  # white text on translucent black box, active word green
        "label": "Box", "font": "Arial", "size": 66, "bold": True, "upper": False,
        "primary": "&H00FFFFFF", "highlight": "&H0055FF55", "outline_c": "&H90000000", "back": "&H90000000",
        "border": 3, "outline": 14, "shadow": 0, "margin_v": 520, "max_words": 5, "max_chars": 28,
    },
    "minimal": {  # subtitle-like, no highlight
        "label": "Minimal", "font": "Arial", "size": 58, "bold": True, "upper": False,
        "primary": "&H00FFFFFF", "highlight": None, "outline_c": "&H00000000", "back": "&H80000000",
        "border": 1, "outline": 3, "shadow": 2, "margin_v": 320, "max_words": 8, "max_chars": 42,
    },
}


@dataclass
class Word:
    start: float
    end: float
    text: str


def words_in_range(transcript: dict[str, Any], start: float, end: float) -> list[Word]:
    """Words overlapping [start, end], re-timed relative to clip start and clamped."""
    out: list[Word] = []
    for seg in transcript.get("segments", []):
        if seg["end"] < start or seg["start"] > end:
            continue
        words = seg.get("words") or [{"start": seg["start"], "end": seg["end"], "word": seg["text"]}]
        for w in words:
            mid = (w["start"] + w["end"]) / 2
            if start <= mid <= end:
                text = w["word"].strip()
                if text:
                    out.append(Word(max(0.0, w["start"] - start), min(end - start, w["end"] - start), text))
    return out


def group_lines(words: list[Word], max_words: int, max_chars: int, max_gap: float = 0.7) -> list[list[Word]]:
    lines: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            chars = sum(len(x.text) + 1 for x in cur) + len(w.text)
            gap = w.start - cur[-1].end
            if len(cur) >= max_words or chars > max_chars or gap > max_gap or cur[-1].text[-1:] in ".?!":
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(words: list[Word], style: str, width: int, height: int,
              safe_zone: str | None = None) -> str:
    """Build an ASS subtitle file. safe_zone (Sprint 1/T5) lifts captions above
    the platform's bottom UI area: 'tiktok' | 'reels' | 'shorts' | None."""
    p = PRESETS.get(style) or PRESETS["bold"]
    scale = min(width, height) / 1080
    vscale = height / 1920 if height > width else height / 1080 * 0.45
    size = int(p["size"] * scale)
    margin_v = int(p["margin_v"] * vscale)
    if safe_zone:
        try:
            from .platforms import scaled_zone
            margin_v = max(margin_v, scaled_zone(safe_zone, width, height)["bottom"])
        except KeyError:
            pass

    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{p['font']},{size},{p['primary']},{p['primary']},{p['outline_c']},{p['back']},"
        f"{-1 if p['bold'] else 0},0,0,0,100,100,0,0,{p['border']},{p['outline'] * scale:.1f},{p['shadow'] * scale:.1f},"
        f"2,{int(60 * scale)},{int(60 * scale)},{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    def fmt(w: Word) -> str:
        return _esc(w.text.upper() if p["upper"] else w.text)

    events: list[str] = []
    for line in group_lines(words, p["max_words"], p["max_chars"]):
        l_start, l_end = line[0].start, max(line[-1].end, line[0].start + 0.3)
        if not p["highlight"]:
            text = " ".join(fmt(w) for w in line)
            events.append(f"Dialogue: 0,{_ass_time(l_start)},{_ass_time(l_end)},Default,,0,0,0,,{text}")
            continue
        # One event per word: the active word is coloured, others use the base colour.
        for i, w in enumerate(line):
            e_start = l_start if i == 0 else w.start
            e_end = line[i + 1].start if i + 1 < len(line) else l_end
            if e_end <= e_start:
                continue
            parts = [
                f"{{\\c{p['highlight']}}}{fmt(x)}{{\\c{p['primary']}}}" if j == i else fmt(x)
                for j, x in enumerate(line)
            ]
            events.append(f"Dialogue: 0,{_ass_time(e_start)},{_ass_time(e_end)},Default,,0,0,0,,{' '.join(parts)}")
    return header + "\n".join(events) + "\n"


def retime_words(words: list[Word], ranges: list[tuple[float, float]]) -> list[Word]:
    """Map word times through keep-ranges (Sprint 1/T6 silence removal).

    Words fully inside a removed silence are dropped; words straddling a cut
    are clamped to the range containing their midpoint.
    """
    bounds: list[tuple[float, float, float]] = []
    offset = 0.0
    for a, b in ranges:
        bounds.append((a, b, offset))
        offset += b - a
    out: list[Word] = []
    for w in words:
        mid = (w.start + w.end) / 2
        for a, b, off in bounds:
            if a <= mid <= b:
                ns = max(a, w.start) - a + off
                ne = min(b, w.end) - a + off
                if ne > ns:
                    out.append(Word(ns, ne, w.text))
                break
    return out


def build_srt(words: list[Word], max_words: int = 8, max_chars: int = 42) -> str:
    blocks = []
    for i, line in enumerate(group_lines(words, max_words, max_chars), 1):
        text = " ".join(w.text for w in line)
        blocks.append(f"{i}\n{_srt_time(line[0].start)} --> {_srt_time(line[-1].end)}\n{text}\n")
    return "\n".join(blocks)
