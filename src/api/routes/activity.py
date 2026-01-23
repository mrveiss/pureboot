"""Global activity log API endpoints."""
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import Node, NodeEvent, NodeStateLog

router = APIRouter()


class ActivityEntry(BaseModel):
    """Single activity entry."""
    id: str
    timestamp: datetime
    type: str  # state_change, node_event
    category: str  # The specific event type or state transition
    node_id: str | None
    node_name: str | None
    message: str
    details: dict | None = None
    triggered_by: str | None = None


class ActivityListResponse(BaseModel):
    """Response for activity list."""
    data: list[ActivityEntry]
    total: int


@router.get("/activity", response_model=ActivityListResponse)
async def get_activity(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    type: Literal["state_change", "node_event"] | None = Query(None, description="Filter by activity type"),
    node_id: str | None = Query(None, description="Filter by node ID"),
    event_type: str | None = Query(None, description="Filter by event type (for node_event)"),
    since: datetime | None = Query(None, description="Filter activities since timestamp"),
    db: AsyncSession = Depends(get_db),
):
    """Get global activity log across all nodes.

    Aggregates NodeEvents and NodeStateLogs into a unified timeline.
    """
    entries: list[ActivityEntry] = []

    # Build conditions for state logs
    state_conditions = []
    if node_id:
        state_conditions.append(NodeStateLog.node_id == node_id)
    if since:
        state_conditions.append(NodeStateLog.created_at >= since)

    # Build conditions for events
    event_conditions = []
    if node_id:
        event_conditions.append(NodeEvent.node_id == node_id)
    if since:
        event_conditions.append(NodeEvent.created_at >= since)
    if event_type:
        event_conditions.append(NodeEvent.event_type == event_type)

    # Fetch state changes if not filtering to node_event only
    if type != "node_event":
        state_query = (
            select(
                NodeStateLog.id,
                NodeStateLog.created_at,
                NodeStateLog.node_id,
                NodeStateLog.from_state,
                NodeStateLog.to_state,
                NodeStateLog.triggered_by,
                NodeStateLog.comment,
                NodeStateLog.metadata_json,
            )
        )
        if state_conditions:
            state_query = state_query.where(*state_conditions)
        state_query = state_query.order_by(NodeStateLog.created_at.desc())

        state_result = await db.execute(state_query)
        state_logs = state_result.all()

        # Get node names for state logs
        node_ids = list(set(log.node_id for log in state_logs if log.node_id))
        node_names: dict[str, str] = {}
        if node_ids:
            nodes_result = await db.execute(
                select(Node.id, Node.hostname, Node.mac_address).where(Node.id.in_(node_ids))
            )
            for n in nodes_result.all():
                node_names[n.id] = n.hostname or n.mac_address

        for log in state_logs:
            metadata = None
            if log.metadata_json:
                try:
                    metadata = json.loads(log.metadata_json)
                except json.JSONDecodeError:
                    pass

            entries.append(ActivityEntry(
                id=f"state_{log.id}",
                timestamp=log.created_at,
                type="state_change",
                category=f"{log.from_state} → {log.to_state}",
                node_id=log.node_id,
                node_name=node_names.get(log.node_id),
                message=log.comment or f"State changed from {log.from_state} to {log.to_state}",
                details=metadata,
                triggered_by=log.triggered_by,
            ))

    # Fetch node events if not filtering to state_change only
    if type != "state_change":
        event_query = (
            select(
                NodeEvent.id,
                NodeEvent.created_at,
                NodeEvent.node_id,
                NodeEvent.event_type,
                NodeEvent.status,
                NodeEvent.message,
                NodeEvent.progress,
                NodeEvent.metadata_json,
                NodeEvent.ip_address,
            )
        )
        if event_conditions:
            event_query = event_query.where(*event_conditions)
        event_query = event_query.order_by(NodeEvent.created_at.desc())

        event_result = await db.execute(event_query)
        events = event_result.all()

        # Get node names for events
        event_node_ids = list(set(e.node_id for e in events if e.node_id))
        if event_node_ids:
            # Merge with existing node_names if needed
            missing_ids = [nid for nid in event_node_ids if nid not in node_names]
            if missing_ids:
                nodes_result = await db.execute(
                    select(Node.id, Node.hostname, Node.mac_address).where(Node.id.in_(missing_ids))
                )
                for n in nodes_result.all():
                    node_names[n.id] = n.hostname or n.mac_address

        for event in events:
            metadata = None
            if event.metadata_json:
                try:
                    metadata = json.loads(event.metadata_json)
                except json.JSONDecodeError:
                    pass

            # Build message
            msg = event.message
            if not msg:
                msg = f"{event.event_type.replace('_', ' ').title()}"
                if event.progress is not None:
                    msg += f" ({event.progress}%)"

            # Add extra details to metadata
            extra = {}
            if event.ip_address:
                extra["ip_address"] = event.ip_address
            if event.progress is not None:
                extra["progress"] = event.progress
            if event.status:
                extra["status"] = event.status

            if extra:
                metadata = {**(metadata or {}), **extra}

            entries.append(ActivityEntry(
                id=f"event_{event.id}",
                timestamp=event.created_at,
                type="node_event",
                category=event.event_type,
                node_id=event.node_id,
                node_name=node_names.get(event.node_id) if event.node_id else None,
                message=msg,
                details=metadata if metadata else None,
                triggered_by="node_report",
            ))

    # Sort by timestamp descending
    entries.sort(key=lambda x: x.timestamp, reverse=True)

    # Apply pagination
    total = len(entries)
    entries = entries[offset:offset + limit]

    return ActivityListResponse(data=entries, total=total)
