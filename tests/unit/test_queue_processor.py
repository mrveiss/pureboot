"""Tests for queue processor."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.queue_processor import QueueProcessor, ProcessResult
from src.agent.queue import QueueItem


@pytest.fixture
def mock_queue():
    """Create mock sync queue."""
    queue = AsyncMock()
    queue.peek = AsyncMock(return_value=[])
    queue.get_pending_count = AsyncMock(return_value=0)
    queue.mark_processing = AsyncMock(return_value=True)
    queue.mark_pending = AsyncMock(return_value=True)
    queue.mark_failed = AsyncMock(return_value=True)
    queue.dequeue = AsyncMock(return_value=True)
    queue.get_stats = AsyncMock(return_value={
        "pending": 0,
        "processing": 0,
        "failed": 0,
        "total": 0,
    })
    return queue


@pytest.fixture
def mock_proxy():
    """Create mock central proxy."""
    proxy = AsyncMock()
    proxy.register_node = AsyncMock(return_value={"success": True, "id": "node-001"})
    proxy.update_node_state = AsyncMock(return_value={"success": True})
    proxy.report_node_event = AsyncMock(return_value={"success": True})
    return proxy


@pytest.fixture
def mock_connectivity():
    """Create mock connectivity monitor."""
    conn = MagicMock()
    conn.is_online = True
    conn.add_listener = MagicMock()
    conn.remove_listener = MagicMock()
    return conn


@pytest.fixture
def processor(mock_queue, mock_proxy, mock_connectivity):
    """Create queue processor for testing."""
    return QueueProcessor(
        queue=mock_queue,
        proxy=mock_proxy,
        connectivity=mock_connectivity,
        batch_size=10,
        retry_delay=0.1,  # Fast retry for tests
        max_retries=3,
    )


@pytest.fixture
def sample_items():
    """Create sample queue items."""
    return [
        QueueItem(
            id="item-1",
            item_type="registration",
            payload={"mac_address": "00:11:22:33:44:55"},
            created_at=datetime.now(timezone.utc),
        ),
        QueueItem(
            id="item-2",
            item_type="state_update",
            payload={"node_id": "node-001", "new_state": "active"},
            created_at=datetime.now(timezone.utc),
        ),
        QueueItem(
            id="item-3",
            item_type="event",
            payload={"node_id": "node-001", "event": {"type": "boot_complete"}},
            created_at=datetime.now(timezone.utc),
        ),
    ]


class TestQueueProcessor:
    """Tests for QueueProcessor class."""

    @pytest.mark.asyncio
    async def test_start_registers_listener(self, processor, mock_connectivity):
        """Test start registers connectivity listener."""
        await processor.start()

        mock_connectivity.add_listener.assert_called_once()
        assert processor._running is True

        await processor.stop()

    @pytest.mark.asyncio
    async def test_stop_removes_listener(self, processor, mock_connectivity):
        """Test stop removes connectivity listener."""
        await processor.start()
        await processor.stop()

        mock_connectivity.remove_listener.assert_called_once()
        assert processor._running is False

    @pytest.mark.asyncio
    async def test_process_on_reconnect(
        self, processor, mock_queue, mock_connectivity, sample_items
    ):
        """Test queue processing triggers on reconnect."""
        # Setup items in queue
        mock_queue.peek.side_effect = [sample_items, []]

        await processor.start()

        # Simulate connectivity restored
        listener = mock_connectivity.add_listener.call_args[0][0]
        await listener(True)

        # Wait for processing
        await asyncio.sleep(3)

        # Should have processed items
        assert mock_queue.peek.called

        await processor.stop()

    @pytest.mark.asyncio
    async def test_process_registration(
        self, processor, mock_queue, mock_proxy, sample_items
    ):
        """Test processing registration item."""
        registration_item = sample_items[0]
        mock_queue.peek.side_effect = [[registration_item], []]

        result = await processor.process_queue()

        mock_proxy.register_node.assert_called_once()
        mock_queue.dequeue.assert_called_with(registration_item.id)
        assert result.processed == 1

    @pytest.mark.asyncio
    async def test_process_state_update(
        self, processor, mock_queue, mock_proxy, sample_items
    ):
        """Test processing state update item."""
        state_item = sample_items[1]
        mock_queue.peek.side_effect = [[state_item], []]

        result = await processor.process_queue()

        mock_proxy.update_node_state.assert_called_once_with(
            "node-001", "active", offline_sync=True
        )
        mock_queue.dequeue.assert_called_with(state_item.id)
        assert result.processed == 1

    @pytest.mark.asyncio
    async def test_process_event(
        self, processor, mock_queue, mock_proxy, sample_items
    ):
        """Test processing event item."""
        event_item = sample_items[2]
        mock_queue.peek.side_effect = [[event_item], []]

        result = await processor.process_queue()

        mock_proxy.report_node_event.assert_called_once()
        mock_queue.dequeue.assert_called_with(event_item.id)
        assert result.processed == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure(
        self, processor, mock_queue, mock_proxy, sample_items
    ):
        """Test retry when processing fails."""
        item = sample_items[0]
        item.attempts = 0
        mock_queue.peek.side_effect = [[item], []]
        mock_proxy.register_node.return_value = {"success": False}

        result = await processor.process_queue()

        # Should mark pending for retry, not failed (not at max retries)
        mock_queue.mark_pending.assert_called()
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(
        self, processor, mock_queue, mock_proxy, sample_items
    ):
        """Test marking failed after max retries."""
        item = sample_items[0]
        item.attempts = 3  # At max retries
        mock_queue.peek.side_effect = [[item], []]
        mock_proxy.register_node.return_value = {"success": False}

        result = await processor.process_queue()

        # Should mark as failed
        mock_queue.mark_failed.assert_called()
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_batch_processing(
        self, processor, mock_queue, mock_proxy, sample_items
    ):
        """Test processing items in batches."""
        # Return all items then empty
        mock_queue.peek.side_effect = [sample_items, []]

        result = await processor.process_queue()

        # Should have processed all items
        assert result.processed == 3
        assert mock_queue.dequeue.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_queue(self, processor, mock_queue):
        """Test processing empty queue."""
        mock_queue.peek.return_value = []

        result = await processor.process_queue()

        assert result.status == "empty"
        assert result.processed == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_partial_success(
        self, processor, mock_queue, mock_proxy, sample_items
    ):
        """Test partial success status."""
        mock_queue.peek.side_effect = [sample_items, []]
        # First succeeds, second fails, third succeeds
        mock_proxy.register_node.return_value = {"success": True, "id": "node-001"}
        mock_proxy.update_node_state.return_value = {"success": False}
        mock_proxy.report_node_event.return_value = {"success": True}

        # Update item attempts to trigger failure
        sample_items[1].attempts = 3

        result = await processor.process_queue()

        assert result.status == "partial"
        assert result.processed == 2
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_stops_when_offline(
        self, processor, mock_queue, mock_proxy, mock_connectivity, sample_items
    ):
        """Test processing stops when connectivity lost."""
        mock_queue.peek.side_effect = [sample_items]

        # Go offline after first item
        call_count = 0

        async def register_with_offline(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                mock_connectivity.is_online = False
            return {"success": True, "id": "node-001"}

        mock_proxy.register_node.side_effect = register_with_offline
        mock_proxy.update_node_state.return_value = {"success": True}

        await processor.process_queue()

        # Should not process all items
        assert call_count < 3

    @pytest.mark.asyncio
    async def test_force_process(self, processor, mock_queue):
        """Test force processing."""
        mock_queue.peek.return_value = []

        result = await processor.force_process()

        assert result is not None
        assert mock_queue.peek.called

    @pytest.mark.asyncio
    async def test_get_stats(self, processor, mock_queue, mock_connectivity):
        """Test getting processor stats."""
        stats = await processor.get_stats()

        assert "is_processing" in stats
        assert "is_online" in stats
        assert "queue" in stats
        assert stats["is_online"] == mock_connectivity.is_online

    @pytest.mark.asyncio
    async def test_queued_status_handling(
        self, processor, mock_queue, mock_proxy, sample_items
    ):
        """Test handling of queued status (still offline)."""
        item = sample_items[0]
        mock_queue.peek.side_effect = [[item], []]
        mock_proxy.register_node.return_value = {"status": "queued"}

        result = await processor.process_queue()

        # Should mark pending for later retry
        mock_queue.mark_pending.assert_called()
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_invalid_state_update_payload(
        self, processor, mock_queue, mock_proxy
    ):
        """Test handling invalid state update payload."""
        invalid_item = QueueItem(
            id="invalid-1",
            item_type="state_update",
            payload={},  # Missing node_id and new_state
            created_at=datetime.now(timezone.utc),
            attempts=3,  # At max retries
        )
        mock_queue.peek.side_effect = [[invalid_item], []]

        result = await processor.process_queue()

        mock_queue.mark_failed.assert_called()
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_unknown_item_type(self, processor, mock_queue):
        """Test handling unknown item type."""
        unknown_item = QueueItem(
            id="unknown-1",
            item_type="unknown_type",
            payload={},
            created_at=datetime.now(timezone.utc),
            attempts=3,
        )
        mock_queue.peek.side_effect = [[unknown_item], []]

        result = await processor.process_queue()

        mock_queue.mark_failed.assert_called()
        assert result.failed == 1


class TestProcessResult:
    """Tests for ProcessResult model."""

    def test_create_result(self):
        """Test creating a process result."""
        result = ProcessResult(
            processed=5,
            failed=1,
            remaining=3,
            errors=["Error 1"],
            duration_seconds=2.5,
            status="partial",
        )

        assert result.processed == 5
        assert result.failed == 1
        assert result.remaining == 3
        assert len(result.errors) == 1
        assert result.duration_seconds == 2.5
        assert result.status == "partial"

    def test_result_defaults(self):
        """Test process result default values."""
        result = ProcessResult()

        assert result.processed == 0
        assert result.failed == 0
        assert result.remaining == 0
        assert result.errors == []
        assert result.duration_seconds == 0.0
        assert result.status == "success"
