"""Boot API endpoint for iPXE."""
import re
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

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


@router.get("/boot", response_class=PlainTextResponse)
async def get_boot_script(mac: str, request: Request) -> str:
    """
    Return iPXE boot script for a node.

    The script returned depends on the node's current state:
    - Unknown node: Register as discovered, boot local
    - discovered: Boot local (waiting for assignment)
    - pending: Return installation script
    - installing: Boot local (installation in progress)
    - installed/active: Boot local

    Args:
        mac: MAC address of the booting node (colon or hyphen separated)
        request: FastAPI request object

    Returns:
        iPXE script as plain text
    """
    mac = validate_mac(mac)
    client_ip = request.client.host if request.client else "unknown"

    # TODO: Look up node in database
    # For now, always return local boot script

    # Log the boot request
    # logger.info(f"Boot request from {mac} ({client_ip})")

    return generate_local_boot_script()
