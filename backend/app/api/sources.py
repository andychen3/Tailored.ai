from fastapi import APIRouter, HTTPException, Query

from app.schemas.source import DeleteSourceResponse, SourceListItem, SourceListResponse
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
                source_type=source.source_type,
                title=source.title,
                source_url=source.source_url,
                video_id=source.video_id,
                file_id=source.file_id,
                expected_chunk_count=source.expected_chunk_count,
                sync_status=source.sync_status,
            )
            for source in sources
        ]
    )


@router.delete("/{source_id}", response_model=DeleteSourceResponse)
def delete_source(source_id: str) -> DeleteSourceResponse:
    source = source_catalog_store.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")

    try:
        from app.pinecone_client import index

        index.delete(
            namespace="__default__",
            filter={"source_id": {"$eq": source_id}},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to delete source embeddings: {exc}",
        ) from exc

    deleted = source_catalog_store.delete_source(source_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete source record.")

    return DeleteSourceResponse(success=True)
