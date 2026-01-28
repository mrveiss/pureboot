"""Service for node health monitoring."""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
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
