# ARM64/Raspberry Pi Phase 4: Diskless/NFS Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable Pi nodes to boot diskless from NFS root filesystems with per-node overlays

**Architecture:** Create NFSManager class to provision per-node NFS directories with overlayfs support. Update Pi deploy scripts to handle NFS root pivot. Add workflow support for `install_method: nfs`.

**Tech Stack:** Python (NFSManager), shell scripts (NFS boot), YAML (workflows)

---

## Task 1: Create NFS Manager Core Class

**Files:**
- Create: `src/core/nfs_manager.py`

**Step 1: Create NFSManager class for NFS root directory management**

```python
"""NFS root filesystem management for diskless Pi nodes."""
import logging
import os
import shutil
import tarfile
from pathlib import Path

logger = logging.getLogger(__name__)


class NFSManager:
    """Manages NFS root filesystems for diskless Pi nodes.

    Directory structure:
        nfs_root/
        ├── base/                    # Shared base images (read-only)
        │   └── ubuntu-arm64/        # Base rootfs
        └── nodes/                   # Per-node overlays
            └── <serial>/            # Node-specific overlay
                ├── upper/           # Writable layer
                ├── work/            # Overlayfs workdir
                └── merged/          # Mount point
    """

    def __init__(
        self,
        nfs_root: str | Path,
        base_dir: str = "base",
        nodes_dir: str = "nodes",
    ):
        """Initialize NFS manager.

        Args:
            nfs_root: Root directory for NFS exports
            base_dir: Subdirectory for base images
            nodes_dir: Subdirectory for per-node overlays
        """
        self.nfs_root = Path(nfs_root)
        self.base_path = self.nfs_root / base_dir
        self.nodes_path = self.nfs_root / nodes_dir

    def ensure_directories(self) -> None:
        """Create required directory structure."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.nodes_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"NFS directories initialized at {self.nfs_root}")

    def validate_serial(self, serial: str) -> bool:
        """Validate Pi serial number format."""
        if not serial or len(serial) != 8:
            return False
        try:
            int(serial, 16)
            return True
        except ValueError:
            return False

    def get_node_path(self, serial: str) -> Path:
        """Get path to node's NFS directory."""
        if not self.validate_serial(serial):
            raise ValueError(f"Invalid serial number: {serial}")
        return self.nodes_path / serial.lower()

    def get_base_images(self) -> list[str]:
        """List available base images."""
        if not self.base_path.exists():
            return []
        return [d.name for d in self.base_path.iterdir() if d.is_dir()]

    def create_node_overlay(
        self,
        serial: str,
        base_image: str,
        hostname: str | None = None,
    ) -> Path:
        """Create per-node overlay directory.

        Args:
            serial: Pi serial number
            base_image: Name of base image to use
            hostname: Optional hostname for the node

        Returns:
            Path to node's merged directory
        """
        serial = serial.lower()
        if not self.validate_serial(serial):
            raise ValueError(f"Invalid serial number: {serial}")

        base_path = self.base_path / base_image
        if not base_path.exists():
            raise ValueError(f"Base image not found: {base_image}")

        node_path = self.get_node_path(serial)

        # Create overlay directories
        upper_dir = node_path / "upper"
        work_dir = node_path / "work"
        merged_dir = node_path / "merged"

        for d in [upper_dir, work_dir, merged_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Create per-node configuration
        self._setup_node_config(upper_dir, serial, hostname)

        logger.info(f"Created NFS overlay for {serial}")
        return merged_dir

    def _setup_node_config(
        self,
        upper_dir: Path,
        serial: str,
        hostname: str | None,
    ) -> None:
        """Set up per-node configuration files in overlay."""
        etc_dir = upper_dir / "etc"
        etc_dir.mkdir(parents=True, exist_ok=True)

        # Set hostname
        hostname = hostname or f"pi-{serial}"
        (etc_dir / "hostname").write_text(f"{hostname}\n")

        # Generate unique machine-id
        import uuid
        machine_id = uuid.uuid4().hex
        (etc_dir / "machine-id").write_text(f"{machine_id}\n")

        logger.debug(f"Created config for {serial}: hostname={hostname}")

    def delete_node_overlay(self, serial: str) -> bool:
        """Delete a node's overlay directory.

        Args:
            serial: Pi serial number

        Returns:
            True if deleted, False if not found
        """
        node_path = self.get_node_path(serial)
        if node_path.exists():
            shutil.rmtree(node_path)
            logger.info(f"Deleted NFS overlay for {serial}")
            return True
        return False

    def get_node_info(self, serial: str) -> dict | None:
        """Get information about a node's NFS setup.

        Returns:
            Dict with base_image, hostname, paths, or None if not found
        """
        node_path = self.get_node_path(serial)
        if not node_path.exists():
            return None

        hostname_file = node_path / "upper" / "etc" / "hostname"
        hostname = hostname_file.read_text().strip() if hostname_file.exists() else None

        return {
            "serial": serial,
            "path": str(node_path),
            "hostname": hostname,
            "upper_dir": str(node_path / "upper"),
            "merged_dir": str(node_path / "merged"),
        }

    def extract_base_image(
        self,
        archive_path: str | Path,
        image_name: str,
    ) -> Path:
        """Extract a base image from tarball.

        Args:
            archive_path: Path to .tar.gz archive
            image_name: Name for the extracted image

        Returns:
            Path to extracted image directory
        """
        archive_path = Path(archive_path)
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        dest_path = self.base_path / image_name
        if dest_path.exists():
            raise ValueError(f"Image already exists: {image_name}")

        dest_path.mkdir(parents=True)

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(dest_path)

        logger.info(f"Extracted base image: {image_name}")
        return dest_path

    def get_overlay_mount_options(
        self,
        serial: str,
        base_image: str,
    ) -> str:
        """Get mount options string for overlayfs.

        Args:
            serial: Pi serial number
            base_image: Name of base image

        Returns:
            Mount options string for mount -t overlay
        """
        node_path = self.get_node_path(serial)
        base_path = self.base_path / base_image

        return (
            f"lowerdir={base_path},"
            f"upperdir={node_path}/upper,"
            f"workdir={node_path}/work"
        )
```

**Step 2: Commit**

```bash
git add src/core/nfs_manager.py
git commit -m "feat: add NFSManager class for diskless Pi boot"
```

---

## Task 2: Add NFS Settings to Configuration

**Files:**
- Modify: `src/config/settings.py`

**Step 1: Add NFS configuration settings**

Add to `PiSettings` class or create new `NFSSettings`:

```python
class NFSSettings(BaseModel):
    """NFS root filesystem settings."""

    enabled: bool = False
    root_path: str = "/srv/nfsroot"
    base_dir: str = "base"
    nodes_dir: str = "nodes"
    default_base_image: str = "ubuntu-arm64"
```

**Step 2: Commit**

```bash
git add src/config/settings.py
git commit -m "feat: add NFS settings for diskless Pi boot"
```

---

## Task 3: Update Pi NFS Boot Script

**Files:**
- Modify: `deploy/scripts/pureboot-pi-nfs.sh`

**Step 1: Replace placeholder with full NFS boot implementation**

```bash
#!/bin/bash
# PureBoot Pi NFS Boot Setup
# Boots Pi from NFS root filesystem with overlayfs

set -e

source /usr/local/bin/pureboot-common.sh
source /usr/local/bin/pureboot-common-arm64.sh

log "=== PureBoot Pi NFS Boot Setup ==="
log ""

# =============================================================================
# NFS Boot Configuration
# =============================================================================

log "NFS boot configuration:"
log "  NFS Server: ${PUREBOOT_NFS_SERVER:-not set}"
log "  NFS Path: ${PUREBOOT_NFS_PATH:-not set}"
log "  Serial: ${PUREBOOT_SERIAL:-$(get_pi_serial)}"
log ""

if [[ -z "${PUREBOOT_NFS_SERVER}" || -z "${PUREBOOT_NFS_PATH}" ]]; then
    log_error "NFS parameters not configured"
    log "Required: pureboot.nfs_server and pureboot.nfs_path"
    log ""
    log "Dropping to shell..."
    exec /bin/sh
fi

# Get serial for per-node overlay
SERIAL="${PUREBOOT_SERIAL:-$(get_pi_serial)}"
if [[ -z "${SERIAL}" ]]; then
    log_error "Could not determine Pi serial number"
    exec /bin/sh
fi

# =============================================================================
# Mount NFS Root
# =============================================================================

NFS_MOUNT="/mnt/nfs"
OVERLAY_MOUNT="/mnt/overlay"
NEWROOT="/mnt/newroot"

mkdir -p "${NFS_MOUNT}" "${OVERLAY_MOUNT}" "${NEWROOT}"

log "Mounting NFS share..."
if ! mount -t nfs -o rw,vers=4,nolock "${PUREBOOT_NFS_SERVER}:${PUREBOOT_NFS_PATH}" "${NFS_MOUNT}"; then
    log_error "Failed to mount NFS root"
    log "Trying NFSv3..."
    if ! mount -t nfs -o rw,vers=3,nolock "${PUREBOOT_NFS_SERVER}:${PUREBOOT_NFS_PATH}" "${NFS_MOUNT}"; then
        log_error "NFS mount failed completely"
        exec /bin/sh
    fi
fi
log "NFS mounted at ${NFS_MOUNT}"

# =============================================================================
# Setup Overlay Filesystem
# =============================================================================

# Check for overlay directories
BASE_DIR="${NFS_MOUNT}/base"
NODE_DIR="${NFS_MOUNT}/nodes/${SERIAL}"

if [[ ! -d "${BASE_DIR}" ]]; then
    log_error "Base directory not found: ${BASE_DIR}"
    log "Available in NFS mount:"
    ls -la "${NFS_MOUNT}" 2>/dev/null || true
    exec /bin/sh
fi

# Find base image (first directory in base/)
BASE_IMAGE=$(ls -1 "${BASE_DIR}" 2>/dev/null | head -1)
if [[ -z "${BASE_IMAGE}" ]]; then
    log_error "No base images found in ${BASE_DIR}"
    exec /bin/sh
fi
BASE_PATH="${BASE_DIR}/${BASE_IMAGE}"
log "Using base image: ${BASE_IMAGE}"

# Create node overlay directories if needed
if [[ ! -d "${NODE_DIR}" ]]; then
    log "Creating overlay directories for ${SERIAL}..."
    mkdir -p "${NODE_DIR}/upper" "${NODE_DIR}/work"

    # Set up basic per-node config
    mkdir -p "${NODE_DIR}/upper/etc"
    echo "pi-${SERIAL}" > "${NODE_DIR}/upper/etc/hostname"
    cat /proc/sys/kernel/random/uuid | tr -d '-' > "${NODE_DIR}/upper/etc/machine-id"
fi

# Mount overlayfs
log "Mounting overlay filesystem..."
if ! mount -t overlay overlay -o "lowerdir=${BASE_PATH},upperdir=${NODE_DIR}/upper,workdir=${NODE_DIR}/work" "${NEWROOT}"; then
    log_error "Failed to mount overlay filesystem"
    log "Attempting direct NFS root mount..."
    if ! mount --bind "${BASE_PATH}" "${NEWROOT}"; then
        log_error "Failed to mount root filesystem"
        exec /bin/sh
    fi
    log_warn "Running with read-only base (no overlay)"
fi

log "Overlay mounted at ${NEWROOT}"

# =============================================================================
# Prepare for pivot_root
# =============================================================================

# Verify we have a valid root filesystem
if [[ ! -x "${NEWROOT}/sbin/init" && ! -x "${NEWROOT}/lib/systemd/systemd" ]]; then
    log_error "No init found in new root"
    log "Contents of ${NEWROOT}:"
    ls -la "${NEWROOT}" 2>/dev/null || true
    exec /bin/sh
fi

# Create required mount points in new root
mkdir -p "${NEWROOT}/proc" "${NEWROOT}/sys" "${NEWROOT}/dev" "${NEWROOT}/run"

# Move existing mounts to new root
log "Moving mounts to new root..."
mount --move /proc "${NEWROOT}/proc" 2>/dev/null || mount -t proc proc "${NEWROOT}/proc"
mount --move /sys "${NEWROOT}/sys" 2>/dev/null || mount -t sysfs sysfs "${NEWROOT}/sys"
mount --move /dev "${NEWROOT}/dev" 2>/dev/null || mount -t devtmpfs devtmpfs "${NEWROOT}/dev"

# =============================================================================
# Switch Root
# =============================================================================

log ""
log "=== Switching to NFS root ==="
log ""

# Notify controller if callback configured
if [[ -n "${PUREBOOT_CALLBACK}" ]]; then
    curl -sf -X POST "${PUREBOOT_CALLBACK}" \
        -H "Content-Type: application/json" \
        -d '{"success": true, "mode": "nfs_boot"}' 2>/dev/null || true
fi

# Determine init path
if [[ -x "${NEWROOT}/lib/systemd/systemd" ]]; then
    INIT="/lib/systemd/systemd"
elif [[ -x "${NEWROOT}/sbin/init" ]]; then
    INIT="/sbin/init"
else
    INIT="/bin/sh"
fi

log "Executing switch_root to ${INIT}..."

# Clean up old root and switch
cd "${NEWROOT}"
mkdir -p "${NEWROOT}/oldroot"

# Use switch_root (preferred) or pivot_root
if command -v switch_root &>/dev/null; then
    exec switch_root "${NEWROOT}" "${INIT}"
else
    pivot_root "${NEWROOT}" "${NEWROOT}/oldroot"
    exec chroot . "${INIT}" <dev/console >dev/console 2>&1
fi

# Should never reach here
log_error "Failed to switch root"
exec /bin/sh
```

**Step 2: Commit**

```bash
git add deploy/scripts/pureboot-pi-nfs.sh
git commit -m "feat: implement full NFS boot with overlay support"
```

---

## Task 4: Add NFS Workflow Support to Boot Endpoint

**Files:**
- Modify: `src/api/routes/boot_pi.py`

**Step 1: Add NFS boot response generation**

Add helper function to generate NFS boot responses:

```python
def _create_nfs_boot_response(
    node: Node,
    workflow: dict,
) -> PiBootResponse:
    """Create boot response for NFS workflow."""
    return PiBootResponse(
        state=node.state,
        action="nfs_boot",
        message=f"Booting from NFS: {workflow.get('name', 'NFS Root')}",
        nfs_server=workflow.get("nfs_server"),
        nfs_path=workflow.get("nfs_path") or workflow.get("nfs_base_path"),
    )
```

Update the boot endpoint to handle `install_method: nfs`.

**Step 2: Commit**

```bash
git add src/api/routes/boot_pi.py
git commit -m "feat: add NFS boot support to Pi boot endpoint"
```

---

## Task 5: Create Example NFS Workflows

**Files:**
- Create: `workflows/examples/pi-diskless-nfs.yaml`
- Create: `workflows/examples/pi-k3s-worker.yaml`

**Step 1: Create basic NFS workflow**

```yaml
# Pi Diskless NFS Boot
# Boots Pi from NFS root with per-node overlay
id: pi-diskless-nfs
name: Pi Diskless (NFS Root)
description: Network boot Pi with NFS root filesystem and persistent overlay
arch: aarch64
install_method: nfs

# NFS configuration
nfs_server: "{{ nfs_server | default('192.168.1.10') }}"
nfs_base_path: /srv/nfsroot

# No local storage needed
target_device: null

# Tags for filtering
tags:
  - diskless
  - nfs
  - raspberry-pi
```

**Step 2: Create K3s worker workflow**

```yaml
# Pi K3s Worker (Diskless)
# Boots Pi as K3s cluster worker node
id: pi-k3s-worker
name: K3s Worker (Diskless Pi)
description: Raspberry Pi as diskless K3s cluster worker
arch: aarch64
install_method: nfs

# NFS configuration
nfs_server: "{{ nfs_server | default('192.168.1.10') }}"
nfs_base_path: /srv/nfsroot/k3s

# K3s configuration
variables:
  k3s_server: "{{ k3s_server | default('https://k3s-master:6443') }}"
  k3s_token: "{{ k3s_token }}"

# Post-boot configuration (run on first boot)
post_boot:
  - name: Join K3s cluster
    script: |
      curl -sfL https://get.k3s.io | K3S_URL="${k3s_server}" K3S_TOKEN="${k3s_token}" sh -s - agent

tags:
  - k3s
  - kubernetes
  - cluster
  - raspberry-pi
```

**Step 3: Commit**

```bash
git add workflows/examples/pi-diskless-nfs.yaml workflows/examples/pi-k3s-worker.yaml
git commit -m "feat: add example NFS workflows for Pi"
```

---

## Task 6: Add Unit Tests for NFSManager

**Files:**
- Create: `tests/unit/test_nfs_manager.py`

**Step 1: Create comprehensive tests**

```python
"""Unit tests for NFSManager."""
import os
import tempfile
from pathlib import Path

import pytest

from src.core.nfs_manager import NFSManager


class TestNFSManagerInit:
    """Test NFSManager initialization."""

    def test_init_with_defaults(self, tmp_path):
        """Test initialization with default subdirectories."""
        manager = NFSManager(tmp_path)
        assert manager.nfs_root == tmp_path
        assert manager.base_path == tmp_path / "base"
        assert manager.nodes_path == tmp_path / "nodes"

    def test_init_with_custom_dirs(self, tmp_path):
        """Test initialization with custom subdirectories."""
        manager = NFSManager(
            tmp_path,
            base_dir="images",
            nodes_dir="overlays",
        )
        assert manager.base_path == tmp_path / "images"
        assert manager.nodes_path == tmp_path / "overlays"


class TestNFSManagerValidation:
    """Test serial number validation."""

    @pytest.fixture
    def manager(self, tmp_path):
        return NFSManager(tmp_path)

    @pytest.mark.parametrize("serial,expected", [
        ("d83add36", True),
        ("00000000", True),
        ("ffffffff", True),
        ("ABCDEF12", True),  # Uppercase ok
        ("", False),
        ("d83add3", False),  # Too short
        ("d83add367", False),  # Too long
        ("d83addgg", False),  # Invalid hex
        ("../etc/passwd", False),  # Path traversal
    ])
    def test_validate_serial(self, manager, serial, expected):
        """Test serial number validation."""
        assert manager.validate_serial(serial) == expected


class TestNFSManagerDirectories:
    """Test directory management."""

    @pytest.fixture
    def manager(self, tmp_path):
        m = NFSManager(tmp_path)
        m.ensure_directories()
        return m

    def test_ensure_directories_creates_structure(self, manager):
        """Test that ensure_directories creates required dirs."""
        assert manager.base_path.exists()
        assert manager.nodes_path.exists()

    def test_get_node_path(self, manager):
        """Test getting path for valid serial."""
        path = manager.get_node_path("d83add36")
        assert path == manager.nodes_path / "d83add36"

    def test_get_node_path_normalizes_case(self, manager):
        """Test that serial is normalized to lowercase."""
        path = manager.get_node_path("D83ADD36")
        assert path == manager.nodes_path / "d83add36"

    def test_get_node_path_invalid_serial(self, manager):
        """Test that invalid serial raises ValueError."""
        with pytest.raises(ValueError):
            manager.get_node_path("invalid")


class TestNFSManagerOverlay:
    """Test overlay creation and deletion."""

    @pytest.fixture
    def manager(self, tmp_path):
        m = NFSManager(tmp_path)
        m.ensure_directories()
        # Create a base image
        base = m.base_path / "ubuntu-arm64"
        base.mkdir()
        (base / "bin").mkdir()
        (base / "etc").mkdir()
        return m

    def test_create_node_overlay(self, manager):
        """Test creating a node overlay."""
        merged = manager.create_node_overlay("d83add36", "ubuntu-arm64")

        node_path = manager.nodes_path / "d83add36"
        assert (node_path / "upper").exists()
        assert (node_path / "work").exists()
        assert merged.exists()

    def test_create_node_overlay_sets_hostname(self, manager):
        """Test that overlay sets hostname."""
        manager.create_node_overlay("d83add36", "ubuntu-arm64", hostname="test-pi")

        hostname_file = manager.nodes_path / "d83add36" / "upper" / "etc" / "hostname"
        assert hostname_file.exists()
        assert hostname_file.read_text().strip() == "test-pi"

    def test_create_node_overlay_generates_machine_id(self, manager):
        """Test that overlay generates machine-id."""
        manager.create_node_overlay("d83add36", "ubuntu-arm64")

        machine_id = manager.nodes_path / "d83add36" / "upper" / "etc" / "machine-id"
        assert machine_id.exists()
        assert len(machine_id.read_text().strip()) == 32

    def test_create_node_overlay_invalid_base(self, manager):
        """Test that invalid base image raises ValueError."""
        with pytest.raises(ValueError, match="Base image not found"):
            manager.create_node_overlay("d83add36", "nonexistent")

    def test_delete_node_overlay(self, manager):
        """Test deleting a node overlay."""
        manager.create_node_overlay("d83add36", "ubuntu-arm64")

        result = manager.delete_node_overlay("d83add36")
        assert result is True
        assert not (manager.nodes_path / "d83add36").exists()

    def test_delete_nonexistent_overlay(self, manager):
        """Test deleting nonexistent overlay returns False."""
        result = manager.delete_node_overlay("00000000")
        assert result is False


class TestNFSManagerInfo:
    """Test information retrieval."""

    @pytest.fixture
    def manager(self, tmp_path):
        m = NFSManager(tmp_path)
        m.ensure_directories()
        (m.base_path / "ubuntu-arm64").mkdir()
        (m.base_path / "alpine-arm64").mkdir()
        return m

    def test_get_base_images(self, manager):
        """Test listing base images."""
        images = manager.get_base_images()
        assert "ubuntu-arm64" in images
        assert "alpine-arm64" in images

    def test_get_node_info_exists(self, manager):
        """Test getting info for existing node."""
        # Create base image structure
        base = manager.base_path / "ubuntu-arm64"
        base.mkdir(exist_ok=True)
        (base / "bin").mkdir(exist_ok=True)

        manager.create_node_overlay("d83add36", "ubuntu-arm64", hostname="my-pi")

        info = manager.get_node_info("d83add36")
        assert info is not None
        assert info["serial"] == "d83add36"
        assert info["hostname"] == "my-pi"

    def test_get_node_info_not_found(self, manager):
        """Test getting info for nonexistent node."""
        info = manager.get_node_info("00000000")
        assert info is None
```

**Step 2: Commit**

```bash
git add tests/unit/test_nfs_manager.py
git commit -m "test: add unit tests for NFSManager"
```

---

## Task 7: Push Branch and Update PR

**Files:**
- None (git operations only)

**Step 1: Push changes**

```bash
git push origin feature/arm64-raspberry-pi
```

**Step 2: Update PR description**

Add Phase 4 section to PR body.

---

## Summary

Phase 4 enables diskless/NFS boot for Raspberry Pi with:

1. **NFSManager** (`src/core/nfs_manager.py`) - Manages NFS root directories and per-node overlays
2. **NFS Settings** - Configuration for NFS root paths
3. **NFS Boot Script** - Full overlay filesystem setup with switch_root
4. **Boot Endpoint** - NFS boot response generation
5. **Example Workflows** - Diskless and K3s worker templates
6. **Unit Tests** - Comprehensive NFSManager tests

The NFS boot flow:
1. Pi network boots, fetches instructions from controller
2. Controller returns `action: nfs_boot` with NFS server/path
3. Pi mounts NFS share, sets up overlayfs (base + per-node)
4. Pi pivots root to NFS overlay and boots init
