# iPXE Boot Script Generation Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate dynamic iPXE boot scripts based on node state and assigned workflow.

**Architecture:** State-aware boot endpoint that returns appropriate iPXE scripts. Workflows defined as JSON files loaded by WorkflowService.

**Tech Stack:** FastAPI, Pydantic, JSON workflow files

---

## 1. Boot Script Generation Architecture

The `/api/v1/boot` endpoint generates state-aware iPXE scripts:

| State | Boot Action |
|-------|-------------|
| Unknown MAC (auto_register=true) | Register node, return discovery script |
| Unknown MAC (auto_register=false) | Return local boot |
| `discovered` | Show "waiting for assignment", local boot |
| `pending` | Load kernel/initrd from workflow, begin installation |
| `installing` | Continue installation (local boot to let installer run) |
| `install_failed` | Show error message, local boot with retry prompt |
| `installed` / `active` | Local boot |
| `retired` | Local boot |

**Key Change:** When state is `pending` AND workflow_id is set, the endpoint generates an actual installation script with kernel/initrd/cmdline from the workflow definition.

**Workflow Definition Format** (stored as JSON files in `/var/lib/pureboot/workflows/`):
```json
{
  "id": "ubuntu-2404-server",
  "name": "Ubuntu 24.04 Server",
  "kernel_path": "/files/workflows/ubuntu-2404/vmlinuz",
  "initrd_path": "/files/workflows/ubuntu-2404/initrd",
  "cmdline": "ip=dhcp autoinstall ds=nocloud-net;s=http://${server}/api/v1/autoinstall/${node_id}/"
}
```

## 2. Workflow Service

A new `WorkflowService` class handles loading workflow definitions from JSON files.

**File:** `src/core/workflow_service.py`

```python
class WorkflowService:
    """Load and manage workflow definitions from JSON files."""

    def __init__(self, workflows_dir: Path):
        self.workflows_dir = workflows_dir

    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Load workflow definition by ID."""
        # Loads from {workflows_dir}/{workflow_id}.json

    async def list_workflows(self) -> list[Workflow]:
        """List all available workflows."""

    def resolve_urls(self, workflow: Workflow, server: str, node: Node) -> ResolvedWorkflow:
        """Resolve template variables in kernel/initrd paths and cmdline."""
        # Supports: ${server}, ${node_id}, ${mac}, ${ip}
```

**Workflow Pydantic Model:**
```python
class Workflow(BaseModel):
    id: str
    name: str
    kernel_path: str      # e.g., "/files/ubuntu/vmlinuz"
    initrd_path: str      # e.g., "/files/ubuntu/initrd"
    cmdline: str          # e.g., "ip=dhcp autoinstall ds=nocloud-net"
    architecture: str = "x86_64"  # x86_64, aarch64
    boot_mode: str = "bios"       # bios, uefi
```

**Config Setting:**
```python
# In settings
workflows_dir: Path = Path("/var/lib/pureboot/workflows")
```

## 3. Updated Boot Endpoint Logic

The existing `boot.py` will be updated to handle `pending` state with actual installation scripts.

```python
match node.state:
    case "discovered":
        return generate_discovery_script(mac, server)

    case "pending":
        if not node.workflow_id:
            return generate_pending_no_workflow_script(node)

        workflow = await workflow_service.get_workflow(node.workflow_id)
        if not workflow:
            return generate_workflow_not_found_script(node)

        return generate_install_script(node, workflow, server)

    case "installing":
        return generate_local_boot_script()

    case "install_failed":
        return generate_install_failed_script(node)

    case "installed" | "active":
        return generate_local_boot_script()
```

**Install Script Generation:**
```python
def generate_install_script(node: Node, workflow: Workflow, server: str) -> str:
    kernel_url = f"http://{server}{workflow.kernel_path}"
    initrd_url = f"http://{server}{workflow.initrd_path}"

    # Substitute variables in cmdline
    cmdline = workflow.cmdline.replace("${server}", server)
    cmdline = cmdline.replace("${node_id}", node.id)
    cmdline = cmdline.replace("${mac}", node.mac_address)

    return f"""#!ipxe
# PureBoot - Installing {workflow.name}
# Node: {node.mac_address}
echo Starting installation: {workflow.name}
kernel {kernel_url} {cmdline}
initrd {initrd_url}
boot
"""
```

## 4. Workflow API Endpoints

**File:** `src/api/routes/workflows.py`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/workflows` | List all available workflows |
| GET | `/api/v1/workflows/{workflow_id}` | Get workflow details |

**Response Schema:**
```python
class WorkflowResponse(BaseModel):
    id: str
    name: str
    kernel_path: str
    initrd_path: str
    cmdline: str
    architecture: str = "x86_64"
    boot_mode: str = "bios"

class WorkflowListResponse(BaseModel):
    data: list[WorkflowResponse]
    total: int
```

## 5. Implementation Summary

**Files to Create:**
| File | Purpose |
|------|---------|
| `src/core/workflow_service.py` | WorkflowService class for loading JSON workflows |
| `src/api/routes/workflows.py` | Workflow list/get API endpoints |
| `tests/unit/test_workflow_service.py` | Unit tests for WorkflowService |
| `tests/unit/test_boot_scripts.py` | Unit tests for boot script generation |

**Files to Modify:**
| File | Changes |
|------|---------|
| `src/api/routes/boot.py` | Add workflow loading, install script generation for `pending` state |
| `src/api/schemas.py` | Add WorkflowResponse, WorkflowListResponse |
| `src/api/routes/__init__.py` | Register workflows router |
| `src/config.py` | Add `workflows_dir` setting |

**Not in Scope (deferred to Issue #28):**
- Workflow CRUD operations (create/update/delete via API)
- Workflow validation
- Template inheritance
- Post-install scripts

**Testing Strategy:**
1. Unit tests for WorkflowService (load, list, resolve URLs)
2. Unit tests for boot script generation per state
3. Integration test: node with workflow_id returns install script

**Example Boot Flow:**
1. Node PXE boots → hits `/api/v1/boot?mac=aa:bb:cc:dd:ee:ff`
2. Node found in `pending` state with `workflow_id=ubuntu-2404-server`
3. WorkflowService loads `/var/lib/pureboot/workflows/ubuntu-2404-server.json`
4. Boot endpoint returns iPXE script with kernel/initrd/cmdline
5. Node boots installer, reports `installation_status=started`
6. State transitions to `installing`
