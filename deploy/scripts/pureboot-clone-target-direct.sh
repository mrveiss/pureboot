#!/bin/bash
# PureBoot Direct Mode Clone Target Script
# This script runs on a target node to receive a disk clone from a source node via HTTPS.
# The disk is streamed using curl with mTLS and written directly to the target device.

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="/tmp/pureboot-certs"
PROGRESS_FIFO="/tmp/pureboot-progress"

# Progress reporting interval in seconds
PROGRESS_INTERVAL=5

# Timeout for waiting for source to be ready (seconds)
SOURCE_READY_TIMEOUT=600

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
# Global variables for transfer tracking
# =============================================================================

SOURCE_IP=""
SOURCE_PORT=""
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

    # Remove certificate directory
    if [[ -d "${CERT_DIR}" ]]; then
        rm -rf "${CERT_DIR}"
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
# Wait for source to be ready
# =============================================================================

wait_for_source() {
    log "Waiting for source to be ready..."

    local timeout=${SOURCE_READY_TIMEOUT}
    local elapsed=0
    local poll_interval=5

    while [[ ${elapsed} -lt ${timeout} ]]; do
        local url="${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}"
        local response

        response=$(curl -sf \
            --connect-timeout 10 \
            --max-time 30 \
            "${url}" 2>/dev/null) || true

        if [[ -n "${response}" ]]; then
            local status
            status=$(echo "${response}" | jq -r '.status // empty' 2>/dev/null)

            log_debug "Session status: ${status}"

            if [[ "${status}" == "source_ready" ]]; then
                # Extract source connection details
                SOURCE_IP=$(echo "${response}" | jq -r '.source_ip // empty' 2>/dev/null)
                SOURCE_PORT=$(echo "${response}" | jq -r '.source_port // empty' 2>/dev/null)
                DISK_SIZE=$(echo "${response}" | jq -r '.size_bytes // 0' 2>/dev/null)

                if [[ -z "${SOURCE_IP}" || -z "${SOURCE_PORT}" ]]; then
                    log_error "Source ready but missing connection details"
                    return 1
                fi

                log "Source is ready!"
                log "  Source IP: ${SOURCE_IP}"
                log "  Source Port: ${SOURCE_PORT}"
                log "  Disk Size: ${DISK_SIZE} bytes ($(format_bytes "${DISK_SIZE}"))"
                return 0
            elif [[ "${status}" == "failed" || "${status}" == "cancelled" ]]; then
                log_error "Clone session ${status}"
                return 1
            fi
        fi

        # Wait before next poll
        sleep ${poll_interval}
        elapsed=$((elapsed + poll_interval))

        if [[ $((elapsed % 30)) -eq 0 ]]; then
            log "Still waiting for source... (${elapsed}s / ${timeout}s)"
        fi
    done

    log_error "Timeout waiting for source to be ready (${timeout}s)"
    return 1
}

# =============================================================================
# Stream disk from source
# =============================================================================

stream_disk() {
    log "Starting disk transfer from source..."

    local source_url="https://${SOURCE_IP}:${SOURCE_PORT}/disk.raw"

    log "Downloading from: ${source_url}"
    log "Writing to: ${PUREBOOT_DEVICE}"

    # Record transfer start time
    TRANSFER_START_TIME=$(date +%s)

    # Report transfer starting
    report_transfer_progress 0 "${DISK_SIZE}" 0 "transferring"

    # Create a named pipe for progress tracking
    rm -f "${PROGRESS_FIFO}"
    mkfifo "${PROGRESS_FIFO}"

    # Start progress monitoring in background
    (
        local last_report_time=${TRANSFER_START_TIME}
        local last_bytes=0

        while IFS= read -r line; do
            # Parse pv output: bytes_transferred
            # pv -n outputs percentage, pv -b outputs bytes
            # We use pv --bytes for raw byte count
            if [[ "${line}" =~ ^[0-9]+$ ]]; then
                BYTES_TRANSFERRED="${line}"
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

                    local percent=0
                    if [[ ${DISK_SIZE} -gt 0 ]]; then
                        percent=$((BYTES_TRANSFERRED * 100 / DISK_SIZE))
                    fi

                    local human_bytes
                    human_bytes=$(format_bytes "${BYTES_TRANSFERRED}")
                    local human_rate
                    human_rate=$(format_bytes "${rate}")

                    log "Transfer progress: ${percent}% (${human_bytes}) at ${human_rate}/s"
                    report_transfer_progress "${BYTES_TRANSFERRED}" "${DISK_SIZE}" "${rate}" "transferring"

                    last_report_time=${current_time}
                    last_bytes=${BYTES_TRANSFERRED}
                fi
            fi
        done < "${PROGRESS_FIFO}"
    ) &
    local progress_pid=$!

    # Perform the transfer using curl -> pv -> dd pipeline
    # curl: download with mTLS
    # pv: monitor progress, output byte count to FIFO
    # dd: write to target device
    local curl_exit=0

    {
        curl -sf \
            --connect-timeout 30 \
            --max-time 0 \
            --cert "${CERT_DIR}/cert.pem" \
            --key "${CERT_DIR}/key.pem" \
            --cacert "${CERT_DIR}/ca.pem" \
            "${source_url}" 2>/dev/null
    } | {
        # pv monitors progress and outputs byte count
        # -f: force output even when not a terminal
        # -n: output percentage (we use --bytes for raw bytes)
        # -b: just count bytes
        # -c: use cursor positioning
        # Output format with -n is just the percentage number
        if command -v pv &>/dev/null; then
            pv -f -n -s "${DISK_SIZE}" 2>"${PROGRESS_FIFO}"
        else
            # Fallback if pv is not available
            cat
        fi
    } | {
        dd of="${PUREBOOT_DEVICE}" bs=4M conv=fsync status=none 2>/dev/null
    } || curl_exit=$?

    # Wait for progress monitor to finish
    sleep 1
    kill ${progress_pid} 2>/dev/null || true
    wait ${progress_pid} 2>/dev/null || true

    # Clean up FIFO
    rm -f "${PROGRESS_FIFO}"

    # Check transfer result
    if [[ ${curl_exit} -ne 0 ]]; then
        log_error "Transfer failed with exit code: ${curl_exit}"
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

    log "Transfer completed: ${human_bytes} in ${transfer_duration}s (avg: ${human_rate}/s)"

    # Report final progress
    report_transfer_progress "${BYTES_TRANSFERRED}" "${DISK_SIZE}" "${avg_rate}" "completed"

    return 0
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
# Main execution
# =============================================================================

log "PureBoot Direct Mode Clone Target starting..."

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

# Wait for source to be ready
if ! wait_for_source; then
    report_failed "Timeout or error waiting for source node" "110"
    exit 1
fi

# Fetch TLS certificates
log "Fetching TLS certificates for target role..."

if ! fetch_certs "target" "${CERT_DIR}"; then
    report_failed "Failed to fetch TLS certificates" "111"
    exit 1
fi

log "TLS certificates fetched successfully"

# Verify certificate files exist
for cert_file in "${CERT_DIR}/cert.pem" "${CERT_DIR}/key.pem" "${CERT_DIR}/ca.pem"; do
    if [[ ! -f "${cert_file}" ]]; then
        report_failed "Certificate file missing: ${cert_file}" "112"
        exit 1
    fi
done

# Stream disk from source
if ! stream_disk; then
    report_failed "Disk transfer failed" "120"
    exit 1
fi

# Verify disk after transfer
if ! verify_disk; then
    report_failed "Disk verification failed" "121"
    exit 1
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
