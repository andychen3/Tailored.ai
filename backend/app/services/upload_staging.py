import os
import shutil
import tempfile

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

UPLOAD_CHUNK_BYTES = 1024 * 1024


def chunk_dir_for(upload_id: str) -> str:
    return os.path.join(settings.upload_staging_dir, "chunks", upload_id)


def ensure_allowed_upload_size(
    *,
    bytes_written: int,
    max_upload_detail,
) -> None:
    if bytes_written > settings.max_file_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=max_upload_detail(),
        )


async def stage_upload(file: UploadFile, ext: str, *, max_upload_detail) -> str:
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
                ensure_allowed_upload_size(
                    bytes_written=bytes_written,
                    max_upload_detail=max_upload_detail,
                )
                tmp.write(chunk)
        return staged_path
    except Exception:
        cleanup_file(staged_path)
        raise


async def write_upload_chunk(
    *,
    upload_id: str,
    chunk_index: int,
    chunk: UploadFile,
) -> None:
    chunk_dir = chunk_dir_for(upload_id)
    os.makedirs(chunk_dir, exist_ok=True)
    chunk_path = os.path.join(chunk_dir, f"{chunk_index:05d}")
    try:
        with open(chunk_path, "wb") as file_handle:
            while True:
                data = await chunk.read(UPLOAD_CHUNK_BYTES)
                if not data:
                    break
                file_handle.write(data)
    finally:
        await chunk.close()


def validate_chunk_set(*, upload_id: str, total_chunks: int) -> str:
    chunk_dir = chunk_dir_for(upload_id)
    for index in range(total_chunks):
        if not os.path.exists(os.path.join(chunk_dir, f"{index:05d}")):
            raise HTTPException(
                status_code=400,
                detail=f"Missing chunk {index}. Upload may be incomplete.",
            )
    return chunk_dir


def assemble_chunks(
    *,
    upload_id: str,
    total_chunks: int,
    ext: str,
    max_upload_detail,
) -> str:
    chunk_dir = validate_chunk_set(upload_id=upload_id, total_chunks=total_chunks)
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
            for index in range(total_chunks):
                chunk_path = os.path.join(chunk_dir, f"{index:05d}")
                with open(chunk_path, "rb") as chunk_file:
                    while True:
                        data = chunk_file.read(UPLOAD_CHUNK_BYTES)
                        if not data:
                            break
                        bytes_written += len(data)
                        ensure_allowed_upload_size(
                            bytes_written=bytes_written,
                            max_upload_detail=max_upload_detail,
                        )
                        tmp.write(data)
        return staged_path
    except Exception:
        cleanup_file(staged_path)
        raise
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)


def cleanup_file(path: str | None) -> None:
    if path and os.path.exists(path):
        os.unlink(path)
