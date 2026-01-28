import { useState } from 'react'
import {
  RefreshCw,
  Settings,
  Wifi,
  WifiOff,
  Clock,
  Activity,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Progress,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Label,
} from '@/components/ui'
import { cn } from '@/lib/utils'
import { useUpdateSite, useTriggerSiteSync } from '@/hooks'
import type { Site, SiteHealth, AutonomyLevel, CachePolicy, ConflictResolution } from '@/types/site'
import { AUTONOMY_LEVEL_LABELS, CACHE_POLICY_LABELS, CONFLICT_RESOLUTION_LABELS } from '@/types/site'

function formatTimeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never'
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

interface AgentDashboardPanelProps {
  site: Site
  health?: SiteHealth | null
}

export function AgentDashboardPanel({ site, health }: AgentDashboardPanelProps) {
  const updateSite = useUpdateSite()
  const triggerSync = useTriggerSiteSync()

  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({
    autonomy_level: site.autonomy_level ?? 'readonly',
    cache_policy: site.cache_policy ?? 'minimal',
    conflict_resolution: site.conflict_resolution ?? 'central_wins',
  })

  const isOnline = site.agent_status === 'online' || site.agent_status === 'degraded'

  const handleSaveConfig = () => {
    updateSite.mutate(
      {
        siteId: site.id,
        data: {
          autonomy_level: editForm.autonomy_level as AutonomyLevel,
          cache_policy: editForm.cache_policy as CachePolicy,
          conflict_resolution: editForm.conflict_resolution as ConflictResolution,
        },
      },
      { onSuccess: () => setEditing(false) },
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Agent Info */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            {isOnline ? (
              <Wifi className="h-4 w-4 text-green-500" />
            ) : (
              <WifiOff className="h-4 w-4 text-red-500" />
            )}
            Agent Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Connection</span>
              <Badge
                variant="outline"
                className={cn(
                  isOnline
                    ? 'bg-green-500/10 text-green-600 border-green-500/20'
                    : 'bg-red-500/10 text-red-600 border-red-500/20',
                )}
              >
                {isOnline ? 'Connected' : 'Disconnected'}
              </Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Last Heartbeat</span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatTimeAgo(site.agent_last_seen)}
              </span>
            </div>
            {site.agent_url && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Agent URL</span>
                <span className="font-mono text-xs truncate max-w-48">
                  {site.agent_url}
                </span>
              </div>
            )}
            <div className="pt-2">
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => triggerSync.mutate({ siteId: site.id })}
                disabled={triggerSync.isPending}
              >
                <RefreshCw className={cn('mr-2 h-3.5 w-3.5', triggerSync.isPending && 'animate-spin')} />
                Trigger Sync
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Health Metrics */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Health Metrics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Nodes</span>
              <span className="font-medium">{health?.nodes_count ?? site.node_count}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Pending Sync Items</span>
              <span className="font-medium">{health?.pending_sync_items ?? 0}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Pending Conflicts</span>
              <span className={cn('font-medium', (health?.conflicts_pending ?? 0) > 0 && 'text-yellow-600')}>
                {health?.conflicts_pending ?? 0}
              </span>
            </div>
            {health?.cache_max_gb && (
              <div className="space-y-1 pt-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Cache</span>
                  <span className="text-xs">
                    {health.cache_used_gb !== null
                      ? `${health.cache_used_gb.toFixed(1)} / ${health.cache_max_gb} GB`
                      : `${health.cache_max_gb} GB max`}
                  </span>
                </div>
                {health.cache_used_gb !== null && (
                  <Progress value={health.cache_used_gb} max={health.cache_max_gb} />
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Configuration */}
      <Card className="md:col-span-2">
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Site Configuration
          </CardTitle>
          {!editing && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              Edit
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {editing ? (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label>Autonomy Level</Label>
                  <Select
                    value={editForm.autonomy_level}
                    onValueChange={(v) => setEditForm({ ...editForm, autonomy_level: v as AutonomyLevel })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(AUTONOMY_LEVEL_LABELS).map(([k, v]) => (
                        <SelectItem key={k} value={k}>{v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Cache Policy</Label>
                  <Select
                    value={editForm.cache_policy}
                    onValueChange={(v) => setEditForm({ ...editForm, cache_policy: v as CachePolicy })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(CACHE_POLICY_LABELS).map(([k, v]) => (
                        <SelectItem key={k} value={k}>{v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Conflict Resolution</Label>
                  <Select
                    value={editForm.conflict_resolution}
                    onValueChange={(v) => setEditForm({ ...editForm, conflict_resolution: v as ConflictResolution })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(CONFLICT_RESOLUTION_LABELS).map(([k, v]) => (
                        <SelectItem key={k} value={k}>{v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSaveConfig} disabled={updateSite.isPending}>
                  {updateSite.isPending ? 'Saving...' : 'Save Configuration'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <span className="text-sm text-muted-foreground">Autonomy Level</span>
                <p className="font-medium capitalize">{site.autonomy_level ?? 'readonly'}</p>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Cache Policy</span>
                <p className="font-medium capitalize">{site.cache_policy ?? 'minimal'}</p>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Conflict Resolution</span>
                <p className="font-medium capitalize">
                  {(site.conflict_resolution ?? 'central_wins').replace('_', ' ')}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
