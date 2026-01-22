"""Boot API endpoint for iPXE."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.state_service import StateTransitionService
from src.core.workflow_service import Workflow, WorkflowNotFoundError, WorkflowService
from src.db.database import get_db
from src.db.models import Node

router = APIRouter()

MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

workflow_service = WorkflowService(settings.workflows_dir)


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
    # Create short ID from last 6 chars of MAC (without colons)
    short_id = mac.replace(":", "")[-6:].upper()
    return f"""#!ipxe
# PureBoot - Node discovered
# MAC: {mac}

:start
echo
echo ========================================
echo   PureBoot - Node Discovered
echo ========================================
echo
echo   Node ID:  {short_id}
echo   MAC:      {mac}
echo   IP:       ${{net0/ip}}
echo   Gateway:  ${{net0/gateway}}
echo   Server:   {server}
echo
echo   Status: Waiting for workflow assignment
echo   Assign a workflow in the web UI to provision.
echo
echo ========================================
echo
echo   Press ESC for iPXE shell
echo   Auto-polling for workflow in 15 seconds...
echo

:prompt
prompt --key 0x1b --timeout 15000 Waiting... && goto shell ||

:wait
echo
echo [${{net0/ip}}] Checking for workflow assignment...
chain {server}/api/v1/boot?mac={mac} || goto retry

:retry
echo [${{net0/ip}}] Server unreachable, retrying in 30 seconds...
sleep 30
goto wait

:shell
echo
echo iPXE Shell - type 'goto start' to return
shell
goto start
"""


def generate_pending_script(node: Node, server: str) -> str:
    """Generate iPXE script for node pending installation."""
    short_id = node.mac_address.replace(":", "")[-6:].upper()
    return f"""#!ipxe
# PureBoot - Installation pending
# MAC: {node.mac_address}
# Workflow: {node.workflow_id or 'none'}
echo
echo ========================================
echo   PureBoot - Pending Installation
echo ========================================
echo
echo   Node ID:  {short_id}
echo   MAC:      {node.mac_address}
echo   IP:       ${{net0/ip}}
echo   Workflow: {node.workflow_id or 'Not assigned'}
echo
echo   Installation will begin on next boot.
echo   Booting from local disk in 5 seconds...
echo
sleep 5
exit
"""


def generate_install_script(node: Node, workflow: Workflow, server: str) -> str:
    """Generate iPXE script for OS installation."""
    kernel_url = f"{server}{workflow.kernel_path}"
    initrd_url = f"{server}{workflow.initrd_path}"
    short_id = node.mac_address.replace(":", "")[-6:].upper()

    return f"""#!ipxe
# PureBoot - Installing {workflow.name}
# Node: {node.mac_address}
# Workflow: {workflow.id}
echo
echo ========================================
echo   PureBoot - OS Installation
echo ========================================
echo
echo   Node ID:  {short_id}
echo   MAC:      {node.mac_address}
echo   IP:       ${{net0/ip}}
echo   Workflow: {workflow.name}
echo
echo Loading kernel...
kernel {kernel_url} {workflow.cmdline}
echo Loading initrd...
initrd {initrd_url}
echo
echo Starting installation...
boot
"""


def generate_pending_no_workflow_script(node: Node) -> str:
    """Generate iPXE script for pending node without workflow."""
    short_id = node.mac_address.replace(":", "")[-6:].upper()
    return f"""#!ipxe
# PureBoot - Pending (no workflow assigned)
# Node: {node.mac_address}
echo
echo ========================================
echo   PureBoot - No Workflow Assigned
echo ========================================
echo
echo   Node ID:  {short_id}
echo   MAC:      {node.mac_address}
echo   IP:       ${{net0/ip}}
echo
echo   Node is pending but no workflow assigned.
echo   Please assign a workflow in the PureBoot UI.
echo
echo   Booting from local disk in 10 seconds...
echo
sleep 10
exit
"""


def generate_workflow_error_script(node: Node, error_message: str) -> str:
    """Generate iPXE script for workflow/installation error."""
    return f"""#!ipxe
# PureBoot - Installation Error
# MAC: {node.mac_address}
# Error: {error_message}
echo
echo *** ERROR ***
echo
echo Node: {node.mac_address}
echo Error: {error_message}
echo
echo Manual intervention may be required.
echo
echo Booting from local disk in 30 seconds...
echo Press any key to enter iPXE shell.
sleep 30 || shell
exit
"""


def generate_install_retry_script(node: Node, server: str) -> str:
    """Generate iPXE script for install retry (still has retries left)."""
    return f"""#!ipxe
# PureBoot - Installation Retry
# MAC: {node.mac_address}
# Attempt: {node.install_attempts}
echo
echo Previous installation attempt timed out.
echo Retrying installation (attempt {node.install_attempts})...
echo
echo Booting from local disk...
echo Installation will restart on next provisioning cycle.
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
    node.last_seen_at = datetime.now(timezone.utc)
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
            # Check if workflow is assigned
            if not node.workflow_id:
                return generate_pending_no_workflow_script(node)

            # Load workflow and generate install script
            try:
                workflow = workflow_service.get_workflow(node.workflow_id)
                # Resolve variables in cmdline
                workflow = workflow_service.resolve_variables(
                    workflow,
                    server=server,
                    node_id=str(node.id),
                    mac=node.mac_address,
                    ip=node.ip_address,
                )
                return generate_install_script(node, workflow, server)
            except (WorkflowNotFoundError, ValueError):
                return generate_workflow_error_script(node, f"Workflow '{node.workflow_id}' not found")
        case "installing":
            # Check for installation timeout
            if settings.install_timeout_minutes > 0 and node.state_changed_at:
                elapsed = datetime.now(timezone.utc) - node.state_changed_at
                timeout_seconds = settings.install_timeout_minutes * 60
                if elapsed.total_seconds() > timeout_seconds:
                    # Installation timed out - handle as failure
                    await StateTransitionService.handle_install_failure(
                        db=db,
                        node=node,
                        error=f"Installation timed out after {settings.install_timeout_minutes} minutes",
                    )
                    await db.flush()
                    # Return appropriate script based on new state
                    if node.state == "install_failed":
                        return generate_workflow_error_script(
                            node, f"Timeout after {settings.install_timeout_minutes}m"
                        )
                    # Still has retries - return retry script (boot local to restart)
                    return generate_install_retry_script(node, server)
            # Normal installing state - boot local
            return generate_local_boot_script()
        case "installed" | "active" | "retired":
            return generate_local_boot_script()
        case _:
            # Default to local boot for unknown states
            return generate_local_boot_script()
