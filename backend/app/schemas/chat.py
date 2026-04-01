from pydantic import BaseModel


class Source(BaseModel):
    title: str
    timestamp: str
    video_id: str | None = None
    url: str | None = None


class CreateSessionRequest(BaseModel):
    user_id: str
    model: str = "gpt-4o-mini"


class CreateSessionResponse(BaseModel):
    session_id: str
    user_id: str


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class ChatMessageResponse(BaseModel):
    reply: str
    sources: list[Source]
    has_context: bool
