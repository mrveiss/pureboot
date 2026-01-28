#!/bin/bash
# PureBoot Pi Image Deployment Script
# Deploys disk images to Raspberry Pi storage (SD card, USB, NVMe)

set -e

# Source common functions (includes ARM64 extensions)
source /usr/local/bin/pureboot-common.sh
source /usr/local/bin/pureboot-common-arm64.sh

# =============================================================================
# Pi Image Deployment
# =============================================================================

# Verify required parameters
verify_pi_params() {
    if [[ -z "${PUREBOOT_IMAGE_URL}" ]]; then
        log_error "Missing pureboot.image_url"
        exit 1
    fi

    if [[ -z "${PUREBOOT_TARGET}" ]]; then
        log "No target specified, auto-detecting..."
        PUREBOOT_TARGET=$(get_pi_boot_device)
        if [[ -z "${PUREBOOT_TARGET}" ]]; then
            log_error "Could not auto-detect target device"
            exit 1
        fi
        log "Auto-detected target: ${PUREBOOT_TARGET}"
    fi

    if [[ ! -b "${PUREBOOT_TARGET}" ]]; then
        log_error "Target device not found: ${PUREBOOT_TARGET}"
        exit 1
    fi
}

# Detect image format from URL
detect_image_format() {
    local url="$1"
    case "${url}" in
        *.raw.gz|*.img.gz)
            echo "raw.gz"
            ;;
        *.raw.xz|*.img.xz)
            echo "raw.xz"
            ;;
        *.raw|*.img)
            echo "raw"
            ;;
        *)
            echo "raw"
            ;;
    esac
}

# Deploy image to Pi storage
deploy_pi_image() {
    local format target_size
    format=$(detect_image_format "${PUREBOOT_IMAGE_URL}")
    target_size=$(blockdev --getsize64 "${PUREBOOT_TARGET}")

    log "=== Deploying Image to Pi ==="
    log "  URL: ${PUREBOOT_IMAGE_URL}"
    log "  Target: ${PUREBOOT_TARGET}"
    log "  Format: ${format}"
    log "  Target size: $((target_size / 1024 / 1024 / 1024)) GB"
    log ""

    # Download and write image
    case "${format}" in
        raw.gz)
            log "Downloading and decompressing gzip image..."
            curl -sfL "${PUREBOOT_IMAGE_URL}" | pigz -d | dd of="${PUREBOOT_TARGET}" bs=4M status=progress conv=fsync
            ;;
        raw.xz)
            log "Downloading and decompressing xz image..."
            curl -sfL "${PUREBOOT_IMAGE_URL}" | xz -d | dd of="${PUREBOOT_TARGET}" bs=4M status=progress conv=fsync
            ;;
        raw)
            log "Downloading raw image..."
            curl -sfL "${PUREBOOT_IMAGE_URL}" | dd of="${PUREBOOT_TARGET}" bs=4M status=progress conv=fsync
            ;;
    esac

    sync
    log "Image written successfully"
}

# Resize partitions to fill disk (Pi-specific)
resize_pi_partitions() {
    log "Resizing partitions to fill disk..."

    # Re-read partition table
    partprobe "${PUREBOOT_TARGET}" 2>/dev/null || true
    sleep 2

    # For SD card (mmcblk0) partitions are mmcblk0p1, mmcblk0p2, etc.
    # For USB/NVMe it's sda1, nvme0n1p1, etc.
    local part_prefix="${PUREBOOT_TARGET}"
    if is_sd_card "${PUREBOOT_TARGET}"; then
        part_prefix="${PUREBOOT_TARGET}p"
    elif [[ "${PUREBOOT_TARGET}" == /dev/nvme* ]]; then
        part_prefix="${PUREBOOT_TARGET}p"
    fi

    # Find last partition
    local last_part last_part_num
    last_part=$(lsblk -n -o NAME "${PUREBOOT_TARGET}" | tail -1)
    last_part_num=$(echo "${last_part}" | sed 's/[^0-9]*//g')

    if [[ -z "${last_part_num}" ]]; then
        log_warn "Could not determine last partition number"
        return 0
    fi

    log "Extending partition ${last_part_num}..."

    # Resize partition using parted
    parted -s "${PUREBOOT_TARGET}" resizepart "${last_part_num}" 100% 2>/dev/null || true

    # Re-read partition table again
    partprobe "${PUREBOOT_TARGET}" 2>/dev/null || true
    sleep 1

    # Resize filesystem
    local part_dev="${part_prefix}${last_part_num}"

    if [[ -b "${part_dev}" ]]; then
        local fstype
        fstype=$(blkid -o value -s TYPE "${part_dev}" 2>/dev/null || echo "")

        case "${fstype}" in
            ext4|ext3|ext2)
                log "Resizing ext filesystem on ${part_dev}..."
                e2fsck -f -y "${part_dev}" 2>/dev/null || true
                resize2fs "${part_dev}" 2>/dev/null || true
                ;;
            btrfs)
                log "Resizing btrfs filesystem on ${part_dev}..."
                mkdir -p /tmp/btrfs_mount
                mount "${part_dev}" /tmp/btrfs_mount
                btrfs filesystem resize max /tmp/btrfs_mount
                umount /tmp/btrfs_mount
                ;;
            *)
                log_warn "Unknown filesystem type: ${fstype}, skipping resize"
                ;;
        esac
    fi

    log "Partition resize complete"
}

# =============================================================================
# Post-Install Configuration
# =============================================================================

# Find root partition on target device
find_root_partition() {
    local device="$1"
    local part_prefix="${device}"

    # Handle partition naming
    if is_sd_card "${device}" || [[ "${device}" == /dev/nvme* ]]; then
        part_prefix="${device}p"
    fi

    # Try common root partition numbers (2 for Pi, 1 for simple images)
    for num in 2 1 3; do
        local part="${part_prefix}${num}"
        if [[ -b "${part}" ]]; then
            local fstype
            fstype=$(blkid -o value -s TYPE "${part}" 2>/dev/null)
            if [[ "${fstype}" =~ ^(ext4|ext3|btrfs|xfs)$ ]]; then
                echo "${part}"
                return 0
            fi
        fi
    done

    return 1
}

# Detect OS type and configure accordingly
configure_os() {
    local mount_point="$1"

    # Detect OS type
    if [[ -f "${mount_point}/etc/rpi-issue" ]] || \
       [[ -f "${mount_point}/etc/apt/sources.list.d/raspi.list" ]]; then
        log "Detected Raspberry Pi OS"
        if [[ -f /usr/local/bin/pureboot-raspios-config.sh ]]; then
            source /usr/local/bin/pureboot-raspios-config.sh
            configure_raspios "${mount_point}" "${PUREBOOT_HOSTNAME:-}"
        fi
    elif [[ -d "${mount_point}/etc/cloud" ]]; then
        log "Detected cloud-init enabled OS (Ubuntu/Debian)"
        if [[ -f /usr/local/bin/pureboot-cloud-init.sh ]]; then
            source /usr/local/bin/pureboot-cloud-init.sh
            configure_cloud_init "${mount_point}" "${PUREBOOT_HOSTNAME:-}" ${PUREBOOT_SSH_KEYS:-}
        fi
    else
        log "Unknown OS type, applying basic configuration"
    fi

    # Always try to enable SSH
    if [[ -f /usr/local/bin/pureboot-cloud-init.sh ]]; then
        source /usr/local/bin/pureboot-cloud-init.sh
        enable_ssh "${mount_point}"
    fi
}

# Run post-install scripts from workflow
run_post_install() {
    if [[ -z "${PUREBOOT_POST_SCRIPT}" ]]; then
        log "No post-install script configured"
        return 0
    fi

    log "Running post-install script..."

    # Mount the target filesystem
    local mount_point="/mnt/target"
    mkdir -p "${mount_point}"

    # Find and mount root partition
    local root_part
    root_part=$(find_root_partition "${PUREBOOT_TARGET}")

    if [[ -z "${root_part}" ]]; then
        log_warn "Could not find root partition for post-install"
        return 1
    fi

    mount "${root_part}" "${mount_point}" || {
        log_error "Failed to mount root partition"
        return 1
    }

    # Download and run script
    local script_file="/tmp/post-install.sh"
    if curl -sfL "${PUREBOOT_POST_SCRIPT}" -o "${script_file}"; then
        chmod +x "${script_file}"

        # Run in chroot if possible
        if [[ -d "${mount_point}/bin" ]]; then
            cp "${script_file}" "${mount_point}/tmp/"
            chroot "${mount_point}" /tmp/post-install.sh || log_warn "Post-install script returned non-zero"
            rm -f "${mount_point}/tmp/post-install.sh"
        else
            "${script_file}" "${mount_point}" || log_warn "Post-install script returned non-zero"
        fi

        log "Post-install script completed"
    else
        log_error "Failed to download post-install script"
    fi

    umount "${mount_point}"
    return 0
}

# Run OS configuration on mounted target
run_os_config() {
    log "Configuring deployed OS..."

    # Mount the target filesystem
    local mount_point="/mnt/target"
    mkdir -p "${mount_point}"

    # Find and mount root partition
    local root_part
    root_part=$(find_root_partition "${PUREBOOT_TARGET}")

    if [[ -z "${root_part}" ]]; then
        log_warn "Could not find root partition for OS config"
        return 0
    fi

    if ! mount "${root_part}" "${mount_point}"; then
        log_warn "Failed to mount root partition for OS config"
        return 0
    fi

    # Configure OS
    configure_os "${mount_point}"

    # Unmount
    umount "${mount_point}"
    log "OS configuration complete"
}

# Notify controller of completion
notify_pi_complete() {
    if [[ -n "${PUREBOOT_CALLBACK}" ]]; then
        log "Notifying controller of completion..."
        curl -sf -X POST "${PUREBOOT_CALLBACK}" \
            -H "Content-Type: application/json" \
            -d '{"success": true}' || log_warn "Failed to notify controller"
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    log "=== PureBoot Pi Image Deployment ==="
    log ""

    # Show configuration
    log "Configuration:"
    log "  Serial: ${PUREBOOT_SERIAL:-$(get_pi_serial)}"
    log "  Model: ${PUREBOOT_PI_MODEL:-$(get_pi_model)}"
    log "  Server: ${PUREBOOT_SERVER:-not set}"
    log "  Node ID: ${PUREBOOT_NODE_ID:-not set}"
    log "  Hostname: ${PUREBOOT_HOSTNAME:-auto}"
    log ""

    verify_pi_params

    deploy_pi_image
    resize_pi_partitions
    run_os_config
    run_post_install
    notify_pi_complete

    log ""
    log "=== Deployment Complete ==="
    log "Rebooting in 5 seconds..."
    sleep 5
    reboot -f
}

main "$@"
