"""Tests for agent boot service components."""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.boot_service import (
    BootMetrics,
    CacheManager,
    AgentBootService,
    create_agent_app,
)


class TestBootMetrics:
    """Tests for BootMetrics class."""

    def test_initial_state(self):
        """Test initial metrics state."""
        metrics = BootMetrics()
        assert metrics.get_nodes_seen_count() == 0
        assert metrics.active_boots == 0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
        assert metrics.get_cache_hit_rate() == 0.0

    @pytest.mark.asyncio
    async def test_record_boot_request(self):
        """Test recording boot requests."""
        metrics = BootMetrics()

        await metrics.record_boot_request("00:11:22:33:44:55")
        assert metrics.get_nodes_seen_count() == 1
        assert metrics.active_boots == 1

        await metrics.record_boot_request("00:11:22:33:44:66")
        assert metrics.get_nodes_seen_count() == 2
        assert metrics.active_boots == 2

        # Same MAC doesn't increase count
        await metrics.record_boot_request("00:11:22:33:44:55")
        assert metrics.get_nodes_seen_count() == 2
        assert metrics.active_boots == 3

    @pytest.mark.asyncio
    async def test_complete_boot_request(self):
        """Test completing boot requests."""
        metrics = BootMetrics()

        await metrics.record_boot_request("00:11:22:33:44:55")
        assert metrics.active_boots == 1

        await metrics.complete_boot_request()
        assert metrics.active_boots == 0

        # Should not go negative
        await metrics.complete_boot_request()
        assert metrics.active_boots == 0

    @pytest.mark.asyncio
    async def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        metrics = BootMetrics()

        await metrics.record_cache_hit()
        await metrics.record_cache_hit()
        await metrics.record_cache_miss()

        # 2 hits / 3 total = 0.666...
        assert abs(metrics.get_cache_hit_rate() - 0.6666) < 0.01

    @pytest.mark.asyncio
    async def test_reset_period(self):
        """Test resetting period metrics."""
        metrics = BootMetrics()

        await metrics.record_boot_request("00:11:22:33:44:55")
        await metrics.record_cache_hit()

        await metrics.reset_period()
        assert metrics.get_nodes_seen_count() == 0
        # Cache stats are not reset (cumulative)
        assert metrics.cache_hits == 1


class TestCacheManager:
    """Tests for CacheManager class."""

    @pytest.mark.asyncio
    async def test_initialize(self, tmp_path):
        """Test cache initialization."""
        cache_dir = tmp_path / "cache"
        manager = CacheManager(cache_dir=cache_dir, max_size_gb=10)

        await manager.initialize()

        assert cache_dir.exists()
        assert (cache_dir / "tftp").exists()
        assert (cache_dir / "http").exists()

    def test_get_cached_path(self, tmp_path):
        """Test getting cached file path."""
        manager = CacheManager(cache_dir=tmp_path, max_size_gb=10)

        path = manager.get_cached_path("tftp", "bios/pxelinux.0")
        assert path == tmp_path / "tftp" / "bios/pxelinux.0"

        # Test path traversal prevention
        path = manager.get_cached_path("tftp", "../../../etc/passwd")
        assert ".." not in str(path)

    @pytest.mark.asyncio
    async def test_cache_file(self, tmp_path):
        """Test caching a file."""
        manager = CacheManager(cache_dir=tmp_path, max_size_gb=10)
        await manager.initialize()

        content = b"test file content"
        path = await manager.cache_file("tftp", "test.bin", content)

        assert path.exists()
        assert path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_is_cached(self, tmp_path):
        """Test checking if file is cached."""
        manager = CacheManager(cache_dir=tmp_path, max_size_gb=10)
        await manager.initialize()

        assert not await manager.is_cached("tftp", "test.bin")

        await manager.cache_file("tftp", "test.bin", b"content")

        assert await manager.is_cached("tftp", "test.bin")

    @pytest.mark.asyncio
    async def test_get_cached_file(self, tmp_path):
        """Test getting cached file."""
        manager = CacheManager(cache_dir=tmp_path, max_size_gb=10)
        await manager.initialize()

        # File doesn't exist
        result = await manager.get_cached_file("tftp", "test.bin")
        assert result is None

        # Cache the file
        await manager.cache_file("tftp", "test.bin", b"content")

        # File exists
        result = await manager.get_cached_file("tftp", "test.bin")
        assert result is not None
        assert result.read_bytes() == b"content"

    @pytest.mark.asyncio
    async def test_get_cache_size(self, tmp_path):
        """Test getting cache size."""
        manager = CacheManager(cache_dir=tmp_path, max_size_gb=10)
        await manager.initialize()

        # Initially empty
        size = await manager.get_cache_size()
        assert size == 0

        # Add some files
        await manager.cache_file("tftp", "file1.bin", b"x" * 100)
        await manager.cache_file("tftp", "file2.bin", b"y" * 200)

        size = await manager.get_cache_size()
        assert size == 300


class TestAgentBootService:
    """Tests for AgentBootService class."""

    @pytest.fixture
    def mock_cache_manager(self, tmp_path):
        """Create a mock cache manager."""
        manager = CacheManager(cache_dir=tmp_path / "cache", max_size_gb=10)
        return manager

    @pytest.fixture
    def boot_metrics(self):
        """Create boot metrics instance."""
        return BootMetrics()

    @pytest.fixture
    def boot_service(self, mock_cache_manager, boot_metrics):
        """Create boot service instance."""
        return AgentBootService(
            central_url="http://central.example.com",
            site_id="site-001",
            cache_manager=mock_cache_manager,
            metrics=boot_metrics,
        )

    def test_rewrite_urls(self, boot_service):
        """Test URL rewriting from central to local."""
        script = """#!ipxe
kernel http://central.example.com/tftp/vmlinuz
initrd http://central.example.com/tftp/initrd
"""
        # Patch settings for test
        with patch("src.agent.boot_service.settings") as mock_settings:
            mock_settings.host = "192.168.1.100"
            mock_settings.port = 8080

            result = boot_service._rewrite_urls(script)

            assert "http://192.168.1.100:8080/tftp/vmlinuz" in result
            assert "http://192.168.1.100:8080/tftp/initrd" in result
            assert "central.example.com/tftp" not in result

    def test_generate_fallback_script(self, boot_service):
        """Test fallback script generation."""
        script = boot_service._generate_fallback_script("00:11:22:33:44:55")

        assert "#!ipxe" in script
        assert "00:11:22:33:44:55" in script
        assert "site-001" in script
        assert "Central Error" in script or "error" in script.lower()
        assert "exit" in script

    def test_generate_offline_script(self, boot_service):
        """Test offline script generation."""
        script = boot_service._generate_offline_script("00:11:22:33:44:55")

        assert "#!ipxe" in script
        assert "00:11:22:33:44:55" in script
        assert "site-001" in script
        assert "Offline" in script
        assert "exit" in script


class TestCreateAgentApp:
    """Tests for create_agent_app function."""

    @pytest.fixture
    def app(self, tmp_path):
        """Create test app."""
        cache_manager = CacheManager(cache_dir=tmp_path / "cache", max_size_gb=10)
        metrics = BootMetrics()
        boot_service = AgentBootService(
            central_url="http://central.example.com",
            site_id="site-001",
            cache_manager=cache_manager,
            metrics=metrics,
        )
        return create_agent_app(boot_service)

    def test_app_created(self, app):
        """Test app is created with expected properties."""
        assert app.title == "PureBoot Site Agent"

        # Check routes exist
        routes = [route.path for route in app.routes]
        assert "/health" in routes
        assert "/api/v1/boot" in routes
        assert "/tftp/{path:path}" in routes
