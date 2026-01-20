"""Boot API endpoint for iPXE."""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.database import get_db
from src.db.models import Node

router = APIRouter()

MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def normalize_mac(mac: str) -> str:
    """Normalize MAC address to colon-separated lowercase."""
    return mac.replace("-", ":").lower()


def validate_mac(mac: str) -> str:
    """Validate and normalize MAC address."""
    if not MAC_PATTERN.match(mac):
        raise HTTPException(status_code=400, detail=f"Invalid MAC address: {mac}")
    return normalize_mac(mac)


def generate_local_boot_script() -> str:
    """Generate iPXE script for local boot."""
    return """#!ipxe
# PureBoot - Boot from local disk
echo Booting from local disk...
exit
"""


def generate_discovery_script(mac: str, server: str) -> str:
    """Generate iPXE script for discovered node."""
    return f"""#!ipxe
# PureBoot - Node discovered
# MAC: {mac}
echo
echo Node registered with PureBoot server.
echo Waiting for provisioning assignment...
echo
echo Booting from local disk in 10 seconds...
echo Press any key to enter iPXE shell.
sleep 10 || shell
exit
"""


def generate_pending_script(node: Node, server: str) -> str:
    """Generate iPXE script for node pending installation."""
    return f"""#!ipxe
# PureBoot - Installation pending
# MAC: {node.mac_address}
# Workflow: {node.workflow_id or 'none'}
echo
echo Node ready for installation.
echo Workflow: {node.workflow_id or 'Not assigned'}
echo
echo Installation will begin on next boot with assigned workflow.
echo Booting from local disk...
sleep 5
exit
"""


@router.get("/boot", response_class=PlainTextResponse)
async def get_boot_script(
    mac: str,
    request: Request,
    vendor: str | None = Query(None, description="Hardware vendor"),
    model: str | None = Query(None, description="Hardware model"),
    serial: str | None = Query(None, description="Serial number"),
    uuid: str | None = Query(None, description="System UUID"),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Return iPXE boot script for a node.

    The script returned depends on the node's current state:
    - Unknown node: Register as discovered (if auto_register), boot local
    - discovered: Boot local (waiting for assignment)
    - pending: Return installation script
    - installing: Boot local (installation in progress)
    - installed/active: Boot local

    Args:
        mac: MAC address of the booting node
        vendor: Hardware vendor (from iPXE ${manufacturer})
        model: Hardware model (from iPXE ${product})
        serial: Serial number (from iPXE ${serial})
        uuid: System UUID (from iPXE ${uuid})
        request: FastAPI request object
        db: Database session

    Returns:
        iPXE script as plain text
    """
    mac = validate_mac(mac)
    client_ip = request.client.host if request.client else None
    server = f"http://{settings.host}:{settings.port}"

    # Look up node by MAC
    result = await db.execute(select(Node).where(Node.mac_address == mac))
    node = result.scalar_one_or_none()

    if not node:
        # Node not found
        if not settings.registration.auto_register:
            # Auto-registration disabled, just boot local
            return generate_local_boot_script()

        # Auto-register new node
        node = Node(
            mac_address=mac,
            ip_address=client_ip,
            vendor=vendor,
            model=model,
            serial_number=serial,
            system_uuid=uuid,
            group_id=settings.registration.default_group_id,
        )
        db.add(node)
        await db.flush()
        return generate_discovery_script(mac, server)

    # Update last seen and hardware info
    node.last_seen_at = datetime.utcnow()
    if client_ip:
        node.ip_address = client_ip
    if vendor and not node.vendor:
        node.vendor = vendor
    if model and not node.model:
        node.model = model
    if serial and not node.serial_number:
        node.serial_number = serial
    if uuid and not node.system_uuid:
        node.system_uuid = uuid

    # Return boot script based on state
    match node.state:
        case "discovered":
            return generate_discovery_script(mac, server)
        case "pending":
            return generate_pending_script(node, server)
        case "installing":
            # Let installation continue, boot local
            return generate_local_boot_script()
        case "installed" | "active" | "retired":
            return generate_local_boot_script()
        case _:
            # Default to local boot for unknown states
            return generate_local_boot_script()
