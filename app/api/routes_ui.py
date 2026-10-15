"""Dashboard UI router and health check endpoint."""

import os
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.services.hospital_client import HospitalClient

router = APIRouter(tags=["UI & Health"])

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))


@router.get("/", summary="Web Dashboard", include_in_schema=False)
async def serve_dashboard():
    """Serve the interactive web demonstration dashboard."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse(
        content={
            "service": "Hospital Bulk Processing System",
            "docs": "/docs",
            "health": "/health",
        }
    )


@router.get("/health", summary="Health Check", tags=["Monitoring"])
async def health_check():
    """Health check endpoint for Render and container orchestrators."""
    settings = get_settings()
    client = HospitalClient(settings=settings)
    upstream_ok = await client.check_health()
    return {
        "status": "healthy",
        "service": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "upstream_api_connected": upstream_ok,
    }
