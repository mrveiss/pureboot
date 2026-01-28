# Workflow Engine & Template Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement full workflow orchestration with step execution tracking and template versioning with semantic versions.

**Architecture:** Database-stored workflows with YAML import/export, callback-based orchestration engine, immutable template versions with major.minor semantics, and structured variable namespaces.

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic v2, pytest

---

## Phase 1: Database Models

### Task 1.1: Add TemplateVersion Model

**Files:**
- Modify: `src/db/models.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_models.py`:

```python
class TestTemplateVersion:
    """Test TemplateVersion model."""

    def test_template_version_creation(self, test_db):
        """TemplateVersion can be created with required fields."""
        template = Template(name="test-template", type="kickstart")
        test_db.add(template)
        test_db.flush()

        version = TemplateVersion(
            template_id=template.id,
            major=1,
            minor=0,
            content="# kickstart content",
            content_hash="abc123",
        )
        test_db.add(version)
        test_db.flush()

        assert version.id is not None
        assert version.major == 1
        assert version.minor == 0
        assert version.version_string == "v1.0"

    def test_template_version_unique_constraint(self, test_db):
        """TemplateVersion enforces unique major.minor per template."""
        template = Template(name="test-template", type="kickstart")
        test_db.add(template)
        test_db.flush()

        v1 = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="v1", content_hash="hash1"
        )
        test_db.add(v1)
        test_db.flush()

        v1_dup = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="v1 dup", content_hash="hash2"
        )
        test_db.add(v1_dup)

        with pytest.raises(Exception):  # IntegrityError
            test_db.flush()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestTemplateVersion -v`
Expected: FAIL with "TemplateVersion not defined"

**Step 3: Write minimal implementation**

Add to `src/db/models.py` after the `Template` class:

```python
class TemplateVersion(Base):
    """Version of a template with immutable content."""

    __tablename__ = "template_versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    template_id: Mapped[str] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    major: Mapped[int] = mapped_column(nullable=False)
    minor: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # For file-based templates (ISOs, images)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_backend_id: Mapped[str | None] = mapped_column(
        ForeignKey("storage_backends.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    template: Mapped["Template"] = relationship(back_populates="versions")
    storage_backend: Mapped["StorageBackend | None"] = relationship()

    @property
    def version_string(self) -> str:
        """Return version as string like 'v1.2'."""
        return f"v{self.major}.{self.minor}"

    __table_args__ = (
        UniqueConstraint("template_id", "major", "minor", name="uq_template_version"),
    )
```

Update `Template` class to add relationships:

```python
# Add after existing fields in Template class:
    current_version_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )

    # Relationships
    versions: Mapped[list["TemplateVersion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestTemplateVersion -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/db/models.py tests/unit/test_models.py
git commit -m "feat: add TemplateVersion model with semantic versioning"
```

---

### Task 1.2: Add Workflow Model

**Files:**
- Modify: `src/db/models.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_models.py`:

```python
class TestWorkflow:
    """Test Workflow model."""

    def test_workflow_creation(self, test_db):
        """Workflow can be created with required fields."""
        workflow = Workflow(
            name="ubuntu-2404",
            description="Ubuntu 24.04 Server",
            os_family="linux",
        )
        test_db.add(workflow)
        test_db.flush()

        assert workflow.id is not None
        assert workflow.name == "ubuntu-2404"
        assert workflow.os_family == "linux"
        assert workflow.architecture == "x86_64"
        assert workflow.boot_mode == "bios"
        assert workflow.is_active is True

    def test_workflow_unique_name(self, test_db):
        """Workflow name must be unique."""
        w1 = Workflow(name="ubuntu", os_family="linux")
        test_db.add(w1)
        test_db.flush()

        w2 = Workflow(name="ubuntu", os_family="linux")
        test_db.add(w2)

        with pytest.raises(Exception):
            test_db.flush()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestWorkflow -v`
Expected: FAIL with "Workflow not defined"

**Step 3: Write minimal implementation**

Add to `src/db/models.py`:

```python
class Workflow(Base):
    """Workflow definition for node provisioning."""

    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    os_family: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    architecture: Mapped[str] = mapped_column(String(50), default="x86_64")
    boot_mode: Mapped[str] = mapped_column(String(50), default="bios")
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan",
        order_by="WorkflowStep.sequence"
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestWorkflow -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/db/models.py tests/unit/test_models.py
git commit -m "feat: add Workflow model for provisioning definitions"
```

---

### Task 1.3: Add WorkflowStep Model

**Files:**
- Modify: `src/db/models.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_models.py`:

```python
class TestWorkflowStep:
    """Test WorkflowStep model."""

    def test_workflow_step_creation(self, test_db):
        """WorkflowStep can be created with required fields."""
        workflow = Workflow(name="test-workflow", os_family="linux")
        test_db.add(workflow)
        test_db.flush()

        step = WorkflowStep(
            workflow_id=workflow.id,
            sequence=1,
            name="Install OS",
            type="boot",
            config_json='{"kernel": "/vmlinuz", "initrd": "/initrd"}',
        )
        test_db.add(step)
        test_db.flush()

        assert step.id is not None
        assert step.sequence == 1
        assert step.type == "boot"
        assert step.timeout_seconds == 3600
        assert step.on_failure == "fail"

    def test_workflow_steps_ordered(self, test_db):
        """Workflow steps are returned in sequence order."""
        workflow = Workflow(name="test-workflow", os_family="linux")
        test_db.add(workflow)
        test_db.flush()

        step3 = WorkflowStep(workflow_id=workflow.id, sequence=3, name="Step 3", type="reboot")
        step1 = WorkflowStep(workflow_id=workflow.id, sequence=1, name="Step 1", type="boot")
        step2 = WorkflowStep(workflow_id=workflow.id, sequence=2, name="Step 2", type="script")
        test_db.add_all([step3, step1, step2])
        test_db.flush()

        test_db.refresh(workflow)
        assert [s.name for s in workflow.steps] == ["Step 1", "Step 2", "Step 3"]
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestWorkflowStep -v`
Expected: FAIL with "WorkflowStep not defined"

**Step 3: Write minimal implementation**

Add to `src/db/models.py`:

```python
class WorkflowStep(Base):
    """Individual step in a workflow."""

    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    timeout_seconds: Mapped[int] = mapped_column(default=3600)
    on_failure: Mapped[str] = mapped_column(String(50), default="fail")
    max_retries: Mapped[int] = mapped_column(default=3)
    retry_delay_seconds: Mapped[int] = mapped_column(default=30)
    next_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rollback_step_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    workflow: Mapped["Workflow"] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("workflow_id", "sequence", name="uq_workflow_step_sequence"),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestWorkflowStep -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/db/models.py tests/unit/test_models.py
git commit -m "feat: add WorkflowStep model for workflow stages"
```

---

### Task 1.4: Add WorkflowExecution Model

**Files:**
- Modify: `src/db/models.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_models.py`:

```python
class TestWorkflowExecution:
    """Test WorkflowExecution model."""

    def test_execution_creation(self, test_db):
        """WorkflowExecution can be created."""
        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-workflow", os_family="linux")
        test_db.add_all([node, workflow])
        test_db.flush()

        execution = WorkflowExecution(
            node_id=node.id,
            workflow_id=workflow.id,
        )
        test_db.add(execution)
        test_db.flush()

        assert execution.id is not None
        assert execution.status == "pending"
        assert execution.started_at is None

    def test_execution_status_transitions(self, test_db):
        """WorkflowExecution status can be updated."""
        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-workflow", os_family="linux")
        test_db.add_all([node, workflow])
        test_db.flush()

        execution = WorkflowExecution(node_id=node.id, workflow_id=workflow.id)
        test_db.add(execution)
        test_db.flush()

        execution.status = "running"
        execution.started_at = datetime.utcnow()
        test_db.flush()

        assert execution.status == "running"
        assert execution.started_at is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestWorkflowExecution -v`
Expected: FAIL with "WorkflowExecution not defined"

**Step 3: Write minimal implementation**

Add to `src/db/models.py`:

```python
class WorkflowExecution(Base):
    """Execution instance of a workflow on a node."""

    __tablename__ = "workflow_executions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    current_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    node: Mapped["Node"] = relationship()
    workflow: Mapped["Workflow"] = relationship()
    current_step: Mapped["WorkflowStep | None"] = relationship()
    step_results: Mapped[list["StepResult"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestWorkflowExecution -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/db/models.py tests/unit/test_models.py
git commit -m "feat: add WorkflowExecution model for tracking provisioning"
```

---

### Task 1.5: Add StepResult Model

**Files:**
- Modify: `src/db/models.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_models.py`:

```python
class TestStepResult:
    """Test StepResult model."""

    def test_step_result_creation(self, test_db):
        """StepResult can be created."""
        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-workflow", os_family="linux")
        test_db.add_all([node, workflow])
        test_db.flush()

        step = WorkflowStep(workflow_id=workflow.id, sequence=1, name="Boot", type="boot")
        test_db.add(step)
        test_db.flush()

        execution = WorkflowExecution(node_id=node.id, workflow_id=workflow.id)
        test_db.add(execution)
        test_db.flush()

        result = StepResult(
            execution_id=execution.id,
            step_id=step.id,
            attempt=1,
            status="running",
        )
        test_db.add(result)
        test_db.flush()

        assert result.id is not None
        assert result.attempt == 1
        assert result.status == "running"

    def test_step_result_with_details(self, test_db):
        """StepResult stores exit code and logs."""
        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-workflow", os_family="linux")
        test_db.add_all([node, workflow])
        test_db.flush()

        step = WorkflowStep(workflow_id=workflow.id, sequence=1, name="Script", type="script")
        execution = WorkflowExecution(node_id=node.id, workflow_id=workflow.id)
        test_db.add_all([step, execution])
        test_db.flush()

        result = StepResult(
            execution_id=execution.id,
            step_id=step.id,
            attempt=1,
            status="failed",
            exit_code=1,
            message="Script failed",
            logs="Error: command not found",
        )
        test_db.add(result)
        test_db.flush()

        assert result.exit_code == 1
        assert result.message == "Script failed"
        assert "command not found" in result.logs
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestStepResult -v`
Expected: FAIL with "StepResult not defined"

**Step 3: Write minimal implementation**

Add to `src/db/models.py`:

```python
class StepResult(Base):
    """Result of executing a workflow step."""

    __tablename__ = "step_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="CASCADE"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    execution: Mapped["WorkflowExecution"] = relationship(back_populates="step_results")
    step: Mapped["WorkflowStep"] = relationship()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_models.py::TestStepResult -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/db/models.py tests/unit/test_models.py
git commit -m "feat: add StepResult model for step execution tracking"
```

---

## Phase 2: Variable Resolver Service

### Task 2.1: Create VariableResolver Service

**Files:**
- Create: `src/core/variable_resolver.py`
- Test: `tests/unit/test_variable_resolver.py`

**Step 1: Write the failing test**

Create `tests/unit/test_variable_resolver.py`:

```python
"""Tests for variable resolver service."""
import pytest

from src.core.variable_resolver import VariableResolver


class TestVariableResolver:
    """Test VariableResolver."""

    def test_resolve_node_variables(self):
        """resolve substitutes node namespace variables."""
        context = {
            "node": {"mac": "aa:bb:cc:dd:ee:ff", "hostname": "server-01"},
        }
        resolver = VariableResolver(context)

        result = resolver.resolve("MAC: ${node.mac}, Host: ${node.hostname}")

        assert result == "MAC: aa:bb:cc:dd:ee:ff, Host: server-01"

    def test_resolve_with_default(self):
        """resolve uses default value when variable is None."""
        context = {"node": {"ip": None}}
        resolver = VariableResolver(context)

        result = resolver.resolve("IP: ${node.ip|dhcp}")

        assert result == "IP: dhcp"

    def test_resolve_missing_keeps_placeholder(self):
        """resolve keeps placeholder for unknown variables."""
        context = {"node": {}}
        resolver = VariableResolver(context)

        result = resolver.resolve("Value: ${node.unknown}")

        assert result == "Value: ${node.unknown}"

    def test_resolve_meta_namespace(self):
        """resolve handles dynamic meta namespace."""
        context = {
            "node": {},
            "meta": {"location": "rack-5", "env": "prod"},
        }
        resolver = VariableResolver(context)

        result = resolver.resolve("Location: ${meta.location}, Env: ${meta.env}")

        assert result == "Location: rack-5, Env: prod"

    def test_list_variables(self):
        """list_variables extracts all variable references."""
        resolver = VariableResolver({})

        vars = resolver.list_variables(
            "MAC=${node.mac} IP=${node.ip|dhcp} URL=${server.url}"
        )

        assert set(vars) == {"node.mac", "node.ip", "server.url"}

    def test_validate_unknown_namespace(self):
        """validate returns errors for unknown namespaces."""
        resolver = VariableResolver({})

        errors = resolver.validate("Value: ${unknown.var}")

        assert len(errors) == 1
        assert "Unknown namespace" in errors[0]
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_variable_resolver.py -v`
Expected: FAIL with "No module named 'src.core.variable_resolver'"

**Step 3: Write minimal implementation**

Create `src/core/variable_resolver.py`:

```python
"""Variable resolution service for templates."""
import re
from typing import Any


KNOWN_NAMESPACES = {
    "node": {"id", "mac", "ip", "hostname", "uuid", "serial", "vendor", "model", "architecture", "boot_mode", "state"},
    "group": {"id", "name", "description"},
    "workflow": {"id", "name", "description"},
    "server": {"url", "tftp_url", "http_url"},
    "template": {"id", "name", "version"},
    "execution": {"id", "step_id", "step_name"},
    "meta": set(),  # Dynamic - any key allowed
    "secret": set(),  # Dynamic - any key allowed
}


class VariableResolver:
    """Resolve template variables from structured namespaces."""

    VARIABLE_PATTERN = re.compile(r'\$\{([a-z]+)\.([a-z_]+)(?:\|([^}]*))?\}')

    def __init__(self, context: dict[str, dict[str, Any]]):
        """Initialize with variable context."""
        self.context = context

    def resolve(self, content: str) -> str:
        """Resolve all ${namespace.key} variables in content."""
        def replace(match: re.Match) -> str:
            namespace, key, default = match.groups()
            ns_context = self.context.get(namespace, {})
            value = ns_context.get(key)
            if value is None:
                return default if default else match.group(0)
            return str(value)

        return self.VARIABLE_PATTERN.sub(replace, content)

    def list_variables(self, content: str) -> list[str]:
        """Extract all variable references."""
        return [f"{m[0]}.{m[1]}" for m in self.VARIABLE_PATTERN.findall(content)]

    def validate(self, content: str) -> list[str]:
        """Return list of validation errors for unknown variables."""
        errors = []
        for namespace, key, _ in self.VARIABLE_PATTERN.findall(content):
            if namespace not in KNOWN_NAMESPACES:
                errors.append(f"Unknown namespace: {namespace}")
            elif namespace not in ("meta", "secret") and key not in KNOWN_NAMESPACES[namespace]:
                errors.append(f"Unknown variable: {namespace}.{key}")
        return errors
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_variable_resolver.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/core/variable_resolver.py tests/unit/test_variable_resolver.py
git commit -m "feat: add VariableResolver service with structured namespaces"
```

---

### Task 2.2: Add Context Builder Helper

**Files:**
- Modify: `src/core/variable_resolver.py`
- Test: `tests/unit/test_variable_resolver.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_variable_resolver.py`:

```python
from src.db.models import Node, Workflow, DeviceGroup


class TestBuildContext:
    """Test context building from models."""

    def test_build_context_from_node(self, test_db):
        """build_context creates context from Node model."""
        node = Node(
            mac_address="aa:bb:cc:dd:ee:ff",
            hostname="server-01",
            ip_address="192.168.1.100",
        )
        test_db.add(node)
        test_db.flush()

        context = build_context(node=node)

        assert context["node"]["mac"] == "aa:bb:cc:dd:ee:ff"
        assert context["node"]["hostname"] == "server-01"
        assert context["node"]["ip"] == "192.168.1.100"

    def test_build_context_with_group(self, test_db):
        """build_context includes group data."""
        group = DeviceGroup(name="production", description="Production servers")
        test_db.add(group)
        test_db.flush()

        node = Node(mac_address="aa:bb:cc:dd:ee:ff", group_id=group.id)
        test_db.add(node)
        test_db.flush()
        test_db.refresh(node)

        context = build_context(node=node)

        assert context["group"]["name"] == "production"
        assert context["group"]["description"] == "Production servers"

    def test_build_context_with_workflow(self, test_db):
        """build_context includes workflow data."""
        workflow = Workflow(name="ubuntu-2404", description="Ubuntu Server", os_family="linux")
        test_db.add(workflow)
        test_db.flush()

        context = build_context(workflow=workflow)

        assert context["workflow"]["name"] == "ubuntu-2404"
        assert context["workflow"]["description"] == "Ubuntu Server"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_variable_resolver.py::TestBuildContext -v`
Expected: FAIL with "cannot import name 'build_context'"

**Step 3: Write minimal implementation**

Add to `src/core/variable_resolver.py`:

```python
from src.db.models import Node, Workflow, WorkflowExecution, DeviceGroup


def build_context(
    node: Node | None = None,
    workflow: Workflow | None = None,
    execution: WorkflowExecution | None = None,
    server_url: str = "",
    tftp_url: str = "",
    http_url: str = "",
    metadata: dict | None = None,
) -> dict[str, dict[str, Any]]:
    """Build variable context from model objects."""
    context: dict[str, dict[str, Any]] = {
        "node": {},
        "group": {},
        "workflow": {},
        "server": {
            "url": server_url,
            "tftp_url": tftp_url,
            "http_url": http_url,
        },
        "execution": {},
        "meta": metadata or {},
    }

    if node:
        context["node"] = {
            "id": node.id,
            "mac": node.mac_address,
            "ip": node.ip_address,
            "hostname": node.hostname,
            "uuid": node.system_uuid,
            "serial": node.serial_number,
            "vendor": node.vendor,
            "model": node.model,
            "architecture": node.arch,
            "boot_mode": node.boot_mode,
            "state": node.state,
        }
        if node.group:
            context["group"] = {
                "id": node.group.id,
                "name": node.group.name,
                "description": node.group.description,
            }

    if workflow:
        context["workflow"] = {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
        }

    if execution:
        context["execution"] = {
            "id": execution.id,
            "step_id": execution.current_step_id,
            "step_name": execution.current_step.name if execution.current_step else None,
        }

    return context
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_variable_resolver.py::TestBuildContext -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/core/variable_resolver.py tests/unit/test_variable_resolver.py
git commit -m "feat: add build_context helper for variable resolution"
```

---

## Phase 3: Template Renderer Service

### Task 3.1: Create TemplateRenderer Service

**Files:**
- Create: `src/core/template_renderer.py`
- Test: `tests/unit/test_template_renderer.py`

**Step 1: Write the failing test**

Create `tests/unit/test_template_renderer.py`:

```python
"""Tests for template renderer service."""
import pytest

from src.core.template_renderer import TemplateRenderer, CircularIncludeError


class TestTemplateRenderer:
    """Test TemplateRenderer."""

    def test_render_simple_template(self):
        """render returns content with variables resolved."""
        async def get_content(name, version):
            return "Hello ${node.hostname}!"

        renderer = TemplateRenderer(get_content)
        context = {"node": {"hostname": "server-01"}}

        result = await_sync(renderer.render("test", None, context))

        assert result == "Hello server-01!"

    def test_render_with_includes(self):
        """render resolves include directives."""
        templates = {
            "main": "Start\n${include:footer}\nEnd",
            "footer": "-- Footer --",
        }

        async def get_content(name, version):
            return templates[name]

        renderer = TemplateRenderer(get_content)

        result = await_sync(renderer.render("main", None, {}))

        assert result == "Start\n-- Footer --\nEnd"

    def test_render_nested_includes(self):
        """render handles nested includes."""
        templates = {
            "main": "${include:level1}",
            "level1": "L1[${include:level2}]",
            "level2": "L2",
        }

        async def get_content(name, version):
            return templates[name]

        renderer = TemplateRenderer(get_content)

        result = await_sync(renderer.render("main", None, {}))

        assert result == "L1[L2]"

    def test_render_circular_include_raises(self):
        """render raises CircularIncludeError for circular includes."""
        templates = {
            "a": "${include:b}",
            "b": "${include:a}",
        }

        async def get_content(name, version):
            return templates[name]

        renderer = TemplateRenderer(get_content)

        with pytest.raises(CircularIncludeError):
            await_sync(renderer.render("a", None, {}))

    def test_render_with_versioned_include(self):
        """render resolves versioned includes."""
        calls = []

        async def get_content(name, version):
            calls.append((name, version))
            return f"Content of {name}:{version}"

        renderer = TemplateRenderer(get_content)

        result = await_sync(renderer.render("main", None, {}, content="${include:base:v2.1}"))

        assert ("base", "v2.1") in calls


def await_sync(coro):
    """Run async function synchronously for tests."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_template_renderer.py -v`
Expected: FAIL with "No module named 'src.core.template_renderer'"

**Step 3: Write minimal implementation**

Create `src/core/template_renderer.py`:

```python
"""Template rendering service with include resolution."""
import re
from typing import Any, Callable, Awaitable

from src.core.variable_resolver import VariableResolver


class CircularIncludeError(Exception):
    """Raised when circular template includes are detected."""
    pass


class MaxIncludeDepthError(Exception):
    """Raised when include depth exceeds maximum."""
    pass


class TemplateRenderer:
    """Render templates with includes and variable substitution."""

    INCLUDE_PATTERN = re.compile(r'\$\{include:([a-zA-Z0-9_-]+)(?::v?(\d+)(?:\.(\d+))?)?\}')
    MAX_INCLUDE_DEPTH = 10

    def __init__(
        self,
        get_content: Callable[[str, str | None], Awaitable[str]],
    ):
        """Initialize with content fetcher function."""
        self._get_content = get_content

    async def render(
        self,
        template_name: str,
        version: str | None,
        context: dict[str, dict[str, Any]],
        content: str | None = None,
    ) -> str:
        """Resolve includes and variables, return final content."""
        if content is None:
            content = await self._get_content(template_name, version)

        content = await self._resolve_includes(content, set())

        resolver = VariableResolver(context)
        content = resolver.resolve(content)

        return content

    async def _resolve_includes(
        self,
        content: str,
        visited: set[str],
        depth: int = 0,
    ) -> str:
        """Recursively resolve ${include:...} references."""
        if depth > self.MAX_INCLUDE_DEPTH:
            raise MaxIncludeDepthError(f"Include depth exceeded {self.MAX_INCLUDE_DEPTH}")

        matches = list(self.INCLUDE_PATTERN.finditer(content))
        if not matches:
            return content

        result = content
        for match in matches:
            template_name, major, minor = match.groups()

            # Build version string
            version = None
            if major and minor:
                version = f"v{major}.{minor}"
            elif major:
                version = f"v{major}"

            ref_key = f"{template_name}:{version}" if version else template_name

            if ref_key in visited:
                raise CircularIncludeError(f"Circular include detected: {ref_key}")

            visited_copy = visited | {ref_key}

            included_content = await self._get_content(template_name, version)
            included_content = await self._resolve_includes(
                included_content, visited_copy, depth + 1
            )

            result = result.replace(match.group(0), included_content)

        return result
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/unit/test_template_renderer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/core/template_renderer.py tests/unit/test_template_renderer.py
git commit -m "feat: add TemplateRenderer service with include resolution"
```

---

## Phase 4: Template Version API

### Task 4.1: Add Template Version Endpoints

**Files:**
- Modify: `src/api/routes/templates.py`
- Test: `tests/integration/test_templates_api.py`

**Step 1: Write the failing test**

Create `tests/integration/test_templates_api.py`:

```python
"""Integration tests for template API."""
import pytest


class TestTemplateVersions:
    """Test template version endpoints."""

    def test_create_first_version(self, client, test_db):
        """POST /templates/{id}/versions creates v1.0 for new template."""
        # Create template first
        response = client.post("/api/v1/templates", json={
            "name": "test-kickstart",
            "type": "kickstart",
            "os_family": "linux",
        })
        template_id = response.json()["data"]["id"]

        # Create first version
        response = client.post(
            f"/api/v1/templates/{template_id}/versions",
            json={"content": "# kickstart config", "commit_message": "Initial version"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["major"] == 1
        assert data["minor"] == 0
        assert data["version_string"] == "v1.0"

    def test_create_minor_version(self, client, test_db):
        """POST /templates/{id}/versions?bump=minor increments minor version."""
        # Create template and first version
        response = client.post("/api/v1/templates", json={
            "name": "test-kickstart",
            "type": "kickstart",
        })
        template_id = response.json()["data"]["id"]

        client.post(f"/api/v1/templates/{template_id}/versions", json={"content": "v1.0"})

        # Create minor version
        response = client.post(
            f"/api/v1/templates/{template_id}/versions?bump=minor",
            json={"content": "v1.1 content"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["version_string"] == "v1.1"

    def test_create_major_version(self, client, test_db):
        """POST /templates/{id}/versions?bump=major increments major version."""
        response = client.post("/api/v1/templates", json={
            "name": "test-kickstart",
            "type": "kickstart",
        })
        template_id = response.json()["data"]["id"]

        client.post(f"/api/v1/templates/{template_id}/versions", json={"content": "v1.0"})

        response = client.post(
            f"/api/v1/templates/{template_id}/versions?bump=major",
            json={"content": "v2.0 content"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["version_string"] == "v2.0"

    def test_list_versions(self, client, test_db):
        """GET /templates/{id}/versions returns all versions."""
        response = client.post("/api/v1/templates", json={
            "name": "test-kickstart",
            "type": "kickstart",
        })
        template_id = response.json()["data"]["id"]

        client.post(f"/api/v1/templates/{template_id}/versions", json={"content": "v1"})
        client.post(f"/api/v1/templates/{template_id}/versions?bump=minor", json={"content": "v2"})

        response = client.get(f"/api/v1/templates/{template_id}/versions")

        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_get_specific_version(self, client, test_db):
        """GET /templates/{id}/versions/v1.0 returns specific version."""
        response = client.post("/api/v1/templates", json={
            "name": "test-kickstart",
            "type": "kickstart",
        })
        template_id = response.json()["data"]["id"]

        client.post(f"/api/v1/templates/{template_id}/versions", json={"content": "Version 1.0 content"})

        response = client.get(f"/api/v1/templates/{template_id}/versions/v1.0")

        assert response.status_code == 200
        assert response.json()["data"]["content"] == "Version 1.0 content"

    def test_get_latest_version(self, client, test_db):
        """GET /templates/{id}/versions/latest returns current version."""
        response = client.post("/api/v1/templates", json={
            "name": "test-kickstart",
            "type": "kickstart",
        })
        template_id = response.json()["data"]["id"]

        client.post(f"/api/v1/templates/{template_id}/versions", json={"content": "v1.0"})
        client.post(f"/api/v1/templates/{template_id}/versions?bump=minor", json={"content": "v1.1 latest"})

        response = client.get(f"/api/v1/templates/{template_id}/versions/latest")

        assert response.status_code == 200
        assert response.json()["data"]["content"] == "v1.1 latest"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/integration/test_templates_api.py -v`
Expected: FAIL with 404 or route not found

**Step 3: Write minimal implementation**

Add to `src/api/routes/templates.py`:

```python
import hashlib
from fastapi import Query


class TemplateVersionCreate(BaseModel):
    """Request body for creating a template version."""
    content: str
    commit_message: str | None = None


class TemplateVersionResponse(BaseModel):
    """Template version response."""
    id: str
    template_id: str
    major: int
    minor: int
    version_string: str
    content: str
    content_hash: str
    size_bytes: int
    commit_message: str | None
    created_at: str


class TemplateVersionListResponse(BaseModel):
    """Response for list of template versions."""
    data: list[TemplateVersionResponse]
    total: int


@router.post("/templates/{template_id}/versions", response_model=ApiResponse, status_code=201)
async def create_template_version(
    template_id: str,
    data: TemplateVersionCreate,
    bump: str = Query("minor", regex="^(minor|major)$"),
    db: AsyncSession = Depends(get_db),
):
    """Create a new template version."""
    from src.db.models import TemplateVersion

    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Get latest version to determine new version numbers
    result = await db.execute(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.major.desc(), TemplateVersion.minor.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    if latest is None:
        major, minor = 1, 0
    elif bump == "major":
        major, minor = latest.major + 1, 0
    else:
        major, minor = latest.major, latest.minor + 1

    content_hash = hashlib.sha256(data.content.encode()).hexdigest()

    version = TemplateVersion(
        template_id=template_id,
        major=major,
        minor=minor,
        content=data.content,
        content_hash=content_hash,
        size_bytes=len(data.content.encode()),
        commit_message=data.commit_message,
    )
    db.add(version)

    # Update template's current version
    template.current_version_id = version.id

    await db.flush()

    return ApiResponse(
        data=TemplateVersionResponse(
            id=version.id,
            template_id=version.template_id,
            major=version.major,
            minor=version.minor,
            version_string=version.version_string,
            content=version.content,
            content_hash=version.content_hash,
            size_bytes=version.size_bytes,
            commit_message=version.commit_message,
            created_at=version.created_at.isoformat(),
        ),
        message=f"Version {version.version_string} created",
    )


@router.get("/templates/{template_id}/versions", response_model=TemplateVersionListResponse)
async def list_template_versions(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all versions of a template."""
    from src.db.models import TemplateVersion

    result = await db.execute(select(Template).where(Template.id == template_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Template not found")

    result = await db.execute(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.major.desc(), TemplateVersion.minor.desc())
    )
    versions = result.scalars().all()

    return TemplateVersionListResponse(
        data=[
            TemplateVersionResponse(
                id=v.id,
                template_id=v.template_id,
                major=v.major,
                minor=v.minor,
                version_string=v.version_string,
                content=v.content,
                content_hash=v.content_hash,
                size_bytes=v.size_bytes,
                commit_message=v.commit_message,
                created_at=v.created_at.isoformat(),
            )
            for v in versions
        ],
        total=len(versions),
    )


@router.get("/templates/{template_id}/versions/{version}", response_model=ApiResponse)
async def get_template_version(
    template_id: str,
    version: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific template version."""
    from src.db.models import TemplateVersion

    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if version == "latest":
        if not template.current_version_id:
            raise HTTPException(status_code=404, detail="No versions exist")
        result = await db.execute(
            select(TemplateVersion).where(TemplateVersion.id == template.current_version_id)
        )
    else:
        # Parse version string like "v1.0" or "v1"
        import re
        match = re.match(r"v?(\d+)(?:\.(\d+))?", version)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid version format")

        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else None

        query = select(TemplateVersion).where(
            TemplateVersion.template_id == template_id,
            TemplateVersion.major == major,
        )
        if minor is not None:
            query = query.where(TemplateVersion.minor == minor)
        else:
            query = query.order_by(TemplateVersion.minor.desc()).limit(1)

        result = await db.execute(query)

    tv = result.scalar_one_or_none()
    if not tv:
        raise HTTPException(status_code=404, detail="Version not found")

    return ApiResponse(
        data=TemplateVersionResponse(
            id=tv.id,
            template_id=tv.template_id,
            major=tv.major,
            minor=tv.minor,
            version_string=tv.version_string,
            content=tv.content,
            content_hash=tv.content_hash,
            size_bytes=tv.size_bytes,
            commit_message=tv.commit_message,
            created_at=tv.created_at.isoformat(),
        )
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/integration/test_templates_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/api/routes/templates.py tests/integration/test_templates_api.py
git commit -m "feat: add template version CRUD API endpoints"
```

---

## Phase 5: Workflow CRUD API

### Task 5.1: Add Workflow CRUD Endpoints

**Files:**
- Modify: `src/api/routes/workflows.py`
- Test: `tests/integration/test_workflows_api.py`

**Step 1: Write the failing test**

Create `tests/integration/test_workflows_api.py`:

```python
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
                {
                    "sequence": 1,
                    "name": "PXE Boot",
                    "type": "boot",
                    "config": {"kernel": "/vmlinuz", "initrd": "/initrd"},
                },
                {
                    "sequence": 2,
                    "name": "Reboot",
                    "type": "reboot",
                    "next_state": "installed",
                },
            ],
        })

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "ubuntu-2404"
        assert len(data["steps"]) == 2

    def test_list_workflows(self, client, test_db):
        """GET /workflows returns all active workflows."""
        client.post("/api/v1/workflows", json={
            "name": "workflow-1", "os_family": "linux", "steps": []
        })
        client.post("/api/v1/workflows", json={
            "name": "workflow-2", "os_family": "windows", "steps": []
        })

        response = client.get("/api/v1/workflows")

        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_list_workflows_filter_os_family(self, client, test_db):
        """GET /workflows?os_family=linux filters by OS family."""
        client.post("/api/v1/workflows", json={
            "name": "linux-wf", "os_family": "linux", "steps": []
        })
        client.post("/api/v1/workflows", json={
            "name": "windows-wf", "os_family": "windows", "steps": []
        })

        response = client.get("/api/v1/workflows?os_family=linux")

        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["data"][0]["os_family"] == "linux"

    def test_get_workflow(self, client, test_db):
        """GET /workflows/{id} returns workflow with steps."""
        create_resp = client.post("/api/v1/workflows", json={
            "name": "test-workflow",
            "os_family": "linux",
            "steps": [{"sequence": 1, "name": "Boot", "type": "boot"}],
        })
        workflow_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/workflows/{workflow_id}")

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "test-workflow"
        assert len(response.json()["data"]["steps"]) == 1

    def test_update_workflow(self, client, test_db):
        """PUT /workflows/{id} updates workflow."""
        create_resp = client.post("/api/v1/workflows", json={
            "name": "test-workflow",
            "os_family": "linux",
            "steps": [],
        })
        workflow_id = create_resp.json()["data"]["id"]

        response = client.put(f"/api/v1/workflows/{workflow_id}", json={
            "name": "updated-workflow",
            "description": "Updated description",
            "os_family": "linux",
            "steps": [{"sequence": 1, "name": "New Step", "type": "boot"}],
        })

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "updated-workflow"
        assert len(response.json()["data"]["steps"]) == 1

    def test_delete_workflow(self, client, test_db):
        """DELETE /workflows/{id} soft deletes workflow."""
        create_resp = client.post("/api/v1/workflows", json={
            "name": "test-workflow",
            "os_family": "linux",
            "steps": [],
        })
        workflow_id = create_resp.json()["data"]["id"]

        response = client.delete(f"/api/v1/workflows/{workflow_id}")

        assert response.status_code == 200

        # Should not appear in list
        list_resp = client.get("/api/v1/workflows")
        assert list_resp.json()["total"] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/integration/test_workflows_api.py -v`
Expected: FAIL with route not found or method not allowed

**Step 3: Write minimal implementation**

Update `src/api/routes/workflows.py` - replace the existing file:

```python
"""Workflow management API endpoints."""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import Workflow, WorkflowStep

router = APIRouter()


# --- Pydantic Schemas ---

class WorkflowStepCreate(BaseModel):
    """Request body for creating a workflow step."""
    sequence: int
    name: str
    type: str
    config: dict = {}
    timeout_seconds: int = 3600
    on_failure: str = "fail"
    max_retries: int = 3
    retry_delay_seconds: int = 30
    next_state: str | None = None


class WorkflowStepResponse(BaseModel):
    """Workflow step response."""
    id: str
    sequence: int
    name: str
    type: str
    config: dict
    timeout_seconds: int
    on_failure: str
    max_retries: int
    retry_delay_seconds: int
    next_state: str | None


class WorkflowCreate(BaseModel):
    """Request body for creating a workflow."""
    name: str
    description: str = ""
    os_family: str
    architecture: str = "x86_64"
    boot_mode: str = "bios"
    steps: list[WorkflowStepCreate] = []


class WorkflowResponse(BaseModel):
    """Workflow response."""
    id: str
    name: str
    description: str
    os_family: str
    architecture: str
    boot_mode: str
    is_active: bool
    steps: list[WorkflowStepResponse]
    created_at: str
    updated_at: str


class WorkflowListResponse(BaseModel):
    """Response for list of workflows."""
    data: list[WorkflowResponse]
    total: int


class ApiResponse(BaseModel):
    """Generic API response."""
    success: bool = True
    message: str | None = None
    data: WorkflowResponse | None = None


def workflow_to_response(workflow: Workflow) -> WorkflowResponse:
    """Convert Workflow model to response."""
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        os_family=workflow.os_family,
        architecture=workflow.architecture,
        boot_mode=workflow.boot_mode,
        is_active=workflow.is_active,
        steps=[
            WorkflowStepResponse(
                id=s.id,
                sequence=s.sequence,
                name=s.name,
                type=s.type,
                config=json.loads(s.config_json) if s.config_json else {},
                timeout_seconds=s.timeout_seconds,
                on_failure=s.on_failure,
                max_retries=s.max_retries,
                retry_delay_seconds=s.retry_delay_seconds,
                next_state=s.next_state,
            )
            for s in workflow.steps
        ],
        created_at=workflow.created_at.isoformat() if workflow.created_at else "",
        updated_at=workflow.updated_at.isoformat() if workflow.updated_at else "",
    )


# --- Endpoints ---

@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    os_family: str | None = Query(None),
    architecture: str | None = Query(None),
    is_active: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """List all workflows with optional filtering."""
    query = select(Workflow).options(selectinload(Workflow.steps))
    query = query.where(Workflow.is_active == is_active)

    if os_family:
        query = query.where(Workflow.os_family == os_family)
    if architecture:
        query = query.where(Workflow.architecture == architecture)

    query = query.order_by(Workflow.name)

    result = await db.execute(query)
    workflows = result.scalars().all()

    return WorkflowListResponse(
        data=[workflow_to_response(w) for w in workflows],
        total=len(workflows),
    )


@router.get("/workflows/{workflow_id}", response_model=ApiResponse)
async def get_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get workflow details by ID."""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.steps))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return ApiResponse(data=workflow_to_response(workflow))


@router.post("/workflows", response_model=ApiResponse, status_code=201)
async def create_workflow(
    data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow."""
    # Check for duplicate name
    existing = await db.execute(select(Workflow).where(Workflow.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Workflow with this name already exists")

    workflow = Workflow(
        name=data.name,
        description=data.description,
        os_family=data.os_family,
        architecture=data.architecture,
        boot_mode=data.boot_mode,
    )
    db.add(workflow)
    await db.flush()

    # Add steps
    for step_data in data.steps:
        step = WorkflowStep(
            workflow_id=workflow.id,
            sequence=step_data.sequence,
            name=step_data.name,
            type=step_data.type,
            config_json=json.dumps(step_data.config),
            timeout_seconds=step_data.timeout_seconds,
            on_failure=step_data.on_failure,
            max_retries=step_data.max_retries,
            retry_delay_seconds=step_data.retry_delay_seconds,
            next_state=step_data.next_state,
        )
        db.add(step)

    await db.flush()
    await db.refresh(workflow, ["steps"])

    return ApiResponse(
        data=workflow_to_response(workflow),
        message="Workflow created successfully",
    )


@router.put("/workflows/{workflow_id}", response_model=ApiResponse)
async def update_workflow(
    workflow_id: str,
    data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    """Update a workflow."""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.steps))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Check name uniqueness if changed
    if data.name != workflow.name:
        existing = await db.execute(select(Workflow).where(Workflow.name == data.name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Workflow with this name already exists")

    workflow.name = data.name
    workflow.description = data.description
    workflow.os_family = data.os_family
    workflow.architecture = data.architecture
    workflow.boot_mode = data.boot_mode

    # Replace steps
    for step in workflow.steps:
        await db.delete(step)

    for step_data in data.steps:
        step = WorkflowStep(
            workflow_id=workflow.id,
            sequence=step_data.sequence,
            name=step_data.name,
            type=step_data.type,
            config_json=json.dumps(step_data.config),
            timeout_seconds=step_data.timeout_seconds,
            on_failure=step_data.on_failure,
            max_retries=step_data.max_retries,
            retry_delay_seconds=step_data.retry_delay_seconds,
            next_state=step_data.next_state,
        )
        db.add(step)

    await db.flush()
    await db.refresh(workflow, ["steps"])

    return ApiResponse(
        data=workflow_to_response(workflow),
        message="Workflow updated successfully",
    )


@router.delete("/workflows/{workflow_id}", response_model=ApiResponse)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Soft delete a workflow."""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.steps))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow.is_active = False
    await db.flush()

    return ApiResponse(
        data=workflow_to_response(workflow),
        message="Workflow deleted successfully",
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/integration/test_workflows_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/api/routes/workflows.py tests/integration/test_workflows_api.py
git commit -m "feat: add workflow CRUD API endpoints with steps"
```

---

## Phase 6: Callback API

### Task 6.1: Add Callback Endpoints

**Files:**
- Create: `src/api/routes/callback.py`
- Modify: `src/main.py` (register router)
- Test: `tests/integration/test_callback_api.py`

**Step 1: Write the failing test**

Create `tests/integration/test_callback_api.py`:

```python
"""Integration tests for callback API."""
import pytest


class TestCallbackAPI:
    """Test callback endpoints for workflow execution."""

    def test_step_callback_success(self, client, test_db):
        """POST /callback/{execution_id}/step/{step_id} records success."""
        # Setup: Create node, workflow, execution
        from src.db.models import Node, Workflow, WorkflowStep, WorkflowExecution
        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-wf", os_family="linux")
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

        response = client.post(
            f"/api/v1/callback/{execution.id}/step/{step.id}",
            json={"status": "success", "message": "Step completed"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_step_callback_with_logs(self, client, test_db):
        """POST /callback records exit code and logs."""
        from src.db.models import Node, Workflow, WorkflowStep, WorkflowExecution
        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-wf", os_family="linux")
        test_db.add_all([node, workflow])
        test_db.flush()

        step = WorkflowStep(workflow_id=workflow.id, sequence=1, name="Script", type="script")
        execution = WorkflowExecution(node_id=node.id, workflow_id=workflow.id, current_step_id=step.id, status="running")
        test_db.add_all([step, execution])
        test_db.flush()

        response = client.post(
            f"/api/v1/callback/{execution.id}/step/{step.id}",
            json={
                "status": "failed",
                "message": "Script error",
                "exit_code": 1,
                "logs": "Error: command not found",
            },
        )

        assert response.status_code == 200

    def test_heartbeat(self, client, test_db):
        """POST /callback/{execution_id}/heartbeat keeps execution alive."""
        from src.db.models import Node, Workflow, WorkflowExecution
        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-wf", os_family="linux")
        test_db.add_all([node, workflow])
        test_db.flush()

        execution = WorkflowExecution(node_id=node.id, workflow_id=workflow.id, status="running")
        test_db.add(execution)
        test_db.flush()

        response = client.post(f"/api/v1/callback/{execution.id}/heartbeat")

        assert response.status_code == 200

    def test_get_current_step(self, client, test_db):
        """GET /callback/{execution_id}/current returns current step config."""
        from src.db.models import Node, Workflow, WorkflowStep, WorkflowExecution
        node = Node(mac_address="aa:bb:cc:dd:ee:ff")
        workflow = Workflow(name="test-wf", os_family="linux")
        test_db.add_all([node, workflow])
        test_db.flush()

        step = WorkflowStep(
            workflow_id=workflow.id,
            sequence=1,
            name="Boot Step",
            type="boot",
            config_json='{"kernel": "/vmlinuz"}',
        )
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

        response = client.get(f"/api/v1/callback/{execution.id}/current")

        assert response.status_code == 200
        assert response.json()["data"]["step_name"] == "Boot Step"
        assert response.json()["data"]["step_type"] == "boot"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/integration/test_callback_api.py -v`
Expected: FAIL with route not found

**Step 3: Write minimal implementation**

Create `src/api/routes/callback.py`:

```python
"""Callback API endpoints for workflow execution agents."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import WorkflowExecution, WorkflowStep, StepResult

router = APIRouter()


class StepCallbackRequest(BaseModel):
    """Request body for step callback."""
    status: str  # success, failed, progress
    message: str | None = None
    exit_code: int | None = None
    logs: str | None = None
    progress_percent: int | None = None


class CurrentStepResponse(BaseModel):
    """Response for current step info."""
    execution_id: str
    step_id: str
    step_name: str
    step_type: str
    step_config: dict


class ApiResponse(BaseModel):
    """Generic API response."""
    success: bool = True
    message: str | None = None
    data: dict | CurrentStepResponse | None = None


@router.post("/callback/{execution_id}/step/{step_id}", response_model=ApiResponse)
async def step_callback(
    execution_id: str,
    step_id: str,
    data: StepCallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Process callback from node agent for step status."""
    result = await db.execute(
        select(WorkflowExecution)
        .options(selectinload(WorkflowExecution.current_step))
        .where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.current_step_id != step_id:
        raise HTTPException(status_code=400, detail="Step ID does not match current step")

    # Find or create step result
    result = await db.execute(
        select(StepResult)
        .where(StepResult.execution_id == execution_id)
        .where(StepResult.step_id == step_id)
        .order_by(StepResult.attempt.desc())
        .limit(1)
    )
    step_result = result.scalar_one_or_none()

    if not step_result:
        step_result = StepResult(
            execution_id=execution_id,
            step_id=step_id,
            attempt=1,
            status=data.status,
        )
        db.add(step_result)
    else:
        step_result.status = data.status

    step_result.message = data.message
    step_result.exit_code = data.exit_code
    step_result.logs = data.logs

    if data.status in ("success", "failed"):
        step_result.completed_at = datetime.utcnow()

    await db.flush()

    return ApiResponse(
        success=True,
        message=f"Step status updated to {data.status}",
    )


@router.post("/callback/{execution_id}/heartbeat", response_model=ApiResponse)
async def heartbeat(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Heartbeat to keep execution from timing out."""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # In a full implementation, this would reset a timeout timer
    return ApiResponse(success=True, message="Heartbeat received")


@router.get("/callback/{execution_id}/current", response_model=ApiResponse)
async def get_current_step(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get current step configuration for the agent."""
    result = await db.execute(
        select(WorkflowExecution)
        .options(selectinload(WorkflowExecution.current_step))
        .where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if not execution.current_step:
        raise HTTPException(status_code=404, detail="No current step")

    step = execution.current_step
    return ApiResponse(
        data=CurrentStepResponse(
            execution_id=execution.id,
            step_id=step.id,
            step_name=step.name,
            step_type=step.type,
            step_config=json.loads(step.config_json) if step.config_json else {},
        )
    )
```

Register the router in `src/main.py`:

```python
# Add import
from src.api.routes.callback import router as callback_router

# Add router registration (after other routers)
app.include_router(callback_router, prefix="/api/v1", tags=["callback"])
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kali/Desktop/PureBoot/PureBoot && python -m pytest tests/integration/test_callback_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/kali/Desktop/PureBoot/PureBoot
git add src/api/routes/callback.py src/main.py tests/integration/test_callback_api.py
git commit -m "feat: add callback API for workflow execution agents"
```

---

## Summary

This implementation plan covers:

1. **Phase 1**: Database models (TemplateVersion, Workflow, WorkflowStep, WorkflowExecution, StepResult)
2. **Phase 2**: Variable resolver service with structured namespaces
3. **Phase 3**: Template renderer with include resolution
4. **Phase 4**: Template version API endpoints
5. **Phase 5**: Workflow CRUD API endpoints
6. **Phase 6**: Callback API for execution agents

**Total Tasks**: 11 tasks across 6 phases

Each task follows TDD: write failing test → implement → verify → commit.

**Next Steps** (not in this plan):
- Workflow orchestrator service (step advancement logic)
- YAML import/export endpoints
- Timeout scheduler integration
- Callback agent scripts (Linux/Windows)