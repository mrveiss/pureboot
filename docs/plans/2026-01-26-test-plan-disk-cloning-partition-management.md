# Test Plan: Disk Cloning & Partition Management

**PR:** #90
**Issues:** #46 (Partition Management), #78 (Live Disk Cloning)
**Date:** 2026-01-26

## Prerequisites

### Hardware Requirements
- **Controller**: Server running PureBoot controller application
- **Source Node**: Physical or virtual machine with bootable disk
- **Target Node**: Physical or virtual machine for cloning target
- **Storage Backend** (for staged mode): NFS server or iSCSI target

### Software Requirements
- PureBoot controller deployed and running
- Deploy image built with clone and partition scripts
- Storage backend configured (for staged mode tests)

---

## Test Categories

### 1. Direct Mode Cloning Tests

#### 1.1 Basic Direct Clone
**Objective:** Verify peer-to-peer cloning works between two nodes

**Steps:**
1. Register two nodes in PureBoot (source and target)
2. Navigate to Clone Sessions → Create New
3. Select "Direct" clone mode
4. Select source node and target node
5. Select source device (e.g., `/dev/sda`)
6. Click "Create Clone Session"
7. Start the clone session
8. Observe source node boots into clone-source-direct workflow
9. Observe target node boots into clone-target-direct workflow
10. Monitor progress in Clone Detail page
11. Wait for completion

**Expected Results:**
- [ ] Clone session created with status "pending"
- [ ] TLS certificates generated for both nodes
- [ ] Source node reports IP and port when ready
- [ ] Target connects to source via mTLS
- [ ] Progress updates appear in real-time
- [ ] Clone completes with status "completed"
- [ ] Target disk contains exact copy of source

#### 1.2 Direct Clone - Source Offline
**Objective:** Verify error handling when source goes offline

**Steps:**
1. Start a direct clone session
2. After source reports ready, forcefully shutdown source
3. Observe target behavior

**Expected Results:**
- [ ] Target detects connection loss
- [ ] Session status updates to "failed"
- [ ] Error message indicates source disconnection

#### 1.3 Direct Clone - Controller Offline Resilience
**Objective:** Verify cloning continues if controller becomes unavailable

**Steps:**
1. Start direct clone session
2. Once cloning begins (progress > 10%), stop the controller
3. Wait for clone to complete on nodes
4. Restart controller

**Expected Results:**
- [ ] Nodes queue progress updates when controller unreachable
- [ ] Clone completes without controller
- [ ] Queued updates sync when controller returns

---

### 2. Staged Mode Cloning Tests

#### 2.1 NFS Staged Clone
**Objective:** Verify cloning via NFS storage backend

**Preconditions:**
- NFS storage backend configured and online

**Steps:**
1. Navigate to Clone Sessions → Create New
2. Select "Staged" clone mode
3. Select source node
4. Select NFS storage backend
5. Create session (target can be assigned later)
6. Start clone session
7. Observe source uploads to NFS
8. Once staging_status = "ready", assign target node
9. Start target download
10. Monitor progress

**Expected Results:**
- [ ] Source mounts NFS share successfully
- [ ] Disk image uploads with compression
- [ ] staging_status transitions: uploading → ready
- [ ] Target mounts same NFS share
- [ ] Target downloads and restores image
- [ ] Clone completes successfully

#### 2.2 iSCSI Staged Clone
**Objective:** Verify cloning via iSCSI storage backend

**Preconditions:**
- iSCSI target configured with available LUNs

**Steps:**
1. Configure iSCSI storage backend
2. Create staged clone session with iSCSI backend
3. Boot source to upload
4. Boot target to download

**Expected Results:**
- [ ] Source connects to iSCSI target
- [ ] Data streams to iSCSI LUN
- [ ] Target connects to same LUN
- [ ] Data restores to local disk

#### 2.3 One-to-Many Staged Clone
**Objective:** Verify multiple targets can clone from single staged image

**Steps:**
1. Complete staged clone with first target
2. Keep staging intact (don't cleanup)
3. Create new session with same source, different target
4. Boot second target

**Expected Results:**
- [ ] Second target can download from existing staging
- [ ] Both targets have identical disk content

---

### 3. Partition Management Tests

#### 3.1 Disk Scan
**Objective:** Verify disk scanning and partition detection

**Steps:**
1. Boot node into partition-management workflow
2. Open Partition Tool page for the node
3. Click "Scan Disks"

**Expected Results:**
- [ ] All disks detected (size, model, serial)
- [ ] Partition table type identified (GPT/MBR)
- [ ] Partitions listed with correct sizes
- [ ] Filesystems detected (ext4, xfs, ntfs, etc.)
- [ ] Usage percentages calculated for mounted filesystems

#### 3.2 Partition Visualization
**Objective:** Verify GParted-style visual representation

**Steps:**
1. Open Partition Tool for a node with multiple partitions
2. Observe disk visualizer

**Expected Results:**
- [ ] Partitions shown as colored blocks
- [ ] Block widths proportional to partition sizes
- [ ] Unallocated space shown in gray
- [ ] Filesystem types indicated by color
- [ ] Partition numbers displayed
- [ ] Click on partition selects it

#### 3.3 Resize Partition
**Objective:** Verify partition resize operation

**Preconditions:**
- Node booted into partition mode
- Disk has resizable partition (can_shrink = true)

**Steps:**
1. Select a resizable partition
2. Click "Resize"
3. Enter new size (smaller than current)
4. Confirm operation
5. Verify operation queued
6. Click "Apply Operations"
7. Confirm apply

**Expected Results:**
- [ ] Resize dialog shows min/max constraints
- [ ] Operation queued with "pending" status
- [ ] Apply executes filesystem resize first
- [ ] Then partition table resize
- [ ] Operation completes successfully
- [ ] Rescan shows new partition size

#### 3.4 Format Partition
**Objective:** Verify partition format operation

**Steps:**
1. Select a partition
2. Click "Format"
3. Select filesystem type (e.g., ext4)
4. Enter optional label
5. Type "FORMAT" to confirm
6. Queue and apply operation

**Expected Results:**
- [ ] Warning about data loss displayed
- [ ] Confirmation required
- [ ] Format operation executes
- [ ] New filesystem created with label

#### 3.5 Create Partition
**Objective:** Verify partition creation in unallocated space

**Preconditions:**
- Disk has unallocated space

**Steps:**
1. Click "Create Partition"
2. Select unallocated region
3. Enter size or use full space
4. Select filesystem type
5. Queue and apply

**Expected Results:**
- [ ] New partition created
- [ ] Filesystem formatted
- [ ] Partition appears in visualizer

#### 3.6 Delete Partition
**Objective:** Verify partition deletion

**Steps:**
1. Select a non-boot partition
2. Click "Delete"
3. Confirm deletion
4. Apply operation

**Expected Results:**
- [ ] Partition removed from partition table
- [ ] Space becomes unallocated
- [ ] Visualizer updates

---

### 4. Resize Integration Tests

#### 4.1 Clone to Smaller Disk (Shrink Source)
**Objective:** Verify cloning when target disk is smaller than source

**Preconditions:**
- Source disk: 100GB with 40GB used
- Target disk: 60GB

**Steps:**
1. Create clone session with these nodes
2. Click "Analyze"
3. Review suggested resize plan
4. Adjust plan if needed in editor
5. Save plan
6. Start clone with shrink_source mode

**Expected Results:**
- [ ] Analysis detects size difference
- [ ] Resize plan suggests shrinking last partition
- [ ] Plan shows feasibility (can fit in 60GB)
- [ ] Source partitions shrink before upload/transfer
- [ ] Clone completes
- [ ] Target boots successfully

#### 4.2 Clone to Larger Disk (Grow Target)
**Objective:** Verify partition expansion after cloning

**Preconditions:**
- Source disk: 100GB
- Target disk: 200GB

**Steps:**
1. Create clone session
2. Select grow_target resize mode
3. Execute clone
4. Verify partitions expand

**Expected Results:**
- [ ] Clone transfers data
- [ ] Target partitions expand to fill disk
- [ ] Filesystem resizes correctly
- [ ] Target boots with full disk capacity

#### 4.3 Resize Plan Editor
**Objective:** Verify manual resize plan modification

**Steps:**
1. Create clone session with different disk sizes
2. Run analysis
3. Open resize plan editor
4. Manually adjust partition sizes
5. Verify feasibility indicator
6. Save modified plan

**Expected Results:**
- [ ] Editor shows visual disk comparison
- [ ] Partition sizes editable
- [ ] Infeasible plans flagged (total > target)
- [ ] Modified plan saved and used

---

### 5. Frontend Tests

#### 5.1 Clone Sessions List
- [ ] Sessions list loads
- [ ] Status filters work
- [ ] Mode filters work (direct/staged)
- [ ] Create button navigates to wizard

#### 5.2 Clone Wizard
- [ ] Mode selection works
- [ ] Storage backend dropdown shows only NFS/iSCSI for staged
- [ ] Source/target node selection works
- [ ] Validation prevents same source/target
- [ ] Direct mode requires target node
- [ ] Staged mode requires storage backend
- [ ] Form submits and navigates to detail

#### 5.3 Clone Detail Page
- [ ] Session info displays correctly
- [ ] Progress bar updates in real-time
- [ ] Staged mode shows phase indicators
- [ ] Resize plan editor accessible when applicable
- [ ] Error messages display on failure

#### 5.4 Partition Tool Page
- [ ] Disk selector works with multiple disks
- [ ] Visualizer renders partitions
- [ ] Partition table shows all details
- [ ] Action buttons work (resize, format, delete)
- [ ] Operation queue displays pending operations
- [ ] Apply button executes queue

---

### 6. Error Handling Tests

#### 6.1 Invalid Node Selection
- [ ] Cannot create session with offline nodes
- [ ] Cannot select same node as source and target
- [ ] Validation messages display

#### 6.2 Storage Backend Errors
- [ ] Error when NFS mount fails
- [ ] Error when iSCSI login fails
- [ ] Cleanup on staging errors

#### 6.3 Clone Failures
- [ ] Disk read errors reported
- [ ] Network interruption handled
- [ ] Insufficient space detected
- [ ] Failed status with error message

#### 6.4 Partition Operation Failures
- [ ] Resize below minimum fails gracefully
- [ ] Format of mounted partition prevented
- [ ] Invalid parameters rejected

---

## Sign-off

| Test Category | Tester | Date | Pass/Fail |
|---------------|--------|------|-----------|
| Direct Mode Cloning | | | |
| Staged Mode Cloning | | | |
| Partition Management | | | |
| Resize Integration | | | |
| Frontend | | | |
| Error Handling | | | |

---

## Notes

- All tests should be performed on the target test infrastructure, not the development host
- Ensure backups before testing on systems with important data
- Monitor controller logs during testing: `journalctl -u pureboot -f`
