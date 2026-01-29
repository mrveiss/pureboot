#!/bin/bash
# PureBoot Installation Script
# Installs or updates PureBoot on Ubuntu systems
#
# Usage:
#   sudo ./setup.sh          # Install or update
#   sudo ./setup.sh install  # Fresh install
#   sudo ./setup.sh update   # Update existing installation

set -e

# Configuration
INSTALL_DIR="/opt/pureboot"
SERVICE_USER="pureboot"
SERVICE_GROUP="pureboot"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Determine mode: install or update
MODE="$1"
if [ -z "$MODE" ]; then
    if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/.venv/bin/python3" ]; then
        MODE="update"
    else
        MODE="install"
    fi
fi

show_header() {
    echo "========================================"
    if [ "$MODE" = "update" ]; then
        echo "  PureBoot Update"
    else
        echo "  PureBoot Installation"
    fi
    echo "========================================"
    echo ""
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_ubuntu() {
    if [ ! -f /etc/os-release ]; then
        log_error "Cannot detect OS. This script requires Ubuntu."
        exit 1
    fi

    source /etc/os-release
    if [ "$ID" != "ubuntu" ]; then
        log_error "This script requires Ubuntu. Detected: $ID"
        exit 1
    fi
    log_info "Detected Ubuntu $VERSION_ID"
}

install_system_packages() {
    log_info "Installing system packages..."
    apt-get update -qq
    apt-get install -y -qq software-properties-common libcap2-bin curl > /dev/null

    # Install Docker for building custom iPXE with bzImage support
    if ! command -v docker &> /dev/null; then
        log_info "Installing Docker..."
        apt-get install -y -qq ca-certificates gnupg > /dev/null
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
        chmod a+r /etc/apt/keyrings/docker.gpg 2>/dev/null || true
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
        if apt-get install -y -qq docker-ce docker-ce-cli containerd.io > /dev/null 2>&1; then
            log_info "Docker installed successfully"
            systemctl enable docker > /dev/null 2>&1 || true
            systemctl start docker > /dev/null 2>&1 || true
        else
            log_warn "Failed to install Docker - will use pre-built bootloaders from repo"
        fi
    else
        log_info "Docker already installed"
    fi

    # Install Python 3.11+ from deadsnakes PPA if needed
    CURRENT_PYTHON=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [ "$(printf '%s\n' "3.11" "$CURRENT_PYTHON" | sort -V | head -n1)" != "3.11" ]; then
        log_info "Installing Python 3.11 from deadsnakes PPA..."
        # Ensure add-apt-repository works properly
        apt-get install -y -qq software-properties-common > /dev/null

        # Remove and re-add PPA to ensure fresh state
        add-apt-repository --remove -y ppa:deadsnakes/ppa > /dev/null 2>&1 || true
        DEBIAN_FRONTEND=noninteractive add-apt-repository -y ppa:deadsnakes/ppa

        # Full apt update to refresh package lists
        apt-get update

        # Show available python3.11 packages for debugging
        log_info "Searching for python3.11 packages..."
        apt-cache search python3.11 | head -5 || true

        if ! apt-get install -y python3.11 python3.11-venv python3.11-dev; then
            log_error "Failed to install Python 3.11."
            log_error "Try running: sudo apt-get update && sudo apt-cache search python3.11"
            exit 1
        fi
        PYTHON_CMD="python3.11"
    else
        apt-get install -y -qq python3 python3-venv python3-pip > /dev/null
        PYTHON_CMD="python3"
    fi

    # Install Node.js 18+ from NodeSource if needed
    if command -v node &> /dev/null; then
        CURRENT_NODE=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
    else
        CURRENT_NODE=0
    fi
    if [ "$CURRENT_NODE" -lt 18 ]; then
        log_info "Installing Node.js 18 from NodeSource..."

        # Remove conflicting Ubuntu packages that interfere with NodeSource
        log_info "Removing conflicting packages..."
        apt-get remove -y libnode-dev libnode72 nodejs-doc > /dev/null 2>&1 || true
        apt-get autoremove -y > /dev/null 2>&1 || true

        # Fix any broken packages
        dpkg --configure -a > /dev/null 2>&1 || true
        apt-get -f install -y > /dev/null 2>&1 || true

        # Install from NodeSource
        curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
        if ! apt-get install -y nodejs; then
            log_error "Failed to install Node.js 18"
            exit 1
        fi
    else
        log_info "Node.js $CURRENT_NODE already installed"
    fi

    log_info "System packages installed"
}

check_python_version() {
    # Use specific python command if set, otherwise detect
    if [ -z "$PYTHON_CMD" ]; then
        if command -v python3.11 &> /dev/null; then
            PYTHON_CMD="python3.11"
        else
            PYTHON_CMD="python3"
        fi
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    REQUIRED_VERSION="3.11"
    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
        log_error "Python $REQUIRED_VERSION or higher is required (found $PYTHON_VERSION)"
        exit 1
    fi
    log_info "Python $PYTHON_VERSION detected ($PYTHON_CMD)"
}

check_node_version() {
    if ! command -v node &> /dev/null; then
        log_error "Node.js is not installed"
        exit 1
    fi
    NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$NODE_VERSION" -lt 18 ]; then
        log_warn "Node.js 18+ recommended (found v$NODE_VERSION). Frontend build may fail."
    fi
    log_info "Node.js v$NODE_VERSION detected"
}

create_service_user() {
    if ! id "$SERVICE_USER" &>/dev/null; then
        log_info "Creating service user '$SERVICE_USER'..."
        useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
        log_info "User '$SERVICE_USER' created"
    else
        log_info "User '$SERVICE_USER' already exists"
    fi
}

create_directories() {
    log_info "Creating directories..."
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/tftp/bios"
    mkdir -p "$INSTALL_DIR/tftp/uefi"
    mkdir -p "$INSTALL_DIR/tftp/grub"
    mkdir -p "$INSTALL_DIR/assets"
    mkdir -p "$INSTALL_DIR/data"
    mkdir -p "$INSTALL_DIR/certs"
    mkdir -p /var/lib/pureboot/workflows
}

install_bootloaders_from_repo() {
    # Fallback: Install pre-built bootloaders from repository
    # Used when Docker build fails or is unavailable
    log_info "Installing fallback bootloaders from repository..."

    # These are pre-built binaries stored in the repo
    # They may lack some features but provide basic functionality

    # Install iPXE UEFI bootloader
    if [ -f "$PROJECT_ROOT/bootloaders/uefi/ipxe.efi" ]; then
        cp "$PROJECT_ROOT/bootloaders/uefi/ipxe.efi" "$INSTALL_DIR/tftp/uefi/ipxe.efi"
        log_info "Installed ipxe.efi from repo (fallback)"
        cp "$PROJECT_ROOT/bootloaders/uefi/ipxe.efi" "$INSTALL_DIR/tftp/uefi/netboot.xyz.efi"
    else
        log_warn "bootloaders/uefi/ipxe.efi not found"
    fi

    # Install iPXE BIOS bootloader
    if [ -f "$PROJECT_ROOT/bootloaders/bios/undionly.kpxe" ]; then
        cp "$PROJECT_ROOT/bootloaders/bios/undionly.kpxe" "$INSTALL_DIR/tftp/bios/undionly.kpxe"
        log_info "Installed undionly.kpxe from repo (fallback)"
    else
        log_warn "bootloaders/bios/undionly.kpxe not found"
    fi
}

install_bootloaders() {
    log_info "Setting up bootloaders..."

    # Copy GRUB UEFI bootloaders (for Hyper-V and other UEFI systems)
    if [ ! -f "$INSTALL_DIR/tftp/bootx64.efi" ]; then
        if [ -f "$PROJECT_ROOT/bootloaders/bootx64.efi" ]; then
            cp "$PROJECT_ROOT/bootloaders/bootx64.efi" "$INSTALL_DIR/tftp/"
            log_info "Copied bootx64.efi (UEFI shim)"
        else
            log_warn "bootx64.efi not found in bootloaders/ - GRUB UEFI boot will not work"
        fi
    else
        log_info "bootx64.efi already exists"
    fi

    if [ ! -f "$INSTALL_DIR/tftp/grubx64.efi" ]; then
        if [ -f "$PROJECT_ROOT/bootloaders/grubx64.efi" ]; then
            cp "$PROJECT_ROOT/bootloaders/grubx64.efi" "$INSTALL_DIR/tftp/"
            log_info "Copied grubx64.efi (GRUB UEFI)"
        else
            log_warn "grubx64.efi not found in bootloaders/ - GRUB UEFI boot will not work"
        fi
    else
        log_info "grubx64.efi already exists"
    fi

    # Create default GRUB config if not exists
    if [ ! -f "$INSTALL_DIR/tftp/grub/grub.cfg" ]; then
        log_info "Creating default GRUB config..."
        cat > "$INSTALL_DIR/tftp/grub/grub.cfg" << 'GRUBCFG'
# PureBoot GRUB Configuration
set default=0
set timeout=5

menuentry "Boot from local disk" {
    exit
}
GRUBCFG
        log_info "Created grub/grub.cfg"
    fi

    log_info "Bootloader download complete"
}

build_custom_bootloaders() {
    # Build iPXE with bzImage support using Docker
    # This is the primary method - creates bootloaders with all required features

    if ! command -v docker &> /dev/null; then
        log_warn "Docker not available - using fallback bootloaders from repo"
        install_bootloaders_from_repo
        return 0
    fi

    # Get server IP for embedded script
    SERVER_IP=$(hostname -I | awk '{print $1}')
    SERVER_ADDR="${SERVER_IP}:8080"

    log_info "Building iPXE bootloaders with bzImage support..."
    log_info "This may take a few minutes on first run..."

    # Build Docker image
    log_info "Building iPXE builder Docker image..."
    if ! docker build -t pureboot/ipxe-builder "$PROJECT_ROOT/docker/ipxe-builder" > /dev/null 2>&1; then
        log_warn "Failed to build Docker image - using fallback bootloaders"
        install_bootloaders_from_repo
        return 0
    fi

    # Create temp directory for build
    BUILD_DIR=$(mktemp -d)
    trap "rm -rf $BUILD_DIR" EXIT

    # Build plain ipxe.efi (no embedded script, with bzImage support)
    # This is served via TFTP and boots from DHCP
    log_info "Building UEFI bootloader (ipxe.efi with bzImage support)..."
    if docker run --rm \
        -v "$INSTALL_DIR/tftp/uefi:/out" \
        pureboot/ipxe-builder \
        "make bin-x86_64-efi/ipxe.efi && cp bin-x86_64-efi/ipxe.efi /out/ipxe.efi" > /dev/null 2>&1; then
        log_info "Built ipxe.efi with bzImage support"
        # Also copy as netboot.xyz.efi for chainload fallback
        cp "$INSTALL_DIR/tftp/uefi/ipxe.efi" "$INSTALL_DIR/tftp/uefi/netboot.xyz.efi"
    else
        log_warn "UEFI bootloader build failed"
        install_bootloaders_from_repo
        return 0
    fi

    # Build plain undionly.kpxe (no embedded script)
    log_info "Building BIOS bootloader (undionly.kpxe)..."
    if docker run --rm \
        -v "$INSTALL_DIR/tftp/bios:/out" \
        pureboot/ipxe-builder \
        "make bin/undionly.kpxe && cp bin/undionly.kpxe /out/undionly.kpxe" > /dev/null 2>&1; then
        log_info "Built undionly.kpxe"
    else
        log_warn "BIOS bootloader build failed"
    fi

    # Also build branded versions with embedded script (optional)
    cat > "$BUILD_DIR/embed.ipxe" << SCRIPT
#!ipxe
# PureBoot Network Boot
dhcp
echo
echo     ____                  ____              __
echo    / __ \\\\__  __________  / __ )____  ____  / /_
echo   / /_/ / / / / ___/ _ \\\\/ __  / __ \\\\/ __ \\\\/ __/
echo  / ____/ /_/ / /  /  __/ /_/ / /_/ / /_/ / /_
echo /_/    \\\\__,_/_/   \\\\___/_____/\\\\____/\\\\____/\\\\__/
echo
echo Network Boot Infrastructure
echo
echo MAC: \${mac}  IP: \${ip}
echo
chain http://$SERVER_ADDR/api/v1/ipxe/boot.ipxe || shell
SCRIPT

    log_info "Building branded UEFI bootloader (pureboot.efi)..."
    docker run --rm \
        -v "$BUILD_DIR:/build" \
        -v "$INSTALL_DIR/tftp/uefi:/out" \
        pureboot/ipxe-builder \
        "make EMBED=/build/embed.ipxe bin-x86_64-efi/ipxe.efi && cp bin-x86_64-efi/ipxe.efi /out/pureboot.efi" > /dev/null 2>&1 || true

    log_info "Building branded BIOS bootloader (pureboot.kpxe)..."
    docker run --rm \
        -v "$BUILD_DIR:/build" \
        -v "$INSTALL_DIR/tftp/bios:/out" \
        pureboot/ipxe-builder \
        "make EMBED=/build/embed.ipxe bin/undionly.kpxe && cp bin/undionly.kpxe /out/pureboot.kpxe" > /dev/null 2>&1 || true

    rm -rf "$BUILD_DIR"
    trap - EXIT

    log_info "Bootloader build complete"
}

setup_pi_firmware() {
    # Download Raspberry Pi firmware files for network boot
    # This enables Pi 3, 4, and 5 to network boot via TFTP
    log_info "Setting up Raspberry Pi firmware..."

    PI_FIRMWARE_DIR="$INSTALL_DIR/tftp/rpi-firmware"
    PI_DEPLOY_DIR="$INSTALL_DIR/tftp/deploy-arm64"

    # Create directories
    mkdir -p "$PI_FIRMWARE_DIR"
    mkdir -p "$PI_DEPLOY_DIR"
    mkdir -p "$INSTALL_DIR/tftp/pi-nodes"

    # Check if firmware already exists
    if [ -f "$PI_FIRMWARE_DIR/bootcode.bin" ] && [ -f "$PI_FIRMWARE_DIR/start4.elf" ]; then
        log_info "Pi firmware already exists, skipping download"
    else
        log_info "Downloading Raspberry Pi firmware from GitHub..."

        # Download firmware files from raspberrypi/firmware repo
        FIRMWARE_URL="https://github.com/raspberrypi/firmware/raw/master/boot"

        # Pi 3 files (required for Pi 3 network boot)
        curl -fsSL "$FIRMWARE_URL/bootcode.bin" -o "$PI_FIRMWARE_DIR/bootcode.bin" 2>/dev/null || log_warn "Failed to download bootcode.bin"
        curl -fsSL "$FIRMWARE_URL/start.elf" -o "$PI_FIRMWARE_DIR/start.elf" 2>/dev/null || log_warn "Failed to download start.elf"
        curl -fsSL "$FIRMWARE_URL/fixup.dat" -o "$PI_FIRMWARE_DIR/fixup.dat" 2>/dev/null || log_warn "Failed to download fixup.dat"

        # Pi 4/5 files
        curl -fsSL "$FIRMWARE_URL/start4.elf" -o "$PI_FIRMWARE_DIR/start4.elf" 2>/dev/null || log_warn "Failed to download start4.elf"
        curl -fsSL "$FIRMWARE_URL/fixup4.dat" -o "$PI_FIRMWARE_DIR/fixup4.dat" 2>/dev/null || log_warn "Failed to download fixup4.dat"

        # Device tree files for common Pi models
        for dtb in bcm2710-rpi-3-b.dtb bcm2710-rpi-3-b-plus.dtb bcm2710-rpi-cm3.dtb \
                   bcm2711-rpi-4-b.dtb bcm2711-rpi-400.dtb bcm2711-rpi-cm4.dtb \
                   bcm2712-rpi-5-b.dtb bcm2712-rpi-500.dtb; do
            curl -fsSL "$FIRMWARE_URL/$dtb" -o "$PI_FIRMWARE_DIR/$dtb" 2>/dev/null || true
        done

        if [ -f "$PI_FIRMWARE_DIR/bootcode.bin" ]; then
            log_info "Pi firmware downloaded successfully"
        else
            log_warn "Failed to download Pi firmware - Pi network boot will not work"
        fi
    fi

    # Download ARM64 kernel and initramfs for Pi deploy environment
    if [ -f "$PI_DEPLOY_DIR/kernel8.img" ] && [ -f "$PI_DEPLOY_DIR/initramfs.img" ]; then
        log_info "Pi deploy files already exist, skipping download"
    else
        log_info "Downloading ARM64 deploy environment (Alpine Linux)..."

        # Alpine Linux ARM64 netboot files work well for Pi deploy environment
        ALPINE_URL="https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/aarch64/netboot"
        curl -fsSL "$ALPINE_URL/vmlinuz-lts" -o "$PI_DEPLOY_DIR/kernel8.img" 2>/dev/null || log_warn "Failed to download kernel8.img"
        curl -fsSL "$ALPINE_URL/initramfs-lts" -o "$PI_DEPLOY_DIR/initramfs.img" 2>/dev/null || log_warn "Failed to download initramfs.img"

        if [ -f "$PI_DEPLOY_DIR/kernel8.img" ]; then
            log_info "Pi deploy environment downloaded successfully"
        else
            log_warn "Failed to download Pi deploy environment - Pi provisioning will not work"
        fi
    fi
}

copy_application_files() {
    log_info "Copying application files..."

    # Remove old source (but preserve data, tftp, assets, .env, .venv)
    rm -rf "$INSTALL_DIR/src"
    rm -rf "$INSTALL_DIR/frontend"
    rm -rf "$INSTALL_DIR/scripts"
    rm -rf "$INSTALL_DIR/docker"

    # Copy new source
    cp -r "$PROJECT_ROOT/src" "$INSTALL_DIR/"
    cp -r "$PROJECT_ROOT/frontend" "$INSTALL_DIR/"
    cp -r "$PROJECT_ROOT/scripts" "$INSTALL_DIR/"
    cp -r "$PROJECT_ROOT/docker" "$INSTALL_DIR/"
    cp "$PROJECT_ROOT/requirements.txt" "$INSTALL_DIR/"
    cp "$PROJECT_ROOT/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true

    # Copy workflow definitions
    if [ -d "$PROJECT_ROOT/workflows" ]; then
        log_info "Copying workflow definitions..."
        cp -r "$PROJECT_ROOT/workflows/"* /var/lib/pureboot/workflows/ 2>/dev/null || true
        chown -R "$SERVICE_USER:$SERVICE_GROUP" /var/lib/pureboot/workflows 2>/dev/null || true
    fi
}

setup_venv() {
    if [ ! -d "$INSTALL_DIR/.venv" ]; then
        log_info "Creating Python virtual environment..."
        $PYTHON_CMD -m venv "$INSTALL_DIR/.venv"
    else
        log_info "Virtual environment exists"
    fi
}

install_python_deps() {
    log_info "Installing Python dependencies..."
    "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip --quiet
    "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
    log_info "Python dependencies installed"
}

build_frontend() {
    log_info "Building frontend..."
    cd "$INSTALL_DIR/frontend"
    npm install --silent 2>/dev/null
    npm run build --silent 2>/dev/null
    log_info "Frontend built"

    # Deploy to assets
    log_info "Deploying frontend assets..."
    rm -rf "$INSTALL_DIR/assets/"*
    cp -r "$INSTALL_DIR/frontend/dist/"* "$INSTALL_DIR/assets/"
    log_info "Frontend deployed to assets/"
}

set_capabilities() {
    log_info "Setting network capabilities..."
    # Resolve symlink to actual python binary
    PYTHON_BIN=$(readlink -f "$INSTALL_DIR/.venv/bin/python3")
    if setcap 'cap_net_bind_service=+ep' "$PYTHON_BIN" 2>/dev/null; then
        log_info "Capabilities set (ports 69, 4011 enabled)"
    else
        log_warn "Could not set capabilities on $PYTHON_BIN"
        log_warn "TFTP (port 69) and Proxy DHCP (port 4011) will require root"
    fi
}

set_ownership() {
    log_info "Setting file ownership..."
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
}

install_systemd_service() {
    log_info "Installing systemd service..."
    cp "$PROJECT_ROOT/systemd/pureboot.service" /etc/systemd/system/
    systemctl daemon-reload
    log_info "Systemd service installed"
}

enable_service() {
    systemctl enable pureboot --quiet
    log_info "Service enabled for auto-start"
}

# ============================================
# Main: Install
# ============================================
do_install() {
    show_header
    check_root
    check_ubuntu
    install_system_packages
    check_python_version
    check_node_version
    create_service_user
    create_directories
    install_bootloaders
    build_custom_bootloaders
    setup_pi_firmware
    copy_application_files
    setup_venv
    install_python_deps
    build_frontend
    set_capabilities
    set_ownership
    install_systemd_service
    enable_service

    echo ""
    echo "========================================"
    echo "  Installation Complete!"
    echo "========================================"
    echo ""
    echo "Installation directory: $INSTALL_DIR"
    echo ""
    echo "Service commands:"
    echo "  service pureboot start    - Start PureBoot"
    echo "  service pureboot stop     - Stop PureBoot"
    echo "  service pureboot restart  - Restart PureBoot"
    echo "  service pureboot status   - Check status"
    echo ""
    echo "View logs:"
    echo "  journalctl -u pureboot -f"
    echo ""
    echo "Configuration:"
    echo "  Edit $INSTALL_DIR/.env to override settings"
    echo "  See PUREBOOT_* environment variables"
    echo ""
    read -p "Start PureBoot now? [Y/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        systemctl start pureboot
        log_info "PureBoot started"
        echo ""
        echo "Access the web UI at: http://$(hostname -I | awk '{print $1}'):8080"
    fi
}

# ============================================
# Main: Update
# ============================================
do_update() {
    show_header
    check_root

    # Verify existing installation
    if [ ! -d "$INSTALL_DIR" ]; then
        log_error "PureBoot is not installed. Run './setup.sh install' first."
        exit 1
    fi

    # Pull latest code from git
    log_info "Fetching latest version from repository..."
    cd "$PROJECT_ROOT"
    if [ -d ".git" ]; then
        CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        git fetch --quiet
        git pull --quiet
        NEW_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
            log_info "Already at latest version ($CURRENT_COMMIT)"
        else
            log_info "Updated from $CURRENT_COMMIT to $NEW_COMMIT"
        fi
    else
        log_warn "Not a git repository. Skipping git pull."
    fi

    # Check if service is running
    WAS_RUNNING=false
    if systemctl is-active --quiet pureboot; then
        WAS_RUNNING=true
        log_info "Stopping PureBoot service..."
        systemctl stop pureboot
    fi

    check_ubuntu
    check_python_version
    check_node_version

    # Ensure directories exist (may be new in updates)
    mkdir -p "$INSTALL_DIR/certs"
    mkdir -p /var/lib/pureboot/workflows

    setup_pi_firmware
    copy_application_files
    install_python_deps
    build_frontend
    set_capabilities
    set_ownership
    install_systemd_service

    echo ""
    echo "========================================"
    echo "  Update Complete!"
    echo "========================================"
    echo ""
    echo "Updated files in: $INSTALL_DIR"
    echo ""
    echo "Preserved:"
    echo "  - $INSTALL_DIR/data/ (database)"
    echo "  - $INSTALL_DIR/tftp/ (boot files)"
    echo "  - $INSTALL_DIR/.env (configuration)"
    echo ""

    if [ "$WAS_RUNNING" = true ]; then
        log_info "Restarting PureBoot service..."
        systemctl start pureboot
        log_info "PureBoot restarted"
    else
        read -p "Start PureBoot now? [Y/n] " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            systemctl start pureboot
            log_info "PureBoot started"
        fi
    fi
}

# ============================================
# Entry point
# ============================================
case "$MODE" in
    install)
        do_install
        ;;
    update)
        do_update
        ;;
    *)
        echo "Usage: $0 [install|update]"
        echo ""
        echo "  install  - Fresh installation"
        echo "  update   - Update existing installation (preserves data)"
        echo ""
        echo "If no argument given, auto-detects based on existing installation."
        exit 1
        ;;
esac
