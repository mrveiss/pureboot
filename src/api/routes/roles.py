"""Roles management API routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import Role, Permission, RolePermission, User
from src.api.dependencies.auth import require_permission


router = APIRouter(prefix="/roles", tags=["roles"])


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    permission_ids: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_ids: list[str] | None = None


class RoleResponse(BaseModel):
    id: str
    name: str
    description: str | None
    is_system_role: bool
    permission_count: int
    created_at: str

    class Config:
        from_attributes = True


class PermissionResponse(BaseModel):
    id: str
    resource: str
    action: str
    description: str | None

    class Config:
        from_attributes = True


@router.get("")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "read")),
) -> list[RoleResponse]:
    """List all roles."""
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .order_by(Role.name)
    )
    roles = result.scalars().all()

    return [
        RoleResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            is_system_role=r.is_system_role,
            permission_count=len(r.permissions),
            created_at=r.created_at.isoformat(),
        )
        for r in roles
    ]


@router.get("/permissions")
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "read")),
) -> list[PermissionResponse]:
    """List all available permissions."""
    result = await db.execute(
        select(Permission).order_by(Permission.resource, Permission.action)
    )
    permissions = result.scalars().all()

    return [
        PermissionResponse(
            id=p.id,
            resource=p.resource,
            action=p.action,
            description=p.description,
        )
        for p in permissions
    ]


@router.post("")
async def create_role(
    data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "create")),
) -> dict:
    """Create a new custom role."""
    # Check for existing name
    result = await db.execute(
        select(Role).where(Role.name == data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role name already exists")

    role = Role(
        name=data.name,
        description=data.description,
        is_system_role=False,
    )
    db.add(role)
    await db.flush()

    # Add permissions
    for perm_id in data.permission_ids:
        db.add(RolePermission(role_id=role.id, permission_id=perm_id))

    await db.commit()

    # Re-fetch with permissions
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role.id)
    )
    role = result.scalar_one()

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_system_role": role.is_system_role,
        "created_at": role.created_at.isoformat(),
        "permissions": [
            PermissionResponse(
                id=p.id,
                resource=p.resource,
                action=p.action,
                description=p.description,
            )
            for p in role.permissions
        ],
    }


@router.get("/{role_id}")
async def get_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "read")),
) -> dict:
    """Get role details with permissions."""
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_system_role": role.is_system_role,
        "created_at": role.created_at.isoformat(),
        "updated_at": role.updated_at.isoformat(),
        "permissions": [
            PermissionResponse(
                id=p.id,
                resource=p.resource,
                action=p.action,
                description=p.description,
            )
            for p in role.permissions
        ],
    }


@router.patch("/{role_id}")
async def update_role(
    role_id: str,
    data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> dict:
    """Update a role (cannot modify system roles)."""
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system_role:
        raise HTTPException(status_code=400, detail="Cannot modify system roles")

    if data.name is not None:
        # Check for duplicate name
        existing = await db.execute(
            select(Role).where(Role.name == data.name, Role.id != role_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Role name already exists")
        role.name = data.name

    if data.description is not None:
        role.description = data.description

    if data.permission_ids is not None:
        # Remove existing permissions
        await db.execute(
            RolePermission.__table__.delete().where(
                RolePermission.role_id == role_id
            )
        )
        # Add new permissions
        for perm_id in data.permission_ids:
            db.add(RolePermission(role_id=role_id, permission_id=perm_id))

    await db.commit()

    # Re-fetch
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .where(Role.id == role_id)
    )
    role = result.scalar_one()

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_system_role": role.is_system_role,
        "created_at": role.created_at.isoformat(),
        "updated_at": role.updated_at.isoformat(),
        "permissions": [
            PermissionResponse(
                id=p.id,
                resource=p.resource,
                action=p.action,
                description=p.description,
            )
            for p in role.permissions
        ],
    }


@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "delete")),
) -> dict:
    """Delete a role (cannot delete system roles)."""
    result = await db.execute(
        select(Role).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system_role:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    await db.delete(role)
    await db.commit()

    return {"success": True, "message": "Role deleted"}
