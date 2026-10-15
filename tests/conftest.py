"""Pytest fixtures and configuration."""

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport

from main import app
from app.config import Settings, get_settings


@pytest.fixture
def test_settings() -> Settings:
    """Return test settings with fast retries and mock URL."""
    return Settings(
        HOSPITAL_API_BASE_URL="https://mock-hospital-api.paribus.test",
        CONCURRENCY_LIMIT=5,
        MAX_CSV_ROWS=20,
        REQUEST_TIMEOUT_SECONDS=2.0,
        MAX_RETRIES=2,
        RETRY_BACKOFF_BASE=0.01,
        DEBUG=True,
    )


@pytest_asyncio.fixture
async def async_client():
    """Async HTTP test client bound directly to the FastAPI ASGI application."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def valid_5_csv_bytes() -> bytes:
    """Bytes for a valid 5-row CSV."""
    return (
        b"name,address,phone\n"
        b"Hospital A,100 Alpha St,555-0001\n"
        b"Hospital B,200 Beta St,555-0002\n"
        b"Hospital C,300 Gamma St,\n"
        b"Hospital D,400 Delta St,555-0004\n"
        b"Hospital E,500 Epsilon St,555-0005\n"
    )


@pytest.fixture
def valid_20_csv_bytes() -> bytes:
    """Bytes for a valid 20-row CSV (maximum allowed)."""
    rows = [f"Hospital {i},{i * 10} Main St,555-01{i:02d}" for i in range(1, 21)]
    return ("name,address,phone\n" + "\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def exceed_limit_csv_bytes() -> bytes:
    """Bytes for a 25-row CSV exceeding the 20-row limit."""
    rows = [f"Hospital {i},{i * 10} Main St,555-01{i:02d}" for i in range(1, 26)]
    return ("name,address,phone\n" + "\n".join(rows) + "\n").encode("utf-8")
