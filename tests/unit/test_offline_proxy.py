"""Tests for offline-aware proxy functionality."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from src.agent.proxy import CentralProxy, ProxyResponse, ProxyMetrics


@pytest.fixture
def mock_state_cache():
    """Create mock state cache."""
    cache = AsyncMock()
    cache.get_node = AsyncMock(return_value=None)
    cache.set_node = AsyncMock(return_value=None)
    cache.initialize = AsyncMock()
    return cache


@pytest.fixture
def mock_content_cache():
    """Create mock content cache."""
    cache = AsyncMock()
    cache.initialize = AsyncMock()
    return cache


@pytest.fixture
def mock_connectivity():
    """Create mock connectivity monitor."""
    conn = MagicMock()
    conn.is_online = True
    return conn


@pytest.fixture
def mock_queue():
    """Create mock sync queue."""
    queue = AsyncMock()
    queue.enqueue = AsyncMock(return_value="queue-id-1")
    return queue


@pytest.fixture
def offline_proxy(mock_state_cache, mock_content_cache, mock_connectivity, mock_queue):
    """Create proxy with offline components."""
    proxy = CentralProxy(
        central_url="http://central:8080",
        state_cache=mock_state_cache,
        content_cache=mock_content_cache,
        site_id="site-001",
        connectivity=mock_connectivity,
        queue=mock_queue,
    )
    return proxy


class TestOfflineProxy:
    """Tests for offline proxy functionality."""

    def test_is_online_with_connectivity(self, offline_proxy, mock_connectivity):
        """Test is_online property with connectivity monitor."""
        mock_connectivity.is_online = True
        assert offline_proxy.is_online is True

        mock_connectivity.is_online = False
        assert offline_proxy.is_online is False

    def test_is_online_without_connectivity(self, mock_state_cache, mock_content_cache):
        """Test is_online defaults to True without monitor."""
        proxy = CentralProxy(
            central_url="http://central:8080",
            state_cache=mock_state_cache,
            content_cache=mock_content_cache,
            site_id="site-001",
        )
        assert proxy.is_online is True

    def test_set_offline_components(self, mock_state_cache, mock_content_cache):
        """Test setting offline components after init."""
        proxy = CentralProxy(
            central_url="http://central:8080",
            state_cache=mock_state_cache,
            content_cache=mock_content_cache,
            site_id="site-001",
        )

        mock_conn = MagicMock()
        mock_q = AsyncMock()

        proxy.set_offline_components(mock_conn, mock_q)

        assert proxy.connectivity is mock_conn
        assert proxy.queue is mock_q

    @pytest.mark.asyncio
    async def test_queue_registration_when_offline(
        self, offline_proxy, mock_connectivity, mock_queue
    ):
        """Test registration is queued when offline."""
        mock_connectivity.is_online = False

        result = await offline_proxy.register_node(
            mac_address="00:11:22:33:44:55",
            ip_address="192.168.1.100",
        )

        assert result["status"] == "queued"
        assert result["offline"] is True
        mock_queue.enqueue.assert_called_once()

        # Check the queued item
        call_args = mock_queue.enqueue.call_args[0][0]
        assert call_args.item_type == "registration"
        assert call_args.payload["mac_address"] == "00:11:22:33:44:55"

    @pytest.mark.asyncio
    async def test_queue_state_update_when_offline(
        self, offline_proxy, mock_connectivity, mock_queue, mock_state_cache
    ):
        """Test state update is queued when offline."""
        mock_connectivity.is_online = False

        result = await offline_proxy.update_node_state(
            node_id="node-001",
            new_state="active",
            mac_address="00:11:22:33:44:55",
        )

        assert result["status"] == "queued"
        assert result["offline"] is True
        mock_queue.enqueue.assert_called_once()

        # Check the queued item
        call_args = mock_queue.enqueue.call_args[0][0]
        assert call_args.item_type == "state_update"
        assert call_args.payload["node_id"] == "node-001"
        assert call_args.payload["new_state"] == "active"

    @pytest.mark.asyncio
    async def test_queue_event_when_offline(
        self, offline_proxy, mock_connectivity, mock_queue
    ):
        """Test event is queued when offline."""
        mock_connectivity.is_online = False

        result = await offline_proxy.report_node_event(
            node_id="node-001",
            event_type="boot_complete",
            event_data={"duration": 120},
        )

        assert result["status"] == "queued"
        assert result["offline"] is True
        mock_queue.enqueue.assert_called_once()

        # Check the queued item
        call_args = mock_queue.enqueue.call_args[0][0]
        assert call_args.item_type == "event"
        assert call_args.payload["node_id"] == "node-001"

    @pytest.mark.asyncio
    async def test_normal_operation_when_online(
        self, offline_proxy, mock_connectivity, mock_queue
    ):
        """Test normal operation when online."""
        mock_connectivity.is_online = True

        # Mock the HTTP request
        with patch.object(offline_proxy, "proxy_request") as mock_request:
            mock_request.return_value = ProxyResponse(
                status_code=201,
                data={"id": "node-001", "state": "discovered"},
            )

            result = await offline_proxy.register_node(
                mac_address="00:11:22:33:44:55",
            )

            assert result["success"] is True
            assert result["id"] == "node-001"
            mock_queue.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_return_queued_status(
        self, offline_proxy, mock_connectivity, mock_queue
    ):
        """Test return value includes queue info when offline."""
        mock_connectivity.is_online = False

        result = await offline_proxy.register_node(
            mac_address="00:11:22:33:44:55",
        )

        assert "queue_id" in result
        assert result["status"] == "queued"

    @pytest.mark.asyncio
    async def test_metrics_record_queued(
        self, offline_proxy, mock_connectivity, mock_queue
    ):
        """Test metrics record queued requests."""
        mock_connectivity.is_online = False

        await offline_proxy.register_node(mac_address="00:11:22:33:44:55")

        stats = offline_proxy.metrics.get_stats()
        assert stats["requests_queued"] == 1
        assert stats["requests_total"] == 1

    @pytest.mark.asyncio
    async def test_offline_sync_flag_skips_queue(
        self, offline_proxy, mock_connectivity, mock_queue
    ):
        """Test offline_sync=True skips queueing."""
        mock_connectivity.is_online = False

        # Mock the HTTP request for the offline_sync case
        with patch.object(offline_proxy, "proxy_request") as mock_request:
            mock_request.return_value = ProxyResponse(
                status_code=201,
                data={"id": "node-001", "state": "discovered"},
            )

            result = await offline_proxy.register_node(
                mac_address="00:11:22:33:44:55",
                offline_sync=True,  # Should not queue
            )

            # Should have called proxy_request directly
            mock_request.assert_called_once()
            mock_queue.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_update_updates_cache_when_offline(
        self, offline_proxy, mock_connectivity, mock_queue, mock_state_cache
    ):
        """Test local cache is updated even when offline."""
        mock_connectivity.is_online = False

        # Setup cached node
        from src.agent.cache.state_cache import CachedNode
        cached_node = MagicMock()
        cached_node.workflow_id = "wf-001"
        cached_node.group_id = "group-001"
        cached_node.ip_address = "192.168.1.100"
        cached_node.vendor = "Dell"
        cached_node.model = "PowerEdge"
        cached_node.raw_data = {}
        mock_state_cache.get_node.return_value = cached_node

        await offline_proxy.update_node_state(
            node_id="node-001",
            new_state="active",
            mac_address="00:11:22:33:44:55",
        )

        # Should have updated local cache
        mock_state_cache.set_node.assert_called_once()
        call_kwargs = mock_state_cache.set_node.call_args[1]
        assert call_kwargs["state"] == "active"


class TestProxyMetrics:
    """Tests for ProxyMetrics with queued tracking."""

    @pytest.mark.asyncio
    async def test_record_queued_request(self):
        """Test recording a queued request."""
        metrics = ProxyMetrics()

        await metrics.record_request(queued=True)

        stats = metrics.get_stats()
        assert stats["requests_queued"] == 1
        assert stats["requests_total"] == 1
        assert stats["requests_proxied"] == 0

    @pytest.mark.asyncio
    async def test_metrics_stats_include_queued(self):
        """Test stats include queued count."""
        metrics = ProxyMetrics()

        await metrics.record_request()  # proxied
        await metrics.record_request(from_cache=True)
        await metrics.record_request(queued=True)
        await metrics.record_request(failed=True)

        stats = metrics.get_stats()
        assert stats["requests_total"] == 4
        assert stats["requests_proxied"] == 1
        assert stats["requests_from_cache"] == 1
        assert stats["requests_queued"] == 1
        assert stats["requests_failed"] == 1
