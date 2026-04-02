from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Source(BaseModel):
    title: str
    timestamp: str
    video_id: str | None = None
    url: str | None = None
    page_number: int | None = None


class CreateSessionRequest(BaseModel):
    user_id: str
    model: str = "gpt-4o-mini"


class CreateSessionResponse(BaseModel):
    session_id: str
    user_id: str
    title: str
    model: str
    created_at: datetime


class SessionSummary(BaseModel):
    session_id: str
    user_id: str
    title: str
    model: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    message_count: int


class SessionMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = []
    created_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class SessionDetailResponse(BaseModel):
    session: SessionSummary
    messages: list[SessionMessage]


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class ChatMessageResponse(BaseModel):
    reply: str
    sources: list[Source]
    has_context: bool
