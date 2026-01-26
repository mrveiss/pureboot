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
