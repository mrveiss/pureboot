# Workflow Engine & Template Management System Design

**Date:** 2026-01-26
**Status:** Draft
**Related Issues:** #28 (Workflow Engine), #80 (Template Management)

## Overview

This design implements a unified workflow engine and enhanced template management system for PureBoot. The system enables full orchestration of node provisioning with step-by-step execution tracking, template versioning with semantic versions, and a flexible variable substitution system.

## Key Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Workflow storage | Hybrid - DB primary, YAML import/export | API flexibility + GitOps compatibility |
| Step execution | Full orchestration | PureBoot actively drives steps after PXE boot |
| Feedback mechanism | Callback agent + cloud-init | Agent for install stages, cloud-init for post-install |
| Template versions | Immutable with major.minor | Clear audit trail, semantic versioning |
| Template composition | Simple includes `${include:name}` | Covers reuse without inheritance complexity |
| Variables | Structured namespaces `${node.x}` | Clear hierarchy, extensible |

---

## Database Models

### Workflow Model

```python
class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    os_family: Mapped[str] = mapped_column(String(50), nullable=False)  # linux, windows, bsd
    architecture: Mapped[str] = mapped_column(String(50), default="x86_64")  # x86_64, aarch64
    boot_mode: Mapped[str] = mapped_column(String(50), default="bios")  # bios, uefi
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    steps: Mapped[list["WorkflowStep"]] = relationship(back_populates="workflow", order_by="WorkflowStep.sequence")
    executions: Mapped[list["WorkflowExecution"]] = relationship(back_populates="workflow")
```

### WorkflowStep Model

```python
class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflows.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)  # execution order
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # boot, script, reboot, wait, cloud_init
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # type-specific configuration
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    on_failure: Mapped[str] = mapped_column(String(50), default="fail")  # fail, retry, skip, rollback
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, default=30)
    next_state: Mapped[str | None] = mapped_column(String(50), nullable=True)  # node state after step
    rollback_step_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    workflow: Mapped["Workflow"] = relationship(back_populates="steps")
```

### WorkflowExecution Model

```python
class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id"), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflows.id"), nullable=False)
    current_step_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workflow_steps.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, running, completed, failed, cancelled
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    node: Mapped["Node"] = relationship()
    workflow: Mapped["Workflow"] = relationship(back_populates="executions")
    current_step: Mapped["WorkflowStep | None"] = relationship()
    step_results: Mapped[list["StepResult"]] = relationship(back_populates="execution")
```

### StepResult Model

```python
class StepResult(Base):
    __tablename__ = "step_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    execution_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_executions.id"), nullable=False)
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_steps.id"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # success, failed, skipped, timed_out
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    execution: Mapped["WorkflowExecution"] = relationship(back_populates="step_results")
    step: Mapped["WorkflowStep"] = relationship()
```

### TemplateVersion Model

```python
class TemplateVersion(Base):
    __tablename__ = "template_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("templates.id"), nullable=False)
    major: Mapped[int] = mapped_column(Integer, nullable=False)
    minor: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # For file-based templates (ISOs, images)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_backend_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("storage_backends.id"), nullable=True)

    # Relationships
    template: Mapped["Template"] = relationship(back_populates="versions")
    storage_backend: Mapped["StorageBackend | None"] = relationship()

    @property
    def version_string(self) -> str:
        return f"v{self.major}.{self.minor}"

    __table_args__ = (
        UniqueConstraint("template_id", "major", "minor", name="uq_template_version"),
    )
```

### Updated Template Model

```python
class Template(Base):
    __tablename__ = "templates"

    # ... existing fields ...

    # New fields for versioning
    current_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("template_versions.id"), nullable=True)

    # Relationships
    versions: Mapped[list["TemplateVersion"]] = relationship(back_populates="template", foreign_keys=[TemplateVersion.template_id])
    current_version: Mapped["TemplateVersion | None"] = relationship(foreign_keys=[current_version_id])
```

---

## Variable Substitution System

### Variable Namespaces

```python
VARIABLE_NAMESPACES = {
    "node": {
        "id", "mac", "ip", "hostname", "uuid", "serial",
        "vendor", "model", "architecture", "boot_mode", "state"
    },
    "group": {
        "id", "name", "description"
    },
    "workflow": {
        "id", "name", "description"
    },
    "server": {
        "url", "tftp_url", "http_url"
    },
    "template": {
        "id", "name", "version"
    },
    "execution": {
        "id", "step_id", "step_name"
    },
    "meta": {
        # Dynamic - pulls from node.metadata JSON field
    },
    "secret": {
        # Pulls from secure storage, masked in logs
    }
}
```

### Variable Syntax

```bash
# Standard variable
${node.mac}                     # aa:bb:cc:dd:ee:ff

# With default value
${node.ip|dhcp}                 # uses "dhcp" if node.ip is unset

# Include another template
${include:base-packages}        # latest version
${include:base-packages:v2}     # latest v2.x
${include:base-packages:v2.1}   # exact version

# Conditional
${if:node.ip}static${endif}     # outputs "static" only if node.ip exists
```

### VariableResolver Service

```python
class VariableResolver:
    """Resolve template variables from structured namespaces."""

    VARIABLE_PATTERN = re.compile(r'\$\{([a-z]+)\.([a-z_]+)(?:\|([^}]*))?\}')

    def __init__(self, node: Node, workflow: Workflow, execution: WorkflowExecution, settings: Settings):
        self.context = self._build_context(node, workflow, execution, settings)

    def _build_context(self, node, workflow, execution, settings) -> dict:
        return {
            "node": {
                "id": node.id,
                "mac": node.mac_address,
                "ip": node.ip_address,
                "hostname": node.hostname,
                # ... etc
            },
            "group": {
                "id": node.group.id if node.group else None,
                "name": node.group.name if node.group else None,
            },
            "workflow": {
                "id": workflow.id,
                "name": workflow.name,
            },
            "server": {
                "url": settings.server_url,
                "tftp_url": f"tftp://{settings.tftp_host}",
                "http_url": f"http://{settings.http_host}:{settings.http_port}",
            },
            "execution": {
                "id": execution.id,
                "step_id": execution.current_step_id,
            },
            "meta": node.metadata or {},
        }

    def resolve(self, content: str) -> str:
        """Resolve all ${namespace.key} variables in content."""
        def replace(match):
            namespace, key, default = match.groups()
            value = self.context.get(namespace, {}).get(key)
            if value is None:
                return default if default else match.group(0)
            return str(value)

        return self.VARIABLE_PATTERN.sub(replace, content)

    def list_variables(self, content: str) -> list[str]:
        """Extract all variable references for validation/UI."""
        return [f"{m[0]}.{m[1]}" for m in self.VARIABLE_PATTERN.findall(content)]

    def validate(self, content: str) -> list[str]:
        """Return list of unknown/invalid variable references."""
        errors = []
        for namespace, key, _ in self.VARIABLE_PATTERN.findall(content):
            if namespace not in VARIABLE_NAMESPACES:
                errors.append(f"Unknown namespace: {namespace}")
            elif namespace != "meta" and key not in VARIABLE_NAMESPACES[namespace]:
                errors.append(f"Unknown variable: {namespace}.{key}")
        return errors
```

---

## Template Include System

### TemplateRenderer Service

```python
class TemplateRenderer:
    """Render templates with includes and variable substitution."""

    INCLUDE_PATTERN = re.compile(r'\$\{include:([a-zA-Z0-9_-]+)(?::v?(\d+)(?:\.(\d+))?)?\}')
    MAX_INCLUDE_DEPTH = 10

    def __init__(self, db: AsyncSession):
        self.db = db

    async def render(
        self,
        template_id: str,
        version: str | None,
        variable_resolver: VariableResolver,
    ) -> str:
        """Resolve includes and variables, return final content."""
        content = await self._get_template_content(template_id, version)
        content = await self._resolve_includes(content, set())
        content = variable_resolver.resolve(content)
        return content

    async def _get_template_content(self, template_id: str, version: str | None) -> str:
        """Get template content by ID and optional version."""
        template = await self._get_template(template_id)

        if version is None:
            # Use current (latest) version
            return template.current_version.content

        # Parse version string (v2, v2.1, or UUID)
        template_version = await self._resolve_version(template, version)
        return template_version.content

    async def _resolve_includes(self, content: str, visited: set[str], depth: int = 0) -> str:
        """Recursively resolve ${include:...} references."""
        if depth > self.MAX_INCLUDE_DEPTH:
            raise MaxIncludeDepthError(f"Include depth exceeded {self.MAX_INCLUDE_DEPTH}")

        async def replace_include(match):
            template_name, major, minor = match.groups()
            ref_key = f"{template_name}:{major}.{minor}" if minor else f"{template_name}:{major}" if major else template_name

            if ref_key in visited:
                raise CircularIncludeError(f"Circular include detected: {ref_key}")
            visited.add(ref_key)

            version = None
            if major and minor:
                version = f"v{major}.{minor}"
            elif major:
                version = f"v{major}"

            included_content = await self._get_template_content_by_name(template_name, version)
            return await self._resolve_includes(included_content, visited, depth + 1)

        # Process all includes
        result = content
        for match in self.INCLUDE_PATTERN.finditer(content):
            replacement = await replace_include(match)
            result = result.replace(match.group(0), replacement)

        return result
```

---

## Workflow Orchestration Engine

### Orchestration Flow

```
Node boots via PXE
        |
        v
PureBoot creates WorkflowExecution (status: pending)
        |
        v
Step 1 starts -> iPXE script generated for step
        |
        v
Node executes step -> Callback agent POSTs status
        |
        v
PureBoot advances to Step 2 (or handles failure)
        |
        v
... repeat until final step ...
        |
        v
WorkflowExecution marked complete -> Node state transitions
```

### WorkflowOrchestrator Service

```python
class WorkflowOrchestrator:
    """Orchestrate workflow execution across nodes."""

    def __init__(self, db: AsyncSession, scheduler: TimeoutScheduler):
        self.db = db
        self.scheduler = scheduler

    async def start_execution(self, node: Node, workflow: Workflow) -> WorkflowExecution:
        """Initialize execution, set first step as current."""
        first_step = workflow.steps[0] if workflow.steps else None

        execution = WorkflowExecution(
            node_id=node.id,
            workflow_id=workflow.id,
            current_step_id=first_step.id if first_step else None,
            status="pending",
        )
        self.db.add(execution)
        await self.db.flush()

        if first_step:
            await self._start_step(execution, first_step)

        return execution

    async def _start_step(self, execution: WorkflowExecution, step: WorkflowStep):
        """Start a workflow step."""
        execution.status = "running"
        execution.current_step_id = step.id
        if not execution.started_at:
            execution.started_at = datetime.utcnow()

        # Create step result record
        result = StepResult(
            execution_id=execution.id,
            step_id=step.id,
            attempt=await self._get_attempt_number(execution.id, step.id),
            status="running",
        )
        self.db.add(result)

        # Schedule timeout
        await self.scheduler.schedule_timeout(
            execution.id, step.id, step.timeout_seconds
        )

        await self.db.flush()

    async def handle_callback(
        self,
        execution_id: str,
        step_id: str,
        status: str,
        message: str | None = None,
        exit_code: int | None = None,
        logs: str | None = None,
    ) -> WorkflowExecution:
        """Process callback from node, advance or handle failure."""
        execution = await self._get_execution(execution_id)
        step = await self._get_step(step_id)

        # Cancel timeout
        await self.scheduler.cancel_timeout(execution_id, step_id)

        # Update step result
        result = await self._get_current_result(execution_id, step_id)
        result.status = status
        result.completed_at = datetime.utcnow()
        result.exit_code = exit_code
        result.message = message
        result.logs = logs

        if status == "success":
            await self._advance_to_next_step(execution, step)
        elif status == "failed":
            await self._handle_failure(execution, step)

        await self.db.flush()
        return execution

    async def _advance_to_next_step(self, execution: WorkflowExecution, completed_step: WorkflowStep):
        """Move to next step or complete execution."""
        # Update node state if step defines next_state
        if completed_step.next_state:
            node = await self._get_node(execution.node_id)
            node.state = completed_step.next_state

        # Find next step
        workflow = await self._get_workflow(execution.workflow_id)
        next_step = None
        for i, step in enumerate(workflow.steps):
            if step.id == completed_step.id and i + 1 < len(workflow.steps):
                next_step = workflow.steps[i + 1]
                break

        if next_step:
            await self._start_step(execution, next_step)
        else:
            # Workflow complete
            execution.status = "completed"
            execution.completed_at = datetime.utcnow()

    async def _handle_failure(self, execution: WorkflowExecution, step: WorkflowStep):
        """Handle step failure based on on_failure policy."""
        attempt = await self._get_attempt_number(execution.id, step.id)

        if step.on_failure == "retry" and attempt < step.max_retries:
            # Schedule retry after delay
            await asyncio.sleep(step.retry_delay_seconds)
            await self._start_step(execution, step)

        elif step.on_failure == "skip":
            # Log warning and continue
            await self._advance_to_next_step(execution, step)

        elif step.on_failure == "rollback" and step.rollback_step_id:
            # Execute rollback step
            rollback_step = await self._get_step(step.rollback_step_id)
            await self._start_step(execution, rollback_step)

        else:
            # Fail execution
            execution.status = "failed"
            execution.completed_at = datetime.utcnow()
            execution.error_message = f"Step '{step.name}' failed after {attempt} attempts"

    async def get_current_boot_config(self, node: Node) -> BootConfig | None:
        """Generate boot config for node's current execution step."""
        execution = await self._get_active_execution(node.id)
        if not execution or not execution.current_step_id:
            return None

        step = await self._get_step(execution.current_step_id)
        return await self._build_boot_config(node, execution, step)
```

### Step Types

| Type | Config Fields | Callback Expected |
|------|---------------|-------------------|
| `boot` | kernel, initrd, cmdline, template_id | Yes - agent reports boot complete |
| `script` | script_url, interpreter | Yes - exit code |
| `reboot` | delay_seconds | Yes - confirms reboot initiated |
| `wait` | duration_seconds | No - timer-based |
| `cloud_init` | template_id, phone_home_url | Yes - cloud-init phone-home |

---

## Callback Agent

### Linux Agent (Shell)

```bash
#!/bin/sh
# pureboot-agent.sh - embedded in initrd
set -e

PUREBOOT_SERVER="${pureboot_server}"
EXECUTION_ID="${execution_id}"
STEP_ID="${step_id}"

callback() {
    status="$1"
    message="$2"
    exit_code="${3:-0}"

    curl -sf -X POST "${PUREBOOT_SERVER}/api/v1/callback/${EXECUTION_ID}/step/${STEP_ID}" \
        -H "Content-Type: application/json" \
        -d "{\"status\":\"${status}\",\"message\":\"${message}\",\"exit_code\":${exit_code}}" \
        || echo "Warning: callback failed"
}

heartbeat() {
    while true; do
        curl -sf -X POST "${PUREBOOT_SERVER}/api/v1/callback/${EXECUTION_ID}/heartbeat" || true
        sleep 30
    done
}

# Start heartbeat in background
heartbeat &
HEARTBEAT_PID=$!

# Report start
callback "progress" "Step started"

# Execute actual work (injected by PureBoot)
${step_script}
result=$?

# Stop heartbeat
kill $HEARTBEAT_PID 2>/dev/null || true

# Report completion
if [ $result -eq 0 ]; then
    callback "success" "Step completed successfully"
else
    callback "failed" "Exit code: $result" $result
fi

exit $result
```

### Windows Agent (PowerShell)

```powershell
# pureboot-agent.ps1 - embedded in WinPE
$ErrorActionPreference = "Stop"

$Server = "${pureboot_server}"
$ExecutionId = "${execution_id}"
$StepId = "${step_id}"

function Send-Callback {
    param($Status, $Message, $ExitCode = 0)

    $body = @{
        status = $Status
        message = $Message
        exit_code = $ExitCode
    } | ConvertTo-Json

    try {
        Invoke-RestMethod -Uri "$Server/api/v1/callback/$ExecutionId/step/$StepId" `
            -Method Post -Body $body -ContentType "application/json"
    } catch {
        Write-Warning "Callback failed: $_"
    }
}

function Start-Heartbeat {
    $script = {
        param($Server, $ExecutionId)
        while ($true) {
            try {
                Invoke-RestMethod -Uri "$Server/api/v1/callback/$ExecutionId/heartbeat" -Method Post
            } catch {}
            Start-Sleep -Seconds 30
        }
    }
    Start-Job -ScriptBlock $script -ArgumentList $Server, $ExecutionId
}

# Start heartbeat
$heartbeatJob = Start-Heartbeat

# Report start
Send-Callback -Status "progress" -Message "Step started"

# Execute actual work
try {
    ${step_script}
    Send-Callback -Status "success" -Message "Step completed successfully"
} catch {
    Send-Callback -Status "failed" -Message $_.Exception.Message -ExitCode 1
    throw
} finally {
    Stop-Job $heartbeatJob -PassThru | Remove-Job
}
```

---

## API Endpoints

### Workflow CRUD

```
GET    /api/v1/workflows                    List workflows (filter: os_family, architecture, is_active)
POST   /api/v1/workflows                    Create workflow
GET    /api/v1/workflows/{id}               Get workflow with steps
PUT    /api/v1/workflows/{id}               Update workflow
DELETE /api/v1/workflows/{id}               Soft delete workflow
POST   /api/v1/workflows/import             Import from YAML
GET    /api/v1/workflows/{id}/export        Export to YAML
```

### Workflow Execution

```
POST   /api/v1/nodes/{node_id}/execute      Start workflow on node
GET    /api/v1/executions/{id}              Get execution status
GET    /api/v1/nodes/{node_id}/executions   List executions for node
POST   /api/v1/executions/{id}/cancel       Cancel execution
POST   /api/v1/executions/{id}/retry        Retry failed step
```

### Callback (Agent)

```
POST   /api/v1/callback/{execution_id}/step/{step_id}   Report step status
GET    /api/v1/callback/{execution_id}/current          Get current step config
POST   /api/v1/callback/{execution_id}/heartbeat        Keep-alive
```

### Template Versions

```
POST   /api/v1/templates/{id}/versions      Create new version (?bump=minor|major)
GET    /api/v1/templates/{id}/versions      List versions
GET    /api/v1/templates/{id}/versions/{v}  Get specific version (v2.3, latest, UUID)
POST   /api/v1/templates/{id}/preview       Preview with variables resolved
GET    /api/v1/templates/{id}/diff          Diff two versions (?from=v1.2&to=v2.0)
```

---

## Implementation Phases

### Phase 1: Database Models & Migrations
- [ ] Add `Workflow`, `WorkflowStep` models
- [ ] Add `TemplateVersion` model
- [ ] Add `WorkflowExecution`, `StepResult` models
- [ ] Update `Template` model with `current_version_id`
- [ ] Create database migrations
- [ ] Add indexes for common queries

### Phase 2: Template Versioning
- [ ] Implement `TemplateVersion` CRUD endpoints
- [ ] Implement `TemplateRenderer` service
- [ ] Implement `VariableResolver` service
- [ ] Add preview endpoint with variable substitution
- [ ] Add version diff endpoint
- [ ] Migrate existing templates to v1.0

### Phase 3: Workflow CRUD
- [ ] Implement workflow CRUD endpoints
- [ ] Implement YAML import/export
- [ ] Update `WorkflowService` for DB + file hybrid
- [ ] Add step validation logic
- [ ] Add workflow assignment to nodes

### Phase 4: Orchestration Engine
- [ ] Implement `WorkflowOrchestrator` service
- [ ] Implement callback API endpoints
- [ ] Implement `TimeoutScheduler`
- [ ] Update iPXE builder for execution context
- [ ] Add execution monitoring/dashboard data

### Phase 5: Callback Agent
- [ ] Create Linux agent script
- [ ] Create Windows agent script (PowerShell)
- [ ] Integrate agent embedding in boot images
- [ ] Implement cloud-init phone-home handler
- [ ] Test end-to-end orchestration

---

## File Structure

```
src/
├── core/
│   ├── workflow_service.py        # Update: DB + file hybrid
│   ├── workflow_orchestrator.py   # New: execution engine
│   ├── template_renderer.py       # New: includes + variables
│   ├── variable_resolver.py       # New: namespace resolution
│   └── timeout_scheduler.py       # New: step timeouts
├── api/routes/
│   ├── workflows.py               # Update: full CRUD + import/export
│   ├── templates.py               # Update: versioning endpoints
│   ├── executions.py              # New: execution management
│   └── callback.py                # New: agent callbacks
├── db/
│   ├── models.py                  # Update: new models
│   └── migrations/                # New migration files
└── agents/
    ├── linux-agent.sh             # New
    └── windows-agent.ps1          # New
```

---

## Testing Strategy

### Unit Tests
- Variable resolution with all namespaces
- Template include resolution (including circular detection)
- State machine transitions during orchestration
- Failure handling policies (retry, skip, rollback)

### Integration Tests
- Full workflow CRUD via API
- Template versioning lifecycle
- YAML import/export round-trip
- Callback processing and step advancement

### E2E Tests
- Complete workflow execution from PXE boot to completion
- Failure and retry scenarios
- Timeout handling
- Multi-step workflows with state transitions