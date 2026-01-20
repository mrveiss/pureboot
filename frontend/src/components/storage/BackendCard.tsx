import { HardDrive, Server, Cloud, Globe, MoreVertical, Pencil, Trash2, Zap } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, Button, Badge } from '@/components/ui'
import {
  STORAGE_BACKEND_TYPE_LABELS,
  STORAGE_STATUS_COLORS,
  type StorageBackend,
  type StorageBackendType,
} from '@/types'
import { cn } from '@/lib/utils'

const TYPE_ICONS: Record<StorageBackendType, React.ElementType> = {
  nfs: Server,
  iscsi: HardDrive,
  s3: Cloud,
  http: Globe,
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function getBackendUrl(backend: StorageBackend): string {
  const { config, type } = backend
  switch (type) {
    case 'nfs':
      return `nfs://${(config as { server: string; export_path: string }).server}${(config as { export_path: string }).export_path}`
    case 'iscsi':
      return `iscsi://${(config as { target: string; port: number }).target}:${(config as { port: number }).port}`
    case 's3':
      return `s3://${(config as { bucket: string }).bucket}`
    case 'http':
      return (config as { base_url: string }).base_url
    default:
      return ''
  }
}

interface BackendCardProps {
  backend: StorageBackend
  onEdit: (backend: StorageBackend) => void
  onDelete: (backend: StorageBackend) => void
  onTest: (backend: StorageBackend) => void
}

export function BackendCard({ backend, onEdit, onDelete, onTest }: BackendCardProps) {
  const Icon = TYPE_ICONS[backend.type]
  const usagePercent = backend.stats.total_bytes
    ? Math.round((backend.stats.used_bytes / backend.stats.total_bytes) * 100)
    : null

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className={cn('h-2 w-2 rounded-full', STORAGE_STATUS_COLORS[backend.status])} />
            <CardTitle className="text-lg flex items-center gap-2">
              <Icon className="h-5 w-5" />
              {backend.name}
            </CardTitle>
          </div>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onTest(backend)}
              title="Test connection"
            >
              <Zap className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onEdit(backend)}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive"
              onClick={() => onDelete(backend)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-2 font-mono truncate">
          {getBackendUrl(backend)}
        </p>

        <div className="flex items-center justify-between text-sm mb-2">
          <Badge variant="outline">{STORAGE_BACKEND_TYPE_LABELS[backend.type]}</Badge>
          <span className="text-muted-foreground">
            {backend.stats.template_count} templates
          </span>
        </div>

        {usagePercent !== null && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{formatBytes(backend.stats.used_bytes)} used</span>
              <span>{formatBytes(backend.stats.total_bytes!)} total</span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full',
                  usagePercent > 90 ? 'bg-red-500' : usagePercent > 70 ? 'bg-yellow-500' : 'bg-green-500'
                )}
                style={{ width: `${usagePercent}%` }}
              />
            </div>
          </div>
        )}

        {usagePercent === null && (
          <div className="text-sm text-muted-foreground">
            {formatBytes(backend.stats.used_bytes)} · {backend.stats.file_count} files
          </div>
        )}
      </CardContent>
    </Card>
  )
}
