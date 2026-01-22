"""Service for logging node lifecycle events."""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Node, NodeEvent

logger = logging.getLogger(__name__)


class EventService:
    """Log node lifecycle events to the database."""

    @staticmethod
    async def log_event(
        db: AsyncSession,
        node: Node,
        event_type: str,
        status: str = "success",
        message: str | None = None,
        progress: int | None = None,
        metadata: dict | None = None,
        ip_address: str | None = None,
    ) -> NodeEvent:
        """
        Log a node lifecycle event.

        Args:
            db: Database session
            node: Node the event belongs to
            event_type: Type of event (boot_started, install_complete, etc.)
            status: Event status (success, failed, in_progress)
            message: Optional message
            progress: Optional progress percentage (0-100)
            metadata: Optional metadata dict
            ip_address: Client IP address

        Returns:
            Created NodeEvent
        """
        event = NodeEvent(
            node_id=node.id,
            event_type=event_type,
            status=status,
            message=message,
            progress=progress,
            metadata_json=json.dumps(metadata) if metadata else None,
            ip_address=ip_address,
        )
        db.add(event)

        logger.info(
            f"Node {node.id} event: {event_type} ({status})"  # nosec - MAC omitted
        )

        return event
