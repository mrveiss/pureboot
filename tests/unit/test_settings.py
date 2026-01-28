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


class TestAgentSettings:
    """Test site agent settings."""

    def test_agent_settings_defaults(self):
        """Agent settings have sensible defaults."""
        from src.config.settings import AgentSettings

        agent = AgentSettings()
        assert agent.mode == "controller"
        assert agent.site_id is None
        assert agent.central_url is None
        assert agent.heartbeat_interval == 60
        assert agent.data_dir == Path("/var/lib/pureboot-agent")

    def test_agent_mode_controller_default(self):
        """Default mode is controller."""
        from src.config.settings import AgentSettings

        agent = AgentSettings()
        assert agent.mode == "controller"

    def test_agent_mode_agent(self):
        """Can set mode to agent."""
        from src.config.settings import AgentSettings

        agent = AgentSettings(mode="agent", site_id="site-123", central_url="https://central.local")
        assert agent.mode == "agent"
        assert agent.site_id == "site-123"
        assert agent.central_url == "https://central.local"

    def test_agent_settings_in_main_settings(self):
        """Agent settings accessible from main settings."""
        from src.config.settings import Settings

        settings = Settings()
        assert hasattr(settings, 'agent')
        assert settings.agent.mode == "controller"

    def test_is_agent_mode_property(self):
        """is_agent_mode property works correctly."""
        from src.config.settings import Settings

        # Default is controller mode
        settings = Settings()
        assert settings.is_agent_mode is False
        assert settings.is_controller_mode is True

    def test_agent_cache_settings(self):
        """Agent cache settings have defaults."""
        from src.config.settings import AgentSettings

        agent = AgentSettings()
        assert agent.cache_dir == Path("/var/lib/pureboot-agent/cache")
        assert agent.cache_max_size_gb == 50

    def test_agent_retry_settings(self):
        """Agent retry settings have defaults."""
        from src.config.settings import AgentSettings

        agent = AgentSettings()
        assert agent.retry_max_attempts == 3
        assert agent.retry_backoff_seconds == 5

    def test_agent_registration_token(self):
        """Agent registration token can be set."""
        from src.config.settings import AgentSettings

        agent = AgentSettings(registration_token="secret-token-123")
        assert agent.registration_token == "secret-token-123"

    def test_agent_registered_flag(self):
        """Agent registered flag defaults to False."""
        from src.config.settings import AgentSettings

        agent = AgentSettings()
        assert agent.registered is False
