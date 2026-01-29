"""Tests for priority-based bandwidth throttler."""
import asyncio
import pytest
import time
from unittest.mock import AsyncMock, patch

from src.core.bandwidth_throttler import (
    ActiveTransfer,
    BandwidthThrottler,
    MIN_BANDWIDTH_BYTES_PER_SEC,
    MIN_BANDWIDTH_MBPS,
    get_throttler,
    configure_throttler,
    throttled_iterator,
)


class TestActiveTransfer:
    """Tests for the ActiveTransfer dataclass."""

    def test_active_transfer_defaults(self):
        """ActiveTransfer has correct default values."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
        )
        assert transfer.transfer_id == "test-1"
        assert transfer.file_path == "/path/to/file"
        assert transfer.total_bytes == 1000
        assert transfer.bytes_transferred == 0
        assert transfer.started_at > 0
        assert transfer.priority == 1.0

    def test_progress_zero_when_nothing_transferred(self):
        """Progress is 0.0 when no bytes transferred."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
        )
        assert transfer.progress == 0.0

    def test_progress_halfway(self):
        """Progress is 0.5 when half transferred."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
            bytes_transferred=500,
        )
        assert transfer.progress == 0.5

    def test_progress_complete(self):
        """Progress is 1.0 when fully transferred."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
            bytes_transferred=1000,
        )
        assert transfer.progress == 1.0

    def test_progress_capped_at_one(self):
        """Progress is capped at 1.0 even if bytes_transferred exceeds total."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
            bytes_transferred=1500,
        )
        assert transfer.progress == 1.0

    def test_progress_zero_bytes_file(self):
        """Progress is 0.0 for zero-byte file."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=0,
        )
        assert transfer.progress == 0.0

    def test_remaining_bytes_full(self):
        """Remaining bytes is total when nothing transferred."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
        )
        assert transfer.remaining_bytes == 1000

    def test_remaining_bytes_partial(self):
        """Remaining bytes is correct during transfer."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
            bytes_transferred=300,
        )
        assert transfer.remaining_bytes == 700

    def test_remaining_bytes_complete(self):
        """Remaining bytes is 0 when complete."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
            bytes_transferred=1000,
        )
        assert transfer.remaining_bytes == 0

    def test_remaining_bytes_not_negative(self):
        """Remaining bytes is not negative even if over-transferred."""
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
            bytes_transferred=1500,
        )
        assert transfer.remaining_bytes == 0


class TestBandwidthThrottler:
    """Tests for the BandwidthThrottler class."""

    def test_default_bandwidth(self):
        """Default bandwidth is 1000 Mbps."""
        throttler = BandwidthThrottler()
        assert throttler.total_bandwidth_mbps == 1000

    def test_custom_bandwidth(self):
        """Can set custom bandwidth."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=500)
        assert throttler.total_bandwidth_mbps == 500

    def test_bandwidth_property_setter(self):
        """Can change bandwidth via property."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=100)
        throttler.total_bandwidth_mbps = 200
        assert throttler.total_bandwidth_mbps == 200

    def test_calculate_priority_baseline(self):
        """Large files with no progress have priority 1.0."""
        throttler = BandwidthThrottler()
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=100 * 1024 * 1024,  # 100 MB
            bytes_transferred=0,
        )
        priority = throttler.calculate_priority(transfer)
        assert priority == 1.0

    def test_calculate_priority_small_file_bonus(self):
        """Small files (< 10 MB) get higher priority."""
        throttler = BandwidthThrottler()

        # 1 MB file should get higher priority
        small_transfer = ActiveTransfer(
            transfer_id="small",
            file_path="/path/to/small",
            total_bytes=1 * 1024 * 1024,  # 1 MB
        )
        small_priority = throttler.calculate_priority(small_transfer)

        # 100 MB file should get base priority
        large_transfer = ActiveTransfer(
            transfer_id="large",
            file_path="/path/to/large",
            total_bytes=100 * 1024 * 1024,  # 100 MB
        )
        large_priority = throttler.calculate_priority(large_transfer)

        assert small_priority > large_priority
        assert small_priority > 1.0
        assert large_priority == 1.0

    def test_calculate_priority_near_completion_bonus(self):
        """Near-completion transfers (> 80%) get higher priority."""
        throttler = BandwidthThrottler()

        # 90% complete should get higher priority
        near_complete = ActiveTransfer(
            transfer_id="near",
            file_path="/path/to/near",
            total_bytes=100 * 1024 * 1024,
            bytes_transferred=90 * 1024 * 1024,
        )
        near_priority = throttler.calculate_priority(near_complete)

        # 50% complete should get base priority
        halfway = ActiveTransfer(
            transfer_id="half",
            file_path="/path/to/half",
            total_bytes=100 * 1024 * 1024,
            bytes_transferred=50 * 1024 * 1024,
        )
        halfway_priority = throttler.calculate_priority(halfway)

        assert near_priority > halfway_priority
        assert near_priority > 1.0
        assert halfway_priority == 1.0

    def test_calculate_priority_combined_bonus(self):
        """Small files near completion get both bonuses."""
        throttler = BandwidthThrottler()

        # Small file at 90% complete
        combined = ActiveTransfer(
            transfer_id="combined",
            file_path="/path/to/combined",
            total_bytes=1 * 1024 * 1024,  # 1 MB
            bytes_transferred=int(0.9 * 1024 * 1024),  # 90%
        )
        combined_priority = throttler.calculate_priority(combined)

        # Should have both size and completion bonuses
        assert combined_priority > 2.0

    @pytest.mark.asyncio
    async def test_register_transfer(self):
        """Can register a new transfer."""
        throttler = BandwidthThrottler()
        transfer = await throttler.register_transfer(
            transfer_id="test-1",
            file_path="/path/to/file",
            total_bytes=1000,
        )
        assert transfer.transfer_id == "test-1"
        assert transfer.file_path == "/path/to/file"
        assert transfer.total_bytes == 1000
        assert throttler.get_active_transfer_count() == 1

    @pytest.mark.asyncio
    async def test_register_multiple_transfers(self):
        """Can register multiple transfers."""
        throttler = BandwidthThrottler()
        await throttler.register_transfer("t1", "/file1", 1000)
        await throttler.register_transfer("t2", "/file2", 2000)
        await throttler.register_transfer("t3", "/file3", 3000)
        assert throttler.get_active_transfer_count() == 3

    @pytest.mark.asyncio
    async def test_unregister_transfer(self):
        """Can unregister a transfer."""
        throttler = BandwidthThrottler()
        await throttler.register_transfer("test-1", "/file", 1000)
        assert throttler.get_active_transfer_count() == 1

        await throttler.unregister_transfer("test-1")
        assert throttler.get_active_transfer_count() == 0

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_transfer(self):
        """Unregistering nonexistent transfer doesn't raise."""
        throttler = BandwidthThrottler()
        await throttler.unregister_transfer("nonexistent")
        # Should not raise

    @pytest.mark.asyncio
    async def test_update_progress(self):
        """Can update transfer progress."""
        throttler = BandwidthThrottler()
        await throttler.register_transfer("test-1", "/file", 1000)

        await throttler.update_progress("test-1", 500)

        transfer = throttler.get_transfer_info("test-1")
        assert transfer.bytes_transferred == 500

    @pytest.mark.asyncio
    async def test_update_progress_incremental(self):
        """Progress updates are incremental."""
        throttler = BandwidthThrottler()
        await throttler.register_transfer("test-1", "/file", 1000)

        await throttler.update_progress("test-1", 200)
        await throttler.update_progress("test-1", 300)

        transfer = throttler.get_transfer_info("test-1")
        assert transfer.bytes_transferred == 500

    @pytest.mark.asyncio
    async def test_update_progress_recalculates_priority(self):
        """Updating progress recalculates priority."""
        throttler = BandwidthThrottler()
        await throttler.register_transfer("test-1", "/file", 100 * 1024 * 1024)

        transfer_before = throttler.get_transfer_info("test-1")
        priority_before = transfer_before.priority

        # Update to 90% complete
        await throttler.update_progress("test-1", 90 * 1024 * 1024)

        transfer_after = throttler.get_transfer_info("test-1")
        priority_after = transfer_after.priority

        # Priority should increase due to near-completion bonus
        assert priority_after > priority_before

    @pytest.mark.asyncio
    async def test_update_progress_nonexistent_transfer(self):
        """Updating nonexistent transfer doesn't raise."""
        throttler = BandwidthThrottler()
        await throttler.update_progress("nonexistent", 500)
        # Should not raise

    @pytest.mark.asyncio
    async def test_get_allowed_bytes_single_transfer(self):
        """Single transfer gets full bandwidth minus min floor."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=100)  # 100 Mbps = 12,500,000 bytes/sec
        await throttler.register_transfer("test-1", "/file", 100 * 1024 * 1024)

        allowed = await throttler.get_allowed_bytes("test-1", interval_seconds=1.0)

        # Should get approximately 100 Mbps = 12,500,000 bytes/sec
        expected = 100 * 125_000  # 12,500,000 bytes/sec
        assert allowed == expected

    @pytest.mark.asyncio
    async def test_get_allowed_bytes_fair_sharing(self):
        """Multiple equal-priority transfers share bandwidth fairly."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=100)

        # Register two equal-priority transfers (large files, no progress)
        await throttler.register_transfer("t1", "/file1", 100 * 1024 * 1024)
        await throttler.register_transfer("t2", "/file2", 100 * 1024 * 1024)

        allowed_1 = await throttler.get_allowed_bytes("t1", interval_seconds=1.0)
        allowed_2 = await throttler.get_allowed_bytes("t2", interval_seconds=1.0)

        # Both should get approximately equal share (50 Mbps each)
        expected_each = 50 * 125_000  # 6,250,000 bytes/sec
        assert allowed_1 == expected_each
        assert allowed_2 == expected_each

    @pytest.mark.asyncio
    async def test_get_allowed_bytes_priority_weighted(self):
        """Higher priority transfers get more bandwidth."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=100)

        # Small file gets higher priority
        await throttler.register_transfer("small", "/small", 1 * 1024 * 1024)
        # Large file gets normal priority
        await throttler.register_transfer("large", "/large", 100 * 1024 * 1024)

        allowed_small = await throttler.get_allowed_bytes("small", interval_seconds=1.0)
        allowed_large = await throttler.get_allowed_bytes("large", interval_seconds=1.0)

        # Small file should get more bandwidth due to higher priority
        assert allowed_small > allowed_large

    @pytest.mark.asyncio
    async def test_get_allowed_bytes_minimum_floor(self):
        """Transfer gets at least minimum bandwidth."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=10)

        # Register many transfers to dilute bandwidth
        for i in range(100):
            await throttler.register_transfer(f"t{i}", f"/file{i}", 100 * 1024 * 1024)

        allowed = await throttler.get_allowed_bytes("t0", interval_seconds=1.0)

        # Should get at least minimum bandwidth floor
        min_allowed = int(MIN_BANDWIDTH_BYTES_PER_SEC * 1.0)
        assert allowed >= min_allowed

    @pytest.mark.asyncio
    async def test_get_allowed_bytes_capped_by_remaining(self):
        """Allowed bytes is capped by remaining bytes."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=1000)
        await throttler.register_transfer("test-1", "/file", 1000)

        # Update to nearly complete
        await throttler.update_progress("test-1", 990)

        allowed = await throttler.get_allowed_bytes("test-1", interval_seconds=1.0)

        # Should be capped at remaining 10 bytes
        assert allowed == 10

    @pytest.mark.asyncio
    async def test_get_allowed_bytes_nonexistent_transfer(self):
        """Nonexistent transfer gets 0 bytes."""
        throttler = BandwidthThrottler()
        allowed = await throttler.get_allowed_bytes("nonexistent", interval_seconds=1.0)
        assert allowed == 0

    @pytest.mark.asyncio
    async def test_get_allowed_bytes_short_interval(self):
        """Short intervals return proportionally less bytes."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=100)
        await throttler.register_transfer("test-1", "/file", 100 * 1024 * 1024)

        allowed_1s = await throttler.get_allowed_bytes("test-1", interval_seconds=1.0)
        allowed_01s = await throttler.get_allowed_bytes("test-1", interval_seconds=0.1)

        # 0.1 second interval should get 1/10 the bytes
        assert allowed_01s == allowed_1s // 10

    def test_get_active_transfer_count_empty(self):
        """Empty throttler has 0 active transfers."""
        throttler = BandwidthThrottler()
        assert throttler.get_active_transfer_count() == 0

    def test_get_transfer_info_exists(self):
        """Can get info for existing transfer."""
        throttler = BandwidthThrottler()
        # Manually add transfer for sync test
        transfer = ActiveTransfer(
            transfer_id="test-1",
            file_path="/file",
            total_bytes=1000,
        )
        throttler._transfers["test-1"] = transfer

        info = throttler.get_transfer_info("test-1")
        assert info is not None
        assert info.transfer_id == "test-1"

    def test_get_transfer_info_not_exists(self):
        """Returns None for nonexistent transfer."""
        throttler = BandwidthThrottler()
        info = throttler.get_transfer_info("nonexistent")
        assert info is None


class TestGlobalThrottler:
    """Tests for global throttler functions."""

    def test_get_throttler_creates_default(self):
        """get_throttler creates default throttler if none exists."""
        # Reset global state
        import src.core.bandwidth_throttler as module
        module._throttler = None

        throttler = get_throttler()
        assert throttler is not None
        assert throttler.total_bandwidth_mbps == 1000

    def test_get_throttler_returns_same_instance(self):
        """get_throttler returns same instance on repeated calls."""
        # Reset global state
        import src.core.bandwidth_throttler as module
        module._throttler = None

        throttler1 = get_throttler()
        throttler2 = get_throttler()
        assert throttler1 is throttler2

    def test_configure_throttler_new_instance(self):
        """configure_throttler creates new instance with bandwidth."""
        import src.core.bandwidth_throttler as module
        module._throttler = None

        configure_throttler(500)
        throttler = get_throttler()
        assert throttler.total_bandwidth_mbps == 500

    def test_configure_throttler_updates_existing(self):
        """configure_throttler updates existing instance bandwidth."""
        import src.core.bandwidth_throttler as module
        module._throttler = None

        configure_throttler(500)
        configure_throttler(800)
        throttler = get_throttler()
        assert throttler.total_bandwidth_mbps == 800


class TestThrottledIterator:
    """Tests for throttled_iterator function."""

    @pytest.mark.asyncio
    async def test_throttled_iterator_yields_all_content(self):
        """Throttled iterator yields all content."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=1000)
        await throttler.register_transfer("test-1", "/file", 100)

        async def content_gen():
            yield b"hello"
            yield b"world"

        chunks = []
        async for chunk in throttled_iterator("test-1", content_gen(), throttler, chunk_size=10):
            chunks.append(chunk)

        # All content should be yielded
        total_content = b"".join(chunks)
        assert total_content == b"helloworld"

    @pytest.mark.asyncio
    async def test_throttled_iterator_unregisters_on_complete(self):
        """Throttled iterator unregisters transfer when complete."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=1000)
        await throttler.register_transfer("test-1", "/file", 100)

        async def content_gen():
            yield b"hello"

        async for _ in throttled_iterator("test-1", content_gen(), throttler):
            pass

        # Transfer should be unregistered
        assert throttler.get_transfer_info("test-1") is None

    @pytest.mark.asyncio
    async def test_throttled_iterator_unregisters_on_error(self):
        """Throttled iterator unregisters transfer on error."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=1000)
        await throttler.register_transfer("test-1", "/file", 100)

        async def failing_gen():
            yield b"hello"
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            async for _ in throttled_iterator("test-1", failing_gen(), throttler):
                pass

        # Transfer should still be unregistered (finally block)
        assert throttler.get_transfer_info("test-1") is None

    @pytest.mark.asyncio
    async def test_throttled_iterator_respects_chunk_size(self):
        """Throttled iterator respects chunk_size parameter."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=1000)
        await throttler.register_transfer("test-1", "/file", 100)

        async def content_gen():
            yield b"a" * 100  # 100 bytes

        chunks = []
        async for chunk in throttled_iterator("test-1", content_gen(), throttler, chunk_size=10):
            chunks.append(chunk)
            assert len(chunk) <= 10  # Each chunk should be at most chunk_size

    @pytest.mark.asyncio
    async def test_throttled_iterator_updates_progress(self):
        """Throttled iterator updates transfer progress."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=1000)
        await throttler.register_transfer("test-1", "/file", 100)

        async def content_gen():
            yield b"a" * 50

        progress_values = []
        async for _ in throttled_iterator("test-1", content_gen(), throttler, chunk_size=100):
            transfer = throttler.get_transfer_info("test-1")
            if transfer:
                progress_values.append(transfer.bytes_transferred)

        # Progress should have been updated
        assert len(progress_values) > 0
        assert max(progress_values) == 50


class TestConcurrentTransfers:
    """Tests for concurrent transfer scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_register_unregister(self):
        """Concurrent register/unregister operations are safe."""
        throttler = BandwidthThrottler()

        async def register_and_unregister(n):
            await throttler.register_transfer(f"t{n}", f"/file{n}", 1000)
            await asyncio.sleep(0.01)
            await throttler.unregister_transfer(f"t{n}")

        # Run many concurrent operations
        tasks = [register_and_unregister(i) for i in range(50)]
        await asyncio.gather(*tasks)

        # Should end with 0 transfers
        assert throttler.get_active_transfer_count() == 0

    @pytest.mark.asyncio
    async def test_concurrent_progress_updates(self):
        """Concurrent progress updates are safe."""
        throttler = BandwidthThrottler()
        await throttler.register_transfer("test-1", "/file", 10000)

        async def update_progress(bytes_to_add):
            await throttler.update_progress("test-1", bytes_to_add)

        # Run many concurrent updates
        tasks = [update_progress(100) for _ in range(50)]
        await asyncio.gather(*tasks)

        transfer = throttler.get_transfer_info("test-1")
        assert transfer.bytes_transferred == 5000  # 50 * 100

    @pytest.mark.asyncio
    async def test_concurrent_get_allowed_bytes(self):
        """Concurrent get_allowed_bytes calls are safe."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=100)

        # Register multiple transfers
        for i in range(10):
            await throttler.register_transfer(f"t{i}", f"/file{i}", 100 * 1024 * 1024)

        async def get_bytes(transfer_id):
            return await throttler.get_allowed_bytes(transfer_id, 0.1)

        # Get allowed bytes concurrently for all transfers
        tasks = [get_bytes(f"t{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should get some bytes
        assert all(r > 0 for r in results)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_min_bandwidth_constants(self):
        """Minimum bandwidth constants are correctly defined."""
        assert MIN_BANDWIDTH_MBPS == 1
        assert MIN_BANDWIDTH_BYTES_PER_SEC == 125_000  # 1 Mbps = 125,000 bytes/sec

    @pytest.mark.asyncio
    async def test_zero_byte_transfer(self):
        """Zero-byte transfer is handled correctly."""
        throttler = BandwidthThrottler()
        await throttler.register_transfer("test-1", "/empty", 0)

        allowed = await throttler.get_allowed_bytes("test-1", 1.0)
        assert allowed == 0  # Can't send more than remaining (0 bytes)

    @pytest.mark.asyncio
    async def test_very_large_transfer(self):
        """Very large transfer is handled correctly."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=100)
        await throttler.register_transfer("test-1", "/huge", 1000 * 1024 * 1024 * 1024)  # 1 TB

        allowed = await throttler.get_allowed_bytes("test-1", 1.0)

        # Should get full bandwidth for 1 second
        expected = 100 * 125_000  # 12,500,000 bytes
        assert allowed == expected

    @pytest.mark.asyncio
    async def test_bandwidth_change_affects_allocation(self):
        """Changing bandwidth affects subsequent allocations."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=100)
        await throttler.register_transfer("test-1", "/file", 100 * 1024 * 1024)

        allowed_before = await throttler.get_allowed_bytes("test-1", 1.0)

        throttler.total_bandwidth_mbps = 200

        allowed_after = await throttler.get_allowed_bytes("test-1", 1.0)

        assert allowed_after == allowed_before * 2

    @pytest.mark.asyncio
    async def test_small_interval_rounding(self):
        """Very small intervals handle rounding correctly."""
        throttler = BandwidthThrottler(total_bandwidth_mbps=1)  # 1 Mbps = 125,000 bytes/sec
        await throttler.register_transfer("test-1", "/file", 100 * 1024 * 1024)

        # Very small interval - 0.001 seconds
        allowed = await throttler.get_allowed_bytes("test-1", 0.001)

        # 125,000 bytes/sec * 0.001 sec = 125 bytes
        assert allowed == 125

    def test_priority_calculation_boundary_cases(self):
        """Priority calculation handles boundary cases."""
        throttler = BandwidthThrottler()

        # Exactly 10 MB (boundary for small file bonus)
        transfer_10mb = ActiveTransfer(
            transfer_id="t1",
            file_path="/file",
            total_bytes=10 * 1024 * 1024,
        )
        priority_10mb = throttler.calculate_priority(transfer_10mb)
        assert priority_10mb == 1.0  # No bonus at exactly 10 MB

        # Exactly 80% complete (boundary for near-completion bonus)
        transfer_80pct = ActiveTransfer(
            transfer_id="t2",
            file_path="/file",
            total_bytes=100 * 1024 * 1024,
            bytes_transferred=80 * 1024 * 1024,
        )
        priority_80pct = throttler.calculate_priority(transfer_80pct)
        assert priority_80pct == 1.0  # No bonus at exactly 80%
