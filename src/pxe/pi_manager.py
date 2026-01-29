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
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

# Valid serial number pattern: 8 lowercase hex characters
SERIAL_PATTERN = re.compile(r"^[0-9a-f]{8}$")

# Known Pi boot files for detection (combined approach)
# These files indicate a request is likely from a Pi network boot
PI_BOOT_FILES: Set[str] = {
    # First-stage bootloader (Pi 3 only)
    "bootcode.bin",
    # GPU firmware
    "start.elf", "start4.elf", "start_x.elf", "start4x.elf",
    "start_db.elf", "start4db.elf", "start_cd.elf", "start4cd.elf",
    # Memory configuration
    "fixup.dat", "fixup4.dat", "fixup_x.dat", "fixup4x.dat",
    "fixup_db.dat", "fixup4db.dat", "fixup_cd.dat", "fixup4cd.dat",
    # Configuration files
    "config.txt", "cmdline.txt",
    # Kernel and initramfs
    "kernel.img", "kernel7.img", "kernel7l.img", "kernel8.img",
    "initramfs.img", "initrd.img",
    # Device trees (common ones)
    "bcm2710-rpi-3-b.dtb", "bcm2710-rpi-3-b-plus.dtb",
    "bcm2710-rpi-cm3.dtb", "bcm2711-rpi-4-b.dtb",
    "bcm2712-rpi-5-b.dtb",
}

# DTB pattern for matching any .dtb file
DTB_PATTERN = re.compile(r"^bcm27\d{2}.*\.dtb$")

# Pi model configurations
# Note: Pi 3 requires bootcode.bin from TFTP (Pi 4/5 have it in EEPROM)
# Pi 3B requires OTP programming for network boot; Pi 3B+ has it enabled by default
PI_MODELS = {
    "pi3": {
        # Pi 3B - requires bootcode.bin from TFTP and OTP programming for network boot
        "firmware_files": ["bootcode.bin", "start.elf", "fixup.dat"],
        "dtb": "bcm2710-rpi-3-b.dtb",
        "arm_64bit": True,
        "requires_otp": True,  # Pi 3B needs OTP programming for USB/network boot
    },
    "pi3b+": {
        # Pi 3B+ - network boot enabled by default in ROM
        "firmware_files": ["bootcode.bin", "start.elf", "fixup.dat"],
        "dtb": "bcm2710-rpi-3-b-plus.dtb",
        "arm_64bit": True,
        "requires_otp": False,  # Pi 3B+ has network boot enabled by default
    },
    "cm3": {
        # Compute Module 3
        "firmware_files": ["bootcode.bin", "start.elf", "fixup.dat"],
        "dtb": "bcm2710-rpi-cm3.dtb",
        "arm_64bit": True,
        "requires_otp": True,
    },
    "pi4": {
        "firmware_files": ["start4.elf", "fixup4.dat"],
        "dtb": "bcm2711-rpi-4-b.dtb",
        "arm_64bit": True,
        "requires_otp": False,  # Pi 4 has network boot in EEPROM
    },
    "pi5": {
        "firmware_files": ["start4.elf", "fixup4.dat"],
        "dtb": "bcm2712-rpi-5-b.dtb",
        "arm_64bit": True,
        "requires_otp": False,  # Pi 5 has network boot in EEPROM
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


def is_pi_boot_file(filename: str) -> bool:
    """Check if a filename is a known Pi boot file.

    Uses combined detection: checks against known boot files list
    and DTB pattern matching.

    Args:
        filename: The filename to check (without path).

    Returns:
        True if the file is a known Pi boot file.
    """
    filename_lower = filename.lower()
    # Check exact match in known files
    if filename_lower in PI_BOOT_FILES:
        return True
    # Check DTB pattern for any device tree file
    if DTB_PATTERN.match(filename_lower):
        return True
    return False


def is_pi_serial_request(path: str) -> tuple[bool, str, str]:
    """Check if a TFTP path looks like a Pi serial number request.

    Pi network boot requests files with paths like:
    - /<serial>/start4.elf
    - /<serial>/bootcode.bin
    - /<serial>/config.txt

    Uses combined detection: path must have 8-hex-char directory
    AND the file must be a known Pi boot file.

    Args:
        path: The TFTP request path.

    Returns:
        Tuple of (is_pi_request, serial_number, filename).
        If not a Pi request, serial_number and filename are empty strings.
    """
    # Normalize path and split
    path = path.lstrip("/")
    parts = path.split("/")

    # Must have at least serial/filename
    if len(parts) < 2:
        return (False, "", "")

    potential_serial = parts[0].lower()
    filename = parts[-1]

    # Combined check: valid serial pattern AND known boot file
    if validate_serial(potential_serial) and is_pi_boot_file(filename):
        return (True, potential_serial, filename)

    return (False, "", "")


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
            pi_model: Pi model (pi3, pi3b+, cm3, pi4, pi5). Defaults to "pi4".
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
            pi_model: Pi model (pi3, pi3b+, cm3, pi4, pi5). Defaults to "pi4".

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
            pi_model: Pi model (pi3, pi3b+, cm3, pi4, pi5).

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

    def generate_cmdline_for_state(
        self,
        serial: str,
        state: str,
        controller_url: Optional[str] = None,
        node_id: Optional[str] = None,
        mac: Optional[str] = None,
        image_url: Optional[str] = None,
        target_device: Optional[str] = None,
        callback_url: Optional[str] = None,
        nfs_server: Optional[str] = None,
        nfs_path: Optional[str] = None,
    ) -> str:
        """Generate state-aware cmdline.txt content for a Pi node.

        This method generates kernel command line parameters based on the node's
        current state in the PureBoot lifecycle. Different states require
        different boot configurations (e.g., installing state needs image URL
        and target device, NFS boot needs server/path).

        Args:
            serial: Pi serial number (8 hex chars).
            state: Current PureBoot node state (e.g., 'discovered', 'installing').
            controller_url: PureBoot controller URL for callbacks.
            node_id: Node ID in PureBoot database.
            mac: MAC address of the Pi.
            image_url: URL to the OS image for installation.
            target_device: Target device for installation (e.g., /dev/mmcblk0).
            callback_url: URL for installation progress callbacks.
            nfs_server: NFS server IP for NFS root boot.
            nfs_path: NFS export path for NFS root boot.

        Returns:
            cmdline.txt content as string (single line ending with newline).

        Raises:
            ValueError: If serial number is invalid.
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
            f"pureboot.state={state}",
        ]

        # Add controller URL if provided
        if controller_url:
            params.append(f"pureboot.url={controller_url}")

        # Handle installing state with install mode parameters
        if state == "installing" and image_url:
            params.extend([
                "pureboot.mode=install",
                f"pureboot.image_url={image_url}",
            ])
            if target_device:
                params.append(f"pureboot.target={target_device}")
            if node_id:
                params.append(f"pureboot.node_id={node_id}")
            if mac:
                params.append(f"pureboot.mac={mac}")
            if callback_url:
                params.append(f"pureboot.callback={callback_url}")
            # Install mode uses ramfs
            params.extend([
                "root=/dev/ram0",
                "rootfstype=ramfs",
            ])
        elif nfs_server and nfs_path:
            # NFS root boot
            params.extend([
                "root=/dev/nfs",
                f"nfsroot={nfs_server}:{nfs_path},vers=4,tcp",
                "rw",
            ])
        else:
            # Default: ramfs root
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

    def update_cmdline_for_state(
        self,
        serial: str,
        state: str,
        **kwargs,
    ) -> None:
        """Update cmdline.txt for an existing node based on state.

        Generates state-aware kernel command line parameters and writes
        them to the node's cmdline.txt file.

        Args:
            serial: Pi serial number (8 hex chars).
            state: Current PureBoot node state.
            **kwargs: Additional parameters passed to generate_cmdline_for_state().
                Supported: controller_url, node_id, mac, image_url,
                target_device, callback_url, nfs_server, nfs_path.

        Raises:
            ValueError: If serial number is invalid.
            FileNotFoundError: If node directory doesn't exist.
        """
        serial = self._validate_serial(serial)
        node_dir = self.nodes_dir / serial

        if not node_dir.exists():
            raise FileNotFoundError(f"Node directory not found: {serial}")

        cmdline_txt = self.generate_cmdline_for_state(
            serial=serial,
            state=state,
            **kwargs,
        )
        cmdline_path = node_dir / "cmdline.txt"
        cmdline_path.write_text(cmdline_txt)
        logger.info(f"Updated cmdline.txt for node {serial} with state: {state}")


class PiDiscoveryManager:
    """Manages the Pi discovery directory for unknown Pi devices.

    When a Pi with an unknown serial number attempts to network boot,
    PureBoot serves files from the discovery directory instead. This
    allows the Pi to boot into a discovery environment that registers
    itself with the PureBoot controller.
    """

    def __init__(
        self,
        discovery_dir: Path,
        firmware_dir: Path,
        deploy_dir: Path,
        default_model: str = "pi4",
        controller_url: Optional[str] = None,
    ):
        """Initialize PiDiscoveryManager.

        Args:
            discovery_dir: Directory for discovery boot files.
            firmware_dir: Directory containing Pi firmware files.
            deploy_dir: Directory containing deploy kernel and initramfs.
            default_model: Default Pi model to assume (affects firmware selection).
            controller_url: PureBoot controller URL for registration.
        """
        self.discovery_dir = Path(discovery_dir).resolve()
        self.firmware_dir = Path(firmware_dir).resolve()
        self.deploy_dir = Path(deploy_dir).resolve()
        self.default_model = default_model
        self.controller_url = controller_url

        logger.info(
            f"PiDiscoveryManager initialized: discovery={self.discovery_dir}, "
            f"default_model={self.default_model}"
        )

    def ensure_discovery_directory(self) -> Path:
        """Create and populate the discovery directory if it doesn't exist.

        The discovery directory contains files needed for any Pi to boot
        into a discovery/registration environment. It includes firmware
        files for both Pi 3 and Pi 4/5 models.

        Returns:
            Path to the discovery directory.
        """
        if self.discovery_dir.exists():
            logger.debug(f"Discovery directory already exists: {self.discovery_dir}")
            return self.discovery_dir

        self.discovery_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Creating Pi discovery directory: {self.discovery_dir}")

        # Symlink firmware files for Pi 3 (bootcode.bin, start.elf, fixup.dat)
        pi3_files = ["bootcode.bin", "start.elf", "fixup.dat"]
        for firmware_file in pi3_files:
            src = self.firmware_dir / firmware_file
            dst = self.discovery_dir / firmware_file
            if src.exists() and not dst.exists():
                dst.symlink_to(src)
                logger.debug(f"Created symlink: {dst} -> {src}")

        # Symlink firmware files for Pi 4/5 (start4.elf, fixup4.dat)
        pi4_files = ["start4.elf", "fixup4.dat"]
        for firmware_file in pi4_files:
            src = self.firmware_dir / firmware_file
            dst = self.discovery_dir / firmware_file
            if src.exists() and not dst.exists():
                dst.symlink_to(src)
                logger.debug(f"Created symlink: {dst} -> {src}")

        # Symlink all DTB files for broad model support
        for dtb_file in self.firmware_dir.glob("*.dtb"):
            dst = self.discovery_dir / dtb_file.name
            if not dst.exists():
                dst.symlink_to(dtb_file)
                logger.debug(f"Created symlink: {dst} -> {dtb_file}")

        # Symlink deploy files (kernel and initramfs)
        deploy_files = ["kernel8.img", "initramfs.img"]
        for deploy_file in deploy_files:
            src = self.deploy_dir / deploy_file
            dst = self.discovery_dir / deploy_file
            if src.exists() and not dst.exists():
                dst.symlink_to(src)
                logger.debug(f"Created symlink: {dst} -> {src}")

        # Generate config.txt for discovery mode
        config_txt = self._generate_discovery_config()
        config_path = self.discovery_dir / "config.txt"
        config_path.write_text(config_txt)
        logger.debug(f"Created config.txt: {config_path}")

        # Generate cmdline.txt for discovery mode
        cmdline_txt = self._generate_discovery_cmdline()
        cmdline_path = self.discovery_dir / "cmdline.txt"
        cmdline_path.write_text(cmdline_txt)
        logger.debug(f"Created cmdline.txt: {cmdline_path}")

        logger.info(f"Pi discovery directory created successfully")
        return self.discovery_dir

    def _generate_discovery_config(self) -> str:
        """Generate config.txt for discovery boot.

        Returns:
            config.txt content compatible with Pi 3, 4, and 5.
        """
        lines = [
            "# PureBoot Discovery Mode config.txt",
            "# This configuration supports Pi 3, 4, and 5 models",
            "",
            "# Boot configuration",
            "arm_64bit=1",
            "",
            "# Kernel",
            "kernel=kernel8.img",
            "initramfs initramfs.img followkernel",
            "",
            "# UART console (for debugging)",
            "enable_uart=1",
            "uart_2ndstage=1",
            "",
            "# GPU memory (minimal for headless)",
            "gpu_mem=16",
            "",
            "# Fast boot",
            "disable_splash=1",
            "boot_delay=0",
        ]
        return "\n".join(lines) + "\n"

    def _generate_discovery_cmdline(self) -> str:
        """Generate cmdline.txt for discovery boot.

        The discovery cmdline includes pureboot.mode=discovery to indicate
        the deploy environment should register this Pi with the controller.

        Returns:
            cmdline.txt content as single line.
        """
        params = [
            # Console on serial UART
            "console=serial0,115200",
            "console=tty1",
            # Network configuration via DHCP
            "ip=dhcp",
            # PureBoot discovery mode
            "pureboot.mode=discovery",
            "pureboot.state=discovered",
        ]

        if self.controller_url:
            params.append(f"pureboot.url={self.controller_url}")

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

    def get_discovery_path(self) -> Path:
        """Get the path to the discovery directory.

        Returns:
            Path to the discovery directory.
        """
        return self.discovery_dir

    def update_controller_url(self, controller_url: str) -> None:
        """Update the controller URL in the discovery cmdline.txt.

        Args:
            controller_url: New controller URL.
        """
        self.controller_url = controller_url
        cmdline_txt = self._generate_discovery_cmdline()
        cmdline_path = self.discovery_dir / "cmdline.txt"
        if cmdline_path.parent.exists():
            cmdline_path.write_text(cmdline_txt)
            logger.info(f"Updated discovery cmdline.txt with URL: {controller_url}")
