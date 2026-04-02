from fastapi.testclient import TestClient

from app.api import sources as sources_api
from app.main import app
from app.services.source_catalog_store import SourceCatalogStore


def test_list_sources_returns_catalog_sources(tmp_path, monkeypatch) -> None:
    store = SourceCatalogStore(str(tmp_path / "sources.sqlite3"))
    store.upsert_ready_source(
        source_id="source_abc",
        user_id="user_1",
        source_type="youtube",
        title="A Video",
        source_url="https://www.youtube.com/watch?v=abc",
        video_id="abc",
        file_id=None,
        expected_chunk_count=12,
    )
    monkeypatch.setattr(sources_api, "source_catalog_store", store)

    client = TestClient(app)
    response = client.get("/sources", params={"user_id": "user_1"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["sources"]) == 1
    item = payload["sources"][0]
    assert item["source_id"] == "source_abc"
    assert item["user_id"] == "user_1"
    assert item["source_type"] == "youtube"
    assert item["title"] == "A Video"
    assert item["source_url"] == "https://www.youtube.com/watch?v=abc"
    assert item["video_id"] == "abc"
    assert item["file_id"] is None
    assert item["expected_chunk_count"] == 12
    assert item["sync_status"] == "in_sync"
    assert item["last_verified_at"] is not None
    assert item["created_at"] is not None
    assert item["updated_at"] is not None
