"""config.py — All settings from environment. Zero hardcoded secrets."""
from __future__ import annotations
import os
from functools import lru_cache
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )

    # Bot
    bot_token: str
    owner_id: int
    webhook_secret: str

    # Database — Railway injects DATABASE_URL automatically
    database_url: str

    # Railway auto-sets these; fallback for local dev
    railway_public_domain: Optional[str] = None
    port: int = Field(default=8000)

    # App
    log_level: str = "INFO"
    max_history_per_user: int = 50
    rate_limit_per_minute: int = 10
    rate_limit_per_day: int = 200
    default_watermark: str = "@myqrro_bot"

    @field_validator("database_url")
    @classmethod
    def normalise_db_url(cls, v: str) -> str:
        # Railway gives postgres:// — asyncpg needs postgresql+asyncpg://
        v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def webhook_host(self) -> str:
        if self.railway_public_domain:
            return f"https://{self.railway_public_domain}"
        return ""

    @property
    def is_webhook_mode(self) -> bool:
        return bool(self.railway_public_domain)

    @property
    def full_webhook_url(self) -> str:
        return f"{self.webhook_host}/webhook/{self.webhook_secret}"

    @property
    def asyncpg_url(self) -> str:
        """Raw asyncpg DSN (no SQLAlchemy prefix)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
