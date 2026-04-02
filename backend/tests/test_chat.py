import json
import sys
import types

from fastapi.testclient import TestClient
from types import SimpleNamespace

sys.modules.setdefault(
    "app.pinecone_client",
    types.SimpleNamespace(index=types.SimpleNamespace(search=lambda **kwargs: None)),
)

from app.api import chat as chat_api
from app.chat.chat_manager import ChatManager
from app.main import app
from app.rag.retriever import RAGRetriever
from app.services.chat_store import ChatStore


class FakeChatManager:
    def __init__(self, model: str, user_id: str) -> None:
        self.model = model
        self.user_id = user_id

    def answer_question(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[str, list[dict], bool, dict[str, int] | None]:
        return (
            f"Echo: {user_input}",
            [{"title": "Demo Video", "timestamp": "0:12"}],
            True,
            {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        )


class FakeStreamingChatManager(FakeChatManager):
    def __init__(self, model: str, user_id: str) -> None:
        super().__init__(model=model, user_id=user_id)
        self.client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=self._create_stream)
            )
        )

    def build_completion_request(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            messages=[{"role": "user", "content": user_input}],
            sources=[{"title": "Demo Video", "timestamp": "0:12"}],
            has_context=True,
        )

    def finalize_answer(self, raw_answer: str, sources: list[dict] | None = None) -> str:
        return raw_answer.strip()

    def _create_stream(self, **kwargs):
        assert kwargs["stream"] is True
        assert kwargs["messages"]
        return [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Echo"))],
                usage=None,
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=": hello"))],
                usage=SimpleNamespace(
                    prompt_tokens=11,
                    completion_tokens=7,
                    total_tokens=18,
                ),
            ),
        ]


class FailingStreamingChatManager(FakeStreamingChatManager):
    def _create_stream(self, **kwargs):
        raise RuntimeError("stream exploded")


class RecordingRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.response = (
            "[Demo Video @ 0:12]\nTax loss harvesting examples can offset gains.",
            [{"title": "Demo Video", "timestamp": "0:12"}],
            True,
        )

    def query(
        self,
        user_id: str,
        question: str,
        top_k: int = 12,
    ) -> tuple[str, list[dict], bool]:
        self.queries.append(question)
        return self.response

    def normalize_query(self, query: str):
        normalized = query.replace("llms", "large language models")
        normalized = normalized.replace("LLMs", "large language models")
        return SimpleNamespace(query=normalized, applied=normalized != query)


class FakeCompletionsClient:
    def __init__(self, rewrite_outputs: list[str] | None = None) -> None:
        self.rewrite_outputs = list(rewrite_outputs or [])
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        last_message = kwargs["messages"][-1]["content"]
        if "Standalone search query:" in last_message:
            if not self.rewrite_outputs:
                raise AssertionError("Missing fake rewrite output.")
            content = self.rewrite_outputs.pop(0)
        else:
            content = "Answer from context."
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            ),
        )


class RaisingRewriteCompletionsClient(FakeCompletionsClient):
    def create(self, **kwargs):
        last_message = kwargs["messages"][-1]["content"]
        if "Standalone search query:" in last_message:
            raise RuntimeError("rewrite exploded")
        return super().create(**kwargs)


def _build_manager_with_fakes(
    *,
    rewrite_outputs: list[str] | None = None,
    retriever: RecordingRetriever | None = None,
) -> tuple[ChatManager, RecordingRetriever, FakeCompletionsClient]:
    manager = ChatManager(model="gpt-4o-mini", user_id="user_1")
    fake_retriever = retriever or RecordingRetriever()
    fake_client = FakeCompletionsClient(rewrite_outputs=rewrite_outputs)
    manager.retriever = fake_retriever
    manager.client = SimpleNamespace(
        chat=SimpleNamespace(completions=fake_client)
    )
    return manager, fake_retriever, fake_client


def _read_sse_events(response) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    current_event: str | None = None
    current_data: list[str] = []

    for line in response.iter_lines():
        if isinstance(line, bytes):
            line = line.decode()
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current_data.append(line.split(":", 1)[1].strip())
        elif not line and current_event:
            events.append((current_event, "\n".join(current_data)))
            current_event = None
            current_data = []

    if current_event:
        events.append((current_event, "\n".join(current_data)))
    return events


def test_chat_session_and_message_and_history(tmp_path, monkeypatch) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    monkeypatch.setattr(
        chat_api,
        "build_chat_manager",
        lambda model, user_id: FakeChatManager(model=model, user_id=user_id),
    )
    client = TestClient(app)

    create_response = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()
    session_id = created_payload["session_id"]
    assert created_payload["user_id"] == "user_1"
    assert created_payload["title"] == "New chat"
    assert created_payload["model"] == "gpt-4o-mini"

    message_response = client.post(
        "/chat/message",
        json={"session_id": session_id, "message": "hello"},
    )
    assert message_response.status_code == 200
    assert message_response.json() == {
        "reply": "Echo: hello",
        "sources": [{"title": "Demo Video", "timestamp": "0:12"}],
        "has_context": True,
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
        "thread_usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
    }

    list_response = client.get("/chat/sessions", params={"user_id": "user_1"})
    assert list_response.status_code == 200
    sessions = list_response.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == session_id
    assert sessions[0]["message_count"] == 2
    assert sessions[0]["total_tokens_total"] == 18

    detail_response = client.get(f"/chat/sessions/{session_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["session"]["title"] == "hello"
    messages = detail_payload["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Echo: hello"
    assert messages[1]["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }

    models_response = client.get("/chat/models")
    assert models_response.status_code == 200
    assert len(models_response.json()["models"]) >= 1

    app.dependency_overrides.clear()


def test_streaming_chat_message_persists_final_assistant_message(tmp_path, monkeypatch) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    monkeypatch.setattr(
        chat_api,
        "build_chat_manager",
        lambda model, user_id: FakeStreamingChatManager(model=model, user_id=user_id),
    )
    client = TestClient(app)

    create_response = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    )
    session_id = create_response.json()["session_id"]

    with client.stream(
        "POST",
        "/chat/message/stream",
        json={"session_id": session_id, "message": "hello"},
    ) as response:
        assert response.status_code == 200
        events = []
        current_event = None
        current_data: list[str] = []
        for line in response.iter_lines():
            if isinstance(line, bytes):
                line = line.decode()
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                current_data.append(line.split(":", 1)[1].strip())
            elif not line and current_event:
                events.append((current_event, "\n".join(current_data)))
                current_event = None
                current_data = []
        if current_event:
            events.append((current_event, "\n".join(current_data)))

        assert [event for event, _ in events] == ["delta", "delta", "completion"]
        completion_payload = next(
            payload for event, payload in events if event == "completion"
        )

    completion = json.loads(completion_payload)
    assert completion["reply"] == "Echo: hello"
    assert completion["assistant_message_id"]
    assert completion["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }

    detail_response = client.get(f"/chat/sessions/{session_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert len(detail_payload["messages"]) == 2
    assert detail_payload["messages"][1]["content"] == "Echo: hello"

    app.dependency_overrides.clear()


def test_chat_message_normalizes_reply_citations_from_structured_sources(
    tmp_path,
    monkeypatch,
) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store

    def build_manager(model: str, user_id: str) -> ChatManager:
        retriever = RecordingRetriever()
        retriever.response = (
            "[Neural networks @ 1:52]\nLLMs use learned weights.",
            [{"title": "Neural networks", "timestamp": "1:52"}],
            True,
        )
        manager, _, fake_client = _build_manager_with_fakes(
            rewrite_outputs=["tell me about llms"],
            retriever=retriever,
        )
        fake_client.create = lambda **kwargs: SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="LLMs use learned weights.\nSource: Neural networks"
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            ),
        )
        manager.model = model
        manager.user_id = user_id
        manager.client = SimpleNamespace(
            chat=SimpleNamespace(completions=fake_client)
        )
        return manager

    monkeypatch.setattr(chat_api, "build_chat_manager", build_manager)
    client = TestClient(app)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    response = client.post(
        "/chat/message",
        json={"session_id": session_id, "message": "tell me about llms"},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "LLMs use learned weights.\n[Neural networks @ 1:52]"
    assert response.json()["sources"] == [{"title": "Neural networks", "timestamp": "1:52"}]

    detail_response = client.get(f"/chat/sessions/{session_id}")
    detail_payload = detail_response.json()
    assert detail_payload["messages"][1]["content"] == (
        "LLMs use learned weights.\n[Neural networks @ 1:52]"
    )
    assert detail_payload["messages"][1]["sources"] == [
        {
            "title": "Neural networks",
            "timestamp": "1:52",
            "video_id": None,
            "url": None,
            "page_number": None,
        }
    ]

    app.dependency_overrides.clear()


def test_chat_threads_remain_isolated(tmp_path, monkeypatch) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    monkeypatch.setattr(
        chat_api,
        "build_chat_manager",
        lambda model, user_id: FakeChatManager(model=model, user_id=user_id),
    )
    client = TestClient(app)

    session_one = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]
    session_two = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    client.post("/chat/message", json={"session_id": session_one, "message": "first"})
    client.post("/chat/message", json={"session_id": session_two, "message": "second"})

    detail_one = client.get(f"/chat/sessions/{session_one}").json()
    detail_two = client.get(f"/chat/sessions/{session_two}").json()

    assert [message["content"] for message in detail_one["messages"]] == [
        "first",
        "Echo: first",
    ]
    assert [message["content"] for message in detail_two["messages"]] == [
        "second",
        "Echo: second",
    ]

    app.dependency_overrides.clear()


def test_delete_session_removes_it_from_history_and_detail(tmp_path) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    client = TestClient(app)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]
    store.add_message(session_id=session_id, role="user", content="hello")

    delete_response = client.delete(f"/chat/sessions/{session_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"success": True}

    list_response = client.get("/chat/sessions", params={"user_id": "user_1"})
    assert list_response.status_code == 200
    assert list_response.json()["sessions"] == []

    detail_response = client.get(f"/chat/sessions/{session_id}")
    assert detail_response.status_code == 404
    assert detail_response.json()["detail"] == "Session not found."

    app.dependency_overrides.clear()


def test_delete_session_does_not_affect_other_sessions(tmp_path) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    client = TestClient(app)

    session_one = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]
    session_two = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]
    other_user_session = client.post(
        "/chat/sessions",
        json={"user_id": "user_2", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    assert client.delete(f"/chat/sessions/{session_one}").status_code == 200

    remaining_user_one = client.get("/chat/sessions", params={"user_id": "user_1"}).json()["sessions"]
    remaining_user_two = client.get("/chat/sessions", params={"user_id": "user_2"}).json()["sessions"]

    assert [session["session_id"] for session in remaining_user_one] == [session_two]
    assert [session["session_id"] for session in remaining_user_two] == [other_user_session]

    app.dependency_overrides.clear()


def test_delete_missing_session_returns_404(tmp_path) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    client = TestClient(app)

    response = client.delete("/chat/sessions/missing-session")

    app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found."


def test_streaming_chat_error_emits_error_event_and_persists_user_message(
    tmp_path,
    monkeypatch,
) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    monkeypatch.setattr(
        chat_api,
        "build_chat_manager",
        lambda model, user_id: FailingStreamingChatManager(model=model, user_id=user_id),
    )
    client = TestClient(app)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    with client.stream(
        "POST",
        "/chat/message/stream",
        json={"session_id": session_id, "message": "hello"},
    ) as response:
        assert response.status_code == 200
        events = _read_sse_events(response)

    assert len(events) == 1
    event_name, payload = events[0]
    assert event_name == "error"
    assert "stream exploded" in json.loads(payload)["detail"]

    detail_response = client.get(f"/chat/sessions/{session_id}")
    detail_payload = detail_response.json()
    assert [message["role"] for message in detail_payload["messages"]] == ["user"]
    assert detail_payload["messages"][0]["content"] == "hello"

    app.dependency_overrides.clear()


def test_streaming_chat_normalizes_reply_and_persists_same_text(
    tmp_path,
    monkeypatch,
) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store

    class CitationStreamingManager(FakeStreamingChatManager):
        def build_completion_request(
            self,
            user_input: str,
            history: list[dict[str, str]] | None = None,
        ) -> SimpleNamespace:
            return SimpleNamespace(
                messages=[{"role": "user", "content": user_input}],
                sources=[{"title": "Neural networks", "timestamp": "1:52"}],
                has_context=True,
            )

        def _create_stream(self, **kwargs):
            assert kwargs["stream"] is True
            return [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="Large language models work like this.\n")
                        )
                    ],
                    usage=None,
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="Source: Neural networks")
                        )
                    ],
                    usage=SimpleNamespace(
                        prompt_tokens=11,
                        completion_tokens=7,
                        total_tokens=18,
                    ),
                ),
            ]

        def finalize_answer(self, raw_answer: str, sources: list[dict] | None = None) -> str:
            manager = ChatManager(model=self.model, user_id=self.user_id)
            return manager.finalize_answer(raw_answer, sources)

    monkeypatch.setattr(
        chat_api,
        "build_chat_manager",
        lambda model, user_id: CitationStreamingManager(model=model, user_id=user_id),
    )
    client = TestClient(app)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    with client.stream(
        "POST",
        "/chat/message/stream",
        json={"session_id": session_id, "message": "tell me about llms"},
    ) as response:
        assert response.status_code == 200
        events = _read_sse_events(response)

    completion_payload = next(
        json.loads(payload) for event, payload in events if event == "completion"
    )
    assert completion_payload["reply"] == (
        "Large language models work like this.\n[Neural networks @ 1:52]"
    )
    assert completion_payload["sources"] == [
        {"title": "Neural networks", "timestamp": "1:52"}
    ]

    detail_response = client.get(f"/chat/sessions/{session_id}")
    detail_payload = detail_response.json()
    assert detail_payload["messages"][1]["content"] == (
        "Large language models work like this.\n[Neural networks @ 1:52]"
    )

    app.dependency_overrides.clear()


def test_create_session_rejects_unsupported_model(tmp_path) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    client = TestClient(app)
    response = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "not-a-model"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported model."


def test_build_completion_request_keeps_self_contained_query_for_retrieval() -> None:
    manager, retriever, _ = _build_manager_with_fakes(
        rewrite_outputs=["What does the tax loss harvesting video say about wash sales?"],
    )

    request = manager.build_completion_request(
        "What does the tax loss harvesting video say about wash sales?",
        history=[{"role": "assistant", "content": "We discussed tax loss harvesting."}],
    )

    assert request.retrieval_query == "What does the tax loss harvesting video say about wash sales?"
    assert retriever.queries == [
        "What does the tax loss harvesting video say about wash sales?"
    ]


def test_build_completion_request_rewrites_follow_up_for_retrieval() -> None:
    manager, retriever, _ = _build_manager_with_fakes(
        rewrite_outputs=["Examples of tax loss harvesting"],
    )

    request = manager.build_completion_request(
        "can u give me examples",
        history=[
            {"role": "user", "content": "Tell me about tax loss harvesting."},
            {"role": "assistant", "content": "It can offset gains using losses."},
        ],
    )

    assert request.retrieval_query == "Examples of tax loss harvesting"
    assert retriever.queries == ["Examples of tax loss harvesting"]
    assert request.messages[-1] == {"role": "user", "content": "can u give me examples"}


def test_build_completion_request_normalizes_new_chat_acronym_query_for_retrieval() -> None:
    manager, retriever, _ = _build_manager_with_fakes()

    request = manager.build_completion_request(
        "can u tell me about llms",
        history=[],
    )

    assert request.retrieval_query == "can u tell me about large language models"
    assert retriever.queries == ["can u tell me about large language models"]


def test_rewrite_failure_falls_back_to_original_user_input() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="user_1")
    retriever = RecordingRetriever()
    manager.retriever = retriever
    manager.client = SimpleNamespace(
        chat=SimpleNamespace(completions=RaisingRewriteCompletionsClient())
    )

    request = manager.build_completion_request(
        "can u give me examples",
        history=[
            {"role": "user", "content": "Tell me about tax loss harvesting."},
            {"role": "assistant", "content": "It can offset gains using losses."},
        ],
    )

    assert request.retrieval_query == "can u give me examples"
    assert retriever.queries == ["can u give me examples"]


def test_retriever_selects_by_combined_similarity_and_keyword_score() -> None:
    retriever = RAGRetriever()

    selected_hits = retriever._select_relevant_hits(
        ranked_hits=[
            {
                "chunk_text": "examples here",
                "keyword_overlap_count": 1,
                "similarity_score": 0.8,
            },
            {
                "chunk_text": "other chunk",
                "keyword_overlap_count": 0,
                "similarity_score": 0.5,
            },
            {
                "chunk_text": "irrelevant",
                "keyword_overlap_count": 2,
                "similarity_score": 0.1,
            },
        ],
    )

    texts = [hit["chunk_text"] for hit in selected_hits]
    assert "examples here" in texts
    assert "other chunk" in texts
    assert "irrelevant" not in texts


def test_retriever_returns_no_context_for_unrelated_hits() -> None:
    retriever = RAGRetriever()
    raw_hits = [
        SimpleNamespace(
            _score=0.1,
            fields={
                "chunk_text": "Load balancers distribute traffic across servers.",
                "source_type": "youtube",
                "video_title": "Scalability Lecture",
                "video_id": "abc123",
                "timestamp": "19:46",
            },
        )
    ]

    retriever._search_hits = lambda **kwargs: raw_hits

    context, sources, has_context = retriever.query(
        user_id="user_1",
        question="What are large language models?",
    )

    assert context == ""
    assert sources == []
    assert has_context is False


def test_retriever_dedupes_sources_for_repeated_source_locations() -> None:
    retriever = RAGRetriever()

    context, sources = retriever._build_context_and_sources(
        [
            {
                "chunk_text": "Chunk one",
                "title": "Scalability Lecture",
                "timestamp": "19:46",
                "video_id": "abc123",
                "file_name": "",
                "source_type": "youtube",
                "page_number": None,
                "keyword_overlap_count": 2,
            },
            {
                "chunk_text": "Chunk two",
                "title": "Scalability Lecture",
                "timestamp": "19:46",
                "video_id": "abc123",
                "file_name": "",
                "source_type": "youtube",
                "page_number": None,
                "keyword_overlap_count": 2,
            },
        ]
    )

    assert "Chunk one" in context
    assert "Chunk two" in context
    assert sources == [
        {
            "title": "Scalability Lecture",
            "timestamp": "19:46",
            "video_id": "abc123",
            "page_number": None,
            "url": "https://www.youtube.com/watch?v=abc123",
        }
    ]


def test_chat_api_uses_rewritten_query_for_follow_up_turn(tmp_path, monkeypatch) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    recorded_retrievers: list[RecordingRetriever] = []

    def build_manager(model: str, user_id: str) -> ChatManager:
        manager, retriever, fake_client = _build_manager_with_fakes(
            rewrite_outputs=["Examples of tax loss harvesting"],
        )
        manager.model = model
        manager.user_id = user_id
        recorded_retrievers.append(retriever)
        manager.client = SimpleNamespace(
            chat=SimpleNamespace(completions=fake_client)
        )
        return manager

    monkeypatch.setattr(chat_api, "build_chat_manager", build_manager)
    client = TestClient(app)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    first_response = client.post(
        "/chat/message",
        json={"session_id": session_id, "message": "Tell me about tax loss harvesting."},
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/chat/message",
        json={"session_id": session_id, "message": "can u give me examples"},
    )

    assert second_response.status_code == 200
    assert second_response.json()["reply"] == "Answer from context."
    assert recorded_retrievers[-1].queries == ["Examples of tax loss harvesting"]

    app.dependency_overrides.clear()


def test_chat_api_returns_no_context_and_no_sources_for_unrelated_follow_up(
    tmp_path,
    monkeypatch,
) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    recorded_retrievers: list[RecordingRetriever] = []
    retriever_responses = [
        (
            "[Scalability Lecture @ 19:46]\nLoad balancers distribute traffic.",
            [{"title": "Scalability Lecture", "timestamp": "19:46"}],
            True,
        ),
        ("", [], False),
    ]

    def build_manager(model: str, user_id: str) -> ChatManager:
        request_index = len(recorded_retrievers)
        retriever = RecordingRetriever()
        retriever.response = retriever_responses[request_index]
        manager, retriever, fake_client = _build_manager_with_fakes(
            rewrite_outputs=[
                "How to implement load balancers"
                if request_index == 0
                else "What are large language models?"
            ],
            retriever=retriever,
        )
        manager.model = model
        manager.user_id = user_id
        recorded_retrievers.append(retriever)
        manager.client = SimpleNamespace(
            chat=SimpleNamespace(completions=fake_client)
        )
        return manager

    monkeypatch.setattr(chat_api, "build_chat_manager", build_manager)
    client = TestClient(app)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    first_response = client.post(
        "/chat/message",
        json={"session_id": session_id, "message": "How do I implement load balancers?"},
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/chat/message",
        json={"session_id": session_id, "message": "What are large language models?"},
    )

    assert second_response.status_code == 200
    assert second_response.json()["has_context"] is False
    assert second_response.json()["sources"] == []
    assert "I couldn't find anything relevant" in second_response.json()["reply"]
    assert recorded_retrievers[-1].queries == ["What are large language models?"]

    detail_response = client.get(f"/chat/sessions/{session_id}")
    detail_payload = detail_response.json()
    assert detail_payload["messages"][-1]["sources"] == []

    app.dependency_overrides.clear()


def test_streaming_chat_returns_no_context_without_sources_for_unrelated_follow_up(
    tmp_path,
    monkeypatch,
) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: store
    recorded_retrievers: list[RecordingRetriever] = []
    retriever_responses = [
        (
            "[Scalability Lecture @ 19:46]\nLoad balancers distribute traffic.",
            [{"title": "Scalability Lecture", "timestamp": "19:46"}],
            True,
        ),
        ("", [], False),
    ]

    def build_manager(model: str, user_id: str) -> ChatManager:
        request_index = len(recorded_retrievers)
        retriever = RecordingRetriever()
        retriever.response = retriever_responses[request_index]
        manager, retriever, fake_client = _build_manager_with_fakes(
            rewrite_outputs=[
                "How to implement load balancers"
                if request_index == 0
                else "What are large language models?"
            ],
            retriever=retriever,
        )
        manager.model = model
        manager.user_id = user_id
        recorded_retrievers.append(retriever)
        manager.client = SimpleNamespace(
            chat=SimpleNamespace(completions=fake_client)
        )
        return manager

    monkeypatch.setattr(chat_api, "build_chat_manager", build_manager)
    client = TestClient(app)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    first_response = client.post(
        "/chat/message",
        json={"session_id": session_id, "message": "How do I implement load balancers?"},
    )
    assert first_response.status_code == 200

    with client.stream(
        "POST",
        "/chat/message/stream",
        json={"session_id": session_id, "message": "What are large language models?"},
    ) as response:
        assert response.status_code == 200
        events = _read_sse_events(response)

    completion_payload = next(
        json.loads(payload) for event, payload in events if event == "completion"
    )
    assert completion_payload["has_context"] is False
    assert completion_payload["sources"] == []
    assert "I couldn't find anything relevant" in completion_payload["reply"]

    detail_response = client.get(f"/chat/sessions/{session_id}")
    detail_payload = detail_response.json()
    assert detail_payload["messages"][-1]["sources"] == []

    app.dependency_overrides.clear()


def test_retriever_returns_high_similarity_hit_with_zero_keyword_overlap() -> None:
    retriever = RAGRetriever()

    selected = retriever._select_relevant_hits(
        ranked_hits=[
            {
                "chunk_text": "Neural nets are deep learning models.",
                "keyword_overlap_count": 0,
                "similarity_score": 0.85,
            },
        ],
    )

    assert len(selected) == 1
    assert selected[0]["chunk_text"] == (
        "Neural nets are deep learning models."
    )


def test_retriever_rejects_low_similarity_hit_with_high_keyword_overlap() -> None:
    retriever = RAGRetriever()

    selected = retriever._select_relevant_hits(
        ranked_hits=[
            {
                "chunk_text": "Unrelated content with matching words.",
                "keyword_overlap_count": 5,
                "similarity_score": 0.1,
            },
        ],
    )

    assert selected == []


def test_retriever_normalize_query_expands_llms() -> None:
    retriever = RAGRetriever()

    normalized = retriever.normalize_query("can u tell me about llms")

    assert normalized.query == "can u tell me about large language models"
    assert normalized.applied is True


def test_retriever_selects_borderline_hit_for_normalized_acronym_query() -> None:
    retriever = RAGRetriever()

    selected = retriever._select_relevant_hits(
        ranked_hits=[
            {
                "chunk_text": "Large language models predict the next token.",
                "keyword_overlap_count": 3,
                "similarity_score": 0.24,
            },
        ],
        normalized_query_applied=True,
    )

    assert len(selected) == 1
    assert selected[0]["chunk_text"] == (
        "Large language models predict the next token."
    )


def test_retriever_rejects_borderline_hit_without_normalized_acronym_query() -> None:
    retriever = RAGRetriever()

    selected = retriever._select_relevant_hits(
        ranked_hits=[
            {
                "chunk_text": "Large language models predict the next token.",
                "keyword_overlap_count": 3,
                "similarity_score": 0.24,
            },
        ],
        normalized_query_applied=False,
    )

    assert selected == []


def test_extract_keywords_preserves_short_acronyms() -> None:
    retriever = RAGRetriever()

    keywords = retriever._extract_keywords(
        "Tell me about LLMs and AI and ML"
    )

    assert "llms" in keywords or "llm" in keywords
    assert "ai" in keywords
    assert "ml" in keywords


def test_extract_keywords_filters_stopwords() -> None:
    retriever = RAGRetriever()

    keywords = retriever._extract_keywords(
        "can you tell me about the thing"
    )

    assert "can" not in keywords
    assert "you" not in keywords
    assert "tell" not in keywords
    assert "about" not in keywords
    assert "the" not in keywords
    assert "thing" not in keywords


# ── Fix 1: Citation stripping tests ──────────────────────


def test_strip_citations_timestamp() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "See [NoSQL Explained @ 12:34] for details."
    assert manager._strip_citations(text) == (
        "See NoSQL Explained @ 12:34 for details."
    )


def test_strip_citations_long_timestamp() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "At [Lecture @ 1:02:30] they explain."
    assert manager._strip_citations(text) == (
        "At Lecture @ 1:02:30 they explain."
    )


def test_strip_citations_page() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "Refer to [report.pdf p.5] here."
    assert manager._strip_citations(text) == (
        "Refer to report.pdf p.5 here."
    )


def test_strip_citations_source_prefix() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "As noted:\n  [Source: Video Title @ 12:34]"
    assert manager._strip_citations(text) == (
        "As noted:\n  Source: Video Title @ 12:34"
    )


def test_strip_citations_preserves_non_citation_brackets() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "Use [1] or [see above] or [code] in your work."
    assert manager._strip_citations(text) == text


def test_normalize_citations_upgrades_source_prefix_to_timestamp() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "Source: Neural networks"
    sources = [{"title": "Neural networks", "timestamp": "1:52"}]
    assert manager._normalize_citations(text, sources) == "[Neural networks @ 1:52]"


def test_normalize_citations_brackets_bare_timestamp_reference() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "See Neural networks @ 1:52 for more."
    sources = [{"title": "Neural networks", "timestamp": "1:52"}]
    assert manager._normalize_citations(text, sources) == (
        "See [Neural networks @ 1:52] for more."
    )


def test_normalize_citations_preserves_existing_correct_brackets() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "See [Neural networks @ 1:52] for more."
    sources = [{"title": "Neural networks", "timestamp": "1:52"}]
    assert manager._normalize_citations(text, sources) == text


def test_normalize_citations_pages_use_bracketed_page_reference() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "Source: report.pdf p.5"
    sources = [{"title": "report.pdf", "timestamp": "", "page_number": 5}]
    assert manager._normalize_citations(text, sources) == "[report.pdf p.5]"


def test_normalize_citations_multiple_sources() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "Start Source: Neural networks and then report.pdf p.5."
    sources = [
        {"title": "Neural networks", "timestamp": "1:52"},
        {"title": "report.pdf", "timestamp": "", "page_number": 5},
    ]
    assert manager._normalize_citations(text, sources) == (
        "Start [Neural networks @ 1:52] and then [report.pdf p.5]."
    )


def test_normalize_citations_preserves_non_citation_brackets() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "Use [1] or [see above] or [code] in your work."
    sources = [{"title": "Neural networks", "timestamp": "1:52"}]
    assert manager._normalize_citations(text, sources) == text


def test_normalize_citations_leaves_unmatched_source_line() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = "Source: Unknown video"
    sources = [{"title": "Neural networks", "timestamp": "1:52"}]
    assert manager._normalize_citations(text, sources) == text


def test_strip_citations_multiple() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    text = (
        "First [Video A @ 1:00] and also [doc.pdf p.3] end."
    )
    assert manager._strip_citations(text) == (
        "First Video A @ 1:00 and also doc.pdf p.3 end."
    )


def test_build_messages_strips_assistant_citations() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    history = [
        {"role": "user", "content": "What about [Video @ 5:00]?"},
        {
            "role": "assistant",
            "content": "As shown in [Video @ 5:00] it works.",
        },
    ]
    context = "[Video @ 10:00]\nNew chunk content here."
    messages, _ = manager._build_messages(context, history)

    user_msg = next(
        m for m in messages if m["role"] == "user"
    )
    assert "[Video @ 5:00]" in user_msg["content"]

    assistant_msg = next(
        m for m in messages if m["role"] == "assistant"
    )
    assert "[Video @ 5:00]" not in assistant_msg["content"]
    assert "Video @ 5:00" in assistant_msg["content"]


# ── Fix 2: Source filtering tests ────────────────────────


def test_format_context_returns_surviving_tags() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    blocks = [
        "[Tag A @ 1:00]\nContent A.",
        "[Tag B @ 2:00]\nContent B.",
        "[Tag C @ 3:00]\nContent C.",
        "[Tag D @ 4:00]\nContent D.",
    ]
    context = "\n\n---\n\n".join(blocks)
    _, surviving = manager._format_context_for_prompt(context)
    assert len(surviving) == manager.MAX_CONTEXT_BLOCKS
    assert "[Tag A @ 1:00]" in surviving
    assert "[Tag B @ 2:00]" in surviving
    assert "[Tag C @ 3:00]" in surviving
    assert "[Tag D @ 4:00]" not in surviving


def test_format_context_drops_block_over_total_char_limit() -> None:
    manager = ChatManager(model="gpt-4o-mini", user_id="u")
    big = "x" * 1200
    blocks = [
        f"[A @ 0:01]\n{big}",
        f"[B @ 0:02]\n{big}",
        f"[C @ 0:03]\n{big}",
    ]
    context = "\n\n---\n\n".join(blocks)
    formatted, surviving = manager._format_context_for_prompt(context)
    assert "[C @ 0:03]" not in surviving
    assert "[A @ 0:01]" in surviving


def test_match_source_to_tag_variants() -> None:
    assert ChatManager._match_source_to_tag(
        {"title": "Vid", "timestamp": "1:23"}
    ) == "[Vid @ 1:23]"
    assert ChatManager._match_source_to_tag(
        {"title": "doc.pdf", "timestamp": "", "page_number": 3}
    ) == "[doc.pdf p.3]"
    assert ChatManager._match_source_to_tag(
        {"title": "Untitled", "timestamp": ""}
    ) == "[Untitled]"
    assert ChatManager._match_source_to_tag(
        {"title": "", "timestamp": "5:00"}
    ) == "[5:00]"
    assert ChatManager._match_source_to_tag(
        {"title": "", "timestamp": ""}
    ) == "[Source]"


def test_sources_filtered_after_context_truncation() -> None:
    retriever = RecordingRetriever()
    big = "y" * 1200
    retriever.response = (
        "\n\n---\n\n".join([
            f"[Vid A @ 0:01]\n{big}",
            f"[Vid B @ 0:02]\n{big}",
            f"[Vid C @ 0:03]\n{big}",
        ]),
        [
            {"title": "Vid A", "timestamp": "0:01"},
            {"title": "Vid B", "timestamp": "0:02"},
            {"title": "Vid C", "timestamp": "0:03"},
        ],
        True,
    )
    manager, _, _ = _build_manager_with_fakes(
        rewrite_outputs=["test query"],
        retriever=retriever,
    )
    request = manager.build_completion_request("test query")
    source_titles = [s["title"] for s in request.sources]
    assert "Vid A" in source_titles
    assert "Vid C" not in source_titles
