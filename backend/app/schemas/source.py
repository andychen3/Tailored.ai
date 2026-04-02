from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SourceType = Literal["youtube", "video_file", "pdf", "text"]
SourceSyncStatus = Literal["in_sync", "missing", "unknown"]


class SourceListItem(BaseModel):
    source_id: str
    user_id: str
    source_type: SourceType
    title: str
    source_url: str | None = None
    video_id: str | None = None
    file_id: str | None = None
    expected_chunk_count: int
    sync_status: SourceSyncStatus
    last_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SourceListResponse(BaseModel):
    sources: list[SourceListItem]
