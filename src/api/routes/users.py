"""User management API endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import User, RefreshToken
from src.api.routes.auth import hash_password, get_current_user
from src.services.audit import audit_action

router = APIRouter()

# Valid roles
VALID_ROLES = {"admin", "operator", "approver", "viewer"}


# --- Schemas ---

class UserCreate(BaseModel):
    """Request to create a user."""
    username: str
    email: str | None = None
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    """Request to update a user."""
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    """Request to change password."""
    current_password: str | None = None  # Required for non-admin
    new_password: str


class UserResponse(BaseModel):
    """User response."""
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool
    last_login_at: str | None
    created_at: str


class UserListResponse(BaseModel):
    """Response for user list."""
    data: list[UserResponse]
    total: int


class ApiResponse(BaseModel):
    """Generic API response."""
    success: bool = True
    message: str | None = None
    data: UserResponse | None = None


# --- Helper Functions ---

def user_to_response(user: User) -> UserResponse:
    """Convert User model to response."""
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


# --- Endpoints ---

@router.get("/users", response_model=UserListResponse)
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    role: str | None = Query(None, description="Filter by role"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    query = select(User)
    count_query = select(func.count()).select_from(User)

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    # Get total
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get users
    query = query.order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        data=[user_to_response(u) for u in users],
        total=total,
    )


@router.get("/users/{user_id}", response_model=ApiResponse)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user details."""
    # Users can view their own profile, admins can view any
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return ApiResponse(data=user_to_response(user))


@router.post("/users", response_model=ApiResponse, status_code=201)
async def create_user(
    data: UserCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Validate role
    if data.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"
        )

    # Check username uniqueness
    result = await db.execute(
        select(User).where(User.username == data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    # Check email uniqueness if provided
    if data.email:
        result = await db.execute(
            select(User).where(User.email == data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already exists")

    # Validate password
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Create user
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Audit user creation
    await audit_action(
        db, request,
        action="create",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        result="success",
    )

    return ApiResponse(
        data=user_to_response(user),
        message="User created successfully",
    )


@router.patch("/users/{user_id}", response_model=ApiResponse)
async def update_user(
    user_id: str,
    data: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user."""
    # Users can update their own email, admins can update anything
    is_self = current_user.id == user_id
    is_admin = current_user.role == "admin"

    if not is_self and not is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Non-admins can only update email
    if not is_admin:
        if data.role is not None or data.is_active is not None:
            raise HTTPException(status_code=403, detail="Only admins can change role or status")

    # Track updated fields for audit
    updated_fields = []

    # Update fields
    if data.email is not None:
        # Check uniqueness
        if data.email:
            result = await db.execute(
                select(User).where(User.email == data.email, User.id != user_id)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Email already exists")
        user.email = data.email or None
        updated_fields.append("email")

    if is_admin:
        if data.role is not None:
            if data.role not in VALID_ROLES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"
                )
            # Prevent demoting last admin
            if user.role == "admin" and data.role != "admin":
                result = await db.execute(
                    select(func.count()).select_from(User).where(User.role == "admin")
                )
                admin_count = result.scalar() or 0
                if admin_count <= 1:
                    raise HTTPException(status_code=400, detail="Cannot demote last admin")
            user.role = data.role
            updated_fields.append("role")

        if data.is_active is not None:
            # Prevent disabling last admin
            if user.role == "admin" and not data.is_active:
                result = await db.execute(
                    select(func.count()).select_from(User).where(
                        User.role == "admin", User.is_active == True
                    )
                )
                active_admin_count = result.scalar() or 0
                if active_admin_count <= 1:
                    raise HTTPException(status_code=400, detail="Cannot disable last active admin")
            user.is_active = data.is_active
            updated_fields.append("is_active")

    await db.flush()
    await db.refresh(user)

    # Audit user update
    if updated_fields:
        await audit_action(
            db, request,
            action="update",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.username,
            details={"updated_fields": updated_fields},
            result="success",
        )

    return ApiResponse(
        data=user_to_response(user),
        message="User updated successfully",
    )


@router.post("/users/{user_id}/password", response_model=ApiResponse)
async def change_password(
    user_id: str,
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change user password."""
    from src.api.routes.auth import verify_password

    is_self = current_user.id == user_id
    is_admin = current_user.role == "admin"

    if not is_self and not is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Non-admins must provide current password
    if is_self and not is_admin:
        if not data.current_password:
            raise HTTPException(status_code=400, detail="Current password required")
        if not verify_password(data.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password incorrect")

    # Validate new password
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user.password_hash = hash_password(data.new_password)
    await db.flush()

    # Invalidate all refresh tokens for this user
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id)
    )
    tokens = result.scalars().all()
    for token in tokens:
        await db.delete(token)
    await db.flush()

    return ApiResponse(message="Password changed successfully")


@router.delete("/users/{user_id}", response_model=ApiResponse)
async def delete_user(
    user_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deleting last admin
    if user.role == "admin":
        result = await db.execute(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
        admin_count = result.scalar() or 0
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete last admin")

    # Store username before deletion for audit
    deleted_username = user.username

    # Delete refresh tokens first (cascade should handle this, but be explicit)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id)
    )
    tokens = result.scalars().all()
    for token in tokens:
        await db.delete(token)

    await db.delete(user)
    await db.flush()

    # Audit user deletion
    await audit_action(
        db, request,
        action="delete",
        resource_type="user",
        resource_id=user_id,
        resource_name=deleted_username,
        result="success",
    )

    return ApiResponse(message="User deleted successfully")
