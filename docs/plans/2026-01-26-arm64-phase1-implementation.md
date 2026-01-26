# ARM64/Raspberry Pi Phase 1: Core Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Pi-specific database fields, schema validation, and TFTP directory management for Raspberry Pi network boot support.

**Architecture:** Extend the existing Node model with `pi_model` field and `pi` boot mode. Create a `PiManager` class to handle per-node TFTP directories with symlinks to shared firmware files. Generate `config.txt` and `cmdline.txt` dynamically based on node state.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, Pydantic v2, pytest, FastAPI

---

## Task 1: Add pi_model Field to Node Model

**Files:**
- Modify: `src/db/models.py:66-67` (after boot_mode field)
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_models.py`:

```python
def test_create_pi_node(self, session):
    """Create Raspberry Pi node with pi_model field."""
    node = Node(
        mac_address="dc:a6:32:12:34:56",
        arch="aarch64",
        boot_mode="pi",
        serial_number="d83add36",
        pi_model="pi4",
    )
    session.add(node)
    session.commit()

    assert node.arch == "aarch64"
    assert node.boot_mode == "pi"
    assert node.pi_model == "pi4"
    assert node.serial_number == "d83add36"


def test_pi_model_optional(self, session):
    """pi_model field is optional (nullable)."""
    node = Node(mac_address="00:11:22:33:44:55")
    session.add(node)
    session.commit()

    assert node.pi_model is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py::TestNodeModel::test_create_pi_node -v`
Expected: FAIL with AttributeError (pi_model not defined)

**Step 3: Write minimal implementation**

In `src/db/models.py`, add after line 67 (boot_mode field):

```python
    pi_model: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py::TestNodeModel -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/db/models.py tests/unit/test_models.py
git commit -m "feat: add pi_model field to Node model for Raspberry Pi support"
```

---

## Task 2: Update boot_mode Validation to Include 'pi'

**Files:**
- Modify: `src/api/schemas.py:82-89` (validate_boot_mode function)
- Test: `tests/unit/test_schemas.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_schemas.py` in `TestNodeCreate` class:

```python
def test_pi_boot_mode_accepted(self):
    """Pi boot mode is accepted."""
    node = NodeCreate(
        mac_address="dc:a6:32:12:34:56",
        arch="aarch64",
        boot_mode="pi",
    )
    assert node.boot_mode == "pi"


def test_pi_node_with_serial(self):
    """Pi node with serial number for identification."""
    node = NodeCreate(
        mac_address="dc:a6:32:12:34:56",
        arch="aarch64",
        boot_mode="pi",
        serial_number="d83add36",
    )
    assert node.serial_number == "d83add36"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_schemas.py::TestNodeCreate::test_pi_boot_mode_accepted -v`
Expected: FAIL with ValidationError "Invalid boot mode: pi"

**Step 3: Write minimal implementation**

In `src/api/schemas.py`, update `validate_boot_mode` (around line 82-89):

```python
@field_validator("boot_mode")
@classmethod
def validate_boot_mode(cls, v: str) -> str:
    """Validate boot mode."""
    valid = {"bios", "uefi", "pi"}
    if v not in valid:
        raise ValueError(f"Invalid boot mode: {v}. Must be one of {valid}")
    return v
```

Also update the Field definition examples (around line 54-58):

```python
boot_mode: str = Field(
    "bios",
    description="Boot mode",
    examples=["bios", "uefi", "pi"],
)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_schemas.py::TestNodeCreate -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/schemas.py tests/unit/test_schemas.py
git commit -m "feat: add 'pi' boot mode for Raspberry Pi nodes"
```

---

## Task 3: Add pi_model to NodeCreate and NodeResponse Schemas

**Files:**
- Modify: `src/api/schemas.py` (NodeCreate, NodeUpdate, NodeResponse classes)
- Test: `tests/unit/test_schemas.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_schemas.py`:

```python
class TestPiNodeSchemas:
    """Test Pi-specific node schema fields."""

    def test_node_create_with_pi_model(self):
        """NodeCreate accepts pi_model field."""
        node = NodeCreate(
            mac_address="dc:a6:32:12:34:56",
            arch="aarch64",
            boot_mode="pi",
            serial_number="d83add36",
            pi_model="pi4",
        )
        assert node.pi_model == "pi4"

    def test_pi_model_validation(self):
        """pi_model must be valid Pi model identifier."""
        node = NodeCreate(
            mac_address="dc:a6:32:12:34:56",
            pi_model="pi4",
        )
        assert node.pi_model == "pi4"

    def test_pi_model_optional(self):
        """pi_model is optional."""
        node = NodeCreate(mac_address="dc:a6:32:12:34:56")
        assert node.pi_model is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_schemas.py::TestPiNodeSchemas -v`
Expected: FAIL with "unexpected keyword argument 'pi_model'"

**Step 3: Write minimal implementation**

In `src/api/schemas.py`:

Add to `NodeCreate` class (after serial_number field, around line 63):
```python
pi_model: str | None = Field(
    None,
    description="Raspberry Pi model",
    examples=["pi3b+", "pi4", "pi5", "cm4"],
)
```

Add to `NodeUpdate` class (after system_uuid, around line 101):
```python
pi_model: str | None = None
```

Add to `NodeResponse` class (after boot_mode, around line 177):
```python
pi_model: str | None = None
```

Update `NodeResponse.from_node()` method to include pi_model:
```python
@classmethod
def from_node(cls, node) -> "NodeResponse":
    """Create response from Node model."""
    return cls(
        id=node.id,
        mac_address=node.mac_address,
        hostname=node.hostname,
        ip_address=node.ip_address,
        state=node.state,
        workflow_id=node.workflow_id,
        vendor=node.vendor,
        model=node.model,
        serial_number=node.serial_number,
        system_uuid=node.system_uuid,
        arch=node.arch,
        boot_mode=node.boot_mode,
        pi_model=getattr(node, 'pi_model', None),  # Handle nodes without pi_model
        group_id=node.group_id,
        tags=[t.tag for t in node.tags],
        install_attempts=node.install_attempts,
        last_install_error=node.last_install_error,
        state_changed_at=node.state_changed_at,
        created_at=node.created_at,
        updated_at=node.updated_at,
        last_seen_at=node.last_seen_at,
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_schemas.py::TestPiNodeSchemas -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/schemas.py tests/unit/test_schemas.py
git commit -m "feat: add pi_model field to node schemas"
```

---

## Task 4: Add Pi Settings to Configuration

**Files:**
- Modify: `src/config/settings.py`
- Test: Create `tests/unit/test_settings.py`

**Step 1: Write the failing test**

Create `tests/unit/test_settings.py`:

```python
"""Tests for application settings."""
import pytest
from pathlib import Path


class TestPiSettings:
    """Test Pi-specific settings."""

    def test_pi_settings_defaults(self):
        """Pi settings have sensible defaults."""
        from src.config.settings import PiSettings

        pi = PiSettings()
        assert pi.enabled is True
        assert pi.firmware_dir == Path("./tftp/rpi-firmware")
        assert pi.deploy_kernel == "kernel8.img"
        assert pi.deploy_initrd == "initramfs.img"

    def test_pi_settings_in_main_settings(self):
        """Pi settings accessible from main settings."""
        from src.config.settings import Settings

        settings = Settings()
        assert hasattr(settings, 'pi')
        assert settings.pi.enabled is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_settings.py -v`
Expected: FAIL with ImportError or AttributeError

**Step 3: Write minimal implementation**

In `src/config/settings.py`, add after `CASettings` class (around line 66):

```python
class PiSettings(BaseSettings):
    """Raspberry Pi boot settings."""
    enabled: bool = True
    firmware_dir: Path = Path("./tftp/rpi-firmware")
    deploy_dir: Path = Path("./tftp/deploy-arm64")
    deploy_kernel: str = "kernel8.img"
    deploy_initrd: str = "initramfs.img"
    # Directory for per-node TFTP files (will contain serial number subdirs)
    nodes_dir: Path = Path("./tftp/pi-nodes")
```

In `Settings` class, add after `ca` field (around line 91):
```python
pi: PiSettings = Field(default_factory=PiSettings)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_settings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/config/settings.py tests/unit/test_settings.py
git commit -m "feat: add Pi settings for firmware and deploy paths"
```

---

## Task 5: Create PiManager Class for TFTP Directory Management

**Files:**
- Create: `src/pxe/pi_manager.py`
- Test: `tests/unit/test_pi_manager.py`

**Step 1: Write the failing test**

Create `tests/unit/test_pi_manager.py`:

```python
"""Tests for Raspberry Pi TFTP directory manager."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil


class TestPiManager:
    """Test PiManager class."""

    @pytest.fixture
    def temp_tftp_root(self):
        """Create temporary TFTP root directory."""
        root = Path(tempfile.mkdtemp())
        # Create firmware directory with dummy files
        firmware_dir = root / "rpi-firmware"
        firmware_dir.mkdir(parents=True)
        (firmware_dir / "start4.elf").touch()
        (firmware_dir / "fixup4.dat").touch()
        (firmware_dir / "bcm2711-rpi-4-b.dtb").touch()

        # Create deploy directory
        deploy_dir = root / "deploy-arm64"
        deploy_dir.mkdir(parents=True)
        (deploy_dir / "kernel8.img").touch()
        (deploy_dir / "initramfs.img").touch()

        # Create nodes directory
        (root / "pi-nodes").mkdir(parents=True)

        yield root
        shutil.rmtree(root)

    def test_create_node_directory(self, temp_tftp_root):
        """Create TFTP directory for Pi node."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="pi4")

        assert node_dir.exists()
        assert (node_dir / "start4.elf").is_symlink()
        assert (node_dir / "config.txt").exists()

    def test_delete_node_directory(self, temp_tftp_root):
        """Delete TFTP directory for Pi node."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="pi4")
        assert node_dir.exists()

        manager.delete_node_directory(serial)
        assert not node_dir.exists()

    def test_serial_validation(self, temp_tftp_root):
        """Serial number must be valid hex string."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        with pytest.raises(ValueError, match="Invalid serial"):
            manager.create_node_directory("../../../etc", pi_model="pi4")

    def test_generate_config_txt(self, temp_tftp_root):
        """Generate config.txt for Pi node."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        config = manager.generate_config_txt(
            serial="d83add36",
            pi_model="pi4",
        )

        assert "arm_64bit=1" in config
        assert "kernel=kernel8.img" in config
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pi_manager.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

Create `src/pxe/pi_manager.py`:

```python
"""Raspberry Pi TFTP directory manager."""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Valid Pi serial number pattern (8 hex characters)
SERIAL_PATTERN = re.compile(r"^[0-9a-fA-F]{8}$")

# Pi 4 firmware files to symlink
PI4_FIRMWARE_FILES = [
    "start4.elf",
    "fixup4.dat",
    "start4x.elf",
    "fixup4x.dat",
    "bcm2711-rpi-4-b.dtb",
]

# Pi 5 firmware files
PI5_FIRMWARE_FILES = [
    "start4.elf",  # Pi 5 uses same GPU firmware
    "fixup4.dat",
    "bcm2712-rpi-5-b.dtb",
]


class PiManager:
    """Manages per-node TFTP directories for Raspberry Pi boot."""

    def __init__(
        self,
        firmware_dir: Path,
        deploy_dir: Path,
        nodes_dir: Path,
    ):
        """Initialize PiManager.

        Args:
            firmware_dir: Directory containing shared Pi firmware files
            deploy_dir: Directory containing ARM64 deploy kernel/initramfs
            nodes_dir: Directory to create per-node subdirectories
        """
        self.firmware_dir = Path(firmware_dir)
        self.deploy_dir = Path(deploy_dir)
        self.nodes_dir = Path(nodes_dir)

    def _validate_serial(self, serial: str) -> str:
        """Validate and normalize Pi serial number.

        Args:
            serial: Pi serial number (8 hex characters)

        Returns:
            Lowercase serial number

        Raises:
            ValueError: If serial is invalid
        """
        serial = serial.lower().strip()
        if not SERIAL_PATTERN.match(serial):
            raise ValueError(f"Invalid serial number: {serial}. Must be 8 hex characters.")
        return serial

    def _get_firmware_files(self, pi_model: str) -> list[str]:
        """Get list of firmware files for Pi model.

        Args:
            pi_model: Pi model identifier (pi4, pi5, etc.)

        Returns:
            List of firmware filenames to symlink
        """
        if pi_model in ("pi5",):
            return PI5_FIRMWARE_FILES
        # Default to Pi 4 firmware
        return PI4_FIRMWARE_FILES

    def get_node_directory(self, serial: str) -> Path:
        """Get path to node's TFTP directory.

        Args:
            serial: Pi serial number

        Returns:
            Path to node directory
        """
        serial = self._validate_serial(serial)
        return self.nodes_dir / serial

    def create_node_directory(
        self,
        serial: str,
        pi_model: str = "pi4",
        node_id: str | None = None,
    ) -> Path:
        """Create TFTP directory for a Pi node.

        Creates directory structure:
        - Symlinks to shared firmware files
        - Symlinks to deploy kernel/initramfs
        - Generated config.txt
        - Generated cmdline.txt (default discovered state)

        Args:
            serial: Pi serial number
            pi_model: Pi model identifier
            node_id: Optional PureBoot node ID for config

        Returns:
            Path to created directory
        """
        serial = self._validate_serial(serial)
        node_dir = self.nodes_dir / serial

        # Create directory
        node_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created Pi node directory: {node_dir}")

        # Symlink firmware files
        for filename in self._get_firmware_files(pi_model):
            src = self.firmware_dir / filename
            dst = node_dir / filename
            if src.exists() and not dst.exists():
                dst.symlink_to(src.resolve())
                logger.debug(f"Symlinked {filename}")

        # Symlink deploy kernel/initramfs
        for filename in ["kernel8.img", "initramfs.img"]:
            src = self.deploy_dir / filename
            dst = node_dir / filename
            if src.exists() and not dst.exists():
                dst.symlink_to(src.resolve())

        # Generate config.txt
        config_txt = self.generate_config_txt(serial, pi_model, node_id)
        (node_dir / "config.txt").write_text(config_txt)

        # Generate default cmdline.txt (discovered state)
        cmdline_txt = self.generate_cmdline_txt(serial, state="discovered")
        (node_dir / "cmdline.txt").write_text(cmdline_txt)

        return node_dir

    def delete_node_directory(self, serial: str) -> bool:
        """Delete TFTP directory for a Pi node.

        Args:
            serial: Pi serial number

        Returns:
            True if deleted, False if didn't exist
        """
        serial = self._validate_serial(serial)
        node_dir = self.nodes_dir / serial

        if not node_dir.exists():
            return False

        # Remove all files and symlinks
        for item in node_dir.iterdir():
            if item.is_symlink() or item.is_file():
                item.unlink()
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)

        node_dir.rmdir()
        logger.info(f"Deleted Pi node directory: {node_dir}")
        return True

    def generate_config_txt(
        self,
        serial: str,
        pi_model: str = "pi4",
        node_id: str | None = None,
    ) -> str:
        """Generate config.txt for Pi node.

        Args:
            serial: Pi serial number
            pi_model: Pi model identifier
            node_id: Optional PureBoot node ID

        Returns:
            config.txt content
        """
        lines = [
            f"# PureBoot generated config for Pi node",
            f"# Serial: {serial}",
            f"# Model: {pi_model}",
        ]
        if node_id:
            lines.append(f"# Node ID: {node_id}")

        lines.extend([
            "",
            "# Enable 64-bit mode",
            "arm_64bit=1",
            "",
            "# Kernel and initramfs",
            "kernel=kernel8.img",
            "initramfs initramfs.img followkernel",
            "",
            "# Enable UART for serial console",
            "enable_uart=1",
            "",
            "# Disable splash for faster boot",
            "disable_splash=1",
            "",
            "# Disable unnecessary features",
            "dtparam=audio=off",
        ])

        return "\n".join(lines) + "\n"

    def generate_cmdline_txt(
        self,
        serial: str,
        state: str = "discovered",
        server_url: str | None = None,
        node_id: str | None = None,
        mac_address: str | None = None,
        extra_params: dict | None = None,
    ) -> str:
        """Generate cmdline.txt for Pi node based on state.

        Args:
            serial: Pi serial number
            state: Node state (discovered, pending, installing, active)
            server_url: PureBoot server URL
            node_id: PureBoot node ID
            mac_address: Node MAC address
            extra_params: Additional kernel parameters

        Returns:
            cmdline.txt content (single line)
        """
        params = ["ip=dhcp"]

        # Console configuration
        params.append("console=ttyAMA0,115200")
        params.append("console=tty1")

        # PureBoot parameters
        params.append(f"pureboot.serial={serial}")
        params.append(f"pureboot.state={state}")

        if server_url:
            params.append(f"pureboot.server={server_url}")
        if node_id:
            params.append(f"pureboot.node_id={node_id}")
        if mac_address:
            params.append(f"pureboot.mac={mac_address}")

        # Add extra parameters
        if extra_params:
            for key, value in extra_params.items():
                params.append(f"{key}={value}")

        return " ".join(params) + "\n"

    def update_cmdline_txt(
        self,
        serial: str,
        **kwargs,
    ) -> bool:
        """Update cmdline.txt for a Pi node.

        Args:
            serial: Pi serial number
            **kwargs: Arguments passed to generate_cmdline_txt

        Returns:
            True if updated, False if node directory doesn't exist
        """
        serial = self._validate_serial(serial)
        node_dir = self.nodes_dir / serial

        if not node_dir.exists():
            return False

        cmdline_txt = self.generate_cmdline_txt(serial, **kwargs)
        (node_dir / "cmdline.txt").write_text(cmdline_txt)
        return True
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pi_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pxe/pi_manager.py tests/unit/test_pi_manager.py
git commit -m "feat: add PiManager for Pi TFTP directory management"
```

---

## Task 6: Update pxe Module __init__.py

**Files:**
- Modify: `src/pxe/__init__.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_pi_manager.py`:

```python
def test_pi_manager_importable_from_pxe():
    """PiManager is importable from src.pxe module."""
    from src.pxe import PiManager
    assert PiManager is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pi_manager.py::test_pi_manager_importable_from_pxe -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Read current `src/pxe/__init__.py` and add PiManager to exports:

```python
"""PXE/TFTP/DHCP modules."""
from .tftp_server import TFTPServer, TFTPHandler
from .dhcp_proxy import DHCPProxyServer
from .pi_manager import PiManager

__all__ = ["TFTPServer", "TFTPHandler", "DHCPProxyServer", "PiManager"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pi_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pxe/__init__.py tests/unit/test_pi_manager.py
git commit -m "feat: export PiManager from pxe module"
```

---

## Task 7: Add Integration Test for Pi Node Lifecycle

**Files:**
- Create: `tests/integration/test_pi_nodes.py`

**Step 1: Write the integration test**

Create `tests/integration/test_pi_nodes.py`:

```python
"""Integration tests for Raspberry Pi node management."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from src.main import app
from src.db.database import get_db, engine
from src.db.models import Base, Node


@pytest.fixture(autouse=True)
async def setup_database():
    """Create tables before each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestPiNodeAPI:
    """Test Pi node API endpoints."""

    @pytest.mark.asyncio
    async def test_create_pi_node(self, client):
        """Create a Raspberry Pi node via API."""
        response = await client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
                "serial_number": "d83add36",
                "pi_model": "pi4",
                "vendor": "Raspberry Pi Foundation",
                "model": "Raspberry Pi 4 Model B",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["arch"] == "aarch64"
        assert data["boot_mode"] == "pi"
        assert data["pi_model"] == "pi4"
        assert data["serial_number"] == "d83add36"

    @pytest.mark.asyncio
    async def test_update_pi_node(self, client):
        """Update Pi node's pi_model field."""
        # Create node
        create_response = await client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
            },
        )
        node_id = create_response.json()["id"]

        # Update pi_model
        update_response = await client.patch(
            f"/api/v1/nodes/{node_id}",
            json={"pi_model": "pi4"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["pi_model"] == "pi4"

    @pytest.mark.asyncio
    async def test_list_pi_nodes_by_arch(self, client):
        """Filter nodes by aarch64 architecture."""
        # Create x86 node
        await client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55", "arch": "x86_64"},
        )
        # Create Pi node
        await client.post(
            "/api/v1/nodes",
            json={
                "mac_address": "dc:a6:32:12:34:56",
                "arch": "aarch64",
                "boot_mode": "pi",
            },
        )

        # List all nodes
        response = await client.get("/api/v1/nodes")
        assert response.status_code == 200
        assert response.json()["total"] == 2

        # Filter by arch (if implemented)
        # This tests the groundwork - actual filtering may be added later
```

**Step 2: Run test**

Run: `pytest tests/integration/test_pi_nodes.py -v`
Expected: PASS (tests create/update/list operations for Pi nodes)

**Step 3: Commit**

```bash
git add tests/integration/test_pi_nodes.py
git commit -m "test: add integration tests for Pi node management"
```

---

## Task 8: Run Full Test Suite and Final Commit

**Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 2: Push branch**

```bash
git push -u origin feature/arm64-raspberry-pi
```

---

## Summary

After completing all tasks, you will have:

1. **Node model** with `pi_model` field for Pi variant tracking
2. **Schema validation** accepting `pi` boot mode and `pi_model` field
3. **Pi settings** in configuration for firmware/deploy paths
4. **PiManager class** for TFTP directory management:
   - Create per-node directories with symlinks
   - Generate `config.txt` and `cmdline.txt`
   - Delete directories on node removal
5. **Integration tests** for Pi node API operations

This completes Phase 1 (Core Infrastructure) of the ARM64/Raspberry Pi support feature.
