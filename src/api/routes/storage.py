"""Storage backend management API endpoints."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    StorageBackendCreate,
    StorageBackendResponse,
    StorageBackendUpdate,
    StorageTestResult,
    NfsConfig,
    HttpConfig,
    S3Config,
    IscsiTargetConfig,
)
from src.core.storage import get_backend_service
from src.db.database import get_db
from src.db.models import StorageBackend

router = APIRouter()


def validate_config(backend_type: str, config: dict) -> dict:
    """Validate config based on backend type."""
    validators = {
        "nfs": NfsConfig,
        "http": HttpConfig,
        "s3": S3Config,
        "iscsi": IscsiTargetConfig,
    }
    validator = validators.get(backend_type)
    if not validator:
        raise HTTPException(status_code=400, detail=f"Unknown backend type: {backend_type}")

    try:
        validated = validator(**config)
        return validated.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/storage/backends", response_model=ApiListResponse[StorageBackendResponse])
async def list_backends(
    db: AsyncSession = Depends(get_db),
):
    """List all storage backends."""
    result = await db.execute(select(StorageBackend))
    backends = result.scalars().all()

    return ApiListResponse(
        data=[StorageBackendResponse.from_backend(b) for b in backends],
        total=len(backends),
    )


@router.post("/storage/backends", response_model=ApiResponse[StorageBackendResponse], status_code=201)
async def create_backend(
    backend_data: StorageBackendCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new storage backend."""
    # Check for duplicate name
    existing = await db.execute(
        select(StorageBackend).where(StorageBackend.name == backend_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Backend '{backend_data.name}' already exists",
        )

    # Validate config based on type
    validated_config = validate_config(backend_data.type, backend_data.config)

    backend = StorageBackend(
        name=backend_data.name,
        type=backend_data.type,
        config_json=json.dumps(validated_config),
        status="offline",
    )
    db.add(backend)
    await db.flush()

    return ApiResponse(
        data=StorageBackendResponse.from_backend(backend),
        message="Storage backend created successfully",
    )


@router.get("/storage/backends/{backend_id}", response_model=ApiResponse[StorageBackendResponse])
async def get_backend(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get storage backend details."""
    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == backend_id)
    )
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")

    return ApiResponse(data=StorageBackendResponse.from_backend(backend))


@router.patch("/storage/backends/{backend_id}", response_model=ApiResponse[StorageBackendResponse])
async def update_backend(
    backend_id: str,
    backend_data: StorageBackendUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a storage backend."""
    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == backend_id)
    )
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")

    if backend_data.name and backend_data.name != backend.name:
        existing = await db.execute(
            select(StorageBackend).where(StorageBackend.name == backend_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Backend '{backend_data.name}' already exists",
            )
        backend.name = backend_data.name

    if backend_data.config:
        validated_config = validate_config(backend.type, backend_data.config)
        backend.config_json = json.dumps(validated_config)

    await db.flush()

    return ApiResponse(
        data=StorageBackendResponse.from_backend(backend),
        message="Backend updated successfully",
    )


@router.delete("/storage/backends/{backend_id}", response_model=ApiResponse[dict])
async def delete_backend(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a storage backend."""
    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == backend_id)
    )
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")

    # Unmount if NFS
    if backend.type == "nfs" and backend.mount_point:
        config = json.loads(backend.config_json)
        service = get_backend_service(backend.id, backend.type, config)
        await service.unmount()

    await db.delete(backend)
    await db.flush()

    return ApiResponse(
        data={"id": backend_id},
        message="Backend deleted successfully",
    )


@router.post("/storage/backends/{backend_id}/test", response_model=ApiResponse[StorageTestResult])
async def test_backend(
    backend_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Test storage backend connection."""
    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == backend_id)
    )
    backend = result.scalar_one_or_none()

    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")

    config = json.loads(backend.config_json)
    service = get_backend_service(backend.id, backend.type, config)

    success, message = await service.test_connection()

    # Update status based on test result
    backend.status = "online" if success else "error"

    # If successful and NFS, try to mount and get stats
    if success and backend.type == "nfs":
        mount_point = await service.mount()
        if mount_point:
            backend.mount_point = mount_point
            stats = await service.get_stats()
            backend.used_bytes = stats["used_bytes"]
            backend.total_bytes = stats["total_bytes"]
            backend.file_count = stats["file_count"]

    await db.flush()

    return ApiResponse(
        data=StorageTestResult(success=success, message=message),
    )
