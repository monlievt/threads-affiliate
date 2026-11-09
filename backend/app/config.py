"""app/config.py — Application settings via pydantic-settings.

Loads configuration from environment variables / .env file.
No secrets are logged or exposed in repr output.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ===== App =====
    APP_ENV: str = Field(default="development", description="Application environment")
    APP_TIMEZONE: str = Field(default="Asia/Jakarta", description="Display timezone")
    SECRET_KEY: str = Field(default="change-me-long-random", description="App secret key")
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/app.db",
        description="Async SQLAlchemy database URL",
    )

    # ===== Safety (hard limits — do NOT raise without explicit approval) =====
    HARD_MAX_POSTS_PER_DAY: int = Field(default=8, ge=1, le=50)
    HARD_MAX_REPLIES_PER_DAY: int = Field(default=10, ge=1, le=50)
    KILL_SWITCH_ON_START: bool = Field(
        default=True,
        description="Kill switch state at startup. Default ON — system will not publish.",
    )

    # ===== LLM =====
    GEMINI_MODEL_TEXT: str = Field(default="gemini-2.5-pro")
    LLM_DAILY_CALL_BUDGET: int = Field(default=200, ge=1)
    GEMINI_API_KEY: str = Field(default="", description="Gemini API key")

    # ===== Tokens & Encryption =====
    TOKEN_ENCRYPTION_KEY: str = Field(
        default="base64-32-bytes",
        description="Fernet key for encrypting Threads tokens in DB",
    )

    # ===== Threads (Meta) =====
    THREADS_API_BASE: str = Field(default="https://graph.threads.net/v1.0")
    THREADS_APP_ID: str = Field(default="")
    THREADS_APP_SECRET: str = Field(default="")
    THREADS_REDIRECT_URI: str = Field(default="https://your-domain/api/oauth/threads/callback")

    # ===== Admin =====
    ADMIN_USERNAME: str = Field(default="admin")
    ADMIN_PASSWORD_HASH: str = Field(
        default="argon2-hash-here",
        description="Argon2 hash of admin password",
    )

    # ===== Telegram =====
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_ADMIN_CHAT_ID: str = Field(default="")

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "production", "testing"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}, got: {v!r}")
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == "testing"

    def __repr__(self) -> str:
        # Never expose secrets in repr
        return f"Settings(APP_ENV={self.APP_ENV!r}, DATABASE_URL={self.DATABASE_URL!r})"


# Singleton settings instance
settings = Settings()
