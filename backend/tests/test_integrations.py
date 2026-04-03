from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api import integrations as integrations_api
from app.main import app
from app.integrations.store import IntegrationStore
from app.services.chat_store import ChatStore


class ExplodingChatManager:
    def __init__(self, model: str, user_id: str) -> None:
        self.model = model
        self.user_id = user_id

    def answer_question(self, user_input: str, history=None):
        raise AssertionError("LLM path should not run for disconnected Notion export intent.")


class FakeOAuthClient:
    def discover_oauth_metadata(self):
        return SimpleNamespace(
            issuer="https://auth.notion.example",
            authorization_endpoint="https://auth.notion.example/authorize",
            token_endpoint="https://auth.notion.example/token",
            registration_endpoint="https://auth.notion.example/register",
        )

    def register_client(self, metadata, *, redirect_uri: str):
        return SimpleNamespace(client_id="client-123", client_secret=None)

    def build_authorization_url(
        self,
        *,
        metadata,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
    ) -> str:
        return (
            "https://notion.example/authorize"
            f"?client_id={client_id}&redirect_uri={redirect_uri}&state={state}&code_challenge={code_challenge}"
        )

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
        client_id: str,
        client_secret: str | None,
        token_endpoint: str,
        authorization_endpoint: str | None,
        issuer: str | None,
    ):
        return SimpleNamespace(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=None,
            client_id=client_id,
            client_secret=client_secret,
            token_endpoint=token_endpoint,
            authorization_endpoint=authorization_endpoint,
            issuer=issuer,
            workspace_id="workspace-1",
            workspace_name="Tailored Workspace",
        )


class FakeExportService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def resume_pending_export(self, pending_action):
        self.calls.append(pending_action.id)
        return SimpleNamespace(message="Saved to Notion.")


def _build_client(tmp_path, monkeypatch):
    chat_store = ChatStore(str(tmp_path / "chat.sqlite3"))
    integration_store = IntegrationStore(str(tmp_path / "integrations.sqlite3"))
    app.dependency_overrides[chat_api.get_chat_store] = lambda: chat_store
    app.dependency_overrides[chat_api.get_integration_store] = lambda: integration_store
    app.dependency_overrides[integrations_api.get_chat_store] = lambda: chat_store
    app.dependency_overrides[integrations_api.get_integration_store] = lambda: integration_store
    fake_export_service = FakeExportService()
    monkeypatch.setattr(chat_api, "build_chat_manager", ExplodingChatManager)
    monkeypatch.setattr(integrations_api, "build_notion_oauth_client", lambda: FakeOAuthClient())
    monkeypatch.setattr(
        integrations_api,
        "build_export_service",
        lambda chat_store, integration_store: fake_export_service,
    )
    return TestClient(app), chat_store, integration_store, fake_export_service


def test_notion_export_returns_connect_action_without_llm(tmp_path, monkeypatch) -> None:
    client, chat_store, integration_store, _ = _build_client(tmp_path, monkeypatch)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    response = client.post(
        "/chat/message",
        json={"session_id": session_id, "message": "summarize this thread into notion"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"].startswith("I can save this thread to Notion")
    assert payload["action"]["type"] == "connect_notion"
    pending_id = payload["action"]["pending_action_id"]
    pending = integration_store.get_pending_action(pending_id)
    assert pending is not None
    assert pending.status == "pending"

    detail = client.get(f"/chat/sessions/{session_id}").json()
    assert detail["messages"][-1]["action"]["pending_action_id"] == pending_id

    app.dependency_overrides.clear()


def test_streaming_notion_export_returns_connect_action(tmp_path, monkeypatch) -> None:
    client, _, _, _ = _build_client(tmp_path, monkeypatch)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]

    with client.stream(
        "POST",
        "/chat/message/stream",
        json={"session_id": session_id, "message": "save this to notion"},
    ) as response:
        assert response.status_code == 200
        body = "".join(
            line.decode() if isinstance(line, bytes) else line
            for line in response.iter_lines()
        )

    assert "connect_notion" in body
    assert "Connect Notion" in body
    app.dependency_overrides.clear()


def test_notion_connect_builds_redirect_and_callback_resumes_export(
    tmp_path,
    monkeypatch,
) -> None:
    client, chat_store, integration_store, fake_export_service = _build_client(tmp_path, monkeypatch)

    session_id = client.post(
        "/chat/sessions",
        json={"user_id": "user_1", "model": "gpt-4o-mini"},
    ).json()["session_id"]
    pending = integration_store.create_pending_action(
        user_id="user_1",
        session_id=session_id,
        action_type="notion_export",
        original_message="export this conversation to notion",
    )

    connect_response = client.get(
        "/integrations/notion/connect",
        params={
            "user_id": "user_1",
            "session_id": session_id,
            "pending_action_id": pending.id,
        },
        follow_redirects=False,
    )
    assert connect_response.status_code == 307
    assert "state=" in connect_response.headers["location"]

    oauth_state = next(
        state
        for state in [
            integration_store.get_oauth_state(row_state)
            for row_state in [
                connect_response.headers["location"].split("state=", 1)[1].split("&", 1)[0]
            ]
        ]
        if state is not None
    )

    callback_response = client.get(
        "/integrations/notion/callback",
        params={"code": "oauth-code", "state": oauth_state.state},
        follow_redirects=False,
    )
    assert callback_response.status_code == 303
    assert "notion=success" in callback_response.headers["location"]
    assert integration_store.get_notion_connection("user_1") is not None
    assert fake_export_service.calls == [pending.id]

    app.dependency_overrides.clear()
