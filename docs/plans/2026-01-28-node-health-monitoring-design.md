# Node Health Monitoring Design

**Issue:** #83
**Date:** 2026-01-28
**Status:** Approved

## Overview

Continuous health monitoring for provisioned nodes with alerting. Uses passive monitoring (heartbeat tracking from existing node reports) with WebSocket-based real-time alerts displayed in the dashboard.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Monitoring approach | Passive | Builds on existing `last_seen_at` tracking, no agent deployment needed |
| Alerting method | WebSocket + Dashboard | No external dependencies, real-time updates |
| Metrics scope | Full | Core metrics + network + trends/scores/graphs |
| Threshold config | Global settings | Simpler to manage, single source of truth |

---

## Data Model

### New Fields on Node Model

```python
# Add to src/db/models.py Node class

# Health tracking
health_status: Mapped[str] = mapped_column(
    String(20), default="unknown", index=True
)  # healthy, stale, offline, unknown
health_score: Mapped[int] = mapped_column(default=100)  # 0-100
boot_count: Mapped[int] = mapped_column(default=0)
last_boot_at: Mapped[datetime | None] = mapped_column(nullable=True)
last_ip_change_at: Mapped[datetime | None] = mapped_column(nullable=True)
previous_ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
```

### NodeHealthSnapshot Model

For historical tracking and trend graphs:

```python
class NodeHealthSnapshot(Base):
    """Point-in-time health snapshot for trend tracking."""

    __tablename__ = "node_health_snapshots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(default=func.now(), index=True)
    health_status: Mapped[str] = mapped_column(String(20), nullable=False)
    health_score: Mapped[int] = mapped_column(nullable=False)
    last_seen_seconds_ago: Mapped[int] = mapped_column(nullable=False)
    boot_count: Mapped[int] = mapped_column(default=0)
    install_attempts: Mapped[int] = mapped_column(default=0)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Relationship
    node: Mapped["Node"] = relationship()

    __table_args__ = (
        Index("ix_health_snapshot_node_time", "node_id", "timestamp"),
    )
```

### HealthAlert Model

```python
class HealthAlert(Base):
    """Health alert for node monitoring."""

    __tablename__ = "health_alerts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # node_stale, node_offline, low_health_score, install_timeout
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # warning, critical
    status: Mapped[str] = mapped_column(
        String(20), default="active", index=True
    )  # active, acknowledged, resolved

    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationship
    node: Mapped["Node"] = relationship()

    __table_args__ = (
        # Prevent duplicate active alerts of same type for same node
        Index(
            "ix_health_alert_active",
            "node_id", "alert_type",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
```

---

## Configuration

Add to `src/config/__init__.py`:

```python
# Health monitoring thresholds
health_stale_threshold_minutes: int = 15
health_offline_threshold_minutes: int = 60
health_snapshot_interval_minutes: int = 5
health_snapshot_retention_days: int = 30

# Health score weights (should sum to 100)
health_score_staleness_weight: int = 40
health_score_install_failures_weight: int = 30
health_score_boot_stability_weight: int = 30

# Alerting
health_alert_on_stale: bool = True
health_alert_on_offline: bool = True
health_alert_on_score_below: int = 50  # 0 to disable
```

---

## Health Service

New file: `src/core/health_service.py`

```python
class HealthService:
    """Service for node health monitoring."""

    @staticmethod
    async def update_node_health(db: AsyncSession, node: Node) -> tuple[str, int]:
        """Recalculate and update node health status and score.

        Returns:
            Tuple of (health_status, health_score)
        """
        pass

    @staticmethod
    async def check_all_nodes(db: AsyncSession) -> list[HealthAlert]:
        """Periodic check of all nodes, returns list of new alerts."""
        pass

    @staticmethod
    async def calculate_health_score(node: Node) -> int:
        """Compute 0-100 health score based on configured weights."""
        pass

    @staticmethod
    async def create_snapshot(db: AsyncSession, node: Node) -> NodeHealthSnapshot:
        """Create point-in-time health snapshot for trending."""
        pass

    @staticmethod
    async def create_alert(
        db: AsyncSession,
        node: Node,
        alert_type: str,
        severity: str,
        message: str,
    ) -> HealthAlert | None:
        """Create alert if one doesn't already exist (active) for this node/type."""
        pass

    @staticmethod
    async def resolve_alert(
        db: AsyncSession,
        node_id: str,
        alert_type: str,
    ) -> bool:
        """Auto-resolve an active alert when condition clears."""
        pass
```

### Health Status Logic

```python
def determine_health_status(node: Node, settings) -> str:
    if node.last_seen_at is None:
        return "unknown"

    now = datetime.now(timezone.utc)
    minutes_since_seen = (now - node.last_seen_at).total_seconds() / 60

    if minutes_since_seen <= settings.health_stale_threshold_minutes:
        return "healthy"
    elif minutes_since_seen <= settings.health_offline_threshold_minutes:
        return "stale"
    else:
        return "offline"
```

### Health Score Calculation

```python
def calculate_health_score(node: Node, settings) -> int:
    score = 100

    # Staleness penalty (0-40 points based on weight)
    if node.last_seen_at:
        minutes_ago = (now - node.last_seen_at).total_seconds() / 60
        staleness_ratio = min(minutes_ago / settings.health_offline_threshold_minutes, 1.0)
        score -= int(staleness_ratio * settings.health_score_staleness_weight)
    else:
        score -= settings.health_score_staleness_weight

    # Install failures penalty (0-30 points)
    if node.install_attempts > 0:
        failure_ratio = min(node.install_attempts / 5, 1.0)  # Max penalty at 5 failures
        score -= int(failure_ratio * settings.health_score_install_failures_weight)

    # Boot stability penalty (0-30 points)
    # Frequent reboots in short period indicate instability
    # (Requires checking recent boot events)

    return max(0, score)
```

---

## API Endpoints

New file: `src/api/routes/health.py`

### Health Summary

```python
@router.get("/health/summary", response_model=ApiResponse[HealthSummaryResponse])
async def get_health_summary(db: AsyncSession = Depends(get_db)):
    """Get dashboard health summary."""
    # Returns counts by status, average score, active alerts
```

**Response schema:**
```python
class HealthSummaryResponse(BaseModel):
    total_nodes: int
    by_status: dict[str, int]  # {healthy: 45, stale: 3, offline: 2, unknown: 1}
    average_score: float
    active_alerts: int
    critical_alerts: int
```

### Health Alerts

```python
@router.get("/health/alerts", response_model=ApiListResponse[HealthAlertResponse])
async def get_health_alerts(
    status: Literal["active", "acknowledged", "resolved"] | None = None,
    severity: Literal["warning", "critical"] | None = None,
    node_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List health alerts with filtering."""

@router.post("/health/alerts/{alert_id}/acknowledge", response_model=ApiResponse)
async def acknowledge_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge an alert."""
```

### Per-Node Health

```python
@router.get("/nodes/{node_id}/health", response_model=ApiResponse[NodeHealthResponse])
async def get_node_health(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed health for a single node."""

@router.get("/nodes/{node_id}/health/history", response_model=ApiListResponse[HealthSnapshotResponse])
async def get_node_health_history(
    node_id: str,
    hours: int = Query(24, ge=1, le=168),  # Max 7 days
    db: AsyncSession = Depends(get_db),
):
    """Get health snapshots for trend graphs."""
```

**Response schemas:**
```python
class NodeHealthResponse(BaseModel):
    node_id: str
    health_status: str
    health_score: int
    score_breakdown: dict[str, int]  # {staleness: -10, install_failures: 0, ...}
    last_seen_at: datetime | None
    boot_count: int
    install_attempts: int
    active_alerts: list[HealthAlertResponse]

class HealthSnapshotResponse(BaseModel):
    timestamp: datetime
    health_status: str
    health_score: int
    last_seen_seconds_ago: int
```

### Extend NodeResponse

Add to existing `NodeResponse` schema:
```python
health_status: str = "unknown"
health_score: int = 100
```

---

## WebSocket Events

Extend `src/core/websocket.py` with new event types:

| Event | Payload | Trigger |
|-------|---------|---------|
| `health:alert_created` | `{alert: HealthAlertResponse}` | New alert triggered |
| `health:alert_resolved` | `{alert_id: str, node_id: str}` | Alert auto-resolved |
| `health:status_changed` | `{node_id: str, old: str, new: str, score: int}` | Node health status changed |
| `health:summary_updated` | `HealthSummaryResponse` | Dashboard counts changed |

---

## Scheduled Jobs

Extend `src/core/scheduler.py`:

```python
async def health_check_job():
    """Runs every minute to check node health."""
    async with get_db_session() as db:
        alerts = await HealthService.check_all_nodes(db)

        if alerts:
            for alert in alerts:
                await WebSocketManager.broadcast("health:alert_created", alert)

            # Broadcast updated summary
            summary = await HealthService.get_summary(db)
            await WebSocketManager.broadcast("health:summary_updated", summary)

        await db.commit()

async def health_snapshot_job():
    """Runs every N minutes (configurable) to create snapshots."""
    async with get_db_session() as db:
        result = await db.execute(
            select(Node).where(Node.state != "retired")
        )
        for node in result.scalars():
            await HealthService.create_snapshot(db, node)
        await db.commit()

async def health_cleanup_job():
    """Runs daily to purge old snapshots."""
    async with get_db_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=settings.health_snapshot_retention_days
        )
        await db.execute(
            delete(NodeHealthSnapshot).where(
                NodeHealthSnapshot.timestamp < cutoff
            )
        )
        await db.commit()
```

---

## Integration Points

### Node Report Endpoint

Update `/report` in `src/api/routes/nodes.py`:

```python
# After updating last_seen_at
old_status = node.health_status
new_status, new_score = await HealthService.update_node_health(db, node)

# Detect IP changes
if report.ip_address and node.ip_address != report.ip_address:
    node.previous_ip_address = node.ip_address
    node.last_ip_change_at = datetime.now(timezone.utc)

# Track boot events
if report.event == "boot_started":
    node.boot_count += 1
    node.last_boot_at = datetime.now(timezone.utc)

# Broadcast if status changed
if old_status != new_status:
    await WebSocketManager.broadcast("health:status_changed", {
        "node_id": node.id,
        "old": old_status,
        "new": new_status,
        "score": new_score,
    })

# Auto-resolve alerts if node is now healthy
if new_status == "healthy":
    await HealthService.resolve_alert(db, node.id, "node_stale")
    await HealthService.resolve_alert(db, node.id, "node_offline")
```

### State Transitions

When node transitions to `active`, resolve related alerts.

### Activity Log

Health alerts should appear in global activity feed (extend activity.py to query HealthAlert table).

### Deprecation

The existing `/nodes/stalled` endpoint should be deprecated in favor of the new health alerts system (but kept for backwards compatibility).

---

## Frontend Components

### Dashboard Health Widget
- Donut chart showing nodes by health status
- Average health score gauge (0-100)
- Active alerts count with severity badges
- Click to navigate to alerts page

### Node List Enhancements
- Health status indicator (colored dot: green/yellow/red/gray)
- Health score column (sortable)
- Filter dropdown for health status

### Node Detail Health Tab
- Current status and score with breakdown
- Line chart: health score over time (24h/7d)
- Boot history timeline
- IP address change log
- Related alerts list

### Alerts Page/Panel
- Table of alerts with columns: severity, node, type, message, created, status
- Filters: status, severity, node
- Acknowledge button (single and bulk)
- Auto-refresh via WebSocket
- Click row to navigate to node

### Real-time Updates
- WebSocket listeners update components without refresh
- Toast notifications for new critical alerts

---

## Implementation Phases

### Phase 1: Core Backend
1. Add new fields to Node model
2. Create NodeHealthSnapshot and HealthAlert models
3. Add configuration settings
4. Implement HealthService
5. Add health API endpoints

### Phase 2: Integration
1. Update node report endpoint to track health
2. Add scheduled jobs for health checks and snapshots
3. Add WebSocket event broadcasting
4. Integrate with activity log

### Phase 3: Frontend
1. Add health widget to dashboard
2. Enhance node list with health indicators
3. Add health tab to node detail page
4. Create alerts page

### Phase 4: Polish
1. Add trend graphs
2. Cleanup job for old snapshots
3. Documentation
4. Tests

---

## Files to Create/Modify

**New files:**
- `src/core/health_service.py`
- `src/api/routes/health.py`
- `frontend/src/api/health.ts`
- `frontend/src/hooks/useHealth.ts`
- `frontend/src/pages/HealthAlerts.tsx`
- `frontend/src/components/HealthWidget.tsx`
- `frontend/src/components/HealthChart.tsx`

**Modified files:**
- `src/db/models.py` - Add Node fields, NodeHealthSnapshot, HealthAlert
- `src/config/__init__.py` - Add health settings
- `src/api/routes/nodes.py` - Integrate health tracking in /report
- `src/api/routes/__init__.py` - Register health router
- `src/api/schemas.py` - Add health response schemas
- `src/core/scheduler.py` - Add health jobs
- `src/core/websocket.py` - Add health events
- `src/api/routes/activity.py` - Include health alerts
- `frontend/src/pages/NodeDetail.tsx` - Add health tab
- `frontend/src/pages/NodeList.tsx` - Add health column/filter
- `frontend/src/pages/Dashboard.tsx` - Add health widget
