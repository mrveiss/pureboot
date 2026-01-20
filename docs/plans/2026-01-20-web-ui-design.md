# PureBoot Web UI Design

**Date:** 2026-01-20
**Status:** Approved
**Issue:** [#3 - Web UI for Monitoring](https://github.com/mrveiss/pureboot/issues/3)

## Overview

React-based web interface for full node lifecycle management - not just monitoring, but active control of the entire deployment process.

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Framework | React 18 + TypeScript | Type safety, ecosystem |
| Build | Vite | Fast dev server, modern bundling |
| Components | shadcn/ui + Tailwind CSS | Accessible, customizable, owned |
| Server State | TanStack Query | Caching, background refresh |
| Client State | Zustand | Simple, lightweight |
| Real-time | WebSocket (native) | Live updates without polling |
| Routing | React Router v6 | Standard, well-supported |

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # shadcn/ui components
│   │   ├── nodes/           # Node-specific components
│   │   ├── workflows/       # Workflow builder components
│   │   ├── templates/       # Template management components
│   │   └── layout/          # Shell, sidebar, header
│   ├── pages/               # Route-level components
│   ├── hooks/               # Custom React hooks
│   ├── api/                 # API client and types
│   ├── stores/              # Zustand stores
│   ├── lib/                 # Utilities
│   └── types/               # TypeScript types
├── public/
└── package.json
```

## State Machine

### States (10 total)

| State | Description |
|-------|-------------|
| `discovered` | New node appeared via PXE, waiting for admin action |
| `ignored` | PureBoot passes to next boot option, not managed |
| `pending` | Workflow assigned, ready for next PXE boot |
| `installing` | OS installation in progress |
| `installed` | Installation complete, ready for local boot |
| `active` | Running from local disk in production |
| `reprovision` | Marked for reinstallation |
| `retired` | Out of service, data still on disk |
| `decommissioned` | End of life, awaiting secure wipe or disposal |
| `wiping` | Secure disk erase in progress |

### State Transitions

```
                              ┌──────────┐
                              │ ignored  │
                              └────▲─────┘
                                   │
┌────────────┐    ┌─────────┐    ┌─┴──────────┐    ┌───────────┐    ┌────────┐
│ discovered │───▶│ pending │───▶│ installing │───▶│ installed │───▶│ active │
└────────────┘    └────▲────┘    └────────────┘    └───────────┘    └───┬────┘
                       │                                                 │
                       │         ┌─────────────┐                        │
                       └─────────│ reprovision │◀───────────────────────┤
                                 └─────────────┘                        │
                                                                        ▼
                                                                  ┌─────────┐
                                                                  │ retired │
                                                                  └────┬────┘
                                                                       ▼
                                                              ┌────────────────┐
                                                              │ decommissioned │◀─┐
                                                              └───────┬────────┘  │
                                                                      ▼           │
                                                                 ┌─────────┐      │
                                                                 │ wiping  │──────┘
                                                                 └─────────┘
```

### Wiping Safeguards

- Only accessible from `decommissioned` state
- Requires explicit selection (not automatic)
- Double confirmation dialog (type hostname to confirm)
- Always requires second user approval (four-eye principle)
- Returns to `decommissioned` with `wiped: true` flag

## Pages

### 1. Dashboard

- Node counts by state (cards with quick filters)
- Discovery feed: live-updating list of `discovered` nodes with one-click workflow assignment
- Recent activity stream
- System health status (TFTP, DHCP, WebSocket connection)

### 2. Nodes

- Searchable, filterable table with virtual scrolling (scales to 500+ nodes)
- Columns: Hostname, MAC, State, Group, Last Seen, Arch
- Filters: State, Group, Tags, Search
- Bulk actions: Assign workflow, Assign group, Add tag, Change state, Retire
- Bulk safeguard: 5+ nodes requires second user approval
- Click row to open Node Detail

### 3. Node Detail

- Full hardware info (MAC, IP, vendor, model, serial, UUID, arch, boot mode)
- Visual state machine diagram
  - Current state highlighted
  - Valid transitions clickable
  - Invalid states dimmed
  - Shows approval requirement badge if applicable
- State history timeline
- Tags management
- Workflow assignment

### 4. Device Groups

- Group list with node counts
- Group CRUD
- Per-group settings:
  - Default workflow
  - Auto-provision toggle
  - Approval rules (which actions require approval)

### 5. Workflows (Drag-and-Drop Builder)

Canvas-based visual editor with component palette.

**Components:**
| Component | Purpose |
|-----------|---------|
| PXE Boot | Boot from network with specified template |
| Install OS | Run installation from template |
| Run Script | Execute post-install or custom script |
| Branch | Conditional: arch, boot_mode, vendor, tag, custom |
| Wait | Pause for manual approval or timeout |
| Wipe Disk | Secure erase step |
| Reboot | Restart node (local or PXE) |

**Features:**
- Drag from sidebar to canvas
- Connect nodes by dragging between ports
- Click node to configure parameters
- Branch nodes have multiple output ports (one per condition)
- Branching logic for hardware detection, OS selection, conditional paths

### 6. Templates

**OS Templates:**
- Name, description, supported arch/boot mode
- Boot configuration (kernel, initrd, cmdline)
- Post-install scripts (ordered list)
- Variables (available in scripts as $VAR_NAME)
- Partition layout reference
- OS user template reference
- Version history with rollback

**Partition Layouts:**
- Predefined layouts: Minimal, Standard Server, LVM Standard, Proxmox/oVirt, Full Disk Encrypt
- Custom layouts with partition table editor
- LVM, RAID, LUKS encryption options
- Disk selection (first disk, all disks, by path)

**OS User Templates:**
- Reusable user definitions across OS templates
- Per-user: username, UID, groups, shell, home directory
- Authentication: password from vault, hashed, disabled, SSH keys
- Options: create home, lock account, system account

### 7. Approvals

- Pending approvals queue
- Approve/reject with comments
- Shows: requester, action, target, timestamp
- Badge in header shows pending count
- Filtered by "needs my approval" vs "all pending"

### 8. Activity Log

- Full audit trail
- Filters: user, action type, date range, target
- Columns: timestamp, user, action, target
- Expandable detail: IP address, before/after values, approval chain
- Export to CSV
- Default retention: 180 days
- Optional SIEM export

**Logged Events:**
- Nodes: discovered, state changed, metadata updated, retired, wiped
- Groups: created, updated, deleted, nodes added/removed
- Workflows: created, updated, deleted, assigned
- Templates: created, updated, deleted
- Users: login, logout, created, role changed, disabled
- Approvals: requested, approved, rejected
- System: PureBoot started, config changed, errors

### 9. Settings

| Section | Configuration |
|---------|---------------|
| General | Instance name, timezone, theme, audit retention |
| Network | TFTP server, DHCP proxy, HTTP server URLs, PXE settings |
| Security | Session timeout, password policy, 2FA settings, API tokens |
| Notifications | Email/Slack/webhook for alerts, event triggers |
| Integrations | Hypervisor connections (oVirt, Proxmox), LDAP/SSO |
| Vault | HashiCorp Vault or local encrypted store |
| Backup | Database backup schedule, export/import |
| About | Version, license, system health |

### 10. Users & Roles (Super Admin only)

**Users:**
- Email, full name, role assignment
- Authentication: local password or SSO/LDAP
- Per-user approval overrides

**Roles (default):**
| Role | Access |
|------|--------|
| Super Admin | Full access, manage users/roles, configure approval rules |
| Admin | Manage nodes/groups/workflows, approve actions |
| Operator | Transition states, assign workflows, view everything |
| Viewer | Read-only access |

**Role Editor:**
- Granular permissions per resource (view, create, edit, delete)
- State transition permissions (which transitions allowed)
- Approval requirements (all transitions, bulk actions, etc.)

## Authentication & Authorization

### Auth Flow

- JWT-based (access token + refresh token)
- Tokens in httpOnly cookies or memory with API refresh
- Auto-refresh before expiry
- SSO/LDAP integration supported

### Approval Rules

Configurable per **role** AND per **device group**, most restrictive wins.

**Role-based example:**
```json
{
  "role": "Junior Operator",
  "actions_requiring_approval": ["all_transitions"]
}
```

**Group-based example:**
```json
{
  "group": "Production Servers",
  "actions_requiring_approval": ["retire", "decommission", "wipe"]
}
```

**Combined logic:** If user is Junior Operator AND node is in Production Servers, all applicable rules apply.

## Real-Time Updates

### WebSocket Events

| Event | Triggers |
|-------|----------|
| `node.created` | New node discovered via PXE |
| `node.state_changed` | Any state transition |
| `node.updated` | Metadata change |
| `approval.requested` | Someone needs sign-off |
| `approval.resolved` | Approved or rejected |
| `wipe.progress` | Disk wipe percentage (0-100%) |

### UI Behavior

- Toast notifications for critical events (failures, approvals needed)
- Bell icon with unread count in header
- Notification dropdown with recent activity
- Tables auto-update without page refresh
- Connection status indicator (green/red dot)

## UI/UX Details

### Theme

- Dark mode and light mode
- System preference detection
- Manual toggle in header and settings
- Preference persisted per user

### Tables

- Virtual scrolling for large datasets
- Checkbox selection with shift-click for range
- "Select all on page" / "Select all matching filter"
- Sticky header during scroll
- Column sorting
- Server-side pagination

### Forms

- Validation with inline error messages
- Confirmation dialogs for destructive actions
- Double confirmation (type to confirm) for critical actions
- Loading states and optimistic updates

## Backend API Requirements

The following additions are needed to support the UI:

### New Endpoints

```
# Authentication
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me

# Users & Roles
GET    /api/v1/users
POST   /api/v1/users
GET    /api/v1/users/{user_id}
PATCH  /api/v1/users/{user_id}
DELETE /api/v1/users/{user_id}
GET    /api/v1/roles
POST   /api/v1/roles
PATCH  /api/v1/roles/{role_id}
DELETE /api/v1/roles/{role_id}

# Approvals
GET    /api/v1/approvals
POST   /api/v1/approvals
GET    /api/v1/approvals/{approval_id}
POST   /api/v1/approvals/{approval_id}/approve
POST   /api/v1/approvals/{approval_id}/reject

# Workflows
GET    /api/v1/workflows
POST   /api/v1/workflows
GET    /api/v1/workflows/{workflow_id}
PATCH  /api/v1/workflows/{workflow_id}
DELETE /api/v1/workflows/{workflow_id}

# Templates
GET    /api/v1/templates
POST   /api/v1/templates
GET    /api/v1/templates/{template_id}
PATCH  /api/v1/templates/{template_id}
DELETE /api/v1/templates/{template_id}
GET    /api/v1/templates/{template_id}/versions

# Partition Layouts
GET    /api/v1/partition-layouts
POST   /api/v1/partition-layouts
GET    /api/v1/partition-layouts/{layout_id}
PATCH  /api/v1/partition-layouts/{layout_id}
DELETE /api/v1/partition-layouts/{layout_id}

# OS User Templates
GET    /api/v1/os-user-templates
POST   /api/v1/os-user-templates
GET    /api/v1/os-user-templates/{template_id}
PATCH  /api/v1/os-user-templates/{template_id}
DELETE /api/v1/os-user-templates/{template_id}

# Activity Log
GET    /api/v1/activity-log
GET    /api/v1/activity-log/export

# Settings
GET    /api/v1/settings
PATCH  /api/v1/settings

# WebSocket
WS     /api/v1/ws
```

### State Machine Updates

Add new states to backend:
- `ignored`
- `decommissioned`
- `wiping`

Update transitions:
- `discovered` → `ignored`
- `ignored` → `discovered`
- `retired` → `decommissioned`
- `decommissioned` → `wiping`
- `wiping` → `decommissioned`

### Database Models

New models needed:
- `User` (id, email, name, role_id, auth_type, password_hash, status)
- `Role` (id, name, permissions, approval_requirements)
- `Approval` (id, action, target, requester_id, approver_id, status, comment)
- `Workflow` (id, name, definition_json, created_by)
- `Template` (id, name, config_json, version, partition_layout_id, os_user_template_id)
- `PartitionLayout` (id, name, config_json)
- `OSUserTemplate` (id, name, users_json)
- `ActivityLog` (id, timestamp, user_id, action, target_type, target_id, details_json)
- `Setting` (key, value)

## Implementation Phases

### Phase 1: Foundation
- Project setup (Vite, React, TypeScript, Tailwind, shadcn/ui)
- Layout shell (sidebar, header, routing)
- Auth flow (login, JWT handling)
- API client setup
- WebSocket connection

### Phase 2: Core Node Management
- Dashboard with node counts
- Nodes table with filtering
- Node detail page
- State machine visualization
- State transitions (with validation)

### Phase 3: Groups & Bulk Operations
- Device groups CRUD
- Bulk selection and actions
- Group assignment

### Phase 4: Workflows & Templates
- Template browser and editor
- Partition layout editor
- OS user template editor
- Workflow builder (drag-and-drop)

### Phase 5: Authorization & Approvals
- Users & roles management
- Permission checking
- Approval workflow
- Four-eye principle enforcement

### Phase 6: Polish
- Activity log
- Settings page
- Notifications
- Dark mode
- Real-time updates refinement

## Acceptance Criteria

From Issue #3:
- [x] All node states visible and filterable
- [x] State transitions can be triggered from UI
- [x] Workflows can be assigned to nodes
- [x] Real-time updates via WebSocket

Additional:
- [ ] Visual state machine for transitions
- [ ] Drag-and-drop workflow builder with branching
- [ ] Role-based access control
- [ ] Approval workflow (configurable per role and group)
- [ ] Wiping requires double confirm + second user
- [ ] Dark/light mode with toggle
- [ ] 180-day audit log retention
- [ ] Scales to 500+ nodes with virtual scrolling
