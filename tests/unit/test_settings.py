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

    def test_pi_settings_deploy_dir(self):
        """Pi deploy directory has correct default."""
        from src.config.settings import PiSettings

        pi = PiSettings()
        assert pi.deploy_dir == Path("./tftp/deploy-arm64")

    def test_pi_settings_nodes_dir(self):
        """Pi nodes directory has correct default."""
        from src.config.settings import PiSettings

        pi = PiSettings()
        assert pi.nodes_dir == Path("./tftp/pi-nodes")
