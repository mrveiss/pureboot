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

    return ApiResponse(data=[IscsiLunResponse.from_lun(lun) for lun in luns])


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

    return ApiResponse(data=IscsiLunResponse.from_lun(lun))


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
    from src.config import settings
    task = asyncio.create_task(_create_lun_background(lun.id, settings.database.url))
    _background_tasks[lun.id] = task

    return ApiResponse(
        data=IscsiLunResponse.from_lun(lun),
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

    return ApiResponse(data=IscsiLunResponse.from_lun(lun))


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
        raise HTTPException(
            status_code=400, detail="Cannot delete assigned LUN - unassign first"
        )

    # Set status and start background delete
    lun.status = "deleting"
    await db.commit()

    from src.config import settings
    task = asyncio.create_task(_delete_lun_background(lun.id, settings.database.url))
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
        raise HTTPException(
            status_code=400, detail=f"Cannot assign LUN in {lun.status} status"
        )
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
    if not backend:
        raise HTTPException(status_code=500, detail="Backend not found for LUN")
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
        data=IscsiLunResponse.from_lun(lun),
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
        if backend:
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
        data=IscsiLunResponse.from_lun(lun),
        message="LUN unassigned",
    )
