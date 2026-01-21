import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { Server, Activity, AlertCircle, CheckCircle, Clock, ArrowRight } from 'lucide-react'
import { useNodeStats, useNodes } from '@/hooks'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, type NodeState } from '@/types'
import { cn } from '@/lib/utils'
import { DhcpSetupBanner } from '@/components/dashboard'

function StatCard({
  title,
  value,
  description,
  icon: Icon,
  iconColor,
  isLoading,
}: {
  title: string
  value: number
  description: string
  icon: React.ElementType
  iconColor: string
  isLoading?: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={cn('h-4 w-4', iconColor)} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {isLoading ? '...' : value}
        </div>
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )
}

function formatTimeAgo(dateStr: string): string {
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

export function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useNodeStats()
  const { data: discoveredResponse, isLoading: discoveredLoading } = useNodes({
    state: 'discovered',
    limit: 5,
  })
  const { data: installingResponse, isLoading: installingLoading } = useNodes({
    state: 'installing',
    limit: 5,
  })

  const discoveredNodes = discoveredResponse?.data ?? []
  const installingNodes = installingResponse?.data ?? []

  // State breakdown for chart
  const stateBreakdown: { state: NodeState; count: number }[] = stats
    ? (Object.entries(stats.by_state) as [NodeState, number][])
        .filter(([_, count]) => count > 0)
        .map(([state, count]) => ({ state, count }))
        .sort((a, b) => b.count - a.count)
    : []

  return (
    <div className="space-y-6">
      {/* DHCP Setup Banner */}
      <DhcpSetupBanner />

      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
        <Link
          to="/nodes"
          className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1"
        >
          View all nodes <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Nodes"
          value={stats?.total ?? 0}
          description="Across all states"
          icon={Server}
          iconColor="text-muted-foreground"
          isLoading={statsLoading}
        />
        <StatCard
          title="Active"
          value={stats?.by_state.active ?? 0}
          description="Running in production"
          icon={CheckCircle}
          iconColor="text-green-500"
          isLoading={statsLoading}
        />
        <StatCard
          title="Discovered"
          value={stats?.discovered_last_hour ?? 0}
          description="New in last hour"
          icon={AlertCircle}
          iconColor="text-blue-500"
          isLoading={statsLoading}
        />
        <StatCard
          title="Installing"
          value={stats?.installing_count ?? 0}
          description="In progress"
          icon={Activity}
          iconColor="text-orange-500"
          isLoading={statsLoading}
        />
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* State breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Nodes by State</CardTitle>
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : stateBreakdown.length === 0 ? (
              <div className="text-muted-foreground">No nodes</div>
            ) : (
              <div className="space-y-2">
                {stateBreakdown.map(({ state, count }) => (
                  <div key={state} className="flex items-center gap-2">
                    <div
                      className={cn('w-3 h-3 rounded-full', NODE_STATE_COLORS[state])}
                    />
                    <div className="flex-1 text-sm">{NODE_STATE_LABELS[state]}</div>
                    <div className="text-sm font-medium">{count}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* New discoveries */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>New Discoveries</CardTitle>
            <AlertCircle className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            {discoveredLoading ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : discoveredNodes.length === 0 ? (
              <div className="text-muted-foreground text-sm">
                No new nodes discovered
              </div>
            ) : (
              <div className="space-y-3">
                {discoveredNodes.map((node) => (
                  <Link
                    key={node.id}
                    to={`/nodes/${node.id}`}
                    className="block hover:bg-muted -mx-2 px-2 py-1 rounded"
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-mono text-sm">{node.mac_address}</div>
                      <div className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatTimeAgo(node.created_at)}
                      </div>
                    </div>
                    {node.vendor && (
                      <div className="text-xs text-muted-foreground">{node.vendor}</div>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Installing now */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Installing Now</CardTitle>
            <Activity className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            {installingLoading ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : installingNodes.length === 0 ? (
              <div className="text-muted-foreground text-sm">
                No installations in progress
              </div>
            ) : (
              <div className="space-y-3">
                {installingNodes.map((node) => (
                  <Link
                    key={node.id}
                    to={`/nodes/${node.id}`}
                    className="block hover:bg-muted -mx-2 px-2 py-1 rounded"
                  >
                    <div className="font-medium text-sm">
                      {node.hostname || node.mac_address}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Started {formatTimeAgo(node.updated_at)}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
