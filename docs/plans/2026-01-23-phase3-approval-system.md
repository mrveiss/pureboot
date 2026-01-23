# Phase 3: Approval System - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement configurable approval rules with async queue, voting, and escalation for the four-eye principle.

**Architecture:** ApprovalRule defines when approval is required (by device group, user group, or global). When a user performs a gated operation, an ApprovalRequest is created. Approvers vote until threshold is met, then the operation executes. A background job handles escalation timeouts.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Pydantic 2.x, APScheduler, React 18, TypeScript, Zustand, TailwindCSS

---

## Task 1: Add ApprovalRule Model

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add ApprovalRule model after ApprovalVote**

Add at the end of models.py (before any relationships that might reference it):

```python
class ApprovalRule(Base):
    """Configuration for when approval is required."""

    __tablename__ = "approval_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    # Scope: what this rule applies to
    scope_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # device_group, user_group, global
    scope_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # FK to device_groups or user_groups (null for global)

    # Operations this rule covers (JSON array)
    operations_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # ["state_transition", "node_delete", "bulk_operation", ...]

    # Approval requirements
    required_approvers: Mapped[int] = mapped_column(default=1)  # 1 = four-eye (requester + 1)
    escalation_timeout_hours: Mapped[int] = mapped_column(default=72)
    escalation_role_id: Mapped[str | None] = mapped_column(
        ForeignKey("roles.id"), nullable=True
    )

    # Status
    is_active: Mapped[bool] = mapped_column(default=True)
    priority: Mapped[int] = mapped_column(default=0)  # Higher = more important

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    escalation_role: Mapped["Role | None"] = relationship()
```

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat(approval): add ApprovalRule model"
```

---

## Task 2: Enhance Approval Model with Target and Escalation

**Files:**
- Modify: `src/db/models.py`

**Step 1: Update Approval model**

Replace the existing Approval class with enhanced version:

```python
class Approval(Base):
    """Approval request for four-eye principle operations."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Operation details
    operation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # state_transition, node_delete, bulk_operation, config_change, user_management
    operation_payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Target resource
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # node, group, user, system
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Requester
    requester_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    requester: Mapped["User"] = relationship(foreign_keys=[requester_id])

    # Status and voting
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, approved, rejected, escalated, expired, cancelled
    required_approvals: Mapped[int] = mapped_column(default=1)
    current_approvals: Mapped[int] = mapped_column(default=0)

    # Rule that triggered this (for reference)
    rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_rules.id"), nullable=True
    )
    rule: Mapped["ApprovalRule | None"] = relationship()

    # Escalation
    escalation_timeout_hours: Mapped[int] = mapped_column(default=72)
    escalated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Resolution
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    resolved_by: Mapped["User | None"] = relationship(foreign_keys=[resolved_by_id])

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    # Relationships
    votes: Mapped[list["ApprovalVote"]] = relationship(
        back_populates="approval", cascade="all, delete-orphan"
    )
```

**Step 2: Update ApprovalVote to use proper FK**

```python
class ApprovalVote(Base):
    """Vote on an approval request."""

    __tablename__ = "approval_votes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Voter
    approver_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    approver: Mapped["User"] = relationship()

    # Vote
    decision: Mapped[str] = mapped_column(String(10), nullable=False)  # approve, reject
    comment: Mapped[str | None] = mapped_column(Text)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationship
    approval: Mapped["Approval"] = relationship(back_populates="votes")

    __table_args__ = (
        UniqueConstraint("approval_id", "approver_id", name="uq_approval_vote_user"),
    )
```

**Step 3: Commit**

```bash
git add src/db/models.py
git commit -m "feat(approval): enhance Approval model with target and escalation"
```

---

## Task 3: Create Approval Service

**Files:**
- Create: `src/services/approval.py`

**Step 1: Create approval checking and execution service**

```python
"""Approval system service for checking rules and executing approved operations."""
import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import (
    Approval, ApprovalVote, ApprovalRule, User, UserGroup,
    UserGroupMember, Node, DeviceGroup
)


# Operation types that can require approval
APPROVAL_OPERATIONS = {
    "state_transition": "Node state transitions",
    "node_delete": "Node deletion",
    "bulk_operation": "Bulk operations on multiple nodes",
    "config_change": "System configuration changes",
    "user_management": "User and role management",
}


async def check_approval_required(
    db: AsyncSession,
    user: User,
    operation_type: str,
    target_type: str,
    target_id: str | None = None,
) -> ApprovalRule | None:
    """
    Check if an operation requires approval based on rules.

    Returns the matching ApprovalRule if approval is required, None otherwise.
    """
    # Get user's groups
    user_group_ids = []
    result = await db.execute(
        select(UserGroupMember.user_group_id).where(
            UserGroupMember.user_id == user.id
        )
    )
    user_group_ids = [r[0] for r in result.all()]

    # Get device group if target is a node
    device_group_id = None
    if target_type == "node" and target_id:
        result = await db.execute(
            select(Node.group_id).where(Node.id == target_id)
        )
        row = result.first()
        if row:
            device_group_id = row[0]

    # Build query for matching rules (highest priority first)
    # Rules match if:
    # 1. Global scope, OR
    # 2. Device group scope matching target's device group, OR
    # 3. User group scope matching user's groups
    # AND operation_type is in the rule's operations list

    result = await db.execute(
        select(ApprovalRule)
        .where(
            ApprovalRule.is_active == True,
            or_(
                ApprovalRule.scope_type == "global",
                and_(
                    ApprovalRule.scope_type == "device_group",
                    ApprovalRule.scope_id == device_group_id
                ),
                and_(
                    ApprovalRule.scope_type == "user_group",
                    ApprovalRule.scope_id.in_(user_group_ids) if user_group_ids else False
                ),
            )
        )
        .order_by(ApprovalRule.priority.desc())
    )
    rules = result.scalars().all()

    # Check each rule for operation match
    for rule in rules:
        operations = json.loads(rule.operations_json)
        if operation_type in operations:
            return rule

    return None


async def create_approval_request(
    db: AsyncSession,
    user: User,
    rule: ApprovalRule,
    operation_type: str,
    operation_payload: dict[str, Any],
    target_type: str,
    target_id: str | None,
    target_name: str | None,
) -> Approval:
    """Create a new approval request."""
    expires_at = datetime.utcnow() + timedelta(hours=rule.escalation_timeout_hours * 2)

    approval = Approval(
        operation_type=operation_type,
        operation_payload_json=json.dumps(operation_payload),
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        requester_id=user.id,
        required_approvals=rule.required_approvers,
        rule_id=rule.id,
        escalation_timeout_hours=rule.escalation_timeout_hours,
        expires_at=expires_at,
    )
    db.add(approval)
    await db.flush()
    await db.refresh(approval)
    return approval


async def cast_vote(
    db: AsyncSession,
    approval_id: str,
    user: User,
    decision: str,
    comment: str | None = None,
) -> tuple[ApprovalVote, Approval]:
    """
    Cast a vote on an approval request.

    Returns tuple of (vote, updated_approval).
    Raises ValueError if user cannot vote or already voted.
    """
    # Get approval with votes
    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.votes))
        .where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise ValueError("Approval request not found")

    if approval.status not in ("pending", "escalated"):
        raise ValueError(f"Cannot vote on {approval.status} request")

    if approval.requester_id == user.id:
        raise ValueError("Cannot vote on your own request")

    # Check if already voted
    for vote in approval.votes:
        if vote.approver_id == user.id:
            raise ValueError("You have already voted on this request")

    # Create vote
    vote = ApprovalVote(
        approval_id=approval_id,
        approver_id=user.id,
        decision=decision,
        comment=comment,
    )
    db.add(vote)

    # Update approval counts and status
    if decision == "approve":
        approval.current_approvals += 1
        if approval.current_approvals >= approval.required_approvals:
            approval.status = "approved"
            approval.resolved_at = datetime.utcnow()
            approval.resolved_by_id = user.id
    elif decision == "reject":
        approval.status = "rejected"
        approval.resolved_at = datetime.utcnow()
        approval.resolved_by_id = user.id

    await db.flush()
    await db.refresh(vote)
    await db.refresh(approval)
    return vote, approval


async def get_pending_approvals_for_user(
    db: AsyncSession,
    user: User,
) -> list[Approval]:
    """Get pending approvals that the user can vote on."""
    # For now, admins can vote on all, others based on access
    # TODO: Implement proper access checking based on target

    result = await db.execute(
        select(Approval)
        .options(
            selectinload(Approval.votes),
            selectinload(Approval.requester),
        )
        .where(
            Approval.status.in_(["pending", "escalated"]),
            Approval.requester_id != user.id,  # Can't vote on own requests
        )
        .order_by(Approval.created_at.desc())
    )
    return list(result.scalars().all())


async def execute_approved_operation(
    db: AsyncSession,
    approval: Approval,
) -> dict[str, Any]:
    """
    Execute an approved operation.

    Returns result dict with success status and message.
    """
    if approval.status != "approved":
        return {"success": False, "error": "Operation not approved"}

    payload = json.loads(approval.operation_payload_json)

    # Route to appropriate executor based on operation type
    # This is a placeholder - actual execution would call the relevant service
    result = {
        "success": True,
        "message": f"Executed {approval.operation_type} on {approval.target_type}",
        "operation_type": approval.operation_type,
        "target_type": approval.target_type,
        "target_id": approval.target_id,
        "payload": payload,
    }

    return result


async def process_escalations(db: AsyncSession) -> int:
    """
    Process pending approvals that have exceeded escalation timeout.

    Returns count of escalated approvals.
    """
    cutoff = datetime.utcnow()
    escalation_cutoff = cutoff - timedelta(hours=1)  # Check each hour

    result = await db.execute(
        select(Approval)
        .options(selectinload(Approval.rule))
        .where(
            Approval.status == "pending",
            Approval.escalated_at.is_(None),
            Approval.created_at < escalation_cutoff,
        )
    )
    approvals = result.scalars().all()

    escalated_count = 0
    for approval in approvals:
        hours_elapsed = (cutoff - approval.created_at).total_seconds() / 3600
        if hours_elapsed >= approval.escalation_timeout_hours:
            approval.status = "escalated"
            approval.escalated_at = cutoff
            escalated_count += 1
            # TODO: Send notification to escalation role

    if escalated_count > 0:
        await db.commit()

    return escalated_count


async def cancel_approval(
    db: AsyncSession,
    approval_id: str,
    user: User,
) -> Approval:
    """Cancel an approval request (only requester or admin can cancel)."""
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise ValueError("Approval request not found")

    if approval.status not in ("pending", "escalated"):
        raise ValueError(f"Cannot cancel {approval.status} request")

    # Only requester or admin can cancel
    if approval.requester_id != user.id and user.role != "admin":
        raise ValueError("You can only cancel your own requests")

    approval.status = "cancelled"
    approval.resolved_at = datetime.utcnow()
    approval.resolved_by_id = user.id

    await db.flush()
    await db.refresh(approval)
    return approval
```

**Step 2: Create services __init__.py if needed**

```bash
mkdir -p src/services
touch src/services/__init__.py
```

**Step 3: Commit**

```bash
git add src/services/
git commit -m "feat(approval): add approval checking and execution service"
```

---

## Task 4: Create Approval Rules API Routes

**Files:**
- Create: `src/api/routes/approval_rules.py`

**Step 1: Create approval rules routes**

```python
"""Approval rules management API routes."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import ApprovalRule, Role, User
from src.api.dependencies.auth import require_permission


router = APIRouter(prefix="/approval-rules", tags=["approval-rules"])


class ApprovalRuleCreate(BaseModel):
    name: str
    description: str | None = None
    scope_type: str  # device_group, user_group, global
    scope_id: str | None = None
    operations: list[str]  # state_transition, node_delete, etc.
    required_approvers: int = 1
    escalation_timeout_hours: int = 72
    escalation_role_id: str | None = None
    priority: int = 0


class ApprovalRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    operations: list[str] | None = None
    required_approvers: int | None = None
    escalation_timeout_hours: int | None = None
    escalation_role_id: str | None = None
    is_active: bool | None = None
    priority: int | None = None


class ApprovalRuleResponse(BaseModel):
    id: str
    name: str
    description: str | None
    scope_type: str
    scope_id: str | None
    operations: list[str]
    required_approvers: int
    escalation_timeout_hours: int
    escalation_role_id: str | None
    escalation_role_name: str | None
    is_active: bool
    priority: int
    created_at: str

    class Config:
        from_attributes = True


@router.get("")
async def list_approval_rules(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval", "read")),
) -> list[ApprovalRuleResponse]:
    """List all approval rules."""
    result = await db.execute(
        select(ApprovalRule)
        .options(selectinload(ApprovalRule.escalation_role))
        .order_by(ApprovalRule.priority.desc(), ApprovalRule.name)
    )
    rules = result.scalars().all()

    return [
        ApprovalRuleResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            scope_type=r.scope_type,
            scope_id=r.scope_id,
            operations=json.loads(r.operations_json),
            required_approvers=r.required_approvers,
            escalation_timeout_hours=r.escalation_timeout_hours,
            escalation_role_id=r.escalation_role_id,
            escalation_role_name=r.escalation_role.name if r.escalation_role else None,
            is_active=r.is_active,
            priority=r.priority,
            created_at=r.created_at.isoformat(),
        )
        for r in rules
    ]


@router.post("")
async def create_approval_rule(
    data: ApprovalRuleCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval", "manage")),
) -> ApprovalRuleResponse:
    """Create a new approval rule."""
    # Validate scope_type
    if data.scope_type not in ("device_group", "user_group", "global"):
        raise HTTPException(status_code=400, detail="Invalid scope_type")

    if data.scope_type != "global" and not data.scope_id:
        raise HTTPException(status_code=400, detail="scope_id required for non-global rules")

    # Check for duplicate name
    result = await db.execute(
        select(ApprovalRule).where(ApprovalRule.name == data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Rule name already exists")

    # Validate escalation role if provided
    escalation_role = None
    if data.escalation_role_id:
        result = await db.execute(
            select(Role).where(Role.id == data.escalation_role_id)
        )
        escalation_role = result.scalar_one_or_none()
        if not escalation_role:
            raise HTTPException(status_code=400, detail="Invalid escalation_role_id")

    rule = ApprovalRule(
        name=data.name,
        description=data.description,
        scope_type=data.scope_type,
        scope_id=data.scope_id if data.scope_type != "global" else None,
        operations_json=json.dumps(data.operations),
        required_approvers=data.required_approvers,
        escalation_timeout_hours=data.escalation_timeout_hours,
        escalation_role_id=data.escalation_role_id,
        priority=data.priority,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    return ApprovalRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        scope_type=rule.scope_type,
        scope_id=rule.scope_id,
        operations=data.operations,
        required_approvers=rule.required_approvers,
        escalation_timeout_hours=rule.escalation_timeout_hours,
        escalation_role_id=rule.escalation_role_id,
        escalation_role_name=escalation_role.name if escalation_role else None,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at.isoformat(),
    )


@router.get("/{rule_id}")
async def get_approval_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval", "read")),
) -> ApprovalRuleResponse:
    """Get approval rule details."""
    result = await db.execute(
        select(ApprovalRule)
        .options(selectinload(ApprovalRule.escalation_role))
        .where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Approval rule not found")

    return ApprovalRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        scope_type=rule.scope_type,
        scope_id=rule.scope_id,
        operations=json.loads(rule.operations_json),
        required_approvers=rule.required_approvers,
        escalation_timeout_hours=rule.escalation_timeout_hours,
        escalation_role_id=rule.escalation_role_id,
        escalation_role_name=rule.escalation_role.name if rule.escalation_role else None,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at.isoformat(),
    )


@router.patch("/{rule_id}")
async def update_approval_rule(
    rule_id: str,
    data: ApprovalRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval", "manage")),
) -> ApprovalRuleResponse:
    """Update an approval rule."""
    result = await db.execute(
        select(ApprovalRule)
        .options(selectinload(ApprovalRule.escalation_role))
        .where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Approval rule not found")

    if data.name is not None:
        # Check for duplicate
        existing = await db.execute(
            select(ApprovalRule).where(
                ApprovalRule.name == data.name,
                ApprovalRule.id != rule_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Rule name already exists")
        rule.name = data.name

    if data.description is not None:
        rule.description = data.description

    if data.operations is not None:
        rule.operations_json = json.dumps(data.operations)

    if data.required_approvers is not None:
        rule.required_approvers = data.required_approvers

    if data.escalation_timeout_hours is not None:
        rule.escalation_timeout_hours = data.escalation_timeout_hours

    if data.escalation_role_id is not None:
        # Validate role
        role_result = await db.execute(
            select(Role).where(Role.id == data.escalation_role_id)
        )
        if not role_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid escalation_role_id")
        rule.escalation_role_id = data.escalation_role_id

    if data.is_active is not None:
        rule.is_active = data.is_active

    if data.priority is not None:
        rule.priority = data.priority

    await db.commit()
    await db.refresh(rule)

    # Reload with relationship
    result = await db.execute(
        select(ApprovalRule)
        .options(selectinload(ApprovalRule.escalation_role))
        .where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one()

    return ApprovalRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        scope_type=rule.scope_type,
        scope_id=rule.scope_id,
        operations=json.loads(rule.operations_json),
        required_approvers=rule.required_approvers,
        escalation_timeout_hours=rule.escalation_timeout_hours,
        escalation_role_id=rule.escalation_role_id,
        escalation_role_name=rule.escalation_role.name if rule.escalation_role else None,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at.isoformat(),
    )


@router.delete("/{rule_id}")
async def delete_approval_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval", "manage")),
) -> dict:
    """Delete an approval rule."""
    result = await db.execute(
        select(ApprovalRule).where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Approval rule not found")

    await db.delete(rule)
    await db.commit()

    return {"success": True, "message": "Approval rule deleted"}
```

**Step 2: Commit**

```bash
git add src/api/routes/approval_rules.py
git commit -m "feat(approval): add approval rules API routes"
```

---

## Task 5: Update Approvals API Routes

**Files:**
- Modify: `src/api/routes/approvals.py`

**Step 1: Read the existing file and update it**

The file should be updated to use the new service and models. Key endpoints:
- GET /approvals - List approvals (with filters for status, user)
- GET /approvals/pending - Pending approvals user can vote on
- GET /approvals/my-requests - User's own requests
- POST /approvals/{id}/vote - Cast a vote
- POST /approvals/{id}/cancel - Cancel own request
- GET /approvals/{id} - Get approval details

**Step 2: Commit**

```bash
git add src/api/routes/approvals.py
git commit -m "feat(approval): update approvals API with voting and cancellation"
```

---

## Task 6: Register New Routes

**Files:**
- Modify: `src/main.py`

**Step 1: Add imports and register approval_rules router**

Add import:
```python
from src.api.routes.approval_rules import router as approval_rules_router
```

Add route registration:
```python
app.include_router(approval_rules_router, prefix="/api/v1", tags=["approval-rules"])
```

**Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat(approval): register approval rules routes"
```

---

## Task 7: Add Escalation Background Job

**Files:**
- Modify: `src/core/scheduler.py` or create `src/core/jobs/escalation.py`

**Step 1: Add escalation job to scheduler**

The job should run periodically (every hour) to check for approvals that need escalation.

```python
async def process_approval_escalations():
    """Background job to process approval escalations."""
    from src.db.database import async_session_factory
    from src.services.approval import process_escalations

    if not async_session_factory:
        return

    async with async_session_factory() as db:
        count = await process_escalations(db)
        if count > 0:
            logger.info(f"Escalated {count} approval requests")
```

**Step 2: Register job in scheduler startup**

**Step 3: Commit**

```bash
git add src/core/
git commit -m "feat(approval): add escalation background job"
```

---

## Task 8: Create Frontend Approval Types

**Files:**
- Modify: `frontend/src/types/approval.ts`

**Step 1: Add/update types**

```typescript
export interface ApprovalRule {
  id: string
  name: string
  description: string | null
  scope_type: 'device_group' | 'user_group' | 'global'
  scope_id: string | null
  operations: string[]
  required_approvers: number
  escalation_timeout_hours: number
  escalation_role_id: string | null
  escalation_role_name: string | null
  is_active: boolean
  priority: number
  created_at: string
}

export interface ApprovalVote {
  id: string
  approver_id: string
  approver_username: string
  decision: 'approve' | 'reject'
  comment: string | null
  created_at: string
}

export interface ApprovalRequest {
  id: string
  operation_type: string
  operation_payload: Record<string, unknown>
  target_type: string
  target_id: string | null
  target_name: string | null
  requester_id: string
  requester_username: string
  status: 'pending' | 'approved' | 'rejected' | 'escalated' | 'expired' | 'cancelled'
  required_approvals: number
  current_approvals: number
  escalation_timeout_hours: number
  escalated_at: string | null
  resolved_at: string | null
  created_at: string
  expires_at: string
  votes: ApprovalVote[]
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/approval.ts
git commit -m "feat(ui): update approval types for new system"
```

---

## Task 9: Create Approval Rules API Client

**Files:**
- Create: `frontend/src/api/approvalRules.ts`

**Step 1: Create API client**

```typescript
import { apiClient } from './client'
import type { ApprovalRule } from '@/types'

export const approvalRulesApi = {
  async list(): Promise<ApprovalRule[]> {
    return apiClient.get<ApprovalRule[]>('/approval-rules')
  },

  async get(id: string): Promise<ApprovalRule> {
    return apiClient.get<ApprovalRule>(`/approval-rules/${id}`)
  },

  async create(data: {
    name: string
    description?: string
    scope_type: string
    scope_id?: string
    operations: string[]
    required_approvers?: number
    escalation_timeout_hours?: number
    escalation_role_id?: string
    priority?: number
  }): Promise<ApprovalRule> {
    return apiClient.post<ApprovalRule>('/approval-rules', data)
  },

  async update(
    id: string,
    data: {
      name?: string
      description?: string
      operations?: string[]
      required_approvers?: number
      escalation_timeout_hours?: number
      escalation_role_id?: string
      is_active?: boolean
      priority?: number
    }
  ): Promise<ApprovalRule> {
    return apiClient.patch<ApprovalRule>(`/approval-rules/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/approval-rules/${id}`)
  },
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/approvalRules.ts
git commit -m "feat(ui): add approval rules API client"
```

---

## Task 10: Create Approval Rules Page

**Files:**
- Create: `frontend/src/pages/ApprovalRules.tsx`

**Step 1: Create the page**

A page that lists approval rules with:
- Name, scope, operations list
- Required approvers, escalation timeout
- Active/inactive status badge
- Edit/delete buttons for management

**Step 2: Commit**

```bash
git add frontend/src/pages/ApprovalRules.tsx
git commit -m "feat(ui): add Approval Rules management page"
```

---

## Task 11: Update Approvals Page with Voting

**Files:**
- Modify: `frontend/src/pages/Approvals.tsx`

**Step 1: Update to support voting**

- Show pending approvals user can vote on
- Vote buttons (Approve/Reject) with comment modal
- Show vote history
- Tabs for "Pending", "My Requests", "All"

**Step 2: Commit**

```bash
git add frontend/src/pages/Approvals.tsx
git commit -m "feat(ui): enhance Approvals page with voting"
```

---

## Task 12: Update Router and Navigation

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Step 1: Add approval-rules route**

**Step 2: Update sidebar navigation**

**Step 3: Commit**

```bash
git add frontend/src/router.tsx frontend/src/pages/index.ts frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(ui): add approval rules route and navigation"
```

---

## Task 13: Final Push

**Step 1: Review all changes**

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat
```

**Step 2: Push branch**

```bash
git push origin feature/issue-8-rbac-audit-logging
```

---

## Summary

This plan implements Phase 3 of the RBAC system:

| Component | Status |
|-----------|--------|
| ApprovalRule model | New |
| Enhanced Approval model | Modified |
| Enhanced ApprovalVote model | Modified |
| Approval service | New |
| Approval rules API routes | New |
| Updated approvals API routes | Modified |
| Escalation background job | New |
| Frontend approval types | Modified |
| Approval rules API client | New |
| Approval Rules page | New |
| Enhanced Approvals page | Modified |
| Router and navigation | Modified |

**Next Phase:** Phase 4 will implement Audit Logging (DB + file + SIEM) and LDAP/AD integration.
