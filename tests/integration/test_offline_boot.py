"""Integration tests for offline boot service functionality."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.agent.boot_service import (
    AgentBootService,
    BootMetrics,
    CacheManager,
    create_agent_app,
)


@pytest.fixture
def tmp_cache_dir(tmp_path):
    """Create temp cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def cache_manager(tmp_cache_dir):
    """Create cache manager."""
    return CacheManager(
        cache_dir=tmp_cache_dir,
        max_size_gb=1,
    )


@pytest.fixture
def boot_metrics():
    """Create boot metrics."""
    return BootMetrics()


@pytest.fixture
def mock_connectivity():
    """Create mock connectivity monitor."""
    conn = MagicMock()
    conn.is_online = True
    conn.offline_duration_seconds = 0
    conn.last_online_at = datetime.now(timezone.utc)
    return conn


@pytest.fixture
def mock_offline_generator():
    """Create mock offline boot generator."""
    gen = AsyncMock()
    gen.generate_script = AsyncMock(return_value="""#!ipxe
# PureBoot Agent - OFFLINE MODE
# MAC: 00:11:22:33:44:55
echo OFFLINE BOOT
sanboot --drive 0x80
""")
    return gen


@pytest.fixture
def boot_service(cache_manager, boot_metrics, mock_connectivity, mock_offline_generator):
    """Create boot service with offline components."""
    service = AgentBootService(
        central_url="http://central:8080",
        site_id="site-001",
        cache_manager=cache_manager,
        metrics=boot_metrics,
        connectivity=mock_connectivity,
        offline_generator=mock_offline_generator,
    )
    return service


class TestBootServiceOfflineIntegration:
    """Tests for boot service offline functionality."""

    def test_is_online_property(self, boot_service, mock_connectivity):
        """Test is_online property reflects connectivity."""
        mock_connectivity.is_online = True
        assert boot_service.is_online is True

        mock_connectivity.is_online = False
        assert boot_service.is_online is False

    def test_is_online_without_connectivity(self, cache_manager, boot_metrics):
        """Test is_online defaults to True without monitor."""
        service = AgentBootService(
            central_url="http://central:8080",
            site_id="site-001",
            cache_manager=cache_manager,
            metrics=boot_metrics,
        )
        assert service.is_online is True

    def test_set_offline_components(self, cache_manager, boot_metrics):
        """Test setting offline components after init."""
        service = AgentBootService(
            central_url="http://central:8080",
            site_id="site-001",
            cache_manager=cache_manager,
            metrics=boot_metrics,
        )

        mock_conn = MagicMock()
        mock_gen = AsyncMock()

        service.set_offline_components(mock_conn, mock_gen)

        assert service.connectivity is mock_conn
        assert service.offline_generator is mock_gen

    @pytest.mark.asyncio
    async def test_boot_uses_offline_generator_when_offline(
        self, boot_service, mock_connectivity, mock_offline_generator
    ):
        """Test boot script uses offline generator when offline."""
        mock_connectivity.is_online = False

        # Create mock request
        request = MagicMock()
        request.query_params = {}

        # Initialize service
        await boot_service.start()

        try:
            script = await boot_service.get_boot_script("00:11:22:33:44:55", request)

            mock_offline_generator.generate_script.assert_called_once()
            assert "OFFLINE" in script
        finally:
            await boot_service.stop()

    @pytest.mark.asyncio
    async def test_boot_falls_back_to_offline_on_error(
        self, boot_service, mock_connectivity, mock_offline_generator
    ):
        """Test boot falls back to offline generator on central error."""
        mock_connectivity.is_online = True  # Think we're online

        # Create mock request
        request = MagicMock()
        request.query_params = {}

        # Initialize service
        await boot_service.start()

        try:
            # Mock HTTP session to fail
            import aiohttp
            boot_service._http_session.get = MagicMock(
                side_effect=aiohttp.ClientError("Connection refused")
            )

            script = await boot_service.get_boot_script("00:11:22:33:44:55", request)

            # Should have used offline generator
            mock_offline_generator.generate_script.assert_called_once()
            assert "OFFLINE" in script
        finally:
            await boot_service.stop()

    @pytest.mark.asyncio
    async def test_boot_includes_offline_indicator(
        self, boot_service, mock_connectivity, mock_offline_generator
    ):
        """Test boot script includes offline indicator."""
        mock_connectivity.is_online = False

        request = MagicMock()
        request.query_params = {}

        await boot_service.start()

        try:
            script = await boot_service.get_boot_script("00:11:22:33:44:55", request)
            assert "OFFLINE" in script
        finally:
            await boot_service.stop()

    def test_extract_hardware_info(self, boot_service):
        """Test hardware info extraction from request."""
        request = MagicMock()
        request.query_params = {
            "vendor": "Dell",
            "model": "PowerEdge R640",
            "serial": "ABC123",
            "uuid": "1234-5678",
        }

        info = boot_service._extract_hardware_info(request)

        assert info["vendor"] == "Dell"
        assert info["model"] == "PowerEdge R640"
        assert info["serial"] == "ABC123"
        assert info["uuid"] == "1234-5678"

    def test_extract_hardware_info_partial(self, boot_service):
        """Test hardware info extraction with partial params."""
        request = MagicMock()
        request.query_params = {"vendor": "HP"}

        info = boot_service._extract_hardware_info(request)

        assert info == {"vendor": "HP"}
        assert "model" not in info


class TestAgentAppOffline:
    """Tests for FastAPI app with offline components."""

    @pytest.fixture
    def app(
        self,
        boot_service,
        mock_connectivity,
    ):
        """Create FastAPI app with offline components."""
        mock_queue = AsyncMock()
        mock_queue.get_stats = AsyncMock(return_value={
            "pending": 5,
            "processing": 1,
            "failed": 0,
            "total": 6,
        })

        return create_agent_app(
            boot_service=boot_service,
            connectivity=mock_connectivity,
            sync_queue=mock_queue,
        )

    def test_health_includes_connectivity_status(self, app, mock_connectivity):
        """Test health endpoint includes connectivity status."""
        mock_connectivity.is_online = True

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "is_online" in data
        assert data["is_online"] is True

    def test_health_includes_offline_duration(self, app, mock_connectivity):
        """Test health endpoint includes offline duration."""
        mock_connectivity.is_online = False
        mock_connectivity.offline_duration_seconds = 3600  # 1 hour

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["offline_duration_seconds"] == 3600

    def test_health_includes_queue_stats(self, app):
        """Test health endpoint includes queue stats."""
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "queue_stats" in data
        assert data["queue_stats"]["pending"] == 5

    @pytest.mark.asyncio
    async def test_boot_endpoint_offline(self, boot_service, mock_connectivity):
        """Test boot endpoint returns offline script."""
        mock_connectivity.is_online = False

        mock_queue = AsyncMock()
        mock_queue.get_stats = AsyncMock(return_value={"pending": 0, "total": 0})

        await boot_service.start()

        try:
            app = create_agent_app(
                boot_service=boot_service,
                connectivity=mock_connectivity,
                sync_queue=mock_queue,
            )

            client = TestClient(app)
            response = client.get("/api/v1/boot?mac=00:11:22:33:44:55")

            assert response.status_code == 200
            assert "OFFLINE" in response.text
        finally:
            await boot_service.stop()
