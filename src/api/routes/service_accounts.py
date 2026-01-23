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
