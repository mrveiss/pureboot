"""System status and configuration API routes."""
import socket
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.database import get_db
from src.db.models import Node

router = APIRouter(prefix="/system", tags=["system"])


class DhcpIssue(BaseModel):
    """A detected DHCP configuration issue."""
    type: str
    count: int
    received: str | None = None
    expected: str | None = None
    affected_macs: list[str] = []


class DhcpRequiredSettings(BaseModel):
    """Required DHCP server settings."""
    next_server: str
    filename_bios: str
    filename_uefi: str


class DhcpStatus(BaseModel):
    """DHCP configuration status."""
    nodes_connected: int
    nodes_with_issues: int
    last_connection: datetime | None
    issues: list[DhcpIssue]


class DhcpStatusResponse(BaseModel):
    """Response for DHCP status endpoint."""
    server_ip: str
    server_port: int
    tftp_enabled: bool
    tftp_port: int
    required_settings: DhcpRequiredSettings
    status: DhcpStatus
    first_run: bool


def get_server_ip() -> str:
    """Auto-detect the server's IP address."""
    try:
        # Create a socket to determine the outgoing IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        # Doesn't actually send anything, just determines routing
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Fallback to configured host or localhost
        if settings.host != "0.0.0.0":
            return settings.host
        return "127.0.0.1"


@router.get("/dhcp-status", response_model=DhcpStatusResponse)
async def get_dhcp_status(db: AsyncSession = Depends(get_db)) -> DhcpStatusResponse:
    """
    Get DHCP configuration status and required settings.

    Returns the server IP, required DHCP options, and any detected
    configuration issues from connected nodes.
    """
    server_ip = get_server_ip()

    # Count total nodes
    total_result = await db.execute(select(func.count(Node.id)))
    total_nodes = total_result.scalar() or 0

    # Get last seen timestamp
    last_seen_result = await db.execute(
        select(func.max(Node.last_seen_at))
    )
    last_connection = last_seen_result.scalar()

    # For now, we don't have DHCP info stored on nodes yet
    # This will be populated when nodes report their DHCP config
    # TODO: Add dhcp_next_server, dhcp_filename columns to Node model
    issues: list[DhcpIssue] = []
    nodes_with_issues = 0

    return DhcpStatusResponse(
        server_ip=server_ip,
        server_port=settings.port,
        tftp_enabled=settings.tftp.enabled,
        tftp_port=settings.tftp.port,
        required_settings=DhcpRequiredSettings(
            next_server=server_ip,
            filename_bios="bios/undionly.kpxe",
            filename_uefi="uefi/ipxe.efi",
        ),
        status=DhcpStatus(
            nodes_connected=total_nodes,
            nodes_with_issues=nodes_with_issues,
            last_connection=last_connection,
            issues=issues,
        ),
        first_run=total_nodes == 0,
    )


class ServerInfoResponse(BaseModel):
    """Basic server information."""
    version: str
    server_ip: str
    http_port: int
    tftp_enabled: bool
    tftp_port: int
    dhcp_proxy_enabled: bool
    dhcp_proxy_port: int


@router.get("/info", response_model=ServerInfoResponse)
async def get_server_info() -> ServerInfoResponse:
    """Get basic server information."""
    return ServerInfoResponse(
        version="0.1.0",
        server_ip=get_server_ip(),
        http_port=settings.port,
        tftp_enabled=settings.tftp.enabled,
        tftp_port=settings.tftp.port,
        dhcp_proxy_enabled=settings.dhcp_proxy.enabled,
        dhcp_proxy_port=settings.dhcp_proxy.port,
    )
