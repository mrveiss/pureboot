#!/bin/bash
# Setup PureBoot deployment environment
# Downloads Alpine netboot and adds deployment tools

set -e

INSTALL_DIR="${1:-/opt/pureboot}"
DEPLOY_DIR="${INSTALL_DIR}/tftp/deploy"
ALPINE_VERSION="3.19"
ALPINE_MIRROR="https://dl-cdn.alpinelinux.org/alpine"

echo "=== Setting up PureBoot Deploy Environment ==="

mkdir -p "${DEPLOY_DIR}"

# Download Alpine netboot kernel
KERNEL_URL="${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/x86_64/netboot/vmlinuz-lts"
if [ ! -f "${DEPLOY_DIR}/vmlinuz" ]; then
    echo "Downloading Alpine kernel..."
    curl -fsSL -o "${DEPLOY_DIR}/vmlinuz" "${KERNEL_URL}"
    echo "Downloaded vmlinuz"
else
    echo "vmlinuz already exists"
fi

# Download Alpine netboot initrd
INITRD_URL="${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/x86_64/netboot/initramfs-lts"
if [ ! -f "${DEPLOY_DIR}/initrd-base" ]; then
    echo "Downloading Alpine initrd..."
    curl -fsSL -o "${DEPLOY_DIR}/initrd-base" "${INITRD_URL}"
    echo "Downloaded initrd-base"
else
    echo "initrd-base already exists"
fi

# Download modloop (kernel modules)
MODLOOP_URL="${ALPINE_MIRROR}/v${ALPINE_VERSION}/releases/x86_64/netboot/modloop-lts"
if [ ! -f "${DEPLOY_DIR}/modloop" ]; then
    echo "Downloading Alpine modloop..."
    curl -fsSL -o "${DEPLOY_DIR}/modloop" "${MODLOOP_URL}"
    echo "Downloaded modloop"
else
    echo "modloop already exists"
fi

# Create the deploy script that will be added to initrd
mkdir -p "${DEPLOY_DIR}/overlay/usr/local/bin"

cat > "${DEPLOY_DIR}/overlay/usr/local/bin/pureboot-deploy" << 'DEPLOY_SCRIPT'
#!/bin/sh
# PureBoot Image Deployment Script
# Reads parameters from kernel cmdline and deploys disk image

log() {
    echo "[PureBoot] $*"
}

error() {
    log "ERROR: $*"
    if [ -n "${PUREBOOT_SERVER}" ] && [ -n "${PUREBOOT_NODE_ID}" ]; then
        wget -q -O - --post-data="{\"error\": \"$*\"}" \
            --header="Content-Type: application/json" \
            "${PUREBOOT_SERVER}/api/v1/nodes/${PUREBOOT_NODE_ID}/install-failed" 2>/dev/null || true
    fi
    log "Dropping to shell..."
    exec /bin/sh
}

# Parse kernel cmdline
parse_cmdline() {
    for param in $(cat /proc/cmdline); do
        case "$param" in
            pureboot.server=*) PUREBOOT_SERVER="${param#pureboot.server=}" ;;
            pureboot.node_id=*) PUREBOOT_NODE_ID="${param#pureboot.node_id=}" ;;
            pureboot.mac=*) PUREBOOT_MAC="${param#pureboot.mac=}" ;;
            pureboot.mode=*) PUREBOOT_MODE="${param#pureboot.mode=}" ;;
            pureboot.image_url=*) PUREBOOT_IMAGE_URL="${param#pureboot.image_url=}" ;;
            pureboot.target=*) PUREBOOT_TARGET="${param#pureboot.target=}" ;;
            pureboot.source_device=*) PUREBOOT_SOURCE_DEVICE="${param#pureboot.source_device=}" ;;
            pureboot.clone_source=*) PUREBOOT_CLONE_SOURCE="${param#pureboot.clone_source=}" ;;
            pureboot.callback=*) PUREBOOT_CALLBACK="${param#pureboot.callback=}" ;;
            pureboot.post_script=*) PUREBOOT_POST_SCRIPT="${param#pureboot.post_script=}" ;;
        esac
    done
}

verify_params() {
    case "${PUREBOOT_MODE}" in
        clone_source)
            [ -z "${PUREBOOT_SOURCE_DEVICE}" ] && error "Missing pureboot.source_device"
            ;;
        clone_target)
            [ -z "${PUREBOOT_CLONE_SOURCE}" ] && error "Missing pureboot.clone_source"
            [ -z "${PUREBOOT_TARGET}" ] && error "Missing pureboot.target"
            ;;
        *)
            # Default image deploy mode
            [ -z "${PUREBOOT_IMAGE_URL}" ] && error "Missing pureboot.image_url"
            [ -z "${PUREBOOT_TARGET}" ] && error "Missing pureboot.target"
            ;;
    esac
}

wait_for_device() {
    log "Waiting for target device ${PUREBOOT_TARGET}..."
    local count=0
    while [ ! -b "${PUREBOOT_TARGET}" ] && [ $count -lt 30 ]; do
        sleep 1
        count=$((count + 1))
    done
    [ ! -b "${PUREBOOT_TARGET}" ] && error "Target device not found: ${PUREBOOT_TARGET}"
    log "Found ${PUREBOOT_TARGET}"
}

deploy_image() {
    local url="${PUREBOOT_IMAGE_URL}"
    log "Deploying image: ${url}"
    log "Target: ${PUREBOOT_TARGET}"

    # Detect format and compression from URL
    case "${url}" in
        # Compressed raw images
        *.raw.gz|*.img.gz)
            log "Downloading and decompressing gzip raw image..."
            wget -q -O - "${url}" | gunzip | dd of="${PUREBOOT_TARGET}" bs=4M status=progress
            ;;
        *.raw.xz|*.img.xz)
            log "Downloading and decompressing xz raw image..."
            wget -q -O - "${url}" | xz -d | dd of="${PUREBOOT_TARGET}" bs=4M status=progress
            ;;
        *.raw.zst|*.img.zst)
            log "Downloading and decompressing zstd raw image..."
            wget -q -O - "${url}" | zstd -d | dd of="${PUREBOOT_TARGET}" bs=4M status=progress
            ;;
        # VM disk formats - these should be pre-converted on server
        # Use scripts/convert-vm-disk.sh to convert VMDK/VHD/QCOW2 to raw.gz
        *.qcow2*|*.vmdk*|*.vhd*)
            error "VM disk formats must be pre-converted to raw. Use convert-vm-disk.sh"
            ;;
        # Uncompressed raw
        *.raw|*.img)
            log "Downloading raw image..."
            wget -q -O - "${url}" | dd of="${PUREBOOT_TARGET}" bs=4M status=progress
            ;;
        # Default: assume raw
        *)
            log "Downloading image (assuming raw format)..."
            wget -q -O - "${url}" | dd of="${PUREBOOT_TARGET}" bs=4M status=progress
            ;;
    esac

    sync
    log "Image written"
}

resize_last_partition() {
    log "Resizing partitions..."

    # Re-read partition table
    partprobe "${PUREBOOT_TARGET}" 2>/dev/null || true
    sleep 2

    # Get disk and partition info
    local disk_size part_end last_part part_dev

    # Find last partition
    last_part=$(fdisk -l "${PUREBOOT_TARGET}" 2>/dev/null | grep "^${PUREBOOT_TARGET}" | tail -1 | awk '{print $1}')
    [ -z "${last_part}" ] && return

    log "Last partition: ${last_part}"

    # Try to extend with growpart or parted
    if command -v growpart >/dev/null 2>&1; then
        local part_num="${last_part##*[!0-9]}"
        growpart "${PUREBOOT_TARGET}" "${part_num}" 2>/dev/null || true
    fi

    # Resize filesystem
    if [ -b "${last_part}" ]; then
        local fstype
        fstype=$(blkid -o value -s TYPE "${last_part}" 2>/dev/null || echo "")
        case "${fstype}" in
            ext4|ext3|ext2)
                log "Resizing ext filesystem..."
                e2fsck -f -y "${last_part}" 2>/dev/null || true
                resize2fs "${last_part}" 2>/dev/null || true
                ;;
            btrfs)
                log "Btrfs will auto-resize on mount"
                ;;
        esac
    fi

    log "Resize complete"
}

notify_complete() {
    if [ -n "${PUREBOOT_CALLBACK}" ]; then
        log "Notifying server..."
        wget -q -O - --post-data='{"success": true}' \
            --header="Content-Type: application/json" \
            "${PUREBOOT_CALLBACK}" 2>/dev/null || true
    fi
}

notify_with_data() {
    local data="$1"
    if [ -n "${PUREBOOT_CALLBACK}" ]; then
        log "Notifying server..."
        wget -q -O - --post-data="${data}" \
            --header="Content-Type: application/json" \
            "${PUREBOOT_CALLBACK}" 2>/dev/null || true
    fi
}

run_post_script() {
    if [ -n "${PUREBOOT_POST_SCRIPT}" ]; then
        log "Running post-script..."
        wget -q -O /tmp/post.sh "${PUREBOOT_POST_SCRIPT}" && \
            chmod +x /tmp/post.sh && /tmp/post.sh || true
    fi
}

# Clone source mode: serve disk via HTTP for other nodes to clone
run_clone_source() {
    local device="${PUREBOOT_SOURCE_DEVICE}"
    local port=9999

    log "=== Clone Source Mode ==="
    log ""
    log "Source device: ${device}"

    # Wait for device
    local count=0
    while [ ! -b "${device}" ] && [ $count -lt 30 ]; do
        sleep 1
        count=$((count + 1))
    done
    [ ! -b "${device}" ] && error "Source device not found: ${device}"

    # Get device size
    local size
    size=$(blockdev --getsize64 "${device}")
    local size_gb=$((size / 1024 / 1024 / 1024))
    log "Device size: ${size_gb} GB (${size} bytes)"

    # Get our IP address
    local my_ip
    my_ip=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v 127.0.0.1 | head -1)
    log "My IP: ${my_ip}"

    # Notify server we're ready to serve
    notify_with_data "{\"ready\": true, \"ip\": \"${my_ip}\", \"port\": ${port}, \"size\": ${size}, \"device\": \"${device}\"}"

    log ""
    log "============================================"
    log "  CLONE SOURCE READY"
    log "============================================"
    log ""
    log "  URL: http://${my_ip}:${port}/disk.raw"
    log "  Size: ${size_gb} GB"
    log ""
    log "  Waiting for clone requests..."
    log "  Press Ctrl+C to stop serving."
    log ""

    # Serve the disk via simple HTTP using busybox httpd or netcat
    # Create a simple CGI script to stream the disk
    mkdir -p /tmp/www/cgi-bin
    cat > /tmp/www/cgi-bin/disk.raw << DISKSCRIPT
#!/bin/sh
echo "Content-Type: application/octet-stream"
echo "Content-Length: ${size}"
echo ""
dd if=${device} bs=4M 2>/dev/null
DISKSCRIPT
    chmod +x /tmp/www/cgi-bin/disk.raw

    # Also create a gzip version for faster transfer
    cat > /tmp/www/cgi-bin/disk.raw.gz << GZSCRIPT
#!/bin/sh
echo "Content-Type: application/octet-stream"
echo "Transfer-Encoding: chunked"
echo ""
dd if=${device} bs=4M 2>/dev/null | gzip -1
GZSCRIPT
    chmod +x /tmp/www/cgi-bin/disk.raw.gz

    # Create info endpoint
    cat > /tmp/www/cgi-bin/info << INFOSCRIPT
#!/bin/sh
echo "Content-Type: application/json"
echo ""
echo "{\"device\": \"${device}\", \"size\": ${size}, \"size_gb\": ${size_gb}}"
INFOSCRIPT
    chmod +x /tmp/www/cgi-bin/info

    # Start HTTP server (busybox httpd with CGI support)
    cd /tmp/www
    httpd -f -p ${port} -c /dev/null 2>&1 &
    local httpd_pid=$!

    # Keep running until interrupted or server signals done
    log "HTTP server started (PID: ${httpd_pid})"

    # Wait for completion signal from server or manual interrupt
    while true; do
        # Check if server wants us to stop
        local status
        status=$(wget -q -O - "${PUREBOOT_SERVER}/api/v1/nodes/${PUREBOOT_NODE_ID}" 2>/dev/null | grep -o '"state":"[^"]*"' | cut -d'"' -f4)
        if [ "${status}" = "retired" ] || [ "${status}" = "pending_decommission" ]; then
            log "Server requested shutdown"
            break
        fi
        sleep 10
    done

    kill ${httpd_pid} 2>/dev/null || true
    log "Clone source stopped"
}

# Clone target mode: receive disk from source node
run_clone_target() {
    local source_url="${PUREBOOT_CLONE_SOURCE}"
    local target="${PUREBOOT_TARGET}"

    log "=== Clone Target Mode ==="
    log ""
    log "Source: ${source_url}"
    log "Target: ${target}"

    wait_for_device

    # Get source info
    log "Getting source disk info..."
    local info
    info=$(wget -q -O - "${source_url%/*}/info" 2>/dev/null || echo "")
    if [ -n "${info}" ]; then
        log "Source info: ${info}"
    fi

    # Clone the disk
    log "Starting disk clone..."
    log "This may take a while depending on disk size..."

    if echo "${source_url}" | grep -q '\.gz$'; then
        log "Downloading compressed stream..."
        wget -q -O - "${source_url}" | gunzip | dd of="${target}" bs=4M status=progress
    else
        log "Downloading raw stream..."
        wget -q -O - "${source_url}" | dd of="${target}" bs=4M status=progress
    fi

    sync
    log "Clone complete"

    # Resize partitions
    resize_last_partition

    # Run post-script if any
    run_post_script

    # Notify completion
    notify_complete

    log ""
    log "=== Clone Complete ==="
    log "Rebooting in 5 seconds..."
    sleep 5
    reboot -f
}

main() {
    log "=== PureBoot Deploy ==="

    parse_cmdline
    verify_params

    log ""
    log "Server:  ${PUREBOOT_SERVER:-not set}"
    log "Node:    ${PUREBOOT_NODE_ID:-not set}"
    log "MAC:     ${PUREBOOT_MAC:-not set}"
    log "Mode:    ${PUREBOOT_MODE:-image}"
    log ""

    case "${PUREBOOT_MODE}" in
        clone_source)
            run_clone_source
            ;;
        clone_target)
            run_clone_target
            ;;
        *)
            # Default: image deployment
            log "Image:   ${PUREBOOT_IMAGE_URL}"
            log "Target:  ${PUREBOOT_TARGET}"
            log ""

            wait_for_device
            deploy_image
            resize_last_partition
            run_post_script
            notify_complete

            log ""
            log "=== Deployment Complete ==="
            log "Rebooting in 5 seconds..."
            sleep 5
            reboot -f
            ;;
    esac
}

main "$@"
DEPLOY_SCRIPT
chmod +x "${DEPLOY_DIR}/overlay/usr/local/bin/pureboot-deploy"

# Create init overlay that runs our script
mkdir -p "${DEPLOY_DIR}/overlay/etc/init.d"
cat > "${DEPLOY_DIR}/overlay/etc/init.d/pureboot" << 'INIT_SCRIPT'
#!/sbin/openrc-run
# PureBoot deployment service

depend() {
    need net
    after networking
}

start() {
    ebegin "Starting PureBoot deployment"
    /usr/local/bin/pureboot-deploy
    eend $?
}
INIT_SCRIPT
chmod +x "${DEPLOY_DIR}/overlay/etc/init.d/pureboot"

# Create combined initrd with overlay
echo "Creating combined initrd..."
cd "${DEPLOY_DIR}"

# Extract base initrd, add overlay, repack
WORK_DIR=$(mktemp -d)
cd "${WORK_DIR}"

# Extract base initrd (gzip compressed cpio)
gunzip -c "${DEPLOY_DIR}/initrd-base" | cpio -id 2>/dev/null || true

# Copy overlay
cp -a "${DEPLOY_DIR}/overlay/"* .

# Repack
find . | cpio -o -H newc 2>/dev/null | gzip -9 > "${DEPLOY_DIR}/initrd"

# Cleanup
cd /
rm -rf "${WORK_DIR}"

echo ""
echo "=== Deploy Environment Ready ==="
echo ""
echo "Files created in ${DEPLOY_DIR}:"
ls -la "${DEPLOY_DIR}/"
echo ""
echo "To use image-based deployment, create a workflow like:"
echo '{'
echo '  "id": "ubuntu-image",'
echo '  "name": "Ubuntu 24.04 from Image",'
echo '  "install_method": "image",'
echo '  "image_url": "http://your-server/images/ubuntu-24.04.raw.gz",'
echo '  "target_device": "/dev/sda"'
echo '}'
