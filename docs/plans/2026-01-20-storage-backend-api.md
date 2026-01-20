# Storage Backend API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Storage Backends API with full NFS and HTTP support (S3 and iSCSI stubbed for later).

**Architecture:** Add StorageBackend model to database, create Pydantic schemas for validation, implement service layer for backend-specific operations (mount NFS, test HTTP connectivity), and expose REST endpoints following existing patterns.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, aiohttp (HTTP backend), subprocess (NFS mount)

**Working Directory:** `/home/kali/Desktop/PureBoot/PureBoot/.worktrees/feature-storage-backend`

**IMPORTANT:** This is a code-editing-only environment. Do NOT run pip install, pytest, or any execution commands. Only create/edit files and make git commits.

---

## Task 1: Add StorageBackend Database Model

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add StorageBackend model**

Add after the `NodeTag` class:

```python
class StorageBackend(Base):
    """Storage backend configuration (NFS, iSCSI, S3, HTTP)."""

    __tablename__ = "storage_backends"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # nfs, iscsi, s3, http
    status: Mapped[str] = mapped_column(String(10), default="offline")  # online, offline, error

    # Type-specific config stored as JSON
    config_json: Mapped[str] = mapped_column(String(2000), nullable=False)

    # Cached stats (updated periodically)
    used_bytes: Mapped[int] = mapped_column(default=0)
    total_bytes: Mapped[int | None] = mapped_column(nullable=True)
    file_count: Mapped[int] = mapped_column(default=0)

    # Mount point for NFS (set when mounted)
    mount_point: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )
```

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat(db): add StorageBackend model"
```

---

## Task 2: Add Storage Schemas

**Files:**
- Modify: `src/api/schemas.py`

**Step 1: Add storage backend schemas**

Add after the `ApiErrorResponse` class at the end of the file:

```python
# ============== Storage Backend Schemas ==============


class NfsConfig(BaseModel):
    """NFS backend configuration."""
    server: str
    export_path: str
    mount_options: str | None = "vers=4.1"

    @field_validator("server")
    @classmethod
    def validate_server(cls, v: str) -> str:
        if not v or len(v) > 255:
            raise ValueError("Server must be 1-255 characters")
        return v

    @field_validator("export_path")
    @classmethod
    def validate_export_path(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("Export path must start with /")
        return v


class HttpConfig(BaseModel):
    """HTTP backend configuration."""
    base_url: str
    auth_method: str = "none"  # none, basic, bearer
    username: str | None = None
    password: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Base URL must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("auth_method")
    @classmethod
    def validate_auth_method(cls, v: str) -> str:
        valid = {"none", "basic", "bearer"}
        if v not in valid:
            raise ValueError(f"Auth method must be one of {valid}")
        return v


class S3Config(BaseModel):
    """S3 backend configuration (stub)."""
    endpoint: str
    bucket: str
    region: str | None = None
    access_key_id: str
    secret_access_key: str | None = None
    cdn_enabled: bool = False
    cdn_url: str | None = None


class IscsiTargetConfig(BaseModel):
    """iSCSI target configuration (stub)."""
    target: str
    port: int = 3260
    chap_enabled: bool = False


class StorageBackendCreate(BaseModel):
    """Schema for creating a storage backend."""
    name: str
    type: str
    config: dict

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v) > 100:
            raise ValueError("Name must be 1-100 characters")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {"nfs", "iscsi", "s3", "http"}
        if v not in valid:
            raise ValueError(f"Type must be one of {valid}")
        return v


class StorageBackendUpdate(BaseModel):
    """Schema for updating a storage backend."""
    name: str | None = None
    config: dict | None = None


class StorageBackendStats(BaseModel):
    """Storage backend statistics."""
    used_bytes: int
    total_bytes: int | None
    file_count: int
    template_count: int = 0


class StorageBackendResponse(BaseModel):
    """Schema for storage backend response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    status: str
    config: dict
    stats: StorageBackendStats
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_backend(cls, backend) -> "StorageBackendResponse":
        """Create response from StorageBackend model."""
        import json
        config = json.loads(backend.config_json)
        # Remove sensitive fields from config
        config.pop("password", None)
        config.pop("secret_access_key", None)

        return cls(
            id=backend.id,
            name=backend.name,
            type=backend.type,
            status=backend.status,
            config=config,
            stats=StorageBackendStats(
                used_bytes=backend.used_bytes,
                total_bytes=backend.total_bytes,
                file_count=backend.file_count,
            ),
            created_at=backend.created_at,
            updated_at=backend.updated_at,
        )


class StorageTestResult(BaseModel):
    """Result of storage backend connection test."""
    success: bool
    message: str
```

**Step 2: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat(api): add storage backend schemas"
```

---

## Task 3: Create Storage Service Layer

**Files:**
- Create: `src/core/storage.py`

**Step 1: Create storage service**

```python
"""Storage backend service layer."""
import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

import aiohttp

logger = logging.getLogger(__name__)


class StorageBackendService(Protocol):
    """Protocol for storage backend operations."""

    async def test_connection(self) -> tuple[bool, str]:
        """Test connection to the backend. Returns (success, message)."""
        ...

    async def get_stats(self) -> dict:
        """Get storage statistics."""
        ...

    async def mount(self) -> str | None:
        """Mount the backend (if applicable). Returns mount point."""
        ...

    async def unmount(self) -> None:
        """Unmount the backend (if applicable)."""
        ...


class NfsBackendService:
    """NFS backend operations."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.server = config["server"]
        self.export_path = config["export_path"]
        self.mount_options = config.get("mount_options", "vers=4.1")
        self._mount_base = Path("/tmp/pureboot/nfs")

    @property
    def mount_point(self) -> Path:
        return self._mount_base / self.backend_id

    async def test_connection(self) -> tuple[bool, str]:
        """Test NFS connectivity using showmount."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "showmount", "-e", self.server,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return False, f"Cannot reach NFS server: {stderr.decode().strip()}"

            exports = stdout.decode()
            if self.export_path not in exports:
                return False, f"Export {self.export_path} not found on {self.server}"

            return True, f"NFS server reachable, export {self.export_path} available"
        except FileNotFoundError:
            return False, "showmount command not found (nfs-common not installed)"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    async def mount(self) -> str | None:
        """Mount the NFS share."""
        self.mount_point.mkdir(parents=True, exist_ok=True)

        # Check if already mounted
        if os.path.ismount(str(self.mount_point)):
            return str(self.mount_point)

        source = f"{self.server}:{self.export_path}"
        cmd = ["mount", "-t", "nfs"]
        if self.mount_options:
            cmd.extend(["-o", self.mount_options])
        cmd.extend([source, str(self.mount_point)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"NFS mount failed: {stderr.decode()}")
                return None

            return str(self.mount_point)
        except Exception as e:
            logger.error(f"NFS mount error: {e}")
            return None

    async def unmount(self) -> None:
        """Unmount the NFS share."""
        if os.path.ismount(str(self.mount_point)):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "umount", str(self.mount_point),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            except Exception as e:
                logger.error(f"NFS unmount error: {e}")

    async def get_stats(self) -> dict:
        """Get NFS storage statistics."""
        if not os.path.ismount(str(self.mount_point)):
            mount_result = await self.mount()
            if not mount_result:
                return {"used_bytes": 0, "total_bytes": None, "file_count": 0}

        try:
            stat = shutil.disk_usage(str(self.mount_point))

            # Count files
            file_count = sum(1 for _ in self.mount_point.rglob("*") if _.is_file())

            return {
                "used_bytes": stat.used,
                "total_bytes": stat.total,
                "file_count": file_count,
            }
        except Exception as e:
            logger.error(f"Failed to get NFS stats: {e}")
            return {"used_bytes": 0, "total_bytes": None, "file_count": 0}


class HttpBackendService:
    """HTTP backend operations."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.base_url = config["base_url"]
        self.auth_method = config.get("auth_method", "none")
        self.username = config.get("username")
        self.password = config.get("password")

    def _get_auth(self) -> aiohttp.BasicAuth | None:
        """Get auth for requests."""
        if self.auth_method == "basic" and self.username:
            return aiohttp.BasicAuth(self.username, self.password or "")
        return None

    def _get_headers(self) -> dict:
        """Get headers for requests."""
        headers = {}
        if self.auth_method == "bearer" and self.password:
            headers["Authorization"] = f"Bearer {self.password}"
        return headers

    async def test_connection(self) -> tuple[bool, str]:
        """Test HTTP connectivity."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    self.base_url,
                    auth=self._get_auth(),
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status < 400:
                        return True, f"HTTP endpoint reachable (status {resp.status})"
                    return False, f"HTTP endpoint returned status {resp.status}"
        except aiohttp.ClientError as e:
            return False, f"HTTP connection failed: {str(e)}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    async def mount(self) -> str | None:
        """HTTP backends don't need mounting."""
        return None

    async def unmount(self) -> None:
        """HTTP backends don't need unmounting."""
        pass

    async def get_stats(self) -> dict:
        """Get HTTP storage statistics (limited info available)."""
        # HTTP backends can't easily report disk usage
        # We'd need to crawl the directory listing
        return {"used_bytes": 0, "total_bytes": None, "file_count": 0}


class S3BackendService:
    """S3 backend operations (stub)."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.config = config

    async def test_connection(self) -> tuple[bool, str]:
        return False, "S3 backend not yet implemented"

    async def mount(self) -> str | None:
        return None

    async def unmount(self) -> None:
        pass

    async def get_stats(self) -> dict:
        return {"used_bytes": 0, "total_bytes": None, "file_count": 0}


class IscsiBackendService:
    """iSCSI backend operations (stub)."""

    def __init__(self, backend_id: str, config: dict):
        self.backend_id = backend_id
        self.config = config

    async def test_connection(self) -> tuple[bool, str]:
        return False, "iSCSI backend not yet implemented"

    async def mount(self) -> str | None:
        return None

    async def unmount(self) -> None:
        pass

    async def get_stats(self) -> dict:
        return {"used_bytes": 0, "total_bytes": None, "file_count": 0}


def get_backend_service(backend_id: str, backend_type: str, config: dict):
    """Factory to get the appropriate backend service."""
    services = {
        "nfs": NfsBackendService,
        "http": HttpBackendService,
        "s3": S3BackendService,
        "iscsi": IscsiBackendService,
    }
    service_class = services.get(backend_type)
    if not service_class:
        raise ValueError(f"Unknown backend type: {backend_type}")
    return service_class(backend_id, config)
```

**Step 2: Commit**

```bash
git add src/core/storage.py
git commit -m "feat(core): add storage backend service layer"
```

---

## Task 4: Create Storage Routes

**Files:**
- Create: `src/api/routes/storage.py`

**Step 1: Create storage router**

```python
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
```

**Step 2: Commit**

```bash
git add src/api/routes/storage.py
git commit -m "feat(api): add storage backend routes"
```

---

## Task 5: Register Storage Router

**Files:**
- Modify: `src/main.py`
- Modify: `src/api/routes/__init__.py`

**Step 1: Update routes __init__.py**

Add to `src/api/routes/__init__.py`:

```python
from src.api.routes import boot, ipxe, nodes, groups, storage
```

**Step 2: Update main.py**

Add import at top:

```python
from src.api.routes import boot, ipxe, nodes, groups, storage
```

Add router registration after groups router:

```python
app.include_router(storage.router, prefix="/api/v1", tags=["storage"])
```

**Step 3: Commit**

```bash
git add src/api/routes/__init__.py src/main.py
git commit -m "feat(api): register storage router"
```

---

## Task 6: Add aiohttp Dependency

**Files:**
- Modify: `requirements.txt`

**Step 1: Add aiohttp**

Add to requirements.txt:

```
aiohttp>=3.9.0
```

**Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: add aiohttp dependency for HTTP backend"
```

---

## Task 7: Close GitHub Issue #14

**Step 1: Push branch**

```bash
git push -u origin feature/storage-backend
```

**Step 2: Create PR**

Create PR referencing issue #14.

---

## Summary

**Files created:**
- `src/core/storage.py` - Backend service layer with NFS and HTTP implementations

**Files modified:**
- `src/db/models.py` - Added StorageBackend model
- `src/api/schemas.py` - Added storage schemas
- `src/api/routes/storage.py` - Added storage endpoints
- `src/api/routes/__init__.py` - Exported storage router
- `src/main.py` - Registered storage router
- `requirements.txt` - Added aiohttp

**Endpoints implemented:**
- `GET /api/v1/storage/backends` - List backends
- `POST /api/v1/storage/backends` - Create backend
- `GET /api/v1/storage/backends/{id}` - Get backend
- `PATCH /api/v1/storage/backends/{id}` - Update backend
- `DELETE /api/v1/storage/backends/{id}` - Delete backend
- `POST /api/v1/storage/backends/{id}/test` - Test connection

**Backend types:**
- NFS - Fully implemented (mount, stats, test)
- HTTP - Fully implemented (test connection)
- S3 - Stubbed (returns "not implemented")
- iSCSI - Stubbed (returns "not implemented")