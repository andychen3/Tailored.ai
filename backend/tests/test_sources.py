import sys
import types

from fastapi.testclient import TestClient

from app.api import sources as sources_api
from app.main import app
from app.services.source_catalog_store import SourceCatalogStore, SourceReconciler


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


def test_source_catalog_persists_across_restart(tmp_path) -> None:
    db_path = str(tmp_path / "sources.sqlite3")
    first_store = SourceCatalogStore(db_path)
    first_store.upsert_ready_source(
        source_id="source_abc",
        user_id="user_1",
        source_type="youtube",
        title="A Video",
        source_url="https://www.youtube.com/watch?v=abc",
        video_id="abc",
        file_id=None,
        expected_chunk_count=12,
    )

    restarted_store = SourceCatalogStore(db_path)
    sources = restarted_store.list_sources("user_1")

    assert len(sources) == 1
    assert sources[0].source_id == "source_abc"
    assert sources[0].title == "A Video"
    assert sources[0].sync_status == "in_sync"


def test_source_reconciler_marks_missing_source(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "sources.sqlite3")
    store = SourceCatalogStore(db_path)
    store.upsert_ready_source(
        source_id="source_missing",
        user_id="user_1",
        source_type="youtube",
        title="Missing Video",
        source_url="https://www.youtube.com/watch?v=missing",
        video_id="missing",
        file_id=None,
        expected_chunk_count=12,
    )

    fake_pinecone_module = types.SimpleNamespace(
        index=types.SimpleNamespace(
            fetch=lambda **kwargs: {"vectors": {}},
        )
    )
    monkeypatch.setitem(sys.modules, "app.pinecone_client", fake_pinecone_module)

    reconciler = SourceReconciler(store)
    reconciler.reconcile_once(limit=10)

    refreshed = store.list_sources("user_1")
    assert len(refreshed) == 1
    assert refreshed[0].sync_status == "missing"
    assert refreshed[0].last_verified_at is not None


def test_delete_source_removes_catalog_row_and_pinecone_vectors(tmp_path, monkeypatch) -> None:
    store = SourceCatalogStore(str(tmp_path / "sources.sqlite3"))
    store.upsert_ready_source(
        source_id="source_delete",
        user_id="user_1",
        source_type="youtube",
        title="Delete Me",
        source_url="https://www.youtube.com/watch?v=delete",
        video_id="delete",
        file_id=None,
        expected_chunk_count=4,
    )
    deleted_calls: list[dict] = []
    fake_pinecone_module = types.SimpleNamespace(
        index=types.SimpleNamespace(
            delete=lambda **kwargs: deleted_calls.append(kwargs),
        )
    )
    monkeypatch.setattr(sources_api, "source_catalog_store", store)
    monkeypatch.setitem(sys.modules, "app.pinecone_client", fake_pinecone_module)

    client = TestClient(app)
    response = client.delete("/sources/source_delete")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert deleted_calls == [
        {
            "namespace": "__default__",
            "filter": {"source_id": {"$eq": "source_delete"}},
        }
    ]
    assert store.list_sources("user_1") == []


def test_delete_source_returns_404_when_missing(tmp_path, monkeypatch) -> None:
    store = SourceCatalogStore(str(tmp_path / "sources.sqlite3"))
    monkeypatch.setattr(sources_api, "source_catalog_store", store)
    monkeypatch.setitem(
        sys.modules,
        "app.pinecone_client",
        types.SimpleNamespace(index=types.SimpleNamespace(delete=lambda **kwargs: None)),
    )

    client = TestClient(app)
    response = client.delete("/sources/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found."


def test_delete_source_keeps_sqlite_row_when_pinecone_delete_fails(tmp_path, monkeypatch) -> None:
    store = SourceCatalogStore(str(tmp_path / "sources.sqlite3"))
    store.upsert_ready_source(
        source_id="source_fail",
        user_id="user_1",
        source_type="youtube",
        title="Keep Me",
        source_url="https://www.youtube.com/watch?v=keep",
        video_id="keep",
        file_id=None,
        expected_chunk_count=2,
    )
    monkeypatch.setattr(sources_api, "source_catalog_store", store)

    def _fail_delete(**_kwargs):
        raise RuntimeError("pinecone down")

    monkeypatch.setitem(
        sys.modules,
        "app.pinecone_client",
        types.SimpleNamespace(index=types.SimpleNamespace(delete=_fail_delete)),
    )

    client = TestClient(app)
    response = client.delete("/sources/source_fail")

    assert response.status_code == 502
    assert "Failed to delete source embeddings" in response.json()["detail"]
    assert [source.source_id for source in store.list_sources("user_1")] == ["source_fail"]


def test_delete_source_does_not_affect_other_sources(tmp_path, monkeypatch) -> None:
    store = SourceCatalogStore(str(tmp_path / "sources.sqlite3"))
    store.upsert_ready_source(
        source_id="source_one",
        user_id="user_1",
        source_type="youtube",
        title="Source One",
        source_url="https://www.youtube.com/watch?v=one",
        video_id="one",
        file_id=None,
        expected_chunk_count=1,
    )
    store.upsert_ready_source(
        source_id="source_two",
        user_id="user_1",
        source_type="youtube",
        title="Source Two",
        source_url="https://www.youtube.com/watch?v=two",
        video_id="two",
        file_id=None,
        expected_chunk_count=1,
    )
    monkeypatch.setattr(sources_api, "source_catalog_store", store)
    monkeypatch.setitem(
        sys.modules,
        "app.pinecone_client",
        types.SimpleNamespace(index=types.SimpleNamespace(delete=lambda **kwargs: None)),
    )

    client = TestClient(app)
    response = client.delete("/sources/source_one")

    assert response.status_code == 200
    assert [source.source_id for source in store.list_sources("user_1")] == ["source_two"]
