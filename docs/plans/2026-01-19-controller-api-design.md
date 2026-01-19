# Controller API with Node Management - Design Document

**Issue:** #2
**Date:** 2026-01-19
**Status:** Approved

## Overview

Implement the FastAPI-based Controller API for node lifecycle management, including database persistence, state machine enforcement, and device groups.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | SQLite (dev) → PostgreSQL (prod) | Start simple, design for migration |
| ORM | SQLAlchemy + Alembic | Industry standard, async support, migrations |
| Auto-registration | Configurable | Flexibility for different security postures |
| Device groups | Single group + tags | Start simple, hierarchy deferred to #10 |
| Four-Eye approval | Deferred to #9 | Focus on core functionality first |

## Project Structure

```
src/
├── db/
│   ├── __init__.py
│   ├── database.py          # Database connection, session management
│   └── models.py            # SQLAlchemy models
├── api/
│   ├── routes/
│   │   ├── nodes.py         # Node CRUD endpoints
│   │   ├── groups.py        # Device group endpoints
│   │   └── boot.py          # Update with DB lookup
│   └── schemas.py           # Pydantic request/response models
├── core/
│   ├── __init__.py
│   └── state_machine.py     # State transition logic
└── config/
    └── settings.py          # Add database + registration settings
```

Alembic migrations will be configured at project root with `alembic/` directory.

## Database Models

### Node

```python
class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mac_address: Mapped[str] = mapped_column(String(17), unique=True, index=True)
    hostname: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    state: Mapped[str] = mapped_column(String(20), default="discovered")
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

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column()
```

### DeviceGroup

```python
class DeviceGroup(Base):
    __tablename__ = "device_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))

    # Default settings
    default_workflow_id: Mapped[str | None] = mapped_column(String(36))
    auto_provision: Mapped[bool] = mapped_column(default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### NodeTag (for multiple tags per node)

```python
class NodeTag(Base):
    __tablename__ = "node_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    tag: Mapped[str] = mapped_column(String(50), index=True)

    __table_args__ = (UniqueConstraint("node_id", "tag"),)
```

## State Machine

### States

| State | Description |
|-------|-------------|
| discovered | Node appeared via PXE, waiting for admin action |
| pending | Workflow assigned, ready for next PXE boot |
| installing | OS installation in progress |
| installed | Installation complete, ready for local boot |
| active | Running from local disk |
| reprovision | Marked for reinstallation |
| deprovisioning | Secure data erasure in progress |
| migrating | Hardware replacement workflow |
| retired | Removed from inventory |

### Valid Transitions

```
discovered    → pending
pending       → installing
installing    → installed
installed     → active
active        → reprovision
active        → deprovisioning
active        → migrating
reprovision   → pending
deprovisioning → retired
migrating     → active
*             → retired (admin override)
```

### Implementation

```python
class NodeStateMachine:
    TRANSITIONS = {
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
        if to_state == "retired":  # Admin can retire from any state
            return True
        return to_state in cls.TRANSITIONS.get(from_state, [])

    @classmethod
    def transition(cls, from_state: str, to_state: str) -> str:
        if not cls.can_transition(from_state, to_state):
            raise InvalidStateTransition(from_state, to_state)
        return to_state
```

## API Endpoints

### Node Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/nodes` | List nodes (filter by state, group, tag) |
| POST | `/api/v1/nodes` | Register node manually |
| GET | `/api/v1/nodes/{id}` | Get node by ID |
| PATCH | `/api/v1/nodes/{id}` | Update node metadata |
| PATCH | `/api/v1/nodes/{id}/state` | Transition state |
| DELETE | `/api/v1/nodes/{id}` | Retire node |
| POST | `/api/v1/nodes/{id}/tags` | Add tag to node |
| DELETE | `/api/v1/nodes/{id}/tags/{tag}` | Remove tag from node |

### Device Groups

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/groups` | List device groups |
| POST | `/api/v1/groups` | Create group |
| GET | `/api/v1/groups/{id}` | Get group details |
| PATCH | `/api/v1/groups/{id}` | Update group |
| DELETE | `/api/v1/groups/{id}` | Delete group |
| GET | `/api/v1/groups/{id}/nodes` | List nodes in group |

### Provisioning

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/boot?mac={mac}` | Get boot instructions |
| POST | `/api/v1/report` | Node status reporting |

## Pydantic Schemas

### Request Schemas

```python
class NodeCreate(BaseModel):
    mac_address: str
    hostname: str | None = None
    arch: str = "x86_64"
    boot_mode: str = "bios"
    group_id: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None

class NodeUpdate(BaseModel):
    hostname: str | None = None
    workflow_id: str | None = None
    group_id: str | None = None

class StateTransition(BaseModel):
    state: str

class NodeReport(BaseModel):
    mac_address: str
    ip_address: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    system_uuid: str | None = None
    state_info: dict | None = None  # Installation progress, etc.

class DeviceGroupCreate(BaseModel):
    name: str
    description: str | None = None
    default_workflow_id: str | None = None
    auto_provision: bool = False

class DeviceGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    default_workflow_id: str | None = None
    auto_provision: bool | None = None
```

### Response Schemas

```python
class NodeResponse(BaseModel):
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
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

class ApiResponse[T](BaseModel):
    success: bool = True
    data: T
    message: str | None = None

class PaginatedResponse[T](BaseModel):
    success: bool = True
    data: list[T]
    total: int
    page: int
    page_size: int
```

## Configuration

### New Settings

```python
class DatabaseSettings(BaseModel):
    url: str = "sqlite+aiosqlite:///./pureboot.db"
    echo: bool = False

class RegistrationSettings(BaseModel):
    auto_register: bool = True
    default_group_id: str | None = None
```

## Boot Logic

```
GET /api/v1/boot?mac={mac}&vendor={vendor}&model={model}&serial={serial}&uuid={uuid}

1. Validate MAC address
2. Look up node by MAC
3. If not found:
   - If auto_register=True: Create in 'discovered' state with hardware info
   - If auto_register=False: Return local boot script
4. Update last_seen_at and hardware info if provided
5. Return boot script based on state:
   - discovered: Local boot (waiting for assignment)
   - pending: Installation script from workflow
   - installing: Local boot (let install continue)
   - installed/active: Local boot
   - retired: Local boot
```

## Implementation Order

1. Database layer (`db/database.py`, `db/models.py`)
2. Alembic setup and initial migration
3. State machine (`core/state_machine.py`)
4. Pydantic schemas (`api/schemas.py`)
5. Node CRUD endpoints (`api/routes/nodes.py`)
6. Device group endpoints (`api/routes/groups.py`)
7. Update boot endpoint with DB lookup
8. Report endpoint
9. Tests

## Future Work

- #9: Four-Eye Approval System
- #10: Hierarchical Device Groups
