from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from app.chat.chat_manager import ChatManager


@dataclass
class Session:
    user_id: str
    manager: "ChatManager"
    created_at: datetime
    last_seen_at: datetime


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def create_session(self, user_id: str, model: str = "gpt-4o-mini") -> str:
        from app.chat.chat_manager import ChatManager

        session_id = uuid4().hex
        now = datetime.now(UTC)
        manager = ChatManager(model=model, user_id=user_id)
        session = Session(
            user_id=user_id,
            manager=manager,
            created_at=now,
            last_seen_at=now,
        )
        with self._lock:
            self._sessions[session_id] = session
        return session_id

    def get_manager(self, session_id: str) -> "ChatManager | None":
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.manager

    def touch(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_seen_at = datetime.now(UTC)


session_store = SessionStore()
