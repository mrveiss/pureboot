#!/bin/bash
# PureBoot Pi Deploy Mode Dispatcher
# Routes to appropriate script based on boot instructions from controller

set -e

# Source common functions
source /usr/local/bin/pureboot-common.sh
source /usr/local/bin/pureboot-common-arm64.sh

log "=== PureBoot Pi Deploy Dispatcher ==="
log ""
log "Pi Serial: ${PUREBOOT_SERIAL:-$(get_pi_serial)}"
log "Pi Model: ${PUREBOOT_PI_MODEL:-$(get_pi_model)}"
log ""

# Ensure network is up
pi_network_up || {
    log_error "Network setup failed"
    exit 1
}

# If we have a server URL, fetch instructions from API
if [[ -n "${PUREBOOT_SERVER}" ]]; then
    log "Fetching boot instructions from controller..."

    INSTRUCTIONS=$(get_boot_instructions)

    if [[ $? -eq 0 && -n "${INSTRUCTIONS}" ]]; then
        log "Got instructions from controller"

        # Parse JSON response
        STATE=$(echo "${INSTRUCTIONS}" | jq -r '.state // empty')
        ACTION=$(echo "${INSTRUCTIONS}" | jq -r '.action // empty')
        MESSAGE=$(echo "${INSTRUCTIONS}" | jq -r '.message // empty')

        log "  State: ${STATE}"
        log "  Action: ${ACTION}"
        log "  Message: ${MESSAGE}"
        log ""

        # Override cmdline params with API response
        if [[ -n "$(echo "${INSTRUCTIONS}" | jq -r '.image_url // empty')" ]]; then
            PUREBOOT_IMAGE_URL=$(echo "${INSTRUCTIONS}" | jq -r '.image_url')
        fi
        if [[ -n "$(echo "${INSTRUCTIONS}" | jq -r '.target_device // empty')" ]]; then
            PUREBOOT_TARGET=$(echo "${INSTRUCTIONS}" | jq -r '.target_device')
        fi
        if [[ -n "$(echo "${INSTRUCTIONS}" | jq -r '.callback_url // empty')" ]]; then
            PUREBOOT_CALLBACK=$(echo "${INSTRUCTIONS}" | jq -r '.callback_url')
        fi
        if [[ -n "$(echo "${INSTRUCTIONS}" | jq -r '.nfs_server // empty')" ]]; then
            PUREBOOT_NFS_SERVER=$(echo "${INSTRUCTIONS}" | jq -r '.nfs_server')
        fi
        if [[ -n "$(echo "${INSTRUCTIONS}" | jq -r '.nfs_path // empty')" ]]; then
            PUREBOOT_NFS_PATH=$(echo "${INSTRUCTIONS}" | jq -r '.nfs_path')
        fi

        # Export for child scripts
        export PUREBOOT_IMAGE_URL PUREBOOT_TARGET PUREBOOT_CALLBACK
        export PUREBOOT_NFS_SERVER PUREBOOT_NFS_PATH
        export PUREBOOT_STATE="${STATE}"
    else
        log_warn "Could not fetch instructions, using cmdline parameters"
        ACTION="${PUREBOOT_MODE:-}"
    fi
else
    log "No server URL, using cmdline parameters"
    ACTION="${PUREBOOT_MODE:-}"
fi

# If no action determined, register and wait
if [[ -z "${ACTION}" || "${ACTION}" == "null" ]]; then
    log "No action specified, registering Pi..."
    register_pi || true

    log ""
    log "Pi registered with controller."
    log "Assign a workflow and reboot to deploy."
    log ""
    log "Dropping to shell..."
    exec /bin/sh
fi

# Dispatch based on action
case "${ACTION}" in
    deploy_image|install)
        log "Dispatching to image deployment..."
        exec /usr/local/bin/pureboot-pi-image.sh
        ;;
    nfs_boot)
        log "Dispatching to NFS boot setup..."
        exec /usr/local/bin/pureboot-pi-nfs.sh
        ;;
    local_boot)
        log "Instructed to boot locally."
        log "This Pi should boot from local storage on next reboot."
        log ""
        log "Rebooting in 5 seconds..."
        sleep 5
        reboot -f
        ;;
    wait)
        log "Instructed to wait (installation in progress elsewhere)."
        log "Dropping to shell..."
        exec /bin/sh
        ;;
    *)
        log_error "Unknown action: ${ACTION}"
        log "Valid actions: deploy_image, nfs_boot, local_boot, wait"
        log ""
        log "Dropping to shell..."
        exec /bin/sh
        ;;
esac
