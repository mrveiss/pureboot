import { Wifi, WifiOff, Clock, HardDrive, Activity, Server } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, Badge, Progress } from '@/components/ui'
import { cn } from '@/lib/utils'
import type { Site, SiteHealth } from '@/types/site'
import { getSiteStatus } from '@/types/site'

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

interface AgentCardProps {
  site: Site
  health?: SiteHealth | null
}

export function AgentCard({ site, health }: AgentCardProps) {
  const status = getSiteStatus(site)
  const isOnline = status === 'online' || status === 'degraded'

  return (
    <div className="space-y-4">
      {/* Agent Status */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
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
              <span className="text-muted-foreground">Status</span>
              <Badge
                variant={isOnline ? 'secondary' : 'destructive'}
                className={cn(
                  isOnline
                    ? 'bg-green-500/10 text-green-600'
                    : 'bg-red-500/10 text-red-600'
                )}
              >
                {status === 'online' ? 'Online' : status === 'degraded' ? 'Degraded' : status === 'offline' ? 'Offline' : 'Unknown'}
              </Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Last Seen</span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatTimeAgo(site.agent_last_seen)}
              </span>
            </div>
            {site.agent_url && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">URL</span>
                <span className="font-mono text-xs">{site.agent_url}</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Health Metrics */}
      {health && (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Activity className="h-4 w-4" />
                Health Metrics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Nodes</span>
                  <span className="font-medium">{health.nodes_count}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Pending Sync</span>
                  <span className="font-medium">{health.pending_sync_items}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Conflicts</span>
                  <span className={cn(
                    'font-medium',
                    health.conflicts_pending > 0 && 'text-yellow-600'
                  )}>
                    {health.conflicts_pending}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Cache Info */}
          {health.cache_max_gb && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <HardDrive className="h-4 w-4" />
                  Cache
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Used</span>
                    <span className="font-medium">
                      {health.cache_used_gb !== null
                        ? `${health.cache_used_gb.toFixed(1)} GB`
                        : 'N/A'}
                      {' / '}
                      {health.cache_max_gb} GB
                    </span>
                  </div>
                  {health.cache_used_gb !== null && (
                    <Progress
                      value={health.cache_used_gb}
                      max={health.cache_max_gb}
                    />
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Configuration */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Server className="h-4 w-4" />
            Configuration
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Autonomy</span>
              <span className="font-medium capitalize">{site.autonomy_level ?? 'readonly'}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Cache Policy</span>
              <span className="font-medium capitalize">{site.cache_policy ?? 'minimal'}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Conflict Resolution</span>
              <span className="font-medium capitalize">
                {(site.conflict_resolution ?? 'central_wins').replace('_', ' ')}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Discovery</span>
              <span className="font-medium capitalize">{site.discovery_method ?? 'dhcp'}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
