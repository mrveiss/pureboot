"""Authentication and authorization dependencies."""
from typing import Callable
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.database import get_db
from src.db.models import User, Role, Permission


async def get_current_user_from_state(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current user from request state (set by middleware)."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(User)
        .options(selectinload(User.role_ref).selectinload(Role.permissions))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")

    return user


def require_permission(resource: str, action: str) -> Callable:
    """Dependency factory to require a specific permission."""
    async def check_permission(
        user: User = Depends(get_current_user_from_state),
    ) -> User:
        # Admin has all permissions (legacy check)
        if user.role == "admin":
            return user

        # Check via role_ref if available
        if user.role_ref:
            for perm in user.role_ref.permissions:
                if perm.resource == resource and perm.action == action:
                    return user

        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: {resource}:{action}"
        )

    return check_permission


def require_any_permission(*permissions: tuple[str, str]) -> Callable:
    """Dependency factory to require any of the specified permissions."""
    async def check_permissions(
        user: User = Depends(get_current_user_from_state),
    ) -> User:
        # Admin has all permissions
        if user.role == "admin":
            return user

        if user.role_ref:
            user_perms = {(p.resource, p.action) for p in user.role_ref.permissions}
            if any(p in user_perms for p in permissions):
                return user

        raise HTTPException(
            status_code=403,
            detail="Permission denied"
        )

    return check_permissions


def require_role(*roles: str) -> Callable:
    """Dependency factory to require specific roles."""
    async def check_role(
        user: User = Depends(get_current_user_from_state),
    ) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return check_role
