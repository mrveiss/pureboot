"""Tests for Raspberry Pi TFTP directory manager."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil


def test_pi_manager_importable_from_pxe():
    """PiManager is importable from src.pxe module."""
    from src.pxe import PiManager
    assert PiManager is not None


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

    def test_generate_cmdline_txt(self, temp_tftp_root):
        """Generate cmdline.txt for Pi node."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        cmdline = manager.generate_cmdline_txt(
            serial="d83add36",
            controller_url="http://192.168.1.100:8080",
        )

        assert "ip=dhcp" in cmdline
        assert "pureboot.serial=d83add36" in cmdline
        assert "pureboot.url=http://192.168.1.100:8080" in cmdline

    def test_serial_validation_too_short(self, temp_tftp_root):
        """Serial number must be 8 hex characters."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        with pytest.raises(ValueError, match="Invalid serial"):
            manager.create_node_directory("abc", pi_model="pi4")

    def test_serial_validation_non_hex(self, temp_tftp_root):
        """Serial number must contain only hex characters."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        with pytest.raises(ValueError, match="Invalid serial"):
            manager.create_node_directory("ghijklmn", pi_model="pi4")

    def test_symlinks_point_to_correct_files(self, temp_tftp_root):
        """Verify symlinks resolve to the correct firmware files."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="pi4")

        # Check firmware symlinks
        start4_link = node_dir / "start4.elf"
        assert start4_link.is_symlink()
        assert start4_link.resolve() == (temp_tftp_root / "rpi-firmware" / "start4.elf").resolve()

        # Check kernel symlink
        kernel_link = node_dir / "kernel8.img"
        assert kernel_link.is_symlink()
        assert kernel_link.resolve() == (temp_tftp_root / "deploy-arm64" / "kernel8.img").resolve()

    def test_update_cmdline_txt(self, temp_tftp_root):
        """Update cmdline.txt for existing node directory."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="pi4")

        # Update cmdline with new URL
        manager.update_cmdline_txt(serial, controller_url="http://newserver:8080")

        cmdline_path = node_dir / "cmdline.txt"
        cmdline_content = cmdline_path.read_text()
        assert "pureboot.url=http://newserver:8080" in cmdline_content

    def test_get_node_directory(self, temp_tftp_root):
        """Get path to node directory."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        expected_path = temp_tftp_root / "pi-nodes" / serial

        assert manager.get_node_directory(serial) == expected_path

    def test_node_exists(self, temp_tftp_root):
        """Check if node directory exists."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        assert not manager.node_exists(serial)

        manager.create_node_directory(serial, pi_model="pi4")
        assert manager.node_exists(serial)

    def test_list_nodes(self, temp_tftp_root):
        """List all Pi node directories."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        # Create multiple nodes
        manager.create_node_directory("d83add36", pi_model="pi4")
        manager.create_node_directory("a1b2c3d4", pi_model="pi4")

        nodes = manager.list_nodes()
        assert len(nodes) == 2
        assert "d83add36" in nodes
        assert "a1b2c3d4" in nodes

    def test_delete_nonexistent_node(self, temp_tftp_root):
        """Deleting nonexistent node should not raise error."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        # Should not raise
        manager.delete_node_directory("nonexistent")

    def test_config_txt_contains_dtb(self, temp_tftp_root):
        """Config.txt should reference the device tree blob."""
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

        # Pi4 uses bcm2711 DTB
        assert "device_tree=bcm2711-rpi-4-b.dtb" in config

    def test_initramfs_in_config(self, temp_tftp_root):
        """Config.txt should include initramfs."""
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

        assert "initramfs initramfs.img followkernel" in config


class TestGenerateCmdlineForState:
    """Tests for generate_cmdline_for_state() method."""

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

    def test_base_params_always_present(self, temp_tftp_root):
        """Base parameters are always included in cmdline."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="discovered",
        )

        # Base params
        assert "console=serial0,115200" in cmdline
        assert "console=tty1" in cmdline
        assert "ip=dhcp" in cmdline
        assert "pureboot.serial=d83add36" in cmdline
        assert "pureboot.state=discovered" in cmdline
        # Ends with quiet loglevel=4 and newline
        assert cmdline.endswith("quiet loglevel=4\n")

    def test_controller_url_added_when_provided(self, temp_tftp_root):
        """Controller URL is added when provided."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="discovered",
            controller_url="http://192.168.1.100:8080",
        )

        assert "pureboot.url=http://192.168.1.100:8080" in cmdline

    def test_controller_url_not_added_when_none(self, temp_tftp_root):
        """Controller URL is not added when not provided."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="discovered",
        )

        assert "pureboot.url=" not in cmdline

    def test_installing_state_with_install_params(self, temp_tftp_root):
        """Installing state adds install mode parameters."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="installing",
            image_url="http://pureboot.local/images/ubuntu.img",
            target_device="/dev/mmcblk0",
            node_id="node-123",
            mac="dc:a6:32:aa:bb:cc",
            callback_url="http://pureboot.local/api/v1/nodes/node-123/callback",
        )

        assert "pureboot.mode=install" in cmdline
        assert "pureboot.image_url=http://pureboot.local/images/ubuntu.img" in cmdline
        assert "pureboot.target=/dev/mmcblk0" in cmdline
        assert "pureboot.node_id=node-123" in cmdline
        assert "pureboot.mac=dc:a6:32:aa:bb:cc" in cmdline
        assert "pureboot.callback=http://pureboot.local/api/v1/nodes/node-123/callback" in cmdline
        assert "root=/dev/ram0" in cmdline
        assert "rootfstype=ramfs" in cmdline

    def test_installing_state_without_image_url(self, temp_tftp_root):
        """Installing state without image_url uses default root."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="installing",
        )

        # Without image_url, should not have install mode params
        assert "pureboot.mode=install" not in cmdline
        # Should have default root
        assert "root=/dev/ram0" in cmdline
        assert "rootfstype=ramfs" in cmdline

    def test_nfs_boot_parameters(self, temp_tftp_root):
        """NFS boot parameters are added when nfs_server and nfs_path provided."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="active",
            nfs_server="192.168.1.10",
            nfs_path="/exports/pi/d83add36",
        )

        assert "root=/dev/nfs" in cmdline
        assert "nfsroot=192.168.1.10:/exports/pi/d83add36,vers=4,tcp" in cmdline
        assert "rw" in cmdline
        # Should NOT have ram0 root when using NFS
        assert "root=/dev/ram0" not in cmdline

    def test_nfs_requires_both_server_and_path(self, temp_tftp_root):
        """NFS boot only enabled when both server and path provided."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        # Only server, no path
        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="active",
            nfs_server="192.168.1.10",
        )
        assert "root=/dev/nfs" not in cmdline
        assert "root=/dev/ram0" in cmdline

        # Only path, no server
        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="active",
            nfs_path="/exports/pi/d83add36",
        )
        assert "root=/dev/nfs" not in cmdline
        assert "root=/dev/ram0" in cmdline

    def test_cmdline_is_single_line(self, temp_tftp_root):
        """Cmdline is a single line ending with newline."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        cmdline = manager.generate_cmdline_for_state(
            serial="d83add36",
            state="installing",
            image_url="http://pureboot.local/images/ubuntu.img",
            controller_url="http://pureboot.local:8080",
        )

        # Single line with newline at end
        lines = cmdline.split("\n")
        assert len(lines) == 2  # Content + empty string after final newline
        assert lines[1] == ""

    def test_invalid_serial_raises_error(self, temp_tftp_root):
        """Invalid serial number raises ValueError."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        with pytest.raises(ValueError, match="Invalid serial"):
            manager.generate_cmdline_for_state(
                serial="invalid",
                state="discovered",
            )


class TestPi3Support:
    """Tests for Raspberry Pi 3 specific support."""

    @pytest.fixture
    def temp_tftp_root_pi3(self):
        """Create temporary TFTP root directory with Pi 3 firmware files."""
        root = Path(tempfile.mkdtemp())
        # Create firmware directory with Pi 3 specific files
        firmware_dir = root / "rpi-firmware"
        firmware_dir.mkdir(parents=True)
        # Pi 3 requires bootcode.bin (Pi 4/5 have it in EEPROM)
        (firmware_dir / "bootcode.bin").touch()
        (firmware_dir / "start.elf").touch()
        (firmware_dir / "fixup.dat").touch()
        # Pi 3B DTB
        (firmware_dir / "bcm2710-rpi-3-b.dtb").touch()
        # Pi 3B+ DTB
        (firmware_dir / "bcm2710-rpi-3-b-plus.dtb").touch()
        # CM3 DTB
        (firmware_dir / "bcm2710-rpi-cm3.dtb").touch()
        # Also add Pi 4/5 firmware for comparison tests
        (firmware_dir / "start4.elf").touch()
        (firmware_dir / "fixup4.dat").touch()
        (firmware_dir / "bcm2711-rpi-4-b.dtb").touch()
        (firmware_dir / "bcm2712-rpi-5-b.dtb").touch()

        # Create deploy directory
        deploy_dir = root / "deploy-arm64"
        deploy_dir.mkdir(parents=True)
        (deploy_dir / "kernel8.img").touch()
        (deploy_dir / "initramfs.img").touch()

        # Create nodes directory
        (root / "pi-nodes").mkdir(parents=True)

        yield root
        shutil.rmtree(root)

    def test_pi3_requires_bootcode_bin(self, temp_tftp_root_pi3):
        """Pi 3 node directory must include bootcode.bin symlink."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root_pi3 / "rpi-firmware",
            deploy_dir=temp_tftp_root_pi3 / "deploy-arm64",
            nodes_dir=temp_tftp_root_pi3 / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="pi3")

        # Pi 3 MUST have bootcode.bin (unlike Pi 4/5)
        bootcode_link = node_dir / "bootcode.bin"
        assert bootcode_link.exists(), "Pi 3 requires bootcode.bin"
        assert bootcode_link.is_symlink()
        assert bootcode_link.resolve() == (temp_tftp_root_pi3 / "rpi-firmware" / "bootcode.bin").resolve()

    def test_pi3_uses_start_elf_not_start4(self, temp_tftp_root_pi3):
        """Pi 3 uses start.elf, not start4.elf."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root_pi3 / "rpi-firmware",
            deploy_dir=temp_tftp_root_pi3 / "deploy-arm64",
            nodes_dir=temp_tftp_root_pi3 / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="pi3")

        # Pi 3 uses start.elf (not start4.elf)
        start_link = node_dir / "start.elf"
        assert start_link.exists(), "Pi 3 should have start.elf"
        assert start_link.is_symlink()

        # Pi 3 should NOT have start4.elf
        start4_link = node_dir / "start4.elf"
        assert not start4_link.exists(), "Pi 3 should not have start4.elf"

    def test_pi3_config_uses_correct_dtb(self, temp_tftp_root_pi3):
        """Pi 3 config.txt references bcm2710-rpi-3-b.dtb."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root_pi3 / "rpi-firmware",
            deploy_dir=temp_tftp_root_pi3 / "deploy-arm64",
            nodes_dir=temp_tftp_root_pi3 / "pi-nodes",
        )

        config = manager.generate_config_txt(
            serial="d83add36",
            pi_model="pi3",
        )

        assert "device_tree=bcm2710-rpi-3-b.dtb" in config

    def test_pi3bplus_uses_correct_dtb(self, temp_tftp_root_pi3):
        """Pi 3B+ config.txt references bcm2710-rpi-3-b-plus.dtb."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root_pi3 / "rpi-firmware",
            deploy_dir=temp_tftp_root_pi3 / "deploy-arm64",
            nodes_dir=temp_tftp_root_pi3 / "pi-nodes",
        )

        config = manager.generate_config_txt(
            serial="d83add36",
            pi_model="pi3b+",
        )

        assert "device_tree=bcm2710-rpi-3-b-plus.dtb" in config

    def test_pi3bplus_has_bootcode_bin(self, temp_tftp_root_pi3):
        """Pi 3B+ also requires bootcode.bin from TFTP."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root_pi3 / "rpi-firmware",
            deploy_dir=temp_tftp_root_pi3 / "deploy-arm64",
            nodes_dir=temp_tftp_root_pi3 / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="pi3b+")

        bootcode_link = node_dir / "bootcode.bin"
        assert bootcode_link.exists(), "Pi 3B+ requires bootcode.bin"
        assert bootcode_link.is_symlink()

    def test_cm3_support(self, temp_tftp_root_pi3):
        """Compute Module 3 is supported."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root_pi3 / "rpi-firmware",
            deploy_dir=temp_tftp_root_pi3 / "deploy-arm64",
            nodes_dir=temp_tftp_root_pi3 / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="cm3")

        # CM3 should have bootcode.bin
        assert (node_dir / "bootcode.bin").exists()
        # CM3 should have correct DTB referenced in config
        config = manager.generate_config_txt(serial, pi_model="cm3")
        assert "device_tree=bcm2710-rpi-cm3.dtb" in config

    def test_pi4_does_not_need_bootcode_bin(self, temp_tftp_root_pi3):
        """Pi 4 does not need bootcode.bin (has it in EEPROM)."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root_pi3 / "rpi-firmware",
            deploy_dir=temp_tftp_root_pi3 / "deploy-arm64",
            nodes_dir=temp_tftp_root_pi3 / "pi-nodes",
        )

        serial = "d83add36"
        node_dir = manager.create_node_directory(serial, pi_model="pi4")

        # Pi 4 should NOT have bootcode.bin (it's in EEPROM)
        bootcode_link = node_dir / "bootcode.bin"
        assert not bootcode_link.exists(), "Pi 4 should not need bootcode.bin"

        # Pi 4 should have start4.elf instead
        assert (node_dir / "start4.elf").exists()

    def test_pi3_model_config_has_requires_otp_flag(self, temp_tftp_root_pi3):
        """Pi 3 model config includes requires_otp flag."""
        from src.pxe.pi_manager import PI_MODELS

        # Pi 3B requires OTP programming for network boot
        assert PI_MODELS["pi3"]["requires_otp"] is True

        # Pi 3B+ has network boot enabled by default
        assert PI_MODELS["pi3b+"]["requires_otp"] is False

        # Pi 4/5 don't need OTP (bootcode in EEPROM)
        assert PI_MODELS["pi4"]["requires_otp"] is False
        assert PI_MODELS["pi5"]["requires_otp"] is False

    def test_all_pi3_models_use_same_firmware(self, temp_tftp_root_pi3):
        """All Pi 3 variants use the same firmware files."""
        from src.pxe.pi_manager import PI_MODELS

        pi3_firmware = ["bootcode.bin", "start.elf", "fixup.dat"]

        assert PI_MODELS["pi3"]["firmware_files"] == pi3_firmware
        assert PI_MODELS["pi3b+"]["firmware_files"] == pi3_firmware
        assert PI_MODELS["cm3"]["firmware_files"] == pi3_firmware


class TestUpdateCmdlineForState:
    """Tests for update_cmdline_for_state() method."""

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

    def test_update_cmdline_for_state_writes_file(self, temp_tftp_root):
        """update_cmdline_for_state writes cmdline.txt to node directory."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        # Create node directory first
        manager.create_node_directory(serial, pi_model="pi4")

        # Update cmdline for state
        manager.update_cmdline_for_state(
            serial=serial,
            state="installing",
            image_url="http://pureboot.local/images/ubuntu.img",
        )

        cmdline_path = temp_tftp_root / "pi-nodes" / serial / "cmdline.txt"
        assert cmdline_path.exists()
        content = cmdline_path.read_text()
        assert "pureboot.state=installing" in content
        assert "pureboot.mode=install" in content

    def test_update_cmdline_for_state_node_not_found(self, temp_tftp_root):
        """update_cmdline_for_state raises FileNotFoundError for missing node."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        with pytest.raises(FileNotFoundError, match="Node directory not found"):
            manager.update_cmdline_for_state(
                serial="d83add36",
                state="installing",
            )

    def test_update_cmdline_for_state_invalid_serial(self, temp_tftp_root):
        """update_cmdline_for_state raises ValueError for invalid serial."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        with pytest.raises(ValueError, match="Invalid serial"):
            manager.update_cmdline_for_state(
                serial="not-valid",
                state="installing",
            )

    def test_update_cmdline_for_state_with_nfs(self, temp_tftp_root):
        """update_cmdline_for_state with NFS parameters."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        manager.create_node_directory(serial, pi_model="pi4")

        manager.update_cmdline_for_state(
            serial=serial,
            state="active",
            nfs_server="192.168.1.10",
            nfs_path="/exports/pi/d83add36",
        )

        cmdline_path = temp_tftp_root / "pi-nodes" / serial / "cmdline.txt"
        content = cmdline_path.read_text()
        assert "pureboot.state=active" in content
        assert "root=/dev/nfs" in content
        assert "nfsroot=192.168.1.10:/exports/pi/d83add36,vers=4,tcp" in content

    def test_update_cmdline_for_state_kwargs_passed(self, temp_tftp_root):
        """update_cmdline_for_state passes kwargs to generate method."""
        from src.pxe.pi_manager import PiManager

        manager = PiManager(
            firmware_dir=temp_tftp_root / "rpi-firmware",
            deploy_dir=temp_tftp_root / "deploy-arm64",
            nodes_dir=temp_tftp_root / "pi-nodes",
        )

        serial = "d83add36"
        manager.create_node_directory(serial, pi_model="pi4")

        manager.update_cmdline_for_state(
            serial=serial,
            state="installing",
            controller_url="http://pureboot.local:8080",
            image_url="http://pureboot.local/images/ubuntu.img",
            target_device="/dev/mmcblk0",
            node_id="node-123",
            mac="dc:a6:32:aa:bb:cc",
            callback_url="http://pureboot.local/api/v1/callback",
        )

        cmdline_path = temp_tftp_root / "pi-nodes" / serial / "cmdline.txt"
        content = cmdline_path.read_text()
        assert "pureboot.url=http://pureboot.local:8080" in content
        assert "pureboot.image_url=http://pureboot.local/images/ubuntu.img" in content
        assert "pureboot.target=/dev/mmcblk0" in content
        assert "pureboot.node_id=node-123" in content
        assert "pureboot.mac=dc:a6:32:aa:bb:cc" in content
        assert "pureboot.callback=http://pureboot.local/api/v1/callback" in content
