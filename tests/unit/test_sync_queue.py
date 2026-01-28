"""Tests for sync queue."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.agent.queue import SyncQueue, QueueItem


@pytest.fixture
async def queue(tmp_path):
    """Create a sync queue for testing."""
    db_path = tmp_path / "queue.db"
    q = SyncQueue(db_path=db_path)
    await q.initialize()
    yield q
    await q.close()


@pytest.fixture
def sample_item():
    """Create a sample queue item."""
    return QueueItem(
        id="test-item-1",
        item_type="registration",
        payload={"mac_address": "00:11:22:33:44:55", "hostname": "test-node"},
        created_at=datetime.now(timezone.utc),
    )


class TestSyncQueue:
    """Tests for SyncQueue class."""

    @pytest.mark.asyncio
    async def test_initialize(self, tmp_path):
        """Test queue initialization creates database."""
        db_path = tmp_path / "test" / "queue.db"
        queue = SyncQueue(db_path=db_path)

        await queue.initialize()

        assert db_path.exists()
        await queue.close()

    @pytest.mark.asyncio
    async def test_enqueue_item(self, queue, sample_item):
        """Test enqueuing an item."""
        queue_id = await queue.enqueue(sample_item)

        assert queue_id == sample_item.id

        # Verify item is in queue
        items = await queue.peek()
        assert len(items) == 1
        assert items[0].id == sample_item.id

    @pytest.mark.asyncio
    async def test_enqueue_generates_id(self, queue):
        """Test enqueue generates ID if not provided."""
        item = QueueItem(
            id="",
            item_type="event",
            payload={"event": "test"},
            created_at=datetime.now(timezone.utc),
        )

        queue_id = await queue.enqueue(item)

        assert queue_id != ""
        assert len(queue_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_dequeue_item(self, queue, sample_item):
        """Test dequeuing an item."""
        await queue.enqueue(sample_item)

        removed = await queue.dequeue(sample_item.id)
        assert removed is True

        # Verify item is gone
        items = await queue.peek()
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_dequeue_nonexistent(self, queue):
        """Test dequeuing nonexistent item."""
        removed = await queue.dequeue("nonexistent-id")
        assert removed is False

    @pytest.mark.asyncio
    async def test_mark_failed(self, queue, sample_item):
        """Test marking item as failed."""
        await queue.enqueue(sample_item)

        updated = await queue.mark_failed(sample_item.id, "Connection error")
        assert updated is True

        # Verify status
        item = await queue.get_item(sample_item.id)
        assert item.status == "failed"
        assert item.last_error == "Connection error"

    @pytest.mark.asyncio
    async def test_mark_processing(self, queue, sample_item):
        """Test marking item as processing."""
        await queue.enqueue(sample_item)

        updated = await queue.mark_processing(sample_item.id)
        assert updated is True

        item = await queue.get_item(sample_item.id)
        assert item.status == "processing"
        assert item.attempts == 1
        assert item.last_attempt_at is not None

    @pytest.mark.asyncio
    async def test_mark_pending(self, queue, sample_item):
        """Test marking item back to pending."""
        await queue.enqueue(sample_item)
        await queue.mark_processing(sample_item.id)

        updated = await queue.mark_pending(sample_item.id)
        assert updated is True

        item = await queue.get_item(sample_item.id)
        assert item.status == "pending"

    @pytest.mark.asyncio
    async def test_pending_count(self, queue):
        """Test getting pending item count."""
        # Add multiple items
        for i in range(5):
            item = QueueItem(
                id=f"item-{i}",
                item_type="registration",
                payload={"index": i},
                created_at=datetime.now(timezone.utc),
            )
            await queue.enqueue(item)

        count = await queue.get_pending_count()
        assert count == 5

    @pytest.mark.asyncio
    async def test_failed_count(self, queue, sample_item):
        """Test getting failed item count."""
        await queue.enqueue(sample_item)
        await queue.mark_failed(sample_item.id, "Error")

        count = await queue.get_failed_count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_failed_items(self, queue):
        """Test getting failed items."""
        # Add items and fail some
        for i in range(5):
            item = QueueItem(
                id=f"item-{i}",
                item_type="registration",
                payload={"index": i},
                created_at=datetime.now(timezone.utc),
            )
            await queue.enqueue(item)
            if i % 2 == 0:  # Fail even items
                await queue.mark_failed(f"item-{i}", "Test error")

        failed = await queue.get_failed_items()
        assert len(failed) == 3  # items 0, 2, 4

    @pytest.mark.asyncio
    async def test_clear_failed(self, queue, sample_item):
        """Test clearing failed items."""
        await queue.enqueue(sample_item)
        await queue.mark_failed(sample_item.id, "Error")

        cleared = await queue.clear_failed()
        assert cleared == 1

        count = await queue.get_failed_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_retry_failed(self, queue, sample_item):
        """Test resetting failed items for retry."""
        await queue.enqueue(sample_item)
        await queue.mark_failed(sample_item.id, "Error")

        reset = await queue.retry_failed()
        assert reset == 1

        item = await queue.get_item(sample_item.id)
        assert item.status == "pending"
        assert item.last_error is None

    @pytest.mark.asyncio
    async def test_queue_persistence(self, tmp_path):
        """Test queue persists across connections."""
        db_path = tmp_path / "persist.db"

        # Create queue and add item
        queue1 = SyncQueue(db_path=db_path)
        await queue1.initialize()

        item = QueueItem(
            id="persist-test",
            item_type="registration",
            payload={"test": "data"},
            created_at=datetime.now(timezone.utc),
        )
        await queue1.enqueue(item)
        await queue1.close()

        # Reopen queue and verify item exists
        queue2 = SyncQueue(db_path=db_path)
        await queue2.initialize()

        items = await queue2.peek()
        assert len(items) == 1
        assert items[0].id == "persist-test"

        await queue2.close()

    @pytest.mark.asyncio
    async def test_peek_respects_limit(self, queue):
        """Test peek respects limit parameter."""
        # Add 10 items
        for i in range(10):
            item = QueueItem(
                id=f"item-{i}",
                item_type="event",
                payload={"index": i},
                created_at=datetime.now(timezone.utc),
            )
            await queue.enqueue(item)

        items = await queue.peek(limit=3)
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_peek_fifo_order(self, queue):
        """Test peek returns items in FIFO order."""
        # Add items with slight delay to ensure ordering
        for i in range(3):
            item = QueueItem(
                id=f"item-{i}",
                item_type="event",
                payload={"index": i},
                created_at=datetime.now(timezone.utc),
            )
            await queue.enqueue(item)

        items = await queue.peek()

        # Should be in order added
        assert items[0].id == "item-0"
        assert items[1].id == "item-1"
        assert items[2].id == "item-2"

    @pytest.mark.asyncio
    async def test_retry_tracking(self, queue, sample_item):
        """Test retry attempts are tracked."""
        await queue.enqueue(sample_item)

        # First attempt
        await queue.mark_processing(sample_item.id)
        await queue.mark_pending(sample_item.id)

        # Second attempt
        await queue.mark_processing(sample_item.id)
        await queue.mark_pending(sample_item.id)

        item = await queue.get_item(sample_item.id)
        assert item.attempts == 2

    @pytest.mark.asyncio
    async def test_get_stats(self, queue):
        """Test getting queue statistics."""
        # Add various items
        for i in range(3):
            item = QueueItem(
                id=f"pending-{i}",
                item_type="registration",
                payload={},
                created_at=datetime.now(timezone.utc),
            )
            await queue.enqueue(item)

        # Add and fail one
        failed_item = QueueItem(
            id="failed-1",
            item_type="event",
            payload={},
            created_at=datetime.now(timezone.utc),
        )
        await queue.enqueue(failed_item)
        await queue.mark_failed("failed-1", "Error")

        # Add and mark processing
        processing_item = QueueItem(
            id="processing-1",
            item_type="state_update",
            payload={},
            created_at=datetime.now(timezone.utc),
        )
        await queue.enqueue(processing_item)
        await queue.mark_processing("processing-1")

        stats = await queue.get_stats()

        assert stats["pending"] == 3
        assert stats["failed"] == 1
        assert stats["processing"] == 1
        assert stats["total"] == 5

    @pytest.mark.asyncio
    async def test_peek_only_returns_pending(self, queue, sample_item):
        """Test peek only returns pending items."""
        await queue.enqueue(sample_item)

        # Mark as processing
        await queue.mark_processing(sample_item.id)

        # Peek should return empty
        items = await queue.peek()
        assert len(items) == 0


class TestQueueItem:
    """Tests for QueueItem model."""

    def test_create_queue_item(self):
        """Test creating a queue item."""
        item = QueueItem(
            id="test-1",
            item_type="registration",
            payload={"mac": "00:11:22:33:44:55"},
            created_at=datetime.now(timezone.utc),
        )

        assert item.id == "test-1"
        assert item.item_type == "registration"
        assert item.payload["mac"] == "00:11:22:33:44:55"
        assert item.attempts == 0
        assert item.status == "pending"

    def test_queue_item_defaults(self):
        """Test queue item default values."""
        item = QueueItem(
            id="test-2",
            item_type="event",
            payload={},
            created_at=datetime.now(timezone.utc),
        )

        assert item.attempts == 0
        assert item.last_attempt_at is None
        assert item.last_error is None
        assert item.status == "pending"
