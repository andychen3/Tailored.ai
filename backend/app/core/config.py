import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv


ROOT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(ROOT_ENV_PATH, override=False)


def _parse_cors_origins(raw_value: str | None) -> list[str]:
    if not raw_value:
        return ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def _parse_int(raw_value: str | None, default: int) -> int:
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


class Settings:
    def __init__(self) -> None:
        self.app_title = os.getenv("APP_TITLE", "Tailored AI API")
        self.cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS"))
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
        self.source_reconcile_interval_seconds = _parse_int(
            os.getenv("SOURCE_RECONCILE_INTERVAL_SECONDS"),
            6 * 60 * 60,
        )


settings = Settings()
