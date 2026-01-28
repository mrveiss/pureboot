"""Tests for health monitoring API schemas."""
from datetime import datetime, timezone
from unittest.mock import MagicMock


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
