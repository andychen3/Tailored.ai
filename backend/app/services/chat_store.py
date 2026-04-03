from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from app.core.config import settings


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class ChatThread:
    session_id: str
    user_id: str
    title: str
    model: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None
    message_count: int = 0
    prompt_tokens_total: int = 0
    completion_tokens_total: int = 0
    total_tokens_total: int = 0


@dataclass(slots=True)
class ChatMessageRecord:
    id: str
    session_id: str
    role: str
    content: str
    sources: list[dict]
    action: dict | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    created_at: datetime


class ChatStore:
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
                CREATE TABLE IF NOT EXISTS chat_threads (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_message_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_threads_user_last
                ON chat_threads(user_id, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    action_json TEXT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_threads(session_id)
                )
                """
            )
            self._ensure_column(conn, "chat_messages", "prompt_tokens", "INTEGER")
            self._ensure_column(conn, "chat_messages", "completion_tokens", "INTEGER")
            self._ensure_column(conn, "chat_messages", "total_tokens", "INTEGER")
            self._ensure_column(conn, "chat_messages", "action_json", "TEXT")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                ON chat_messages(session_id, created_at ASC)
                """
            )

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(col["name"] == column_name for col in columns):
            return
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )

    def create_session(
        self,
        *,
        user_id: str,
        model: str,
        title: str = "New chat",
    ) -> ChatThread:
        now = _utc_now_iso()
        session_id = uuid4().hex
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO chat_threads (
                        session_id,
                        user_id,
                        title,
                        model,
                        created_at,
                        updated_at,
                        last_message_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (session_id, user_id, title, model, now, now),
                )
        return ChatThread(
            session_id=session_id,
            user_id=user_id,
            title=title,
            model=model,
            created_at=_parse_datetime(now),
            updated_at=_parse_datetime(now),
            last_message_at=None,
            message_count=0,
        )

    def get_session(self, session_id: str) -> ChatThread | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    t.session_id,
                    t.user_id,
                    t.title,
                    t.model,
                    t.created_at,
                    t.updated_at,
                    t.last_message_at,
                    COALESCE(COUNT(m.id), 0) AS message_count,
                    COALESCE(SUM(m.prompt_tokens), 0) AS prompt_tokens_total,
                    COALESCE(SUM(m.completion_tokens), 0) AS completion_tokens_total,
                    COALESCE(SUM(m.total_tokens), 0) AS total_tokens_total
                FROM chat_threads t
                LEFT JOIN chat_messages m ON m.session_id = t.session_id
                WHERE t.session_id = ?
                GROUP BY t.session_id
                """,
                (session_id,),
            ).fetchone()
        return self._row_to_thread(row) if row else None

    def list_sessions(self, user_id: str) -> list[ChatThread]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.session_id,
                    t.user_id,
                    t.title,
                    t.model,
                    t.created_at,
                    t.updated_at,
                    t.last_message_at,
                    COALESCE(COUNT(m.id), 0) AS message_count,
                    COALESCE(SUM(m.prompt_tokens), 0) AS prompt_tokens_total,
                    COALESCE(SUM(m.completion_tokens), 0) AS completion_tokens_total,
                    COALESCE(SUM(m.total_tokens), 0) AS total_tokens_total
                FROM chat_threads t
                LEFT JOIN chat_messages m ON m.session_id = t.session_id
                WHERE t.user_id = ?
                GROUP BY t.session_id
                ORDER BY COALESCE(t.last_message_at, t.created_at) DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_thread(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                thread_deleted = conn.execute(
                    """
                    DELETE FROM chat_threads
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).rowcount
                if thread_deleted == 0:
                    return False
                conn.execute(
                    """
                    DELETE FROM chat_messages
                    WHERE session_id = ?
                    """,
                    (session_id,),
                )
        return True

    def add_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        action: dict | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> ChatMessageRecord:
        now = _utc_now_iso()
        message_id = uuid4().hex
        serialized_sources = json.dumps(sources or [])
        serialized_action = json.dumps(action) if action is not None else None
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO chat_messages (
                        id,
                        session_id,
                        role,
                        content,
                        sources_json,
                        action_json,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        session_id,
                        role,
                        content,
                        serialized_sources,
                        serialized_action,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE chat_threads
                    SET last_message_at = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (now, now, session_id),
                )
        return ChatMessageRecord(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            sources=sources or [],
            action=action,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            created_at=_parse_datetime(now),
        )

    def list_messages(self, session_id: str) -> list[ChatMessageRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    session_id,
                    role,
                    content,
                    sources_json,
                    action_json,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def set_title(self, session_id: str, title: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE chat_threads
                    SET title = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (title, _utc_now_iso(), session_id),
                )

    def _row_to_thread(self, row: sqlite3.Row) -> ChatThread:
        last_message_raw = row["last_message_at"]
        return ChatThread(
            session_id=row["session_id"],
            user_id=row["user_id"],
            title=row["title"],
            model=row["model"],
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
            last_message_at=_parse_datetime(last_message_raw) if last_message_raw else None,
            message_count=int(row["message_count"]),
            prompt_tokens_total=int(row["prompt_tokens_total"]),
            completion_tokens_total=int(row["completion_tokens_total"]),
            total_tokens_total=int(row["total_tokens_total"]),
        )

    def _row_to_message(self, row: sqlite3.Row) -> ChatMessageRecord:
        try:
            sources = json.loads(row["sources_json"]) if row["sources_json"] else []
        except json.JSONDecodeError:
            sources = []
        try:
            action = json.loads(row["action_json"]) if row["action_json"] else None
        except json.JSONDecodeError:
            action = None
        return ChatMessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            sources=sources,
            action=action,
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            created_at=_parse_datetime(row["created_at"]),
        )


chat_store = ChatStore(settings.chat_db_path)
