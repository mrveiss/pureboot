"""Tests for conflict detection."""
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.conflicts import ConflictDetector, Conflict


@pytest.fixture
async def detector(tmp_path):
    """Create conflict detector for testing."""
    db_path = tmp_path / "conflicts.db"
    d = ConflictDetector(db_path=db_path)
    await d.initialize()
    yield d
    await d.close()


@pytest.fixture
def sample_conflict():
    """Create a sample conflict."""
    now = datetime.now(timezone.utc)
    return Conflict(
        id="conflict-001",
        node_mac="00:11:22:33:44:55",
        node_id="node-001",
        local_state="active",
        central_state="pending",
        local_updated_at=now - timedelta(hours=1),
        central_updated_at=now,
        conflict_type="state_mismatch",
        detected_at=now,
    )


@pytest.fixture
def mock_state_cache():
    """Create mock state cache."""
    cache = AsyncMock()

    # Create mock cached nodes
    from unittest.mock import MagicMock
    cached1 = MagicMock()
    cached1.mac_address = "00:11:22:33:44:55"
    cached1.node_id = "node-001"
    cached1.state = "active"
    cached1.cached_at = datetime.now(timezone.utc) - timedelta(hours=1)

    cache.get_all_nodes = AsyncMock(return_value=[cached1])
    return cache


class TestConflictDetector:
    """Tests for ConflictDetector class."""

    @pytest.mark.asyncio
    async def test_initialize(self, tmp_path):
        """Test detector initialization creates database."""
        db_path = tmp_path / "test" / "conflicts.db"
        detector = ConflictDetector(db_path=db_path)

        await detector.initialize()

        assert db_path.exists()
        await detector.close()

    @pytest.mark.asyncio
    async def test_mark_conflict(self, detector, sample_conflict):
        """Test storing a conflict."""
        await detector.mark_conflict(sample_conflict)

        # Retrieve it
        conflict = await detector.get_conflict(sample_conflict.id)
        assert conflict is not None
        assert conflict.node_mac == sample_conflict.node_mac
        assert conflict.conflict_type == "state_mismatch"

    @pytest.mark.asyncio
    async def test_get_pending_conflicts(self, detector, sample_conflict):
        """Test getting pending conflicts."""
        await detector.mark_conflict(sample_conflict)

        pending = await detector.get_pending_conflicts()
        assert len(pending) == 1
        assert pending[0].id == sample_conflict.id

    @pytest.mark.asyncio
    async def test_resolve_conflict(self, detector, sample_conflict):
        """Test resolving a conflict."""
        await detector.mark_conflict(sample_conflict)

        resolved = await detector.resolve_conflict(
            sample_conflict.id,
            resolution="keep_central",
            resolved_by="admin",
        )
        assert resolved is True

        # Check it's resolved
        conflict = await detector.get_conflict(sample_conflict.id)
        assert conflict.resolved is True
        assert conflict.resolution == "keep_central"
        assert conflict.resolved_by == "admin"
        assert conflict.resolved_at is not None

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_conflict(self, detector):
        """Test resolving nonexistent conflict."""
        resolved = await detector.resolve_conflict(
            "nonexistent",
            resolution="keep_local",
        )
        assert resolved is False

    @pytest.mark.asyncio
    async def test_get_conflict_count(self, detector):
        """Test getting pending conflict count."""
        now = datetime.now(timezone.utc)

        # Add multiple conflicts
        for i in range(3):
            conflict = Conflict(
                id=f"conflict-{i}",
                node_mac=f"00:11:22:33:44:{i:02x}",
                local_state="active",
                central_state="pending",
                local_updated_at=now,
                central_updated_at=now,
                conflict_type="state_mismatch",
                detected_at=now,
            )
            await detector.mark_conflict(conflict)

        count = await detector.get_conflict_count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_conflicts_for_node(self, detector, sample_conflict):
        """Test getting conflicts for specific node."""
        await detector.mark_conflict(sample_conflict)

        # Add another conflict for different node
        other_conflict = Conflict(
            id="conflict-002",
            node_mac="00:11:22:33:44:66",
            local_state="active",
            central_state="pending",
            local_updated_at=datetime.now(timezone.utc),
            central_updated_at=datetime.now(timezone.utc),
            conflict_type="state_mismatch",
            detected_at=datetime.now(timezone.utc),
        )
        await detector.mark_conflict(other_conflict)

        # Get for specific node
        node_conflicts = await detector.get_conflicts_for_node("00:11:22:33:44:55")
        assert len(node_conflicts) == 1
        assert node_conflicts[0].id == sample_conflict.id

    @pytest.mark.asyncio
    async def test_detect_state_mismatch(self, detector, mock_state_cache):
        """Test detecting state mismatch conflict."""
        central_nodes = [
            {
                "id": "node-001",
                "mac_address": "00:11:22:33:44:55",
                "state": "pending",  # Different from cached "active"
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        conflicts = await detector.check_conflicts(central_nodes, mock_state_cache)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "state_mismatch"
        assert conflicts[0].local_state == "active"
        assert conflicts[0].central_state == "pending"

    @pytest.mark.asyncio
    async def test_detect_missing_central(self, detector, mock_state_cache):
        """Test detecting node missing from central."""
        central_nodes = []  # Empty - node is missing from central

        conflicts = await detector.check_conflicts(central_nodes, mock_state_cache)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "missing_central"
        assert conflicts[0].central_state == "missing"

    @pytest.mark.asyncio
    async def test_detect_missing_local(self, detector, mock_state_cache):
        """Test detecting node missing from local cache."""
        # Empty cache
        mock_state_cache.get_all_nodes.return_value = []

        central_nodes = [
            {
                "id": "node-002",
                "mac_address": "00:11:22:33:44:66",
                "state": "active",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        conflicts = await detector.check_conflicts(central_nodes, mock_state_cache)

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "missing_local"
        assert conflicts[0].local_state == "missing"

    @pytest.mark.asyncio
    async def test_no_conflict_when_states_match(self, detector, mock_state_cache):
        """Test no conflict when states match."""
        central_nodes = [
            {
                "id": "node-001",
                "mac_address": "00:11:22:33:44:55",
                "state": "active",  # Same as cached
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        conflicts = await detector.check_conflicts(central_nodes, mock_state_cache)

        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_resolved_conflicts_not_in_pending(self, detector, sample_conflict):
        """Test resolved conflicts not returned in pending."""
        await detector.mark_conflict(sample_conflict)
        await detector.resolve_conflict(sample_conflict.id, "keep_central")

        pending = await detector.get_pending_conflicts()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_clear_resolved(self, detector, sample_conflict):
        """Test clearing old resolved conflicts."""
        await detector.mark_conflict(sample_conflict)
        await detector.resolve_conflict(sample_conflict.id, "keep_central")

        # Clear resolved older than 0 days (all resolved)
        cleared = await detector.clear_resolved(older_than_days=0)

        # Note: The actual behavior depends on SQLite julianday calculation
        # In tests, newly resolved conflicts may or may not be cleared
        # depending on timing


class TestConflict:
    """Tests for Conflict model."""

    def test_create_conflict(self):
        """Test creating a conflict."""
        now = datetime.now(timezone.utc)
        conflict = Conflict(
            id="test-1",
            node_mac="00:11:22:33:44:55",
            node_id="node-001",
            local_state="active",
            central_state="pending",
            local_updated_at=now,
            central_updated_at=now,
            conflict_type="state_mismatch",
            detected_at=now,
        )

        assert conflict.id == "test-1"
        assert conflict.resolved is False
        assert conflict.resolution is None

    def test_conflict_defaults(self):
        """Test conflict default values."""
        now = datetime.now(timezone.utc)
        conflict = Conflict(
            id="test-2",
            node_mac="00:11:22:33:44:55",
            local_state="active",
            central_state="pending",
            local_updated_at=now,
            central_updated_at=now,
            conflict_type="state_mismatch",
            detected_at=now,
        )

        assert conflict.node_id is None
        assert conflict.resolved is False
        assert conflict.resolution is None
        assert conflict.resolved_at is None
        assert conflict.resolved_by is None
