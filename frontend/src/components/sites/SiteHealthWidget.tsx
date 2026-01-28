import { Link } from 'react-router-dom'
import { Globe, Wifi, WifiOff, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { useSites } from '@/hooks'
import { getSiteStatus } from '@/types/site'

export function SiteHealthWidget() {
  const { data: response, isLoading } = useSites()
  const sites = response?.data ?? []

  const totalSites = sites.length
  const onlineCount = sites.filter((s) => getSiteStatus(s) === 'online').length
  const offlineCount = sites.filter((s) => getSiteStatus(s) === 'offline').length
  const degradedCount = sites.filter((s) => getSiteStatus(s) === 'degraded').length
  const problemCount = offlineCount + degradedCount

  if (totalSites === 0 && !isLoading) {
    return null // Don't show widget if no sites exist
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Site Health</CardTitle>
        <Globe className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-muted-foreground text-sm">Loading...</div>
        ) : (
          <div className="space-y-3">
            {/* Summary numbers */}
            <div className="flex items-center justify-between">
              <span className="text-2xl font-bold">{totalSites}</span>
              <span className="text-sm text-muted-foreground">total sites</span>
            </div>

            {/* Online/Offline bar */}
            <div className="flex h-2 rounded-full overflow-hidden bg-secondary">
              {onlineCount > 0 && (
                <div
                  className="bg-green-500 transition-all"
                  style={{ width: `${(onlineCount / totalSites) * 100}%` }}
                />
              )}
              {degradedCount > 0 && (
                <div
                  className="bg-yellow-500 transition-all"
                  style={{ width: `${(degradedCount / totalSites) * 100}%` }}
                />
              )}
              {offlineCount > 0 && (
                <div
                  className="bg-red-500 transition-all"
                  style={{ width: `${(offlineCount / totalSites) * 100}%` }}
                />
              )}
            </div>

            {/* Breakdown */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-1.5">
                  <Wifi className="h-3.5 w-3.5 text-green-500" />
                  <span>Online</span>
                </div>
                <span className="font-medium">{onlineCount}</span>
              </div>
              {degradedCount > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5 text-yellow-500" />
                    <span>Degraded</span>
                  </div>
                  <span className="font-medium">{degradedCount}</span>
                </div>
              )}
              {offlineCount > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-1.5">
                    <WifiOff className="h-3.5 w-3.5 text-red-500" />
                    <span>Offline</span>
                  </div>
                  <span className="font-medium">{offlineCount}</span>
                </div>
              )}
            </div>

            {/* Link */}
            <Link
              to="/groups?tab=sites"
              className="block text-sm text-primary hover:underline"
            >
              View all sites
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
