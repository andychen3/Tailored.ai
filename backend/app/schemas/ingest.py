from pydantic import BaseModel, HttpUrl


class IngestYoutubeRequest(BaseModel):
    user_id: str
    url: HttpUrl
    video_title: str


class IngestYoutubeResponse(BaseModel):
    success: bool
    video_id: str
    chunks_ingested: int
