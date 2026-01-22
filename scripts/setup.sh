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
}

download_bootloaders() {
    log_info "Downloading bootloaders..."

    IPXE_BASE_URL="https://boot.ipxe.org"

    # Download iPXE UEFI bootloader
    if [ ! -f "$INSTALL_DIR/tftp/uefi/ipxe.efi" ]; then
        log_info "Downloading ipxe.efi (UEFI x64)..."
        if curl -fsSL "$IPXE_BASE_URL/ipxe.efi" -o "$INSTALL_DIR/tftp/uefi/ipxe.efi"; then
            log_info "Downloaded ipxe.efi"
        else
            log_warn "Failed to download ipxe.efi - iPXE UEFI boot will not work"
        fi
    else
        log_info "ipxe.efi already exists"
    fi

    # Download iPXE BIOS bootloader
    if [ ! -f "$INSTALL_DIR/tftp/bios/undionly.kpxe" ]; then
        log_info "Downloading undionly.kpxe (BIOS)..."
        if curl -fsSL "$IPXE_BASE_URL/undionly.kpxe" -o "$INSTALL_DIR/tftp/bios/undionly.kpxe"; then
            log_info "Downloaded undionly.kpxe"
        else
            log_warn "Failed to download undionly.kpxe - iPXE BIOS boot will not work"
        fi
    else
        log_info "undionly.kpxe already exists"
    fi

    # Copy GRUB UEFI bootloaders from system packages (for Hyper-V and other UEFI systems)
    if [ ! -f "$INSTALL_DIR/tftp/bootx64.efi" ]; then
        log_info "Installing GRUB UEFI bootloaders..."
        # Install grub-efi-amd64-signed and shim-signed packages
        if apt-get install -y -qq grub-efi-amd64-signed shim-signed > /dev/null 2>&1; then
            # Copy signed bootloaders
            if [ -f /usr/lib/shim/shimx64.efi.signed ]; then
                cp /usr/lib/shim/shimx64.efi.signed "$INSTALL_DIR/tftp/bootx64.efi"
                log_info "Copied bootx64.efi (signed shim)"
            elif [ -f /usr/lib/shim/shimx64.efi ]; then
                cp /usr/lib/shim/shimx64.efi "$INSTALL_DIR/tftp/bootx64.efi"
                log_info "Copied bootx64.efi (shim)"
            fi

            if [ -f /usr/lib/grub/x86_64-efi-signed/grubnetx64.efi.signed ]; then
                cp /usr/lib/grub/x86_64-efi-signed/grubnetx64.efi.signed "$INSTALL_DIR/tftp/grubx64.efi"
                log_info "Copied grubx64.efi (signed GRUB)"
            elif [ -f /usr/lib/grub/x86_64-efi/monolithic/grubnetx64.efi ]; then
                cp /usr/lib/grub/x86_64-efi/monolithic/grubnetx64.efi "$INSTALL_DIR/tftp/grubx64.efi"
                log_info "Copied grubx64.efi (GRUB)"
            fi
        else
            log_warn "Failed to install GRUB packages - GRUB UEFI boot will not work"
            log_info "You can manually copy bootx64.efi and grubx64.efi to $INSTALL_DIR/tftp/"
        fi
    else
        log_info "bootx64.efi already exists"
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
    # Only build if Docker is available
    if ! command -v docker &> /dev/null; then
        log_info "Docker not available - skipping custom bootloader build"
        log_info "To build custom branded bootloaders later, run:"
        log_info "  $INSTALL_DIR/scripts/build-ipxe.sh <server_ip>:8080"
        return 0
    fi

    # Get server IP for embedded script
    SERVER_IP=$(hostname -I | awk '{print $1}')
    SERVER_ADDR="${SERVER_IP}:8080"

    log_info "Building custom PureBoot bootloaders for $SERVER_ADDR..."
    log_info "This may take a few minutes on first run..."

    # Build Docker image
    log_info "Building iPXE builder Docker image..."
    if ! docker build -t pureboot/ipxe-builder "$PROJECT_ROOT/docker/ipxe-builder"; then
        log_warn "Failed to build Docker image - using stock bootloaders"
        return 0
    fi

    # Create temp directory for build
    BUILD_DIR=$(mktemp -d)
    trap "rm -rf $BUILD_DIR" EXIT

    # Generate embedded script with PureBoot branding
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

    # Build UEFI bootloader
    log_info "Building UEFI bootloader (ipxe.efi)..."
    docker run --rm \
        -v "$BUILD_DIR:/build" \
        -v "$INSTALL_DIR/tftp/uefi:/out" \
        pureboot/ipxe-builder \
        "make EMBED=/build/embed.ipxe bin-x86_64-efi/ipxe.efi && cp bin-x86_64-efi/ipxe.efi /out/pureboot.efi"

    if [ -f "$INSTALL_DIR/tftp/uefi/pureboot.efi" ]; then
        log_info "Created: tftp/uefi/pureboot.efi"
    else
        log_warn "UEFI bootloader build failed - using stock ipxe.efi"
    fi

    # Build BIOS bootloader
    log_info "Building BIOS bootloader (undionly.kpxe)..."
    docker run --rm \
        -v "$BUILD_DIR:/build" \
        -v "$INSTALL_DIR/tftp/bios:/out" \
        pureboot/ipxe-builder \
        "make EMBED=/build/embed.ipxe bin/undionly.kpxe && cp bin/undionly.kpxe /out/pureboot.kpxe"

    if [ -f "$INSTALL_DIR/tftp/bios/pureboot.kpxe" ]; then
        log_info "Created: tftp/bios/pureboot.kpxe"
    else
        log_warn "BIOS bootloader build failed - using stock undionly.kpxe"
    fi

    rm -rf "$BUILD_DIR"
    trap - EXIT

    log_info "Custom bootloader build complete"
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
    download_bootloaders
    build_custom_bootloaders
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
