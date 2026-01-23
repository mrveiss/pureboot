"""User groups management API routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import (
    UserGroup, UserGroupMember, UserGroupRole, UserGroupDeviceGroup,
    UserGroupTag, UserGroupNode, User, Role, DeviceGroup, Node
)
from src.api.dependencies.auth import require_permission


router = APIRouter(prefix="/user-groups", tags=["user-groups"])


class UserGroupCreate(BaseModel):
    name: str
    description: str | None = None
    requires_approval: bool = False


class UserGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    requires_approval: bool | None = None


class UserGroupResponse(BaseModel):
    id: str
    name: str
    description: str | None
    requires_approval: bool
    member_count: int
    role_names: list[str]
    created_at: str

    class Config:
        from_attributes = True


class MemberAssignment(BaseModel):
    user_ids: list[str]


class RoleAssignment(BaseModel):
    role_ids: list[str]


class DeviceGroupAssignment(BaseModel):
    device_group_ids: list[str]


class TagAssignment(BaseModel):
    tags: list[str]


class NodeAssignment(BaseModel):
    node_ids: list[str]


@router.get("")
async def list_user_groups(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "read")),
) -> list[UserGroupResponse]:
    """List all user groups."""
    result = await db.execute(
        select(UserGroup)
        .options(
            selectinload(UserGroup.members),
            selectinload(UserGroup.roles),
        )
        .order_by(UserGroup.name)
    )
    groups = result.scalars().all()

    return [
        UserGroupResponse(
            id=g.id,
            name=g.name,
            description=g.description,
            requires_approval=g.requires_approval,
            member_count=len(g.members),
            role_names=[r.name for r in g.roles],
            created_at=g.created_at.isoformat(),
        )
        for g in groups
    ]


@router.post("")
async def create_user_group(
    data: UserGroupCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "create")),
) -> UserGroupResponse:
    """Create a new user group."""
    # Check for existing name
    result = await db.execute(
        select(UserGroup).where(UserGroup.name == data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Group name already exists")

    group = UserGroup(
        name=data.name,
        description=data.description,
        requires_approval=data.requires_approval,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)

    return UserGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        requires_approval=group.requires_approval,
        member_count=0,
        role_names=[],
        created_at=group.created_at.isoformat(),
    )


@router.get("/{group_id}")
async def get_user_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "read")),
) -> dict:
    """Get user group details with members, roles, and access mappings."""
    result = await db.execute(
        select(UserGroup)
        .options(
            selectinload(UserGroup.members),
            selectinload(UserGroup.roles),
            selectinload(UserGroup.device_groups),
        )
        .where(UserGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="User group not found")

    # Get tags
    tag_result = await db.execute(
        select(UserGroupTag).where(UserGroupTag.user_group_id == group_id)
    )
    tags = [t.tag for t in tag_result.scalars().all()]

    # Get explicit nodes
    node_result = await db.execute(
        select(UserGroupNode).where(UserGroupNode.user_group_id == group_id)
    )
    node_ids = [n.node_id for n in node_result.scalars().all()]

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "requires_approval": group.requires_approval,
        "ldap_group_dn": group.ldap_group_dn,
        "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
        "members": [
            {"id": m.id, "username": m.username, "email": m.email}
            for m in group.members
        ],
        "roles": [
            {"id": r.id, "name": r.name, "description": r.description}
            for r in group.roles
        ],
        "access": {
            "device_groups": [
                {"id": dg.id, "name": dg.name}
                for dg in group.device_groups
            ],
            "tags": tags,
            "node_ids": node_ids,
        },
    }


@router.patch("/{group_id}")
async def update_user_group(
    group_id: str,
    data: UserGroupUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> UserGroupResponse:
    """Update a user group."""
    result = await db.execute(
        select(UserGroup)
        .options(selectinload(UserGroup.members), selectinload(UserGroup.roles))
        .where(UserGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="User group not found")

    if data.name is not None:
        # Check for duplicate name
        existing = await db.execute(
            select(UserGroup).where(
                UserGroup.name == data.name,
                UserGroup.id != group_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Group name already exists")
        group.name = data.name

    if data.description is not None:
        group.description = data.description

    if data.requires_approval is not None:
        group.requires_approval = data.requires_approval

    await db.commit()
    await db.refresh(group)

    return UserGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        requires_approval=group.requires_approval,
        member_count=len(group.members),
        role_names=[r.name for r in group.roles],
        created_at=group.created_at.isoformat(),
    )


@router.delete("/{group_id}")
async def delete_user_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "delete")),
) -> dict:
    """Delete a user group."""
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status_code=404, detail="User group not found")

    await db.delete(group)
    await db.commit()

    return {"success": True, "message": "User group deleted"}


@router.post("/{group_id}/members")
async def assign_members(
    group_id: str,
    data: MemberAssignment,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> dict:
    """Assign members to a user group (replaces existing)."""
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == group_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User group not found")

    # Remove existing members
    await db.execute(
        UserGroupMember.__table__.delete().where(
            UserGroupMember.user_group_id == group_id
        )
    )

    # Add new members
    for user_id in data.user_ids:
        db.add(UserGroupMember(user_id=user_id, user_group_id=group_id))

    await db.commit()
    return {"success": True, "message": f"Assigned {len(data.user_ids)} members"}


@router.post("/{group_id}/roles")
async def assign_roles(
    group_id: str,
    data: RoleAssignment,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> dict:
    """Assign roles to a user group (replaces existing)."""
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == group_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User group not found")

    # Remove existing roles
    await db.execute(
        UserGroupRole.__table__.delete().where(
            UserGroupRole.user_group_id == group_id
        )
    )

    # Add new roles
    for role_id in data.role_ids:
        db.add(UserGroupRole(user_group_id=group_id, role_id=role_id))

    await db.commit()
    return {"success": True, "message": f"Assigned {len(data.role_ids)} roles"}


@router.post("/{group_id}/access/device-groups")
async def assign_device_groups(
    group_id: str,
    data: DeviceGroupAssignment,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> dict:
    """Assign device group access (replaces existing)."""
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == group_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User group not found")

    # Remove existing
    await db.execute(
        UserGroupDeviceGroup.__table__.delete().where(
            UserGroupDeviceGroup.user_group_id == group_id
        )
    )

    # Add new
    for dg_id in data.device_group_ids:
        db.add(UserGroupDeviceGroup(user_group_id=group_id, device_group_id=dg_id))

    await db.commit()
    return {"success": True, "message": f"Assigned {len(data.device_group_ids)} device groups"}


@router.post("/{group_id}/access/tags")
async def assign_tags(
    group_id: str,
    data: TagAssignment,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> dict:
    """Assign tag-based access (replaces existing)."""
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == group_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User group not found")

    # Remove existing
    await db.execute(
        UserGroupTag.__table__.delete().where(
            UserGroupTag.user_group_id == group_id
        )
    )

    # Add new
    for tag in data.tags:
        db.add(UserGroupTag(user_group_id=group_id, tag=tag))

    await db.commit()
    return {"success": True, "message": f"Assigned {len(data.tags)} tags"}


@router.post("/{group_id}/access/nodes")
async def assign_nodes(
    group_id: str,
    data: NodeAssignment,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> dict:
    """Assign explicit node access (replaces existing)."""
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == group_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User group not found")

    # Remove existing
    await db.execute(
        UserGroupNode.__table__.delete().where(
            UserGroupNode.user_group_id == group_id
        )
    )

    # Add new
    for node_id in data.node_ids:
        db.add(UserGroupNode(user_group_id=group_id, node_id=node_id))

    await db.commit()
    return {"success": True, "message": f"Assigned {len(data.node_ids)} nodes"}
