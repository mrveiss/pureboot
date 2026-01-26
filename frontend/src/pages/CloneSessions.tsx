import { Link } from 'react-router-dom'
import {
  Plus,
  Copy,
  ArrowRight,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  RefreshCw,
  Server,
  HardDrive,
  AlertCircle,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Button,
} from '@/components/ui'
import { useCloneSessions, useCloneUpdates } from '@/hooks'
import type { CloneSession, CloneStatus } from '@/types/clone'
import { CLONE_STATUS_COLORS, CLONE_STATUS_LABELS } from '@/types/clone'
import { cn } from '@/lib/utils'

/**
 * Format bytes to human-readable string
 */
function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === 0) return '0 B'

  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${units[i]}`
}

/**
 * Format transfer rate to human-readable string
 */
function formatRate(bytesPerSecond: number | null): string {
  if (bytesPerSecond === null || bytesPerSecond === 0) return '0 B/s'

  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  const k = 1024
  const i = Math.floor(Math.log(bytesPerSecond) / Math.log(k))

  return `${(bytesPerSecond / Math.pow(k, i)).toFixed(2)} ${units[i]}`
}

/**
 * Format timestamp to relative time
 */
function formatTimestamp(timestamp: string | null): string {
  if (!timestamp) return 'N/A'

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

/**
 * Get icon for clone status
 */
function getStatusIcon(status: CloneStatus) {
  switch (status) {
    case 'completed':
      return <CheckCircle className="h-4 w-4" />
    case 'failed':
    case 'cancelled':
      return <XCircle className="h-4 w-4" />
    case 'cloning':
      return <Loader2 className="h-4 w-4 animate-spin" />
    case 'source_ready':
      return <ArrowRight className="h-4 w-4" />
    case 'pending':
    default:
      return <Clock className="h-4 w-4" />
  }
}

/**
 * Clone status badge component
 */
function CloneStatusBadge({ status }: { status: CloneStatus }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        'border-0 text-white gap-1.5',
        CLONE_STATUS_COLORS[status]
      )}
    >
      {getStatusIcon(status)}
      {CLONE_STATUS_LABELS[status]}
    </Badge>
  )
}

/**
 * Clone progress bar component
 */
function CloneProgress({ session }: { session: CloneSession }) {
  const progressPercent = session.progress_percent
  const bytesTransferred = session.bytes_transferred
  const bytesTotal = session.bytes_total
  const transferRate = session.transfer_rate_bps

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {formatBytes(bytesTransferred)} / {formatBytes(bytesTotal)}
        </span>
        {transferRate !== null && transferRate > 0 && (
          <span className="text-muted-foreground">
            {formatRate(transferRate)}
          </span>
        )}
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full transition-all duration-300',
            session.status === 'cloning' ? 'bg-yellow-500' :
            session.status === 'completed' ? 'bg-green-500' :
            session.status === 'failed' ? 'bg-red-500' : 'bg-blue-500'
          )}
          style={{ width: `${progressPercent}%` }}
        />
      </div>
      <div className="text-right text-sm font-medium">
        {progressPercent.toFixed(1)}%
      </div>
    </div>
  )
}

/**
 * Clone session card component
 */
function CloneSessionCard({ session }: { session: CloneSession }) {
  return (
    <Card className="hover:border-primary/50 transition-colors">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="text-lg">
              {session.name || `Clone ${session.id.slice(0, 8)}`}
            </CardTitle>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="outline" className="text-xs">
                {session.clone_mode === 'staged' ? 'Staged' : 'Direct'}
              </Badge>
              {session.resize_mode !== 'none' && (
                <Badge variant="secondary" className="text-xs">
                  {session.resize_mode === 'shrink_source' ? 'Shrink' : 'Grow'}
                </Badge>
              )}
            </div>
          </div>
          <CloneStatusBadge status={session.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Source and Target info */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Server className="h-3 w-3" />
              Source
            </div>
            <div className="font-medium">
              {session.source_node_name || session.source_node_id.slice(0, 8)}
            </div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <HardDrive className="h-3 w-3" />
              {session.source_device}
            </div>
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Server className="h-3 w-3" />
              Target
            </div>
            <div className="font-medium">
              {session.target_node_id
                ? (session.target_node_name || session.target_node_id.slice(0, 8))
                : 'Not assigned'
              }
            </div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <HardDrive className="h-3 w-3" />
              {session.target_device}
            </div>
          </div>
        </div>

        {/* Staging backend info for staged mode */}
        {session.clone_mode === 'staged' && session.staging_backend_name && (
          <div className="text-sm">
            <span className="text-muted-foreground">Staging: </span>
            <span>{session.staging_backend_name}</span>
            {session.staging_status && (
              <Badge variant="outline" className="ml-2 text-xs">
                {session.staging_status}
              </Badge>
            )}
          </div>
        )}

        {/* Progress bar for active or completed clones */}
        {(session.status === 'cloning' || session.status === 'completed' ||
          (session.bytes_total !== null && session.bytes_total > 0)) && (
          <CloneProgress session={session} />
        )}

        {/* Error message */}
        {session.error_message && (
          <div className="flex items-start gap-2 text-sm text-destructive rounded-md bg-destructive/10 p-2">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{session.error_message}</span>
          </div>
        )}

        {/* Timestamps */}
        <div className="flex items-center justify-between text-xs text-muted-foreground border-t pt-3">
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Created {formatTimestamp(session.created_at)}
          </div>
          {session.completed_at && (
            <div>
              Completed {formatTimestamp(session.completed_at)}
            </div>
          )}
          {session.started_at && !session.completed_at && (
            <div>
              Started {formatTimestamp(session.started_at)}
            </div>
          )}
        </div>

        {/* Link to detail page */}
        <Button variant="outline" size="sm" className="w-full" asChild>
          <Link to={`/clone/${session.id}`}>
            View Details
            <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  )
}

/**
 * Clone Sessions list page
 */
export function CloneSessions() {
  // Enable real-time updates via WebSocket
  const { isConnected } = useCloneUpdates()

  // Fetch clone sessions
  const { data: response, isLoading, refetch, isFetching } = useCloneSessions()
  const sessions = response?.data ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-3xl font-bold tracking-tight">Clone Sessions</h2>
          {isConnected && (
            <div className="flex items-center gap-1 text-xs text-green-600">
              <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
              Live
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          </Button>
          <Button asChild>
            <Link to="/clone/new">
              <Plus className="mr-2 h-4 w-4" />
              New Clone
            </Link>
          </Button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="text-muted-foreground">Loading clone sessions...</div>
      ) : sessions.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <Copy className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p className="text-lg font-medium">No clone sessions</p>
              <p className="text-sm mt-1">
                Create a new clone session to duplicate a node&apos;s disk to another node.
              </p>
              <Button className="mt-4" asChild>
                <Link to="/clone/new">
                  <Plus className="mr-2 h-4 w-4" />
                  Create Clone Session
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {sessions.map((session) => (
            <CloneSessionCard key={session.id} session={session} />
          ))}
        </div>
      )}
    </div>
  )
}
