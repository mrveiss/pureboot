#!/bin/bash
# Build PureBoot deployment image based on Alpine Linux
# This creates a minimal Linux environment for image-based OS deployment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
OUTPUT_DIR="${SCRIPT_DIR}/output"

# Alpine version
ALPINE_VERSION="3.19"
ALPINE_ARCH="x86_64"
ALPINE_MIRROR="https://dl-cdn.alpinelinux.org/alpine"

echo "=== PureBoot Deploy Image Builder ==="
echo ""

# Create build directories
mkdir -p "${BUILD_DIR}" "${OUTPUT_DIR}"

# Download Alpine minirootfs
ROOTFS_URL="${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/${ALPINE_ARCH}/alpine-minirootfs-${ALPINE_VERSION}.0-${ALPINE_ARCH}.tar.gz"
ROOTFS_FILE="${BUILD_DIR}/alpine-minirootfs.tar.gz"

if [ ! -f "${ROOTFS_FILE}" ]; then
    echo "Downloading Alpine minirootfs..."
    curl -fsSL -o "${ROOTFS_FILE}" "${ROOTFS_URL}"
fi

# Create rootfs directory
ROOTFS_DIR="${BUILD_DIR}/rootfs"
rm -rf "${ROOTFS_DIR}"
mkdir -p "${ROOTFS_DIR}"

echo "Extracting rootfs..."
tar -xzf "${ROOTFS_FILE}" -C "${ROOTFS_DIR}"

# Install required packages using chroot
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
    ntfs-3g \
    ntfs-3g-progs \
    util-linux \
    coreutils \
    bash \
    jq \
    openssl \
    lighttpd \
    lighttpd-mod_auth \
    btrfs-progs \
    xfsprogs \
    bc
INSTALL_EOF
chmod +x "${ROOTFS_DIR}/install-packages.sh"

# Run in chroot (requires root)
if [ "$(id -u)" = "0" ]; then
    chroot "${ROOTFS_DIR}" /install-packages.sh
else
    echo "NOTE: Run as root to install packages, or use Docker"
    echo "Skipping package installation..."
fi
rm -f "${ROOTFS_DIR}/install-packages.sh"

# Add PureBoot deploy script
mkdir -p "${ROOTFS_DIR}/usr/local/bin"
cat > "${ROOTFS_DIR}/usr/local/bin/pureboot-deploy" << 'DEPLOY_EOF'
#!/bin/bash
# PureBoot Image Deployment Script
# Reads parameters from kernel cmdline and deploys disk image

set -e

log() {
    echo "[PureBoot] $*"
}

error() {
    log "ERROR: $*"
    # Notify server of failure
    if [ -n "${PUREBOOT_SERVER}" ] && [ -n "${PUREBOOT_NODE_ID}" ]; then
        curl -sf -X POST "${PUREBOOT_SERVER}/api/v1/nodes/${PUREBOOT_NODE_ID}/install-failed" \
            -H "Content-Type: application/json" \
            -d "{\"error\": \"$*\"}" || true
    fi
    exit 1
}

# Parse kernel cmdline for pureboot.* parameters
parse_cmdline() {
    for param in $(cat /proc/cmdline); do
        case "$param" in
            pureboot.server=*)
                PUREBOOT_SERVER="${param#pureboot.server=}"
                ;;
            pureboot.node_id=*)
                PUREBOOT_NODE_ID="${param#pureboot.node_id=}"
                ;;
            pureboot.mac=*)
                PUREBOOT_MAC="${param#pureboot.mac=}"
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
            pureboot.post_script=*)
                PUREBOOT_POST_SCRIPT="${param#pureboot.post_script=}"
                ;;
        esac
    done
}

# Verify required parameters
verify_params() {
    [ -z "${PUREBOOT_IMAGE_URL}" ] && error "Missing pureboot.image_url"
    [ -z "${PUREBOOT_TARGET}" ] && error "Missing pureboot.target"
    [ ! -b "${PUREBOOT_TARGET}" ] && error "Target device not found: ${PUREBOOT_TARGET}"
}

# Detect image format from URL or content
detect_format() {
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
        *.qcow2)
            echo "qcow2"
            ;;
        *)
            echo "raw"
            ;;
    esac
}

# Deploy image to target device
deploy_image() {
    local format
    format=$(detect_format "${PUREBOOT_IMAGE_URL}")

    log "Deploying image to ${PUREBOOT_TARGET}"
    log "Image URL: ${PUREBOOT_IMAGE_URL}"
    log "Format: ${format}"

    # Get target device size
    local target_size
    target_size=$(blockdev --getsize64 "${PUREBOOT_TARGET}")
    log "Target size: $((target_size / 1024 / 1024 / 1024)) GB"

    # Download and write image
    case "${format}" in
        raw.gz)
            log "Downloading and decompressing gzip image..."
            curl -sfL "${PUREBOOT_IMAGE_URL}" | pigz -d | dd of="${PUREBOOT_TARGET}" bs=4M status=progress
            ;;
        raw.xz)
            log "Downloading and decompressing xz image..."
            curl -sfL "${PUREBOOT_IMAGE_URL}" | xz -d | dd of="${PUREBOOT_TARGET}" bs=4M status=progress
            ;;
        raw)
            log "Downloading raw image..."
            curl -sfL "${PUREBOOT_IMAGE_URL}" | dd of="${PUREBOOT_TARGET}" bs=4M status=progress
            ;;
        *)
            error "Unsupported image format: ${format}"
            ;;
    esac

    sync
    log "Image written successfully"
}

# Resize last partition to fill disk
resize_partitions() {
    log "Resizing partitions..."

    # Re-read partition table
    partprobe "${PUREBOOT_TARGET}" || true
    sleep 2

    # Find last partition number
    local last_part
    last_part=$(lsblk -n -o NAME "${PUREBOOT_TARGET}" | tail -1)
    local part_num
    part_num=$(echo "${last_part}" | sed 's/[^0-9]*//g')

    if [ -n "${part_num}" ]; then
        log "Extending partition ${part_num}..."
        # Use growpart if available, otherwise use parted
        if command -v growpart >/dev/null 2>&1; then
            growpart "${PUREBOOT_TARGET}" "${part_num}" || true
        else
            # Use parted to resize
            parted -s "${PUREBOOT_TARGET}" resizepart "${part_num}" 100% || true
        fi

        # Resize filesystem
        local part_dev="${PUREBOOT_TARGET}${part_num}"
        [ ! -b "${part_dev}" ] && part_dev="${PUREBOOT_TARGET}p${part_num}"

        if [ -b "${part_dev}" ]; then
            local fstype
            fstype=$(blkid -o value -s TYPE "${part_dev}" 2>/dev/null || echo "")
            case "${fstype}" in
                ext4|ext3|ext2)
                    log "Resizing ext filesystem on ${part_dev}..."
                    e2fsck -f -y "${part_dev}" || true
                    resize2fs "${part_dev}" || true
                    ;;
                ntfs)
                    log "NTFS resize not supported in deploy environment"
                    ;;
                *)
                    log "Unknown filesystem type: ${fstype}"
                    ;;
            esac
        fi
    fi

    log "Partition resize complete"
}

# Run post-deployment script
run_post_script() {
    if [ -n "${PUREBOOT_POST_SCRIPT}" ]; then
        log "Running post-deployment script..."
        local script_file="/tmp/post-script.sh"
        curl -sfL "${PUREBOOT_POST_SCRIPT}" -o "${script_file}"
        chmod +x "${script_file}"
        "${script_file}"
        log "Post-script complete"
    fi
}

# Notify server of completion
notify_complete() {
    if [ -n "${PUREBOOT_CALLBACK}" ]; then
        log "Notifying server of completion..."
        curl -sf -X POST "${PUREBOOT_CALLBACK}" \
            -H "Content-Type: application/json" \
            -d '{"success": true}' || log "Warning: Failed to notify server"
    fi
}

# Main
main() {
    log "=== PureBoot Image Deployment ==="

    parse_cmdline
    verify_params

    log ""
    log "Configuration:"
    log "  Server:    ${PUREBOOT_SERVER:-not set}"
    log "  Node ID:   ${PUREBOOT_NODE_ID:-not set}"
    log "  MAC:       ${PUREBOOT_MAC:-not set}"
    log "  Image:     ${PUREBOOT_IMAGE_URL}"
    log "  Target:    ${PUREBOOT_TARGET}"
    log ""

    deploy_image
    resize_partitions
    run_post_script
    notify_complete

    log ""
    log "=== Deployment Complete ==="
    log "Rebooting in 5 seconds..."
    sleep 5
    reboot -f
}

main "$@"
DEPLOY_EOF
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-deploy"

# Copy clone scripts
echo "Copying clone scripts..."
cp "${SCRIPT_DIR}/scripts/pureboot-common.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-clone-source-direct.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-clone-target-direct.sh" "${ROOTFS_DIR}/usr/local/bin/"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-common.sh"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-clone-source-direct.sh"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-clone-target-direct.sh"

# Create init script
cat > "${ROOTFS_DIR}/init" << 'INIT_EOF'
#!/bin/sh
# PureBoot Deploy Init

# Mount essential filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev

# Wait for network
echo "Waiting for network..."
for i in $(seq 1 30); do
    if ip link show | grep -q "state UP"; then
        break
    fi
    sleep 1
done

# Get IP via DHCP
for iface in eth0 ens3 enp0s3; do
    if ip link show "$iface" 2>/dev/null | grep -q "state UP"; then
        udhcpc -i "$iface" -t 10 -n || true
        break
    fi
done

# Run deployment
exec /usr/local/bin/pureboot-deploy
INIT_EOF
chmod +x "${ROOTFS_DIR}/init"

# Create initrd
echo "Creating initrd..."
cd "${ROOTFS_DIR}"
find . | cpio -o -H newc | gzip -9 > "${OUTPUT_DIR}/initrd"

# Copy kernel (need to extract from Alpine or use host kernel)
echo ""
echo "=== Build Complete ==="
echo ""
echo "Output files:"
echo "  ${OUTPUT_DIR}/initrd"
echo ""
echo "NOTE: You need to provide a Linux kernel (vmlinuz) separately."
echo "Options:"
echo "  1. Download from Alpine: ${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/${ALPINE_ARCH}/netboot/"
echo "  2. Use your distribution's kernel"
echo "  3. Build a custom kernel"
echo ""
echo "Copy vmlinuz and initrd to /opt/pureboot/tftp/deploy/"
