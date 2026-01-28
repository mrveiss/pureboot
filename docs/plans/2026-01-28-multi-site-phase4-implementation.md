# Multi-Site Management Phase 4: Offline Operation

**Issue:** #76 (Phase 4 of 7)
**Status:** COMPLETED
**Prerequisites:** Phase 3 (API Proxy & Caching) - COMPLETED
**Started:** 2026-01-28
**Completed:** 2026-01-28

---

## Overview

Phase 4 enables the site agent to operate fully offline when the central controller is unavailable. Nodes can continue booting, and state changes are queued for synchronization when connectivity is restored.

### Goals

1. Agent operates autonomously when central is unreachable
2. Boot scripts generated from cached state
3. State changes queued locally (pending sync queue)
4. Automatic reconnection and queue flush
5. Conflict detection for offline changes
6. Graceful degradation with clear status indicators

### Non-Goals (Later Phases)

- Conflict resolution UI (Phase 5)
- Node migration between sites (Phase 6)
- Multi-agent coordination (Phase 7)

---

## Implementation Tasks (TDD)

### Task 1: Connectivity Monitor

**Files:**
- Create: `src/agent/connectivity.py`
- Test: `tests/unit/test_connectivity.py`

**Changes:**
```python
class ConnectivityMonitor:
    """Monitors connection to central controller."""

    def __init__(
        self,
        central_url: str,
        check_interval: int = 30,
        timeout: float = 5.0,
        failure_threshold: int = 3,
    ):
        self.central_url = central_url
        self.check_interval = check_interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold

    @property
    def is_online(self) -> bool:
        """Check if currently connected to central."""

    @property
    def last_online_at(self) -> datetime | None:
        """When was last successful connection."""

    @property
    def offline_duration(self) -> timedelta | None:
        """How long have we been offline."""

    async def check_connectivity(self) -> bool:
        """Perform connectivity check."""

    async def start(self):
        """Start monitoring loop."""

    async def stop(self):
        """Stop monitoring loop."""

    def add_listener(self, callback: Callable[[bool], Awaitable[None]]):
        """Add callback for connectivity changes."""
```

**Tests:**
- test_connectivity_check_success
- test_connectivity_check_failure
- test_offline_after_threshold
- test_online_after_recovery
- test_listener_notification

---

### Task 2: Pending Sync Queue

**Files:**
- Create: `src/agent/queue.py`
- Test: `tests/unit/test_sync_queue.py`

**Changes:**
```python
class SyncQueue:
    """Queue for pending state changes during offline operation."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def initialize(self):
        """Initialize queue database."""

    async def enqueue(self, item: QueueItem) -> str:
        """Add item to queue, return queue ID."""

    async def peek(self, limit: int = 10) -> list[QueueItem]:
        """Get items without removing them."""

    async def dequeue(self, queue_id: str) -> bool:
        """Remove item from queue after successful sync."""

    async def mark_failed(self, queue_id: str, error: str) -> None:
        """Mark item as failed with error message."""

    async def get_pending_count(self) -> int:
        """Get count of pending items."""

    async def get_failed_items(self) -> list[QueueItem]:
        """Get items that failed to sync."""

    async def clear_failed(self) -> int:
        """Clear failed items, return count."""


class QueueItem(BaseModel):
    id: str
    item_type: str  # registration, state_update, event
    payload: dict
    created_at: datetime
    attempts: int = 0
    last_error: str | None = None
    status: str = "pending"  # pending, processing, failed
```

**Tests:**
- test_enqueue_item
- test_dequeue_item
- test_mark_failed
- test_pending_count
- test_queue_persistence
- test_retry_tracking

---

### Task 3: Offline Boot Script Generator

**Files:**
- Create: `src/agent/offline_boot.py`
- Test: `tests/unit/test_offline_boot.py`

**Changes:**
```python
class OfflineBootGenerator:
    """Generates boot scripts when operating offline."""

    def __init__(
        self,
        state_cache: NodeStateCache,
        content_cache: ContentCache,
        site_id: str,
        default_action: str = "local",  # local, discovery, last_known
    ):
        self.state_cache = state_cache
        self.content_cache = content_cache
        self.site_id = site_id
        self.default_action = default_action

    async def generate_script(
        self,
        mac: str,
        hardware_info: dict | None = None,
    ) -> str:
        """Generate boot script from cached state."""

    async def _generate_discovery_script(self, mac: str) -> str:
        """Script for unknown nodes in offline mode."""

    async def _generate_cached_script(self, node: CachedNode) -> str:
        """Script based on cached node state."""

    async def _generate_local_boot_script(self, mac: str) -> str:
        """Default local boot script."""
```

**Tests:**
- test_generate_from_cached_node
- test_generate_for_unknown_node
- test_generate_discovery_script
- test_generate_local_boot
- test_offline_indicator_in_script

---

### Task 4: Queue Processor

**Files:**
- Create: `src/agent/queue_processor.py`
- Test: `tests/unit/test_queue_processor.py`

**Changes:**
```python
class QueueProcessor:
    """Processes sync queue when connectivity is restored."""

    def __init__(
        self,
        queue: SyncQueue,
        proxy: CentralProxy,
        connectivity: ConnectivityMonitor,
        batch_size: int = 10,
        retry_delay: float = 5.0,
        max_retries: int = 3,
    ):
        self.queue = queue
        self.proxy = proxy
        self.connectivity = connectivity
        self.batch_size = batch_size
        self.retry_delay = retry_delay
        self.max_retries = max_retries

    async def process_queue(self) -> ProcessResult:
        """Process pending items in queue."""

    async def _process_item(self, item: QueueItem) -> bool:
        """Process single queue item."""

    async def _process_registration(self, payload: dict) -> bool:
        """Process queued node registration."""

    async def _process_state_update(self, payload: dict) -> bool:
        """Process queued state update."""

    async def _process_event(self, payload: dict) -> bool:
        """Process queued node event."""

    async def start(self):
        """Start queue processor (listens for connectivity)."""

    async def stop(self):
        """Stop queue processor."""


class ProcessResult(BaseModel):
    processed: int = 0
    failed: int = 0
    remaining: int = 0
    errors: list[str] = []
```

**Tests:**
- test_process_on_reconnect
- test_process_registration
- test_process_state_update
- test_retry_on_failure
- test_max_retries_exceeded
- test_batch_processing

---

### Task 5: Offline-Aware Proxy

**Files:**
- Modify: `src/agent/proxy.py`
- Test: `tests/unit/test_offline_proxy.py`

**Changes:**
Update CentralProxy to queue operations when offline:
```python
class CentralProxy:
    def __init__(
        self,
        # ... existing params ...
        connectivity: ConnectivityMonitor | None = None,
        queue: SyncQueue | None = None,
    ):
        self.connectivity = connectivity
        self.queue = queue

    async def register_node(self, registration: dict) -> dict:
        """Register node - queue if offline."""
        if self.connectivity and not self.connectivity.is_online:
            if self.queue:
                await self.queue.enqueue(QueueItem(
                    id=str(uuid.uuid4()),
                    item_type="registration",
                    payload=registration,
                    created_at=datetime.now(timezone.utc),
                ))
            return {"status": "queued", "offline": True}
        # ... normal registration ...

    async def update_node_state(self, node_id: str, new_state: str) -> dict:
        """Update state - queue if offline."""
        # Similar offline handling
```

**Tests:**
- test_queue_registration_when_offline
- test_queue_state_update_when_offline
- test_normal_operation_when_online
- test_return_queued_status

---

### Task 6: Offline Boot Service Integration

**Files:**
- Modify: `src/agent/boot_service.py`
- Test: `tests/integration/test_offline_boot.py`

**Changes:**
Update AgentBootService to use offline generator:
```python
class AgentBootService:
    def __init__(
        self,
        # ... existing params ...
        connectivity: ConnectivityMonitor | None = None,
        offline_generator: OfflineBootGenerator | None = None,
    ):
        self.connectivity = connectivity
        self.offline_generator = offline_generator

    async def get_boot_script(self, mac: str, request: Request) -> str:
        """Generate boot script - use offline mode if disconnected."""
        # Check connectivity
        if self.connectivity and not self.connectivity.is_online:
            if self.offline_generator:
                return await self.offline_generator.generate_script(
                    mac,
                    hardware_info=self._extract_hardware_info(request),
                )
            return self._generate_offline_script(mac)

        # ... normal online boot script generation ...
```

**Tests:**
- test_boot_uses_offline_generator
- test_boot_falls_back_when_central_unreachable
- test_boot_includes_offline_indicator

---

### Task 7: Conflict Detection

**Files:**
- Create: `src/agent/conflicts.py`
- Test: `tests/unit/test_conflicts.py`

**Changes:**
```python
class ConflictDetector:
    """Detects conflicts between offline changes and central state."""

    def __init__(self, state_cache: NodeStateCache):
        self.state_cache = state_cache

    async def check_conflicts(
        self,
        central_nodes: list[dict],
    ) -> list[Conflict]:
        """Check for conflicts between cached and central state."""

    async def mark_conflict(self, conflict: Conflict) -> None:
        """Mark a conflict for resolution."""

    async def get_pending_conflicts(self) -> list[Conflict]:
        """Get unresolved conflicts."""

    async def resolve_conflict(
        self,
        conflict_id: str,
        resolution: str,  # keep_local, keep_central, merge
    ) -> bool:
        """Resolve a conflict."""


class Conflict(BaseModel):
    id: str
    node_mac: str
    local_state: str
    central_state: str
    local_updated_at: datetime
    central_updated_at: datetime
    conflict_type: str  # state_mismatch, missing_local, missing_central
    resolved: bool = False
    resolution: str | None = None
```

**Tests:**
- test_detect_state_mismatch
- test_detect_missing_local
- test_detect_missing_central
- test_mark_conflict
- test_resolve_conflict

---

### Task 8: Agent Main Integration

**Files:**
- Modify: `src/agent/main.py`
- Test: `tests/integration/test_offline_agent.py`

**Changes:**
Update SiteAgent to include offline components:
```python
class SiteAgent:
    def __init__(self):
        # ... existing ...
        self.connectivity: ConnectivityMonitor | None = None
        self.sync_queue: SyncQueue | None = None
        self.queue_processor: QueueProcessor | None = None
        self.offline_generator: OfflineBootGenerator | None = None
        self.conflict_detector: ConflictDetector | None = None

    async def _initialize_offline_components(self):
        """Initialize Phase 4 offline components."""
        # Connectivity monitor
        self.connectivity = ConnectivityMonitor(
            central_url=self.config.central_url,
            check_interval=self.config.connectivity_check_interval,
        )
        await self.connectivity.start()

        # Sync queue
        queue_db = self.config.data_dir / "state" / "queue.db"
        self.sync_queue = SyncQueue(db_path=queue_db)
        await self.sync_queue.initialize()

        # Queue processor
        self.queue_processor = QueueProcessor(
            queue=self.sync_queue,
            proxy=self.proxy,
            connectivity=self.connectivity,
        )
        await self.queue_processor.start()

        # Offline boot generator
        self.offline_generator = OfflineBootGenerator(
            state_cache=self.state_cache,
            content_cache=self.content_cache,
            site_id=self.config.site_id,
        )

        # Conflict detector
        self.conflict_detector = ConflictDetector(
            state_cache=self.state_cache,
        )
```

**Tests:**
- test_agent_starts_offline_components
- test_agent_handles_offline_mode
- test_agent_processes_queue_on_reconnect

---

### Task 9: Heartbeat Offline Metrics

**Files:**
- Modify: `src/agent/heartbeat.py`
- Test: `tests/unit/test_heartbeat_offline.py`

**Changes:**
```python
class AgentMetrics(BaseModel):
    # ... existing fields ...

    # Offline metrics
    is_online: bool = True
    last_online_at: datetime | None = None
    offline_duration_seconds: int = 0
    pending_queue_items: int = 0
    failed_queue_items: int = 0
    conflicts_pending: int = 0
```

**Tests:**
- test_heartbeat_includes_offline_metrics
- test_metrics_when_offline
- test_queue_metrics_accuracy

---

### Task 10: Configuration Updates

**Files:**
- Modify: `src/config/settings.py`
- Test: `tests/unit/test_offline_config.py`

**Changes:**
```python
class AgentSettings(BaseSettings):
    # ... existing fields ...

    # Offline operation settings
    connectivity_check_interval: int = 30  # seconds
    connectivity_timeout: float = 5.0
    connectivity_failure_threshold: int = 3
    offline_default_action: str = "local"  # local, discovery, last_known
    queue_batch_size: int = 10
    queue_retry_delay: float = 5.0
    queue_max_retries: int = 3
```

**Tests:**
- test_offline_config_defaults
- test_offline_config_from_env

---

## Dependencies

| Task | Depends On |
|------|------------|
| 2 | - |
| 1 | - |
| 3 | Phase 3 caches |
| 4 | 1, 2 |
| 5 | 1, 2 |
| 6 | 1, 3 |
| 7 | Phase 3 caches |
| 8 | 1-7 |
| 9 | 1, 2, 7 |
| 10 | - |

---

## Success Criteria

1. Agent continues serving boot scripts when central is unreachable
2. State changes queued locally during offline operation
3. Queue automatically processed when connectivity restored
4. Conflicts detected between offline changes and central state
5. Clear offline status indicators in boot scripts and health endpoint
6. Metrics include offline duration and queue status

---

## Offline Boot Script Example

```bash
#!ipxe
# PureBoot Agent - OFFLINE MODE
# MAC: ${mac}
# Site: ${site_id}
# Cached State: ${node_state}
# Offline Since: ${offline_since}

echo
echo *** PureBoot Site Agent - OFFLINE ***
echo
echo   Central controller is unreachable.
echo   Operating from cached state.
echo   Node state: ${node_state}
echo   Last sync: ${last_sync}
echo
echo   Proceeding with ${action}...
echo

# Action based on cached state
${boot_commands}
```

---

## Notes

- SQLite database for sync queue (same as state cache)
- Connectivity monitor uses health endpoint check
- Queue processor triggers on connectivity change
- Conflicts stored in state cache database
- Phase 5 will add conflict resolution UI
