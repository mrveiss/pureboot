"""Callback API endpoints for node provisioning feedback."""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import WorkflowExecution, StepResult, WorkflowStep


router = APIRouter(prefix="/callback", tags=["callbacks"])


class StepStartedRequest(BaseModel):
    """Request for step-started callback."""

    execution_id: str
    step_id: str


class StepCompletedRequest(BaseModel):
    """Request for step-completed callback."""

    execution_id: str
    step_id: str
    exit_code: int = 0
    message: str | None = Field(None, max_length=10000)


class StepFailedRequest(BaseModel):
    """Request for step-failed callback."""

    execution_id: str
    step_id: str
    exit_code: int = 1
    message: str | None = Field(None, max_length=10000)
    logs: str | None = Field(None, max_length=1000000)  # 1MB limit for logs


class HeartbeatRequest(BaseModel):
    """Request for heartbeat callback."""

    execution_id: str


class StepResultResponse(BaseModel):
    """Response with step result data."""

    id: str
    execution_id: str
    step_id: str
    attempt: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    exit_code: int | None
    message: str | None
    logs: str | None

    @classmethod
    def from_result(cls, result: StepResult) -> "StepResultResponse":
        """Create response from StepResult model."""
        return cls(
            id=result.id,
            execution_id=result.execution_id,
            step_id=result.step_id,
            attempt=result.attempt,
            status=result.status,
            started_at=result.started_at,
            completed_at=result.completed_at,
            exit_code=result.exit_code,
            message=result.message,
            logs=result.logs,
        )


class CallbackResponse(BaseModel):
    """Standard callback response."""

    success: bool = True
    data: StepResultResponse | None = None
    message: str = "OK"


class SimpleResponse(BaseModel):
    """Simple success response."""

    success: bool = True
    message: str = "OK"


@router.post("/step-started", response_model=CallbackResponse)
def callback_step_started(
    data: StepStartedRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Handle step-started callback from provisioning agent.

    Creates a new StepResult record marking the step as running.
    """
    # Verify execution exists
    execution = db.get(WorkflowExecution, data.execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Verify step exists and belongs to the workflow
    step = db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.id == data.step_id)
        .where(WorkflowStep.workflow_id == execution.workflow_id)
    ).scalars().first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found in workflow")

    # Get current attempt number
    existing_results = db.execute(
        select(StepResult)
        .where(StepResult.execution_id == data.execution_id)
        .where(StepResult.step_id == data.step_id)
    ).scalars().all()
    attempt = len(existing_results) + 1

    # Create step result
    result = StepResult(
        execution_id=data.execution_id,
        step_id=data.step_id,
        attempt=attempt,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(result)
    db.flush()
    db.refresh(result)

    return {
        "success": True,
        "data": StepResultResponse.from_result(result),
        "message": "Step started",
    }


@router.post("/step-completed", response_model=CallbackResponse)
def callback_step_completed(
    data: StepCompletedRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Handle step-completed callback from provisioning agent.

    Updates the running StepResult to completed status.
    """
    # Verify execution exists
    execution = db.get(WorkflowExecution, data.execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Find the running step result
    result = db.execute(
        select(StepResult)
        .where(StepResult.execution_id == data.execution_id)
        .where(StepResult.step_id == data.step_id)
        .where(StepResult.status == "running")
        .order_by(StepResult.attempt.desc())
    ).scalars().first()

    if not result:
        raise HTTPException(status_code=404, detail="Running step result not found")

    result.status = "completed"
    result.completed_at = datetime.now(timezone.utc)
    result.exit_code = data.exit_code
    result.message = data.message
    db.flush()
    db.refresh(result)

    return {
        "success": True,
        "data": StepResultResponse.from_result(result),
        "message": "Step completed",
    }


@router.post("/step-failed", response_model=CallbackResponse)
def callback_step_failed(
    data: StepFailedRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Handle step-failed callback from provisioning agent.

    Updates the running StepResult to failed status.
    """
    # Verify execution exists
    execution = db.get(WorkflowExecution, data.execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Find the running step result
    result = db.execute(
        select(StepResult)
        .where(StepResult.execution_id == data.execution_id)
        .where(StepResult.step_id == data.step_id)
        .where(StepResult.status == "running")
        .order_by(StepResult.attempt.desc())
    ).scalars().first()

    if not result:
        raise HTTPException(status_code=404, detail="Running step result not found")

    result.status = "failed"
    result.completed_at = datetime.now(timezone.utc)
    result.exit_code = data.exit_code
    result.message = data.message
    result.logs = data.logs
    db.flush()
    db.refresh(result)

    return {
        "success": True,
        "data": StepResultResponse.from_result(result),
        "message": "Step failed",
    }


@router.post("/heartbeat", response_model=SimpleResponse)
def callback_heartbeat(
    data: HeartbeatRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Validate that a workflow execution exists.

    Can be used by provisioning agents to verify the controller is reachable
    and the execution is still tracked.
    """
    execution = db.get(WorkflowExecution, data.execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Could add a last_heartbeat field to WorkflowExecution if needed
    # For now just verify the execution exists

    return {
        "success": True,
        "message": "Heartbeat received",
    }
