from pydantic import BaseModel, HttpUrl


class IngestYoutubeRequest(BaseModel):
    user_id: str
    url: HttpUrl


class IngestYoutubeResponse(BaseModel):
    success: bool
    video_id: str
    video_title: str
    chunks_ingested: int
