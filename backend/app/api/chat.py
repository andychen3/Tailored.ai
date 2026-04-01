from fastapi import APIRouter, Depends, HTTPException

from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    CreateSessionRequest,
    CreateSessionResponse,
)
from app.services.session_store import SessionStore, session_store

router = APIRouter()


def get_session_store() -> SessionStore:
    return session_store


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(
    payload: CreateSessionRequest,
    store: SessionStore = Depends(get_session_store),
) -> CreateSessionResponse:
    session_id = store.create_session(user_id=payload.user_id, model=payload.model)
    return CreateSessionResponse(session_id=session_id, user_id=payload.user_id)


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    response_model_exclude_none=True,
)
def send_message(
    payload: ChatMessageRequest,
    store: SessionStore = Depends(get_session_store),
) -> ChatMessageResponse:
    manager = store.get_manager(payload.session_id)
    if manager is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    try:
        reply, sources, has_context = manager.answer_question(payload.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat request failed: {exc}") from exc

    store.touch(payload.session_id)
    return ChatMessageResponse(reply=reply, sources=sources, has_context=has_context)
