"""Disk and partition API routes."""
import json
from datetime import datetime, timezone
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ApiListResponse, ApiResponse, DiskInfoResponse, PartitionInfo
from src.core.websocket import global_ws_manager
from src.db.database import get_db
from src.db.models import DiskInfo, Node

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
