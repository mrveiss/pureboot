"""Heartbeat loop for site agent.

Manages periodic heartbeat sending to the central controller.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Callable, Awaitable

from src.agent.central_client import (
    CentralClient,
    AgentMetrics,
    HeartbeatResponse,
    HeartbeatError,
)

logger = logging.getLogger(__name__)


class HeartbeatLoop:
    """Manages periodic heartbeat to central controller."""

    def __init__(
        self,
        client: CentralClient,
        interval: int = 60,
        agent_version: str = "0.1.0",
        metrics_collector: Callable[[], AgentMetrics] | None = None,
        command_handler: Callable[[str, dict], Awaitable[None]] | None = None,
    ):
        """Initialize the heartbeat loop.

        Args:
            client: CentralClient instance for communication
            interval: Heartbeat interval in seconds
            agent_version: Version string of the agent
            metrics_collector: Optional callback to collect current metrics
            command_handler: Optional callback to handle commands from central
        """
        self.client = client
        self.interval = interval
        self.agent_version = agent_version
        self.metrics_collector = metrics_collector
        self.command_handler = command_handler

        self._running = False
        self._task: asyncio.Task | None = None
        self._start_time: float | None = None
        self._consecutive_failures = 0
        self._max_failures = 5  # Go to degraded mode after this many failures

        # Default service status
        self._services: dict[str, str] = {}

        # Boot metrics source (set by agent main)
        self._boot_metrics = None
        self._cache_manager = None

        # Cache sources (set by agent main)
        self._state_cache = None
        self._content_cache = None
        self._sync_service = None
        self._proxy = None

        # Offline sources (set by agent main)
        self._connectivity = None
        self._sync_queue = None
        self._conflict_detector = None

    def set_metrics_source(self, boot_metrics, cache_manager):
        """Set the boot metrics and cache manager for collecting real metrics."""
        self._boot_metrics = boot_metrics
        self._cache_manager = cache_manager

    def set_cache_sources(self, state_cache=None, content_cache=None, sync_service=None, proxy=None):
        """Set cache sources for comprehensive metrics collection."""
        self._state_cache = state_cache
        self._content_cache = content_cache
        self._sync_service = sync_service
        self._proxy = proxy

    def set_offline_sources(self, connectivity=None, sync_queue=None, conflict_detector=None):
        """Set offline operation sources for metrics collection."""
        self._connectivity = connectivity
        self._sync_queue = sync_queue
        self._conflict_detector = conflict_detector

    @property
    def uptime_seconds(self) -> int:
        """Get agent uptime in seconds."""
        if self._start_time is None:
            return 0
        return int(time.time() - self._start_time)

    def set_service_status(self, service: str, status: str):
        """Set status for a service (e.g., 'tftp': 'ok')."""
        self._services[service] = status

    async def collect_metrics_async(self) -> AgentMetrics:
        """Collect current agent metrics (async version for offline sources).

        Override metrics_collector in __init__ for custom metrics.
        """
        if self.metrics_collector:
            return self.metrics_collector()

        # Collect metrics from boot service if available
        nodes_seen = 0
        active_boots = 0
        cache_hit_rate = 0.0
        disk_usage_percent = 0.0
        last_sync_at = None
        pending_sync_items = 0
        conflicts_pending = 0
        is_online = True
        offline_duration_seconds = 0

        if self._boot_metrics:
            nodes_seen = self._boot_metrics.get_nodes_seen_count()
            active_boots = self._boot_metrics.active_boots
            cache_hit_rate = self._boot_metrics.get_cache_hit_rate()

        if self._cache_manager:
            disk_usage_percent = self._cache_manager.get_disk_usage_percent()

        # Additional cache metrics from content cache
        if self._content_cache:
            disk_usage_percent = self._content_cache.get_disk_usage_percent()

        # Sync service metrics
        if self._sync_service:
            last_sync_at = self._sync_service.last_sync_at

        # Proxy metrics (augment cache hit rate with proxy stats)
        if self._proxy:
            proxy_stats = self._proxy.metrics.get_stats()
            # Blend boot cache and proxy cache rates
            if proxy_stats["requests_total"] > 0:
                proxy_cache_rate = proxy_stats["cache_rate"]
                # Use proxy rate if no boot metrics, otherwise average
                if cache_hit_rate == 0.0:
                    cache_hit_rate = proxy_cache_rate
                else:
                    cache_hit_rate = (cache_hit_rate + proxy_cache_rate) / 2

        # Offline metrics
        if self._connectivity:
            is_online = self._connectivity.is_online
            offline_duration_seconds = self._connectivity.offline_duration_seconds

        if self._sync_queue:
            pending_sync_items = await self._sync_queue.get_pending_count()

        if self._conflict_detector:
            conflicts_pending = await self._conflict_detector.get_conflict_count()

        return AgentMetrics(
            agent_version=self.agent_version,
            uptime_seconds=self.uptime_seconds,
            services=self._services.copy(),
            nodes_seen_last_hour=nodes_seen,
            active_boots=active_boots,
            cache_hit_rate=cache_hit_rate,
            disk_usage_percent=disk_usage_percent,
            pending_sync_items=pending_sync_items,
            last_sync_at=last_sync_at,
            conflicts_pending=conflicts_pending,
            is_online=is_online,
            offline_duration_seconds=offline_duration_seconds,
        )

    def collect_metrics(self) -> AgentMetrics:
        """Collect current agent metrics (sync version - for backwards compatibility).

        Note: This version doesn't include async offline metrics.
        Use collect_metrics_async for full metrics.
        """
        if self.metrics_collector:
            return self.metrics_collector()

        # Collect metrics from boot service if available
        nodes_seen = 0
        active_boots = 0
        cache_hit_rate = 0.0
        disk_usage_percent = 0.0
        last_sync_at = None
        pending_sync_items = 0
        is_online = True
        offline_duration_seconds = 0

        if self._boot_metrics:
            nodes_seen = self._boot_metrics.get_nodes_seen_count()
            active_boots = self._boot_metrics.active_boots
            cache_hit_rate = self._boot_metrics.get_cache_hit_rate()

        if self._cache_manager:
            disk_usage_percent = self._cache_manager.get_disk_usage_percent()

        # Additional cache metrics from content cache
        if self._content_cache:
            disk_usage_percent = self._content_cache.get_disk_usage_percent()

        # Sync service metrics
        if self._sync_service:
            last_sync_at = self._sync_service.last_sync_at

        # Proxy metrics (augment cache hit rate with proxy stats)
        if self._proxy:
            proxy_stats = self._proxy.metrics.get_stats()
            # Blend boot cache and proxy cache rates
            if proxy_stats["requests_total"] > 0:
                proxy_cache_rate = proxy_stats["cache_rate"]
                # Use proxy rate if no boot metrics, otherwise average
                if cache_hit_rate == 0.0:
                    cache_hit_rate = proxy_cache_rate
                else:
                    cache_hit_rate = (cache_hit_rate + proxy_cache_rate) / 2

        # Offline metrics (sync versions)
        if self._connectivity:
            is_online = self._connectivity.is_online
            offline_duration_seconds = self._connectivity.offline_duration_seconds

        return AgentMetrics(
            agent_version=self.agent_version,
            uptime_seconds=self.uptime_seconds,
            services=self._services.copy(),
            nodes_seen_last_hour=nodes_seen,
            active_boots=active_boots,
            cache_hit_rate=cache_hit_rate,
            disk_usage_percent=disk_usage_percent,
            pending_sync_items=pending_sync_items,
            last_sync_at=last_sync_at,
            conflicts_pending=0,  # Async-only
            is_online=is_online,
            offline_duration_seconds=offline_duration_seconds,
        )

    async def _heartbeat_once(self) -> HeartbeatResponse | None:
        """Send a single heartbeat."""
        try:
            metrics = self.collect_metrics()
            response = await self.client.heartbeat(metrics)

            # Reset failure counter on success
            self._consecutive_failures = 0

            # Handle any commands from central
            if response.commands and self.command_handler:
                for cmd in response.commands:
                    try:
                        await self.command_handler(cmd.command, cmd.params)
                    except Exception as e:
                        logger.error(f"Error handling command {cmd.command}: {e}")

            return response

        except HeartbeatError as e:
            self._consecutive_failures += 1
            if self._consecutive_failures <= self._max_failures:
                logger.warning(f"Heartbeat failed ({self._consecutive_failures}): {e}")
            else:
                logger.error(
                    f"Heartbeat failed {self._consecutive_failures} times. "
                    "Central controller may be unreachable."
                )
            return None

        except Exception as e:
            self._consecutive_failures += 1
            logger.exception(f"Unexpected error during heartbeat: {e}")
            return None

    async def _run_loop(self):
        """Main heartbeat loop."""
        logger.info(f"Starting heartbeat loop (interval: {self.interval}s)")

        while self._running:
            await self._heartbeat_once()
            await asyncio.sleep(self.interval)

    async def start(self):
        """Start the heartbeat loop."""
        if self._running:
            logger.warning("Heartbeat loop already running")
            return

        self._running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Heartbeat loop started")

    async def stop(self):
        """Stop the heartbeat loop."""
        if not self._running:
            return

        logger.info("Stopping heartbeat loop...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Heartbeat loop stopped")

    @property
    def is_running(self) -> bool:
        """Check if heartbeat loop is running."""
        return self._running

    @property
    def is_connected(self) -> bool:
        """Check if recently connected to central (based on heartbeat success)."""
        return self._consecutive_failures < self._max_failures

    async def send_immediate(self) -> HeartbeatResponse | None:
        """Send an immediate heartbeat (outside regular interval)."""
        return await self._heartbeat_once()
