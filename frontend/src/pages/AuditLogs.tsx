import { useState, useEffect } from 'react'
import { auditApi } from '@/api'
import type { AuditLog, AuditFilters, AuditLogListResponse } from '@/types'
import { AUDIT_RESULT_COLORS, AUDIT_ACTOR_TYPE_LABELS } from '@/types/audit'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Input,
} from '@/components/ui'
import {
  ChevronDown,
  ChevronRight,
  Search,
  FileText,
  RefreshCw,
  Filter,
  X,
  ChevronLeft,
  ChevronsLeft,
  ChevronsRight,
  Calendar,
} from 'lucide-react'
import { cn } from '@/lib/utils'

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString()
}

function formatRelativeTime(timestamp: string): string {
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

function getActionBadgeColor(action: string): string {
  if (action.startsWith('create') || action.startsWith('add')) {
    return 'bg-green-100 text-green-800'
  }
  if (action.startsWith('delete') || action.startsWith('remove')) {
    return 'bg-red-100 text-red-800'
  }
  if (action.startsWith('update') || action.startsWith('edit') || action.startsWith('change')) {
    return 'bg-blue-100 text-blue-800'
  }
  if (action.startsWith('login') || action.startsWith('auth')) {
    return 'bg-purple-100 text-purple-800'
  }
  if (action.startsWith('approve') || action.startsWith('reject')) {
    return 'bg-orange-100 text-orange-800'
  }
  return 'bg-gray-100 text-gray-800'
}

const PAGE_SIZES = [25, 50, 100]

export function AuditLogs() {
  const [data, setData] = useState<AuditLogListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [filters, setFilters] = useState<AuditFilters>({})
  const [actions, setActions] = useState<string[]>([])
  const [resourceTypes, setResourceTypes] = useState<string[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [actorSearch, setActorSearch] = useState('')
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Load filter options on mount
  useEffect(() => {
    async function loadFilterOptions() {
      try {
        const [actionsRes, resourceTypesRes] = await Promise.all([
          auditApi.getActions(),
          auditApi.getResourceTypes(),
        ])
        setActions(actionsRes.actions)
        setResourceTypes(resourceTypesRes.resource_types)
      } catch (error) {
        console.error('Failed to load filter options:', error)
      }
    }
    loadFilterOptions()
  }, [])

  // Load data when page, pageSize, or filters change
  useEffect(() => {
    async function loadData() {
      setLoading(true)
      try {
        const result = await auditApi.list(page, pageSize, filters)
        setData(result)
      } catch (error) {
        console.error('Failed to load audit logs:', error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [page, pageSize, filters])

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      const result = await auditApi.list(page, pageSize, filters)
      setData(result)
    } catch (error) {
      console.error('Failed to refresh audit logs:', error)
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleActorSearch = () => {
    if (actorSearch.trim()) {
      setFilters({ ...filters, actor_username: actorSearch.trim() })
      setPage(1)
    }
  }

  const clearFilters = () => {
    setFilters({})
    setActorSearch('')
    setPage(1)
  }

  const hasFilters = filters.action || filters.resource_type || filters.result ||
                     filters.actor_username || filters.from_date || filters.to_date

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0
  const logs = data?.items ?? []

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Audit Logs</h2>
        <Button
          variant="outline"
          size="icon"
          onClick={handleRefresh}
          disabled={isRefreshing}
        >
          <RefreshCw className={isRefreshing ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
        </Button>
      </div>

      <p className="text-muted-foreground">
        View and search through security audit logs. All user actions and system events are recorded here.
      </p>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Filters:</span>
            </div>

            {/* Action filter */}
            <Select
              value={filters.action || 'all'}
              onValueChange={(v) => {
                setFilters({ ...filters, action: v === 'all' ? undefined : v })
                setPage(1)
              }}
            >
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="All actions" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Actions</SelectItem>
                {actions.map((action) => (
                  <SelectItem key={action} value={action}>
                    {action.replace(/_/g, ' ')}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Resource type filter */}
            <Select
              value={filters.resource_type || 'all'}
              onValueChange={(v) => {
                setFilters({ ...filters, resource_type: v === 'all' ? undefined : v })
                setPage(1)
              }}
            >
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="All resources" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Resources</SelectItem>
                {resourceTypes.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type.replace(/_/g, ' ')}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Result filter */}
            <Select
              value={filters.result || 'all'}
              onValueChange={(v) => {
                setFilters({ ...filters, result: v === 'all' ? undefined : v })
                setPage(1)
              }}
            >
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="All results" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Results</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="failure">Failure</SelectItem>
                <SelectItem value="denied">Denied</SelectItem>
              </SelectContent>
            </Select>

            {/* Actor username search */}
            <div className="flex items-center gap-1">
              <Input
                placeholder="Actor username..."
                value={actorSearch}
                onChange={(e) => setActorSearch(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleActorSearch()}
                className="w-[160px]"
              />
              <Button variant="outline" size="icon" onClick={handleActorSearch}>
                <Search className="h-4 w-4" />
              </Button>
            </div>

            {/* Date range filters */}
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <Input
                type="date"
                placeholder="From"
                value={filters.from_date || ''}
                onChange={(e) => {
                  setFilters({ ...filters, from_date: e.target.value || undefined })
                  setPage(1)
                }}
                className="w-[140px]"
              />
              <span className="text-muted-foreground">to</span>
              <Input
                type="date"
                placeholder="To"
                value={filters.to_date || ''}
                onChange={(e) => {
                  setFilters({ ...filters, to_date: e.target.value || undefined })
                  setPage(1)
                }}
                className="w-[140px]"
              />
            </div>

            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-4 w-4 mr-1" />
                Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Audit Logs Table */}
      {loading ? (
        <div className="text-muted-foreground">Loading audit logs...</div>
      ) : logs.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <FileText className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>No audit logs found.</p>
              <p className="text-sm mt-1">
                {hasFilters
                  ? 'Try adjusting your filters to see more results.'
                  : 'Audit logs will appear here as actions are performed.'}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-medium">
              Showing {logs.length} of {data?.total ?? 0} entries
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {/* Table Header */}
            <div className="grid grid-cols-[40px_180px_150px_120px_1fr_100px_120px] gap-2 px-4 py-3 bg-muted/50 border-b text-sm font-medium text-muted-foreground">
              <div></div>
              <div>Timestamp</div>
              <div>Actor</div>
              <div>Action</div>
              <div>Resource</div>
              <div>Result</div>
              <div>IP Address</div>
            </div>

            {/* Table Rows */}
            <div className="divide-y">
              {logs.map((log) => (
                <div key={log.id}>
                  {/* Main Row */}
                  <div
                    className={cn(
                      'grid grid-cols-[40px_180px_150px_120px_1fr_100px_120px] gap-2 px-4 py-3 items-center hover:bg-muted/30 cursor-pointer',
                      expandedId === log.id && 'bg-muted/30'
                    )}
                    onClick={() => toggleExpand(log.id)}
                  >
                    {/* Expand button */}
                    <div className="flex items-center justify-center">
                      {expandedId === log.id ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>

                    {/* Timestamp */}
                    <div className="text-sm" title={formatTimestamp(log.timestamp)}>
                      <span className="text-muted-foreground">
                        {formatRelativeTime(log.timestamp)}
                      </span>
                    </div>

                    {/* Actor */}
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-medium truncate">{log.actor_username}</span>
                      <Badge
                        variant="outline"
                        className="text-[10px] px-1 py-0 shrink-0"
                      >
                        {AUDIT_ACTOR_TYPE_LABELS[log.actor_type] || log.actor_type}
                      </Badge>
                    </div>

                    {/* Action */}
                    <div>
                      <Badge className={cn('text-xs', getActionBadgeColor(log.action))}>
                        {log.action.replace(/_/g, ' ')}
                      </Badge>
                    </div>

                    {/* Resource */}
                    <div className="text-sm min-w-0">
                      <span className="text-muted-foreground">{log.resource_type}</span>
                      {(log.resource_name || log.resource_id) && (
                        <span className="ml-1 font-medium truncate">
                          {log.resource_name || log.resource_id}
                        </span>
                      )}
                    </div>

                    {/* Result */}
                    <div>
                      <Badge className={cn('text-xs', AUDIT_RESULT_COLORS[log.result])}>
                        {log.result}
                      </Badge>
                    </div>

                    {/* IP Address */}
                    <div className="text-sm text-muted-foreground font-mono">
                      {log.actor_ip || '-'}
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {expandedId === log.id && (
                    <div className="px-14 py-4 bg-muted/20 border-t">
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="text-muted-foreground">Full Timestamp:</span>
                          <span className="ml-2">{formatTimestamp(log.timestamp)}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Log ID:</span>
                          <span className="ml-2 font-mono text-xs">{log.id}</span>
                        </div>
                        {log.actor_id && (
                          <div>
                            <span className="text-muted-foreground">Actor ID:</span>
                            <span className="ml-2 font-mono text-xs">{log.actor_id}</span>
                          </div>
                        )}
                        {log.session_id && (
                          <div>
                            <span className="text-muted-foreground">Session ID:</span>
                            <span className="ml-2 font-mono text-xs">{log.session_id}</span>
                          </div>
                        )}
                        {log.auth_method && (
                          <div>
                            <span className="text-muted-foreground">Auth Method:</span>
                            <span className="ml-2">{log.auth_method}</span>
                          </div>
                        )}
                        {log.resource_id && (
                          <div>
                            <span className="text-muted-foreground">Resource ID:</span>
                            <span className="ml-2 font-mono text-xs">{log.resource_id}</span>
                          </div>
                        )}
                        {log.error_message && (
                          <div className="col-span-2">
                            <span className="text-muted-foreground">Error:</span>
                            <span className="ml-2 text-red-600">{log.error_message}</span>
                          </div>
                        )}
                        {log.details && Object.keys(log.details).length > 0 && (
                          <div className="col-span-2">
                            <span className="text-muted-foreground">Details:</span>
                            <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-auto">
                              {JSON.stringify(log.details, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Pagination */}
      {data && data.total > 0 && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>Rows per page:</span>
            <Select
              value={String(pageSize)}
              onValueChange={(v) => {
                setPageSize(Number(v))
                setPage(1)
              }}
            >
              <SelectTrigger className="w-[70px] h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage(1)}
                disabled={page === 1}
              >
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage(page - 1)}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage(page + 1)}
                disabled={page >= totalPages}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage(totalPages)}
                disabled={page >= totalPages}
              >
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
