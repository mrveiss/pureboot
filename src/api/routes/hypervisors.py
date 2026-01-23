"""Hypervisor management API endpoints."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import Hypervisor
from src.api.schemas import ApiResponse, ApiListResponse

router = APIRouter(prefix="/hypervisors", tags=["hypervisors"])


# ============== Schemas ==============


class HypervisorCreate(BaseModel):
    """Schema for creating a hypervisor connection."""

    name: str = Field(..., min_length=2, max_length=100)
    type: str = Field(..., description="Hypervisor type: ovirt or proxmox")
    api_url: str = Field(..., description="API URL (e.g., https://ovirt.example.com/ovirt-engine/api)")
    username: str | None = Field(None, description="Username for authentication")
    password: str | None = Field(None, description="Password for authentication")
    verify_ssl: bool = Field(True, description="Verify SSL certificates")

    def model_post_init(self, __context):
        if self.type not in ("ovirt", "proxmox"):
            raise ValueError("Type must be 'ovirt' or 'proxmox'")


class HypervisorUpdate(BaseModel):
    """Schema for updating a hypervisor connection."""

    name: str | None = Field(None, min_length=2, max_length=100)
    api_url: str | None = None
    username: str | None = None
    password: str | None = None
    verify_ssl: bool | None = None


class HypervisorResponse(BaseModel):
    """Response schema for hypervisor."""

    id: str
    name: str
    type: str
    api_url: str
    username: str | None
    verify_ssl: bool
    status: str
    last_error: str | None
    last_sync_at: datetime | None
    vm_count: int
    host_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, h: Hypervisor) -> "HypervisorResponse":
        return cls(
            id=h.id,
            name=h.name,
            type=h.type,
            api_url=h.api_url,
            username=h.username,
            verify_ssl=h.verify_ssl,
            status=h.status,
            last_error=h.last_error,
            last_sync_at=h.last_sync_at,
            vm_count=h.vm_count,
            host_count=h.host_count,
            created_at=h.created_at,
            updated_at=h.updated_at,
        )


class HypervisorTestResult(BaseModel):
    """Result of hypervisor connection test."""

    success: bool
    message: str
    version: str | None = None
    vm_count: int | None = None
    host_count: int | None = None


class VMResponse(BaseModel):
    """VM information from hypervisor."""

    id: str
    name: str
    status: str
    cpu_cores: int | None = None
    memory_mb: int | None = None
    os_type: str | None = None
    ip_addresses: list[str] = []
    host: str | None = None


class VMTemplateResponse(BaseModel):
    """VM template from hypervisor."""

    id: str
    name: str
    os_type: str | None = None
    cpu_cores: int | None = None
    memory_mb: int | None = None


# ============== Helper Functions ==============


def encrypt_password(password: str) -> str:
    """Encrypt password for storage.

    Note: For production, use proper encryption with a secret key.
    This is a placeholder that just base64 encodes.
    """
    import base64
    return base64.b64encode(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt password from storage."""
    import base64
    return base64.b64decode(encrypted.encode()).decode()


# ============== Endpoints ==============


@router.get("", response_model=ApiListResponse[HypervisorResponse])
async def list_hypervisors(
    db: AsyncSession = Depends(get_db),
):
    """List all configured hypervisors."""
    result = await db.execute(select(Hypervisor).order_by(Hypervisor.name))
    hypervisors = result.scalars().all()

    return ApiListResponse(
        data=[HypervisorResponse.from_model(h) for h in hypervisors],
        total=len(hypervisors),
    )


@router.post("", response_model=ApiResponse[HypervisorResponse], status_code=201)
async def create_hypervisor(
    data: HypervisorCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new hypervisor connection."""
    # Check for duplicate name
    existing = await db.execute(
        select(Hypervisor).where(Hypervisor.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Hypervisor with name '{data.name}' already exists",
        )

    hypervisor = Hypervisor(
        name=data.name,
        type=data.type,
        api_url=data.api_url,
        username=data.username,
        password_encrypted=encrypt_password(data.password) if data.password else None,
        verify_ssl=data.verify_ssl,
        status="unknown",
    )
    db.add(hypervisor)
    await db.flush()
    await db.refresh(hypervisor)

    return ApiResponse(
        data=HypervisorResponse.from_model(hypervisor),
        message=f"Hypervisor '{data.name}' added successfully",
    )


@router.get("/{hypervisor_id}", response_model=ApiResponse[HypervisorResponse])
async def get_hypervisor(
    hypervisor_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get hypervisor details."""
    result = await db.execute(
        select(Hypervisor).where(Hypervisor.id == hypervisor_id)
    )
    hypervisor = result.scalar_one_or_none()

    if not hypervisor:
        raise HTTPException(status_code=404, detail="Hypervisor not found")

    return ApiResponse(data=HypervisorResponse.from_model(hypervisor))


@router.patch("/{hypervisor_id}", response_model=ApiResponse[HypervisorResponse])
async def update_hypervisor(
    hypervisor_id: str,
    data: HypervisorUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update hypervisor configuration."""
    result = await db.execute(
        select(Hypervisor).where(Hypervisor.id == hypervisor_id)
    )
    hypervisor = result.scalar_one_or_none()

    if not hypervisor:
        raise HTTPException(status_code=404, detail="Hypervisor not found")

    # Check for duplicate name
    if data.name and data.name != hypervisor.name:
        existing = await db.execute(
            select(Hypervisor).where(Hypervisor.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Hypervisor with name '{data.name}' already exists",
            )

    update_data = data.model_dump(exclude_unset=True)

    # Handle password encryption
    if "password" in update_data:
        password = update_data.pop("password")
        if password:
            update_data["password_encrypted"] = encrypt_password(password)

    for field, value in update_data.items():
        setattr(hypervisor, field, value)

    await db.flush()
    await db.refresh(hypervisor)

    return ApiResponse(
        data=HypervisorResponse.from_model(hypervisor),
        message="Hypervisor updated successfully",
    )


@router.delete("/{hypervisor_id}", response_model=ApiResponse)
async def delete_hypervisor(
    hypervisor_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a hypervisor connection."""
    result = await db.execute(
        select(Hypervisor).where(Hypervisor.id == hypervisor_id)
    )
    hypervisor = result.scalar_one_or_none()

    if not hypervisor:
        raise HTTPException(status_code=404, detail="Hypervisor not found")

    name = hypervisor.name
    await db.delete(hypervisor)
    await db.flush()

    return ApiResponse(
        success=True,
        data=None,
        message=f"Hypervisor '{name}' deleted",
    )


@router.post("/{hypervisor_id}/test", response_model=ApiResponse[HypervisorTestResult])
async def test_hypervisor_connection(
    hypervisor_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Test hypervisor connection and update status."""
    result = await db.execute(
        select(Hypervisor).where(Hypervisor.id == hypervisor_id)
    )
    hypervisor = result.scalar_one_or_none()

    if not hypervisor:
        raise HTTPException(status_code=404, detail="Hypervisor not found")

    # Decrypt password for testing
    password = None
    if hypervisor.password_encrypted:
        try:
            password = decrypt_password(hypervisor.password_encrypted)
        except Exception:
            pass

    # Test connection based on type
    try:
        if hypervisor.type == "ovirt":
            test_result = await _test_ovirt_connection(
                hypervisor.api_url,
                hypervisor.username,
                password,
                hypervisor.verify_ssl,
            )
        elif hypervisor.type == "proxmox":
            test_result = await _test_proxmox_connection(
                hypervisor.api_url,
                hypervisor.username,
                password,
                hypervisor.verify_ssl,
            )
        else:
            test_result = HypervisorTestResult(
                success=False,
                message=f"Unknown hypervisor type: {hypervisor.type}",
            )

        # Update status
        hypervisor.status = "online" if test_result.success else "error"
        hypervisor.last_error = None if test_result.success else test_result.message
        hypervisor.last_sync_at = datetime.now(timezone.utc)
        if test_result.vm_count is not None:
            hypervisor.vm_count = test_result.vm_count
        if test_result.host_count is not None:
            hypervisor.host_count = test_result.host_count

        await db.flush()

        return ApiResponse(
            data=test_result,
            message="Connection test completed",
        )

    except Exception as e:
        hypervisor.status = "error"
        hypervisor.last_error = str(e)
        await db.flush()

        return ApiResponse(
            data=HypervisorTestResult(
                success=False,
                message=f"Connection failed: {e}",
            ),
            message="Connection test failed",
        )


@router.get("/{hypervisor_id}/vms", response_model=ApiListResponse[VMResponse])
async def list_hypervisor_vms(
    hypervisor_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List VMs from the hypervisor."""
    result = await db.execute(
        select(Hypervisor).where(Hypervisor.id == hypervisor_id)
    )
    hypervisor = result.scalar_one_or_none()

    if not hypervisor:
        raise HTTPException(status_code=404, detail="Hypervisor not found")

    password = None
    if hypervisor.password_encrypted:
        try:
            password = decrypt_password(hypervisor.password_encrypted)
        except Exception:
            pass

    try:
        if hypervisor.type == "ovirt":
            vms = await _list_ovirt_vms(
                hypervisor.api_url,
                hypervisor.username,
                password,
                hypervisor.verify_ssl,
            )
        elif hypervisor.type == "proxmox":
            vms = await _list_proxmox_vms(
                hypervisor.api_url,
                hypervisor.username,
                password,
                hypervisor.verify_ssl,
            )
        else:
            vms = []

        return ApiListResponse(data=vms, total=len(vms))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list VMs: {e}",
        )


@router.get("/{hypervisor_id}/templates", response_model=ApiListResponse[VMTemplateResponse])
async def list_hypervisor_templates(
    hypervisor_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List VM templates from the hypervisor."""
    result = await db.execute(
        select(Hypervisor).where(Hypervisor.id == hypervisor_id)
    )
    hypervisor = result.scalar_one_or_none()

    if not hypervisor:
        raise HTTPException(status_code=404, detail="Hypervisor not found")

    password = None
    if hypervisor.password_encrypted:
        try:
            password = decrypt_password(hypervisor.password_encrypted)
        except Exception:
            pass

    try:
        if hypervisor.type == "ovirt":
            templates = await _list_ovirt_templates(
                hypervisor.api_url,
                hypervisor.username,
                password,
                hypervisor.verify_ssl,
            )
        elif hypervisor.type == "proxmox":
            templates = await _list_proxmox_templates(
                hypervisor.api_url,
                hypervisor.username,
                password,
                hypervisor.verify_ssl,
            )
        else:
            templates = []

        return ApiListResponse(data=templates, total=len(templates))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list templates: {e}",
        )


# ============== Hypervisor API Stubs ==============
# These are placeholder implementations that return mock data.
# Real implementation would use ovirt-engine-sdk-python and proxmoxer libraries.


async def _test_ovirt_connection(
    api_url: str,
    username: str | None,
    password: str | None,
    verify_ssl: bool,
) -> HypervisorTestResult:
    """Test oVirt/RHV connection.

    Real implementation would use:
        import ovirtsdk4 as sdk
        connection = sdk.Connection(url=api_url, username=username, password=password, insecure=not verify_ssl)
        api = connection.system_service().get()
    """
    # Stub: Return mock success
    return HypervisorTestResult(
        success=True,
        message="Connection successful (stub)",
        version="4.5.0",
        vm_count=12,
        host_count=3,
    )


async def _test_proxmox_connection(
    api_url: str,
    username: str | None,
    password: str | None,
    verify_ssl: bool,
) -> HypervisorTestResult:
    """Test Proxmox VE connection.

    Real implementation would use:
        from proxmoxer import ProxmoxAPI
        proxmox = ProxmoxAPI(host, user=username, password=password, verify_ssl=verify_ssl)
        version = proxmox.version.get()
    """
    # Stub: Return mock success
    return HypervisorTestResult(
        success=True,
        message="Connection successful (stub)",
        version="8.1.3",
        vm_count=8,
        host_count=2,
    )


async def _list_ovirt_vms(
    api_url: str,
    username: str | None,
    password: str | None,
    verify_ssl: bool,
) -> list[VMResponse]:
    """List VMs from oVirt. Stub implementation."""
    # Return mock data
    return [
        VMResponse(
            id="vm-001",
            name="web-server-01",
            status="up",
            cpu_cores=4,
            memory_mb=8192,
            os_type="rhel_8x64",
            ip_addresses=["192.168.1.10"],
            host="hypervisor-01",
        ),
        VMResponse(
            id="vm-002",
            name="db-server-01",
            status="up",
            cpu_cores=8,
            memory_mb=32768,
            os_type="rhel_9x64",
            ip_addresses=["192.168.1.20"],
            host="hypervisor-02",
        ),
    ]


async def _list_proxmox_vms(
    api_url: str,
    username: str | None,
    password: str | None,
    verify_ssl: bool,
) -> list[VMResponse]:
    """List VMs from Proxmox. Stub implementation."""
    # Return mock data
    return [
        VMResponse(
            id="100",
            name="ubuntu-web",
            status="running",
            cpu_cores=2,
            memory_mb=4096,
            os_type="l26",
            ip_addresses=["10.0.0.100"],
            host="pve-node-01",
        ),
        VMResponse(
            id="101",
            name="debian-app",
            status="stopped",
            cpu_cores=4,
            memory_mb=8192,
            os_type="l26",
            ip_addresses=[],
            host="pve-node-01",
        ),
    ]


async def _list_ovirt_templates(
    api_url: str,
    username: str | None,
    password: str | None,
    verify_ssl: bool,
) -> list[VMTemplateResponse]:
    """List VM templates from oVirt. Stub implementation."""
    return [
        VMTemplateResponse(
            id="template-001",
            name="RHEL 9 Base",
            os_type="rhel_9x64",
            cpu_cores=2,
            memory_mb=4096,
        ),
        VMTemplateResponse(
            id="template-002",
            name="Windows Server 2022",
            os_type="windows_2022",
            cpu_cores=4,
            memory_mb=8192,
        ),
    ]


async def _list_proxmox_templates(
    api_url: str,
    username: str | None,
    password: str | None,
    verify_ssl: bool,
) -> list[VMTemplateResponse]:
    """List VM templates from Proxmox. Stub implementation."""
    return [
        VMTemplateResponse(
            id="9000",
            name="ubuntu-24.04-template",
            os_type="l26",
            cpu_cores=2,
            memory_mb=2048,
        ),
        VMTemplateResponse(
            id="9001",
            name="debian-12-template",
            os_type="l26",
            cpu_cores=1,
            memory_mb=1024,
        ),
    ]
