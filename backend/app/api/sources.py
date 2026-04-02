from fastapi import APIRouter, HTTPException, Query

from app.schemas.source import SourceListItem, SourceListResponse
from app.services.source_catalog_store import source_catalog_store

router = APIRouter()


@router.get("", response_model=SourceListResponse)
def list_sources(user_id: str = Query(...)) -> SourceListResponse:
    cleaned_user_id = user_id.strip()
    if not cleaned_user_id:
        raise HTTPException(status_code=400, detail="Missing user_id.")

    sources = source_catalog_store.list_sources(cleaned_user_id)
    return SourceListResponse(
        sources=[
            SourceListItem(
                source_id=source.source_id,
                user_id=source.user_id,
                source_type=source.source_type,
                title=source.title,
                source_url=source.source_url,
                video_id=source.video_id,
                file_id=source.file_id,
                expected_chunk_count=source.expected_chunk_count,
                sync_status=source.sync_status,
                last_verified_at=source.last_verified_at,
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
            for source in sources
        ]
    )
