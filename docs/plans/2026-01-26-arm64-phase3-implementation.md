# ARM64/Raspberry Pi Phase 3: Deploy Environment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an ARM64 Alpine Linux deploy environment for Raspberry Pi network boot provisioning

**Architecture:** Adapt the existing x86 deploy environment (`deploy/build-deploy-image.sh`) for ARM64. Create `build-arm64-deploy-image.sh` that builds Alpine aarch64 initramfs with PureBoot agent scripts. Pi-specific scripts handle Pi boot quirks and SD card deployment.

**Tech Stack:** Alpine Linux 3.19 aarch64, shell scripts, curl, dd, parted

---

## Task 1: Create ARM64 Build Script Foundation

**Files:**
- Create: `deploy/build-arm64-deploy-image.sh`

**Step 1: Create the build script with Alpine ARM64 setup**

```bash
#!/bin/bash
# Build PureBoot ARM64 deployment image based on Alpine Linux
# This creates a minimal Linux environment for Raspberry Pi provisioning

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build-arm64"
OUTPUT_DIR="${SCRIPT_DIR}/output-arm64"

# Alpine version (same as x86)
ALPINE_VERSION="3.19"
ALPINE_ARCH="aarch64"
ALPINE_MIRROR="https://dl-cdn.alpinelinux.org/alpine"

echo "=== PureBoot ARM64 Deploy Image Builder ==="
echo ""
echo "Building for: ${ALPINE_ARCH}"
echo "Alpine version: ${ALPINE_VERSION}"
echo ""

# Create build directories
mkdir -p "${BUILD_DIR}" "${OUTPUT_DIR}"

# Download Alpine minirootfs for ARM64
ROOTFS_URL="${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/${ALPINE_ARCH}/alpine-minirootfs-${ALPINE_VERSION}.0-${ALPINE_ARCH}.tar.gz"
ROOTFS_FILE="${BUILD_DIR}/alpine-minirootfs-${ALPINE_ARCH}.tar.gz"

if [ ! -f "${ROOTFS_FILE}" ]; then
    echo "Downloading Alpine minirootfs for ${ALPINE_ARCH}..."
    curl -fsSL -o "${ROOTFS_FILE}" "${ROOTFS_URL}"
fi

# Create rootfs directory
ROOTFS_DIR="${BUILD_DIR}/rootfs"
rm -rf "${ROOTFS_DIR}"
mkdir -p "${ROOTFS_DIR}"

echo "Extracting rootfs..."
tar -xzf "${ROOTFS_FILE}" -C "${ROOTFS_DIR}"

# Install required packages using QEMU if on x86 host
echo "Installing packages..."
cp /etc/resolv.conf "${ROOTFS_DIR}/etc/resolv.conf"

cat > "${ROOTFS_DIR}/install-packages.sh" << 'INSTALL_EOF'
#!/bin/sh
apk update
apk add --no-cache \
    curl \
    wget \
    xz \
    gzip \
    pigz \
    pv \
    parted \
    e2fsprogs \
    e2fsprogs-extra \
    dosfstools \
    util-linux \
    coreutils \
    bash \
    jq \
    openssl \
    bc \
    udev
INSTALL_EOF
chmod +x "${ROOTFS_DIR}/install-packages.sh"

# Check if we can chroot (requires same arch or QEMU)
if [ "$(uname -m)" = "aarch64" ]; then
    echo "Native ARM64 build..."
    chroot "${ROOTFS_DIR}" /install-packages.sh
elif [ "$(id -u)" = "0" ] && [ -x /usr/bin/qemu-aarch64-static ]; then
    echo "Cross-build using QEMU..."
    cp /usr/bin/qemu-aarch64-static "${ROOTFS_DIR}/usr/bin/"
    chroot "${ROOTFS_DIR}" /install-packages.sh
    rm -f "${ROOTFS_DIR}/usr/bin/qemu-aarch64-static"
else
    echo "NOTE: Cannot install packages (need root + QEMU for cross-build)"
    echo "Install qemu-user-static and run as root, or build on ARM64 hardware"
    echo "Skipping package installation..."
fi
rm -f "${ROOTFS_DIR}/install-packages.sh"

# Continue with script copying below...
```

**Step 2: Make the script executable and commit**

```bash
chmod +x deploy/build-arm64-deploy-image.sh
git add deploy/build-arm64-deploy-image.sh
git commit -m "feat: add ARM64 deploy image build script foundation"
```

---

## Task 2: Add ARM64-Specific Common Functions

**Files:**
- Create: `deploy/scripts/pureboot-common-arm64.sh`

**Step 1: Create ARM64-specific common functions**

```bash
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
```

**Step 2: Commit the ARM64 common functions**

```bash
chmod +x deploy/scripts/pureboot-common-arm64.sh
git add deploy/scripts/pureboot-common-arm64.sh
git commit -m "feat: add ARM64/Pi-specific common functions"
```

---

## Task 3: Create Pi Image Deployment Script

**Files:**
- Create: `deploy/scripts/pureboot-pi-image.sh`

**Step 1: Create Pi-specific image deployment script**

```bash
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
```

**Step 2: Commit**

```bash
chmod +x deploy/scripts/pureboot-pi-image.sh
git add deploy/scripts/pureboot-pi-image.sh
git commit -m "feat: add Pi-specific image deployment script"
```

---

## Task 4: Create Pi Deploy Mode Dispatcher

**Files:**
- Create: `deploy/scripts/pureboot-pi-deploy.sh`

**Step 1: Create Pi deployment dispatcher**

```bash
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
```

**Step 2: Commit**

```bash
chmod +x deploy/scripts/pureboot-pi-deploy.sh
git add deploy/scripts/pureboot-pi-deploy.sh
git commit -m "feat: add Pi deploy mode dispatcher"
```

---

## Task 5: Create Pi NFS Boot Script (Placeholder)

**Files:**
- Create: `deploy/scripts/pureboot-pi-nfs.sh`

**Step 1: Create NFS boot script placeholder**

```bash
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
```

**Step 2: Commit**

```bash
chmod +x deploy/scripts/pureboot-pi-nfs.sh
git add deploy/scripts/pureboot-pi-nfs.sh
git commit -m "feat: add Pi NFS boot script placeholder (Phase 4)"
```

---

## Task 6: Create ARM64 Init Script

**Files:**
- Create: `deploy/arm64-init.sh`

**Step 1: Create init script for ARM64 initramfs**

```bash
#!/bin/sh
# PureBoot ARM64 Init Script
# Runs as /init in the initramfs for Raspberry Pi boot

# Mount essential filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts

# Enable kernel messages on console
echo 1 > /proc/sys/kernel/printk

echo ""
echo "====================================="
echo "   PureBoot ARM64 Deploy Environment"
echo "====================================="
echo ""

# Wait for storage devices to settle
echo "Waiting for devices..."
sleep 2

# Trigger udev if available
if [ -x /sbin/udevd ]; then
    /sbin/udevd --daemon
    udevadm trigger
    udevadm settle --timeout=10
fi

# Bring up loopback
ip link set lo up

# Wait for ethernet interface
echo "Waiting for network interface..."
for i in $(seq 1 30); do
    if ip link show eth0 2>/dev/null | grep -q "state UP"; then
        break
    fi
    if ip link show end0 2>/dev/null | grep -q "state UP"; then
        break
    fi
    # Try to bring up interface
    for iface in eth0 end0; do
        ip link set "$iface" up 2>/dev/null || true
    done
    sleep 1
done

# Get IP via DHCP
echo "Getting IP address via DHCP..."
for iface in eth0 end0; do
    if ip link show "$iface" 2>/dev/null; then
        udhcpc -i "$iface" -t 10 -n 2>/dev/null && break
    fi
done

# Show network config
echo ""
echo "Network configuration:"
ip addr show | grep -E "^[0-9]|inet " | head -10
echo ""

# Run PureBoot Pi deploy dispatcher
if [ -x /usr/local/bin/pureboot-pi-deploy.sh ]; then
    exec /usr/local/bin/pureboot-pi-deploy.sh
else
    echo "ERROR: Deploy script not found"
    echo "Dropping to shell..."
    exec /bin/sh
fi
```

**Step 2: Commit**

```bash
chmod +x deploy/arm64-init.sh
git add deploy/arm64-init.sh
git commit -m "feat: add ARM64 init script for Pi initramfs"
```

---

## Task 7: Complete Build Script

**Files:**
- Modify: `deploy/build-arm64-deploy-image.sh`

**Step 1: Add script copying and initramfs creation**

Append to `deploy/build-arm64-deploy-image.sh`:

```bash
# Copy common scripts
echo "Copying PureBoot scripts..."
mkdir -p "${ROOTFS_DIR}/usr/local/bin"

# Base common script
cp "${SCRIPT_DIR}/scripts/pureboot-common.sh" "${ROOTFS_DIR}/usr/local/bin/"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-common.sh"

# ARM64-specific scripts
cp "${SCRIPT_DIR}/scripts/pureboot-common-arm64.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-pi-deploy.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-pi-image.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-pi-nfs.sh" "${ROOTFS_DIR}/usr/local/bin/"
chmod +x "${ROOTFS_DIR}/usr/local/bin/"*.sh

# Init script
cp "${SCRIPT_DIR}/arm64-init.sh" "${ROOTFS_DIR}/init"
chmod +x "${ROOTFS_DIR}/init"

# Create initramfs
echo ""
echo "Creating initramfs..."
cd "${ROOTFS_DIR}"
find . | cpio -o -H newc 2>/dev/null | gzip -9 > "${OUTPUT_DIR}/initramfs-arm64.img"

echo ""
echo "=== Build Complete ==="
echo ""
echo "Output files:"
echo "  ${OUTPUT_DIR}/initramfs-arm64.img"
echo ""
echo "To complete the deploy environment, you also need:"
echo "  1. Linux kernel for ARM64 (kernel8.img)"
echo "     Download from: ${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/${ALPINE_ARCH}/netboot/"
echo "     Or use: linux-rpi kernel from Alpine packages"
echo ""
echo "  2. Copy to PureBoot TFTP server:"
echo "     cp ${OUTPUT_DIR}/initramfs-arm64.img /path/to/tftp/deploy-arm64/"
echo "     cp kernel8.img /path/to/tftp/deploy-arm64/"
echo ""
```

**Step 2: Commit**

```bash
git add deploy/build-arm64-deploy-image.sh
git commit -m "feat: complete ARM64 build script with script copying and initramfs creation"
```

---

## Task 8: Add Unit Tests for ARM64 Functions

**Files:**
- Create: `tests/unit/test_arm64_scripts.py`

**Step 1: Create test file**

```python
"""Unit tests for ARM64 deploy scripts.

These tests verify the shell scripts have correct structure and
expected functions without requiring ARM64 hardware.
"""
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).parent.parent.parent / "deploy"
SCRIPTS_DIR = DEPLOY_DIR / "scripts"


class TestARM64ScriptExistence:
    """Verify all required ARM64 scripts exist."""

    def test_build_script_exists(self):
        """Test ARM64 build script exists."""
        script = DEPLOY_DIR / "build-arm64-deploy-image.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_common_arm64_exists(self):
        """Test ARM64 common functions script exists."""
        script = SCRIPTS_DIR / "pureboot-common-arm64.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_pi_deploy_exists(self):
        """Test Pi deploy dispatcher exists."""
        script = SCRIPTS_DIR / "pureboot-pi-deploy.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_pi_image_exists(self):
        """Test Pi image deployment script exists."""
        script = SCRIPTS_DIR / "pureboot-pi-image.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_pi_nfs_exists(self):
        """Test Pi NFS boot script exists."""
        script = SCRIPTS_DIR / "pureboot-pi-nfs.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_arm64_init_exists(self):
        """Test ARM64 init script exists."""
        script = DEPLOY_DIR / "arm64-init.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"


class TestARM64ScriptSyntax:
    """Verify shell scripts have valid syntax."""

    @pytest.mark.parametrize("script_name", [
        "build-arm64-deploy-image.sh",
    ])
    def test_build_script_syntax(self, script_name):
        """Test build script has valid bash syntax."""
        script = DEPLOY_DIR / script_name
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in {script_name}: {result.stderr}"

    @pytest.mark.parametrize("script_name", [
        "pureboot-common-arm64.sh",
        "pureboot-pi-deploy.sh",
        "pureboot-pi-image.sh",
        "pureboot-pi-nfs.sh",
    ])
    def test_scripts_syntax(self, script_name):
        """Test deploy scripts have valid bash syntax."""
        script = SCRIPTS_DIR / script_name
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in {script_name}: {result.stderr}"

    def test_init_script_syntax(self):
        """Test init script has valid sh syntax."""
        script = DEPLOY_DIR / "arm64-init.sh"
        result = subprocess.run(
            ["sh", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in arm64-init.sh: {result.stderr}"


class TestARM64ScriptContent:
    """Verify scripts contain expected content."""

    def test_common_arm64_has_pi_functions(self):
        """Test ARM64 common script has Pi-specific functions."""
        script = SCRIPTS_DIR / "pureboot-common-arm64.sh"
        content = script.read_text()

        expected_functions = [
            "get_pi_serial",
            "get_pi_model",
            "get_pi_mac",
            "get_pi_boot_device",
            "pi_network_up",
            "register_pi",
            "get_boot_instructions",
            "parse_pi_cmdline",
        ]

        for func in expected_functions:
            assert func in content, f"Missing function: {func}"

    def test_pi_image_has_deploy_functions(self):
        """Test Pi image script has deployment functions."""
        script = SCRIPTS_DIR / "pureboot-pi-image.sh"
        content = script.read_text()

        expected = [
            "deploy_pi_image",
            "resize_pi_partitions",
            "notify_pi_complete",
            "PUREBOOT_IMAGE_URL",
            "PUREBOOT_TARGET",
        ]

        for item in expected:
            assert item in content, f"Missing: {item}"

    def test_pi_deploy_has_dispatcher(self):
        """Test Pi deploy script dispatches to correct scripts."""
        script = SCRIPTS_DIR / "pureboot-pi-deploy.sh"
        content = script.read_text()

        expected = [
            "deploy_image",
            "nfs_boot",
            "local_boot",
            "pureboot-pi-image.sh",
            "pureboot-pi-nfs.sh",
            "get_boot_instructions",
        ]

        for item in expected:
            assert item in content, f"Missing: {item}"

    def test_build_script_uses_aarch64(self):
        """Test build script targets aarch64 architecture."""
        script = DEPLOY_DIR / "build-arm64-deploy-image.sh"
        content = script.read_text()

        assert 'ALPINE_ARCH="aarch64"' in content
        assert "initramfs-arm64.img" in content
```

**Step 2: Commit**

```bash
git add tests/unit/test_arm64_scripts.py
git commit -m "test: add unit tests for ARM64 deploy scripts"
```

---

## Task 9: Push Branch and Update PR

**Files:**
- None (git operations only)

**Step 1: Verify all files**

```bash
ls -la deploy/build-arm64-deploy-image.sh
ls -la deploy/arm64-init.sh
ls -la deploy/scripts/pureboot-common-arm64.sh
ls -la deploy/scripts/pureboot-pi-*.sh
```

**Step 2: Push changes**

```bash
git push origin feature/arm64-raspberry-pi
```

**Step 3: Update PR description**

Add Phase 3 section to PR body:

```markdown
## Phase 3: Deploy Environment

- ARM64 Alpine Linux initramfs build script (`build-arm64-deploy-image.sh`)
- Pi-specific common functions (`pureboot-common-arm64.sh`)
- Pi image deployment script (`pureboot-pi-image.sh`)
- Pi deploy mode dispatcher (`pureboot-pi-deploy.sh`)
- NFS boot placeholder for Phase 4 (`pureboot-pi-nfs.sh`)
- ARM64 init script for initramfs
- Unit tests for script syntax and content
```

---

## Summary

Phase 3 creates the ARM64 deploy environment with:

1. **Build Script** (`build-arm64-deploy-image.sh`) - Builds Alpine aarch64 initramfs
2. **Common Functions** (`pureboot-common-arm64.sh`) - Pi hardware detection, network, API
3. **Image Deployment** (`pureboot-pi-image.sh`) - Deploy disk images to Pi storage
4. **Deploy Dispatcher** (`pureboot-pi-deploy.sh`) - Routes based on controller instructions
5. **NFS Boot** (`pureboot-pi-nfs.sh`) - Placeholder for Phase 4
6. **Init Script** (`arm64-init.sh`) - Entry point in initramfs

The deploy environment:
- Boots via TFTP on Raspberry Pi
- Fetches instructions from PureBoot API
- Deploys disk images to SD/USB/NVMe
- Reports completion to controller
- Supports future NFS diskless boot (Phase 4)
