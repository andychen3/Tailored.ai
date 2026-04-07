"""Executes tool calls from the agent loop by dispatching to MCP clients."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.core.config import settings
from app.integrations.notion_client import RemoteNotionMCPClient
from app.integrations.store import IntegrationStore, NotionConnection
from app.services.chat_store import ChatStore
from mcp_server.server import (
    get_thread_messages_tool,
    get_thread_sources_tool,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolResult:
    content: str
    action: dict | None = None


@dataclass(slots=True)
class ToolExecutor:
    user_id: str
    session_id: str
    base_url: str
    integration_store: IntegrationStore
    chat_store: ChatStore
    notion_client: RemoteNotionMCPClient = field(default_factory=RemoteNotionMCPClient)

    def execute(self, tool_name: str, arguments: dict) -> ToolResult:
        dispatch = {
            "get_current_thread_messages": self._get_thread_messages,
            "get_current_thread_sources": self._get_thread_sources,
            "notion_search": self._notion_search,
            "notion_create_page": self._notion_create_page,
            "notion_fetch": self._notion_fetch,
        }
        handler = dispatch.get(tool_name)
        if handler is None:
            return ToolResult(content=json.dumps({"error": f"Unknown tool: {tool_name}"}))
        try:
            return handler(arguments)
        except Exception as exc:
            logger.exception("Tool execution failed: %s", tool_name)
            return ToolResult(content=json.dumps({"error": str(exc)}))

    # -- Thread tools (auto-inject session_id) --------------------------------

    def _get_thread_messages(self, arguments: dict) -> ToolResult:
        limit = arguments.get("limit", 200)
        result = get_thread_messages_tool(
            self.chat_store,
            session_id=self.session_id,
            limit=limit,
        )
        return ToolResult(content=json.dumps(result, default=str))

    def _get_thread_sources(self, _arguments: dict) -> ToolResult:
        result = get_thread_sources_tool(
            self.chat_store,
            session_id=self.session_id,
        )
        return ToolResult(content=json.dumps(result, default=str))

    # -- Notion tools ----------------------------------------------------------

    def _get_notion_connection(self) -> NotionConnection | None:
        connection = self.integration_store.get_notion_connection(self.user_id)
        if connection is None:
            return None
        return self.notion_client.ensure_valid_connection(
            connection,
            on_refresh=lambda refreshed: self.integration_store.upsert_notion_connection(
                user_id=self.user_id,
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

    def _require_notion(self) -> NotionConnection | ToolResult:
        connection = self._get_notion_connection()
        if connection is not None:
            return connection
        pending = self.integration_store.create_pending_action(
            user_id=self.user_id,
            session_id=self.session_id,
            action_type="connect_notion",
            original_message="",
        )
        action = {
            "type": "connect_notion",
            "label": "Connect Notion",
            "url": (
                f"{self.base_url.rstrip('/')}/integrations/notion/connect"
                f"?user_id={self.user_id}"
                f"&session_id={self.session_id}"
                f"&pending_action_id={pending.id}"
            ),
        }
        return ToolResult(
            content=json.dumps({
                "error": "Notion is not connected. The user needs to connect their Notion workspace first.",
            }),
            action=action,
        )

    def _notion_search(self, arguments: dict) -> ToolResult:
        conn = self._require_notion()
        if isinstance(conn, ToolResult):
            return conn
        query = arguments.get("query", "")
        result = self.notion_client.call_tool(
            conn,
            tool_name="notion-search",
            arguments={"query": query},
        )
        return ToolResult(content=json.dumps(result, default=str))

    def _notion_create_page(self, arguments: dict) -> ToolResult:
        conn = self._require_notion()
        if isinstance(conn, ToolResult):
            return conn
        result = self.notion_client.create_child_page(
            conn,
            parent_page_id=arguments["parent_page_id"],
            title=arguments["title"],
            markdown=arguments["markdown"],
        )
        extracted = self.notion_client.extract_page_reference(result)
        return ToolResult(content=json.dumps({
            "page_id": extracted.get("page_id"),
            "page_url": extracted.get("page_url"),
            "success": True,
        }, default=str))

    def _notion_fetch(self, arguments: dict) -> ToolResult:
        conn = self._require_notion()
        if isinstance(conn, ToolResult):
            return conn
        page_id = arguments.get("page_id", "")
        result = self.notion_client.fetch_page(conn, page_id)
        return ToolResult(content=json.dumps(result, default=str))
