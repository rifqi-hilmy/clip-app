"""AI highlight detection: LLM-based clip suggestion from video transcripts."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

log = logging.getLogger("clip.highlight")


@dataclass
class HighlightSettings:
    provider: str = "ollama"
    ollama_model: str = "qwen2.5:3b"
    ollama_url: str = "http://localhost:11434"
    openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    openai_api_key: str = ""
    openai_model: str = "gemini-2.0-flash"
    target_durations: list = field(default_factory=lambda: [15, 30, 60])
    max_clips: int = 10
    min_score: float = 40.0


@dataclass
class HighlightResult:
    start: float
    end: float
    title: str
    score: float
    reason: str
    target_duration: int


def check_ollama(url: str) -> dict[str, Any]:
    try:
        resp = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        return {"available": True, "models": models}
    except Exception:
        return {"available": False, "models": []}


def chunk_transcript(segments: list[dict[str, Any]], chunk_seconds: int = 300, overlap: int = 30) -> list[dict[str, Any]]:
    if not segments:
        return []
    
    chunks = []
    current_chunk = []
    start_time = segments[0]["start"]
    end_time = start_time + chunk_seconds

    for seg in segments:
        while seg["start"] >= end_time and current_chunk:
            chunks.append({
                "start": current_chunk[0]["start"],
                "end": current_chunk[-1]["end"],
                "text": "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in current_chunk),
                "segments": current_chunk
            })
            start_time = end_time - overlap
            end_time = start_time + chunk_seconds
            current_chunk = [s for s in current_chunk if s["start"] >= start_time]
            
        current_chunk.append(seg)
        
    if current_chunk:
        chunks.append({
            "start": current_chunk[0]["start"],
            "end": current_chunk[-1]["end"],
            "text": "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in current_chunk),
            "segments": current_chunk
        })

    return chunks


def heat_score(heatmap: list[dict[str, Any]] | None, start: float, end: float) -> float:
    if not heatmap:
        return 0.5
    
    relevant = [h["value"] for h in heatmap if h["start_time"] < end and h["end_time"] > start]
    if not relevant:
        return 0.5
    return sum(relevant) / len(relevant)


def snap_to_sentence(segments: list[dict[str, Any]], time: float, direction: str = 'nearest') -> float:
    if not segments:
        return time
        
    # Find the segment containing the time
    for i, seg in enumerate(segments):
        if seg["start"] <= time <= seg["end"]:
            # Simple heuristic: closer to start or end?
            if direction == 'nearest':
                if time - seg["start"] < seg["end"] - time:
                    return seg["start"]
                else:
                    return seg["end"]
            elif direction == 'start':
                return seg["start"]
            elif direction == 'end':
                return seg["end"]
                
    # If out of bounds, snap to nearest bound
    if time < segments[0]["start"]:
        return segments[0]["start"]
    return segments[-1]["end"]

def extract_json_array(text: str) -> list[dict[str, Any]]:
    """Robustly extract a list of clip objects from LLM response.
    Handles:
      - Bare array: [ {...}, {...} ]
      - Object with list: { "clips": [ {...} ] } or { "highlights": [ {...} ] }
      - Single clip object: { "start": ..., "end": ... }
      - Markdown fenced code blocks: ```json ... ```
    """
    clean_text = text.strip()
    # Strip markdown codeblocks if any
    clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"\s*```$", "", clean_text)
    clean_text = clean_text.strip()

    # 1. Try parsing full text as JSON directly
    try:
        parsed = json.loads(clean_text)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            # Check for keys that hold a list
            for key in ("clips", "highlights", "moments", "results", "data"):
                if key in parsed and isinstance(parsed[key], list):
                    return [x for x in parsed[key] if isinstance(x, dict)]
            # If the dict itself looks like a clip
            if "start" in parsed and "end" in parsed:
                return [parsed]
            # Look for any list in values
            for v in parsed.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
    except json.JSONDecodeError:
        pass

    # 2. Try regex extraction of array [ ... ]
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass

    # 3. Try regex extraction of object { ... }
    match_obj = re.search(r'\{.*\}', text, re.DOTALL)
    if match_obj:
        try:
            data = json.loads(match_obj.group(0))
            if isinstance(data, dict):
                for key in ("clips", "highlights", "moments", "results", "data"):
                    if key in data and isinstance(data[key], list):
                        return [x for x in data[key] if isinstance(x, dict)]
                if "start" in data and "end" in data:
                    return [data]
        except json.JSONDecodeError:
            pass

    log.warning("Could not parse any clips from LLM output: %s", text[:300])
    return []

def call_llm(prompt: str, settings: HighlightSettings) -> list[dict[str, Any]]:
    if settings.provider == "ollama":
        url = f"{settings.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": settings.ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json"
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            return extract_json_array(content)
            
    else: # openai
        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        payload = {
            "model": settings.openai_model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return extract_json_array(content)


def find_highlights(
    transcript_data: dict[str, Any], 
    heatmap: list[dict[str, Any]] | None, 
    video_title: str, 
    duration: float, 
    settings: HighlightSettings, 
    on_progress: Callable[[float, str], None]
) -> list[HighlightResult]:

    segments = transcript_data.get("segments", [])
    if not segments:
        return []

    chunks = chunk_transcript(segments)
    
    # Score chunks
    for c in chunks:
        c["heat_score"] = heat_score(heatmap, c["start"], c["end"])

    # Sort chunks by heat score (descending) and take top N to avoid massive context
    # Let's take top 5 chunks if we have them
    chunks.sort(key=lambda x: x["heat_score"], reverse=True)
    top_chunks = chunks[:5]
    
    all_results = []
    
    total_chunks = len(top_chunks)
    for i, chunk in enumerate(top_chunks):
        on_progress((i / total_chunks) * 0.8, f"Menganalisa bagian {i+1}/{total_chunks}...")
        
        heatmap_info = ""
        if heatmap:
            heatmap_info = f"This segment has an engagement score of {chunk['heat_score']*100:.1f}/100."
            
        duration_fmt = f"{int(duration // 60)}:{int(duration % 60):02d}"
            
        prompt = f"""You are a video clipping AI. Given a transcript segment with timestamps, identify the most engaging, viral-worthy moments for short-form clips (YouTube Shorts, TikTok).

Video Title: {video_title}
Total Duration: {duration_fmt}
Target Clip Durations: {settings.target_durations} seconds

Transcript (with timestamps):
{chunk['text']}

{heatmap_info}

Find the {settings.max_clips} best clip-worthy moments. For each clip:
- Choose a segment that tells a COMPLETE story/thought (has a clear beginning and end)
- Prefer moments with: hooks, surprising statements, emotional peaks, funny moments, key insights, dramatic reveals
- Avoid cutting mid-sentence
- Each clip should be self-contained and understandable without context

Respond with a JSON object containing a "clips" list:
{{
  "clips": [
    {{
      "start": 12.5,
      "end": 42.5, 
      "title": "Catchy title for this clip",
      "score": 85,
      "reason": "Brief explanation of why this moment is clip-worthy"
    }}
  ]
}}"""
        try:
            items = call_llm(prompt, settings)
            for item in items:
                raw_start = float(item.get("start", 0))
                raw_end = float(item.get("end", raw_start + 30))
                if raw_end <= raw_start:
                    raw_end = raw_start + 30

                start = snap_to_sentence(segments, raw_start, 'start')
                end = snap_to_sentence(segments, raw_end, 'end')
                if end <= start:
                    end = start + 15

                score = float(item.get("score", 50))
                
                if score >= settings.min_score:
                    dur = end - start
                    # Find closest target duration
                    target = min(settings.target_durations, key=lambda x: abs(x - dur))
                    
                    all_results.append(HighlightResult(
                        start=start,
                        end=end,
                        title=str(item.get("title", "Clip")),
                        score=score,
                        reason=str(item.get("reason", "")),
                        target_duration=target
                    ))
        except Exception as e:
            log.warning("Error calling LLM for chunk %d: %s", i, e)
            continue

    on_progress(0.9, "Memproses hasil...")
    
    # Sort by score
    all_results.sort(key=lambda x: x.score, reverse=True)
    
    # Merge overlapping (simple deduplication)
    final_results = []
    for r in all_results:
        overlap = False
        for f in final_results:
            if max(r.start, f.start) < min(r.end, f.end):
                overlap = True
                break
        if not overlap:
            final_results.append(r)
            if len(final_results) >= settings.max_clips:
                break
                
    on_progress(1.0, "Selesai")
    return final_results
