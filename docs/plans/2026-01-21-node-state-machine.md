# Node State Machine Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add audit logging, install failure handling with retry limits, and auto-transitions via node reporting to the node state machine.

**Architecture:** Extend existing `NodeStateMachine` class with `install_failed` state. Add `NodeStateLog` model for audit trail. Extend `/report` endpoint to handle installation status and trigger auto-transitions. All state changes logged to both database and application logs.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2

---

## Task 1: Add NodeStateLog Model

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add the NodeStateLog model after the Node class**

```python
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
    node: Mapped[Node] = relationship()
```

**Step 2: Extend Node model with install tracking fields**

Add these fields to the existing `Node` class after `last_seen_at`:

```python
    # Installation tracking
    install_attempts: Mapped[int] = mapped_column(default=0)
    last_install_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_changed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

**Step 3: Add relationship from Node to state logs**

Add to the Node class relationships section:

```python
    state_logs: Mapped[list["NodeStateLog"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )
```

And update NodeStateLog relationship:

```python
    node: Mapped["Node"] = relationship(back_populates="state_logs")
```

**Step 4: Commit**

```bash
git add src/db/models.py
git commit -m "feat(db): add NodeStateLog model and install tracking fields"
```

---

## Task 2: Update State Machine with install_failed State

**Files:**
- Modify: `src/core/state_machine.py`

**Step 1: Add install_failed to STATES list**

Update the STATES list:

```python
    STATES: ClassVar[list[str]] = [
        "discovered",
        "pending",
        "installing",
        "install_failed",
        "installed",
        "active",
        "reprovision",
        "deprovisioning",
        "migrating",
        "retired",
    ]
```

**Step 2: Update TRANSITIONS dict**

```python
    TRANSITIONS: ClassVar[dict[str, list[str]]] = {
        "discovered": ["pending"],
        "pending": ["installing"],
        "installing": ["installed", "install_failed"],
        "install_failed": ["pending"],
        "installed": ["active"],
        "active": ["reprovision", "deprovisioning", "migrating"],
        "reprovision": ["pending"],
        "deprovisioning": ["retired"],
        "migrating": ["active"],
        "retired": [],
    }
```

**Step 3: Commit**

```bash
git add src/core/state_machine.py
git commit -m "feat(state-machine): add install_failed state"
```

---

## Task 3: Add Pydantic Schemas for State Logging

**Files:**
- Modify: `src/api/schemas.py`

**Step 1: Extend StateTransition schema**

Find the existing `StateTransition` class and update it:

```python
class StateTransition(BaseModel):
    """Request to transition node to new state."""

    state: str
    comment: str | None = None
    force: bool = False  # Bypasses retry limit, resets counters
```

**Step 2: Extend NodeReport schema**

Find the existing `NodeReport` class and add installation fields:

```python
class NodeReport(BaseModel):
    """Node status report from the node itself."""

    mac_address: str
    ip_address: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    system_uuid: str | None = None

    # Installation reporting
    installation_status: str | None = None  # started, progress, complete, failed
    installation_progress: int | None = None  # 0-100
    installation_error: str | None = None
```

**Step 3: Add NodeStateLogResponse schema**

Add after the existing node schemas:

```python
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
        import json

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
```

**Step 4: Add NodeHistoryResponse schema**

```python
class NodeHistoryResponse(BaseModel):
    """Response for node state history."""

    data: list[NodeStateLogResponse]
    total: int
```

**Step 5: Update NodeResponse to include new fields**

Find the `NodeResponse` class and add:

```python
class NodeResponse(BaseModel):
    """Response schema for a node."""

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
    # New fields
    install_attempts: int
    last_install_error: str | None
    state_changed_at: datetime | None

    @classmethod
    def from_node(cls, node: "Node") -> "NodeResponse":
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
            install_attempts=node.install_attempts,
            last_install_error=node.last_install_error,
            state_changed_at=node.state_changed_at,
        )
```

**Step 6: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat(api): add state logging schemas and extend NodeReport"
```

---

## Task 4: Create State Transition Service

**Files:**
- Create: `src/core/state_service.py`

**Step 1: Create the state service module**

```python
"""Service for managing node state transitions with audit logging."""
import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.state_machine import InvalidStateTransition, NodeStateMachine
from src.db.models import Node, NodeStateLog

logger = logging.getLogger(__name__)

MAX_INSTALL_ATTEMPTS = 3


class StateTransitionService:
    """Handles node state transitions with validation and audit logging."""

    @staticmethod
    async def transition(
        db: AsyncSession,
        node: Node,
        to_state: str,
        triggered_by: str = "admin",
        user_id: str | None = None,
        comment: str | None = None,
        metadata: dict | None = None,
        force: bool = False,
    ) -> Node:
        """
        Transition a node to a new state with audit logging.

        Args:
            db: Database session
            node: Node to transition
            to_state: Target state
            triggered_by: Who triggered (admin, system, node_report)
            user_id: User ID if admin triggered
            comment: Optional comment
            metadata: Optional metadata dict
            force: Bypass retry limits and reset counters

        Returns:
            Updated node

        Raises:
            InvalidStateTransition: If transition is not valid
            ValueError: If max retries exceeded without force
        """
        from_state = node.state

        # Check retry limit for install_failed -> pending
        if (
            from_state == "install_failed"
            and to_state == "pending"
            and not force
            and node.install_attempts >= MAX_INSTALL_ATTEMPTS
        ):
            raise ValueError(
                f"Max install attempts ({MAX_INSTALL_ATTEMPTS}) exceeded. "
                "Use force=true to reset and retry."
            )

        # Validate transition
        if not NodeStateMachine.can_transition(from_state, to_state):
            raise InvalidStateTransition(from_state, to_state)

        # Apply transition
        node.state = to_state
        node.state_changed_at = datetime.utcnow()

        # Reset counters if force or successful install
        if force or to_state == "installed":
            node.install_attempts = 0
            node.last_install_error = None

        # Create audit log
        log_entry = NodeStateLog(
            node_id=node.id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            user_id=user_id,
            comment=comment,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        db.add(log_entry)

        # Application logging
        logger.info(
            f"Node {node.id} ({node.mac_address}) transitioned: "
            f"{from_state} -> {to_state} (triggered_by={triggered_by})"
        )

        return node

    @staticmethod
    async def handle_install_failure(
        db: AsyncSession,
        node: Node,
        error: str | None = None,
    ) -> Node:
        """
        Handle installation failure with retry logic.

        Args:
            db: Database session
            node: Node that failed installation
            error: Error message

        Returns:
            Updated node (either still installing or install_failed)
        """
        node.install_attempts += 1
        node.last_install_error = error

        if node.install_attempts >= MAX_INSTALL_ATTEMPTS:
            # Max retries exceeded - transition to install_failed
            return await StateTransitionService.transition(
                db=db,
                node=node,
                to_state="install_failed",
                triggered_by="node_report",
                metadata={"error": error, "attempt": node.install_attempts},
            )
        else:
            # Still have retries - stay in installing, just log
            logger.warning(
                f"Node {node.id} install failed (attempt {node.install_attempts}/{MAX_INSTALL_ATTEMPTS}): {error}"
            )
            return node
```

**Step 2: Commit**

```bash
git add src/core/state_service.py
git commit -m "feat(core): add state transition service with audit logging"
```

---

## Task 5: Update Nodes API with State Service

**Files:**
- Modify: `src/api/routes/nodes.py`

**Step 1: Update imports**

Add these imports at the top:

```python
import json
from sqlalchemy import func, select
from src.core.state_service import StateTransitionService
from src.db.models import Node, NodeStateLog, NodeTag
from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    NodeCreate,
    NodeHistoryResponse,
    NodeReport,
    NodeResponse,
    NodeStateLogResponse,
    NodeUpdate,
    StateTransition,
    TagCreate,
)
```

**Step 2: Update transition_node_state endpoint**

Replace the existing `transition_node_state` function:

```python
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
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state=transition.state,
            triggered_by="admin",
            comment=transition.comment,
            force=transition.force,
        )
        await db.flush()
        await db.refresh(node, ["tags"])

        return ApiResponse(
            data=NodeResponse.from_node(node),
            message=f"Node transitioned to {transition.state}",
        )
    except InvalidStateTransition as e:
        valid = NodeStateMachine.get_valid_transitions(node.state)
        raise HTTPException(
            status_code=400,
            detail=f"{str(e)}. Valid transitions: {valid}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Step 3: Update retire_node endpoint**

Replace the existing `retire_node` function:

```python
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
        await StateTransitionService.transition(
            db=db,
            node=node,
            to_state="retired",
            triggered_by="admin",
        )
        await db.flush()
        await db.refresh(node, ["tags"])

        return ApiResponse(
            data=NodeResponse.from_node(node),
            message="Node retired",
        )
    except InvalidStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Step 4: Add history endpoint**

Add this new endpoint after the state transition endpoint:

```python
@router.get("/nodes/{node_id}/history", response_model=NodeHistoryResponse)
async def get_node_history(
    node_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get node state transition history."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Node not found")

    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(NodeStateLog).where(NodeStateLog.node_id == node_id)
    )
    total = count_result.scalar() or 0

    # Get logs with pagination
    logs_result = await db.execute(
        select(NodeStateLog)
        .where(NodeStateLog.node_id == node_id)
        .order_by(NodeStateLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = logs_result.scalars().all()

    return NodeHistoryResponse(
        data=[NodeStateLogResponse.from_log(log) for log in logs],
        total=total,
    )
```

**Step 5: Commit**

```bash
git add src/api/routes/nodes.py
git commit -m "feat(api): update node endpoints to use state service"
```

---

## Task 6: Update Report Endpoint with Installation Handling

**Files:**
- Modify: `src/api/routes/nodes.py`

**Step 1: Update report_node_status endpoint**

Replace the existing `report_node_status` function:

```python
@router.post("/report", response_model=ApiResponse[NodeResponse])
async def report_node_status(
    report: NodeReport,
    db: AsyncSession = Depends(get_db),
):
    """Report node status and update information.

    Called by nodes to report their current status, update
    hardware information, and report installation progress.
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

    # Handle installation status reporting
    message = "Status reported successfully"

    if report.installation_status:
        if report.installation_status == "started" and node.state == "pending":
            # Node started installing
            await StateTransitionService.transition(
                db=db,
                node=node,
                to_state="installing",
                triggered_by="node_report",
            )
            node.install_attempts = 0
            message = "Installation started"

        elif report.installation_status == "complete" and node.state == "installing":
            # Installation succeeded
            await StateTransitionService.transition(
                db=db,
                node=node,
                to_state="installed",
                triggered_by="node_report",
            )
            message = "Installation completed"

        elif report.installation_status == "failed" and node.state == "installing":
            # Installation failed
            await StateTransitionService.handle_install_failure(
                db=db,
                node=node,
                error=report.installation_error,
            )
            if node.state == "install_failed":
                message = f"Installation failed after {node.install_attempts} attempts"
            else:
                message = f"Installation failed (attempt {node.install_attempts}), will retry"

        elif report.installation_status == "progress":
            # Progress update - just log, no state change
            pass

    await db.flush()
    await db.refresh(node, ["tags"])

    return ApiResponse(
        data=NodeResponse.from_node(node),
        message=message,
    )
```

**Step 2: Commit**

```bash
git add src/api/routes/nodes.py
git commit -m "feat(api): add installation status handling to report endpoint"
```

---

## Task 7: Push Branch and Create PR

**Step 1: Push the branch**

```bash
git push -u origin feature/state-machine
```

**Step 2: Create pull request**

```bash
gh pr create --title "feat: enhance node state machine with audit logging" --body "$(cat <<'EOF'
## Summary

Implements Issue #29 - Node state machine transitions with:

- New `install_failed` state after 3 failed installation attempts
- `NodeStateLog` audit table for full state history
- Extended `/report` endpoint for installation status reporting
- Node history API endpoint (`GET /nodes/{id}/history`)
- Force reset capability for manual intervention

## Changes

- **Models:** Added `NodeStateLog`, extended `Node` with install tracking
- **State Machine:** Added `install_failed` state and transitions
- **Schemas:** Extended `StateTransition`, `NodeReport`, added history schemas
- **Services:** New `StateTransitionService` for transition logic
- **API:** Updated state endpoint, added history endpoint, extended report

## State Flow

```
pending -> installing (node reports "started")
installing -> installed (node reports "complete")
installing -> install_failed (3rd failure)
install_failed -> pending (admin force reset)
```

Closes #29

## Test Plan

- [ ] Verify state transitions work via API
- [ ] Test installation failure retry logic (3 attempts)
- [ ] Verify force reset bypasses retry limit
- [ ] Check history endpoint returns audit logs
- [ ] Confirm application logs capture transitions

Generated with Claude Code
EOF
)"
```

---

## Quick Reference

| Task | Description | Files |
|------|-------------|-------|
| 1 | Database models | `src/db/models.py` |
| 2 | State machine update | `src/core/state_machine.py` |
| 3 | Pydantic schemas | `src/api/schemas.py` |
| 4 | State transition service | `src/core/state_service.py` |
| 5 | Node API updates | `src/api/routes/nodes.py` |
| 6 | Report endpoint | `src/api/routes/nodes.py` |
| 7 | Push & PR | Git operations |
