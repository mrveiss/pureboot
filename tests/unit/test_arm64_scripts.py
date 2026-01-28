"""Unit tests for ARM64 deploy scripts.

These tests verify the shell scripts have correct structure and
expected functions without requiring ARM64 hardware.
"""
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).parent.parent.parent / "deploy"
SCRIPTS_DIR = DEPLOY_DIR / "scripts"


class TestARM64ScriptExistence:
    """Verify all required ARM64 scripts exist."""

    def test_build_script_exists(self):
        """Test ARM64 build script exists."""
        script = DEPLOY_DIR / "build-arm64-deploy-image.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_common_arm64_exists(self):
        """Test ARM64 common functions script exists."""
        script = SCRIPTS_DIR / "pureboot-common-arm64.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_pi_deploy_exists(self):
        """Test Pi deploy dispatcher exists."""
        script = SCRIPTS_DIR / "pureboot-pi-deploy.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_pi_image_exists(self):
        """Test Pi image deployment script exists."""
        script = SCRIPTS_DIR / "pureboot-pi-image.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_pi_nfs_exists(self):
        """Test Pi NFS boot script exists."""
        script = SCRIPTS_DIR / "pureboot-pi-nfs.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_arm64_init_exists(self):
        """Test ARM64 init script exists."""
        script = DEPLOY_DIR / "arm64-init.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"


class TestARM64ScriptSyntax:
    """Verify shell scripts have valid syntax."""

    @pytest.mark.parametrize("script_name", [
        "build-arm64-deploy-image.sh",
    ])
    def test_build_script_syntax(self, script_name):
        """Test build script has valid bash syntax."""
        script = DEPLOY_DIR / script_name
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in {script_name}: {result.stderr}"

    @pytest.mark.parametrize("script_name", [
        "pureboot-common-arm64.sh",
        "pureboot-pi-deploy.sh",
        "pureboot-pi-image.sh",
        "pureboot-pi-nfs.sh",
    ])
    def test_scripts_syntax(self, script_name):
        """Test deploy scripts have valid bash syntax."""
        script = SCRIPTS_DIR / script_name
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in {script_name}: {result.stderr}"

    def test_init_script_syntax(self):
        """Test init script has valid sh syntax."""
        script = DEPLOY_DIR / "arm64-init.sh"
        result = subprocess.run(
            ["sh", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in arm64-init.sh: {result.stderr}"


class TestARM64ScriptContent:
    """Verify scripts contain expected content."""

    def test_common_arm64_has_pi_functions(self):
        """Test ARM64 common script has Pi-specific functions."""
        script = SCRIPTS_DIR / "pureboot-common-arm64.sh"
        content = script.read_text()

        expected_functions = [
            "get_pi_serial",
            "get_pi_model",
            "get_pi_mac",
            "get_pi_boot_device",
            "pi_network_up",
            "register_pi",
            "get_boot_instructions",
            "parse_pi_cmdline",
        ]

        for func in expected_functions:
            assert func in content, f"Missing function: {func}"

    def test_pi_image_has_deploy_functions(self):
        """Test Pi image script has deployment functions."""
        script = SCRIPTS_DIR / "pureboot-pi-image.sh"
        content = script.read_text()

        expected = [
            "deploy_pi_image",
            "resize_pi_partitions",
            "notify_pi_complete",
            "PUREBOOT_IMAGE_URL",
            "PUREBOOT_TARGET",
        ]

        for item in expected:
            assert item in content, f"Missing: {item}"

    def test_pi_deploy_has_dispatcher(self):
        """Test Pi deploy script dispatches to correct scripts."""
        script = SCRIPTS_DIR / "pureboot-pi-deploy.sh"
        content = script.read_text()

        expected = [
            "deploy_image",
            "nfs_boot",
            "local_boot",
            "pureboot-pi-image.sh",
            "pureboot-pi-nfs.sh",
            "get_boot_instructions",
        ]

        for item in expected:
            assert item in content, f"Missing: {item}"

    def test_build_script_uses_aarch64(self):
        """Test build script targets aarch64 architecture."""
        script = DEPLOY_DIR / "build-arm64-deploy-image.sh"
        content = script.read_text()

        assert 'ALPINE_ARCH="aarch64"' in content
        assert "initramfs-arm64.img" in content
