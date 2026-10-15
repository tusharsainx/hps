"""API router aggregation."""

from fastapi import APIRouter
from app.api.routes_bulk import router as bulk_router
from app.api.routes_status import router as status_router
from app.api.routes_ws import router as ws_router
from app.api.routes_ui import router as ui_router

api_router = APIRouter()
api_router.include_router(ui_router)
api_router.include_router(bulk_router)
api_router.include_router(status_router)
api_router.include_router(ws_router)

__all__ = ["api_router"]
