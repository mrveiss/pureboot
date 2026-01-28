"""Sync queue for pending state changes during offline operation.

The sync queue:
- Stores pending operations when central is unreachable
- Persists to SQLite for durability across restarts
- Tracks retry attempts and failures
- Provides ordered processing (FIFO)
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

logger = logging.getLogger(__name__)


class QueueItem(BaseModel):
    """Item in the sync queue."""

    id: str
    item_type: str  # registration, state_update, event
    payload: dict
    created_at: datetime
    attempts: int = 0
    last_attempt_at: datetime | None = None
    last_error: str | None = None
    status: Literal["pending", "processing", "failed"] = "pending"

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class SyncQueue:
    """Queue for pending state changes during offline operation."""

    def __init__(self, db_path: Path):
        """Initialize sync queue.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the queue database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        def _init_db():
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_queue (
                    id TEXT PRIMARY KEY,
                    item_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    last_attempt_at TEXT,
                    last_error TEXT,
                    status TEXT DEFAULT 'pending'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_queue_status
                ON sync_queue (status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_queue_created
                ON sync_queue (created_at)
            """)
            conn.commit()
            return conn

        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(None, _init_db)
        logger.info(f"Sync queue initialized at {self.db_path}")

    async def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    async def enqueue(self, item: QueueItem) -> str:
        """Add item to queue.

        Args:
            item: Queue item to add

        Returns:
            Queue item ID
        """
        async with self._lock:
            if not item.id:
                item.id = str(uuid.uuid4())

            def _insert():
                self._conn.execute(
                    """
                    INSERT INTO sync_queue
                    (id, item_type, payload, created_at, attempts,
                     last_attempt_at, last_error, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.item_type,
                        json.dumps(item.payload),
                        item.created_at.isoformat(),
                        item.attempts,
                        item.last_attempt_at.isoformat() if item.last_attempt_at else None,
                        item.last_error,
                        item.status,
                    ),
                )
                self._conn.commit()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _insert)

            logger.debug(f"Enqueued {item.item_type}: {item.id}")
            return item.id

    async def peek(self, limit: int = 10) -> list[QueueItem]:
        """Get pending items without removing them.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of pending queue items (oldest first)
        """
        async with self._lock:

            def _peek():
                cursor = self._conn.execute(
                    """
                    SELECT * FROM sync_queue
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return cursor.fetchall()

            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(None, _peek)

            return [self._row_to_item(row) for row in rows]

    async def get_item(self, queue_id: str) -> QueueItem | None:
        """Get a specific queue item by ID.

        Args:
            queue_id: Queue item ID

        Returns:
            Queue item or None if not found
        """
        async with self._lock:

            def _get():
                cursor = self._conn.execute(
                    "SELECT * FROM sync_queue WHERE id = ?",
                    (queue_id,),
                )
                return cursor.fetchone()

            loop = asyncio.get_event_loop()
            row = await loop.run_in_executor(None, _get)

            if row:
                return self._row_to_item(row)
            return None

    async def dequeue(self, queue_id: str) -> bool:
        """Remove item from queue after successful sync.

        Args:
            queue_id: Queue item ID to remove

        Returns:
            True if item was removed, False if not found
        """
        async with self._lock:

            def _delete():
                cursor = self._conn.execute(
                    "DELETE FROM sync_queue WHERE id = ?",
                    (queue_id,),
                )
                self._conn.commit()
                return cursor.rowcount > 0

            loop = asyncio.get_event_loop()
            removed = await loop.run_in_executor(None, _delete)

            if removed:
                logger.debug(f"Dequeued item: {queue_id}")
            return removed

    async def mark_processing(self, queue_id: str) -> bool:
        """Mark item as being processed.

        Args:
            queue_id: Queue item ID

        Returns:
            True if updated, False if not found
        """
        async with self._lock:

            def _update():
                now = datetime.now(timezone.utc).isoformat()
                cursor = self._conn.execute(
                    """
                    UPDATE sync_queue
                    SET status = 'processing', last_attempt_at = ?, attempts = attempts + 1
                    WHERE id = ?
                    """,
                    (now, queue_id),
                )
                self._conn.commit()
                return cursor.rowcount > 0

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _update)

    async def mark_pending(self, queue_id: str) -> bool:
        """Mark item back as pending (for retry).

        Args:
            queue_id: Queue item ID

        Returns:
            True if updated, False if not found
        """
        async with self._lock:

            def _update():
                cursor = self._conn.execute(
                    """
                    UPDATE sync_queue
                    SET status = 'pending'
                    WHERE id = ?
                    """,
                    (queue_id,),
                )
                self._conn.commit()
                return cursor.rowcount > 0

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _update)

    async def mark_failed(self, queue_id: str, error: str) -> bool:
        """Mark item as failed with error message.

        Args:
            queue_id: Queue item ID
            error: Error message describing the failure

        Returns:
            True if updated, False if not found
        """
        async with self._lock:

            def _update():
                cursor = self._conn.execute(
                    """
                    UPDATE sync_queue
                    SET status = 'failed', last_error = ?
                    WHERE id = ?
                    """,
                    (error, queue_id),
                )
                self._conn.commit()
                return cursor.rowcount > 0

            loop = asyncio.get_event_loop()
            updated = await loop.run_in_executor(None, _update)

            if updated:
                logger.warning(f"Queue item {queue_id} marked failed: {error}")
            return updated

    async def get_pending_count(self) -> int:
        """Get count of pending items.

        Returns:
            Number of pending items in queue
        """
        async with self._lock:

            def _count():
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM sync_queue WHERE status = 'pending'"
                )
                return cursor.fetchone()[0]

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _count)

    async def get_failed_count(self) -> int:
        """Get count of failed items.

        Returns:
            Number of failed items in queue
        """
        async with self._lock:

            def _count():
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM sync_queue WHERE status = 'failed'"
                )
                return cursor.fetchone()[0]

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _count)

    async def get_failed_items(self) -> list[QueueItem]:
        """Get items that failed to sync.

        Returns:
            List of failed queue items
        """
        async with self._lock:

            def _get_failed():
                cursor = self._conn.execute(
                    """
                    SELECT * FROM sync_queue
                    WHERE status = 'failed'
                    ORDER BY created_at ASC
                    """
                )
                return cursor.fetchall()

            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(None, _get_failed)

            return [self._row_to_item(row) for row in rows]

    async def clear_failed(self) -> int:
        """Clear failed items from queue.

        Returns:
            Number of items cleared
        """
        async with self._lock:

            def _clear():
                cursor = self._conn.execute(
                    "DELETE FROM sync_queue WHERE status = 'failed'"
                )
                self._conn.commit()
                return cursor.rowcount

            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(None, _clear)

            if count > 0:
                logger.info(f"Cleared {count} failed queue items")
            return count

    async def retry_failed(self) -> int:
        """Reset failed items to pending for retry.

        Returns:
            Number of items reset
        """
        async with self._lock:

            def _retry():
                cursor = self._conn.execute(
                    """
                    UPDATE sync_queue
                    SET status = 'pending', last_error = NULL
                    WHERE status = 'failed'
                    """
                )
                self._conn.commit()
                return cursor.rowcount

            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(None, _retry)

            if count > 0:
                logger.info(f"Reset {count} failed items for retry")
            return count

    async def get_stats(self) -> dict:
        """Get queue statistics.

        Returns:
            Dict with queue statistics
        """
        async with self._lock:

            def _stats():
                cursor = self._conn.execute("""
                    SELECT status, COUNT(*) as count
                    FROM sync_queue
                    GROUP BY status
                """)
                return {row["status"]: row["count"] for row in cursor.fetchall()}

            loop = asyncio.get_event_loop()
            status_counts = await loop.run_in_executor(None, _stats)

            return {
                "pending": status_counts.get("pending", 0),
                "processing": status_counts.get("processing", 0),
                "failed": status_counts.get("failed", 0),
                "total": sum(status_counts.values()),
            }

    def _row_to_item(self, row: sqlite3.Row) -> QueueItem:
        """Convert database row to QueueItem.

        Args:
            row: SQLite row

        Returns:
            QueueItem instance
        """
        return QueueItem(
            id=row["id"],
            item_type=row["item_type"],
            payload=json.loads(row["payload"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            attempts=row["attempts"],
            last_attempt_at=(
                datetime.fromisoformat(row["last_attempt_at"])
                if row["last_attempt_at"]
                else None
            ),
            last_error=row["last_error"],
            status=row["status"],
        )
