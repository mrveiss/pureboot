"""Node state cache using SQLite for local persistence.

The state cache stores node information locally to:
- Enable fast boot script generation without central roundtrip
- Provide resilience when central is temporarily unreachable
- Track nodes seen at this site
"""
import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Default cache TTL in seconds (5 minutes)
DEFAULT_TTL_SECONDS = 300


class CachedNode(BaseModel):
    """Cached node state."""

    mac_address: str
    node_id: str | None = None
    state: str
    workflow_id: str | None = None
    group_id: str | None = None
    ip_address: str | None = None
    vendor: str | None = None
    model: str | None = None
    cached_at: datetime
    expires_at: datetime
    raw_data: dict[str, Any] = {}

    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def ttl_seconds(self) -> int:
        """Get remaining TTL in seconds."""
        remaining = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(remaining))


class NodeStateCache:
    """Local SQLite cache for node state.

    Stores node information in a local SQLite database to provide
    fast lookups and offline resilience.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS nodes (
        mac_address TEXT PRIMARY KEY,
        node_id TEXT,
        state TEXT NOT NULL,
        workflow_id TEXT,
        group_id TEXT,
        ip_address TEXT,
        vendor TEXT,
        model TEXT,
        cached_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        raw_data TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_nodes_group ON nodes(group_id);
    CREATE INDEX IF NOT EXISTS idx_nodes_state ON nodes(state);
    CREATE INDEX IF NOT EXISTS idx_nodes_expires ON nodes(expires_at);
    """

    def __init__(self, db_path: Path, default_ttl: int = DEFAULT_TTL_SECONDS):
        """Initialize the state cache.

        Args:
            db_path: Path to SQLite database file
            default_ttl: Default TTL for cache entries in seconds
        """
        self.db_path = Path(db_path)
        self.default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize the database schema."""
        if self._initialized:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        def _init_db():
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(self.SCHEMA)
            conn.commit()
            conn.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _init_db)
        self._initialized = True
        logger.info(f"Node state cache initialized at {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    async def get_node(self, mac: str) -> CachedNode | None:
        """Get cached node by MAC address.

        Args:
            mac: MAC address (normalized to lowercase with colons)

        Returns:
            CachedNode if found and not expired, None otherwise
        """
        await self.initialize()
        mac = mac.lower().replace("-", ":")

        def _get():
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM nodes WHERE mac_address = ?",
                    (mac,)
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        row = await loop.run_in_executor(None, _get)

        if row is None:
            return None

        node = CachedNode(
            mac_address=row["mac_address"],
            node_id=row["node_id"],
            state=row["state"],
            workflow_id=row["workflow_id"],
            group_id=row["group_id"],
            ip_address=row["ip_address"],
            vendor=row["vendor"],
            model=row["model"],
            cached_at=datetime.fromisoformat(row["cached_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            raw_data=json.loads(row["raw_data"]),
        )

        # Check expiry but still return - let caller decide
        if node.is_expired:
            logger.debug(f"Cache entry for {mac} is expired (ttl was {self.default_ttl}s)")

        return node

    async def set_node(
        self,
        node: CachedNode | None = None,
        *,
        mac_address: str | None = None,
        node_id: str | None = None,
        state: str | None = None,
        workflow_id: str | None = None,
        group_id: str | None = None,
        ip_address: str | None = None,
        vendor: str | None = None,
        model: str | None = None,
        raw_data: dict | None = None,
        ttl: int | None = None,
    ) -> CachedNode:
        """Cache or update node state.

        Can pass either a CachedNode object or individual fields.

        Args:
            node: CachedNode to cache
            mac_address: MAC address (required if node not provided)
            state: Node state (required if node not provided)
            ttl: Optional TTL override in seconds

        Returns:
            The cached node
        """
        await self.initialize()

        if node is None:
            if mac_address is None or state is None:
                raise ValueError("mac_address and state required when node not provided")

            now = datetime.now(timezone.utc)
            ttl_secs = ttl if ttl is not None else self.default_ttl

            node = CachedNode(
                mac_address=mac_address.lower().replace("-", ":"),
                node_id=node_id,
                state=state,
                workflow_id=workflow_id,
                group_id=group_id,
                ip_address=ip_address,
                vendor=vendor,
                model=model,
                cached_at=now,
                expires_at=now + timedelta(seconds=ttl_secs),
                raw_data=raw_data or {},
            )

        def _set():
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nodes
                    (mac_address, node_id, state, workflow_id, group_id,
                     ip_address, vendor, model, cached_at, expires_at, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node.mac_address,
                        node.node_id,
                        node.state,
                        node.workflow_id,
                        node.group_id,
                        node.ip_address,
                        node.vendor,
                        node.model,
                        node.cached_at.isoformat(),
                        node.expires_at.isoformat(),
                        json.dumps(node.raw_data),
                    )
                )
                conn.commit()
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _set)
        logger.debug(f"Cached node {node.mac_address} state={node.state}")
        return node

    async def get_nodes_by_group(self, group_id: str) -> list[CachedNode]:
        """Get all cached nodes in a group.

        Args:
            group_id: Group ID to filter by

        Returns:
            List of cached nodes (may include expired)
        """
        await self.initialize()

        def _get():
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM nodes WHERE group_id = ?",
                    (group_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, _get)

        return [
            CachedNode(
                mac_address=row["mac_address"],
                node_id=row["node_id"],
                state=row["state"],
                workflow_id=row["workflow_id"],
                group_id=row["group_id"],
                ip_address=row["ip_address"],
                vendor=row["vendor"],
                model=row["model"],
                cached_at=datetime.fromisoformat(row["cached_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                raw_data=json.loads(row["raw_data"]),
            )
            for row in rows
        ]

    async def get_all_nodes(self) -> list[CachedNode]:
        """Get all cached nodes.

        Returns:
            List of all cached nodes
        """
        await self.initialize()

        def _get():
            conn = self._get_connection()
            try:
                cursor = conn.execute("SELECT * FROM nodes")
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, _get)

        return [
            CachedNode(
                mac_address=row["mac_address"],
                node_id=row["node_id"],
                state=row["state"],
                workflow_id=row["workflow_id"],
                group_id=row["group_id"],
                ip_address=row["ip_address"],
                vendor=row["vendor"],
                model=row["model"],
                cached_at=datetime.fromisoformat(row["cached_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                raw_data=json.loads(row["raw_data"]),
            )
            for row in rows
        ]

    async def invalidate(self, mac: str) -> bool:
        """Remove node from cache.

        Args:
            mac: MAC address to invalidate

        Returns:
            True if entry was removed, False if not found
        """
        await self.initialize()
        mac = mac.lower().replace("-", ":")

        def _delete():
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM nodes WHERE mac_address = ?",
                    (mac,)
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        deleted = await loop.run_in_executor(None, _delete)
        if deleted:
            logger.debug(f"Invalidated cache for {mac}")
        return deleted

    async def invalidate_expired(self) -> int:
        """Remove all expired entries from cache.

        Returns:
            Number of entries removed
        """
        await self.initialize()
        now = datetime.now(timezone.utc).isoformat()

        def _delete_expired():
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM nodes WHERE expires_at < ?",
                    (now,)
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        count = await loop.run_in_executor(None, _delete_expired)
        if count > 0:
            logger.info(f"Evicted {count} expired cache entries")
        return count

    async def get_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        await self.initialize()

        def _stats():
            conn = self._get_connection()
            try:
                cursor = conn.execute("SELECT COUNT(*) as total FROM nodes")
                total = cursor.fetchone()["total"]

                now = datetime.now(timezone.utc).isoformat()
                cursor = conn.execute(
                    "SELECT COUNT(*) as expired FROM nodes WHERE expires_at < ?",
                    (now,)
                )
                expired = cursor.fetchone()["expired"]

                cursor = conn.execute(
                    "SELECT MIN(cached_at) as oldest FROM nodes"
                )
                row = cursor.fetchone()
                oldest = row["oldest"] if row else None

                return {
                    "total_entries": total,
                    "expired_entries": expired,
                    "valid_entries": total - expired,
                    "oldest_entry": oldest,
                }
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _stats)

    async def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries removed
        """
        await self.initialize()

        def _clear():
            conn = self._get_connection()
            try:
                cursor = conn.execute("DELETE FROM nodes")
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

        loop = asyncio.get_event_loop()
        count = await loop.run_in_executor(None, _clear)
        logger.info(f"Cleared {count} cache entries")
        return count
