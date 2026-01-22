"""SQLAlchemy database models."""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class DeviceGroup(Base):
    """Device group for organizing nodes with shared settings."""

    __tablename__ = "device_groups"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    # Default settings for nodes in this group
    default_workflow_id: Mapped[str | None] = mapped_column(String(36))
    auto_provision: Mapped[bool] = mapped_column(default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    nodes: Mapped[list["Node"]] = relationship(back_populates="group")


class Node(Base):
    """Node representing a physical or virtual machine."""

    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    mac_address: Mapped[str] = mapped_column(
        String(17), unique=True, index=True, nullable=False
    )
    hostname: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv6 compatible
    state: Mapped[str] = mapped_column(String(20), default="discovered", nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(36))

    # Hardware identification
    vendor: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100), index=True)
    system_uuid: Mapped[str | None] = mapped_column(String(36))

    # Metadata
    arch: Mapped[str] = mapped_column(String(10), default="x86_64")
    boot_mode: Mapped[str] = mapped_column(String(4), default="bios")

    # Relationships
    group_id: Mapped[str | None] = mapped_column(ForeignKey("device_groups.id"))
    group: Mapped[DeviceGroup | None] = relationship(back_populates="nodes")
    tags: Mapped[list["NodeTag"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column()

    # Installation tracking
    install_attempts: Mapped[int] = mapped_column(default=0)
    last_install_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_changed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # State log relationship
    state_logs: Mapped[list["NodeStateLog"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )

    # Event log relationship
    events: Mapped[list["NodeEvent"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class NodeStateLog(Base):
    """Audit log for node state transitions."""

    __tablename__ = "node_state_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_state: Mapped[str] = mapped_column(String(20), nullable=False)
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)
    triggered_by: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # admin, system, node_report
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationship
    node: Mapped["Node"] = relationship(back_populates="state_logs")


class NodeEvent(Base):
    """General event log for node lifecycle events."""

    __tablename__ = "node_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Event type: boot_started, install_started, install_progress, install_complete,
    #             install_failed, first_boot, heartbeat
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Status: success, failed, in_progress
    status: Mapped[str] = mapped_column(String(20), default="success")

    # Optional message and progress
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[int | None] = mapped_column(nullable=True)  # 0-100

    # Metadata (OS version, kernel, etc.)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Client info
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationship
    node: Mapped["Node"] = relationship(back_populates="events")


class NodeTag(Base):
    """Tag for categorizing nodes."""

    __tablename__ = "node_tags"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Relationships
    node: Mapped[Node] = relationship(back_populates="tags")

    __table_args__ = (UniqueConstraint("node_id", "tag", name="uq_node_tag"),)


class StorageBackend(Base):
    """Storage backend configuration (NFS, iSCSI, S3, HTTP)."""

    __tablename__ = "storage_backends"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(10), index=True, nullable=False)  # nfs, iscsi, s3, http
    status: Mapped[str] = mapped_column(String(10), index=True, default="offline")  # online, offline, error

    # Type-specific config stored as JSON
    config_json: Mapped[str] = mapped_column(Text, nullable=False)

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


class SyncJob(Base):
    """Sync job for automated file synchronization from external sources."""

    __tablename__ = "sync_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)

    # Destination
    destination_backend_id: Mapped[str] = mapped_column(
        ForeignKey("storage_backends.id"), nullable=False
    )
    destination_backend: Mapped[StorageBackend] = relationship()
    destination_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Filtering
    include_pattern: Mapped[str | None] = mapped_column(String(500), nullable=True)
    exclude_pattern: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Schedule
    schedule: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # manual, hourly, daily, weekly, monthly
    schedule_day: Mapped[int | None] = mapped_column(nullable=True)  # 0-6 or 1-31
    schedule_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM

    # Sync options
    verify_checksums: Mapped[bool] = mapped_column(default=True)
    delete_removed: Mapped[bool] = mapped_column(default=False)
    keep_versions: Mapped[int] = mapped_column(default=3)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="idle", index=True
    )  # idle, running, synced, failed
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    runs: Mapped[list["SyncJobRun"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class SyncJobRun(Base):
    """Individual run record for a sync job."""

    __tablename__ = "sync_job_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="running"
    )  # running, success, failed

    # Stats
    files_synced: Mapped[int] = mapped_column(default=0)
    bytes_transferred: Mapped[int] = mapped_column(default=0)

    # Progress
    current_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    progress_percent: Mapped[int] = mapped_column(default=0)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    job: Mapped[SyncJob] = relationship(back_populates="runs")