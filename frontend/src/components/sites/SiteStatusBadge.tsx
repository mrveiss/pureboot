import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui'
import type { Site, SiteStatusDisplay } from '@/types/site'
import { getSiteStatus, SITE_STATUS_LABELS } from '@/types/site'

interface SiteStatusBadgeProps {
  site: Site
  className?: string
}

const STATUS_VARIANT: Record<SiteStatusDisplay, string> = {
  online: 'bg-green-500/10 text-green-600 border-green-500/20',
  degraded: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20',
  offline: 'bg-red-500/10 text-red-600 border-red-500/20',
  unknown: 'bg-gray-500/10 text-gray-500 border-gray-500/20',
}

const STATUS_DOT: Record<SiteStatusDisplay, string> = {
  online: 'bg-green-500',
  degraded: 'bg-yellow-500',
  offline: 'bg-red-500',
  unknown: 'bg-gray-400',
}

export function SiteStatusBadge({ site, className }: SiteStatusBadgeProps) {
  const status = getSiteStatus(site)

  return (
    <Badge
      variant="outline"
      className={cn(STATUS_VARIANT[status], className)}
    >
      <span className={cn('mr-1.5 h-2 w-2 rounded-full', STATUS_DOT[status])} />
      {SITE_STATUS_LABELS[status]}
    </Badge>
  )
}
