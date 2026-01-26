"""Raspberry Pi TFTP directory manager for network boot.

This module manages per-node TFTP directories for Raspberry Pi network boot.
Each Pi is identified by its serial number and gets a dedicated directory
containing:
- Symlinks to shared firmware files (start4.elf, fixup4.dat, DTBs)
- Symlinks to deploy kernel/initramfs
- Generated config.txt with boot configuration
- Generated cmdline.txt with kernel parameters
"""
import logging
import re
import shutil
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Valid serial number pattern: 8 lowercase hex characters
SERIAL_PATTERN = re.compile(r"^[0-9a-f]{8}$")

# Pi model configurations
PI_MODELS = {
    "pi4": {
        "firmware_files": ["start4.elf", "fixup4.dat"],
        "dtb": "bcm2711-rpi-4-b.dtb",
        "arm_64bit": True,
    },
    "pi3": {
        "firmware_files": ["start.elf", "fixup.dat"],
        "dtb": "bcm2710-rpi-3-b.dtb",
        "arm_64bit": True,
    },
    "pi5": {
        "firmware_files": ["start4.elf", "fixup4.dat"],
        "dtb": "bcm2712-rpi-5-b.dtb",
        "arm_64bit": True,
    },
}


def validate_serial(serial: str) -> bool:
    """Validate Pi serial number format.

    Args:
        serial: The serial number to validate.

    Returns:
        True if valid, False otherwise.
    """
    return bool(SERIAL_PATTERN.match(serial.lower()))


class PiManager:
    """Manages TFTP directories for Raspberry Pi network boot.

    Each Pi gets a directory at /tftpboot/pi-nodes/<serial>/ containing
    all files needed for network boot via TFTP.
    """

    def __init__(
        self,
        firmware_dir: Path,
        deploy_dir: Path,
        nodes_dir: Path,
    ):
        """Initialize PiManager.

        Args:
            firmware_dir: Directory containing Pi firmware files
                (start4.elf, fixup4.dat, DTBs, etc.)
            deploy_dir: Directory containing deploy kernel and initramfs
                (kernel8.img, initramfs.img)
            nodes_dir: Directory where per-node directories will be created
                (e.g., /tftpboot/pi-nodes/)
        """
        self.firmware_dir = Path(firmware_dir).resolve()
        self.deploy_dir = Path(deploy_dir).resolve()
        self.nodes_dir = Path(nodes_dir).resolve()

        logger.info(
            f"PiManager initialized: firmware={self.firmware_dir}, "
            f"deploy={self.deploy_dir}, nodes={self.nodes_dir}"
        )

    def _validate_serial(self, serial: str) -> str:
        """Validate and normalize serial number.

        Args:
            serial: The serial number to validate.

        Returns:
            Normalized (lowercase) serial number.

        Raises:
            ValueError: If serial number is invalid.
        """
        serial = serial.lower().strip()
        if not validate_serial(serial):
            raise ValueError(
                f"Invalid serial number: '{serial}'. "
                "Must be 8 lowercase hex characters."
            )
        return serial

    def get_node_directory(self, serial: str) -> Path:
        """Get the path to a node's TFTP directory.

        Args:
            serial: Pi serial number (8 hex chars).

        Returns:
            Path to the node's directory.
        """
        serial = self._validate_serial(serial)
        return self.nodes_dir / serial

    def node_exists(self, serial: str) -> bool:
        """Check if a node directory exists.

        Args:
            serial: Pi serial number (8 hex chars).

        Returns:
            True if the node directory exists.
        """
        return self.get_node_directory(serial).exists()

    def list_nodes(self) -> List[str]:
        """List all Pi node directories.

        Returns:
            List of serial numbers with directories.
        """
        nodes = []
        if self.nodes_dir.exists():
            for path in self.nodes_dir.iterdir():
                if path.is_dir() and validate_serial(path.name):
                    nodes.append(path.name)
        return sorted(nodes)

    def create_node_directory(
        self,
        serial: str,
        pi_model: str = "pi4",
        controller_url: Optional[str] = None,
    ) -> Path:
        """Create TFTP directory for a Pi node.

        Creates a directory structure with:
        - Symlinks to firmware files (start4.elf, fixup4.dat, DTB)
        - Symlinks to deploy files (kernel8.img, initramfs.img)
        - Generated config.txt
        - Generated cmdline.txt

        Args:
            serial: Pi serial number (8 hex chars).
            pi_model: Pi model (pi3, pi4, pi5). Defaults to "pi4".
            controller_url: PureBoot controller URL for cmdline.txt.

        Returns:
            Path to the created node directory.

        Raises:
            ValueError: If serial number is invalid or model unknown.
        """
        serial = self._validate_serial(serial)

        if pi_model not in PI_MODELS:
            raise ValueError(
                f"Unknown Pi model: '{pi_model}'. "
                f"Valid models: {list(PI_MODELS.keys())}"
            )

        model_config = PI_MODELS[pi_model]
        node_dir = self.nodes_dir / serial

        # Create node directory
        node_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Creating Pi node directory: {node_dir}")

        # Create symlinks to firmware files
        for firmware_file in model_config["firmware_files"]:
            src = self.firmware_dir / firmware_file
            dst = node_dir / firmware_file
            if src.exists() and not dst.exists():
                dst.symlink_to(src)
                logger.debug(f"Created symlink: {dst} -> {src}")

        # Create symlink to DTB
        dtb_file = model_config["dtb"]
        dtb_src = self.firmware_dir / dtb_file
        dtb_dst = node_dir / dtb_file
        if dtb_src.exists() and not dtb_dst.exists():
            dtb_dst.symlink_to(dtb_src)
            logger.debug(f"Created symlink: {dtb_dst} -> {dtb_src}")

        # Create symlinks to deploy files (kernel and initramfs)
        deploy_files = ["kernel8.img", "initramfs.img"]
        for deploy_file in deploy_files:
            src = self.deploy_dir / deploy_file
            dst = node_dir / deploy_file
            if src.exists() and not dst.exists():
                dst.symlink_to(src)
                logger.debug(f"Created symlink: {dst} -> {src}")

        # Generate and write config.txt
        config_txt = self.generate_config_txt(serial, pi_model)
        config_path = node_dir / "config.txt"
        config_path.write_text(config_txt)
        logger.debug(f"Created config.txt: {config_path}")

        # Generate and write cmdline.txt
        cmdline_txt = self.generate_cmdline_txt(serial, controller_url)
        cmdline_path = node_dir / "cmdline.txt"
        cmdline_path.write_text(cmdline_txt)
        logger.debug(f"Created cmdline.txt: {cmdline_path}")

        logger.info(f"Pi node directory created successfully: {serial}")
        return node_dir

    def delete_node_directory(self, serial: str) -> None:
        """Delete TFTP directory for a Pi node.

        Safely removes the entire node directory and its contents.

        Args:
            serial: Pi serial number (8 hex chars).
        """
        try:
            serial = self._validate_serial(serial)
        except ValueError:
            # Invalid serial - nothing to delete
            logger.warning(f"Invalid serial number for deletion: {serial}")
            return

        node_dir = self.nodes_dir / serial

        if node_dir.exists():
            shutil.rmtree(node_dir)
            logger.info(f"Deleted Pi node directory: {serial}")
        else:
            logger.debug(f"Pi node directory does not exist: {serial}")

    def generate_config_txt(
        self,
        serial: str,
        pi_model: str = "pi4",
    ) -> str:
        """Generate config.txt content for a Pi node.

        Args:
            serial: Pi serial number (8 hex chars).
            pi_model: Pi model (pi3, pi4, pi5). Defaults to "pi4".

        Returns:
            config.txt content as string.
        """
        serial = self._validate_serial(serial)

        if pi_model not in PI_MODELS:
            raise ValueError(f"Unknown Pi model: '{pi_model}'")

        model_config = PI_MODELS[pi_model]
        lines = [
            "# PureBoot auto-generated config.txt",
            f"# Pi Serial: {serial}",
            f"# Pi Model: {pi_model}",
            "",
            "# Boot configuration",
        ]

        # 64-bit mode
        if model_config["arm_64bit"]:
            lines.append("arm_64bit=1")

        # Kernel and initramfs
        lines.extend([
            "",
            "# Kernel",
            "kernel=kernel8.img",
            "initramfs initramfs.img followkernel",
        ])

        # Device tree
        lines.extend([
            "",
            "# Device tree",
            f"device_tree={model_config['dtb']}",
        ])

        # Enable UART for debugging
        lines.extend([
            "",
            "# UART console (for debugging)",
            "enable_uart=1",
            "uart_2ndstage=1",
        ])

        # GPU memory (minimal for headless)
        lines.extend([
            "",
            "# GPU memory (minimal for headless)",
            "gpu_mem=16",
        ])

        # Disable splash/logo for faster boot
        lines.extend([
            "",
            "# Fast boot",
            "disable_splash=1",
            "boot_delay=0",
        ])

        return "\n".join(lines) + "\n"

    def generate_cmdline_txt(
        self,
        serial: str,
        controller_url: Optional[str] = None,
    ) -> str:
        """Generate cmdline.txt content for a Pi node.

        Args:
            serial: Pi serial number (8 hex chars).
            controller_url: PureBoot controller URL.

        Returns:
            cmdline.txt content as string (single line).
        """
        serial = self._validate_serial(serial)

        params = [
            # Console on serial UART
            "console=serial0,115200",
            "console=tty1",
            # Network configuration via DHCP
            "ip=dhcp",
            # PureBoot parameters
            f"pureboot.serial={serial}",
        ]

        if controller_url:
            params.append(f"pureboot.url={controller_url}")

        # Root filesystem (initramfs)
        params.extend([
            "root=/dev/ram0",
            "rootfstype=ramfs",
        ])

        # Boot quietly but show errors
        params.extend([
            "quiet",
            "loglevel=4",
        ])

        return " ".join(params) + "\n"

    def update_cmdline_txt(
        self,
        serial: str,
        controller_url: Optional[str] = None,
    ) -> None:
        """Update cmdline.txt for an existing node.

        Args:
            serial: Pi serial number (8 hex chars).
            controller_url: PureBoot controller URL.

        Raises:
            FileNotFoundError: If node directory doesn't exist.
        """
        serial = self._validate_serial(serial)
        node_dir = self.nodes_dir / serial

        if not node_dir.exists():
            raise FileNotFoundError(f"Node directory not found: {serial}")

        cmdline_txt = self.generate_cmdline_txt(serial, controller_url)
        cmdline_path = node_dir / "cmdline.txt"
        cmdline_path.write_text(cmdline_txt)
        logger.info(f"Updated cmdline.txt for node: {serial}")

    def update_config_txt(
        self,
        serial: str,
        pi_model: str = "pi4",
    ) -> None:
        """Update config.txt for an existing node.

        Args:
            serial: Pi serial number (8 hex chars).
            pi_model: Pi model (pi3, pi4, pi5).

        Raises:
            FileNotFoundError: If node directory doesn't exist.
        """
        serial = self._validate_serial(serial)
        node_dir = self.nodes_dir / serial

        if not node_dir.exists():
            raise FileNotFoundError(f"Node directory not found: {serial}")

        config_txt = self.generate_config_txt(serial, pi_model)
        config_path = node_dir / "config.txt"
        config_path.write_text(config_txt)
        logger.info(f"Updated config.txt for node: {serial}")
