# iSCSI LUN API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement iSCSI LUN API endpoints for creating, managing, and assigning boot LUNs to nodes.

**Architecture:** New `IscsiLun` database model with FK to `StorageBackend` and `Node`. Service layer (`IscsiLunService`) wraps targetcli commands for LUN operations. Asyncio background tasks handle long-running create/delete operations. CHAP passwords encrypted with Fernet.

**Tech Stack:** FastAPI, SQLAlchemy, asyncio, targetcli (shell), cryptography (Fernet)

**Working Directory:** `/home/kali/Desktop/PureBoot/PureBoot/.worktrees/feature-iscsi-lun`

**IMPORTANT:** This is a code-editing-only environment. Do NOT run pip install, pytest, python, or any execution commands. Only create/edit files and make git commits.

---

## Task 1: Add IscsiLun Database Model

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add IscsiLun model**

Add after the `StorageBackend` class:

```python
class IscsiLun(Base):
    """iSCSI LUN for boot-from-SAN and storage provisioning."""

    __tablename__ = "iscsi_luns"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    size_gb: Mapped[int] = mapped_column(nullable=False)

    # Reference to iSCSI storage backend
    backend_id: Mapped[str] = mapped_column(
        ForeignKey("storage_backends.id"), nullable=False
    )
    backend: Mapped[StorageBackend] = relationship()

    # iSCSI identifiers
    iqn: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    lun_number: Mapped[int] = mapped_column(default=0)

    # Purpose and status
    purpose: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # boot_from_san, install_source, auto_provision
    status: Mapped[str] = mapped_column(
        String(20), default="creating", index=True
    )  # creating, ready, active, error, deleting
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Node assignment
    assigned_node_id: Mapped[str | None] = mapped_column(
        ForeignKey("nodes.id"), nullable=True
    )
    assigned_node: Mapped["Node | None"] = relationship()

    # CHAP authentication (password encrypted)
    chap_enabled: Mapped[bool] = mapped_column(default=False)
    chap_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    chap_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )
```

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat(db): add IscsiLun model"
```

---

## Task 2: Add iSCSI LUN Schemas

**Files:**
- Modify: `src/api/schemas.py`

**Step 1: Add iSCSI LUN schemas**

Add at the end of the file:

```python
# ============== iSCSI LUN Schemas ==============


class IscsiLunCreate(BaseModel):
    """Schema for creating an iSCSI LUN."""
    name: str
    size_gb: int
    backend_id: str
    purpose: Literal["boot_from_san", "install_source", "auto_provision"]
    chap_enabled: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("Name must contain only alphanumeric characters and hyphens")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Name cannot start or end with a hyphen")
        return v.lower()

    @field_validator("size_gb")
    @classmethod
    def validate_size(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Size must be at least 1 GB")
        if v > 10000:
            raise ValueError("Size cannot exceed 10000 GB")
        return v


class IscsiLunUpdate(BaseModel):
    """Schema for updating an iSCSI LUN."""
    name: str | None = None
    chap_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("Name must contain only alphanumeric characters and hyphens")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Name cannot start or end with a hyphen")
        return v.lower()


class IscsiLunResponse(BaseModel):
    """Response schema for iSCSI LUN."""
    id: str
    name: str
    size_gb: int
    backend_id: str
    backend_name: str
    iqn: str
    lun_number: int
    purpose: str
    status: str
    error_message: str | None
    assigned_node_id: str | None
    assigned_node_name: str | None
    chap_enabled: bool
    chap_username: str | None
    created_at: datetime
    updated_at: datetime


class LunAssign(BaseModel):
    """Schema for assigning a LUN to a node."""
    node_id: str
```

**Step 2: Add Literal import if not present**

Ensure the import section includes:
```python
from typing import Literal
```

**Step 3: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat(api): add iSCSI LUN schemas"
```

---

## Task 3: Create iSCSI LUN Service

**Files:**
- Create: `src/core/iscsi.py`

**Step 1: Create the iSCSI service module**

```python
"""iSCSI LUN service layer using targetcli."""
import asyncio
import logging
import os
import secrets
import string
from base64 import urlsafe_b64decode, urlsafe_b64encode

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Encryption key derivation
_SECRET_KEY = os.environ.get("PUREBOOT_SECRET_KEY", "pureboot-dev-secret-key-change-in-prod")
_SALT = b"pureboot-iscsi-salt"


def _get_fernet() -> Fernet:
    """Get Fernet instance for encryption/decryption."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480000,
    )
    key = urlsafe_b64encode(kdf.derive(_SECRET_KEY.encode()))
    return Fernet(key)


def encrypt_password(password: str) -> str:
    """Encrypt a CHAP password."""
    f = _get_fernet()
    return f.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt a CHAP password."""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def generate_chap_password(length: int = 16) -> str:
    """Generate a random CHAP password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_iqn(name: str) -> str:
    """Generate an IQN for a LUN."""
    return f"iqn.2026-01.local.pureboot:{name}"


def generate_initiator_iqn(mac_address: str) -> str:
    """Generate an initiator IQN for a node."""
    # Remove colons and lowercase
    mac_clean = mac_address.replace(":", "").lower()
    return f"iqn.2026-01.local.pureboot:node:{mac_clean}"


class IscsiLunService:
    """Service for managing iSCSI LUNs via targetcli."""

    def __init__(self, backend_config: dict):
        self.config = backend_config
        self.target_name = backend_config.get("target_name", "iqn.2026-01.local.pureboot:target1")
        self.portal_ip = backend_config.get("portal_ip", "0.0.0.0")
        self.portal_port = backend_config.get("portal_port", 3260)
        self.backingstore_type = backend_config.get("backingstore_type", "file")
        self.backingstore_path = backend_config.get("backingstore_path", "/var/lib/pureboot/luns")

    async def _run_targetcli(self, *args: str) -> tuple[bool, str]:
        """Run a targetcli command."""
        cmd = ["sudo", "targetcli"] + list(args)
        logger.info(f"Running: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode != 0:
                error = stderr.decode().strip() or stdout.decode().strip()
                logger.error(f"targetcli failed: {error}")
                return False, error

            return True, stdout.decode().strip()
        except asyncio.TimeoutError:
            logger.error("targetcli command timed out")
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"targetcli error: {e}")
            return False, str(e)

    async def create_backingstore(self, name: str, size_gb: int) -> tuple[bool, str]:
        """Create a backingstore for a LUN."""
        if self.backingstore_type == "file":
            # Ensure directory exists
            os.makedirs(self.backingstore_path, exist_ok=True)
            file_path = f"{self.backingstore_path}/{name}.img"
            return await self._run_targetcli(
                f"/backstores/fileio create {name} {file_path} {size_gb}G sparse=true"
            )
        elif self.backingstore_type == "block":
            # Assume LVM - backingstore_path is the VG name
            vg_name = self.backingstore_path
            # First create the LV
            create_lv = await asyncio.create_subprocess_exec(
                "sudo", "lvcreate", "-L", f"{size_gb}G", "-n", name, vg_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await create_lv.communicate()
            if create_lv.returncode != 0:
                return False, stderr.decode().strip()

            # Then create the block backingstore
            return await self._run_targetcli(
                f"/backstores/block create {name} /dev/{vg_name}/{name}"
            )
        else:
            return False, f"Unknown backingstore type: {self.backingstore_type}"

    async def delete_backingstore(self, name: str) -> tuple[bool, str]:
        """Delete a backingstore."""
        if self.backingstore_type == "file":
            success, msg = await self._run_targetcli(f"/backstores/fileio delete {name}")
            if success:
                # Also remove the file
                file_path = f"{self.backingstore_path}/{name}.img"
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            return success, msg
        elif self.backingstore_type == "block":
            success, msg = await self._run_targetcli(f"/backstores/block delete {name}")
            if success:
                # Also remove the LV
                vg_name = self.backingstore_path
                await asyncio.create_subprocess_exec(
                    "sudo", "lvremove", "-f", f"/dev/{vg_name}/{name}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            return success, msg
        else:
            return False, f"Unknown backingstore type: {self.backingstore_type}"

    async def create_lun(self, name: str, lun_number: int = 0) -> tuple[bool, str]:
        """Create a LUN under the target."""
        backingstore = "fileio" if self.backingstore_type == "file" else "block"
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/luns create /backstores/{backingstore}/{name} lun={lun_number}"
        )

    async def delete_lun(self, lun_number: int) -> tuple[bool, str]:
        """Delete a LUN from the target."""
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/luns delete lun{lun_number}"
        )

    async def create_acl(self, initiator_iqn: str) -> tuple[bool, str]:
        """Create an ACL for an initiator."""
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/acls create {initiator_iqn}"
        )

    async def delete_acl(self, initiator_iqn: str) -> tuple[bool, str]:
        """Delete an ACL for an initiator."""
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/acls delete {initiator_iqn}"
        )

    async def set_chap(self, initiator_iqn: str, username: str, password: str) -> tuple[bool, str]:
        """Set CHAP credentials for an initiator."""
        return await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/acls/{initiator_iqn} set auth userid={username} password={password}"
        )

    async def save_config(self) -> tuple[bool, str]:
        """Save targetcli configuration."""
        return await self._run_targetcli("saveconfig")

    async def ensure_target_exists(self) -> tuple[bool, str]:
        """Ensure the iSCSI target exists, create if not."""
        # Check if target exists
        success, output = await self._run_targetcli("/iscsi ls")
        if self.target_name in output:
            return True, "Target exists"

        # Create target
        success, msg = await self._run_targetcli(f"/iscsi create {self.target_name}")
        if not success:
            return False, msg

        # Set portal
        await self._run_targetcli(
            f"/iscsi/{self.target_name}/tpg1/portals create {self.portal_ip} {self.portal_port}"
        )

        # Enable target
        await self._run_targetcli(f"/iscsi/{self.target_name}/tpg1 set attribute authentication=0")
        await self._run_targetcli(f"/iscsi/{self.target_name}/tpg1 set attribute generate_node_acls=0")

        return await self.save_config()
```

**Step 2: Commit**

```bash
git add src/core/iscsi.py
git commit -m "feat(core): add iSCSI LUN service with targetcli integration"
```

---

## Task 4: Create iSCSI LUN Routes

**Files:**
- Create: `src/api/routes/luns.py`

**Step 1: Create the LUN routes module**

```python
"""iSCSI LUN API endpoints."""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ApiResponse,
    IscsiLunCreate,
    IscsiLunUpdate,
    IscsiLunResponse,
    LunAssign,
)
from src.core.iscsi import (
    IscsiLunService,
    encrypt_password,
    decrypt_password,
    generate_chap_password,
    generate_iqn,
    generate_initiator_iqn,
)
from src.db.database import get_db
from src.db.models import IscsiLun, StorageBackend, Node

logger = logging.getLogger(__name__)
router = APIRouter()

# Track background tasks
_background_tasks: dict[str, asyncio.Task] = {}


def _lun_to_response(lun: IscsiLun) -> IscsiLunResponse:
    """Convert LUN model to response schema."""
    return IscsiLunResponse(
        id=lun.id,
        name=lun.name,
        size_gb=lun.size_gb,
        backend_id=lun.backend_id,
        backend_name=lun.backend.name if lun.backend else "Unknown",
        iqn=lun.iqn,
        lun_number=lun.lun_number,
        purpose=lun.purpose,
        status=lun.status,
        error_message=lun.error_message,
        assigned_node_id=lun.assigned_node_id,
        assigned_node_name=lun.assigned_node.hostname if lun.assigned_node else None,
        chap_enabled=lun.chap_enabled,
        chap_username=lun.chap_username,
        created_at=lun.created_at,
        updated_at=lun.updated_at,
    )


async def _create_lun_background(lun_id: str, db_url: str):
    """Background task to create LUN via targetcli."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # Get the LUN
            result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
            lun = result.scalar_one_or_none()
            if not lun:
                logger.error(f"LUN {lun_id} not found for background creation")
                return

            # Get backend config
            result = await db.execute(
                select(StorageBackend).where(StorageBackend.id == lun.backend_id)
            )
            backend = result.scalar_one_or_none()
            if not backend:
                lun.status = "error"
                lun.error_message = "Backend not found"
                await db.commit()
                return

            config = json.loads(backend.config_json)
            service = IscsiLunService(config)

            # Ensure target exists
            success, msg = await service.ensure_target_exists()
            if not success:
                lun.status = "error"
                lun.error_message = f"Failed to ensure target: {msg}"
                await db.commit()
                return

            # Create backingstore
            success, msg = await service.create_backingstore(lun.name, lun.size_gb)
            if not success:
                lun.status = "error"
                lun.error_message = f"Failed to create backingstore: {msg}"
                await db.commit()
                return

            # Create LUN
            success, msg = await service.create_lun(lun.name, lun.lun_number)
            if not success:
                # Cleanup backingstore
                await service.delete_backingstore(lun.name)
                lun.status = "error"
                lun.error_message = f"Failed to create LUN: {msg}"
                await db.commit()
                return

            # Save config
            await service.save_config()

            # Update status
            lun.status = "ready"
            lun.error_message = None
            await db.commit()
            logger.info(f"LUN {lun.name} created successfully")

        except Exception as e:
            logger.exception(f"Error creating LUN {lun_id}")
            try:
                result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
                lun = result.scalar_one_or_none()
                if lun:
                    lun.status = "error"
                    lun.error_message = str(e)
                    await db.commit()
            except Exception:
                pass
        finally:
            await engine.dispose()


async def _delete_lun_background(lun_id: str, db_url: str):
    """Background task to delete LUN via targetcli."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # Get the LUN
            result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
            lun = result.scalar_one_or_none()
            if not lun:
                logger.error(f"LUN {lun_id} not found for background deletion")
                return

            # Get backend config
            result = await db.execute(
                select(StorageBackend).where(StorageBackend.id == lun.backend_id)
            )
            backend = result.scalar_one_or_none()
            if not backend:
                # Just delete the record
                await db.delete(lun)
                await db.commit()
                return

            config = json.loads(backend.config_json)
            service = IscsiLunService(config)

            # Delete LUN
            await service.delete_lun(lun.lun_number)

            # Delete backingstore
            await service.delete_backingstore(lun.name)

            # Save config
            await service.save_config()

            # Delete record
            await db.delete(lun)
            await db.commit()
            logger.info(f"LUN {lun.name} deleted successfully")

        except Exception as e:
            logger.exception(f"Error deleting LUN {lun_id}")
            try:
                result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
                lun = result.scalar_one_or_none()
                if lun:
                    lun.status = "error"
                    lun.error_message = f"Delete failed: {str(e)}"
                    await db.commit()
            except Exception:
                pass
        finally:
            await engine.dispose()


@router.get("/storage/luns", response_model=ApiResponse[list[IscsiLunResponse]])
async def list_luns(
    backend_id: str | None = Query(default=None, description="Filter by backend ID"),
    status: str | None = Query(default=None, description="Filter by status"),
    purpose: str | None = Query(default=None, description="Filter by purpose"),
    db: AsyncSession = Depends(get_db),
):
    """List all iSCSI LUNs."""
    query = select(IscsiLun)

    if backend_id:
        query = query.where(IscsiLun.backend_id == backend_id)
    if status:
        query = query.where(IscsiLun.status == status)
    if purpose:
        query = query.where(IscsiLun.purpose == purpose)

    result = await db.execute(query)
    luns = result.scalars().all()

    return ApiResponse(data=[_lun_to_response(lun) for lun in luns])


@router.get("/storage/luns/{lun_id}", response_model=ApiResponse[IscsiLunResponse])
async def get_lun(
    lun_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get an iSCSI LUN by ID."""
    result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
    lun = result.scalar_one_or_none()

    if not lun:
        raise HTTPException(status_code=404, detail="LUN not found")

    return ApiResponse(data=_lun_to_response(lun))


@router.post("/storage/luns", response_model=ApiResponse[IscsiLunResponse])
async def create_lun(
    body: IscsiLunCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new iSCSI LUN."""
    # Verify backend exists and is iSCSI type
    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == body.backend_id)
    )
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")
    if backend.type != "iscsi":
        raise HTTPException(status_code=400, detail="Backend must be iSCSI type")

    # Check for duplicate name
    result = await db.execute(select(IscsiLun).where(IscsiLun.name == body.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="LUN name already exists")

    # Get next LUN number for this backend
    result = await db.execute(
        select(IscsiLun)
        .where(IscsiLun.backend_id == body.backend_id)
        .order_by(IscsiLun.lun_number.desc())
    )
    last_lun = result.scalar_one_or_none()
    next_lun_number = (last_lun.lun_number + 1) if last_lun else 0

    # Generate IQN
    iqn = generate_iqn(body.name)

    # Create CHAP credentials if enabled
    chap_username = None
    chap_password_encrypted = None
    if body.chap_enabled:
        chap_username = body.name
        chap_password = generate_chap_password()
        chap_password_encrypted = encrypt_password(chap_password)

    # Create LUN record
    lun = IscsiLun(
        name=body.name,
        size_gb=body.size_gb,
        backend_id=body.backend_id,
        iqn=iqn,
        lun_number=next_lun_number,
        purpose=body.purpose,
        status="creating",
        chap_enabled=body.chap_enabled,
        chap_username=chap_username,
        chap_password_encrypted=chap_password_encrypted,
    )
    db.add(lun)
    await db.commit()
    await db.refresh(lun)

    # Start background task
    from src.db.database import DATABASE_URL
    task = asyncio.create_task(_create_lun_background(lun.id, DATABASE_URL))
    _background_tasks[lun.id] = task

    return ApiResponse(
        data=_lun_to_response(lun),
        message="LUN creation started",
    )


@router.patch("/storage/luns/{lun_id}", response_model=ApiResponse[IscsiLunResponse])
async def update_lun(
    lun_id: str,
    body: IscsiLunUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an iSCSI LUN."""
    result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
    lun = result.scalar_one_or_none()

    if not lun:
        raise HTTPException(status_code=404, detail="LUN not found")

    if lun.status not in ("ready", "active"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update LUN in {lun.status} status"
        )

    if body.name is not None:
        # Check for duplicate
        result = await db.execute(
            select(IscsiLun).where(IscsiLun.name == body.name, IscsiLun.id != lun_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="LUN name already exists")
        lun.name = body.name
        lun.iqn = generate_iqn(body.name)

    if body.chap_enabled is not None:
        lun.chap_enabled = body.chap_enabled
        if body.chap_enabled and not lun.chap_username:
            lun.chap_username = lun.name
            lun.chap_password_encrypted = encrypt_password(generate_chap_password())

    await db.commit()
    await db.refresh(lun)

    return ApiResponse(data=_lun_to_response(lun))


@router.delete("/storage/luns/{lun_id}", status_code=204)
async def delete_lun(
    lun_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete an iSCSI LUN."""
    result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
    lun = result.scalar_one_or_none()

    if not lun:
        raise HTTPException(status_code=404, detail="LUN not found")

    if lun.status == "creating":
        raise HTTPException(status_code=400, detail="Cannot delete LUN while creating")
    if lun.status == "deleting":
        raise HTTPException(status_code=400, detail="LUN already being deleted")
    if lun.assigned_node_id:
        raise HTTPException(status_code=400, detail="Cannot delete assigned LUN - unassign first")

    # Set status and start background delete
    lun.status = "deleting"
    await db.commit()

    from src.db.database import DATABASE_URL
    task = asyncio.create_task(_delete_lun_background(lun.id, DATABASE_URL))
    _background_tasks[lun.id] = task


@router.post("/storage/luns/{lun_id}/assign", response_model=ApiResponse[IscsiLunResponse])
async def assign_lun(
    lun_id: str,
    body: LunAssign,
    db: AsyncSession = Depends(get_db),
):
    """Assign a LUN to a node."""
    # Get LUN
    result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
    lun = result.scalar_one_or_none()

    if not lun:
        raise HTTPException(status_code=404, detail="LUN not found")
    if lun.status not in ("ready", "active"):
        raise HTTPException(status_code=400, detail=f"Cannot assign LUN in {lun.status} status")
    if lun.assigned_node_id:
        raise HTTPException(status_code=400, detail="LUN already assigned")

    # Get node
    result = await db.execute(select(Node).where(Node.id == body.node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Get backend config
    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == lun.backend_id)
    )
    backend = result.scalar_one_or_none()
    config = json.loads(backend.config_json)
    service = IscsiLunService(config)

    # Create ACL for node
    initiator_iqn = generate_initiator_iqn(node.mac_address)
    success, msg = await service.create_acl(initiator_iqn)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to create ACL: {msg}")

    # Set CHAP if enabled
    if lun.chap_enabled and lun.chap_username and lun.chap_password_encrypted:
        password = decrypt_password(lun.chap_password_encrypted)
        success, msg = await service.set_chap(initiator_iqn, lun.chap_username, password)
        if not success:
            # Cleanup ACL
            await service.delete_acl(initiator_iqn)
            raise HTTPException(status_code=500, detail=f"Failed to set CHAP: {msg}")

    await service.save_config()

    # Update LUN
    lun.assigned_node_id = node.id
    lun.status = "active"
    await db.commit()
    await db.refresh(lun)

    return ApiResponse(
        data=_lun_to_response(lun),
        message=f"LUN assigned to {node.hostname or node.mac_address}",
    )


@router.post("/storage/luns/{lun_id}/unassign", response_model=ApiResponse[IscsiLunResponse])
async def unassign_lun(
    lun_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Unassign a LUN from a node."""
    # Get LUN with node
    result = await db.execute(select(IscsiLun).where(IscsiLun.id == lun_id))
    lun = result.scalar_one_or_none()

    if not lun:
        raise HTTPException(status_code=404, detail="LUN not found")
    if not lun.assigned_node_id:
        raise HTTPException(status_code=400, detail="LUN not assigned")

    # Get node
    result = await db.execute(select(Node).where(Node.id == lun.assigned_node_id))
    node = result.scalar_one_or_none()

    if node:
        # Get backend config
        result = await db.execute(
            select(StorageBackend).where(StorageBackend.id == lun.backend_id)
        )
        backend = result.scalar_one_or_none()
        config = json.loads(backend.config_json)
        service = IscsiLunService(config)

        # Remove ACL
        initiator_iqn = generate_initiator_iqn(node.mac_address)
        await service.delete_acl(initiator_iqn)
        await service.save_config()

    # Update LUN
    lun.assigned_node_id = None
    lun.status = "ready"
    await db.commit()
    await db.refresh(lun)

    return ApiResponse(
        data=_lun_to_response(lun),
        message="LUN unassigned",
    )
```

**Step 2: Commit**

```bash
git add src/api/routes/luns.py
git commit -m "feat(api): add iSCSI LUN routes"
```

---

## Task 5: Register LUN Router and Add Dependencies

**Files:**
- Modify: `src/main.py`
- Modify: `src/db/database.py`
- Modify: `requirements.txt`

**Step 1: Update database.py to export DATABASE_URL**

Add near the top of the file after the DATABASE_URL definition:

```python
# Export for background tasks
DATABASE_URL = DATABASE_URL  # Already defined, just ensure it's accessible
```

Or if DATABASE_URL is defined inline, extract it to a module-level constant.

**Step 2: Update main.py imports**

Change:
```python
from src.api.routes import boot, ipxe, nodes, groups, storage, files
```
To:
```python
from src.api.routes import boot, ipxe, nodes, groups, storage, files, luns
```

**Step 3: Add router registration in main.py**

Add after the files router:
```python
app.include_router(luns.router, prefix="/api/v1", tags=["luns"])
```

**Step 4: Add cryptography to requirements.txt**

Add:
```
cryptography>=41.0.0
```

**Step 5: Commit**

```bash
git add src/main.py src/db/database.py requirements.txt
git commit -m "feat(api): register LUN router and add cryptography dependency"
```

---

## Task 6: Create Issue for Task Queue Overhaul

**Files:**
- None (GitHub issue)

**Step 1: Create GitHub issue for future task queue system**

```bash
gh issue create --title "Refactor: Implement proper task queue system" --body "## Description

Replace asyncio background tasks with a proper task queue system for long-running operations.

## Current State

- LUN create/delete use asyncio background tasks
- Tasks are fire-and-forget with no retry logic
- No visibility into task progress
- Tasks lost if server restarts

## Proposed Solution

Implement a task queue system using one of:
- Celery + Redis (most robust)
- ARQ (async Redis queue)
- Dramatiq + Redis
- RQ (simpler Redis queue)

## Requirements

- [ ] Task persistence (survive restarts)
- [ ] Retry logic with exponential backoff
- [ ] Task progress tracking
- [ ] Task cancellation
- [ ] Dead letter queue for failed tasks
- [ ] Task scheduling (for periodic operations)
- [ ] Web UI for task monitoring (optional)

## Affected Areas

- iSCSI LUN operations (create, delete)
- Future: VM provisioning
- Future: Bulk node operations
- Future: Scheduled maintenance tasks

## Related

- #16 (iSCSI LUN API - uses asyncio tasks as interim solution)"
```

**Step 2: Note the issue number for reference**

---

## Task 7: Push and Create PR

**Step 1: Push branch**

```bash
git push -u origin feature/iscsi-lun
```

**Step 2: Create PR**

Create PR referencing issue #16.

---

## Summary

**Files created:**
- `src/core/iscsi.py` - iSCSI LUN service with targetcli integration
- `src/api/routes/luns.py` - LUN API endpoints

**Files modified:**
- `src/db/models.py` - Added IscsiLun model
- `src/api/schemas.py` - Added LUN schemas
- `src/main.py` - Registered LUN router
- `src/db/database.py` - Export DATABASE_URL
- `requirements.txt` - Added cryptography

**Endpoints implemented:**
- `GET /api/v1/storage/luns` - List LUNs
- `GET /api/v1/storage/luns/{id}` - Get LUN
- `POST /api/v1/storage/luns` - Create LUN (async)
- `PATCH /api/v1/storage/luns/{id}` - Update LUN
- `DELETE /api/v1/storage/luns/{id}` - Delete LUN (async)
- `POST /api/v1/storage/luns/{id}/assign` - Assign to node
- `POST /api/v1/storage/luns/{id}/unassign` - Unassign from node

**Future work:**
- Task queue system (new issue created)
- iPXE sanboot integration
