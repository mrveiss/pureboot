import { RefreshCw, Pencil, Trash2, Play, Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, Button, Badge } from '@/components/ui'
import { SYNC_STATUS_COLORS, SYNC_SCHEDULE_LABELS, type SyncJob } from '@/types'
import { cn } from '@/lib/utils'

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return date.toLocaleDateString()
}

interface SyncJobCardProps {
  job: SyncJob
  onEdit: (job: SyncJob) => void
  onDelete: (job: SyncJob) => void
  onRun: (job: SyncJob) => void
  isRunning: boolean
}

export function SyncJobCard({ job, onEdit, onDelete, onRun, isRunning }: SyncJobCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className={cn('h-2 w-2 rounded-full', SYNC_STATUS_COLORS[job.status])} />
            <CardTitle className="text-lg">{job.name}</CardTitle>
          </div>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onRun(job)}
              disabled={isRunning || job.status === 'running'}
              title="Run now"
            >
              <Play className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onEdit(job)}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive"
              onClick={() => onDelete(job)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Source:</span>
            <span className="font-mono truncate">{job.source_url}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Destination:</span>
            <span>{job.destination_backend_name} {job.destination_path}</span>
          </div>

          <div className="flex items-center justify-between pt-2">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <Badge variant="outline">{SYNC_SCHEDULE_LABELS[job.schedule]}</Badge>
            </div>
            <span className="text-muted-foreground">
              Last: {formatDate(job.last_run_at)}
            </span>
          </div>

          {job.status === 'failed' && job.last_error && (
            <div className="mt-2 p-2 bg-destructive/10 rounded text-destructive text-xs">
              {job.last_error}
            </div>
          )}

          {job.status === 'running' && (
            <div className="flex items-center gap-2 text-yellow-600">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Syncing...</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
