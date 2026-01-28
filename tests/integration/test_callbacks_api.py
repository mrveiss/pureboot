"""Integration tests for callback API."""
import pytest
from datetime import datetime, timezone


class TestCallbackAPI:
    """Test callback endpoints."""

    def _create_execution(self, test_db):
        """Helper to create a workflow execution for testing."""
        from src.db.models import Node, Workflow, WorkflowStep, WorkflowExecution

        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-workflow", os_family="linux")
        test_db.add_all([node, workflow])
        test_db.flush()

        step = WorkflowStep(workflow_id=workflow.id, sequence=1, name="Boot", type="boot")
        test_db.add(step)
        test_db.flush()

        execution = WorkflowExecution(
            node_id=node.id,
            workflow_id=workflow.id,
            current_step_id=step.id,
            status="running",
        )
        test_db.add(execution)
        test_db.flush()
        return execution, step

    def test_callback_step_started(self, client, test_db):
        """POST /callback/step-started creates step result."""
        execution, step = self._create_execution(test_db)

        response = client.post(
            "/api/v1/callback/step-started",
            json={
                "execution_id": execution.id,
                "step_id": step.id,
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "running"

    def test_callback_step_completed(self, client, test_db):
        """POST /callback/step-completed updates step result."""
        from src.db.models import StepResult

        execution, step = self._create_execution(test_db)

        # Create running step result
        result = StepResult(
            execution_id=execution.id,
            step_id=step.id,
            attempt=1,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        test_db.add(result)
        test_db.flush()

        response = client.post(
            "/api/v1/callback/step-completed",
            json={
                "execution_id": execution.id,
                "step_id": step.id,
                "exit_code": 0,
                "message": "Step completed successfully",
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "completed"
        assert response.json()["data"]["exit_code"] == 0

    def test_callback_step_failed(self, client, test_db):
        """POST /callback/step-failed updates step result with failure."""
        from src.db.models import StepResult

        execution, step = self._create_execution(test_db)

        result = StepResult(
            execution_id=execution.id,
            step_id=step.id,
            attempt=1,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        test_db.add(result)
        test_db.flush()

        response = client.post(
            "/api/v1/callback/step-failed",
            json={
                "execution_id": execution.id,
                "step_id": step.id,
                "exit_code": 1,
                "message": "Step failed with error",
                "logs": "Error: Something went wrong",
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "failed"
        assert response.json()["data"]["exit_code"] == 1

    def test_callback_execution_not_found(self, client, test_db):
        """POST /callback/step-started with invalid execution returns 404."""
        response = client.post(
            "/api/v1/callback/step-started",
            json={
                "execution_id": "nonexistent-id",
                "step_id": "some-step-id",
            },
        )

        assert response.status_code == 404

    def test_callback_step_started_invalid_step(self, client, test_db):
        """POST /callback/step-started with invalid step_id returns 404."""
        execution, _ = self._create_execution(test_db)

        response = client.post(
            "/api/v1/callback/step-started",
            json={
                "execution_id": execution.id,
                "step_id": "invalid-step-id",
            },
        )

        assert response.status_code == 404
        assert "Step not found" in response.json()["detail"]

    def test_callback_heartbeat(self, client, test_db):
        """POST /callback/heartbeat updates execution timestamp."""
        execution, step = self._create_execution(test_db)

        response = client.post(
            "/api/v1/callback/heartbeat",
            json={
                "execution_id": execution.id,
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_callback_heartbeat_not_found(self, client, test_db):
        """POST /callback/heartbeat with invalid execution returns 404."""
        response = client.post(
            "/api/v1/callback/heartbeat",
            json={
                "execution_id": "nonexistent-id",
            },
        )

        assert response.status_code == 404

    def test_callback_step_completed_no_running_result(self, client, test_db):
        """POST /callback/step-completed without running result returns 404."""
        execution, step = self._create_execution(test_db)

        response = client.post(
            "/api/v1/callback/step-completed",
            json={
                "execution_id": execution.id,
                "step_id": step.id,
                "exit_code": 0,
            },
        )

        assert response.status_code == 404

    def test_callback_step_failed_no_running_result(self, client, test_db):
        """POST /callback/step-failed without running result returns 404."""
        execution, step = self._create_execution(test_db)

        response = client.post(
            "/api/v1/callback/step-failed",
            json={
                "execution_id": execution.id,
                "step_id": step.id,
                "exit_code": 1,
            },
        )

        assert response.status_code == 404

    def test_callback_step_started_increments_attempt(self, client, test_db):
        """POST /callback/step-started increments attempt number."""
        from src.db.models import StepResult

        execution, step = self._create_execution(test_db)

        # Create a completed step result (simulating a previous attempt)
        result = StepResult(
            execution_id=execution.id,
            step_id=step.id,
            attempt=1,
            status="failed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        test_db.add(result)
        test_db.flush()

        # Start a new attempt
        response = client.post(
            "/api/v1/callback/step-started",
            json={
                "execution_id": execution.id,
                "step_id": step.id,
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["attempt"] == 2
        assert response.json()["data"]["status"] == "running"
