"""WebSocket endpoints for real-time progress streaming."""

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.progress_broadcaster import get_progress_broadcaster
from app.services.batch_repository import get_batch_repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Real-Time Progress"])


@router.websocket("/ws/batches/{batch_id}")
async def websocket_batch_progress(websocket: WebSocket, batch_id: str):
    """WebSocket stream providing real-time progress updates for a batch ID."""
    broadcaster = get_progress_broadcaster()
    repo = get_batch_repository()

    await broadcaster.connect(batch_id, websocket)

    # Immediately push current status if available
    current = repo.get_batch(batch_id)
    if current:
        try:
            await websocket.send_json(current.to_progress_response().model_dump())
        except Exception as exc:
            logger.debug("Failed sending initial state on WS for %s: %s", batch_id, exc)

    try:
        # Keep connection open and handle incoming client pings
        while True:
            # Client can send ping or text
            data = await websocket.receive_text()
            if data.strip().lower() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await broadcaster.disconnect(batch_id, websocket)
    except Exception as exc:
        logger.debug("WebSocket error for batch %s: %s", batch_id, exc)
        await broadcaster.disconnect(batch_id, websocket)
