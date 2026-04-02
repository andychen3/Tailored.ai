import uuid

from app.pinecone_client import index
from app.rag.ingestion.builders import (
    PINECONE_BATCH_SIZE,
    build_file_records,
    build_youtube_records,
)
from app.rag.ingestion.youtube_ingester import YouTubeIngester


class IngestService:
    def __init__(self) -> None:
        self.youtube_ingester = YouTubeIngester()

    def ingest_youtube_url(
        self,
        *,
        user_id: str,
        url: str,
        source_id: str | None = None,
    ) -> tuple[int, str, str]:
        video_info = self.youtube_ingester.get_video_info(url)
        video_title = video_info["title"]
        video_id, transcript = self.youtube_ingester.fetch_transcript(url)
        source_id = source_id or uuid.uuid4().hex
        records = build_youtube_records(
            user_id=user_id,
            source_id=source_id,
            video_id=video_id,
            video_title=video_title,
            transcript=transcript,
        )
        self._upsert_records(records)
        return len(records), video_title, source_id

    def ingest_file(
        self,
        *,
        user_id: str,
        file_path: str,
        filename: str,
        source_type: str,
        source_id: str | None = None,
    ) -> tuple[int, str, str, str]:
        source_id = source_id or uuid.uuid4().hex
        records, file_id = build_file_records(
            user_id=user_id,
            file_path=file_path,
            filename=filename,
            source_type=source_type,
            source_id=source_id,
        )
        self._upsert_records(records)
        return len(records), file_id, filename, source_id

    def _upsert_records(self, records: list[dict]) -> None:
        for start in range(0, len(records), PINECONE_BATCH_SIZE):
            batch = records[start : start + PINECONE_BATCH_SIZE]
            index.upsert_records(namespace="__default__", records=batch)
