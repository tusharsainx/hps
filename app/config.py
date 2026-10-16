import os
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ENV_FILE = os.path.join(_ROOT_DIR, ".env")


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
    BATCH_TTL_SECONDS: int = 86400  # Automatically evicts completed batches older than 24 hours

    # Application Metadata
    APP_TITLE: str = "Hospital Bulk Processing System"
    APP_DESCRIPTION: str = (
        "High-performance bulk ingestion and batch management service integrating "
        "with the Paribus Hospital Directory API."
    )
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=(".env", _ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
