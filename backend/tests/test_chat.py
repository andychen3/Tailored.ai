from fastapi.testclient import TestClient

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
    ) -> tuple[str, list[dict], bool]:
        return (
            f"Echo: {user_input}",
            [{"title": "Demo Video", "timestamp": "0:12"}],
            True,
        )


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
    }

    list_response = client.get("/chat/sessions", params={"user_id": "user_1"})
    assert list_response.status_code == 200
    sessions = list_response.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == session_id
    assert sessions[0]["message_count"] == 2

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

    app.dependency_overrides.clear()
