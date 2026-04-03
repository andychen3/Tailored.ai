from __future__ import annotations

from app.services.chat_store import ChatMessageRecord, ChatThread


def _to_iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def serialize_thread(thread: ChatThread) -> dict[str, object]:
    return {
        "session_id": thread.session_id,
        "user_id": thread.user_id,
        "title": thread.title,
        "model": thread.model,
        "created_at": _to_iso(thread.created_at),
        "updated_at": _to_iso(thread.updated_at),
        "last_message_at": _to_iso(thread.last_message_at),
        "message_count": thread.message_count,
        "prompt_tokens_total": thread.prompt_tokens_total,
        "completion_tokens_total": thread.completion_tokens_total,
        "total_tokens_total": thread.total_tokens_total,
    }


def serialize_usage(message: ChatMessageRecord) -> dict[str, int] | None:
    if message.total_tokens is None:
        return None
    return {
        "prompt_tokens": message.prompt_tokens or 0,
        "completion_tokens": message.completion_tokens or 0,
        "total_tokens": message.total_tokens,
    }


def serialize_message(message: ChatMessageRecord) -> dict[str, object]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "created_at": _to_iso(message.created_at),
        "usage": serialize_usage(message),
    }


def serialize_source_entry(
    *,
    message: ChatMessageRecord,
    source: dict,
) -> dict[str, object]:
    return {
        "message_id": message.id,
        "role": message.role,
        "created_at": _to_iso(message.created_at),
        "title": source.get("title", ""),
        "timestamp": source.get("timestamp"),
        "url": source.get("url"),
        "video_id": source.get("video_id"),
        "page_number": source.get("page_number"),
    }
