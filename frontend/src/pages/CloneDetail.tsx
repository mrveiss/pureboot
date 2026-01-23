import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Server,
  HardDrive,
  Clock,
  AlertCircle,
  XCircle,
  Copy,
  Loader2,
  CheckCircle,
  ArrowRight,
  Activity,
  Network,
} from 'lucide-react'
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Progress,
} from '@/components/ui'
import { useCloneSession, useDeleteCloneSession, useCloneUpdates } from '@/hooks'
import { CLONE_STATUS_COLORS, CLONE_STATUS_LABELS, type CloneStatus } from '@/types/clone'
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
 * Format duration in seconds to human-readable string
 */
function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}m ${secs}s`
  }
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

/**
 * Format timestamp to localized string
 */
function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'N/A'
  return new Date(dateStr).toLocaleString()
}

/**
 * Calculate elapsed time from start to end (or now if not completed)
 */
function calculateElapsed(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt) return 'N/A'

  const start = new Date(startedAt).getTime()
  const end = completedAt ? new Date(completedAt).getTime() : Date.now()
  const seconds = (end - start) / 1000

  return formatDuration(seconds)
}

/**
 * Get icon for clone status
 */
function getStatusIcon(status: CloneStatus) {
  switch (status) {
    case 'completed':
      return <CheckCircle className="h-5 w-5" />
    case 'failed':
    case 'cancelled':
      return <XCircle className="h-5 w-5" />
    case 'cloning':
      return <Loader2 className="h-5 w-5 animate-spin" />
    case 'source_ready':
      return <ArrowRight className="h-5 w-5" />
    case 'pending':
    default:
      return <Clock className="h-5 w-5" />
  }
}

export function CloneDetail() {
  const { id } = useParams<{ id: string }>()
  const { data: response, isLoading, error } = useCloneSession(id ?? '')
  const deleteSession = useDeleteCloneSession()

  // Enable real-time updates
  const { isConnected } = useCloneUpdates()

  const handleCancel = () => {
    if (!id) return
    if (!confirm('Are you sure you want to cancel this clone session?')) return

    deleteSession.mutate(id)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading clone session details...</div>
      </div>
    )
  }

  if (error || !response?.data) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" asChild>
          <Link to="/clone">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Clone Sessions
          </Link>
        </Button>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-destructive">
              {error instanceof Error ? error.message : 'Clone session not found'}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const session = response.data
  const canCancel = ['pending', 'source_ready', 'cloning'].includes(session.status)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" asChild>
            <Link to="/clone">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold">
                {session.name || `Clone ${session.id.slice(0, 8)}`}
              </h2>
              <Badge variant="outline" className="text-sm">
                {session.clone_mode === 'staged' ? 'Staged' : 'Direct'}
              </Badge>
              <Badge
                variant="outline"
                className={cn('border-0 text-white gap-1.5', CLONE_STATUS_COLORS[session.status])}
              >
                {getStatusIcon(session.status)}
                {CLONE_STATUS_LABELS[session.status]}
              </Badge>
              {isConnected && (
                <div className="flex items-center gap-1 text-xs text-green-600">
                  <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                  Live
                </div>
              )}
            </div>
            <p className="text-muted-foreground font-mono text-sm mt-1">
              {session.id}
            </p>
          </div>
        </div>
        {canCancel && (
          <Button
            variant="destructive"
            onClick={handleCancel}
            disabled={deleteSession.isPending}
          >
            <XCircle className="mr-2 h-4 w-4" />
            {deleteSession.isPending ? 'Cancelling...' : 'Cancel Clone'}
          </Button>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left column */}
        <div className="space-y-6">
          {/* Progress Section - Only show for active/completed clones */}
          {(session.status === 'cloning' ||
            session.status === 'completed' ||
            (session.bytes_total !== null && session.bytes_total > 0)) && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="h-5 w-5" />
                  Transfer Progress
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span>
                      {formatBytes(session.bytes_transferred)} / {formatBytes(session.bytes_total)}
                    </span>
                    <span className="font-medium">{session.progress_percent.toFixed(1)}%</span>
                  </div>
                  <Progress
                    value={session.progress_percent}
                    className={cn(
                      'h-3',
                      session.status === 'cloning' && 'animate-pulse'
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <div className="text-muted-foreground">Transfer Rate</div>
                    <div className="font-medium text-lg">
                      {formatRate(session.transfer_rate_bps)}
                    </div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Elapsed Time</div>
                    <div className="font-medium text-lg">
                      {calculateElapsed(session.started_at, session.completed_at)}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Error Message */}
          {session.error_message && (
            <Card className="border-destructive">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="h-5 w-5" />
                  Error
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-sm text-destructive bg-destructive/10 rounded-md p-3">
                  {session.error_message}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Source Node Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                Source Node
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Node</div>
                  <div className="font-medium">
                    {session.source_node_name || session.source_node_id.slice(0, 8)}
                  </div>
                  <code className="text-xs text-muted-foreground">{session.source_node_id}</code>
                </div>
                <div>
                  <div className="text-muted-foreground flex items-center gap-1">
                    <HardDrive className="h-3 w-3" />
                    Device
                  </div>
                  <div className="font-medium font-mono">{session.source_device}</div>
                </div>
                {session.source_ip && (
                  <div>
                    <div className="text-muted-foreground flex items-center gap-1">
                      <Network className="h-3 w-3" />
                      IP Address
                    </div>
                    <div className="font-medium font-mono">
                      {session.source_ip}:{session.source_port}
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Target Node Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Copy className="h-5 w-5" />
                Target Node
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {session.target_node_id ? (
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <div className="text-muted-foreground">Node</div>
                    <div className="font-medium">
                      {session.target_node_name || session.target_node_id.slice(0, 8)}
                    </div>
                    <code className="text-xs text-muted-foreground">{session.target_node_id}</code>
                  </div>
                  <div>
                    <div className="text-muted-foreground flex items-center gap-1">
                      <HardDrive className="h-3 w-3" />
                      Device
                    </div>
                    <div className="font-medium font-mono">{session.target_device}</div>
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">
                  Not assigned
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Session Details */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Copy className="h-5 w-5" />
                Session Details
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Clone Mode</div>
                  <div className="font-medium capitalize">{session.clone_mode}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Resize Mode</div>
                  <div className="font-medium">
                    {session.resize_mode === 'none'
                      ? 'None'
                      : session.resize_mode === 'shrink_source'
                        ? 'Shrink Source'
                        : 'Grow Target'}
                  </div>
                </div>
                {session.clone_mode === 'staged' && (
                  <>
                    <div className="col-span-2">
                      <div className="text-muted-foreground">Staging Backend</div>
                      <div className="font-medium">
                        {session.staging_backend_name || 'Not set'}
                      </div>
                    </div>
                    {session.staging_status && (
                      <div className="col-span-2">
                        <div className="text-muted-foreground">Staging Status</div>
                        <Badge variant="outline" className="capitalize">
                          {session.staging_status}
                        </Badge>
                      </div>
                    )}
                    {session.staging_path && (
                      <div className="col-span-2">
                        <div className="text-muted-foreground">Staging Path</div>
                        <code className="text-xs">{session.staging_path}</code>
                      </div>
                    )}
                  </>
                )}
                {session.created_by && (
                  <div className="col-span-2">
                    <div className="text-muted-foreground">Created By</div>
                    <div className="font-medium">{session.created_by}</div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Timeline Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Timeline
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <div className="h-2 w-2 rounded-full bg-green-500 mt-2" />
                  <div>
                    <div className="text-sm font-medium">Created</div>
                    <div className="text-sm text-muted-foreground">
                      {formatDate(session.created_at)}
                    </div>
                  </div>
                </div>

                {session.started_at && (
                  <div className="flex items-start gap-3">
                    <div className="h-2 w-2 rounded-full bg-blue-500 mt-2" />
                    <div>
                      <div className="text-sm font-medium">Started</div>
                      <div className="text-sm text-muted-foreground">
                        {formatDate(session.started_at)}
                      </div>
                    </div>
                  </div>
                )}

                {session.completed_at && (
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        'h-2 w-2 rounded-full mt-2',
                        session.status === 'completed' ? 'bg-green-500' :
                        session.status === 'failed' ? 'bg-red-500' : 'bg-gray-500'
                      )}
                    />
                    <div>
                      <div className="text-sm font-medium">
                        {session.status === 'completed' ? 'Completed' :
                         session.status === 'failed' ? 'Failed' :
                         session.status === 'cancelled' ? 'Cancelled' : 'Ended'}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {formatDate(session.completed_at)}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Duration */}
              {session.started_at && session.completed_at && (
                <div className="pt-3 border-t">
                  <div className="text-sm text-muted-foreground">Total Duration</div>
                  <div className="font-medium text-lg">
                    {calculateElapsed(session.started_at, session.completed_at)}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Status-specific info cards */}
          {session.status === 'pending' && (
            <Card className="border-yellow-500/50 bg-yellow-500/5">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <Clock className="h-5 w-5 text-yellow-500 mt-0.5" />
                  <div>
                    <div className="font-medium">Waiting for Source Node</div>
                    <p className="text-sm text-muted-foreground mt-1">
                      The source node needs to boot and prepare its disk for cloning.
                      This typically happens automatically when the node PXE boots.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {session.status === 'source_ready' && (
            <Card className="border-blue-500/50 bg-blue-500/5">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <ArrowRight className="h-5 w-5 text-blue-500 mt-0.5" />
                  <div>
                    <div className="font-medium">Ready for Target Node</div>
                    <p className="text-sm text-muted-foreground mt-1">
                      The source node is ready and waiting. Boot the target node to
                      begin the cloning process.
                    </p>
                    {session.source_ip && (
                      <div className="mt-2 text-xs font-mono bg-muted rounded px-2 py-1 inline-block">
                        Source listening on {session.source_ip}:{session.source_port}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {session.status === 'cloning' && (
            <Card className="border-yellow-500/50 bg-yellow-500/5">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <Loader2 className="h-5 w-5 text-yellow-500 animate-spin mt-0.5" />
                  <div>
                    <div className="font-medium">Clone in Progress</div>
                    <p className="text-sm text-muted-foreground mt-1">
                      Data is being transferred from the source to the target node.
                      Do not power off either node until the transfer is complete.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
