from __future__ import annotations

import os
import tempfile
import time

from fastapi.testclient import TestClient

from app.api.ingest import get_ingest_job_store, get_retriever
from app.main import app
from app.services.ingest_job_store import IngestJob, IngestJobResult, IngestJobStore


class FakeIngester:
    def get_video_id(self, url: str) -> str:
        return "abc123"


class FakeRetriever:
    def __init__(self) -> None:
        self.ingester = FakeIngester()

    def ingest_youtube_url(self, user_id: str, url: str) -> tuple[int, str, str]:
        return 4, "Test Video", "source_youtube_1"


def test_ingest_youtube() -> None:
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever()
    client = TestClient(app)

    response = client.post(
        "/ingest/youtube",
        json={
            "user_id": "user_1",
            "url": "https://www.youtube.com/watch?v=abc123",
            "video_title": "Test Video",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "video_id": "abc123",
        "video_title": "Test Video",
        "chunks_ingested": 4,
    }


def _wait_for_job(client: TestClient, job_id: str) -> dict:
    deadline = time.time() + 2
    while time.time() < deadline:
        response = client.get(f"/ingest/jobs/{job_id}")
        payload = response.json()
        if payload["status"] in {"ready", "error"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for ingest job to finish.")


def test_ingest_file_returns_202_and_job_ready() -> None:
    def processor(job: IngestJob) -> IngestJobResult:
        return IngestJobResult(
            source_id="source_file_1",
            file_id="demo_file_1234",
            file_name=job.file_name,
            chunks_ingested=7,
        )

    store = IngestJobStore(processor=processor)
    app.dependency_overrides[get_ingest_job_store] = lambda: store
    client = TestClient(app)

    response = client.post(
        "/ingest/file",
        data={"user_id": "user_1"},
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 202
    queued = response.json()
    assert queued == {
        "success": True,
        "job_id": queued["job_id"],
        "file_name": "notes.txt",
        "source_type": "text",
        "status": "queued",
    }

    job = _wait_for_job(client, queued["job_id"])

    app.dependency_overrides.clear()

    assert job == {
        "success": True,
        "job_id": queued["job_id"],
        "file_name": "notes.txt",
        "source_type": "text",
        "status": "ready",
        "file_id": "demo_file_1234",
        "chunks_ingested": 7,
        "error_message": None,
    }


def test_ingest_file_rejects_unsupported_extension() -> None:
    client = TestClient(app)

    response = client.post(
        "/ingest/file",
        data={"user_id": "user_1"},
        files={"file": ("notes.docx", b"hello world", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_ingest_file_rejects_oversized_upload(monkeypatch) -> None:
    temp_dir = tempfile.mkdtemp()
    monkeypatch.setattr("app.api.ingest.settings.max_file_bytes", 4)
    monkeypatch.setattr("app.api.ingest.settings.upload_staging_dir", temp_dir)

    client = TestClient(app)
    response = client.post(
        "/ingest/file",
        data={"user_id": "user_1"},
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "File exceeds the maximum upload size of 4 bytes."
    assert os.listdir(temp_dir) == []


def test_get_ingest_job_returns_404_for_unknown_job() -> None:
    client = TestClient(app)

    response = client.get("/ingest/jobs/does-not-exist")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingest job not found."


def test_ingest_file_job_failure_surfaces_error() -> None:
    def processor(job: IngestJob) -> IngestJobResult:
        raise ValueError(f"Could not process {job.file_name}")

    store = IngestJobStore(processor=processor)
    app.dependency_overrides[get_ingest_job_store] = lambda: store
    client = TestClient(app)

    response = client.post(
        "/ingest/file",
        data={"user_id": "user_1"},
        files={"file": ("clip.mp4", b"video-bytes", "video/mp4")},
    )

    assert response.status_code == 202
    queued = response.json()

    job = _wait_for_job(client, queued["job_id"])

    app.dependency_overrides.clear()

    assert job == {
        "success": False,
        "job_id": queued["job_id"],
        "file_name": "clip.mp4",
        "source_type": "video_file",
        "status": "error",
        "file_id": None,
        "chunks_ingested": None,
        "error_message": "Could not process clip.mp4",
    }
