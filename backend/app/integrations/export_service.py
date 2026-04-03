from __future__ import annotations

from dataclasses import dataclass
import logging

from app.chat.openai_client import build_openai_client
from app.chat.prompts import USER_MESSAGE_SUMMARIZE_PROMPT
from app.core.config import settings
from app.integrations.local_thread_client import LocalTailoredMCPClient
from app.integrations.notion_client import (
    NotionOAuthError,
    RemoteNotionMCPClient,
    normalize_notion_id,
)
from app.integrations.store import IntegrationStore, PendingChatAction
from app.services.chat_store import ChatStore

logger = logging.getLogger(__name__)

def _timestamp_to_seconds(timestamp: str) -> int | None:
    """Convert 'M:SS' or 'H:MM:SS' to total seconds for YouTube ?t= param."""
    parts = timestamp.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return (
                int(parts[0]) * 3600
                + int(parts[1]) * 60
                + int(parts[2])
            )
    except ValueError:
        pass
    return None


_SUMMARIZE_MODEL = "gpt-4o-mini"
_SUMMARIZE_MIN_LENGTH = 200


def _summarize_user_message(
    client,
    content: str,
) -> str:
    if len(content) < _SUMMARIZE_MIN_LENGTH:
        return content
    try:
        response = client.chat.completions.create(
            model=_SUMMARIZE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": USER_MESSAGE_SUMMARIZE_PROMPT,
                },
                {"role": "user", "content": content},
            ],
        )
        result = (
            response.choices[0].message.content or ""
        ).strip()
        return result if result else content
    except Exception:
        logger.exception("User message summarization failed")
        return content


@dataclass(slots=True)
class ExportResult:
    message: str
    page_url: str | None = None


class NotionExportService:
    def __init__(
        self,
        *,
        chat_store: ChatStore,
        integration_store: IntegrationStore,
        thread_client: LocalTailoredMCPClient,
        notion_client: RemoteNotionMCPClient,
    ) -> None:
        self._chat_store = chat_store
        self._integration_store = integration_store
        self._thread_client = thread_client
        self._notion_client = notion_client

    def resume_pending_export(self, pending_action: PendingChatAction) -> ExportResult:
        connection = self._integration_store.get_notion_connection(pending_action.user_id)
        if connection is None:
            raise NotionOAuthError("Notion is not connected for this user.")

        connection = self._notion_client.ensure_valid_connection(
            connection,
            on_refresh=lambda refreshed: self._integration_store.upsert_notion_connection(
                user_id=pending_action.user_id,
                access_token=refreshed.access_token,
                refresh_token=refreshed.refresh_token,
                expires_at=refreshed.expires_at,
                client_id=refreshed.client_id,
                client_secret=refreshed.client_secret,
                token_endpoint=refreshed.token_endpoint,
                authorization_endpoint=refreshed.authorization_endpoint,
                issuer=refreshed.issuer,
                workspace_id=refreshed.workspace_id,
                workspace_name=refreshed.workspace_name,
            ),
        )
        workspace_id, workspace_name = self._notion_client.get_workspace_info(connection)
        if workspace_id or workspace_name:
            connection = self._integration_store.upsert_notion_connection(
                user_id=pending_action.user_id,
                access_token=connection.access_token,
                refresh_token=connection.refresh_token,
                expires_at=connection.expires_at,
                client_id=connection.client_id,
                client_secret=connection.client_secret,
                token_endpoint=connection.token_endpoint,
                authorization_endpoint=connection.authorization_endpoint,
                issuer=connection.issuer,
                workspace_id=workspace_id or connection.workspace_id,
                workspace_name=workspace_name or connection.workspace_name,
            )

        try:
            bundle = self._thread_client.get_thread_bundle(pending_action.session_id)
            page_title = self._extract_title(bundle)
            bundle = self._summarize_user_messages(bundle)
            markdown = self._render_conversation(bundle)
            configured_parent_id = settings.notion_conversation_notes_page_id.strip()
            parent_id = configured_parent_id
            if configured_parent_id:
                parent_id = normalize_notion_id(configured_parent_id)
                logger.info(
                    "Using configured Notion Conversation Notes parent",
                    extra={
                        "configured_parent_page_id": configured_parent_id,
                        "normalized_parent_page_id": parent_id,
                    },
                )
                parent = self._notion_client.fetch_page(connection, parent_id)
                if not parent or parent.get("object") == "error":
                    raise RuntimeError(
                        f"Configured Conversation Notes page could not be fetched: {parent_id}"
                    )
            else:
                parent = self._notion_client.search_page(connection, "Conversation Notes")
                logger.info("Notion parent search result", extra={"parent": parent})
                if parent is None or not parent.get("id"):
                    raise RuntimeError("Could not find the Notion page 'Conversation Notes'.")
                parent_id = str(parent["id"])
            page = self._notion_client.create_child_page(
                connection,
                parent_page_id=parent_id,
                title=page_title,
                markdown=markdown,
            )
            extracted = self._notion_client.extract_page_reference(page)
            page_ref = extracted["page_url"] or extracted["page_id"]
            if not page_ref:
                raise RuntimeError("Notion create-pages returned no page id or URL.")
            verification = self._notion_client.fetch_page(connection, page_ref)
            if not verification:
                raise RuntimeError("Notion page verification failed after create-pages.")
            page_url = extracted["page_url"] or self._extract_page_url(verification)
            if not page_url:
                raise RuntimeError("Created Notion page could not be verified with a page URL.")
            parent_match = self._extract_parent_page_id(verification)
            if parent_match and normalize_notion_id(parent_match) != normalize_notion_id(parent_id):
                raise RuntimeError(
                    "Created Notion page was not saved under the configured Conversation Notes page. "
                    f"Expected parent {parent_id}, got {parent_match}."
                )
            reply = (
                f"I saved this thread to Notion as '{page_title}'"
                + (f" in {connection.workspace_name}" if connection.workspace_name else "")
                + f". {page_url}"
            )
            logger.info(
                "Notion export verified",
                extra={
                    "session_id": pending_action.session_id,
                    "parent_page_id": parent_id,
                    "created_page_url": page_url,
                    "workspace_name": connection.workspace_name,
                },
            )
            self._chat_store.add_message(
                session_id=pending_action.session_id,
                role="assistant",
                content=reply,
                sources=[],
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
            )
            self._integration_store.update_pending_action_status(pending_action.id, "completed")
            return ExportResult(message=reply, page_url=page_url)
        except Exception:
            self._integration_store.update_pending_action_status(pending_action.id, "failed")
            raise

    def _summarize_user_messages(
        self, bundle: dict[str, object]
    ) -> dict[str, object]:
        client = build_openai_client()
        new_messages = []
        for msg in bundle.get("messages") or []:
            if (
                isinstance(msg, dict)
                and msg.get("role") == "user"
            ):
                summarized = _summarize_user_message(
                    client,
                    str(msg.get("content") or ""),
                )
                new_messages.append(
                    {**msg, "content": summarized}
                )
            else:
                new_messages.append(msg)
        return {**bundle, "messages": new_messages}

    def _extract_title(self, bundle: dict[str, object]) -> str:
        thread = bundle.get("thread") or {}
        title = str(thread.get("title") or "").strip()
        if title:
            return title
        messages = bundle.get("messages") or []
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = str(msg.get("content") or "").strip()
                if content:
                    return content[:80] + ("..." if len(content) > 80 else "")
        return "Chat Thread"

    def _render_conversation(self, bundle: dict[str, object]) -> str:
        messages = bundle.get("messages") or []
        raw_sources = bundle.get("sources") or []

        # Group sources by message_id so each response shows only its own sources
        sources_by_message: dict[str, list[dict]] = {}
        for src in raw_sources:
            if not isinstance(src, dict):
                continue
            mid = str(src.get("message_id") or "")
            if mid:
                sources_by_message.setdefault(mid, []).append(src)

        sections: list[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "").strip()
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                sections.append(f"**User**\n\n{content}")
            elif role == "assistant":
                msg_id = str(msg.get("id") or "")
                msg_sources = sources_by_message.get(msg_id, [])
                source_lines: list[str] = []
                seen: set[str] = set()
                for src in msg_sources:
                    source_title = str(src.get("title") or "").strip()
                    timestamp = str(src.get("timestamp") or "").strip()
                    if not source_title:
                        continue
                    label = (
                        f"{source_title} @ {timestamp}"
                        if timestamp
                        else source_title
                    )
                    if label in seen:
                        continue
                    seen.add(label)
                    url = src.get("url") or ""
                    if url and timestamp:
                        secs = _timestamp_to_seconds(timestamp)
                        if secs is not None:
                            sep = "&" if "?" in url else "?"
                            url = f"{url}{sep}t={secs}"
                    if url:
                        source_lines.append(f"- [{label}]({url})")
                    else:
                        source_lines.append(f"- {label}")
                block = f"**Response**\n\n{content}"
                if source_lines:
                    block += "\n\n**Sources**\n\n" + "\n".join(
                        source_lines
                    )
                sections.append(block)
        return "\n\n---\n\n".join(sections)

    def _extract_page_url(self, payload: dict[str, object]) -> str | None:
        if isinstance(payload.get("url"), str):
            return str(payload["url"])
        pages = payload.get("pages")
        if isinstance(pages, list):
            for page in pages:
                if isinstance(page, dict) and isinstance(page.get("url"), str):
                    return str(page["url"])
        return None

    def _extract_parent_page_id(self, payload: object) -> str | None:
        if isinstance(payload, dict):
            parent = payload.get("parent")
            if isinstance(parent, dict):
                page_id = parent.get("page_id")
                if isinstance(page_id, str) and page_id.strip():
                    return page_id
            for value in payload.values():
                found = self._extract_parent_page_id(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = self._extract_parent_page_id(value)
                if found:
                    return found
        return None
