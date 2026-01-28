"""Cache management API endpoints for site agent.

Provides endpoints for monitoring and managing the local cache.
"""
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["cache"])


# Request/Response models
class CacheStatsResponse(BaseModel):
    """Cache statistics response."""
    content_cache: dict
    node_cache: dict
    policy: str
    patterns: list[str]


class CacheEntryResponse(BaseModel):
    """Cache entry information."""
    path: str
    category: str
    size_bytes: int
    cached_at: datetime
    last_accessed: datetime
    expires_at: datetime | None


class EvictRequest(BaseModel):
    """Cache eviction request."""
    policy: Literal["expired", "lru", "all"] = "expired"
    category: str | None = None
    max_evict: int | None = None


class EvictResponse(BaseModel):
    """Cache eviction response."""
    evicted_count: int
    freed_bytes: int


class SyncRequest(BaseModel):
    """Manual sync request."""
    force: bool = False
    categories: list[str] | None = None


class SyncResponse(BaseModel):
    """Sync operation response."""
    status: str
    files_synced: int
    bytes_transferred: int
    errors: list[str]


# Cache instances will be set by agent main
_content_cache = None
_state_cache = None
_sync_service = None


def set_caches(content_cache, state_cache, sync_service=None):
    """Set cache instances for this router."""
    global _content_cache, _state_cache, _sync_service
    _content_cache = content_cache
    _state_cache = state_cache
    _sync_service = sync_service


def get_content_cache():
    """Get content cache instance."""
    if _content_cache is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    return _content_cache


def get_state_cache():
    """Get state cache instance."""
    if _state_cache is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    return _state_cache


@router.get("/cache", response_model=CacheStatsResponse)
async def get_cache_stats():
    """Get cache statistics and status.

    Returns information about both content cache and node state cache.
    """
    content_cache = get_content_cache()
    state_cache = get_state_cache()

    content_stats = await content_cache.get_stats()
    node_stats = await state_cache.get_stats()

    return CacheStatsResponse(
        content_cache={
            "total_size_bytes": content_stats.total_size_bytes,
            "max_size_bytes": content_stats.max_size_bytes,
            "usage_percent": content_stats.usage_percent,
            "total_entries": content_stats.total_entries,
            "categories": content_stats.categories,
            "disk_usage_percent": content_cache.get_disk_usage_percent(),
        },
        node_cache={
            "total_entries": node_stats["total_entries"],
            "valid_entries": node_stats["valid_entries"],
            "expired_entries": node_stats["expired_entries"],
            "oldest_entry": node_stats["oldest_entry"],
        },
        policy=content_cache.policy,
        patterns=content_cache.patterns,
    )


@router.get("/cache/entries", response_model=list[CacheEntryResponse])
async def list_cache_entries(category: str | None = None):
    """List cached content entries.

    Args:
        category: Optional filter by category
    """
    content_cache = get_content_cache()

    entries = await content_cache.list_entries(category)

    return [
        CacheEntryResponse(
            path=e.path,
            category=e.category,
            size_bytes=e.size_bytes,
            cached_at=e.cached_at,
            last_accessed=e.last_accessed,
            expires_at=e.expires_at,
        )
        for e in entries
    ]


@router.delete("/cache/{category}/{path:path}")
async def evict_cache_entry(category: str, path: str):
    """Evict a specific cache entry.

    Args:
        category: Cache category (bootloaders, templates, etc.)
        path: File path within category
    """
    content_cache = get_content_cache()

    evicted = await content_cache.evict(category, path)

    if not evicted:
        raise HTTPException(status_code=404, detail="Cache entry not found")

    return {"status": "evicted", "category": category, "path": path}


@router.post("/cache/evict", response_model=EvictResponse)
async def evict_cache(request: EvictRequest):
    """Evict cache entries based on policy.

    Policies:
    - expired: Remove only expired entries
    - lru: Remove least recently used entries
    - all: Remove all entries (optionally filtered by category)
    """
    content_cache = get_content_cache()
    state_cache = get_state_cache()

    evicted_count = 0
    freed_bytes = 0

    if request.policy == "expired":
        # Evict expired content
        evicted_count += await content_cache.evict_expired()
        # Evict expired nodes
        evicted_count += await state_cache.invalidate_expired()

    elif request.policy == "all":
        # Clear content cache
        stats_before = await content_cache.get_stats()
        count = await content_cache.clear(request.category)
        evicted_count += count
        freed_bytes = stats_before.total_size_bytes

        # Clear node cache if no category filter
        if not request.category:
            evicted_count += await state_cache.clear()

    elif request.policy == "lru":
        # LRU eviction is handled automatically by size limits
        # For manual LRU, we'd need to track sizes and oldest entries
        evicted_count = await content_cache.evict_expired()

    return EvictResponse(
        evicted_count=evicted_count,
        freed_bytes=freed_bytes,
    )


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(request: SyncRequest):
    """Trigger manual sync with central controller.

    Downloads content from central based on cache policy.
    """
    global _sync_service

    if _sync_service is None:
        # Sync service not configured - just return success
        return SyncResponse(
            status="skipped",
            files_synced=0,
            bytes_transferred=0,
            errors=["Sync service not configured"],
        )

    try:
        result = await _sync_service.run_manual_sync(
            force=request.force,
            categories=request.categories,
        )

        return SyncResponse(
            status="completed",
            files_synced=result.files_synced,
            bytes_transferred=result.bytes_transferred,
            errors=result.errors,
        )

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return SyncResponse(
            status="failed",
            files_synced=0,
            bytes_transferred=0,
            errors=[str(e)],
        )


@router.delete("/cache/nodes/{mac_address}")
async def invalidate_node_cache(mac_address: str):
    """Invalidate cached node data.

    Args:
        mac_address: Node MAC address
    """
    state_cache = get_state_cache()

    deleted = await state_cache.invalidate(mac_address)

    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found in cache")

    return {"status": "invalidated", "mac_address": mac_address}


@router.delete("/cache/nodes")
async def clear_node_cache():
    """Clear all cached node data."""
    state_cache = get_state_cache()

    count = await state_cache.clear()

    return {"status": "cleared", "evicted_count": count}
