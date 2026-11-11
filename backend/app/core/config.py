"""Application settings, loaded from environment variables (and `.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["dev", "test", "staging", "prod"]

_INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me-0123456789abcdef"  # noqa: S105 (dev default, rejected in prod)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: AppEnv = "dev"
    app_name: str = "Play Laser Tag API"
    log_level: str = "INFO"

    # Async SQLAlchemy URL, e.g. mysql+asyncmy://user:pass@mysql:3306/playlasertag?charset=utf8mb4
    database_url: str = "mysql+asyncmy://plt:plt@localhost:3306/playlasertag?charset=utf8mb4"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_echo: bool = False

    # Empty string means "no Redis" (allowed only outside prod/staging; in-memory fallbacks are used).
    redis_url: str = ""

    jwt_secret: SecretStr = SecretStr(_INSECURE_DEFAULT_SECRET)
    jwt_issuer: str = "playlasertag"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 14 * 24 * 3600
    quote_ttl_seconds: int = 15 * 60
    refresh_cookie_secure: bool = True

    login_max_failures: int = 5
    login_lockout_seconds: int = 15 * 60
    login_rate_limit_per_minute: int = 5
    public_rate_limit_per_minute: int = 30
    booking_rate_limit_per_minute: int = 10

    # --- voice (ADR-005/007): provider keys stay on the server; the kiosk never sees them ---
    voice_provider: Literal["openai", "gemini", "scripted"] = "gemini"
    openai_api_key: SecretStr | None = None
    openai_realtime_model: str = "gpt-realtime-2.1-mini"
    openai_voice: str = "marin"
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    gemini_api_key: SecretStr | None = None
    gemini_live_model: str = "gemini-3.8-live"
    gemini_voice: str = "Kore"
    voice_max_session_seconds: int = 600

    cors_origins: list[str] = Field(default_factory=list)
    business_timezone: str = "Asia/Kolkata"
    check_migrations_on_ready: bool = True
    expose_docs: bool = True

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app_env in ("prod", "staging"):
            secret = self.jwt_secret.get_secret_value()
            if secret == _INSECURE_DEFAULT_SECRET or len(secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of at least 32 characters")
            if not self.redis_url:
                raise ValueError("REDIS_URL is required in staging/prod")
            if self.voice_provider == "scripted":
                raise ValueError("VOICE_PROVIDER=scripted is a test double and can't run in staging/prod")
            if not self.refresh_cookie_secure:
                raise ValueError("REFRESH_COOKIE_SECURE must be true in staging/prod")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
