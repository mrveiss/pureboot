"""Integration tests for workflow API."""
import pytest


class TestWorkflowCRUD:
    """Test workflow CRUD endpoints."""

    def test_create_workflow(self, client, test_db):
        """POST /workflows creates a new workflow."""
        response = client.post("/api/v1/workflows", json={
            "name": "ubuntu-2404",
            "description": "Ubuntu 24.04 Server",
            "os_family": "linux",
            "architecture": "x86_64",
            "boot_mode": "uefi",
            "steps": [
                {"sequence": 1, "name": "PXE Boot", "type": "boot", "config": {"kernel": "/vmlinuz"}},
                {"sequence": 2, "name": "Reboot", "type": "reboot", "next_state": "installed"},
            ],
        })

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "ubuntu-2404"
        assert data["description"] == "Ubuntu 24.04 Server"
        assert data["os_family"] == "linux"
        assert data["architecture"] == "x86_64"
        assert data["boot_mode"] == "uefi"
        assert data["is_active"] is True
        assert len(data["steps"]) == 2
        assert data["steps"][0]["name"] == "PXE Boot"
        assert data["steps"][0]["config"] == {"kernel": "/vmlinuz"}
        assert data["steps"][1]["next_state"] == "installed"

    def test_create_workflow_minimal(self, client, test_db):
        """POST /workflows with minimal data creates workflow with defaults."""
        response = client.post("/api/v1/workflows", json={
            "name": "minimal-workflow",
            "os_family": "linux",
            "steps": [],
        })

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "minimal-workflow"
        assert data["description"] == ""
        assert data["architecture"] == "x86_64"
        assert data["boot_mode"] == "bios"
        assert data["steps"] == []

    def test_create_workflow_duplicate_name(self, client, test_db):
        """POST /workflows with duplicate name returns 409."""
        client.post("/api/v1/workflows", json={
            "name": "dup",
            "os_family": "linux",
            "steps": [],
        })
        response = client.post("/api/v1/workflows", json={
            "name": "dup",
            "os_family": "linux",
            "steps": [],
        })
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_workflow_invalid_name(self, client, test_db):
        """POST /workflows with missing name returns 422."""
        response = client.post("/api/v1/workflows", json={
            "os_family": "linux",
            "steps": [],
        })
        assert response.status_code == 422

    def test_list_workflows(self, client, test_db):
        """GET /workflows returns all active workflows."""
        client.post("/api/v1/workflows", json={
            "name": "wf-1",
            "os_family": "linux",
            "steps": [],
        })
        client.post("/api/v1/workflows", json={
            "name": "wf-2",
            "os_family": "windows",
            "steps": [],
        })

        response = client.get("/api/v1/workflows")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["data"]) == 2

    def test_list_workflows_filter_os_family(self, client, test_db):
        """GET /workflows?os_family=linux filters by OS family."""
        client.post("/api/v1/workflows", json={
            "name": "linux-wf",
            "os_family": "linux",
            "steps": [],
        })
        client.post("/api/v1/workflows", json={
            "name": "windows-wf",
            "os_family": "windows",
            "steps": [],
        })

        response = client.get("/api/v1/workflows?os_family=linux")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["data"][0]["os_family"] == "linux"

    def test_list_workflows_filter_architecture(self, client, test_db):
        """GET /workflows?architecture=aarch64 filters by architecture."""
        client.post("/api/v1/workflows", json={
            "name": "arm-wf",
            "os_family": "linux",
            "architecture": "aarch64",
            "steps": [],
        })
        client.post("/api/v1/workflows", json={
            "name": "x86-wf",
            "os_family": "linux",
            "architecture": "x86_64",
            "steps": [],
        })

        response = client.get("/api/v1/workflows?architecture=aarch64")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["data"][0]["architecture"] == "aarch64"

    def test_list_workflows_excludes_inactive(self, client, test_db):
        """GET /workflows does not return soft-deleted workflows."""
        from src.db.models import Workflow

        workflow = Workflow(name="inactive-wf", os_family="linux", is_active=False)
        test_db.add(workflow)
        test_db.flush()

        response = client.get("/api/v1/workflows")

        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_get_workflow(self, client, test_db):
        """GET /workflows/{id} returns workflow with steps."""
        create_resp = client.post("/api/v1/workflows", json={
            "name": "test-wf",
            "os_family": "linux",
            "steps": [
                {"sequence": 1, "name": "Boot", "type": "boot", "config": {"kernel": "/vmlinuz"}},
            ],
        })
        workflow_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/workflows/{workflow_id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "test-wf"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["type"] == "boot"

    def test_get_workflow_not_found(self, client, test_db):
        """GET /workflows/{id} returns 404 for missing workflow."""
        response = client.get("/api/v1/workflows/nonexistent-id")
        assert response.status_code == 404

    def test_get_workflow_inactive(self, client, test_db):
        """GET /workflows/{id} returns 404 for inactive workflow."""
        from src.db.models import Workflow

        workflow = Workflow(name="inactive-wf", os_family="linux", is_active=False)
        test_db.add(workflow)
        test_db.flush()

        response = client.get(f"/api/v1/workflows/{workflow.id}")
        assert response.status_code == 404

    def test_update_workflow(self, client, test_db):
        """PUT /workflows/{id} updates workflow."""
        create_resp = client.post("/api/v1/workflows", json={
            "name": "test",
            "os_family": "linux",
            "steps": [],
        })
        workflow_id = create_resp.json()["data"]["id"]

        response = client.put(f"/api/v1/workflows/{workflow_id}", json={
            "name": "updated",
            "description": "Updated description",
            "os_family": "linux",
            "steps": [
                {"sequence": 1, "name": "New Step", "type": "boot", "config": {}},
            ],
        })

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "updated"
        assert data["description"] == "Updated description"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["name"] == "New Step"

    def test_update_workflow_not_found(self, client, test_db):
        """PUT /workflows/{id} returns 404 for missing workflow."""
        response = client.put("/api/v1/workflows/nonexistent-id", json={
            "name": "updated",
            "os_family": "linux",
            "steps": [],
        })
        assert response.status_code == 404

    def test_update_workflow_duplicate_name(self, client, test_db):
        """PUT /workflows/{id} with duplicate name returns 409."""
        client.post("/api/v1/workflows", json={
            "name": "existing",
            "os_family": "linux",
            "steps": [],
        })
        create_resp = client.post("/api/v1/workflows", json={
            "name": "test",
            "os_family": "linux",
            "steps": [],
        })
        workflow_id = create_resp.json()["data"]["id"]

        response = client.put(f"/api/v1/workflows/{workflow_id}", json={
            "name": "existing",
            "os_family": "linux",
            "steps": [],
        })

        assert response.status_code == 409

    def test_delete_workflow(self, client, test_db):
        """DELETE /workflows/{id} soft deletes workflow."""
        create_resp = client.post("/api/v1/workflows", json={
            "name": "test",
            "os_family": "linux",
            "steps": [],
        })
        workflow_id = create_resp.json()["data"]["id"]

        response = client.delete(f"/api/v1/workflows/{workflow_id}")

        assert response.status_code == 200
        assert response.json()["message"] == "Workflow deleted"

        # Should not appear in list
        list_resp = client.get("/api/v1/workflows")
        assert list_resp.json()["total"] == 0

        # Direct get should return 404
        get_resp = client.get(f"/api/v1/workflows/{workflow_id}")
        assert get_resp.status_code == 404

    def test_delete_workflow_not_found(self, client, test_db):
        """DELETE /workflows/{id} returns 404 for missing workflow."""
        response = client.delete("/api/v1/workflows/nonexistent-id")
        assert response.status_code == 404

    def test_workflow_step_fields(self, client, test_db):
        """Workflow steps include all expected fields."""
        response = client.post("/api/v1/workflows", json={
            "name": "full-step-test",
            "os_family": "linux",
            "steps": [
                {
                    "sequence": 1,
                    "name": "Boot Step",
                    "type": "boot",
                    "config": {"kernel": "/vmlinuz", "initrd": "/initrd.img"},
                    "timeout_seconds": 1800,
                    "on_failure": "retry",
                    "max_retries": 5,
                    "retry_delay_seconds": 60,
                    "next_state": "installing",
                },
            ],
        })

        assert response.status_code == 201
        step = response.json()["data"]["steps"][0]
        assert step["sequence"] == 1
        assert step["name"] == "Boot Step"
        assert step["type"] == "boot"
        assert step["config"] == {"kernel": "/vmlinuz", "initrd": "/initrd.img"}
        assert step["timeout_seconds"] == 1800
        assert step["on_failure"] == "retry"
        assert step["max_retries"] == 5
        assert step["retry_delay_seconds"] == 60
        assert step["next_state"] == "installing"

    def test_workflow_step_defaults(self, client, test_db):
        """Workflow steps have sensible defaults."""
        response = client.post("/api/v1/workflows", json={
            "name": "default-step-test",
            "os_family": "linux",
            "steps": [
                {
                    "sequence": 1,
                    "name": "Minimal Step",
                    "type": "script",
                },
            ],
        })

        assert response.status_code == 201
        step = response.json()["data"]["steps"][0]
        assert step["config"] is None or step["config"] == {}
        assert step["timeout_seconds"] == 300
        assert step["on_failure"] == "fail"
        assert step["max_retries"] == 0
        assert step["retry_delay_seconds"] == 30
        assert step["next_state"] is None

    def test_create_workflow_invalid_os_family(self, client, test_db):
        """POST /workflows with invalid os_family returns 422."""
        response = client.post("/api/v1/workflows", json={
            "name": "invalid-wf", "os_family": "invalid", "steps": []
        })
        assert response.status_code == 422

    def test_create_workflow_invalid_step_type(self, client, test_db):
        """POST /workflows with invalid step type returns 422."""
        response = client.post("/api/v1/workflows", json={
            "name": "invalid-wf", "os_family": "linux",
            "steps": [{"sequence": 1, "name": "Bad", "type": "invalid"}]
        })
        assert response.status_code == 422

    def test_create_workflow_duplicate_sequences(self, client, test_db):
        """POST /workflows with duplicate sequences returns 400."""
        response = client.post("/api/v1/workflows", json={
            "name": "dup-seq", "os_family": "linux",
            "steps": [
                {"sequence": 1, "name": "Step1", "type": "boot"},
                {"sequence": 1, "name": "Step2", "type": "reboot"},
            ]
        })
        assert response.status_code == 400
        assert "unique" in response.json()["detail"].lower()