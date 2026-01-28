"""Site agent management API endpoints.

These endpoints are called by site agents for registration and heartbeat.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ApiResponse,
    AgentRegistration,
    AgentConfig,
    AgentRegistrationResponse,
    AgentHeartbeat,
    HeartbeatResponse,
    HeartbeatCommand,
    AgentStatusResponse,
)
from src.db.database import get_db
from src.db.models import DeviceGroup

router = APIRouter()


def hash_token(token: str) -> str:
    """Hash a token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """Verify a token against its hash."""
    return hash_token(token) == token_hash


@router.post("/agents/register", response_model=AgentRegistrationResponse)
async def register_agent(
    registration: AgentRegistration,
    db: AsyncSession = Depends(get_db),
):
    """Register a site agent with the central controller.

    The agent provides its site_id and registration token. If valid,
    the agent's URL and status are updated, and configuration is returned.
    """
    # Look up the site
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == registration.site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Verify token
    if not site.agent_token_hash:
        raise HTTPException(
            status_code=400,
            detail="No registration token configured for this site. Generate one first.",
        )

    if not verify_token(registration.token, site.agent_token_hash):
        raise HTTPException(status_code=401, detail="Invalid registration token")

    # Update site with agent info
    site.agent_url = registration.agent_url
    site.agent_status = "online"
    site.agent_last_seen = datetime.utcnow()

    await db.flush()

    # Return configuration
    config = AgentConfig(
        site_id=site.id,
        site_name=site.name,
        autonomy_level=site.autonomy_level,
        cache_policy=site.cache_policy,
        cache_max_size_gb=site.cache_max_size_gb,
        cache_retention_days=site.cache_retention_days,
        heartbeat_interval=60,
        sync_enabled=True,
    )

    return AgentRegistrationResponse(
        success=True,
        message="Agent registered successfully",
        config=config,
    )


@router.post("/agents/heartbeat", response_model=HeartbeatResponse)
async def agent_heartbeat(
    heartbeat: AgentHeartbeat,
    db: AsyncSession = Depends(get_db),
):
    """Receive heartbeat from site agent.

    Updates agent status and last_seen timestamp.
    Returns any pending commands for the agent.
    """
    # Look up the site
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == heartbeat.site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Update site status
    site.agent_status = "online"
    site.agent_last_seen = datetime.utcnow()

    await db.flush()

    # Collect any pending commands for this agent
    commands: list[HeartbeatCommand] = []

    # TODO: Check for pending sync requests, config updates, etc.
    # For now, return empty command list

    return HeartbeatResponse(
        acknowledged=True,
        server_time=datetime.utcnow(),
        commands=commands,
    )


@router.get("/agents/{site_id}/status", response_model=ApiResponse[AgentStatusResponse])
async def get_agent_status(
    site_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed status for a site's agent."""
    result = await db.execute(
        select(DeviceGroup).where(
            DeviceGroup.id == site_id,
            DeviceGroup.is_site == True,
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Calculate status based on last_seen
    status = site.agent_status
    if site.agent_last_seen:
        time_since_heartbeat = datetime.utcnow() - site.agent_last_seen
        if time_since_heartbeat > timedelta(minutes=5):
            status = "offline"
        elif time_since_heartbeat > timedelta(minutes=2):
            status = "degraded"

    return ApiResponse(
        data=AgentStatusResponse(
            site_id=site.id,
            site_name=site.name,
            agent_url=site.agent_url,
            agent_status=status,
            agent_last_seen=site.agent_last_seen,
            agent_version=None,  # Would come from heartbeat data
            uptime_seconds=None,
            services=None,
            nodes_count=0,  # Would need to query nodes
            cache_hit_rate=None,
            disk_usage_percent=None,
        )
    )
