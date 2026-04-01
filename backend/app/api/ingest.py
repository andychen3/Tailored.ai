import os
import shutil
import tempfile
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.core.config import settings
from app.schemas.ingest import (
    IngestFileQueuedResponse,
    IngestJobResponse,
    IngestSourceType,
    IngestYoutubeRequest,
    IngestYoutubeResponse,
    UploadChunkResponse,
    UploadCompleteResponse,
)
from app.services.ingest_job_store import (
    IngestJob,
    IngestJobResult,
    IngestJobStore,
    ingest_job_store,
)

if TYPE_CHECKING:
    from app.rag.retriever import RAGRetriever

router = APIRouter()

ALLOWED_EXTENSIONS: dict[str, IngestSourceType] = {
    ".mp4": "video_file",
    ".mov": "video_file",
    ".avi": "video_file",
    ".pdf": "pdf",
    ".txt": "text",
}
UPLOAD_CHUNK_BYTES = 1024 * 1024
CONTENT_LENGTH_GRACE_BYTES = 1024 * 1024


@lru_cache(maxsize=1)
def get_retriever() -> "RAGRetriever":
    from app.rag.retriever import RAGRetriever

    return RAGRetriever()


def get_ingest_job_store() -> IngestJobStore:
    return ingest_job_store


def _process_ingest_job(job: IngestJob) -> IngestJobResult:
    retriever = get_retriever()
    chunk_count, file_id, display_name = retriever.ingest_file(
        user_id=job.user_id,
        file_path=job.staged_path,
        filename=job.file_name,
        source_type=job.source_type,
    )
    return IngestJobResult(
        file_id=file_id,
        file_name=display_name,
        chunks_ingested=chunk_count,
    )


def _max_upload_detail() -> str:
    if settings.max_file_bytes >= 1024 * 1024:
        size = f"{settings.max_file_bytes // (1024 * 1024)} MB"
    elif settings.max_file_bytes >= 1024:
        size = f"{settings.max_file_bytes // 1024} KB"
    else:
        size = f"{settings.max_file_bytes} bytes"
    return f"File exceeds the maximum upload size of {size}."


def _parse_content_length(request: Request) -> int | None:
    raw_value = request.headers.get("content-length")
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def _build_job_response(job: IngestJob) -> IngestJobResponse:
    return IngestJobResponse(
        success=job.status != "error",
        job_id=job.job_id,
        file_name=job.file_name,
        source_type=job.source_type,
        status=job.status,
        file_id=job.file_id,
        chunks_ingested=job.chunks_ingested,
        error_message=job.error_message,
    )


async def _stage_upload(file: UploadFile, ext: str) -> str:
    os.makedirs(settings.upload_staging_dir, exist_ok=True)

    staged_path = None
    bytes_written = 0
    try:
        with tempfile.NamedTemporaryFile(
            dir=settings.upload_staging_dir,
            prefix="ingest_",
            suffix=ext,
            delete=False,
        ) as tmp:
            staged_path = tmp.name
            while True:
                chunk = await file.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > settings.max_file_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=_max_upload_detail(),
                    )
                tmp.write(chunk)
        return staged_path
    except Exception:
        if staged_path and os.path.exists(staged_path):
            os.unlink(staged_path)
        raise


ingest_job_store.set_processor(_process_ingest_job)


@router.post("/youtube", response_model=IngestYoutubeResponse)
def ingest_youtube(
    payload: IngestYoutubeRequest,
    retriever: "RAGRetriever" = Depends(get_retriever),
) -> IngestYoutubeResponse:
    source_url = str(payload.url)
    video_id = retriever.ingester.get_video_id(source_url)
    if not video_id:
        raise HTTPException(
            status_code=400,
            detail="Could not extract YouTube video ID.",
        )

    try:
        chunk_count, video_title = retriever.ingest_youtube_url(
            user_id=payload.user_id,
            url=source_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Ingestion failed: {exc}"
        ) from exc

    return IngestYoutubeResponse(
        success=True,
        video_id=video_id,
        video_title=video_title,
        chunks_ingested=chunk_count,
    )


@router.post(
    "/file",
    response_model=IngestFileQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_file(
    request: Request,
    user_id: str = Form(...),
    file: UploadFile = File(...),
    store: IngestJobStore = Depends(get_ingest_job_store),
) -> IngestFileQueuedResponse:
    if not user_id.strip():
        raise HTTPException(status_code=400, detail="Missing user_id.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file.")

    content_length = _parse_content_length(request)
    if content_length is not None and content_length > settings.max_file_bytes + CONTENT_LENGTH_GRACE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=_max_upload_detail(),
        )

    ext = os.path.splitext(file.filename)[1].lower()
    source_type = ALLOWED_EXTENSIONS.get(ext)
    if not source_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: '{ext}'. "
            f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    if file.size is not None and file.size > settings.max_file_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=_max_upload_detail(),
        )

    staged_path = None
    try:
        staged_path = await _stage_upload(file, ext)
        job = store.create_job(
            user_id=user_id.strip(),
            file_name=file.filename,
            source_type=source_type,
            staged_path=staged_path,
        )
        store.queue_job(job.job_id)
        staged_path = None
    except HTTPException:
        if staged_path and os.path.exists(staged_path):
            os.unlink(staged_path)
        raise
    except Exception as exc:
        if staged_path and os.path.exists(staged_path):
            os.unlink(staged_path)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue ingestion: {exc}",
        ) from exc
    finally:
        await file.close()

    return IngestFileQueuedResponse(
        success=True,
        job_id=job.job_id,
        file_name=job.file_name,
        source_type=source_type,
        status="queued",
    )


@router.post("/upload-chunk", response_model=UploadChunkResponse)
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
) -> UploadChunkResponse:
    """Receive one chunk of a multi-part file upload and write it to disk."""
    chunk_dir = os.path.join(settings.upload_staging_dir, "chunks", upload_id)
    os.makedirs(chunk_dir, exist_ok=True)
    chunk_path = os.path.join(chunk_dir, f"{chunk_index:05d}")
    try:
        with open(chunk_path, "wb") as f:
            while True:
                data = await chunk.read(UPLOAD_CHUNK_BYTES)
                if not data:
                    break
                f.write(data)
    finally:
        await chunk.close()

    return UploadChunkResponse(
        upload_id=upload_id,
        chunk_index=chunk_index,
        received=True,
    )


@router.post(
    "/upload-complete",
    response_model=UploadCompleteResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_complete(
    upload_id: str = Form(...),
    file_name: str = Form(...),
    total_chunks: int = Form(...),
    user_id: str = Form(...),
    store: IngestJobStore = Depends(get_ingest_job_store),
) -> UploadCompleteResponse:
    """Reassemble uploaded chunks into a single file and queue an ingest job."""
    if not user_id.strip():
        raise HTTPException(status_code=400, detail="Missing user_id.")

    ext = os.path.splitext(file_name)[1].lower()
    source_type = ALLOWED_EXTENSIONS.get(ext)
    if not source_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: '{ext}'. "
            f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    chunk_dir = os.path.join(settings.upload_staging_dir, "chunks", upload_id)
    for i in range(total_chunks):
        if not os.path.exists(os.path.join(chunk_dir, f"{i:05d}")):
            raise HTTPException(
                status_code=400,
                detail=f"Missing chunk {i}. Upload may be incomplete.",
            )

    os.makedirs(settings.upload_staging_dir, exist_ok=True)
    staged_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=settings.upload_staging_dir,
            prefix="ingest_",
            suffix=ext,
            delete=False,
        ) as tmp:
            staged_path = tmp.name
            bytes_written = 0
            for i in range(total_chunks):
                chunk_path = os.path.join(chunk_dir, f"{i:05d}")
                with open(chunk_path, "rb") as cf:
                    while True:
                        data = cf.read(UPLOAD_CHUNK_BYTES)
                        if not data:
                            break
                        bytes_written += len(data)
                        if bytes_written > settings.max_file_bytes:
                            raise HTTPException(
                                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                                detail=_max_upload_detail(),
                            )
                        tmp.write(data)

        job = store.create_job(
            user_id=user_id.strip(),
            file_name=file_name,
            source_type=source_type,
            staged_path=staged_path,
        )
        store.queue_job(job.job_id)
        staged_path = None
    except HTTPException:
        if staged_path and os.path.exists(staged_path):
            os.unlink(staged_path)
        raise
    except Exception as exc:
        if staged_path and os.path.exists(staged_path):
            os.unlink(staged_path)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to assemble upload: {exc}",
        ) from exc
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)

    return UploadCompleteResponse(
        success=True,
        job_id=job.job_id,
        file_name=job.file_name,
        source_type=source_type,
        status="queued",
    )


@router.get("/jobs/{job_id}", response_model=IngestJobResponse)
def get_ingest_job(
    job_id: str,
    store: IngestJobStore = Depends(get_ingest_job_store),
) -> IngestJobResponse:
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingest job not found.")
    return _build_job_response(job)
