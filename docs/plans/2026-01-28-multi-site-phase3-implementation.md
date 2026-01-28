# Multi-Site Management Phase 3: API Proxy & Caching

**Issue:** #76 (Phase 3 of 7)
**Status:** COMPLETED
**Prerequisites:** Phase 2 (Site Agent - Minimal) - COMPLETED
**Completed:** 2026-01-28

---

## Overview

Phase 3 enables the site agent to act as an API proxy between nodes and the central controller, with local caching to improve resilience and performance. Nodes boot through the agent, which transparently proxies requests to central while caching responses.

### Goals

1. Agent proxies node API calls to central controller
2. Local SQLite cache for node state
3. Content caching with configurable policies
4. Cache management API endpoints
5. Cache sync triggers (scheduled, on-demand, push, manual)

### Non-Goals (Later Phases)

- Full offline operation (Phase 4)
- Conflict resolution (Phase 5)
- Node migration (Phase 6)

---

## Implementation Tasks (TDD)

### Task 1: Node State Cache Model

**Files:**
- Create: `src/agent/cache/state_cache.py`
- Test: `tests/unit/test_state_cache.py`

**Changes:**
```python
class NodeStateCache:
    """Local SQLite cache for node state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def get_node(self, mac: str) -> CachedNode | None:
        """Get cached node by MAC address."""

    async def set_node(self, node: CachedNode) -> None:
        """Cache or update node state."""

    async def get_nodes_by_group(self, group_id: str) -> list[CachedNode]:
        """Get all cached nodes in a group."""

    async def invalidate(self, mac: str) -> None:
        """Remove node from cache."""


class CachedNode(BaseModel):
    mac_address: str
    state: str
    workflow_id: str | None
    group_id: str | None
    cached_at: datetime
    expires_at: datetime
    raw_data: dict  # Full node response from central
```

**Tests:**
- test_cache_node
- test_get_cached_node
- test_cache_expiry
- test_invalidate_node
- test_cache_persistence

---

### Task 2: Content Cache Manager

**Files:**
- Create: `src/agent/cache/content_cache.py`
- Modify: `src/agent/boot_service.py`
- Test: `tests/unit/test_content_cache.py`

**Changes:**
```python
class ContentCache:
    """Manages cached boot files and templates."""

    CATEGORIES = {
        "bootloaders": {"always_cache": True, "max_age_days": None},
        "scripts": {"always_cache": False, "max_age_days": 1},
        "templates": {"always_cache": False, "max_age_days": 7},
        "images": {"always_cache": False, "max_age_days": 30},
    }

    def __init__(self, cache_dir: Path, max_size_gb: int, policy: str):
        self.cache_dir = cache_dir
        self.max_size_bytes = max_size_gb * 1024**3
        self.policy = policy  # minimal, assigned, mirror, pattern

    async def get(self, category: str, path: str) -> Path | None:
        """Get cached file path if exists and valid."""

    async def put(self, category: str, path: str, content: bytes) -> Path:
        """Cache content, respecting size limits."""

    async def should_cache(self, category: str, path: str) -> bool:
        """Check if path should be cached per policy."""

    async def evict_expired(self) -> int:
        """Remove expired cache entries, return count."""

    async def evict_to_size(self) -> int:
        """Evict oldest entries to meet size limit."""
```

**Tests:**
- test_cache_bootloader_always
- test_cache_template_per_policy
- test_size_limit_enforcement
- test_expiry_eviction
- test_lru_eviction

---

### Task 3: API Proxy Service

**Files:**
- Create: `src/agent/proxy.py`
- Test: `tests/unit/test_proxy.py`

**Changes:**
```python
class CentralProxy:
    """Proxies API requests to central controller."""

    def __init__(
        self,
        central_url: str,
        state_cache: NodeStateCache,
        content_cache: ContentCache,
    ):
        self.central_url = central_url
        self.state_cache = state_cache
        self.content_cache = content_cache

    async def proxy_request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: dict | None = None,
    ) -> ProxyResponse:
        """Proxy request to central, caching response."""

    async def get_node_by_mac(self, mac: str) -> CachedNode | None:
        """Get node, checking cache first then central."""

    async def register_node(self, registration: dict) -> dict:
        """Proxy node registration to central."""

    async def update_node_state(self, node_id: str, new_state: str) -> dict:
        """Proxy state transition to central."""
```

**Tests:**
- test_proxy_to_central
- test_cache_response
- test_serve_from_cache
- test_central_unavailable_serve_cache
- test_cache_invalidation_on_update

---

### Task 4: Agent API Endpoints (Node-Facing)

**Files:**
- Modify: `src/agent/boot_service.py`
- Test: `tests/integration/test_agent_node_api.py`

**Endpoints:**
```python
# Node registration (proxied to central)
@app.post("/api/v1/nodes/register")
async def register_node(registration: NodeRegistration):
    """Proxy node registration to central."""

# Node state query
@app.get("/api/v1/nodes")
async def get_nodes(mac: str | None = None):
    """Get nodes, from cache or central."""

# Node state update
@app.patch("/api/v1/nodes/{node_id}/state")
async def update_node_state(node_id: str, state: StateUpdate):
    """Proxy state transition to central."""

# Node event reporting
@app.post("/api/v1/nodes/{node_id}/event")
async def report_node_event(node_id: str, event: NodeEvent):
    """Proxy node event to central."""
```

**Tests:**
- test_register_node_proxied
- test_get_node_from_cache
- test_get_node_from_central
- test_state_update_proxied
- test_event_proxied

---

### Task 5: Cache Management API

**Files:**
- Create: `src/agent/routes/cache.py`
- Modify: `src/agent/boot_service.py`
- Test: `tests/integration/test_agent_cache_api.py`

**Endpoints:**
```python
@router.get("/api/v1/agent/cache")
async def get_cache_stats():
    """Get cache statistics and contents."""
    return {
        "total_size_bytes": ...,
        "max_size_bytes": ...,
        "usage_percent": ...,
        "policy": ...,
        "categories": {
            "bootloaders": {"count": 5, "size_bytes": 1024000},
            "templates": {"count": 12, "size_bytes": 50000},
            ...
        },
        "node_cache": {
            "count": 45,
            "oldest_entry": "2026-01-27T10:00:00Z",
        }
    }

@router.delete("/api/v1/agent/cache/{category}/{path:path}")
async def evict_cache_entry(category: str, path: str):
    """Evict specific cache entry."""

@router.post("/api/v1/agent/cache/evict")
async def evict_cache(policy: EvictPolicy):
    """Evict cache entries per policy (expired, lru, all)."""

@router.post("/api/v1/agent/sync")
async def trigger_sync(force: bool = False):
    """Trigger manual sync with central."""
```

**Tests:**
- test_get_cache_stats
- test_evict_specific_entry
- test_evict_expired
- test_evict_all
- test_trigger_sync

---

### Task 6: Cache Sync Service

**Files:**
- Create: `src/agent/sync.py`
- Test: `tests/unit/test_agent_sync.py`

**Changes:**
```python
class CacheSyncService:
    """Synchronizes cache with central controller."""

    def __init__(
        self,
        central_client: CentralClient,
        content_cache: ContentCache,
        state_cache: NodeStateCache,
    ):
        ...

    async def sync_bootloaders(self) -> SyncResult:
        """Sync essential bootloader files."""

    async def sync_assigned_content(self, site_id: str) -> SyncResult:
        """Sync content assigned to this site."""

    async def sync_patterns(self, patterns: list[str]) -> SyncResult:
        """Sync content matching glob patterns."""

    async def full_sync(self) -> SyncResult:
        """Full mirror sync (for mirror policy)."""

    async def run_scheduled_sync(self):
        """Scheduled sync based on policy."""


class SyncResult(BaseModel):
    files_synced: int
    bytes_transferred: int
    errors: list[str]
    duration_seconds: float
```

**Tests:**
- test_sync_bootloaders
- test_sync_assigned_content
- test_sync_patterns
- test_full_sync
- test_scheduled_sync

---

### Task 7: Cache Policy Configuration

**Files:**
- Modify: `src/config/settings.py`
- Modify: `src/api/schemas.py`
- Test: `tests/unit/test_cache_policy.py`

**Changes:**
```python
# Add to AgentSettings
class AgentSettings(BaseSettings):
    # ... existing fields ...

    # Cache policy settings
    cache_policy: str = "minimal"  # minimal, assigned, mirror, pattern
    cache_patterns: list[str] = []  # For pattern policy
    cache_retention_days: int = 30
    sync_schedule: str = "0 2 * * *"  # Cron: 2 AM daily

# Add to SiteUpdate schema (central)
class SiteUpdate(BaseModel):
    # ... existing fields ...
    cache_policy: str | None = None
    cache_patterns_json: str | None = None
    cache_max_size_gb: int | None = None
    cache_retention_days: int | None = None
```

**Tests:**
- test_minimal_policy_caching
- test_assigned_policy_caching
- test_mirror_policy_caching
- test_pattern_policy_caching
- test_policy_from_central_config

---

### Task 8: Proxy Boot Script Generation

**Files:**
- Modify: `src/agent/boot_service.py`
- Test: `tests/integration/test_agent_boot_proxy.py`

**Changes:**
Update boot service to use proxy for node lookup:
```python
async def get_boot_script(self, mac: str, request: Request) -> str:
    """Generate boot script, using cached or proxied node state."""

    # 1. Check state cache for node
    cached = await self.state_cache.get_node(mac)
    if cached and not cached.is_expired:
        node = cached
    else:
        # 2. Proxy to central, cache result
        node = await self.proxy.get_node_by_mac(mac)

    # 3. Generate script based on node state
    if node is None:
        return self._generate_discovery_script(mac)
    return self._generate_state_script(node)
```

**Tests:**
- test_boot_from_cached_node
- test_boot_fetches_from_central
- test_boot_caches_central_response
- test_boot_when_central_unavailable

---

### Task 9: Heartbeat Cache Metrics

**Files:**
- Modify: `src/agent/heartbeat.py`
- Modify: `src/api/schemas.py`
- Test: `tests/unit/test_heartbeat_metrics.py`

**Changes:**
```python
# Update AgentMetrics
class AgentMetrics(BaseModel):
    # ... existing fields ...

    # Cache metrics
    cache_size_bytes: int = 0
    cache_entries: int = 0
    cache_hit_rate: float = 0.0
    node_cache_entries: int = 0
    last_sync_at: datetime | None = None
    last_sync_result: str | None = None  # success, partial, failed
    pending_sync_items: int = 0
```

**Tests:**
- test_heartbeat_includes_cache_metrics
- test_cache_metrics_accuracy

---

### Task 10: Central Push Notifications

**Files:**
- Modify: `src/api/routes/agents.py` (central)
- Modify: `src/agent/heartbeat.py` (agent)
- Test: `tests/integration/test_push_notifications.py`

**Changes:**
Central can include commands in heartbeat response:
```python
class HeartbeatCommand(BaseModel):
    command: str  # sync, invalidate, update_config
    params: dict

# Commands:
# - sync: Trigger cache sync
# - invalidate: Invalidate specific cache entries
# - update_config: Update agent configuration
```

**Tests:**
- test_push_sync_command
- test_push_invalidate_command
- test_push_config_update

---

## Dependencies

| Task | Depends On |
|------|------------|
| 2 | 1 |
| 3 | 1, 2 |
| 4 | 3 |
| 5 | 2 |
| 6 | 2, 3 |
| 7 | - |
| 8 | 3, 4 |
| 9 | 2 |
| 10 | 4 |

---

## Success Criteria

1. Agent proxies node API calls to central
2. Node state cached locally in SQLite
3. Boot files cached per configurable policy
4. Cache management API functional
5. Scheduled and manual sync working
6. Cache metrics reported in heartbeat
7. Central can push commands to agents

---

## Cache Directory Structure

```
/var/lib/pureboot-agent/
├── cache/
│   ├── bootloaders/      # Always cached
│   │   ├── ipxe.efi
│   │   ├── undionly.kpxe
│   │   └── grub/
│   ├── scripts/          # Short TTL
│   ├── templates/        # Medium TTL
│   │   ├── kickstart/
│   │   ├── preseed/
│   │   └── cloud-init/
│   └── images/           # Long TTL
│       ├── ubuntu-24.04.iso
│       └── windows-2022.wim
└── state/
    └── nodes.db          # SQLite state cache
```

---

## Notes

- SQLite for state cache (lightweight, no external deps)
- Content cache uses filesystem with metadata
- Cache policies configurable per site from central
- Bootloaders always cached for reliability
- Phase 4 will build on this for offline operation
