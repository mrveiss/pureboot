# Issue 014: Implement Users & Roles Page and Authentication System

**Priority:** LOW
**Type:** Full Stack Feature
**Component:** Frontend + Backend
**Status:** Open

---

## Summary

The Users & Roles page shows "Coming Soon" placeholder. PureBoot currently has no authentication - the frontend has a mock auth store but no real login.

## Current Behavior

**Router:** `frontend/src/router.tsx:30`
```typescript
{ path: 'users', element: <div>Users & Roles (Coming Soon)</div> },
```

**Current Auth:** Mock store in `frontend/src/stores/auth.ts` with hardcoded user.

## Expected Functionality

### Authentication System

1. **Login page:** Username/password authentication
2. **Session management:** JWT tokens with refresh
3. **Role-based access control (RBAC)**
4. **Audit logging:** Track user actions

### Roles (suggested)

| Role | Permissions |
|------|-------------|
| Viewer | Read-only access to all pages |
| Operator | Can manage nodes, run workflows |
| Admin | Full access including settings, users |
| Approver | Can approve pending operations |

### Backend API Design

```
POST   /api/v1/auth/login              - Login
POST   /api/v1/auth/logout             - Logout
POST   /api/v1/auth/refresh            - Refresh token
GET    /api/v1/auth/me                 - Get current user

GET    /api/v1/users                   - List users (admin)
GET    /api/v1/users/{id}              - Get user details
POST   /api/v1/users                   - Create user (admin)
PATCH  /api/v1/users/{id}              - Update user
DELETE /api/v1/users/{id}              - Delete user (admin)

GET    /api/v1/roles                   - List roles
```

### User Model

```python
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer")
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### Frontend Page Features

1. **Users Tab:**
   - List all users
   - Create new user
   - Edit user role
   - Disable/enable user
   - Delete user

2. **Roles Tab:**
   - View role definitions
   - (Future: Custom roles)

3. **My Account:**
   - Change password
   - View login history

## Implementation Steps

### Phase 1: Backend Authentication
1. Create User model
2. Implement password hashing (bcrypt)
3. Implement JWT token generation
4. Create auth middleware
5. Create login/logout endpoints
6. Add user CRUD endpoints

### Phase 2: Frontend Authentication
1. Update auth store to use real API
2. Create real Login page
3. Add token storage and refresh
4. Add auth headers to API client
5. Implement logout

### Phase 3: Users Management
1. Create Users page
2. Create user forms
3. Add role management

### Phase 4: RBAC
1. Add permission checks to backend routes
2. Add UI restrictions based on role
3. Hide/disable features based on permissions

## Security Considerations

- Passwords hashed with bcrypt (cost factor 12)
- JWT tokens expire in 15 minutes
- Refresh tokens expire in 7 days
- Rate limiting on login endpoint
- Account lockout after 5 failed attempts
- Audit log for all auth events

## Acceptance Criteria

- [ ] Login with username/password works
- [ ] JWT tokens issued and validated
- [ ] Token refresh works
- [ ] Role-based access enforced
- [ ] Users page shows all users (admin only)
- [ ] Can create/edit/delete users
- [ ] Password change works
- [ ] Audit trail for auth events

## Related Files

- `frontend/src/router.tsx`
- `frontend/src/stores/auth.ts`
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/Users.tsx` (new)
- `src/db/models.py`
- `src/api/routes/auth.py` (new)
- `src/api/routes/users.py` (new)
- `src/core/auth.py` (new)

## Dependencies

- None (foundational feature)
