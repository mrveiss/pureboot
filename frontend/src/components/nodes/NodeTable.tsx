import { useRef, useState, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Badge, Button, Input, Checkbox } from '@/components/ui'
import { Search, ChevronUp, ChevronDown, Filter } from 'lucide-react'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, type Node, type NodeState } from '@/types'
import { useSelectionStore } from '@/stores'

interface NodeTableProps {
  nodes: Node[]
  isLoading?: boolean
  onStateFilter?: (state: NodeState | null) => void
  selectedState?: NodeState | null
  enableSelection?: boolean
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
  enableSelection = true,
}: NodeTableProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('hostname')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')

  const {
    selectedNodeIds,
    isAllSelected,
    toggleNode,
    selectAll,
    deselectAll,
    setTotalNodes,
  } = useSelectionStore()

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

  // Update total nodes count for selection store
  useEffect(() => {
    setTotalNodes(sortedNodes.length)
  }, [sortedNodes.length, setTotalNodes])

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

  const handleSelectAll = () => {
    if (isAllSelected) {
      deselectAll()
    } else {
      selectAll(sortedNodes.map(n => n.id))
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

  const someSelected = selectedNodeIds.size > 0 && !isAllSelected

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
          {enableSelection && (
            <div className="w-12 p-3 flex items-center justify-center">
              <Checkbox
                checked={isAllSelected}
                indeterminate={someSelected}
                onCheckedChange={handleSelectAll}
              />
            </div>
          )}
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
                const isSelected = selectedNodeIds.has(node.id)
                return (
                  <div
                    key={node.id}
                    className={cn(
                      'absolute left-0 right-0 flex items-center border-b last:border-0',
                      isSelected ? 'bg-muted/50' : 'hover:bg-muted/30'
                    )}
                    style={{
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    {enableSelection && (
                      <div
                        className="w-12 p-3 flex items-center justify-center"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={() => toggleNode(node.id)}
                        />
                      </div>
                    )}
                    <Link
                      to={`/nodes/${node.id}`}
                      className="flex-1 flex items-center"
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
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Footer with count */}
      <div className="text-sm text-muted-foreground">
        Showing {sortedNodes.length} of {nodes.length} nodes
        {selectedNodeIds.size > 0 && ` · ${selectedNodeIds.size} selected`}
      </div>
    </div>
  )
}
