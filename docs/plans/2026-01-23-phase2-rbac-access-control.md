# Phase 2: RBAC & Access Control - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement UserGroups with node access scoping, service accounts, and API keys, plus full GUI for user/role/group management.

**Architecture:** UserGroups provide team-based access control. Users belong to groups, groups have roles (inherited permissions) and access to nodes via three methods: device groups, tags, or explicit node assignment. Service accounts are Users with `is_service_account=true` that can have API keys for programmatic access.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Pydantic 2.x, React 18, TypeScript, Zustand, TailwindCSS, shadcn/ui

---

## Task 1: Add UserGroup and Association Models

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add UserGroup model after Role model**

Add at line ~530 (after `RolePermission` class):

```python
class UserGroup(Base):
    """User group for team-based access control."""

    __tablename__ = "user_groups"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    requires_approval: Mapped[bool] = mapped_column(default=False)
    ldap_group_dn: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    # Relationships
    members: Mapped[list["User"]] = relationship(
        secondary="user_group_members", back_populates="groups"
    )
    roles: Mapped[list["Role"]] = relationship(
        secondary="user_group_roles", back_populates="user_groups"
    )
    device_groups: Mapped[list["DeviceGroup"]] = relationship(
        secondary="user_group_device_groups", back_populates="user_groups"
    )


class UserGroupMember(Base):
    """Association table for users and user groups."""

    __tablename__ = "user_group_members"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(default=func.now())


class UserGroupRole(Base):
    """Association table for user groups and roles."""

    __tablename__ = "user_group_roles"

    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class UserGroupDeviceGroup(Base):
    """Access mapping: user group → device groups."""

    __tablename__ = "user_group_device_groups"

    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    device_group_id: Mapped[str] = mapped_column(
        ForeignKey("device_groups.id", ondelete="CASCADE"), primary_key=True
    )


class UserGroupTag(Base):
    """Access mapping: user group → tags."""

    __tablename__ = "user_group_tags"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_group_id", "tag", name="uq_user_group_tag"),
    )


class UserGroupNode(Base):
    """Access mapping: user group → explicit nodes."""

    __tablename__ = "user_group_nodes"

    user_group_id: Mapped[str] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
```

**Step 2: Update User model to add groups relationship and service account fields**

In User class, add after `updated_at`:

```python
    # Service account fields
    is_service_account: Mapped[bool] = mapped_column(default=False)
    service_account_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Auth source for LDAP/AD
    auth_source: Mapped[str] = mapped_column(String(10), default="local")  # local, ldap, ad
    ldap_dn: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    groups: Mapped[list["UserGroup"]] = relationship(
        secondary="user_group_members", back_populates="members"
    )
```

**Step 3: Update Role model to add user_groups relationship**

In Role class, add to relationships:

```python
    user_groups: Mapped[list["UserGroup"]] = relationship(
        secondary="user_group_roles", back_populates="roles"
    )
```

**Step 4: Update DeviceGroup model to add user_groups relationship**

In DeviceGroup class, add to relationships:

```python
    user_groups: Mapped[list["UserGroup"]] = relationship(
        secondary="user_group_device_groups", back_populates="device_groups"
    )
```

**Step 5: Commit**

```bash
git add src/db/models.py
git commit -m "feat(rbac): add UserGroup and access control models"
```

---

## Task 2: Add API Key Model

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add ApiKey model after RefreshToken model**

```python
class ApiKey(Base):
    """API key for service account authentication."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    service_account_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    scopes_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of scope restrictions
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    # Relationships
    service_account: Mapped["User"] = relationship(foreign_keys=[service_account_id])
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint("service_account_id", "name", name="uq_api_key_account_name"),
    )
```

**Step 2: Commit**

```bash
git add src/db/models.py
git commit -m "feat(rbac): add ApiKey model for service accounts"
```

---

## Task 3: Create API Key Generation Utility

**Files:**
- Create: `src/utils/api_keys.py`

**Step 1: Create API key utility**

```python
"""API key generation and verification utilities."""
import secrets
import hashlib
from datetime import datetime

import bcrypt


def generate_api_key(environment: str = "live") -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        tuple of (full_key, key_prefix, key_hash)
        - full_key: The complete key to show user once (pb_live_XXXXXXXX_SECRET)
        - key_prefix: First part for identification (pb_live_XXXXXXXX)
        - key_hash: bcrypt hash of the secret portion for storage
    """
    # Generate 8-char ID and 48-char secret
    key_id = secrets.token_hex(4)  # 8 hex chars
    secret = secrets.token_hex(24)  # 48 hex chars

    # Format: pb_{env}_{id}_{secret}
    prefix = f"pb_{environment}_{key_id}"
    full_key = f"{prefix}_{secret}"

    # Hash only the secret portion
    key_hash = bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()

    return full_key, prefix, key_hash


def verify_api_key(full_key: str, stored_hash: str) -> bool:
    """
    Verify an API key against its stored hash.

    Args:
        full_key: The complete API key (pb_live_XXXXXXXX_SECRET)
        stored_hash: The bcrypt hash of the secret

    Returns:
        True if valid, False otherwise
    """
    try:
        parts = full_key.split("_")
        if len(parts) != 4:
            return False

        secret = parts[3]
        return bcrypt.checkpw(secret.encode(), stored_hash.encode())
    except Exception:
        return False


def parse_api_key(full_key: str) -> tuple[str, str] | None:
    """
    Parse an API key to extract prefix and secret.

    Args:
        full_key: The complete API key

    Returns:
        tuple of (prefix, secret) or None if invalid format
    """
    try:
        parts = full_key.split("_")
        if len(parts) != 4:
            return None

        prefix = f"{parts[0]}_{parts[1]}_{parts[2]}"
        secret = parts[3]
        return prefix, secret
    except Exception:
        return None
```

**Step 2: Commit**

```bash
git add src/utils/api_keys.py
git commit -m "feat(rbac): add API key generation utilities"
```

---

## Task 4: Update Auth Middleware for API Key Authentication

**Files:**
- Modify: `src/api/middleware/auth.py`

**Step 1: Add API key authentication support**

Replace the existing middleware with:

```python
"""Authentication middleware for FastAPI."""
from datetime import datetime

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.api.routes.auth import verify_access_token
from src.db.database import async_session_factory
from src.db.models import ApiKey, User
from src.utils.api_keys import parse_api_key, verify_api_key


# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/boot",
    "/api/v1/ipxe",
    "/api/v1/report",
}

# Path prefixes that don't require authentication
PUBLIC_PREFIXES = (
    "/assets",
    "/api/v1/boot/",
    "/api/v1/ipxe/",
)


def is_public_path(path: str) -> bool:
    """Check if path is public (no auth required)."""
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


async def authenticate_api_key(
    key: str, db: AsyncSession, client_ip: str
) -> tuple[User | None, str | None]:
    """
    Authenticate via API key.

    Returns:
        tuple of (user, error_message)
    """
    parsed = parse_api_key(key)
    if not parsed:
        return None, "Invalid API key format"

    prefix, _ = parsed

    # Look up key by prefix
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_prefix == prefix)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        return None, "API key not found"

    if not api_key.is_active:
        return None, "API key is disabled"

    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        return None, "API key has expired"

    # Verify the key
    if not verify_api_key(key, api_key.key_hash):
        return None, "Invalid API key"

    # Load the service account
    result = await db.execute(
        select(User).where(User.id == api_key.service_account_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return None, "Service account not found"

    if not user.is_active:
        return None, "Service account is disabled"

    if user.expires_at and user.expires_at < datetime.utcnow():
        return None, "Service account has expired"

    # Update last used
    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == api_key.id)
        .values(last_used_at=datetime.utcnow(), last_used_ip=client_ip)
    )
    await db.commit()

    return user, None


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce authentication on protected routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths
        if is_public_path(path):
            return await call_next(request)

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authentication scheme"},
            )

        token = auth_header[7:]

        # Check if it's an API key (starts with pb_)
        if token.startswith("pb_"):
            if not async_session_factory:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Database not initialized"},
                )

            client_ip = request.client.host if request.client else "unknown"
            async with async_session_factory() as db:
                user, error = await authenticate_api_key(token, db, client_ip)

                if error:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": error},
                    )

                # Store user info in request state
                request.state.user_id = user.id
                request.state.username = user.username
                request.state.role = user.role
                request.state.auth_method = "api_key"

                return await call_next(request)

        # Otherwise treat as JWT
        payload = verify_access_token(token)

        if not payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # Store user info in request state
        request.state.user_id = payload.get("sub")
        request.state.username = payload.get("username")
        request.state.role = payload.get("role")
        request.state.auth_method = "jwt"

        return await call_next(request)
```

**Step 2: Commit**

```bash
git add src/api/middleware/auth.py
git commit -m "feat(rbac): add API key authentication to middleware"
```

---

## Task 5: Create User Groups API Routes

**Files:**
- Create: `src/api/routes/user_groups.py`

**Step 1: Create user groups routes**

```python
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
```

**Step 2: Commit**

```bash
git add src/api/routes/user_groups.py
git commit -m "feat(rbac): add user groups API routes"
```

---

## Task 6: Create Service Accounts API Routes

**Files:**
- Create: `src/api/routes/service_accounts.py`

**Step 1: Create service accounts routes**

```python
"""Service accounts management API routes."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import User, ApiKey, Role
from src.api.dependencies.auth import require_permission, get_current_user_from_state
from src.api.routes.auth import hash_password
from src.utils.api_keys import generate_api_key


router = APIRouter(prefix="/service-accounts", tags=["service-accounts"])


class ServiceAccountCreate(BaseModel):
    username: str
    description: str | None = None
    role_id: str | None = None
    expires_at: str | None = None  # ISO format


class ServiceAccountUpdate(BaseModel):
    description: str | None = None
    role_id: str | None = None
    expires_at: str | None = None
    is_active: bool | None = None


class ServiceAccountResponse(BaseModel):
    id: str
    username: str
    description: str | None
    role: str | None
    is_active: bool
    expires_at: str | None
    owner_username: str | None
    api_key_count: int
    created_at: str

    class Config:
        from_attributes = True


class ApiKeyCreate(BaseModel):
    name: str
    expires_at: str | None = None  # ISO format


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    created_at: str
    expires_at: str | None
    last_used_at: str | None
    last_used_ip: str | None

    class Config:
        from_attributes = True


class ApiKeyCreateResponse(ApiKeyResponse):
    full_key: str  # Only shown once at creation


@router.get("")
async def list_service_accounts(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "read")),
) -> list[ServiceAccountResponse]:
    """List all service accounts."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.role_ref))
        .where(User.is_service_account == True)
        .order_by(User.username)
    )
    accounts = result.scalars().all()

    responses = []
    for acc in accounts:
        # Get owner username
        owner_username = None
        if acc.owner_id:
            owner_result = await db.execute(
                select(User.username).where(User.id == acc.owner_id)
            )
            owner_username = owner_result.scalar_one_or_none()

        # Get API key count
        key_result = await db.execute(
            select(ApiKey).where(ApiKey.service_account_id == acc.id)
        )
        key_count = len(key_result.scalars().all())

        responses.append(ServiceAccountResponse(
            id=acc.id,
            username=acc.username,
            description=acc.service_account_description,
            role=acc.role_ref.name if acc.role_ref else acc.role,
            is_active=acc.is_active,
            expires_at=acc.expires_at.isoformat() if acc.expires_at else None,
            owner_username=owner_username,
            api_key_count=key_count,
            created_at=acc.created_at.isoformat(),
        ))

    return responses


@router.post("")
async def create_service_account(
    data: ServiceAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user", "create")),
) -> ServiceAccountResponse:
    """Create a new service account."""
    # Check for existing username
    result = await db.execute(
        select(User).where(User.username == data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    # Validate role if provided
    role = None
    if data.role_id:
        role_result = await db.execute(
            select(Role).where(Role.id == data.role_id)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=400, detail="Invalid role ID")

    # Parse expires_at
    expires_at = None
    if data.expires_at:
        try:
            expires_at = datetime.fromisoformat(data.expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format")

    account = User(
        username=data.username,
        email=f"{data.username}@service.local",
        password_hash=hash_password(f"svc-{data.username}-disabled"),  # Not usable for login
        role=role.name if role else "viewer",
        role_id=data.role_id,
        is_service_account=True,
        service_account_description=data.description,
        owner_id=current_user.id,
        expires_at=expires_at,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return ServiceAccountResponse(
        id=account.id,
        username=account.username,
        description=account.service_account_description,
        role=role.name if role else "viewer",
        is_active=account.is_active,
        expires_at=account.expires_at.isoformat() if account.expires_at else None,
        owner_username=current_user.username,
        api_key_count=0,
        created_at=account.created_at.isoformat(),
    )


@router.get("/{account_id}")
async def get_service_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "read")),
) -> dict:
    """Get service account details with API keys."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.role_ref))
        .where(User.id == account_id, User.is_service_account == True)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="Service account not found")

    # Get owner
    owner_username = None
    if account.owner_id:
        owner_result = await db.execute(
            select(User.username).where(User.id == account.owner_id)
        )
        owner_username = owner_result.scalar_one_or_none()

    # Get API keys
    keys_result = await db.execute(
        select(ApiKey).where(ApiKey.service_account_id == account_id)
    )
    keys = keys_result.scalars().all()

    return {
        "id": account.id,
        "username": account.username,
        "description": account.service_account_description,
        "role": account.role_ref.name if account.role_ref else account.role,
        "is_active": account.is_active,
        "expires_at": account.expires_at.isoformat() if account.expires_at else None,
        "owner_username": owner_username,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
        "api_keys": [
            ApiKeyResponse(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                is_active=k.is_active,
                created_at=k.created_at.isoformat(),
                expires_at=k.expires_at.isoformat() if k.expires_at else None,
                last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
                last_used_ip=k.last_used_ip,
            )
            for k in keys
        ],
    }


@router.patch("/{account_id}")
async def update_service_account(
    account_id: str,
    data: ServiceAccountUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> ServiceAccountResponse:
    """Update a service account."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.role_ref))
        .where(User.id == account_id, User.is_service_account == True)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="Service account not found")

    if data.description is not None:
        account.service_account_description = data.description

    if data.role_id is not None:
        role_result = await db.execute(
            select(Role).where(Role.id == data.role_id)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=400, detail="Invalid role ID")
        account.role_id = data.role_id
        account.role = role.name

    if data.expires_at is not None:
        try:
            account.expires_at = datetime.fromisoformat(data.expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format")

    if data.is_active is not None:
        account.is_active = data.is_active

    await db.commit()
    await db.refresh(account)

    # Get owner username
    owner_username = None
    if account.owner_id:
        owner_result = await db.execute(
            select(User.username).where(User.id == account.owner_id)
        )
        owner_username = owner_result.scalar_one_or_none()

    # Get API key count
    key_result = await db.execute(
        select(ApiKey).where(ApiKey.service_account_id == account.id)
    )
    key_count = len(key_result.scalars().all())

    return ServiceAccountResponse(
        id=account.id,
        username=account.username,
        description=account.service_account_description,
        role=account.role_ref.name if account.role_ref else account.role,
        is_active=account.is_active,
        expires_at=account.expires_at.isoformat() if account.expires_at else None,
        owner_username=owner_username,
        api_key_count=key_count,
        created_at=account.created_at.isoformat(),
    )


@router.delete("/{account_id}")
async def delete_service_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "delete")),
) -> dict:
    """Delete a service account and all its API keys."""
    result = await db.execute(
        select(User).where(User.id == account_id, User.is_service_account == True)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="Service account not found")

    await db.delete(account)
    await db.commit()

    return {"success": True, "message": "Service account deleted"}


@router.post("/{account_id}/api-keys")
async def create_api_key(
    account_id: str,
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user", "update")),
) -> ApiKeyCreateResponse:
    """Create a new API key for a service account."""
    # Verify service account exists
    result = await db.execute(
        select(User).where(User.id == account_id, User.is_service_account == True)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="Service account not found")

    # Check for duplicate name
    name_result = await db.execute(
        select(ApiKey).where(
            ApiKey.service_account_id == account_id,
            ApiKey.name == data.name
        )
    )
    if name_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="API key name already exists")

    # Generate key
    full_key, prefix, key_hash = generate_api_key()

    # Parse expires_at
    expires_at = None
    if data.expires_at:
        try:
            expires_at = datetime.fromisoformat(data.expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format")

    api_key = ApiKey(
        service_account_id=account_id,
        name=data.name,
        key_hash=key_hash,
        key_prefix=prefix,
        created_by_id=current_user.id,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        full_key=full_key,  # Only returned at creation!
        is_active=api_key.is_active,
        created_at=api_key.created_at.isoformat(),
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
        last_used_at=None,
        last_used_ip=None,
    )


@router.delete("/{account_id}/api-keys/{key_id}")
async def revoke_api_key(
    account_id: str,
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user", "update")),
) -> dict:
    """Revoke (delete) an API key."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.service_account_id == account_id
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    await db.delete(api_key)
    await db.commit()

    return {"success": True, "message": "API key revoked"}
```

**Step 2: Commit**

```bash
git add src/api/routes/service_accounts.py
git commit -m "feat(rbac): add service accounts and API keys routes"
```

---

## Task 7: Create Roles API Routes

**Files:**
- Create: `src/api/routes/roles.py`

**Step 1: Create roles routes**

```python
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
```

**Step 2: Commit**

```bash
git add src/api/routes/roles.py
git commit -m "feat(rbac): add roles and permissions API routes"
```

---

## Task 8: Register New Routes in main.py

**Files:**
- Modify: `src/main.py`

**Step 1: Import and register new routers**

Add imports:

```python
from src.api.routes.user_groups import router as user_groups_router
from src.api.routes.service_accounts import router as service_accounts_router
from src.api.routes.roles import router as roles_router
```

Add route registrations after existing routes:

```python
app.include_router(user_groups_router, prefix="/api/v1")
app.include_router(service_accounts_router, prefix="/api/v1")
app.include_router(roles_router, prefix="/api/v1")
```

**Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat(rbac): register user groups, service accounts, and roles routes"
```

---

## Task 9: Update Seed Script with UserGroup Support

**Files:**
- Modify: `src/db/seed.py`

**Step 1: Add default user groups to seed script**

Add after the role seeding:

```python
# Define default user groups
USER_GROUPS = {
    "Administrators": {
        "description": "Full system administrators",
        "requires_approval": False,
        "roles": ["admin"],
    },
    "Operators": {
        "description": "Node operators and workflow managers",
        "requires_approval": False,
        "roles": ["operator"],
    },
    "Viewers": {
        "description": "Read-only access for monitoring",
        "requires_approval": False,
        "roles": ["viewer"],
    },
    "Auditors": {
        "description": "Audit and compliance team",
        "requires_approval": False,
        "roles": ["auditor"],
    },
}


async def seed_user_groups(db: AsyncSession, role_map: dict[str, Role]) -> dict[str, "UserGroup"]:
    """Create default user groups if they don't exist."""
    from src.db.models import UserGroup, UserGroupRole

    group_map = {}

    for group_name, group_def in USER_GROUPS.items():
        result = await db.execute(
            select(UserGroup).where(UserGroup.name == group_name)
        )
        group = result.scalar_one_or_none()

        if not group:
            group = UserGroup(
                name=group_name,
                description=group_def["description"],
                requires_approval=group_def["requires_approval"],
            )
            db.add(group)
            await db.flush()

            # Add roles
            for role_name in group_def["roles"]:
                if role_name in role_map:
                    db.add(UserGroupRole(
                        user_group_id=group.id,
                        role_id=role_map[role_name].id
                    ))

        group_map[group_name] = group

    await db.flush()
    return group_map
```

Update `seed_database()` function to call `seed_user_groups`:

```python
async def seed_database():
    """Run all seed operations."""
    await init_db()

    if not async_session_factory:
        print("Database not initialized")
        return

    async with async_session_factory() as db:
        print("Seeding permissions...")
        perm_map = await seed_permissions(db)
        print(f"  Created/verified {len(perm_map)} permissions")

        print("Seeding roles...")
        role_map = await seed_roles(db, perm_map)
        print(f"  Created/verified {len(role_map)} roles")

        print("Seeding user groups...")
        group_map = await seed_user_groups(db, role_map)
        print(f"  Created/verified {len(group_map)} user groups")

        print("Checking admin user...")
        await seed_admin_user(db, role_map)

        await db.commit()
        print("Database seeding complete!")
```

**Step 2: Add UserGroup import at top of file**

```python
from src.db.models import Role, Permission, RolePermission, User, UserGroup, UserGroupRole
```

**Step 3: Commit**

```bash
git add src/db/seed.py
git commit -m "feat(rbac): add default user groups to seed script"
```

---

## Task 10: Create Frontend Types for RBAC

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add RBAC types**

```typescript
// User Groups
export interface UserGroup {
  id: string
  name: string
  description: string | null
  requires_approval: boolean
  ldap_group_dn: string | null
  member_count: number
  role_names: string[]
  created_at: string
  updated_at?: string
}

export interface UserGroupDetail extends UserGroup {
  members: { id: string; username: string; email: string | null }[]
  roles: { id: string; name: string; description: string | null }[]
  access: {
    device_groups: { id: string; name: string }[]
    tags: string[]
    node_ids: string[]
  }
}

// Roles & Permissions
export interface Permission {
  id: string
  resource: string
  action: string
  description: string | null
}

export interface Role {
  id: string
  name: string
  description: string | null
  is_system_role: boolean
  permission_count: number
  created_at: string
}

export interface RoleDetail extends Role {
  permissions: Permission[]
  updated_at: string
}

// Service Accounts
export interface ServiceAccount {
  id: string
  username: string
  description: string | null
  role: string | null
  is_active: boolean
  expires_at: string | null
  owner_username: string | null
  api_key_count: number
  created_at: string
}

export interface ApiKey {
  id: string
  name: string
  key_prefix: string
  is_active: boolean
  created_at: string
  expires_at: string | null
  last_used_at: string | null
  last_used_ip: string | null
}

export interface ApiKeyCreate extends ApiKey {
  full_key: string  // Only at creation
}

export interface ServiceAccountDetail extends ServiceAccount {
  updated_at: string
  api_keys: ApiKey[]
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(ui): add RBAC types for user groups, roles, service accounts"
```

---

## Task 11: Create User Groups API Client

**Files:**
- Create: `frontend/src/api/userGroups.ts`

**Step 1: Create user groups API**

```typescript
import { apiClient } from './client'
import type { UserGroup, UserGroupDetail } from '@/types'

interface ApiResponse<T> {
  success: boolean
  data?: T
  message?: string
}

export const userGroupsApi = {
  async list(): Promise<UserGroup[]> {
    return apiClient.get<UserGroup[]>('/user-groups')
  },

  async get(id: string): Promise<UserGroupDetail> {
    return apiClient.get<UserGroupDetail>(`/user-groups/${id}`)
  },

  async create(data: {
    name: string
    description?: string
    requires_approval?: boolean
  }): Promise<UserGroup> {
    return apiClient.post<UserGroup>('/user-groups', data)
  },

  async update(
    id: string,
    data: {
      name?: string
      description?: string
      requires_approval?: boolean
    }
  ): Promise<UserGroup> {
    return apiClient.patch<UserGroup>(`/user-groups/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/user-groups/${id}`)
  },

  async assignMembers(id: string, userIds: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/members`, { user_ids: userIds })
  },

  async assignRoles(id: string, roleIds: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/roles`, { role_ids: roleIds })
  },

  async assignDeviceGroups(id: string, deviceGroupIds: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/access/device-groups`, {
      device_group_ids: deviceGroupIds,
    })
  },

  async assignTags(id: string, tags: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/access/tags`, { tags })
  },

  async assignNodes(id: string, nodeIds: string[]): Promise<void> {
    await apiClient.post(`/user-groups/${id}/access/nodes`, { node_ids: nodeIds })
  },
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/userGroups.ts
git commit -m "feat(ui): add user groups API client"
```

---

## Task 12: Create Roles API Client

**Files:**
- Create: `frontend/src/api/roles.ts`

**Step 1: Create roles API**

```typescript
import { apiClient } from './client'
import type { Role, RoleDetail, Permission } from '@/types'

export const rolesApi = {
  async list(): Promise<Role[]> {
    return apiClient.get<Role[]>('/roles')
  },

  async listPermissions(): Promise<Permission[]> {
    return apiClient.get<Permission[]>('/roles/permissions')
  },

  async get(id: string): Promise<RoleDetail> {
    return apiClient.get<RoleDetail>(`/roles/${id}`)
  },

  async create(data: {
    name: string
    description?: string
    permission_ids?: string[]
  }): Promise<RoleDetail> {
    return apiClient.post<RoleDetail>('/roles', data)
  },

  async update(
    id: string,
    data: {
      name?: string
      description?: string
      permission_ids?: string[]
    }
  ): Promise<RoleDetail> {
    return apiClient.patch<RoleDetail>(`/roles/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/roles/${id}`)
  },
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/roles.ts
git commit -m "feat(ui): add roles API client"
```

---

## Task 13: Create Service Accounts API Client

**Files:**
- Create: `frontend/src/api/serviceAccounts.ts`

**Step 1: Create service accounts API**

```typescript
import { apiClient } from './client'
import type { ServiceAccount, ServiceAccountDetail, ApiKey, ApiKeyCreate } from '@/types'

export const serviceAccountsApi = {
  async list(): Promise<ServiceAccount[]> {
    return apiClient.get<ServiceAccount[]>('/service-accounts')
  },

  async get(id: string): Promise<ServiceAccountDetail> {
    return apiClient.get<ServiceAccountDetail>(`/service-accounts/${id}`)
  },

  async create(data: {
    username: string
    description?: string
    role_id?: string
    expires_at?: string
  }): Promise<ServiceAccount> {
    return apiClient.post<ServiceAccount>('/service-accounts', data)
  },

  async update(
    id: string,
    data: {
      description?: string
      role_id?: string
      expires_at?: string
      is_active?: boolean
    }
  ): Promise<ServiceAccount> {
    return apiClient.patch<ServiceAccount>(`/service-accounts/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/service-accounts/${id}`)
  },

  async createApiKey(
    accountId: string,
    data: {
      name: string
      expires_at?: string
    }
  ): Promise<ApiKeyCreate> {
    return apiClient.post<ApiKeyCreate>(`/service-accounts/${accountId}/api-keys`, data)
  },

  async revokeApiKey(accountId: string, keyId: string): Promise<void> {
    await apiClient.delete(`/service-accounts/${accountId}/api-keys/${keyId}`)
  },
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/serviceAccounts.ts
git commit -m "feat(ui): add service accounts API client"
```

---

## Task 14: Create User Groups Page

**Files:**
- Create: `frontend/src/pages/UserGroups.tsx`

**Step 1: Create user groups page**

```tsx
import { useState, useEffect } from 'react'
import { Plus, Users, Shield, Pencil, Trash2 } from 'lucide-react'
import { Button, Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { userGroupsApi } from '@/api/userGroups'
import type { UserGroup } from '@/types'

export function UserGroups() {
  const [groups, setGroups] = useState<UserGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    try {
      setLoading(true)
      const data = await userGroupsApi.list()
      setGroups(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load user groups')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-destructive bg-destructive/10 rounded-md">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">User Groups</h1>
          <p className="text-muted-foreground">
            Manage team-based access control and permissions
          </p>
        </div>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Create Group
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {groups.map((group) => (
          <Card key={group.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <CardTitle className="text-lg">{group.name}</CardTitle>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                {group.description || 'No description'}
              </p>
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-1">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  <span>{group.member_count} members</span>
                </div>
                <div className="flex items-center gap-1">
                  <Shield className="h-4 w-4 text-muted-foreground" />
                  <span>{group.role_names.length} roles</span>
                </div>
              </div>
              {group.requires_approval && (
                <div className="mt-2">
                  <span className="text-xs px-2 py-1 rounded bg-amber-100 dark:bg-amber-900 text-amber-800 dark:text-amber-200">
                    Requires Approval
                  </span>
                </div>
              )}
              {group.role_names.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {group.role_names.map((role) => (
                    <span
                      key={role}
                      className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary"
                    >
                      {role}
                    </span>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {groups.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No user groups found. Create one to get started.
        </div>
      )}
    </div>
  )
}

export default UserGroups
```

**Step 2: Commit**

```bash
git add frontend/src/pages/UserGroups.tsx
git commit -m "feat(ui): add User Groups page"
```

---

## Task 15: Create Service Accounts Page

**Files:**
- Create: `frontend/src/pages/ServiceAccounts.tsx`

**Step 1: Create service accounts page**

```tsx
import { useState, useEffect } from 'react'
import { Plus, Key, User, Clock, Copy, Check } from 'lucide-react'
import { Button, Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { serviceAccountsApi } from '@/api/serviceAccounts'
import type { ServiceAccount } from '@/types'

export function ServiceAccounts() {
  const [accounts, setAccounts] = useState<ServiceAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAccounts()
  }, [])

  const loadAccounts = async () => {
    try {
      setLoading(true)
      const data = await serviceAccountsApi.list()
      setAccounts(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load service accounts')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-destructive bg-destructive/10 rounded-md">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Service Accounts</h1>
          <p className="text-muted-foreground">
            Manage machine identities for API access
          </p>
        </div>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Create Service Account
        </Button>
      </div>

      <div className="grid gap-4">
        {accounts.map((account) => (
          <Card key={account.id}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <User className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold">{account.username}</h3>
                    <p className="text-sm text-muted-foreground">
                      {account.description || 'No description'}
                    </p>
                    <div className="flex items-center gap-4 mt-2 text-sm">
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        account.is_active
                          ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
                          : 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
                      }`}>
                        {account.is_active ? 'Active' : 'Disabled'}
                      </span>
                      {account.role && (
                        <span className="text-muted-foreground">
                          Role: {account.role}
                        </span>
                      )}
                      {account.owner_username && (
                        <span className="text-muted-foreground">
                          Owner: {account.owner_username}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-sm">
                      <Key className="h-4 w-4 text-muted-foreground" />
                      <span>{account.api_key_count} API keys</span>
                    </div>
                    {account.expires_at && (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1">
                        <Clock className="h-3 w-3" />
                        <span>Expires: {new Date(account.expires_at).toLocaleDateString()}</span>
                      </div>
                    )}
                  </div>
                  <Button variant="outline" size="sm">
                    Manage Keys
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {accounts.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No service accounts found. Create one for API access.
        </div>
      )}
    </div>
  )
}

export default ServiceAccounts
```

**Step 2: Commit**

```bash
git add frontend/src/pages/ServiceAccounts.tsx
git commit -m "feat(ui): add Service Accounts page"
```

---

## Task 16: Create Roles Page

**Files:**
- Create: `frontend/src/pages/Roles.tsx`

**Step 1: Create roles page**

```tsx
import { useState, useEffect } from 'react'
import { Plus, Shield, Lock, Pencil, Trash2 } from 'lucide-react'
import { Button, Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { rolesApi } from '@/api/roles'
import type { Role } from '@/types'

export function Roles() {
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadRoles()
  }, [])

  const loadRoles = async () => {
    try {
      setLoading(true)
      const data = await rolesApi.list()
      setRoles(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load roles')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-destructive bg-destructive/10 rounded-md">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Roles & Permissions</h1>
          <p className="text-muted-foreground">
            Manage access control roles and their permissions
          </p>
        </div>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Create Role
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {roles.map((role) => (
          <Card key={role.id}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-primary" />
                  <CardTitle className="text-lg">{role.name}</CardTitle>
                  {role.is_system_role && (
                    <Lock className="h-4 w-4 text-muted-foreground" />
                  )}
                </div>
                {!role.is_system_role && (
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-3">
                {role.description || 'No description'}
              </p>
              <div className="flex items-center justify-between">
                <span className="text-sm">
                  {role.permission_count} permissions
                </span>
                {role.is_system_role && (
                  <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">
                    System Role
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {roles.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No roles found.
        </div>
      )}
    </div>
  )
}

export default Roles
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Roles.tsx
git commit -m "feat(ui): add Roles page"
```

---

## Task 17: Update Pages Index and Router

**Files:**
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/router.tsx`

**Step 1: Export new pages**

In `frontend/src/pages/index.ts`, add:

```typescript
export { UserGroups } from './UserGroups'
export { ServiceAccounts } from './ServiceAccounts'
export { Roles } from './Roles'
```

**Step 2: Update router**

In `frontend/src/router.tsx`, add imports:

```typescript
import { UserGroups, ServiceAccounts, Roles } from '@/pages'
```

Add routes inside the protected section:

```typescript
{
  path: 'user-groups',
  element: (
    <ProtectedRoute requiredRole="admin">
      <UserGroups />
    </ProtectedRoute>
  ),
},
{
  path: 'service-accounts',
  element: (
    <ProtectedRoute requiredRole="admin">
      <ServiceAccounts />
    </ProtectedRoute>
  ),
},
{
  path: 'roles',
  element: (
    <ProtectedRoute requiredRole="admin">
      <Roles />
    </ProtectedRoute>
  ),
},
```

**Step 3: Commit**

```bash
git add frontend/src/pages/index.ts frontend/src/router.tsx
git commit -m "feat(ui): add routes for user groups, service accounts, and roles"
```

---

## Task 18: Update Sidebar Navigation

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Step 1: Add navigation items**

Find the navigation items array and add entries for the new pages:

```typescript
// Add to navigation items (in the admin section or create one):
{
  title: 'User Groups',
  href: '/user-groups',
  icon: Users,
},
{
  title: 'Service Accounts',
  href: '/service-accounts',
  icon: Bot,  // or Key
},
{
  title: 'Roles',
  href: '/roles',
  icon: Shield,
},
```

Import new icons at top:

```typescript
import { Users, Shield, Bot } from 'lucide-react'
```

**Step 2: Commit**

```bash
git add frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(ui): add navigation for RBAC pages"
```

---

## Task 19: Final Commit and Push

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

This plan implements Phase 2 of the RBAC system:

| Component | Status |
|-----------|--------|
| UserGroup model | New |
| UserGroupMember/Role/DeviceGroup/Tag/Node models | New |
| ApiKey model | New |
| API key utilities | New |
| Auth middleware (API key support) | Modified |
| User Groups API routes | New |
| Service Accounts API routes | New |
| Roles API routes | New |
| Seed script (user groups) | Modified |
| Frontend types | Modified |
| API clients (userGroups, roles, serviceAccounts) | New |
| User Groups page | New |
| Service Accounts page | New |
| Roles page | New |
| Router (new routes) | Modified |
| Sidebar navigation | Modified |

**Next Phase:** Phase 3 will implement the Approval System with rules, requests, votes, and escalation.
