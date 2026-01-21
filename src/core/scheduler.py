"""APScheduler-based job scheduler for sync jobs."""
import logging
from datetime import datetime
from typing import Callable, Optional

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Manages scheduled sync jobs using APScheduler."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(
            job_defaults={"coalesce": True, "max_instances": 1}
        )
        self._job_callback: Optional[Callable] = None

    def set_job_callback(self, callback: Callable) -> None:
        """Set the callback function to execute when a job triggers."""
        self._job_callback = callback

    def schedule_job(
        self,
        job_id: str,
        schedule: str,
        schedule_day: Optional[int] = None,
        schedule_time: Optional[str] = None,
    ) -> Optional[datetime]:
        """
        Add or update job schedule.

        Returns next run time or None for manual jobs.
        """
        # Remove existing schedule if present
        self.remove_job(job_id)

        if schedule == "manual":
            return None

        # Parse schedule_time
        hour, minute = 0, 0
        if schedule_time:
            hour, minute = map(int, schedule_time.split(":"))

        # Build trigger based on schedule type
        if schedule == "hourly":
            trigger = CronTrigger(minute=0)
        elif schedule == "daily":
            trigger = CronTrigger(hour=hour, minute=minute)
        elif schedule == "weekly":
            # schedule_day: 0=Monday, 6=Sunday
            trigger = CronTrigger(day_of_week=schedule_day, hour=hour, minute=minute)
        elif schedule == "monthly":
            trigger = CronTrigger(day=schedule_day, hour=hour, minute=minute)
        else:
            logger.warning(f"Unknown schedule type: {schedule}")
            return None

        # Add job to scheduler
        job = self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job_id,
            args=[job_id],
            replace_existing=True,
        )

        logger.info(f"Scheduled job {job_id} with {schedule} trigger")
        return job.next_run_time

    async def _execute_job(self, job_id: str) -> None:
        """Execute the job callback when scheduler triggers."""
        if self._job_callback:
            logger.info(f"Scheduler triggering job {job_id}")
            await self._job_callback(job_id)
        else:
            logger.warning(f"No callback set for scheduled job {job_id}")

    def remove_job(self, job_id: str) -> None:
        """Remove job from scheduler."""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job {job_id} from scheduler")
        except JobLookupError:
            pass  # Job doesn't exist

    def get_next_run_time(self, job_id: str) -> Optional[datetime]:
        """Get next scheduled run time for a job."""
        job = self.scheduler.get_job(job_id)
        return job.next_run_time if job else None

    def start(self) -> None:
        """Start scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        """Graceful shutdown."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler stopped")

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self.scheduler.running


# Global instance
sync_scheduler = SyncScheduler()
