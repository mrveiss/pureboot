#!/bin/bash
# PureBoot Pi NFS Boot Setup
# Configures Pi for NFS root filesystem (diskless operation)
# Note: Full NFS support is Phase 4

set -e

source /usr/local/bin/pureboot-common.sh
source /usr/local/bin/pureboot-common-arm64.sh

log "=== PureBoot Pi NFS Boot Setup ==="
log ""

# This is a placeholder for Phase 4 (Diskless/NFS Support)
# For now, display configuration and drop to shell

log "NFS boot configuration:"
log "  NFS Server: ${PUREBOOT_NFS_SERVER:-not set}"
log "  NFS Path: ${PUREBOOT_NFS_PATH:-not set}"
log ""

if [[ -z "${PUREBOOT_NFS_SERVER}" || -z "${PUREBOOT_NFS_PATH}" ]]; then
    log_error "NFS parameters not configured"
    log "Required: pureboot.nfs_server and pureboot.nfs_path"
    log ""
    log "Dropping to shell..."
    exec /bin/sh
fi

# Basic NFS root pivot (simplified)
log "Mounting NFS root..."

mkdir -p /mnt/nfsroot

if mount -t nfs -o rw,vers=4 "${PUREBOOT_NFS_SERVER}:${PUREBOOT_NFS_PATH}" /mnt/nfsroot; then
    log "NFS root mounted successfully"

    # Check if it's a valid rootfs
    if [[ -d /mnt/nfsroot/bin && -d /mnt/nfsroot/etc ]]; then
        log "Valid root filesystem detected"
        log ""
        log "NFS root is ready at /mnt/nfsroot"
        log "Full pivot_root support coming in Phase 4"
        log ""
        log "Dropping to shell..."
        exec /bin/sh
    else
        log_error "NFS mount doesn't contain valid root filesystem"
        umount /mnt/nfsroot
    fi
else
    log_error "Failed to mount NFS root"
fi

log ""
log "Dropping to shell..."
exec /bin/sh
