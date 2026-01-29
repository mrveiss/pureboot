"""Tests for HealthService."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

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
