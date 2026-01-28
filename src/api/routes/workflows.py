"""Workflow management API endpoints."""
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.api.schemas import ApiResponse
from src.db.database import get_db
from src.db.models import Workflow, WorkflowStep

router = APIRouter()


# ============== Pydantic Schemas ==============


class WorkflowStepCreate(BaseModel):
    """Input schema for creating a workflow step."""

    sequence: int = Field(..., ge=1, description="Step execution order (1-based)")
    name: str = Field(..., min_length=1, max_length=255)
    type: Literal["boot", "script", "reboot", "wait", "cloud_init"] = Field(
        ..., description="Step type"
    )
    config: dict | None = Field(None, description="Step configuration")
    timeout_seconds: int = Field(300, ge=1, description="Step timeout")
    on_failure: Literal["fail", "retry", "skip", "rollback"] = Field(
        "fail", description="Failure action"
    )
    max_retries: int = Field(0, ge=0, description="Maximum retry attempts")
    retry_delay_seconds: int = Field(30, ge=0, description="Delay between retries")
    next_state: Literal[
        "discovered", "pending", "installing", "installed", "active", "reprovision", "retired"
    ] | None = Field(None, description="Node state after step completion")


class WorkflowStepResponse(BaseModel):
    """Response schema for workflow step."""

    id: str
    sequence: int
    name: str
    type: str
    config: dict[str, Any]
    timeout_seconds: int
    on_failure: str
    max_retries: int
    retry_delay_seconds: int
    next_state: str | None

    @classmethod
    def from_step(cls, step: WorkflowStep) -> "WorkflowStepResponse":
        """Create response from WorkflowStep model."""
        config = {}
        if step.config_json:
            try:
                config = json.loads(step.config_json)
            except json.JSONDecodeError:
                config = {}

        return cls(
            id=step.id,
            sequence=step.sequence,
            name=step.name,
            type=step.type,
            config=config,
            timeout_seconds=step.timeout_seconds,
            on_failure=step.on_failure,
            max_retries=step.max_retries,
            retry_delay_seconds=step.retry_delay_seconds,
            next_state=step.next_state,
        )


class WorkflowCreate(BaseModel):
    """Input schema for creating a workflow."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    os_family: Literal["linux", "windows", "bsd"] = Field(
        ..., description="Target OS family"
    )
    architecture: Literal["x86_64", "aarch64", "armv7l"] | None = Field(
        None, description="Target architecture"
    )
    boot_mode: Literal["bios", "uefi"] | None = Field(
        None, description="Boot mode"
    )
    steps: list[WorkflowStepCreate] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    """Input schema for updating a workflow."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    os_family: Literal["linux", "windows", "bsd"] = Field(
        ..., description="Target OS family"
    )
    architecture: Literal["x86_64", "aarch64", "armv7l"] | None = Field(
        None, description="Target architecture"
    )
    boot_mode: Literal["bios", "uefi"] | None = Field(
        None, description="Boot mode"
    )
    steps: list[WorkflowStepCreate] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    """Response schema for workflow."""

    id: str
    name: str
    description: str
    os_family: str
    architecture: str
    boot_mode: str
    is_active: bool
    steps: list[WorkflowStepResponse]

    @classmethod
    def from_workflow(cls, workflow: Workflow) -> "WorkflowResponse":
        """Create response from Workflow model."""
        return cls(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description or "",
            os_family=workflow.os_family,
            architecture=workflow.architecture,
            boot_mode=workflow.boot_mode,
            is_active=workflow.is_active,
            steps=[WorkflowStepResponse.from_step(s) for s in workflow.steps],
        )


class WorkflowListResponse(BaseModel):
    """Response for workflow listing."""

    data: list[WorkflowResponse]
    total: int


# ============== Endpoints ==============


@router.post("/workflows", response_model=ApiResponse[WorkflowResponse], status_code=201)
def create_workflow(data: WorkflowCreate, db: Session = Depends(get_db)):
    """Create a new workflow with steps.

    Returns 409 if a workflow with the same name already exists.
    """
    # Check for duplicate name
    existing = db.execute(
        select(Workflow).where(Workflow.name == data.name, Workflow.is_active == True)  # noqa: E712
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=409, detail=f"Workflow '{data.name}' already exists")

    # Validate step sequence uniqueness
    sequences = [s.sequence for s in data.steps]
    if len(sequences) != len(set(sequences)):
        raise HTTPException(status_code=400, detail="Step sequences must be unique within a workflow")

    # Create workflow
    workflow = Workflow(
        name=data.name,
        description=data.description or "",
        os_family=data.os_family,
        architecture=data.architecture or "x86_64",
        boot_mode=data.boot_mode or "bios",
        is_active=True,
    )
    db.add(workflow)
    db.flush()

    # Create steps
    for step_data in data.steps:
        step = WorkflowStep(
            workflow_id=workflow.id,
            sequence=step_data.sequence,
            name=step_data.name,
            type=step_data.type,
            config_json=json.dumps(step_data.config or {}),
            timeout_seconds=step_data.timeout_seconds,
            on_failure=step_data.on_failure,
            max_retries=step_data.max_retries,
            retry_delay_seconds=step_data.retry_delay_seconds,
            next_state=step_data.next_state,
        )
        db.add(step)

    db.commit()
    db.refresh(workflow)

    # Eager load steps for response
    workflow = db.execute(
        select(Workflow)
        .where(Workflow.id == workflow.id)
        .options(selectinload(Workflow.steps))
    ).scalar_one()

    return ApiResponse(data=WorkflowResponse.from_workflow(workflow))


@router.get("/workflows", response_model=WorkflowListResponse)
def list_workflows(
    os_family: str | None = Query(None, description="Filter by OS family"),
    architecture: str | None = Query(None, description="Filter by architecture"),
    db: Session = Depends(get_db),
):
    """List all active workflows with optional filters."""
    query = select(Workflow).where(Workflow.is_active == True).options(selectinload(Workflow.steps))  # noqa: E712

    if os_family:
        query = query.where(Workflow.os_family == os_family)

    if architecture:
        query = query.where(Workflow.architecture == architecture)

    workflows = db.execute(query).scalars().all()

    return WorkflowListResponse(
        data=[WorkflowResponse.from_workflow(w) for w in workflows],
        total=len(workflows),
    )


@router.get("/workflows/{workflow_id}", response_model=ApiResponse[WorkflowResponse])
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """Get a workflow by ID with its steps.

    Returns 404 if the workflow does not exist or is inactive.
    """
    workflow = db.execute(
        select(Workflow)
        .where(Workflow.id == workflow_id, Workflow.is_active == True)  # noqa: E712
        .options(selectinload(Workflow.steps))
    ).scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")

    return ApiResponse(data=WorkflowResponse.from_workflow(workflow))


@router.put("/workflows/{workflow_id}", response_model=ApiResponse[WorkflowResponse])
def update_workflow(workflow_id: str, data: WorkflowUpdate, db: Session = Depends(get_db)):
    """Update a workflow and its steps.

    This replaces all existing steps with the new steps provided.
    Returns 404 if the workflow does not exist.
    Returns 409 if the new name conflicts with an existing workflow.
    """
    workflow = db.execute(
        select(Workflow)
        .where(Workflow.id == workflow_id, Workflow.is_active == True)  # noqa: E712
        .options(selectinload(Workflow.steps))
    ).scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")

    # Check for name conflict (if name is being changed)
    if data.name != workflow.name:
        existing = db.execute(
            select(Workflow).where(
                Workflow.name == data.name,
                Workflow.is_active == True,  # noqa: E712
                Workflow.id != workflow_id,
            )
        ).scalar_one_or_none()

        if existing:
            raise HTTPException(status_code=409, detail=f"Workflow '{data.name}' already exists")

    # Validate step sequence uniqueness
    sequences = [s.sequence for s in data.steps]
    if len(sequences) != len(set(sequences)):
        raise HTTPException(status_code=400, detail="Step sequences must be unique within a workflow")

    # Update workflow fields
    workflow.name = data.name
    workflow.description = data.description or ""
    workflow.os_family = data.os_family
    workflow.architecture = data.architecture or "x86_64"
    workflow.boot_mode = data.boot_mode or "bios"

    # Delete existing steps
    for step in workflow.steps:
        db.delete(step)

    # Create new steps
    for step_data in data.steps:
        step = WorkflowStep(
            workflow_id=workflow.id,
            sequence=step_data.sequence,
            name=step_data.name,
            type=step_data.type,
            config_json=json.dumps(step_data.config or {}),
            timeout_seconds=step_data.timeout_seconds,
            on_failure=step_data.on_failure,
            max_retries=step_data.max_retries,
            retry_delay_seconds=step_data.retry_delay_seconds,
            next_state=step_data.next_state,
        )
        db.add(step)

    db.commit()

    # Refresh with eager loading
    workflow = db.execute(
        select(Workflow)
        .where(Workflow.id == workflow.id)
        .options(selectinload(Workflow.steps))
    ).scalar_one()

    return ApiResponse(data=WorkflowResponse.from_workflow(workflow))


@router.delete("/workflows/{workflow_id}", response_model=ApiResponse[None])
def delete_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """Soft delete a workflow.

    Sets is_active=False rather than removing the record.
    Returns 404 if the workflow does not exist.
    """
    workflow = db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.is_active == True)  # noqa: E712
    ).scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")

    workflow.is_active = False
    db.commit()

    return ApiResponse(data=None, message="Workflow deleted")