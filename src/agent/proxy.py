"""API proxy service for forwarding requests to central controller.

The proxy service:
- Forwards node API requests to central controller
- Caches responses in local state cache
- Serves from cache when central is unavailable
- Queues operations when offline for later sync
- Tracks request metrics
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

import aiohttp
from pydantic import BaseModel

from src.agent.cache.state_cache import NodeStateCache, CachedNode
from src.agent.cache.content_cache import ContentCache

if TYPE_CHECKING:
    from src.agent.connectivity import ConnectivityMonitor
    from src.agent.queue import SyncQueue, QueueItem

logger = logging.getLogger(__name__)


class ProxyError(Exception):
    """Error during proxy operation."""
    pass


class CentralUnavailableError(ProxyError):
    """Central controller is unavailable."""
    pass


class ProxyResponse(BaseModel):
    """Response from proxy request."""
    status_code: int
    data: dict | list | None = None
    error: str | None = None
    from_cache: bool = False
    cached_at: datetime | None = None


class ProxyMetrics:
    """Tracks proxy request metrics."""

    def __init__(self):
        self.requests_total: int = 0
        self.requests_proxied: int = 0
        self.requests_from_cache: int = 0
        self.requests_queued: int = 0
        self.requests_failed: int = 0
        self.central_errors: int = 0
        self._lock = asyncio.Lock()

    async def record_request(
        self,
        from_cache: bool = False,
        queued: bool = False,
        failed: bool = False,
    ):
        """Record a proxy request."""
        async with self._lock:
            self.requests_total += 1
            if failed:
                self.requests_failed += 1
            elif queued:
                self.requests_queued += 1
            elif from_cache:
                self.requests_from_cache += 1
            else:
                self.requests_proxied += 1

    async def record_central_error(self):
        """Record a central controller error."""
        async with self._lock:
            self.central_errors += 1

    def get_stats(self) -> dict:
        """Get metrics stats."""
        return {
            "requests_total": self.requests_total,
            "requests_proxied": self.requests_proxied,
            "requests_from_cache": self.requests_from_cache,
            "requests_queued": self.requests_queued,
            "requests_failed": self.requests_failed,
            "central_errors": self.central_errors,
            "cache_rate": (
                self.requests_from_cache / self.requests_total
                if self.requests_total > 0
                else 0.0
            ),
        }


class CentralProxy:
    """Proxies API requests to central controller with caching and offline support."""

    def __init__(
        self,
        central_url: str,
        state_cache: NodeStateCache,
        content_cache: ContentCache,
        site_id: str,
        timeout: float = 30.0,
        connectivity: "ConnectivityMonitor | None" = None,
        queue: "SyncQueue | None" = None,
    ):
        """Initialize the proxy.

        Args:
            central_url: Base URL of central controller
            state_cache: Node state cache
            content_cache: Content cache
            site_id: This agent's site ID
            timeout: Request timeout in seconds
            connectivity: Optional connectivity monitor for offline detection
            queue: Optional sync queue for offline operations
        """
        self.central_url = central_url.rstrip("/")
        self.state_cache = state_cache
        self.content_cache = content_cache
        self.site_id = site_id
        self.timeout = timeout
        self.connectivity = connectivity
        self.queue = queue
        self.metrics = ProxyMetrics()
        self._session: aiohttp.ClientSession | None = None

    @property
    def is_online(self) -> bool:
        """Check if currently online."""
        if self.connectivity is None:
            return True  # Assume online if no monitor
        return self.connectivity.is_online

    def set_offline_components(
        self,
        connectivity: "ConnectivityMonitor",
        queue: "SyncQueue",
    ):
        """Set offline operation components after initialization.

        Args:
            connectivity: Connectivity monitor
            queue: Sync queue
        """
        self.connectivity = connectivity
        self.queue = queue

    async def start(self):
        """Start the proxy (initialize HTTP session)."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        await self.state_cache.initialize()
        await self.content_cache.initialize()
        logger.info(f"Central proxy started (central={self.central_url})")

    async def stop(self):
        """Stop the proxy."""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Central proxy stopped")

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> tuple[int, dict | list | None]:
        """Make HTTP request to central.

        Returns:
            Tuple of (status_code, response_data)

        Raises:
            CentralUnavailableError: If central is unreachable
        """
        url = f"{self.central_url}{path}"

        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json_body,
            ) as resp:
                status = resp.status
                try:
                    data = await resp.json()
                except aiohttp.ContentTypeError:
                    data = None
                return status, data

        except aiohttp.ClientError as e:
            await self.metrics.record_central_error()
            raise CentralUnavailableError(f"Central unavailable: {e}") from e

    async def proxy_request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: dict | None = None,
        cache_key: str | None = None,
    ) -> ProxyResponse:
        """Proxy request to central controller.

        Args:
            method: HTTP method
            path: API path (e.g., /api/v1/nodes)
            params: Query parameters
            body: Request body for POST/PATCH
            cache_key: Optional key for caching GET responses

        Returns:
            ProxyResponse with result
        """
        try:
            status, data = await self._request(method, path, params, body)
            await self.metrics.record_request()

            return ProxyResponse(
                status_code=status,
                data=data,
                from_cache=False,
            )

        except CentralUnavailableError as e:
            await self.metrics.record_request(failed=True)
            return ProxyResponse(
                status_code=503,
                error=str(e),
                from_cache=False,
            )

    async def get_node_by_mac(self, mac: str) -> CachedNode | None:
        """Get node by MAC address, checking cache first.

        Args:
            mac: MAC address (any format)

        Returns:
            CachedNode if found, None otherwise
        """
        mac = mac.lower().replace("-", ":")

        # Check cache first
        cached = await self.state_cache.get_node(mac)
        if cached and not cached.is_expired:
            await self.metrics.record_request(from_cache=True)
            logger.debug(f"Serving node {mac} from cache")
            return cached

        # Fetch from central
        try:
            status, data = await self._request(
                "GET",
                "/api/v1/nodes",
                params={"mac": mac},
            )

            if status == 200 and data:
                # Handle list response (search by MAC)
                if isinstance(data, list) and len(data) > 0:
                    node_data = data[0]
                elif isinstance(data, dict):
                    node_data = data
                else:
                    await self.metrics.record_request()
                    return None

                # Cache the response
                node = await self.state_cache.set_node(
                    mac_address=mac,
                    node_id=node_data.get("id"),
                    state=node_data.get("state", "discovered"),
                    workflow_id=node_data.get("workflow_id"),
                    group_id=node_data.get("group_id"),
                    ip_address=node_data.get("ip_address"),
                    vendor=node_data.get("vendor"),
                    model=node_data.get("model"),
                    raw_data=node_data,
                )
                await self.metrics.record_request()
                return node

            await self.metrics.record_request()
            return None

        except CentralUnavailableError:
            # Central unavailable - return stale cache if available
            if cached:
                logger.warning(f"Central unavailable, serving stale cache for {mac}")
                await self.metrics.record_request(from_cache=True)
                return cached

            await self.metrics.record_request(failed=True)
            return None

    async def register_node(
        self,
        registration: dict | None = None,
        mac_address: str | None = None,
        ip_address: str | None = None,
        vendor: str | None = None,
        model: str | None = None,
        serial_number: str | None = None,
        system_uuid: str | None = None,
        offline_sync: bool = False,
    ) -> dict:
        """Proxy node registration to central.

        Args:
            registration: Full registration dict (from queue processing)
            mac_address: Node MAC address
            ip_address: Node IP address
            vendor: Hardware vendor
            model: Hardware model
            serial_number: Serial number
            system_uuid: System UUID
            offline_sync: True if called from queue processor (skip queueing)

        Returns:
            Dict with registration result
        """
        # Build registration from params if not provided
        if registration is None:
            registration = {
                "mac_address": mac_address,
                "ip_address": ip_address,
                "vendor": vendor,
                "model": model,
                "serial_number": serial_number,
                "system_uuid": system_uuid,
                "site_id": self.site_id,
            }
            # Remove None values
            registration = {k: v for k, v in registration.items() if v is not None}

        mac = registration.get("mac_address", mac_address)

        # Check if offline and should queue
        if not self.is_online and self.queue and not offline_sync:
            # Queue for later sync
            from src.agent.queue import QueueItem
            item = QueueItem(
                id=str(uuid.uuid4()),
                item_type="registration",
                payload=registration,
                created_at=datetime.now(timezone.utc),
            )
            await self.queue.enqueue(item)
            await self.metrics.record_request(queued=True)
            logger.info(f"Queued registration for {mac} (offline)")
            return {"status": "queued", "offline": True, "queue_id": item.id}

        # Online - proxy to central
        response = await self.proxy_request(
            "POST",
            "/api/v1/nodes/register",
            body=registration,
        )

        # Cache successful registration
        if response.status_code in (200, 201) and response.data:
            await self.state_cache.set_node(
                mac_address=mac,
                node_id=response.data.get("id"),
                state=response.data.get("state", "discovered"),
                workflow_id=response.data.get("workflow_id"),
                group_id=response.data.get("group_id"),
                ip_address=registration.get("ip_address"),
                vendor=registration.get("vendor"),
                model=registration.get("model"),
                raw_data=response.data,
            )
            return {"success": True, **response.data}

        return {
            "success": False,
            "status_code": response.status_code,
            "error": response.error,
        }

    async def update_node_state(
        self,
        node_id: str,
        new_state: str,
        mac_address: str | None = None,
        offline_sync: bool = False,
    ) -> dict:
        """Proxy node state update to central.

        Args:
            node_id: Node ID
            new_state: New state
            mac_address: Optional MAC for cache update
            offline_sync: True if called from queue processor (skip queueing)

        Returns:
            Dict with update result
        """
        # Check if offline and should queue
        if not self.is_online and self.queue and not offline_sync:
            # Queue for later sync
            from src.agent.queue import QueueItem
            item = QueueItem(
                id=str(uuid.uuid4()),
                item_type="state_update",
                payload={
                    "node_id": node_id,
                    "new_state": new_state,
                    "mac_address": mac_address,
                },
                created_at=datetime.now(timezone.utc),
            )
            await self.queue.enqueue(item)
            await self.metrics.record_request(queued=True)
            logger.info(f"Queued state update for {node_id} -> {new_state} (offline)")

            # Update local cache even when offline
            if mac_address:
                cached = await self.state_cache.get_node(mac_address)
                if cached:
                    await self.state_cache.set_node(
                        mac_address=mac_address,
                        node_id=node_id,
                        state=new_state,
                        workflow_id=cached.workflow_id,
                        group_id=cached.group_id,
                        ip_address=cached.ip_address,
                        vendor=cached.vendor,
                        model=cached.model,
                        raw_data=cached.raw_data,
                    )

            return {"status": "queued", "offline": True, "queue_id": item.id}

        # Online - proxy to central
        response = await self.proxy_request(
            "PATCH",
            f"/api/v1/nodes/{node_id}/state",
            body={"state": new_state},
        )

        # Update cache on success
        if response.status_code == 200:
            if mac_address:
                cached = await self.state_cache.get_node(mac_address)
                if cached:
                    await self.state_cache.set_node(
                        mac_address=mac_address,
                        node_id=node_id,
                        state=new_state,
                        workflow_id=cached.workflow_id,
                        group_id=cached.group_id,
                        ip_address=cached.ip_address,
                        vendor=cached.vendor,
                        model=cached.model,
                        raw_data=cached.raw_data,
                    )
            return {"success": True}

        return {
            "success": False,
            "status_code": response.status_code,
            "error": response.error,
        }

    async def report_node_event(
        self,
        node_id: str,
        event: dict | None = None,
        event_type: str | None = None,
        event_data: dict | None = None,
        offline_sync: bool = False,
    ) -> dict:
        """Proxy node event to central.

        Args:
            node_id: Node ID
            event: Full event dict (from queue processing)
            event_type: Event type (alternative to event dict)
            event_data: Event data (alternative to event dict)
            offline_sync: True if called from queue processor (skip queueing)

        Returns:
            Dict with result
        """
        # Build event from params if not provided
        if event is None:
            event = {
                "event_type": event_type,
                "event_data": event_data or {},
                "site_id": self.site_id,
            }

        # Ensure site_id is set
        if "site_id" not in event:
            event["site_id"] = self.site_id

        # Check if offline and should queue
        if not self.is_online and self.queue and not offline_sync:
            # Queue for later sync
            from src.agent.queue import QueueItem
            item = QueueItem(
                id=str(uuid.uuid4()),
                item_type="event",
                payload={
                    "node_id": node_id,
                    "event": event,
                },
                created_at=datetime.now(timezone.utc),
            )
            await self.queue.enqueue(item)
            await self.metrics.record_request(queued=True)
            logger.info(f"Queued event for {node_id} (offline)")
            return {"status": "queued", "offline": True, "queue_id": item.id}

        # Online - proxy to central
        response = await self.proxy_request(
            "POST",
            f"/api/v1/nodes/{node_id}/event",
            body=event,
        )

        if response.status_code in (200, 201):
            return {"success": True}

        return {
            "success": False,
            "status_code": response.status_code,
            "error": response.error,
        }

    async def get_workflow(self, workflow_id: str) -> dict | None:
        """Get workflow from central.

        Args:
            workflow_id: Workflow ID

        Returns:
            Workflow data or None
        """
        response = await self.proxy_request(
            "GET",
            f"/api/v1/workflows/{workflow_id}",
        )

        if response.status_code == 200:
            return response.data
        return None

    async def invalidate_node_cache(self, mac_address: str):
        """Invalidate cached node data.

        Called when central notifies of node changes.
        """
        await self.state_cache.invalidate(mac_address)
        logger.debug(f"Invalidated cache for {mac_address}")
