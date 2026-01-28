# Phase 5: Site Management UI Design

**Date:** 2026-01-28
**Issue:** #76 - Multi-Site Management
**Phase:** 5 of 7
**Status:** Design approved

## Overview

Phase 5 adds a Site Management UI to the PureBoot web frontend for multi-site operations monitoring and site administration. The UI integrates sites under the existing Device Groups concept (sites are groups with `is_site=true`), provides agent dashboards, offline/conflict indicators, and real-time status updates via polling.

## Design Decisions

- **Primary use case:** Both operations monitoring AND site administration
- **Navigation placement:** Under existing Device Groups as a tab
- **Alerting approach:** Badge + toast notifications + dashboard widget (all three)
- **Conflict resolution:** Simple list with quick actions combined with side-by-side diff view

## Section 1: Navigation & Structure

### Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/groups?tab=sites` | DeviceGroupsPage (Sites tab) | Sites listing view |
| `/groups/:id` | GroupDetail (enhanced) | Site detail with agent/conflict tabs |
| `/groups/:id/agents` | AgentDashboardPanel | Agent status and management |
| `/groups/:id/conflicts` | ConflictResolutionPage | Conflict detection and resolution |

### Sidebar Integration

- "Device Groups" sidebar item gains a badge showing count of sites with problems (offline, conflicts, degraded)
- Badge uses destructive variant (red) when any site is offline, warning (yellow) for conflicts only
- Clicking navigates to `/groups` which now has a "Sites" tab alongside the existing "Groups" tab

### Tab Behavior

The DeviceGroupsPage gets a two-tab layout:
- **Groups** tab (default): Existing hierarchical device groups view
- **Sites** tab: New site listing filtered by `is_site=true`

URL parameter `?tab=sites` activates the Sites tab directly (used by sidebar badge click and dashboard widget).

## Section 2: Sites Listing View

### Card Grid Layout

Each site displays as a card in a responsive grid (1-3 columns depending on viewport):

**Card Content:**
- **Header:** Site name + status badge (Online/Offline/Degraded)
- **Body:**
  - Node count (assigned to this site)
  - Agent heartbeat age ("Last seen: 2m ago")
  - Pending conflicts count (with warning icon if > 0)
  - Cache hit rate (percentage bar)
- **Footer:** Quick actions (View Details, Generate Token)

**Status Badge Logic:**
- **Online** (green): Agent heartbeat within 2x interval, no critical issues
- **Degraded** (yellow): Agent online but has pending conflicts or high queue
- **Offline** (red): Agent heartbeat missed, connectivity lost
- **Unknown** (gray): No agent registered yet

### Filtering & Sorting

- **Filter by status:** All | Online | Degraded | Offline | Unknown
- **Sort by:** Name (A-Z) | Status (problems first) | Last Heartbeat | Node Count
- **Quick toggle:** "Show problems only" — filters to Degraded + Offline
- **Search:** Text search by site name or site ID

### Actions

- **Click card** → Navigate to site detail (`/groups/:id`)
- **"Create Site" button** → Opens dialog to create a new site (name, description, location, timezone)
- **"Generate Token" menu action** → Creates one-time agent registration token, copies to clipboard

## Section 3: Site Detail & Agent Dashboard

### Site Detail Enhancement

The existing GroupDetail page is enhanced when `is_site=true`:

**Additional tabs appear:**
- **Nodes** (existing): Nodes in this group/site
- **Agent** (new): Agent status and configuration
- **Conflicts** (new): Conflict detection and resolution

### Agent Dashboard Panel (`/groups/:id/agents`)

**Agent Info Card:**
- Agent version + update indicator (outdated badge if mismatched)
- Uptime since last restart
- Online/Offline status with duration
- Registered at timestamp
- Last heartbeat with relative time

**Services Status:**
- HTTP Boot Service: status indicator (ok/error/unknown)
- TFTP Server: status indicator
- Cache Sync: status + last sync time

**Cache Metrics:**
- Cache hit rate (progress bar)
- Cache size / max size
- Content items cached
- Node states cached

**Queue Statistics:**
- Pending operations count
- Processing count
- Failed count (with retry info)
- "Flush Queue" action button

**Configuration Section:**
- Autonomy level: readonly | limited | full (editable dropdown)
- Cache policy: minimal | assigned | mirror | pattern (editable dropdown)
- Conflict resolution strategy: central_wins | last_write | site_wins | manual
- Cache patterns (editable list for pattern-based caching)
- "Save Configuration" button → PATCH to API

### Dashboard Widget ("Site Health")

Added to the main Dashboard page:
- Total sites count
- Online / Offline breakdown with mini bar chart
- Total pending conflicts across all sites
- Click navigates to `/groups?tab=sites`
- Uses same React Query cache (no extra API calls)

## Section 4: Conflict Resolution View

### Route: `/groups/:id/conflicts`

Accessible as a tab within the site detail page.

### Conflict Table

| Column | Description |
|--------|-------------|
| Node | MAC address + hostname |
| Type | state_mismatch, missing_local, missing_central |
| Local State | Agent's cached state |
| Central State | Controller's state |
| Detected At | Timestamp of detection |
| Actions | Quick resolution buttons |

- Badge in tab header shows pending conflict count
- Filter by conflict type
- Sort by detection time (newest first)
- "Resolve All" bulk action with confirmation dialog

### Quick Actions (per row)

- **"Keep Central"** — accepts central controller's version
- **"Keep Local"** — keeps the agent's cached version
- **"Merge"** — opens the diff view for manual resolution

### Expandable Diff View (on row click or "Merge")

Two-panel layout:
- **Left panel:** Local State (agent cache)
- **Right panel:** Central State (controller)
- Shows: node state, last updated timestamp, additional metadata (workflow, IP, etc.)
- Differences highlighted with red/green background
- Timestamp comparison showing which change is newer
- Resolution buttons: "Accept Local", "Accept Central", "Custom" (edit dialog)

### Resolution History

- Toggle to show resolved conflicts (collapsed by default)
- Shows: resolution strategy, resolved by, resolved at
- "Clear History" button to purge old entries

### API Calls

- `GET /api/v1/sites/{id}/conflicts` — list conflicts
- `POST /api/v1/sites/{id}/conflicts/{conflict_id}/resolve` — resolve single
- `POST /api/v1/sites/{id}/conflicts/resolve-all` — bulk resolve

## Section 5: Toast Notifications & Real-time Updates

### Polling Strategy

- React Query with 30-second `refetchInterval` for sites list and agent status
- 60-second interval for conflict counts
- `refetchIntervalInBackground: false` — pauses when tab is hidden

### Toast Notifications

| Event | Style | Message | Action |
|-------|-------|---------|--------|
| Site went offline | Red (destructive) | "Site {name} lost connectivity" | "View" button |
| Site reconnected | Green (success) | "Site {name} reconnected" | Shows pending sync count |
| New conflicts | Yellow (warning) | "{count} new conflicts at {site}" | "Resolve" button |
| Agent version mismatch | Info (blue) | "Agent at {site} running outdated version" | — |

### Detection Logic (`useSiteAlerts` hook)

- Compare previous query data with current on each refetch
- Track `previousOnlineStatus` in a ref to detect state transitions
- Only fire toasts on state *changes*, not on every poll cycle
- Debounce: suppress duplicate toasts within 60 seconds

## Section 6: File Structure

### New Files

```
frontend/src/
├── api/
│   └── sites.ts                    # API client for sites, agents, conflicts
├── types/
│   └── sites.ts                    # TypeScript types (Site, Agent, Conflict)
├── hooks/
│   ├── useSites.ts                 # React Query hooks for sites data
│   ├── useAgents.ts                # React Query hooks for agent data
│   ├── useConflicts.ts             # React Query hooks for conflicts
│   └── useSiteAlerts.ts            # Toast notification logic
├── pages/
│   ├── SitesListPage.tsx           # Sites tab content (card grid)
│   ├── SiteDetailPage.tsx          # Site detail with tabs
│   ├── AgentDashboardPanel.tsx     # Agent info panel (tab content)
│   └── ConflictResolutionPage.tsx  # Conflict table + diff view
├── components/
│   └── sites/
│       ├── SiteCard.tsx            # Individual site card
│       ├── SiteStatusBadge.tsx     # Online/offline/degraded badge
│       ├── AgentCard.tsx           # Agent info card
│       ├── ConflictTable.tsx       # Conflict list table
│       ├── ConflictDiffView.tsx    # Side-by-side diff panel
│       ├── SiteHealthWidget.tsx    # Dashboard widget
│       └── CreateSiteDialog.tsx    # New site creation dialog
```

### Modified Files

| File | Change |
|------|--------|
| `frontend/src/components/layout/Sidebar.tsx` | Add badge with problem site count |
| `frontend/src/pages/Groups.tsx` | Add "Sites" tab |
| `frontend/src/pages/Dashboard.tsx` | Add Site Health widget |
| `frontend/src/router.tsx` | Add new routes |

### Implementation Order

1. Types and API client (`types/sites.ts`, `api/sites.ts`)
2. React Query hooks (`hooks/useSites.ts`, `useAgents.ts`, `useConflicts.ts`)
3. Site components (`components/sites/`)
4. Pages (SitesListPage, SiteDetailPage, AgentDashboardPanel, ConflictResolutionPage)
5. Integration (Sidebar badge, Groups tab, Dashboard widget, routes)
6. Toast alert system (`hooks/useSiteAlerts.ts`)
