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
    root_only: bool = Query(False, description="Only return root groups"),
    parent_id: str | None = Query(None, description="Filter by parent ID"),
    db: AsyncSession = Depends(get_db),
):
    """List all device groups."""
    query = select(DeviceGroup)

    if root_only:
        query = query.where(DeviceGroup.parent_id.is_(None))
    elif parent_id:
        query = query.where(DeviceGroup.parent_id == parent_id)

    result = await db.execute(query)
    groups = result.scalars().all()

    # Get node counts
    count_query = (
        select(Node.group_id, func.count(Node.id))
        .where(Node.group_id.isnot(None))
        .group_by(Node.group_id)
    )
    count_result = await db.execute(count_query)
    node_counts = dict(count_result.all())

    # Get children counts
    children_query = (
        select(DeviceGroup.parent_id, func.count(DeviceGroup.id))
        .where(DeviceGroup.parent_id.isnot(None))
        .group_by(DeviceGroup.parent_id)
    )
    children_result = await db.execute(children_query)
    children_counts = dict(children_result.all())

    return ApiListResponse(
        data=[
            DeviceGroupResponse.from_group(
                g,
                node_count=node_counts.get(g.id, 0),
                children_count=children_counts.get(g.id, 0),
            )
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
    # Check for duplicate name
    existing = await db.execute(
        select(DeviceGroup).where(DeviceGroup.name == group_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Group '{group_data.name}' already exists",
        )

    # Validate parent if provided
    parent = None
    if group_data.parent_id:
        result = await db.execute(
            select(DeviceGroup).where(DeviceGroup.id == group_data.parent_id)
        )
        parent = result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent group not found")

    # Compute path and depth
    if parent:
        path = f"{parent.path}/{group_data.name}"
        depth = parent.depth + 1
    else:
        path = f"/{group_data.name}"
        depth = 0

    group = DeviceGroup(
        name=group_data.name,
        description=group_data.description,
        parent_id=group_data.parent_id,
        path=path,
        depth=depth,
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

    # Node count
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    # Children count
    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == group_id
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    return ApiResponse(
        data=DeviceGroupResponse.from_group(
            group, node_count=node_count, children_count=children_count
        )
    )


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

    # Check for name conflict
    if group_data.name and group_data.name != group.name:
        existing = await db.execute(
            select(DeviceGroup).where(DeviceGroup.name == group_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Group '{group_data.name}' already exists",
            )

    # Handle parent change (reparent)
    update_data = group_data.model_dump(exclude_unset=True)
    if "parent_id" in update_data:
        new_parent_id = update_data["parent_id"]
        old_path = group.path

        # Cannot be own parent
        if new_parent_id == group_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot set group as its own parent",
            )

        if new_parent_id:
            # Validate new parent exists
            parent_result = await db.execute(
                select(DeviceGroup).where(DeviceGroup.id == new_parent_id)
            )
            new_parent = parent_result.scalar_one_or_none()
            if not new_parent:
                raise HTTPException(status_code=404, detail="Parent group not found")

            # Prevent circular reference
            if new_parent.path.startswith(group.path + "/") or new_parent.id == group_id:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot move group under itself or its descendant",
                )

            # Compute new path
            new_name = update_data.get("name", group.name)
            new_path = f"{new_parent.path}/{new_name}"
            new_depth = new_parent.depth + 1
        else:
            # Moving to root
            new_name = update_data.get("name", group.name)
            new_path = f"/{new_name}"
            new_depth = 0

        # Update descendants' paths
        depth_diff = new_depth - group.depth
        descendants_result = await db.execute(
            select(DeviceGroup).where(
                DeviceGroup.path.startswith(old_path + "/")
            )
        )
        descendants = descendants_result.scalars().all()
        for desc in descendants:
            desc.path = desc.path.replace(old_path, new_path, 1)
            desc.depth = desc.depth + depth_diff

        group.path = new_path
        group.depth = new_depth
        group.parent_id = new_parent_id

        # Remove parent_id from update_data since we handled it
        del update_data["parent_id"]

    # Handle name change (update path if not already handled by reparent)
    if "name" in update_data and "parent_id" not in group_data.model_dump(exclude_unset=True):
        old_path = group.path
        if group.parent_id:
            # Get parent path
            parent_result = await db.execute(
                select(DeviceGroup).where(DeviceGroup.id == group.parent_id)
            )
            parent = parent_result.scalar_one()
            new_path = f"{parent.path}/{update_data['name']}"
        else:
            new_path = f"/{update_data['name']}"

        # Update descendants' paths
        descendants_result = await db.execute(
            select(DeviceGroup).where(
                DeviceGroup.path.startswith(old_path + "/")
            )
        )
        descendants = descendants_result.scalars().all()
        for desc in descendants:
            desc.path = desc.path.replace(old_path, new_path, 1)

        group.path = new_path

    # Apply remaining updates
    for field, value in update_data.items():
        setattr(group, field, value)

    await db.flush()

    # Get counts
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == group_id
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    return ApiResponse(
        data=DeviceGroupResponse.from_group(
            group, node_count=node_count, children_count=children_count
        ),
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
