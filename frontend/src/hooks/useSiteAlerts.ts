import { useRef, useEffect, useCallback } from 'react'
import type { Site, SiteStatusDisplay } from '@/types/site'
import { getSiteStatus } from '@/types/site'

interface SiteAlert {
  type: 'offline' | 'online' | 'conflicts' | 'version_mismatch'
  siteId: string
  siteName: string
  message: string
  variant: 'destructive' | 'success' | 'warning' | 'info'
}

interface UseSiteAlertsOptions {
  onAlert?: (alert: SiteAlert) => void
  debounceMs?: number
}

/**
 * Hook that detects site status changes and fires alert callbacks.
 * Compares previous site data with current data on each poll cycle.
 */
export function useSiteAlerts(
  sites: Site[] | undefined,
  options: UseSiteAlertsOptions = {},
) {
  const { onAlert, debounceMs = 60000 } = options
  const previousStatusRef = useRef<Map<string, SiteStatusDisplay>>(new Map())
  const lastAlertRef = useRef<Map<string, number>>(new Map())

  const shouldAlert = useCallback(
    (siteId: string): boolean => {
      const lastAlert = lastAlertRef.current.get(siteId) ?? 0
      return Date.now() - lastAlert > debounceMs
    },
    [debounceMs],
  )

  useEffect(() => {
    if (!sites || !onAlert) return

    const prevStatuses = previousStatusRef.current
    const newStatuses = new Map<string, SiteStatusDisplay>()

    for (const site of sites) {
      const currentStatus = getSiteStatus(site)
      newStatuses.set(site.id, currentStatus)

      const prevStatus = prevStatuses.get(site.id)

      // Skip if no previous data (first load)
      if (prevStatus === undefined) continue

      // Skip if status unchanged
      if (prevStatus === currentStatus) continue

      // Skip if debounced
      if (!shouldAlert(site.id)) continue

      // Detect transitions
      if (currentStatus === 'offline' && prevStatus !== 'offline') {
        onAlert({
          type: 'offline',
          siteId: site.id,
          siteName: site.name,
          message: `Site ${site.name} lost connectivity`,
          variant: 'destructive',
        })
        lastAlertRef.current.set(site.id, Date.now())
      } else if (
        currentStatus === 'online' &&
        (prevStatus === 'offline' || prevStatus === 'degraded')
      ) {
        onAlert({
          type: 'online',
          siteId: site.id,
          siteName: site.name,
          message: `Site ${site.name} reconnected`,
          variant: 'success',
        })
        lastAlertRef.current.set(site.id, Date.now())
      } else if (currentStatus === 'degraded' && prevStatus === 'online') {
        onAlert({
          type: 'conflicts',
          siteId: site.id,
          siteName: site.name,
          message: `Site ${site.name} is degraded`,
          variant: 'warning',
        })
        lastAlertRef.current.set(site.id, Date.now())
      }
    }

    previousStatusRef.current = newStatuses
  }, [sites, onAlert, shouldAlert])
}

export type { SiteAlert }
