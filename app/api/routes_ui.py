"""Root router and health check endpoint."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.services.hospital_client import HospitalClient

router = APIRouter()


@router.get("/", summary="Root Redirect", include_in_schema=False)
@router.head("/", include_in_schema=False)
async def root():
    """Redirect root path to interactive Swagger OpenAPI documentation."""
    return RedirectResponse(url="/docs")


@router.get("/health", summary="Health Check", tags=["Monitoring"])
async def health_check():
    """Health check endpoint for Render, UptimeRobot, and container orchestrators."""
    settings = get_settings()
    client = HospitalClient(settings=settings)
    try:
        upstream_ok = await client.check_health()
    finally:
        await client.close()
    return {
        "status": "healthy",
        "service": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "upstream_api_connected": upstream_ok,
    }


@router.head("/health", include_in_schema=False)
async def health_check_head():
    """HEAD probe for UptimeRobot and load balancers."""
    return await health_check()

