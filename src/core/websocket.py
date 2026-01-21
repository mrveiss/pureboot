"""WebSocket connection manager for real-time updates."""
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class SyncWebSocketManager:
    """Manages WebSocket connections for sync progress updates."""

    def __init__(self):
        # job_id -> set of connected websockets
        self.connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        """Accept connection and register for job updates."""
        await websocket.accept()
        if job_id not in self.connections:
            self.connections[job_id] = set()
        self.connections[job_id].add(websocket)
        logger.info(f"WebSocket connected for job {job_id}")

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        """Remove connection on disconnect."""
        if job_id in self.connections:
            self.connections[job_id].discard(websocket)
            if not self.connections[job_id]:
                del self.connections[job_id]
        logger.info(f"WebSocket disconnected for job {job_id}")

    async def broadcast_progress(self, job_id: str, progress: dict) -> None:
        """Send progress update to all connections watching this job."""
        if job_id not in self.connections:
            return

        dead_connections = []
        for ws in self.connections[job_id]:
            try:
                await ws.send_json(progress)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.append(ws)

        for ws in dead_connections:
            self.connections[job_id].discard(ws)

    def get_connection_count(self, job_id: str) -> int:
        """Get number of active connections for a job."""
        return len(self.connections.get(job_id, set()))


# Global instance
ws_manager = SyncWebSocketManager()
