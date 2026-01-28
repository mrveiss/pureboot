"""PureBoot Site Agent entry point.

The site agent runs at remote locations to:
- Serve TFTP and HTTP boot files locally
- Register and maintain heartbeat with central controller
- Cache content from central for offline operation
- Proxy API requests to central with local caching
- Operate autonomously when central is unreachable (Phase 4)

Usage:
    python -m src.agent.main
"""
import asyncio
import logging
import signal
from pathlib import Path

import uvicorn

from src.config import settings
from src.agent.central_client import CentralClient, RegistrationError
from src.agent.heartbeat import HeartbeatLoop
from src.agent.boot_service import (
    AgentBootService,
    BootMetrics,
    CacheManager,
    create_agent_app,
)
from src.agent.cache.state_cache import NodeStateCache
from src.agent.cache.content_cache import ContentCache
from src.agent.proxy import CentralProxy
from src.agent.sync import CacheSyncService
from src.agent.connectivity import ConnectivityMonitor
from src.agent.queue import SyncQueue
from src.agent.queue_processor import QueueProcessor
from src.agent.offline_boot import OfflineBootGenerator
from src.agent.conflicts import ConflictDetector
from src.pxe.tftp_server import TFTPServer

logger = logging.getLogger(__name__)

# Version of the site agent
AGENT_VERSION = "0.3.0"  # Phase 4 version


class SiteAgent:
    """PureBoot Site Agent with offline support."""

    def __init__(self):
        """Initialize the site agent."""
        self.config = settings.agent
        self.central_client: CentralClient | None = None
        self.heartbeat_loop: HeartbeatLoop | None = None
        self.tftp_server: TFTPServer | None = None
        self.boot_service: AgentBootService | None = None
        self.http_server: asyncio.Server | None = None
        self.boot_metrics = BootMetrics()

        # Legacy cache manager (for boot service compatibility)
        self.cache_manager = CacheManager(
            cache_dir=self.config.cache_dir,
            max_size_gb=self.config.cache_max_size_gb,
        )

        # Phase 3 components
        self.state_cache: NodeStateCache | None = None
        self.content_cache: ContentCache | None = None
        self.proxy: CentralProxy | None = None
        self.sync_service: CacheSyncService | None = None

        # Phase 4 components (offline operation)
        self.connectivity: ConnectivityMonitor | None = None
        self.sync_queue: SyncQueue | None = None
        self.queue_processor: QueueProcessor | None = None
        self.offline_generator: OfflineBootGenerator | None = None
        self.conflict_detector: ConflictDetector | None = None

        self._shutdown_event = asyncio.Event()

    def _validate_config(self):
        """Validate agent configuration."""
        if not self.config.site_id:
            raise ValueError("PUREBOOT_AGENT__SITE_ID is required")
        if not self.config.central_url:
            raise ValueError("PUREBOOT_AGENT__CENTRAL_URL is required")
        if not self.config.registration_token and not self.config.registered:
            raise ValueError(
                "PUREBOOT_AGENT__REGISTRATION_TOKEN is required for initial registration"
            )

    async def _register_with_central(self) -> bool:
        """Register agent with central controller."""
        if self.config.registered:
            logger.info("Agent already registered, skipping registration")
            return True

        if not self.config.registration_token:
            logger.error("No registration token configured")
            return False

        logger.info(f"Registering with central controller at {self.config.central_url}")

        try:
            agent_url = f"http://{settings.host}:{settings.port}"
            config = await self.central_client.register(
                agent_url=agent_url,
                agent_version=AGENT_VERSION,
            )

            logger.info(f"Registered successfully as site: {config.site_name}")
            logger.info(f"Autonomy level: {config.autonomy_level}")
            logger.info(f"Cache policy: {config.cache_policy}")

            # Update heartbeat interval from server config
            if self.heartbeat_loop:
                self.heartbeat_loop.interval = config.heartbeat_interval

            return True

        except RegistrationError as e:
            logger.error(f"Registration failed: {e}")
            return False

    async def _initialize_caches(self):
        """Initialize Phase 3 cache components."""
        # State cache for nodes
        state_db = self.config.data_dir / "state" / "nodes.db"
        self.state_cache = NodeStateCache(
            db_path=state_db,
            default_ttl=self.config.node_cache_ttl,
        )
        await self.state_cache.initialize()
        logger.info(f"Node state cache initialized at {state_db}")

        # Content cache
        self.content_cache = ContentCache(
            cache_dir=self.config.cache_dir,
            max_size_gb=self.config.cache_max_size_gb,
            policy=self.config.cache_policy,
            patterns=self.config.cache_patterns,
            retention_days=self.config.cache_retention_days,
        )
        await self.content_cache.initialize()
        logger.info(f"Content cache initialized (policy={self.config.cache_policy})")

        # Initialize Phase 4 offline components
        await self._initialize_offline_components()

        # Proxy for API requests (with offline support)
        self.proxy = CentralProxy(
            central_url=self.config.central_url,
            state_cache=self.state_cache,
            content_cache=self.content_cache,
            site_id=self.config.site_id,
            connectivity=self.connectivity,
            queue=self.sync_queue,
        )
        await self.proxy.start()
        logger.info("Central proxy initialized")

        # Queue processor for syncing offline changes
        self.queue_processor = QueueProcessor(
            queue=self.sync_queue,
            proxy=self.proxy,
            connectivity=self.connectivity,
            batch_size=self.config.queue_batch_size,
            retry_delay=self.config.queue_retry_delay,
            max_retries=self.config.queue_max_retries,
        )
        await self.queue_processor.start()
        logger.info("Queue processor initialized")

        # Sync service
        self.sync_service = CacheSyncService(
            central_url=self.config.central_url,
            site_id=self.config.site_id,
            content_cache=self.content_cache,
            state_cache=self.state_cache,
        )
        await self.sync_service.start()
        logger.info("Cache sync service initialized")

    async def _initialize_offline_components(self):
        """Initialize Phase 4 offline operation components."""
        # Connectivity monitor
        self.connectivity = ConnectivityMonitor(
            central_url=self.config.central_url,
            check_interval=self.config.connectivity_check_interval,
            timeout=self.config.connectivity_timeout,
            failure_threshold=self.config.connectivity_failure_threshold,
        )
        await self.connectivity.start()
        logger.info("Connectivity monitor started")

        # Register connectivity listener for offline events
        self.connectivity.add_listener(self._on_connectivity_change)

        # Sync queue for offline operations
        queue_db = self.config.data_dir / "state" / "queue.db"
        self.sync_queue = SyncQueue(db_path=queue_db)
        await self.sync_queue.initialize()
        logger.info(f"Sync queue initialized at {queue_db}")

        # Offline boot generator
        self.offline_generator = OfflineBootGenerator(
            state_cache=self.state_cache,
            content_cache=self.content_cache,
            site_id=self.config.site_id,
            default_action=self.config.offline_default_action,
        )
        logger.info("Offline boot generator initialized")

        # Conflict detector
        conflict_db = self.config.data_dir / "state" / "conflicts.db"
        self.conflict_detector = ConflictDetector(db_path=conflict_db)
        await self.conflict_detector.initialize()
        logger.info("Conflict detector initialized")

    async def _on_connectivity_change(self, is_online: bool):
        """Handle connectivity state changes.

        Args:
            is_online: True if now online, False if offline
        """
        if is_online:
            logger.info("Connectivity restored - updating offline generator")
            if self.offline_generator:
                self.offline_generator.set_offline_since(None)
        else:
            logger.warning("Lost connectivity to central - entering offline mode")
            if self.offline_generator and self.connectivity:
                self.offline_generator.set_offline_since(
                    self.connectivity.offline_since
                )

    async def _handle_command(self, command: str, params: dict):
        """Handle commands from central controller."""
        logger.info(f"Received command: {command} with params: {params}")

        if command == "sync":
            # Trigger cache sync
            if self.sync_service:
                asyncio.create_task(self.sync_service.run_manual_sync(
                    force=params.get("force", False),
                    categories=params.get("categories"),
                ))

        elif command == "invalidate":
            # Invalidate cache entries
            mac = params.get("mac_address")
            if mac and self.state_cache:
                await self.state_cache.invalidate(mac)
            category = params.get("category")
            path = params.get("path")
            if category and path and self.content_cache:
                await self.content_cache.evict(category, path)

        elif command == "update_config":
            # Update agent configuration (e.g., cache policy)
            if "cache_policy" in params and self.content_cache:
                self.content_cache.policy = params["cache_policy"]
            if "cache_patterns" in params and self.content_cache:
                self.content_cache.patterns = params["cache_patterns"]

        else:
            logger.warning(f"Unknown command: {command}")

    async def _start_boot_service(self):
        """Start the HTTP boot service."""
        # Initialize Phase 3 caches first (includes Phase 4 offline components)
        await self._initialize_caches()

        # Boot service with offline support
        self.boot_service = AgentBootService(
            central_url=self.config.central_url,
            site_id=self.config.site_id,
            cache_manager=self.cache_manager,
            metrics=self.boot_metrics,
            connectivity=self.connectivity,
            offline_generator=self.offline_generator,
        )
        await self.boot_service.start()

        # Create the FastAPI app with Phase 3 and Phase 4 components
        app = create_agent_app(
            self.boot_service,
            proxy=self.proxy,
            state_cache=self.state_cache,
            content_cache=self.content_cache,
            connectivity=self.connectivity,
            sync_queue=self.sync_queue,
        )

        # Start uvicorn server
        config = uvicorn.Config(
            app=app,
            host=settings.host,
            port=settings.port,
            log_level="info" if not settings.debug else "debug",
        )
        server = uvicorn.Server(config)

        # Run server in background task
        self._http_task = asyncio.create_task(server.serve())
        logger.info(f"HTTP boot service started on {settings.host}:{settings.port}")

        if self.heartbeat_loop:
            self.heartbeat_loop.set_service_status("http", "ok")
            self.heartbeat_loop.set_metrics_source(self.boot_metrics, self.cache_manager)
            self.heartbeat_loop.set_cache_sources(
                state_cache=self.state_cache,
                content_cache=self.content_cache,
                sync_service=self.sync_service,
                proxy=self.proxy,
            )
            # Set offline sources for heartbeat
            self.heartbeat_loop.set_offline_sources(
                connectivity=self.connectivity,
                sync_queue=self.sync_queue,
                conflict_detector=self.conflict_detector,
            )

    async def _start_tftp_server(self):
        """Start the TFTP server."""
        if not settings.tftp.enabled:
            logger.info("TFTP server disabled")
            return

        # For agent mode, use cache directory as TFTP root
        tftp_root = self.cache_manager.cache_dir / "tftp"
        tftp_root.mkdir(parents=True, exist_ok=True)

        self.tftp_server = TFTPServer(
            root=tftp_root,
            host=settings.tftp.host,
            port=settings.tftp.port,
        )

        try:
            await self.tftp_server.start()
            logger.info(f"TFTP server started on {settings.tftp.host}:{settings.tftp.port}")
            if self.heartbeat_loop:
                self.heartbeat_loop.set_service_status("tftp", "ok")
        except PermissionError:
            logger.warning(
                f"Cannot bind to port {settings.tftp.port} (requires root). "
                "TFTP server disabled."
            )
            self.tftp_server = None
            if self.heartbeat_loop:
                self.heartbeat_loop.set_service_status("tftp", "error")

    async def _start_heartbeat(self):
        """Start the heartbeat loop."""
        self.heartbeat_loop = HeartbeatLoop(
            client=self.central_client,
            interval=self.config.heartbeat_interval,
            agent_version=AGENT_VERSION,
            command_handler=self._handle_command,
        )
        await self.heartbeat_loop.start()

    async def _handle_shutdown(self):
        """Handle graceful shutdown."""
        logger.info("Shutting down site agent...")

        if self.heartbeat_loop:
            await self.heartbeat_loop.stop()

        if self.tftp_server:
            await self.tftp_server.stop()

        if self.boot_service:
            await self.boot_service.stop()

        # Stop Phase 4 offline components
        if self.queue_processor:
            await self.queue_processor.stop()

        if self.connectivity:
            await self.connectivity.stop()

        if self.sync_queue:
            await self.sync_queue.close()

        if self.conflict_detector:
            await self.conflict_detector.close()

        # Stop Phase 3 components
        if self.sync_service:
            await self.sync_service.stop()

        if self.proxy:
            await self.proxy.stop()

        # Cancel HTTP server task
        if hasattr(self, "_http_task") and self._http_task:
            self._http_task.cancel()
            try:
                await self._http_task
            except asyncio.CancelledError:
                pass

        if self.central_client:
            await self.central_client.close()

        logger.info("Site agent stopped")

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: self._shutdown_event.set())

    async def run(self):
        """Run the site agent."""
        logger.info("Starting PureBoot Site Agent...")

        # Validate configuration
        try:
            self._validate_config()
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            return 1

        # Initialize central client
        self.central_client = CentralClient(
            central_url=self.config.central_url,
            site_id=self.config.site_id,
            token=self.config.registration_token,
        )

        # Start heartbeat loop
        await self._start_heartbeat()

        # Register with central
        if not await self._register_with_central():
            logger.error("Failed to register with central controller")
            await self._handle_shutdown()
            return 1

        # Start HTTP boot service
        await self._start_boot_service()

        # Start TFTP server
        await self._start_tftp_server()

        # Set up signal handlers
        self._setup_signal_handlers()

        logger.info(
            f"Site Agent running for site {self.config.site_id}. "
            f"Press Ctrl+C to stop."
        )

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # Clean up
        await self._handle_shutdown()
        return 0


async def main():
    """Run the site agent."""
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if not settings.is_agent_mode:
        logger.error(
            "Not in agent mode. Set PUREBOOT_AGENT__MODE=agent to run as site agent."
        )
        return 1

    agent = SiteAgent()
    return await agent.run()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
