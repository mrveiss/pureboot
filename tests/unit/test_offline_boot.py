"""Tests for offline boot script generator."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.offline_boot import OfflineBootGenerator, OfflineBootScripts
from src.agent.cache.state_cache import CachedNode


@pytest.fixture
def mock_state_cache():
    """Create mock state cache."""
    cache = AsyncMock()
    cache.get_node = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def mock_content_cache():
    """Create mock content cache."""
    return AsyncMock()


@pytest.fixture
def generator(mock_state_cache, mock_content_cache):
    """Create offline boot generator for testing."""
    return OfflineBootGenerator(
        state_cache=mock_state_cache,
        content_cache=mock_content_cache,
        site_id="site-001",
        default_action="local",
    )


@pytest.fixture
def cached_node():
    """Create a sample cached node."""
    return CachedNode(
        mac_address="00:11:22:33:44:55",
        state="active",
        workflow_id="wf-001",
        group_id="group-001",
        cached_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        raw_data={"id": "node-001"},
    )


class TestOfflineBootGenerator:
    """Tests for OfflineBootGenerator class."""

    @pytest.mark.asyncio
    async def test_generate_from_cached_node(self, generator, mock_state_cache, cached_node):
        """Test generating script from cached node state."""
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "#!ipxe" in script
        assert "OFFLINE" in script
        assert "active" in script
        assert "sanboot" in script

    @pytest.mark.asyncio
    async def test_generate_for_unknown_node(self, generator, mock_state_cache):
        """Test generating script for unknown node."""
        mock_state_cache.get_node.return_value = None

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "#!ipxe" in script
        assert "OFFLINE" in script
        assert "not registered" in script
        assert "sanboot" in script

    @pytest.mark.asyncio
    async def test_generate_discovery_script(self, mock_state_cache, mock_content_cache):
        """Test discovery mode for unknown nodes."""
        generator = OfflineBootGenerator(
            state_cache=mock_state_cache,
            content_cache=mock_content_cache,
            site_id="site-001",
            default_action="discovery",
        )
        mock_state_cache.get_node.return_value = None

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "#!ipxe" in script
        assert "Discovery" in script
        assert "MAC Address:" in script

    @pytest.mark.asyncio
    async def test_generate_local_boot(self, generator, mock_state_cache, cached_node):
        """Test local boot for active nodes."""
        cached_node.state = "active"
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "sanboot" in script
        assert "active" in script.lower()

    @pytest.mark.asyncio
    async def test_offline_indicator_in_script(self, generator, mock_state_cache):
        """Test that offline indicator is present in script."""
        mock_state_cache.get_node.return_value = None

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "OFFLINE" in script
        assert "Central controller is unreachable" in script

    @pytest.mark.asyncio
    async def test_mac_normalization(self, generator, mock_state_cache, cached_node):
        """Test MAC address normalization."""
        mock_state_cache.get_node.return_value = cached_node

        # Test with different MAC formats
        await generator.generate_script("00-11-22-33-44-55")
        mock_state_cache.get_node.assert_called_with("00:11:22:33:44:55")

        await generator.generate_script("00:11:22:33:44:55")
        mock_state_cache.get_node.assert_called_with("00:11:22:33:44:55")

        await generator.generate_script("00:11:22:33:44:55")
        mock_state_cache.get_node.assert_called_with("00:11:22:33:44:55")

    @pytest.mark.asyncio
    async def test_state_discovered(self, generator, mock_state_cache, cached_node):
        """Test script for discovered state."""
        cached_node.state = "discovered"
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "discovered" in script
        assert "Cannot provision while offline" in script
        assert "sanboot" in script

    @pytest.mark.asyncio
    async def test_state_pending(self, generator, mock_state_cache, cached_node):
        """Test script for pending state."""
        cached_node.state = "pending"
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "pending" in script
        assert "Cannot provision while offline" in script

    @pytest.mark.asyncio
    async def test_state_installing_warning(self, generator, mock_state_cache, cached_node):
        """Test warning script for installing state."""
        cached_node.state = "installing"
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "installing" in script
        assert "WARNING" in script
        assert "Cannot continue installation" in script

    @pytest.mark.asyncio
    async def test_state_installed(self, generator, mock_state_cache, cached_node):
        """Test script for installed state."""
        cached_node.state = "installed"
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "installed" in script
        assert "sanboot" in script

    @pytest.mark.asyncio
    async def test_state_reprovision(self, generator, mock_state_cache, cached_node):
        """Test script for reprovision state."""
        cached_node.state = "reprovision"
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "reprovision" in script
        assert "Cannot reprovision while offline" in script

    @pytest.mark.asyncio
    async def test_state_retired(self, generator, mock_state_cache, cached_node):
        """Test script for retired state."""
        cached_node.state = "retired"
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "retired" in script
        assert "No boot action" in script

    @pytest.mark.asyncio
    async def test_unknown_state(self, generator, mock_state_cache, cached_node):
        """Test script for unknown state."""
        cached_node.state = "unknown_state"
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "unknown" in script.lower()
        assert "sanboot" in script

    @pytest.mark.asyncio
    async def test_offline_since_display(self, mock_state_cache, mock_content_cache):
        """Test offline duration is displayed."""
        offline_since = datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)
        generator = OfflineBootGenerator(
            state_cache=mock_state_cache,
            content_cache=mock_content_cache,
            site_id="site-001",
            offline_since=offline_since,
        )
        mock_state_cache.get_node.return_value = None

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "Offline Since:" in script
        assert "2h 30m" in script

    def test_set_offline_since(self, generator):
        """Test setting offline_since timestamp."""
        now = datetime.now(timezone.utc)
        generator.set_offline_since(now)
        assert generator.offline_since == now

    @pytest.mark.asyncio
    async def test_last_known_mode_with_cache(self, mock_state_cache, mock_content_cache, cached_node):
        """Test last_known mode uses cached state."""
        generator = OfflineBootGenerator(
            state_cache=mock_state_cache,
            content_cache=mock_content_cache,
            site_id="site-001",
            default_action="last_known",
        )
        mock_state_cache.get_node.return_value = cached_node

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "active" in script

    @pytest.mark.asyncio
    async def test_last_known_mode_without_cache(self, mock_state_cache, mock_content_cache):
        """Test last_known mode falls back to local when no cache."""
        generator = OfflineBootGenerator(
            state_cache=mock_state_cache,
            content_cache=mock_content_cache,
            site_id="site-001",
            default_action="last_known",
        )
        mock_state_cache.get_node.return_value = None

        script = await generator.generate_script("00:11:22:33:44:55")

        assert "not registered" in script
        assert "sanboot" in script


class TestOfflineBootScripts:
    """Tests for OfflineBootScripts static methods."""

    def test_local_boot_script(self):
        """Test generating local boot script."""
        script = OfflineBootScripts.local_boot(
            mac="00:11:22:33:44:55",
            site_id="site-001",
            reason="Offline mode",
        )

        assert "#!ipxe" in script
        assert "00:11:22:33:44:55" in script
        assert "site-001" in script
        assert "Offline mode" in script
        assert "sanboot" in script

    def test_local_boot_script_no_reason(self):
        """Test local boot script without reason."""
        script = OfflineBootScripts.local_boot(
            mac="00:11:22:33:44:55",
            site_id="site-001",
        )

        assert "#!ipxe" in script
        assert "Reason:" not in script

    def test_maintenance_mode_script(self):
        """Test generating maintenance mode script."""
        script = OfflineBootScripts.maintenance_mode(
            mac="00:11:22:33:44:55",
            site_id="site-001",
            message="Scheduled maintenance until 5 PM",
        )

        assert "#!ipxe" in script
        assert "MAINTENANCE MODE" in script
        assert "Scheduled maintenance until 5 PM" in script
        assert "sanboot" in script

    def test_maintenance_mode_default_message(self):
        """Test maintenance mode with default message."""
        script = OfflineBootScripts.maintenance_mode(
            mac="00:11:22:33:44:55",
            site_id="site-001",
        )

        assert "System under maintenance" in script

    def test_error_script(self):
        """Test generating error script."""
        script = OfflineBootScripts.error_script(
            mac="00:11:22:33:44:55",
            site_id="site-001",
            error="Database connection failed",
        )

        assert "#!ipxe" in script
        assert "ERROR" in script
        assert "Database connection failed" in script
        assert "sanboot" in script
