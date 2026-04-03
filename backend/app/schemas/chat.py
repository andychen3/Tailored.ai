from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Source(BaseModel):
    title: str
    timestamp: str
    video_id: str | None = None
    url: str | None = None
    page_number: int | None = None


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AssistantAction(BaseModel):
    type: str
    label: str
    url: str
    pending_action_id: str | None = None


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
    title: str
    model: str
    created_at: datetime
    prompt_tokens_total: int = 0
    completion_tokens_total: int = 0
    total_tokens_total: int = 0


class SessionMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = []
    usage: TokenUsage | None = None
    action: AssistantAction | None = None


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class SessionDetailResponse(BaseModel):
    session: SessionSummary
    messages: list[SessionMessage]


class DeleteSessionResponse(BaseModel):
    success: bool


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class ChatMessageResponse(BaseModel):
    reply: str
    sources: list[Source]
    usage: TokenUsage | None = None
    thread_usage: TokenUsage | None = None
    action: AssistantAction | None = None


class ChatModelItem(BaseModel):
    id: str
    max_context_tokens: int | None = None


class ChatModelListResponse(BaseModel):
    models: list[ChatModelItem]
