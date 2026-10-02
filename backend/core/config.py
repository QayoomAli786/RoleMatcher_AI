"""Centralized configuration for CareerCopilot AI using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    redis_url: str = "redis://localhost:6379/0"

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

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
