"""System settings service."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import SystemSetting

# Known setting keys
SETTING_DEFAULT_BOOT_BACKEND_ID = "default_boot_backend_id"
SETTING_FILE_SERVING_BANDWIDTH_MBPS = "file_serving_bandwidth_mbps"

# Defaults
DEFAULT_BANDWIDTH_MBPS = 1000


async def get_setting(db: AsyncSession, key: str) -> str | None:
    """Get a system setting value."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


async def set_setting(db: AsyncSession, key: str, value: str | None) -> None:
    """Set a system setting value."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = value
    else:
        setting = SystemSetting(key=key, value=value)
        db.add(setting)

    await db.flush()


async def get_default_boot_backend_id(db: AsyncSession) -> str | None:
    """Get the default boot backend ID."""
    return await get_setting(db, SETTING_DEFAULT_BOOT_BACKEND_ID)


async def get_file_serving_bandwidth_mbps(db: AsyncSession) -> int:
    """Get the file serving bandwidth limit in Mbps."""
    value = await get_setting(db, SETTING_FILE_SERVING_BANDWIDTH_MBPS)
    if value:
        try:
            return int(value)
        except ValueError:
            pass
    return DEFAULT_BANDWIDTH_MBPS
