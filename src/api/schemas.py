"""Pydantic schemas for API request/response validation."""
import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

if TYPE_CHECKING:
    from src.db.models import NodeStateLog

T = TypeVar("T")

MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def normalize_mac(mac: str) -> str:
    """Normalize MAC address to colon-separated lowercase."""
    return mac.replace("-", ":").lower()


# ============== Node Schemas ==============


class NodeCreate(BaseModel):
    """Schema for creating a new node."""

    mac_address: str
    hostname: str | None = None
    arch: str = "x86_64"
    boot_mode: str = "bios"
    group_id: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    system_uuid: str | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        """Validate and normalize MAC address."""
        if not MAC_PATTERN.match(v):
            raise ValueError(f"Invalid MAC address format: {v}")
        return normalize_mac(v)

    @field_validator("arch")
    @classmethod
    def validate_arch(cls, v: str) -> str:
        """Validate architecture."""
        valid = {"x86_64", "arm64", "aarch64"}
        if v not in valid:
            raise ValueError(f"Invalid architecture: {v}. Must be one of {valid}")
        return v

    @field_validator("boot_mode")
    @classmethod
    def validate_boot_mode(cls, v: str) -> str:
        """Validate boot mode."""
        valid = {"bios", "uefi"}
        if v not in valid:
            raise ValueError(f"Invalid boot mode: {v}. Must be one of {valid}")
        return v


class NodeUpdate(BaseModel):
    """Schema for updating a node."""

    hostname: str | None = None
    workflow_id: str | None = None
    group_id: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    system_uuid: str | None = None


class StateTransition(BaseModel):
    """Request to transition node to new state."""

    state: str
    comment: str | None = None
    force: bool = False  # Bypasses retry limit, resets counters

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Validate state is a known state."""
        from src.core.state_machine import NodeStateMachine

        if v not in NodeStateMachine.STATES:
            raise ValueError(
                f"Invalid state: {v}. Must be one of {NodeStateMachine.STATES}"
            )
        return v


class TagCreate(BaseModel):
    """Schema for adding a tag."""

    tag: str

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        """Validate tag format."""
        if not v or len(v) > 50:
            raise ValueError("Tag must be 1-50 characters")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Tag can only contain letters, numbers, hyphens, underscores")
        return v.lower()


class NodeResponse(BaseModel):
    """Schema for node response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    mac_address: str
    hostname: str | None
    ip_address: str | None
    state: str
    workflow_id: str | None
    vendor: str | None
    model: str | None
    serial_number: str | None
    system_uuid: str | None
    arch: str
    boot_mode: str
    group_id: str | None
    tags: list[str] = []
    install_attempts: int = 0
    last_install_error: str | None = None
    state_changed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None

    @classmethod
    def from_node(cls, node) -> "NodeResponse":
        """Create response from Node model."""
        return cls(
            id=node.id,
            mac_address=node.mac_address,
            hostname=node.hostname,
            ip_address=node.ip_address,
            state=node.state,
            workflow_id=node.workflow_id,
            vendor=node.vendor,
            model=node.model,
            serial_number=node.serial_number,
            system_uuid=node.system_uuid,
            arch=node.arch,
            boot_mode=node.boot_mode,
            group_id=node.group_id,
            tags=[t.tag for t in node.tags],
            install_attempts=node.install_attempts,
            last_install_error=node.last_install_error,
            state_changed_at=node.state_changed_at,
            created_at=node.created_at,
            updated_at=node.updated_at,
            last_seen_at=node.last_seen_at,
        )


class NodeStateLogResponse(BaseModel):
    """Response schema for node state log entry."""

    id: str
    from_state: str
    to_state: str
    triggered_by: str
    user_id: str | None
    comment: str | None
    metadata: dict | None
    created_at: datetime

    @classmethod
    def from_log(cls, log: "NodeStateLog") -> "NodeStateLogResponse":
        metadata = None
        if log.metadata_json:
            try:
                metadata = json.loads(log.metadata_json)
            except json.JSONDecodeError:
                metadata = None

        return cls(
            id=log.id,
            from_state=log.from_state,
            to_state=log.to_state,
            triggered_by=log.triggered_by,
            user_id=log.user_id,
            comment=log.comment,
            metadata=metadata,
            created_at=log.created_at,
        )


class NodeHistoryResponse(BaseModel):
    """Response for node state history."""

    data: list[NodeStateLogResponse]
    total: int


# ============== Device Group Schemas ==============


class DeviceGroupCreate(BaseModel):
    """Schema for creating a device group."""

    name: str
    description: str | None = None
    default_workflow_id: str | None = None
    auto_provision: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate group name."""
        if not v or len(v) > 100:
            raise ValueError("Name must be 1-100 characters")
        return v


class DeviceGroupUpdate(BaseModel):
    """Schema for updating a device group."""

    name: str | None = None
    description: str | None = None
    default_workflow_id: str | None = None
    auto_provision: bool | None = None


class DeviceGroupResponse(BaseModel):
    """Schema for device group response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    default_workflow_id: str | None
    auto_provision: bool
    created_at: datetime
    updated_at: datetime
    node_count: int = 0

    @classmethod
    def from_group(cls, group, node_count: int = 0) -> "DeviceGroupResponse":
        """Create response from DeviceGroup model."""
        return cls(
            id=group.id,
            name=group.name,
            description=group.description,
            default_workflow_id=group.default_workflow_id,
            auto_provision=group.auto_provision,
            created_at=group.created_at,
            updated_at=group.updated_at,
            node_count=node_count,
        )


# ============== Report Schemas ==============


class NodeReport(BaseModel):
    """Node status report from the node itself."""

    mac_address: str

    # Event-based reporting (new)
    event: Literal[
        "boot_started",
        "install_started",
        "install_progress",
        "install_complete",
        "install_failed",
        "first_boot",
        "heartbeat",
    ] | None = None
    status: Literal["success", "failed", "in_progress"] = "success"
    message: str | None = None
    event_metadata: dict | None = None

    # Hardware/network info
    ip_address: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    system_uuid: str | None = None

    # Legacy installation reporting (backwards compatibility)
    installation_status: Literal["started", "progress", "complete", "failed"] | None = None
    installation_progress: int | None = None  # 0-100
    installation_error: str | None = None

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        """Validate and normalize MAC address."""
        if not MAC_PATTERN.match(v):
            raise ValueError(f"Invalid MAC address format: {v}")
        return normalize_mac(v)

    @field_validator("installation_progress")
    @classmethod
    def validate_progress(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("Progress must be between 0 and 100")
        return v


class NodeEventResponse(BaseModel):
    """Response for a single node event."""

    id: str
    node_id: str
    event_type: str
    status: str
    message: str | None
    progress: int | None
    metadata: dict | None
    ip_address: str | None
    created_at: datetime

    @classmethod
    def from_event(cls, event) -> "NodeEventResponse":
        """Create response from NodeEvent model."""
        import json
        metadata = None
        if event.metadata_json:
            try:
                metadata = json.loads(event.metadata_json)
            except json.JSONDecodeError:
                pass
        return cls(
            id=event.id,
            node_id=event.node_id,
            event_type=event.event_type,
            status=event.status,
            message=event.message,
            progress=event.progress,
            metadata=metadata,
            ip_address=event.ip_address,
            created_at=event.created_at,
        )


class NodeEventListResponse(BaseModel):
    """Response for node events list."""

    data: list[NodeEventResponse]
    total: int


# ============== Generic Response Schemas ==============


class ApiResponse(BaseModel, Generic[T]):
    """Generic API response wrapper."""

    success: bool = True
    data: T
    message: str | None = None


class ApiListResponse(BaseModel, Generic[T]):
    """Generic API list response wrapper."""

    success: bool = True
    data: list[T]
    total: int


class ApiErrorResponse(BaseModel):
    """API error response."""

    success: bool = False
    error: str
    detail: str | None = None


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
            raise ValueError(f"Auth method must be one of: {', '.join(sorted(valid))}")
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
            raise ValueError(f"Type must be one of: {', '.join(sorted(valid))}")
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


# ============== File Browser Schemas ==============


class StorageFile(BaseModel):
    """File or directory in storage backend."""

    name: str
    path: str
    type: str  # "file" or "directory"
    size: int | None = None
    mime_type: str | None = None
    modified_at: datetime | None = None
    item_count: int | None = None  # For directories


class FileListResponse(BaseModel):
    """Response for file listing."""

    path: str
    files: list[StorageFile]
    total: int


class FolderCreate(BaseModel):
    """Schema for creating a folder."""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v or not v.startswith("/"):
            raise ValueError("Path must start with /")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v.rstrip("/") or "/"


class FileMove(BaseModel):
    """Schema for moving files."""

    source_path: str
    destination_path: str

    @field_validator("source_path", "destination_path")
    @classmethod
    def validate_paths(cls, v: str) -> str:
        if not v or not v.startswith("/"):
            raise ValueError("Path must start with /")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v


class FileDelete(BaseModel):
    """Schema for deleting files."""

    paths: list[str]

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, v: list[str]) -> list[str]:
        for path in v:
            if not path or not path.startswith("/"):
                raise ValueError(f"Path must start with /: {path}")
            if ".." in path:
                raise ValueError("Path traversal not allowed")
        return v


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

    model_config = ConfigDict(from_attributes=True)

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

    @classmethod
    def from_lun(cls, lun) -> "IscsiLunResponse":
        """Create response from IscsiLun model."""
        return cls(
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


class LunAssign(BaseModel):
    """Schema for assigning a LUN to a node."""

    node_id: str


# ============== Sync Job Schemas ==============


class SyncJobCreate(BaseModel):
    """Schema for creating a sync job."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$",
    )
    source_url: HttpUrl
    destination_backend_id: str
    destination_path: str = Field(..., max_length=500)
    include_pattern: str | None = Field(None, max_length=500)
    exclude_pattern: str | None = Field(None, max_length=500)
    schedule: Literal["manual", "hourly", "daily", "weekly", "monthly"]
    schedule_day: int | None = None
    schedule_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    verify_checksums: bool = True
    delete_removed: bool = False
    keep_versions: int = Field(3, ge=0, le=10)

    @field_validator("destination_path")
    @classmethod
    def validate_destination_path(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("Path cannot contain '..'")
        return v.strip("/")

    @field_validator("schedule_day")
    @classmethod
    def validate_schedule_day(cls, v: int | None, info) -> int | None:
        schedule = info.data.get("schedule")
        if schedule == "weekly" and v is not None and not (0 <= v <= 6):
            raise ValueError("Weekly schedule_day must be 0-6 (Mon-Sun)")
        if schedule == "monthly" and v is not None and not (1 <= v <= 31):
            raise ValueError("Monthly schedule_day must be 1-31")
        return v

    @model_validator(mode="after")
    def validate_schedule_requirements(self) -> "SyncJobCreate":
        if self.schedule in ("daily", "weekly", "monthly") and not self.schedule_time:
            raise ValueError(f"{self.schedule} schedule requires schedule_time")
        if self.schedule == "weekly" and self.schedule_day is None:
            raise ValueError("Weekly schedule requires schedule_day (0-6)")
        if self.schedule == "monthly" and self.schedule_day is None:
            raise ValueError("Monthly schedule requires schedule_day (1-31)")
        return self


class SyncJobUpdate(BaseModel):
    """Schema for updating a sync job."""

    name: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$",
    )
    source_url: HttpUrl | None = None
    destination_path: str | None = Field(None, max_length=500)
    include_pattern: str | None = None
    exclude_pattern: str | None = None
    schedule: Literal["manual", "hourly", "daily", "weekly", "monthly"] | None = None
    schedule_day: int | None = None
    schedule_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    verify_checksums: bool | None = None
    delete_removed: bool | None = None
    keep_versions: int | None = Field(None, ge=0, le=10)

    @field_validator("destination_path")
    @classmethod
    def validate_destination_path(cls, v: str | None) -> str | None:
        if v and ".." in v:
            raise ValueError("Path cannot contain '..'")
        return v.strip("/") if v else v


class SyncJobResponse(BaseModel):
    """Response schema for sync job."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_url: str
    destination_backend_id: str
    destination_backend_name: str
    destination_path: str
    include_pattern: str | None
    exclude_pattern: str | None
    schedule: str
    schedule_day: int | None
    schedule_time: str | None
    verify_checksums: bool
    delete_removed: bool
    keep_versions: int
    status: str
    last_run_at: datetime | None
    last_error: str | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job) -> "SyncJobResponse":
        """Create response from SyncJob model."""
        return cls(
            id=job.id,
            name=job.name,
            source_url=job.source_url,
            destination_backend_id=job.destination_backend_id,
            destination_backend_name=job.destination_backend.name if job.destination_backend else "Unknown",
            destination_path=job.destination_path,
            include_pattern=job.include_pattern,
            exclude_pattern=job.exclude_pattern,
            schedule=job.schedule,
            schedule_day=job.schedule_day,
            schedule_time=job.schedule_time,
            verify_checksums=job.verify_checksums,
            delete_removed=job.delete_removed,
            keep_versions=job.keep_versions,
            status=job.status,
            last_run_at=job.last_run_at,
            last_error=job.last_error,
            next_run_at=job.next_run_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class SyncJobRunResponse(BaseModel):
    """Response schema for sync job run."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    files_synced: int
    bytes_transferred: int
    current_file: str | None
    progress_percent: int
    error: str | None


class SyncProgress(BaseModel):
    """WebSocket message format for sync progress."""

    job_id: str
    run_id: str
    status: str
    current_file: str | None
    files_synced: int
    bytes_transferred: int
    progress_percent: int
    error: str | None


# ============== Workflow Schemas ==============


class WorkflowResponse(BaseModel):
    """Workflow definition for OS installation."""

    id: str
    name: str
    kernel_path: str
    initrd_path: str
    cmdline: str
    architecture: str = "x86_64"
    boot_mode: str = "bios"


class WorkflowListResponse(BaseModel):
    """Response for workflow listing."""

    data: list[WorkflowResponse]
    total: int
