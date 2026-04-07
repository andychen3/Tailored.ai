from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.config import settings
from app.integrations.notion_client import (
    NotionOAuthClient,
    NotionOAuthError,
    build_pkce_pair,
    build_state_token,
)
from app.integrations.store import IntegrationStore, integration_store
from app.services.chat_store import ChatStore, chat_store

router = APIRouter()


class DisconnectIntegrationRequest(BaseModel):
    user_id: str


def get_chat_store() -> ChatStore:
    return chat_store


def get_integration_store() -> IntegrationStore:
    return integration_store


def build_notion_oauth_client() -> NotionOAuthClient:
    return NotionOAuthClient()


def _frontend_redirect_url(*, session_id: str, status: str, detail: str | None = None) -> str:
    query = {"notion": status, "session_id": session_id}
    if detail:
        query["detail"] = detail
    return f"{settings.frontend_app_url}?{urlencode(query)}"


@router.get("/notion/status")
def notion_status(
    user_id: str = Query(...),
    store: IntegrationStore = Depends(get_integration_store),
) -> dict[str, object]:
    connection = store.get_notion_connection(user_id.strip())
    return {
        "connected": connection is not None,
        "workspace_name": connection.workspace_name if connection else None,
    }


@router.post("/notion/disconnect")
def disconnect_notion(
    payload: DisconnectIntegrationRequest,
    store: IntegrationStore = Depends(get_integration_store),
) -> dict[str, object]:
    user_id = payload.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id.")
    deleted = store.delete_notion_connection(user_id)
    return {"success": True, "disconnected": deleted}


@router.get("/notion/connect")
def connect_notion(
    request: Request,
    user_id: str = Query(...),
    session_id: str = Query(...),
    pending_action_id: str = Query(...),
    store: IntegrationStore = Depends(get_integration_store),
    oauth_client: NotionOAuthClient = Depends(build_notion_oauth_client),
) -> RedirectResponse:
    pending = store.get_pending_action(pending_action_id)
    if pending is None or pending.user_id != user_id or pending.session_id != session_id:
        raise HTTPException(status_code=404, detail="Pending action not found.")

    redirect_uri = str(request.base_url).rstrip("/") + settings.notion_oauth_redirect_path
    code_verifier, code_challenge = build_pkce_pair()
    state = build_state_token()
    try:
        metadata = oauth_client.discover_oauth_metadata()
        credentials = oauth_client.register_client(metadata, redirect_uri=redirect_uri)
        target = oauth_client.build_authorization_url(
            metadata=metadata,
            client_id=credentials.client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
        )
        store.create_oauth_state(
            user_id=user_id,
            session_id=session_id,
            pending_action_id=pending_action_id,
            provider="notion",
            state=state,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            token_endpoint=metadata.token_endpoint,
            authorization_endpoint=metadata.authorization_endpoint,
            issuer=metadata.issuer,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
    except NotionOAuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(url=target, status_code=307)


@router.get("/notion/callback")
def notion_callback(
    code: str = Query(...),
    state: str = Query(...),
    oauth_client: NotionOAuthClient = Depends(build_notion_oauth_client),
    store: IntegrationStore = Depends(get_integration_store),
    chat_store: ChatStore = Depends(get_chat_store),
) -> RedirectResponse:
    state_record = store.get_oauth_state(state)
    if state_record is None or state_record.provider != "notion":
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    if state_record.consumed_at is not None:
        raise HTTPException(status_code=400, detail="OAuth state has already been used.")
    if state_record.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=400, detail="OAuth state has expired.")

    store.consume_oauth_state(state)
    try:
        token_result = oauth_client.exchange_code(
            code=code,
            redirect_uri=state_record.redirect_uri,
            code_verifier=state_record.code_verifier,
            client_id=state_record.client_id,
            client_secret=state_record.client_secret,
            token_endpoint=state_record.token_endpoint,
            authorization_endpoint=state_record.authorization_endpoint,
            issuer=state_record.issuer,
        )
        store.upsert_notion_connection(
            user_id=state_record.user_id,
            access_token=token_result.access_token,
            refresh_token=token_result.refresh_token,
            expires_at=token_result.expires_at,
            client_id=token_result.client_id,
            client_secret=token_result.client_secret,
            token_endpoint=token_result.token_endpoint,
            authorization_endpoint=token_result.authorization_endpoint,
            issuer=token_result.issuer,
            workspace_id=token_result.workspace_id,
            workspace_name=token_result.workspace_name,
        )
        store.update_pending_action_status(state_record.pending_action_id, "completed")
        chat_store.add_message(
            session_id=state_record.session_id,
            role="assistant",
            content=(
                "Notion is now connected! "
                "You can ask me to save this conversation to Notion whenever you're ready."
            ),
            sources=[],
        )
        return RedirectResponse(
            url=_frontend_redirect_url(session_id=state_record.session_id, status="success"),
            status_code=303,
        )
    except Exception as exc:
        chat_store.add_message(
            session_id=state_record.session_id,
            role="assistant",
            content=f"I couldn't finish the Notion export: {exc}",
            sources=[],
        )
        store.update_pending_action_status(state_record.pending_action_id, "failed")
        return RedirectResponse(
            url=_frontend_redirect_url(
                session_id=state_record.session_id,
                status="error",
                detail=str(exc),
            ),
            status_code=303,
        )
