# RBAC & Audit Logging Design

**Issue:** #8 - Advanced RBAC and Audit Logging
**Date:** 2026-01-23
**Status:** Approved

## Overview

Implement Role-Based Access Control and comprehensive audit logging for PureBoot to meet enterprise security requirements. This design covers authentication, authorization, approval workflows, audit trails, and LDAP/AD integration.

### Key Decisions

- **Deployment context:** Multi-team enterprise
- **Node access scoping:** Union of device groups, tags, and explicit assignment
- **Approval triggers:** Device group settings AND user group settings (either can require approval)
- **Approval workflow:** Async queue with escalation on timeout
- **Directory integration:** LDAP/AD with local admin fallback
- **Audit destinations:** Database + file export + SIEM streaming
- **Machine identity:** Service accounts with API keys
- **GUI requirement:** Full GUI integration for all features

---

## Section 1: Data Model

### Users & Authentication

```
User
├── id (UUID)
├── username (unique)
├── email
├── password_hash (nullable - null for LDAP users)
├── auth_source (local | ldap | ad)
├── ldap_dn (nullable - for LDAP/AD users)
├── is_active
├── is_service_account (boolean)
├── created_at, updated_at
└── last_login_at
```

### Roles & Permissions

```
Role
├── id (UUID)
├── name (admin | operator | viewer | auditor | custom)
├── description
├── is_system_role (prevents deletion of built-in roles)
└── permissions[] (many-to-many)

Permission
├── id (UUID)
├── resource (node | group | workflow | storage | user | system | audit)
├── action (create | read | update | delete | execute | approve)
└── description
```

### User Groups

```
UserGroup
├── id (UUID)
├── name
├── requires_approval (boolean - all changes by this group need approval)
├── ldap_group_dn (nullable - for LDAP sync)
├── roles[] (many-to-many - inherited by members)
└── users[] (many-to-many)
```

### Node Access Scoping

Access is a **union** of three methods:

```
UserGroup_DeviceGroup (team → device group access)
UserGroup_Tag (team → tag-based access)
UserGroup_Node (team → explicit node access)
```

A user can access a node if ANY of these conditions are met:
- User's group has access to the node's device group
- User's group has access to a tag on the node
- User's group has explicit access to the node

---

## Section 2: Approval System

### Approval Configuration

```
ApprovalRule
├── id (UUID)
├── name
├── description
├── scope_type (device_group | user_group | global)
├── scope_id (nullable - references DeviceGroup or UserGroup)
├── operations[] (state_transition | node_delete | bulk_operation |
│                 config_change | user_management)
├── required_approvers (int, default 1 for "four-eye" = 2 total)
├── escalation_timeout_hours (default 72)
├── escalation_role_id (FK to Role - who gets escalated requests)
├── is_active
└── priority (higher priority rules override lower)
```

### Approval Workflow

```
ApprovalRequest
├── id (UUID)
├── operation_type
├── operation_payload (JSON - what action to perform)
├── target_type (node | group | user | system)
├── target_id
├── requester_id (FK to User)
├── status (pending | approved | rejected | escalated | expired)
├── required_approvals (int - copied from rule at creation)
├── current_approvals (int)
├── created_at
├── escalated_at (nullable)
├── resolved_at (nullable)
└── resolved_by_id (nullable)

ApprovalVote
├── id (UUID)
├── request_id (FK to ApprovalRequest)
├── approver_id (FK to User)
├── decision (approve | reject)
├── comment (nullable)
└── created_at
```

### Approval Flow

1. User initiates operation → system checks ApprovalRules
2. If rule matches (device group OR user group requires approval) → create ApprovalRequest
3. Notify eligible approvers (same or higher role, access to target)
4. Approvers vote → when `current_approvals >= required_approvals` → execute operation
5. If `escalation_timeout_hours` passes → status = escalated, notify escalation role
6. Escalation role can approve/reject directly

### Default Operations Requiring Approval

All of the following default to requiring approval (configurable per device group / user group):

- Node state transitions
- Node deletion
- Bulk operations (any operation affecting multiple nodes)
- Configuration changes (system settings, storage backends, workflows)
- User/role management

---

## Section 3: Audit Logging

### Audit Log Model

```
AuditLog
├── id (UUID)
├── timestamp
├── correlation_id (UUID - links related operations)
├── user_id (FK to User, nullable for system actions)
├── user_email (denormalized for retention after user deletion)
├── auth_method (local | ldap | ad | api_key)
├── source_ip
├── user_agent
├── action (create | read | update | delete | login | logout |
│           approve | reject | state_transition | bulk_operation)
├── resource_type (node | group | workflow | user | role | system | approval)
├── resource_id (nullable)
├── resource_name (denormalized)
├── request_method (GET | POST | PATCH | DELETE)
├── request_path
├── request_body_hash (SHA256 - for sensitive data, not full body)
├── response_status (HTTP status code)
├── success (boolean)
├── failure_reason (nullable)
├── metadata_json (extensible - before/after values, etc.)
└── approval_request_id (nullable - links to approval if applicable)
```

### Output Destinations

| Destination | Purpose | Implementation |
|-------------|---------|----------------|
| Database | UI queries, filtering, search | SQLAlchemy model, indexed on timestamp/user/resource |
| File Export | Compliance archives | Scheduled job → JSON/CSV to configurable path |
| SIEM | Real-time monitoring | Syslog (RFC 5424) or webhook to configurable endpoint |

### Events Logged

| Category | Events |
|----------|--------|
| Authentication | Login success/failure, logout, API key usage, token refresh |
| Authorization | Permission denied, role checks |
| Node Operations | CRUD, state transitions, tag changes |
| Bulk Operations | Multi-node actions with affected IDs |
| Configuration | Settings changes, storage backend changes, workflow changes |
| User Management | User/role CRUD, group membership changes |
| Approvals | Request created, vote cast, approved/rejected/escalated |

---

## Section 4: API Keys & Service Accounts

### Service Account Model

Service accounts are Users with `is_service_account=true`:

```
ServiceAccount (extends User)
├── id (UUID)
├── username (e.g., "svc-ansible", "svc-jenkins")
├── description (purpose of this service account)
├── owner_id (FK to User - human responsible for this account)
├── is_active
├── created_at
└── expires_at (nullable - optional expiration)
```

### API Key Model

```
ApiKey
├── id (UUID)
├── service_account_id (FK to User where is_service_account=true)
├── name (e.g., "jenkins-prod", "ansible-staging")
├── key_hash (bcrypt hash - actual key shown once at creation)
├── key_prefix (first 8 chars for identification)
├── scopes[] (optional further restriction beyond service account's role)
├── is_active
├── created_at
├── expires_at (nullable)
├── last_used_at
├── last_used_ip
└── created_by_id (FK to User - who created this key)
```

### API Key Format

```
pb_live_a3x7k9m2_f8d4e6b1c9a2f0e5d7c3b8a1e4f6d9c2b5a0e3f7d1c8
└─prefix─┘└─id───┘└──────────────secret─────────────────────────┘
```

- Prefix `pb_live_` or `pb_test_` for environment identification
- 8-char ID for lookup without exposing secret
- 48-char cryptographic random secret

### Authentication Flow

```
Request with "Authorization: Bearer pb_live_a3x7k9m2_..."
    ↓
Extract key_prefix → lookup ApiKey by prefix
    ↓
Verify full key against key_hash
    ↓
Check: is_active, not expired, service account active
    ↓
Load service account's roles/permissions
    ↓
Apply any additional scope restrictions from ApiKey.scopes
    ↓
Proceed with request (audit log records api_key auth method)
```

---

## Section 5: GUI Integration

### New UI Pages

| Page | Purpose | Key Features |
|------|---------|--------------|
| **Login** | Authentication | Username/password form, LDAP/AD selector, "Local admin" fallback option |
| **Users** | User management | List/create/edit users, role assignment, group membership, disable/enable |
| **User Groups** | Team management | CRUD groups, assign roles, set "requires approval" flag, map to device groups/tags/nodes |
| **Service Accounts** | Machine identities | CRUD service accounts, assign owner, set expiration |
| **API Keys** | Key management | Create (show key once), list, revoke, view last used |
| **Roles & Permissions** | RBAC config | View built-in roles, create custom roles, assign permissions |
| **Approval Rules** | Configure approvals | Create rules by device group or user group, set operations, escalation config |
| **Approval Queue** | Pending approvals | List pending requests, approve/reject with comment, view history |
| **My Requests** | User's own requests | Track status of user's pending requests |
| **Audit Logs** | Log viewer | Searchable/filterable table, date range, export to CSV, detail view |

### Changes to Existing Pages

| Page | Changes |
|------|---------|
| **Nodes list** | Filter by "my accessible nodes", show pending approval badge |
| **Node detail** | Actions gated by permissions, "Request approval" button when needed |
| **Device Groups** | "Access" tab showing which user groups have access, approval rule config |
| **Settings** | LDAP/AD configuration, SIEM endpoint config, file export schedule |
| **Header/Nav** | User menu (profile, logout), notification bell for pending approvals |

### Approval UX Flow

```
Operator clicks "Retire Node" on critical device group
    ↓
Modal: "This operation requires approval. Add a comment (optional):"
    ↓
Submit → Toast: "Approval request submitted. You'll be notified when resolved."
    ↓
Request appears in operator's "My Requests" page
    ↓
Approvers see notification badge, request in "Approval Queue"
    ↓
Approver clicks request → sees details, clicks "Approve" with comment
    ↓
Operation executes → both parties notified → audit logged
```

---

## Section 6: LDAP/AD Integration

### Configuration Model

```
LdapConfig
├── id (UUID)
├── name (e.g., "Corporate AD")
├── is_active
├── provider_type (ldap | active_directory)
├── server_url (e.g., "ldaps://ad.corp.example.com:636")
├── bind_dn (service account for searches)
├── bind_password_encrypted
├── user_search_base (e.g., "OU=Users,DC=corp,DC=example,DC=com")
├── user_search_filter (e.g., "(sAMAccountName={username})")
├── group_search_base
├── group_search_filter
├── user_attr_map_json (maps LDAP attrs → PureBoot fields)
├── sync_interval_minutes (for group membership sync)
├── tls_verify (boolean)
├── tls_ca_cert (nullable - custom CA)
└── created_at, updated_at
```

### Authentication Flow

```
User enters username/password
    ↓
Check local users first (for local admin fallback)
    ↓
If not local → iterate active LdapConfigs
    ↓
LDAP bind with user credentials
    ↓
On success: fetch user attributes, sync group memberships
    ↓
Create/update User record (auth_source=ldap|ad, ldap_dn set)
    ↓
Map LDAP groups → UserGroups (via ldap_group_dn field)
    ↓
Issue session token
```

### Group Sync

- Background job runs every `sync_interval_minutes`
- Queries LDAP for group memberships
- Updates UserGroup memberships to match LDAP
- Removes users from UserGroups if no longer in LDAP group
- Audit logs all sync changes

### GUI: LDAP Configuration Page

- Add/edit LDAP configurations
- "Test Connection" button
- "Test User Login" with username/password input
- "Sync Now" button for manual group sync
- Sync history log

---

## Section 7: Implementation Phases

### Phase 1: Core Auth Foundation

**Backend:**
- User, Role, Permission database models
- Local authentication (login/logout endpoints)
- Session management with JWT tokens
- Auth middleware on all API routes
- Password hashing with bcrypt

**Frontend:**
- Login page
- User menu in header (profile, logout)
- Protected route wrapper
- Auth context/state management

**Deliverables:**
- Users can log in with local accounts
- All API routes require authentication
- Session tokens with refresh mechanism

---

### Phase 2: RBAC & Access Control

**Backend:**
- UserGroup model with node scoping (device group, tag, explicit)
- Permission enforcement middleware
- Service account model
- API key generation and authentication
- Access control checks on all endpoints

**Frontend:**
- Users management page (CRUD)
- User Groups management page (CRUD, assign roles, set access)
- Roles & Permissions page (view/create roles)
- Service Accounts page (CRUD)
- API Keys page (create, list, revoke)
- Update existing pages with permission gating

**Deliverables:**
- Users assigned to groups with roles
- Nodes accessible based on group→device group/tag/explicit mapping
- Service accounts with API keys working
- UI enforces permissions (hides/disables unauthorized actions)

---

### Phase 3: Approval System

**Backend:**
- ApprovalRule, ApprovalRequest, ApprovalVote models
- Approval check middleware (intercepts operations, creates requests)
- Background job for escalation timeout processing
- Notification system (in-app, webhook for future email)
- Operation executor (runs approved operations)

**Frontend:**
- Approval Rules configuration page
- Approval Queue page (list, approve/reject, comment)
- My Requests page (track own requests)
- Approval modal on gated actions
- Notification badge in header
- Pending approval indicators on nodes/groups

**Deliverables:**
- Operations requiring approval create pending requests
- Approvers can approve/reject with comments
- Approved operations execute automatically
- Timed-out requests escalate to configured role

---

### Phase 4: Audit & Directory Integration

**Backend:**
- AuditLog model with indexes
- Audit middleware (logs all API requests)
- File export scheduled job (JSON/CSV)
- SIEM streaming (syslog RFC 5424 / webhook)
- LdapConfig model
- LDAP/AD authentication provider
- Background job for LDAP group sync

**Frontend:**
- Audit Logs page (search, filter, date range, export)
- Audit log detail view
- LDAP Configuration page (CRUD, test connection, test login)
- Settings page for SIEM endpoint and file export schedule
- Sync status and history display

**Deliverables:**
- All actions logged to database
- Logs exportable to files on schedule
- Real-time log streaming to SIEM
- LDAP/AD users can authenticate
- LDAP groups sync to UserGroups automatically

---

## Database Schema Summary

### New Tables

| Table | Phase | Purpose |
|-------|-------|---------|
| `users` | 1 | User accounts (human and service) |
| `roles` | 1 | Role definitions |
| `permissions` | 1 | Permission definitions |
| `role_permissions` | 1 | Many-to-many: roles ↔ permissions |
| `user_groups` | 2 | Team groupings |
| `user_group_members` | 2 | Many-to-many: users ↔ user groups |
| `user_group_roles` | 2 | Many-to-many: user groups ↔ roles |
| `user_group_device_groups` | 2 | Access: user group → device groups |
| `user_group_tags` | 2 | Access: user group → tags |
| `user_group_nodes` | 2 | Access: user group → explicit nodes |
| `api_keys` | 2 | API keys for service accounts |
| `approval_rules` | 3 | Approval configuration |
| `approval_requests` | 3 | Pending/completed approval requests |
| `approval_votes` | 3 | Individual approval/reject votes |
| `audit_logs` | 4 | Comprehensive audit trail |
| `ldap_configs` | 4 | LDAP/AD server configurations |

---

## Security Considerations

- Passwords hashed with bcrypt (cost factor 12)
- JWT tokens with short expiry (15 min) + refresh tokens (7 days)
- API keys hashed, never stored in plain text
- LDAP bind passwords encrypted at rest
- Audit logs include request body hash, not full body (prevents sensitive data in logs)
- Rate limiting on login endpoint
- Local admin account for break-glass recovery
- All permission checks server-side (UI is convenience only)

---

## References

- [Issue #8](https://github.com/mrveiss/pureboot/issues/8)
- [PRD Section 9 - Security](../PureBoot_Product_Requirements_Document.md)
- [CLAUDE.md - Four-Eye Principle](../../CLAUDE.md)
