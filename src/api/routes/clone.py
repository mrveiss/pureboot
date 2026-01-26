"""Clone session API routes."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    CloneAnalysisResponse,
    CloneCertBundle,
    CloneFailedRequest,
    CloneProgressUpdate,
    CloneSessionCreate,
    CloneSessionResponse,
    CloneSessionUpdate,
    CloneSourceReady,
    DiskInfoResponse,
    PartitionPlanItem,
    ResizePlan,
)
from src.core.ca import ca_service
from src.core.websocket import global_ws_manager
from src.db.database import get_db
from src.db.models import CloneSession, DiskInfo, Node, StorageBackend

router = APIRouter(tags=["Clone Sessions"])


@router.post("/clone-sessions", response_model=ApiResponse[CloneSessionResponse])
async def create_clone_session(
    request: CloneSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new clone session."""
    # Verify source node exists
    result = await db.execute(select(Node).where(Node.id == request.source_node_id))
    source_node = result.scalar_one_or_none()
    if not source_node:
        raise HTTPException(status_code=404, detail="Source node not found")

    # Verify target node if provided
    if request.target_node_id:
        result = await db.execute(select(Node).where(Node.id == request.target_node_id))
        target_node = result.scalar_one_or_none()
        if not target_node:
            raise HTTPException(status_code=404, detail="Target node not found")

    # Verify storage backend for staged mode
    if request.clone_mode == "staged" and request.staging_backend_id:
        result = await db.execute(
            select(StorageBackend).where(StorageBackend.id == request.staging_backend_id)
        )
        backend = result.scalar_one_or_none()
        if not backend:
            raise HTTPException(status_code=404, detail="Storage backend not found")

    # Create session
    session = CloneSession(
        name=request.name,
        clone_mode=request.clone_mode,
        source_node_id=request.source_node_id,
        target_node_id=request.target_node_id,
        source_device=request.source_device,
        target_device=request.target_device,
        staging_backend_id=request.staging_backend_id,
        resize_mode=request.resize_mode,
    )

    # Generate certificates for direct mode
    if request.clone_mode == "direct" and ca_service.is_initialized:
        source_cert, source_key = ca_service.issue_session_cert(session.id, "source")
        target_cert, target_key = ca_service.issue_session_cert(session.id, "target")
        session.source_cert_pem = source_cert
        session.source_key_pem = source_key
        session.target_cert_pem = target_cert
        session.target_key_pem = target_key

    db.add(session)
    await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
            selectinload(CloneSession.staging_backend),
        )
        .where(CloneSession.id == session.id)
    )
    session = result.scalar_one()

    return ApiResponse(
        data=CloneSessionResponse.from_session(session),
        message="Clone session created",
    )


@router.get("/clone-sessions", response_model=ApiListResponse[CloneSessionResponse])
async def list_clone_sessions(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List clone sessions."""
    query = select(CloneSession).options(
        selectinload(CloneSession.source_node),
        selectinload(CloneSession.target_node),
        selectinload(CloneSession.staging_backend),
    )

    if status:
        query = query.where(CloneSession.status == status)

    query = query.order_by(CloneSession.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    sessions = result.scalars().all()

    # Get total count
    count_query = select(CloneSession)
    if status:
        count_query = count_query.where(CloneSession.status == status)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return ApiListResponse(
        data=[CloneSessionResponse.from_session(s) for s in sessions],
        total=total,
    )


@router.get("/clone-sessions/{session_id}", response_model=ApiResponse[CloneSessionResponse])
async def get_clone_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a clone session by ID."""
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
            selectinload(CloneSession.staging_backend),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    return ApiResponse(data=CloneSessionResponse.from_session(session))


@router.patch("/clone-sessions/{session_id}", response_model=ApiResponse[CloneSessionResponse])
async def update_clone_session(
    session_id: str,
    request: CloneSessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a clone session."""
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
            selectinload(CloneSession.staging_backend),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.status not in ("pending",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update session in {session.status} status",
        )

    # Update fields
    if request.name is not None:
        session.name = request.name
    if request.target_node_id is not None:
        # Verify target node
        result = await db.execute(select(Node).where(Node.id == request.target_node_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Target node not found")
        session.target_node_id = request.target_node_id
    if request.target_device is not None:
        session.target_device = request.target_device
    if request.resize_mode is not None:
        session.resize_mode = request.resize_mode

    await db.flush()

    # Reload
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
            selectinload(CloneSession.staging_backend),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one()

    return ApiResponse(
        data=CloneSessionResponse.from_session(session),
        message="Clone session updated",
    )


@router.delete("/clone-sessions/{session_id}", response_model=ApiResponse[dict])
async def delete_clone_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete or cancel a clone session."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.status in ("cloning",):
        # Mark as cancelled instead of deleting
        session.status = "cancelled"
        session.completed_at = datetime.now(timezone.utc)
        await db.flush()

        # Broadcast cancellation
        await global_ws_manager.broadcast(
            "clone.cancelled",
            {"session_id": session_id},
        )

        return ApiResponse(data={"id": session_id}, message="Clone session cancelled")

    # Delete if pending or completed
    await db.delete(session)
    await db.flush()

    return ApiResponse(data={"id": session_id}, message="Clone session deleted")


@router.get("/clone-sessions/{session_id}/certs", response_model=ApiResponse[CloneCertBundle])
async def get_clone_certs(
    session_id: str,
    role: str = Query(..., description="Role: source or target"),
    db: AsyncSession = Depends(get_db),
):
    """Get TLS certificates for a clone session participant."""
    if role not in ("source", "target"):
        raise HTTPException(status_code=400, detail="Role must be 'source' or 'target'")

    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.clone_mode != "direct":
        raise HTTPException(
            status_code=400,
            detail="Certificates only available for direct mode sessions",
        )

    if not ca_service.is_initialized:
        raise HTTPException(status_code=503, detail="CA service not initialized")

    if role == "source":
        cert_pem = session.source_cert_pem
        key_pem = session.source_key_pem
    else:
        cert_pem = session.target_cert_pem
        key_pem = session.target_key_pem

    if not cert_pem or not key_pem:
        raise HTTPException(
            status_code=400,
            detail=f"Certificates not yet generated for {role}. Start the session first.",
        )

    return ApiResponse(
        data=CloneCertBundle(
            cert_pem=cert_pem,
            key_pem=key_pem,
            ca_pem=ca_service.get_ca_cert_pem(),
        )
    )


@router.post("/clone-sessions/{session_id}/source-ready", response_model=ApiResponse[dict])
async def clone_source_ready(
    session_id: str,
    request: CloneSourceReady,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by source node when ready to serve disk.

    This endpoint:
    1. Records source IP, port, and disk size from the request
    2. Updates session status to "source_ready"
    3. Broadcasts "clone.source_ready" WebSocket event
    4. For direct mode with target assigned: auto-triggers target node boot
    """
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    # Update session with source info
    session.status = "source_ready"
    session.source_ip = request.ip
    session.source_port = request.port
    session.bytes_total = request.size_bytes
    # Only set started_at if not already set (start endpoint may have set it)
    if not session.started_at:
        session.started_at = datetime.now(timezone.utc)

    # For direct mode: auto-trigger target node boot if target is assigned
    target_boot_triggered = False
    if session.clone_mode == "direct" and session.target_node_id:
        target_node = session.target_node
        if target_node:
            # Set clone workflow for target node
            # Format: clone-target:<session_id>:<device>:<source_ip>:<source_port>
            # This allows the boot endpoint to look up session and connect params
            target_node.workflow_id = (
                f"clone-target:{session.id}:{session.target_device}:"
                f"{request.ip}:{request.port}"
            )

            # Transition to pending state so node will boot into clone mode
            if target_node.state in ("discovered", "active", "installed"):
                target_node.state = "pending"
                target_node.state_changed_at = datetime.now(timezone.utc)

            target_boot_triggered = True

    await db.flush()

    # Broadcast event
    await global_ws_manager.broadcast(
        "clone.source_ready",
        {
            "session_id": session_id,
            "source_ip": request.ip,
            "source_port": request.port,
            "size_bytes": request.size_bytes,
            "target_boot_triggered": target_boot_triggered,
        },
    )

    # Build response message
    if target_boot_triggered:
        message = (
            f"Source ready at {request.ip}:{request.port}. "
            "Target node configured for clone boot - reboot target to begin transfer."
        )
    else:
        message = f"Source ready at {request.ip}:{request.port}"

    return ApiResponse(
        data={
            "status": "source_ready",
            "target_boot_triggered": target_boot_triggered,
        },
        message=message,
    )


@router.post("/clone-sessions/{session_id}/progress", response_model=ApiResponse[dict])
async def clone_progress(
    session_id: str,
    request: CloneProgressUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Progress update from source or target."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    # Update progress
    session.bytes_transferred = request.bytes_transferred
    if request.transfer_rate_bps is not None:
        session.transfer_rate_bps = request.transfer_rate_bps

    if session.status == "source_ready":
        session.status = "cloning"

    await db.flush()

    # Calculate progress
    progress_percent = 0.0
    if session.bytes_total and session.bytes_total > 0:
        progress_percent = (session.bytes_transferred / session.bytes_total) * 100

    # Broadcast progress
    await global_ws_manager.broadcast(
        "clone.progress",
        {
            "session_id": session_id,
            "bytes_transferred": session.bytes_transferred,
            "bytes_total": session.bytes_total,
            "progress_percent": round(progress_percent, 1),
            "transfer_rate_bps": session.transfer_rate_bps,
            "status": request.status,
        },
    )

    return ApiResponse(data={"progress_percent": round(progress_percent, 1)})


@router.post("/clone-sessions/{session_id}/complete", response_model=ApiResponse[dict])
async def clone_complete(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark clone session as complete."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    if session.bytes_total:
        session.bytes_transferred = session.bytes_total

    await db.flush()

    # Calculate duration
    duration_seconds = 0
    if session.started_at:
        duration = session.completed_at - session.started_at
        duration_seconds = int(duration.total_seconds())

    # Broadcast completion
    await global_ws_manager.broadcast(
        "clone.completed",
        {
            "session_id": session_id,
            "duration_seconds": duration_seconds,
        },
    )

    return ApiResponse(
        data={"status": "completed", "duration_seconds": duration_seconds},
        message="Clone completed successfully",
    )


@router.post("/clone-sessions/{session_id}/failed", response_model=ApiResponse[dict])
async def clone_failed(
    session_id: str,
    data: CloneFailedRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mark clone session as failed."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    session.status = "failed"
    session.error_message = data.error_message
    session.completed_at = datetime.now(timezone.utc)

    await db.flush()

    # Broadcast failure
    await global_ws_manager.broadcast(
        "clone.failed",
        {
            "session_id": session_id,
            "error": data.error_message,
            "error_code": data.error_code,
        },
    )

    return ApiResponse(
        data={"status": "failed", "error_code": data.error_code},
        message=f"Clone failed: {data.error_message}",
    )


@router.post("/clone-sessions/{session_id}/start", response_model=ApiResponse[dict])
async def start_clone_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a clone session by triggering the source node to boot into clone mode.

    This endpoint:
    1. Validates the session exists and is in "pending" status
    2. Generates TLS certificates for source (and target if assigned)
    3. Sets the source node's workflow to boot into clone source mode
    4. Broadcasts clone.started WebSocket event

    The source node will boot into a special clone environment that:
    - Serves the source disk over the network
    - Reports readiness via the /source-ready endpoint
    """
    # Load session with relationships
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start session in '{session.status}' status. Must be 'pending'.",
        )

    # Generate TLS certificates if CA is initialized
    if ca_service.is_initialized:
        # Generate source certificate
        source_cert, source_key = ca_service.issue_session_cert(
            session.id, "source"
        )
        session.source_cert_pem = source_cert
        session.source_key_pem = source_key

        # Generate target certificate if target node is assigned
        if session.target_node_id:
            target_cert, target_key = ca_service.issue_session_cert(
                session.id, "target"
            )
            session.target_cert_pem = target_cert
            session.target_key_pem = target_key

    # Set session start time
    session.started_at = datetime.now(timezone.utc)

    # Configure source node for clone boot
    # We use a special workflow ID format: clone-source:<session_id>
    # The boot endpoint will detect this and generate appropriate boot config
    source_node = session.source_node
    if source_node:
        # Set clone workflow - format: clone-source:<session_id>:<device>
        # This allows the boot endpoint to look up the session and device
        source_node.workflow_id = f"clone-source:{session.id}:{session.source_device}"

        # Transition to pending state so node will boot into clone mode on next boot
        # The boot endpoint checks for 'pending' state to serve install/clone scripts
        if source_node.state in ("discovered", "active", "installed"):
            source_node.state = "pending"
            source_node.state_changed_at = datetime.now(timezone.utc)

    await db.flush()

    # Broadcast clone started event
    await global_ws_manager.broadcast(
        "clone.started",
        {
            "session_id": session_id,
            "source_node_id": session.source_node_id,
            "target_node_id": session.target_node_id,
            "clone_mode": session.clone_mode,
            "source_device": session.source_device,
        },
    )

    # Determine source boot mode based on node's boot_mode setting
    source_boot_mode = "bios"
    if source_node:
        source_boot_mode = source_node.boot_mode or "bios"

    return ApiResponse(
        data={
            "session_id": session_id,
            "source_boot_mode": source_boot_mode,
            "status": "starting",
            "message": "Source node configured for clone boot. Reboot source node to begin.",
        },
        message="Clone session started. Reboot source node to begin cloning.",
    )


def _generate_resize_plan(
    source_disk: DiskInfo,
    target_disk: DiskInfo | None,
    resize_mode: str,
) -> ResizePlan:
    """
    Generate a resize plan based on source/target disk sizes.

    Args:
        source_disk: Source disk info with partition data
        target_disk: Target disk info (may be None if not yet assigned)
        resize_mode: Current resize mode setting

    Returns:
        ResizePlan with partition adjustments
    """
    source_size = source_disk.size_bytes
    target_size = target_disk.size_bytes if target_disk else source_size

    # Parse source partitions
    partitions = []
    if source_disk.partitions_json:
        try:
            partition_data = json.loads(source_disk.partitions_json)
            for p in partition_data:
                partitions.append(
                    PartitionPlanItem(
                        partition=p.get("number", 0),
                        current_size_bytes=p.get("size_bytes", 0),
                        new_size_bytes=p.get("size_bytes", 0),  # Default: keep same
                        filesystem=p.get("filesystem"),
                        action="keep",
                        min_size_bytes=p.get("min_size_bytes"),
                        can_resize=p.get("can_shrink", False),
                    )
                )
        except (json.JSONDecodeError, TypeError):
            pass

    # Determine if resize is needed
    if target_size >= source_size:
        # Target is same or larger - no shrinking needed
        # Could grow partitions if resize_mode is grow_target
        if resize_mode == "grow_target" and target_size > source_size:
            # Find the last resizable partition and grow it
            extra_space = target_size - source_size
            for p in reversed(partitions):
                if p.can_resize and p.filesystem in ("ext4", "xfs", "btrfs", "ntfs"):
                    p.new_size_bytes = p.current_size_bytes + extra_space
                    p.action = "grow"
                    break

        return ResizePlan(
            source_disk_bytes=source_size,
            target_disk_bytes=target_size,
            resize_mode=resize_mode,
            partitions=partitions,
            feasible=True,
        )

    # Target is smaller - need to shrink
    size_to_reduce = source_size - target_size

    # Check if shrinking is feasible
    total_shrinkable = 0
    for p in partitions:
        if p.can_resize and p.min_size_bytes is not None:
            shrink_potential = p.current_size_bytes - p.min_size_bytes
            if shrink_potential > 0:
                total_shrinkable += shrink_potential

    if total_shrinkable < size_to_reduce:
        return ResizePlan(
            source_disk_bytes=source_size,
            target_disk_bytes=target_size,
            resize_mode="shrink_source",
            partitions=partitions,
            feasible=False,
            error_message=(
                f"Cannot shrink partitions enough. Need to reduce {size_to_reduce} bytes "
                f"but only {total_shrinkable} bytes available for shrinking."
            ),
        )

    # Distribute shrinkage across partitions (proportionally)
    remaining_to_shrink = size_to_reduce
    for p in reversed(partitions):  # Start from last partition
        if remaining_to_shrink <= 0:
            break
        if p.can_resize and p.min_size_bytes is not None:
            shrink_potential = p.current_size_bytes - p.min_size_bytes
            if shrink_potential > 0:
                shrink_amount = min(shrink_potential, remaining_to_shrink)
                p.new_size_bytes = p.current_size_bytes - shrink_amount
                p.action = "shrink"
                remaining_to_shrink -= shrink_amount

    return ResizePlan(
        source_disk_bytes=source_size,
        target_disk_bytes=target_size,
        resize_mode="shrink_source",
        partitions=partitions,
        feasible=True,
    )


@router.post(
    "/clone-sessions/{session_id}/analyze",
    response_model=ApiResponse[CloneAnalysisResponse],
)
async def analyze_clone_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze source and target disks to determine if resize is needed.

    Compares disk sizes and generates a suggested resize plan if
    source disk is larger than target.
    """
    # Load session with relationships
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    # Get source disk info
    result = await db.execute(
        select(DiskInfo).where(
            DiskInfo.node_id == session.source_node_id,
            DiskInfo.device == session.source_device,
        )
    )
    source_disk = result.scalar_one_or_none()

    if not source_disk:
        raise HTTPException(
            status_code=404,
            detail=f"No disk info found for source node device {session.source_device}. "
            "Run disk scan on source node first.",
        )

    # Get target disk info if target is assigned
    target_disk = None
    if session.target_node_id:
        result = await db.execute(
            select(DiskInfo).where(
                DiskInfo.node_id == session.target_node_id,
                DiskInfo.device == session.target_device,
            )
        )
        target_disk = result.scalar_one_or_none()

    # Calculate size difference
    source_size = source_disk.size_bytes
    target_size = target_disk.size_bytes if target_disk else source_size
    size_difference = source_size - target_size
    resize_needed = size_difference > 0

    # Generate suggested plan
    suggested_plan = _generate_resize_plan(
        source_disk, target_disk, session.resize_mode
    )

    # Build disk info dicts for response
    source_disk_dict = DiskInfoResponse.from_disk_info(source_disk).model_dump()
    target_disk_dict = (
        DiskInfoResponse.from_disk_info(target_disk).model_dump()
        if target_disk
        else None
    )

    return ApiResponse(
        data=CloneAnalysisResponse(
            source_disk=source_disk_dict,
            target_disk=target_disk_dict,
            size_difference_bytes=size_difference,
            resize_needed=resize_needed,
            suggested_plan=suggested_plan,
        ),
        message="Clone analysis complete",
    )


@router.get(
    "/clone-sessions/{session_id}/plan",
    response_model=ApiResponse[ResizePlan | None],
)
async def get_resize_plan(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the current resize plan for a clone session."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    # Parse stored plan if exists
    if session.partition_plan_json:
        try:
            plan_data = json.loads(session.partition_plan_json)
            plan = ResizePlan(**plan_data)
            return ApiResponse(data=plan)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error parsing stored resize plan: {e}",
            )

    return ApiResponse(data=None, message="No resize plan configured")


@router.put(
    "/clone-sessions/{session_id}/plan",
    response_model=ApiResponse[ResizePlan],
)
async def update_resize_plan(
    session_id: str,
    plan: ResizePlan,
    db: AsyncSession = Depends(get_db),
):
    """Update the resize plan for a clone session."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.status not in ("pending", "source_ready"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update plan for session in '{session.status}' status",
        )

    # Validate plan feasibility
    if not plan.feasible:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot save infeasible plan: {plan.error_message}",
        )

    # Store plan as JSON
    session.partition_plan_json = plan.model_dump_json()
    session.resize_mode = plan.resize_mode

    await db.flush()

    return ApiResponse(
        data=plan,
        message="Resize plan updated successfully",
    )
