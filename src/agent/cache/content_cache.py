"""Content cache manager for boot files and templates.

Manages cached boot files with configurable policies:
- minimal: Bootloaders + active workflows only
- assigned: Above + explicitly assigned content
- mirror: Full sync of all content
- pattern: Cache items matching glob patterns
"""
import asyncio
import fnmatch
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

CachePolicy = Literal["minimal", "assigned", "mirror", "pattern"]


@dataclass
class CacheCategory:
    """Configuration for a cache category."""
    name: str
    always_cache: bool = False
    max_age_days: int | None = None  # None = never expire
    priority: int = 0  # Higher priority = evicted last


# Default category configurations
DEFAULT_CATEGORIES: dict[str, CacheCategory] = {
    "bootloaders": CacheCategory(
        name="bootloaders",
        always_cache=True,
        max_age_days=None,  # Never expire
        priority=100,
    ),
    "scripts": CacheCategory(
        name="scripts",
        always_cache=False,
        max_age_days=1,
        priority=10,
    ),
    "templates": CacheCategory(
        name="templates",
        always_cache=False,
        max_age_days=7,
        priority=50,
    ),
    "images": CacheCategory(
        name="images",
        always_cache=False,
        max_age_days=30,
        priority=30,
    ),
}


@dataclass
class CacheEntry:
    """Metadata for a cached file."""
    path: str
    category: str
    size_bytes: int
    cached_at: datetime
    last_accessed: datetime
    expires_at: datetime | None


@dataclass
class CacheStats:
    """Cache statistics."""
    total_size_bytes: int = 0
    max_size_bytes: int = 0
    usage_percent: float = 0.0
    total_entries: int = 0
    categories: dict[str, dict] = field(default_factory=dict)


class ContentCache:
    """Manages cached boot files and templates."""

    METADATA_FILE = ".cache_meta.json"

    def __init__(
        self,
        cache_dir: Path,
        max_size_gb: int = 50,
        policy: CachePolicy = "minimal",
        patterns: list[str] | None = None,
        retention_days: int = 30,
    ):
        """Initialize content cache.

        Args:
            cache_dir: Root directory for cache storage
            max_size_gb: Maximum cache size in GB
            policy: Cache policy (minimal, assigned, mirror, pattern)
            patterns: Glob patterns for pattern policy
            retention_days: Default retention for non-essential files
        """
        self.cache_dir = Path(cache_dir)
        self.max_size_bytes = max_size_gb * 1024 * 1024 * 1024
        self.policy = policy
        self.patterns = patterns or []
        self.retention_days = retention_days
        self.categories = DEFAULT_CATEGORIES.copy()
        self._lock = asyncio.Lock()
        self._metadata: dict[str, CacheEntry] = {}

    async def initialize(self):
        """Initialize cache directories and load metadata."""
        # Create category directories
        for category in self.categories:
            (self.cache_dir / category).mkdir(parents=True, exist_ok=True)

        # Load metadata
        await self._load_metadata()
        logger.info(
            f"Content cache initialized at {self.cache_dir} "
            f"(policy={self.policy}, max={self.max_size_bytes // (1024**3)}GB)"
        )

    async def _load_metadata(self):
        """Load cache metadata from disk."""
        meta_path = self.cache_dir / self.METADATA_FILE

        def _load():
            if not meta_path.exists():
                return {}
            try:
                with open(meta_path) as f:
                    data = json.load(f)
                return {
                    k: CacheEntry(
                        path=v["path"],
                        category=v["category"],
                        size_bytes=v["size_bytes"],
                        cached_at=datetime.fromisoformat(v["cached_at"]),
                        last_accessed=datetime.fromisoformat(v["last_accessed"]),
                        expires_at=(
                            datetime.fromisoformat(v["expires_at"])
                            if v.get("expires_at")
                            else None
                        ),
                    )
                    for k, v in data.items()
                }
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load cache metadata: {e}")
                return {}

        loop = asyncio.get_event_loop()
        self._metadata = await loop.run_in_executor(None, _load)

    async def _save_metadata(self):
        """Save cache metadata to disk."""
        meta_path = self.cache_dir / self.METADATA_FILE

        def _save():
            data = {
                k: {
                    "path": v.path,
                    "category": v.category,
                    "size_bytes": v.size_bytes,
                    "cached_at": v.cached_at.isoformat(),
                    "last_accessed": v.last_accessed.isoformat(),
                    "expires_at": v.expires_at.isoformat() if v.expires_at else None,
                }
                for k, v in self._metadata.items()
            }
            with open(meta_path, "w") as f:
                json.dump(data, f, indent=2)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _save)

    def _get_cache_key(self, category: str, path: str) -> str:
        """Get cache key for category/path."""
        return f"{category}/{path}"

    def _get_file_path(self, category: str, path: str) -> Path:
        """Get filesystem path for cached file."""
        # Sanitize path to prevent traversal
        safe_path = path.lstrip("/").replace("..", "")
        return self.cache_dir / category / safe_path

    async def get(self, category: str, path: str) -> Path | None:
        """Get cached file path if exists and valid.

        Args:
            category: Cache category (bootloaders, templates, etc.)
            path: File path within category

        Returns:
            Path to cached file if valid, None otherwise
        """
        cache_key = self._get_cache_key(category, path)
        file_path = self._get_file_path(category, path)

        # Check file exists
        if not file_path.exists():
            self._metadata.pop(cache_key, None)
            return None

        # Check metadata
        entry = self._metadata.get(cache_key)
        if entry:
            # Check expiry
            if entry.expires_at and datetime.now(timezone.utc) > entry.expires_at:
                logger.debug(f"Cache entry expired: {cache_key}")
                await self.evict(category, path)
                return None

            # Update last accessed
            entry.last_accessed = datetime.now(timezone.utc)
            await self._save_metadata()

        return file_path

    async def put(
        self,
        category: str,
        path: str,
        content: bytes,
        expires_in: timedelta | None = None,
    ) -> Path:
        """Cache content.

        Args:
            category: Cache category
            path: File path within category
            content: File content
            expires_in: Optional expiry override

        Returns:
            Path to cached file
        """
        async with self._lock:
            # Check if we should cache this
            if not await self.should_cache(category, path):
                raise ValueError(f"Cache policy does not allow caching: {category}/{path}")

            # Calculate expiry
            now = datetime.now(timezone.utc)
            cat_config = self.categories.get(category)
            if expires_in:
                expires_at = now + expires_in
            elif cat_config and cat_config.max_age_days:
                expires_at = now + timedelta(days=cat_config.max_age_days)
            else:
                expires_at = None

            # Check size limits before writing
            await self._ensure_space(len(content))

            # Write file
            file_path = self._get_file_path(category, path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            def _write():
                temp_path = file_path.with_suffix(".tmp")
                temp_path.write_bytes(content)
                temp_path.rename(file_path)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _write)

            # Update metadata
            cache_key = self._get_cache_key(category, path)
            self._metadata[cache_key] = CacheEntry(
                path=path,
                category=category,
                size_bytes=len(content),
                cached_at=now,
                last_accessed=now,
                expires_at=expires_at,
            )
            await self._save_metadata()

            logger.debug(f"Cached {category}/{path} ({len(content)} bytes)")
            return file_path

    async def should_cache(self, category: str, path: str) -> bool:
        """Check if path should be cached per policy.

        Args:
            category: Cache category
            path: File path

        Returns:
            True if should cache
        """
        cat_config = self.categories.get(category)

        # Always cache bootloaders
        if cat_config and cat_config.always_cache:
            return True

        # Policy-based decisions
        if self.policy == "minimal":
            # Only bootloaders (handled above)
            return False

        elif self.policy == "assigned":
            # Bootloaders + assigned content
            # (Caller should check if content is assigned)
            return True

        elif self.policy == "mirror":
            # Cache everything
            return True

        elif self.policy == "pattern":
            # Match against patterns
            full_path = f"{category}/{path}"
            for pattern in self.patterns:
                if fnmatch.fnmatch(full_path, pattern):
                    return True
            return False

        return False

    async def evict(self, category: str, path: str) -> bool:
        """Evict specific cache entry.

        Args:
            category: Cache category
            path: File path

        Returns:
            True if entry was evicted
        """
        async with self._lock:
            cache_key = self._get_cache_key(category, path)
            file_path = self._get_file_path(category, path)

            def _delete():
                if file_path.exists():
                    file_path.unlink()
                    return True
                return False

            loop = asyncio.get_event_loop()
            deleted = await loop.run_in_executor(None, _delete)

            if cache_key in self._metadata:
                del self._metadata[cache_key]
                await self._save_metadata()

            if deleted:
                logger.debug(f"Evicted {cache_key}")
            return deleted

    async def evict_expired(self) -> int:
        """Evict all expired entries.

        Returns:
            Number of entries evicted
        """
        now = datetime.now(timezone.utc)
        expired = [
            (entry.category, entry.path)
            for entry in self._metadata.values()
            if entry.expires_at and entry.expires_at < now
        ]

        count = 0
        for category, path in expired:
            if await self.evict(category, path):
                count += 1

        if count > 0:
            logger.info(f"Evicted {count} expired cache entries")
        return count

    async def _ensure_space(self, needed_bytes: int):
        """Ensure enough space for new content, evicting if needed."""
        current_size = await self.get_total_size()

        if current_size + needed_bytes <= self.max_size_bytes:
            return

        # Need to evict - use LRU within priority groups
        entries = sorted(
            self._metadata.values(),
            key=lambda e: (
                self.categories.get(e.category, CacheCategory(name="")).priority,
                e.last_accessed,
            ),
        )

        target_size = self.max_size_bytes - needed_bytes
        while current_size > target_size and entries:
            entry = entries.pop(0)
            # Don't evict always_cache items
            cat = self.categories.get(entry.category)
            if cat and cat.always_cache:
                continue

            await self.evict(entry.category, entry.path)
            current_size -= entry.size_bytes

    async def get_total_size(self) -> int:
        """Get total cache size in bytes."""
        return sum(e.size_bytes for e in self._metadata.values())

    async def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        total_size = await self.get_total_size()

        # Group by category
        categories = {}
        for entry in self._metadata.values():
            if entry.category not in categories:
                categories[entry.category] = {"count": 0, "size_bytes": 0}
            categories[entry.category]["count"] += 1
            categories[entry.category]["size_bytes"] += entry.size_bytes

        return CacheStats(
            total_size_bytes=total_size,
            max_size_bytes=self.max_size_bytes,
            usage_percent=(total_size / self.max_size_bytes * 100) if self.max_size_bytes else 0,
            total_entries=len(self._metadata),
            categories=categories,
        )

    async def list_entries(self, category: str | None = None) -> list[CacheEntry]:
        """List cache entries.

        Args:
            category: Optional category filter

        Returns:
            List of cache entries
        """
        entries = list(self._metadata.values())
        if category:
            entries = [e for e in entries if e.category == category]
        return sorted(entries, key=lambda e: e.cached_at, reverse=True)

    async def clear(self, category: str | None = None) -> int:
        """Clear cache entries.

        Args:
            category: Optional category to clear (None = all)

        Returns:
            Number of entries cleared
        """
        if category:
            entries = [
                (e.category, e.path)
                for e in self._metadata.values()
                if e.category == category
            ]
        else:
            entries = [(e.category, e.path) for e in self._metadata.values()]

        count = 0
        for cat, path in entries:
            if await self.evict(cat, path):
                count += 1

        logger.info(f"Cleared {count} cache entries" + (f" in {category}" if category else ""))
        return count

    def get_disk_usage_percent(self) -> float:
        """Get disk usage percent of cache partition."""
        try:
            total, used, free = shutil.disk_usage(self.cache_dir)
            return (used / total) * 100
        except Exception:
            return 0.0
