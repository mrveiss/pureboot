#!/bin/bash
# PureBoot ARM64 Common Functions
# Extends pureboot-common.sh with Pi-specific functionality
# Source this after pureboot-common.sh

# Prevent direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "This script should be sourced, not executed directly."
    exit 1
fi

# =============================================================================
# Pi-Specific Variables (populated by parse_pi_cmdline)
# =============================================================================
PUREBOOT_SERIAL=""      # Pi serial number from cmdline
PUREBOOT_PI_MODEL=""    # Pi model (pi3, pi4, pi5)

# =============================================================================
# Pi Kernel Cmdline Parsing
# =============================================================================

# Parse Pi-specific parameters from kernel cmdline
# Extends the base parse_cmdline with Pi parameters
parse_pi_cmdline() {
    local cmdline
    if [[ -r /proc/cmdline ]]; then
        cmdline=$(cat /proc/cmdline)
    else
        log_warn "Cannot read /proc/cmdline"
        return 0
    fi

    local param
    for param in ${cmdline}; do
        case "${param}" in
            pureboot.serial=*)
                PUREBOOT_SERIAL="${param#pureboot.serial=}"
                ;;
            pureboot.state=*)
                PUREBOOT_STATE="${param#pureboot.state=}"
                ;;
            pureboot.pi_model=*)
                PUREBOOT_PI_MODEL="${param#pureboot.pi_model=}"
                ;;
            pureboot.image_url=*)
                PUREBOOT_IMAGE_URL="${param#pureboot.image_url=}"
                ;;
            pureboot.target=*)
                PUREBOOT_TARGET="${param#pureboot.target=}"
                ;;
            pureboot.callback=*)
                PUREBOOT_CALLBACK="${param#pureboot.callback=}"
                ;;
            pureboot.url=*)
                PUREBOOT_SERVER="${param#pureboot.url=}"
                ;;
            pureboot.nfs_server=*)
                PUREBOOT_NFS_SERVER="${param#pureboot.nfs_server=}"
                ;;
            pureboot.nfs_path=*)
                PUREBOOT_NFS_PATH="${param#pureboot.nfs_path=}"
                ;;
        esac
    done

    log_debug "Parsed Pi cmdline: serial=${PUREBOOT_SERIAL}, model=${PUREBOOT_PI_MODEL}"
    log_debug "Parsed Pi cmdline: state=${PUREBOOT_STATE}, target=${PUREBOOT_TARGET}"
}

# =============================================================================
# Pi Hardware Detection
# =============================================================================

# Get Pi serial number from /proc/cpuinfo
# Usage: serial=$(get_pi_serial)
get_pi_serial() {
    local serial
    serial=$(grep -i "Serial" /proc/cpuinfo 2>/dev/null | awk '{print $3}' | tail -c 9 | head -c 8)

    if [[ -z "${serial}" ]]; then
        log_error "Could not read Pi serial number from /proc/cpuinfo"
        return 1
    fi

    # Normalize to lowercase
    echo "${serial,,}"
    return 0
}

# Detect Pi model from device tree
# Usage: model=$(get_pi_model)
get_pi_model() {
    local model_file="/proc/device-tree/model"

    if [[ ! -r "${model_file}" ]]; then
        log_warn "Cannot read device tree model, defaulting to pi4"
        echo "pi4"
        return 0
    fi

    local model_str
    model_str=$(cat "${model_file}" | tr -d '\0')

    case "${model_str}" in
        *"Pi 5"*)
            echo "pi5"
            ;;
        *"Pi 4"*|*"Pi 400"*)
            echo "pi4"
            ;;
        *"Pi 3"*)
            echo "pi3"
            ;;
        *"Compute Module 4"*)
            echo "cm4"
            ;;
        *)
            log_warn "Unknown Pi model: ${model_str}, defaulting to pi4"
            echo "pi4"
            ;;
    esac
    return 0
}

# Get MAC address of eth0 (Pi ethernet)
# Usage: mac=$(get_pi_mac)
get_pi_mac() {
    local mac

    # Try eth0 first (most Pi models)
    if [[ -r /sys/class/net/eth0/address ]]; then
        mac=$(cat /sys/class/net/eth0/address)
    # Try end0 (Pi 5 naming)
    elif [[ -r /sys/class/net/end0/address ]]; then
        mac=$(cat /sys/class/net/end0/address)
    else
        log_error "Could not find ethernet MAC address"
        return 1
    fi

    echo "${mac}"
    return 0
}

# =============================================================================
# Pi Storage Detection
# =============================================================================

# Detect Pi boot storage device
# Returns /dev/mmcblk0 for SD, /dev/nvme0n1 for NVMe, etc.
# Usage: device=$(get_pi_boot_device)
get_pi_boot_device() {
    # Check for NVMe (Pi 5 with NVMe HAT)
    if [[ -b /dev/nvme0n1 ]]; then
        echo "/dev/nvme0n1"
        return 0
    fi

    # Check for USB boot
    for disk in /dev/sd[a-z]; do
        if [[ -b "${disk}" ]]; then
            # Check if it's USB (not iSCSI)
            local tran
            tran=$(lsblk -n -o TRAN "${disk}" 2>/dev/null | head -1)
            if [[ "${tran}" == "usb" ]]; then
                echo "${disk}"
                return 0
            fi
        fi
    done

    # Default: SD card
    if [[ -b /dev/mmcblk0 ]]; then
        echo "/dev/mmcblk0"
        return 0
    fi

    log_error "Could not detect boot storage device"
    return 1
}

# Check if device is SD card (for Pi-specific handling)
# Usage: if is_sd_card "/dev/mmcblk0"; then ...
is_sd_card() {
    local device="$1"
    [[ "${device}" == /dev/mmcblk* ]]
}

# =============================================================================
# Pi Network Setup
# =============================================================================

# Bring up network on Pi (handles interface naming differences)
# Usage: pi_network_up
pi_network_up() {
    local iface

    # Try different interface names
    for iface in eth0 end0; do
        if ip link show "${iface}" &>/dev/null; then
            log "Bringing up network interface: ${iface}"
            ip link set "${iface}" up

            # Get IP via DHCP
            if command -v udhcpc &>/dev/null; then
                udhcpc -i "${iface}" -t 10 -n 2>/dev/null || true
            elif command -v dhclient &>/dev/null; then
                dhclient -1 "${iface}" 2>/dev/null || true
            fi

            # Wait for IP
            local retries=10
            while [[ ${retries} -gt 0 ]]; do
                if ip addr show "${iface}" | grep -q "inet "; then
                    log "Network up on ${iface}"
                    return 0
                fi
                sleep 1
                ((retries--))
            done
        fi
    done

    log_error "Failed to bring up network"
    return 1
}

# =============================================================================
# Pi API Communication
# =============================================================================

# Register Pi with PureBoot controller
# Usage: register_pi
register_pi() {
    local serial mac model ip_addr endpoint

    serial=$(get_pi_serial) || serial="${PUREBOOT_SERIAL}"
    mac=$(get_pi_mac) || mac="unknown"
    model=$(get_pi_model) || model="${PUREBOOT_PI_MODEL:-pi4}"
    ip_addr=$(get_local_ip) || ip_addr="unknown"

    endpoint="/api/v1/nodes/register-pi"

    local data
    data=$(cat << EOF
{
    "serial": "${serial}",
    "mac": "${mac}",
    "model": "${model}",
    "ip_address": "${ip_addr}"
}
EOF
)

    log "Registering Pi with controller..."
    log "  Serial: ${serial}"
    log "  MAC: ${mac}"
    log "  Model: ${model}"

    if api_post "${endpoint}" "${data}"; then
        log "Pi registered successfully"
        return 0
    else
        log_error "Failed to register Pi"
        return 1
    fi
}

# Get boot instructions from controller
# Usage: instructions=$(get_boot_instructions)
get_boot_instructions() {
    local serial endpoint response

    serial=$(get_pi_serial) || serial="${PUREBOOT_SERIAL}"

    if [[ -z "${serial}" ]]; then
        log_error "No serial number available"
        return 1
    fi

    if [[ -z "${PUREBOOT_SERVER}" ]]; then
        log_error "PUREBOOT_SERVER not set"
        return 1
    fi

    endpoint="${PUREBOOT_SERVER}/api/v1/boot/pi?serial=${serial}"

    log "Fetching boot instructions from ${endpoint}..."

    response=$(curl -sf --connect-timeout 10 --max-time 30 "${endpoint}" 2>/dev/null)

    if [[ $? -ne 0 || -z "${response}" ]]; then
        log_error "Failed to fetch boot instructions"
        return 1
    fi

    echo "${response}"
    return 0
}

# =============================================================================
# Initialization
# =============================================================================

# Initialize Pi-specific environment
_pureboot_arm64_init() {
    # Parse Pi cmdline parameters
    parse_pi_cmdline

    # Auto-detect serial if not in cmdline
    if [[ -z "${PUREBOOT_SERIAL}" ]]; then
        PUREBOOT_SERIAL=$(get_pi_serial 2>/dev/null) || true
    fi

    # Auto-detect model if not in cmdline
    if [[ -z "${PUREBOOT_PI_MODEL}" ]]; then
        PUREBOOT_PI_MODEL=$(get_pi_model 2>/dev/null) || true
    fi
}

# Run initialization when sourced
_pureboot_arm64_init