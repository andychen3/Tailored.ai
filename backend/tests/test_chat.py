import json

from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.api import chat as chat_api
from app.main import app
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

    def finalize_answer(self, raw_answer: str) -> str:
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
