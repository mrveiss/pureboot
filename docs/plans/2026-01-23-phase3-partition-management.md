# Phase 3: Partition Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a web-based GParted-style partition management tool for viewing and modifying disk partitions on PXE-booted nodes.

**Architecture:** Nodes boot into partition mode, deploy env scans disks and reports to controller, user queues operations via web UI, operations execute on node with progress reporting.

**Tech Stack:** Backend Python/FastAPI, deploy scripts with parted/resize2fs/ntfsresize, React frontend with disk visualizer

---

## Task 1: Disk Scan Script

**Files:**
- Create: `deploy/scripts/pureboot-disk-scan.sh`

**Step 1: Create the disk scan script**

```bash
#!/bin/bash
# PureBoot Disk Scan Script
# Outputs disk and partition information as JSON

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/pureboot-common.sh" ]]; then
    source "${SCRIPT_DIR}/pureboot-common.sh"
elif [[ -f "/usr/local/bin/pureboot-common.sh" ]]; then
    source "/usr/local/bin/pureboot-common.sh"
fi

# Scan a single disk and output JSON
scan_disk() {
    local device="$1"
    local disk_json=""

    # Get disk info
    local size_bytes model serial
    size_bytes=$(blockdev --getsize64 "$device" 2>/dev/null || echo "0")
    model=$(lsblk -dn -o MODEL "$device" 2>/dev/null | tr -d '"' | xargs)
    serial=$(lsblk -dn -o SERIAL "$device" 2>/dev/null | xargs)

    # Get partition table type
    local pttype
    pttype=$(blkid -o value -s PTTYPE "$device" 2>/dev/null || echo "unknown")

    # Scan partitions
    local partitions_json="[]"
    if command -v parted &>/dev/null; then
        partitions_json=$(scan_partitions "$device")
    fi

    # Output JSON
    cat <<EOF
{
    "device": "$device",
    "size_bytes": $size_bytes,
    "model": $(json_string "$model"),
    "serial": $(json_string "$serial"),
    "partition_table": "$pttype",
    "partitions": $partitions_json
}
EOF
}

# Scan partitions on a disk
scan_partitions() {
    local device="$1"
    local partitions="["
    local first=true

    # Use parted to get partition info
    while IFS=: read -r num start end size fs name flags; do
        [[ "$num" =~ ^[0-9]+$ ]] || continue

        # Convert to bytes (parted outputs in sectors or human readable)
        local start_bytes end_bytes size_bytes
        start_bytes=$(parse_size_to_bytes "$start")
        end_bytes=$(parse_size_to_bytes "$end")
        size_bytes=$(parse_size_to_bytes "$size")

        # Get filesystem type and usage
        local part_device="${device}${num}"
        [[ ! -b "$part_device" ]] && part_device="${device}p${num}"

        local fstype label used_bytes
        fstype=$(blkid -o value -s TYPE "$part_device" 2>/dev/null || echo "")
        label=$(blkid -o value -s LABEL "$part_device" 2>/dev/null || echo "")
        used_bytes=$(get_fs_usage "$part_device" "$fstype")

        # Determine partition type
        local ptype="linux"
        case "$fs" in
            fat*|FAT*) ptype="efi" ;;
            ntfs|NTFS) ptype="ntfs" ;;
            linux-swap*) ptype="swap" ;;
        esac

        # Can this partition shrink?
        local can_shrink=false
        local min_size=0
        case "$fstype" in
            ext4|ext3|ext2|ntfs|btrfs)
                can_shrink=true
                min_size=$((used_bytes + 104857600))  # used + 100MB buffer
                ;;
        esac

        # Parse flags
        local flags_json="[]"
        if [[ -n "$flags" ]]; then
            flags_json=$(echo "$flags" | tr ',' '\n' | jq -R . | jq -s .)
        fi

        $first || partitions+=","
        first=false

        partitions+=$(cat <<EOF
{
    "number": $num,
    "start_bytes": $start_bytes,
    "end_bytes": $end_bytes,
    "size_bytes": $size_bytes,
    "type": "$ptype",
    "filesystem": $(json_string "$fstype"),
    "label": $(json_string "$label"),
    "flags": $flags_json,
    "used_bytes": ${used_bytes:-null},
    "used_percent": $(calc_percent "$used_bytes" "$size_bytes"),
    "can_shrink": $can_shrink,
    "min_size_bytes": ${min_size:-null}
}
EOF
)
    done < <(parted -s "$device" unit B print 2>/dev/null | grep -E '^ *[0-9]')

    partitions+="]"
    echo "$partitions"
}

# Get filesystem usage in bytes
get_fs_usage() {
    local device="$1"
    local fstype="$2"

    case "$fstype" in
        ext4|ext3|ext2)
            local blocks used
            read -r _ blocks used _ < <(dumpe2fs -h "$device" 2>/dev/null | grep -E "Block (count|size):|Free blocks:" | awk '{print $NF}')
            # Simplified - just try df
            df -B1 "$device" 2>/dev/null | awk 'NR==2 {print $3}' || echo "null"
            ;;
        ntfs)
            ntfsinfo -m "$device" 2>/dev/null | awk '/Cluster Size|Volume Size|Free Clusters/' || echo "null"
            ;;
        *)
            echo "null"
            ;;
    esac
}

# Helper: Convert size string to bytes
parse_size_to_bytes() {
    local size="$1"
    # Remove 'B' suffix if present
    size="${size%B}"
    echo "${size%.*}"  # Remove decimal part
}

# Helper: JSON string (handles null)
json_string() {
    local val="$1"
    if [[ -z "$val" ]]; then
        echo "null"
    else
        echo "\"$val\""
    fi
}

# Helper: Calculate percentage
calc_percent() {
    local used="$1"
    local total="$2"
    if [[ -z "$used" || "$used" == "null" || "$total" -eq 0 ]]; then
        echo "null"
    else
        echo "scale=1; $used * 100 / $total" | bc
    fi
}

# Main: Scan all disks or specific device
main() {
    local target_device="${1:-}"

    if [[ -n "$target_device" ]]; then
        scan_disk "$target_device"
    else
        # Scan all block devices (exclude loops, ram, etc)
        echo "["
        local first=true
        for device in /dev/sd? /dev/nvme?n? /dev/vd?; do
            [[ -b "$device" ]] || continue
            $first || echo ","
            first=false
            scan_disk "$device"
        done
        echo "]"
    fi
}

main "$@"
```

**Step 2: Commit**

```bash
git add deploy/scripts/pureboot-disk-scan.sh
git commit -m "feat(partition): add disk scan script

Outputs disk and partition information as JSON:
- Disk size, model, serial, partition table type
- Partition boundaries, filesystem, usage
- Shrink capability and minimum size
- Parses parted output for accuracy"
```

---

## Task 2: Partition Operations Script

**Files:**
- Create: `deploy/scripts/pureboot-partition-ops.sh`

**Step 1: Create the partition operations script**

Script that executes partition operations (resize, create, delete, format, set_flag). Uses parted for partition table ops, and filesystem-specific tools for resize:
- ext4: e2fsck + resize2fs
- ntfs: ntfsresize
- xfs: xfs_growfs (grow only)
- btrfs: btrfs filesystem resize

Key functions:
- `op_resize`: Resize partition and filesystem
- `op_create`: Create new partition
- `op_delete`: Delete partition
- `op_format`: Format partition with filesystem
- `op_set_flag`: Set/clear partition flags
- `execute_operation`: Dispatcher that parses JSON and calls appropriate function

**Step 2: Commit**

```bash
git add deploy/scripts/pureboot-partition-ops.sh
git commit -m "feat(partition): add partition operations script

Executes partition operations with filesystem awareness:
- Resize with ext4/ntfs/xfs/btrfs support
- Create/delete partitions via parted
- Format with mkfs.ext4/mkfs.ntfs/etc
- Set/clear partition flags
- Reports progress and errors to controller"
```

---

## Task 3: Partition Mode Boot Script

**Files:**
- Create: `deploy/scripts/pureboot-partition.sh`

**Step 1: Create the partition mode script**

Main entry point when booting with `pureboot.mode=partition`:
1. Source common functions
2. Scan disks and report to controller
3. Poll controller for queued operations
4. Execute operations and report progress
5. Stay online until explicitly shutdown

**Step 2: Update build script to copy partition scripts**

Add to `deploy/build-deploy-image.sh`:
```bash
cp "${SCRIPT_DIR}/scripts/pureboot-disk-scan.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-partition-ops.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-partition.sh" "${ROOTFS_DIR}/usr/local/bin/"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-disk-scan.sh"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-partition-ops.sh"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-partition.sh"
```

**Step 3: Commit**

```bash
git add deploy/scripts/pureboot-partition.sh deploy/build-deploy-image.sh
git commit -m "feat(partition): add partition mode boot script

Main entry point for partition management:
- Scans disks and reports to controller
- Polls for queued operations
- Executes operations with progress reporting
- Stays online for interactive management"
```

---

## Task 4: Backend Disk Endpoints

**Files:**
- Create: `src/api/routes/disks.py`
- Modify: `src/main.py` (register router)

**Step 1: Create disk API router**

Endpoints:
- `GET /nodes/{node_id}/disks` - List disks on node (from cache)
- `GET /nodes/{node_id}/disks/{device}` - Get disk details with partitions
- `POST /nodes/{node_id}/disks/scan` - Trigger fresh disk scan (sends command to node)
- `POST /nodes/{node_id}/disks/report` - Receive scan results from node

**Step 2: Register router in main.py**

**Step 3: Commit**

```bash
git add src/api/routes/disks.py src/main.py
git commit -m "feat(partition): add disk scan API endpoints

Endpoints for disk management:
- GET /nodes/{id}/disks - list cached disks
- GET /nodes/{id}/disks/{device} - disk details
- POST /nodes/{id}/disks/scan - trigger scan
- POST /nodes/{id}/disks/report - receive results"
```

---

## Task 5: Backend Partition Operation Endpoints

**Files:**
- Modify: `src/api/routes/disks.py`

**Step 1: Add partition operation endpoints**

- `POST /nodes/{node_id}/disks/{device}/operations` - Queue operation
- `GET /nodes/{node_id}/disks/{device}/operations` - List queued operations
- `DELETE /nodes/{node_id}/disks/{device}/operations/{op_id}` - Remove queued operation
- `POST /nodes/{node_id}/disks/{device}/apply` - Execute all queued operations
- `POST /nodes/{node_id}/partition-operations/{op_id}/status` - Receive status update from node

**Step 2: Add WebSocket events**

Broadcast events:
- `partition.scan_complete`
- `partition.operation_started`
- `partition.operation_complete`
- `partition.operation_failed`

**Step 3: Commit**

```bash
git add src/api/routes/disks.py
git commit -m "feat(partition): add partition operation endpoints

Queue and execute partition operations:
- Queue operations with validation
- List/remove pending operations
- Apply all operations on device
- WebSocket events for real-time updates"
```

---

## Task 6: Partition Workflow YAML

**Files:**
- Create: `workflows/partition-management.yaml`

**Step 1: Create workflow definition**

```yaml
id: partition-management
name: Partition Management
description: Boot into deploy environment for interactive partition management

install_method: deploy

boot_params:
  pureboot.mode: partition

architecture: x86_64
boot_mode: uefi
```

**Step 2: Commit**

```bash
git add workflows/partition-management.yaml
git commit -m "feat(partition): add partition management workflow

Workflow definition for partition mode boot."
```

---

## Task 7: Frontend Partition Types and API

**Files:**
- Create: `frontend/src/types/partition.ts`
- Create: `frontend/src/api/disks.ts`
- Modify: `frontend/src/api/index.ts`

**Step 1: Create TypeScript types**

```typescript
export interface PartitionInfo {
  number: number
  start_bytes: number
  end_bytes: number
  size_bytes: number
  size_human?: string
  type: string
  filesystem: string | null
  label: string | null
  flags: string[]
  used_bytes: number | null
  used_percent: number | null
  can_shrink: boolean
  min_size_bytes: number | null
}

export interface DiskInfo {
  id: string
  node_id: string
  device: string
  size_bytes: number
  size_human: string
  model: string | null
  serial: string | null
  partition_table: string | null
  partitions: PartitionInfo[]
  scanned_at: string
}

export interface PartitionOperation {
  id: string
  node_id: string
  device: string
  operation: 'resize' | 'create' | 'delete' | 'format' | 'move' | 'set_flag'
  params: Record<string, unknown>
  sequence: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  error_message: string | null
  created_at: string
  executed_at: string | null
}

export type PartitionOperationType = PartitionOperation['operation']
```

**Step 2: Create API client**

**Step 3: Commit**

```bash
git add frontend/src/types/partition.ts frontend/src/api/disks.ts frontend/src/api/index.ts
git commit -m "feat(partition): add frontend types and API client

Types and API for partition management:
- DiskInfo, PartitionInfo types
- PartitionOperation type
- Disk listing and scan API
- Operation queue API"
```

---

## Task 8: Frontend Disk Hooks

**Files:**
- Create: `frontend/src/hooks/useDisks.ts`
- Create: `frontend/src/hooks/usePartitionUpdates.ts`
- Modify: `frontend/src/hooks/index.ts`
- Modify: `frontend/src/hooks/useWebSocket.ts` (add partition events)

**Step 1: Create React Query hooks**

```typescript
export const diskKeys = {
  all: ['disks'] as const,
  byNode: (nodeId: string) => [...diskKeys.all, nodeId] as const,
  disk: (nodeId: string, device: string) => [...diskKeys.byNode(nodeId), device] as const,
  operations: (nodeId: string, device: string) => [...diskKeys.disk(nodeId, device), 'operations'] as const,
}

export function useNodeDisks(nodeId: string)
export function useDisk(nodeId: string, device: string)
export function usePartitionOperations(nodeId: string, device: string)
export function useScanDisks()
export function useQueueOperation()
export function useRemoveOperation()
export function useApplyOperations()
```

**Step 2: Create WebSocket update hook**

**Step 3: Add partition events to WebSocket types**

**Step 4: Commit**

```bash
git add frontend/src/hooks/useDisks.ts frontend/src/hooks/usePartitionUpdates.ts frontend/src/hooks/index.ts frontend/src/hooks/useWebSocket.ts
git commit -m "feat(partition): add React Query hooks for disks

Hooks for disk and partition management:
- useNodeDisks, useDisk for disk info
- usePartitionOperations for operation queue
- useScanDisks, useQueueOperation, useApplyOperations mutations
- usePartitionUpdates for real-time WebSocket updates"
```

---

## Task 9: Disk Visualizer Component

**Files:**
- Create: `frontend/src/components/disks/DiskVisualizer.tsx`

**Step 1: Create disk visualizer component**

Visual representation of disk with partitions:
- Horizontal bar showing disk with colored partition segments
- Partition labels with filesystem type and size
- Color coding by partition type (EFI=blue, Linux=green, Swap=orange, NTFS=purple, Free=gray)
- Click to select partition
- Tooltips with detailed info

**Step 2: Commit**

```bash
git add frontend/src/components/disks/DiskVisualizer.tsx
git commit -m "feat(partition): add disk visualizer component

Visual disk representation with:
- Proportional partition segments
- Color coding by type
- Click to select
- Detailed tooltips"
```

---

## Task 10: Partition Table Component

**Files:**
- Create: `frontend/src/components/disks/PartitionTable.tsx`

**Step 1: Create partition table component**

Table showing all partitions with:
- Columns: #, Start, End, Size, Type, Filesystem, Label, Flags, Used
- Row actions: Resize, Format, Delete, Set Flags
- Selected row highlighting
- Disabled actions when inappropriate (can't shrink XFS, etc)

**Step 2: Commit**

```bash
git add frontend/src/components/disks/PartitionTable.tsx
git commit -m "feat(partition): add partition table component

Partition listing with:
- Detailed partition information
- Action buttons per partition
- Selection highlighting
- Smart action availability"
```

---

## Task 11: Operation Dialogs

**Files:**
- Create: `frontend/src/components/disks/ResizeDialog.tsx`
- Create: `frontend/src/components/disks/FormatDialog.tsx`
- Create: `frontend/src/components/disks/CreatePartitionDialog.tsx`
- Create: `frontend/src/components/disks/OperationQueue.tsx`

**Step 1: Create resize dialog**

- Slider for new size (respects min/max)
- Before/after visualization
- Shows filesystem type and shrink capability
- Warns about data loss potential

**Step 2: Create format dialog**

- Filesystem type selector (ext4, xfs, ntfs, fat32, swap)
- Label input
- Warning about data loss

**Step 3: Create partition dialog**

- Start/end or size input
- Filesystem type
- Partition type (primary, logical for MBR)

**Step 4: Create operation queue display**

- List of pending operations
- Reorder/remove capabilities
- Status indicators

**Step 5: Commit**

```bash
git add frontend/src/components/disks/ResizeDialog.tsx frontend/src/components/disks/FormatDialog.tsx frontend/src/components/disks/CreatePartitionDialog.tsx frontend/src/components/disks/OperationQueue.tsx
git commit -m "feat(partition): add partition operation dialogs

Dialogs for partition operations:
- Resize with slider and visualization
- Format with filesystem selection
- Create partition wizard
- Operation queue management"
```

---

## Task 12: Partition Tool Page

**Files:**
- Create: `frontend/src/pages/PartitionTool.tsx`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/pages/index.ts`

**Step 1: Create main partition tool page**

Page layout:
- Header with node info and refresh button
- Disk selector (if multiple disks)
- DiskVisualizer component
- PartitionTable component
- OperationQueue component
- Apply button with confirmation modal

**Step 2: Add routes**

```tsx
{ path: 'nodes/:nodeId/disks', element: <PartitionTool /> }
```

**Step 3: Commit**

```bash
git add frontend/src/pages/PartitionTool.tsx frontend/src/router.tsx frontend/src/pages/index.ts
git commit -m "feat(partition): add partition tool page

Main partition management interface:
- Disk selection and visualization
- Partition table with actions
- Operation queue display
- Apply with confirmation"
```

---

## Task 13: Add Partition Link to Node Detail

**Files:**
- Modify: `frontend/src/pages/NodeDetail.tsx`

**Step 1: Add link to partition tool**

Add a "Manage Partitions" button that links to `/nodes/{nodeId}/disks` when node is in a state that supports partition management (discovered, active).

**Step 2: Commit**

```bash
git add frontend/src/pages/NodeDetail.tsx
git commit -m "feat(partition): add partition tool link to node detail

Adds 'Manage Partitions' button to node detail page."
```

---

## Summary

Phase 3 implements partition management with:

**Deploy Environment (3 tasks):**
1. Disk scan script
2. Partition operations script
3. Partition mode boot script

**Backend (3 tasks):**
4. Disk endpoints
5. Partition operation endpoints
6. Partition workflow YAML

**Frontend (7 tasks):**
7. Types and API client
8. React Query hooks
9. Disk visualizer component
10. Partition table component
11. Operation dialogs
12. Partition tool page
13. Node detail link

Total: 13 tasks
