"""Client for communicating with central PureBoot controller.

This module provides the CentralClient class that handles:
- Agent registration with the central controller
- Periodic heartbeat sending
- Configuration retrieval
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration received from central controller after registration."""
    site_id: str
    site_name: str
    autonomy_level: str | None
    cache_policy: str | None
    cache_max_size_gb: int | None
    cache_retention_days: int | None
    heartbeat_interval: int
    sync_enabled: bool


@dataclass
class AgentMetrics:
    """Metrics sent to central controller with heartbeat."""
    agent_version: str
    uptime_seconds: int
    services: dict[str, str]
    nodes_seen_last_hour: int = 0
    active_boots: int = 0
    cache_hit_rate: float = 0.0
    disk_usage_percent: float = 0.0
    pending_sync_items: int = 0
    last_sync_at: datetime | None = None
    conflicts_pending: int = 0
    # Phase 4 offline metrics
    is_online: bool = True
    offline_duration_seconds: int = 0


@dataclass
class HeartbeatCommand:
    """Command received from central controller via heartbeat response."""
    command: str
    params: dict


@dataclass
class HeartbeatResponse:
    """Response received from heartbeat."""
    acknowledged: bool
    server_time: datetime
    commands: list[HeartbeatCommand]


class CentralClientError(Exception):
    """Base exception for central client errors."""
    pass


class RegistrationError(CentralClientError):
    """Error during agent registration."""
    pass


class HeartbeatError(CentralClientError):
    """Error during heartbeat."""
    pass


class CentralClient:
    """Client for communicating with central PureBoot controller."""

    def __init__(
        self,
        central_url: str,
        site_id: str,
        token: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize the central client.

        Args:
            central_url: Base URL of central controller (e.g., https://central.example.com)
            site_id: ID of the site this agent belongs to
            token: Registration token (required for initial registration)
            timeout: HTTP request timeout in seconds
        """
        self.central_url = central_url.rstrip("/")
        self.site_id = site_id
        self.token = token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def register(self, agent_url: str, agent_version: str) -> AgentConfig:
        """Register this agent with the central controller.

        Args:
            agent_url: URL where this agent can be reached
            agent_version: Version of the agent software

        Returns:
            AgentConfig with site configuration

        Raises:
            RegistrationError: If registration fails
        """
        if not self.token:
            raise RegistrationError("Registration token is required")

        client = await self._get_client()
        url = f"{self.central_url}/api/v1/agents/register"

        try:
            response = await client.post(
                url,
                json={
                    "site_id": self.site_id,
                    "token": self.token,
                    "agent_url": agent_url,
                    "agent_version": agent_version,
                    "capabilities": ["tftp", "http"],
                },
            )

            if response.status_code == 401:
                raise RegistrationError("Invalid registration token")
            elif response.status_code == 404:
                raise RegistrationError(f"Site {self.site_id} not found")
            elif response.status_code != 200:
                raise RegistrationError(
                    f"Registration failed: {response.status_code} - {response.text}"
                )

            data = response.json()
            config = data["config"]

            return AgentConfig(
                site_id=config["site_id"],
                site_name=config["site_name"],
                autonomy_level=config.get("autonomy_level"),
                cache_policy=config.get("cache_policy"),
                cache_max_size_gb=config.get("cache_max_size_gb"),
                cache_retention_days=config.get("cache_retention_days"),
                heartbeat_interval=config.get("heartbeat_interval", 60),
                sync_enabled=config.get("sync_enabled", True),
            )

        except httpx.RequestError as e:
            raise RegistrationError(f"Connection error: {e}")

    async def heartbeat(self, metrics: AgentMetrics) -> HeartbeatResponse:
        """Send heartbeat to central controller.

        Args:
            metrics: Current agent metrics

        Returns:
            HeartbeatResponse with acknowledgement and any commands

        Raises:
            HeartbeatError: If heartbeat fails
        """
        client = await self._get_client()
        url = f"{self.central_url}/api/v1/agents/heartbeat"

        try:
            response = await client.post(
                url,
                json={
                    "site_id": self.site_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent_version": metrics.agent_version,
                    "uptime_seconds": metrics.uptime_seconds,
                    "services": metrics.services,
                    "nodes_seen_last_hour": metrics.nodes_seen_last_hour,
                    "active_boots": metrics.active_boots,
                    "cache_hit_rate": metrics.cache_hit_rate,
                    "disk_usage_percent": metrics.disk_usage_percent,
                    "pending_sync_items": metrics.pending_sync_items,
                    "last_sync_at": metrics.last_sync_at.isoformat() if metrics.last_sync_at else None,
                    "conflicts_pending": metrics.conflicts_pending,
                },
            )

            if response.status_code == 404:
                raise HeartbeatError(f"Site {self.site_id} not found")
            elif response.status_code != 200:
                raise HeartbeatError(
                    f"Heartbeat failed: {response.status_code} - {response.text}"
                )

            data = response.json()

            commands = [
                HeartbeatCommand(
                    command=cmd["command"],
                    params=cmd.get("params", {}),
                )
                for cmd in data.get("commands", [])
            ]

            return HeartbeatResponse(
                acknowledged=data.get("acknowledged", True),
                server_time=datetime.fromisoformat(data["server_time"].replace("Z", "+00:00")),
                commands=commands,
            )

        except httpx.RequestError as e:
            raise HeartbeatError(f"Connection error: {e}")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
