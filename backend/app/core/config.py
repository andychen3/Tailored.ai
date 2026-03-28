import os


def _parse_cors_origins(raw_value: str | None) -> list[str]:
    if not raw_value:
        return ["http://localhost:3000", "http://localhost:5173"]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


class Settings:
    def __init__(self) -> None:
        self.app_title = os.getenv("APP_TITLE", "Tailored AI API")
        self.cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS"))


settings = Settings()
