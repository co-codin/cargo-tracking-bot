"""Настройки приложения из переменных окружения / .env (pydantic-settings)."""
import secrets
from typing import Optional

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: Optional[SecretStr] = None
    # https://example.com — публичный адрес; если не задан, бот работает через long polling
    webhook_url: Optional[str] = None
    webhook_secret: str = secrets.token_urlsafe(24)
    redis_url: Optional[str] = None
    cache_ttl: int = 300
    cache_log_level: str = "INFO"
    log_level: str = "INFO"
    source_url: str = "https://cgr.qoldau.kz/ru/information/stat"
    run_bot: bool = True

    @field_validator("webhook_secret", mode="before")
    @classmethod
    def _secret(cls, v):
        return v or secrets.token_urlsafe(24)

    @field_validator("webhook_url", "redis_url", mode="before")
    @classmethod
    def _empty_none(cls, v):
        return v or None


settings = Settings()
