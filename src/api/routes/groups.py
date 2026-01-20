"""Device group management API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    DeviceGroupCreate,
    DeviceGroupResponse,
    DeviceGroupUpdate,
    NodeResponse,
)
from src.db.database import get_db
from src.db.models import DeviceGroup, Node

router = APIRouter()


@router.get("/groups", response_model=ApiListResponse[DeviceGroupResponse])
async def list_groups(
    db: AsyncSession = Depends(get_db),
):
    """List all device groups."""
    query = select(DeviceGroup)
    result = await db.execute(query)
    groups = result.scalars().all()

    count_query = (
        select(Node.group_id, func.count(Node.id))
        .where(Node.group_id.isnot(None))
        .group_by(Node.group_id)
    )
    count_result = await db.execute(count_query)
    counts = dict(count_result.all())

    return ApiListResponse(
        data=[
            DeviceGroupResponse.from_group(g, node_count=counts.get(g.id, 0))
            for g in groups
        ],
        total=len(groups),
    )


@router.post("/groups", response_model=ApiResponse[DeviceGroupResponse], status_code=201)
async def create_group(
    group_data: DeviceGroupCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new device group."""
    existing = await db.execute(
        select(DeviceGroup).where(DeviceGroup.name == group_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Group '{group_data.name}' already exists",
        )

    group = DeviceGroup(
        name=group_data.name,
        description=group_data.description,
        default_workflow_id=group_data.default_workflow_id,
        auto_provision=group_data.auto_provision,
    )
    db.add(group)
    await db.flush()

    return ApiResponse(
        data=DeviceGroupResponse.from_group(group),
        message="Group created successfully",
    )


@router.get("/groups/{group_id}", response_model=ApiResponse[DeviceGroupResponse])
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get device group details."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    return ApiResponse(data=DeviceGroupResponse.from_group(group, node_count=node_count))


@router.patch("/groups/{group_id}", response_model=ApiResponse[DeviceGroupResponse])
async def update_group(
    group_id: str,
    group_data: DeviceGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update device group."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group_data.name and group_data.name != group.name:
        existing = await db.execute(
            select(DeviceGroup).where(DeviceGroup.name == group_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Group '{group_data.name}' already exists",
            )

    update_data = group_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)

    await db.flush()

    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    return ApiResponse(
        data=DeviceGroupResponse.from_group(group, node_count=node_count),
        message="Group updated successfully",
    )


@router.delete("/groups/{group_id}", response_model=ApiResponse[dict])
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete device group."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    if node_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete group with {node_count} node(s). Remove nodes first.",
        )

    await db.delete(group)
    await db.flush()

    return ApiResponse(
        data={"id": group_id},
        message="Group deleted successfully",
    )


@router.get("/groups/{group_id}/nodes", response_model=ApiListResponse[NodeResponse])
async def list_group_nodes(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List nodes in a device group."""
    group_result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    if not group_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Group not found")

    query = (
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.group_id == group_id)
    )
    result = await db.execute(query)
    nodes = result.scalars().all()

    return ApiListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes),
    )
