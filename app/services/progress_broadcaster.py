"""Real-time progress broadcasting service for WebSocket subscribers."""

import asyncio
import logging
from typing import Dict, List, Optional
from fastapi import WebSocket

from app.models.batch import BatchProgressResponse

logger = logging.getLogger(__name__)


class ProgressBroadcaster:
    """Manages active WebSocket connections per batch ID and broadcasts live updates."""

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, batch_id: str, websocket: WebSocket):
        """Accept and register a new WebSocket connection for a batch ID."""
        await websocket.accept()
        async with self._lock:
            if batch_id not in self._connections:
                self._connections[batch_id] = []
            self._connections[batch_id].append(websocket)
        logger.info("WebSocket connected for batch %s (Subscribers: %d)", batch_id, len(self._connections[batch_id]))

    async def disconnect(self, batch_id: str, websocket: WebSocket):
        """Unregister a client WebSocket connection."""
        async with self._lock:
            if batch_id in self._connections and websocket in self._connections[batch_id]:
                self._connections[batch_id].remove(websocket)
                if not self._connections[batch_id]:
                    del self._connections[batch_id]
        logger.info("WebSocket disconnected for batch %s", batch_id)

    async def broadcast(self, batch_id: str, progress: BatchProgressResponse):
        """Broadcast progress payload to subscribers."""
        async with self._lock:
            subscribers = list(self._connections.get(batch_id, []))

        if not subscribers:
            return

        payload = progress.model_dump()
        dead_connections: List[WebSocket] = []

        for ws in subscribers:
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.debug("Failed sending update to client on batch %s: %s", batch_id, exc)
                dead_connections.append(ws)

        if dead_connections:
            async with self._lock:
                current_subs = self._connections.get(batch_id, [])
                for dead_ws in dead_connections:
                    if dead_ws in current_subs:
                        current_subs.remove(dead_ws)
                if not current_subs and batch_id in self._connections:
                    del self._connections[batch_id]


_broadcaster: Optional[ProgressBroadcaster] = None


def get_progress_broadcaster() -> ProgressBroadcaster:
    """Dependency provider for the singleton ProgressBroadcaster instance."""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = ProgressBroadcaster()
    return _broadcaster
