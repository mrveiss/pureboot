"""Tests for iPXE script generation."""
import pytest
from src.pxe.ipxe_scripts import IPXEScriptGenerator


class TestIPXEScriptGenerator:
    """Test iPXE script generation."""

    @pytest.fixture
    def generator(self):
        """Create script generator."""
        return IPXEScriptGenerator(
            server_address="192.168.1.10",
            timeout=5,
            show_menu=True,
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
        assert "192.168.1.10" in script

    def test_includes_menu_when_enabled(self, generator):
        """Script includes menu when show_menu=True."""
        script = generator.generate_boot_script()
        assert ":menu" in script
        assert "choose" in script

    def test_excludes_menu_when_disabled(self):
        """Script excludes menu when show_menu=False."""
        generator = IPXEScriptGenerator(
            server_address="192.168.1.10",
            timeout=5,
            show_menu=False
        )
        script = generator.generate_boot_script()
        assert ":menu" not in script

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
