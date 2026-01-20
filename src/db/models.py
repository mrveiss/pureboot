"""SQLAlchemy database models."""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
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