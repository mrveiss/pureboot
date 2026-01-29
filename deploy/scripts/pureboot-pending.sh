#!/bin/bash
# PureBoot Pending Mode Script
# Runs when a node is in pending state without a workflow assigned.
# Scans disks, reports them, and polls for workflow assignment.

set -e

# Source common functions
source /usr/local/bin/pureboot-common.sh

# Poll interval in seconds
POLL_INTERVAL="${PUREBOOT_POLL_INTERVAL:-10}"

# =============================================================================
# Disk Scanning
# =============================================================================

# Scan disks and report to controller
scan_and_report_disks() {
    log "Scanning disks..."

    if [[ ! -x /usr/local/bin/pureboot-disk-scan.sh ]]; then
        log_warn "Disk scan script not found"
        return 1
    fi

    local scan_output
    scan_output=$(/usr/local/bin/pureboot-disk-scan.sh 2>/dev/null)

    if [[ $? -ne 0 || -z "${scan_output}" ]]; then
        log_warn "Disk scan failed or returned no data"
        return 1
    fi

    # Extract disks array and report
    local disks_array
    disks_array=$(echo "${scan_output}" | jq -c '.disks // []')

    local report_data="{\"disks\": ${disks_array}}"
    local endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}/disks/report"

    if api_post "${endpoint}" "${report_data}"; then
        log "Disk information reported to controller"
        return 0
    else
        log_warn "Failed to report disk info"
        return 1
    fi
}

# =============================================================================
# Workflow Polling
# =============================================================================

# Check if a workflow has been assigned
check_workflow_assigned() {
    local endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}"
    local url="${PUREBOOT_SERVER}${endpoint}"

    local response
    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        "${url}" 2>/dev/null)

    if [[ $? -ne 0 ]]; then
        log_debug "Failed to check node status"
        return 1
    fi

    local workflow_id
    workflow_id=$(echo "${response}" | jq -r '.data.workflow_id // empty')

    if [[ -n "${workflow_id}" && "${workflow_id}" != "null" ]]; then
        log "Workflow assigned: ${workflow_id}"
        echo "${workflow_id}"
        return 0
    fi

    return 1
}

# =============================================================================
# Main Loop
# =============================================================================

main() {
    log "=== PureBoot Pending Mode ==="
    log ""
    log "Configuration:"
    log "  Server:   ${PUREBOOT_SERVER:-not set}"
    log "  Node ID:  ${PUREBOOT_NODE_ID:-not set}"
    log "  MAC:      ${PUREBOOT_MAC:-not set}"
    log ""

    # Verify required parameters
    if [[ -z "${PUREBOOT_SERVER}" ]]; then
        log_error "PUREBOOT_SERVER not set"
        log "Dropping to shell..."
        exec /bin/sh
    fi

    if [[ -z "${PUREBOOT_NODE_ID}" ]]; then
        log_error "PUREBOOT_NODE_ID not set"
        log "Dropping to shell..."
        exec /bin/sh
    fi

    # Initial disk scan
    scan_and_report_disks

    log ""
    log "Waiting for workflow assignment..."
    log "Poll interval: ${POLL_INTERVAL}s"
    log ""

    # Poll for workflow assignment
    while true; do
        local workflow_id
        if workflow_id=$(check_workflow_assigned); then
            log ""
            log "Workflow ${workflow_id} assigned!"
            log "Rebooting to start workflow execution..."
            sleep 3
            reboot -f
        fi

        # Check if a disk rescan was requested
        local scan_endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}/disks/scan-status"
        local scan_response
        scan_response=$(curl -sf "${PUREBOOT_SERVER}${scan_endpoint}" 2>/dev/null)

        if [[ $? -eq 0 ]]; then
            local scan_requested
            scan_requested=$(echo "${scan_response}" | jq -r '.data.scan_requested // false')

            if [[ "${scan_requested}" == "true" ]]; then
                log "Disk rescan requested"
                scan_and_report_disks
            fi
        fi

        log_debug "No workflow yet, sleeping ${POLL_INTERVAL}s..."
        sleep "${POLL_INTERVAL}"
    done
}

main "$@"
