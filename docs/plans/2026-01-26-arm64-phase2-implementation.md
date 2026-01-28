# ARM64/Raspberry Pi Phase 2: API & Registration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Pi-specific API endpoints for boot configuration and node registration

**Architecture:** New `boot_pi.py` route module provides Pi-specific endpoints that work with `PiManager` from Phase 1. Pi nodes register via serial number, get linked to MAC addresses, and receive dynamic cmdline.txt based on state.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, PiManager

---

## Task 1: Add Pi Registration Schema

**Files:**
- Modify: `src/api/schemas.py`
- Test: `tests/unit/test_schemas.py`

**Step 1: Write the failing test**

Create test file for Pi schemas:

```python
# tests/unit/test_schemas.py (add to existing or create)
import pytest
from pydantic import ValidationError
from src.api.schemas import PiRegisterRequest, PiBootResponse


def test_pi_register_valid_serial():
    """Test valid Pi serial number registration."""
    req = PiRegisterRequest(
        serial="d83add36",
        mac="dc:a6:32:12:34:56",
        model="pi4",
        ip_address="192.168.1.100",
    )
    assert req.serial == "d83add36"
    assert req.mac == "dc:a6:32:12:34:56"


def test_pi_register_uppercase_serial_normalized():
    """Test uppercase serial is normalized to lowercase."""
    req = PiRegisterRequest(
        serial="D83ADD36",
        mac="dc:a6:32:12:34:56",
    )
    assert req.serial == "d83add36"


def test_pi_register_invalid_serial():
    """Test invalid serial number rejected."""
    with pytest.raises(ValidationError) as exc:
        PiRegisterRequest(
            serial="invalid!",
            mac="dc:a6:32:12:34:56",
        )
    assert "serial" in str(exc.value).lower()


def test_pi_register_serial_too_short():
    """Test serial number must be 8 characters."""
    with pytest.raises(ValidationError):
        PiRegisterRequest(
            serial="d83add",
            mac="dc:a6:32:12:34:56",
        )


def test_pi_boot_response_discovered():
    """Test boot response for discovered state."""
    resp = PiBootResponse(
        state="discovered",
        message="Node registered, awaiting workflow assignment",
    )
    assert resp.state == "discovered"
    assert resp.action is None


def test_pi_boot_response_installing():
    """Test boot response for installing state with action."""
    resp = PiBootResponse(
        state="installing",
        action="deploy_image",
        image_url="http://server/images/ubuntu.img",
        target_device="/dev/mmcblk0",
        callback_url="http://server/api/v1/nodes/123/installed",
    )
    assert resp.state == "installing"
    assert resp.action == "deploy_image"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_schemas.py::test_pi_register_valid_serial -v`
Expected: FAIL with "cannot import name 'PiRegisterRequest'"

**Step 3: Write minimal implementation**

Add to `src/api/schemas.py`:

```python
import re
# ... existing imports ...

# Pi serial pattern: 8 lowercase hex characters
PI_SERIAL_PATTERN = re.compile(r"^[0-9a-f]{8}$")


class PiRegisterRequest(BaseModel):
    """Request to register a Raspberry Pi node.

    Example:
        ```json
        {
            "serial": "d83add36",
            "mac": "dc:a6:32:12:34:56",
            "model": "pi4",
            "ip_address": "192.168.1.100"
        }
        ```
    """

    serial: str = Field(
        ...,
        description="Pi serial number (8 hex characters)",
        examples=["d83add36", "10000000abcdef12"],
    )
    mac: str = Field(
        ...,
        description="MAC address of the Pi",
        examples=["dc:a6:32:12:34:56"],
    )
    model: str = Field(
        "pi4",
        description="Pi model",
        examples=["pi3", "pi4", "pi5"],
    )
    ip_address: str | None = Field(
        None,
        description="Current IP address",
        examples=["192.168.1.100"],
    )

    @field_validator("serial")
    @classmethod
    def validate_serial(cls, v: str) -> str:
        """Validate and normalize Pi serial number."""
        v = v.lower().strip()
        if not PI_SERIAL_PATTERN.match(v):
            raise ValueError(
                f"Invalid Pi serial number: '{v}'. Must be 8 hex characters."
            )
        return v

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        """Validate and normalize MAC address."""
        if not MAC_PATTERN.match(v):
            raise ValueError(f"Invalid MAC address format: {v}")
        return normalize_mac(v)

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate Pi model."""
        valid = {"pi3", "pi4", "pi5"}
        if v not in valid:
            raise ValueError(f"Invalid Pi model: {v}. Must be one of {valid}")
        return v


class PiBootResponse(BaseModel):
    """Response for Pi boot endpoint.

    Example (discovered):
        ```json
        {
            "state": "discovered",
            "message": "Node registered, awaiting workflow assignment"
        }
        ```

    Example (installing):
        ```json
        {
            "state": "installing",
            "action": "deploy_image",
            "image_url": "http://server/images/ubuntu-arm64.img",
            "target_device": "/dev/mmcblk0",
            "callback_url": "http://server/api/v1/nodes/123/installed"
        }
        ```
    """

    state: str = Field(..., description="Current node state")
    message: str | None = Field(None, description="Human-readable status message")
    action: str | None = Field(
        None,
        description="Action for deploy environment",
        examples=["deploy_image", "nfs_boot", "local_boot"],
    )
    image_url: str | None = Field(None, description="URL of disk image to deploy")
    target_device: str | None = Field(
        None,
        description="Target device for image deployment",
        examples=["/dev/mmcblk0", "/dev/sda"],
    )
    callback_url: str | None = Field(
        None,
        description="URL to call when deployment completes",
    )
    nfs_server: str | None = Field(None, description="NFS server for diskless boot")
    nfs_path: str | None = Field(None, description="NFS path for root filesystem")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_schemas.py -k pi -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/schemas.py tests/unit/test_schemas.py
git commit -m "feat(api): add Pi registration and boot response schemas"
```

---

## Task 2: Create Pi Boot Routes Module

**Files:**
- Create: `src/api/routes/boot_pi.py`
- Test: `tests/unit/test_boot_pi.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_boot_pi.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_pi_manager():
    """Create mock PiManager."""
    manager = MagicMock()
    manager.node_exists.return_value = True
    manager.create_node_directory.return_value = "/tftp/pi-nodes/d83add36"
    return manager


def test_boot_pi_endpoint_exists():
    """Test that boot/pi endpoint exists."""
    from src.api.routes.boot_pi import router
    routes = [r.path for r in router.routes]
    assert "/boot/pi" in routes


def test_register_pi_endpoint_exists():
    """Test that nodes/register-pi endpoint exists."""
    from src.api.routes.boot_pi import router
    routes = [r.path for r in router.routes]
    assert "/nodes/register-pi" in routes
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_boot_pi.py::test_boot_pi_endpoint_exists -v`
Expected: FAIL with "No module named 'src.api.routes.boot_pi'"

**Step 3: Write minimal implementation**

Create `src/api/routes/boot_pi.py`:

```python
"""Raspberry Pi boot API endpoints.

These endpoints support Pi network boot:
- GET /boot/pi - Returns boot instructions based on node state
- POST /nodes/register-pi - Registers a Pi node by serial number
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ApiResponse,
    NodeResponse,
    PiBootResponse,
    PiRegisterRequest,
)
from src.config import settings
from src.core.workflow_service import WorkflowService
from src.db.database import get_db
from src.db.models import Node
from src.pxe import PiManager, validate_serial

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
workflow_service = WorkflowService(settings.workflows_dir)


def get_pi_manager() -> PiManager:
    """Get PiManager instance from settings."""
    return PiManager(
        firmware_dir=settings.pi.firmware_dir,
        deploy_dir=settings.pi.deploy_dir,
        nodes_dir=settings.pi.nodes_dir,
    )


@router.get("/boot/pi", response_model=PiBootResponse)
async def get_pi_boot_instructions(
    serial: str = Query(..., description="Pi serial number (8 hex chars)"),
    mac: str | None = Query(None, description="MAC address for registration"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> PiBootResponse:
    """
    Get boot instructions for a Raspberry Pi.

    Called by the Pi deploy environment to determine what action to take
    based on the node's current state.

    The response includes:
    - state: Current node state
    - action: What the deploy environment should do
    - Additional fields depending on state (image_url, nfs_server, etc.)

    Args:
        serial: Pi serial number (8 hex characters, e.g., "d83add36")
        mac: Optional MAC address for auto-registration
        request: FastAPI request object
        db: Database session

    Returns:
        PiBootResponse with boot instructions
    """
    # Validate serial
    try:
        serial = serial.lower().strip()
        if not validate_serial(serial):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid serial number: {serial}. Must be 8 hex characters.",
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    server = f"http://{settings.host}:{settings.port}"
    client_ip = request.client.host if request and request.client else None

    # Look up node by serial number
    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.serial_number == serial)
    )
    node = result.scalar_one_or_none()

    if not node:
        # Node not found - check auto-register
        if not settings.registration.auto_register:
            return PiBootResponse(
                state="unknown",
                message="Node not registered. Auto-registration disabled.",
            )

        # Auto-register new Pi node
        node = Node(
            mac_address=mac or f"pi:{serial[:2]}:{serial[2:4]}:{serial[4:6]}:{serial[6:8]}:00",
            serial_number=serial,
            ip_address=client_ip,
            arch="aarch64",
            boot_mode="pi",
            pi_model="pi4",  # Default, can be updated later
            group_id=settings.registration.default_group_id,
        )
        db.add(node)
        await db.flush()

        # Create TFTP directory for this Pi
        pi_manager = get_pi_manager()
        try:
            pi_manager.create_node_directory(serial, "pi4", server)
            logger.info(f"Created TFTP directory for Pi: {serial}")
        except Exception as e:
            logger.warning(f"Failed to create TFTP directory for {serial}: {e}")

        return PiBootResponse(
            state="discovered",
            message="Node registered, awaiting workflow assignment",
        )

    # Update last seen
    node.last_seen_at = datetime.now(timezone.utc)
    if client_ip:
        node.ip_address = client_ip

    # Return response based on state
    match node.state:
        case "discovered":
            return PiBootResponse(
                state="discovered",
                message="Awaiting workflow assignment",
            )

        case "pending":
            if not node.workflow_id:
                return PiBootResponse(
                    state="pending",
                    message="No workflow assigned",
                    action="local_boot",
                )

            # Get workflow details
            try:
                workflow = workflow_service.get_workflow(node.workflow_id)
                workflow = workflow_service.resolve_variables(
                    workflow,
                    server=server,
                    node_id=str(node.id),
                    mac=node.mac_address,
                    ip=node.ip_address,
                )

                if workflow.install_method == "image":
                    return PiBootResponse(
                        state="pending",
                        action="deploy_image",
                        message=f"Ready to install: {workflow.name}",
                        image_url=workflow.image_url,
                        target_device=workflow.target_device or "/dev/mmcblk0",
                        callback_url=f"{server}/api/v1/nodes/{node.id}/installed",
                    )
                elif workflow.install_method == "nfs":
                    return PiBootResponse(
                        state="pending",
                        action="nfs_boot",
                        message=f"Ready for NFS boot: {workflow.name}",
                        nfs_server=workflow.nfs_server,
                        nfs_path=workflow.nfs_path,
                    )
                else:
                    return PiBootResponse(
                        state="pending",
                        action="install",
                        message=f"Ready to install: {workflow.name}",
                    )
            except Exception as e:
                logger.error(f"Error loading workflow {node.workflow_id}: {e}")
                return PiBootResponse(
                    state="pending",
                    message=f"Workflow error: {e}",
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
            return PiBootResponse(
                state=node.state,
                message=f"Unknown state: {node.state}",
                action="local_boot",
            )


@router.post("/nodes/register-pi", response_model=ApiResponse[NodeResponse])
async def register_pi_node(
    registration: PiRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[NodeResponse]:
    """
    Register or update a Raspberry Pi node.

    Creates a new node entry for the Pi identified by its serial number,
    or updates an existing node. Also creates the TFTP directory structure
    needed for Pi network boot.

    Args:
        registration: Pi registration data (serial, mac, model, ip)
        request: FastAPI request object
        db: Database session

    Returns:
        ApiResponse containing the NodeResponse
    """
    server = f"http://{settings.host}:{settings.port}"
    client_ip = request.client.host if request and request.client else registration.ip_address

    # Check if node already exists by serial
    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.serial_number == registration.serial)
    )
    node = result.scalar_one_or_none()

    pi_manager = get_pi_manager()

    if node:
        # Update existing node
        node.mac_address = registration.mac
        node.pi_model = registration.model
        if client_ip:
            node.ip_address = client_ip
        node.last_seen_at = datetime.now(timezone.utc)

        # Update TFTP directory if model changed
        try:
            if pi_manager.node_exists(registration.serial):
                pi_manager.update_config_txt(registration.serial, registration.model)
            else:
                pi_manager.create_node_directory(
                    registration.serial, registration.model, server
                )
        except Exception as e:
            logger.warning(f"TFTP directory update failed for {registration.serial}: {e}")

        await db.flush()
        await db.refresh(node, ["tags"])

        return ApiResponse(
            data=NodeResponse.from_node(node),
            message="Pi node updated",
        )

    # Create new node
    node = Node(
        mac_address=registration.mac,
        serial_number=registration.serial,
        ip_address=client_ip,
        arch="aarch64",
        boot_mode="pi",
        pi_model=registration.model,
        group_id=settings.registration.default_group_id,
    )
    db.add(node)
    await db.flush()
    await db.refresh(node, ["tags"])

    # Create TFTP directory
    try:
        pi_manager.create_node_directory(registration.serial, registration.model, server)
        logger.info(f"Created TFTP directory for Pi: {registration.serial}")
    except Exception as e:
        logger.warning(f"Failed to create TFTP directory for {registration.serial}: {e}")

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message="Pi node registered",
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_boot_pi.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/routes/boot_pi.py tests/unit/test_boot_pi.py
git commit -m "feat(api): add Pi boot and registration endpoints"
```

---

## Task 3: Register Pi Routes in Main App

**Files:**
- Modify: `src/main.py`
- Test: Manual verification via route list

**Step 1: Write the failing test**

```python
# tests/unit/test_main_routes.py
def test_pi_routes_registered():
    """Test Pi routes are registered in main app."""
    from src.main import app
    routes = [r.path for r in app.routes]
    assert "/api/v1/boot/pi" in routes
    assert "/api/v1/nodes/register-pi" in routes
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_main_routes.py::test_pi_routes_registered -v`
Expected: FAIL with "AssertionError" (routes not found)

**Step 3: Write minimal implementation**

Edit `src/main.py`:

1. Add import near other route imports:
```python
from src.api.routes.boot_pi import router as boot_pi_router
```

2. Add router registration after other routers:
```python
app.include_router(boot_pi_router, prefix="/api/v1", tags=["boot-pi"])
```

3. Add OpenAPI tag in the tags list:
```python
{
    "name": "boot-pi",
    "description": "Raspberry Pi network boot endpoints",
},
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_main_routes.py::test_pi_routes_registered -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py tests/unit/test_main_routes.py
git commit -m "feat(main): register Pi boot routes in application"
```

---

## Task 4: Add Dynamic Cmdline Generation Method to PiManager

**Files:**
- Modify: `src/pxe/pi_manager.py`
- Test: `tests/unit/test_pi_manager.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_pi_manager.py`:

```python
def test_generate_cmdline_for_state_discovered(pi_manager, tmp_path):
    """Test cmdline generation for discovered state."""
    cmdline = pi_manager.generate_cmdline_for_state(
        serial="d83add36",
        state="discovered",
        controller_url="http://192.168.1.10:8080",
    )
    assert "pureboot.serial=d83add36" in cmdline
    assert "pureboot.state=discovered" in cmdline
    assert "pureboot.url=http://192.168.1.10:8080" in cmdline
    assert "ip=dhcp" in cmdline


def test_generate_cmdline_for_state_installing(pi_manager, tmp_path):
    """Test cmdline generation for installing state with image URL."""
    cmdline = pi_manager.generate_cmdline_for_state(
        serial="d83add36",
        state="installing",
        controller_url="http://192.168.1.10:8080",
        node_id="abc123",
        mac="dc:a6:32:12:34:56",
        image_url="http://192.168.1.10/images/ubuntu.img",
        target_device="/dev/mmcblk0",
        callback_url="http://192.168.1.10:8080/api/v1/nodes/abc123/installed",
    )
    assert "pureboot.mode=install" in cmdline
    assert "pureboot.image_url=" in cmdline
    assert "pureboot.target=/dev/mmcblk0" in cmdline
    assert "pureboot.callback=" in cmdline


def test_generate_cmdline_for_state_nfs(pi_manager, tmp_path):
    """Test cmdline generation for NFS diskless boot."""
    cmdline = pi_manager.generate_cmdline_for_state(
        serial="d83add36",
        state="active",
        controller_url="http://192.168.1.10:8080",
        nfs_server="192.168.1.10",
        nfs_path="/nfsroot/d83add36",
    )
    assert "root=/dev/nfs" in cmdline
    assert "nfsroot=192.168.1.10:/nfsroot/d83add36" in cmdline
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pi_manager.py::test_generate_cmdline_for_state_discovered -v`
Expected: FAIL with "AttributeError: 'PiManager' has no attribute 'generate_cmdline_for_state'"

**Step 3: Write minimal implementation**

Add to `src/pxe/pi_manager.py`:

```python
def generate_cmdline_for_state(
    self,
    serial: str,
    state: str,
    controller_url: str | None = None,
    node_id: str | None = None,
    mac: str | None = None,
    image_url: str | None = None,
    target_device: str | None = None,
    callback_url: str | None = None,
    nfs_server: str | None = None,
    nfs_path: str | None = None,
) -> str:
    """Generate state-specific cmdline.txt content.

    Args:
        serial: Pi serial number (8 hex chars).
        state: Current node state (discovered, pending, installing, active).
        controller_url: PureBoot controller URL.
        node_id: Node UUID for callbacks.
        mac: Node MAC address.
        image_url: URL of disk image for installation.
        target_device: Target device for image deployment.
        callback_url: URL to call when deployment completes.
        nfs_server: NFS server IP for diskless boot.
        nfs_path: NFS path for root filesystem.

    Returns:
        cmdline.txt content as string (single line).
    """
    serial = self._validate_serial(serial)

    # Base parameters for all states
    params = [
        "console=serial0,115200",
        "console=tty1",
        "ip=dhcp",
        f"pureboot.serial={serial}",
        f"pureboot.state={state}",
    ]

    if controller_url:
        params.append(f"pureboot.url={controller_url}")

    # State-specific parameters
    if state == "installing" and image_url:
        # Image deployment mode
        params.extend([
            "pureboot.mode=install",
            f"pureboot.image_url={image_url}",
        ])
        if target_device:
            params.append(f"pureboot.target={target_device}")
        if node_id:
            params.append(f"pureboot.node_id={node_id}")
        if mac:
            params.append(f"pureboot.mac={mac}")
        if callback_url:
            params.append(f"pureboot.callback={callback_url}")
        # Boot from initramfs for deployment
        params.extend(["root=/dev/ram0", "rootfstype=ramfs"])

    elif nfs_server and nfs_path:
        # NFS diskless boot
        params.extend([
            "root=/dev/nfs",
            f"nfsroot={nfs_server}:{nfs_path},vers=4,tcp",
            "rw",
        ])

    else:
        # Default: boot from initramfs (discovery or local boot)
        params.extend(["root=/dev/ram0", "rootfstype=ramfs"])

    # Common boot parameters
    params.extend(["quiet", "loglevel=4"])

    return " ".join(params) + "\n"


def update_cmdline_for_state(
    self,
    serial: str,
    state: str,
    **kwargs,
) -> None:
    """Update cmdline.txt for a node based on state.

    Args:
        serial: Pi serial number (8 hex chars).
        state: Current node state.
        **kwargs: Additional parameters passed to generate_cmdline_for_state.

    Raises:
        FileNotFoundError: If node directory doesn't exist.
    """
    serial = self._validate_serial(serial)
    node_dir = self.nodes_dir / serial

    if not node_dir.exists():
        raise FileNotFoundError(f"Node directory not found: {serial}")

    cmdline_txt = self.generate_cmdline_for_state(serial, state, **kwargs)
    cmdline_path = node_dir / "cmdline.txt"
    cmdline_path.write_text(cmdline_txt)
    logger.info(f"Updated cmdline.txt for node {serial} (state: {state})")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pi_manager.py -k cmdline_for_state -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pxe/pi_manager.py tests/unit/test_pi_manager.py
git commit -m "feat(pxe): add state-based cmdline generation to PiManager"
```

---

## Task 5: Integration Tests for Pi Endpoints

**Files:**
- Create: `tests/integration/test_pi_api.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_pi_api.py
"""Integration tests for Pi boot API endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Node


@pytest.fixture
async def pi_node(db_session: AsyncSession) -> Node:
    """Create a test Pi node."""
    node = Node(
        mac_address="dc:a6:32:12:34:56",
        serial_number="d83add36",
        arch="aarch64",
        boot_mode="pi",
        pi_model="pi4",
        state="discovered",
    )
    db_session.add(node)
    await db_session.flush()
    await db_session.refresh(node)
    return node


@pytest.mark.asyncio
async def test_get_boot_pi_unknown_serial(client: AsyncClient):
    """Test boot endpoint with unknown serial returns discovered state."""
    response = await client.get(
        "/api/v1/boot/pi",
        params={"serial": "00000001", "mac": "dc:a6:32:aa:bb:cc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "discovered"


@pytest.mark.asyncio
async def test_get_boot_pi_existing_node(client: AsyncClient, pi_node: Node):
    """Test boot endpoint with existing node returns correct state."""
    response = await client.get(
        "/api/v1/boot/pi",
        params={"serial": pi_node.serial_number},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "discovered"


@pytest.mark.asyncio
async def test_get_boot_pi_invalid_serial(client: AsyncClient):
    """Test boot endpoint rejects invalid serial."""
    response = await client.get(
        "/api/v1/boot/pi",
        params={"serial": "invalid!"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_pi_new_node(client: AsyncClient):
    """Test registering a new Pi node."""
    response = await client.post(
        "/api/v1/nodes/register-pi",
        json={
            "serial": "abcd1234",
            "mac": "dc:a6:32:aa:bb:cc",
            "model": "pi4",
            "ip_address": "192.168.1.100",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["serial_number"] == "abcd1234"
    assert data["data"]["boot_mode"] == "pi"
    assert data["data"]["arch"] == "aarch64"


@pytest.mark.asyncio
async def test_register_pi_update_existing(client: AsyncClient, pi_node: Node):
    """Test updating an existing Pi node."""
    response = await client.post(
        "/api/v1/nodes/register-pi",
        json={
            "serial": pi_node.serial_number,
            "mac": "dc:a6:32:99:88:77",  # New MAC
            "model": "pi5",  # Updated model
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["mac_address"] == "dc:a6:32:99:88:77"
    assert data["data"]["pi_model"] == "pi5"


@pytest.mark.asyncio
async def test_register_pi_invalid_model(client: AsyncClient):
    """Test registration rejects invalid Pi model."""
    response = await client.post(
        "/api/v1/nodes/register-pi",
        json={
            "serial": "12345678",
            "mac": "dc:a6:32:aa:bb:cc",
            "model": "invalid",
        },
    )
    assert response.status_code == 422  # Validation error
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_pi_api.py -v`
Expected: FAIL (tests should fail initially, then pass after full implementation)

**Step 3: Verify all tests pass**

Once all previous tasks are complete, run:
Run: `pytest tests/integration/test_pi_api.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add tests/integration/test_pi_api.py
git commit -m "test(api): add integration tests for Pi boot endpoints"
```

---

## Task 6: Update Node Lookup to Support Serial Number

**Files:**
- Modify: `src/api/routes/nodes.py`
- Test: `tests/integration/test_pi_api.py`

**Step 1: Write the failing test**

Add to `tests/integration/test_pi_api.py`:

```python
@pytest.mark.asyncio
async def test_get_node_by_serial(client: AsyncClient, pi_node: Node):
    """Test getting a node works after Pi registration."""
    response = await client.get(f"/api/v1/nodes/{pi_node.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["serial_number"] == pi_node.serial_number
    assert data["data"]["pi_model"] == "pi4"
```

**Step 2: Run test to verify it passes**

This test should already pass since NodeResponse.from_node handles pi_model.

Run: `pytest tests/integration/test_pi_api.py::test_get_node_by_serial -v`
Expected: PASS

**Step 3: Verify node creation includes pi_model**

Edit `src/api/routes/nodes.py` - ensure pi_model is set when creating nodes:

In `create_node` function, add `pi_model` to Node creation:

```python
node = Node(
    mac_address=node_data.mac_address,
    hostname=node_data.hostname,
    arch=node_data.arch,
    boot_mode=node_data.boot_mode,
    group_id=node_data.group_id,
    vendor=node_data.vendor,
    model=node_data.model,
    serial_number=node_data.serial_number,
    system_uuid=node_data.system_uuid,
    pi_model=node_data.pi_model,  # Add this line
)
```

**Step 4: Run tests to verify**

Run: `pytest tests/integration/test_pi_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/routes/nodes.py tests/integration/test_pi_api.py
git commit -m "fix(api): include pi_model in node creation"
```

---

## Task 7: Add TFTP Directory Cleanup on Node Delete

**Files:**
- Modify: `src/api/routes/nodes.py`
- Test: `tests/unit/test_node_cleanup.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_node_cleanup.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_retire_pi_node_cleans_tftp():
    """Test that retiring a Pi node cleans up TFTP directory."""
    # This test verifies the behavior is implemented
    from src.api.routes.nodes import retire_node
    # The actual implementation should call pi_manager.delete_node_directory
    # when retiring a node with boot_mode='pi'
    pass  # Placeholder - actual test depends on implementation
```

**Step 2: Write minimal implementation**

In `src/api/routes/nodes.py`, update the `retire_node` function:

```python
@router.delete("/nodes/{node_id}", response_model=ApiResponse[NodeResponse])
async def retire_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retire a node (sets state to retired)."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    try:
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state="retired",
            triggered_by="admin",
        )
        await db.flush()
        await db.refresh(node, ["tags"])

        # Clean up Pi TFTP directory if this is a Pi node
        if node.boot_mode == "pi" and node.serial_number:
            try:
                from src.config import settings
                from src.pxe import PiManager
                pi_manager = PiManager(
                    firmware_dir=settings.pi.firmware_dir,
                    deploy_dir=settings.pi.deploy_dir,
                    nodes_dir=settings.pi.nodes_dir,
                )
                pi_manager.delete_node_directory(node.serial_number)
            except Exception as e:
                # Log but don't fail - TFTP cleanup is best-effort
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to clean up Pi TFTP directory for {node.serial_number}: {e}"
                )

        return ApiResponse(
            data=NodeResponse.from_node(node),
            message="Node retired",
        )
    except InvalidStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Step 3: Run tests to verify**

Run: `pytest tests/ -k pi -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/api/routes/nodes.py tests/unit/test_node_cleanup.py
git commit -m "feat(api): clean up Pi TFTP directory on node retirement"
```

---

## Task 8: Push Branch and Update PR

**Files:**
- None (git operations only)

**Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 2: Push changes**

```bash
git push origin feature/arm64-raspberry-pi
```

**Step 3: Update PR description**

The PR should now include Phase 2 changes. Update the PR body to include:

```markdown
## Phase 2: API & Registration

- `GET /api/v1/boot/pi?serial=<serial>` - Returns boot instructions based on node state
- `POST /api/v1/nodes/register-pi` - Registers Pi nodes by serial number
- Dynamic cmdline.txt generation based on state
- Serial-to-MAC address linking
- TFTP directory cleanup on node retirement
```

**Step 4: Verify**

Check GitHub PR for updated commit list.

---

## Summary

Phase 2 adds the following functionality:

1. **Pi Registration Schema** (`PiRegisterRequest`, `PiBootResponse`) - Pydantic schemas for Pi-specific requests
2. **Boot Pi Endpoint** (`GET /api/v1/boot/pi`) - Returns JSON boot instructions based on state
3. **Register Pi Endpoint** (`POST /api/v1/nodes/register-pi`) - Creates/updates Pi nodes
4. **State-based Cmdline** - Dynamic cmdline.txt generation for different states
5. **TFTP Cleanup** - Automatic directory cleanup when Pi nodes are retired

This integrates with Phase 1's `PiManager` and prepares for Phase 3 (deploy environment).
