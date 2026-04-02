from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.schemas.chat import (
    ChatModelItem,
    ChatModelListResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    CreateSessionRequest,
    CreateSessionResponse,
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
        user_id=session.user_id,
        title=session.title,
        model=session.model,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at,
        message_count=session.message_count,
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


@router.get("/models", response_model=ChatModelListResponse)
def list_models() -> ChatModelListResponse:
    return ChatModelListResponse(
        models=[
            ChatModelItem(
                id=model,
                label=model,
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
    return SessionListResponse(sessions=[_to_session_summary(s) for s in sessions])


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
                id=m.id,
                role=m.role,
                content=m.content,
                sources=m.sources,
                usage=(
                    {
                        "prompt_tokens": m.prompt_tokens,
                        "completion_tokens": m.completion_tokens,
                        "total_tokens": m.total_tokens,
                    }
                    if m.total_tokens is not None
                    else None
                ),
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    response_model_exclude_none=True,
)
def send_message(
    payload: ChatMessageRequest,
    store: ChatStore = Depends(get_chat_store),
) -> ChatMessageResponse:
    session = store.get_session(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    prior_messages = store.list_messages(payload.session_id)
    history = [{"role": m.role, "content": m.content} for m in prior_messages]
    manager = build_chat_manager(model=session.model, user_id=session.user_id)
    user_text = payload.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Missing message.")

    if session.title == "New chat":
        store.set_title(payload.session_id, user_text[:40].strip() or "New chat")

    store.add_message(
        session_id=payload.session_id,
        role="user",
        content=user_text,
    )

    try:
        reply, sources, has_context, usage = manager.answer_question(user_text, history=history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {exc}") from exc

    store.add_message(
        session_id=payload.session_id,
        role="assistant",
        content=reply,
        sources=sources,
        prompt_tokens=usage["prompt_tokens"] if usage else None,
        completion_tokens=usage["completion_tokens"] if usage else None,
        total_tokens=usage["total_tokens"] if usage else None,
    )
    updated_session = store.get_session(payload.session_id)
    thread_usage = (
        {
            "prompt_tokens": updated_session.prompt_tokens_total,
            "completion_tokens": updated_session.completion_tokens_total,
            "total_tokens": updated_session.total_tokens_total,
        }
        if updated_session is not None
        else None
    )
    return ChatMessageResponse(
        reply=reply,
        sources=sources,
        has_context=has_context,
        usage=_to_usage(usage),
        thread_usage=thread_usage,
    )
