# OS Image and File Management Design

**Issue:** #31
**Date:** 2026-01-28
**Status:** Approved

## Overview

PureBoot needs unified file management for OS images, kernels, initrds, and installation files. The storage backend system exists but needs integration with the boot workflow.

## Design Decisions

| Topic | Decision |
|-------|----------|
| Storage integration | Single default backend |
| File serving | Dual protocol (TFTP + HTTP) |
| ISO extraction | Not needed (PureBoot loader handles it) |
| Checksum validation | Full integrity chain |
| Bandwidth throttling | Adaptive fair sharing with priority |

## Components

### 1. Storage Backend Configuration

**Default Boot Backend Setting**

Add a system setting to designate one storage backend as the default source for boot files:

```python
# System settings (DB or config)
default_boot_backend_id: str | None  # UUID of the storage backend
```

Workflow path resolution:
1. Workflow specifies `kernel: ubuntu-2404/vmlinuz`
2. System looks up `default_boot_backend_id`
3. File is fetched from that backend at path `/ubuntu-2404/vmlinuz`

**API Changes:**

- `PATCH /api/v1/system/settings` - Set `default_boot_backend_id`
- `GET /api/v1/system/settings` - Read current settings

**Validation:**
- Non-existent backend ID returns 404
- Offline backend shows warning but is allowed (may come online later)

### 2. Unified File Serving Endpoint

**HTTP Endpoint**

New endpoint to serve files from the default boot backend:

```
GET /api/v1/files/{path:path}
```

Example: `GET /api/v1/files/ubuntu-2404/vmlinuz`

This endpoint:
1. Looks up `default_boot_backend_id`
2. Fetches file from that backend
3. Streams to client with appropriate headers

**Response headers:**
- `Content-Type` - MIME type
- `Content-Length` - File size
- `ETag` - SHA256 checksum (for integrity verification)
- `X-Checksum-SHA256` - Explicit checksum header

**TFTP Integration**

The existing TFTP server proxies requests to the default backend:

1. TFTP request for `ubuntu-2404/vmlinuz`
2. TFTP server fetches from default backend via internal API
3. Streams back over TFTP protocol

**Optional Caching:**
- TFTP server can cache frequently-accessed files locally
- Cache invalidated when backend file changes (via checksum comparison)

### 3. Checksum Validation (Full Integrity)

**On Upload**

When a file is uploaded to any storage backend:

1. Compute SHA256 as chunks stream through
2. Store checksum in a new `file_checksums` table:

```python
class FileChecksum(Base):
    __tablename__ = "file_checksums"

    id: Mapped[str]  # UUID
    backend_id: Mapped[str]  # FK to storage_backends
    file_path: Mapped[str]  # Path within backend
    checksum_sha256: Mapped[str]  # 64-char hex
    size_bytes: Mapped[int]
    computed_at: Mapped[datetime]

    __table_args__ = (
        UniqueConstraint("backend_id", "file_path", name="uq_backend_file_path"),
    )
```

**On Download**

Serve checksum headers:
- `ETag: "sha256:<checksum>"`
- `X-Checksum-SHA256: <checksum>`

Clients can verify downloaded content matches.

**User-Provided Verification**

Upload endpoint accepts optional `expected_checksum` parameter:

```
POST /api/v1/storage/backends/{id}/files?path=/ubuntu&expected_checksum=abc123...
```

If provided, upload fails with 422 if computed checksum doesn't match.

**Background Integrity Scan**

Periodic job (configurable) re-computes checksums and flags mismatches.

### 4. Bandwidth Throttling (Adaptive Fair Sharing)

**Configuration**

System setting for total bandwidth budget:

```python
# System settings
file_serving_bandwidth_mbps: int = 1000  # Total budget (default 1 Gbps)
```

**Transfer Tracking**

Track active downloads in memory:

```python
@dataclass
class ActiveTransfer:
    id: str
    client_ip: str
    file_path: str
    file_size: int
    bytes_sent: int
    started_at: datetime
```

**Priority Calculation**

Each active transfer gets a priority score. Smaller files and near-completion transfers get higher priority:

```python
def calculate_priority(transfer: ActiveTransfer) -> float:
    remaining = transfer.file_size - transfer.bytes_sent
    percent_complete = transfer.bytes_sent / transfer.file_size

    # Smaller remaining bytes = higher priority
    size_score = 1.0 / (remaining + 1)
    # Accelerates priority as nearing completion
    completion_score = percent_complete ** 2

    return size_score + completion_score
```

**Bandwidth Allocation**

Each chunk send cycle:
1. Sum all priorities across active transfers
2. Each transfer gets `(its_priority / total_priority) * total_bandwidth`
3. Minimum floor (e.g., 1 Mbps) so no transfer fully starves

**Implementation**

Use `asyncio` rate limiting with token bucket per transfer. Bucket sizes adjusted dynamically based on priority recalculation.

### 5. Workflow Integration

**Workflow File References**

Workflows reference files by path relative to the default boot backend:

```yaml
# workflows/ubuntu-2404.yaml
name: Ubuntu 24.04 Server
install_method: kernel
kernel_path: /ubuntu-2404/vmlinuz
initrd_path: /ubuntu-2404/initrd
cmdline: "ip=dhcp url=${server.url}/files/ubuntu-2404/ubuntu-24.04.iso"
```

**URL Resolution**

The `WorkflowService` resolves paths to full URLs:

```python
def resolve_file_url(self, path: str, server: str) -> str:
    return f"{server}/api/v1/files{path}"
```

**Boot Script Generation**

In `boot.py`, kernel/initrd URLs use the new file endpoint:

```python
kernel_url = f"{server}/api/v1/files{workflow.kernel_path}"
initrd_url = f"{server}/api/v1/files{workflow.initrd_path}"
```

**Validation**

When a workflow is assigned to a node, optionally verify referenced files exist in the default backend. Warn in UI if files missing (don't block assignment).

## Out of Scope

- **ISO extraction** - Not needed; PureBoot loader mounts ISOs directly
- **File browser UI** - Frontend work, separate issue

## Implementation Tasks

1. Add `FileChecksum` model and migration
2. Add system settings for `default_boot_backend_id` and `file_serving_bandwidth_mbps`
3. Create `GET /api/v1/files/{path}` endpoint with checksum headers
4. Add checksum computation to file upload flow
5. Implement bandwidth throttler with priority-based fair sharing
6. Update TFTP server to proxy from default backend
7. Update `boot.py` to use new file URLs
8. Add optional file existence validation for workflow assignment