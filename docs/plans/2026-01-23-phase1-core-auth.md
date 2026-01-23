# Phase 1: Core Auth Foundation - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable authentication enforcement across all API routes and add a functional login UI.

**Architecture:** The backend already has User/RefreshToken models, JWT auth, and user management routes. This phase adds: (1) Role and Permission models for fine-grained RBAC, (2) auth middleware to protect all routes, (3) a Login page in the frontend, and (4) ProtectedRoute wrapper to guard UI routes.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Pydantic 2.x, React 18, TypeScript, Zustand, TailwindCSS

---

## Task 1: Add Role and Permission Models

**Files:**
- Modify: `src/db/models.py`

**Step 1: Add Role model after User model**

Add at line ~463 (after `User` class):

```python
class Role(Base):
    """Role definition for RBAC."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_system_role: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles"
    )


class Permission(Base):
    """Permission definition for RBAC."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    resource: Mapped[str] = mapped_column(String(50), nullable=False)  # node, group, user, etc.
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # create, read, update, delete
    description: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    roles: Mapped[list["Role"]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_permission_resource_action"),
    )


class RolePermission(Base):
    """Association table for roles and permissions."""

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )
```

**Step 2: Update User model to reference Role**

Modify User class - add `role_id` FK and relationship (keep legacy `role` string for migration):

```python
# In User class, after the existing fields, add:
    role_id: Mapped[str | None] = mapped_column(
        ForeignKey("roles.id"), nullable=True
    )
    role_ref: Mapped["Role | None"] = relationship()
```

**Step 3: Commit**

```bash
git add src/db/models.py
git commit -m "feat(rbac): add Role and Permission models"
```

---

## Task 2: Create Database Seed Script for Default Roles

**Files:**
- Create: `src/db/seed.py`

**Step 1: Create seed script**

```python
"""Seed database with default roles and permissions."""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import async_session_factory, init_db
from src.db.models import Role, Permission, RolePermission, User
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


async def seed_roles(db: AsyncSession, perm_map: dict) -> dict[str, Role]:
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
                perms = [perm_map[p] for p in role_def["permissions"] if p in perm_map]

            for perm in perms:
                rp = RolePermission(role_id=role.id, permission_id=perm.id)
                db.add(rp)

        role_map[role_name] = role

    await db.flush()
    return role_map


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

        print("Checking admin user...")
        await seed_admin_user(db, role_map)

        await db.commit()
        print("Database seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed_database())
```

**Step 2: Commit**

```bash
git add src/db/seed.py
git commit -m "feat(rbac): add database seed script for roles and permissions"
```

---

## Task 3: Create Auth Middleware

**Files:**
- Create: `src/api/middleware/auth.py`
- Modify: `src/main.py`

**Step 1: Create auth middleware**

```python
"""Authentication middleware for FastAPI."""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.api.routes.auth import verify_access_token


# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/boot",  # PXE boot endpoints
    "/api/v1/ipxe",  # iPXE endpoints
    "/api/v1/report",  # Node reporting
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
        payload = verify_access_token(token)

        if not payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # Store user info in request state for downstream use
        request.state.user_id = payload.get("sub")
        request.state.username = payload.get("username")
        request.state.role = payload.get("role")

        return await call_next(request)
```

**Step 2: Add middleware to main.py**

In `src/main.py`, add after `app = FastAPI(...)`:

```python
from src.api.middleware.auth import AuthMiddleware

# Add auth middleware (after app creation, before routes)
app.add_middleware(AuthMiddleware)
```

**Step 3: Create middleware __init__.py**

```bash
mkdir -p src/api/middleware
touch src/api/middleware/__init__.py
```

**Step 4: Commit**

```bash
git add src/api/middleware/
git add src/main.py
git commit -m "feat(rbac): add authentication middleware"
```

---

## Task 4: Create Permission Checking Dependency

**Files:**
- Create: `src/api/dependencies/auth.py`

**Step 1: Create permission dependency**

```python
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
```

**Step 2: Create dependencies __init__.py**

```bash
mkdir -p src/api/dependencies
touch src/api/dependencies/__init__.py
```

**Step 3: Commit**

```bash
git add src/api/dependencies/
git commit -m "feat(rbac): add permission checking dependencies"
```

---

## Task 5: Create Login Page Component

**Files:**
- Create: `frontend/src/pages/Login.tsx`

**Step 1: Create Login page**

```tsx
import { useState, FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'

export function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const { login, isAuthenticated, isLoading } = useAuthStore()
  const location = useLocation()

  // Redirect if already authenticated
  if (isAuthenticated) {
    const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/'
    return <Navigate to={from} replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    if (!username || !password) {
      setError('Please enter username and password')
      return
    }

    try {
      await login(username, password)
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Login failed. Please check your credentials.')
      }
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h1 className="text-center text-3xl font-bold text-gray-900 dark:text-white">
            PureBoot
          </h1>
          <h2 className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">
            Node Lifecycle Management
          </h2>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="rounded-md shadow-sm space-y-4">
            <div>
              <label htmlFor="username" className="sr-only">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="appearance-none relative block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 placeholder-gray-500 dark:placeholder-gray-400 text-gray-900 dark:text-white bg-white dark:bg-gray-800 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Username"
                disabled={isLoading}
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="appearance-none relative block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 placeholder-gray-500 dark:placeholder-gray-400 text-gray-900 dark:text-white bg-white dark:bg-gray-800 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Password"
                disabled={isLoading}
              />
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-600 dark:text-red-400 text-center">
              {error}
            </div>
          )}

          <div>
            <button
              type="submit"
              disabled={isLoading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <span className="flex items-center">
                  <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Signing in...
                </span>
              ) : (
                'Sign in'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default Login
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Login.tsx
git commit -m "feat(ui): add Login page component"
```

---

## Task 6: Create ProtectedRoute Component

**Files:**
- Create: `frontend/src/components/ProtectedRoute.tsx`

**Step 1: Create ProtectedRoute wrapper**

```tsx
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { useEffect, useState } from 'react'

interface ProtectedRouteProps {
  children: React.ReactNode
  requiredRole?: string | string[]
}

export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { isAuthenticated, user, accessToken, fetchUser, refreshTokens } = useAuthStore()
  const location = useLocation()
  const [isChecking, setIsChecking] = useState(true)

  useEffect(() => {
    const checkAuth = async () => {
      // If we have a token but no user, try to fetch user
      if (accessToken && !user) {
        try {
          await fetchUser()
        } catch {
          // Token might be expired, try refresh
          try {
            await refreshTokens()
            await fetchUser()
          } catch {
            // Refresh failed, will redirect to login
          }
        }
      }
      setIsChecking(false)
    }

    checkAuth()
  }, [accessToken, user, fetchUser, refreshTokens])

  // Show loading while checking auth
  if (isChecking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Check role requirement
  if (requiredRole) {
    const roles = Array.isArray(requiredRole) ? requiredRole : [requiredRole]
    if (!roles.includes(user.role)) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Access Denied</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              You don't have permission to access this page.
            </p>
          </div>
        </div>
      )
    }
  }

  return <>{children}</>
}

export default ProtectedRoute
```

**Step 2: Commit**

```bash
git add frontend/src/components/ProtectedRoute.tsx
git commit -m "feat(ui): add ProtectedRoute component"
```

---

## Task 7: Update Router to Use Protected Routes

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/pages/index.ts`

**Step 1: Update pages index to export Login**

Check current exports and add Login:

```tsx
// Add to frontend/src/pages/index.ts
export { Login } from './Login'
```

**Step 2: Update router.tsx**

```tsx
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import {
  Dashboard,
  Nodes,
  NodeDetail,
  Groups,
  GroupDetail,
  Workflows,
  Templates,
  Hypervisors,
  ActivityLog,
  Approvals,
  Users,
  Storage,
  Settings,
  Login,
  NotFound
} from '@/pages'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'nodes', element: <Nodes /> },
      { path: 'nodes/:nodeId', element: <NodeDetail /> },
      { path: 'groups', element: <Groups /> },
      { path: 'groups/:groupId', element: <GroupDetail /> },
      { path: 'workflows', element: <Workflows /> },
      { path: 'templates', element: <Templates /> },
      { path: 'hypervisors', element: <Hypervisors /> },
      { path: 'storage', element: <Storage /> },
      { path: 'approvals', element: <Approvals /> },
      { path: 'activity', element: <ActivityLog /> },
      { path: 'settings', element: <Settings /> },
      {
        path: 'users',
        element: (
          <ProtectedRoute requiredRole="admin">
            <Users />
          </ProtectedRoute>
        ),
      },
      { path: '*', element: <NotFound /> },
    ],
  },
])
```

**Step 3: Commit**

```bash
git add frontend/src/router.tsx frontend/src/pages/index.ts
git commit -m "feat(ui): enable protected routes with login redirect"
```

---

## Task 8: Add User Menu to Header

**Files:**
- Modify: `frontend/src/components/layout/Header.tsx` (or equivalent)

**Step 1: Find and update header component**

Add user dropdown to header showing username and logout button:

```tsx
// Add to Header component
import { useAuthStore } from '@/stores/auth'

// In component:
const { user, logout } = useAuthStore()

// In JSX, add user menu:
<div className="flex items-center gap-4">
  {user && (
    <div className="flex items-center gap-2">
      <span className="text-sm text-gray-600 dark:text-gray-400">
        {user.username}
      </span>
      <span className="text-xs px-2 py-1 rounded bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
        {user.role}
      </span>
      <button
        onClick={() => logout()}
        className="text-sm text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
      >
        Logout
      </button>
    </div>
  )}
</div>
```

**Step 2: Commit**

```bash
git add frontend/src/components/layout/
git commit -m "feat(ui): add user menu with logout to header"
```

---

## Task 9: Update Auth API Client

**Files:**
- Modify: `frontend/src/api/auth.ts`
- Modify: `frontend/src/api/client.ts`

**Step 1: Update client to handle 401 errors**

In `frontend/src/api/client.ts`, add interceptor for token refresh:

```tsx
// Add response interceptor for 401 handling
// When 401 is received, try to refresh token, then retry request
// If refresh fails, clear auth and redirect to login
```

**Step 2: Ensure auth API handles errors properly**

In `frontend/src/api/auth.ts`, ensure login throws meaningful errors:

```tsx
export const authApi = {
  async login(credentials: LoginCredentials): Promise<AuthTokens> {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
      credentials: 'include', // For refresh token cookie
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Login failed')
    }

    const data = await response.json()
    return data.data
  },
  // ... rest of methods
}
```

**Step 3: Commit**

```bash
git add frontend/src/api/
git commit -m "feat(ui): improve auth API error handling"
```

---

## Task 10: Integration Testing

**Files:**
- Test manually via UI

**Step 1: Seed database on test system**

Run seed script:
```bash
python -m src.db.seed
```

**Step 2: Test login flow**

1. Navigate to `/` - should redirect to `/login`
2. Enter invalid credentials - should show error
3. Enter valid credentials (admin/admin) - should redirect to dashboard
4. Check user menu shows username and role
5. Click logout - should redirect to `/login`
6. Navigate to `/users` as non-admin - should show "Access Denied"

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: address integration testing issues"
```

---

## Task 11: Final Commit and Push

**Step 1: Review all changes**

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat
```

**Step 2: Push branch**

```bash
git push -u origin feature/issue-8-rbac-audit-logging
```

---

## Summary

This plan implements Phase 1 of the RBAC system:

| Component | Status |
|-----------|--------|
| Role/Permission models | New |
| Database seed script | New |
| Auth middleware | New |
| Permission dependencies | New |
| Login page | New |
| ProtectedRoute wrapper | New |
| User menu in header | Modified |
| Router with auth | Modified |

**Next Phase:** Phase 2 will add UserGroups, node access scoping, service accounts, and API keys.
