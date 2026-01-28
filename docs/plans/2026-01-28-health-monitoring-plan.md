# Node Health Monitoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add continuous passive health monitoring for provisioned nodes with alerting and dashboard integration.

**Architecture:** Extends the existing Node model with health tracking fields, adds two new models (NodeHealthSnapshot, HealthAlert), a HealthService for computing health status/scores, scheduled jobs for periodic checks, and API endpoints for health data. Real-time alerts via existing WebSocket infrastructure.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), APScheduler, Pydantic, WebSocket

**Worktree:** `.worktrees/feature-health-monitoring` (branch: `feature/health-monitoring`)

**Important:** Do NOT install dependencies or run tests on this host. Code editing only per CLAUDE.md restrictions.

---

### Task 1: Add Health Settings to Configuration

**Files:**
- Modify: `src/config/settings.py:156-198`

**Step 1: Add HealthSettings class**

In `src/config/settings.py`, add a new settings class after `AgentSettings` (before `Settings`):

```python
class HealthSettings(BaseSettings):
    """Node health monitoring settings."""
    stale_threshold_minutes: int = 15
    offline_threshold_minutes: int = 60
    snapshot_interval_minutes: int = 5
    snapshot_retention_days: int = 30

    # Health score weights (should sum to 100)
    score_staleness_weight: int = 40
    score_install_failures_weight: int = 30
    score_boot_stability_weight: int = 30

    # Alerting
    alert_on_stale: bool = True
    alert_on_offline: bool = True
    alert_on_score_below: int = 50  # 0 to disable
```

**Step 2: Register in Settings class**

Add to `Settings` class (after `agent` field at line 182):

```python
health: HealthSettings = Field(default_factory=HealthSettings)
```

**Step 3: Commit**

```bash
git add src/config/settings.py
git commit -m "feat: add health monitoring configuration settings"
```

---

### Task 2: Add Health Fields to Node Model

**Files:**
- Modify: `src/db/models.py:101-164` (Node class)

**Step 1: Add health tracking fields to Node model**

After the `boot_mode` field (line 125) and before the `pi_model` field, add:

```python
# Health monitoring
health_status: Mapped[str] = mapped_column(
    String(20), default="unknown", index=True
)  # healthy, stale, offline, unknown
health_score: Mapped[int] = mapped_column(default=100)  # 0-100
boot_count: Mapped[int] = mapped_column(default=0)
last_boot_at: Mapped[datetime | None] = mapped_column(nullable=True)
last_ip_change_at: Mapped[datetime | None] = mapped_column(nullable=True)
previous_ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
```

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat: add health monitoring fields to Node model"
```

---

### Task 3: Add NodeHealthSnapshot Model

**Files:**
- Modify: `src/db/models.py` (after NodeEvent class, around line 230)

**Step 1: Add NodeHealthSnapshot model**

Add after the `NodeEvent` class:

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

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat: add NodeHealthSnapshot model for trend tracking"
```

---

### Task 4: Add HealthAlert Model

**Files:**
- Modify: `src/db/models.py` (after NodeHealthSnapshot)

**Step 1: Add HealthAlert model**

Add after `NodeHealthSnapshot`:

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
```

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat: add HealthAlert model for node monitoring alerts"
```

---

### Task 5: Add Health Response Schemas

**Files:**
- Modify: `src/api/schemas.py`

**Step 1: Add health schemas after NodeStatsResponse (line 1514)**

```python
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
```

**Step 2: Add health_status and health_score to NodeResponse**

In the `NodeResponse` class (line 167), add two new fields after `last_seen_at`:

```python
health_status: str = "unknown"
health_score: int = 100
```

Also update the `from_node` classmethod to include them:

```python
health_status=getattr(node, 'health_status', 'unknown'),
health_score=getattr(node, 'health_score', 100),
```

**Step 3: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat: add health monitoring API schemas"
```

---

### Task 6: Implement HealthService

**Files:**
- Create: `src/core/health_service.py`

**Step 1: Create the health service file**

```python
"""Service for node health monitoring."""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import HealthAlert, Node, NodeEvent, NodeHealthSnapshot

logger = logging.getLogger(__name__)

# Valid health statuses
HEALTH_STATUSES = ("healthy", "stale", "offline", "unknown")

# Alert type to severity mapping
ALERT_SEVERITY = {
    "node_stale": "warning",
    "node_offline": "critical",
    "low_health_score": "warning",
    "install_timeout": "critical",
}


class HealthService:
    """Service for computing and tracking node health."""

    @staticmethod
    def determine_health_status(node: Node) -> str:
        """Determine node health status based on last_seen_at."""
        if node.last_seen_at is None:
            return "unknown"

        now = datetime.now(timezone.utc)
        last_seen = node.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        seconds_since_seen = (now - last_seen).total_seconds()
        minutes_since_seen = seconds_since_seen / 60

        if minutes_since_seen <= settings.health.stale_threshold_minutes:
            return "healthy"
        elif minutes_since_seen <= settings.health.offline_threshold_minutes:
            return "stale"
        else:
            return "offline"

    @staticmethod
    def calculate_health_score(node: Node) -> tuple[int, dict[str, int]]:
        """Compute 0-100 health score with breakdown.

        Returns:
            Tuple of (score, breakdown_dict)
        """
        breakdown: dict[str, int] = {
            "staleness": 0,
            "install_failures": 0,
            "boot_stability": 0,
        }

        # Staleness penalty
        if node.last_seen_at is None:
            breakdown["staleness"] = -settings.health.score_staleness_weight
        else:
            now = datetime.now(timezone.utc)
            last_seen = node.last_seen_at
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)

            minutes_ago = (now - last_seen).total_seconds() / 60
            staleness_ratio = min(
                minutes_ago / settings.health.offline_threshold_minutes, 1.0
            )
            breakdown["staleness"] = -int(
                staleness_ratio * settings.health.score_staleness_weight
            )

        # Install failures penalty
        if node.install_attempts > 0:
            failure_ratio = min(node.install_attempts / 5, 1.0)
            breakdown["install_failures"] = -int(
                failure_ratio * settings.health.score_install_failures_weight
            )

        # Boot stability penalty (frequent reboots)
        boot_count = getattr(node, "boot_count", 0) or 0
        if boot_count > 10:
            instability_ratio = min((boot_count - 10) / 20, 1.0)
            breakdown["boot_stability"] = -int(
                instability_ratio * settings.health.score_boot_stability_weight
            )

        score = 100 + sum(breakdown.values())
        return max(0, min(100, score)), breakdown

    @staticmethod
    async def update_node_health(
        db: AsyncSession, node: Node
    ) -> tuple[str, int]:
        """Recalculate and update node health status and score.

        Returns:
            Tuple of (health_status, health_score)
        """
        new_status = HealthService.determine_health_status(node)
        new_score, _ = HealthService.calculate_health_score(node)

        node.health_status = new_status
        node.health_score = new_score

        return new_status, new_score

    @staticmethod
    async def check_all_nodes(db: AsyncSession) -> list[HealthAlert]:
        """Check health of all non-retired nodes and create/resolve alerts.

        Returns:
            List of newly created alerts.
        """
        result = await db.execute(
            select(Node).where(Node.state != "retired")
        )
        nodes = result.scalars().all()
        new_alerts: list[HealthAlert] = []

        for node in nodes:
            old_status = node.health_status
            new_status, new_score = await HealthService.update_node_health(
                db, node
            )

            # Create alerts for unhealthy nodes
            if (
                new_status == "stale"
                and settings.health.alert_on_stale
            ):
                alert = await HealthService._create_alert_if_new(
                    db,
                    node,
                    "node_stale",
                    f"Node {node.hostname or node.mac_address} is stale "
                    f"(no heartbeat for >{settings.health.stale_threshold_minutes}m)",
                )
                if alert:
                    new_alerts.append(alert)

            elif (
                new_status == "offline"
                and settings.health.alert_on_offline
            ):
                alert = await HealthService._create_alert_if_new(
                    db,
                    node,
                    "node_offline",
                    f"Node {node.hostname or node.mac_address} is offline "
                    f"(no heartbeat for >{settings.health.offline_threshold_minutes}m)",
                )
                if alert:
                    new_alerts.append(alert)
                # Also resolve any stale alert since it's now offline
                await HealthService.resolve_alert(db, node.id, "node_stale")

            elif new_status == "healthy":
                # Auto-resolve stale and offline alerts
                await HealthService.resolve_alert(db, node.id, "node_stale")
                await HealthService.resolve_alert(db, node.id, "node_offline")

            # Low health score alert
            threshold = settings.health.alert_on_score_below
            if threshold > 0 and new_score < threshold:
                alert = await HealthService._create_alert_if_new(
                    db,
                    node,
                    "low_health_score",
                    f"Node {node.hostname or node.mac_address} health score "
                    f"is {new_score} (below threshold {threshold})",
                )
                if alert:
                    new_alerts.append(alert)
            elif threshold > 0 and new_score >= threshold:
                await HealthService.resolve_alert(
                    db, node.id, "low_health_score"
                )

        return new_alerts

    @staticmethod
    async def create_snapshot(
        db: AsyncSession, node: Node
    ) -> NodeHealthSnapshot:
        """Create a point-in-time health snapshot for trend tracking."""
        now = datetime.now(timezone.utc)
        last_seen_seconds = 0

        if node.last_seen_at:
            last_seen = node.last_seen_at
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            last_seen_seconds = int((now - last_seen).total_seconds())

        snapshot = NodeHealthSnapshot(
            node_id=node.id,
            health_status=node.health_status or "unknown",
            health_score=node.health_score or 100,
            last_seen_seconds_ago=last_seen_seconds,
            boot_count=getattr(node, "boot_count", 0) or 0,
            install_attempts=node.install_attempts or 0,
            ip_address=node.ip_address,
        )
        db.add(snapshot)
        return snapshot

    @staticmethod
    async def get_summary(db: AsyncSession) -> dict:
        """Get health summary for dashboard."""
        # Count by health status
        status_result = await db.execute(
            select(Node.health_status, func.count())
            .where(Node.state != "retired")
            .group_by(Node.health_status)
        )
        by_status = dict(status_result.all())

        # Total non-retired nodes
        total = sum(by_status.values())

        # Average score
        avg_result = await db.execute(
            select(func.avg(Node.health_score)).where(Node.state != "retired")
        )
        avg_score = avg_result.scalar() or 0.0

        # Active alerts
        alert_result = await db.execute(
            select(func.count())
            .select_from(HealthAlert)
            .where(HealthAlert.status == "active")
        )
        active_alerts = alert_result.scalar() or 0

        # Critical alerts
        critical_result = await db.execute(
            select(func.count())
            .select_from(HealthAlert)
            .where(HealthAlert.status == "active")
            .where(HealthAlert.severity == "critical")
        )
        critical_alerts = critical_result.scalar() or 0

        return {
            "total_nodes": total,
            "by_status": by_status,
            "average_score": round(float(avg_score), 1),
            "active_alerts": active_alerts,
            "critical_alerts": critical_alerts,
        }

    @staticmethod
    async def _create_alert_if_new(
        db: AsyncSession,
        node: Node,
        alert_type: str,
        message: str,
        details: dict | None = None,
    ) -> HealthAlert | None:
        """Create an alert only if no active alert of this type exists."""
        existing = await db.execute(
            select(HealthAlert)
            .where(HealthAlert.node_id == node.id)
            .where(HealthAlert.alert_type == alert_type)
            .where(HealthAlert.status == "active")
        )
        if existing.scalar_one_or_none():
            return None

        severity = ALERT_SEVERITY.get(alert_type, "warning")
        alert = HealthAlert(
            node_id=node.id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            details_json=json.dumps(details) if details else None,
        )
        db.add(alert)
        logger.info(f"Health alert created: {alert_type} for node {node.id}")
        return alert

    @staticmethod
    async def resolve_alert(
        db: AsyncSession, node_id: str, alert_type: str
    ) -> bool:
        """Resolve an active alert when condition clears.

        Returns:
            True if an alert was resolved, False otherwise.
        """
        result = await db.execute(
            select(HealthAlert)
            .where(HealthAlert.node_id == node_id)
            .where(HealthAlert.alert_type == alert_type)
            .where(HealthAlert.status == "active")
        )
        alert = result.scalar_one_or_none()

        if alert:
            alert.status = "resolved"
            alert.resolved_at = datetime.now(timezone.utc)
            logger.info(
                f"Health alert resolved: {alert_type} for node {node_id}"
            )
            return True
        return False
```

**Step 2: Commit**

```bash
git add src/core/health_service.py
git commit -m "feat: implement HealthService for node health monitoring"
```

---

### Task 7: Add Health API Endpoints

**Files:**
- Create: `src/api/routes/health.py`

**Step 1: Create health routes file**

```python
"""Health monitoring API endpoints."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    HealthAlertResponse,
    HealthSnapshotResponse,
    HealthSummaryResponse,
    NodeHealthDetailResponse,
)
from src.core.health_service import HealthService
from src.db.database import get_db
from src.db.models import HealthAlert, Node, NodeHealthSnapshot

router = APIRouter()


@router.get(
    "/health/summary",
    response_model=ApiResponse[HealthSummaryResponse],
)
async def get_health_summary(
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard health summary with counts by status and alert totals."""
    summary = await HealthService.get_summary(db)
    return ApiResponse(data=HealthSummaryResponse(**summary))


@router.get(
    "/health/alerts",
    response_model=ApiListResponse[HealthAlertResponse],
)
async def get_health_alerts(
    status: Literal["active", "acknowledged", "resolved"] | None = Query(
        None, description="Filter by alert status"
    ),
    severity: Literal["warning", "critical"] | None = Query(
        None, description="Filter by severity"
    ),
    node_id: str | None = Query(None, description="Filter by node ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List health alerts with filtering and pagination."""
    query = select(HealthAlert).join(Node)

    if status:
        query = query.where(HealthAlert.status == status)
    if severity:
        query = query.where(HealthAlert.severity == severity)
    if node_id:
        query = query.where(HealthAlert.node_id == node_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Fetch paginated
    query = query.order_by(HealthAlert.created_at.desc())
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    alerts = result.scalars().all()

    # Get node names
    node_ids = list(set(a.node_id for a in alerts))
    node_names: dict[str, str] = {}
    if node_ids:
        names_result = await db.execute(
            select(Node.id, Node.hostname, Node.mac_address).where(
                Node.id.in_(node_ids)
            )
        )
        for n in names_result.all():
            node_names[n.id] = n.hostname or n.mac_address

    return ApiListResponse(
        data=[
            HealthAlertResponse.from_alert(a, node_names.get(a.node_id))
            for a in alerts
        ],
        total=total,
    )


@router.post(
    "/health/alerts/{alert_id}/acknowledge",
    response_model=ApiResponse[HealthAlertResponse],
)
async def acknowledge_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge a health alert."""
    result = await db.execute(
        select(HealthAlert).where(HealthAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot acknowledge alert with status '{alert.status}'",
        )

    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.flush()

    # Get node name
    node_result = await db.execute(
        select(Node.hostname, Node.mac_address).where(Node.id == alert.node_id)
    )
    node_row = node_result.one_or_none()
    node_name = (node_row.hostname or node_row.mac_address) if node_row else None

    return ApiResponse(
        data=HealthAlertResponse.from_alert(alert, node_name),
        message="Alert acknowledged",
    )


@router.get(
    "/nodes/{node_id}/health",
    response_model=ApiResponse[NodeHealthDetailResponse],
)
async def get_node_health(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed health information for a single node."""
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Calculate score breakdown
    _, breakdown = HealthService.calculate_health_score(node)

    # Get active alerts for this node
    alerts_result = await db.execute(
        select(HealthAlert)
        .where(HealthAlert.node_id == node_id)
        .where(HealthAlert.status == "active")
        .order_by(HealthAlert.created_at.desc())
    )
    alerts = alerts_result.scalars().all()
    node_name = node.hostname or node.mac_address

    return ApiResponse(
        data=NodeHealthDetailResponse(
            node_id=node.id,
            health_status=node.health_status or "unknown",
            health_score=node.health_score or 100,
            score_breakdown=breakdown,
            last_seen_at=node.last_seen_at,
            boot_count=getattr(node, "boot_count", 0) or 0,
            install_attempts=node.install_attempts or 0,
            last_boot_at=getattr(node, "last_boot_at", None),
            last_ip_change_at=getattr(node, "last_ip_change_at", None),
            previous_ip_address=getattr(node, "previous_ip_address", None),
            active_alerts=[
                HealthAlertResponse.from_alert(a, node_name) for a in alerts
            ],
        )
    )


@router.get(
    "/nodes/{node_id}/health/history",
    response_model=ApiListResponse[HealthSnapshotResponse],
)
async def get_node_health_history(
    node_id: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of history"),
    db: AsyncSession = Depends(get_db),
):
    """Get health snapshots for trend graphs."""
    # Verify node exists
    node_result = await db.execute(select(Node).where(Node.id == node_id))
    if not node_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Node not found")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(NodeHealthSnapshot)
        .where(NodeHealthSnapshot.node_id == node_id)
        .where(NodeHealthSnapshot.timestamp >= since)
        .order_by(NodeHealthSnapshot.timestamp.asc())
    )
    snapshots = result.scalars().all()

    return ApiListResponse(
        data=[
            HealthSnapshotResponse(
                timestamp=s.timestamp,
                health_status=s.health_status,
                health_score=s.health_score,
                last_seen_seconds_ago=s.last_seen_seconds_ago,
                boot_count=s.boot_count,
                install_attempts=s.install_attempts,
                ip_address=s.ip_address,
            )
            for s in snapshots
        ],
        total=len(snapshots),
    )
```

**Step 2: Commit**

```bash
git add src/api/routes/health.py
git commit -m "feat: add health monitoring API endpoints"
```

---

### Task 8: Register Health Router in main.py

**Files:**
- Modify: `src/main.py:28-29` (imports) and `src/main.py:381-382` (router registration)

**Step 1: Add import**

After the `disks_router` import (line 28), add:

```python
from src.api.routes.health import router as health_router
```

**Step 2: Add OpenAPI tag**

In the `openapi_tags` list (around line 246), add:

```python
{
    "name": "health",
    "description": "Node health monitoring - status, alerts, and trend data",
},
```

**Step 3: Register router**

After the `disks_router` include (line 381), add:

```python
app.include_router(health_router, prefix="/api/v1", tags=["health"])
```

**Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat: register health monitoring router"
```

---

### Task 9: Add Scheduled Health Jobs

**Files:**
- Modify: `src/main.py:115-138` (lifespan, after scheduler start)

**Step 1: Add health check job**

After the agent status update job registration (line 138), add:

```python
# Schedule health check job (every minute)
sync_scheduler.scheduler.add_job(
    _health_check_job,
    'interval',
    minutes=1,
    id='health_check',
    replace_existing=True,
)
logger.info("Health check job scheduled (every 1 minute)")

# Schedule health snapshot job
sync_scheduler.scheduler.add_job(
    _health_snapshot_job,
    'interval',
    minutes=settings.health.snapshot_interval_minutes,
    id='health_snapshot',
    replace_existing=True,
)
logger.info(
    f"Health snapshot job scheduled (every {settings.health.snapshot_interval_minutes} minutes)"
)

# Schedule health cleanup job (daily at 3 AM)
sync_scheduler.scheduler.add_job(
    _health_cleanup_job,
    'cron',
    hour=3,
    minute=0,
    id='health_cleanup',
    replace_existing=True,
)
logger.info("Health snapshot cleanup job scheduled (daily at 3:00 AM)")
```

**Step 2: Add job functions**

Before the `OPENAPI_DESCRIPTION` string (line 193), add:

```python
async def _health_check_job():
    """Periodic health check for all nodes."""
    from src.core.health_service import HealthService
    from src.core.websocket import global_ws_manager

    if not async_session_factory:
        return

    async with async_session_factory() as db:
        try:
            new_alerts = await HealthService.check_all_nodes(db)
            await db.commit()

            # Broadcast new alerts via WebSocket
            for alert in new_alerts:
                await global_ws_manager.broadcast(
                    "health:alert_created",
                    {
                        "id": alert.id,
                        "node_id": alert.node_id,
                        "alert_type": alert.alert_type,
                        "severity": alert.severity,
                        "message": alert.message,
                    },
                )

            # Broadcast updated summary
            if new_alerts:
                async with async_session_factory() as db2:
                    summary = await HealthService.get_summary(db2)
                    await global_ws_manager.broadcast(
                        "health:summary_updated", summary
                    )

        except Exception:
            logger.exception("Health check job failed")


async def _health_snapshot_job():
    """Create health snapshots for all non-retired nodes."""
    from src.core.health_service import HealthService

    if not async_session_factory:
        return

    async with async_session_factory() as db:
        try:
            result = await db.execute(
                select(Node).where(Node.state != "retired")
            )
            nodes = result.scalars().all()

            for node in nodes:
                await HealthService.create_snapshot(db, node)

            await db.commit()
            logger.debug(f"Created health snapshots for {len(nodes)} nodes")
        except Exception:
            logger.exception("Health snapshot job failed")


async def _health_cleanup_job():
    """Delete old health snapshots beyond retention period."""
    from sqlalchemy import delete

    if not async_session_factory:
        return

    async with async_session_factory() as db:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(
                days=settings.health.snapshot_retention_days
            )
            result = await db.execute(
                delete(NodeHealthSnapshot).where(
                    NodeHealthSnapshot.timestamp < cutoff
                )
            )
            await db.commit()
            deleted = result.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old health snapshots")
        except Exception:
            logger.exception("Health cleanup job failed")
```

**Step 3: Add required imports at top of main.py**

Add these imports (some may already exist):

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from src.db.models import Node, NodeHealthSnapshot
```

**Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat: add scheduled health check, snapshot, and cleanup jobs"
```

---

### Task 10: Integrate Health Tracking in Node Report

**Files:**
- Modify: `src/api/routes/nodes.py:558-622` (report_node_status function)

**Step 1: Add health import**

At the top of `nodes.py`, add:

```python
from src.core.health_service import HealthService
from src.core.websocket import global_ws_manager
```

**Step 2: Update report_node_status to track health**

After `node.last_seen_at = datetime.now(timezone.utc)` (line 591), add IP change tracking:

```python
# Track IP address changes
if report.ip_address and node.ip_address != report.ip_address:
    node.previous_ip_address = node.ip_address
    node.last_ip_change_at = datetime.now(timezone.utc)
```

**Step 3: Update _handle_event to track boots**

In `_handle_event` (line 663), in the `case "boot_started"` branch (line 687), add:

```python
case "boot_started":
    node.boot_count = (node.boot_count or 0) + 1
    node.last_boot_at = datetime.now(timezone.utc)
    message = "Boot started event logged"
```

**Step 4: Update health after report processing**

Before `await db.flush()` at line 616, add:

```python
# Update health status
old_status = node.health_status
new_status, new_score = await HealthService.update_node_health(db, node)

# Auto-resolve alerts if node is now healthy
if new_status == "healthy":
    await HealthService.resolve_alert(db, node.id, "node_stale")
    await HealthService.resolve_alert(db, node.id, "node_offline")

# Broadcast health status change
if old_status != new_status:
    await global_ws_manager.broadcast(
        "health:status_changed",
        {
            "node_id": node.id,
            "old_status": old_status,
            "new_status": new_status,
            "health_score": new_score,
        },
    )
```

**Step 5: Commit**

```bash
git add src/api/routes/nodes.py
git commit -m "feat: integrate health tracking in node report endpoint"
```

---

### Task 11: Add WebSocket Event Documentation

**Files:**
- Modify: `src/main.py` (OPENAPI_DESCRIPTION)

**Step 1: Add health WebSocket events to the description**

In the WebSocket Events section of `OPENAPI_DESCRIPTION`, add:

```
- `health:alert_created` - New health alert triggered
- `health:alert_resolved` - Health alert auto-resolved
- `health:status_changed` - Node health status changed
- `health:summary_updated` - Health summary counts updated
```

**Step 2: Commit**

```bash
git add src/main.py
git commit -m "docs: add health WebSocket events to OpenAPI description"
```

---

### Task 12: Integrate Health Alerts into Activity Feed

**Files:**
- Modify: `src/api/routes/activity.py`

**Step 1: Add HealthAlert query**

After the node events section (around line 190), add a third source of activity entries:

```python
# Fetch health alerts if not filtering to specific types
if type not in ("state_change", "node_event"):
    alert_conditions = []
    if node_id:
        alert_conditions.append(HealthAlert.node_id == node_id)
    if since:
        alert_conditions.append(HealthAlert.created_at >= since)

    alert_query = select(
        HealthAlert.id,
        HealthAlert.created_at,
        HealthAlert.node_id,
        HealthAlert.alert_type,
        HealthAlert.severity,
        HealthAlert.status,
        HealthAlert.message,
        HealthAlert.details_json,
    )
    if alert_conditions:
        alert_query = alert_query.where(*alert_conditions)
    alert_query = alert_query.order_by(HealthAlert.created_at.desc())

    alert_result = await db.execute(alert_query)
    alerts = alert_result.all()

    # Get node names for alerts
    alert_node_ids = list(set(a.node_id for a in alerts if a.node_id))
    if alert_node_ids:
        missing_ids = [nid for nid in alert_node_ids if nid not in node_names]
        if missing_ids:
            nodes_result = await db.execute(
                select(Node.id, Node.hostname, Node.mac_address).where(
                    Node.id.in_(missing_ids)
                )
            )
            for n in nodes_result.all():
                node_names[n.id] = n.hostname or n.mac_address

    for alert in alerts:
        details = None
        if alert.details_json:
            try:
                details = json.loads(alert.details_json)
            except json.JSONDecodeError:
                pass

        entries.append(ActivityEntry(
            id=f"alert_{alert.id}",
            timestamp=alert.created_at,
            type="health_alert",
            category=alert.alert_type,
            node_id=alert.node_id,
            node_name=node_names.get(alert.node_id) if alert.node_id else None,
            message=alert.message,
            details={
                **(details or {}),
                "severity": alert.severity,
                "alert_status": alert.status,
            },
            triggered_by="health_monitor",
        ))
```

**Step 2: Add import**

At the top of `activity.py`, add:

```python
from src.db.models import Node, NodeEvent, NodeStateLog, HealthAlert
```

**Step 3: Update type filter to accept health_alert**

Update the type parameter:

```python
type: Literal["state_change", "node_event", "health_alert"] | None = Query(None, description="Filter by activity type"),
```

**Step 4: Commit**

```bash
git add src/api/routes/activity.py
git commit -m "feat: integrate health alerts into activity feed"
```

---

### Task 13: Create Tests

**Files:**
- Create: `tests/test_health_service.py`
- Create: `tests/test_health_api.py`

**Step 1: Create health service tests**

```python
"""Tests for HealthService."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.health_service import HealthService


def _make_node(**kwargs):
    """Create a mock Node for testing."""
    defaults = {
        "id": "test-node-1",
        "mac_address": "00:11:22:33:44:55",
        "hostname": "test-node",
        "ip_address": "192.168.1.100",
        "state": "active",
        "health_status": "unknown",
        "health_score": 100,
        "last_seen_at": datetime.now(timezone.utc),
        "boot_count": 0,
        "install_attempts": 0,
        "last_boot_at": None,
        "last_ip_change_at": None,
        "previous_ip_address": None,
    }
    defaults.update(kwargs)
    node = MagicMock()
    for k, v in defaults.items():
        setattr(node, k, v)
    return node


class TestDetermineHealthStatus:
    """Tests for health status determination."""

    def test_unknown_when_never_seen(self):
        node = _make_node(last_seen_at=None)
        assert HealthService.determine_health_status(node) == "unknown"

    def test_healthy_when_recently_seen(self):
        node = _make_node(
            last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=5)
        )
        assert HealthService.determine_health_status(node) == "healthy"

    def test_stale_when_threshold_exceeded(self):
        node = _make_node(
            last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=30)
        )
        assert HealthService.determine_health_status(node) == "stale"

    def test_offline_when_long_unseen(self):
        node = _make_node(
            last_seen_at=datetime.now(timezone.utc) - timedelta(hours=2)
        )
        assert HealthService.determine_health_status(node) == "offline"

    def test_handles_naive_datetime(self):
        node = _make_node(
            last_seen_at=datetime.now() - timedelta(minutes=5)
        )
        # Should not raise - treats naive as UTC
        result = HealthService.determine_health_status(node)
        assert result in ("healthy", "stale", "offline", "unknown")


class TestCalculateHealthScore:
    """Tests for health score calculation."""

    def test_perfect_score_for_healthy_node(self):
        node = _make_node(
            last_seen_at=datetime.now(timezone.utc),
            install_attempts=0,
            boot_count=0,
        )
        score, breakdown = HealthService.calculate_health_score(node)
        assert score == 100

    def test_penalizes_staleness(self):
        node = _make_node(
            last_seen_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        score, breakdown = HealthService.calculate_health_score(node)
        assert score < 100
        assert breakdown["staleness"] < 0

    def test_penalizes_install_failures(self):
        node = _make_node(install_attempts=3)
        score, breakdown = HealthService.calculate_health_score(node)
        assert score < 100
        assert breakdown["install_failures"] < 0

    def test_penalizes_frequent_reboots(self):
        node = _make_node(boot_count=25)
        score, breakdown = HealthService.calculate_health_score(node)
        assert score < 100
        assert breakdown["boot_stability"] < 0

    def test_never_seen_gets_max_staleness_penalty(self):
        node = _make_node(last_seen_at=None)
        score, breakdown = HealthService.calculate_health_score(node)
        assert breakdown["staleness"] == -40  # Default weight

    def test_score_never_below_zero(self):
        node = _make_node(
            last_seen_at=None,
            install_attempts=10,
            boot_count=50,
        )
        score, _ = HealthService.calculate_health_score(node)
        assert score >= 0

    def test_score_never_above_100(self):
        node = _make_node()
        score, _ = HealthService.calculate_health_score(node)
        assert score <= 100
```

**Step 2: Create API endpoint tests**

```python
"""Tests for health monitoring API endpoints."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone


# These tests verify the endpoint logic and schemas.
# They require a running database which won't be available on this host.
# Run on the test system: pytest tests/test_health_api.py


class TestHealthSchemas:
    """Test health response schema construction."""

    def test_health_summary_response(self):
        from src.api.schemas import HealthSummaryResponse

        summary = HealthSummaryResponse(
            total_nodes=50,
            by_status={"healthy": 45, "stale": 3, "offline": 2},
            average_score=87.5,
            active_alerts=5,
            critical_alerts=2,
        )
        assert summary.total_nodes == 50
        assert summary.by_status["healthy"] == 45
        assert summary.average_score == 87.5

    def test_health_alert_response_from_alert(self):
        from src.api.schemas import HealthAlertResponse

        alert = MagicMock()
        alert.id = "alert-1"
        alert.node_id = "node-1"
        alert.alert_type = "node_stale"
        alert.severity = "warning"
        alert.status = "active"
        alert.message = "Node is stale"
        alert.details_json = None
        alert.created_at = datetime.now(timezone.utc)
        alert.acknowledged_at = None
        alert.acknowledged_by = None
        alert.resolved_at = None

        response = HealthAlertResponse.from_alert(alert, "test-node")
        assert response.id == "alert-1"
        assert response.node_name == "test-node"
        assert response.severity == "warning"

    def test_node_health_detail_response(self):
        from src.api.schemas import NodeHealthDetailResponse

        detail = NodeHealthDetailResponse(
            node_id="node-1",
            health_status="healthy",
            health_score=95,
            score_breakdown={"staleness": -5, "install_failures": 0, "boot_stability": 0},
            last_seen_at=datetime.now(timezone.utc),
            boot_count=3,
            install_attempts=0,
        )
        assert detail.health_score == 95
        assert detail.score_breakdown["staleness"] == -5

    def test_health_snapshot_response(self):
        from src.api.schemas import HealthSnapshotResponse

        snapshot = HealthSnapshotResponse(
            timestamp=datetime.now(timezone.utc),
            health_status="healthy",
            health_score=90,
            last_seen_seconds_ago=120,
            boot_count=5,
            install_attempts=0,
            ip_address="192.168.1.100",
        )
        assert snapshot.health_score == 90
        assert snapshot.ip_address == "192.168.1.100"
```

**Step 3: Commit**

```bash
git add tests/test_health_service.py tests/test_health_api.py
git commit -m "test: add health monitoring unit tests"
```

---

### Task 14: Final Verification and Summary Commit

**Step 1: Verify all files exist**

```bash
ls -la src/core/health_service.py
ls -la src/api/routes/health.py
ls -la tests/test_health_service.py
ls -la tests/test_health_api.py
```

**Step 2: Review git log**

```bash
git log --oneline --no-walk HEAD~12..HEAD
```

Verify the commit history matches expected tasks.

**Step 3: Push branch**

```bash
git push -u origin feature/health-monitoring
```
