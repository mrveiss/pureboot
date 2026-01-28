"""Queue processor for syncing offline changes when connectivity is restored.

The queue processor:
- Listens for connectivity changes
- Processes queued items when online
- Handles retries with exponential backoff
- Reports processing results
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from src.agent.connectivity import ConnectivityMonitor
from src.agent.queue import SyncQueue, QueueItem
from src.agent.proxy import CentralProxy

logger = logging.getLogger(__name__)


class ProcessResult(BaseModel):
    """Result of queue processing."""

    processed: int = 0
    failed: int = 0
    remaining: int = 0
    errors: list[str] = []
    duration_seconds: float = 0.0
    status: Literal["success", "partial", "failed", "empty"] = "success"


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
        """Initialize queue processor.

        Args:
            queue: Sync queue instance
            proxy: Central proxy instance
            connectivity: Connectivity monitor instance
            batch_size: Number of items to process per batch
            retry_delay: Delay between retries in seconds
            max_retries: Maximum retry attempts before marking failed
        """
        self.queue = queue
        self.proxy = proxy
        self.connectivity = connectivity
        self.batch_size = batch_size
        self.retry_delay = retry_delay
        self.max_retries = max_retries

        self._running = False
        self._processing = False
        self._last_result: ProcessResult | None = None

    @property
    def last_result(self) -> ProcessResult | None:
        """Get result of last processing run."""
        return self._last_result

    @property
    def is_processing(self) -> bool:
        """Check if currently processing queue."""
        return self._processing

    async def start(self):
        """Start the queue processor.

        Registers for connectivity change notifications.
        """
        if self._running:
            logger.warning("Queue processor already running")
            return

        self._running = True

        # Register for connectivity changes
        self.connectivity.add_listener(self._on_connectivity_change)

        # If already online, process any pending items
        if self.connectivity.is_online:
            asyncio.create_task(self._process_with_delay(delay=2.0))

        logger.info("Queue processor started")

    async def stop(self):
        """Stop the queue processor."""
        if not self._running:
            return

        self._running = False
        self.connectivity.remove_listener(self._on_connectivity_change)

        # Wait for any in-progress processing to complete
        while self._processing:
            await asyncio.sleep(0.1)

        logger.info("Queue processor stopped")

    async def _on_connectivity_change(self, is_online: bool):
        """Handle connectivity change notification.

        Args:
            is_online: True if now online, False if offline
        """
        if is_online and self._running:
            logger.info("Connectivity restored - processing queue")
            # Process with slight delay to ensure connection is stable
            asyncio.create_task(self._process_with_delay(delay=2.0))

    async def _process_with_delay(self, delay: float = 0.0):
        """Process queue after optional delay.

        Args:
            delay: Seconds to wait before processing
        """
        if delay > 0:
            await asyncio.sleep(delay)

        if self._running and self.connectivity.is_online:
            await self.process_queue()

    async def process_queue(self) -> ProcessResult:
        """Process pending items in queue.

        Returns:
            ProcessResult with processing statistics
        """
        if self._processing:
            logger.debug("Queue processing already in progress")
            return ProcessResult(status="empty")

        self._processing = True
        start_time = datetime.now(timezone.utc)
        result = ProcessResult()

        try:
            while self._running and self.connectivity.is_online:
                # Get batch of pending items
                items = await self.queue.peek(limit=self.batch_size)

                if not items:
                    break

                for item in items:
                    if not self._running or not self.connectivity.is_online:
                        break

                    success = await self._process_item(item)

                    if success:
                        result.processed += 1
                    else:
                        result.failed += 1

            # Get remaining count
            result.remaining = await self.queue.get_pending_count()

            # Calculate duration
            result.duration_seconds = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds()

            # Determine status
            if result.processed == 0 and result.failed == 0:
                result.status = "empty"
            elif result.failed == 0:
                result.status = "success"
            elif result.processed > 0:
                result.status = "partial"
            else:
                result.status = "failed"

            self._last_result = result
            logger.info(
                f"Queue processing complete: {result.processed} processed, "
                f"{result.failed} failed, {result.remaining} remaining"
            )

            return result

        except Exception as e:
            logger.exception(f"Error during queue processing: {e}")
            result.errors.append(str(e))
            result.status = "failed"
            self._last_result = result
            return result

        finally:
            self._processing = False

    async def _process_item(self, item: QueueItem) -> bool:
        """Process a single queue item.

        Args:
            item: Queue item to process

        Returns:
            True if processed successfully, False otherwise
        """
        # Mark as processing
        await self.queue.mark_processing(item.id)

        try:
            # Route to appropriate handler
            if item.item_type == "registration":
                success = await self._process_registration(item.payload)
            elif item.item_type == "state_update":
                success = await self._process_state_update(item.payload)
            elif item.item_type == "event":
                success = await self._process_event(item.payload)
            else:
                logger.warning(f"Unknown queue item type: {item.item_type}")
                success = False

            if success:
                # Remove from queue on success
                await self.queue.dequeue(item.id)
                return True
            else:
                # Check retry count
                if item.attempts >= self.max_retries:
                    await self.queue.mark_failed(
                        item.id,
                        f"Max retries ({self.max_retries}) exceeded",
                    )
                else:
                    # Mark pending for retry
                    await self.queue.mark_pending(item.id)
                    await asyncio.sleep(self.retry_delay)
                return False

        except Exception as e:
            logger.error(f"Error processing queue item {item.id}: {e}")

            # Check retry count
            if item.attempts >= self.max_retries:
                await self.queue.mark_failed(item.id, str(e))
            else:
                await self.queue.mark_pending(item.id)
                await asyncio.sleep(self.retry_delay)

            return False

    async def _process_registration(self, payload: dict) -> bool:
        """Process queued node registration.

        Args:
            payload: Registration payload

        Returns:
            True if registration succeeded
        """
        try:
            result = await self.proxy.register_node(payload, offline_sync=True)

            if result.get("status") == "queued":
                # Still offline, can't process
                return False

            return result.get("success", False) or "id" in result

        except Exception as e:
            logger.error(f"Failed to process registration: {e}")
            return False

    async def _process_state_update(self, payload: dict) -> bool:
        """Process queued state update.

        Args:
            payload: State update payload with node_id and new_state

        Returns:
            True if update succeeded
        """
        try:
            node_id = payload.get("node_id")
            new_state = payload.get("new_state")

            if not node_id or not new_state:
                logger.error("Invalid state update payload")
                return False

            result = await self.proxy.update_node_state(
                node_id,
                new_state,
                offline_sync=True,
            )

            if result.get("status") == "queued":
                # Still offline, can't process
                return False

            return result.get("success", False)

        except Exception as e:
            logger.error(f"Failed to process state update: {e}")
            return False

    async def _process_event(self, payload: dict) -> bool:
        """Process queued node event.

        Args:
            payload: Event payload with node_id and event data

        Returns:
            True if event was sent successfully
        """
        try:
            node_id = payload.get("node_id")
            event = payload.get("event", {})

            if not node_id:
                logger.error("Invalid event payload - missing node_id")
                return False

            result = await self.proxy.report_node_event(
                node_id,
                event,
                offline_sync=True,
            )

            if result.get("status") == "queued":
                # Still offline, can't process
                return False

            return result.get("success", False)

        except Exception as e:
            logger.error(f"Failed to process event: {e}")
            return False

    async def force_process(self) -> ProcessResult:
        """Force immediate queue processing.

        Returns:
            ProcessResult with processing statistics
        """
        return await self.process_queue()

    async def get_stats(self) -> dict:
        """Get processor statistics.

        Returns:
            Dict with processor stats
        """
        queue_stats = await self.queue.get_stats()

        return {
            "is_processing": self._processing,
            "is_online": self.connectivity.is_online,
            "queue": queue_stats,
            "last_result": self._last_result.model_dump() if self._last_result else None,
        }
