import { useState, useMemo } from 'react'
import { Plus, Search, Filter, Globe } from 'lucide-react'
import { Button, Input, Badge } from '@/components/ui'
import { SiteCard, CreateSiteDialog } from '@/components/sites'
import { useSites } from '@/hooks'
import type { SiteStatusDisplay } from '@/types/site'
import { getSiteStatus } from '@/types/site'

const STATUS_FILTERS: { label: string; value: SiteStatusDisplay | 'all' | 'problems' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Online', value: 'online' },
  { label: 'Degraded', value: 'degraded' },
  { label: 'Offline', value: 'offline' },
  { label: 'Unknown', value: 'unknown' },
  { label: 'Problems', value: 'problems' },
]

type SortKey = 'name' | 'status' | 'nodes' | 'last_seen'

export function SitesListPage() {
  const { data: response, isLoading } = useSites()
  const [createOpen, setCreateOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [sortBy, setSortBy] = useState<SortKey>('status')

  const sites = response?.data ?? []

  const filteredSites = useMemo(() => {
    let result = [...sites]

    // Search
    if (search) {
      const lower = search.toLowerCase()
      result = result.filter(
        (s) =>
          s.name.toLowerCase().includes(lower) ||
          s.id.toLowerCase().includes(lower),
      )
    }

    // Status filter
    if (statusFilter === 'problems') {
      result = result.filter((s) => {
        const st = getSiteStatus(s)
        return st === 'offline' || st === 'degraded'
      })
    } else if (statusFilter !== 'all') {
      result = result.filter((s) => getSiteStatus(s) === statusFilter)
    }

    // Sort
    result.sort((a, b) => {
      switch (sortBy) {
        case 'name':
          return a.name.localeCompare(b.name)
        case 'status': {
          const order: Record<SiteStatusDisplay, number> = {
            offline: 0,
            degraded: 1,
            unknown: 2,
            online: 3,
          }
          return (order[getSiteStatus(a)] ?? 4) - (order[getSiteStatus(b)] ?? 4)
        }
        case 'nodes':
          return b.node_count - a.node_count
        case 'last_seen': {
          const aTime = a.agent_last_seen ? new Date(a.agent_last_seen).getTime() : 0
          const bTime = b.agent_last_seen ? new Date(b.agent_last_seen).getTime() : 0
          return bTime - aTime
        }
        default:
          return 0
      }
    })

    return result
  }, [sites, search, statusFilter, sortBy])

  const problemCount = sites.filter((s) => {
    const st = getSiteStatus(s)
    return st === 'offline' || st === 'degraded'
  }).length

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search sites..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        <div className="flex items-center gap-1">
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f.value}
              variant={statusFilter === f.value ? 'default' : 'ghost'}
              size="sm"
              className="h-8 text-xs"
              onClick={() => setStatusFilter(f.value)}
            >
              {f.label}
              {f.value === 'problems' && problemCount > 0 && (
                <Badge variant="destructive" className="ml-1 h-4 min-w-4 px-1 text-[10px]">
                  {problemCount}
                </Badge>
              )}
            </Button>
          ))}
        </div>

        <div className="ml-auto">
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create Site
          </Button>
        </div>
      </div>

      {/* Sort options */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Sort by:</span>
        {(['status', 'name', 'nodes', 'last_seen'] as SortKey[]).map((key) => (
          <Button
            key={key}
            variant={sortBy === key ? 'secondary' : 'ghost'}
            size="sm"
            className="h-7 text-xs"
            onClick={() => setSortBy(key)}
          >
            {key === 'last_seen' ? 'Last Seen' : key.charAt(0).toUpperCase() + key.slice(1)}
          </Button>
        ))}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="text-muted-foreground">Loading sites...</div>
      ) : filteredSites.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Globe className="mx-auto h-12 w-12 mb-4 opacity-50" />
          {sites.length === 0 ? (
            <>
              <p>No sites created yet.</p>
              <p className="text-sm mt-1">Create a site to manage remote locations.</p>
            </>
          ) : (
            <p>No sites match your filters.</p>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredSites.map((site) => (
            <SiteCard key={site.id} site={site} />
          ))}
        </div>
      )}

      <CreateSiteDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
