"""In-memory прогресс TRIZ-анализа по session_id."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

AnalysisStatus = Literal["idle", "running", "completed", "failed"]


@dataclass
class AnalysisProgressState:
    session_id: str
    progress: int = 0
    stage: str = ""
    status: AnalysisStatus = "idle"
    error: str | None = None


class AnalysisProgressStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, AnalysisProgressState] = {}

    def start(self, session_id: str) -> None:
        with self._lock:
            self._jobs[session_id] = AnalysisProgressState(
                session_id=session_id,
                progress=0,
                stage="Подготовка к анализу",
                status="running",
            )

    def update(self, session_id: str, progress: int, stage: str) -> None:
        with self._lock:
            job = self._jobs.get(session_id)
            if job is None or job.status != "running":
                return
            job.progress = max(0, min(100, progress))
            job.stage = stage

    def complete(self, session_id: str) -> None:
        with self._lock:
            job = self._jobs.get(session_id)
            if job is None:
                return
            job.progress = 100
            job.stage = "Готово"
            job.status = "completed"

    def fail(self, session_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(session_id)
            if job is None:
                return
            job.status = "failed"
            job.error = error

    def get(self, session_id: str) -> AnalysisProgressState | None:
        with self._lock:
            job = self._jobs.get(session_id)
            if job is None:
                return None
            return AnalysisProgressState(
                session_id=job.session_id,
                progress=job.progress,
                stage=job.stage,
                status=job.status,
                error=job.error,
            )

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._jobs.pop(session_id, None)


analysis_progress = AnalysisProgressStore()
