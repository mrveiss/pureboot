# Web UI Phase 2: Core Node Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the core node management features including dashboard with live data, nodes table with filtering/virtual scrolling, node detail page, and interactive state machine visualization.

**Architecture:** Extend Phase 1 foundation with React Query hooks for data fetching, TanStack Virtual for large list rendering, and a custom SVG-based state machine diagram component. All components use existing shadcn/ui patterns.

**Tech Stack:** React 18, TypeScript, TanStack Query, TanStack Virtual, React Router v6, Tailwind CSS, Lucide icons

**Working Directory:** `/home/kali/Desktop/PureBoot/PureBoot/.worktrees/feature-web-ui/frontend`

**IMPORTANT:** This is a code-editing-only environment. Do NOT run npm install, npm run dev, or any other commands that execute the application. Only create/edit files.

---

## Task 1: Add State Machine Types and Transitions

**Files:**
- Modify: `frontend/src/types/node.ts`

**Step 1: Add state transition map and history types**

Add the following to the end of `frontend/src/types/node.ts`:

```typescript
// Valid state transitions
export const NODE_STATE_TRANSITIONS: Record<NodeState, NodeState[]> = {
  discovered: ['pending', 'ignored'],
  ignored: ['discovered'],
  pending: ['installing'],
  installing: ['installed'],
  installed: ['active'],
  active: ['reprovision', 'migrating', 'retired'],
  reprovision: ['pending'],
  migrating: ['active'],
  retired: ['decommissioned'],
  decommissioned: ['wiping'],
  wiping: ['decommissioned'],
}

export interface StateHistoryEntry {
  id: string
  node_id: string
  from_state: NodeState | null
  to_state: NodeState
  changed_by: string
  changed_at: string
  comment: string | null
}

export interface NodeStats {
  total: number
  by_state: Record<NodeState, number>
  discovered_last_hour: number
  installing_count: number
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/node.ts
git commit -m "feat(frontend): add state transitions and history types"
```

---

## Task 2: Add TanStack Virtual to Dependencies

**Files:**
- Modify: `frontend/package.json`

**Step 1: Add @tanstack/react-virtual dependency**

In `frontend/package.json`, add to dependencies:

```json
"@tanstack/react-virtual": "^3.0.0",
```

Add after the existing `@tanstack/react-query-devtools` line.

**Step 2: Commit**

```bash
git add frontend/package.json
git commit -m "feat(frontend): add tanstack virtual for large list rendering"
```

---

## Task 3: Create React Query Hooks for Nodes

**Files:**
- Create: `frontend/src/hooks/useNodes.ts`
- Modify: `frontend/src/hooks/index.ts`

**Step 1: Create useNodes.ts**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { nodesApi } from '@/api'
import type { Node, NodeFilterParams, NodeState, NodeStats } from '@/types'

export const nodeKeys = {
  all: ['nodes'] as const,
  lists: () => [...nodeKeys.all, 'list'] as const,
  list: (filters: NodeFilterParams) => [...nodeKeys.lists(), filters] as const,
  details: () => [...nodeKeys.all, 'detail'] as const,
  detail: (id: string) => [...nodeKeys.details(), id] as const,
  stats: () => [...nodeKeys.all, 'stats'] as const,
  history: (id: string) => [...nodeKeys.all, 'history', id] as const,
}

export function useNodes(filters?: NodeFilterParams) {
  return useQuery({
    queryKey: nodeKeys.list(filters ?? {}),
    queryFn: () => nodesApi.list(filters),
  })
}

export function useNode(nodeId: string) {
  return useQuery({
    queryKey: nodeKeys.detail(nodeId),
    queryFn: () => nodesApi.get(nodeId),
    enabled: !!nodeId,
  })
}

export function useNodeStats() {
  return useQuery({
    queryKey: nodeKeys.stats(),
    queryFn: async (): Promise<NodeStats> => {
      // This will call a stats endpoint when available
      // For now, compute from list
      const response = await nodesApi.list({ limit: 1000 })
      const nodes = response.data

      const by_state = {} as Record<NodeState, number>
      const states: NodeState[] = [
        'discovered', 'ignored', 'pending', 'installing', 'installed',
        'active', 'reprovision', 'migrating', 'retired', 'decommissioned', 'wiping'
      ]
      states.forEach(s => by_state[s] = 0)
      nodes.forEach(n => by_state[n.state]++)

      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString()
      const discovered_last_hour = nodes.filter(
        n => n.state === 'discovered' && n.created_at > oneHourAgo
      ).length

      return {
        total: nodes.length,
        by_state,
        discovered_last_hour,
        installing_count: by_state.installing,
      }
    },
    staleTime: 30000, // 30 seconds
  })
}

export function useUpdateNodeState() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ nodeId, newState }: { nodeId: string; newState: NodeState }) =>
      nodesApi.updateState(nodeId, newState),
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.detail(nodeId) })
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
    },
  })
}

export function useUpdateNode() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ nodeId, data }: { nodeId: string; data: Partial<Node> }) =>
      nodesApi.update(nodeId, data),
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.detail(nodeId) })
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
    },
  })
}
```

**Step 2: Update hooks/index.ts**

```typescript
export { useWebSocket } from './useWebSocket'
export type { WebSocketEvent } from './useWebSocket'
export {
  useNodes,
  useNode,
  useNodeStats,
  useUpdateNodeState,
  useUpdateNode,
  nodeKeys,
} from './useNodes'
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat(frontend): add React Query hooks for node data fetching"
```

---

## Task 4: Create State Machine Visualization Component

**Files:**
- Create: `frontend/src/components/nodes/StateMachine.tsx`

**Step 1: Create StateMachine.tsx**

```typescript
import { cn } from '@/lib/utils'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, NODE_STATE_TRANSITIONS, type NodeState } from '@/types'

interface StateMachineProps {
  currentState?: NodeState
  onStateClick?: (state: NodeState) => void
  highlightTransitions?: boolean
  className?: string
}

// Position each state on a virtual grid
const STATE_POSITIONS: Record<NodeState, { x: number; y: number }> = {
  discovered: { x: 50, y: 100 },
  ignored: { x: 50, y: 200 },
  pending: { x: 200, y: 100 },
  installing: { x: 350, y: 100 },
  installed: { x: 500, y: 100 },
  active: { x: 650, y: 100 },
  reprovision: { x: 350, y: 200 },
  migrating: { x: 650, y: 200 },
  retired: { x: 650, y: 300 },
  decommissioned: { x: 500, y: 400 },
  wiping: { x: 650, y: 400 },
}

const STATE_RADIUS = 40

function getStateColor(state: NodeState, isCurrent: boolean): string {
  if (isCurrent) {
    return NODE_STATE_COLORS[state].replace('bg-', '')
  }
  return 'gray-300'
}

interface ArrowProps {
  from: NodeState
  to: NodeState
  isHighlighted: boolean
}

function Arrow({ from, to, isHighlighted }: ArrowProps) {
  const fromPos = STATE_POSITIONS[from]
  const toPos = STATE_POSITIONS[to]

  // Calculate direction vector
  const dx = toPos.x - fromPos.x
  const dy = toPos.y - fromPos.y
  const len = Math.sqrt(dx * dx + dy * dy)

  // Normalize and offset by radius
  const nx = dx / len
  const ny = dy / len

  const startX = fromPos.x + nx * STATE_RADIUS
  const startY = fromPos.y + ny * STATE_RADIUS
  const endX = toPos.x - nx * (STATE_RADIUS + 8) // Extra space for arrow head
  const endY = toPos.y - ny * (STATE_RADIUS + 8)

  // Calculate control point for curved arrow (if same row/col)
  const midX = (startX + endX) / 2
  const midY = (startY + endY) / 2

  // Add curve offset for arrows that go backwards
  const curveOffset = dx < 0 || (dx === 0 && dy < 0) ? 30 : 0
  const controlX = midX + ny * curveOffset
  const controlY = midY - nx * curveOffset

  const pathD = curveOffset
    ? `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`
    : `M ${startX} ${startY} L ${endX} ${endY}`

  return (
    <g>
      <defs>
        <marker
          id={`arrow-${from}-${to}`}
          markerWidth="10"
          markerHeight="7"
          refX="9"
          refY="3.5"
          orient="auto"
        >
          <polygon
            points="0 0, 10 3.5, 0 7"
            fill={isHighlighted ? '#3b82f6' : '#9ca3af'}
          />
        </marker>
      </defs>
      <path
        d={pathD}
        fill="none"
        stroke={isHighlighted ? '#3b82f6' : '#d1d5db'}
        strokeWidth={isHighlighted ? 2 : 1}
        markerEnd={`url(#arrow-${from}-${to})`}
      />
    </g>
  )
}

interface StateNodeProps {
  state: NodeState
  isCurrent: boolean
  isReachable: boolean
  onClick?: () => void
}

function StateNode({ state, isCurrent, isReachable, onClick }: StateNodeProps) {
  const pos = STATE_POSITIONS[state]
  const baseColor = NODE_STATE_COLORS[state].replace('bg-', '')

  // Map Tailwind colors to actual hex values
  const colorMap: Record<string, string> = {
    'blue-500': '#3b82f6',
    'gray-500': '#6b7280',
    'yellow-500': '#eab308',
    'orange-500': '#f97316',
    'teal-500': '#14b8a6',
    'green-500': '#22c55e',
    'purple-500': '#a855f7',
    'indigo-500': '#6366f1',
    'gray-600': '#4b5563',
    'gray-700': '#374151',
    'red-500': '#ef4444',
  }

  const fillColor = isCurrent ? colorMap[baseColor] : (isReachable ? '#e5e7eb' : '#f3f4f6')
  const strokeColor = isCurrent ? colorMap[baseColor] : (isReachable ? '#3b82f6' : '#d1d5db')
  const textColor = isCurrent ? '#ffffff' : '#374151'

  return (
    <g
      className={cn(
        'transition-all',
        onClick && isReachable && 'cursor-pointer hover:opacity-80'
      )}
      onClick={onClick && isReachable ? onClick : undefined}
    >
      <circle
        cx={pos.x}
        cy={pos.y}
        r={STATE_RADIUS}
        fill={fillColor}
        stroke={strokeColor}
        strokeWidth={isCurrent ? 3 : isReachable ? 2 : 1}
        strokeDasharray={isReachable && !isCurrent ? '4 2' : undefined}
      />
      <text
        x={pos.x}
        y={pos.y}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={textColor}
        fontSize="10"
        fontWeight={isCurrent ? 'bold' : 'normal'}
      >
        {NODE_STATE_LABELS[state]}
      </text>
    </g>
  )
}

export function StateMachine({
  currentState,
  onStateClick,
  highlightTransitions = true,
  className,
}: StateMachineProps) {
  const reachableStates = currentState
    ? new Set(NODE_STATE_TRANSITIONS[currentState])
    : new Set<NodeState>()

  const allStates = Object.keys(STATE_POSITIONS) as NodeState[]

  // Generate all arrows
  const arrows: { from: NodeState; to: NodeState }[] = []
  for (const [from, toStates] of Object.entries(NODE_STATE_TRANSITIONS)) {
    for (const to of toStates) {
      arrows.push({ from: from as NodeState, to })
    }
  }

  return (
    <div className={cn('overflow-auto', className)}>
      <svg viewBox="0 0 750 480" className="w-full h-auto min-w-[600px]">
        {/* Render arrows first (behind nodes) */}
        {arrows.map(({ from, to }) => (
          <Arrow
            key={`${from}-${to}`}
            from={from}
            to={to}
            isHighlighted={highlightTransitions && currentState === from}
          />
        ))}

        {/* Render state nodes */}
        {allStates.map((state) => (
          <StateNode
            key={state}
            state={state}
            isCurrent={currentState === state}
            isReachable={reachableStates.has(state)}
            onClick={onStateClick ? () => onStateClick(state) : undefined}
          />
        ))}

        {/* Legend */}
        <g transform="translate(20, 440)">
          <text x="0" y="0" fontSize="10" fill="#6b7280">
            Click a reachable state (dashed border) to transition
          </text>
        </g>
      </svg>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/nodes/
git commit -m "feat(frontend): add state machine visualization component"
```

---

## Task 5: Create Node Table with Virtual Scrolling

**Files:**
- Create: `frontend/src/components/nodes/NodeTable.tsx`

**Step 1: Create NodeTable.tsx**

```typescript
import { useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Badge, Button, Input } from '@/components/ui'
import { Search, ChevronUp, ChevronDown, Filter } from 'lucide-react'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, type Node, type NodeState } from '@/types'

interface NodeTableProps {
  nodes: Node[]
  isLoading?: boolean
  onStateFilter?: (state: NodeState | null) => void
  selectedState?: NodeState | null
}

type SortField = 'hostname' | 'mac_address' | 'state' | 'arch' | 'last_seen_at'
type SortDirection = 'asc' | 'desc'

function StateBadge({ state }: { state: NodeState }) {
  return (
    <Badge
      variant="outline"
      className={cn('border-0 text-white', NODE_STATE_COLORS[state])}
    >
      {NODE_STATE_LABELS[state]}
    </Badge>
  )
}

function formatLastSeen(dateStr: string | null): string {
  if (!dateStr) return 'Never'

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export function NodeTable({
  nodes,
  isLoading,
  onStateFilter,
  selectedState,
}: NodeTableProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('hostname')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')

  // Filter nodes by search
  const filteredNodes = nodes.filter((node) => {
    const searchLower = search.toLowerCase()
    return (
      (node.hostname?.toLowerCase().includes(searchLower) ?? false) ||
      node.mac_address.toLowerCase().includes(searchLower) ||
      node.state.toLowerCase().includes(searchLower) ||
      (node.ip_address?.toLowerCase().includes(searchLower) ?? false)
    )
  })

  // Sort nodes
  const sortedNodes = [...filteredNodes].sort((a, b) => {
    let aVal: string | null = ''
    let bVal: string | null = ''

    switch (sortField) {
      case 'hostname':
        aVal = a.hostname ?? ''
        bVal = b.hostname ?? ''
        break
      case 'mac_address':
        aVal = a.mac_address
        bVal = b.mac_address
        break
      case 'state':
        aVal = a.state
        bVal = b.state
        break
      case 'arch':
        aVal = a.arch
        bVal = b.arch
        break
      case 'last_seen_at':
        aVal = a.last_seen_at ?? ''
        bVal = b.last_seen_at ?? ''
        break
    }

    const cmp = (aVal ?? '').localeCompare(bVal ?? '')
    return sortDirection === 'asc' ? cmp : -cmp
  })

  const rowVirtualizer = useVirtualizer({
    count: sortedNodes.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 52,
    overscan: 10,
  })

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return null
    return sortDirection === 'asc' ? (
      <ChevronUp className="h-4 w-4" />
    ) : (
      <ChevronDown className="h-4 w-4" />
    )
  }

  const allStates: NodeState[] = [
    'discovered', 'ignored', 'pending', 'installing', 'installed',
    'active', 'reprovision', 'migrating', 'retired', 'decommissioned', 'wiping'
  ]

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by hostname, MAC, IP..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        {onStateFilter && (
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <div className="flex flex-wrap gap-1">
              <Button
                variant={selectedState === null ? 'default' : 'outline'}
                size="sm"
                onClick={() => onStateFilter(null)}
              >
                All
              </Button>
              {allStates.map((state) => (
                <Button
                  key={state}
                  variant={selectedState === state ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => onStateFilter(state)}
                  className={cn(
                    selectedState === state && NODE_STATE_COLORS[state],
                    selectedState === state && 'text-white border-0'
                  )}
                >
                  {NODE_STATE_LABELS[state]}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="rounded-md border">
        {/* Header */}
        <div className="flex border-b bg-muted/50 text-sm font-medium">
          <button
            className="flex-1 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('hostname')}
          >
            Hostname <SortIcon field="hostname" />
          </button>
          <button
            className="w-40 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('mac_address')}
          >
            MAC Address <SortIcon field="mac_address" />
          </button>
          <button
            className="w-32 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('state')}
          >
            State <SortIcon field="state" />
          </button>
          <button
            className="w-24 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('arch')}
          >
            Arch <SortIcon field="arch" />
          </button>
          <button
            className="w-28 p-3 text-left flex items-center gap-1 hover:bg-muted"
            onClick={() => handleSort('last_seen_at')}
          >
            Last Seen <SortIcon field="last_seen_at" />
          </button>
        </div>

        {/* Virtual scrolling body */}
        <div
          ref={parentRef}
          className="h-[500px] overflow-auto"
        >
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              Loading nodes...
            </div>
          ) : sortedNodes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              No nodes found
            </div>
          ) : (
            <div
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                width: '100%',
                position: 'relative',
              }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const node = sortedNodes[virtualRow.index]
                return (
                  <Link
                    key={node.id}
                    to={`/nodes/${node.id}`}
                    className="absolute left-0 right-0 flex items-center border-b last:border-0 hover:bg-muted/50"
                    style={{
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    <div className="flex-1 p-3 text-sm font-medium truncate">
                      {node.hostname || (
                        <span className="text-muted-foreground">(undiscovered)</span>
                      )}
                    </div>
                    <div className="w-40 p-3 text-sm font-mono text-muted-foreground">
                      {node.mac_address}
                    </div>
                    <div className="w-32 p-3">
                      <StateBadge state={node.state} />
                    </div>
                    <div className="w-24 p-3 text-sm">{node.arch}</div>
                    <div className="w-28 p-3 text-sm text-muted-foreground">
                      {formatLastSeen(node.last_seen_at)}
                    </div>
                  </Link>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Footer with count */}
      <div className="text-sm text-muted-foreground">
        Showing {sortedNodes.length} of {nodes.length} nodes
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/nodes/
git commit -m "feat(frontend): add node table with virtual scrolling and filtering"
```

---

## Task 6: Create Node Detail Page

**Files:**
- Create: `frontend/src/pages/NodeDetail.tsx`
- Modify: `frontend/src/pages/index.ts`

**Step 1: Create NodeDetail.tsx**

```typescript
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Server, Clock, Cpu, HardDrive, Network, Tag } from 'lucide-react'
import { Button, Card, CardContent, CardHeader, CardTitle, Badge, Separator } from '@/components/ui'
import { StateMachine } from '@/components/nodes/StateMachine'
import { useNode, useUpdateNodeState } from '@/hooks'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, NODE_STATE_TRANSITIONS, type NodeState } from '@/types'
import { cn } from '@/lib/utils'

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'N/A'
  return new Date(dateStr).toLocaleString()
}

export function NodeDetail() {
  const { nodeId } = useParams<{ nodeId: string }>()
  const { data: response, isLoading, error } = useNode(nodeId ?? '')
  const updateState = useUpdateNodeState()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading node details...</div>
      </div>
    )
  }

  if (error || !response?.data) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" asChild>
          <Link to="/nodes">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Nodes
          </Link>
        </Button>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-destructive">
              {error instanceof Error ? error.message : 'Node not found'}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const node = response.data
  const validTransitions = NODE_STATE_TRANSITIONS[node.state] ?? []

  const handleStateTransition = (newState: NodeState) => {
    if (!validTransitions.includes(newState)) return

    // For wiping, would need confirmation dialog - simplified for now
    if (newState === 'wiping') {
      if (!confirm('This will securely erase all data on this node. Are you sure?')) {
        return
      }
    }

    updateState.mutate({ nodeId: node.id, newState })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" asChild>
            <Link to="/nodes">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h2 className="text-2xl font-bold">
              {node.hostname || node.mac_address}
            </h2>
            <p className="text-muted-foreground">
              {node.hostname ? node.mac_address : 'Hostname not assigned'}
            </p>
          </div>
        </div>
        <Badge
          variant="outline"
          className={cn('text-lg px-4 py-1 border-0 text-white', NODE_STATE_COLORS[node.state])}
        >
          {NODE_STATE_LABELS[node.state]}
        </Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left column - Node info */}
        <div className="space-y-6">
          {/* Basic Info */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                Node Information
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Hostname</div>
                  <div className="font-medium">{node.hostname || 'Not assigned'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">IP Address</div>
                  <div className="font-medium font-mono">{node.ip_address || 'N/A'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">MAC Address</div>
                  <div className="font-medium font-mono">{node.mac_address}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">System UUID</div>
                  <div className="font-medium font-mono text-xs">{node.system_uuid || 'N/A'}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Hardware Info */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5" />
                Hardware
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Architecture</div>
                  <div className="font-medium">{node.arch}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Boot Mode</div>
                  <div className="font-medium uppercase">{node.boot_mode}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Vendor</div>
                  <div className="font-medium">{node.vendor || 'Unknown'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Model</div>
                  <div className="font-medium">{node.model || 'Unknown'}</div>
                </div>
                <div className="col-span-2">
                  <div className="text-muted-foreground">Serial Number</div>
                  <div className="font-medium font-mono">{node.serial_number || 'N/A'}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Timestamps */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Timeline
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">First Discovered</div>
                  <div className="font-medium">{formatDate(node.created_at)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Last Updated</div>
                  <div className="font-medium">{formatDate(node.updated_at)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Last Seen</div>
                  <div className="font-medium">{formatDate(node.last_seen_at)}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Tags */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Tag className="h-5 w-5" />
                Tags
              </CardTitle>
            </CardHeader>
            <CardContent>
              {node.tags.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {node.tags.map((tag) => (
                    <Badge key={tag} variant="secondary">{tag}</Badge>
                  ))}
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">No tags assigned</div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column - State machine */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Network className="h-5 w-5" />
                State Machine
              </CardTitle>
            </CardHeader>
            <CardContent>
              <StateMachine
                currentState={node.state}
                onStateClick={handleStateTransition}
                highlightTransitions={true}
              />

              <Separator className="my-4" />

              <div className="space-y-2">
                <div className="text-sm font-medium">Available Transitions</div>
                {validTransitions.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {validTransitions.map((state) => (
                      <Button
                        key={state}
                        variant="outline"
                        size="sm"
                        onClick={() => handleStateTransition(state)}
                        disabled={updateState.isPending}
                        className={cn(
                          'hover:text-white',
                          `hover:${NODE_STATE_COLORS[state]}`
                        )}
                      >
                        Transition to {NODE_STATE_LABELS[state]}
                      </Button>
                    ))}
                  </div>
                ) : (
                  <div className="text-muted-foreground text-sm">
                    No transitions available from this state
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Workflow assignment placeholder */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HardDrive className="h-5 w-5" />
                Workflow
              </CardTitle>
            </CardHeader>
            <CardContent>
              {node.workflow_id ? (
                <div className="text-sm">
                  <span className="text-muted-foreground">Assigned: </span>
                  <span className="font-medium">{node.workflow_id}</span>
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">
                  No workflow assigned
                </div>
              )}
              <Button variant="outline" size="sm" className="mt-4" disabled>
                Assign Workflow (Coming Soon)
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Update pages/index.ts**

```typescript
export { Dashboard } from './Dashboard'
export { Login } from './Login'
export { Nodes } from './Nodes'
export { NodeDetail } from './NodeDetail'
export { NotFound } from './NotFound'
```

**Step 3: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat(frontend): add node detail page with state machine"
```

---

## Task 7: Update Dashboard with Live Stats

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Replace Dashboard.tsx with real data version**

```typescript
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { Server, Activity, AlertCircle, CheckCircle, Clock, ArrowRight } from 'lucide-react'
import { useNodeStats, useNodes } from '@/hooks'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, type NodeState } from '@/types'
import { cn } from '@/lib/utils'

function StatCard({
  title,
  value,
  description,
  icon: Icon,
  iconColor,
  isLoading,
}: {
  title: string
  value: number
  description: string
  icon: React.ElementType
  iconColor: string
  isLoading?: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={cn('h-4 w-4', iconColor)} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {isLoading ? '...' : value}
        </div>
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

export function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useNodeStats()
  const { data: discoveredResponse, isLoading: discoveredLoading } = useNodes({
    state: 'discovered',
    limit: 5,
  })
  const { data: installingResponse, isLoading: installingLoading } = useNodes({
    state: 'installing',
    limit: 5,
  })

  const discoveredNodes = discoveredResponse?.data ?? []
  const installingNodes = installingResponse?.data ?? []

  // State breakdown for chart
  const stateBreakdown: { state: NodeState; count: number }[] = stats
    ? (Object.entries(stats.by_state) as [NodeState, number][])
        .filter(([_, count]) => count > 0)
        .map(([state, count]) => ({ state, count }))
        .sort((a, b) => b.count - a.count)
    : []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
        <Link
          to="/nodes"
          className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1"
        >
          View all nodes <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Nodes"
          value={stats?.total ?? 0}
          description="Across all states"
          icon={Server}
          iconColor="text-muted-foreground"
          isLoading={statsLoading}
        />
        <StatCard
          title="Active"
          value={stats?.by_state.active ?? 0}
          description="Running in production"
          icon={CheckCircle}
          iconColor="text-green-500"
          isLoading={statsLoading}
        />
        <StatCard
          title="Discovered"
          value={stats?.discovered_last_hour ?? 0}
          description="New in last hour"
          icon={AlertCircle}
          iconColor="text-blue-500"
          isLoading={statsLoading}
        />
        <StatCard
          title="Installing"
          value={stats?.installing_count ?? 0}
          description="In progress"
          icon={Activity}
          iconColor="text-orange-500"
          isLoading={statsLoading}
        />
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* State breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Nodes by State</CardTitle>
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : stateBreakdown.length === 0 ? (
              <div className="text-muted-foreground">No nodes</div>
            ) : (
              <div className="space-y-2">
                {stateBreakdown.map(({ state, count }) => (
                  <div key={state} className="flex items-center gap-2">
                    <div
                      className={cn('w-3 h-3 rounded-full', NODE_STATE_COLORS[state])}
                    />
                    <div className="flex-1 text-sm">{NODE_STATE_LABELS[state]}</div>
                    <div className="text-sm font-medium">{count}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* New discoveries */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>New Discoveries</CardTitle>
            <AlertCircle className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            {discoveredLoading ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : discoveredNodes.length === 0 ? (
              <div className="text-muted-foreground text-sm">
                No new nodes discovered
              </div>
            ) : (
              <div className="space-y-3">
                {discoveredNodes.map((node) => (
                  <Link
                    key={node.id}
                    to={`/nodes/${node.id}`}
                    className="block hover:bg-muted -mx-2 px-2 py-1 rounded"
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-mono text-sm">{node.mac_address}</div>
                      <div className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatTimeAgo(node.created_at)}
                      </div>
                    </div>
                    {node.vendor && (
                      <div className="text-xs text-muted-foreground">{node.vendor}</div>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Installing now */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Installing Now</CardTitle>
            <Activity className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            {installingLoading ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : installingNodes.length === 0 ? (
              <div className="text-muted-foreground text-sm">
                No installations in progress
              </div>
            ) : (
              <div className="space-y-3">
                {installingNodes.map((node) => (
                  <Link
                    key={node.id}
                    to={`/nodes/${node.id}`}
                    className="block hover:bg-muted -mx-2 px-2 py-1 rounded"
                  >
                    <div className="font-medium text-sm">
                      {node.hostname || node.mac_address}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Started {formatTimeAgo(node.updated_at)}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): update dashboard with live node stats"
```

---

## Task 8: Update Nodes Page with New Table

**Files:**
- Modify: `frontend/src/pages/Nodes.tsx`

**Step 1: Replace Nodes.tsx with new implementation**

```typescript
import { useState } from 'react'
import { Card, CardContent, CardHeader, Button } from '@/components/ui'
import { Plus, RefreshCw } from 'lucide-react'
import { NodeTable } from '@/components/nodes/NodeTable'
import { useNodes } from '@/hooks'
import type { NodeState } from '@/types'

export function Nodes() {
  const [stateFilter, setStateFilter] = useState<NodeState | null>(null)

  const { data: response, isLoading, refetch, isFetching } = useNodes(
    stateFilter ? { state: stateFilter, limit: 1000 } : { limit: 1000 }
  )

  const nodes = response?.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Nodes</h2>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          </Button>
          <Button disabled>
            <Plus className="mr-2 h-4 w-4" />
            Register Node
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-0" />
        <CardContent>
          <NodeTable
            nodes={nodes}
            isLoading={isLoading}
            onStateFilter={setStateFilter}
            selectedState={stateFilter}
          />
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Nodes.tsx
git commit -m "feat(frontend): update nodes page with new table component"
```

---

## Task 9: Add Node Detail Route

**Files:**
- Modify: `frontend/src/router.tsx`

**Step 1: Update router.tsx to include node detail route**

```typescript
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout'
import { Dashboard, Login, Nodes, NodeDetail, NotFound } from '@/pages'
import { useAuthStore } from '@/stores'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <PublicRoute>
        <Login />
      </PublicRoute>
    ),
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
      { path: 'groups', element: <div>Device Groups (Coming Soon)</div> },
      { path: 'workflows', element: <div>Workflows (Coming Soon)</div> },
      { path: 'templates', element: <div>Templates (Coming Soon)</div> },
      { path: 'hypervisors', element: <div>Hypervisors (Coming Soon)</div> },
      { path: 'storage', element: <div>Storage (Coming Soon)</div> },
      { path: 'approvals', element: <div>Approvals (Coming Soon)</div> },
      { path: 'activity', element: <div>Activity Log (Coming Soon)</div> },
      { path: 'settings', element: <div>Settings (Coming Soon)</div> },
      { path: 'users', element: <div>Users & Roles (Coming Soon)</div> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
```

**Step 2: Commit**

```bash
git add frontend/src/router.tsx
git commit -m "feat(frontend): add node detail route"
```

---

## Task 10: Create Component Index for Nodes

**Files:**
- Create: `frontend/src/components/nodes/index.ts`

**Step 1: Create index.ts**

```typescript
export { StateMachine } from './StateMachine'
export { NodeTable } from './NodeTable'
```

**Step 2: Commit**

```bash
git add frontend/src/components/nodes/
git commit -m "feat(frontend): add nodes components index"
```

---

## Task 11: Add WebSocket Integration for Real-time Updates

**Files:**
- Create: `frontend/src/hooks/useNodeUpdates.ts`
- Modify: `frontend/src/hooks/index.ts`

**Step 1: Create useNodeUpdates.ts**

```typescript
import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useWebSocket, type WebSocketEvent } from './useWebSocket'
import { nodeKeys } from './useNodes'

export function useNodeUpdates() {
  const queryClient = useQueryClient()

  const handleMessage = useCallback((event: WebSocketEvent) => {
    switch (event.type) {
      case 'node.created':
        // Invalidate node list to show new node
        queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
        queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
        break

      case 'node.state_changed':
        // Invalidate specific node and lists
        queryClient.invalidateQueries({ queryKey: nodeKeys.detail(event.data.id) })
        queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
        queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
        break

      case 'node.updated':
        // Invalidate specific node
        queryClient.invalidateQueries({ queryKey: nodeKeys.detail(event.data.id) })
        queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
        break
    }
  }, [queryClient])

  const { isConnected, reconnect } = useWebSocket({
    onMessage: handleMessage,
    onConnect: () => {
      console.log('WebSocket connected - real-time updates enabled')
    },
    onDisconnect: () => {
      console.log('WebSocket disconnected')
    },
  })

  return { isConnected, reconnect }
}
```

**Step 2: Update hooks/index.ts**

```typescript
export { useWebSocket } from './useWebSocket'
export type { WebSocketEvent } from './useWebSocket'
export {
  useNodes,
  useNode,
  useNodeStats,
  useUpdateNodeState,
  useUpdateNode,
  nodeKeys,
} from './useNodes'
export { useNodeUpdates } from './useNodeUpdates'
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat(frontend): add WebSocket integration for real-time node updates"
```

---

## Task 12: Add WebSocket Provider to App

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Update App.tsx to use WebSocket updates**

```typescript
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { router } from './router'
import { useNodeUpdates } from '@/hooks'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60, // 1 minute
      retry: 1,
    },
  },
})

function WebSocketProvider({ children }: { children: React.ReactNode }) {
  useNodeUpdates()
  return <>{children}</>
}

function AppContent() {
  return (
    <WebSocketProvider>
      <RouterProvider router={router} />
    </WebSocketProvider>
  )
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): integrate WebSocket provider for real-time updates"
```

---

## Task 13: Final Verification and Push

**Step 1: Verify all files are committed**

```bash
git status
```

**Step 2: Push the updated feature branch**

```bash
git push origin feature/web-ui
```

---

## Phase 2 Complete

**What was built:**
- State machine types with valid transitions
- React Query hooks for nodes (list, detail, stats, mutations)
- Interactive SVG state machine visualization
- Virtual scrolling node table (supports 500+ nodes)
- Node detail page with full information
- Dashboard with live stats from API
- State filter buttons
- WebSocket integration for real-time updates
- Proper React Query cache invalidation

**Next Phase:** Groups & Bulk Operations (Device groups CRUD, bulk selection, group assignment)
