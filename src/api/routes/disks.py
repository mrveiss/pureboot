"""Disk and partition API routes."""
import json
from datetime import datetime, timezone
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    DiskInfoResponse,
    PartitionInfo,
    PartitionOperationCreate,
    PartitionOperationResponse,
)
from src.core.websocket import global_ws_manager
from src.db.database import get_db
from src.db.models import DiskInfo, Node, PartitionOperation

router = APIRouter(tags=["Disks"])


class DiskScanReport(BaseModel):
    """Report from node disk scan."""

    disks: list[dict]  # Raw disk info from scan script


@router.get("/nodes/{node_id}/disks", response_model=ApiListResponse[DiskInfoResponse])
async def list_node_disks(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all cached disks for a node."""
    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get all disks for this node
    result = await db.execute(
        select(DiskInfo)
        .where(DiskInfo.node_id == node_id)
        .order_by(DiskInfo.device)
    )
    disks = result.scalars().all()

    return ApiListResponse(
        data=[DiskInfoResponse.from_disk_info(d) for d in disks],
        total=len(disks),
    )


@router.get("/nodes/{node_id}/disks/{device:path}", response_model=ApiResponse[DiskInfoResponse])
async def get_node_disk(
    node_id: str,
    device: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get specific disk information for a node.

    The device path should be URL encoded (e.g., /dev/sda becomes %2Fdev%2Fsda).
    """
    # URL decode the device path
    device = unquote(device)

    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get the specific disk
    result = await db.execute(
        select(DiskInfo).where(
            DiskInfo.node_id == node_id,
            DiskInfo.device == device,
        )
    )
    disk = result.scalar_one_or_none()

    if not disk:
        raise HTTPException(
            status_code=404,
            detail=f"Disk {device} not found for node {node_id}",
        )

    return ApiResponse(data=DiskInfoResponse.from_disk_info(disk))


@router.post("/nodes/{node_id}/disks/scan", response_model=ApiResponse[dict])
async def trigger_disk_scan(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a disk scan on a node.

    This marks the node as needing a disk rescan. The node will pick this up
    on its next poll and report disk information via the /report endpoint.
    """
    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Broadcast scan request event - the node agent will pick this up
    await global_ws_manager.broadcast(
        "partition.scan_requested",
        {
            "node_id": node_id,
            "mac_address": node.mac_address,
        },
    )

    return ApiResponse(
        data={
            "node_id": node_id,
            "status": "scan_requested",
        },
        message="Disk scan requested. Node will report results on next poll.",
    )


@router.post("/nodes/{node_id}/disks/report", response_model=ApiResponse[dict])
async def receive_disk_report(
    node_id: str,
    report: DiskScanReport,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive disk scan results from a node.

    This endpoint is called by nodes to report their disk configuration.
    It upserts DiskInfo records (updates existing or creates new).
    """
    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get existing disk records for this node
    result = await db.execute(
        select(DiskInfo).where(DiskInfo.node_id == node_id)
    )
    existing_disks = {d.device: d for d in result.scalars().all()}

    # Track what devices we've seen in this report
    reported_devices = set()
    created_count = 0
    updated_count = 0

    for disk_data in report.disks:
        device = disk_data.get("device")
        if not device:
            continue

        reported_devices.add(device)

        # Extract partition data if present
        partitions_json = None
        partitions = disk_data.get("partitions", [])
        if partitions:
            # Convert to PartitionInfo format for validation
            validated_partitions = []
            for p in partitions:
                try:
                    # Build human readable size
                    size_bytes = p.get("size_bytes", 0)
                    size_gb = size_bytes / (1024 ** 3)
                    if size_gb >= 1:
                        size_human = f"{size_gb:.1f} GB"
                    else:
                        size_mb = size_bytes / (1024 ** 2)
                        size_human = f"{size_mb:.1f} MB"

                    partition_info = {
                        "number": p.get("number", 0),
                        "start_bytes": p.get("start_bytes", 0),
                        "end_bytes": p.get("end_bytes", 0),
                        "size_bytes": size_bytes,
                        "size_human": size_human,
                        "type": p.get("type", "unknown"),
                        "filesystem": p.get("filesystem"),
                        "label": p.get("label"),
                        "flags": p.get("flags", []),
                        "used_bytes": p.get("used_bytes"),
                        "used_percent": p.get("used_percent"),
                        "can_shrink": p.get("can_shrink", False),
                        "min_size_bytes": p.get("min_size_bytes"),
                    }
                    validated_partitions.append(partition_info)
                except Exception:
                    # Skip invalid partition data
                    continue
            partitions_json = json.dumps(validated_partitions)

        if device in existing_disks:
            # Update existing record
            disk = existing_disks[device]
            disk.size_bytes = disk_data.get("size_bytes", disk.size_bytes)
            disk.model = disk_data.get("model", disk.model)
            disk.serial = disk_data.get("serial", disk.serial)
            disk.partition_table = disk_data.get("partition_table", disk.partition_table)
            disk.partitions_json = partitions_json
            disk.scanned_at = datetime.now(timezone.utc)
            updated_count += 1
        else:
            # Create new record
            disk = DiskInfo(
                node_id=node_id,
                device=device,
                size_bytes=disk_data.get("size_bytes", 0),
                model=disk_data.get("model"),
                serial=disk_data.get("serial"),
                partition_table=disk_data.get("partition_table"),
                partitions_json=partitions_json,
                scanned_at=datetime.now(timezone.utc),
            )
            db.add(disk)
            created_count += 1

    await db.flush()

    # Broadcast scan complete event
    await global_ws_manager.broadcast(
        "partition.scan_complete",
        {
            "node_id": node_id,
            "disk_count": len(reported_devices),
            "created": created_count,
            "updated": updated_count,
        },
    )

    return ApiResponse(
        data={
            "node_id": node_id,
            "disks_reported": len(reported_devices),
            "created": created_count,
            "updated": updated_count,
        },
        message=f"Disk scan report processed: {created_count} created, {updated_count} updated",
    )


# ============== Partition Operation Schemas ==============


class OperationStatusUpdate(BaseModel):
    """Request body for updating operation status from node."""

    status: str  # running, completed, failed
    error_message: str | None = None


# ============== Partition Operation Endpoints ==============


@router.post(
    "/nodes/{node_id}/disks/{device:path}/operations",
    response_model=ApiResponse[PartitionOperationResponse],
)
async def queue_partition_operation(
    node_id: str,
    device: str,
    operation_data: PartitionOperationCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Queue a new partition operation for a device.

    The operation will be added to the queue and executed when apply is called.
    """
    # URL decode the device path
    device = unquote(device)

    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get max sequence number for this node/device
    result = await db.execute(
        select(func.max(PartitionOperation.sequence)).where(
            PartitionOperation.node_id == node_id,
            PartitionOperation.device == device,
            PartitionOperation.status == "pending",
        )
    )
    max_seq = result.scalar() or 0
    new_sequence = max_seq + 1

    # Create the operation record
    operation = PartitionOperation(
        node_id=node_id,
        device=device,
        operation=operation_data.operation,
        params_json=json.dumps(operation_data.params),
        sequence=new_sequence,
        status="pending",
    )
    db.add(operation)
    await db.flush()
    await db.refresh(operation)

    # Broadcast operation queued event
    await global_ws_manager.broadcast(
        "partition.operation_queued",
        {
            "node_id": node_id,
            "device": device,
            "operation_id": operation.id,
            "operation": operation_data.operation,
            "sequence": new_sequence,
        },
    )

    return ApiResponse(
        data=PartitionOperationResponse.from_operation(operation),
        message=f"Operation queued with sequence {new_sequence}",
    )


@router.get(
    "/nodes/{node_id}/disks/{device:path}/operations",
    response_model=ApiListResponse[PartitionOperationResponse],
)
async def list_partition_operations(
    node_id: str,
    device: str,
    status: str | None = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
):
    """
    List queued partition operations for a device.

    Operations are ordered by sequence number.
    """
    # URL decode the device path
    device = unquote(device)

    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Build query
    query = select(PartitionOperation).where(
        PartitionOperation.node_id == node_id,
        PartitionOperation.device == device,
    )

    if status:
        valid_statuses = {"pending", "running", "completed", "failed"}
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}",
            )
        query = query.where(PartitionOperation.status == status)

    query = query.order_by(PartitionOperation.sequence)

    result = await db.execute(query)
    operations = result.scalars().all()

    return ApiListResponse(
        data=[PartitionOperationResponse.from_operation(op) for op in operations],
        total=len(operations),
    )


@router.delete(
    "/nodes/{node_id}/disks/{device:path}/operations/{operation_id}",
    response_model=ApiResponse[dict],
)
async def remove_partition_operation(
    node_id: str,
    device: str,
    operation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a pending partition operation.

    Only operations with status 'pending' can be removed.
    """
    # URL decode the device path
    device = unquote(device)

    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get the operation
    result = await db.execute(
        select(PartitionOperation).where(
            PartitionOperation.id == operation_id,
            PartitionOperation.node_id == node_id,
            PartitionOperation.device == device,
        )
    )
    operation = result.scalar_one_or_none()

    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")

    if operation.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remove operation with status '{operation.status}'. Only pending operations can be removed.",
        )

    await db.delete(operation)
    await db.flush()

    return ApiResponse(
        data={"operation_id": operation_id, "removed": True},
        message="Operation removed successfully",
    )


@router.post(
    "/nodes/{node_id}/disks/{device:path}/apply",
    response_model=ApiResponse[dict],
)
async def apply_partition_operations(
    node_id: str,
    device: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute all pending partition operations on a device.

    This broadcasts an event that the node agent will pick up to execute
    the queued operations.
    """
    # URL decode the device path
    device = unquote(device)

    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get pending operations count
    result = await db.execute(
        select(func.count(PartitionOperation.id)).where(
            PartitionOperation.node_id == node_id,
            PartitionOperation.device == device,
            PartitionOperation.status == "pending",
        )
    )
    pending_count = result.scalar() or 0

    if pending_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No pending operations to apply",
        )

    # Broadcast apply requested event
    await global_ws_manager.broadcast(
        "partition.operations_apply_requested",
        {
            "node_id": node_id,
            "mac_address": node.mac_address,
            "device": device,
            "pending_count": pending_count,
        },
    )

    return ApiResponse(
        data={
            "node_id": node_id,
            "device": device,
            "pending_count": pending_count,
            "status": "apply_requested",
        },
        message=f"Apply requested for {pending_count} pending operations",
    )


@router.post(
    "/nodes/{node_id}/partition-operations/{operation_id}/status",
    response_model=ApiResponse[dict],
)
async def update_operation_status(
    node_id: str,
    operation_id: str,
    status_update: OperationStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive operation status update from a node.

    This endpoint is called by node agents to report the status of
    partition operations as they execute.
    """
    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get the operation
    result = await db.execute(
        select(PartitionOperation).where(
            PartitionOperation.id == operation_id,
            PartitionOperation.node_id == node_id,
        )
    )
    operation = result.scalar_one_or_none()

    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")

    # Validate status
    valid_statuses = {"running", "completed", "failed"}
    if status_update.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}",
        )

    # Update operation
    operation.status = status_update.status
    if status_update.error_message:
        operation.error_message = status_update.error_message
    if status_update.status in ("completed", "failed"):
        operation.executed_at = datetime.now(timezone.utc)

    await db.flush()

    # Broadcast appropriate event based on status
    event_map = {
        "running": "partition.operation_started",
        "completed": "partition.operation_complete",
        "failed": "partition.operation_failed",
    }
    event_type = event_map[status_update.status]

    event_data = {
        "node_id": node_id,
        "operation_id": operation_id,
        "device": operation.device,
        "operation": operation.operation,
        "status": status_update.status,
    }
    if status_update.error_message:
        event_data["error_message"] = status_update.error_message

    await global_ws_manager.broadcast(event_type, event_data)

    return ApiResponse(
        data={
            "operation_id": operation_id,
            "status": status_update.status,
        },
        message=f"Operation status updated to {status_update.status}",
    )
