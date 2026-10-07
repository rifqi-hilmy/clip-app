"""Minimal background job runner (thread pool) with DB-persisted progress."""
from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlmodel import Session

from .db import engine
from .events import hub
from .models import Job

log = logging.getLogger("clip.jobs")

# 1 worker = heavy jobs (download/render) run sequentially; CPU-friendly on a laptop.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clip-job")


class JobContext:
    """Passed to job functions so they can report progress."""

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        self._last_push = 0.0

    def update(self, progress: float | None = None, message: str | None = None, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_push < 0.4:  # throttle DB writes / WS spam
            return
        self._last_push = now
        with Session(engine) as s:
            job = s.get(Job, self.job_id)
            if not job:
                return
            if progress is not None:
                job.progress = max(0.0, min(1.0, progress))
            if message is not None:
                job.message = message
            job.updated_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()
            s.refresh(job)
            hub.publish({"type": "job", "job": job.model_dump(mode="json")})


def _set_status(job_id: int, status: str, *, error: str | None = None, progress: float | None = None) -> None:
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job:
            return
        job.status = status
        job.error = error
        if progress is not None:
            job.progress = progress
        job.updated_at = datetime.now(timezone.utc)
        s.add(job)
        s.commit()
        s.refresh(job)
        hub.publish({"type": "job", "job": job.model_dump(mode="json")})


def enqueue(job: Job, fn: Callable[[JobContext], None]) -> Job:
    """Persist job and schedule fn(ctx) on the worker thread."""
    with Session(engine) as s:
        s.add(job)
        s.commit()
        s.refresh(job)
        job_id = job.id
        hub.publish({"type": "job", "job": job.model_dump(mode="json")})

    def runner() -> None:
        _set_status(job_id, "running")
        try:
            fn(JobContext(job_id))
            _set_status(job_id, "done", progress=1.0)
        except Exception as exc:  # report any failure to the UI
            log.error("Job %s failed: %s", job_id, traceback.format_exc())
            _set_status(job_id, "error", error=str(exc)[:2000])

    _executor.submit(runner)
    return job


def recover_stale_jobs() -> None:
    """Jobs left 'running'/'queued' from a previous run can never finish; mark them failed."""
    from sqlmodel import select

    with Session(engine) as s:
        for job in s.exec(select(Job).where(Job.status.in_(["queued", "running"]))):  # type: ignore[attr-defined]
            job.status = "error"
            job.error = "Interrupted (server restarted)"
            s.add(job)
        s.commit()
