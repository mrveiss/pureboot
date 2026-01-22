# iPXE Boot Script Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate dynamic iPXE boot scripts based on node state and workflow assignment.

**Architecture:** WorkflowService loads JSON workflow definitions from disk. Boot endpoint uses workflow data to generate install scripts when node is in `pending` state with workflow assigned.

**Tech Stack:** FastAPI, Pydantic, JSON files for workflow definitions

---

## Task 1: Add Workflow Pydantic Schema

**Files:**
- Modify: `src/api/schemas.py` (add at end, around line 814)

**Step 1: Add WorkflowResponse schema**

Add at end of `src/api/schemas.py`:

```python
# ============== Workflow Schemas ==============


class WorkflowResponse(BaseModel):
    """Workflow definition for OS installation."""

    id: str
    name: str
    kernel_path: str
    initrd_path: str
    cmdline: str
    architecture: str = "x86_64"
    boot_mode: str = "bios"


class WorkflowListResponse(BaseModel):
    """Response for workflow listing."""

    data: list[WorkflowResponse]
    total: int
```

**Step 2: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat: add workflow response schemas"
```

---

## Task 2: Add Workflows Directory Setting

**Files:**
- Modify: `src/config/settings.py` (add workflows_dir to Settings class)

**Step 1: Add workflows_dir setting**

In `src/config/settings.py`, add to the `Settings` class (around line 52):

```python
class Settings(BaseSettings):
    """Main application settings."""
    model_config = SettingsConfigDict(
        env_prefix="PUREBOOT_",
        env_nested_delimiter="__",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False

    # Workflow definitions directory
    workflows_dir: Path = Path("/var/lib/pureboot/workflows")

    tftp: TFTPSettings = Field(default_factory=TFTPSettings)
    dhcp_proxy: DHCPProxySettings = Field(default_factory=DHCPProxySettings)
    boot_menu: BootMenuSettings = Field(default_factory=BootMenuSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    registration: RegistrationSettings = Field(default_factory=RegistrationSettings)
```

**Step 2: Commit**

```bash
git add src/config/settings.py
git commit -m "feat: add workflows_dir setting"
```

---

## Task 3: Create WorkflowService with Tests

**Files:**
- Create: `src/core/workflow_service.py`
- Create: `tests/unit/test_workflow_service.py`

**Step 1: Write failing tests**

Create `tests/unit/test_workflow_service.py`:

```python
"""Tests for workflow service."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

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
```

**Step 2: Create WorkflowService implementation**

Create `src/core/workflow_service.py`:

```python
"""Service for loading and managing workflow definitions."""
import json
import logging
from dataclasses import dataclass
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
    kernel_path: str
    initrd_path: str
    cmdline: str
    architecture: str = "x86_64"
    boot_mode: str = "bios"


class WorkflowService:
    """Load and manage workflow definitions from JSON files."""

    def __init__(self, workflows_dir: Path):
        """Initialize with workflows directory path."""
        self.workflows_dir = workflows_dir

    def get_workflow(self, workflow_id: str) -> Workflow:
        """
        Load workflow definition by ID.

        Args:
            workflow_id: Workflow identifier (filename without .json)

        Returns:
            Workflow object

        Raises:
            WorkflowNotFoundError: If workflow file doesn't exist
        """
        workflow_path = self.workflows_dir / f"{workflow_id}.json"

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

        return Workflow(
            id=workflow.id,
            name=workflow.name,
            kernel_path=workflow.kernel_path,
            initrd_path=workflow.initrd_path,
            cmdline=cmdline,
            architecture=workflow.architecture,
            boot_mode=workflow.boot_mode,
        )
```

**Step 3: Commit**

```bash
git add src/core/workflow_service.py tests/unit/test_workflow_service.py
git commit -m "feat: add WorkflowService for loading workflow definitions"
```

---

## Task 4: Create Workflows API Router

**Files:**
- Create: `src/api/routes/workflows.py`

**Step 1: Create workflows router**

Create `src/api/routes/workflows.py`:

```python
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
                kernel_path=w.kernel_path,
                initrd_path=w.initrd_path,
                cmdline=w.cmdline,
                architecture=w.architecture,
                boot_mode=w.boot_mode,
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
                kernel_path=workflow.kernel_path,
                initrd_path=workflow.initrd_path,
                cmdline=workflow.cmdline,
                architecture=workflow.architecture,
                boot_mode=workflow.boot_mode,
            )
        )
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
```

**Step 2: Register router in main app**

In `src/main.py`, add import and include router. Find where other routers are included (search for `app.include_router`) and add:

```python
from src.api.routes.workflows import router as workflows_router

# Add with other router includes
app.include_router(workflows_router, prefix="/api/v1", tags=["workflows"])
```

**Step 3: Commit**

```bash
git add src/api/routes/workflows.py src/main.py
git commit -m "feat: add workflows API endpoints"
```

---

## Task 5: Update Boot Endpoint for Installation Scripts

**Files:**
- Modify: `src/api/routes/boot.py`

**Step 1: Add imports and workflow service**

At top of `src/api/routes/boot.py`, add:

```python
from datetime import datetime, timezone

from src.core.workflow_service import WorkflowNotFoundError, WorkflowService
```

After the router definition, add:

```python
workflow_service = WorkflowService(settings.workflows_dir)
```

**Step 2: Add install script generator function**

After `generate_pending_script` function (around line 70), add:

```python
def generate_install_script(node: Node, workflow, server: str) -> str:
    """Generate iPXE script for OS installation."""
    kernel_url = f"{server}{workflow.kernel_path}"
    initrd_url = f"{server}{workflow.initrd_path}"

    return f"""#!ipxe
# PureBoot - Installing {workflow.name}
# Node: {node.mac_address}
# Workflow: {workflow.id}
echo
echo ======================================
echo  PureBoot OS Installation
echo ======================================
echo
echo Workflow: {workflow.name}
echo Node MAC: {node.mac_address}
echo
echo Loading kernel...
kernel {kernel_url} {workflow.cmdline}
echo Loading initrd...
initrd {initrd_url}
echo
echo Starting installation...
boot
"""


def generate_pending_no_workflow_script(node: Node) -> str:
    """Generate iPXE script for pending node without workflow."""
    return f"""#!ipxe
# PureBoot - Pending (no workflow assigned)
# Node: {node.mac_address}
echo
echo Node is pending but no workflow assigned.
echo Please assign a workflow in the PureBoot UI.
echo
echo Booting from local disk in 10 seconds...
sleep 10
exit
"""


def generate_install_failed_script(node: Node) -> str:
    """Generate iPXE script for failed installation."""
    error_msg = node.last_install_error or "Unknown error"
    return f"""#!ipxe
# PureBoot - Installation Failed
# Node: {node.mac_address}
# Attempts: {node.install_attempts}
echo
echo ======================================
echo  Installation Failed
echo ======================================
echo
echo Node: {node.mac_address}
echo Attempts: {node.install_attempts}
echo Error: {error_msg}
echo
echo Manual intervention required.
echo Use PureBoot UI to reset and retry.
echo
echo Booting from local disk in 30 seconds...
echo Press any key for iPXE shell.
sleep 30 || shell
exit
"""
```

**Step 3: Update get_boot_script endpoint**

Replace the `match node.state:` block (around line 147) with:

```python
    # Return boot script based on state
    match node.state:
        case "discovered":
            return generate_discovery_script(mac, server)
        case "pending":
            # Check if workflow is assigned
            if not node.workflow_id:
                return generate_pending_no_workflow_script(node)

            # Load workflow and generate install script
            try:
                workflow = workflow_service.get_workflow(node.workflow_id)
                # Resolve variables in cmdline
                workflow = workflow_service.resolve_variables(
                    workflow,
                    server=server,
                    node_id=node.id,
                    mac=node.mac_address,
                    ip=node.ip_address,
                )
                return generate_install_script(node, workflow, server)
            except WorkflowNotFoundError:
                # Workflow not found - log error and show message
                return f"""#!ipxe
# PureBoot - Workflow Error
# Node: {node.mac_address}
echo
echo ERROR: Workflow '{node.workflow_id}' not found.
echo Please verify workflow exists or assign a different one.
echo
echo Booting from local disk...
sleep 10
exit
"""
        case "installing":
            # Let installation continue, boot local
            return generate_local_boot_script()
        case "install_failed":
            return generate_install_failed_script(node)
        case "installed" | "active" | "retired":
            return generate_local_boot_script()
        case _:
            # Default to local boot for unknown states
            return generate_local_boot_script()
```

**Step 4: Fix datetime.utcnow() deprecation**

Change line 134 from:
```python
    node.last_seen_at = datetime.utcnow()
```
to:
```python
    node.last_seen_at = datetime.now(timezone.utc)
```

**Step 5: Commit**

```bash
git add src/api/routes/boot.py
git commit -m "feat: generate installation scripts from workflows in boot endpoint"
```

---

## Task 6: Add Boot Script Tests

**Files:**
- Create: `tests/unit/test_boot_scripts.py`

**Step 1: Create boot script tests**

Create `tests/unit/test_boot_scripts.py`:

```python
"""Tests for boot script generation."""
import pytest
from unittest.mock import MagicMock, patch

from src.api.routes.boot import (
    generate_local_boot_script,
    generate_discovery_script,
    generate_install_script,
    generate_pending_no_workflow_script,
    generate_install_failed_script,
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

    def test_install_script_contains_kernel_initrd(self):
        """Install script includes kernel and initrd commands."""
        node = MagicMock()
        node.mac_address = "aa:bb:cc:dd:ee:ff"
        node.id = "test-node-id"

        workflow = Workflow(
            id="ubuntu-2404",
            name="Ubuntu 24.04",
            kernel_path="/files/ubuntu/vmlinuz",
            initrd_path="/files/ubuntu/initrd",
            cmdline="ip=dhcp",
        )

        script = generate_install_script(node, workflow, "http://server:8080")

        assert "#!ipxe" in script
        assert "kernel http://server:8080/files/ubuntu/vmlinuz" in script
        assert "initrd http://server:8080/files/ubuntu/initrd" in script
        assert "ip=dhcp" in script
        assert "boot" in script

    def test_pending_no_workflow_script(self):
        """Pending script without workflow shows message."""
        node = MagicMock()
        node.mac_address = "aa:bb:cc:dd:ee:ff"

        script = generate_pending_no_workflow_script(node)

        assert "#!ipxe" in script
        assert "no workflow" in script.lower()
        assert "exit" in script

    def test_install_failed_script_shows_error(self):
        """Install failed script shows error message and attempts."""
        node = MagicMock()
        node.mac_address = "aa:bb:cc:dd:ee:ff"
        node.install_attempts = 3
        node.last_install_error = "Disk not found"

        script = generate_install_failed_script(node)

        assert "#!ipxe" in script
        assert "Failed" in script
        assert "3" in script
        assert "Disk not found" in script
        assert "Manual intervention" in script
```

**Step 2: Commit**

```bash
git add tests/unit/test_boot_scripts.py
git commit -m "test: add boot script generation tests"
```

---

## Task 7: Create Example Workflow File

**Files:**
- Create: `examples/workflows/ubuntu-2404-server.json`

**Step 1: Create example workflow**

Create directory and file `examples/workflows/ubuntu-2404-server.json`:

```json
{
  "id": "ubuntu-2404-server",
  "name": "Ubuntu 24.04 LTS Server",
  "kernel_path": "/api/v1/files/default/workflows/ubuntu-2404/vmlinuz",
  "initrd_path": "/api/v1/files/default/workflows/ubuntu-2404/initrd",
  "cmdline": "ip=dhcp autoinstall ds=nocloud-net;s=${server}/api/v1/autoinstall/${node_id}/",
  "architecture": "x86_64",
  "boot_mode": "bios"
}
```

**Step 2: Commit**

```bash
mkdir -p examples/workflows
git add examples/workflows/ubuntu-2404-server.json
git commit -m "docs: add example Ubuntu workflow definition"
```

---

## Task 8: Push and Create PR

**Step 1: Push branch**

```bash
git push -u origin feature/ipxe-boot-scripts
```

**Step 2: Create PR**

```bash
gh pr create --title "feat: iPXE boot script generation with workflow support" --body "$(cat <<'EOF'
## Summary

- Adds WorkflowService for loading workflow definitions from JSON files
- Updates boot endpoint to generate installation scripts when node is `pending` with workflow assigned
- Adds `/api/v1/workflows` endpoints for listing and viewing workflows
- Adds `workflows_dir` configuration setting

## Changes

- `src/core/workflow_service.py` - New service for loading JSON workflow files
- `src/api/routes/workflows.py` - New API endpoints for workflows
- `src/api/routes/boot.py` - Updated to generate install scripts from workflows
- `src/api/schemas.py` - Added WorkflowResponse schemas
- `src/config/settings.py` - Added workflows_dir setting
- Tests for workflow service and boot script generation

## Boot Script Flow

1. Node PXE boots and requests `/api/v1/boot?mac=...`
2. If node in `pending` state with `workflow_id`:
   - Load workflow JSON from `workflows_dir`
   - Generate iPXE script with kernel/initrd/cmdline
3. Node boots installer

## Test plan

- [ ] Unit tests pass for WorkflowService
- [ ] Boot endpoint returns install script for pending node with workflow
- [ ] Boot endpoint returns error message if workflow not found
- [ ] Workflows API lists available workflows

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add workflow schemas | `src/api/schemas.py` |
| 2 | Add workflows_dir setting | `src/config/settings.py` |
| 3 | Create WorkflowService | `src/core/workflow_service.py`, tests |
| 4 | Create workflows router | `src/api/routes/workflows.py`, `src/main.py` |
| 5 | Update boot endpoint | `src/api/routes/boot.py` |
| 6 | Add boot script tests | `tests/unit/test_boot_scripts.py` |
| 7 | Example workflow | `examples/workflows/ubuntu-2404-server.json` |
| 8 | Push and create PR | - |
