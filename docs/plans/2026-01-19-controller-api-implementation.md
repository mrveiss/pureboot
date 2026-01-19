# Controller API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the FastAPI Controller API with node lifecycle management, database persistence, and device groups (Issue #2).

**Architecture:** SQLAlchemy async ORM with SQLite (PostgreSQL-compatible), Pydantic schemas for API validation, state machine as a pure Python class enforcing valid transitions. Device groups provide shared settings for nodes.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, aiosqlite, Pydantic v2

---

## Task 1: Add Database Dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`

**Step 1: Update requirements.txt**

Add to `requirements.txt`:
```
sqlalchemy[asyncio]>=2.0.0
aiosqlite>=0.19.0
alembic>=1.13.0
greenlet>=3.0.0
```

**Step 2: Update pyproject.toml**

Add to dependencies list in `pyproject.toml`:
```toml
"sqlalchemy[asyncio]>=2.0.0",
"aiosqlite>=0.19.0",
"alembic>=1.13.0",
```

**Step 3: Commit**

```bash
git add requirements.txt pyproject.toml
git commit -m "chore: add database dependencies (SQLAlchemy, Alembic, aiosqlite)"
```

---

## Task 2: Database Configuration

**Files:**
- Modify: `src/config/settings.py`

**Step 1: Add database and registration settings**

Add these classes to `src/config/settings.py` before the `Settings` class:

```python
class DatabaseSettings(BaseSettings):
    """Database settings."""
    url: str = "sqlite+aiosqlite:///./pureboot.db"
    echo: bool = False  # Log SQL statements


class RegistrationSettings(BaseSettings):
    """Node registration settings."""
    auto_register: bool = True  # Auto-register unknown MACs
    default_group_id: str | None = None  # Default group for new nodes
```

**Step 2: Add to main Settings class**

Add these fields to the `Settings` class:

```python
database: DatabaseSettings = Field(default_factory=DatabaseSettings)
registration: RegistrationSettings = Field(default_factory=RegistrationSettings)
```

**Step 3: Commit**

```bash
git add src/config/settings.py
git commit -m "feat: add database and registration configuration settings"
```

---

## Task 3: State Machine Implementation

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/state_machine.py`
- Create: `tests/unit/test_state_machine.py`

**Step 1: Create core package init**

Create `src/core/__init__.py`:
```python
"""Core business logic."""
```

**Step 2: Write failing tests for state machine**

Create `tests/unit/test_state_machine.py`:
```python
"""Tests for node state machine."""
import pytest

from src.core.state_machine import NodeStateMachine, InvalidStateTransition


class TestNodeStateMachine:
    """Test state machine transitions."""

    def test_discovered_to_pending_allowed(self):
        """Can transition from discovered to pending."""
        assert NodeStateMachine.can_transition("discovered", "pending") is True

    def test_discovered_to_active_not_allowed(self):
        """Cannot skip states."""
        assert NodeStateMachine.can_transition("discovered", "active") is False

    def test_pending_to_installing_allowed(self):
        """Can transition from pending to installing."""
        assert NodeStateMachine.can_transition("pending", "installing") is True

    def test_installing_to_installed_allowed(self):
        """Can transition from installing to installed."""
        assert NodeStateMachine.can_transition("installing", "installed") is True

    def test_installed_to_active_allowed(self):
        """Can transition from installed to active."""
        assert NodeStateMachine.can_transition("installed", "active") is True

    def test_active_to_reprovision_allowed(self):
        """Can transition from active to reprovision."""
        assert NodeStateMachine.can_transition("active", "reprovision") is True

    def test_reprovision_to_pending_allowed(self):
        """Can transition from reprovision back to pending."""
        assert NodeStateMachine.can_transition("reprovision", "pending") is True

    def test_any_state_to_retired_allowed(self):
        """Can retire from any state."""
        for state in NodeStateMachine.STATES:
            if state != "retired":
                assert NodeStateMachine.can_transition(state, "retired") is True

    def test_retired_cannot_transition(self):
        """Retired state is terminal except to retired."""
        assert NodeStateMachine.can_transition("retired", "discovered") is False
        assert NodeStateMachine.can_transition("retired", "pending") is False

    def test_transition_raises_on_invalid(self):
        """transition() raises InvalidStateTransition for invalid transitions."""
        with pytest.raises(InvalidStateTransition) as exc_info:
            NodeStateMachine.transition("discovered", "active")
        assert "discovered" in str(exc_info.value)
        assert "active" in str(exc_info.value)

    def test_transition_returns_new_state_on_valid(self):
        """transition() returns new state on valid transition."""
        result = NodeStateMachine.transition("discovered", "pending")
        assert result == "pending"

    def test_get_valid_transitions(self):
        """get_valid_transitions returns list of valid next states."""
        valid = NodeStateMachine.get_valid_transitions("active")
        assert "reprovision" in valid
        assert "deprovisioning" in valid
        assert "migrating" in valid
        assert "retired" in valid

    def test_all_states_defined(self):
        """All expected states are defined."""
        expected = {
            "discovered", "pending", "installing", "installed",
            "active", "reprovision", "deprovisioning", "migrating", "retired"
        }
        assert set(NodeStateMachine.STATES) == expected
```

**Step 3: Run tests to verify they fail**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_state_machine.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.core.state_machine'"

**Step 4: Implement state machine**

Create `src/core/state_machine.py`:
```python
"""Node state machine for lifecycle management."""
from typing import ClassVar


class InvalidStateTransition(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: str, to_state: str):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid state transition from '{from_state}' to '{to_state}'"
        )


class NodeStateMachine:
    """State machine for node lifecycle management.

    States:
        discovered: Node appeared via PXE, waiting for admin action
        pending: Workflow assigned, ready for next PXE boot
        installing: OS installation in progress
        installed: Installation complete, ready for local boot
        active: Running from local disk
        reprovision: Marked for reinstallation
        deprovisioning: Secure data erasure in progress
        migrating: Hardware replacement workflow
        retired: Removed from inventory
    """

    STATES: ClassVar[list[str]] = [
        "discovered",
        "pending",
        "installing",
        "installed",
        "active",
        "reprovision",
        "deprovisioning",
        "migrating",
        "retired",
    ]

    TRANSITIONS: ClassVar[dict[str, list[str]]] = {
        "discovered": ["pending"],
        "pending": ["installing"],
        "installing": ["installed"],
        "installed": ["active"],
        "active": ["reprovision", "deprovisioning", "migrating"],
        "reprovision": ["pending"],
        "deprovisioning": ["retired"],
        "migrating": ["active"],
        "retired": [],
    }

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        """Check if a state transition is valid.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if transition is valid, False otherwise
        """
        # Admin can retire from any state
        if to_state == "retired":
            return from_state != "retired"

        return to_state in cls.TRANSITIONS.get(from_state, [])

    @classmethod
    def transition(cls, from_state: str, to_state: str) -> str:
        """Perform a state transition.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            The new state

        Raises:
            InvalidStateTransition: If the transition is not valid
        """
        if not cls.can_transition(from_state, to_state):
            raise InvalidStateTransition(from_state, to_state)
        return to_state

    @classmethod
    def get_valid_transitions(cls, from_state: str) -> list[str]:
        """Get list of valid transitions from a state.

        Args:
            from_state: Current state

        Returns:
            List of valid target states
        """
        valid = list(cls.TRANSITIONS.get(from_state, []))
        # Can always retire (except from retired)
        if from_state != "retired" and "retired" not in valid:
            valid.append("retired")
        return valid
```

**Step 5: Run tests to verify they pass**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_state_machine.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/core/__init__.py src/core/state_machine.py tests/unit/test_state_machine.py
git commit -m "feat: implement node state machine with transition validation"
```

---

## Task 4: Database Models

**Files:**
- Create: `src/db/__init__.py`
- Create: `src/db/models.py`
- Create: `src/db/database.py`

**Step 1: Create db package init**

Create `src/db/__init__.py`:
```python
"""Database module."""
from src.db.database import get_db, init_db, close_db
from src.db.models import Base, Node, DeviceGroup, NodeTag

__all__ = ["get_db", "init_db", "close_db", "Base", "Node", "DeviceGroup", "NodeTag"]
```

**Step 2: Create database connection module**

Create `src/db/database.py`:
```python
"""Database connection and session management."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

engine = create_async_engine(
    settings.database.url,
    echo=settings.database.echo,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database tables."""
    from src.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
```

**Step 3: Create database models**

Create `src/db/models.py`:
```python
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
```

**Step 4: Commit**

```bash
git add src/db/__init__.py src/db/database.py src/db/models.py
git commit -m "feat: add SQLAlchemy database models for Node, DeviceGroup, NodeTag"
```

---

## Task 5: Database Model Tests

**Files:**
- Create: `tests/unit/test_models.py`

**Step 1: Write model tests**

Create `tests/unit/test_models.py`:
```python
"""Tests for database models."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.models import Base, Node, DeviceGroup, NodeTag


@pytest.fixture
def engine():
    """Create in-memory SQLite engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create database session."""
    with Session(engine) as session:
        yield session


class TestNodeModel:
    """Test Node model."""

    def test_create_node_with_defaults(self, session):
        """Create node with default values."""
        node = Node(mac_address="00:11:22:33:44:55")
        session.add(node)
        session.commit()

        assert node.id is not None
        assert node.mac_address == "00:11:22:33:44:55"
        assert node.state == "discovered"
        assert node.arch == "x86_64"
        assert node.boot_mode == "bios"

    def test_create_node_with_hardware_info(self, session):
        """Create node with hardware identification."""
        node = Node(
            mac_address="00:11:22:33:44:55",
            vendor="Dell Inc.",
            model="PowerEdge R740",
            serial_number="ABC123",
            system_uuid="550e8400-e29b-41d4-a716-446655440000",
        )
        session.add(node)
        session.commit()

        assert node.vendor == "Dell Inc."
        assert node.model == "PowerEdge R740"
        assert node.serial_number == "ABC123"

    def test_mac_address_unique(self, session):
        """MAC address must be unique."""
        node1 = Node(mac_address="00:11:22:33:44:55")
        node2 = Node(mac_address="00:11:22:33:44:55")
        session.add(node1)
        session.commit()

        session.add(node2)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()


class TestDeviceGroupModel:
    """Test DeviceGroup model."""

    def test_create_group(self, session):
        """Create device group."""
        group = DeviceGroup(name="webservers", description="Web server nodes")
        session.add(group)
        session.commit()

        assert group.id is not None
        assert group.name == "webservers"
        assert group.auto_provision is False

    def test_group_name_unique(self, session):
        """Group name must be unique."""
        group1 = DeviceGroup(name="webservers")
        group2 = DeviceGroup(name="webservers")
        session.add(group1)
        session.commit()

        session.add(group2)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_node_group_relationship(self, session):
        """Node can belong to a group."""
        group = DeviceGroup(name="webservers")
        node = Node(mac_address="00:11:22:33:44:55", group=group)
        session.add(node)
        session.commit()

        assert node.group_id == group.id
        assert node in group.nodes


class TestNodeTagModel:
    """Test NodeTag model."""

    def test_add_tag_to_node(self, session):
        """Add tag to node."""
        node = Node(mac_address="00:11:22:33:44:55")
        tag = NodeTag(node=node, tag="production")
        session.add(tag)
        session.commit()

        assert tag.id is not None
        assert tag.tag == "production"
        assert tag in node.tags

    def test_node_can_have_multiple_tags(self, session):
        """Node can have multiple tags."""
        node = Node(mac_address="00:11:22:33:44:55")
        tag1 = NodeTag(node=node, tag="production")
        tag2 = NodeTag(node=node, tag="webserver")
        session.add_all([tag1, tag2])
        session.commit()

        assert len(node.tags) == 2

    def test_same_tag_same_node_not_allowed(self, session):
        """Same tag on same node not allowed."""
        node = Node(mac_address="00:11:22:33:44:55")
        tag1 = NodeTag(node=node, tag="production")
        tag2 = NodeTag(node=node, tag="production")
        session.add_all([tag1, tag2])

        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_tags_deleted_with_node(self, session):
        """Tags are deleted when node is deleted."""
        node = Node(mac_address="00:11:22:33:44:55")
        tag = NodeTag(node=node, tag="production")
        session.add(tag)
        session.commit()

        tag_id = tag.id
        session.delete(node)
        session.commit()

        assert session.get(NodeTag, tag_id) is None
```

**Step 2: Run tests**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/unit/test_models.py
git commit -m "test: add unit tests for database models"
```

---

## Task 6: Pydantic API Schemas

**Files:**
- Create: `src/api/schemas.py`

**Step 1: Create Pydantic schemas**

Create `src/api/schemas.py`:
```python
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
```

**Step 2: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat: add Pydantic schemas for API request/response validation"
```

---

## Task 7: Schema Tests

**Files:**
- Create: `tests/unit/test_schemas.py`

**Step 1: Write schema tests**

Create `tests/unit/test_schemas.py`:
```python
"""Tests for API schemas."""
import pytest
from pydantic import ValidationError

from src.api.schemas import (
    NodeCreate,
    NodeUpdate,
    StateTransition,
    TagCreate,
    DeviceGroupCreate,
    NodeReport,
)


class TestNodeCreate:
    """Test NodeCreate schema."""

    def test_valid_node_create(self):
        """Create node with valid data."""
        node = NodeCreate(mac_address="00:11:22:33:44:55")
        assert node.mac_address == "00:11:22:33:44:55"
        assert node.arch == "x86_64"
        assert node.boot_mode == "bios"

    def test_mac_address_normalized(self):
        """MAC address is normalized."""
        node = NodeCreate(mac_address="00-11-22-AA-BB-CC")
        assert node.mac_address == "00:11:22:aa:bb:cc"

    def test_invalid_mac_rejected(self):
        """Invalid MAC address rejected."""
        with pytest.raises(ValidationError) as exc_info:
            NodeCreate(mac_address="invalid")
        assert "Invalid MAC address" in str(exc_info.value)

    def test_invalid_arch_rejected(self):
        """Invalid architecture rejected."""
        with pytest.raises(ValidationError) as exc_info:
            NodeCreate(mac_address="00:11:22:33:44:55", arch="invalid")
        assert "Invalid architecture" in str(exc_info.value)

    def test_invalid_boot_mode_rejected(self):
        """Invalid boot mode rejected."""
        with pytest.raises(ValidationError) as exc_info:
            NodeCreate(mac_address="00:11:22:33:44:55", boot_mode="invalid")
        assert "Invalid boot mode" in str(exc_info.value)

    def test_with_hardware_info(self):
        """Create node with hardware info."""
        node = NodeCreate(
            mac_address="00:11:22:33:44:55",
            vendor="Dell Inc.",
            model="PowerEdge R740",
            serial_number="ABC123",
        )
        assert node.vendor == "Dell Inc."
        assert node.model == "PowerEdge R740"


class TestStateTransition:
    """Test StateTransition schema."""

    def test_valid_state(self):
        """Valid state accepted."""
        transition = StateTransition(state="pending")
        assert transition.state == "pending"

    def test_invalid_state_rejected(self):
        """Invalid state rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StateTransition(state="invalid_state")
        assert "Invalid state" in str(exc_info.value)


class TestTagCreate:
    """Test TagCreate schema."""

    def test_valid_tag(self):
        """Valid tag accepted."""
        tag = TagCreate(tag="production")
        assert tag.tag == "production"

    def test_tag_normalized_lowercase(self):
        """Tag is normalized to lowercase."""
        tag = TagCreate(tag="PRODUCTION")
        assert tag.tag == "production"

    def test_tag_with_special_chars_rejected(self):
        """Tag with invalid characters rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TagCreate(tag="prod@server")
        assert "can only contain" in str(exc_info.value)

    def test_empty_tag_rejected(self):
        """Empty tag rejected."""
        with pytest.raises(ValidationError):
            TagCreate(tag="")


class TestDeviceGroupCreate:
    """Test DeviceGroupCreate schema."""

    def test_valid_group(self):
        """Valid group accepted."""
        group = DeviceGroupCreate(name="webservers")
        assert group.name == "webservers"
        assert group.auto_provision is False

    def test_empty_name_rejected(self):
        """Empty name rejected."""
        with pytest.raises(ValidationError):
            DeviceGroupCreate(name="")


class TestNodeReport:
    """Test NodeReport schema."""

    def test_valid_report(self):
        """Valid report accepted."""
        report = NodeReport(
            mac_address="00:11:22:33:44:55",
            ip_address="192.168.1.100",
            hostname="webserver-01",
        )
        assert report.mac_address == "00:11:22:33:44:55"
        assert report.ip_address == "192.168.1.100"

    def test_mac_normalized(self):
        """MAC address normalized."""
        report = NodeReport(mac_address="00-11-22-AA-BB-CC")
        assert report.mac_address == "00:11:22:aa:bb:cc"
```

**Step 2: Run tests**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_schemas.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/unit/test_schemas.py
git commit -m "test: add unit tests for API schemas"
```

---

## Task 8: Node CRUD Endpoints

**Files:**
- Create: `src/api/routes/nodes.py`

**Step 1: Create node routes**

Create `src/api/routes/nodes.py`:
```python
"""Node management API endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    NodeCreate,
    NodeResponse,
    NodeUpdate,
    StateTransition,
    TagCreate,
)
from src.core.state_machine import InvalidStateTransition, NodeStateMachine
from src.db.database import get_db
from src.db.models import Node, NodeTag

router = APIRouter()


@router.get("/nodes", response_model=ApiListResponse[NodeResponse])
async def list_nodes(
    state: str | None = Query(None, description="Filter by state"),
    group_id: str | None = Query(None, description="Filter by group ID"),
    tag: str | None = Query(None, description="Filter by tag"),
    db: AsyncSession = Depends(get_db),
):
    """List all nodes with optional filtering."""
    query = select(Node).options(selectinload(Node.tags))

    if state:
        query = query.where(Node.state == state)
    if group_id:
        query = query.where(Node.group_id == group_id)
    if tag:
        query = query.join(Node.tags).where(NodeTag.tag == tag.lower())

    result = await db.execute(query)
    nodes = result.scalars().unique().all()

    return ApiListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes),
    )


@router.post("/nodes", response_model=ApiResponse[NodeResponse], status_code=201)
async def create_node(
    node_data: NodeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new node."""
    # Check for existing MAC
    existing = await db.execute(
        select(Node).where(Node.mac_address == node_data.mac_address)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Node with MAC {node_data.mac_address} already exists",
        )

    node = Node(
        mac_address=node_data.mac_address,
        hostname=node_data.hostname,
        arch=node_data.arch,
        boot_mode=node_data.boot_mode,
        group_id=node_data.group_id,
        vendor=node_data.vendor,
        model=node_data.model,
        serial_number=node_data.serial_number,
        system_uuid=node_data.system_uuid,
    )
    db.add(node)
    await db.flush()

    # Reload with tags relationship
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message="Node registered successfully",
    )


@router.get("/nodes/{node_id}", response_model=ApiResponse[NodeResponse])
async def get_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get node details by ID."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return ApiResponse(data=NodeResponse.from_node(node))


@router.patch("/nodes/{node_id}", response_model=ApiResponse[NodeResponse])
async def update_node(
    node_id: str,
    node_data: NodeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update node metadata."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Update only provided fields
    update_data = node_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(node, field, value)

    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message="Node updated successfully",
    )


@router.patch("/nodes/{node_id}/state", response_model=ApiResponse[NodeResponse])
async def transition_node_state(
    node_id: str,
    transition: StateTransition,
    db: AsyncSession = Depends(get_db),
):
    """Transition node to a new state."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    try:
        new_state = NodeStateMachine.transition(node.state, transition.state)
        node.state = new_state
        await db.flush()
        await db.refresh(node, ["tags"])

        return ApiResponse(
            data=NodeResponse.from_node(node),
            message=f"Node transitioned to {new_state}",
        )
    except InvalidStateTransition as e:
        valid = NodeStateMachine.get_valid_transitions(node.state)
        raise HTTPException(
            status_code=400,
            detail=f"{str(e)}. Valid transitions: {valid}",
        )


@router.delete("/nodes/{node_id}", response_model=ApiResponse[NodeResponse])
async def retire_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retire a node (sets state to retired)."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    try:
        node.state = NodeStateMachine.transition(node.state, "retired")
        await db.flush()
        await db.refresh(node, ["tags"])

        return ApiResponse(
            data=NodeResponse.from_node(node),
            message="Node retired",
        )
    except InvalidStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/{node_id}/tags", response_model=ApiResponse[NodeResponse])
async def add_node_tag(
    node_id: str,
    tag_data: TagCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a tag to a node."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Check if tag already exists
    existing_tags = [t.tag for t in node.tags]
    if tag_data.tag in existing_tags:
        raise HTTPException(
            status_code=409,
            detail=f"Tag '{tag_data.tag}' already exists on node",
        )

    tag = NodeTag(node_id=node_id, tag=tag_data.tag)
    db.add(tag)
    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message=f"Tag '{tag_data.tag}' added",
    )


@router.delete("/nodes/{node_id}/tags/{tag}", response_model=ApiResponse[NodeResponse])
async def remove_node_tag(
    node_id: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a tag from a node."""
    result = await db.execute(
        select(Node).options(selectinload(Node.tags)).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Find and delete the tag
    tag_lower = tag.lower()
    tag_to_delete = None
    for t in node.tags:
        if t.tag == tag_lower:
            tag_to_delete = t
            break

    if not tag_to_delete:
        raise HTTPException(
            status_code=404,
            detail=f"Tag '{tag}' not found on node",
        )

    await db.delete(tag_to_delete)
    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message=f"Tag '{tag}' removed",
    )
```

**Step 2: Commit**

```bash
git add src/api/routes/nodes.py
git commit -m "feat: implement node CRUD API endpoints"
```

---

## Task 9: Device Group Endpoints

**Files:**
- Create: `src/api/routes/groups.py`

**Step 1: Create group routes**

Create `src/api/routes/groups.py`:
```python
"""Device group management API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    DeviceGroupCreate,
    DeviceGroupResponse,
    DeviceGroupUpdate,
    NodeResponse,
)
from src.db.database import get_db
from src.db.models import DeviceGroup, Node

router = APIRouter()


@router.get("/groups", response_model=ApiListResponse[DeviceGroupResponse])
async def list_groups(
    db: AsyncSession = Depends(get_db),
):
    """List all device groups."""
    # Get groups with node counts
    query = select(DeviceGroup)
    result = await db.execute(query)
    groups = result.scalars().all()

    # Get node counts
    count_query = (
        select(Node.group_id, func.count(Node.id))
        .where(Node.group_id.isnot(None))
        .group_by(Node.group_id)
    )
    count_result = await db.execute(count_query)
    counts = dict(count_result.all())

    return ApiListResponse(
        data=[
            DeviceGroupResponse.from_group(g, node_count=counts.get(g.id, 0))
            for g in groups
        ],
        total=len(groups),
    )


@router.post("/groups", response_model=ApiResponse[DeviceGroupResponse], status_code=201)
async def create_group(
    group_data: DeviceGroupCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new device group."""
    # Check for existing name
    existing = await db.execute(
        select(DeviceGroup).where(DeviceGroup.name == group_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Group '{group_data.name}' already exists",
        )

    group = DeviceGroup(
        name=group_data.name,
        description=group_data.description,
        default_workflow_id=group_data.default_workflow_id,
        auto_provision=group_data.auto_provision,
    )
    db.add(group)
    await db.flush()

    return ApiResponse(
        data=DeviceGroupResponse.from_group(group),
        message="Group created successfully",
    )


@router.get("/groups/{group_id}", response_model=ApiResponse[DeviceGroupResponse])
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get device group details."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Get node count
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    return ApiResponse(data=DeviceGroupResponse.from_group(group, node_count=node_count))


@router.patch("/groups/{group_id}", response_model=ApiResponse[DeviceGroupResponse])
async def update_group(
    group_id: str,
    group_data: DeviceGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update device group."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check for name conflict if updating name
    if group_data.name and group_data.name != group.name:
        existing = await db.execute(
            select(DeviceGroup).where(DeviceGroup.name == group_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Group '{group_data.name}' already exists",
            )

    # Update only provided fields
    update_data = group_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)

    await db.flush()

    # Get node count
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    return ApiResponse(
        data=DeviceGroupResponse.from_group(group, node_count=node_count),
        message="Group updated successfully",
    )


@router.delete("/groups/{group_id}", response_model=ApiResponse[dict])
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete device group."""
    result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check for nodes in group
    count_query = select(func.count(Node.id)).where(Node.group_id == group_id)
    count_result = await db.execute(count_query)
    node_count = count_result.scalar() or 0

    if node_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete group with {node_count} node(s). Remove nodes first.",
        )

    await db.delete(group)
    await db.flush()

    return ApiResponse(
        data={"id": group_id},
        message="Group deleted successfully",
    )


@router.get("/groups/{group_id}/nodes", response_model=ApiListResponse[NodeResponse])
async def list_group_nodes(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List nodes in a device group."""
    # Verify group exists
    group_result = await db.execute(
        select(DeviceGroup).where(DeviceGroup.id == group_id)
    )
    if not group_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Group not found")

    # Get nodes
    query = (
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.group_id == group_id)
    )
    result = await db.execute(query)
    nodes = result.scalars().all()

    return ApiListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes),
    )
```

**Step 2: Commit**

```bash
git add src/api/routes/groups.py
git commit -m "feat: implement device group API endpoints"
```

---

## Task 10: Update Boot Endpoint with Database

**Files:**
- Modify: `src/api/routes/boot.py`

**Step 1: Update boot.py with database lookup**

Replace contents of `src/api/routes/boot.py`:
```python
"""Boot API endpoint for iPXE."""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.database import get_db
from src.db.models import Node

router = APIRouter()

MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def normalize_mac(mac: str) -> str:
    """Normalize MAC address to colon-separated lowercase."""
    return mac.replace("-", ":").lower()


def validate_mac(mac: str) -> str:
    """Validate and normalize MAC address."""
    if not MAC_PATTERN.match(mac):
        raise HTTPException(status_code=400, detail=f"Invalid MAC address: {mac}")
    return normalize_mac(mac)


def generate_local_boot_script() -> str:
    """Generate iPXE script for local boot."""
    return """#!ipxe
# PureBoot - Boot from local disk
echo Booting from local disk...
exit
"""


def generate_discovery_script(mac: str, server: str) -> str:
    """Generate iPXE script for discovered node."""
    return f"""#!ipxe
# PureBoot - Node discovered
# MAC: {mac}
echo
echo Node registered with PureBoot server.
echo Waiting for provisioning assignment...
echo
echo Booting from local disk in 10 seconds...
echo Press any key to enter iPXE shell.
sleep 10 || shell
exit
"""


def generate_pending_script(node: Node, server: str) -> str:
    """Generate iPXE script for node pending installation."""
    # TODO: Generate actual installation script from workflow
    return f"""#!ipxe
# PureBoot - Installation pending
# MAC: {node.mac_address}
# Workflow: {node.workflow_id or 'none'}
echo
echo Node ready for installation.
echo Workflow: {node.workflow_id or 'Not assigned'}
echo
echo Installation will begin on next boot with assigned workflow.
echo Booting from local disk...
sleep 5
exit
"""


@router.get("/boot", response_class=PlainTextResponse)
async def get_boot_script(
    mac: str,
    request: Request,
    vendor: str | None = Query(None, description="Hardware vendor"),
    model: str | None = Query(None, description="Hardware model"),
    serial: str | None = Query(None, description="Serial number"),
    uuid: str | None = Query(None, description="System UUID"),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Return iPXE boot script for a node.

    The script returned depends on the node's current state:
    - Unknown node: Register as discovered (if auto_register), boot local
    - discovered: Boot local (waiting for assignment)
    - pending: Return installation script
    - installing: Boot local (installation in progress)
    - installed/active: Boot local

    Args:
        mac: MAC address of the booting node
        vendor: Hardware vendor (from iPXE ${manufacturer})
        model: Hardware model (from iPXE ${product})
        serial: Serial number (from iPXE ${serial})
        uuid: System UUID (from iPXE ${uuid})
        request: FastAPI request object
        db: Database session

    Returns:
        iPXE script as plain text
    """
    mac = validate_mac(mac)
    client_ip = request.client.host if request.client else None
    server = f"http://{settings.host}:{settings.port}"

    # Look up node by MAC
    result = await db.execute(select(Node).where(Node.mac_address == mac))
    node = result.scalar_one_or_none()

    if not node:
        # Node not found
        if not settings.registration.auto_register:
            # Auto-registration disabled, just boot local
            return generate_local_boot_script()

        # Auto-register new node
        node = Node(
            mac_address=mac,
            ip_address=client_ip,
            vendor=vendor,
            model=model,
            serial_number=serial,
            system_uuid=uuid,
            group_id=settings.registration.default_group_id,
        )
        db.add(node)
        await db.flush()
        return generate_discovery_script(mac, server)

    # Update last seen and hardware info
    node.last_seen_at = datetime.utcnow()
    if client_ip:
        node.ip_address = client_ip
    if vendor and not node.vendor:
        node.vendor = vendor
    if model and not node.model:
        node.model = model
    if serial and not node.serial_number:
        node.serial_number = serial
    if uuid and not node.system_uuid:
        node.system_uuid = uuid

    # Return boot script based on state
    match node.state:
        case "discovered":
            return generate_discovery_script(mac, server)
        case "pending":
            return generate_pending_script(node, server)
        case "installing":
            # Let installation continue, boot local
            return generate_local_boot_script()
        case "installed" | "active" | "retired":
            return generate_local_boot_script()
        case _:
            # Default to local boot for unknown states
            return generate_local_boot_script()
```

**Step 2: Commit**

```bash
git add src/api/routes/boot.py
git commit -m "feat: update boot endpoint with database lookup and auto-registration"
```

---

## Task 11: Report Endpoint

**Files:**
- Modify: `src/api/routes/nodes.py` (add report endpoint)

**Step 1: Add report endpoint to nodes.py**

Add to end of `src/api/routes/nodes.py`:
```python
@router.post("/report", response_model=ApiResponse[NodeResponse])
async def report_node_status(
    report: NodeReport,
    db: AsyncSession = Depends(get_db),
):
    """Report node status and update information.

    Called by nodes to report their current status and update
    hardware information after OS boot.
    """
    # Look up node by MAC
    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.mac_address == report.mac_address)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node with MAC {report.mac_address} not found",
        )

    # Update node information
    node.last_seen_at = datetime.utcnow()

    if report.ip_address:
        node.ip_address = report.ip_address
    if report.hostname:
        node.hostname = report.hostname
    if report.vendor:
        node.vendor = report.vendor
    if report.model:
        node.model = report.model
    if report.serial_number:
        node.serial_number = report.serial_number
    if report.system_uuid:
        node.system_uuid = report.system_uuid

    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message="Status reported successfully",
    )
```

**Step 2: Add NodeReport import**

Add `NodeReport` to the imports at the top of `src/api/routes/nodes.py`:
```python
from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    NodeCreate,
    NodeReport,
    NodeResponse,
    NodeUpdate,
    StateTransition,
    TagCreate,
)
```

**Step 3: Commit**

```bash
git add src/api/routes/nodes.py
git commit -m "feat: add node status report endpoint"
```

---

## Task 12: Update Main App with Routes

**Files:**
- Modify: `src/main.py`

**Step 1: Update main.py to include new routes and database init**

Update imports and lifespan in `src/main.py`:

Add to imports:
```python
from src.api.routes import boot, ipxe, nodes, groups
from src.db.database import init_db, close_db
```

Update lifespan function to init/close database:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global tftp_server, dhcp_proxy

    logger.info("Starting PureBoot...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # ... rest of existing startup code ...

    yield

    # Cleanup
    logger.info("Shutting down PureBoot...")

    if tftp_server:
        await tftp_server.stop()

    if dhcp_proxy:
        await dhcp_proxy.stop()

    await close_db()
    logger.info("Database connections closed")
```

Add new routers after existing ones:
```python
# Mount API routes
app.include_router(boot.router, prefix="/api/v1", tags=["boot"])
app.include_router(ipxe.router, prefix="/api/v1", tags=["ipxe"])
app.include_router(nodes.router, prefix="/api/v1", tags=["nodes"])
app.include_router(groups.router, prefix="/api/v1", tags=["groups"])
```

**Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: register node and group routes, init database on startup"
```

---

## Task 13: API Integration Tests

**Files:**
- Create: `tests/integration/test_nodes_api.py`
- Create: `tests/integration/test_groups_api.py`

**Step 1: Create test fixtures**

Create `tests/conftest.py`:
```python
"""Shared test fixtures."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.db.models import Base
from src.db.database import get_db
from src.main import app


@pytest.fixture
def test_db():
    """Create a test database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    Base.metadata.drop_all(engine)


@pytest.fixture
def client(test_db):
    """Create test client with overridden database."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
```

**Step 2: Create node API tests**

Create `tests/integration/test_nodes_api.py`:
```python
"""Integration tests for node API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestNodesCRUD:
    """Test node CRUD operations."""

    def test_create_node(self, client: TestClient):
        """Create a new node."""
        response = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["mac_address"] == "00:11:22:33:44:55"
        assert data["data"]["state"] == "discovered"

    def test_create_node_with_hardware_info(self, client: TestClient):
        """Create node with hardware information."""
        response = client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "00:11:22:33:44:55",
                "vendor": "Dell Inc.",
                "model": "PowerEdge R740",
                "serial_number": "ABC123",
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["vendor"] == "Dell Inc."
        assert data["model"] == "PowerEdge R740"
        assert data["serial_number"] == "ABC123"

    def test_create_duplicate_mac_fails(self, client: TestClient):
        """Cannot create node with duplicate MAC."""
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:55"})
        response = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        assert response.status_code == 409

    def test_list_nodes(self, client: TestClient):
        """List all nodes."""
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:55"})
        client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:66"})

        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_get_node(self, client: TestClient):
        """Get node by ID."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == node_id

    def test_get_nonexistent_node(self, client: TestClient):
        """Get nonexistent node returns 404."""
        response = client.get("/api/v1/nodes/nonexistent-id")
        assert response.status_code == 404

    def test_update_node(self, client: TestClient):
        """Update node metadata."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/nodes/{node_id}",
            json={"hostname": "webserver-01"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["hostname"] == "webserver-01"

    def test_retire_node(self, client: TestClient):
        """Retire a node."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.delete(f"/api/v1/nodes/{node_id}")
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "retired"


class TestNodeStateTransitions:
    """Test node state transitions."""

    def test_valid_transition(self, client: TestClient):
        """Valid state transition succeeds."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/nodes/{node_id}/state",
            json={"state": "pending"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "pending"

    def test_invalid_transition_fails(self, client: TestClient):
        """Invalid state transition fails."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/nodes/{node_id}/state",
            json={"state": "active"},  # Can't go discovered -> active
        )
        assert response.status_code == 400
        assert "Invalid state transition" in response.json()["detail"]


class TestNodeTags:
    """Test node tagging."""

    def test_add_tag(self, client: TestClient):
        """Add tag to node."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]

        response = client.post(
            f"/api/v1/nodes/{node_id}/tags",
            json={"tag": "production"},
        )
        assert response.status_code == 200
        assert "production" in response.json()["data"]["tags"]

    def test_remove_tag(self, client: TestClient):
        """Remove tag from node."""
        create_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = create_resp.json()["data"]["id"]
        client.post(f"/api/v1/nodes/{node_id}/tags", json={"tag": "production"})

        response = client.delete(f"/api/v1/nodes/{node_id}/tags/production")
        assert response.status_code == 200
        assert "production" not in response.json()["data"]["tags"]

    def test_filter_by_tag(self, client: TestClient):
        """Filter nodes by tag."""
        # Create two nodes
        resp1 = client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:55"})
        resp2 = client.post("/api/v1/nodes", json={"mac_address": "00:11:22:33:44:66"})
        node1_id = resp1.json()["data"]["id"]

        # Tag only first node
        client.post(f"/api/v1/nodes/{node1_id}/tags", json={"tag": "production"})

        # Filter by tag
        response = client.get("/api/v1/nodes?tag=production")
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["data"][0]["id"] == node1_id
```

**Step 3: Create group API tests**

Create `tests/integration/test_groups_api.py`:
```python
"""Integration tests for device group API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestGroupsCRUD:
    """Test device group CRUD operations."""

    def test_create_group(self, client: TestClient):
        """Create a new device group."""
        response = client.post(
            "/api/v1/groups",
            json={"name": "webservers", "description": "Web servers"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "webservers"

    def test_create_duplicate_name_fails(self, client: TestClient):
        """Cannot create group with duplicate name."""
        client.post("/api/v1/groups", json={"name": "webservers"})
        response = client.post("/api/v1/groups", json={"name": "webservers"})
        assert response.status_code == 409

    def test_list_groups(self, client: TestClient):
        """List all groups."""
        client.post("/api/v1/groups", json={"name": "webservers"})
        client.post("/api/v1/groups", json={"name": "databases"})

        response = client.get("/api/v1/groups")
        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_get_group(self, client: TestClient):
        """Get group by ID."""
        create_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/groups/{group_id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == group_id

    def test_update_group(self, client: TestClient):
        """Update group."""
        create_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/groups/{group_id}",
            json={"description": "Updated description"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["description"] == "Updated description"

    def test_delete_empty_group(self, client: TestClient):
        """Delete empty group succeeds."""
        create_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = create_resp.json()["data"]["id"]

        response = client.delete(f"/api/v1/groups/{group_id}")
        assert response.status_code == 200

    def test_delete_group_with_nodes_fails(self, client: TestClient):
        """Cannot delete group with nodes."""
        # Create group
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        # Create node in group
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55", "group_id": group_id},
        )

        # Try to delete group
        response = client.delete(f"/api/v1/groups/{group_id}")
        assert response.status_code == 400
        assert "Cannot delete group" in response.json()["detail"]


class TestGroupNodes:
    """Test group-node relationships."""

    def test_list_group_nodes(self, client: TestClient):
        """List nodes in a group."""
        # Create group
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        # Create nodes
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55", "group_id": group_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:66", "group_id": group_id},
        )
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:77"},  # No group
        )

        response = client.get(f"/api/v1/groups/{group_id}/nodes")
        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_group_node_count(self, client: TestClient):
        """Group shows correct node count."""
        # Create group
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        # Create node in group
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55", "group_id": group_id},
        )

        # Check node count
        response = client.get(f"/api/v1/groups/{group_id}")
        assert response.json()["data"]["node_count"] == 1

    def test_assign_node_to_group(self, client: TestClient):
        """Assign existing node to group."""
        # Create group and node
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]
        node_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node_id = node_resp.json()["data"]["id"]

        # Assign node to group
        response = client.patch(
            f"/api/v1/nodes/{node_id}",
            json={"group_id": group_id},
        )
        assert response.status_code == 200
        assert response.json()["data"]["group_id"] == group_id
```

**Step 4: Run integration tests**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/integration/test_nodes_api.py tests/integration/test_groups_api.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add tests/conftest.py tests/integration/test_nodes_api.py tests/integration/test_groups_api.py
git commit -m "test: add integration tests for node and group API endpoints"
```

---

## Task 14: Final Verification

**Step 1: Run all tests**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest -v`
Expected: All tests PASS

**Step 2: Verify API docs**

The FastAPI app should now have Swagger documentation at `/docs` showing all endpoints.

**Step 3: Final commit with issue reference**

```bash
git add -A
git commit -m "feat: complete Controller API implementation

Implements issue #2 with:
- Node CRUD with state machine enforcement
- Device groups with shared settings
- Node tags for flexible categorization
- Hardware identification (vendor, model, serial)
- Configurable auto-registration
- Boot endpoint with database lookup
- Status report endpoint

Closes #2"
```

---

## Summary

**Files created:**
- `src/core/__init__.py`
- `src/core/state_machine.py`
- `src/db/__init__.py`
- `src/db/database.py`
- `src/db/models.py`
- `src/api/schemas.py`
- `src/api/routes/nodes.py`
- `src/api/routes/groups.py`
- `tests/conftest.py`
- `tests/unit/test_state_machine.py`
- `tests/unit/test_models.py`
- `tests/unit/test_schemas.py`
- `tests/integration/test_nodes_api.py`
- `tests/integration/test_groups_api.py`

**Files modified:**
- `requirements.txt`
- `pyproject.toml`
- `src/config/settings.py`
- `src/api/routes/boot.py`
- `src/main.py`

**Deferred:**
- Alembic migrations (use `init_db()` for now)
- #9 Four-Eye Approval
- #10 Hierarchical Device Groups
