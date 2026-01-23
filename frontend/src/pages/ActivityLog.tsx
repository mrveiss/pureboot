import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  ArrowRight,
  Clock,
  Server,
  RefreshCw,
  Filter,
  X,
} from 'lucide-react'
import {
  Card,
  CardContent,
  Button,
  Badge,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { useActivity } from '@/hooks'
import type { ActivityEntry, ActivityFilters } from '@/types'
import { ACTIVITY_TYPE_LABELS, EVENT_TYPE_LABELS, NODE_STATE_LABELS } from '@/types'
import { cn } from '@/lib/utils'

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

function formatFullTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}

function getActivityIcon(entry: ActivityEntry) {
  if (entry.type === 'state_change') {
    return <ArrowRight className="h-4 w-4" />
  }
  return <Activity className="h-4 w-4" />
}

function getActivityColor(entry: ActivityEntry): string {
  if (entry.type === 'state_change') {
    if (entry.category.includes('active')) return 'bg-green-500'
    if (entry.category.includes('installing')) return 'bg-blue-500'
    if (entry.category.includes('failed')) return 'bg-red-500'
    if (entry.category.includes('retired')) return 'bg-gray-500'
    return 'bg-yellow-500'
  }

  // Node events
  const eventType = entry.category
  if (eventType.includes('complete') || eventType === 'first_boot') return 'bg-green-500'
  if (eventType.includes('failed')) return 'bg-red-500'
  if (eventType.includes('progress') || eventType.includes('started')) return 'bg-blue-500'
  if (eventType === 'heartbeat') return 'bg-gray-400'
  return 'bg-yellow-500'
}

function getCategoryLabel(entry: ActivityEntry): string {
  if (entry.type === 'state_change') {
    // Parse "from_state → to_state" format
    const parts = entry.category.split(' → ')
    if (parts.length === 2) {
      const from = NODE_STATE_LABELS[parts[0]] || parts[0]
      const to = NODE_STATE_LABELS[parts[1]] || parts[1]
      return `${from} → ${to}`
    }
    return entry.category
  }
  return EVENT_TYPE_LABELS[entry.category] || entry.category.replace(/_/g, ' ')
}

export function ActivityLog() {
  const [filters, setFilters] = useState<ActivityFilters>({ limit: 100 })
  const { data: response, isLoading, refetch, isFetching } = useActivity(filters)

  const entries = response?.data ?? []
  const total = response?.total ?? 0

  const clearFilters = () => {
    setFilters({ limit: 100 })
  }

  const hasFilters = filters.type || filters.event_type

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Activity Log</h2>
        <Button
          variant="outline"
          size="icon"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Filters:</span>
            </div>

            <Select
              value={filters.type || 'all'}
              onValueChange={(v) => setFilters({ ...filters, type: v === 'all' ? undefined : v as ActivityFilters['type'] })}
            >
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="All types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                <SelectItem value="state_change">State Changes</SelectItem>
                <SelectItem value="node_event">Node Events</SelectItem>
              </SelectContent>
            </Select>

            {filters.type === 'node_event' && (
              <Select
                value={filters.event_type || 'all'}
                onValueChange={(v) => setFilters({ ...filters, event_type: v === 'all' ? undefined : v })}
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="All events" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Events</SelectItem>
                  {Object.entries(EVENT_TYPE_LABELS).map(([key, label]) => (
                    <SelectItem key={key} value={key}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}

            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-4 w-4 mr-1" />
                Clear
              </Button>
            )}

            <div className="ml-auto text-sm text-muted-foreground">
              Showing {entries.length} of {total} entries
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Timeline */}
      {isLoading ? (
        <div className="text-muted-foreground">Loading activity...</div>
      ) : entries.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <Activity className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No activity recorded yet.</p>
              <p className="text-sm mt-1">Activity will appear here as nodes report events and state changes.</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-6 top-0 bottom-0 w-px bg-border" />

          <div className="space-y-4">
            {entries.map((entry) => (
              <div key={entry.id} className="relative flex gap-4 pl-4">
                {/* Timeline dot */}
                <div
                  className={cn(
                    'absolute left-4 w-5 h-5 rounded-full flex items-center justify-center text-white z-10',
                    getActivityColor(entry)
                  )}
                >
                  {getActivityIcon(entry)}
                </div>

                {/* Content */}
                <Card className="flex-1 ml-8">
                  <CardContent className="pt-4 pb-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge variant="outline" className="text-xs">
                            {ACTIVITY_TYPE_LABELS[entry.type] || entry.type}
                          </Badge>
                          <span className="font-medium">{getCategoryLabel(entry)}</span>
                        </div>

                        <p className="text-sm text-muted-foreground mt-1">
                          {entry.message}
                        </p>

                        {entry.node_id && (
                          <div className="flex items-center gap-2 mt-2 text-sm">
                            <Server className="h-3 w-3 text-muted-foreground" />
                            <Link
                              to={`/nodes/${entry.node_id}`}
                              className="text-primary hover:underline"
                            >
                              {entry.node_name || entry.node_id}
                            </Link>
                          </div>
                        )}

                        {entry.details && Object.keys(entry.details).length > 0 && (
                          <div className="mt-2 text-xs text-muted-foreground">
                            {entry.details.ip_address && (
                              <span className="mr-3">IP: {String(entry.details.ip_address)}</span>
                            )}
                            {entry.details.progress !== undefined && (
                              <span className="mr-3">Progress: {entry.details.progress}%</span>
                            )}
                            {entry.triggered_by && (
                              <span>By: {entry.triggered_by}</span>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-1 text-xs text-muted-foreground shrink-0">
                        <Clock className="h-3 w-3" />
                        <span title={formatFullTimestamp(entry.timestamp)}>
                          {formatTimestamp(entry.timestamp)}
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
