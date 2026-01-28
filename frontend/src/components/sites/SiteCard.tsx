import { Link } from 'react-router-dom'
import { Server, Clock, Database } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { SiteStatusBadge } from './SiteStatusBadge'
import type { Site } from '@/types/site'

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

interface SiteCardProps {
  site: Site
}

export function SiteCard({ site }: SiteCardProps) {
  return (
    <Card className="relative hover:border-foreground/20 transition-colors">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <CardTitle className="text-lg">{site.name}</CardTitle>
          <SiteStatusBadge site={site} />
        </div>
        {site.description && (
          <p className="text-sm text-muted-foreground line-clamp-1">
            {site.description}
          </p>
        )}
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Node count */}
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Server className="h-3.5 w-3.5" />
              <span>Nodes</span>
            </div>
            <span className="font-medium">{site.node_count}</span>
          </div>

          {/* Last heartbeat */}
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              <span>Last seen</span>
            </div>
            <span className="font-medium">{formatTimeAgo(site.agent_last_seen)}</span>
          </div>

          {/* Cache policy */}
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Database className="h-3.5 w-3.5" />
              <span>Cache</span>
            </div>
            <span className="font-medium capitalize">{site.cache_policy ?? 'minimal'}</span>
          </div>

          {/* Autonomy level */}
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Autonomy</span>
            <span className="font-medium capitalize">{site.autonomy_level ?? 'readonly'}</span>
          </div>
        </div>

        {/* Link overlay */}
        <Link
          to={`/groups/${site.id}`}
          className="absolute inset-0"
          aria-label={`View ${site.name}`}
        />
      </CardContent>
    </Card>
  )
}
