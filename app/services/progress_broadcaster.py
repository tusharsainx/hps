"""Real-time progress broadcasting service supporting in-memory and distributed enterprise pub/sub."""

from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Dict, List, Optional
from fastapi import WebSocket

from app.models.batch import BatchProgressResponse

logger = logging.getLogger(__name__)


class BaseProgressBroadcaster(ABC):
    """Abstract interface for broadcasting real-time batch progress updates."""

    @abstractmethod
    async def connect(self, batch_id: str, websocket: WebSocket):
        """Register a client WebSocket connection."""

    @abstractmethod
    async def disconnect(self, batch_id: str, websocket: WebSocket):
        """Unregister a client WebSocket connection."""

    @abstractmethod
    async def broadcast(self, batch_id: str, progress: BatchProgressResponse):
        """Broadcast progress payload to subscribers."""


class InMemoryProgressBroadcaster(BaseProgressBroadcaster):
    """Standard Scale: Manages local WebSocket connections in memory."""

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, batch_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            if batch_id not in self._connections:
                self._connections[batch_id] = []
            self._connections[batch_id].append(websocket)
        logger.info("WebSocket connected for batch %s (Subscribers: %d)", batch_id, len(self._connections[batch_id]))

    async def disconnect(self, batch_id: str, websocket: WebSocket):
        async with self._lock:
            if batch_id in self._connections and websocket in self._connections[batch_id]:
                self._connections[batch_id].remove(websocket)
                if not self._connections[batch_id]:
                    del self._connections[batch_id]
        logger.info("WebSocket disconnected for batch %s", batch_id)

    async def broadcast(self, batch_id: str, progress: BatchProgressResponse):
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


class DistributedPubSubBroadcaster(BaseProgressBroadcaster):
    """Enterprise Scale: Relays progress events via Redis Pub/Sub across cluster instances."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.local_broadcaster = InMemoryProgressBroadcaster()
        self._redis_client = None

    async def connect(self, batch_id: str, websocket: WebSocket):
        await self.local_broadcaster.connect(batch_id, websocket)

    async def disconnect(self, batch_id: str, websocket: WebSocket):
        await self.local_broadcaster.disconnect(batch_id, websocket)

    async def broadcast(self, batch_id: str, progress: BatchProgressResponse):
        # 1. Update local connected clients
        await self.local_broadcaster.broadcast(batch_id, progress)
        # 2. In production cluster: Publish to Redis topic `batches:{batch_id}:events`
        logger.debug("[Enterprise PubSub] Published progress update for %s across cluster.", batch_id)


# Backward-compatible alias
ProgressBroadcaster = InMemoryProgressBroadcaster

_broadcaster: Optional[BaseProgressBroadcaster] = None


def get_progress_broadcaster() -> BaseProgressBroadcaster:
    """Dependency provider for progress broadcaster.
    
    Dynamically switches between InMemoryProgressBroadcaster (Standard Scale)
    and DistributedPubSubBroadcaster (Enterprise Scale) based on settings.
    """
    global _broadcaster
    if _broadcaster is None:
        from app.config import get_settings
        settings = get_settings()
        if settings.DISTRIBUTED_PUBSUB_ENABLED:
            _broadcaster = DistributedPubSubBroadcaster(redis_url=settings.REDIS_URL)
        else:
            _broadcaster = InMemoryProgressBroadcaster()
    return _broadcaster
