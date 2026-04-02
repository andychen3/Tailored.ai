import os
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
from app.services.ingest_catalog_service import upsert_ready_source
from app.services.ingest_job_store import (
    IngestJob,
    IngestJobResult,
    IngestJobStore,
    ingest_job_store,
)
from app.services.upload_staging import (
    assemble_chunks,
    cleanup_file,
    stage_upload,
    write_upload_chunk,
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
CONTENT_LENGTH_GRACE_BYTES = 1024 * 1024


@lru_cache(maxsize=1)
def get_retriever() -> "RAGRetriever":
    from app.rag.retriever import RAGRetriever

    return RAGRetriever()


def get_ingest_job_store() -> IngestJobStore:
    return ingest_job_store


def _process_ingest_job(job: IngestJob) -> IngestJobResult:
    retriever = get_retriever()
    chunk_count, file_id, display_name, source_id = retriever.ingest_file(
        user_id=job.user_id,
        file_path=job.staged_path,
        filename=job.file_name,
        source_type=job.source_type,
    )
    upsert_ready_source(
        source_id=source_id,
        user_id=job.user_id,
        source_type=job.source_type,
        title=display_name,
        source_url=None,
        video_id=None,
        file_id=file_id,
        expected_chunk_count=chunk_count,
    )
    return IngestJobResult(
        source_id=source_id,
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
        source_id=job.source_id,
        file_name=job.file_name,
        source_type=job.source_type,
        status=job.status,
        file_id=job.file_id,
        chunks_ingested=job.chunks_ingested,
        error_message=job.error_message,
    )


def _validate_file_request(
    *,
    request: Request,
    user_id: str,
    file: UploadFile,
) -> IngestSourceType:
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
            detail=f"Unsupported file type: '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    if file.size is not None and file.size > settings.max_file_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=_max_upload_detail(),
        )
    return source_type


def _queue_ingest_job(
    *,
    store: IngestJobStore,
    user_id: str,
    file_name: str,
    source_type: IngestSourceType,
    staged_path: str,
):
    job = store.create_job(
        user_id=user_id.strip(),
        file_name=file_name,
        source_type=source_type,
        staged_path=staged_path,
    )
    store.queue_job(job.job_id)
    return job


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
        chunk_count, video_title, source_id = retriever.ingest_youtube_url(
            user_id=payload.user_id,
            url=source_url,
        )
        upsert_ready_source(
            source_id=source_id,
            user_id=payload.user_id,
            source_type="youtube",
            title=video_title,
            source_url=source_url,
            video_id=video_id,
            file_id=None,
            expected_chunk_count=chunk_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Ingestion failed: {exc}"
        ) from exc

    return IngestYoutubeResponse(
        success=True,
        source_id=source_id,
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
    source_type = _validate_file_request(request=request, user_id=user_id, file=file)
    ext = os.path.splitext(file.filename or "")[1].lower()

    staged_path = None
    try:
        staged_path = await stage_upload(file, ext, max_upload_detail=_max_upload_detail)
        job = _queue_ingest_job(
            store=store,
            user_id=user_id,
            file_name=file.filename or "",
            source_type=source_type,
            staged_path=staged_path,
        )
        staged_path = None
    except HTTPException:
        cleanup_file(staged_path)
        raise
    except Exception as exc:
        cleanup_file(staged_path)
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
    await write_upload_chunk(
        upload_id=upload_id,
        chunk_index=chunk_index,
        chunk=chunk,
    )
    return UploadChunkResponse(upload_id=upload_id, chunk_index=chunk_index, received=True)


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
    if not user_id.strip():
        raise HTTPException(status_code=400, detail="Missing user_id.")

    ext = os.path.splitext(file_name)[1].lower()
    source_type = ALLOWED_EXTENSIONS.get(ext)
    if not source_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    staged_path = None
    try:
        staged_path = assemble_chunks(
            upload_id=upload_id,
            total_chunks=total_chunks,
            ext=ext,
            max_upload_detail=_max_upload_detail,
        )
        job = _queue_ingest_job(
            store=store,
            user_id=user_id,
            file_name=file_name,
            source_type=source_type,
            staged_path=staged_path,
        )
        staged_path = None
    except HTTPException:
        cleanup_file(staged_path)
        raise
    except Exception as exc:
        cleanup_file(staged_path)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to assemble upload: {exc}",
        ) from exc

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
