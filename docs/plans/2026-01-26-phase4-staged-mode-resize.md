# Phase 4: Staged Mode & Resize Integration

**Date:** 2026-01-26
**Status:** In Progress
**Dependencies:** Phase 1 (Infrastructure), Phase 2 (Direct Cloning), Phase 3 (Partitions)

## Overview

Phase 4 completes the disk cloning feature by adding:
1. **Staged Mode Cloning** - Clone via intermediate storage (NFS/iSCSI) for one-to-many and offline scenarios
2. **Resize Integration** - Analyze disk sizes and automatically shrink/grow partitions for different-sized disks

## Staged Mode Flow

```
Source → Storage Backend → Target(s)
         (NFS or iSCSI)
```

1. User creates clone session with `clone_mode: "staged"` and selects storage backend
2. Controller provisions staging space (NFS directory or iSCSI LUN)
3. Source boots, uploads disk image to staging
4. Source completes, can reboot to normal operation
5. Target(s) boot (can be immediate or delayed)
6. Target downloads from staging, writes to local disk
7. Optional: resize partitions on target
8. Controller cleans up staging after completion

## Implementation Tasks

### Task 1: Storage Backend Database Model
**Files:**
- Modify: `src/db/models.py` - Add StorageBackend model
- Modify: `src/api/schemas.py` - Add storage backend schemas

**StorageBackend model:**
```python
class StorageBackend(Base):
    __tablename__ = "storage_backends"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    backend_type: Mapped[str] = mapped_column(String(20), nullable=False)  # nfs, iscsi

    # NFS config
    nfs_server: Mapped[str | None] = mapped_column(String(255))
    nfs_export: Mapped[str | None] = mapped_column(String(500))
    nfs_options: Mapped[str | None] = mapped_column(String(255))

    # iSCSI config
    iscsi_target: Mapped[str | None] = mapped_column(String(255))
    iscsi_portal: Mapped[str | None] = mapped_column(String(255))
    iscsi_username: Mapped[str | None] = mapped_column(String(255))
    iscsi_password: Mapped[str | None] = mapped_column(String(255))

    # Capacity tracking
    total_bytes: Mapped[int | None] = mapped_column(BigInteger)
    available_bytes: Mapped[int | None] = mapped_column(BigInteger)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
```

### Task 2: Storage Backend API
**Files:**
- Create: `src/api/routes/storage_backends.py`
- Modify: `src/main.py` - Register router

**Endpoints:**
- `GET /storage-backends` - List all storage backends
- `GET /storage-backends/{id}` - Get backend details
- `POST /storage-backends` - Create new backend
- `PUT /storage-backends/{id}` - Update backend
- `DELETE /storage-backends/{id}` - Delete backend
- `POST /storage-backends/{id}/test` - Test connectivity
- `GET /storage-backends/{id}/space` - Get available space

### Task 3: Clone Session Staging Fields
**Files:**
- Modify: `src/db/models.py` - Add staging fields to CloneSession
- Modify: `src/api/schemas.py` - Update clone session schemas
- Modify: `src/api/routes/clone.py` - Support staged mode creation

**New fields on CloneSession:**
- `staging_backend_id` - FK to storage_backends
- `staging_path` - Path within storage backend
- `staging_size_bytes` - Size of staged image
- `staging_status` - pending, provisioning, uploading, ready, downloading, cleanup, deleted

### Task 4: Staging Provisioning Logic
**Files:**
- Create: `src/services/staging.py` - Staging provisioning service

**Functions:**
- `provision_nfs_staging(session, backend)` - Create NFS directory
- `provision_iscsi_staging(session, backend, size_bytes)` - Create iSCSI LUN
- `cleanup_staging(session)` - Remove staging resources
- `get_staging_mount_info(session)` - Return mount instructions for nodes

### Task 5: Clone Analysis & Resize Plan Endpoints
**Files:**
- Modify: `src/api/routes/clone.py` - Add analysis endpoints
- Create: `src/services/resize_plan.py` - Resize planning logic

**Endpoints:**
- `POST /clone-sessions/{id}/analyze` - Compare source/target disk sizes, generate resize plan
- `GET /clone-sessions/{id}/plan` - Get current resize plan
- `PUT /clone-sessions/{id}/plan` - Update resize plan (user modifications)

**Resize plan schema:**
```python
class PartitionPlan(BaseModel):
    partition: int
    current_size_bytes: int
    new_size_bytes: int
    filesystem: str | None
    action: Literal["keep", "shrink", "grow", "delete"]

class ResizePlan(BaseModel):
    source_disk_bytes: int
    target_disk_bytes: int
    resize_mode: Literal["none", "shrink_source", "grow_target"]
    partitions: list[PartitionPlan]
    feasible: bool
    error_message: str | None
```

### Task 6: Staged Mode Source Script
**Files:**
- Create: `deploy/scripts/pureboot-clone-source-staged.sh`
- Modify: `deploy/build-deploy-image.sh` - Include new script

**Script flow:**
1. Fetch session info and staging mount details from controller
2. Mount NFS share or connect to iSCSI LUN
3. Execute pre-clone resize if `resize_mode == "shrink_source"`
4. Stream disk to staging: `dd if=/dev/sda | gzip > /mnt/staging/disk.raw.gz`
5. Report progress periodically
6. Unmount/disconnect staging
7. Report completion

### Task 7: Staged Mode Target Script
**Files:**
- Create: `deploy/scripts/pureboot-clone-target-staged.sh`
- Modify: `deploy/build-deploy-image.sh` - Include new script

**Script flow:**
1. Fetch session info and staging mount details
2. Mount NFS share or connect to iSCSI LUN
3. Stream from staging to disk: `gunzip -c /mnt/staging/disk.raw.gz | dd of=/dev/sda`
4. Report progress periodically
5. Execute post-clone resize if `resize_mode == "grow_target"`
6. Unmount/disconnect staging
7. Report completion

### Task 8: NFS/iSCSI Mount Helpers
**Files:**
- Modify: `deploy/scripts/pureboot-common.sh` - Add mount/unmount functions

**Functions:**
- `mount_nfs(server, export, mountpoint, options)` - Mount NFS share
- `unmount_nfs(mountpoint)` - Unmount NFS
- `iscsi_login(target, portal, username, password)` - iSCSI login
- `iscsi_logout(target)` - iSCSI logout
- `get_iscsi_device(target)` - Find iSCSI device path

### Task 9: Pre/Post Clone Resize Integration
**Files:**
- Modify: `deploy/scripts/pureboot-clone-source-staged.sh` - Pre-clone shrink
- Modify: `deploy/scripts/pureboot-clone-target-staged.sh` - Post-clone grow

**Integration:**
- Use partition operations from Phase 3 scripts
- Fetch resize plan from controller
- Execute resize operations before/after cloning

### Task 10: Mode Dispatcher Update
**Files:**
- Modify: `deploy/build-deploy-image.sh` - Add staged mode dispatch

**Modes:**
- `clone-source-direct` → `pureboot-clone-source-direct.sh`
- `clone-target-direct` → `pureboot-clone-target-direct.sh`
- `clone-source-staged` → `pureboot-clone-source-staged.sh`
- `clone-target-staged` → `pureboot-clone-target-staged.sh`
- `partition` → `pureboot-partition.sh`

### Task 11: Staged Clone Workflow YAMLs
**Files:**
- Create: `workflows/clone-source-staged.yaml`
- Create: `workflows/clone-target-staged.yaml`

### Task 12: Frontend Storage Backend Types & API
**Files:**
- Create: `frontend/src/types/storage.ts`
- Create: `frontend/src/api/storageBackends.ts`
- Modify: `frontend/src/api/index.ts` - Export new API

### Task 13: Frontend Storage Backend Hooks
**Files:**
- Create: `frontend/src/hooks/useStorageBackends.ts`
- Modify: `frontend/src/hooks/index.ts` - Export new hooks

### Task 14: Frontend Storage Backend Management Page
**Files:**
- Create: `frontend/src/pages/StorageBackends.tsx`
- Create: `frontend/src/components/storage/StorageBackendForm.tsx`
- Modify: `frontend/src/router.tsx` - Add route
- Modify: `frontend/src/components/layout/Sidebar.tsx` - Add nav link

### Task 15: Frontend Clone Wizard Enhancement
**Files:**
- Modify: `frontend/src/pages/CloneSessions.tsx` - Staged mode option
- Create: `frontend/src/components/clone/CloneWizard.tsx` - Multi-step wizard
- Create: `frontend/src/components/clone/StorageStep.tsx` - Storage selection
- Create: `frontend/src/components/clone/ResizePlanStep.tsx` - Resize planning

### Task 16: Frontend Resize Plan Editor
**Files:**
- Create: `frontend/src/components/clone/ResizePlanEditor.tsx`
- Visual editor for partition resize plan
- Show source/target disk comparison
- Allow manual adjustment of partition sizes

### Task 17: Frontend Staged Progress Display
**Files:**
- Modify: `frontend/src/pages/CloneDetail.tsx` - Staged progress phases
- Show: provisioning → uploading → ready → downloading → cleanup phases
- Different progress bars for upload vs download

## Task Dependencies

```
Task 1 (DB Model)
    │
    ├──► Task 2 (API) ──► Task 14 (Frontend Page)
    │                          │
    │                          └──► Task 15 (Wizard)
    │
    └──► Task 3 (Session Fields) ──► Task 4 (Provisioning)
                                          │
                                          ├──► Task 6 (Source Script)
                                          │         │
                                          │         └──► Task 9 (Resize)
                                          │
                                          └──► Task 7 (Target Script)
                                                    │
                                                    └──► Task 9 (Resize)

Task 5 (Analysis) ──► Task 16 (Resize Editor)

Task 8 (Mount Helpers) ──► Task 6, Task 7

Task 10 (Dispatcher) ──► Task 11 (Workflows)

Task 12, 13 (Frontend Types) ──► Task 14, 15, 16, 17
```

## Execution Order

**Batch 1 (Backend Foundation):**
- Task 1: Storage Backend Database Model
- Task 5: Clone Analysis & Resize Plan Endpoints

**Batch 2 (Backend API & Services):**
- Task 2: Storage Backend API
- Task 3: Clone Session Staging Fields
- Task 4: Staging Provisioning Logic

**Batch 3 (Deploy Scripts):**
- Task 8: NFS/iSCSI Mount Helpers
- Task 6: Staged Mode Source Script
- Task 7: Staged Mode Target Script
- Task 9: Pre/Post Clone Resize Integration
- Task 10: Mode Dispatcher Update
- Task 11: Staged Clone Workflow YAMLs

**Batch 4 (Frontend):**
- Task 12: Frontend Storage Backend Types & API
- Task 13: Frontend Storage Backend Hooks
- Task 14: Frontend Storage Backend Management Page
- Task 15: Frontend Clone Wizard Enhancement
- Task 16: Frontend Resize Plan Editor
- Task 17: Frontend Staged Progress Display

## Acceptance Criteria

1. Users can configure NFS and iSCSI storage backends
2. Clone sessions can be created in staged mode with storage backend selection
3. Source nodes can upload disk images to staging storage
4. Target nodes can download from staging and restore to local disk
5. Different-sized disk cloning works with automatic resize planning
6. Users can manually adjust resize plans before cloning
7. Staged clone progress shows distinct upload/download phases
8. Staging cleanup happens automatically after completion
