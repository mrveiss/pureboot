#!/bin/bash
# PureBoot Staged Mode Clone Source Script
# This script runs on a source node to upload its disk image to staging storage.
# The disk is streamed using dd and optionally compressed with gzip before uploading.
# Supports NFS and iSCSI staging backends.

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_MOUNTPOINT="/mnt/staging"
PROGRESS_FIFO="/tmp/pureboot-progress"

# Progress reporting interval in seconds
PROGRESS_INTERVAL=5

# Default block size for dd operations
DD_BLOCK_SIZE="4M"

# Compression level for gzip (1-9, 6 is default balance)
GZIP_LEVEL=6

# =============================================================================
# Source common functions
# =============================================================================

# Try multiple locations for common script
if [[ -f "${SCRIPT_DIR}/pureboot-common.sh" ]]; then
    source "${SCRIPT_DIR}/pureboot-common.sh"
elif [[ -f "/usr/local/bin/pureboot-common.sh" ]]; then
    source "/usr/local/bin/pureboot-common.sh"
else
    echo "ERROR: Cannot find pureboot-common.sh"
    exit 1
fi

# =============================================================================
# Global variables
# =============================================================================

# Session info (populated by fetch_session_info)
SESSION_STATUS=""
RESIZE_MODE=""
COMPRESSION_ENABLED="true"
IMAGE_FILENAME=""

# Staging info (populated by fetch_staging_info)
STAGING_TYPE=""      # "nfs" or "iscsi"
STAGING_SERVER=""    # NFS server or iSCSI target portal
STAGING_PATH=""      # NFS export path or iSCSI target IQN
STAGING_LUN=""       # iSCSI LUN number
STAGING_DEVICE=""    # iSCSI device path after login

# Disk info
DISK_SIZE=0
DISK_SIZE_HUMAN=""

# Transfer tracking
TRANSFER_START_TIME=0
BYTES_WRITTEN=0
LAST_PROGRESS_TIME=0

# =============================================================================
# Cleanup function
# =============================================================================

cleanup() {
    log "Cleaning up..."

    # Remove progress FIFO if exists
    if [[ -p "${PROGRESS_FIFO}" ]]; then
        rm -f "${PROGRESS_FIFO}"
    fi

    # Unmount staging if still mounted
    if mountpoint -q "${STAGING_MOUNTPOINT}" 2>/dev/null; then
        log "Unmounting staging storage..."
        unmount_staging_storage
    fi

    # Disconnect iSCSI if connected
    if [[ "${STAGING_TYPE}" == "iscsi" && -n "${STAGING_PATH}" ]]; then
        log "Disconnecting iSCSI session..."
        disconnect_iscsi_session || true
    fi

    # Flush any remaining queued updates
    flush_queue

    log "Cleanup complete"
}

# Set up cleanup trap
trap cleanup EXIT INT TERM

# =============================================================================
# Error handling function
# =============================================================================

report_failed() {
    local error_message="$1"
    local error_code="${2:-1}"

    log_error "${error_message}"

    local data
    data=$(cat << EOF
{
    "role": "source",
    "error_message": "${error_message}",
    "error_code": "${error_code}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    api_post_resilient "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/failed" "${data}"
}

# =============================================================================
# Update staging status
# =============================================================================

update_staging_status() {
    local status="$1"
    local message="${2:-}"

    log "Updating staging status to: ${status}"

    local data
    data=$(cat << EOF
{
    "status": "${status}",
    "message": "${message}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    if api_post "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/staging-status" "${data}"; then
        log_debug "Staging status updated successfully"
    else
        log_warn "Failed to update staging status"
        queue_update "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/staging-status" "${data}"
    fi
}

# =============================================================================
# Report transfer progress to controller
# =============================================================================

report_upload_progress() {
    local bytes_written="$1"
    local bytes_total="$2"
    local transfer_rate="$3"

    local percent=0
    if [[ ${bytes_total} -gt 0 ]]; then
        percent=$((bytes_written * 100 / bytes_total))
    fi

    local data
    data=$(cat << EOF
{
    "role": "source",
    "bytes_written": ${bytes_written},
    "bytes_total": ${bytes_total},
    "percent": ${percent},
    "transfer_rate_bps": ${transfer_rate},
    "status": "uploading",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    api_post_resilient "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/progress" "${data}"
}

# =============================================================================
# Report completion to controller
# =============================================================================

report_completion() {
    log "Reporting completion to controller..."

    local transfer_duration
    transfer_duration=$(($(date +%s) - TRANSFER_START_TIME))
    if [[ ${transfer_duration} -le 0 ]]; then
        transfer_duration=1
    fi

    local avg_rate=$((BYTES_WRITTEN / transfer_duration))

    # Get final image size if compressed
    local image_size=${BYTES_WRITTEN}
    local image_path="${STAGING_MOUNTPOINT}/${IMAGE_FILENAME}"
    if [[ -f "${image_path}" ]]; then
        image_size=$(stat -c %s "${image_path}" 2>/dev/null || echo "${BYTES_WRITTEN}")
    fi

    local data
    data=$(cat << EOF
{
    "role": "source",
    "source_size_bytes": ${DISK_SIZE},
    "image_size_bytes": ${image_size},
    "bytes_written": ${BYTES_WRITTEN},
    "transfer_duration_seconds": ${transfer_duration},
    "average_rate_bps": ${avg_rate},
    "compressed": ${COMPRESSION_ENABLED},
    "image_filename": "${IMAGE_FILENAME}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    if api_post "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/source-complete" "${data}"; then
        log "Completion reported successfully"
    else
        log_warn "Failed to report completion to controller"
        queue_update "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/source-complete" "${data}"
    fi
}

# =============================================================================
# Fetch session info from controller
# =============================================================================

fetch_session_info() {
    log "Fetching session info from controller..."

    local url="${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}"
    local response

    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        "${url}" 2>/dev/null)

    if [[ $? -ne 0 || -z "${response}" ]]; then
        log_error "Failed to fetch session info from controller"
        return 1
    fi

    # Parse session info - extract from .data wrapper
    local session_data
    session_data=$(echo "${response}" | jq -r '.data // .' 2>/dev/null)

    SESSION_STATUS=$(echo "${session_data}" | jq -r '.status // empty' 2>/dev/null)
    RESIZE_MODE=$(echo "${session_data}" | jq -r '.resize_mode // "none"' 2>/dev/null)
    COMPRESSION_ENABLED=$(echo "${session_data}" | jq -r '.compression_enabled // true' 2>/dev/null)
    IMAGE_FILENAME=$(echo "${session_data}" | jq -r '.image_filename // "disk.raw.gz"' 2>/dev/null)

    # Validate session status
    if [[ -z "${SESSION_STATUS}" ]]; then
        log_error "Invalid session response: missing status"
        return 1
    fi

    log "Session info:"
    log "  Status: ${SESSION_STATUS}"
    log "  Resize Mode: ${RESIZE_MODE}"
    log "  Compression: ${COMPRESSION_ENABLED}"
    log "  Image Filename: ${IMAGE_FILENAME}"

    return 0
}

# =============================================================================
# Fetch staging info from controller
# =============================================================================

fetch_staging_info() {
    log "Fetching staging info from controller..."

    local url="${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/staging-info"
    local response

    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        "${url}" 2>/dev/null)

    if [[ $? -ne 0 || -z "${response}" ]]; then
        log_error "Failed to fetch staging info from controller"
        return 1
    fi

    # Parse staging info
    STAGING_TYPE=$(echo "${response}" | jq -r '.type // empty' 2>/dev/null)
    STAGING_SERVER=$(echo "${response}" | jq -r '.server // empty' 2>/dev/null)
    STAGING_PATH=$(echo "${response}" | jq -r '.path // empty' 2>/dev/null)
    STAGING_LUN=$(echo "${response}" | jq -r '.lun // 0' 2>/dev/null)

    # Validate staging info
    if [[ -z "${STAGING_TYPE}" ]]; then
        log_error "Invalid staging response: missing type"
        return 1
    fi

    if [[ -z "${STAGING_SERVER}" ]]; then
        log_error "Invalid staging response: missing server"
        return 1
    fi

    log "Staging info:"
    log "  Type: ${STAGING_TYPE}"
    log "  Server: ${STAGING_SERVER}"
    log "  Path: ${STAGING_PATH}"
    if [[ "${STAGING_TYPE}" == "iscsi" ]]; then
        log "  LUN: ${STAGING_LUN}"
    fi

    return 0
}

# =============================================================================
# Mount NFS staging storage
# =============================================================================

mount_nfs_staging() {
    log "Mounting NFS staging storage..."

    local nfs_export="${STAGING_SERVER}:${STAGING_PATH}"

    # Ensure mount point exists
    mkdir -p "${STAGING_MOUNTPOINT}"

    # Check if already mounted
    if mountpoint -q "${STAGING_MOUNTPOINT}" 2>/dev/null; then
        log_warn "Staging mountpoint already mounted, unmounting first"
        umount "${STAGING_MOUNTPOINT}" || {
            log_error "Failed to unmount existing staging mount"
            return 1
        }
    fi

    # Mount NFS share
    log "Mounting ${nfs_export} to ${STAGING_MOUNTPOINT}"

    if ! mount -t nfs -o "vers=3,nolock,soft,timeo=300,retrans=3" \
        "${nfs_export}" "${STAGING_MOUNTPOINT}"; then
        log_error "Failed to mount NFS share: ${nfs_export}"
        return 1
    fi

    # Verify mount is accessible
    if ! touch "${STAGING_MOUNTPOINT}/.pureboot_test" 2>/dev/null; then
        log_error "NFS share is mounted but not writable"
        umount "${STAGING_MOUNTPOINT}" || true
        return 1
    fi
    rm -f "${STAGING_MOUNTPOINT}/.pureboot_test"

    log "NFS staging storage mounted successfully"
    return 0
}

# =============================================================================
# Connect iSCSI staging storage
# =============================================================================

connect_iscsi_staging() {
    log "Connecting iSCSI staging storage..."

    local target_portal="${STAGING_SERVER}"
    local target_iqn="${STAGING_PATH}"

    # Check if open-iscsi is available
    if ! command -v iscsiadm &>/dev/null; then
        log_error "iscsiadm not found - iSCSI support not available"
        return 1
    fi

    # Discover the target
    log "Discovering iSCSI target on ${target_portal}..."
    if ! iscsiadm -m discovery -t sendtargets -p "${target_portal}" &>/dev/null; then
        log_error "Failed to discover iSCSI target on ${target_portal}"
        return 1
    fi

    # Login to the target
    log "Logging in to iSCSI target ${target_iqn}..."
    if ! iscsiadm -m node -T "${target_iqn}" -p "${target_portal}" --login; then
        log_error "Failed to login to iSCSI target"
        return 1
    fi

    # Wait for device to appear
    log "Waiting for iSCSI device..."
    local wait_count=0
    local max_wait=30
    while [[ ${wait_count} -lt ${max_wait} ]]; do
        # Find the iSCSI device by scanning /dev/disk/by-path
        STAGING_DEVICE=$(ls -l /dev/disk/by-path/ 2>/dev/null | \
            grep "ip-${target_portal}.*-lun-${STAGING_LUN}" | \
            awk '{print $NF}' | xargs -I{} readlink -f /dev/disk/by-path/{} 2>/dev/null | \
            head -1)

        if [[ -b "${STAGING_DEVICE}" ]]; then
            log "iSCSI device found: ${STAGING_DEVICE}"
            break
        fi

        sleep 1
        ((wait_count++))
    done

    if [[ ! -b "${STAGING_DEVICE}" ]]; then
        log_error "iSCSI device did not appear within ${max_wait} seconds"
        # Logout on failure
        iscsiadm -m node -T "${target_iqn}" -p "${target_portal}" --logout &>/dev/null || true
        return 1
    fi

    # Mount the iSCSI device
    mkdir -p "${STAGING_MOUNTPOINT}"

    # Try to detect and mount the filesystem
    local fstype
    fstype=$(blkid -o value -s TYPE "${STAGING_DEVICE}" 2>/dev/null || true)

    if [[ -z "${fstype}" ]]; then
        log_warn "No filesystem detected on iSCSI device, attempting to format as ext4"
        if ! mkfs.ext4 -F -L pureboot-staging "${STAGING_DEVICE}"; then
            log_error "Failed to format iSCSI device"
            return 1
        fi
        fstype="ext4"
    fi

    log "Mounting iSCSI device (${fstype}) to ${STAGING_MOUNTPOINT}"
    if ! mount -t "${fstype}" "${STAGING_DEVICE}" "${STAGING_MOUNTPOINT}"; then
        log_error "Failed to mount iSCSI device"
        return 1
    fi

    # Verify mount is writable
    if ! touch "${STAGING_MOUNTPOINT}/.pureboot_test" 2>/dev/null; then
        log_error "iSCSI storage is mounted but not writable"
        umount "${STAGING_MOUNTPOINT}" || true
        return 1
    fi
    rm -f "${STAGING_MOUNTPOINT}/.pureboot_test"

    log "iSCSI staging storage connected and mounted successfully"
    return 0
}

# =============================================================================
# Mount staging storage (dispatcher)
# =============================================================================

mount_staging_storage() {
    case "${STAGING_TYPE}" in
        nfs)
            mount_nfs_staging
            ;;
        iscsi)
            connect_iscsi_staging
            ;;
        *)
            log_error "Unsupported staging type: ${STAGING_TYPE}"
            return 1
            ;;
    esac
}

# =============================================================================
# Unmount NFS staging storage
# =============================================================================

unmount_nfs_staging() {
    log "Unmounting NFS staging storage..."

    # Sync to ensure all data is written
    sync

    if mountpoint -q "${STAGING_MOUNTPOINT}" 2>/dev/null; then
        if ! umount "${STAGING_MOUNTPOINT}"; then
            log_warn "Clean unmount failed, forcing unmount..."
            umount -f "${STAGING_MOUNTPOINT}" || {
                log_error "Failed to unmount NFS staging storage"
                return 1
            }
        fi
    fi

    log "NFS staging storage unmounted"
    return 0
}

# =============================================================================
# Disconnect iSCSI staging storage
# =============================================================================

disconnect_iscsi_session() {
    local target_portal="${STAGING_SERVER}"
    local target_iqn="${STAGING_PATH}"

    log "Disconnecting iSCSI session..."

    # Logout from the target
    if ! iscsiadm -m node -T "${target_iqn}" -p "${target_portal}" --logout 2>/dev/null; then
        log_warn "Failed to logout from iSCSI target (may already be disconnected)"
    fi

    log "iSCSI session disconnected"
    return 0
}

# =============================================================================
# Unmount iSCSI staging storage
# =============================================================================

unmount_iscsi_staging() {
    log "Unmounting iSCSI staging storage..."

    # Sync to ensure all data is written
    sync

    if mountpoint -q "${STAGING_MOUNTPOINT}" 2>/dev/null; then
        if ! umount "${STAGING_MOUNTPOINT}"; then
            log_warn "Clean unmount failed, forcing unmount..."
            umount -f "${STAGING_MOUNTPOINT}" || {
                log_error "Failed to unmount iSCSI staging storage"
                return 1
            }
        fi
    fi

    # Disconnect iSCSI session
    disconnect_iscsi_session

    log "iSCSI staging storage unmounted and disconnected"
    return 0
}

# =============================================================================
# Unmount staging storage (dispatcher)
# =============================================================================

unmount_staging_storage() {
    case "${STAGING_TYPE}" in
        nfs)
            unmount_nfs_staging
            ;;
        iscsi)
            unmount_iscsi_staging
            ;;
        *)
            log_warn "Unknown staging type for unmount: ${STAGING_TYPE}"
            # Try generic unmount
            if mountpoint -q "${STAGING_MOUNTPOINT}" 2>/dev/null; then
                umount "${STAGING_MOUNTPOINT}" || true
            fi
            ;;
    esac
}

# =============================================================================
# Check if pre-clone shrink is needed
# =============================================================================

needs_shrink() {
    [[ "${RESIZE_MODE}" == "shrink_source" ]]
}

# =============================================================================
# Execute pre-clone shrink operations
# =============================================================================

execute_shrink() {
    log "Executing pre-clone shrink operations..."

    # Fetch the resize plan from controller
    local url="${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/resize-plan"
    local response

    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        "${url}" 2>/dev/null)

    if [[ $? -ne 0 || -z "${response}" ]]; then
        log_error "Failed to fetch resize plan from controller"
        return 1
    fi

    # Parse resize operations
    local operations
    operations=$(echo "${response}" | jq -r '.operations // []' 2>/dev/null)

    local op_count
    op_count=$(echo "${operations}" | jq 'length' 2>/dev/null)

    if [[ "${op_count}" == "0" || "${op_count}" == "null" ]]; then
        log "No resize operations to execute"
        return 0
    fi

    log "Executing ${op_count} resize operations..."

    # Execute each operation using pureboot-partition-ops.sh
    local op_script="${SCRIPT_DIR}/pureboot-partition-ops.sh"
    if [[ ! -x "${op_script}" ]]; then
        op_script="/usr/local/bin/pureboot-partition-ops.sh"
    fi

    if [[ ! -x "${op_script}" ]]; then
        log_error "Partition operations script not found"
        return 1
    fi

    local i=0
    while [[ ${i} -lt ${op_count} ]]; do
        local op
        op=$(echo "${operations}" | jq -c ".[${i}]" 2>/dev/null)

        log "Executing operation $((i+1))/${op_count}: $(echo "${op}" | jq -r '.operation')"

        if ! "${op_script}" "${op}"; then
            log_error "Resize operation failed: ${op}"
            return 1
        fi

        ((i++))
    done

    # Update disk size after shrink
    DISK_SIZE=$(get_disk_size "${PUREBOOT_DEVICE}")
    DISK_SIZE_HUMAN=$(format_bytes "${DISK_SIZE}")
    log "Disk size after shrink: ${DISK_SIZE} bytes (${DISK_SIZE_HUMAN})"

    log "Pre-clone shrink operations completed successfully"
    return 0
}

# =============================================================================
# Stream disk to staging storage
# =============================================================================

stream_disk_to_staging() {
    log "Starting disk upload to staging storage..."

    local image_path="${STAGING_MOUNTPOINT}/${IMAGE_FILENAME}"

    log "Source device: ${PUREBOOT_DEVICE}"
    log "Destination: ${image_path}"
    log "Compression: ${COMPRESSION_ENABLED}"
    log "Disk size: ${DISK_SIZE_HUMAN}"

    # Check for sufficient space on staging
    local available_space
    available_space=$(df -B1 "${STAGING_MOUNTPOINT}" | tail -1 | awk '{print $4}')
    local available_human
    available_human=$(format_bytes "${available_space}")
    log "Available staging space: ${available_human}"

    # For compressed images, estimate ~40-60% of original size as minimum
    local min_required
    if [[ "${COMPRESSION_ENABLED}" == "true" ]]; then
        min_required=$((DISK_SIZE * 40 / 100))
    else
        min_required=${DISK_SIZE}
    fi

    if [[ ${available_space} -lt ${min_required} ]]; then
        log_error "Insufficient staging space: need $(format_bytes ${min_required}), have ${available_human}"
        return 1
    fi

    # Record transfer start time
    TRANSFER_START_TIME=$(date +%s)
    LAST_PROGRESS_TIME=${TRANSFER_START_TIME}

    # Create progress FIFO
    rm -f "${PROGRESS_FIFO}"
    mkfifo "${PROGRESS_FIFO}"

    # Start progress monitoring in background
    (
        local last_bytes=0
        local last_time=${TRANSFER_START_TIME}

        while IFS= read -r line; do
            # pv -n outputs percentage as integer
            if [[ "${line}" =~ ^[0-9]+$ ]]; then
                local percent="${line}"
                local current_time
                current_time=$(date +%s)
                local time_diff=$((current_time - last_time))

                # Calculate bytes from percentage
                BYTES_WRITTEN=$((DISK_SIZE * percent / 100))

                # Report at intervals
                if [[ ${time_diff} -ge ${PROGRESS_INTERVAL} ]]; then
                    local bytes_diff=$((BYTES_WRITTEN - last_bytes))
                    local rate=0
                    if [[ ${time_diff} -gt 0 ]]; then
                        rate=$((bytes_diff / time_diff))
                    fi

                    local human_bytes
                    human_bytes=$(format_bytes "${BYTES_WRITTEN}")
                    local human_rate
                    human_rate=$(format_bytes "${rate}")

                    log "Upload progress: ${percent}% (${human_bytes} / ${DISK_SIZE_HUMAN}) at ${human_rate}/s"
                    report_upload_progress "${BYTES_WRITTEN}" "${DISK_SIZE}" "${rate}"

                    last_time=${current_time}
                    last_bytes=${BYTES_WRITTEN}
                fi
            fi
        done < "${PROGRESS_FIFO}"
    ) &
    local progress_pid=$!

    # Build the pipeline based on compression setting
    local pipeline_result=0

    if [[ "${COMPRESSION_ENABLED}" == "true" ]]; then
        log "Streaming with gzip compression (level ${GZIP_LEVEL})..."

        # Pipeline: dd -> pv -> gzip -> file
        {
            dd if="${PUREBOOT_DEVICE}" bs="${DD_BLOCK_SIZE}" status=none 2>/dev/null
        } | {
            # pv monitors progress
            if command -v pv &>/dev/null; then
                pv -f -n -s "${DISK_SIZE}" 2>"${PROGRESS_FIFO}"
            else
                cat
            fi
        } | {
            gzip -${GZIP_LEVEL} -c
        } > "${image_path}" || pipeline_result=$?
    else
        log "Streaming without compression..."

        # Pipeline: dd -> pv -> file
        {
            dd if="${PUREBOOT_DEVICE}" bs="${DD_BLOCK_SIZE}" status=none 2>/dev/null
        } | {
            # pv monitors progress
            if command -v pv &>/dev/null; then
                pv -f -n -s "${DISK_SIZE}" 2>"${PROGRESS_FIFO}"
            else
                cat
            fi
        } > "${image_path}" || pipeline_result=$?
    fi

    # Wait for progress monitor to finish
    sleep 1
    kill ${progress_pid} 2>/dev/null || true
    wait ${progress_pid} 2>/dev/null || true

    # Clean up FIFO
    rm -f "${PROGRESS_FIFO}"

    # Check pipeline result
    if [[ ${pipeline_result} -ne 0 ]]; then
        log_error "Disk streaming failed with exit code: ${pipeline_result}"
        return 1
    fi

    # Sync to ensure all data is written
    sync

    # Get final image size
    local final_size
    final_size=$(stat -c %s "${image_path}" 2>/dev/null || echo "0")
    BYTES_WRITTEN=${final_size}

    local final_human
    final_human=$(format_bytes "${final_size}")

    local transfer_duration=$(($(date +%s) - TRANSFER_START_TIME))
    local avg_rate=0
    if [[ ${transfer_duration} -gt 0 ]]; then
        avg_rate=$((BYTES_WRITTEN / transfer_duration))
    fi

    local human_rate
    human_rate=$(format_bytes "${avg_rate}")

    log "Upload completed: ${final_human} in ${transfer_duration}s (avg: ${human_rate}/s)"

    if [[ "${COMPRESSION_ENABLED}" == "true" ]]; then
        local compression_ratio
        if [[ ${final_size} -gt 0 ]]; then
            compression_ratio=$((100 - (final_size * 100 / DISK_SIZE)))
            log "Compression ratio: ${compression_ratio}% reduction (${DISK_SIZE_HUMAN} -> ${final_human})"
        fi
    fi

    # Report final progress
    report_upload_progress "${DISK_SIZE}" "${DISK_SIZE}" "${avg_rate}"

    return 0
}

# =============================================================================
# Main execution
# =============================================================================

log "=== PureBoot Staged Mode Clone Source ==="

# Validate required parameters
if [[ -z "${PUREBOOT_SERVER}" ]]; then
    report_failed "PUREBOOT_SERVER not set. Cannot communicate with controller." "101"
    exit 1
fi

if [[ -z "${PUREBOOT_SESSION_ID}" ]]; then
    report_failed "PUREBOOT_SESSION_ID not set. Clone session not identified." "102"
    exit 1
fi

if [[ -z "${PUREBOOT_DEVICE}" ]]; then
    report_failed "PUREBOOT_DEVICE not set. No source disk specified." "103"
    exit 1
fi

# Validate device exists and is a block device
if [[ ! -b "${PUREBOOT_DEVICE}" ]]; then
    report_failed "Device not found or not a block device: ${PUREBOOT_DEVICE}" "104"
    exit 1
fi

log "Configuration:"
log "  Server: ${PUREBOOT_SERVER}"
log "  Session ID: ${PUREBOOT_SESSION_ID}"
log "  Device: ${PUREBOOT_DEVICE}"

# Get disk information
log "Getting disk information..."

DISK_SIZE=$(get_disk_size "${PUREBOOT_DEVICE}")
if [[ $? -ne 0 || -z "${DISK_SIZE}" ]]; then
    report_failed "Failed to get disk size for ${PUREBOOT_DEVICE}" "105"
    exit 1
fi

DISK_SIZE_HUMAN=$(format_bytes "${DISK_SIZE}")
log "Disk size: ${DISK_SIZE} bytes (${DISK_SIZE_HUMAN})"

# Fetch session info
if ! fetch_session_info; then
    report_failed "Failed to fetch session info from controller" "110"
    exit 1
fi

# Fetch staging info
if ! fetch_staging_info; then
    report_failed "Failed to fetch staging info from controller" "111"
    exit 1
fi

# Mount staging storage
log "Mounting staging storage..."
if ! mount_staging_storage; then
    report_failed "Failed to mount staging storage" "112"
    exit 1
fi

log "Staging storage mounted at ${STAGING_MOUNTPOINT}"

# Check for pre-clone resize
if needs_shrink; then
    log "Pre-clone shrink requested..."
    if ! execute_shrink; then
        report_failed "Pre-clone shrink operations failed" "120"
        exit 1
    fi
fi

# Update staging status to uploading
update_staging_status "uploading" "Starting disk upload"

# Stream disk to staging
if ! stream_disk_to_staging; then
    report_failed "Disk upload to staging failed" "130"
    exit 1
fi

# Update staging status to ready
update_staging_status "ready" "Disk image ready for cloning"

# Unmount staging storage
log "Unmounting staging storage..."
if ! unmount_staging_storage; then
    log_warn "Failed to cleanly unmount staging storage"
fi

# Report completion
report_completion

# Flush any remaining queued updates
flush_queue

log "=== Clone source upload complete ==="
log "Source script finished successfully"
