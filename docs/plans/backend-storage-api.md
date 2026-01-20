# Backend Storage API Requirements

**Status:** Not Implemented
**Priority:** Required for Phase 4 Frontend
**Created:** 2026-01-20

This document specifies the backend API endpoints required to support the Phase 4 Storage Infrastructure frontend.

---

## 1. Storage Backends API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/backends` | List all storage backends |
| GET | `/api/v1/storage/backends/{id}` | Get backend details |
| POST | `/api/v1/storage/backends` | Create backend |
| PATCH | `/api/v1/storage/backends/{id}` | Update backend |
| DELETE | `/api/v1/storage/backends/{id}` | Delete backend |
| POST | `/api/v1/storage/backends/{id}/test` | Test connection |

### Data Model

```python
class StorageBackend:
    id: str (UUID)
    name: str
    type: Literal['nfs', 'iscsi', 's3', 'http']
    status: Literal['online', 'offline', 'error']
    config: dict  # Type-specific configuration
    stats: {
        used_bytes: int
        total_bytes: int | None
        file_count: int
        template_count: int
    }
    created_at: datetime
    updated_at: datetime
```

### Implementation Notes

- **NFS**: Use subprocess to mount/unmount, check connectivity via stat
- **iSCSI**: Use targetcli or open-iscsi for target management
- **S3**: Use boto3 for S3-compatible storage
- **HTTP**: Simple HTTP HEAD requests for connectivity

---

## 2. File Browser API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/backends/{id}/files?path=/` | List files |
| POST | `/api/v1/storage/backends/{id}/files` | Upload file (multipart) |
| GET | `/api/v1/storage/backends/{id}/files/download?path=` | Download file |
| DELETE | `/api/v1/storage/backends/{id}/files` | Delete files (body: paths[]) |
| POST | `/api/v1/storage/backends/{id}/folders` | Create folder |
| POST | `/api/v1/storage/backends/{id}/files/move` | Move files |

### Data Model

```python
class StorageFile:
    name: str
    path: str
    type: Literal['file', 'directory']
    size: int | None
    mime_type: str | None
    modified_at: datetime
    item_count: int | None  # For directories
```

### Implementation Notes

- NFS: Direct filesystem operations on mounted share
- S3: Use boto3 list_objects_v2, get_object, put_object
- HTTP: Read-only listing via directory index parsing
- iSCSI: Not applicable (block storage, not file)

---

## 3. iSCSI LUN API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/luns` | List all LUNs |
| GET | `/api/v1/storage/luns/{id}` | Get LUN details |
| POST | `/api/v1/storage/luns` | Create LUN |
| PATCH | `/api/v1/storage/luns/{id}` | Update LUN |
| DELETE | `/api/v1/storage/luns/{id}` | Delete LUN |
| POST | `/api/v1/storage/luns/{id}/assign` | Assign to node |
| POST | `/api/v1/storage/luns/{id}/unassign` | Unassign from node |

### Data Model

```python
class IscsiLun:
    id: str (UUID)
    name: str
    size_gb: int
    target_id: str  # Reference to iSCSI backend
    target_name: str
    iqn: str  # Auto-generated IQN
    purpose: Literal['boot_from_san', 'install_source', 'auto_provision']
    status: Literal['active', 'ready', 'error', 'creating', 'deleting']
    assigned_node_id: str | None
    assigned_node_name: str | None
    chap_enabled: bool
    created_at: datetime
    updated_at: datetime
```

### Implementation Notes

- Use targetcli for LUN management
- IQN format: `iqn.2026-01.local.pureboot:{lun_name}`
- CHAP credentials stored in secrets vault
- Background task for LUN creation (can take time)

---

## 4. Sync Jobs API

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/storage/sync-jobs` | List sync jobs |
| GET | `/api/v1/storage/sync-jobs/{id}` | Get job details |
| POST | `/api/v1/storage/sync-jobs` | Create job |
| PATCH | `/api/v1/storage/sync-jobs/{id}` | Update job |
| DELETE | `/api/v1/storage/sync-jobs/{id}` | Delete job |
| POST | `/api/v1/storage/sync-jobs/{id}/run` | Trigger manual run |
| GET | `/api/v1/storage/sync-jobs/{id}/history` | Get run history |

### Data Model

```python
class SyncJob:
    id: str (UUID)
    name: str
    source_url: str
    destination_backend_id: str
    destination_backend_name: str
    destination_path: str
    include_pattern: str | None
    exclude_pattern: str | None
    schedule: Literal['manual', 'hourly', 'daily', 'weekly', 'monthly']
    schedule_day: int | None  # 0-6 for weekly, 1-31 for monthly
    schedule_time: str | None  # HH:MM
    verify_checksums: bool
    delete_removed: bool
    keep_versions: int
    status: Literal['idle', 'running', 'synced', 'failed']
    last_run_at: datetime | None
    last_error: str | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

class SyncJobRun:
    id: str (UUID)
    job_id: str
    started_at: datetime
    completed_at: datetime | None
    status: Literal['running', 'success', 'failed']
    files_synced: int
    bytes_transferred: int
    error: str | None
```

### Implementation Notes

- Use rclone or rsync for actual sync operations
- Scheduler integration (APScheduler or Celery Beat)
- WebSocket notifications for real-time status updates
- Keep last N run records per job

---

## Implementation Priority

1. **Storage Backends** - Foundation for all other features
2. **File Browser** - Most commonly used feature
3. **Sync Jobs** - Automated content updates
4. **iSCSI LUNs** - Advanced feature, can be deferred

---

## Security Considerations

- Validate all paths to prevent directory traversal
- Encrypt credentials at rest
- Rate limit upload endpoints
- Validate file types for uploads
- Audit log all operations
