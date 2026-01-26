# Multi-Site Management Design

**Issue:** #76
**Status:** Design Complete
**Author:** Claude + mrveiss
**Date:** 2026-01-26
**Prerequisites:** Issue #10 (Hierarchical Device Groups)

---

## Overview

Enable PureBoot to manage nodes across multiple physical locations/data centers from a single control plane while ensuring local boot infrastructure at each site for reliability and performance.

### Problem Statement

PureBoot currently assumes a single-site deployment. Organizations with multiple datacenters, cloud regions, or logical environments need:
- Local boot infrastructure at each site (PXE/TFTP doesn't work over WAN)
- Centralized management and visibility
- Resilience when connectivity between sites fails

### Use Cases

1. **Geographically distributed datacenters** - Multiple physical locations (US-East, EU-West) with their own networks
2. **Logical separation within one location** - Different environments (prod/staging/dev) or departments
3. **Hybrid cloud/on-prem** - Mix of on-premises datacenters and cloud regions

### Key Principles

- **Central control plane**: Single source of truth for configuration, single UI
- **Local data plane**: Each site handles its own boot traffic
- **Configurable autonomy**: Sites operate independently when needed
- **Prerequisite**: Builds on Issue #10 (Hierarchical Device Groups)

---

## Architecture

### Hybrid Model

Central controller for management/UI, lightweight site agents for local execution.

```
┌─────────────────────────────────────────────────────────────┐
│                    Central Controller                        │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────────┐  │
│  │ Web UI  │  │ REST API│  │Database │  │ Sync Engine   │  │
│  └─────────┘  └─────────┘  └─────────┘  └───────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │ Heartbeat / WebSocket
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐┌──────────────┐┌──────────────┐
│  Site Agent  ││  Site Agent  ││  Site Agent  │
│  (US-East)   ││  (EU-West)   ││  (Dev Lab)   │
├──────────────┤├──────────────┤├──────────────┤
│ • TFTP/HTTP  ││ • TFTP/HTTP  ││ • TFTP/HTTP  │
│ • API Proxy  ││ • API Proxy  ││ • API Proxy  │
│ • Local Cache││ • Local Cache││ • Local Cache│
└──────────────┘└──────────────┘└──────────────┘
       │              │              │
    [Nodes]        [Nodes]        [Nodes]
```

### Site Hierarchy

Sites use flexible arbitrary depth hierarchy (no fixed levels). Examples:
- `Global / US / US-East / Rack-A`
- `Production / Datacenter-1`
- `Dev`

Sites are implemented as a special type of DeviceGroup (from Issue #10) with additional site-specific fields.

---

## Data Model

### Extended DeviceGroup Model

Building on Issue #10's hierarchical DeviceGroups, sites add location-specific fields.

```python
class DeviceGroup(Base):
    # Existing fields from #10
    id: Mapped[str]
    name: Mapped[str]
    description: Mapped[str | None]
    parent_id: Mapped[str | None]  # From #10 - enables hierarchy

    # Site-specific fields (null for regular groups)
    is_site: Mapped[bool] = False

    # Site agent connection (only when is_site=True)
    agent_url: Mapped[str | None]          # https://agent.site.local:8443
    agent_token_hash: Mapped[str | None]   # For agent authentication
    agent_status: Mapped[str | None]       # online, offline, degraded
    agent_last_seen: Mapped[datetime | None]

    # Site autonomy settings
    autonomy_level: Mapped[str | None]     # readonly, limited, full
    conflict_resolution: Mapped[str | None] # central_wins, last_write,
                                            # site_wins, manual

    # Content caching policy
    cache_policy: Mapped[str | None]       # minimal, assigned, mirror, pattern
    cache_patterns_json: Mapped[str | None] # Glob patterns for what to cache
    cache_max_size_gb: Mapped[int | None]   # Storage limit
    cache_retention_days: Mapped[int]       # Evict unused content after N days

    # Network discovery config
    discovery_method: Mapped[str | None]   # dhcp, dns, anycast, fallback
    discovery_config_json: Mapped[str | None]

    # Migration policy
    migration_policy: Mapped[str | None]   # manual, auto_accept, auto_release,
                                           # bidirectional
```

### Node Changes

Nodes gain a `home_site_id` (where they physically boot from) distinct from `group_id` (logical organization):

```python
class Node(Base):
    # Existing
    group_id: Mapped[str | None]  # Logical group assignment

    # New
    home_site_id: Mapped[str | None]  # Physical site (auto-detected on boot)
```

### Sync State Tracking

```python
class SyncState(Base):
    """Tracks sync state per entity."""
    entity_type: Mapped[str]      # node, workflow, template
    entity_id: Mapped[str]
    site_id: Mapped[str]
    version: Mapped[int]          # Incrementing version
    last_modified: Mapped[datetime]
    last_modified_by: Mapped[str] # site_id or "central"
    checksum: Mapped[str]         # Content hash for conflict detection
```

### Conflict Queue

```python
class SyncConflict(Base):
    """Conflicts pending manual resolution."""
    entity_type: Mapped[str]
    entity_id: Mapped[str]
    site_id: Mapped[str]
    central_state_json: Mapped[str]
    site_state_json: Mapped[str]
    detected_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]
    resolution: Mapped[str | None]  # accepted_central, accepted_site, merged
```

### Migration Claim

```python
class MigrationClaim(Base):
    """Tracks node migration between sites."""
    id: Mapped[str]
    node_id: Mapped[str]

    source_site_id: Mapped[str]      # Where node was
    target_site_id: Mapped[str]      # Where node booted

    status: Mapped[str]              # pending, approved, rejected, expired

    # Auto-approval policy evaluation
    auto_approve_eligible: Mapped[bool]
    policy_matched: Mapped[str | None]  # Which policy allowed/denied

    # Approval tracking (reuses existing approval system)
    approval_id: Mapped[str | None]  # Links to Approval table if manual

    created_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]
    expires_at: Mapped[datetime]
```

---

## Site Agent Architecture

The site agent is a lightweight PureBoot instance with a focused role.

### Components

```
┌─────────────────────────────────────────────────┐
│                  Site Agent                      │
├─────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌─────────────┐ │
│  │TFTP Server│  │HTTP Server│  │ API Proxy   │ │
│  │  (port 69)│  │(port 8080)│  │ (port 8443) │ │
│  └───────────┘  └───────────┘  └─────────────┘ │
│         │            │               │          │
│         └────────────┴───────────────┘          │
│                      │                          │
│              ┌───────▼───────┐                  │
│              │  Local Cache  │                  │
│              │  • Bootloaders│                  │
│              │  • Templates  │                  │
│              │  • Node state │                  │
│              └───────────────┘                  │
│                      │                          │
│              ┌───────▼───────┐                  │
│              │  Sync Engine  │                  │
│              │  • Heartbeat  │                  │
│              │  • Content    │                  │
│              │  • State      │                  │
│              └───────────────┘                  │
└─────────────────────────────────────────────────┘
```

### Operating Modes

| Mode | Central Reachable | Behavior |
|------|-------------------|----------|
| **Connected** | Yes | Proxy requests to central, cache responses |
| **Degraded** | Intermittent | Queue writes, serve from cache, sync when possible |
| **Offline** | No | Full local operation per autonomy level |

### Autonomy Levels

| Level | Can Discover Nodes | Can Change State | Can Approve |
|-------|-------------------|------------------|-------------|
| `readonly` | No (queue for central) | No | No |
| `limited` | Yes | Yes (safe transitions only) | No |
| `full` | Yes | Yes (all transitions) | Yes |

### Local Services

- **TFTP Server (port 69)**: Serves bootloaders (iPXE, GRUB)
- **HTTP Server (port 8080)**: Boot files, templates, ISOs
- **API Proxy (port 8443)**: Node-facing API, proxied to central or handled locally

---

## Synchronization

### Sync Flow

```
Central                          Site Agent
   │                                  │
   │◄──── Heartbeat (30s-5min) ───────│  Status, metrics, queue size
   │                                  │
   │◄──── State Changes ──────────────│  Node transitions, discoveries
   │                                  │
   │────── Config Push ──────────────►│  Workflows, templates metadata
   │                                  │
   │────── Content Sync ─────────────►│  Bootloaders, ISOs (on-demand/scheduled)
   │                                  │
   ├──── WebSocket (optional) ───────►│  Real-time events, immediate push
   │                                  │
```

### Conflict Resolution Strategies

Configurable per-site:

| Strategy | When Conflict Detected |
|----------|----------------------|
| `central_wins` | Discard site changes, apply central state |
| `last_write` | Compare timestamps, newest wins |
| `site_wins` | Keep site changes for nodes at that site |
| `manual` | Flag in `SyncConflict` table for human review |

---

## Node Migration

### Claim-Based Flow

When a node physically moves between sites, the new site detects it on boot.

```
1. Node boots at Site B (was registered at Site A)
   │
2. Site B agent receives PXE request, checks MAC
   │
   ├─► Node unknown locally → query central
   │
3. Central returns: "Node belongs to Site A"
   │
4. Site B creates MigrationClaim
   │
5. Site A notified (or auto-approves per policy)
   │
   ├─► Approved: Node reassigned to Site B
   │
   └─► Rejected: Node boots with "return to home site" message
```

### Auto-Approval Policies

Configurable per-site:

| Policy | Behavior |
|--------|----------|
| `manual` | All claims require approval |
| `auto_accept` | This site auto-approves incoming claims |
| `auto_release` | This site auto-approves releasing nodes to other sites |
| `bidirectional` | Both directions auto-approved |

### During Pending Claim

Configurable behavior:
- Boot with a "pending migration" minimal environment
- Boot normally at new site (if target has `limited` or `full` autonomy)
- Refuse to boot until resolved (strictest policy)

---

## Content Caching

### Cache Hierarchy

```
Site Agent Storage
├── /bootloaders/          # Always cached (small, essential)
│   ├── ipxe.efi
│   ├── undionly.kpxe
│   └── grub/
├── /scripts/              # iPXE scripts, generated on-demand
├── /templates/            # Cached per policy
│   ├── kickstart/
│   ├── preseed/
│   └── cloud-init/
├── /images/               # Large files, cached per policy
│   ├── ubuntu-24.04.iso
│   └── windows-2022.wim
└── /state/                # Local node state cache
    └── nodes.db           # SQLite for offline operation
```

### Cache Policies

| Policy | Behavior |
|--------|----------|
| `minimal` | Bootloaders + active workflows only. Fetch templates on-demand. |
| `assigned` | Above + explicitly assigned templates/images. Admin controls. |
| `mirror` | Full sync of all content from central. High storage use. |
| `pattern` | Cache items matching glob patterns (e.g., `ubuntu-*`, `kickstart/*`) |

### Sync Triggers

- **Scheduled**: Nightly sync of assigned content
- **On-demand**: Template requested by node, not in cache → fetch and cache
- **Push**: Central pushes critical updates immediately
- **Manual**: Admin triggers sync via UI/API

---

## Health Monitoring

### Heartbeat Protocol

```python
class Heartbeat:
    site_id: str
    timestamp: datetime

    # Agent health
    agent_version: str
    uptime_seconds: int

    # Service status
    services: dict  # {"tftp": "ok", "http": "ok", "api": "ok"}

    # Metrics
    nodes_seen_last_hour: int
    active_boots: int
    cache_hit_rate: float
    disk_usage_percent: float

    # Sync status
    pending_sync_items: int
    last_sync_at: datetime
    conflicts_pending: int
```

### Status Determination

| Last Heartbeat | Status |
|----------------|--------|
| < 2 intervals ago | `online` |
| 2-5 intervals ago | `degraded` |
| > 5 intervals ago | `offline` |

### WebSocket Upgrade

When agent connects via WebSocket:
- Real-time event streaming (node boots, state changes)
- Immediate config push from central
- Lower heartbeat frequency (connection itself is health indicator)

### Alert Conditions

| Condition | Severity | Action |
|-----------|----------|--------|
| Site offline | Critical | Notify admins, UI warning |
| Site degraded | Warning | UI indicator, log |
| Sync backlog > threshold | Warning | Notify, auto-retry |
| Conflicts pending > N | Info | Notify site admin |
| Cache storage > 90% | Warning | Evict old content |
| Service down (TFTP/HTTP) | Critical | Notify, attempt restart |

---

## API Design

### Central Controller - New Endpoints

```
Sites (extends DeviceGroups from #10)
  GET    /api/v1/sites                    # List all sites
  GET    /api/v1/sites/{id}               # Get site details + agent status
  POST   /api/v1/sites                    # Create site
  PATCH  /api/v1/sites/{id}               # Update site config
  DELETE /api/v1/sites/{id}               # Remove site

  GET    /api/v1/sites/{id}/nodes         # Nodes at this site
  GET    /api/v1/sites/{id}/health        # Detailed health metrics
  POST   /api/v1/sites/{id}/sync          # Trigger manual sync

Agent Registration
  POST   /api/v1/agents/register          # Agent registers with central
  POST   /api/v1/agents/heartbeat         # Heartbeat endpoint
  WS     /api/v1/agents/ws                # WebSocket upgrade

Migration
  GET    /api/v1/migrations               # List pending claims
  GET    /api/v1/migrations/{id}          # Claim details
  POST   /api/v1/migrations/{id}/approve  # Approve claim
  POST   /api/v1/migrations/{id}/reject   # Reject claim

Sync
  GET    /api/v1/sync/conflicts           # List unresolved conflicts
  POST   /api/v1/sync/conflicts/{id}/resolve  # Resolve conflict
```

### Site Agent - Local Endpoints

```
Node-facing (what booting nodes call)
  GET    /boot/{mac}                      # iPXE script for node
  GET    /templates/{path}                # Fetch template/file
  POST   /api/v1/nodes/register           # Node self-registration
  POST   /api/v1/nodes/{id}/event         # Node reports event
  PATCH  /api/v1/nodes/{id}/state         # State transition

Agent management (local admin)
  GET    /api/v1/agent/status             # Local agent status
  POST   /api/v1/agent/sync               # Force sync with central
  GET    /api/v1/agent/cache              # Cache contents/stats
  DELETE /api/v1/agent/cache/{path}       # Evict cached item
```

### Request Flow Example

```
Node boots → DHCP points to Site Agent
         → GET /boot/aa:bb:cc:dd:ee:ff

Site Agent (connected mode):
  → Check local cache for node
  → Proxy to central: GET /api/v1/nodes?mac=aa:bb:cc:dd:ee:ff
  → Cache response
  → Return iPXE script

Site Agent (offline mode):
  → Check local cache
  → Found: Return iPXE script from cache
  → Not found + full autonomy: Create node locally, queue sync
  → Not found + readonly: Return "try again later" script
```

---

## Node Discovery Methods

Primary method is DHCP-based, but all are configurable per-site:

| Method | Description |
|--------|-------------|
| `dhcp` | DHCP server's next-server option points to site agent (default) |
| `dns` | Nodes resolve `pureboot.local` via split-horizon/GeoDNS |
| `anycast` | All agents share anycast IP, routing directs to nearest |
| `fallback` | Try mDNS → DNS → hardcoded central |

---

## Implementation Phases

### Phase 0: Prerequisite (Issue #10)
- Implement hierarchical DeviceGroups
- Parent-child relationships, settings inheritance
- **Must complete before multi-site work**

### Phase 1: Site Model Foundation
- Extend DeviceGroup with `is_site` and site-specific fields
- Site CRUD API endpoints
- UI: Sites view in dashboard
- No agent yet - just data model
- **Deliverable**: Can create/manage sites as labeled groups

### Phase 2: Site Agent (Minimal)
- Standalone agent binary/container
- TFTP + HTTP boot services
- Agent registration with central
- Heartbeat protocol
- **Deliverable**: Agent serves boot files, central knows it exists

### Phase 3: API Proxy & Caching
- Agent proxies node API calls to central
- Local SQLite cache for node state
- Content caching (bootloaders, templates)
- **Deliverable**: Nodes can boot through agent, agent caches responses

### Phase 4: Offline Operation
- Autonomy level enforcement
- Offline queue for state changes
- Sync engine for reconnection
- **Deliverable**: Sites work when disconnected (per autonomy level)

### Phase 5: Conflict Resolution
- Conflict detection on sync
- Resolution strategies (configurable)
- Conflict queue + UI for manual resolution
- **Deliverable**: Safe reconnection after offline operation

### Phase 6: Node Migration
- Migration claim model
- Claim detection on cross-site boot
- Approval workflow integration
- Auto-approval policies
- **Deliverable**: Nodes can move between sites safely

### Phase 7: Advanced Features
- WebSocket upgrade for real-time
- Content push from central
- Alerting integration
- Multi-site dashboard view
- **Deliverable**: Production-ready multi-site

---

## Dependencies

| Dependency | Status | Impact |
|------------|--------|--------|
| Issue #10 (Hierarchical DeviceGroups) | Open | Blocker - must implement first |
| Issue #38 (Live Disk Cloning) | Open | Enables cross-site migration with data |
| WebSocket infrastructure | Partial | Extend for agent communication |
| Approval system | Done | Reuse for migration claims |

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Clock drift causing sync issues | Medium | Use vector clocks, not just timestamps |
| Split-brain during network partition | Medium | Configurable conflict resolution, manual fallback |
| Agent storage fills up | Low | Cache eviction policies, size limits, alerts |
| Large ISO sync over slow WAN | High | Delta sync, compression, scheduled off-peak |
| Agent compromise exposes all site nodes | Medium | Scoped agent tokens, mTLS, audit logging |

---

## Open Questions

To resolve during implementation:

1. Should agent be same codebase as controller (feature flags) or separate?
2. SQLite vs embedded PostgreSQL for agent local storage?
3. Delta sync protocol for large files (rsync-like vs custom)?

---

## References

- Issue #76: Multi-Site Management
- Issue #10: Hierarchical Device Groups (prerequisite)
- Issue #38: Live Disk Cloning (enables migration)