import { useState, useMemo } from 'react'
import {
  Button,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { ConflictTable } from '@/components/sites'
import { useSiteConflicts, useResolveConflict, useResolveAllConflicts } from '@/hooks'
import type { ConflictType, ConflictResolutionAction } from '@/types/site'
import { CONFLICT_TYPE_LABELS } from '@/types/site'

interface ConflictResolutionPageProps {
  siteId: string
}

export function ConflictResolutionPage({ siteId }: ConflictResolutionPageProps) {
  const { data: response, isLoading } = useSiteConflicts(siteId)
  const resolveConflict = useResolveConflict()
  const resolveAll = useResolveAllConflicts()

  const [typeFilter, setTypeFilter] = useState<ConflictType | 'all'>('all')
  const [resolveAllOpen, setResolveAllOpen] = useState(false)
  const [bulkResolution, setBulkResolution] = useState<ConflictResolutionAction>('keep_central')
  const [showResolved, setShowResolved] = useState(false)

  const allConflicts = response?.data ?? []

  const pendingConflicts = useMemo(() => {
    let result = allConflicts.filter((c) => !c.resolved_at)
    if (typeFilter !== 'all') {
      result = result.filter((c) => c.conflict_type === typeFilter)
    }
    return result.sort(
      (a, b) => new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime(),
    )
  }, [allConflicts, typeFilter])

  const resolvedConflicts = useMemo(() => {
    return allConflicts
      .filter((c) => c.resolved_at)
      .sort(
        (a, b) =>
          new Date(b.resolved_at!).getTime() - new Date(a.resolved_at!).getTime(),
      )
  }, [allConflicts])

  const handleResolve = (conflictId: string, resolution: ConflictResolutionAction) => {
    resolveConflict.mutate({ siteId, conflictId, resolution })
  }

  const handleResolveAll = () => {
    resolveAll.mutate(
      { siteId, resolution: bulkResolution },
      { onSuccess: () => setResolveAllOpen(false) },
    )
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-sm">
            {pendingConflicts.length} pending
          </Badge>

          <div className="flex items-center gap-1">
            <Button
              variant={typeFilter === 'all' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setTypeFilter('all')}
            >
              All
            </Button>
            {(Object.entries(CONFLICT_TYPE_LABELS) as [ConflictType, string][]).map(
              ([type, label]) => (
                <Button
                  key={type}
                  variant={typeFilter === type ? 'secondary' : 'ghost'}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setTypeFilter(type)}
                >
                  {label}
                </Button>
              ),
            )}
          </div>
        </div>

        {pendingConflicts.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setResolveAllOpen(true)}
          >
            Resolve All ({pendingConflicts.length})
          </Button>
        )}
      </div>

      {/* Pending conflicts */}
      {isLoading ? (
        <div className="text-muted-foreground">Loading conflicts...</div>
      ) : (
        <ConflictTable
          conflicts={pendingConflicts}
          onResolve={handleResolve}
          isResolving={resolveConflict.isPending}
        />
      )}

      {/* Resolved conflicts (collapsible) */}
      {resolvedConflicts.length > 0 && (
        <div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowResolved(!showResolved)}
            className="text-muted-foreground"
          >
            {showResolved ? 'Hide' : 'Show'} resolved ({resolvedConflicts.length})
          </Button>

          {showResolved && (
            <div className="mt-2 space-y-2 border rounded-md">
              {resolvedConflicts.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center justify-between px-3 py-2 text-sm border-b last:border-0 text-muted-foreground"
                >
                  <span className="font-mono">{c.node_mac}</span>
                  <span>{CONFLICT_TYPE_LABELS[c.conflict_type]}</span>
                  <span className="capitalize">{c.resolution?.replace('_', ' ')}</span>
                  <span>{c.resolved_by ?? 'system'}</span>
                  <span className="text-xs">
                    {c.resolved_at ? new Date(c.resolved_at).toLocaleString() : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Resolve All Dialog */}
      <Dialog open={resolveAllOpen} onOpenChange={setResolveAllOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Resolve All Conflicts</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <p className="text-sm text-muted-foreground">
              This will resolve all {pendingConflicts.length} pending conflicts with the
              selected strategy.
            </p>
            <div className="space-y-2">
              <label className="text-sm font-medium">Resolution Strategy</label>
              <Select
                value={bulkResolution}
                onValueChange={(v) => setBulkResolution(v as ConflictResolutionAction)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="keep_central">Keep Central</SelectItem>
                  <SelectItem value="keep_local">Keep Local</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResolveAllOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleResolveAll}
              disabled={resolveAll.isPending}
            >
              {resolveAll.isPending ? 'Resolving...' : `Resolve ${pendingConflicts.length} Conflicts`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
