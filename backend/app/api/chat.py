import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.chat.constants import NO_CONTEXT_MESSAGE
from app.chat.openai_client import usage_to_dict
from app.core.config import settings
from app.schemas.chat import (
    ChatModelItem,
    ChatModelListResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteSessionResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionMessage,
    SessionSummary,
)
from app.services.chat_store import ChatStore, chat_store

router = APIRouter()


def get_chat_store() -> ChatStore:
    return chat_store


def build_chat_manager(*, model: str, user_id: str):
    from app.chat.chat_manager import ChatManager

    return ChatManager(model=model, user_id=user_id)


def _to_session_summary(session) -> SessionSummary:
    return SessionSummary(
        session_id=session.session_id,
        title=session.title,
        model=session.model,
        created_at=session.created_at,
        prompt_tokens_total=session.prompt_tokens_total,
        completion_tokens_total=session.completion_tokens_total,
        total_tokens_total=session.total_tokens_total,
    )


def _to_usage(usage: dict[str, int] | None):
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def _build_thread_usage(store: ChatStore, session_id: str):
    updated_session = store.get_session(session_id)
    if updated_session is None:
        return None
    return {
        "prompt_tokens": updated_session.prompt_tokens_total,
        "completion_tokens": updated_session.completion_tokens_total,
        "total_tokens": updated_session.total_tokens_total,
    }


def _persist_assistant_turn(
    *,
    store: ChatStore,
    session_id: str,
    reply: str,
    sources: list[dict],
    usage: dict[str, int] | None = None,
):
    return store.add_message(
        session_id=session_id,
        role="assistant",
        content=reply,
        sources=sources,
        prompt_tokens=usage["prompt_tokens"] if usage else None,
        completion_tokens=usage["completion_tokens"] if usage else None,
        total_tokens=usage["total_tokens"] if usage else None,
    )


def _build_chat_response(
    *,
    store: ChatStore,
    session_id: str,
    reply: str,
    sources: list[dict],
    usage: dict[str, int] | None,
    assistant_message_id: str | None = None,
) -> dict:
    payload = {
        "reply": reply,
        "sources": sources,
        "usage": _to_usage(usage),
        "thread_usage": _build_thread_usage(store, session_id),
    }
    if assistant_message_id:
        payload["assistant_message_id"] = assistant_message_id
    return payload


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _prepare_turn(
    *,
    payload: ChatMessageRequest,
    store: ChatStore,
) -> tuple[object, str, list[dict[str, str]], object]:
    session = store.get_session(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    user_text = payload.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Missing message.")

    prior_messages = store.list_messages(payload.session_id)
    history = [{"role": message.role, "content": message.content} for message in prior_messages]

    if session.title == "New chat":
        store.set_title(payload.session_id, user_text[:40].strip() or "New chat")

    user_record = store.add_message(
        session_id=payload.session_id,
        role="user",
        content=user_text,
    )
    return session, user_text, history, user_record


@router.get("/models", response_model=ChatModelListResponse)
def list_models() -> ChatModelListResponse:
    return ChatModelListResponse(
        models=[
            ChatModelItem(
                id=model,
                max_context_tokens=settings.chat_model_context_limits.get(model),
            )
            for model in settings.chat_allowed_models
        ]
    )


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(
    payload: CreateSessionRequest,
    store: ChatStore = Depends(get_chat_store),
) -> CreateSessionResponse:
    user_id = payload.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id.")
    if payload.model not in settings.chat_allowed_models:
        raise HTTPException(status_code=400, detail="Unsupported model.")

    created = store.create_session(user_id=user_id, model=payload.model)
    return CreateSessionResponse(
        session_id=created.session_id,
        user_id=created.user_id,
        title=created.title,
        model=created.model,
        created_at=created.created_at,
    )


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    user_id: str = Query(...),
    store: ChatStore = Depends(get_chat_store),
) -> SessionListResponse:
    cleaned_user_id = user_id.strip()
    if not cleaned_user_id:
        raise HTTPException(status_code=400, detail="Missing user_id.")

    sessions = store.list_sessions(cleaned_user_id)
    return SessionListResponse(sessions=[_to_session_summary(session) for session in sessions])


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: str,
    store: ChatStore = Depends(get_chat_store),
) -> SessionDetailResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = store.list_messages(session_id)
    return SessionDetailResponse(
        session=_to_session_summary(session),
        messages=[
            SessionMessage(
                id=message.id,
                role=message.role,
                content=message.content,
                sources=message.sources,
                usage=(
                    {
                        "prompt_tokens": message.prompt_tokens,
                        "completion_tokens": message.completion_tokens,
                        "total_tokens": message.total_tokens,
                    }
                    if message.total_tokens is not None
                    else None
                ),
            )
            for message in messages
        ],
    )


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
def delete_session(
    session_id: str,
    store: ChatStore = Depends(get_chat_store),
) -> DeleteSessionResponse:
    deleted = store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    return DeleteSessionResponse(success=True)


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    response_model_exclude_none=True,
)
def send_message(
    payload: ChatMessageRequest,
    store: ChatStore = Depends(get_chat_store),
) -> ChatMessageResponse:
    session, user_text, history, _ = _prepare_turn(payload=payload, store=store)
    manager = build_chat_manager(model=session.model, user_id=session.user_id)

    try:
        reply, sources, _, usage = manager.answer_question(user_text, history=history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {exc}") from exc

    _persist_assistant_turn(
        store=store,
        session_id=payload.session_id,
        reply=reply,
        sources=sources,
        usage=usage,
    )
    return ChatMessageResponse(
        **_build_chat_response(
            store=store,
            session_id=payload.session_id,
            reply=reply,
            sources=sources,
            usage=usage,
        )
    )


@router.post("/message/stream")
def stream_message(
    payload: ChatMessageRequest,
    store: ChatStore = Depends(get_chat_store),
) -> StreamingResponse:
    session, user_text, history, _ = _prepare_turn(payload=payload, store=store)
    manager = build_chat_manager(model=session.model, user_id=session.user_id)
    completion_request = manager.build_completion_request(user_text, history=history)

    async def event_stream() -> AsyncIterator[str]:
        raw_answer = ""
        usage_payload: dict[str, int] | None = None

        try:
            if not completion_request.has_context:
                cleaned_answer = manager.finalize_answer(NO_CONTEXT_MESSAGE, [])
                assistant_record = _persist_assistant_turn(
                    store=store,
                    session_id=payload.session_id,
                    reply=cleaned_answer,
                    sources=[],
                )
                yield _sse_event("delta", {"delta": cleaned_answer})
                yield _sse_event(
                    "completion",
                    _build_chat_response(
                        store=store,
                        session_id=payload.session_id,
                        reply=cleaned_answer,
                        sources=[],
                        usage=None,
                        assistant_message_id=assistant_record.id,
                    ),
                )
                return

            response_stream = manager.client.chat.completions.create(
                model=manager.model,
                messages=completion_request.messages,
                stream=True,
                stream_options={"include_usage": True},
            )

            for chunk in response_stream:
                choice = chunk.choices[0] if chunk.choices else None
                delta = getattr(choice.delta, "content", None) if choice is not None else None
                if delta:
                    raw_answer += delta
                    yield _sse_event("delta", {"delta": delta})

                usage_payload = usage_to_dict(getattr(chunk, "usage", None)) or usage_payload

            cleaned_answer = manager.finalize_answer(raw_answer, completion_request.sources)
            assistant_record = _persist_assistant_turn(
                store=store,
                session_id=payload.session_id,
                reply=cleaned_answer,
                sources=completion_request.sources,
                usage=usage_payload,
            )
            yield _sse_event(
                "completion",
                _build_chat_response(
                    store=store,
                    session_id=payload.session_id,
                    reply=cleaned_answer,
                    sources=completion_request.sources,
                    usage=usage_payload,
                    assistant_message_id=assistant_record.id,
                ),
            )
        except Exception as exc:
            yield _sse_event("error", {"detail": f"Chat request failed: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
