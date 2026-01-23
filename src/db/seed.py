"""Seed database with default roles and permissions."""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import async_session_factory, init_db
from src.db.models import Role, Permission, RolePermission, User, UserGroup, UserGroupRole
from src.api.routes.auth import hash_password


# Define all permissions
PERMISSIONS = [
    # Node permissions
    ("node", "create", "Create new nodes"),
    ("node", "read", "View nodes"),
    ("node", "update", "Update node details"),
    ("node", "delete", "Delete nodes"),
    ("node", "transition", "Transition node state"),
    # Group permissions
    ("group", "create", "Create device groups"),
    ("group", "read", "View device groups"),
    ("group", "update", "Update device groups"),
    ("group", "delete", "Delete device groups"),
    # User permissions
    ("user", "create", "Create users"),
    ("user", "read", "View users"),
    ("user", "update", "Update users"),
    ("user", "delete", "Delete users"),
    # Workflow permissions
    ("workflow", "read", "View workflows"),
    ("workflow", "execute", "Execute workflows"),
    # Storage permissions
    ("storage", "create", "Create storage backends"),
    ("storage", "read", "View storage backends"),
    ("storage", "update", "Update storage backends"),
    ("storage", "delete", "Delete storage backends"),
    # System permissions
    ("system", "read", "View system info"),
    ("system", "configure", "Configure system settings"),
    # Approval permissions
    ("approval", "read", "View approvals"),
    ("approval", "vote", "Vote on approvals"),
    ("approval", "manage", "Manage approval rules"),
    # Audit permissions
    ("audit", "read", "View audit logs"),
    ("audit", "export", "Export audit logs"),
    # LDAP permissions
    ("ldap", "read", "View LDAP configurations"),
    ("ldap", "write", "Manage LDAP configurations"),
]

# Define roles and their permissions
ROLES = {
    "admin": {
        "description": "Full system access",
        "is_system_role": True,
        "permissions": "*",  # All permissions
    },
    "operator": {
        "description": "Node and workflow management",
        "is_system_role": True,
        "permissions": [
            ("node", "create"), ("node", "read"), ("node", "update"), ("node", "transition"),
            ("group", "read"),
            ("workflow", "read"), ("workflow", "execute"),
            ("storage", "read"),
            ("system", "read"),
            ("approval", "read"), ("approval", "vote"),
        ],
    },
    "viewer": {
        "description": "Read-only access",
        "is_system_role": True,
        "permissions": [
            ("node", "read"),
            ("group", "read"),
            ("workflow", "read"),
            ("storage", "read"),
            ("system", "read"),
            ("approval", "read"),
        ],
    },
    "auditor": {
        "description": "Audit log access",
        "is_system_role": True,
        "permissions": [
            ("node", "read"),
            ("group", "read"),
            ("system", "read"),
            ("audit", "read"), ("audit", "export"),
        ],
    },
}


async def seed_permissions(db: AsyncSession) -> dict[tuple[str, str], Permission]:
    """Create all permissions if they don't exist."""
    perm_map = {}

    for resource, action, description in PERMISSIONS:
        result = await db.execute(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action
            )
        )
        perm = result.scalar_one_or_none()

        if not perm:
            perm = Permission(
                resource=resource,
                action=action,
                description=description,
            )
            db.add(perm)
            await db.flush()

        perm_map[(resource, action)] = perm

    return perm_map


async def seed_roles(db: AsyncSession, perm_map: dict[tuple[str, str], Permission]) -> dict[str, Role]:
    """Create all roles if they don't exist."""
    role_map = {}

    for role_name, role_def in ROLES.items():
        result = await db.execute(
            select(Role).where(Role.name == role_name)
        )
        role = result.scalar_one_or_none()

        if not role:
            role = Role(
                name=role_name,
                description=role_def["description"],
                is_system_role=role_def["is_system_role"],
            )
            db.add(role)
            await db.flush()

            # Add permissions
            if role_def["permissions"] == "*":
                perms = list(perm_map.values())
            else:
                perms = []
                for p in role_def["permissions"]:
                    if p in perm_map:
                        perms.append(perm_map[p])
                    else:
                        print(f"  Warning: Permission {p} not found for role {role_name}")

            for perm in perms:
                rp = RolePermission(role_id=role.id, permission_id=perm.id)
                db.add(rp)

        role_map[role_name] = role

    await db.flush()
    return role_map


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


async def seed_user_groups(db: AsyncSession, role_map: dict[str, Role]) -> dict[str, UserGroup]:
    """Create default user groups if they don't exist."""
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
                else:
                    print(f"  Warning: Role {role_name} not found for group {group_name}")

        group_map[group_name] = group

    await db.flush()
    return group_map


async def seed_admin_user(db: AsyncSession, role_map: dict[str, Role]) -> None:
    """Create default admin user if no users exist."""
    result = await db.execute(select(User).limit(1))
    if result.scalar_one_or_none():
        return  # Users already exist

    admin_role = role_map.get("admin")
    admin = User(
        username="admin",
        email="admin@localhost",
        password_hash=hash_password("admin"),  # Change in production!
        role="admin",  # Legacy field
        role_id=admin_role.id if admin_role else None,
    )
    db.add(admin)
    await db.flush()
    print("Created default admin user (username: admin, password: admin)")


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


if __name__ == "__main__":
    asyncio.run(seed_database())
