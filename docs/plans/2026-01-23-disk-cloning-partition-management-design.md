# Disk Cloning & Partition Management Design

**Issues:** #46 (Partition Management Tool), #78 (Complete Live Disk Cloning)
**Date:** 2026-01-23
**Status:** Draft

## Overview

This design covers two related GitHub issues as a unified feature:

- **Issue #46 - Partition Management Tool**: A web-based GParted-style interface for viewing and modifying disk partitions on booted nodes.
- **Issue #78 - Live Disk Cloning**: Complete the clone coordination backend and add a clone wizard UI for VM migration and rapid deployment.

### User Workflows Supported

1. **Clone same-size disks**: Source → Target (direct copy)
2. **Clone to smaller disk**: Analyze partitions → Shrink on source → Clone → Boot
3. **Clone to larger disk**: Clone → Grow partitions on target → Boot
4. **VM disk expansion**: Boot into partition tool → Grow partition → Reboot
5. **Disk preparation**: Create partition layout before OS install

---

## Architecture

### Key Design Decisions

- **Controller as CA**: Controller generates root CA at startup, issues short-lived certs per clone session
- **Dual clone modes**: Staged (via storage backend) and Direct (peer-to-peer)
- **Decentralized cloning**: Controller orchestrates but doesn't proxy data
- **Offline resilience**: Nodes queue status updates when controller unreachable
- **Encryption**: All traffic encrypted (HTTPS for controller↔node, mTLS for node↔node)

### Clone Modes

| Mode | Use Case | Data Path | Source Behavior |
|------|----------|-----------|-----------------|
| `staged` | Templates, one-to-many, offline targets | Source → Storage → Target(s) | Reboots after upload |
| `direct` | Live migration, device swap | Source → Target (P2P over mTLS) | Stays online until complete |

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       PureBoot Controller                        │
│                                                                  │
│  CA Service              Clone API            Partition API      │
│  - Generate root CA      - Create session     - Scan disks       │
│  - Issue session certs   - Track progress     - Queue operations │
│                          - Manage lifecycle   - Execute changes  │
└──────────────────────────────────────────────────────────────────┘
                    │                     │
        ┌───────────┴───────────┐         │
        ▼                       ▼         ▼
┌───────────────┐       ┌───────────────┐
│ Clone Source  │ mTLS  │ Clone Target  │
│               │◄─────►│               │
│ Deploy Env    │ or    │ Deploy Env    │
│ + TLS Server  │ via   │ + TLS Client  │
│ + Disk Tools  │Storage│ + Disk Tools  │
└───────────────┘       └───────────────┘
```

### Staged Mode Flow

```
1. User creates clone session, selects storage backend for staging
2. Controller provisions staging:
   - NFS: Creates directory path
   - iSCSI: Creates new LUN sized to source disk
3. Source node boots into deploy env
4. Source mounts staging (NFS) or connects to LUN (iSCSI)
5. Source streams disk to staging: dd | gzip > /mnt/staging/disk.raw.gz
6. Source reports complete, reboots to normal operation
7. Target node boots (can be immediately or later)
8. Target mounts same staging volume
9. Target streams from staging to local disk
10. Target runs partition resize if needed
11. Target reports complete, controller cleans up staging
```

### Direct Mode Flow

```
1. Controller creates clone session, generates TLS certs for both nodes
2. Source boots into deploy env, fetches certs from controller
3. Source starts HTTPS server on port 9999
4. Source registers as ready (IP, port, disk size)
5. Controller notifies target: "Source ready at https://192.168.1.50:9999"
6. Target boots into deploy env, fetches certs
7. Target connects to source via mTLS
8. Clone streams peer-to-peer (controller not in data path)
9. Both nodes periodically POST progress to controller
10. If controller unreachable: queue updates, retry with backoff
11. On completion: target reboots, syncs final status when controller returns
```

---

## Certificate Authority

### CA Storage

```
/opt/pureboot/certs/
├── ca.crt          # CA certificate (public)
├── ca.key          # CA private key (protected, 600 perms)
└── ca.srl          # Serial number tracker
```

### Certificate Specifications

- **Algorithm**: ECDSA P-256 (small, fast)
- **CA cert validity**: 10 years (configurable)
- **Session certs validity**: 24 hours (covers long clones + retry buffer)
- **Key usage**: Server auth (source), Client auth (target), mutual TLS

### Certificate Delivery

1. Boot params include: `pureboot.session_id={id}` and `pureboot.server={url}`
2. Node boots, calls `GET /api/v1/clone-sessions/{id}/certs?role=source|target`
3. Controller returns cert bundle (cert + key + CA) over HTTPS
4. Node loads certs into memory, starts TLS server/client

---

## Data Model

### New Tables

```sql
-- Clone session tracking
CREATE TABLE clone_sessions (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending, source_ready, cloning, completed, failed, cancelled

    clone_mode VARCHAR(10) NOT NULL DEFAULT 'staged',
    -- staged, direct

    source_node_id VARCHAR(36) NOT NULL REFERENCES nodes(id),
    target_node_id VARCHAR(36) REFERENCES nodes(id),
    source_device VARCHAR(50) NOT NULL DEFAULT '/dev/sda',
    target_device VARCHAR(50) NOT NULL DEFAULT '/dev/sda',

    -- Direct mode fields
    source_ip VARCHAR(45),
    source_port INTEGER DEFAULT 9999,
    source_cert_pem TEXT,
    source_key_pem TEXT,
    target_cert_pem TEXT,
    target_key_pem TEXT,

    -- Staged mode fields
    staging_backend_id VARCHAR(36) REFERENCES storage_backends(id),
    staging_path VARCHAR(500),
    staging_size_bytes BIGINT,
    staging_status VARCHAR(20),
    -- pending, provisioned, uploading, ready, downloading, cleanup, deleted

    -- Resize fields
    resize_mode VARCHAR(20) DEFAULT 'none',
    -- none, shrink_source, grow_target
    partition_plan_json TEXT,

    -- Progress tracking
    bytes_total BIGINT,
    bytes_transferred BIGINT DEFAULT 0,
    transfer_rate_bps BIGINT,

    -- Metadata
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR(255)
);

-- Cached disk/partition info from nodes
CREATE TABLE disk_info (
    id VARCHAR(36) PRIMARY KEY,
    node_id VARCHAR(36) NOT NULL REFERENCES nodes(id),
    device VARCHAR(50) NOT NULL,
    size_bytes BIGINT NOT NULL,
    model VARCHAR(255),
    serial VARCHAR(255),
    partition_table VARCHAR(10),
    -- gpt, mbr, unknown
    partitions_json TEXT,
    scanned_at TIMESTAMP NOT NULL,

    UNIQUE(node_id, device)
);

-- Queued partition operations
CREATE TABLE partition_operations (
    id VARCHAR(36) PRIMARY KEY,
    node_id VARCHAR(36) NOT NULL REFERENCES nodes(id),
    session_id VARCHAR(36) REFERENCES clone_sessions(id),
    device VARCHAR(50) NOT NULL,
    operation VARCHAR(20) NOT NULL,
    -- resize, create, delete, format, move, set_flag
    params_json TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending, running, completed, failed
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP
);

CREATE INDEX idx_partition_ops_node_status ON partition_operations(node_id, status);
```

### Partition JSON Structure

Inside `disk_info.partitions_json`:

```json
[
  {
    "number": 1,
    "start_bytes": 1048576,
    "end_bytes": 536870912,
    "size_bytes": 535822336,
    "type": "efi",
    "filesystem": "fat32",
    "label": "EFI",
    "flags": ["boot", "esp"],
    "used_bytes": 5242880,
    "mountpoint": null
  },
  {
    "number": 2,
    "start_bytes": 536870912,
    "end_bytes": 107374182400,
    "size_bytes": 106837311488,
    "type": "linux",
    "filesystem": "ext4",
    "label": "root",
    "flags": [],
    "used_bytes": 45097156608,
    "mountpoint": "/"
  }
]
```

### Partition Operation Params

```json
// Resize
{"partition": 2, "new_size_bytes": 85899345920}

// Create
{"start_bytes": 107374182400, "size_bytes": 21474836480, "type": "linux", "filesystem": "ext4", "label": "data"}

// Delete
{"partition": 3}

// Format
{"partition": 2, "filesystem": "ext4", "label": "root"}

// Set flag
{"partition": 1, "flag": "boot", "value": true}
```

---

## API Endpoints

### Clone Session Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/clone-sessions` | Create new clone session |
| `GET` | `/clone-sessions` | List all sessions (with filters) |
| `GET` | `/clone-sessions/{id}` | Get session details |
| `PATCH` | `/clone-sessions/{id}` | Update session (assign target, change settings) |
| `DELETE` | `/clone-sessions/{id}` | Cancel/delete session |
| `POST` | `/clone-sessions/{id}/start` | Start cloning (boots source node) |
| `GET` | `/clone-sessions/{id}/certs` | Get TLS certs for node (query: `role=source\|target`) |

### Clone Session Callbacks

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/clone-sessions/{id}/source-ready` | Source reports ready with IP |
| `POST` | `/clone-sessions/{id}/progress` | Progress update from source or target |
| `POST` | `/clone-sessions/{id}/complete` | Clone finished successfully |
| `POST` | `/clone-sessions/{id}/failed` | Clone failed with error |

### Disk & Partition Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/nodes/{id}/disks` | List disks on node (cached or live) |
| `GET` | `/nodes/{id}/disks/{device}` | Get disk details with partitions |
| `POST` | `/nodes/{id}/disks/scan` | Trigger fresh disk scan |
| `POST` | `/nodes/{id}/disks/{device}/operations` | Queue partition operation |
| `GET` | `/nodes/{id}/disks/{device}/operations` | List queued operations |
| `DELETE` | `/nodes/{id}/disks/{device}/operations/{op_id}` | Remove queued operation |
| `POST` | `/nodes/{id}/disks/{device}/apply` | Execute all queued operations |

### Clone Analysis Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/clone-sessions/{id}/analyze` | Compare source/target sizes, suggest resize plan |
| `GET` | `/clone-sessions/{id}/plan` | Get current resize plan |
| `PUT` | `/clone-sessions/{id}/plan` | Update resize plan |

### Schemas

```python
class CloneSessionCreate(BaseModel):
    name: str | None = None
    source_node_id: str
    target_node_id: str | None = None
    source_device: str = "/dev/sda"
    target_device: str = "/dev/sda"
    clone_mode: Literal["staged", "direct"] = "staged"
    staging_backend_id: str | None = None  # Required if mode=staged
    resize_mode: Literal["none", "shrink_source", "grow_target"] = "none"

class CloneSessionResponse(BaseModel):
    id: str
    name: str | None
    status: str
    clone_mode: str
    source_node_id: str
    source_node_name: str | None
    target_node_id: str | None
    target_node_name: str | None
    source_device: str
    target_device: str
    source_ip: str | None
    resize_mode: str
    bytes_total: int | None
    bytes_transferred: int
    transfer_rate_bps: int | None
    progress_percent: float
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

class CloneProgressUpdate(BaseModel):
    role: Literal["source", "target"]
    bytes_transferred: int
    transfer_rate_bps: int | None = None
    status: Literal["transferring", "verifying", "resizing"] | None = None

class DiskResponse(BaseModel):
    device: str
    size_bytes: int
    size_human: str
    model: str | None
    serial: str | None
    partition_table: str
    partitions: list[PartitionResponse]
    scanned_at: datetime

class PartitionResponse(BaseModel):
    number: int
    start_bytes: int
    end_bytes: int
    size_bytes: int
    size_human: str
    type: str
    filesystem: str | None
    label: str | None
    flags: list[str]
    used_bytes: int | None
    used_percent: float | None
    can_shrink: bool
    min_size_bytes: int | None

class PartitionOperationCreate(BaseModel):
    operation: Literal["resize", "create", "delete", "format", "move", "set_flag"]
    params: dict
```

### WebSocket Events

```python
# Clone events
{"type": "clone.started", "data": {"session_id": "...", "source_node_id": "...", "target_node_id": "..."}}
{"type": "clone.source_ready", "data": {"session_id": "...", "source_ip": "..."}}
{"type": "clone.progress", "data": {"session_id": "...", "bytes_transferred": 1073741824, "progress_percent": 25.5, "transfer_rate_bps": 104857600}}
{"type": "clone.completed", "data": {"session_id": "...", "duration_seconds": 3600}}
{"type": "clone.failed", "data": {"session_id": "...", "error": "..."}}

# Partition events
{"type": "partition.scan_complete", "data": {"node_id": "...", "device": "/dev/sda"}}
{"type": "partition.operation_started", "data": {"node_id": "...", "operation_id": "...", "operation": "resize"}}
{"type": "partition.operation_complete", "data": {"node_id": "...", "operation_id": "..."}}
{"type": "partition.operation_failed", "data": {"node_id": "...", "operation_id": "...", "error": "..."}}
```

---

## Deploy Environment

### Required Packages

| Package | Purpose |
|---------|---------|
| `openssl` | TLS for HTTPS server/client |
| `lighttpd` + `mod_openssl` | HTTPS server for disk streaming |
| `curl` | HTTPS client for callbacks and disk download |
| `parted` | Partition table manipulation |
| `e2fsprogs` | ext2/3/4 filesystem tools (resize2fs, e2fsck) |
| `ntfs-3g-progs` | NTFS resize (ntfsresize) |
| `btrfs-progs` | Btrfs tools |
| `xfsprogs` | XFS tools (xfs_growfs - grow only) |
| `dosfstools` | FAT32 tools |
| `lsblk`, `blkid` | Disk enumeration |
| `jq` | JSON parsing for API responses |
| `pv` | Progress monitoring for dd streams |
| `nfs-utils` | NFS client (staged mode) |
| `open-iscsi` | iSCSI initiator (staged mode) |

### Boot Modes

| Mode | Kernel Param | Purpose |
|------|--------------|---------|
| `clone_source_direct` | `pureboot.mode=clone_source_direct` | Serve disk via HTTPS |
| `clone_target_direct` | `pureboot.mode=clone_target_direct` | Stream from source via HTTPS |
| `clone_source_staged` | `pureboot.mode=clone_source_staged` | Upload disk to storage |
| `clone_target_staged` | `pureboot.mode=clone_target_staged` | Download from storage |
| `partition` | `pureboot.mode=partition` | Interactive partition tool |

### Script Structure

```
/usr/local/bin/
├── pureboot-deploy              # Main entrypoint (mode dispatcher)
├── pureboot-common.sh           # Shared functions
├── pureboot-clone-source-direct.sh
├── pureboot-clone-target-direct.sh
├── pureboot-clone-source-staged.sh
├── pureboot-clone-target-staged.sh
├── pureboot-partition.sh
└── pureboot-image.sh

/usr/local/lib/pureboot/
├── disk-scan.sh                 # Enumerate disks → JSON
├── partition-ops.sh             # Execute partition operations
├── tls-setup.sh                 # Fetch and configure TLS certs
└── offline-queue.sh             # Queue updates when controller unreachable
```

### Offline Resilience

```bash
QUEUE_DIR="/tmp/pureboot-queue"

queue_update() {
    local endpoint="$1"
    local payload="$2"
    local timestamp=$(date +%s)
    mkdir -p "$QUEUE_DIR"
    echo "$endpoint|$payload" > "$QUEUE_DIR/${timestamp}.pending"
}

flush_queue() {
    for f in "$QUEUE_DIR"/*.pending; do
        [ -f "$f" ] || continue
        local endpoint=$(cut -d'|' -f1 < "$f")
        local payload=$(cut -d'|' -f2- < "$f")
        if api_post "$endpoint" "$payload"; then
            rm "$f"
        fi
    done
}

api_post_resilient() {
    local endpoint="$1"
    local payload="$2"
    if ! api_post "$endpoint" "$payload"; then
        log "Controller unreachable, queueing update"
        queue_update "$endpoint" "$payload"
    fi
}
```

### Filesystem Resize Support

| Filesystem | Shrink | Grow | Online Grow |
|------------|--------|------|-------------|
| ext4       | Yes    | Yes  | Yes         |
| xfs        | No     | Yes  | Yes         |
| ntfs       | Yes    | Yes  | No          |
| btrfs      | Yes    | Yes  | Yes         |
| fat32      | Yes    | Yes  | No          |

---

## Frontend UI

### New Pages

| Page | Route | Purpose |
|------|-------|---------|
| Clone Sessions | `/clone` | List and manage clone sessions |
| Clone Wizard | `/clone/new` | Multi-step wizard to create clone |
| Clone Detail | `/clone/{id}` | Monitor active clone, view history |
| Partition Tool | `/nodes/{id}/disks` | View/edit partitions on a node |

### Clone Wizard Steps

1. **Select Mode**: Staged vs Direct
2. **Select Source**: Node and disk selection with partition preview
3. **Select Storage** (staged) or **Select Target** (direct)
4. **Resize Plan** (if size mismatch detected)
5. **Review & Start**: Summary with confirmation

### Component Structure

```
src/components/clone/
├── CloneWizard.tsx
├── CloneModeStep.tsx
├── CloneSourceStep.tsx
├── CloneStagingStep.tsx
├── CloneTargetStep.tsx
├── CloneResizeStep.tsx
├── CloneReviewStep.tsx
├── CloneSessionCard.tsx
├── CloneProgressView.tsx
└── CloneTimeline.tsx

src/components/disks/
├── DiskVisualizer.tsx
├── PartitionTable.tsx
├── PartitionResizeDialog.tsx
├── PartitionCreateDialog.tsx
├── PartitionFormatDialog.tsx
├── OperationQueue.tsx
└── DiskSelector.tsx
```

---

## Implementation Phases

### Phase 1: Core Infrastructure

**Backend:**
- CA certificate generation at startup (`src/core/ca.py`)
- CloneSession, DiskInfo, PartitionOperation database models
- Clone session CRUD endpoints
- Certificate issuance endpoint
- WebSocket events for clone status

**Deploy Environment:**
- Add TLS packages (openssl, curl with TLS)
- Add partition packages (parted, e2fsprogs, ntfs-3g-progs)
- Add storage packages (nfs-utils, open-iscsi)
- TLS setup script
- Offline queue script

**Frontend:**
- Clone sessions list page (empty state, basic list)
- CloneSession types and API client
- WebSocket event handlers for clone events

---

### Phase 2: Direct Mode Cloning

**Backend:**
- Clone session start endpoint (triggers source boot)
- Source ready callback with IP/cert registration
- Progress update endpoint with offline queue handling
- Complete/failed callbacks
- Target workflow auto-assignment when source ready

**Deploy Environment:**
- Direct mode source script
- Direct mode target script
- HTTPS server setup with lighttpd + TLS
- Progress reporting with `pv`
- Retry logic for controller callbacks

**Frontend:**
- Clone wizard: mode selection step
- Clone wizard: source selection step
- Clone wizard: target selection step (direct mode)
- Clone wizard: review and start step
- Clone detail page with live progress
- Clone timeline component

---

### Phase 3: Partition Management

**Backend:**
- Disk scan endpoint
- Disk/partition list endpoints
- Partition operation queue endpoints
- Apply operations endpoint
- Partition operation execution tracking
- WebSocket events for partition operations

**Deploy Environment:**
- Disk scan script (outputs JSON)
- Partition operations script
- Partition mode boot script
- Filesystem-aware resize (ext4, ntfs, xfs, btrfs)

**Frontend:**
- Partition tool page
- Disk visualizer component
- Partition table with actions
- Resize dialog with slider
- Create/delete/format dialogs
- Operation queue display
- Apply confirmation modal

---

### Phase 4: Staged Mode & Resize Integration

**Backend:**
- Staging volume provisioning (NFS path, iSCSI LUN)
- Staged mode clone flow
- Storage space check endpoint
- Staging cleanup logic
- Clone analysis endpoint
- Resize plan generation
- Pre-clone resize execution

**Deploy Environment:**
- Staged mode source script
- Staged mode target script
- NFS mount/unmount handling
- iSCSI discovery/login/logout handling
- Pre-clone partition resize integration

**Frontend:**
- Clone wizard: staging storage step
- Clone wizard: resize plan step
- Size mismatch detection and warning
- Resize plan editor
- Staged clone progress (upload → ready → download phases)
- Storage backend space indicator

---

## Phase Dependencies

```
Phase 1 (Infrastructure)
    │
    ├──► Phase 2 (Direct Cloning)
    │        │
    │        └──► Phase 4 (Staged + Resize)
    │                 ▲
    └──► Phase 3 (Partitions) ─────┘
```

Phase 3 can run in parallel with Phase 2, but Phase 4 needs both.

---

## References

- [Issue #46 - Partition Management Tool](https://github.com/mrveiss/pureboot/issues/46)
- [Issue #78 - Complete Live Disk Cloning](https://github.com/mrveiss/pureboot/issues/78)
- [Existing clone-target workflow](../../workflows/clone-target.yaml)
- [Deploy environment script](../../scripts/setup-deploy-env.sh)