"""Connectivity monitor for tracking connection to central controller.

The connectivity monitor:
- Periodically checks if central controller is reachable
- Tracks online/offline state transitions
- Notifies listeners when connectivity changes
- Provides offline duration tracking
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Awaitable

import aiohttp

logger = logging.getLogger(__name__)


class ConnectivityMonitor:
    """Monitors connection to central controller."""

    def __init__(
        self,
        central_url: str,
        check_interval: int = 30,
        timeout: float = 5.0,
        failure_threshold: int = 3,
    ):
        """Initialize connectivity monitor.

        Args:
            central_url: Base URL of central controller
            check_interval: Seconds between connectivity checks
            timeout: Timeout for health check requests
            failure_threshold: Consecutive failures before marking offline
        """
        self.central_url = central_url.rstrip("/")
        self.check_interval = check_interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold

        self._is_online = True  # Assume online initially
        self._last_online_at: datetime | None = None
        self._offline_since: datetime | None = None
        self._consecutive_failures = 0
        self._consecutive_successes = 0

        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._listeners: list[Callable[[bool], Awaitable[None]]] = []

    @property
    def is_online(self) -> bool:
        """Check if currently connected to central."""
        return self._is_online

    @property
    def last_online_at(self) -> datetime | None:
        """When was last successful connection."""
        return self._last_online_at

    @property
    def offline_since(self) -> datetime | None:
        """When did we go offline (None if online)."""
        return self._offline_since

    @property
    def offline_duration(self) -> timedelta | None:
        """How long have we been offline."""
        if self._is_online or self._offline_since is None:
            return None
        return datetime.now(timezone.utc) - self._offline_since

    @property
    def offline_duration_seconds(self) -> int:
        """Offline duration in seconds."""
        duration = self.offline_duration
        if duration is None:
            return 0
        return int(duration.total_seconds())

    def add_listener(self, callback: Callable[[bool], Awaitable[None]]):
        """Add callback for connectivity changes.

        Callback receives True when going online, False when going offline.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[bool], Awaitable[None]]):
        """Remove a connectivity change callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def _notify_listeners(self, is_online: bool):
        """Notify all listeners of connectivity change."""
        for listener in self._listeners:
            try:
                await listener(is_online)
            except Exception as e:
                logger.error(f"Error in connectivity listener: {e}")

    async def check_connectivity(self) -> bool:
        """Perform connectivity check.

        Returns:
            True if central is reachable, False otherwise
        """
        if not self._session:
            return False

        try:
            url = f"{self.central_url}/health"
            async with self._session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status == 200:
                    return True
                logger.debug(f"Health check returned {resp.status}")
                return False
        except aiohttp.ClientError as e:
            logger.debug(f"Connectivity check failed: {e}")
            return False
        except asyncio.TimeoutError:
            logger.debug("Connectivity check timed out")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in connectivity check: {e}")
            return False

    async def _update_state(self, check_result: bool):
        """Update online/offline state based on check result."""
        now = datetime.now(timezone.utc)
        was_online = self._is_online

        if check_result:
            # Success
            self._consecutive_failures = 0
            self._consecutive_successes += 1
            self._last_online_at = now

            # Go online after one success (quick recovery)
            if not self._is_online:
                self._is_online = True
                self._offline_since = None
                logger.info("Connectivity restored to central controller")
                await self._notify_listeners(True)

        else:
            # Failure
            self._consecutive_successes = 0
            self._consecutive_failures += 1

            # Go offline after threshold failures
            if self._is_online and self._consecutive_failures >= self.failure_threshold:
                self._is_online = False
                self._offline_since = now
                logger.warning(
                    f"Lost connectivity to central controller "
                    f"(after {self._consecutive_failures} failures)"
                )
                await self._notify_listeners(False)

    async def _run_loop(self):
        """Main monitoring loop."""
        logger.info(
            f"Connectivity monitor started (interval={self.check_interval}s, "
            f"threshold={self.failure_threshold})"
        )

        while self._running:
            result = await self.check_connectivity()
            await self._update_state(result)

            await asyncio.sleep(self.check_interval)

    async def start(self):
        """Start the connectivity monitor."""
        if self._running:
            logger.warning("Connectivity monitor already running")
            return

        self._session = aiohttp.ClientSession()
        self._running = True
        self._last_online_at = datetime.now(timezone.utc)

        # Do initial check
        result = await self.check_connectivity()
        await self._update_state(result)

        # Start monitoring loop
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Connectivity monitor started")

    async def stop(self):
        """Stop the connectivity monitor."""
        if not self._running:
            return

        logger.info("Stopping connectivity monitor...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._session:
            await self._session.close()
            self._session = None

        logger.info("Connectivity monitor stopped")

    async def force_check(self) -> bool:
        """Force an immediate connectivity check.

        Returns:
            Current online status after check
        """
        result = await self.check_connectivity()
        await self._update_state(result)
        return self._is_online
