"""Agent boot service for serving PXE/iPXE boot files locally.

The boot service runs on site agents to:
- Serve iPXE boot scripts that redirect to central controller for node state
- Serve cached boot files (kernels, initrds, ISOs) from local cache
- Proxy uncached requests to central controller
- Serve from offline cache when central is unavailable
- Track boot request metrics for heartbeat
"""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TYPE_CHECKING

import aiohttp
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse, Response

from src.config import settings

if TYPE_CHECKING:
    from src.agent.connectivity import ConnectivityMonitor
    from src.agent.offline_boot import OfflineBootGenerator

logger = logging.getLogger(__name__)


class BootMetrics:
    """Track boot service metrics for heartbeat."""

    def __init__(self):
        self.nodes_seen: set[str] = set()
        self.active_boots: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self._lock = asyncio.Lock()
        self._last_reset = datetime.now(timezone.utc)

    async def record_boot_request(self, mac: str):
        """Record a boot request from a node."""
        async with self._lock:
            self.nodes_seen.add(mac)
            self.active_boots += 1

    async def complete_boot_request(self):
        """Mark a boot request as complete."""
        async with self._lock:
            self.active_boots = max(0, self.active_boots - 1)

    async def record_cache_hit(self):
        """Record a cache hit."""
        async with self._lock:
            self.cache_hits += 1

    async def record_cache_miss(self):
        """Record a cache miss."""
        async with self._lock:
            self.cache_misses += 1

    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    def get_nodes_seen_count(self) -> int:
        """Get count of unique nodes seen in the current period."""
        return len(self.nodes_seen)

    async def reset_period(self):
        """Reset period metrics (called after heartbeat)."""
        async with self._lock:
            self.nodes_seen.clear()
            self._last_reset = datetime.now(timezone.utc)


class CacheManager:
    """Manage cached boot files."""

    def __init__(self, cache_dir: Path, max_size_gb: int):
        self.cache_dir = Path(cache_dir)
        self.max_size_bytes = max_size_gb * 1024 * 1024 * 1024
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize cache directory."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "tftp").mkdir(exist_ok=True)
        (self.cache_dir / "http").mkdir(exist_ok=True)
        logger.info(f"Cache initialized at {self.cache_dir}")

    def get_cached_path(self, category: str, filename: str) -> Path:
        """Get path to cached file."""
        # Sanitize filename to prevent path traversal
        safe_name = filename.lstrip("/").replace("..", "")
        return self.cache_dir / category / safe_name

    async def is_cached(self, category: str, filename: str) -> bool:
        """Check if file is in cache."""
        path = self.get_cached_path(category, filename)
        return path.exists() and path.is_file()

    async def get_cached_file(self, category: str, filename: str) -> Path | None:
        """Get cached file path if it exists."""
        path = self.get_cached_path(category, filename)
        if path.exists() and path.is_file():
            return path
        return None

    async def cache_file(self, category: str, filename: str, content: bytes) -> Path:
        """Cache a file."""
        path = self.get_cached_path(category, filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically using temp file
        temp_path = path.with_suffix(".tmp")
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, temp_path.write_bytes, content)
            await loop.run_in_executor(None, temp_path.rename, path)
            logger.debug(f"Cached {category}/{filename} ({len(content)} bytes)")
            return path
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise e

    async def get_cache_size(self) -> int:
        """Get total cache size in bytes."""
        total = 0
        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def get_disk_usage_percent(self) -> float:
        """Get cache disk usage as percentage of max."""
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.cache_dir)
            return (used / total) * 100
        except Exception:
            return 0.0


class AgentBootService:
    """HTTP boot service for site agent with offline support."""

    def __init__(
        self,
        central_url: str,
        site_id: str,
        cache_manager: CacheManager,
        metrics: BootMetrics,
        connectivity: "ConnectivityMonitor | None" = None,
        offline_generator: "OfflineBootGenerator | None" = None,
    ):
        self.central_url = central_url.rstrip("/")
        self.site_id = site_id
        self.cache = cache_manager
        self.metrics = metrics
        self.connectivity = connectivity
        self.offline_generator = offline_generator
        self._http_session: aiohttp.ClientSession | None = None

    @property
    def is_online(self) -> bool:
        """Check if currently online."""
        if self.connectivity is None:
            return True  # Assume online if no monitor
        return self.connectivity.is_online

    def set_offline_components(
        self,
        connectivity: "ConnectivityMonitor",
        offline_generator: "OfflineBootGenerator",
    ):
        """Set offline operation components after initialization.

        Args:
            connectivity: Connectivity monitor
            offline_generator: Offline boot script generator
        """
        self.connectivity = connectivity
        self.offline_generator = offline_generator

    async def start(self):
        """Start the boot service."""
        await self.cache.initialize()
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        )
        logger.info("Agent boot service started")

    async def stop(self):
        """Stop the boot service."""
        if self._http_session:
            await self._http_session.close()
            self._http_session = None
        logger.info("Agent boot service stopped")

    async def get_boot_script(self, mac: str, request: Request) -> str:
        """Generate boot script for a node.

        The agent generates a boot script that chains to the central controller
        for node state and workflow information. When offline, uses cached state
        to generate boot scripts.
        """
        await self.metrics.record_boot_request(mac)

        # Extract hardware info from request
        hardware_info = self._extract_hardware_info(request)

        try:
            # Check if we know we're offline - use offline generator if available
            if not self.is_online and self.offline_generator:
                logger.info(f"Generating offline boot script for {mac}")
                return await self.offline_generator.generate_script(mac, hardware_info)

            # Online - proxy request to central controller for boot script
            url = f"{self.central_url}/api/v1/boot"
            params = {"mac": mac}

            # Forward hardware info if provided
            for key in ["vendor", "model", "serial", "uuid"]:
                if key in request.query_params:
                    params[key] = request.query_params[key]

            async with self._http_session.get(url, params=params) as resp:
                if resp.status == 200:
                    script = await resp.text()
                    # Rewrite central URLs to local agent URLs for cached files
                    script = self._rewrite_urls(script)
                    return script
                else:
                    logger.error(f"Central returned {resp.status} for boot request")
                    return self._generate_fallback_script(mac)

        except aiohttp.ClientError as e:
            logger.warning(f"Cannot reach central controller: {e}")
            # Try offline generator if available
            if self.offline_generator:
                return await self.offline_generator.generate_script(mac, hardware_info)
            return self._generate_offline_script(mac)

        finally:
            await self.metrics.complete_boot_request()

    def _extract_hardware_info(self, request: Request) -> dict:
        """Extract hardware information from request parameters.

        Args:
            request: FastAPI request object

        Returns:
            Dict with hardware info
        """
        info = {}
        for key in ["vendor", "model", "serial", "uuid"]:
            if key in request.query_params:
                info[key] = request.query_params[key]
        return info

    def _rewrite_urls(self, script: str) -> str:
        """Rewrite central URLs to local agent URLs for cached files.

        Files served from /tftp/ can be served from local cache.
        """
        # Replace central server URL with local agent URL for TFTP files
        local_server = f"http://{settings.host}:{settings.port}"
        script = script.replace(
            f"{self.central_url}/tftp/",
            f"{local_server}/tftp/"
        )
        return script

    def _generate_fallback_script(self, mac: str) -> str:
        """Generate fallback script when central returns error."""
        return f"""#!ipxe
# PureBoot Agent - Central Error
# MAC: {mac}
# Site: {self.site_id}

echo
echo *** PureBoot Site Agent ***
echo
echo   Central controller returned an error.
echo   Booting from local disk...
echo
sleep 3
exit
"""

    def _generate_offline_script(self, mac: str) -> str:
        """Generate offline script when central is unreachable."""
        return f"""#!ipxe
# PureBoot Agent - Offline Mode
# MAC: {mac}
# Site: {self.site_id}

echo
echo *** PureBoot Site Agent - Offline ***
echo
echo   Cannot reach central controller.
echo   Site agent is operating in offline mode.
echo   Booting from local disk...
echo
sleep 5
exit
"""

    async def serve_tftp_file(self, path: str) -> Response:
        """Serve a TFTP file from cache or proxy from central."""
        # Try cache first
        cached = await self.cache.get_cached_file("tftp", path)
        if cached:
            await self.metrics.record_cache_hit()
            content = cached.read_bytes()
            return Response(
                content=content,
                media_type="application/octet-stream",
            )

        # Cache miss - fetch from central
        await self.metrics.record_cache_miss()

        try:
            url = f"{self.central_url}/tftp/{path}"
            async with self._http_session.get(url) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    # Cache the file for future requests
                    await self.cache.cache_file("tftp", path, content)
                    return Response(
                        content=content,
                        media_type="application/octet-stream",
                    )
                elif resp.status == 404:
                    raise HTTPException(status_code=404, detail="File not found")
                else:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Central returned {resp.status}"
                    )

        except aiohttp.ClientError as e:
            logger.error(f"Cannot fetch {path} from central: {e}")
            raise HTTPException(
                status_code=503,
                detail="Cannot reach central controller"
            )


def create_agent_app(
    boot_service: AgentBootService,
    proxy=None,
    state_cache=None,
    content_cache=None,
    connectivity=None,
    sync_queue=None,
) -> FastAPI:
    """Create FastAPI app for agent boot services.

    Args:
        boot_service: Boot service instance
        proxy: Optional CentralProxy for node API proxying
        state_cache: Optional NodeStateCache for node caching
        content_cache: Optional ContentCache for content caching
        connectivity: Optional ConnectivityMonitor for offline detection
        sync_queue: Optional SyncQueue for offline operations
    """
    from src.agent.routes import nodes_router, cache_router
    from src.agent.routes.nodes import set_proxy as set_nodes_proxy
    from src.agent.routes.cache import set_caches

    app = FastAPI(
        title="PureBoot Site Agent",
        description="Local boot services for PureBoot site agent",
        version="0.2.0",  # Phase 4 version
    )

    # Configure node routes with proxy
    if proxy:
        set_nodes_proxy(proxy)
        app.include_router(nodes_router)

    # Configure cache routes
    if state_cache and content_cache:
        set_caches(content_cache, state_cache)
        app.include_router(cache_router)

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        health_data = {
            "status": "healthy",
            "mode": "agent",
            "site_id": boot_service.site_id,
            "cache_hit_rate": boot_service.metrics.get_cache_hit_rate(),
            "nodes_seen": boot_service.metrics.get_nodes_seen_count(),
            "disk_usage_percent": boot_service.cache.get_disk_usage_percent(),
        }

        # Add connectivity status if available
        if connectivity:
            health_data["is_online"] = connectivity.is_online
            health_data["offline_duration_seconds"] = connectivity.offline_duration_seconds
            if connectivity.last_online_at:
                health_data["last_online_at"] = connectivity.last_online_at.isoformat()

        # Add proxy metrics if available
        if proxy:
            health_data["proxy_stats"] = proxy.metrics.get_stats()

        # Add queue stats if available
        if sync_queue:
            health_data["queue_stats"] = await sync_queue.get_stats()

        return health_data

    @app.get("/api/v1/boot", response_class=PlainTextResponse)
    async def get_boot_script(mac: str, request: Request):
        """Return iPXE boot script for a node."""
        return await boot_service.get_boot_script(mac, request)

    @app.get("/tftp/{path:path}")
    async def serve_tftp(path: str):
        """Serve TFTP files from cache or proxy from central."""
        return await boot_service.serve_tftp_file(path)

    return app