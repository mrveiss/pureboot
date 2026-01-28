"""Tests for the central client."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from src.agent.central_client import (
    CentralClient,
    AgentConfig,
    AgentMetrics,
    HeartbeatResponse,
    RegistrationError,
    HeartbeatError,
)


class TestCentralClientInit:
    """Test CentralClient initialization."""

    def test_init_with_required_params(self):
        """Client initializes with required parameters."""
        client = CentralClient(
            central_url="https://central.example.com",
            site_id="site-123",
        )
        assert client.central_url == "https://central.example.com"
        assert client.site_id == "site-123"
        assert client.token is None

    def test_init_with_token(self):
        """Client initializes with registration token."""
        client = CentralClient(
            central_url="https://central.example.com",
            site_id="site-123",
            token="secret-token",
        )
        assert client.token == "secret-token"

    def test_url_trailing_slash_stripped(self):
        """Trailing slash is stripped from URL."""
        client = CentralClient(
            central_url="https://central.example.com/",
            site_id="site-123",
        )
        assert client.central_url == "https://central.example.com"


class TestCentralClientRegister:
    """Test agent registration."""

    @pytest.mark.asyncio
    async def test_register_requires_token(self):
        """Registration fails without token."""
        client = CentralClient(
            central_url="https://central.example.com",
            site_id="site-123",
        )

        with pytest.raises(RegistrationError) as exc_info:
            await client.register("https://agent.local:8443", "0.1.0")

        assert "token is required" in str(exc_info.value)


class TestAgentMetrics:
    """Test AgentMetrics dataclass."""

    def test_metrics_creation(self):
        """Can create metrics with all fields."""
        metrics = AgentMetrics(
            agent_version="0.1.0",
            uptime_seconds=3600,
            services={"tftp": "ok", "http": "ok"},
            nodes_seen_last_hour=10,
            active_boots=2,
            cache_hit_rate=0.85,
            disk_usage_percent=45.5,
        )
        assert metrics.agent_version == "0.1.0"
        assert metrics.uptime_seconds == 3600
        assert metrics.services["tftp"] == "ok"
        assert metrics.cache_hit_rate == 0.85

    def test_metrics_defaults(self):
        """Metrics have sensible defaults."""
        metrics = AgentMetrics(
            agent_version="0.1.0",
            uptime_seconds=0,
            services={},
        )
        assert metrics.nodes_seen_last_hour == 0
        assert metrics.active_boots == 0
        assert metrics.cache_hit_rate == 0.0


class TestAgentConfig:
    """Test AgentConfig dataclass."""

    def test_config_creation(self):
        """Can create config with all fields."""
        config = AgentConfig(
            site_id="site-123",
            site_name="Datacenter West",
            autonomy_level="limited",
            cache_policy="assigned",
            cache_max_size_gb=100,
            cache_retention_days=30,
            heartbeat_interval=60,
            sync_enabled=True,
        )
        assert config.site_id == "site-123"
        assert config.site_name == "Datacenter West"
        assert config.autonomy_level == "limited"
        assert config.heartbeat_interval == 60
