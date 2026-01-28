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
