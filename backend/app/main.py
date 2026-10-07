"""FastAPI entry point. Run: uvicorn app.main:app --reload --port 8000 (from backend/)."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import bootstrap, settings
from .db import init_db
from .diagnostics import check_tools
from .events import hub
from .jobs import recover_stale_jobs
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Must run before StaticFiles is mounted (it requires the directory to exist).
bootstrap()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    recover_stale_jobs()
    hub.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="YouTube Clipper (local)", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "tools": check_tools()}


app.include_router(router)
# Serves source videos & exports with HTTP Range support (needed for seeking in <video>).
app.mount("/media", StaticFiles(directory=settings.storage_dir), name="media")
