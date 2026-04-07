from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
import re
from urllib import parse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.core.config import settings
from app.integrations.store import NotionConnection

logger = logging.getLogger(__name__)
NOTION_URL_RE = re.compile(r"https://www\.notion\.so/[^\s)]+")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}\b"
)

try:
    from mcp.client.sse import sse_client
except ImportError:  # pragma: no cover - depends on installed SDK variant
    sse_client = None


def _base64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def build_pkce_pair() -> tuple[str, str]:
    import hashlib

    verifier = _base64url(secrets.token_bytes(32))
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_state_token() -> str:
    return secrets.token_urlsafe(32)


def normalize_notion_id(value: str) -> str:
    cleaned = "".join(ch for ch in value.strip() if ch.isalnum())
    if len(cleaned) == 32:
        return (
            f"{cleaned[0:8]}-"
            f"{cleaned[8:12]}-"
            f"{cleaned[12:16]}-"
            f"{cleaned[16:20]}-"
            f"{cleaned[20:32]}"
        )
    return value.strip()


@dataclass(slots=True)
class OAuthMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None


@dataclass(slots=True)
class ClientCredentials:
    client_id: str
    client_secret: str | None = None


@dataclass(slots=True)
class TokenExchangeResult:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    workspace_id: str | None
    workspace_name: str | None
    client_id: str
    client_secret: str | None
    token_endpoint: str
    authorization_endpoint: str | None
    issuer: str | None


class NotionOAuthError(RuntimeError):
    pass


class NotionOAuthClient:
    def __init__(self) -> None:
        self._mcp_server_url = settings.notion_mcp_server_url
        self._user_agent = "TailoredAI-NotionMCP/1.0"

    def discover_oauth_metadata(self) -> OAuthMetadata:
        server_url = parse.urlparse(self._mcp_server_url)
        protected_resource_url = parse.urlunparse(
            (
                server_url.scheme,
                server_url.netloc,
                "/.well-known/oauth-protected-resource",
                "",
                "",
                "",
            )
        )
        protected_resource = self._fetch_json(protected_resource_url)
        authorization_servers = protected_resource.get("authorization_servers")
        if not isinstance(authorization_servers, list) or not authorization_servers:
            raise NotionOAuthError("OAuth discovery failed: missing authorization_servers.")
        issuer = str(authorization_servers[0]).rstrip("/")
        metadata_url = f"{issuer}/.well-known/oauth-authorization-server"
        metadata = self._fetch_json(metadata_url)
        authorization_endpoint = str(metadata.get("authorization_endpoint") or "")
        token_endpoint = str(metadata.get("token_endpoint") or "")
        if not authorization_endpoint or not token_endpoint:
            raise NotionOAuthError("OAuth discovery failed: missing OAuth endpoints.")
        registration_endpoint = metadata.get("registration_endpoint")
        return OAuthMetadata(
            issuer=issuer,
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            registration_endpoint=str(registration_endpoint) if registration_endpoint else None,
        )

    def register_client(self, metadata: OAuthMetadata, *, redirect_uri: str) -> ClientCredentials:
        if not metadata.registration_endpoint:
            raise NotionOAuthError("Notion MCP did not advertise dynamic client registration.")
        payload = {
            "client_name": "Tailored.ai Notion Export",
            "client_uri": settings.frontend_app_url,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "user",
        }
        response = self._post_json(metadata.registration_endpoint, payload)
        client_id = str(response.get("client_id") or "")
        if not client_id:
            raise NotionOAuthError("Client registration failed: missing client_id.")
        client_secret = response.get("client_secret")
        return ClientCredentials(
            client_id=client_id,
            client_secret=str(client_secret) if client_secret else None,
        )

    def build_authorization_url(
        self,
        *,
        metadata: OAuthMetadata,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        state: str,
    ) -> str:
        params = parse.urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": "user",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "consent",
            }
        )
        return f"{metadata.authorization_endpoint}?{params}"

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
    ) -> TokenExchangeResult:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        if client_secret:
            payload["client_secret"] = client_secret
        return self._perform_token_request(
            payload,
            token_endpoint=token_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            authorization_endpoint=authorization_endpoint,
            issuer=issuer,
        )

    def refresh_token(self, connection: NotionConnection) -> TokenExchangeResult:
        if not connection.refresh_token:
            raise NotionOAuthError("No refresh token available for Notion connection.")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
            "client_id": connection.client_id,
        }
        if connection.client_secret:
            payload["client_secret"] = connection.client_secret
        return self._perform_token_request(
            payload,
            token_endpoint=connection.token_endpoint,
            client_id=connection.client_id,
            client_secret=connection.client_secret,
            authorization_endpoint=connection.authorization_endpoint,
            issuer=connection.issuer,
        )

    def _perform_token_request(
        self,
        payload: dict[str, str],
        *,
        token_endpoint: str,
        client_id: str,
        client_secret: str | None,
        authorization_endpoint: str | None,
        issuer: str | None,
    ) -> TokenExchangeResult:
        try:
            response = httpx.post(
                token_endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": self._user_agent,
                },
                timeout=20,
                follow_redirects=True,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise NotionOAuthError(
                f"Notion token exchange failed: {exc.response.text or exc.response.reason_phrase}"
            ) from exc
        except httpx.HTTPError as exc:
            raise NotionOAuthError(f"Notion token exchange failed: {exc}") from exc

        expires_in = data.get("expires_in")
        expires_at = None
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
        access_token = str(data.get("access_token") or "")
        if not access_token:
            raise NotionOAuthError("Notion token exchange failed: missing access token.")
        refresh_token = data.get("refresh_token")
        return TokenExchangeResult(
            access_token=access_token,
            refresh_token=str(refresh_token) if refresh_token else None,
            expires_at=expires_at,
            workspace_id=None,
            workspace_name=None,
            client_id=client_id,
            client_secret=client_secret,
            token_endpoint=token_endpoint,
            authorization_endpoint=authorization_endpoint,
            issuer=issuer,
        )

    def _fetch_json(self, url: str) -> dict[str, object]:
        try:
            response = httpx.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": self._user_agent,
                },
                timeout=20,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise NotionOAuthError(
                f"OAuth discovery failed: {exc.response.text or exc.response.reason_phrase}"
            ) from exc
        except httpx.HTTPError as exc:
            raise NotionOAuthError(f"OAuth discovery failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise NotionOAuthError("OAuth discovery failed: malformed JSON response.")
        return payload

    def _post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": self._user_agent,
                },
                timeout=20,
                follow_redirects=True,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            raise NotionOAuthError(
                f"Client registration failed: {exc.response.text or exc.response.reason_phrase}"
            ) from exc
        except httpx.HTTPError as exc:
            raise NotionOAuthError(f"Client registration failed: {exc}") from exc
        if not isinstance(body, dict):
            raise NotionOAuthError("Client registration failed: malformed JSON response.")
        return body


class RemoteNotionMCPClient:
    def __init__(self) -> None:
        self._oauth = NotionOAuthClient()

    def ensure_valid_connection(
        self,
        connection: NotionConnection,
        *,
        on_refresh: Callable[[TokenExchangeResult], NotionConnection] | None = None,
    ) -> NotionConnection:
        if connection.expires_at and connection.expires_at <= datetime.now(UTC) + timedelta(minutes=5):
            refreshed = self._oauth.refresh_token(connection)
            if on_refresh is None:
                raise NotionOAuthError("Missing refresh handler for expired Notion connection.")
            return on_refresh(refreshed)
        return connection

    def search_page(self, connection: NotionConnection, title: str) -> dict[str, object] | None:
        response = self.call_tool(
            connection,
            tool_name="notion-search",
            arguments={"query": title},
        )
        results = response.get("results")
        if not isinstance(results, list):
            return None
        normalized_title = title.strip().lower()
        for item in results:
            if not isinstance(item, dict):
                continue
            item_title = self._extract_page_title(item)
            if item_title.strip().lower() == normalized_title:
                return item
        return None

    def _extract_page_title(self, page: dict[str, object]) -> str:
        # Simple top-level title (MCP-simplified format)
        top_level = page.get("title")
        if isinstance(top_level, str) and top_level.strip():
            return top_level
        # Notion API format: properties.title.title[].plain_text
        properties = page.get("properties")
        if isinstance(properties, dict):
            for prop in properties.values():
                if not isinstance(prop, dict):
                    continue
                if prop.get("type") == "title" or prop.get("id") == "title":
                    title_list = prop.get("title")
                    if isinstance(title_list, list) and title_list:
                        return str(title_list[0].get("plain_text", ""))
        return ""

    def create_child_page(
        self,
        connection: NotionConnection,
        *,
        parent_page_id: str,
        title: str,
        markdown: str,
    ) -> dict[str, object]:
        create_attempts = [
            {
                "parent": {"type": "page_id", "page_id": parent_page_id},
                "pages": [
                    {
                        "properties": {"title": title},
                        "content": markdown,
                    }
                ],
            },
            {
                "parent": {"page_id": parent_page_id},
                "pages": [
                    {
                        "properties": {"title": title},
                        "content": markdown,
                    }
                ],
            },
            {
                "parent_id": parent_page_id,
                "pages": [
                    {
                        "properties": {"title": title},
                        "content": markdown,
                    }
                ],
            },
            {
                "parent_id": parent_page_id,
                "pages": [
                    {
                        "properties": {"Name": title},
                        "content": markdown,
                    }
                ],
            },
        ]
        for arguments in create_attempts:
            response = self.call_tool(
                connection,
                tool_name="notion-create-pages",
                arguments=arguments,
            )
            logger.info(
                "Notion create-pages response",
                extra={
                    "tool": "notion-create-pages",
                    "arguments": arguments,
                    "response": response,
                },
            )
            extracted = self.extract_page_reference(response)
            if extracted["page_id"] or extracted["page_url"]:
                return response
        raise NotionOAuthError(
            "Notion create-pages did not return a verifiable page reference. "
            f"Last response: {self._summarize_payload(response)}"
        )

    def fetch_page(self, connection: NotionConnection, page_ref: str) -> dict[str, object]:
        response = self.call_tool(
            connection,
            tool_name="notion-fetch",
            arguments={"id": page_ref},
        )
        logger.info(
            "Notion fetch response",
            extra={"tool": "notion-fetch", "page_ref": page_ref, "response": response},
        )
        return response

    def get_workspace_info(self, connection: NotionConnection) -> tuple[str | None, str | None]:
        try:
            payload = self.call_tool(connection, tool_name="notion-get-self", arguments={})
        except Exception:
            return None, None
        workspace_name = None
        workspace_id = None
        if isinstance(payload, dict):
            workspace_name = self._deep_find_string(payload, ("workspace_name", "name"))
            workspace_id = self._deep_find_string(payload, ("workspace_id", "workspaceId", "id"))
        return workspace_id, workspace_name

    def call_tool(
        self,
        connection: NotionConnection,
        *,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running — safe to use asyncio.run()
            return asyncio.run(self._call_tool_async(connection, tool_name=tool_name, arguments=arguments))

        # Already in an event loop (e.g. FastAPI) — run in a separate thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                self._call_tool_async(connection, tool_name=tool_name, arguments=arguments),
            )
            return future.result(timeout=60)

    def extract_page_reference(self, payload: dict[str, object]) -> dict[str, str | None]:
        page_url = self._deep_find_string(payload, ("url", "public_url"))
        if not page_url:
            page_url = self._extract_url_from_text(payload)
        page_id = self._find_page_id(payload)
        if not page_id:
            page_id = self._extract_id_from_text(payload)
        return {"page_id": page_id, "page_url": page_url}

    async def _call_tool_async(
        self,
        connection: NotionConnection,
        *,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        headers = {
            "Authorization": f"Bearer {connection.access_token}",
            "User-Agent": "TailoredAI-NotionMCP/1.0",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as http_client:
            try:
                return await self._call_tool_streamable(http_client, tool_name, arguments)
            except Exception:
                if sse_client is None:
                    raise
                return await self._call_tool_sse(headers, tool_name, arguments)

    async def _call_tool_streamable(
        self,
        http_client: httpx.AsyncClient,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        async with streamable_http_client(
            settings.notion_mcp_server_url,
            http_client=http_client,
        ) as streams:
            read_stream, write_stream = self._extract_stream_pair(streams)
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                return self._normalize_tool_result(result)

    async def _call_tool_sse(
        self,
        headers: dict[str, str],
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        try:
            async with sse_client(settings.notion_mcp_sse_url, headers=headers) as streams:
                read_stream, write_stream = self._extract_stream_pair(streams)
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
                    return self._normalize_tool_result(result)
        except TypeError:
            async with sse_client(settings.notion_mcp_sse_url) as streams:
                read_stream, write_stream = self._extract_stream_pair(streams)
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
                    return self._normalize_tool_result(result)

    def _normalize_tool_result(self, result: object) -> dict[str, object]:
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return structured
        if structured is not None:
            return {"result": structured}

        content = getattr(result, "content", None)
        if isinstance(content, list):
            texts: list[str] = []
            for block in content:
                text_value = getattr(block, "text", None)
                if isinstance(text_value, str) and text_value.strip():
                    texts.append(text_value)
            if len(texts) == 1:
                try:
                    parsed = json.loads(texts[0])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
            if texts:
                return {"content": texts}
        return {}

    def _deep_find_string(self, payload: object, keys: tuple[str, ...]) -> str | None:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            for value in payload.values():
                found = self._deep_find_string(value, keys)
                if found:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = self._deep_find_string(value, keys)
                if found:
                    return found
        return None

    def _find_page_id(self, payload: object) -> str | None:
        if isinstance(payload, dict):
            object_type = payload.get("object")
            if object_type == "page" and isinstance(payload.get("id"), str):
                return str(payload["id"])
            if isinstance(payload.get("page_id"), str):
                return str(payload["page_id"])
            for value in payload.values():
                found = self._find_page_id(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = self._find_page_id(value)
                if found:
                    return found
        return None

    def _extract_url_from_text(self, payload: object) -> str | None:
        for text in self._collect_text(payload):
            match = NOTION_URL_RE.search(text)
            if match:
                return match.group(0)
        return None

    def _extract_id_from_text(self, payload: object) -> str | None:
        for text in self._collect_text(payload):
            match = UUID_RE.search(text)
            if match:
                return match.group(0)
        return None

    def _collect_text(self, payload: object) -> list[str]:
        if isinstance(payload, str):
            return [payload]
        if isinstance(payload, dict):
            collected: list[str] = []
            for value in payload.values():
                collected.extend(self._collect_text(value))
            return collected
        if isinstance(payload, list):
            collected: list[str] = []
            for value in payload:
                collected.extend(self._collect_text(value))
            return collected
        return []

    def _summarize_payload(self, payload: object) -> str:
        try:
            raw = json.dumps(payload, ensure_ascii=True)
        except TypeError:
            raw = str(payload)
        if len(raw) > 600:
            return raw[:597] + "..."
        return raw

    def _extract_stream_pair(self, streams: object) -> tuple[object, object]:
        if isinstance(streams, tuple) and len(streams) >= 2:
            return streams[0], streams[1]
        if isinstance(streams, list) and len(streams) >= 2:
            return streams[0], streams[1]
        raise NotionOAuthError("MCP transport returned an unexpected stream shape.")
