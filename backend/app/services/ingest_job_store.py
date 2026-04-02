from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from queue import Queue
from threading import Lock, Thread
from uuid import uuid4

from app.schemas.ingest import IngestJobStatus, IngestSourceType


@dataclass(slots=True)
class IngestJob:
    job_id: str
    user_id: str
    file_name: str
    source_type: IngestSourceType
    staged_path: str
    status: IngestJobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    file_id: str | None = None
    chunks_ingested: int | None = None


@dataclass(slots=True)
class IngestJobResult:
    source_id: str
    file_id: str
    file_name: str
    chunks_ingested: int


ProcessIngestJob = Callable[[IngestJob], IngestJobResult]


class IngestJobStore:
    def __init__(self, processor: ProcessIngestJob | None = None) -> None:
        self._jobs: dict[str, IngestJob] = {}
        self._lock = Lock()
        self._queue: Queue[str] = Queue()
        self._processor = processor
        self._worker = Thread(
            target=self._run_worker,
            name="ingest-job-worker",
            daemon=True,
        )
        self._worker.start()

    def set_processor(self, processor: ProcessIngestJob) -> None:
        self._processor = processor

    def create_job(
        self,
        *,
        user_id: str,
        file_name: str,
        source_type: IngestSourceType,
        staged_path: str,
    ) -> IngestJob:
        now = datetime.now(UTC)
        job = IngestJob(
            job_id=uuid4().hex,
            user_id=user_id,
            file_name=file_name,
            source_type=source_type,
            staged_path=staged_path,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return replace(job)

    def queue_job(self, job_id: str) -> None:
        if self._processor is None:
            raise RuntimeError("Ingest job processor is not configured.")
        self._queue.put(job_id)

    def get_job(self, job_id: str) -> IngestJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return replace(job) if job else None

    def _run_worker(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                processor = self._processor
                if processor is None:
                    self._mark_error(job_id, "Ingest job processor is not configured.")
                    continue

                job = self._mark_processing(job_id)
                if job is None:
                    continue

                try:
                    result = processor(job)
                except Exception as exc:  # pragma: no cover - safety net
                    self._mark_error(job_id, str(exc) or "Ingestion failed.")
                else:
                    self._mark_ready(job_id, result)
                finally:
                    if os.path.exists(job.staged_path):
                        os.unlink(job.staged_path)
            finally:
                self._queue.task_done()

    def _mark_processing(self, job_id: str) -> IngestJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            now = datetime.now(UTC)
            job.status = "processing"
            job.started_at = now
            job.updated_at = now
            job.error_message = None
            return replace(job)

    def _mark_ready(self, job_id: str, result: IngestJobResult) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            now = datetime.now(UTC)
            job.status = "ready"
            job.file_id = result.file_id
            job.file_name = result.file_name
            job.chunks_ingested = result.chunks_ingested
            job.error_message = None
            job.finished_at = now
            job.updated_at = now

    def _mark_error(self, job_id: str, error_message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            now = datetime.now(UTC)
            job.status = "error"
            job.error_message = error_message
            job.finished_at = now
            job.updated_at = now


ingest_job_store = IngestJobStore()
