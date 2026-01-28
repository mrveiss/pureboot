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
    log ""

    verify_pi_params

    deploy_pi_image
    resize_pi_partitions
    notify_pi_complete

    log ""
    log "=== Deployment Complete ==="
    log "Rebooting in 5 seconds..."
    sleep 5
    reboot -f
}

main "$@"