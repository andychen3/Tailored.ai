from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from app.core.config import settings


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class NotionConnection:
    user_id: str
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    client_id: str
    client_secret: str | None
    token_endpoint: str
    authorization_endpoint: str | None
    issuer: str | None
    workspace_id: str | None
    workspace_name: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class PendingChatAction:
    id: str
    user_id: str
    session_id: str
    action_type: str
    original_message: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class OAuthState:
    id: str
    user_id: str
    session_id: str
    pending_action_id: str
    provider: str
    state: str
    code_verifier: str
    redirect_uri: str
    client_id: str
    client_secret: str | None
    token_endpoint: str
    authorization_endpoint: str | None
    issuer: str | None
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None


class IntegrationStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

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

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notion_connections (
                    user_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at TEXT,
                    client_id TEXT NOT NULL DEFAULT '',
                    client_secret TEXT,
                    token_endpoint TEXT NOT NULL DEFAULT '',
                    authorization_endpoint TEXT,
                    issuer TEXT,
                    workspace_id TEXT,
                    workspace_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_chat_actions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    original_message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_states (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    pending_action_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    state TEXT NOT NULL UNIQUE,
                    code_verifier TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    client_id TEXT NOT NULL DEFAULT '',
                    client_secret TEXT,
                    token_endpoint TEXT NOT NULL DEFAULT '',
                    authorization_endpoint TEXT,
                    issuer TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT
                )
                """
            )
            self._ensure_column(conn, "notion_connections", "client_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "notion_connections", "client_secret", "TEXT")
            self._ensure_column(conn, "notion_connections", "token_endpoint", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "notion_connections", "authorization_endpoint", "TEXT")
            self._ensure_column(conn, "notion_connections", "issuer", "TEXT")
            self._ensure_column(conn, "oauth_states", "client_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "oauth_states", "client_secret", "TEXT")
            self._ensure_column(conn, "oauth_states", "token_endpoint", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "oauth_states", "authorization_endpoint", "TEXT")
            self._ensure_column(conn, "oauth_states", "issuer", "TEXT")

    def upsert_notion_connection(
        self,
        *,
        user_id: str,
        access_token: str,
        refresh_token: str | None,
        expires_at: datetime | None,
        client_id: str,
        client_secret: str | None,
        token_endpoint: str,
        authorization_endpoint: str | None,
        issuer: str | None,
        workspace_id: str | None,
        workspace_name: str | None,
    ) -> NotionConnection:
        now = _utc_now_iso()
        created_at = now
        with self._lock:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT created_at FROM notion_connections WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                if existing:
                    created_at = existing["created_at"]
                conn.execute(
                    """
                    INSERT INTO notion_connections (
                        user_id,
                        access_token,
                        refresh_token,
                        expires_at,
                        client_id,
                        client_secret,
                        token_endpoint,
                        authorization_endpoint,
                        issuer,
                        workspace_id,
                        workspace_name,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        access_token = excluded.access_token,
                        refresh_token = excluded.refresh_token,
                        expires_at = excluded.expires_at,
                        client_id = excluded.client_id,
                        client_secret = excluded.client_secret,
                        token_endpoint = excluded.token_endpoint,
                        authorization_endpoint = excluded.authorization_endpoint,
                        issuer = excluded.issuer,
                        workspace_id = excluded.workspace_id,
                        workspace_name = excluded.workspace_name,
                        updated_at = excluded.updated_at
                    """,
                    (
                        user_id,
                        access_token,
                        refresh_token,
                        expires_at.isoformat() if expires_at else None,
                        client_id,
                        client_secret,
                        token_endpoint,
                        authorization_endpoint,
                        issuer,
                        workspace_id,
                        workspace_name,
                        created_at,
                        now,
                    ),
                )
        return self.get_notion_connection(user_id)  # type: ignore[return-value]

    def get_notion_connection(self, user_id: str) -> NotionConnection | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM notion_connections WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return NotionConnection(
            user_id=row["user_id"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            expires_at=_parse_datetime(row["expires_at"]),
            client_id=row["client_id"],
            client_secret=row["client_secret"],
            token_endpoint=row["token_endpoint"],
            authorization_endpoint=row["authorization_endpoint"],
            issuer=row["issuer"],
            workspace_id=row["workspace_id"],
            workspace_name=row["workspace_name"],
            created_at=_parse_datetime(row["created_at"]) or datetime.now(UTC),
            updated_at=_parse_datetime(row["updated_at"]) or datetime.now(UTC),
        )

    def delete_notion_connection(self, user_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                deleted = conn.execute(
                    "DELETE FROM notion_connections WHERE user_id = ?",
                    (user_id,),
                ).rowcount
        return deleted > 0

    def create_pending_action(
        self,
        *,
        user_id: str,
        session_id: str,
        action_type: str,
        original_message: str,
        status: str = "pending",
    ) -> PendingChatAction:
        action_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO pending_chat_actions (
                        id,
                        user_id,
                        session_id,
                        action_type,
                        original_message,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (action_id, user_id, session_id, action_type, original_message, status, now, now),
                )
        return self.get_pending_action(action_id)  # type: ignore[return-value]

    def get_pending_action(self, action_id: str) -> PendingChatAction | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pending_chat_actions WHERE id = ?",
                (action_id,),
            ).fetchone()
        if row is None:
            return None
        return PendingChatAction(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            action_type=row["action_type"],
            original_message=row["original_message"],
            status=row["status"],
            created_at=_parse_datetime(row["created_at"]) or datetime.now(UTC),
            updated_at=_parse_datetime(row["updated_at"]) or datetime.now(UTC),
        )

    def update_pending_action_status(self, action_id: str, status: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE pending_chat_actions
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, _utc_now_iso(), action_id),
                )

    def create_oauth_state(
        self,
        *,
        user_id: str,
        session_id: str,
        pending_action_id: str,
        provider: str,
        state: str,
        code_verifier: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str | None,
        token_endpoint: str,
        authorization_endpoint: str | None,
        issuer: str | None,
        expires_at: datetime,
    ) -> OAuthState:
        state_id = uuid4().hex
        now = _utc_now_iso()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO oauth_states (
                        id,
                        user_id,
                        session_id,
                        pending_action_id,
                        provider,
                        state,
                        code_verifier,
                        redirect_uri,
                        client_id,
                        client_secret,
                        token_endpoint,
                        authorization_endpoint,
                        issuer,
                        created_at,
                        expires_at,
                        consumed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        state_id,
                        user_id,
                        session_id,
                        pending_action_id,
                        provider,
                        state,
                        code_verifier,
                        redirect_uri,
                        client_id,
                        client_secret,
                        token_endpoint,
                        authorization_endpoint,
                        issuer,
                        now,
                        expires_at.isoformat(),
                    ),
                )
        return self.get_oauth_state(state)  # type: ignore[return-value]

    def get_oauth_state(self, state: str) -> OAuthState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM oauth_states WHERE state = ?",
                (state,),
            ).fetchone()
        if row is None:
            return None
        return OAuthState(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            pending_action_id=row["pending_action_id"],
            provider=row["provider"],
            state=row["state"],
            code_verifier=row["code_verifier"],
            redirect_uri=row["redirect_uri"],
            client_id=row["client_id"],
            client_secret=row["client_secret"],
            token_endpoint=row["token_endpoint"],
            authorization_endpoint=row["authorization_endpoint"],
            issuer=row["issuer"],
            created_at=_parse_datetime(row["created_at"]) or datetime.now(UTC),
            expires_at=_parse_datetime(row["expires_at"]) or datetime.now(UTC),
            consumed_at=_parse_datetime(row["consumed_at"]),
        )

    def consume_oauth_state(self, state: str) -> OAuthState | None:
        record = self.get_oauth_state(state)
        if record is None or record.consumed_at is not None:
            return record
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE oauth_states
                    SET consumed_at = ?
                    WHERE state = ? AND consumed_at IS NULL
                    """,
                    (_utc_now_iso(), state),
                )
        return self.get_oauth_state(state)


integration_store = IntegrationStore(settings.integration_db_path)
