"""Unit tests for NFSManager."""
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

    def test_init_with_string_path(self, tmp_path):
        """Test initialization with string path instead of Path object."""
        manager = NFSManager(str(tmp_path))
        assert manager.nfs_root == tmp_path


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
        ("abcdef12", True),  # Lowercase ok
        ("", False),
        ("d83add3", False),  # Too short
        ("d83add367", False),  # Too long
        ("d83addgg", False),  # Invalid hex
        ("d83add3!", False),  # Invalid character
        (None, False),  # None value
    ])
    def test_validate_serial(self, manager, serial, expected):
        """Test serial number validation."""
        if serial is None:
            assert manager.validate_serial("") is False
        else:
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

    def test_ensure_directories_idempotent(self, manager):
        """Test that ensure_directories can be called multiple times."""
        manager.ensure_directories()
        manager.ensure_directories()
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
        with pytest.raises(ValueError, match="Invalid serial number"):
            manager.get_node_path("invalid")

    def test_get_node_path_too_short(self, manager):
        """Test that too-short serial raises ValueError."""
        with pytest.raises(ValueError, match="Invalid serial number"):
            manager.get_node_path("d83add")


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
        (base / "sbin").mkdir()
        return m

    def test_create_node_overlay(self, manager):
        """Test creating a node overlay."""
        merged = manager.create_node_overlay("d83add36", "ubuntu-arm64")

        node_path = manager.nodes_path / "d83add36"
        assert (node_path / "upper").exists()
        assert (node_path / "work").exists()
        assert merged.exists()
        assert merged == node_path / "merged"

    def test_create_node_overlay_with_uppercase_serial(self, manager):
        """Test that uppercase serial is normalized."""
        merged = manager.create_node_overlay("D83ADD36", "ubuntu-arm64")
        assert merged == manager.nodes_path / "d83add36" / "merged"

    def test_create_node_overlay_sets_hostname(self, manager):
        """Test that overlay sets custom hostname."""
        manager.create_node_overlay("d83add36", "ubuntu-arm64", hostname="test-pi")

        hostname_file = manager.nodes_path / "d83add36" / "upper" / "etc" / "hostname"
        assert hostname_file.exists()
        assert hostname_file.read_text().strip() == "test-pi"

    def test_create_node_overlay_default_hostname(self, manager):
        """Test that overlay sets default hostname based on serial."""
        manager.create_node_overlay("d83add36", "ubuntu-arm64")

        hostname_file = manager.nodes_path / "d83add36" / "upper" / "etc" / "hostname"
        assert hostname_file.read_text().strip() == "pi-d83add36"

    def test_create_node_overlay_generates_machine_id(self, manager):
        """Test that overlay generates machine-id."""
        manager.create_node_overlay("d83add36", "ubuntu-arm64")

        machine_id = manager.nodes_path / "d83add36" / "upper" / "etc" / "machine-id"
        assert machine_id.exists()
        content = machine_id.read_text().strip()
        assert len(content) == 32
        # Verify it's valid hex
        int(content, 16)

    def test_create_node_overlay_unique_machine_ids(self, manager):
        """Test that each node gets unique machine-id."""
        manager.create_node_overlay("d83add36", "ubuntu-arm64")
        manager.create_node_overlay("d83add37", "ubuntu-arm64")

        id1 = (manager.nodes_path / "d83add36" / "upper" / "etc" / "machine-id").read_text()
        id2 = (manager.nodes_path / "d83add37" / "upper" / "etc" / "machine-id").read_text()
        assert id1 != id2

    def test_create_node_overlay_invalid_base(self, manager):
        """Test that invalid base image raises ValueError."""
        with pytest.raises(ValueError, match="Base image not found"):
            manager.create_node_overlay("d83add36", "nonexistent")

    def test_create_node_overlay_invalid_serial(self, manager):
        """Test that invalid serial raises ValueError."""
        with pytest.raises(ValueError, match="Invalid serial number"):
            manager.create_node_overlay("invalid", "ubuntu-arm64")

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

    def test_delete_overlay_invalid_serial(self, manager):
        """Test delete with invalid serial returns False."""
        result = manager.delete_node_overlay("invalid")
        assert result is False

    def test_node_overlay_exists(self, manager):
        """Test checking if overlay exists."""
        assert manager.node_overlay_exists("d83add36") is False

        manager.create_node_overlay("d83add36", "ubuntu-arm64")
        assert manager.node_overlay_exists("d83add36") is True

        manager.delete_node_overlay("d83add36")
        assert manager.node_overlay_exists("d83add36") is False

    def test_node_overlay_exists_invalid_serial(self, manager):
        """Test exists check with invalid serial returns False."""
        assert manager.node_overlay_exists("invalid") is False


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
        assert len(images) == 2

    def test_get_base_images_empty(self, tmp_path):
        """Test listing base images when none exist."""
        manager = NFSManager(tmp_path)
        manager.ensure_directories()
        images = manager.get_base_images()
        assert images == []

    def test_get_base_images_no_directory(self, tmp_path):
        """Test listing when base directory doesn't exist."""
        manager = NFSManager(tmp_path)
        # Don't call ensure_directories
        images = manager.get_base_images()
        assert images == []

    def test_get_node_info_exists(self, manager):
        """Test getting info for existing node."""
        # Create base image structure for overlay creation
        base = manager.base_path / "ubuntu-arm64"
        (base / "bin").mkdir(exist_ok=True)

        manager.create_node_overlay("d83add36", "ubuntu-arm64", hostname="my-pi")

        info = manager.get_node_info("d83add36")
        assert info is not None
        assert info["serial"] == "d83add36"
        assert info["hostname"] == "my-pi"
        assert "path" in info
        assert "upper_dir" in info
        assert "merged_dir" in info

    def test_get_node_info_not_found(self, manager):
        """Test getting info for nonexistent node."""
        info = manager.get_node_info("00000000")
        assert info is None

    def test_get_node_info_invalid_serial(self, manager):
        """Test getting info with invalid serial."""
        info = manager.get_node_info("invalid")
        assert info is None


class TestNFSManagerMountOptions:
    """Test mount options generation."""

    @pytest.fixture
    def manager(self, tmp_path):
        m = NFSManager(tmp_path)
        m.ensure_directories()
        (m.base_path / "ubuntu-arm64").mkdir()
        return m

    def test_get_overlay_mount_options(self, manager):
        """Test generating overlay mount options."""
        options = manager.get_overlay_mount_options("d83add36", "ubuntu-arm64")

        assert "lowerdir=" in options
        assert "upperdir=" in options
        assert "workdir=" in options
        assert "ubuntu-arm64" in options
        assert "d83add36" in options

    def test_get_overlay_mount_options_invalid_serial(self, manager):
        """Test mount options with invalid serial."""
        with pytest.raises(ValueError, match="Invalid serial number"):
            manager.get_overlay_mount_options("invalid", "ubuntu-arm64")
