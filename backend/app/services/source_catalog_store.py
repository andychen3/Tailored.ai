from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock, Thread
from typing import Literal

from app.core.config import settings

SourceType = Literal["youtube", "video_file", "pdf", "text"]
SourceStatus = Literal["ready", "error"]
SourceSyncStatus = Literal["in_sync", "missing", "unknown"]


@dataclass(slots=True)
class SourceRecord:
    source_id: str
    user_id: str
    source_type: SourceType
    title: str
    source_url: str | None
    video_id: str | None
    file_id: str | None
    expected_chunk_count: int
    status: SourceStatus
    sync_status: SourceSyncStatus
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class SourceCatalogStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT,
                    video_id TEXT,
                    file_id TEXT,
                    expected_chunk_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    sync_status TEXT NOT NULL,
                    last_verified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sources_user_created
                ON sources(user_id, created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sources_recent
                ON sources(updated_at DESC)
                """
            )

    def upsert_ready_source(
        self,
        *,
        source_id: str,
        user_id: str,
        source_type: SourceType,
        title: str,
        source_url: str | None,
        video_id: str | None,
        file_id: str | None,
        expected_chunk_count: int,
    ) -> None:
        now = _utc_now_iso()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sources (
                        source_id,
                        user_id,
                        source_type,
                        title,
                        source_url,
                        video_id,
                        file_id,
                        expected_chunk_count,
                        status,
                        sync_status,
                        last_verified_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready', 'in_sync', ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        user_id=excluded.user_id,
                        source_type=excluded.source_type,
                        title=excluded.title,
                        source_url=excluded.source_url,
                        video_id=excluded.video_id,
                        file_id=excluded.file_id,
                        expected_chunk_count=excluded.expected_chunk_count,
                        status='ready',
                        sync_status='in_sync',
                        last_verified_at=excluded.last_verified_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        source_id,
                        user_id,
                        source_type,
                        title,
                        source_url,
                        video_id,
                        file_id,
                        expected_chunk_count,
                        now,
                        now,
                        now,
                    ),
                )

    def list_sources(self, user_id: str) -> list[SourceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM sources
                WHERE user_id = ? AND status = 'ready'
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_recent_ready_sources(self, limit: int = 200) -> list[SourceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM sources
                WHERE status = 'ready'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def mark_source_sync_status(
        self,
        source_id: str,
        *,
        sync_status: SourceSyncStatus,
        verified_at: datetime | None = None,
    ) -> None:
        verified_at_iso = (verified_at or datetime.now(UTC)).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE sources
                    SET sync_status = ?,
                        last_verified_at = ?,
                        updated_at = ?
                    WHERE source_id = ?
                    """,
                    (
                        sync_status,
                        verified_at_iso,
                        verified_at_iso,
                        source_id,
                    ),
                )

    def _row_to_record(self, row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            source_id=row["source_id"],
            user_id=row["user_id"],
            source_type=row["source_type"],
            title=row["title"],
            source_url=row["source_url"],
            video_id=row["video_id"],
            file_id=row["file_id"],
            expected_chunk_count=int(row["expected_chunk_count"]),
            status=row["status"],
            sync_status=row["sync_status"],
            last_verified_at=_parse_datetime(row["last_verified_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class SourceReconciler:
    def __init__(self, source_store: SourceCatalogStore) -> None:
        self._source_store = source_store
        self._thread: Thread | None = None
        self._started = False

    def reconcile_once(self, *, limit: int = 200) -> None:
        from app.pinecone_client import index

        sources = self._source_store.list_recent_ready_sources(limit=limit)
        for source in sources:
            sentinel_id = f"{source.source_id}:0"
            sync_status: SourceSyncStatus = "missing"
            try:
                fetched = index.fetch(namespace="__default__", ids=[sentinel_id])
            except Exception:
                sync_status = "unknown"
            else:
                vectors = self._extract_vectors(fetched)
                if sentinel_id in vectors:
                    sync_status = "in_sync"
            self._source_store.mark_source_sync_status(
                source.source_id,
                sync_status=sync_status,
                verified_at=datetime.now(UTC),
            )

    def start_background_reconcile(self, *, interval_seconds: int) -> None:
        if self._started:
            return
        self._started = True

        def _loop() -> None:
            while True:
                try:
                    self.reconcile_once()
                except Exception:
                    pass
                ThreadEvent.sleep(interval_seconds)

        self._thread = Thread(
            target=_loop,
            name="source-reconcile-worker",
            daemon=True,
        )
        self._thread.start()

    def _extract_vectors(self, fetch_result: object) -> dict[str, object]:
        vectors = getattr(fetch_result, "vectors", None)
        if isinstance(vectors, dict):
            return vectors
        if isinstance(fetch_result, dict):
            maybe_vectors = fetch_result.get("vectors")
            if isinstance(maybe_vectors, dict):
                return maybe_vectors
        return {}


class ThreadEvent:
    @staticmethod
    def sleep(seconds: int) -> None:
        import time

        time.sleep(max(seconds, 10))


source_catalog_store = SourceCatalogStore(settings.sources_db_path)
source_reconciler = SourceReconciler(source_catalog_store)
