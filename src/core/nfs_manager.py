"""NFS root filesystem management for diskless Pi nodes."""
import logging
import shutil
import tarfile
import uuid
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
        """Validate Pi serial number format.

        Args:
            serial: Pi serial number to validate

        Returns:
            True if valid 8-character hex string, False otherwise
        """
        if not serial or len(serial) != 8:
            return False
        try:
            int(serial, 16)
            return True
        except ValueError:
            return False

    def get_node_path(self, serial: str) -> Path:
        """Get path to node's NFS directory.

        Args:
            serial: Pi serial number

        Returns:
            Path to the node's overlay directory

        Raises:
            ValueError: If serial number is invalid
        """
        if not self.validate_serial(serial):
            raise ValueError(f"Invalid serial number: {serial}")
        return self.nodes_path / serial.lower()

    def get_base_images(self) -> list[str]:
        """List available base images.

        Returns:
            List of base image directory names
        """
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

        Raises:
            ValueError: If serial is invalid or base image not found
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
        """Set up per-node configuration files in overlay.

        Args:
            upper_dir: Path to overlay upper directory
            serial: Pi serial number
            hostname: Optional hostname (defaults to pi-<serial>)
        """
        etc_dir = upper_dir / "etc"
        etc_dir.mkdir(parents=True, exist_ok=True)

        # Set hostname
        hostname = hostname or f"pi-{serial}"
        (etc_dir / "hostname").write_text(f"{hostname}\n")

        # Generate unique machine-id
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
        try:
            node_path = self.get_node_path(serial)
        except ValueError:
            return False

        if node_path.exists():
            shutil.rmtree(node_path)
            logger.info(f"Deleted NFS overlay for {serial}")
            return True
        return False

    def get_node_info(self, serial: str) -> dict | None:
        """Get information about a node's NFS setup.

        Args:
            serial: Pi serial number

        Returns:
            Dict with base_image, hostname, paths, or None if not found
        """
        try:
            node_path = self.get_node_path(serial)
        except ValueError:
            return None

        if not node_path.exists():
            return None

        hostname_file = node_path / "upper" / "etc" / "hostname"
        hostname = hostname_file.read_text().strip() if hostname_file.exists() else None

        return {
            "serial": serial.lower(),
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

        Raises:
            FileNotFoundError: If archive doesn't exist
            ValueError: If image already exists
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

        Raises:
            ValueError: If serial is invalid
        """
        node_path = self.get_node_path(serial)
        base_path = self.base_path / base_image

        return (
            f"lowerdir={base_path},"
            f"upperdir={node_path}/upper,"
            f"workdir={node_path}/work"
        )

    def node_overlay_exists(self, serial: str) -> bool:
        """Check if a node overlay exists.

        Args:
            serial: Pi serial number

        Returns:
            True if overlay exists, False otherwise
        """
        try:
            node_path = self.get_node_path(serial)
            return node_path.exists()
        except ValueError:
            return False
