from typing import Literal

from pydantic import BaseModel, HttpUrl

IngestSourceType = Literal["video_file", "pdf", "text"]
IngestJobStatus = Literal["queued", "processing", "ready", "error"]


class IngestYoutubeRequest(BaseModel):
    user_id: str
    url: HttpUrl


class IngestYoutubeResponse(BaseModel):
    success: bool
    video_id: str
    video_title: str
    chunks_ingested: int


class IngestFileQueuedResponse(BaseModel):
    success: bool
    job_id: str
    file_name: str
    source_type: IngestSourceType
    status: Literal["queued"]


class IngestJobResponse(BaseModel):
    success: bool
    job_id: str
    file_name: str
    source_type: IngestSourceType
    status: IngestJobStatus
    file_id: str | None = None
    chunks_ingested: int | None = None
    error_message: str | None = None


class UploadChunkResponse(BaseModel):
    upload_id: str
    chunk_index: int
    received: bool


class UploadCompleteResponse(BaseModel):
    success: bool
    job_id: str
    file_name: str
    source_type: IngestSourceType
    status: Literal["queued"]
