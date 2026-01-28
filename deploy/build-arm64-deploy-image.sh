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

# OS configuration helpers
cp "${SCRIPT_DIR}/scripts/pureboot-cloud-init.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-raspios-config.sh" "${ROOTFS_DIR}/usr/local/bin/"

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