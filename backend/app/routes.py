"""REST + WebSocket routes."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from .config import settings
from .db import engine, get_session
from .events import hub
from .jobs import JobContext, enqueue
from .models import Clip, Job, Project, Video
from .services import captions, downloader, highlighter, reframer, renderer, silence, transcriber
from .services.platforms import list_zones as _list_safe_zones

router = APIRouter(prefix="/api")


# ---------- helpers ----------

def media_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(settings.storage_dir.resolve())
    except ValueError:
        return None
    return "/media/" + rel.as_posix()


def video_out(v: Video) -> dict[str, Any]:
    d = v.model_dump(mode="json")
    d["media_url"] = media_url(v.path)
    return d


def clip_out(c: Clip) -> dict[str, Any]:
    d = c.model_dump(mode="json")
    d["export_url"] = media_url(c.export_path)
    srt = Path(c.export_path).with_suffix(".srt") if c.export_path else None
    d["srt_url"] = media_url(str(srt)) if srt and srt.exists() else None
    return d


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s[:n] or "clip"


def _project_or_404(s: Session, project_id: int) -> Project:
    p = s.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _notify_project(project_id: int) -> None:
    hub.publish({"type": "project", "project_id": project_id})


# ---------- schemas ----------

class UrlIn(BaseModel):
    url: str


class ProjectIn(BaseModel):
    url: str
    language: Optional[str] = None  # "id" | "en" | None (auto)


class ClipIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = ""
    aspect: str = "9:16"  # 9:16 | 1:1 | 4:5 | original  (Sprint 1/T2)
    reframe: str = "blur"
    crop_x: float = Field(0.5, ge=0, le=1)
    caption_style: Optional[str] = None  # None = no captions | bold | box | minimal
    loudnorm: bool = True  # Sprint 1/T1
    safe_zone: Optional[str] = None  # Sprint 1/T5: tiktok | reels | shorts | None
    remove_silence: bool = False  # Sprint 1/T6
    silence_db: float = -35.0  # Sprint 1/T6
    silence_min_dur: float = 0.8  # Sprint 1/T6


class ClipPatch(BaseModel):
    start: Optional[float] = Field(None, ge=0)
    end: Optional[float] = Field(None, gt=0)
    title: Optional[str] = None
    aspect: Optional[str] = None
    reframe: Optional[str] = None
    crop_x: Optional[float] = Field(None, ge=0, le=1)
    caption_style: Optional[str] = None
    loudnorm: Optional[bool] = None  # Sprint 1/T1
    safe_zone: Optional[str] = None  # Sprint 1/T5
    remove_silence: Optional[bool] = None  # Sprint 1/T6
    silence_db: Optional[float] = None  # Sprint 1/T6
    silence_min_dur: Optional[float] = None  # Sprint 1/T6


class ReviewIn(BaseModel):
    state: str  # pending | approved | rejected


class TranscribeIn(BaseModel):
    model: str = "small"
    language: Optional[str] = None  # overrides project language; None = use project / auto
    force: bool = False


class HighlightIn(BaseModel):
    provider: str = "ollama"  # "ollama" | "openai"
    model: str | None = None  # override; None = use config default
    max_clips: int = 10
    target_durations: list[int] = Field(default_factory=lambda: [15, 30, 60])
    min_score: float = 40.0


class HighlightSettingsIn(BaseModel):
    provider: str | None = None
    ollama_model: str | None = None  
    ollama_url: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None


class LocalFileIn(BaseModel):
    path: str
    title: str = ""
    language: Optional[str] = None


class GenerateMetaIn(BaseModel):
    provider: str = "ollama"
    model: str | None = None


# ---------- videos / projects ----------

@router.post("/videos/info")
def video_info(body: UrlIn) -> dict[str, Any]:
    if not downloader.extract_youtube_id(body.url):
        raise HTTPException(400, "URL YouTube tidak valid")
    try:
        info = downloader.fetch_info(body.url)
    except Exception as exc:
        raise HTTPException(502, f"Gagal mengambil info video: {exc}") from exc
    info["has_heatmap"] = bool(info.pop("heatmap"))
    info["chapters_count"] = len(info.pop("chapters") or [])
    return info


@router.get("/projects")
def list_projects(s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = s.exec(select(Project, Video).join(Video).order_by(col(Project.created_at).desc())).all()
    out = []
    for p, v in rows:
        n = len(s.exec(select(Clip.id).where(Clip.project_id == p.id)).all())
        out.append(p.model_dump(mode="json") | {"video": video_out(v), "clip_count": n})
    return out


def _download_job(project_id: int, video_id: int) -> Any:
    def run(ctx: JobContext) -> None:
        with Session(engine) as s:
            v = s.get(Video, video_id)
            p = s.get(Project, project_id)
            assert v and p
            p.status = "downloading"
            s.add(p)
            s.commit()
            url, yid = v.url, v.youtube_id
        _notify_project(project_id)
        try:
            path = downloader.download(url, yid, lambda prog, msg: ctx.update(prog, msg))
        except Exception:
            with Session(engine) as s:
                p = s.get(Project, project_id)
                if p:
                    p.status = "error"
                    s.add(p)
                    s.commit()
            _notify_project(project_id)
            raise
        with Session(engine) as s:
            v = s.get(Video, video_id)
            assert v
            v.path = str(path)
            s.add(v)
            # every project using this video becomes ready
            for p in s.exec(select(Project).where(Project.video_id == video_id)):
                p.status = "ready"
                s.add(p)
            s.commit()
        ctx.update(1.0, "Download selesai", force=True)
        _notify_project(project_id)

    return run


@router.post("/projects")
def create_project(body: ProjectIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    yid = downloader.extract_youtube_id(body.url)
    if not yid:
        raise HTTPException(400, "URL YouTube tidak valid")

    video = s.exec(select(Video).where(Video.youtube_id == yid)).first()
    if not video:
        try:
            info = downloader.fetch_info(body.url)
        except Exception as exc:
            raise HTTPException(502, f"Gagal mengambil info video: {exc}") from exc
        video = Video(**info)
        s.add(video)
        s.commit()
        s.refresh(video)

    ready = bool(video.path and Path(video.path).exists())
    project = Project(video_id=video.id, name=video.title, language=body.language,
                      status="ready" if ready else "created")
    s.add(project)
    s.commit()
    s.refresh(project)

    if not ready:
        enqueue(Job(project_id=project.id, type="download"), _download_job(project.id, video.id))

    return project.model_dump(mode="json") | {"video": video_out(video)}


@router.get("/projects/{project_id}")
def get_project(project_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    p = _project_or_404(s, project_id)
    v = s.get(Video, p.video_id)
    clips = s.exec(select(Clip).where(Clip.project_id == p.id).order_by(col(Clip.start))).all()
    jobs = s.exec(select(Job).where(Job.project_id == p.id).order_by(col(Job.id).desc()).limit(50)).all()
    return p.model_dump(mode="json") | {
        "video": video_out(v) if v else None,
        "clips": [clip_out(c) for c in clips],
        "jobs": [j.model_dump(mode="json") for j in jobs],
        "transcript": _transcript_meta(v),
    }


@router.post("/projects/{project_id}/download")
def retry_download(project_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    p = _project_or_404(s, project_id)
    job = enqueue(Job(project_id=p.id, type="download"), _download_job(p.id, p.video_id))
    return job.model_dump(mode="json")


# ---------- storage management (Sprint 1/T3) ----------

def _dir_size_mb(path: Path) -> float:
    total = 0
    if path.exists():
        for f in path.rglob("*"):
            try:
                if f.is_file() and not f.is_symlink():
                    total += f.stat().st_size
            except OSError:
                pass
    return round(total / (1024 * 1024), 1)


@router.get("/storage/usage")
def storage_usage(s: Session = Depends(get_session)) -> dict[str, Any]:
    videos_mb = _dir_size_mb(settings.videos_dir)
    exports_mb = _dir_size_mb(settings.exports_dir)
    by_project: list[dict[str, Any]] = []
    for p in s.exec(select(Project)):
        exp_mb = _dir_size_mb(settings.exports_dir / str(p.id))
        v = s.get(Video, p.video_id)
        src_mb = 0.0
        if v and v.path:
            try:
                src_mb = Path(v.path).stat().st_size / (1024 * 1024)
            except OSError:
                src_mb = 0.0
        by_project.append({"project_id": p.id, "name": p.name,
                           "mb": round(exp_mb + src_mb, 1)})
    by_project.sort(key=lambda x: x["mb"], reverse=True)
    return {"total_mb": round(videos_mb + exports_mb, 1),
            "videos_mb": videos_mb, "exports_mb": exports_mb,
            "by_project": by_project}


@router.delete("/projects/{project_id}/source")
def delete_source(project_id: int, s: Session = Depends(get_session)) -> dict[str, str]:
    """Delete the downloaded source video file; clips & transcript are kept."""
    p = _project_or_404(s, project_id)
    v = s.get(Video, p.video_id)
    if v and v.path:
        try:
            Path(v.path).unlink(missing_ok=True)
            Path(v.path).parent.rmdir()  # remove now-empty video dir
        except OSError:
            pass
        v.path = None
        s.add(v)
        # every project sharing this video needs a re-download
        for other in s.exec(select(Project).where(Project.video_id == v.id)):
            other.status = "created"
            s.add(other)
    s.commit()
    return {"status": "deleted"}


@router.delete("/videos/{video_id}/cache")
def delete_video_cache(video_id: int, s: Session = Depends(get_session)) -> dict[str, str]:
    v = s.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    if s.exec(select(Project.id).where(Project.video_id == video_id)).first():
        raise HTTPException(409, "Video masih dipakai project — hapus project dulu")
    if v.path:
        try:
            Path(v.path).unlink(missing_ok=True)
            Path(v.path).parent.rmdir()
        except OSError:
            pass
    tdir = downloader.video_dir(v.youtube_id)
    if tdir.exists():
        shutil.rmtree(tdir, ignore_errors=True)
    s.delete(v)
    s.commit()
    return {"status": "deleted"}


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, s: Session = Depends(get_session)) -> dict[str, str]:
    p = _project_or_404(s, project_id)
    for j in s.exec(select(Job).where(Job.project_id == p.id)):
        s.delete(j)
    for c in s.exec(select(Clip).where(Clip.project_id == p.id)):
        s.delete(c)
    s.delete(p)  # source video stays cached for reuse
    s.commit()
    return {"status": "deleted"}


# ---------- transcription & captions ----------

def _transcript_meta(v: Video | None) -> Optional[dict[str, Any]]:
    if not v:
        return None
    t = transcriber.load_transcript(downloader.video_dir(v.youtube_id))
    if not t:
        return None
    return {"language": t["language"], "model": t["model"], "segments": len(t["segments"])}


def _transcribe_job(project_id: int, model: str, language: Optional[str]) -> Any:
    def run(ctx: JobContext) -> None:
        with Session(engine) as s:
            p = s.get(Project, project_id)
            v = s.get(Video, p.video_id) if p else None
            if not v or not v.path or not Path(v.path).exists():
                raise RuntimeError("Video sumber belum di-download")
            source, yid = Path(v.path), v.youtube_id
        transcriber.transcribe(source, downloader.video_dir(yid), model=model, language=language,
                               on_progress=lambda prog, msg: ctx.update(prog, msg))
        ctx.update(1.0, "Transkripsi selesai", force=True)
        _notify_project(project_id)

    return run


@router.get("/whisper/models")
def whisper_models() -> dict[str, Any]:
    return {"models": transcriber.WHISPER_MODELS, "default": "small"}


@router.get("/captions/presets")
def caption_presets() -> list[dict[str, str]]:
    return [{"id": k, "label": v["label"]} for k, v in captions.PRESETS.items()]


@router.get("/platforms/safe-zones")
def safe_zones() -> list[dict[str, str]]:
    """Sprint 1/T5: per-platform safe zones for the 9:16 canvas."""
    return _list_safe_zones()


@router.post("/projects/{project_id}/transcribe")
def start_transcribe(project_id: int, body: TranscribeIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    p = _project_or_404(s, project_id)
    if body.model not in transcriber.WHISPER_MODELS:
        raise HTTPException(400, f"Model tidak dikenal: {body.model}")
    v = s.get(Video, p.video_id)
    meta = _transcript_meta(v)
    if meta and not body.force:
        raise HTTPException(409, "Transkrip sudah ada (pakai force untuk ulang)")
    language = body.language if body.language is not None else p.language
    job = enqueue(Job(project_id=p.id, type="transcribe"), _transcribe_job(p.id, body.model, language or None))
    return job.model_dump(mode="json")


@router.get("/projects/{project_id}/transcript")
def get_transcript(project_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    p = _project_or_404(s, project_id)
    v = s.get(Video, p.video_id)
    t = transcriber.load_transcript(downloader.video_dir(v.youtube_id)) if v else None
    if not t:
        raise HTTPException(404, "Belum ada transkrip")
    return t


# ---------- clips ----------

def _validate_range(start: float, end: float, duration: float) -> None:
    if end <= start:
        raise HTTPException(400, "End harus lebih besar dari start")
    if end - start < 1:
        raise HTTPException(400, "Durasi klip minimal 1 detik")
    if duration and end > duration + 0.5:
        raise HTTPException(400, "End melebihi durasi video")


_VALID_ASPECTS = {"9:16", "1:1", "4:5", "original"}  # Sprint 1/T2


def _validate_aspect(aspect: Optional[str]) -> None:
    if aspect is not None and aspect not in _VALID_ASPECTS:
        raise HTTPException(400, f"Aspect tidak valid: {aspect}")


@router.post("/projects/{project_id}/clips")
def create_clip(project_id: int, body: ClipIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    p = _project_or_404(s, project_id)
    v = s.get(Video, p.video_id)
    _validate_range(body.start, body.end, v.duration if v else 0)
    _validate_aspect(body.aspect)
    c = Clip(project_id=p.id, **body.model_dump())
    if not c.title:
        n = len(s.exec(select(Clip.id).where(Clip.project_id == p.id)).all()) + 1
        c.title = f"Clip {n}"
    s.add(c)
    s.commit()
    s.refresh(c)
    return clip_out(c)


@router.patch("/clips/{clip_id}")
def update_clip(clip_id: int, body: ClipPatch, s: Session = Depends(get_session)) -> dict[str, Any]:
    c = s.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, "Clip not found")
    for k, val in body.model_dump(exclude_unset=True).items():
        setattr(c, k, val)
    p = s.get(Project, c.project_id)
    v = s.get(Video, p.video_id) if p else None
    _validate_range(c.start, c.end, v.duration if v else 0)
    _validate_aspect(c.aspect)
    s.add(c)
    s.commit()
    s.refresh(c)
    return clip_out(c)


@router.delete("/clips/{clip_id}")
def delete_clip(clip_id: int, s: Session = Depends(get_session)) -> dict[str, str]:
    c = s.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, "Clip not found")
    for j in s.exec(select(Job).where(Job.clip_id == c.id)):
        s.delete(j)
    s.delete(c)
    s.commit()
    return {"status": "deleted"}


# ---------- clip review (Sprint 1/T4) ----------

@router.patch("/clips/{clip_id}/review")
def review_clip(clip_id: int, body: ReviewIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    c = s.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, "Clip not found")
    if body.state not in ("pending", "approved", "rejected"):
        raise HTTPException(400, "State tidak valid: pending | approved | rejected")
    c.review_state = body.state
    s.add(c)
    s.commit()
    s.refresh(c)
    return clip_out(c)


@router.post("/projects/{project_id}/review-all")
def review_all_clips(project_id: int, body: ReviewIn,
                     s: Session = Depends(get_session)) -> dict[str, int]:
    p = _project_or_404(s, project_id)
    if body.state not in ("pending", "approved", "rejected"):
        raise HTTPException(400, "State tidak valid: pending | approved | rejected")
    n = 0
    for c in s.exec(select(Clip).where(Clip.project_id == p.id,
                                       Clip.review_state == "pending")):
        c.review_state = body.state
        s.add(c)
        n += 1
    s.commit()
    return {"updated": n}


def _render_job(clip_id: int) -> Any:
    def run(ctx: JobContext) -> None:
        with Session(engine) as s:
            c = s.get(Clip, clip_id)
            if not c:
                raise RuntimeError("Clip sudah dihapus")
            p = s.get(Project, c.project_id)
            v = s.get(Video, p.video_id) if p else None
            if not v or not v.path or not Path(v.path).exists():
                raise RuntimeError("Video sumber belum di-download")
            out = settings.exports_dir / str(c.project_id) / f"clip_{c.id:03d}_{_slug(c.title)}.mp4"
            spec = renderer.RenderSpec(source=Path(v.path), output=out, start=c.start, end=c.end,
                                       aspect=c.aspect, reframe=c.reframe, crop_x=c.crop_x,
                                       loudnorm=c.loudnorm)
            project_id, style, yid = c.project_id, c.caption_style, v.youtube_id

        out.parent.mkdir(parents=True, exist_ok=True)

        # Phase 4: face tracking before render
        if spec.reframe == "face" and spec.aspect == "9:16":
            ctx.update(0.0, "Face tracking…")
            try:
                tracking = reframer.track_faces(
                    spec.source, spec.start, spec.end,
                    on_progress=lambda p, msg: ctx.update(p * 0.3, f"Face: {msg}"),
                )
                spec.face_offsets = tracking.offsets
                spec.face_fps = tracking.fps
            except Exception as exc:
                import logging
                logging.getLogger("clip.render").warning("Face tracking failed, falling back to center: %s", exc)
                spec.reframe = "center"  # fallback

        # Sprint 1/T6: silence removal — detect keep-ranges before captions so
        # word timings can be remapped to the trimmed timeline.
        if c.remove_silence:
            ctx.update(0.0, "Mendeteksi jeda diam…")
            try:
                found = silence.detect_silences(spec.source, spec.start, spec.end,
                                                db=c.silence_db, min_dur=c.silence_min_dur)
                ranges = silence.nonsilent_ranges(spec.end - spec.start, found)
                full = [(0.0, spec.end - spec.start)]
                if ranges != full:
                    spec.keep_ranges = ranges
                    ctx.update(0.05, f"Jeda diam dibuang: {len(ranges)} segmen")
            except Exception as exc:
                import logging
                logging.getLogger("clip.render").warning(
                    "Silence detect failed, keeping full clip: %s", exc)

        srt_path = out.with_suffix(".srt")
        transcript = transcriber.load_transcript(downloader.video_dir(yid))
        if transcript:
            words = captions.words_in_range(transcript, spec.start, spec.end)
            if spec.keep_ranges:
                words = captions.retime_words(words, spec.keep_ranges)
            srt_path.write_text(captions.build_srt(words), encoding="utf-8")
            if style:
                info = renderer.probe(spec.source)
                w, h = renderer.output_size(spec, info["width"], info["height"])
                spec.ass_file = out.with_suffix(".ass")
                spec.ass_file.write_text(
                    captions.build_ass(words, style, w, h, c.safe_zone),  # Sprint 1/T5
                    encoding="utf-8")
        elif style:
            raise RuntimeError("Caption butuh transkrip — jalankan Transkripsi dulu")
        else:
            srt_path.unlink(missing_ok=True)

        progress_base = 0.3 if spec.reframe == "face" else 0.0
        path = renderer.render(spec, lambda prog, msg: ctx.update(
            progress_base + prog * (1.0 - progress_base), msg))
        if spec.ass_file:
            spec.ass_file.unlink(missing_ok=True)
        with Session(engine) as s:
            c = s.get(Clip, clip_id)
            if c:
                c.export_path = str(path)
                s.add(c)
                s.commit()
        ctx.update(1.0, "Render selesai", force=True)
        _notify_project(project_id)

    return run


@router.post("/clips/{clip_id}/render")
def render_clip(clip_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    c = s.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, "Clip not found")
    if c.review_state != "approved":  # Sprint 1/T4
        raise HTTPException(409, "Klip belum di-approve — selesaikan review dulu")
    job = enqueue(Job(project_id=c.project_id, clip_id=c.id, type="render"), _render_job(c.id))
    return job.model_dump(mode="json")


@router.post("/projects/{project_id}/render-all")
def render_all(project_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    p = _project_or_404(s, project_id)
    clips = s.exec(select(Clip).where(Clip.project_id == p.id).order_by(col(Clip.start))).all()
    jobs: list[dict[str, Any]] = []
    skipped = 0
    for c in clips:
        if c.review_state != "approved":  # Sprint 1/T4
            skipped += 1
            continue
        jobs.append(enqueue(Job(project_id=p.id, clip_id=c.id, type="render"),
                            _render_job(c.id)).model_dump(mode="json"))
    return {"jobs": jobs, "skipped": skipped}


def _highlight_job(project_id: int, settings_dict: dict[str, Any]) -> Any:
    def run(ctx: JobContext) -> None:
        with Session(engine) as s:
            p = s.get(Project, project_id)
            v = s.get(Video, p.video_id) if p else None
            if not v:
                raise RuntimeError("Video tidak ditemukan")

            transcript_data = transcriber.load_transcript(downloader.video_dir(v.youtube_id))
            if not transcript_data:
                raise RuntimeError("Transkrip belum tersedia")

            heatmap_data = v.heatmap  # list[dict] | None from YouTube "Most Replayed"
            title = v.title
            dur = v.duration or 0.0

        hl_settings = highlighter.HighlightSettings(**settings_dict)

        ctx.update(0.1, "Menganalisa transkrip…")
        results = highlighter.find_highlights(
            transcript_data=transcript_data,
            heatmap=heatmap_data,
            video_title=title,
            duration=dur,
            settings=hl_settings,
            on_progress=lambda prog, msg: ctx.update(0.1 + prog * 0.8, msg),
        )

        with Session(engine) as s:
            for r in results:
                s.add(Clip(
                    project_id=project_id,
                    start=r.start,
                    end=r.end,
                    title=r.title,
                    source="ai",
                    score=r.score,
                    reason=r.reason,
                    review_state="pending",  # Sprint 1/T4: must be reviewed before render
                ))
            s.commit()

        ctx.update(1.0, f"Selesai — {len(results)} klip ditemukan", force=True)
        _notify_project(project_id)
    return run


@router.post("/projects/{project_id}/highlight")
def start_highlight(project_id: int, body: HighlightIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    p = _project_or_404(s, project_id)
    v = s.get(Video, p.video_id)
    t = transcriber.load_transcript(downloader.video_dir(v.youtube_id)) if v else None
    if not t:
        raise HTTPException(400, "Jalankan transkripsi terlebih dahulu")
        
    settings_dict = {
        "provider": body.provider,
        "ollama_url": settings.ollama_url,
        "ollama_model": body.model or settings.ollama_model,
        "openai_base_url": settings.openai_base_url,
        "openai_api_key": settings.openai_api_key,
        "openai_model": body.model or settings.openai_model,
        "max_clips": body.max_clips,
        "target_durations": body.target_durations,
        "min_score": body.min_score,
    }
    
    job = enqueue(Job(project_id=p.id, type="highlight"), _highlight_job(p.id, settings_dict))
    return job.model_dump(mode="json")


@router.get("/highlight/status")
def highlight_status() -> dict[str, Any]:
    return {
        "ollama": highlighter.check_ollama(settings.ollama_url),
        "openai": {"configured": bool(settings.openai_api_key)},
        "default_provider": settings.highlight_provider
    }


@router.put("/settings/highlight")
def update_highlight_settings(body: HighlightSettingsIn) -> dict[str, Any]:
    # Saving to a JSON file at storage/highlight_settings.json
    path = settings.storage_dir / "highlight_settings.json"
    
    current = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    updates = body.model_dump(exclude_unset=True)
    current.update(updates)
    
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    
    # Also update in-memory settings instance for immediate effect
    for k, v in updates.items():
        if hasattr(settings, k) and v is not None:
            setattr(settings, k, v)
            
    return current


@router.get("/settings/highlight")
def get_highlight_settings() -> dict[str, Any]:
    path = settings.storage_dir / "highlight_settings.json"
    current = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    return {
        "provider": current.get("provider", settings.highlight_provider),
        "ollama_model": current.get("ollama_model", settings.ollama_model),
        "ollama_url": current.get("ollama_url", settings.ollama_url),
        "openai_base_url": current.get("openai_base_url", settings.openai_base_url),
        "openai_api_key": current.get("openai_api_key", settings.openai_api_key),
        "openai_model": current.get("openai_model", settings.openai_model),
    }

# ---------- local file import (Phase 5) ----------

@router.post("/projects/import-local")
def import_local(body: LocalFileIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    """Create a project from a local video file (not YouTube)."""
    src = Path(body.path)
    if not src.exists():
        raise HTTPException(400, f"File tidak ditemukan: {body.path}")
    if not src.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts"):
        raise HTTPException(400, "Format file tidak didukung. Gunakan MP4, MKV, WEBM, AVI, MOV.")

    # Generate a unique ID for local files
    import hashlib
    file_hash = hashlib.md5(str(src.resolve()).encode()).hexdigest()[:11]
    local_id = f"local_{file_hash}"

    video = s.exec(select(Video).where(Video.youtube_id == local_id)).first()
    if not video:
        # Probe the video for duration
        try:
            info = renderer.probe(src)
            dur = info.get("duration", 0)
        except Exception:
            dur = 0.0

        # Copy file to storage
        dest_dir = settings.videos_dir / local_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"source{src.suffix}"
        if not dest.exists():
            shutil.copy2(str(src), str(dest))

        video = Video(
            youtube_id=local_id,
            url=f"file:///{src.resolve().as_posix()}",
            title=body.title or src.stem,
            channel="Local",
            duration=dur,
            path=str(dest),
        )
        s.add(video)
        s.commit()
        s.refresh(video)

    project = Project(
        video_id=video.id,
        name=video.title,
        language=body.language,
        status="ready",
    )
    s.add(project)
    s.commit()
    s.refresh(project)
    return project.model_dump(mode="json") | {"video": video_out(video)}


# ---------- generate title / hashtags (Phase 5) ----------

@router.post("/clips/{clip_id}/generate-meta")
def generate_clip_meta(clip_id: int, body: GenerateMetaIn,
                       s: Session = Depends(get_session)) -> dict[str, Any]:
    """Use LLM to generate a catchy title, description, and hashtags for a clip."""
    c = s.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, "Clip not found")
    p = s.get(Project, c.project_id)
    v = s.get(Video, p.video_id) if p else None
    if not v:
        raise HTTPException(404, "Video not found")

    # Get transcript for the clip's time range
    transcript = transcriber.load_transcript(downloader.video_dir(v.youtube_id))
    clip_text = ""
    if transcript:
        for seg in transcript.get("segments", []):
            if seg["end"] > c.start and seg["start"] < c.end:
                clip_text += seg["text"] + " "
    clip_text = clip_text.strip()
    if not clip_text:
        raise HTTPException(400, "Tidak ada transkrip untuk klip ini — jalankan transkripsi dulu")

    prompt = f"""Generate metadata for a short-form video clip. The clip is from a video titled "{v.title}".

Clip transcript:
{clip_text[:2000]}

Generate a response with ONLY this JSON:
{{
  "title": "A catchy, engaging title for the clip (max 60 chars)",
  "description": "A brief description for the clip (max 150 chars)",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3", "hashtag4", "hashtag5"]
}}

The title and description should be in the same language as the transcript.
Make it catchy and optimized for YouTube Shorts / TikTok."""

    hl_settings = highlighter.HighlightSettings(
        provider=body.provider,
        ollama_model=body.model or settings.ollama_model,
        ollama_url=settings.ollama_url,
        openai_base_url=settings.openai_base_url,
        openai_api_key=settings.openai_api_key,
        openai_model=body.model or settings.openai_model,
    )

    try:
        result = highlighter.call_llm(prompt, hl_settings)
        if isinstance(result, list) and result:
            meta = result[0]
        elif isinstance(result, dict):
            meta = result
        else:
            # Try to parse as a single object
            raw = highlighter.call_llm(prompt, hl_settings)
            meta = raw[0] if isinstance(raw, list) and raw else {}
    except Exception as exc:
        raise HTTPException(502, f"LLM error: {exc}") from exc

    return {
        "title": meta.get("title", c.title),
        "description": meta.get("description", ""),
        "hashtags": meta.get("hashtags", []),
    }


# ---------- presets (Phase 5) ----------

@router.get("/presets")
def list_presets() -> list[dict[str, Any]]:
    path = settings.storage_dir / "presets.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


@router.post("/presets")
def save_preset(body: dict[str, Any]) -> list[dict[str, Any]]:
    path = settings.storage_dir / "presets.json"
    presets = list_presets()
    import time
    body["id"] = f"preset_{int(time.time())}"
    presets.append(body)
    path.write_text(json.dumps(presets, indent=2), encoding="utf-8")
    return presets


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: str) -> list[dict[str, Any]]:
    path = settings.storage_dir / "presets.json"
    presets = [p for p in list_presets() if p.get("id") != preset_id]
    path.write_text(json.dumps(presets, indent=2), encoding="utf-8")
    return presets


# ---------- jobs & realtime ----------

@router.get("/jobs")
def list_jobs(project_id: Optional[int] = None, s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    q = select(Job).order_by(col(Job.id).desc()).limit(100)
    if project_id is not None:
        q = q.where(Job.project_id == project_id)
    return [j.model_dump(mode="json") for j in s.exec(q).all()]


@router.websocket("/ws")
async def ws_events(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive / ignore client messages
    except WebSocketDisconnect:
        hub.disconnect(ws)
