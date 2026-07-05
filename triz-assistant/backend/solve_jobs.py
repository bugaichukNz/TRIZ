"""In-memory хранилище асинхронных TRIZ-анализов (POST /solve/jobs)."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

JobStatus = Literal["running", "done", "error"]

FINISHED_JOB_TTL_SECONDS = 3600


@dataclass
class SolveJobRecord:
    job_id: str
    user_id: str
    problem: str
    status: JobStatus = "running"
    progress_pct: int = 0
    stage: str = "Подготовка к анализу"
    result: dict[str, Any] | None = None
    error: str | None = None
    chat_session_id: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class SolveJobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, SolveJobRecord] = {}

    def create(
        self,
        user_id: str,
        problem: str,
        *,
        chat_session_id: str | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._purge_expired_locked()
            self._jobs[job_id] = SolveJobRecord(
                job_id=job_id,
                user_id=user_id,
                problem=problem,
                chat_session_id=chat_session_id,
            )
        return job_id

    def update_progress(self, job_id: str, pct: int, stage: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "running":
                return
            job.progress_pct = max(0, min(100, pct))
            job.stage = stage

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "done"
            job.progress_pct = 100
            job.stage = "Готово"
            job.result = result
            job.finished_at = time.time()

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "error"
            job.error = error
            job.finished_at = time.time()

    def get_for_user(self, job_id: str, user_id: str) -> SolveJobRecord | None:
        with self._lock:
            self._purge_expired_locked()
            job = self._jobs.get(job_id)
            if job is None or job.user_id != user_id:
                return None
            return SolveJobRecord(
                job_id=job.job_id,
                user_id=job.user_id,
                problem=job.problem,
                status=job.status,
                progress_pct=job.progress_pct,
                stage=job.stage,
                result=job.result,
                error=job.error,
                chat_session_id=job.chat_session_id,
                created_at=job.created_at,
                finished_at=job.finished_at,
            )

    def _purge_expired_locked(self) -> None:
        now = time.time()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in ("done", "error")
            and job.finished_at is not None
            and now - job.finished_at > FINISHED_JOB_TTL_SECONDS
        ]
        for job_id in expired:
            del self._jobs[job_id]


solve_jobs = SolveJobStore()
