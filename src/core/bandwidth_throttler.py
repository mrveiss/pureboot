"""Priority-based bandwidth throttler for fair file serving."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# Minimum bandwidth floor per transfer (1 Mbps)
MIN_BANDWIDTH_MBPS = 1
MIN_BANDWIDTH_BYTES_PER_SEC = MIN_BANDWIDTH_MBPS * 125_000  # 1 Mbps = 125,000 bytes/sec


@dataclass
class ActiveTransfer:
    """Tracks an active file transfer."""

    transfer_id: str
    file_path: str
    total_bytes: int
    bytes_transferred: int = 0
    started_at: float = field(default_factory=time.time)
    priority: float = 1.0

    @property
    def progress(self) -> float:
        """Return progress as a fraction (0.0 to 1.0)."""
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, self.bytes_transferred / self.total_bytes)

    @property
    def remaining_bytes(self) -> int:
        """Return remaining bytes to transfer."""
        return max(0, self.total_bytes - self.bytes_transferred)


class BandwidthThrottler:
    """
    Priority-based bandwidth throttler for file transfers.

    Fairly distributes bandwidth among active transfers with priority
    weighting. Small files and near-completion transfers get higher priority.
    """

    def __init__(self, total_bandwidth_mbps: int = 1000):
        """
        Initialize throttler.

        Args:
            total_bandwidth_mbps: Total bandwidth limit in Mbps
        """
        self._total_bandwidth_bytes_per_sec = total_bandwidth_mbps * 125_000
        self._transfers: dict[str, ActiveTransfer] = {}
        self._lock = asyncio.Lock()

    @property
    def total_bandwidth_mbps(self) -> int:
        """Get total bandwidth limit in Mbps."""
        return self._total_bandwidth_bytes_per_sec // 125_000

    @total_bandwidth_mbps.setter
    def total_bandwidth_mbps(self, value: int) -> None:
        """Set total bandwidth limit in Mbps."""
        self._total_bandwidth_bytes_per_sec = value * 125_000

    def calculate_priority(self, transfer: ActiveTransfer) -> float:
        """
        Calculate priority for a transfer.

        Higher priority for:
        - Small files (< 10 MB get bonus)
        - Near-completion transfers (> 80% complete get bonus)

        Returns:
            Priority weight (higher = more bandwidth share)
        """
        priority = 1.0

        # Small file bonus (< 10 MB)
        if transfer.total_bytes < 10 * 1024 * 1024:
            # Scale from 2.0 (0 bytes) to 1.0 (10 MB)
            size_factor = 1.0 - (transfer.total_bytes / (10 * 1024 * 1024))
            priority += size_factor

        # Near-completion bonus (> 80% complete)
        if transfer.progress > 0.8:
            # Scale from 1.0 (80%) to 2.0 (100%)
            completion_factor = (transfer.progress - 0.8) / 0.2
            priority += completion_factor

        return priority

    async def register_transfer(
        self, transfer_id: str, file_path: str, total_bytes: int
    ) -> ActiveTransfer:
        """
        Register a new transfer.

        Args:
            transfer_id: Unique identifier for this transfer
            file_path: Path of file being transferred
            total_bytes: Total size of the file

        Returns:
            The ActiveTransfer object
        """
        async with self._lock:
            transfer = ActiveTransfer(
                transfer_id=transfer_id,
                file_path=file_path,
                total_bytes=total_bytes,
            )
            transfer.priority = self.calculate_priority(transfer)
            self._transfers[transfer_id] = transfer
            logger.debug(
                f"Registered transfer {transfer_id}: {file_path} ({total_bytes} bytes)"
            )
            return transfer

    async def unregister_transfer(self, transfer_id: str) -> None:
        """
        Unregister a completed or cancelled transfer.

        Args:
            transfer_id: The transfer to unregister
        """
        async with self._lock:
            if transfer_id in self._transfers:
                transfer = self._transfers.pop(transfer_id)
                logger.debug(
                    f"Unregistered transfer {transfer_id}: "
                    f"{transfer.bytes_transferred}/{transfer.total_bytes} bytes"
                )

    async def update_progress(self, transfer_id: str, bytes_sent: int) -> None:
        """
        Update transfer progress.

        Args:
            transfer_id: The transfer to update
            bytes_sent: Additional bytes transferred
        """
        async with self._lock:
            if transfer_id in self._transfers:
                transfer = self._transfers[transfer_id]
                transfer.bytes_transferred += bytes_sent
                # Recalculate priority as progress changes
                transfer.priority = self.calculate_priority(transfer)

    async def get_allowed_bytes(
        self, transfer_id: str, interval_seconds: float = 0.1
    ) -> int:
        """
        Get the number of bytes this transfer is allowed to send.

        Args:
            transfer_id: The transfer requesting bandwidth
            interval_seconds: Time interval for this allocation

        Returns:
            Number of bytes allowed for this interval
        """
        async with self._lock:
            if transfer_id not in self._transfers:
                return 0

            transfer = self._transfers[transfer_id]
            num_transfers = len(self._transfers)

            if num_transfers == 0:
                return 0

            # Calculate total priority weight
            total_priority = sum(t.priority for t in self._transfers.values())

            # This transfer's share of bandwidth
            priority_share = transfer.priority / total_priority

            # Bytes allowed this interval based on priority share
            total_bytes_this_interval = (
                self._total_bandwidth_bytes_per_sec * interval_seconds
            )
            allowed = int(total_bytes_this_interval * priority_share)

            # Ensure minimum bandwidth floor
            min_allowed = int(MIN_BANDWIDTH_BYTES_PER_SEC * interval_seconds)
            allowed = max(allowed, min_allowed)

            # Don't exceed remaining bytes
            allowed = min(allowed, transfer.remaining_bytes)

            return allowed

    def get_active_transfer_count(self) -> int:
        """Return number of active transfers."""
        return len(self._transfers)

    def get_transfer_info(self, transfer_id: str) -> ActiveTransfer | None:
        """Get info about a specific transfer."""
        return self._transfers.get(transfer_id)


# Global throttler instance (configured at startup)
_throttler: BandwidthThrottler | None = None


def get_throttler() -> BandwidthThrottler:
    """Get the global throttler instance."""
    global _throttler
    if _throttler is None:
        _throttler = BandwidthThrottler()
    return _throttler


def configure_throttler(bandwidth_mbps: int) -> None:
    """Configure the global throttler bandwidth."""
    global _throttler
    if _throttler is None:
        _throttler = BandwidthThrottler(bandwidth_mbps)
    else:
        _throttler.total_bandwidth_mbps = bandwidth_mbps


async def throttled_iterator(
    transfer_id: str,
    content_iterator: AsyncIterator[bytes],
    throttler: BandwidthThrottler,
    chunk_size: int = 8192,
) -> AsyncIterator[bytes]:
    """
    Wrap a content iterator with throttling.

    Args:
        transfer_id: The transfer ID for this stream
        content_iterator: The original content iterator
        throttler: The bandwidth throttler
        chunk_size: Maximum chunk size to yield

    Yields:
        Throttled chunks of content
    """
    try:
        buffer = b""
        async for chunk in content_iterator:
            buffer += chunk

            while len(buffer) >= chunk_size:
                # Get allowed bytes for this interval
                allowed = await throttler.get_allowed_bytes(transfer_id, 0.1)

                if allowed <= 0:
                    # Wait and try again
                    await asyncio.sleep(0.1)
                    continue

                # Send up to allowed bytes
                send_size = min(len(buffer), allowed, chunk_size)
                to_send = buffer[:send_size]
                buffer = buffer[send_size:]

                await throttler.update_progress(transfer_id, len(to_send))
                yield to_send

                # Small delay to distribute bandwidth more evenly
                await asyncio.sleep(0.01)

        # Send any remaining buffer
        while buffer:
            allowed = await throttler.get_allowed_bytes(transfer_id, 0.1)

            if allowed <= 0:
                await asyncio.sleep(0.1)
                continue

            send_size = min(len(buffer), allowed, chunk_size)
            to_send = buffer[:send_size]
            buffer = buffer[send_size:]

            await throttler.update_progress(transfer_id, len(to_send))
            yield to_send

            if buffer:
                await asyncio.sleep(0.01)

    finally:
        await throttler.unregister_transfer(transfer_id)
