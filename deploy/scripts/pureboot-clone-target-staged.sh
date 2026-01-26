#!/bin/bash
# PureBoot Staged Mode Clone Target Script
# This script runs on a target node to download a disk image from staging storage (NFS/iSCSI)
# and write it to the local disk.

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_MOUNTPOINT="/mnt/staging"
PROGRESS_FIFO="/tmp/pureboot-progress"

# Progress reporting interval in seconds
PROGRESS_INTERVAL=5

# Timeout for waiting for staging to be ready (seconds)
STAGING_READY_TIMEOUT=1800

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

# Staging info (populated by fetch_staging_info)
STAGING_TYPE=""
STAGING_SERVER=""
STAGING_EXPORT=""
STAGING_PATH=""
STAGING_OPTIONS=""
STAGING_IMAGE_FILENAME=""
STAGING_ISCSI_TARGET=""
STAGING_ISCSI_PORTAL=""
STAGING_ISCSI_USERNAME=""
STAGING_ISCSI_PASSWORD=""
STAGING_ISCSI_DEVICE=""

# Session info (populated by fetch_session_info)
SESSION_RESIZE_MODE=""
DISK_SIZE=0
TRANSFER_START_TIME=0
BYTES_TRANSFERRED=0

# =============================================================================
# Cleanup function
# =============================================================================

cleanup() {
    log "Cleaning up..."

    # Remove FIFO if exists
    if [[ -p "${PROGRESS_FIFO}" ]]; then
        rm -f "${PROGRESS_FIFO}"
    fi

    # Unmount staging storage
    unmount_staging_storage

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
    "role": "target",
    "error_message": "${error_message}",
    "error_code": "${error_code}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    api_post_resilient "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/failed" "${data}"
}

# =============================================================================
# Report completion to controller
# =============================================================================

report_complete() {
    log "Reporting completion to controller..."

    local transfer_duration
    transfer_duration=$(($(date +%s) - TRANSFER_START_TIME))
    if [[ ${transfer_duration} -le 0 ]]; then
        transfer_duration=1
    fi

    local avg_rate=$((BYTES_TRANSFERRED / transfer_duration))

    local data
    data=$(cat << EOF
{
    "role": "target",
    "bytes_transferred": ${BYTES_TRANSFERRED},
    "transfer_duration_seconds": ${transfer_duration},
    "average_rate_bps": ${avg_rate},
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    if api_post "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/complete" "${data}"; then
        log "Completion reported successfully"
    else
        log_warn "Failed to report completion to controller"
        queue_update "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/complete" "${data}"
    fi
}

# =============================================================================
# Report transfer progress to controller
# =============================================================================

report_transfer_progress() {
    local bytes_transferred="$1"
    local bytes_total="$2"
    local transfer_rate="$3"
    local status="$4"

    local data
    data=$(cat << EOF
{
    "role": "target",
    "bytes_transferred": ${bytes_transferred},
    "bytes_total": ${bytes_total},
    "transfer_rate_bps": ${transfer_rate},
    "status": "${status}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    api_post_resilient "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/progress" "${data}"
}

# =============================================================================
# Update staging status on controller
# =============================================================================

update_staging_status() {
    local new_status="$1"

    log "Updating staging status to: ${new_status}"

    local data
    data=$(cat << EOF
{
    "staging_status": "${new_status}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    api_post_resilient "/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/staging-status" "${data}"
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

    # Parse response - extract from data field if wrapped
    local session_data
    session_data=$(echo "${response}" | jq -r '.data // .' 2>/dev/null)

    SESSION_RESIZE_MODE=$(echo "${session_data}" | jq -r '.resize_mode // "none"' 2>/dev/null)
    DISK_SIZE=$(echo "${session_data}" | jq -r '.bytes_total // 0' 2>/dev/null)

    log "Session info:"
    log "  Resize mode: ${SESSION_RESIZE_MODE}"
    log "  Disk size: ${DISK_SIZE} bytes ($(format_bytes "${DISK_SIZE}"))"

    return 0
}

# =============================================================================
# Wait for staging to be ready (source upload complete)
# =============================================================================

wait_for_staging_ready() {
    log "Waiting for staging to be ready (source upload complete)..."

    local timeout=${STAGING_READY_TIMEOUT}
    local elapsed=0
    local poll_interval=10

    while [[ ${elapsed} -lt ${timeout} ]]; do
        local url="${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}"
        local response

        response=$(curl -sf \
            --connect-timeout 10 \
            --max-time 30 \
            "${url}" 2>/dev/null) || true

        if [[ -n "${response}" ]]; then
            # Parse response - extract from data field if wrapped
            local session_data
            session_data=$(echo "${response}" | jq -r '.data // .' 2>/dev/null)

            local staging_status
            staging_status=$(echo "${session_data}" | jq -r '.staging_status // empty' 2>/dev/null)

            log_debug "Staging status: ${staging_status}"

            if [[ "${staging_status}" == "ready" ]]; then
                log "Staging is ready - source upload complete"
                return 0
            elif [[ "${staging_status}" == "failed" ]]; then
                log_error "Staging failed on source side"
                return 1
            fi

            local session_status
            session_status=$(echo "${session_data}" | jq -r '.status // empty' 2>/dev/null)

            if [[ "${session_status}" == "failed" || "${session_status}" == "cancelled" ]]; then
                log_error "Clone session ${session_status}"
                return 1
            fi
        fi

        # Wait before next poll
        sleep ${poll_interval}
        elapsed=$((elapsed + poll_interval))

        if [[ $((elapsed % 60)) -eq 0 ]]; then
            log "Still waiting for staging to be ready... (${elapsed}s / ${timeout}s)"
        fi
    done

    log_error "Timeout waiting for staging to be ready (${timeout}s)"
    return 1
}

# =============================================================================
# Fetch staging mount info from controller
# =============================================================================

fetch_staging_info() {
    log "Fetching staging mount info from controller..."

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

    # Parse response - extract from data field if wrapped
    local staging_data
    staging_data=$(echo "${response}" | jq -r '.data // .' 2>/dev/null)

    STAGING_TYPE=$(echo "${staging_data}" | jq -r '.type // empty' 2>/dev/null)

    if [[ -z "${STAGING_TYPE}" ]]; then
        log_error "Invalid staging info response - missing type"
        return 1
    fi

    if [[ "${STAGING_TYPE}" == "nfs" ]]; then
        STAGING_SERVER=$(echo "${staging_data}" | jq -r '.server // empty' 2>/dev/null)
        STAGING_EXPORT=$(echo "${staging_data}" | jq -r '.export // empty' 2>/dev/null)
        STAGING_PATH=$(echo "${staging_data}" | jq -r '.path // empty' 2>/dev/null)
        STAGING_OPTIONS=$(echo "${staging_data}" | jq -r '.options // "ro"' 2>/dev/null)
        STAGING_IMAGE_FILENAME=$(echo "${staging_data}" | jq -r '.image_filename // "disk.raw.gz"' 2>/dev/null)

        log "NFS staging info:"
        log "  Server: ${STAGING_SERVER}"
        log "  Export: ${STAGING_EXPORT}"
        log "  Path: ${STAGING_PATH}"
        log "  Options: ${STAGING_OPTIONS}"
        log "  Image file: ${STAGING_IMAGE_FILENAME}"

        if [[ -z "${STAGING_SERVER}" || -z "${STAGING_EXPORT}" ]]; then
            log_error "Invalid NFS staging info - missing server or export"
            return 1
        fi
    elif [[ "${STAGING_TYPE}" == "iscsi" ]]; then
        STAGING_ISCSI_TARGET=$(echo "${staging_data}" | jq -r '.target // empty' 2>/dev/null)
        STAGING_ISCSI_PORTAL=$(echo "${staging_data}" | jq -r '.portal // empty' 2>/dev/null)
        STAGING_ISCSI_USERNAME=$(echo "${staging_data}" | jq -r '.username // empty' 2>/dev/null)
        STAGING_ISCSI_PASSWORD=$(echo "${staging_data}" | jq -r '.password // empty' 2>/dev/null)

        log "iSCSI staging info:"
        log "  Target: ${STAGING_ISCSI_TARGET}"
        log "  Portal: ${STAGING_ISCSI_PORTAL}"
        log "  Auth: $([ -n "${STAGING_ISCSI_USERNAME}" ] && echo "CHAP enabled" || echo "No auth")"

        if [[ -z "${STAGING_ISCSI_TARGET}" || -z "${STAGING_ISCSI_PORTAL}" ]]; then
            log_error "Invalid iSCSI staging info - missing target or portal"
            return 1
        fi
    else
        log_error "Unsupported staging type: ${STAGING_TYPE}"
        return 1
    fi

    return 0
}

# =============================================================================
# Mount NFS staging storage
# =============================================================================

mount_nfs_staging() {
    log "Mounting NFS staging storage..."

    # Create mount point
    mkdir -p "${STAGING_MOUNTPOINT}"

    # Build NFS mount path
    local nfs_source="${STAGING_SERVER}:${STAGING_EXPORT}"
    local mount_options="ro,noatime"

    if [[ -n "${STAGING_OPTIONS}" && "${STAGING_OPTIONS}" != "null" ]]; then
        # Remove any 'rw' option and add 'ro' for target (read-only)
        mount_options=$(echo "${STAGING_OPTIONS}" | sed 's/rw/ro/g')
        # Ensure 'ro' is present
        if [[ ! "${mount_options}" =~ (^|,)ro(,|$) ]]; then
            mount_options="ro,${mount_options}"
        fi
    fi

    log "Mounting ${nfs_source} to ${STAGING_MOUNTPOINT} with options: ${mount_options}"

    if ! mount -t nfs -o "${mount_options}" "${nfs_source}" "${STAGING_MOUNTPOINT}"; then
        log_error "Failed to mount NFS staging storage"
        return 1
    fi

    # Verify the staging path exists
    local full_staging_path="${STAGING_MOUNTPOINT}/${STAGING_PATH}"
    if [[ ! -d "${full_staging_path}" ]]; then
        log_error "Staging directory not found: ${full_staging_path}"
        umount "${STAGING_MOUNTPOINT}" 2>/dev/null || true
        return 1
    fi

    # Verify the disk image exists
    local image_path="${full_staging_path}/${STAGING_IMAGE_FILENAME}"
    if [[ ! -f "${image_path}" ]]; then
        log_error "Disk image not found: ${image_path}"
        umount "${STAGING_MOUNTPOINT}" 2>/dev/null || true
        return 1
    fi

    log "NFS staging mounted successfully"
    log "Disk image found at: ${image_path}"

    return 0
}

# =============================================================================
# Connect to iSCSI staging storage
# =============================================================================

connect_iscsi_staging() {
    log "Connecting to iSCSI staging storage..."

    # Check for open-iscsi tools
    if ! command -v iscsiadm &>/dev/null; then
        log_error "iscsiadm not found - iSCSI tools not installed"
        return 1
    fi

    # Discover target
    log "Discovering iSCSI target at portal: ${STAGING_ISCSI_PORTAL}"
    if ! iscsiadm -m discovery -t sendtargets -p "${STAGING_ISCSI_PORTAL}" 2>/dev/null; then
        log_error "Failed to discover iSCSI targets"
        return 1
    fi

    # Set CHAP credentials if provided
    if [[ -n "${STAGING_ISCSI_USERNAME}" && "${STAGING_ISCSI_USERNAME}" != "null" ]]; then
        log "Configuring CHAP authentication..."
        iscsiadm -m node -T "${STAGING_ISCSI_TARGET}" -p "${STAGING_ISCSI_PORTAL}" \
            --op update -n node.session.auth.authmethod -v CHAP 2>/dev/null || true
        iscsiadm -m node -T "${STAGING_ISCSI_TARGET}" -p "${STAGING_ISCSI_PORTAL}" \
            --op update -n node.session.auth.username -v "${STAGING_ISCSI_USERNAME}" 2>/dev/null || true
        iscsiadm -m node -T "${STAGING_ISCSI_TARGET}" -p "${STAGING_ISCSI_PORTAL}" \
            --op update -n node.session.auth.password -v "${STAGING_ISCSI_PASSWORD}" 2>/dev/null || true
    fi

    # Login to target
    log "Logging in to iSCSI target: ${STAGING_ISCSI_TARGET}"
    if ! iscsiadm -m node -T "${STAGING_ISCSI_TARGET}" -p "${STAGING_ISCSI_PORTAL}" --login; then
        log_error "Failed to login to iSCSI target"
        return 1
    fi

    # Wait for device to appear
    log "Waiting for iSCSI device to appear..."
    local wait_count=0
    while [[ ${wait_count} -lt 30 ]]; do
        # Find the iSCSI device
        STAGING_ISCSI_DEVICE=$(lsblk -dpno NAME,TRAN 2>/dev/null | grep iscsi | awk '{print $1}' | head -1)

        if [[ -n "${STAGING_ISCSI_DEVICE}" && -b "${STAGING_ISCSI_DEVICE}" ]]; then
            log "iSCSI device found: ${STAGING_ISCSI_DEVICE}"
            return 0
        fi

        sleep 1
        ((wait_count++))
    done

    log_error "Timeout waiting for iSCSI device to appear"
    iscsiadm -m node -T "${STAGING_ISCSI_TARGET}" -p "${STAGING_ISCSI_PORTAL}" --logout 2>/dev/null || true
    return 1
}

# =============================================================================
# Mount staging storage (dispatcher)
# =============================================================================

mount_staging_storage() {
    if [[ "${STAGING_TYPE}" == "nfs" ]]; then
        mount_nfs_staging
    elif [[ "${STAGING_TYPE}" == "iscsi" ]]; then
        connect_iscsi_staging
    else
        log_error "Unknown staging type: ${STAGING_TYPE}"
        return 1
    fi
}

# =============================================================================
# Unmount NFS staging storage
# =============================================================================

unmount_nfs_staging() {
    if mountpoint -q "${STAGING_MOUNTPOINT}" 2>/dev/null; then
        log "Unmounting NFS staging storage..."
        sync
        umount "${STAGING_MOUNTPOINT}" 2>/dev/null || {
            log_warn "Standard unmount failed, trying lazy unmount..."
            umount -l "${STAGING_MOUNTPOINT}" 2>/dev/null || true
        }
    fi
}

# =============================================================================
# Disconnect from iSCSI staging storage
# =============================================================================

disconnect_iscsi_staging() {
    if [[ -n "${STAGING_ISCSI_TARGET}" ]]; then
        log "Logging out from iSCSI target..."
        iscsiadm -m node -T "${STAGING_ISCSI_TARGET}" -p "${STAGING_ISCSI_PORTAL}" --logout 2>/dev/null || true
    fi
}

# =============================================================================
# Unmount staging storage (dispatcher)
# =============================================================================

unmount_staging_storage() {
    if [[ "${STAGING_TYPE}" == "nfs" ]]; then
        unmount_nfs_staging
    elif [[ "${STAGING_TYPE}" == "iscsi" ]]; then
        disconnect_iscsi_staging
    fi
}

# =============================================================================
# Stream disk from NFS staging
# =============================================================================

stream_disk_from_nfs() {
    log "Streaming disk from NFS staging to local device..."

    local image_path="${STAGING_MOUNTPOINT}/${STAGING_PATH}/${STAGING_IMAGE_FILENAME}"

    log "Source image: ${image_path}"
    log "Target device: ${PUREBOOT_DEVICE}"

    # Get compressed file size for progress estimation
    local compressed_size
    compressed_size=$(stat -c %s "${image_path}" 2>/dev/null || echo "0")
    log "Compressed image size: $(format_bytes "${compressed_size}")"

    # Record transfer start time
    TRANSFER_START_TIME=$(date +%s)

    # Report transfer starting
    report_transfer_progress 0 "${DISK_SIZE}" 0 "downloading"

    # Create a named pipe for progress tracking
    rm -f "${PROGRESS_FIFO}"
    mkfifo "${PROGRESS_FIFO}"

    # Start progress monitoring in background
    (
        local last_report_time=${TRANSFER_START_TIME}
        local last_bytes=0

        while IFS= read -r line; do
            # pv -n outputs percentage
            if [[ "${line}" =~ ^[0-9]+$ ]]; then
                # Convert percentage to bytes
                local percent="${line}"
                BYTES_TRANSFERRED=$((DISK_SIZE * percent / 100))

                local current_time
                current_time=$(date +%s)
                local time_diff=$((current_time - last_report_time))

                # Report at intervals
                if [[ ${time_diff} -ge ${PROGRESS_INTERVAL} ]]; then
                    local bytes_diff=$((BYTES_TRANSFERRED - last_bytes))
                    local rate=0
                    if [[ ${time_diff} -gt 0 ]]; then
                        rate=$((bytes_diff / time_diff))
                    fi

                    local human_bytes
                    human_bytes=$(format_bytes "${BYTES_TRANSFERRED}")
                    local human_rate
                    human_rate=$(format_bytes "${rate}")

                    log "Download progress: ${percent}% (${human_bytes}) at ${human_rate}/s"
                    report_transfer_progress "${BYTES_TRANSFERRED}" "${DISK_SIZE}" "${rate}" "downloading"

                    last_report_time=${current_time}
                    last_bytes=${BYTES_TRANSFERRED}
                fi
            fi
        done < "${PROGRESS_FIFO}"
    ) &
    local progress_pid=$!

    # Perform the transfer using gunzip -> pv -> dd pipeline
    local transfer_exit=0

    {
        gunzip -c "${image_path}"
    } | {
        # pv monitors progress and outputs percentage
        if command -v pv &>/dev/null; then
            pv -f -n -s "${DISK_SIZE}" 2>"${PROGRESS_FIFO}"
        else
            # Fallback if pv is not available
            cat
        fi
    } | {
        dd of="${PUREBOOT_DEVICE}" bs=4M conv=fsync status=none 2>/dev/null
    } || transfer_exit=$?

    # Wait for progress monitor to finish
    sleep 1
    kill ${progress_pid} 2>/dev/null || true
    wait ${progress_pid} 2>/dev/null || true

    # Clean up FIFO
    rm -f "${PROGRESS_FIFO}"

    # Check transfer result
    if [[ ${transfer_exit} -ne 0 ]]; then
        log_error "Transfer failed with exit code: ${transfer_exit}"
        return 1
    fi

    # Get final bytes transferred
    BYTES_TRANSFERRED=$(get_disk_size "${PUREBOOT_DEVICE}")

    local transfer_duration=$(($(date +%s) - TRANSFER_START_TIME))
    local avg_rate=0
    if [[ ${transfer_duration} -gt 0 ]]; then
        avg_rate=$((BYTES_TRANSFERRED / transfer_duration))
    fi

    local human_bytes
    human_bytes=$(format_bytes "${BYTES_TRANSFERRED}")
    local human_rate
    human_rate=$(format_bytes "${avg_rate}")

    log "Download completed: ${human_bytes} in ${transfer_duration}s (avg: ${human_rate}/s)"

    # Report final progress
    report_transfer_progress "${BYTES_TRANSFERRED}" "${DISK_SIZE}" "${avg_rate}" "completed"

    return 0
}

# =============================================================================
# Stream disk from iSCSI staging
# =============================================================================

stream_disk_from_iscsi() {
    log "Streaming disk from iSCSI staging to local device..."

    log "Source device: ${STAGING_ISCSI_DEVICE}"
    log "Target device: ${PUREBOOT_DEVICE}"

    # For iSCSI, the LUN contains the raw (possibly compressed) disk image
    # We need to determine if it's compressed or raw
    # Check first few bytes for gzip magic number (1f 8b)
    local magic
    magic=$(dd if="${STAGING_ISCSI_DEVICE}" bs=2 count=1 2>/dev/null | xxd -p)

    # Record transfer start time
    TRANSFER_START_TIME=$(date +%s)

    # Report transfer starting
    report_transfer_progress 0 "${DISK_SIZE}" 0 "downloading"

    # Create a named pipe for progress tracking
    rm -f "${PROGRESS_FIFO}"
    mkfifo "${PROGRESS_FIFO}"

    # Start progress monitoring in background
    (
        local last_report_time=${TRANSFER_START_TIME}
        local last_bytes=0

        while IFS= read -r line; do
            if [[ "${line}" =~ ^[0-9]+$ ]]; then
                local percent="${line}"
                BYTES_TRANSFERRED=$((DISK_SIZE * percent / 100))

                local current_time
                current_time=$(date +%s)
                local time_diff=$((current_time - last_report_time))

                if [[ ${time_diff} -ge ${PROGRESS_INTERVAL} ]]; then
                    local bytes_diff=$((BYTES_TRANSFERRED - last_bytes))
                    local rate=0
                    if [[ ${time_diff} -gt 0 ]]; then
                        rate=$((bytes_diff / time_diff))
                    fi

                    local human_bytes
                    human_bytes=$(format_bytes "${BYTES_TRANSFERRED}")
                    local human_rate
                    human_rate=$(format_bytes "${rate}")

                    log "Download progress: ${percent}% (${human_bytes}) at ${human_rate}/s"
                    report_transfer_progress "${BYTES_TRANSFERRED}" "${DISK_SIZE}" "${rate}" "downloading"

                    last_report_time=${current_time}
                    last_bytes=${BYTES_TRANSFERRED}
                fi
            fi
        done < "${PROGRESS_FIFO}"
    ) &
    local progress_pid=$!

    local transfer_exit=0

    if [[ "${magic}" == "1f8b" ]]; then
        # Gzip compressed
        log "Detected gzip compressed image on iSCSI LUN"
        {
            gunzip -c < "${STAGING_ISCSI_DEVICE}"
        } | {
            if command -v pv &>/dev/null; then
                pv -f -n -s "${DISK_SIZE}" 2>"${PROGRESS_FIFO}"
            else
                cat
            fi
        } | {
            dd of="${PUREBOOT_DEVICE}" bs=4M conv=fsync status=none 2>/dev/null
        } || transfer_exit=$?
    else
        # Raw image - direct copy
        log "Raw image detected on iSCSI LUN"
        {
            dd if="${STAGING_ISCSI_DEVICE}" bs=4M status=none 2>/dev/null
        } | {
            if command -v pv &>/dev/null; then
                pv -f -n -s "${DISK_SIZE}" 2>"${PROGRESS_FIFO}"
            else
                cat
            fi
        } | {
            dd of="${PUREBOOT_DEVICE}" bs=4M conv=fsync status=none 2>/dev/null
        } || transfer_exit=$?
    fi

    # Wait for progress monitor to finish
    sleep 1
    kill ${progress_pid} 2>/dev/null || true
    wait ${progress_pid} 2>/dev/null || true

    # Clean up FIFO
    rm -f "${PROGRESS_FIFO}"

    if [[ ${transfer_exit} -ne 0 ]]; then
        log_error "Transfer failed with exit code: ${transfer_exit}"
        return 1
    fi

    BYTES_TRANSFERRED=$(get_disk_size "${PUREBOOT_DEVICE}")

    local transfer_duration=$(($(date +%s) - TRANSFER_START_TIME))
    local avg_rate=0
    if [[ ${transfer_duration} -gt 0 ]]; then
        avg_rate=$((BYTES_TRANSFERRED / transfer_duration))
    fi

    local human_bytes
    human_bytes=$(format_bytes "${BYTES_TRANSFERRED}")
    local human_rate
    human_rate=$(format_bytes "${avg_rate}")

    log "Download completed: ${human_bytes} in ${transfer_duration}s (avg: ${human_rate}/s)"
    report_transfer_progress "${BYTES_TRANSFERRED}" "${DISK_SIZE}" "${avg_rate}" "completed"

    return 0
}

# =============================================================================
# Stream disk from staging (dispatcher)
# =============================================================================

stream_disk_from_staging() {
    if [[ "${STAGING_TYPE}" == "nfs" ]]; then
        stream_disk_from_nfs
    elif [[ "${STAGING_TYPE}" == "iscsi" ]]; then
        stream_disk_from_iscsi
    else
        log_error "Unknown staging type: ${STAGING_TYPE}"
        return 1
    fi
}

# =============================================================================
# Verify disk after transfer
# =============================================================================

verify_disk() {
    log "Verifying disk after transfer..."

    # Sync to ensure all data is written
    sync

    # Run partprobe to re-read partition table
    if command -v partprobe &>/dev/null; then
        log "Running partprobe to re-read partition table..."
        if partprobe "${PUREBOOT_DEVICE}" 2>/dev/null; then
            log "Partition table re-read successfully"
        else
            log_warn "partprobe failed, partition table may need manual refresh"
        fi
    else
        log_warn "partprobe not found, skipping partition table refresh"
    fi

    # Verify device is still accessible
    if [[ ! -b "${PUREBOOT_DEVICE}" ]]; then
        log_error "Target device no longer accessible: ${PUREBOOT_DEVICE}"
        return 1
    fi

    local final_size
    final_size=$(get_disk_size "${PUREBOOT_DEVICE}")
    log "Final disk size: $(format_bytes "${final_size}")"

    log "Disk verification completed"
    return 0
}

# =============================================================================
# Check if resize is needed
# =============================================================================

needs_grow() {
    if [[ "${SESSION_RESIZE_MODE}" == "grow_target" ]]; then
        return 0
    fi
    return 1
}

# =============================================================================
# Execute post-clone partition grow operations
# =============================================================================

execute_grow() {
    log "Executing post-clone partition grow operations..."

    # Fetch resize plan from controller
    local url="${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/plan"
    local response

    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        "${url}" 2>/dev/null)

    if [[ $? -ne 0 || -z "${response}" ]]; then
        log_warn "Failed to fetch resize plan from controller, skipping grow"
        return 0
    fi

    # Parse response - extract from data field if wrapped
    local plan_data
    plan_data=$(echo "${response}" | jq -r '.data // .' 2>/dev/null)

    if [[ "${plan_data}" == "null" || -z "${plan_data}" ]]; then
        log "No resize plan configured, skipping grow"
        return 0
    fi

    # Extract partitions that need growing
    local partitions_json
    partitions_json=$(echo "${plan_data}" | jq -c '.partitions // []' 2>/dev/null)

    if [[ "${partitions_json}" == "[]" || -z "${partitions_json}" ]]; then
        log "No partition operations in resize plan"
        return 0
    fi

    # Process each partition that needs growing
    echo "${partitions_json}" | jq -c '.[]' | while read -r partition; do
        local action
        local part_num
        local new_size
        local filesystem

        action=$(echo "${partition}" | jq -r '.action // "keep"')
        part_num=$(echo "${partition}" | jq -r '.partition // 0')
        new_size=$(echo "${partition}" | jq -r '.new_size_bytes // 0')
        filesystem=$(echo "${partition}" | jq -r '.filesystem // empty')

        if [[ "${action}" != "grow" ]]; then
            continue
        fi

        log "Growing partition ${part_num} to $(format_bytes "${new_size}")"

        # Determine partition device name
        local part_device
        if [[ "${PUREBOOT_DEVICE}" =~ nvme[0-9]+n[0-9]+ ]]; then
            part_device="${PUREBOOT_DEVICE}p${part_num}"
        else
            part_device="${PUREBOOT_DEVICE}${part_num}"
        fi

        # Use growpart if available (from cloud-utils-growpart)
        if command -v growpart &>/dev/null; then
            log "Using growpart to expand partition ${part_num}..."
            if growpart "${PUREBOOT_DEVICE}" "${part_num}"; then
                log "Partition ${part_num} expanded successfully"
            else
                log_warn "growpart failed for partition ${part_num}"
                continue
            fi
        elif command -v parted &>/dev/null; then
            # Fallback to parted
            log "Using parted to resize partition ${part_num}..."
            if parted -s "${PUREBOOT_DEVICE}" resizepart "${part_num}" 100%; then
                log "Partition ${part_num} resized successfully"
            else
                log_warn "parted resize failed for partition ${part_num}"
                continue
            fi
        else
            log_warn "No partition grow tool available (growpart or parted)"
            continue
        fi

        # Resize the filesystem if supported
        if [[ -n "${filesystem}" ]]; then
            log "Resizing ${filesystem} filesystem on ${part_device}..."

            case "${filesystem}" in
                ext2|ext3|ext4)
                    if command -v resize2fs &>/dev/null; then
                        # Run fsck first
                        e2fsck -f -y "${part_device}" 2>/dev/null || true
                        if resize2fs "${part_device}"; then
                            log "Filesystem resized successfully"
                        else
                            log_warn "resize2fs failed"
                        fi
                    else
                        log_warn "resize2fs not available"
                    fi
                    ;;
                xfs)
                    # XFS requires mounting to resize
                    local tmp_mount="/tmp/xfs-resize-$$"
                    mkdir -p "${tmp_mount}"
                    if mount "${part_device}" "${tmp_mount}"; then
                        if command -v xfs_growfs &>/dev/null; then
                            xfs_growfs "${tmp_mount}" || log_warn "xfs_growfs failed"
                        fi
                        umount "${tmp_mount}"
                    fi
                    rmdir "${tmp_mount}" 2>/dev/null || true
                    ;;
                btrfs)
                    local tmp_mount="/tmp/btrfs-resize-$$"
                    mkdir -p "${tmp_mount}"
                    if mount "${part_device}" "${tmp_mount}"; then
                        if command -v btrfs &>/dev/null; then
                            btrfs filesystem resize max "${tmp_mount}" || log_warn "btrfs resize failed"
                        fi
                        umount "${tmp_mount}"
                    fi
                    rmdir "${tmp_mount}" 2>/dev/null || true
                    ;;
                ntfs)
                    if command -v ntfsresize &>/dev/null; then
                        ntfsresize -f "${part_device}" || log_warn "ntfsresize failed"
                    else
                        log_warn "ntfsresize not available"
                    fi
                    ;;
                *)
                    log_warn "Filesystem type ${filesystem} not supported for resize"
                    ;;
            esac
        fi
    done

    log "Post-clone grow operations completed"
    return 0
}

# =============================================================================
# Main execution
# =============================================================================

log "PureBoot Staged Mode Clone Target starting..."

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
    report_failed "PUREBOOT_DEVICE not set. No target disk specified." "103"
    exit 1
fi

# Validate device exists and is a block device
if [[ ! -b "${PUREBOOT_DEVICE}" ]]; then
    report_failed "Device not found or not a block device: ${PUREBOOT_DEVICE}" "104"
    exit 1
fi

log "Configuration validated:"
log "  Server: ${PUREBOOT_SERVER}"
log "  Session ID: ${PUREBOOT_SESSION_ID}"
log "  Device: ${PUREBOOT_DEVICE}"

# Fetch session info
if ! fetch_session_info; then
    report_failed "Failed to fetch session info" "110"
    exit 1
fi

# Wait for staging to be ready (source upload complete)
if ! wait_for_staging_ready; then
    report_failed "Timeout or error waiting for staging to be ready" "111"
    exit 1
fi

# Fetch staging mount info
if ! fetch_staging_info; then
    report_failed "Failed to fetch staging mount info" "112"
    exit 1
fi

# Mount staging storage
if ! mount_staging_storage; then
    report_failed "Failed to mount staging storage" "113"
    exit 1
fi

# Update staging status to downloading
update_staging_status "downloading"

# Stream disk from staging to local device
if ! stream_disk_from_staging; then
    report_failed "Disk download failed" "120"
    exit 1
fi

# Unmount staging storage
unmount_staging_storage

# Verify disk after transfer
if ! verify_disk; then
    report_failed "Disk verification failed" "121"
    exit 1
fi

# Check for post-clone resize
if needs_grow; then
    execute_grow
fi

# Report completion
report_complete

# Flush any remaining queued updates
flush_queue

log "Clone operation completed successfully"
log "Rebooting in 5 seconds..."

sleep 5

# Reboot the system
log "Initiating reboot..."
reboot
