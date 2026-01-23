"""LDAP configuration API routes."""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.db.database import get_db
from src.db.models import LdapConfig, User
from src.api.dependencies.auth import require_permission
from src.utils.crypto import encrypt_value, decrypt_value


router = APIRouter(prefix="/ldap-configs", tags=["ldap"])


class LdapConfigCreate(BaseModel):
    name: str
    server_url: str
    use_ssl: bool = False
    use_start_tls: bool = False
    bind_dn: str
    bind_password: str  # Will be encrypted
    base_dn: str
    user_search_filter: str = "(&(objectClass=user)(sAMAccountName={username}))"
    group_search_filter: str = "(&(objectClass=group)(member={user_dn}))"
    username_attribute: str = "sAMAccountName"
    email_attribute: str = "mail"
    display_name_attribute: str = "displayName"
    group_attribute: str = "memberOf"
    is_active: bool = True
    is_primary: bool = False
    sync_groups: bool = True
    auto_create_users: bool = True


class LdapConfigUpdate(BaseModel):
    name: str | None = None
    server_url: str | None = None
    use_ssl: bool | None = None
    use_start_tls: bool | None = None
    bind_dn: str | None = None
    bind_password: str | None = None  # Will be encrypted if provided
    base_dn: str | None = None
    user_search_filter: str | None = None
    group_search_filter: str | None = None
    username_attribute: str | None = None
    email_attribute: str | None = None
    display_name_attribute: str | None = None
    group_attribute: str | None = None
    is_active: bool | None = None
    is_primary: bool | None = None
    sync_groups: bool | None = None
    auto_create_users: bool | None = None


def config_to_response(config: LdapConfig) -> dict:
    """Convert LdapConfig model to response dict (excludes encrypted password)."""
    return {
        "id": config.id,
        "name": config.name,
        "server_url": config.server_url,
        "use_ssl": config.use_ssl,
        "use_start_tls": config.use_start_tls,
        "bind_dn": config.bind_dn,
        "base_dn": config.base_dn,
        "user_search_filter": config.user_search_filter,
        "group_search_filter": config.group_search_filter,
        "username_attribute": config.username_attribute,
        "email_attribute": config.email_attribute,
        "display_name_attribute": config.display_name_attribute,
        "group_attribute": config.group_attribute,
        "is_active": config.is_active,
        "is_primary": config.is_primary,
        "sync_groups": config.sync_groups,
        "auto_create_users": config.auto_create_users,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
        "last_sync_at": config.last_sync_at.isoformat() if config.last_sync_at else None,
    }


@router.get("")
async def list_ldap_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ldap", "read")),
):
    """List all LDAP configurations."""
    result = await db.execute(select(LdapConfig).order_by(LdapConfig.is_primary.desc()))
    configs = result.scalars().all()
    return [config_to_response(c) for c in configs]


@router.post("", status_code=201)
async def create_ldap_config(
    data: LdapConfigCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ldap", "write")),
):
    """Create a new LDAP configuration."""
    # Check for duplicate name
    result = await db.execute(select(LdapConfig).where(LdapConfig.name == data.name))
    if result.scalar_one_or_none():
        raise HTTPException(400, "LDAP config with this name already exists")

    config = LdapConfig(
        name=data.name,
        server_url=data.server_url,
        use_ssl=data.use_ssl,
        use_start_tls=data.use_start_tls,
        bind_dn=data.bind_dn,
        bind_password_encrypted=encrypt_value(data.bind_password),
        base_dn=data.base_dn,
        user_search_filter=data.user_search_filter,
        group_search_filter=data.group_search_filter,
        username_attribute=data.username_attribute,
        email_attribute=data.email_attribute,
        display_name_attribute=data.display_name_attribute,
        group_attribute=data.group_attribute,
        is_active=data.is_active,
        is_primary=data.is_primary,
        sync_groups=data.sync_groups,
        auto_create_users=data.auto_create_users,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config_to_response(config)


@router.get("/{config_id}")
async def get_ldap_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ldap", "read")),
):
    """Get a specific LDAP configuration."""
    result = await db.execute(select(LdapConfig).where(LdapConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "LDAP config not found")
    return config_to_response(config)


@router.patch("/{config_id}")
async def update_ldap_config(
    config_id: str,
    data: LdapConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ldap", "write")),
):
    """Update an LDAP configuration."""
    result = await db.execute(select(LdapConfig).where(LdapConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "LDAP config not found")

    update_data = data.model_dump(exclude_unset=True)

    # Handle password encryption
    if "bind_password" in update_data:
        update_data["bind_password_encrypted"] = encrypt_value(update_data.pop("bind_password"))

    for key, value in update_data.items():
        setattr(config, key, value)

    await db.commit()
    await db.refresh(config)
    return config_to_response(config)


@router.delete("/{config_id}", status_code=204)
async def delete_ldap_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ldap", "write")),
):
    """Delete an LDAP configuration."""
    result = await db.execute(select(LdapConfig).where(LdapConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "LDAP config not found")

    await db.delete(config)
    await db.commit()


@router.post("/{config_id}/test")
async def test_ldap_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("ldap", "write")),
):
    """Test LDAP connection and bind."""
    result = await db.execute(select(LdapConfig).where(LdapConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "LDAP config not found")

    try:
        from ldap3 import Server, Connection, ALL, SIMPLE

        server = Server(config.server_url, use_ssl=config.use_ssl, get_info=ALL)
        bind_password = decrypt_value(config.bind_password_encrypted)
        conn = Connection(
            server,
            user=config.bind_dn,
            password=bind_password,
            authentication=SIMPLE,
        )

        if config.use_start_tls:
            conn.start_tls()

        if conn.bind():
            conn.unbind()
            return {"success": True, "message": "Connection successful"}
        else:
            return {"success": False, "message": "Bind failed"}
    except ImportError:
        return {"success": False, "message": "ldap3 library not installed"}
    except Exception as e:
        return {"success": False, "message": str(e)}
