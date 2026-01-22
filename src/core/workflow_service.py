"""Service for loading and managing workflow definitions."""
import json
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class WorkflowNotFoundError(Exception):
    """Raised when a workflow is not found."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        super().__init__(f"Workflow not found: {workflow_id}")


class Workflow(BaseModel):
    """Workflow definition for OS installation."""

    id: str
    name: str
    kernel_path: str = ""
    initrd_path: str = ""
    cmdline: str = ""
    architecture: str = "x86_64"
    boot_mode: str = "bios"
    # Install method: "kernel" (default), "sanboot" (ISO), "chain" (chainload URL), "image" (disk image)
    install_method: str = "kernel"
    # For sanboot/chain: the URL to boot from
    boot_url: str = ""
    # For image method: disk image URL and target device
    image_url: str = ""
    target_device: str = "/dev/sda"
    # Post-deploy script URL (optional)
    post_script_url: str = ""


class WorkflowService:
    """Load and manage workflow definitions from JSON files."""

    def __init__(self, workflows_dir: Path) -> None:
        """Initialize with workflows directory path."""
        self.workflows_dir = workflows_dir

    def _validate_workflow_path(self, workflow_id: str) -> Path:
        """
        Validate and return safe workflow file path.

        Args:
            workflow_id: Workflow identifier (filename without .json)

        Returns:
            Validated Path to workflow file

        Raises:
            ValueError: If workflow_id contains path traversal sequences
        """
        # Resolve the path to catch traversal attempts
        workflow_path = (self.workflows_dir / f"{workflow_id}.json").resolve()
        workflows_dir_resolved = self.workflows_dir.resolve()

        # Ensure the path is within the workflows directory
        if not str(workflow_path).startswith(str(workflows_dir_resolved) + "/"):
            raise ValueError(f"Invalid workflow_id: {workflow_id}")

        return workflow_path

    def get_workflow(self, workflow_id: str) -> Workflow:
        """
        Load workflow definition by ID.

        Args:
            workflow_id: Workflow identifier (filename without .json)

        Returns:
            Workflow object

        Raises:
            WorkflowNotFoundError: If workflow file doesn't exist
            ValueError: If workflow_id contains path traversal sequences
        """
        workflow_path = self._validate_workflow_path(workflow_id)

        if not workflow_path.exists():
            raise WorkflowNotFoundError(workflow_id)

        try:
            data = json.loads(workflow_path.read_text())
            return Workflow(**data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to load workflow {workflow_id}: {e}")
            raise WorkflowNotFoundError(workflow_id) from e

    def list_workflows(self) -> list[Workflow]:
        """
        List all available workflows.

        Returns:
            List of Workflow objects
        """
        if not self.workflows_dir.exists():
            return []

        workflows = []
        for path in self.workflows_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                workflows.append(Workflow(**data))
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Skipping invalid workflow {path.name}: {e}")
                continue

        return workflows

    def resolve_variables(
        self,
        workflow: Workflow,
        server: str,
        node_id: str,
        mac: str,
        ip: str | None = None,
    ) -> Workflow:
        """
        Resolve template variables in workflow cmdline.

        Supported variables:
            ${server} - PureBoot server URL
            ${node_id} - Node UUID
            ${mac} - Node MAC address
            ${ip} - Node IP address (if available)

        Args:
            workflow: Original workflow
            server: Server base URL
            node_id: Node ID
            mac: Node MAC address
            ip: Node IP address (optional)

        Returns:
            New Workflow with resolved cmdline
        """
        cmdline = workflow.cmdline
        cmdline = cmdline.replace("${server}", server)
        cmdline = cmdline.replace("${node_id}", node_id)
        cmdline = cmdline.replace("${mac}", mac)
        if ip:
            cmdline = cmdline.replace("${ip}", ip)

        # Also resolve variables in boot_url if present
        boot_url = workflow.boot_url
        if boot_url:
            boot_url = boot_url.replace("${server}", server)
            boot_url = boot_url.replace("${node_id}", node_id)
            boot_url = boot_url.replace("${mac}", mac)
            if ip:
                boot_url = boot_url.replace("${ip}", ip)

        # Resolve variables in image_url if present
        image_url = workflow.image_url
        if image_url:
            image_url = image_url.replace("${server}", server)
            image_url = image_url.replace("${node_id}", node_id)
            image_url = image_url.replace("${mac}", mac)
            if ip:
                image_url = image_url.replace("${ip}", ip)

        # Resolve variables in post_script_url if present
        post_script_url = workflow.post_script_url
        if post_script_url:
            post_script_url = post_script_url.replace("${server}", server)
            post_script_url = post_script_url.replace("${node_id}", node_id)
            post_script_url = post_script_url.replace("${mac}", mac)
            if ip:
                post_script_url = post_script_url.replace("${ip}", ip)

        return Workflow(
            id=workflow.id,
            name=workflow.name,
            kernel_path=workflow.kernel_path,
            initrd_path=workflow.initrd_path,
            cmdline=cmdline,
            architecture=workflow.architecture,
            boot_mode=workflow.boot_mode,
            install_method=workflow.install_method,
            boot_url=boot_url,
            image_url=image_url,
            target_device=workflow.target_device,
            post_script_url=post_script_url,
        )
