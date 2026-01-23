"""WebSocket endpoint for real-time updates."""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from src.core.websocket import global_ws_manager
from src.api.routes.auth import verify_access_token

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None, description="JWT access token"),
):
    """WebSocket endpoint for real-time events.

    Events sent:
    - node.created: New node discovered
    - node.state_changed: Node state transition
    - node.updated: Node data updated
    - install.progress: Installation progress update
    - approval.requested: New approval request
    - approval.resolved: Approval approved/rejected
    """
    # Validate token if provided (auth is optional for now during development)
    user_info = None
    if token:
        payload = verify_access_token(token)
        if payload:
            user_info = {"id": payload.get("sub"), "username": payload.get("username")}
        else:
            logger.warning("WebSocket connection with invalid token")
            # Still allow connection but log it

    await global_ws_manager.connect(websocket)
    logger.info(f"WebSocket connected. User: {user_info or 'anonymous'}")

    try:
        while True:
            # Keep connection alive and handle any incoming messages
            data = await websocket.receive_text()
            # For now, just echo back or ignore client messages
            # Could implement ping/pong or other commands here
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await global_ws_manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected. User: {user_info or 'anonymous'}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await global_ws_manager.disconnect(websocket)
