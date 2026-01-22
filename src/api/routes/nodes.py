"""Node management API endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    NodeCreate,
    NodeEventListResponse,
    NodeEventResponse,
    NodeHistoryResponse,
    NodeReport,
    NodeResponse,
    NodeStateLogResponse,
    NodeUpdate,
    StateTransition,
    TagCreate,
)
from src.core.event_service import EventService
from src.core.state_machine import InvalidStateTransition, NodeStateMachine
from src.core.state_service import StateTransitionService
from src.db.database import get_db
from src.db.models import Node, NodeEvent, NodeStateLog, NodeTag

router = APIRouter()


@router.get("/nodes", response_model=ApiListResponse[NodeResponse])
async def list_nodes(
    state: str | None = Query(None, description="Filter by state"),
    group_id: str | None = Query(None, description="Filter by group ID"),
    tag: str | None = Query(None, description="Filter by tag"),
    db: AsyncSession = Depends(get_db),
):
    """List all nodes with optional filtering."""
    query = select(Node).options(selectinload(Node.tags))

    if state:
        query = query.where(Node.state == state)
    if group_id:
        query = query.where(Node.group_id == group_id)
    if tag:
        query = query.join(Node.tags).where(NodeTag.tag == tag.lower())

    result = await db.execute(query)
    nodes = result.scalars().unique().all()

    return ApiListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes),
    )


@router.post("/nodes", response_model=ApiResponse[NodeResponse], status_code=201)
async def create_node(
    node_data: NodeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new node."""
    existing = await db.execute(
        select(Node).where(Node.mac_address == node_data.mac_address)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Node with MAC {node_data.mac_address} already exists",
        )

    node = Node(
        mac_address=node_data.mac_address,
        hostname=node_data.hostname,
        arch=node_data.arch,
        boot_mode=node_data.boot_mode,
        group_id=node_data.group_id,
        vendor=node_data.vendor,
        model=node_data.model,
        serial_number=node_data.serial_number,
        system_uuid=node_data.system_uuid,
    )
    db.add(node)
    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message="Node registered successfully",
    )


@router.get("/nodes/stalled", response_model=ApiListResponse[NodeResponse])
async def get_stalled_nodes(
    db: AsyncSession = Depends(get_db),
):
    """Get nodes with timed-out installations.

    Returns nodes in 'installing' state that have exceeded
    the install_timeout_minutes threshold.
    """
    if settings.install_timeout_minutes <= 0:
        return ApiListResponse(data=[], total=0)

    timeout_threshold = datetime.now(timezone.utc) - timedelta(
        minutes=settings.install_timeout_minutes
    )

    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.state == "installing")
        .where(Node.state_changed_at < timeout_threshold)
        .order_by(Node.state_changed_at.asc())
    )
    nodes = result.scalars().all()

    return ApiListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes),
    )


@router.get("/nodes/{node_id}", response_model=ApiResponse[NodeResponse])
async def get_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get node details by ID."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return ApiResponse(data=NodeResponse.from_node(node))


@router.patch("/nodes/{node_id}", response_model=ApiResponse[NodeResponse])
async def update_node(
    node_id: str,
    node_data: NodeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update node metadata."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    update_data = node_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(node, field, value)

    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message="Node updated successfully",
    )


@router.patch("/nodes/{node_id}/state", response_model=ApiResponse[NodeResponse])
async def transition_node_state(
    node_id: str,
    transition: StateTransition,
    db: AsyncSession = Depends(get_db),
):
    """Transition node to a new state."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    try:
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state=transition.state,
            triggered_by="admin",
            comment=transition.comment,
            force=transition.force,
        )
        await db.flush()
        await db.refresh(node, ["tags"])

        return ApiResponse(
            data=NodeResponse.from_node(node),
            message=f"Node transitioned to {transition.state}",
        )
    except InvalidStateTransition as e:
        valid = NodeStateMachine.get_valid_transitions(node.state)
        raise HTTPException(
            status_code=400,
            detail=f"{str(e)}. Valid transitions: {valid}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/nodes/{node_id}/history", response_model=NodeHistoryResponse)
async def get_node_history(
    node_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get node state transition history."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Node not found")

    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(NodeStateLog).where(NodeStateLog.node_id == node_id)
    )
    total = count_result.scalar() or 0

    # Get logs with pagination
    logs_result = await db.execute(
        select(NodeStateLog)
        .where(NodeStateLog.node_id == node_id)
        .order_by(NodeStateLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = logs_result.scalars().all()

    return NodeHistoryResponse(
        data=[NodeStateLogResponse.from_log(log) for log in logs],
        total=total,
    )


@router.delete("/nodes/{node_id}", response_model=ApiResponse[NodeResponse])
async def retire_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retire a node (sets state to retired)."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    try:
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state="retired",
            triggered_by="admin",
        )
        await db.flush()
        await db.refresh(node, ["tags"])

        return ApiResponse(
            data=NodeResponse.from_node(node),
            message="Node retired",
        )
    except InvalidStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/{node_id}/tags", response_model=ApiResponse[NodeResponse])
async def add_node_tag(
    node_id: str,
    tag_data: TagCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a tag to a node."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    existing_tags = [t.tag for t in node.tags]
    if tag_data.tag in existing_tags:
        raise HTTPException(
            status_code=409,
            detail=f"Tag '{tag_data.tag}' already exists on node",
        )

    tag = NodeTag(node_id=node_id, tag=tag_data.tag)
    db.add(tag)
    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message=f"Tag '{tag_data.tag}' added",
    )


@router.delete("/nodes/{node_id}/tags/{tag}", response_model=ApiResponse[NodeResponse])
async def remove_node_tag(
    node_id: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a tag from a node."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    tag_lower = tag.lower()
    tag_to_delete = None
    for t in node.tags:
        if t.tag == tag_lower:
            tag_to_delete = t
            break

    if not tag_to_delete:
        raise HTTPException(
            status_code=404,
            detail=f"Tag '{tag}' not found on node",
        )

    await db.delete(tag_to_delete)
    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message=f"Tag '{tag}' removed",
    )


@router.post("/report", response_model=ApiResponse[NodeResponse])
async def report_node_status(
    report: NodeReport,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Report node status and update information.

    Called by nodes to report their current status, update
    hardware information, and report installation progress.

    Supports both:
    - New event-based reporting (event field)
    - Legacy installation_status reporting (backwards compatible)
    """
    # Look up node by MAC
    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.mac_address == report.mac_address)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node with MAC {report.mac_address} not found",
        )

    # Get client IP
    client_ip = request.client.host if request.client else report.ip_address

    # Update node information
    node.last_seen_at = datetime.now(timezone.utc)

    if report.ip_address:
        node.ip_address = report.ip_address
    if report.hostname:
        node.hostname = report.hostname
    if report.vendor:
        node.vendor = report.vendor
    if report.model:
        node.model = report.model
    if report.serial_number:
        node.serial_number = report.serial_number
    if report.system_uuid:
        node.system_uuid = report.system_uuid

    message = "Status reported successfully"

    # Handle new event-based reporting
    if report.event:
        message = await _handle_event(db, node, report, client_ip)

    # Handle legacy installation_status (backwards compatibility)
    elif report.installation_status:
        message = await _handle_legacy_installation_status(db, node, report, client_ip)

    await db.flush()
    await db.refresh(node)

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message=message,
    )


@router.get("/nodes/{node_id}/events", response_model=NodeEventListResponse)
async def get_node_events(
    node_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: str | None = Query(None, description="Filter by event type"),
    db: AsyncSession = Depends(get_db),
):
    """Get events for a specific node."""
    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    # Build query
    query = select(NodeEvent).where(NodeEvent.node_id == node_id)
    if event_type:
        query = query.where(NodeEvent.event_type == event_type)
    query = query.order_by(NodeEvent.created_at.desc())

    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    # Get paginated results
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()

    return NodeEventListResponse(
        data=[NodeEventResponse.from_event(e) for e in events],
        total=total,
    )


async def _handle_event(
    db: AsyncSession,
    node: Node,
    report: NodeReport,
    client_ip: str | None,
) -> str:
    """Handle event-based reporting."""
    event_type = report.event
    message = "Event logged"

    # Log the event
    await EventService.log_event(
        db=db,
        node=node,
        event_type=event_type,
        status=report.status,
        message=report.message,
        progress=report.installation_progress,
        metadata=report.event_metadata,
        ip_address=client_ip,
    )

    # Handle state transitions based on event
    match event_type:
        case "boot_started":
            message = "Boot started event logged"

        case "install_started":
            if node.state == "pending":
                await StateTransitionService.transition(
                    db=db,
                    node=node,
                    to_state="installing",
                    triggered_by="node_report",
                )
                node.install_attempts = 0
                message = "Installation started"

        case "install_progress":
            message = f"Installation progress: {report.installation_progress or 0}%"

        case "install_complete":
            if node.state == "installing":
                await StateTransitionService.transition(
                    db=db,
                    node=node,
                    to_state="installed",
                    triggered_by="node_report",
                )
                message = "Installation completed"

        case "install_failed":
            if node.state == "installing":
                await StateTransitionService.handle_install_failure(
                    db=db,
                    node=node,
                    error=report.message or report.installation_error,
                )
                if node.state == "install_failed":
                    message = f"Installation failed after {node.install_attempts} attempts"
                else:
                    message = f"Installation failed (attempt {node.install_attempts}), will retry"

        case "first_boot":
            if node.state == "installed":
                await StateTransitionService.transition(
                    db=db,
                    node=node,
                    to_state="active",
                    triggered_by="node_report",
                    metadata=report.event_metadata,
                )
                message = "First boot - node now active"

        case "heartbeat":
            message = "Heartbeat received"

    return message


async def _handle_legacy_installation_status(
    db: AsyncSession,
    node: Node,
    report: NodeReport,
    client_ip: str | None,
) -> str:
    """Handle legacy installation_status field for backwards compatibility."""
    message = "Status reported successfully"

    # Map legacy status to event type for logging
    event_type_map = {
        "started": "install_started",
        "progress": "install_progress",
        "complete": "install_complete",
        "failed": "install_failed",
    }
    event_type = event_type_map.get(report.installation_status, "unknown")

    # Log as event
    await EventService.log_event(
        db=db,
        node=node,
        event_type=event_type,
        status="success" if report.installation_status != "failed" else "failed",
        message=report.installation_error,
        progress=report.installation_progress,
        ip_address=client_ip,
    )

    # Handle state transitions (existing logic)
    if report.installation_status == "started" and node.state == "pending":
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state="installing",
            triggered_by="node_report",
        )
        node.install_attempts = 0
        message = "Installation started"

    elif report.installation_status == "complete" and node.state == "installing":
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state="installed",
            triggered_by="node_report",
        )
        message = "Installation completed"

    elif report.installation_status == "failed" and node.state == "installing":
        await StateTransitionService.handle_install_failure(
            db=db,
            node=node,
            error=report.installation_error,
        )
        if node.state == "install_failed":
            message = f"Installation failed after {node.install_attempts} attempts"
        else:
            message = f"Installation failed (attempt {node.install_attempts}), will retry"

    return message
