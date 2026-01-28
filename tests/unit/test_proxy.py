"""Tests for API proxy service."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

from src.agent.proxy import (
    CentralProxy,
    ProxyResponse,
    ProxyMetrics,
    CentralUnavailableError,
)
from src.agent.cache.state_cache import NodeStateCache, CachedNode
from src.agent.cache.content_cache import ContentCache


class TestProxyMetrics:
    """Tests for ProxyMetrics class."""

    @pytest.mark.asyncio
    async def test_record_request(self):
        """Test recording requests."""
        metrics = ProxyMetrics()

        await metrics.record_request()
        assert metrics.requests_total == 1
        assert metrics.requests_proxied == 1

        await metrics.record_request(from_cache=True)
        assert metrics.requests_total == 2
        assert metrics.requests_from_cache == 1

        await metrics.record_request(failed=True)
        assert metrics.requests_total == 3
        assert metrics.requests_failed == 1

    @pytest.mark.asyncio
    async def test_record_central_error(self):
        """Test recording central errors."""
        metrics = ProxyMetrics()

        await metrics.record_central_error()
        await metrics.record_central_error()

        assert metrics.central_errors == 2

    def test_get_stats(self):
        """Test getting stats."""
        metrics = ProxyMetrics()
        metrics.requests_total = 100
        metrics.requests_proxied = 80
        metrics.requests_from_cache = 15
        metrics.requests_failed = 5

        stats = metrics.get_stats()
        assert stats["requests_total"] == 100
        assert stats["cache_rate"] == 0.15


class TestCentralProxy:
    """Tests for CentralProxy class."""

    @pytest.fixture
    def state_cache(self, tmp_path):
        """Create state cache."""
        return NodeStateCache(db_path=tmp_path / "state" / "nodes.db")

    @pytest.fixture
    def content_cache(self, tmp_path):
        """Create content cache."""
        return ContentCache(
            cache_dir=tmp_path / "cache",
            max_size_gb=1,
            policy="assigned",
        )

    @pytest.fixture
    def proxy(self, state_cache, content_cache):
        """Create proxy instance."""
        return CentralProxy(
            central_url="http://central.example.com",
            state_cache=state_cache,
            content_cache=content_cache,
            site_id="site-001",
        )

    @pytest.mark.asyncio
    async def test_get_node_from_cache(self, proxy, state_cache):
        """Test getting node from cache."""
        await state_cache.initialize()

        # Pre-populate cache
        await state_cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="pending",
            node_id="node-001",
            workflow_id="ubuntu-2404",
        )

        # Should return from cache without HTTP request
        node = await proxy.get_node_by_mac("00:11:22:33:44:55")

        assert node is not None
        assert node.mac_address == "00:11:22:33:44:55"
        assert node.state == "pending"
        assert proxy.metrics.requests_from_cache == 1

    @pytest.mark.asyncio
    async def test_get_node_from_central(self, proxy, state_cache, content_cache):
        """Test getting node from central."""
        await state_cache.initialize()
        await content_cache.initialize()

        # Mock HTTP session
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[{
            "id": "node-001",
            "mac_address": "00:11:22:33:44:55",
            "state": "discovered",
            "workflow_id": None,
        }])

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=None),
        ))

        proxy._session = mock_session

        node = await proxy.get_node_by_mac("00:11:22:33:44:55")

        assert node is not None
        assert node.mac_address == "00:11:22:33:44:55"
        assert node.state == "discovered"

        # Should be cached now
        cached = await state_cache.get_node("00:11:22:33:44:55")
        assert cached is not None

    @pytest.mark.asyncio
    async def test_get_node_central_unavailable_stale_cache(self, proxy, state_cache):
        """Test serving stale cache when central unavailable."""
        await state_cache.initialize()

        # Pre-populate with expired cache
        now = datetime.now(timezone.utc)
        await state_cache.set_node(
            CachedNode(
                mac_address="00:11:22:33:44:55",
                state="pending",
                node_id="node-001",
                cached_at=now - timedelta(hours=1),
                expires_at=now - timedelta(minutes=30),  # Expired
            )
        )

        # Mock central unavailable
        mock_session = MagicMock()
        mock_session.request = MagicMock(side_effect=aiohttp.ClientError("Connection refused"))
        proxy._session = mock_session

        # Should return stale cache
        node = await proxy.get_node_by_mac("00:11:22:33:44:55")

        assert node is not None
        assert node.state == "pending"
        assert proxy.metrics.requests_from_cache == 1

    @pytest.mark.asyncio
    async def test_register_node(self, proxy, state_cache, content_cache):
        """Test registering node via proxy."""
        await state_cache.initialize()
        await content_cache.initialize()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(return_value={
            "id": "node-002",
            "mac_address": "00:11:22:33:44:66",
            "state": "discovered",
        })

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=None),
        ))

        proxy._session = mock_session

        response = await proxy.register_node(
            mac_address="00:11:22:33:44:66",
            ip_address="192.168.1.100",
            vendor="Dell",
        )

        assert response.status_code == 201
        assert response.data["id"] == "node-002"

        # Should be cached
        cached = await state_cache.get_node("00:11:22:33:44:66")
        assert cached is not None

    @pytest.mark.asyncio
    async def test_update_node_state(self, proxy, state_cache, content_cache):
        """Test updating node state via proxy."""
        await state_cache.initialize()
        await content_cache.initialize()

        # Pre-populate cache
        await state_cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="discovered",
            node_id="node-001",
        )

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "id": "node-001",
            "state": "pending",
        })

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=None),
        ))

        proxy._session = mock_session

        response = await proxy.update_node_state(
            node_id="node-001",
            new_state="pending",
            mac_address="00:11:22:33:44:55",
        )

        assert response.status_code == 200

        # Cache should be updated
        cached = await state_cache.get_node("00:11:22:33:44:55")
        assert cached.state == "pending"

    @pytest.mark.asyncio
    async def test_invalidate_node_cache(self, proxy, state_cache):
        """Test invalidating cached node."""
        await state_cache.initialize()

        await state_cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="pending",
            node_id="node-001",
        )

        await proxy.invalidate_node_cache("00:11:22:33:44:55")

        cached = await state_cache.get_node("00:11:22:33:44:55")
        assert cached is None


class TestProxyResponse:
    """Tests for ProxyResponse model."""

    def test_from_cache_flag(self):
        """Test from_cache flag."""
        response = ProxyResponse(
            status_code=200,
            data={"id": "node-001"},
            from_cache=True,
        )
        assert response.from_cache is True

    def test_error_response(self):
        """Test error response."""
        response = ProxyResponse(
            status_code=503,
            error="Central unavailable",
        )
        assert response.error == "Central unavailable"
        assert response.data is None
