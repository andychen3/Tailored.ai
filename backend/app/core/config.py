import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(ROOT_ENV_PATH, override=False)


def _parse_cors_origins(raw_value: str | None) -> list[str]:
    if not raw_value:
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    return [
        origin.strip()
        for origin in raw_value.split(",")
        if origin.strip()
    ]


def _parse_int(raw_value: str | None, default: int) -> int:
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _parse_csv(raw_value: str | None, default: list[str]) -> list[str]:
    if not raw_value:
        return default
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    return values or default


def _parse_model_limits(
    raw_value: str | None,
    allowed_models: list[str],
) -> dict[str, int]:
    default_limit = 128000
    limits = {model: default_limit for model in allowed_models}
    if not raw_value:
        return limits

    for item in raw_value.split(","):
        token = item.strip()
        if not token or ":" not in token:
            continue
        model, limit_str = token.split(":", 1)
        model = model.strip()
        limit_str = limit_str.strip()
        if not model:
            continue
        try:
            parsed_limit = int(limit_str)
        except ValueError:
            continue
        if parsed_limit > 0:
            limits[model] = parsed_limit
    return limits


class Settings:
    def __init__(self) -> None:
        self.app_title = os.getenv("APP_TITLE", "Tailored AI API")
        self.cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS"))
        self.frontend_app_url = os.getenv("FRONTEND_APP_URL", "http://localhost:5173")
        self.max_file_bytes = _parse_int(
            os.getenv("MAX_FILE_BYTES"),
            3 * 1024 * 1024 * 1024,
        )
        self.upload_staging_dir = os.getenv(
            "UPLOAD_STAGING_DIR",
            os.path.join(tempfile.gettempdir(), "tailored_ai_uploads"),
        )
        self.sources_db_path = os.getenv(
            "SOURCES_DB_PATH",
            os.path.join(tempfile.gettempdir(), "tailored_ai_sources.sqlite3"),
        )
        self.chat_db_path = os.getenv(
            "CHAT_DB_PATH",
            os.path.join(tempfile.gettempdir(), "tailored_ai_chat.sqlite3"),
        )
        self.integration_db_path = os.getenv(
            "INTEGRATION_DB_PATH",
            self.chat_db_path,
        )
        self.chat_allowed_models = _parse_csv(
            os.getenv("CHAT_ALLOWED_MODELS"),
            ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1"],
        )
        self.chat_model_context_limits = _parse_model_limits(
            os.getenv("CHAT_MODEL_CONTEXT_LIMITS"),
            self.chat_allowed_models,
        )
        self.source_reconcile_interval_seconds = _parse_int(
            os.getenv("SOURCE_RECONCILE_INTERVAL_SECONDS"),
            6 * 60 * 60,
        )
        self.notion_mcp_server_url = os.getenv(
            "NOTION_MCP_SERVER_URL",
            "https://mcp.notion.com/mcp",
        )
        self.notion_mcp_sse_url = os.getenv(
            "NOTION_MCP_SSE_URL",
            "https://mcp.notion.com/sse",
        )
        self.notion_conversation_notes_page_id = os.getenv(
            "NOTION_CONVERSATION_NOTES_PAGE_ID",
            "",
        )
        self.notion_oauth_redirect_path = os.getenv(
            "NOTION_OAUTH_REDIRECT_PATH",
            "/integrations/notion/callback",
        )


settings = Settings()
