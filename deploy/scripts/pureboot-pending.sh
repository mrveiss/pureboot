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
# Command Polling
# =============================================================================

# Check for pending commands from controller
check_pending_command() {
    local endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}/command?clear=true"
    local url="${PUREBOOT_SERVER}${endpoint}"

    local response
    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        "${url}" 2>/dev/null)

    if [[ $? -ne 0 ]]; then
        return 1
    fi

    local command
    command=$(echo "${response}" | jq -r '.data.command // empty')

    if [[ -n "${command}" && "${command}" != "null" ]]; then
        echo "${command}"
        return 0
    fi

    return 1
}

# Execute a command
execute_command() {
    local command="$1"

    case "${command}" in
        poweroff)
            log ""
            log "=== Poweroff command received ==="
            log "Shutting down in 3 seconds..."
            sleep 3
            poweroff -f
            ;;
        reboot)
            log ""
            log "=== Reboot command received ==="
            log "Rebooting in 3 seconds..."
            sleep 3
            reboot -f
            ;;
        rescan)
            log ""
            log "=== Rescan command received ==="
            scan_and_report_disks
            ;;
        *)
            log_warn "Unknown command: ${command}"
            return 1
            ;;
    esac
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
            log "Fetching workflow instructions..."

            # Fetch boot instructions from controller
            local instructions_endpoint="/api/v1/boot/instructions?mac=${PUREBOOT_MAC}"
            local instructions
            instructions=$(curl -sf "${PUREBOOT_SERVER}${instructions_endpoint}" 2>/dev/null)

            if [[ $? -eq 0 && -n "${instructions}" ]]; then
                # Parse action/mode from instructions
                local action
                action=$(echo "${instructions}" | jq -r '.action // .mode // empty')

                # Export any additional parameters
                export PUREBOOT_IMAGE_URL=$(echo "${instructions}" | jq -r '.image_url // empty')
                export PUREBOOT_TARGET=$(echo "${instructions}" | jq -r '.target_device // empty')
                export PUREBOOT_SOURCE_DEVICE=$(echo "${instructions}" | jq -r '.source_device // empty')
                export PUREBOOT_CALLBACK=$(echo "${instructions}" | jq -r '.callback_url // empty')

                log "Action: ${action}"

                # Dispatch to appropriate script
                case "${action}" in
                    clone_source_direct)
                        exec /usr/local/bin/pureboot-clone-source-direct.sh
                        ;;
                    clone_target_direct)
                        exec /usr/local/bin/pureboot-clone-target-direct.sh
                        ;;
                    clone_source_staged)
                        exec /usr/local/bin/pureboot-clone-source-staged.sh
                        ;;
                    clone_target_staged)
                        exec /usr/local/bin/pureboot-clone-target-staged.sh
                        ;;
                    partition)
                        exec /usr/local/bin/pureboot-partition.sh
                        ;;
                    deploy_image|install|image)
                        exec /usr/local/bin/pureboot-image.sh
                        ;;
                    local_boot)
                        log "Instructed to boot locally. Rebooting..."
                        sleep 3
                        reboot -f
                        ;;
                    *)
                        log_warn "Unknown action: ${action}, continuing to poll..."
                        ;;
                esac
            else
                log_warn "Failed to fetch workflow instructions, will retry..."
            fi
        fi

        # Check for pending commands (poweroff, reboot, rescan)
        local pending_cmd
        if pending_cmd=$(check_pending_command); then
            log "Command received: ${pending_cmd}"
            execute_command "${pending_cmd}"
            # If we get here (rescan), continue polling
        fi

        # Check if a disk rescan was requested (legacy scan-status endpoint)
        local scan_endpoint="/api/v1/nodes/${PUREBOOT_NODE_ID}/disks/scan-status"
        local scan_response
        scan_response=$(curl -sf "${PUREBOOT_SERVER}${scan_endpoint}" 2>/dev/null)

        if [[ $? -eq 0 ]]; then
            local scan_requested
            scan_requested=$(echo "${scan_response}" | jq -r '.data.scan_requested // false')

            if [[ "${scan_requested}" == "true" ]]; then
                log "Disk rescan requested (legacy)"
                scan_and_report_disks
            fi
        fi

        log_debug "No workflow yet, sleeping ${POLL_INTERVAL}s..."
        sleep "${POLL_INTERVAL}"
    done
}

main "$@"
