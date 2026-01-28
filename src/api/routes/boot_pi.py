"""Raspberry Pi boot API endpoints.

This module provides boot endpoints specifically for Raspberry Pi devices
that use TFTP-based network boot rather than iPXE.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    MAC_PATTERN,
    ApiResponse,
    NodeResponse,
    PiBootResponse,
    PiRegisterRequest,
    normalize_mac,
)
from src.config import settings
from src.core.workflow_service import Workflow, WorkflowNotFoundError, WorkflowService
from src.db.database import get_db
from src.db.models import Node
from src.pxe import PiManager
from src.pxe.pi_manager import validate_serial
from src.utils.network import get_server_url, get_primary_ip

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize workflow service
workflow_service = WorkflowService(settings.workflows_dir)


def get_pi_manager() -> PiManager:
    """Get configured PiManager instance.

    Returns:
        PiManager configured with paths from settings.
    """
    return PiManager(
        firmware_dir=settings.pi.firmware_dir,
        deploy_dir=settings.pi.deploy_dir,
        nodes_dir=settings.pi.nodes_dir,
    )


@router.get("/boot/pi", response_model=PiBootResponse)
async def get_pi_boot_instructions(
    serial: str = Query(
        ...,
        description="Pi serial number (8 hex characters from /proc/cpuinfo)",
        min_length=8,
        max_length=8,
    ),
    mac: str | None = Query(
        None,
        description="MAC address for auto-registration",
    ),
    db: AsyncSession = Depends(get_db),
    *,
    request: Request,
) -> PiBootResponse:
    """Get boot instructions for a Raspberry Pi.

    This endpoint is called by the Pi deploy environment during network boot
    to determine what action to take based on the node's current state.

    Args:
        serial: Pi serial number (8 hex characters).
        mac: Optional MAC address for auto-registration.
        request: FastAPI request object.
        db: Database session.

    Returns:
        PiBootResponse with state and action instructions.

    Raises:
        HTTPException: If serial number is invalid.
    """
    # Validate and normalize serial number
    serial = serial.lower()
    if not validate_serial(serial):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Pi serial number: {serial}. Must be 8 hexadecimal characters.",
        )

    # Validate MAC if provided
    if mac:
        if not MAC_PATTERN.match(mac):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid MAC address format: {mac}",
            )
        mac = normalize_mac(mac)

    # Get client IP
    client_ip = request.client.host if request and request.client else None
    server = get_server_url()

    # Look up node by serial number
    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.serial_number == serial)
    )
    node = result.scalar_one_or_none()

    if not node:
        # Node not found
        if not settings.registration.auto_register:
            # Auto-registration disabled - return local boot
            return PiBootResponse(
                state="unknown",
                message="Node not registered. Auto-registration disabled.",
                action="local_boot",
            )

        # Auto-register new node
        node = Node(
            serial_number=serial,
            mac_address=mac or f"pi-{serial}",  # Use placeholder if MAC not provided
            ip_address=client_ip,
            arch="aarch64",
            boot_mode="pi",
            pi_model="pi4",  # Default to Pi4, can be updated via register endpoint
            group_id=settings.registration.default_group_id,
        )
        db.add(node)
        await db.flush()

        # Create TFTP directory for the node
        try:
            pi_manager = get_pi_manager()
            pi_manager.create_node_directory(
                serial=serial,
                pi_model="pi4",
                controller_url=server,
            )
            logger.info(f"Created TFTP directory for Pi node: {serial}")
        except Exception as e:
            logger.error(f"Failed to create TFTP directory for {serial}: {e}")
            # Continue anyway - node is registered

        return PiBootResponse(
            state="discovered",
            message="Node registered. Awaiting workflow assignment.",
        )

    # Update last seen
    node.last_seen_at = datetime.now(timezone.utc)
    if client_ip:
        node.ip_address = client_ip
    if mac and (not node.mac_address or node.mac_address.startswith("pi-")):
        node.mac_address = mac

    # Return response based on node state
    match node.state:
        case "discovered":
            return PiBootResponse(
                state="discovered",
                message="Awaiting workflow assignment",
            )

        case "pending":
            # Check if workflow is assigned
            if not node.workflow_id:
                return PiBootResponse(
                    state="pending",
                    message="Pending but no workflow assigned",
                    action="local_boot",
                )

            # Load workflow and return appropriate action
            try:
                workflow = workflow_service.get_workflow(node.workflow_id)
                workflow = workflow_service.resolve_variables(
                    workflow,
                    server=server,
                    node_id=str(node.id),
                    mac=node.mac_address,
                    ip=node.ip_address,
                )
                return _get_workflow_response(node, workflow, server)
            except (WorkflowNotFoundError, ValueError) as e:
                logger.error(f"Failed to load workflow {node.workflow_id}: {e}")
                return PiBootResponse(
                    state="pending",
                    message=f"Workflow '{node.workflow_id}' not found",
                    action="local_boot",
                )

        case "installing":
            return PiBootResponse(
                state="installing",
                message="Installation in progress",
                action="wait",
            )

        case "installed" | "active":
            return PiBootResponse(
                state=node.state,
                message="Boot from local storage",
                action="local_boot",
            )

        case _:
            # Unknown or other states - default to local boot
            return PiBootResponse(
                state=node.state,
                message=f"State: {node.state}",
                action="local_boot",
            )


def _get_workflow_response(node: Node, workflow: Workflow, server: str) -> PiBootResponse:
    """Generate PiBootResponse based on workflow install method.

    Args:
        node: Node being booted.
        workflow: Resolved workflow definition.
        server: Server base URL.

    Returns:
        PiBootResponse with appropriate action and parameters.
    """
    callback_url = f"{server}/api/v1/nodes/{node.id}/installed"

    if workflow.install_method == "image":
        # Image-based deployment
        return PiBootResponse(
            state="installing",
            message=f"Deploying {workflow.name}",
            action="deploy_image",
            image_url=workflow.image_url,
            target_device=workflow.target_device,
            callback_url=callback_url,
        )

    elif workflow.install_method == "nfs":
        # NFS root boot (diskless)
        # Extract NFS parameters from workflow or use defaults from settings
        default_nfs_server = get_primary_ip() if settings.host == "0.0.0.0" else settings.host
        nfs_server = (
            workflow.boot_params.get("nfs_server")
            or getattr(workflow, "nfs_server", None)
            or default_nfs_server
        )
        nfs_base_path = (
            workflow.boot_params.get("nfs_path")
            or workflow.boot_params.get("nfs_base_path")
            or getattr(workflow, "nfs_base_path", None)
            or str(settings.nfs.root_path)
        )
        return PiBootResponse(
            state="installing",
            message=f"NFS boot: {workflow.name}",
            action="nfs_boot",
            nfs_server=nfs_server,
            nfs_path=nfs_base_path,
            callback_url=callback_url,
        )

    else:
        # Default to local boot for unsupported methods
        return PiBootResponse(
            state="pending",
            message=f"Workflow method '{workflow.install_method}' not supported for Pi",
            action="local_boot",
        )


@router.post("/nodes/register-pi", response_model=ApiResponse[NodeResponse])
async def register_pi_node(
    registration: PiRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[NodeResponse]:
    """Register or update a Raspberry Pi node.

    This endpoint is called by the Pi deploy environment to register itself
    with the controller during network boot.

    Args:
        registration: Pi registration data (serial, mac, model, ip_address).
        request: FastAPI request object.
        db: Database session.

    Returns:
        ApiResponse containing NodeResponse for the registered node.
    """
    serial = registration.serial
    mac = registration.mac
    pi_model = registration.model
    ip_address = registration.ip_address or (
        request.client.host if request.client else None
    )

    server = get_server_url()

    # Look up existing node by serial number
    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.serial_number == serial)
    )
    node = result.scalar_one_or_none()

    pi_manager = get_pi_manager()

    if node:
        # Update existing node
        node.mac_address = mac
        node.pi_model = pi_model
        if ip_address:
            node.ip_address = ip_address
        node.last_seen_at = datetime.now(timezone.utc)

        # Update TFTP config if model changed
        try:
            if pi_manager.node_exists(serial):
                pi_manager.update_config_txt(serial, pi_model)
                pi_manager.update_cmdline_txt(serial, server)
            else:
                pi_manager.create_node_directory(
                    serial=serial,
                    pi_model=pi_model,
                    controller_url=server,
                )
            logger.info(f"Updated TFTP config for Pi node: {serial}")
        except Exception as e:
            logger.error(f"Failed to update TFTP config for {serial}: {e}")

        await db.flush()
        await db.refresh(node, ["tags"])

        return ApiResponse(
            success=True,
            data=NodeResponse.from_node(node),
            message=f"Pi node {serial} updated",
        )

    else:
        # Create new node
        node = Node(
            serial_number=serial,
            mac_address=mac,
            ip_address=ip_address,
            arch="aarch64",
            boot_mode="pi",
            pi_model=pi_model,
            group_id=settings.registration.default_group_id,
        )
        db.add(node)
        await db.flush()

        # Create TFTP directory
        try:
            pi_manager.create_node_directory(
                serial=serial,
                pi_model=pi_model,
                controller_url=server,
            )
            logger.info(f"Created TFTP directory for new Pi node: {serial}")
        except Exception as e:
            logger.error(f"Failed to create TFTP directory for {serial}: {e}")

        await db.refresh(node, ["tags"])

        return ApiResponse(
            success=True,
            data=NodeResponse.from_node(node),
            message=f"Pi node {serial} registered",
        )
