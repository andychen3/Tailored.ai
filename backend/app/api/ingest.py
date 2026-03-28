from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.ingest import IngestYoutubeRequest, IngestYoutubeResponse

if TYPE_CHECKING:
    from app.rag.retriever import RAGRetriever

router = APIRouter()


@lru_cache(maxsize=1)
def get_retriever() -> "RAGRetriever":
    from app.rag.retriever import RAGRetriever

    return RAGRetriever()


@router.post("/youtube", response_model=IngestYoutubeResponse)
def ingest_youtube(
    payload: IngestYoutubeRequest,
    retriever: "RAGRetriever" = Depends(get_retriever),
) -> IngestYoutubeResponse:
    source_url = str(payload.url)
    video_id = retriever.ingester.get_video_id(source_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Could not extract YouTube video ID.")

    try:
        chunk_count = retriever.ingest_youtube_url(
            user_id=payload.user_id,
            url=source_url,
            video_title=payload.video_title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    return IngestYoutubeResponse(
        success=True,
        video_id=video_id,
        chunks_ingested=chunk_count,
    )
