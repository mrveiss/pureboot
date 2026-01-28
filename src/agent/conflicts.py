"""Conflict detection for offline changes vs central state.

The conflict detector:
- Detects conflicts between cached state and central state
- Stores conflicts for later resolution
- Provides API for viewing and resolving conflicts
"""
import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from src.agent.cache.state_cache import NodeStateCache

logger = logging.getLogger(__name__)


class Conflict(BaseModel):
    """Represents a conflict between local and central state."""

    id: str
    node_mac: str
    node_id: str | None = None
    local_state: str
    central_state: str
    local_updated_at: datetime
    central_updated_at: datetime
    conflict_type: Literal["state_mismatch", "missing_local", "missing_central"]
    detected_at: datetime
    resolved: bool = False
    resolution: Literal["keep_local", "keep_central", "merge"] | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ConflictDetector:
    """Detects and manages conflicts between offline changes and central state."""

    def __init__(self, db_path: Path):
        """Initialize conflict detector.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the conflict database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        def _init_db():
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conflicts (
                    id TEXT PRIMARY KEY,
                    node_mac TEXT NOT NULL,
                    node_id TEXT,
                    local_state TEXT NOT NULL,
                    central_state TEXT NOT NULL,
                    local_updated_at TEXT NOT NULL,
                    central_updated_at TEXT NOT NULL,
                    conflict_type TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    resolved INTEGER DEFAULT 0,
                    resolution TEXT,
                    resolved_at TEXT,
                    resolved_by TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conflicts_resolved
                ON conflicts (resolved)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conflicts_mac
                ON conflicts (node_mac)
            """)
            conn.commit()
            return conn

        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(None, _init_db)
        logger.info(f"Conflict detector initialized at {self.db_path}")

    async def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    async def check_conflicts(
        self,
        central_nodes: list[dict],
        state_cache: NodeStateCache,
    ) -> list[Conflict]:
        """Check for conflicts between cached and central state.

        Args:
            central_nodes: List of node data from central
            state_cache: Local node state cache

        Returns:
            List of detected conflicts
        """
        conflicts = []
        now = datetime.now(timezone.utc)

        # Create lookup of central nodes by MAC
        central_by_mac = {}
        for node in central_nodes:
            mac = node.get("mac_address", "").lower()
            if mac:
                central_by_mac[mac] = node

        # Check cached nodes against central
        cached_nodes = await state_cache.get_all_nodes()

        for cached in cached_nodes:
            mac = cached.mac_address.lower()
            central = central_by_mac.get(mac)

            if central is None:
                # Node in cache but not in central
                conflict = Conflict(
                    id=str(uuid.uuid4()),
                    node_mac=mac,
                    node_id=cached.node_id,
                    local_state=cached.state,
                    central_state="missing",
                    local_updated_at=cached.cached_at,
                    central_updated_at=now,
                    conflict_type="missing_central",
                    detected_at=now,
                )
                conflicts.append(conflict)
                await self.mark_conflict(conflict)

            elif cached.state != central.get("state"):
                # State mismatch
                central_updated = central.get("updated_at")
                if central_updated:
                    if isinstance(central_updated, str):
                        central_updated = datetime.fromisoformat(
                            central_updated.replace("Z", "+00:00")
                        )
                else:
                    central_updated = now

                conflict = Conflict(
                    id=str(uuid.uuid4()),
                    node_mac=mac,
                    node_id=cached.node_id or central.get("id"),
                    local_state=cached.state,
                    central_state=central.get("state", "unknown"),
                    local_updated_at=cached.cached_at,
                    central_updated_at=central_updated,
                    conflict_type="state_mismatch",
                    detected_at=now,
                )
                conflicts.append(conflict)
                await self.mark_conflict(conflict)

            # Remove from central lookup (to find missing_local later)
            if mac in central_by_mac:
                del central_by_mac[mac]

        # Check for nodes in central but not in cache (missing_local)
        for mac, central in central_by_mac.items():
            central_updated = central.get("updated_at")
            if central_updated:
                if isinstance(central_updated, str):
                    central_updated = datetime.fromisoformat(
                        central_updated.replace("Z", "+00:00")
                    )
            else:
                central_updated = now

            conflict = Conflict(
                id=str(uuid.uuid4()),
                node_mac=mac,
                node_id=central.get("id"),
                local_state="missing",
                central_state=central.get("state", "unknown"),
                local_updated_at=now,
                central_updated_at=central_updated,
                conflict_type="missing_local",
                detected_at=now,
            )
            conflicts.append(conflict)
            await self.mark_conflict(conflict)

        if conflicts:
            logger.warning(f"Detected {len(conflicts)} conflicts after reconnect")

        return conflicts

    async def mark_conflict(self, conflict: Conflict) -> None:
        """Store a conflict for later resolution.

        Args:
            conflict: Conflict to store
        """
        async with self._lock:

            def _insert():
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO conflicts
                    (id, node_mac, node_id, local_state, central_state,
                     local_updated_at, central_updated_at, conflict_type,
                     detected_at, resolved, resolution, resolved_at, resolved_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conflict.id,
                        conflict.node_mac,
                        conflict.node_id,
                        conflict.local_state,
                        conflict.central_state,
                        conflict.local_updated_at.isoformat(),
                        conflict.central_updated_at.isoformat(),
                        conflict.conflict_type,
                        conflict.detected_at.isoformat(),
                        1 if conflict.resolved else 0,
                        conflict.resolution,
                        conflict.resolved_at.isoformat() if conflict.resolved_at else None,
                        conflict.resolved_by,
                    ),
                )
                self._conn.commit()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _insert)

    async def get_pending_conflicts(self) -> list[Conflict]:
        """Get unresolved conflicts.

        Returns:
            List of unresolved conflicts
        """
        async with self._lock:

            def _get():
                cursor = self._conn.execute(
                    """
                    SELECT * FROM conflicts
                    WHERE resolved = 0
                    ORDER BY detected_at DESC
                    """
                )
                return cursor.fetchall()

            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(None, _get)

            return [self._row_to_conflict(row) for row in rows]

    async def get_conflict(self, conflict_id: str) -> Conflict | None:
        """Get a specific conflict by ID.

        Args:
            conflict_id: Conflict ID

        Returns:
            Conflict or None if not found
        """
        async with self._lock:

            def _get():
                cursor = self._conn.execute(
                    "SELECT * FROM conflicts WHERE id = ?",
                    (conflict_id,),
                )
                return cursor.fetchone()

            loop = asyncio.get_event_loop()
            row = await loop.run_in_executor(None, _get)

            if row:
                return self._row_to_conflict(row)
            return None

    async def resolve_conflict(
        self,
        conflict_id: str,
        resolution: Literal["keep_local", "keep_central", "merge"],
        resolved_by: str = "system",
    ) -> bool:
        """Resolve a conflict.

        Args:
            conflict_id: ID of conflict to resolve
            resolution: Resolution strategy
            resolved_by: Who resolved the conflict

        Returns:
            True if resolved, False if not found
        """
        async with self._lock:
            now = datetime.now(timezone.utc)

            def _resolve():
                cursor = self._conn.execute(
                    """
                    UPDATE conflicts
                    SET resolved = 1, resolution = ?, resolved_at = ?, resolved_by = ?
                    WHERE id = ?
                    """,
                    (resolution, now.isoformat(), resolved_by, conflict_id),
                )
                self._conn.commit()
                return cursor.rowcount > 0

            loop = asyncio.get_event_loop()
            resolved = await loop.run_in_executor(None, _resolve)

            if resolved:
                logger.info(f"Resolved conflict {conflict_id} with {resolution}")
            return resolved

    async def get_conflict_count(self) -> int:
        """Get count of pending conflicts.

        Returns:
            Number of unresolved conflicts
        """
        async with self._lock:

            def _count():
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM conflicts WHERE resolved = 0"
                )
                return cursor.fetchone()[0]

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _count)

    async def get_conflicts_for_node(self, mac: str) -> list[Conflict]:
        """Get conflicts for a specific node.

        Args:
            mac: Node MAC address

        Returns:
            List of conflicts for the node
        """
        async with self._lock:

            def _get():
                cursor = self._conn.execute(
                    """
                    SELECT * FROM conflicts
                    WHERE node_mac = ?
                    ORDER BY detected_at DESC
                    """,
                    (mac.lower(),),
                )
                return cursor.fetchall()

            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(None, _get)

            return [self._row_to_conflict(row) for row in rows]

    async def clear_resolved(self, older_than_days: int = 30) -> int:
        """Clear old resolved conflicts.

        Args:
            older_than_days: Clear conflicts resolved more than this many days ago

        Returns:
            Number of conflicts cleared
        """
        async with self._lock:
            cutoff = datetime.now(timezone.utc)

            def _clear():
                # SQLite doesn't have great date math, so we'll do it differently
                cursor = self._conn.execute(
                    """
                    DELETE FROM conflicts
                    WHERE resolved = 1
                    AND julianday('now') - julianday(resolved_at) > ?
                    """,
                    (older_than_days,),
                )
                self._conn.commit()
                return cursor.rowcount

            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(None, _clear)

            if count > 0:
                logger.info(f"Cleared {count} old resolved conflicts")
            return count

    def _row_to_conflict(self, row: sqlite3.Row) -> Conflict:
        """Convert database row to Conflict.

        Args:
            row: SQLite row

        Returns:
            Conflict instance
        """
        return Conflict(
            id=row["id"],
            node_mac=row["node_mac"],
            node_id=row["node_id"],
            local_state=row["local_state"],
            central_state=row["central_state"],
            local_updated_at=datetime.fromisoformat(row["local_updated_at"]),
            central_updated_at=datetime.fromisoformat(row["central_updated_at"]),
            conflict_type=row["conflict_type"],
            detected_at=datetime.fromisoformat(row["detected_at"]),
            resolved=bool(row["resolved"]),
            resolution=row["resolution"],
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"])
                if row["resolved_at"]
                else None
            ),
            resolved_by=row["resolved_by"],
        )
