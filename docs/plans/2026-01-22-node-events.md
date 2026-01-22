# Node Events Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance node reporting with full lifecycle events, NodeEvent audit model, and installation timeout detection.

**Architecture:** Extend existing NodeReport schema with event types, add NodeEvent model for event logging, update report endpoint to handle all events and trigger state transitions, add timeout detection in boot endpoint.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, SQLite/PostgreSQL

---

## Task 1: Add NodeEvent Model

**Files:**
- Modify: `src/db/models.py` (add after NodeStateLog class, around line 114)

**Step 1: Add NodeEvent model**

Add after the `NodeStateLog` class in `src/db/models.py`:

```python
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
    node: Mapped["Node"] = relationship()
```

**Step 2: Add events relationship to Node model**

In the `Node` class, add after the `state_logs` relationship (around line 88):

```python
    # Event log relationship
    events: Mapped[list["NodeEvent"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )
```

**Step 3: Update NodeEvent relationship back_populates**

Change the NodeEvent relationship to:

```python
    node: Mapped["Node"] = relationship(back_populates="events")
```

**Step 4: Commit**

```bash
git add src/db/models.py
git commit -m "feat(db): add NodeEvent model for lifecycle event logging"
```

---

## Task 2: Add Install Timeout Setting

**Files:**
- Modify: `src/config/settings.py` (add to Settings class)

**Step 1: Add install_timeout_minutes setting**

In `src/config/settings.py`, add to the `Settings` class after `workflows_dir`:

```python
    # Installation timeout in minutes (0 = disabled)
    install_timeout_minutes: int = 60
```

**Step 2: Commit**

```bash
git add src/config/settings.py
git commit -m "feat(config): add install_timeout_minutes setting"
```

---

## Task 3: Add installed→active Transition

**Files:**
- Modify: `src/core/state_machine.py`

**Step 1: Read current state machine**

Read the file to find the VALID_TRANSITIONS dict.

**Step 2: Add installed→active transition**

Update the "installed" entry to include "active":

```python
    "installed": ["active", "reprovision", "retired"],
```

**Step 3: Commit**

```bash
git add src/core/state_machine.py
git commit -m "feat(state-machine): add installed to active transition"
```

---

## Task 4: Extend NodeReport Schema

**Files:**
- Modify: `src/api/schemas.py` (update NodeReport class)

**Step 1: Update NodeReport schema**

Replace the existing `NodeReport` class with:

```python
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
```

**Step 2: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat(api): extend NodeReport schema with event types"
```

---

## Task 5: Add NodeEventResponse Schema

**Files:**
- Modify: `src/api/schemas.py` (add after NodeReport)

**Step 1: Add NodeEventResponse schema**

Add after the `NodeReport` class:

```python
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
```

**Step 2: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat(api): add NodeEventResponse schema"
```

---

## Task 6: Create Event Logging Service

**Files:**
- Create: `src/core/event_service.py`

**Step 1: Create EventService**

Create `src/core/event_service.py`:

```python
"""Service for logging node lifecycle events."""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Node, NodeEvent

logger = logging.getLogger(__name__)


class EventService:
    """Log node lifecycle events to the database."""

    @staticmethod
    async def log_event(
        db: AsyncSession,
        node: Node,
        event_type: str,
        status: str = "success",
        message: str | None = None,
        progress: int | None = None,
        metadata: dict | None = None,
        ip_address: str | None = None,
    ) -> NodeEvent:
        """
        Log a node lifecycle event.

        Args:
            db: Database session
            node: Node the event belongs to
            event_type: Type of event (boot_started, install_complete, etc.)
            status: Event status (success, failed, in_progress)
            message: Optional message
            progress: Optional progress percentage (0-100)
            metadata: Optional metadata dict
            ip_address: Client IP address

        Returns:
            Created NodeEvent
        """
        event = NodeEvent(
            node_id=node.id,
            event_type=event_type,
            status=status,
            message=message,
            progress=progress,
            metadata_json=json.dumps(metadata) if metadata else None,
            ip_address=ip_address,
        )
        db.add(event)

        logger.info(
            f"Node {node.id} ({node.mac_address}) event: {event_type} ({status})"
        )

        return event
```

**Step 2: Commit**

```bash
git add src/core/event_service.py
git commit -m "feat(core): add EventService for logging node events"
```

---

## Task 7: Update Report Endpoint with Event Handling

**Files:**
- Modify: `src/api/routes/nodes.py`

**Step 1: Add imports**

Add to imports at top of file:

```python
from src.core.event_service import EventService
from src.db.models import NodeEvent
```

**Step 2: Update report_node_status function**

Replace the `report_node_status` function with enhanced version that handles both new event-based reporting and legacy installation_status:

```python
@router.post("/report", response_model=ApiResponse[NodeResponse])
async def report_node_status(
    report: NodeReport,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Report node status and update information.

    Called by nodes to report their current status, update
    hardware information, and report installation progress.

    Supports both:
    - New event-based reporting (event field)
    - Legacy installation_status reporting (backwards compatible)
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

    # Get client IP
    client_ip = request.client.host if request.client else report.ip_address

    # Update node information
    node.last_seen_at = datetime.now(timezone.utc)

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

    message = "Status reported successfully"

    # Handle new event-based reporting
    if report.event:
        message = await _handle_event(db, node, report, client_ip)

    # Handle legacy installation_status (backwards compatibility)
    elif report.installation_status:
        message = await _handle_legacy_installation_status(db, node, report, client_ip)

    await db.flush()
    await db.refresh(node)

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message=message,
    )


async def _handle_event(
    db: AsyncSession,
    node: Node,
    report: NodeReport,
    client_ip: str | None,
) -> str:
    """Handle event-based reporting."""
    event_type = report.event
    message = "Event logged"

    # Log the event
    await EventService.log_event(
        db=db,
        node=node,
        event_type=event_type,
        status=report.status,
        message=report.message,
        progress=report.installation_progress,
        metadata=report.event_metadata,
        ip_address=client_ip,
    )

    # Handle state transitions based on event
    match event_type:
        case "boot_started":
            message = "Boot started event logged"

        case "install_started":
            if node.state == "pending":
                await StateTransitionService.transition(
                    db=db,
                    node=node,
                    to_state="installing",
                    triggered_by="node_report",
                )
                node.install_attempts = 0
                message = "Installation started"

        case "install_progress":
            message = f"Installation progress: {report.installation_progress or 0}%"

        case "install_complete":
            if node.state == "installing":
                await StateTransitionService.transition(
                    db=db,
                    node=node,
                    to_state="installed",
                    triggered_by="node_report",
                )
                message = "Installation completed"

        case "install_failed":
            if node.state == "installing":
                await StateTransitionService.handle_install_failure(
                    db=db,
                    node=node,
                    error=report.message or report.installation_error,
                )
                if node.state == "install_failed":
                    message = f"Installation failed after {node.install_attempts} attempts"
                else:
                    message = f"Installation failed (attempt {node.install_attempts}), will retry"

        case "first_boot":
            if node.state == "installed":
                await StateTransitionService.transition(
                    db=db,
                    node=node,
                    to_state="active",
                    triggered_by="node_report",
                    metadata=report.event_metadata,
                )
                message = "First boot - node now active"

        case "heartbeat":
            message = "Heartbeat received"

    return message


async def _handle_legacy_installation_status(
    db: AsyncSession,
    node: Node,
    report: NodeReport,
    client_ip: str | None,
) -> str:
    """Handle legacy installation_status field for backwards compatibility."""
    message = "Status reported successfully"

    # Map legacy status to event type for logging
    event_type_map = {
        "started": "install_started",
        "progress": "install_progress",
        "complete": "install_complete",
        "failed": "install_failed",
    }
    event_type = event_type_map.get(report.installation_status, "unknown")

    # Log as event
    await EventService.log_event(
        db=db,
        node=node,
        event_type=event_type,
        status="success" if report.installation_status != "failed" else "failed",
        message=report.installation_error,
        progress=report.installation_progress,
        ip_address=client_ip,
    )

    # Handle state transitions (existing logic)
    if report.installation_status == "started" and node.state == "pending":
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state="installing",
            triggered_by="node_report",
        )
        node.install_attempts = 0
        message = "Installation started"

    elif report.installation_status == "complete" and node.state == "installing":
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state="installed",
            triggered_by="node_report",
        )
        message = "Installation completed"

    elif report.installation_status == "failed" and node.state == "installing":
        await StateTransitionService.handle_install_failure(
            db=db,
            node=node,
            error=report.installation_error,
        )
        if node.state == "install_failed":
            message = f"Installation failed after {node.install_attempts} attempts"
        else:
            message = f"Installation failed (attempt {node.install_attempts}), will retry"

    return message
```

**Step 3: Add Request import**

Ensure `Request` is imported from fastapi:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request
```

**Step 4: Commit**

```bash
git add src/api/routes/nodes.py
git commit -m "feat(api): update report endpoint with event handling"
```

---

## Task 8: Add Timeout Detection to Boot Endpoint

**Files:**
- Modify: `src/api/routes/boot.py`

**Step 1: Add imports**

Add to imports:

```python
from src.core.state_service import StateTransitionService
```

**Step 2: Update installing case in get_boot_script**

Replace the `case "installing":` block with timeout detection:

```python
        case "installing":
            # Check for installation timeout
            if settings.install_timeout_minutes > 0 and node.state_changed_at:
                elapsed = datetime.now(timezone.utc) - node.state_changed_at
                timeout_seconds = settings.install_timeout_minutes * 60
                if elapsed.total_seconds() > timeout_seconds:
                    # Installation timed out - handle as failure
                    await StateTransitionService.handle_install_failure(
                        db=db,
                        node=node,
                        error=f"Installation timed out after {settings.install_timeout_minutes} minutes",
                    )
                    await db.flush()
                    # Return appropriate script based on new state
                    if node.state == "install_failed":
                        return generate_workflow_error_script(
                            node, f"Timeout after {settings.install_timeout_minutes}m"
                        )
                    # Still has retries - return install script
                    if node.workflow_id:
                        try:
                            workflow = workflow_service.get_workflow(node.workflow_id)
                            workflow = workflow_service.resolve_variables(
                                workflow,
                                server=server,
                                node_id=str(node.id),
                                mac=node.mac_address,
                                ip=node.ip_address,
                            )
                            return generate_install_script(node, workflow, server)
                        except (WorkflowNotFoundError, ValueError):
                            pass
            # Normal installing state - boot local
            return generate_local_boot_script()
```

**Step 3: Commit**

```bash
git add src/api/routes/boot.py
git commit -m "feat(api): add installation timeout detection to boot endpoint"
```

---

## Task 9: Add Node Events API Endpoint

**Files:**
- Modify: `src/api/routes/nodes.py`

**Step 1: Add events endpoint**

Add after the report endpoint:

```python
@router.get("/{node_id}/events", response_model=NodeEventListResponse)
async def get_node_events(
    node_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: str | None = Query(None, description="Filter by event type"),
    db: AsyncSession = Depends(get_db),
):
    """Get events for a specific node."""
    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    # Build query
    query = select(NodeEvent).where(NodeEvent.node_id == node_id)
    if event_type:
        query = query.where(NodeEvent.event_type == event_type)
    query = query.order_by(NodeEvent.created_at.desc())

    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    # Get paginated results
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()

    return NodeEventListResponse(
        data=[NodeEventResponse.from_event(e) for e in events],
        total=total,
    )
```

**Step 2: Add imports**

Add to imports:

```python
from src.api.schemas import NodeEventListResponse, NodeEventResponse
from sqlalchemy import func
```

**Step 3: Commit**

```bash
git add src/api/routes/nodes.py
git commit -m "feat(api): add node events endpoint"
```

---

## Task 10: Add Stalled Nodes API Endpoint

**Files:**
- Modify: `src/api/routes/nodes.py`

**Step 1: Add stalled nodes endpoint**

Add after the events endpoint:

```python
@router.get("/stalled", response_model=NodeListResponse)
async def get_stalled_nodes(
    db: AsyncSession = Depends(get_db),
):
    """Get nodes with timed-out installations.

    Returns nodes in 'installing' state that have exceeded
    the install_timeout_minutes threshold.
    """
    if settings.install_timeout_minutes <= 0:
        return NodeListResponse(data=[], total=0)

    timeout_threshold = datetime.now(timezone.utc) - timedelta(
        minutes=settings.install_timeout_minutes
    )

    result = await db.execute(
        select(Node)
        .options(selectinload(Node.tags))
        .where(Node.state == "installing")
        .where(Node.state_changed_at < timeout_threshold)
        .order_by(Node.state_changed_at.asc())
    )
    nodes = result.scalars().all()

    return NodeListResponse(
        data=[NodeResponse.from_node(n) for n in nodes],
        total=len(nodes),
    )
```

**Step 2: Add timedelta import**

Add to imports:

```python
from datetime import datetime, timedelta, timezone
```

**Step 3: Commit**

```bash
git add src/api/routes/nodes.py
git commit -m "feat(api): add stalled nodes endpoint"
```

---

## Task 11: Add Unit Tests

**Files:**
- Create: `tests/unit/test_event_service.py`

**Step 1: Create event service tests**

Create `tests/unit/test_event_service.py`:

```python
"""Tests for event service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.event_service import EventService


class TestEventService:
    """Test EventService."""

    @pytest.mark.asyncio
    async def test_log_event_creates_event(self):
        """log_event creates NodeEvent in database."""
        db = AsyncMock()
        node = MagicMock()
        node.id = "node-123"
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        event = await EventService.log_event(
            db=db,
            node=node,
            event_type="boot_started",
            status="success",
            message="Node booted",
        )

        assert event.node_id == "node-123"
        assert event.event_type == "boot_started"
        assert event.status == "success"
        assert event.message == "Node booted"
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_with_metadata(self):
        """log_event serializes metadata to JSON."""
        db = AsyncMock()
        node = MagicMock()
        node.id = "node-123"
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        event = await EventService.log_event(
            db=db,
            node=node,
            event_type="first_boot",
            metadata={"os_version": "Ubuntu 24.04", "kernel": "6.8.0"},
        )

        assert event.metadata_json is not None
        assert "Ubuntu 24.04" in event.metadata_json

    @pytest.mark.asyncio
    async def test_log_event_with_progress(self):
        """log_event stores progress percentage."""
        db = AsyncMock()
        node = MagicMock()
        node.id = "node-123"
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        event = await EventService.log_event(
            db=db,
            node=node,
            event_type="install_progress",
            progress=75,
        )

        assert event.progress == 75
```

**Step 2: Commit**

```bash
git add tests/unit/test_event_service.py
git commit -m "test: add event service unit tests"
```

---

## Task 12: Push and Create PR

**Step 1: Push branch**

```bash
git push -u origin feature/node-events
```

**Step 2: Create PR**

```bash
gh pr create --title "feat: enhance node reporting with lifecycle events (Issue #30)" --body "$(cat <<'EOF'
## Summary

- Adds NodeEvent model for logging all node lifecycle events
- Extends NodeReport schema with event-based reporting
- Adds installed→active state transition via first_boot event
- Adds installation timeout detection
- Adds node events API endpoint
- Adds stalled nodes API endpoint
- Maintains backwards compatibility with legacy installation_status

## Changes

- `src/db/models.py` - Add NodeEvent model
- `src/core/event_service.py` - New EventService for logging events
- `src/core/state_machine.py` - Add installed→active transition
- `src/config/settings.py` - Add install_timeout_minutes setting
- `src/api/schemas.py` - Extend NodeReport, add NodeEventResponse
- `src/api/routes/nodes.py` - Enhanced report endpoint, events API
- `src/api/routes/boot.py` - Timeout detection

## Event Types

| Event | Description | State Transition |
|-------|-------------|------------------|
| boot_started | Node began PXE boot | - |
| install_started | Installation began | pending → installing |
| install_progress | Progress update | - |
| install_complete | Installation succeeded | installing → installed |
| install_failed | Installation failed | retry or install_failed |
| first_boot | First boot after install | installed → active |
| heartbeat | Periodic health check | - |

## Test plan

- [ ] Event service logs events correctly
- [ ] Report endpoint handles all event types
- [ ] Legacy installation_status still works
- [ ] Timeout detection triggers on stalled installs
- [ ] Events API returns node events
- [ ] Stalled API returns timed-out nodes

Closes #30

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add NodeEvent model | `src/db/models.py` |
| 2 | Add timeout setting | `src/config/settings.py` |
| 3 | Add installed→active transition | `src/core/state_machine.py` |
| 4 | Extend NodeReport schema | `src/api/schemas.py` |
| 5 | Add NodeEventResponse schema | `src/api/schemas.py` |
| 6 | Create EventService | `src/core/event_service.py` |
| 7 | Update report endpoint | `src/api/routes/nodes.py` |
| 8 | Add timeout detection | `src/api/routes/boot.py` |
| 9 | Add events endpoint | `src/api/routes/nodes.py` |
| 10 | Add stalled endpoint | `src/api/routes/nodes.py` |
| 11 | Add unit tests | `tests/unit/test_event_service.py` |
| 12 | Push and create PR | - |
