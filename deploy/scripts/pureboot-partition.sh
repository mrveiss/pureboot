#!/bin/bash
# PureBoot Partition Mode Boot Script
# Main entry point for partition management mode (pureboot.mode=partition).
# Scans disks, reports to controller, polls for operations, and executes them.
#
# This script stays online until receiving a shutdown signal, allowing
# interactive partition management from the controller.

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Polling interval in seconds
POLL_INTERVAL=5

# Heartbeat interval in seconds (report online status)
HEARTBEAT_INTERVAL=30

# Shutdown flag
SHUTDOWN_REQUESTED=false

# Last heartbeat timestamp
LAST_HEARTBEAT=0

# =============================================================================
# Source common functions
# =============================================================================

# Try multiple locations for common script
if [[ -f "${SCRIPT_DIR}/pureboot-common.sh" ]]; then
    source "${SCRIPT_DIR}/pureboot-common.sh"
elif [[ -f "/usr/local/bin/pureboot-common.sh" ]]; then
    source "/usr/local/bin/pureboot-common.sh"
else
    echo "ERROR: Cannot find pureboot-common.sh" >&2
    exit 1
fi

# =============================================================================
# Signal Handling
# =============================================================================

# Handle shutdown signals gracefully
handle_shutdown() {
    log "Shutdown signal received"
    SHUTDOWN_REQUESTED=true
}

# Set up signal traps
trap handle_shutdown SIGTERM SIGINT

# =============================================================================
# Cleanup Function
# =============================================================================

cleanup() {
    log "Cleaning up..."

    # Flush any remaining queued updates
    flush_queue

    # Report offline status to controller
    if [[ -n "${PUREBOOT_SERVER}" && -n "${PUREBOOT_NODE_ID}" ]]; then
        local offline_data
        offline_data=$(cat << EOF
{
    "status": "offline",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)
        api_post "/api/v1/nodes/${PUREBOOT_NODE_ID}/partition-mode/status" "${offline_data}" || true
    fi

    log "Cleanup complete"
}

# Set up cleanup trap
trap cleanup EXIT

# =============================================================================
# API Functions
# =============================================================================

# Report disk information to controller
# Usage: report_disk_info
report_disk_info() {
    log "Scanning disks..."

    # Use pureboot-disk-scan.sh to get disk information
    local scan_output
    if [[ -f "${SCRIPT_DIR}/pureboot-disk-scan.sh" ]]; then
        scan_output=$("${SCRIPT_DIR}/pureboot-disk-scan.sh" 2>/dev/null)
    elif [[ -f "/usr/local/bin/pureboot-disk-scan.sh" ]]; then
        scan_output=$(/usr/local/bin/pureboot-disk-scan.sh 2>/dev/null)
    else
        log_error "Cannot find pureboot-disk-scan.sh"
        return 1
    fi

    if [[ -z "${scan_output}" ]]; then
        log_error "Disk scan returned empty output"
        return 1
    fi

    # Validate JSON
    if ! echo "${scan_output}" | jq . &>/dev/null; then
        log_error "Disk scan returned invalid JSON"
        return 1
    fi

    # Build report payload
    local report_data
    report_data=$(cat << EOF
{
    "node_id": "${PUREBOOT_NODE_ID}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "scan_result": ${scan_output}
}
EOF
)

    local endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}/disks/report"

    if api_post "${endpoint}" "${report_data}"; then
        log "Disk information reported successfully"
        return 0
    else
        log_warn "Failed to report disk information, queuing for retry"
        queue_update "${endpoint}" "${report_data}"
        return 1
    fi
}

# Poll controller for pending partition operations
# Usage: operations_json=$(poll_operations)
poll_operations() {
    local endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}/partition-operations?status=pending"
    local url="${PUREBOOT_SERVER}${endpoint}"
    local response

    log_debug "Polling for pending operations: ${url}"

    # Make GET request
    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        "${url}" 2>/dev/null)

    local curl_exit=$?

    if [[ ${curl_exit} -ne 0 ]]; then
        log_debug "Poll request failed with curl exit code: ${curl_exit}"
        return 1
    fi

    # Validate response is JSON
    if ! echo "${response}" | jq . &>/dev/null; then
        log_debug "Poll response is not valid JSON"
        return 1
    fi

    echo "${response}"
    return 0
}

# Report operation status to controller
# Usage: report_op_status "op_id" "status" "message" ["result_json"]
report_op_status() {
    local op_id="$1"
    local status="$2"
    local message="$3"
    local result="${4:-null}"

    local endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}/partition-operations/${op_id}/status"

    local status_data
    status_data=$(cat << EOF
{
    "status": "${status}",
    "message": "${message}",
    "result": ${result},
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    if api_post "${endpoint}" "${status_data}"; then
        log_debug "Operation status reported: ${op_id} -> ${status}"
        return 0
    else
        log_warn "Failed to report operation status, queuing for retry"
        queue_update "${endpoint}" "${status_data}"
        return 1
    fi
}

# Send heartbeat to controller
# Usage: send_heartbeat
send_heartbeat() {
    local endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}/partition-mode/heartbeat"

    local heartbeat_data
    heartbeat_data=$(cat << EOF
{
    "status": "online",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    if api_post "${endpoint}" "${heartbeat_data}"; then
        log_debug "Heartbeat sent successfully"
        return 0
    else
        log_debug "Failed to send heartbeat"
        return 1
    fi
}

# =============================================================================
# Operation Execution
# =============================================================================

# Execute a single partition operation
# Usage: execute_operation "operation_json"
# Returns: 0 on success, 1 on failure
execute_operation() {
    local op_json="$1"
    local op_id operation device params

    # Parse operation details
    op_id=$(echo "${op_json}" | jq -r '.id // empty')
    operation=$(echo "${op_json}" | jq -r '.operation // empty')
    device=$(echo "${op_json}" | jq -r '.device // empty')
    params=$(echo "${op_json}" | jq -c '.params // {}')

    if [[ -z "${op_id}" ]]; then
        log_error "Operation missing ID"
        return 1
    fi

    if [[ -z "${operation}" ]]; then
        log_error "Operation ${op_id} missing operation type"
        report_op_status "${op_id}" "failed" "Missing operation type"
        return 1
    fi

    log "Executing operation ${op_id}: ${operation} on ${device}"

    # Report operation as in progress
    report_op_status "${op_id}" "in_progress" "Starting ${operation}"

    # Build operation JSON for partition-ops script
    local op_input
    op_input=$(cat << EOF
{
    "operation": "${operation}",
    "device": "${device}",
    "params": ${params}
}
EOF
)

    # Execute operation using pureboot-partition-ops.sh
    local result
    local exit_code

    if [[ -f "${SCRIPT_DIR}/pureboot-partition-ops.sh" ]]; then
        result=$("${SCRIPT_DIR}/pureboot-partition-ops.sh" "${op_input}" 2>&1) || exit_code=$?
    elif [[ -f "/usr/local/bin/pureboot-partition-ops.sh" ]]; then
        result=$(/usr/local/bin/pureboot-partition-ops.sh "${op_input}" 2>&1) || exit_code=$?
    else
        log_error "Cannot find pureboot-partition-ops.sh"
        report_op_status "${op_id}" "failed" "Partition operations script not found"
        return 1
    fi

    exit_code=${exit_code:-0}

    # Parse result
    local result_status result_message result_data

    if echo "${result}" | jq . &>/dev/null; then
        result_status=$(echo "${result}" | jq -r '.status // "unknown"')
        result_message=$(echo "${result}" | jq -r '.message // "No message"')
        result_data=$(echo "${result}" | jq -c '.data // null')
    else
        # Non-JSON output (error case)
        result_status="error"
        result_message="${result}"
        result_data="null"
    fi

    if [[ "${result_status}" == "success" ]]; then
        log "Operation ${op_id} completed successfully: ${result_message}"
        report_op_status "${op_id}" "completed" "${result_message}" "${result_data}"
        return 0
    else
        log_error "Operation ${op_id} failed: ${result_message}"
        report_op_status "${op_id}" "failed" "${result_message}" "${result_data}"
        return 1
    fi
}

# Execute all pending operations
# Usage: execute_pending_ops "operations_json"
execute_pending_ops() {
    local ops_json="$1"
    local operations_count
    local success_count=0
    local fail_count=0

    # Get number of operations
    operations_count=$(echo "${ops_json}" | jq '.operations | length' 2>/dev/null || echo "0")

    if [[ "${operations_count}" -eq 0 ]]; then
        log_debug "No pending operations"
        return 0
    fi

    log "Found ${operations_count} pending operation(s)"

    # Execute each operation
    local i
    for ((i = 0; i < operations_count; i++)); do
        local op
        op=$(echo "${ops_json}" | jq -c ".operations[${i}]")

        if execute_operation "${op}"; then
            ((success_count++))
        else
            ((fail_count++))
        fi

        # Check for shutdown between operations
        if [[ "${SHUTDOWN_REQUESTED}" == "true" ]]; then
            log "Shutdown requested, stopping operation execution"
            break
        fi
    done

    log "Operations completed: ${success_count} succeeded, ${fail_count} failed"

    # Return failure if any operations failed
    if [[ ${fail_count} -gt 0 ]]; then
        return 1
    fi

    return 0
}

# =============================================================================
# Main Loop
# =============================================================================

# Main polling loop
main_loop() {
    log "Entering main polling loop (interval: ${POLL_INTERVAL}s)"

    while [[ "${SHUTDOWN_REQUESTED}" != "true" ]]; do
        local current_time
        current_time=$(date +%s)

        # Send heartbeat periodically
        if [[ $((current_time - LAST_HEARTBEAT)) -ge ${HEARTBEAT_INTERVAL} ]]; then
            send_heartbeat
            LAST_HEARTBEAT=${current_time}
        fi

        # Try to flush any queued updates
        flush_queue

        # Poll for pending operations
        local pending_ops
        if pending_ops=$(poll_operations); then
            # Check if there are operations to execute
            local op_count
            op_count=$(echo "${pending_ops}" | jq '.operations | length' 2>/dev/null || echo "0")

            if [[ "${op_count}" -gt 0 ]]; then
                # Execute pending operations
                if execute_pending_ops "${pending_ops}"; then
                    # Re-scan and report disk info after successful operations
                    log "Re-scanning disks after operations..."
                    report_disk_info
                else
                    # Still re-scan even if some ops failed
                    log "Re-scanning disks after operations (some failed)..."
                    report_disk_info
                fi
            fi
        else
            log_debug "Failed to poll for operations, will retry"
        fi

        # Sleep until next poll (interruptible by signals)
        local sleep_count=0
        while [[ ${sleep_count} -lt ${POLL_INTERVAL} && "${SHUTDOWN_REQUESTED}" != "true" ]]; do
            sleep 1
            ((sleep_count++))
        done
    done

    log "Main loop exited"
}

# =============================================================================
# Main Function
# =============================================================================

main() {
    log "=== PureBoot Partition Mode ==="
    log "Starting partition management..."

    # Validate required parameters
    if [[ -z "${PUREBOOT_SERVER}" ]]; then
        log_error "PUREBOOT_SERVER not set. Cannot communicate with controller."
        exit 1
    fi

    if [[ -z "${PUREBOOT_NODE_ID}" ]]; then
        log_error "PUREBOOT_NODE_ID not set. Node not identified."
        exit 1
    fi

    log "Configuration:"
    log "  Server: ${PUREBOOT_SERVER}"
    log "  Node ID: ${PUREBOOT_NODE_ID}"
    log "  Poll Interval: ${POLL_INTERVAL}s"
    log "  Heartbeat Interval: ${HEARTBEAT_INTERVAL}s"

    # Get local IP address
    local local_ip
    local_ip=$(get_local_ip)
    if [[ -n "${local_ip}" ]]; then
        log "  Local IP: ${local_ip}"
    fi

    # Report online status to controller
    log "Reporting online status to controller..."
    local online_data
    online_data=$(cat << EOF
{
    "status": "online",
    "ip": "${local_ip}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    if api_post "/api/v1/nodes/${PUREBOOT_NODE_ID}/partition-mode/status" "${online_data}"; then
        log "Online status reported successfully"
    else
        log_warn "Failed to report online status, continuing anyway"
        queue_update "/api/v1/nodes/${PUREBOOT_NODE_ID}/partition-mode/status" "${online_data}"
    fi

    # Initial disk scan and report
    log "Performing initial disk scan..."
    if report_disk_info; then
        log "Initial disk scan completed"
    else
        log_warn "Initial disk scan failed, will retry in main loop"
    fi

    # Initialize heartbeat timestamp
    LAST_HEARTBEAT=$(date +%s)

    # Enter main loop
    main_loop

    log "=== PureBoot Partition Mode Complete ==="
}

# =============================================================================
# Entry Point
# =============================================================================

main "$@"
