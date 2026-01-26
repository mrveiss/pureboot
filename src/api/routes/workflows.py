"""Workflow management API endpoints."""
from fastapi import APIRouter, HTTPException

from src.api.schemas import ApiResponse, WorkflowListResponse, WorkflowResponse
from src.config import settings
from src.core.workflow_service import WorkflowNotFoundError, WorkflowService

router = APIRouter()

# Initialize service with configured directory
workflow_service = WorkflowService(settings.workflows_dir)


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows():
    """List all available workflows."""
    workflows = workflow_service.list_workflows()
    return WorkflowListResponse(
        data=[
            WorkflowResponse(
                id=w.id,
                name=w.name,
                description=w.description,
                kernel_path=w.kernel_path,
                initrd_path=w.initrd_path,
                cmdline=w.cmdline,
                architecture=w.architecture,
                boot_mode=w.boot_mode,
                install_method=w.install_method,
                boot_params=w.boot_params,
            )
            for w in workflows
        ],
        total=len(workflows),
    )


@router.get("/workflows/{workflow_id}", response_model=ApiResponse[WorkflowResponse])
async def get_workflow(workflow_id: str):
    """Get workflow details by ID."""
    try:
        workflow = workflow_service.get_workflow(workflow_id)
        return ApiResponse(
            data=WorkflowResponse(
                id=workflow.id,
                name=workflow.name,
                description=workflow.description,
                kernel_path=workflow.kernel_path,
                initrd_path=workflow.initrd_path,
                cmdline=workflow.cmdline,
                architecture=workflow.architecture,
                boot_mode=workflow.boot_mode,
                install_method=workflow.install_method,
                boot_params=workflow.boot_params,
            )
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow ID")
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
