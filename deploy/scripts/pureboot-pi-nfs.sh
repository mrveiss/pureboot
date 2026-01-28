#!/bin/bash
# PureBoot Pi NFS Boot Setup
# Boots Pi from NFS root filesystem with overlayfs

set -e

source /usr/local/bin/pureboot-common.sh
source /usr/local/bin/pureboot-common-arm64.sh

log "=== PureBoot Pi NFS Boot Setup ==="
log ""

# =============================================================================
# NFS Boot Configuration
# =============================================================================

log "NFS boot configuration:"
log "  NFS Server: ${PUREBOOT_NFS_SERVER:-not set}"
log "  NFS Path: ${PUREBOOT_NFS_PATH:-not set}"
log "  Serial: ${PUREBOOT_SERIAL:-$(get_pi_serial)}"
log ""

if [[ -z "${PUREBOOT_NFS_SERVER}" || -z "${PUREBOOT_NFS_PATH}" ]]; then
    log_error "NFS parameters not configured"
    log "Required: pureboot.nfs_server and pureboot.nfs_path"
    log ""
    log "Dropping to shell..."
    exec /bin/sh
fi

# Get serial for per-node overlay
SERIAL="${PUREBOOT_SERIAL:-$(get_pi_serial)}"
if [[ -z "${SERIAL}" ]]; then
    log_error "Could not determine Pi serial number"
    exec /bin/sh
fi

# =============================================================================
# Mount NFS Root
# =============================================================================

NFS_MOUNT="/mnt/nfs"
OVERLAY_MOUNT="/mnt/overlay"
NEWROOT="/mnt/newroot"

mkdir -p "${NFS_MOUNT}" "${OVERLAY_MOUNT}" "${NEWROOT}"

log "Mounting NFS share..."
if ! mount -t nfs -o rw,vers=4,nolock "${PUREBOOT_NFS_SERVER}:${PUREBOOT_NFS_PATH}" "${NFS_MOUNT}"; then
    log_error "Failed to mount NFS root with NFSv4"
    log "Trying NFSv3..."
    if ! mount -t nfs -o rw,vers=3,nolock "${PUREBOOT_NFS_SERVER}:${PUREBOOT_NFS_PATH}" "${NFS_MOUNT}"; then
        log_error "NFS mount failed completely"
        exec /bin/sh
    fi
fi
log "NFS mounted at ${NFS_MOUNT}"

# =============================================================================
# Setup Overlay Filesystem
# =============================================================================

# Check for overlay directories
BASE_DIR="${NFS_MOUNT}/base"
NODE_DIR="${NFS_MOUNT}/nodes/${SERIAL}"

if [[ ! -d "${BASE_DIR}" ]]; then
    log_error "Base directory not found: ${BASE_DIR}"
    log "Available in NFS mount:"
    ls -la "${NFS_MOUNT}" 2>/dev/null || true
    exec /bin/sh
fi

# Find base image (first directory in base/)
BASE_IMAGE=$(ls -1 "${BASE_DIR}" 2>/dev/null | head -1)
if [[ -z "${BASE_IMAGE}" ]]; then
    log_error "No base images found in ${BASE_DIR}"
    exec /bin/sh
fi
BASE_PATH="${BASE_DIR}/${BASE_IMAGE}"
log "Using base image: ${BASE_IMAGE}"

# Create node overlay directories if needed
if [[ ! -d "${NODE_DIR}" ]]; then
    log "Creating overlay directories for ${SERIAL}..."
    mkdir -p "${NODE_DIR}/upper" "${NODE_DIR}/work"

    # Set up basic per-node config
    mkdir -p "${NODE_DIR}/upper/etc"
    echo "pi-${SERIAL}" > "${NODE_DIR}/upper/etc/hostname"
    cat /proc/sys/kernel/random/uuid | tr -d '-' > "${NODE_DIR}/upper/etc/machine-id"
fi

# Mount overlayfs
log "Mounting overlay filesystem..."
if ! mount -t overlay overlay -o "lowerdir=${BASE_PATH},upperdir=${NODE_DIR}/upper,workdir=${NODE_DIR}/work" "${NEWROOT}"; then
    log_error "Failed to mount overlay filesystem"
    log "Attempting direct NFS root mount..."
    if ! mount --bind "${BASE_PATH}" "${NEWROOT}"; then
        log_error "Failed to mount root filesystem"
        exec /bin/sh
    fi
    log_warn "Running with read-only base (no overlay)"
fi

log "Overlay mounted at ${NEWROOT}"

# =============================================================================
# Prepare for pivot_root
# =============================================================================

# Verify we have a valid root filesystem
if [[ ! -x "${NEWROOT}/sbin/init" && ! -x "${NEWROOT}/lib/systemd/systemd" ]]; then
    log_error "No init found in new root"
    log "Contents of ${NEWROOT}:"
    ls -la "${NEWROOT}" 2>/dev/null || true
    exec /bin/sh
fi

# Create required mount points in new root
mkdir -p "${NEWROOT}/proc" "${NEWROOT}/sys" "${NEWROOT}/dev" "${NEWROOT}/run"

# Move existing mounts to new root
log "Moving mounts to new root..."
mount --move /proc "${NEWROOT}/proc" 2>/dev/null || mount -t proc proc "${NEWROOT}/proc"
mount --move /sys "${NEWROOT}/sys" 2>/dev/null || mount -t sysfs sysfs "${NEWROOT}/sys"
mount --move /dev "${NEWROOT}/dev" 2>/dev/null || mount -t devtmpfs devtmpfs "${NEWROOT}/dev"

# =============================================================================
# Switch Root
# =============================================================================

log ""
log "=== Switching to NFS root ==="
log ""

# Notify controller if callback configured
if [[ -n "${PUREBOOT_CALLBACK}" ]]; then
    curl -sf -X POST "${PUREBOOT_CALLBACK}" \
        -H "Content-Type: application/json" \
        -d '{"success": true, "mode": "nfs_boot"}' 2>/dev/null || true
fi

# Determine init path
if [[ -x "${NEWROOT}/lib/systemd/systemd" ]]; then
    INIT="/lib/systemd/systemd"
elif [[ -x "${NEWROOT}/sbin/init" ]]; then
    INIT="/sbin/init"
else
    INIT="/bin/sh"
fi

log "Executing switch_root to ${INIT}..."

# Clean up old root and switch
cd "${NEWROOT}"
mkdir -p "${NEWROOT}/oldroot"

# Use switch_root (preferred) or pivot_root
if command -v switch_root &>/dev/null; then
    exec switch_root "${NEWROOT}" "${INIT}"
else
    pivot_root "${NEWROOT}" "${NEWROOT}/oldroot"
    exec chroot . "${INIT}" <dev/console >dev/console 2>&1
fi

# Should never reach here
log_error "Failed to switch root"
exec /bin/sh
