"""Centralized configuration for CareerCopilot AI using pydantic-settings."""

import os
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Vercel Functions have a read-only filesystem except for /tmp. Keep local
# development on the repo-level SQLite file, but use /tmp on Vercel so the app
# can create/write its database instead of crashing on startup.
_ON_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))


class Settings(BaseSettings):
    """Application settings loaded from environment variables with sensible defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CC_",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "CareerCopilot AI"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── Redis (optional — used by the rate limiter when reachable) ──────────
    redis_url: str = "" if _ON_VERCEL else "redis://localhost:6379/0"

    # ── Database ──────────────────────────────────────────────────────────────
    # Neon / Postgres. Accepts both the app-style CC_DATABASE_URL and the
    # conventional DATABASE_URL used by Neon's dashboard. When set, it takes
    # precedence over SQLite (including on Vercel, where SQLite is ephemeral).
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("CC_DATABASE_URL", "DATABASE_URL"),
    )

    # SQLite fallback for local development (relative paths resolve to the repo root).
    sqlite_path: str = "/tmp/rolematcher.db" if _ON_VERCEL else "data/rolematcher.db"

    # ── LLM Providers ───────────────────────────────────────────────────────
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    qwen_api_key: str = ""

    # Model routing
    fast_model: str = "gemini/gemini-2.5-flash-lite"
    strong_model: str = "gemini/gemini-2.5-flash"

    # Generation defaults
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096

    # ── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # ── File Upload ──────────────────────────────────────────────────────────
    max_upload_size_mb: int = 10
    allowed_upload_extensions: list[str] = [".pdf", ".docx", ".txt"]

    # ── SMTP Email ───────────────────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "RoleMatcherAI"
    smtp_use_tls: bool = True

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
