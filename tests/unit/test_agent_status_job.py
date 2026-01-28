"""Tests for agent status update job."""
import pytest
from datetime import datetime, timedelta

from src.core.agent_status_job import (
    get_status_for_last_seen,
    HEARTBEAT_INTERVAL,
    DEGRADED_THRESHOLD,
    OFFLINE_THRESHOLD,
)


class TestGetStatusForLastSeen:
    """Test status calculation based on last seen timestamp."""

    def test_online_recent_heartbeat(self):
        """Agent with recent heartbeat is online."""
        # Last seen 30 seconds ago
        last_seen = datetime.utcnow() - timedelta(seconds=30)
        status = get_status_for_last_seen(last_seen)
        assert status == "online"

    def test_online_within_threshold(self):
        """Agent within degraded threshold is online."""
        # Last seen just under degraded threshold
        threshold = HEARTBEAT_INTERVAL * DEGRADED_THRESHOLD - 10
        last_seen = datetime.utcnow() - timedelta(seconds=threshold)
        status = get_status_for_last_seen(last_seen)
        assert status == "online"

    def test_degraded_status(self):
        """Agent with stale heartbeat is degraded."""
        # Last seen between degraded and offline thresholds
        threshold = HEARTBEAT_INTERVAL * (DEGRADED_THRESHOLD + 1)
        last_seen = datetime.utcnow() - timedelta(seconds=threshold)
        status = get_status_for_last_seen(last_seen)
        assert status == "degraded"

    def test_offline_no_heartbeat(self):
        """Agent with no recent heartbeat is offline."""
        # Last seen well beyond offline threshold
        threshold = HEARTBEAT_INTERVAL * (OFFLINE_THRESHOLD + 5)
        last_seen = datetime.utcnow() - timedelta(seconds=threshold)
        status = get_status_for_last_seen(last_seen)
        assert status == "offline"

    def test_offline_none_last_seen(self):
        """Agent with no last_seen is offline."""
        status = get_status_for_last_seen(None)
        assert status == "offline"

    def test_threshold_boundaries(self):
        """Test exact threshold boundaries."""
        now = datetime.utcnow()

        # Just at degraded threshold - should be degraded
        degraded_time = now - timedelta(seconds=HEARTBEAT_INTERVAL * DEGRADED_THRESHOLD + 1)
        assert get_status_for_last_seen(degraded_time) == "degraded"

        # Just at offline threshold - should be offline
        offline_time = now - timedelta(seconds=HEARTBEAT_INTERVAL * OFFLINE_THRESHOLD + 1)
        assert get_status_for_last_seen(offline_time) == "offline"


class TestStatusConstants:
    """Test status threshold constants."""

    def test_heartbeat_interval(self):
        """Heartbeat interval is 60 seconds."""
        assert HEARTBEAT_INTERVAL == 60

    def test_degraded_threshold(self):
        """Degraded threshold is 2 intervals."""
        assert DEGRADED_THRESHOLD == 2

    def test_offline_threshold(self):
        """Offline threshold is 5 intervals."""
        assert OFFLINE_THRESHOLD == 5

    def test_degraded_before_offline(self):
        """Degraded threshold is before offline threshold."""
        assert DEGRADED_THRESHOLD < OFFLINE_THRESHOLD
