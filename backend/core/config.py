"""Centralized configuration for CareerCopilot AI using pydantic-settings."""

from functools import lru_cache
from pathlib import Path

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
    environment: str = "development"  # development | staging | production

    # ── Database ─────────────────────────────────────────────────────────────
    postgres_url: str = "sqlite+aiosqlite:///./careercopilot.db"
    postgres_url_sync: str = "sqlite:///./careercopilot.db"
    redis_url: str = "redis://localhost:6379/0"

    # ── LLM Providers ───────────────────────────────────────────────────────
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str | None = None
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Model routing
    fast_model: str = "gemini/gemini-2.5-flash-lite"
    strong_model: str = "gemini/gemini-2.5-flash"
    embedding_model: str = "text-embedding-004"

    # Generation defaults
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    embedding_dimensions: int = 1536

    # ── JWT / Auth ───────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours

    # ── Storage ──────────────────────────────────────────────────────────────
    storage_backend: str = "local"  # local | s3
    storage_base_path: Path = Path("storage")
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # ── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # ── File Upload ──────────────────────────────────────────────────────────
    max_upload_size_mb: int = 10
    allowed_upload_extensions: list[str] = [".pdf", ".docx", ".txt"]

    # ── Vector Store ─────────────────────────────────────────────────────────
    vector_store_backend: str = "pgvector"  # pgvector | pinecone | chroma
    pinecone_index: str = ""
    pinecone_api_key: str = ""

    # ── Celery / Background Tasks ────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
