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
PI_SERIAL_PATTERN = re.compile(r"^[0-9a-f]{8}$")


def normalize_mac(mac: str) -> str:
    """Normalize MAC address to colon-separated lowercase."""
    return mac.replace("-", ":").lower()


# ============== Node Schemas ==============


class NodeCreate(BaseModel):
    """Schema for creating a new node.

    Example:
        ```json
        {
            "mac_address": "00:11:22:33:44:55",
            "hostname": "web-server-01",
            "arch": "x86_64",
            "boot_mode": "uefi"
        }
        ```
    """

    mac_address: str = Field(
        ...,
        description="MAC address in format XX:XX:XX:XX:XX:XX",
        examples=["00:11:22:33:44:55", "aa:bb:cc:dd:ee:ff"],
    )
    hostname: str | None = Field(
        None,
        description="Hostname for the node",
        examples=["web-server-01", "db-node-02"],
    )
    arch: str = Field(
        "x86_64",
        description="CPU architecture",
        examples=["x86_64", "arm64", "aarch64"],
    )
    boot_mode: str = Field(
        "bios",
        description="Boot mode",
        examples=["bios", "uefi", "pi"],
    )
    group_id: str | None = Field(None, description="Device group ID to assign")
    vendor: str | None = Field(None, description="Hardware vendor", examples=["Dell", "HP", "Lenovo"])
    model: str | None = Field(None, description="Hardware model", examples=["PowerEdge R640", "ProLiant DL380"])
    serial_number: str | None = Field(None, description="Serial number")
    system_uuid: str | None = Field(None, description="System UUID from SMBIOS")
    pi_model: str | None = Field(
        None,
        description="Raspberry Pi model",
        examples=["pi3b+", "pi4", "pi5", "cm4"],
    )

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
        valid = {"bios", "uefi", "pi"}
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
    pi_model: str | None = None


class StateTransition(BaseModel):
    """Request to transition node to new state.

    Example:
        ```json
        {
            "state": "pending",
            "comment": "Approved for provisioning by admin"
        }
        ```
    """

    state: str = Field(
        ...,
        description="Target state for the node",
        examples=["pending", "installing", "active", "retired"],
    )
    comment: str | None = Field(
        None,
        description="Optional comment about the transition",
        examples=["Approved for provisioning", "Failed hardware - replacing"],
    )
    force: bool = Field(
        False,
        description="Force transition, bypassing retry limits and resetting counters",
    )

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
    pi_model: str | None = None
    group_id: str | None
    tags: list[str] = []
    install_attempts: int = 0
    last_install_error: str | None = None
    state_changed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None
    health_status: str = "unknown"
    health_score: int = 100

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
            pi_model=getattr(node, 'pi_model', None),  # Handle nodes without pi_model
            group_id=node.group_id,
            tags=[t.tag for t in node.tags],
            install_attempts=node.install_attempts,
            last_install_error=node.last_install_error,
            state_changed_at=node.state_changed_at,
            created_at=node.created_at,
            updated_at=node.updated_at,
            last_seen_at=node.last_seen_at,
            health_status=getattr(node, 'health_status', 'unknown'),
            health_score=getattr(node, 'health_score', 100),
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


# ============== Raspberry Pi Schemas ==============


class PiRegisterRequest(BaseModel):
    """Schema for registering a Raspberry Pi node.

    Used by Pi deploy environments to register themselves with the controller
    during network boot. The serial number is used as the primary identifier
    for Pi devices.

    Example:
        ```json
        {
            "serial": "d83add36",
            "mac": "dc:a6:32:12:34:56",
            "model": "pi4",
            "ip_address": "192.168.1.100"
        }
        ```
    """

    serial: str = Field(
        ...,
        description="Pi serial number (8 hex characters from /proc/cpuinfo)",
        examples=["d83add36", "0000000a"],
    )
    mac: str = Field(
        ...,
        description="MAC address of the Pi's ethernet interface",
        examples=["dc:a6:32:12:34:56", "e4:5f:01:ab:cd:ef"],
    )
    model: str = Field(
        "pi4",
        description="Raspberry Pi model identifier",
        examples=["pi3", "pi4", "pi5"],
    )
    ip_address: str | None = Field(
        None,
        description="Current IP address of the Pi",
        examples=["192.168.1.100", "10.0.0.50"],
    )

    @field_validator("serial")
    @classmethod
    def validate_serial(cls, v: str) -> str:
        """Validate and normalize Pi serial number.

        Pi serial numbers are 8 hex characters, normalized to lowercase.
        """
        normalized = v.lower()
        if not PI_SERIAL_PATTERN.match(normalized):
            raise ValueError(
                f"Invalid Pi serial number: {v}. "
                "Must be exactly 8 hexadecimal characters."
            )
        return normalized

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        """Validate and normalize MAC address."""
        if not MAC_PATTERN.match(v):
            raise ValueError(f"Invalid MAC address format: {v}")
        return normalize_mac(v)

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate Pi model identifier."""
        valid_models = {"pi3", "pi4", "pi5"}
        if v not in valid_models:
            raise ValueError(
                f"Invalid Pi model: {v}. Must be one of {sorted(valid_models)}"
            )
        return v


class PiBootResponse(BaseModel):
    """Response schema for Pi boot endpoint.

    Returned by the controller to tell the Pi deploy environment what action
    to take based on the node's current state.

    Actions:
        - deploy_image: Download and write image to target device
        - nfs_boot: Boot from NFS root (diskless operation)
        - local_boot: Boot from local storage (SD card / NVMe)

    Example (deploy_image):
        ```json
        {
            "state": "installing",
            "message": "Deploying Ubuntu Server 24.04 ARM64",
            "action": "deploy_image",
            "image_url": "http://pureboot.local/images/ubuntu-arm64.img.xz",
            "target_device": "/dev/mmcblk0",
            "callback_url": "http://pureboot.local/api/v1/nodes/abc123/report"
        }
        ```

    Example (nfs_boot):
        ```json
        {
            "state": "installing",
            "action": "nfs_boot",
            "nfs_server": "192.168.1.10",
            "nfs_path": "/srv/nfs/pi-roots/node-abc123"
        }
        ```

    Example (local_boot):
        ```json
        {
            "state": "active",
            "action": "local_boot",
            "message": "Boot from local SD card"
        }
        ```
    """

    state: str = Field(
        ...,
        description="Current state of the node in the state machine",
        examples=["discovered", "pending", "installing", "active"],
    )
    message: str | None = Field(
        None,
        description="Human-readable status message",
        examples=["Waiting for approval", "Deploying Ubuntu Server 24.04"],
    )
    action: str | None = Field(
        None,
        description="Action for the deploy environment to take",
        examples=["deploy_image", "nfs_boot", "local_boot"],
    )
    image_url: str | None = Field(
        None,
        description="URL of the disk image to deploy",
        examples=["http://pureboot.local/images/ubuntu-arm64.img.xz"],
    )
    target_device: str | None = Field(
        None,
        description="Target device for image deployment",
        examples=["/dev/mmcblk0", "/dev/nvme0n1"],
    )
    callback_url: str | None = Field(
        None,
        description="URL to call when deployment is complete",
        examples=["http://pureboot.local/api/v1/nodes/abc123/report"],
    )
    nfs_server: str | None = Field(
        None,
        description="NFS server IP or hostname for diskless boot",
        examples=["192.168.1.10", "nfs.local"],
    )
    nfs_path: str | None = Field(
        None,
        description="NFS path to root filesystem for diskless boot",
        examples=["/srv/nfs/pi-roots/node-abc123"],
    )


# ============== Device Group Schemas ==============


class DeviceGroupCreate(BaseModel):
    """Schema for creating a device group."""

    name: str
    description: str | None = None
    parent_id: str | None = None
    default_workflow_id: str | None = None
    auto_provision: bool | None = None

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
    parent_id: str | None = None
    default_workflow_id: str | None = None
    auto_provision: bool | None = None


class DeviceGroupResponse(BaseModel):
    """Schema for device group response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None

    # Hierarchy
    parent_id: str | None
    path: str
    depth: int
    children_count: int = 0

    # Own settings (may be None = inherit)
    default_workflow_id: str | None
    auto_provision: bool | None

    # Effective settings (computed)
    effective_workflow_id: str | None = None
    effective_auto_provision: bool = False

    # Metadata
    node_count: int = 0
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_group(
        cls,
        group,
        node_count: int = 0,
        children_count: int = 0,
        effective_workflow_id: str | None = None,
        effective_auto_provision: bool = False,
    ) -> "DeviceGroupResponse":
        """Create response from DeviceGroup model."""
        return cls(
            id=group.id,
            name=group.name,
            description=group.description,
            parent_id=group.parent_id,
            path=group.path,
            depth=group.depth,
            children_count=children_count,
            default_workflow_id=group.default_workflow_id,
            auto_provision=group.auto_provision,
            effective_workflow_id=effective_workflow_id
            if effective_workflow_id
            else group.default_workflow_id,
            effective_auto_provision=effective_auto_provision
            if group.auto_provision is None
            else group.auto_provision,
            node_count=node_count,
            created_at=group.created_at,
            updated_at=group.updated_at,
        )


# ============== Site Schemas ==============

# Valid values for site-specific enum fields
AUTONOMY_LEVELS = {"readonly", "limited", "full"}
CONFLICT_RESOLUTIONS = {"central_wins", "last_write", "site_wins", "manual"}
CACHE_POLICIES = {"minimal", "assigned", "mirror", "pattern"}
DISCOVERY_METHODS = {"dhcp", "dns", "anycast", "fallback"}
MIGRATION_POLICIES = {"manual", "auto_accept", "auto_release", "bidirectional"}


class SiteCreate(BaseModel):
    """Schema for creating a site (is_site=True DeviceGroup).

    Sites are special DeviceGroups that represent physical locations
    with their own site agents for local caching and offline operation.

    Example:
        ```json
        {
            "name": "datacenter-west",
            "description": "Western datacenter site",
            "parent_id": null,
            "agent_url": "https://site-west.example.com:8443",
            "autonomy_level": "limited",
            "cache_policy": "assigned"
        }
        ```
    """

    name: str = Field(
        ...,
        description="Site name",
        examples=["datacenter-west", "branch-office-nyc"],
    )
    description: str | None = Field(
        None,
        description="Site description",
    )
    parent_id: str | None = Field(
        None,
        description="Parent site ID (for nested site hierarchy)",
    )

    # Site agent connection
    agent_url: str | None = Field(
        None,
        description="URL of the site agent",
        examples=["https://site-agent.local:8443"],
    )

    # Site autonomy settings
    autonomy_level: str = Field(
        "readonly",
        description="Site autonomy level: readonly, limited, or full",
    )
    conflict_resolution: str = Field(
        "central_wins",
        description="Conflict resolution strategy: central_wins, last_write, site_wins, manual",
    )

    # Content caching policy
    cache_policy: str = Field(
        "minimal",
        description="Cache policy: minimal, assigned, mirror, pattern",
    )
    cache_patterns_json: str | None = Field(
        None,
        description="JSON patterns for pattern-based caching",
    )
    cache_max_size_gb: int | None = Field(
        None,
        description="Maximum cache size in GB",
        ge=1,
    )
    cache_retention_days: int = Field(
        30,
        description="Cache retention period in days",
        ge=1,
    )

    # Network discovery config
    discovery_method: str = Field(
        "dhcp",
        description="How nodes discover this site: dhcp, dns, anycast, fallback",
    )
    discovery_config_json: str | None = Field(
        None,
        description="JSON configuration for discovery method",
    )

    # Migration policy
    migration_policy: str = Field(
        "manual",
        description="Node migration policy: manual, auto_accept, auto_release, bidirectional",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate site name."""
        if not v or len(v) > 100:
            raise ValueError("Name must be 1-100 characters")
        return v

    @field_validator("autonomy_level")
    @classmethod
    def validate_autonomy_level(cls, v: str) -> str:
        """Validate autonomy level."""
        if v not in AUTONOMY_LEVELS:
            raise ValueError(f"Invalid autonomy_level: {v}. Must be one of {AUTONOMY_LEVELS}")
        return v

    @field_validator("conflict_resolution")
    @classmethod
    def validate_conflict_resolution(cls, v: str) -> str:
        """Validate conflict resolution strategy."""
        if v not in CONFLICT_RESOLUTIONS:
            raise ValueError(f"Invalid conflict_resolution: {v}. Must be one of {CONFLICT_RESOLUTIONS}")
        return v

    @field_validator("cache_policy")
    @classmethod
    def validate_cache_policy(cls, v: str) -> str:
        """Validate cache policy."""
        if v not in CACHE_POLICIES:
            raise ValueError(f"Invalid cache_policy: {v}. Must be one of {CACHE_POLICIES}")
        return v

    @field_validator("discovery_method")
    @classmethod
    def validate_discovery_method(cls, v: str) -> str:
        """Validate discovery method."""
        if v not in DISCOVERY_METHODS:
            raise ValueError(f"Invalid discovery_method: {v}. Must be one of {DISCOVERY_METHODS}")
        return v

    @field_validator("migration_policy")
    @classmethod
    def validate_migration_policy(cls, v: str) -> str:
        """Validate migration policy."""
        if v not in MIGRATION_POLICIES:
            raise ValueError(f"Invalid migration_policy: {v}. Must be one of {MIGRATION_POLICIES}")
        return v


class SiteUpdate(BaseModel):
    """Schema for updating a site.

    All fields are optional. Only provided fields will be updated.
    """

    name: str | None = None
    description: str | None = None
    parent_id: str | None = None
    agent_url: str | None = None
    autonomy_level: str | None = None
    conflict_resolution: str | None = None
    cache_policy: str | None = None
    cache_patterns_json: str | None = None
    cache_max_size_gb: int | None = Field(None, ge=1)
    cache_retention_days: int | None = Field(None, ge=1)
    discovery_method: str | None = None
    discovery_config_json: str | None = None
    migration_policy: str | None = None

    @field_validator("autonomy_level")
    @classmethod
    def validate_autonomy_level(cls, v: str | None) -> str | None:
        """Validate autonomy level if provided."""
        if v is not None and v not in AUTONOMY_LEVELS:
            raise ValueError(f"Invalid autonomy_level: {v}. Must be one of {AUTONOMY_LEVELS}")
        return v

    @field_validator("conflict_resolution")
    @classmethod
    def validate_conflict_resolution(cls, v: str | None) -> str | None:
        """Validate conflict resolution if provided."""
        if v is not None and v not in CONFLICT_RESOLUTIONS:
            raise ValueError(f"Invalid conflict_resolution: {v}. Must be one of {CONFLICT_RESOLUTIONS}")
        return v

    @field_validator("cache_policy")
    @classmethod
    def validate_cache_policy(cls, v: str | None) -> str | None:
        """Validate cache policy if provided."""
        if v is not None and v not in CACHE_POLICIES:
            raise ValueError(f"Invalid cache_policy: {v}. Must be one of {CACHE_POLICIES}")
        return v

    @field_validator("discovery_method")
    @classmethod
    def validate_discovery_method(cls, v: str | None) -> str | None:
        """Validate discovery method if provided."""
        if v is not None and v not in DISCOVERY_METHODS:
            raise ValueError(f"Invalid discovery_method: {v}. Must be one of {DISCOVERY_METHODS}")
        return v

    @field_validator("migration_policy")
    @classmethod
    def validate_migration_policy(cls, v: str | None) -> str | None:
        """Validate migration policy if provided."""
        if v is not None and v not in MIGRATION_POLICIES:
            raise ValueError(f"Invalid migration_policy: {v}. Must be one of {MIGRATION_POLICIES}")
        return v


class SiteResponse(DeviceGroupResponse):
    """Extended response schema for sites.

    Includes all DeviceGroupResponse fields plus site-specific fields.
    """

    is_site: bool = True

    # Site agent status
    agent_url: str | None = None
    agent_status: str | None = None  # online, offline, degraded
    agent_last_seen: datetime | None = None

    # Site autonomy settings
    autonomy_level: str | None = None
    conflict_resolution: str | None = None

    # Content caching policy
    cache_policy: str | None = None
    cache_patterns_json: str | None = None
    cache_max_size_gb: int | None = None
    cache_retention_days: int | None = None

    # Network discovery config
    discovery_method: str | None = None
    discovery_config_json: str | None = None

    # Migration policy
    migration_policy: str | None = None

    @classmethod
    def from_site(
        cls,
        site,
        node_count: int = 0,
        children_count: int = 0,
        effective_workflow_id: str | None = None,
        effective_auto_provision: bool = False,
    ) -> "SiteResponse":
        """Create response from DeviceGroup model with is_site=True."""
        return cls(
            id=site.id,
            name=site.name,
            description=site.description,
            parent_id=site.parent_id,
            path=site.path,
            depth=site.depth,
            children_count=children_count,
            default_workflow_id=site.default_workflow_id,
            auto_provision=site.auto_provision,
            effective_workflow_id=effective_workflow_id
            if effective_workflow_id
            else site.default_workflow_id,
            effective_auto_provision=effective_auto_provision
            if site.auto_provision is None
            else site.auto_provision,
            node_count=node_count,
            created_at=site.created_at,
            updated_at=site.updated_at,
            # Site-specific fields
            is_site=site.is_site,
            agent_url=site.agent_url,
            agent_status=site.agent_status,
            agent_last_seen=site.agent_last_seen,
            autonomy_level=site.autonomy_level,
            conflict_resolution=site.conflict_resolution,
            cache_policy=site.cache_policy,
            cache_patterns_json=site.cache_patterns_json,
            cache_max_size_gb=site.cache_max_size_gb,
            cache_retention_days=site.cache_retention_days,
            discovery_method=site.discovery_method,
            discovery_config_json=site.discovery_config_json,
            migration_policy=site.migration_policy,
        )


class SiteHealthResponse(BaseModel):
    """Response schema for site health status."""

    site_id: str
    agent_status: str | None  # online, offline, degraded
    agent_last_seen: datetime | None
    pending_sync_items: int = 0
    conflicts_pending: int = 0
    nodes_count: int = 0
    cache_used_gb: float | None = None
    cache_max_gb: int | None = None


class SiteSyncRequest(BaseModel):
    """Request to trigger manual sync for a site."""

    full_sync: bool = Field(
        False,
        description="Whether to perform a full sync (vs incremental)",
    )
    entity_types: list[str] | None = Field(
        None,
        description="Specific entity types to sync (e.g., ['node', 'workflow'])",
    )


class SiteSyncResponse(BaseModel):
    """Response for sync trigger request."""

    sync_id: str
    status: str  # queued, started
    message: str


# ============== Report Schemas ==============


class NodeReport(BaseModel):
    """Node status report from the node itself.

    This endpoint is called by nodes during the boot and installation process
    to report their status and update hardware information.

    Example (event-based):
        ```json
        {
            "mac_address": "00:11:22:33:44:55",
            "event": "install_progress",
            "status": "in_progress",
            "message": "Installing packages",
            "ip_address": "192.168.1.100"
        }
        ```
    """

    mac_address: str = Field(
        ...,
        description="MAC address of the reporting node",
        examples=["00:11:22:33:44:55"],
    )

    # Event-based reporting (new)
    event: Literal[
        "boot_started",
        "install_started",
        "install_progress",
        "install_complete",
        "install_failed",
        "first_boot",
        "heartbeat",
    ] | None = Field(
        None,
        description="Event type being reported",
    )
    status: Literal["success", "failed", "in_progress"] = Field(
        "success",
        description="Status of the event",
    )
    message: str | None = Field(
        None,
        description="Human-readable status message",
        examples=["Installing packages", "Copying files"],
    )
    event_metadata: dict | None = Field(
        None,
        description="Additional event-specific metadata",
    )

    # Hardware/network info
    ip_address: str | None = Field(
        None,
        description="Current IP address of the node",
        examples=["192.168.1.100", "10.0.0.50"],
    )
    hostname: str | None = Field(
        None,
        description="Hostname of the node",
    )
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    system_uuid: str | None = None

    # Legacy installation reporting (backwards compatibility)
    installation_status: Literal["started", "progress", "complete", "failed"] | None = Field(
        None,
        description="Legacy: Installation status (use 'event' instead)",
    )
    installation_progress: int | None = Field(
        None,
        description="Installation progress percentage (0-100)",
        ge=0,
        le=100,
    )
    installation_error: str | None = Field(
        None,
        description="Error message if installation failed",
    )

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
    available_bytes: int | None = None
    file_count: int
    template_count: int = 0


class StorageBackendResponse(BaseModel):
    """Schema for storage backend response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    status: str
    enabled: bool = True
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

        # Calculate available bytes if total is known
        available_bytes = None
        if backend.total_bytes is not None:
            available_bytes = max(0, backend.total_bytes - backend.used_bytes)

        # Derive enabled from status (enabled if not explicitly offline)
        enabled = backend.status != "offline"

        return cls(
            id=backend.id,
            name=backend.name,
            type=backend.type,
            status=backend.status,
            enabled=enabled,
            config=config,
            stats=StorageBackendStats(
                used_bytes=backend.used_bytes,
                total_bytes=backend.total_bytes,
                available_bytes=available_bytes,
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


# ============== Node Stats Schemas ==============


class NodeStatsResponse(BaseModel):
    """Aggregated node statistics."""

    total: int
    by_state: dict[str, int]
    discovered_last_hour: int
    installing_count: int


# ============== Health Monitoring Schemas ==============


class HealthSummaryResponse(BaseModel):
    """Dashboard health summary."""

    total_nodes: int
    by_status: dict[str, int]  # {healthy: 45, stale: 3, offline: 2, unknown: 1}
    average_score: float
    active_alerts: int
    critical_alerts: int


class HealthAlertResponse(BaseModel):
    """Response for a single health alert."""

    id: str
    node_id: str
    node_name: str | None = None
    alert_type: str
    severity: str
    status: str
    message: str
    details: dict | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None

    @classmethod
    def from_alert(cls, alert, node_name: str | None = None) -> "HealthAlertResponse":
        """Create response from HealthAlert model."""
        details = None
        if alert.details_json:
            try:
                details = json.loads(alert.details_json)
            except json.JSONDecodeError:
                pass
        return cls(
            id=alert.id,
            node_id=alert.node_id,
            node_name=node_name,
            alert_type=alert.alert_type,
            severity=alert.severity,
            status=alert.status,
            message=alert.message,
            details=details,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
            acknowledged_by=alert.acknowledged_by,
            resolved_at=alert.resolved_at,
        )


class NodeHealthDetailResponse(BaseModel):
    """Detailed health for a single node."""

    node_id: str
    health_status: str
    health_score: int
    score_breakdown: dict[str, int]
    last_seen_at: datetime | None
    boot_count: int
    install_attempts: int
    last_boot_at: datetime | None = None
    last_ip_change_at: datetime | None = None
    previous_ip_address: str | None = None
    active_alerts: list[HealthAlertResponse] = []


class HealthSnapshotResponse(BaseModel):
    """Response for a single health snapshot."""

    timestamp: datetime
    health_status: str
    health_score: int
    last_seen_seconds_ago: int
    boot_count: int
    install_attempts: int
    ip_address: str | None = None


# ============== Bulk Operation Schemas ==============


class BulkAssignGroupRequest(BaseModel):
    """Request to assign multiple nodes to a group."""

    node_ids: list[str]
    group_id: str | None = None


class BulkAssignWorkflowRequest(BaseModel):
    """Request to assign multiple nodes to a workflow."""

    node_ids: list[str]
    workflow_id: str | None = None


class BulkAddTagRequest(BaseModel):
    """Request to add a tag to multiple nodes."""

    node_ids: list[str]
    tag: str

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        """Validate and normalize tag."""
        v = v.strip().lower()
        if not v or len(v) > 50:
            raise ValueError("Tag must be 1-50 characters")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Tag can only contain letters, numbers, hyphens, underscores")
        return v


class BulkRemoveTagRequest(BaseModel):
    """Request to remove a tag from multiple nodes."""

    node_ids: list[str]
    tag: str

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        """Normalize tag."""
        return v.strip().lower()


class BulkChangeStateRequest(BaseModel):
    """Request to change state for multiple nodes."""

    node_ids: list[str]
    new_state: str

    @field_validator("new_state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Validate state is a known state."""
        from src.core.state_machine import NodeStateMachine

        if v not in NodeStateMachine.STATES:
            raise ValueError(
                f"Invalid state: {v}. Must be one of {NodeStateMachine.STATES}"
            )
        return v


class BulkOperationResult(BaseModel):
    """Result of a bulk operation."""

    updated: int


class BulkChangeStateError(BaseModel):
    """Error for a single node in bulk state change."""

    node_id: str
    error: str


class BulkChangeStateResult(BaseModel):
    """Result of bulk state change operation."""

    updated: int
    failed: int
    errors: list[BulkChangeStateError] = []


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


class CloneFailedRequest(BaseModel):
    """Request body for marking clone session as failed."""

    error_message: str
    error_code: str | None = None
    role: Literal["source", "target"] | None = None


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


# ============== Resize Plan Schemas ==============


class PartitionPlanItem(BaseModel):
    """Single partition in a resize plan."""

    partition: int
    current_size_bytes: int
    new_size_bytes: int
    filesystem: str | None = None
    action: Literal["keep", "shrink", "grow", "delete"] = "keep"
    min_size_bytes: int | None = None
    can_resize: bool = True


class ResizePlan(BaseModel):
    """Plan for resizing partitions during clone."""

    source_disk_bytes: int
    target_disk_bytes: int
    resize_mode: Literal["none", "shrink_source", "grow_target"]
    partitions: list[PartitionPlanItem]
    feasible: bool = True
    error_message: str | None = None


class CloneAnalysisResponse(BaseModel):
    """Response from clone analysis."""

    source_disk: dict | None = None  # Disk info
    target_disk: dict | None = None  # Disk info
    size_difference_bytes: int
    resize_needed: bool
    suggested_plan: ResizePlan | None = None


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


# ============== Site Agent Schemas ==============


class AgentRegistration(BaseModel):
    """Schema for site agent registration with central controller."""

    site_id: str = Field(..., description="Site ID this agent belongs to")
    token: str = Field(..., description="Registration token")
    agent_url: str = Field(..., description="URL where agent can be reached")
    agent_version: str = Field(..., description="Agent software version")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Agent capabilities (e.g., ['tftp', 'http', 'proxy'])",
    )


class AgentConfig(BaseModel):
    """Configuration returned to agent after registration."""

    site_id: str
    site_name: str
    autonomy_level: str | None
    cache_policy: str | None
    cache_max_size_gb: int | None
    cache_retention_days: int | None
    heartbeat_interval: int = 60
    sync_enabled: bool = True


class AgentRegistrationResponse(BaseModel):
    """Response for successful agent registration."""

    success: bool = True
    message: str
    config: AgentConfig


class AgentHeartbeat(BaseModel):
    """Schema for agent heartbeat to central controller."""

    site_id: str = Field(..., description="Site ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_version: str = Field(..., description="Agent software version")
    uptime_seconds: int = Field(..., ge=0)
    services: dict[str, str] = Field(
        ...,
        description="Service status (e.g., {'tftp': 'ok', 'http': 'ok'})",
    )
    nodes_seen_last_hour: int = 0
    active_boots: int = 0
    cache_hit_rate: float = Field(0.0, ge=0.0, le=1.0)
    disk_usage_percent: float = Field(0.0, ge=0.0, le=100.0)
    pending_sync_items: int = 0
    last_sync_at: datetime | None = None
    conflicts_pending: int = 0


class HeartbeatCommand(BaseModel):
    """Command sent to agent via heartbeat response."""

    command: str  # sync, reload_config, cache_evict
    params: dict = Field(default_factory=dict)


class HeartbeatResponse(BaseModel):
    """Response to agent heartbeat."""

    acknowledged: bool = True
    server_time: datetime = Field(default_factory=datetime.utcnow)
    commands: list[HeartbeatCommand] = Field(default_factory=list)


class AgentStatusResponse(BaseModel):
    """Response for agent status query."""

    site_id: str
    site_name: str
    agent_url: str | None
    agent_status: str | None  # online, degraded, offline
    agent_last_seen: datetime | None
    agent_version: str | None
    uptime_seconds: int | None
    services: dict[str, str] | None
    nodes_count: int = 0
    cache_hit_rate: float | None
    disk_usage_percent: float | None