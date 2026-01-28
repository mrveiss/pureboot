import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { useSites } from '@/hooks'
import { getSiteStatus } from '@/types/site'

export function AppShell() {
  const { data: sitesResponse } = useSites()
  const sites = sitesResponse?.data ?? []
  const problemSites = sites.filter((s) => {
    const status = getSiteStatus(s)
    return status === 'offline' || status === 'degraded'
  }).length

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar pendingApprovals={3} problemSites={problemSites} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header notificationCount={5} />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
