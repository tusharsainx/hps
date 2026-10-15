"""FastAPI Application entry point for Hospital Bulk Processing System."""

from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import get_settings
from app.services.hospital_client import UpstreamApiException
from app.services.csv_validator import CsvValidationException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

settings = get_settings()
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    logger.info("Starting %s v%s...", settings.APP_TITLE, settings.APP_VERSION)
    logger.info("Connected to Upstream API: %s", settings.HOSPITAL_API_BASE_URL)
    logger.info("Max CSV Rows: %d | Concurrency Limit: %d", settings.MAX_CSV_ROWS, settings.CONCURRENCY_LIMIT)
    yield
    logger.info("Shutting down %s...", settings.APP_TITLE)


app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if directory exists
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include all API routes
app.include_router(api_router)


# Global Exception Handlers
@app.exception_handler(CsvValidationException)
async def csv_validation_exception_handler(request: Request, exc: CsvValidationException):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
