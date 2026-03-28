from fastapi.testclient import TestClient

from app.api.ingest import get_retriever
from app.main import app


class FakeIngester:
    def get_video_id(self, url: str) -> str:
        return "abc123"


class FakeRetriever:
    def __init__(self) -> None:
        self.ingester = FakeIngester()

    def ingest_youtube_url(self, user_id: str, url: str, video_title: str) -> int:
        return 4


def test_ingest_youtube() -> None:
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever()
    client = TestClient(app)

    response = client.post(
        "/ingest/youtube",
        json={
            "user_id": "user_1",
            "url": "https://www.youtube.com/watch?v=abc123",
            "video_title": "Test Video",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "video_id": "abc123",
        "chunks_ingested": 4,
    }
