import { Card, CardContent, CardHeader, CardTitle, Badge, Button } from '@/components/ui'
import { Plus, Search } from 'lucide-react'
import { Input } from '@/components/ui'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, type NodeState } from '@/types'
import { cn } from '@/lib/utils'

// Placeholder data
const mockNodes = [
  { id: '1', hostname: 'web-server-01', mac_address: 'AA:BB:CC:DD:EE:01', state: 'active' as NodeState, arch: 'x86_64', last_seen_at: '2m ago' },
  { id: '2', hostname: 'db-server-01', mac_address: 'AA:BB:CC:DD:EE:02', state: 'pending' as NodeState, arch: 'x86_64', last_seen_at: '5m ago' },
  { id: '3', hostname: null, mac_address: 'AA:BB:CC:DD:EE:03', state: 'discovered' as NodeState, arch: 'arm64', last_seen_at: '1m ago' },
  { id: '4', hostname: 'old-server-03', mac_address: 'AA:BB:CC:DD:EE:04', state: 'retired' as NodeState, arch: 'x86_64', last_seen_at: '3d ago' },
]

function StateBadge({ state }: { state: NodeState }) {
  return (
    <Badge
      variant="outline"
      className={cn('border-0 text-white', NODE_STATE_COLORS[state])}
    >
      {NODE_STATE_LABELS[state]}
    </Badge>
  )
}

export function Nodes() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Nodes</h2>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Register Node
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search nodes..." className="pl-10" />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="p-3 text-left text-sm font-medium">Hostname</th>
                  <th className="p-3 text-left text-sm font-medium">MAC Address</th>
                  <th className="p-3 text-left text-sm font-medium">State</th>
                  <th className="p-3 text-left text-sm font-medium">Arch</th>
                  <th className="p-3 text-left text-sm font-medium">Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {mockNodes.map((node) => (
                  <tr key={node.id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="p-3 text-sm font-medium">
                      {node.hostname || <span className="text-muted-foreground">(undiscovered)</span>}
                    </td>
                    <td className="p-3 text-sm font-mono text-muted-foreground">
                      {node.mac_address}
                    </td>
                    <td className="p-3">
                      <StateBadge state={node.state} />
                    </td>
                    <td className="p-3 text-sm">{node.arch}</td>
                    <td className="p-3 text-sm text-muted-foreground">{node.last_seen_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
