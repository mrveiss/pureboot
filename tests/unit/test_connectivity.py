"""Tests for connectivity monitor."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from src.agent.connectivity import ConnectivityMonitor


@pytest.fixture
def monitor():
    """Create a connectivity monitor for testing."""
    return ConnectivityMonitor(
        central_url="http://central:8080",
        check_interval=1,
        timeout=1.0,
        failure_threshold=3,
    )


class TestConnectivityMonitor:
    """Tests for ConnectivityMonitor class."""

    def test_initial_state(self, monitor):
        """Test initial state is online."""
        assert monitor.is_online is True
        assert monitor.last_online_at is None
        assert monitor.offline_since is None
        assert monitor.offline_duration is None

    def test_url_normalization(self):
        """Test central URL is normalized."""
        m = ConnectivityMonitor(central_url="http://central:8080/")
        assert m.central_url == "http://central:8080"

    @pytest.mark.asyncio
    async def test_connectivity_check_success(self, monitor):
        """Test successful connectivity check."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value.__aenter__.return_value = mock_response

        monitor._session = mock_session

        result = await monitor.check_connectivity()
        assert result is True
        mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_connectivity_check_failure_status(self, monitor):
        """Test connectivity check with non-200 status."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_session.get.return_value.__aenter__.return_value = mock_response

        monitor._session = mock_session

        result = await monitor.check_connectivity()
        assert result is False

    @pytest.mark.asyncio
    async def test_connectivity_check_connection_error(self, monitor):
        """Test connectivity check with connection error."""
        mock_session = AsyncMock()
        mock_session.get.side_effect = aiohttp.ClientError("Connection refused")

        monitor._session = mock_session

        result = await monitor.check_connectivity()
        assert result is False

    @pytest.mark.asyncio
    async def test_connectivity_check_timeout(self, monitor):
        """Test connectivity check with timeout."""
        mock_session = AsyncMock()
        mock_session.get.side_effect = asyncio.TimeoutError()

        monitor._session = mock_session

        result = await monitor.check_connectivity()
        assert result is False

    @pytest.mark.asyncio
    async def test_connectivity_check_no_session(self, monitor):
        """Test connectivity check without session returns False."""
        monitor._session = None
        result = await monitor.check_connectivity()
        assert result is False

    @pytest.mark.asyncio
    async def test_offline_after_threshold(self, monitor):
        """Test going offline after threshold failures."""
        mock_session = AsyncMock()
        mock_session.get.side_effect = aiohttp.ClientError("Connection refused")
        monitor._session = mock_session

        # Should still be online after fewer than threshold failures
        for i in range(monitor.failure_threshold - 1):
            await monitor._update_state(False)
            assert monitor.is_online is True

        # Should go offline at threshold
        await monitor._update_state(False)
        assert monitor.is_online is False
        assert monitor.offline_since is not None

    @pytest.mark.asyncio
    async def test_online_after_recovery(self, monitor):
        """Test going back online after recovery."""
        # First go offline
        monitor._is_online = False
        monitor._offline_since = datetime.now(timezone.utc)

        # Single success should bring back online
        await monitor._update_state(True)
        assert monitor.is_online is True
        assert monitor.offline_since is None
        assert monitor.last_online_at is not None

    @pytest.mark.asyncio
    async def test_listener_notification_offline(self, monitor):
        """Test listener is notified when going offline."""
        listener = AsyncMock()
        monitor.add_listener(listener)

        # Trigger offline
        for _ in range(monitor.failure_threshold):
            await monitor._update_state(False)

        listener.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_listener_notification_online(self, monitor):
        """Test listener is notified when coming back online."""
        listener = AsyncMock()
        monitor.add_listener(listener)

        # Go offline first
        monitor._is_online = False
        monitor._offline_since = datetime.now(timezone.utc)

        # Come back online
        await monitor._update_state(True)

        listener.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_listener_error_handling(self, monitor):
        """Test listener errors don't crash monitor."""
        bad_listener = AsyncMock(side_effect=Exception("Listener error"))
        good_listener = AsyncMock()

        monitor.add_listener(bad_listener)
        monitor.add_listener(good_listener)

        # Go offline
        monitor._is_online = False
        monitor._offline_since = datetime.now(timezone.utc)

        # Come back online - should not raise
        await monitor._update_state(True)

        # Both listeners should have been called
        bad_listener.assert_called_once()
        good_listener.assert_called_once()

    def test_remove_listener(self, monitor):
        """Test removing a listener."""
        listener = AsyncMock()
        monitor.add_listener(listener)
        assert listener in monitor._listeners

        monitor.remove_listener(listener)
        assert listener not in monitor._listeners

    def test_offline_duration(self, monitor):
        """Test offline duration calculation."""
        # Initially online
        assert monitor.offline_duration is None
        assert monitor.offline_duration_seconds == 0

        # Go offline
        monitor._is_online = False
        monitor._offline_since = datetime.now(timezone.utc)

        # Should have some duration
        assert monitor.offline_duration is not None
        assert monitor.offline_duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_consecutive_failure_reset(self, monitor):
        """Test consecutive failures reset on success."""
        # Accumulate some failures
        for _ in range(monitor.failure_threshold - 1):
            await monitor._update_state(False)

        assert monitor._consecutive_failures == monitor.failure_threshold - 1

        # Success should reset counter
        await monitor._update_state(True)
        assert monitor._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_start_and_stop(self, monitor):
        """Test starting and stopping the monitor."""
        with patch.object(monitor, "check_connectivity", return_value=True):
            await monitor.start()

            assert monitor._running is True
            assert monitor._session is not None
            assert monitor._task is not None

            await monitor.stop()

            assert monitor._running is False
            assert monitor._session is None
            assert monitor._task is None

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, monitor):
        """Test starting when already running does nothing."""
        with patch.object(monitor, "check_connectivity", return_value=True):
            await monitor.start()
            task1 = monitor._task

            await monitor.start()
            task2 = monitor._task

            # Should be same task
            assert task1 is task2

            await monitor.stop()

    @pytest.mark.asyncio
    async def test_force_check(self, monitor):
        """Test force check performs immediate check."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value.__aenter__.return_value = mock_response

        monitor._session = mock_session

        result = await monitor.force_check()
        assert result is True
        assert monitor.is_online is True


class TestConnectivityIntegration:
    """Integration-style tests for ConnectivityMonitor."""

    @pytest.mark.asyncio
    async def test_full_online_offline_cycle(self, monitor):
        """Test full cycle of going offline and back online."""
        listener = AsyncMock()
        monitor.add_listener(listener)

        mock_session = AsyncMock()
        monitor._session = mock_session

        # Start online
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await monitor.check_connectivity()
        await monitor._update_state(result)
        assert monitor.is_online is True

        # Go offline (simulate failures)
        mock_session.get.side_effect = aiohttp.ClientError("Offline")

        for _ in range(monitor.failure_threshold):
            result = await monitor.check_connectivity()
            await monitor._update_state(result)

        assert monitor.is_online is False
        listener.assert_called_with(False)

        # Come back online
        mock_session.get.side_effect = None
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await monitor.check_connectivity()
        await monitor._update_state(result)

        assert monitor.is_online is True
        listener.assert_called_with(True)
