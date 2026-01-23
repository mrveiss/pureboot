"""Approval rules management API routes."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import ApprovalRule, User
from src.api.dependencies.auth import require_permission


router = APIRouter(prefix="/approval-rules", tags=["approval-rules"])


class ApprovalRuleCreate(BaseModel):
    name: str
    scope_type: str  # "device_group", "user_group", "global"
    scope_id: str | None = None
    operations: list[str]  # List of operation types
    required_approvers: int = 1
    escalation_timeout_hours: int = 72
    escalation_role_id: str | None = None
    is_active: bool = True
    priority: int = 0


class ApprovalRuleUpdate(BaseModel):
    name: str | None = None
    scope_type: str | None = None
    scope_id: str | None = None
    operations: list[str] | None = None
    required_approvers: int | None = None
    escalation_timeout_hours: int | None = None
    escalation_role_id: str | None = None
    is_active: bool | None = None
    priority: int | None = None


class ApprovalRuleResponse(BaseModel):
    id: str
    name: str
    scope_type: str
    scope_id: str | None
    operations: list[str]
    required_approvers: int
    escalation_timeout_hours: int
    escalation_role_id: str | None
    is_active: bool
    priority: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


def rule_to_response(rule: ApprovalRule) -> dict:
    """Convert ApprovalRule model to response dict with operations as list."""
    return {
        "id": rule.id,
        "name": rule.name,
        "scope_type": rule.scope_type,
        "scope_id": rule.scope_id,
        "operations": json.loads(rule.operations_json),
        "required_approvers": rule.required_approvers,
        "escalation_timeout_hours": rule.escalation_timeout_hours,
        "escalation_role_id": rule.escalation_role_id,
        "is_active": rule.is_active,
        "priority": rule.priority,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }


@router.get("")
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval_rule", "read")),
) -> list[ApprovalRuleResponse]:
    """List all approval rules ordered by priority (highest first)."""
    result = await db.execute(
        select(ApprovalRule).order_by(ApprovalRule.priority.desc(), ApprovalRule.name)
    )
    rules = result.scalars().all()

    return [rule_to_response(r) for r in rules]


@router.get("/{rule_id}")
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval_rule", "read")),
) -> ApprovalRuleResponse:
    """Get a specific approval rule by ID."""
    result = await db.execute(
        select(ApprovalRule).where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Approval rule not found")

    return rule_to_response(rule)


@router.post("", status_code=201)
async def create_rule(
    data: ApprovalRuleCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval_rule", "create")),
) -> ApprovalRuleResponse:
    """Create a new approval rule."""
    # Validate scope_type
    valid_scope_types = ("device_group", "user_group", "global")
    if data.scope_type not in valid_scope_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope_type. Must be one of: {', '.join(valid_scope_types)}",
        )

    # Check for duplicate name
    result = await db.execute(
        select(ApprovalRule).where(ApprovalRule.name == data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Approval rule name already exists")

    # Create the rule
    rule = ApprovalRule(
        name=data.name,
        scope_type=data.scope_type,
        scope_id=data.scope_id,
        operations_json=json.dumps(data.operations),
        required_approvers=data.required_approvers,
        escalation_timeout_hours=data.escalation_timeout_hours,
        escalation_role_id=data.escalation_role_id,
        is_active=data.is_active,
        priority=data.priority,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    return rule_to_response(rule)


@router.patch("/{rule_id}")
async def update_rule(
    rule_id: str,
    data: ApprovalRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval_rule", "update")),
) -> ApprovalRuleResponse:
    """Update an existing approval rule."""
    result = await db.execute(
        select(ApprovalRule).where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Approval rule not found")

    # Validate scope_type if provided
    if data.scope_type is not None:
        valid_scope_types = ("device_group", "user_group", "global")
        if data.scope_type not in valid_scope_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scope_type. Must be one of: {', '.join(valid_scope_types)}",
            )
        rule.scope_type = data.scope_type

    # Check for duplicate name if updating
    if data.name is not None:
        existing = await db.execute(
            select(ApprovalRule).where(
                ApprovalRule.name == data.name, ApprovalRule.id != rule_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400, detail="Approval rule name already exists"
            )
        rule.name = data.name

    if data.scope_id is not None:
        rule.scope_id = data.scope_id

    if data.operations is not None:
        rule.operations_json = json.dumps(data.operations)

    if data.required_approvers is not None:
        rule.required_approvers = data.required_approvers

    if data.escalation_timeout_hours is not None:
        rule.escalation_timeout_hours = data.escalation_timeout_hours

    if data.escalation_role_id is not None:
        rule.escalation_role_id = data.escalation_role_id

    if data.is_active is not None:
        rule.is_active = data.is_active

    if data.priority is not None:
        rule.priority = data.priority

    await db.commit()
    await db.refresh(rule)

    return rule_to_response(rule)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("approval_rule", "delete")),
) -> None:
    """Delete an approval rule."""
    result = await db.execute(
        select(ApprovalRule).where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Approval rule not found")

    await db.delete(rule)
    await db.commit()
