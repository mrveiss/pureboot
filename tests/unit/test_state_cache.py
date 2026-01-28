"""Tests for node state cache."""
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.agent.cache.state_cache import NodeStateCache, CachedNode


class TestCachedNode:
    """Tests for CachedNode model."""

    def test_is_expired_false(self):
        """Test node is not expired when expires_at is in future."""
        node = CachedNode(
            mac_address="00:11:22:33:44:55",
            state="discovered",
            cached_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        assert node.is_expired is False

    def test_is_expired_true(self):
        """Test node is expired when expires_at is in past."""
        node = CachedNode(
            mac_address="00:11:22:33:44:55",
            state="discovered",
            cached_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        assert node.is_expired is True

    def test_ttl_seconds(self):
        """Test TTL calculation."""
        node = CachedNode(
            mac_address="00:11:22:33:44:55",
            state="discovered",
            cached_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        # Allow some tolerance for test execution time
        assert 115 <= node.ttl_seconds <= 120

    def test_ttl_seconds_expired(self):
        """Test TTL is 0 when expired."""
        node = CachedNode(
            mac_address="00:11:22:33:44:55",
            state="discovered",
            cached_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        assert node.ttl_seconds == 0


class TestNodeStateCache:
    """Tests for NodeStateCache class."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a test cache instance."""
        db_path = tmp_path / "state" / "nodes.db"
        return NodeStateCache(db_path=db_path, default_ttl=300)

    @pytest.mark.asyncio
    async def test_initialize(self, cache):
        """Test cache initializes database."""
        await cache.initialize()
        assert cache.db_path.exists()
        assert cache._initialized is True

    @pytest.mark.asyncio
    async def test_set_and_get_node(self, cache):
        """Test caching and retrieving a node."""
        await cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="discovered",
            node_id="node-001",
            workflow_id="ubuntu-2404",
            group_id="default",
        )

        node = await cache.get_node("00:11:22:33:44:55")
        assert node is not None
        assert node.mac_address == "00:11:22:33:44:55"
        assert node.state == "discovered"
        assert node.node_id == "node-001"
        assert node.workflow_id == "ubuntu-2404"
        assert node.group_id == "default"

    @pytest.mark.asyncio
    async def test_set_node_with_cached_node(self, cache):
        """Test caching with CachedNode object."""
        now = datetime.now(timezone.utc)
        node = CachedNode(
            mac_address="00:11:22:33:44:55",
            state="pending",
            cached_at=now,
            expires_at=now + timedelta(seconds=300),
            raw_data={"extra": "data"},
        )

        result = await cache.set_node(node)
        assert result.mac_address == "00:11:22:33:44:55"

        retrieved = await cache.get_node("00:11:22:33:44:55")
        assert retrieved is not None
        assert retrieved.raw_data == {"extra": "data"}

    @pytest.mark.asyncio
    async def test_get_node_normalizes_mac(self, cache):
        """Test MAC address normalization."""
        await cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="discovered",
        )

        # Different formats should all work
        assert await cache.get_node("00:11:22:33:44:55") is not None
        assert await cache.get_node("00-11-22-33-44-55") is not None
        assert await cache.get_node("00:11:22:33:44:55".upper()) is not None

    @pytest.mark.asyncio
    async def test_get_node_not_found(self, cache):
        """Test getting non-existent node returns None."""
        node = await cache.get_node("00:00:00:00:00:00")
        assert node is None

    @pytest.mark.asyncio
    async def test_update_node(self, cache):
        """Test updating existing node."""
        await cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="discovered",
        )

        await cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="pending",
            workflow_id="ubuntu-2404",
        )

        node = await cache.get_node("00:11:22:33:44:55")
        assert node.state == "pending"
        assert node.workflow_id == "ubuntu-2404"

    @pytest.mark.asyncio
    async def test_invalidate_node(self, cache):
        """Test invalidating cache entry."""
        await cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="discovered",
        )

        deleted = await cache.invalidate("00:11:22:33:44:55")
        assert deleted is True

        node = await cache.get_node("00:11:22:33:44:55")
        assert node is None

    @pytest.mark.asyncio
    async def test_invalidate_not_found(self, cache):
        """Test invalidating non-existent entry."""
        deleted = await cache.invalidate("00:00:00:00:00:00")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_get_nodes_by_group(self, cache):
        """Test getting nodes by group."""
        await cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="discovered",
            group_id="site-a",
        )
        await cache.set_node(
            mac_address="00:11:22:33:44:66",
            state="pending",
            group_id="site-a",
        )
        await cache.set_node(
            mac_address="00:11:22:33:44:77",
            state="discovered",
            group_id="site-b",
        )

        nodes = await cache.get_nodes_by_group("site-a")
        assert len(nodes) == 2
        macs = {n.mac_address for n in nodes}
        assert "00:11:22:33:44:55" in macs
        assert "00:11:22:33:44:66" in macs

    @pytest.mark.asyncio
    async def test_get_all_nodes(self, cache):
        """Test getting all nodes."""
        await cache.set_node(mac_address="00:11:22:33:44:55", state="discovered")
        await cache.set_node(mac_address="00:11:22:33:44:66", state="pending")

        nodes = await cache.get_all_nodes()
        assert len(nodes) == 2

    @pytest.mark.asyncio
    async def test_invalidate_expired(self, cache):
        """Test invalidating expired entries."""
        now = datetime.now(timezone.utc)

        # Add valid entry
        await cache.set_node(
            CachedNode(
                mac_address="00:11:22:33:44:55",
                state="discovered",
                cached_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )

        # Add expired entry
        await cache.set_node(
            CachedNode(
                mac_address="00:11:22:33:44:66",
                state="discovered",
                cached_at=now - timedelta(minutes=10),
                expires_at=now - timedelta(minutes=5),
            )
        )

        count = await cache.invalidate_expired()
        assert count == 1

        # Valid entry still exists
        assert await cache.get_node("00:11:22:33:44:55") is not None
        # Expired entry removed
        assert await cache.get_node("00:11:22:33:44:66") is None

    @pytest.mark.asyncio
    async def test_get_stats(self, cache):
        """Test getting cache statistics."""
        now = datetime.now(timezone.utc)

        await cache.set_node(
            CachedNode(
                mac_address="00:11:22:33:44:55",
                state="discovered",
                cached_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        await cache.set_node(
            CachedNode(
                mac_address="00:11:22:33:44:66",
                state="discovered",
                cached_at=now - timedelta(minutes=10),
                expires_at=now - timedelta(minutes=5),
            )
        )

        stats = await cache.get_stats()
        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
        assert stats["valid_entries"] == 1
        assert stats["oldest_entry"] is not None

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        """Test clearing all entries."""
        await cache.set_node(mac_address="00:11:22:33:44:55", state="discovered")
        await cache.set_node(mac_address="00:11:22:33:44:66", state="pending")

        count = await cache.clear()
        assert count == 2

        nodes = await cache.get_all_nodes()
        assert len(nodes) == 0

    @pytest.mark.asyncio
    async def test_custom_ttl(self, cache):
        """Test custom TTL for cache entry."""
        await cache.set_node(
            mac_address="00:11:22:33:44:55",
            state="discovered",
            ttl=60,  # 1 minute
        )

        node = await cache.get_node("00:11:22:33:44:55")
        assert node is not None
        # TTL should be around 60 seconds
        assert 55 <= node.ttl_seconds <= 60

    @pytest.mark.asyncio
    async def test_cache_persistence(self, tmp_path):
        """Test cache persists across instances."""
        db_path = tmp_path / "state" / "nodes.db"

        # First cache instance
        cache1 = NodeStateCache(db_path=db_path)
        await cache1.set_node(
            mac_address="00:11:22:33:44:55",
            state="discovered",
        )

        # Second cache instance using same DB
        cache2 = NodeStateCache(db_path=db_path)
        node = await cache2.get_node("00:11:22:33:44:55")

        assert node is not None
        assert node.state == "discovered"
