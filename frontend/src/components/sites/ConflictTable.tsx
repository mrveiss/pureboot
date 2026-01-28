import { useState } from 'react'
import { AlertTriangle, Check, ArrowRight, ChevronDown, ChevronRight } from 'lucide-react'
import { Button, Badge } from '@/components/ui'
import { cn } from '@/lib/utils'
import { ConflictDiffView } from './ConflictDiffView'
import type { SiteConflict, ConflictResolutionAction } from '@/types/site'
import { CONFLICT_TYPE_LABELS } from '@/types/site'

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

const TYPE_BADGE_STYLE: Record<string, string> = {
  state_mismatch: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20',
  missing_local: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
  missing_central: 'bg-red-500/10 text-red-600 border-red-500/20',
}

interface ConflictTableProps {
  conflicts: SiteConflict[]
  onResolve: (conflictId: string, resolution: ConflictResolutionAction) => void
  isResolving?: boolean
}

export function ConflictTable({ conflicts, onResolve, isResolving }: ConflictTableProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (conflicts.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Check className="mx-auto h-8 w-8 mb-2 opacity-50" />
        <p>No pending conflicts.</p>
      </div>
    )
  }

  return (
    <div className="space-y-0 border rounded-md">
      {/* Header */}
      <div className="grid grid-cols-[2rem_1fr_8rem_6rem_6rem_14rem] gap-2 items-center px-3 py-2 border-b bg-muted/50 text-xs font-medium text-muted-foreground">
        <div />
        <div>Node</div>
        <div>Type</div>
        <div>Local</div>
        <div>Central</div>
        <div>Actions</div>
      </div>

      {/* Rows */}
      {conflicts.map((conflict) => {
        const isExpanded = expandedId === conflict.id

        return (
          <div key={conflict.id} className="border-b last:border-0">
            <div
              className={cn(
                'grid grid-cols-[2rem_1fr_8rem_6rem_6rem_14rem] gap-2 items-center px-3 py-2',
                'hover:bg-muted/30 cursor-pointer transition-colors',
                isExpanded && 'bg-muted/20',
              )}
              onClick={() => setExpandedId(isExpanded ? null : conflict.id)}
            >
              <div>
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
              </div>

              <div>
                <span className="font-mono text-sm">{conflict.node_mac}</span>
                {conflict.node_id && (
                  <span className="text-xs text-muted-foreground ml-2">
                    ({conflict.node_id})
                  </span>
                )}
              </div>

              <div>
                <Badge
                  variant="outline"
                  className={cn(
                    'text-xs',
                    TYPE_BADGE_STYLE[conflict.conflict_type] ?? '',
                  )}
                >
                  {CONFLICT_TYPE_LABELS[conflict.conflict_type]}
                </Badge>
              </div>

              <div className="text-sm font-medium capitalize">
                {conflict.local_state}
              </div>

              <div className="text-sm font-medium capitalize">
                {conflict.central_state}
              </div>

              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  disabled={isResolving}
                  onClick={() => onResolve(conflict.id, 'keep_central')}
                >
                  Central
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  disabled={isResolving}
                  onClick={() => onResolve(conflict.id, 'keep_local')}
                >
                  Local
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  disabled={isResolving}
                  onClick={() =>
                    setExpandedId(isExpanded ? null : conflict.id)
                  }
                >
                  Diff
                </Button>
              </div>
            </div>

            {/* Expanded diff view */}
            {isExpanded && (
              <div className="px-3 pb-3 border-t bg-muted/10">
                <ConflictDiffView
                  conflict={conflict}
                  onResolve={(resolution) => onResolve(conflict.id, resolution)}
                  isResolving={isResolving}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
