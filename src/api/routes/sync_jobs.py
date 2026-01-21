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

    # Get total count efficiently
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count()).select_from(SyncJobRun).where(SyncJobRun.job_id == job_id)
    )
    total = count_result.scalar() or 0

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
async def sync_progress_websocket(
    websocket: WebSocket,
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint for real-time sync progress."""
    # Verify job exists before accepting connection
    result = await db.execute(
        select(SyncJob).where(SyncJob.id == job_id)
    )
    if not result.scalar_one_or_none():
        await websocket.close(code=4004, reason="Job not found")
        return

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
