"""Audit log API routes."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies.auth import require_permission
from src.db.database import get_db
from src.db.models import AuditLog, User


router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    """Response model for a single audit log entry."""

    id: str
    timestamp: str
    actor_id: str | None
    actor_type: str
    actor_username: str
    actor_ip: str | None
    action: str
    resource_type: str
    resource_id: str | None
    resource_name: str | None
    details: dict | None
    result: str
    error_message: str | None
    session_id: str | None
    auth_method: str | None


class AuditLogListResponse(BaseModel):
    """Response model for paginated audit log list."""

    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


def audit_to_response(log: AuditLog) -> dict:
    """Convert AuditLog model to response dictionary."""
    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat(),
        "actor_id": log.actor_id,
        "actor_type": log.actor_type,
        "actor_username": log.actor_username,
        "actor_ip": log.actor_ip,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "resource_name": log.resource_name,
        "details": json.loads(log.details_json) if log.details_json else None,
        "result": log.result,
        "error_message": log.error_message,
        "session_id": log.session_id,
        "auth_method": log.auth_method,
    }


@router.get("")
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("audit", "read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    action: str | None = None,
    resource_type: str | None = None,
    actor_username: str | None = None,
    result: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
) -> AuditLogListResponse:
    """List audit logs with filtering and pagination.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page (max 100)
        action: Filter by action type (login, logout, create, update, delete, etc.)
        resource_type: Filter by resource type (node, user, role, approval, etc.)
        actor_username: Filter by actor username (partial match)
        result: Filter by result (success, failure, denied)
        from_date: Filter logs from this date/time
        to_date: Filter logs until this date/time

    Returns:
        Paginated list of audit log entries
    """
    # Build query
    query = select(AuditLog)
    conditions = []

    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if actor_username:
        conditions.append(AuditLog.actor_username.ilike(f"%{actor_username}%"))
    if result:
        conditions.append(AuditLog.result == result)
    if from_date:
        conditions.append(AuditLog.timestamp >= from_date)
    if to_date:
        conditions.append(AuditLog.timestamp <= to_date)

    if conditions:
        query = query.where(and_(*conditions))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(desc(AuditLog.timestamp))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result_rows = await db.execute(query)
    logs = result_rows.scalars().all()

    return AuditLogListResponse(
        items=[AuditLogResponse(**audit_to_response(log)) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/actions")
async def list_audit_actions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("audit", "read")),
) -> dict:
    """Get distinct action types for filtering.

    Returns:
        List of unique action types in the audit log
    """
    query_result = await db.execute(select(distinct(AuditLog.action)))
    actions = [row[0] for row in query_result.fetchall()]
    return {"actions": sorted(actions)}


@router.get("/resource-types")
async def list_resource_types(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("audit", "read")),
) -> dict:
    """Get distinct resource types for filtering.

    Returns:
        List of unique resource types in the audit log
    """
    query_result = await db.execute(select(distinct(AuditLog.resource_type)))
    types = [row[0] for row in query_result.fetchall()]
    return {"resource_types": sorted(types)}
