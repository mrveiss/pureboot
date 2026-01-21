# Sync Jobs API Design

**Issue:** #17 - Backend: Implement Sync Jobs API
**Date:** 2026-01-21
**Status:** Approved

## Overview

Implement automated file synchronization from external HTTP/HTTPS sources to PureBoot storage backends. Primary use cases include mirroring OS ISOs, driver packages, and configuration files.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sync tool | rsync | Battle-tested, efficient delta transfers, built into most Linux systems |
| Scheduler | APScheduler | In-process, SQLite persistence, no additional infrastructure |
| Real-time updates | WebSocket | Full real-time progress for sync operations |
| Version retention | Timestamped directories | Each sync creates dated subdirectory, oldest pruned |
| Run history | Time-based (30 days) | Runs older than 30 days auto-deleted |

## Data Model

### SyncJob

```python
class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[str]  # UUID, primary key
    name: Mapped[str]  # unique, alphanumeric + hyphens
    source_url: Mapped[str]  # HTTP/HTTPS URL to sync from

    # Destination
    destination_backend_id: Mapped[str]  # FK to storage_backends
    destination_path: Mapped[str]  # relative path within backend

    # Filtering
    include_pattern: Mapped[str | None]  # glob pattern (e.g., "*.iso")
    exclude_pattern: Mapped[str | None]  # glob pattern (e.g., "*.tmp")

    # Schedule
    schedule: Mapped[str]  # 'manual', 'hourly', 'daily', 'weekly', 'monthly'
    schedule_day: Mapped[int | None]  # 0-6 for weekly (Mon-Sun), 1-31 for monthly
    schedule_time: Mapped[str | None]  # HH:MM format

    # Sync options
    verify_checksums: Mapped[bool]  # default True
    delete_removed: Mapped[bool]  # default False
    keep_versions: Mapped[int]  # default 3, range 0-10

    # Status
    status: Mapped[str]  # 'idle', 'running', 'synced', 'failed'
    last_run_at: Mapped[datetime | None]
    last_error: Mapped[str | None]
    next_run_at: Mapped[datetime | None]

    # Timestamps
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Relationships
    backend: relationship -> StorageBackend
    runs: relationship -> SyncJobRun[]
```

### SyncJobRun

```python
class SyncJobRun(Base):
    __tablename__ = "sync_job_runs"

    id: Mapped[str]  # UUID, primary key
    job_id: Mapped[str]  # FK to sync_jobs
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    status: Mapped[str]  # 'running', 'success', 'failed'

    # Stats
    files_synced: Mapped[int]  # default 0
    bytes_transferred: Mapped[int]  # default 0

    # Progress (updated during run)
    current_file: Mapped[str | None]
    progress_percent: Mapped[int]  # default 0

    error: Mapped[str | None]

    # Relationships
    job: relationship -> SyncJob
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/sync-jobs` | List jobs (filter by status, backend_id) |
| GET | `/api/v1/storage/sync-jobs/{id}` | Get job details |
| POST | `/api/v1/storage/sync-jobs` | Create job |
| PATCH | `/api/v1/storage/sync-jobs/{id}` | Update job |
| DELETE | `/api/v1/storage/sync-jobs/{id}` | Delete job (cancels if running) |
| POST | `/api/v1/storage/sync-jobs/{id}/run` | Trigger manual run |
| POST | `/api/v1/storage/sync-jobs/{id}/cancel` | Cancel running job |
| GET | `/api/v1/storage/sync-jobs/{id}/history` | Get run history (paginated) |
| WS | `/ws/sync/{job_id}` | Real-time progress updates |

### Schemas

```python
class SyncJobCreate(BaseModel):
    name: str  # pattern: ^[a-zA-Z0-9][a-zA-Z0-9\-]{1,98}[a-zA-Z0-9]$
    source_url: HttpUrl
    destination_backend_id: str
    destination_path: str  # max 500 chars, no ".." or leading "/"
    include_pattern: str | None = None
    exclude_pattern: str | None = None
    schedule: Literal['manual', 'hourly', 'daily', 'weekly', 'monthly']
    schedule_day: int | None = None  # required for weekly/monthly
    schedule_time: str | None = None  # required for daily/weekly/monthly, HH:MM
    verify_checksums: bool = True
    delete_removed: bool = False
    keep_versions: int = 3  # range 0-10

class SyncJobUpdate(BaseModel):
    name: str | None = None
    source_url: HttpUrl | None = None
    destination_path: str | None = None
    include_pattern: str | None = None
    exclude_pattern: str | None = None
    schedule: Literal['manual', 'hourly', 'daily', 'weekly', 'monthly'] | None = None
    schedule_day: int | None = None
    schedule_time: str | None = None
    verify_checksums: bool | None = None
    delete_removed: bool | None = None
    keep_versions: int | None = None

class SyncJobResponse(BaseModel):
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

class SyncJobRunResponse(BaseModel):
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
    """WebSocket message format."""
    job_id: str
    run_id: str
    status: str  # 'running', 'success', 'failed'
    current_file: str | None
    files_synced: int
    bytes_transferred: int
    progress_percent: int
    error: str | None
```

## Service Layer

### SyncService

```python
class SyncService:
    """Handles rsync execution and progress tracking."""

    def __init__(self, ws_manager: SyncWebSocketManager):
        self.ws_manager = ws_manager
        self.running_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.sync_semaphore = asyncio.Semaphore(3)  # max concurrent syncs

    async def run_sync(self, job: SyncJob, run: SyncJobRun) -> bool:
        """Execute sync operation with progress reporting."""
        # 1. Acquire semaphore (queue if at limit)
        # 2. Create timestamped destination directory
        # 3. Build rsync command with options
        # 4. Execute with progress parsing
        # 5. Broadcast progress via WebSocket
        # 6. Prune old versions if keep_versions exceeded
        # 7. Cleanup old run records (>30 days)
        # 8. Release semaphore

    async def cancel_sync(self, job_id: str) -> bool:
        """Cancel running sync by terminating rsync process."""

    def _build_rsync_command(self, job: SyncJob, dest_path: str) -> list[str]:
        """Build rsync command with appropriate flags."""
        # Base: rsync -avz --progress --info=progress2
        # --include/--exclude for patterns
        # --checksum if verify_checksums
        # --delete if delete_removed
```

### rsync Command Structure

```bash
rsync -avz --progress --info=progress2 \
    --include="*.iso" \
    --exclude="*" \
    --checksum \
    https://releases.ubuntu.com/24.04/ \
    /mnt/nfs-backend/ubuntu/2026-01-21T14:30:00/
```

### Progress Parsing

rsync with `--info=progress2` outputs:
```
    1,234,567,890  45%   12.34MB/s    0:05:23
```

Regex pattern: `(\d[\d,]*)\s+(\d+)%\s+([\d.]+\w+/s)`

Progress updates throttled to max 2/second to avoid WebSocket flooding.

## Scheduler Integration

### SyncScheduler

```python
class SyncScheduler:
    """Manages scheduled sync jobs using APScheduler."""

    def __init__(self, db_url: str):
        self.scheduler = AsyncIOScheduler(
            jobstores={'default': SQLAlchemyJobStore(url=db_url)},
            job_defaults={'coalesce': True, 'max_instances': 1}
        )

    def schedule_job(self, sync_job: SyncJob) -> None:
        """Add or update job schedule based on sync_job settings."""

    def remove_job(self, job_id: str) -> None:
        """Remove job from scheduler."""

    def get_next_run_time(self, job_id: str) -> datetime | None:
        """Get next scheduled run time for a job."""

    def start(self) -> None:
        """Start scheduler on app startup."""

    def shutdown(self) -> None:
        """Graceful shutdown on app exit."""
```

### Schedule Mapping

| Schedule | APScheduler Trigger |
|----------|---------------------|
| manual | No trigger (run via API only) |
| hourly | `CronTrigger(minute=0)` |
| daily | `CronTrigger(hour=H, minute=M)` |
| weekly | `CronTrigger(day_of_week=D, hour=H, minute=M)` |
| monthly | `CronTrigger(day=D, hour=H, minute=M)` |

### FastAPI Integration

```python
@app.on_event("startup")
async def startup():
    scheduler.start()
    # Re-register all non-manual jobs from database

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=True)
```

## WebSocket Implementation

### SyncWebSocketManager

```python
class SyncWebSocketManager:
    """Manages WebSocket connections for sync progress updates."""

    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}  # job_id -> websockets

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        """Accept connection and register for job updates."""

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        """Remove connection on disconnect."""

    async def broadcast_progress(self, job_id: str, progress: SyncProgress) -> None:
        """Send progress update to all connections watching this job."""
```

### WebSocket Endpoint

```python
@router.websocket("/ws/sync/{job_id}")
async def sync_progress_ws(websocket: WebSocket, job_id: str):
    await ws_manager.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(job_id, websocket)
```

## Error Handling

| Error | Handling |
|-------|----------|
| Source URL unreachable | Set status='failed', store error, broadcast via WebSocket |
| Destination backend offline | Reject run with 400, suggest testing backend first |
| rsync timeout (4h default) | Kill process, set status='failed' |
| Disk full on destination | Parse rsync error, set status='failed' |
| Invalid include/exclude pattern | Validate on create/update, reject with 400 |
| Job deleted while running | Cancel rsync process, cleanup partial files |

## Security

1. **URL Validation** - Only HTTP/HTTPS sources (Pydantic HttpUrl)
2. **Path Traversal** - Reject `..` or leading `/` in destination_path
3. **Command Injection** - Use subprocess with list args, never shell interpolation
4. **Rate Limiting** - Max 1 manual run trigger per job per minute
5. **Backend Access** - Verify backend exists and is online before starting

## Concurrency Control

- Global semaphore limits concurrent syncs (default: 3, configurable)
- Jobs queue up if limit reached
- Per-backend locking prevents parallel writes to same destination
- APScheduler `max_instances=1` prevents overlapping scheduled runs

## Version Management

Each sync creates a timestamped subdirectory:
```
/mnt/nfs-backend/ubuntu/
├── 2026-01-19T10:00:00/
├── 2026-01-20T10:00:00/
└── 2026-01-21T10:00:00/  (latest)
```

After sync completes, directories beyond `keep_versions` are pruned (oldest first).

## Dependencies

- `apscheduler>=3.10.0` - Job scheduling
- rsync (system package) - File synchronization

## Related Issues

- #21 - Task Queue System Overhaul (future migration path for scheduler)
- #XX - GUI Setting for Scheduler Backend Selection (to be created)
