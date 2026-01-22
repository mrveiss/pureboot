"""Tests for event service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.event_service import EventService


class TestEventService:
    """Test EventService."""

    @pytest.mark.asyncio
    async def test_log_event_creates_event(self):
        """log_event creates NodeEvent in database."""
        db = AsyncMock()
        node = MagicMock()
        node.id = "node-123"
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        event = await EventService.log_event(
            db=db,
            node=node,
            event_type="boot_started",
            status="success",
            message="Node booted",
        )

        assert event.node_id == "node-123"
        assert event.event_type == "boot_started"
        assert event.status == "success"
        assert event.message == "Node booted"
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_with_metadata(self):
        """log_event serializes metadata to JSON."""
        db = AsyncMock()
        node = MagicMock()
        node.id = "node-123"
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        event = await EventService.log_event(
            db=db,
            node=node,
            event_type="first_boot",
            metadata={"os_version": "Ubuntu 24.04", "kernel": "6.8.0"},
        )

        assert event.metadata_json is not None
        assert "Ubuntu 24.04" in event.metadata_json

    @pytest.mark.asyncio
    async def test_log_event_with_progress(self):
        """log_event stores progress percentage."""
        db = AsyncMock()
        node = MagicMock()
        node.id = "node-123"
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        event = await EventService.log_event(
            db=db,
            node=node,
            event_type="install_progress",
            progress=75,
        )

        assert event.progress == 75
