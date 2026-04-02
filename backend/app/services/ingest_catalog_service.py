from app.services.source_catalog_store import source_catalog_store


def upsert_ready_source(
    *,
    source_id: str,
    user_id: str,
    source_type: str,
    title: str,
    source_url: str | None,
    video_id: str | None,
    file_id: str | None,
    expected_chunk_count: int,
) -> None:
    source_catalog_store.upsert_ready_source(
        source_id=source_id,
        user_id=user_id,
        source_type=source_type,
        title=title,
        source_url=source_url,
        video_id=video_id,
        file_id=file_id,
        expected_chunk_count=expected_chunk_count,
    )
