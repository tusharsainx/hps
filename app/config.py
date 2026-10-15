"""Application configuration and environment settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration managed via environment variables."""

    # Upstream Hospital Directory API
    HOSPITAL_API_BASE_URL: str = "https://hospital-directory.onrender.com"

    # Concurrency and Performance Controls
    CONCURRENCY_LIMIT: int = 10
    MAX_CSV_ROWS: int = 20
    REQUEST_TIMEOUT_SECONDS: float = 15.0
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_BASE: float = 0.5
    MAX_CONNECTIONS: int = 50
    MAX_KEEPALIVE_CONNECTIONS: int = 20

    # In-memory batch cache limit (evicts oldest when full)
    MAX_BATCH_STORE_SIZE: int = 10000

    # Enterprise Scaling & Pluggable Backends
    STORAGE_BACKEND: str = "memory"  # Options: 'memory', 'redis', 'database'
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = "sqlite:///./batches.db"
    EXECUTION_ENGINE: str = "asyncio"  # Options: 'asyncio', 'distributed'
    DISTRIBUTED_PUBSUB_ENABLED: bool = False
    GLOBAL_RATE_LIMIT_RPS: int = 25

    # Application Metadata
    APP_TITLE: str = "Hospital Bulk Processing System"
    APP_DESCRIPTION: str = (
        "High-performance bulk ingestion and batch management service integrating "
        "with the Paribus Hospital Directory API."
    )
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
