"""Tests for agent CLI commands."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import argparse

from src.agent.cli import (
    create_parser,
    cmd_init,
    cmd_status,
)


class TestCreateParser:
    """Tests for CLI argument parser."""

    def test_parser_created(self):
        """Test parser is created with subcommands."""
        parser = create_parser()
        assert parser.prog == "pureboot-agent"

    def test_init_command_requires_args(self):
        """Test init command requires all arguments."""
        parser = create_parser()

        # Missing all required args
        with pytest.raises(SystemExit):
            parser.parse_args(["init"])

    def test_init_command_parses_args(self):
        """Test init command parses arguments correctly."""
        parser = create_parser()
        args = parser.parse_args([
            "init",
            "--site-id", "site-001",
            "--central-url", "http://central:8080",
            "--token", "secret-token",
        ])

        assert args.command == "init"
        assert args.site_id == "site-001"
        assert args.central_url == "http://central:8080"
        assert args.token == "secret-token"

    def test_init_command_optional_args(self):
        """Test init command optional arguments have defaults."""
        parser = create_parser()
        args = parser.parse_args([
            "init",
            "--site-id", "site-001",
            "--central-url", "http://central:8080",
            "--token", "secret-token",
        ])

        assert args.data_dir == "/var/lib/pureboot-agent"
        assert args.cache_size == 50

    def test_start_command(self):
        """Test start command."""
        parser = create_parser()
        args = parser.parse_args(["start"])
        assert args.command == "start"

    def test_status_command(self):
        """Test status command."""
        parser = create_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_sync_command(self):
        """Test sync command."""
        parser = create_parser()
        args = parser.parse_args(["sync"])
        assert args.command == "sync"


class TestCmdInit:
    """Tests for init command."""

    def test_creates_directories(self, tmp_path):
        """Test init creates required directories."""
        args = argparse.Namespace(
            site_id="site-001",
            central_url="http://central:8080",
            token="test-token",
            data_dir=str(tmp_path / "agent"),
            cache_size=10,
        )

        result = cmd_init(args)

        assert result == 0
        assert (tmp_path / "agent").exists()
        assert (tmp_path / "agent" / "cache" / "tftp").exists()
        assert (tmp_path / "agent" / "cache" / "http").exists()

    def test_creates_env_file(self, tmp_path):
        """Test init creates .env configuration file."""
        args = argparse.Namespace(
            site_id="site-001",
            central_url="http://central:8080",
            token="test-token",
            data_dir=str(tmp_path / "agent"),
            cache_size=25,
        )

        result = cmd_init(args)

        assert result == 0
        env_file = tmp_path / "agent" / ".env"
        assert env_file.exists()

        content = env_file.read_text()
        assert "PUREBOOT_AGENT__MODE=agent" in content
        assert "PUREBOOT_AGENT__SITE_ID=site-001" in content
        assert "PUREBOOT_AGENT__CENTRAL_URL=http://central:8080" in content
        assert "PUREBOOT_AGENT__REGISTRATION_TOKEN=test-token" in content
        assert "PUREBOOT_AGENT__CACHE_MAX_SIZE_GB=25" in content

    def test_permission_error(self, tmp_path):
        """Test init handles permission errors."""
        # Use a path that can't be created
        args = argparse.Namespace(
            site_id="site-001",
            central_url="http://central:8080",
            token="test-token",
            data_dir="/root/definitely-not-writable-dir",
            cache_size=10,
        )

        # Mock mkdir to raise PermissionError
        with patch.object(Path, "mkdir", side_effect=PermissionError("Permission denied")):
            result = cmd_init(args)
            assert result == 1


class TestCmdStatus:
    """Tests for status command."""

    @pytest.mark.asyncio
    async def test_status_not_agent_mode(self):
        """Test status when not in agent mode."""
        with patch("src.agent.cli.settings") as mock_settings:
            mock_settings.is_agent_mode = False
            mock_settings.agent.mode = "controller"
            mock_settings.agent.site_id = None
            mock_settings.agent.central_url = None

            args = argparse.Namespace()
            result = cmd_status(args)

            # Should return error when not in agent mode
            assert result == 1

    @pytest.mark.asyncio
    async def test_status_no_central_url(self):
        """Test status when central URL not configured."""
        with patch("src.agent.cli.settings") as mock_settings:
            mock_settings.is_agent_mode = True
            mock_settings.agent.mode = "agent"
            mock_settings.agent.site_id = "site-001"
            mock_settings.agent.central_url = None
            mock_settings.agent.registered = False

            args = argparse.Namespace()
            result = cmd_status(args)

            assert result == 1
