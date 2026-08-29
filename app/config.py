"""Runtime settings, loaded from environment variables (and a local .env file).

Only *deployment* / *secret* values belong here — connection strings, API keys,
feature flags. Anything about how the restaurant works lives in
`restaurant_config.py` instead.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL. psycopg v3 driver -> "postgresql+psycopg://".
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/reservations"

    # Comma-separated list of origins allowed to call /api/* (the Vercel frontend).
    cors_origins: str = "http://localhost:5173"

    # Set to "1" to make the phone webhook politely decline new calls.
    kill_switch: bool = False

    # Secrets that later phases need; unused in Phase 1.
    openai_api_key: str = ""
    twilio_auth_token: str = ""
    public_host: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
