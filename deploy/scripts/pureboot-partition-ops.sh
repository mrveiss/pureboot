#!/bin/bash
# PureBoot Partition Operations Script
# Executes partition operations (resize, create, delete, format, set_flag) on a node.
# Called by the partition mode script with JSON operation parameters.
#
# Usage: pureboot-partition-ops.sh '<json_operation>'
#        echo '<json_operation>' | pureboot-partition-ops.sh
#
# Example:
#   pureboot-partition-ops.sh '{"operation": "resize", "device": "/dev/sda", "params": {"partition": 2, "new_size_bytes": 107374182400}}'

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
# JSON Helper Functions
# =============================================================================

# Output a JSON result object
# Usage: json_result "success" "message"
#        json_result "error" "error message"
json_result() {
    local status="$1"
    local message="$2"
    local data="${3:-null}"

    if [[ "${status}" == "success" ]]; then
        echo "{\"status\": \"success\", \"message\": \"${message}\", \"data\": ${data}}"
    else
        echo "{\"status\": \"error\", \"message\": \"${message}\", \"data\": ${data}}"
    fi
}

# Parse JSON value using jq
# Usage: value=$(json_get ".params.partition" "${json}")
json_get() {
    local path="$1"
    local json="$2"
    echo "${json}" | jq -r "${path} // empty" 2>/dev/null
}

# =============================================================================
# Validation Functions
# =============================================================================

# Check if device exists and is a block device
# Usage: validate_device "/dev/sda"
validate_device() {
    local device="$1"

    if [[ -z "${device}" ]]; then
        log_error "Device not specified"
        return 1
    fi

    if [[ ! -b "${device}" ]]; then
        log_error "Device not found or not a block device: ${device}"
        return 1
    fi

    return 0
}

# Check if partition exists on device
# Usage: validate_partition "/dev/sda" 2
validate_partition() {
    local device="$1"
    local part_num="$2"
    local part_device

    if [[ -z "${part_num}" ]] || ! [[ "${part_num}" =~ ^[0-9]+$ ]]; then
        log_error "Invalid partition number: ${part_num}"
        return 1
    fi

    # Build partition device name
    part_device=$(get_partition_device "${device}" "${part_num}")

    if [[ ! -b "${part_device}" ]]; then
        log_error "Partition not found: ${part_device}"
        return 1
    fi

    return 0
}

# Get partition device path from disk and partition number
# Usage: part_device=$(get_partition_device "/dev/sda" 2)
get_partition_device() {
    local device="$1"
    local part_num="$2"

    # Handle NVMe and mmcblk devices (need 'p' separator)
    if [[ "${device}" =~ nvme[0-9]+n[0-9]+$ ]] || [[ "${device}" =~ mmcblk[0-9]+$ ]]; then
        echo "${device}p${part_num}"
    else
        echo "${device}${part_num}"
    fi
}

# Get current partition size in bytes
# Usage: size=$(get_partition_size "/dev/sda" 2)
get_partition_size() {
    local device="$1"
    local part_num="$2"
    local part_device

    part_device=$(get_partition_device "${device}" "${part_num}")
    blockdev --getsize64 "${part_device}" 2>/dev/null
}

# Get filesystem type for a partition
# Usage: fstype=$(get_filesystem_type "/dev/sda1")
get_filesystem_type() {
    local part_device="$1"
    blkid -o value -s TYPE "${part_device}" 2>/dev/null || true
}

# Check if partition is mounted
# Usage: if is_mounted "/dev/sda1"; then ...
is_mounted() {
    local part_device="$1"
    findmnt -n "${part_device}" &>/dev/null
}

# Get mount point for a partition
# Usage: mount_point=$(get_mount_point "/dev/sda1")
get_mount_point() {
    local part_device="$1"
    findmnt -n -o TARGET "${part_device}" 2>/dev/null | head -1
}

# =============================================================================
# Filesystem Operations
# =============================================================================

# Resize ext4 filesystem
# Usage: resize_ext4 "/dev/sda1" 107374182400
resize_ext4() {
    local part_device="$1"
    local new_size_bytes="$2"
    local current_size

    current_size=$(blockdev --getsize64 "${part_device}" 2>/dev/null)

    log "Resizing ext4 filesystem on ${part_device}"

    # Must be unmounted for resize
    if is_mounted "${part_device}"; then
        log_error "Partition ${part_device} must be unmounted for ext4 resize"
        return 1
    fi

    # Always run filesystem check first
    log "Running filesystem check on ${part_device}"
    if ! e2fsck -f -y "${part_device}" &>/dev/null; then
        log_warn "Filesystem check reported issues, continuing anyway"
    fi

    if [[ ${new_size_bytes} -lt ${current_size} ]]; then
        # Shrinking: resize filesystem first
        local new_size_kb=$((new_size_bytes / 1024))
        log "Shrinking ext4 filesystem to ${new_size_kb}K"
        if ! resize2fs "${part_device}" "${new_size_kb}K"; then
            log_error "Failed to shrink ext4 filesystem"
            return 1
        fi
    else
        # Growing: filesystem will be resized after partition resize
        log "ext4 filesystem will be grown after partition resize"
    fi

    return 0
}

# Grow ext4 filesystem to fill partition
# Usage: grow_ext4 "/dev/sda1"
grow_ext4() {
    local part_device="$1"

    log "Growing ext4 filesystem on ${part_device} to fill partition"

    if is_mounted "${part_device}"; then
        # Can grow online for ext4
        if ! resize2fs "${part_device}"; then
            log_error "Failed to grow ext4 filesystem"
            return 1
        fi
    else
        # Offline grow
        e2fsck -f -y "${part_device}" &>/dev/null || true
        if ! resize2fs "${part_device}"; then
            log_error "Failed to grow ext4 filesystem"
            return 1
        fi
    fi

    return 0
}

# Resize NTFS filesystem
# Usage: resize_ntfs "/dev/sda1" 107374182400
resize_ntfs() {
    local part_device="$1"
    local new_size_bytes="$2"

    log "Resizing NTFS filesystem on ${part_device}"

    # NTFS must be unmounted
    if is_mounted "${part_device}"; then
        log_error "Partition ${part_device} must be unmounted for NTFS resize"
        return 1
    fi

    # ntfsresize requires --force for automated use
    if ! ntfsresize -f -s "${new_size_bytes}" "${part_device}"; then
        log_error "Failed to resize NTFS filesystem"
        return 1
    fi

    return 0
}

# Grow NTFS filesystem to fill partition
# Usage: grow_ntfs "/dev/sda1"
grow_ntfs() {
    local part_device="$1"

    log "Growing NTFS filesystem on ${part_device} to fill partition"

    if is_mounted "${part_device}"; then
        log_error "Partition ${part_device} must be unmounted for NTFS resize"
        return 1
    fi

    # ntfsresize without -s grows to fill partition
    if ! ntfsresize -f "${part_device}"; then
        log_error "Failed to grow NTFS filesystem"
        return 1
    fi

    return 0
}

# Resize XFS filesystem (grow only, must be mounted)
# Usage: resize_xfs "/dev/sda1" 107374182400
resize_xfs() {
    local part_device="$1"
    local new_size_bytes="$2"
    local current_size mount_point

    current_size=$(blockdev --getsize64 "${part_device}" 2>/dev/null)

    log "Resizing XFS filesystem on ${part_device}"

    # XFS can only grow, not shrink
    if [[ ${new_size_bytes} -lt ${current_size} ]]; then
        log_error "XFS filesystems cannot be shrunk, only grown"
        return 1
    fi

    # XFS must be mounted to resize
    if ! is_mounted "${part_device}"; then
        log_error "XFS filesystem must be mounted to resize"
        return 1
    fi

    mount_point=$(get_mount_point "${part_device}")

    # xfs_growfs works on mount point
    if ! xfs_growfs "${mount_point}"; then
        log_error "Failed to grow XFS filesystem"
        return 1
    fi

    return 0
}

# Grow XFS filesystem (must be mounted)
# Usage: grow_xfs "/dev/sda1"
grow_xfs() {
    local part_device="$1"
    local mount_point temp_mount=""

    log "Growing XFS filesystem on ${part_device}"

    if is_mounted "${part_device}"; then
        mount_point=$(get_mount_point "${part_device}")
    else
        # Need to temporarily mount for XFS grow
        temp_mount=$(mktemp -d)
        log "Temporarily mounting ${part_device} to ${temp_mount}"
        if ! mount "${part_device}" "${temp_mount}"; then
            rmdir "${temp_mount}"
            log_error "Failed to mount XFS filesystem for resize"
            return 1
        fi
        mount_point="${temp_mount}"
    fi

    # Grow filesystem
    local result=0
    if ! xfs_growfs "${mount_point}"; then
        log_error "Failed to grow XFS filesystem"
        result=1
    fi

    # Unmount if we mounted it
    if [[ -n "${temp_mount}" ]]; then
        umount "${temp_mount}"
        rmdir "${temp_mount}"
    fi

    return ${result}
}

# Resize Btrfs filesystem
# Usage: resize_btrfs "/dev/sda1" 107374182400
resize_btrfs() {
    local part_device="$1"
    local new_size_bytes="$2"
    local mount_point temp_mount=""

    log "Resizing Btrfs filesystem on ${part_device}"

    # Btrfs can be resized mounted or unmounted, but command differs
    if is_mounted "${part_device}"; then
        mount_point=$(get_mount_point "${part_device}")
    else
        # Need to temporarily mount for Btrfs resize
        temp_mount=$(mktemp -d)
        log "Temporarily mounting ${part_device} to ${temp_mount}"
        if ! mount "${part_device}" "${temp_mount}"; then
            rmdir "${temp_mount}"
            log_error "Failed to mount Btrfs filesystem for resize"
            return 1
        fi
        mount_point="${temp_mount}"
    fi

    # Resize filesystem
    local result=0
    if ! btrfs filesystem resize "${new_size_bytes}" "${mount_point}"; then
        log_error "Failed to resize Btrfs filesystem"
        result=1
    fi

    # Unmount if we mounted it
    if [[ -n "${temp_mount}" ]]; then
        umount "${temp_mount}"
        rmdir "${temp_mount}"
    fi

    return ${result}
}

# Grow Btrfs filesystem to fill partition
# Usage: grow_btrfs "/dev/sda1"
grow_btrfs() {
    local part_device="$1"
    local mount_point temp_mount=""

    log "Growing Btrfs filesystem on ${part_device}"

    if is_mounted "${part_device}"; then
        mount_point=$(get_mount_point "${part_device}")
    else
        temp_mount=$(mktemp -d)
        log "Temporarily mounting ${part_device} to ${temp_mount}"
        if ! mount "${part_device}" "${temp_mount}"; then
            rmdir "${temp_mount}"
            log_error "Failed to mount Btrfs filesystem for resize"
            return 1
        fi
        mount_point="${temp_mount}"
    fi

    # Use 'max' to fill partition
    local result=0
    if ! btrfs filesystem resize max "${mount_point}"; then
        log_error "Failed to grow Btrfs filesystem"
        result=1
    fi

    if [[ -n "${temp_mount}" ]]; then
        umount "${temp_mount}"
        rmdir "${temp_mount}"
    fi

    return ${result}
}

# =============================================================================
# Partition Operations
# =============================================================================

# Resize partition operation
# Params: partition (number), new_size_bytes
op_resize() {
    local device="$1"
    local params="$2"
    local part_num new_size_bytes part_device fstype current_size

    # Parse parameters
    part_num=$(json_get ".partition" "${params}")
    new_size_bytes=$(json_get ".new_size_bytes" "${params}")

    if [[ -z "${part_num}" ]]; then
        log_error "Missing required parameter: partition"
        json_result "error" "Missing required parameter: partition"
        return 1
    fi

    if [[ -z "${new_size_bytes}" ]]; then
        log_error "Missing required parameter: new_size_bytes"
        json_result "error" "Missing required parameter: new_size_bytes"
        return 1
    fi

    # Validate partition exists
    if ! validate_partition "${device}" "${part_num}"; then
        json_result "error" "Partition ${part_num} not found on ${device}"
        return 1
    fi

    part_device=$(get_partition_device "${device}" "${part_num}")
    fstype=$(get_filesystem_type "${part_device}")
    current_size=$(get_partition_size "${device}" "${part_num}")

    log "Resizing partition ${part_num} on ${device} from ${current_size} to ${new_size_bytes} bytes"
    log "Filesystem type: ${fstype:-none}"

    # Determine if shrinking or growing
    local is_shrink=false
    if [[ ${new_size_bytes} -lt ${current_size} ]]; then
        is_shrink=true
        log "Operation: shrink"
    else
        log "Operation: grow"
    fi

    # For shrink: resize filesystem first, then partition
    # For grow: resize partition first, then filesystem

    if [[ "${is_shrink}" == "true" ]]; then
        # Shrink filesystem first (if applicable)
        if [[ -n "${fstype}" ]]; then
            case "${fstype}" in
                ext2|ext3|ext4)
                    if ! resize_ext4 "${part_device}" "${new_size_bytes}"; then
                        json_result "error" "Failed to shrink ext4 filesystem"
                        return 1
                    fi
                    ;;
                ntfs|ntfs-3g)
                    if ! resize_ntfs "${part_device}" "${new_size_bytes}"; then
                        json_result "error" "Failed to shrink NTFS filesystem"
                        return 1
                    fi
                    ;;
                xfs)
                    log_error "XFS filesystems cannot be shrunk"
                    json_result "error" "XFS filesystems cannot be shrunk"
                    return 1
                    ;;
                btrfs)
                    if ! resize_btrfs "${part_device}" "${new_size_bytes}"; then
                        json_result "error" "Failed to shrink Btrfs filesystem"
                        return 1
                    fi
                    ;;
                swap)
                    # Swap doesn't need filesystem resize
                    log "Swap partition - no filesystem resize needed"
                    ;;
                *)
                    log_warn "Unknown filesystem type: ${fstype}, skipping filesystem resize"
                    ;;
            esac
        fi

        # Shrink partition
        log "Shrinking partition ${part_num} to ${new_size_bytes} bytes"
        local end_bytes=$(($(parted -s "${device}" unit B print | grep -E "^ *${part_num} " | awk '{print $2}' | sed 's/B//') + new_size_bytes - 1))
        if ! parted -s "${device}" resizepart "${part_num}" "${new_size_bytes}B"; then
            json_result "error" "Failed to shrink partition"
            return 1
        fi

    else
        # Grow partition first
        log "Growing partition ${part_num} to ${new_size_bytes} bytes"

        # Get partition start
        local start_bytes
        start_bytes=$(parted -s "${device}" unit B print | grep -E "^ *${part_num} " | awk '{print $2}' | sed 's/B//')
        local end_bytes=$((start_bytes + new_size_bytes - 1))

        if ! parted -s "${device}" resizepart "${part_num}" "${end_bytes}B"; then
            json_result "error" "Failed to grow partition"
            return 1
        fi

        # Inform kernel of partition change
        partprobe "${device}" 2>/dev/null || true
        sleep 1

        # Grow filesystem
        if [[ -n "${fstype}" ]]; then
            case "${fstype}" in
                ext2|ext3|ext4)
                    if ! grow_ext4 "${part_device}"; then
                        json_result "error" "Failed to grow ext4 filesystem"
                        return 1
                    fi
                    ;;
                ntfs|ntfs-3g)
                    if ! grow_ntfs "${part_device}"; then
                        json_result "error" "Failed to grow NTFS filesystem"
                        return 1
                    fi
                    ;;
                xfs)
                    if ! grow_xfs "${part_device}"; then
                        json_result "error" "Failed to grow XFS filesystem"
                        return 1
                    fi
                    ;;
                btrfs)
                    if ! grow_btrfs "${part_device}"; then
                        json_result "error" "Failed to grow Btrfs filesystem"
                        return 1
                    fi
                    ;;
                swap)
                    # Recreate swap with new size
                    log "Recreating swap partition"
                    mkswap "${part_device}" &>/dev/null || true
                    ;;
                *)
                    log_warn "Unknown filesystem type: ${fstype}, skipping filesystem grow"
                    ;;
            esac
        fi
    fi

    # Inform kernel of partition change
    partprobe "${device}" 2>/dev/null || true

    log "Partition ${part_num} resized successfully"
    json_result "success" "Partition ${part_num} resized to ${new_size_bytes} bytes"
    return 0
}

# Create partition operation
# Params: start_bytes, size_bytes (or end_bytes), type, filesystem, label
op_create() {
    local device="$1"
    local params="$2"
    local start_bytes size_bytes end_bytes part_type filesystem label

    # Parse parameters
    start_bytes=$(json_get ".start_bytes" "${params}")
    size_bytes=$(json_get ".size_bytes" "${params}")
    end_bytes=$(json_get ".end_bytes" "${params}")
    part_type=$(json_get ".type" "${params}")
    filesystem=$(json_get ".filesystem" "${params}")
    label=$(json_get ".label" "${params}")

    if [[ -z "${start_bytes}" ]]; then
        log_error "Missing required parameter: start_bytes"
        json_result "error" "Missing required parameter: start_bytes"
        return 1
    fi

    # Calculate end if not provided
    if [[ -z "${end_bytes}" ]]; then
        if [[ -z "${size_bytes}" ]]; then
            log_error "Must provide either size_bytes or end_bytes"
            json_result "error" "Must provide either size_bytes or end_bytes"
            return 1
        fi
        end_bytes=$((start_bytes + size_bytes - 1))
    fi

    # Default partition type
    part_type="${part_type:-primary}"

    log "Creating partition on ${device}: start=${start_bytes}, end=${end_bytes}, type=${part_type}"

    # Create partition with parted
    if ! parted -s "${device}" mkpart "${part_type}" "${start_bytes}B" "${end_bytes}B"; then
        json_result "error" "Failed to create partition"
        return 1
    fi

    # Inform kernel of partition change
    partprobe "${device}" 2>/dev/null || true
    sleep 1

    # Find the new partition number (highest number)
    local new_part_num
    new_part_num=$(parted -s "${device}" print | grep -E "^ *[0-9]+" | tail -1 | awk '{print $1}')

    if [[ -z "${new_part_num}" ]]; then
        log_error "Failed to determine new partition number"
        json_result "error" "Partition created but could not determine partition number"
        return 1
    fi

    local new_part_device
    new_part_device=$(get_partition_device "${device}" "${new_part_num}")

    log "Created partition ${new_part_num}: ${new_part_device}"

    # Format if filesystem specified
    if [[ -n "${filesystem}" ]]; then
        log "Formatting partition with ${filesystem}"

        local mkfs_cmd=""
        local mkfs_opts=""

        case "${filesystem}" in
            ext2)
                mkfs_cmd="mkfs.ext2"
                [[ -n "${label}" ]] && mkfs_opts="-L ${label}"
                ;;
            ext3)
                mkfs_cmd="mkfs.ext3"
                [[ -n "${label}" ]] && mkfs_opts="-L ${label}"
                ;;
            ext4)
                mkfs_cmd="mkfs.ext4"
                [[ -n "${label}" ]] && mkfs_opts="-L ${label}"
                ;;
            xfs)
                mkfs_cmd="mkfs.xfs"
                [[ -n "${label}" ]] && mkfs_opts="-L ${label}"
                ;;
            btrfs)
                mkfs_cmd="mkfs.btrfs"
                [[ -n "${label}" ]] && mkfs_opts="-L ${label}"
                ;;
            ntfs)
                mkfs_cmd="mkfs.ntfs"
                mkfs_opts="-Q"  # Quick format
                [[ -n "${label}" ]] && mkfs_opts+=" -L ${label}"
                ;;
            vfat|fat32)
                mkfs_cmd="mkfs.vfat"
                mkfs_opts="-F 32"
                [[ -n "${label}" ]] && mkfs_opts+=" -n ${label}"
                ;;
            fat16)
                mkfs_cmd="mkfs.vfat"
                mkfs_opts="-F 16"
                [[ -n "${label}" ]] && mkfs_opts+=" -n ${label}"
                ;;
            swap)
                mkfs_cmd="mkswap"
                [[ -n "${label}" ]] && mkfs_opts="-L ${label}"
                ;;
            *)
                log_error "Unsupported filesystem type: ${filesystem}"
                json_result "error" "Unsupported filesystem type: ${filesystem}"
                return 1
                ;;
        esac

        # shellcheck disable=SC2086
        if ! ${mkfs_cmd} ${mkfs_opts} "${new_part_device}"; then
            json_result "error" "Partition created but formatting failed"
            return 1
        fi

        log "Formatted partition with ${filesystem}"
    fi

    json_result "success" "Created partition ${new_part_num}" "{\"partition\": ${new_part_num}, \"device\": \"${new_part_device}\"}"
    return 0
}

# Delete partition operation
# Params: partition (number)
op_delete() {
    local device="$1"
    local params="$2"
    local part_num part_device

    # Parse parameters
    part_num=$(json_get ".partition" "${params}")

    if [[ -z "${part_num}" ]]; then
        log_error "Missing required parameter: partition"
        json_result "error" "Missing required parameter: partition"
        return 1
    fi

    # Validate partition exists
    if ! validate_partition "${device}" "${part_num}"; then
        json_result "error" "Partition ${part_num} not found on ${device}"
        return 1
    fi

    part_device=$(get_partition_device "${device}" "${part_num}")

    # Check if mounted
    if is_mounted "${part_device}"; then
        log_error "Partition ${part_device} is mounted, cannot delete"
        json_result "error" "Partition is mounted, unmount first"
        return 1
    fi

    log "Deleting partition ${part_num} on ${device}"

    # Delete partition with parted
    if ! parted -s "${device}" rm "${part_num}"; then
        json_result "error" "Failed to delete partition"
        return 1
    fi

    # Inform kernel of partition change
    partprobe "${device}" 2>/dev/null || true

    log "Partition ${part_num} deleted successfully"
    json_result "success" "Partition ${part_num} deleted"
    return 0
}

# Format partition operation
# Params: partition (number), filesystem, label
op_format() {
    local device="$1"
    local params="$2"
    local part_num filesystem label part_device

    # Parse parameters
    part_num=$(json_get ".partition" "${params}")
    filesystem=$(json_get ".filesystem" "${params}")
    label=$(json_get ".label" "${params}")

    if [[ -z "${part_num}" ]]; then
        log_error "Missing required parameter: partition"
        json_result "error" "Missing required parameter: partition"
        return 1
    fi

    if [[ -z "${filesystem}" ]]; then
        log_error "Missing required parameter: filesystem"
        json_result "error" "Missing required parameter: filesystem"
        return 1
    fi

    # Validate partition exists
    if ! validate_partition "${device}" "${part_num}"; then
        json_result "error" "Partition ${part_num} not found on ${device}"
        return 1
    fi

    part_device=$(get_partition_device "${device}" "${part_num}")

    # Check if mounted
    if is_mounted "${part_device}"; then
        log_error "Partition ${part_device} is mounted, cannot format"
        json_result "error" "Partition is mounted, unmount first"
        return 1
    fi

    log "Formatting partition ${part_num} on ${device} with ${filesystem}"

    local mkfs_cmd=""
    local mkfs_opts=""

    case "${filesystem}" in
        ext2)
            mkfs_cmd="mkfs.ext2"
            mkfs_opts="-F"  # Force
            [[ -n "${label}" ]] && mkfs_opts+=" -L ${label}"
            ;;
        ext3)
            mkfs_cmd="mkfs.ext3"
            mkfs_opts="-F"
            [[ -n "${label}" ]] && mkfs_opts+=" -L ${label}"
            ;;
        ext4)
            mkfs_cmd="mkfs.ext4"
            mkfs_opts="-F"
            [[ -n "${label}" ]] && mkfs_opts+=" -L ${label}"
            ;;
        xfs)
            mkfs_cmd="mkfs.xfs"
            mkfs_opts="-f"  # Force
            [[ -n "${label}" ]] && mkfs_opts+=" -L ${label}"
            ;;
        btrfs)
            mkfs_cmd="mkfs.btrfs"
            mkfs_opts="-f"
            [[ -n "${label}" ]] && mkfs_opts+=" -L ${label}"
            ;;
        ntfs)
            mkfs_cmd="mkfs.ntfs"
            mkfs_opts="-Q -F"  # Quick format, force
            [[ -n "${label}" ]] && mkfs_opts+=" -L ${label}"
            ;;
        vfat|fat32)
            mkfs_cmd="mkfs.vfat"
            mkfs_opts="-F 32"
            [[ -n "${label}" ]] && mkfs_opts+=" -n ${label}"
            ;;
        fat16)
            mkfs_cmd="mkfs.vfat"
            mkfs_opts="-F 16"
            [[ -n "${label}" ]] && mkfs_opts+=" -n ${label}"
            ;;
        swap)
            mkfs_cmd="mkswap"
            mkfs_opts="-f"
            [[ -n "${label}" ]] && mkfs_opts+=" -L ${label}"
            ;;
        *)
            log_error "Unsupported filesystem type: ${filesystem}"
            json_result "error" "Unsupported filesystem type: ${filesystem}"
            return 1
            ;;
    esac

    # shellcheck disable=SC2086
    if ! ${mkfs_cmd} ${mkfs_opts} "${part_device}"; then
        json_result "error" "Failed to format partition"
        return 1
    fi

    log "Partition ${part_num} formatted with ${filesystem}"
    json_result "success" "Partition ${part_num} formatted with ${filesystem}"
    return 0
}

# Set partition flag operation
# Params: partition (number), flag, value (on/off)
op_set_flag() {
    local device="$1"
    local params="$2"
    local part_num flag value

    # Parse parameters
    part_num=$(json_get ".partition" "${params}")
    flag=$(json_get ".flag" "${params}")
    value=$(json_get ".value" "${params}")

    if [[ -z "${part_num}" ]]; then
        log_error "Missing required parameter: partition"
        json_result "error" "Missing required parameter: partition"
        return 1
    fi

    if [[ -z "${flag}" ]]; then
        log_error "Missing required parameter: flag"
        json_result "error" "Missing required parameter: flag"
        return 1
    fi

    # Default value is 'on'
    value="${value:-on}"

    # Validate value
    if [[ "${value}" != "on" && "${value}" != "off" ]]; then
        log_error "Invalid flag value: ${value} (must be 'on' or 'off')"
        json_result "error" "Invalid flag value: must be 'on' or 'off'"
        return 1
    fi

    # Validate partition exists
    if ! validate_partition "${device}" "${part_num}"; then
        json_result "error" "Partition ${part_num} not found on ${device}"
        return 1
    fi

    log "Setting flag '${flag}' to '${value}' on partition ${part_num}"

    # Set flag with parted
    if ! parted -s "${device}" set "${part_num}" "${flag}" "${value}"; then
        json_result "error" "Failed to set partition flag"
        return 1
    fi

    log "Flag '${flag}' set to '${value}' on partition ${part_num}"
    json_result "success" "Flag '${flag}' set to '${value}' on partition ${part_num}"
    return 0
}

# =============================================================================
# Main Dispatcher
# =============================================================================

# Execute a partition operation
# Takes JSON with: operation, device, params
execute_operation() {
    local input_json="$1"
    local operation device params

    # Parse top-level JSON
    operation=$(json_get ".operation" "${input_json}")
    device=$(json_get ".device" "${input_json}")
    params=$(echo "${input_json}" | jq -c '.params // {}' 2>/dev/null)

    if [[ -z "${operation}" ]]; then
        log_error "Missing required field: operation"
        json_result "error" "Missing required field: operation"
        return 1
    fi

    if [[ -z "${device}" ]]; then
        log_error "Missing required field: device"
        json_result "error" "Missing required field: device"
        return 1
    fi

    # Validate device exists
    if ! validate_device "${device}"; then
        json_result "error" "Device not found: ${device}"
        return 1
    fi

    log "Executing operation: ${operation} on ${device}"
    log_debug "Parameters: ${params}"

    # Dispatch to appropriate operation function
    case "${operation}" in
        resize)
            op_resize "${device}" "${params}"
            ;;
        create)
            op_create "${device}" "${params}"
            ;;
        delete)
            op_delete "${device}" "${params}"
            ;;
        format)
            op_format "${device}" "${params}"
            ;;
        set_flag)
            op_set_flag "${device}" "${params}"
            ;;
        *)
            log_error "Unknown operation: ${operation}"
            json_result "error" "Unknown operation: ${operation}"
            return 1
            ;;
    esac
}

# =============================================================================
# Main Function
# =============================================================================

main() {
    local input_json=""

    # Get input from argument or stdin
    if [[ $# -gt 0 ]]; then
        input_json="$1"
    else
        # Read from stdin
        input_json=$(cat)
    fi

    if [[ -z "${input_json}" ]]; then
        log_error "No input provided"
        json_result "error" "No input provided. Usage: $0 '<json_operation>'"
        exit 1
    fi

    # Validate JSON
    if ! echo "${input_json}" | jq . &>/dev/null; then
        log_error "Invalid JSON input"
        json_result "error" "Invalid JSON input"
        exit 1
    fi

    # Execute the operation
    execute_operation "${input_json}"
}

# =============================================================================
# Entry Point
# =============================================================================

main "$@"
