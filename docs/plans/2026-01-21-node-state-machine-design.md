# Node State Machine Enhancement Design

## Overview

Enhance the existing node state machine with audit logging, installation failure handling, and auto-transition support for the node lifecycle.

## State Machine

### States

| State | Description |
|-------|-------------|
| `discovered` | Node PXE booted, MAC registered, awaiting approval |
| `pending` | Approved, workflow assigned, waiting to install |
| `installing` | Active installation in progress |
| `install_failed` | Installation failed after max retries, requires intervention |
| `installed` | Installation complete, awaiting manual verification |
| `active` | In production use |
| `reprovision` | Marked for re-imaging |
| `deprovisioning` | Secure data erasure in progress |
| `migrating` | Hardware replacement workflow |
| `retired` | Decommissioned |

### Transitions

```
discovered → pending (admin approval)
pending → installing (node reports "started")
installing → installed (node reports "complete")
installing → install_failed (node reports "failed", attempts >= 3)
install_failed → pending (admin assigns new workflow + force reset)
installed → active (admin verification)
active → reprovision | deprovisioning | migrating
reprovision → pending
deprovisioning → retired
migrating → active
any → retired (admin decommission)
```

### Failure Handling

- Node stays in `installing` for first 2 failures (attempts 1, 2)
- On 3rd failure, transitions to `install_failed`
- `install_failed` requires manual intervention:
  1. Admin assigns different workflow via `PATCH /nodes/{id}`
  2. Admin resets to `pending` with `force: true`
  3. Retry counter resets, node re-enters install queue

## Data Model

### NodeStateLog Table

```python
class NodeStateLog(Base):
    __tablename__ = "node_state_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    from_state: Mapped[str] = mapped_column(String(20), nullable=False)
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)  # admin, system, node_report
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### Node Model Extensions

```python
# Add to Node model
install_attempts: Mapped[int] = mapped_column(default=0)
last_install_error: Mapped[str | None] = mapped_column(Text, nullable=True)
state_changed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

## API Changes

### Extended StateTransition Schema

```python
class StateTransition(BaseModel):
    state: str
    comment: str | None = None
    force: bool = False  # Bypasses retry limit, resets counters
```

### Extended NodeReport Schema

```python
class NodeReport(BaseModel):
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

### Node History Endpoint

```
GET /api/v1/nodes/{id}/history?limit=50&offset=0
```

Response:
```json
{
  "data": [
    {
      "id": "uuid",
      "from_state": "installing",
      "to_state": "install_failed",
      "triggered_by": "node_report",
      "user_id": null,
      "comment": null,
      "metadata": {"error": "Disk not found", "attempt": 3},
      "created_at": "2026-01-21T10:30:00Z"
    }
  ],
  "total": 15
}
```

## Report Handling Logic

| `installation_status` | Current State | Action |
|----------------------|---------------|--------|
| `started` | `pending` | Transition to `installing`, reset `install_attempts` |
| `progress` | `installing` | Update progress tracking, no state change |
| `complete` | `installing` | Transition to `installed`, reset `install_attempts` |
| `failed` | `installing` | Increment `install_attempts`; if >= 3 → `install_failed`, else stay `installing` |

## Logging

All state transitions are:
1. Recorded in `node_state_logs` table (queryable via API)
2. Logged via application logger with structured data

## Future Considerations

- **Auto-promote configuration**: Per device group and per user group settings for automatic `installed → active` transition
- **Separate installation endpoint**: `POST /api/v1/nodes/{id}/installation-status` if report endpoint becomes overloaded
- **Workflow engine integration**: Workflows define auto-transition behavior

## Files to Modify

| File | Changes |
|------|---------|
| `src/db/models.py` | Add `NodeStateLog`, extend `Node` |
| `src/api/schemas.py` | Add `NodeStateLogResponse`, extend `NodeReport`, `StateTransition` |
| `src/core/state_machine.py` | Add `install_failed` state and transitions |
| `src/api/routes/nodes.py` | Update endpoints, add history, extend report handling |

## Decision Summary

| Decision | Choice |
|----------|--------|
| Audit storage | Database table + application logs |
| Auto-transition trigger | Extend existing `/report` endpoint |
| Failure handling | New `install_failed` state after 3 retries |
| Auto-promote | Manual only (configurable per group later) |
| Manual retry | Change workflow via PATCH, then force reset to `pending` |
| Max retries | 3 attempts before requiring intervention |
