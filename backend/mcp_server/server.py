from __future__ import annotations

from typing import Any

from app.services.chat_store import ChatStore

from .config import DEFAULT_TOOL_LIMIT, MAX_TOOL_LIMIT, SERVER_NAME, settings
from .serializers import serialize_message, serialize_source_entry, serialize_thread

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised manually once dependency is installed.
    FastMCP = None


def _error(code: str, message: str) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
        }
    }


def _validate_non_empty(value: str, *, field_name: str) -> str | None:
    cleaned = value.strip()
    if cleaned:
        return cleaned
    return None


def _normalize_limit(limit: int) -> int | None:
    if limit < 1:
        return None
    return min(limit, MAX_TOOL_LIMIT)


def list_threads_tool(
    store: ChatStore,
    *,
    user_id: str,
    limit: int = DEFAULT_TOOL_LIMIT,
) -> dict[str, object]:
    cleaned_user_id = _validate_non_empty(user_id, field_name="user_id")
    if cleaned_user_id is None:
        return _error("missing_user_id", "Missing user_id.")

    normalized_limit = _normalize_limit(limit)
    if normalized_limit is None:
        return _error("invalid_limit", "limit must be an integer greater than 0.")

    threads = store.list_sessions(cleaned_user_id)[:normalized_limit]
    return {"threads": [serialize_thread(thread) for thread in threads]}


def get_thread_tool(store: ChatStore, *, session_id: str) -> dict[str, object]:
    cleaned_session_id = _validate_non_empty(session_id, field_name="session_id")
    if cleaned_session_id is None:
        return _error("missing_session_id", "Missing session_id.")

    thread = store.get_session(cleaned_session_id)
    if thread is None:
        return _error("session_not_found", f"Session '{cleaned_session_id}' was not found.")

    return {"thread": serialize_thread(thread)}


def get_thread_messages_tool(
    store: ChatStore,
    *,
    session_id: str,
    limit: int = DEFAULT_TOOL_LIMIT,
) -> dict[str, object]:
    cleaned_session_id = _validate_non_empty(session_id, field_name="session_id")
    if cleaned_session_id is None:
        return _error("missing_session_id", "Missing session_id.")

    normalized_limit = _normalize_limit(limit)
    if normalized_limit is None:
        return _error("invalid_limit", "limit must be an integer greater than 0.")

    thread = store.get_session(cleaned_session_id)
    if thread is None:
        return _error("session_not_found", f"Session '{cleaned_session_id}' was not found.")

    messages = store.list_messages(cleaned_session_id)
    selected_messages = messages[-normalized_limit:]
    return {
        "session_id": thread.session_id,
        "messages": [serialize_message(message) for message in selected_messages],
    }


def get_thread_sources_tool(store: ChatStore, *, session_id: str) -> dict[str, object]:
    cleaned_session_id = _validate_non_empty(session_id, field_name="session_id")
    if cleaned_session_id is None:
        return _error("missing_session_id", "Missing session_id.")

    thread = store.get_session(cleaned_session_id)
    if thread is None:
        return _error("session_not_found", f"Session '{cleaned_session_id}' was not found.")

    messages = store.list_messages(cleaned_session_id)
    flattened_sources: list[dict[str, Any]] = []
    for message in messages:
        for source in message.sources:
            flattened_sources.append(
                serialize_source_entry(message=message, source=source)
            )

    return {
        "session_id": thread.session_id,
        "sources": flattened_sources,
    }


def create_mcp_server(store: ChatStore | None = None):
    if FastMCP is None:
        raise RuntimeError(
            "The 'mcp' package is not installed. Run 'poetry install' in backend/ first."
        )

    chat_store = store or ChatStore(settings.chat_db_path)
    mcp = FastMCP(
        SERVER_NAME,
        instructions=(
            "Read-only access to Tailored.ai chat threads, messages, and cited sources. "
            "Use these tools to inspect existing conversations without mutating app state."
        ),
        json_response=True,
    )

    @mcp.tool()
    def list_threads(user_id: str, limit: int = DEFAULT_TOOL_LIMIT) -> dict[str, object]:
        """List recent chat threads for a user."""
        return list_threads_tool(chat_store, user_id=user_id, limit=limit)

    @mcp.tool()
    def get_thread(session_id: str) -> dict[str, object]:
        """Get thread metadata and token totals for one chat session."""
        return get_thread_tool(chat_store, session_id=session_id)

    @mcp.tool()
    def get_thread_messages(
        session_id: str,
        limit: int = DEFAULT_TOOL_LIMIT,
    ) -> dict[str, object]:
        """Get chronological messages for one chat session."""
        return get_thread_messages_tool(chat_store, session_id=session_id, limit=limit)

    @mcp.tool()
    def get_thread_sources(session_id: str) -> dict[str, object]:
        """Get flattened cited sources for one chat session."""
        return get_thread_sources_tool(chat_store, session_id=session_id)

    return mcp


def main() -> None:
    create_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
