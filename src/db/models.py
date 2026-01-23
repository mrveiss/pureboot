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
    user_groups: Mapped[list["UserGroup"]] = relationship(
        secondary="user_group_device_groups", back_populates="device_groups"
    )


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

    # User groups with direct access to this node
    user_groups: Mapped[list["UserGroup"]] = relationship(
        secondary="user_group_nodes", back_populates="nodes"
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


class Template(Base):
    """Template for OS installation (ISO, kickstart, preseed, etc.)."""

    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # iso, kickstart, preseed, autounattend, cloud-init, script
    os_family: Mapped[str | None] = mapped_column(String(20))  # linux, windows, bsd
    os_name: Mapped[str | None] = mapped_column(String(50))  # ubuntu, debian, rhel, windows
    os_version: Mapped[str | None] = mapped_column(String(20))  # 24.04, 9, 2022
    architecture: Mapped[str] = mapped_column(String(10), default="x86_64")  # x86_64, aarch64

    # File storage
    file_path: Mapped[str | None] = mapped_column(String(500))
    storage_backend_id: Mapped[str | None] = mapped_column(
        ForeignKey("storage_backends.id"), nullable=True
    )
    storage_backend: Mapped["StorageBackend | None"] = relationship()
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64))  # SHA256

    # Metadata
    description: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )


class Approval(Base):
    """Approval request for four-eye principle operations."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    action_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # bulk_wipe, bulk_retire, delete_template, etc.
    action_data_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON

    # Requester info (no auth yet, so just names/IPs)
    requester_id: Mapped[str | None] = mapped_column(String(100))
    requester_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, approved, rejected, expired, cancelled
    required_approvers: Mapped[int] = mapped_column(default=2)

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    votes: Mapped[list["ApprovalVote"]] = relationship(
        back_populates="approval", cascade="all, delete-orphan"
    )


class ApprovalVote(Base):
    """Vote on an approval request."""

    __tablename__ = "approval_votes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Voter info
    user_id: Mapped[str | None] = mapped_column(String(100))
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Vote
    vote: Mapped[str] = mapped_column(String(10), nullable=False)  # approve, reject
    comment: Mapped[str | None] = mapped_column(Text)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationship
    approval: Mapped["Approval"] = relationship(back_populates="votes")


class User(Base):
    """User account for authentication and authorization."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), default="viewer", nullable=False
    )  # admin, operator, approver, viewer

    # RBAC role reference (for new permission system)
    role_id: Mapped[str | None] = mapped_column(
        ForeignKey("roles.id"), nullable=True
    )
    role_ref: Mapped["Role | None"] = relationship()

    # Service account fields
    is_service_account: Mapped[bool] = mapped_column(default=False)
    service_account_description: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Auth source for LDAP/AD
    auth_source: Mapped[str] = mapped_column(
        String(10), default="local"
    )  # local, ldap, ad
    ldap_dn: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Account status
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)

    # Tracking
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    groups: Mapped[list["UserGroup"]] = relationship(
        secondary="user_group_members", back_populates="members"
    )


class Role(Base):
    """Role definition for RBAC."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_system_role: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles"
    )
    user_groups: Mapped[list["UserGroup"]] = relationship(
        secondary="user_group_roles", back_populates="roles"
    )


class Permission(Base):
    """Permission definition for RBAC."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    resource: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    roles: Mapped[list["Role"]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_permission_resource_action"),
    )


class RolePermission(Base):
    """Association table for roles and permissions."""

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserGroup(Base):
    """User group for team-based access control."""

    __tablename__ = "user_groups"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    requires_approval: Mapped[bool] = mapped_column(default=False)
    ldap_group_dn: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    members: Mapped[list["User"]] = relationship(
        secondary="user_group_members", back_populates="groups"
    )
    roles: Mapped[list["Role"]] = relationship(
        secondary="user_group_roles", back_populates="user_groups"
    )
    device_groups: Mapped[list["DeviceGroup"]] = relationship(
        secondary="user_group_device_groups", back_populates="user_groups"
    )
    tags: Mapped[list["UserGroupTag"]] = relationship(
        back_populates="user_group", cascade="all, delete-orphan"
    )
    nodes: Mapped[list["Node"]] = relationship(
        secondary="user_group_nodes", back_populates="user_groups"
    )


class UserGroupMember(Base):
    """Association table for users and user groups."""

    __tablename__ = "user_group_members"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(default=func.now())


class UserGroupRole(Base):
    """Association table for user groups and roles."""

    __tablename__ = "user_group_roles"

    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class UserGroupDeviceGroup(Base):
    """Association table for user groups and device groups."""

    __tablename__ = "user_group_device_groups"

    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    device_group_id: Mapped[str] = mapped_column(
        ForeignKey("device_groups.id", ondelete="CASCADE"), primary_key=True
    )


class UserGroupTag(Base):
    """Tag for categorizing user groups and defining node access by tag."""

    __tablename__ = "user_group_tags"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Relationships
    user_group: Mapped["UserGroup"] = relationship(back_populates="tags")

    __table_args__ = (
        UniqueConstraint("user_group_id", "tag", name="uq_user_group_tag"),
    )


class UserGroupNode(Base):
    """Association table for user groups and nodes (direct node access)."""

    __tablename__ = "user_group_nodes"

    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )


class RefreshToken(Base):
    """Refresh token for JWT authentication."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationship
    user: Mapped["User"] = relationship()


class Hypervisor(Base):
    """Hypervisor connection for VM management (oVirt, Proxmox)."""

    __tablename__ = "hypervisors"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # ovirt, proxmox

    # Connection details
    api_url: Mapped[str] = mapped_column(String(500), nullable=False)
    username: Mapped[str | None] = mapped_column(String(100))
    password_encrypted: Mapped[str | None] = mapped_column(Text)  # Encrypted password
    verify_ssl: Mapped[bool] = mapped_column(default=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="unknown", index=True
    )  # online, offline, error, unknown
    last_error: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None] = mapped_column()

    # Cached stats
    vm_count: Mapped[int] = mapped_column(default=0)
    host_count: Mapped[int] = mapped_column(default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )