#!/bin/bash
# Build custom PureBoot iPXE bootloaders with embedded script
#
# This script builds iPXE binaries that automatically chain to your PureBoot server.
# The bootloaders will show the PureBoot logo and branding on boot.
#
# Usage:
#   ./build-ipxe.sh <server_address>
#   ./build-ipxe.sh 192.168.1.10:8080
#   ./build-ipxe.sh pureboot.local:8080

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_ROOT/docker/ipxe-builder"
OUTPUT_DIR="$PROJECT_ROOT/tftp"

# Server address (required)
SERVER_ADDRESS="${1:-}"

if [ -z "$SERVER_ADDRESS" ]; then
    echo "Build custom PureBoot iPXE bootloaders"
    echo ""
    echo "Usage: $0 <server_address>"
    echo ""
    echo "Examples:"
    echo "  $0 192.168.1.10:8080"
    echo "  $0 pureboot.local:8080"
    echo ""
    echo "The bootloaders will be placed in:"
    echo "  $OUTPUT_DIR/bios/pureboot.kpxe"
    echo "  $OUTPUT_DIR/uefi/pureboot.efi"
    exit 1
fi

log_info "Building custom iPXE for PureBoot server: $SERVER_ADDRESS"

# Check for Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker is required to build custom iPXE"
    log_error "Install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Create temp directory for build
BUILD_DIR=$(mktemp -d)
trap "rm -rf $BUILD_DIR" EXIT

# Generate embedded script
cat > "$BUILD_DIR/embed.ipxe" << EOF
#!ipxe
# PureBoot embedded boot script
# Auto-generated for server: $SERVER_ADDRESS

dhcp
echo
echo Booting from PureBoot server...
echo
chain http://$SERVER_ADDRESS/api/v1/ipxe/boot.ipxe || goto error

:error
echo
echo Failed to contact PureBoot server at $SERVER_ADDRESS
echo
echo Press any key for iPXE shell...
prompt
shell
EOF

log_info "Generated embedded script"

# Build Docker image if needed
log_info "Building Docker image (this may take a few minutes on first run)..."
docker build -t pureboot/ipxe-builder "$DOCKER_DIR"

# Create output directories
mkdir -p "$OUTPUT_DIR/bios"
mkdir -p "$OUTPUT_DIR/uefi"

# Build BIOS bootloader
log_info "Building BIOS bootloader (undionly.kpxe)..."
docker run --rm \
    -v "$BUILD_DIR:/build:ro" \
    -v "$OUTPUT_DIR/bios:/output" \
    pureboot/ipxe-builder \
    EMBED=/build/embed.ipxe bin/undionly.kpxe

# Copy output
if [ -f "$OUTPUT_DIR/bios/bin/undionly.kpxe" ]; then
    mv "$OUTPUT_DIR/bios/bin/undionly.kpxe" "$OUTPUT_DIR/bios/pureboot.kpxe"
    rm -rf "$OUTPUT_DIR/bios/bin"
    log_info "Created: $OUTPUT_DIR/bios/pureboot.kpxe"
fi

# Build UEFI bootloader
log_info "Building UEFI x64 bootloader (ipxe.efi)..."
docker run --rm \
    -v "$BUILD_DIR:/build:ro" \
    -v "$OUTPUT_DIR/uefi:/output" \
    pureboot/ipxe-builder \
    EMBED=/build/embed.ipxe bin-x86_64-efi/ipxe.efi

# Copy output
if [ -f "$OUTPUT_DIR/uefi/bin-x86_64-efi/ipxe.efi" ]; then
    mv "$OUTPUT_DIR/uefi/bin-x86_64-efi/ipxe.efi" "$OUTPUT_DIR/uefi/pureboot.efi"
    rm -rf "$OUTPUT_DIR/uefi/bin-x86_64-efi"
    log_info "Created: $OUTPUT_DIR/uefi/pureboot.efi"
fi

echo ""
echo -e "${CYAN}========================================"
echo "  Custom iPXE Build Complete!"
echo "========================================${NC}"
echo ""
echo "Bootloader files created:"
echo "  BIOS: $OUTPUT_DIR/bios/pureboot.kpxe"
echo "  UEFI: $OUTPUT_DIR/uefi/pureboot.efi"
echo ""
echo "DHCP Configuration:"
echo "  next-server: $(echo $SERVER_ADDRESS | cut -d: -f1)"
echo ""
echo "  For BIOS:  filename \"bios/pureboot.kpxe\""
echo "  For UEFI:  filename \"uefi/pureboot.efi\""
echo ""
echo "Or use dynamic configuration (recommended):"
echo "  if option arch = 00:00 { filename \"bios/pureboot.kpxe\"; }"
echo "  elsif option arch = 00:07 { filename \"uefi/pureboot.efi\"; }"
echo ""
