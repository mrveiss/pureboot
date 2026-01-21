# Sync Jobs API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement automated file synchronization from HTTP/HTTPS sources to storage backends with scheduling, WebSocket progress, and version management.

**Architecture:** APScheduler for job scheduling, rsync for file transfers, WebSocket manager for real-time progress broadcasting. Jobs stored in SQLite, runs tracked with 30-day retention. Timestamped directories for versioning.

**Tech Stack:** FastAPI, SQLAlchemy, APScheduler, WebSocket, rsync (system)

---

## Task 1: Add SyncJob and SyncJobRun Database Models

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add SyncJob model**

Add after `IscsiLun` class:

```python
class SyncJob(Base):
    """Sync job for automated file synchronization from external sources."""

    __tablename__ = "sync_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)

    # Destination
    destination_backend_id: Mapped[str] = mapped_column(
        ForeignKey("storage_backends.id"), nullable=False
    )
    destination_backend: Mapped[StorageBackend] = relationship()
    destination_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Filtering
    include_pattern: Mapped[str | None] = mapped_column(String(500), nullable=True)
    exclude_pattern: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Schedule
    schedule: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # manual, hourly, daily, weekly, monthly
    schedule_day: Mapped[int | None] = mapped_column(nullable=True)  # 0-6 or 1-31
    schedule_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM

    # Sync options
    verify_checksums: Mapped[bool] = mapped_column(default=True)
    delete_removed: Mapped[bool] = mapped_column(default=False)
    keep_versions: Mapped[int] = mapped_column(default=3)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="idle", index=True
    )  # idle, running, synced, failed
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    runs: Mapped[list["SyncJobRun"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class SyncJobRun(Base):
    """Individual run record for a sync job."""

    __tablename__ = "sync_job_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="running"
    )  # running, success, failed

    # Stats
    files_synced: Mapped[int] = mapped_column(default=0)
    bytes_transferred: Mapped[int] = mapped_column(default=0)

    # Progress
    current_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    progress_percent: Mapped[int] = mapped_column(default=0)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    job: Mapped[SyncJob] = relationship(back_populates="runs")
```

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat(db): add SyncJob and SyncJobRun models"
```

---

## Task 2: Add Sync Job Schemas

**Files:**
- Modify: `src/api/schemas.py`

**Step 1: Add imports and schemas**

Add after existing imports:

```python
from pydantic import HttpUrl
```

Add after `IscsiLunResponse` class:

```python
# Sync Job Schemas

class SyncJobCreate(BaseModel):
    """Schema for creating a sync job."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$",
    )
    source_url: HttpUrl
    destination_backend_id: str
    destination_path: str = Field(..., max_length=500)
    include_pattern: str | None = Field(None, max_length=500)
    exclude_pattern: str | None = Field(None, max_length=500)
    schedule: Literal["manual", "hourly", "daily", "weekly", "monthly"]
    schedule_day: int | None = None
    schedule_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    verify_checksums: bool = True
    delete_removed: bool = False
    keep_versions: int = Field(3, ge=0, le=10)

    @field_validator("destination_path")
    @classmethod
    def validate_destination_path(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("Path cannot contain '..'")
        return v.strip("/")

    @field_validator("schedule_day")
    @classmethod
    def validate_schedule_day(cls, v: int | None, info) -> int | None:
        schedule = info.data.get("schedule")
        if schedule == "weekly" and v is not None and not (0 <= v <= 6):
            raise ValueError("Weekly schedule_day must be 0-6 (Mon-Sun)")
        if schedule == "monthly" and v is not None and not (1 <= v <= 31):
            raise ValueError("Monthly schedule_day must be 1-31")
        return v

    @model_validator(mode="after")
    def validate_schedule_requirements(self) -> "SyncJobCreate":
        if self.schedule in ("daily", "weekly", "monthly") and not self.schedule_time:
            raise ValueError(f"{self.schedule} schedule requires schedule_time")
        if self.schedule == "weekly" and self.schedule_day is None:
            raise ValueError("Weekly schedule requires schedule_day (0-6)")
        if self.schedule == "monthly" and self.schedule_day is None:
            raise ValueError("Monthly schedule requires schedule_day (1-31)")
        return self


class SyncJobUpdate(BaseModel):
    """Schema for updating a sync job."""

    name: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$",
    )
    source_url: HttpUrl | None = None
    destination_path: str | None = Field(None, max_length=500)
    include_pattern: str | None = None
    exclude_pattern: str | None = None
    schedule: Literal["manual", "hourly", "daily", "weekly", "monthly"] | None = None
    schedule_day: int | None = None
    schedule_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    verify_checksums: bool | None = None
    delete_removed: bool | None = None
    keep_versions: int | None = Field(None, ge=0, le=10)

    @field_validator("destination_path")
    @classmethod
    def validate_destination_path(cls, v: str | None) -> str | None:
        if v and ".." in v:
            raise ValueError("Path cannot contain '..'")
        return v.strip("/") if v else v


class SyncJobResponse(BaseModel):
    """Response schema for sync job."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_url: str
    destination_backend_id: str
    destination_backend_name: str
    destination_path: str
    include_pattern: str | None
    exclude_pattern: str | None
    schedule: str
    schedule_day: int | None
    schedule_time: str | None
    verify_checksums: bool
    delete_removed: bool
    keep_versions: int
    status: str
    last_run_at: datetime | None
    last_error: str | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job) -> "SyncJobResponse":
        """Create response from SyncJob model."""
        return cls(
            id=job.id,
            name=job.name,
            source_url=job.source_url,
            destination_backend_id=job.destination_backend_id,
            destination_backend_name=job.destination_backend.name if job.destination_backend else "Unknown",
            destination_path=job.destination_path,
            include_pattern=job.include_pattern,
            exclude_pattern=job.exclude_pattern,
            schedule=job.schedule,
            schedule_day=job.schedule_day,
            schedule_time=job.schedule_time,
            verify_checksums=job.verify_checksums,
            delete_removed=job.delete_removed,
            keep_versions=job.keep_versions,
            status=job.status,
            last_run_at=job.last_run_at,
            last_error=job.last_error,
            next_run_at=job.next_run_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class SyncJobRunResponse(BaseModel):
    """Response schema for sync job run."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    files_synced: int
    bytes_transferred: int
    current_file: str | None
    progress_percent: int
    error: str | None


class SyncProgress(BaseModel):
    """WebSocket message format for sync progress."""

    job_id: str
    run_id: str
    status: str
    current_file: str | None
    files_synced: int
    bytes_transferred: int
    progress_percent: int
    error: str | None
```

**Step 2: Add Literal import if not present**

Ensure this import exists at top:

```python
from typing import Literal
```

**Step 3: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat(api): add sync job schemas"
```

---

## Task 3: Create WebSocket Manager

**Files:**
- Create: `src/core/websocket.py`

**Step 1: Create WebSocket manager**

```python
"""WebSocket connection manager for real-time updates."""
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class SyncWebSocketManager:
    """Manages WebSocket connections for sync progress updates."""

    def __init__(self):
        # job_id -> set of connected websockets
        self.connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        """Accept connection and register for job updates."""
        await websocket.accept()
        if job_id not in self.connections:
            self.connections[job_id] = set()
        self.connections[job_id].add(websocket)
        logger.info(f"WebSocket connected for job {job_id}")

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        """Remove connection on disconnect."""
        if job_id in self.connections:
            self.connections[job_id].discard(websocket)
            if not self.connections[job_id]:
                del self.connections[job_id]
        logger.info(f"WebSocket disconnected for job {job_id}")

    async def broadcast_progress(self, job_id: str, progress: dict) -> None:
        """Send progress update to all connections watching this job."""
        if job_id not in self.connections:
            return

        dead_connections = []
        for ws in self.connections[job_id]:
            try:
                await ws.send_json(progress)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.append(ws)

        for ws in dead_connections:
            self.connections[job_id].discard(ws)

    def get_connection_count(self, job_id: str) -> int:
        """Get number of active connections for a job."""
        return len(self.connections.get(job_id, set()))


# Global instance
ws_manager = SyncWebSocketManager()
```

**Step 2: Commit**

```bash
git add src/core/websocket.py
git commit -m "feat(core): add WebSocket manager for sync progress"
```

---

## Task 4: Create Sync Service

**Files:**
- Create: `src/core/sync.py`

**Step 1: Create sync service**

```python
"""Sync service for rsync-based file synchronization."""
import asyncio
import logging
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.api.schemas import SyncProgress
from src.core.websocket import ws_manager
from src.db.models import SyncJob, SyncJobRun, StorageBackend

logger = logging.getLogger(__name__)

# Regex to parse rsync progress output
# Example: "    1,234,567,890  45%   12.34MB/s    0:05:23"
PROGRESS_PATTERN = re.compile(r"([\d,]+)\s+(\d+)%\s+([\d.]+\w+/s)")

# Max concurrent syncs
MAX_CONCURRENT_SYNCS = 3


class SyncService:
    """Handles rsync execution and progress tracking."""

    def __init__(self):
        self.running_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.sync_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SYNCS)
        self._last_broadcast: Dict[str, float] = {}

    async def run_sync(
        self,
        job: SyncJob,
        run: SyncJobRun,
        db_url: str,
    ) -> bool:
        """Execute sync operation with progress reporting."""
        async with self.sync_semaphore:
            return await self._execute_sync(job, run, db_url)

    async def _execute_sync(
        self,
        job: SyncJob,
        run: SyncJobRun,
        db_url: str,
    ) -> bool:
        """Internal sync execution."""
        # Create separate engine for background task
        engine = create_async_engine(db_url)

        try:
            # Get backend mount point
            async with AsyncSession(engine) as db:
                result = await db.execute(
                    select(StorageBackend).where(StorageBackend.id == job.destination_backend_id)
                )
                backend = result.scalar_one_or_none()
                if not backend or not backend.mount_point:
                    raise ValueError("Backend not mounted or not found")
                mount_point = backend.mount_point

            # Create timestamped destination directory
            timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            dest_path = Path(mount_point) / job.destination_path / timestamp
            dest_path.mkdir(parents=True, exist_ok=True)

            # Build rsync command
            cmd = self._build_rsync_command(job, str(dest_path))
            logger.info(f"Running rsync: {' '.join(cmd)}")

            # Execute rsync
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self.running_processes[job.id] = proc

            # Parse progress output
            files_synced = 0
            bytes_transferred = 0

            async for line in proc.stdout:
                line_str = line.decode().strip()
                if not line_str:
                    continue

                # Parse progress
                match = PROGRESS_PATTERN.search(line_str)
                if match:
                    bytes_str = match.group(1).replace(",", "")
                    bytes_transferred = int(bytes_str)
                    progress_percent = int(match.group(2))

                    # Throttle broadcasts to 2/second
                    await self._broadcast_throttled(
                        job.id,
                        run.id,
                        "running",
                        None,
                        files_synced,
                        bytes_transferred,
                        progress_percent,
                    )

                # Count files (rsync outputs filename when transferring)
                elif not line_str.startswith(" ") and "/" in line_str:
                    files_synced += 1
                    current_file = line_str.split()[-1] if line_str.split() else None

                    await self._broadcast_throttled(
                        job.id,
                        run.id,
                        "running",
                        current_file,
                        files_synced,
                        bytes_transferred,
                        run.progress_percent,
                    )

            await proc.wait()

            if job.id in self.running_processes:
                del self.running_processes[job.id]

            success = proc.returncode == 0

            # Update run record
            async with AsyncSession(engine) as db:
                result = await db.execute(
                    select(SyncJobRun).where(SyncJobRun.id == run.id)
                )
                db_run = result.scalar_one()
                db_run.completed_at = datetime.utcnow()
                db_run.status = "success" if success else "failed"
                db_run.files_synced = files_synced
                db_run.bytes_transferred = bytes_transferred
                db_run.progress_percent = 100 if success else db_run.progress_percent

                if not success:
                    db_run.error = f"rsync exited with code {proc.returncode}"

                # Update job status
                result = await db.execute(
                    select(SyncJob).where(SyncJob.id == job.id)
                )
                db_job = result.scalar_one()
                db_job.status = "synced" if success else "failed"
                db_job.last_run_at = datetime.utcnow()
                if not success:
                    db_job.last_error = db_run.error

                await db.commit()

            # Broadcast final status
            await ws_manager.broadcast_progress(
                job.id,
                SyncProgress(
                    job_id=job.id,
                    run_id=run.id,
                    status="success" if success else "failed",
                    current_file=None,
                    files_synced=files_synced,
                    bytes_transferred=bytes_transferred,
                    progress_percent=100 if success else 0,
                    error=None if success else f"rsync exited with code {proc.returncode}",
                ).model_dump(),
            )

            # Prune old versions
            if success:
                await self._prune_versions(
                    Path(mount_point) / job.destination_path,
                    job.keep_versions,
                )

            # Cleanup old runs (>30 days)
            await self._cleanup_old_runs(job.id, engine)

            return success

        except Exception as e:
            logger.exception(f"Sync failed for job {job.id}: {e}")

            # Update run as failed
            async with AsyncSession(engine) as db:
                result = await db.execute(
                    select(SyncJobRun).where(SyncJobRun.id == run.id)
                )
                db_run = result.scalar_one_or_none()
                if db_run:
                    db_run.completed_at = datetime.utcnow()
                    db_run.status = "failed"
                    db_run.error = str(e)

                result = await db.execute(
                    select(SyncJob).where(SyncJob.id == job.id)
                )
                db_job = result.scalar_one_or_none()
                if db_job:
                    db_job.status = "failed"
                    db_job.last_run_at = datetime.utcnow()
                    db_job.last_error = str(e)

                await db.commit()

            # Broadcast error
            await ws_manager.broadcast_progress(
                job.id,
                SyncProgress(
                    job_id=job.id,
                    run_id=run.id,
                    status="failed",
                    current_file=None,
                    files_synced=0,
                    bytes_transferred=0,
                    progress_percent=0,
                    error=str(e),
                ).model_dump(),
            )

            return False

        finally:
            await engine.dispose()

    def _build_rsync_command(self, job: SyncJob, dest_path: str) -> list[str]:
        """Build rsync command with appropriate flags."""
        cmd = [
            "rsync",
            "-avz",
            "--progress",
            "--info=progress2",
        ]

        if job.include_pattern:
            cmd.extend(["--include", job.include_pattern])

        if job.exclude_pattern:
            cmd.extend(["--exclude", job.exclude_pattern])

        if job.verify_checksums:
            cmd.append("--checksum")

        if job.delete_removed:
            cmd.append("--delete")

        # Source URL (rsync can handle http/https via curl)
        cmd.append(job.source_url)

        # Destination path
        cmd.append(dest_path + "/")

        return cmd

    async def _broadcast_throttled(
        self,
        job_id: str,
        run_id: str,
        status: str,
        current_file: Optional[str],
        files_synced: int,
        bytes_transferred: int,
        progress_percent: int,
    ) -> None:
        """Broadcast progress, throttled to max 2/second."""
        now = asyncio.get_event_loop().time()
        last = self._last_broadcast.get(job_id, 0)

        if now - last < 0.5:  # 500ms throttle
            return

        self._last_broadcast[job_id] = now

        await ws_manager.broadcast_progress(
            job_id,
            SyncProgress(
                job_id=job_id,
                run_id=run_id,
                status=status,
                current_file=current_file,
                files_synced=files_synced,
                bytes_transferred=bytes_transferred,
                progress_percent=progress_percent,
                error=None,
            ).model_dump(),
        )

    async def _prune_versions(self, base_path: Path, keep_versions: int) -> None:
        """Remove old timestamped directories beyond keep_versions."""
        if keep_versions <= 0:
            return

        try:
            # List timestamped directories
            dirs = sorted(
                [d for d in base_path.iterdir() if d.is_dir()],
                key=lambda d: d.name,
                reverse=True,
            )

            # Remove directories beyond keep_versions
            for old_dir in dirs[keep_versions:]:
                logger.info(f"Pruning old version: {old_dir}")
                await asyncio.to_thread(shutil.rmtree, old_dir)

        except Exception as e:
            logger.warning(f"Failed to prune versions: {e}")

    async def _cleanup_old_runs(self, job_id: str, engine) -> None:
        """Delete run records older than 30 days."""
        cutoff = datetime.utcnow() - timedelta(days=30)

        async with AsyncSession(engine) as db:
            await db.execute(
                delete(SyncJobRun).where(
                    SyncJobRun.job_id == job_id,
                    SyncJobRun.started_at < cutoff,
                )
            )
            await db.commit()

    async def cancel_sync(self, job_id: str) -> bool:
        """Cancel running sync by terminating rsync process."""
        proc = self.running_processes.get(job_id)
        if proc:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

            if job_id in self.running_processes:
                del self.running_processes[job_id]

            return True
        return False

    def is_running(self, job_id: str) -> bool:
        """Check if a job is currently running."""
        return job_id in self.running_processes


# Global instance
sync_service = SyncService()
```

**Step 2: Commit**

```bash
git add src/core/sync.py
git commit -m "feat(core): add sync service with rsync integration"
```

---

## Task 5: Create Scheduler Service

**Files:**
- Create: `src/core/scheduler.py`

**Step 1: Create scheduler service**

```python
"""APScheduler-based job scheduler for sync jobs."""
import logging
from datetime import datetime
from typing import Callable, Optional

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
        except Exception:
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
```

**Step 2: Commit**

```bash
git add src/core/scheduler.py
git commit -m "feat(core): add APScheduler-based sync scheduler"
```

---

## Task 6: Create Sync Jobs Routes

**Files:**
- Create: `src/api/routes/sync_jobs.py`

**Step 1: Create routes file**

```python
"""Sync job management API endpoints."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    ApiListResponse,
    ApiResponse,
    SyncJobCreate,
    SyncJobResponse,
    SyncJobRunResponse,
    SyncJobUpdate,
)
from src.core.scheduler import sync_scheduler
from src.core.sync import sync_service
from src.core.websocket import ws_manager
from src.db.database import get_db, get_database_url
from src.db.models import StorageBackend, SyncJob, SyncJobRun

logger = logging.getLogger(__name__)
router = APIRouter()

# Rate limiting for manual runs (job_id -> last_run_time)
_manual_run_times: dict[str, float] = {}


@router.get("/storage/sync-jobs", response_model=ApiListResponse[SyncJobResponse])
async def list_sync_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    backend_id: Optional[str] = Query(None, description="Filter by backend"),
    db: AsyncSession = Depends(get_db),
):
    """List all sync jobs."""
    query = select(SyncJob).options(selectinload(SyncJob.destination_backend))

    if status:
        query = query.where(SyncJob.status == status)
    if backend_id:
        query = query.where(SyncJob.destination_backend_id == backend_id)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return ApiListResponse(
        data=[SyncJobResponse.from_job(j) for j in jobs],
        total=len(jobs),
    )


@router.get("/storage/sync-jobs/{job_id}", response_model=ApiResponse[SyncJobResponse])
async def get_sync_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get sync job details."""
    result = await db.execute(
        select(SyncJob)
        .options(selectinload(SyncJob.destination_backend))
        .where(SyncJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")

    return ApiResponse(data=SyncJobResponse.from_job(job))


@router.post("/storage/sync-jobs", response_model=ApiResponse[SyncJobResponse], status_code=201)
async def create_sync_job(
    job_data: SyncJobCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new sync job."""
    # Check for duplicate name
    existing = await db.execute(
        select(SyncJob).where(SyncJob.name == job_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Job '{job_data.name}' already exists")

    # Verify backend exists
    result = await db.execute(
        select(StorageBackend).where(StorageBackend.id == job_data.destination_backend_id)
    )
    backend = result.scalar_one_or_none()
    if not backend:
        raise HTTPException(status_code=400, detail="Destination backend not found")

    # Create job
    job = SyncJob(
        name=job_data.name,
        source_url=str(job_data.source_url),
        destination_backend_id=job_data.destination_backend_id,
        destination_path=job_data.destination_path,
        include_pattern=job_data.include_pattern,
        exclude_pattern=job_data.exclude_pattern,
        schedule=job_data.schedule,
        schedule_day=job_data.schedule_day,
        schedule_time=job_data.schedule_time,
        verify_checksums=job_data.verify_checksums,
        delete_removed=job_data.delete_removed,
        keep_versions=job_data.keep_versions,
        status="idle",
    )

    # Schedule if not manual
    if job_data.schedule != "manual":
        next_run = sync_scheduler.schedule_job(
            job.id,
            job_data.schedule,
            job_data.schedule_day,
            job_data.schedule_time,
        )
        job.next_run_at = next_run

    db.add(job)
    await db.flush()

    # Reload with relationship
    await db.refresh(job, ["destination_backend"])

    return ApiResponse(
        data=SyncJobResponse.from_job(job),
        message="Sync job created successfully",
    )


@router.patch("/storage/sync-jobs/{job_id}", response_model=ApiResponse[SyncJobResponse])
async def update_sync_job(
    job_id: str,
    job_data: SyncJobUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a sync job."""
    result = await db.execute(
        select(SyncJob)
        .options(selectinload(SyncJob.destination_backend))
        .where(SyncJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")

    if job.status == "running":
        raise HTTPException(status_code=400, detail="Cannot update running job")

    # Check name uniqueness
    if job_data.name and job_data.name != job.name:
        existing = await db.execute(
            select(SyncJob).where(SyncJob.name == job_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Job '{job_data.name}' already exists")
        job.name = job_data.name

    # Update fields
    if job_data.source_url is not None:
        job.source_url = str(job_data.source_url)
    if job_data.destination_path is not None:
        job.destination_path = job_data.destination_path
    if job_data.include_pattern is not None:
        job.include_pattern = job_data.include_pattern
    if job_data.exclude_pattern is not None:
        job.exclude_pattern = job_data.exclude_pattern
    if job_data.verify_checksums is not None:
        job.verify_checksums = job_data.verify_checksums
    if job_data.delete_removed is not None:
        job.delete_removed = job_data.delete_removed
    if job_data.keep_versions is not None:
        job.keep_versions = job_data.keep_versions

    # Update schedule
    schedule_changed = False
    if job_data.schedule is not None:
        job.schedule = job_data.schedule
        schedule_changed = True
    if job_data.schedule_day is not None:
        job.schedule_day = job_data.schedule_day
        schedule_changed = True
    if job_data.schedule_time is not None:
        job.schedule_time = job_data.schedule_time
        schedule_changed = True

    if schedule_changed:
        if job.schedule == "manual":
            sync_scheduler.remove_job(job.id)
            job.next_run_at = None
        else:
            next_run = sync_scheduler.schedule_job(
                job.id,
                job.schedule,
                job.schedule_day,
                job.schedule_time,
            )
            job.next_run_at = next_run

    await db.flush()

    return ApiResponse(
        data=SyncJobResponse.from_job(job),
        message="Sync job updated successfully",
    )


@router.delete("/storage/sync-jobs/{job_id}", response_model=ApiResponse[dict])
async def delete_sync_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a sync job."""
    result = await db.execute(
        select(SyncJob).where(SyncJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")

    # Cancel if running
    if job.status == "running":
        await sync_service.cancel_sync(job_id)

    # Remove from scheduler
    sync_scheduler.remove_job(job_id)

    await db.delete(job)
    await db.flush()

    return ApiResponse(
        data={"id": job_id},
        message="Sync job deleted successfully",
    )


@router.post("/storage/sync-jobs/{job_id}/run", response_model=ApiResponse[SyncJobRunResponse])
async def run_sync_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Trigger manual sync run."""
    # Rate limiting: 1 run per minute per job
    now = asyncio.get_event_loop().time()
    last_run = _manual_run_times.get(job_id, 0)
    if now - last_run < 60:
        raise HTTPException(
            status_code=429,
            detail="Rate limit: wait 1 minute between manual runs",
        )
    _manual_run_times[job_id] = now

    result = await db.execute(
        select(SyncJob)
        .options(selectinload(SyncJob.destination_backend))
        .where(SyncJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")

    if job.status == "running":
        raise HTTPException(status_code=400, detail="Job is already running")

    # Verify backend is online
    if not job.destination_backend:
        raise HTTPException(status_code=400, detail="Destination backend not found")
    if job.destination_backend.status != "online":
        raise HTTPException(status_code=400, detail="Destination backend is not online")

    # Create run record
    run = SyncJobRun(job_id=job_id)
    db.add(run)

    # Update job status
    job.status = "running"
    await db.flush()
    await db.refresh(run)

    # Start background sync
    db_url = get_database_url()
    asyncio.create_task(sync_service.run_sync(job, run, db_url))

    return ApiResponse(
        data=SyncJobRunResponse(
            id=run.id,
            job_id=run.job_id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            status=run.status,
            files_synced=run.files_synced,
            bytes_transferred=run.bytes_transferred,
            current_file=run.current_file,
            progress_percent=run.progress_percent,
            error=run.error,
        ),
        message="Sync started",
    )


@router.post("/storage/sync-jobs/{job_id}/cancel", response_model=ApiResponse[dict])
async def cancel_sync_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running sync job."""
    result = await db.execute(
        select(SyncJob).where(SyncJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")

    if job.status != "running":
        raise HTTPException(status_code=400, detail="Job is not running")

    cancelled = await sync_service.cancel_sync(job_id)

    if cancelled:
        job.status = "idle"
        await db.flush()

    return ApiResponse(
        data={"cancelled": cancelled},
        message="Sync cancelled" if cancelled else "Could not cancel sync",
    )


@router.get("/storage/sync-jobs/{job_id}/history", response_model=ApiListResponse[SyncJobRunResponse])
async def get_sync_job_history(
    job_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get run history for a sync job."""
    # Verify job exists
    result = await db.execute(
        select(SyncJob).where(SyncJob.id == job_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sync job not found")

    # Get runs
    result = await db.execute(
        select(SyncJobRun)
        .where(SyncJobRun.job_id == job_id)
        .order_by(SyncJobRun.started_at.desc())
        .offset(offset)
        .limit(limit)
    )
    runs = result.scalars().all()

    # Get total count
    count_result = await db.execute(
        select(SyncJobRun).where(SyncJobRun.job_id == job_id)
    )
    total = len(count_result.scalars().all())

    return ApiListResponse(
        data=[
            SyncJobRunResponse(
                id=r.id,
                job_id=r.job_id,
                started_at=r.started_at,
                completed_at=r.completed_at,
                status=r.status,
                files_synced=r.files_synced,
                bytes_transferred=r.bytes_transferred,
                current_file=r.current_file,
                progress_percent=r.progress_percent,
                error=r.error,
            )
            for r in runs
        ],
        total=total,
    )


@router.websocket("/ws/sync/{job_id}")
async def sync_progress_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time sync progress."""
    await ws_manager.connect(job_id, websocket)
    try:
        while True:
            # Keep connection alive, handle pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(job_id, websocket)


async def _scheduled_job_callback(job_id: str) -> None:
    """Callback executed by scheduler for scheduled jobs."""
    from src.db.database import async_session_factory, get_database_url

    async with async_session_factory() as db:
        result = await db.execute(
            select(SyncJob)
            .options(selectinload(SyncJob.destination_backend))
            .where(SyncJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            logger.warning(f"Scheduled job {job_id} not found")
            return

        if job.status == "running":
            logger.info(f"Job {job_id} already running, skipping scheduled run")
            return

        if not job.destination_backend or job.destination_backend.status != "online":
            logger.warning(f"Backend not online for job {job_id}")
            job.status = "failed"
            job.last_error = "Backend not online"
            await db.commit()
            return

        # Create run record
        run = SyncJobRun(job_id=job_id)
        db.add(run)
        job.status = "running"
        await db.commit()
        await db.refresh(run)

        # Update next_run_at
        next_run = sync_scheduler.get_next_run_time(job_id)
        if next_run:
            job.next_run_at = next_run
            await db.commit()

    # Start sync
    db_url = get_database_url()
    await sync_service.run_sync(job, run, db_url)


# Set scheduler callback
sync_scheduler.set_job_callback(_scheduled_job_callback)
```

**Step 2: Commit**

```bash
git add src/api/routes/sync_jobs.py
git commit -m "feat(api): add sync jobs routes with WebSocket support"
```

---

## Task 7: Register Router and Add Dependencies

**Files:**
- Modify: `src/main.py`
- Modify: `requirements.txt`
- Modify: `src/db/database.py`

**Step 1: Add database URL helper to database.py**

Add after existing imports and before `get_db`:

```python
def get_database_url() -> str:
    """Get the database URL for async connections."""
    from src.config.settings import settings
    return f"sqlite+aiosqlite:///{settings.data_directory}/pureboot.db"
```

Add async_session_factory if not present:

```python
async_session_factory = None

async def init_db():
    """Initialize database and create tables."""
    global async_session_factory
    # ... existing code ...
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

**Step 2: Add router import and registration to main.py**

Add import:

```python
from src.api.routes.sync_jobs import router as sync_jobs_router
from src.core.scheduler import sync_scheduler
```

Add router registration (after other routers):

```python
app.include_router(sync_jobs_router, prefix="/api/v1", tags=["sync-jobs"])
```

Add scheduler startup/shutdown:

```python
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    sync_scheduler.start()
    # Re-register scheduled jobs from database
    await _register_scheduled_jobs()

@app.on_event("shutdown")
async def shutdown_event():
    sync_scheduler.shutdown(wait=True)

async def _register_scheduled_jobs():
    """Re-register all non-manual sync jobs on startup."""
    from src.db.database import async_session_factory
    from src.db.models import SyncJob
    from sqlalchemy import select

    if not async_session_factory:
        return

    async with async_session_factory() as db:
        result = await db.execute(
            select(SyncJob).where(SyncJob.schedule != "manual")
        )
        jobs = result.scalars().all()

        for job in jobs:
            next_run = sync_scheduler.schedule_job(
                job.id,
                job.schedule,
                job.schedule_day,
                job.schedule_time,
            )
            if next_run:
                job.next_run_at = next_run

        await db.commit()
```

**Step 3: Add APScheduler to requirements.txt**

Add line:

```
apscheduler>=3.10.0
```

**Step 4: Commit**

```bash
git add src/main.py src/db/database.py requirements.txt
git commit -m "feat: register sync jobs router and add scheduler integration"
```

---

## Task 8: Push and Create PR

**Step 1: Push branch**

```bash
git push -u origin feature/sync-jobs
```

**Step 2: Create PR**

```bash
gh pr create --title "Backend: Implement Sync Jobs API" --body "$(cat <<'EOF'
## Summary

Implements Sync Jobs API for automated file synchronization from HTTP/HTTPS sources. Closes #17.

- Add `SyncJob` and `SyncJobRun` database models
- Add Pydantic schemas with validation
- Implement APScheduler-based job scheduling
- Add rsync-based sync service with progress tracking
- WebSocket endpoint for real-time progress updates
- Timestamped directory versioning with configurable retention
- 30-day time-based run history retention

### Key Features

- **Scheduling:** Manual, hourly, daily, weekly, monthly schedules
- **Progress:** Real-time WebSocket updates during sync
- **Versioning:** Timestamped directories, configurable retention
- **Filtering:** Include/exclude patterns for rsync
- **Options:** Checksum verification, delete removed files

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/sync-jobs` | List sync jobs |
| GET | `/api/v1/storage/sync-jobs/{id}` | Get job details |
| POST | `/api/v1/storage/sync-jobs` | Create job |
| PATCH | `/api/v1/storage/sync-jobs/{id}` | Update job |
| DELETE | `/api/v1/storage/sync-jobs/{id}` | Delete job |
| POST | `/api/v1/storage/sync-jobs/{id}/run` | Trigger manual run |
| POST | `/api/v1/storage/sync-jobs/{id}/cancel` | Cancel running job |
| GET | `/api/v1/storage/sync-jobs/{id}/history` | Get run history |
| WS | `/ws/sync/{job_id}` | Real-time progress |

## Test plan

- [ ] Create sync job with various schedules
- [ ] Trigger manual run and verify WebSocket progress
- [ ] Verify timestamped directory creation
- [ ] Test version pruning after sync
- [ ] Verify run history cleanup (>30 days)
- [ ] Test job cancellation

## Related

- Closes #17
- Created #23 for scheduler backend GUI setting

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Database models | `src/db/models.py` |
| 2 | Pydantic schemas | `src/api/schemas.py` |
| 3 | WebSocket manager | `src/core/websocket.py` |
| 4 | Sync service | `src/core/sync.py` |
| 5 | Scheduler service | `src/core/scheduler.py` |
| 6 | API routes | `src/api/routes/sync_jobs.py` |
| 7 | Registration & deps | `src/main.py`, `src/db/database.py`, `requirements.txt` |
| 8 | Push & PR | Git operations |

**Dependencies:** `apscheduler>=3.10.0`, rsync (system package)
