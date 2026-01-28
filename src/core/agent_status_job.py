"""Periodic job to update site agent statuses based on heartbeats.

This job runs every minute to:
- Mark agents as 'online' if heartbeat was within 2 intervals
- Mark agents as 'degraded' if heartbeat was 2-5 intervals ago
- Mark agents as 'offline' if no heartbeat for 5+ intervals
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import async_session_factory
from src.db.models import DeviceGroup

logger = logging.getLogger(__name__)

# Default heartbeat interval in seconds
HEARTBEAT_INTERVAL = 60

# Status thresholds (in heartbeat intervals)
DEGRADED_THRESHOLD = 2  # Mark degraded after 2 missed heartbeats
OFFLINE_THRESHOLD = 5   # Mark offline after 5 missed heartbeats


async def update_agent_statuses():
    """Update agent statuses for all sites based on heartbeat timestamps.

    This function should be called periodically (e.g., every minute) by the scheduler.
    """
    if not async_session_factory:
        logger.warning("Database session factory not available")
        return

    async with async_session_factory() as db:
        # Get all sites with agents
        result = await db.execute(
            select(DeviceGroup).where(
                DeviceGroup.is_site == True,
                DeviceGroup.agent_last_seen.isnot(None),
            )
        )
        sites = result.scalars().all()

        now = datetime.utcnow()
        updated_count = 0

        for site in sites:
            time_since_heartbeat = now - site.agent_last_seen
            interval_seconds = HEARTBEAT_INTERVAL

            # Calculate thresholds in seconds
            degraded_threshold = timedelta(seconds=interval_seconds * DEGRADED_THRESHOLD)
            offline_threshold = timedelta(seconds=interval_seconds * OFFLINE_THRESHOLD)

            # Determine new status
            if time_since_heartbeat > offline_threshold:
                new_status = "offline"
            elif time_since_heartbeat > degraded_threshold:
                new_status = "degraded"
            else:
                new_status = "online"

            # Update if status changed
            if site.agent_status != new_status:
                old_status = site.agent_status
                site.agent_status = new_status
                updated_count += 1
                logger.info(
                    f"Site {site.name} ({site.id}) agent status: {old_status} -> {new_status}"
                )

        await db.commit()

        if updated_count > 0:
            logger.info(f"Updated agent status for {updated_count} site(s)")


def get_status_for_last_seen(last_seen: datetime | None) -> str:
    """Calculate agent status based on last seen timestamp.

    Args:
        last_seen: When the agent was last seen (sent heartbeat)

    Returns:
        Status string: 'online', 'degraded', or 'offline'
    """
    if last_seen is None:
        return "offline"

    now = datetime.utcnow()
    time_since_heartbeat = now - last_seen

    degraded_threshold = timedelta(seconds=HEARTBEAT_INTERVAL * DEGRADED_THRESHOLD)
    offline_threshold = timedelta(seconds=HEARTBEAT_INTERVAL * OFFLINE_THRESHOLD)

    if time_since_heartbeat > offline_threshold:
        return "offline"
    elif time_since_heartbeat > degraded_threshold:
        return "degraded"
    else:
        return "online"
