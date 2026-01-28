"""Tests for content cache manager."""
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.agent.cache.content_cache import ContentCache, CacheStats


class TestContentCache:
    """Tests for ContentCache class."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a test cache instance."""
        return ContentCache(
            cache_dir=tmp_path / "cache",
            max_size_gb=1,  # 1GB for tests
            policy="assigned",
        )

    @pytest.mark.asyncio
    async def test_initialize(self, cache):
        """Test cache initialization creates directories."""
        await cache.initialize()

        assert (cache.cache_dir / "bootloaders").exists()
        assert (cache.cache_dir / "scripts").exists()
        assert (cache.cache_dir / "templates").exists()
        assert (cache.cache_dir / "images").exists()

    @pytest.mark.asyncio
    async def test_put_and_get(self, cache):
        """Test caching and retrieving content."""
        await cache.initialize()

        content = b"test bootloader content"
        path = await cache.put("bootloaders", "ipxe.efi", content)

        assert path.exists()
        assert path.read_bytes() == content

        # Get should return the path
        result = await cache.get("bootloaders", "ipxe.efi")
        assert result == path

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache):
        """Test getting non-existent file returns None."""
        await cache.initialize()

        result = await cache.get("bootloaders", "nonexistent.efi")
        assert result is None

    @pytest.mark.asyncio
    async def test_evict(self, cache):
        """Test evicting cache entry."""
        await cache.initialize()

        await cache.put("templates", "kickstart.ks", b"kickstart content")

        # File exists
        assert await cache.get("templates", "kickstart.ks") is not None

        # Evict
        result = await cache.evict("templates", "kickstart.ks")
        assert result is True

        # File gone
        assert await cache.get("templates", "kickstart.ks") is None

    @pytest.mark.asyncio
    async def test_evict_nonexistent(self, cache):
        """Test evicting non-existent entry."""
        await cache.initialize()

        result = await cache.evict("templates", "nonexistent.ks")
        assert result is False

    @pytest.mark.asyncio
    async def test_expiry(self, cache):
        """Test cache expiry."""
        await cache.initialize()

        # Cache with immediate expiry
        await cache.put(
            "scripts",
            "test.ipxe",
            b"script content",
            expires_in=timedelta(seconds=-1),  # Already expired
        )

        # Should return None due to expiry
        result = await cache.get("scripts", "test.ipxe")
        assert result is None

    @pytest.mark.asyncio
    async def test_evict_expired(self, cache):
        """Test evicting all expired entries."""
        await cache.initialize()

        # Add valid entry
        await cache.put(
            "bootloaders",
            "valid.efi",
            b"valid content",
        )

        # Add expired entry
        await cache.put(
            "scripts",
            "expired.ipxe",
            b"expired content",
            expires_in=timedelta(seconds=-1),
        )

        # Evict expired
        count = await cache.evict_expired()
        assert count == 1

        # Valid still exists
        assert await cache.get("bootloaders", "valid.efi") is not None

    @pytest.mark.asyncio
    async def test_get_stats(self, cache):
        """Test getting cache statistics."""
        await cache.initialize()

        await cache.put("bootloaders", "ipxe.efi", b"x" * 100)
        await cache.put("templates", "kickstart.ks", b"y" * 200)

        stats = await cache.get_stats()

        assert stats.total_size_bytes == 300
        assert stats.total_entries == 2
        assert "bootloaders" in stats.categories
        assert stats.categories["bootloaders"]["count"] == 1
        assert stats.categories["bootloaders"]["size_bytes"] == 100

    @pytest.mark.asyncio
    async def test_clear_category(self, cache):
        """Test clearing specific category."""
        await cache.initialize()

        await cache.put("bootloaders", "ipxe.efi", b"content")
        await cache.put("templates", "kickstart.ks", b"content")

        count = await cache.clear("templates")
        assert count == 1

        # Bootloader still exists
        assert await cache.get("bootloaders", "ipxe.efi") is not None
        # Template cleared
        assert await cache.get("templates", "kickstart.ks") is None

    @pytest.mark.asyncio
    async def test_clear_all(self, cache):
        """Test clearing all cache."""
        await cache.initialize()

        await cache.put("bootloaders", "ipxe.efi", b"content")
        await cache.put("templates", "kickstart.ks", b"content")

        count = await cache.clear()
        assert count == 2

        stats = await cache.get_stats()
        assert stats.total_entries == 0


class TestCachePolicy:
    """Tests for cache policy behavior."""

    @pytest.mark.asyncio
    async def test_minimal_policy_bootloaders_only(self, tmp_path):
        """Test minimal policy only caches bootloaders."""
        cache = ContentCache(
            cache_dir=tmp_path / "cache",
            max_size_gb=1,
            policy="minimal",
        )
        await cache.initialize()

        # Bootloaders should be allowed
        assert await cache.should_cache("bootloaders", "ipxe.efi") is True

        # Templates should not be allowed
        assert await cache.should_cache("templates", "kickstart.ks") is False

    @pytest.mark.asyncio
    async def test_assigned_policy_allows_all(self, tmp_path):
        """Test assigned policy allows all content."""
        cache = ContentCache(
            cache_dir=tmp_path / "cache",
            max_size_gb=1,
            policy="assigned",
        )
        await cache.initialize()

        assert await cache.should_cache("bootloaders", "ipxe.efi") is True
        assert await cache.should_cache("templates", "kickstart.ks") is True
        assert await cache.should_cache("images", "ubuntu.iso") is True

    @pytest.mark.asyncio
    async def test_mirror_policy_allows_all(self, tmp_path):
        """Test mirror policy allows everything."""
        cache = ContentCache(
            cache_dir=tmp_path / "cache",
            max_size_gb=1,
            policy="mirror",
        )
        await cache.initialize()

        assert await cache.should_cache("bootloaders", "ipxe.efi") is True
        assert await cache.should_cache("templates", "kickstart.ks") is True
        assert await cache.should_cache("images", "ubuntu.iso") is True

    @pytest.mark.asyncio
    async def test_pattern_policy(self, tmp_path):
        """Test pattern policy matches glob patterns."""
        cache = ContentCache(
            cache_dir=tmp_path / "cache",
            max_size_gb=1,
            policy="pattern",
            patterns=["bootloaders/*", "templates/kickstart/*", "images/ubuntu-*"],
        )
        await cache.initialize()

        # Matching patterns
        assert await cache.should_cache("bootloaders", "ipxe.efi") is True
        assert await cache.should_cache("templates", "kickstart/server.ks") is True
        assert await cache.should_cache("images", "ubuntu-24.04.iso") is True

        # Non-matching
        assert await cache.should_cache("templates", "preseed/base.cfg") is False
        assert await cache.should_cache("images", "windows.wim") is False


class TestCacheSizeLimit:
    """Tests for cache size limiting."""

    @pytest.mark.asyncio
    async def test_size_limit_enforcement(self, tmp_path):
        """Test cache enforces size limit via eviction."""
        # Very small cache for testing
        cache = ContentCache(
            cache_dir=tmp_path / "cache",
            max_size_gb=0,  # Will use bytes directly
            policy="assigned",
        )
        cache.max_size_bytes = 500  # 500 bytes max

        await cache.initialize()

        # Fill cache
        await cache.put("templates", "file1.txt", b"x" * 200)
        await cache.put("templates", "file2.txt", b"y" * 200)

        stats = await cache.get_stats()
        assert stats.total_size_bytes == 400

        # Adding more should trigger eviction
        await cache.put("templates", "file3.txt", b"z" * 200)

        stats = await cache.get_stats()
        # Should have evicted oldest to make room
        assert stats.total_size_bytes <= 500

    @pytest.mark.asyncio
    async def test_bootloaders_not_evicted(self, tmp_path):
        """Test bootloaders are never evicted for space."""
        cache = ContentCache(
            cache_dir=tmp_path / "cache",
            max_size_gb=0,
            policy="assigned",
        )
        cache.max_size_bytes = 300

        await cache.initialize()

        # Add bootloader (always_cache)
        await cache.put("bootloaders", "ipxe.efi", b"x" * 100)

        # Add template (can be evicted)
        await cache.put("templates", "file1.txt", b"y" * 100)

        # Add more templates to trigger eviction
        await cache.put("templates", "file2.txt", b"z" * 100)

        # Bootloader should still exist
        assert await cache.get("bootloaders", "ipxe.efi") is not None
