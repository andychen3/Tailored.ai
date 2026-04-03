from __future__ import annotations

from app.services.chat_store import ChatStore
from mcp_server.server import (
    get_thread_messages_tool,
    get_thread_sources_tool,
    get_thread_tool,
)


class LocalTailoredMCPClient:
    """Thin wrapper around the local read-only thread MCP surface."""

    def __init__(self, store: ChatStore) -> None:
        self._store = store

    def get_thread_bundle(self, session_id: str) -> dict[str, object]:
        thread_payload = get_thread_tool(self._store, session_id=session_id)
        messages_payload = get_thread_messages_tool(self._store, session_id=session_id, limit=200)
        sources_payload = get_thread_sources_tool(self._store, session_id=session_id)
        return {
            "thread": thread_payload.get("thread"),
            "messages": messages_payload.get("messages", []),
            "sources": sources_payload.get("sources", []),
        }
