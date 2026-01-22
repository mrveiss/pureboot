# Node Events and Installation Reporting Enhancement - Design

**Issue:** #30 (Implement node reporting API for installation progress)
**Date:** 2026-01-22

## Overview

Enhance the existing node reporting system to support all lifecycle events, add a NodeEvent audit model, and implement installation timeout detection.

## Current State

PR #35 (State Machine) already implemented:
- `POST /api/v1/nodes/report` endpoint
- `NodeReport` schema with `installation_status` field
- State transitions: pending→installing→installed/install_failed
- `NodeStateLog` for state transition auditing

## What's Missing

1. Additional events: `boot_started`, `first_boot`, `heartbeat`
2. `NodeEvent` model for general event logging (beyond state changes)
3. Installation timeout detection
4. `installed→active` state transition via `first_boot` event

## Design

### 1. NodeEvent Model

New database model for logging all node lifecycle events:

```python
class NodeEvent(Base):
    """General event log for node lifecycle events."""

    __tablename__ = "node_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)

    event_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), default="success")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[int | None] = mapped_column(nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now())

    node: Mapped["Node"] = relationship()
```

**Difference from NodeStateLog:**
- NodeStateLog: State transitions only (from_state → to_state)
- NodeEvent: All lifecycle events including heartbeats, progress updates, boots

### 2. Extended NodeReport Schema

```python
class NodeReport(BaseModel):
    mac_address: str

    # New event-based field
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
    metadata: dict | None = None

    # Existing fields for backwards compatibility
    ip_address: str | None = None
    hostname: str | None = None
    # ... other hardware fields ...

    # Legacy fields (still supported)
    installation_status: Literal["started", "progress", "complete", "failed"] | None = None
    installation_progress: int | None = None
    installation_error: str | None = None
```

### 3. Event Handling Logic

| Event | State Transition | Actions |
|-------|-----------------|---------|
| `boot_started` | None | Log event, update last_seen |
| `install_started` | pending → installing | Log event, reset install_attempts |
| `install_progress` | None | Log event with progress %, update last_seen |
| `install_complete` | installing → installed | Log event |
| `install_failed` | installing → pending/install_failed | Increment attempts, log error |
| `first_boot` | installed → active | Log event with OS metadata |
| `heartbeat` | None | Update last_seen, log event |

### 4. State Machine Update

Add `installed → active` transition:

```python
VALID_TRANSITIONS = {
    # ... existing ...
    "installed": ["active", "reprovision", "retired"],  # Add "active"
    # ...
}
```

### 5. Installation Timeout

Configuration:
```python
# settings.py
install_timeout_minutes: int = 60
```

On-demand detection in boot endpoint when node is in `installing` state:
```python
if node.state == "installing" and node.state_changed_at:
    elapsed = datetime.now(timezone.utc) - node.state_changed_at
    if elapsed.total_seconds() > settings.install_timeout_minutes * 60:
        await StateTransitionService.handle_install_failure(
            db, node, error="Installation timed out"
        )
```

### 6. New API Endpoints

**Get Node Events:**
```
GET /api/v1/nodes/{node_id}/events
```

**List Stalled Installations:**
```
GET /api/v1/nodes/stalled
```

## Implementation Tasks

1. Add NodeEvent model to `src/db/models.py`
2. Add `install_timeout_minutes` setting to `src/config/settings.py`
3. Add `installed→active` transition to `src/core/state_machine.py`
4. Extend NodeReport schema with `event` field and `metadata`
5. Add NodeEventResponse schema
6. Update report endpoint to handle all event types and log to NodeEvent
7. Add timeout detection in boot endpoint
8. Add `GET /api/v1/nodes/{node_id}/events` endpoint
9. Add `GET /api/v1/nodes/stalled` endpoint
10. Tests for new functionality

## Files Changed

**Create:**
- None (NodeEvent added to existing models.py)

**Modify:**
- `src/db/models.py` - Add NodeEvent model
- `src/api/schemas.py` - Extend NodeReport, add NodeEventResponse
- `src/api/routes/nodes.py` - Update report endpoint, add events API
- `src/api/routes/boot.py` - Add timeout detection
- `src/core/state_machine.py` - Add installed→active transition
- `src/config/settings.py` - Add install_timeout_minutes
