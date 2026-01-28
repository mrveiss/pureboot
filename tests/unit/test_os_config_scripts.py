"""Unit tests for OS configuration scripts."""
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).parent.parent.parent / "deploy"
SCRIPTS_DIR = DEPLOY_DIR / "scripts"


class TestOSConfigScriptExistence:
    """Verify OS configuration scripts exist."""

    def test_cloud_init_script_exists(self):
        """Test cloud-init helper exists."""
        script = SCRIPTS_DIR / "pureboot-cloud-init.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_raspios_config_script_exists(self):
        """Test Raspberry Pi OS helper exists."""
        script = SCRIPTS_DIR / "pureboot-raspios-config.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"


class TestOSConfigScriptSyntax:
    """Verify scripts have valid syntax."""

    @pytest.mark.parametrize("script_name", [
        "pureboot-cloud-init.sh",
        "pureboot-raspios-config.sh",
    ])
    def test_script_syntax(self, script_name):
        """Test script has valid bash syntax."""
        script = SCRIPTS_DIR / script_name
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestOSConfigScriptContent:
    """Verify scripts contain expected functions."""

    def test_cloud_init_has_functions(self):
        """Test cloud-init script has expected functions."""
        script = SCRIPTS_DIR / "pureboot-cloud-init.sh"
        content = script.read_text()

        expected = [
            "configure_cloud_init",
            "create_nocloud_seed",
            "set_target_hostname",
            "enable_ssh",
        ]

        for func in expected:
            assert func in content, f"Missing function: {func}"

    def test_raspios_config_has_functions(self):
        """Test Raspberry Pi OS script has expected functions."""
        script = SCRIPTS_DIR / "pureboot-raspios-config.sh"
        content = script.read_text()

        expected = [
            "configure_raspios",
            "configure_wifi",
            "disable_piwiz",
            "create_userconf",
            "add_ssh_keys",
        ]

        for func in expected:
            assert func in content, f"Missing function: {func}"


class TestPiImageScriptUpdated:
    """Verify Pi image script has OS config integration."""

    def test_pi_image_has_os_config(self):
        """Test Pi image script has OS configuration functions."""
        script = SCRIPTS_DIR / "pureboot-pi-image.sh"
        content = script.read_text()

        expected = [
            "configure_os",
            "run_post_install",
            "run_os_config",
            "find_root_partition",
            "PUREBOOT_POST_SCRIPT",
            "PUREBOOT_HOSTNAME",
        ]

        for item in expected:
            assert item in content, f"Missing: {item}"

    def test_pi_image_sources_helpers(self):
        """Test Pi image script sources helper scripts."""
        script = SCRIPTS_DIR / "pureboot-pi-image.sh"
        content = script.read_text()

        # Should source helpers conditionally
        assert "pureboot-cloud-init.sh" in content
        assert "pureboot-raspios-config.sh" in content


class TestWorkflowsExist:
    """Verify Pi workflows exist."""

    def test_raspios_lite_workflow_exists(self):
        """Test Raspberry Pi OS Lite workflow exists."""
        workflow = DEPLOY_DIR.parent / "workflows" / "pi-raspios-lite.yaml"
        assert workflow.exists(), f"Missing: {workflow}"

    def test_ubuntu_arm64_workflow_exists(self):
        """Test Ubuntu ARM64 workflow exists."""
        workflow = DEPLOY_DIR.parent / "workflows" / "pi-ubuntu-arm64.yaml"
        assert workflow.exists(), f"Missing: {workflow}"

    def test_diskless_nfs_workflow_exists(self):
        """Test NFS diskless workflow exists."""
        workflow = DEPLOY_DIR.parent / "workflows" / "pi-diskless-nfs.yaml"
        assert workflow.exists(), f"Missing: {workflow}"

    def test_k3s_worker_workflow_exists(self):
        """Test K3s worker workflow exists."""
        workflow = DEPLOY_DIR.parent / "workflows" / "pi-k3s-worker.yaml"
        assert workflow.exists(), f"Missing: {workflow}"
