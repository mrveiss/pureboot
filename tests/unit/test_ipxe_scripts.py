"""Tests for iPXE script generation."""
import pytest
from pathlib import Path
from src.pxe.ipxe_scripts import IPXEScriptGenerator, update_tftp_boot_scripts


class TestIPXEScriptGenerator:
    """Test iPXE script generation."""

    @pytest.fixture
    def generator(self):
        """Create script generator."""
        return IPXEScriptGenerator(
            server_address="192.168.1.10:8080",
            timeout=5,
            logo_url="/assets/pureboot-logo.png"
        )

    def test_generates_valid_ipxe_header(self, generator):
        """Script starts with #!ipxe."""
        script = generator.generate_boot_script()
        assert script.startswith("#!ipxe")

    def test_includes_ascii_logo(self, generator):
        """Script includes ASCII logo."""
        script = generator.generate_boot_script()
        assert "PureBoot" in script or "____" in script

    def test_includes_server_address(self, generator):
        """Script includes configured server address."""
        script = generator.generate_boot_script()
        assert "192.168.1.10:8080" in script

    def test_includes_retry_loop(self, generator):
        """Script includes retry logic for server unreachable."""
        script = generator.generate_boot_script()
        assert ":retry" in script
        assert "goto retry" in script

    def test_includes_timeout_value(self, generator):
        """Script includes configured timeout."""
        script = generator.generate_boot_script()
        # 5 seconds = 5000 milliseconds for imgfetch
        assert "5000" in script or "sleep 5" in script

    def test_local_boot_script(self, generator):
        """Local boot script exits iPXE."""
        script = generator.generate_local_boot()
        assert "#!ipxe" in script
        assert "exit" in script

    def test_embedded_script_for_binary(self, generator):
        """Embedded script uses ${next-server} or hardcoded address."""
        script = generator.generate_embedded_script()
        assert "#!ipxe" in script
        assert "chain" in script or "imgfetch" in script


class TestGenerateAutoexecScript:
    """Test autoexec.ipxe script generation."""

    def test_generates_valid_ipxe_header(self):
        """Autoexec script starts with #!ipxe."""
        generator = IPXEScriptGenerator(server_address="192.168.1.10:8080")
        script = generator.generate_autoexec_script()
        assert script.startswith("#!ipxe")

    def test_includes_server_address_comment(self):
        """Autoexec script includes server address in comment."""
        generator = IPXEScriptGenerator(server_address="10.0.0.5:8080")
        script = generator.generate_autoexec_script()
        assert "# Server: 10.0.0.5:8080" in script

    def test_includes_do_not_edit_warning(self):
        """Autoexec script warns against manual editing."""
        generator = IPXEScriptGenerator(server_address="192.168.1.10:8080")
        script = generator.generate_autoexec_script()
        assert "do not edit manually" in script.lower()

    def test_chains_to_http_api(self):
        """Autoexec script chains to HTTP boot API."""
        generator = IPXEScriptGenerator(server_address="192.168.1.10:8080")
        script = generator.generate_autoexec_script()
        assert "chain http://192.168.1.10:8080/api/v1/boot" in script

    def test_includes_mac_address_parameter(self):
        """Autoexec script passes MAC address to boot API."""
        generator = IPXEScriptGenerator(server_address="192.168.1.10:8080")
        script = generator.generate_autoexec_script()
        assert "mac=${net0/mac}" in script

    def test_includes_retry_logic(self):
        """Autoexec script has retry on failure."""
        generator = IPXEScriptGenerator(server_address="192.168.1.10:8080")
        script = generator.generate_autoexec_script()
        assert ":retry" in script
        assert "sleep 5" in script

    def test_displays_network_info(self):
        """Autoexec script displays network information."""
        generator = IPXEScriptGenerator(server_address="192.168.1.10:8080")
        script = generator.generate_autoexec_script()
        assert "${net0/mac}" in script
        assert "${net0/ip}" in script


class TestUpdateTftpBootScripts:
    """Test TFTP boot script update functionality."""

    def test_creates_autoexec_in_tftp_root(self, tmp_path):
        """Creates autoexec.ipxe in TFTP root directory."""
        update_tftp_boot_scripts(tmp_path, "192.168.1.10:8080")

        autoexec_path = tmp_path / "autoexec.ipxe"
        assert autoexec_path.exists()
        content = autoexec_path.read_text()
        assert "#!ipxe" in content
        assert "192.168.1.10:8080" in content

    def test_creates_uefi_boot_script(self, tmp_path):
        """Creates boot.ipxe in uefi subdirectory."""
        (tmp_path / "uefi").mkdir()
        update_tftp_boot_scripts(tmp_path, "192.168.1.10:8080")

        uefi_path = tmp_path / "uefi" / "boot.ipxe"
        assert uefi_path.exists()
        content = uefi_path.read_text()
        assert "#!ipxe" in content
        assert "192.168.1.10:8080" in content

    def test_creates_bios_boot_script(self, tmp_path):
        """Creates boot.ipxe in bios subdirectory."""
        (tmp_path / "bios").mkdir()
        update_tftp_boot_scripts(tmp_path, "192.168.1.10:8080")

        bios_path = tmp_path / "bios" / "boot.ipxe"
        assert bios_path.exists()
        content = bios_path.read_text()
        assert "#!ipxe" in content
        assert "192.168.1.10:8080" in content

    def test_skips_uefi_if_directory_missing(self, tmp_path):
        """Skips uefi/boot.ipxe if uefi directory doesn't exist."""
        update_tftp_boot_scripts(tmp_path, "192.168.1.10:8080")

        uefi_path = tmp_path / "uefi" / "boot.ipxe"
        assert not uefi_path.exists()

    def test_skips_bios_if_directory_missing(self, tmp_path):
        """Skips bios/boot.ipxe if bios directory doesn't exist."""
        update_tftp_boot_scripts(tmp_path, "192.168.1.10:8080")

        bios_path = tmp_path / "bios" / "boot.ipxe"
        assert not bios_path.exists()

    def test_updates_existing_script_with_new_address(self, tmp_path):
        """Updates existing script when server address changes."""
        # Create initial script with old address
        autoexec_path = tmp_path / "autoexec.ipxe"
        autoexec_path.write_text("#!ipxe\n# Server: 10.0.0.1:8080\nold content")

        # Update with new address
        update_tftp_boot_scripts(tmp_path, "192.168.1.10:8080")

        content = autoexec_path.read_text()
        assert "192.168.1.10:8080" in content
        assert "10.0.0.1:8080" not in content

    def test_skips_update_when_content_unchanged(self, tmp_path):
        """Skips write when script content is already correct."""
        # First update
        update_tftp_boot_scripts(tmp_path, "192.168.1.10:8080")
        autoexec_path = tmp_path / "autoexec.ipxe"
        first_mtime = autoexec_path.stat().st_mtime_ns

        # Second update with same address - should skip
        update_tftp_boot_scripts(tmp_path, "192.168.1.10:8080")
        second_mtime = autoexec_path.stat().st_mtime_ns

        assert first_mtime == second_mtime

    def test_includes_server_address_in_all_scripts(self, tmp_path):
        """All generated scripts include the server address."""
        (tmp_path / "uefi").mkdir()
        (tmp_path / "bios").mkdir()
        server_addr = "10.20.30.40:9000"

        update_tftp_boot_scripts(tmp_path, server_addr)

        for script_path in [
            tmp_path / "autoexec.ipxe",
            tmp_path / "uefi" / "boot.ipxe",
            tmp_path / "bios" / "boot.ipxe",
        ]:
            content = script_path.read_text()
            assert server_addr in content, f"{script_path} missing server address"
