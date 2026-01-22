"""Tests for workflow service."""
import json
import pytest
from pathlib import Path

from src.core.workflow_service import WorkflowService, Workflow, WorkflowNotFoundError


class TestWorkflowService:
    """Test WorkflowService."""

    def test_get_workflow_returns_workflow(self, tmp_path: Path):
        """get_workflow returns workflow when file exists."""
        workflow_data = {
            "id": "ubuntu-2404",
            "name": "Ubuntu 24.04 Server",
            "kernel_path": "/files/ubuntu/vmlinuz",
            "initrd_path": "/files/ubuntu/initrd",
            "cmdline": "ip=dhcp",
        }
        workflow_file = tmp_path / "ubuntu-2404.json"
        workflow_file.write_text(json.dumps(workflow_data))

        service = WorkflowService(tmp_path)
        workflow = service.get_workflow("ubuntu-2404")

        assert workflow.id == "ubuntu-2404"
        assert workflow.name == "Ubuntu 24.04 Server"
        assert workflow.kernel_path == "/files/ubuntu/vmlinuz"

    def test_get_workflow_raises_when_not_found(self, tmp_path: Path):
        """get_workflow raises WorkflowNotFoundError when file missing."""
        service = WorkflowService(tmp_path)

        with pytest.raises(WorkflowNotFoundError):
            service.get_workflow("nonexistent")

    def test_list_workflows_returns_all(self, tmp_path: Path):
        """list_workflows returns all workflow files."""
        for i in range(3):
            data = {
                "id": f"workflow-{i}",
                "name": f"Workflow {i}",
                "kernel_path": f"/kernel{i}",
                "initrd_path": f"/initrd{i}",
                "cmdline": "",
            }
            (tmp_path / f"workflow-{i}.json").write_text(json.dumps(data))

        service = WorkflowService(tmp_path)
        workflows = service.list_workflows()

        assert len(workflows) == 3
        assert {w.id for w in workflows} == {"workflow-0", "workflow-1", "workflow-2"}

    def test_list_workflows_empty_dir(self, tmp_path: Path):
        """list_workflows returns empty list for empty directory."""
        service = WorkflowService(tmp_path)
        workflows = service.list_workflows()
        assert workflows == []

    def test_resolve_variables(self, tmp_path: Path):
        """resolve_variables substitutes placeholders."""
        workflow_data = {
            "id": "test",
            "name": "Test",
            "kernel_path": "/files/kernel",
            "initrd_path": "/files/initrd",
            "cmdline": "server=${server} node=${node_id} mac=${mac}",
        }
        (tmp_path / "test.json").write_text(json.dumps(workflow_data))

        service = WorkflowService(tmp_path)
        workflow = service.get_workflow("test")

        resolved = service.resolve_variables(
            workflow,
            server="http://192.168.1.1:8080",
            node_id="abc-123",
            mac="aa:bb:cc:dd:ee:ff",
        )

        assert "server=http://192.168.1.1:8080" in resolved.cmdline
        assert "node=abc-123" in resolved.cmdline
        assert "mac=aa:bb:cc:dd:ee:ff" in resolved.cmdline

    def test_workflow_defaults(self, tmp_path: Path):
        """Workflow has correct defaults for optional fields."""
        workflow_data = {
            "id": "minimal",
            "name": "Minimal",
            "kernel_path": "/kernel",
            "initrd_path": "/initrd",
            "cmdline": "",
        }
        (tmp_path / "minimal.json").write_text(json.dumps(workflow_data))

        service = WorkflowService(tmp_path)
        workflow = service.get_workflow("minimal")

        assert workflow.architecture == "x86_64"
        assert workflow.boot_mode == "bios"

    def test_get_workflow_rejects_path_traversal(self, tmp_path: Path):
        """get_workflow raises ValueError for path traversal attempts."""
        service = WorkflowService(tmp_path)

        with pytest.raises(ValueError, match="Invalid workflow_id"):
            service.get_workflow("../../../etc/passwd")

    def test_get_workflow_rejects_path_traversal_encoded(self, tmp_path: Path):
        """get_workflow raises ValueError for encoded path traversal."""
        service = WorkflowService(tmp_path)

        with pytest.raises(ValueError, match="Invalid workflow_id"):
            service.get_workflow("..%2F..%2Fetc/passwd")

    def test_get_workflow_rejects_absolute_path(self, tmp_path: Path):
        """get_workflow raises ValueError for absolute path injection."""
        service = WorkflowService(tmp_path)

        # This tests attempting to inject an absolute path
        with pytest.raises(ValueError, match="Invalid workflow_id"):
            service.get_workflow("/etc/passwd/../../../tmp/evil")
