"""SQLAlchemy database models."""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, func
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

    # Hierarchy
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("device_groups.id", ondelete="RESTRICT"), nullable=True
    )
    path: Mapped[str] = mapped_column(String(1000), index=True, default="/")
    depth: Mapped[int] = mapped_column(default=0)

    # Default settings for nodes in this group (nullable for inheritance)
    default_workflow_id: Mapped[str | None] = mapped_column(String(36))
    auto_provision: Mapped[bool | None] = mapped_column(default=None)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    parent: Mapped["DeviceGroup | None"] = relationship(
        "DeviceGroup",
        back_populates="children",
        remote_side="DeviceGroup.id",
    )
    children: Mapped[list["DeviceGroup"]] = relationship(
        "DeviceGroup",
        back_populates="parent",
    )
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
    pi_model: Mapped[str | None] = mapped_column(String(20), nullable=True)

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

    # Version tracking
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Metadata
    description: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    versions: Mapped[list["TemplateVersion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class TemplateVersion(Base):
    """Version of a template with semantic major.minor versioning."""

    __tablename__ = "template_versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    template_id: Mapped[str] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    major: Mapped[int] = mapped_column(nullable=False)
    minor: Mapped[int] = mapped_column(nullable=False)

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File storage (optional, for large templates stored externally)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_backend_id: Mapped[str | None] = mapped_column(
        ForeignKey("storage_backends.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    template: Mapped["Template"] = relationship(back_populates="versions")
    created_by: Mapped["User | None"] = relationship()
    storage_backend: Mapped["StorageBackend | None"] = relationship()

    @property
    def version_string(self) -> str:
        """Return semantic version string (e.g., 'v1.0')."""
        return f"v{self.major}.{self.minor}"

    __table_args__ = (
        UniqueConstraint("template_id", "major", "minor", name="uq_template_version"),
    )


class Workflow(Base):
    """Workflow definition for provisioning orchestration."""

    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    os_family: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # linux, windows, bsd
    architecture: Mapped[str] = mapped_column(String(50), default="x86_64")
    boot_mode: Mapped[str] = mapped_column(String(50), default="bios")
    is_active: Mapped[bool] = mapped_column(default=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.sequence",
    )


class WorkflowStep(Base):
    """Individual step within a workflow for provisioning orchestration."""

    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # boot, script, reboot, wait, cloud_init

    # Step configuration
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    timeout_seconds: Mapped[int] = mapped_column(default=3600)

    # Failure handling
    on_failure: Mapped[str] = mapped_column(
        String(50), default="fail"
    )  # fail, retry, skip, rollback
    max_retries: Mapped[int] = mapped_column(default=3)
    retry_delay_seconds: Mapped[int] = mapped_column(default=30)

    # State transition
    next_state: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # node state after step completes
    rollback_step_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    workflow: Mapped["Workflow"] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("workflow_id", "sequence", name="uq_workflow_step_sequence"),
    )


class WorkflowExecution(Base):
    """Execution instance of a workflow on a specific node."""

    __tablename__ = "workflow_executions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    current_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True
    )

    # Status: pending, running, completed, failed, cancelled
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    node: Mapped["Node"] = relationship()
    workflow: Mapped["Workflow"] = relationship()
    current_step: Mapped["WorkflowStep | None"] = relationship()
    step_results: Mapped[list["WorkflowStepResult"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )


class WorkflowStepResult(Base):
    """Result of executing a workflow step."""

    __tablename__ = "workflow_step_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Status: pending, running, completed, failed, skipped
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Result tracking
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    execution: Mapped["WorkflowExecution"] = relationship(back_populates="step_results")
    step: Mapped["WorkflowStep"] = relationship()


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

    # Link to approval rule that triggered this request
    rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_rules.id", ondelete="SET NULL"), nullable=True
    )

    # Operation type for policy matching (e.g., "node.provision", "workflow.execute")
    operation_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Requester info (no auth yet, so just names/IPs)
    requester_id: Mapped[str | None] = mapped_column(String(100))
    requester_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, approved, rejected, expired, cancelled
    required_approvers: Mapped[int] = mapped_column(default=2)

    # Escalation tracking
    escalated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    escalation_count: Mapped[int] = mapped_column(default=0)

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Additional context about the request
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    rule: Mapped["ApprovalRule | None"] = relationship(back_populates="approvals")
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

    # Whether this vote came from escalation (e.g., escalation role member)
    is_escalation_vote: Mapped[bool] = mapped_column(default=False)

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
    escalation_rules: Mapped[list["ApprovalRule"]] = relationship(
        back_populates="escalation_role"
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


class ApprovalRule(Base):
    """Configurable approval rule for operations requiring multi-party approval."""

    __tablename__ = "approval_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    scope_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # device_group, user_group, global
    scope_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # null for global scope
    operations_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON array of operation types
    required_approvers: Mapped[int] = mapped_column(default=1)
    escalation_timeout_hours: Mapped[int] = mapped_column(default=72)
    escalation_role_id: Mapped[str | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    priority: Mapped[int] = mapped_column(default=0)  # Higher priority rules evaluated first
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    escalation_role: Mapped["Role | None"] = relationship(
        back_populates="escalation_rules"
    )
    approvals: Mapped[list["Approval"]] = relationship(back_populates="rule")


class AuditLog(Base):
    """Immutable audit trail for security-relevant events."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # When
    timestamp: Mapped[datetime] = mapped_column(
        default=func.now(), index=True, nullable=False
    )

    # Who
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # User or service account ID
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user, service_account, system
    actor_username: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv4 or IPv6

    # What
    action: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # login, logout, create, update, delete, approve, reject, etc.
    resource_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # node, user, role, approval, etc.
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Details
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON with action-specific details

    # Result
    result: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failure, denied
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Session tracking
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    auth_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # jwt, api_key, ldap

    __table_args__ = (
        Index('ix_audit_timestamp_action', 'timestamp', 'action'),
        Index('ix_audit_actor_resource', 'actor_id', 'resource_type'),
    )


class LdapConfig(Base):
    """LDAP/AD server configuration."""

    __tablename__ = "ldap_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Server settings
    server_url: Mapped[str] = mapped_column(String(500), nullable=False)  # ldap://server:389 or ldaps://server:636
    use_ssl: Mapped[bool] = mapped_column(default=False)
    use_start_tls: Mapped[bool] = mapped_column(default=False)

    # Bind credentials (for searching)
    bind_dn: Mapped[str] = mapped_column(String(500), nullable=False)
    bind_password_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)

    # Search settings
    base_dn: Mapped[str] = mapped_column(String(500), nullable=False)
    user_search_filter: Mapped[str] = mapped_column(
        String(500), default="(&(objectClass=user)(sAMAccountName={username}))"
    )
    group_search_filter: Mapped[str] = mapped_column(
        String(500), default="(&(objectClass=group)(member={user_dn}))"
    )

    # Attribute mappings
    username_attribute: Mapped[str] = mapped_column(String(50), default="sAMAccountName")
    email_attribute: Mapped[str] = mapped_column(String(50), default="mail")
    display_name_attribute: Mapped[str] = mapped_column(String(50), default="displayName")
    group_attribute: Mapped[str] = mapped_column(String(50), default="memberOf")

    # Status
    is_active: Mapped[bool] = mapped_column(default=True)
    is_primary: Mapped[bool] = mapped_column(default=False)

    # Sync settings
    sync_groups: Mapped[bool] = mapped_column(default=True)
    auto_create_users: Mapped[bool] = mapped_column(default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)


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


class ApiKey(Base):
    """API key for service account authentication."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    service_account_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    scopes_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of scope restrictions
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    # Relationships
    service_account: Mapped["User"] = relationship(foreign_keys=[service_account_id])
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint("service_account_id", "name", name="uq_api_key_account_name"),
    )


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