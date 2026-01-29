"""Tests for boot script generation."""
import pytest
from unittest.mock import MagicMock

from src.api.routes.boot import (
    generate_local_boot_script,
    generate_discovery_script,
    generate_install_script,
    generate_pending_script,
    generate_pending_no_workflow_script,
    generate_workflow_error_script,
)
from src.core.workflow_service import Workflow


class TestBootScriptGeneration:
    """Test boot script generation functions."""

    def test_local_boot_script(self):
        """Local boot script contains exit command."""
        script = generate_local_boot_script()
        assert "#!ipxe" in script
        assert "exit" in script

    def test_discovery_script_contains_mac(self):
        """Discovery script includes MAC address."""
        script = generate_discovery_script("aa:bb:cc:dd:ee:ff", "http://server:8080")
        assert "#!ipxe" in script
        assert "aa:bb:cc:dd:ee:ff" in script
        assert "registered" in script.lower()

    def test_pending_script_shows_workflow(self):
        """Pending script shows workflow ID if assigned."""
        node = MagicMock()
        node.mac_address = "aa:bb:cc:dd:ee:ff"
        node.workflow_id = "ubuntu-2404"

        script = generate_pending_script(node, "http://server:8080")

        assert "#!ipxe" in script
        assert "aa:bb:cc:dd:ee:ff" in script
        assert "ubuntu-2404" in script
        assert "exit" in script

    def test_install_script_contains_kernel_initrd(self):
        """Install script includes kernel and initrd commands."""
        node = MagicMock()
        node.mac_address = "aa:bb:cc:dd:ee:ff"
        node.id = "test-node-id"

        workflow = Workflow(
            id="ubuntu-2404",
            name="Ubuntu 24.04",
            kernel_path="/ubuntu/vmlinuz",
            initrd_path="/ubuntu/initrd",
            cmdline="ip=dhcp",
        )

        script = generate_install_script(node, workflow, "http://server:8080")

        assert "#!ipxe" in script
        # Kernel/initrd URLs use the /api/v1/files endpoint for serving
        assert "kernel http://server:8080/api/v1/files/ubuntu/vmlinuz" in script
        assert "initrd http://server:8080/api/v1/files/ubuntu/initrd" in script
        assert "ip=dhcp" in script
        assert "boot" in script

    def test_pending_no_workflow_script(self):
        """Pending script without workflow shows message."""
        node = MagicMock()
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        script = generate_pending_no_workflow_script(node, "http://server:8080")

        assert "#!ipxe" in script
        assert "awaiting workflow" in script.lower()
        assert "chain" in script  # Uses chain to poll for workflow

    def test_workflow_error_script(self):
        """Workflow error script shows error message."""
        node = MagicMock()
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        script = generate_workflow_error_script(node, "missing-workflow")

        assert "#!ipxe" in script
        assert "missing-workflow" in script
        assert "ERROR" in script
        assert "not found" in script.lower()
