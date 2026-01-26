# Phase 1: Core Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish the foundational infrastructure for disk cloning and partition management - CA service, database models, basic API endpoints, and WebSocket events.

**Architecture:** Controller generates a root CA at startup for issuing session certificates. New database models track clone sessions, disk info, and partition operations. API endpoints provide CRUD for clone sessions with certificate issuance. WebSocket broadcasts clone status events.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy (async), cryptography library, Pydantic v2

**Design Document:** [2026-01-23-disk-cloning-partition-management-design.md](./2026-01-23-disk-cloning-partition-management-design.md)

---

## Task 1: Add CA Settings to Configuration

**Files:**
- Modify: `src/config/settings.py`

**Step 1: Add CA settings class**

Add after `RegistrationSettings` class:

```python
class CASettings(BaseSettings):
    """Certificate Authority settings for clone session TLS."""
    enabled: bool = True
    cert_dir: Path = Path("/opt/pureboot/certs")
    ca_validity_years: int = 10
    session_cert_validity_hours: int = 24
    key_algorithm: str = "ECDSA"  # ECDSA or RSA
    key_size: int = 256  # 256 for ECDSA (P-256), 2048/4096 for RSA
```

**Step 2: Add CA settings to main Settings class**

Add to `Settings` class fields:

```python
    ca: CASettings = Field(default_factory=CASettings)
```

**Step 3: Commit**

```bash
git add src/config/settings.py
git commit -m "feat: add CA settings for clone session TLS"
```

---

## Task 2: Create CA Service

**Files:**
- Create: `src/core/ca.py`

**Step 1: Create the CA service file**

```python
"""Certificate Authority service for clone session TLS."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from src.config import settings


class CAService:
    """Manages the Certificate Authority for clone session certificates."""

    def __init__(self):
        self.cert_dir = settings.ca.cert_dir
        self.ca_cert_path = self.cert_dir / "ca.crt"
        self.ca_key_path = self.cert_dir / "ca.key"
        self._ca_cert = None
        self._ca_key = None

    def initialize(self) -> None:
        """Initialize CA, generating root cert if needed."""
        if not settings.ca.enabled:
            return

        self.cert_dir.mkdir(parents=True, exist_ok=True)

        if self.ca_cert_path.exists() and self.ca_key_path.exists():
            self._load_ca()
        else:
            self._generate_ca()

    def _generate_ca(self) -> None:
        """Generate new CA certificate and key."""
        # Generate private key
        private_key = ec.generate_private_key(ec.SECP256R1())

        # Build certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PureBoot"),
            x509.NameAttribute(NameOID.COMMON_NAME, "PureBoot CA"),
        ])

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=365 * settings.ca.ca_validity_years))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Save key with restricted permissions
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.ca_key_path.write_bytes(key_pem)
        os.chmod(self.ca_key_path, 0o600)

        # Save certificate
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        self.ca_cert_path.write_bytes(cert_pem)

        self._ca_key = private_key
        self._ca_cert = cert

    def _load_ca(self) -> None:
        """Load existing CA certificate and key."""
        key_pem = self.ca_key_path.read_bytes()
        self._ca_key = serialization.load_pem_private_key(key_pem, password=None)

        cert_pem = self.ca_cert_path.read_bytes()
        self._ca_cert = x509.load_pem_x509_certificate(cert_pem)

    def issue_session_cert(
        self,
        session_id: str,
        role: str,  # "source" or "target"
        san_ip: str | None = None,
    ) -> tuple[str, str]:
        """
        Issue a certificate for a clone session participant.

        Returns:
            Tuple of (cert_pem, key_pem) as strings
        """
        if not self._ca_cert or not self._ca_key:
            raise RuntimeError("CA not initialized")

        # Generate key for this cert
        private_key = ec.generate_private_key(ec.SECP256R1())

        # Build subject
        cn = f"clone-{session_id}-{role}"
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PureBoot"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ])

        now = datetime.now(timezone.utc)
        validity_hours = settings.ca.session_cert_validity_hours

        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self._ca_cert.subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(hours=validity_hours))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
        )

        # Add key usage for TLS
        if role == "source":
            # Source acts as server
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
        else:
            # Target acts as client
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )

        # Add SAN if IP provided
        if san_ip:
            from ipaddress import ip_address
            builder = builder.add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(cn),
                    x509.IPAddress(ip_address(san_ip)),
                ]),
                critical=False,
            )
        else:
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.DNSName(cn)]),
                critical=False,
            )

        cert = builder.sign(self._ca_key, hashes.SHA256())

        # Serialize
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        return cert_pem, key_pem

    def get_ca_cert_pem(self) -> str:
        """Get CA certificate as PEM string."""
        if not self._ca_cert:
            raise RuntimeError("CA not initialized")
        return self._ca_cert.public_bytes(serialization.Encoding.PEM).decode()

    @property
    def is_initialized(self) -> bool:
        """Check if CA is initialized."""
        return self._ca_cert is not None and self._ca_key is not None


# Singleton instance
ca_service = CAService()
```

**Step 2: Commit**

```bash
git add src/core/ca.py
git commit -m "feat: implement CA service for clone session certificates"
```

---

## Task 3: Add Database Models for Clone Sessions

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add CloneSession model**

Add at the end of the file:

```python
class CloneSession(Base):
    """Clone session for disk cloning between nodes."""

    __tablename__ = "clone_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # pending, source_ready, cloning, completed, failed, cancelled

    clone_mode: Mapped[str] = mapped_column(
        String(10), default="staged", nullable=False
    )  # staged, direct

    # Source and target nodes
    source_node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id"), nullable=False
    )
    source_node: Mapped["Node"] = relationship(foreign_keys=[source_node_id])
    target_node_id: Mapped[str | None] = mapped_column(
        ForeignKey("nodes.id"), nullable=True
    )
    target_node: Mapped["Node | None"] = relationship(foreign_keys=[target_node_id])

    source_device: Mapped[str] = mapped_column(String(50), default="/dev/sda")
    target_device: Mapped[str] = mapped_column(String(50), default="/dev/sda")

    # Direct mode fields
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    source_port: Mapped[int] = mapped_column(default=9999)
    source_cert_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_key_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_cert_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_key_pem: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Staged mode fields
    staging_backend_id: Mapped[str | None] = mapped_column(
        ForeignKey("storage_backends.id"), nullable=True
    )
    staging_backend: Mapped["StorageBackend | None"] = relationship()
    staging_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    staging_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    staging_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # pending, provisioned, uploading, ready, downloading, cleanup, deleted

    # Resize fields
    resize_mode: Mapped[str] = mapped_column(String(20), default="none")
    # none, shrink_source, grow_target
    partition_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Progress tracking
    bytes_total: Mapped[int | None] = mapped_column(nullable=True)
    bytes_transferred: Mapped[int] = mapped_column(default=0)
    transfer_rate_bps: Mapped[int | None] = mapped_column(nullable=True)

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

**Step 2: Add DiskInfo model**

Add after CloneSession:

```python
class DiskInfo(Base):
    """Cached disk and partition information from nodes."""

    __tablename__ = "disk_info"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node: Mapped["Node"] = relationship()

    device: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    partition_table: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # gpt, mbr, unknown
    partitions_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    scanned_at: Mapped[datetime] = mapped_column(default=func.now())

    __table_args__ = (UniqueConstraint("node_id", "device", name="uq_node_device"),)
```

**Step 3: Add PartitionOperation model**

Add after DiskInfo:

```python
class PartitionOperation(Base):
    """Queued partition operation for a node."""

    __tablename__ = "partition_operations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node: Mapped["Node"] = relationship()

    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("clone_sessions.id", ondelete="SET NULL"), nullable=True
    )
    session: Mapped["CloneSession | None"] = relationship()

    device: Mapped[str] = mapped_column(String(50), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    # resize, create, delete, format, move, set_flag
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending, running, completed, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    executed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

**Step 4: Commit**

```bash
git add src/db/models.py
git commit -m "feat: add database models for clone sessions, disk info, partition operations"
```

---

## Task 4: Add Pydantic Schemas for Clone Sessions

**Files:**
- Modify: `src/api/schemas.py`

**Step 1: Add clone session schemas**

Add at the end of the file:

```python
# ============== Clone Session Schemas ==============


class CloneSessionCreate(BaseModel):
    """Schema for creating a clone session."""

    name: str | None = Field(None, max_length=255, description="Optional session name")
    source_node_id: str = Field(..., description="Source node ID")
    target_node_id: str | None = Field(None, description="Target node ID (can be set later)")
    source_device: str = Field("/dev/sda", description="Source disk device")
    target_device: str = Field("/dev/sda", description="Target disk device")
    clone_mode: Literal["staged", "direct"] = Field("staged", description="Clone mode")
    staging_backend_id: str | None = Field(
        None, description="Storage backend for staged mode"
    )
    resize_mode: Literal["none", "shrink_source", "grow_target"] = Field(
        "none", description="Partition resize strategy"
    )

    @model_validator(mode="after")
    def validate_staged_requires_backend(self) -> "CloneSessionCreate":
        if self.clone_mode == "staged" and not self.staging_backend_id:
            raise ValueError("staging_backend_id required for staged mode")
        if self.clone_mode == "direct" and not self.target_node_id:
            raise ValueError("target_node_id required for direct mode")
        return self


class CloneSessionUpdate(BaseModel):
    """Schema for updating a clone session."""

    name: str | None = None
    target_node_id: str | None = None
    target_device: str | None = None
    resize_mode: Literal["none", "shrink_source", "grow_target"] | None = None


class CloneSessionResponse(BaseModel):
    """Response schema for clone session."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str | None
    status: str
    clone_mode: str
    source_node_id: str
    source_node_name: str | None = None
    target_node_id: str | None
    target_node_name: str | None = None
    source_device: str
    target_device: str
    source_ip: str | None
    source_port: int
    staging_backend_id: str | None
    staging_backend_name: str | None = None
    staging_path: str | None
    staging_status: str | None
    resize_mode: str
    bytes_total: int | None
    bytes_transferred: int
    transfer_rate_bps: int | None
    progress_percent: float = 0.0
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    created_by: str | None

    @classmethod
    def from_session(cls, session) -> "CloneSessionResponse":
        """Create response from CloneSession model."""
        progress = 0.0
        if session.bytes_total and session.bytes_total > 0:
            progress = (session.bytes_transferred / session.bytes_total) * 100

        return cls(
            id=session.id,
            name=session.name,
            status=session.status,
            clone_mode=session.clone_mode,
            source_node_id=session.source_node_id,
            source_node_name=session.source_node.hostname if session.source_node else None,
            target_node_id=session.target_node_id,
            target_node_name=session.target_node.hostname if session.target_node else None,
            source_device=session.source_device,
            target_device=session.target_device,
            source_ip=session.source_ip,
            source_port=session.source_port,
            staging_backend_id=session.staging_backend_id,
            staging_backend_name=session.staging_backend.name if session.staging_backend else None,
            staging_path=session.staging_path,
            staging_status=session.staging_status,
            resize_mode=session.resize_mode,
            bytes_total=session.bytes_total,
            bytes_transferred=session.bytes_transferred,
            transfer_rate_bps=session.transfer_rate_bps,
            progress_percent=round(progress, 1),
            error_message=session.error_message,
            created_at=session.created_at,
            started_at=session.started_at,
            completed_at=session.completed_at,
            created_by=session.created_by,
        )


class CloneProgressUpdate(BaseModel):
    """Progress update from clone source or target."""

    role: Literal["source", "target"]
    bytes_transferred: int = Field(..., ge=0)
    transfer_rate_bps: int | None = Field(None, ge=0)
    status: Literal["transferring", "verifying", "resizing"] | None = None


class CloneSourceReady(BaseModel):
    """Notification that clone source is ready."""

    ip: str
    port: int = 9999
    size_bytes: int
    device: str


class CloneCertBundle(BaseModel):
    """Certificate bundle for clone session participant."""

    cert_pem: str
    key_pem: str
    ca_pem: str
```

**Step 2: Add disk and partition schemas**

Add after clone schemas:

```python
# ============== Disk and Partition Schemas ==============


class PartitionInfo(BaseModel):
    """Information about a single partition."""

    number: int
    start_bytes: int
    end_bytes: int
    size_bytes: int
    size_human: str = ""
    type: str  # efi, linux, swap, ntfs, etc.
    filesystem: str | None = None
    label: str | None = None
    flags: list[str] = []
    used_bytes: int | None = None
    used_percent: float | None = None
    can_shrink: bool = False
    min_size_bytes: int | None = None


class DiskInfoResponse(BaseModel):
    """Response schema for disk information."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    node_id: str
    device: str
    size_bytes: int
    size_human: str = ""
    model: str | None
    serial: str | None
    partition_table: str | None
    partitions: list[PartitionInfo] = []
    scanned_at: datetime

    @classmethod
    def from_disk_info(cls, disk_info) -> "DiskInfoResponse":
        """Create response from DiskInfo model."""
        partitions = []
        if disk_info.partitions_json:
            import json
            try:
                partitions = [PartitionInfo(**p) for p in json.loads(disk_info.partitions_json)]
            except (json.JSONDecodeError, TypeError):
                pass

        # Human readable size
        size_gb = disk_info.size_bytes / (1024 ** 3)
        if size_gb >= 1000:
            size_human = f"{size_gb / 1024:.1f} TB"
        else:
            size_human = f"{size_gb:.1f} GB"

        return cls(
            id=disk_info.id,
            node_id=disk_info.node_id,
            device=disk_info.device,
            size_bytes=disk_info.size_bytes,
            size_human=size_human,
            model=disk_info.model,
            serial=disk_info.serial,
            partition_table=disk_info.partition_table,
            partitions=partitions,
            scanned_at=disk_info.scanned_at,
        )


class PartitionOperationCreate(BaseModel):
    """Schema for creating a partition operation."""

    operation: Literal["resize", "create", "delete", "format", "move", "set_flag"]
    params: dict = Field(..., description="Operation-specific parameters")

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: dict, info) -> dict:
        """Validate params based on operation type."""
        # Basic validation - more specific validation happens in the service
        if not v:
            raise ValueError("params cannot be empty")
        return v


class PartitionOperationResponse(BaseModel):
    """Response schema for partition operation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    node_id: str
    session_id: str | None
    device: str
    operation: str
    params: dict
    sequence: int
    status: str
    error_message: str | None
    created_at: datetime
    executed_at: datetime | None

    @classmethod
    def from_operation(cls, op) -> "PartitionOperationResponse":
        """Create response from PartitionOperation model."""
        import json
        params = {}
        try:
            params = json.loads(op.params_json)
        except (json.JSONDecodeError, TypeError):
            pass

        return cls(
            id=op.id,
            node_id=op.node_id,
            session_id=op.session_id,
            device=op.device,
            operation=op.operation,
            params=params,
            sequence=op.sequence,
            status=op.status,
            error_message=op.error_message,
            created_at=op.created_at,
            executed_at=op.executed_at,
        )
```

**Step 3: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat: add Pydantic schemas for clone sessions and disk operations"
```

---

## Task 5: Create Clone Sessions API Router

**Files:**
- Create: `src/api/routes/clone.py`

**Step 1: Create the clone routes file**

```python
"""Clone session API routes."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    CloneCertBundle,
    CloneProgressUpdate,
    CloneSessionCreate,
    CloneSessionResponse,
    CloneSessionUpdate,
    CloneSourceReady,
)
from src.core.ca import ca_service
from src.core.websocket import global_ws_manager
from src.db.database import get_db
from src.db.models import CloneSession, Node, StorageBackend

router = APIRouter(tags=["Clone Sessions"])


@router.post("/clone-sessions", response_model=ApiResponse[CloneSessionResponse])
async def create_clone_session(
    request: CloneSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new clone session."""
    # Verify source node exists
    result = await db.execute(select(Node).where(Node.id == request.source_node_id))
    source_node = result.scalar_one_or_none()
    if not source_node:
        raise HTTPException(status_code=404, detail="Source node not found")

    # Verify target node if provided
    if request.target_node_id:
        result = await db.execute(select(Node).where(Node.id == request.target_node_id))
        target_node = result.scalar_one_or_none()
        if not target_node:
            raise HTTPException(status_code=404, detail="Target node not found")

    # Verify storage backend for staged mode
    if request.clone_mode == "staged" and request.staging_backend_id:
        result = await db.execute(
            select(StorageBackend).where(StorageBackend.id == request.staging_backend_id)
        )
        backend = result.scalar_one_or_none()
        if not backend:
            raise HTTPException(status_code=404, detail="Storage backend not found")

    # Create session
    session = CloneSession(
        name=request.name,
        clone_mode=request.clone_mode,
        source_node_id=request.source_node_id,
        target_node_id=request.target_node_id,
        source_device=request.source_device,
        target_device=request.target_device,
        staging_backend_id=request.staging_backend_id,
        resize_mode=request.resize_mode,
    )

    # Generate certificates for direct mode
    if request.clone_mode == "direct" and ca_service.is_initialized:
        source_cert, source_key = ca_service.issue_session_cert(session.id, "source")
        target_cert, target_key = ca_service.issue_session_cert(session.id, "target")
        session.source_cert_pem = source_cert
        session.source_key_pem = source_key
        session.target_cert_pem = target_cert
        session.target_key_pem = target_key

    db.add(session)
    await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
            selectinload(CloneSession.staging_backend),
        )
        .where(CloneSession.id == session.id)
    )
    session = result.scalar_one()

    return ApiResponse(
        data=CloneSessionResponse.from_session(session),
        message="Clone session created",
    )


@router.get("/clone-sessions", response_model=ApiListResponse[CloneSessionResponse])
async def list_clone_sessions(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List clone sessions."""
    query = select(CloneSession).options(
        selectinload(CloneSession.source_node),
        selectinload(CloneSession.target_node),
        selectinload(CloneSession.staging_backend),
    )

    if status:
        query = query.where(CloneSession.status == status)

    query = query.order_by(CloneSession.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    sessions = result.scalars().all()

    # Get total count
    count_query = select(CloneSession)
    if status:
        count_query = count_query.where(CloneSession.status == status)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    return ApiListResponse(
        data=[CloneSessionResponse.from_session(s) for s in sessions],
        total=total,
    )


@router.get("/clone-sessions/{session_id}", response_model=ApiResponse[CloneSessionResponse])
async def get_clone_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a clone session by ID."""
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
            selectinload(CloneSession.staging_backend),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    return ApiResponse(data=CloneSessionResponse.from_session(session))


@router.patch("/clone-sessions/{session_id}", response_model=ApiResponse[CloneSessionResponse])
async def update_clone_session(
    session_id: str,
    request: CloneSessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a clone session."""
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
            selectinload(CloneSession.staging_backend),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.status not in ("pending",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update session in {session.status} status",
        )

    # Update fields
    if request.name is not None:
        session.name = request.name
    if request.target_node_id is not None:
        # Verify target node
        result = await db.execute(select(Node).where(Node.id == request.target_node_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Target node not found")
        session.target_node_id = request.target_node_id
    if request.target_device is not None:
        session.target_device = request.target_device
    if request.resize_mode is not None:
        session.resize_mode = request.resize_mode

    await db.flush()

    # Reload
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
            selectinload(CloneSession.staging_backend),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one()

    return ApiResponse(
        data=CloneSessionResponse.from_session(session),
        message="Clone session updated",
    )


@router.delete("/clone-sessions/{session_id}", response_model=ApiResponse[dict])
async def delete_clone_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete or cancel a clone session."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.status in ("cloning",):
        # Mark as cancelled instead of deleting
        session.status = "cancelled"
        session.completed_at = datetime.now(timezone.utc)
        await db.flush()

        # Broadcast cancellation
        await global_ws_manager.broadcast(
            "clone.cancelled",
            {"session_id": session_id},
        )

        return ApiResponse(data={"id": session_id}, message="Clone session cancelled")

    # Delete if pending or completed
    await db.delete(session)
    await db.flush()

    return ApiResponse(data={"id": session_id}, message="Clone session deleted")


@router.get("/clone-sessions/{session_id}/certs", response_model=ApiResponse[CloneCertBundle])
async def get_clone_certs(
    session_id: str,
    role: str = Query(..., description="Role: source or target"),
    db: AsyncSession = Depends(get_db),
):
    """Get TLS certificates for a clone session participant."""
    if role not in ("source", "target"):
        raise HTTPException(status_code=400, detail="Role must be 'source' or 'target'")

    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.clone_mode != "direct":
        raise HTTPException(
            status_code=400,
            detail="Certificates only available for direct mode sessions",
        )

    if not ca_service.is_initialized:
        raise HTTPException(status_code=503, detail="CA service not initialized")

    if role == "source":
        cert_pem = session.source_cert_pem
        key_pem = session.source_key_pem
    else:
        cert_pem = session.target_cert_pem
        key_pem = session.target_key_pem

    if not cert_pem or not key_pem:
        raise HTTPException(status_code=404, detail=f"Certificates not found for {role}")

    return ApiResponse(
        data=CloneCertBundle(
            cert_pem=cert_pem,
            key_pem=key_pem,
            ca_pem=ca_service.get_ca_cert_pem(),
        )
    )


@router.post("/clone-sessions/{session_id}/source-ready", response_model=ApiResponse[dict])
async def clone_source_ready(
    session_id: str,
    request: CloneSourceReady,
    db: AsyncSession = Depends(get_db),
):
    """Called by source node when ready to serve disk."""
    result = await db.execute(
        select(CloneSession)
        .options(
            selectinload(CloneSession.source_node),
            selectinload(CloneSession.target_node),
        )
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    # Update session
    session.status = "source_ready"
    session.source_ip = request.ip
    session.source_port = request.port
    session.bytes_total = request.size_bytes
    session.started_at = datetime.now(timezone.utc)

    await db.flush()

    # Broadcast event
    await global_ws_manager.broadcast(
        "clone.source_ready",
        {
            "session_id": session_id,
            "source_ip": request.ip,
            "source_port": request.port,
            "size_bytes": request.size_bytes,
        },
    )

    return ApiResponse(
        data={"status": "source_ready"},
        message=f"Source ready at {request.ip}:{request.port}",
    )


@router.post("/clone-sessions/{session_id}/progress", response_model=ApiResponse[dict])
async def clone_progress(
    session_id: str,
    request: CloneProgressUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Progress update from source or target."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    # Update progress
    session.bytes_transferred = request.bytes_transferred
    if request.transfer_rate_bps is not None:
        session.transfer_rate_bps = request.transfer_rate_bps

    if session.status == "source_ready":
        session.status = "cloning"

    await db.flush()

    # Calculate progress
    progress_percent = 0.0
    if session.bytes_total and session.bytes_total > 0:
        progress_percent = (session.bytes_transferred / session.bytes_total) * 100

    # Broadcast progress
    await global_ws_manager.broadcast(
        "clone.progress",
        {
            "session_id": session_id,
            "bytes_transferred": session.bytes_transferred,
            "bytes_total": session.bytes_total,
            "progress_percent": round(progress_percent, 1),
            "transfer_rate_bps": session.transfer_rate_bps,
            "status": request.status,
        },
    )

    return ApiResponse(data={"progress_percent": round(progress_percent, 1)})


@router.post("/clone-sessions/{session_id}/complete", response_model=ApiResponse[dict])
async def clone_complete(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark clone session as complete."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    if session.bytes_total:
        session.bytes_transferred = session.bytes_total

    await db.flush()

    # Calculate duration
    duration_seconds = 0
    if session.started_at:
        duration = session.completed_at - session.started_at
        duration_seconds = int(duration.total_seconds())

    # Broadcast completion
    await global_ws_manager.broadcast(
        "clone.completed",
        {
            "session_id": session_id,
            "duration_seconds": duration_seconds,
        },
    )

    return ApiResponse(
        data={"status": "completed", "duration_seconds": duration_seconds},
        message="Clone completed successfully",
    )


@router.post("/clone-sessions/{session_id}/failed", response_model=ApiResponse[dict])
async def clone_failed(
    session_id: str,
    error: str = Query(..., description="Error message"),
    db: AsyncSession = Depends(get_db),
):
    """Mark clone session as failed."""
    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    session.status = "failed"
    session.error_message = error
    session.completed_at = datetime.now(timezone.utc)

    await db.flush()

    # Broadcast failure
    await global_ws_manager.broadcast(
        "clone.failed",
        {
            "session_id": session_id,
            "error": error,
        },
    )

    return ApiResponse(
        data={"status": "failed"},
        message=f"Clone failed: {error}",
    )
```

**Step 2: Commit**

```bash
git add src/api/routes/clone.py
git commit -m "feat: implement clone sessions API router"
```

---

## Task 6: Register Clone Router and Initialize CA

**Files:**
- Modify: `src/main.py`

**Step 1: Add imports**

Add to imports section:

```python
from src.api.routes.clone import router as clone_router
from src.core.ca import ca_service
```

**Step 2: Register the router**

Find where other routers are registered (e.g., `app.include_router(...)`) and add:

```python
app.include_router(clone_router)
```

**Step 3: Initialize CA on startup**

Find the startup event or lifespan handler. Add CA initialization:

```python
# If using @app.on_event("startup"):
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    ca_service.initialize()
```

Or if using lifespan context manager, add within the lifespan function:

```python
ca_service.initialize()
```

**Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat: register clone router and initialize CA service on startup"
```

---

## Task 7: Add Frontend Types for Clone Sessions

**Files:**
- Create: `frontend/src/types/clone.ts`

**Step 1: Create the types file**

```typescript
export type CloneMode = 'staged' | 'direct';
export type CloneStatus = 'pending' | 'source_ready' | 'cloning' | 'completed' | 'failed' | 'cancelled';
export type ResizeMode = 'none' | 'shrink_source' | 'grow_target';
export type StagingStatus = 'pending' | 'provisioned' | 'uploading' | 'ready' | 'downloading' | 'cleanup' | 'deleted';

export interface CloneSession {
  id: string;
  name: string | null;
  status: CloneStatus;
  clone_mode: CloneMode;
  source_node_id: string;
  source_node_name: string | null;
  target_node_id: string | null;
  target_node_name: string | null;
  source_device: string;
  target_device: string;
  source_ip: string | null;
  source_port: number;
  staging_backend_id: string | null;
  staging_backend_name: string | null;
  staging_path: string | null;
  staging_status: StagingStatus | null;
  resize_mode: ResizeMode;
  bytes_total: number | null;
  bytes_transferred: number;
  transfer_rate_bps: number | null;
  progress_percent: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  created_by: string | null;
}

export interface CloneSessionCreate {
  name?: string;
  source_node_id: string;
  target_node_id?: string;
  source_device?: string;
  target_device?: string;
  clone_mode?: CloneMode;
  staging_backend_id?: string;
  resize_mode?: ResizeMode;
}

export interface CloneSessionUpdate {
  name?: string;
  target_node_id?: string;
  target_device?: string;
  resize_mode?: ResizeMode;
}

export const CLONE_STATUS_COLORS: Record<CloneStatus, string> = {
  pending: 'bg-gray-500',
  source_ready: 'bg-blue-500',
  cloning: 'bg-yellow-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  cancelled: 'bg-gray-400',
};

export const CLONE_STATUS_LABELS: Record<CloneStatus, string> = {
  pending: 'Pending',
  source_ready: 'Source Ready',
  cloning: 'Cloning',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
};
```

**Step 2: Commit**

```bash
git add frontend/src/types/clone.ts
git commit -m "feat: add TypeScript types for clone sessions"
```

---

## Task 8: Add Frontend API Client for Clone Sessions

**Files:**
- Create: `frontend/src/api/clone.ts`

**Step 1: Create the API client**

```typescript
import { apiClient } from './client';
import type { ApiResponse, ApiListResponse } from './client';
import type { CloneSession, CloneSessionCreate, CloneSessionUpdate } from '../types/clone';

export const cloneApi = {
  list(params?: { status?: string; limit?: number; offset?: number }): Promise<ApiListResponse<CloneSession>> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.offset) searchParams.set('offset', params.offset.toString());
    const query = searchParams.toString();
    return apiClient.get(`/clone-sessions${query ? `?${query}` : ''}`);
  },

  get(sessionId: string): Promise<ApiResponse<CloneSession>> {
    return apiClient.get(`/clone-sessions/${sessionId}`);
  },

  create(data: CloneSessionCreate): Promise<ApiResponse<CloneSession>> {
    return apiClient.post('/clone-sessions', data);
  },

  update(sessionId: string, data: CloneSessionUpdate): Promise<ApiResponse<CloneSession>> {
    return apiClient.patch(`/clone-sessions/${sessionId}`, data);
  },

  delete(sessionId: string): Promise<ApiResponse<{ id: string }>> {
    return apiClient.delete(`/clone-sessions/${sessionId}`);
  },

  // Callbacks (usually called by nodes, but available for testing)
  sourceReady(sessionId: string, data: { ip: string; port: number; size_bytes: number; device: string }): Promise<ApiResponse<{ status: string }>> {
    return apiClient.post(`/clone-sessions/${sessionId}/source-ready`, data);
  },

  progress(sessionId: string, data: { role: 'source' | 'target'; bytes_transferred: number; transfer_rate_bps?: number }): Promise<ApiResponse<{ progress_percent: number }>> {
    return apiClient.post(`/clone-sessions/${sessionId}/progress`, data);
  },

  complete(sessionId: string): Promise<ApiResponse<{ status: string; duration_seconds: number }>> {
    return apiClient.post(`/clone-sessions/${sessionId}/complete`, {});
  },

  failed(sessionId: string, error: string): Promise<ApiResponse<{ status: string }>> {
    return apiClient.post(`/clone-sessions/${sessionId}/failed?error=${encodeURIComponent(error)}`, {});
  },
};
```

**Step 2: Commit**

```bash
git add frontend/src/api/clone.ts
git commit -m "feat: add frontend API client for clone sessions"
```

---

## Task 9: Add React Query Hooks for Clone Sessions

**Files:**
- Create: `frontend/src/hooks/useCloneSessions.ts`

**Step 1: Create the hooks file**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cloneApi } from '../api/clone';
import type { CloneSessionCreate, CloneSessionUpdate } from '../types/clone';

export const cloneSessionKeys = {
  all: ['clone-sessions'] as const,
  lists: () => [...cloneSessionKeys.all, 'list'] as const,
  list: (filters: { status?: string }) => [...cloneSessionKeys.lists(), filters] as const,
  details: () => [...cloneSessionKeys.all, 'detail'] as const,
  detail: (id: string) => [...cloneSessionKeys.details(), id] as const,
};

export function useCloneSessions(filters?: { status?: string }) {
  return useQuery({
    queryKey: cloneSessionKeys.list(filters ?? {}),
    queryFn: () => cloneApi.list(filters),
  });
}

export function useCloneSession(sessionId: string) {
  return useQuery({
    queryKey: cloneSessionKeys.detail(sessionId),
    queryFn: () => cloneApi.get(sessionId),
    enabled: !!sessionId,
  });
}

export function useCreateCloneSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CloneSessionCreate) => cloneApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() });
    },
  });
}

export function useUpdateCloneSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, data }: { sessionId: string; data: CloneSessionUpdate }) =>
      cloneApi.update(sessionId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.detail(variables.sessionId) });
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() });
    },
  });
}

export function useDeleteCloneSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => cloneApi.delete(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() });
    },
  });
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useCloneSessions.ts
git commit -m "feat: add React Query hooks for clone sessions"
```

---

## Task 10: Add WebSocket Event Handlers for Clone Events

**Files:**
- Modify: `frontend/src/hooks/useWebSocket.ts`

**Step 1: Add clone event types**

Find the `WebSocketEvent` type definition and add clone events:

```typescript
// Add to WebSocketEvent union type:
| { type: 'clone.started'; data: { session_id: string; source_node_id: string; target_node_id: string } }
| { type: 'clone.source_ready'; data: { session_id: string; source_ip: string; source_port: number; size_bytes: number } }
| { type: 'clone.progress'; data: { session_id: string; bytes_transferred: number; bytes_total: number; progress_percent: number; transfer_rate_bps: number | null; status: string | null } }
| { type: 'clone.completed'; data: { session_id: string; duration_seconds: number } }
| { type: 'clone.failed'; data: { session_id: string; error: string } }
| { type: 'clone.cancelled'; data: { session_id: string } }
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useWebSocket.ts
git commit -m "feat: add WebSocket event types for clone sessions"
```

---

## Task 11: Create useCloneUpdates Hook

**Files:**
- Create: `frontend/src/hooks/useCloneUpdates.ts`

**Step 1: Create the hook**

```typescript
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWebSocket } from './useWebSocket';
import { cloneSessionKeys } from './useCloneSessions';
import type { WebSocketEvent } from './useWebSocket';

export function useCloneUpdates() {
  const queryClient = useQueryClient();
  const { lastEvent } = useWebSocket();

  useEffect(() => {
    if (!lastEvent) return;

    const event = lastEvent as WebSocketEvent;

    switch (event.type) {
      case 'clone.started':
      case 'clone.source_ready':
      case 'clone.completed':
      case 'clone.failed':
      case 'clone.cancelled':
        // Invalidate both list and specific session
        queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() });
        queryClient.invalidateQueries({
          queryKey: cloneSessionKeys.detail(event.data.session_id),
        });
        break;

      case 'clone.progress':
        // Update cache directly for smoother progress updates
        queryClient.setQueryData(
          cloneSessionKeys.detail(event.data.session_id),
          (old: any) => {
            if (!old?.data) return old;
            return {
              ...old,
              data: {
                ...old.data,
                bytes_transferred: event.data.bytes_transferred,
                bytes_total: event.data.bytes_total,
                progress_percent: event.data.progress_percent,
                transfer_rate_bps: event.data.transfer_rate_bps,
                status: event.data.status === 'transferring' ? 'cloning' : old.data.status,
              },
            };
          }
        );
        // Also invalidate list to update progress there
        queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() });
        break;
    }
  }, [lastEvent, queryClient]);
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useCloneUpdates.ts
git commit -m "feat: add useCloneUpdates hook for real-time clone progress"
```

---

## Task 12: Final Commit - Phase 1 Complete

**Step 1: Create summary commit**

```bash
git add -A
git status
```

If there are any remaining uncommitted files, commit them:

```bash
git commit -m "chore: phase 1 complete - core infrastructure for disk cloning"
```

**Step 2: Verify all commits**

```bash
git log --oneline -15
```

Expected commits (newest first):
- chore: phase 1 complete - core infrastructure for disk cloning (if needed)
- feat: add useCloneUpdates hook for real-time clone progress
- feat: add WebSocket event types for clone sessions
- feat: add React Query hooks for clone sessions
- feat: add frontend API client for clone sessions
- feat: add TypeScript types for clone sessions
- feat: register clone router and initialize CA service on startup
- feat: implement clone sessions API router
- feat: add Pydantic schemas for clone sessions and disk operations
- feat: add database models for clone sessions, disk info, partition operations
- feat: implement CA service for clone session certificates
- feat: add CA settings for clone session TLS

---

## Summary

Phase 1 establishes:

1. **CA Service** (`src/core/ca.py`) - Generates root CA, issues session certificates
2. **Database Models** - CloneSession, DiskInfo, PartitionOperation
3. **API Schemas** - Pydantic models for request/response validation
4. **API Router** (`src/api/routes/clone.py`) - CRUD endpoints + callbacks
5. **Frontend Types** - TypeScript interfaces
6. **Frontend API Client** - API wrapper functions
7. **React Query Hooks** - Data fetching and caching
8. **WebSocket Integration** - Real-time progress updates

**Next Phase:** Phase 2 - Direct Mode Cloning (deploy environment scripts, boot integration)