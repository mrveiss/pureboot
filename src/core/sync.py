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
