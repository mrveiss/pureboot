"""Site management API endpoints.

Sites are special DeviceGroups with is_site=True that represent physical
locations with their own site agents for local caching and offline operation.
"""
import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    NodeResponse,
    SiteCreate,
    SiteUpdate,
    SiteResponse,
    SiteHealthResponse,
    SiteSyncRequest,
    SiteSyncResponse,
)
from src.db.database import get_db
from src.db.models import DeviceGroup, Node, SyncState, SyncConflict

router = APIRouter()


async def compute_effective_site_settings(
    site: DeviceGroup, db: AsyncSession
) -> tuple[str | None, bool]:
    """Compute effective settings by walking up ancestor chain.

    Returns (effective_workflow_id, effective_auto_provision).
    Uses simple override model: child wins if set, else inherit.
    """
    effective_workflow_id = site.default_workflow_id
    effective_auto_provision = site.auto_provision

    # Walk up ancestors if we still need values
    current_id = site.parent_id
    while current_id and (effective_workflow_id is None or effective_auto_provision is None):
        parent_result = await db.execute(
            select(DeviceGroup).where(DeviceGroup.id == current_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            break

        if effective_workflow_id is None and parent.default_workflow_id is not None:
            effective_workflow_id = parent.default_workflow_id

        if effective_auto_provision is None and parent.auto_provision is not None:
            effective_auto_provision = parent.auto_provision

        current_id = parent.parent_id

    # Default auto_provision to False if still None after inheritance
    if effective_auto_provision is None:
        effective_auto_provision = False

    return effective_workflow_id, effective_auto_provision


@router.get("/sites", response_model=ApiListResponse[SiteResponse])
async def list_sites(
    parent_id: str | None = Query(None, description="Filter by parent site ID"),
    db: AsyncSession = Depends(get_db),
):
    """List all sites (DeviceGroups with is_site=True)."""
    query = select(DeviceGroup).where(DeviceGroup.is_site == True)

    if parent_id:
        query = query.where(DeviceGroup.parent_id == parent_id)

    result = await db.execute(query)
    sites = result.scalars().all()

    # Get node counts (nodes with home_site_id pointing to each site)
    count_query = (
        select(Node.home_site_id, func.count(Node.id))
        .where(Node.home_site_id.isnot(None))
        .group_by(Node.home_site_id)
    )
    count_result = await db.execute(count_query)
    node_counts = dict(count_result.all())

    # Get children counts (child sites)
    children_query = (
        select(DeviceGroup.parent_id, func.count(DeviceGroup.id))
        .where(DeviceGroup.parent_id.isnot(None))
        .where(DeviceGroup.is_site == True)
        .group_by(DeviceGroup.parent_id)
    )
    children_result = await db.execute(children_query)
    children_counts = dict(children_result.all())

    return ApiListResponse(
        data=[
            SiteResponse.from_site(
                s,
                node_count=node_counts.get(s.id, 0),
                children_count=children_counts.get(s.id, 0),
            )
            for s in sites
        ],
        total=len(sites),
    )


@router.post("/sites", response_model=ApiResponse[SiteResponse], status_code=201)
async def create_site(
    site_data: SiteCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new site (DeviceGroup with is_site=True)."""
    # Check for duplicate name
    existing = await db.execute(
        select(DeviceGroup).where(DeviceGroup.name == site_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Site or group '{site_data.name}' already exists",
        )

    # Validate parent if provided (must be a site, not a regular group)
    parent = None
    if site_data.parent_id:
        result = await db.execute(
            select(DeviceGroup).where(DeviceGroup.id == site_data.parent_id)
        )
        parent = result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent not found")
        if not parent.is_site:
            raise HTTPException(
                status_code=400,
                detail="Sites can only be nested under other sites, not regular groups",
            )

    # Compute path and depth
    if parent:
        path = f"{parent.path}/{site_data.name}"
        depth = parent.depth + 1
    else:
        path = f"/{site_data.name}"
        depth = 0

    site = DeviceGroup(
        name=site_data.name,
        description=site_data.description,
        parent_id=site_data.parent_id,
        path=path,
        depth=depth,
        # Mark as site
        is_site=True,
        # Site-specific fields
        agent_url=site_data.agent_url,
        autonomy_level=site_data.autonomy_level,
        conflict_resolution=site_data.conflict_resolution,
        cache_policy=site_data.cache_policy,
        cache_patterns_json=site_data.cache_patterns_json,
        cache_max_size_gb=site_data.cache_max_size_gb,
        cache_retention_days=site_data.cache_retention_days,
        discovery_method=site_data.discovery_method,
        discovery_config_json=site_data.discovery_config_json,
        migration_policy=site_data.migration_policy,
    )
    db.add(site)
    await db.flush()

    return ApiResponse(
        data=SiteResponse.from_site(site),
        message="Site created successfully",
    )


@router.get("/sites/{site_id}", response_model=ApiResponse[SiteResponse])
async def get_site(
    site_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get site details including agent status."""
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Node count (nodes with home_site_id = this site)
    count_query = select(func.count(Node.id)).where(Node.home_site_id == site_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    # Children count (child sites)
    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == site_id,
        DeviceGroup.is_site == True,
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    # Compute effective settings
    effective_workflow_id, effective_auto_provision = await compute_effective_site_settings(
        site, db
    )

    return ApiResponse(
        data=SiteResponse.from_site(
            site,
            node_count=node_count,
            children_count=children_count,
            effective_workflow_id=effective_workflow_id,
            effective_auto_provision=effective_auto_provision,
        )
    )


@router.patch("/sites/{site_id}", response_model=ApiResponse[SiteResponse])
async def update_site(
    site_id: str,
    site_data: SiteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update site configuration."""
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Check for name conflict
    if site_data.name and site_data.name != site.name:
        existing = await db.execute(
            select(DeviceGroup).where(DeviceGroup.name == site_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Site or group '{site_data.name}' already exists",
            )

    # Handle parent change (reparent)
    update_data = site_data.model_dump(exclude_unset=True)
    if "parent_id" in update_data:
        new_parent_id = update_data["parent_id"]
        old_path = site.path

        # Cannot be own parent
        if new_parent_id == site_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot set site as its own parent",
            )

        if new_parent_id:
            # Validate new parent exists and is a site
            parent_result = await db.execute(
                select(DeviceGroup).where(DeviceGroup.id == new_parent_id)
            )
            new_parent = parent_result.scalar_one_or_none()
            if not new_parent:
                raise HTTPException(status_code=404, detail="Parent not found")
            if not new_parent.is_site:
                raise HTTPException(
                    status_code=400,
                    detail="Sites can only be nested under other sites",
                )

            # Prevent circular reference
            if new_parent.path.startswith(site.path + "/") or new_parent.id == site_id:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot move site under itself or its descendant",
                )

            # Compute new path
            new_name = update_data.get("name", site.name)
            new_path = f"{new_parent.path}/{new_name}"
            new_depth = new_parent.depth + 1
        else:
            # Moving to root
            new_name = update_data.get("name", site.name)
            new_path = f"/{new_name}"
            new_depth = 0

        # Update descendants' paths
        depth_diff = new_depth - site.depth
        descendants_result = await db.execute(
            select(DeviceGroup).where(
                DeviceGroup.path.startswith(old_path + "/")
            )
        )
        descendants = descendants_result.scalars().all()
        for desc in descendants:
            desc.path = desc.path.replace(old_path, new_path, 1)
            desc.depth = desc.depth + depth_diff

        site.path = new_path
        site.depth = new_depth
        site.parent_id = new_parent_id

        # Remove parent_id from update_data since we handled it
        del update_data["parent_id"]

    # Handle name change (update path if not already handled by reparent)
    if "name" in update_data and "parent_id" not in site_data.model_dump(exclude_unset=True):
        old_path = site.path
        if site.parent_id:
            # Get parent path
            parent_result = await db.execute(
                select(DeviceGroup).where(DeviceGroup.id == site.parent_id)
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

        site.path = new_path

    # Apply remaining updates (site-specific fields)
    for field, value in update_data.items():
        setattr(site, field, value)

    await db.flush()

    # Get counts
    count_query = select(func.count(Node.id)).where(Node.home_site_id == site_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == site_id,
        DeviceGroup.is_site == True,
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    return ApiResponse(
        data=SiteResponse.from_site(
            site, node_count=node_count, children_count=children_count
        ),
        message="Site updated successfully",
    )


@router.delete("/sites/{site_id}", response_model=ApiResponse[dict])
async def delete_site(
    site_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a site.

    Cannot delete if site has child sites or assigned nodes.
    """
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Check for child sites
    children_query = select(func.count(DeviceGroup.id)).where(
        DeviceGroup.parent_id == site_id,
        DeviceGroup.is_site == True,
    )
    children_result = await db.execute(children_query)
    children_count = children_result.scalar() or 0

    if children_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete site with {children_count} child site(s). Remove children first.",
        )

    # Check for nodes with home_site_id pointing to this site
    count_query = select(func.count(Node.id)).where(Node.home_site_id == site_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    if node_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete site with {node_count} assigned node(s). Reassign nodes first.",
        )

    await db.delete(site)
    await db.flush()

    return ApiResponse(
        data={"id": site_id},
        message="Site deleted successfully",
    )


@router.get("/sites/{site_id}/nodes", response_model=ApiListResponse[NodeResponse])
async def list_site_nodes(
    site_id: str,
    include_descendant_sites: bool = Query(
        False, description="Include nodes from descendant sites"
    ),
    db: AsyncSession = Depends(get_db),
):
    """List nodes assigned to this site (by home_site_id)."""
    site_result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if include_descendant_sites:
        # Get all descendant site IDs using materialized path
        descendants_result = await db.execute(
            select(DeviceGroup.id).where(
                DeviceGroup.path.startswith(site.path + "/"),
                DeviceGroup.is_site == True,
            )
        )
        descendant_ids = [g for g in descendants_result.scalars().all()]
        all_site_ids = [site_id] + descendant_ids

        query = (
            select(Node)
            .options(selectinload(Node.tags))
            .where(Node.home_site_id.in_(all_site_ids))
        )
    else:
        query = (
            select(Node)
            .options(selectinload(Node.tags))
            .where(Node.home_site_id == site_id)
        )

    result = await db.execute(query)
    nodes = result.scalars().all()

    return ApiListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes),
    )


@router.get("/sites/{site_id}/health", response_model=ApiResponse[SiteHealthResponse])
async def get_site_health(
    site_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed site health metrics."""
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Count nodes
    nodes_query = select(func.count(Node.id)).where(Node.home_site_id == site_id)
    nodes_result = await db.execute(nodes_query)
    nodes_count = nodes_result.scalar() or 0

    # Count pending sync items
    sync_query = select(func.count(SyncState.id)).where(SyncState.site_id == site_id)
    sync_result = await db.execute(sync_query)
    pending_sync = sync_result.scalar() or 0

    # Count unresolved conflicts
    conflicts_query = select(func.count(SyncConflict.id)).where(
        SyncConflict.site_id == site_id,
        SyncConflict.resolved_at.is_(None),
    )
    conflicts_result = await db.execute(conflicts_query)
    conflicts_pending = conflicts_result.scalar() or 0

    health = SiteHealthResponse(
        site_id=site_id,
        agent_status=site.agent_status,
        agent_last_seen=site.agent_last_seen,
        pending_sync_items=pending_sync,
        conflicts_pending=conflicts_pending,
        nodes_count=nodes_count,
        cache_used_gb=None,  # Would come from agent status report
        cache_max_gb=site.cache_max_size_gb,
    )

    return ApiResponse(data=health)


@router.post("/sites/{site_id}/sync", response_model=ApiResponse[SiteSyncResponse])
async def trigger_site_sync(
    site_id: str,
    sync_request: SiteSyncRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger manual sync for a site.

    This queues a sync request that will be processed when the site agent
    is online. If the site is offline, the request is queued for later.
    """
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Generate a sync request ID
    import uuid
    sync_id = str(uuid.uuid4())

    # In a full implementation, this would create a SyncRequest record
    # and notify the site agent via WebSocket or push notification.
    # For now, we just return a queued status.

    if site.agent_status == "online":
        status = "started"
        message = "Sync started - site agent is online"
    else:
        status = "queued"
        message = f"Sync queued - site agent is {site.agent_status or 'unknown'}"

    return ApiResponse(
        data=SiteSyncResponse(
            sync_id=sync_id,
            status=status,
            message=message,
        ),
        message=message,
    )


class AgentTokenResponse(BaseModel):
    """Response containing agent registration token."""
    token: str
    expires_in_hours: int = 24
    message: str


def hash_token(token: str) -> str:
    """Hash a token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/sites/{site_id}/agent-token", response_model=ApiResponse[AgentTokenResponse])
async def generate_agent_token(
    site_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generate a one-time registration token for the site agent.

    The token is returned once in plain text. It is stored hashed in the database.
    Generating a new token invalidates any previous token.
    """
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Generate secure random token
    token = secrets.token_urlsafe(32)

    # Store hash
    site.agent_token_hash = hash_token(token)

    await db.flush()

    return ApiResponse(
        data=AgentTokenResponse(
            token=token,
            expires_in_hours=24,
            message="Token generated. Save it now - it will not be shown again.",
        ),
        message="Agent registration token generated",
    )
