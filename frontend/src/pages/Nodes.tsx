import { useState } from 'react'
import { Card, CardContent, CardHeader, Button } from '@/components/ui'
import { Plus, RefreshCw } from 'lucide-react'
import { NodeTable } from '@/components/nodes/NodeTable'
import { useNodes } from '@/hooks'
import type { NodeState } from '@/types'

export function Nodes() {
  const [stateFilter, setStateFilter] = useState<NodeState | null>(null)

  const { data: response, isLoading, refetch, isFetching } = useNodes(
    stateFilter ? { state: stateFilter, limit: 1000 } : { limit: 1000 }
  )

  const nodes = response?.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Nodes</h2>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
          </Button>
          <Button disabled>
            <Plus className="mr-2 h-4 w-4" />
            Register Node
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-0" />
        <CardContent>
          <NodeTable
            nodes={nodes}
            isLoading={isLoading}
            onStateFilter={setStateFilter}
            selectedState={stateFilter}
          />
        </CardContent>
      </Card>
    </div>
  )
}
