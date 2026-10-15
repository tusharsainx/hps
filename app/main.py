"""FastAPI Application entry point for Hospital Bulk Processing System."""

import sys
from pathlib import Path

# Ensure project root is in sys.path so running from either project root
# (uvicorn app.main:app) or within the app/ directory (uvicorn main:app) works seamlessly
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.config import get_settings
from app.services.hospital_client import HospitalClient, UpstreamApiException
from app.services.csv_validator import CsvValidationException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

settings = get_settings()


async def _keep_alive_heartbeat_loop():
    """Periodically ping upstream Render API to prevent free-tier sleep (15 min inactivity timeout)."""
    # Brief initial pause after server boot before firing first keep-alive ping
    await asyncio.sleep(5)
    client = HospitalClient(settings=settings)
    try:
        while True:
            try:
                upstream_ok = await client.check_health()
                logger.info(
                    "[Heartbeat] Upstream Render API ping: %s (URL: %s)",
                    "ONLINE" if upstream_ok else "UNREACHABLE",
                    settings.HOSPITAL_API_BASE_URL,
                )
            except Exception as exc:
                logger.warning("[Heartbeat] Upstream ping failed: %s", exc)

            if settings.SELF_PING_URL:
                try:
                    c = await client._get_client()
                    resp = await c.get(settings.SELF_PING_URL, timeout=10.0)
                    logger.info("[Heartbeat] Self ping status: %d (URL: %s)", resp.status_code, settings.SELF_PING_URL)
                except Exception as exc:
                    logger.warning("[Heartbeat] Self ping failed: %s", exc)

            await asyncio.sleep(settings.KEEP_ALIVE_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("[Heartbeat] Keep-Alive loop terminated cleanly.")
    finally:
        await client.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager with automated Keep-Alive heartbeat."""
    logger.info("Starting %s v%s...", settings.APP_TITLE, settings.APP_VERSION)
    logger.info("Connected to Upstream API: %s", settings.HOSPITAL_API_BASE_URL)
    logger.info("Max CSV Rows: %d | Concurrency Limit: %d", settings.MAX_CSV_ROWS, settings.CONCURRENCY_LIMIT)

    heartbeat_task = None
    if settings.KEEP_ALIVE_ENABLED:
        heartbeat_task = asyncio.create_task(_keep_alive_heartbeat_loop())
        logger.info(
            "Render Keep-Alive Heartbeat active (interval: %ds / %.1f min).",
            settings.KEEP_ALIVE_INTERVAL_SECONDS,
            settings.KEEP_ALIVE_INTERVAL_SECONDS / 60,
        )

    yield

    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    logger.info("Shutting down %s...", settings.APP_TITLE)


openapi_tags = [
    {
        "name": "Bulk Processing",
        "description": "Endpoints to ingest CSV files, pre-validate schemas, resume failed operations, and rollback batches.",
    },
    {
        "name": "Batch Status & Progress",
        "description": "Polling endpoints to monitor batch progress, execution metrics, and list historical batches.",
    },
    {
        "name": "Monitoring",
        "description": "Health check probes for service availability and upstream directory connectivity.",
    },
]

app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=openapi_tags,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API routes
app.include_router(api_router)


# Global Exception Handlers
@app.exception_handler(CsvValidationException)
async def csv_validation_exception_handler(request: Request, exc: CsvValidationException):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": "CSV Validation Failed",
            "message": exc.message,
            "details": [e.model_dump() for e in exc.errors],
        },
    )


@app.exception_handler(UpstreamApiException)
async def upstream_api_exception_handler(request: Request, exc: UpstreamApiException):
    return JSONResponse(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        content={
            "error": "Upstream API Error",
            "message": exc.message,
            "details": exc.details,
        },
    )
