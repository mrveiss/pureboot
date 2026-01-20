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

### States (11 total)

| State | Description |
|-------|-------------|
| `discovered` | New node appeared via PXE, waiting for admin action |
| `ignored` | PureBoot passes to next boot option, not managed |
| `pending` | Workflow assigned, ready for next PXE boot |
| `installing` | OS installation in progress |
| `installed` | Installation complete, ready for local boot |
| `active` | Running from local disk in production |
| `reprovision` | Marked for reinstallation |
| `migrating` | 1:1 hardware replacement in progress (snapshots to iSCSI, restores to new hardware) |
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
                                                                        │
                                                          ┌─────────────┤
                                                          ▼             ▼
                                                   ┌───────────┐  ┌─────────┐
                                                   │ migrating │  │ retired │
                                                   └─────┬─────┘  └────┬────┘
                                                         │             │
                                                         ▼             │
                                                      active           │
                                                                       ▼
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

### 6. Hypervisors

Manage connections to hypervisor platforms for VM provisioning.

**Supported Hypervisors:**

| Platform | Integration Level | Capabilities |
|----------|-------------------|--------------|
| oVirt/RHV | Full API | VM lifecycle, templates, storage domains, HA, live migration |
| Proxmox VE | Full API | VM/container creation, template management |
| VMware ESXi | Partial API | VM creation, basic management |
| Hyper-V | Full API | VM creation, PXE boot, template cloning |
| KVM/Libvirt | Full API | VM lifecycle, storage management |

**Hypervisors List Page:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Hypervisors                                          [+ Add Hypervisor]     │
├─────────────────────────────────────────────────────────────────────────────┤
│ NAME               │ TYPE      │ URL                    │ VMs  │ STATUS    │
├────────────────────┼───────────┼────────────────────────┼──────┼───────────┤
│ oVirt Production   │ oVirt/RHV │ ovirt.example.com      │ 142  │ 🟢 Online │
│ Proxmox Cluster    │ Proxmox   │ proxmox.example.com    │ 48   │ 🟢 Online │
│ VMware Lab         │ ESXi      │ esxi.example.com       │ 12   │ 🟡 Degraded│
│ Dev KVM            │ Libvirt   │ kvm.example.com        │ 8    │ 🟢 Online │
└────────────────────┴───────────┴────────────────────────┴──────┴───────────┘
```

**Hypervisor Connection Editor:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Hypervisor: oVirt Production                    [Test] [Sync] [Save] [Delete]│
├─────────────────────────────────────────────────────────────────────────────┤
│ Name:        [oVirt Production                  ]                           │
│ Type:        [oVirt/RHV ▾]                                                  │
│ URL:         [https://ovirt.example.com/ovirt-engine/api]                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ CREDENTIALS                                                                 │
│ Auth Method: (●) Username/Password  ( ) From vault                         │
│ Username:    [admin@internal                    ]                           │
│ Password:    [••••••••••••••••                  ]                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ OPTIONS                                                                     │
│ [x] Verify SSL certificate                                                  │
│ [x] Auto-sync templates (every 6 hours)                                     │
│ [ ] Enable live migration support                                           │
│ Default Cluster: [Default ▾]                                               │
│ Default Storage: [data ▾]                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Hypervisor Detail Page (VM Management):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ oVirt Production                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ Status: 🟢 Online │ VMs: 142 │ Templates: 8 │ Last Sync: 2 hours ago       │
├──────────────────┬──────────────────────────────────────────────────────────┤
│                  │                                                          │
│ Overview         │ VIRTUAL MACHINES                       [+ Create VM]     │
│ VMs              │                                                          │
│ Templates        │ 🔍 Search...    State: [All ▾]    Cluster: [All ▾]      │
│ Storage Domains  │ ┌──────────────────────────────────────────────────────┐│
│ Networks         │ │ NAME            │ STATE   │ CPU │ RAM  │ CLUSTER    ││
│                  │ ├─────────────────┼─────────┼─────┼──────┼────────────┤│
│                  │ │ web-server-01   │ 🟢 Up   │ 4   │ 8 GB │ Production ││
│                  │ │ db-server-01    │ 🟢 Up   │ 8   │ 32GB │ Production ││
│                  │ │ test-vm-01      │ 🔴 Down │ 2   │ 4 GB │ Dev        ││
│                  │ └─────────────────┴─────────┴─────┴──────┴────────────┘│
│                  │                                                          │
│                  │ QUICK ACTIONS                                            │
│                  │ [Sync Templates] [Migrate VMs] [Storage Report]         │
└──────────────────┴──────────────────────────────────────────────────────────┘
```

**VM Creation Modal (from Hypervisor):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Create VM on oVirt Production                                        [Close]│
├─────────────────────────────────────────────────────────────────────────────┤
│ VM Name:     [pureboot-node-                    ]                           │
│ Template:    [ubuntu-2404-template ▾]                                      │
│ Cluster:     [Production ▾]                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ RESOURCES                                                                   │
│ CPU Cores:   [4  ]    Sockets: [1  ]                                       │
│ Memory:      [8   ] GB                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ STORAGE                                                                     │
│ Disk 1:      [50  ] GB    Storage Domain: [data ▾]    Interface: [VirtIO] │
│                                                          [+ Add Disk]      │
├─────────────────────────────────────────────────────────────────────────────┤
│ NETWORK                                                                     │
│ NIC 1:       Network: [ovirtmgmt ▾]    Profile: [default ▾]               │
│                                                          [+ Add NIC]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ POST-CREATION                                                               │
│ [x] Register as PureBoot node                                               │
│ [x] Start VM after creation                                                 │
│ [ ] Wait for IP and trigger PXE boot                                       │
│ Assign Workflow: [ubuntu-server ▾]                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                    [Cancel] [Create VM]     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Template Sync:**
- Pull templates from hypervisors into PureBoot
- Push PureBoot templates to hypervisors
- Version tracking and comparison
- Scheduled auto-sync

### 7. Storage Management

Central management for all deployment artifacts - ISOs, images, boot files.

**Storage Backends (all supported, configurable per-template):**

| Backend | Use Case | Access Method |
|---------|----------|---------------|
| HTTP (local) | Boot files, scripts, small images | Direct download |
| NFS | Large file shares, ISOs, mounted during install | Network mount |
| iSCSI | Boot from SAN, install source, block storage | Block device |
| S3-compatible | Primary image store, multi-site, CDN | HTTP/HTTPS |

**Access Methods (template decides, hybrid default):**
- Small boot environment loaded to RAM (initrd, kernel)
- Large files streamed/mounted from network storage
- Per-template configuration of preferred method

**Storage Page:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Storage                                                                     │
├──────────────────┬──────────────────────────────────────────────────────────┤
│                  │                                                          │
│ Backends         │ STORAGE BACKENDS                      [+ Add Backend]   │
│ Files            │                                                          │
│ iSCSI LUNs       │ ┌────────────────────────────────────────────────────┐  │
│ Sync Jobs        │ │ 🟢 NFS - Primary                                   │  │
│                  │ │    nfs://storage.local/pureboot                    │  │
│                  │ │    Used by: 12 templates · 450 GB                  │  │
│                  │ ├────────────────────────────────────────────────────┤  │
│                  │ │ 🟢 S3 - Images                                     │  │
│                  │ │    s3://pureboot-images.s3.amazonaws.com           │  │
│                  │ │    Used by: 8 templates · 1.2 TB · CDN enabled     │  │
│                  │ ├────────────────────────────────────────────────────┤  │
│                  │ │ 🟢 iSCSI - SAN Boot                                │  │
│                  │ │    iscsi://san.local:3260                          │  │
│                  │ │    LUNs: 24 · Total: 2.4 TB                        │  │
│                  │ └────────────────────────────────────────────────────┘  │
└──────────────────┴──────────────────────────────────────────────────────────┘
```

**Backend Configuration Editor:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Storage Backend: NFS - Primary                        [Test] [Save] [Delete]│
├─────────────────────────────────────────────────────────────────────────────┤
│ Name:        [NFS - Primary                     ]                           │
│ Type:        (●) NFS  ( ) S3  ( ) iSCSI  ( ) HTTP                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ NFS SETTINGS                                                                │
│ Server:      [storage.local                     ]                           │
│ Export Path: [/pureboot                         ]                           │
│ Mount Opts:  [vers=4.1,rsize=1048576,wsize=1048576]                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ CREDENTIALS (optional)                                                      │
│ ( ) None  (●) Kerberos  ( ) From vault [select ▾]                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ CDN SETTINGS (S3 only)                                                      │
│ [ ] Enable CDN                                                              │
│ CDN URL:     [                                  ]                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

**File Browser:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Files                           Backend: [NFS - Primary ▾]   [Upload] [New Folder]│
├─────────────────────────────────────────────────────────────────────────────┤
│ 📁 /pureboot                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ ☐ │ 📁 isos/                    │ —      │ 12 items │ 2026-01-15 │         │
│ ☐ │ 📁 images/                  │ —      │ 8 items  │ 2026-01-18 │         │
│ ☐ │ 📁 kernels/                 │ —      │ 24 items │ 2026-01-20 │         │
│ ☐ │ 📁 scripts/                 │ —      │ 15 items │ 2026-01-19 │         │
│ ☐ │ 📄 ubuntu-24.04-live.iso    │ 5.2 GB │ ISO      │ 2026-01-10 │ [⋮]    │
│ ☐ │ 📄 windows-2022.iso         │ 6.1 GB │ ISO      │ 2026-01-08 │ [⋮]    │
└───┴─────────────────────────────┴────────┴──────────┴────────────┴─────────┘
│ 2 selected                                      [Download] [Move] [Delete]  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**iSCSI LUN Management:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ iSCSI LUNs                                              [+ Create LUN]      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Target: iscsi://san.local:3260                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ NAME               │ SIZE    │ ASSIGNED TO      │ PURPOSE      │ STATUS    │
├────────────────────┼─────────┼──────────────────┼──────────────┼───────────┤
│ web-server-01-boot │ 100 GB  │ web-server-01    │ Boot from SAN│ 🟢 Active │
│ db-server-01-boot  │ 100 GB  │ db-server-01     │ Boot from SAN│ 🟢 Active │
│ install-source-01  │ 50 GB   │ (shared)         │ Install src  │ 🟢 Active │
│ staging-pool-01    │ 500 GB  │ (unassigned)     │ Auto-provision│ 🔵 Ready │
└────────────────────┴─────────┴──────────────────┴──────────────┴───────────┘
```

**LUN Editor:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ iSCSI LUN: web-server-01-boot                         [Save] [Delete]       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Name:        [web-server-01-boot                ]                           │
│ Size:        [100     ] GB   [ ] Allow resize                               │
│ Target:      [san.local:3260 ▾]                                             │
│ IQN:         iqn.2026-01.local.san:web-server-01-boot (auto-generated)     │
├─────────────────────────────────────────────────────────────────────────────┤
│ PURPOSE                                                                     │
│ (●) Boot from SAN    - Node boots and runs from this LUN                   │
│ ( ) Install source   - Mounted during installation only                     │
│ ( ) Auto-provision   - Assigned automatically to new nodes                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ ASSIGNMENT                                                                  │
│ Assigned to: [web-server-01 ▾]                  [Unassign]                  │
│ Initiator:   iqn.2026-01.local.pureboot:web-server-01                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ ACCESS CONTROL                                                              │
│ [x] CHAP authentication                                                     │
│ Username:    [From vault: web-server-01-iscsi ▾]                           │
│ Password:    [From vault: web-server-01-iscsi ▾]                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Sync Jobs (External Sources):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sync Jobs                                               [+ Create Job]      │
├─────────────────────────────────────────────────────────────────────────────┤
│ NAME                    │ SOURCE                  │ SCHEDULE  │ STATUS     │
├─────────────────────────┼─────────────────────────┼───────────┼────────────┤
│ Ubuntu ISOs             │ releases.ubuntu.com     │ Weekly    │ 🟢 Synced  │
│ Debian Netboot          │ deb.debian.org          │ Daily     │ 🟢 Synced  │
│ Windows Updates         │ wsus.internal           │ Daily     │ 🟡 Running │
│ VMware Tools            │ packages.vmware.com     │ Weekly    │ 🔴 Failed  │
└─────────────────────────┴─────────────────────────┴───────────┴────────────┘
```

**Sync Job Editor:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Sync Job: Ubuntu ISOs                                 [Run Now] [Save]      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Name:        [Ubuntu ISOs                       ]                           │
│ Source URL:  [https://releases.ubuntu.com/24.04/]                          │
│ Destination: [NFS - Primary ▾] /isos/ubuntu/                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ FILE FILTER                                                                 │
│ Include:     [*-live-server-amd64.iso           ]                          │
│ Exclude:     [*.zsync, *.torrent                ]                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ SCHEDULE                                                                    │
│ (●) Scheduled  [ ] Manual only                                              │
│ Frequency:   [Weekly ▾]  Day: [Sunday ▾]  Time: [02:00 ▾]                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ OPTIONS                                                                     │
│ [x] Verify checksums (SHA256)                                               │
│ [x] Delete removed files                                                    │
│ [ ] Keep previous versions (count: [3])                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**In OS Template, storage reference:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ INSTALLATION SOURCE                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ Access Method: (●) Hybrid (recommended)  ( ) Download to RAM  ( ) Mount    │
│                                                                             │
│ Boot Files:                                                                 │
│   Backend:   [HTTP - Local ▾]                                              │
│   Kernel:    [/kernels/ubuntu/vmlinuz           ]  [Browse]                │
│   Initrd:    [/kernels/ubuntu/initrd            ]  [Browse]                │
│                                                                             │
│ Install Image:                                                              │
│   Backend:   [NFS - Primary ▾]                                             │
│   Path:      [/isos/ubuntu/ubuntu-24.04-live.iso]  [Browse]                │
│   Mount as:  [/mnt/install                      ]                          │
│                                                                             │
│ OR iSCSI Boot:                                                              │
│   [ ] Boot from SAN                                                         │
│   LUN Pool:  [staging-pool-01 ▾]  (auto-assigns LUN to node)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7. Templates

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

# Hypervisors
GET    /api/v1/hypervisors
POST   /api/v1/hypervisors
GET    /api/v1/hypervisors/{hypervisor_id}
PATCH  /api/v1/hypervisors/{hypervisor_id}
DELETE /api/v1/hypervisors/{hypervisor_id}
POST   /api/v1/hypervisors/{hypervisor_id}/test
POST   /api/v1/hypervisors/{hypervisor_id}/sync
GET    /api/v1/hypervisors/{hypervisor_id}/vms
POST   /api/v1/hypervisors/{hypervisor_id}/vms
GET    /api/v1/hypervisors/{hypervisor_id}/vms/{vm_id}
POST   /api/v1/hypervisors/{hypervisor_id}/vms/{vm_id}/start
POST   /api/v1/hypervisors/{hypervisor_id}/vms/{vm_id}/stop
POST   /api/v1/hypervisors/{hypervisor_id}/vms/{vm_id}/migrate
GET    /api/v1/hypervisors/{hypervisor_id}/templates
GET    /api/v1/hypervisors/{hypervisor_id}/storage-domains
GET    /api/v1/hypervisors/{hypervisor_id}/networks

# Storage
GET    /api/v1/storage/backends
POST   /api/v1/storage/backends
GET    /api/v1/storage/backends/{backend_id}
PATCH  /api/v1/storage/backends/{backend_id}
DELETE /api/v1/storage/backends/{backend_id}
POST   /api/v1/storage/backends/{backend_id}/test
GET    /api/v1/storage/backends/{backend_id}/files
POST   /api/v1/storage/backends/{backend_id}/files
DELETE /api/v1/storage/backends/{backend_id}/files/{path}
GET    /api/v1/storage/iscsi/luns
POST   /api/v1/storage/iscsi/luns
GET    /api/v1/storage/iscsi/luns/{lun_id}
PATCH  /api/v1/storage/iscsi/luns/{lun_id}
DELETE /api/v1/storage/iscsi/luns/{lun_id}
GET    /api/v1/storage/sync-jobs
POST   /api/v1/storage/sync-jobs
PATCH  /api/v1/storage/sync-jobs/{job_id}
DELETE /api/v1/storage/sync-jobs/{job_id}
POST   /api/v1/storage/sync-jobs/{job_id}/run

# WebSocket
WS     /api/v1/ws
```

### State Machine Updates

Add new states to backend:
- `ignored`
- `migrating`
- `decommissioned`
- `wiping`

Update transitions:
- `discovered` → `ignored`
- `ignored` → `discovered`
- `active` → `migrating`
- `migrating` → `active`
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
- `Hypervisor` (id, name, type, url, credentials_json, options_json, status)
- `StorageBackend` (id, name, type, connection_json, options_json)
- `IscsiLun` (id, name, target_id, size, purpose, assigned_node_id, status)
- `SyncJob` (id, name, source_url, destination_backend_id, filter_json, schedule, status)
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
- Dashboard with node counts and discovery feed
- Nodes table with filtering and virtual scrolling
- Node detail page
- State machine visualization (11 states)
- State transitions (with validation)

### Phase 3: Groups & Bulk Operations
- Device groups CRUD
- Bulk selection and actions
- Group assignment
- Approval rules per group

### Phase 4: Storage Infrastructure
- Storage backends management (NFS, iSCSI, S3, HTTP)
- File browser (upload, download, organize)
- iSCSI LUN management (create, assign, delete)
- Sync jobs for external sources

### Phase 5: Hypervisor Integration
- Hypervisor connections (oVirt, Proxmox, VMware, Hyper-V, KVM)
- VM listing and management
- Template sync between PureBoot and hypervisors
- VM creation from PureBoot

### Phase 6: Workflows & Templates
- Template browser and editor
- Partition layout editor
- OS user template editor
- Workflow builder (drag-and-drop with branching)
- Storage source configuration per template

### Phase 7: Authorization & Approvals
- Users & roles management
- Permission checking
- Approval workflow
- Four-eye principle enforcement
- Per-role and per-group approval rules

### Phase 8: Polish
- Activity log (180-day retention)
- Settings page
- Notifications (toast, bell icon, WebSocket)
- Dark/light mode with toggle
- Real-time updates refinement
- Migration workflow UI

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
- [ ] Hypervisor integration (oVirt, Proxmox, VMware, Hyper-V, KVM)
- [ ] Storage management (NFS, iSCSI, S3, HTTP)
- [ ] iSCSI LUN provisioning and management
- [ ] File browser with upload/download
- [ ] Sync jobs from external sources (vendor mirrors)
- [ ] Hardware migration workflow (1:1 replacement)
