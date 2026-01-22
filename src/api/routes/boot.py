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
echo
echo  ************************************************************
echo  *                                                          *
echo  *                    P U R E B O O T                       *
echo  *              Network Boot Management System              *
echo  *                                                          *
echo  *     Press ESC now to skip and boot from local disk       *
echo  *                                                          *
echo  ************************************************************
echo
echo   Node ID:  {short_id}
echo   MAC:      {mac}
echo   IP:       ${{net0/ip}}
echo   Server:   {server}
echo
echo   Status: Discovered - awaiting workflow assignment
echo

:prompt
prompt --key 0x1b --timeout 10000 Press ESC to skip, waiting 10s... && goto skip ||

:wait
echo
echo [{short_id}] Polling server for workflow...
chain {server}/api/v1/boot?mac={mac} || goto retry

:retry
echo [{short_id}] Server unreachable, retry in 30s (ESC to skip)...
prompt --key 0x1b --timeout 30000 && goto skip ||
goto wait

:skip
echo
echo Skipping PureBoot - booting from local disk...
echo
exit
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
    """Generate iPXE script for OS installation.

    Supports three install methods:
    - kernel: Traditional kernel/initrd boot (default)
    - sanboot: Boot directly from ISO URL
    - chain: Chainload to another iPXE script/URL
    """
    short_id = node.mac_address.replace(":", "")[-6:].upper()

    # Common header for all methods
    header = f"""#!ipxe
# PureBoot - Installing {workflow.name}
# Node: {node.mac_address}
# Workflow: {workflow.id}
# Method: {workflow.install_method}
echo
echo ========================================
echo   PureBoot - OS Installation
echo ========================================
echo
echo   Node ID:  {short_id}
echo   MAC:      {node.mac_address}
echo   IP:       ${{net0/ip}}
echo   Workflow: {workflow.name}
echo   Method:   {workflow.install_method}
echo
"""

    # Generate boot commands based on install method
    if workflow.install_method == "sanboot":
        # Boot directly from ISO (for live installers)
        boot_url = workflow.boot_url
        if not boot_url:
            return generate_workflow_error_script(node, "sanboot method requires boot_url")
        boot_commands = f"""echo Booting from ISO: {boot_url}
echo
echo This may take several minutes to download...
echo
sanboot {boot_url} || goto error

:error
echo
echo *** BOOT FAILED ***
echo Failed to boot from ISO.
echo Press any key to enter iPXE shell.
sleep 30 || shell
exit
"""
    elif workflow.install_method == "chain":
        # Chainload to another URL (for custom boot scripts)
        boot_url = workflow.boot_url
        if not boot_url:
            return generate_workflow_error_script(node, "chain method requires boot_url")
        boot_commands = f"""echo Chainloading: {boot_url}
echo
chain {boot_url} || goto error

:error
echo
echo *** CHAIN FAILED ***
echo Failed to chainload boot script.
echo Press any key to enter iPXE shell.
sleep 30 || shell
exit
"""
    elif workflow.install_method == "image":
        # Image-based deployment: boot deploy kernel, stream disk image
        image_url = workflow.image_url
        if not image_url:
            return generate_workflow_error_script(node, "image method requires image_url")
        # Use .efi extension so iPXE recognizes it as EFI binary
        deploy_kernel = f"{server}/tftp/deploy/vmlinuz-virt.efi"
        deploy_initrd = f"{server}/tftp/deploy/initramfs-virt"
        # Pass deployment parameters via kernel cmdline
        # initrd= tells the EFI stub kernel the initrd filename
        deploy_cmdline = (
            f"initrd=initramfs-virt "
            f"ip=dhcp "
            f"pureboot.server={server} "
            f"pureboot.node_id={node.id} "
            f"pureboot.mac={node.mac_address} "
            f"pureboot.image_url={image_url} "
            f"pureboot.target={workflow.target_device} "
            f"pureboot.callback={server}/api/v1/nodes/{node.id}/installed "
            f"console=ttyS0 console=tty0"
        )
        if workflow.post_script_url:
            deploy_cmdline += f" pureboot.post_script={workflow.post_script_url}"
        # For UEFI: use imgfetch to load kernel as EFI binary, then imgexec
        # iPXE EFI cannot use bzImage format, but can execute EFI_STUB kernels directly
        boot_commands = f"""echo Image-based deployment
echo
echo   Image:  {image_url}
echo   Target: {workflow.target_device}
echo
echo Downloading initrd from {deploy_initrd}...
imgfetch --name initramfs-virt {deploy_initrd} || goto ierror
echo Downloading kernel (EFI) from {deploy_kernel}...
imgfetch --name kernel {deploy_kernel} || goto kerror
echo
echo Booting kernel as EFI binary...
imgargs kernel {deploy_cmdline}
imgexec kernel || goto booterror

:kerror
echo
echo *** KERNEL LOAD FAILED ***
echo Could not load: {deploy_kernel}
echo Press any key for shell...
prompt
shell

:ierror
echo
echo *** INITRD LOAD FAILED ***
echo Could not load: {deploy_initrd}
echo Press any key for shell...
prompt
shell

:booterror
echo
echo *** BOOT FAILED ***
echo Failed to start kernel.
echo Press any key for shell...
prompt
shell
"""
    elif workflow.install_method == "clone":
        # Clone mode: this node serves its disk as source for other nodes
        # Boots into deploy environment and runs disk server
        # Use .efi extension so iPXE recognizes it as EFI binary
        deploy_kernel = f"{server}/tftp/deploy/vmlinuz-virt.efi"
        deploy_initrd = f"{server}/tftp/deploy/initramfs-virt"
        # Pass clone server parameters via kernel cmdline
        # initrd= tells the EFI stub kernel the initrd filename
        deploy_cmdline = (
            f"initrd=initramfs-virt "
            f"ip=dhcp "
            f"pureboot.server={server} "
            f"pureboot.node_id={node.id} "
            f"pureboot.mac={node.mac_address} "
            f"pureboot.mode=clone_source "
            f"pureboot.source_device={workflow.source_device} "
            f"pureboot.callback={server}/api/v1/nodes/{node.id}/clone-ready "
            f"console=ttyS0 console=tty0"
        )
        # For UEFI: use imgfetch to load kernel as EFI binary, then imgexec
        # iPXE EFI cannot use bzImage format, but can execute EFI_STUB kernels directly
        boot_commands = f"""echo Clone Source Mode
echo
echo   This node will serve its disk for cloning
echo   Source: {workflow.source_device}
echo
echo   Other nodes can clone from this machine.
echo   Do NOT shut down until cloning is complete.
echo
echo Downloading initrd from {deploy_initrd}...
imgfetch --name initramfs-virt {deploy_initrd} || goto ierror
echo Downloading kernel (EFI) from {deploy_kernel}...
imgfetch --name kernel {deploy_kernel} || goto kerror
echo
echo Booting kernel as EFI binary...
imgargs kernel {deploy_cmdline}
imgexec kernel || goto booterror

:kerror
echo
echo *** KERNEL LOAD FAILED ***
echo Could not load: {deploy_kernel}
echo Press any key for shell...
prompt
shell

:ierror
echo
echo *** INITRD LOAD FAILED ***
echo Could not load: {deploy_initrd}
echo Press any key for shell...
prompt
shell

:booterror
echo
echo *** BOOT FAILED ***
echo Failed to start kernel.
echo Press any key for shell...
prompt
shell
"""
    else:
        # Default: kernel/initrd boot
        kernel_url = f"{server}{workflow.kernel_path}"
        initrd_url = f"{server}{workflow.initrd_path}"
        boot_commands = f"""echo Loading kernel...
kernel {kernel_url} {workflow.cmdline} || goto error
echo Loading initrd...
initrd {initrd_url} || goto error
echo
echo Starting installation...
boot

:error
echo
echo *** BOOT FAILED ***
echo Failed to load kernel or initrd.
echo Press any key to enter iPXE shell.
sleep 30 || shell
exit
"""

    return header + boot_commands


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
