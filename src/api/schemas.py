"""Pydantic schemas for API request/response validation."""
import re
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, field_validator

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
    """Schema for state transition request."""

    state: str

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
            created_at=node.created_at,
            updated_at=node.updated_at,
            last_seen_at=node.last_seen_at,
        )


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
    """Schema for node status report."""

    mac_address: str
    ip_address: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    system_uuid: str | None = None
    state_info: dict | None = None  # Installation progress, etc.

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        """Validate and normalize MAC address."""
        if not MAC_PATTERN.match(v):
            raise ValueError(f"Invalid MAC address format: {v}")
        return normalize_mac(v)


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
