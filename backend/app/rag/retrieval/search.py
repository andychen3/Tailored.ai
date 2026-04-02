from typing import Any

from pinecone import SearchQuery

from app.pinecone_client import index


def search_hits(*, user_id: str, question: str, top_k: int) -> list[Any]:
    results = index.search(
        namespace="__default__",
        query=SearchQuery(
            inputs={"text": question},
            top_k=top_k,
            filter={"user_id": {"$eq": user_id}},
        ),
        fields=[
            "chunk_text",
            "video_title",
            "timestamp",
            "user_id",
            "video_id",
            "source_type",
            "file_name",
            "file_id",
            "page_number",
        ],
    )
    return extract_hits(results)


def extract_hits(results: Any) -> list[Any]:
    matches = getattr(results, "matches", None)
    if matches is not None:
        return list(matches)

    search_result = getattr(results, "result", None)
    hits = getattr(search_result, "hits", None) if search_result else None
    if hits is not None:
        return list(hits)

    return []
