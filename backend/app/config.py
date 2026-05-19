import json
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    anthropic_api_key: str
    app_auth_token: str
    database_url: str = "postgresql+asyncpg://agents:agents_local_dev@postgres:5432/agents"
    redis_url: str = "redis://redis:6379/0"

    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_chat_id: str = ""
    telegram_webhook_secret: str = ""

    # Notion
    notion_api_token: str = ""
    notion_watched_boards: list[str] = []

    # Transcripción de voz (Whisper via OpenAI o local con faster-whisper)
    openai_api_key: str = ""
    whisper_model: str = "base"  # tiny | base | small | medium — solo aplica al modo local

    # Gmail
    gmail_oauth_token: str = ""
    gmail_watcher_enabled: bool = False
    gmail_watched_labels: list[str] = ["INBOX"]

    # Calendar
    calendar_oauth_token: str = ""
    calendar_watcher_enabled: bool = False

    # Security
    allowed_working_dirs: list[str] = []
    max_cost_per_session_usd: float = 5.0
    max_cost_per_day_usd: float = 20.0
    security_strict_mode: bool = True
    security_notify_level: str = "warning"

    @field_validator(
        "notion_watched_boards", "allowed_working_dirs", "gmail_watched_labels",
        mode="before",
    )
    @classmethod
    def parse_json_list(cls, v: str | list) -> list:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v]
        return v


settings = Settings()
