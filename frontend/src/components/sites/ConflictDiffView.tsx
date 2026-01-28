import { ArrowRight, Clock } from 'lucide-react'
import { Button, Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { cn } from '@/lib/utils'
import type { SiteConflict, ConflictResolutionAction } from '@/types/site'
import { CONFLICT_TYPE_LABELS } from '@/types/site'

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString()
}

function isNewer(a: string, b: string): boolean {
  return new Date(a).getTime() > new Date(b).getTime()
}

interface ConflictDiffViewProps {
  conflict: SiteConflict
  onResolve: (resolution: ConflictResolutionAction) => void
  isResolving?: boolean
}

export function ConflictDiffView({ conflict, onResolve, isResolving }: ConflictDiffViewProps) {
  const localIsNewer = isNewer(conflict.local_updated_at, conflict.central_updated_at)

  return (
    <div className="pt-3 space-y-3">
      <div className="text-xs text-muted-foreground">
        Type: {CONFLICT_TYPE_LABELS[conflict.conflict_type]}
        {' | '}
        Detected: {formatDateTime(conflict.detected_at)}
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* Local state */}
        <Card className={cn(localIsNewer && 'ring-1 ring-blue-500/30')}>
          <CardHeader className="pb-2 px-3 pt-3">
            <CardTitle className="text-xs font-medium flex items-center justify-between">
              <span>Local (Agent Cache)</span>
              {localIsNewer && (
                <span className="text-blue-500 text-xs font-normal">Newer</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">State</span>
                <span
                  className={cn(
                    'font-medium capitalize px-2 py-0.5 rounded text-xs',
                    conflict.local_state !== conflict.central_state
                      ? 'bg-green-500/10 text-green-600'
                      : '',
                  )}
                >
                  {conflict.local_state}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Updated</span>
                <span className="text-xs flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDateTime(conflict.local_updated_at)}
                </span>
              </div>
              {conflict.node_id && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Node ID</span>
                  <span className="font-mono text-xs">{conflict.node_id}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Central state */}
        <Card className={cn(!localIsNewer && 'ring-1 ring-blue-500/30')}>
          <CardHeader className="pb-2 px-3 pt-3">
            <CardTitle className="text-xs font-medium flex items-center justify-between">
              <span>Central (Controller)</span>
              {!localIsNewer && (
                <span className="text-blue-500 text-xs font-normal">Newer</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">State</span>
                <span
                  className={cn(
                    'font-medium capitalize px-2 py-0.5 rounded text-xs',
                    conflict.local_state !== conflict.central_state
                      ? 'bg-red-500/10 text-red-600'
                      : '',
                  )}
                >
                  {conflict.central_state}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Updated</span>
                <span className="text-xs flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDateTime(conflict.central_updated_at)}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Resolution buttons */}
      <div className="flex items-center gap-2 justify-end">
        <Button
          variant="outline"
          size="sm"
          disabled={isResolving}
          onClick={() => onResolve('keep_local')}
        >
          Accept Local
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={isResolving}
          onClick={() => onResolve('keep_central')}
        >
          Accept Central
        </Button>
      </div>
    </div>
  )
}
