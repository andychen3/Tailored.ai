from fastapi.testclient import TestClient

from app.api.chat import get_session_store
from app.main import app


class FakeManager:
    def answer_question(self, message: str) -> tuple[str, list[dict], bool]:
        return (
            f"Echo: {message}",
            [{"title": "Demo Video", "timestamp": "0:12"}],
            True,
        )


class FakeSessionStore:
    def __init__(self) -> None:
        self._managers: dict[str, FakeManager] = {}

    def create_session(self, user_id: str, model: str = "gpt-4o-mini") -> str:
        session_id = "session_test"
        self._managers[session_id] = FakeManager()
        return session_id

    def get_manager(self, session_id: str) -> FakeManager | None:
        return self._managers.get(session_id)

    def touch(self, session_id: str) -> None:
        return None


def test_chat_session_and_message() -> None:
    fake_store = FakeSessionStore()
    app.dependency_overrides[get_session_store] = lambda: fake_store
    client = TestClient(app)

    create_response = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    )

    assert create_response.status_code == 200
    assert create_response.json() == {
        "session_id": "session_test",
        "user_id": "user_1",
    }

    message_response = client.post(
        "/chat/message",
        json={"session_id": "session_test", "message": "hello"},
    )

    app.dependency_overrides.clear()

    assert message_response.status_code == 200
    assert message_response.json() == {
        "reply": "Echo: hello",
        "sources": [{"title": "Demo Video", "timestamp": "0:12"}],
        "has_context": True,
    }
