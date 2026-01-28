"""Node-facing API endpoints for site agent.

These endpoints proxy node requests to the central controller
while providing local caching for improved resilience.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["nodes"])


# Request/Response models
class NodeRegistration(BaseModel):
    """Node self-registration request."""
    mac_address: str
    ip_address: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    system_uuid: str | None = None


class StateUpdate(BaseModel):
    """Node state update request."""
    state: str


class NodeEvent(BaseModel):
    """Node event report."""
    event_type: str
    event_data: dict[str, Any] = {}
    timestamp: datetime | None = None


class NodeResponse(BaseModel):
    """Node information response."""
    id: str | None = None
    mac_address: str
    state: str
    workflow_id: str | None = None
    group_id: str | None = None
    ip_address: str | None = None
    vendor: str | None = None
    model: str | None = None
    from_cache: bool = False
    cached_at: datetime | None = None


# Note: The actual proxy instance will be set by the agent main module
# when creating the FastAPI app. This is a placeholder that will be
# replaced with dependency injection.
_proxy = None


def set_proxy(proxy):
    """Set the proxy instance for this router."""
    global _proxy
    _proxy = proxy


def get_proxy():
    """Get the proxy instance."""
    if _proxy is None:
        raise HTTPException(
            status_code=503,
            detail="Proxy not initialized",
        )
    return _proxy


@router.post("/nodes/register", response_model=NodeResponse)
async def register_node(registration: NodeRegistration, request: Request):
    """Register a new node with the system.

    Proxies registration to central controller and caches result.
    """
    proxy = get_proxy()

    response = await proxy.register_node(
        mac_address=registration.mac_address,
        ip_address=registration.ip_address or (
            request.client.host if request.client else None
        ),
        vendor=registration.vendor,
        model=registration.model,
        serial_number=registration.serial_number,
        system_uuid=registration.system_uuid,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.error or "Registration failed",
        )

    data = response.data or {}
    return NodeResponse(
        id=data.get("id"),
        mac_address=registration.mac_address,
        state=data.get("state", "discovered"),
        workflow_id=data.get("workflow_id"),
        group_id=data.get("group_id"),
        ip_address=registration.ip_address,
        vendor=registration.vendor,
        model=registration.model,
        from_cache=response.from_cache,
        cached_at=response.cached_at,
    )


@router.get("/nodes", response_model=list[NodeResponse])
async def get_nodes(
    mac: str | None = Query(None, description="Filter by MAC address"),
    group_id: str | None = Query(None, description="Filter by group ID"),
):
    """Get nodes, optionally filtered by MAC or group.

    Returns cached data when available, proxies to central otherwise.
    """
    proxy = get_proxy()

    if mac:
        # Get single node by MAC
        node = await proxy.get_node_by_mac(mac)
        if not node:
            return []

        return [
            NodeResponse(
                id=node.node_id,
                mac_address=node.mac_address,
                state=node.state,
                workflow_id=node.workflow_id,
                group_id=node.group_id,
                ip_address=node.ip_address,
                vendor=node.vendor,
                model=node.model,
                from_cache=True,
                cached_at=node.cached_at,
            )
        ]

    if group_id:
        # Get nodes by group from cache
        nodes = await proxy.state_cache.get_nodes_by_group(group_id)
        return [
            NodeResponse(
                id=n.node_id,
                mac_address=n.mac_address,
                state=n.state,
                workflow_id=n.workflow_id,
                group_id=n.group_id,
                ip_address=n.ip_address,
                vendor=n.vendor,
                model=n.model,
                from_cache=True,
                cached_at=n.cached_at,
            )
            for n in nodes
        ]

    # Return all cached nodes (don't proxy full list to central)
    nodes = await proxy.state_cache.get_all_nodes()
    return [
        NodeResponse(
            id=n.node_id,
            mac_address=n.mac_address,
            state=n.state,
            workflow_id=n.workflow_id,
            group_id=n.group_id,
            ip_address=n.ip_address,
            vendor=n.vendor,
            model=n.model,
            from_cache=True,
            cached_at=n.cached_at,
        )
        for n in nodes
    ]


@router.get("/nodes/{node_id}", response_model=NodeResponse)
async def get_node(node_id: str):
    """Get a specific node by ID.

    Proxies to central if not in cache.
    """
    proxy = get_proxy()

    # First check if we have it cached (by searching all nodes)
    nodes = await proxy.state_cache.get_all_nodes()
    for node in nodes:
        if node.node_id == node_id:
            return NodeResponse(
                id=node.node_id,
                mac_address=node.mac_address,
                state=node.state,
                workflow_id=node.workflow_id,
                group_id=node.group_id,
                ip_address=node.ip_address,
                vendor=node.vendor,
                model=node.model,
                from_cache=True,
                cached_at=node.cached_at,
            )

    # Proxy to central
    response = await proxy.proxy_request("GET", f"/api/v1/nodes/{node_id}")

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Node not found")

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.error or "Failed to get node",
        )

    data = response.data or {}
    return NodeResponse(
        id=data.get("id"),
        mac_address=data.get("mac_address", ""),
        state=data.get("state", "unknown"),
        workflow_id=data.get("workflow_id"),
        group_id=data.get("group_id"),
        ip_address=data.get("ip_address"),
        vendor=data.get("vendor"),
        model=data.get("model"),
        from_cache=False,
    )


@router.patch("/nodes/{node_id}/state", response_model=NodeResponse)
async def update_node_state(node_id: str, update: StateUpdate):
    """Update node state.

    Proxies to central and updates cache on success.
    """
    proxy = get_proxy()

    # Find MAC address for cache update
    mac_address = None
    nodes = await proxy.state_cache.get_all_nodes()
    for node in nodes:
        if node.node_id == node_id:
            mac_address = node.mac_address
            break

    response = await proxy.update_node_state(
        node_id=node_id,
        new_state=update.state,
        mac_address=mac_address,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.error or "State update failed",
        )

    data = response.data or {}
    return NodeResponse(
        id=data.get("id", node_id),
        mac_address=data.get("mac_address", mac_address or ""),
        state=data.get("state", update.state),
        workflow_id=data.get("workflow_id"),
        group_id=data.get("group_id"),
        from_cache=False,
    )


@router.post("/nodes/{node_id}/event")
async def report_node_event(node_id: str, event: NodeEvent):
    """Report an event from a node.

    Proxies to central for processing.
    """
    proxy = get_proxy()

    response = await proxy.report_node_event(
        node_id=node_id,
        event_type=event.event_type,
        event_data=event.event_data,
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.error or "Event report failed",
        )

    return {"status": "accepted", "event_type": event.event_type}
