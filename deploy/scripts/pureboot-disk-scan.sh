#!/bin/bash
# PureBoot Disk Scan Script
# Scans disk and partition information and outputs as JSON for the controller.
# Usage: pureboot-disk-scan.sh [device]
#   If device is provided, scans only that device
#   Otherwise, scans all detected block devices

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Buffer for minimum size calculation (100MB in bytes)
MIN_SIZE_BUFFER=104857600

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

# Output a JSON string value, properly quoted, or null for empty strings
# Usage: json_string "value"
json_string() {
    local value="$1"
    if [[ -z "${value}" ]]; then
        echo "null"
    else
        # Escape special JSON characters
        value="${value//\\/\\\\}"  # Backslash
        value="${value//\"/\\\"}"  # Double quote
        value="${value//$'\n'/\\n}" # Newline
        value="${value//$'\r'/\\r}" # Carriage return
        value="${value//$'\t'/\\t}" # Tab
        echo "\"${value}\""
    fi
}

# Convert parted size output to bytes
# Parted outputs sizes like "1000B", "1024MB", "50GB", etc.
# Usage: bytes=$(parse_size_to_bytes "1024MB")
parse_size_to_bytes() {
    local size_str="$1"
    local number unit

    # Remove trailing B if present (parted outputs like "1048576B")
    size_str="${size_str%B}"

    # Extract number and unit
    if [[ "${size_str}" =~ ^([0-9]+)([A-Za-z]*)$ ]]; then
        number="${BASH_REMATCH[1]}"
        unit="${BASH_REMATCH[2]}"
    else
        # Just a number
        number="${size_str}"
        unit=""
    fi

    # Convert based on unit
    case "${unit}" in
        "" | "B")
            echo "${number}"
            ;;
        "kB" | "KB" | "K")
            echo "$((number * 1000))"
            ;;
        "KiB")
            echo "$((number * 1024))"
            ;;
        "MB" | "M")
            echo "$((number * 1000 * 1000))"
            ;;
        "MiB")
            echo "$((number * 1024 * 1024))"
            ;;
        "GB" | "G")
            echo "$((number * 1000 * 1000 * 1000))"
            ;;
        "GiB")
            echo "$((number * 1024 * 1024 * 1024))"
            ;;
        "TB" | "T")
            echo "$((number * 1000 * 1000 * 1000 * 1000))"
            ;;
        "TiB")
            echo "$((number * 1024 * 1024 * 1024 * 1024))"
            ;;
        *)
            # Unknown unit, return as-is
            echo "${number}"
            ;;
    esac
}

# =============================================================================
# Filesystem Usage Functions
# =============================================================================

# Get filesystem usage for a partition
# Returns: used_bytes or empty string if not determinable
# Usage: used=$(get_fs_usage "/dev/sda1" "ext4")
get_fs_usage() {
    local device="$1"
    local fstype="$2"
    local used_bytes=""
    local mount_point=""
    local temp_mount=""

    # Check if device is already mounted
    mount_point=$(findmnt -n -o TARGET "${device}" 2>/dev/null | head -1)

    if [[ -n "${mount_point}" ]]; then
        # Device is mounted, use df
        used_bytes=$(df -B1 "${device}" 2>/dev/null | tail -1 | awk '{print $3}')
    else
        # Try to get usage without mounting based on filesystem type
        case "${fstype}" in
            ext2|ext3|ext4)
                # Use dumpe2fs to get block count and free blocks
                local block_size block_count free_blocks
                block_size=$(dumpe2fs -h "${device}" 2>/dev/null | grep "Block size:" | awk '{print $3}')
                block_count=$(dumpe2fs -h "${device}" 2>/dev/null | grep "Block count:" | awk '{print $3}')
                free_blocks=$(dumpe2fs -h "${device}" 2>/dev/null | grep "Free blocks:" | awk '{print $3}')
                if [[ -n "${block_size}" && -n "${block_count}" && -n "${free_blocks}" ]]; then
                    local total_bytes=$((block_size * block_count))
                    local free_bytes=$((block_size * free_blocks))
                    used_bytes=$((total_bytes - free_bytes))
                fi
                ;;
            ntfs)
                # Use ntfsinfo to get cluster info
                local cluster_size total_clusters free_clusters
                cluster_size=$(ntfsinfo -m "${device}" 2>/dev/null | grep "Cluster Size:" | awk '{print $3}')
                total_clusters=$(ntfsinfo -m "${device}" 2>/dev/null | grep "Volume Size in Clusters:" | awk '{print $5}')
                free_clusters=$(ntfsinfo -m "${device}" 2>/dev/null | grep "Free Clusters:" | awk '{print $3}')
                if [[ -n "${cluster_size}" && -n "${total_clusters}" && -n "${free_clusters}" ]]; then
                    local total_bytes=$((cluster_size * total_clusters))
                    local free_bytes=$((cluster_size * free_clusters))
                    used_bytes=$((total_bytes - free_bytes))
                fi
                ;;
            btrfs)
                # For btrfs, we need to mount to get accurate usage
                # Skip for now if not mounted
                ;;
            xfs)
                # Use xfs_db for unmounted filesystems
                local block_size agcount agblocks freeblks
                block_size=$(xfs_db -r -c "sb 0" -c "print blocksize" "${device}" 2>/dev/null | awk -F= '{print $2}' | tr -d ' ')
                agcount=$(xfs_db -r -c "sb 0" -c "print agcount" "${device}" 2>/dev/null | awk -F= '{print $2}' | tr -d ' ')
                agblocks=$(xfs_db -r -c "sb 0" -c "print agblocks" "${device}" 2>/dev/null | awk -F= '{print $2}' | tr -d ' ')
                freeblks=$(xfs_db -r -c "freesp -s" "${device}" 2>/dev/null | tail -1 | awk '{print $2}')
                if [[ -n "${block_size}" && -n "${agcount}" && -n "${agblocks}" && -n "${freeblks}" ]]; then
                    local total_bytes=$((block_size * agcount * agblocks))
                    local free_bytes=$((block_size * freeblks))
                    used_bytes=$((total_bytes - free_bytes))
                fi
                ;;
        esac
    fi

    echo "${used_bytes}"
}

# =============================================================================
# Partition Scanning Functions
# =============================================================================

# Determine partition type based on filesystem and flags
# Usage: type=$(get_partition_type "vfat" "boot, esp")
get_partition_type() {
    local fstype="$1"
    local flags="$2"

    # Check for EFI System Partition
    if [[ "${flags}" == *"esp"* ]] || [[ "${flags}" == *"boot"* && "${fstype}" == "vfat" ]]; then
        echo "efi"
        return
    fi

    # Check filesystem type
    case "${fstype}" in
        ntfs|ntfs-3g)
            echo "ntfs"
            ;;
        swap)
            echo "swap"
            ;;
        ext2|ext3|ext4|xfs|btrfs)
            echo "linux"
            ;;
        vfat|fat16|fat32)
            echo "fat"
            ;;
        *)
            if [[ -n "${fstype}" ]]; then
                echo "${fstype}"
            else
                echo "unknown"
            fi
            ;;
    esac
}

# Check if a filesystem can be shrunk
# Usage: if can_shrink "ext4"; then ...
can_shrink() {
    local fstype="$1"
    case "${fstype}" in
        ext2|ext3|ext4|ntfs|ntfs-3g|btrfs)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Scan partitions on a disk device using parted
# Outputs JSON array of partition objects
# Usage: scan_partitions "/dev/sda"
scan_partitions() {
    local device="$1"
    local partitions_json="["
    local first_partition=true

    # Get parted output in machine-parseable format
    # Format: number:start:end:size:fs:name:flags
    local parted_output
    parted_output=$(parted -s "${device}" unit B print 2>/dev/null | grep -E "^ *[0-9]+")

    if [[ -z "${parted_output}" ]]; then
        echo "[]"
        return
    fi

    while IFS= read -r line; do
        # Skip empty lines
        [[ -z "${line}" ]] && continue

        # Parse parted output
        # Example line: " 1      1048576B    537919487B    536870912B  fat32                boot, esp"
        local part_num start_str end_str size_str fs_name flags

        # Use regex to parse the line
        if [[ "${line}" =~ ^[[:space:]]*([0-9]+)[[:space:]]+([0-9]+)B[[:space:]]+([0-9]+)B[[:space:]]+([0-9]+)B[[:space:]]+([^[:space:]]*)[[:space:]]*([^[:space:]]*)[[:space:]]*(.*)?$ ]]; then
            part_num="${BASH_REMATCH[1]}"
            start_str="${BASH_REMATCH[2]}"
            end_str="${BASH_REMATCH[3]}"
            size_str="${BASH_REMATCH[4]}"
            fs_name="${BASH_REMATCH[5]}"
            # BASH_REMATCH[6] would be partition name for GPT
            flags="${BASH_REMATCH[7]}"
        else
            # Try alternative parsing for simpler output
            part_num=$(echo "${line}" | awk '{print $1}')
            start_str=$(echo "${line}" | awk '{print $2}' | sed 's/B$//')
            end_str=$(echo "${line}" | awk '{print $3}' | sed 's/B$//')
            size_str=$(echo "${line}" | awk '{print $4}' | sed 's/B$//')
            fs_name=$(echo "${line}" | awk '{print $5}')
            flags=$(echo "${line}" | awk '{$1=$2=$3=$4=$5=""; print $0}' | sed 's/^[[:space:]]*//')
        fi

        # Determine partition device name
        local part_device
        if [[ "${device}" =~ nvme[0-9]+n[0-9]+$ ]] || [[ "${device}" =~ mmcblk[0-9]+$ ]]; then
            part_device="${device}p${part_num}"
        else
            part_device="${device}${part_num}"
        fi

        # Get filesystem info from blkid (more accurate than parted)
        local blkid_output fstype label uuid
        blkid_output=$(blkid -o export "${part_device}" 2>/dev/null || true)

        if [[ -n "${blkid_output}" ]]; then
            fstype=$(echo "${blkid_output}" | grep "^TYPE=" | cut -d= -f2)
            label=$(echo "${blkid_output}" | grep "^LABEL=" | cut -d= -f2)
            uuid=$(echo "${blkid_output}" | grep "^UUID=" | cut -d= -f2)
        fi

        # Use parted fs if blkid didn't find one
        if [[ -z "${fstype}" && -n "${fs_name}" ]]; then
            fstype="${fs_name}"
        fi

        # Convert sizes to bytes
        local start_bytes end_bytes size_bytes
        start_bytes="${start_str}"
        end_bytes="${end_str}"
        size_bytes="${size_str}"

        # Get filesystem usage
        local used_bytes used_percent min_size_bytes
        used_bytes=$(get_fs_usage "${part_device}" "${fstype}")

        if [[ -n "${used_bytes}" && "${used_bytes}" =~ ^[0-9]+$ && ${size_bytes} -gt 0 ]]; then
            used_percent=$((used_bytes * 100 / size_bytes))
            min_size_bytes=$((used_bytes + MIN_SIZE_BUFFER))
        else
            used_bytes=""
            used_percent=""
            min_size_bytes=""
        fi

        # Determine partition type
        local part_type
        part_type=$(get_partition_type "${fstype}" "${flags}")

        # Check if filesystem can be shrunk
        local shrinkable="false"
        if can_shrink "${fstype}"; then
            shrinkable="true"
        fi

        # Build flags JSON array
        local flags_json="[]"
        if [[ -n "${flags}" ]]; then
            # Convert comma-separated flags to JSON array
            flags_json="["
            local flag_first=true
            for flag in ${flags//,/ }; do
                flag=$(echo "${flag}" | tr -d '[:space:]')
                [[ -z "${flag}" ]] && continue
                if [[ "${flag_first}" == "true" ]]; then
                    flag_first=false
                else
                    flags_json+=","
                fi
                flags_json+="\"${flag}\""
            done
            flags_json+="]"
        fi

        # Add comma separator between partitions
        if [[ "${first_partition}" == "true" ]]; then
            first_partition=false
        else
            partitions_json+=","
        fi

        # Build partition JSON object
        partitions_json+="{"
        partitions_json+="\"number\":${part_num},"
        partitions_json+="\"device\":\"${part_device}\","
        partitions_json+="\"start_bytes\":${start_bytes},"
        partitions_json+="\"end_bytes\":${end_bytes},"
        partitions_json+="\"size_bytes\":${size_bytes},"
        partitions_json+="\"type\":\"${part_type}\","
        partitions_json+="\"filesystem\":$(json_string "${fstype}"),"
        partitions_json+="\"label\":$(json_string "${label}"),"
        partitions_json+="\"uuid\":$(json_string "${uuid}"),"
        partitions_json+="\"flags\":${flags_json},"

        if [[ -n "${used_bytes}" ]]; then
            partitions_json+="\"used_bytes\":${used_bytes},"
            partitions_json+="\"used_percent\":${used_percent},"
            partitions_json+="\"min_size_bytes\":${min_size_bytes},"
        else
            partitions_json+="\"used_bytes\":null,"
            partitions_json+="\"used_percent\":null,"
            partitions_json+="\"min_size_bytes\":null,"
        fi

        partitions_json+="\"can_shrink\":${shrinkable}"
        partitions_json+="}"

    done <<< "${parted_output}"

    partitions_json+="]"
    echo "${partitions_json}"
}

# =============================================================================
# Disk Scanning Functions
# =============================================================================

# Get disk model from various sources
# Usage: model=$(get_disk_model "/dev/sda")
get_disk_model() {
    local device="$1"
    local device_name model

    device_name=$(basename "${device}")

    # Try /sys/block/.../device/model
    if [[ -f "/sys/block/${device_name}/device/model" ]]; then
        model=$(cat "/sys/block/${device_name}/device/model" 2>/dev/null | tr -d '\n' | sed 's/[[:space:]]*$//')
    fi

    # Try hdparm if model not found
    if [[ -z "${model}" ]] && command -v hdparm &>/dev/null; then
        model=$(hdparm -I "${device}" 2>/dev/null | grep "Model Number:" | sed 's/.*Model Number:[[:space:]]*//')
    fi

    # Try smartctl
    if [[ -z "${model}" ]] && command -v smartctl &>/dev/null; then
        model=$(smartctl -i "${device}" 2>/dev/null | grep "Device Model:" | sed 's/.*Device Model:[[:space:]]*//')
    fi

    echo "${model}"
}

# Get disk serial number
# Usage: serial=$(get_disk_serial "/dev/sda")
get_disk_serial() {
    local device="$1"
    local device_name serial

    device_name=$(basename "${device}")

    # Try /sys/block/.../device/serial
    if [[ -f "/sys/block/${device_name}/device/serial" ]]; then
        serial=$(cat "/sys/block/${device_name}/device/serial" 2>/dev/null | tr -d '\n' | sed 's/[[:space:]]*$//')
    fi

    # Try udevadm
    if [[ -z "${serial}" ]]; then
        serial=$(udevadm info --query=property --name="${device}" 2>/dev/null | grep "ID_SERIAL_SHORT=" | cut -d= -f2)
    fi

    # Try hdparm
    if [[ -z "${serial}" ]] && command -v hdparm &>/dev/null; then
        serial=$(hdparm -I "${device}" 2>/dev/null | grep "Serial Number:" | sed 's/.*Serial Number:[[:space:]]*//')
    fi

    echo "${serial}"
}

# Get partition table type (gpt, msdos/mbr, etc.)
# Usage: table=$(get_partition_table "/dev/sda")
get_partition_table() {
    local device="$1"
    local table_type

    # Use parted to get partition table type
    table_type=$(parted -s "${device}" print 2>/dev/null | grep "Partition Table:" | awk '{print $3}')

    # Normalize names
    case "${table_type}" in
        gpt)
            echo "gpt"
            ;;
        msdos)
            echo "mbr"
            ;;
        *)
            if [[ -n "${table_type}" ]]; then
                echo "${table_type}"
            else
                echo "unknown"
            fi
            ;;
    esac
}

# Scan a single disk device and output JSON
# Usage: scan_disk "/dev/sda"
scan_disk() {
    local device="$1"

    # Validate device
    if [[ ! -b "${device}" ]]; then
        log_error "Device not found or not a block device: ${device}" >&2
        return 1
    fi

    # Get disk information
    local size_bytes model serial partition_table partitions_json

    size_bytes=$(get_disk_size "${device}" 2>/dev/null)
    if [[ -z "${size_bytes}" ]]; then
        size_bytes=0
    fi

    model=$(get_disk_model "${device}")
    serial=$(get_disk_serial "${device}")
    partition_table=$(get_partition_table "${device}")
    partitions_json=$(scan_partitions "${device}")

    # Build disk JSON object
    local disk_json="{"
    disk_json+="\"device\":\"${device}\","
    disk_json+="\"size_bytes\":${size_bytes},"
    disk_json+="\"model\":$(json_string "${model}"),"
    disk_json+="\"serial\":$(json_string "${serial}"),"
    disk_json+="\"partition_table\":\"${partition_table}\","
    disk_json+="\"partitions\":${partitions_json}"
    disk_json+="}"

    echo "${disk_json}"
}

# =============================================================================
# Device Discovery Functions
# =============================================================================

# Find all block devices to scan
# Returns list of device paths
find_block_devices() {
    local devices=()

    # SATA/SCSI disks (/dev/sd?)
    for dev in /dev/sd[a-z]; do
        if [[ -b "${dev}" ]]; then
            devices+=("${dev}")
        fi
    done

    # NVMe disks (/dev/nvme?n?)
    for dev in /dev/nvme[0-9]n[0-9]; do
        if [[ -b "${dev}" ]]; then
            devices+=("${dev}")
        fi
    done

    # VirtIO disks (/dev/vd?)
    for dev in /dev/vd[a-z]; do
        if [[ -b "${dev}" ]]; then
            devices+=("${dev}")
        fi
    done

    # MMC/eMMC devices (/dev/mmcblk?)
    for dev in /dev/mmcblk[0-9]; do
        if [[ -b "${dev}" ]]; then
            devices+=("${dev}")
        fi
    done

    echo "${devices[@]}"
}

# =============================================================================
# Main Function
# =============================================================================

main() {
    local target_device="$1"
    local output_json=""

    if [[ -n "${target_device}" ]]; then
        # Scan specific device
        if [[ ! -b "${target_device}" ]]; then
            echo "{\"error\": \"Device not found: ${target_device}\"}" >&2
            exit 1
        fi

        output_json=$(scan_disk "${target_device}")
    else
        # Scan all devices
        local devices
        devices=$(find_block_devices)

        if [[ -z "${devices}" ]]; then
            echo "{\"disks\": []}"
            exit 0
        fi

        output_json="{\"disks\":["
        local first_disk=true

        for device in ${devices}; do
            if [[ "${first_disk}" == "true" ]]; then
                first_disk=false
            else
                output_json+=","
            fi
            output_json+=$(scan_disk "${device}")
        done

        output_json+="]}"
    fi

    # Output final JSON
    echo "${output_json}"
}

# =============================================================================
# Entry Point
# =============================================================================

main "$@"
