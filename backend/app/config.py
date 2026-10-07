"""Application configuration & paths."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]  # d:\LEARN\clip
BACKEND_DIR = ROOT_DIR / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_prefix="CLIP_", extra="ignore")

    storage_dir: Path = ROOT_DIR / "storage"
    tools_dir: Path = ROOT_DIR / "tools"
    db_path: Path = ROOT_DIR / "storage" / "clip.db"

    # yt-dlp needs an external JS runtime for YouTube. Node is already installed here.
    js_runtime: str = "node"
    cookies_file: Path | None = None

    # Rendering defaults (Phase 1+)
    video_encoder: str = "h264_amf"  # or "libx264"

    # CORS for the Vite dev server
    frontend_origin: str = "http://localhost:5173"

    # AI highlight (Phase 3)
    highlight_provider: str = "ollama"  # "ollama" | "openai"
    ollama_model: str = "qwen2.5:3b"
    ollama_url: str = "http://localhost:11434"
    openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    openai_api_key: str = ""
    openai_model: str = "gemini-2.0-flash"

    @property
    def videos_dir(self) -> Path:
        return self.storage_dir / "videos"

    @property
    def exports_dir(self) -> Path:
        return self.storage_dir / "exports"

    @property
    def ffmpeg_bin_dir(self) -> Path:
        return self.tools_dir / "ffmpeg" / "bin"


settings = Settings()


def bootstrap() -> None:
    """Create folders and put portable FFmpeg on PATH for this process."""
    for d in (settings.storage_dir, settings.videos_dir, settings.exports_dir):
        d.mkdir(parents=True, exist_ok=True)
    if settings.ffmpeg_bin_dir.exists():
        os.environ["PATH"] = str(settings.ffmpeg_bin_dir) + os.pathsep + os.environ.get("PATH", "")
