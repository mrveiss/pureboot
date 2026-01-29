"""Tests for SystemSetting model and system settings service."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.db.models import Base, SystemSetting
from src.core.system_settings import (
    get_setting,
    set_setting,
    get_default_boot_backend_id,
    get_file_serving_bandwidth_mbps,
    SETTING_DEFAULT_BOOT_BACKEND_ID,
    SETTING_FILE_SERVING_BANDWIDTH_MBPS,
    DEFAULT_BANDWIDTH_MBPS,
)


# =============================================================================
# Sync Model Tests
# =============================================================================


@pytest.fixture
def engine():
    """Create in-memory SQLite engine for sync tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create database session for sync tests."""
    with Session(engine) as session:
        yield session


class TestSystemSettingModel:
    """Test SystemSetting model."""

    def test_create_setting(self, session):
        """Create SystemSetting with key and value."""
        setting = SystemSetting(key="test_key", value="test_value")
        session.add(setting)
        session.commit()

        assert setting.key == "test_key"
        assert setting.value == "test_value"
        assert setting.updated_at is not None

    def test_create_setting_with_null_value(self, session):
        """SystemSetting value can be null."""
        setting = SystemSetting(key="null_key", value=None)
        session.add(setting)
        session.commit()

        assert setting.key == "null_key"
        assert setting.value is None

    def test_key_is_primary_key(self, session):
        """Key serves as primary key (unique)."""
        setting1 = SystemSetting(key="unique_key", value="value1")
        session.add(setting1)
        session.commit()

        setting2 = SystemSetting(key="unique_key", value="value2")
        session.add(setting2)

        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_update_setting_value(self, session):
        """SystemSetting value can be updated."""
        setting = SystemSetting(key="update_key", value="initial")
        session.add(setting)
        session.commit()

        setting.value = "updated"
        session.commit()

        refreshed = session.get(SystemSetting, "update_key")
        assert refreshed.value == "updated"


# =============================================================================
# Async Service Tests
# =============================================================================


@pytest.fixture
async def async_engine():
    """Create async in-memory SQLite engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine):
    """Create async database session."""
    async_session_maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_maker() as session:
        yield session


class TestGetSetting:
    """Test get_setting function."""

    @pytest.mark.asyncio
    async def test_get_setting_not_found(self, async_session):
        """get_setting returns None for non-existent key."""
        result = await get_setting(async_session, "nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_setting_returns_value(self, async_session):
        """get_setting returns the stored value."""
        setting = SystemSetting(key="test_key", value="test_value")
        async_session.add(setting)
        await async_session.flush()

        result = await get_setting(async_session, "test_key")
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_setting_with_null_value(self, async_session):
        """get_setting returns None for null value."""
        setting = SystemSetting(key="null_key", value=None)
        async_session.add(setting)
        await async_session.flush()

        result = await get_setting(async_session, "null_key")
        assert result is None


class TestSetSetting:
    """Test set_setting function."""

    @pytest.mark.asyncio
    async def test_set_setting_creates_new(self, async_session):
        """set_setting creates new setting when key doesn't exist."""
        await set_setting(async_session, "new_key", "new_value")

        result = await get_setting(async_session, "new_key")
        assert result == "new_value"

    @pytest.mark.asyncio
    async def test_set_setting_updates_existing(self, async_session):
        """set_setting updates existing setting."""
        setting = SystemSetting(key="existing_key", value="old_value")
        async_session.add(setting)
        await async_session.flush()

        await set_setting(async_session, "existing_key", "new_value")

        result = await get_setting(async_session, "existing_key")
        assert result == "new_value"

    @pytest.mark.asyncio
    async def test_set_setting_with_null(self, async_session):
        """set_setting can set value to null."""
        await set_setting(async_session, "null_test", "initial")
        await set_setting(async_session, "null_test", None)

        result = await get_setting(async_session, "null_test")
        assert result is None


class TestGetDefaultBootBackendId:
    """Test get_default_boot_backend_id function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_set(self, async_session):
        """Returns None when default boot backend is not configured."""
        result = await get_default_boot_backend_id(async_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_configured_backend_id(self, async_session):
        """Returns the configured boot backend ID."""
        setting = SystemSetting(
            key=SETTING_DEFAULT_BOOT_BACKEND_ID, value="backend-uuid-123"
        )
        async_session.add(setting)
        await async_session.flush()

        result = await get_default_boot_backend_id(async_session)
        assert result == "backend-uuid-123"


class TestGetFileServingBandwidthMbps:
    """Test get_file_serving_bandwidth_mbps function."""

    @pytest.mark.asyncio
    async def test_returns_default_when_not_set(self, async_session):
        """Returns default bandwidth when not configured."""
        result = await get_file_serving_bandwidth_mbps(async_session)
        assert result == DEFAULT_BANDWIDTH_MBPS

    @pytest.mark.asyncio
    async def test_returns_configured_bandwidth(self, async_session):
        """Returns configured bandwidth value."""
        setting = SystemSetting(
            key=SETTING_FILE_SERVING_BANDWIDTH_MBPS, value="500"
        )
        async_session.add(setting)
        await async_session.flush()

        result = await get_file_serving_bandwidth_mbps(async_session)
        assert result == 500

    @pytest.mark.asyncio
    async def test_returns_default_for_invalid_value(self, async_session):
        """Returns default when stored value is not a valid integer."""
        setting = SystemSetting(
            key=SETTING_FILE_SERVING_BANDWIDTH_MBPS, value="not_a_number"
        )
        async_session.add(setting)
        await async_session.flush()

        result = await get_file_serving_bandwidth_mbps(async_session)
        assert result == DEFAULT_BANDWIDTH_MBPS

    @pytest.mark.asyncio
    async def test_returns_default_for_empty_value(self, async_session):
        """Returns default when stored value is empty string."""
        setting = SystemSetting(
            key=SETTING_FILE_SERVING_BANDWIDTH_MBPS, value=""
        )
        async_session.add(setting)
        await async_session.flush()

        result = await get_file_serving_bandwidth_mbps(async_session)
        assert result == DEFAULT_BANDWIDTH_MBPS
