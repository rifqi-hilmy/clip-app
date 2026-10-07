"""Database models (SQLModel / SQLite)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import JSON, Column, Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Video(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    youtube_id: str = Field(index=True, unique=True)
    url: str
    title: str = ""
    channel: str = ""
    duration: float = 0.0
    thumbnail: str = ""
    path: Optional[str] = None  # local source file once downloaded
    heatmap: Optional[list[dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    chapters: Optional[list[dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    name: str = ""
    status: str = "created"  # created | downloading | ready | analyzing | error
    language: Optional[str] = None  # "id" | "en" | None(auto)
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)


class Clip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    start: float
    end: float
    title: str = ""
    score: Optional[float] = None
    reason: str = ""
    source: str = "manual"  # manual | ai
    aspect: str = "9:16"  # 9:16 | original
    reframe: str = "blur"  # blur | center | face
    crop_x: float = 0.5  # horizontal crop center (0..1) for "center" mode
    caption_style: Optional[str] = None
    loudnorm: bool = True  # Sprint 1/T1: loudness normalization on render
    review_state: str = "approved"  # Sprint 1/T4: pending | approved | rejected
    safe_zone: Optional[str] = None  # Sprint 1/T5: tiktok | reels | shorts | None
    remove_silence: bool = False  # Sprint 1/T6
    silence_db: float = -35.0  # Sprint 1/T6
    silence_min_dur: float = 0.8  # Sprint 1/T6
    export_path: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(default=None, foreign_key="project.id", index=True)
    clip_id: Optional[int] = Field(default=None, foreign_key="clip.id")
    type: str  # download | transcribe | highlight | render
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
