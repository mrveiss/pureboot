import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, FolderOpen, Users, Settings, GitBranch } from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
} from '@/components/ui'
import { NodeTable } from '@/components/nodes/NodeTable'
import { useGroup, useGroupNodes } from '@/hooks'

export function GroupDetail() {
  const { groupId } = useParams<{ groupId: string }>()
  const { data: groupResponse, isLoading: groupLoading } = useGroup(groupId ?? '')
  const { data: nodesResponse, isLoading: nodesLoading } = useGroupNodes(groupId ?? '')

  if (groupLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading group details...</div>
      </div>
    )
  }

  const group = groupResponse?.data
  const nodes = nodesResponse?.data ?? []

  if (!group) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" asChild>
          <Link to="/groups">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Groups
          </Link>
        </Button>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-destructive">Group not found</div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" asChild>
            <Link to="/groups">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              <FolderOpen className="h-6 w-6" />
              {group.name}
            </h2>
            <p className="text-muted-foreground">
              {group.description || 'No description'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {group.auto_provision && (
            <Badge variant="secondary" className="bg-green-500/10 text-green-600">
              Auto-provision
            </Badge>
          )}
          <Button variant="outline" disabled>
            <Settings className="mr-2 h-4 w-4" />
            Settings
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Nodes</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{group.node_count}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Default Workflow</CardTitle>
            <GitBranch className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {group.default_workflow_id || 'None'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Created</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {new Date(group.created_at).toLocaleDateString()}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Nodes Table */}
      <Card>
        <CardHeader>
          <CardTitle>Nodes in this Group</CardTitle>
        </CardHeader>
        <CardContent>
          <NodeTable
            nodes={nodes}
            isLoading={nodesLoading}
            enableSelection={true}
          />
        </CardContent>
      </Card>
    </div>
  )
}
